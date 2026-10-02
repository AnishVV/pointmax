"""Gateway candidates per ring: scored, capped, and deduped to their lowest ring.

Ring 1: airports with scheduled service within `radius_km` of any home airport.
Ring 2: domestic alliance hubs, plus airports that appeared as first connections in ring 0.
Ring 3: international gateways on the way (YYZ, YUL, MEX ...).
Alternate destinations near the arrival city are handled by `alternate_destinations`.

Score = + connection signal (cheap ring 0 itineraries that connect there) + alliances hubbed
there - distance from the nearest home airport. Stopover hubs are flagged, not scored.
"""

from dataclasses import dataclass, field

from pointmax.config import Settings
from pointmax.geo import airports as geo
from pointmax.geo.hubs import (
    DESTINATION_ALTERNATES,
    NORTH_AMERICA_GATEWAYS,
    STOPOVER_HUBS,
    US_ALLIANCE_HUBS,
    alliance_count,
    metro_siblings,
)
from pointmax.models import AwardOption


@dataclass(frozen=True)
class Candidate:
    iata: str
    ring: int
    score: float
    km_from_home: float
    stopover: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)


def connection_signal(options: list[AwardOption], costs: dict[int, float]) -> dict[str, float]:
    """Weight each first-connection airport by how cheap the ring 0 results through it were.

    `costs` maps id(option) -> effective cost; the cheapest result through any airport gets 1.0.
    """
    best = min(costs.values(), default=0.0)
    signal: dict[str, float] = {}
    for o in options:
        if o.stops < 1 or not o.segments:
            continue
        hub = o.segments[0].dest
        cost = costs.get(id(o))
        if not cost or cost <= 0:
            continue
        signal[hub] = signal.get(hub, 0.0) + best / cost
    return signal


def _min_km(iata: str, homes: list[str]) -> float:
    ap = geo.get(iata)
    return min(geo.haversine_km(geo.get(h), ap) for h in homes)


def _known(iata: str) -> bool:
    try:
        geo.get(iata)
    except KeyError:
        return False
    return True


def excluded_for(homes: list[str], dest: str) -> set[str]:
    out = set(homes) | {dest} | metro_siblings(dest)
    for h in homes:
        out |= metro_siblings(h)
    return out


def pick(
    ring: int,
    homes: list[str],
    dest: str,
    s: Settings,
    *,
    used: set[str],
    signal: dict[str, float] | None = None,
) -> list[Candidate]:
    """Candidates for one ring, best first, capped. Does not mutate `used`."""
    signal = signal or {}
    skip = excluded_for(homes, dest) | used
    pool: dict[str, str] = {}  # iata -> reason
    if ring == 1:
        for h in homes:
            for ap, _ in geo.nearby(h, s.radius_km):
                pool[ap.iata] = f"within {s.radius_km:.0f} km of {h}"
    elif ring == 2:
        for code in US_ALLIANCE_HUBS:
            pool[code] = "alliance hub"
        for code in signal:
            pool.setdefault(code, "connection in ring 0 results")
    elif ring == 3:
        for code in NORTH_AMERICA_GATEWAYS:
            pool[code] = "international gateway"
    else:
        raise ValueError("pick() handles rings 1-3")
    out = []
    for code, why in pool.items():
        if code in skip or not _known(code):
            continue
        km = _min_km(code, homes)
        size = 1.0 if geo.get(code).type == "large_airport" else 0.0
        score = signal.get(code, 0.0) * 3 + alliance_count(code) + size - km / 1000
        reasons = [why]
        if code in signal:
            reasons.append(f"ring 0 connection signal {signal[code]:.2f}")
        if alliance_count(code):
            reasons.append(f"{alliance_count(code)} alliance hub(s)")
        out.append(Candidate(code, ring, score, km, code in STOPOVER_HUBS, tuple(reasons)))
    out.sort(key=lambda c: (-c.score, c.km_from_home, c.iata))
    return out[: s.ring_caps.get(ring, 5)]


def alternate_destinations(dest: str, homes: list[str], used: set[str]) -> list[str]:
    return [
        a
        for a in DESTINATION_ALTERNATES.get(dest, ())
        if a not in used and a not in homes and a not in metro_siblings(dest) and _known(a)
    ]
