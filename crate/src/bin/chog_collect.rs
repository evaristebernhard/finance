use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use chog_prices::{
    Checkpoint, RpcUrlPool,
    chog_v1::{checkpoint_path, default_data_root_path, find_block_at_or_before_timestamp},
    load_checkpoint, rpc_call_hex_u64_from_pool,
};
use chrono::Utc;
use clap::{Parser, ValueEnum};
use reqwest::blocking::Client;
use serde_json::json;

const DEFAULT_RPC_URL: &str = "https://rpc.monad.xyz";
const DEFAULT_LOOKBACK_DAYS: u64 = 30;
const DEFAULT_LOG_RANGE_BLOCKS: u64 = 1_000;
const DEFAULT_HEADER_PART_BLOCKS: u64 = 100;
const DEFAULT_HEADER_BATCH_SIZE: usize = 10;
const DEFAULT_EVENT_HEADER_BATCH_SIZE: usize = 200;
const DEFAULT_HEADER_BATCH_THROTTLE_MS: u64 = 1_300;
const SECONDS_PER_DAY: u64 = 24 * 60 * 60;
const CHOG_LOG_RPCS_ENV: &str = "CHOG_LOG_RPCS";
const CHOG_LOG_RANGE_BLOCKS_ENV: &str = "CHOG_LOG_RANGE_BLOCKS";

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum Mode {
    Backfill,
    Incremental,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum HeaderMode {
    Event,
    Full,
    Skip,
}

#[derive(Debug, Parser)]
#[command(
    name = "chog_collect",
    about = "Run one CHOG v1 collection pass for cron/systemd timers."
)]
struct Args {
    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Collection mode.
    #[arg(long, value_enum)]
    mode: Mode,

    /// Backfill lookback window when --from-block is omitted in backfill mode.
    #[arg(long, default_value_t = DEFAULT_LOOKBACK_DAYS)]
    lookback_days: u64,

    /// Explicit first block for log/header collectors.
    #[arg(long)]
    from_block: Option<u64>,

    /// Explicit final block for log/header collectors. Defaults to latest at run start.
    #[arg(long)]
    to_block: Option<u64>,

    #[arg(long = "rpc-url", default_value = DEFAULT_RPC_URL)]
    rpc_url: Vec<String>,

    /// RPC URLs for eth_getLogs collectors. Defaults to --rpc-url values.
    #[arg(long = "log-rpc-url")]
    log_rpc_url: Vec<String>,

    /// RPC URLs for header and receipt collectors. Defaults to --rpc-url values.
    #[arg(long = "header-rpc-url")]
    header_rpc_url: Vec<String>,

    /// Block range size per eth_getLogs request for log collectors.
    #[arg(long)]
    log_range_blocks: Option<u64>,

    /// Block count per output part/checkpoint chunk for block_header_sample.
    #[arg(long, default_value_t = DEFAULT_HEADER_PART_BLOCKS)]
    header_part_blocks: u64,

    /// Block numbers per JSON-RPC batch for block_header_sample.
    #[arg(long)]
    header_batch_size: Option<usize>,

    /// Milliseconds to sleep between block_header_sample JSON-RPC batches.
    #[arg(long, default_value_t = DEFAULT_HEADER_BATCH_THROTTLE_MS)]
    header_batch_throttle_ms: u64,

    /// Header collection strategy. "event" fetches only blocks that contain local CHOG events.
    #[arg(long, value_enum, default_value_t = HeaderMode::Event)]
    header_mode: HeaderMode,

    /// Suffix for child collector checkpoints, useful for parallel shards.
    #[arg(long)]
    checkpoint_suffix: Option<String>,

    /// Skip the DexScreener pair snapshot.
    #[arg(long)]
    skip_dex_snapshot: bool,

    /// Also collect V2/V3 Swap logs for all known DexScreener CHOG pools.
    #[arg(long)]
    include_dex_swaps: bool,

    /// Skip CHOG hourly prices.
    #[arg(long)]
    skip_prices: bool,

    /// Skip transaction receipt collection.
    #[arg(long)]
    skip_receipts: bool,

    /// Skip memecoin event/hourly feature rebuild.
    #[arg(long)]
    skip_memecoin_features: bool,

    /// Skip CHOG v1 quality checks after collection.
    #[arg(long)]
    skip_quality_check: bool,

    /// Print planned child collector commands without running them.
    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug)]
struct ChildRun {
    bin: &'static str,
    args: Vec<String>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.lookback_days == 0 {
        bail!("--lookback-days must be greater than 0");
    }
    let log_range_blocks = resolve_log_range_blocks(&args)?;
    let header_batch_size = resolve_header_batch_size(&args)?;
    if log_range_blocks == 0 {
        bail!("--log-range-blocks must be greater than 0");
    }
    if header_batch_size == 0 {
        bail!("--header-batch-size must be greater than 0");
    }
    if args.header_part_blocks == 0 {
        bail!("--header-part-blocks must be greater than 0");
    }

    let data_root = args
        .data_root
        .clone()
        .unwrap_or_else(default_data_root_path);
    let client = Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent("finance-chain-chog-collect/0.1")
        .build()
        .context("failed to build HTTP client")?;
    let rpc_urls = RpcUrlPool::from_values(&args.rpc_url, DEFAULT_RPC_URL)?;
    let latest_block =
        rpc_call_hex_u64_from_pool(&client, &rpc_urls, "eth_blockNumber", json!([]))?;
    let to_block = args.to_block.unwrap_or(latest_block);
    let from_block = resolve_from_block(
        &args,
        &data_root,
        &client,
        rpc_urls.primary(),
        latest_block,
        to_block,
    )?;

    println!("mode: {:?}", args.mode);
    println!("fixed latest block at run start: {latest_block}");
    if let Some(from_block) = from_block {
        println!("block window: {from_block}..{to_block}");
    } else {
        println!("block window: resume..{to_block}");
    }

    let mut runs = Vec::new();
    let log_rpc_urls = resolve_log_rpc_urls(&args);
    push_rpc_log_runs(
        &mut runs,
        &args,
        &data_root,
        from_block,
        to_block,
        log_range_blocks,
        &log_rpc_urls,
    );
    push_header_run(
        &mut runs,
        &args,
        &data_root,
        from_block,
        to_block,
        header_batch_size,
    );
    push_snapshot_runs(&mut runs, &args, &data_root)?;
    push_derived_runs(&mut runs, &args, &data_root);

    for run in runs {
        run_child(&run, args.dry_run)?;
    }

    Ok(())
}

fn resolve_from_block(
    args: &Args,
    data_root: &Path,
    client: &Client,
    rpc_url: &str,
    latest_block: u64,
    to_block: u64,
) -> Result<Option<u64>> {
    if let Some(from_block) = args.from_block {
        if from_block > to_block {
            bail!("--from-block {from_block} is greater than --to-block/latest {to_block}");
        }
        return Ok(Some(from_block));
    }

    match args.mode {
        Mode::Incremental => Ok(None),
        Mode::Backfill => {
            let now = Utc::now().timestamp();
            let lookback_seconds = args
                .lookback_days
                .checked_mul(SECONDS_PER_DAY)
                .context("invalid --lookback-days")?;
            let target = now
                .checked_sub(lookback_seconds as i64)
                .context("invalid backfill timestamp")?;
            let from_block =
                find_block_at_or_before_timestamp(client, rpc_url, target as u64, latest_block)?;
            if from_block > to_block {
                bail!(
                    "resolved backfill from block {from_block} is greater than to block {to_block}"
                );
            }
            let _ = data_root;
            Ok(Some(from_block))
        }
    }
}

fn push_rpc_log_runs(
    runs: &mut Vec<ChildRun>,
    args: &Args,
    data_root: &Path,
    from_block: Option<u64>,
    to_block: u64,
    log_range_blocks: u64,
    log_rpc_urls: &[String],
) {
    let mut common = vec![
        "--format".to_string(),
        "parquet".to_string(),
        "--data-root".to_string(),
        data_root.display().to_string(),
        "--log-range-blocks".to_string(),
        log_range_blocks.to_string(),
        "--to-block".to_string(),
        to_block.to_string(),
        "--append".to_string(),
    ];
    push_rpc_url_args(&mut common, log_rpc_urls);
    push_checkpoint_suffix_arg(&mut common, &args.checkpoint_suffix);
    match args.mode {
        Mode::Incremental if from_block.is_none() => common.push("--resume".to_string()),
        _ => {}
    }
    if let Some(from_block) = from_block {
        common.push("--from-block".to_string());
        common.push(from_block.to_string());
    }

    runs.push(ChildRun {
        bin: "transfer_sample",
        args: common.clone(),
    });
    runs.push(ChildRun {
        bin: "v3_swap_sample",
        args: common,
    });
    if args.include_dex_swaps {
        let mut dex_args = vec![
            "--data-root".to_string(),
            data_root.display().to_string(),
            "--log-range-blocks".to_string(),
            log_range_blocks.to_string(),
            "--to-block".to_string(),
            to_block.to_string(),
            "--append".to_string(),
        ];
        push_rpc_url_args(&mut dex_args, log_rpc_urls);
        push_checkpoint_suffix_arg(&mut dex_args, &args.checkpoint_suffix);
        match args.mode {
            Mode::Incremental if from_block.is_none() => dex_args.push("--resume".to_string()),
            _ => {}
        }
        if let Some(from_block) = from_block {
            dex_args.push("--from-block".to_string());
            dex_args.push(from_block.to_string());
        }
        runs.push(ChildRun {
            bin: "dex_swap_collect",
            args: dex_args,
        });
    }
}

fn push_header_run(
    runs: &mut Vec<ChildRun>,
    args: &Args,
    data_root: &Path,
    from_block: Option<u64>,
    to_block: u64,
    header_batch_size: usize,
) {
    match args.header_mode {
        HeaderMode::Skip => {}
        HeaderMode::Event => {
            let mut header_args = vec![
                "--data-root".to_string(),
                data_root.display().to_string(),
                "--to-block".to_string(),
                to_block.to_string(),
                "--batch-size".to_string(),
                header_batch_size.to_string(),
                "--batch-throttle-ms".to_string(),
                args.header_batch_throttle_ms.to_string(),
            ];
            push_rpc_url_args(
                &mut header_args,
                rpc_urls_for(&args.header_rpc_url, &args.rpc_url),
            );
            push_checkpoint_suffix_arg(&mut header_args, &args.checkpoint_suffix);
            if let Some(from_block) = from_block {
                header_args.push("--from-block".to_string());
                header_args.push(from_block.to_string());
            }
            runs.push(ChildRun {
                bin: "event_header_sample",
                args: header_args,
            });
        }
        HeaderMode::Full => {
            let mut header_args = vec![
                "--data-root".to_string(),
                data_root.display().to_string(),
                "--to-block".to_string(),
                to_block.to_string(),
                "--part-blocks".to_string(),
                args.header_part_blocks.to_string(),
                "--batch-size".to_string(),
                header_batch_size.to_string(),
                "--batch-throttle-ms".to_string(),
                args.header_batch_throttle_ms.to_string(),
            ];
            push_rpc_url_args(
                &mut header_args,
                rpc_urls_for(&args.header_rpc_url, &args.rpc_url),
            );
            push_checkpoint_suffix_arg(&mut header_args, &args.checkpoint_suffix);
            match args.mode {
                Mode::Incremental if from_block.is_none() => {
                    header_args.push("--resume".to_string())
                }
                _ => {}
            }
            if let Some(from_block) = from_block {
                header_args.push("--from-block".to_string());
                header_args.push(from_block.to_string());
            }
            runs.push(ChildRun {
                bin: "block_header_sample",
                args: header_args,
            });
        }
    }
}

fn push_snapshot_runs(runs: &mut Vec<ChildRun>, args: &Args, data_root: &Path) -> Result<()> {
    if !args.skip_dex_snapshot {
        runs.push(ChildRun {
            bin: "dex_snapshot",
            args: vec![
                "--format".to_string(),
                "parquet".to_string(),
                "--data-root".to_string(),
                data_root.display().to_string(),
            ],
        });
    }

    if !args.skip_prices && (args.mode == Mode::Backfill || price_due(data_root)?) {
        let hours = args
            .lookback_days
            .checked_mul(24)
            .context("invalid --lookback-days")?;
        runs.push(ChildRun {
            bin: "chog_prices",
            args: vec![
                "--format".to_string(),
                "parquet".to_string(),
                "--data-root".to_string(),
                data_root.display().to_string(),
                "--hours".to_string(),
                hours.to_string(),
            ],
        });
    }

    if !args.skip_receipts {
        let mut receipt_args = vec![
            "--data-root".to_string(),
            data_root.display().to_string(),
            "--from-data-root".to_string(),
            "--source-scope".to_string(),
            "chog-pool-txs".to_string(),
            "--timestamp-source".to_string(),
            "local-first".to_string(),
        ];
        push_rpc_url_args(
            &mut receipt_args,
            rpc_urls_for(&args.header_rpc_url, &args.rpc_url),
        );
        push_checkpoint_suffix_arg(&mut receipt_args, &args.checkpoint_suffix);
        runs.push(ChildRun {
            bin: "receipt_sample",
            args: receipt_args,
        });
    }
    Ok(())
}

fn push_derived_runs(runs: &mut Vec<ChildRun>, args: &Args, data_root: &Path) {
    if !args.skip_memecoin_features {
        runs.push(ChildRun {
            bin: "dex_rebuild",
            args: vec![
                "--data-root".to_string(),
                data_root.display().to_string(),
                "memecoin-features".to_string(),
            ],
        });
    }

    if !args.skip_quality_check {
        runs.push(ChildRun {
            bin: "chog_quality_check",
            args: vec!["--data-root".to_string(), data_root.display().to_string()],
        });
    }
}

fn resolve_log_range_blocks(args: &Args) -> Result<u64> {
    if let Some(value) = args.log_range_blocks {
        return Ok(value);
    }
    match std::env::var(CHOG_LOG_RANGE_BLOCKS_ENV) {
        Ok(value) if !value.trim().is_empty() => value
            .trim()
            .parse::<u64>()
            .with_context(|| format!("invalid {CHOG_LOG_RANGE_BLOCKS_ENV} value {}", value.trim())),
        _ => Ok(DEFAULT_LOG_RANGE_BLOCKS),
    }
}

fn resolve_header_batch_size(args: &Args) -> Result<usize> {
    if let Some(value) = args.header_batch_size {
        return Ok(value);
    }
    Ok(match args.header_mode {
        HeaderMode::Event => DEFAULT_EVENT_HEADER_BATCH_SIZE,
        HeaderMode::Full | HeaderMode::Skip => DEFAULT_HEADER_BATCH_SIZE,
    })
}

fn resolve_log_rpc_urls(args: &Args) -> Vec<String> {
    if !args.log_rpc_url.is_empty() {
        return args.log_rpc_url.clone();
    }
    if let Ok(value) = std::env::var(CHOG_LOG_RPCS_ENV) {
        if !value.trim().is_empty() {
            return vec![value];
        }
    }
    args.rpc_url.clone()
}

fn rpc_urls_for<'a>(preferred: &'a [String], fallback: &'a [String]) -> &'a [String] {
    if preferred.is_empty() {
        fallback
    } else {
        preferred
    }
}

fn push_rpc_url_args(child_args: &mut Vec<String>, rpc_urls: &[String]) {
    for rpc_url in rpc_urls {
        child_args.push("--rpc-url".to_string());
        child_args.push(rpc_url.clone());
    }
}

fn push_checkpoint_suffix_arg(child_args: &mut Vec<String>, checkpoint_suffix: &Option<String>) {
    if let Some(checkpoint_suffix) = checkpoint_suffix {
        child_args.push("--checkpoint-suffix".to_string());
        child_args.push(checkpoint_suffix.clone());
    }
}

fn price_due(data_root: &Path) -> Result<bool> {
    let path = checkpoint_path(data_root, "chog_prices");
    if !path.exists() {
        return Ok(true);
    }
    let checkpoint: Checkpoint = load_checkpoint(&path)?;
    let updated = chrono::DateTime::parse_from_rfc3339(&checkpoint.updated_at_utc)
        .with_context(|| {
            format!(
                "invalid price checkpoint timestamp {}",
                checkpoint.updated_at_utc
            )
        })?
        .with_timezone(&Utc);
    Ok((Utc::now() - updated).num_seconds() >= 60 * 60)
}

fn run_child(run: &ChildRun, dry_run: bool) -> Result<()> {
    if dry_run {
        println!("dry-run: {}", display_child(run));
        return Ok(());
    }

    println!("running: {}", display_child(run));
    let mut command = child_command(run)?;
    let status = command
        .status()
        .with_context(|| format!("failed to run {}", display_child(run)))?;
    if !status.success() {
        bail!(
            "child collector failed with status {status}: {}",
            display_child(run)
        );
    }
    Ok(())
}

fn child_command(run: &ChildRun) -> Result<Command> {
    let current_exe = std::env::current_exe().context("failed to resolve current executable")?;
    let sibling = current_exe.with_file_name(run.bin);
    if sibling.exists() {
        let mut command = Command::new(sibling);
        command.args(&run.args);
        return Ok(command);
    }

    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml");
    let mut command = Command::new("cargo");
    command
        .arg("run")
        .arg("--manifest-path")
        .arg(manifest)
        .arg("--bin")
        .arg(run.bin)
        .arg("--")
        .args(&run.args);
    Ok(command)
}

fn display_child(run: &ChildRun) -> String {
    let mut parts = vec![run.bin.to_string()];
    let mut redact_next = false;
    for arg in &run.args {
        if redact_next {
            parts.push("<redacted>".to_string());
            redact_next = false;
            continue;
        }
        parts.push(arg.clone());
        if arg == "--rpc-url" {
            redact_next = true;
        }
    }
    parts.join(" ")
}
