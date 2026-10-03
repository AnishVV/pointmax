# pointmax

A command-line tool that finds the cheapest-in-real-terms way to fly somewhere on points,
including itineraries that start with a separately ticketed positioning flight. It runs on
PointsYeah's internal API with your own account.

Status: **built offline, not yet run against PointsYeah.** Login, client, ranking, positioning
planner and CLI exist and are tested against synthetic data; every API field name is a guess
until fixtures are recorded. See [docs/UNVERIFIED.md](docs/UNVERIFIED.md) and the
[implementation plan](https://claude.ai/code/artifact/fd699a9c-7d0c-4bbe-b4ad-510ad4837329).

```sh
uv run pointmax login                       # or: login --from-chrome
uv run pointmax search home LHR --date 2026-12-23 --flex 2 --cabin business
uv run pointmax show 1
```

## Search history

Every `search` is logged with its query and ranked results to `~/.config/pointmax/history.sqlite`
(next to the cache, never in the repo; no expiry), so you can compare routes, dates and
programs across runs.

```sh
uv run pointmax history list --to LHR --cabin business   # past runs, best effective cost
uv run pointmax history show 12                          # its results; then `show N` works
uv run pointmax history export runs.csv                  # one row per result (--runs: per run)
uv run pointmax history delete 12
```

Filters on `list` and `export`: `--from`, `--to`, `--cabin`, `--program`, `--since YYYY-MM-DD`.
The file is plain SQLite (tables `runs` and `results`), so `sqlite3` or pandas can query it too.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Google Chrome.

```sh
uv sync
uv run pointmax --help
```

## Development

```sh
scripts/check.sh           # lint, format check, offline tests (run before every push)
uv run pytest -m live      # live tests; need a PointsYeah session (from M1)
```

### Recording fixtures

Offline tests replay real, scrubbed PointsYeah responses from `tests/fixtures/`.

1. `uv run python -m pointmax.devtools.record` opens Chrome with the pointmax profile
   (`~/.config/pointmax/chrome-profile`). Log in, then run these searches in the PointsYeah UI,
   letting each finish:
   - DFW → LHR, one-way, any cabin
   - DFW → AMD, one-way
   - one multi-city search with 2 segments (e.g. AUS → IAH, IAH → LHR)

   Press Enter in the terminal when done. Raw traffic lands in `captures/<timestamp>/`, which is
   git-ignored because it holds account identifiers.
2. `uv run python -m pointmax.devtools.scrub captures/<timestamp> --labels dfw-lhr,dfw-amd,multi`
   writes one folder per search to `tests/fixtures/` plus `crypto_kat.json`. It decrypts each
   live query with your session key, checks our serialization matches the browser byte for byte,
   strips account identifiers, and re-encrypts the known-answer pair under a dummy key. It refuses
   to finish if any identifier survives.
3. Look over `git diff tests/fixtures`, then commit.

### Airport data

`src/pointmax/data/airports.csv` is an extract of the public-domain
[OurAirports](https://ourairports.com/data/) dataset (large and medium airports with an IATA
code). Refresh it with `uv run python scripts/update_airports.py`.

## Layout

```
src/pointmax/
  cli.py, config.py, models.py, cache.py, history.py, ratelimit.py
  sources/pointsyeah/   session, crypto, client, raw, normalize
  geo/                  airports (OurAirports, haversine, nearby), hubs
  planner/              candidates, plan, stitch
  rank/                 value
  render/               table, export
  devtools/             fixture recorder and scrubber
tests/fixtures/         recorded, scrubbed PointsYeah responses
```

Secrets never enter the repo. The session lives in `~/.config/pointmax/session.json` (mode 600).

### Capturing fixtures from the CLI itself

`pointmax search ... --save-raw captures/run1` writes the raw API traffic (unscrubbed) in the
same format the browser recorder produces, so `devtools.scrub captures/run1` works on it. That
exercises our own client end to end, but the browser recorder remains the ground truth for the
query shape: our own queries would otherwise only confirm what we already guessed.
`uv run python -m pointmax.devtools.find_data_key` prints the bundle code around the `data` key
constant so it can be read by hand.
