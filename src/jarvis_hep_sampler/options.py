"""Sampling.Bounds: HEP-reserved keys and the plug-in's options (technical design §5.3).

``seed`` (all profiles), ``point_number`` (independent) and ``max_worker``
belong to Jarvis-HEP. Every other Bounds key is a plug-in option. Options are
checked against ``OPTIONS_SCHEMA`` only when the plug-in provides one.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from jarvis_hep_sampler.errors import PluginConfigError, PluginLoadError
from jarvis_hep_sampler.metadata import GENERATIONAL, INDEPENDENT

RESERVED_KEYS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        INDEPENDENT: ("seed", "point_number", "max_worker"),
        GENERATIONAL: ("seed", "max_worker"),
    }
)

# Jarvis-HEP accepts integer strings for these keys (schema ``integerish``).
_INTEGER_STRING = re.compile(r"^[+-]?\d+$")


@dataclass(frozen=True)
class ReservedSettings:
    """Normalised HEP-reserved Bounds keys."""

    seed: int = 0
    point_number: int | None = None
    max_worker: int | None = None


@dataclass(frozen=True)
class OptionIssue:
    """One ``OPTIONS_SCHEMA`` violation, located relative to ``Sampling.Bounds``."""

    path: tuple[str | int, ...]
    message: str

    def location(self, prefix: str = "Bounds") -> str:
        text = prefix
        for part in self.path:
            text += f"[{part}]" if isinstance(part, int) else f".{part}"
        return text


def reserved_keys(profile: str) -> tuple[str, ...]:
    try:
        return RESERVED_KEYS[profile]
    except KeyError as exc:
        raise PluginConfigError(f"unknown profile {profile!r}") from exc


def split_bounds(
    bounds: Mapping[str, Any] | None, profile: str = INDEPENDENT
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split ``Sampling.Bounds`` into ``(reserved, options)``."""
    if bounds is None:
        return {}, {}
    if not isinstance(bounds, Mapping):
        raise PluginConfigError("Sampling.Bounds must be a mapping", yaml_path="Bounds")
    keys = reserved_keys(profile)
    reserved = {str(key): value for key, value in bounds.items() if key in keys}
    options = {key: value for key, value in bounds.items() if key not in keys}
    return reserved, options


def _integer(key: str, value: Any, *, minimum: int) -> int:
    if isinstance(value, bool):
        number = None
    elif isinstance(value, int):
        number = value
    elif isinstance(value, str) and _INTEGER_STRING.match(value.strip()):
        number = int(value.strip())
    else:
        number = None
    if number is None or number < minimum:
        bound = "a non-negative" if minimum == 0 else "a positive"
        raise PluginConfigError(
            f"Bounds.{key} must be {bound} integer, got {value!r}", yaml_path=f"Bounds.{key}"
        )
    return number


def parse_reserved(reserved: Mapping[str, Any], profile: str = INDEPENDENT) -> ReservedSettings:
    """Validate and normalise the HEP-reserved keys for *profile*."""
    unexpected = sorted(set(reserved) - set(reserved_keys(profile)))
    if unexpected:
        raise PluginConfigError(f"Bounds key(s) {', '.join(unexpected)} are not reserved keys")
    seed = _integer("seed", reserved["seed"], minimum=0) if "seed" in reserved else 0
    point_number = None
    if profile == INDEPENDENT:
        if "point_number" not in reserved:
            raise PluginConfigError(
                "the independent profile needs Bounds.point_number", yaml_path="Bounds.point_number"
            )
        point_number = _integer("point_number", reserved["point_number"], minimum=1)
    max_worker = None
    if reserved.get("max_worker") is not None:
        max_worker = _integer("max_worker", reserved["max_worker"], minimum=1)
    return ReservedSettings(seed=seed, point_number=point_number, max_worker=max_worker)


def freeze_options(options: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return a read-only, JSON-only view of *options* (lists become tuples).

    Options take part in the scan identity, so only JSON data is accepted:
    string keys, None, bool, int, finite float, str, lists and mappings.
    """
    if options is None:
        return MappingProxyType({})
    if not isinstance(options, Mapping):
        raise PluginConfigError("plug-in options must be a mapping")
    return _freeze(options, ())


def _freeze(value: Any, path: tuple[str | int, ...]) -> Any:
    where = OptionIssue(path, "").location()
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PluginConfigError(f"{where} must be a finite number", yaml_path=where)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PluginConfigError(
                    f"{where} has a non-string key {key!r}", yaml_path=where
                )
            frozen[key] = _freeze(item, (*path, key))
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, (*path, index)) for index, item in enumerate(value))
    raise PluginConfigError(
        f"{where} holds {type(value).__name__} {value!r}; options must be JSON data",
        yaml_path=where,
    )


def thaw_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Plain ``dict``/``list`` copy of frozen options (for schemas and JSON)."""
    return _thaw(options)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def check_options_schema(schema: object) -> dict[str, Any]:
    """Validate an ``OPTIONS_SCHEMA`` and return a plain JSON copy."""
    if not isinstance(schema, Mapping):
        raise PluginLoadError(
            f"OPTIONS_SCHEMA must be a dict or None, got {type(schema).__name__}"
        )
    try:
        plain = json.loads(json.dumps(dict(schema), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise PluginLoadError(f"OPTIONS_SCHEMA must contain only JSON data: {exc}") from exc
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError

    try:
        Draft202012Validator.check_schema(plain)
    except SchemaError as exc:
        raise PluginLoadError(f"OPTIONS_SCHEMA is not a valid JSON Schema: {exc.message}") from exc
    return plain


def schema_issues(
    schema: Mapping[str, Any] | None, options: Mapping[str, Any]
) -> list[OptionIssue]:
    """Return every ``OPTIONS_SCHEMA`` violation of *options* (empty without a schema)."""
    if schema is None:
        return []
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(dict(schema))
    issues = [
        OptionIssue(tuple(error.absolute_path), error.message)
        for error in validator.iter_errors(thaw_options(options))
    ]
    return sorted(issues, key=lambda issue: (tuple(map(str, issue.path)), issue.message))


__all__ = [
    "OptionIssue",
    "RESERVED_KEYS",
    "ReservedSettings",
    "check_options_schema",
    "freeze_options",
    "parse_reserved",
    "reserved_keys",
    "schema_issues",
    "split_bounds",
    "thaw_options",
]
