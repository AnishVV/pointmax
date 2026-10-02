"""Find the default `data` key constant in PointsYeah's Next.js bundle (plan: module 59807, i.GI).

    uv run python -m pointmax.devtools.find_data_key

Fetches the homepage, downloads every /_next/static script it references and prints the text
around `59807` and `GI` so you can read the constant. Untested against the live site (it was
unreachable from where this was written); the patterns are a starting point, not a guarantee.
"""

import re
import sys

import httpx

BASE = "https://www.pointsyeah.com"
SCRIPT = re.compile(r'(?:src|href)="(/_next/static/[^"]+\.js)"')
MARKERS = (r"59807", r"\bGI\b", r"LefjQ2pEXmiy")


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        html = c.get(BASE + "/").raise_for_status().text
        scripts = sorted(set(SCRIPT.findall(html)))
        print(f"{len(scripts)} scripts on the homepage", file=sys.stderr)
        for path in scripts:
            text = c.get(BASE + path).text
            for marker in MARKERS:
                for m in re.finditer(marker, text):
                    lo, hi = max(0, m.start() - 160), min(len(text), m.end() + 240)
                    print(f"--- {path} [{marker}] @ {m.start()}\n{text[lo:hi]}\n")
                    break  # first hit per marker per file is enough to locate it


if __name__ == "__main__":
    main()
