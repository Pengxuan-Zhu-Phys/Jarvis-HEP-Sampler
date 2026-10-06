"""Load a plug-in file (technical design §4.1).

The file is read once, hashed, compiled and executed from the same bytes, so
the recorded SHA-256 always matches the code that runs. ``sys.path`` is not
touched; the module is registered under a private name derived from its path
and content.

Importing a plug-in runs user code. Only ``Jarvis sampler load`` / ``check``
and the run preflight do it; ``Jarvis validate`` / ``man`` read the registry.
"""

from __future__ import annotations

import hashlib
import inspect
import sys
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis_hep_sampler.errors import PluginError, PluginLoadError
from jarvis_hep_sampler.metadata import (
    GENERATIONAL,
    INDEPENDENT,
    SUPPORTED_PROFILES,
    PluginMetadata,
    parse_metadata,
)
from jarvis_hep_sampler.options import check_options_schema

# name -> number of positional arguments the function must accept.
PROFILE_FUNCTIONS: Mapping[str, Mapping[str, int]] = {
    INDEPENDENT: {"prepare": 1, "draw": 3, "draw_block": 3},
    GENERATIONAL: {"init_state": 1, "ask": 3, "tell": 3},
}
OPTIONAL_HOOKS: Mapping[str, int] = {
    "validate_options": 1,
    "settings_rows": 2,
    "summary_rows": 2,
    "stop_reason": 2,
    "status": 2,
}
_ARGUMENTS = {
    "prepare": "(setup)",
    "draw": "(context, rng, plan)",
    "draw_block": "(context, rng, plan)",
    "init_state": "(setup)",
    "ask": "(state, context, rng)",
    "tell": "(state, context, results)",
    "validate_options": "(options)",
    "settings_rows": "(setup, plan)",
    "summary_rows": "(plan, stats)",
    "stop_reason": "(plan, stats)",
    "status": "(plan, stats)",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class LoadedPlugin:
    """An imported, structurally valid plug-in."""

    metadata: PluginMetadata
    options_schema: Mapping[str, Any] | None
    functions: Mapping[str, Callable[..., Any]]
    source_path: Path
    source_sha256: str
    source_bytes: bytes = field(repr=False)
    module: types.ModuleType = field(repr=False)

    @property
    def method(self) -> str:
        return self.metadata.method

    @property
    def hooks(self) -> tuple[str, ...]:
        """Names of the functions the plug-in defines, sorted."""
        return tuple(sorted(self.functions))

    def function(self, name: str) -> Callable[..., Any] | None:
        return self.functions.get(name)


def load_plugin_file(path: str | Path, *, reserved_names: Iterable[str] = ()) -> LoadedPlugin:
    """Import the plug-in at *path* and check it against the file convention."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise PluginLoadError(f"plug-in file not found: {source}", source=str(source))
    resolved = source.resolve()
    try:
        payload = resolved.read_bytes()
    except OSError as exc:
        raise PluginLoadError(f"cannot read {resolved}: {exc}", source=str(resolved)) from exc
    return load_plugin_source(payload, origin=resolved, reserved_names=reserved_names)


def load_plugin_source(
    payload: bytes, *, origin: str | Path, reserved_names: Iterable[str] = ()
) -> LoadedPlugin:
    """Import a plug-in from its source bytes; *origin* names it in tracebacks."""
    origin_path = Path(origin)
    origin_text = str(origin_path)
    digest = sha256_bytes(payload)
    module_name = (
        f"_jarvis_sampler_plugin_{sha256_bytes(origin_text.encode('utf-8'))[:12]}_{digest[:12]}"
    )
    try:
        code = compile(payload, origin_text, "exec", dont_inherit=True)
    except SyntaxError as exc:
        raise PluginLoadError(
            f"cannot compile the plug-in: {exc.msg} (line {exc.lineno})", source=origin_text
        ) from exc

    module = types.ModuleType(module_name)
    module.__file__ = origin_text
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        exec(code, module.__dict__)
        plugin = _inspect_module(
            module,
            origin=origin_path,
            digest=digest,
            payload=payload,
            reserved_names=reserved_names,
        )
    except PluginError:
        _restore_module(module_name, previous)
        raise
    except Exception as exc:
        _restore_module(module_name, previous)
        raise PluginLoadError(
            f"importing the plug-in failed: {type(exc).__name__}: {exc}", source=origin_text
        ) from exc
    except BaseException:
        _restore_module(module_name, previous)
        raise
    return plugin


def _restore_module(name: str, previous: types.ModuleType | None) -> None:
    if previous is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = previous


def _inspect_module(
    module: types.ModuleType,
    *,
    origin: Path,
    digest: str,
    payload: bytes,
    reserved_names: Iterable[str],
) -> LoadedPlugin:
    namespace = module.__dict__
    source = str(origin)
    if "PLUGIN" not in namespace:
        raise PluginLoadError("the plug-in defines no PLUGIN dict", source=source)
    try:
        metadata = parse_metadata(namespace["PLUGIN"], reserved_names=reserved_names)
    except PluginLoadError as exc:
        exc.source = exc.source or source
        raise
    method = metadata.method

    def fail(message: str) -> PluginLoadError:
        return PluginLoadError(message, method=method, source=source)

    if metadata.profile not in SUPPORTED_PROFILES:
        raise fail(
            f"profile {metadata.profile!r} is reserved for a later Jarvis-HEP-Sampler; "
            f"this version runs: {', '.join(SUPPORTED_PROFILES)}"
        )

    schema = namespace.get("OPTIONS_SCHEMA")
    if schema is not None:
        try:
            schema = check_options_schema(schema)
        except PluginLoadError as exc:
            raise fail(exc.message) from exc

    wanted = {**PROFILE_FUNCTIONS[metadata.profile], **OPTIONAL_HOOKS}
    functions: dict[str, Callable[..., Any]] = {}
    for name, arity in wanted.items():
        if name not in namespace:
            continue
        candidate = namespace[name]
        if not callable(candidate):
            raise fail(f"{name} must be a function {_ARGUMENTS[name]}")
        _check_arity(name, candidate, arity, fail)
        functions[name] = candidate

    if metadata.profile == INDEPENDENT:
        if metadata.block_size is not None:
            if "draw_block" not in functions:
                raise fail("PLUGIN['block_size'] is set, so the plug-in must define draw_block()")
        elif "draw" not in functions:
            if "draw_block" in functions:
                raise fail("draw_block() needs PLUGIN['block_size']; or define draw() instead")
            raise fail("the independent profile needs a draw(context, rng, plan) function")

    return LoadedPlugin(
        metadata=metadata,
        options_schema=schema,
        functions=functions,
        source_path=origin,
        source_sha256=digest,
        source_bytes=payload,
        module=module,
    )


def _check_arity(name: str, function: Callable[..., Any], arity: int, fail) -> None:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return
    try:
        signature.bind(*([None] * arity))
    except TypeError as exc:
        raise fail(f"{name} must accept {_ARGUMENTS[name]}: {exc}") from exc


__all__ = [
    "LoadedPlugin",
    "OPTIONAL_HOOKS",
    "PROFILE_FUNCTIONS",
    "load_plugin_file",
    "load_plugin_source",
    "sha256_bytes",
]
