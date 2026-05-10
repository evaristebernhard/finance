param(
    [int]$Days = 10,
    [UInt64]$StartFrom = 71691947,
    [UInt64]$StartTo = 71907946,
    [string]$FirstDayTag = "day20260501",
    [UInt64]$BlocksPerDay = 216000,
    [UInt64]$ShardSize = 18000,
    [int]$MaxParallelLogShards = 4,
    [ValidateSet("transfer", "v3", "dex", "headers", "receipts", "features", "quality")]
    [string]$StartPhase = "transfer",
    [string]$DataRoot = "",
    [string]$LogRoot = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

if ([string]::IsNullOrWhiteSpace($LogRoot)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $LogRoot = Join-Path $RepoRoot "logs\chog_memecoin_backfill_$stamp"
}
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$RunLog = Join-Path $LogRoot "run.log"

function Add-RunLogLine {
    param([string]$Line)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Line + [Environment]::NewLine)
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        try {
            $stream = [System.IO.File]::Open(
                $RunLog,
                [System.IO.FileMode]::Append,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::ReadWrite
            )
            try {
                $stream.Write($bytes, 0, $bytes.Length)
            } finally {
                $stream.Dispose()
            }
            return
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 200
        }
    }
    throw "failed to append to run log after retries: $RunLog"
}

function Write-RunLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "o"), $Message
    Add-RunLogLine $line
    Write-Output $line
}

function Strip-InlineComment {
    param([string]$Value)
    $inSingle = $false
    $inDouble = $false
    for ($i = 0; $i -lt $Value.Length; $i++) {
        $ch = $Value[$i]
        if ($ch -eq "'" -and -not $inDouble) {
            $inSingle = -not $inSingle
        } elseif ($ch -eq '"' -and -not $inSingle) {
            $inDouble = -not $inDouble
        } elseif ($ch -eq "#" -and -not $inSingle -and -not $inDouble) {
            return $Value.Substring(0, $i).Trim()
        }
    }
    return $Value.Trim()
}

function Clean-EnvScalar {
    param([string]$Value)
    $value = Strip-InlineComment $Value
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        return $value.Substring(1, $value.Length - 2)
    }
    return $value
}

function Add-ExpandedArrayToken {
    param(
        [System.Collections.Generic.List[string]]$Target,
        [hashtable]$Vars,
        [string]$Token
    )
    $token = (Clean-EnvScalar $Token).Trim()
    if ([string]::IsNullOrWhiteSpace($token)) {
        return
    }
    if ($token -match '^\$\{([A-Za-z_][A-Za-z0-9_]*)\[@\]\}$') {
        $name = $Matches[1]
        if ($Vars.ContainsKey($name)) {
            $existing = $Vars[$name]
            if ($existing -is [array]) {
                foreach ($item in $existing) {
                    if (-not [string]::IsNullOrWhiteSpace($item)) {
                        $Target.Add([string]$item)
                    }
                }
            } else {
                foreach ($item in ([string]$existing).Split(",")) {
                    $trimmed = $item.Trim()
                    if ($trimmed) {
                        $Target.Add($trimmed)
                    }
                }
            }
        }
        return
    }
    $Target.Add($token)
}

function Parse-EnvArray {
    param(
        [string[]]$Lines,
        [ref]$Index,
        [hashtable]$Vars,
        [string]$Initial
    )
    $items = [System.Collections.Generic.List[string]]::new()
    $value = $Initial.Trim()
    if ($value.StartsWith("(")) {
        $value = $value.Substring(1).Trim()
    }
    while ($true) {
        $done = $false
        if ($value.EndsWith(")")) {
            $done = $true
            $value = $value.Substring(0, $value.Length - 1).Trim()
        }
        $line = Strip-InlineComment $value
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            $matches = [regex]::Matches($line, '"[^"]*"|''[^'']*''|\S+')
            foreach ($match in $matches) {
                Add-ExpandedArrayToken -Target $items -Vars $Vars -Token $match.Value
            }
        }
        if ($done) {
            break
        }
        $Index.Value++
        if ($Index.Value -ge $Lines.Count) {
            throw "unterminated env array"
        }
        $value = $Lines[$Index.Value].Trim()
    }
    return [string[]]$items.ToArray()
}

function Import-ChogEnv {
    param([string]$Path)
    $vars = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $vars
    }
    $lines = Get-Content -LiteralPath $Path
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i].Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }
        if ($line.StartsWith("export ")) {
            $line = $line.Substring(7).TrimStart()
        }
        if ($line -notmatch '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            continue
        }
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.StartsWith("(")) {
            $indexRef = [ref]$i
            $array = Parse-EnvArray -Lines $lines -Index $indexRef -Vars $vars -Initial $value
            $i = $indexRef.Value
            $vars[$name] = $array
            [Environment]::SetEnvironmentVariable($name, ($array -join ","), "Process")
        } else {
            $scalar = Clean-EnvScalar $value
            $vars[$name] = $scalar
            [Environment]::SetEnvironmentVariable($name, $scalar, "Process")
        }
    }
    return $vars
}

function Get-VarAsArray {
    param(
        [hashtable]$Vars,
        [string]$Name
    )
    if (-not $Vars.ContainsKey($Name)) {
        return @()
    }
    $value = $Vars[$Name]
    if ($value -is [array]) {
        return @($value | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    return @(([string]$value).Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Get-Secrets {
    param([hashtable]$Vars)
    $secrets = [System.Collections.Generic.List[string]]::new()
    foreach ($key in $Vars.Keys) {
        $value = $Vars[$key]
        if ($value -is [array]) {
            foreach ($item in $value) {
                if ($item -and ([string]$item).Length -gt 8) {
                    $secrets.Add([string]$item)
                }
            }
        } elseif ($value -and ([string]$value).Length -gt 8) {
            $secrets.Add([string]$value)
            foreach ($item in ([string]$value).Split(",")) {
                $trimmed = $item.Trim()
                if ($trimmed.Length -gt 8) {
                    $secrets.Add($trimmed)
                }
            }
        }
    }
    return [string[]]($secrets | Sort-Object -Unique)
}

function Sanitize-Text {
    param(
        [AllowNull()][object]$Text,
        [string[]]$Secrets
    )
    $s = [string]$Text
    foreach ($secret in ($Secrets | Sort-Object Length -Descending)) {
        if (-not [string]::IsNullOrWhiteSpace($secret)) {
            $s = $s.Replace($secret, "<SECRET>")
        }
    }
    $s = $s -replace 'https?://[^\s\]\)''"]+', '<RPC_URL>'
    return $s
}

function Invoke-Bin {
    param(
        [string]$Bin,
        [string[]]$ProcArgs,
        [string]$StepName,
        [string[]]$Secrets
    )
    $exe = Join-Path $RepoRoot "crate\target\debug\$Bin.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "missing binary: $exe"
    }
    Write-RunLog "START $StepName"
    $output = & $exe @ProcArgs 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) {
        Add-RunLogLine ("  " + (Sanitize-Text -Text $line -Secrets $Secrets))
    }
    if ($code -ne 0) {
        Write-RunLog "FAIL $StepName exit=$code"
        throw "$StepName failed with exit code $code"
    }
    Write-RunLog "DONE $StepName"
    return [string[]]($output | ForEach-Object { [string]$_ })
}

function Invoke-ShardedCollector {
    param(
        [string]$Bin,
        [UInt64]$FromBlock,
        [UInt64]$ToBlock,
        [string]$DayTag,
        [string]$SuffixPrefix,
        [string[]]$BaseArgs,
        [UInt64]$ShardSize,
        [int]$MaxParallel,
        [string[]]$Secrets
    )
    Write-RunLog "START $Bin shards for $DayTag $FromBlock..$ToBlock"
    $exe = Join-Path $RepoRoot "crate\target\debug\$Bin.exe"
    $jobs = @()
    $failed = $false
    $failureMessages = [System.Collections.Generic.List[string]]::new()
    $shardIndex = 0
    for ($start = $FromBlock; $start -le $ToBlock; $start += $ShardSize) {
        $end = [Math]::Min([UInt64]($start + $ShardSize - 1), $ToBlock)
        $suffix = "{0}-{1}-s{2:D2}" -f $DayTag, $SuffixPrefix, $shardIndex
        $args = @($BaseArgs + @(
            "--from-block", [string]$start,
            "--to-block", [string]$end,
            "--checkpoint-suffix", $suffix
        ))
        while (@($jobs | Where-Object { $_.State -eq "Running" }).Count -ge $MaxParallel) {
            $done = Wait-Job -Job $jobs -Any
            $result = Receive-Job -Job $done
            Remove-Job -Job $done
            $jobs = @($jobs | Where-Object { $_.Id -ne $done.Id })
            foreach ($line in $result.Output) {
                Add-RunLogLine ("  " + (Sanitize-Text -Text $line -Secrets $Secrets))
            }
            if ($result.ExitCode -ne 0) {
                $failed = $true
                $failureMessages.Add("$($result.Label) exit=$($result.ExitCode)")
            } else {
                Write-RunLog "DONE $($result.Label)"
            }
        }
        $label = "$Bin $suffix $start..$end"
        Write-RunLog "START $label"
        $jobs += Start-Job -ScriptBlock {
            param($Exe, $ProcArgs, $WorkDir, $Label)
            Set-Location $WorkDir
            $out = & $Exe @ProcArgs 2>&1
            $code = $LASTEXITCODE
            [PSCustomObject]@{
                Label = $Label
                ExitCode = $code
                Output = [string[]]($out | ForEach-Object { [string]$_ })
            }
        } -ArgumentList $exe, $args, $RepoRoot, $label
        $shardIndex++
    }
    while (@($jobs).Count -gt 0) {
        $done = Wait-Job -Job $jobs -Any
        $result = Receive-Job -Job $done
        Remove-Job -Job $done
        $jobs = @($jobs | Where-Object { $_.Id -ne $done.Id })
        foreach ($line in $result.Output) {
            Add-RunLogLine ("  " + (Sanitize-Text -Text $line -Secrets $Secrets))
        }
        if ($result.ExitCode -ne 0) {
            $failed = $true
            $failureMessages.Add("$($result.Label) exit=$($result.ExitCode)")
        } else {
            Write-RunLog "DONE $($result.Label)"
        }
    }
    if ($failed) {
        throw "$Bin shard failures: $($failureMessages -join '; ')"
    }
    Write-RunLog "DONE $Bin shards for $DayTag"
}

function Get-QueuedReceipts {
    param(
        [string]$DataRootAbs,
        [string[]]$HeaderRpcArgs,
        [string[]]$Secrets
    )
    $args = @(
        "--data-root", $DataRootAbs,
        "--from-data-root",
        "--source-scope", "chog-pool-txs",
        "--timestamp-source", "local-first",
        "--rpc-batch-size", "50",
        "--receipt-only",
        "--dry-run"
    ) + $HeaderRpcArgs
    $output = Invoke-Bin -Bin "receipt_sample" -ProcArgs $args -StepName "receipt dry-run" -Secrets $Secrets
    foreach ($line in $output) {
        if ($line -match 'queued hashes after dedupe:\s+(\d+)') {
            return [int]$Matches[1]
        }
    }
    throw "could not parse receipt dry-run queue"
}

function Complete-Receipts {
    param(
        [string]$DataRootAbs,
        [string[]]$HeaderRpcArgs,
        [string[]]$Secrets
    )
    $queued = Get-QueuedReceipts -DataRootAbs $DataRootAbs -HeaderRpcArgs $HeaderRpcArgs -Secrets $Secrets
    Write-RunLog "receipt queue=$queued"
    if ($queued -le 0) {
        return
    }
    $smokeArgs = @(
        "--data-root", $DataRootAbs,
        "--from-data-root",
        "--source-scope", "chog-pool-txs",
        "--timestamp-source", "local-first",
        "--max-txs", "25",
        "--batch-size", "25",
        "--rpc-batch-size", "25",
        "--receipt-only"
    ) + $HeaderRpcArgs
    Invoke-Bin -Bin "receipt_sample" -ProcArgs $smokeArgs -StepName "receipt smoke 25" -Secrets $Secrets | Out-Null
    while ($true) {
        $queued = Get-QueuedReceipts -DataRootAbs $DataRootAbs -HeaderRpcArgs $HeaderRpcArgs -Secrets $Secrets
        Write-RunLog "receipt queue=$queued"
        if ($queued -le 0) {
            break
        }
        $take = [Math]::Min(200, $queued)
        $args = @(
            "--data-root", $DataRootAbs,
            "--from-data-root",
            "--source-scope", "chog-pool-txs",
            "--timestamp-source", "local-first",
            "--max-txs", [string]$take,
            "--batch-size", "50",
            "--rpc-batch-size", "50",
            "--receipt-only"
        ) + $HeaderRpcArgs
        Invoke-Bin -Bin "receipt_sample" -ProcArgs $args -StepName "receipt batch $take" -Secrets $Secrets | Out-Null
    }
}

function Get-PlannedMemecoinParts {
    param(
        [string]$DataRootAbs,
        [string[]]$Secrets
    )
    $output = Invoke-Bin -Bin "dex_rebuild" -ProcArgs @("--data-root", $DataRootAbs, "memecoin-features", "--dry-run") -StepName "memecoin dry-run" -Secrets $Secrets
    $paths = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $output) {
        if ($line -match 'path=(.+)$') {
            $path = [System.IO.Path]::GetFullPath($Matches[1].Trim())
            [void]$paths.Add($path)
        }
    }
    return $paths
}

function Remove-StaleMemecoinParts {
    param(
        [string]$DataRootAbs,
        [System.Collections.Generic.HashSet[string]]$Planned
    )
    $derivedRoot = [System.IO.Path]::GetFullPath((Join-Path $DataRootAbs "derived"))
    $datasets = @("memecoin_event_features", "memecoin_hourly_features")
    $removed = 0
    foreach ($dataset in $datasets) {
        $root = [System.IO.Path]::GetFullPath((Join-Path $derivedRoot $dataset))
        if (-not $root.StartsWith($derivedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "refusing to clean outside derived root: $root"
        }
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -Filter *.parquet -File) {
            $full = [System.IO.Path]::GetFullPath($file.FullName)
            if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "refusing to remove unexpected path: $full"
            }
            if (-not $Planned.Contains($full)) {
                Remove-Item -LiteralPath $full -Force
                $removed++
            }
        }
    }
    Write-RunLog "removed stale memecoin derived parts=$removed"
}

function Rebuild-MemecoinFeatures {
    param(
        [string]$DataRootAbs,
        [string[]]$Secrets
    )
    $planned = Get-PlannedMemecoinParts -DataRootAbs $DataRootAbs -Secrets $Secrets
    Invoke-Bin -Bin "dex_rebuild" -ProcArgs @("--data-root", $DataRootAbs, "memecoin-features") -StepName "memecoin rebuild" -Secrets $Secrets | Out-Null
    Remove-StaleMemecoinParts -DataRootAbs $DataRootAbs -Planned $planned
}

function Invoke-EventHeaders {
    param(
        [UInt64]$FromBlock,
        [UInt64]$ToBlock,
        [string]$DayTag,
        [string]$DataRootAbs,
        [string[]]$HeaderRpcArgs,
        [string[]]$Secrets
    )
    $base = @(
        "--data-root", $DataRootAbs,
        "--from-block", [string]$FromBlock,
        "--to-block", [string]$ToBlock,
        "--batch-size", "200",
        "--batch-throttle-ms", "0"
    ) + $HeaderRpcArgs
    Invoke-Bin -Bin "event_header_sample" -ProcArgs ($base + @("--dry-run")) -StepName "$DayTag event headers dry-run" -Secrets $Secrets | Out-Null
    Invoke-Bin -Bin "event_header_sample" -ProcArgs ($base + @("--checkpoint-suffix", "$DayTag-event-headers")) -StepName "$DayTag event headers" -Secrets $Secrets | Out-Null
}

function Test-RunPhase {
    param(
        [string]$Current,
        [string]$Phase
    )
    $order = @{
        transfer = 0
        v3 = 1
        dex = 2
        headers = 3
        receipts = 4
        features = 5
        quality = 6
    }
    return $order[$Phase] -ge $order[$Current]
}

$envPath = Join-Path $RepoRoot ".env.chog.local"
$vars = Import-ChogEnv -Path $envPath
$secrets = Get-Secrets -Vars $vars

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    if ($vars.ContainsKey("CHOG_DATA_ROOT")) {
        $DataRoot = [string]$vars["CHOG_DATA_ROOT"]
    } else {
        $DataRoot = "data/chog/v1"
    }
}
if (-not [System.IO.Path]::IsPathRooted($DataRoot)) {
    $DataRoot = Join-Path $RepoRoot $DataRoot
}
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)

$logRpcs = Get-VarAsArray -Vars $vars -Name "CHOG_LOG_RPCS"
if ($logRpcs.Count -eq 0) {
    $logRpcs = Get-VarAsArray -Vars $vars -Name "CHOG_PUBLIC_LOG_RPCS"
}
if ($logRpcs.Count -eq 0) {
    throw "no CHOG_LOG_RPCS or CHOG_PUBLIC_LOG_RPCS configured"
}

$headerRpcs = @()
if ($vars.ContainsKey("CHOG_HEADER_RPC") -and -not [string]::IsNullOrWhiteSpace([string]$vars["CHOG_HEADER_RPC"])) {
    $headerRpcs = @([string]$vars["CHOG_HEADER_RPC"])
}
if ($headerRpcs.Count -eq 0) {
    $headerRpcs = @($logRpcs[0])
}

$logRangeBlocks = 1000
if ($vars.ContainsKey("CHOG_LOG_RANGE_BLOCKS")) {
    $logRangeBlocks = [int]$vars["CHOG_LOG_RANGE_BLOCKS"]
}

$logRpcArgs = @()
foreach ($rpc in $logRpcs) {
    $logRpcArgs += @("--rpc-url", [string]$rpc)
}
$headerRpcArgs = @()
foreach ($rpc in $headerRpcs) {
    $headerRpcArgs += @("--rpc-url", [string]$rpc)
}

$commonLogArgs = @(
    "--format", "parquet",
    "--append",
    "--log-range-blocks", [string]$logRangeBlocks,
    "--data-root", $DataRoot
) + $logRpcArgs

$commonDexArgs = @(
    "--append",
    "--log-range-blocks", [string]$logRangeBlocks,
    "--data-root", $DataRoot
) + $logRpcArgs

Write-RunLog "repo=$RepoRoot"
Write-RunLog "data_root=$DataRoot"
Write-RunLog "log_root=$LogRoot"
Write-RunLog "days=$Days first=$FirstDayTag $StartFrom..$StartTo shard_size=$ShardSize max_parallel=$MaxParallelLogShards start_phase=$StartPhase"
Write-RunLog "rpc_config log_count=$($logRpcs.Count) header_count=$($headerRpcs.Count) log_range_blocks=$logRangeBlocks"

$tagDate = [datetime]::ParseExact($FirstDayTag.Substring(3), "yyyyMMdd", $null)
$from = $StartFrom
$to = $StartTo

for ($dayIndex = 0; $dayIndex -lt $Days; $dayIndex++) {
    $dayTag = "day" + $tagDate.AddDays(-$dayIndex).ToString("yyyyMMdd")
    $phase = if ($dayIndex -eq 0) { $StartPhase } else { "transfer" }
    Write-RunLog "DAY START $dayTag $from..$to"
    if (Test-RunPhase -Current $phase -Phase "transfer") {
        Invoke-ShardedCollector -Bin "transfer_sample" -FromBlock $from -ToBlock $to -DayTag $dayTag -SuffixPrefix "transfer" -BaseArgs $commonLogArgs -ShardSize $ShardSize -MaxParallel $MaxParallelLogShards -Secrets $secrets
    } else {
        Write-RunLog "SKIP transfer_sample shards for $dayTag due to start_phase=$phase"
    }
    if (Test-RunPhase -Current $phase -Phase "v3") {
        Invoke-ShardedCollector -Bin "v3_swap_sample" -FromBlock $from -ToBlock $to -DayTag $dayTag -SuffixPrefix "main" -BaseArgs $commonLogArgs -ShardSize $ShardSize -MaxParallel $MaxParallelLogShards -Secrets $secrets
    } else {
        Write-RunLog "SKIP v3_swap_sample shards for $dayTag due to start_phase=$phase"
    }
    if (Test-RunPhase -Current $phase -Phase "dex") {
        Invoke-ShardedCollector -Bin "dex_swap_collect" -FromBlock $from -ToBlock $to -DayTag $dayTag -SuffixPrefix "dex" -BaseArgs $commonDexArgs -ShardSize $ShardSize -MaxParallel $MaxParallelLogShards -Secrets $secrets
    } else {
        Write-RunLog "SKIP dex_swap_collect shards for $dayTag due to start_phase=$phase"
    }
    if (Test-RunPhase -Current $phase -Phase "headers") {
        Invoke-EventHeaders -FromBlock $from -ToBlock $to -DayTag $dayTag -DataRootAbs $DataRoot -HeaderRpcArgs $headerRpcArgs -Secrets $secrets
    } else {
        Write-RunLog "SKIP event headers for $dayTag due to start_phase=$phase"
    }
    if (Test-RunPhase -Current $phase -Phase "receipts") {
        Complete-Receipts -DataRootAbs $DataRoot -HeaderRpcArgs $headerRpcArgs -Secrets $secrets
    } else {
        Write-RunLog "SKIP receipts for $dayTag due to start_phase=$phase"
    }
    if (Test-RunPhase -Current $phase -Phase "features") {
        Rebuild-MemecoinFeatures -DataRootAbs $DataRoot -Secrets $secrets
    } else {
        Write-RunLog "SKIP memecoin features for $dayTag due to start_phase=$phase"
    }
    if (Test-RunPhase -Current $phase -Phase "quality") {
        Invoke-Bin -Bin "chog_quality_check" -ProcArgs @("--data-root", $DataRoot) -StepName "$dayTag quality check" -Secrets $secrets | Out-Null
    } else {
        Write-RunLog "SKIP quality check for $dayTag due to start_phase=$phase"
    }
    Write-RunLog "DAY DONE $dayTag $from..$to"
    $to = $from - 1
    $from = $from - $BlocksPerDay
}

Write-RunLog "ALL DONE"
