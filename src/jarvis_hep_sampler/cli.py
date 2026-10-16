"""``jsampler``: the command for samplers loaded by this package.

It reads and writes the user registry. It does not know Jarvis-HEP's built-in
methods. ``check --card`` reads Variables and Bounds from the task YAML.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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


class _Parser(argparse.ArgumentParser):
    """Argparse parser whose help and usage errors use Jarvis rich panels."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self.add_argument(
            "-h", "--help", action="help", help="Show this message and exit.",
        )

    def format_usage(self) -> str:
        parts = [f"Usage: {self.prog} [OPTIONS]"]
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                parts.append("<command>")
            elif not action.option_strings and action.dest != argparse.SUPPRESS:
                label = str(action.metavar or f"<{action.dest}>")
                parts.append(label if action.required else f"[{label}]")
        return " ".join(parts) + "\n"

    def format_help(self) -> str:
        if _json():
            return json.dumps(
                _help_document(self), indent=2, sort_keys=True, ensure_ascii=False,
            ) + "\n"
        from io import StringIO

        buffer = StringIO()
        width = shutil.get_terminal_size((80, 24)).columns
        console = Console(
            file=buffer,
            highlight=False,
            force_terminal=sys.stdout.isatty() and not bool(os.environ.get("NO_COLOR")),
            no_color=bool(os.environ.get("NO_COLOR")),
            width=width,
        )
        _render_help(self, console)
        return buffer.getvalue()

    def error(self, message: str) -> None:
        root = _root_prog(self.prog)
        command = self.prog.removeprefix(root).strip() or "root"
        emit_error(
            root, message, command=_command_path(root, command), error_type="ArgumentError",
            hint=f"Use {self.prog} -h for usage.", as_json=_json(),
        )
        self.exit(EXIT_USAGE)


def _root_prog(prog: str) -> str:
    return "Jarvis sampler" if prog.startswith("Jarvis sampler") else prog.split()[0]


def _command_path(prog: str, command: str) -> str:
    if prog.startswith("Jarvis sampler") and not command.startswith("sampler "):
        return f"sampler {command}"
    return command


def _metavar(action: argparse.Action) -> str:
    if action.metavar is not None:
        if isinstance(action.metavar, tuple):
            return " ".join(action.metavar)
        return str(action.metavar)
    if action.type is int:
        return "<int>"
    return "<str>"


def _help_document(parser: argparse.ArgumentParser) -> dict[str, Any]:
    arguments: list[dict[str, str]] = []
    options: list[dict[str, Any]] = []
    commands: list[dict[str, str]] = []
    for action in parser._actions:
        if action.help == argparse.SUPPRESS:
            continue
        if isinstance(action, argparse._SubParsersAction):
            descriptions = {
                choice.dest: choice.help or ""
                for choice in getattr(action, "_choices_actions", [])
            }
            commands.extend(
                {"help": descriptions.get(name, ""), "name": name} for name in action.choices
            )
            continue
        if action.option_strings:
            options.append({
                "help": action.help or "",
                "metavar": None if action.nargs == 0 else _metavar(action),
                "names": list(action.option_strings),
            })
        elif action.dest not in {"help", "sampler_command"}:
            arguments.append({
                "help": action.help or "",
                "metavar": _metavar(action),
                "name": action.dest,
            })
    return {
        "arguments": arguments,
        "command": _command_path(
            _root_prog(parser.prog),
            f"{parser.prog.removeprefix(_root_prog(parser.prog)).strip()} help".strip(),
        ),
        "commands": commands,
        "description": parser.description or "",
        "ok": True,
        "options": options,
        "prog": parser.prog,
        "usage": parser.format_usage().strip(),
    }


def _help_panel(console: Console, title: str, rows: list[tuple[Text, Text, str]]) -> None:
    if not rows:
        return
    table = Table(
        show_header=False,
        expand=True,
        box=None,
        pad_edge=False,
        padding=(0, 1),
        highlight=False,
    )
    table.add_column(width=24, no_wrap=True)
    table.add_column(width=6, no_wrap=True)
    table.add_column(ratio=1)
    for primary, alias, help_text in rows:
        table.add_row(primary, alias, help_text)
    console.print(Panel(
        table, title=title, title_align="left", border_style="dim", padding=(0, 1),
    ))


def _render_help(parser: argparse.ArgumentParser, console: Console) -> None:
    document = _help_document(parser)
    console.print(Text(str(document["usage"]), style="bold"))
    if document["description"]:
        console.print(Text(str(document["description"])))
    if document["commands"]:
        console.print(Text(f"Command help: {parser.prog} COMMAND -h"))
    console.print()
    arguments = [
        (
            Text(item["name"], style="bold cyan"),
            Text(item["metavar"], style="bold yellow"),
            item["help"],
        )
        for item in document["arguments"]
    ]
    options = []
    for item in document["options"]:
        longs = [name for name in item["names"] if name.startswith("--")]
        shorts = [name for name in item["names"] if not name.startswith("--")]
        label = ",".join(longs or shorts)
        if item["metavar"]:
            label = f"{label} {item['metavar']}"
        options.append((
            Text(label, style="bold cyan"),
            Text(",".join(shorts if longs else []), style="bold cyan"),
            item["help"],
        ))
    commands = [
        (Text(item["name"], style="bold cyan"), Text(""), item["help"])
        for item in document["commands"]
    ]
    _help_panel(console, "Arguments", arguments)
    _help_panel(console, "Options", options)
    _help_panel(console, "Commands", commands)


def build_parser(
    prog: str,
    *,
    command_help: Mapping[str, str] | None = None,
    command_description: Mapping[str, str] | None = None,
) -> argparse.ArgumentParser:
    """Build the shared parser, with optional host descriptions for subcommands."""
    options = _json_options()
    parser = _Parser(
        parents=[options],
        prog=prog,
        description=(
            "Write your own sampler as one Python file, load it once, then use it as "
            "Sampling.Method like a built-in method."
        ),
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Show the Jarvis-HEP-Sampler version and exit.",
    )
    sub = parser.add_subparsers(
        dest="sampler_command", required=False, parser_class=_Parser,
    )

    def label(name: str, default: str) -> str:
        return (command_help or {}).get(name, default)

    def description(name: str, default: str) -> str:
        return (command_description or {}).get(name, default)

    init = sub.add_parser(
        "init",
        parents=[options],
        help=label("init", "Create a sampler file from the template"),
        description=description("init", "Create a sampler file from the template"),
    )
    init.add_argument("method", help="Sampling.Method name, e.g. MyLatinHypercube")
    init.add_argument("--output", help="File or directory to write (default ./<Method>.py)")

    check = sub.add_parser(
        "check",
        parents=[options],
        help=label("check", "Check a sampler file offline (no Redis)"),
        description=description("check", "Check a sampler file offline (no Redis)"),
    )
    check.add_argument("target", metavar="<file>", help="Sampler Python file")
    context = check.add_mutually_exclusive_group()
    context.add_argument("--dimension", type=int, help="Number of variables (default 2)")
    context.add_argument("--card", help="Task YAML to take Variables and Bounds from")
    check.add_argument("--options", help="YAML file with the sampler's Bounds options")
    check.add_argument(
        "--points", type=int, help="Total candidate budget (default: the card's, else 100)",
    )
    check.add_argument("--seed", type=int, help="Seed (default: the card's, else 0)")

    load = sub.add_parser(
        "load",
        parents=[options],
        help=label("load", "Load or replace a sampler for every new run"),
        description=description("load", "Load or replace a sampler for every new run"),
    )
    load.add_argument("file", help="Sampler .py file")

    sub.add_parser(
        "list",
        parents=[options],
        help=label("list", "List samplers loaded by this package"),
        description=description("list", "List samplers loaded by this package"),
    )

    info = sub.add_parser(
        "info",
        parents=[options],
        help=label("info", "Show one loaded sampler"),
        description=description("info", "Show one loaded sampler"),
    )
    info.add_argument("method", help="Sampling.Method name")

    remove = sub.add_parser(
        "remove",
        parents=[options],
        help=label("remove", "Unload a sampler (your file is kept)"),
        description=description("remove", "Unload a sampler (your file is kept)"),
    )
    remove.add_argument("method", help="Sampling.Method name")
    remove.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    prog: str = "jsampler",
    command_help: Mapping[str, str] | None = None,
    command_description: Mapping[str, str] | None = None,
) -> int:
    """Run ``jsampler``. ``argv`` defaults to ``sys.argv[1:]``."""
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(
        prog, command_help=command_help, command_description=command_description,
    )
    token = _AS_JSON.set("--json" in args)
    try:
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
        return _dispatch(prog, parser, parsed)
    finally:
        _AS_JSON.reset(token)


def _dispatch(prog: str, parser: argparse.ArgumentParser, parsed: Any) -> int:
    if parsed.version:
        if _json():
            _print_json({
                "ok": True, "command": _command_path(prog, "version"),
                "name": "Jarvis-HEP-Sampler",
                "version": __version__,
            })
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
    return EXIT_OK


def _json() -> bool:
    return _AS_JSON.get()


def _print_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _console() -> Console:
    return Console(highlight=False)


def emit_error(
    prog: str,
    message: str,
    *,
    command: str | None = None,
    hint: str | None = None,
    error_type: str = "UsageError",
    code: int = EXIT_USAGE,
    as_json: bool | None = None,
) -> int:
    """Render a CLI error for ``jsampler`` or a forwarding Jarvis command."""
    json_mode = _json() if as_json is None else as_json
    command_path = command or "root"
    if json_mode:
        _print_json({
            "command": command_path,
            "error": {"type": error_type, "message": message, "hint": hint},
            "ok": False,
        })
    else:
        lines: list[Any] = [Text(message)]
        if hint:
            lines.extend((Text(""), Text(hint, style="dim")))
        Console(
            stderr=True, highlight=False,
            force_terminal=sys.stderr.isatty() and not bool(os.environ.get("NO_COLOR")),
            no_color=bool(os.environ.get("NO_COLOR")),
        ).print(Panel(
            Group(*lines),
            title=Text(prog, style="bold"),
            border_style="red",
            box=box.ROUNDED,
            padding=(0, 1),
        ))
    return code


def _error(
    prog: str, message: str, *, command: str | None = None,
    code: int = EXIT_USAGE, hint: str | None = None,
    error_type: str = "UsageError",
) -> int:
    return emit_error(
        prog, message, command=_command_path(prog, command or "root"), code=code, hint=hint,
        error_type=error_type,
    )


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
        return _error(
            prog, str(exc), command="init", error_type=type(exc).__name__,
            hint=f"Choose another method or output path, then run {prog} init <Method>.",
        )
    note = f"Edit draw(), then run: {prog} load {path}"
    if _json():
        _print_json({
            "command": _command_path(prog, "init"), "method": method,
            "ok": True, "path": str(path),
        })
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


def _run_check(prog: str, args: Any) -> int:
    from jarvis_hep_sampler.options import parse_reserved, split_bounds
    from jarvis_hep_sampler.testing import check_plugin

    target = Path(str(args.target)).expanduser()
    if not target.is_file():
        return _error(
            prog, f"sampler file not found: {args.target}", command="check",
            error_type="FileNotFoundError",
            hint=(f"Use {prog} info <Method> to locate a loaded sampler's source file, "
                  f"then run {prog} check <file>."),
        )
    if args.dimension is not None and args.dimension <= 0:
        return _error(
            prog, f"--dimension must be positive (got {args.dimension})", command="check",
            error_type="ValueError", hint=f"Run {prog} check {args.target} --dimension 2.",
        )
    if args.points is not None and args.points <= 0:
        return _error(
            prog, f"--points must be positive (got {args.points})", command="check",
            error_type="ValueError", hint=f"Run {prog} check {args.target} --points 100.",
        )
    if args.seed is not None and args.seed < 0:
        return _error(
            prog, f"--seed must be non-negative (got {args.seed})", command="check",
            error_type="ValueError", hint=f"Run {prog} check {args.target} --seed 0.",
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
        return _error(
            prog, str(exc), command="check", error_type=type(exc).__name__,
            hint=f"Correct the check inputs and run {prog} check {args.target} again.",
        )
    if args.seed is not None:
        seed = int(args.seed)
        if args.card:
            overrides.append("seed")
    if args.points is not None:
        point_number = int(args.points)
        if args.card:
            overrides.append("point_number (changes the total candidate budget)")
    dimension = None if variable_names is not None else (
        int(args.dimension) if args.dimension is not None else 2
    )
    variables = ", ".join(variable_names) if variable_names is not None else dimension
    report = check_plugin(
        str(target),
        point_number=point_number,
        seed=seed,
        variable_names=variable_names,
        dimension=dimension,
        options=options,
    )
    if _json():
        payload: dict[str, Any] = {
            "checks": [
                {
                    "detail": item.detail, "name": item.name, "ok": item.ok,
                    "skipped": item.skipped,
                }
                for item in report.items
            ],
            "command": _command_path(prog, "check"),
            "method": report.method,
            "ok": report.ok,
            "settings": {
                "card_overrides": overrides,
                "point_number": point_number,
                "seed": seed,
                "variables": variables,
            },
            "target": str(args.target),
        }
        if not report.ok:
            failure = next(
                (item for item in report.items if not item.ok and not item.skipped), None,
            )
            payload["error"] = {
                "type": "CheckFailed",
                "message": failure.detail if failure is not None else "sampler check failed",
                "hint": f"Correct {args.target} and run {prog} check {args.target} again.",
            }
        _print_json(payload)
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
            note=(
                "card overrides: "
                + (", ".join(overrides) if overrides else "none")
                + ("\n--points changes the total candidate budget from the card."
                   if args.points is not None else "")
                if args.card else ""
            ),
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
        return _error(
            prog, detail, command="load", error_type=type(exc).__name__,
            hint=f"Correct the sampler file and run {prog} load {file} again.",
        )
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
            "command": _command_path(prog, "load"),
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
        return _error(
            prog, str(exc), command="list", error_type="RegistryError",
            hint=(f"Repair the registry at {registry.home} or restore it from a backup, "
                  f"then run {prog} list."),
        )
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
            "command": _command_path(prog, "list"),
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
    from jarvis_hep_sampler.errors import RegistryError

    registry = SamplerRegistry()
    try:
        entry = registry.get(method)
    except RegistryError as exc:
        return _error(
            prog, str(exc), command="info", error_type="RegistryError",
            hint=(f"Repair the registry at {registry.home} or restore it from a backup, "
                  f"then run {prog} info {method}."),
        )
    if entry is None:
        return _error(
            prog, f"no loaded sampler named {method!r}", command="info",
            error_type="RegistryError", hint=f"Run {prog} list to see loaded samplers.",
        )
    status = _status(registry, entry)
    if _json():
        _print_json({
            "command": _command_path(prog, "info"),
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
                hint=f"Run {prog} remove {method} --yes.",
            )
        answer = input(f"Remove sampler {method} from {registry.home}? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            _panel("Remove", [("result", "Nothing removed.")], border="dim")
            return EXIT_OK
    try:
        removed = registry.remove(method)
    except RegistryError as exc:
        return _error(
            prog, str(exc), command="remove", error_type="RegistryError",
            hint=f"Run {prog} list to inspect the registry, then retry removal.",
        )
    if _json():
        _print_json({
            "command": _command_path(prog, "remove"),
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
