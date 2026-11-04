<#
Stops this project's servers: the windows scripts/start.ps1 recorded in
.run\pids.json (whole process trees), plus this project's backend, frontend
and paper_trading.engine processes, however they were started.

Processes are matched by command line, never by port or PID alone, so another
project on port 3000 is left running, and a stale PID in pids.json that Windows
has since reused for something else is ignored.
Postgres is left running -- it's a Docker container with
restart: unless-stopped, shared state rather than a dev server.
#>
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".run\pids.json"
$frontend = Join-Path $root "frontend"

function Stop-Tree([int]$id, [string]$label) {
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
        taskkill /T /F /PID $id | Out-Null
        Write-Host "  stopped $label (PID $id)"
    }
}

if (Test-Path $pidFile) {
    try {
        (Get-Content $pidFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
            $p = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$_.Value)"
            if ($p -and $p.Name -eq "powershell.exe" -and $p.CommandLine -like "*swingbot:*") {
                Stop-Tree ([int]$_.Value) $_.Name
            }
        }
    } catch {}
    Remove-Item $pidFile -Force
}

# Windows opened by an older start script, or by hand with the same titles.
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -like "*WindowTitle = 'swingbot:*" -and $_.ProcessId -ne $PID } |
    ForEach-Object { Stop-Tree $_.ProcessId "swingbot window" }

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*uvicorn*api.main:app*" -or $_.CommandLine -like "*paper_trading.engine*" } |
    ForEach-Object { Stop-Tree $_.ProcessId "python server" }

Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like "*$frontend\*" } |
    ForEach-Object { Stop-Tree $_.ProcessId "frontend" }

Write-Host "Done. (Postgres left running.)"
