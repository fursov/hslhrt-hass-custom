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
    core = types.ModuleType("homeassistant.core")
    core.callback = lambda func: func
    events = types.ModuleType("homeassistant.helpers.event")
    listeners = []
    cancelled = []

    def fake_track_time_change(hass, callback, *, second):
        assert second == 0
        listeners.append(callback)

        def unsubscribe():
            cancelled.append(callback)
            listeners.remove(callback)

        return unsubscribe

    events.async_track_utc_time_change = fake_track_time_change

    class SensorEntity:
        def async_on_remove(self, remove_callback):
            if not hasattr(self, "_remove_callbacks"):
                self._remove_callbacks = []
            self._remove_callbacks.append(remove_callback)

        def async_write_ha_state(self):
            self._writes = getattr(self, "_writes", 0) + 1

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        async def async_added_to_hass(self):
            pass

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
        ("homeassistant.core", core),
        ("homeassistant.helpers.event", events),
        ("homeassistant.helpers", helpers),
        ("homeassistant.helpers.update_coordinator", coordinator_api),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("hslhrt.sensor", ROOT / "sensor.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "hslhrt.sensor", module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "time", lambda: NOW)
    module._test_minute_callbacks = listeners
    module._test_cancelled_callbacks = cancelled
    return module


def config_entry():
    return SimpleNamespace(
        entry_id="entry1",
        unique_id="HSL:1000 8",
        options={},
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
    hass = SimpleNamespace(data={"hslhrt": {"entry1": {"coordinator": co}}})
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


def test_options_change_name_without_changing_entity_identity(sensors):
    entry = config_entry()
    entry.options = {"routes_filter": ["2", "8"], "destination_filter": "ALL"}
    entity = sensors.HSLHRTRouteSensor(
        coordinator([trip(NOW + 100)]), entry
    )
    assert entity._attr_unique_id == "HSL:1000 8"
    assert entity._attr_name == "Töölöntori(H1000) 2, 8"


def test_local_minute_timer_updates_three_sensors_and_cleans_up(sensors):
    """No coordinator or network refresh is needed to advance existing data."""
    co = coordinator([trip(NOW + 121, "8"), trip(NOW + 240, "2")])
    classes = (
        sensors.HSLHRTRouteSensor,
        sensors.HSLHRTNextArrivalSensor,
        sensors.HSLHRTMinutesUntilArrivalSensor,
    )
    instances = [cls(co, config_entry()) for cls in classes]
    for entity in instances:
        entity.hass = SimpleNamespace()
        asyncio.run(entity.async_added_to_hass())
    assert len(sensors._test_minute_callbacks) == 3
    assert instances[0].native_value == "8"
    co.data["routes"][0]["arrival_timestamp"] = NOW - 1
    for listener in list(sensors._test_minute_callbacks):
        listener(datetime.fromtimestamp(NOW + 180, timezone.utc))
    assert all(entity._writes == 1 for entity in instances)
    assert instances[0].native_value == "2"
    assert instances[1].native_value == datetime.fromtimestamp(
        NOW + 240, timezone.utc
    )
    assert instances[2].native_value == 4
    for entity in instances:
        for remove in entity._remove_callbacks:
            remove()
    assert not sensors._test_minute_callbacks
    assert len(sensors._test_cancelled_callbacks) == 3


def test_tracked_vehicles_sensor_does_not_get_minute_timer(sensors):
    """HFP has its own GPS freshness timer, not the local timetable timer."""
    manager = SimpleNamespace(add_listener=lambda callback: lambda: None)
    entity = sensors.HSLHRTTrackedVehiclesSensor(
        coordinator([]), config_entry(), manager
    )
    entity.hass = SimpleNamespace()
    asyncio.run(entity.async_added_to_hass())
    assert sensors._test_minute_callbacks == []
