from datetime import date, datetime

import pytest

from pointmax.cache import Cache
from pointmax.models import AwardOption, Cabin
from pointmax.sources.base import SearchRequest, chunk_dates


def _opt(**kw):
    base = dict(
        program="Aeroplan",
        origin="DFW",
        dest="LHR",
        date=date(2026, 12, 23),
        cabin="Business",
        miles=60000,
        taxes_usd=78.0,
        fetched_at=datetime(2026, 10, 2),
    )
    return AwardOption(**(base | kw))


@pytest.mark.parametrize(
    ("text", "cabin"),
    [
        ("Economy", Cabin.ECONOMY),
        ("Premium Economy", Cabin.PREMIUM),
        ("PREMIUM_ECONOMY", Cabin.PREMIUM),
        ("Business", Cabin.BUSINESS),
        ("First", Cabin.FIRST),
        ("business class", Cabin.BUSINESS),
    ],
)
def test_cabin_parse(text, cabin):
    assert Cabin.parse(text) is cabin


def test_cabin_parse_unknown():
    with pytest.raises(ValueError):
        Cabin.parse("steerage")


def test_chunk_dates_7_days_max_4():
    assert chunk_dates(date(2026, 12, 20), date(2026, 12, 26), 4) == [
        (date(2026, 12, 20), date(2026, 12, 23)),
        (date(2026, 12, 24), date(2026, 12, 26)),
    ]


def test_chunk_single_day():
    assert chunk_dates(date(2026, 12, 20), date(2026, 12, 20), 4) == [(date(2026, 12, 20),) * 2]


def test_request_key_stable_and_distinct():
    a = SearchRequest(origin="DFW", dest="LHR", start=date(2026, 12, 20), end=date(2026, 12, 23))
    assert a.key == a.model_copy().key
    assert a.key != a.model_copy(update={"pax": 2}).key
    assert a.days == 4


def test_cache_round_trip_and_ttl(tmp_path):
    now = [1000.0]
    c = Cache(tmp_path / "c.sqlite", ttl_hours=1, clock=lambda: now[0])
    req = SearchRequest(origin="DFW", dest="LHR", start=date(2026, 12, 20), end=date(2026, 12, 23))
    assert c.get(req) is None
    c.put(req, [_opt(flags={"bonus"})])
    got = c.get(req)
    assert got and got[0].miles == 60000 and got[0].flags == {"bonus"}
    assert c.get(req, fresh=True) is None
    now[0] += 3601
    assert c.get(req) is None
    assert c.stats()["searches"] == 1
    assert c.clear() == 1


def test_poll_stats():
    c = Cache(":memory:")
    assert c.avg_polls_per_task() == 6.0
    c.record_task(4, 20)
    c.record_task(8, 40)
    assert c.avg_polls_per_task() == 6.0
