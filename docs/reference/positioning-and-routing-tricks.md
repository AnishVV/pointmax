# Positioning Flights & Routing Tricks

> Imported 2026-10-03 from the "Travel point maximizer" project (pasted by Anish into the "Import artifacts from earlier project" thread). Text verbatim.

**Volatility: LOW** for the mechanics below; **HIGH** for the specific dollar/mile figures in the worked examples (illustrative, not current pricing).

## The mechanic

A positioning flight (a.k.a. repositioning flight) is a cheap, short hop — booked as a separate ticket from the international/long-haul segment — used purely to relocate to a departure city with better pricing before starting the real trip. This works because airlines price city-pairs by competition, not distance: a small city can price at 2–3x a nearby major hub for the identical onward itinerary.

Rule of thumb: "An award from a small city might price at 100,000 miles; the same award starting from the right hub might be 55,000."

## Worked examples

* Cash fare, domestic hop unlocks cheaper transatlantic fare: Minneapolis → Copenhagen priced $900+ round-trip direct. Adding a $159 MSP–BOS positioning flight and booking BOS–CPH separately for $356 dropped the total to ~$515.
* Award availability, domestic hop unlocks a sweet spot: A positioning flight into Chicago unlocked Iberia Avios business class to Madrid at 40,500 miles (unavailable/priced far higher from the home airport) — turning a $3,000+ cash business seat into a ~$140 flight + miles.
* One-way award construction: Pricing outbound/return as two separate one-way awards often beats round-trip pricing and lets you mix alliances per direction — e.g. a Tokyo–Newark segment booked standalone for 90,000 United miles.
* Partner-program arbitrage: The identical domestic segment can cost different mileage depending on which partner program prices it — e.g. a Delta domestic flight booked through Air France-KLM Flying Blue for ~15,500 miles vs. 23,000 SkyMiles direct.
* Nashville/DFW → Doha via Qatar: positioning flights from smaller cities (e.g. Nashville, DFW) into a Qatar Airways gateway, ticketed as one coordinated multi-city itinerary, avoided expensive direct routing from the home city.

## Open-jaw tickets

An open-jaw itinerary flies into one city and out of a different one, with you arranging your own transport between them — instead of booking a connecting flight for that internal leg.

Example: New York → Switzerland. A standard round-trip to Geneva alone priced at $674. Flying into Geneva and out of Zurich (an open jaw) priced lower than that round-trip while also covering ground between two regions worth visiting — and dramatically cheaper than booking the same two flights separately as one-ways (which exceeded $2,000).

When to use it: any trip touching more than one city in a region. Compare round-trip-to-one-city-plus-separate-transport against an open jaw before defaulting to round-trip.

## The "VPN for cheaper flights" myth — debunked

A persistent myth claims switching your browser/VPN location to another country shows cheaper fares. Testing (e.g. checking a Cathay Pacific fare from a Vietnamese VPN) found no price difference, and there are no verified success stories behind the claim.

Why it doesn't work: airlines price tickets by origin airport, not by where the buyer is browsing from or paying from. Changing your apparent location changes nothing about the fare basis.

What actually works instead: the real, verified lever is a positioning flight — physically starting the itinerary from a cheaper origin city. One documented case: flying Seoul → [departure city] first cut a premium economy fare roughly in half by originating out of Seoul instead of the traveler's home city.

Implication for the tool: never model "cheaper from another region's site" as a pricing input — model pricing strictly by origin airport, and treat any apparent geo-based price difference as noise/caching rather than a real signal.
