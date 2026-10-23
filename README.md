# hslhrt-hass-custom

Custom Home Assistant integration for HSL public transport stops in the Helsinki region, using the [Digitransit Routing v2 GraphQL API](https://digitransit.fi/en/developers/apis/1-routing-api/).

## Digitransit API key

Digitransit requires a free subscription key. Register and obtain yours at https://portal-api.digitransit.fi/ . The integration sends it using the `digitransit-subscription-key` header and stores the key in Home Assistant's config entry.

**Upgrading from 0.3.5:** Existing configured stops are retained. After updating, Home Assistant asks you to **Reauthenticate** the integration to add an API key. Do not delete the old stop entries. You can also use **Reconfigure** to rotate a key.

## Installation

### HACS (custom repository)

1. Add `https://github.com/fursov/hslhrt-hass-custom` as a **custom Integration** repository in HACS.
2. Install the integration and restart Home Assistant.
3. Go to **Settings → Devices & services**, add **Helsinki Regional Transport**, and enter your API key and stop name/code.
4. Optionally enter a route or destination filter. Use `ALL` for any route/destination; a route takes precedence over destination.

### Manual installation

Copy the files from `custom_components/hslhrt/` in this repository into your Home Assistant configuration directory at `custom_components/hslhrt/`. Restart Home Assistant and configure from **Settings → Devices & services**.

## Notes on v0.4.0

- Migrated from retired Routing v1 to Routing v2.
- Uses HA's shared asynchronous HTTP session (no standalone GraphQL library).
- The one-sensor-per-config-entry model and legacy `ROUTE`, `DESTINATION`, `ARRIVAL TIME`, `ROUTES` attributes remain supported.
- Realtime arrival timestamps are computed from `serviceDay` and the appropriate arrival offset, so journeys across midnight and daylight-saving transitions are handled correctly.
- Stop name disambiguation is supported beginning with v0.6.0.
- This version has not been live-tested against Digitransit with a personal API key; tests use fixture responses.

## Fixes (v0.6.1)

- **Public stop code search:** Input such as `E4971`, `E4972`, `H0209` or `Si2223` is now resolved via Digitransit Geocoding, rather than passed to the Routing GraphQL name search. The chosen GTFS stop is always checked against its public code before creating a config entry.
- **Name search:** Names such as `Eestinmalmintie` still show a stop picker when multiple boarding platforms share the same name.
- The same Digitransit subscription key is used for both Routing and Geocoding APIs. Ensure that your subscription permits access to Geocoding v1.
- **No migration:** Existing config entries and entity IDs remain unchanged. This fix affects adding new stops only.

## Configuration improvements (v0.6.0)

- **Stop picker:** Searching by name now offers a dropdown of matching stop platforms, including the public code and GTFS ID, instead of silently taking the first result. Exact stop codes and GTFS IDs skip the picker. The picker shows at most the first 50 valid API results; narrow your search if necessary.
- **Options:** Open **Settings → Devices & services → Helsinki Regional Transport → Configure** for a configured stop. Select any number of routes, optionally a destination, and a polling interval of 1, 2, 3, 5, 10, 15 or 30 minutes. Leave route selection empty to include all routes. A nonempty route selection takes precedence over the destination filter.
- **Compatibility:** Existing entries without options keep their original single-route or destination filter and the 1-minute polling interval. Saving Options preserves the config entry and entity unique IDs; the display name may reflect the newly selected routes. Configured options trigger an automatic integration reload.
- **Rate limits:** One Digitransit timetable query is made per configured stop/route entry at each poll. Reducing polling frequency reduces API requests but also makes arrival predictions and the minute ETA less current.

## Maintenance (v0.5.1)

- Fix loading the configuration flow on recent Home Assistant versions: `ConfigType` is imported from `homeassistant.helpers.typing`, not `homeassistant.core`.
- No changes to existing configured stops, API keys, sensor IDs or polling behavior.

## Sensors (v0.5.0)

Each configured stop/route creates three sensors:

| Sensor | Example state | Notes |
| --- | --- | --- |
| Existing route sensor | `8` | Maintains the original `unique_id` and the legacy `ROUTE`, `DESTINATION`, `ARRIVAL TIME`, and `ROUTES` attributes |
| Next arrival | `2026-10-23T12:15:00+00:00` | Timestamp sensor (timezone-aware UTC); Home Assistant displays it in the local timezone |
| Minutes until arrival | `4` | Numeric sensor, unit `min`, updated with the stop's one-minute polling cycle and rounded up |

**Entity IDs:** Home Assistant generates entity IDs from names and its entity registry. Existing entity IDs are not renamed intentionally. The new entity IDs may differ depending on previous installations and user customizations.

The route sensor also exposes a compact `departures` list **including** the next arrival, with route, destination, scheduled/realtime timestamps, and delay in seconds. The existing `ROUTES` attribute still **excludes** the next arrival, consistent with v0.4.0 and the historical implementation. For storage safety, it contains at most **20 subsequent departures**; `departures` contains at most **10 departures**. The original query still requests up to 100 journeys. Expired and cancelled departures are not included.

Stop metadata (`STOP NAME`, `STOP CODE`, `GTFS ID`) is present even if there are no upcoming journeys. If the stop has no upcoming journeys, all three sensors have an unknown state (`None` internally), while `ROUTES` and `departures` are empty. If the Digitransit request fails, the coordinator marks its entities unavailable instead.

This release retains the existing API key and reauthentication flow from v0.4.0. It is a sensor-focused update; selecting among multiple stops and HFP vehicle tracking are separate future changes.

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
