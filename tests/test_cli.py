"""The jsampler command. It only sees samplers loaded by this package."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis_hep_sampler import __version__
from jarvis_hep_sampler.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_help_uses_rich_panels(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-h"]) == 0
    out = capsys.readouterr().out
    assert "Commands" in out and "init" in out and "╭" in out
    assert main(["check", "-h"]) == 0
    assert "Arguments" in capsys.readouterr().out
    assert main(["--json", "-h"]) == 0
    raw = capsys.readouterr().out
    assert "╭" not in raw
    document = json.loads(raw)
    names = {item["name"] for item in document["commands"]}
    assert names == {"init", "check", "load", "list", "info", "remove"}
    assert any("--json" in item["names"] for item in document["options"])
    assert main(["check", "--json", "-h"]) == 0
    check_help = json.loads(capsys.readouterr().out)
    assert any(item["name"] == "target" for item in check_help["arguments"])
    assert any("--card" in item["names"] for item in check_help["options"])


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-v"]) == 0
    assert capsys.readouterr().out.strip() == f"Jarvis-HEP-Sampler {__version__}"
    assert main(["--version", "--json"], prog="Jarvis sampler") == 0
    assert capsys.readouterr().out.strip() == f"Jarvis-HEP-Sampler {__version__}"


def test_usage_error_is_rich_or_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 2
    assert "╭" in capsys.readouterr().err
    assert main(["init", "--json"]) == 2
    raw = capsys.readouterr().out
    assert "╭" not in raw
    assert json.loads(raw)["ok"] is False


def test_init_load_list_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "MyScan.py"
    assert main(["init", "MyScan", "--output", str(target)]) == 0
    assert "jsampler load" in capsys.readouterr().out
    assert main(["check", str(target), "--dimension", "2", "--points", "8"]) == 0
    assert main(["load", str(target)], prog="Jarvis sampler") == 0
    assert "Sampling.Method: MyScan" in capsys.readouterr().out
    assert main(["list"]) == 0
    assert "MyScan" in capsys.readouterr().out
    assert main(["info", "MyScan"]) == 0
    assert main(["remove", "MyScan", "--yes"]) == 0


def test_check_card_reads_task_yaml(capsys: pytest.CaptureFixture[str]) -> None:
    plugin = ROOT / "examples" / "MyLatinHypercube.py"
    card = ROOT / "examples" / "MyLatinHypercube.task.yaml"
    report = SimpleNamespace(method="MyLatinHypercube", ok=True, rows=lambda: [])
    with patch("jarvis_hep_sampler.testing.check_plugin", return_value=report) as checker:
        assert main(["check", str(plugin), "--card", str(card)]) == 0
    kwargs = checker.call_args.kwargs
    assert kwargs["variable_names"] == ["x", "y"]
    assert kwargs["seed"] == 7
    assert kwargs["point_number"] == 32
    assert kwargs["options"] == {"centered": True}
    assert "CARD OVERRIDES" in capsys.readouterr().out


def test_json_is_plain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "MyScan.py"
    assert main(["init", "MyScan", "--output", str(target), "--json"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["ok"] is True and created["path"].endswith("MyScan.py")
    assert main(["load", str(target), "--json"]) == 0
    loaded = json.loads(capsys.readouterr().out)
    assert loaded["method"] == "MyScan"
    assert main(["--json", "list"]) == 0
    raw = capsys.readouterr().out
    assert "╭" not in raw
    assert json.loads(raw)["samplers"][0]["method"] == "MyScan"
    assert main(["info", "Missing", "--json"]) != 0
    failed = json.loads(capsys.readouterr().out)
    assert failed["ok"] is False and "Missing" in failed["error"]["message"]
