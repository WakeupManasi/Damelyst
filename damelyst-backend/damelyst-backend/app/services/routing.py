from __future__ import annotations

import uuid

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.common import Coordinate
from app.models.route import RouteCandidate, RouteSegment
from app.services.errors import NoRoutesFoundError, RoutingError, UpstreamConfigError

logger = get_logger(__name__)

# Heuristic keywords for classifying a street as a "main road" when ORS road-class
# extras aren't requested/available. This is intentionally simple and swappable.
_MAIN_ROAD_HINTS = ("highway", "avenue", "boulevard", "main st", "main road", "expressway")


class OpenRouteServiceClient:
    """Thin async wrapper around the ORS Directions API (foot-walking profile)."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def get_walking_routes(
        self, origin: Coordinate, destination: Coordinate, alternatives: int = 3
    ) -> list[RouteCandidate]:
        if not self._settings.has_live_ors:
            raise UpstreamConfigError(
                "ORS_API_KEY is not configured; cannot fetch walking routes."
            )
        try:
            data = await self._request(origin, destination, alternatives)
        except httpx.HTTPError as exc:
            logger.exception("ORS request failed")
            raise RoutingError(f"OpenRouteService request failed: {exc}") from exc

        features = data.get("features") or []
        if not features:
            raise NoRoutesFoundError("OpenRouteService returned no walking routes.")

        return [self._to_candidate(feature) for feature in features]

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _request(
        self, origin: Coordinate, destination: Coordinate, alternatives: int
    ) -> dict:
        url = f"{self._settings.ors_base_url}/v2/directions/foot-walking/geojson"
        payload = {
            "coordinates": [list(origin.as_tuple()), list(destination.as_tuple())],
            "alternative_routes": {
                "target_count": max(1, alternatives),
                "share_factor": 0.6,
                "weight_factor": 1.6,
            },
            "extra_info": ["waytype", "steepness"],
            "instructions": True,
        }
        headers = {
            "Authorization": self._settings.ors_api_key,
            "Content-Type": "application/json",
        }
        response = await self._client.post(
            url, json=payload, headers=headers, timeout=self._settings.http_timeout_seconds
        )
        response.raise_for_status()
        return response.json()

    def _to_candidate(self, feature: dict) -> RouteCandidate:
        coords = feature["geometry"]["coordinates"]
        geometry = [Coordinate(lon=c[0], lat=c[1]) for c in coords]

        props = feature.get("properties", {})
        summary = props.get("summary", {})
        segments_raw = props.get("segments", [])

        segments: list[RouteSegment] = []
        for seg in segments_raw:
            for step in seg.get("steps", []):
                way_points = step.get("way_points", [0, 0])
                start_idx, end_idx = way_points[0], way_points[-1]
                if start_idx >= len(geometry) or end_idx >= len(geometry):
                    continue
                name = step.get("name") or None
                segments.append(
                    RouteSegment(
                        start=geometry[start_idx],
                        end=geometry[end_idx],
                        distance_m=step.get("distance", 0.0),
                        street_name=name,
                        is_main_road=_looks_like_main_road(name),
                    )
                )

        if not segments and len(geometry) >= 2:
            # Fallback: treat the whole route as one unnamed segment.
            segments = [
                RouteSegment(
                    start=geometry[0],
                    end=geometry[-1],
                    distance_m=summary.get("distance", 0.0),
                    street_name=None,
                    is_main_road=False,
                )
            ]

        return RouteCandidate(
            route_id=str(uuid.uuid4()),
            geometry=geometry,
            segments=segments,
            distance_m=summary.get("distance", 0.0),
            duration_s=summary.get("duration", 0.0),
        )


def _looks_like_main_road(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(hint in lowered for hint in _MAIN_ROAD_HINTS)
