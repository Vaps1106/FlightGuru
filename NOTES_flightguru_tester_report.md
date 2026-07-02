# FlightGuru — Production Tester Report

Date: 2026-07-01 · Scope: `src/flightguru/` (v2 Python package) · Method: code read + mentally executed + 5 live probes run against the actual `.venv` (requests 2.34.2). Test suite: 59/59 pass.

## Executive Summary

Overall: Well-structured, well-documented, well-tested personal monitor. The pipeline (control gate → search → normalize → delta → notify) is clean and the "never invent data" validation is genuinely enforced. **But there is a proven secret-leak into logs that is release-blocking in this app's actual deployment (GitHub Actions).**

- Risk level: **High** (Critical if the repo / Actions logs are public)
- Production recommendation: **Needs Significant Changes** — fix secret redaction before relying on it in CI; the rest are correctness/robustness polish.

The "millions of users" framing doesn't apply (single-user tool), so scores below are judged against *its own* reliability bar, not web-scale.

---

## Critical Issues

**C1 — Telegram bot token & SerpApi key leak into logs on failure. (PROVEN)**
`net.py` logs the raw exception on every retry (`request failed ({exc})`), and `main.py` logs `Telegram: failed - {exc}`, and `health.py` returns `str(exc)`. The `requests` exception string contains the full URL.

Proven live:
- Telegram POST → any network error → exception string contains `/bot<TOKEN>/sendMessage` verbatim. (`TOKEN IN EXC MSG: True`)
- SerpApi GET → a 401/403/404 (e.g. bad/expired key) → `resp.raise_for_status()` raises `"401 Client Error ... for url: https://serpapi.com/search?...&api_key=<KEY>"`, which flows into `on_error` → logged as `warn: serpapi <date>: ...`. (`KEY IN raise_for_status MSG: True`)

Why Critical *here*: the app runs in **GitHub Actions** (`.github/workflows/flightguru.yml`), and Actions writes stdout/console + the rotating `logs/flightguru.log`. For a public repo, workflow logs are world-readable → a single Telegram network blip publishes the bot token = full bot takeover. The rotating log file could also be committed if not git-ignored.

Fix: redact before logging. Sanitize the exception/URL, e.g.:
```python
import re
def _safe(msg: str) -> str:
    msg = re.sub(r"/bot\d+:[\w-]+", "/bot<redacted>", msg)
    msg = re.sub(r"(api_key=)[^&\s]+", r"\1<redacted>", msg)
    return msg
# then: log.warning(f"request failed ({_safe(str(exc))}); ...")
```
Apply in `net.py`, `main.py` (Telegram failure line), and `health.py` (`telegram_check` return). Also confirm `logs/` is git-ignored.

---

## High Severity Issues

*(none beyond C1 — the token leak is the only high-impact defect found)*

---

## Medium Issues

**M1 — Malformed/typo'd `control.json` crashes the whole run (uncaught).**
`main()` calls `check_active(load_control())` *before* any try/except. `load_control` does `json.loads(...)` (raises `JSONDecodeError` on a stray comma) and `check_active` does `date.fromisoformat(active_from)` (raises `ValueError` on `"2026-8-1"` or a typo). `control.json` is *explicitly designed to be hand-edited by the owner* (per its docstring), so a human typo → unhandled exception → non-zero exit, no Telegram, silent-ish failure. Wrap the control load/check in try/except and treat a bad file as "paused, log why".

**M2 — SerpApi prices are stamped with the *requested* currency, not the confirmed one. (PROVEN)**
`parse_serpapi(..., currency=currency)` sets `Offer.currency` to whatever we asked for (`settings.currency`), regardless of what SerpApi actually priced in. The currency guard in `normalize(prefer_currency=...)` then always matches for SerpApi (we labeled it ourselves), so it is a **no-op for SerpApi** and can't catch a mismatch. If SerpApi ever ignores the `currency` param (locale/account effects are documented behavior for Google Flights scraping), a EUR price gets compared to a USD target and mislabeled. The guard only really protects against Duffel, which reports its true `total_currency`. Consider reading SerpApi's returned currency field where present, or clearly documenting this as an unverifiable assumption.

**M3 — "dropped since last check" can compare different flights/dates, and different routes.**
`get_last_total_price()` returns the most recent snapshot's `total_price` with no filter on route or depart_date. Each run's "cheapest in range" may be a *different* departure date than last run's, so `dropped X` compares two different flights. And if `ORIGIN`/`DESTINATION` env vars change, history silently mixes routes. For a cheapest-in-range tracker this may be acceptable by design, but the Telegram wording ("dropped since last check") implies same-fare tracking it doesn't do. Either scope the query by route (+ optionally date) or soften the message.

---

## Low Issues

- **L1 — `iso_duration_to_minutes` ignores a day component.** `PT20H55M` works; a `P1DT2H…` (>24h itinerary) parses only `H`/`M` and undercounts by a day. Display-only (`minutes_between` uses real datetimes, unaffected). Add `(\d+)D` handling.
- **L2 — Non-JSON 200 response is retried pointlessly.** `resp.json()` raises `requests.JSONDecodeError` (confirmed subclass of `RequestException`), so it's safely caught — but a genuinely non-JSON 200 will burn all 3 attempts + backoff before failing. Not harmful, just wasteful. Optional: don't retry decode errors.
- **L3 — "no booking link → no alert" branch is near-dead code.** `build_deep_link` only returns `None` when origin/dest/date are blank, but those come from settings defaults and `offer.search_date` is always set, so `link is None` in `main.py` is effectively unreachable in normal operation. Fine as defensive code; just noting it isn't exercised.

---

## Hallucination Findings

None. Spot-checked every external API shape against the code:
- Duffel `POST /air/offer_requests?return_offers=true`, `data.offers[].{total_amount,base_amount,tax_amount,total_currency,slices[].segments[]}` — consistent and real.
- SerpApi `engine=google_flights`, `best_flights`/`other_flights`/`layovers`/`flights[]` — consistent.
- Telegram `getMe` / `sendMessage`, `ok` field — correct.
No invented functions, imports, or SDK methods. `requests`, `python-dotenv`, `sqlite3` all real and used correctly.

## Security Findings

- **C1** (secrets in logs) — the one real security bug; proven.
- Secrets sourced from env / `.env` (git-ignored) — good, no hardcoded secrets in source. `scripts/check_secrets.py` exists as a guard.
- Telegram sent as plain text (no parse_mode) — deliberately avoids HTML-injection/`&`-drop bug from v1. Good.
- No SQL injection surface: all queries parameterized. No user-controlled input reaches shell/FS/eval.
- SSRF/path-traversal: URLs are constructed from fixed hosts + config, not attacker input. N/A for this tool.

## Performance Findings

- Search is IO-bound and correctly parallelized with a bounded `ThreadPoolExecutor` (workers ≤ tasks). Deterministic reassembly via per-index slots is thread-safe under CPython. Good.
- SerpApi quota protected by `serpapi_max_dates` + `evenly_sample` (verified: **no duplicate date picks** across sizes 2–39, so no wasted paid calls). Hypothesis of duplicate calls was tested and **disproven**.
- SQLite: opens a fresh connection per call (`save`, `get_last`, `count`, `last_alert`) — 4–5 connects per run. Negligible at this scale; would matter only at high frequency.
- Big-O: search O(providers × dates) network calls; normalize O(n log n) sort. All fine for the data volume (tens of offers).

## Missing Test Cases

1. Secret redaction on Telegram/SerpApi failure (currently *nothing* asserts tokens stay out of logs — the leak has no test).
2. Malformed `control.json` (bad JSON, bad date string) — M1 path is untested.
3. SerpApi returning a currency different from the requested one (M2).
4. `dropped` message when this run's cheapest is a different depart_date than last run's (M3).
5. `iso_duration_to_minutes` with a `P…D…` day component (L1).
6. `net.request_json` receiving a 200 with a non-JSON body (L2).

## Recommended Improvements (highest impact first)

1. **Redact secrets in all log paths** (`net.py`, `main.py`, `health.py`) + confirm `logs/` git-ignored. *(release-blocker)*
2. Guard the `control.json` load/parse against typos (M1).
3. Decide + document the SerpApi currency contract; stop letting the guard silently pass it (M2).
4. Scope price-history comparison by route (M3).
5. Add the six missing tests above; add L1/L2 polish.

---

## Final Production Score

| Category | Score |
|---|---|
| Correctness | 8/10 |
| Reliability | 6/10 (control.json crash, cross-date compare) |
| Security | 4/10 (proven secret leak into CI logs) |
| Performance | 9/10 |
| Maintainability | 9/10 |
| Readability | 10/10 |
| Testing | 8/10 (good coverage, gaps around failure/secret paths) |
| Scalability | 8/10 (fine for scope) |
| Observability | 7/10 (logs good, but leak secrets) |
| Deployment readiness | 5/10 (blocked by C1 in CI) |

**Overall Score: 74/100 · Confidence: 88%**

**Deployment Recommendation: Needs Significant Changes.** Functionally the tool works and is unusually clean for a personal project. The single blocker is the proven secret leak (C1) — cheap to fix, high impact given the GitHub Actions deployment. After C1 + M1, this is comfortably "Ready with Minor Fixes."
