from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencies import IncidentRepoDep
from app.models.common import Coordinate
from app.models.incident import IncidentCreate, IncidentReport
from app.services.errors import IncidentNotFoundError

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post("", response_model=IncidentReport, status_code=status.HTTP_201_CREATED)
async def create_incident(payload: IncidentCreate, repo: IncidentRepoDep) -> IncidentReport:
    """
    Submit a new incident report. There is no authentication in this
    prototype; reports start as `unverified` and would move through a
    verification workflow (community or official) in a production system.
    """
    report = IncidentReport.from_create(payload)
    return await repo.add(report)


@router.get("", response_model=list[IncidentReport])
async def list_nearby_incidents(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    repo: IncidentRepoDep,
    radius_m: Annotated[float, Query(ge=10, le=5000)] = 250,
    only_verified: bool = False,
) -> list[IncidentReport]:
    center = Coordinate(lon=lon, lat=lat)
    return await repo.list_near(center, radius_m, only_verified=only_verified)


@router.get("/{incident_id}", response_model=IncidentReport)
async def get_incident(incident_id: str, repo: IncidentRepoDep) -> IncidentReport:
    incident = await repo.get(incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident {incident_id} not found")
    return incident
