from __future__ import annotations

import ast
import logging
from pathlib import Path

import numpy as np
import pytest

from jarvis_hep_sampler.errors import PluginLoadError
from jarvis_hep_sampler.log import SamplerLog, format_table
from jarvis_hep_sampler.template import render_template, write_template
from jarvis_hep_sampler.testing import (
    assert_conforms,
    check_plugin,
    reference_stream,
    run_offline,
)

from .conftest import EXAMPLES


def test_template_renders_valid_python():
    text = render_template("MySampler")
    ast.parse(text)
    assert '"method": "MySampler"' in text
    assert "__METHOD__" not in text


def test_template_checks_the_name():
    with pytest.raises(PluginLoadError):
        render_template("my_sampler")
    with pytest.raises(PluginLoadError, match="built-in"):
        render_template("Grid", reserved_names=["Grid"])
    with pytest.raises(PluginLoadError, match="no template"):
        render_template("MySampler", profile="generational")


def test_write_template_never_overwrites(tmp_path):
    path = write_template("MySampler", tmp_path)
    assert path == tmp_path / "MySampler.py"
    with pytest.raises(FileExistsError, match="already exists"):
        write_template("MySampler", tmp_path)
    assert write_template("Other", tmp_path / "sub" / "o.py").exists()


def test_generated_template_conforms(tmp_path):
    path = write_template("MySampler", tmp_path)
    report = assert_conforms(path, dimension=3, options={"upper": 0.25})
    assert report.method == "MySampler"
    run = run_offline(path, dimension=3, point_number=50, options={"upper": 0.25})
    assert run.points.max() <= 0.25


@pytest.mark.parametrize("centered", [False, True])
def test_latin_hypercube_example(centered):
    run = run_offline(
        EXAMPLES / "LatinHypercube.py",
        variable_names=["mass", "coupling", "mixing"],
        point_number=200,
        seed=7,
        options={"centered": centered},
    )
    strata = np.floor(run.points * 200).astype(int)
    for column in strata.T:
        assert sorted(column) == list(range(200))
    assert run.settings_rows == [("centered", centered)]
    assert run.stop_reason == "point_number reached"
    assert_conforms(EXAMPLES / "LatinHypercube.py", dimension=2, options={"centered": centered})


def test_reference_stream_with_selection_and_resume(uniform_plugin):
    def keep(u: np.ndarray) -> bool:
        return bool(u[0] < 0.5)

    full = list(
        reference_stream(uniform_plugin, point_number=40, seed=2, dimension=2, selection=keep)
    )
    assert [p.accepted_index for p in full] == list(range(len(full)))
    assert all(p.u[0] < 0.5 for p in full)
    cut = full[len(full) // 2]
    tail = list(
        reference_stream(
            uniform_plugin,
            point_number=40,
            seed=2,
            dimension=2,
            selection=keep,
            start_candidate=cut.candidate_index,
            start_accepted=cut.accepted_index,
        )
    )
    expected = full[len(full) // 2 :]
    assert [(p.candidate_index, p.accepted_index) for p in tail] == [
        (p.candidate_index, p.accepted_index) for p in expected
    ]
    assert all(np.array_equal(a.u, b.u) for a, b in zip(tail, expected, strict=True))


def test_selection_rejecting_everything_ends_normally(uniform_plugin):
    run = run_offline(uniform_plugin, point_number=25, dimension=1, selection=lambda u: False)
    assert (run.candidates, run.accepted) == (25, 0)
    assert run.points.shape == (0, 1)
    assert run.stop_reason == "point_number reached"


def test_check_reports_failures_without_raising(write_plugin):
    bad = write_plugin(
        """
PLUGIN = {"api_version": 1, "method": "Bad", "version": "1", "profile": "independent"}

def draw(context, rng, plan):
    return [2.0] * context.dimension
""",
        "Bad.py",
    )
    report = check_plugin(bad, dimension=2)
    assert not report.ok
    assert report.failures()[0].name == "draw"
    assert "outside [0, 1]" in report.failures()[0].detail
    with pytest.raises(AssertionError, match="does not conform"):
        assert_conforms(bad, dimension=2)


def test_check_catches_hidden_state(write_plugin):
    stateful = write_plugin(
        """
import numpy as np

PLUGIN = {"api_version": 1, "method": "Stateful", "version": "1", "profile": "independent"}
_GLOBAL = np.random.default_rng()

def draw(context, rng, plan):
    return _GLOBAL.random(context.dimension)
""",
        "Stateful.py",
    )
    report = check_plugin(stateful, dimension=2)
    assert [item.name for item in report.failures()] == ["repeatability"]


def test_check_reports_load_errors(tmp_path: Path):
    report = check_plugin(tmp_path / "missing.py", dimension=1)
    assert [item.name for item in report.items] == ["load"]
    assert not report.ok


def test_check_blocked_plugin(blocked_plugin):
    report = assert_conforms(blocked_plugin, dimension=2, point_number=10)
    assert "block_size 4" in report.items[0].detail


def test_log_facade(caplog):
    log = SamplerLog("Demo")
    with caplog.at_level(logging.DEBUG, logger="jarvis_hep_sampler.Demo"):
        log.step("Demo Step ->", [("generation", 3), ("accepted", "40%")])
        log.adjust("scale", 0.1, 0.05, "acceptance too low")
        log.saved("Chain file", "/tmp/chain.csv")
        log.info("value %d", 5)
    messages = [record.getMessage() for record in caplog.records]
    assert messages[0].splitlines()[0] == "Demo Step ->"
    assert "generation | 3" in messages[0]
    assert messages[1] == "scale: 0.1 -> 0.05 (acceptance too low)"
    assert messages[2] == "Chain file saved to /tmp/chain.csv"
    assert messages[3] == "value 5"
    assert [record.levelno for record in caplog.records] == [
        logging.INFO,
        logging.WARNING,
        logging.WARNING,
        logging.INFO,
    ]


def test_log_facade_uses_the_given_backend():
    calls = []

    class Backend:
        def emit(self, level, message):
            calls.append(("emit", level, message))

        def emit_table(self, level, title, rows):
            calls.append(("table", level, title, list(rows)))

    log = SamplerLog("Demo", Backend())
    log.step("T", [("a", 1)])
    log.warning("w")
    assert calls == [("table", logging.INFO, "T", [("a", 1)]), ("emit", logging.WARNING, "w")]


def test_format_table_matches_the_jarvis_layout():
    assert format_table("Title ->", [("key", 1), ("longer key", "v")]).splitlines() == [
        "Title ->",
        "Field      | Value",
        "---------- | -----",
        "key        | 1",
        "longer key | v",
    ]
