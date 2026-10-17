"""Jarvis CLI design §12 and sampler naming/check boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest

from jarvis_hep_sampler import __version__
from jarvis_hep_sampler.cli import main
from jarvis_hep_sampler.testing import check_plugin


@pytest.mark.parametrize("command", [None, "init", "check", "load", "list", "info", "remove"])
def test_each_help_uses_jarvis_layout_and_json_in_either_order(command, capsys):
    prefix = [] if command is None else [command]
    assert main([*prefix, "-h"]) == 0
    output = capsys.readouterr().out
    assert output.splitlines()[0].startswith(
        f"Usage: jsampler{f' {command}' if command else ''} [OPTIONS]"
    )
    assert "Show this message and exit." in output
    assert "╭─ Options" in output
    for args in (["--json", *prefix, "-h"], [*prefix, "-h", "--json"]):
        assert main(args) == 0
        document = json.loads(capsys.readouterr().out)
        assert document["ok"] is True
        assert document["command"] == (f"{command} help" if command else "help")


def test_version_and_errors_follow_shared_json_contract(capsys, monkeypatch):
    assert main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["command"] == "help"
    for args in (["--version", "--json"], ["--json", "--version"]):
        assert main(args) == 0
        assert json.loads(capsys.readouterr().out) == {
            "ok": True, "command": "version", "name": "Jarvis-HEP-Sampler",
            "version": __version__,
        }
    assert main(["unknown-command"]) == 2
    error = capsys.readouterr().err
    assert "╭" in error and "jsampler" in error
    assert "Traceback" not in error and "usage:" not in error
    assert main(["--json", "unknown-command"]) == 2
    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is False
    assert document["command"] == "root"
    assert document["error"]["type"] == "ArgumentError"
    assert document["error"]["message"]
    monkeypatch.setenv("NO_COLOR", "1")
    assert main(["-h"]) == 0
    assert "\x1b[" not in capsys.readouterr().out
    assert main(["unknown-command"]) == 2
    assert "\x1b[" not in capsys.readouterr().err


def test_check_accepts_only_files_and_rejects_invalid_dimension(
    uniform_plugin: Path, capsys,
):
    assert main(["load", str(uniform_plugin)]) == 0
    capsys.readouterr()
    assert main(["check", "Uniform"]) == 2
    error = capsys.readouterr().err
    assert "jsampler info <Method>" in error
    assert main(["check", str(uniform_plugin), "--dimension", "0", "--json"]) == 2
    document = json.loads(capsys.readouterr().out)
    assert document["error"]["type"] == "ValueError"
    assert "--dimension" in document["error"]["message"]
    assert main(["check", str(uniform_plugin), "--dimension", "-1"]) == 2
    assert "--dimension" in capsys.readouterr().err


def test_negative_seed_fails_before_plugin_check(uniform_plugin: Path, capsys):
    with patch("jarvis_hep_sampler.testing.check_plugin") as checker:
        assert main(["check", str(uniform_plugin), "--seed", "-1", "--json"]) == 2
        captured = capsys.readouterr()
        document = json.loads(captured.out)
        assert captured.err == ""
        assert document["ok"] is False
        assert document["command"] == "check"
        assert document["error"]["type"] == "ValueError"
        assert "--seed" in document["error"]["message"]
        assert main(["check", str(uniform_plugin), "--seed", "-1"]) == 2
        text_error = capsys.readouterr().err
        assert "╭" in text_error and "--seed" in text_error
        assert "Traceback" not in text_error
        checker.assert_not_called()


def test_reserved_method_is_first_and_execution_is_skipped(write_plugin, tmp_path, capsys):
    marker = tmp_path / "executed"
    path = write_plugin(f'''
PLUGIN = {{"api_version": 1, "method": "Grid", "version": "1", "profile": "independent"}}
def validate_options(options):
    open({str(marker)!r}, "w").write("options")
def prepare(setup):
    open({str(marker)!r}, "w").write("prepare")
def draw(context, rng, plan):
    open({str(marker)!r}, "w").write("draw")
    return [0.5] * context.dimension
''', "Grid.py")
    report = check_plugin(path, dimension=2, point_number=4)
    assert report.items[0].name == "method"
    assert [item.name for item in report.failures()] == ["method"]
    assert all(item.skipped for item in report.items[1:])
    assert not marker.exists()
    assert main(["check", str(path), "--points", "4", "--json"]) == 2
    document = json.loads(capsys.readouterr().out)
    assert document["error"]["type"] == "CheckFailed"
    assert document["checks"][0]["name"] == "method"
    assert all(item["skipped"] for item in document["checks"][1:])
    assert not marker.exists()


@pytest.mark.parametrize("command", ["list", "info", "remove"])
def test_corrupt_registry_exits_two_with_single_json_error(command, tmp_path, capsys):
    home = tmp_path / "samplers-home"
    home.mkdir()
    (home / "sources.json").write_text("{not json", encoding="utf-8")
    args = [command]
    if command != "list":
        args.append("Uniform")
    if command == "remove":
        args.append("--yes")
    assert main([*args, "--json"]) == 2
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert captured.err == ""
    assert document["ok"] is False
    assert document["command"] == command
    assert document["error"]["type"] == "RegistryError"
    assert document["error"]["message"]
    assert "Traceback" not in captured.out


def test_host_can_extend_list_and_info_help_without_parser_copy(capsys):
    for command in ("list", "info"):
        assert main(
            [command, "-h"], prog="Jarvis sampler",
            command_help={command: f"Show {command} including built-in methods"},
            command_description={command: f"Show {command} including built-in methods"},
        ) == 0
        output = capsys.readouterr().out
        assert output.startswith(f"Usage: Jarvis sampler {command}")
        assert f"Show {command} including built-in methods" in output
    assert main(["--json", "-h"], prog="Jarvis sampler") == 0
    assert json.loads(capsys.readouterr().out)["command"] == "sampler help"


def test_host_catalog_uses_the_same_text_and_json_renderers(tmp_path, monkeypatch, capsys):
    from jarvis_hep_sampler import cli

    monkeypatch.setenv("JARVIS_SAMPLERS_HOME", str(tmp_path / "registry"))
    host = {"method": "HostMethod", "version": "1", "profile": "independent",
            "source": "host", "status": "built-in"}

    def listing(payload):
        return {**payload, "host_methods": [host]}

    def info(method, payload):
        if method == "HostMethod":
            return {"ok": True, "command": "sampler info", **host,
                    "conflicts": [{"method": "hostmethod", "problems": ["name conflict"],
                                   "repair_command": "Jarvis sampler remove hostmethod --yes"}]}
        return payload

    extension = cli.CatalogExtension(listing, info, (("host_methods", "Host methods"),))
    with mock.patch.object(cli, "_render_list_section", wraps=cli._render_list_section) as renderer:
        assert main(["list"], catalog=extension) == 0
        assert renderer.call_count == 2
    text = capsys.readouterr().out
    assert "No samplers loaded." in text and "Host methods" in text and "HostMethod" in text
    assert main(["list", "--json"], catalog=extension) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["samplers"] == [] and document["host_methods"] == [host]
    with mock.patch.object(cli, "_render_info", wraps=cli._render_info) as renderer:
        assert main(["info", "HostMethod"], catalog=extension) == 0
        renderer.assert_called_once()
    assert "remove hostmethod --yes" in capsys.readouterr().out
    assert main(["info", "HostMethod", "--json"], catalog=extension) == 0
    assert json.loads(capsys.readouterr().out)["conflicts"][0]["method"] == "hostmethod"


def test_bad_output_remains_exit_one_while_reserved_check_is_exit_two(write_plugin, capsys):
    path = write_plugin('''
PLUGIN = {"api_version": 1, "method": "BadOutput", "version": "1", "profile": "independent"}
def draw(context, rng, plan):
    return [float("nan")] * context.dimension
''')
    assert main(["check", str(path), "--json"]) == 1
    document = json.loads(capsys.readouterr().out)
    assert document["checks"][0]["ok"] is True
    assert document["error"]["type"] == "CheckFailed"


def test_reserved_name_precedes_even_invalid_options_schema(write_plugin, capsys):
    path = write_plugin('''
PLUGIN = {"api_version": 1, "method": "Grid", "version": "1", "profile": "independent"}
OPTIONS_SCHEMA = {"type": 42}
def draw(context, rng, plan):
    raise AssertionError("draw must not execute")
''')
    assert main(["check", str(path), "--json"]) == 2
    document = json.loads(capsys.readouterr().out)
    assert "built-in" in document["checks"][0]["detail"]
    assert all(item["skipped"] for item in document["checks"][1:])
    assert main(["load", str(path), "--json"]) == 2
    assert "built-in" in json.loads(capsys.readouterr().out)["error"]["message"]
