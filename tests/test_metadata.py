from __future__ import annotations

import pytest

from jarvis_hep_sampler.errors import PluginLoadError
from jarvis_hep_sampler.metadata import check_method_name, parse_metadata
from jarvis_hep_sampler.template import render_template

BASE = {"api_version": 1, "method": "LatinHypercube", "version": "0.1.0", "profile": "independent"}


def meta(**changes):
    data = dict(BASE)
    for key, value in changes.items():
        if value is ...:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def test_minimal_metadata_defaults():
    parsed = parse_metadata(BASE)
    assert parsed.method == "LatinHypercube"
    assert parsed.description == ""
    assert parsed.statistical is False
    assert parsed.block_size is None
    assert parsed.to_dict() == {**BASE, "description": "", "statistical": False}


@pytest.mark.parametrize("name", ["Random", "AdaptiveBridson", "MCMC", "PTEnsemble", "X1"])
def test_builtin_shaped_names_are_valid(name):
    assert check_method_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "latin", "L", "Latin-Hypercube", "Latin Hypercube", "lab:lhs", "", 3, None,
        "A" * 65, "Demo\n",
    ],
)
def test_bad_method_names(name):
    with pytest.raises(PluginLoadError):
        check_method_name(name)


def test_template_rejects_a_method_with_a_trailing_newline():
    with pytest.raises(PluginLoadError, match="2-64 letters or digits"):
        render_template("Demo\n")


def test_builtin_names_are_reserved_whatever_the_case():
    with pytest.raises(PluginLoadError, match="built-in"):
        check_method_name("RANDOM", reserved_names=["Random"])


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"method": ...}, "missing"),
        ({"blocksize": 4}, "unknown key"),
        ({"api_version": 2}, "API version 1"),
        ({"api_version": True}, "integer"),
        ({"version": " "}, "non-empty"),
        ({"profile": "mcmc"}, "profile"),
        ({"statistical": "yes"}, "true or false"),
        ({"block_size": 0}, "positive integer"),
        ({"block_size": True}, "positive integer"),
        ({"state_version": 1}, "generational"),
        ({"feedback_return": {"mode": "minimal"}}, "generational"),
        ({"description": float("nan")}, "JSON"),
    ],
)
def test_invalid_metadata(changes, message):
    with pytest.raises(PluginLoadError, match=message):
        parse_metadata(meta(**changes))


def test_generational_needs_state_version_and_checks_feedback_return():
    with pytest.raises(PluginLoadError, match="state_version"):
        parse_metadata(meta(profile="generational"))
    feedback = {"mode": "fields", "fields": ["x"]}
    parsed = parse_metadata(meta(profile="generational", state_version=1, feedback_return=feedback))
    assert parsed.feedback_return == {"mode": "fields", "fields": ["x"], "include_logl": True}
    with pytest.raises(PluginLoadError, match="mode"):
        parse_metadata(
            meta(profile="generational", state_version=1, feedback_return={"mode": "all"})
        )


def test_metadata_must_be_a_dict():
    with pytest.raises(PluginLoadError, match="dict"):
        parse_metadata(["not", "a", "dict"])
