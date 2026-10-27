# Changelog

All notable changes to this HSL HRT integration are recorded here.
Versions refer to GitHub release tags, not Home Assistant Core versions.
The integration manifest normally matches the release tag; the historical
exception for `v0.8.2` is documented below.

## [0.9.5] — Unreleased

- Added the Home Assistant integration category
  `vehicles_transport.public_transport` to `manifest.json` for catalog
  discovery by public-transport users.
- Prepared release metadata and updated the changelog to reflect the
  already-published v0.9.4 and v0.9.2 releases.
- Metadata-only update: no runtime behavior, configuration, API polling,
  MQTT subscriptions, entities or dependencies changed.

## [0.9.4] — 2026-10-27

- Deduplicate live HFP map markers across separately configured stops by
  exact journey identity; a vehicle remains visible while any configured
  stop is still tracking it, with ownership transferred on stop unload.
- Preserve the standard Home Assistant geolocation `distance` (distance
  from Home); expose `next_tracked_stop`, `tracked_stop_codes` and
  `distance_to_next_tracked_stop_km` (straight-line distance to a
  configured future stop, not a road or full-route next-stop estimate).
- Test two stops tracking the same vehicle, independent lifetime and
  platform ownership transfer; no changes to HFP broker subscriptions.

## [0.9.3] — 2026-10-26

- Read Digitransit's stop-specific scheduled and realtime departure times and
  trip-relative `stopPositionInPattern` without additional API calls.
- Add `next_departure_N_display` and accompanying source/event/minutes
  attributes to stop map markers. Fresh (≤120 seconds since last API poll)
  through-stop realtime predictions show a relative arrival countdown.
- At a trip's first stop, display the departure clock time without implying
  a bus is approaching; fall back to scheduled clock times if the realtime
  data is stale, missing or the trip position is unknown.
- Preserve legacy sensor names, unique IDs, and `next_departure_N` values;
  the Browser Mod popup prefers enriched labels with a legacy fallback.

## [0.9.2] — 2026-10-26

- Fixed HFP periodic MQTT subscription maintenance: register the timer
  callback on Home Assistant's event loop rather than running
  `hass.async_create_task` from an executor thread (PR21).
- Updated lightweight-test Home Assistant callback stubs and added a
  regression check for the periodic timer registration.

## [0.9.1] — 2026-10-25

- Display configurable upcoming arrivals on each stop's standard Map
  More Info dialog: 1–10 entries per configuration, default 5, as
  `next_departure_1`…`next_departure_N` attributes with local arrival
  time, route and destination.
- Reuse the already-filtered Digitransit coordinator data without additional
  HTTP requests; refresh attributes each minute and on timetable updates,
  removing expired journeys. Preserve entity identities and GPS behavior.
- Localized options in English and Finnish, bounds validation, real HA
  regression tests and DST-aware timestamp formatting.

## [0.9.0] — 2026-10-25

- Refresh route, next-arrival timestamp and minutes-until-arrival sensors
  locally on each UTC minute boundary, without extra Digitransit requests
  or HFP MQTT changes.
- Automatically advance to the next already-fetched departure when a vehicle
  arrives, and clear stale timetable states and attributes once all known
  departures expire, even with a 30-minute API polling interval.
- Register minute timers only for active timetable entities and clean them
  up on removal; added unit and real Home Assistant regression tests.

## [0.8.2] — 2026-10-23

> **Historical version mismatch:** GitHub tag `v0.8.2` points to commit
> `56b30a1`, where `custom_components/hslhrt/manifest.json` already
> declared version `0.9.0`. This was published as `v0.8.2`; do not
> rewrite the tag. The subsequent `v0.9.0` release restored
> the correspondence between GitHub tag and manifest version.

- Added configured-stop map markers through the separate `hslhrt_stops`
  geolocation source, with `mdi:circle-small` icons and stop name/code details
  (PR16).
- Digitransit stop `lat`/`lon` are retrieved in the existing Routing v2
  departure query; no additional requests or subscription/API-key changes.
- Show stops independently of HFP availability, refresh their coordinates on
  successful coordinator updates, and remove them on unload or invalid data.
- Map Card examples now combine `hslhrt` vehicles (route/emoji labels) and
  `hslhrt_stops` stops (circle icons) with separate source display modes.
- Added real Home Assistant tests for GPS-disabled stops, map coexistence,
  invalid coordinates, coordinate changes, unload and documented configuration.

## [0.8.1] — 2026-10-23

- Fixed MQTT subscription updates by scheduling and awaiting the executor
  Future correctly; serialized updates across rapid timetable changes.
- Resubscribe to the desired HFP journeys after MQTT reconnection, track
  acknowledged subscriptions and retry failed operations on timer refresh.
- Expose Digitransit route transport mode in tracked-vehicle and geolocation
  attributes, with mode-appropriate MDI icons and emoji-based `marker_label`.
- Show `marker_label` on the native Map Card by default, with `route` as
  a number-only alternative. No entity ID or config migration required.
- Added real HA MQTT lifecycle tests for changing and reconnecting subscriptions,
  plus mode-specific geolocation and map YAML regression checks.

## [0.8.0] — 2026-10-23

- Improved the Options Flow with compact GPS lookahead and journeys-per-route
  drop-downs, while preserving stored integer settings and existing entries.
- Added complete Finnish (`fi`) translations for setup, stop selection,
  reauthentication, preferences, errors and abort messages.
- Updated README with an actual screenshot of compact Options Flow;
  the earlier pre-release radio-button screenshot remains archived.

- Raised the declared minimum supported Home Assistant Core version in HACS
  from 2025.1.0 to 2026.10.2, matching the actual integration-test baseline.
  Earlier Home Assistant versions are no longer advertised as supported.

- Added native Map Card integration via temporary `geo_location` entities,
  one for each selected journey with fresh HFP GPS coordinates.
- Markers are updated in place and removed after GPS expires, when the
  scheduled journey is no longer selected, on unload, or when HFP is disabled.
- Stable `hslhrt` geolocation source for Map Card and automations, with
  route, destination, stop code, arrival and vehicle metadata.
- No persistent entity-registry entries; existing sensors and unique IDs are
  unchanged.
- Added real Home Assistant tests for multiple simultaneous vehicles,
  relocation, expiry, reappearance, unload and disabled tracking.

## [0.7.0]

- Optional HFP v2 MQTT tracking for multiple upcoming journeys of every
  selected public route at a configured stop.
- Per-entry options for tracking horizon and journeys per route; defaults are
  30 minutes and two journeys per route, with tracking off by default.
- New tracked-vehicles sensor with exact journey matching, fresh coordinates
  and connection status. Existing timetable sensors are unaffected by outages.
- Bounded TLS MQTT subscriptions and position expiration. Native map entities
  are deferred to the next development phase.
- Moved change history out of README into this file.
- Added real Home Assistant integration tests in PR7 (Python 3.14,
  Home Assistant Core 2026.10.2), leaving older unit tests separate.

## [0.6.1]

- Fixed direct lookup of public HSL stop codes such as E4971 and E4972 by
  searching Digitransit Geocoding instead of name-only GraphQL lookup.
- Verified the selected stop's public code against its Routing API details,
  preventing selection of the opposite-side stop.
- Preserved name search and the ambiguous-stop picker.

## [0.6.0]

- Added interactive stop selection showing stop code and GTFS ID when multiple
  stops share a name.
- Added Options Flow for multiple routes, destination filter and an
  entry-specific 1–30-minute polling interval.
- Existing config entries and unique IDs remain compatible.

## [0.5.1]

- Fixed loading config flows on recent Home Assistant versions by replacing
  the obsolete `homeassistant.core.Config` annotation with `ConfigType`.
- Added an import regression test.

## [0.5.0]

- Modernized CoordinatorEntity updates and preserved the legacy route sensor.
- Added timestamp and numeric minutes-until-arrival sensors.
- Added compact, bounded upcoming departure attributes.
- Improved filtering of expired and cancelled departures.

## [0.4.0]

- Migrated from retired Digitransit Routing v1 to Routing v2 GraphQL.
- Switched to asynchronous requests using the shared Home Assistant HTTP session.
- Added API key configuration and reauthentication for existing entries.
- Corrected stop-time handling across midnight and daylight-saving transitions.

## [0.3.5 and earlier]

- Legacy version from the original `hslhrt-hass-custom` integration, with
  one route/stop sensor per configuration entry.
