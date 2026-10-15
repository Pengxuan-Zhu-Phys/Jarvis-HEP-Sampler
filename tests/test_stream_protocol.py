"""Pinned raw PCG64 vectors for stream protocol 1.

These values were recorded from the reviewed 0.1.0 implementation. Comparing
against literals catches an accidental change even when both sides of an
offline/native replay would otherwise use the same changed stream function.
"""

from __future__ import annotations

import pytest

from jarvis_hep_sampler.streams import (
    STREAM_PROTOCOL,
    block_stream,
    candidate_stream,
    generation_stream,
    prepare_stream,
)


@pytest.mark.parametrize(
    ("factory", "args", "expected"),
    [
        (prepare_stream, (7,), [
            10880027834572141776, 9343578914191250935,
            14147486210259354237, 3441786370434220632,
        ]),
        (candidate_stream, (7, 0), [
            3387299006101535565, 10532303420069247545,
            15627726090825445423, 6809262229629655794,
        ]),
        (candidate_stream, (7, 17), [
            10289200672643891176, 14266539031475836674,
            5900413877810560826, 16648284419060306744,
        ]),
        (block_stream, (7, 3), [
            10055757297791638425, 9491665633288771667,
            17242445273188289523, 16950619466999154455,
        ]),
        (generation_stream, (7, 2), [
            3672745802703101566, 6259394118081268551,
            11544664423816374817, 15859290509749916635,
        ]),
    ],
    ids=["prepare", "candidate-zero", "candidate-seventeen", "block", "generation"],
)
def test_protocol_one_raw_vectors(factory, args, expected):
    assert STREAM_PROTOCOL == 1
    assert factory(*args).bit_generator.random_raw(4).tolist() == expected
