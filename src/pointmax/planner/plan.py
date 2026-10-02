"""Ring-by-ring search planning with branch and bound.

Ring 0 searches every home airport directly. Each further ring picks gateway candidates, then:
  1. searches the main leg G -> destination first (on ring 0's cheapest dates only),
  2. drops G if its main leg alone can't beat the best itinerary so far (bound check),
  3. only for survivors, searches positioning home -> G on [D-1, D] for each surviving date,
  4. stitches positioning x main under buffer rules and prices the result.
Before each ring it quotes tasks and minutes; it continues automatically while the previous
ring paid off, otherwise it asks (`--yes` skips the question). `--budget-min` and `--rings` cap it.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from pointmax.config import Settings
from pointmax.geo import airports as geo
from pointmax.models import AwardOption, CashLeg, Itinerary
from pointmax.planner import candidates as cand
from pointmax.planner import stitch as st
from pointmax.rank import filters as flt
from pointmax.rank import value as val
from pointmax.sources.base import SearchRequest

REQUESTS_PER_MIN = 10.0  # 50 per 5 min is the binding limit
AUTO_CONTINUE_GAIN_PCT = 10.0
DRIVE_MAX_KM = 300.0


class Backend(Protocol):
    max_date_range: int

    async def search_many(
        self, requests: list[SearchRequest], *, fresh: bool = False
    ) -> dict[str, list[AwardOption]]: ...

    def avg_polls_per_task(self) -> float: ...


@dataclass
class Query:
    homes: list[str]
    dest: str
    start: date
    end: date
    pax: int = 1
    filters: flt.Filters = field(default_factory=flt.Filters)
    rings: int = 2
    budget_min: float = 15.0
    yes: bool = False
    fresh: bool = False
    pax_totals: bool = False


@dataclass
class RingReport:
    ring: int
    gateways: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    tasks: int = 0
    best_before: float | None = None
    best_after: float | None = None
    stopped: str = ""

    @property
    def gain_pct(self) -> float | None:
        if self.best_before in (None, 0) or self.best_after is None:
            return None
        return (self.best_before - self.best_after) / self.best_before * 100  # type: ignore[operator]


@dataclass
class SearchResult:
    itineraries: list[Itinerary]
    rings: list[RingReport]
    warnings: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0


def windows_for(dates: list[date], max_days: int) -> list[tuple[date, date]]:
    """Greedy windows of at most `max_days` days that cover every date in `dates`."""
    out: list[tuple[date, date]] = []
    for d in sorted(set(dates)):
        if out and (d - out[-1][0]).days < max_days:
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


class Planner:
    def __init__(
        self,
        backend: Backend,
        settings: Settings,
        *,
        echo: Callable[[str], None] = lambda _: None,
        ask: Callable[[str], Awaitable[bool]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backend, self.s, self.echo, self._ask, self._clock = (
            backend,
            settings,
            echo,
            ask,
            clock,
        )

    # ---- helpers --------------------------------------------------------------------------

    def _value(self, it: Itinerary, q: Query) -> Itinerary:
        it.value = val.value_itinerary(it, self.s, pax=q.pax, pax_totals=q.pax_totals)
        return it

    def _standalone(self, opt: AwardOption, q: Query) -> float:
        it = Itinerary(legs=[opt], roles=["main"], ring=0)
        return val.value_itinerary(it, self.s, pax=q.pax, pax_totals=q.pax_totals).c_eff

    def _quote(self, ring: int, tasks: int, q: Query) -> float:
        reqs = tasks * (1 + self.backend.avg_polls_per_task())
        return reqs / REQUESTS_PER_MIN

    def ring_dates(self, q: Query, directs: list[Itinerary]) -> list[date]:
        """Ring 0's cheapest dates in the cabin, plus every date with no space there."""
        window = [q.start + timedelta(days=i) for i in range((q.end - q.start).days + 1)]
        if not directs:
            return window
        cheapest: dict[date, float] = {}
        for it in directs:
            assert it.value is not None
            d = it.main.date
            cheapest[d] = min(cheapest.get(d, float("inf")), it.value.c_eff)
        best = sorted(cheapest, key=lambda d: cheapest[d])[: self.s.ring_dates]
        empty = [d for d in window if d not in cheapest]
        return sorted(set(best) | set(empty))

    def _requests(self, origin: str, dest: str, dates: list[date], q: Query) -> list[SearchRequest]:
        return [
            SearchRequest(origin=origin, dest=dest, start=a, end=b, pax=q.pax)
            for a, b in windows_for(dates, self.backend.max_date_range)
        ]

    def _positioning_options(
        self, home: str, gateway: str, options: list[AwardOption], q: Query, day: date
    ) -> list[AwardOption | CashLeg]:
        """Cheapest of award-at-CPP, the option's own cash price, or a labeled estimate."""
        priced: list[tuple[float, AwardOption | CashLeg]] = []
        for o in options:
            if o.origin != home and not cand.metro_siblings(home) & {o.origin}:
                continue
            if not flt.option_ok(o, flt.Filters(pax=q.pax)):
                continue
            award = self._standalone(o, q)
            if o.cash_price_usd and o.cash_price_usd < award / max(q.pax, 1):
                priced.append(
                    (
                        o.cash_price_usd,
                        CashLeg(
                            origin=o.origin,
                            dest=o.dest,
                            date=o.date,
                            price_usd=o.cash_price_usd,
                            estimated=False,
                            dep=o.dep,
                            arr=o.arr,
                        ),
                    )
                )
            else:
                priced.append((award / max(q.pax, 1), o))
        priced.sort(key=lambda p: p[0])
        legs = [leg for _, leg in priced]
        if not legs:
            legs = [self._estimate(home, gateway, day, q)]
        return legs

    def _estimate(self, home: str, gateway: str, day: date, q: Query) -> CashLeg:
        km = geo.haversine_km(geo.get(home), geo.get(gateway))
        if km <= DRIVE_MAX_KM:
            return CashLeg(
                origin=home,
                dest=gateway,
                date=day,
                price_usd=km * self.s.drive_usd_per_km,
                estimated=True,
                mode="drive",
            )
        return CashLeg(
            origin=home, dest=gateway, date=day, price_usd=self.s.cash_estimate(km), estimated=True
        )

    # ---- the search -----------------------------------------------------------------------

    async def run(self, q: Query) -> SearchResult:
        t0 = self._clock()
        reports: list[RingReport] = []
        warnings: list[str] = []

        reqs = [r for h in q.homes for r in self._requests(h, q.dest, _span(q.start, q.end), q)]
        self.echo(f"Ring 0: direct from {', '.join(q.homes)}, {len(reqs)} searches.")
        results = await self.backend.search_many(reqs, fresh=q.fresh)
        ring0 = [o for opts in results.values() for o in opts]
        directs = [
            self._value(Itinerary(legs=[o], roles=["main"], ring=0), q)
            for o in ring0
            if flt.option_ok(o, q.filters)
        ]
        best = min((i.value.c_eff for i in directs if i.value), default=None)
        reports.append(RingReport(0, list(q.homes), [], len(reqs), None, best))
        all_its = list(directs)

        used: set[str] = set(q.homes)
        signal = cand.connection_signal(
            ring0, {id(i.main): i.value.c_eff for i in directs if i.value}
        )
        prev_gain: float | None = None
        for ring in range(1, q.rings + 1):
            gws = cand.pick(ring, q.homes, q.dest, self.s, used=used, signal=signal)
            if not gws:
                reports.append(RingReport(ring, stopped="no candidates"))
                continue
            dates = self.ring_dates(q, directs)
            main_reqs = [r for g in gws for r in self._requests(g.iata, q.dest, dates, q)]
            est = self._quote(ring, len(main_reqs) * 2, q)
            elapsed_min = (self._clock() - t0) / 60
            best_txt = f"${best:,.0f}" if best is not None else "none yet"
            prev_txt = (
                f" Previous ring improved by {prev_gain:.0f}%." if prev_gain is not None else ""
            )
            self.echo(
                f"Ring {ring}: {len(gws)} gateways, about {len(main_reqs) * 2} tasks, "
                f"about {est:.0f} min. Best so far {best_txt}.{prev_txt}"
            )
            if elapsed_min + est > q.budget_min:
                reports.append(RingReport(ring, [g.iata for g in gws], stopped="over budget"))
                warnings.append(
                    f"Stopped before ring {ring}: over the {q.budget_min:.0f} min budget."
                )
                break
            auto = (
                ring == 1
                or prev_gain is None
                or prev_gain >= AUTO_CONTINUE_GAIN_PCT
                or best is None
            )
            if not auto and not q.yes:
                ok = await self._ask(f"Ring {ring}: continue? [Y/n]") if self._ask else True
                if not ok:
                    reports.append(RingReport(ring, [g.iata for g in gws], stopped="declined"))
                    break
            used |= {g.iata for g in gws}
            report = RingReport(ring, [g.iata for g in gws], best_before=best)
            new_its, report = await self._ring(
                ring, gws, dates, q, main_reqs, directs, best, report
            )
            all_its.extend(new_its)
            costs = ([best] if best is not None else []) + [
                i.value.c_eff for i in new_its if i.value
            ]
            best = min(costs) if costs else None
            report.best_after = best
            prev_gain = report.gain_pct or 0.0
            reports.append(report)

        val.apply_savings(all_its)
        return SearchResult(all_its, reports, warnings, self._clock() - t0)

    async def _ring(
        self,
        ring: int,
        gws: list[cand.Candidate],
        dates: list[date],
        q: Query,
        main_reqs: list[SearchRequest],
        directs: list[Itinerary],
        best: float | None,
        report: RingReport,
    ) -> tuple[list[Itinerary], RingReport]:
        # 1. main legs first
        results = await self.backend.search_many(main_reqs, fresh=q.fresh)
        report.tasks += len(main_reqs)
        mains_by_gw: dict[str, list[AwardOption]] = {}
        for req in main_reqs:
            for o in results.get(req.key, []):
                if flt.option_ok(o, q.filters):
                    mains_by_gw.setdefault(req.origin, []).append(o)

        # 2. bound check
        survivors: dict[str, list[tuple[float, AwardOption]]] = {}
        for g in gws:
            priced = sorted(
                ((self._standalone(o, q), o) for o in mains_by_gw.get(g.iata, [])),
                key=lambda p: p[0],
            )
            if not priced or (best is not None and priced[0][0] >= best):
                report.pruned.append(g.iata)
                continue
            survivors[g.iata] = [p for p in priced if best is None or p[0] < best]

        # 3. positioning for survivors only
        pos_reqs: list[SearchRequest] = []
        for gw, priced in survivors.items():
            days = sorted({o.date for _, o in priced})
            need = sorted({d + timedelta(days=k) for d in days for k in (-1, 0)})
            for h in q.homes:
                if gw == h or cand.metro_siblings(h) & {gw}:
                    continue
                pos_reqs.extend(self._requests(h, gw, need, q))
        pos_results = await self.backend.search_many(pos_reqs, fresh=q.fresh) if pos_reqs else {}
        report.tasks += len(pos_reqs)

        # 4. stitch and price
        out: list[Itinerary] = []
        for gw, priced in survivors.items():
            mains = [o for _, o in priced]
            for h in q.homes:
                if gw == h or cand.metro_siblings(h) & {gw}:
                    continue
                opts = [
                    o
                    for r in pos_reqs
                    if r.origin == h and r.dest == gw
                    for o in pos_results.get(r.key, [])
                ]
                legs = self._positioning_options(h, gw, opts, q, min(o.date for o in mains))
                for it in st.stitch(legs, mains, gw, ring, self.s):
                    self._value(it, q)
                    if not st.dominated(it, directs, self.s.dominance_pct):
                        out.append(it)
        return out, report


def _span(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]
