param(
  [string]$Symbol = "MONUSDT",
  [string]$DataRoot = "data/mon_usdc/v1",
  [ValidateSet("partial_top20", "strict_l2")]
  [string]$Mode = "strict_l2",
  [string]$RunTag = "live_orderbook_l2_v1",
  [string]$RestBase = "https://fapi.binance.com",
  [int]$RestartDelaySeconds = 10,
  [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "data\mon_usdc\v1\_work\live_orderbook_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Set-Location $RepoRoot

while ($true) {
  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $log = Join-Path $LogDir ("mon_usdc_live_orderbook_{0}_{1}.log" -f $RunTag, $stamp)
  Add-Content -Path $log -Value ("[{0}] starting live orderbook collector mode={1} run_tag={2}" -f (Get-Date).ToUniversalTime().ToString("o"), $Mode, $RunTag)

  $args = @(
    "scripts\mon_usdc_live_orderbook_collector.py",
    "--symbol", $Symbol,
    "--data-root", $DataRoot,
    "--mode", $Mode,
    "--run-tag", $RunTag
  )
  if ($Mode -eq "strict_l2") {
    $args += @("--rest-bases", $RestBase)
  }
  if ($Proxy.Trim().Length -gt 0) {
    $args += @("--proxy", $Proxy.Trim())
  }

  & python @args *>> $log
  $code = $LASTEXITCODE
  Add-Content -Path $log -Value ("[{0}] collector exited with code {1}; restarting in {2}s" -f (Get-Date).ToUniversalTime().ToString("o"), $code, $RestartDelaySeconds)
  Start-Sleep -Seconds $RestartDelaySeconds
}
