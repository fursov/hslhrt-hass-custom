"""Configuration and API-key reauthentication for HSL HRT."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import DigitransitAuthError, DigitransitClient, DigitransitError
from .const import (
    ALL,
    CONF_API_KEY,
    DESTINATION,
    DOMAIN,
    NAME_CODE,
    ROUTE,
    STOP_CODE,
    STOP_GTFS,
    STOP_NAME,
)
from .schedule import base_unique_id, route_matches, select_stop


def _normalized(value: str) -> str:
    """Normalize optional route and destination filters."""
    return value.strip() or ALL


async def _resolve_stop(client: DigitransitClient, name_or_code: str) -> dict | None:
    """Search first, then read patterns from the selected stop."""
    if name_or_code.upper().startswith("HSL:"):
        return await client.get_stop_info(name_or_code.upper())
    candidates = await client.search_stops(name_or_code)
    selected = select_stop(candidates, name_or_code)
    if selected is None or not selected.get("gtfsId"):
        return None
    return await client.get_stop_info(selected["gtfsId"])


class HSLHRTConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Manage stop entries while retaining their original unique IDs."""

    VERSION = 1  # Older config entries must continue to load without migration.

    async def async_step_user(self, user_input=None):
        """Create a stop entry with a valid Digitransit subscription key."""
        errors = {}
        if user_input is not None:
            stop_query = user_input[NAME_CODE].strip()
            route = _normalized(user_input[ROUTE])
            destination = _normalized(user_input[DESTINATION])
            key = user_input[CONF_API_KEY].strip()

            if not stop_query:
                errors[NAME_CODE] = "invalid_name_code"
            elif not key:
                errors[CONF_API_KEY] = "invalid_api_key"
            else:
                client = DigitransitClient(async_get_clientsession(self.hass), key)
                try:
                    stop = await _resolve_stop(client, stop_query)
                except DigitransitAuthError:
                    errors["base"] = "invalid_api_key"
                except DigitransitError:
                    errors["base"] = "cannot_connect"
                else:
                    if stop is None:
                        errors[NAME_CODE] = "invalid_name_code"
                    elif not route_matches(stop, route, destination):
                        errors[ROUTE if route.casefold() != ALL else DESTINATION] = (
                            "invalid_route"
                            if route.casefold() != ALL
                            else "invalid_destination"
                        )
                    else:
                        uid = base_unique_id(stop["gtfsId"], route, destination)
                        await self.async_set_unique_id(uid)
                        self._abort_if_unique_id_configured()
                        suffix = (
                            route.upper()
                            if route.casefold() != ALL
                            else destination.upper()
                            if destination.casefold() != ALL
                            else "ALL"
                        )
                        return self.async_create_entry(
                            title=f"{stop['name']}({stop.get('code') or ''}) {suffix}",
                            data={
                                STOP_GTFS: stop["gtfsId"],
                                STOP_NAME: stop["name"],
                                STOP_CODE: stop.get("code") or "",
                                ROUTE: route,
                                DESTINATION: destination,
                                CONF_API_KEY: key,
                            },
                        )

        schema = vol.Schema(
            {
                vol.Required(NAME_CODE, default=""): str,
                vol.Required(ROUTE, default="ALL"): str,
                vol.Required(DESTINATION, default="ALL"): str,
                vol.Required(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reauth(self, entry_data):
        """Start an API key flow for an existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Add/replace the API key without deleting the existing entry."""
        return await self._async_update_key("reauth_confirm", user_input)

    async def async_step_reconfigure(self, user_input=None):
        """Allow manual key rotation from the integration menu."""
        return await self._async_update_key("reconfigure", user_input)

    async def _async_update_key(self, step_id, user_input):
        """Validate a key against the already configured stop."""
        errors = {}
        entry = (
            self._get_reauth_entry()
            if step_id == "reauth_confirm"
            else self._get_reconfigure_entry()
        )
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            if not key:
                errors["base"] = "invalid_api_key"
            else:
                client = DigitransitClient(async_get_clientsession(self.hass), key)
                try:
                    stop = await client.get_stop_info(entry.data[STOP_GTFS])
                except DigitransitAuthError:
                    errors["base"] = "invalid_api_key"
                except DigitransitError:
                    errors["base"] = "cannot_connect"
                else:
                    if stop is None:
                        errors["base"] = "invalid_name_code"
                    else:
                        await self.async_set_unique_id(entry.unique_id)
                        self._abort_if_unique_id_mismatch()
                        return self.async_update_reload_and_abort(
                            entry, data_updates={CONF_API_KEY: key}
                        )

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )
