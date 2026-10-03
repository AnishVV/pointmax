"""Source-agnostic domain models. Nothing downstream of normalize.py knows PointsYeah exists."""

from datetime import date, datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field


class Cabin(IntEnum):
    ECONOMY = 1
    PREMIUM = 2
    BUSINESS = 3
    FIRST = 4

    @classmethod
    def parse(cls, text: str) -> "Cabin":
        t = text.strip().lower().replace("_", " ").replace("-", " ")
        if "premium" in t:
            return cls.PREMIUM
        if t.startswith("first") or t == "f":
            return cls.FIRST
        if t.startswith(("business", "biz", "j")):
            return cls.BUSINESS
        if t.startswith(("econ", "coach", "main", "basic", "blue", "y")):
            return cls.ECONOMY
        raise ValueError(f"Unknown cabin {text!r}")


class TransferPath(BaseModel):
    bank: str
    points: int  # bank points needed; actual_points when a bonus applies
    bonus_pct: int = 0
    bonus_ends: date | None = None


class FlightSegment(BaseModel):
    flight_no: str
    carrier: str
    origin: str
    dest: str
    dep: datetime  # local time at origin
    arr: datetime  # local time at destination
    cabin: str = ""
    aircraft: str = ""
    layover_min: int = 0


class AwardOption(BaseModel):
    source: str = "pointsyeah"
    program: str
    program_code: str = ""
    origin: str
    dest: str
    date: date
    cabin: str  # headline cabin
    miles: int
    taxes_usd: float = 0.0
    cash_price_usd: float | None = None
    seats: int | None = None  # None = unknown ("not live inventory")
    segments: list[FlightSegment] = Field(default_factory=list)
    duration_min: int = 0
    stops: int = 0
    premium_pct: float = 0.0
    booking_url: str = ""
    transfers: list[TransferPath] = Field(default_factory=list)
    buy_promo: str | None = None
    flags: set[str] = Field(default_factory=set)
    fetched_at: datetime | None = None

    @property
    def headline_cabin(self) -> Cabin:
        return Cabin.parse(self.cabin)

    @property
    def dep(self) -> datetime | None:
        return self.segments[0].dep if self.segments else None

    @property
    def arr(self) -> datetime | None:
        return self.segments[-1].arr if self.segments else None

    @property
    def flight_numbers(self) -> tuple[str, ...]:
        return tuple(s.flight_no for s in self.segments)


class CashLeg(BaseModel):
    """A positioning leg with no award, or an estimate. Estimates are never hidden."""

    origin: str
    dest: str
    date: date
    price_usd: float
    estimated: bool = True
    mode: Literal["flight", "drive"] = "flight"
    dep: datetime | None = None
    arr: datetime | None = None


Role = Literal["position_out", "main", "position_in"]


class LegValue(BaseModel):
    description: str
    funding: str  # e.g. "Chase Ultimate Rewards +20% bonus" or "cash"
    points_usd: float = 0.0
    taxes_usd: float = 0.0
    cash_usd: float = 0.0
    redemption_cpp: float | None = None
    redemption_label: str | None = None  # great | good | poor

    @property
    def total_usd(self) -> float:
        return self.points_usd + self.taxes_usd + self.cash_usd


class ValueBreakdown(BaseModel):
    c_eff: float
    legs: list[LegValue] = Field(default_factory=list)
    hotel_usd: float = 0.0
    savings_usd: float | None = None
    savings_pct: float | None = None
    extra_hours: float | None = None
    notes: list[str] = Field(default_factory=list)


class Itinerary(BaseModel):
    legs: list[AwardOption | CashLeg]  # in travel order
    roles: list[Role]
    gateway: str | None = None
    ring: int = 0
    hotel_nights: int = 0  # overnight in the gateway city; priced by the hotel allowance
    notes: list[str] = Field(default_factory=list)
    value: ValueBreakdown | None = None

    @property
    def main(self) -> AwardOption:
        for leg, role in zip(self.legs, self.roles, strict=True):
            if role == "main" and isinstance(leg, AwardOption):
                return leg
        raise ValueError("itinerary has no main award leg")

    @property
    def award_legs(self) -> list[AwardOption]:
        return [leg for leg in self.legs if isinstance(leg, AwardOption)]
