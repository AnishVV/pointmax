from datetime import date
from itertools import pairwise

import httpx
import respx
from synthetic import create_body, fetch_body, route, summary

from pointmax.ratelimit import RateLimiter
from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah import client as c
from pointmax.sources.pointsyeah.session import SessionData

SECTION = "AbCd1234"
CREATE = c.API_BASE + c.CREATE_PATH
FETCH = c.API_BASE + c.FETCH_PATH


class Clock:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def make(clock=None, **kw):
    clock = clock or Clock()
    limiter = RateLimiter(clock=clock, sleep=clock.sleep)
    session = SessionData(request_key_section=SECTION, cookies=[{"name": "sid", "value": "x"}])
    cl = c.PointsYeahClient(session, limiter, clock=clock, sleep=clock.sleep, **kw)
    return cl, clock


REQ = SearchRequest(origin="DFW", dest="LHR", start=date(2026, 12, 23), end=date(2026, 12, 26))


def seq(*bodies):
    return [httpx.Response(200, json=b) for b in bodies]


@respx.mock
async def test_stops_when_summary_count_matches_total():
    s1 = summary("Air Canada Aeroplan", routes=[route()])
    s2 = summary("United", routes=[route("United MileagePlus", 70000)])
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 2)))
    f = respx.post(FETCH).mock(
        side_effect=seq(
            fetch_body("processing", [s1]), fetch_body("done", [s1, s2]), fetch_body("done", [])
        )
    )
    cl, _ = make()
    [t] = await cl.run_tasks([REQ])
    assert t.stop_reason == "complete" and t.polls == 2 and f.call_count == 2
    assert len(t.routes) == 2  # duplicate s1 route de-duplicated


@respx.mock
async def test_create_body_is_encrypted_with_session_key():
    from pointmax.sources.pointsyeah import crypto

    r = respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 1)))
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("done", [summary()])))
    cl, _ = make()
    await cl.run_tasks([REQ])
    import json

    sent = json.loads(r.calls[0].request.content)
    q = json.loads(crypto.decrypt_text(sent["encrypted"], SECTION))
    assert q["search_type"] == "one_way" and q["cabins"] == c.ALL_CABINS
    assert q["passengers_v2"]["adults"] == 1 and q["source"] == "pc"
    assert r.calls[0].request.headers["cookie"] == "sid=x"


@respx.mock
async def test_quiet_fallback_after_first_done():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 5)))
    respx.post(FETCH).mock(
        side_effect=seq(
            fetch_body("processing", [summary()]),
            fetch_body("done", []),
            fetch_body("processing", []),
            fetch_body("processing", []),
            fetch_body("processing", []),
        )
    )
    cl, _ = make()
    [t] = await cl.run_tasks([REQ])
    assert t.stop_reason == "quiet" and t.polls == 4


@respx.mock
async def test_cap_after_four_minutes():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 3)))
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("processing", [])))
    cl, clock = make()
    start = clock.t
    [t] = await cl.run_tasks([REQ])
    assert t.stop_reason == "cap" and clock.t - start >= c.TASK_CAP_S


@respx.mock
async def test_cadence_five_then_seven_then_two_after_done():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 9)))
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("processing", [])))
    cl, clock = make()
    times = []
    orig = cl.fetch_result

    async def spy(task_id):
        times.append(clock.t)
        return await orig(task_id)

    cl.fetch_result = spy
    await cl.run_tasks([REQ])
    gaps = [round(b - a) for a, b in pairwise(times)]
    assert gaps and set(gaps) == {7}


@respx.mock
async def test_round_robin_shares_one_limiter():
    other = REQ.model_copy(update={"origin": "AUS"})
    ids = iter(["T1", "T2"])
    respx.post(CREATE).mock(
        side_effect=lambda r: httpx.Response(200, json=create_body(next(ids), 1))
    )
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("done", [summary()])))
    cl, _ = make()
    tasks = await cl.run_tasks([REQ, other])
    assert [t.stop_reason for t in tasks] == ["complete", "complete"]
    stamps = sorted(cl.limiter._stamps)
    assert all(sum(1 for t in stamps if s <= t < s + 30) <= 10 for s in stamps)


@respx.mock
async def test_retry_on_5xx_then_succeed():
    respx.post(CREATE).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=create_body("T1", 1))]
    )
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("done", [summary()])))
    cl, _ = make()
    [t] = await cl.run_tasks([REQ])
    assert t.stop_reason == "complete"


@respx.mock
async def test_429_triggers_cooldown():
    respx.post(CREATE).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=create_body("T1", 1))]
    )
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("done", [summary()])))
    cl, clock = make()
    start = clock.t
    await cl.run_tasks([REQ])
    assert clock.t - start >= c.COOLDOWN_429_S - 5


@respx.mock
async def test_session_refresh_once_then_retry():
    respx.post(CREATE).mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=create_body("T1", 1))]
    )
    respx.post(FETCH).mock(return_value=httpx.Response(200, json=fetch_body("done", [summary()])))
    refreshed = []

    async def refresh():
        refreshed.append(1)
        return SessionData(request_key_section=SECTION, cookies=[{"name": "sid", "value": "new"}])

    cl, _ = make(refresh=refresh)
    [t] = await cl.run_tasks([REQ])
    assert refreshed == [1] and t.stop_reason == "complete"


@respx.mock
async def test_dead_session_marks_tasks_and_fails_fast():
    r = respx.post(CREATE).mock(return_value=httpx.Response(403))
    other = REQ.model_copy(update={"origin": "AUS"})
    cl, _ = make()
    tasks = await cl.run_tasks([REQ, other])
    assert cl.session_dead and all("HTTP 403" in t.error or "expired" in t.error for t in tasks)
    assert r.call_count == 1  # the second task never hit the network


@respx.mock
async def test_session_expires_mid_poll_refreshes_once():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 1)))
    respx.post(FETCH).mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json=fetch_body("done", [summary()]))]
    )
    calls = []

    async def refresh():
        calls.append(1)
        return SessionData(request_key_section=SECTION, cookies=[{"name": "sid", "value": "n"}])

    cl, _ = make(refresh=refresh)
    [t] = await cl.run_tasks([REQ])
    assert calls == [1] and t.stop_reason == "complete"


@respx.mock
async def test_4xx_is_a_task_error_not_a_crash():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 1)))
    respx.post(FETCH).mock(return_value=httpx.Response(404))
    cl, _ = make()
    [t] = await cl.run_tasks([REQ])
    assert "404" in t.error


@respx.mock
async def test_nonzero_code_is_reported_with_message():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json={"code": 7, "message": "quota"}))
    cl, _ = make()
    [t] = await cl.run_tasks([REQ])
    assert "code 7" in t.error and "quota" in t.error


@respx.mock
async def test_on_exchange_traffic_feeds_scrubber(tmp_path):
    import json

    from pointmax.devtools import scrub

    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T9", 1)))
    respx.post(FETCH).mock(
        return_value=httpx.Response(200, json=fetch_body("done", [summary(routes=[route()])]))
    )
    log: list[dict] = []
    cl, _ = make(on_exchange=log.append)
    await cl.run_tasks([REQ])
    auth = {
        "t": 0,
        "at": "2026-10-02T00:00:00+00:00",
        "method": "GET",
        "url": "https://www.pointsyeah.com/api/auth/session",
        "status": 200,
        "request_headers": {},
        "request_body": None,
        "response_body": json.dumps(
            {"data": {"isAuthenticated": True, "requestKeySection": SECTION}}
        ),
    }
    path = tmp_path / "traffic.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in [auth, *log]))
    scrub.build_fixtures(path, tmp_path / "fx", ["dfw-lhr"])
    meta = json.loads((tmp_path / "fx" / "dfw-lhr" / "meta.json").read_text())
    assert meta["browser_byte_match"] and meta["polls"] == 1 and meta["total_sub_tasks"] == 1
