"""Regression tests for v0.6 options and stop metadata helpers."""

import importlib
import sys
import types
from datetime import timedelta
from pathlib import Path

import pytest
from types import SimpleNamespace

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"
package = sys.modules.setdefault("hslhrt", types.ModuleType("hslhrt"))
package.__path__ = [str(INTEGRATION)]

config = importlib.import_module("hslhrt.configuration")


def test_existing_single_route_preserved_without_options():
    data = {"route": "8", "destination": "ALL"}
    assert config.default_selected_routes(data, {}) == ["8"]
    assert config.effective_filters(data, {}) == ("8", "ALL", None)
    assert config.scan_interval_minutes({}) == 1


def test_existing_destination_preserved_and_override_can_select_all():
    data = {"route": "ALL", "destination": "Kamppi"}
    assert config.effective_filters(data, {}) == ("ALL", "Kamppi", None)
    choices = {"routes_filter": [], "destination_filter": "Kamppi"}
    assert config.effective_filters(data, choices) == ("all", "Kamppi", [])
    assert config.effective_filters(
        data, {"routes_filter": [], "destination_filter": "ALL"}
    ) == ("all", "ALL", [])


def test_multiple_routes_options_and_poll_interval():
    data = {"route": "8", "destination": "Kamppi"}
    opts = {
        "routes_filter": ["2", "8"],
        "destination_filter": "Espoo",
        "scan_interval": 5,
    }
    assert config.default_selected_routes(data, opts) == ["2", "8"]
    assert config.effective_filters(data, opts) == ("all", "Espoo", ["2", "8"])
    assert config.scan_interval_minutes(opts) == 5


def test_invalid_interval_options_do_not_break_coordinator():
    assert config.scan_interval_minutes({"scan_interval": -10}) == 1
    assert config.scan_interval_minutes({"scan_interval": "5"}) == 1
    assert config.scan_interval_minutes({"scan_interval": 31}) == 1
    assert config.scan_interval_minutes({"scan_interval": True}) == 1
    assert config.scan_interval_minutes({"scan_interval": 30}) == 30


def test_route_names_are_deduplicated_and_sorted():
    stop = {"patterns": [
        {"route": {"shortName": "8"}},
        {"route": {"shortName": "2"}},
        {"route": {"shortName": "8"}, "headsign": "Other"},
        {"route": None},
        {"route": {"shortName": ""}},
    ]}
    assert config.available_routes(stop) == ["2", "8"]


def test_stop_choices_disambiguate_same_names_and_skip_duplicates():
    stops = [
        {"gtfsId": "HSL:1", "name": "Kamppi", "code": "H0101"},
        {"gtfsId": "HSL:2", "name": "Kamppi", "code": "H0102"},
        {"gtfsId": "HSL:1", "name": "Kamppi", "code": "H0101"},
        {"name": "Invalid"},
        None,
    ]
    assert [stop["gtfsId"] for stop in config.stop_candidates(stops)] == [
        "HSL:1", "HSL:2"
    ]
    assert len(config.stop_candidates(stops, limit=1)) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ALL", []),
        ("all", []),
        ("", []),
        ("158", ["158"]),
        ("158, 530", ["158", "530"]),
        ("158 530", ["158", "530"]),
        ("158,530", ["158", "530"]),
        ("530 , 158   158", ["158", "530"]),
        ("  m1, M1    530 ", ["530", "M1"]),
    ],
)
def test_initial_route_input_accepts_commas_spaces_and_deduplicates(raw, expected):
    assert config.parse_route_filter(raw) == expected


@pytest.mark.parametrize("raw", ["ALL,158", "158 all", "ALL ALL", ",,", " ,  "])
def test_invalid_all_mixtures_and_empty_tokens_are_not_accepted(raw):
    with pytest.raises(ValueError):
        config.parse_route_filter(raw)


def test_canonical_routes_stabilize_identity_across_input_spelling():
    assert config.canonical_route_filter("530, 158") == "158,530"
    assert config.canonical_route_filter("158 530") == "158,530"
    assert config.canonical_route_filter("158,530,158") == "158,530"
    assert config.canonical_route_filter("all") == "ALL"


def test_legacy_multi_route_data_is_resolved_and_options_defaulted():
    data = {"route": "158,530", "destination": "ALL"}
    assert config.default_selected_routes(data, {}) == ["158", "530"]
    assert config.effective_filters(data, {}) == ("all", "ALL", ["158", "530"])
    # Explicit route selections in existing OptionsFlow override initial data.
    overrides = {"routes_filter": ["530"]}
    assert config.effective_filters(data, overrides) == (
        "all", "ALL", ["530"]
    )
    assert config.effective_filters(data, {"routes_filter": []}) == (
        "all", "ALL", []
    )
