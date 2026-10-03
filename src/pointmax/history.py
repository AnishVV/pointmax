"""Search history: every `pointmax search` run and its ranked results, kept in SQLite.

Lives next to the cache in the config dir (never in the repo). Unlike the cache it has no TTL:
it is the record to compare routes, dates and programs across runs. One row per run (the query),
one row per ranked itinerary (flattened for SQL/CSV, plus the full itinerary JSON).
"""

import csv
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pointmax.models import Itinerary
from pointmax.planner.plan import Query, SearchResult

MAX_RESULTS_PER_RUN = 100

RUN_COLUMNS = [
    "run_id",
    "at",
    "leg",
    "parent_id",
    "status",
    "origins",
    "dest",
    "depart_start",
    "depart_end",
    "cabin",
    "pax",
    "rings",
    "sort",
    "n_results",
    "best_eff_usd",
    "best_program",
    "searches",
    "elapsed_s",
]

RESULT_COLUMNS = [
    "rank",
    "route",
    "gateway",
    "ring",
    "depart_date",
    "program",
    "origin",
    "dest",
    "cabin",
    "miles",
    "taxes_usd",
    "positioning_usd",
    "effective_usd",
    "cpp",
    "funding",
    "stops",
    "duration_min",
    "flights",
    "flags",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    leg TEXT NOT NULL DEFAULT 'outbound',
    parent_id INTEGER REFERENCES runs(run_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'ok',
    origins TEXT NOT NULL,
    dest TEXT NOT NULL,
    depart_start TEXT NOT NULL,
    depart_end TEXT NOT NULL,
    cabin TEXT NOT NULL DEFAULT '',
    pax INTEGER NOT NULL DEFAULT 1,
    rings INTEGER NOT NULL DEFAULT 0,
    sort TEXT NOT NULL DEFAULT 'eff',
    filters TEXT NOT NULL DEFAULT '{}',
    n_results INTEGER NOT NULL DEFAULT 0,
    best_eff_usd REAL,
    best_program TEXT,
    searches INTEGER NOT NULL DEFAULT 0,
    elapsed_s REAL NOT NULL DEFAULT 0,
    ring_report TEXT NOT NULL DEFAULT '[]',
    warnings TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS results (
    run_id INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    route TEXT NOT NULL,
    gateway TEXT,
    ring INTEGER NOT NULL,
    depart_date TEXT NOT NULL,
    program TEXT NOT NULL,
    origin TEXT NOT NULL,
    dest TEXT NOT NULL,
    cabin TEXT NOT NULL,
    miles INTEGER NOT NULL,
    taxes_usd REAL NOT NULL,
    positioning_usd REAL,
    effective_usd REAL NOT NULL,
    cpp REAL,
    funding TEXT NOT NULL DEFAULT '',
    stops INTEGER NOT NULL,
    duration_min INTEGER NOT NULL,
    flights TEXT NOT NULL DEFAULT '',
    flags TEXT NOT NULL DEFAULT '',
    itinerary TEXT NOT NULL,
    PRIMARY KEY (run_id, rank));
CREATE INDEX IF NOT EXISTS runs_route ON runs (dest, origins);
CREATE INDEX IF NOT EXISTS results_program ON results (program);
"""


@dataclass
class RunFilter:
    origin: str | None = None  # matches any of a run's origins
    dest: str | None = None
    cabin: str | None = None
    program: str | None = None  # runs with at least one result in this program
    since: str | None = None  # YYYY-MM-DD, on the run time
    limit: int | None = None

    def where(self) -> tuple[str, list[Any]]:
        sql, args = ["1=1"], []
        if self.origin:
            sql.append("(',' || r.origins || ',') LIKE ?")
            args.append(f"%,{self.origin.upper()},%")
        if self.dest:
            sql.append("r.dest = ?")
            args.append(self.dest.upper())
        if self.cabin:
            sql.append("r.cabin = ?")
            args.append(self.cabin.lower())
        if self.program:
            sql.append(
                "EXISTS (SELECT 1 FROM results x WHERE x.run_id = r.run_id"
                " AND x.program LIKE ? COLLATE NOCASE)"
            )
            args.append(f"%{self.program}%")
        if self.since:
            sql.append("substr(r.at, 1, 10) >= ?")
            args.append(self.since)
        return " AND ".join(sql), args


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def flatten(it: Itinerary, rank: int) -> dict[str, Any]:
    """One result row: the main award leg plus the itinerary's effective cost."""
    assert it.value is not None
    main = it.main
    main_lv = next(lv for lv, r in zip(it.value.legs, it.roles, strict=True) if r == "main")
    pos = it.value.c_eff - main_lv.total_usd if it.gateway else None
    first = it.legs[0]
    return {
        "rank": rank,
        "route": f"{first.origin}→[{it.gateway}]→{main.dest}"
        if it.gateway
        else f"{main.origin}→{main.dest}",
        "gateway": it.gateway,
        "ring": it.ring,
        "depart_date": main.date.isoformat(),
        "program": main.program,
        "origin": first.origin,
        "dest": main.dest,
        "cabin": main.cabin,
        "miles": main.miles,
        "taxes_usd": round(sum(o.taxes_usd for o in it.award_legs), 2),
        "positioning_usd": round(pos, 2) if pos is not None else None,
        "effective_usd": round(it.value.c_eff, 2),
        "cpp": round(main_lv.redemption_cpp, 2) if main_lv.redemption_cpp else None,
        "funding": main_lv.funding,
        "stops": main.stops,
        "duration_min": main.duration_min,
        "flights": " ".join(main.flight_numbers),
        "flags": " ".join(sorted(main.flags)),
    }


class History:
    def __init__(self, path: Path | str, clock: Callable[[], str] = _now) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)
        self._clock = clock

    def record(
        self,
        q: Query,
        res: SearchResult,
        ranked: list[Itinerary],
        *,
        sort: str = "eff",
        leg: str = "outbound",
        parent_id: int | None = None,
        status: str = "ok",
    ) -> int:
        f = q.filters
        filters = {
            "min_premium": f.min_premium,
            "max_stops": f.max_stops,
            "max_hours": f.max_hours,
            "max_taxes": f.max_taxes,
            "no_redeye": f.no_redeye,
            "no_overnight": f.no_overnight,
            "no_self_transfer": f.no_self_transfer,
            "fresh": q.fresh,
        }
        rings = [
            {
                "ring": r.ring,
                "gateways": r.gateways,
                "pruned": r.pruned,
                "tasks": r.tasks,
                "best_after": r.best_after,
                "stopped": r.stopped,
            }
            for r in res.rings
        ]
        best = ranked[0] if ranked else None
        cur = self._db.execute(
            "INSERT INTO runs (at, leg, parent_id, status, origins, dest, depart_start,"
            " depart_end, cabin, pax, rings, sort, filters, n_results, best_eff_usd,"
            " best_program, searches, elapsed_s, ring_report, warnings)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._clock(),
                leg,
                parent_id,
                status,
                ",".join(q.homes),
                q.dest,
                q.start.isoformat(),
                q.end.isoformat(),
                f.cabin.name.lower() if f.cabin else "",
                q.pax,
                q.rings,
                sort,
                json.dumps(filters),
                len(ranked),
                round(best.value.c_eff, 2) if best and best.value else None,
                best.main.program if best else None,
                sum(r.tasks for r in res.rings),
                round(res.elapsed_s, 1),
                json.dumps(rings),
                json.dumps(res.warnings),
            ),
        )
        run_id = int(cur.lastrowid or 0)
        rows = [
            {**flatten(it, n), "run_id": run_id, "itinerary": it.model_dump_json()}
            for n, it in enumerate(ranked[:MAX_RESULTS_PER_RUN], 1)
            if it.value is not None
        ]
        if rows:
            cols = ["run_id", *RESULT_COLUMNS, "itinerary"]
            self._db.executemany(
                f"INSERT INTO results ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [[r[c] for c in cols] for r in rows],
            )
        self._db.commit()
        return run_id

    def runs(self, flt: RunFilter | None = None) -> list[dict[str, Any]]:
        flt = flt or RunFilter()
        where, args = flt.where()
        sql = f"SELECT r.* FROM runs r WHERE {where} ORDER BY r.run_id DESC"
        if flt.limit:
            sql += " LIMIT ?"
            args.append(flt.limit)
        return [dict(row) for row in self._db.execute(sql, args)]

    def run(self, run_id: int) -> dict[str, Any] | None:
        row = self._db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def itineraries(self, run_id: int) -> list[Itinerary]:
        rows = self._db.execute(
            "SELECT itinerary FROM results WHERE run_id = ? ORDER BY rank", (run_id,)
        )
        return [Itinerary.model_validate_json(r[0]) for r in rows]

    def export_csv(
        self, path: Path, flt: RunFilter | None = None, *, runs_only: bool = False
    ) -> int:
        """Write runs (one row each) or results joined with their run's query. Returns row count."""
        flt = flt or RunFilter()
        where, args = flt.where()
        run_cols = ", ".join(f"r.{c}" for c in RUN_COLUMNS)
        if runs_only:
            cols = RUN_COLUMNS
            sql = f"SELECT {run_cols} FROM runs r WHERE {where} ORDER BY r.run_id"
        else:
            cols = RUN_COLUMNS + [f"result_{c}" if c in RUN_COLUMNS else c for c in RESULT_COLUMNS]
            res_cols = ", ".join(f"x.{c}" for c in RESULT_COLUMNS)
            if flt.program:  # only that program's rows, not every result of matching runs
                where += " AND x.program LIKE ? COLLATE NOCASE"
                args.append(f"%{flt.program}%")
            sql = (
                f"SELECT {run_cols}, {res_cols} FROM runs r JOIN results x"
                f" ON x.run_id = r.run_id WHERE {where} ORDER BY r.run_id, x.rank"
            )
        rows = self._db.execute(sql, args).fetchall()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows(tuple(r) for r in rows)
        return len(rows)

    def delete(self, run_id: int) -> bool:
        cur = self._db.execute("DELETE FROM runs WHERE run_id = ? OR parent_id = ?", (run_id,) * 2)
        self._db.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._db.close()
