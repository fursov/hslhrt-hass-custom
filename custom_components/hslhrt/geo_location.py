"""Vehicle and configured-stop locations for Home Assistant's native Map card.

Vehicles are temporary (fresh HFP GPS only); configured stops remain visible
independently of HFP, so the map is useful even with no active vehicles.
Neither location type enters the permanent entity registry.
"""

import asyncio
import hashlib
import math
import time
from collections.abc import Callable

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.const import ATTR_ATTRIBUTION, UnitOfLength
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.util.location import distance as distance_meters

from .const import (
    ATTRIBUTION,
    COORDINATOR,
    CONF_MAP_STOP_DEPARTURES,
    DEFAULT_MAP_STOP_DEPARTURES,
    DOMAIN,
    GEO_LOCATION_CONTROLLER,
    HFP_MANAGER,
    STOP_CODE,
    STOP_GTFS,
    STOP_NAME,
)
from .schedule import stop_map_departure_attributes
from .vehicle import marker_label, vehicle_icon

SOURCE = DOMAIN
STOP_SOURCE = f"{DOMAIN}_stops"
SHARED_MAP_KEY = "_shared_vehicle_map"


def stop_coordinates(data: dict | None) -> tuple[float, float] | None:
    """Accept only real, finite Digitransit stop coordinates."""
    data = data or {}
    latitude, longitude = data.get("stop_latitude"), data.get("stop_longitude")
    if (
        type(latitude) not in (int, float)
        or type(longitude) not in (int, float)
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not (-90 <= latitude <= 90)
        or not (-180 <= longitude <= 180)
    ):
        return None
    return float(latitude), float(longitude)


def _distance_from_home(hass, latitude: float, longitude: float) -> float | None:
    """Report kilometers when Home Assistant has a configured home location."""
    if hass.config.latitude is None or hass.config.longitude is None:
        return None
    return round(
        distance_meters(
            hass.config.latitude, hass.config.longitude, latitude, longitude
        ) / 1000,
        1,
    )



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
    registry = hass.data[DOMAIN].get(SHARED_MAP_KEY)
    if registry is None:
        registry = HSLHRTSharedVehicleMap(hass)
        hass.data[DOMAIN][SHARED_MAP_KEY] = registry
    controller = HSLHRTMapController(
        hass, config_entry, data.get(HFP_MANAGER), async_add_entities,
        data[COORDINATOR], registry,
    )
    data[GEO_LOCATION_CONTROLLER] = controller
    controller.start()


class HSLHRTStopLocation(GeolocationEvent):
    """A selected physical stop, independent of live-vehicle GPS coverage."""

    _attr_should_poll = False
    _attr_icon = "mdi:circle-small"
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(
        self, hass, entry, coords: tuple[float, float], coordinator
    ) -> None:
        self._hass_ref = hass
        self._coordinator = coordinator
        self._departures_limit = entry.options.get(
            CONF_MAP_STOP_DEPARTURES, DEFAULT_MAP_STOP_DEPARTURES
        )
        self._latitude, self._longitude = coords
        self._stop_name = entry.data.get(STOP_NAME, "")
        self._stop_code = entry.data.get(STOP_CODE, "")
        self._stop_gtfs = entry.data.get(STOP_GTFS, "")
        signature = hashlib.sha256(
            (entry.entry_id + ":" + self._stop_gtfs).encode()
        ).hexdigest()[:16]
        self.entity_id = f"geo_location.hslhrt_stop_{signature}"
        self._attr_name = f"{self._stop_name} ({self._stop_code})"

    @property
    def source(self) -> str:
        return STOP_SOURCE

    @property
    def latitude(self) -> float:
        return self._latitude

    @property
    def longitude(self) -> float:
        return self._longitude

    @property
    def distance(self) -> float | None:
        return _distance_from_home(self._hass_ref, self.latitude, self.longitude)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "stop_name": self._stop_name,
            "stop_code": self._stop_code,
            "stop_gtfs": self._stop_gtfs,
            **stop_map_departure_attributes(
                self._coordinator.data, time.time(), self._departures_limit
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Keep More Info current even between Digitransit API polls."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self._on_timetable_update)
        )
        self.async_on_remove(
            async_track_utc_time_change(
                self.hass, self._on_minute_tick, second=0
            )
        )

    @callback
    def _on_timetable_update(self) -> None:
        self.async_write_ha_state()

    @callback
    def _on_minute_tick(self, _now) -> None:
        self.async_write_ha_state()

    def update_location(self, coords: tuple[float, float]) -> None:
        if coords == (self._latitude, self._longitude):
            return
        self._latitude, self._longitude = coords
        if self.hass is not None:
            self.async_write_ha_state()


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
        self._retired = False
        # Physical trip identity is independent of the configured stop.
        signature = hashlib.sha256(":".join(key).encode()).hexdigest()[:16]
        self.entity_id = f"geo_location.hslhrt_{signature}"
        self._attr_name = (
            f"HSL {position.get('route', '?')} "
            f"{position.get('destination') or ''}"
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
        return _distance_from_home(self._hass_ref, self.latitude, self.longitude)

    @property
    def extra_state_attributes(self) -> dict:
        """Expose useful public journey details, but no API key."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "stop_code": self._position.get("next_tracked_stop"),
            "tracked_stop_codes": self._position.get("tracked_stop_codes", []),
            "next_tracked_stop": self._position.get("next_tracked_stop"),
            "next_tracked_stop_name": self._position.get("next_tracked_stop_name"),
            "distance_to_next_tracked_stop_km": self._position.get(
                "distance_to_next_tracked_stop_km"
            ),
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


class HSLHRTSharedVehicleMap:
    """Deduplicate vehicle markers across all stop config entries."""

    def __init__(self, hass) -> None:
        self._hass = hass
        self._controllers = {}
        self._owner_id = None
        self._entities = {}
        self._task = None
        self._dirty = False

    @callback
    def register(self, controller) -> None:
        self._controllers[controller._entry.entry_id] = controller
        self.schedule_sync()

    @callback
    def schedule_sync(self) -> None:
        """Only invoke from the Home Assistant event-loop thread."""
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = self._hass.async_create_task(self._async_sync())

    async def unregister(self, controller) -> None:
        """Retire old platform markers before a different entry takes ownership."""
        ident = controller._entry.entry_id
        if self._controllers.get(ident) is not controller:
            return
        if self._task is not None:
            await self._task
        self._controllers.pop(ident)
        if self._owner_id == ident:
            self._owner_id = None
            for entity in self._entities.values():
                entity._retired = True
                if entity.hass is not None:
                    await entity.async_remove(force_remove=True)
            self._entities.clear()
        if self._controllers:
            self.schedule_sync()
        else:
            self._hass.data[DOMAIN].pop(SHARED_MAP_KEY, None)

    def _snapshot(self) -> dict:
        """Select freshest GPS and collect configured stops per exact trip."""
        now = time.time()
        positions = {}
        tracked = {}
        for controller in self._controllers.values():
            if controller._manager is None:
                continue
            stop = controller._entry.data
            code = stop.get(STOP_CODE) or ""
            name = stop.get(STOP_NAME) or ""
            stop_id = stop.get(STOP_GTFS) or controller._entry.entry_id
            coords = stop_coordinates(controller._coordinator.data)
            for key, row in active_positions(controller._manager.visible()).items():
                previous = positions.get(key)
                if previous is None or (
                    row["position_timestamp"] > previous["position_timestamp"]
                ):
                    positions[key] = row
                eta = row.get("arrival_timestamp")
                if type(eta) not in (int, float) or not math.isfinite(eta):
                    eta = None
                stops = tracked.setdefault(key, {})
                prior = stops.get(stop_id)
                if prior is None or (
                    eta is not None
                    and (prior["eta"] is None or eta < prior["eta"])
                ):
                    stops[stop_id] = {
                        "code": code, "name": name, "eta": eta, "coords": coords
                    }
        for key, position in tuple(positions.items()):
            stops = list(tracked[key].values())
            candidates = [
                s for s in stops if s["eta"] is not None and s["eta"] >= now
            ]
            candidates.sort(key=lambda s: s["eta"])
            nearest_upcoming = candidates[0] if candidates else None
            distance = None
            if nearest_upcoming is not None and nearest_upcoming["coords"]:
                lat, lon = nearest_upcoming["coords"]
                distance = round(
                    distance_meters(position["latitude"], position["longitude"],
                                    lat, lon) / 1000, 2
                )
            positions[key] = {
                **position,
                "tracked_stop_codes": sorted({
                    s["code"] for s in stops if s["code"]
                }),
                "next_tracked_stop": (
                    nearest_upcoming["code"] if nearest_upcoming else None
                ),
                "next_tracked_stop_name": (
                    nearest_upcoming["name"] if nearest_upcoming else None
                ),
                "distance_to_next_tracked_stop_km": distance,
            }
        return positions

    async def _async_sync(self) -> None:
        while self._dirty:
            self._dirty = False
            owner = self._controllers.get(self._owner_id)
            if owner is None:
                for controller in self._controllers.values():
                    if controller._manager is not None and not controller._stopped:
                        owner = controller
                        self._owner_id = controller._entry.entry_id
                        break
            desired = self._snapshot() if owner is not None else {}
            for key in tuple(self._entities):
                if key not in desired:
                    entity = self._entities.pop(key)
                    entity._retired = True
                    if entity.hass is not None:
                        await entity.async_remove(force_remove=True)
            additions = []
            for key, row in desired.items():
                if key in self._entities:
                    self._entities[key].update_position(row)
                else:
                    entity = HSLHRTVehicleLocation(
                        self._hass, owner._entry, key, row
                    )
                    self._entities[key] = entity
                    additions.append(entity)
            if additions:
                owner._async_add_entities(additions)


class HSLHRTMapController:
    """Reconcile Home Assistant map entities with the current HFP positions."""

    def __init__(
        self, hass, entry, manager, async_add_entities: Callable, coordinator,
        registry: HSLHRTSharedVehicleMap,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._manager = manager
        self._coordinator = coordinator
        self._registry = registry
        self._async_add_entities = async_add_entities
        self._stop_entity: HSLHRTStopLocation | None = None
        self._remove_coordinator: Callable | None = None
        self._unsubscribe: Callable | None = None
        self._task: asyncio.Task | None = None
        self._dirty = False
        self._stopped = False

    def start(self) -> None:
        """Receive the same throttled GPS updates as the tracked-vehicles sensor."""
        self._remove_coordinator = self._coordinator.async_add_listener(
            self._schedule_sync
        )
        if self._manager is not None:
            self._unsubscribe = self._manager.add_listener(self._schedule_sync)
        self._registry.register(self)
        self._schedule_sync()

    @callback
    def _schedule_sync(self) -> None:
        """Keep stop location fresh and reconcile shared vehicles."""
        if self._stopped:
            return
        self._registry.schedule_sync()
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = self._hass.async_create_task(self._async_sync())

    async def _async_sync(self) -> None:
        """Add, update and remove markers without retaining stale entities."""
        while self._dirty and not self._stopped:
            self._dirty = False
            coords = stop_coordinates(self._coordinator.data)
            if coords is None and self._stop_entity is not None:
                entity = self._stop_entity
                self._stop_entity = None
                if entity.hass is not None:
                    await entity.async_remove(force_remove=True)
            elif coords is not None:
                if self._stop_entity is None:
                    self._stop_entity = HSLHRTStopLocation(
                        self._hass, self._entry, coords, self._coordinator
                    )
                    self._async_add_entities([self._stop_entity])
                else:
                    self._stop_entity.update_location(coords)


    async def async_stop(self) -> None:
        """Unsubscribe before the HA platform unload removes its entities."""
        self._stopped = True
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._remove_coordinator is not None:
            self._remove_coordinator()
            self._remove_coordinator = None
        if self._task is not None:
            await self._task
            self._task = None
        await self._registry.unregister(self)
        self._stop_entity = None
