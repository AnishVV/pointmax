"""Dual sliding-window rate limiter (10 per 30 s, 50 per 5 min) behind one `acquire()`.

Timestamps can persist in SQLite so back-to-back CLI runs share one budget. The clock and
sleep are injectable so tests drive 200 acquires on a fake clock.
"""

import asyncio
import sqlite3
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path

DEFAULT_WINDOWS: tuple[tuple[int, float], ...] = ((10, 30.0), (50, 300.0))


class RateLimiter:
    def __init__(
        self,
        windows: tuple[tuple[int, float], ...] = DEFAULT_WINDOWS,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        db_path: Path | None = None,
        key: str = "pointsyeah",
    ) -> None:
        self.windows = windows
        self._clock = clock
        self._sleep = sleep
        self._key = key
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._db: sqlite3.Connection | None = None
        self.waits: list[float] = []  # seconds slept per acquire, for --verbose and tests
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(db_path)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS rate_stamps (key TEXT NOT NULL, ts REAL NOT NULL)"
            )
            self._db.execute("CREATE INDEX IF NOT EXISTS rate_stamps_key ON rate_stamps (key, ts)")
            self._load()

    @property
    def horizon(self) -> float:
        return max(w for _, w in self.windows)

    def _load(self) -> None:
        assert self._db is not None
        cutoff = self._clock() - self.horizon
        self._db.execute("DELETE FROM rate_stamps WHERE key = ? AND ts < ?", (self._key, cutoff))
        self._db.commit()
        rows = self._db.execute(
            "SELECT ts FROM rate_stamps WHERE key = ? ORDER BY ts", (self._key,)
        ).fetchall()
        self._stamps.extend(ts for (ts,) in rows)

    def _prune(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= self.horizon:
            self._stamps.popleft()

    def _delay(self, now: float) -> float:
        """Seconds until a request is allowed in every window (0 if allowed now)."""
        delay = 0.0
        for limit, span in self.windows:
            recent = [t for t in self._stamps if now - t < span]
            if len(recent) >= limit:
                delay = max(delay, recent[-limit] + span - now)
        return delay

    def remaining(self) -> list[tuple[int, float, int]]:
        """(limit, window seconds, requests left) per window, as of now."""
        now = self._clock()
        self._prune(now)
        return [
            (limit, span, limit - sum(1 for t in self._stamps if now - t < span))
            for limit, span in self.windows
        ]

    def cooldown(self, seconds: float) -> None:
        """After a 429: pretend every window is full until `seconds` from now."""
        now = self._clock()
        for _ in range(max(limit for limit, _ in self.windows)):
            self._record(now + seconds - self.horizon)

    def _record(self, ts: float) -> None:
        self._stamps.append(ts)
        if self._db is not None:
            self._db.execute("INSERT INTO rate_stamps (key, ts) VALUES (?, ?)", (self._key, ts))
            self._db.commit()

    async def acquire(self) -> float:
        """Wait until a request is allowed, record it, return seconds waited."""
        async with self._lock:
            waited = 0.0
            while True:
                now = self._clock()
                self._prune(now)
                delay = self._delay(now)
                if delay <= 0:
                    break
                await self._sleep(delay)
                waited += delay
            self._record(self._clock())
            self.waits.append(waited)
            return waited

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
