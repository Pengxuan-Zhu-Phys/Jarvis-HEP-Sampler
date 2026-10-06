"""Read-only contexts passed to plug-in functions (technical design §4.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from jarvis_hep_sampler.log import SamplerLog
from jarvis_hep_sampler.streams import prepare_stream


@dataclass(frozen=True)
class SetupContext:
    """Argument of ``prepare(setup)`` and of the settings hook."""

    seed: int
    point_number: int
    dimension: int
    variable_names: tuple[str, ...]
    options: Mapping[str, Any]
    log: SamplerLog

    def rng(self) -> np.random.Generator:
        """A fresh generator on the stream reserved for ``prepare``."""
        return prepare_stream(self.seed)


@dataclass(frozen=True)
class DrawContext:
    """First argument of ``draw(context, rng, plan)``."""

    candidate_index: int
    point_number: int
    dimension: int
    variable_names: tuple[str, ...]
    options: Mapping[str, Any]
    log: SamplerLog


@dataclass(frozen=True)
class BlockContext:
    """First argument of ``draw_block(context, rng, plan)``.

    The block covers candidate indices
    ``[block_index * block_size, (block_index + 1) * block_size)``.
    """

    block_index: int
    block_size: int
    point_number: int
    dimension: int
    variable_names: tuple[str, ...]
    options: Mapping[str, Any]
    log: SamplerLog


@dataclass(frozen=True)
class SamplerStats:
    """Read-only counters passed to the summary, stop-reason and status hooks."""

    candidates: int
    accepted: int
    point_number: int


__all__ = ["BlockContext", "DrawContext", "SamplerStats", "SetupContext"]
