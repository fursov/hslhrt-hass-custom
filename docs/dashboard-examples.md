# Dashboard examples

## Route sensor history (illustration)

![Example of a route sensor's Home Assistant history](../resources/images/sensor-state-history.png)

This screenshot is **not a timetable card**. It shows changes in the route
sensor's state; for actual upcoming departures use the attributes or
dashboard examples below.

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
custom Lovelace cards. For `ha-map-card`, `auto-entities` and Browser Mod,
see the [custom map guide](custom-map.md).

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
already handles day boundaries and local-time presentation. All three timetable
sensors (next route, next arrival and remaining minutes) are **re-evaluated
locally at each minute boundary** using the most recently fetched departures.
Expired trips disappear and the next known trip becomes active even between
Digitransit polls. The configured polling interval (1–30 minutes) still
controls **only** HTTP requests to Digitransit, not these local updates.
No extra API calls or HFP MQTT operations are made by the minute timer. When
all fetched departures expire, values become unknown until new data arrives.

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

### 6. Live vehicle locations and configured stops (Map Card)

Stops appear as circle-icon markers as soon as their coordinates are
available from Digitransit, even if no live GPS positions are available.
Vehicles appear when HFP tracking is enabled and GPS is fresh. This map
includes all configured stops and all selected vehicles across entries,
not just the one used in the dashboard examples.

```yaml
type: map
geo_location_sources:
  - source: hslhrt
    label_mode: attribute
    attribute: marker_label
  - source: hslhrt_stops
    label_mode: icon
auto_fit: true
```

To show **only vehicle route numbers**, change `attribute: marker_label`
to `attribute: route` in the YAML. Remove the `hslhrt_stops` source
from the card to hide stops without affecting any HA entities. To show only the mode-dependent MDI icon,
replace the `label_mode` and `attribute` lines with `label_mode: icon`.
The built-in Map Card does not render separate icon-and-text controls in the
same marker; `marker_label` is a simple combined text alternative. Stop
markers use `label_mode: icon` with the `mdi:circle-small` icon.

Vehicle markers are temporary; they disappear if GPS ages beyond 90 seconds
or a journey is no longer selected. Configured-stop markers are independent
of HFP and remain visible while valid stop coordinates are available.
If no vehicles are shown, the timetable sensors may still be working normally.
No extra MQTT integration in Home Assistant is required.

## Historical screenshots

The original UI screenshots are preserved in
[Historical dashboard screenshots](legacy-ui-examples.md). They document
the earlier integration, **not** the current 2026.10 dashboard. The old
template-sensor and entity-filter examples are intentionally not recommended:
they are unnecessarily complicated and can be wrong around midnight.
The configuration and options screenshots in the [configuration guide](configuration.md)
were captured in an actual Home Assistant instance. They
show different example stops and are not a guarantee of exact entity names
or map availability on your installation.

