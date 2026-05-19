use std::net::SocketAddr;
use std::path::PathBuf;

use anyhow::Context;
use ccusdt_replay_exchange::api;
use ccusdt_replay_exchange::{ExchangeConfig, PaperExchange, ReplaySource, load_replay};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(version, about = "Standalone local CCUSDT paper exchange MVP")]
struct Args {
    #[arg(long, default_value = "127.0.0.1:8797")]
    addr: SocketAddr,

    #[arg(long, default_value = "CCUSDT")]
    symbol: String,

    #[arg(long)]
    csv: Option<PathBuf>,

    #[arg(long, default_value_t = 10_000.0)]
    starting_cash: f64,

    #[arg(long, default_value_t = 0.0)]
    fee_bps: f64,

    #[arg(long, default_value_t = 3.0)]
    max_leverage: f64,

    #[arg(long, default_value_t = 10_000)]
    synthetic_frames: usize,
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
    let source = match args.csv {
        Some(path) => ReplaySource::Csv(path),
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
