from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.common import Coordinate, ScoreBreakdown, TimeOfDay, utcnow


class RouteAnalysisRequest(BaseModel):
    """User-facing request: either raw coordinates or free-text addresses."""

    origin: Coordinate | None = None
    destination: Coordinate | None = None
    origin_text: str | None = Field(default=None, description="Free-text address to geocode")
    destination_text: str | None = Field(default=None, description="Free-text address to geocode")
    departure_time: datetime | None = Field(
        default=None, description="Defaults to now if omitted"
    )
    max_alternatives: int = Field(default=3, ge=1, le=5)
    dimension_weights: dict[str, float] | None = Field(
        default=None,
        description="Optional override weights, keyed by ScoreDimension value, summing ~1.0",
    )

    @model_validator(mode="after")
    def _require_endpoints(self) -> "RouteAnalysisRequest":
        if self.origin is None and not self.origin_text:
            raise ValueError("origin or origin_text is required")
        if self.destination is None and not self.destination_text:
            raise ValueError("destination or destination_text is required")
        return self

    @property
    def effective_departure_time(self) -> datetime:
        return self.departure_time or utcnow()


class RouteSegment(BaseModel):
    """A stretch of a route with per-segment context used for scoring."""

    start: Coordinate
    end: Coordinate
    distance_m: float = Field(..., ge=0)
    street_name: str | None = None
    is_main_road: bool = False


class RouteCandidate(BaseModel):
    """A single candidate walking route as returned by the routing provider."""

    route_id: str
    geometry: list[Coordinate]
    segments: list[RouteSegment]
    distance_m: float = Field(..., ge=0)
    duration_s: float = Field(..., ge=0)
    provider: str = "openrouteservice"


class ScoredRoute(BaseModel):
    """A route candidate enriched with its score breakdown and explanation."""

    candidate: RouteCandidate
    score: ScoreBreakdown
    explanation: str | None = None
    incident_count_nearby: int = 0


class RouteAnalysisResult(BaseModel):
    """Final response: all scored candidates, ranked best-first."""

    origin: Coordinate
    destination: Coordinate
    time_of_day: TimeOfDay
    generated_at: datetime = Field(default_factory=utcnow)
    routes: list[ScoredRoute]
    recommended_route_id: str | None = None

    @model_validator(mode="after")
    def _set_recommended(self) -> "RouteAnalysisResult":
        if self.routes and self.recommended_route_id is None:
            best = max(self.routes, key=lambda r: r.score.overall)
            self.recommended_route_id = best.candidate.route_id
        return self
