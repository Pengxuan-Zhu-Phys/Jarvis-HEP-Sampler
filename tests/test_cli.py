"""The jsampler command, which Jarvis sampler calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis_hep_sampler import __version__
from jarvis_hep_sampler.cli import main


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
