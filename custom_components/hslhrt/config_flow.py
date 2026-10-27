"""HSL stop configuration, disambiguation, options and API-key flows."""

import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .client import DigitransitAuthError, DigitransitClient, DigitransitError
from .configuration import (
    available_routes,
    canonical_route_filter,
    default_selected_routes,
    scan_interval_minutes,
    stop_candidates,
)
from .const import (
    ALL,
    CONF_API_KEY,
    CONF_HFP_ENABLED,
    CONF_HFP_HORIZON,
    CONF_HFP_PER_ROUTE,
    CONF_MAP_STOP_DEPARTURES,
    CONF_DESTINATION_FILTER,
    CONF_ROUTES,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_STOP,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_HFP_HORIZON,
    DEFAULT_HFP_PER_ROUTE,
    DEFAULT_MAP_STOP_DEPARTURES,
    MAX_MAP_STOP_DEPARTURES,
    DESTINATION,
    DOMAIN,
    NAME_CODE,
    ROUTE,
    STOP_CODE,
    STOP_GTFS,
    STOP_NAME,
)
from .schedule import base_unique_id, route_matches


def _normalized(value: str) -> str:
    """Normalize a route or destination filter."""
    return value.strip() or ALL


HFP_HORIZON_CHOICES = (15, 30, 45, 60, 90)
HFP_PER_ROUTE_CHOICES = (1, 2, 3, 4, 5)
MAP_STOP_DEPARTURE_CHOICES = tuple(range(1, MAX_MAP_STOP_DEPARTURES + 1))


def _dropdown_for_int_choices(values: tuple[int, ...]) -> SelectSelector:
    """Render small integer option sets as compact drop-downs.

    SelectSelector sends strings through the frontend; conversion back to
    integers happens only when saving the options entry.
    """
    return SelectSelector(
        SelectSelectorConfig(
            options=[str(value) for value in values],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _stop_title(stop: dict) -> str:
    """Keep public stop code and GTFS ID visible for duplicate stop names."""
    return (
        f"{stop.get('name') or 'Unknown'} "
        f"({stop.get('code') or 'no code'}) — {stop['gtfsId']}"
    )


class HSLHRTConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Manage stop configuration without migrating existing entry IDs."""

    VERSION = 1

    def __init__(self) -> None:
        """Hold pending stop choices only for the current UI flow."""
        self._pending: dict | None = None
        self._candidates: dict[str, dict] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Expose the options flow on existing stop entries."""
        return HSLHRTOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Search for stops and offer a choice if the name is ambiguous."""
        errors = {}
        if user_input is not None:
            name = user_input[NAME_CODE].strip()
            key = user_input[CONF_API_KEY].strip()
            try:
                route = canonical_route_filter(_normalized(user_input[ROUTE]))
            except ValueError:
                errors[ROUTE] = "invalid_route"
            if not name:
                errors[NAME_CODE] = "invalid_name_code"
            elif not key:
                errors[CONF_API_KEY] = "invalid_api_key"
            elif not errors:
                destination = _normalized(user_input[DESTINATION])
                client = DigitransitClient(async_get_clientsession(self.hass), key)
                try:
                    if name.upper().startswith("HSL:"):
                        stop = await client.get_stop_info(name.upper())
                        candidates = [stop] if stop is not None else []
                    elif re.fullmatch(r"[A-Za-z]{1,3}[0-9]{3,5}", name):
                        # Public stop codes (E4971, H0209) are not GTFS IDs.
                        # GraphQL stops(name:) does not resolve them reliably.
                        candidate = await client.search_stop_by_code(name)
                        candidates = [candidate] if candidate else []
                    else:
                        candidates = await client.search_stops(name)
                except DigitransitAuthError:
                    errors["base"] = "invalid_api_key"
                except DigitransitError:
                    errors["base"] = "cannot_connect"
                else:
                    choices = stop_candidates(candidates)
                    if not choices:
                        errors[NAME_CODE] = "invalid_name_code"
                    else:
                        self._pending = {
                            ROUTE: route,
                            DESTINATION: destination,
                            CONF_API_KEY: key,
                        }
                        self._candidates = {
                            stop["gtfsId"]: stop for stop in choices
                        }
                        # Only code/GTFS ID is unique. A stop *name* can match
                        # two or more platforms, even if names are identical.
                        exact_code = next(
                            (
                                stop
                                for stop in choices
                                if name.casefold()
                                in (
                                    (stop.get("code") or "").casefold(),
                                    stop["gtfsId"].casefold(),
                                )
                            ),
                            None,
                        )
                        if exact_code is not None or len(choices) == 1:
                            return await self._async_create_stop(
                                exact_code or choices[0]
                            )
                        return await self.async_step_select_stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(NAME_CODE, default=""): str,
                    vol.Required(ROUTE, default=ALL.upper()): str,
                    vol.Required(DESTINATION, default=ALL.upper()): str,
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_stop(self, user_input=None):
        """Let the user disambiguate identical or similar stop names."""
        if not self._pending or not self._candidates:
            return self.async_abort(reason="missing_stop_selection")

        errors = {}
        if user_input is not None:
            selected = self._candidates.get(user_input.get(CONF_SELECTED_STOP))
            if selected is None:
                errors["base"] = "invalid_name_code"
            else:
                return await self._async_create_stop(selected)

        choices = [
            SelectOptionDict(value=gtfs_id, label=_stop_title(stop))
            for gtfs_id, stop in self._candidates.items()
        ]
        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_STOP): SelectSelector(
                        SelectSelectorConfig(
                            options=choices, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def _async_create_stop(self, candidate):
        """Resolve selected stop details and create a validated entry."""
        assert self._pending is not None
        client = DigitransitClient(
            async_get_clientsession(self.hass), self._pending[CONF_API_KEY]
        )
        is_selection = len(self._candidates) > 1
        step_id = "select_stop" if is_selection else "user"
        try:
            stop = await client.get_stop_info(candidate["gtfsId"])
        except DigitransitAuthError:
            error = "invalid_api_key"
            stop = None
        except DigitransitError:
            error = "cannot_connect"
            stop = None
        else:
            error = "invalid_name_code" if stop is None else None
            # Reject fuzzy geocoder results for a different physical stop.
            requested_code = candidate.get("code")
            if (
                error is None
                and requested_code
                and (stop.get("code") or "").casefold()
                != requested_code.casefold()
            ):
                error = "invalid_name_code"

        if error is not None:
            if is_selection:
                return self.async_show_form(
                    step_id="select_stop",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_SELECTED_STOP): SelectSelector(
                                SelectSelectorConfig(
                                    options=[
                                        SelectOptionDict(
                                            value=ident, label=_stop_title(value)
                                        )
                                        for ident, value in self._candidates.items()
                                    ],
                                    mode=SelectSelectorMode.DROPDOWN,
                                )
                            )
                        }
                    ),
                    errors={"base": error},
                )
            # Do not persist or echo API keys on a failed form.
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(NAME_CODE): str,
                        vol.Required(ROUTE, default=ALL.upper()): str,
                        vol.Required(DESTINATION, default=ALL.upper()): str,
                        vol.Required(CONF_API_KEY): str,
                    }
                ),
                errors={"base": error},
            )

        route = self._pending[ROUTE]
        destination = self._pending[DESTINATION]
        if not route_matches(stop, route, destination):
            error = "invalid_route" if route.casefold() != ALL else "invalid_destination"
            if is_selection:
                # Destination/route is unsuitable for the chosen platform.
                return await self._show_stop_error(error)
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(NAME_CODE): str,
                        vol.Required(ROUTE, default=ALL.upper()): str,
                        vol.Required(DESTINATION, default=ALL.upper()): str,
                        vol.Required(CONF_API_KEY): str,
                    }
                ),
                errors={"base": error},
            )

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
                CONF_API_KEY: self._pending[CONF_API_KEY],
            },
        )

    async def _show_stop_error(self, error: str):
        """Redisplay the stop picker with a validation error."""
        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SELECTED_STOP): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=key, label=_stop_title(stop))
                                for key, stop in self._candidates.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors={"base": error},
        )

    async def async_step_reauth(self, entry_data):
        """Start reauthentication without deleting existing stop entries."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Add or rotate the subscription key."""
        return await self._async_update_key("reauth_confirm", user_input)

    async def async_step_reconfigure(self, user_input=None):
        """Support explicit subscription-key rotation."""
        return await self._async_update_key("reconfigure", user_input)

    async def _async_update_key(self, step_id, user_input):
        """Verify a key against the existing stop without losing options."""
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


class HSLHRTOptionsFlow(config_entries.OptionsFlow):
    """Manage route/destination filtering and per-entry poll interval."""

    def __init__(self) -> None:
        """Create temporary route choices."""
        self._available_routes: list[str] | None = None

    async def async_step_init(self, user_input=None):
        """Allow multiple routes and interval selection without new entities."""
        entry = self.config_entry
        errors = {}
        previously_selected = default_selected_routes(entry.data, entry.options)

        if self._available_routes is None:
            client = DigitransitClient(
                async_get_clientsession(self.hass), entry.data[CONF_API_KEY]
            )
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
                    self._available_routes = available_routes(stop)

        if self._available_routes is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        all_routes = sorted(
            {*self._available_routes, *previously_selected}, key=str.casefold
        )
        if user_input is not None:
            selected = user_input.get(CONF_ROUTES, [])
            valid_routes = {route.casefold() for route in all_routes}
            if not isinstance(selected, list) or any(
                not isinstance(route, str)
                or route.casefold() not in valid_routes
                for route in selected
            ):
                errors[CONF_ROUTES] = "invalid_route"
            horizon = str(
                user_input.get(CONF_HFP_HORIZON, DEFAULT_HFP_HORIZON)
            )
            per_route = str(
                user_input.get(CONF_HFP_PER_ROUTE, DEFAULT_HFP_PER_ROUTE)
            )
            if horizon not in {str(value) for value in HFP_HORIZON_CHOICES}:
                errors[CONF_HFP_HORIZON] = "invalid_selection"
            if per_route not in {str(value) for value in HFP_PER_ROUTE_CHOICES}:
                errors[CONF_HFP_PER_ROUTE] = "invalid_selection"
            stop_departures = str(
                user_input.get(
                    CONF_MAP_STOP_DEPARTURES, DEFAULT_MAP_STOP_DEPARTURES
                )
            )
            if stop_departures not in {
                str(value) for value in MAP_STOP_DEPARTURE_CHOICES
            }:
                errors[CONF_MAP_STOP_DEPARTURES] = "invalid_selection"
            if not errors:
                destination = _normalized(
                    user_input.get(CONF_DESTINATION_FILTER, ALL)
                )
                interval = user_input[CONF_SCAN_INTERVAL]
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_ROUTES: sorted(set(selected), key=str.casefold),
                        CONF_DESTINATION_FILTER: destination,
                        CONF_SCAN_INTERVAL: interval,
                        CONF_HFP_ENABLED: user_input.get(CONF_HFP_ENABLED, False),
                        # Preserve the existing integer settings contract.
                        CONF_HFP_HORIZON: int(horizon),
                        CONF_HFP_PER_ROUTE: int(per_route),
                        CONF_MAP_STOP_DEPARTURES: int(stop_departures),
                    },
                )

        selected_default = (
            entry.options.get(CONF_ROUTES, previously_selected)
            if user_input is None
            else user_input.get(CONF_ROUTES, previously_selected)
        )
        destination_default = (
            entry.options.get(
                CONF_DESTINATION_FILTER, entry.data.get(DESTINATION, ALL)
            )
            if user_input is None
            else user_input.get(CONF_DESTINATION_FILTER, ALL)
        )
        interval_default = (
            scan_interval_minutes(entry.options)
            if user_input is None
            else user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_ROUTES, default=selected_default): SelectSelector(
                    SelectSelectorConfig(
                        options=all_routes,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_DESTINATION_FILTER, default=destination_default
                ): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=interval_default
                ): vol.In([1, 2, 3, 5, 10, 15, 30]),
                vol.Optional(
                    CONF_HFP_ENABLED,
                    default=entry.options.get(CONF_HFP_ENABLED, False),
                ): bool,
                vol.Required(
                    CONF_HFP_HORIZON,
                    default=str(
                        user_input.get(CONF_HFP_HORIZON, DEFAULT_HFP_HORIZON)
                        if user_input is not None
                        else entry.options.get(CONF_HFP_HORIZON, DEFAULT_HFP_HORIZON)
                    ),
                ): _dropdown_for_int_choices(HFP_HORIZON_CHOICES),
                vol.Required(
                    CONF_HFP_PER_ROUTE,
                    default=str(
                        user_input.get(CONF_HFP_PER_ROUTE, DEFAULT_HFP_PER_ROUTE)
                        if user_input is not None
                        else entry.options.get(CONF_HFP_PER_ROUTE, DEFAULT_HFP_PER_ROUTE)
                    ),
                ): _dropdown_for_int_choices(HFP_PER_ROUTE_CHOICES),
                vol.Required(
                    CONF_MAP_STOP_DEPARTURES,
                    default=str(
                        user_input.get(
                            CONF_MAP_STOP_DEPARTURES, DEFAULT_MAP_STOP_DEPARTURES
                        )
                        if user_input is not None
                        else entry.options.get(
                            CONF_MAP_STOP_DEPARTURES, DEFAULT_MAP_STOP_DEPARTURES
                        )
                    ),
                ): _dropdown_for_int_choices(MAP_STOP_DEPARTURE_CHOICES),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
