# Installation

## Requirements

- Home Assistant Core 2026.10.2 or later (Python 3.14); older Core releases are not supported.
- A Digitransit subscription key from <https://portal-api.digitransit.fi/>.
- Internet access to Digitransit's Routing API.
- Optional: network access to the public HSL HFP MQTT broker for vehicle locations.

## HACS installation (recommended)

1. In HACS, add `https://github.com/fursov/hslhrt-hass-custom` as a custom **Integration** repository.
2. Install **Helsinki Regional Transport**.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration** and search for **Helsinki Regional Transport**.
5. Enter your Digitransit subscription key, stop and filters. Do **not** put the key in dashboard YAML or screenshots.

## Manual installation

Copy the `custom_components/hslhrt/` directory into
`<Home Assistant config>/custom_components/hslhrt/`, restart, then
add the integration through **Settings → Devices & services**.

The API key is transmitted as the `digitransit-subscription-key` header.
Existing older entries may request reauthentication; do not delete
entries merely because a key must be renewed.

## Next steps

- [Configure stops and GPS tracking](configuration.md)
- [Dashboard examples](dashboard-examples.md)
- [Live vehicle map using ha-map-card, auto-entities and Browser Mod](custom-map.md)

## Troubleshooting

No departures? Confirm the exact stop platform (code/GTFS ID), filters,
network/API key and whether the stop has any upcoming journeys.

No vehicles on the map? Enable *Track GPS positions* for the relevant stop.
Only selected upcoming journeys with fresh HFP GPS appear; an empty map does
not mean the timetable API is broken. The HFP broker is separate from the
Home Assistant MQTT integration.
