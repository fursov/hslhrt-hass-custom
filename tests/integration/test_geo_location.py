"""Map lifecycle tests against real Home Assistant geo_location entities."""

import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hslhrt.const import DOMAIN, HFP_MANAGER
from custom_components.hslhrt.geo_location import (
    active_positions,
    journey_key,
    stop_coordinates,
)


def _trip_response(stop_response):
    """Produce two unique journeys, one each for routes 8 and 2."""
    stop = stop_response(departure_count=2)
    day = stop["stoptimesWithoutPatterns"][0]["serviceDay"]
    for idx, stop_time in enumerate(stop["stoptimesWithoutPatterns"]):
        line = "8" if idx == 0 else "2"
        stop_time["trip"] = {
            "directionId": "0",
            "departureStoptime": {
                "serviceDay": day,
                "scheduledDeparture": stop_time["scheduledArrival"] - 120,
            },
            "route": {
                "gtfsId": f"HSL:100{line}",
                "shortName": line,
                "mode": "BUS" if idx == 0 else "TRAM",
            },
        }
    return stop


def _position(latitude, longitude, timestamp=None):
    return {
        "latitude": latitude,
        "longitude": longitude,
        "position_timestamp": timestamp or time.time(),
        "operator": "0022",
        "vehicle": "01111",
        "speed_m_s": 10.5,
        "heading": 90,
    }


@pytest.mark.asyncio
async def test_map_markers_follow_multiple_journeys_and_expire(
    hass, make_entry, mock_digitransit, stop_response
):
    """Markers appear with GPS, update in place, and disappear when stale."""
    setup_client, _ = mock_digitransit
    setup_client.get_departures = AsyncMock(
        return_value=_trip_response(stop_response)
    )
    entry = make_entry(
        route="ALL",
        options={
            "track_vehicles": True,
            "tracking_horizon_minutes": 30,
            "tracking_per_route": 2,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.hslhrt.hfp.HFPManager._open_worker"),
        patch("custom_components.hslhrt.hfp.HFPManager._close_worker"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        manager = hass.data[DOMAIN][entry.entry_id][HFP_MANAGER]
        keys = list(manager._targets)
        assert len(keys) == 2
        stops = [
            state for state in hass.states.async_all("geo_location")
            if state.attributes["source"] == "hslhrt_stops"
        ]
        assert len(stops) == 1
        assert stops[0].attributes["stop_code"] == "E4971"
        assert (stops[0].attributes["latitude"], stops[0].attributes["longitude"]) == (
            60.205, 24.9
        )
        assert stops[0].attributes["icon"] == "mdi:circle-small"

        manager._accept_position(keys[0], _position(60.1, 24.8))
        manager._accept_position(keys[1], _position(60.2, 24.9))
        manager._notify(force=True)
        await hass.async_block_till_done()

        markers = [
            state for state in hass.states.async_all("geo_location")
            if state.attributes["source"] == "hslhrt"
        ]
        assert len(markers) == 2
        ids = {state.entity_id for state in markers}
        assert len(ids) == 2
        assert {state.attributes["route"] for state in markers} == {"8", "2"}
        by_route = {state.attributes["route"]: state for state in markers}
        assert by_route["8"].attributes["vehicle_mode"] == "BUS"
        assert by_route["8"].attributes["marker_label"] == "🚌 8"
        assert by_route["8"].attributes["icon"] == "mdi:bus"
        assert by_route["2"].attributes["vehicle_mode"] == "TRAM"
        assert by_route["2"].attributes["marker_label"] == "🚋 2"
        assert by_route["2"].attributes["icon"] == "mdi:tram"
        assert {state.attributes["source"] for state in markers} == {"hslhrt"}
        assert all(state.attributes["stop_code"] == "E4971" for state in markers)

        # Transient geolocation entities must not pollute the entity registry.
        registry = er.async_get(hass)
        registrations = er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
        assert len(registrations) == 4  # Three legacy + tracked-vehicles sensor
        assert not any(x.domain == "geo_location" for x in registrations)

        manager._accept_position(keys[0], _position(60.3, 25.0))
        manager._notify(force=True)
        await hass.async_block_till_done()
        updated = [
            state for state in hass.states.async_all("geo_location")
            if state.attributes["source"] == "hslhrt"
        ]
        assert {state.entity_id for state in updated} == ids
        assert any(state.attributes["latitude"] == 60.3 for state in updated)

        # Markers disappear even though original timetables are still valid.
        manager._positions[keys[0]]["position_timestamp"] = time.time() - 120
        manager._notify(force=True)
        await hass.async_block_till_done()
        remaining = [
            state for state in hass.states.async_all("geo_location")
            if state.attributes["source"] == "hslhrt"
        ]
        assert len(remaining) == 1
        assert remaining[0].attributes["route"] == "2"

        manager._positions[keys[1]]["position_timestamp"] = time.time() - 120
        manager._notify(force=True)
        await hass.async_block_till_done()
        assert {
            state.attributes["source"] for state in
            hass.states.async_all("geo_location")
        } == {"hslhrt_stops"}

        # A fresh position restores the vehicle without creating a permanent ID.
        manager._accept_position(keys[0], _position(60.4, 25.1))
        manager._notify(force=True)
        await hass.async_block_till_done()
        assert len([
            state for state in hass.states.async_all("geo_location")
            if state.attributes["source"] == "hslhrt"
        ]) == 1

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.async_all("geo_location") == []


@pytest.mark.asyncio
async def test_configured_stop_stays_visible_when_gps_disabled(
    hass, make_entry, mock_digitransit
):
    """Configured stops show on the stop layer, even with no MQTT tracking."""
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    markers = hass.states.async_all("geo_location")
    assert len(markers) == 1
    assert markers[0].attributes["source"] == "hslhrt_stops"
    assert markers[0].attributes["stop_gtfs"] == "HSL:1000"
    assert markers[0].attributes["stop_name"] == "Example"
    assert markers[0].attributes["stop_code"] == "E4971"
    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 3
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_all("geo_location") == []


def test_only_fresh_valid_exact_journeys_are_map_eligible():
    """Validate GPS inputs without relying on HA state machines."""
    trip = {
        "hfp_route_id": "1055", "direction": "1",
        "start_time": "12:05", "operating_day": "2026-10-23",
        "route": "55",
    }
    assert journey_key(trip) == ("1055", "1", "12:05", "2026-10-23")
    good = {**trip, "gps_available": True, "latitude": 60.1, "longitude": 24.8}
    bad = [
        {**good, "gps_available": False},
        {**good, "latitude": None},
        {**good, "longitude": 181},
        {**good, "latitude": float("nan")},
        {**good, "operating_day": None},
    ]
    selected = active_positions([*bad, good])
    assert len(selected) == 1
    assert next(iter(selected.values())) == good



@pytest.mark.asyncio
async def test_stop_marker_follows_coordinator_location_and_missing_coordinates(
    hass, make_entry, mock_digitransit, stop_response
):
    """Configured stop positions are not guessed or kept after invalid updates."""
    api, _flow = mock_digitransit
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    first = hass.states.async_all("geo_location")
    assert len(first) == 1
    stable_id = first[0].entity_id
    updated = stop_response()
    updated.update(lat=60.25, lon=24.85)
    api.get_departures = AsyncMock(return_value=updated)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    # Force each immediate response; async_request_refresh debounces rapid calls.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    moved = hass.states.get(stable_id)
    assert moved is not None
    assert moved.attributes["latitude"] == 60.25
    assert moved.attributes["longitude"] == 24.85

    invalid = stop_response()
    invalid.update(lat=None, lon=24.85)
    api.get_departures = AsyncMock(return_value=invalid)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.async_all("geo_location") == []

    api.get_departures = AsyncMock(return_value=stop_response())
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(stable_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_all("geo_location") == []


@pytest.mark.asyncio
async def test_invalid_stop_coords_do_not_publish_false_marker(
    hass, make_entry, mock_digitransit, stop_response
):
    api, _flow = mock_digitransit
    response = stop_response()
    response.update(lat=999, lon=24.9)
    api.get_departures = AsyncMock(return_value=response)
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_all("geo_location") == []
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("latitude,longitude", [
    (None, 24.9),
    (60.1, float("nan")),
    (60.1, 181),
    (True, 24.9),
    ("60.1", 24.9),
])
def test_invalid_stop_position_is_omitted(latitude, longitude):
    assert stop_coordinates({"stop_latitude": latitude, "stop_longitude": longitude}) is None


def test_valid_stop_position():
    assert stop_coordinates({"stop_latitude": 60.21, "stop_longitude": 24.86}) == (
        60.21, 24.86
    )



@pytest.mark.asyncio
async def test_stop_more_info_configured_departures_refresh_without_extra_api(
    hass, make_entry, mock_digitransit, stop_response
):
    """The marker shows the selected N trips, and locally expires old trips."""
    client, _flow = mock_digitransit
    client.get_departures = AsyncMock(
        return_value=stop_response(route="8", departure_count=4)
    )
    entry = make_entry(
        route="ALL", options={
            "map_stop_departures": 2,
            "scan_interval": 30,
        }
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    first = hass.states.async_all("geo_location")
    assert len(first) == 1
    ident = first[0].entity_id
    attrs = first[0].attributes
    assert attrs["source"] == "hslhrt_stops"
    assert attrs["upcoming_departures_count"] == 2
    assert attrs["next_departure_1"].endswith("8 → Kamppi")
    assert attrs["next_departure_2"].endswith("8 → Kamppi")
    assert attrs["next_departure_1"] != attrs["next_departure_2"]
    assert "next_departure_3" not in attrs
    assert client.get_departures.await_count == 1

    # The first route expires without any new data or coordinator refresh.
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    coordinator.data["routes"][0]["arrival_timestamp"] = time.time() - 1
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()
    changed = hass.states.get(ident).attributes
    assert changed["upcoming_departures_count"] == 2
    assert changed["next_departure_1"] == attrs["next_departure_2"]
    assert changed["next_departure_2"] != attrs["next_departure_2"]
    assert client.get_departures.await_count == 1

    # Stop timetable also immediately changes when a new response arrives.
    client.get_departures = AsyncMock(
        return_value=stop_response(route="2", departure_count=1)
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    updated = hass.states.get(ident).attributes
    assert updated["upcoming_departures_count"] == 1
    assert updated["next_departure_1"].endswith("2 → Kamppi")
    assert "next_departure_2" not in updated
    assert client.get_departures.await_count == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ident) is None
