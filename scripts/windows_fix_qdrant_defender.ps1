# OpenConstructionERP - Windows Defender fix for Qdrant snapshot restore.
#
# Why this exists:
# Qdrant 1.18+ writes a WAL clock file (newest_clocks.json) during snapshot
# recovery and calls fsync() on it. On native Windows, Defender's real-time
# scanner briefly holds a handle on the file as soon as it appears on disk
# and Qdrant gets ACCESS_DENIED (os error 5) before the scan releases.
# The download succeeds - only the final disk sync fails - and Qdrant
# rolls back the entire restore. Install hangs / errors with
# "Qdrant could not fetch or restore the snapshot ..." even though the
# bytes arrived fine.
#
# How to use:
# 1. Right-click this file -> "Run with PowerShell".
# 2. Approve the UAC prompt that appears.
# 3. Return to the app and click "Install" again on the catalogue card.
#
# Nothing is uninstalled or reconfigured - we only add ~/.openestimator
# to Defender's exclusion list. To remove the exclusion later, open an
# elevated PowerShell and run:
#   Remove-MpPreference -ExclusionPath "$env:USERPROFILE\.openestimator"

$ErrorActionPreference = "Stop"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host ""
    Write-Host "This script must run AS ADMINISTRATOR." -ForegroundColor Yellow
    Write-Host "Re-launching with UAC elevation..." -ForegroundColor Yellow
    Write-Host ""
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-NoExit",
        "-File", "`"$PSCommandPath`""
    )
    exit
}

$targetPath = Join-Path $env:USERPROFILE ".openestimator"

Write-Host ""
Write-Host "OpenConstructionERP - Qdrant Defender fix" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Adding Defender exclusion for:" -ForegroundColor White
Write-Host "  $targetPath" -ForegroundColor Green
Write-Host ""

try {
    $current = (Get-MpPreference).ExclusionPath
    $already = $current | Where-Object { $_ -ieq $targetPath }
    if ($already) {
        Write-Host "Already excluded. No change needed." -ForegroundColor Green
    } else {
        Add-MpPreference -ExclusionPath $targetPath
        Write-Host "Exclusion added successfully." -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "Current exclusions:" -ForegroundColor White
    (Get-MpPreference).ExclusionPath | ForEach-Object {
        Write-Host "  - $_" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "Done. Go back to the app and click 'Install' on the catalogue card." -ForegroundColor Cyan
    Write-Host "No restart of Qdrant or the backend is needed." -ForegroundColor Cyan
    Write-Host ""
} catch {
    Write-Host ""
    Write-Host "Failed to add exclusion: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Workaround: open Windows Security manually:" -ForegroundColor Yellow
    Write-Host "  Settings > Update and Security > Windows Security >" -ForegroundColor Yellow
    Write-Host "  Virus and threat protection > Manage settings >" -ForegroundColor Yellow
    Write-Host "  Add or remove exclusions > Add an exclusion > Folder >" -ForegroundColor Yellow
    Write-Host "  $targetPath" -ForegroundColor Green
    Write-Host ""
}

Write-Host "Press any key to close..." -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
