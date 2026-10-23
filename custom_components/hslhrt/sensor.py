"""Sensors for a configured Digitransit stop and optional route filter."""

import math
import time
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION, UnitOfTime
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ALL,
    ATTR_ARR_TIME,
    ATTR_DEST,
    ATTR_ROUTE,
    ATTR_STOP_CODE,
    ATTR_STOP_GTFS,
    ATTR_STOP_NAME,
    ATTRIBUTION,
    COORDINATOR,
    DESTINATION,
    DICT_KEY_ARRIVAL,
    DICT_KEY_DEST,
    DICT_KEY_ROUTE,
    DOMAIN,
    HFP_MANAGER,
    MAX_DEPARTURES_ATTRIBUTE,
    MAX_LEGACY_ROUTES,
    STOP_CODE,
    STOP_GTFS,
    STOP_NAME,
)
from .configuration import effective_filters
from .schedule import upcoming_departures


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add the legacy route sensor and two new arrival sensors."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = data[COORDINATOR]
    entities = [
        HSLHRTRouteSensor(coordinator, config_entry),
        HSLHRTNextArrivalSensor(coordinator, config_entry),
        HSLHRTMinutesUntilArrivalSensor(coordinator, config_entry),
    ]
    if (manager := data.get(HFP_MANAGER)) is not None:
        entities.append(HSLHRTTrackedVehiclesSensor(coordinator, config_entry, manager))
    async_add_entities(entities)


class HSLHRTBaseSensor(CoordinatorEntity, SensorEntity):
    """Share naming and coordinator updates across the three sensors."""

    _attr_has_entity_name = False

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator)
        config = config_entry.data
        route, destination, routes = effective_filters(
            config, config_entry.options
        )
        suffix = (
            ", ".join(routes)
            if routes
            else route.upper()
            if routes is None and route.casefold() != ALL
            else destination.upper()
            if destination.casefold() != ALL
            else "ALL"
        )
        self._base_name = (
            f"{config.get(STOP_NAME, 'Stop')}({config.get(STOP_CODE, '')}) {suffix}"
        )
        # For old entries this is unchanged from v0.4.0. New entities
        # receive suffixes derived from the same stable config-entry ID.
        self._base_unique_id = config_entry.unique_id or config_entry.entry_id

    def _upcoming(self) -> list[dict]:
        """Return future arrivals from the coordinator's latest response."""
        return upcoming_departures(self.coordinator.data, time.time())


class HSLHRTRouteSensor(HSLHRTBaseSensor):
    """Legacy text state: number of the next arriving route."""

    _attr_icon = "mdi:bus"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = self._base_name
        self._attr_unique_id = self._base_unique_id

    @property
    def native_value(self) -> str | None:
        """Return the route number, updated on each coordinator refresh."""
        departures = self._upcoming()
        return departures[0][DICT_KEY_ROUTE] if departures else None

    @property
    def extra_state_attributes(self) -> dict:
        """Preserve old attributes and expose a short structured timetable."""
        data = self.coordinator.data or {}
        upcoming = self._upcoming()
        attributes = {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            ATTR_STOP_NAME: data.get(STOP_NAME),
            ATTR_STOP_CODE: data.get(STOP_CODE),
            ATTR_STOP_GTFS: data.get(STOP_GTFS),
            "ROUTES": [],
            "departures": [],
        }

        def legacy_row(departure: dict) -> dict:
            return {
                ATTR_ROUTE: departure[DICT_KEY_ROUTE],
                ATTR_DEST: departure[DICT_KEY_DEST] or "Unavailable",
                ATTR_ARR_TIME: departure[DICT_KEY_ARRIVAL],
                "arrival_datetime": departure["arrival_datetime"],
                "realtime": departure["realtime"],
            }

        def detailed_row(departure: dict) -> dict:
            return {
                "route": departure[DICT_KEY_ROUTE],
                "destination": departure[DICT_KEY_DEST] or "Unavailable",
                "arrival_time": departure[DICT_KEY_ARRIVAL],
                "arrival_datetime": departure["arrival_datetime"],
                "scheduled_datetime": datetime.fromtimestamp(
                    departure["scheduled_timestamp"], tz=timezone.utc
                ).isoformat(),
                "realtime": departure["realtime"],
                "delay_seconds": departure["delay_seconds"],
            }

        if upcoming:
            # Keep the legacy attribute names and exclude the first bus from
            # ROUTES, as existing Lovelace cards expect.
            attributes.update(legacy_row(upcoming[0]))
            attributes["ROUTES"] = [
                legacy_row(departure)
                for departure in upcoming[1 : MAX_LEGACY_ROUTES + 1]
            ]

        attributes["departures"] = [
            detailed_row(departure)
            for departure in upcoming[:MAX_DEPARTURES_ATTRIBUTE]
        ]
        return attributes


class HSLHRTNextArrivalSensor(HSLHRTBaseSensor):
    """Timestamp of the next scheduled or real-time arrival."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = f"{self._base_name} Next arrival"
        self._attr_unique_id = f"{self._base_unique_id}_next_arrival"

    @property
    def native_value(self) -> datetime | None:
        """Return a timezone-aware UTC datetime for Home Assistant."""
        departures = self._upcoming()
        if not departures:
            return None
        return datetime.fromtimestamp(
            departures[0]["arrival_timestamp"], tz=timezone.utc
        )


class HSLHRTMinutesUntilArrivalSensor(HSLHRTBaseSensor):
    """Rounded-up number of minutes until the next arrival."""

    _attr_icon = "mdi:timer-outline"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator, config_entry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = f"{self._base_name} Minutes until arrival"
        self._attr_unique_id = f"{self._base_unique_id}_minutes_until_arrival"

    @property
    def native_value(self) -> int | None:
        """Return the remaining whole minutes, updated every API poll."""
        now_timestamp = time.time()
        departures = upcoming_departures(self.coordinator.data, now_timestamp)
        if not departures:
            return None
        return max(
            0, math.ceil((departures[0]["arrival_timestamp"] - now_timestamp) / 60)
        )


class HSLHRTTrackedVehiclesSensor(HSLHRTBaseSensor):
    """Number of upcoming selected journeys with recent, exact GPS matches.

    A compact list of selected journeys is provided even if no GPS is known.
    Dynamic geo_location entities are intentionally deferred to PR9.
    """

    _attr_icon = "mdi:map-marker-path"
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator, config_entry, manager) -> None:
        super().__init__(coordinator, config_entry)
        self._manager = manager
        self._remove_hfp_listener = None
        self._attr_name = f"{self._base_name} Tracked vehicles"
        self._attr_unique_id = f"{self._base_unique_id}_tracked_vehicles"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_hfp_listener = self._manager.add_listener(
            self.async_write_ha_state
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_hfp_listener:
            self._remove_hfp_listener()
            self._remove_hfp_listener = None
        await super().async_will_remove_from_hass()

    @property
    def native_value(self) -> int:
        """Return the number of selected journeys with fresh vehicle GPS."""
        return sum(
            row["gps_available"] for row in self._manager.visible()
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Expose bounded per-journey locations and connection diagnostics."""
        rows = self._manager.visible()
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "hfp_connected": self._manager.connected,
            "selected_journeys": len(rows),
            "vehicles": rows[:32],
        }
