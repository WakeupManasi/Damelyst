from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class TimeOfDay(StrEnum):
    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"

    @classmethod
    def from_hour(cls, hour: int) -> "TimeOfDay":
        if 5 <= hour < 8:
            return cls.DAWN
        if 8 <= hour < 18:
            return cls.DAY
        if 18 <= hour < 21:
            return cls.DUSK
        return cls.NIGHT


class Coordinate(BaseModel):
    """WGS84 lon/lat pair. Longitude first to match GeoJSON convention."""

    lon: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)

    def as_tuple(self) -> tuple[float, float]:
        return (self.lon, self.lat)


class ScoreDimension(StrEnum):
    LIGHTING = "lighting"
    ACTIVITY = "activity"
    VISIBILITY = "visibility"
    MAIN_ROAD_QUALITY = "main_road_quality"
    OVERSIGHT = "oversight"
    EMERGENCY_PROXIMITY = "emergency_proximity"
    INCIDENT_HISTORY = "incident_history"


class DimensionScore(BaseModel):
    """A single 0-100 dimension score plus the rationale behind it."""

    dimension: ScoreDimension
    value: float = Field(..., ge=0, le=100)
    weight: float = Field(..., ge=0, le=1)
    rationale: str


class ScoreBreakdown(BaseModel):
    """Composite safety/quality score for a route, built from weighted dimensions."""

    overall: float = Field(..., ge=0, le=100)
    dimensions: list[DimensionScore]
    time_of_day: TimeOfDay

    @field_validator("dimensions")
    @classmethod
    def _non_empty(cls, v: list[DimensionScore]) -> list[DimensionScore]:
        if not v:
            raise ValueError("dimensions must not be empty")
        return v


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
