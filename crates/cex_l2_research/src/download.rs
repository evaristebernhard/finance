use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File};
use std::hash::{Hash, Hasher};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result, anyhow, bail};
use chrono::{Datelike, NaiveDate};
use flate2::read::GzDecoder;
use reqwest::blocking::Client;
use reqwest::header::{ACCEPT, AUTHORIZATION, HeaderMap, HeaderValue, USER_AGENT};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const DEFAULT_BONK_DATA_ROOT: &str = "data/bonk/v1";
pub const DEFAULT_FROM_DATE: &str = "2026-04-29";
pub const DEFAULT_TO_DATE: &str = "2026-05-12";
pub const DEFAULT_BULLISH_BASKET_RUN_TAG: &str = "20260513_bullish_l2_basket_rust_v1";
pub const DEFAULT_BULLISH_EXCHANGE: &str = "bullish";
pub const DEFAULT_BULLISH_BASKET_SYMBOLS: &str = concat!(
    "BONK1MUSDC,BONK1MUSDT,",
    "BTCUSDC,ETHUSDC,SOLUSDC,",
    "DOGEUSDC,PENGUUSDC,",
    "PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,",
    "SUIUSDC,APTUSDC,ARBUSDC,OPUSDC"
);
pub const DEFAULT_BULLISH_DATA_TYPES: &str = "book_snapshot_25,book_ticker,trades";
pub const DEFAULT_FULL_L2_DATA_TYPES: &str =
    "incremental_book_L2,book_snapshot_25,book_ticker,trades";
pub const DEFAULT_MIN_DOWNLOAD_BYTES_PER_SECOND: u64 = 32 * 1024;

const DATASETS_BASE: &str = "https://datasets.tardis.dev/v1";
const USER_AGENT_VALUE: &str = "finance-chain-bonk-bullish-l2-downloader-rust/0.1";
const LOW_SPEED_GRACE_SECONDS: u64 = 30;
const READ_STALL_TIMEOUT_SECONDS: u64 = 45;

#[derive(Debug, Clone)]
pub struct BullishDownloadConfig {
    pub exchange: String,
    pub data_root: PathBuf,
    pub date_dir: PathBuf,
    pub env_file: PathBuf,
    pub api_key: Option<String>,
    pub from_date: NaiveDate,
    pub to_date: NaiveDate,
    pub symbols: String,
    pub extra_symbols: String,
    pub data_types: String,
    pub run_tag: String,
    pub timeout_seconds: u64,
    pub max_retries: usize,
    pub workers: usize,
    pub skip_preflight: bool,
    pub min_free_gb: f64,
    pub force: bool,
    pub dry_run: bool,
    pub quick_validate: bool,
    pub min_bytes_per_second: u64,
    pub output_prefix: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileResult {
    pub exchange: String,
    pub data_type: String,
    pub symbol: String,
    pub date: String,
    pub url: String,
    pub path: String,
    pub status: String,
    pub http_status: Option<u16>,
    pub bytes: u64,
    pub gzip_ok: bool,
    pub header: Vec<String>,
    pub sample_rows: u64,
    pub error: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SymbolPreflightRow {
    pub symbol: String,
    pub status: String,
    pub exchange: String,
    #[serde(rename = "type")]
    pub symbol_type: String,
    #[serde(rename = "availableSince")]
    pub available_since: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BullishDownloadOutputs {
    pub completion_json: String,
    pub manifest_csv: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BullishDownloadSummary {
    pub run_tag: String,
    pub started_at_utc: String,
    pub finished_at_utc: String,
    pub data_root: String,
    pub date_dir: String,
    pub from_date: String,
    pub to_date: String,
    pub symbols: Vec<String>,
    pub scheduled_symbols: Vec<String>,
    pub workers: usize,
    pub skip_preflight: bool,
    pub symbol_preflight: Vec<SymbolPreflightRow>,
    pub data_types: Vec<String>,
    pub dry_run: bool,
    pub free_gb_before: f64,
    pub counts: BTreeMap<String, usize>,
    pub raw_fingerprint: RawFingerprint,
    pub outputs: BullishDownloadOutputs,
    pub files: Vec<FileResult>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RawFingerprint {
    pub file_count: usize,
    pub total_bytes: u64,
    pub hash: String,
}

#[derive(Debug, Clone)]
struct DownloadJob {
    exchange: String,
    day: NaiveDate,
    data_type: String,
    symbol: String,
    url: String,
    path: PathBuf,
}

#[derive(Debug, Clone)]
struct ValidateResult {
    gzip_ok: bool,
    header: Vec<String>,
    sample_rows: u64,
    empty_payload: bool,
    error: String,
}

pub fn run_bullish_l2_download(config: &BullishDownloadConfig) -> Result<BullishDownloadSummary> {
    if config.from_date > config.to_date {
        bail!(
            "--from-date {} is after --to-date {}",
            config.from_date,
            config.to_date
        );
    }
    if config.workers == 0 {
        bail!("--workers must be >= 1");
    }
    let started_at_utc = utc_now_string();
    fs::create_dir_all(&config.date_dir)
        .with_context(|| format!("failed to create {}", config.date_dir.display()))?;
    fs::create_dir_all(&config.data_root)
        .with_context(|| format!("failed to create {}", config.data_root.display()))?;

    let exchange = normalized_exchange(&config.exchange)?;
    let mut symbols = parse_symbol_list(&config.symbols);
    symbols.extend(parse_symbol_list(&config.extra_symbols));
    symbols = dedup(symbols);
    let data_types = parse_data_types(&config.data_types);
    if symbols.is_empty() {
        bail!("at least one symbol is required");
    }
    if data_types.is_empty() {
        bail!("at least one data type is required");
    }

    let free_gb = free_gb(&config.data_root)?;
    if !config.dry_run && free_gb < config.min_free_gb {
        bail!(
            "free disk space is {:.2} GB, below --min-free-gb {:.2}",
            free_gb,
            config.min_free_gb
        );
    }

    let api_key = if config.dry_run && config.skip_preflight {
        String::new()
    } else {
        load_tardis_key(config)?
    };
    let client = build_client(config.timeout_seconds)?;
    let (scheduled_symbols, symbol_preflight) = if config.dry_run && api_key.is_empty() {
        (
            symbols.clone(),
            symbols
                .iter()
                .map(|symbol| SymbolPreflightRow {
                    symbol: symbol.clone(),
                    status: "not_checked".to_string(),
                    exchange: exchange.clone(),
                    symbol_type: String::new(),
                    available_since: String::new(),
                })
                .collect(),
        )
    } else {
        preflight_symbols(
            &client,
            &symbols,
            &api_key,
            &exchange,
            config.skip_preflight,
            config.timeout_seconds,
        )?
    };

    let dates = date_range(config.from_date, config.to_date);
    let missing_symbols = symbol_preflight
        .iter()
        .filter(|row| row.status == "missing")
        .map(|row| row.symbol.clone())
        .collect::<Vec<_>>();
    let mut results = missing_symbol_results(
        &config.data_root,
        &dates,
        &data_types,
        &missing_symbols,
        &exchange,
    );
    let jobs = build_jobs(
        &config.data_root,
        &dates,
        &data_types,
        &scheduled_symbols,
        &exchange,
    );
    for result in &results {
        eprintln!(
            "{} {} {}: {} bytes={}",
            result.date, result.data_type, result.symbol, result.status, result.bytes
        );
    }
    results.extend(run_jobs(jobs, config, api_key, client)?);
    results.sort_by(|a, b| {
        a.date
            .cmp(&b.date)
            .then_with(|| a.data_type.cmp(&b.data_type))
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.path.cmp(&b.path))
    });
    let counts = status_counts(&results);
    let raw_fingerprint = fingerprint_results(&results);
    let completion_path = config.date_dir.join(format!(
        "{}_completion_{}.json",
        config.output_prefix, config.run_tag
    ));
    let manifest_path = config.date_dir.join(format!(
        "{}_manifest_{}.csv",
        config.output_prefix, config.run_tag
    ));
    let outputs = BullishDownloadOutputs {
        completion_json: path_string(&completion_path),
        manifest_csv: path_string(&manifest_path),
    };
    let summary = BullishDownloadSummary {
        run_tag: config.run_tag.clone(),
        started_at_utc,
        finished_at_utc: utc_now_string(),
        data_root: path_string(&config.data_root),
        date_dir: path_string(&config.date_dir),
        from_date: config.from_date.to_string(),
        to_date: config.to_date.to_string(),
        symbols,
        scheduled_symbols,
        workers: config.workers,
        skip_preflight: config.skip_preflight,
        symbol_preflight,
        data_types,
        dry_run: config.dry_run,
        free_gb_before: free_gb,
        counts,
        raw_fingerprint,
        outputs,
        files: results,
    };
    write_json_atomic(&completion_path, &summary)?;
    write_manifest_csv(&manifest_path, &summary.files)?;
    Ok(summary)
}

fn run_jobs(
    jobs: Vec<DownloadJob>,
    config: &BullishDownloadConfig,
    api_key: String,
    client: Client,
) -> Result<Vec<FileResult>> {
    if jobs.is_empty() {
        return Ok(Vec::new());
    }
    let queue = Arc::new(Mutex::new(VecDeque::from(jobs)));
    let results = Arc::new(Mutex::new(Vec::<FileResult>::new()));
    let api_key = Arc::new(api_key);
    let config = Arc::new(config.clone());
    let workers = config.workers.min(queue.lock().unwrap().len()).max(1);
    let mut handles = Vec::with_capacity(workers);
    for _ in 0..workers {
        let queue = Arc::clone(&queue);
        let results = Arc::clone(&results);
        let api_key = Arc::clone(&api_key);
        let config = Arc::clone(&config);
        let client = client.clone();
        handles.push(thread::spawn(move || -> Result<()> {
            loop {
                let job = {
                    let mut guard = queue.lock().unwrap();
                    guard.pop_front()
                };
                let Some(job) = job else {
                    break;
                };
                let result = process_job(&client, &job, &config, &api_key);
                eprintln!(
                    "{} {} {}: {} bytes={}",
                    result.date, result.data_type, result.symbol, result.status, result.bytes
                );
                results.lock().unwrap().push(result);
            }
            Ok(())
        }));
    }
    for handle in handles {
        handle
            .join()
            .map_err(|_| anyhow!("download worker panicked"))??;
    }
    let mut guard = results.lock().unwrap();
    Ok(std::mem::take(&mut *guard))
}

fn process_job(
    client: &Client,
    job: &DownloadJob,
    config: &BullishDownloadConfig,
    api_key: &str,
) -> FileResult {
    if config.dry_run {
        return base_result(job, "planned", None, 0, false, Vec::new(), 0, "");
    }
    if job.path.exists() && !config.force {
        match validate_gzip_csv(&job.path, config.quick_validate) {
            Ok(validation) => {
                let bytes = job.path.metadata().map(|meta| meta.len()).unwrap_or(0);
                let status = if validation.gzip_ok && validation.sample_rows > 0 {
                    "skipped"
                } else if validation.empty_payload || validation.gzip_ok {
                    "empty"
                } else {
                    "error"
                };
                if status != "error" {
                    return base_result(
                        job,
                        status,
                        None,
                        bytes,
                        validation.gzip_ok,
                        validation.header,
                        validation.sample_rows,
                        &validation.error,
                    );
                }
            }
            Err(err) => {
                let bytes = job.path.metadata().map(|meta| meta.len()).unwrap_or(0);
                return base_result(
                    job,
                    "error",
                    None,
                    bytes,
                    false,
                    Vec::new(),
                    0,
                    &err.to_string(),
                );
            }
        }
    }
    match download_file(client, job, api_key, config) {
        Ok(result) => result,
        Err(err) => base_result(
            job,
            "error",
            None,
            0,
            false,
            Vec::new(),
            0,
            &err.to_string(),
        ),
    }
}

fn download_file(
    client: &Client,
    job: &DownloadJob,
    api_key: &str,
    config: &BullishDownloadConfig,
) -> Result<FileResult> {
    let retries = config.max_retries.max(1);
    let mut last_error = String::new();
    for attempt in 0..retries {
        eprintln!(
            "download_attempt exchange={} data_type={} symbol={} date={} attempt={}/{}",
            job.exchange,
            job.data_type,
            job.symbol,
            job.day,
            attempt + 1,
            retries
        );
        match download_once(
            client,
            &job.url,
            &job.path,
            api_key,
            config.min_bytes_per_second,
        ) {
            Ok((status, bytes)) => {
                let validation = validate_gzip_csv(&job.path, config.quick_validate)?;
                if !validation.gzip_ok {
                    let _ = fs::remove_file(&job.path);
                    return Ok(base_result(
                        job,
                        "error",
                        Some(status),
                        bytes,
                        false,
                        validation.header,
                        validation.sample_rows,
                        &validation.error,
                    ));
                }
                if validation.empty_payload || validation.sample_rows == 0 {
                    return Ok(base_result(
                        job,
                        "empty",
                        Some(status),
                        bytes,
                        true,
                        validation.header,
                        validation.sample_rows,
                        &validation.error,
                    ));
                }
                return Ok(base_result(
                    job,
                    "downloaded",
                    Some(status),
                    bytes,
                    true,
                    validation.header,
                    validation.sample_rows,
                    "",
                ));
            }
            Err(DownloadError::Http { status, body }) => {
                if status == 400 && body.contains("\"code\": 140") {
                    return Ok(base_result(
                        job,
                        "unavailable",
                        Some(status),
                        0,
                        false,
                        Vec::new(),
                        0,
                        &body,
                    ));
                }
                if status == 404 {
                    return Ok(base_result(
                        job,
                        "missing",
                        Some(status),
                        0,
                        false,
                        Vec::new(),
                        0,
                        &body,
                    ));
                }
                if status == 401 || status == 403 || (400..500).contains(&status) {
                    return Ok(base_result(
                        job,
                        "error",
                        Some(status),
                        0,
                        false,
                        Vec::new(),
                        0,
                        &body,
                    ));
                }
                last_error = format!("HTTP {status}: {body}");
            }
            Err(DownloadError::Other(err)) => {
                last_error = err;
            }
        }
        if attempt + 1 < retries {
            eprintln!(
                "download_retry exchange={} data_type={} symbol={} date={} attempt={}/{} error={}",
                job.exchange,
                job.data_type,
                job.symbol,
                job.day,
                attempt + 1,
                retries,
                last_error
            );
            sleep_for_attempt(attempt);
        }
    }
    Ok(base_result(
        job,
        "error",
        None,
        0,
        false,
        Vec::new(),
        0,
        &last_error,
    ))
}

#[derive(Debug)]
enum DownloadError {
    Http { status: u16, body: String },
    Other(String),
}

fn download_once(
    client: &Client,
    url: &str,
    path: &Path,
    api_key: &str,
    min_bytes_per_second: u64,
) -> std::result::Result<(u16, u64), DownloadError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| DownloadError::Other(err.to_string()))?;
    }
    let part_path = path.with_file_name(format!(
        ".{}.part.{}",
        path.file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("download"),
        std::process::id()
    ));
    let _ = fs::remove_file(&part_path);
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static(USER_AGENT_VALUE));
    headers.insert(
        ACCEPT,
        HeaderValue::from_static("text/csv,application/gzip,*/*"),
    );
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {api_key}"))
            .map_err(|err| DownloadError::Other(err.to_string()))?,
    );
    let mut response = client
        .get(url)
        .headers(headers)
        .send()
        .map_err(|err| DownloadError::Other(err.to_string()))?;
    let status = response.status().as_u16();
    if !response.status().is_success() {
        let body = response
            .text()
            .unwrap_or_default()
            .chars()
            .take(240)
            .collect::<String>();
        return Err(DownloadError::Http { status, body });
    }
    let expected = response.content_length();
    let mut file = File::create(&part_path).map_err(|err| DownloadError::Other(err.to_string()))?;
    let started = Instant::now();
    let mut bytes = 0u64;
    let mut next_progress_log = 64 * 1024 * 1024;
    let (chunk_tx, chunk_rx) = mpsc::sync_channel::<std::result::Result<Vec<u8>, String>>(2);
    thread::spawn(move || {
        let mut buffer = [0u8; 1024 * 1024];
        loop {
            match response.read(&mut buffer) {
                Ok(0) => {
                    let _ = chunk_tx.send(Ok(Vec::new()));
                    break;
                }
                Ok(read) => {
                    if chunk_tx.send(Ok(buffer[..read].to_vec())).is_err() {
                        break;
                    }
                }
                Err(err) => {
                    let _ = chunk_tx.send(Err(err.to_string()));
                    break;
                }
            }
        }
    });
    loop {
        let chunk = match chunk_rx.recv_timeout(Duration::from_secs(READ_STALL_TIMEOUT_SECONDS)) {
            Ok(Ok(chunk)) => chunk,
            Ok(Err(err)) => {
                drop(file);
                let _ = fs::remove_file(&part_path);
                return Err(DownloadError::Other(err));
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                drop(file);
                let _ = fs::remove_file(&part_path);
                return Err(DownloadError::Other(format!(
                    "download stalled: no bytes for {READ_STALL_TIMEOUT_SECONDS}s after {bytes} bytes"
                )));
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                drop(file);
                let _ = fs::remove_file(&part_path);
                return Err(DownloadError::Other(
                    "download reader disconnected".to_string(),
                ));
            }
        };
        if chunk.is_empty() {
            break;
        }
        file.write_all(&chunk)
            .map_err(|err| DownloadError::Other(err.to_string()))?;
        bytes = bytes.saturating_add(chunk.len() as u64);
        if bytes >= next_progress_log {
            eprintln!(
                "download_progress path={} total_bytes={bytes}",
                path.display()
            );
            next_progress_log = next_progress_log.saturating_add(64 * 1024 * 1024);
        }
        let elapsed = started.elapsed();
        if elapsed >= Duration::from_secs(LOW_SPEED_GRACE_SECONDS) {
            let bytes_per_second = bytes / elapsed.as_secs().max(1);
            if min_bytes_per_second > 0 && bytes_per_second < min_bytes_per_second {
                drop(file);
                let _ = fs::remove_file(&part_path);
                return Err(DownloadError::Other(format!(
                    "download too slow: {bytes_per_second} B/s after {}s",
                    elapsed.as_secs()
                )));
            }
        }
    }
    file.flush()
        .map_err(|err| DownloadError::Other(err.to_string()))?;
    drop(file);
    if expected.is_some_and(|expected| expected != bytes) {
        let _ = fs::remove_file(&part_path);
        return Err(DownloadError::Other(format!(
            "truncated download: got {bytes}, expected {}",
            expected.unwrap()
        )));
    }
    if bytes == 0 {
        let _ = fs::remove_file(&part_path);
        return Err(DownloadError::Other("empty download".to_string()));
    }
    if path.exists() {
        fs::remove_file(path).map_err(|err| DownloadError::Other(err.to_string()))?;
    }
    fs::rename(&part_path, path).map_err(|err| DownloadError::Other(err.to_string()))?;
    Ok((status, bytes))
}

fn validate_gzip_csv(path: &Path, quick_validate: bool) -> Result<ValidateResult> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let decoder = GzDecoder::new(file);
    let mut reader = BufReader::new(decoder);
    let mut header_line = String::new();
    let header_bytes = reader
        .read_line(&mut header_line)
        .with_context(|| format!("failed to read gzip header {}", path.display()))?;
    if header_bytes == 0 {
        return Ok(ValidateResult {
            gzip_ok: true,
            header: Vec::new(),
            sample_rows: 0,
            empty_payload: true,
            error: "empty gzip payload".to_string(),
        });
    }
    let header = parse_header_line(&header_line)?;
    let mut sample_rows = 0u64;
    let mut line = String::new();
    for _ in 0..3 {
        line.clear();
        if reader
            .read_line(&mut line)
            .with_context(|| format!("failed to read sample row {}", path.display()))?
            == 0
        {
            break;
        }
        if !line.trim().is_empty() {
            sample_rows += 1;
        }
    }
    if !quick_validate {
        let mut sink = [0u8; 1024 * 1024];
        while reader
            .read(&mut sink)
            .with_context(|| format!("failed to drain gzip {}", path.display()))?
            > 0
        {}
    }
    Ok(ValidateResult {
        gzip_ok: true,
        header,
        sample_rows,
        empty_payload: false,
        error: String::new(),
    })
}

fn parse_header_line(line: &str) -> Result<Vec<String>> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .from_reader(line.as_bytes());
    let record = reader
        .records()
        .next()
        .ok_or_else(|| anyhow!("missing CSV header"))?
        .context("failed to parse CSV header")?;
    Ok(record.iter().map(str::to_string).collect())
}

fn build_jobs(
    data_root: &Path,
    dates: &[NaiveDate],
    data_types: &[String],
    symbols: &[String],
    exchange: &str,
) -> Vec<DownloadJob> {
    let mut jobs = Vec::new();
    for day in dates {
        for data_type in data_types {
            for symbol in symbols {
                jobs.push(DownloadJob {
                    exchange: exchange.to_string(),
                    day: *day,
                    data_type: data_type.clone(),
                    symbol: symbol.clone(),
                    url: dataset_url(exchange, data_type, *day, symbol),
                    path: raw_path(data_root, exchange, data_type, *day, symbol),
                });
            }
        }
    }
    jobs
}

fn missing_symbol_results(
    data_root: &Path,
    dates: &[NaiveDate],
    data_types: &[String],
    missing_symbols: &[String],
    exchange: &str,
) -> Vec<FileResult> {
    build_jobs(data_root, dates, data_types, missing_symbols, exchange)
        .into_iter()
        .map(|job| {
            base_result(
                &job,
                "missing",
                None,
                0,
                false,
                Vec::new(),
                0,
                "symbol not present in Bullish metadata preflight",
            )
        })
        .collect()
}

fn base_result(
    job: &DownloadJob,
    status: &str,
    http_status: Option<u16>,
    bytes: u64,
    gzip_ok: bool,
    header: Vec<String>,
    sample_rows: u64,
    error: &str,
) -> FileResult {
    FileResult {
        exchange: job.exchange.clone(),
        data_type: job.data_type.clone(),
        symbol: job.symbol.clone(),
        date: job.day.to_string(),
        url: job.url.clone(),
        path: path_string(&job.path),
        status: status.to_string(),
        http_status,
        bytes,
        gzip_ok,
        header,
        sample_rows,
        error: error.to_string(),
    }
}

fn preflight_symbols(
    client: &Client,
    symbols: &[String],
    api_key: &str,
    exchange: &str,
    skip_preflight: bool,
    _timeout_seconds: u64,
) -> Result<(Vec<String>, Vec<SymbolPreflightRow>)> {
    if skip_preflight {
        return Ok((
            symbols.to_vec(),
            symbols
                .iter()
                .map(|symbol| SymbolPreflightRow {
                    symbol: symbol.clone(),
                    status: "not_checked".to_string(),
                    exchange: exchange.to_string(),
                    symbol_type: String::new(),
                    available_since: String::new(),
                })
                .collect(),
        ));
    }
    let metadata = bullish_symbol_metadata(client, api_key, exchange)?;
    let mut scheduled = Vec::new();
    let mut rows = Vec::new();
    for symbol in symbols {
        if let Some(item) = metadata.get(symbol) {
            scheduled.push(symbol.clone());
            rows.push(SymbolPreflightRow {
                symbol: symbol.clone(),
                status: "available".to_string(),
                exchange: exchange.to_string(),
                symbol_type: item
                    .get("type")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                available_since: item
                    .get("availableSince")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
            });
        } else {
            rows.push(SymbolPreflightRow {
                symbol: symbol.clone(),
                status: "missing".to_string(),
                exchange: exchange.to_string(),
                symbol_type: String::new(),
                available_since: String::new(),
            });
        }
    }
    Ok((scheduled, rows))
}

fn bullish_symbol_metadata(
    client: &Client,
    api_key: &str,
    exchange: &str,
) -> Result<BTreeMap<String, Value>> {
    let mut headers = HeaderMap::new();
    headers.insert(USER_AGENT, HeaderValue::from_static(USER_AGENT_VALUE));
    headers.insert(ACCEPT, HeaderValue::from_static("application/json"));
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {api_key}"))
            .context("invalid Tardis API key header")?,
    );
    let body = client
        .get(format!("https://api.tardis.dev/v1/exchanges/{exchange}"))
        .headers(headers)
        .send()
        .with_context(|| format!("failed to request {exchange} metadata"))?
        .error_for_status()
        .with_context(|| format!("{exchange} metadata request failed"))?
        .json::<Value>()
        .context("failed to parse Bullish metadata JSON")?;
    let symbols = body
        .get("availableSymbols")
        .or_else(|| body.get("symbols"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut out = BTreeMap::new();
    for item in symbols {
        if let Some(symbol) = item.as_str() {
            let symbol = symbol.to_ascii_uppercase();
            out.insert(symbol.clone(), serde_json::json!({ "id": symbol }));
        } else if let Some(object) = item.as_object() {
            let symbol = object
                .get("id")
                .or_else(|| object.get("symbol"))
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_ascii_uppercase();
            if !symbol.is_empty() {
                out.insert(symbol, Value::Object(object.clone()));
            }
        }
    }
    Ok(out)
}

fn load_tardis_key(config: &BullishDownloadConfig) -> Result<String> {
    if let Some(key) = config
        .api_key
        .as_ref()
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    {
        if key.len() < 20 {
            bail!("TARDIS_API_KEY exists but is too short");
        }
        return Ok(key.to_string());
    }
    if let Ok(key) = std::env::var("TARDIS_API_KEY") {
        let key = key.trim().to_string();
        if key.len() < 20 {
            bail!("TARDIS_API_KEY exists in environment but is too short");
        }
        return Ok(key);
    }
    let text = fs::read_to_string(&config.env_file).with_context(|| {
        format!(
            "TARDIS_API_KEY not found; env file does not exist or cannot be read: {}",
            config.env_file.display()
        )
    })?;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('#') {
            continue;
        }
        if let Some(rest) = trimmed.strip_prefix("TARDIS_API_KEY") {
            let Some(value) = rest.trim_start().strip_prefix('=') else {
                continue;
            };
            let key = value
                .trim()
                .trim_matches('"')
                .trim_matches('\'')
                .to_string();
            if key.len() < 20 {
                bail!("TARDIS_API_KEY exists but is too short");
            }
            return Ok(key);
        }
    }
    bail!("TARDIS_API_KEY not found in {}", config.env_file.display())
}

fn dataset_url(exchange: &str, data_type: &str, day: NaiveDate, symbol: &str) -> String {
    format!(
        "{DATASETS_BASE}/{exchange}/{}/{:04}/{:02}/{:02}/{}.csv.gz",
        data_type,
        day.year(),
        day.month(),
        day.day(),
        symbol
    )
}

fn raw_path(
    data_root: &Path,
    exchange: &str,
    data_type: &str,
    day: NaiveDate,
    symbol: &str,
) -> PathBuf {
    data_root
        .join("external")
        .join(format!("{exchange}_{data_type}"))
        .join(format!("symbol={symbol}"))
        .join(format!("dt={day}"))
        .join(format!("{symbol}.csv.gz"))
}

fn date_range(start: NaiveDate, end: NaiveDate) -> Vec<NaiveDate> {
    let mut out = Vec::new();
    let mut day = start;
    while day <= end {
        out.push(day);
        day = day.succ_opt().expect("date overflow");
    }
    out
}

pub fn parse_symbol_list(raw: &str) -> Vec<String> {
    raw.split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_ascii_uppercase)
        .collect()
}

pub fn parse_data_types(raw: &str) -> Vec<String> {
    dedup(
        raw.split(',')
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
            .collect(),
    )
}

fn normalized_exchange(raw: &str) -> Result<String> {
    let exchange = raw.trim().to_ascii_lowercase();
    if exchange.is_empty() {
        bail!("--exchange must not be empty");
    }
    if exchange.contains('/') || exchange.contains('\\') || exchange.contains("..") {
        bail!("invalid exchange name: {exchange}");
    }
    Ok(exchange)
}

fn dedup<T>(values: Vec<T>) -> Vec<T>
where
    T: Clone + Ord,
{
    let mut seen = BTreeMap::<T, ()>::new();
    let mut out = Vec::new();
    for value in values {
        if seen.insert(value.clone(), ()).is_none() {
            out.push(value);
        }
    }
    out
}

fn status_counts(results: &[FileResult]) -> BTreeMap<String, usize> {
    let mut out = BTreeMap::new();
    for result in results {
        *out.entry(result.status.clone()).or_insert(0) += 1;
    }
    out
}

fn fingerprint_results(results: &[FileResult]) -> RawFingerprint {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    let mut file_count = 0usize;
    let mut total_bytes = 0u64;
    for result in results {
        if matches!(result.status.as_str(), "downloaded" | "skipped" | "empty") {
            file_count += 1;
            total_bytes = total_bytes.saturating_add(result.bytes);
            result.path.hash(&mut hasher);
            result.bytes.hash(&mut hasher);
            result.status.hash(&mut hasher);
        }
    }
    RawFingerprint {
        file_count,
        total_bytes,
        hash: format!("{:016x}", hasher.finish()),
    }
}

fn write_manifest_csv(path: &Path, rows: &[FileResult]) -> Result<()> {
    let temp = temp_path_for(path);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    {
        let mut writer = csv::Writer::from_path(&temp)
            .with_context(|| format!("failed to create {}", temp.display()))?;
        writer.write_record([
            "exchange",
            "data_type",
            "symbol",
            "date",
            "url",
            "path",
            "status",
            "http_status",
            "bytes",
            "gzip_ok",
            "header",
            "sample_rows",
            "error",
        ])?;
        for row in rows {
            writer.write_record([
                row.exchange.as_str(),
                row.data_type.as_str(),
                row.symbol.as_str(),
                row.date.as_str(),
                row.url.as_str(),
                row.path.as_str(),
                row.status.as_str(),
                &row.http_status
                    .map(|value| value.to_string())
                    .unwrap_or_default(),
                &row.bytes.to_string(),
                if row.gzip_ok { "True" } else { "False" },
                &row.header.join("|"),
                &row.sample_rows.to_string(),
                row.error.as_str(),
            ])?;
        }
        writer.flush()?;
    }
    replace_file(&temp, path)
}

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let temp = temp_path_for(path);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    {
        let file =
            File::create(&temp).with_context(|| format!("failed to create {}", temp.display()))?;
        serde_json::to_writer_pretty(file, value)
            .with_context(|| format!("failed to write {}", temp.display()))?;
    }
    replace_file(&temp, path)
}

fn replace_file(temp: &Path, path: &Path) -> Result<()> {
    const ATTEMPTS: usize = 20;
    for attempt in 0..ATTEMPTS {
        if path.exists() {
            match fs::remove_file(path) {
                Ok(()) => {}
                Err(err) if attempt + 1 < ATTEMPTS => {
                    sleep_replace_retry(attempt);
                    if !temp.exists() {
                        return Err(err)
                            .with_context(|| format!("failed to remove {}", path.display()));
                    }
                    continue;
                }
                Err(err) => {
                    return Err(err)
                        .with_context(|| format!("failed to remove {}", path.display()));
                }
            }
        }
        match fs::rename(temp, path) {
            Ok(()) => return Ok(()),
            Err(_err) if attempt + 1 < ATTEMPTS => {
                sleep_replace_retry(attempt);
                continue;
            }
            Err(err) => {
                return Err(err).with_context(|| {
                    format!("failed to move {} to {}", temp.display(), path.display())
                });
            }
        }
    }
    bail!(
        "failed to replace {} with {} after retries",
        path.display(),
        temp.display()
    )
}

fn sleep_replace_retry(attempt: usize) {
    let millis = 50 * ((attempt as u64 + 1).min(20));
    thread::sleep(Duration::from_millis(millis));
}

fn temp_path_for(path: &Path) -> PathBuf {
    let filename = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("out");
    path.with_file_name(format!(".{filename}.tmp.{}", std::process::id()))
}

fn sleep_for_attempt(attempt: usize) {
    let delays = [2, 5, 15, 45];
    thread::sleep(Duration::from_secs(delays[attempt.min(delays.len() - 1)]));
}

fn build_client(timeout_seconds: u64) -> Result<Client> {
    Client::builder()
        .timeout(Duration::from_secs(timeout_seconds))
        .connect_timeout(Duration::from_secs(30))
        .pool_max_idle_per_host(0)
        .build()
        .context("failed to build HTTP client")
}

fn free_gb(path: &Path) -> Result<f64> {
    let probe = existing_probe_path(path);
    let bytes = fs2::available_space(&probe)
        .with_context(|| format!("failed to inspect free space for {}", probe.display()))?;
    Ok(bytes as f64 / 1024.0 / 1024.0 / 1024.0)
}

fn existing_probe_path(path: &Path) -> PathBuf {
    let mut probe = path.to_path_buf();
    while !probe.exists() {
        let Some(parent) = probe.parent() else {
            break;
        };
        if parent == probe {
            break;
        }
        probe = parent.to_path_buf();
    }
    probe
}

fn utc_now_string() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, true)
}

pub fn path_string(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_symbols_uppercases_and_dedup_is_stable() {
        let values = dedup(parse_symbol_list("bonk1musdc, BONK1MUSDC,ethusdc"));
        assert_eq!(values, vec!["BONK1MUSDC", "ETHUSDC"]);
    }

    #[test]
    fn raw_path_matches_python_layout() {
        let day = NaiveDate::from_ymd_opt(2026, 5, 10).unwrap();
        let path = raw_path(
            Path::new("data/bonk/v1"),
            DEFAULT_BULLISH_EXCHANGE,
            "trades",
            day,
            "BONK1MUSDC",
        );
        assert_eq!(
            path_string(&path),
            "data/bonk/v1/external/bullish_trades/symbol=BONK1MUSDC/dt=2026-05-10/BONK1MUSDC.csv.gz"
        );
    }
}
