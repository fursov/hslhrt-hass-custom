"""Use the real HA entity registry without connecting to the public HFP broker."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.helpers import entity_registry as er

from custom_components.hslhrt.const import COORDINATOR, DOMAIN, HFP_MANAGER


@pytest.mark.asyncio
async def test_opt_in_hfp_adds_one_real_sensor_without_network(
    hass, make_entry, mock_digitransit, stop_response
):
    setup_client, _ = mock_digitransit
    sample = stop_response(departure_count=2)
    service_day = sample["stoptimesWithoutPatterns"][0]["serviceDay"]
    # In the real API, HFP metadata belongs to the trip from the first stop.
    for idx, item in enumerate(sample["stoptimesWithoutPatterns"]):
        item["trip"] = {
            "directionId": "0",
            "departureStoptime": {
                "serviceDay": service_day,
                "scheduledDeparture": item["scheduledArrival"] - 120,
            },
            "route": {"gtfsId": "HSL:1008", "shortName": "8"},
        }
    setup_client.get_departures = AsyncMock(return_value=sample)
    entry = make_entry(options={
        "track_vehicles": True,
        "tracking_horizon_minutes": 30,
        "tracking_per_route": 2,
    })
    entry.add_to_hass(hass)

    with (
        patch("custom_components.hslhrt.hfp.HFPManager._open_worker"),
        patch("custom_components.hslhrt.hfp.HFPManager._close_worker"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entities = er.async_entries_for_config_entry(registry, entry.entry_id)
        assert len(entities) == 4
        tracker = next(x for x in entities if x.unique_id.endswith("_tracked_vehicles"))
        state = hass.states.get(tracker.entity_id)
        assert state is not None
        assert state.state == "0"
        assert state.attributes["selected_journeys"] == 2
        assert all(not vehicle["gps_available"] for vehicle in state.attributes["vehicles"])

        manager = hass.data[DOMAIN][entry.entry_id][HFP_MANAGER]
        key = next(iter(manager._targets))
        manager._last_notify = 0
        manager._accept_position(key, {
            "latitude": 60.2, "longitude": 24.8,
            "position_timestamp": time.time(),
            "operator": "0022", "vehicle": "01111",
        })
        await hass.async_block_till_done()
        updated = hass.states.get(tracker.entity_id)
        assert updated.state == "1"
        assert updated.attributes["vehicles"][0]["gps_available"] is True

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
