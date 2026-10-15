"""The jsampler command. It only sees samplers loaded by this package."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis_hep_sampler import __version__
from jarvis_hep_sampler.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["-v"]) == 0
    assert capsys.readouterr().out.strip() == f"Jarvis-HEP-Sampler {__version__}"
    assert main(["--version"], prog="Jarvis sampler") == 0
    assert capsys.readouterr().out.strip() == f"Jarvis-HEP-Sampler {__version__}"


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
    assert "card overrides" in capsys.readouterr().out
