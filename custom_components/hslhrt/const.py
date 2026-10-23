"""Constants and GraphQL queries for the HSL Digitransit integration."""

import logging
from datetime import timedelta

_LOGGER = logging.getLogger(__package__)

DOMAIN = "hslhrt"
NAME = DEFAULT_NAME = "HSLHRT"
MANUFACTURER = "Helsinki Regional Transport Authority"
COORDINATOR = "coordinator"
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)
DEFAULT_SCAN_INTERVAL = 1
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ROUTES = "routes_filter"
CONF_DESTINATION_FILTER = "destination_filter"
CONF_SELECTED_STOP = "selected_stop"
UNDO_UPDATE_LISTENER = "undo_update_listener"

BASE_URL = "https://api.digitransit.fi/routing/v2/hsl/gtfs/v1"
CONF_API_KEY = "api_key"
API_KEY_HEADER = "digitransit-subscription-key"
REQUEST_TIMEOUT = 10
DEPARTURE_LIMIT = 100
# Keep entity attributes small to avoid bloating Recorder storage.
MAX_LEGACY_ROUTES = 20
MAX_DEPARTURES_ATTRIBUTE = 10

NAME_CODE = "user_name_code"
STOP_CODE = "stop_code"
STOP_NAME = "stop_name"
STOP_GTFS = "stop_gtfs"
ROUTE = "route"
DESTINATION = "destination"
ALL = "all"

DICT_KEY_ROUTE = "route"
DICT_KEY_ROUTES = "routes"
DICT_KEY_DEST = "destination"
DICT_KEY_ARRIVAL = "arrival"

ATTR_ROUTE = "ROUTE"
ATTR_DEST = "DESTINATION"
ATTR_ARR_TIME = "ARRIVAL TIME"
ATTR_STOP_NAME = "STOP NAME"
ATTR_STOP_CODE = "STOP CODE"
ATTR_STOP_GTFS = "GTFS ID"
ATTRIBUTION = "Data provided by Digitransit / Helsinki Regional Transport (HSL)"

# Only query fields supported by Digitransit Routing v2 (GTFS GraphQL).
STOP_SEARCH_QUERY = """
query FindStops($name: String!) {
  stops(name: $name) {
    gtfsId
    name
    code
  }
}
"""

STOP_INFO_QUERY = """
query StopInfo($id: String!) {
  stop(id: $id) {
    gtfsId
    name
    code
    patterns {
      headsign
      route {
        shortName
      }
    }
  }
}
"""

# The GraphQL service defaults startTime to the current time.
# Request a bounded set of the next departures; do not fetch a full day each minute.
STOP_DEPARTURES_QUERY = """
query StopDepartures($id: String!) {
  stop(id: $id) {
    gtfsId
    name
    code
    stoptimesWithoutPatterns(numberOfDepartures: 100) {
      serviceDay
      scheduledArrival
      realtimeArrival
      realtime
      realtimeState
      headsign
      trip {
        route {
          shortName
        }
      }
    }
  }
}
"""
