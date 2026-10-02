"""SYNTHETIC PointsYeah-shaped data built from the plan's guessed schema.

Not recorded from the live API. When real fixtures exist, these helpers should be replaced by
them (or kept only for edge cases) and the field names in raw.py verified.
"""

from typing import Any

from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah.normalize import normalize_routes


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


def opt(
    program,
    miles,
    origin,
    dest,
    dep,
    arr,
    cabin="Business",
    tax=6.0,
    flight="XX1",
    cash=None,
    transfer=None,
):
    seg = segment(flight, origin, dest, dep, arr, cabin=cabin)
    kw = {"cash_price": cash} if cash is not None else {}
    return normalize_routes(
        [route(program, miles, tax, cabin, date=dep[:10], segments=[seg], transfer=transfer, **kw)]
    )[0]


class FakeBackend:
    max_date_range = 4

    def __init__(self, data):
        self.data = data  # {(origin, dest): [AwardOption]}
        self.asked: list[SearchRequest] = []

    async def search_many(self, requests, *, fresh=False):
        out = {}
        for r in requests:
            self.asked.append(r)
            out[r.key] = [
                o for o in self.data.get((r.origin, r.dest), []) if r.start <= o.date <= r.end
            ]
        return out

    def avg_polls_per_task(self):
        return 5.0


def scenario():
    return {
        ("DFW", "LHR"): [
            opt(
                "Alaska Atmos Rewards",
                275000,
                "DFW",
                "LHR",
                "2026-12-23 17:00",
                "2026-12-24 08:00",
                flight="AS100",
            )
        ],
        ("IAH", "LHR"): [
            opt(
                "Aeroplan",
                60000,
                "IAH",
                "LHR",
                "2026-12-23 18:00",
                "2026-12-24 08:00",
                tax=78.0,
                flight="UA900",
            )
        ],
        ("AUS", "IAH"): [
            opt(
                "United MileagePlus",
                8000,
                "AUS",
                "IAH",
                "2026-12-23 10:00",
                "2026-12-23 11:10",
                cabin="Economy",
                tax=5.6,
                flight="UA1",
            )
        ],
    }
