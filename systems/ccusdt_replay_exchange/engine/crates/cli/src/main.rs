use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::Context;
use ccusdt_exchange_sim::PaperExchange;
use ccusdt_replay_core::{
    ExchangeConfig, ReplaySource, build_canonical_dataset, canonical_quote_path, load_replay,
    scan_catalog, validate_canonical, write_catalog,
};
use ccusdt_replay_runner::{RunnerOptions, ToyStrategyConfig, default_run_id, run_toy_strategy};
use clap::{Parser, Subcommand};

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
