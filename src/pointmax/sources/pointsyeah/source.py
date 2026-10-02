"""PointsYeah backend for the planner: cache first, then the client, then normalize."""

import time

from pointmax.cache import Cache
from pointmax.models import AwardOption
from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah.client import PointsYeahClient
from pointmax.sources.pointsyeah.normalize import normalize_routes
from pointmax.sources.pointsyeah.raw import SchemaWarnings

DEFAULT_MAX_DATE_RANGE = 4  # free plan, one-way


class PointsYeahBackend:
    name = "pointsyeah"

    def __init__(self, client: PointsYeahClient, cache: Cache, max_date_range: int | None = None):
        self.client, self.cache = client, cache
        self.max_date_range = max_date_range or DEFAULT_MAX_DATE_RANGE
        self.warnings = SchemaWarnings()
        self.cache_hits = 0
        self.live_searches = 0
        self.failures: list[str] = []

    def avg_polls_per_task(self) -> float:
        return self.cache.avg_polls_per_task()

    async def search_many(
        self, requests: list[SearchRequest], *, fresh: bool = False
    ) -> dict[str, list[AwardOption]]:
        out: dict[str, list[AwardOption]] = {}
        misses: list[SearchRequest] = []
        for r in requests:
            cached = self.cache.get(r, fresh=fresh)
            if cached is None:
                misses.append(r)
            else:
                out[r.key] = cached
                self.cache_hits += 1
        if misses:
            started = time.monotonic()
            tasks = await self.client.run_tasks(misses)
            elapsed = time.monotonic() - started
            for t in tasks:
                if t.error:
                    self.failures.append(f"{t.request.label()}: {t.error}")
                    out[t.request.key] = []
                    continue
                options = normalize_routes(list(t.routes.values()), self.warnings)
                self.cache.put(t.request, options)
                self.cache.record_task(t.polls, elapsed / max(len(tasks), 1))
                out[t.request.key] = options
                self.live_searches += 1
        return out
