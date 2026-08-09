# v2 monitor — archived 2026-08-09

Kept for reference, not used. Nothing here is imported by the running code.

## What this was

FlightGuru v2 watched **one fixed route** — BOM to JFK — against **one price
target** ($700). It ran on command via a GitHub Actions workflow, compared each
result against the last one, and sent a Telegram alert when the price dropped or
went under target. It worked, and it was used.

## Why it was retired

v3 answers a different question. Instead of watching one route forever, you text
it and it searches whatever trip you describe, then tells you if a nearby airport
is cheaper. There is no background watching at all, so everything that existed to
support watching had nothing left to do.

The owner confirmed on 2026-08-09 that the monitor is no longer needed.

## What is in here

| File | What it did | Why it went |
|---|---|---|
| `src/control.py`, `control.json` | Pause switch and an active date window, so monitoring could be stopped without editing code | Nothing runs unattended now, so there is nothing to pause |
| `src/delta.py` | Compared this run's price to the last one; decided "dropped" and "below target" | There is no "last run" to compare against |
| `src/search.py` | Fanned one route out across a range of departure dates | v3 searches the dates you actually ask for |
| `src/serpapi.py` | v2's Google Flights provider — one way, one origin, one destination, one date | Superseded by `providers/flights.py`, which handles round trips, multi-city and several airports at once |
| `src/duffel.py` | Second price source | Never used in practice: only a test token was ever available, which returns demo data |
| `workflows/flightguru.yml` | Manual-trigger GitHub Actions run | GitHub Actions cannot host a chat bot — it only wakes when triggered. v3 runs on Railway |
| `tests/` | Tests for the above | Move with the code they cover |

## Related

- v1 PowerShell implementation: `archive/v1-powershell/`
- v3 plan: `docs/PLAN_v3_scanner.md`
