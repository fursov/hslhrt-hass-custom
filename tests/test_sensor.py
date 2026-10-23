"""Sensor contract tests using a minimal Home Assistant API stub."""

import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"
NOW = 1792700000.0


@pytest.fixture
def sensors(monkeypatch):
    """Import the actual sensor module with isolated HA dependencies."""
    if "hslhrt" not in sys.modules:
        package = types.ModuleType("hslhrt")
        package.__path__ = [str(ROOT)]
        monkeypatch.setitem(sys.modules, "hslhrt", package)

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    sensor_api = types.ModuleType("homeassistant.components.sensor")
    constants = types.ModuleType("homeassistant.const")
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    coordinator_api = types.ModuleType("homeassistant.helpers.update_coordinator")

    class SensorEntity:
        pass

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    class SensorDeviceClass:
        TIMESTAMP = "timestamp"

    class UnitOfTime:
        MINUTES = "min"

    sensor_api.SensorEntity = SensorEntity
    sensor_api.SensorDeviceClass = SensorDeviceClass
    coordinator_api.CoordinatorEntity = CoordinatorEntity
    constants.ATTR_ATTRIBUTION = "attribution"
    constants.UnitOfTime = UnitOfTime

    for name, module in (
        ("homeassistant", ha),
        ("homeassistant.components", components),
        ("homeassistant.components.sensor", sensor_api),
        ("homeassistant.const", constants),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.update_coordinator", coordinator_api),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("hslhrt.sensor", ROOT / "sensor.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "hslhrt.sensor", module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "time", lambda: NOW)
    return module


def config_entry():
    return SimpleNamespace(
        entry_id="entry1",
        unique_id="HSL:1000 8",
        data={"stop_gtfs": "HSL:1000", "stop_name": "Töölöntori",
              "stop_code": "H1000", "route": "8", "destination": "ALL"},
    )


def trip(timestamp, route="8"):
    return {
        "arrival_timestamp": timestamp,
        "scheduled_timestamp": timestamp - 45,
        "arrival": "12:15:00",
        "arrival_datetime": datetime.fromtimestamp(
            timestamp, tz=timezone.utc
        ).isoformat(),
        "realtime": True,
        "delay_seconds": 45,
        "route": route,
        "destination": "Jätkäsaari",
    }


def coordinator(rows):
    return SimpleNamespace(data={
        "stop_name": "Töölöntori", "stop_code": "H1000",
        "stop_gtfs": "HSL:1000", "routes": rows,
    })


def test_sensor_registration_preserves_legacy_unique_id(sensors):
    co = coordinator([trip(NOW + 121)])
    hass = {"hslhrt": {"entry1": {"coordinator": co}}}
    entities = []
    asyncio.run(sensors.async_setup_entry(hass, config_entry(), entities.extend))
    assert len(entities) == 3
    route, arrival, eta = entities
    assert route._attr_unique_id == "HSL:1000 8"
    assert arrival._attr_unique_id == "HSL:1000 8_next_arrival"
    assert eta._attr_unique_id == "HSL:1000 8_minutes_until_arrival"
    assert route._attr_name == "Töölöntori(H1000) 8"


def test_legacy_attributes_and_bounded_timetable(sensors):
    rows = [trip(NOW + 180 + i * 300) for i in range(25)]
    entity = sensors.HSLHRTRouteSensor(coordinator(rows), config_entry())
    assert entity.native_value == "8"
    attrs = entity.extra_state_attributes
    assert attrs["STOP NAME"] == "Töölöntori"
    assert attrs["STOP CODE"] == "H1000"
    assert attrs["GTFS ID"] == "HSL:1000"
    assert attrs["ROUTE"] == "8"
    assert attrs["DESTINATION"] == "Jätkäsaari"
    assert attrs["ARRIVAL TIME"] == "12:15:00"
    assert len(attrs["ROUTES"]) == 20
    assert len(attrs["departures"]) == 10
    assert attrs["ROUTES"][0]["arrival_datetime"] == rows[1]["arrival_datetime"]
    assert attrs["departures"][0]["arrival_datetime"] == rows[0]["arrival_datetime"]
    assert attrs["departures"][0]["delay_seconds"] == 45
    assert attrs["departures"][0]["scheduled_datetime"] == datetime.fromtimestamp(
        rows[0]["scheduled_timestamp"], tz=timezone.utc
    ).isoformat()


def test_expiry_next_arrival_eta_and_coordinator_updates(sensors):
    co = coordinator([trip(NOW - 10, "4"), trip(NOW + 80, "8")])
    route = sensors.HSLHRTRouteSensor(co, config_entry())
    arrival = sensors.HSLHRTNextArrivalSensor(co, config_entry())
    eta = sensors.HSLHRTMinutesUntilArrivalSensor(co, config_entry())
    assert route.native_value == "8"
    assert arrival.native_value == datetime.fromtimestamp(
        NOW + 80, tz=timezone.utc
    )
    assert eta.native_value == 2
    assert arrival._attr_device_class == "timestamp"
    assert eta._attr_native_unit_of_measurement == "min"

    co.data["routes"] = [trip(NOW + 25, "2")]
    assert route.native_value == "2"
    assert arrival.native_value == datetime.fromtimestamp(NOW + 25, tz=timezone.utc)
    assert eta.native_value == 1


def test_empty_and_departed_routes_are_unknown(sensors):
    co = coordinator([])
    route = sensors.HSLHRTRouteSensor(co, config_entry())
    arrival = sensors.HSLHRTNextArrivalSensor(co, config_entry())
    eta = sensors.HSLHRTMinutesUntilArrivalSensor(co, config_entry())
    assert route.native_value is None
    assert arrival.native_value is None
    assert eta.native_value is None
    attrs = route.extra_state_attributes
    assert attrs["STOP NAME"] == "Töölöntori"
    assert attrs["ROUTES"] == []
    assert attrs["departures"] == []
    co.data["routes"] = [trip(NOW - 1)]
    assert route.native_value is None
    assert arrival.native_value is None
    assert eta.native_value is None


def test_eta_rounds_up_exact_and_partial_minutes(sensors):
    co = coordinator([trip(NOW + 120)])
    eta = sensors.HSLHRTMinutesUntilArrivalSensor(co, config_entry())
    assert eta.native_value == 2
    co.data["routes"] = [trip(NOW + 120.01)]
    assert eta.native_value == 3
