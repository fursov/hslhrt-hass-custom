# Live HSL map with ha-map-card, auto-entities and Browser Mod

This is an **optional dashboard setup**. The integration itself needs only
Home Assistant Core and Digitransit; the frontend cards below are not integration
dependencies.

> Screenshots are pending. The example YAML is provided now; add your actual
> screenshots later without changing the integration's backend.
>
> <!-- TODO screenshot: full-screen transport map with buses and stops -->
> <!-- TODO screenshot: tapped stop showing five upcoming departures -->
> <!-- TODO screenshot: Browser Mod fullscreen popup with live map -->

## Prerequisites

- Install the HSL HRT integration and configure stops;
- enable **Track GPS positions** at stops whose live vehicles you want;
- install [ha-map-card](https://github.com/nathan-gs/ha-map-card) and
  [auto-entities](https://github.com/thomasloven/lovelace-auto-entities)
  through HACS as dashboard cards;
- optionally install [Browser Mod](https://github.com/thomasloven/hass-browser_mod)
  if you want to open the entire map in a large popup.

The integration exposes two `geo_location` entity sources:

- `hslhrt`: **temporary vehicles** with fresh GPS and a `marker_label`
  attribute such as `🚌 530`.
- `hslhrt_stops`: **configured stop platforms**, available even when
  HFP tracking is off. Stop entity attributes include
  `next_departure_1` ... `next_departure_N` (default N=5).

## 1. Self-updating transport map (recommended)

Paste the following into a Manual card. Unlike the built-in Home Assistant
Map card, **ha-map-card** uses per-entity `display: attribute` and
`attribute: marker_label`, not `geo_location_sources.label_mode`.

```yaml
type: custom:auto-entities
card:
  type: custom:map-card
  x: 24.94
  y: 60.17
  zoom: 11
  focus_follow: contains
  marker_grouping: spread
filter:
  include:
    - domain: geo_location
      attributes:
        source: hslhrt
      options:
        display: attribute
        attribute: marker_label
        tap_action:
          action: more-info
    - domain: geo_location
      attributes:
        source: hslhrt_stops
      options:
        display: icon
        tap_action:
          action: more-info
unique: true
```

The example longitude/latitude (`x`/`y`) centers the map around Helsinki;
adjust them and the zoom level to your preferences.

`auto-entities` automatically passes matching entity IDs to `ha-map-card`.
As temporary GPS entities appear or disappear, it updates the map without
hardcoded journey IDs. Matching by `source` also distinguishes vehicles and
stops; **do not** use a broad `geo_location.hslhrt_*` vehicle filter,
because it also matches stop IDs.

Tap a stop to open Home Assistant's normal **More Info** dialog with
the next N filtered arrivals. This requires neither Browser Mod nor extra
backend API calls. Tap a vehicle for its attributes, including route,
destination, heading, speed and position timestamp. Do not expect a GPS
marker for every timetable journey.

The `marker_grouping: spread` option helps when multiple map markers
overlap. If your installed card does not recognize the option, remove it
and use the card's default marker layout.

## 2. Open the map in a Browser Mod popup (optional)

Browser Mod's documented `fire-dom-event` action works on a regular
dashboard button. The following button opens a fullscreen popup
containing the dynamically populated map:

```yaml
type: button
name: HSL live map
icon: mdi:map
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      title: HSL live map
      initial_style: fullscreen
      content:
        type: custom:auto-entities
        card:
          type: custom:map-card
          x: 24.94
          y: 60.17
          zoom: 11
          focus_follow: contains
          marker_grouping: spread
        filter:
          include:
            - domain: geo_location
              attributes:
                source: hslhrt
              options:
                display: attribute
                attribute: marker_label
                tap_action:
                  action: more-info
            - domain: geo_location
              attributes:
                source: hslhrt_stops
              options:
                display: icon
                tap_action:
                  action: more-info
        unique: true
```

Browser Mod is used here **to open the map**, not to override taps on map
markers. The card's documented `tap_action` support does not include
`fire-dom-event`; changing marker clicks to a Browser Mod popup would
require separate frontend validation. The standard More Info behavior is
the supported default.

## 3. Full-width map view

For a map filling the dashboard area, create a dedicated dashboard view of
type **Panel** containing only the `custom:auto-entities` wrapper from
section 1. Panel views support only one root card, so place any additional
controls inside a wrapper card or choose a different view type.

## 4. Built-in Map card alternative

The built-in map uses a **different schema**. If you do not need
ha-map-card, auto-entities or Browser Mod, use:

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

Avoid `show_all: true` if you want to select only these two geolocation
sources. In the built-in card, `show_all` cannot be combined with explicit
`entities` or `geo_location_sources`.

## Limitations and verification

- The examples are based on published card configuration interfaces; the
  **combined setup has not yet been visually verified** in your Home Assistant
  instance. Adjust version-specific card options if necessary.
- GPS coordinates and HFP headings are not arrival predictions.
- The `next_departure_N` stop attributes currently show **clock times**;
  see [Realtime arrival analysis](realtime-arrivals.md) for proposed
  predictive countdown indicators and origin-stop behavior.

## Screenshot checklist (to add later)

1. Main map, preferably showing both transport and stop markers.
2. Stop marker More Info with five arrivals.
3. Optional Browser Mod popup at desktop/mobile width.
4. Example of marker clustering/spreading in a dense area.
