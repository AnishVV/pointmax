# Point Valuations, Transfer Partners & Fixed vs. Dynamic Pricing

> Imported 2026-10-03 from the "Travel point maximizer" project (pasted by Anish into the "Import artifacts from earlier project" thread). Text verbatim; tab-separated tables converted to markdown.

**Volatility: HIGH** for the specific cent-per-point figures (these shift monthly with published valuation guides) — **MEDIUM** for the transfer-partner relationships and the fixed-vs-dynamic classification, which change only when a bank or program restructures its program.

## Why this file matters for a "maximizer" tool

The entire premise of a points maximizer requires comparing value across currencies — is it better to redeem 60,000 Amex points via Flying Blue, or via a Marriott hotel stay, or via a cash-back-style portal booking? None of the other files in this set answer that on their own; this file is the common-denominator layer everything else should be evaluated against.

## Baseline valuations (cents per point, snapshot Sept. 2026 — re-pull monthly)

Transferable bank currencies:

| Program | ¢/point |
| --- | --- |
| Bilt Rewards | 2.2 |
| Chase Ultimate Rewards | 2.05 |
| Amex Membership Rewards | 2.0 |
| Citi ThankYou Rewards | 1.9 |
| Capital One Miles | 1.85 |

Airline programs:

| Program | ¢/mile |
| --- | --- |
| Alaska Atmos Rewards | 1.55 |
| Avianca LifeMiles | 1.55 |
| Air Canada Aeroplan | 1.5 |
| American AAdvantage | 1.45 |
| Virgin Atlantic Flying Club | 1.45 |
| JetBlue TrueBlue | 1.35 |
| British Airways/Iberia Avios | 1.4 |
| ANA Mileage Club | 1.4 |
| Air France-KLM Flying Blue | 1.4 |
| Southwest Rapid Rewards | 1.25 |
| Singapore KrisFlyer | 1.3 |
| Frontier Miles | 1.3 |
| Cathay Asia Miles | 1.3 |
| Delta SkyMiles | 1.2 |
| United MileagePlus | 1.2 |
| Emirates Skywards | 1.2 |
| Etihad Guest | 1.2 |
| Qantas Frequent Flyer | 1.2 |
| Turkish Miles&Smiles | 1.1 |

Hotel programs:

| Chain | ¢/point |
| --- | --- |
| Accor Live Limitless | 2.3 |
| World of Hyatt | 1.65 |
| Choice Privileges | 0.85 |
| Wyndham Rewards | 0.7 |
| Marriott Bonvoy | 0.75 |
| Best Western Rewards | 0.6 |
| IHG One Rewards | 0.6 |
| Hilton Honors | 0.4 |

Read this as directional, not precise: these are blended averages across typical redemptions. The whole point of the sweet-spot tables elsewhere in this reference set is that a specific redemption can be worth 2–4x the baseline average (e.g. Avios' 1.4¢ baseline vs. a 40,500-mile Madrid business seat worth closer to 4–6¢/mile). Use the baseline to compare unremarkable redemptions or to value points sitting idle; use the sweet-spot tables to find the outliers.

## Transfer partner map (bank point → program)

| Bank currency | Transfers to (airlines) | Transfers to (hotels) |
| --- | --- | --- |
| Amex Membership Rewards | Aer Lingus, AeroMexico, Air Canada (Aeroplan), Alitalia/ITA, ANA, Avianca (LifeMiles), British Airways, Cathay Pacific, Delta, El Al, Emirates, Etihad, Air France-KLM (Flying Blue), Hawaiian, Iberia, JetBlue, Qantas, Singapore Airlines, Virgin Atlantic | Choice, Hilton, Marriott |
| Chase Ultimate Rewards | Aer Lingus, Air France-KLM (Flying Blue), British Airways, Emirates, Iberia, JetBlue, Singapore Airlines, Southwest, United, Virgin Atlantic | World of Hyatt, IHG, Marriott |
| Citi ThankYou | Air France-KLM (Flying Blue), Avianca (LifeMiles), Cathay Pacific, Etihad, EVA Air, Garuda Indonesia, JetBlue, Malaysia Airlines, Qantas, Qatar Airways, Singapore Airlines, Thai Airways, Turkish Airlines, Virgin Atlantic | (no hotel transfer partners) |
| Capital One Miles | Aeromexico, Air Canada (Aeroplan), Avianca (LifeMiles), British Airways, Emirates, and others | Accor, Wyndham |
| Bilt Rewards | Overlaps significantly with Amex's airline list (shared points ecosystem) — verify current list, changes periodically | Marriott, Hyatt, IHG |

Key implication for the tool: the same bank point balance can reach a given program through more than one bank only in some cases (e.g. Flying Blue is reachable from Amex, Chase, and Citi), so when a Flying Blue sweet spot is found, check whether the user's actual point balance sits at Amex, Chase, or Citi — any of the three works. But Chase is the only path to Hyatt and Southwest among the majors, and Citi is the only listed path to Qatar Airways and Turkish Miles&Smiles among the four banks above — those are single points of failure worth flagging distinctly.

## Fixed award charts vs. dynamic pricing — why sweet spots exist on some programs and not others

Dynamic/revenue-based pricing: the mileage cost tracks the cash fare in real time, and rises/falls with demand exactly like a cash ticket would. Delta SkyMiles pioneered this model; several others have since partially adopted it for their own metal. This eliminates sweet spots — there's no chart to arbitrage because the "chart" is just the cash fare converted at a fixed cents-per-mile rate. Average redemption value tends to sit low (Delta averages ~1.1¢/mile).

Fixed award charts: mileage cost is set by a published chart (by zone, region, or distance band) that doesn't move with the cash fare. This is where sweet spots live — when the chart under-prices a high-demand route relative to its cash cost, that gap is the sweet spot. Alaska/Atmos Rewards, Avianca LifeMiles, Aeroplan, Avios, ANA, Turkish Miles&Smiles, and Flying Blue are the primary fixed-chart programs referenced throughout this reference set for exactly this reason.

Mixed model: American and United price their own-metal flights dynamically but still use fixed charts for partner awards (this is why Excursionist Perk-style United partner awards and AAdvantage's Oneworld partner sweet spots — Cathay First, JAL First, Qatar Qsuite — still work even though a United.com domestic ticket is dynamically priced).

Tool implication: when searching a dynamically-priced program's own flights, there's little value in an award-search tool beyond confirming availability — the price will roughly match cash value converted at that program's baseline rate. The tool should invest search effort disproportionately in fixed-chart programs and partner awards on mixed-model programs, since that's where mispricing (and therefore savings) actually occurs.
