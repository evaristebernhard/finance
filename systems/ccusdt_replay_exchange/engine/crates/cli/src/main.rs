use std::io::{BufRead, BufReader};
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::{Command as ProcessCommand, Stdio};

use anyhow::Context;
use ccusdt_exchange_sim::PaperExchange;
use ccusdt_replay_core::{
    ExchangeConfig, MarketFrame, ReplaySource, TradeEvent, build_canonical_dataset,
    canonical_quote_path, load_canonical_l2_updates, load_canonical_trades, load_replay,
    scan_catalog, stream_canonical_market, validate_canonical, write_catalog,
};
use ccusdt_replay_runner::{
    BridgeFailurePolicy, OrderArrivalMode, PanelDecisionFrame, PythonStreamOptions, RunnerOptions,
    RunnerServerOptions, SparsePublicStreamMode, SparsePythonStreamOptions, StreamClockMode,
    StreamLogMode, TakerFillModel, ToyStrategyConfig, default_run_id,
    run_panel_sparse_fast_clock_python_stream_strategy, run_panel_sparse_python_stream_strategy,
    run_python_stream_strategy, run_runner_server, run_sparse_python_stream_strategy,
    run_toy_strategy,
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
    SparsePython(RunSparsePythonArgs),
    Server(RunServerArgs),
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

    #[arg(long, value_enum, default_value_t = ArrivalModeArg::Timer)]
    arrival_mode: ArrivalModeArg,

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

#[derive(Debug, Parser)]
struct RunSparsePythonArgs {
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

    #[arg(long, default_value_t = 10_000)]
    max_events: usize,

    #[arg(long, default_value_t = 0)]
    latency_us: u64,

    #[arg(long, value_enum, default_value_t = ArrivalModeArg::Timer)]
    arrival_mode: ArrivalModeArg,

    #[arg(long, value_enum, default_value_t = ClockModeArg::DeterministicStep)]
    clock_mode: ClockModeArg,

    #[arg(long, default_value_t = 1.0)]
    wall_latency_speedup: f64,

    #[arg(long, value_enum, default_value_t = LogModeArg::Compact)]
    log_mode: LogModeArg,

    #[arg(long, value_enum, default_value_t = FillModelArg::TopOfBook)]
    fill_model: FillModelArg,

    #[arg(long, value_enum, default_value_t = PublicStreamModeArg::StrictEvent)]
    public_stream_mode: PublicStreamModeArg,

    #[arg(long, default_value_t = 512)]
    public_batch_size: usize,

    #[arg(long, default_value_t = 30_000_000)]
    public_batch_max_span_us: u64,

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

    #[arg(long, default_value_t = false)]
    compact_l2: bool,

    #[arg(long, default_value_t = 10_000.0)]
    starting_cash: f64,

    #[arg(long, default_value_t = 0.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 3.0)]
    max_leverage: f64,
}

#[derive(Debug, Parser)]
struct RunServerArgs {
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

    #[arg(long, default_value_t = 10_000)]
    max_events: usize,

    #[arg(long, default_value_t = 0)]
    latency_us: u64,

    #[arg(long, value_enum, default_value_t = ArrivalModeArg::Timer)]
    arrival_mode: ArrivalModeArg,

    #[arg(long, value_enum, default_value_t = ClockModeArg::DeterministicStep)]
    clock_mode: ClockModeArg,

    #[arg(long, default_value_t = 1.0)]
    wall_latency_speedup: f64,

    #[arg(long, value_enum, default_value_t = LogModeArg::Compact)]
    log_mode: LogModeArg,

    #[arg(long, value_enum, default_value_t = FillModelArg::TopOfBook)]
    fill_model: FillModelArg,

    #[arg(long, default_value = "127.0.0.1:8801")]
    public_addr: SocketAddr,

    #[arg(long, default_value = "127.0.0.1:8802")]
    private_addr: SocketAddr,

    #[arg(long, default_value = "127.0.0.1:8803")]
    order_addr: SocketAddr,

    #[arg(long)]
    state_addr: Option<SocketAddr>,

    #[arg(long, default_value_t = 500)]
    startup_wait_ms: u64,

    #[arg(long, default_value_t = 0)]
    event_sleep_us: u64,

    #[arg(long, default_value_t = false)]
    include_l2: bool,

    #[arg(long)]
    l2_max_rows: Option<usize>,

    #[arg(long, default_value_t = 200)]
    l2_batch_size: usize,

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

#[derive(Clone, Copy, Debug, ValueEnum)]
enum LogModeArg {
    Compact,
    Audit,
    Full,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum FillModelArg {
    TopOfBook,
    L2Depth,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum PublicStreamModeArg {
    StrictEvent,
    BatchedPublicV1,
    BatchedPublicBarrierV1,
    PanelSparseV1,
    PanelSparseFastClockV1,
}

#[derive(Clone, Copy, Debug, ValueEnum)]
enum ArrivalModeArg {
    Timer,
    NextEvent,
}

impl From<ArrivalModeArg> for OrderArrivalMode {
    fn from(value: ArrivalModeArg) -> Self {
        match value {
            ArrivalModeArg::Timer => Self::Timer,
            ArrivalModeArg::NextEvent => Self::NextEvent,
        }
    }
}

impl From<ClockModeArg> for StreamClockMode {
    fn from(value: ClockModeArg) -> Self {
        match value {
            ClockModeArg::DeterministicStep => Self::DeterministicStep,
            ClockModeArg::AcceleratedAsync => Self::AcceleratedAsync,
        }
    }
}

impl From<LogModeArg> for StreamLogMode {
    fn from(value: LogModeArg) -> Self {
        match value {
            LogModeArg::Compact => Self::Compact,
            LogModeArg::Audit => Self::Audit,
            LogModeArg::Full => Self::Full,
        }
    }
}

impl From<FillModelArg> for TakerFillModel {
    fn from(value: FillModelArg) -> Self {
        match value {
            FillModelArg::TopOfBook => Self::TopOfBookTakerIocV1,
            FillModelArg::L2Depth => Self::L2TakerDepthV1,
        }
    }
}

impl From<PublicStreamModeArg> for SparsePublicStreamMode {
    fn from(value: PublicStreamModeArg) -> Self {
        match value {
            PublicStreamModeArg::StrictEvent => Self::StrictEvent,
            PublicStreamModeArg::BatchedPublicV1 => Self::BatchedPublicV1,
            PublicStreamModeArg::BatchedPublicBarrierV1 => Self::BatchedPublicBarrierV1,
            PublicStreamModeArg::PanelSparseV1 => Self::PanelSparseV1,
            PublicStreamModeArg::PanelSparseFastClockV1 => Self::PanelSparseFastClockV1,
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
            RunCommand::SparsePython(args) => {
                let summary = run_sparse_python(args)?;
                println!("{}", serde_json::to_string_pretty(&summary)?);
                Ok(())
            }
            RunCommand::Server(args) => {
                let summary = run_server(args)?;
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
            arrival_mode: args.arrival_mode.into(),
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

fn run_sparse_python(
    args: RunSparsePythonArgs,
) -> anyhow::Result<ccusdt_replay_runner::SparsePythonStreamSummary> {
    let public_stream_mode: SparsePublicStreamMode = args.public_stream_mode.into();
    let panel_mode = matches!(
        public_stream_mode,
        SparsePublicStreamMode::PanelSparseV1 | SparsePublicStreamMode::PanelSparseFastClockV1
    );
    let fast_clock_mode = matches!(
        public_stream_mode,
        SparsePublicStreamMode::PanelSparseFastClockV1
    );
    anyhow::ensure!(
        !fast_clock_mode || matches!(args.fill_model, FillModelArg::TopOfBook),
        "panel-sparse-fast-clock-v1 only supports --fill-model top-of-book"
    );
    let panel_cache_manifest = if panel_mode {
        Some(load_panel_cache_manifest(
            &args.repo_root,
            &args.symbol,
            &args.canonical_date,
        )?)
    } else {
        None
    };
    let mut panel_frames = if panel_mode {
        Some(load_panel_decision_frames(
            &args.python,
            &args.repo_root,
            &args.symbol,
            &args.canonical_date,
        )?)
    } else {
        None
    };
    let quote_frames = if fast_clock_mode {
        Some(
            load_replay(ReplaySource::Csv(canonical_quote_path(
                &args.repo_root,
                &args.symbol,
                &args.canonical_date,
            )))
            .with_context(|| {
                format!(
                    "load canonical quote frame index for {}",
                    args.canonical_date
                )
            })?,
        )
    } else {
        None
    };
    let trade_events = if fast_clock_mode {
        Some(
            load_canonical_trades(&args.repo_root, &args.symbol, &args.canonical_date)
                .with_context(|| {
                    format!(
                        "load canonical trades for fast clock {}",
                        args.canonical_date
                    )
                })?,
        )
    } else {
        None
    };
    if fast_clock_mode {
        assign_panel_fast_clock_observed_seq(
            panel_frames
                .as_mut()
                .context("panel_sparse_fast_clock_v1 missing decision frames")?,
            quote_frames
                .as_ref()
                .context("panel_sparse_fast_clock_v1 missing quote frames")?,
            trade_events
                .as_ref()
                .context("panel_sparse_fast_clock_v1 missing trade events")?,
        )?;
    }
    let mut strategy_args = vec!["--sparse-output".to_string()];
    strategy_args.extend(args.strategy_args);
    let options = SparsePythonStreamOptions {
        run_id: args
            .run_id
            .unwrap_or_else(|| default_run_id("sparse_python_runner")),
        run_root: args.run_root,
        source_label: if fast_clock_mode {
            format!(
                "panel_sparse_fast_clock_v1:{}:{}",
                args.symbol, args.canonical_date
            )
        } else {
            format!(
                "canonical_sparse_exchange_stream_v1:{}:{}",
                args.symbol, args.canonical_date
            )
        },
        exchange_config: ExchangeConfig {
            symbol: args.symbol.clone(),
            starting_cash: args.starting_cash,
            fee_bps: args.fee_bps,
            max_leverage: args.max_leverage,
        },
        max_events: args.max_events,
        latency_us: args.latency_us,
        arrival_mode: args.arrival_mode.into(),
        clock_mode: args.clock_mode.into(),
        wall_latency_speedup: args.wall_latency_speedup,
        bridge_timeout_ms: args.bridge_timeout_ms,
        failure_policy: args.failure_policy.into(),
        log_mode: args.log_mode.into(),
        fill_model: args.fill_model.into(),
        public_stream_mode,
        public_batch_size: args.public_batch_size,
        public_batch_max_span_us: args.public_batch_max_span_us,
        panel_frame_cache_manifest: panel_cache_manifest,
        compact_l2: args.compact_l2,
        python: args.python,
        strategy_script: args.strategy_script,
        strategy_args,
    };
    if fast_clock_mode {
        run_panel_sparse_fast_clock_python_stream_strategy(
            quote_frames.context("panel_sparse_fast_clock_v1 missing quote frames")?,
            panel_frames.context("panel_sparse_fast_clock_v1 missing decision frames")?,
            options,
        )
    } else if let Some(panel_frames) = panel_frames {
        let stream = stream_canonical_market(
            &args.repo_root,
            &args.symbol,
            &args.canonical_date,
            args.include_l2
                || matches!(args.fill_model, FillModelArg::L2Depth)
                || matches!(public_stream_mode, SparsePublicStreamMode::PanelSparseV1),
            args.l2_batch_size,
            args.l2_max_rows,
        )
        .with_context(|| format!("stream canonical market for {}", args.canonical_date))?;
        run_panel_sparse_python_stream_strategy(stream, panel_frames, options)
    } else {
        let stream = stream_canonical_market(
            &args.repo_root,
            &args.symbol,
            &args.canonical_date,
            args.include_l2 || matches!(args.fill_model, FillModelArg::L2Depth),
            args.l2_batch_size,
            args.l2_max_rows,
        )
        .with_context(|| format!("stream canonical market for {}", args.canonical_date))?;
        run_sparse_python_stream_strategy(stream, options)
    }
}

fn panel_cache_manifest_path(repo_root: &std::path::Path, symbol: &str, day: &str) -> PathBuf {
    repo_root
        .join("data/canonical_parquet/cex/bullish")
        .join(symbol)
        .join("decision_frame_v1")
        .join(format!("dt={day}"))
        .join("manifest.json")
}

fn load_panel_cache_manifest(
    repo_root: &std::path::Path,
    symbol: &str,
    day: &str,
) -> anyhow::Result<serde_json::Value> {
    let path = panel_cache_manifest_path(repo_root, symbol, day);
    let raw = std::fs::read_to_string(&path).with_context(|| format!("read {}", path.display()))?;
    let manifest = serde_json::from_str::<serde_json::Value>(&raw)
        .with_context(|| format!("parse {}", path.display()))?;
    anyhow::ensure!(
        manifest.get("schema_id").and_then(|v| v.as_str())
            == Some("decision_frame_parquet_cache_manifest_v1"),
        "invalid decision_frame cache manifest schema at {}",
        path.display()
    );
    anyhow::ensure!(
        manifest.get("dataset").and_then(|v| v.as_str()) == Some("decision_frame_v1"),
        "invalid decision_frame cache dataset at {}",
        path.display()
    );
    Ok(manifest)
}

fn load_panel_decision_frames(
    python: &std::path::Path,
    repo_root: &std::path::Path,
    symbol: &str,
    day: &str,
) -> anyhow::Result<std::collections::VecDeque<PanelDecisionFrame>> {
    let script =
        repo_root.join("systems/ccusdt_replay_exchange/diagnostics/decision_frame_cache.py");
    let mut child = ProcessCommand::new(python)
        .arg(&script)
        .arg("export-ndjson")
        .arg("--repo-root")
        .arg(repo_root)
        .arg("--symbol")
        .arg(symbol)
        .arg("--from-date")
        .arg(day)
        .arg("--to-date")
        .arg(day)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .with_context(|| format!("spawn panel frame exporter {}", script.display()))?;
    let stdout = child
        .stdout
        .take()
        .context("panel frame exporter stdout was not piped")?;
    let reader = BufReader::new(stdout);
    let mut frames = std::collections::VecDeque::new();
    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let frame = serde_json::from_str::<serde_json::Value>(&line)
            .context("parse panel_sparse decision_frame JSON")?;
        let local_ts_us = frame
            .get("local_ts_us")
            .and_then(|v| v.as_u64())
            .context("decision_frame missing local_ts_us")?;
        let observed_seq = frame
            .get("observed_seq")
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        let exchange_ts_us = frame
            .get("exchange_ts_us")
            .and_then(|v| v.as_u64())
            .unwrap_or(local_ts_us);
        let event_index = frame
            .get("event_index")
            .and_then(|v| v.as_u64())
            .unwrap_or((frames.len() + 1) as u64);
        frames.push_back(PanelDecisionFrame {
            frame,
            observed_seq,
            arrival_stream_seq: observed_seq,
            exchange_ts_us,
            local_ts_us,
            event_index,
        });
    }
    let status = child.wait().context("wait for panel frame exporter")?;
    anyhow::ensure!(
        status.success(),
        "panel frame exporter failed with status {status}"
    );
    anyhow::ensure!(
        !frames.is_empty(),
        "panel_sparse_v1 decision_frame cache exported zero frames"
    );
    Ok(frames)
}

fn assign_panel_fast_clock_observed_seq(
    panel_frames: &mut std::collections::VecDeque<PanelDecisionFrame>,
    quote_frames: &[MarketFrame],
    trade_events: &[TradeEvent],
) -> anyhow::Result<()> {
    anyhow::ensure!(!quote_frames.is_empty(), "quote frame index is empty");
    anyhow::ensure!(!panel_frames.is_empty(), "decision frame cache is empty");
    let mut quote_idx = 0usize;
    let mut trade_idx = 0usize;
    let mut panel_idx = 0usize;
    let mut stream_seq = 0u64;
    let mut current_local_ts_us: Option<u64> = None;
    let mut first_seq_at_current_ts = 0u64;
    while panel_idx < panel_frames.len() {
        let quote_key = quote_frames
            .get(quote_idx)
            .map(|quote| (quote.local_ts_us, 0u8));
        let trade_key = trade_events
            .get(trade_idx)
            .map(|trade| (trade.local_ts_us, 1u8));
        let panel_key = panel_frames
            .get(panel_idx)
            .map(|frame| (frame.local_ts_us, 2u8));
        let Some((choice, key)) = [
            (0usize, quote_key),
            (1usize, trade_key),
            (2usize, panel_key),
        ]
        .into_iter()
        .filter_map(|(choice, key)| key.map(|key| (choice, key)))
        .min_by_key(|(_, key)| *key) else {
            anyhow::bail!(
                "ran out of quote/trade/panel events before assigning panel observed_seq"
            );
        };
        if current_local_ts_us != Some(key.0) {
            current_local_ts_us = Some(key.0);
            first_seq_at_current_ts = stream_seq;
        }
        match choice {
            0 => quote_idx += 1,
            1 => trade_idx += 1,
            2 => {
                if let Some(frame) = panel_frames.get_mut(panel_idx) {
                    frame.observed_seq = stream_seq;
                    frame.arrival_stream_seq = first_seq_at_current_ts;
                    frame.frame["observed_seq"] = serde_json::json!(stream_seq);
                }
                panel_idx += 1;
            }
            _ => unreachable!("only three fast-clock sources"),
        }
        stream_seq += 1;
    }
    Ok(())
}

fn run_server(args: RunServerArgs) -> anyhow::Result<ccusdt_replay_runner::RunnerServerSummary> {
    let stream = stream_canonical_market(
        &args.repo_root,
        &args.symbol,
        &args.canonical_date,
        args.include_l2 || matches!(args.fill_model, FillModelArg::L2Depth),
        args.l2_batch_size,
        args.l2_max_rows,
    )
    .with_context(|| format!("stream canonical market for {}", args.canonical_date))?;
    run_runner_server(
        stream,
        RunnerServerOptions {
            run_id: args
                .run_id
                .unwrap_or_else(|| default_run_id("runner_server")),
            run_root: args.run_root,
            source_label: format!(
                "canonical_runner_server_v1:{}:{}",
                args.symbol, args.canonical_date
            ),
            exchange_config: ExchangeConfig {
                symbol: args.symbol,
                starting_cash: args.starting_cash,
                fee_bps: args.fee_bps,
                max_leverage: args.max_leverage,
            },
            max_events: args.max_events,
            latency_us: args.latency_us,
            arrival_mode: args.arrival_mode.into(),
            clock_mode: args.clock_mode.into(),
            wall_latency_speedup: args.wall_latency_speedup,
            log_mode: args.log_mode.into(),
            fill_model: args.fill_model.into(),
            public_addr: args.public_addr,
            private_addr: args.private_addr,
            order_addr: args.order_addr,
            state_addr: args.state_addr,
            startup_wait_ms: args.startup_wait_ms,
            event_sleep_us: args.event_sleep_us,
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
