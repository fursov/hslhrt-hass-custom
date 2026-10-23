"""Optional, route-scoped HSL HFP v2 MQTT vehicle tracking.

No MQTT message may change the Routing v2 timetable. MQTT is best-effort:
unmatched and stale vehicles are kept out of the published positions.
"""

import asyncio
import json
import math
import ssl
import time
from collections import defaultdict
from datetime import timedelta
from typing import Any, Callable

from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DEFAULT_HFP_HORIZON,
    DEFAULT_HFP_PER_ROUTE,
    HFP_HOST,
    HFP_MAX_SUBSCRIPTIONS,
    HFP_PORT,
    HFP_POSITION_UPDATE_SECONDS,
    HFP_STALE_SECONDS,
    _LOGGER,
)

TripKey = tuple[str, str, str, str]  # GTFS route, HFP direction, start, day


def trip_key(departure: dict) -> TripKey | None:
    """Return the *exact* HFP journey identity or None if insufficient data."""
    fields = (
        departure.get("hfp_route_id"),
        departure.get("hfp_direction"),
        departure.get("hfp_start"),
        departure.get("hfp_operating_day"),
    )
    if any(not isinstance(value, str) or not value for value in fields):
        return None
    route, direction, start, day = fields
    if (
        not route.isalnum()
        or direction not in ("1", "2")
        or len(start) != 5
        or start[2] != ":"
        or not start.replace(":", "").isdigit()
        or len(day) != 10
    ):
        return None
    return route, direction, start, day


def select_journeys(
    coordinator_data: dict | None,
    timestamp: float,
    horizon_minutes: int = DEFAULT_HFP_HORIZON,
    per_route: int = DEFAULT_HFP_PER_ROUTE,
) -> dict[TripKey, dict]:
    """Select the next N departures per public route inside the horizon.

    Limit broker subscriptions globally. Do not substitute a vehicle merely
    because its displayed route number matches a selected route number.
    """
    if not (1 <= horizon_minutes <= 90 and 1 <= per_route <= 5):
        return {}
    rows = (coordinator_data or {}).get("routes") or []
    count: dict[str, int] = defaultdict(int)
    selected: dict[TripKey, dict] = {}
    sorted_rows = sorted(
        (
            row for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("arrival_timestamp"), (int, float))
            and timestamp <= row["arrival_timestamp"] <= timestamp + horizon_minutes * 60
        ),
        key=lambda row: row["arrival_timestamp"],
    )
    for row in sorted_rows:
        key = trip_key(row)
        line = row.get("route")
        if key is None or not isinstance(line, str):
            continue
        if count[line] >= per_route or key in selected:
            continue
        count[line] += 1
        selected[key] = row
        if len(selected) >= HFP_MAX_SUBSCRIPTIONS:
            break
    return selected


def topic_for_trip(key: TripKey) -> str:
    """Subscribe on a specific route, direction and start, never fleet-wide."""
    route, direction, start, _day = key
    return f"/hfp/v2/journey/ongoing/vp/+/+/+/{route}/{direction}/+/{start}/#"


def parse_position(topic: str, payload: bytes, now: float) -> tuple[TripKey, dict] | None:
    """Validate an HFP VP message and derive its exact GTFS journey identity."""
    parts = topic.strip("/").split("/")
    if (
        len(parts) < 13
        or parts[:5] != ["hfp", "v2", "journey", "ongoing", "vp"]
        or parts[9] not in ("1", "2")
    ):
        return None
    try:
        message = json.loads(payload)
    except (ValueError, UnicodeDecodeError, TypeError):
        return None
    if not isinstance(message, dict) or not isinstance(message.get("VP"), dict):
        return None
    vp = message["VP"]
    day = vp.get("oday")
    if not isinstance(day, str):
        return None
    key = (parts[8], parts[9], parts[11], day)
    if not trip_key({
        "hfp_route_id": key[0], "hfp_direction": key[1],
        "hfp_start": key[2], "hfp_operating_day": key[3],
    }):
        return None
    # Cross-check payload against topic where fields are present.
    if (
        str(vp.get("route") or key[0]) != key[0]
        or str(vp.get("dir") or key[1]) != key[1]
        or str(vp.get("start") or key[2]) != key[2]
    ):
        return None
    lat, lon = vp.get("lat"), vp.get("long")
    if (
        type(lat) not in (int, float)
        or type(lon) not in (int, float)
        or not math.isfinite(lat)
        or not math.isfinite(lon)
        or not (-90 <= lat <= 90 and -180 <= lon <= 180)
    ):
        return None
    try:
        timestamp = float(vp["tsi"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(timestamp) or abs(timestamp - now) > HFP_STALE_SECONDS:
        return None
    speed = vp.get("spd")
    heading = vp.get("hdg")
    return key, {
        "latitude": lat,
        "longitude": lon,
        "speed_m_s": speed if type(speed) in (int, float) else None,
        "heading": heading if type(heading) in (int, float) else None,
        "operator": parts[6],
        "vehicle": parts[7],
        "position_timestamp": timestamp,
    }


class HFPManager:
    """Own one TLS MQTT connection per enabled stop config entry."""

    def __init__(self, hass, coordinator, horizon: int, per_route: int):
        self.hass = hass
        self.coordinator = coordinator
        self.horizon = horizon
        self.per_route = per_route
        self._client = None
        self._targets: dict[TripKey, dict] = {}
        self._topics: frozenset[str] = frozenset()
        # These are the topics acknowledged by the current broker connection.
        self._subscribed_topics: frozenset[str] = frozenset()
        self._connection_generation = 0
        self._subscription_task: asyncio.Task | None = None
        self._positions: dict[TripKey, dict] = {}
        self._listeners: set[Callable[[], None]] = set()
        self._remove_coordinator = None
        self._remove_timer = None
        self._last_notify = 0.0
        self.connected = False
        self._stopping = False

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an HA-entity update callback."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _notify(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_notify >= HFP_POSITION_UPDATE_SECONDS:
            self._last_notify = now
            for callback in tuple(self._listeners):
                callback()

    def _refresh_targets(self) -> None:
        """Called in the HA event loop after each Routing coordinator refresh."""
        if self._stopping:
            return
        targets = select_journeys(
            self.coordinator.data, time.time(), self.horizon, self.per_route
        )
        desired = frozenset(topic_for_trip(key) for key in targets)
        old = self._topics
        self._targets = targets
        self._topics = desired
        for key in tuple(self._positions):
            if key not in targets:
                del self._positions[key]
        if old != desired:
            self._schedule_subscription_sync()
        self._notify(force=True)

    def _schedule_subscription_sync(self) -> None:
        """Schedule a coroutine, never wrap an executor Future in a Task."""
        if self._stopping or not self.connected or self._client is None:
            return
        if self._subscription_task is None or self._subscription_task.done():
            self._subscription_task = self.hass.async_create_task(
                self._async_sync_subscriptions()
            )

    def _change_subscriptions(
        self, remove: frozenset[str], add: frozenset[str]
    ) -> tuple[frozenset[str], frozenset[str]]:
        """Run paho calls in an executor and return successfully changed topics."""
        client = self._client
        if client is None:
            return frozenset(), frozenset()
        removed = set()
        added = set()
        for topic in sorted(remove):
            result, _mid = client.unsubscribe(topic)
            if result == 0:
                removed.add(topic)
            else:
                _LOGGER.warning("HFP MQTT unsubscribe failed for %s: %s", topic, result)
        for topic in sorted(add):
            result, _mid = client.subscribe(topic, qos=0)
            if result == 0:
                added.add(topic)
            else:
                _LOGGER.warning("HFP MQTT subscribe failed for %s: %s", topic, result)
        return frozenset(removed), frozenset(added)

    async def _async_sync_subscriptions(self) -> None:
        """Serialize broker changes and converge after rapid timetable updates."""
        while not self._stopping and self.connected and self._client is not None:
            desired = self._topics
            applied = self._subscribed_topics
            if desired == applied:
                return
            generation = self._connection_generation
            try:
                removed, added = await self.hass.async_add_executor_job(
                    self._change_subscriptions, applied - desired, desired - applied
                )
            except Exception:
                _LOGGER.exception("Failed to update HFP MQTT subscriptions")
                return
            # Discard results from a disconnected broker session. A reconnect
            # resets the applied topics, and the loop will resubscribe.
            if generation != self._connection_generation:
                continue
            self._subscribed_topics = (applied - removed) | added
            if self._subscribed_topics == applied:
                # Broker rejected the operations; retry on the next refresh.
                return

    def _open_worker(self) -> None:
        """All TLS setup and thread creation happen outside the HA event loop."""
        import paho.mqtt.client as mqtt

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
        )
        client.tls_set_context(ssl.create_default_context())
        client.reconnect_delay_set(min_delay=2, max_delay=60)

        def on_connect(_client, _userdata, _flags, reason_code, _properties):
            # Only the Home Assistant loop may modify subscription state.
            self.hass.loop.call_soon_threadsafe(
                self._set_connected, not reason_code.is_failure
            )

        def on_disconnect(_client, _userdata, _flags, _reason, _properties):
            self.hass.loop.call_soon_threadsafe(self._set_connected, False)

        def on_message(_client, _userdata, msg):
            parsed = parse_position(msg.topic, msg.payload, time.time())
            if parsed:
                self.hass.loop.call_soon_threadsafe(
                    self._accept_position, parsed[0], parsed[1]
                )

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        self._client = client
        client.connect_async(HFP_HOST, HFP_PORT, keepalive=60)
        client.loop_start()

    def _set_connected(self, value: bool) -> None:
        if self._stopping:
            return
        self._connection_generation += 1
        self.connected = value
        # Every MQTT reconnect has a fresh broker subscription session.
        self._subscribed_topics = frozenset()
        self._schedule_subscription_sync()
        self._notify(force=True)

    def _accept_position(self, key: TripKey, position: dict) -> None:
        """Never accept a position from a journey not selected by Routing."""
        if self._stopping or key not in self._targets:
            return
        old = self._positions.get(key)
        if old and old["position_timestamp"] > position["position_timestamp"]:
            return
        self._positions[key] = position
        self._notify()

    def visible(self) -> list[dict]:
        """Give callers a compact timetable+GPS view without stale coordinates."""
        now = time.time()
        result = []
        for key, trip in self._targets.items():
            position = self._positions.get(key)
            fresh = bool(
                position and now - position["position_timestamp"] <= HFP_STALE_SECONDS
            )
            row = {
                "route": trip.get("route"),
                "vehicle_mode": trip.get("vehicle_mode"),
                "destination": trip.get("destination"),
                "arrival_datetime": trip.get("arrival_datetime"),
                "hfp_route_id": key[0],
                "direction": key[1],
                "start_time": key[2],
                "operating_day": key[3],
                "gps_available": fresh,
            }
            if fresh:
                row.update(position)
            result.append(row)
        return result

    async def async_start(self) -> None:
        """Initialize subscriptions and start reconnecting in the background."""
        self._remove_coordinator = self.coordinator.async_add_listener(
            self._refresh_targets
        )
        self._remove_timer = async_track_time_interval(
            self.hass,
            lambda _now: (self._schedule_subscription_sync(), self._notify(force=True)),
            timedelta(seconds=30),
        )
        self._refresh_targets()
        try:
            await self.hass.async_add_executor_job(self._open_worker)
        except Exception:
            # Position tracking is optional; Routing must keep working.
            _LOGGER.exception("Unable to start optional HFP connection")
            self.connected = False

    def _close_worker(self) -> None:
        if self._client:
            self._client.disconnect()
            self._client.loop_stop()
            self._client = None

    async def async_stop(self) -> None:
        """Stop background network activity on unload or options reload."""
        self._stopping = True
        if self._remove_coordinator:
            self._remove_coordinator()
            self._remove_coordinator = None
        if self._remove_timer:
            self._remove_timer()
            self._remove_timer = None
        if self._subscription_task is not None:
            await self._subscription_task
            self._subscription_task = None
        await self.hass.async_add_executor_job(self._close_worker)
        self._listeners.clear()
        self._targets.clear()
        self._positions.clear()
