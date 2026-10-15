"""The ``PLUGIN`` metadata dict and the method-name rule (technical design §4.2)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from jarvis_hep_sampler.errors import PluginLoadError

API_VERSION = 1

INDEPENDENT = "independent"
GENERATIONAL = "generational"
# Profiles whose interface is frozen in API v1.
KNOWN_PROFILES = (INDEPENDENT, GENERATIONAL)
# Profiles this SDK version can run. Generational arrives with S3.
SUPPORTED_PROFILES = (INDEPENDENT,)

# Same shape as every built-in Sampling.Method name (Random, AdaptiveBridson, ...).
METHOD_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]{1,63}$")

FEEDBACK_MODES = ("minimal", "fields", "all_flat")

_REQUIRED_KEYS = ("api_version", "method", "version", "profile")
_OPTIONAL_KEYS = (
    "description",
    "statistical",
    "block_size",
    "state_version",
    "feedback_return",
)
_FEEDBACK_KEYS = frozenset({"mode", "fields", "include_logl"})


def check_method_name(name: object, *, reserved_names: Iterable[str] = ()) -> str:
    """Return *name* if it is a valid plug-in method name, else raise.

    *reserved_names* are the built-in Jarvis-HEP methods; a plug-in may not
    take one of them, whatever the letter case.
    """
    if not isinstance(name, str) or not METHOD_NAME_RE.fullmatch(name):
        raise PluginLoadError(
            f"method name {name!r} must start with an upper-case letter and use "
            "2-64 letters or digits, like the built-in methods (e.g. MyLatinHypercube)"
        )
    folded = name.casefold()
    for reserved in reserved_names:
        if folded == str(reserved).casefold():
            raise PluginLoadError(
                f"method name {name!r} is a built-in Jarvis-HEP method; choose another name",
                method=name,
            )
    return name


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


@dataclass(frozen=True)
class PluginMetadata:
    """Validated contents of a plug-in's ``PLUGIN`` dict."""

    api_version: int
    method: str
    version: str
    profile: str
    description: str = ""
    statistical: bool = False
    block_size: int | None = None
    state_version: int | None = None
    feedback_return: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON form, as stored in the registry."""
        data: dict[str, Any] = {
            "api_version": self.api_version,
            "method": self.method,
            "version": self.version,
            "profile": self.profile,
            "description": self.description,
            "statistical": self.statistical,
        }
        if self.block_size is not None:
            data["block_size"] = self.block_size
        if self.state_version is not None:
            data["state_version"] = self.state_version
        if self.feedback_return is not None:
            data["feedback_return"] = json.loads(json.dumps(dict(self.feedback_return)))
        return data


def parse_metadata(raw: object, *, reserved_names: Iterable[str] = ()) -> PluginMetadata:
    """Validate a ``PLUGIN`` dict and return it as :class:`PluginMetadata`."""
    if not isinstance(raw, Mapping):
        raise PluginLoadError(f"PLUGIN must be a dict, got {type(raw).__name__}")
    method_hint = raw.get("method") if isinstance(raw.get("method"), str) else None

    def fail(message: str) -> PluginLoadError:
        return PluginLoadError(message, method=method_hint)

    unknown = sorted(str(key) for key in raw if key not in _REQUIRED_KEYS + _OPTIONAL_KEYS)
    if unknown:
        allowed = ", ".join(_REQUIRED_KEYS + _OPTIONAL_KEYS)
        raise fail(f"PLUGIN has unknown key(s) {', '.join(unknown)}; allowed keys: {allowed}")
    missing = [key for key in _REQUIRED_KEYS if key not in raw]
    if missing:
        raise fail(f"PLUGIN is missing required key(s): {', '.join(missing)}")
    try:
        json.dumps(dict(raw), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise fail(f"PLUGIN must contain only JSON data: {exc}") from exc

    api_version = raw["api_version"]
    if isinstance(api_version, bool) or not isinstance(api_version, int):
        raise fail(f"PLUGIN['api_version'] must be an integer, got {api_version!r}")
    if api_version != API_VERSION:
        raise fail(
            f"PLUGIN['api_version'] is {api_version}; this Jarvis-HEP-Sampler supports "
            f"API version {API_VERSION}"
        )

    method = check_method_name(raw["method"], reserved_names=reserved_names)

    version = raw["version"]
    if not isinstance(version, str) or not version.strip():
        raise fail("PLUGIN['version'] must be a non-empty string, e.g. '0.1.0'")

    profile = raw["profile"]
    if profile not in KNOWN_PROFILES:
        raise fail(f"PLUGIN['profile'] must be one of {', '.join(KNOWN_PROFILES)}; got {profile!r}")

    description = raw.get("description", "")
    if not isinstance(description, str):
        raise fail("PLUGIN['description'] must be a string")

    statistical = raw.get("statistical", False)
    if not isinstance(statistical, bool):
        raise fail("PLUGIN['statistical'] must be true or false")

    block_size = raw.get("block_size")
    if block_size is not None:
        if profile != INDEPENDENT:
            raise fail("PLUGIN['block_size'] only applies to the independent profile")
        if not _positive_int(block_size):
            raise fail(f"PLUGIN['block_size'] must be a positive integer, got {block_size!r}")

    state_version = raw.get("state_version")
    if profile == GENERATIONAL:
        if not _positive_int(state_version):
            raise fail(
                "the generational profile needs PLUGIN['state_version'] (a positive integer)"
            )
    elif state_version is not None:
        raise fail("PLUGIN['state_version'] only applies to the generational profile")

    feedback_return = raw.get("feedback_return")
    if feedback_return is not None:
        if profile != GENERATIONAL:
            raise fail("PLUGIN['feedback_return'] only applies to the generational profile")
        feedback_return = _check_feedback_return(feedback_return, fail)

    return PluginMetadata(
        api_version=api_version,
        method=method,
        version=version.strip(),
        profile=profile,
        description=description.strip(),
        statistical=statistical,
        block_size=block_size,
        state_version=state_version,
        feedback_return=feedback_return,
    )


def _check_feedback_return(value: object, fail: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise fail("PLUGIN['feedback_return'] must be a dict")
    unknown = sorted(str(key) for key in value if key not in _FEEDBACK_KEYS)
    if unknown:
        raise fail(f"PLUGIN['feedback_return'] has unknown key(s): {', '.join(unknown)}")
    mode = value.get("mode", "minimal")
    if mode not in FEEDBACK_MODES:
        raise fail(f"PLUGIN['feedback_return']['mode'] must be one of {', '.join(FEEDBACK_MODES)}")
    fields = value.get("fields", [])
    if not isinstance(fields, (list, tuple)) or not all(
        isinstance(item, str) and item for item in fields
    ):
        raise fail("PLUGIN['feedback_return']['fields'] must be a list of names")
    include_logl = value.get("include_logl", True)
    if not isinstance(include_logl, bool):
        raise fail("PLUGIN['feedback_return']['include_logl'] must be true or false")
    return {"mode": mode, "fields": list(fields), "include_logl": include_logl}


__all__ = [
    "API_VERSION",
    "FEEDBACK_MODES",
    "GENERATIONAL",
    "INDEPENDENT",
    "KNOWN_PROFILES",
    "METHOD_NAME_RE",
    "PluginMetadata",
    "SUPPORTED_PROFILES",
    "check_method_name",
    "parse_metadata",
]
