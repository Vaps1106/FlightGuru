#Requires -Version 5.1
# FlightGuru.ps1 - Flight Price Monitor (SerpApi / Google Flights - live prices)
#
# Usage:
#   .\FlightGuru.ps1            - run a price check right now
#   .\FlightGuru.ps1 -Install   - register Windows Task Scheduler (every 8 hours, no expiry)
#   .\FlightGuru.ps1 -Uninstall - remove the scheduled task

param(
    [switch]$Install,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# -- Paths --------------------------------------------------------------------
$Root       = $PSScriptRoot
$ConfigFile = Join-Path $Root "config.json"
$StateFile  = Join-Path $Root "state.json"
$LogDir     = Join-Path $Root "logs"
$LogFile    = Join-Path $LogDir "price_history.csv"

# -- Config -------------------------------------------------------------------
if (-not (Test-Path $ConfigFile)) {
    Write-Error "config.json not found. Copy config.example.json to config.json."
    exit 1
}
$Config = Get-Content $ConfigFile -Raw | ConvertFrom-Json

# -- Init ---------------------------------------------------------------------
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
if (-not (Test-Path $LogFile)) {
    "Timestamp,Airline,Flights,Date,DepTime,ArrTime,Duration,Stops,Layovers,Price_USD,Below_Target,BookingURL" |
        Out-File $LogFile -Encoding UTF8
}

# -- Fetch live flights via SerpApi (Google Flights) --------------------------
function Get-LiveFlights {
    param([string]$Origin, [string]$Destination, [string]$TargetMonth, [string]$ApiKey)

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    # Try 15th of target month; fall back to 15th of next two months if empty
    $datesToTry = @(
        "$TargetMonth-15",
        ([datetime]"$TargetMonth-01").AddMonths(-1).ToString("yyyy-MM") + "-15",
        ([datetime]"$TargetMonth-01").AddMonths(1).ToString("yyyy-MM")  + "-15"
    )

    foreach ($searchDate in $datesToTry) {
        Write-Host "  Trying $searchDate ..." -NoNewline

        $uri = "https://serpapi.com/search?engine=google_flights" +
               "&departure_id=$Origin&arrival_id=$Destination" +
               "&outbound_date=$searchDate&type=2&currency=USD&hl=en" +
               "&api_key=$ApiKey"

        try {
            $r = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 30

            $raw = @()
            if ($r.best_flights)  { $raw += $r.best_flights  }
            if ($r.other_flights) { $raw += $r.other_flights }

            if ($raw.Count -eq 0) {
                Write-Host " no data" -ForegroundColor Yellow
                continue
            }

            Write-Host " $($raw.Count) flights found" -ForegroundColor Green

            $results = [System.Collections.Generic.List[PSCustomObject]]::new()

            foreach ($f in $raw) {
                $legs      = $f.flights
                $firstLeg  = $legs[0]
                $lastLeg   = $legs[$legs.Count - 1]
                $stops     = $legs.Count - 1

                $flightNos = ($legs | ForEach-Object { $_.flight_number }) -join " + "
                $airline   = $firstLeg.airline
                $depTime   = $firstLeg.departure_airport.time
                $arrTime   = $lastLeg.arrival_airport.time

                $durH      = [int]($f.total_duration / 60)
                $durM      = $f.total_duration % 60
                $duration  = "${durH}h ${durM}m"

                $layovers  = ""
                if ($f.layovers -and $f.layovers.Count -gt 0) {
                    $layovers = ($f.layovers | ForEach-Object {
                        $lh = [int]($_.duration / 60)
                        $lm = $_.duration % 60
                        "$($_.id) (${lh}h ${lm}m)"
                    }) -join ", "
                }

                $stopsLabel = if ($stops -eq 0) { "Nonstop" } `
                              elseif ($stops -eq 1) { "1 stop" } `
                              else { "$stops stops" }

                $bookURL = "https://www.google.com/travel/flights#flt=" +
                           "$Origin.$Destination.$searchDate;c:USD;e:1;sd:1;tt:o"

                $results.Add([PSCustomObject]@{
                    SearchDate  = $searchDate
                    Airline     = $airline
                    FlightNos   = $flightNos
                    DepTime     = $depTime
                    ArrTime     = $arrTime
                    Duration    = $duration
                    Stops       = $stops
                    StopsLabel  = $stopsLabel
                    Layovers    = $layovers
                    Price       = [int]$f.price
                    URL         = $bookURL
                })
            }

            # Return sorted by price - first date with data wins
            return ($results | Sort-Object Price)
        }
        catch {
            Write-Host " error: $($_.Exception.Message)" -ForegroundColor Red
        }
    }

    return @()
}

# -- Telegram -----------------------------------------------------------------
function Send-TelegramMessage {
    param([string]$Message)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $token  = $Config.telegram.bot_token
    $chatId = $Config.telegram.chat_id
    $body   = @{ chat_id = $chatId; text = $Message; parse_mode = "HTML" } |
                ConvertTo-Json -Compress
    try {
        $r = Invoke-RestMethod `
            -Uri "https://api.telegram.org/bot$token/sendMessage" `
            -Method Post -Body $body `
            -ContentType "application/json; charset=utf-8"
        if ($r.ok) { Write-Host "  [Telegram] Sent." -ForegroundColor Green }
    }
    catch { Write-Warning "  [Telegram] Failed: $($_.Exception.Message)" }
}

# -- State --------------------------------------------------------------------
function Get-LastPrice {
    if (Test-Path $StateFile) {
        return [int]((Get-Content $StateFile -Raw | ConvertFrom-Json).last_price)
    }
    return 9999
}

function Save-State([int]$Price) {
    @{ last_price = $Price; updated = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") } |
        ConvertTo-Json | Out-File $StateFile -Encoding UTF8
}

# -- Log ----------------------------------------------------------------------
function Write-FlightLog {
    param($Flight, [bool]$Alert)
    $ts   = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts,$($Flight.Airline),$($Flight.FlightNos),$($Flight.SearchDate)," +
    "$($Flight.DepTime),$($Flight.ArrTime),$($Flight.Duration)," +
    "$($Flight.Stops),$($Flight.Layovers),$($Flight.Price),$Alert,$($Flight.URL)" |
        Out-File $LogFile -Append -Encoding UTF8
}

# -- Scheduler ----------------------------------------------------------------
$TaskName = "FlightGuru_Monitor"

function Install-Scheduler {
    $script   = Join-Path $Root "FlightGuru.ps1"
    $action   = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
    # 8 hours to stay within SerpApi 100 calls/month free tier
    $trigger  = New-ScheduledTaskTrigger `
        -Once -At (Get-Date).AddMinutes(2) `
        -RepetitionInterval (New-TimeSpan -Hours 8)
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask `
        -TaskName $TaskName -Action $action `
        -Trigger $trigger -Settings $settings `
        -RunLevel Limited -Force | Out-Null
    Write-Host ""
    Write-Host "  Task '$TaskName' registered." -ForegroundColor Green
    Write-Host "  Runs every 8 hours (stays within SerpApi free tier)." -ForegroundColor Gray
    Write-Host "  No expiry - you control when to stop." -ForegroundColor Gray
    Write-Host "  To remove: .\FlightGuru.ps1 -Uninstall" -ForegroundColor Gray
}

function Uninstall-Scheduler {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  Task '$TaskName' removed." -ForegroundColor Yellow
    } else {
        Write-Host "  Task '$TaskName' not found - nothing to remove." -ForegroundColor Gray
    }
}

# -- Main ---------------------------------------------------------------------
if ($Install)   { Install-Scheduler;   exit 0 }
if ($Uninstall) { Uninstall-Scheduler; exit 0 }

$origin      = $Config.search.origin_iata
$destination = $Config.search.destination_iata
$target      = [int]$Config.search.target_price
$month       = $Config.search.search_month
$apiKey      = $Config.serpapi.api_key
$originCity  = $Config.search.origin_city
$destCity    = $Config.search.destination_city

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  FlightGuru - Price Check" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  Route  : $originCity -> $destCity"
Write-Host "  Month  : $month"
Write-Host "  Target : Below `$$target USD"
Write-Host "  Source : Google Flights (live)"
Write-Host "  Time   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "--------------------------------"

$flights = Get-LiveFlights -Origin $origin -Destination $destination `
               -TargetMonth $month -ApiKey $apiKey

if ($flights.Count -eq 0) {
    Write-Warning "  No live data returned. Google Flights may not have inventory this far out."
    Send-TelegramMessage -Message "[FlightGuru] Check run at $(Get-Date -Format 'yyyy-MM-dd HH:mm')`nRoute: $originCity -> $destCity`nStatus: No live data available yet for $month. Will retry next cycle."
    exit 0
}

# Display results
Write-Host ""
Write-Host "  Results (sorted by price):" -ForegroundColor White
$flights | Select-Object -First 5 | ForEach-Object {
    Write-Host ("  `$$($_.Price)  {0,-22} {1}  {2,-8}  {3}" -f `
        $_.Airline, $_.FlightNos, $_.StopsLabel, $_.SearchDate)
}

$cheapest = $flights | Select-Object -First 1
$lastLow  = Get-LastPrice
$alert    = $cheapest.Price -lt $target

Write-Host ""
Write-Host ("  Cheapest : `$$($cheapest.Price)  $($cheapest.Airline)  $($cheapest.FlightNos)") -ForegroundColor Cyan
Write-Host "  Last low : `$$lastLow"
Write-Host "  Target   : Below `$$target"

Write-FlightLog -Flight $cheapest -Alert $alert
Save-State -Price $cheapest.Price

# Build Telegram report
$priceChangeLine = ""
if ($cheapest.Price -lt $lastLow -and $lastLow -ne 9999) {
    $drop = $lastLow - $cheapest.Price
    $priceChangeLine = "Note   : Price dropped `$$drop since last check!`n"
    Write-Host "  Price dropped `$$drop since last check!" -ForegroundColor Yellow
}

if ($alert) {
    $statusLine = "Status : *** PRICE BELOW TARGET ***"
    Write-Host "  *** PRICE BELOW TARGET - sending alert ***" -ForegroundColor Green
} else {
    $statusLine = "Status : Above target (monitoring...)"
    Write-Host "  Price `$$($cheapest.Price) is above target `$$target." -ForegroundColor Yellow
}

# Top 3 flight details block
$flightBlock = ""
$rank = 1
$flights | Select-Object -First 3 | ForEach-Object {
    $flightBlock += "#$rank  $($_.Airline)`n"
    $flightBlock += "     Flights  : $($_.FlightNos)`n"
    $flightBlock += "     Date     : $($_.SearchDate)`n"
    $flightBlock += "     Departs  : $($_.DepTime)`n"
    $flightBlock += "     Arrives  : $($_.ArrTime)`n"
    $flightBlock += "     Duration : $($_.Duration)`n"
    $flightBlock += "     Stops    : $($_.StopsLabel)"
    if ($_.Layovers -ne "") { $flightBlock += " via $($_.Layovers)" }
    $flightBlock += "`n"
    $flightBlock += "     Price    : `$$($_.Price) USD`n"
    $flightBlock += "     Book     : $($_.URL)`n`n"
    $rank++
}

$msg = "[FlightGuru] Price Report`n" +
       "$(Get-Date -Format 'yyyy-MM-dd HH:mm')`n" +
       "--------------------------------`n" +
       "Route  : $originCity -> $destCity`n" +
       "Target : Below `$$target USD`n" +
       $priceChangeLine +
       $statusLine + "`n" +
       "--------------------------------`n`n" +
       "Top Flights:`n`n" +
       $flightBlock

Send-TelegramMessage -Message $msg

Write-Host ""
Write-Host "  Log: logs\price_history.csv"
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
