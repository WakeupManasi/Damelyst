from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.models.common import DimensionScore, ScoreBreakdown, ScoreDimension, TimeOfDay
from app.models.incident import IncidentReport, VerificationStatus
from app.models.route import RouteCandidate
from app.services.geometry import clamp, haversine_m, min_distance_to_route_m

# Default dimension weights. Must be non-negative; do not need to sum to exactly 1
# (they are renormalized), which makes client-supplied partial overrides safe.
DEFAULT_WEIGHTS: dict[ScoreDimension, float] = {
    ScoreDimension.LIGHTING: 0.18,
    ScoreDimension.ACTIVITY: 0.14,
    ScoreDimension.VISIBILITY: 0.14,
    ScoreDimension.MAIN_ROAD_QUALITY: 0.12,
    ScoreDimension.OVERSIGHT: 0.14,
    ScoreDimension.EMERGENCY_PROXIMITY: 0.10,
    ScoreDimension.INCIDENT_HISTORY: 0.18,
}

_INCIDENT_SEARCH_RADIUS_M = 60.0
_INCIDENT_HALF_LIFE_DAYS = 90.0
_VERIFICATION_WEIGHT = {
    VerificationStatus.OFFICIALLY_VERIFIED: 1.0,
    VerificationStatus.COMMUNITY_VERIFIED: 0.7,
    VerificationStatus.UNVERIFIED: 0.35,
    VerificationStatus.REJECTED: 0.0,
}

# Night hours dampen lighting/activity/oversight; day hours boost them.
_TIME_OF_DAY_MULTIPLIER: dict[TimeOfDay, float] = {
    TimeOfDay.DAY: 1.0,
    TimeOfDay.DAWN: 0.8,
    TimeOfDay.DUSK: 0.7,
    TimeOfDay.NIGHT: 0.45,
}


class InfrastructureSignalProvider(Protocol):
    """
    Pluggable source for lighting / activity / visibility / oversight /
    emergency-proximity signals. The default implementation below is a
    transparent heuristic over route geometry (main-road proportion, time of
    day). Swap this out for a real streetlight GIS layer, POI density API,
    CCTV registry, or emergency-services dataset without touching callers.
    """

    def main_road_quality(self, route: RouteCandidate) -> float: ...
    def lighting(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float: ...
    def activity(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float: ...
    def visibility(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float: ...
    def oversight(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float: ...
    def emergency_proximity(self, route: RouteCandidate) -> float: ...


class HeuristicInfrastructureSignalProvider:
    """Default, no-external-dependency implementation of InfrastructureSignalProvider."""

    def _main_road_fraction(self, route: RouteCandidate) -> float:
        total = sum(s.distance_m for s in route.segments) or route.distance_m or 1.0
        main = sum(s.distance_m for s in route.segments if s.is_main_road)
        return clamp(main / total, 0.0, 1.0)

    def main_road_quality(self, route: RouteCandidate) -> float:
        return clamp(self._main_road_fraction(route) * 100)

    def lighting(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float:
        base = 40 + 55 * self._main_road_fraction(route)
        return clamp(base * _TIME_OF_DAY_MULTIPLIER[time_of_day])

    def activity(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float:
        base = 35 + 55 * self._main_road_fraction(route)
        return clamp(base * _TIME_OF_DAY_MULTIPLIER[time_of_day])

    def visibility(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float:
        # Long unbroken minor-road stretches reduce visibility/sightlines more
        # than frequent turns/intersections on well-trafficked streets.
        fraction = self._main_road_fraction(route)
        segment_density = len(route.segments) / max(route.distance_m / 500, 1)
        base = 45 + 40 * fraction + min(15, segment_density * 3)
        return clamp(base * (0.7 + 0.3 * _TIME_OF_DAY_MULTIPLIER[time_of_day]))

    def oversight(self, route: RouteCandidate, time_of_day: TimeOfDay) -> float:
        # "Eyes on the street": approximated from main-road fraction (frontage,
        # passersby) modulated by time of day.
        base = 30 + 60 * self._main_road_fraction(route)
        return clamp(base * _TIME_OF_DAY_MULTIPLIER[time_of_day])

    def emergency_proximity(self, route: RouteCandidate) -> float:
        # Proxy: routes that stay closer to main roads are assumed more
        # reachable by emergency responders and closer to help (shops, transit).
        return clamp(55 + 45 * self._main_road_fraction(route))


def _incident_recency_weight(occurred_at: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86400)
    # Exponential decay with a configurable half-life.
    return 0.5 ** (age_days / _INCIDENT_HALF_LIFE_DAYS)


def score_incident_history(
    route: RouteCandidate,
    incidents: list[IncidentReport],
    now: datetime,
    search_radius_m: float = _INCIDENT_SEARCH_RADIUS_M,
) -> tuple[float, int]:
    """
    Returns (0-100 score, nearby_incident_count). Higher score = fewer / less
    severe / less recent / less verified incidents near the route corridor.
    """
    nearby = [i for i in incidents if min_distance_to_route_m(i.location, route) <= search_radius_m]
    if not nearby:
        return 100.0, 0

    penalty = 0.0
    for incident in nearby:
        verification_factor = _VERIFICATION_WEIGHT.get(incident.verification_status, 0.35)
        recency_factor = _incident_recency_weight(incident.occurred_at, now)
        penalty += 14.0 * verification_factor * recency_factor

    score = clamp(100.0 - penalty)
    return score, len(nearby)


def normalize_weights(
    overrides: dict[ScoreDimension, float] | None,
) -> dict[ScoreDimension, float]:
    weights = dict(DEFAULT_WEIGHTS)
    if overrides:
        for dim, value in overrides.items():
            if value < 0:
                continue
            weights[dim] = value
    total = sum(weights.values()) or 1.0
    return {dim: value / total for dim, value in weights.items()}


def score_route(
    route: RouteCandidate,
    time_of_day: TimeOfDay,
    incidents: list[IncidentReport],
    now: datetime,
    weight_overrides: dict[ScoreDimension, float] | None = None,
    signal_provider: InfrastructureSignalProvider | None = None,
) -> tuple[ScoreBreakdown, int]:
    provider = signal_provider or HeuristicInfrastructureSignalProvider()
    weights = normalize_weights(weight_overrides)

    incident_score, nearby_count = score_incident_history(route, incidents, now)

    raw_values: dict[ScoreDimension, tuple[float, str]] = {
        ScoreDimension.LIGHTING: (
            provider.lighting(route, time_of_day),
            f"Estimated from main-road coverage and {time_of_day.value} conditions.",
        ),
        ScoreDimension.ACTIVITY: (
            provider.activity(route, time_of_day),
            f"Expected pedestrian/foot traffic during {time_of_day.value}.",
        ),
        ScoreDimension.VISIBILITY: (
            provider.visibility(route, time_of_day),
            "Sightline estimate from road type and intersection frequency.",
        ),
        ScoreDimension.MAIN_ROAD_QUALITY: (
            provider.main_road_quality(route),
            "Share of route distance on classified main roads.",
        ),
        ScoreDimension.OVERSIGHT: (
            provider.oversight(route, time_of_day),
            "Approximate 'eyes on the street' from road frontage and time of day.",
        ),
        ScoreDimension.EMERGENCY_PROXIMITY: (
            provider.emergency_proximity(route),
            "Proxy for reachability by emergency responders / nearby help.",
        ),
        ScoreDimension.INCIDENT_HISTORY: (
            incident_score,
            f"{nearby_count} verified/unverified incident report(s) within "
            f"{int(_INCIDENT_SEARCH_RADIUS_M)}m of this route, recency- and "
            "verification-weighted.",
        ),
    }

    dimensions = [
        DimensionScore(dimension=dim, value=value, weight=weights[dim], rationale=rationale)
        for dim, (value, rationale) in raw_values.items()
    ]
    overall = sum(d.value * d.weight for d in dimensions)

    breakdown = ScoreBreakdown(
        overall=clamp(overall), dimensions=dimensions, time_of_day=time_of_day
    )
    return breakdown, nearby_count
