from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.common import Coordinate
from app.models.incident import IncidentReport


@runtime_checkable
class IncidentRepository(Protocol):
    """Storage contract for incident reports. Swap the memory impl for a DB later."""

    async def add(self, incident: IncidentReport) -> IncidentReport: ...

    async def get(self, incident_id: str) -> IncidentReport | None: ...

    async def list_near(
        self, center: Coordinate, radius_m: float, only_verified: bool = False
    ) -> list[IncidentReport]: ...

    async def list_all(self) -> list[IncidentReport]: ...


@runtime_checkable
class RouteCacheRepository(Protocol):
    """Storage contract for caching route-analysis results by request signature."""

    async def get(self, key: str) -> dict | None: ...

    async def set(self, key: str, value: dict, ttl_seconds: int = 300) -> None: ...
