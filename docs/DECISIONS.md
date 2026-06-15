# DECISIONS.md — architecture decision record

Each entry: the decision, why, and what we rejected.

## D1 — Host on GitHub Actions (scheduled workflow)
**Decision:** Run the monitor as a free scheduled GitHub Actions workflow.
**Why:** The task is periodic, not always-on. Free, no server to manage, has a
manual "Run" button.
**Rejected:** Railway/Render/Fly always-on tiers (cost or sleep), AWS ECS (too complex).

## D2 — SQLite committed back to the repo (not Postgres)
**Decision:** Store history in `data/flightguru.db` and commit it back each run.
**Why:** Single file, zero server, free, easy backup. Committing also resets
GitHub's 60-day cron-disable timer automatically.
**Rejected:** Managed Postgres/Redis — unnecessary cost/complexity for one route.

## D3 — No Redis cache
**Decision:** Skip caching.
**Why:** ~3 checks/day generates nowhere near enough traffic to need it.

## D4 — No Docker
**Decision:** No container image.
**Why:** GitHub Actions already provides a clean Python environment via
`requirements.txt`. Docker would add complexity for no benefit here.
**Revisit if:** we ever move off GitHub Actions to a different host.

## D5 — Duffel + SerpApi as price sources
**Decision:** Use **Duffel** (Flight Offers Search) as the primary source and
**SerpApi** (Google Flights) as a cross-check. Either or both run depending on
which keys are configured.
**Why:** Duffel returns real, bookable fares with a tax/fee breakdown — free to
search, fixing v1's inaccurate scraped prices — and SerpApi adds an independent
all-in display price for sanity-checking. SerpApi's small free quota is the
reason `search.py` caps how many dates it samples.
**History:** Amadeus Self-Service was the original Phase-0 plan, but during
Phase 2 we switched to Duffel for stronger, directly-bookable offers (and added
SerpApi as the cross-check). TravelPayouts was rejected (cached/inaccurate,
confirmed in v1).

## D6 — Kayak deterministic deep links as the practical default
**Decision:** Generate Kayak URLs (`kayak.com/flights/ORIGIN-DEST/DATE`) that
land the user directly on real, pre-filled results sorted cheapest-first. If a
usable link cannot be built, send no alert and log it.
**Why:** Universal "click once and pay" deep links do not exist for free across
all airlines. We first tried the Google Flights `#flt=` hash format, but Google
deprecated it — it opened a blank search page (verified 2026-06-10), the exact
re-entry problem the spec forbids. Kayak's URL scheme is deterministic and
pre-fills reliably. Full in-app booking (Duffel) is deferred as a future option.

## D7 — Telegram only for now (WhatsApp deferred)
**Decision:** Ship Telegram (free, already works). WhatsApp via Twilio is Phase 4b, optional.
**Why:** Twilio WhatsApp costs money and needs business setup.

## D8 — Defer Prometheus/Grafana
**Decision:** Use plain logs + price history instead of dashboards.
**Why:** Enterprise monitoring is overkill for a personal one-route monitor.

## D9 — Plain-text Telegram (no HTML parse mode)
**Decision:** Send messages as plain text.
**Why:** v1 used HTML mode, where an unescaped `&` silently dropped alerts. We
avoid the bug entirely by not using HTML.

## D10 — Start/stop control via control.json
**Decision:** A committed `control.json` (enabled flag + active date window) that
`main.py` checks first; when inactive it exits before any API call.
**Why:** Lets the owner pause/resume and auto-stop after the trip to control
usage/cost, without code changes or deleting the schedule. Works identically
locally and in GitHub Actions because the file is committed to the repo.

## D11 — Search concurrency (default 4 workers)
**Decision:** Searches run in parallel via a thread pool, sized by the
`SEARCH_WORKERS` knob, which defaults to `4`. Set it to `1` for the old
sequential behaviour, or lower it if a provider rate-limits you. The shared HTTP
`requests.Session` is safe to use across these threads because we never mutate
session state — every call passes its own headers/params and urllib3's
connection pool is itself thread-safe.
**Why:** A full date-range run is dominated by sequential network round-trips;
parallelism is the single biggest wall-clock win (≈10s → ≈3s at 4 workers in a
simulated run). `4` is a modest default that stays comfortably within the free
provider tiers while delivering most of the speedup. Concurrency cannot change
*which* fare wins: `normalize()` sorts purely by price, so result ordering is
irrelevant; the count of offers is identical to sequential.
**Trade-off / known limitation:** Higher worker counts make more requests in a
short window, which a rate-limited provider (notably SerpApi's small free quota)
may answer with HTTP 429. We mitigate per request — 429-aware backoff that
honours a numeric `Retry-After` — but there is **no global throttle**, so under
heavy concurrency several threads can back off and retry around the same time.
Keep `SEARCH_WORKERS` modest (≈4) for the free tiers; raise only if a provider
tolerates it. The HTTP-date form of `Retry-After` is not parsed (rare for these
providers); it degrades to exponential backoff.
**Rejected:** A high default worker count (risks the free quotas); a global
token-bucket throttle (more machinery than a one-route monitor needs at 4
workers); async/aiohttp (larger rewrite, no real gain at this scale).
