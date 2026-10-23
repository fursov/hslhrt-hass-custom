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



@pytest.mark.asyncio
async def test_mqtt_subscriptions_change_serialize_and_resubscribe_after_reconnect(
    hass,
):
    """Use the real HA task/executor APIs, without connecting to MQTT."""
    from custom_components.hslhrt.hfp import HFPManager
    from types import SimpleNamespace

    class FakeMQTT:
        def __init__(self):
            self.subscribe_calls = []
            self.unsubscribe_calls = []

        def subscribe(self, topic, qos=0):
            self.subscribe_calls.append(topic)
            return (0, len(self.subscribe_calls))

        def unsubscribe(self, topic):
            self.unsubscribe_calls.append(topic)
            return (0, len(self.unsubscribe_calls))

        def disconnect(self):
            return 0

        def loop_stop(self):
            pass

    def departure(line: str, minutes: int):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        instant = time.time() + minutes * 60
        helsinki = datetime.fromtimestamp(instant, ZoneInfo("Europe/Helsinki"))
        return {
            "route": line,
            "arrival_timestamp": instant,
            "hfp_route_id": f"{line}00",
            "hfp_direction": "1",
            "hfp_start": helsinki.strftime("%H:%M"),
            "hfp_operating_day": helsinki.date().isoformat(),
        }

    first = departure("533", 10)
    second = departure("236", 15)
    third = departure("530", 12)
    coordinator = SimpleNamespace(data={"routes": [first, second]})
    manager = HFPManager(hass, coordinator, horizon=30, per_route=2)
    broker = FakeMQTT()
    manager._client = broker
    manager._refresh_targets()
    assert manager._subscribed_topics == frozenset()
    # Initial TCP handshake; an executor Future is awaited by a real coroutine.
    manager._set_connected(True)
    await hass.async_block_till_done()
    expected = set(manager._topics)
    assert expected == set(broker.subscribe_calls)
    assert manager._subscribed_topics == expected

    coordinator.data = {"routes": [second, third]}
    manager._refresh_targets()
    await hass.async_block_till_done()
    now = set(manager._topics)
    assert manager._subscribed_topics == now
    assert all("53300" not in topic for topic in now)
    assert len(broker.unsubscribe_calls) == 1
    assert len(broker.subscribe_calls) == 3

    manager._set_connected(False)
    assert manager._subscribed_topics == frozenset()
    manager._set_connected(True)
    await hass.async_block_till_done()
    assert manager._subscribed_topics == now
    assert len(broker.subscribe_calls) == 5

    # Several coordinator refreshes before the scheduled coroutine runs:
    # only the final set of topics should be reflected at the broker.
    coordinator.data = {"routes": [first]}
    manager._refresh_targets()
    coordinator.data = {"routes": [second]}
    manager._refresh_targets()
    coordinator.data = {"routes": [first, third]}
    manager._refresh_targets()
    await hass.async_block_till_done()
    assert manager._subscribed_topics == manager._topics
    assert len(manager._subscribed_topics) == 2
    await manager.async_stop()
    assert manager._subscription_task is None


@pytest.mark.asyncio
async def test_rejected_mqtt_subscription_does_not_claim_success(hass):
    from custom_components.hslhrt.hfp import HFPManager
    from types import SimpleNamespace

    class RejectBroker:
        def subscribe(self, topic, qos=0):
            return (128, 0)

        def unsubscribe(self, topic):
            return (0, 0)

        def disconnect(self):
            pass

        def loop_stop(self):
            pass

    manager = HFPManager(hass, SimpleNamespace(), 30, 2)
    manager._client = RejectBroker()
    manager._topics = frozenset({"/hfp/test"})
    manager._set_connected(True)
    await hass.async_block_till_done()
    assert not manager._subscribed_topics
    await manager.async_stop()
