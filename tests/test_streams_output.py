from __future__ import annotations

import numpy as np
import pytest

from jarvis_hep_sampler.errors import PluginOutputError
from jarvis_hep_sampler.output import check_block, check_point
from jarvis_hep_sampler.streams import (
    block_stream,
    candidate_stream,
    generation_stream,
    prepare_stream,
    stream,
)


def test_streams_are_deterministic_and_seed_zero_is_valid():
    assert np.array_equal(candidate_stream(0, 5).random(4), candidate_stream(0, 5).random(4))
    assert not np.array_equal(candidate_stream(0, 5).random(4), candidate_stream(0, 6).random(4))
    assert not np.array_equal(candidate_stream(0, 5).random(4), candidate_stream(1, 5).random(4))


def test_stream_domains_are_separate():
    draws = {
        "prepare": prepare_stream(7).random(),
        "candidate": candidate_stream(7, 0).random(),
        "block": block_stream(7, 0).random(),
        "generation": generation_stream(7, 0).random(),
    }
    assert len(set(draws.values())) == 4


def test_stream_uses_explicit_pcg64():
    assert isinstance(stream(3, 1).bit_generator, np.random.PCG64)


@pytest.mark.parametrize("seed", [-1, True, 1.5, "3"])
def test_bad_seeds_are_rejected(seed):
    with pytest.raises(ValueError):
        stream(seed)


@pytest.mark.parametrize(
    "value",
    [
        [0.0, 1.0],
        (0, 1),
        np.array([0.25, 0.75]),
        np.array([0, 1], dtype=np.int64),
        [np.float32(0.5), 1],
    ],
)
def test_valid_points_include_both_ends(value):
    point = check_point(value, dimension=2, candidate_index=3)
    assert point.dtype == np.float64
    assert point.flags["C_CONTIGUOUS"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([[0.1, 0.2]], "shape"),
        ([0.1], "shape"),
        ([True, 0.5], "expected real numbers"),
        (np.array([True, False]), "dtype bool"),
        ([0.1 + 0j, 0.2], "expected real numbers"),
        (["0.1", 0.2], "expected real numbers"),
        ([float("nan"), 0.2], "not finite"),
        ([float("inf"), 0.2], "not finite"),
        ([-0.1, 0.2], "outside"),
        ([0.5, 1.0000001], "outside"),
        ({"a": 1}, "numpy array, list or tuple"),
    ],
)
def test_invalid_points(value, message):
    with pytest.raises(PluginOutputError, match=message) as info:
        check_point(value, dimension=2, candidate_index=9, variable_names=("m", "g"), method="M")
    assert info.value.candidate_index == 9
    assert info.value.method == "M"


def test_error_names_the_variable():
    with pytest.raises(PluginOutputError, match=r"component 1 \(coupling\)"):
        check_point([0.5, 2.0], dimension=2, variable_names=("mass", "coupling"))


def test_block_checks_only_rows_in_budget():
    block = np.full((4, 2), 0.5)
    block[3] = np.nan  # beyond point_number: discarded, not checked
    rows = check_block(block, block_size=4, dimension=2, block_index=2, valid_rows=3)
    assert rows.shape == (3, 2)
    block[1, 0] = 7.0
    with pytest.raises(PluginOutputError, match="outside") as info:
        check_block(block, block_size=4, dimension=2, block_index=2, valid_rows=3)
    assert info.value.candidate_index == 9


def test_block_shape_must_match_exactly():
    with pytest.raises(PluginOutputError, match="shape"):
        check_block(np.zeros((3, 2)), block_size=4, dimension=2, block_index=0)


def test_point_float64_overflow_keeps_output_error_context():
    with pytest.raises(PluginOutputError, match="float64") as info:
        check_point([10 ** 400], dimension=1, candidate_index=7, method="Demo")
    assert isinstance(info.value.__cause__, OverflowError)
    assert info.value.method == "Demo"
    assert info.value.candidate_index == 7


def test_block_float64_overflow_keeps_output_error_context():
    with pytest.raises(PluginOutputError, match="float64") as info:
        check_block([[0.5], [10 ** 400]], block_size=2, dimension=1, block_index=3, method="Demo")
    assert isinstance(info.value.__cause__, OverflowError)
    assert info.value.method == "Demo"
    assert info.value.candidate_index == 6
