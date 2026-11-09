from __future__ import annotations

import math

from app.models.common import Coordinate
from app.models.route import RouteCandidate

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance in meters between two lon/lat points."""
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def point_to_segment_distance_m(p: Coordinate, a: Coordinate, b: Coordinate) -> float:
    """
    Approximate min distance from point p to segment a-b, in meters.
    Uses an equirectangular projection local to the segment, which is accurate
    enough at pedestrian-route scale (tens of meters to a few km).
    """
    lat0 = math.radians((a.lat + b.lat) / 2)
    cos_lat0 = math.cos(lat0)

    def to_xy(c: Coordinate) -> tuple[float, float]:
        x = math.radians(c.lon) * cos_lat0 * EARTH_RADIUS_M
        y = math.radians(c.lat) * EARTH_RADIUS_M
        return x, y

    px, py = to_xy(p)
    ax, ay = to_xy(a)
    bx, by = to_xy(b)

    abx, aby = bx - ax, by - ay
    seg_len_sq = abx**2 + aby**2
    if seg_len_sq == 0:
        return math.hypot(px - ax, py - ay)

    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / seg_len_sq))
    closest_x = ax + t * abx
    closest_y = ay + t * aby
    return math.hypot(px - closest_x, py - closest_y)


def min_distance_to_route_m(point: Coordinate, route: RouteCandidate) -> float:
    """Minimum distance from a point to any segment of a route's geometry."""
    geometry = route.geometry
    if len(geometry) < 2:
        return haversine_m(point, geometry[0]) if geometry else math.inf
    return min(
        point_to_segment_distance_m(point, geometry[i], geometry[i + 1])
        for i in range(len(geometry) - 1)
    )


def route_length_m(geometry: list[Coordinate]) -> float:
    if len(geometry) < 2:
        return 0.0
    return sum(haversine_m(geometry[i], geometry[i + 1]) for i in range(len(geometry) - 1))


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
