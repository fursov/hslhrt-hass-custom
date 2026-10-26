# Helsinki Regional Transport (HSL HRT)

Home Assistant custom integration for HSL stop timetables, realtime arrival
information and optional live vehicle locations in the Helsinki region.
It uses [Digitransit Routing API](https://digitransit.fi/en/developers/apis/1-routing-api/)
and the public HSL HFP MQTT stream.

## Features

- **Upcoming journeys:** choose a stop platform by name, public stop code
  or GTFS ID, then filter by route or destination.
- **Timetable sensors:** next route, next arrival timestamp and minutes
  until arrival. Canceled journeys are filtered out.
- **Realtime-aware times:** prefer Digitransit's realtime arrival estimate
  when it is available, falling back to the scheduled time when it is not.
- **Minute-by-minute display updates:** counts down from the last fetched
  estimate without issuing an additional HTTP request every minute.
- **Optional live vehicles:** match HFP GPS telemetry to selected journeys,
  including route, destination, position, heading and speed when available.
- **Map markers:** expose temporary vehicle `geo_location` entities and
  independently expose configured stop locations.
- **Stop departures on the map:** tap a stop marker to see its next
  departures (configurable count, default five).
- **English and Finnish configuration interface.**

## How it works

The Routing API provides stop timetables and realtime predictions when
available. Filtering, expiration of old entries and countdown display are
managed locally in Home Assistant. The configured polling interval controls
how often *new predictions* arrive.

Optional HFP vehicle tracking supplements the timetable with fresh GPS
positions over a separate MQTT connection. Vehicle positions are not used
as a substitute for timetable predictions. Map vehicle markers disappear if
their positions become stale; stop markers do not depend on live GPS.

These capabilities work with standard Home Assistant sensors and maps. The
optional **ha-map-card**, **auto-entities** and **Browser Mod** frontend
components can provide a more customizable map experience.

## Documentation

- [Installation and requirements](docs/installation.md)
- [Configure stops, filters and GPS tracking](docs/configuration.md)
- [Sensor and timetable dashboard examples](docs/dashboard-examples.md)
- [Interactive transport map with ha-map-card, auto-entities and Browser Mod stop popups](docs/custom-map.md)
- [Understanding realtime predictions and origin stops](docs/realtime-arrivals.md)
- [Development and testing](docs/development.md)

## Credits

Original author: Anand Radhakrishnan
([@anand-p-r](https://github.com/anand-p-r)).

Data attribution: Digitransit / Helsinki Regional Transport (HSL).
