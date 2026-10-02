"""Local, free filters and sorting over cached results."""

from collections.abc import Callable
from dataclasses import dataclass

from pointmax.models import AwardOption, Cabin, Itinerary


@dataclass
class Filters:
    cabin: Cabin | None = None
    min_premium: int = 60
    max_stops: int | None = None
    max_hours: float | None = None
    max_taxes: float | None = None
    no_redeye: bool = False
    no_overnight: bool = False
    no_self_transfer: bool = False
    pax: int = 1


def cabin_ok(opt: AwardOption, want: Cabin, min_premium: int) -> bool:
    """Headline cabin >= wanted, and either every segment is, or premium_pct >= threshold.

    premium_pct is 0 on single-cabin itineraries, so the all-segments test is required.
    """
    if opt.headline_cabin < want:
        return False

    def seg_ok(c: str) -> bool:
        try:
            return Cabin.parse(c) >= want
        except ValueError:
            return False

    all_seg = bool(opt.segments) and all(seg_ok(s.cabin or opt.cabin) for s in opt.segments)
    return all_seg or opt.premium_pct >= min_premium


def option_ok(opt: AwardOption, f: Filters) -> bool:
    if f.cabin is not None and not cabin_ok(opt, f.cabin, f.min_premium):
        return False
    if opt.seats is not None and opt.seats < f.pax:
        return False
    if f.max_stops is not None and opt.stops > f.max_stops:
        return False
    if f.max_hours is not None and opt.duration_min / 60 > f.max_hours:
        return False
    if f.max_taxes is not None and opt.taxes_usd > f.max_taxes:
        return False
    return not (
        (f.no_redeye and "redeye" in opt.flags)
        or (f.no_overnight and "overnight" in opt.flags)
        or (f.no_self_transfer and "self_transfer" in opt.flags)
    )


def itinerary_ok(it: Itinerary, f: Filters) -> bool:
    return all(option_ok(o, f) for o in it.award_legs)


SORTS: dict[str, Callable[[Itinerary], tuple]] = {
    "eff": lambda i: (i.value.c_eff, _hours(i), i.main.stops),
    "cpp": lambda i: (-_main_cpp(i), i.value.c_eff),
    "miles": lambda i: (sum(o.miles for o in i.award_legs), i.value.c_eff),
    "duration": lambda i: (_hours(i), i.value.c_eff),
    "taxes": lambda i: (sum(o.taxes_usd for o in i.award_legs), i.value.c_eff),
}


def _main_cpp(it: Itinerary) -> float:
    if it.value is None:
        return 0.0
    for lv, role in zip(it.value.legs, it.roles, strict=True):
        if role == "main":
            return lv.redemption_cpp or 0.0
    return 0.0


def _hours(it: Itinerary) -> float:
    return sum(o.duration_min for o in it.award_legs) / 60


def sort_itineraries(its: list[Itinerary], key: str = "eff") -> list[Itinerary]:
    if key not in SORTS:
        raise ValueError(f"unknown sort {key!r}; choose from {sorted(SORTS)}")
    return sorted((i for i in its if i.value), key=SORTS[key])
