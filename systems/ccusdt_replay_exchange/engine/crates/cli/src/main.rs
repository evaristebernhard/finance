use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::Context;
use ccusdt_exchange_sim::PaperExchange;
use ccusdt_replay_core::{
    ExchangeConfig, ReplaySource, build_canonical_dataset, canonical_quote_path,
    load_canonical_l2_updates, load_canonical_trades, load_replay, scan_catalog,
    validate_canonical, write_catalog,
};
use ccusdt_replay_runner::{
    BridgeFailurePolicy, PythonStreamOptions, RunnerOptions, StreamClockMode, ToyStrategyConfig,
    default_run_id, run_python_stream_strategy, run_toy_strategy,
};
use clap::{Parser, Subcommand, ValueEnum};

mod api;

#[derive(Debug, Parser)]
#[command(version, about = "Standalone local CCUSDT paper exchange MVP")]
struct Args {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Serve(ServeArgs),
    Catalog {
        #[command(subcommand)]
        command: CatalogCommand,
    },
    Canonical {
        #[command(subcommand)]
        command: CanonicalCommand,
    },
    Run {
        #[command(subcommand)]
        command: RunCommand,
    },
}

#[derive(Debug, Parser)]
struct ServeArgs {
    #[arg(long, default_value = "127.0.0.1:8797")]
    addr: SocketAddr,

    #[arg(long, default_value = "CCUSDT")]
    symbol: String,

    #[arg(long)]
    csv: Option<PathBuf>,

    #[arg(long)]
    repo_root: Option<PathBuf>,

    #[arg(long)]
    canonical_date: Option<String>,

    #[arg(long, default_value_t = 10_000.0)]
    starting_cash: f64,

    #[arg(long, default_value_t = 0.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 3.0)]
    max_leverage: f64,

    #[arg(long, default_value_t = 10_000)]
    synthetic_frames: usize,
}

#[derive(Debug, Subcommand)]
enum CatalogCommand {
    Scan {
        #[arg(long, default_value = ".")]
        repo_root: PathBuf,

        #[arg(long, default_value = "CCUSDT")]
        symbol: String,
    },
}

#[derive(Debug, Subcommand)]
enum CanonicalCommand {
    Build {
        #[arg(long)]
        dataset: String,

        #[arg(long, default_value = ".")]
        repo_root: PathBuf,

        #[arg(long, default_value = "CCUSDT")]
        symbol: String,

        #[arg(long)]
        from: String,

        #[arg(long)]
        to: String,
    },
    Validate {
        #[arg(long, default_value = ".")]
        repo_root: PathBuf,

        #[arg(long, default_value = "CCUSDT")]
        symbol: String,

        #[arg(long)]
        from: String,

        #[arg(long)]
        to: String,
    },
}

#[derive(Debug, Subcommand)]
enum RunCommand {
    Toy(RunToyArgs),
    Python(RunPythonArgs),
}

#[derive(Debug, Parser)]
struct RunToyArgs {
    #[arg(long, default_value = "CCUSDT")]
    symbol: String,

    #[arg(long)]
    csv: Option<PathBuf>,

    #[arg(long, default_value = ".")]
    repo_root: PathBuf,

    #[arg(long)]
    canonical_date: Option<String>,

    #[arg(long, default_value_t = 1_000)]
    synthetic_frames: usize,

    #[arg(long, default_value = "systems/ccusdt_replay_exchange/runs")]
    run_root: PathBuf,

    #[arg(long)]
    run_id: Option<String>,

    #[arg(long, default_value_t = 1_000)]
    max_frames: usize,

    #[arg(long, default_value_t = 1)]
    latency_frames: u64,

    #[arg(long, default_value_t = 10.0)]
    qty: f64,

    #[arg(long, default_value_t = 20)]
    hold_frames: u64,

    #[arg(long, default_value_t = false)]
    log_holds: bool,

    #[arg(long, default_value_t = 10_000.0)]
    starting_cash: f64,

    #[arg(long, default_value_t = 0.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 3.0)]
    max_leverage: f64,
}

#[derive(Debug, Parser)]
struct RunPythonArgs {
    #[arg(long, default_value = "CCUSDT")]
    symbol: String,

    #[arg(long, default_value = ".")]
    repo_root: PathBuf,

    #[arg(long)]
    canonical_date: String,

    #[arg(long, default_value = "systems/ccusdt_replay_exchange/runs")]
    run_root: PathBuf,

    #[arg(long)]
    run_id: Option<String>,

    #[arg(long, default_value_t = 1_000)]
    max_frames: usize,

    #[arg(long, default_value_t = 0)]
    latency_us: u64,

    #[arg(long, value_enum, default_value_t = ClockModeArg::DeterministicStep)]
    clock_mode: ClockModeArg,

    #[arg(long, default_value_t = 1.0)]
    wall_latency_speedup: f64,

    #[arg(long, default_value = "python")]
    python: PathBuf,

    #[arg(
        long,
        default_value = "systems/ccusdt_replay_exchange/strategies/python/ccusdt_tfi_core_idle01/strategy.py"
    )]
    strategy_script: PathBuf,

    #[arg(long = "strategy-arg")]
    strategy_args: Vec<String>,

    #[arg(long, default_value_t = 1_000)]
    bridge_timeout_ms: u64,

    #[arg(long, value_enum, default_value_t = FailurePolicyArg::FailFast)]
    failure_policy: FailurePolicyArg,

    #[arg(long, default_value_t = false)]
    include_l2: bool,

    #[arg(long)]
    l2_max_rows: Option<usize>,

    #[arg(long, default_value_t = 200)]
    l2_batch_size: usize,

    #[arg(long)]
    l2_depth_smoke_qty: Option<f64>,

    #[arg(long, default_value_t = 10_000.0)]
    starting_cash: f64,

    #[arg(long, default_value_t = 0.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 3.0)]
    max_leverage: f64,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum FailurePolicyArg {
    FailFast,
    HoldAndLog,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum ClockModeArg {
    DeterministicStep,
    AcceleratedAsync,
}

impl From<ClockModeArg> for StreamClockMode {
    fn from(value: ClockModeArg) -> Self {
        match value {
            ClockModeArg::DeterministicStep => Self::DeterministicStep,
            ClockModeArg::AcceleratedAsync => Self::AcceleratedAsync,
        }
    }
}

impl From<FailurePolicyArg> for BridgeFailurePolicy {
    fn from(value: FailurePolicyArg) -> Self {
        match value {
            FailurePolicyArg::FailFast => Self::FailFast,
            FailurePolicyArg::HoldAndLog => Self::HoldAndLog,
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "ccusdt_replay_exchange=info,tower_http=info".into()),
        )
        .init();

    let args = Args::parse();
    match args.command {
        Command::Serve(args) => serve(args).await,
        Command::Catalog {
            command: CatalogCommand::Scan { repo_root, symbol },
        } => {
            let catalog = scan_catalog(&repo_root, &symbol)?;
            let path = write_catalog(&repo_root, &catalog)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "ok": true,
                    "catalog_path": path.to_string_lossy().replace('\\', "/"),
                    "datasets": catalog.datasets.len(),
                    "feature_sidecars": catalog.feature_sidecars.len(),
                    "legacy_research_artifacts": catalog.legacy_research_artifacts.len()
                }))?
            );
            Ok(())
        }
        Command::Canonical { command } => match command {
            CanonicalCommand::Build {
                dataset,
                repo_root,
                symbol,
                from,
                to,
            } => {
                let result = build_canonical_dataset(&repo_root, &symbol, &dataset, &from, &to)?;
                println!("{}", serde_json::to_string_pretty(&result)?);
                Ok(())
            }
            CanonicalCommand::Validate {
                repo_root,
                symbol,
                from,
                to,
            } => {
                let result = validate_canonical(&repo_root, &symbol, &from, &to)?;
                println!("{}", serde_json::to_string_pretty(&result)?);
                Ok(())
            }
        },
        Command::Run { command } => match command {
            RunCommand::Toy(args) => {
                let summary = run_toy(args)?;
                println!("{}", serde_json::to_string_pretty(&summary)?);
                Ok(())
            }
            RunCommand::Python(args) => {
                let summary = run_python(args)?;
                println!("{}", serde_json::to_string_pretty(&summary)?);
                Ok(())
            }
        },
    }
}

async fn serve(args: ServeArgs) -> anyhow::Result<()> {
    let source = match args.csv {
        Some(path) => ReplaySource::Csv(path),
        None if args.canonical_date.is_some() => {
            let repo_root = args.repo_root.unwrap_or_else(|| PathBuf::from("."));
            ReplaySource::Csv(canonical_quote_path(
                &repo_root,
                &args.symbol,
                args.canonical_date.as_deref().unwrap(),
            ))
        }
        None => ReplaySource::Synthetic {
            frames: args.synthetic_frames,
        },
    };
    let frames = load_replay(source).context("failed to load replay source")?;
    let config = ExchangeConfig {
        symbol: args.symbol,
        starting_cash: args.starting_cash,
        fee_bps: args.fee_bps,
        max_leverage: args.max_leverage,
    };
    let exchange = PaperExchange::new(config, frames)?;
    api::serve(exchange, args.addr).await
}

fn run_toy(args: RunToyArgs) -> anyhow::Result<ccusdt_replay_runner::RunSummary> {
    let (source, source_label) = replay_source(
        args.csv.clone(),
        Some(args.repo_root.clone()),
        args.canonical_date.clone(),
        &args.symbol,
        args.synthetic_frames,
    );
    let frames = load_replay(source).context("failed to load replay source")?;
    run_toy_strategy(
        frames,
        RunnerOptions {
            run_id: args.run_id.unwrap_or_else(|| default_run_id("toy_runner")),
            run_root: args.run_root,
            source_label,
            exchange_config: ExchangeConfig {
                symbol: args.symbol,
                starting_cash: args.starting_cash,
                fee_bps: args.fee_bps,
                max_leverage: args.max_leverage,
            },
            max_frames: args.max_frames,
            latency_frames: args.latency_frames,
            log_holds: args.log_holds,
            strategy: ToyStrategyConfig {
                qty: args.qty,
                hold_frames: args.hold_frames,
            },
        },
    )
}

fn run_python(args: RunPythonArgs) -> anyhow::Result<ccusdt_replay_runner::PythonStreamSummary> {
    let quote_path = canonical_quote_path(&args.repo_root, &args.symbol, &args.canonical_date);
    let frames = load_replay(ReplaySource::Csv(quote_path))
        .with_context(|| format!("load canonical quote frames for {}", args.canonical_date))?;
    let trades = load_canonical_trades(&args.repo_root, &args.symbol, &args.canonical_date)
        .with_context(|| format!("load canonical trades for {}", args.canonical_date))?;
    let l2_updates = if args.include_l2 {
        load_canonical_l2_updates(
            &args.repo_root,
            &args.symbol,
            &args.canonical_date,
            args.l2_max_rows,
        )
        .with_context(|| format!("load canonical L2 updates for {}", args.canonical_date))?
    } else {
        Vec::new()
    };
    run_python_stream_strategy(
        frames,
        trades,
        l2_updates,
        PythonStreamOptions {
            run_id: args
                .run_id
                .unwrap_or_else(|| default_run_id("python_stream_runner")),
            run_root: args.run_root,
            source_label: format!(
                "canonical_exchange_stream_v1:{}:{}",
                args.symbol, args.canonical_date
            ),
            exchange_config: ExchangeConfig {
                symbol: args.symbol,
                starting_cash: args.starting_cash,
                fee_bps: args.fee_bps,
                max_leverage: args.max_leverage,
            },
            max_frames: args.max_frames,
            latency_us: args.latency_us,
            clock_mode: args.clock_mode.into(),
            wall_latency_speedup: args.wall_latency_speedup,
            bridge_timeout_ms: args.bridge_timeout_ms,
            failure_policy: args.failure_policy.into(),
            python: args.python,
            strategy_script: args.strategy_script,
            strategy_args: args.strategy_args,
            include_l2: args.include_l2,
            l2_batch_size: args.l2_batch_size,
            l2_depth_smoke_qty: args.l2_depth_smoke_qty,
        },
    )
}

fn replay_source(
    csv: Option<PathBuf>,
    repo_root: Option<PathBuf>,
    canonical_date: Option<String>,
    symbol: &str,
    synthetic_frames: usize,
) -> (ReplaySource, String) {
    match csv {
        Some(path) => {
            let label = format!("csv:{}", path.to_string_lossy().replace('\\', "/"));
            (ReplaySource::Csv(path), label)
        }
        None if canonical_date.is_some() => {
            let repo_root = repo_root.unwrap_or_else(|| PathBuf::from("."));
            let date = canonical_date.expect("checked canonical date");
            let path = canonical_quote_path(&repo_root, symbol, &date);
            (
                ReplaySource::Csv(path),
                format!("canonical_quote_frame_v1:{symbol}:{date}"),
            )
        }
        None => (
            ReplaySource::Synthetic {
                frames: synthetic_frames,
            },
            format!("synthetic:{synthetic_frames}"),
        ),
    }
}
