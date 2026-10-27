# Stop configuration and options

Each configuration entry refers to a specific HSL stop platform.

## Selecting a stop

Search by name, public stop code (e.g. `E4971`), or exact GTFS ID
(`HSL:...`). If multiple similarly named platforms exist, select the
specific platform/code; different directions often have distinct stop IDs.

![Initial stop setup (API key blank)](../resources/images/configure-stop.png)

![Select a stop platform](../resources/images/select-stop.png)

### Route filter during initial setup

The initial **Routes** text field accepts `ALL` (all routes), a single
route (`530`) or multiple routes separated by **commas, spaces or both**:

```text
158, 530
158 530
158,530
```

All examples above select routes `158` and `530`. Duplicates are removed
and the list is stored in a canonical order, so `530 158` has the same
configuration identity as `158,530`. Enter `ALL` **alone** for all
routes; do not combine `ALL` with a route number. The integration checks
that **every requested route** serves the selected physical stop and reports
an error otherwise.

The existing route selector under **Configure** already allows selecting
multiple routes from a dropdown, without typing separators. It will
preselect all routes originally supplied in the text field. Existing
single-route and `ALL` entries are unchanged; selecting new routes in
Configure does not rename or recreate the existing sensor entities.

## Routes, destinations and polling

Open **Configure** on the integration entry.

- Select one or more routes, or a destination filter (`ALL` for all).
- A nonempty route selection takes precedence over the destination filter.
- Digitransit polling interval: 1, 2, 3, 5, 10, 15 or 30 minutes.
  This governs *new network predictions*; local minute-boundary updates
  only recalculate the countdown from the last fetched data.
- **Upcoming departures shown when tapping a map stop**: 1–10, default
  5; changes the `next_departure_1` ... attributes in More Info and
  requires no additional requests.

## Optional live vehicle tracking (HFP)

Enable **Track GPS positions** under **Configure** if you want live
vehicle markers and the tracked-vehicles sensor.

- Lookahead: 15–90 minutes (default 30).
- Maximum journeys per public route: 1–5 (default 2).
- The integration subscribes to exact route/direction/start combinations
  over TLS at `mqtt.hsl.fi:8883`, with a cap of 32 subscriptions per stop.
- Positions older than 90 seconds are not displayed as fresh GPS.
- GPS matching can be unavailable for some timetable journeys.

![Compact GPS preferences](../resources/images/stop-options-compact.png)

The routing timetable, route sensor and arrival sensors remain usable
when HFP tracking is disabled or the MQTT broker is unavailable.

## Language and entity IDs

The setup and options UI are available in English and Finnish. Change
the language in the Home Assistant user profile; restart/refresh if older
translations are cached.

Find actual entity IDs under **Settings → Devices & services → Helsinki
Regional Transport → Entities** or **Developer Tools → States**.
Examples in the guides use sample entity IDs that may differ on your system.

[Dashboard examples](dashboard-examples.md) ·
[Custom map](custom-map.md)
