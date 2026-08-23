from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from app.models.common import Coordinate, TimeOfDay
from app.models.incident import IncidentReport
from app.models.route import RouteAnalysisRequest, RouteCandidate, ScoredRoute
from app.repositories.protocols import IncidentRepository
from app.services.geocoding import GeoapifyClient
from app.services.llm import Explainer
from app.services.routing import OpenRouteServiceClient


@dataclass(frozen=True)
class AgentDeps:
    """External clients/repos the workflow nodes need. Not part of the graph's
    persisted state semantics - just carried alongside it for DI."""

    geocoder: GeoapifyClient
    router: OpenRouteServiceClient
    incident_repo: IncidentRepository
    explainer: Explainer


class AgentState(TypedDict, total=False):
    deps: AgentDeps
    request: RouteAnalysisRequest

    origin: Coordinate
    destination: Coordinate
    time_of_day: TimeOfDay

    candidates: list[RouteCandidate]
    incidents: list[IncidentReport]
    scored_routes: list[ScoredRoute]

    errors: list[str]
    # Free-form progress log used to drive SSE events; each node appends here.
    progress: list[dict[str, Any]]
