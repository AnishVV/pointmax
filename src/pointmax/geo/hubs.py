"""Curated hub lists for ring 2 (domestic alliance hubs) and ring 3 (international gateways).

Compiled from general knowledge in M0 because `hubs-alliances-carriers.md` was not
available to the session. Reconcile against that reference before M4 relies on it.
"""

ALLIANCES = ("oneworld", "Star Alliance", "SkyTeam")

# US hub -> alliances with a carrier hubbed there (AA/AS oneworld, UA Star, DL SkyTeam).
US_ALLIANCE_HUBS: dict[str, frozenset[str]] = {
    "ATL": frozenset({"SkyTeam"}),
    "BOS": frozenset({"SkyTeam"}),
    "CLT": frozenset({"oneworld"}),
    "DCA": frozenset({"oneworld"}),
    "DEN": frozenset({"Star Alliance"}),
    "DFW": frozenset({"oneworld"}),
    "DTW": frozenset({"SkyTeam"}),
    "EWR": frozenset({"Star Alliance"}),
    "IAD": frozenset({"Star Alliance"}),
    "IAH": frozenset({"Star Alliance"}),
    "JFK": frozenset({"oneworld", "SkyTeam"}),
    "LAX": frozenset({"oneworld", "Star Alliance", "SkyTeam"}),
    "MIA": frozenset({"oneworld"}),
    "MSP": frozenset({"SkyTeam"}),
    "ORD": frozenset({"oneworld", "Star Alliance"}),
    "PHL": frozenset({"oneworld"}),
    "PHX": frozenset({"oneworld"}),
    "SEA": frozenset({"oneworld", "SkyTeam"}),
    "SFO": frozenset({"Star Alliance", "oneworld"}),
    "SLC": frozenset({"SkyTeam"}),
}

# Hubs where a free or cheap stopover is commonly allowed; a bonus flag, not a cost.
STOPOVER_HUBS = frozenset({"KEF", "IST", "DXB", "DOH", "AUH", "SIN", "PTY", "LIS"})

# International gateways near the US that are often cheaper starting points (ring 3).
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
