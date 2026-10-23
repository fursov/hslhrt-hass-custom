"""Mock HTTP-level tests of the Digitransit v2 client."""

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hslhrt"
package = types.ModuleType("hslhrt")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("hslhrt", package)
client_module = importlib.import_module("hslhrt.client")


class Response:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self.payload


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_request_uses_v2_post_with_key_header():
    session = Session(Response(payload={"data": {"stops": []}}))
    client = client_module.DigitransitClient(session, "SECRET-KEY")
    assert asyncio.run(client.search_stops("Töölöntori")) == []
    url, kwargs = session.calls[0]
    assert url.endswith("/routing/v2/hsl/gtfs/v1")
    assert kwargs["headers"] == {"digitransit-subscription-key": "SECRET-KEY"}
    assert kwargs["json"]["variables"] == {"name": "Töölöntori"}
    assert "stops(name:" in kwargs["json"]["query"]


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_api_key_does_not_leak_key(status):
    session = Session(Response(status=status))
    client = client_module.DigitransitClient(session, "TOP-SECRET")
    with pytest.raises(client_module.DigitransitAuthError) as exc:
        asyncio.run(client.get_departures("HSL:123"))
    assert "TOP-SECRET" not in str(exc.value)


def test_graphql_errors_do_not_expose_server_response():
    session = Session(Response(payload={
        "errors": [{"message": "secret backend details"}], "data": None
    }))
    client = client_module.DigitransitClient(session, "SECRET-KEY")
    with pytest.raises(client_module.DigitransitError) as exc:
        asyncio.run(client.get_stop_info("HSL:123"))
    assert "secret backend details" not in str(exc.value)


def test_stop_query_uses_bounded_departures():
    session = Session(Response(payload={"data": {"stop": {
        "gtfsId": "HSL:123",
        "stoptimesWithoutPatterns": [],
    }}}))
    client = client_module.DigitransitClient(session, "SECRET-KEY")
    stop = asyncio.run(client.get_departures("HSL:123"))
    assert stop["gtfsId"] == "HSL:123"
    assert "numberOfDepartures: 100" in session.calls[0][1]["json"]["query"]
