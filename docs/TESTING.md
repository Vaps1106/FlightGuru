# TESTING.md

## How to run
```powershell
pytest                 # all tests
pytest --cov=flightguru # with coverage
```
CI runs the same on every push via `.github/workflows/tests.yml`.
**No phase proceeds while tests fail.**

## Strategy by phase
- **Unit tests** (target 90%+ coverage): each pipeline module in isolation,
  using saved sample API responses (no live calls).
- **Integration tests** (Phase 2+): real Amadeus *test* environment, DB writes,
  Telegram send to a test chat.
- **End-to-end** (Phase 3+): full search → store → notify on sample data.
- **Chaos** (Phase 5): simulate API outages, slow/invalid responses, DB failures.
- **Regression**: full suite before every release.

## Current status (Phases 1–3)
All unit tests run without network or real keys (providers tested via saved
sample responses; storage uses isolated temp DBs):
- `test_foundation.py` — imports, provider gating, clean `main()` run.
- `test_control.py` — pause/resume + active window.
- `test_search.py` — date range + even sampling.
- `test_duffel.py` / `test_serpapi.py` — response parsing.
- `test_normalize.py` — validation, dedupe, sort.
- `test_deeplink.py` — Kayak deep-link construction.
- `test_storage.py` / `test_delta.py` — SQLite history + price-drop logic.

Live integration (real API calls) is verified manually and needs real keys.
