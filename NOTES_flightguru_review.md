# FlightGuru — Bug & Optimization Review (2026-07-01)

Loop-driven review of the v2 Python app. Baseline: 45 tests passing. After fixes: 51 passing.

## Fixed this pass (with tests)

### 1. Duffel times shown as raw ISO timestamps  — BUG (display)
Duffel returned `depart_time`/`arrive_time` as full ISO (`2026-07-20T02:15:00-04:00`) and
they went straight into the log **and the Telegram message** unformatted, while SerpApi
already shows clean `2026-07-20 08:00`. So a Duffel alert looked like
`Depart 2026-07-20T02:15:00-04:00 -> arrive ...` — ugly and inconsistent.
- **Fix:** added `normalize.fmt_time()` (ISO → `YYYY-MM-DD HH:MM`, pass-through if not ISO);
  applied it in `parse_duffel`. SerpApi already-clean strings pass through unchanged.
- Tests: `test_fmt_time_*` in `test_normalize.py`.

### 2. `net.py` ignored the `Retry-After` header  — BUG (rate-limit correctness)
The module advertises "429-aware backoff," but on a 429/503 it used a fixed exponential
delay and **ignored the `Retry-After` header** that SerpApi/Telegram/Duffel send to say
exactly how long to wait. Result: we could retry too early (wasted call, still throttled)
or later than needed.
- **Fix:** `_retry_after_seconds()` reads the numeric `Retry-After` header and waits that
  long, capped at `RETRY_AFTER_CAP = 60s` so one run can't hang. Falls back to exponential
  backoff when the header is absent or in HTTP-date form.
- Tests: `test_honors_retry_after_header`, `test_retry_after_is_capped`.

### 3. `load_settings()` could crash the whole run on a typo  — BUG (robustness)
`int(os.environ.get("TARGET_PRICE", "700"))` raises `ValueError` on a bad value (e.g.
`7O0` with a letter O). `main.py` only catches `RuntimeError`, so the run would crash with
a traceback instead of exiting cleanly.
- **Fix:** `_int_env(name, default)` returns the default on unset/non-numeric input;
  used for `SEARCH_DATE_STEP`, `SEARCH_MAX_WORKERS`, `SERPAPI_MAX_DATES`, `TARGET_PRICE`.
- Test: `test_int_env_defaults_and_bad_values`.

## Flagged — NOT changed (need your call)

### A. Telegram alert can be sent twice  — BUG (low probability)
`net.request_json` retries **all** methods, including the non-idempotent Telegram
`sendMessage` POST. If Telegram returns 500 or times out *after* actually delivering,
the retry sends a **duplicate alert**. Options: (a) don't retry POSTs on timeout, only on
explicit 429/503; (b) pass `retries=1` for Telegram; (c) leave it (duplicates are rare and
harmless-ish). I left it because retrying a transient Telegram 5xx is usually what you want
— your call on the trade-off.

### B. `alerts_sent` table is written but never read  — FIXED (2026-07-01)
Wired up in the alert-dedup change: `storage.last_alert_price()` + pure
`delta.should_send_alert()`. A below-target fare now alerts once and re-alerts only when
the price drops below the last alerted price for that date. Heartbeat mode unchanged.

### G. Cross-currency prices compared as equal  — FIXED (2026-07-01)
`normalize()` sorted/compared `total_price` across offers regardless of currency, so a
Duffel fare priced in the account currency (e.g. GBP) could win over a USD fare and skew
the below-target check. Latent today (SerpApi is USD-only) but real once Duffel is enabled.
Fixed with `normalize(offers, prefer_currency=...)`; `main.py` passes `settings.currency`
and logs a hint if everything is filtered out by currency.

### C. Duffel searches all 26 dates every run  — OPTIMIZATION
SerpApi is capped (`serpapi_max_dates`), but Duffel hits every date in the range each run.
Search is free, so it's not a cost issue, but it's 26 sequential-ish API calls. If runs get
slow, give Duffel its own date cap/step or widen `search_max_workers` for it.

### D. Shared worker pool can burst SerpApi  — MINOR
`search_max_workers=6` is shared across all provider tasks, so up to 6 SerpApi calls can
fire at once and trip its rate limit (net.py retries, so it self-heals). Per-provider
concurrency caps would be cleaner if it becomes a problem.

### E. `get_logger()` `_configured` global has a threading race  — THEORETICAL
Two threads entering setup at once could double-add handlers (duplicate log lines).
Currently safe because `main.py` builds the logger at import, before any threads start.
Only matters if the logger is first created inside a worker. Low priority.

### F. `build_deep_link` None-branch is effectively dead  — TIDY-UP
Origin/dest/date are always present, so the "no link → no alert" guard never triggers in
practice. Harmless; just noting it's dead code as written.

## Post-fix verification (2026-07-01)
- Live `python -m flightguru.main --health`: **ALL OK** — providers_configured: serpapi;
  telegram: @VapsFlight_bot reachable. Fixes did not break the running app.
- Full suite: **51 passed**.

## Verified healthy
- Concurrency in `search_all`: deterministic result ordering, per-error locking, one failed
  (provider, date) doesn't abort the run. Solid.
- `normalize`: rejects offers missing price/currency/times/airline; dedup + deterministic
  cheapest pick. Good "never invent data" guardrail.
- Control gate + config placeholder detection: clean early exits, no wasted API calls.
