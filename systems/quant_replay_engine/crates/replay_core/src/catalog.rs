use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

const CCUSDT_DATA_ROOT: &str = "data/ccusdt/v1";
const CATALOG_PATH: &str = "data/catalog/ccusdt/v1/catalog.json";

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Catalog {
    pub schema_version: String,
    pub symbol: String,
    pub generated_by: String,
    pub data_root: String,
    pub catalog_path: String,
    pub datasets: Vec<CatalogDataset>,
    pub feature_sidecars: Vec<FeatureSidecar>,
    pub legacy_research_artifacts: Vec<LegacyResearchArtifact>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CatalogDataset {
    pub dataset_id: String,
    pub venue: String,
    pub symbol: String,
    pub data_type: String,
    pub role: String,
    pub schema_id: String,
    pub path_glob: String,
    pub file_count: usize,
    pub byte_size: u64,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub dates: Vec<String>,
    pub missing_dates: Vec<String>,
    pub expectation_status: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct FeatureSidecar {
    pub dataset_id: String,
    pub role: String,
    pub schema_id: String,
    pub path_glob: String,
    pub run_tag: String,
    pub symbol: String,
    pub dates: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct LegacyResearchArtifact {
    pub path: String,
    pub classification: String,
}

#[derive(Clone, Debug)]
struct RawDatasetSpec {
    data_dir: &'static str,
    data_type: &'static str,
    role: &'static str,
    schema_id: &'static str,
    expected_start: &'static str,
    expected_end: &'static str,
    required: bool,
}

pub fn default_catalog_path(repo_root: &Path) -> PathBuf {
    repo_root.join(CATALOG_PATH)
}

pub fn scan_catalog(repo_root: &Path, symbol: &str) -> Result<Catalog> {
    let specs = [
        RawDatasetSpec {
            data_dir: "bullish_book_ticker",
            data_type: "book_ticker",
            role: "market_truth",
            schema_id: "quote_frame_v1",
            expected_start: "2026-04-29",
            expected_end: "2026-05-18",
            required: true,
        },
        RawDatasetSpec {
            data_dir: "bullish_trades",
            data_type: "trades",
            role: "market_truth",
            schema_id: "trade_event_v1",
            expected_start: "2026-04-29",
            expected_end: "2026-05-18",
            required: true,
        },
        RawDatasetSpec {
            data_dir: "bullish_incremental_book_L2",
            data_type: "incremental_book_L2",
            role: "market_truth",
            schema_id: "l2_level_update_v1",
            expected_start: "2026-04-29",
            expected_end: "2026-05-18",
            required: true,
        },
        RawDatasetSpec {
            data_dir: "bullish_book_snapshot_25",
            data_type: "book_snapshot_25",
            role: "optional_depth_reference",
            schema_id: "book_snapshot_25_raw",
            expected_start: "2026-04-29",
            expected_end: "2026-05-15",
            required: false,
        },
    ];

    let datasets = specs
        .iter()
        .map(|spec| scan_raw_dataset(repo_root, symbol, spec))
        .collect::<Result<Vec<_>>>()?;

    Ok(Catalog {
        schema_version: "catalog_v1".to_string(),
        symbol: symbol.to_string(),
        generated_by: "quant_replay_cli catalog scan".to_string(),
        data_root: CCUSDT_DATA_ROOT.to_string(),
        catalog_path: CATALOG_PATH.to_string(),
        datasets,
        feature_sidecars: scan_feature_sidecars(repo_root, symbol)?,
        legacy_research_artifacts: scan_legacy_research_artifacts(repo_root)?,
    })
}

pub fn write_catalog(repo_root: &Path, catalog: &Catalog) -> Result<PathBuf> {
    let path = default_catalog_path(repo_root);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let json = serde_json::to_string_pretty(catalog)?;
    fs::write(&path, json)?;
    Ok(path)
}

fn scan_raw_dataset(
    repo_root: &Path,
    symbol: &str,
    spec: &RawDatasetSpec,
) -> Result<CatalogDataset> {
    let root = repo_root
        .join(CCUSDT_DATA_ROOT)
        .join("external")
        .join(spec.data_dir)
        .join(format!("symbol={symbol}"));
    let mut dates = Vec::new();
    let mut byte_size = 0u64;
    if root.exists() {
        for entry in fs::read_dir(&root).with_context(|| format!("scan {}", root.display()))? {
            let entry = entry?;
            if !entry.file_type()?.is_dir() {
                continue;
            }
            let name = entry.file_name().to_string_lossy().to_string();
            let Some(date) = name.strip_prefix("dt=") else {
                continue;
            };
            let file = entry.path().join(format!("{symbol}.csv.gz"));
            if file.exists() {
                dates.push(date.to_string());
                byte_size += file.metadata()?.len();
            }
        }
    }
    dates.sort();
    let start_date = dates.first().cloned();
    let end_date = dates.last().cloned();
    let missing_dates = if let (Some(start), Some(end)) = (&start_date, &end_date) {
        missing_dates(start, end, &dates)?
    } else {
        Vec::new()
    };
    let expected = date_range(spec.expected_start, spec.expected_end)?;
    let expected_missing: Vec<String> = expected
        .iter()
        .filter(|date| !dates.contains(date))
        .cloned()
        .collect();
    let expectation_status = if expected_missing.is_empty() {
        "matches_expected_coverage".to_string()
    } else if spec.required {
        format!(
            "required_missing_expected_dates:{}",
            expected_missing.join("|")
        )
    } else {
        format!(
            "optional_missing_expected_dates:{}",
            expected_missing.join("|")
        )
    };

    Ok(CatalogDataset {
        dataset_id: format!("cex.bullish.{symbol}.{}", spec.data_type),
        venue: "bullish".to_string(),
        symbol: symbol.to_string(),
        data_type: spec.data_type.to_string(),
        role: spec.role.to_string(),
        schema_id: spec.schema_id.to_string(),
        path_glob: format!(
            "{CCUSDT_DATA_ROOT}/external/{}/symbol={symbol}/dt=*/{symbol}.csv.gz",
            spec.data_dir
        ),
        file_count: dates.len(),
        byte_size,
        start_date,
        end_date,
        dates,
        missing_dates,
        expectation_status,
    })
}

fn scan_feature_sidecars(repo_root: &Path, symbol: &str) -> Result<Vec<FeatureSidecar>> {
    let root = repo_root
        .join(CCUSDT_DATA_ROOT)
        .join("derived")
        .join("ccusdt_v1_fixed_event_factor_panel");
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    for run in fs::read_dir(&root)? {
        let run = run?;
        if !run.file_type()?.is_dir() {
            continue;
        }
        let run_name = run.file_name().to_string_lossy().to_string();
        let Some(run_tag) = run_name.strip_prefix("run_tag=") else {
            continue;
        };
        let symbol_root = run.path().join(format!("symbol={symbol}"));
        let mut dates = Vec::new();
        if symbol_root.exists() {
            for entry in fs::read_dir(&symbol_root)? {
                let entry = entry?;
                if entry.file_type()?.is_dir() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    if let Some(date) = name.strip_prefix("dt=") {
                        dates.push(date.to_string());
                    }
                }
            }
        }
        dates.sort();
        out.push(FeatureSidecar {
            dataset_id: format!("feature.ccusdt.fixed_event_factor_panel.{run_tag}"),
            role: "feature_sidecar_reference".to_string(),
            schema_id: "feature_sidecar_v1".to_string(),
            path_glob: format!(
                "{CCUSDT_DATA_ROOT}/derived/ccusdt_v1_fixed_event_factor_panel/run_tag={run_tag}/symbol={symbol}/dt=*/part_*.csv"
            ),
            run_tag: run_tag.to_string(),
            symbol: symbol.to_string(),
            dates,
        });
    }
    out.sort_by(|a, b| a.run_tag.cmp(&b.run_tag));
    Ok(out)
}

fn scan_legacy_research_artifacts(repo_root: &Path) -> Result<Vec<LegacyResearchArtifact>> {
    let root = repo_root.join("date");
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut out = Vec::new();
    for entry in fs::read_dir(&root)? {
        let entry = entry?;
        if !entry.file_type()?.is_file() {
            continue;
        }
        let name = entry.file_name().to_string_lossy().to_string();
        if !name.starts_with("ccusdt_v1_tfi_") {
            continue;
        }
        out.push(LegacyResearchArtifact {
            path: format!("date/{name}"),
            classification: classify_legacy_artifact(&name).to_string(),
        });
    }
    out.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(out)
}

fn classify_legacy_artifact(name: &str) -> &'static str {
    const LABEL_HINTS: &[&str] = &[
        "oos",
        "pnl",
        "return",
        "profit",
        "loss",
        "mfe",
        "mae",
        "path",
        "daily",
        "summary",
        "scorecard",
        "events",
        "clipped",
        "strategy",
        "sizing",
        "exit",
        "decay",
        "watcher",
        "manager",
    ];
    if LABEL_HINTS.iter().any(|hint| name.contains(hint)) {
        "research_label_v1"
    } else {
        "feature_sidecar_v1_candidate"
    }
}

fn missing_dates(start: &str, end: &str, dates: &[String]) -> Result<Vec<String>> {
    let present: BTreeSet<&str> = dates.iter().map(String::as_str).collect();
    Ok(date_range(start, end)?
        .into_iter()
        .filter(|date| !present.contains(date.as_str()))
        .collect())
}

pub fn date_range(start: &str, end: &str) -> Result<Vec<String>> {
    let mut current = parse_date(start)?;
    let end = parse_date(end)?;
    let mut out = Vec::new();
    while current <= end {
        out.push(format!(
            "{:04}-{:02}-{:02}",
            current.0, current.1, current.2
        ));
        current = next_date(current)?;
    }
    Ok(out)
}

fn parse_date(date: &str) -> Result<(i32, u32, u32)> {
    let parts: Vec<&str> = date.split('-').collect();
    anyhow::ensure!(parts.len() == 3, "bad date: {date}");
    let y = parts[0].parse::<i32>()?;
    let m = parts[1].parse::<u32>()?;
    let d = parts[2].parse::<u32>()?;
    anyhow::ensure!((1..=12).contains(&m), "bad month in date: {date}");
    anyhow::ensure!(
        (1..=days_in_month(y, m)).contains(&d),
        "bad day in date: {date}"
    );
    Ok((y, m, d))
}

fn next_date((y, m, d): (i32, u32, u32)) -> Result<(i32, u32, u32)> {
    let days = days_in_month(y, m);
    if d < days {
        Ok((y, m, d + 1))
    } else if m < 12 {
        Ok((y, m + 1, 1))
    } else {
        Ok((y + 1, 1, 1))
    }
}

fn days_in_month(y: i32, m: u32) -> u32 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(y) => 29,
        2 => 28,
        _ => 0,
    }
}

fn is_leap_year(y: i32) -> bool {
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn date_range_crosses_month() {
        assert_eq!(
            date_range("2026-04-29", "2026-05-02").unwrap(),
            vec!["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02"]
        );
    }

    #[test]
    fn classifies_future_like_artifacts_as_research_label() {
        assert_eq!(
            classify_legacy_artifact("ccusdt_v1_tfi_current_oos_unit_entries.csv"),
            "research_label_v1"
        );
        assert_eq!(
            classify_legacy_artifact("ccusdt_v1_tfi_membership_20260518.csv"),
            "feature_sidecar_v1_candidate"
        );
    }

    #[test]
    fn scan_catalog_detects_coverage_and_missing_dates() {
        let root = temp_repo("catalog_scan");
        for date in ["2026-04-29", "2026-05-01"] {
            let file = root
                .join(CCUSDT_DATA_ROOT)
                .join("external")
                .join("bullish_book_ticker")
                .join("symbol=CCUSDT")
                .join(format!("dt={date}"))
                .join("CCUSDT.csv.gz");
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            fs::write(file, "fixture").unwrap();
        }
        let catalog = scan_catalog(&root, "CCUSDT").unwrap();
        let ticker = catalog
            .datasets
            .iter()
            .find(|dataset| dataset.data_type == "book_ticker")
            .unwrap();
        assert_eq!(ticker.file_count, 2);
        assert_eq!(ticker.start_date.as_deref(), Some("2026-04-29"));
        assert_eq!(ticker.end_date.as_deref(), Some("2026-05-01"));
        assert_eq!(ticker.missing_dates, vec!["2026-04-30"]);
    }

    fn temp_repo(name: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("ccusdt_replay_{name}_{nonce}"));
        fs::create_dir_all(&path).unwrap();
        path
    }
}
