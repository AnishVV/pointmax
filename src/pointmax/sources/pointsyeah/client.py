"""PointsYeah search client: encrypt, create_task, fetch_result, round-robin poller.

Request and response shapes are verified against recorded fixtures (tests/fixtures).

Recorded behaviour: results are drained (each poll returns a disjoint batch), `total_sub_tasks`
over-counts (54 announced, 51 summaries arrive), and every task ends its status sequence
"processing..., done, processing, done". So the primary stop rule is the SECOND `done` poll.
Fallbacks: summaries >= total and done; 3 empty polls after the first done; 4 minutes per task.
Cadence: first poll ~5 s after create, ~7 s apart until the first `done`, then ~2 s. Always
through the shared limiter.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from pointmax.ratelimit import RateLimiter
from pointmax.sources.base import SearchRequest
from pointmax.sources.pointsyeah import crypto, raw
from pointmax.sources.pointsyeah.session import SessionData, SessionError

log = logging.getLogger("pointmax.client")

API_BASE = "https://api2.pointsyeah.com"
CREATE_PATH = "/flight/search/create_task"
FETCH_PATH = "/flight/search/fetch_result"
ALL_CABINS = ["Economy", "Premium Economy", "Business", "First"]
FIRST_POLL_S, POLL_INTERVAL_S, AFTER_DONE_INTERVAL_S = 5.0, 7.0, 2.0
STOP_AT_DONE_POLLS = 2
QUIET_DONE_POLLS = 3
TASK_CAP_S = 240.0
RETRIES = 2
COOLDOWN_429_S = 60.0


class ApiError(RuntimeError):
    pass


def build_query(req: SearchRequest) -> dict[str, Any]:
    """The plaintext create_task query; key order matches the browser, byte for byte."""
    return {
        "search_type": req.search_type,
        "cabins": ALL_CABINS,
        "segments": [
            {
                "arrival": req.dest,
                "departure": req.origin,
                "departure_date": {"from": req.start.isoformat(), "to": req.end.isoformat()},
            }
        ],
        "passengers_v2": {"adults": req.pax, "children": 0},
        "source": "pc",
    }


@dataclass
class TaskState:
    request: SearchRequest
    task_id: str = ""
    total: int = 0
    polls: int = 0
    status: str = ""
    quiet_done: int = 0
    done_polls: int = 0
    summaries: set[tuple[str, ...]] = field(default_factory=set)
    routes: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    started: float = 0.0
    next_poll: float = 0.0
    stop_reason: str = ""
    error: str = ""

    @property
    def finished(self) -> bool:
        return bool(self.stop_reason or self.error)

    def absorb(self, status: str, items: list[dict[str, Any]]) -> None:
        self.status = status
        for item in items:
            key = raw.summary_key(item)
            self.summaries.add(key)
            for route in raw.item_routes(item):
                self.routes.setdefault(raw.route_key(route), route)
        if status == "done":
            self.done_polls += 1
        # empty polls once the first `done` has been seen
        self.quiet_done = self.quiet_done + 1 if self.done_polls and not items else 0


class PointsYeahClient:
    def __init__(
        self,
        session: SessionData,
        limiter: RateLimiter,
        *,
        http: httpx.AsyncClient | None = None,
        refresh: Callable[[], Awaitable[SessionData]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        on_exchange: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.session = session
        self.limiter = limiter
        self._http = http or httpx.AsyncClient(timeout=30)
        self._own_http = http is None
        self._refresh = refresh
        self._clock, self._sleep = clock, sleep
        self._progress = on_progress
        self._on_exchange = on_exchange  # raw request/response sink for --save-raw
        self._t0 = clock()
        self.requests_made = 0
        self.session_dead = False  # set once a refresh fails; later calls fail fast

    async def aclose(self) -> None:
        if self._own_http:
            await self._http.aclose()

    # ---- transport -----------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": self.session.user_agent,
            "Origin": "https://www.pointsyeah.com",
            "Referer": "https://www.pointsyeah.com/",
            "Cookie": self.session.cookie_header(),
        }

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        """One POST through the limiter, with 2 retries on network errors and 5xx."""
        last: Exception | None = None
        for attempt in range(RETRIES):
            await self.limiter.acquire()
            self.requests_made += 1
            try:
                resp = await self._http.post(API_BASE + path, json=body, headers=self._headers())
            except httpx.TransportError as e:
                last = e
            else:
                self._record(path, body, resp)
                if resp.status_code == 429:
                    log.warning("429 from PointsYeah: cooling down %.0fs", COOLDOWN_429_S)
                    self.limiter.cooldown(COOLDOWN_429_S)
                    last = ApiError("rate limited (429)")
                elif resp.status_code in (401, 403):
                    raise SessionError(f"HTTP {resp.status_code} from PointsYeah")
                elif resp.status_code >= 500:
                    last = ApiError(f"HTTP {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ApiError(f"HTTP {resp.status_code} from {path}")
                else:
                    return resp.json()
            await self._sleep(2.0 * (attempt + 1))
        raise ApiError(f"{path} failed after {RETRIES} tries: {last}")

    def _record(self, path: str, body: dict[str, Any], resp: httpx.Response) -> None:
        """Hand the raw exchange to the sink, in the format devtools.scrub reads."""
        if self._on_exchange is None:
            return
        self._on_exchange(
            {
                "t": round(self._clock() - self._t0, 3),
                "at": datetime.now(UTC).isoformat(),
                "method": "POST",
                "url": API_BASE + path,
                "status": resp.status_code,
                "request_headers": {
                    "user-agent": self.session.user_agent,
                    "origin": "https://www.pointsyeah.com",
                    "referer": "https://www.pointsyeah.com/",
                    "content-type": "application/json",
                },
                "request_body": json.dumps(body),
                "response_body": resp.text,
            }
        )

    async def create_task(self, req: SearchRequest) -> tuple[str, int]:
        enc = crypto.encrypt_query(build_query(req), self.session.request_key_section)
        # The browser's `data` is a different ciphertext under a bundle default key we have not
        # found; whether the server accepts `data == encrypted` is still untested live.
        body = await self._post(CREATE_PATH, {"data": enc, "encrypted": enc})
        if raw.response_code(body) != 0:
            msg = body.get("message") or body.get("msg") or "" if isinstance(body, dict) else ""
            raise SessionError(f"create_task returned code {raw.response_code(body)} {msg}".strip())
        return raw.parse_create(body)

    async def fetch_result(self, task_id: str) -> Any:
        return await self._post(FETCH_PATH, {"task_id": task_id})

    async def _with_refresh(self, call: Callable[[], Awaitable[Any]]) -> Any:
        """Run `call`; on a session error refresh once and retry, else mark the session dead."""
        if self.session_dead:
            raise SessionError("Session expired. Run `pointmax login`.")
        try:
            return await call()
        except SessionError:
            if self._refresh is None:
                self.session_dead = True
                raise
            try:
                self.session = await self._refresh()
                return await call()
            except SessionError:
                self.session_dead = True
                raise

    async def _create_with_refresh(self, req: SearchRequest) -> tuple[str, int]:
        return await self._with_refresh(lambda: self.create_task(req))

    # ---- poller --------------------------------------------------------------------------

    def _interval(self, t: TaskState) -> float:
        return AFTER_DONE_INTERVAL_S if t.done_polls else POLL_INTERVAL_S

    def _check_stop(self, t: TaskState) -> None:
        now = self._clock()
        all_in = t.status == "done" and t.total and len(t.summaries) >= t.total
        if t.done_polls >= STOP_AT_DONE_POLLS or all_in:
            t.stop_reason = "complete"
        elif t.quiet_done >= QUIET_DONE_POLLS:
            t.stop_reason = "quiet"
            log.warning(
                "%s: stopped on quiet polls with %d/%d summaries",
                t.request.label(),
                len(t.summaries),
                t.total,
            )
        elif now - t.started >= TASK_CAP_S:
            t.stop_reason = "cap"
            log.warning("%s: hit the %.0fs cap", t.request.label(), TASK_CAP_S)

    def _emit(self, tasks: list[TaskState]) -> None:
        if self._progress:
            self._progress(
                {
                    "open": sum(not t.finished for t in tasks),
                    "done": sum(t.finished for t in tasks),
                    "polls": sum(t.polls for t in tasks),
                    "remaining": self.limiter.remaining(),
                }
            )

    async def run_tasks(self, requests: list[SearchRequest]) -> list[TaskState]:
        """Create every task, then poll all open ones round-robin under one limiter."""
        tasks = [TaskState(request=r) for r in requests]
        for t in tasks:
            try:
                t.task_id, t.total = await self._create_with_refresh(t.request)
            except SessionError as e:
                for rest in tasks:
                    if not rest.task_id:
                        rest.error = str(e)
                break
            except (ApiError, ValueError) as e:
                t.error = str(e)
                continue
            t.started = self._clock()
            t.next_poll = t.started + FIRST_POLL_S
            self._emit(tasks)

        while True:
            open_tasks = [t for t in tasks if not t.finished]
            if not open_tasks:
                break
            t = min(open_tasks, key=lambda x: x.next_poll)
            if (wait := t.next_poll - self._clock()) > 0:
                await self._sleep(wait)
            try:
                body = await self._with_refresh(lambda tid=t.task_id: self.fetch_result(tid))
            except SessionError as e:
                for rest in open_tasks:
                    rest.error = str(e)
                break
            except ApiError as e:
                t.error = str(e)
                continue
            t.polls += 1
            status, items = raw.parse_fetch(body)
            t.absorb(status, items)
            t.next_poll = self._clock() + self._interval(t)
            self._check_stop(t)
            self._emit(tasks)
        return tasks
