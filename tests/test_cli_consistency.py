"""Jarvis CLI design §12 and sampler naming/check boundaries."""

from __future__ import annotations

import json
from pathlib import Path
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
    assert main(["check", str(path), "--points", "4", "--json"]) == 1
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
