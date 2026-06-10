# CHANGELOG.md

All notable changes to FlightGuru. Newest first.

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
