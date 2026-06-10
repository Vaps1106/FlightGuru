# FlightGuru v2

Verified flight-price monitor. Checks real airfare (Amadeus), stores price
history, and alerts on Telegram when a fare beats the target — running **free**
on GitHub Actions.

> Route: **BOM → JFK**, target **< $700 USD**, departing **2026-07-20 → 2026-08-14**.

**Status:** Phase 1 (Project Foundation) complete. Flight search arrives in Phase 2.
The previous PowerShell version is retired under [`archive/v1-powershell/`](archive/v1-powershell/).

## How it works

A scheduled GitHub Actions workflow wakes up every few hours and runs the
pipeline: **search → normalize/validate → deep link → store → decide → notify**.
Each module lives in its own file under `src/flightguru/`. Price history is kept
in `data/flightguru.db` (SQLite) and committed back to the repo each run, so it
survives between runs at no cost.

## Project layout

```
.github/workflows/   monitor.yml (scheduled check) + tests.yml (CI)
src/flightguru/      the pipeline modules
tests/               pytest suite
data/                SQLite price history (committed back)
docs/                PROJECT, ARCHITECTURE, DECISIONS, etc.
archive/             retired v1 (PowerShell)
```

## Run it locally

1. Install Python 3.12+.
2. Create and activate a virtual environment (an isolated Python for this project):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your keys (see below).
5. Run the tests: `pytest`
6. Run the foundation: `python -m flightguru.main`

## Getting Amadeus keys (free)

1. Go to https://developers.amadeus.com and register a free account; confirm your email.
2. Sign in → **My Self-Service Workspace** → **Create new app**.
3. Copy the generated **API Key** and **API Secret**.
4. Put them in `.env` as `AMADEUS_CLIENT_ID` and `AMADEUS_CLIENT_SECRET`.
5. Keep `AMADEUS_ENV=test` (free tier) until we're ready for live production data.

## Secrets

Secrets never live in the code. Locally they sit in `.env` (git-ignored). In the
cloud they go in **GitHub → Settings → Secrets and variables → Actions**:
`AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`. See [`docs/SECURITY.md`](docs/SECURITY.md).

See [`docs/PROJECT.md`](docs/PROJECT.md) for the full picture.
