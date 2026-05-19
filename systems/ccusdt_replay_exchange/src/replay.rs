use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

use crate::types::MarketFrame;

#[derive(Clone, Debug)]
pub enum ReplaySource {
    Csv(PathBuf),
    Synthetic { frames: usize },
}

pub fn load_replay(source: ReplaySource) -> Result<Vec<MarketFrame>> {
    match source {
        ReplaySource::Csv(path) => load_csv_replay(&path),
        ReplaySource::Synthetic { frames } => synthetic_replay(frames),
    }
}

fn load_csv_replay(path: &Path) -> Result<Vec<MarketFrame>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open replay csv: {}", path.display()))?;
    let headers = reader.headers()?.clone();

    let ts_idx = first_header(
        &headers,
        &["ts", "timestamp", "local_ts", "local_timestamp"],
    )
    .context("csv needs one timestamp column: ts/timestamp/local_ts/local_timestamp")?;
    let bid_idx = first_header(&headers, &["bid", "best_bid", "best_bid_price", "bestBid"])
        .context("csv needs one bid column: bid/best_bid/best_bid_price/bestBid")?;
    let ask_idx = first_header(&headers, &["ask", "best_ask", "best_ask_price", "bestAsk"])
        .context("csv needs one ask column: ask/best_ask/best_ask_price/bestAsk")?;

    let mut frames = Vec::new();
    for (row_idx, row) in reader.records().enumerate() {
        let row = row.with_context(|| format!("bad csv row {}", row_idx + 2))?;
        let ts = row.get(ts_idx).unwrap_or("").to_string();
        let bid = parse_f64(row.get(bid_idx), "bid", row_idx + 2)?;
        let ask = parse_f64(row.get(ask_idx), "ask", row_idx + 2)?;
        frames.push(MarketFrame::new(row_idx as u64, ts, bid, ask)?);
    }
    anyhow::ensure!(!frames.is_empty(), "replay csv had no frames");
    Ok(frames)
}

fn first_header(headers: &csv::StringRecord, names: &[&str]) -> Option<usize> {
    headers.iter().position(|header| {
        let normalized = header.trim();
        names
            .iter()
            .any(|name| normalized.eq_ignore_ascii_case(name))
    })
}

fn parse_f64(value: Option<&str>, name: &str, row: usize) -> Result<f64> {
    value
        .context("missing csv value")?
        .trim()
        .parse::<f64>()
        .with_context(|| format!("failed to parse {name} at csv row {row}"))
}

fn synthetic_replay(frames: usize) -> Result<Vec<MarketFrame>> {
    anyhow::ensure!(frames > 0, "synthetic replay needs at least one frame");
    let mut out = Vec::with_capacity(frames);
    for seq in 0..frames {
        let t = seq as f64;
        let trend = 0.00002 * t;
        let wave = (t / 23.0).sin() * 0.0015 + (t / 71.0).cos() * 0.0008;
        let mid = 1.0 + trend + wave;
        let spread = mid * 0.0002;
        let ts = format!("synthetic:{seq:06}");
        out.push(MarketFrame::new(
            seq as u64,
            ts,
            mid - spread * 0.5,
            mid + spread * 0.5,
        )?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synthetic_has_valid_quotes() {
        let frames = synthetic_replay(16).unwrap();
        assert_eq!(frames.len(), 16);
        assert!(frames.iter().all(|frame| frame.bid <= frame.ask));
        assert!(frames.iter().all(|frame| frame.mid > 0.0));
    }
}
