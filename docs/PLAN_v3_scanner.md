# FlightGuru v3 — Chat-Driven Flight Scanner

**Date:** 2026-08-09
**Status:** Plan, awaiting go-ahead

## What changes

v2 was a **monitor**: one fixed route (BOM→JFK), one fixed price target ($700), running on a
schedule, shouting when the price dropped.

v3 is a **scanner**: you start a conversation on Telegram, it asks what you need, it searches,
it answers. Nothing runs in the background.

## The conversation

```
You:  I need a flight
Bot:  Where are you flying from?
You:  JFK
Bot:  Where to?
You:  LAX
Bot:  Round trip, one way, or multi-city?
You:  round trip
Bot:  Outbound date?
You:  2026-09-12
Bot:  Return date?
You:  2026-09-19
Bot:  How many travelling?          (default 1 adult — "skip" accepts defaults)
You:  1
Bot:  Searching JFK→LAX and nearby airports...

      CHEAPEST — $184 round trip
      Delta DL412 + DL887
      JFK 08:15 → LAX 11:40, nonstop, 6h 25m
      [book]

      NEARBY AIRPORT — save $47
      From EWR instead: $137
      United UA523, nonstop, 6h 10m
      EWR is 24 mi from JFK
      [book]
```

## City names, not just airport codes

You will not always know the code, so every place question accepts either:

- an **airport code** — `JFK`, `BOM`
- a **city name** — `new york`, `mumbai`, `bombay`, `nyc`, `LA`

City input resolves to *every* airport serving that city, which is exactly the multi-airport
search we already want. "New York" → `JFK,LGA,EWR`. So city input and the nearby feature are the
same machinery.

Handling:
- The airport table carries `municipality` and `country`, so matching is a lookup, not an API call
- An alias table covers the common ones: `nyc`/`new york`, `la`/`los angeles`, `sf`, `dc`,
  `bombay`→Mumbai, `bangalore`→Bengaluru, `calcutta`→Kolkata, `madras`→Chennai
- Ambiguous names get a question back, not a guess:
  *"Which Springfield? 1) Springfield, MO 2) Springfield, IL 3) Springfield, MA"*
- Unrecognised input gets the closest matches offered rather than a bare error

## The nearby-airport feature

The important finding: **SerpApi's `departure_id` takes a comma-separated list.**
`departure_id=JFK,LGA,EWR,HPN` is **one** API call, not four. Each returned flight carries its
own `departure_airport.id`, so results can be grouped by origin and compared.

That makes this feature nearly free on quota — the earlier worry about burning 100 searches/month
was wrong.

To know that JFK's neighbours are LGA/EWR/HPN we need an airport table with coordinates:

- Source: OurAirports public dataset (free, public domain), filtered to **`scheduled_service = yes`
  at any airport size** — *not* large/medium only. Small fields like Tweed New Haven (HVN),
  Portsmouth (PSM) and Stewart (SWF) are exactly where Avelo, Breeze and Allegiant operate, and a
  size filter would have thrown them away.
- "Nearby" = great-circle distance within a radius, default **100 miles**, configurable
- Cap the fan-out at the 4 nearest, to keep the Google query sane

### Verified live, 2026-08-09 (one search spent)

`departure_id=JFK,LGA,EWR,HVN` → `MCO`, one way, sorted by price. Results came back spanning
multiple origins in a single call, and included **Avelo `XP 717` at $84** next to Frontier at $54
from the NYC airports.

Two things this proves:
1. The comma-separated multi-airport query works and mixes origins in one result set.
2. Ultra-low-cost regional carriers (Avelo, and by extension Breeze) **are** present in Google
   Flights data. They are not missing the way they were when those airlines launched.

Caveat found: a `json_restrictor` with nested `departure_airport{id}` silently dropped those
fields. The parser must read the full response, or the restrictor syntax needs testing properly.
`departure_airport` per leg is what identifies which airport a fare leaves from, so this matters —
without it the nearby comparison cannot group results.

Same trick works on `arrival_id` for destination-side alternatives (LAX / BUR / SNA / LGB / ONT).

## SerpApi parameters we now use

| Need | Parameter |
|---|---|
| Round trip | `type=1` + `return_date` |
| One way | `type=2` |
| Multi-city | `type=3` + `multi_city_json` |
| Multiple origin airports | `departure_id=JFK,LGA,EWR` |
| Multiple destination airports | `arrival_id=LAX,BUR,SNA` |
| Cheapest first | `sort_by=2` |
| Passengers | `adults`, `children`, `infants_in_seat`, `infants_on_lap` |
| Cabin | `travel_class` |
| Stops filter | `stops` |
| Bags | `bags` |

Note: for round trips the first call returns the **total** round-trip price, which is all we need
to rank. Fetching the specific return leg costs a second call (`departure_token`) — we only spend
that on the single cheapest result, not on every candidate.

Repeat identical searches within an hour are served from SerpApi's cache, free.

## Code plan

### Reused as-is
`net.py` (retries, 429 backoff) · `log.py` (rotating logs, secret redaction) · `normalize.py`
(validation, currency guard) · `deeplink.py` · most of `providers/serpapi.py`'s parsing

### Rewritten
- `config.py` — env vars held one global route. Now env holds only **secrets + defaults**;
  the route comes from the conversation. New `SearchRequest` dataclass carries one search.
- `models.py` — `Offer` gains `origin_airport`, `destination_airport`, `return_date`,
  `trip_type`, and return-leg fields.
- `providers/serpapi.py` — build params from a `SearchRequest` instead of global `Settings`.
- `main.py` — becomes a thin CLI for one-off searches; the bot is the primary entry point.

### New
- `airports.py` — airport table, coordinates, distance, `nearby(code, radius)`, and
  `resolve(text)` turning a code *or* city name into a list of airports
- `data/airports.csv` — trimmed OurAirports extract (code, name, city, country, lat, lon)
- `conversation.py` — the question flow as a state machine (one state per user, persisted so a
  restart doesn't lose your half-finished answers)
- `bot.py` — Telegram long-polling loop: read messages, drive the conversation, send results
- `parse.py` — forgiving input parsing: place text, "next friday" → a date, "12 sep" →
  2026-09-12, "2 adults 1 kid" → passenger counts

### Archived (moved to `archive/v2-monitor/`, not deleted)
`control.py` + `control.json` · `delta.py` · `health.py` alert checks · `alerts_sent` table ·
`.github/workflows/flightguru.yml` · the `TARGET_PRICE` / `NOTIFY_EVERY_RUN` settings

### Storage
`price_snapshots` keeps working as a search log (useful history), gains `search_id`,
`return_date`, `trip_type`, `origin_airport`. `alerts_sent` is dropped.

## Phases

1. **Search core** — `SearchRequest`, round trip + multi-city, multi-airport, updated parsing.
   Tests. No chat yet; drive it from the CLI.
2. **Airports** — dataset, distance, nearby lookup. Tests.
3. **Nearby comparison** — fan out origins, group results by airport, build the
   "you'd save $47 from EWR" comparison. Tests.
4. **Conversation** — state machine + input parsing. Tests (no network needed).
5. **Bot** — Telegram polling loop, wire it all together. Live test.
6. **Deploy** — Railway or PC, plus README/CHANGELOG.

## Decisions

1. **Hosting: Railway** (decided 2026-08-09). Always on, so the bot answers with the PC off. Same
   platform as PriceGuru, so the deploy path is already familiar. Long-polling rather than a
   webhook — no public URL or TLS to manage, and it survives restarts without re-registering.
   Development still runs locally against the same code; only the start command differs.

## Open decisions

1. **Nearby on the destination side too?** Only the origin side was asked for. Costs nothing extra
   to support. *Assumption: build both, default the destination side off, let the conversation
   offer it.*
2. **Nearby radius.** *Assumption: 100 miles, configurable.*
