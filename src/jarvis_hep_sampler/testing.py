"""Offline driver and conformance checks (technical design §5.1 ``check``, §9.1).

Nothing here needs Redis or Jarvis-HEP. :func:`check_plugin` is what
``jsampler check`` runs. :func:`reference_stream` replays the same session a
scan uses. It is not an independent proof of random-stream correctness.

Selection here acts on unit-cube points. In a real scan Jarvis-HEP applies
``Sampling.selection`` to the mapped physical values; the index bookkeeping
is the same.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from jarvis_hep_sampler.errors import PluginError
from jarvis_hep_sampler.loader import LoadedPlugin, load_plugin_file, load_plugin_source
from jarvis_hep_sampler.log import SamplerLog
from jarvis_hep_sampler.options import thaw_options
from jarvis_hep_sampler.session import IndependentSession

Selection = Callable[[np.ndarray], bool]
PluginLike = LoadedPlugin | str | Path


def _plugin(plugin: PluginLike) -> LoadedPlugin:
    return plugin if isinstance(plugin, LoadedPlugin) else load_plugin_file(plugin)


def _names(variable_names: Sequence[str] | None, dimension: int | None) -> tuple[str, ...]:
    if variable_names is not None:
        return tuple(str(name) for name in variable_names)
    if dimension is None:
        raise ValueError("pass variable_names or dimension")
    return tuple(f"x{index}" for index in range(int(dimension)))


def _session(
    plugin: LoadedPlugin,
    *,
    seed: int,
    point_number: int,
    names: tuple[str, ...],
    options: Mapping[str, Any] | None,
    log: SamplerLog | None,
) -> IndependentSession:
    session = IndependentSession(
        plugin,
        seed=seed,
        point_number=point_number,
        variable_names=names,
        options=options,
        log=log,
    )
    session.prepare()
    return session


@dataclass(frozen=True)
class ReferencePoint:
    """One accepted point: what Jarvis-HEP must submit at ``accepted_index``."""

    candidate_index: int
    accepted_index: int
    u: np.ndarray


def reference_stream(
    plugin: PluginLike,
    *,
    point_number: int,
    seed: int = 0,
    variable_names: Sequence[str] | None = None,
    dimension: int | None = None,
    options: Mapping[str, Any] | None = None,
    selection: Selection | None = None,
    start_candidate: int = 0,
    start_accepted: int = 0,
    log: SamplerLog | None = None,
) -> Iterator[ReferencePoint]:
    """Yield the accepted points in order, starting from a ``(candidate, accepted)`` cursor.

    A fresh session is prepared, exactly as a resumed scan does, so starting
    mid-stream must reproduce the tail of an uninterrupted stream.
    """
    session = _session(
        _plugin(plugin),
        seed=seed,
        point_number=point_number,
        names=_names(variable_names, dimension),
        options=options,
        log=log,
    )
    accepted = int(start_accepted)
    for candidate, u in session.points(start_candidate):
        if selection is not None and not selection(u):
            continue
        yield ReferencePoint(candidate_index=candidate, accepted_index=accepted, u=u)
        accepted += 1


@dataclass(frozen=True)
class OfflineRun:
    """Result of :func:`run_offline`."""

    method: str
    points: np.ndarray
    candidate_indices: tuple[int, ...]
    candidates: int
    accepted: int
    settings_rows: list[tuple[str, Any]]
    summary_rows: list[tuple[str, Any]]
    stop_reason: str | None
    status: dict[str, Any]
    hook_errors: list[str]


def run_offline(
    plugin: PluginLike,
    *,
    point_number: int,
    seed: int = 0,
    variable_names: Sequence[str] | None = None,
    dimension: int | None = None,
    options: Mapping[str, Any] | None = None,
    selection: Selection | None = None,
    log: SamplerLog | None = None,
) -> OfflineRun:
    """Run the whole candidate budget without Redis and collect what a scan would log."""
    loaded = _plugin(plugin)
    names = _names(variable_names, dimension)
    session = _session(
        loaded, seed=seed, point_number=point_number, names=names, options=options, log=log
    )
    points: list[np.ndarray] = []
    indices: list[int] = []
    for candidate, u in session.points():
        if selection is not None and not selection(u):
            continue
        points.append(u)
        indices.append(candidate)
    stats = session.stats(candidates=session.point_number, accepted=len(points))
    array = np.array(points, dtype=np.float64).reshape(len(points), len(names))
    return OfflineRun(
        method=loaded.method,
        points=array,
        candidate_indices=tuple(indices),
        candidates=session.point_number,
        accepted=len(points),
        settings_rows=session.settings_rows(),
        summary_rows=session.summary_rows(stats),
        stop_reason=session.stop_reason(stats),
        status=session.status(stats),
        hook_errors=list(session.hook_errors),
    )


@dataclass(frozen=True)
class CheckItem:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class CheckReport:
    """What ``jsampler check`` prints."""

    method: str | None
    items: tuple[CheckItem, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    def rows(self) -> list[tuple[str, str]]:
        return [(item.name, f"{'ok' if item.ok else 'FAIL'}  {item.detail}") for item in self.items]

    def failures(self) -> list[CheckItem]:
        return [item for item in self.items if not item.ok]


def check_plugin(
    plugin: PluginLike,
    *,
    point_number: int = 100,
    seed: int = 0,
    variable_names: Sequence[str] | None = None,
    dimension: int | None = None,
    options: Mapping[str, Any] | None = None,
    reserved_names: Sequence[str] = (),
    log: SamplerLog | None = None,
) -> CheckReport:
    """Check a plug-in offline. Stops at the first failing stage; never raises for plug-in bugs.

    Checks: load, options, prepare (with ``validate_options``), the output
    contract for every candidate, repeatability with the same seed, restart
    from the middle (what a resume does), and the logging hooks. It does not
    judge whether the algorithm is scientifically right.
    """
    items: list[CheckItem] = []

    def report(method: str | None = None) -> CheckReport:
        return CheckReport(method=method, items=tuple(items))

    try:
        loaded = (
            plugin
            if isinstance(plugin, LoadedPlugin)
            else load_plugin_file(plugin, reserved_names=reserved_names)
        )
    except PluginError as exc:
        items.append(CheckItem("load", False, str(exc)))
        return report()
    meta = loaded.metadata
    items.append(
        CheckItem(
            "load",
            True,
            f"{meta.method} {meta.version}, profile {meta.profile}"
            + (f", block_size {meta.block_size}" if meta.block_size else ""),
        )
    )
    names = _names(variable_names, dimension)

    try:
        session = IndependentSession(
            loaded, seed=seed, point_number=point_number, variable_names=names, options=options,
            log=log,
        )
    except PluginError as exc:
        items.append(CheckItem("options", False, str(exc)))
        return report(meta.method)
    issues = session.option_issues()
    if loaded.options_schema is None:
        items.append(CheckItem("options", True, "no OPTIONS_SCHEMA; options not checked"))
    elif issues:
        detail = "; ".join(f"{issue.location()}: {issue.message}" for issue in issues)
        items.append(CheckItem("options", False, detail))
        return report(meta.method)
    else:
        items.append(CheckItem("options", True, "match OPTIONS_SCHEMA"))

    started = time.perf_counter()
    try:
        session.prepare()
    except PluginError as exc:
        items.append(CheckItem("prepare", False, str(exc)))
        return report(meta.method)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    items.append(CheckItem("prepare", True, f"{elapsed_ms:.1f} ms"))

    try:
        first = np.array([u for _, u in session.points()])
    except PluginError as exc:
        items.append(CheckItem("draw", False, str(exc)))
        return report(meta.method)
    items.append(
        CheckItem(
            "draw",
            True,
            f"{len(first)} points, shape ({session.dimension},), all in [0, 1]",
        )
    )

    try:
        again = _session(
            load_plugin_source(loaded.source_bytes, origin=loaded.source_path),
            seed=seed, point_number=point_number, names=names, options=options, log=log
        )
        second = np.array([u for _, u in again.points()])
        same = np.array_equal(first, second)
    except PluginError as exc:
        same, detail = False, str(exc)
    else:
        detail = (
            "fresh import with the same seed gives identical points"
            if same else "fresh import with the same seed gave different points"
        )
    items.append(CheckItem("repeatability", same, detail))
    if not same:
        return report(meta.method)

    middle = point_number // 2
    try:
        tail = _process_restart(loaded, session, middle)
        resumed = np.array_equal(tail, first[middle:])
    except (PluginError, OSError, ValueError) as exc:
        resumed, detail = False, str(exc)
    else:
        detail = (
            f"fresh process at candidate {middle} reproduces the stream"
            if resumed
            else f"restart at candidate {middle} gave different points"
        )
    items.append(CheckItem("resume", resumed, detail))

    stats = session.stats(candidates=point_number, accepted=point_number)
    session.settings_rows()
    session.summary_rows(stats)
    session.stop_reason(stats)
    session.status(stats)
    if session.hook_errors:
        items.append(CheckItem("hooks", False, "; ".join(session.hook_errors)))
    else:
        present = [name for name in loaded.hooks if name not in {"prepare", "draw", "draw_block"}]
        items.append(CheckItem("hooks", True, ", ".join(present) if present else "none defined"))
    return report(meta.method)


def _process_restart(plugin: LoadedPlugin, session: IndependentSession, start: int) -> np.ndarray:
    """Replay pinned source bytes in a new interpreter, preserving __file__."""
    with tempfile.TemporaryDirectory(prefix="jhs-check-") as directory:
        config = Path(directory) / "config.json"
        output = Path(directory) / "tail.npy"
        config.write_text(json.dumps({
            "source": base64.b64encode(plugin.source_bytes).decode("ascii"),
            "origin": str(plugin.source_path),
            "seed": session.seed,
            "point_number": session.point_number,
            "variable_names": session.setup.variable_names,
            "options": thaw_options(session.options),
            "start": start,
        }), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "jarvis_hep_sampler._check_restart", str(config), str(output)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[-4096:]
            raise PluginError(f"fresh-process check failed (exit {result.returncode}): {detail}")
        return np.load(output, allow_pickle=False)


def assert_conforms(plugin: PluginLike, **kwargs: Any) -> CheckReport:
    """``assert`` form of :func:`check_plugin` for pytest suites."""
    report = check_plugin(plugin, **kwargs)
    if not report.ok:
        lines = "\n".join(f"  {name}: {detail}" for name, detail in report.rows())
        raise AssertionError(f"plug-in does not conform:\n{lines}")
    return report


__all__ = [
    "CheckItem",
    "CheckReport",
    "OfflineRun",
    "ReferencePoint",
    "assert_conforms",
    "check_plugin",
    "reference_stream",
    "run_offline",
]
