# Helsinki Regional Transport (HSL HRT)

Home Assistant custom integration for upcoming HSL departures at a selected stop using
[Digitransit Routing v2](https://digitransit.fi/en/developers/apis/1-routing-api/).

**Release history:** [CHANGELOG.md](CHANGELOG.md).

## Home Assistant compatibility

**Minimum supported Home Assistant Core: 2026.10.2 (Python 3.14).**
This is the version used by the real Home Assistant integration test suite
in GitHub Actions. Earlier Home Assistant versions are not supported by
the current HSL HRT integration. HACS checks this requirement when installing
or updating the integration. This compatibility requirement is separate
from the HSL HRT integration's version number.

## Installation

In HACS, add `https://github.com/fursov/hslhrt-hass-custom` as a custom
**Integration** repository. Install it, restart Home Assistant, then open
**Settings → Devices & services** and add **Helsinki Regional Transport**.

For manual installation, copy `custom_components/hslhrt/` into
`<HA configuration>/custom_components/hslhrt/` and restart Home Assistant.

You need a Digitransit API subscription key from
https://portal-api.digitransit.fi/ . The key is sent in the
`digitransit-subscription-key` header. Existing configurations imported
from v0.3.5 require reauthentication but should not be deleted.

## Stop setup and filtering

Enter a stop name, public stop code (`E4971`, `E4972`) or GTFS ID
(`HSL:...`). Name search shows a selection when multiple platforms are
returned. The code search verifies the exact stop against Routing v2.

Under **Configure**, select one or more routes and a destination filter
(`ALL` means all). A nonempty route selection takes precedence over
destination. The Routing API polling interval can be set to 1, 2, 3, 5, 10,
15 or 30 minutes. Existing entries keep their original filters until changed.

## Sensors

Each stop/route entry has three standard sensors:

| Sensor | Meaning |
| --- | --- |
| Route | Route number of the next arriving bus/tram, with legacy `ROUTE`, `DESTINATION`, `ARRIVAL TIME`, `ROUTES` and stop attributes |
| Next arrival | Timezone-aware datetime of the next arrival |
| Minutes until arrival | Rounded-up minutes until the next arrival |

The legacy `ROUTES` attribute excludes the first arrival and is capped at
20 further departures. The modern `departures` attribute includes the first
10. These sensors remain available when GPS tracking is disabled or HFP is offline.

## Optional HFP vehicle tracking (v0.7.0)

The integration can track **multiple next journeys per route at the configured
stop**, not just the first bus overall. Open **Configure** and enable
*Track GPS positions*. Choose a horizon (15–90 minutes, default 30) and a
maximum number of journeys per public route (1–5, default 2).

Once enabled, an additional **Tracked vehicles** sensor appears:

- Numeric state: number of upcoming journeys with fresh GPS coordinates.
- `selected_journeys`: number of eligible trips whose GTFS journey identity
  can be matched to HFP.
- `vehicles`: bounded list of planned journeys and their GPS when available.
  Each row includes route, arrival, direction, trip start, operating day and
  `gps_available`. The `latitude`, `longitude`, speed and heading appear
  only when the HFP position is fresh.
- `hfp_connected`: whether the public MQTT broker is currently connected.

Tracking uses TLS with the public `mqtt.hsl.fi:8883` broker, separately from
your own Home Assistant / Zigbee2MQTT broker. It does **not** require another
Digitransit API key. No GPS data is fabricated: if there is no matching HFP
vehicle or the last position is older than 90 seconds, the journey stays in
the list but `gps_available` is false. The integration limits subscriptions
to 32 exact route/direction/start combinations per stop. Updates of HA
entities are throttled to approximately five seconds.

Some timetable journeys lack the GTFS metadata required for exact matching;
they remain in the original timetable but are omitted from HFP selection.
GPS positions are exposed on Home Assistant's Map card when fresh HFP data is available (see below).

## Live vehicle map (v0.8.0)

With HFP tracking enabled on a configured stop, the integration now publishes
**temporary** `geo_location` entities for selected upcoming journeys that
currently have fresh HFP GPS coordinates. No marker is shown when the vehicle
is not known or its last position is older than 90 seconds.

Add a built-in **Map** card and select the `hslhrt` source under
**Geolocation sources**. YAML equivalent:

```yaml
type: map
geo_location_sources:
  - hslhrt
auto_fit: true
```

The map contains **all tracking-enabled configured stops**. Each vehicle
marker shows its public route and destination. Its attributes include the stop
code, scheduled arrival, vehicle/operator identifiers, position timestamp,
heading and speed where available. The source is `hslhrt`.

Markers **update in place** as new coordinates arrive and are completely
removed when their journey leaves the selected horizon, the GPS becomes stale,
the configuration unloads or GPS tracking is switched off. These temporary
entities deliberately have no permanent registry entries and cannot be pinned
individually before a vehicle has been observed. The existing route and ETA
sensors continue to function independently from HFP.

## Dashboard examples

The examples below use a stop configured as **Eestinmalmintie (E4971)** with
the **ALL** routes option. Replace each sample `sensor.eestinmalmintie_e4971_all`
entity ID (and its suffixes) with the actual entities shown under
**Settings → Devices & services → Helsinki Regional Transport → Entities**
or **Developer Tools → States**. Home Assistant generates IDs from entity names;
they can differ after renaming, selecting routes, or restoring old entries.
The `_next_arrival`, `_minutes_until_arrival`, and `_tracked_vehicles`
suffixes refer to *unique IDs*, not guaranteed literal entity IDs.
Do not create additional template sensors just to obtain these values.

These examples use **built-in Home Assistant cards** and require no
custom Lovelace cards.

### 1. Next route and arrival (Entities Card)

Three sensors are created by default per configured stop entry.

```yaml
type: entities
title: Eestinmalmintie (E4971)
show_header_toggle: false
entities:
  - entity: sensor.eestinmalmintie_e4971_all
    name: Next route
  - entity: sensor.eestinmalmintie_e4971_all_next_arrival
    name: Next arrival
  - entity: sensor.eestinmalmintie_e4971_all_minutes_until_arrival
    name: Minutes until arrival
```

The next-arrival sensor has Home Assistant's timestamp device class; it
already handles day boundaries and local-time presentation. The minutes sensor
updates on each Digitransit poll (every 1–30 minutes according to Options).

### 2. Route and stop details (Entities Card)

This example uses the **legacy attributes**, which are still provided
on the main route sensor. Attribute names are case-sensitive.

```yaml
type: entities
title: Eestinmalmintie details
entities:
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all
    attribute: STOP NAME
    name: Stop
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all
    attribute: STOP CODE
    name: Stop code
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all
    attribute: ROUTE
    name: Next route
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all
    attribute: DESTINATION
    name: Destination
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all
    attribute: ARRIVAL TIME
    name: Arrival (local HH:MM:SS)
```

The main sensor state is already the next route number; the attributes
`ROUTE`, `DESTINATION`, and `ARRIVAL TIME` are absent if there is no
upcoming departure. The legacy `ROUTES` list *excludes* this first departure.

### 3. Next arrival with a readable countdown (Markdown Card)

No `platform: template` sensors are needed. Use the real minutes-until-arrival
sensor rather than subtracting clock-time strings; the timestamp sensor handles
overnight departures correctly.

```yaml
type: markdown
title: Next HSL departure
content: |
  {% set route_sensor = 'sensor.eestinmalmintie_e4971_all' %}
  {% set minutes_sensor = 'sensor.eestinmalmintie_e4971_all_minutes_until_arrival' %}
  {% set arrivals = state_attr(route_sensor, 'departures') or [] %}
  {% if arrivals %}
  {% set trip = arrivals[0] %}
  {% set arrival = as_datetime(trip.arrival_datetime, none) %}
  **Route {{ trip.route }} → {{ trip.destination }}**

  Expected: **{{ as_local(arrival).strftime('%d.%m %H:%M') if arrival else 'unknown' }}**

  Time remaining: **{{ states(minutes_sensor) }} min**
  {% else %}
  No upcoming departures, or data is currently unavailable.
  {% endif %}
```

### 4. Table of upcoming departures (Markdown Card)

Use the structured `departures` attribute, which **includes** the nearest
departure and is limited to 10. The legacy `ROUTES` attribute starts with
the *second* departure, so using that list would omit the next bus.

```yaml
type: markdown
title: Eestinmalmintie departures
content: |
  {% set arrivals = state_attr('sensor.eestinmalmintie_e4971_all', 'departures') or [] %}
  {% if arrivals %}
  | Route | Destination | Arrival | Data |
  | :---- | :---------- | :------ | :--- |
  {% for trip in arrivals[:6] %}
  {% set dt = as_datetime(trip.arrival_datetime, none) %}
  | {{ trip.route }} | {{ trip.destination }} | {{ as_local(dt).strftime('%d.%m %H:%M') if dt else '—' }} | {{ 'Realtime' if trip.realtime else 'Scheduled' }} |
  {% endfor %}
  {% else %}
  No upcoming departures, or data is currently unavailable.
  {% endif %}
```

Timestamps in `departures[*].arrival_datetime` are ISO 8601 UTC values;
`as_local` converts them to your Home Assistant timezone. Blank/unknown
departures produce an explanatory message rather than a template error.

### 5. Optional HFP tracking status (Entities Card)

Only available after **Configure → Track GPS positions** is enabled. A value
of `0` means zero tracked journeys currently have fresh GPS; check
`hfp_connected` for broker connectivity, and `selected_journeys` for
the number of journeys eligible for matching.

```yaml
type: entities
title: HSL live vehicles
entities:
  - entity: sensor.eestinmalmintie_e4971_all_tracked_vehicles
    name: Vehicles with fresh GPS
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all_tracked_vehicles
    attribute: hfp_connected
    name: HFP MQTT connected
  - type: attribute
    entity: sensor.eestinmalmintie_e4971_all_tracked_vehicles
    attribute: selected_journeys
    name: Selected journeys
```

The `vehicles` attribute contains individual journey records with
`gps_available`, and fresh `latitude`/`longitude` only when known.
Availability of coordinates is not guaranteed for every upcoming journey.

### 6. Live vehicle locations (Map Card)

Requires optional HFP tracking and at least one fresh vehicle position.
This map shows all current `geo_location` markers from the `hslhrt`
source, including vehicles tracked by *other configured stops*.

```yaml
type: map
geo_location_sources:
  - hslhrt
auto_fit: true
```

Markers are temporary; they disappear if GPS ages beyond 90 seconds or
a journey is no longer selected. A blank map does not mean timetable sensors
are broken. No extra MQTT integration in Home Assistant is required.

### Historical screenshots

The four original UI screenshots are preserved in
[Historical dashboard screenshots](docs/legacy-ui-examples.md). They document
the earlier integration, **not** the current 2026.10 dashboard. The old
template-sensor and entity-filter examples are intentionally not recommended:
they are unnecessarily complicated and can be wrong around midnight.
Current screenshots should only be added after capture and verification
on an actual Home Assistant instance.

## Development and tests

Run the lightweight unit tests in a Python 3.13 environment:

```sh
python -m pip install pytest ruff aiohttp voluptuous
python -m pytest -q tests --ignore=tests/integration
```

Run tests against real Home Assistant Core in a separate Python 3.14
environment (no live HSL calls):

```sh
python -m pip install -r requirements-ha-tests.txt
python -m pytest -q -p pytest_homeassistant_custom_component tests/integration
```

These must run in **separate processes**, because the fast tests use
`homeassistant` module stubs. CI runs both suites, Hassfest and HACS.
The Home Assistant integration-test baseline is pinned for repeatability.

## Original Author
Anand Radhakrishnan [@anand-p-r](https://github.com/anand-p-r)
