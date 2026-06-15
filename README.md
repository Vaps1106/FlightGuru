# FlightGuru v2

Verified flight-price monitor. Checks real airfare (Duffel + SerpApi/Google
Flights), stores price history, and alerts on Telegram when a fare beats the
target — running **free** on GitHub Actions.

> Route: **BOM → JFK**, target **< $700 USD**, departing **2026-07-20 → 2026-08-14**.

**Status:** v2 production release — full pipeline live (multi-provider search,
SQLite history, Telegram alerts, retries/logging/health). The previous PowerShell
version is retired under [`archive/v1-powershell/`](archive/v1-powershell/).

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

## Getting provider keys (free)

The monitor reads from one or both flight providers — whichever keys you supply
(see `PROVIDERS` in `.env.example`). Each is free to start.

**Duffel** (real, bookable fares with a tax/fee breakdown):
1. Sign up at https://app.duffel.com and verify your email.
2. Create an **access token** under **Developers → Access tokens**.
3. Put it in `.env` as `DUFFEL_ACCESS_TOKEN` (leave `DUFFEL_VERSION=v2`).

**SerpApi** (Google Flights display prices; free tier ~100 searches/month):
1. Sign up at https://serpapi.com and confirm your account.
2. Copy your **API key** from the dashboard.
3. Put it in `.env` as `SERPAPI_API_KEY`.

## Secrets

Secrets never live in the code. Locally they sit in `.env` (git-ignored). In the
cloud they go in **GitHub → Settings → Secrets and variables → Actions**:
`DUFFEL_ACCESS_TOKEN`, `SERPAPI_API_KEY`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`. See [`docs/SECURITY.md`](docs/SECURITY.md).

See [`docs/PROJECT.md`](docs/PROJECT.md) for the full picture.
