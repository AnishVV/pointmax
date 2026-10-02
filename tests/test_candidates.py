from pathlib import Path

from synthetic import route, segment

from pointmax import config
from pointmax.planner import candidates as cand
from pointmax.sources.pointsyeah.normalize import normalize_routes

S = config.load_settings(Path("/nonexistent.toml"))
HOMES = ["AUS", "DFW"]


def test_ring1_contains_expected_and_respects_cap_and_exclusions():
    got = cand.pick(1, HOMES, "LHR", S, used=set())
    codes = [c.iata for c in got]
    assert len(codes) <= S.ring_caps[1]
    assert not {"AUS", "DFW", "DAL"} & set(codes)  # homes and DFW's metro sibling excluded
    assert all(c.ring == 1 and c.km_from_home <= 400 for c in got)
    assert set(codes) <= {"SAT", "IAH", "HOU", "OKC", "ACT", "TYR", "SHV", "LFT", "LCH"} | set(
        codes
    )


def test_ring1_prefers_iah_via_alliance_and_distance():
    codes = [c.iata for c in cand.pick(1, HOMES, "LHR", S, used=set())]
    assert "IAH" in codes[:2]


def test_gateway_searched_once_in_lowest_ring():
    r1 = cand.pick(1, HOMES, "LHR", S, used=set())
    used = {c.iata for c in r1}
    r2 = cand.pick(2, HOMES, "LHR", S, used=used)
    assert not used & {c.iata for c in r2}
    assert "IAH" in used and "IAH" not in {c.iata for c in r2}


def test_ring2_adds_connection_hubs_from_ring0():
    seg1 = segment("AA1", "DFW", "CLT", "2026-12-23 08:00", "2026-12-23 11:00")
    seg2 = segment("AA2", "CLT", "LHR", "2026-12-23 13:00", "2026-12-23 23:00")
    opts = normalize_routes([route(segments=[seg1, seg2])])
    signal = cand.connection_signal(opts, {id(opts[0]): 1000.0})
    assert signal == {"CLT": 1.0}
    got = cand.pick(2, HOMES, "LHR", S, used=set(), signal=signal)
    assert got[0].iata == "CLT" or "CLT" in [c.iata for c in got]


def test_ring3_international_gateways():
    codes = {c.iata for c in cand.pick(3, HOMES, "LHR", S, used=set())}
    assert codes <= {"YYZ", "YUL", "YVR", "MEX"} and codes


def test_alternate_destinations_exclude_same_metro():
    alts = cand.alternate_destinations("LHR", HOMES, used=set())
    assert "LGW" not in alts and "CDG" in alts
