# BONK CEX V5 Rust/Python Architecture

Status: 2026-05-13. This is an engineering plan for the next BONK Bullish L2 research pass. It is not a trading rule, not an execution plan, not a sizing rule, and not an alpha claim.

## Goal

Move BONK CEX research from a script-led V3/V4 loop to a contract-led V5 loop:

```text
Rust canonical data products -> Python research probes -> docs and go/no-go decisions
```

The boundary should be simple:

- Rust owns anything that must be deterministic, repeatable, large, or expensive to parse.
- Python owns anything exploratory, visual, model-heavy, or likely to change several times in a day.

This keeps the canonical definitions frozen while preserving the speed of Python research.

## Current Surface

Existing Rust crate:

```text
crates/cex_l2_research
```

Existing Rust binaries:

```text
bonk_bullish_l2_download
bonk_cex_price_context
bonk_cex_l2_report
bonk_cex_research_panel
bonk_cex_model_report
```

Existing Python BONK scripts include:

```text
scripts/bonk_bullish_l2_download.py
scripts/bonk_cex_l2_report.py
scripts/bonk_v3_*.py
scripts/bonk_v4_*.py
```

The current canonical run tag is:

```text
20260513_bullish_l2_basket_price_v1
```

The current research read is that the best BONK object is a `BONK1MUSDT` H4 orderbook state, especially:

```text
depth_high + rv_low
depth_high + rv_low + cv_spread
```

V5 should not reselect this object while changing data definitions. First freeze the canonical labels, panel, and capacity contracts; then rerun the V4 probes against those frozen outputs.

## Ownership Decisions

### Rust Owns

Rust should own download, raw parsing, exact labels, short-horizon labels, panel construction, and deterministic capacity.

These are the Rust responsibilities:

| area | reason | output type |
| --- | --- | --- |
| Bullish/Tardis download | retries, auth handling, file validation, manifesting, fingerprinting | raw `.csv.gz`, manifest CSV, completion JSON |
| Binance kline context | deterministic 1m price-context build and coverage reporting | parquet, quality CSV, summary CSV, completion JSON |
| Raw L2 parsing | large gzip CSV scans, minute aggregation, stable schema | parquet state and quality CSV |
| Timestamp-exact labels | label semantics must be frozen and reproducible | parquet labels |
| Short-horizon labels | 5m/15m/30m labels must use the same exact label engine | parquet labels |
| Research panel | stable join of L2 state, labels, covariance, price context | parquet panel and completion JSON |
| Deterministic capacity | capacity arithmetic should not drift across Python probes | CSV/JSON capacity table |
| Simple controlled diagnostics | low-capacity logistic/bucket sanity checks are useful as smoke tests | CSV/markdown summaries |

Rust should treat Python output as non-canonical. Rust inputs should be raw exchange data, price context, and prior Rust-derived parquet only.

### Python Owns

Python should own exploration, ML, plots, probes, and research narrative generation.

These are the Python responsibilities:

| area | reason | output type |
| --- | --- | --- |
| V3/V4 probes | high iteration rate and changing hypotheses | CSV/JSON/markdown |
| ML experiments | sklearn/pandas iteration is faster than rebuilding Rust models | CSV metrics, plots, reports |
| Plots and figures | visualization ergonomics | PNG/SVG/markdown |
| State taxonomy | clustering and semantic labeling may change often | CSV/markdown |
| Negative controls | many temporary variants, but must read frozen Rust labels/panel | CSV/JSON/markdown |
| Gate ablations | exploratory ranking, feature families, threshold stress | CSV/markdown |
| Notebook-like probes | one-off questions and follow-up diagnostics | append-only research artifacts |

Python scripts should not redefine canonical labels once V5 Rust labels exist. If a Python probe needs a new label family, add it as a proposed Rust label spec first, then run the probe from the Rust output.

## Canonical Data Flow

```text
1. Rust download
   data/bonk/v1/external/bullish_{book_snapshot_25,book_ticker,trades}/...

2. Rust price context
   data/bonk/v1/derived/bonk_cex_price_context/*.parquet

3. Rust L2 state and labels
   data/bonk/v1/derived/bonk_cex_l2_state/*.parquet
   data/bonk/v1/derived/bonk_cex_covariance_state/*.parquet
   data/bonk/v1/derived/bonk_path_labels/*.parquet

4. Rust panel
   data/bonk/v1/derived/bonk_l2_label_context_panel/*.parquet

5. Rust deterministic capacity
   date/bonk_v5_capacity_*.csv
   date/bonk_v5_capacity_*.json

6. Python research probes
   date/bonk_v5_*.csv
   docs/markets/bonk/v1-cex-v5-*.md
```

The key V5 change is that step 3 should include both timestamp-exact H1/H4/H12 labels and exact 5m/15m/30m short-horizon labels. V4 exact-label and short-horizon scripts have already shown the desired behavior; V5 should make those definitions canonical.

## CLI Boundaries

### 1. Download Raw Bullish L2

Existing Rust boundary:

```powershell
cargo run --release -p cex_l2_research --bin bonk_bullish_l2_download -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --from-date 2026-04-29 `
  --to-date 2026-05-12 `
  --symbols BONK1MUSDC,BONK1MUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PENGUUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC,APTUSDC,ARBUSDC,OPUSDC `
  --data-types book_snapshot_25,book_ticker,trades `
  --run-tag 20260513_bullish_l2_basket_price_v1 `
  --workers 4
```

Output contract:

```text
data/bonk/v1/external/bullish_book_snapshot_25/symbol=<SYMBOL>/dt=<YYYY-MM-DD>/<SYMBOL>.csv.gz
data/bonk/v1/external/bullish_book_ticker/symbol=<SYMBOL>/dt=<YYYY-MM-DD>/<SYMBOL>.csv.gz
data/bonk/v1/external/bullish_trades/symbol=<SYMBOL>/dt=<YYYY-MM-DD>/<SYMBOL>.csv.gz
date/bonk_bullish_l2_download_manifest_<run_tag>.csv
date/bonk_bullish_l2_download_completion_<run_tag>.json
```

The manifest must include exchange, data type, symbol, date, path, status, byte count, gzip validation, sampled rows, and error text. Do not print API keys or env contents.

### 2. Build Price Context

Existing Rust boundary:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_price_context -- `
  --data-root data/bonk/v1 `
  --local-kline-dir data/mon_usdc/v1/external/binance_klines `
  --date-dir date `
  --from-date 2026-04-29 `
  --to-date 2026-05-12 `
  --run-tag 20260513_bullish_l2_basket_price_v1 `
  --workers 4
```

Output contract:

```text
data/bonk/v1/derived/bonk_cex_price_context/bonk_cex_price_context_<run_tag>.parquet
date/bonk_v1_cex_price_context_quality_<run_tag>.csv
date/bonk_v1_cex_price_context_summary_<run_tag>.csv
date/bonk_v1_cex_price_context_completion_<run_tag>.json
```

Required parquet semantics:

- One row per minute timestamp.
- Current and trailing context columns are t-and-earlier only.
- Future context columns, if present in downstream panels, must be explicitly labeled as future outcomes and not used as model features.

### 3. Build L2 State And Labels

Existing Rust boundary:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_l2_report -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --doc-dir docs/markets/bonk `
  --run-tag 20260513_bullish_l2_basket_price_v1 `
  --symbols BONK1MUSDC,BONK1MUSDT,BTCUSDC,ETHUSDC,SOLUSDC,DOGEUSDC,PENGUUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,SUIUSDC,APTUSDC,ARBUSDC,OPUSDC `
  --label-symbols BONK1MUSDC,BONK1MUSDT `
  --horizons-hours 1,4,12 `
  --barriers-bps 50,100,200,300 `
  --workers 4
```

V5 target boundary:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_l2_report -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --doc-dir docs/markets/bonk `
  --run-tag 20260513_bullish_l2_basket_price_v5 `
  --symbols <basket> `
  --label-symbols BONK1MUSDC,BONK1MUSDT `
  --label-specs direction_h1_h4_100,movement_h1_h4_h12_50_100,short_5m_15m_30m_20_30 `
  --label-mode exact `
  --workers 4
```

Output contract:

```text
data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_<run_tag>.parquet
data/bonk/v1/derived/bonk_cex_covariance_state/bonk_cex_covariance_state_<run_tag>.parquet
data/bonk/v1/derived/bonk_path_labels/bonk_path_labels_<run_tag>.parquet
date/bonk_v1_cex_l2_quality_<run_tag>.csv
date/bonk_v1_cex_l2_summary_<run_tag>.csv
date/bonk_v1_cex_l2_factor_tests_<run_tag>.csv
date/bonk_v1_cex_l2_stability_<run_tag>.csv
date/bonk_v1_cex_l2_completion_<run_tag>.json
docs/markets/bonk/v1-cex-l2-report.md
```

Required label columns:

```text
run_tag
timestamp_utc
timestamp_us
symbol
asset
horizon_minutes
horizon_hours
barrier_bps
label_family
label_mode
price_per_token
future_timestamp_us
future_price_per_token
future_return_bps
mfe_up_bps
mae_down_bps
path_width_bps
barrier_first_hit
label_status
observed_future_minutes
expected_future_minutes
missing_future_minutes
```

Required `barrier_first_hit` values:

```text
upper_first
lower_first
both_or_ambiguous
none
future_missing
bad_start_price
```

Exact-label rule:

- `future_return_bps` uses the exact target timestamp if available.
- If the exact endpoint is missing, use a documented status rather than silently shifting by row count.
- MFE/MAE and first-hit are computed over observed future timestamps inside the horizon.
- Missing future minutes are counted and carried into the label row.

Short-horizon rule:

- `5m`, `15m`, and `30m` labels use `horizon_minutes`, not fractional hours as the primary key.
- The primary short barriers are `20` and `30` bps.
- Short labels are decay/capacity diagnostics first; they should not replace H4 state validation.

### 4. Build Research Panel

Existing Rust boundary:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_research_panel -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --run-tag 20260513_bullish_l2_basket_price_v1 `
  --l2-run-tag 20260513_bullish_l2_basket_price_v1 `
  --price-context-run-tag 20260513_bullish_l2_basket_price_v1
```

Output contract:

```text
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_<run_tag>.parquet
date/bonk_v1_controlled_factor_tests_<run_tag>.csv
date/bonk_v1_research_panel_completion_<run_tag>.json
```

Required panel key:

```text
symbol, timestamp_us, horizon_minutes, barrier_bps, label_family
```

Panel joins should be left-biased toward labels: every valid label row should either produce one panel row or a documented missing-state count in the completion JSON. Duplicate keys should be counted and treated as a failure unless explicitly allowed for a new label family.

### 5. Build Deterministic Capacity

V5 should move the deterministic part of `scripts/bonk_v4_orderbook_capacity.py` into Rust.

Proposed Rust boundary:

```powershell
cargo run --release -p cex_l2_research --bin bonk_cex_capacity -- `
  --data-root data/bonk/v1 `
  --date-dir date `
  --run-tag 20260513_bullish_l2_basket_price_v5 `
  --panel data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v5.parquet `
  --l2-state data/bonk/v1/derived/bonk_cex_l2_state/bonk_cex_l2_state_20260513_bullish_l2_basket_price_v5.parquet `
  --quote-buckets 5,10,25,50,100,250,500,1000 `
  --fee-bps 2.0
```

Output contract:

```text
date/bonk_v5_capacity_<run_tag>.csv
date/bonk_v5_capacity_<run_tag>.json
date/bonk_v5_capacity_completion_<run_tag>.json
```

Required capacity columns:

```text
run_tag
gate_id
gate_family
symbol
horizon_minutes
barrier_bps
fold
rows
selected_rows
selected_share
gross_median_bps
future_return_median_bps
lower_first_rate
mfe_median_bps
mae_median_bps
path_width_median_bps
depth_level
quote_bucket
displayed_depth_coverage
p10_displayed_depth
p50_displayed_depth
p90_depth_participation
spread_cost_bps
fee_bps
slippage_stress_bps
stress_net_median_bps
capacity_status
status_reason
```

Rust should not decide to trade. It should only compute the deterministic displayed-depth and stress-net table so every Python report reads the same capacity numbers.

### 6. Run Python Probes

Python probes should accept explicit input paths and output tags. New V5 scripts should avoid hard-coding V4 input paths except as defaults.

Recommended boundary:

```powershell
python scripts/bonk_v5_orderbook_probe.py `
  --panel data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v5.parquet `
  --capacity date/bonk_v5_capacity_20260513_bullish_l2_basket_price_v5.csv `
  --date-dir date `
  --doc-dir docs/markets/bonk `
  --out-tag 20260513_bullish_l2_basket_price_v5
```

Python output contract:

```text
date/bonk_v5_<probe>_<out_tag>_*.csv
date/bonk_v5_<probe>_<out_tag>_completion.json
docs/markets/bonk/v1-cex-v5-<probe>.md
docs/markets/bonk/figures/bonk_v5_<probe>_<out_tag>_*.png
```

Python completion JSON should record:

```text
input panel path
input capacity path
input run tag
out tag
generated_at_utc
row counts
selected symbols
selected horizons
selected barriers
output paths
```

## Naming Rules

Use `run_tag` for canonical Rust data products and `out_tag` for Python research outputs.

Recommended next canonical tag:

```text
20260513_bullish_l2_basket_price_v5
```

Recommended labels:

```text
label_family=direction
label_family=movement
label_family=short_microstructure
label_mode=exact
```

Recommended output stem:

```text
bonk_v5_<component>_<run_tag>
```

Do not overwrite V3/V4 outputs. V5 outputs should be append-only unless a command uses the same tag intentionally.

## Small Rust TODO Skeleton

The lowest-risk Rust change is not a broad refactor. Add a small label contract layer inside `crates/cex_l2_research` and keep the existing binary names.

Proposed files:

```text
crates/cex_l2_research/src/labels.rs
crates/cex_l2_research/src/capacity.rs
crates/cex_l2_research/src/bin/bonk_cex_capacity.rs
```

Proposed `labels.rs` surface:

```rust
pub struct LabelSpec {
    pub family: String,
    pub horizons_minutes: Vec<u64>,
    pub barriers_bps: Vec<u64>,
}

pub struct ExactLabelInput {
    pub timestamp_us: u64,
    pub price_per_token: f64,
}

pub struct ExactLabelRow {
    pub horizon_minutes: u64,
    pub barrier_bps: u64,
    pub label_family: String,
    pub label_mode: String,
    pub future_return_bps: Option<f64>,
    pub mfe_up_bps: Option<f64>,
    pub mae_down_bps: Option<f64>,
    pub path_width_bps: Option<f64>,
    pub barrier_first_hit: String,
    pub label_status: String,
    pub observed_future_minutes: u64,
    pub expected_future_minutes: u64,
    pub missing_future_minutes: u64,
}

pub fn build_exact_labels_for_symbol(
    run_tag: &str,
    symbol: &str,
    prices: &[ExactLabelInput],
    specs: &[LabelSpec],
) -> anyhow::Result<Vec<ExactLabelRow>>;
```

Proposed `capacity.rs` surface:

```rust
pub struct CapacityConfig {
    pub run_tag: String,
    pub panel_path: PathBuf,
    pub l2_state_path: PathBuf,
    pub quote_buckets: Vec<f64>,
    pub fee_bps: f64,
}

pub fn run_capacity(config: &CapacityConfig) -> anyhow::Result<CapacitySummary>;
```

This is small enough to add behind tests without changing the existing downloader or parser. The first implementation can keep old defaults and add exact label specs as an opt-in flag. Once the V5 outputs match the V4 Python audits, flip `--label-mode exact` to the default.

## Validation Checklist

Before using V5 outputs for new research:

- `cargo fmt --manifest-path Cargo.toml`
- `cargo test -p cex_l2_research`
- Download completion JSON has zero errors or documented unavailable files.
- L2 quality CSV has no unexpected schema or gzip parse failures.
- Label completion JSON reports duplicate panel keys as zero.
- Exact labels reproduce the V4 exact-label audit within documented expected differences.
- Short-horizon label row counts match feasible observed-minute coverage.
- Capacity output reproduces the V4 capacity table directionally before Python probes use it.

## Key Decisions

1. Rust is the canonical data and label engine.
2. Python is the exploratory research and reporting engine.
3. Timestamp-exact labels should be moved out of `scripts/bonk_v4_exact_label_audit.py` and into Rust.
4. Short-horizon labels should be moved out of `scripts/bonk_v4_short_horizon_orderbook.py` and into Rust.
5. Deterministic displayed-depth capacity should move out of `scripts/bonk_v4_orderbook_capacity.py` and into Rust.
6. Python probes should consume explicit Rust parquet/CSV inputs and write append-only V5 artifacts.
7. The current H4 BONK1MUSDT state should stay frozen while V5 changes data definitions.
8. More L2 collection should wait until the frozen state survives the V5 exact-label, short-horizon, negative-control, and capacity rerun.
