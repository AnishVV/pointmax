from datetime import date
from pathlib import Path

import pytest
from synthetic import FakeBackend, opt, scenario

from pointmax import config
from pointmax.models import Cabin
from pointmax.planner import plan as pl
from pointmax.rank import filters as flt

S = config.load_settings(Path("/nonexistent.toml"))


def query(**kw):
    base = dict(
        homes=["AUS", "DFW"],
        dest="LHR",
        start=date(2026, 12, 23),
        end=date(2026, 12, 24),
        filters=flt.Filters(cabin=Cabin.BUSINESS),
        yes=True,
    )
    return pl.Query(**(base | kw))


async def test_positioning_beats_direct_and_gets_savings():
    be = FakeBackend(scenario())
    res = await pl.Planner(be, S).run(query())
    ranked = flt.sort_itineraries(res.itineraries)
    top = ranked[0]
    assert top.gateway == "IAH" and top.ring == 1
    assert top.roles == ["position_out", "main"]
    # 60,000 Aeroplan via Chase @2.0c + $78 taxes, plus the AUS->IAH award leg
    assert top.value.c_eff == pytest.approx(1278 + top.value.legs[0].total_usd)
    direct = next(i for i in ranked if i.ring == 0)
    assert direct.value.c_eff == pytest.approx(275000 * 0.02 + 6)
    assert top.value.savings_pct and top.value.savings_pct > 70
    r1 = res.rings[1]
    assert r1.gain_pct and r1.gain_pct > 70 and "IAH" in r1.gateways


async def test_bound_check_prunes_gateways_without_positioning_searches():
    be = FakeBackend(scenario())
    res = await pl.Planner(be, S).run(query())
    pruned = set(res.rings[1].pruned)
    assert {"HOU", "SAT", "OKC"} & pruned
    pos_dests = {r.dest for r in be.asked if r.dest != "LHR"}
    assert pos_dests == {"IAH"}  # positioning only ever searched toward the surviving gateway


async def test_gateway_searched_once_across_rings():
    be = FakeBackend(scenario())
    await pl.Planner(be, S).run(query(rings=2))
    iah_main = [r for r in be.asked if r.origin == "IAH" and r.dest == "LHR"]
    assert len(iah_main) == 1


async def test_ring_dates_limits_later_rings():
    data = scenario()
    data[("DFW", "LHR")].append(
        opt("Alaska Atmos Rewards", 300000, "DFW", "LHR", "2026-12-24 17:00", "2026-12-25 08:00")
    )
    be = FakeBackend(data)
    q = query()
    pln = pl.Planner(be, S)
    s = S
    s.ring_dates = 1
    res = await pln.run(q)
    ring1_main = [r for r in be.asked if r.dest == "LHR" and r.origin not in q.homes]
    assert all(r.start == r.end == date(2026, 12, 23) for r in ring1_main)
    assert res.rings[0].best_after is not None
    s.ring_dates = 2


async def test_no_estimate_when_positioning_returns_nothing():
    data = scenario()
    del data[("AUS", "IAH")]
    be = FakeBackend(data)
    res = await pl.Planner(be, S).run(query())
    top = flt.sort_itineraries(res.itineraries)[0]
    assert top.gateway == "IAH"
    cash = [leg for leg in top.legs if hasattr(leg, "estimated")]
    assert cash and cash[0].estimated and "estimated" in top.value.notes[0]


async def test_sparse_route_completes_with_no_results():
    be = FakeBackend({})
    res = await pl.Planner(be, S).run(query(dest="AMD"))
    assert res.itineraries == [] and res.rings[0].best_after is None


async def test_budget_stop():
    be = FakeBackend(scenario())
    res = await pl.Planner(be, S).run(query(budget_min=0.01))
    assert res.rings[-1].stopped == "over budget" and res.warnings


async def test_declined_ring_stops():
    be = FakeBackend({("DFW", "LHR"): scenario()[("DFW", "LHR")]})

    async def no(_):
        return False

    res = await pl.Planner(be, S, ask=no).run(query(yes=False, rings=2))
    # ring 1 auto-continues; ring 2 asks because ring 1 gained nothing, and is declined
    assert [r.stopped for r in res.rings][-1] == "declined"


def test_windows_for():
    d = date
    assert pl.windows_for([d(2026, 12, 23), d(2026, 12, 24), d(2026, 12, 29)], 4) == [
        (d(2026, 12, 23), d(2026, 12, 24)),
        (d(2026, 12, 29), d(2026, 12, 29)),
    ]
    assert pl.windows_for([d(2026, 12, 23), d(2026, 12, 27)], 4) == [
        (d(2026, 12, 23), d(2026, 12, 23)),
        (d(2026, 12, 27), d(2026, 12, 27)),
    ]


async def test_ring0_empty_then_ring1_finds_continues_without_prompt():
    data = scenario()
    del data[("DFW", "LHR")]
    asked = []

    async def ask(prompt):
        asked.append(prompt)
        return True

    res = await pl.Planner(FakeBackend(data), S, ask=ask).run(query(yes=False, rings=2))
    assert res.rings[0].best_after is None and res.rings[1].best_after is not None
    assert asked == []  # no baseline to compare against, so ring 2 is automatic
