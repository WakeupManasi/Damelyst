from __future__ import annotations

import pytest

from app.models.common import Coordinate
from app.models.incident import IncidentCreate, IncidentReport, IncidentType
from app.repositories.memory import InMemoryIncidentRepository, InMemoryRouteCache


@pytest.mark.asyncio
async def test_add_and_get_incident():
    repo = InMemoryIncidentRepository()
    report = IncidentReport.from_create(
        IncidentCreate(
            location=Coordinate(lon=0.0, lat=0.0),
            incident_type=IncidentType.POOR_LIGHTING,
            description="Streetlight out for a week.",
        )
    )
    await repo.add(report)

    fetched = await repo.get(report.incident_id)
    assert fetched is not None
    assert fetched.incident_id == report.incident_id


@pytest.mark.asyncio
async def test_list_near_filters_by_radius():
    repo = InMemoryIncidentRepository()
    close = IncidentReport.from_create(
        IncidentCreate(
            location=Coordinate(lon=0.0, lat=0.001),
            incident_type=IncidentType.OTHER,
            description="Close incident",
        )
    )
    far = IncidentReport.from_create(
        IncidentCreate(
            location=Coordinate(lon=1.0, lat=1.0),
            incident_type=IncidentType.OTHER,
            description="Far incident",
        )
    )
    await repo.add(close)
    await repo.add(far)

    nearby = await repo.list_near(Coordinate(lon=0.0, lat=0.0), radius_m=500)
    ids = {i.incident_id for i in nearby}
    assert close.incident_id in ids
    assert far.incident_id not in ids


@pytest.mark.asyncio
async def test_route_cache_expires():
    cache = InMemoryRouteCache()
    await cache.set("key", {"a": 1}, ttl_seconds=0)
    # TTL of 0 should already be expired on next check.
    import asyncio

    await asyncio.sleep(0.01)
    value = await cache.get("key")
    assert value is None


@pytest.mark.asyncio
async def test_route_cache_returns_value_before_expiry():
    cache = InMemoryRouteCache()
    await cache.set("key", {"a": 1}, ttl_seconds=60)
    value = await cache.get("key")
    assert value == {"a": 1}
