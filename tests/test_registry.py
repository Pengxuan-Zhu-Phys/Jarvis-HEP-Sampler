from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import jarvis_hep_sampler.loader as loader_module
import jarvis_hep_sampler.registry as registry_module
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
        registry.load(random)
    assert "Random" not in registry.entries()


@pytest.mark.parametrize("legacy_name", ["Grid", "grid"])
def test_old_reserved_name_registration_can_still_be_read_and_removed(
    uniform_plugin, legacy_name
):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    stored = json.loads(registry.store_path.read_text())
    old = stored["entries"].pop("Uniform")
    old["plugin"]["method"] = legacy_name
    stored["entries"][legacy_name] = old
    registry.store_path.write_text(json.dumps(stored), encoding="utf-8")

    assert registry.get(legacy_name).method == legacy_name
    assert legacy_name in registry.entries()
    assert registry.remove(legacy_name).method == legacy_name
    assert registry.entries() == {}
    assert not registry.snapshot_path(entry).exists()
    assert uniform_plugin.exists()


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
    with pytest.raises(RegistryError, match="jsampler load"):
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
        ("[]", "not a jsampler registry"),
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


def test_snapshot_executes_the_same_bytes_that_were_verified(uniform_plugin, monkeypatch):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    snapshot = registry.snapshot_path(entry)
    read_bytes = type(snapshot).read_bytes
    reads = 0

    def change_after_read(path):
        nonlocal reads
        payload = read_bytes(path)
        if path == snapshot:
            reads += 1
            path.write_bytes(payload.replace(b'"1.0"', b'"changed"'))
        return payload

    monkeypatch.setattr(type(snapshot), "read_bytes", change_after_read)
    plugin = registry.load_snapshot("Uniform")
    assert reads == 1
    assert plugin.source_sha256 == entry.source_sha256
    assert plugin.metadata.version == "1.0"


@pytest.mark.skipif(registry_module.fcntl is None, reason="POSIX registry locking")
@pytest.mark.parametrize("change", ["reload", "remove"])
def test_snapshot_read_is_locked_but_import_can_change_registry(
    uniform_plugin, monkeypatch, change
):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    snapshot = registry.snapshot_path(entry)
    read_snapshot = registry._read_snapshot
    execute = loader_module.load_plugin_source
    fcntl = registry_module.fcntl

    def locked_read(current):
        with open(registry.lock_path, "a+") as probe:
            with pytest.raises(BlockingIOError):
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return read_snapshot(current)

    def change_before_import(payload, *, origin, reserved_names=()):
        if origin == snapshot:
            with open(registry.lock_path, "a+") as probe:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if change == "reload":
                uniform_plugin.write_text(UNIFORM.replace('"1.0"', '"2.0"'))
                registry.load(uniform_plugin)
            else:
                registry.remove("Uniform")
        return execute(payload, origin=origin, reserved_names=reserved_names)

    monkeypatch.setattr(registry, "_read_snapshot", locked_read)
    monkeypatch.setattr(loader_module, "load_plugin_source", change_before_import)
    plugin = registry.load_snapshot("Uniform")
    assert not snapshot.exists()
    assert plugin.source_sha256 == entry.source_sha256
    assert plugin.metadata.version == "1.0"
    assert uniform_plugin.exists()
    current = registry.get("Uniform")
    assert (current.version if current else None) == ("2.0" if change == "reload" else None)


@pytest.mark.skipif(registry_module.fcntl is None, reason="POSIX registry locking")
def test_concurrent_case_only_registrations_cannot_both_succeed(write_plugin):
    first = write_plugin(UNIFORM, "first.py")
    second = write_plugin(UNIFORM.replace('"Uniform"', '"UNIFORM"'), "second.py")
    registry = SamplerRegistry()

    def load(path):
        try:
            return registry.load(path)
        except PluginLoadError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(load, (first, second)))
    assert sum(isinstance(result, PluginLoadError) for result in results) == 1
    assert len(registry.entries()) == 1


@pytest.mark.parametrize(
    "snapshot",
    [None, "../source.py", "user_sources/../source.py", "elsewhere/Uniform-123456789abc.py",
     "user_sources/source.py"],
)
def test_malformed_snapshot_paths_do_not_change_files(uniform_plugin, snapshot):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    raw = json.loads(registry.store_path.read_text())
    raw["entries"]["Uniform"]["snapshot"] = snapshot
    registry.store_path.write_text(json.dumps(raw))
    before = registry.store_path.read_bytes()
    source_before = uniform_plugin.read_bytes()
    for action in (registry.entries, lambda: registry.remove("Uniform"),
                   lambda: registry.load(uniform_plugin)):
        with pytest.raises(RegistryError, match="snapshot"):
            action()
    assert registry.store_path.read_bytes() == before
    assert uniform_plugin.read_bytes() == source_before
    assert registry.snapshot_path(entry).read_bytes() == source_before


def test_absolute_snapshot_cannot_delete_the_working_source(uniform_plugin):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    invalid = replace(entry, snapshot=str(uniform_plugin))
    with pytest.raises(RegistryError, match="snapshot"):
        registry.snapshot_path(invalid)
    assert "snapshot" in registry.problems(invalid)[0]
    raw = json.loads(registry.store_path.read_text())
    raw["entries"]["Uniform"]["snapshot"] = str(uniform_plugin)
    registry.store_path.write_text(json.dumps(raw))
    with pytest.raises(RegistryError, match="snapshot"):
        registry.remove("Uniform")
    assert uniform_plugin.exists()


@pytest.mark.parametrize("directory_link", [False, True])
def test_symlink_snapshots_are_rejected_without_touching_target(
    uniform_plugin, tmp_path, directory_link
):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    snapshot = registry.snapshot_path(entry)
    if directory_link:
        target = tmp_path / "external-snapshots"
        registry.snapshot_dir.rename(target)
        registry.snapshot_dir.symlink_to(target, target_is_directory=True)
        sentinel = target / snapshot.name
    else:
        sentinel = tmp_path / "sentinel.py"
        sentinel.write_bytes(snapshot.read_bytes())
        snapshot.unlink()
        snapshot.symlink_to(sentinel)
    before = sentinel.read_bytes()
    for action in (registry.entries, lambda: registry.load_snapshot("Uniform"),
                   lambda: registry.remove("Uniform"), lambda: registry.load(uniform_plugin)):
        with pytest.raises(RegistryError, match="symbolic links|symbolic link"):
            action()
    assert sentinel.read_bytes() == before
    assert uniform_plugin.exists()


def test_non_utf8_registry_is_a_registry_error():
    registry = SamplerRegistry()
    registry.home.mkdir(parents=True)
    registry.store_path.write_bytes(b"\xff")
    with pytest.raises(RegistryError, match="cannot read") as info:
        registry.entries()
    assert isinstance(info.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize("failure", ["snapshot", "store"])
def test_precommit_write_failure_preserves_previous_registration(
    uniform_plugin, monkeypatch, failure
):
    registry = SamplerRegistry()
    old = registry.load(uniform_plugin).entry
    before = registry.store_path.read_bytes()
    uniform_plugin.write_text(UNIFORM.replace('"1.0"', '"2.0"'))
    write = registry_module._atomic_write_bytes

    def fail_write(path, payload):
        if (path == registry.store_path) == (failure == "store"):
            raise PermissionError("injected precommit write failure")
        return write(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr(registry_module, "_atomic_write_bytes", fail_write)
        with pytest.raises(RegistryError, match="injected precommit") as info:
            registry.load(uniform_plugin)
    assert isinstance(info.value.__cause__, PermissionError)
    assert registry.store_path.read_bytes() == before
    assert registry.load_snapshot("Uniform").source_sha256 == old.source_sha256
    abandoned = set(registry.snapshot_dir.iterdir()) - {registry.snapshot_path(old)}
    assert len(abandoned) == (1 if failure == "store" else 0)
    uniform_plugin.write_text(UNIFORM.replace('"1.0"', '"3.0"'))
    current = registry.load(uniform_plugin).entry
    assert set(registry.snapshot_dir.iterdir()) == abandoned | {registry.snapshot_path(current)}


@pytest.mark.parametrize("operation", ["load", "remove"])
def test_postcommit_cleanup_failure_warns_and_retries(
    uniform_plugin, monkeypatch, caplog, operation
):
    registry = SamplerRegistry()
    old = registry.load(uniform_plugin).entry
    old_path = registry.snapshot_path(old)
    uniform_plugin.write_text(UNIFORM.replace('"1.0"', '"2.0"'))
    delete = registry._delete_snapshot

    def fail_delete(snapshot, entries):
        if snapshot == old.snapshot:
            raise PermissionError("injected cleanup failure")
        return delete(snapshot, entries)

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_delete_snapshot", fail_delete)
        result = (
            registry.load(uniform_plugin) if operation == "load" else registry.remove("Uniform")
        )
    assert (result.entry.version if operation == "load" else result.version) == (
        "2.0" if operation == "load" else "1.0"
    )
    assert (registry.get("Uniform") is None) == (operation == "remove")
    assert old_path.exists()
    assert "already committed" in caplog.text
    assert "retried on the next successful sampler load/remove" in caplog.text
    pending_path = registry.home / ".pending_cleanup.json"
    assert json.loads(pending_path.read_text()) == {old.snapshot: old.source_sha256}
    registry.load(uniform_plugin)
    assert not old_path.exists()
    assert not pending_path.exists()
    assert uniform_plugin.exists()


def test_cleanup_preserves_untracked_files_and_symlinks(uniform_plugin, tmp_path):
    registry = SamplerRegistry()
    registry.load(uniform_plugin)
    helper = registry.snapshot_dir / "helper.py"
    helper.write_text("# user helper\n")
    mismatched = registry.snapshot_dir / "UserFile-000000000000.py"
    mismatched.write_text("# user file with a snapshot-shaped name\n")
    sentinel = tmp_path / "sentinel.py"
    payload = b"# old managed snapshot\n"
    sentinel.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()[:12]
    linked = registry.snapshot_dir / f"Linked-{digest}.py"
    linked.symlink_to(sentinel)
    directory = registry.snapshot_dir / "Directory-000000000000.py"
    directory.mkdir()
    orphan = registry.snapshot_dir / f"OldSnapshot-{digest}.py"
    orphan.write_bytes(payload)
    registry.load(uniform_plugin)
    assert orphan.exists()
    assert helper.exists() and mismatched.exists() and directory.is_dir()
    assert linked.is_symlink()
    assert sentinel.read_bytes() == payload


def test_remove_preserves_a_working_source_in_the_snapshot_directory(
    uniform_plugin, write_plugin
):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    source = registry.snapshot_path(entry)
    registry.load(source)
    assert registry.get("Uniform").source_path == str(source.resolve())
    registry.remove("Uniform")
    other = write_plugin(UNIFORM.replace('"Uniform"', '"Other"'), "other.py")
    registry.load(other)
    assert source.read_bytes() == uniform_plugin.read_bytes()


def test_pending_cleanup_preserves_changed_snapshots(uniform_plugin, monkeypatch, caplog):
    registry = SamplerRegistry()
    old = registry.load(uniform_plugin).entry
    old_path = registry.snapshot_path(old)

    def cannot_delete(*_):
        raise PermissionError("injected cleanup failure")

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_delete_snapshot", cannot_delete)
        registry.remove("Uniform")
    old_path.write_text("# user replaced this file\n")
    uniform_plugin.write_text(UNIFORM.replace('"1.0"', '"2.0"'))
    registry.load(uniform_plugin)
    assert old_path.read_text() == "# user replaced this file\n"
    assert "retained without cleanup" in caplog.text
    assert not (registry.home / ".pending_cleanup.json").exists()


@pytest.mark.parametrize("pending", ['{broken', '{"../source.py": "bad"}'])
def test_invalid_pending_cleanup_warns_without_deleting_files(
    uniform_plugin, pending, caplog
):
    registry = SamplerRegistry()
    registry.load(uniform_plugin)
    pending_path = registry.home / ".pending_cleanup.json"
    pending_path.write_text(pending)
    result = registry.remove("Uniform")
    assert result.method == "Uniform"
    assert uniform_plugin.exists()
    assert pending_path.read_text() == pending
    assert "Previously retained files are untouched" in caplog.text


def test_pending_cleanup_write_failure_does_not_fail_a_committed_remove(
    uniform_plugin, monkeypatch, caplog
):
    registry = SamplerRegistry()
    entry = registry.load(uniform_plugin).entry
    write = registry_module._atomic_write_bytes

    def cannot_delete(*_):
        raise PermissionError("injected snapshot cleanup failure")

    def cannot_record(path, payload):
        if path.name == ".pending_cleanup.json":
            raise PermissionError("injected cleanup journal failure")
        return write(path, payload)

    monkeypatch.setattr(registry, "_delete_snapshot", cannot_delete)
    monkeypatch.setattr(registry_module, "_atomic_write_bytes", cannot_record)
    assert registry.remove("Uniform") == entry
    assert registry.get("Uniform") is None
    assert registry.snapshot_path(entry).exists()
    assert uniform_plugin.exists()
    assert "cannot record pending cleanup" in caplog.text
    assert "may require manual cleanup" in caplog.text
