"""Map lifecycle tests against real Home Assistant geo_location entities."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.helpers import entity_registry as er

from custom_components.hslhrt.const import DOMAIN, HFP_MANAGER
from custom_components.hslhrt.geo_location import active_positions, journey_key


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
        assert hass.states.async_all("geo_location") == []

        manager._accept_position(keys[0], _position(60.1, 24.8))
        manager._accept_position(keys[1], _position(60.2, 24.9))
        manager._notify(force=True)
        await hass.async_block_till_done()

        markers = hass.states.async_all("geo_location")
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
        updated = hass.states.async_all("geo_location")
        assert {state.entity_id for state in updated} == ids
        assert any(state.attributes["latitude"] == 60.3 for state in updated)

        # Markers disappear even though original timetables are still valid.
        manager._positions[keys[0]]["position_timestamp"] = time.time() - 120
        manager._notify(force=True)
        await hass.async_block_till_done()
        remaining = hass.states.async_all("geo_location")
        assert len(remaining) == 1
        assert remaining[0].attributes["route"] == "2"

        manager._positions[keys[1]]["position_timestamp"] = time.time() - 120
        manager._notify(force=True)
        await hass.async_block_till_done()
        assert hass.states.async_all("geo_location") == []

        # A fresh position restores the vehicle without creating a permanent ID.
        manager._accept_position(keys[0], _position(60.4, 25.1))
        manager._notify(force=True)
        await hass.async_block_till_done()
        assert len(hass.states.async_all("geo_location")) == 1

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.async_all("geo_location") == []


@pytest.mark.asyncio
async def test_no_geolocation_entities_when_gps_disabled(
    hass, make_entry, mock_digitransit
):
    """Legacy installations have no MQTT manager or map markers."""
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
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
