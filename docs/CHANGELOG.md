# CHANGELOG.md

All notable changes to FlightGuru. Newest first.

## [Unreleased] — Route-scoped history + duration/retry polish (2026-07-01)
- **Correctness (M3):** `get_last_total_price` now accepts `origin`/`destination`
  and `main.py` passes them, so the "dropped since last check" comparison only
  looks at snapshots for the *same route*. Changing `ORIGIN`/`DESTINATION` no
  longer compares this route's price against an unrelated route's last snapshot.
- **Fix (L1):** `iso_duration_to_minutes` now parses the day component
  (`P1DT2H30M`); a >24h itinerary was previously undercounted by a full day in
  the displayed duration.
- **Fix (L2):** `net.py` no longer retries a non-JSON 200 response. A malformed
  body is a hard failure (retrying the identical request can't fix it), so it now
  fails fast instead of burning all attempts + backoff. The raised message
  carries no URL, so no secret can leak from this path.
- (L3, the "no booking link -> no alert" guard, left as intentional defensive
  code — see report.)
- Tests: +4 (`test_storage`, `test_normalize`, `test_net`); 71 → 75 passing.
- Found by the `/tester` production review — see `NOTES_flightguru_tester_report.md`.

## [Unreleased] — SerpApi currency stamping (2026-07-01)
- **Correctness fix (M2):** `parse_serpapi` stamped every offer with the
  *requested* currency, so the currency guard in `normalize()` could never catch
  a mismatch (we'd labeled it ourselves). It now stamps the currency SerpApi
  reports having used (`search_parameters.currency`), falling back to the
  requested currency only when SerpApi doesn't echo one. If SerpApi ever prices
  in a different currency than asked, the offer now carries the real currency and
  the guard drops it instead of comparing, e.g., EUR against a USD target.
  (SerpApi gives no per-price currency, so this reflects its reported currency,
  not a per-price guarantee — Duffel remains the verified-currency source.)
- Verified: a fixture where SerpApi reports EUR while USD was requested now
  produces EUR offers, and a USD-preferred `normalize()` drops them.
- Tests: +3 (`test_serpapi.py`); 68 → 71 passing.
- Found by the `/tester` production review — see `NOTES_flightguru_tester_report.md`.

## [Unreleased] — control.json fails closed (2026-07-01)
- **Robustness fix (M1):** a malformed `control.json` (bad JSON, wrong shape, or
  a mistyped date like `2026-8-1`) used to crash the run with an uncaught
  exception — the load happened before `main.py`'s try/except. Since that file is
  meant to be hand-edited, a typo was a real risk. `load_control` now catches
  parse errors and `check_active` catches bad dates; both **fail closed** —
  monitoring is reported "not active" with a clear reason and **no API calls are
  made** until the file is fixed. Added a `Control.error` field.
- Verified end-to-end: `python -m flightguru.main` with a trailing-comma
  `control.json` now exits 0 with `Skipped - control.json could not be read (...)`
  instead of a traceback.
- Tests: +4 (`test_control.py`); 64 → 68 passing.
- Found by the `/tester` production review — see `NOTES_flightguru_tester_report.md`.

## [Unreleased] — Secret redaction in logs (2026-07-01)
- **Security fix (C1):** secrets could leak into logs on a request failure. A
  `requests` exception message contains the request URL, so a Telegram network
  error printed the bot token (`/bot<token>/sendMessage`) and a SerpApi 4xx
  printed the `api_key=` query param — into the console (GitHub Actions logs,
  world-readable on a public repo) and the log file. `log.py` now runs every
  record through a `_RedactingFilter` that strips Telegram bot tokens, `api_key=`
  params, and `Bearer` tokens before any handler sees them, so all current and
  future log lines are scrubbed. Added `log.redact()` (pure helper).
- Verified end-to-end: the same failing Telegram request that used to leak the
  token now logs `/bot<redacted>`.
- Tests: +5 (`test_log_redaction.py`); 59 → 64 passing.
- Found by the `/tester` production review — see `NOTES_flightguru_tester_report.md`.

## [Unreleased] — Currency guard (2026-07-01)
- `normalize()` now takes an optional `prefer_currency`. `main.py` passes
  `settings.currency`, so offers priced in another currency are excluded from the
  cheapest pick and the below-target check instead of being compared as if equal.
  This is latent today (SerpApi prices in USD) but would break the pick once
  Duffel is enabled, since Duffel prices in the account currency. Default of None
  keeps all currencies, so nothing changes for single-currency runs.
- `main.py` logs a clear hint when every offer is filtered out by currency.
- Tests: +2 (`test_normalize.py`).

## [Unreleased] — Review pass (2026-07-01)
- Wired up the `alerts_sent` table, which was written but never read. A
  below-target fare now alerts once and re-alerts only when the price drops below
  the last alerted price for that date, instead of alerting on every run. Added
  `storage.last_alert_price(depart_date)` and pure `delta.should_send_alert()`;
  the every-run heartbeat (`NOTIFY_EVERY_RUN=true`) is unchanged.
- Fixed: Duffel depart/arrive times were shown as raw ISO timestamps in the log and
  Telegram message; added `normalize.fmt_time()` so both providers display clean
  `YYYY-MM-DD HH:MM`.
- Fixed: `net.py` now honors the `Retry-After` header on 429/503 (capped at 60s) instead
  of always using fixed exponential backoff.
- Fixed: `load_settings()` no longer crashes on a non-numeric env var (e.g. a typo in
  `TARGET_PRICE`); `_int_env()` falls back to the default.
- Tests: +12 across `test_delta`, `test_storage`, `test_net`, `test_normalize`,
  `test_foundation`; 45 → 57 passing.
- See `NOTES_flightguru_review.md` for remaining flagged items (duplicate-alert risk on
  Telegram retry, Duffel date-cap optimization).

## [2.0.0] — Production release (2026-06-10)
- v2 Python rebuild complete: Phases 0–6. Multi-provider verified-price monitor
  (SerpApi live; Duffel ready for a live token), SQLite history, Telegram alerts,
  retries/logging/health checks, secret-leak guard, deployed on free GitHub Actions.
- Replaces the archived v1 PowerShell monitor.

## [2.0.0-dev] — Phase 5: Production Hardening
- Added `net.py`: HTTP with retry + 429/5xx-aware exponential backoff; all
  providers and Telegram now go through it.
- Added `log.py`: console + rotating file logging (logs/flightguru.log).
- Added `health.py` + `python -m flightguru.main --health` (checks providers + Telegram).
- Added `scripts/check_secrets.py` secret-leak guard; wired into CI (tests.yml).
- Tests: `test_net.py` (retry logic), `test_health.py`.
- Docs: backup = git history of data/flightguru.db; monitoring = logs + every-run heartbeat.

## [2.0.0-dev] — Phase 3: Price Monitoring Engine
- Added SQLite storage (`storage.py`): `price_snapshots` + `alerts_sent` tables;
  saves the cheapest verified offer per run; history commits back via the workflow.
- Added delta detection (`delta.py`): below-target + price-drop-since-last-check.
- Wired storage + delta into `main.py` (records each run, reports last price / drop).
- Tests: `test_storage.py`, `test_delta.py`.

## [2.0.0-dev] — Phase 2: Flight Search Engine
- Multi-provider search: Duffel + SerpApi (live "internet via API"); switched
  default to SerpApi-only until a live Duffel token (test token returns demo data).
- Added provider modules, `models.Offer`, normalize/validate/dedupe, search
  orchestration with date range + even sampling.
- Booking deep link switched from deprecated Google Flights `#flt=` to Kayak
  deterministic URLs (pre-fills reliably).
- Tests for both providers' parsing, normalization, deep links, and search dates.

## [2.0.0-dev] — Phase 1: Project Foundation
- Started v2 Python rebuild; retired v1 PowerShell to `archive/v1-powershell/`.
- Added package skeleton (`src/flightguru/`) with stub pipeline modules:
  search, normalize, deeplink, storage, delta, notify.
- Added working `config.py` (env-var/`.env` based) and a foundation `main.py`.
- Added pytest suite (`tests/test_foundation.py`) and `pyproject.toml`.
- Added GitHub Actions: `tests.yml` (CI) and `monitor.yml` (scheduled check + commit-back).
- Added start/stop usage control (`control.py` + `control.json`): pause/resume and
  an active date window that auto-stops monitoring; checked before any API call.
- Added docs: PROJECT, ARCHITECTURE, DECISIONS, SECURITY, TESTING, DEPLOYMENT, OPERATIONS.
- Added `.env.example`, `.gitignore`, `requirements.txt`.

## [1.x] — v1 PowerShell (archived)
- SerpApi + Telegram monitor on Windows Task Scheduler. See `archive/v1-powershell/`.
