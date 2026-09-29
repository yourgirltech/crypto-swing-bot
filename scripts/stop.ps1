<#
Stops everything scripts/start.ps1 started: the windows it recorded in
.run\pids.json (whole process trees), plus anything still listening on
8010/3000 or running paper_trading.engine, however it was started.
Postgres is left running -- it's a Docker container with
restart: unless-stopped, shared state rather than a dev server.
#>
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".run\pids.json"

function Stop-Tree([int]$id, [string]$label) {
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
        taskkill /T /F /PID $id | Out-Null
        Write-Host "  stopped $label (PID $id)"
    }
}

if (Test-Path $pidFile) {
    try {
        (Get-Content $pidFile -Raw | ConvertFrom-Json).PSObject.Properties |
            ForEach-Object { Stop-Tree ([int]$_.Value) $_.Name }
    } catch {}
    Remove-Item $pidFile -Force
}

foreach ($port in 8010, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Tree $_.OwningProcess "listener on :$port" }
}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*paper_trading.engine*" } |
    ForEach-Object { Stop-Tree $_.ProcessId "paper trading engine" }

Write-Host "Done. (Postgres left running.)"
