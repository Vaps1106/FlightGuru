# DEPLOYMENT.md

## Where it runs

**On your own PC**, started automatically at login by a Windows scheduled task.

Cloud hosting was considered and deliberately not used — see "Why not the cloud"
below. The `Procfile` and `railway.json` in the repo are leftovers from that
evaluation and are not in use.

The practical consequence: **the bot answers only while your PC is on and awake.**
Message it from the road with the machine asleep and nothing comes back until you
are home. Everything else works exactly the same.

## Day-to-day

| To do this | Run this |
|---|---|
| Start the bot | `.\scripts\start_bot.ps1` |
| Stop the bot | `.\scripts\stop_bot.ps1` |
| See what it's doing | `Get-Content logs\flightguru.log -Tail 20` |
| Check it's healthy | `$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m flightguru.main --health` |

The bot runs windowless via `pythonw.exe`, so there is nothing on screen. That is
why the log matters: it is timestamped, rotated, and has secrets stripped out, so
it is safe to read and safe to paste when asking for help.

Starting twice is harmless — `start_bot.ps1` refuses if the bot is already up.
That guard exists because two bots polling the same Telegram token each receive a
random share of the messages, which breaks a conversation apart mid-question with
no obvious cause.

**A single bot appears as two processes.** On Windows the venv's `pythonw.exe` is
a small redirector that launches the base interpreter as its child. Only the child
is polling. Seeing two PIDs is normal.

## The scheduled task

Named **FlightGuru Bot**, triggered at logon.

```powershell
Get-ScheduledTask     -TaskName 'FlightGuru Bot'   # is it registered
Get-ScheduledTaskInfo -TaskName 'FlightGuru Bot'   # LastTaskResult 0 = fine
Start-ScheduledTask   -TaskName 'FlightGuru Bot'   # run it now
Disable-ScheduledTask -TaskName 'FlightGuru Bot'   # stop it starting at login
Enable-ScheduledTask  -TaskName 'FlightGuru Bot'
Unregister-ScheduledTask -TaskName 'FlightGuru Bot' -Confirm:$false   # remove it
```

Disabling the task does not stop a bot that is already running — use
`stop_bot.ps1` for that.

To recreate the task from scratch, see the registration command in
`docs/OPERATIONS.md`.

## Configuration

Everything lives in `.env` at the repo root, which is git-ignored. Copy
`.env.example` and fill it in.

| Variable | Required | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | From @BotFather |
| `TELEGRAM_CHAT_ID` | yes | Who may use the bot. **Empty means it ignores everyone** — deliberately, so a leaked token cannot burn your search quota. `*` allows anyone. Comma-separate for several people. |
| `SERPAPI_API_KEY` | yes | Free tier ~100 searches/month, shared with PriceGuru |
| `CURRENCY` | no | Default `USD` |
| `NEARBY_ENABLED` | no | Default `true` |
| `NEARBY_RADIUS_MILES` | no | Default `100`, about a two-hour drive |
| `NEARBY_DESTINATION` | no | Default `false` — also check airports near where you're landing |
| `POLL_TIMEOUT` | no | Default `30` seconds |

Changing `.env` needs a restart: `.\scripts\stop_bot.ps1` then `.\scripts\start_bot.ps1`.

## Search quota

One trip search costs **one** SerpApi search no matter how many airports it
covers, because Google Flights takes a comma-separated airport list. Repeating an
identical search within an hour is served from cache and is free.

At roughly 100 searches a month, that is about three trip searches a day. The bot
does not run anything in the background, so nothing is spent unless you ask.

## Troubleshooting

**The bot doesn't reply at all.**
Check it is running (`.\scripts\start_bot.ps1` will say so), then check
`TELEGRAM_CHAT_ID` is set — an empty value silently ignores every message, and the
log says so at startup.

**The log is full of `ConnectionResetError` to api.telegram.org.**
Expected on this machine. Its network resets roughly a quarter of TLS handshakes
to `api.telegram.org` specifically, while other hosts are unaffected — the
signature of ISP-level filtering of Telegram. The bot retries enough to work
through it (4 attempts per poll, 6 per message, and a failure at startup is not
fatal). If replies feel slow, this is why. It is not a fault in the code.

**Searches fail but Telegram works.**
Check the SerpApi quota at serpapi.com. `--health` reports whether the key is
configured but deliberately does not spend a search to test it.

## Why not the cloud

Railway was chosen first, then ruled out by the owner on 2026-08-09 after the code
was already portable. It would have kept the bot answering with the PC off, and it
would have avoided the Telegram connection resets described above.

Running locally is the trade that was chosen instead: no hosting account, no
monthly cost, nothing running anywhere you cannot see. The code has no dependency
on where it runs, so this can be revisited without changes.

## Tests

`tests.yml` runs the suite on every push and PR. The old `flightguru.yml`
monitoring workflow is archived at `archive/v2-monitor/workflows/`.
