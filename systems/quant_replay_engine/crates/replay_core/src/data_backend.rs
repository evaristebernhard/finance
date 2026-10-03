//! Data-source boundaries for the replay kernel.
//!
//! A backend may use CSV/GZip during migration, Parquet for the local product,
//! or DuckDB/ClickHouse for catalog and institutional deployments. The Runner
//! should consume the resulting ordered event stream, not issue a database
//! query for every market event.

use std::path::{Path, PathBuf};

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::{CanonicalMarketEvent, CanonicalMarketStream, canonical::validate_canonical};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct MarketDataRequest {
    pub symbol: String,
    pub date: String,
    pub include_l2: bool,
    pub l2_batch_size: usize,
    pub l2_max_rows: Option<usize>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub enum MarketDataBackendKind {
    CanonicalFiles,
    Parquet,
    EmbeddedDuckDb,
    ClickHouse,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DatasetDescriptor {
    pub symbol: String,
    pub date: String,
    pub backend: MarketDataBackendKind,
    pub quotes_present: bool,
    pub trades_present: bool,
    pub l2_present: bool,
    pub l2_reconstructible: bool,
    pub l2_status: String,
}

/// Contract between a storage adapter and the deterministic Runner.
///
/// Implementations are allowed to query indexes while opening a run, but the
/// returned iterator must be safe for sequential consumption by the hot path.
pub trait MarketDataBackend {
    type Stream: Iterator<Item = Result<CanonicalMarketEvent>>;

    fn describe(&self, request: &MarketDataRequest) -> Result<DatasetDescriptor>;

    fn open_stream(&self, request: &MarketDataRequest) -> Result<Self::Stream>;
}

/// Compatibility adapter for the current canonical CSV/GZip layout.
///
/// This is intentionally kept behind the same trait that future Parquet and
/// embedded DuckDB adapters will implement.
#[derive(Clone, Debug)]
pub struct CanonicalFilesBackend {
    pub repo_root: PathBuf,
}

impl CanonicalFilesBackend {
    pub fn new(repo_root: impl Into<PathBuf>) -> Self {
        Self {
            repo_root: repo_root.into(),
        }
    }
}

impl MarketDataBackend for CanonicalFilesBackend {
    type Stream = CanonicalMarketStream;

    fn describe(&self, request: &MarketDataRequest) -> Result<DatasetDescriptor> {
        let validation = validate_canonical(
            Path::new(&self.repo_root),
            &request.symbol,
            &request.date,
            &request.date,
        )?;
        let quotes = validation
            .datasets
            .iter()
            .find(|dataset| dataset.dataset == "quote_frame_v1");
        let trades = validation
            .datasets
            .iter()
            .find(|dataset| dataset.dataset == "trade_event_v1");
        let l2 = validation
            .datasets
            .iter()
            .find(|dataset| dataset.dataset == "l2_level_update_v1");

        Ok(DatasetDescriptor {
            symbol: request.symbol.clone(),
            date: request.date.clone(),
            backend: MarketDataBackendKind::CanonicalFiles,
            quotes_present: quotes.is_some_and(|dataset| dataset.exists && dataset.status == "ok"),
            trades_present: trades.is_some_and(|dataset| dataset.exists && dataset.status == "ok"),
            l2_present: l2.is_some_and(|dataset| dataset.exists && dataset.rows > 0),
            l2_reconstructible: l2.is_some_and(|dataset| dataset.quality.reconstructible),
            l2_status: l2
                .map(|dataset| dataset.status.clone())
                .unwrap_or_else(|| "missing".to_string()),
        })
    }

    fn open_stream(&self, request: &MarketDataRequest) -> Result<Self::Stream> {
        crate::stream_canonical_market(
            &self.repo_root,
            &request.symbol,
            &request.date,
            request.include_l2,
            request.l2_batch_size,
            request.l2_max_rows,
        )
    }
}
