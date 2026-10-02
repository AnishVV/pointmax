import pytest

from pointmax.geo import airports, hubs


def test_home_airports_load():
    for code in ("AUS", "DFW", "DAL", "IAH", "LHR", "NRT", "AMD"):
        ap = airports.get(code)
        assert ap.scheduled_service


def test_unknown_airport():
    with pytest.raises(KeyError):
        airports.get("ZZZ")


def test_haversine_dfw_aus():
    d = airports.haversine_km(airports.get("DFW"), airports.get("AUS"))
    assert 285 < d < 310


def test_ring1_examples_within_400km():
    near = {ap.iata for home in ("AUS", "DFW") for ap, _ in airports.nearby(home, 400)}
    assert {"SAT", "IAH", "HOU", "OKC", "DAL"} <= near


def test_nearby_sorted_and_excludes_self():
    hits = airports.nearby("DFW", 400)
    assert all(ap.iata != "DFW" for ap, _ in hits)
    assert [d for _, d in hits] == sorted(d for _, d in hits)


def test_every_curated_hub_is_a_known_airport():
    codes = (
        set(hubs.US_ALLIANCE_HUBS)
        | hubs.STOPOVER_HUBS
        | set(hubs.NORTH_AMERICA_GATEWAYS)
        | set(hubs.DESTINATION_ALTERNATES)
        | {c for alts in hubs.DESTINATION_ALTERNATES.values() for c in alts}
    )
    for code in codes:
        airports.get(code)
    for alliances in hubs.US_ALLIANCE_HUBS.values():
        assert alliances <= set(hubs.ALLIANCES)
