from __future__ import annotations

import pytest

from jarvis_hep_sampler.testing import check_plugin, run_offline

HEADER = '''
import numpy as np
PLUGIN = {"api_version": 1, "method": "BoundaryDemo", "version": "1", "profile": "independent"}
def draw(context, rng, plan):
    return [0.5] * context.dimension
'''


@pytest.mark.parametrize("body", [
    '''
def settings_rows(setup, plan):
    yield ("count", 1)
    raise RuntimeError("late rows failure")
''',
    '''
class Metrics(dict):
    def items(self):
        yield ("count", 1)
        raise RuntimeError("late metrics failure")
def status(plan, stats):
    return Metrics()
''',
    '''
def stop_reason(plan, stats):
    return np.array(["budget", "finished"])
''',
])
def test_checker_reports_hook_result_failures_and_offline_run_continues(write_plugin, body):
    path = write_plugin(HEADER + body)
    report = check_plugin(path, dimension=1, point_number=4)
    assert [item.name for item in report.failures()] == ["hooks"]
    run = run_offline(path, dimension=1, point_number=4)
    assert (run.candidates, run.accepted) == (4, 4)
    assert len(run.hook_errors) == 1


@pytest.mark.parametrize("blocked", [False, True], ids=["draw", "draw-block"])
def test_checker_reports_float64_overflow_as_output_failure(write_plugin, blocked):
    metadata = ', "block_size": 2' if blocked else ""
    function = "draw_block" if blocked else "draw"
    value = "[[10 ** 400]] * context.block_size" if blocked else "[10 ** 400]"
    path = write_plugin(f'''
PLUGIN = {{"api_version": 1, "method": "BoundaryDemo", "version": "1",
          "profile": "independent"{metadata}}}
def {function}(context, rng, plan):
    return {value}
''')
    report = check_plugin(path, dimension=1, point_number=4)
    assert [item.name for item in report.failures()] == ["draw"]
    assert "float64" in report.failures()[0].detail
    assert "method BoundaryDemo" in report.failures()[0].detail
    assert "candidate 0" in report.failures()[0].detail
