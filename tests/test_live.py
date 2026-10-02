"""Live checks against PointsYeah. Run by hand: `uv run pytest -m live` (needs `pointmax login`)."""

import asyncio
from datetime import date, timedelta

import pytest

from pointmax import config
from pointmax.ratelimit import RateLimiter
from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah import session as sess
from pointmax.sources.pointsyeah.client import PointsYeahClient
from pointmax.sources.pointsyeah.normalize import normalize_routes

pytestmark = pytest.mark.live


def test_status_authenticated():
    data = sess.load_session()
    info = asyncio.run(sess.check_session(data))
    assert info.authenticated
    assert info.request_key_section == data.request_key_section


def test_direct_search_dfw_lhr_stays_inside_rate_windows():
    async def go():
        data = await sess.ensure_session()
        limiter = RateLimiter(db_path=config.cache_path())
        client = PointsYeahClient(data, limiter)
        start = date.today() + timedelta(days=60)
        req = SearchRequest(origin="DFW", dest="LHR", start=start, end=start + timedelta(days=3))
        [task] = await client.run_tasks([req])
        await client.aclose()
        stamps = sorted(limiter._stamps)
        return task, stamps

    task, stamps = asyncio.run(go())
    assert not task.error
    options = normalize_routes(list(task.routes.values()))
    assert len(options) > 0
    assert all(sum(1 for t in stamps if s <= t < s + 30) <= 10 for s in stamps)
    assert all(sum(1 for t in stamps if s <= t < s + 300) <= 50 for s in stamps)
