# PointsYeah API — Reverse-Engineering Notes

> Imported 2026-10-03 from the "Travel point maximizer" project (pasted by Anish into the "Import artifacts from earlier project" thread). Text is verbatim except that the account's `requestKeySection` value is redacted as `<redacted>`.

Captured live via browser network interception + in-page JS instrumentation (built-in browser, logged into Anish's own PointsYeah account). Verified end-to-end by successfully decrypting a live request, and by capturing a fully-populated live-availability response (DFW→LHR).

## Frontend

* Next.js SPA at `www.pointsyeah.com`.
* Auth/session: `GET /api/auth/session` (same-origin, cookie-based) returns:

```json
  {
    "success": true,
    "data": {
      "isAuthenticated": true,
      "user": {"userId": "<uuid>", "username": "<uuid>"},
      "userAttributes": {"email": "..."},
      "subscription": {
        "isFreePlan": true,
        "maxDateRange": {"ONEWAY": 4, "ROUNDTRIP": 2, "MULTICITY": 2},
        "subscriptionStatus": {"status": false, "sub_type": "monthly"},
        "isPremiumUser": false
      },
      "safeClaims": {
        "joinedAt": "2024-11-25",
        "requestKeySection": "<redacted>"
      }
    }
  }
```

`safeClaims.requestKeySection` is the critical field — it's the per-account key material for request encryption (see below). `subscription.maxDateRange` caps how wide a single search's date window can be on the free tier (one-way: 4 days, roundtrip: 2, multi-city: 2) — wider sweeps must be chunked into multiple searches.

## Search flow (async task/poll pattern, 3 endpoints)

1. `POST https://api2.pointsyeah.com/flight/search/create_task` Body: `{"data": "<b64 ciphertext>", "encrypted": "<b64 ciphertext>"}` — both fields are AES-CBC ciphertext of the same plaintext query JSON (see Encryption below), just encrypted under two different derived keys. Response: `{"code":0,"success":true,"data":{"task_id":"...","total_sub_tasks":72,"status":"created"}}` `total_sub_tasks` = programs × dates being fanned out server-side (e.g. 18 programs × 4-day window = 72).
2. `POST https://api2.pointsyeah.com/flight/search/fetch_result` Body: `{"task_id": "<from step 1>"}` — sent plaintext, unencrypted (confirmed live; unlike `create_task`, no AES wrapping needed here). Poll repeatedly (client polls every few hundred ms) until `data.status == "done"`. Each poll returns only a partial batch — accumulate `data.result` arrays across all polls; the full set is never returned in one response. Gotcha confirmed live: `status` is not monotonic — a poll can report `"done"` with an empty `result`, and a later poll on the same `task_id` can report `"processing"` again before settling back to `"done"`. This looks like independent sub-task batches (e.g. one per program or per segment in a multi-city search) each completing on their own schedule under one shared `task_id`. Do not stop polling on the first `"done"` — keep polling until you've seen a few consecutive `"done"` responses with empty results (a short quiet period), not just one. When a program/date has zero live availability, its result entry is summary-only:

   ```json
   {"program": "Virgin Australia Velocity", "code": "VA", "date": "2026-12-21", "departure": "DFW", "arrival": "AMD", "routes": [], "cost": 1.319}
   ```

   `cost` here is a normalized relative-value score (roughly 0–3+), not a real price — it's what PointsYeah uses to rank/heatmap dates before you look at specifics. It is not needed by our tool; ignore it once `routes` is populated. When a program/date has live bookable availability, the same entry's `routes` array is populated with full itinerary objects — see full schema below. This only failed to appear in early testing because the sampled route (DFW→AMD, Ahmedabad) genuinely had zero award space across every checked program for those dates; a well-served route (DFW→LHR) returned 2,115 populated route objects across 8 programs on the first try.

3. `POST https://api.pointsyeah.com/v2/live/flight/history` (note: `api.` not `api2.`) — optional, plaintext (unencrypted) request that just logs the search for the "recent searches" feature. Safe to skip entirely.

## Confirmed plaintext query schemas

One-way:

```json
{
  "search_type": "one_way",
  "cabins": ["Economy", "Premium Economy", "Business", "First"],
  "segments": [{"arrival": "AMD", "departure": "DFW", "departure_date": {"from": "2026-12-22", "to": "2026-12-25"}}],
  "passengers_v2": {"adults": 1, "children": 0},
  "source": "mobile"
}
```

Multi-city — confirmed live (captured and decrypted an actual submission: DFW→LHR Dec 22-23, then LHR→CDG Dec 26):

```json
{
  "search_type": "multi_city",
  "cabins": ["Economy", "Premium Economy", "Business", "First"],
  "segments": [
    {"arrival": "LHR", "departure": "DFW", "departure_date": {"from": "2026-12-22", "to": "2026-12-23"}},
    {"arrival": "CDG", "departure": "LHR", "departure_date": {"from": "2026-12-26", "to": "2026-12-26"}}
  ],
  "passengers_v2": {"adults": 1, "children": 0},
  "source": "mobile"
}
```

Exactly as guessed: just extra `{arrival, departure, departure_date}` entries in `segments`. This is architecturally important — one `create_task` call with N segments searches all N legs in a single request/task_id, rather than needing N separate one-way searches. Confirmed behavior:

* All segments' results come back through the same `task_id` / polling stream, not separate ones per segment.
* Each result item in the accumulated `data.result[]` is tagged with its own `departure`/`arrival` pair, so the tool must group/split results client-side by `(departure, arrival)` to know which segment each result belongs to — there is no explicit `segment_index` field.
* The PointsYeah UI itself does this same grouping: the multi-city results page shows a "Flight 1: DFW-LHR" / "Flight 2: LHR-CDG" tab switcher over what is really one combined result set.
* This is a per-leg search, not a combined-itinerary search — it does not return single bookable itineraries that cover both legs together under one program/booking. It's equivalent to running two one-way searches and merging by tab, just cheaper (one task) and respecting one shared date-range budget. For our tool's positioning-flight use case (find a cheap/available award to city B, then a separate award from B to actual destination C), this is exactly the right primitive: submit the positioning leg + the onward leg as one multi-city request, then independently rank/combine the per-leg results ourselves (award tool doesn't stitch fares into a single "itinerary price" — we do that layer).
* `search_type: "round_trip"` is still unconfirmed (not yet captured live) but almost certainly follows the same pattern — likely a single segment with both `departure_date` (outbound) and an added return-date field, or two segments with swapped arrival/departure. Low priority to verify now that the segment-array pattern is proven for multi-city.

The search page's URL query string carries an equivalent, human-readable encoding (`cabins`, `banks`, `airlineProgram`, `tripType`, `adults`, `children`, `departure`, `arrival`, `departure2`, `arrival2`, `departDate`, `departDateSec`, `departDate2`, `departDateSec2`, `multiday`) — `tripType=1` one-way, `tripType=3` multi-city (confirmed from live URLs); round-trip's numeric value not yet observed.

## Full result/route schema (confirmed live, DFW→LHR sample)

Each item in `fetch_result`'s accumulated `data.result[]` array:

```
{program, code, date, departure, arrival, cost, routes: [ <route>, ... ]}
```

Each `<route>` object (this is the real payload — one per bookable itinerary option):

```json
{
  "payment": {
    "currency": "USD",
    "tax": 5.6,
    "miles": 275000,
    "cabin": "Business",
    "unit": "points",
    "short_unit": "pts",
    "seats": 6,
    "cash_price": 5285
  },
  "segments": [
    {
      "duration": 276,
      "flight_number": "AS321",
      "aircraft": "Boeing 737-900 (Winglets) Passenger",
      "dt": "2026-12-24T14:04:00",
      "da": "DFW",
      "at": "2026-12-24T16:40:00",
      "aa": "SEA",
      "layover": 135,
      "cabin": "First"
    }
  ],
  "duration": 976,
  "cross_days": 1,
  "program": "Alaska Atmos Rewards",
  "code": "AS",
  "premium_cabin_percentage": 0,
  "url": "https://www.alaskaair.com/search/results?O=DFW&D=LHR&OD=2026-12-24&A=1&C=0&L=0&RT=false&ShoppingMethod=onlineaward",
  "cash_ticket_url": "https://www.alaskaair.com/search/results?...",
  "extra": {},
  "promotion": null,
  "transfer": [
    {"bank": "Bilt", "actual_points": 275000, "points": 275000, "bonus_percentage": 0, "bonus_end_date": null, "bonus_slogn": "", "url": "https://www.biltrewards.com/", "code": "Bilt"}
  ]
}
```

Field notes:

* `payment.miles` / `payment.tax` — the actual award price shown to the user (miles + cash taxes/fees). `payment.cash_price` — comparable cash fare for the same flight (0 when unknown).
* `segments[]` — per-leg detail: `dt`/`at` are local departure/arrival timestamps, `da`/`aa` are IATA codes, `cabin` can differ per segment (mixed-cabin itineraries are common on connections, e.g. First on a short domestic segment feeding a Business long-haul), `layover` in minutes (0 on the last segment).
* `url` — deep link straight into the airline's own booking flow for that exact itinerary (huge for the tool: this is the actual "go book it" link). `cash_ticket_url` is the equivalent cash-fare booking link (often blank).
* `transfer[]` — every bank/transferable-currency path that can reach this award, each with `bank`, `points` needed (may exceed `payment.miles` if the bank's transfer ratio isn't 1:1 — compare `actual_points` vs `points`), and `bonus_percentage`/`bonus_end_date`/`bonus_slogn` for live transfer bonuses (populated when a bonus is running, e.g. Chase Ultimate Rewards +20% to Aeroplan was live during testing).
* `promotion` — non-null when the program is running a "buy points" promo (e.g. `{"description": "Buy points up to 100% bonus at 1.88 cents per mile", "url": "..."}`), relevant when no transfer path exists or buying up is cheaper than the redemption is worth.
* `extra` — sometimes populated with `booking_code` (fare bucket), `left_seats` (a full per-booking-class seat count map, e.g. `{"J":9,"Z":8,"Y":9,...}` — richer than the single `payment.seats` number), `special_member_price`/`special_price_for_chase` flags, and `get_card_member_miles` (a co-brand-cardholder-only lower price). `payment.seats` of `9999` means "unlimited / buy-to-order," not real live inventory.
* `premium_cabin_percentage` — confirmed via the UI's "Premium Cabin %" filter tooltip: "This filter applies only to mixed-cabin Business or First Class itineraries with at least one Economy or Premium Economy segment. The % sets the minimum flight time in Business/First. Itineraries with more Economy or Premium Economy time than selected are hidden." I.e. it's `(time spent in Business/First) / (total itinerary time)`, only meaningful for mixed-cabin routings; 0 for single-cabin itineraries.

This is the complete data the tool needs to rank and present real bookable options — no further per-card "detail" endpoint exists; everything is embedded directly in `fetch_result`'s accumulated response once a subtask resolves with live inventory.

## Search filters / parameters catalog (from the results-page filter bar)

These are the full set of ways a search's results can be narrowed. Distinguish query-shaping filters (part of `create_task`'s plaintext, i.e. actually change what's searched) from client-side post-filters (narrow an already-fetched result set the browser is holding — useful for our tool's own ranking/filtering logic, but not something we need to send to the API since we'll have the full raw result set already):

* Sort (client-side, re-orders the already-fetched list): Points Low to High, Quickest Flights, Longest Flights, Taxes Low to High, Departure Time, Arrival Time, Cash Low to High, My Own Points Value (Premium Member only — requires the user to have entered their personal cents-per-point valuations).
* Multi Dates (client-side): when a date-range search returns multiple dates, this lets you toggle specific dates on/off; shows a per-date cheapest-price teaser (e.g. "Tue Dec 22: 30,000 pts + $5.6" vs "Wed Dec 23: 27,500 pts + $25.6"). Useful pattern for our tool's own date-sweep UI.
* Cabins (query-shaping — maps directly to the `cabins` array in the plaintext query): Economy, Premium Economy, Business, First (including 2-cabin F). Each option shows live "From X pts + $Y" teaser and a per-cabin result count.
* Airline Programs (post-filter over results, NOT a query param — the search always queries all ~18 programs; this just filters which ones are displayed): the checkbox list only lists programs that actually returned results for this search (e.g. 7 of 18 for DFW-LHR: Aeromexico Rewards, Air Canada Aeroplan, Alaska Atmos Rewards, American Airlines AAdvantage, Delta SkyMiles, Qantas Frequent Flyer, United MileagePlus). The full master universe of 18 airline-program codes (from the default URL query param, confirmed): `AR` Aerolíneas Plus, `AM` Aeromexico Rewards, `AC` Air Canada Aeroplan, `KL` Air France/KLM Flying Blue, `AS` Alaska Atmos Rewards, `AA` American AAdvantage, `AV` Avianca LifeMiles, `DL` Delta SkyMiles, `ET` Ethiopian ShebaMiles, `EY` Etihad Guest, `B6` JetBlue TrueBlue, `LH` Lufthansa Miles & More, `QF` Qantas Frequent Flyer, `SK` SAS EuroBonus, `TK` Turkish Miles&Smiles, `UA` United MileagePlus, `VS` Virgin Atlantic Flying Club, `VA` Virgin Australia Velocity. Note PointsYeah's own reference doc (`airline-hubs-and-cheap-legs-reference.md`) flags Aeroplan/Flying Blue as sometimes incomplete here — worth cross-checking against Point.me or Seats.aero for those two specifically.
* Bank Programs (post-filter, shows which transferable-currency banks can reach the results shown): American Express Membership Rewards, Bilt Rewards, Capital One Miles, Chase Ultimate Rewards, Citi ThankYou Points, Wells Fargo, US Bank — matches the `banks` URL param master list exactly (7 total).
* Stops (post-filter, radio, single-select): Any number of stops, Non-stop only, 1 stop or fewer, 2 stops or fewer. Each option shows a live (matching/total) count and a "From" price teaser.
* Max Points (post-filter, range slider + manual min/max text entry): bounded to the actual min/max points values present in the current result set (e.g. 27,500–500,000).
* Time (post-filter, two independent range sliders): Departure time-of-day (at the origin airport) and Arrival time-of-day (at the destination airport), each 0:00–24:00 "Any time" by default.
* Duration (post-filter, range slider + manual entry): total itinerary duration in hours (e.g. 9–33 hours), bounded to what's actually in the result set.
* Airlines (post-filter — operating carrier, distinct from "Airline Programs" which is the redemption/loyalty program): checkbox list of actual operating airlines in the results, e.g. Aeromexico, Air Canada, Air France, Alaska Airlines, American Airlines, British Airways, Delta Air Lines, Mixed Airlines (codeshare/interline itineraries with more than one operating carrier), Qatar Airways, United Airlines.
* Max Taxes (post-filter, range slider + manual entry): cash co-pay (taxes/fees) range, e.g. $5–$1,579.
* Premium Cabin % (post-filter, radio): Any, ≥20%, ≥40%, ≥60%, ≥80%, 100% — see `premium_cabin_percentage` field notes above for exact semantics.
* Aircraft (post-filter): long checkbox list of aircraft type/model strings pulled raw from airline data feeds — messy/inconsistent naming (e.g. both `"AIRBUS A220-300"` and `"Airbus A220-300"` appear as separate entries), dozens of entries. Low priority for our tool; mostly useful for avoiding/targeting specific cabin hard-products.
* Promotion (post-filter, checkbox): "Bank transfer promotion" (a live transfer bonus applies — matches `transfer[].bonus_percentage > 0`) and "Buy points promotion" (matches non-null `promotion` field). High value for our tool — these are exactly the situations where the effective cost-per-point math changes favorably.
* Departure Airports / Arrival Airports / Connecting Airports (post-filter, checkbox lists with per-airport result counts): Departure/Arrival confirm the metro-area auto-inclusion behavior already documented (e.g. a DFW search silently also includes DAL). Connecting Airports is a checkbox list of every layover hub that appears across the current result set (e.g. for DFW-LHR: ATL, BNA, BOS, CDG, CLT, DEN, DOH, DTW, EWR, FLL, IAD, IAH, JFK, LAX, MEX, MIA, MSP, MSY, ORD, PHL, RDU, SEA, SFO, YUL, YYZ, plus one non-standard renamed-airport entry). This is directly useful for our tool's positioning-flight logic — it's effectively a free list of "which hubs currently have connecting award itineraries on this route," a starting point for identifying viable positioning/layover cities without having to brute-force test candidates.
* Flight Quality (post-filter, checkbox toggles, all on by default): "Show Redeye Flight", "Show flight with self-transfer" (itineraries requiring you to re-check-in / re-clear security between disjoint tickets — 0 in our sample), "Show flight with overnight connection". Useful defaults for our tool to expose as user-configurable quality filters.

Net takeaway for the tool's architecture: the only filters that actually change what gets searched server-side are `cabins` and the `segments` array (route/date/trip-type) — everything else (programs, banks, stops, points/time/duration/tax ranges, airlines, aircraft, premium %, promotions, airports, flight quality) is applied client-side over one comprehensive result set that already contains every program's live availability. This means our tool should always request the widest possible cabin set and let all programs run, then apply any of the above as post-filters/ranking criteria locally — there's no API-level way to narrow the search itself beyond route, date, and cabin, and no benefit to trying.

### "Departure/Arrival/Connecting Airports" filters — metro-area auto-inclusion

These are client-side filters over the already-fetched result set, not additional search parameters — e.g. searching "Dallas-Fort Worth (DFW)" actually searches both DFW and DAL (the metro area) server-side already, and the "Departure Airports" chip just lets you narrow the display to one or the other after the fact (confirmed: it showed "DAL (117/117)" and "DFW (1998/1998)", i.e. both fully included by default). This does not give you cross-city positioning search in one request — for genuinely different origin cities (e.g. DFW vs. AUS vs. IAH as separate candidate origins), the tool will need to run separate searches per candidate origin, same as it would for any other program, and merge results itself. (Connecting Airports, however, is a great signal — see catalog above.)

## Encryption — cracked and verified live

* Algorithm: AES-128-CBC (CryptoJS on the frontend), PKCS7 padding.
* IV: fixed for every request — ASCII string `"1020304050607080"` (16 bytes).
* Key: `base64_decode(f"LefjQ2pEXmiy/nNZvhJ43i8{key_section}YHYbn1hOuAgA=")`
  * For the `encrypted` field: `key_section = safeClaims.requestKeySection` (per-account, from `/api/auth/session`; confirmed value on this account: `<redacted>`).
  * For the `data` field: a fixed default constant baked into the JS bundle (not yet extracted — lower priority; requests worked fine in testing so the server likely only validates `encrypted` for logged-in accounts). Tried a handful of plausible guesses (all-zeros, the literal string "default", etc.) against a captured `data` field and none decrypted cleanly — this needs the actual JS constant extracted from the bundle, not brute-forced, if it ever becomes necessary.
* Verified: decrypting a live request's `encrypted` field with this exact recipe (Web Crypto `AES-CBC`, key built from the account's `requestKeySection`) reproduced the plaintext query JSON byte-for-byte, for both a one-way and a multi-city submission.

Practical implication for the tool: on startup, log in once (headless browser), capture the session cookie + `requestKeySection` from `/api/auth/session`, then all subsequent `create_task`/`fetch_result` calls can be plain HTTP + this AES recipe — no browser needed per search. Re-run the login step whenever the cookie expires or `requestKeySection` stops validating.

## Auth mechanics

* Session is a cookie set on `.pointsyeah.com` (sent to both `www.` and `api2.` subdomains automatically).
* No custom `Authorization` header — only `Content-Type: application/json` is set client-side.
* The session cookie is HttpOnly (invisible to `document.cookie`) — must be obtained via a real login flow (e.g., Playwright's cookie jar) rather than reconstructed.

## Rate limit budget (per Anish's request)

Client-side limiter, shared across `create_task` + `fetch_result` calls to a given site:

* max 10 requests / 30 seconds
* max 50 requests / 5 minutes

Note: a single search already generates dozens of `fetch_result` polls (one search here made ~45-70 polling calls to resolve 72 subtasks). At 10 req/30s that's several seconds of polling per search even before considering multiple candidate airports/dates — budget for this in the tool's UX (e.g. a progress indicator) and consider whether polling interval itself needs to slow down to stay under budget when running many searches back to back. The "keep polling past the first done" gotcha (see Search flow above) makes this a bit worse — plan for a few extra polls per search beyond the naive minimum.

## Open questions

1. Default `key_section` constant used for the `data` field (module `59807`, referenced as `i.GI`) — only matters if the server ever rejects a request where `data` doesn't also decrypt validly; untested since `encrypted` alone worked for both one-way and multi-city submissions.
2. Exact `search_type` value and shape for `round_trip` (multi-city is now confirmed — see above). Likely either a single segment with an added return-date field, or two segments with swapped arrival/departure; low priority since multi-city already proves the general "array of segments" pattern works and can approximate round-trip if needed (outbound leg + return leg as two segments).
3. Whether `requestKeySection` rotates (per session? per login?) or is stable long-term for a given account.
4. Point.me's equivalent API — not yet investigated (separate site/stack).
