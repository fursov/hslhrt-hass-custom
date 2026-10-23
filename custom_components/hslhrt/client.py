"""Asynchronous Digitransit Routing v2 GraphQL client."""

import asyncio
from typing import Any

import aiohttp

from .const import (
    API_KEY_HEADER,
    BASE_URL,
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
        """Search stops by name or public code."""
        data = await self._query(STOP_SEARCH_QUERY, {"name": name})
        stops = data.get("stops")
        if not isinstance(stops, list):
            raise DigitransitError("Stop search returned invalid data")
        return [stop for stop in stops if isinstance(stop, dict)]

    async def get_stop_info(self, gtfs_id: str) -> dict[str, Any] | None:
        """Retrieve metadata for stop and its route patterns."""
        data = await self._query(STOP_INFO_QUERY, {"id": gtfs_id})
        return data.get("stop")

    async def get_departures(self, gtfs_id: str) -> dict[str, Any] | None:
        """Retrieve upcoming departures for a stop."""
        data = await self._query(STOP_DEPARTURES_QUERY, {"id": gtfs_id})
        return data.get("stop")
