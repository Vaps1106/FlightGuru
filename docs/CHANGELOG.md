# CHANGELOG.md

All notable changes to FlightGuru. Newest first.

## [2.1.0] — Search performance & resilience (2026-06-15)
- **Parallel search** (`search.py`): provider/date searches now run concurrently
  via a thread pool, controlled by the new `SEARCH_WORKERS` setting (default `4`),
  cutting a full run from tens of seconds to a few. Set `SEARCH_WORKERS=1` for the
  old sequential behaviour, or lower it if a provider rate-limits you. Result
  order is preserved and per-`(provider, date)` error isolation is unchanged, so
  concurrency never changes which fare is chosen (verified by
  `test_search_all_sequential_and_parallel_match`).
- **Connection reuse** (`net.py`): all HTTP now goes through one shared
  `requests.Session`, reusing TCP/TLS connections across the many same-host calls
  in a run instead of re-handshaking each time.
- **Rate-limit politeness** (`net.py`): a numeric `Retry-After` header on an HTTP
  429 is now honoured (we wait at least that long) instead of only guessing with
  exponential backoff. Reduces dropped dates. (HTTP-date form of `Retry-After`
  is not parsed; it falls back to exponential backoff — see DECISIONS D11.)
- **Leaner DB writes** (`storage.py`): snapshot/alert writes use a single
  connection (schema + insert in one transaction) instead of opening a second
  connection per write.
- **No wasted quota** (`search.py`): `evenly_sample` de-duplicates its sampled
  dates so a scarce SerpApi call is never spent re-checking a date.
- Tests: added parallel-vs-sequential equivalence, error isolation, sample
  de-dup, and Retry-After coverage (39 → 43 passing).
- See DECISIONS D11 for the concurrency trade-off and known limitations.

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
