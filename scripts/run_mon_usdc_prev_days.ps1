param(
    [int]$Days = 50,
    [UInt64]$AnchorFromBlock = 70990455,
    [UInt64]$BlocksPerDay = 216000,
    [string]$RunTag = "prev50-20260509",
    [string]$DataRoot = "data/mon_usdc/v1",
    [UInt64]$LogRangeBlocks = 1000,
    [int]$LogBatchSize = 8,
    [int]$HeaderBatchSize = 500,
    [int]$SwapParallelism = 2,
    [int]$SwapMaxAttempts = 5,
    [int]$ReceiptShardCount = 4,
    [int]$ReceiptBatchSize = 500,
    [int]$ReceiptRpcBatchSize = 100,
    [string]$EnvFile = ".env.chog.local",
    [string]$FastLogRpcEnvVar = "ALCHEMY_RPC",
    [string[]]$SwapRpcUrl = @(),
    [switch]$SkipSwaps,
    [switch]$SkipHeaders,
    [switch]$SkipReceipts,
    [switch]$SkipQuality
)

$ErrorActionPreference = "Stop"

function Resolve-LocalPath {
    param([string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Exe,
        [string[]]$StepArgs
    )
    Write-Host "[$(Get-Date -Format o)] START $Name"
    & $Exe @StepArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
    Write-Host "[$(Get-Date -Format o)] DONE  $Name"
}

function Get-Checkpoint {
    param(
        [string]$Collector,
        [string]$Suffix
    )
    $path = Join-Path $script:DataRootPath "_checkpoints/${Collector}--${Suffix}.json"
    if (Test-Path $path) {
        return Get-Content -Raw $path | ConvertFrom-Json
    }
    return $null
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Name
    )
    if (-not (Test-Path $Path)) {
        return $null
    }
    $pattern = "^\s*(?:export\s+)?$([regex]::Escape($Name))\s*=\s*(.*)\s*$"
    foreach ($line in Get-Content $Path) {
        if ($line -match $pattern) {
            $value = $Matches[1].Trim()
            $quote = $null
            $end = $value.Length
            for ($i = 0; $i -lt $value.Length; $i++) {
                $ch = $value[$i]
                if ($ch -eq '"' -or $ch -eq "'") {
                    if ($quote -eq $ch) {
                        $quote = $null
                    } elseif ($null -eq $quote) {
                        $quote = $ch
                    }
                } elseif ($ch -eq "#" -and $null -eq $quote) {
                    $end = $i
                    break
                }
            }
            $value = $value.Substring(0, $end).Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }
    return $null
}

function Split-RpcValues {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }
    $text = $Value.Trim()
    if (($text.StartsWith("[") -and $text.EndsWith("]")) -or
        ($text.StartsWith("(") -and $text.EndsWith(")"))) {
        $text = $text.Substring(1, $text.Length - 2)
    }
    return @($text -split '[,\s]+' | ForEach-Object { $_.Trim().Trim('"').Trim("'") } | Where-Object { $_ })
}

function Get-DayWindow {
    param([int]$Day)
    $dayTo = [UInt64]($AnchorFromBlock - ([UInt64]($Day - 1) * $BlocksPerDay) - 1)
    $dayFrom = [UInt64]($dayTo - $BlocksPerDay + 1)
    $dayId = "d{0:D2}" -f $Day
    return [pscustomobject]@{
        Day = $Day
        DayId = $dayId
        From = $dayFrom
        To = $dayTo
        Suffix = "mon-usdc-${RunTag}-${dayId}"
    }
}

function Get-RunMiddleSuffix {
    param([string]$Middle)
    if ($RunTag -match "^(.*)-(\d{8})$") {
        return "mon-usdc-$($Matches[1])-${Middle}-$($Matches[2])"
    }
    return "mon-usdc-${RunTag}-${Middle}"
}

function Get-LogPrefix {
    if ($RunTag -match "^(.*)-\d{8}$") {
        return "mon_usdc_$($Matches[1])"
    }
    return "mon_usdc_$($RunTag -replace '[^A-Za-z0-9_]+', '_')"
}

function Get-SwapPlan {
    param([object]$Window)
    $checkpoint = Get-Checkpoint -Collector "mon_usdc_swap_collect" -Suffix $Window.Suffix
    if ($null -ne $checkpoint) {
        $lastCompleted = [UInt64]$checkpoint.last_completed_block
        if ($lastCompleted -ge [UInt64]$Window.To) {
            return [pscustomobject]@{
                Status = "complete"
                From = [UInt64]$Window.From
                LastCompleted = $lastCompleted
            }
        }
        if ($lastCompleted -ge [UInt64]$Window.From) {
            return [pscustomobject]@{
                Status = "resume"
                From = [UInt64]($lastCompleted + 1)
                LastCompleted = $lastCompleted
            }
        }
    }
    return [pscustomobject]@{
        Status = "pending"
        From = [UInt64]$Window.From
        LastCompleted = $null
    }
}

function Assert-SwapCheckpoints {
    param([object[]]$Windows)
    foreach ($window in $Windows) {
        $checkpoint = Get-Checkpoint -Collector "mon_usdc_swap_collect" -Suffix $window.Suffix
        if ($null -eq $checkpoint) {
            throw "missing swap checkpoint for $($window.DayId): $($window.Suffix)"
        }
        $lastCompleted = [UInt64]$checkpoint.last_completed_block
        if ($lastCompleted -lt [UInt64]$window.To) {
            throw "incomplete swap checkpoint for $($window.DayId): last_completed_block=$lastCompleted target=$($window.To)"
        }
    }
}

function Test-SwapCheckpointComplete {
    param([object]$Job)
    $checkpoint = Get-Checkpoint -Collector "mon_usdc_swap_collect" -Suffix $Job.Suffix
    if ($null -eq $checkpoint) {
        return $false
    }
    return ([UInt64]$checkpoint.last_completed_block -ge [UInt64]$Job.To)
}

function Invoke-WithRpcEnvCleared {
    param([scriptblock]$Body)
    $names = @(
        "MON_USDC_RPC_URLS",
        "MONAD_RPC_URLS",
        "CHOG_LOG_RPCS",
        "CHOG_PUBLIC_LOG_RPCS",
        "CHOG_HEADER_RPC",
        "ALCHEMY_RPC",
        "RPC_URL"
    )
    $saved = @{}
    foreach ($name in $names) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
    try {
        & $Body
    } finally {
        foreach ($name in $names) {
            [Environment]::SetEnvironmentVariable($name, $saved[$name], "Process")
        }
    }
}

function Start-SwapJob {
    param([object]$Job)
    $swapArgs = @(
        "--rpc-url", $Job.RpcUrl,
        "--env-file", $script:EmptySwapEnvFile,
        "--from-block", "$($Job.From)",
        "--to-block", "$($Job.To)",
        "--data-root", $script:DataRootPath,
        "--log-range-blocks", "$LogRangeBlocks",
        "--log-batch-size", "$LogBatchSize",
        "--checkpoint-suffix", $Job.Suffix
    )
    Write-Host "[$(Get-Date -Format o)] START swaps $($Job.DayId) $($Job.From)..$($Job.To) rpc_slot=$($Job.RpcSlot)"
    Invoke-WithRpcEnvCleared {
        $process = Start-Process `
            -FilePath $script:SwapExe `
            -ArgumentList $swapArgs `
            -RedirectStandardOutput $Job.OutLog `
            -RedirectStandardError $Job.ErrLog `
            -WindowStyle Hidden `
            -PassThru
        $Job | Add-Member -NotePropertyName Process -NotePropertyValue $process -Force
    }
    return $Job
}

function Stop-ActiveJobs {
    param([object[]]$Jobs)
    foreach ($job in $Jobs) {
        if ($null -ne $job.Process) {
            $job.Process.Refresh()
            if (-not $job.Process.HasExited) {
                Stop-Process -Id $job.Process.Id -Force
            }
        }
    }
}

function Write-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 12
    )
    if (Test-Path $Path) {
        Get-Content $Path -Tail $Lines
    }
}

function Invoke-SwapQueue {
    param(
        [object[]]$Jobs,
        [int]$Parallelism
    )
    if ($Jobs.Count -eq 0) {
        Write-Host "[$(Get-Date -Format o)] swaps queue empty"
        return
    }

    $pending = [System.Collections.Generic.Queue[object]]::new()
    foreach ($job in $Jobs) {
        $pending.Enqueue($job)
    }
    $active = @()
    try {
        while ($pending.Count -gt 0 -or $active.Count -gt 0) {
            while ($pending.Count -gt 0 -and $active.Count -lt $Parallelism) {
                $active += Start-SwapJob -Job $pending.Dequeue()
            }

            Start-Sleep -Seconds 30
            $stillRunning = @()
            foreach ($job in $active) {
                $job.Process.Refresh()
                if ($job.Process.HasExited) {
                    $job.Process.WaitForExit()
                    $exitCode = $job.Process.ExitCode
                    if ([string]::IsNullOrWhiteSpace("$exitCode") -and
                        (Test-SwapCheckpointComplete -Job $job) -and
                        ((-not (Test-Path $job.ErrLog)) -or ((Get-Item $job.ErrLog).Length -eq 0))) {
                        $exitCode = 0
                    }
                    if ($exitCode -ne 0) {
                        Write-Host "--- $([System.IO.Path]::GetFileName($job.ErrLog)) ERR ---"
                        Write-LogTail -Path $job.ErrLog -Lines 30
                        if ($job.Attempt -lt $SwapMaxAttempts) {
                            $checkpoint = Get-Checkpoint -Collector "mon_usdc_swap_collect" -Suffix $job.Suffix
                            if ($null -ne $checkpoint) {
                                $lastCompleted = [UInt64]$checkpoint.last_completed_block
                                if ($lastCompleted -ge [UInt64]$job.From -and $lastCompleted -lt [UInt64]$job.To) {
                                    $job.From = [UInt64]($lastCompleted + 1)
                                }
                            }
                            $job.Attempt += 1
                            $job.RpcSlot = (($job.RpcSlot + 1) % $script:SwapRpcValues.Count)
                            $job.RpcUrl = $script:SwapRpcValues[$job.RpcSlot]
                            Write-Host "[$(Get-Date -Format o)] RETRY swaps $($job.DayId) attempt=$($job.Attempt)/$SwapMaxAttempts from $($job.From) rpc_slot=$($job.RpcSlot)"
                            $pending.Enqueue($job)
                            continue
                        }
                        throw "swaps $($job.DayId) failed with exit code $exitCode"
                    }
                    Write-Host "[$(Get-Date -Format o)] DONE  swaps $($job.DayId) $($job.From)..$($job.To)"
                    Write-Host "--- $([System.IO.Path]::GetFileName($job.OutLog)) ---"
                    Write-LogTail -Path $job.OutLog -Lines 8
                    if ((Test-Path $job.ErrLog) -and ((Get-Item $job.ErrLog).Length -gt 0)) {
                        Write-Host "--- $([System.IO.Path]::GetFileName($job.ErrLog)) ERR ---"
                        Write-LogTail -Path $job.ErrLog -Lines 20
                    }
                } else {
                    $stillRunning += $job
                }
            }
            $active = $stillRunning
            if ($active.Count -gt 0 -or $pending.Count -gt 0) {
                Write-Host "[$(Get-Date -Format o)] swap jobs running=$($active.Count) pending=$($pending.Count)"
            }
        }
    } catch {
        Stop-ActiveJobs -Jobs $active
        throw
    }
}

if ($Days -le 0) {
    throw "-Days must be greater than 0"
}
if ($BlocksPerDay -eq 0) {
    throw "-BlocksPerDay must be greater than 0"
}
if ($LogRangeBlocks -eq 0) {
    throw "-LogRangeBlocks must be greater than 0"
}
if ($LogBatchSize -le 0) {
    throw "-LogBatchSize must be greater than 0"
}
if ($HeaderBatchSize -le 0) {
    throw "-HeaderBatchSize must be greater than 0"
}
if ($SwapParallelism -le 0) {
    throw "-SwapParallelism must be greater than 0"
}
if ($SwapMaxAttempts -le 0) {
    throw "-SwapMaxAttempts must be greater than 0"
}
if ($ReceiptShardCount -le 0) {
    throw "-ReceiptShardCount must be greater than 0"
}

$repoRoot = (Resolve-Path ".").Path
$script:DataRootPath = Resolve-LocalPath -Path $DataRoot
$envFilePath = Resolve-LocalPath -Path $EnvFile
$script:SwapExe = Join-Path $repoRoot "target/debug/mon_usdc_swap_collect.exe"
$headerExe = Join-Path $repoRoot "target/debug/mon_usdc_event_header_sample.exe"
$receiptExe = Join-Path $repoRoot "target/debug/mon_usdc_receipt_sample.exe"
$qualityExe = Join-Path $repoRoot "target/debug/mon_usdc_quality_check.exe"
$script:EmptySwapEnvFile = Join-Path $repoRoot ".mon_usdc_swap_only_empty_env"
$logDir = Join-Path $repoRoot "logs"
$logPrefix = Get-LogPrefix
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

foreach ($exe in @($script:SwapExe, $headerExe, $receiptExe, $qualityExe)) {
    if (-not (Test-Path $exe)) {
        throw "required executable not found: $exe"
    }
}
if (-not (Test-Path $script:DataRootPath)) {
    throw "data root not found: $script:DataRootPath"
}

$swapRpcValues = @($SwapRpcUrl | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
if ($swapRpcValues.Count -eq 0) {
    $envValue = Get-EnvValue -Path $envFilePath -Name $FastLogRpcEnvVar
    $swapRpcValues = @(Split-RpcValues -Value $envValue)
}
if (-not $SkipSwaps -and $swapRpcValues.Count -eq 0) {
    throw "no fast swap RPCs configured in $FastLogRpcEnvVar or -SwapRpcUrl"
}

$effectiveSwapParallelism = $SwapParallelism
if ($swapRpcValues.Count -gt 0 -and $effectiveSwapParallelism -gt $swapRpcValues.Count) {
    $effectiveSwapParallelism = $swapRpcValues.Count
}
$script:SwapRpcValues = $swapRpcValues

$windows = @()
for ($day = 1; $day -le $Days; $day++) {
    $windows += Get-DayWindow -Day $day
}

Write-Host "[$(Get-Date -Format o)] MON/USDC previous-day runner"
Write-Host "days=$Days anchor_from=$AnchorFromBlock blocks_per_day=$BlocksPerDay run_tag=$RunTag data_root=$script:DataRootPath"
Write-Host "swap_parallelism=$effectiveSwapParallelism swap_max_attempts=$SwapMaxAttempts log_range_blocks=$LogRangeBlocks log_batch_size=$LogBatchSize"
if (-not $SkipSwaps) {
    Write-Host "[$(Get-Date -Format o)] swap RPC override enabled: $($swapRpcValues.Count) fast endpoints from $FastLogRpcEnvVar/CLI"
}
Write-Host "[$(Get-Date -Format o)] requested window $($windows[-1].From)..$($windows[0].To)"

if (-not $SkipSwaps) {
    Write-Host "[$(Get-Date -Format o)] PHASE swaps first"
    $swapJobs = @()
    $swapJobIndex = 0
    foreach ($window in $windows) {
        $plan = Get-SwapPlan -Window $window
        if ($plan.Status -eq "complete") {
            Write-Host "[$(Get-Date -Format o)] SKIP swaps $($window.DayId) $($window.From)..$($window.To) checkpoint complete"
            continue
        }
        if ($plan.Status -eq "resume") {
            Write-Host "[$(Get-Date -Format o)] RESUME swaps $($window.DayId) from $($plan.From) after checkpoint"
        }
        $rpcSlot = ($swapJobIndex % $swapRpcValues.Count)
        $swapJobIndex += 1
        $swapJobs += [pscustomobject]@{
            DayId = $window.DayId
            From = [UInt64]$plan.From
            To = [UInt64]$window.To
            Suffix = $window.Suffix
            RpcUrl = $swapRpcValues[$rpcSlot]
            RpcSlot = $rpcSlot
            OutLog = Join-Path $logDir "${logPrefix}_swaps_$($window.DayId).out"
            ErrLog = Join-Path $logDir "${logPrefix}_swaps_$($window.DayId).err"
            Process = $null
            Attempt = 1
        }
    }
    Invoke-SwapQueue -Jobs $swapJobs -Parallelism $effectiveSwapParallelism
    Assert-SwapCheckpoints -Windows $windows
}

if (-not $SkipHeaders) {
    Write-Host "[$(Get-Date -Format o)] PHASE headers after all swaps"
    Invoke-Step -Name "headers all swap event blocks" -Exe $headerExe -StepArgs @(
        "--data-root", $script:DataRootPath,
        "--batch-size", "$HeaderBatchSize",
        "--checkpoint-suffix", (Get-RunMiddleSuffix -Middle "headers-all")
    )
}

if (-not $SkipReceipts) {
    Write-Host "[$(Get-Date -Format o)] PHASE receipts after headers"
    Invoke-Step -Name "receipt dry-run before shards" -Exe $receiptExe -StepArgs @(
        "--dry-run",
        "--from-data-root",
        "--data-root", $script:DataRootPath
    )

    $processes = @()
    for ($shard = 0; $shard -lt $ReceiptShardCount; $shard++) {
        $out = Join-Path $logDir "${logPrefix}_receipts_shard${shard}.out"
        $err = Join-Path $logDir "${logPrefix}_receipts_shard${shard}.err"
        $suffix = Get-RunMiddleSuffix -Middle "receipts-shard${shard}"
        $args = @(
            "--from-data-root",
            "--data-root", $script:DataRootPath,
            "--batch-size", "$ReceiptBatchSize",
            "--rpc-batch-size", "$ReceiptRpcBatchSize",
            "--receipt-only",
            "--shard-index", "$shard",
            "--shard-count", "$ReceiptShardCount",
            "--checkpoint-suffix", $suffix
        )
        Write-Host "[$(Get-Date -Format o)] START receipt shard $shard/$ReceiptShardCount"
        $processes += [pscustomobject]@{
            Shard = $shard
            OutLog = $out
            ErrLog = $err
            Process = Start-Process -FilePath $receiptExe -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
        }
    }

    while ($true) {
        $running = @($processes | Where-Object {
            $_.Process.Refresh()
            -not $_.Process.HasExited
        })
        Write-Host "[$(Get-Date -Format o)] receipt shards running=$($running.Count)"
        if ($running.Count -eq 0) {
            break
        }
        Start-Sleep -Seconds 60
    }

    foreach ($job in $processes) {
        $job.Process.Refresh()
        if ($job.Process.HasExited) {
            $job.Process.WaitForExit()
        }
        $exitCode = $job.Process.ExitCode
        if ([string]::IsNullOrWhiteSpace("$exitCode") -and
            ((-not (Test-Path $job.ErrLog)) -or ((Get-Item $job.ErrLog).Length -eq 0))) {
            $exitCode = 0
        }
        if ($exitCode -ne 0) {
            Write-Host "--- $([System.IO.Path]::GetFileName($job.ErrLog)) ERR ---"
            Write-LogTail -Path $job.ErrLog -Lines 30
            throw "receipt shard $($job.Shard) failed with exit code $exitCode"
        }
    }

    foreach ($job in $processes) {
        Write-Host "--- $([System.IO.Path]::GetFileName($job.OutLog)) ---"
        Write-LogTail -Path $job.OutLog -Lines 8
    }
    foreach ($job in $processes) {
        if ((Test-Path $job.ErrLog) -and ((Get-Item $job.ErrLog).Length -gt 0)) {
            Write-Host "--- $([System.IO.Path]::GetFileName($job.ErrLog)) ERR ---"
            Write-LogTail -Path $job.ErrLog -Lines 20
        }
    }

    Invoke-Step -Name "receipt dry-run after shards" -Exe $receiptExe -StepArgs @(
        "--dry-run",
        "--from-data-root",
        "--data-root", $script:DataRootPath
    )
}

if (-not $SkipQuality) {
    Invoke-Step -Name "event header dry-run final" -Exe $headerExe -StepArgs @(
        "--dry-run",
        "--data-root", $script:DataRootPath
    )
    Invoke-Step -Name "quality check final" -Exe $qualityExe -StepArgs @(
        "--data-root", $script:DataRootPath
    )
}

Write-Host "[$(Get-Date -Format o)] MON/USDC previous-day runner complete"
