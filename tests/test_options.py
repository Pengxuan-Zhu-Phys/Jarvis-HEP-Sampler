from __future__ import annotations

import datetime as dt

import pytest

from jarvis_hep_sampler.errors import PluginConfigError, PluginLoadError
from jarvis_hep_sampler.options import (
    check_options_schema,
    freeze_options,
    parse_reserved,
    schema_issues,
    split_bounds,
    thaw_options,
)


def test_split_bounds_separates_hep_keys():
    reserved, options = split_bounds(
        {"seed": 7, "point_number": 100, "max_worker": 4, "centered": True}
    )
    assert reserved == {"seed": 7, "point_number": 100, "max_worker": 4}
    assert options == {"centered": True}
    assert split_bounds({"point_number": 5, "seed": 1}, "generational")[1] == {"point_number": 5}


def test_reserved_defaults_and_integer_strings():
    settings = parse_reserved({"point_number": "100"})
    assert (settings.seed, settings.point_number, settings.max_worker) == (0, 100, None)
    assert parse_reserved({"seed": 0, "point_number": 1}).seed == 0


@pytest.mark.parametrize(
    "reserved",
    [
        {},
        {"point_number": 0},
        {"point_number": True},
        {"point_number": 1.5},
        {"point_number": "1e3"},
        {"point_number": 10, "seed": -1},
        {"point_number": 10, "seed": False},
        {"point_number": 10, "max_worker": 0},
    ],
)
def test_bad_reserved_values(reserved):
    with pytest.raises(PluginConfigError) as info:
        parse_reserved(reserved)
    assert info.value.yaml_path.startswith("Bounds.")


def test_freeze_options_is_read_only_and_json_only():
    frozen = freeze_options({"a": [1, {"b": 2.5}], "c": None})
    assert frozen["a"][1]["b"] == 2.5
    assert isinstance(frozen["a"], tuple)
    with pytest.raises(TypeError):
        frozen["c"] = 1  # type: ignore[index]
    assert thaw_options(frozen) == {"a": [1, {"b": 2.5}], "c": None}


@pytest.mark.parametrize(
    ("options", "where"),
    [
        ({"when": dt.date(2026, 1, 1)}, "Bounds.when"),
        ({"x": float("nan")}, "Bounds.x"),
        ({"x": {1: "a"}}, "Bounds.x"),
        ({"x": [0, {"y": float("inf")}]}, "Bounds.x[1].y"),
    ],
)
def test_freeze_rejects_non_json_values(options, where):
    with pytest.raises(PluginConfigError) as info:
        freeze_options(options)
    assert info.value.yaml_path == where


def test_schema_issues_locate_the_option():
    schema = check_options_schema(
        {
            "type": "object",
            "properties": {"upper": {"type": "number", "maximum": 1}},
            "additionalProperties": False,
        }
    )
    issues = schema_issues(schema, freeze_options({"upper": 2, "uper": 1, "zzz": 0}))
    by_location = {issue.location(): issue.message for issue in issues}
    assert set(by_location) == {"Bounds.upper", "Bounds.uper", "Bounds.zzz"}
    assert by_location["Bounds.uper"] == "unknown option 'uper'; did you mean 'upper'?"
    assert by_location["Bounds.zzz"] == "unknown option 'zzz' (known options: upper)"
    assert schema_issues(None, freeze_options({"anything": 1})) == []


@pytest.mark.parametrize("schema", [{"type": "not-a-type"}, ["list"], {"x": float("nan")}])
def test_invalid_schemas_fail_at_load(schema):
    with pytest.raises(PluginLoadError):
        check_options_schema(schema)
