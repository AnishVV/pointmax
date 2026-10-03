# Award Sweet Spots, Distance/Off-Peak Charts & Fuel Surcharges

> Imported 2026-10-03 from the "Travel point maximizer" project (pasted by Anish into the "Import artifacts from earlier project" thread). Text verbatim; tab-separated tables converted to markdown.

**Volatility: HIGH** — award charts and surcharge policy change without much notice. Re-verify before hardcoding into pricing logic.

## What a "sweet spot" is

A specific route/cabin combination where a program's award chart badly undervalues the actual cash cost — usually because the chart is a flat regional chart rather than true distance- or demand-based pricing.

## Sweet spot table

| Alliance/Program | Route | Cabin | Cost |
| --- | --- | --- | --- |
| Oneworld — Alaska Atmos Rewards | US → Hong Kong (Cathay Pacific) | First | 70,000 miles |
| Oneworld — Alaska/AAdvantage | US → Tokyo (JAL) | First | 70,000–80,000 miles |
| Oneworld — Alaska Atmos Rewards | US → Sydney (Qantas) | Business | 55,000 miles |
| Oneworld — AAdvantage | US East Coast → Doha (Qatar Qsuite) | Business | 70,000 miles |
| Oneworld — Iberia Avios | US → Madrid | Business (off-peak) | 40,500 miles |
| Star Alliance — Turkish Miles&Smiles | US → Europe | Business | ~45,000 miles |
| Star Alliance — ANA Mileage Club | Round-trip US → Tokyo | First | 150,000–165,000 miles |
| Star Alliance — Aeroplan | US → Europe (Lufthansa/Swiss) | First | ~100,000 miles |
| SkyTeam — Flying Blue | US → Europe | Business (Saver) | ~60,000 miles |
| SkyTeam — Virgin Points | US → Europe (Delta One) | Business | 47,500–70,000 points |
| SkyTeam — Virgin Points | US → Tokyo (ANA First) | First | 72,500–85,000 points |
| Non-alliance — KrisFlyer | West Coast US → Hawaii | Economy | 13,500 miles |

## Distance-based charts (ANA round-the-world)

ANA prices its round-the-world award by total distance flown, not zones or stop count:

| Total distance | Business class cost |
| --- | --- |
| Under 22,000 miles | 125,000 miles |
| 22,001–25,000 miles | 145,000 miles |
| 25,001–29,000 miles | 170,000 miles |

Ground transport between cities doesn't count toward the distance total — a routing that skips short regional flights in favor of overland transfers can add extra stops "for free." Best chart for a genuine multi-continent trip rather than point-to-point.

## Off-peak vs. peak charts

Iberia Avios, British Airways Avios, and ANA all publish different mileage prices for "off-peak" vs. "peak" dates on the identical flight — off-peak can be 30–40% cheaper in miles. Model this as a calendar-aware filter per program, not a single static price per route.

## Fuel/carrier-imposed surcharges by program

No fuel surcharges on any award, including partner-operated flights: JetBlue TrueBlue, Southwest Rapid Rewards, Spirit Free Spirit, Air Canada Aeroplan, Avianca LifeMiles, United MileagePlus.

Surcharges on specific partners only:

| Program | Surcharges apply to |
| --- | --- |
| Alaska Mileage Plan/Atmos Rewards | British Airways- and Icelandair-operated flights |
| American AAdvantage | British Airways- and Iberia-operated flights |
| Delta SkyMiles | Delta/Air France-KLM/Virgin Atlantic flights departing Europe |
| British Airways Executive Club | Its own BA-operated flights (reducible by paying more Avios) |
| Virgin Atlantic Flying Club | Virgin Atlantic- and Delta-operated flights (heavy) |
| Emirates Skywards | Emirates-operated flights, all cabins (large) |
| Singapore KrisFlyer | Every partner except Singapore Airlines itself |

Rule for the tool: when the same award seat is bookable through multiple programs (common within an alliance), always compare the all-in cost (miles + taxes/surcharges) — the cheapest-looking mileage price isn't always the cheapest ticket. Example: booking a British Airways flight through Alaska or Aeroplan instead of BA's own Avios often avoids BA's own surcharges entirely.
