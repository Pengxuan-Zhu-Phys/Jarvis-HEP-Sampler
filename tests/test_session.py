from __future__ import annotations

import logging

import numpy as np
import pytest

from jarvis_hep_sampler.errors import PluginConfigError, PluginOutputError
from jarvis_hep_sampler.loader import load_plugin_file
from jarvis_hep_sampler.session import IndependentSession

HEADER = """
import numpy as np

PLUGIN = {"api_version": 1, "method": "Demo", "version": "1", "profile": "independent"%s}
"""


def make(write_plugin, body: str, extra: str = "", **kwargs):
    plugin = load_plugin_file(write_plugin(HEADER % extra + body))
    options = kwargs.pop("options", None)
    session = IndependentSession(
        plugin,
        seed=kwargs.pop("seed", 3),
        point_number=kwargs.pop("point_number", 10),
        variable_names=kwargs.pop("variable_names", ("a", "b")),
        options=options,
    )
    return session


def test_repeated_hook_errors_are_bounded_and_logged_once(write_plugin, caplog):
    session = make(write_plugin, '''
def draw(context, rng, plan):
    return rng.random(context.dimension)
def status(plan, stats):
    raise ValueError(str(stats.candidates) + "x" * 10000)
''')
    session.prepare()
    with caplog.at_level(logging.WARNING):
        for candidate in range(1000):
            assert session.status(session.stats(candidate, 0)) == {}
    assert len(session.hook_errors) == 1
    assert len(session.hook_errors[0]) <= 512
    assert len([r for r in caplog.records if "could not report status" in r.message]) == 1


def test_prepare_runs_once_and_plan_reaches_draw(write_plugin):
    body = """
CALLS = []

def prepare(setup):
    CALLS.append(setup.point_number)
    return {"scale": 0.5, "names": setup.variable_names}

def draw(context, rng, plan):
    assert context.variable_names == plan["names"]
    return rng.random(context.dimension) * plan["scale"]
"""
    session = make(write_plugin, body)
    session.prepare()
    points = np.array([u for _, u in session.points()])
    assert points.shape == (10, 2) and points.max() <= 0.5
    assert session.plugin.module.CALLS == [10]


def test_point_requires_prepare_and_index_in_budget(uniform_plugin):
    session = IndependentSession(
        load_plugin_file(uniform_plugin), seed=0, point_number=3, variable_names=["x"]
    )
    with pytest.raises(RuntimeError):
        session.point(0)
    session.prepare()
    with pytest.raises(IndexError):
        session.point(3)


def test_points_depend_only_on_seed_and_index(uniform_plugin):
    plugin = load_plugin_file(uniform_plugin)
    a = IndependentSession(plugin, seed=1, point_number=20, variable_names=["x", "y"])
    b = IndependentSession(plugin, seed=1, point_number=20, variable_names=["x", "y"])
    a.prepare()
    b.prepare()
    forward = [a.point(i) for i in range(20)]
    backward = [b.point(i) for i in reversed(range(20))][::-1]
    assert all(np.array_equal(x, y) for x, y in zip(forward, backward, strict=True))


def test_schema_and_validate_options_run_in_prepare(write_plugin):
    body = """
OPTIONS_SCHEMA = {"type": "object", "properties": {"k": {"type": "integer"}}}

def validate_options(options):
    if options.get("k", 0) > 5:
        raise ValueError("k too large")

def draw(context, rng, plan):
    return rng.random(context.dimension)
"""
    with pytest.raises(PluginConfigError, match="Bounds.k") as info:
        make(write_plugin, body, options={"k": "x"}).prepare()
    assert info.value.yaml_path == "Bounds.k"
    with pytest.raises(PluginConfigError, match="k too large") as info:
        make(write_plugin, body, options={"k": 9}).prepare()
    assert isinstance(info.value.__cause__, ValueError)
    make(write_plugin, body, options={"k": 2}).prepare()


def test_prepare_failure_is_a_config_error(write_plugin):
    body = """
def prepare(setup):
    raise KeyError("missing table")

def draw(context, rng, plan):
    return rng.random(context.dimension)
"""
    with pytest.raises(PluginConfigError, match="prepare\\(\\) failed: KeyError"):
        make(write_plugin, body).prepare()


def test_draw_exception_and_bad_output_carry_the_candidate(write_plugin):
    body = """
def draw(context, rng, plan):
    if context.candidate_index == 4:
        raise ZeroDivisionError("bad")
    if context.candidate_index == 6:
        return [0.5, float("nan")]
    return rng.random(context.dimension)
"""
    session = make(write_plugin, body)
    session.prepare()
    with pytest.raises(PluginOutputError, match="ZeroDivisionError") as info:
        session.point(4)
    assert info.value.candidate_index == 4
    with pytest.raises(PluginOutputError, match="not finite") as info:
        session.point(6)
    assert info.value.candidate_index == 6


def test_options_are_read_only_inside_the_plugin(write_plugin):
    body = """
def prepare(setup):
    setup.options["x"] = 1

def draw(context, rng, plan):
    return rng.random(context.dimension)
"""
    with pytest.raises(PluginConfigError, match="TypeError"):
        make(write_plugin, body, options={"x": 0}).prepare()


def test_blocks_are_cut_at_point_number_and_cold_start_matches(blocked_plugin):
    plugin = load_plugin_file(blocked_plugin)
    full = IndependentSession(plugin, seed=5, point_number=10, variable_names=["a", "b"])
    full.prepare()
    stream = np.array([u for _, u in full.points()])
    assert stream.shape == (10, 2)
    cold = IndependentSession(plugin, seed=5, point_number=10, variable_names=["a", "b"])
    cold.prepare()
    assert np.array_equal(cold.point(9), stream[9])
    assert np.array_equal(cold.point(5), stream[5])


def test_from_bounds_uses_reserved_keys(uniform_plugin):
    session = IndependentSession.from_bounds(
        load_plugin_file(uniform_plugin),
        {"seed": "4", "point_number": 7, "extra": [1, 2]},
        variable_names=["x"],
    )
    assert (session.seed, session.point_number) == (4, 7)
    assert session.options == {"extra": (1, 2)}


def test_no_variables_is_rejected(uniform_plugin):
    with pytest.raises(PluginConfigError, match="at least one variable"):
        IndependentSession(
            load_plugin_file(uniform_plugin), seed=0, point_number=1, variable_names=[]
        )


def test_hooks_and_their_failures(write_plugin, caplog):
    body = """
def draw(context, rng, plan):
    return rng.random(context.dimension)

def settings_rows(setup, plan):
    return [("mode", "fast")]

def summary_rows(plan, stats):
    raise RuntimeError("summary broke")

def status(plan, stats):
    return {"a": 1, "b": 2.5, "nan": float("nan"), "obj": object(), "long": "x" * 99,
            **{f"k{i}": i for i in range(10)}}
"""
    session = make(write_plugin, body)
    session.prepare()
    stats = session.stats(candidates=10, accepted=8)
    assert session.settings_rows() == [("mode", "fast")]
    with caplog.at_level(logging.WARNING):
        assert session.summary_rows(stats) == []
    assert "summary broke" in caplog.text
    assert session.hook_errors and "summary_rows" in session.hook_errors[0]
    metrics = session.status(stats)
    assert len(metrics) == 8
    assert "nan" not in metrics and "obj" not in metrics
    assert metrics["long"] == "x" * 32
    assert session.stop_reason(stats) == "point_number reached"
    assert session.stop_reason(session.stats(candidates=3, accepted=3)) is None


@pytest.mark.parametrize(
    ("hook", "body", "detail"),
    [
        ("settings_rows", '''
def settings_rows(setup, plan):
    yield ("count", 1)
    raise RuntimeError("rows iteration failed")
''', "rows iteration failed"),
        ("summary_rows", '''
class BadLabel:
    def __str__(self):
        raise RuntimeError("row label failed")
def summary_rows(plan, stats):
    return [(BadLabel(), 1)]
''', "row label failed"),
        ("status", '''
class Metrics(dict):
    def items(self):
        yield ("count", 1)
        raise RuntimeError("metrics iteration failed")
def status(plan, stats):
    return Metrics()
''', "metrics iteration failed"),
        ("status", '''
class BadLabel:
    def __str__(self):
        raise RuntimeError("metric label failed")
def status(plan, stats):
    return {BadLabel(): 1}
''', "metric label failed"),
        ("stop_reason", '''
def stop_reason(plan, stats):
    return np.array(["budget", "finished"])
''', "ValueError"),
        ("stop_reason", '''
class BadReason:
    def __str__(self):
        raise RuntimeError("reason text failed")
def stop_reason(plan, stats):
    return BadReason()
''', "reason text failed"),
    ],
    ids=["lazy-rows", "row-label", "lazy-metrics", "metric-label", "reason-truth", "reason-text"],
)
def test_reporting_result_errors_are_isolated(write_plugin, caplog, hook, body, detail):
    session = make(write_plugin, '''
def draw(context, rng, plan):
    return [0.5] * context.dimension
''' + body)
    session.prepare()
    stats = session.stats(candidates=3, accepted=2)

    def report():
        if hook == "settings_rows":
            return session.settings_rows()
        return getattr(session, hook)(stats)

    expected = {} if hook == "status" else None if hook == "stop_reason" else []
    with caplog.at_level(logging.WARNING):
        assert report() == expected
        assert report() == expected
    assert len(session.hook_errors) == 1
    assert hook in session.hook_errors[0] and detail in session.hook_errors[0]
    assert len([record for record in caplog.records if "could not report" in record.message]) == 1
    assert np.array_equal(session.point(0), [0.5, 0.5])
    if hook == "stop_reason":
        finished = session.stats(candidates=10, accepted=2)
        assert session.stop_reason(finished) == "point_number reached"


def test_hook_exception_with_broken_text_still_reports_failure(write_plugin):
    session = make(write_plugin, '''
class Unprintable(RuntimeError):
    def __str__(self):
        raise ValueError("text failed")
def status(plan, stats):
    raise Unprintable()
def draw(context, rng, plan):
    return [0.5] * context.dimension
''')
    session.prepare()
    assert session.status(session.stats(0, 0)) == {}
    assert len(session.hook_errors) == 1
    assert "Unprintable: <exception text unavailable>" in session.hook_errors[0]


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_reporting_iteration_preserves_control_flow_exceptions(write_plugin, exception):
    session = make(write_plugin, f'''
def settings_rows(setup, plan):
    yield ("count", 1)
    raise {exception.__name__}("stop")
def draw(context, rng, plan):
    return [0.5] * context.dimension
''')
    session.prepare()
    with pytest.raises(exception, match="stop"):
        session.settings_rows()
    assert session.hook_errors == []


def test_status_normalizes_numpy_scalars_and_keeps_scalar_limits(write_plugin):
    session = make(write_plugin, '''
def status(plan, stats):
    return {"count": np.int64(4), "unsigned": np.uint32(5), "scale": np.float32(.25),
            "ready": np.bool_(True), "label": np.str_("x" * 99),
            "nan": np.float32("nan"), "inf": np.float64("inf"),
            "complex": np.complex64(1j), "array": np.array(.5),
            "date": np.datetime64("2026-10-15")}
def draw(context, rng, plan):
    return [0.5] * context.dimension
''')
    session.prepare()
    metrics = session.status(session.stats(0, 0))
    assert metrics == {"count": 4, "unsigned": 5, "scale": .25, "ready": True, "label": "x" * 32}
    assert [type(value) for value in metrics.values()] == [int, int, float, bool, str]
    assert session.hook_errors == []
