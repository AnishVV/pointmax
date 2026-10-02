from datetime import date

from synthetic import route, segment

from pointmax.sources.pointsyeah.normalize import normalize_routes, parse_dt
from pointmax.sources.pointsyeah.raw import SchemaWarnings, parse_route


def one(**kw):
    out = normalize_routes([route(**kw)])
    assert len(out) == 1
    return out[0]


def test_basic_fields():
    o = one(program="Alaska Atmos Rewards", miles=275000, tax=5.6)
    assert (o.miles, o.taxes_usd, o.cabin, o.origin, o.dest) == (
        275000,
        5.6,
        "Business",
        "DFW",
        "LHR",
    )
    assert o.date == date(2026, 12, 23) and o.stops == 0
    assert o.seats is None  # 9999 means not live inventory


def test_low_seats_and_bonus_flags():
    o = one(
        seats=2,
        transfer=[
            {
                "bank": "Bilt",
                "points": 60000,
                "actual_points": 50000,
                "bonus_percentage": 20,
                "bonus_end": "2026-10-15",
            }
        ],
    )
    assert {"low_seats", "bonus"} <= o.flags
    assert o.transfers[0].points == 50000 and o.transfers[0].bonus_ends == date(2026, 10, 15)


def test_redeye_window():
    red = segment(dt="2026-12-23 22:00", at="2026-12-24 06:30")
    day = segment(dt="2026-12-23 10:00", at="2026-12-23 18:00")
    assert "redeye" in one(segments=[red]).flags
    assert "redeye" not in one(segments=[day]).flags


def test_overnight_layover_and_self_transfer():
    a = segment("AA1", "DFW", "ORD", "2026-12-23 20:00", "2026-12-23 23:00")
    b = segment("AA2", "ORD", "LHR", "2026-12-24 08:00", "2026-12-24 22:00")
    assert "overnight" in one(segments=[a, b]).flags
    c = segment("AA3", "MDW", "LHR", "2026-12-24 08:00", "2026-12-24 22:00")
    flags = one(segments=[a, c]).flags
    assert "self_transfer" in flags


def test_short_layover_not_overnight():
    a = segment("AA1", "DFW", "ORD", "2026-12-23 10:00", "2026-12-23 13:00")
    b = segment("AA2", "ORD", "LHR", "2026-12-23 16:00", "2026-12-24 06:00")
    assert "overnight" not in one(segments=[a, b]).flags


def test_missing_core_fields_skipped_with_one_warning():
    w = SchemaWarnings()
    bad = route()
    del bad["payment"]
    assert parse_route(bad, w) is None and parse_route(dict(bad), w) is None
    assert len(w.seen) == 1


def test_unknown_field_warns_once_but_keeps_route():
    w = SchemaWarnings()
    raw = parse_route(route(mystery_field=1), w)
    assert raw is not None and any("mystery_field" in m for m in w.seen)


def test_alternate_spellings_accepted():
    r = route()
    r["payment"] = {"cabin": "Business", "points": 70000, "taxes": 12.5, "currency": "USD"}
    o = normalize_routes([r])[0]
    assert o.miles == 70000 and o.taxes_usd == 12.5


def test_unknown_currency_flagged():
    r = route()
    r["payment"]["currency"] = "EUR"
    assert "currency_unconverted" in normalize_routes([r])[0].flags


def test_parse_dt_formats():
    assert parse_dt("2026-12-23 17:30").hour == 17
    assert parse_dt("2026-12-23T17:30:00Z").minute == 30
    assert parse_dt("garbage") is None
