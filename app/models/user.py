from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.common import ScoreDimension


class UserRoutingPreferences(BaseModel):
    """
    Optional per-request preference profile. There is no authentication in this
    prototype, so preferences are passed by the client per-request rather than
    tied to a stored account.
    """

    dimension_weights: dict[ScoreDimension, float] = Field(default_factory=dict)
    avoid_incident_types: list[str] = Field(default_factory=list)
    max_detour_ratio: float = Field(
        default=1.5, ge=1.0, le=3.0, description="Max acceptable distance vs. the shortest route"
    )
