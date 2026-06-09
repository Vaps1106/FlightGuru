#Requires -Version 5.1
# FlightGuru.ps1 - Flight Price Monitor (Travelpayouts API)
#
# Usage:
#   .\FlightGuru.ps1            - run a price check right now
#   .\FlightGuru.ps1 -Install   - register Windows Task Scheduler (every 6 hours, no expiry)
#   .\FlightGuru.ps1 -Uninstall - remove the scheduled task

param(
    [switch]$Install,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# Required for HTTPS on Windows 10 / PowerShell 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

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
if (-not (Test-Path $LogDir))  { New-Item -ItemType Directory -Path $LogDir | Out-Null }
if (-not (Test-Path $LogFile)) {
    "Timestamp,Airline,FlightNo,DepartureDate,DepartureTime,Stops,Price_USD,Below_Target,BookingURL" |
        Out-File $LogFile -Encoding UTF8
}

# -- Airline code lookup ------------------------------------------------------
$AirlineNames = @{
    "AI" = "Air India"
    "EY" = "Etihad Airways"
    "EK" = "Emirates"
    "QR" = "Qatar Airways"
    "BA" = "British Airways"
    "RJ" = "Royal Jordanian"
    "GF" = "Gulf Air"
    "KU" = "Kuwait Airways"
    "UA" = "United Airlines"
    "AA" = "American Airlines"
    "AC" = "Air Canada"
    "VS" = "Virgin Atlantic"
    "LH" = "Lufthansa"
    "TK" = "Turkish Airlines"
    "SQ" = "Singapore Airlines"
    "CX" = "Cathay Pacific"
    "MS" = "EgyptAir"
    "ET" = "Ethiopian Airlines"
    "WY" = "Oman Air"
    "SV" = "Saudia"
}

function Get-AirlineName([string]$code) {
    if ($AirlineNames.ContainsKey($code)) { return $AirlineNames[$code] }
    return $code
}

# -- Booking URL --------------------------------------------------------------
function Get-BookingURL {
    param([string]$Origin, [string]$Destination, [string]$DepartDate)
    # DepartDate format: YYYY-MM-DD
    $parts = $DepartDate -split "-"
    $dd    = $parts[2]
    $mm    = $parts[1]
    # Aviasales deep-link format: {ORIGIN}{DD}{MM}{DEST}{PAX}
    return "https://www.aviasales.com/search/$Origin$dd$mm${Destination}1"
}

# -- Telegram -----------------------------------------------------------------
function Send-TelegramAlert {
    param([string]$Message)
    $token  = $Config.telegram.bot_token
    $chatId = $Config.telegram.chat_id
    $body   = @{
        chat_id    = $chatId
        text       = $Message
        parse_mode = "HTML"
    } | ConvertTo-Json -Compress
    try {
        $r = Invoke-RestMethod `
            -Uri "https://api.telegram.org/bot$token/sendMessage" `
            -Method Post -Body $body `
            -ContentType "application/json; charset=utf-8"
        if ($r.ok) { Write-Host "  [Telegram] Alert sent." -ForegroundColor Green }
    }
    catch { Write-Warning "  [Telegram] Failed: $($_.Exception.Message)" }
}

# -- Fetch flights from Travelpayouts -----------------------------------------
function Get-Flights {
    param([string]$Origin, [string]$Destination, [string]$Month, [string]$Token)

    # Try mid-month date; API returns nearest available prices around that date
    $searchDate = "$Month-15"
    $uri = "https://api.travelpayouts.com/v1/prices/calendar" +
           "?origin=$Origin&destination=$Destination" +
           "&depart_date=$searchDate&one_way=true&currency=usd&token=$Token"

    try {
        $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 20
        if (-not $response.success) {
            Write-Warning "  API returned success=false"
            return @()
        }

        $flights = [System.Collections.Generic.List[PSCustomObject]]::new()
        $data    = $response.data

        # PSCustomObject properties = date keys
        $data.PSObject.Properties | ForEach-Object {
            $date  = $_.Name
            $f     = $_.Value
            $code  = $f.airline
            $name  = Get-AirlineName $code
            $depDT = [datetime]$f.departure_at
            $url   = Get-BookingURL -Origin $Origin -Destination $Destination -DepartDate $date

            $flights.Add([PSCustomObject]@{
                Date      = $date
                Airline   = $name
                Code      = $code
                FlightNo  = "$code$($f.flight_number)"
                DepTime   = $depDT.ToString("HH:mm")
                Stops     = [int]$f.transfers
                Price     = [int]$f.price
                URL       = $url
            })
        }

        return ($flights | Sort-Object Price)
    }
    catch {
        Write-Warning "  API error: $($_.Exception.Message)"
        return @()
    }
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
    $line = "$ts,$($Flight.Airline),$($Flight.FlightNo),$($Flight.Date),$($Flight.DepTime),$($Flight.Stops),$($Flight.Price),$Alert,$($Flight.URL)"
    $line | Out-File $LogFile -Append -Encoding UTF8
}

# -- Scheduler ----------------------------------------------------------------
$TaskName = "FlightGuru_Monitor"

function Install-Scheduler {
    $script   = Join-Path $Root "FlightGuru.ps1"
    $action   = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
    $trigger  = New-ScheduledTaskTrigger `
        -Once -At (Get-Date).AddMinutes(2) `
        -RepetitionInterval (New-TimeSpan -Hours 6)
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask `
        -TaskName $TaskName -Action $action `
        -Trigger $trigger -Settings $settings `
        -RunLevel Limited -Force | Out-Null
    Write-Host ""
    Write-Host "  Task '$TaskName' registered." -ForegroundColor Green
    Write-Host "  Runs every 6 hours. No expiry - you control when to stop." -ForegroundColor Gray
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
$token       = $Config.travelpayouts.api_token
$originCity  = $Config.search.origin_city
$destCity    = $Config.search.destination_city

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  FlightGuru - Price Check" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  Route  : $originCity -> $destCity"
Write-Host "  Month  : $month"
Write-Host "  Target : Below `$$target USD"
Write-Host "  Time   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "--------------------------------"
Write-Host "  Fetching from Travelpayouts API..."

$flights = Get-Flights -Origin $origin -Destination $destination -Month $month -Token $token

if ($flights.Count -eq 0) {
    Write-Warning "  No flights returned. Data for $month may not be cached yet - will retry next cycle."
    exit 0
}

Write-Host ""
Write-Host "  Results:" -ForegroundColor White
$flights | ForEach-Object {
    $stops = if ($_.Stops -eq 0) { "Nonstop" } elseif ($_.Stops -eq 1) { "1 stop" } else { "$($_.Stops) stops" }
    Write-Host ("  [{0}] {1,-22} {2}  {3,-8}  `${4}" -f $_.Date, $_.Airline, $_.DepTime, $stops, $_.Price)
}

$cheapest = $flights | Select-Object -First 1
$lastLow  = Get-LastPrice
$alert    = $cheapest.Price -lt $target

Write-Host ""
Write-Host ("  Cheapest : {0} {1} on {2} at {3} - `${4}" -f `
    $cheapest.Airline, $cheapest.FlightNo, $cheapest.Date, $cheapest.DepTime, $cheapest.Price) -ForegroundColor Cyan
Write-Host "  Last low : `$$lastLow"
Write-Host "  Target   : Below `$$target"
Write-Host ""

Write-FlightLog -Flight $cheapest -Alert $alert
Save-State -Price $cheapest.Price

$stopsLabel = if ($cheapest.Stops -eq 0) { "Nonstop" } elseif ($cheapest.Stops -eq 1) { "1 stop" } else { "$($cheapest.Stops) stops" }

if ($alert) {
    Write-Host "  *** PRICE BELOW TARGET - sending alert ***" -ForegroundColor Green
    $msg = "[FlightGuru] PRICE ALERT!`n`n" +
           "Route    : $originCity -> $destCity`n" +
           "Airline  : $($cheapest.Airline) ($($cheapest.FlightNo))`n" +
           "Date     : $($cheapest.Date)`n" +
           "Dep Time : $($cheapest.DepTime)`n" +
           "Stops    : $stopsLabel`n" +
           "Price    : `$$($cheapest.Price) USD`n" +
           "Target   : Below `$$target`n`n" +
           "Book Now : $($cheapest.URL)"
    Send-TelegramAlert -Message $msg
}
elseif ($cheapest.Price -lt $lastLow) {
    $drop = $lastLow - $cheapest.Price
    Write-Host "  Price dropped `$$drop since last check (`$$lastLow -> `$$($cheapest.Price))" -ForegroundColor Yellow
    Write-Host "  Still above target. No alert sent." -ForegroundColor Yellow
}
else {
    Write-Host "  Price `$$($cheapest.Price) is above target `$$target. No alert." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Log: logs\price_history.csv"
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
