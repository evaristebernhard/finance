use std::cell::Cell;
use std::collections::BTreeMap;

use anyhow::{Context, Result, anyhow, bail};
use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Debug)]
pub struct RpcUrlPool {
    urls: Vec<String>,
    next: Cell<usize>,
}

impl RpcUrlPool {
    pub fn from_values(values: &[String], default_url: &str) -> Result<Self> {
        let mut urls = Vec::new();
        for value in values {
            for url in value.split(',') {
                let url = url.trim();
                if !url.is_empty() && !urls.iter().any(|existing| existing == url) {
                    urls.push(url.to_string());
                }
            }
        }
        if urls.is_empty() {
            urls.push(default_url.to_string());
        }
        Ok(Self {
            urls,
            next: Cell::new(0),
        })
    }

    pub fn len(&self) -> usize {
        self.urls.len()
    }

    pub fn is_empty(&self) -> bool {
        self.urls.is_empty()
    }

    pub fn next_url(&self) -> &str {
        let index = self.next.get();
        self.next.set((index + 1) % self.urls.len());
        &self.urls[index]
    }
}

#[derive(Debug, Deserialize)]
struct RpcResponse<T> {
    result: Option<T>,
    error: Option<RpcError>,
}

#[derive(Debug, Deserialize)]
struct RpcError {
    code: i64,
    message: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RpcBlock {
    pub number: Option<String>,
    pub hash: Option<String>,
    pub parent_hash: Option<String>,
    pub timestamp: String,
    pub base_fee_per_gas: Option<String>,
    pub gas_used: String,
    pub gas_limit: String,
    pub miner: Option<String>,
    pub extra_data: Option<String>,
    #[serde(default)]
    pub transactions: Vec<Value>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RpcReceipt {
    pub transaction_hash: String,
    pub transaction_index: Option<String>,
    pub block_hash: Option<String>,
    pub block_number: Option<String>,
    pub from: Option<String>,
    pub to: Option<String>,
    pub cumulative_gas_used: Option<String>,
    pub gas_used: Option<String>,
    pub contract_address: Option<String>,
    pub logs: Option<Vec<Value>>,
    pub status: Option<String>,
    pub effective_gas_price: Option<String>,
    #[serde(rename = "type")]
    pub tx_type: Option<String>,
}

#[derive(Debug, Clone)]
pub enum RpcBatchItem {
    Result(Value),
    Error(String),
}

pub fn parse_hex_u64(value: &str) -> Result<u64> {
    u64::from_str_radix(value.trim_start_matches("0x"), 16)
        .with_context(|| format!("invalid hex u64: {value}"))
}

pub fn to_hex(value: u64) -> String {
    format!("0x{value:x}")
}

pub fn rpc_call<T: for<'de> Deserialize<'de>>(
    client: &Client,
    rpc_url: &str,
    method: &str,
    params: Value,
) -> Result<T> {
    let body = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    });
    let response = client
        .post(rpc_url)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .with_context(|| format!("failed RPC request {method}"))?;
    let status = response.status();
    let text = response.text().context("failed to read RPC response")?;
    if !status.is_success() {
        bail!("RPC request {method} failed with status {status}: {text}");
    }

    let response: RpcResponse<T> = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC response: {text}"))?;
    if let Some(error) = response.error {
        bail!("RPC error {} from {method}: {}", error.code, error.message);
    }
    response
        .result
        .ok_or_else(|| anyhow!("RPC response from {method} did not include result"))
}

pub fn rpc_call_from_pool<T: for<'de> Deserialize<'de>>(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    params: Value,
) -> Result<T> {
    let mut last_error = None;
    for _ in 0..rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_call(client, rpc_url, method, params.clone()) {
            Ok(value) => return Ok(value),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("RPC pool has no URLs")))
}

pub fn rpc_batch_items(
    client: &Client,
    rpc_url: &str,
    method: &str,
    params_list: &[Value],
) -> Result<Vec<RpcBatchItem>> {
    if params_list.is_empty() {
        return Ok(Vec::new());
    }
    let body = params_list
        .iter()
        .enumerate()
        .map(|(index, params)| {
            json!({
                "jsonrpc": "2.0",
                "id": index as u64,
                "method": method,
                "params": params,
            })
        })
        .collect::<Vec<_>>();

    let response = client
        .post(rpc_url)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .with_context(|| format!("failed JSON-RPC batch request {method}"))?;
    let status = response.status();
    let text = response
        .text()
        .context("failed to read RPC batch response")?;
    if !status.is_success() {
        bail!("RPC batch request {method} failed with status {status}: {text}");
    }

    let mut value: Value = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse RPC batch response: {text}"))?;
    if value.is_object() {
        value = Value::Array(vec![value]);
    }
    let responses = value
        .as_array()
        .ok_or_else(|| anyhow!("RPC batch response from {method} was not an array"))?;
    let mut by_id = BTreeMap::<u64, RpcBatchItem>::new();
    for response in responses {
        let id = response
            .get("id")
            .and_then(Value::as_u64)
            .ok_or_else(|| anyhow!("RPC batch response from {method} did not include id"))?;
        if let Some(error) = response.get("error") {
            by_id.insert(id, RpcBatchItem::Error(error.to_string()));
        } else {
            by_id.insert(
                id,
                RpcBatchItem::Result(response.get("result").cloned().unwrap_or(Value::Null)),
            );
        }
    }

    let mut items = Vec::with_capacity(params_list.len());
    for index in 0..params_list.len() {
        items.push(
            by_id
                .remove(&(index as u64))
                .unwrap_or_else(|| RpcBatchItem::Error("missing batch response".to_string())),
        );
    }
    Ok(items)
}

pub fn rpc_batch_results_from_pool(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    method: &str,
    params_list: &[Value],
) -> Result<Vec<Value>> {
    let mut last_error = None;
    for _ in 0..rpc_urls.len() {
        let rpc_url = rpc_urls.next_url();
        match rpc_batch_items(client, rpc_url, method, params_list) {
            Ok(items) => {
                let mut values = Vec::with_capacity(items.len());
                for item in items {
                    match item {
                        RpcBatchItem::Result(value) => values.push(value),
                        RpcBatchItem::Error(error) => {
                            bail!("RPC batch item from {method} failed: {error}")
                        }
                    }
                }
                return Ok(values);
            }
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("RPC pool has no URLs")))
}
