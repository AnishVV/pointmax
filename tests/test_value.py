from datetime import date, datetime
from pathlib import Path

import pytest
from synthetic import route, segment

from pointmax import config
from pointmax.models import AwardOption, CashLeg, Itinerary
from pointmax.rank import filters as flt
from pointmax.rank import value as v
from pointmax.sources.pointsyeah.normalize import normalize_routes

S = config.load_settings(Path("/nonexistent.toml"))


def opt(**kw) -> AwardOption:
    return normalize_routes([route(**kw)])[0]


def direct(o, ring=0):
    return Itinerary(legs=[o], roles=["main"], ring=ring)


def test_hand_computed_effective_cost():
    # 60,000 via Chase UR @2.0c = $1,200 + $78 taxes
    it = direct(opt(miles=60000, tax=78.0))
    assert v.value_itinerary(it, S).c_eff == pytest.approx(1278.0)


def test_cheapest_funding_path_with_bonus_label():
    o = opt(
        miles=60000,
        transfer=[
            {"bank": "Chase Ultimate Rewards", "points": 60000, "actual_points": 60000},
            {
                "bank": "Bilt",
                "points": 60000,
                "actual_points": 50000,
                "bonus_percentage": 20,
                "bonus_end": "2026-10-15",
            },
        ],
    )
    label, usd, note = v.best_funding(o, S, 1)
    assert usd == pytest.approx(1000.0) and label == "Bilt +20% bonus, ends Oct 15" and note is None


def test_own_miles_only_if_balance_listed():
    o = opt(miles=60000, transfer=[{"bank": "Chase Ultimate Rewards", "points": 60000}])
    assert v.best_funding(o, S, 1)[1] == pytest.approx(1200.0)  # own miles at 1.5c ignored
    s2 = config.load_settings(Path("/nonexistent.toml"))
    s2.balances = {"Aeroplan": 100000}
    label, usd, _ = v.best_funding(o, s2, 1)
    assert usd == pytest.approx(900.0) and "balance" in label


def test_no_transfer_path_uses_program_cpp_and_notes():
    o = opt(program="Some Airline", miles=50000, transfer=[])
    _, usd, note = v.best_funding(o, S, 1)
    assert note == "no-transfer" and usd == pytest.approx(600.0)  # default 1.2c
    it = direct(o)
    assert "no-transfer" in v.value_itinerary(it, S).notes[0]


def test_pax_multiplies_unless_totals():
    it = direct(opt(miles=60000, tax=78.0))
    assert v.value_itinerary(it, S, pax=2).c_eff == pytest.approx(2556.0)
    assert v.value_itinerary(it, S, pax=2, pax_totals=True).c_eff == pytest.approx(1278.0)


def test_cash_leg_and_hotel():
    main = opt(miles=60000, tax=78.0)
    pos = CashLeg(origin="AUS", dest="DFW", date=date(2026, 12, 22), price_usd=95.0)
    it = Itinerary(
        legs=[pos, main], roles=["position_out", "main"], gateway="DFW", ring=1, hotel_nights=1
    )
    val = v.value_itinerary(it, S)
    assert val.c_eff == pytest.approx(1278 + 95 + 150) and val.hotel_usd == 150
    assert "estimated" in val.notes[0]


def test_cpp_achieved_and_label():
    o = opt(miles=275000, tax=5.6, cash_price=5300.0)
    assert v.cpp_achieved(o) == pytest.approx((5300 - 5.6) / 275000 * 100)
    assert v.redemption_label(2.4, 1.5) == "great"
    assert v.redemption_label(1.5, 1.5) == "good"
    assert v.redemption_label(0.9, 1.5) == "poor"
    assert v.cpp_achieved(opt(cash_price=0.0)) is None


def test_savings_vs_best_direct_same_cabin():
    d1 = direct(opt(miles=275000, tax=6.0, program="Alaska Atmos Rewards"))
    pos_main = opt(miles=60000, tax=78.0)
    p = Itinerary(
        legs=[
            CashLeg(
                origin="AUS",
                dest="DFW",
                date=date(2026, 12, 22),
                price_usd=95.0,
                dep=datetime(2026, 12, 23, 6),
                arr=datetime(2026, 12, 23, 7),
            ),
            pos_main,
        ],
        roles=["position_out", "main"],
        ring=1,
        gateway="DFW",
    )
    for it in (d1, p):
        it.value = v.value_itinerary(it, S)
    v.apply_savings([d1, p])
    assert p.value.savings_usd == pytest.approx(d1.value.c_eff - p.value.c_eff)
    assert p.value.savings_pct > 50 and p.value.extra_hours is not None


def test_cabin_filter_all_business_with_premium_pct_zero_passes():
    o = opt(cabin="Business")
    assert o.premium_pct == 0 and flt.cabin_ok(o, flt.Cabin.BUSINESS, 60)


def test_cabin_filter_mixed_itinerary():
    segs = [
        segment(
            "AA1", "DFW", "ORD", cabin="Business", dt="2026-12-23 08:00", at="2026-12-23 10:00"
        ),
        segment("AA2", "ORD", "LHR", cabin="Economy", dt="2026-12-23 12:00", at="2026-12-24 02:00"),
    ]
    r = route(cabin="Business", segments=segs)
    r["premium_pct"] = 40
    assert not flt.cabin_ok(normalize_routes([r])[0], flt.Cabin.BUSINESS, 60)
    r["premium_pct"] = 70
    assert flt.cabin_ok(normalize_routes([r])[0], flt.Cabin.BUSINESS, 60)


def test_economy_headline_fails_business_filter():
    assert not flt.cabin_ok(opt(cabin="Economy"), flt.Cabin.BUSINESS, 60)


def test_option_filters():
    o = opt(seats=1)
    assert not flt.option_ok(o, flt.Filters(pax=2))
    assert flt.option_ok(o, flt.Filters(pax=1, max_taxes=100))
    assert not flt.option_ok(o, flt.Filters(max_taxes=10))
    assert not flt.option_ok(
        opt(segments=[segment(dt="2026-12-23 22:00", at="2026-12-24 06:00")]),
        flt.Filters(no_redeye=True),
    )


def test_sorting_ties_and_keys():
    a, b = direct(opt(miles=60000)), direct(opt(miles=50000))
    for it in (a, b):
        it.value = v.value_itinerary(it, S)
    assert flt.sort_itineraries([a, b])[0] is b
    assert flt.sort_itineraries([a, b], "miles")[0] is b
    with pytest.raises(ValueError):
        flt.sort_itineraries([a], "nope")
