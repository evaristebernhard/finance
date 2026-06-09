$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$HermesEnv = Join-Path $env:LOCALAPPDATA "hermes\.env"

$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
$env:COCKPIT_BASE_URL = if ($env:COCKPIT_BASE_URL) { $env:COCKPIT_BASE_URL } else { "http://127.0.0.1:32081/v1" }
$env:COCKPIT_PROXY_DEFAULT_MAX_TOKENS = if ($env:COCKPIT_PROXY_DEFAULT_MAX_TOKENS) { $env:COCKPIT_PROXY_DEFAULT_MAX_TOKENS } else { "8192" }

if (-not $env:COCKPIT_API_KEY -and (Test-Path $HermesEnv)) {
    $line = Get-Content $HermesEnv | Where-Object { $_ -match '^OPENAI_API_KEY=' } | Select-Object -First 1
    if ($line) {
        $env:COCKPIT_API_KEY = $line -replace '^OPENAI_API_KEY=', ''
    }
}

python (Join-Path $PSScriptRoot "cockpit_sse_proxy.py") --host 127.0.0.1 --port 32181
