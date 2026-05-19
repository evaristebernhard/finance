param(
    [string]$DataRoot = "data/mon_usdc/v1",
    [string]$RunTag = "20260510_87d",
    [string]$EnvFile = ".env.chog.local",
    [UInt64]$FromBlock = 54574468,
    [UInt64]$ToBlock = 73366454,
    [int]$TxBodyWorkers = 4,
    [int]$ReceiptLogWorkers = 4,
    [int]$PoolStateShards = 4,
    [int]$TraceShards = 1,
    [int]$TxBodyBatchSize = 50,
    [int]$TxBodyRpcBatchSize = 50,
    [int]$ReceiptLogBatchSize = 250,
    [int]$ReceiptLogRpcBatchSize = 50,
    [int]$PoolStateRpcBatchSize = 25,
    [int]$TraceRpcBatchSize = 1,
    [int]$MaxPoolStateEventBlocks = 20000,
    [int]$MaxTraceTxs = 25000,
    [ValidateSet("debug","release")]
    [string]$Profile = "release",
    [ValidateSet("dry-run","tx-bodies","receipt-logs","derived-1","pool-state","traces","derived-2","quality","all")]
    [string]$StartPhase = "all",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Body
    )
    Write-Host ""
    Write-Host "== $Name =="
    & $Body
}

function Run-Bin {
    param(
        [string]$Exe,
        [string[]]$Args
    )
    $path = Join-Path "target/$Profile" "$Exe.exe"
    if (!(Test-Path $path)) {
        throw "missing binary $path; run without -SkipBuild first or choose -Profile debug"
    }
    Write-Host "$path $($Args -join ' ')"
    & $path @Args
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe failed with exit code $LASTEXITCODE"
    }
}

function Run-Sharded {
    param(
        [string]$Exe,
        [int]$ShardCount,
        [string[]]$BaseArgs
    )
    for ($i = 0; $i -lt $ShardCount; $i++) {
        Run-Bin $Exe ($BaseArgs + @("--shard-index", "$i", "--shard-count", "$ShardCount"))
    }
}

$phaseOrder = @("dry-run","tx-bodies","receipt-logs","derived-1","pool-state","traces","derived-2","quality")
$startIndex = if ($StartPhase -eq "all") { 0 } else { [Array]::IndexOf($phaseOrder, $StartPhase) }
if ($startIndex -lt 0) {
    throw "unknown StartPhase $StartPhase"
}

if (!$SkipBuild) {
    Invoke-Step "Build binaries" {
        if ($Profile -eq "release") {
            cargo build --release -p mon_usdc_collectors -p mon_usdc_research
        } else {
            cargo build -p mon_usdc_collectors -p mon_usdc_research
        }
    }
}

$common = @("--data-root", $DataRoot, "--env-file", $EnvFile, "--from-block", "$FromBlock", "--to-block", "$ToBlock")

if ($startIndex -le [Array]::IndexOf($phaseOrder, "dry-run")) {
    Invoke-Step "Dry-run queues" {
        Run-Bin "mon_usdc_tx_body_sample" ($common + @("--dry-run", "--workers", "$TxBodyWorkers", "--batch-size", "$TxBodyBatchSize", "--rpc-batch-size", "$TxBodyRpcBatchSize"))
        Run-Bin "mon_usdc_receipt_log_bundle" ($common + @("--dry-run", "--workers", "$ReceiptLogWorkers", "--batch-size", "$ReceiptLogBatchSize", "--rpc-batch-size", "$ReceiptLogRpcBatchSize"))
        Run-Bin "mon_usdc_pool_state_sample" ($common + @("--dry-run", "--max-event-blocks", "$MaxPoolStateEventBlocks", "--rpc-batch-size", "$PoolStateRpcBatchSize"))
        Run-Bin "mon_usdc_trace_sample" ($common + @("--dry-run", "--max-txs", "$MaxTraceTxs", "--rpc-batch-size", "$TraceRpcBatchSize"))
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "tx-bodies")) {
    Invoke-Step "Collect tx bodies" {
        Run-Bin "mon_usdc_tx_body_sample" ($common + @("--workers", "$TxBodyWorkers", "--batch-size", "$TxBodyBatchSize", "--rpc-batch-size", "$TxBodyRpcBatchSize", "--checkpoint-suffix", "$RunTag-txbody"))
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "receipt-logs")) {
    Invoke-Step "Collect receipt log bundles" {
        Run-Bin "mon_usdc_receipt_log_bundle" ($common + @("--workers", "$ReceiptLogWorkers", "--batch-size", "$ReceiptLogBatchSize", "--rpc-batch-size", "$ReceiptLogRpcBatchSize", "--checkpoint-suffix", "$RunTag-receiptlogs"))
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "derived-1")) {
    Invoke-Step "Rebuild full derived labels" {
        Run-Bin "mon_usdc_enriched_rebuild" @("--data-root", $DataRoot, "--run-tag", $RunTag)
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "pool-state")) {
    Invoke-Step "Collect pool state samples" {
        Run-Sharded "mon_usdc_pool_state_sample" $PoolStateShards ($common + @("--max-event-blocks", "$MaxPoolStateEventBlocks", "--rpc-batch-size", "$PoolStateRpcBatchSize", "--checkpoint-suffix", "$RunTag-poolstate"))
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "traces")) {
    Invoke-Step "Collect debug trace samples" {
        Run-Sharded "mon_usdc_trace_sample" $TraceShards ($common + @("--max-txs", "$MaxTraceTxs", "--rpc-batch-size", "$TraceRpcBatchSize", "--checkpoint-suffix", "$RunTag-trace"))
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "derived-2")) {
    Invoke-Step "Rebuild enriched outputs and completion report" {
        Run-Bin "mon_usdc_enriched_rebuild" @("--data-root", $DataRoot, "--run-tag", $RunTag)
    }
}

if ($startIndex -le [Array]::IndexOf($phaseOrder, "quality")) {
    Invoke-Step "Quality check" {
        Run-Bin "mon_usdc_quality_check" @("--data-root", $DataRoot, "--from-block", "$FromBlock", "--to-block", "$ToBlock")
    }
}
