from __future__ import annotations

import json
import os

import pytest

from jarvis_hep_sampler.errors import PluginLoadError, RegistryError
from jarvis_hep_sampler.registry import (
    SOURCE_CHANGED,
    SOURCE_MISSING,
    SOURCE_OK,
    SamplerRegistry,
    samplers_home,
)

from .conftest import UNIFORM


def test_home_comes_from_the_environment(_isolated_registry):
    assert samplers_home() == _isolated_registry
    assert SamplerRegistry().home == _isolated_registry


def test_absent_registry_is_empty():
    registry = SamplerRegistry()
    assert registry.entries() == {}
    assert registry.signature() is None


def test_load_snapshots_and_records(uniform_plugin):
    registry = SamplerRegistry()
    result = registry.load(uniform_plugin)
    entry = result.entry
    assert result.replaced is None and result.changed
    assert entry.snapshot == f"user_sources/Uniform-{entry.short_hash}.py"
    assert registry.snapshot_path(entry).read_bytes() == uniform_plugin.read_bytes()
    stored = json.loads(registry.store_path.read_text())
    assert stored["version"] == 1
    assert stored["entries"]["Uniform"]["plugin"]["method"] == "Uniform"
    assert registry.get("Uniform") == entry
    assert registry.problems(entry) == []
    assert registry.signature() is not None
    assert not [p for p in registry.home.rglob("*.tmp")]


def test_reload_replaces_and_deletes_the_old_snapshot(uniform_plugin):
    registry = SamplerRegistry()
    old = registry.load(uniform_plugin).entry
    uniform_plugin.write_text(UNIFORM.replace('"1.0"', '"2.0"'))
    result = registry.load(uniform_plugin)
    assert result.replaced == old and result.changed
    assert result.entry.version == "2.0"
    assert not registry.snapshot_path(old).exists()
    assert registry.snapshot_path(result.entry).exists()
    assert len(registry.entries()) == 1


def test_reloading_identical_content_is_a_no_op(uniform_plugin):
    registry = SamplerRegistry()
    first = registry.load(uniform_plugin).entry
    again = registry.load(uniform_plugin)
    assert not again.changed
    assert registry.snapshot_path(first).exists()


def test_case_only_conflict_and_reserved_names(write_plugin, uniform_plugin):
    registry = SamplerRegistry()
    registry.load(uniform_plugin)
    other = write_plugin(UNIFORM.replace('"Uniform"', '"UNIFORM"'), "upper.py")
    with pytest.raises(PluginLoadError, match="letter case"):
        registry.load(other)
    random = write_plugin(UNIFORM.replace('"Uniform"', '"Random"'), "random.py")
    with pytest.raises(PluginLoadError, match="built-in"):
        registry.load(random, reserved_names=["Random"])


def test_runs_use_the_snapshot_not_the_working_copy(uniform_plugin):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    uniform_plugin.write_text(UNIFORM.replace("rng.random", "0.5 + 0 * rng.random"))
    assert registry.source_state(entry) == SOURCE_CHANGED
    plugin = registry.load_snapshot("Uniform")
    assert plugin.source_sha256 == entry.source_sha256
    assert plugin.source_path == registry.snapshot_path(entry)
    uniform_plugin.unlink()
    assert registry.source_state(entry) == SOURCE_MISSING


def test_source_state_ok(uniform_plugin):
    registry = SamplerRegistry()
    assert registry.source_state(registry.load(uniform_plugin).entry) == SOURCE_OK


def test_broken_snapshots_are_reported(uniform_plugin):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    snapshot = registry.snapshot_path(entry)
    snapshot.write_text("# tampered\n" + snapshot.read_text())
    assert "does not match" in registry.problems(entry)[0]
    with pytest.raises(RegistryError, match="Jarvis sampler load"):
        registry.load_snapshot("Uniform")
    snapshot.unlink()
    assert "missing" in registry.problems(entry)[0]


def test_remove(uniform_plugin):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    with pytest.raises(RegistryError, match="did you mean Uniform"):
        registry.remove("uniform")
    removed = registry.remove("Uniform")
    assert removed == entry
    assert registry.entries() == {}
    assert not registry.snapshot_path(entry).exists()
    assert uniform_plugin.exists()
    with pytest.raises(RegistryError, match="no sampler"):
        registry.load_snapshot("Uniform")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not valid JSON"),
        ("[]", "not a Jarvis sampler registry"),
        ('{"version": 9, "entries": {}}', "registry version 9"),
        ('{"version": 1, "entries": {"X": {"plugin": {}}}}', "malformed"),
    ],
)
def test_corrupt_registry_is_an_error(content, message):
    registry = SamplerRegistry()
    registry.home.mkdir(parents=True)
    registry.store_path.write_text(content)
    with pytest.raises(RegistryError, match=message):
        registry.entries()


def test_load_failure_leaves_the_registry_untouched(write_plugin, uniform_plugin):
    registry = SamplerRegistry()
    registry.load(uniform_plugin)
    before = registry.store_path.read_bytes()
    with pytest.raises(PluginLoadError):
        registry.load(write_plugin("x = 1\n", "bad.py"))
    assert registry.store_path.read_bytes() == before


def test_registry_module_does_not_import_numpy_or_jsonschema():
    import subprocess
    import sys

    code = (
        "import sys, jarvis_hep_sampler.registry as r; r.SamplerRegistry().entries(); "
        "print('numpy' in sys.modules, 'jsonschema' in sys.modules)"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    output = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    ).stdout.split()
    assert output == ["False", "False"]


def test_schema_option_order_is_preserved(write_plugin):
    path = write_plugin(
        UNIFORM
        + "\nOPTIONS_SCHEMA = {'type': 'object', 'properties': "
        "{'zeta': {'type': 'number'}, 'alpha': {'type': 'number'}}}\n",
        "Ordered.py",
    )
    SamplerRegistry().load(path)
    stored = SamplerRegistry().get("Uniform").options_schema
    assert list(stored["properties"]) == ["zeta", "alpha"]
