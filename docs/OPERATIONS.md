# OPERATIONS.md

## Run a check now
GitHub → **Actions** tab → **flightguru** → **Run workflow**.
Or locally: `python -m flightguru.main`.

## Pause / resume / set active window (control usage)
Edit `control.json` at the repo root, then push (to apply in the cloud):
- **Pause now:** set `"enabled": false`. The next run exits immediately and makes
  **no API calls**. Set back to `true` to resume.
- **Auto-start / auto-stop:** `"active_from"` and `"active_until"` (YYYY-MM-DD,
  UTC). Monitoring only runs within that window — so it stops on its own after
  the trip dates. Leave a date as `""` to remove that bound.

Example — paused:
```json
{ "enabled": false, "active_from": "2026-06-10", "active_until": "2026-08-14" }
```
(You can also fully stop the schedule via GitHub → Actions → flightguru → "…" → Disable workflow.)

## See history
Open `data/flightguru.db` (any SQLite viewer), or review the commit history of
that file in the repo.

## Common issues
- **No alerts arriving:** check the latest `flightguru` run logs in the Actions tab;
  confirm the four secrets are set; confirm the Telegram chat ID is correct.
- **"Missing required environment variable":** a secret/`.env` value is unset.
- **Nothing happens:** the flightguru workflow is manual-only — it only runs when you trigger
  it (GitHub app, `gh workflow run flightguru.yml`, a phone Shortcut, or the Claude
  GitHub connector). There is no automatic schedule by design.
- **Amadeus errors:** verify keys, and that `AMADEUS_ENV` matches the keys' tier
  (test vs production).

## Health check
Run `python -m flightguru.main --health` (or trigger it in Actions). It verifies
a provider is configured and that the Telegram bot is reachable. Exit code 0 = OK.

## Monitoring
- Every run sends a Telegram message — that doubles as a heartbeat: if messages
  stop arriving, something is wrong, check the latest `flightguru` run logs.
- Local runs also write a timestamped, rotating log to `logs/flightguru.log`.
- Transient API failures auto-retry with backoff (`net.py`); persistent ones are
  logged and skipped without aborting the run.

## Backup & disaster recovery
- **Backup:** the price history (`data/flightguru.db`) is committed to git every
  run, so its full change history lives in the repo — every clone is a backup.
- **Rebuild from scratch:** clone repo, set the Actions secrets, run `flightguru`.
- The retired v1 remains in `archive/v1-powershell/` as a fallback.

## Recreating the "FlightGuru Bot" scheduled task

Registered 2026-08-09. Run this from the repo folder if the task is ever removed
and needs rebuilding:

```powershell
$root    = 'C:\vaibhav\Claude AI\FlightGuru'
$script  = Join-Path $root 'scripts\start_bot.ps1'
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
             -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
             -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -StartWhenAvailable `
             -ExecutionTimeLimit ([TimeSpan]::Zero) `
             -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'FlightGuru Bot' -Action $action -Trigger $trigger `
             -Settings $settings -Force
```

Two settings are load-bearing:

- `-ExecutionTimeLimit ([TimeSpan]::Zero)` — without it Windows kills the task
  after three days. The bot is meant to run indefinitely.
- `-AllowStartIfOnBatteries` / `-DontStopIfGoingOnBatteries` — otherwise the bot
  stops the moment a laptop is unplugged, which is exactly when you are most
  likely to be searching for a flight.

Verify with `Get-ScheduledTaskInfo -TaskName 'FlightGuru Bot'`; `LastTaskResult`
of 0 means it started cleanly.
