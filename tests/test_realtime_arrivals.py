"""Realtime stop-board and trip-origin regression tests (pure Python)."""

import importlib
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "hslhrt"
if "hslhrt" not in sys.modules:
    package = types.ModuleType("hslhrt")
    package.__path__ = [str(INTEGRATION)]
    sys.modules["hslhrt"] = package
schedule = importlib.import_module("hslhrt.schedule")
constants = importlib.import_module("hslhrt.const")


def item(day, arrival, departure, *, position, realtime=False,
         predicted_arrival=None, predicted_departure=None, route="530"):
    value = {
        "serviceDay": day,
        "scheduledArrival": arrival,
        "scheduledDeparture": departure,
        "realtimeArrival": predicted_arrival,
        "realtimeDeparture": predicted_departure,
        "realtime": realtime,
        "realtimeState": "SCHEDULED",
        "stopPositionInPattern": position,
        "headsign": "Matinkylä",
        "trip": {"route": {"shortName": route, "mode": "BUS"}},
    }
    return value


def parse(events, *, fetched_at):
    return schedule.parse_departures({
        "name": "Eestinmalmintie", "code": "E4971",
        "gtfsId": "HSL:1000", "stoptimesWithoutPatterns": events,
    }, fetched_at=fetched_at)


def test_trip_origin_uses_departure_not_an_arriving_vehicle_eta():
    day = 1792702800
    now = day + 700
    parsed = parse([item(day, 500, 900, position=0, realtime=True,
                         predicted_arrival=620, predicted_departure=980)],
                   fetched_at=now - 30)
    row = parsed["routes"][0]
    assert row["is_origin_stop"] is True
    assert row["event_kind"] == "departure"
    assert row["display_source"] == "realtime"
    assert row["scheduled_departure_timestamp"] == day + 900
    assert row["realtime_departure_timestamp"] == day + 980
    assert row["departure_timestamp"] == day + 980
    attrs = schedule.stop_map_departure_attributes(parsed, now)
    assert attrs["upcoming_departures_count"] == 1
    assert "departs (realtime)" in attrs["next_departure_1_display"]
    assert " min " not in attrs["next_departure_1_display"]
    assert attrs["next_departure_1_event"] == "departure"
    assert attrs["next_departure_1_source"] == "realtime"
    assert "next_departure_1_minutes" not in attrs
    assert attrs["next_departure_1"].endswith("530 → Matinkylä")


def test_intermediate_stop_fresh_live_prediction_is_relative_minutes():
    day = 1792702800
    now = day + 550
    parsed = parse([item(day, 600, 610, position=3, realtime=True,
                         predicted_arrival=720, predicted_departure=730)],
                   fetched_at=now - 60)
    row = parsed["routes"][0]
    assert row["is_origin_stop"] is False
    assert row["event_kind"] == "arrival"
    assert row["realtime_arrival_timestamp"] == day + 720
    assert row["scheduled_timestamp"] == day + 600
    assert row["delay_seconds"] == 120
    attrs = schedule.stop_map_departure_attributes(parsed, now)
    assert attrs["next_departure_1_minutes"] == 3
    assert attrs["next_departure_1_display"].startswith("3 min (realtime)")
    assert attrs["next_departure_1_source"] == "realtime"
    assert attrs["next_departure_1_event"] == "arrival"
    assert attrs["next_departure_1"].startswith("00:12")


def test_scheduled_and_unknown_origin_never_imply_live_arrival():
    day = 1792702800
    now = day + 100
    unknown = item(day, 500, 520, position=None, realtime=True,
                   predicted_arrival=590, predicted_departure=610)
    scheduled = item(day, 400, 410, position=2, realtime=False,
                     predicted_arrival=600)
    parsed = parse([unknown, scheduled], fetched_at=now)
    rows = parsed["routes"]
    assert {row["route"] for row in rows} == {"530"}
    assert any(row["is_origin_stop"] is None and row["event_kind"] == "departure"
               and row["display_source"] == "scheduled" for row in rows)
    attrs = schedule.stop_map_departure_attributes(parsed, now)
    assert attrs["upcoming_departures_count"] == 2
    assert all(" min (realtime)" not in attrs[f"next_departure_{idx}_display"]
               for idx in (1, 2))
    assert attrs["next_departure_1_source"] == "scheduled"
    assert attrs["next_departure_2_source"] == "scheduled"


def test_stale_realtime_falls_back_and_expired_schedule_is_removed():
    day = 1792702800
    now = day + 600
    parsed = parse([
        item(day, 450, 450, position=1, realtime=True,
             predicted_arrival=1000),
        item(day, 750, 750, position=2, realtime=True,
             predicted_arrival=900, route="8"),
    ], fetched_at=now - constants.REALTIME_FRESHNESS_SECONDS - 1)
    attrs = schedule.stop_map_departure_attributes(parsed, now)
    assert attrs["upcoming_departures_count"] == 1
    assert attrs["next_departure_1_source"] == "scheduled"
    assert attrs["next_departure_1_event"] == "arrival"
    assert " (scheduled)" in attrs["next_departure_1_display"]
    assert " min " not in attrs["next_departure_1_display"]
    assert attrs["next_departure_1_display"].endswith("8 → Matinkylä")


def test_stop_is_origin_only_per_trip_even_when_the_route_loops():
    day = 1792702800
    now = day + 100
    parsed = parse([
        item(day, 500, 500, position=0),
        item(day, 600, 600, position=7, route="530"),
    ], fetched_at=now)
    assert [x["is_origin_stop"] for x in parsed["routes"]] == [True, False]
    attrs = schedule.stop_map_departure_attributes(parsed, now)
    assert attrs["next_departure_1_event"] == "departure"
    assert attrs["next_departure_2_event"] == "arrival"


def test_canceled_event_remains_hidden_and_old_fields_unchanged():
    day = 1792702800
    now = day + 100
    canceled = item(day, 150, 160, position=0)
    canceled["realtimeState"] = "CANCELED"
    parsed = parse([
        canceled, item(day, 300, 300, position=2),
    ], fetched_at=now)
    assert len(parsed["routes"]) == 1
    row = parsed["routes"][0]
    assert row["arrival_timestamp"] == day + 300
    assert row["arrival"] == "00:05:00"
    assert row["realtime"] is False
    attrs = schedule.stop_map_departure_attributes(parsed, now)
    assert attrs["next_departure_1"] == "00:05 · 530 → Matinkylä"


def test_scheduled_display_preserves_midnight_and_dst_fold():
    tz = ZoneInfo("Europe/Helsinki")
    first = datetime(2026, 10, 25, 3, 30, fold=0, tzinfo=tz).timestamp()
    second = datetime(2026, 10, 25, 3, 30, fold=1, tzinfo=tz).timestamp()
    assert second - first == 3600
    data = {
        "prediction_checked_at": first - 60,
        "routes": [
            {"route": "A", "destination": "First", "arrival_timestamp": first,
             "event_kind": "arrival", "display_timestamp": first,
             "display_scheduled_timestamp": first, "display_source": "scheduled",
             "is_origin_stop": False},
            {"route": "B", "destination": "Second", "arrival_timestamp": second,
             "event_kind": "arrival", "display_timestamp": second,
             "display_scheduled_timestamp": second, "display_source": "scheduled",
             "is_origin_stop": False},
        ],
    }
    attrs = schedule.stop_map_departure_attributes(data, first - 60)
    assert attrs["upcoming_departures_count"] == 2
    assert attrs["next_departure_1_display"].startswith("03:30 (scheduled)")
    assert attrs["next_departure_2_display"].startswith("03:30 (scheduled)")
    next_day = datetime(2026, 10, 26, 0, 4, tzinfo=tz).timestamp()
    data["routes"] = [{
        "route": "C", "destination": "Late", "arrival_timestamp": next_day,
        "display_timestamp": next_day, "display_scheduled_timestamp": next_day,
        "event_kind": "arrival", "display_source": "scheduled",
        "is_origin_stop": False,
    }]
    attrs = schedule.stop_map_departure_attributes(data, first - 60)
    assert attrs["next_departure_1_display"].startswith("26.10 00:04")


def test_graphql_requests_origin_position_and_separate_departure_times():
    query = constants.STOP_DEPARTURES_QUERY
    assert "stopPositionInPattern" in query
    assert "scheduledDeparture" in query
    assert "realtimeDeparture" in query
    assert "departureStoptime" in query  # HFP journey matching retained
    assert "gtfsId" in query
