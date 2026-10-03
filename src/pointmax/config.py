"""Paths and user settings (~/.config/pointmax/config.toml).

Cents-per-point defaults come from the reference valuation doc (Sept. 2026 snapshot). Buffers,
distance bands and the hotel allowance are still best-knowledge placeholders to review.
"""

import copy
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def config_dir() -> Path:
    """`$POINTMAX_HOME`, else `$XDG_CONFIG_HOME/pointmax`, else `~/.config/pointmax`."""
    if home := os.environ.get("POINTMAX_HOME"):
        return Path(home)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "pointmax"


def session_path() -> Path:
    return config_dir() / "session.json"


def chrome_profile_dir() -> Path:
    return config_dir() / "chrome-profile"


def config_path() -> Path:
    return config_dir() / "config.toml"


def cache_path() -> Path:
    return config_dir() / "cache.sqlite"


def last_search_path() -> Path:
    return config_dir() / "last_search.json"


DEFAULT_HOME_AIRPORTS = ("AUS", "DFW")

DEFAULT_TOML = """\
# pointmax settings. Values shown are defaults; delete a line to fall back to it.

# Airports you can start from. All are searched directly (ring 0).
home = ["AUS", "DFW"]
cache_ttl_hours = 6
dominance_pct = 10        # a self-built itinerary must beat a single ticket by this much

# Cents per point/mile. Baselines from the reference doc point-valuations-and-transfer-partners.md
# (snapshot Sept. 2026; it says to re-pull monthly). Set your own valuations if they differ.
[cpp]
# Bank currencies (names as PointsYeah reports them)
"Chase Ultimate Rewards" = 2.05
"American Exp Membership Rewards" = 2.0
"Citi ThankYou" = 1.9
"Capital One" = 1.85
"Bilt" = 2.2
"WF" = 1.6                # not in the reference doc: unverified
"US Bank" = 1.5           # not in the reference doc: unverified
# Airline programs (names as PointsYeah reports them), valued for your own miles
"Alaska Atmos Rewards" = 1.55
"Avianca LifeMiles" = 1.55
"Air Canada Aeroplan" = 1.5
"American Airlines AAdvantage" = 1.45
"Virgin Atlantic Flying Club" = 1.45
"JetBlue True Blue" = 1.35
"Air France/KLM Flying Blue" = 1.4
"United MileagePlus" = 1.2
"Delta SkyMiles" = 1.2
"Qantas Frequent Flyer" = 1.2
"Turkish Miles & Smiles" = 1.1
"default" = 1.2           # any program not listed above

# Program miles you already hold. A program's own miles only count as a funding path if listed.
[balances]

# Prefer these banks as a small tiebreak. Never hides other options.
[prefer]
banks = []
tiebreak_pct = 2

[buffers]
same_airport_hours = 3
metro_change_hours = 4
max_early_arrival_hours = 24
hotel_allowance_usd = 150

[rings]
radius_km = 400
cap_ring1 = 5
cap_ring2 = 6
cap_ring3 = 6
default_rings = 2
budget_min = 15
ring_dates = 2

# Cash positioning estimates when PointsYeah returns nothing: [max_km, usd]
[distance_bands]
bands = [[200, 90], [450, 130], [900, 180], [1800, 260], [20000, 380]]
drive_usd_per_km = 0.42   # IRS-style mileage, for ring 1 drives
"""


@dataclass
class Settings:
    home: list[str] = field(default_factory=lambda: list(DEFAULT_HOME_AIRPORTS))
    cache_ttl_hours: float = 6.0
    dominance_pct: float = 10.0
    cpp: dict[str, float] = field(default_factory=dict)
    balances: dict[str, int] = field(default_factory=dict)
    prefer_banks: list[str] = field(default_factory=list)
    prefer_tiebreak_pct: float = 2.0
    same_airport_hours: float = 3.0
    metro_change_hours: float = 4.0
    max_early_arrival_hours: float = 24.0
    hotel_allowance_usd: float = 150.0
    radius_km: float = 400.0
    ring_caps: dict[int, int] = field(default_factory=lambda: {1: 5, 2: 6, 3: 6})
    default_rings: int = 2
    budget_min: float = 15.0
    ring_dates: int = 2
    distance_bands: list[tuple[float, float]] = field(default_factory=list)
    drive_usd_per_km: float = 0.42

    def cpp_for(self, currency: str) -> float:
        """Cents per point for a bank currency or program (case-insensitive, then default)."""
        lower = {k.lower(): v for k, v in self.cpp.items()}
        return lower.get(currency.lower(), lower.get("default", 1.2))

    def has_cpp(self, currency: str) -> bool:
        return currency.lower() in {k.lower() for k in self.cpp if k != "default"}

    def cash_estimate(self, km: float) -> float:
        for max_km, usd in self.distance_bands:
            if km <= max_km:
                return usd
        return self.distance_bands[-1][1] if self.distance_bands else 400.0


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def from_dict(d: dict[str, Any]) -> Settings:
    rings, buf, prefer = d.get("rings", {}), d.get("buffers", {}), d.get("prefer", {})
    return Settings(
        home=[str(a).upper() for a in d["home"]],
        cache_ttl_hours=float(d["cache_ttl_hours"]),
        dominance_pct=float(d["dominance_pct"]),
        cpp={str(k): float(v) for k, v in d.get("cpp", {}).items()},
        balances={str(k): int(v) for k, v in d.get("balances", {}).items()},
        prefer_banks=list(prefer.get("banks", [])),
        prefer_tiebreak_pct=float(prefer.get("tiebreak_pct", 2)),
        same_airport_hours=float(buf["same_airport_hours"]),
        metro_change_hours=float(buf["metro_change_hours"]),
        max_early_arrival_hours=float(buf["max_early_arrival_hours"]),
        hotel_allowance_usd=float(buf["hotel_allowance_usd"]),
        radius_km=float(rings["radius_km"]),
        ring_caps={
            1: int(rings["cap_ring1"]),
            2: int(rings["cap_ring2"]),
            3: int(rings["cap_ring3"]),
        },
        default_rings=int(rings["default_rings"]),
        budget_min=float(rings["budget_min"]),
        ring_dates=int(rings["ring_dates"]),
        distance_bands=[(float(a), float(b)) for a, b in d["distance_bands"]["bands"]],
        drive_usd_per_km=float(d["distance_bands"]["drive_usd_per_km"]),
    )


def load_settings(path: Path | None = None) -> Settings:
    base = tomllib.loads(DEFAULT_TOML)
    path = path or config_path()
    if path.exists():
        base = _merge(base, tomllib.loads(path.read_text()))
    return from_dict(base)


def write_default(path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_TOML)
    return path
