# Things to verify against live data

The API shapes are now verified against recorded fixtures (first section). Hubs and
cents-per-point defaults now follow the reference docs (second section). The rest is still
best-knowledge defaults.

## Confirmed from recorded fixtures (2026-10-03, tests/fixtures)

Verified against three recordings (dfw-lhr, dfw-amd, multi-city) and covered by `tests/test_recorded.py`.

| Area | Finding | Where |
| --- | --- | --- |
| create_task plaintext | `search_type`, `cabins`, `segments[{arrival, departure, departure_date{from,to}}]`, `passengers_v2{adults, children}` (no infants), `source: "pc"`. `build_query` is byte-identical to the browser's | `client.build_query` |
| Cipher | Our compact serialization and AES-CBC reproduce the browser's ciphertext (`browser_byte_match`, `reencrypt_match`); an 8-char section gives AES-256 | `crypto`, `test_crypto.test_known_answer` |
| create_task response | `{code, success, data{task_id, total_sub_tasks, status: "created"}}` | `raw.parse_create` |
| fetch_result | `{code, success, data{result[], status}}`; results are drained: polls return disjoint batches | `raw.parse_fetch` |
| Stop rule | `total_sub_tasks` over-counts (54 announced, 51 summaries), so "summaries == total" never fires. Every task ends `done, processing, done`; we stop at the second `done`. First `done` at about 32 s | `client._check_stop` |
| Cadence | Slower polling loses nothing (batches are drained). Now 5 s, then 7 s, then 2 s after the first `done`; about 6 polls per search instead of the browser's 37 | `client` constants |
| Summary | one per program-date: `program, code, date, departure, arrival, routes[]`, optional `cost` (meaning unknown, ignored) | `raw.summary_key` |
| Route | no date/origin/dest of its own: date comes from the summary, origin/dest from the first and last segment (`da`, `aa`) | `raw.item_routes`, `normalize` |
| Route fields | `payment{currency, tax, miles, cabin, unit, short_unit, seats, cash_price}`, `segments[{duration, flight_number, aircraft, dt, da, at, aa, layover, cabin}]`, `transfer[{bank, actual_points, points, bonus_percentage, bonus_end_date (epoch s), bonus_slogn, url, code}]`, `promotion{description, url}`, `duration`, `cross_days`, `premium_cabin_percentage`, `url`, `cash_ticket_url`, `extra` | `raw.RawRoute` |
| Units and quirks | durations are minutes (floats allowed) and route `duration` is real elapsed time; `seats` is an int or a string, 9999 = not live; `cash_price` 0 = unknown; currency always USD; `premium_cabin_percentage` is a float and 0 on all-Business routes | `normalize` |
| Segment cabin | sometimes a fare brand ("Main Basic", "Blue", "Comfort") under headline Economy; unparseable ones fall back to the headline cabin | `models.Cabin`, `filters.cabin_ok` |
| Alternate airports | a DFW search also returns DAL; an LHR search rarely returns LGW/LCY; metro siblings do appear | `geo/hubs.METRO_GROUPS` |
| Names | banks: Bilt, Chase Ultimate Rewards, American Exp Membership Rewards, Capital One, Citi ThankYou, US Bank, WF. 17 programs seen, e.g. "Air Canada Aeroplan", "Air France/KLM Flying Blue" | `config [cpp]` |

## Taken from the reference docs (2026-10-03)

| Area | Source | Where |
| --- | --- | --- |
| US alliance hubs: added LGA, CVG, PDX, SAN, ANC; SFO is Star Alliance only | hubs-alliances-carriers.md | `geo/hubs.US_ALLIANCE_HUBS` |
| Stopover hubs (KEF, IST, DXB, DOH, AUH, SIN, PTY, LIS) | reference README, rule 9 | `geo/hubs.STOPOVER_HUBS` |
| Cents-per-point baselines for 5 banks and 11 programs (Sept. 2026 snapshot, re-pull monthly) | point-valuations-and-transfer-partners.md | `config [cpp]` |

## Still unverified

| Area | Assumption | Where | How to confirm |
| --- | --- | --- | --- |
| `/api/auth/session` fields | `isAuthenticated`, `requestKeySection`, `userId`, `maxDateRange`, found anywhere in the JSON | `session.parse_auth` | `pointmax status` after login |
| `data` field | sent equal to `encrypted`. The browser sends a different 256-byte ciphertext of (probably) the same plaintext under a bundle default key we have not found; obvious defaults did not match. Stored as `live_data_ciphertext` in the KAT | `client.create_task` | first live search; if rejected, find bundle module `i.GI` (`devtools/find_data_key.py`) |
| Summary `cost` | float on 91 route-less items; meaning unknown, ignored | `raw` | compare with the site UI |
| Per-person vs total pricing for `--pax 2` | assumed per person | `normalize`, `value` | record a 2-adult search |
| Bank and program names | cpp keys now match the recorded names; a program not listed uses the 1.2c default and adds a `default-cpp` note | `config [cpp]` | notes on a real run |

## Open questions the code assumes

- Whether the free plan has a daily search quota: no handling yet.
- Which login path works: `pointmax login` tries Chrome automation, `--from-chrome` imports cookies. Neither has been run. Session lifetime unknown.

## Defaults I made up

- `config.DEFAULT_TOML`: WF and US Bank cents-per-point (not in the valuations doc), distance bands, hotel allowance (150), drive cost per km, buffers (3 h, 4 h, 24 h; the README only says 3–4+ h). Review before trusting rankings.
- `geo/hubs.py`: destination alternates, metro groups, and the YUL/YVR/MEX gateways (the doc names only YYZ).
- Ring scoring weights in `planner/candidates.py` (connection signal x3, +1 for large airports, distance penalty 1 per 1000 km).
- Request budget: 10 requests per minute (the 50 per 5 min limit) for time quotes.

## Not built yet

- Positioning for the return leg: `--return` runs a direct-only search.
- Ring 3 alternate destinations with a `position_in` leg: `alternate_destinations()` exists but the planner does not use it.
- `pointmax login` has never opened a real browser; `silent_refresh` likewise.
- Extracting the default `data` key: `devtools/find_data_key.py` only prints bundle code, and has never reached the live site.
- The live tests (`pytest -m live`) are written but have never run.
