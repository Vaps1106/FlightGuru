#Requires -Version 5.1
# FlightGuru.ps1 — Flight Price Monitor
#
# Usage:
#   .\FlightGuru.ps1            — run a price check right now
#   .\FlightGuru.ps1 -Install   — register Windows Task Scheduler (every 6 hours, no expiry)
#   .\FlightGuru.ps1 -Uninstall — remove the scheduled task

param(
    [switch]$Install,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# Required for Telegram API on Windows 10 / PowerShell 5.1
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ── Paths ─────────────────────────────────────────────────────────────────────
$Root       = $PSScriptRoot
$ConfigFile = Join-Path $Root "config.json"
$StateFile  = Join-Path $Root "state.json"
$LogDir     = Join-Path $Root "logs"
$LogFile    = Join-Path $LogDir "price_history.csv"

# ── Config ────────────────────────────────────────────────────────────────────
if (-not (Test-Path $ConfigFile)) {
    Write-Error "config.json not found. Copy config.example.json to config.json and fill in your details."
    exit 1
}
$Config = Get-Content $ConfigFile -Raw | ConvertFrom-Json

# ── Init ──────────────────────────────────────────────────────────────────────
if (-not (Test-Path $LogDir))  { New-Item -ItemType Directory -Path $LogDir | Out-Null }
if (-not (Test-Path $LogFile)) {
    "Timestamp,Source,Price_USD,Below_Target,URL" | Out-File $LogFile -Encoding UTF8
}

# ── Telegram ──────────────────────────────────────────────────────────────────
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
            -Method Post `
            -Body $body `
            -ContentType "application/json; charset=utf-8"
        if ($r.ok) { Write-Host "  [Telegram] Alert sent." -ForegroundColor Green }
    }
    catch {
        Write-Warning "  [Telegram] Failed: $($_.Exception.Message)"
    }
}

# ── Price Search ──────────────────────────────────────────────────────────────
function Search-Prices {
    $found   = [System.Collections.Generic.List[PSCustomObject]]::new()
    $headers = @{
        "User-Agent"      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        "Accept-Language" = "en-US,en;q=0.9"
        "Accept"          = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    function Get-MinPrice([string]$html) {
        $matches = [regex]::Matches($html, '\$\s*(\d{3,4})')
        $matches |
            ForEach-Object { [int]$_.Groups[1].Value } |
            Where-Object   { $_ -ge 200 -and $_ -le 5000 } |
            Sort-Object    |
            Select-Object -First 1
    }

    # Source 1 — Bing search (most reliable, no JS needed)
    try {
        Write-Host "  Bing    ..." -NoNewline
        $q    = "cheapest+one+way+flight+Mumbai+BOM+New+York+economy+August+2026+price+USD"
        $html = (Invoke-WebRequest "https://www.bing.com/search?q=$q" `
                    -Headers $headers -UseBasicParsing -TimeoutSec 20).Content
        $p = Get-MinPrice $html
        if ($p) {
            $found.Add([PSCustomObject]@{
                Source = "Bing"
                Price  = $p
                URL    = "https://www.bing.com/search?q=$q"
            })
            Write-Host " `$$p" -ForegroundColor Cyan
        } else { Write-Host " no price found" -ForegroundColor Yellow }
    }
    catch { Write-Host " error: $($_.Exception.Message)" -ForegroundColor Red }

    # Source 2 — Kayak route page
    try {
        Write-Host "  Kayak   ..." -NoNewline
        $uri  = "https://www.kayak.com/flight-routes/Mumbai-Chhatrapati-Shivaji-BOM/New-York-NYC"
        $html = (Invoke-WebRequest $uri -Headers $headers -UseBasicParsing -TimeoutSec 20).Content
        $p = Get-MinPrice $html
        if ($p) {
            $found.Add([PSCustomObject]@{ Source = "Kayak"; Price = $p; URL = $uri })
            Write-Host " `$$p" -ForegroundColor Cyan
        } else { Write-Host " no price found" -ForegroundColor Yellow }
    }
    catch { Write-Host " error: $($_.Exception.Message)" -ForegroundColor Red }

    # Source 3 — Momondo route page
    try {
        Write-Host "  Momondo ..." -NoNewline
        $uri  = "https://www.momondo.com/flights/mumbai/new-york-city"
        $html = (Invoke-WebRequest $uri -Headers $headers -UseBasicParsing -TimeoutSec 20).Content
        $p = Get-MinPrice $html
        if ($p) {
            $found.Add([PSCustomObject]@{ Source = "Momondo"; Price = $p; URL = $uri })
            Write-Host " `$$p" -ForegroundColor Cyan
        } else { Write-Host " no price found" -ForegroundColor Yellow }
    }
    catch { Write-Host " error: $($_.Exception.Message)" -ForegroundColor Red }

    return $found
}

# ── State ─────────────────────────────────────────────────────────────────────
function Get-LastPrice {
    if (Test-Path $StateFile) {
        return [int]((Get-Content $StateFile -Raw | ConvertFrom-Json).last_price)
    }
    return 9999
}

function Save-State([int]$Price) {
    @{
        last_price = $Price
        updated    = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    } | ConvertTo-Json | Out-File $StateFile -Encoding UTF8
}

# ── Logging ───────────────────────────────────────────────────────────────────
function Write-PriceLog {
    param($Results, [bool]$Alert)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    foreach ($r in $Results) {
        "$ts,$($r.Source),$($r.Price),$Alert,$($r.URL)" |
            Out-File $LogFile -Append -Encoding UTF8
    }
}

# ── Scheduler ─────────────────────────────────────────────────────────────────
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
                    -StartWhenAvailable `
                    -RunOnlyIfNetworkAvailable `
                    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action   $action `
        -Trigger  $trigger `
        -Settings $settings `
        -RunLevel Limited `
        -Force | Out-Null
    Write-Host ""
    Write-Host "  Task '$TaskName' registered." -ForegroundColor Green
    Write-Host "  Runs every 6 hours. No expiry — you control when to stop." -ForegroundColor Gray
    Write-Host "  To remove: .\FlightGuru.ps1 -Uninstall" -ForegroundColor Gray
}

function Uninstall-Scheduler {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  Task '$TaskName' removed." -ForegroundColor Yellow
    } else {
        Write-Host "  Task '$TaskName' not found — nothing to remove." -ForegroundColor Gray
    }
}

# ── Main ──────────────────────────────────────────────────────────────────────
if ($Install)   { Install-Scheduler;   exit 0 }
if ($Uninstall) { Uninstall-Scheduler; exit 0 }

$origin      = $Config.search.origin_city
$destination = $Config.search.destination_city
$target      = [int]$Config.search.target_price
$month       = $Config.search.month_label

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  FlightGuru — Price Check" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  Route  : $origin → $destination"
Write-Host "  Month  : $month"
Write-Host "  Target : Below `$$target USD"
Write-Host "  Time   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "--------------------------------"

$results = Search-Prices

if ($results.Count -eq 0) {
    Write-Warning "No prices retrieved from any source. Check your internet connection."
    exit 1
}

$lowest  = $results | Sort-Object Price | Select-Object -First 1
$lastLow = Get-LastPrice
$alert   = $lowest.Price -lt $target

Write-Host ""
Write-Host "  Lowest found : `$$($lowest.Price) via $($lowest.Source)"
Write-Host "  Last known   : `$$lastLow"
Write-Host "  Target       : Below `$$target"
Write-Host ""

Write-PriceLog -Results $results -Alert $alert
Save-State -Price $lowest.Price

if ($alert) {
    Write-Host "  *** PRICE BELOW TARGET — sending alert ***" -ForegroundColor Green
    $msg = "✈ FLIGHT PRICE ALERT!`n`n" +
           "Route : $origin → $destination`n" +
           "Price : `$$($lowest.Price) USD`n" +
           "Target: Below `$$target`n" +
           "Month : $month`n" +
           "Source: $($lowest.Source)`n`n" +
           "Book Now: $($lowest.URL)"
    Send-TelegramAlert -Message $msg
}
elseif ($lowest.Price -lt $lastLow) {
    $drop = $lastLow - $lowest.Price
    Write-Host "  Price dropped `$$drop since last check (`$$lastLow → `$$($lowest.Price))" -ForegroundColor Yellow
    Write-Host "  Still above target. No alert sent." -ForegroundColor Yellow
}
else {
    Write-Host "  Price `$$($lowest.Price) is above target `$$target. No alert." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Log: logs\price_history.csv"
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
