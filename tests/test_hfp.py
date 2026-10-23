"""HFP parsing, exact matching and selection without a real MQTT broker."""

import importlib
import json
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"
package = sys.modules.setdefault("hslhrt", types.ModuleType("hslhrt"))
package.__path__ = [str(ROOT)]

# The fast test environment deliberately has no real Home Assistant Core.
for name in ("homeassistant", "homeassistant.helpers"):
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
if "homeassistant.helpers.event" not in sys.modules:
    module = types.ModuleType("homeassistant.helpers.event")
    module.async_track_time_interval = lambda *args, **kwargs: lambda: None
    sys.modules["homeassistant.helpers.event"] = module

hfp = importlib.import_module("hslhrt.hfp")


def trip(route, idx, when, direction="1", day="2026-10-23"):
    return {
        "route": route, "destination": "Kamppi",
        "arrival_timestamp": when,
        "arrival_datetime": "2026-10-23T10:00:00+00:00",
        "hfp_route_id": f"{route}99",
        "hfp_direction": direction,
        "hfp_start": f"1{idx}:00",
        "hfp_operating_day": day,
    }


def topic(route="53399", direction="1", start="10:00"):
    return (
        f"/hfp/v2/journey/ongoing/vp/bus/0022/01111/"
        f"{route}/{direction}/Espoo/{start}/1130106/2/60;24/19/#"
    )


def payload(route="53399", direction="1", start="10:00", day="2026-10-23",
            now=1_792_750_000, lat=60.1, lon=24.8):
    return json.dumps({"VP": {
        "route": route, "dir": direction, "start": start,
        "oday": day, "tsi": now, "lat": lat, "long": lon,
        "spd": 11.5, "hdg": 180,
    }}).encode()


def test_multiple_routes_and_two_journeys_each_are_selected():
    now = 1000
    departures = [
        trip("533", 0, 1200), trip("236", 1, 1300),
        trip("533", 2, 1400), trip("236", 3, 1500),
        trip("533", 4, 1600), trip("235", 5, 1700),
        trip("777", 6, 4000),
    ]
    got = hfp.select_journeys({"routes": departures}, now, 30, 2)
    assert [row["route"] for row in got.values()] == [
        "533", "236", "533", "236", "235"
    ]
    assert len({hfp.topic_for_trip(key) for key in got}) == 5
    assert all(x.startswith("/hfp/v2/journey/ongoing/vp/") for x in
               (hfp.topic_for_trip(k) for k in got))


def test_missing_metadata_and_duplicate_journeys_are_skipped():
    now = 100
    item = trip("533", 0, 150)
    duplicate = dict(item, arrival_timestamp=190)
    missing = dict(trip("2", 1, 190), hfp_start=None)
    result = hfp.select_journeys({"routes": [item, duplicate, missing]}, now)
    assert len(result) == 1


def test_hfp_exact_trip_and_operating_day_match():
    now = 1_792_750_000
    parsed = hfp.parse_position(topic(), payload(now=now), now)
    assert parsed is not None
    key, position = parsed
    assert key == ("53399", "1", "10:00", "2026-10-23")
    assert position["latitude"] == 60.1
    assert position["longitude"] == 24.8
    assert position["vehicle"] == "01111"

    manager = hfp.HFPManager(SimpleNamespace(), SimpleNamespace(), 30, 2)
    manager._targets = {key: trip("533", 0, now + 100)}
    manager._accept_position(key, position)
    assert manager.visible()[0]["gps_available"] is False  # historical timestamp
    manager._targets[("53399", "2", "10:00", "2026-10-23")] = trip(
        "533", 0, now + 200
    )
    assert manager.visible()[1]["gps_available"] is False


def test_reject_wrong_direction_route_or_time_and_stale_coordinates():
    now = 1_792_750_000
    assert hfp.parse_position(topic(), payload(direction="2", now=now), now) is None
    assert hfp.parse_position(topic(), payload(route="123", now=now), now) is None
    assert hfp.parse_position(topic(), payload(start="11:00", now=now), now) is None
    assert hfp.parse_position(topic(), payload(now=now - 1000), now) is None
    assert hfp.parse_position(topic(), payload(lat=999, now=now), now) is None
    assert hfp.parse_position(topic(), b"invalid-json", now) is None


def test_manager_rejects_unselected_route_and_older_telemetry():
    now = time.time()
    key = ("53399", "1", "10:00", "2026-10-23")
    manager = hfp.HFPManager(SimpleNamespace(), SimpleNamespace(), 30, 2)
    manager._targets = {key: trip("533", 0, now + 600)}
    position = {
        "latitude": 60.2, "longitude": 24.8,
        "position_timestamp": now,
    }
    manager._accept_position(("99999", "1", "10:00", "2026-10-23"), position)
    assert manager.visible()[0]["gps_available"] is False
    manager._accept_position(key, position)
    assert manager.visible()[0]["gps_available"] is True
    manager._accept_position(key, dict(position, position_timestamp=now - 5))
    assert manager.visible()[0]["latitude"] == 60.2
    manager._positions[key]["position_timestamp"] = now - 100
    assert manager.visible()[0]["gps_available"] is False
    assert "latitude" not in manager.visible()[0]


def test_midnight_service_day_and_direction_in_schedule_parser():
    schedule = importlib.import_module("hslhrt.schedule")
    service_day = 1792702800
    result = schedule.parse_departures({
        "name": "Example", "code": "E4971", "gtfsId": "HSL:1000",
        "stoptimesWithoutPatterns": [{
            "serviceDay": service_day,
            "scheduledArrival": 25 * 3600 + 10 * 60,
            "realtimeArrival": 25 * 3600 + 10 * 60,
            "realtime": True,
            "headsign": "Kamppi",
            "trip": {
                "directionId": "0",
                "departureStoptime": {
                    "serviceDay": service_day,
                    "scheduledDeparture": 24 * 3600 + 45 * 60,
                },
                "route": {"gtfsId": "HSL:1055", "shortName": "55"},
            },
        }],
    })
    item = result["routes"][0]
    assert item["hfp_route_id"] == "1055"
    assert item["hfp_direction"] == "1"
    assert item["hfp_start"] == "00:45"
    assert item["hfp_operating_day"] == "2026-10-23"
