"""Asynchronous Digitransit Routing v2 GraphQL client."""

import asyncio
import re
from typing import Any

import aiohttp

from .const import (
    API_KEY_HEADER,
    BASE_URL,
    GEOCODING_URL,
    REQUEST_TIMEOUT,
    STOP_DEPARTURES_QUERY,
    STOP_INFO_QUERY,
    STOP_SEARCH_QUERY,
)


class DigitransitError(Exception):
    """An API request could not be completed."""


class DigitransitAuthError(DigitransitError):
    """The API rejected the subscription key."""


class DigitransitClient:
    """Small API client using Home Assistant's shared aiohttp session."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def _query(
        self, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                BASE_URL,
                json={"query": query, "variables": variables},
                headers={API_KEY_HEADER: self._api_key},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status in (401, 403):
                    raise DigitransitAuthError("Digitransit API key was rejected")
                if response.status != 200:
                    raise DigitransitError(
                        f"Digitransit returned HTTP {response.status}"
                    )
                payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            # Do not expose response bodies, URLs with query strings or API keys.
            raise DigitransitError("Unable to reach Digitransit") from error

        if not isinstance(payload, dict):
            raise DigitransitError("Invalid Digitransit response")
        if payload.get("errors"):
            # The response's error descriptions are not trusted and may contain
            # implementation details. Do not log or expose them verbatim.
            raise DigitransitError("Digitransit GraphQL request failed")
        if not isinstance(payload.get("data"), dict):
            raise DigitransitError("Digitransit response has no data")
        return payload["data"]

    async def search_stops(self, name: str) -> list[dict[str, Any]]:
        """Search stops by name using the Routing GraphQL API."""
        data = await self._query(STOP_SEARCH_QUERY, {"name": name})
        stops = data.get("stops")
        if not isinstance(stops, list):
            raise DigitransitError("Stop search returned invalid data")
        return [stop for stop in stops if isinstance(stop, dict)]



    async def search_stop_by_code(self, code: str) -> dict[str, Any] | None:
        """Find a public HSL stop code with the Digitransit geocoder.

        GraphQL `stops(name: ...)` searches *names*, not the rider-facing
        stop code. Geocoding supplies the actual GTFS identifier, which is
        subsequently verified against the Routing API by the config flow.
        """
        normalized = code.strip().upper()
        try:
            async with self._session.get(
                GEOCODING_URL,
                params={"text": normalized, "layers": "stop", "size": 20},
                headers={API_KEY_HEADER: self._api_key},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status in (401, 403):
                    raise DigitransitAuthError(
                        "Digitransit geocoding subscription key was rejected"
                    )
                if response.status != 200:
                    raise DigitransitError(
                        f"Digitransit geocoding returned HTTP {response.status}"
                    )
                payload = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            raise DigitransitError("Unable to search Digitransit stop codes") from error

        if not isinstance(payload, dict) or not isinstance(
            payload.get("features"), list
        ):
            raise DigitransitError("Invalid Digitransit geocoding response")

        for feature in payload["features"]:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties")
            if not isinstance(props, dict) or props.get("layer") != "stop":
                continue

            gid = props.get("gid")
            gid = gid if isinstance(gid, str) else ""
            suffix = gid.rpartition("#")[2].upper() if "#" in gid else ""
            possible_codes = (props.get("code"), props.get("shortName"), suffix)
            if not any(
                isinstance(value, str) and value.strip().upper() == normalized
                for value in possible_codes
            ):
                continue

            gtfs_id = props.get("gtfsId")
            if not isinstance(gtfs_id, str) or not gtfs_id.startswith("HSL:"):
                match = re.search(r"HSL:[A-Za-z0-9]+(?=#|$)", gid, re.IGNORECASE)
                gtfs_id = match.group(0).upper() if match else None
            if gtfs_id:
                return {"gtfsId": gtfs_id, "code": normalized}
        return None

    async def get_stop_info(self, gtfs_id: str) -> dict[str, Any] | None:
        """Retrieve metadata for stop and its route patterns."""
        data = await self._query(STOP_INFO_QUERY, {"id": gtfs_id})
        return data.get("stop")

    async def get_departures(self, gtfs_id: str) -> dict[str, Any] | None:
        """Retrieve upcoming departures for a stop."""
        data = await self._query(STOP_DEPARTURES_QUERY, {"id": gtfs_id})
        return data.get("stop")
