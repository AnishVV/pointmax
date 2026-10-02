"""SYNTHETIC PointsYeah-shaped data built from the plan's guessed schema.

Not recorded from the live API. When real fixtures exist, these helpers should be replaced by
them (or kept only for edge cases) and the field names in raw.py verified.
"""

from typing import Any


def segment(
    flight="AA100",
    frm="DFW",
    to="LHR",
    dt="2026-12-23 17:30",
    at="2026-12-24 07:40",
    cabin="Business",
    layover=0,
) -> dict[str, Any]:
    return {
        "flight_no": flight,
        "carrier": flight[:2],
        "from": frm,
        "to": to,
        "dt": dt,
        "at": at,
        "cabin": cabin,
        "aircraft": "77W",
        "layover": layover,
    }


def route(
    program="Aeroplan",
    miles=60000,
    tax=78.0,
    cabin="Business",
    date="2026-12-23",
    segments=None,
    transfer=None,
    cash_price=3200.0,
    seats=9999,
    **extra,
) -> dict[str, Any]:
    segs = segments if segments is not None else [segment(cabin=cabin)]
    return {
        "program": program,
        "program_code": program[:2].upper(),
        "from": segs[0]["from"],
        "to": segs[-1]["to"],
        "date": date,
        "payment": {
            "cabin": cabin,
            "miles": miles,
            "tax": tax,
            "cash_price": cash_price,
            "currency": "USD",
        },
        "seats": seats,
        "duration": 840,
        "premium_pct": 0,
        "booking_url": "https://example.test/book",
        "segments": segs,
        "transfer": transfer
        if transfer is not None
        else [
            {
                "bank": "Chase Ultimate Rewards",
                "points": miles,
                "actual_points": miles,
                "bonus_percentage": 0,
            }
        ],
        "promotion": None,
        **extra,
    }


def summary(program="Aeroplan", date="2026-12-23", dep="DFW", arr="LHR", routes=None):
    return {
        "program": program,
        "date": date,
        "departure": dep,
        "arrival": arr,
        "routes": routes or [],
    }


def fetch_body(status, items):
    return {"code": 0, "data": {"status": status, "result": items}}


def create_body(task_id="T1", total=2):
    return {"code": 0, "data": {"task_id": task_id, "total_sub_tasks": total}}
