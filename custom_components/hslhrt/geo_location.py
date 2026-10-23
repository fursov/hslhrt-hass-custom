"""Temporary HFP vehicle locations for Home Assistant's native Map card.

This platform creates entities only for *fresh* HFP vehicle positions. Unlike
permanent sensors, journey entities have no unique_id and do not enter the
entity registry. When a journey ends or GPS expires, its entity is removed.
"""

import asyncio
import hashlib
import math
from collections.abc import Callable

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.const import ATTR_ATTRIBUTION, UnitOfLength
from homeassistant.util.location import distance as distance_meters

from .const import ATTRIBUTION, DOMAIN, GEO_LOCATION_CONTROLLER, HFP_MANAGER
from .vehicle import marker_label, vehicle_icon

SOURCE = DOMAIN


def journey_key(row: dict) -> tuple[str, str, str, str] | None:
    """Return the exact journey identity used by the HFP manager."""
    keys = ("hfp_route_id", "direction", "start_time", "operating_day")
    values = tuple(row.get(name) for name in keys)
    return values if all(isinstance(value, str) and value for value in values) else None


def active_positions(rows: list[dict]) -> dict[tuple[str, str, str, str], dict]:
    """Filter absent/malformed coordinates; never display stale vehicle GPS."""
    active = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("gps_available"):
            continue
        key = journey_key(row)
        latitude, longitude = row.get("latitude"), row.get("longitude")
        if (
            key is None
            or type(latitude) not in (int, float)
            or type(longitude) not in (int, float)
            or not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not (-90 <= latitude <= 90)
            or not (-180 <= longitude <= 180)
        ):
            continue
        active[key] = row
    return active


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Watch optional HFP updates and publish temporary geolocation entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    if (manager := data.get(HFP_MANAGER)) is None:
        return
    controller = HSLHRTMapController(
        hass, config_entry, manager, async_add_entities
    )
    data[GEO_LOCATION_CONTROLLER] = controller
    controller.start()


class HSLHRTVehicleLocation(GeolocationEvent):
    """A vehicle on one scheduled journey, not a persistent device."""

    _attr_should_poll = False
    _attr_icon = "mdi:map-marker"
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, hass, entry, key, position) -> None:
        """Give this short-lived journey an unregistered deterministic entity ID."""
        self._hass_ref = hass
        self._key = key
        self._position = position
        self._stop_code = entry.data.get("stop_code", "")
        self._retired = False
        signature = hashlib.sha256(
            (entry.entry_id + ":" + ":".join(key)).encode()
        ).hexdigest()[:16]
        self.entity_id = f"geo_location.hslhrt_{signature}"
        self._attr_name = (
            f"HSL {position.get('route', '?')} "
            f"{position.get('destination') or ''} "
            f"({entry.data.get('stop_code', '')})"
        )

    @property
    def icon(self) -> str:
        """Match the documented Digitransit transport mode where known."""
        return vehicle_icon(self._position.get("vehicle_mode"))

    @property
    def source(self) -> str:
        """Map card's geolocation source filter."""
        return SOURCE

    @property
    def latitude(self) -> float:
        return self._position["latitude"]

    @property
    def longitude(self) -> float:
        return self._position["longitude"]

    @property
    def distance(self) -> float | None:
        """Distance in km from the configured Home Assistant location."""
        latitude = self._hass_ref.config.latitude
        longitude = self._hass_ref.config.longitude
        if latitude is None or longitude is None:
            return None
        return round(
            distance_meters(
                latitude, longitude, self.latitude, self.longitude
            ) / 1000,
            1,
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Expose useful public journey details, but no API key."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "stop_code": self._stop_code,
            "route": self._position.get("route"),
            "vehicle_mode": self._position.get("vehicle_mode"),
            "marker_label": marker_label(
                self._position.get("route"), self._position.get("vehicle_mode")
            ),
            "destination": self._position.get("destination"),
            "arrival_datetime": self._position.get("arrival_datetime"),
            "hfp_route_id": self._key[0],
            "direction": self._key[1],
            "start_time": self._key[2],
            "operating_day": self._key[3],
            "operator": self._position.get("operator"),
            "vehicle": self._position.get("vehicle"),
            "speed_m_s": self._position.get("speed_m_s"),
            "heading": self._position.get("heading"),
            "position_timestamp": self._position.get("position_timestamp"),
        }

    def update_position(self, row: dict) -> None:
        """Update the same entity instead of creating map-marker duplicates."""
        self._position = row
        if self.hass is not None and not self._retired:
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Remove a marker if its GPS expired during asynchronous registration."""
        await super().async_added_to_hass()
        if self._retired:
            await self.async_remove(force_remove=True)


class HSLHRTMapController:
    """Reconcile Home Assistant map entities with the current HFP positions."""

    def __init__(
        self, hass, entry, manager, async_add_entities: Callable
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._manager = manager
        self._async_add_entities = async_add_entities
        self._entities: dict[tuple[str, str, str, str], HSLHRTVehicleLocation] = {}
        self._unsubscribe: Callable | None = None
        self._task: asyncio.Task | None = None
        self._dirty = False
        self._stopped = False

    def start(self) -> None:
        """Receive the same throttled GPS updates as the tracked-vehicles sensor."""
        self._unsubscribe = self._manager.add_listener(self._schedule_sync)
        self._schedule_sync()

    def _schedule_sync(self) -> None:
        """Coalesce rapid MQTT messages into one serialized reconciliation task."""
        if self._stopped:
            return
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = self._hass.async_create_task(self._async_sync())

    async def _async_sync(self) -> None:
        """Add, update and remove markers without retaining stale entities."""
        while self._dirty and not self._stopped:
            self._dirty = False
            active = active_positions(self._manager.visible())
            desired = set(active)
            for key in tuple(self._entities):
                if key not in desired:
                    entity = self._entities.pop(key)
                    entity._retired = True
                    if entity.hass is not None:
                        await entity.async_remove(force_remove=True)

            additions = []
            for key, position in active.items():
                if key in self._entities:
                    self._entities[key].update_position(position)
                    continue
                entity = HSLHRTVehicleLocation(
                    self._hass, self._entry, key, position
                )
                self._entities[key] = entity
                additions.append(entity)
            if additions and not self._stopped:
                self._async_add_entities(additions)

    async def async_stop(self) -> None:
        """Unsubscribe before the HA platform unload removes its entities."""
        self._stopped = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._task is not None:
            await self._task
            self._task = None
        self._entities.clear()
