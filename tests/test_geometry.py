from __future__ import annotations

from app.models.common import Coordinate
from app.models.route import RouteCandidate, RouteSegment
from app.services.geometry import (
    haversine_m,
    min_distance_to_route_m,
    point_to_segment_distance_m,
    route_length_m,
)


def test_haversine_same_point_is_zero():
    p = Coordinate(lon=-0.1276, lat=51.5074)
    assert haversine_m(p, p) == 0.0


def test_haversine_known_distance_london_paris():
    london = Coordinate(lon=-0.1276, lat=51.5074)
    paris = Coordinate(lon=2.3522, lat=48.8566)
    distance_km = haversine_m(london, paris) / 1000
    # Known great-circle distance is ~344km; allow generous tolerance.
    assert 330 <= distance_km <= 360


def test_point_to_segment_distance_on_segment_is_zero():
    a = Coordinate(lon=0.0, lat=0.0)
    b = Coordinate(lon=0.0, lat=0.01)
    midpoint = Coordinate(lon=0.0, lat=0.005)
    assert point_to_segment_distance_m(midpoint, a, b) < 1.0


def test_point_to_segment_distance_off_segment_is_positive():
    a = Coordinate(lon=0.0, lat=0.0)
    b = Coordinate(lon=0.0, lat=0.01)
    off_point = Coordinate(lon=0.01, lat=0.005)
    assert point_to_segment_distance_m(off_point, a, b) > 500


def test_min_distance_to_route_picks_closest_segment():
    geometry = [
        Coordinate(lon=0.0, lat=0.0),
        Coordinate(lon=0.0, lat=0.01),
        Coordinate(lon=0.01, lat=0.01),
    ]
    route = RouteCandidate(
        route_id="r1",
        geometry=geometry,
        segments=[
            RouteSegment(start=geometry[0], end=geometry[1], distance_m=1000),
            RouteSegment(start=geometry[1], end=geometry[2], distance_m=1000),
        ],
        distance_m=2000,
        duration_s=1500,
    )
    near_second_segment = Coordinate(lon=0.005, lat=0.0101)
    assert min_distance_to_route_m(near_second_segment, route) < 200


def test_route_length_sums_segment_distances():
    geometry = [
        Coordinate(lon=0.0, lat=0.0),
        Coordinate(lon=0.0, lat=0.01),
        Coordinate(lon=0.01, lat=0.01),
    ]
    length = route_length_m(geometry)
    assert length > 0
