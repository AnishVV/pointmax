"""Bundled OurAirports data, haversine distance and radius search.

`data/airports.csv` is a public-domain OurAirports extract (large and medium airports
with an IATA code). Regenerate it with `scripts/update_airports.py`.
"""

import csv
import math
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True, slots=True)
class Airport:
    iata: str
    name: str
    type: str  # large_airport | medium_airport
    lat: float
    lon: float
    country: str
    region: str
    city: str
    scheduled_service: bool


@cache
def load_airports() -> dict[str, Airport]:
    """IATA code -> Airport. Where a code repeats, the larger airport wins."""
    rank = {"large_airport": 0, "medium_airport": 1}
    out: dict[str, Airport] = {}
    text = files("pointmax.data").joinpath("airports.csv").read_text(encoding="utf-8")
    for row in csv.DictReader(text.splitlines()):
        ap = Airport(
            iata=row["iata_code"],
            name=row["name"],
            type=row["type"],
            lat=float(row["latitude_deg"]),
            lon=float(row["longitude_deg"]),
            country=row["iso_country"],
            region=row["iso_region"],
            city=row["municipality"],
            scheduled_service=row["scheduled_service"] == "yes",
        )
        prev = out.get(ap.iata)
        if prev is None or (
            (rank[ap.type], not ap.scheduled_service)
            < (rank[prev.type], not prev.scheduled_service)
        ):
            out[ap.iata] = ap
    return out


def get(iata: str) -> Airport:
    try:
        return load_airports()[iata.upper()]
    except KeyError:
        raise KeyError(f"Unknown airport {iata!r}") from None


def haversine_km(a: Airport, b: Airport) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def nearby(iata: str, km: float, *, scheduled_only: bool = True) -> list[tuple[Airport, float]]:
    """Airports within `km` of `iata` (excluding itself), nearest first."""
    origin = get(iata)
    hits = []
    for ap in load_airports().values():
        if ap.iata == origin.iata or (scheduled_only and not ap.scheduled_service):
            continue
        d = haversine_km(origin, ap)
        if d <= km:
            hits.append((ap, d))
    return sorted(hits, key=lambda t: t[1])
