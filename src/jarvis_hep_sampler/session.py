"""Run one independent plug-in for one scan (technical design §4.3–§4.5, §7.1).

:class:`IndependentSession` is the single implementation of the independent
profile. The offline driver (:mod:`jarvis_hep_sampler.testing`) and the
Jarvis-HEP adapter both use it, so ``Jarvis sampler check`` and a real scan
produce the same points.

The session owns: option checks, ``validate_options``, ``prepare``, the
per-index random streams, the ``draw_block`` cache and the output contract.
Jarvis-HEP owns everything after a point leaves :meth:`IndependentSession.point`:
mapping, selection, UUIDs, Redis, archiving and checkpoints.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

import numpy as np

from jarvis_hep_sampler.contexts import BlockContext, DrawContext, SamplerStats, SetupContext
from jarvis_hep_sampler.errors import (
    PluginConfigError,
    PluginError,
    PluginLoadError,
    PluginOutputError,
)
from jarvis_hep_sampler.loader import LoadedPlugin
from jarvis_hep_sampler.log import SamplerLog
from jarvis_hep_sampler.metadata import INDEPENDENT
from jarvis_hep_sampler.options import (
    OptionIssue,
    freeze_options,
    parse_reserved,
    schema_issues,
    split_bounds,
)
from jarvis_hep_sampler.output import check_block, check_point
from jarvis_hep_sampler.streams import block_stream, candidate_stream

STATUS_MAX_KEYS = 8
STATUS_MAX_TEXT = 32
HOOK_ERROR_LIMIT = 16
HOOK_ERROR_MAX_TEXT = 512
DEFAULT_STOP_REASON = "point_number reached"


class IndependentSession:
    """Prepare once, then produce the point for any candidate index."""

    def __init__(
        self,
        plugin: LoadedPlugin,
        *,
        seed: int,
        point_number: int,
        variable_names: Sequence[str],
        options: Mapping[str, Any] | None = None,
        log: SamplerLog | None = None,
    ) -> None:
        if plugin.metadata.profile != INDEPENDENT:
            raise PluginLoadError(
                f"IndependentSession cannot run profile {plugin.metadata.profile!r}",
                method=plugin.method,
            )
        settings = parse_reserved({"seed": seed, "point_number": point_number}, INDEPENDENT)
        names = tuple(str(name) for name in variable_names)
        if not names:
            raise PluginConfigError(
                "a sampler plug-in needs at least one variable", method=plugin.method
            )
        self.plugin = plugin
        self.log = log if log is not None else SamplerLog(plugin.method)
        self.options = freeze_options(options)
        self.setup = SetupContext(
            seed=settings.seed,
            point_number=int(settings.point_number or 0),
            dimension=len(names),
            variable_names=names,
            options=self.options,
            log=self.log,
        )
        self.hook_errors: list[str] = []
        self._failed_hooks: set[str] = set()
        self._plan: Any = None
        self._prepared = False
        self._block: tuple[int, np.ndarray] | None = None

    @classmethod
    def from_bounds(
        cls,
        plugin: LoadedPlugin,
        bounds: Mapping[str, Any] | None,
        *,
        variable_names: Sequence[str],
        log: SamplerLog | None = None,
    ) -> IndependentSession:
        """Build a session from ``Sampling.Bounds`` as written in the task card."""
        reserved, options = split_bounds(bounds, INDEPENDENT)
        settings = parse_reserved(reserved, INDEPENDENT)
        return cls(
            plugin,
            seed=settings.seed,
            point_number=int(settings.point_number or 0),
            variable_names=variable_names,
            options=options,
            log=log,
        )

    # ------------------------------------------------------------- properties
    @property
    def method(self) -> str:
        return self.plugin.method

    @property
    def seed(self) -> int:
        return self.setup.seed

    @property
    def point_number(self) -> int:
        return self.setup.point_number

    @property
    def dimension(self) -> int:
        return self.setup.dimension

    @property
    def block_size(self) -> int | None:
        return self.plugin.metadata.block_size

    @property
    def plan(self) -> Any:
        return self._plan

    @property
    def prepared(self) -> bool:
        return self._prepared

    # ---------------------------------------------------------------- prepare
    def option_issues(self) -> list[OptionIssue]:
        """``OPTIONS_SCHEMA`` violations; always empty when there is no schema."""
        return schema_issues(self.plugin.options_schema, self.options)

    def prepare(self) -> None:
        """Check the options, run ``validate_options`` and ``prepare``. Call once."""
        issues = self.option_issues()
        if issues:
            first = issues[0]
            more = f" (+{len(issues) - 1} more)" if len(issues) > 1 else ""
            raise PluginConfigError(
                f"options do not match OPTIONS_SCHEMA: {first.location()}: {first.message}{more}",
                method=self.method,
                yaml_path=first.location(),
                source=str(self.plugin.source_path),
            )
        validate = self.plugin.function("validate_options")
        if validate is not None:
            try:
                validate(self.options)
            except Exception as exc:
                raise PluginConfigError(
                    f"validate_options() rejected the options: {type(exc).__name__}: {exc}",
                    method=self.method,
                    source=str(self.plugin.source_path),
                ) from exc
        prepare = self.plugin.function("prepare")
        if prepare is not None:
            try:
                self._plan = prepare(self.setup)
            except Exception as exc:
                raise PluginConfigError(
                    f"prepare() failed: {type(exc).__name__}: {exc}",
                    method=self.method,
                    source=str(self.plugin.source_path),
                ) from exc
        self._block = None
        self._prepared = True

    # ----------------------------------------------------------------- points
    def point(self, candidate_index: int) -> np.ndarray:
        """Return the unit-cube point for *candidate_index* (a fresh float64 array)."""
        if not self._prepared:
            raise RuntimeError("IndependentSession.prepare() must run before point()")
        index = int(candidate_index)
        if not 0 <= index < self.point_number:
            raise IndexError(
                f"candidate index {index} is outside [0, {self.point_number})"
            )
        if self.block_size is not None:
            block_index, row = divmod(index, self.block_size)
            return self._block_rows(block_index)[row].copy()
        context = DrawContext(
            candidate_index=index,
            point_number=self.point_number,
            dimension=self.dimension,
            variable_names=self.setup.variable_names,
            options=self.options,
            log=self.log,
        )
        draw = self.plugin.functions["draw"]
        try:
            raw = draw(context, candidate_stream(self.seed, index), self._plan)
        except PluginError:
            raise
        except Exception as exc:
            raise PluginOutputError(
                f"draw() raised {type(exc).__name__}: {exc}",
                method=self.method,
                candidate_index=index,
                source=str(self.plugin.source_path),
            ) from exc
        return check_point(
            raw,
            dimension=self.dimension,
            candidate_index=index,
            variable_names=self.setup.variable_names,
            method=self.method,
        )

    def points(self, start: int = 0, stop: int | None = None) -> Iterator[tuple[int, np.ndarray]]:
        """Yield ``(candidate_index, point)`` for ``start <= index < stop``."""
        end = self.point_number if stop is None else min(int(stop), self.point_number)
        for index in range(max(0, int(start)), end):
            yield index, self.point(index)

    def _block_rows(self, block_index: int) -> np.ndarray:
        if self._block is not None and self._block[0] == block_index:
            return self._block[1]
        size = int(self.block_size or 0)
        context = BlockContext(
            block_index=block_index,
            block_size=size,
            point_number=self.point_number,
            dimension=self.dimension,
            variable_names=self.setup.variable_names,
            options=self.options,
            log=self.log,
        )
        draw_block = self.plugin.functions["draw_block"]
        try:
            raw = draw_block(context, block_stream(self.seed, block_index), self._plan)
        except PluginError:
            raise
        except Exception as exc:
            raise PluginOutputError(
                f"draw_block() raised {type(exc).__name__}: {exc}",
                method=self.method,
                candidate_index=block_index * size,
                source=str(self.plugin.source_path),
            ) from exc
        rows = check_block(
            raw,
            block_size=size,
            dimension=self.dimension,
            block_index=block_index,
            valid_rows=self.point_number - block_index * size,
            variable_names=self.setup.variable_names,
            method=self.method,
        )
        self._block = (block_index, rows)
        return rows

    # ------------------------------------------------------------------ hooks
    def stats(self, candidates: int, accepted: int) -> SamplerStats:
        return SamplerStats(
            candidates=int(candidates), accepted=int(accepted), point_number=self.point_number
        )

    def settings_rows(self) -> list[tuple[str, Any]]:
        """Plug-in rows for the settings table (S2)."""
        return self._rows("settings_rows", self.setup, self._plan)

    def summary_rows(self, stats: SamplerStats) -> list[tuple[str, Any]]:
        """Plug-in rows for the summary table (S10)."""
        return self._rows("summary_rows", self._plan, stats)

    def stop_reason(self, stats: SamplerStats) -> str | None:
        """The plug-in's stop reason, else ``point_number reached`` once the budget is spent."""
        reason = self._call_hook(
            "stop_reason", None, self._plan, stats,
            normalize=lambda value: str(value) if value else None,
        )
        if reason is not None:
            return reason
        return DEFAULT_STOP_REASON if stats.candidates >= stats.point_number else None

    def status(self, stats: SamplerStats) -> dict[str, Any]:
        """Monitor metrics from the plug-in: at most 8 scalar keys, short strings."""
        return self._call_hook("status", {}, self._plan, stats, normalize=self._status_metrics)

    @staticmethod
    def _status_metrics(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise TypeError(f"returned {type(raw).__name__}, expected a dict")
        metrics: dict[str, Any] = {}
        for key, value in raw.items():
            if len(metrics) >= STATUS_MAX_KEYS:
                break
            label = str(key)[:STATUS_MAX_TEXT]
            if isinstance(value, np.generic):
                value = value.item()
            if isinstance(value, (bool, int)):
                metrics[label] = value
            elif isinstance(value, float) and math.isfinite(value):
                metrics[label] = value
            elif isinstance(value, str):
                metrics[label] = value[:STATUS_MAX_TEXT]
        return metrics

    def _rows(self, name: str, *args: Any) -> list[tuple[str, Any]]:
        return self._call_hook(
            name, [], *args,
            normalize=lambda raw: [(str(key), value) for key, value in (raw or [])],
        )

    def _call_hook(
        self, name: str, default: Any, *args: Any, normalize: Callable[[Any], Any]
    ) -> Any:
        hook = self.plugin.function(name)
        if hook is None:
            return default
        try:
            # A generator or custom mapping can fail only when consumed, and
            # truth/str conversions also run plug-in code. Protect all of it.
            return normalize(hook(*args))
        except Exception as exc:
            try:
                detail = str(exc)
            except Exception:
                detail = "<exception text unavailable>"
            self._hook_failed(name, f"raised {type(exc).__name__}: {detail}")
            return default

    def _hook_failed(self, name: str, detail: str) -> None:
        # Keep one warning per hook per session, even if its exception text
        # changes at every candidate. Reporting must not grow with the scan.
        if name in self._failed_hooks:
            return
        self._failed_hooks.add(name)
        message = f"{self.method} Sampler could not report {name}: {detail}"[:HOOK_ERROR_MAX_TEXT]
        if len(self.hook_errors) < HOOK_ERROR_LIMIT:
            self.hook_errors.append(message)
        self.log.warning(message)


__all__ = ["DEFAULT_STOP_REASON", "IndependentSession"]
