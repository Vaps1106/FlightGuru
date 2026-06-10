# DEPLOYMENT.md

## Where it runs
GitHub Actions — no server. Two workflows:
- `flightguru.yml` — **manual-only** price check (`workflow_dispatch`); runs when you
  trigger it. Commits updated `data/flightguru.db` back to the repo.
- `tests.yml` — runs the test suite on every push/PR.

## How to trigger a run
- **GitHub mobile app / website:** Actions → flightguru → Run workflow.
- **Command line:** `gh workflow run flightguru.yml`
- **Claude mobile app:** with the GitHub connector enabled (Actions read+write),
  ask Claude to "run the flightguru workflow in Vaps1106/FlightGuru on master".
- **Phone Shortcut:** POST to
  `https://api.github.com/repos/Vaps1106/FlightGuru/actions/workflows/flightguru.yml/dispatches`
  with body `{"ref":"master"}` and a fine-grained token (Actions: read+write).

## The four cloud secrets
Set these as GitHub Actions secrets (the cloud equivalent of `.env`):
`DUFFEL_ACCESS_TOKEN`, `SERPAPI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## One-time setup (via the GitHub CLI)
```powershell
# from the repo folder
gh secret set DUFFEL_ACCESS_TOKEN  --body "duffel_live_..."
gh secret set SERPAPI_API_KEY      --body "your_serpapi_key"
gh secret set TELEGRAM_BOT_TOKEN   --body "12345:abc..."
gh secret set TELEGRAM_CHAT_ID     --body "6889043609"

git push -u origin master           # publish the code
gh workflow run flightguru.yml         # trigger one cloud run to verify
gh run watch                        # watch it finish
```
Or do it in the browser: Settings → Secrets and variables → Actions → New secret,
then Actions tab → flightguru → Run workflow.

## Release checklist
1. `pytest` green and `python scripts/check_secrets.py` passes.
2. Four secrets set (above). `.env` is NOT pushed (git-ignored).
3. Code pushed; `tests` workflow passes on GitHub.
4. `flightguru` triggered once; a Telegram message arrives and `data/flightguru.db`
   is committed back by the run.
5. Confirm the 8-hour schedule is active (Actions tab shows upcoming runs).

## Re-enabling an automatic schedule (optional)
The flightguru workflow is manual-only by default. To make it run on a timer again, add a
`schedule` block under `on:` in `flightguru.yml`, e.g. `- cron: "0 */8 * * *"`
(every 8 hours, UTC). Format is `minute hour day month weekday`.

## Notes
- Manual runs have no timing concerns; each run is one search + one Telegram report.
- Keep the repo **private**; usage stays within the free Actions minutes.
