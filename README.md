# hslhrt-hass-custom

Custom Home Assistant integration for HSL public transport stop departures in the Helsinki metropolitan area. Data is provided by [Digitransit](https://digitransit.fi/en/).

> [!WARNING]
> The legacy integration currently uses Digitransit Routing API v1, which was retired in April 2025. **This repository-layout PR does not restore API functionality.** Routing v2 and API-key authentication are planned for a separate follow-up PR. Do not treat this branch as a working replacement for the legacy integration yet.

## Installation

### HACS (custom repository)

1. In HACS, open the menu for adding a custom repository.
2. Enter `https://github.com/fursov/hslhrt-hass-custom` and select **Integration**.
3. Install the repository, restart Home Assistant, then add **Helsinki Regional Transport** under **Settings → Devices & services**.

### Manual installation

Copy the **contents** of this repository's `custom_components/hslhrt/` directory into `<Home Assistant config>/custom_components/hslhrt/` and restart Home Assistant.

There must be no extra nested `custom_components` folder. The integration is configured through the UI: enter a stop name or public stop code, and optionally a route or destination. `ALL` disables the respective filter. Route selection takes precedence over destination.

The `hacs.json` manifest currently declares Home Assistant **2025.1.0** as the *target minimum version for modernization*. Runtime compatibility has not yet been verified; the old API remains unavailable until PR2.

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
