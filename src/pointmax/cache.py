"""SQLite cache: request key -> normalized options with a TTL, plus poll statistics."""

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from pointmax.models import AwardOption
from pointmax.sources.base import SearchRequest


class Cache:
    def __init__(
        self,
        path: Path | str,
        ttl_hours: float = 6.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._ttl = ttl_hours * 3600
        self._clock = clock
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS searches (
                key TEXT PRIMARY KEY, label TEXT NOT NULL, fetched_at REAL NOT NULL,
                options TEXT NOT NULL, n INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS task_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                polls INTEGER NOT NULL, seconds REAL NOT NULL);
            """
        )

    def get(self, req: SearchRequest, *, fresh: bool = False) -> list[AwardOption] | None:
        if fresh:
            return None
        row = self._db.execute(
            "SELECT fetched_at, options FROM searches WHERE key = ?", (req.key,)
        ).fetchone()
        if row is None or self._clock() - row[0] > self._ttl:
            return None
        import json

        return [AwardOption.model_validate(o) for o in json.loads(row[1])]

    def put(self, req: SearchRequest, options: list[AwardOption]) -> None:
        payload = "[" + ",".join(o.model_dump_json() for o in options) + "]"
        self._db.execute(
            "INSERT OR REPLACE INTO searches (key, label, fetched_at, options, n) "
            "VALUES (?, ?, ?, ?, ?)",
            (req.key, req.label(), self._clock(), payload, len(options)),
        )
        self._db.commit()

    def record_task(self, polls: int, seconds: float) -> None:
        self._db.execute(
            "INSERT INTO task_stats (at, polls, seconds) VALUES (?, ?, ?)",
            (self._clock(), polls, seconds),
        )
        self._db.commit()

    def avg_polls_per_task(self, default: float = 6.0, last: int = 50) -> float:
        rows = self._db.execute(
            "SELECT polls FROM task_stats ORDER BY id DESC LIMIT ?", (last,)
        ).fetchall()
        return sum(r[0] for r in rows) / len(rows) if rows else default

    def stats(self) -> dict[str, float]:
        n, opts = self._db.execute("SELECT COUNT(*), COALESCE(SUM(n), 0) FROM searches").fetchone()
        return {"searches": n, "options": opts, "stale_after_hours": self._ttl / 3600}

    def clear(self) -> int:
        n = self._db.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
        self._db.execute("DELETE FROM searches")
        self._db.commit()
        return n

    def close(self) -> None:
        self._db.close()
