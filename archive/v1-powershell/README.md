# v1 — PowerShell (ARCHIVED, retired)

This folder is the original FlightGuru v1: a single PowerShell script
(`FlightGuru.ps1`) that fetched prices via SerpApi (Google Flights) and sent
Telegram alerts, scheduled with Windows Task Scheduler.

It has been **retired** and replaced by the v2 Python rebuild in the repo root.
Kept here for reference and recovery only — do not run as the live monitor.

Why retired (see `docs/DECISIONS.md` in the project root for full detail):
- Relied on scraping search-result pages (display prices, no tax/fee breakdown).
- Month-fallback logic could report a non-target month as if it were August.
- Telegram HTML mode could silently drop alerts containing `&`.
- CSV header drifted out of sync with the data being written.

Contents: `FlightGuru.ps1`, `config.json` (secrets, git-ignored),
`config.example.json`, `state.json`, `logs/`.
