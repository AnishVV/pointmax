from pointmax.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += s


async def _run(n, **kw):
    clock = FakeClock()
    rl = RateLimiter(clock=clock, sleep=clock.sleep, **kw)
    stamps = []
    for _ in range(n):
        await rl.acquire()
        stamps.append(clock.t)
    return rl, clock, stamps


def _max_in_window(stamps, span):
    return max(sum(1 for t in stamps if s <= t < s + span) for s in stamps)


async def test_200_acquires_respect_both_windows():
    _, _, stamps = await _run(200)
    assert _max_in_window(stamps, 30) <= 10
    assert _max_in_window(stamps, 300) <= 50


async def test_burst_then_wait():
    _, _, stamps = await _run(11)
    assert stamps[9] == stamps[0]  # first 10 are immediate
    assert stamps[10] - stamps[0] >= 30  # the 11th waits out the 30 s window


async def test_cooldown_blocks():
    clock = FakeClock()
    rl = RateLimiter(clock=clock, sleep=clock.sleep)
    rl.cooldown(60)
    start = clock.t
    await rl.acquire()
    assert clock.t - start >= 59


async def test_persists_across_instances(tmp_path):
    db = tmp_path / "rl.sqlite"
    clock = FakeClock()
    a = RateLimiter(clock=clock, sleep=clock.sleep, db_path=db)
    for _ in range(10):
        await a.acquire()
    a.close()
    b = RateLimiter(clock=clock, sleep=clock.sleep, db_path=db)
    start = clock.t
    await b.acquire()
    assert clock.t - start >= 29  # second run inherits the full 30 s window
    b.close()


async def test_remaining():
    clock = FakeClock()
    rl = RateLimiter(clock=clock, sleep=clock.sleep)
    await rl.acquire()
    assert [r for _, _, r in rl.remaining()] == [9, 49]
