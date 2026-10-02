"""Regenerate src/pointmax/data/airports.csv from the OurAirports public-domain dataset.

    uv run python scripts/update_airports.py

Keeps large and medium airports that have an IATA code, and only the columns pointmax uses.
"""

import csv
import io
from pathlib import Path

import httpx

SOURCE = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
OUT = Path(__file__).resolve().parents[1] / "src" / "pointmax" / "data" / "airports.csv"
COLUMNS = [
    "iata_code", "ident", "type", "name", "latitude_deg", "longitude_deg",
    "iso_country", "iso_region", "municipality", "scheduled_service",
]  # fmt: skip
TYPES = {"large_airport", "medium_airport"}


def main() -> None:
    text = httpx.get(SOURCE, timeout=60, follow_redirects=True).raise_for_status().text
    rows = [
        r
        for r in csv.DictReader(io.StringIO(text))
        if r["iata_code"].strip() and r["type"] in TYPES
    ]
    rows.sort(key=lambda r: r["iata_code"])
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} airports to {OUT}")


if __name__ == "__main__":
    main()
