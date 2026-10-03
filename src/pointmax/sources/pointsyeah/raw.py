"""Pydantic models of the raw PointsYeah JSON, verified against recorded fixtures (2026-10).

Shapes (see tests/fixtures): a fetch_result item is one summary per program-date with `routes`;
a route has no date, origin or destination of its own, so `item_routes` injects the summary's
date as `date`, and origin/dest come from the first and last segment (`da`, `aa`). Unknown or
missing fields log one warning per run through `SchemaWarnings` so drift is noticed, and a route
is kept whenever its core price fields exist.
"""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger("pointmax.raw")


class SchemaWarnings:
    """Collects one warning per distinct problem per run."""

    def __init__(self) -> None:
        self.seen: set[str] = set()

    def warn(self, msg: str) -> None:
        if msg not in self.seen:
            self.seen.add(msg)
            log.warning("PointsYeah schema: %s", msg)


class _Raw(BaseModel):
    model_config = ConfigDict(extra="allow")


class RawTransfer(_Raw):
    bank: str | None = None
    points: float | None = None
    actual_points: float | None = None
    bonus_percentage: float | None = None
    bonus_end_date: float | None = None  # epoch seconds
    bonus_slogn: str | None = None  # sic
    url: str | None = None
    code: str | None = None


class RawSegment(_Raw):
    flight_number: str | None = None
    aircraft: str | None = None
    dt: str | None = None  # ISO local departure time
    da: str | None = None  # departure airport
    at: str | None = None  # ISO local arrival time
    aa: str | None = None  # arrival airport
    cabin: str | None = None  # a cabin or a fare brand ("Main Basic", "Blue")
    duration: float | None = None
    layover: float | None = None  # minutes before the next segment


class RawPayment(_Raw):
    cabin: str | None = None
    miles: int | None = None
    tax: float | None = None
    cash_price: float | None = None  # 0 means unknown
    currency: str | None = None
    unit: str | None = None
    short_unit: str | None = None
    seats: int | str | None = None  # 9999 = not live; real values 1-9


class RawPromotion(_Raw):
    description: str | None = None
    url: str | None = None


class RawRoute(_Raw):
    program: str | None = None
    code: str | None = None
    date: str | None = None  # injected from the summary by item_routes
    payment: RawPayment | None = None
    segments: list[RawSegment] = Field(default_factory=list)
    transfer: list[RawTransfer] = Field(default_factory=list)
    promotion: RawPromotion | None = None
    duration: float | None = None  # real elapsed minutes
    cross_days: int | None = None
    premium_cabin_percentage: float | None = None
    url: str | None = None
    cash_ticket_url: str | None = None
    extra: dict[str, Any] | None = None

    def core_missing(self) -> list[str]:
        missing = []
        if not self.program:
            missing.append("program")
        if self.payment is None or not self.payment.miles:
            missing.append("payment.miles")
        if not self.segments:
            missing.append("segments")
        return missing


def parse_route(data: dict[str, Any], warnings: SchemaWarnings) -> RawRoute | None:
    try:
        route = RawRoute.model_validate(data)
    except ValidationError as e:
        warnings.warn(f"route failed validation: {e.errors()[0]['loc']} {e.errors()[0]['type']}")
        return None
    for extra in route.model_extra or {}:
        warnings.warn(f"unknown route field {extra!r}")
    for extra in (route.payment.model_extra if route.payment else None) or {}:
        warnings.warn(f"unknown payment field {extra!r}")
    if missing := route.core_missing():
        warnings.warn(f"route missing core fields {missing}; skipped")
        return None
    return route


# ---- result envelope -------------------------------------------------------


def _find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        kids = list(obj.values())
    elif isinstance(obj, list):
        kids = obj
    else:
        return None
    for k in kids:
        if (hit := _find(k, key)) is not None:
            return hit
    return None


def parse_create(body: Any) -> tuple[str, int]:
    """create_task response -> (task_id, total_sub_tasks)."""
    task_id = _find(body, "task_id")
    total = _find(body, "total_sub_tasks")
    if task_id is None:
        raise ValueError("create_task response has no task_id")
    return str(task_id), int(total) if total is not None else 0


def response_code(body: Any) -> int:
    code = body.get("code", 0) if isinstance(body, dict) else 0
    return int(code) if str(code).lstrip("-").isdigit() else 0


def parse_fetch(body: Any) -> tuple[str, list[dict[str, Any]]]:
    """fetch_result response -> (status, items); items are summaries, maybe with routes."""
    status = str(_find(body, "status") or "").lower()
    result = _find(body, "result")
    items = [r for r in result if isinstance(r, dict)] if isinstance(result, list) else []
    return status, items


def summary_key(item: dict[str, Any]) -> tuple[str, ...]:
    """(program, date, departure, arrival): identifies one sub-task's summary."""
    return tuple(str(item.get(k) or "") for k in ("program", "date", "departure", "arrival"))


def item_routes(item: dict[str, Any]) -> list[dict[str, Any]]:
    """The summary's routes, each tagged with the summary's date (routes carry none)."""
    routes = item.get("routes")
    if not isinstance(routes, list):
        return []
    return [{**r, "date": item.get("date")} for r in routes if isinstance(r, dict)]


def route_key(route: dict[str, Any]) -> tuple[Any, ...]:
    """(program, date, flight numbers, first departure, cabin, miles): one route across polls."""
    segs = [s for s in route.get("segments") or [] if isinstance(s, dict)]
    pay = route.get("payment") or {}
    return (
        route.get("program"),
        route.get("date"),
        tuple(str(s.get("flight_number") or "") for s in segs),
        segs[0].get("dt") if segs else None,
        pay.get("cabin"),
        pay.get("miles"),
    )
