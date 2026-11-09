from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_geocoder
from app.models.common import Coordinate
from app.services.geocoding import GeoapifyClient

router = APIRouter(prefix="/geocode", tags=["geocode"])


@router.get("", response_model=Coordinate)
async def geocode_address(
    q: Annotated[str, Query(min_length=2, description="Free-text address or place name")],
    geocoder: Annotated[GeoapifyClient, Depends(get_geocoder)],
) -> Coordinate:
    return await geocoder.geocode(q)
