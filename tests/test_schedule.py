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


def test_upcoming_departures_discard_expired_keep_order_without_mutation():
    data = {"routes": [
        {"route": "8", "arrival_timestamp": 105},
        {"route": "8", "arrival_timestamp": 99},
        {"route": "2", "arrival_timestamp": 102},
        {"route": "4", "arrival_timestamp": None},
    ]}
    upcoming = schedule.upcoming_departures(data, 100)
    assert [row["arrival_timestamp"] for row in upcoming] == [102, 105]
    assert len(data["routes"]) == 4
    assert schedule.upcoming_departures({}, 100) == []
    assert schedule.upcoming_departures(None, 100) == []



def test_multiple_route_filter_and_destination_precedence():
    epoch = 1792702800
    stop = make_stop([
        departure(epoch, 300, route="8", destination="West"),
        departure(epoch, 500, route="2", destination="East"),
        departure(epoch, 400, route="4", destination="East"),
    ])
    # Explicit route list overrides destination filter.
    rows = schedule.parse_departures(
        stop, "ALL", "West", route_filters=["2", "4"]
    )["routes"]
    assert [r["route"] for r in rows] == ["4", "2"]
    # Empty list means all routes; direction can still restrict them.
    rows = schedule.parse_departures(
        stop, "8", "East", route_filters=[]
    )["routes"]
    assert [r["route"] for r in rows] == ["4", "2"]
    # Existing route-only entries still use the v0.5 filtering semantics.
    rows = schedule.parse_departures(stop, "8", "East")["routes"]
    assert [r["route"] for r in rows] == ["8"]



def test_route_mode_from_routing_api_does_not_change_timetable_filtering():
    row = departure(1792702800, 900, route="M1")
    row["trip"]["route"]["mode"] = "SUBWAY"
    parsed = schedule.parse_departures(make_stop([row]), route_filter="M1")
    assert len(parsed["routes"]) == 1
    assert parsed["routes"][0]["vehicle_mode"] == "SUBWAY"
    row["trip"]["route"]["mode"] = None
    assert schedule.parse_departures(make_stop([row]))["routes"][0]["vehicle_mode"] is None



def test_stop_coordinates_survive_empty_departure_list():
    stop = make_stop([])
    stop.update(lat=60.205, lon=24.9)
    parsed = schedule.parse_departures(stop)
    assert parsed["stop_latitude"] == 60.205
    assert parsed["stop_longitude"] == 24.9
    assert parsed["routes"] == []



def test_stop_map_more_info_departures_respect_limit_time_and_filters():
    """Map More Info rows are ordered, bounded and human-readable."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    helsinki = ZoneInfo("Europe/Helsinki")
    now = datetime(2026, 10, 24, 23, 55, tzinfo=helsinki).timestamp()
    t1 = datetime(2026, 10, 24, 23, 58, tzinfo=helsinki).timestamp()
    t2 = datetime(2026, 10, 25, 0, 4, tzinfo=helsinki).timestamp()
    data = {"routes": [
        {"route": "8", "destination": "Kamppi", "arrival_timestamp": t2},
        {"route": "2", "destination": "Espoo", "arrival_timestamp": now - 10},
        {"route": "530", "destination": "Matinkylä", "arrival_timestamp": t1},
    ]}
    assert schedule.stop_map_departure_attributes(data, now, 2) == {
        "upcoming_departures_count": 2,
        "next_departure_1": "23:58 · 530 → Matinkylä",
        "next_departure_2": "25.10 00:04 · 8 → Kamppi",
    }
    assert schedule.stop_map_departure_attributes(data, t1 + 1, 1) == {
        "upcoming_departures_count": 1,
        "next_departure_1": "25.10 00:04 · 8 → Kamppi",
    }
    assert schedule.stop_map_departure_attributes(data, t2 + 1, 5) == {
        "upcoming_departures_count": 0,
    }


@pytest.mark.parametrize("invalid_limit", [0, -1, 11, True, "7", None])
def test_stop_map_departure_limit_is_bounded(invalid_limit):
    epoch = 1792702800
    data = {"routes": [
        {"route": str(i), "destination": "X", "arrival_timestamp": epoch + 60 + i}
        for i in range(11)
    ]}
    result = schedule.stop_map_departure_attributes(data, epoch, invalid_limit)
    assert result["upcoming_departures_count"] == 5
    assert "next_departure_5" in result
    assert "next_departure_6" not in result


def test_stop_map_timetable_keeps_dst_fold_distinct():
    """Epoch timestamps distinguish two real instances of 03:30 during DST."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Helsinki")
    first = datetime(2026, 10, 25, 3, 30, fold=0, tzinfo=tz).timestamp()
    second = datetime(2026, 10, 25, 3, 30, fold=1, tzinfo=tz).timestamp()
    assert second - first == 3600
    data = {"routes": [
        {"route": "A", "destination": "First", "arrival_timestamp": first},
        {"route": "B", "destination": "Second", "arrival_timestamp": second},
    ]}
    attrs = schedule.stop_map_departure_attributes(data, first - 60, 5)
    assert attrs["upcoming_departures_count"] == 2
    assert attrs["next_departure_1"] == "03:30 · A → First"
    assert attrs["next_departure_2"] == "03:30 · B → Second"
