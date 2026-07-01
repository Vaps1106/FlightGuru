# CHANGELOG.md

All notable changes to FlightGuru. Newest first.

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
