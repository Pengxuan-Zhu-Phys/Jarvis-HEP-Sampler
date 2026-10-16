"""Jarvis-HEP-Sampler: the plug-in SDK for user-defined Jarvis-HEP samplers.

A plug-in is one ``.py`` file with a ``PLUGIN`` dict, an optional
``OPTIONS_SCHEMA`` and a few functions (``prepare`` / ``draw`` / hooks).
Users create it with ``jsampler init``, load it once, and then write
``Sampling.Method: <Name>`` like any built-in method. ``jsampler`` only sees
samplers in this package's registry.

This package owns the plug-in format: metadata rules, loading, the user
registry, random streams, output checks, the logging facade and the offline
test kit. Jarvis-HEP owns the runtime. Names are imported lazily so reading
the registry stays light.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from jarvis_hep_sampler._version import __version__

_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    # metadata
    "API_VERSION": ("jarvis_hep_sampler.metadata", "API_VERSION"),
    "PluginMetadata": ("jarvis_hep_sampler.metadata", "PluginMetadata"),
    "RESERVED_METHOD_NAMES": ("jarvis_hep_sampler.metadata", "RESERVED_METHOD_NAMES"),
    "check_method_name": ("jarvis_hep_sampler.metadata", "check_method_name"),
    # contexts and logging
    "BlockContext": ("jarvis_hep_sampler.contexts", "BlockContext"),
    "DrawContext": ("jarvis_hep_sampler.contexts", "DrawContext"),
    "SamplerStats": ("jarvis_hep_sampler.contexts", "SamplerStats"),
    "SetupContext": ("jarvis_hep_sampler.contexts", "SetupContext"),
    "LogBackend": ("jarvis_hep_sampler.log", "LogBackend"),
    "SamplerLog": ("jarvis_hep_sampler.log", "SamplerLog"),
    # errors
    "PluginConfigError": ("jarvis_hep_sampler.errors", "PluginConfigError"),
    "PluginError": ("jarvis_hep_sampler.errors", "PluginError"),
    "PluginLoadError": ("jarvis_hep_sampler.errors", "PluginLoadError"),
    "PluginOutputError": ("jarvis_hep_sampler.errors", "PluginOutputError"),
    "PluginResumeMismatch": ("jarvis_hep_sampler.errors", "PluginResumeMismatch"),
    "RegistryError": ("jarvis_hep_sampler.errors", "RegistryError"),
    # streams
    "STREAM_PROTOCOL": ("jarvis_hep_sampler.streams", "STREAM_PROTOCOL"),
    # options
    "OptionIssue": ("jarvis_hep_sampler.options", "OptionIssue"),
    "ReservedSettings": ("jarvis_hep_sampler.options", "ReservedSettings"),
    "parse_reserved": ("jarvis_hep_sampler.options", "parse_reserved"),
    "schema_issues": ("jarvis_hep_sampler.options", "schema_issues"),
    "split_bounds": ("jarvis_hep_sampler.options", "split_bounds"),
    # loading and running
    "LoadedPlugin": ("jarvis_hep_sampler.loader", "LoadedPlugin"),
    "load_plugin_file": ("jarvis_hep_sampler.loader", "load_plugin_file"),
    "load_plugin_source": ("jarvis_hep_sampler.loader", "load_plugin_source"),
    "IndependentSession": ("jarvis_hep_sampler.session", "IndependentSession"),
    # registry and template
    "LoadResult": ("jarvis_hep_sampler.registry", "LoadResult"),
    "RegistryEntry": ("jarvis_hep_sampler.registry", "RegistryEntry"),
    "SamplerRegistry": ("jarvis_hep_sampler.registry", "SamplerRegistry"),
    "samplers_home": ("jarvis_hep_sampler.registry", "samplers_home"),
    "render_template": ("jarvis_hep_sampler.template", "render_template"),
    "write_template": ("jarvis_hep_sampler.template", "write_template"),
}

# Kept literal so linters and IDEs see the exports; a test pins it to _LAZY_ATTRS.
__all__ = [
    "API_VERSION",
    "BlockContext",
    "DrawContext",
    "IndependentSession",
    "LoadResult",
    "LoadedPlugin",
    "LogBackend",
    "OptionIssue",
    "PluginConfigError",
    "PluginError",
    "PluginLoadError",
    "PluginMetadata",
    "PluginOutputError",
    "PluginResumeMismatch",
    "RegistryEntry",
    "RegistryError",
    "RESERVED_METHOD_NAMES",
    "ReservedSettings",
    "STREAM_PROTOCOL",
    "SamplerLog",
    "SamplerRegistry",
    "SamplerStats",
    "SetupContext",
    "__version__",
    "check_method_name",
    "load_plugin_file",
    "load_plugin_source",
    "parse_reserved",
    "render_template",
    "samplers_home",
    "schema_issues",
    "split_bounds",
    "write_template",
]

if TYPE_CHECKING:
    from jarvis_hep_sampler.contexts import BlockContext, DrawContext, SamplerStats, SetupContext
    from jarvis_hep_sampler.errors import (
        PluginConfigError,
        PluginError,
        PluginLoadError,
        PluginOutputError,
        PluginResumeMismatch,
        RegistryError,
    )
    from jarvis_hep_sampler.loader import LoadedPlugin, load_plugin_file, load_plugin_source
    from jarvis_hep_sampler.log import LogBackend, SamplerLog
    from jarvis_hep_sampler.metadata import (
        API_VERSION,
        RESERVED_METHOD_NAMES,
        PluginMetadata,
        check_method_name,
    )
    from jarvis_hep_sampler.options import (
        OptionIssue,
        ReservedSettings,
        parse_reserved,
        schema_issues,
        split_bounds,
    )
    from jarvis_hep_sampler.registry import (
        LoadResult,
        RegistryEntry,
        SamplerRegistry,
        samplers_home,
    )
    from jarvis_hep_sampler.session import IndependentSession
    from jarvis_hep_sampler.streams import STREAM_PROTOCOL
    from jarvis_hep_sampler.template import render_template, write_template


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | set(globals()))
