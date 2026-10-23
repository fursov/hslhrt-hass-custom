"""HSL HRT integration: Digitransit Routing v2 polling coordinator."""

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import DigitransitAuthError, DigitransitClient, DigitransitError
from .const import (
    ALL,
    CONF_API_KEY,
    COORDINATOR,
    DESTINATION,
    DOMAIN,
    MIN_TIME_BETWEEN_UPDATES,
    ROUTE,
    STOP_GTFS,
    UNDO_UPDATE_LISTENER,
    _LOGGER,
)
from .schedule import base_unique_id, parse_departures

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Prepare storage for configuration entries."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry) -> bool:
    """Set up HSL HRT from a UI config entry."""
    api_key = config_entry.data.get(CONF_API_KEY)
    if not api_key:
        # Existing v1 config entries have no API key. Trigger reauth rather
        # than requiring removal/recreation of their entities.
        raise ConfigEntryAuthFailed("Digitransit API key is required")

    client = DigitransitClient(async_get_clientsession(hass), api_key)
    coordinator = HSLHRTDataUpdateCoordinator(hass, client, config_entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    undo_listener = config_entry.add_update_listener(update_listener)
    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: undo_listener,
    }
    try:
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    except Exception:
        undo_listener()
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry) -> bool:
    """Unload platforms and unsubscribe listeners."""
    if not await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        return False
    data = hass.data[DOMAIN].pop(config_entry.entry_id, None)
    if data is not None:
        data[UNDO_UPDATE_LISTENER]()
    return True


async def update_listener(hass: HomeAssistant, config_entry) -> None:
    """Reload on configuration changes."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class HSLHRTDataUpdateCoordinator(DataUpdateCoordinator):
    """Poll a stop's next departures and notify its sensor."""

    def __init__(self, hass, client: DigitransitClient, config_entry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=MIN_TIME_BETWEEN_UPDATES
        )
        self._client = client
        self.gtfs_id = config_entry.data[STOP_GTFS]
        self.route = config_entry.data.get(ROUTE, ALL) or ALL
        self.dest = config_entry.data.get(DESTINATION, ALL) or ALL

    async def _async_update_data(self) -> dict:
        try:
            stop = await self._client.get_departures(self.gtfs_id)
            if stop is None:
                raise UpdateFailed("Stop not found in Digitransit")
            return parse_departures(stop, self.route, self.dest)
        except DigitransitAuthError as error:
            raise ConfigEntryAuthFailed("Digitransit API key was rejected") from error
        except (DigitransitError, ValueError, TypeError, OverflowError) as error:
            raise UpdateFailed(f"Unable to update HSL departure data: {error}") from error
