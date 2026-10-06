"""Exceptions raised for sampler plug-ins (technical design §4.7).

Every error carries the context Jarvis-HEP prints in the sampler failure
record: the method, the plug-in source, the task-card path and, for output
errors, the candidate index. The plug-in's own exception, when there is one,
is chained as ``__cause__`` so its traceback reaches the log file.
"""

from __future__ import annotations

from typing import Any


class PluginError(Exception):
    """Base class for all plug-in errors."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        source: str | None = None,
        yaml_path: str | None = None,
        candidate_index: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.method = method
        self.source = source
        self.yaml_path = yaml_path
        self.candidate_index = candidate_index

    def context_rows(self) -> list[tuple[str, Any]]:
        """Return the known context as ``(field, value)`` rows."""
        rows: list[tuple[str, Any]] = []
        if self.method:
            rows.append(("method", self.method))
        if self.candidate_index is not None:
            rows.append(("candidate", self.candidate_index))
        if self.yaml_path:
            rows.append(("at", self.yaml_path))
        if self.source:
            rows.append(("source", self.source))
        return rows

    def __str__(self) -> str:
        rows = self.context_rows()
        if not rows:
            return self.message
        details = ", ".join(f"{key} {value}" for key, value in rows)
        return f"{self.message} ({details})"


class PluginLoadError(PluginError):
    """The plug-in file cannot be imported or does not follow the file convention."""


class PluginConfigError(PluginError):
    """The options, ``validate_options`` or ``prepare`` rejected the configuration."""


class PluginOutputError(PluginError):
    """``draw`` / ``draw_block`` raised, or returned a point that breaks the output contract."""


class PluginResumeMismatch(PluginError):
    """A resumed scan does not match the identity recorded by the original run."""


class RegistryError(PluginError):
    """The user sampler registry is unreadable or one of its entries is broken."""


__all__ = [
    "PluginConfigError",
    "PluginError",
    "PluginLoadError",
    "PluginOutputError",
    "PluginResumeMismatch",
    "RegistryError",
]
