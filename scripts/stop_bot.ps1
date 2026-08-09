# Stop the FlightGuru bot.
#
# Ends the background pythonw process running flightguru.main. The scheduled task
# starts it again at your next login -- to stop that too:
#     Disable-ScheduledTask -TaskName 'FlightGuru Bot'

$running = @(Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*flightguru.main*' })

if ($running.Count -eq 0) {
    Write-Output 'FlightGuru bot is not running.'
    exit 0
}

# A single bot shows up as two processes: the venv's pythonw.exe redirector and
# the base interpreter it spawns. Stopping the parent takes the child with it, so
# by the time we reach the child it is usually already gone. That is the normal
# case, not an error, and it must not be reported as one.
$stopped = 0
foreach ($process in $running) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        $stopped++
    } catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
        # Already exited with its parent.
    }
}

if ($stopped -gt 0) {
    Write-Output "FlightGuru bot stopped."
} else {
    Write-Output 'FlightGuru bot was already stopping.'
}
