from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Coordinate, utcnow


class IncidentType(StrEnum):
    HARASSMENT = "harassment"
    THEFT = "theft"
    ASSAULT = "assault"
    UNSAFE_INFRASTRUCTURE = "unsafe_infrastructure"
    POOR_LIGHTING = "poor_lighting"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    OTHER = "other"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    COMMUNITY_VERIFIED = "community_verified"
    OFFICIALLY_VERIFIED = "officially_verified"
    REJECTED = "rejected"


class IncidentCreate(BaseModel):
    """Payload for submitting a new incident report."""

    location: Coordinate
    incident_type: IncidentType
    description: str = Field(..., min_length=3, max_length=1000)
    occurred_at: datetime | None = None
    reporter_id: str | None = Field(
        default=None, description="Opaque client-supplied id; no auth in this prototype"
    )


class IncidentReport(BaseModel):
    """Stored incident record."""

    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    location: Coordinate
    incident_type: IncidentType
    description: str
    occurred_at: datetime
    reported_at: datetime = Field(default_factory=utcnow)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    reporter_id: str | None = None

    @classmethod
    def from_create(cls, payload: IncidentCreate) -> "IncidentReport":
        return cls(
            location=payload.location,
            incident_type=payload.incident_type,
            description=payload.description,
            occurred_at=payload.occurred_at or utcnow(),
            reporter_id=payload.reporter_id,
        )


class NearbyIncidentQuery(BaseModel):
    center: Coordinate
    radius_m: float = Field(default=250, ge=10, le=5000)
    only_verified: bool = False
