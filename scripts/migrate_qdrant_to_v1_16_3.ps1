# OpenConstructionERP - migrate from Qdrant 1.18.0 to 1.16.3 (Windows).
#
# Why this exists:
# Qdrant 1.17+ writes a WAL clock file (newest_clocks.json) during snapshot
# recovery. Windows Defender briefly locks this file on creation, so the
# fsync from Qdrant fails with "Access is denied. (os error 5)" - every
# CWICR catalogue install in /setup/databases fails. Qdrant 1.16.3 does
# not write that clock file and the install completes normally with no
# Defender exclusion needed.
#
# What this does:
# 1. Stop the running qdrant.exe (the OpenConstructionERP backend will
#    auto-respawn it on the first request after migration).
# 2. Move the existing storage/ aside to storage.1.18.bak.<timestamp>.
#    Qdrant does not support downgrade, so the new 1.16.3 needs a fresh
#    storage dir. Existing oe_* collections (BOQ embeddings etc.) are
#    re-indexed lazily by the backend from the SQL source of truth.
# 3. Replace qdrant.exe with the 1.16.3 binary.
# 4. Start the new Qdrant - same port 6333, same config.
#
# Safe to re-run: if qdrant.exe is already 1.16.3, nothing changes.

$ErrorActionPreference = "Stop"

$qdrantHome = Join-Path $env:USERPROFILE ".openestimator\qdrant"
$qdrantExe  = Join-Path $qdrantHome "qdrant.exe"
$storage    = Join-Path $qdrantHome "storage"
$config     = Join-Path $qdrantHome "config\config.yaml"

$pinnedTag = "v1.16.3"
$downloadUrl = "https://github.com/qdrant/qdrant/releases/download/$pinnedTag/qdrant-x86_64-pc-windows-msvc.zip"

Write-Host ""
Write-Host "OpenConstructionERP - Qdrant migration to 1.16.3" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $qdrantExe)) {
    Write-Host "Qdrant not installed at $qdrantExe" -ForegroundColor Yellow
    Write-Host "Nothing to migrate. Backend will install 1.16.3 on first /match-elements use." -ForegroundColor Yellow
    exit 0
}

# 1. Detect running version
$currentVersion = "unknown"
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:6333/" -TimeoutSec 3 -ErrorAction Stop
    $currentVersion = $resp.version
    Write-Host "Currently running: Qdrant $currentVersion" -ForegroundColor White
} catch {
    Write-Host "Qdrant is not currently running (or unreachable on :6333)." -ForegroundColor Gray
}

if ($currentVersion -eq "1.16.3") {
    Write-Host "Already on 1.16.3 - nothing to do." -ForegroundColor Green
    exit 0
}

# 2. Stop the running Qdrant
Write-Host ""
Write-Host "Stopping qdrant.exe..." -ForegroundColor White
$proc = Get-NetTCPConnection -LocalPort 6333 -ErrorAction SilentlyContinue
if ($proc) {
    $pid_ = $proc.OwningProcess
    Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "  Stopped PID $pid_" -ForegroundColor Gray
} else {
    Write-Host "  Already stopped." -ForegroundColor Gray
}

# 3. Backup storage
if (Test-Path $storage) {
    $ts = Get-Date -Format "yyyy-MM-dd_HHmmss"
    $backupDir = "$storage.bak.$ts"
    Write-Host ""
    Write-Host "Backing up storage dir to:" -ForegroundColor White
    Write-Host "  $backupDir" -ForegroundColor Gray
    Move-Item -Path $storage -Destination $backupDir -Force
    Write-Host "  OK (backend will rebuild oe_* collections from SQL on demand)." -ForegroundColor Gray
}

# 4. Download 1.16.3 and replace binary
Write-Host ""
Write-Host "Downloading Qdrant $pinnedTag..." -ForegroundColor White
$tmpZip = Join-Path $qdrantHome "qdrant-$pinnedTag.zip"
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpZip -UseBasicParsing -ErrorAction Stop
    Write-Host "  Downloaded $((Get-Item $tmpZip).Length / 1MB | ForEach-Object { '{0:N1}' -f $_ }) MB" -ForegroundColor Gray
} catch {
    Write-Host "Download failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Replacing qdrant.exe..." -ForegroundColor White
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($tmpZip)
try {
    foreach ($entry in $zip.Entries) {
        if ($entry.Name -ieq "qdrant.exe") {
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $qdrantExe, $true)
            Write-Host "  Replaced." -ForegroundColor Gray
            break
        }
    }
} finally {
    $zip.Dispose()
}
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue

# 5. Start new Qdrant
Write-Host ""
Write-Host "Starting Qdrant 1.16.3..." -ForegroundColor White
if (-not (Test-Path $config)) {
    Write-Host "  Config missing - backend will write one on next /match-elements use." -ForegroundColor Yellow
} else {
    $argList = @("--config-path", "`"$config`"")
    Start-Process -FilePath $qdrantExe -ArgumentList $argList -WorkingDirectory $qdrantHome -WindowStyle Hidden
    Start-Sleep -Seconds 4
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:6333/" -TimeoutSec 3
        Write-Host "  Running: Qdrant $($resp.version)" -ForegroundColor Green
    } catch {
        Write-Host "  Qdrant did not respond on :6333 yet - check qdrant.log" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Migration complete. Go to /setup/databases and try Install again." -ForegroundColor Cyan
Write-Host "The install should now succeed in ~30 seconds, no Defender prompt." -ForegroundColor Cyan
Write-Host ""
