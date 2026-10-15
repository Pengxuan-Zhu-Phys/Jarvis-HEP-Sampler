"""Checks applied to every point a plug-in returns (technical design §4.4).

A point must be real numbers of the exact expected shape, finite, and inside
the closed unit interval. Nothing is clipped or redrawn: a bad point stops
the scan with the candidate index and the offending component.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from jarvis_hep_sampler.errors import PluginOutputError

_REAL_KINDS = frozenset("iuf")


def _check_elements(values: Sequence[object], fail) -> None:
    for item in values:
        if isinstance(item, np.ndarray):
            if item.dtype.kind not in _REAL_KINDS:
                raise fail(f"contains an array of dtype {item.dtype}; expected real numbers")
            continue
        if isinstance(item, (list, tuple)):
            _check_elements(item, fail)
            continue
        if isinstance(item, (bool, np.bool_)) or not isinstance(
            item, (int, float, np.integer, np.floating)
        ):
            raise fail(f"contains {item!r} ({type(item).__name__}); expected real numbers")


def _as_float_array(value: object, fail) -> np.ndarray:
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in _REAL_KINDS:
            raise fail(f"has dtype {value.dtype}; expected real numbers")
    elif isinstance(value, (list, tuple)):
        _check_elements(value, fail)
    else:
        raise fail(f"must be a numpy array, list or tuple, got {type(value).__name__}")
    try:
        return np.array(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise fail(f"cannot convert to a regular float64 array: {exc}") from exc


def _component(index: int, variable_names: Sequence[str]) -> str:
    if 0 <= index < len(variable_names):
        return f"component {index} ({variable_names[index]})"
    return f"component {index}"


def _check_values(
    values: np.ndarray,
    *,
    first_candidate: int,
    variable_names: Sequence[str],
    method: str | None,
) -> None:
    bad = ~np.isfinite(values) | (values < 0.0) | (values > 1.0)
    if not bad.any():
        return
    if values.ndim == 1:
        row, column = 0, int(np.flatnonzero(bad)[0])
        value = float(values[column])
    else:
        row, column = (int(item) for item in np.argwhere(bad)[0])
        value = float(values[row, column])
    reason = "is not finite" if not np.isfinite(value) else "is outside [0, 1]"
    raise PluginOutputError(
        f"{_component(column, variable_names)} = {value!r} {reason}",
        method=method,
        candidate_index=first_candidate + row,
    )


def check_point(
    value: object,
    *,
    dimension: int,
    candidate_index: int | None = None,
    variable_names: Sequence[str] = (),
    method: str | None = None,
) -> np.ndarray:
    """Return *value* from ``draw`` as a contiguous float64 vector, or raise."""

    def fail(message: str) -> PluginOutputError:
        return PluginOutputError(
            f"draw() output {message}", method=method, candidate_index=candidate_index
        )

    point = _as_float_array(value, fail)
    if point.shape != (dimension,):
        raise fail(f"has shape {point.shape}; expected ({dimension},)")
    _check_values(
        point,
        first_candidate=candidate_index or 0,
        variable_names=variable_names,
        method=method,
    )
    return np.ascontiguousarray(point)


def check_block(
    value: object,
    *,
    block_size: int,
    dimension: int,
    block_index: int,
    valid_rows: int | None = None,
    variable_names: Sequence[str] = (),
    method: str | None = None,
) -> np.ndarray:
    """Return the used rows of a ``draw_block`` result as float64, or raise.

    The block must have shape ``(block_size, dimension)``. Only the first
    *valid_rows* rows (those inside ``point_number``) are checked and kept;
    the rest are discarded.
    """
    first = block_index * block_size

    def fail(message: str) -> PluginOutputError:
        return PluginOutputError(
            f"draw_block() output for block {block_index} {message}",
            method=method,
            candidate_index=first,
        )

    block = _as_float_array(value, fail)
    if block.shape != (block_size, dimension):
        raise fail(f"has shape {block.shape}; expected ({block_size}, {dimension})")
    rows = block_size if valid_rows is None else max(0, min(block_size, int(valid_rows)))
    used = np.ascontiguousarray(block[:rows])
    _check_values(used, first_candidate=first, variable_names=variable_names, method=method)
    return used


__all__ = ["check_block", "check_point"]
