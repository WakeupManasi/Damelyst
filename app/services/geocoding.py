from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.common import Coordinate
from app.services.errors import GeocodeNotFoundError, GeocodingError, UpstreamConfigError

logger = get_logger(__name__)


class GeoapifyClient:
    """Thin async wrapper around the Geoapify Geocoding API."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def geocode(self, query: str) -> Coordinate:
        if not self._settings.has_live_geoapify:
            raise UpstreamConfigError(
                "GEOAPIFY_API_KEY is not configured; cannot geocode free-text addresses."
            )
        try:
            data = await self._request(query)
        except httpx.HTTPError as exc:
            logger.exception("Geoapify request failed")
            raise GeocodingError(f"Geoapify request failed: {exc}") from exc

        features = data.get("features") or []
        if not features:
            raise GeocodeNotFoundError(f"No geocoding match for query: {query!r}")

        lon, lat = features[0]["geometry"]["coordinates"][:2]
        return Coordinate(lon=lon, lat=lat)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, query: str) -> dict:
        url = f"{self._settings.geoapify_base_url}/v1/geocode/search"
        response = await self._client.get(
            url,
            params={"text": query, "apiKey": self._settings.geoapify_api_key, "limit": 1},
            timeout=self._settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
