"""Small geospatial helpers used by the dependency-free MVP."""

from __future__ import annotations

from decimal import Decimal
from math import cos, pi
from typing import Any

HECTARES_PER_SQUARE_KM = Decimal("100")
KM_PER_DEGREE_LAT = Decimal("111.32")


def polygon_area_hectares(geojson: dict[str, Any]) -> Decimal:
    """Approximate GeoJSON polygon/multipolygon area in hectares.

    The production system should use PostGIS or a certified geodetic library. This
    deterministic implementation supports tests and local demos without external
    dependencies.
    """

    geometry_type = geojson.get("type")
    coordinates = geojson.get("coordinates", [])
    if geometry_type == "Polygon":
        return _polygon_coordinates_area(coordinates)
    if geometry_type == "MultiPolygon":
        return sum((_polygon_coordinates_area(polygon) for polygon in coordinates), Decimal("0"))
    raise ValueError("geometry_geojson must be a Polygon or MultiPolygon")


def centroid(geojson: dict[str, Any]) -> tuple[Decimal, Decimal]:
    """Return a simple centroid as latitude/longitude for route and crisis checks."""

    points = list(_iter_lon_lat_points(geojson))
    if not points:
        raise ValueError("geometry_geojson must contain coordinates")
    lon_sum = sum((point[0] for point in points), Decimal("0"))
    lat_sum = sum((point[1] for point in points), Decimal("0"))
    count = Decimal(len(points))
    return lat_sum / count, lon_sum / count


def point_in_bbox(lat: Decimal, lon: Decimal, min_lat: Decimal, min_lon: Decimal, max_lat: Decimal, max_lon: Decimal) -> bool:
    """Return whether a point is inside a crisis event bounding box."""

    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _polygon_coordinates_area(coordinates: list[Any]) -> Decimal:
    if not coordinates:
        return Decimal("0")
    outer = _ring_area_square_km(coordinates[0])
    holes = sum((_ring_area_square_km(ring) for ring in coordinates[1:]), Decimal("0"))
    return abs(outer - holes) * HECTARES_PER_SQUARE_KM


def _ring_area_square_km(ring: list[Any]) -> Decimal:
    if len(ring) < 4:
        return Decimal("0")
    average_lat = sum((Decimal(str(point[1])) for point in ring), Decimal("0")) / Decimal(len(ring))
    km_per_degree_lon = KM_PER_DEGREE_LAT * Decimal(str(cos(float(average_lat) * pi / 180)))
    projected = [
        (Decimal(str(point[0])) * km_per_degree_lon, Decimal(str(point[1])) * KM_PER_DEGREE_LAT)
        for point in ring
    ]
    twice_area = Decimal("0")
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        twice_area += x1 * y2 - x2 * y1
    return abs(twice_area) / Decimal("2")


def _iter_lon_lat_points(geojson: dict[str, Any]):
    geometry_type = geojson.get("type")
    coordinates = geojson.get("coordinates", [])
    if geometry_type == "Polygon":
        for ring in coordinates:
            for lon, lat in ring:
                yield Decimal(str(lon)), Decimal(str(lat))
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for lon, lat in ring:
                    yield Decimal(str(lon)), Decimal(str(lat))
    else:
        raise ValueError("geometry_geojson must be a Polygon or MultiPolygon")
