"""Deterministic random streams (technical design §7.1).

Every stream is derived from ``Bounds.seed`` plus a fixed key, through an
explicit PCG64 generator. A point therefore depends only on the seed and its
index, never on worker count, batch size or completion order. Reproduction is
guaranteed within one Python/NumPy environment.
"""

from __future__ import annotations

import numpy as np

STREAM_PROTOCOL = 1

_PREPARE = 0
_CANDIDATE = 1
_BLOCK = 2
_GENERATION = 3


def _non_negative(name: str, value: object) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    return int(value)


def stream(seed: int, *key: int) -> np.random.Generator:
    """Return the generator for ``(seed, *key)`` under the current stream protocol."""
    root = _non_negative("seed", seed)
    parts = tuple(_non_negative("stream key", item) for item in key)
    sequence = np.random.SeedSequence(root, spawn_key=(STREAM_PROTOCOL, *parts))
    return np.random.Generator(np.random.PCG64(sequence))


def prepare_stream(seed: int) -> np.random.Generator:
    """Stream handed to ``prepare`` through ``SetupContext.rng()``."""
    return stream(seed, _PREPARE)


def candidate_stream(seed: int, candidate_index: int) -> np.random.Generator:
    """Stream for ``draw`` at one candidate index."""
    return stream(seed, _CANDIDATE, candidate_index)


def block_stream(seed: int, block_index: int) -> np.random.Generator:
    """Stream for ``draw_block`` at one block index."""
    return stream(seed, _BLOCK, block_index)


def generation_stream(seed: int, generation: int) -> np.random.Generator:
    """Stream for one generation of a generational plug-in (S3)."""
    return stream(seed, _GENERATION, generation)


__all__ = [
    "STREAM_PROTOCOL",
    "block_stream",
    "candidate_stream",
    "generation_stream",
    "prepare_stream",
    "stream",
]
