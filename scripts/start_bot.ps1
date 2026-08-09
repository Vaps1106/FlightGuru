# Launch the FlightGuru bot in the background.
#
# Used by the "FlightGuru Bot" scheduled task, which runs this at login. Can also
# be run by hand if you ever want the bot going without the task.
#
# Uses pythonw.exe rather than python.exe so nothing appears on screen. That
# discards console output, which is fine: the bot writes a timestamped, secret-
# redacted log to logs\flightguru.log regardless, and that is the thing worth
# reading when something looks wrong.

$ErrorActionPreference = 'Stop'

# The project root is one level up from this script, wherever it has been moved to.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# .env is read from the working directory, and data\ and logs\ are relative to
# it too, so the location above matters more than it looks.
$env:PYTHONPATH = 'src'

$pythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    throw "No virtualenv found at $pythonw. Create it with: python -m venv .venv"
}

# Only one instance may run. Two bots polling the same Telegram token would each
# receive a share of the messages at random, so a conversation would break apart
# mid-question with no obvious cause.
#
# Expect this to match TWO processes for a single bot: on Windows the venv's
# pythonw.exe is a small redirector that launches the base interpreter as its
# child. Only the child is actually polling.
$running = @(Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*flightguru.main*' })
if ($running.Count -gt 0) {
    $pids = ($running | ForEach-Object { $_.ProcessId }) -join ', '
    Write-Output "FlightGuru bot is already running (PID $pids). Nothing to do."
    exit 0
}

Start-Process -FilePath $pythonw `
              -ArgumentList '-m', 'flightguru.main' `
              -WorkingDirectory $root `
              -WindowStyle Hidden

Write-Output "FlightGuru bot started. Log: $(Join-Path $root 'logs\flightguru.log')"
