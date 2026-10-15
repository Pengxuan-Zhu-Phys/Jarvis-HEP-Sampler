"""``jsampler``: the command for samplers loaded by this package.

It reads and writes the user registry. It does not know Jarvis-HEP's built-in
methods. ``check --card`` reads Variables and Bounds from the task YAML.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from jarvis_hep_sampler._version import __version__

EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_USAGE = 2
_HELP_FLAGS = frozenset({"-h", "--help"})
_AS_JSON: ContextVar[bool] = ContextVar("jsampler_json", default=False)


def _json_options() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--json",
        action="store_true",
        help="Print one plain JSON object instead of the formatted view",
    )
    return parent


def build_parser(prog: str) -> argparse.ArgumentParser:
    """The ``jsampler`` command. ``prog`` is the name printed in help and errors."""
    options = _json_options()
    parser = argparse.ArgumentParser(
        parents=[options],
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

    init = sub.add_parser("init", parents=[options], help="Create a sampler file from the template")
    init.add_argument("method", help="Sampling.Method name, e.g. MyLatinHypercube")
    init.add_argument("--output", help="File or directory to write (default ./<Method>.py)")

    check = sub.add_parser("check", parents=[options], help="Check a sampler offline (no Redis)")
    check.add_argument("target", help="Sampler file, or the name of a loaded sampler")
    context = check.add_mutually_exclusive_group()
    context.add_argument("--dimension", type=int, help="Number of variables (default 2)")
    context.add_argument("--card", help="Task YAML to take Variables and Bounds from")
    check.add_argument("--options", help="YAML file with the sampler's Bounds options")
    check.add_argument(
        "--points", type=int, help="Total candidate budget (default: the card's, else 100)",
    )
    check.add_argument("--seed", type=int, help="Seed (default: the card's, else 0)")

    load = sub.add_parser(
        "load", parents=[options], help="Load or replace a sampler for every new run",
    )
    load.add_argument("file", help="Sampler .py file")

    sub.add_parser("list", parents=[options], help="List samplers loaded by this package")

    info = sub.add_parser("info", parents=[options], help="Show one loaded sampler")
    info.add_argument("method", help="Sampling.Method name")

    remove = sub.add_parser(
        "remove", parents=[options], help="Unload a sampler (your file is kept)",
    )
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
    token = _AS_JSON.set("--json" in args)
    try:
        return _dispatch(prog, parser, parsed)
    finally:
        _AS_JSON.reset(token)


def _dispatch(prog: str, parser: argparse.ArgumentParser, parsed: Any) -> int:
    if parsed.version:
        if _json():
            _print_json({"package": "Jarvis-HEP-Sampler", "version": __version__})
        else:
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


def _json() -> bool:
    return _AS_JSON.get()


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _console() -> Console:
    return Console(highlight=False)


def _prefix(prog: str) -> str:
    return "[Jarvis]" if prog.startswith("Jarvis") else "[jsampler]"


def _error(prog: str, message: str, *, command: str | None = None, code: int = EXIT_USAGE) -> int:
    if _json():
        payload: dict[str, Any] = {"ok": False, "error": {"message": message}}
        if command is not None:
            payload["command"] = command
        _print_json(payload)
    else:
        print(f"{_prefix(prog)} {message}", file=sys.stderr)
    return code


def _panel(
    title: str,
    rows: list[tuple[str, Any]],
    *,
    note: str = "",
    border: str = "cyan",
) -> None:
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold dim", no_wrap=True)
    grid.add_column(overflow="fold")
    for key, value in rows:
        grid.add_row(key.upper(), Text(str(value)))
    body: Any = grid
    if note:
        body = Group(grid, Text(""), Text(note))
    _console().print(Panel(
        body,
        title=Text(title, style="bold"),
        box=box.ROUNDED,
        border_style=border,
        padding=(0, 1),
    ))


def _run_init(prog: str, method: str, output: str | None) -> int:
    from jarvis_hep_sampler import write_template
    from jarvis_hep_sampler.errors import PluginError

    try:
        path = write_template(method, output)
    except (PluginError, FileExistsError) as exc:
        return _error(prog, str(exc), command="init")
    note = f"Edit draw(), then run: {prog} load {path}"
    if _json():
        _print_json({"command": "init", "method": method, "ok": True, "path": str(path)})
    else:
        _panel(f"Created · {method}", [("file", path)], note=note, border="green")
    return EXIT_OK


def _card_sampling(path: str) -> tuple[list[str], dict[str, Any]]:
    """Variable names and ``Sampling.Bounds`` from a task YAML file."""
    data = _load_yaml_mapping(path, "task card")
    sampling = data.get("Sampling") or {}
    if not isinstance(sampling, Mapping):
        raise ValueError("Sampling must be a mapping")
    raw_variables = sampling.get("Variables") or []
    if not isinstance(raw_variables, list):
        raise ValueError("Sampling.Variables must be a list")
    names: list[str] = []
    for index, item in enumerate(raw_variables):
        if not isinstance(item, Mapping):
            raise ValueError(f"Sampling.Variables[{index}] must be a mapping")
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(f"Sampling.Variables[{index}].name is required")
        names.append(name)
    bounds = sampling.get("Bounds") or {}
    if not isinstance(bounds, Mapping):
        raise ValueError("Sampling.Bounds must be a mapping")
    return names, dict(bounds)


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
    if entry is None:
        return None
    return str(SamplerRegistry().snapshot_path(entry))


def _run_check(prog: str, args: Any) -> int:
    from jarvis_hep_sampler.options import parse_reserved, split_bounds
    from jarvis_hep_sampler.testing import check_plugin

    target = _check_target(str(args.target))
    if target is None:
        return _error(
            prog, f"{args.target} is neither a file nor a loaded sampler", command="check",
        )

    variable_names: list[str] | None = None
    options: dict[str, Any] = {}
    seed = 0
    point_number = 100
    overrides: list[str] = []
    try:
        if args.card:
            variable_names, bounds = _card_sampling(args.card)
            reserved, options = split_bounds(bounds)
            settings = parse_reserved(reserved)
            seed = settings.seed
            point_number = int(settings.point_number)
        if args.options:
            options = dict(_load_yaml_mapping(args.options, "options file"))
            if args.card:
                overrides.append("options (replaced by --options)")
    except Exception as exc:
        return _error(prog, str(exc), command="check")
    if args.seed is not None:
        seed = int(args.seed)
        if args.card:
            overrides.append("seed")
    if args.points is not None:
        point_number = int(args.points)
        if args.card:
            overrides.append("point_number (changes the total candidate budget)")
    dimension = None if variable_names else int(args.dimension or 2)
    variables = ", ".join(variable_names) if variable_names else dimension
    report = check_plugin(
        target,
        point_number=point_number,
        seed=seed,
        variable_names=variable_names,
        dimension=dimension,
        options=options,
    )
    if _json():
        _print_json({
            "checks": [
                {"detail": item.detail, "name": item.name, "ok": item.ok} for item in report.items
            ],
            "command": "check",
            "method": report.method,
            "ok": report.ok,
            "settings": {
                "card_overrides": overrides,
                "point_number": point_number,
                "seed": seed,
                "variables": variables,
            },
            "target": str(args.target),
        })
    else:
        rows = [
            ("variables", variables),
            ("seed", seed),
            ("point number", point_number),
            ("card overrides", ", ".join(overrides) if overrides else "none"),
            *report.rows(),
        ]
        _panel(
            f"Check · {report.method or args.target}",
            rows,
            border="green" if report.ok else "red",
        )
    return EXIT_OK if report.ok else EXIT_RUN_FAILED


def _run_load(prog: str, file: str) -> int:
    from jarvis_hep_sampler import SamplerRegistry
    from jarvis_hep_sampler.errors import PluginError

    try:
        result = SamplerRegistry().load(file)
    except PluginError as exc:
        detail = f"Cannot load {file}: {exc}"
        cause = exc.__cause__
        if cause is not None:
            detail = f"{detail} Caused by {type(cause).__name__}: {cause}"
        return _error(prog, detail, command="load")
    entry = result.entry
    snapshot = str(SamplerRegistry().snapshot_path(entry))
    replaced: str | None = None
    if result.replaced is not None:
        old = result.replaced
        replaced = (
            f"{old.version} ({old.short_hash}) -> {entry.version} ({entry.short_hash})"
            if result.changed
            else "unchanged (same file)"
        )
    if _json():
        payload: dict[str, Any] = {
            "command": "load",
            "method": entry.method,
            "ok": True,
            "options_schema": entry.options_schema is not None,
            "profile": entry.profile,
            "snapshot": snapshot,
            "source": entry.source_path,
            "version": entry.version,
        }
        if replaced is not None:
            payload["replaced"] = replaced
        _print_json(payload)
    else:
        rows: list[tuple[str, Any]] = [
            ("version", entry.version),
            ("profile", entry.profile),
            ("options schema", "yes" if entry.options_schema is not None else "no"),
            ("source", entry.source_path),
            ("snapshot", snapshot),
        ]
        if replaced is not None:
            rows.append(("replaced", replaced))
        _panel(
            f"Loaded · {entry.method}",
            rows,
            note=f"Use it in a task card as  Sampling.Method: {entry.method}",
            border="green",
        )
    return EXIT_OK


def _status(registry: Any, entry: Any) -> str:
    problems = registry.problems(entry)
    if problems:
        return f"broken: {problems[0]}"
    return registry.source_state(entry)


def _status_text(status: str) -> Text:
    if status == "ok":
        style = "bold green"
    elif status.startswith("broken") or "missing" in status:
        style = "bold red"
    else:
        style = "bold yellow"
    return Text(status, style=style)


def _run_list(prog: str) -> int:
    from jarvis_hep_sampler import SamplerRegistry
    from jarvis_hep_sampler.errors import RegistryError

    registry = SamplerRegistry()
    try:
        entries = registry.entries()
    except RegistryError as exc:
        return _error(prog, str(exc), command="list", code=EXIT_RUN_FAILED)
    listed = [
        {
            "method": method,
            "profile": entry.profile,
            "source": entry.source_path,
            "status": _status(registry, entry),
            "version": entry.version,
        }
        for method, entry in entries.items()
    ]
    if _json():
        _print_json({
            "command": "list",
            "ok": True,
            "registry": str(registry.home),
            "samplers": listed,
        })
        return EXIT_OK
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold dim")
    for name in ("Method", "Version", "Profile", "Source", "Status"):
        table.add_column(name.upper(), overflow="fold")
    for item in listed:
        table.add_row(
            Text(item["method"], style="bold #c8c8ff"),
            item["version"],
            item["profile"],
            Text(item["source"], style="dim"),
            _status_text(item["status"]),
        )
    body: Any = table
    if not listed:
        body = Group(table, Text("No samplers loaded.", style="dim"))
    _console().print(
        Panel(
            Group(body, Text(""), Text(f"Registry: {registry.home}", style="dim")),
            title=Text("Loaded samplers", style="bold"),
            box=box.ROUNDED,
            border_style="dim",
            padding=(0, 1),
        )
    )
    return EXIT_OK


def _run_info(prog: str, method: str) -> int:
    from jarvis_hep_sampler import SamplerRegistry

    registry = SamplerRegistry()
    entry = registry.get(method)
    if entry is None:
        return _error(
            prog, f"no loaded sampler named {method!r}; see: {prog} list", command="info",
        )
    status = _status(registry, entry)
    if _json():
        _print_json({
            "command": "info",
            "description": entry.description,
            "functions": list(entry.hooks),
            "loaded_at": entry.loaded_at,
            "method": entry.method,
            "ok": True,
            "options_schema": entry.options_schema is not None,
            "profile": entry.profile,
            "sha256": entry.source_sha256,
            "snapshot": str(registry.snapshot_path(entry)),
            "source": entry.source_path,
            "statistical": entry.statistical,
            "status": status,
            "version": entry.version,
        })
        return EXIT_OK
    _panel(f"Sampler · {entry.method}", [
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
        ("status", status),
    ])
    return EXIT_OK


def _run_remove(prog: str, method: str, *, yes: bool) -> int:
    from jarvis_hep_sampler import SamplerRegistry
    from jarvis_hep_sampler.errors import RegistryError

    registry = SamplerRegistry()
    if not yes:
        if _json() or not sys.stdin.isatty():
            return _error(
                prog, "pass --yes to remove a sampler non-interactively", command="remove",
            )
        answer = input(f"Remove sampler {method} from {registry.home}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Nothing removed.")
            return EXIT_OK
    try:
        removed = registry.remove(method)
    except RegistryError as exc:
        return _error(prog, str(exc), command="remove")
    if _json():
        _print_json({
            "command": "remove",
            "method": removed.method,
            "ok": True,
            "source": removed.source_path,
        })
    else:
        _panel(
            f"Removed · {removed.method}",
            [("file", removed.source_path)],
            note="Your file is unchanged.",
            border="green",
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
