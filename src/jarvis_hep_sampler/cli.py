"""``jsampler``: the Jarvis-HEP-Sampler command.

``Jarvis sampler`` calls this same command with ``prog="Jarvis sampler"``.
The library does not import Jarvis-HEP. Task cards and built-in method names
are read from Jarvis-HEP only when that package is installed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jarvis_hep_sampler._version import __version__

EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_USAGE = 2
_HELP_FLAGS = frozenset({"-h", "--help"})


def build_parser(prog: str) -> argparse.ArgumentParser:
    """The shared command surface for ``jsampler`` and ``Jarvis sampler``."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Write your own sampler as one Python file, load it once, then use it as "
            "Sampling.Method like a built-in method. "
            "Requires Jarvis-HEP-Sampler 1.x (1.0.0 or newer, before 2)."
        ),
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Print the Jarvis-HEP-Sampler version",
    )
    sub = parser.add_subparsers(dest="sampler_command", required=False)

    init = sub.add_parser("init", help="Create a sampler file from the template")
    init.add_argument("method", help="Sampling.Method name, e.g. MyLatinHypercube")
    init.add_argument("--output", help="File or directory to write (default ./<Method>.py)")

    check = sub.add_parser("check", help="Check a sampler offline (no Redis)")
    check.add_argument("target", help="Sampler file, or the name of a loaded sampler")
    context = check.add_mutually_exclusive_group()
    context.add_argument("--dimension", type=int, help="Number of variables (default 2)")
    context.add_argument("--card", help="Task YAML to take Variables and Bounds from")
    check.add_argument("--options", help="YAML file with the sampler's Bounds options")
    check.add_argument(
        "--points", type=int, help="Total candidate budget (default: the card's, else 100)",
    )
    check.add_argument("--seed", type=int, help="Seed (default: the card's, else 0)")

    load = sub.add_parser("load", help="Load or replace a sampler for every new run")
    load.add_argument("file", help="Sampler .py file")

    sub.add_parser("list", help="List loaded and shipped plug-in samplers")

    info = sub.add_parser("info", help="Show one loaded sampler")
    info.add_argument("method", help="Sampling.Method name")

    remove = sub.add_parser("remove", help="Unload a sampler (your file is kept)")
    remove.add_argument("method", help="Sampling.Method name")
    remove.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    return parser


def main(argv: list[str] | None = None, *, prog: str = "jsampler") -> int:
    """Run ``jsampler``. ``argv`` defaults to ``sys.argv[1:]``."""
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(prog)
    if not args or args[0] in _HELP_FLAGS:
        parser.print_help()
        return EXIT_OK
    if any(arg in _HELP_FLAGS for arg in args):
        try:
            parser.parse_args(args)
        except SystemExit as exc:
            return int(exc.code or EXIT_OK)
        return EXIT_OK
    try:
        parsed = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code or EXIT_USAGE)
    if parsed.version:
        print(f"Jarvis-HEP-Sampler {__version__}")
        return EXIT_OK
    command = parsed.sampler_command
    if command == "init":
        return _run_init(prog, parsed.method, parsed.output)
    if command == "check":
        return _run_check(prog, parsed)
    if command == "load":
        return _run_load(prog, parsed.file)
    if command == "list":
        return _run_list(prog)
    if command == "info":
        return _run_info(prog, parsed.method)
    if command == "remove":
        return _run_remove(prog, parsed.method, yes=bool(parsed.yes))
    parser.print_help()
    return EXIT_USAGE


def _prefix(prog: str) -> str:
    return "[Jarvis]" if prog.startswith("Jarvis") else "[jsampler]"


def _error(prog: str, message: str) -> int:
    print(f"{_prefix(prog)} {message}", file=sys.stderr)
    return EXIT_USAGE


def _table(title: str, rows: list[tuple[str, Any]]) -> None:
    print(title)
    width = max((len(str(key)) for key, _ in rows), default=0)
    for key, value in rows:
        print(f"  {str(key).ljust(width)}  {value}")


def _reserved() -> frozenset[str]:
    catalog = _catalog()
    if catalog is None:
        return frozenset()
    return frozenset(catalog.reserved_method_names())


def _catalog() -> Any | None:
    try:
        import jarvishep2.sampler_catalog as catalog
    except ImportError:
        return None
    return catalog


def _run_init(prog: str, method: str, output: str | None) -> int:
    from jarvis_hep_sampler import write_template
    from jarvis_hep_sampler.errors import PluginError

    try:
        path = write_template(method, output, reserved_names=_reserved())
    except (PluginError, FileExistsError) as exc:
        return _error(prog, str(exc))
    print(f"Created {path} from the independent sampler template.")
    print(f"Edit draw(), then run: {prog} load {path}")
    return EXIT_OK


def _load_yaml_mapping(path: str, what: str) -> Mapping[str, Any]:
    import yaml

    with open(Path(path).expanduser(), encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{what} {path} must contain a YAML mapping")
    return data


def _check_target(target: str) -> str | None:
    if Path(target).expanduser().is_file():
        return target
    from jarvis_hep_sampler import SamplerRegistry

    entry = SamplerRegistry().get(target)
    if entry is not None:
        return str(SamplerRegistry().snapshot_path(entry))
    catalog = _catalog()
    if catalog is None:
        return None
    record = catalog.plugin_record(target)
    return record.snapshot_path if record is not None else None


def _run_check(prog: str, args: Any) -> int:
    from jarvis_hep_sampler.options import parse_reserved, split_bounds
    from jarvis_hep_sampler.testing import check_plugin

    target = _check_target(str(args.target))
    if target is None:
        return _error(prog, f"{args.target} is neither a file nor a loaded sampler")

    variable_names: list[str] | None = None
    options: dict[str, Any] = {}
    seed = 0
    point_number = 100
    overrides: list[str] = []
    try:
        if args.card:
            try:
                from jarvishep2.sampling.variables import load_variables
                from jarvishep2.task_config import load_task_yaml
            except ImportError:
                return _error(prog, f"{prog} check --card needs Jarvis-HEP")
            config = load_task_yaml(args.card)
            variable_names = [variable.name for variable in load_variables(config)]
            bounds = dict((config.get("Sampling") or {}).get("Bounds") or {})
            reserved, options = split_bounds(bounds)
            settings = parse_reserved(reserved)
            seed = settings.seed
            point_number = int(settings.point_number)
        if args.options:
            options = dict(_load_yaml_mapping(args.options, "options file"))
            if args.card:
                overrides.append("options (replaced by --options)")
    except Exception as exc:
        return _error(prog, str(exc))
    if args.seed is not None:
        seed = int(args.seed)
        if args.card:
            overrides.append("seed")
    if args.points is not None:
        point_number = int(args.points)
        if args.card:
            overrides.append("point_number (changes the total candidate budget)")
    dimension = None if variable_names else int(args.dimension or 2)

    _table("Offline check settings ->", [
        ("variables", ", ".join(variable_names) if variable_names else dimension),
        ("seed", seed),
        ("point number", point_number),
        ("card overrides", ", ".join(overrides) if overrides else "none"),
    ])
    report = check_plugin(
        target,
        point_number=point_number,
        seed=seed,
        variable_names=variable_names,
        dimension=dimension,
        options=options,
        reserved_names=() if target != args.target else _reserved(),
    )
    _table(f"{report.method or args.target} check ->", report.rows())
    return EXIT_OK if report.ok else EXIT_RUN_FAILED


def _run_load(prog: str, file: str) -> int:
    from jarvis_hep_sampler import SamplerRegistry
    from jarvis_hep_sampler.errors import PluginError

    try:
        result = SamplerRegistry().load(file, reserved_names=_reserved())
    except PluginError as exc:
        print(f"{_prefix(prog)} Cannot load {file}: {exc}", file=sys.stderr)
        cause = exc.__cause__
        if cause is not None:
            print(f"{_prefix(prog)} Caused by {type(cause).__name__}: {cause}", file=sys.stderr)
        return EXIT_USAGE
    entry = result.entry
    rows: list[tuple[str, Any]] = [
        ("version", entry.version),
        ("profile", entry.profile),
        ("options schema", "yes" if entry.options_schema is not None else "no"),
        ("source", entry.source_path),
        ("snapshot", SamplerRegistry().snapshot_path(entry)),
    ]
    if result.replaced is not None:
        old = result.replaced
        rows.append((
            "replaced",
            f"{old.version} ({old.short_hash}) -> {entry.version} ({entry.short_hash})"
            if result.changed
            else "unchanged (same file)",
        ))
    _table(f"Loaded sampler {entry.method} ->", rows)
    print(f"Use it in a task card as  Sampling.Method: {entry.method}")
    return EXIT_OK


def _status(registry: Any, entry: Any, reserved: frozenset[str]) -> str:
    if entry.method.casefold() in {name.casefold() for name in reserved}:
        return "shadowed by a built-in method"
    problems = registry.problems(entry)
    if problems:
        return f"broken: {problems[0]}"
    return registry.source_state(entry)


def _print_rows(rows: list[tuple[str, str, str, str, str]]) -> None:
    header = ("Method", "Version", "Profile", "Source", "Status")
    widths = [max(len(str(row[i])) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, tuple("-" * width for width in widths), *rows]:
        line = "  ".join(
            str(cell).ljust(width) for cell, width in zip(row, widths, strict=True)
        )
        print(line.rstrip())


def _run_list(prog: str) -> int:
    from jarvis_hep_sampler import SamplerRegistry
    from jarvis_hep_sampler.errors import RegistryError

    registry = SamplerRegistry()
    rows: list[tuple[str, str, str, str, str]] = []
    catalog = _catalog()
    if catalog is not None:
        for spec in catalog.builtin_plugin_specs():
            record = catalog.plugin_record(spec.name)
            rows.append((
                spec.name, record.version if record else "", "independent", "shipped", "ok",
            ))
    try:
        entries = registry.entries()
    except RegistryError as exc:
        _print_rows(rows)
        print(f"{_prefix(prog)} {exc}", file=sys.stderr)
        return EXIT_RUN_FAILED
    reserved = _reserved()
    for method, entry in entries.items():
        rows.append((
            method, entry.version, entry.profile, entry.source_path,
            _status(registry, entry, reserved),
        ))
    _print_rows(rows)
    print(f"Registry: {registry.home}")
    return EXIT_OK


def _run_info(prog: str, method: str) -> int:
    from jarvis_hep_sampler import SamplerRegistry

    catalog = _catalog()
    record = catalog.plugin_record(method) if catalog is not None else None
    spec_name = None
    if catalog is not None:
        spec = catalog.spec_for(method)
        spec_name = spec.name if spec is not None else None
    registry = SamplerRegistry()
    entry = registry.get(method)
    if record is None and entry is None:
        return _error(prog, f"no plug-in sampler named {method!r}; see: {prog} list")
    if record is not None:
        rows: list[tuple[str, Any]] = [
            ("version", record.version),
            ("profile", record.profile),
            ("description", record.description or "—"),
            ("statistical", "yes" if record.statistical else "no"),
            ("options schema", "yes" if record.options_schema is not None else "no"),
            ("functions", ", ".join(record.hooks)),
            ("source", record.source_path),
        ]
        user = getattr(catalog, "SOURCE_USER", "user")
        if record.source == user:
            rows += [
                ("snapshot", record.snapshot_path),
                ("sha256", record.source_sha256),
                ("loaded at", record.loaded_at),
                ("status", _status(registry, entry, _reserved()) if entry else "missing"),
            ]
        else:
            rows.append(("status", "shipped with Jarvis-HEP"))
        _table(f"Sampler {spec_name or method} ->", rows)
        return EXIT_OK
    assert entry is not None
    _table(f"Sampler {entry.method} ->", [
        ("version", entry.version),
        ("profile", entry.profile),
        ("description", entry.description or "—"),
        ("statistical", "yes" if entry.statistical else "no"),
        ("options schema", "yes" if entry.options_schema is not None else "no"),
        ("functions", ", ".join(entry.hooks)),
        ("source", entry.source_path),
        ("snapshot", registry.snapshot_path(entry)),
        ("sha256", entry.source_sha256),
        ("loaded at", entry.loaded_at),
        ("status", _status(registry, entry, _reserved())),
    ])
    return EXIT_OK


def _run_remove(prog: str, method: str, *, yes: bool) -> int:
    from jarvis_hep_sampler import SamplerRegistry
    from jarvis_hep_sampler.errors import RegistryError

    if method.casefold() in {name.casefold() for name in _reserved()}:
        return _error(prog, f"{method} is a built-in method and cannot be removed")
    registry = SamplerRegistry()
    if not yes:
        if not sys.stdin.isatty():
            return _error(prog, "pass --yes to remove a sampler non-interactively")
        answer = input(f"Remove sampler {method} from {registry.home}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Nothing removed.")
            return EXIT_OK
    try:
        removed = registry.remove(method)
    except RegistryError as exc:
        return _error(prog, str(exc))
    print(f"Removed sampler {removed.method}; your file {removed.source_path} is unchanged.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
