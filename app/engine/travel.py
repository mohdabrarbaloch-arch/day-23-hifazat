"""Great-circle distance between two coordinates (haversine)."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in kilometres between two points on a sphere."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def lookup_city(
    city: str, country: str, cities: dict[tuple[str, str], tuple[float, float]]
) -> tuple[float, float] | None:
    """Resolve coordinates for a city.

    Exact (city, country) first. If the country is missing — a very common
    case for card feeds that only report a merchant location — fall back to a
    unique city-name match. If the name is ambiguous across countries we
    return None rather than guess, because a wrong guess would produce a false
    "impossible travel" accusation.
    """
    if not city:
        return None
    if country:
        hit = cities.get((city, country))
        if hit is not None:
            return hit

    matches = [coord for (name, _country), coord in cities.items() if name == city]
    if len(matches) == 1:
        return matches[0]
    return None


def is_rapid_geo_change(
    city_a: str,
    country_a: str,
    city_b: str,
    country_b: str,
    hours_between: float,
    cities: dict[str, tuple[float, float]],
    *,
    min_km: float = 400.0,
    max_hours: float = 24.0,
) -> bool:
    """True when two *different* cities >= min_km apart occur within max_hours.

    Same city (or either side unknown) can never be a geo violation.
    """
    if not city_a or not city_b or (city_a == city_b and country_a == country_b):
        return False
    if hours_between < 0 or hours_between > max_hours:
        return False

    coord_a = lookup_city(city_a, country_a, cities)
    coord_b = lookup_city(city_b, country_b, cities)
    if coord_a is None or coord_b is None:
        # We cannot prove the distance, so we do not accuse.
        return False

    return haversine_km(*coord_a, *coord_b) >= min_km
