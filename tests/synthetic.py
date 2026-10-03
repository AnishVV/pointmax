"""SYNTHETIC PointsYeah-shaped data in the verified schema, for edge cases the recorded fixtures
lack. Whole-response behaviour is tested against tests/fixtures (test_recorded.py)."""

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
        "duration": 600,
        "flight_number": flight,
        "aircraft": "Boeing 777-300ER ",
        "dt": dt.replace(" ", "T") + ":00",
        "da": frm,
        "at": at.replace(" ", "T") + ":00",
        "aa": to,
        "layover": layover,
        "cabin": cabin,
    }


def route(
    program="Air Canada Aeroplan",
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
    """A route as PointsYeah returns it: no date/origin/dest (the summary carries the date)."""
    segs = segments if segments is not None else [segment(cabin=cabin)]
    return {
        "payment": {
            "currency": "USD",
            "tax": tax,
            "miles": miles,
            "cabin": cabin,
            "unit": "points",
            "short_unit": "pts",
            "seats": seats,
            "cash_price": cash_price,
        },
        "segments": segs,
        "duration": 840,
        "cross_days": 1,
        "program": program,
        "code": program[:2].upper(),
        "premium_cabin_percentage": 0,
        "url": "https://example.test/book",
        "cash_ticket_url": "",
        "extra": {},
        "promotion": None,
        "transfer": transfer
        if transfer is not None
        else [
            {
                "bank": "Chase Ultimate Rewards",
                "actual_points": miles,
                "points": miles,
                "bonus_percentage": 0,
                "bonus_end_date": 0,
                "bonus_slogn": "",
                "url": "",
                "code": "CH",
            }
        ],
        **extra,
    }


def summary(program="Air Canada Aeroplan", date="2026-12-23", dep="DFW", arr="LHR", routes=None):
    return {
        "program": program,
        "code": program[:2].upper(),
        "date": date,
        "departure": dep,
        "arrival": arr,
        "routes": routes or [],
    }


def fetch_body(status, items):
    return {"code": 0, "success": True, "data": {"status": status, "result": items}}


def create_body(task_id="T1", total=2):
    return {
        "code": 0,
        "success": True,
        "data": {"task_id": task_id, "total_sub_tasks": total, "status": "created"},
    }


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
                "Air Canada Aeroplan",
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
