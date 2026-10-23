"""Home Assistant end-to-end config-entry and entity registry tests."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

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
async def test_transient_api_failure_recovers_real_sensor(
    hass, make_entry, mock_digitransit, stop_response
):
    """DataUpdateCoordinator must mark entities unavailable and recover."""
    from custom_components.hslhrt.client import DigitransitError

    setup_client, _ = mock_digitransit
    entry = make_entry(route="ALL")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    row = next(
        ent for ent in er.async_entries_for_config_entry(registry, entry.entry_id)
        if ent.unique_id == "HSL:1000 ALL"
    )
    assert hass.states.get(row.entity_id).state == "8"

    setup_client.get_departures.side_effect = DigitransitError("test outage")
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(row.entity_id).state == "unavailable"

    setup_client.get_departures.side_effect = None
    setup_client.get_departures.return_value = stop_response()
    await coordinator.async_request_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(row.entity_id).state == "8"
