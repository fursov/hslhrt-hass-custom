"""Real Home Assistant integration-test fixtures, isolated from stubbed unit tests."""

from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hslhrt.const import DOMAIN

# Explicit plugin registration supplies the real HA 'hass' and registry fixtures.
pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def enable_hslhrt_custom_integration(enable_custom_integrations):
    """Tell HA's integration loader to search custom_components."""
    yield


@pytest.fixture
def make_entry():
    """Generate real ConfigEntry records while retaining legacy IDs."""
    def build(route="8", options=None, api_key="TEST-KEY"):
        return MockConfigEntry(
            domain=DOMAIN,
            unique_id=f"HSL:1000 {route.upper()}",
            title=f"Example (E4971) {route.upper()}",
            data={
                "stop_gtfs": "HSL:1000",
                "stop_name": "Example",
                "stop_code": "E4971",
                "route": route,
                "destination": "ALL",
                **({"api_key": api_key} if api_key is not None else {}),
            },
            options=options or {},
        )
    return build


@pytest.fixture
def stop_response():
    """Return a realistic future timestamp computed from a Helsinki service day."""
    local = datetime.now(ZoneInfo("Europe/Helsinki"))
    service_day = int(
        datetime.combine(local.date(), time.min, tzinfo=ZoneInfo("Europe/Helsinki"))
        .timestamp()
    )
    arrival = int(datetime.now(timezone.utc).timestamp()) + 600 - service_day

    def build(route="8", departure_count=1):
        return {
            "gtfsId": "HSL:1000",
            "name": "Example",
            "code": "E4971",
            "stoptimesWithoutPatterns": [
                {
                    "serviceDay": service_day,
                    "scheduledArrival": arrival + number * 120,
                    "realtimeArrival": arrival + number * 120,
                    "realtime": True,
                    "realtimeState": "UPDATED",
                    "headsign": "Kamppi",
                    "trip": {"route": {"shortName": route}},
                }
                for number in range(departure_count)
            ],
        }
    return build


@pytest.fixture
def mock_digitransit(stop_response):
    """Intercept all Digitransit client methods; never make network calls."""
    info = {
        "gtfsId": "HSL:1000", "code": "E4971", "name": "Example",
        "patterns": [
            {"headsign": "Kamppi", "route": {"shortName": "8"}},
            {"headsign": "Espoo", "route": {"shortName": "2"}},
        ],
    }
    with (
        patch("custom_components.hslhrt.DigitransitClient") as setup_client,
        patch("custom_components.hslhrt.config_flow.DigitransitClient") as flow_client,
    ):
        for client in (setup_client.return_value, flow_client.return_value):
            client.get_departures = AsyncMock(return_value=stop_response())
            client.get_stop_info = AsyncMock(return_value=info)
            client.search_stops = AsyncMock(return_value=[
                {"name": "Example", "code": "E4971", "gtfsId": "HSL:1000"},
                {"name": "Example", "code": "E4972", "gtfsId": "HSL:1001"},
            ])
            client.search_stop_by_code = AsyncMock(return_value={
                "gtfsId": "HSL:1000", "code": "E4971"
            })
        yield setup_client.return_value, flow_client.return_value
