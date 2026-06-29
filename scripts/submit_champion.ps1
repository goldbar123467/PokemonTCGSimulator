param(
    [string]$ArchivePath = "artifacts\submission_champion.tar.gz",
    [string]$Competition = "pokemon-tcg-ai-battle",
    [string]$Message = "selected_lucario_source_champion rawexec_checked cg_included",
    [int]$PollSeconds = 300,
    [int]$PollIntervalSeconds = 15,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path -LiteralPath $ArchivePath)) {
    throw "Missing archive: $ArchivePath"
}

$contents = tar -tzf $ArchivePath
if ($contents -notcontains "main.py" -or $contents -notcontains "deck.csv" -or $contents -notcontains "cg/api.py") {
    throw "Archive must contain top-level main.py, deck.csv, and cg/api.py"
}

$validationOutput = & python -m ptcg.kaggle_archive_validator --archive $ArchivePath 2>&1
$validationExit = $LASTEXITCODE
$validationOutput | ForEach-Object { Write-Output $_ }
if ($validationExit -ne 0) {
    throw "Archive raw-exec validation failed; not submitting"
}

if ($DryRun) {
    Write-Output "Dry run passed; would submit $ArchivePath to $Competition with message: $Message"
    exit 0
}

$validationDir = Join-Path $root "artifacts\submit_validation"
New-Item -ItemType Directory -Force -Path $validationDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$beforeFile = Join-Path $validationDir "kaggle_submit_before_$stamp.txt"
$submitFile = Join-Path $validationDir "kaggle_submit_output_$stamp.txt"
$afterFile = Join-Path $validationDir "kaggle_submit_after_$stamp.txt"
$quotaFile = Join-Path $validationDir "kaggle_submit_quota_$stamp.json"

function Invoke-KaggleCapture {
    param(
        [string[]]$Arguments,
        [string]$OutputPath
    )

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & kaggle @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }

    $lines = @($output | ForEach-Object { $_.ToString() })
    $lines | Set-Content -LiteralPath $OutputPath -Encoding utf8
    $lines | ForEach-Object { Write-Output $_ }
    if ($exitCode -ne 0) {
        throw "kaggle $($Arguments -join ' ') exited $exitCode"
    }
}

Invoke-KaggleCapture -Arguments @("competitions", "submissions", "-c", $Competition) -OutputPath $beforeFile
$beforeRef = (& python -m ptcg.kaggle_submit_guard first-ref --path $beforeFile 2>$null)

$oldPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $quotaOutput = & python -m ptcg.kaggle_quota_guard --competition $Competition 2>&1
    $quotaExit = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $oldPreference
}
$quotaLines = @($quotaOutput | ForEach-Object { $_.ToString() })
$quotaLines | Set-Content -LiteralPath $quotaFile -Encoding utf8
$quotaLines | ForEach-Object { Write-Output $_ }
if ($quotaExit -ne 0) {
    throw "Kaggle daily submission quota reached or unavailable; not submitting"
}

Invoke-KaggleCapture -Arguments @("competitions", "submit", "-c", $Competition, "-f", $ArchivePath, "-m", $Message) -OutputPath $submitFile

& python -m ptcg.kaggle_submit_guard check-output --path $submitFile
if ($LASTEXITCODE -ne 0) {
    throw "Kaggle submit output contains an error; no successful submission recorded"
}

Start-Sleep -Seconds 5
Invoke-KaggleCapture -Arguments @("competitions", "submissions", "-c", $Competition) -OutputPath $afterFile
$afterRef = (& python -m ptcg.kaggle_submit_guard first-ref --path $afterFile 2>$null)
if (-not $afterRef -or $afterRef -eq $beforeRef) {
    throw "Kaggle did not create a new submission row"
}

$deadline = (Get-Date).AddSeconds($PollSeconds)
do {
    $status = (& python -m ptcg.kaggle_submit_guard status --path $afterFile --ref $afterRef 2>$null)
    if ($status -eq "ERROR") {
        throw "Kaggle submission $afterRef reached ERROR"
    }
    if ($status -eq "COMPLETE") {
        Write-Output "Kaggle submission $afterRef COMPLETE"
        exit 0
    }
    if ($PollSeconds -le 0) {
        Write-Output "Kaggle submission $afterRef created with status $status"
        exit 0
    }
    Start-Sleep -Seconds $PollIntervalSeconds
    Invoke-KaggleCapture -Arguments @("competitions", "submissions", "-c", $Competition) -OutputPath $afterFile
} while ((Get-Date) -lt $deadline)

throw "Kaggle submission $afterRef did not complete within $PollSeconds seconds"
