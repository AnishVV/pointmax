"""Record PointsYeah traffic from a real Chrome window, for test fixtures.

    uv run python -m pointmax.devtools.record [--out captures]

Opens Chrome with the pointmax profile. Log in, run the searches you want recorded, wait for
each to finish, then press Enter here. Raw traffic (which includes account identifiers) goes to
`captures/<timestamp>/traffic.jsonl`, which is git-ignored; run `pointmax.devtools.scrub` on it
to produce committable fixtures.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from pointmax.config import chrome_profile_dir

WATCHED = (
    "/flight/search/create_task",
    "/flight/search/fetch_result",
    "/api/auth/session",
)
KEPT_REQUEST_HEADERS = ("user-agent", "origin", "referer", "content-type")


async def record(out_dir: Path) -> Path:
    from playwright.async_api import async_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "traffic.jsonl"
    t0 = time.monotonic()
    count = 0

    async with async_playwright() as pw:
        profile = chrome_profile_dir()
        profile.mkdir(parents=True, exist_ok=True)
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel="chrome",
            headless=False,
            ignore_default_args=["--enable-automation"],
        )
        with path.open("a", encoding="utf-8") as fh:

            async def on_response(resp) -> None:
                nonlocal count
                if not any(w in resp.url for w in WATCHED):
                    return
                req = resp.request
                try:
                    body = await resp.text()
                except Exception as e:  # body gone after navigation
                    body = f"<unavailable: {e}>"
                entry = {
                    "t": round(time.monotonic() - t0, 3),
                    "at": datetime.now(UTC).isoformat(),
                    "method": req.method,
                    "url": resp.url,
                    "status": resp.status,
                    "request_headers": {
                        k: v for k, v in req.headers.items() if k in KEPT_REQUEST_HEADERS
                    },
                    "request_body": req.post_data,
                    "response_body": body,
                }
                fh.write(json.dumps(entry) + "\n")
                fh.flush()
                count += 1
                print(f"  captured {req.method} {resp.url.split('?')[0]} ({resp.status})")

            ctx.on("response", on_response)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto("https://www.pointsyeah.com/")
            print("Log in and run your searches. Press Enter here when every search has finished.")
            await asyncio.get_running_loop().run_in_executor(None, input)
            await ctx.close()

    print(f"{count} responses written to {path}")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("captures"))
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    asyncio.run(record(args.out / stamp))


if __name__ == "__main__":
    main()
