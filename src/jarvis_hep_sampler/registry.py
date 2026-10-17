"""The user sampler registry under ``~/.jarvis/samplers`` (technical design §5.2).

``jsampler load`` snapshots a plug-in file into ``user_sources/`` and
records it in ``sources.json``, so every new terminal sees it without another
load. Loading the same method again replaces the entry and deletes the old
snapshot. Runs use the snapshot, never the user's working copy.

This module imports neither NumPy nor jsonschema: Jarvis-HEP reads the
registry while validating task cards, which must stay light and must not
execute plug-in code.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis_hep_sampler._version import __version__
from jarvis_hep_sampler.errors import PluginLoadError, RegistryError

if TYPE_CHECKING:
    from jarvis_hep_sampler.loader import LoadedPlugin

try:  # POSIX file locks; Jarvis-HEP runs on Linux and macOS.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

ENV_HOME = "JARVIS_SAMPLERS_HOME"
REGISTRY_VERSION = 1
STORE_NAME = "sources.json"
SNAPSHOT_DIR = "user_sources"
LOCK_NAME = ".lock"

SOURCE_OK = "ok"
SOURCE_CHANGED = "source changed since load"
SOURCE_MISSING = "source missing"

_LOGGER = logging.getLogger(__name__)
_SNAPSHOT_NAME_RE = re.compile(r"[A-Z][A-Za-z0-9]{1,63}-[0-9a-f]{12}\.py")
_PENDING_CLEANUP = ".pending_cleanup.json"


def _snapshot_relative_path(snapshot: object) -> Path:
    if not isinstance(snapshot, str):
        raise ValueError("snapshot must be a relative path under user_sources")
    relative = Path(snapshot)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 2
        or relative.parts[0] != SNAPSHOT_DIR
        or not _SNAPSHOT_NAME_RE.fullmatch(relative.name)
    ):
        raise ValueError("snapshot must be user_sources/<Method>-<hash>.py")
    return relative


def samplers_home() -> Path:
    """``$JARVIS_SAMPLERS_HOME``, else ``~/.jarvis/samplers``."""
    override = os.environ.get(ENV_HOME, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".jarvis" / "samplers"


@dataclass(frozen=True)
class RegistryEntry:
    """One loaded sampler, as recorded in ``sources.json``."""

    method: str
    source_path: str
    snapshot: str
    source_sha256: str
    loaded_at: str
    sdk_version: str
    plugin: Mapping[str, Any]
    options_schema: Mapping[str, Any] | None
    hooks: tuple[str, ...]

    @property
    def version(self) -> str:
        return str(self.plugin.get("version", ""))

    @property
    def profile(self) -> str:
        return str(self.plugin.get("profile", ""))

    @property
    def description(self) -> str:
        return str(self.plugin.get("description", ""))

    @property
    def statistical(self) -> bool:
        return bool(self.plugin.get("statistical", False))

    @property
    def short_hash(self) -> str:
        return self.source_sha256[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "snapshot": self.snapshot,
            "source_sha256": self.source_sha256,
            "loaded_at": self.loaded_at,
            "sdk_version": self.sdk_version,
            "plugin": dict(self.plugin),
            "options_schema": None if self.options_schema is None else dict(self.options_schema),
            "hooks": list(self.hooks),
        }

    @classmethod
    def from_dict(cls, method: str, raw: object) -> RegistryEntry:
        if not isinstance(raw, Mapping):
            raise RegistryError(f"registry entry {method!r} is not an object", method=method)
        try:
            plugin = raw["plugin"]
            schema = raw.get("options_schema")
            if not isinstance(plugin, Mapping) or plugin.get("method") != method:
                raise ValueError("plugin metadata does not match the entry name")
            if schema is not None and not isinstance(schema, Mapping):
                raise ValueError("options_schema must be an object or null")
            snapshot = raw["snapshot"]
            _snapshot_relative_path(snapshot)
            return cls(
                method=method,
                source_path=str(raw["source_path"]),
                snapshot=snapshot,
                source_sha256=str(raw["source_sha256"]),
                loaded_at=str(raw.get("loaded_at", "")),
                sdk_version=str(raw.get("sdk_version", "")),
                plugin=dict(plugin),
                options_schema=None if schema is None else dict(schema),
                hooks=tuple(str(item) for item in raw.get("hooks", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryError(
                f"registry entry {method!r} is malformed: {exc}", method=method
            ) from exc


@dataclass(frozen=True)
class LoadResult:
    """Outcome of :meth:`SamplerRegistry.load`."""

    entry: RegistryEntry
    replaced: RegistryEntry | None

    @property
    def changed(self) -> bool:
        return self.replaced is None or self.replaced.source_sha256 != self.entry.source_sha256


class SamplerRegistry:
    """Read and change the registry in one directory (default :func:`samplers_home`)."""

    def __init__(self, home: str | Path | None = None) -> None:
        self.home = Path(home).expanduser() if home is not None else samplers_home()

    @property
    def store_path(self) -> Path:
        return self.home / STORE_NAME

    @property
    def snapshot_dir(self) -> Path:
        return self.home / SNAPSHOT_DIR

    @property
    def lock_path(self) -> Path:
        return self.home / LOCK_NAME

    # ------------------------------------------------------------------ read
    def signature(self) -> tuple[int, int] | None:
        """``(mtime_ns, size)`` of ``sources.json`` for cheap cache checks; None if absent."""
        try:
            stat = self.store_path.stat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RegistryError(f"cannot inspect {self.store_path}: {exc}") from exc
        return (stat.st_mtime_ns, stat.st_size)

    def entries(self) -> dict[str, RegistryEntry]:
        """All loaded samplers by method name. An absent registry is empty."""
        store = self._read_store()
        return {
            method: RegistryEntry.from_dict(method, raw)
            for method, raw in sorted(store["entries"].items())
        }

    def get(self, method: str) -> RegistryEntry | None:
        return self.entries().get(str(method))

    def snapshot_path(self, entry: RegistryEntry) -> Path:
        return self._managed_snapshot_path(entry.snapshot)

    def _managed_snapshot_path(self, snapshot: str) -> Path:
        try:
            relative = _snapshot_relative_path(snapshot)
            path = self.home / relative
            managed = self.home.resolve() / SNAPSHOT_DIR
            if self.snapshot_dir.is_symlink() or path.is_symlink():
                raise ValueError("managed snapshots cannot be symbolic links")
            if not path.resolve().is_relative_to(managed):
                raise ValueError("snapshot resolves outside the managed user_sources directory")
        except (OSError, RuntimeError, ValueError) as exc:
            raise RegistryError(f"invalid snapshot {snapshot!r}: {exc}") from exc
        return path

    def problems(self, entry: RegistryEntry) -> list[str]:
        """Reasons the snapshot of *entry* cannot be used (empty when it is fine)."""
        try:
            self._read_snapshot(entry)
        except RegistryError as exc:
            return [exc.message]
        return []

    def _read_snapshot(self, entry: RegistryEntry) -> tuple[Path, bytes]:
        path = self.snapshot_path(entry)
        try:
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise RegistryError(f"snapshot {path} is missing", method=entry.method) from exc
        except OSError as exc:
            raise RegistryError(
                f"snapshot {path} cannot be read: {exc}", method=entry.method
            ) from exc
        if hashlib.sha256(payload).hexdigest() != entry.source_sha256:
            raise RegistryError(
                f"snapshot {path} does not match the recorded SHA-256", method=entry.method
            )
        return path, payload

    def source_state(self, entry: RegistryEntry) -> str:
        """Compare the user's working copy with what was loaded."""
        try:
            payload = Path(entry.source_path).read_bytes()
        except OSError:
            return SOURCE_MISSING
        if hashlib.sha256(payload).hexdigest() != entry.source_sha256:
            return SOURCE_CHANGED
        return SOURCE_OK

    def load_snapshot(self, method: str) -> LoadedPlugin:
        """Import the loaded snapshot of *method* (what a run uses)."""
        from jarvis_hep_sampler.loader import load_plugin_source

        with self._locked(shared=True):
            entry = self.get(method)
            if entry is None:
                raise RegistryError(
                    f"no sampler named {method!r} is loaded; run: jsampler load <file>",
                    method=str(method),
                )
            try:
                path, payload = self._read_snapshot(entry)
            except RegistryError as exc:
                raise RegistryError(
                    f"{exc.message}; run: jsampler load {entry.source_path}",
                    method=entry.method,
                ) from exc
        # User imports may take arbitrary time or use the registry themselves.
        # Keep them outside the lock and execute exactly the bytes just verified.
        plugin = load_plugin_source(payload, origin=path)
        if plugin.method != entry.method:
            raise RegistryError(
                f"snapshot {path} declares method {plugin.method!r}, not {entry.method!r}",
                method=entry.method,
            )
        return plugin

    # ---------------------------------------------------------------- change
    def load(self, path: str | Path, *, reserved_names: Iterable[str] = ()) -> LoadResult:
        """Import *path*, check it, snapshot it and record it (replacing the same method)."""
        from jarvis_hep_sampler.loader import load_plugin_file
        from jarvis_hep_sampler.metadata import check_external_method_name

        plugin = load_plugin_file(
            path, metadata_validator=lambda meta: check_external_method_name(
                meta.method, reserved_names=reserved_names,
            ),
        )
        method = plugin.method
        entry = RegistryEntry(
            method=method,
            source_path=str(plugin.source_path),
            snapshot=f"{SNAPSHOT_DIR}/{method}-{plugin.source_sha256[:12]}.py",
            source_sha256=plugin.source_sha256,
            loaded_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            sdk_version=__version__,
            plugin=plugin.metadata.to_dict(),
            options_schema=plugin.options_schema,
            hooks=plugin.hooks,
        )
        with self._locked():
            store = self._read_store()
            entries: dict[str, Any] = store["entries"]
            for other in entries:
                if other != method and other.casefold() == method.casefold():
                    raise PluginLoadError(
                        f"{method} differs only in letter case from the loaded sampler {other}; "
                        f"run: jsampler remove {other}",
                        method=method,
                    )
            replaced = (
                RegistryEntry.from_dict(method, entries[method]) if method in entries else None
            )
            _atomic_write_bytes(self.snapshot_path(entry), plugin.source_bytes)
            entries[method] = entry.to_dict()
            self._write_store(store)
            retired = () if replaced is None else (replaced,)
            self._cleanup_snapshots(entries, retired=retired)
        return LoadResult(entry=entry, replaced=replaced)

    def remove(self, method: str) -> RegistryEntry:
        """Forget *method* and delete its snapshot. The user's source file is kept."""
        with self._locked():
            store = self._read_store()
            entries: dict[str, Any] = store["entries"]
            if method not in entries:
                hint = [name for name in entries if name.casefold() == str(method).casefold()]
                suffix = f"; did you mean {hint[0]}?" if hint else ""
                raise RegistryError(f"no sampler named {method!r} is loaded{suffix}", method=method)
            removed = RegistryEntry.from_dict(method, entries.pop(method))
            self._write_store(store)
            self._cleanup_snapshots(entries, retired=(removed,))
        return removed

    # -------------------------------------------------------------- internals
    @contextlib.contextmanager
    def _locked(self, *, shared: bool = False) -> Iterator[None]:
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            with open(self.lock_path, "a+", encoding="utf-8") as handle:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise RegistryError(f"cannot access sampler registry {self.home}: {exc}") from exc

    def _read_store(self) -> dict[str, Any]:
        try:
            text = self.store_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"version": REGISTRY_VERSION, "entries": {}}
        except (OSError, UnicodeError) as exc:
            raise RegistryError(f"cannot read {self.store_path}: {exc}") from exc
        try:
            store = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RegistryError(
                f"{self.store_path} is not valid JSON ({exc}); fix it or delete it and load "
                "the samplers again"
            ) from exc
        if not isinstance(store, dict) or not isinstance(store.get("entries"), dict):
            raise RegistryError(f"{self.store_path} is not a jsampler registry")
        version = store.get("version")
        if version != REGISTRY_VERSION:
            raise RegistryError(
                f"{self.store_path} has registry version {version!r}; this Jarvis-HEP-Sampler "
                f"reads version {REGISTRY_VERSION}"
            )
        for method, raw in store["entries"].items():
            self.snapshot_path(RegistryEntry.from_dict(method, raw))
        return store

    def _write_store(self, store: Mapping[str, Any]) -> None:
        # Entries are sorted by method name; everything inside an entry keeps its
        # order, so an OPTIONS_SCHEMA lists its options as the author wrote them.
        ordered = {
            "version": store["version"],
            "entries": dict(sorted(store["entries"].items())),
        }
        text = json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"
        _atomic_write_bytes(self.store_path, text.encode("utf-8"))

    def _delete_snapshot(self, snapshot: str, entries: Mapping[str, Any]) -> None:
        path = self._managed_snapshot_path(snapshot)
        still_used = any(
            isinstance(raw, Mapping) and raw.get("snapshot") == snapshot for raw in entries.values()
        )
        if not still_used:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()

    def _cleanup_snapshots(
        self, entries: Mapping[str, Any], *, retired: Iterable[RegistryEntry] = ()
    ) -> None:
        # Only retry explicitly retired snapshots. A filename or matching source
        # hash alone does not establish ownership of arbitrary files in this folder.
        retired = tuple(retired)
        pending, can_save = self._read_pending_cleanup()
        pending.update({entry.snapshot: entry.source_sha256 for entry in retired})
        active = {raw["snapshot"] for raw in entries.values()}
        sources = [str(raw["source_path"]) for raw in entries.values()]
        sources.extend(entry.source_path for entry in retired)
        protected = set()
        for source in sources:
            try:
                protected.add(Path(source).resolve())
            except (OSError, RuntimeError, ValueError):
                # An invalid filesystem path cannot refer to a deletable source.
                continue
        for snapshot, expected in list(pending.items()):
            path = self.home / snapshot
            try:
                path = self._managed_snapshot_path(snapshot)
                if snapshot in active or path.resolve() in protected:
                    pending.pop(snapshot)
                    continue
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    _LOGGER.warning(
                        "Sampler registry change is already committed; snapshot %s has changed "
                        "and is retained without cleanup.", path
                    )
                    pending.pop(snapshot)
                    continue
                self._delete_snapshot(snapshot, entries)
                pending.pop(snapshot)
            except FileNotFoundError:
                pending.pop(snapshot)
            except (OSError, RegistryError) as exc:
                self._cleanup_warning(path, exc)
        if can_save:
            self._write_pending_cleanup(pending)
        elif pending:
            _LOGGER.warning(
                "Sampler registry change is already committed; pending cleanup could not be "
                "recorded. Retained snapshots: %s", ", ".join(sorted(pending))
            )

    def _read_pending_cleanup(self) -> tuple[dict[str, str], bool]:
        path = self.home / _PENDING_CLEANUP
        try:
            pending = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(pending, dict):
                raise ValueError("expected a snapshot-to-SHA-256 object")
            for snapshot, digest in pending.items():
                _snapshot_relative_path(snapshot)
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("invalid snapshot SHA-256")
        except FileNotFoundError:
            return {}, True
        except (OSError, UnicodeError, ValueError) as exc:
            _LOGGER.warning(
                "Sampler registry change is already committed; cannot read pending cleanup "
                "%s: %s. Previously retained files are untouched; repair this file to retry.",
                path, exc
            )
            return {}, False
        return pending, True

    def _write_pending_cleanup(self, pending: Mapping[str, str]) -> None:
        path = self.home / _PENDING_CLEANUP
        try:
            if pending:
                payload = (json.dumps(dict(pending), indent=2) + "\n").encode("utf-8")
                _atomic_write_bytes(path, payload)
            else:
                with contextlib.suppress(FileNotFoundError):
                    path.unlink()
        except OSError as exc:
            _LOGGER.warning(
                "Sampler registry change is already committed; cannot record pending cleanup "
                "at %s: %s. Retained snapshots may require manual cleanup: %s",
                path, exc, ", ".join(sorted(pending)) or "see previous cleanup warnings"
            )

    @staticmethod
    def _cleanup_warning(path: Path, exc: Exception) -> None:
        _LOGGER.warning(
            "Sampler registry change is already committed; cannot clean up %s: %s. "
            "Cleanup will be retried on the next successful sampler load/remove.",
            path,
            exc,
        )


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(handle.name)
        raise


__all__ = [
    "ENV_HOME",
    "LoadResult",
    "REGISTRY_VERSION",
    "RegistryEntry",
    "SOURCE_CHANGED",
    "SOURCE_MISSING",
    "SOURCE_OK",
    "SamplerRegistry",
    "samplers_home",
]
