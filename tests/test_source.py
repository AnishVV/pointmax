from datetime import date

import httpx
import pytest
import respx
from synthetic import create_body, fetch_body, route, summary
from test_client import CREATE, FETCH, Clock, make

from pointmax.cache import Cache
from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah.session import SessionError
from pointmax.sources.pointsyeah.source import PointsYeahBackend

R1 = SearchRequest(origin="DFW", dest="LHR", start=date(2026, 12, 23), end=date(2026, 12, 23))
R2 = R1.model_copy(update={"origin": "AUS"})


@respx.mock
async def test_cache_hit_skips_network_and_normalizes():
    respx.post(CREATE).mock(return_value=httpx.Response(200, json=create_body("T1", 1)))
    f = respx.post(FETCH).mock(
        return_value=httpx.Response(200, json=fetch_body("done", [summary(routes=[route()])]))
    )
    cl, _ = make()
    be = PointsYeahBackend(cl, Cache(":memory:"))
    first = await be.search_many([R1])
    assert len(first[R1.key]) == 1 and be.live_searches == 1
    calls = f.call_count
    second = await be.search_many([R1])
    assert second[R1.key][0].miles == 60000 and f.call_count == calls and be.cache_hits == 1
    assert be.avg_polls_per_task() == 1.0


@respx.mock
async def test_dead_session_keeps_earlier_searches_and_raises():
    respx.post(CREATE).mock(
        side_effect=[httpx.Response(200, json=create_body("T1", 1)), httpx.Response(403)]
    )
    respx.post(FETCH).mock(
        return_value=httpx.Response(200, json=fetch_body("done", [summary(routes=[route()])]))
    )
    cache = Cache(":memory:")
    cl, _ = make()
    be = PointsYeahBackend(cl, cache)
    await be.search_many([R1])  # finishes and is cached
    with pytest.raises(SessionError):
        await be.search_many([R2])  # session dies on create
    assert cache.get(R1) is not None
    assert cache.get(R2) is None


@respx.mock
async def test_failed_task_not_cached():
    respx.post(CREATE).mock(return_value=httpx.Response(500))
    cl, clock = make()
    cache = Cache(":memory:")
    be = PointsYeahBackend(cl, cache)
    out = await be.search_many([R1])
    assert out[R1.key] == [] and be.failures and cache.get(R1) is None
    assert isinstance(clock, Clock)
