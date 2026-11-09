from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.common import Coordinate, ScoreDimension, TimeOfDay
from app.models.incident import IncidentReport, IncidentType, VerificationStatus
from app.models.route import RouteCandidate, RouteSegment
from app.services.scoring import normalize_weights, score_incident_history, score_route


def _make_route(main_road_fraction: float) -> RouteCandidate:
    geometry = [
        Coordinate(lon=0.0, lat=0.0),
        Coordinate(lon=0.0, lat=0.005),
        Coordinate(lon=0.0, lat=0.01),
    ]
    main_dist = 500 * main_road_fraction
    minor_dist = 500 * (1 - main_road_fraction)
    segments = [
        RouteSegment(
            start=geometry[0], end=geometry[1], distance_m=main_dist,
            street_name="Main Avenue", is_main_road=True,
        ),
        RouteSegment(
            start=geometry[1], end=geometry[2], distance_m=minor_dist,
            street_name="Quiet Lane", is_main_road=False,
        ),
    ]
    return RouteCandidate(
        route_id="test-route",
        geometry=geometry,
        segments=segments,
        distance_m=main_dist + minor_dist,
        duration_s=600,
    )


def test_main_road_route_scores_higher_at_night_than_minor_road_route():
    main_route = _make_route(main_road_fraction=1.0)
    minor_route = _make_route(main_road_fraction=0.0)
    now = datetime.now(timezone.utc)

    main_score, _ = score_route(main_route, TimeOfDay.NIGHT, incidents=[], now=now)
    minor_score, _ = score_route(minor_route, TimeOfDay.NIGHT, incidents=[], now=now)

    assert main_score.overall > minor_score.overall


def test_night_scores_lower_than_day_for_same_route():
    route = _make_route(main_road_fraction=0.5)
    now = datetime.now(timezone.utc)

    day_score, _ = score_route(route, TimeOfDay.DAY, incidents=[], now=now)
    night_score, _ = score_route(route, TimeOfDay.NIGHT, incidents=[], now=now)

    assert day_score.overall > night_score.overall


def test_nearby_incident_reduces_incident_history_score():
    route = _make_route(main_road_fraction=1.0)
    now = datetime.now(timezone.utc)

    incident = IncidentReport(
        location=Coordinate(lon=0.0001, lat=0.002),
        incident_type=IncidentType.HARASSMENT,
        description="Reported harassment near this stretch.",
        occurred_at=now - timedelta(days=1),
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
    )

    score_no_incidents, count_no = score_incident_history(route, [], now)
    score_with_incident, count_with = score_incident_history(route, [incident], now)

    assert count_no == 0
    assert count_with == 1
    assert score_with_incident < score_no_incidents


def test_old_incident_penalizes_less_than_recent_incident():
    route = _make_route(main_road_fraction=1.0)
    now = datetime.now(timezone.utc)
    location = Coordinate(lon=0.0001, lat=0.002)

    recent = IncidentReport(
        location=location, incident_type=IncidentType.THEFT, description="recent",
        occurred_at=now - timedelta(days=2),
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
    )
    old = IncidentReport(
        location=location, incident_type=IncidentType.THEFT, description="old",
        occurred_at=now - timedelta(days=400),
        verification_status=VerificationStatus.OFFICIALLY_VERIFIED,
    )

    recent_score, _ = score_incident_history(route, [recent], now)
    old_score, _ = score_incident_history(route, [old], now)

    assert old_score > recent_score


def test_normalize_weights_sums_to_one():
    weights = normalize_weights(None)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_normalize_weights_respects_overrides():
    weights = normalize_weights({ScoreDimension.LIGHTING: 10.0})
    assert weights[ScoreDimension.LIGHTING] > 0.5
