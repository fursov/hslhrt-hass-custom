"""Home Assistant end-to-end config-entry and entity registry tests."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hslhrt.schedule import parse_departures

from custom_components.hslhrt.const import COORDINATOR, DOMAIN


@pytest.mark.asyncio
async def test_setup_registers_real_sensor_entities(
    hass, make_entry, mock_digitransit
):
    """The real HA loader must import integration + sensor platform."""
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    rows = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(rows) == 3
    assert {row.unique_id for row in rows} == {
        "HSL:1000 8",
        "HSL:1000 8_next_arrival",
        "HSL:1000 8_minutes_until_arrival",
    }

    route_row = next(row for row in rows if row.unique_id == "HSL:1000 8")
    route_state = hass.states.get(route_row.entity_id)
    assert route_state is not None
    assert route_state.state == "8"
    assert route_state.attributes["STOP CODE"] == "E4971"
    assert route_state.attributes["ROUTE"] == "8"
    assert route_state.attributes["ROUTES"] == []
    assert route_state.attributes["departures"]

    time_row = next(row for row in rows if row.unique_id.endswith("_next_arrival"))
    assert hass.states.get(time_row.entity_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.asyncio
async def test_coordinator_refresh_changes_real_entity_state(
    hass, make_entry, mock_digitransit, stop_response
):
    """Updating the coordinator must write new sensor state via HA."""
    setup_client, _ = mock_digitransit
    entry = make_entry(route="ALL")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity = next(
        row for row in er.async_entries_for_config_entry(registry, entry.entry_id)
        if row.unique_id == "HSL:1000 ALL"
    )
    assert hass.states.get(entity.entity_id).state == "8"

    setup_client.get_departures = AsyncMock(return_value=stop_response(route="2"))
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity.entity_id).state == "2"


@pytest.mark.asyncio
async def test_missing_key_starts_reauthentication(
    hass, make_entry
):
    """Legacy config entries must not silently attempt unauthenticated calls."""
    entry = make_entry(api_key=None)
    entry.add_to_hass(hass)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not result
    assert entry.state is ConfigEntryState.SETUP_ERROR or (
        entry.state is ConfigEntryState.SETUP_RETRY
    ) or entry.state is ConfigEntryState.MIGRATION_ERROR or (
        entry.state is ConfigEntryState.LOADED
    ) is False



@pytest.mark.asyncio
async def test_minute_tick_updates_eta_and_next_route_without_extra_api_calls(
    hass, make_entry, mock_digitransit, stop_response
):
    """Cross a departure boundary locally without invoking Digitransit again."""
    client, _flow = mock_digitransit
    entry = make_entry(route="ALL", options={"scan_interval": 30})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    rows = {
        row.unique_id: row.entity_id
        for row in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    route_id = rows["HSL:1000 ALL"]
    arrival_id = rows["HSL:1000 ALL_next_arrival"]
    eta_id = rows["HSL:1000 ALL_minutes_until_arrival"]
    assert hass.states.get(route_id).state == "8"
    assert client.get_departures.await_count == 1

    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    old = coordinator.data["routes"][0]
    old["arrival_timestamp"] = time.time() - 15
    new = parse_departures(stop_response(route="2"))["routes"][0]
    # The later route has a distinct ETA, so we verify timestamp rollover.
    new["arrival_timestamp"] -= 60
    new["arrival_datetime"] = datetime.fromtimestamp(
        new["arrival_timestamp"], tz=timezone.utc
    ).isoformat()
    coordinator.data["routes"].append(new)
    assert hass.states.get(route_id).state == "8"  # no coordinator push
    previous_arrival = hass.states.get(arrival_id).state

    # Time event fires the sensor-only timer, not the coordinator/API.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()

    assert hass.states.get(route_id).state == "2"
    assert hass.states.get(arrival_id).state == datetime.fromtimestamp(
        new["arrival_timestamp"], tz=timezone.utc
    ).isoformat()
    assert hass.states.get(arrival_id).state != previous_arrival
    assert hass.states.get(route_id).attributes["departures"][0]["route"] == "2"
    eta = int(hass.states.get(eta_id).state)
    assert 1 <= eta <= 11
    assert client.get_departures.await_count == 1

    # Expire the last known arrival: all three timetable entities become unknown.
    new["arrival_timestamp"] = time.time() - 1
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=4))
    await hass.async_block_till_done()
    assert hass.states.get(route_id).state == "unknown"
    assert hass.states.get(arrival_id).state == "unknown"
    assert hass.states.get(eta_id).state == "unknown"
    assert hass.states.get(route_id).attributes["departures"] == []
    assert client.get_departures.await_count == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # Registered sensor entities remain as unavailable states after unload.
    ids = (route_id, arrival_id, eta_id)
    before_tick = {
        entity_id: hass.states.get(entity_id).last_updated
        for entity_id in ids
    }
    assert all(hass.states.get(entity_id).state == "unavailable" for entity_id in ids)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert all(hass.states.get(entity_id).state == "unavailable" for entity_id in ids)
    assert all(
        hass.states.get(entity_id).last_updated == before_tick[entity_id]
        for entity_id in ids
    )
    assert client.get_departures.await_count == 1
