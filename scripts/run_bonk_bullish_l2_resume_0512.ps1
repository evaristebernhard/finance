param(
    [string]$DataRoot = "data/bonk/v1",
    [string]$DateDir = "date",
    [string]$DocDir = "docs/markets/bonk",
    [string]$FinalRunTag = "20260513_bullish_l2_v1",
    [string]$BonkDownloadRunTag = "20260513_bullish_l2_0512",
    [string]$MemeDownloadRunTag = "20260513_bullish_meme_l2_0512",
    [string]$BonkSymbols = "BONK1MUSDC,BONK1MUSDT",
    [string]$MemeSymbols = "DOGEUSDC,PENGUUSDC",
    [switch]$SkipMeme,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param([string[]]$CommandArgs)
    $display = "python " + ($CommandArgs -join " ")
    if ($DryRun) {
        Write-Host "[dry-run] $display"
        return
    }
    Write-Host "[run] $display"
    & python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "command failed with exit code $LASTEXITCODE`: $display"
    }
}

$allSymbols = $BonkSymbols
if (-not $SkipMeme -and $MemeSymbols.Trim().Length -gt 0) {
    $allSymbols = "$BonkSymbols,$MemeSymbols"
}

Invoke-Step -CommandArgs @(
    "scripts/bonk_bullish_l2_download.py",
    "--data-root", $DataRoot,
    "--date-dir", $DateDir,
    "--from-date", "2026-05-12",
    "--to-date", "2026-05-12",
    "--symbols", $BonkSymbols,
    "--run-tag", $BonkDownloadRunTag
)

if (-not $SkipMeme -and $MemeSymbols.Trim().Length -gt 0) {
    Invoke-Step -CommandArgs @(
        "scripts/bonk_bullish_l2_download.py",
        "--data-root", $DataRoot,
        "--date-dir", $DateDir,
        "--from-date", "2026-05-12",
        "--to-date", "2026-05-12",
        "--symbols", $MemeSymbols,
        "--run-tag", $MemeDownloadRunTag
    )
}

Invoke-Step -CommandArgs @(
    "scripts/bonk_cex_l2_report.py",
    "--data-root", $DataRoot,
    "--date-dir", $DateDir,
    "--doc-dir", $DocDir,
    "--run-tag", $FinalRunTag,
    "--symbols", $allSymbols,
    "--label-symbols", $BonkSymbols
)
