from __future__ import annotations

import re
from pathlib import Path

import jarvis_hep_sampler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "jarvis_hep_sampler"


def test_versions_match():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'(?m)^version\s*=\s*"([^"]+)"$', pyproject).group(1)
    assert jarvis_hep_sampler.__version__ == version


def test_public_names_resolve():
    lazy = set(jarvis_hep_sampler._LAZY_ATTRS)
    assert set(jarvis_hep_sampler.__all__) == lazy | {"__version__"}
    for name in jarvis_hep_sampler.__all__:
        assert getattr(jarvis_hep_sampler, name) is not None
    assert "SamplerRegistry" in dir(jarvis_hep_sampler)


def test_sdk_never_imports_jarvis_hep_or_redis():
    pattern = re.compile(r"^\s*(?:from|import)\s+(jarvishep2?|redis|jarvis_portal)\b", re.M)
    offenders = [
        path.name for path in SOURCE.rglob("*.py") if pattern.search(path.read_text("utf-8"))
    ]
    assert offenders == []


def test_template_ships_as_package_data():
    assert (SOURCE / "templates" / "independent.py.tmpl").is_file()
    assert (SOURCE / "py.typed").is_file()
