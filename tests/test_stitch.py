from datetime import date
from pathlib import Path

from synthetic import route, segment

from pointmax import config
from pointmax.geo.hubs import metro_siblings, same_metro
from pointmax.models import CashLeg, Itinerary
from pointmax.planner import stitch as st
from pointmax.rank.value import value_itinerary
from pointmax.sources.pointsyeah.normalize import normalize_routes

S = config.load_settings(Path("/nonexistent.toml"))


def main_at(origin="IAH", dep="2026-12-23 18:00", flight="UA900"):
    seg = segment(flight, origin, "LHR", dep, "2026-12-24 08:00")
    return normalize_routes([route("Aeroplan", 60000, segments=[seg])])[0]


def pos_to(dest="IAH", arr="2026-12-23 12:00", origin="AUS", flight="UA1"):
    seg = segment(flight, origin, dest, "2026-12-23 10:00", arr, cabin="Economy")
    return normalize_routes([route("United MileagePlus", 8000, 5.6, "Economy", segments=[seg])])[0]


def test_metro():
    assert same_metro("HOU", "IAH") and "DAL" in metro_siblings("DFW")
    assert not same_metro("DFW", "IAH")


def test_exactly_three_hours_ok_same_airport():
    ok, nights, _ = st.feasibility(pos_to(arr="2026-12-23 15:00"), main_at(), S)
    assert ok and nights == 0


def test_under_three_hours_rejected():
    assert not st.feasibility(pos_to(arr="2026-12-23 15:01"), main_at(), S)[0]


def test_metro_change_needs_four_hours():
    p = pos_to(dest="HOU", arr="2026-12-23 14:30")
    assert not st.feasibility(p, main_at("IAH"), S)[0]  # 3.5 h, different airport
    p2 = pos_to(dest="HOU", arr="2026-12-23 14:00")
    assert st.feasibility(p2, main_at("IAH"), S)[0]


def test_different_cities_rejected():
    assert not st.feasibility(pos_to(dest="SAT"), main_at("IAH"), S)[0]


def test_night_before_counts_hotel():
    p = pos_to(arr="2026-12-22 21:00")
    ok, nights, note = st.feasibility(p, main_at(), S)
    assert ok and nights == 1 and "overnight" in note


def test_more_than_24h_rejected():
    assert not st.feasibility(pos_to(arr="2026-12-22 17:00"), main_at(), S)[0]


def test_cash_leg_estimate_without_times():
    leg = CashLeg(origin="AUS", dest="IAH", date=date(2026, 12, 22), price_usd=120)
    ok, nights, _ = st.feasibility(leg, main_at(), S)
    assert ok and nights == 0


def test_stitch_cross_join_drops_infeasible():
    mains = [main_at(), main_at(dep="2026-12-23 11:00")]
    out = st.stitch([pos_to()], mains, "IAH", 1, S)
    assert len(out) == 1 and out[0].gateway == "IAH" and out[0].roles == ["position_out", "main"]


def test_appears_inside():
    assert st.appears_inside(("UA900",), ("UA1", "UA900"))
    assert not st.appears_inside(("UA900", "UA2"), ("UA1", "UA900"))
    assert not st.appears_inside((), ("UA1",))


def _direct(flights, miles):
    segs = [
        segment(
            f,
            "AUS" if i == 0 else "IAH",
            "IAH" if i == 0 else "LHR",
            f"2026-12-23 {8 + i * 4:02d}:00",
            f"2026-12-23 {10 + i * 4:02d}:30",
        )
        for i, f in enumerate(flights)
    ]
    it = Itinerary(
        legs=[normalize_routes([route("Aeroplan", miles, 80.0, segments=segs)])[0]],
        roles=["main"],
        ring=0,
    )
    it.value = value_itinerary(it, S)
    return it


def test_dominance_single_ticket_wins_unless_10pct_cheaper():
    direct = _direct(["UA1", "UA900"], 60000)  # 1280
    built_equal = Itinerary(legs=[main_at()], roles=["main"], ring=1)
    built_equal.value = value_itinerary(built_equal, S)
    built_equal.value.c_eff = 1270  # only 0.8% cheaper
    assert st.dominated(built_equal, [direct], 10)
    built_equal.value.c_eff = 1100  # 14% cheaper
    assert not st.dominated(built_equal, [direct], 10)


def test_same_flights_not_dominated():
    d = _direct(["UA900"], 60000)
    b = Itinerary(legs=[main_at()], roles=["main"], ring=1)
    b.value = value_itinerary(b, S)
    assert not st.dominated(b, [d], 10)
