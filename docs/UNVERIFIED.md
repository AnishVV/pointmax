# Things to verify against live data

Everything below was built without recorded fixtures or the reference docs, using the plan's
recon notes and best-knowledge defaults. Each item names where it lives and how to confirm it.
Record fixtures first (README, "Recording fixtures"); most items are then a diff away.

## PointsYeah API shapes (all guesses)

| Area | Guess | Where | How to confirm |
| --- | --- | --- | --- |
| `/api/auth/session` fields | `isAuthenticated`, `requestKeySection`, `userId`, `maxDateRange`, found anywhere in the JSON | `session.parse_auth` | `pointmax status` after login; compare with the recorded response |
| create_task plaintext | `search_type`, `cabins` (4 names), `passengers_v2.adults`, `source: "mobile"` are from recon; the segment keys (`origin`, `destination`, `date_start`, `date_end`) are invented | `client.build_query` | scrub output prints `browser_byte_match`; diff `tests/fixtures/*/query.json` against `build_query` |
| create_task response | `data.task_id`, `data.total_sub_tasks`, `code == 0` | `raw.parse_create` | fixture `create_task.json` |
| `data` field | sent equal to `encrypted`; browser may use a bundle constant | `client.create_task` | `meta.json` has `data_equals_encrypted`; if false, extract the bundle key (plan, M2) |
| Cipher | AES key size follows the decoded key length (8-char section gives AES-256, not AES-128 as the plan says) | `crypto.derive_key` | known-answer test once `crypto_kat.json` exists |
| fetch_result envelope | `data.status` of `processing` or `done`, `data.result` is a list of summaries, each with optional `routes` | `raw.parse_fetch`, `item_routes` | fixture `fetch_result.jsonl` |
| Summary identity | `(program, date, departure, arrival)` | `raw.summary_key` | count equals `total_sub_tasks` on a done poll (M2 experiment) |
| Route fields | `payment.{cabin,miles,tax,cash_price,currency}`, `segments[].{flight_no,from,to,dt,at,cabin,aircraft,layover}`, `transfer[].{bank,points,actual_points,bonus_percentage,bonus_end}`, `promotion.description`, `seats` (9999 = not live), `premium_pct`, `booking_url`, `duration` | `raw.RawRoute` | the warnings printed on the first real parse name every unknown or missing field |
| Duration unit | minutes | `normalize` | compare with a segment sum |
| Time format | ISO-like local times without zone | `normalize.parse_dt` | fixture |

## Open questions from the plan that code currently assumes

- Per-person vs total miles for `--pax 2`: assumed per person (multiply). `Query.pax_totals` flips it. (M2 check)
- Slow polling loses nothing: cadence is 2 s x 3 then 6 s. (M2 experiment; constants in `client.py`)
- Whether an LHR search already returns LGW/LCY: ring 3 currently always drops same-metro alternates. (`geo/hubs.METRO_GROUPS`)
- Whether the free plan has a daily search quota: no handling yet.
- Which login path works: `pointmax login` tries Chrome automation, `--from-chrome` imports cookies. Neither has been run. Session lifetime unknown.

## Defaults I made up

- `config.DEFAULT_TOML`: every cents-per-point value, distance bands, hotel allowance (150), drive cost per km, buffers (3 h, 4 h, 24 h). Review before trusting rankings.
- `geo/hubs.py`: alliance hubs, stopover hubs, destination alternates, metro groups, from general knowledge, not `hubs-alliances-carriers.md`.
- Ring scoring weights in `planner/candidates.py` (connection signal x3, +1 for large airports, distance penalty 1 per 1000 km).
- Request budget: 10 requests per minute (the 50 per 5 min limit) for time quotes.

## Not built yet

- Positioning for the return leg: `--return` runs a direct-only search.
- Ring 3 alternate destinations with a `position_in` leg: `alternate_destinations()` exists but the planner does not use it.
- `pointmax login` has never opened a real browser; `silent_refresh` likewise.
- Extracting the default `data` key: `devtools/find_data_key.py` only prints bundle code, and has never reached the live site.
- The live tests (`pytest -m live`) are written but have never run.
