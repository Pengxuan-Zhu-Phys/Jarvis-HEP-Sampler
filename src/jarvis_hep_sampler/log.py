"""Logging facade handed to plug-ins (technical design §4.5).

Plug-ins never touch a logger directly. They call the ``log`` object they get
in every context. Inside Jarvis-HEP the backend writes to
``Jarvis-HEP.Sampler.<Method>`` in the Jarvis layout; offline (``check``,
:mod:`jarvis_hep_sampler.testing`) it writes to the standard ``logging``
logger ``jarvis_hep_sampler.<Method>``.

The runtime alone writes the lifecycle records (start, settings, ready,
checkpoint, failure, result, summary). A plug-in writes only step tables (S5),
adjustments (S7) and saved-file lines (S11), plus free-form messages.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any, Protocol


class LogBackend(Protocol):
    """Where :class:`SamplerLog` sends its records."""

    def emit(self, level: int, message: str) -> None: ...

    def emit_table(self, level: int, title: str, rows: Sequence[tuple[str, Any]]) -> None: ...


def format_table(title: str, rows: Iterable[tuple[str, Any]]) -> str:
    """Render a two-column ``Field | Value`` table like Jarvis-HEP's sampler log."""
    normalized = [(str(key), str(value)) for key, value in rows]
    if not normalized:
        return str(title)
    key_width = max(len("Field"), *(len(key) for key, _ in normalized))
    value_width = max(len("Value"), *(len(value) for _, value in normalized))
    lines = [
        str(title),
        f"{'Field':<{key_width}} | {'Value':<{value_width}}",
        f"{'-' * key_width} | {'-' * value_width}",
    ]
    lines.extend(f"{key:<{key_width}} | {value}" for key, value in normalized)
    return "\n".join(lines)


class StdlibLogBackend:
    """Offline backend: the standard ``logging`` logger ``jarvis_hep_sampler.<method>``."""

    def __init__(self, method: str) -> None:
        self.logger = logging.getLogger(f"jarvis_hep_sampler.{method}")

    def emit(self, level: int, message: str) -> None:
        self.logger.log(level, message)

    def emit_table(self, level: int, title: str, rows: Sequence[tuple[str, Any]]) -> None:
        self.logger.log(level, format_table(title, rows))


class SamplerLog:
    """The ``log`` object a plug-in receives in ``SetupContext`` / ``DrawContext``."""

    def __init__(self, method: str, backend: LogBackend | None = None) -> None:
        self._method = str(method)
        self._backend: LogBackend = backend if backend is not None else StdlibLogBackend(method)

    @property
    def method(self) -> str:
        return self._method

    def step(self, title: str, rows: Iterable[tuple[str, Any]] = ()) -> None:
        """S5: one table per generation or stage, e.g. ``log.step("Chains ->", rows)``."""
        self._backend.emit_table(
            logging.INFO, str(title), [(str(key), value) for key, value in rows]
        )

    def adjust(self, name: str, old: Any, new: Any, why: str) -> None:
        """S7: a setting that was changed, ignored or clamped."""
        self._backend.emit(logging.WARNING, f"{name}: {old} -> {new} ({why})")

    def saved(self, what: str, path: Any) -> None:
        """S11: a result file the plug-in wrote."""
        self._backend.emit(logging.WARNING, f"{what} saved to {path}")

    def debug(self, message: str, *args: Any) -> None:
        self._backend.emit(logging.DEBUG, _format(message, args))

    def info(self, message: str, *args: Any) -> None:
        self._backend.emit(logging.INFO, _format(message, args))

    def warning(self, message: str, *args: Any) -> None:
        self._backend.emit(logging.WARNING, _format(message, args))


def _format(message: str, args: tuple[Any, ...]) -> str:
    return str(message) % args if args else str(message)


__all__ = ["LogBackend", "SamplerLog", "StdlibLogBackend", "format_table"]
