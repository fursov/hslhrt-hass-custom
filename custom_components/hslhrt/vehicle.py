"""Presentation-only transport mode mapping for HSL map markers.

Never guess a transport type from a line number. Unknown Digitransit modes
display the public route number without a misleading vehicle pictogram.
"""

MODE_PRESENTATION = {
    "BUS": ("🚌", "mdi:bus"),
    "TROLLEYBUS": ("🚌", "mdi:bus"),
    "COACH": ("🚌", "mdi:bus"),
    "TRAM": ("🚋", "mdi:tram"),
    "SUBWAY": ("🚇", "mdi:subway"),
    "RAIL": ("🚆", "mdi:train"),
    "FERRY": ("⛴", "mdi:ferry"),
    "FUNICULAR": ("🚞", "mdi:train"),
    "GONDOLA": ("🚡", "mdi:gondola"),
}


def vehicle_icon(mode: str | None) -> str:
    """Return the MDI icon for a known mode, otherwise a generic map marker."""
    item = MODE_PRESENTATION.get(mode.upper()) if isinstance(mode, str) else None
    return item[1] if item else "mdi:map-marker"


def marker_label(route: str | None, mode: str | None) -> str:
    """Compose a short readable marker using a known icon and route number."""
    public_route = str(route).strip() if route is not None else ""
    item = MODE_PRESENTATION.get(mode.upper()) if isinstance(mode, str) else None
    return f"{item[0]} {public_route}" if item and public_route else public_route or "?"
