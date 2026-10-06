from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never touch the real ~/.jarvis/samplers."""
    home = tmp_path / "samplers-home"
    monkeypatch.setenv("JARVIS_SAMPLERS_HOME", str(home))
    return home


@pytest.fixture
def write_plugin(tmp_path: Path) -> Callable[..., Path]:
    """Write a plug-in file from source text (dedented) and return its path."""

    def _write(source: str, name: str = "plugin.py", directory: Path | None = None) -> Path:
        folder = directory or tmp_path
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    return _write


UNIFORM = """
PLUGIN = {
    "api_version": 1,
    "method": "Uniform",
    "version": "1.0",
    "profile": "independent",
}


def draw(context, rng, plan):
    return rng.random(context.dimension)
"""


BLOCKED = """
import numpy as np

PLUGIN = {
    "api_version": 1,
    "method": "Blocked",
    "version": "1.0",
    "profile": "independent",
    "block_size": 4,
}


def draw_block(context, rng, plan):
    return rng.random((context.block_size, context.dimension))
"""


@pytest.fixture
def uniform_plugin(write_plugin: Callable[..., Path]) -> Path:
    return write_plugin(UNIFORM, "Uniform.py")


@pytest.fixture
def blocked_plugin(write_plugin: Callable[..., Path]) -> Path:
    return write_plugin(BLOCKED, "Blocked.py")
