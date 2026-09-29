<#
One-command start for the whole local stack. Run from anywhere:

    .\start.cmd              # Postgres + backend (8010) + frontend (3000) + paper trading engine
    .\start.cmd -NoEngine    # everything except the paper trading engine

Each server gets its OWN visible console window, on purpose:
- the paper trading engine blocks on a real y/n approval prompt
  (paper_trading/engine.py -- human approval is mandatory, no auto-execute
  mode), so it needs an interactive console, not a hidden background job;
- closing a window stops that server; .\stop.cmd stops all of them.

Anything already running (port 8010/3000 listening, an engine process
alive) is left alone rather than started twice, so re-running this is safe.
PIDs of the windows it opens go to .run\pids.json for stop.ps1.
#>
param([switch]$NoEngine)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $root ".run"
New-Item -ItemType Directory -Force $runDir | Out-Null
$pidFile = Join-Path $runDir "pids.json"

$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

function Test-PortListening([int]$port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Get-EngineProcess {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*paper_trading.engine*" }
}

function Start-Window([string]$title, [string]$workDir, [string]$command) {
    $full = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$workDir'; $command"
    $p = Start-Process powershell -PassThru -WorkingDirectory $workDir `
        -ArgumentList "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $full
    Write-Host "  started $title (window PID $($p.Id))" -ForegroundColor Green
    return $p.Id
}

$pids = @{}
if (Test-Path $pidFile) {
    try { (Get-Content $pidFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $pids[$_.Name] = $_.Value } } catch {}
}

# 1. Postgres (docker-compose.yml, host port 5433). `up -d` is idempotent.
Write-Host "Postgres (5433)..."
if (Test-PortListening 5433) {
    Write-Host "  already listening" -ForegroundColor DarkGray
} elseif (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose -f (Join-Path $root "docker-compose.yml") up -d postgres
    for ($i = 0; $i -lt 30 -and -not (Test-PortListening 5433); $i++) { Start-Sleep 1 }
    if (-not (Test-PortListening 5433)) { Write-Warning "Postgres still not listening on 5433 -- is Docker Desktop running?" }
} else {
    Write-Warning "docker not found and nothing on 5433 -- start Docker Desktop, then re-run."
}

# 2. Backend API (FastAPI). First start can take 1-2 min: imports are slow from the OneDrive folder.
Write-Host "Backend (8010)..."
if (Test-PortListening 8010) {
    Write-Host "  already listening" -ForegroundColor DarkGray
} else {
    $pids["backend"] = Start-Window "swingbot: backend :8010" $root "& '$python' -m uvicorn api.main:app --port 8010"
}

# 3. Frontend (Next.js dev server).
Write-Host "Frontend (3000)..."
$frontend = Join-Path $root "frontend"
if (Test-PortListening 3000) {
    Write-Host "  already listening" -ForegroundColor DarkGray
} else {
    $install = if (Test-Path (Join-Path $frontend "node_modules")) { "" } else { "npm install; " }
    $pids["frontend"] = Start-Window "swingbot: frontend :3000" $frontend "${install}npm run dev"
}

# 4. Paper trading engine -- continuous. The loop restarts it if the process
# itself dies (per-cycle errors are already caught inside engine.main()).
if (-not $NoEngine) {
    Write-Host "Paper trading engine..."
    if (Get-EngineProcess) {
        Write-Host "  already running" -ForegroundColor DarkGray
    } else {
        # OKX is ISP-blocked on this network; the engine needs the VPN.
        try {
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 8 "https://www.okx.com/api/v5/public/time" | Out-Null
        } catch {
            Write-Warning "OKX unreachable -- turn the VPN on. Starting the engine anyway; it retries every poll cycle."
        }
        $loop = "while (`$true) { & '$python' -m paper_trading.engine; " +
                "Write-Host 'Engine process exited -- restarting in 30s. Close this window to stop it.' -ForegroundColor Yellow; " +
                "Start-Sleep 30 }"
        $pids["engine"] = Start-Window "swingbot: paper engine (answer approvals here)" $root $loop
    }
}

$pids | ConvertTo-Json | Set-Content -Encoding utf8 $pidFile

Write-Host ""
Write-Host "Dashboard: http://localhost:3000   API docs: http://localhost:8010/docs"
Write-Host "Stop everything: .\stop.cmd"
