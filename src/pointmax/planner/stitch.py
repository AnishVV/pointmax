"""Combine positioning and main legs into itineraries under connection-buffer rules.

Separate tickets need a buffer: 3 h at the same airport and 4 h when changing airports within
a metro (defaults, configurable). Times at the gateway are both local, so no time-zone math.
A positioning leg may arrive up to 24 h before the main departure; arriving on an earlier
calendar day counts as one night at the gateway (hotel allowance).
"""

from datetime import timedelta

from pointmax.config import Settings
from pointmax.geo.hubs import same_metro
from pointmax.models import AwardOption, CashLeg, Itinerary

TOP_POSITIONING = 5
TOP_MAIN = 10


def feasibility(
    pos: AwardOption | CashLeg, main: AwardOption, s: Settings
) -> tuple[bool, int, str | None]:
    """(ok, hotel nights at the gateway, note)."""
    if main.dep is None:
        return False, 0, None
    if isinstance(pos, CashLeg):
        arr = pos.arr
        if arr is None:  # an estimate with no times: assume it can be scheduled
            nights = 1 if pos.date < main.dep.date() else 0
            return True, nights, "overnight in gateway" if nights else None
    else:
        arr = pos.arr
    if arr is None:
        return False, 0, None
    gap = main.dep - arr
    if pos.dest != main.origin and not same_metro(pos.dest, main.origin):
        return False, 0, None
    needed = s.same_airport_hours if pos.dest == main.origin else s.metro_change_hours
    if gap < timedelta(hours=needed) or gap > timedelta(hours=s.max_early_arrival_hours):
        return False, 0, None
    nights = 1 if arr.date() < main.dep.date() else 0
    return True, nights, f"overnight in {main.origin}" if nights else None


def appears_inside(main_flights: tuple[str, ...], ticket_flights: tuple[str, ...]) -> bool:
    """True when `main_flights` is a contiguous run inside a single-ticket itinerary."""
    n = len(main_flights)
    if n == 0 or n > len(ticket_flights):
        return False
    return any(
        ticket_flights[i : i + n] == main_flights for i in range(len(ticket_flights) - n + 1)
    )


def dominated(it: Itinerary, directs: list[Itinerary], pct: float) -> bool:
    """A single ticket protects the connection, so it wins unless self-built is `pct` cheaper."""
    if it.value is None:
        return False
    flights = it.main.flight_numbers
    for d in directs:
        if d.value is None or not appears_inside(flights, d.main.flight_numbers):
            continue
        if d.main.flight_numbers == flights:
            continue  # same flights, no connection to protect
        if it.value.c_eff > d.value.c_eff * (1 - pct / 100):
            return True
    return False


def stitch(
    positioning: list[AwardOption | CashLeg],
    mains: list[AwardOption],
    gateway: str,
    ring: int,
    s: Settings,
    *,
    role: str = "position_out",
) -> list[Itinerary]:
    """Cross-join positioning x main options, dropping infeasible pairs."""
    out = []
    for pos in positioning[:TOP_POSITIONING]:
        for main in mains[:TOP_MAIN]:
            ok, nights, note = feasibility(pos, main, s)
            if not ok:
                continue
            out.append(
                Itinerary(
                    legs=[pos, main],
                    roles=[role, "main"],  # type: ignore[list-item]
                    gateway=gateway,
                    ring=ring,
                    hotel_nights=nights,
                    notes=[note] if note else [],
                )
            )
    return out
