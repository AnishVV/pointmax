"""Pydantic models of the raw PointsYeah JSON.

EVERY FIELD NAME HERE IS A GUESS from the plan's recon notes (payment.cabin, payment.cash_price,
dt/at, transfer[].actual_points, promotion.description, seats 9999) until real fixtures are
recorded. `AliasChoices` lists the plausible spellings; unknown or missing fields log one warning
per run through `SchemaWarnings` so drift is noticed, and a route is kept whenever its core
price fields exist. Replace guesses with verified names after the first fixture recording.
"""

import logging
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger("pointmax.raw")


class SchemaWarnings:
    """Collects one warning per distinct problem per run."""

    def __init__(self) -> None:
        self.seen: set[str] = set()

    def warn(self, msg: str) -> None:
        if msg not in self.seen:
            self.seen.add(msg)
            log.warning("PointsYeah schema: %s", msg)


def _alias(*names: str) -> Any:
    return Field(default=None, validation_alias=AliasChoices(*names))


class _Raw(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RawTransfer(_Raw):
    bank: str | None = _alias("bank", "bank_name", "name", "currency")
    points: int | None = _alias("points", "bank_points")
    actual_points: int | None = _alias("actual_points", "actualPoints")
    bonus_percentage: int | None = _alias("bonus_percentage", "bonus_pct", "bonus")
    bonus_end: str | None = _alias("bonus_end", "bonus_end_date", "bonus_expires", "end_date")


class RawSegment(_Raw):
    flight_no: str | None = _alias("flight_no", "flight_number", "flightNumber", "number")
    carrier: str | None = _alias("carrier", "airline", "marketing_carrier")
    origin: str | None = _alias("from", "origin", "dep_airport", "departure_airport")
    dest: str | None = _alias("to", "dest", "arr_airport", "arrival_airport")
    dt: str | None = _alias("dt", "departure_time", "dep_time")
    at: str | None = _alias("at", "arrival_time", "arr_time")
    cabin: str | None = _alias("cabin", "cabin_class")
    aircraft: str | None = _alias("aircraft", "equipment", "plane")
    layover: int | None = _alias("layover", "layover_min", "layover_minutes")


class RawPayment(_Raw):
    cabin: str | None = _alias("cabin", "cabin_class")
    miles: int | None = _alias("miles", "points", "mileage")
    tax: float | None = _alias("tax", "taxes", "taxes_usd", "fees")
    cash_price: float | None = _alias("cash_price", "cashPrice", "cash")
    currency: str | None = _alias("currency", "tax_currency")


class RawPromotion(_Raw):
    description: str | None = _alias("description", "desc", "title")


class RawRoute(_Raw):
    program: str | None = _alias("program", "program_name", "airline_program")
    program_code: str | None = _alias("program_code", "programCode", "code")
    origin: str | None = _alias("from", "origin", "dep")
    dest: str | None = _alias("to", "dest", "arr")
    date: str | None = _alias("date", "departure_date", "dep_date")
    payment: RawPayment | None = None
    seats: int | None = _alias("seats", "seats_remaining", "available_seats")
    duration: int | None = _alias("duration", "duration_min", "total_duration")
    premium_pct: int | None = _alias("premium_pct", "premiumPct", "premium_percentage")
    booking_url: str | None = _alias("booking_url", "bookingUrl", "url", "link")
    segments: list[RawSegment] = Field(default_factory=list)
    transfer: list[RawTransfer] = Field(default_factory=list)
    promotion: RawPromotion | None = None
    bonus_percentage: int | None = None

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
    if missing := route.core_missing():
        warnings.warn(f"route missing core fields {missing}; skipped")
        return None
    return route


# ---- result envelope (also guessed) -------------------------------------------------------


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

    def pick(*names: str) -> str:
        for n in names:
            if n in item and item[n] is not None:
                return str(item[n])
        return ""

    return (
        pick("program", "program_code", "program_name"),
        pick("date", "departure_date"),
        pick("departure", "from", "origin"),
        pick("arrival", "to", "dest"),
    )


def item_routes(item: dict[str, Any]) -> list[dict[str, Any]]:
    routes = item.get("routes")
    if isinstance(routes, list):
        return [r for r in routes if isinstance(r, dict)]
    return [item] if "segments" in item else []


def route_key(route: dict[str, Any]) -> tuple[Any, ...]:
    """(flight numbers, cabin, miles): identifies one route across duplicate polls."""
    flights = tuple(
        str(s.get("flight_no") or s.get("flight_number") or s.get("number") or "")
        for s in route.get("segments") or []
        if isinstance(s, dict)
    )
    pay = route.get("payment") or {}
    return (
        route.get("program") or route.get("program_code"),
        route.get("date"),
        flights,
        pay.get("cabin"),
        pay.get("miles") or pay.get("points"),
    )
