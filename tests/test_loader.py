from __future__ import annotations

import hashlib
import sys

import pytest

from jarvis_hep_sampler.errors import PluginLoadError
from jarvis_hep_sampler.loader import load_plugin_file, load_plugin_source

HEADER = """
PLUGIN = {"api_version": 1, "method": "%s", "version": "1", "profile": "independent"%s}
"""


def source(body: str, method: str = "Demo", extra: str = "") -> str:
    return HEADER % (method, extra) + body


DRAW = "\ndef draw(context, rng, plan):\n    return rng.random(context.dimension)\n"


def test_loads_and_records_hash(write_plugin):
    path = write_plugin(source(DRAW))
    plugin = load_plugin_file(path)
    assert plugin.method == "Demo"
    assert plugin.hooks == ("draw",)
    assert plugin.options_schema is None
    assert plugin.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert plugin.source_path == path.resolve()


def test_does_not_touch_sys_path(write_plugin):
    before = list(sys.path)
    load_plugin_file(write_plugin(source(DRAW)))
    assert sys.path == before


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("x = 1\n", "no PLUGIN"),
        (source(""), "needs a draw"),
        (
            source("\ndef draw(context, rng):\n    pass\n"),
            r"draw must accept \(context, rng, plan\)",
        ),
        (source("\ndraw = 3\n"), "must be a function"),
        (source(DRAW + "\nOPTIONS_SCHEMA = {'type': 'nope'}\n"), "not a valid JSON Schema"),
        (source(DRAW + "\nOPTIONS_SCHEMA = 'x'\n"), "dict or None"),
        (
            source("\ndef draw_block(context, rng, plan):\n    pass\n"),
            "needs PLUGIN\\['block_size'\\]",
        ),
        (source(DRAW, extra=', "block_size": 4'), "must define draw_block"),
        (source(DRAW + "\ndef status(plan):\n    return {}\n"), "status must accept"),
        ("def broken(:\n", "cannot compile"),
        ("raise RuntimeError('boom')\n", "RuntimeError: boom"),
    ],
)
def test_structural_errors(write_plugin, text, message):
    with pytest.raises(PluginLoadError, match=message):
        load_plugin_file(write_plugin(text))


def test_generational_profile_is_recognised_but_not_runnable_yet(write_plugin):
    text = """
PLUGIN = {"api_version": 1, "method": "Chain", "version": "1",
          "profile": "generational", "state_version": 1}
"""
    with pytest.raises(PluginLoadError, match="reserved for a later"):
        load_plugin_file(write_plugin(text))


def test_reserved_names(write_plugin):
    with pytest.raises(PluginLoadError, match="built-in"):
        load_plugin_file(write_plugin(source(DRAW, method="Random")))
    with pytest.raises(PluginLoadError, match="built-in"):
        load_plugin_file(write_plugin(source(DRAW, method="Grid")), reserved_names=[])


def test_trusted_builtin_loader_allows_only_the_exact_expected_name(write_plugin):
    path = write_plugin(source(DRAW, method="LatinHypercube"))
    with pytest.raises(PluginLoadError, match="built-in"):
        load_plugin_file(path)
    loaded = load_plugin_file(path, trusted_builtin_method="LatinHypercube")
    assert loaded.method == "LatinHypercube"
    assert load_plugin_source(
        path.read_bytes(), origin=path, trusted_builtin_method="LatinHypercube"
    ).method == "LatinHypercube"
    with pytest.raises(PluginLoadError, match="built-in"):
        load_plugin_file(path, trusted_builtin_method="Grid")
    other = write_plugin(source(DRAW, method="Grid"), "Grid.py")
    with pytest.raises(PluginLoadError, match="built-in"):
        load_plugin_file(other, trusted_builtin_method="LatinHypercube")


def test_import_error_keeps_the_cause_and_cleans_sys_modules(write_plugin):
    path = write_plugin("import not_a_real_module_xyz\n")
    before = set(sys.modules)
    with pytest.raises(PluginLoadError, match="ModuleNotFoundError") as info:
        load_plugin_file(path)
    assert isinstance(info.value.__cause__, ModuleNotFoundError)
    assert info.value.source == str(path.resolve())
    assert not {name for name in set(sys.modules) - before if name.startswith("_jarvis_sampler")}


def test_same_basename_in_two_directories(write_plugin, tmp_path):
    first = write_plugin(source(DRAW + "\nVALUE = 1\n"), "p.py", tmp_path / "a")
    second = write_plugin(source(DRAW + "\nVALUE = 2\n"), "p.py", tmp_path / "b")
    one, two = load_plugin_file(first), load_plugin_file(second)
    assert one.module.VALUE == 1 and two.module.VALUE == 2
    assert one.module.__name__ != two.module.__name__


def test_missing_file(tmp_path):
    with pytest.raises(PluginLoadError, match="not found"):
        load_plugin_file(tmp_path / "nope.py")


def test_plugin_defined_dataclass_works(write_plugin):
    text = source(
        DRAW
        + "\nfrom dataclasses import dataclass\n\n@dataclass\nclass Plan:\n    upper: float = 1.0\n"
    )
    plugin = load_plugin_file(write_plugin(text))
    assert plugin.module.Plan().upper == 1.0
