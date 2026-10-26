# Realtime arrival and departure estimates: analysis and design

**Status:** investigation and proposed implementation; not implemented here.
This document describes what the current integration already knows and the
changes required to create a departure-board-style display.

## Where HSL realtime predictions come from

HSL publishes predicted stop arrival/departure times via GTFS Realtime
**Trip Updates**, separate from the HFP vehicle-position stream. The
Digitransit Routing v2 GraphQL API exposes those stop-time predictions.

Useful background:

- [HSL Open Data](https://www.hsl.fi/en/opendata)
- [HSL GTFS Realtime notes](https://hsldevcom.github.io/gtfs_rt/)
- [Digitransit Routing API](https://digitransit.fi/en/developers/apis/1-routing-api/)
- [Digitransit real-time field semantics](https://digitransit.fi/en/developers/apis/1-routing-api/3-realtime-information/)
- [GTFS Realtime Trip Updates specification](https://gtfs.org/documentation/realtime/reference/)

Digitransit explicitly documents that `realtimeArrival` and
`realtimeDeparture` fall back to static times by default; the
`realtime` flag says whether they were updated from a real-time source.
A nonempty `realtimeArrival` field **alone** does not mean live GPS-based
prediction.

We should **not** claim to reproduce a particular physical stop-display's
proprietary calculation without checking its data feed or observing that
display side by side. For comparable arrival predictions, the existing
Digitransit endpoint is the best starting point. Vehicle GPS alone is not
a reliable travel-time estimator: street topology, traffic, dwell times and
headways matter.

## Already implemented

The integration queries, for each matching stop-time:

- `serviceDay`, `scheduledArrival`, `realtimeArrival`, `realtime`;
- `realtimeState` (including filtering canceled trips);
- trip route and metadata used for HFP matching.

`schedule.parse_departures` already uses
`serviceDay + realtimeArrival` when `realtime` is true and the realtime
field is valid, otherwise `serviceDay + scheduledArrival`.
`realtime`, `delay_seconds`, `arrival_timestamp` and
`arrival_datetime` are already represented in processed data;
`sensor.*_minutes_until_arrival` counts down to that computed timestamp.
The `departures` sensor attribute currently exposes `realtime` and
`delay_seconds`. **These are not strictly timetable-only values.**

The current limitation is freshness and interpretation:

- Between network polls (1–30 minutes), the countdown changes each minute
  but the prediction itself is unchanged.
- The public map stop attributes show local absolute clock times, not
  relative minutes or a visual realtime-vs-scheduled distinction.
- Current calculations are arrival-centric even though passengers at a
  stop usually want the next *departure* from that platform.
- We do not currently identify an origin/terminal stop of a specific trip.

## Proposed data model

First, augment the **existing** Digitransit stop-times GraphQL query,
rather than adding a second API or constructing travel estimates from GPS:

```graphql
stoptimesWithoutPatterns(numberOfDepartures: 100) {
  serviceDay
  scheduledArrival
  realtimeArrival
  scheduledDeparture
  realtimeDeparture
  realtime
  realtimeState
  headsign
  trip {
    directionId
    departureStoptime {
      serviceDay
      scheduledDeparture
    }
  }
}
```

The added `scheduledDeparture` and `realtimeDeparture` are supported
stop-time fields. Preserve the existing route, mode and HFP-matching
fields in the production query. As needed, also investigate
`arrivalDelay` / `departureDelay` and a stable first-stop identity.

Store distinct timestamps, not a single overloaded `arrival` value:

- `scheduled_arrival_timestamp`
- `estimated_arrival_timestamp` (only for genuine realtime input)
- `scheduled_departure_timestamp`
- `estimated_departure_timestamp` (only for genuine realtime input)
- `prediction_source`: `realtime` or `scheduled` for the **displayed
  event**, and `prediction_checked_at` (time of last successful fetch)
- `is_origin_stop`: true/false/unknown, **per trip and stop platform**

Compute timestamps as `serviceDay + offset`, then convert to local time
when formatting. This handles trips spanning midnight and seasonal DST
changes. Do not compute timestamps by combining a local calendar date with
a clock time.

## Identifying origin stops

A stop is an origin **for a particular trip**, not inherently for all
routes serving that stop. An interchange may be the first stop for one
route and a through stop for another.

Compare the current stop's **GTFS ID** to the first stop's GTFS ID in the
trip's ordered stop sequence. The currently queried
`trip.departureStoptime` gives the initial scheduled departure time for
HFP matching, but the existing query does **not** fetch the first-stop ID.
Investigate whether `trip.departureStoptime.stop.gtfsId` is exposed in
the production schema, or use a documented trip-stop sequence field.
**Validate the schema and a few real journeys before committing a query.**

Do **not** infer an origin merely because `scheduledArrival ==
scheduledDeparture` or because HFP has no vehicle position: intermediate
stops can also have equal arrival/departure times, and GPS can be missing.

If a trip starts at this platform, display its **departure** countdown or
scheduled departure clock time, not a fictional estimated *arrival*. If
the first-stop identity cannot be established, retain `unknown` and do
not fabricate `is_origin_stop = false`.

## Proposed presentation

For an intermediate stop with a valid and recent realtime prediction:

- `530 → Kamppi · 4 min · live` (or a consistent icon/style)
- Optionally show the predicted local clock time below it.

For an origin stop:

- `530 → Kamppi · departs 12:30` (scheduled unless a separately
  verified realtime **departure** is available).
- Never present this as "bus arriving in 4 min".

If realtime is unavailable:

- `530 → Kamppi · 12:30 · scheduled`; do not imply live precision
  merely because a client-side countdown can be calculated.
- For a departure that is in the past at last API fetch, suppress or mark
  the value stale instead of displaying a negative minute count.

Suggested UI surfaces, in priority order:

1. Extend existing route sensor `departures` entries with event kind
   (arrival/departure), source, scheduled and realtime timestamps.
   Keep legacy fields unchanged.
2. Extend the existing `geo_location` stop marker's
   `next_departure_N` formatted attributes, preferably using a clear
   `~4 min (live)` vs `12:30 (scheduled)` marker. Do not silently
   change their value contract without a test and release note.
3. Keep existing `Next arrival` and `Minutes until arrival` sensors
   compatible; consider a distinct next-departure sensor only if users
   need that semantic distinction for automations.
4. Dashboard cards and Browser Mod popups can consume the enriched data
   without becoming backend dependencies.

## Prediction freshness

An often-overlooked point: `realtime: true` in a cached response does
**not** mean the estimate is still fresh now. Persist the last successful
API fetch timestamp and distinguish it from a local minute-tick update.
Choose and document a configurable or conservative freshness threshold
before displaying a `live` badge. A 30-minute poll interval should not
look as fresh as a one-minute interval.

Use no extra network requests for frontend rendering; refresh the data
through the existing coordinator. Increasing polling frequency can improve
freshness but must respect the Digitransit subscription's API limits.

## Validation plan

Before implementation:

1. Sample a few intermediate stops and compare
   `scheduledArrival`/`realtimeArrival` and the HSL app/physical board
   at the **same moment**. Expect some differences in rounding, latency
   and backend source.
2. Compare origin platforms and through stops using the same public route
   and verify trip-specific first-stop classification.
3. Compare both `arrival` and `departure` values for stops with dwell.
4. Confirm `realtimeState`, cancellations, missing predictions, unusual
   night routes, loops and day changes.
5. Add unit and real Home Assistant integration tests for data mapping,
   origin/unknown classification, staleness, fallback and entity compatibility.
6. Audit all new timer, coordinator and MQTT paths for event-loop
   thread safety. This part should not need Pyscript.

## Scope boundaries

This document is an **investigation**, not a claim that the physical
display's exact algorithm has been reverse-engineered. No new API field,
sensor, config option or display format has been deployed by writing this
document.
