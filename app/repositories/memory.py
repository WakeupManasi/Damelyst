from __future__ import annotations

import asyncio
import time

from app.models.common import Coordinate
from app.models.incident import IncidentReport
from app.services.geometry import haversine_m


class InMemoryIncidentRepository:
    """
    Async-safe, process-local incident store. Implements IncidentRepository.
    Replace with a Postgres/PostGIS-backed implementation later without touching
    callers, since they depend on the protocol, not this class.
    """

    def __init__(self) -> None:
        self._items: dict[str, IncidentReport] = {}
        self._lock = asyncio.Lock()

    async def add(self, incident: IncidentReport) -> IncidentReport:
        async with self._lock:
            self._items[incident.incident_id] = incident
        return incident

    async def get(self, incident_id: str) -> IncidentReport | None:
        return self._items.get(incident_id)

    async def list_near(
        self, center: Coordinate, radius_m: float, only_verified: bool = False
    ) -> list[IncidentReport]:
        results = []
        for item in self._items.values():
            if only_verified and item.verification_status == "unverified":
                continue
            if haversine_m(center, item.location) <= radius_m:
                results.append(item)
        return results

    async def list_all(self) -> list[IncidentReport]:
        return list(self._items.values())

    async def seed(self, incidents: list[IncidentReport]) -> None:
        async with self._lock:
            for incident in incidents:
                self._items[incident.incident_id] = incident


class InMemoryRouteCache:
    """Simple TTL cache for route-analysis results. Implements RouteCacheRepository."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, dict]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            async with self._lock:
                self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: dict, ttl_seconds: int = 300) -> None:
        async with self._lock:
            self._store[key] = (time.monotonic() + ttl_seconds, value)
