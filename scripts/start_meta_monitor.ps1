param(
    [string]$ReplayDir = "data\Pokemon-Replays-Public",
    [string]$OutputDir = "artifacts\meta_monitor",
    [double]$IntervalSeconds = 300,
    [int]$HeartbeatEvery = 10
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$logPath = Join-Path $OutputDir "monitor.log"

function Write-MonitorLine {
    param([string]$Line)
    $Line | Out-File -FilePath $logPath -Append -Encoding utf8
    Write-Host $Line
}

while ($true) {
    $started = Get-Date -Format o
    Write-MonitorLine "loop_start local_time=$started interval_seconds=$IntervalSeconds"
    & python scripts\ptcg_meta_side_monitor.py `
        --replay-dir $ReplayDir `
        --output-dir $OutputDir `
        --heartbeat-every $HeartbeatEvery 2>&1 | ForEach-Object {
            Write-MonitorLine $_
        }

    if ($IntervalSeconds -le 0) {
        break
    }
    $sleeping = Get-Date -Format o
    Write-MonitorLine "loop_sleep local_time=$sleeping seconds=$IntervalSeconds"
    Start-Sleep -Seconds $IntervalSeconds
}
