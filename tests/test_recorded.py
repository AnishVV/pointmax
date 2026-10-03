"""Tests against the real, scrubbed PointsYeah recordings in tests/fixtures."""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from pointmax.ratelimit import RateLimiter
from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah import client as c
from pointmax.sources.pointsyeah import crypto, raw
from pointmax.sources.pointsyeah.normalize import normalize_routes
from pointmax.sources.pointsyeah.session import SessionData

FIX = Path(__file__).parent / "fixtures"
CREATE = c.API_BASE + c.CREATE_PATH
FETCH = c.API_BASE + c.FETCH_PATH


def polls(name):
    lines = (FIX / name / "fetch_result.jsonl").read_text().splitlines()
    return [json.loads(x)["body"] for x in lines]


def all_routes(name):
    out = {}
    for body in polls(name):
        for item in body["data"]["result"]:
            for r in raw.item_routes(item):
                out.setdefault(raw.route_key(r), r)
    return list(out.values())


class Clock:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def make():
    clock = Clock()
    limiter = RateLimiter(clock=clock, sleep=clock.sleep)
    session = SessionData(request_key_section="pmTESTse", cookies=[{"name": "sid", "value": "x"}])
    return c.PointsYeahClient(session, limiter, clock=clock, sleep=clock.sleep), clock


def test_build_query_matches_recorded_browser_query():
    req = SearchRequest(origin="DFW", dest="LHR", start=date(2026, 11, 9), end=date(2026, 11, 11))
    q = c.build_query(req)
    assert q == json.loads((FIX / "dfw-lhr" / "query.json").read_text())
    kat = json.loads((FIX / "crypto_kat.json").read_text())
    assert crypto.serialize(q) == kat["plaintext"]
    assert crypto.encrypt_text(crypto.serialize(q), kat["section"]) == kat["ciphertext"]


def test_create_response_parses():
    body = json.loads((FIX / "dfw-lhr" / "create_task.json").read_text())["body"]
    assert raw.parse_create(body) == (body["data"]["task_id"], 54)


@pytest.mark.parametrize("name", ["dfw-lhr", "dfw-amd", "multi"])
def test_every_recorded_route_parses_without_schema_warnings(name, caplog):
    routes = all_routes(name)
    assert routes
    with caplog.at_level(logging.WARNING, logger="pointmax.raw"):
        options = normalize_routes(routes)
    assert not [r for r in caplog.records if r.name == "pointmax.raw"]
    assert len(options) == len(routes)
    assert all(o.miles > 0 and o.segments and o.origin and o.dest for o in options)
    assert all(o.date for o in options)


def test_first_dfw_lhr_route_spot_check():
    first = next(r for item in polls("dfw-lhr")[0]["data"]["result"] for r in raw.item_routes(item))
    [o] = normalize_routes([first])
    assert o.program == "Virgin Atlantic Flying Club" and o.program_code == "VS"
    assert (o.miles, o.taxes_usd, o.seats, o.stops, o.duration_min) == (23500, 319.0, 9, 1, 709)
    assert (o.origin, o.dest, o.date) == ("DFW", "LHR", date(2026, 11, 9))
    assert len(o.transfers) == 6 and o.cash_price_usd is None


def test_alternate_airports_present():
    options = normalize_routes(all_routes("dfw-lhr"))
    assert "DAL" in {o.origin for o in options}
    assert all(o.dest in {"LHR", "LGW", "LCY"} for o in options)


def test_multi_city_has_per_segment_summaries():
    items = [i for b in polls("multi") for i in b["data"]["result"]]
    assert len({(i["departure"], i["arrival"]) for i in items}) > 1


class ReplayServer:
    """Serves a recording against the fake clock: each poll drains every recorded poll that has
    happened by now, so a slower poller sees merged batches, as the real (drained) API behaves."""

    def __init__(self, name, clock):
        self.recorded = [
            json.loads(x) for x in (FIX / name / "fetch_result.jsonl").read_text().splitlines()
        ]
        self.clock, self.start, self.cursor, self.status = clock, 0.0, 0, "processing"

    def create(self, request):
        self.start = self.clock()
        body = json.loads((FIX / "dfw-lhr" / "create_task.json").read_text())["body"]
        return httpx.Response(200, json=body)

    def fetch(self, request):
        now = self.clock() - self.start
        items = []
        while self.cursor < len(self.recorded) and self.recorded[self.cursor]["t"] <= now:
            data = self.recorded[self.cursor]["body"]["data"]
            items += data["result"]
            self.status = data["status"]
            self.cursor += 1
        body = {"code": 0, "success": True, "data": {"result": items, "status": self.status}}
        return httpx.Response(200, json=body)


@respx.mock
async def test_poller_replays_recorded_dfw_lhr_and_stops_at_second_done():
    cl, clock = make()
    server = ReplayServer("dfw-lhr", clock)
    respx.post(CREATE).mock(side_effect=server.create)
    respx.post(FETCH).mock(side_effect=server.fetch)
    req = SearchRequest(origin="DFW", dest="LHR", start=date(2026, 11, 9), end=date(2026, 11, 11))
    [t] = await cl.run_tasks([req])
    assert t.stop_reason == "complete" and t.done_polls == 2
    assert t.polls < 15  # the browser polled 37 times
    assert len(t.summaries) == 51 < t.total == 54
    assert len(t.routes) == len(all_routes("dfw-lhr"))
    assert clock() - server.start < 60
