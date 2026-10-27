"""Pure configuration helpers shared by the flows and entities."""

import re

from .const import (
    ALL,
    CONF_DESTINATION_FILTER,
    CONF_ROUTES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DESTINATION,
    ROUTE,
)



def parse_route_filter(value: str) -> list[str]:
    """Interpret ALL or route numbers separated by commas and/or whitespace.

    Case-insensitive de-duplication and sorting make the same logical
    selection stable regardless of spelling, separator or input order.
    An empty value (or ALL alone) means every route. Mixing ALL with
    explicit routes is invalid rather than silently ignoring the latter.
    """
    if not isinstance(value, str):
        raise ValueError("Route filter must be a string")
    if not value.strip():
        return []
    tokens = [token for token in re.split(r"[,\\s]+", value.strip()) if token]
    if not tokens:
        raise ValueError("No route names supplied")
    if any(token.casefold() == ALL for token in tokens):
        if len(tokens) == 1:
            return []
        raise ValueError("ALL cannot be combined with explicit routes")
    unique = {token.casefold(): token.upper() for token in tokens}
    return sorted(unique.values(), key=str.casefold)


def canonical_route_filter(value: str) -> str:
    """Persist a deterministic route string while retaining legacy IDs."""
    routes = parse_route_filter(value)
    return ",".join(routes) if routes else ALL.upper()

def available_routes(stop: dict) -> list[str]:
    """Return unique route names serving a stop, sorted for the selector."""
    result: dict[str, str] = {}
    for pattern in stop.get("patterns") or []:
        if not isinstance(pattern, dict):
            continue
        route = pattern.get("route") or {}
        if not isinstance(route, dict):
            continue
        name = route.get("shortName")
        if isinstance(name, str) and (name := name.strip()):
            result.setdefault(name.casefold(), name)
    return sorted(result.values(), key=str.casefold)


def default_selected_routes(data: dict, options: dict) -> list[str]:
    """Retain legacy route filtering until the user changes the options."""
    if CONF_ROUTES in options:
        return list(options[CONF_ROUTES])
    return parse_route_filter(data.get(ROUTE, ALL) or ALL)


def effective_filters(data: dict, options: dict) -> tuple[str, str, list[str] | None]:
    """Resolve filters without changing the original config-entry identity.

    A configured route list takes precedence over destination. A stored empty
    list explicitly means all routes, optionally restricted by destination.
    Absence of the option preserves the legacy single-route semantics.
    """
    legacy_route = data.get(ROUTE, ALL) or ALL
    destination = (
        options.get(CONF_DESTINATION_FILTER, data.get(DESTINATION, ALL)) or ALL
    )
    selected_routes = options.get(CONF_ROUTES)
    if selected_routes is None:
        routes = parse_route_filter(legacy_route)
        if len(routes) > 1:
            return ALL, destination, routes
        # Existing single-route config entries retain their old semantics.
        return legacy_route, destination, None
    selected = [
        value.strip()
        for value in selected_routes
        if isinstance(value, str) and value.strip()
    ]
    return ALL, destination, selected


def scan_interval_minutes(options: dict) -> int:
    """Return a safe supported interval for the coordinator."""
    value = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if type(value) is not int or not 1 <= value <= 30:
        return DEFAULT_SCAN_INTERVAL
    return value


def stop_candidates(stops: list[dict], limit: int = 50) -> list[dict]:
    """De-duplicate valid search results while preserving their API order."""
    result = []
    seen = set()
    for stop in stops:
        if not isinstance(stop, dict):
            continue
        gtfs_id = stop.get("gtfsId")
        if not isinstance(gtfs_id, str) or not gtfs_id or gtfs_id in seen:
            continue
        seen.add(gtfs_id)
        result.append(stop)
        if len(result) == limit:
            break
    return result
