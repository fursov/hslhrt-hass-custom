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

This release can track **multiple next journeys per route at the configured
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
GPS points on the native Home Assistant map are planned for PR9.

## Live vehicle map (v0.8.0)

With HFP tracking enabled on a configured stop, the integration now publishes
**temporary** `geo_location` entities for selected upcoming journeys that
currently have fresh HFP GPS coordinates. No marker is shown when the vehicle
is not known or its last position is older than 90 seconds.

Add a built-in **Map** card and select **HSL HRT** (`hslhrt`) under
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

## Sensor

Sensor provides real time arrival information of a `route` (bus/tram) if available. If real time info is unavailable, it provides the scheduled arrival time of the `route`. If integration is configured with a `route`, sensor provides arrival times filtered for that `route` only. If the integration is configured without a `route`, it provides arrival times for all `routes` arriving at the given stop, in order of their arrival time. Sensor attributes provide the `Stop Name`, `Stop Code`, `Stop GTFS ID` and a list of upcoming `routes` with their arrival times for the day.

<br/>

## UI Options (Entities Card Configuration)

### Option-1
<br/>
Display HSL stops as a list also showing the upcoming route

![Option-1](resources/images/ui-option-1.jpg?raw=true)
<br/>

#### Lovelace UI Entities Card Configuration, for Option-1:
```
type: entities
entities:
  - entity: sensor.toolontori_h0209_2
  - entity: sensor.toolontori_h0209_all
  - entity: sensor.toolontori_h0209_8
  - entity: sensor.jupperi_e1465_all
title: HSL Lines
show_header_toggle: false
```

<br/>

### Option-2
<br/>
Display a HSL stop with attributes showing route, arrival time and destination

![Option-2](resources/images/ui-option-2.jpg?raw=true)

<br/>

#### Lovalace UI Entities Card Configuration, for Option-2:
```
type: entities
title: HSL - Route - 8
entities:
  - type: attribute
    icon: 'mdi:city-variant'
    entity: sensor.toolontori_h0209_8
    attribute: STOP NAME
    name: Stop Name
  - type: attribute
    icon: 'mdi:format-title'
    entity: sensor.toolontori_h0209_8
    attribute: STOP CODE
    name: Stop Code
  - type: attribute
    icon: 'mdi:bus'
    entity: sensor.toolontori_h0209_8
    attribute: ROUTE
    name: Next Line
  - type: attribute
    icon: 'mdi:city'
    entity: sensor.toolontori_h0209_8
    attribute: DESTINATION
    name: Destination
  - type: attribute
    icon: 'mdi:clock'
    entity: sensor.toolontori_h0209_8
    attribute: ARRIVAL TIME
    name: Arrival Time
```
<br/>

### Option-3
<br/>
With a template sensor, more UI options are possible, such as displaying remaining time until next arrival and next two upcoming arrival times:

![Option-3](resources/images/ui-option-3.jpg?raw=true)

<br/>

#### Template Sensor for next 2 routes at the stop, for Option-3:
```
  - platform: template
    sensors:
      next_route_533_1:
        friendly_name: Next 533 - 1
        value_template: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') != None %}
                           {% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') | length > 0 %}
                             {{ state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES')[0]['ARRIVAL TIME'] }}
                           {% else %}
                             'No more lines today'
                           {% endif %}
                         {% else %}
                           'No more lines today'
                         {% endif %}"
        attribute_templates:
          route: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') != None %}
                    {% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') | length > 0 %}
                      {{ state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES')[0]['ROUTE'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') != None %}
                          {% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') | length > 0 %}
                            {{ state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES')[0]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
      next_route_533_2:
        friendly_name: Next 533 - 2
        value_template: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') != None %}
                           {% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') | length > 1 %}
                             {{ state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES')[1]['ARRIVAL TIME'] }}
                           {% else %}
                             'No more lines today'
                           {% endif %}
                         {% else %}
                           'No more lines today'
                         {% endif %}"
        attribute_templates:
          route: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') != None %}
                    {% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') | length > 1 %}
                      {{ state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES')[1]['ROUTE'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') != None %}
                          {% if state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES') | length > 1 %}
                            {{ state_attr('sensor.henttaanaukio_e3313_533', 'ROUTES')[1]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
      time_533_remaining:
        friendly_name: "Time Until Next 533 Arrival"
        value_template: "{% if state_attr('sensor.henttaanaukio_e3313_533', 'ARRIVAL TIME') != None %}
                           {% set curr_time = now().replace(tzinfo=None) %}
                           {% set time_str = state_attr('sensor.henttaanaukio_e3313_533', 'ARRIVAL TIME') %}
                           {% set time_obj = strptime(time_str, '%H:%M:%S') %}
                           {% set right_time = time_obj.replace(year=curr_time.year, day=curr_time.day, month=curr_time.month) %}
                           {% set td = right_time - curr_time %}
                           {{ td.seconds | int| timestamp_custom('%H:%M:%S', false) }}
                         {% else %}
                           'Unavailable'
                         {% endif %}"
```
<br/>

#### Lovalace UI using Entities Card Configuration, for Option-3:
```
type: entities
title: HSL - School - 533
entities:
  - type: attribute
    icon: 'mdi:city-variant'
    entity: sensor.henttaanaukio_e3313_533
    attribute: STOP NAME
    name: Stop Name
  - type: attribute
    icon: 'mdi:format-title'
    entity: sensor.henttaanaukio_e3313_533
    attribute: STOP CODE
    name: Stop Code
  - type: attribute
    icon: 'mdi:bus'
    entity: sensor.henttaanaukio_e3313_533
    attribute: ROUTE
    name: Next Line
  - type: attribute
    icon: 'mdi:city'
    entity: sensor.henttaanaukio_e3313_533
    attribute: DESTINATION
    name: Destination
  - type: attribute
    icon: 'mdi:clock'
    entity: sensor.henttaanaukio_e3313_533
    attribute: ARRIVAL TIME
    name: Arrival Time
  - entity: sensor.time_533_remaining
    name: Time Until Next Arrival
  - entity: sensor.next_route_533_1
    name: Next 533 Option 1
  - entity: sensor.next_route_533_2
    name: Next 533 Option 2
```

<br/>

### Option-4
<br/>
With a template sensor, show the upcoming routes at a stop as a table:

![Option-4](resources/images/ui-option-4.jpg?raw=true)

<br/>

#### Template Sensor for next 4 routes at the stop, for Option-4:
```
##
## HSL Next Routes and Remaining Times!
##
## Norotie V1530
  - platform: template
    sensors:
      next_route_v1530_1:
        friendly_name: Next Route - 1
        value_template: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                           {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 0 %}
                             {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[0]['ROUTE'] }}
                           {% else %}
                             'NA'
                           {% endif %}
                         {% else %}
                           'NA'
                         {% endif %}"
        attribute_templates:
          arrival_time: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                    {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 0 %}
                      {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[0]['ARRIVAL TIME'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                          {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 0 %}
                            {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[0]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
      next_route_v1530_2:
        friendly_name: Next Route - 2
        value_template: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                           {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 1 %}
                             {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[1]['ROUTE'] }}
                           {% else %}
                             'NA'
                           {% endif %}
                         {% else %}
                           'NA'
                         {% endif %}"
        attribute_templates:
          arrival_time: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                    {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 1 %}
                      {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[1]['ARRIVAL TIME'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                          {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 1 %}
                            {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[1]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
      next_route_v1530_3:
        friendly_name: Next Route - 3
        value_template: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                           {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 2 %}
                             {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[2]['ROUTE'] }}
                           {% else %}
                             'NA'
                           {% endif %}
                         {% else %}
                           'NA'
                         {% endif %}"
        attribute_templates:
          arrival_time: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                    {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 2 %}
                      {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[2]['ARRIVAL TIME'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                          {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 2 %}
                            {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[2]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
      next_route_v1530_4:
        friendly_name: Next Route - 4
        value_template: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                           {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 3 %}
                             {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[3]['ROUTE'] }}
                           {% else %}
                             'NA'
                           {% endif %}
                         {% else %}
                           'NA'
                         {% endif %}"
        attribute_templates:
          arrival_time: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                    {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 3 %}
                      {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[3]['ARRIVAL TIME'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                          {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 3 %}
                            {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[3]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
      next_route_v1530_5:
        friendly_name: Next Route - 5
        value_template: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                           {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 4 %}
                             {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[4]['ROUTE'] }}
                           {% else %}
                             'NA'
                           {% endif %}
                         {% else %}
                           'NA'
                         {% endif %}"
        attribute_templates:
          arrival_time: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                    {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 4 %}
                      {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[4]['ARRIVAL TIME'] }}
                    {% else %}
                      'Unavailable'
                    {% endif %}
                  {% else %}
                    'Unavailable'
                  {% endif %}"
          destination: "{% if state_attr('sensor.norotie_v1530_all', 'ROUTES') != None %}
                          {% if state_attr('sensor.norotie_v1530_all', 'ROUTES') | length > 4 %}
                            {{ state_attr('sensor.norotie_v1530_all', 'ROUTES')[4]['DESTINATION'] }}
                          {% else %}
                            'Unavailable'
                          {% endif %}
                        {% else %}
                          'Unavailable'
                        {% endif %}"
```
<br/>

#### Lovalace Markdown Table with schedule using Entity Filter Card Configuration, for Option-4:
```
type: entity-filter
entities:
  - sensor.next_route_v1530_1
  - sensor.next_route_v1530_2
  - sensor.next_route_v1530_3
  - sensor.next_route_v1530_4
  - sensor.next_route_v1530_5  
state_filter:
  - operator: '!='
    value: "'NA'"
card:
  type: markdown
  content: >-
    | Arrival Time &nbsp;&nbsp;&nbsp;&nbsp; | Route &nbsp;&nbsp;&nbsp;&nbsp; | Destination |

    | :----------- | :---- | :---------- |

    | {% set n = 0 %} {% if config.entities | length > n %} {{
    state_attr(config.entities[n].entity, 'arrival_time') }} | {{
    states(config.entities[n].entity) }} | {{
    state_attr(config.entities[n].entity, 'destination') }} {% endif %} |

    | {% set n = 1 %} {% if config.entities | length > n %} {{
    state_attr(config.entities[n].entity, 'arrival_time') }} | {{
    states(config.entities[n].entity) }} | {{
    state_attr(config.entities[n].entity, 'destination') }} {% endif %} |

    | {% set n = 2 %} {% if config.entities | length > n %} {{
    state_attr(config.entities[n].entity, 'arrival_time') }} | {{
    states(config.entities[n].entity) }} | {{
    state_attr(config.entities[n].entity, 'destination') }} {% endif %} |

    | {% set n = 3 %} {% if config.entities | length > n %} {{
    state_attr(config.entities[n].entity, 'arrival_time') }} | {{
    states(config.entities[n].entity) }} | {{
    state_attr(config.entities[n].entity, 'destination') }} {% endif %} |

    | {% set n = 4 %} {% if config.entities | length > n %} {{
    state_attr(config.entities[n].entity, 'arrival_time') }} | {{
    states(config.entities[n].entity) }} | {{
    state_attr(config.entities[n].entity, 'destination') }} {% endif %} |

    | {% set n = 5 %} {% if config.entities | length > n %} {{
    state_attr(config.entities[n].entity, 'arrival_time') }} | {{
    states(config.entities[n].entity) }} | {{
    state_attr(config.entities[n].entity, 'destination') }} {% endif %} |

title: V1530 Next Lines

```

<br/>

**Note**: Sometimes the API query returns wierd results such as blank destinations or route numbers. If you see something like this, leave a comment and I can take a look at pruning the results further.

## Original Author
Anand Radhakrishnan [@anand-p-r](https://github.com/anand-p-r)
