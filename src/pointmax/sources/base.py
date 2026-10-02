"""AwardSource protocol and the source-agnostic search request."""

import hashlib
from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel

from pointmax.models import AwardOption


class SearchRequest(BaseModel):
    origin: str
    dest: str
    start: date
    end: date  # inclusive; one task covers at most the plan's max date range
    search_type: Literal["one_way", "multi_city"] = "one_way"
    pax: int = 1

    @property
    def key(self) -> str:
        raw = f"{self.search_type}|{self.origin}|{self.dest}|{self.start}|{self.end}|{self.pax}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def label(self) -> str:
        span = str(self.start) if self.start == self.end else f"{self.start}..{self.end}"
        return f"{self.origin}->{self.dest} {span}"


class AwardSource(Protocol):
    name: str

    async def search(self, request: SearchRequest) -> list[AwardOption]: ...


def chunk_dates(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """Split [start, end] into windows of at most `max_days` days (e.g. 7 days, max 4 -> 4 + 3)."""
    from datetime import timedelta

    out, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=max_days - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out
