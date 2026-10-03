# Travel point maximizer — reference README (core principles and rules of thumb)

> Imported 2026-10-03 from the "Travel point maximizer" project (pasted by Anish into the "Import artifacts from earlier project" thread). Text verbatim. This appears to be the "reference README" the pointmax plan cites by rule number (e.g. rule 3, rule 7).

## Core principles (apply across every file)

1. Award/cash pricing is origin-dependent, not distance-dependent. The same trip prices very differently by departure city because airlines set city-pair pricing on competition, not miles flown. Always price 2–4 alternate nearby gateways before pricing from the home airport.
2. A positioning flight is a cheap, separately-ticketed short hop used purely to relocate to a cheaper departure city. This is the single biggest lever for cutting long-haul cost, in cash or miles.
3. Hubs matter more than airlines. Alliances let you mix carriers, so the real optimization question is "which hub gets the best onward pricing," not "which airline."
4. Not all points are equal, and not all "miles" are worth the same thing. A mile's real value depends on whether its program uses a fixed chart (sweet spots exist) or dynamic pricing (value tracks cash, no sweet spots) — see point-valuations-and-transfer-partners.md before assuming any two currencies are interchangeable.

## Consolidated rules of thumb for the tool

1. Price 2–4 alternate nearby gateway airports for every search, not just the home airport, in both cash and award mode.
2. Treat positioning legs as separate tickets with 3–4+ hour connection buffers (more across budget carriers or separate airports).
3. Prefer hub cities served by multiple alliances — it doubles award-search surface area.
4. Always price Middle East hubs (DXB/DOH/AUH/IST) as a candidate connection for Europe/US ↔ Africa/South Asia/Southeast Asia, even when not obviously on the direct path.
5. Check the same route against multiple transferable-point programs (Amex, Chase, Capital One, Citi) and multiple alliance partners — pricing varies by program for an identical flight. Watch for single-points-of-failure (only Chase reaches Hyatt/Southwest; only Citi reaches Qatar/Turkish among the major four banks).
6. Never self-connect a budget carrier to a legacy carrier on one itinerary/booking — always separate tickets, generous buffer, carry-on only if possible.
7. Always compare round-trip pricing against two one-way awards — one-ways are frequently cheaper and let you mix alliances per direction.
8. Compare all-in award cost (miles + carrier-imposed surcharges + government departure taxes/duties) across every program that can book the same partner flight, not just the sticker mileage price.
9. Flag stopover-eligible hubs (KEF, IST, DXB, DOH, AUH, SIN, PTY, LIS) as bonus value, not just connection time.
10. Surface brand-new routes (<12 months old) as a temporarily-favorable cash-fare category, while expecting thin award availability.
11. Don't rely on PointsYeah or Point.me alone — cross-check Aeroplan/Flying Blue availability elsewhere (their known gap), and treat Point.me as the booking-path verifier rather than a second discovery engine.
12. Check for named multi-city perks (United Excursionist Perk, Aeroplan stopovers) before pricing a multi-stop routing as plain one-ways.
13. Search immediately when a program's booking window opens (~11–12 months out) for known trips; run standing alerts for flexible ones.
14. Treat fuel dumping and hidden-city ticketing as manual, occasional, non-automatable techniques — real account-suspension risk if repeated or automated.
15. Model pricing strictly by origin airport, never by browser locale/VPN region — "cheaper fares from another country's site" is a myth; the only real lever is actually departing from a cheaper city.
16. Consider open-jaw itineraries (fly into city A, out of city B) whenever a trip visits more than one city in a region — often cheaper than round-trip-to-one-city plus separate intra-region transport.
17. Invest search effort disproportionately in fixed-chart programs and partner awards on mixed-model programs (Alaska, Aeroplan, Avios, ANA, Flying Blue, Turkish, and AA/UA partner awards) — dynamically-priced own-metal awards (Delta, and AA/UA's own flights) rarely beat their baseline cents-per-point value, so there's little to "find."
18. When a routing passes near a known fifth-freedom city pair, price that segment on the fifth-freedom operator specifically — it's a distinct cheap/premium-value category separate from ordinary positioning flights.

## Maintenance notes

* Re-verify anything tagged HIGH/VERY HIGH before hardcoding it into pricing logic — these reflect a snapshot from research done in September 2026.
* LATAM's alliance/partnership status shifts periodically (codeshares with both Oneworld and Delta) — confirm live before hardcoding partner logic.
* PointsYeah/Point.me feature gaps are based on 2026 user/reviewer reports — spot-check against current tool state before deciding what a third data source needs to cover.
* Point valuations (cents-per-point) should be re-pulled monthly from a source like TPG's or Upgraded Points' valuation guides — these are the single fastest-moving numbers in the whole reference set.
