"""Validate the complete installed SDK wheel with no source-path imports."""

import importlib.metadata as metadata
import os
import sys
import tempfile
from pathlib import Path

import jarvis_hep_sampler
from jarvis_hep_sampler import SamplerRegistry, write_template
from jarvis_hep_sampler.testing import check_plugin

expected = sys.argv[1]
assert metadata.version("Jarvis-HEP-Sampler") == jarvis_hep_sampler.__version__ == expected
assert Path(jarvis_hep_sampler.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
with tempfile.TemporaryDirectory() as tmp:
    os.environ["JARVIS_SAMPLERS_HOME"] = str(Path(tmp) / "registry")
    source = write_template("ReleaseSmoke", tmp)
    report = check_plugin(source, dimension=2)
    assert report.ok, report.rows()
    registry = SamplerRegistry()
    entry = registry.load(source).entry
    assert registry.load_snapshot(entry.method).source_sha256 == entry.source_sha256
print("Complete installed SDK, template, restarted checker and registry smoke passed.")
