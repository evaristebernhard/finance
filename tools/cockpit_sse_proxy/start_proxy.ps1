$ErrorActionPreference = "Stop"

$HermesEnv = Join-Path $env:LOCALAPPDATA "hermes\.env"

$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"
$env:COCKPIT_BASE_URL = if ($env:COCKPIT_BASE_URL) { $env:COCKPIT_BASE_URL } else { "http://127.0.0.1:32081/v1" }
$env:COCKPIT_DEFAULT_MODEL = if ($env:COCKPIT_DEFAULT_MODEL) { $env:COCKPIT_DEFAULT_MODEL } else { "gpt-5.5" }

if (-not $env:COCKPIT_API_KEY -and (Test-Path $HermesEnv)) {
    $line = Get-Content $HermesEnv | Where-Object { $_ -match "^\uFEFF?OPENAI_API_KEY=" } | Select-Object -First 1
    if ($line) {
        $env:COCKPIT_API_KEY = $line -replace "^\uFEFF?OPENAI_API_KEY=", ""
    }
}

$script = Join-Path $PSScriptRoot "cockpit_stream_shim.mjs"
node $script --host 127.0.0.1 --port 32181
