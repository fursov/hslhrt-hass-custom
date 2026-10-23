"""Unit tests for schedule parsing (without a Home Assistant installation)."""

import importlib
import sys
import types
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"
# Import pure Python files while bypassing Home Assistant's integration __init__.
package = types.ModuleType("hslhrt")
package.__path__ = [str(INTEGRATION)]
sys.modules.setdefault("hslhrt", package)
schedule = importlib.import_module("hslhrt.schedule")


def make_stop(stoptimes):
    return {
        "name": "Test stop",
        "code": "H1000",
        "gtfsId": "HSL:1000",
        "stoptimesWithoutPatterns": stoptimes,
    }


def departure(service_day, scheduled, realtime=None, realtime_enabled=False,
              route="8", destination="Jätkäsaari", state="SCHEDULED"):
    return {
        "serviceDay": service_day,
        "scheduledArrival": scheduled,
        "realtimeArrival": realtime,
        "realtime": realtime_enabled,
        "realtimeState": state,
        "headsign": destination,
        "trip": {"route": {"shortName": route}},
    }


def test_arrival_after_midnight_has_correct_timestamp():
    # 2026-10-23 00:00:00 EEST = 2026-10-22 21:00:00 UTC
    midnight_utc = 1792702800
    parsed = schedule.parse_departures(make_stop([
        departure(midnight_utc, 24 * 3600 + 600),
    ]))
    row = parsed["routes"][0]
    assert row["arrival_timestamp"] == midnight_utc + 87000
    assert row["arrival"] == "00:10:00"


def test_realtime_arrival_and_scheduled_fallback():
    # Service day is local midnight; adding offsets yields Unix timestamps.
    epoch = 1792702800
    result = schedule.parse_departures(make_stop([
        departure(epoch, 3600, 3900, True, route="8"),
        departure(epoch, 7200, 7400, False, route="2"),
    ]))["routes"]
    assert result[0]["arrival_timestamp"] == epoch + 3900
    assert result[0]["delay_seconds"] == 300
    assert result[0]["realtime"] is True
    assert result[1]["arrival_timestamp"] == epoch + 7200
    assert result[1]["realtime"] is False


def test_route_precedence_and_cancellation():
    epoch = 1792702800
    values = [
        departure(epoch, 300, route="8", destination="West"),
        departure(epoch, 100, route="2", destination="East"),
        departure(epoch, 200, route="8", destination="West", state="CANCELED"),
    ]
    result = schedule.parse_departures(
        make_stop(values), route_filter="8", destination_filter="East"
    )
    assert [r["route"] for r in result["routes"]] == ["8"]


def test_sorting_and_empty_stop():
    epoch = 1792702800
    rows = [departure(epoch, 600), departure(epoch, 300)]
    result = schedule.parse_departures(make_stop(rows))
    assert [x["arrival_timestamp"] for x in result["routes"]] == [
        epoch + 300, epoch + 600
    ]
    assert schedule.parse_departures(make_stop([]))["routes"] == []
    with pytest.raises(ValueError):
        schedule.parse_departures(None)


def test_stop_matching_and_ids():
    stops = [
        {"name": "Töölöntori", "code": "H0209", "gtfsId": "HSL:111"},
        {"name": "Töölöntori", "code": "H0210", "gtfsId": "HSL:222"},
    ]
    assert schedule.select_stop(stops, "h0210")["gtfsId"] == "HSL:222"
    assert schedule.select_stop(stops, "töölöntori")["gtfsId"] == "HSL:111"
    assert schedule.base_unique_id("HSL:111", route="8") == "HSL:111 8"
    assert schedule.base_unique_id("HSL:111") == "HSL:111 ALL"


def test_route_validation():
    stop = {"patterns": [
        {"headsign": "Kamppi", "route": {"shortName": "8"}},
        {"headsign": "Jätkäsaari", "route": {"shortName": "2"}},
    ]}
    assert schedule.route_matches(stop, "8", "ALL")
    assert schedule.route_matches(stop, "ALL", "kamppi")
    assert not schedule.route_matches(stop, "33", "ALL")
    assert not schedule.route_matches(stop, "ALL", "Espoo")
