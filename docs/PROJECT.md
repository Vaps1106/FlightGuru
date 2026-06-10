# PROJECT.md — FlightGuru v2 (single source of truth)

## Business goal
Notify the owner the moment a **BOM → JFK** fare departing **2026-07-20 to
2026-08-14** drops below **$700 USD**, with a *trustworthy* price (taxes + fees
included) and a usable booking link — so a cheap seat can be booked before it
disappears.

## Requirements
- Prices must be real and verified (no scraped/cached/estimated numbers).
- Every reported price includes timestamp, currency, taxes, fees, source.
- Alerts include "Verified at: YYYY-MM-DD HH:MM UTC".
- A working booking deep link, or **no alert** (log "Deep booking URL unavailable").
- Never invent prices, routes, airlines, or links.
- Store every price snapshot (history).
- Run unattended for months, for free.
- Search the whole departure-date range (2026-07-20 → 2026-08-14), and report
  the single cheapest verified fare **once per run** (one summary, not per-flight spam).

## Architecture (summary)
Scheduled GitHub Actions run → `flightguru` pipeline
(search → normalize/validate → deeplink → storage → delta → notify). Full diagram
in [ARCHITECTURE.md](ARCHITECTURE.md).

## Tech stack
Python 3.12 · requests · SQLite · pytest · GitHub Actions (host + scheduler) ·
Telegram. Rationale and rejected alternatives in [DECISIONS.md](DECISIONS.md).

## APIs
- **Amadeus Self-Service — Flight Offers Search** (primary): real fares + tax/fee
  breakdown, free test tier.
- **Duffel** (later/optional): true bookable offers for stronger deep links.

## Database schema
SQLite at `data/flightguru.db`, committed back each run.
- `price_snapshots`: every check (checked_at_utc, verified_at_utc, source,
  origin, destination, depart_date, airline, flight_numbers, base_price, taxes,
  fees, total_price, currency, stops, duration_minutes, deep_link, below_target).
- `alerts_sent`: log of notifications already sent (prevents duplicates).

## Monitoring strategy
Structured logs in each Actions run + a price-history file. Heavy dashboards
(Prometheus/Grafana) deferred as overkill for a personal monitor.

## Deployment strategy
GitHub Actions scheduled workflow (`monitor.yml`), every 8 hours, free.
See [DEPLOYMENT.md](DEPLOYMENT.md).

## Risks
- Universal "click-to-book" deep links are an industry-hard problem (see DECISIONS D6).
- Amadeus free-tier quotas/rate limits.
- **Date-range cost:** the range spans 26 days. Checking each date = up to 26 API
  calls per run. Phase 2 must sample dates or cap calls to stay within the free tier.
- GitHub cron timing is best-effort (minor delays).
- Summer-2026 fares may not all be available this far in advance.

## Open issues
- Confirm one-way vs round-trip for BOM→JFK.
- Decide Duffel vs Google-Flights links once Phase 2 data is seen.

## Future enhancements
- WhatsApp alerts (Twilio, paid).
- Multiple routes / flexible dates.
- Migrate SQLite → hosted Postgres if it ever needs multi-device access.

## Phase status
- Phase 0 Architecture — ✅ approved
- Phase 1 Foundation — ✅ complete
- Phase 2 Search Engine — ✅ complete (Duffel + SerpApi; SerpApi-only live until a live Duffel token)
- Phase 3 Price Monitoring — ✅ complete (SQLite history + delta detection)
- Phase 4 Notifications — ✅ complete (Telegram; WhatsApp deferred)
- Phase 5 Production Hardening — ✅ complete (retries, logging, health, secret scan)
- Phase 6 Production Release — ✅ docs/version ready; deploying to GitHub Actions
