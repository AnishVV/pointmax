"""Effective cost, best funding path, CPP achieved, savings vs direct.

    C_eff = sum over award legs of ( min over funding of points * cpp / 100 + taxes )
            + sum of cash legs + hotel allowance

A program's own miles are a funding path only for programs in `[balances]`; otherwise a low
own-miles valuation could undercut a bank transfer you cannot actually avoid. With no transfer
path and no balance, the program's own CPP is used and the leg is noted `no-transfer`.
"""

from pointmax.config import Settings
from pointmax.models import AwardOption, CashLeg, Itinerary, LegValue, ValueBreakdown


def _bonus_text(pct: int, ends: object) -> str:
    if pct <= 0:
        return ""
    when = f", ends {ends:%b %-d}" if ends else ""
    return f" +{pct}% bonus{when}"


def best_funding(opt: AwardOption, s: Settings, mult: int) -> tuple[str, float, str | None]:
    """(label, points cost in USD, note) for the cheapest way to fund this award."""
    candidates: list[tuple[float, float, str]] = []  # (comparison cost, real cost, label)
    for tr in opt.transfers:
        cost = tr.points * mult * s.cpp_for(tr.bank) / 100
        cmp_cost = cost * (1 - s.prefer_tiebreak_pct / 100) if tr.bank in s.prefer_banks else cost
        candidates.append((cmp_cost, cost, f"{tr.bank}{_bonus_text(tr.bonus_pct, tr.bonus_ends)}"))
    owned = {k.lower(): v for k, v in s.balances.items()}
    for name in (opt.program, opt.program_code):
        if name and owned.get(name.lower(), 0) >= opt.miles * mult:
            cost = opt.miles * mult * s.cpp_for(opt.program) / 100
            candidates.append((cost, cost, f"{opt.program} miles (balance)"))
            break
    if candidates:
        _, cost, label = min(candidates, key=lambda c: c[0])
        return label, cost, None
    cost = opt.miles * mult * s.cpp_for(opt.program) / 100
    return f"{opt.program} miles (no transfer path)", cost, "no-transfer"


def cpp_achieved(opt: AwardOption) -> float | None:
    """(cash price - taxes) / miles, in cents. None without a cash price."""
    if not opt.cash_price_usd or not opt.miles:
        return None
    return (opt.cash_price_usd - opt.taxes_usd) / opt.miles * 100


def redemption_label(achieved: float, baseline: float) -> str:
    if achieved >= 1.5 * baseline:
        return "great"
    return "good" if achieved >= baseline else "poor"


def value_itinerary(
    it: Itinerary, s: Settings, *, pax: int = 1, pax_totals: bool = False
) -> ValueBreakdown:
    """Price an itinerary. `pax_totals` = PointsYeah already returns totals for adults > 1."""
    mult = 1 if pax_totals else pax
    legs: list[LegValue] = []
    notes: list[str] = []
    for leg, role in zip(it.legs, it.roles, strict=True):
        if isinstance(leg, CashLeg):
            tag = "est." if leg.estimated else "cash"
            legs.append(
                LegValue(
                    description=f"{leg.origin}->{leg.dest} {leg.mode} ({tag})",
                    funding="cash (estimate)" if leg.estimated else "cash",
                    cash_usd=leg.price_usd * pax,
                )
            )
            if leg.estimated:
                notes.append("includes an estimated cash leg")
            continue
        label, pts_usd, note = best_funding(leg, s, mult)
        lv = LegValue(
            description=f"{leg.origin}->{leg.dest} {leg.program}",
            funding=label,
            points_usd=pts_usd,
            taxes_usd=leg.taxes_usd * mult,
        )
        if note:
            notes.append(f"{leg.program}: {note}")
        if role == "main" and (achieved := cpp_achieved(leg)) is not None:
            lv.redemption_cpp = achieved
            lv.redemption_label = redemption_label(achieved, s.cpp_for(leg.program))
        legs.append(lv)
    hotel = it.hotel_nights * s.hotel_allowance_usd
    return ValueBreakdown(
        c_eff=sum(lv.total_usd for lv in legs) + hotel, legs=legs, hotel_usd=hotel, notes=notes
    )


def elapsed_hours(it: Itinerary) -> float | None:
    """Door-to-door hours from the first departure to the last arrival, when times are known."""
    first, last = it.legs[0], it.legs[-1]
    dep = first.dep if first.dep else None
    arr = last.arr if last.arr else None
    if dep is None or arr is None:
        return None
    return (arr - dep).total_seconds() / 3600


def apply_savings(itins: list[Itinerary]) -> None:
    """Fill savings and extra hours vs the best direct itinerary in the same cabin."""
    best: dict[int, Itinerary] = {}
    for it in itins:
        if it.ring == 0 and it.value:
            cabin = int(it.main.headline_cabin)
            if cabin not in best or it.value.c_eff < best[cabin].value.c_eff:  # type: ignore[union-attr]
                best[cabin] = it
    for it in itins:
        if it.ring == 0 or not it.value:
            continue
        direct = best.get(int(it.main.headline_cabin))
        if direct is None or direct.value is None:
            continue
        it.value.savings_usd = direct.value.c_eff - it.value.c_eff
        it.value.savings_pct = (
            it.value.savings_usd / direct.value.c_eff * 100 if direct.value.c_eff else None
        )
        a, b = elapsed_hours(it), elapsed_hours(direct)
        if a is not None and b is not None:
            it.value.extra_hours = a - b
