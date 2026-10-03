"""Rich tables: ranked results, ring tradeoff, and the detail view for `pointmax show N`."""

from rich.console import Console
from rich.table import Table

from pointmax.models import AwardOption, CashLeg, Itinerary
from pointmax.planner.plan import RingReport, SearchResult


def route_text(it: Itinerary) -> str:
    first, main = it.legs[0], it.main
    if it.gateway:
        return f"{first.origin}→[{it.gateway}]→{main.dest}"
    return f"{main.origin}→{main.dest}"


def pos_cost(it: Itinerary) -> float | None:
    if it.value is None or not it.gateway:
        return None
    main_total = next(
        lv.total_usd for lv, r in zip(it.value.legs, it.roles, strict=True) if r == "main"
    )
    return it.value.c_eff - main_total


def flag_text(it: Itinerary) -> str:
    flags = set(it.main.flags)
    if it.value and any("estimated" in n for n in it.value.notes):
        flags.add("est.")
    if it.hotel_nights:
        flags.add(f"hotel x{it.hotel_nights}")
    if it.gateway:
        flags.discard("self_transfer")
    return " ".join(sorted(flags))


def results_table(its: list[Itinerary], top: int = 15) -> Table:
    t = Table(title=None, header_style="bold", expand=False)
    for col, just in [
        ("#", "right"),
        ("Route", "left"),
        ("Date", "left"),
        ("Program", "left"),
        ("Pts", "right"),
        ("Taxes", "right"),
        ("Pos.", "right"),
        ("Eff. $", "right"),
        ("cpp", "right"),
        ("Hrs", "right"),
        ("Flags", "left"),
    ]:
        t.add_column(col, justify=just)  # type: ignore[arg-type]
    for i, it in enumerate(its[:top], 1):
        assert it.value is not None
        main = it.main
        pos = pos_cost(it)
        main_leg = next(lv for lv, r in zip(it.value.legs, it.roles, strict=True) if r == "main")
        t.add_row(
            str(i),
            route_text(it),
            f"{main.date:%b %-d}",
            main.program,
            f"{main.miles:,}",
            f"${sum(o.taxes_usd for o in it.award_legs):,.0f}",
            f"${pos:,.0f}" if pos is not None else "—",
            f"${it.value.c_eff:,.0f}",
            f"{main_leg.redemption_cpp:.1f}" if main_leg.redemption_cpp else "—",
            f"{main.duration_min / 60:.0f}",
            flag_text(it),
        )
    return t


def ring_table(res: SearchResult) -> Table:
    t = Table(title="Ring tradeoff", header_style="bold")
    for col in ("Ring", "Gateways", "Searches", "Best eff. $", "vs direct", "Extra hrs"):
        t.add_column(col, justify="left" if col == "Ring" else "right")
    base = res.rings[0].best_after if res.rings else None
    for r in res.rings:
        extra = _extra_hours(res, r)
        t.add_row(
            str(r.ring),
            ", ".join(r.gateways) if r.ring else "/".join(r.gateways),
            str(r.tasks) if r.tasks else "—",
            f"${r.best_after:,.0f}" if r.best_after is not None else "—",
            _vs_direct(r, base),
            f"{extra:+.1f}" if extra is not None else "—",
        )
    return t


def _vs_direct(r: RingReport, base: float | None) -> str:
    if r.stopped:
        return f"→ stopped ({r.stopped})"
    if r.ring == 0 or base is None or r.best_after is None:
        return "—"
    if r.best_before is not None and r.best_after >= r.best_before - 0.5:
        return "no gain"
    diff = base - r.best_after
    return "no gain" if diff <= 0.5 else f"-{diff / base * 100:.0f}% (${diff:,.0f})"


def _extra_hours(res: SearchResult, r: RingReport) -> float | None:
    cands = [i for i in res.itineraries if i.ring == r.ring and i.value]
    if not cands or r.ring == 0:
        return None
    best = min(cands, key=lambda i: i.value.c_eff)  # type: ignore[union-attr]
    return best.value.extra_hours  # type: ignore[union-attr]


def _leg_line(leg: AwardOption | CashLeg, role: str) -> str:
    if isinstance(leg, CashLeg):
        tag = "est." if leg.estimated else "cash"
        return f"{role}: {leg.origin}→{leg.dest} {leg.mode} ({tag}) ${leg.price_usd:,.0f}"
    return (
        f"{role}: {leg.origin}→{leg.dest} {leg.program} {leg.miles:,} pts + ${leg.taxes_usd:,.2f}"
    )


def detail(console: Console, it: Itinerary, n: int) -> None:
    assert it.value is not None
    console.print(f"[bold]Result {n}: {route_text(it)}[/bold]  effective ${it.value.c_eff:,.0f}")
    for leg, role, lv in zip(it.legs, it.roles, it.value.legs, strict=True):
        console.print(f"  {_leg_line(leg, role)}")
        console.print(
            f"    funding: {lv.funding}  (${lv.points_usd:,.0f} points"
            f" + ${lv.taxes_usd + lv.cash_usd:,.0f} cash)"
        )
        if lv.redemption_cpp:
            console.print(
                f"    redemption: {lv.redemption_cpp:.1f}¢ per point ({lv.redemption_label})"
            )
        if isinstance(leg, AwardOption):
            for s in leg.segments:
                console.print(
                    f"    {s.flight_no} {s.origin} {s.dep:%b %-d %H:%M}"
                    f" → {s.dest} {s.arr:%b %-d %H:%M} {s.cabin}"
                )
            if leg.buy_promo:
                console.print(f"    promo: {leg.buy_promo}")
            if leg.booking_url:
                console.print(f"    book: {leg.booking_url}")
    if it.value.hotel_usd:
        console.print(f"  hotel allowance: ${it.value.hotel_usd:,.0f}")
    if it.value.savings_usd is not None:
        console.print(
            f"  saves ${it.value.savings_usd:,.0f} ({it.value.savings_pct:.0f}%) vs best direct"
        )
    for note in it.notes + it.value.notes:
        console.print(f"  note: {note}")


def render_results(console: Console, res: SearchResult, ranked: list[Itinerary], top: int) -> None:
    if not ranked:
        console.print("[yellow]No award space found for these dates and filters.[/yellow]")
    else:
        console.print(results_table(ranked, top))
    console.print()
    console.print(ring_table(res))
    for w in res.warnings:
        console.print(f"[yellow]{w}[/yellow]")


def history_table(runs: list[dict]) -> Table:
    """Past runs from the search history, newest first."""
    t = Table(title="Search history", header_style="bold")
    for col, just in [
        ("ID", "right"),
        ("When", "left"),
        ("Route", "left"),
        ("Dates", "left"),
        ("Cabin", "left"),
        ("Pax", "right"),
        ("Results", "right"),
        ("Best eff. $", "right"),
        ("Best program", "left"),
        ("Status", "left"),
    ]:
        t.add_column(col, justify=just)  # type: ignore[arg-type]
    for r in runs:
        dates = r["depart_start"]
        if r["depart_end"] != r["depart_start"]:
            dates += f"…{r['depart_end'][5:]}"
        route = f"{r['origins'].replace(',', '/')}→{r['dest']}"
        if r["leg"] == "return":
            route += " (return)"
        t.add_row(
            str(r["run_id"]),
            r["at"][:16].replace("T", " "),
            route,
            dates,
            r["cabin"] or "any",
            str(r["pax"]),
            str(r["n_results"]),
            f"${r['best_eff_usd']:,.0f}" if r["best_eff_usd"] is not None else "—",
            r["best_program"] or "—",
            "" if r["status"] == "ok" else r["status"],
        )
    return t
