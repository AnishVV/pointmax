"""Curated hub lists for ring 2 (domestic alliance hubs) and ring 3 (international gateways).

US hubs and stopover hubs follow the reference docs hubs-alliances-carriers.md and the
reference README (rule 9). The doc rates hub assignments MEDIUM volatility: re-verify yearly.
"""

ALLIANCES = ("oneworld", "Star Alliance", "SkyTeam")

# US hub -> alliances with a carrier hubbed there, per hubs-alliances-carriers.md:
# American and Alaska are oneworld, United is Star Alliance, Delta is SkyTeam.
# United's Guam hub is left out (not a domestic positioning point); Southwest and JetBlue
# hubs are left out because neither carrier is in an alliance.
US_ALLIANCE_HUBS: dict[str, frozenset[str]] = {
    "ANC": frozenset({"oneworld"}),
    "ATL": frozenset({"SkyTeam"}),
    "BOS": frozenset({"SkyTeam"}),
    "CLT": frozenset({"oneworld"}),
    "CVG": frozenset({"SkyTeam"}),
    "DCA": frozenset({"oneworld"}),
    "DEN": frozenset({"Star Alliance"}),
    "DFW": frozenset({"oneworld"}),
    "DTW": frozenset({"SkyTeam"}),
    "EWR": frozenset({"Star Alliance"}),
    "IAD": frozenset({"Star Alliance"}),
    "IAH": frozenset({"Star Alliance"}),
    "JFK": frozenset({"oneworld", "SkyTeam"}),
    "LAX": frozenset({"oneworld", "Star Alliance", "SkyTeam"}),
    "LGA": frozenset({"oneworld", "SkyTeam"}),
    "MIA": frozenset({"oneworld"}),
    "MSP": frozenset({"SkyTeam"}),
    "ORD": frozenset({"oneworld", "Star Alliance"}),
    "PDX": frozenset({"oneworld"}),
    "PHL": frozenset({"oneworld"}),
    "PHX": frozenset({"oneworld"}),
    "SAN": frozenset({"oneworld"}),
    "SEA": frozenset({"oneworld", "SkyTeam"}),
    "SFO": frozenset({"Star Alliance"}),
    "SLC": frozenset({"SkyTeam"}),
}

# Hubs where a free or cheap stopover is commonly allowed (README rule 9); a bonus flag, not a cost.
STOPOVER_HUBS = frozenset({"KEF", "IST", "DXB", "DOH", "AUH", "SIN", "PTY", "LIS"})

# International gateways near the US that are often cheaper starting points (ring 3).
# The reference doc names YYZ as a positioning point; YUL, YVR and MEX are unverified.
NORTH_AMERICA_GATEWAYS = ("YYZ", "YUL", "YVR", "MEX")

# Same-metro alternates for common destinations (ring 3 "near the arrival city").
DESTINATION_ALTERNATES: dict[str, tuple[str, ...]] = {
    "LHR": ("LGW", "LCY", "STN", "CDG", "AMS", "DUB"),
    "CDG": ("ORY", "LHR", "AMS", "BRU"),
    "NRT": ("HND", "KIX", "ICN", "TPE"),
    "HND": ("NRT", "KIX", "ICN", "TPE"),
    "AMD": ("BOM", "DEL", "BDQ"),
}


def alliance_count(iata: str) -> int:
    return len(US_ALLIANCE_HUBS.get(iata, ()))


# Airports that share a city: PointsYeah adds these automatically, and changing between them
# between separate tickets needs the longer metro buffer.
METRO_GROUPS: tuple[frozenset[str], ...] = tuple(
    frozenset(g.split())
    for g in (
        "DFW DAL",
        "IAH HOU",
        "JFK EWR LGA",
        "ORD MDW",
        "DCA IAD BWI",
        "LAX BUR LGB SNA ONT",
        "SFO OAK SJC",
        "MIA FLL",
        "LHR LGW LCY STN",
        "CDG ORY",
        "NRT HND",
    )
)


def metro_siblings(iata: str) -> frozenset[str]:
    """Other airports in the same metro area (empty if none known)."""
    for group in METRO_GROUPS:
        if iata in group:
            return group - {iata}
    return frozenset()


def same_metro(a: str, b: str) -> bool:
    return a == b or b in metro_siblings(a)
