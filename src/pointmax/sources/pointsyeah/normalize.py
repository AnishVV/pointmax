"""Raw PointsYeah route -> AwardOption, with the plan's flags.

Flags: redeye (a segment leaves 21:00-03:59 local and lands the next day before 10:00),
overnight (a layover covers 01:00-05:00 local), low_seats (<= 4), bonus (any transfer bonus),
self_transfer (a segment starts at a different airport than the previous one ended).
Non-USD currencies are converted with RATES_TO_USD and flagged, never treated as dollars.
"""

from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Any

from pointmax.models import AwardOption, FlightSegment, TransferPath
from pointmax.sources.pointsyeah.raw import RawRoute, SchemaWarnings, parse_route

# Placeholder FX table; move into config when a non-USD currency is actually seen.
RATES_TO_USD: dict[str, float] = {"USD": 1.0}
NOT_LIVE_SEATS = 9999


def parse_seats(value: int | str | None) -> int | None:
    """Seats arrive as an int or a numeric string; 9999 means the count is not live."""
    try:
        n = int(value) if value is not None else None
    except ValueError:
        return None
    return None if n is None or n == NOT_LIVE_SEATS or n < 0 else n


def epoch_date(value: float | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value, UTC).date()
    except (OverflowError, OSError, ValueError):
        return None


def parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    t = text.strip().replace(" ", "T").rstrip("Z")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt.replace(tzinfo=None)  # local wall-clock time, as PointsYeah reports it


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


def _in_window(t: time, start: time, end: time) -> bool:
    return start <= t <= end if start <= end else t >= start or t <= end


def is_redeye(seg: FlightSegment) -> bool:
    return (
        _in_window(seg.dep.time(), time(21, 0), time(3, 59))
        and seg.arr.date() > seg.dep.date()
        and seg.arr.time() < time(10, 0)
    )


def has_overnight_layover(segs: list[FlightSegment]) -> bool:
    """A layover overlapping 01:00-05:00 local on any night."""
    for prev, nxt in pairwise(segs):
        day = prev.arr.date()
        while day <= nxt.dep.date():
            start = datetime.combine(day, time(1, 0))
            end = datetime.combine(day, time(5, 0))
            if prev.arr < end and nxt.dep > start:
                return True
            day += timedelta(days=1)
    return False


def is_self_transfer(segs: list[FlightSegment]) -> bool:
    return any(a.dest != b.origin for a, b in pairwise(segs))


def normalize_route(
    raw: RawRoute, warnings: SchemaWarnings, fetched_at: datetime | None = None
) -> AwardOption | None:
    pay = raw.payment
    assert pay is not None  # guaranteed by core_missing()
    segments: list[FlightSegment] = []
    for s in raw.segments:
        dep, arr = parse_dt(s.dt), parse_dt(s.at)
        if dep is None or arr is None or not s.da or not s.aa:
            warnings.warn("segment missing times or airports; route skipped")
            return None
        segments.append(
            FlightSegment(
                flight_no=(s.flight_number or "").replace(" ", ""),
                carrier=(s.flight_number or "")[:2],
                origin=s.da,
                dest=s.aa,
                dep=dep,
                arr=arr,
                cabin=s.cabin or pay.cabin or "",
                aircraft=(s.aircraft or "").strip(),
                layover_min=round(s.layover or 0),
            )
        )
    flags: set[str] = set()
    if any(is_redeye(s) for s in segments):
        flags.add("redeye")
    if has_overnight_layover(segments):
        flags.add("overnight")
    if is_self_transfer(segments):
        flags.add("self_transfer")

    seats = parse_seats(pay.seats)
    if seats is not None and seats <= 4:
        flags.add("low_seats")

    transfers = []
    for tr in raw.transfer:
        pts = round(tr.actual_points or tr.points or 0)
        if not tr.bank or not pts:
            continue
        pct = round(tr.bonus_percentage or 0)
        if pct > 0:
            flags.add("bonus")
        transfers.append(
            TransferPath(
                bank=tr.bank, points=pts, bonus_pct=pct, bonus_ends=epoch_date(tr.bonus_end_date)
            )
        )

    currency = (pay.currency or "USD").upper()
    rate = RATES_TO_USD.get(currency)
    if rate is None:
        warnings.warn(f"unsupported currency {currency!r}; taxes treated as USD and flagged")
        flags.add("currency_unconverted")
        rate = 1.0
    elif currency != "USD":
        flags.add("currency_converted")
    cash = pay.cash_price * rate if pay.cash_price else None

    if not raw.duration:
        # local times at both ends differ by time zone, so this is only a rough lower bound
        flags.add("duration_estimated")
    day = parse_date(raw.date) or segments[0].dep.date()
    return AwardOption(
        program=raw.program or "",
        program_code=raw.code or "",
        origin=segments[0].origin,
        dest=segments[-1].dest,
        date=day,
        cabin=pay.cabin or segments[0].cabin,
        miles=pay.miles or 0,
        taxes_usd=round((pay.tax or 0.0) * rate, 2),
        cash_price_usd=cash,
        seats=seats,
        segments=segments,
        duration_min=round(raw.duration)
        if raw.duration
        else int((segments[-1].arr - segments[0].dep).total_seconds() // 60),
        stops=len(segments) - 1,
        premium_pct=raw.premium_cabin_percentage or 0.0,
        booking_url=raw.url or "",
        transfers=transfers,
        buy_promo=(raw.promotion.description or None) if raw.promotion else None,
        flags=flags,
        fetched_at=fetched_at or datetime.now(UTC).replace(tzinfo=None),
    )


def normalize_routes(
    routes: list[dict[str, Any]], warnings: SchemaWarnings | None = None
) -> list[AwardOption]:
    warnings = warnings or SchemaWarnings()
    out = []
    for data in routes:
        raw = parse_route(data, warnings)
        if raw and (opt := normalize_route(raw, warnings)):
            out.append(opt)
    return out
