use std::path::PathBuf;

use anyhow::Result;
use chog_prices::{
    analysis::{
        BasicAnalysis, DatasetInventory, DexHourSummary, DexOverview, DexPoolSummary,
        DexQuoteSummary, PriceSummary, basic_analysis,
    },
    chog_v1::default_data_root_path,
};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "chog_analyze",
    about = "Run basic read-only analysis over local CHOG v1 Parquet data."
)]
struct Args {
    /// CHOG v1 data root.
    #[arg(long)]
    data_root: Option<PathBuf>,

    /// Number of top pools and hours to show.
    #[arg(long, default_value_t = 10)]
    top: usize,

    /// Print machine-readable JSON instead of a text report.
    #[arg(long)]
    json: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();
    let data_root = args.data_root.unwrap_or_else(default_data_root_path);
    let analysis = basic_analysis(&data_root, args.top)?;
    if args.json {
        println!("{}", serde_json::to_string_pretty(&analysis)?);
    } else {
        print_text_report(&analysis);
    }
    Ok(())
}

fn print_text_report(analysis: &BasicAnalysis) {
    println!("data inventory");
    for row in analysis.inventory.iter().filter(|row| row.files > 0) {
        print_inventory(row);
    }

    println!();
    println!("dex overview");
    print_dex_overview(&analysis.dex.overview);

    if !analysis.dex.by_quote.is_empty() {
        println!();
        println!("dex by quote");
        for row in &analysis.dex.by_quote {
            print_quote(row);
        }
    }

    if !analysis.dex.top_pools.is_empty() {
        println!();
        println!("top pools by chog volume");
        for row in &analysis.dex.top_pools {
            print_pool(row);
        }
    }

    if !analysis.dex.top_hours.is_empty() {
        println!();
        println!("top hours by chog volume");
        for row in &analysis.dex.top_hours {
            print_hour(row);
        }
    }

    if let Some(prices) = &analysis.prices {
        println!();
        println!("price summary");
        print_price_summary(prices);
    }
}

fn print_inventory(row: &DatasetInventory) {
    let block_window = match (row.min_block, row.max_block) {
        (Some(min), Some(max)) => format!(" blocks={min}..{max}"),
        _ => String::new(),
    };
    let utc_window = match (&row.min_utc, &row.max_utc) {
        (Some(min), Some(max)) => format!(" utc={min}..{max}"),
        _ => String::new(),
    };
    println!(
        "{}.{} files={} rows={}{}{}",
        row.layer, row.dataset, row.files, row.rows, block_window, utc_window
    );
}

fn print_dex_overview(row: &DexOverview) {
    let block_window = match (row.first_block, row.last_block) {
        (Some(first), Some(last)) => format!("{first}..{last}"),
        _ => "n/a".to_string(),
    };
    let utc_window = match (&row.first_utc, &row.last_utc) {
        (Some(first), Some(last)) => format!("{first}..{last}"),
        _ => "n/a".to_string(),
    };
    println!(
        "swaps={} txs={} pools={} blocks={} utc={}",
        row.swaps, row.txs, row.pools, block_window, utc_window
    );
    println!(
        "buy_swaps={} sell_swaps={} buy_chog={} sell_chog={} net_buy_chog={} chog_volume={} quote_volume={}",
        row.buy_swaps,
        row.sell_swaps,
        fmt_amount(row.buy_chog),
        fmt_amount(row.sell_chog),
        fmt_amount(row.net_buy_chog),
        fmt_amount(row.chog_volume),
        fmt_amount(row.quote_volume)
    );
}

fn print_quote(row: &DexQuoteSummary) {
    println!(
        "{} swaps={} txs={} pools={} chog_volume={} quote_volume={} avg_price={} net_buy_chog={}",
        non_empty(&row.quote_symbol),
        row.swaps,
        row.txs,
        row.pools,
        fmt_amount(row.chog_volume),
        fmt_amount(row.quote_volume),
        fmt_amount(row.avg_price_quote_per_chog),
        fmt_amount(row.net_buy_chog)
    );
}

fn print_pool(row: &DexPoolSummary) {
    println!(
        "{} {} {} swaps={} txs={} chog_volume={} quote_volume={} avg_price={} net_buy_chog={} pool={}",
        non_empty(&row.dex_id),
        non_empty(&row.family),
        non_empty(&row.quote_symbol),
        row.swaps,
        row.txs,
        fmt_amount(row.chog_volume),
        fmt_amount(row.quote_volume),
        fmt_amount(row.avg_price_quote_per_chog),
        fmt_amount(row.net_buy_chog),
        row.pool_address
    );
}

fn print_hour(row: &DexHourSummary) {
    println!(
        "{} swaps={} pool_txs={} chog_volume={} quote_volume={} net_buy_chog={}",
        row.hour_utc,
        row.swaps,
        row.pool_txs,
        fmt_amount(row.chog_volume),
        fmt_amount(row.quote_volume),
        fmt_amount(row.net_buy_chog)
    );
}

fn print_price_summary(row: &PriceSummary) {
    println!(
        "points={} hours={}..{} latest={} price_usd={} min={} max={}",
        row.points,
        row.min_hour_utc.as_deref().unwrap_or("n/a"),
        row.max_hour_utc.as_deref().unwrap_or("n/a"),
        row.latest_hour_utc.as_deref().unwrap_or("n/a"),
        row.latest_price_usd
            .map(fmt_amount)
            .unwrap_or_else(|| "n/a".to_string()),
        row.min_price_usd
            .map(fmt_amount)
            .unwrap_or_else(|| "n/a".to_string()),
        row.max_price_usd
            .map(fmt_amount)
            .unwrap_or_else(|| "n/a".to_string())
    );
}

fn non_empty(value: &str) -> &str {
    if value.is_empty() { "unknown" } else { value }
}

fn fmt_amount(value: f64) -> String {
    if value == 0.0 {
        return "0".to_string();
    }
    let abs = value.abs();
    let raw = if abs >= 1000.0 {
        format!("{value:.2}")
    } else if abs >= 1.0 {
        format!("{value:.6}")
    } else {
        format!("{value:.10}")
    };
    raw.trim_end_matches('0').trim_end_matches('.').to_string()
}
