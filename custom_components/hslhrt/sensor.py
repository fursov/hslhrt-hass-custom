"""HSL HRT sensor platform, preserving the original stop/route entity model."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
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
    DICT_KEY_ROUTES,
    DOMAIN,
    ROUTE,
    STOP_CODE,
    STOP_GTFS,
    STOP_NAME,
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up one sensor for the stop/route filter."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    async_add_entities([HSLHRTRouteSensor(coordinator, config_entry)])


class HSLHRTRouteSensor(CoordinatorEntity, SensorEntity):
    """Expose the next route and upcoming departure attributes."""

    _attr_icon = "mdi:bus"
    _attr_has_entity_name = False

    def __init__(self, coordinator, config_entry):
        super().__init__(coordinator)
        data = config_entry.data
        route = data.get(ROUTE) or ALL
        destination = data.get(DESTINATION) or ALL
        suffix = (
            route.upper()
            if route.lower() != ALL
            else destination.upper()
            if destination.lower() != ALL
            else "ALL"
        )
        self._attr_name = (
            f"{data.get(STOP_NAME, 'Stop')}({data.get(STOP_CODE, '')}) {suffix}"
        )
        self._attr_unique_id = config_entry.unique_id or config_entry.entry_id

    @property
    def native_value(self):
        """Return the line of the next arriving vehicle."""
        routes = (self.coordinator.data or {}).get(DICT_KEY_ROUTES) or []
        return routes[0][DICT_KEY_ROUTE] if routes else None

    @property
    def extra_state_attributes(self):
        """Provide legacy attribute names plus timestamp metadata."""
        data = self.coordinator.data or {}
        routes = data.get(DICT_KEY_ROUTES) or []
        attributes = {ATTR_ATTRIBUTION: ATTRIBUTION}
        if not routes:
            return attributes

        def format_route(departure):
            return {
                ATTR_ROUTE: departure[DICT_KEY_ROUTE],
                ATTR_DEST: departure[DICT_KEY_DEST] or "Unavailable",
                ATTR_ARR_TIME: departure[DICT_KEY_ARRIVAL],
                "arrival_datetime": departure["arrival_datetime"],
                "realtime": departure["realtime"],
            }

        attributes.update(format_route(routes[0]))
        attributes.update(
            {
                "ROUTES": [format_route(departure) for departure in routes[1:]],
                ATTR_STOP_NAME: data.get(STOP_NAME),
                ATTR_STOP_CODE: data.get(STOP_CODE),
                ATTR_STOP_GTFS: data.get(STOP_GTFS),
            }
        )
        return attributes
