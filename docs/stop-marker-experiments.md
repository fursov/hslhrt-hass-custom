# Experiments: compact HSL stop markers on Home Assistant maps

HSL HRT 0.9.0 publishes tracked physical stops as transient
`geo_location` entities from the `hslhrt_stops` source. Those entities
are useful and correct, but **the built-in Map Card always wraps ordinary
geolocation markers in its standard marker shape**, so the existing
`mdi:circle-small` appears as a tiny dot *inside* a large dark pin.

The default Map Card also clusters nearby markers as you zoom out.
These behaviors are frontend presentation choices, not issues with the
Digitransit latitude/longitude data. There is no per-source setting
for a 6-pixel circle in the stock Map Card.

## First control: keep the native Map Card but turn clustering off

```yaml
type: map
geo_location_sources:
  - source: hslhrt
    label_mode: attribute
    attribute: marker_label
  - source: hslhrt_stops
    label_mode: icon
cluster: false
auto_fit: true
```

`cluster: false` is supported by Home Assistant 2026.10 and prevents
**all** markers (both vehicles and stops) from being grouped at smaller
zoom levels. The pins remain full size, may overlap and may obscure the
map. You can test this without updating HSL HRT.

## Approach A: try individually sized icons in a custom Leaflet map

The third-party [Home Assistant Map Card
(nathan-gs/ha-map-card)](https://github.com/nathan-gs/ha-map-card)
supports `size` per entity and `cluster_markers: false`.

Install this *separate frontend card* through HACS first, then replace
the sample entity IDs below with real IDs from **Developer Tools → States**.
Stop IDs begin with `geo_location.hslhrt_stop_`. The trailing part is a
stable, installation-specific hash, **not the stop code**.

```yaml
type: custom:map-card
cluster_markers: false
entities:
  - entity: geo_location.hslhrt_stop_REPLACE_WITH_REAL_ID
    display: icon
    icon: mdi:circle
    size: 12
    color: "#80c4ec"
```

This tests whether an independently sized 12 px marker is sufficiently
small and readable. If a circle with a thin outline is needed instead,
a purpose-built Leaflet `CircleMarker` component would be required.
The `size` option **does not change Home Assistant's built-in Map
Card**, and the visual result needs validation with the installed
custom-card version.

**Limitation:** the third-party card's documented entity configuration
requires explicit entity IDs. It does *not* document an equivalent of
`geo_location_sources` that automatically discovers changing HFP vehicle
entities. Consequently this is a **stop-only visual experiment**, not a
drop-in replacement for the combined live bus-and-stop map. Do not
migrate your existing main map to it without checking that limitation.

## Approach B: compare one temporary Home Assistant zone

Zones are a different domain, `zone.*`, and are drawn separately from
the ordinary geo_location marker cluster in the frontend. They have a
**radius in meters** and a zone icon, not a freely scalable screen-pixel
dot. Even a tiny-radius zone may still display an icon at its center.

For a one-stop **temporary comparison only**:

1. In Home Assistant, go to **Settings → Areas, labels & zones → Zones**.
   Create a zone at the actual HSL stop's coordinates, give it a distinct
   name like `HSL stop test`, set a small radius (e.g. 5 meters if your
   UI accepts it) and choose `mdi:circle-small`. Check the marker in a
   separate dashboard. Do **not** generate a large collection of zones.
2. Add the test zone to a *separate* Map Card alongside vehicles:

```yaml
type: map
geo_location_sources:
  - source: hslhrt
    label_mode: attribute
    attribute: marker_label
entities:
  - zone.hsl_stop_test
show_zone_radius: true
cluster: false
auto_fit: true
```

The custom `zone.hsl_stop_test` ID is **illustrative**, not guaranteed;
use the ID HA assigns. When the experiment ends, delete the test zone.

### Why not automatically create zone entities in the integration?

* **Normal (non-passive) zones influence presence tracking:** a nearby
  person/device tracker may be considered to occupy the bus stop zone.
  They also appear in the Zones section of Home Assistant.
* **Passive zones are explicitly hidden in ordinary/panel Map Card views.**
  This avoids presence-tracking effects but makes them unsuitable as
  a simple automatic stop layer without additional frontend work.
* Home Assistant renders zones in a separate layer that does not join
  the ordinary marker cluster, but *a zone is not a tiny dot*. The
  circle size is measured in meters and changes on screen with zoom.
* A real stop can have multiple configuration entries; duplicates
  would create additional zone records unless deduplicated.

**Recommendation:** retain the current `geo_location` stop entities
and do not publish zone entities from the integration. Try the small-icon
custom card for visual comparison; if exact non-clustering 6–8 px dots
next to dynamic vehicle markers are needed, use a dedicated HSL
frontend layer that renders Leaflet CircleMarkers, instead of changing
the backend entity domain.

References:

- [Home Assistant built-in Map Card](https://www.home-assistant.io/dashboards/map/)
- [Home Assistant zones](https://www.home-assistant.io/integrations/zone/)
- [nathan-gs custom Map Card](https://github.com/nathan-gs/ha-map-card)
