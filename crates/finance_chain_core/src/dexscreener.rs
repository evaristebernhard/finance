use std::collections::BTreeMap;

use anyhow::{Context, Result};
use reqwest::blocking::Client;
use serde_json::Value;

#[derive(Debug, Clone, PartialEq)]
pub struct PoolCandidate {
    pub fetched_at_utc: String,
    pub rank_liquidity: u64,
    pub chain_id: String,
    pub dex_id: String,
    pub labels: String,
    pub family_hint: String,
    pub pair_address: String,
    pub base_address: String,
    pub base_symbol: String,
    pub quote_address: String,
    pub quote_symbol: String,
    pub price_usd: String,
    pub liquidity_usd: f64,
    pub volume_m5_usd: f64,
    pub volume_h1_usd: f64,
    pub volume_h6_usd: f64,
    pub volume_h24_usd: f64,
    pub m5_buys: u64,
    pub m5_sells: u64,
    pub h1_buys: u64,
    pub h1_sells: u64,
    pub h6_buys: u64,
    pub h6_sells: u64,
    pub h24_buys: u64,
    pub h24_sells: u64,
    pub pair_created_at: String,
    pub url: String,
}

impl PoolCandidate {
    pub fn from_known(
        rank_liquidity: u64,
        dex_id: &str,
        labels: &str,
        pair_address: &str,
        base_address: &str,
        base_symbol: &str,
        quote_address: &str,
        quote_symbol: &str,
    ) -> Self {
        Self {
            fetched_at_utc: String::new(),
            rank_liquidity,
            chain_id: "monad".to_string(),
            dex_id: dex_id.to_string(),
            labels: labels.to_string(),
            family_hint: family_hint(labels).to_string(),
            pair_address: pair_address.to_string(),
            base_address: base_address.to_string(),
            base_symbol: base_symbol.to_string(),
            quote_address: quote_address.to_string(),
            quote_symbol: quote_symbol.to_string(),
            price_usd: String::new(),
            liquidity_usd: 0.0,
            volume_m5_usd: 0.0,
            volume_h1_usd: 0.0,
            volume_h6_usd: 0.0,
            volume_h24_usd: 0.0,
            m5_buys: 0,
            m5_sells: 0,
            h1_buys: 0,
            h1_sells: 0,
            h6_buys: 0,
            h6_sells: 0,
            h24_buys: 0,
            h24_sells: 0,
            pair_created_at: String::new(),
            url: String::new(),
        }
    }
}

pub fn discover_pair_pools(
    client: &Client,
    chain: &str,
    token_a: &str,
    token_b: &str,
    fetched_at_utc: &str,
) -> Result<Vec<PoolCandidate>> {
    let mut by_address = BTreeMap::<String, PoolCandidate>::new();
    for token in [token_a, token_b] {
        let url = format!("https://api.dexscreener.com/token-pairs/v1/{chain}/{token}");
        let pairs: Value = client
            .get(&url)
            .header("accept", "application/json")
            .send()
            .with_context(|| format!("failed DexScreener request {url}"))?
            .error_for_status()
            .with_context(|| format!("DexScreener returned non-success for {url}"))?
            .json()
            .with_context(|| format!("failed to parse DexScreener JSON from {url}"))?;
        let Some(pairs) = pairs.as_array() else {
            continue;
        };
        for pair in pairs {
            let candidate = pair_to_candidate(pair, fetched_at_utc);
            if contains_pair(&candidate, token_a, token_b) {
                by_address.insert(candidate.pair_address.to_ascii_lowercase(), candidate);
            }
        }
    }

    let mut rows = by_address.into_values().collect::<Vec<_>>();
    rows.sort_by(|a, b| {
        b.liquidity_usd
            .total_cmp(&a.liquidity_usd)
            .then_with(|| b.volume_h24_usd.total_cmp(&a.volume_h24_usd))
            .then_with(|| a.pair_address.cmp(&b.pair_address))
    });
    for (index, row) in rows.iter_mut().enumerate() {
        row.rank_liquidity = (index + 1) as u64;
    }
    Ok(rows)
}

fn pair_to_candidate(pair: &Value, fetched_at_utc: &str) -> PoolCandidate {
    let base = pair.get("baseToken").unwrap_or(&Value::Null);
    let quote = pair.get("quoteToken").unwrap_or(&Value::Null);
    let liquidity = pair.get("liquidity").unwrap_or(&Value::Null);
    let volume = pair.get("volume").unwrap_or(&Value::Null);
    let txns = pair.get("txns").unwrap_or(&Value::Null);
    let m5 = txns.get("m5").unwrap_or(&Value::Null);
    let h1 = txns.get("h1").unwrap_or(&Value::Null);
    let h6 = txns.get("h6").unwrap_or(&Value::Null);
    let h24 = txns.get("h24").unwrap_or(&Value::Null);
    let labels = pair
        .get("labels")
        .and_then(Value::as_array)
        .map(|labels| {
            labels
                .iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join("|")
        })
        .unwrap_or_default();
    PoolCandidate {
        fetched_at_utc: fetched_at_utc.to_string(),
        rank_liquidity: 0,
        chain_id: string_value(pair.get("chainId")),
        dex_id: string_value(pair.get("dexId")),
        labels: labels.clone(),
        family_hint: family_hint(&labels).to_string(),
        pair_address: string_value(pair.get("pairAddress")),
        base_address: string_value(base.get("address")),
        base_symbol: string_value(base.get("symbol")),
        quote_address: string_value(quote.get("address")),
        quote_symbol: string_value(quote.get("symbol")),
        price_usd: string_value(pair.get("priceUsd")),
        liquidity_usd: f64_value(liquidity.get("usd")),
        volume_m5_usd: f64_value(volume.get("m5")),
        volume_h1_usd: f64_value(volume.get("h1")),
        volume_h6_usd: f64_value(volume.get("h6")),
        volume_h24_usd: f64_value(volume.get("h24")),
        m5_buys: u64_value(m5.get("buys")),
        m5_sells: u64_value(m5.get("sells")),
        h1_buys: u64_value(h1.get("buys")),
        h1_sells: u64_value(h1.get("sells")),
        h6_buys: u64_value(h6.get("buys")),
        h6_sells: u64_value(h6.get("sells")),
        h24_buys: u64_value(h24.get("buys")),
        h24_sells: u64_value(h24.get("sells")),
        pair_created_at: string_value(pair.get("pairCreatedAt")),
        url: string_value(pair.get("url")),
    }
}

fn contains_pair(row: &PoolCandidate, token_a: &str, token_b: &str) -> bool {
    let addresses = [
        row.base_address.to_ascii_lowercase(),
        row.quote_address.to_ascii_lowercase(),
    ];
    addresses.contains(&token_a.to_ascii_lowercase())
        && addresses.contains(&token_b.to_ascii_lowercase())
}

fn family_hint(labels: &str) -> &'static str {
    let labels = labels.to_ascii_lowercase();
    if labels.split('|').any(|label| label == "v3") {
        "v3"
    } else if labels
        .split('|')
        .any(|label| matches!(label, "v2" | "v2.2"))
    {
        "v2"
    } else {
        "unknown"
    }
}

fn string_value(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(value)) => value.to_string(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(value)) => value.to_string(),
        _ => String::new(),
    }
}

fn f64_value(value: Option<&Value>) -> f64 {
    match value {
        Some(Value::Number(value)) => value.as_f64().unwrap_or(0.0),
        Some(Value::String(value)) => value.parse::<f64>().unwrap_or(0.0),
        _ => 0.0,
    }
}

fn u64_value(value: Option<&Value>) -> u64 {
    match value {
        Some(Value::Number(value)) => value.as_u64().unwrap_or(0),
        Some(Value::String(value)) => value.parse::<u64>().unwrap_or(0),
        _ => 0,
    }
}
