# Realtime stop arrivals and origin departures

This document describes the real-time stop board introduced after v0.9.2.
It augments the existing sensor and map entities, without additional network
requests and without changes to the Digitransit API key configuration.

## Data source and how predictions work

HSL provides GTFS Realtime **Trip Updates** with predictions for individual
stop-time events. Digitransit exposes these in its Routing v2 GraphQL API.
Our integration already consumed `realtimeArrival` for legacy arrival
sensors. The stop board now also requests `scheduledDeparture`,
`realtimeDeparture`, and `stopPositionInPattern`.

- [Digitransit Routing API](https://digitransit.fi/en/developers/apis/1-routing-api/)
- [Real-time information](https://digitransit.fi/en/developers/apis/1-routing-api/3-realtime-information/)
- [OpenTripPlanner Stoptime GraphQL fields](https://docs.opentripplanner.org/api/dev-2.x/graphql-gtfs/types/Stoptime)
- [GTFS-RT Trip Updates](https://gtfs.org/documentation/realtime/reference/)

**Important:** `realtimeArrival` and `realtimeDeparture` can contain
fallback scheduled values. The boolean `realtime` field indicates actual
realtime data. A predicted time is not directly calculated from HFP GPS
coordinates in this integration.

Predictions are refreshed using the already-configured Digitransit polling
interval (1–30 minutes). Minute-boundary HA updates change the displayed
countdown but do not trigger additional API requests.

## Origin stop detection

`stopPositionInPattern` is **0 at the first stop for an individual trip**
and nonzero at subsequent positions (including loops). The system does not
infer this from a stop name, from equality of arrival and departure times,
or from the absence of GPS.

- **Through stop**: show a relative realtime *arrival* countdown when
  a prediction is fresh; otherwise show the scheduled *arrival* clock time.
- **Origin stop**: show the scheduled or realtime *departure* clock time.
  Do **not** say a bus will arrive in a certain number of minutes.
- **Unknown trip position**: show the scheduled *departure* clock time
  conservatively, not an unverified approaching-bus ETA.

A stop can be an origin for one trip and a through stop for another.

## Prediction freshness

The stop board labels an ETA `realtime` only if:

1. The Digitransit stop-time has `realtime: true` with the required
   arrival or departure prediction;
2. The trip position is known; and
3. The last **successful Digitransit fetch** is at most **120 seconds** old.

This is an application-level freshness threshold for the *last retrieved*
prediction, not a guaranteed timestamp of the underlying GTFS-RT record.
A 30-minute API polling configuration will show a realtime countdown for
up to 2 minutes after the fetch; afterwards it falls back to scheduled
times. No outdated calculated ETA is called "live".

When the fallback scheduled event has already passed, its entry is
removed from the stop board even if the cached realtime estimate points
into the future. Cancellation filtering remains in effect.

## New map stop attributes

For each configured upcoming departure slot (1–10, default 5):

| Attribute | Meaning |
| --- | --- |
| `next_departure_N` | Backward-compatible `HH:MM · Route → Destination` text |
| `next_departure_N_display` | New user-facing realtime countdown or clock-time/departure text |
| `next_departure_N_event` | `arrival` or `departure` |
| `next_departure_N_source` | `realtime` or `scheduled` after checking freshness |
| `next_departure_N_minutes` | **Only present** for a fresh predicted arrival at a through stop |

For example (the times and routes are illustrative):

- Through stop with a fresh forecast:
  `4 min (realtime) · 530 → Matinkylä`.
- Through stop without fresh realtime:
  `13:01 (scheduled) · 530 → Matinkylä`.
- Origin stop: `13:01 departs (scheduled) · 530 → Matinkylä`.

The map's Browser Mod popup template in
[Interactive HSL map](custom-map.md) prefers `next_departure_N_display`
and falls back to `next_departure_N` for older integration versions.

## Existing sensors and compatibility

The legacy route state, `Next arrival` timestamp sensor, and
`Minutes until arrival` sensor are **unchanged**. They continue to use
the existing arrival-based semantic contract; in particular, do not treat
the legacy arrival sensor at a route's origin as GPS arrival information.

The route sensor's bounded `departures` attribute retains all old keys
and adds origin/event metadata and separate departure timestamps. Its
`prediction_checked_at` value indicates the last successful API fetch,
not the last minute-timer tick.

The integration computes absolute timestamps as
`serviceDay + seconds-from-service-day` before converting to
`Europe/Helsinki`; this matters for trips after midnight and DST folds.

## Limitations and field verification

The first-stop field is documented in OpenTripPlanner's published GTFS
GraphQL schema. It still needs confirmation against the user's *actual*
Digitransit HSL endpoint and live stop records; CI uses mocked API data.
Compare the HSL app/physical boards at the same instant for an origin
stop and a through stop before claiming exact visual or numerical parity.

The stop-board display is not a second ETA estimator based on GPS;
it provides a more honest presentation of existing upstream predictions.
