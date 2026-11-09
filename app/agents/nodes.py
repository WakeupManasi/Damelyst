from __future__ import annotations

from datetime import datetime, timezone

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.models.common import ScoreDimension, TimeOfDay
from app.models.route import ScoredRoute
from app.services.scoring import score_route

logger = get_logger(__name__)


def _log_progress(state: AgentState, stage: str, message: str, **extra: object) -> dict:
    entry = {"stage": stage, "message": message, **extra}
    progress = list(state.get("progress", []))
    progress.append(entry)
    return {"progress": progress}


async def resolve_endpoints(state: AgentState) -> dict:
    """Geocode free-text origin/destination if raw coordinates weren't supplied."""
    request = state["request"]
    deps = state["deps"]

    origin = request.origin
    if origin is None:
        assert request.origin_text is not None
        origin = await deps.geocoder.geocode(request.origin_text)

    destination = request.destination
    if destination is None:
        assert request.destination_text is not None
        destination = await deps.geocoder.geocode(request.destination_text)

    departure = request.effective_departure_time
    time_of_day = TimeOfDay.from_hour(departure.astimezone(timezone.utc).hour)

    progress = _log_progress(
        state,
        "resolve_endpoints",
        f"Resolved endpoints for {time_of_day.value} travel.",
        origin=origin.model_dump(),
        destination=destination.model_dump(),
    )
    return {"origin": origin, "destination": destination, "time_of_day": time_of_day, **progress}


async def fetch_route_candidates(state: AgentState) -> dict:
    """Fetch candidate walking routes from OpenRouteService."""
    deps = state["deps"]
    request = state["request"]
    candidates = await deps.router.get_walking_routes(
        state["origin"], state["destination"], alternatives=request.max_alternatives
    )
    progress = _log_progress(
        state,
        "fetch_route_candidates",
        f"Retrieved {len(candidates)} candidate walking route(s).",
        count=len(candidates),
    )
    return {"candidates": candidates, **progress}


async def fetch_relevant_incidents(state: AgentState) -> dict:
    """Load verified/unverified incident reports that could affect any candidate route."""
    deps = state["deps"]
    incidents = await deps.incident_repo.list_all()
    progress = _log_progress(
        state,
        "fetch_relevant_incidents",
        f"Loaded {len(incidents)} incident report(s) from the repository.",
        count=len(incidents),
    )
    return {"incidents": incidents, **progress}


async def score_candidates(state: AgentState) -> dict:
    """Compute the multi-dimensional score for every candidate route."""
    request = state["request"]
    now = datetime.now(timezone.utc)

    weight_overrides = None
    if request.dimension_weights:
        weight_overrides = {}
        for key, value in request.dimension_weights.items():
            try:
                weight_overrides[ScoreDimension(key)] = value
            except ValueError:
                logger.warning("Ignoring unknown score dimension override: %s", key)

    scored: list[ScoredRoute] = []
    for candidate in state["candidates"]:
        breakdown, nearby_count = score_route(
            route=candidate,
            time_of_day=state["time_of_day"],
            incidents=state["incidents"],
            now=now,
            weight_overrides=weight_overrides,
        )
        scored.append(
            ScoredRoute(candidate=candidate, score=breakdown, incident_count_nearby=nearby_count)
        )

    scored.sort(key=lambda r: r.score.overall, reverse=True)
    progress = _log_progress(
        state,
        "score_candidates",
        f"Scored {len(scored)} route(s).",
        scores=[round(r.score.overall, 1) for r in scored],
    )
    return {"scored_routes": scored, **progress}


async def generate_explanations(state: AgentState) -> dict:
    """Ask the LLM (or deterministic fallback) to explain each route's score."""
    deps = state["deps"]
    scored_routes = state["scored_routes"]

    explained: list[ScoredRoute] = []
    for idx, scored in enumerate(scored_routes, start=1):
        label = f"Route {idx} ({scored.candidate.distance_m:.0f}m, {scored.candidate.duration_s / 60:.0f} min)"
        try:
            explanation = await deps.explainer.explain(
                label, scored.score, scored.incident_count_nearby
            )
        except Exception:  # noqa: BLE001 - explanation failures shouldn't kill the request
            logger.exception("Explanation generation failed for %s", scored.candidate.route_id)
            explanation = (
                f"{label} scores {scored.score.overall:.0f}/100. "
                "A detailed narrative explanation is temporarily unavailable."
            )
        explained.append(scored.model_copy(update={"explanation": explanation}))

    progress = _log_progress(
        state, "generate_explanations", f"Generated explanations for {len(explained)} route(s)."
    )
    return {"scored_routes": explained, **progress}
