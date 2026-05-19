use std::{
    collections::{BTreeMap, BTreeSet, HashMap},
    net::SocketAddr,
    path::{Path, PathBuf},
    sync::Arc,
};

use anyhow::{Context, Result};
use axum::{
    Json, Router,
    extract::{Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
};
use chrono::{DateTime, Utc};
use clap::Parser;
use csv::StringRecord;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use tower_http::{cors::CorsLayer, trace::TraceLayer};

const DEFAULT_BONK_RUN_TAG: &str = "20260514_bonk_v10_stage1_pilot";
const DEFAULT_CC_RUN_TAG: &str = "20260517_ccusdt_fixed_factors_v3";
const DEFAULT_LIMIT: usize = 1200;
const MAX_LIMIT: usize = 8000;

#[derive(Parser, Debug)]
struct Args {
    #[arg(long, default_value = ".")]
    data_root: PathBuf,
    #[arg(long, default_value = DEFAULT_BONK_RUN_TAG)]
    run_tag: String,
    #[arg(long, default_value = DEFAULT_CC_RUN_TAG)]
    cc_run_tag: String,
    #[arg(long, default_value = "127.0.0.1:8787")]
    addr: SocketAddr,
}

#[derive(Clone)]
struct AppState {
    root: Arc<PathBuf>,
    markets: Arc<BTreeMap<String, MarketSpec>>,
}

#[derive(Clone)]
struct MarketSpec {
    id: &'static str,
    label: &'static str,
    replay_mode: ReplayMode,
    run_tag: String,
    data_root: &'static str,
    replay_dataset: Option<&'static str>,
    factor_dataset: &'static str,
    price_book_kind: &'static str,
    factor_kind: &'static str,
    replay_caveat: &'static str,
    quality_prefix: &'static str,
    factor_ranking_prefix: &'static str,
    default_symbol: &'static str,
    default_date: &'static str,
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum ReplayMode {
    BookStatePlusFactors,
    FactorPanelOnly,
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn not_found(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
            message: message.into(),
        }
    }

    fn internal(error: anyhow::Error) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: format!("{error:#}"),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({ "error": self.message }))).into_response()
    }
}

impl From<anyhow::Error> for ApiError {
    fn from(error: anyhow::Error) -> Self {
        Self::internal(error)
    }
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    markets: Vec<MarketInfo>,
}

#[derive(Serialize)]
struct MarketInfo {
    id: String,
    label: String,
    run_tag: String,
    replay_mode: ReplayMode,
    default_symbol: String,
    default_date: String,
}

#[derive(Serialize)]
struct ManifestResponse {
    market: String,
    market_label: String,
    run_tag: String,
    replay_mode: ReplayMode,
    markets: Vec<MarketInfo>,
    symbols: Vec<String>,
    dates: Vec<String>,
    replay_files: Vec<Value>,
    quality_daily: Vec<Value>,
    artifacts: Vec<String>,
}

#[derive(Deserialize)]
struct ReplayQuery {
    market: Option<String>,
    symbol: Option<String>,
    date: Option<String>,
    offset: Option<usize>,
    limit: Option<usize>,
    stride: Option<usize>,
}

#[derive(Serialize)]
struct ReplayResponse {
    run_tag: String,
    symbol: String,
    date: String,
    offset: usize,
    limit: usize,
    stride: usize,
    rows_returned: usize,
    rows: Vec<ReplayRow>,
    source_parts: Vec<String>,
    data_sources: ReplayDataSources,
}

#[derive(Serialize)]
struct ReplayDataSources {
    price_book: String,
    factors: String,
    join_key: &'static str,
    caveat: String,
    price_book_kind: &'static str,
    factor_kind: &'static str,
}

#[derive(Serialize)]
struct ReplayRow {
    event_index: u64,
    timestamp: i64,
    local_timestamp: i64,
    timestamp_utc: String,
    best_bid_price: f64,
    best_bid_amount: f64,
    best_ask_price: f64,
    best_ask_amount: f64,
    mid_price: f64,
    spread_bps: f64,
    microprice: f64,
    bid_levels: Vec<BookLevel>,
    ask_levels: Vec<BookLevel>,
    factors: Map<String, Value>,
}

#[derive(Serialize)]
struct BookLevel {
    price: f64,
    amount: f64,
}

#[derive(Deserialize)]
struct SummaryQuery {
    market: Option<String>,
    symbol: Option<String>,
    date: Option<String>,
    limit: Option<usize>,
}

#[derive(Serialize)]
struct SummaryResponse {
    run_tag: String,
    symbol: String,
    date: String,
    quality_hourly: Vec<Value>,
    state_hourly: Vec<Value>,
    path_hourly: Vec<Value>,
    path_summary: Vec<Value>,
    factor_ranking: Vec<Value>,
    blockers: Vec<Value>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "market_replay_backend=info,tower_http=info".into()),
        )
        .init();

    let state = AppState {
        root: Arc::new(args.data_root.canonicalize().unwrap_or(args.data_root)),
        markets: Arc::new(build_markets(args.run_tag, args.cc_run_tag)),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/api/manifest", get(manifest))
        .route("/api/replay", get(replay))
        .route("/api/summary", get(summary))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(args.addr).await?;
    tracing::info!("replay API listening on http://{}", args.addr);
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        markets: market_infos(&state),
    })
}

#[derive(Deserialize)]
struct MarketQuery {
    market: Option<String>,
}

async fn manifest(
    State(state): State<AppState>,
    Query(query): Query<MarketQuery>,
) -> Result<Json<ManifestResponse>, ApiError> {
    let market = market_spec(&state, query.market.as_deref())?;
    let quality_path = dated_file(&state, market, market.quality_prefix, "csv");

    let quality_daily = read_csv_json(&quality_path, None)
        .with_context(|| format!("reading {}", quality_path.display()))?;
    let replay_files = match market.replay_mode {
        ReplayMode::BookStatePlusFactors => {
            let manifest_path = dated_file(&state, market, "bonk_v10_replay_state_manifest", "csv");
            read_csv_json(&manifest_path, None)
                .with_context(|| format!("reading {}", manifest_path.display()))?
        }
        ReplayMode::FactorPanelOnly => quality_daily.clone(),
    };

    let mut symbols = BTreeSet::new();
    let mut dates = BTreeSet::new();
    for row in replay_files.iter().chain(quality_daily.iter()) {
        if let Some(symbol) = row.get("symbol").and_then(Value::as_str) {
            symbols.insert(symbol.to_string());
        }
        if let Some(date) = row.get("date").and_then(Value::as_str) {
            dates.insert(date.to_string());
        }
    }

    Ok(Json(ManifestResponse {
        market: market.id.to_string(),
        market_label: market.label.to_string(),
        run_tag: market.run_tag.clone(),
        replay_mode: market.replay_mode,
        markets: market_infos(&state),
        symbols: symbols.into_iter().collect(),
        dates: dates.into_iter().collect(),
        replay_files,
        quality_daily,
        artifacts: manifest_artifacts(&state, market, &quality_path),
    }))
}

async fn replay(
    State(state): State<AppState>,
    Query(query): Query<ReplayQuery>,
) -> Result<Json<ReplayResponse>, ApiError> {
    let market = market_spec(&state, query.market.as_deref())?;
    let symbol = clean_query_value(
        query.symbol.as_deref().unwrap_or(market.default_symbol),
        "symbol",
    )?;
    let date = clean_query_value(query.date.as_deref().unwrap_or(market.default_date), "date")?;
    let offset = query.offset.unwrap_or(0);
    let limit = query.limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let stride = query.stride.unwrap_or(1).max(1);
    let factor_panel_dir = factor_panel_dir(&state, market, &symbol, &date);
    let (rows, parts, price_book, price_book_kind, factor_kind, caveat) = match market.replay_mode {
        ReplayMode::BookStatePlusFactors => {
            let replay_state_dir = replay_state_dir(&state, market, &symbol, &date)
                .ok_or_else(|| ApiError::not_found("market has no replay state dataset"))?;
            replay_from_book_state(
                &replay_state_dir,
                &factor_panel_dir,
                offset,
                limit,
                stride,
                &state,
                market,
            )?
        }
        ReplayMode::FactorPanelOnly => {
            replay_from_factor_panel(&factor_panel_dir, offset, limit, stride, &state, market)?
        }
    };

    Ok(Json(ReplayResponse {
        run_tag: market.run_tag.clone(),
        symbol,
        date,
        offset,
        limit,
        stride,
        rows_returned: rows.len(),
        rows,
        source_parts: parts
            .iter()
            .map(|path| relative_to_root(path, &state.root))
            .collect(),
        data_sources: ReplayDataSources {
            price_book,
            factors: relative_to_root(&factor_panel_dir, &state.root),
            join_key: "timestamp",
            caveat,
            price_book_kind,
            factor_kind,
        },
    }))
}

async fn summary(
    State(state): State<AppState>,
    Query(query): Query<SummaryQuery>,
) -> Result<Json<SummaryResponse>, ApiError> {
    let market = market_spec(&state, query.market.as_deref())?;
    let symbol = clean_query_value(
        query.symbol.as_deref().unwrap_or(market.default_symbol),
        "symbol",
    )?;
    let date = clean_query_value(query.date.as_deref().unwrap_or(market.default_date), "date")?;
    let limit = query.limit.unwrap_or(80).clamp(1, 250);
    let filters = HashMap::from([
        ("symbol".to_string(), symbol.clone()),
        ("date".to_string(), date.clone()),
    ]);
    let symbol_filter = HashMap::from([("symbol".to_string(), symbol.clone())]);

    let (quality_hourly, state_hourly, path_hourly, path_summary, blockers) =
        match market.replay_mode {
            ReplayMode::BookStatePlusFactors => (
                read_csv_json_filtered_optional(
                    &dated_file(
                        &state,
                        market,
                        "bonk_v10_dynamic_orderbook_analysis_quality_hourly",
                        "csv",
                    ),
                    &filters,
                    Some(limit),
                )?,
                read_csv_json_filtered_optional(
                    &dated_file(
                        &state,
                        market,
                        "bonk_v10_dynamic_orderbook_analysis_state_hourly",
                        "csv",
                    ),
                    &filters,
                    Some(limit),
                )?,
                read_csv_json_filtered_optional(
                    &dated_file(
                        &state,
                        market,
                        "bonk_v10_dynamic_orderbook_analysis_path_hourly",
                        "csv",
                    ),
                    &filters,
                    Some(limit),
                )?,
                read_csv_json_filtered_optional(
                    &dated_file(
                        &state,
                        market,
                        "bonk_v10_dynamic_orderbook_analysis_path_summary",
                        "csv",
                    ),
                    &symbol_filter,
                    Some(limit),
                )?,
                read_csv_json_optional(
                    &dated_file(
                        &state,
                        market,
                        "bonk_v10_dynamic_orderbook_analysis_blockers",
                        "csv",
                    ),
                    Some(limit),
                )?,
            ),
            ReplayMode::FactorPanelOnly => (
                read_csv_json_filtered_optional(
                    &dated_file(&state, market, market.quality_prefix, "csv"),
                    &filters,
                    Some(limit),
                )?,
                Vec::new(),
                Vec::new(),
                read_csv_json_filtered_optional(
                    &dated_file(
                        &state,
                        market,
                        "ccusdt_v1_fixed_event_factors_stability",
                        "csv",
                    ),
                    &symbol_filter,
                    Some(limit),
                )?,
                Vec::new(),
            ),
        };
    let factor_ranking = read_csv_json_filtered_optional(
        &dated_file(&state, market, market.factor_ranking_prefix, "csv"),
        &symbol_filter,
        Some(limit),
    )?;

    Ok(Json(SummaryResponse {
        run_tag: market.run_tag.clone(),
        symbol,
        date,
        quality_hourly,
        state_hourly,
        path_hourly,
        path_summary,
        factor_ranking,
        blockers,
    }))
}

fn replay_from_book_state(
    replay_state_dir: &Path,
    factor_panel_dir: &Path,
    offset: usize,
    limit: usize,
    stride: usize,
    state: &AppState,
    market: &MarketSpec,
) -> Result<
    (
        Vec<ReplayRow>,
        Vec<PathBuf>,
        String,
        &'static str,
        &'static str,
        String,
    ),
    ApiError,
> {
    if !replay_state_dir.exists() {
        return Err(ApiError::not_found(format!(
            "missing replay state directory: {}",
            replay_state_dir.display()
        )));
    }

    let parts = csv_parts(replay_state_dir)?;
    let mut rows = Vec::with_capacity(limit);
    let mut timestamps = BTreeSet::new();
    let mut seen = 0usize;
    let mut sampled = 0usize;
    let mut ordinal = 0u64;

    for part in &parts {
        let mut reader = csv::Reader::from_path(part)
            .with_context(|| format!("opening replay part {}", part.display()))?;
        let headers = reader
            .headers()
            .map_err(|error| ApiError::internal(error.into()))?
            .clone();
        let header_index = header_index(&headers);
        for record in reader.records() {
            let record = record.map_err(|error| ApiError::internal(error.into()))?;
            if sampled % stride != 0 {
                sampled += 1;
                continue;
            }
            sampled += 1;
            if seen < offset {
                seen += 1;
                continue;
            }
            if rows.len() >= limit {
                break;
            }
            ordinal += 1;
            let row = parse_replay_state_row(&header_index, &record, ordinal)?;
            timestamps.insert(row.timestamp);
            rows.push(row);
            seen += 1;
        }
        if rows.len() >= limit {
            break;
        }
    }

    if factor_panel_dir.exists() && !timestamps.is_empty() {
        let factors = read_factor_lookup(factor_panel_dir, &timestamps)?;
        for row in &mut rows {
            if let Some((event_index, factor_map)) = factors.get(&row.timestamp) {
                row.event_index = *event_index;
                row.factors.extend(factor_map.clone());
                add_source_diagnostics(row, market.price_book_kind, market.factor_kind);
            }
        }
    }

    Ok((
        rows,
        parts,
        relative_to_root(replay_state_dir, &state.root),
        market.price_book_kind,
        market.factor_kind,
        market.replay_caveat.to_string(),
    ))
}

fn replay_from_factor_panel(
    panel_dir: &Path,
    offset: usize,
    limit: usize,
    stride: usize,
    state: &AppState,
    market: &MarketSpec,
) -> Result<
    (
        Vec<ReplayRow>,
        Vec<PathBuf>,
        String,
        &'static str,
        &'static str,
        String,
    ),
    ApiError,
> {
    if !panel_dir.exists() {
        return Err(ApiError::not_found(format!(
            "missing factor panel directory: {}",
            panel_dir.display()
        )));
    }
    let parts = csv_parts(panel_dir)?;
    let mut rows = Vec::with_capacity(limit);
    let mut seen = 0usize;
    let mut sampled = 0usize;

    for part in &parts {
        let mut reader = csv::Reader::from_path(part)
            .with_context(|| format!("opening factor panel part {}", part.display()))?;
        let headers = reader
            .headers()
            .map_err(|error| ApiError::internal(error.into()))?
            .clone();
        let header_index = header_index(&headers);
        for record in reader.records() {
            let record = record.map_err(|error| ApiError::internal(error.into()))?;
            if sampled % stride != 0 {
                sampled += 1;
                continue;
            }
            sampled += 1;
            if seen < offset {
                seen += 1;
                continue;
            }
            if rows.len() >= limit {
                break;
            }
            rows.push(parse_factor_panel_replay_row(
                &header_index,
                &record,
                market,
            )?);
            seen += 1;
        }
        if rows.len() >= limit {
            break;
        }
    }

    Ok((
        rows,
        parts,
        relative_to_root(panel_dir, &state.root),
        market.price_book_kind,
        market.factor_kind,
        market.replay_caveat.to_string(),
    ))
}

fn parse_replay_state_row(
    headers: &HashMap<String, usize>,
    record: &StringRecord,
    ordinal: u64,
) -> Result<ReplayRow, ApiError> {
    let bid_levels = parse_levels(field(headers, record, "bid_top_levels_json")?)?;
    let ask_levels = parse_levels(field(headers, record, "ask_top_levels_json")?)?;
    let timestamp = parse_i64(headers, record, "timestamp")?;
    let local_timestamp = parse_i64(headers, record, "local_timestamp")?;
    let mut factors = Map::new();
    for name in [
        "snapshot_batch",
        "batch_rows",
        "crossed_levels_removed",
        "bid_levels",
        "ask_levels",
        "bid_depth_5",
        "ask_depth_5",
        "imbalance_5",
        "bid_depth_25",
        "ask_depth_25",
        "imbalance_25",
        "bid_slope_5",
        "ask_slope_5",
        "depth_curvature_5",
    ] {
        if let Some(value) = record_get(headers, record, name) {
            factors.insert(name.to_string(), cell_to_value(value));
        }
    }

    Ok(ReplayRow {
        event_index: ordinal,
        timestamp,
        local_timestamp,
        timestamp_utc: micros_to_utc(timestamp),
        best_bid_price: parse_f64(headers, record, "best_bid_price")?,
        best_bid_amount: parse_f64(headers, record, "best_bid_amount")?,
        best_ask_price: parse_f64(headers, record, "best_ask_price")?,
        best_ask_amount: parse_f64(headers, record, "best_ask_amount")?,
        mid_price: parse_f64(headers, record, "mid_price")?,
        spread_bps: parse_f64(headers, record, "spread_bps")?,
        microprice: parse_f64(headers, record, "microprice")?,
        bid_levels,
        ask_levels,
        factors,
    })
}

fn parse_factor_panel_replay_row(
    headers: &HashMap<String, usize>,
    record: &StringRecord,
    market: &MarketSpec,
) -> Result<ReplayRow, ApiError> {
    let bid_levels = parse_levels(field(headers, record, "bid_top_levels_json")?)?;
    let ask_levels = parse_levels(field(headers, record, "ask_top_levels_json")?)?;
    let timestamp = parse_i64(headers, record, "timestamp")?;
    let local_timestamp = parse_i64(headers, record, "local_timestamp")?;
    let event_index = record_get(headers, record, "event_index")
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(0);
    let mut row = ReplayRow {
        event_index,
        timestamp,
        local_timestamp,
        timestamp_utc: micros_to_utc(timestamp),
        best_bid_price: parse_f64(headers, record, "best_bid_price")?,
        best_bid_amount: parse_f64(headers, record, "best_bid_amount")?,
        best_ask_price: parse_f64(headers, record, "best_ask_price")?,
        best_ask_amount: parse_f64(headers, record, "best_ask_amount")?,
        mid_price: parse_f64(headers, record, "mid_price")?,
        spread_bps: parse_f64(headers, record, "spread_bps")?,
        microprice: parse_f64(headers, record, "microprice")?,
        bid_levels,
        ask_levels,
        factors: factor_map(headers, record),
    };
    add_source_diagnostics(&mut row, market.price_book_kind, market.factor_kind);
    Ok(row)
}

fn read_factor_lookup(
    panel_dir: &Path,
    timestamps: &BTreeSet<i64>,
) -> Result<HashMap<i64, (u64, Map<String, Value>)>, ApiError> {
    let mut out = HashMap::new();
    for part in csv_parts(panel_dir)? {
        let mut reader = csv::Reader::from_path(&part)
            .with_context(|| format!("opening factor part {}", part.display()))
            .map_err(ApiError::from)?;
        let headers = reader
            .headers()
            .map_err(|error| ApiError::internal(error.into()))?
            .clone();
        let header_index = header_index(&headers);
        for record in reader.records() {
            let record = record.map_err(|error| ApiError::internal(error.into()))?;
            let timestamp = match record_get(&header_index, &record, "timestamp")
                .and_then(|value| value.parse::<i64>().ok())
            {
                Some(value) if timestamps.contains(&value) => value,
                _ => continue,
            };
            let event_index = record_get(&header_index, &record, "event_index")
                .and_then(|value| value.parse::<u64>().ok())
                .unwrap_or(0);
            out.insert(timestamp, (event_index, factor_map(&header_index, &record)));
            if out.len() >= timestamps.len() {
                return Ok(out);
            }
        }
    }
    Ok(out)
}

fn factor_map(headers: &HashMap<String, usize>, record: &StringRecord) -> Map<String, Value> {
    let mut out = Map::new();
    for (name, idx) in headers {
        if is_core_replay_column(name) {
            continue;
        }
        if let Some(value) = record.get(*idx) {
            out.insert(name.clone(), cell_to_value(value));
        }
    }
    for (name, alias) in [
        ("best_bid_price", "panel_best_bid_price"),
        ("best_ask_price", "panel_best_ask_price"),
        ("mid_price", "panel_mid_price"),
        ("spread_bps", "panel_spread_bps"),
        ("microprice", "panel_microprice"),
    ] {
        if let Some(value) = record_get(headers, record, name) {
            out.insert(alias.to_string(), cell_to_value(value));
        }
    }
    out
}

fn is_core_replay_column(name: &str) -> bool {
    matches!(
        name,
        "run_tag"
            | "date"
            | "symbol"
            | "exchange"
            | "timestamp"
            | "local_timestamp"
            | "event_index"
            | "best_bid_price"
            | "best_bid_amount"
            | "best_ask_price"
            | "best_ask_amount"
            | "mid_price"
            | "spread_bps"
            | "microprice"
            | "bid_top_levels_json"
            | "ask_top_levels_json"
    )
}

fn add_source_diagnostics(row: &mut ReplayRow, price_book_source: &str, factor_source: &str) {
    if let Some(panel_mid) = map_number(row.factors.get("panel_mid_price")) {
        if row.mid_price.abs() > f64::EPSILON {
            let delta_bps = (panel_mid / row.mid_price - 1.0) * 10_000.0;
            row.factors
                .insert("panel_mid_delta_bps".to_string(), json!(delta_bps));
            row.factors.insert(
                "panel_mid_delta_ticks_est".to_string(),
                json!((panel_mid - row.mid_price) / 0.001),
            );
        }
    }
    row.factors
        .insert("price_book_source".to_string(), json!(price_book_source));
    row.factors
        .insert("factor_source".to_string(), json!(factor_source));
}

fn map_number(value: Option<&Value>) -> Option<f64> {
    value
        .and_then(|value| match value {
            Value::Number(number) => number.as_f64(),
            Value::String(text) => text.parse::<f64>().ok(),
            _ => None,
        })
        .filter(|value| value.is_finite())
}

fn build_markets(bonk_run_tag: String, cc_run_tag: String) -> BTreeMap<String, MarketSpec> {
    [
        MarketSpec {
            id: "ccusdt",
            label: "CCUSDT",
            replay_mode: ReplayMode::FactorPanelOnly,
            run_tag: cc_run_tag,
            data_root: "data/ccusdt/v1",
            replay_dataset: None,
            factor_dataset: "ccusdt_v1_fixed_event_factor_panel",
            price_book_kind: "factor_panel",
            factor_kind: "cc_fixed_event_panel",
            replay_caveat: "CCUSDT uses the fixed event factor panel itself for price/book replay; rows are snapshot-diff diagnostics, not queue-position fill evidence",
            quality_prefix: "ccusdt_v1_fixed_event_factors_quality",
            factor_ranking_prefix: "ccusdt_v1_fixed_event_factors_path_ranking",
            default_symbol: "CCUSDT",
            default_date: "2026-04-29",
        },
        MarketSpec {
            id: "bonk",
            label: "BONK",
            replay_mode: ReplayMode::BookStatePlusFactors,
            run_tag: bonk_run_tag,
            data_root: "data/bonk/v1",
            replay_dataset: Some("bonk_v10_replayed_book_state"),
            factor_dataset: "bonk_v10c_event_ofi_panel",
            price_book_kind: "book_state",
            factor_kind: "v10c_panel",
            replay_caveat: "price/order-book fields are served from bonk_v10_replayed_book_state; V10c panel price fields are exposed only as diagnostics because stale panel prices were observed in replay windows",
            quality_prefix: "bonk_v10_dynamic_orderbook_analysis_quality_daily",
            factor_ranking_prefix: "bonk_v10c_event_ofi_path_ranking",
            default_symbol: "BONK1MUSDC",
            default_date: "2026-05-06",
        },
    ]
    .into_iter()
    .map(|market| (market.id.to_string(), market))
    .collect()
}

fn market_spec<'a>(state: &'a AppState, market: Option<&str>) -> Result<&'a MarketSpec, ApiError> {
    let id = market.unwrap_or("ccusdt").to_ascii_lowercase();
    state
        .markets
        .get(&id)
        .ok_or_else(|| ApiError::bad_request(format!("unknown market: {id}")))
}

fn market_infos(state: &AppState) -> Vec<MarketInfo> {
    let mut infos: Vec<_> = state
        .markets
        .values()
        .map(|market| MarketInfo {
            id: market.id.to_string(),
            label: market.label.to_string(),
            run_tag: market.run_tag.clone(),
            replay_mode: market.replay_mode,
            default_symbol: market.default_symbol.to_string(),
            default_date: market.default_date.to_string(),
        })
        .collect();
    infos.sort_by_key(|market| (market.id != "ccusdt", market.id.clone()));
    infos
}

fn manifest_artifacts(state: &AppState, market: &MarketSpec, quality_path: &Path) -> Vec<String> {
    let mut artifacts = vec![
        relative_to_root(quality_path, &state.root),
        format!(
            "{}/derived/{}/run_tag={}",
            market.data_root, market.factor_dataset, market.run_tag
        ),
    ];
    if let Some(dataset) = market.replay_dataset {
        artifacts.push(format!(
            "{}/derived/{}/run_tag={}",
            market.data_root, dataset, market.run_tag
        ));
    }
    artifacts
}

fn factor_panel_dir(state: &AppState, market: &MarketSpec, symbol: &str, date: &str) -> PathBuf {
    state
        .root
        .join(market.data_root)
        .join("derived")
        .join(market.factor_dataset)
        .join(format!("run_tag={}", market.run_tag))
        .join(format!("symbol={symbol}"))
        .join(format!("dt={date}"))
}

fn replay_state_dir(
    state: &AppState,
    market: &MarketSpec,
    symbol: &str,
    date: &str,
) -> Option<PathBuf> {
    market.replay_dataset.map(|dataset| {
        state
            .root
            .join(market.data_root)
            .join("derived")
            .join(dataset)
            .join(format!("run_tag={}", market.run_tag))
            .join(format!("symbol={symbol}"))
            .join(format!("dt={date}"))
            .join("state_parts")
    })
}

fn parse_levels(raw: &str) -> Result<Vec<BookLevel>, ApiError> {
    let levels: Vec<[f64; 2]> = serde_json::from_str(raw)
        .with_context(|| "parsing top-level order book json")
        .map_err(ApiError::from)?;
    Ok(levels
        .into_iter()
        .map(|level| BookLevel {
            price: level[0],
            amount: level[1],
        })
        .collect())
}

fn read_csv_json(path: &Path, limit: Option<usize>) -> Result<Vec<Value>> {
    read_csv_json_filtered(path, &HashMap::new(), limit)
}

fn read_csv_json_optional(path: &Path, limit: Option<usize>) -> Result<Vec<Value>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_csv_json(path, limit)
}

fn read_csv_json_filtered_optional(
    path: &Path,
    filters: &HashMap<String, String>,
    limit: Option<usize>,
) -> Result<Vec<Value>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    read_csv_json_filtered(path, filters, limit)
}

fn read_csv_json_filtered(
    path: &Path,
    filters: &HashMap<String, String>,
    limit: Option<usize>,
) -> Result<Vec<Value>> {
    let mut reader =
        csv::Reader::from_path(path).with_context(|| format!("opening {}", path.display()))?;
    let headers = reader.headers()?.clone();
    let mut out = Vec::new();
    for record in reader.records() {
        let record = record?;
        if !filters_match(&headers, &record, filters) {
            continue;
        }
        out.push(record_to_value(&headers, &record));
        if limit.is_some_and(|value| out.len() >= value) {
            break;
        }
    }
    Ok(out)
}

fn filters_match(
    headers: &StringRecord,
    record: &StringRecord,
    filters: &HashMap<String, String>,
) -> bool {
    filters.iter().all(|(key, expected)| {
        headers
            .iter()
            .position(|header| header == key)
            .and_then(|idx| record.get(idx))
            .is_some_and(|actual| actual == expected)
    })
}

fn record_to_value(headers: &StringRecord, record: &StringRecord) -> Value {
    let mut map = Map::new();
    for (idx, header) in headers.iter().enumerate() {
        map.insert(
            header.to_string(),
            cell_to_value(record.get(idx).unwrap_or_default()),
        );
    }
    Value::Object(map)
}

fn cell_to_value(value: &str) -> Value {
    let trimmed = value.trim();
    if trimmed.is_empty() || trimmed.eq_ignore_ascii_case("nan") {
        Value::Null
    } else if trimmed.eq_ignore_ascii_case("true") {
        Value::Bool(true)
    } else if trimmed.eq_ignore_ascii_case("false") {
        Value::Bool(false)
    } else if let Ok(value) = trimmed.parse::<i64>() {
        json!(value)
    } else if let Ok(value) = trimmed.parse::<f64>() {
        if value.is_finite() {
            json!(value)
        } else {
            Value::Null
        }
    } else {
        json!(trimmed)
    }
}

fn csv_parts(dir: &Path) -> Result<Vec<PathBuf>, ApiError> {
    let mut parts = Vec::new();
    for entry in std::fs::read_dir(dir)
        .with_context(|| format!("reading directory {}", dir.display()))
        .map_err(ApiError::from)?
    {
        let entry = entry.map_err(|error| ApiError::internal(error.into()))?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) == Some("csv") {
            parts.push(path);
        }
    }
    parts.sort();
    if parts.is_empty() {
        return Err(ApiError::not_found(format!(
            "no csv replay parts under {}",
            dir.display()
        )));
    }
    Ok(parts)
}

fn dated_file(state: &AppState, market: &MarketSpec, prefix: &str, ext: &str) -> PathBuf {
    state
        .root
        .join("date")
        .join(format!("{prefix}_{}.{}", market.run_tag, ext))
}

fn clean_query_value(value: &str, label: &str) -> Result<String, ApiError> {
    let ok = value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.'));
    if ok && !value.contains("..") && !value.is_empty() {
        Ok(value.to_string())
    } else {
        Err(ApiError::bad_request(format!("invalid {label}: {value}")))
    }
}

fn header_index(headers: &StringRecord) -> HashMap<String, usize> {
    headers
        .iter()
        .enumerate()
        .map(|(idx, name)| (name.to_string(), idx))
        .collect()
}

fn field<'a>(
    headers: &HashMap<String, usize>,
    record: &'a StringRecord,
    name: &str,
) -> Result<&'a str, ApiError> {
    record_get(headers, record, name)
        .ok_or_else(|| ApiError::bad_request(format!("missing {name}")))
}

fn record_get<'a>(
    headers: &HashMap<String, usize>,
    record: &'a StringRecord,
    name: &str,
) -> Option<&'a str> {
    headers.get(name).and_then(|idx| record.get(*idx))
}

fn parse_f64(
    headers: &HashMap<String, usize>,
    record: &StringRecord,
    name: &str,
) -> Result<f64, ApiError> {
    field(headers, record, name)?
        .parse::<f64>()
        .map_err(|error| ApiError::bad_request(format!("invalid {name}: {error}")))
}

fn parse_i64(
    headers: &HashMap<String, usize>,
    record: &StringRecord,
    name: &str,
) -> Result<i64, ApiError> {
    field(headers, record, name)?
        .parse::<i64>()
        .map_err(|error| ApiError::bad_request(format!("invalid {name}: {error}")))
}

fn micros_to_utc(value: i64) -> String {
    DateTime::<Utc>::from_timestamp_micros(value)
        .map(|dt| dt.to_rfc3339_opts(chrono::SecondsFormat::Millis, true))
        .unwrap_or_else(|| value.to_string())
}

fn relative_to_root(path: &Path, root: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
