#!/usr/bin/env python
"""CCUSDT factor method sweep.

Research-only diagnostics. This consumes the fixed event-orderbook factor
panel that is already built from local Bullish/Tardis files. It does not
download data, modify raw files, infer queue-position fill evidence, or emit
trading advice.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl
from pandas.errors import PerformanceWarning
from scipy.stats import spearmanr
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.feature_selection import mutual_info_regression
from sklearn.impute import SimpleImputer
from sklearn.linear_model import HuberRegressor, LogisticRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=PerformanceWarning)


GUARDRAIL = "research_only_diagnostics_no_trading_advice_no_execution_recommendation_no_alpha_claim"
SOURCE_RUN_TAG = "20260517_ccusdt_fixed_factors_v3"
RUN_TAG = "20260517_ccusdt_method_sweep_v1"
EPS = 1e-12
US_PER_SECOND = 1_000_000

META_COLS = [
    "run_tag",
    "date",
    "symbol",
    "timestamp",
    "local_timestamp",
    "event_index",
    "is_snapshot_batch",
    "factor_eligible",
    "execute_cancel_confidence",
    "batch_rows",
    "best_bid_price",
    "best_bid_amount",
    "best_ask_price",
    "best_ask_amount",
    "mid_price",
    "spread_bps",
    "microprice",
    "microprice_dev_bps",
    "trade_window_count",
    "trade_notional_quote",
]

FEATURE_COLS = [
    "batch_rows",
    "noop_updates",
    "create_updates",
    "replenish_updates",
    "decrease_updates",
    "remove_updates",
    "best_bid_amount",
    "best_ask_amount",
    "spread_bps",
    "microprice_dev_bps",
    "bid_levels",
    "ask_levels",
    "bid_depth_1",
    "ask_depth_1",
    "bid_depth_2",
    "ask_depth_2",
    "bid_depth_3",
    "ask_depth_3",
    "bid_depth_5",
    "ask_depth_5",
    "bid_depth_10",
    "ask_depth_10",
    "bid_depth_25",
    "ask_depth_25",
    "queue_imbalance_1",
    "queue_imbalance_5",
    "queue_imbalance_25",
    "limit_add_bid_amount",
    "limit_add_ask_amount",
    "replenish_bid_amount",
    "replenish_ask_amount",
    "decrease_bid_amount",
    "decrease_ask_amount",
    "remove_bid_amount",
    "remove_ask_amount",
    "depletion_bid_amount",
    "depletion_ask_amount",
    "execute_bid_amount",
    "execute_ask_amount",
    "cancel_bid_amount",
    "cancel_ask_amount",
    "event_matched_rate",
    "trade_window_count",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "trade_arrival_alignment",
    "ofi_l1_raw",
    "ofi_l1_depth_norm",
    "mlofi_raw_l1",
    "mlofi_raw_l2",
    "mlofi_raw_l3",
    "mlofi_raw_l5",
    "mlofi_raw_l10",
    "mlofi_raw_l25",
    "mlofi_norm_l1",
    "mlofi_norm_l2",
    "mlofi_norm_l3",
    "mlofi_norm_l5",
    "mlofi_norm_l10",
    "mlofi_norm_l25",
    "mlofi_roll10_l1",
    "mlofi_roll10_l2",
    "mlofi_roll10_l3",
    "mlofi_roll10_l5",
    "mlofi_roll10_l10",
    "mlofi_roll10_l25",
    "queue_depletion_intensity",
    "replenish_intensity",
    "cancellation_withdrawal_intensity",
    "liquidity_shock_score",
]


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def panel_run_root(self) -> Path:
        return self.panel_root / f"run_tag={self.source_run_tag}" / "symbol=CCUSDT"

    @property
    def quality_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_quality_{self.run_tag}.csv"

    @property
    def target_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_targets_{self.run_tag}.csv"

    @property
    def single_factor_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_single_factor_{self.run_tag}.csv"

    @property
    def stability_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_stability_{self.run_tag}.csv"

    @property
    def negative_controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_negative_controls_{self.run_tag}.csv"

    @property
    def model_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_models_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / "v1-factor-method-sweep.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a broad CCUSDT factor method sweep.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--event-horizons", default="1,5,10,25,70,250,500")
    parser.add_argument("--time-horizons-sec", default="10,60,300,900")
    parser.add_argument("--max-stat-rows", type=int, default=220_000)
    parser.add_argument("--max-mi-rows", type=int, default=30_000)
    parser.add_argument("--max-mi-pairs", type=int, default=160)
    parser.add_argument("--max-model-rows", type=int, default=120_000)
    parser.add_argument("--top-control-pairs", type=int, default=60)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--skip-models", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return repo_root() / path


def parse_ints(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if text:
            values.append(int(text))
    if not values:
        raise ValueError("expected at least one horizon")
    return values


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle), [])


def present_usecols(first_csv: Path, requested: Iterable[str]) -> list[str]:
    header = set(csv_header(first_csv))
    return [col for col in requested if col in header]


def discover_panel_files(paths: Paths) -> list[Path]:
    files = sorted(paths.panel_run_root.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no panel CSV files found under {paths.panel_run_root}")
    return files


def load_panel(paths: Paths) -> tuple[pd.DataFrame, list[str]]:
    files = discover_panel_files(paths)
    requested = list(dict.fromkeys([*META_COLS, *FEATURE_COLS]))
    usecols = present_usecols(files[0], requested)
    pattern = str(paths.panel_run_root / "dt=*" / "*.csv")
    print(f"loading panel files={len(files)} columns={len(usecols)}", flush=True)
    lf = pl.scan_csv(
        pattern,
        infer_schema_length=1000,
        null_values=["", "NaN", "nan", "NA"],
        ignore_errors=True,
    ).select(usecols)
    frame = lf.collect(streaming=True).sort(["date", "event_index"])
    df = frame.to_pandas()
    del frame
    df["date"] = df["date"].astype(str)
    usable_features = [col for col in FEATURE_COLS if col in df.columns]
    for col in usable_features:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    for col in [
        "event_index",
        "local_timestamp",
        "timestamp",
        "batch_rows",
        "mid_price",
        "best_bid_price",
        "best_ask_price",
        "best_bid_amount",
        "best_ask_amount",
        "spread_bps",
        "microprice_dev_bps",
        "trade_window_count",
        "trade_notional_quote",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df, usable_features


def add_labels(
    df: pd.DataFrame,
    event_horizons: list[int],
    time_horizons_sec: list[int],
) -> tuple[pd.DataFrame, list[str]]:
    target_cols: list[str] = []
    n = len(df)
    new_cols: dict[str, np.ndarray] = {
        "mid_change_prev": np.zeros(n, dtype=bool),
        "quote_change_prev": np.zeros(n, dtype=bool),
        "top_size_change_prev": np.zeros(n, dtype=bool),
        "gap_sec": np.full(n, np.nan, dtype="float64"),
    }
    for horizon in event_horizons:
        new_cols[f"fwd_event_{horizon}_bps"] = np.full(n, np.nan, dtype="float64")
        new_cols[f"past_event_{horizon}_bps"] = np.full(n, np.nan, dtype="float64")
        target_cols.append(f"fwd_event_{horizon}_bps")
    for seconds in time_horizons_sec:
        new_cols[f"fwd_time_{seconds}s_bps"] = np.full(n, np.nan, dtype="float64")
        new_cols[f"past_time_{seconds}s_bps"] = np.full(n, np.nan, dtype="float64")
        target_cols.append(f"fwd_time_{seconds}s_bps")

    for date, idx in df.groupby("date", sort=False).groups.items():
        pos = np.asarray(idx)
        mids = df.loc[pos, "mid_price"].to_numpy(dtype="float64")
        times = df.loc[pos, "local_timestamp"].to_numpy(dtype="float64")
        bids = df.loc[pos, "best_bid_price"].to_numpy(dtype="float64")
        asks = df.loc[pos, "best_ask_price"].to_numpy(dtype="float64")
        bid_amt = df.loc[pos, "best_bid_amount"].to_numpy(dtype="float64")
        ask_amt = df.loc[pos, "best_ask_amount"].to_numpy(dtype="float64")

        if len(pos) <= 1:
            continue

        prev_mid = np.r_[np.nan, mids[:-1]]
        prev_bid = np.r_[np.nan, bids[:-1]]
        prev_ask = np.r_[np.nan, asks[:-1]]
        prev_bid_amt = np.r_[np.nan, bid_amt[:-1]]
        prev_ask_amt = np.r_[np.nan, ask_amt[:-1]]
        new_cols["mid_change_prev"][pos] = np.isfinite(prev_mid) & (np.abs(mids - prev_mid) > EPS)
        new_cols["quote_change_prev"][pos] = (
            np.isfinite(prev_bid)
            & np.isfinite(prev_ask)
            & ((np.abs(bids - prev_bid) > EPS) | (np.abs(asks - prev_ask) > EPS))
        )
        new_cols["top_size_change_prev"][pos] = (
            np.isfinite(prev_bid_amt)
            & np.isfinite(prev_ask_amt)
            & ((np.abs(bid_amt - prev_bid_amt) > EPS) | (np.abs(ask_amt - prev_ask_amt) > EPS))
        )
        new_cols["gap_sec"][pos[1:]] = np.diff(times) / US_PER_SECOND

        for horizon in event_horizons:
            fwd = np.full(len(pos), np.nan)
            past = np.full(len(pos), np.nan)
            if len(pos) > horizon:
                fwd[:-horizon] = 10_000.0 * np.log(
                    np.maximum(mids[horizon:], EPS) / np.maximum(mids[:-horizon], EPS)
                )
                past[horizon:] = 10_000.0 * np.log(
                    np.maximum(mids[horizon:], EPS) / np.maximum(mids[:-horizon], EPS)
                )
            fwd_col = f"fwd_event_{horizon}_bps"
            past_col = f"past_event_{horizon}_bps"
            new_cols[fwd_col][pos] = fwd
            new_cols[past_col][pos] = past

        for seconds in time_horizons_sec:
            fwd = np.full(len(pos), np.nan)
            past = np.full(len(pos), np.nan)
            fwd_idx = np.searchsorted(times, times + seconds * US_PER_SECOND, side="left")
            valid = fwd_idx < len(pos)
            fwd[valid] = 10_000.0 * np.log(
                np.maximum(mids[fwd_idx[valid]], EPS) / np.maximum(mids[valid], EPS)
            )
            past_idx = np.searchsorted(times, times - seconds * US_PER_SECOND, side="right") - 1
            valid_past = past_idx >= 0
            past[valid_past] = 10_000.0 * np.log(
                np.maximum(mids[valid_past], EPS) / np.maximum(mids[past_idx[valid_past]], EPS)
            )
            fwd_col = f"fwd_time_{seconds}s_bps"
            past_col = f"past_time_{seconds}s_bps"
            new_cols[fwd_col][pos] = fwd
            new_cols[past_col][pos] = past

    labels = pd.DataFrame(new_cols, index=df.index)
    return pd.concat([df, labels], axis=1), target_cols


def longest_true_run(mask: np.ndarray, times: np.ndarray) -> tuple[int, float]:
    if len(mask) == 0:
        return 0, 0.0
    best_len = 1
    best_sec = 0.0
    start = 0
    for i in range(1, len(mask)):
        if not mask[i]:
            run_len = i - start
            if run_len > best_len:
                best_len = run_len
                best_sec = max(0.0, (times[i - 1] - times[start]) / US_PER_SECOND)
            start = i
    run_len = len(mask) - start
    if run_len > best_len:
        best_len = run_len
        best_sec = max(0.0, (times[-1] - times[start]) / US_PER_SECOND)
    return int(best_len), float(best_sec)


def quality_rows(df: pd.DataFrame, target_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, g in df.groupby("date", sort=True):
        quote_same = ~g["quote_change_prev"].fillna(False).to_numpy(bool)
        mid_same = ~g["mid_change_prev"].fillna(False).to_numpy(bool)
        times = g["local_timestamp"].to_numpy(dtype="float64")
        longest_quote_frames, longest_quote_seconds = longest_true_run(quote_same, times)
        longest_mid_frames, longest_mid_seconds = longest_true_run(mid_same, times)
        row: dict[str, object] = {
            "run_tag": RUN_TAG,
            "source_run_tag": g["run_tag"].iloc[0] if "run_tag" in g else "",
            "date": date,
            "rows": len(g),
            "snapshot_rate": finite_mean(g["is_snapshot_batch"].astype(float)) if "is_snapshot_batch" in g else np.nan,
            "factor_eligible_rate": finite_mean(g["factor_eligible"].astype(float)) if "factor_eligible" in g else np.nan,
            "distinct_mid": int(g["mid_price"].nunique(dropna=True)),
            "distinct_quote_pairs": int(g[["best_bid_price", "best_ask_price"]].drop_duplicates().shape[0]),
            "mid_change_rate": finite_mean(g["mid_change_prev"].astype(float)),
            "quote_change_rate": finite_mean(g["quote_change_prev"].astype(float)),
            "top_size_change_rate": finite_mean(g["top_size_change_prev"].astype(float)),
            "trade_present_rate": finite_mean((g["trade_window_count"].fillna(0) > 0).astype(float)),
            "gap_sec_p50": finite_quantile(g["gap_sec"], 0.50),
            "gap_sec_p95": finite_quantile(g["gap_sec"], 0.95),
            "longest_quote_run_frames": longest_quote_frames,
            "longest_quote_run_seconds": longest_quote_seconds,
            "longest_mid_run_frames": longest_mid_frames,
            "longest_mid_run_seconds": longest_mid_seconds,
            "guardrail": GUARDRAIL,
        }
        for target in target_cols:
            vals = g[target].to_numpy(dtype="float64")
            valid = np.isfinite(vals)
            row[f"{target}_valid_rows"] = int(valid.sum())
            row[f"{target}_nonzero_rate"] = float((np.abs(vals[valid]) > EPS).mean()) if valid.any() else np.nan
            row[f"{target}_abs_p95"] = float(np.nanpercentile(np.abs(vals[valid]), 95)) if valid.any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def target_rows(df: pd.DataFrame, target_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for target in target_cols:
        vals = df[target].to_numpy(dtype="float64")
        valid = np.isfinite(vals)
        nonzero = valid & (np.abs(vals) > EPS)
        rows.append(
            {
                "run_tag": RUN_TAG,
                "target": target,
                "valid_rows": int(valid.sum()),
                "nonzero_rows": int(nonzero.sum()),
                "nonzero_rate": float(nonzero.sum() / valid.sum()) if valid.any() else np.nan,
                "mean_bps": finite_mean(vals[valid]),
                "abs_mean_bps": finite_mean(np.abs(vals[valid])),
                "abs_p50_bps": finite_quantile(vals_abs(vals[valid]), 0.50),
                "abs_p90_bps": finite_quantile(vals_abs(vals[valid]), 0.90),
                "abs_p99_bps": finite_quantile(vals_abs(vals[valid]), 0.99),
                "positive_rate_nonzero": float((vals[nonzero] > 0).mean()) if nonzero.any() else np.nan,
                "guardrail": GUARDRAIL,
            }
        )
    return pd.DataFrame(rows)


def finite_mean(values: Iterable[float]) -> float:
    arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float], q: float) -> float:
    arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def vals_abs(values: np.ndarray) -> np.ndarray:
    return np.abs(values[np.isfinite(values)])


def stratified_sample(df: pd.DataFrame, max_rows: int, seed: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.copy()
    rng = np.random.default_rng(seed)
    pieces = []
    dates = sorted(df["date"].dropna().unique())
    per_date = max(1, math.ceil(max_rows / max(1, len(dates))))
    for date in dates:
        g = df[df["date"] == date]
        if len(g) <= per_date:
            pieces.append(g)
        else:
            take = rng.choice(g.index.to_numpy(), size=per_date, replace=False)
            pieces.append(g.loc[np.sort(take)])
    out = pd.concat(pieces, axis=0).sort_values(["date", "event_index"])
    if len(out) > max_rows:
        take = rng.choice(out.index.to_numpy(), size=max_rows, replace=False)
        out = out.loc[np.sort(take)]
    return out.reset_index(drop=True)


def clean_xy(df: pd.DataFrame, feature: str, target: str) -> tuple[np.ndarray, np.ndarray]:
    x = df[feature].to_numpy(dtype="float64")
    y = df[target].to_numpy(dtype="float64")
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    return x, y


def safe_pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 20 or np.nanstd(x) <= EPS or np.nanstd(y) <= EPS:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def safe_spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 20 or np.nanstd(x) <= EPS or np.nanstd(y) <= EPS:
        return np.nan
    corr = spearmanr(x, y, nan_policy="omit").correlation
    return float(corr) if corr is not None and math.isfinite(corr) else np.nan


def safe_auc(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    mask = np.isfinite(x) & np.isfinite(y) & (np.abs(y) > EPS)
    if mask.sum() < 50:
        return np.nan, np.nan, int(mask.sum())
    labels = y[mask] > 0
    if labels.min() == labels.max():
        return np.nan, np.nan, int(mask.sum())
    try:
        raw = float(roc_auc_score(labels, x[mask]))
    except ValueError:
        return np.nan, np.nan, int(mask.sum())
    return raw, max(raw, 1.0 - raw), int(mask.sum())


def decile_profile(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    if len(x) < 200 or np.nanstd(x) <= EPS:
        return {
            "top_mean_bps": np.nan,
            "bottom_mean_bps": np.nan,
            "top_bottom_bps": np.nan,
            "top_positive_rate": np.nan,
            "bottom_positive_rate": np.nan,
            "monotonic_spearman": np.nan,
        }
    q_low = float(np.nanquantile(x, 0.10))
    q_high = float(np.nanquantile(x, 0.90))
    top = y[x >= q_high]
    bottom = y[x <= q_low]
    try:
        buckets_raw = pd.qcut(pd.Series(x), q=10, labels=False, duplicates="drop")
        buckets = buckets_raw.to_numpy(dtype="float64")
    except ValueError:
        buckets = pd.Series(x).rank(method="average", pct=True).to_numpy()
        buckets = np.minimum(9, np.floor(buckets * 10)).astype(float)
    means = []
    bucket_ids = sorted(int(v) for v in pd.Series(buckets).dropna().unique())
    for bucket in bucket_ids:
        vals = y[buckets == bucket]
        means.append(float(np.nanmean(vals)) if len(vals) else np.nan)
    monotonic = np.nan
    if len(bucket_ids) >= 3:
        corr = spearmanr(np.asarray(bucket_ids, dtype="float64"), np.asarray(means, dtype="float64"), nan_policy="omit").correlation
        monotonic = float(corr) if corr is not None and math.isfinite(corr) else np.nan
    return {
        "top_mean_bps": finite_mean(top),
        "bottom_mean_bps": finite_mean(bottom),
        "top_bottom_bps": finite_mean(top) - finite_mean(bottom),
        "top_positive_rate": float((top > 0).mean()) if len(top) else np.nan,
        "bottom_positive_rate": float((bottom > 0).mean()) if len(bottom) else np.nan,
        "monotonic_spearman": monotonic,
    }


def factor_family(feature: str) -> str:
    if feature.startswith("mlofi"):
        return "MLOFI"
    if feature.startswith("ofi"):
        return "OFI"
    if "queue_imbalance" in feature or "depth" in feature or "levels" in feature:
        return "depth_queue"
    if "trade" in feature:
        return "trade_arrival"
    if "replenish" in feature:
        return "replenish"
    if "depletion" in feature or "decrease" in feature or "remove" in feature or "cancel" in feature:
        return "depletion_cancel"
    if "spread" in feature or "microprice" in feature:
        return "quote_state"
    if "update" in feature or feature == "batch_rows":
        return "snapshot_update_mix"
    return "other"


def single_factor_sweep(
    stat_df: pd.DataFrame,
    mi_df: pd.DataFrame,
    features: list[str],
    target_cols: list[str],
    max_mi_pairs: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for target in target_cols:
        for feature in features:
            x, y = clean_xy(stat_df, feature, target)
            valid_rows = len(x)
            if valid_rows < 50:
                continue
            unique = pd.Series(x).nunique(dropna=True)
            nonzero_target_rate = float((np.abs(y) > EPS).mean()) if len(y) else np.nan
            pearson = safe_pearson(x, y)
            spearman = safe_spearman(x, y)
            auc_raw, auc_oriented, auc_rows = safe_auc(x, y)
            profile = decile_profile(x, y)

            score = (
                100.0 * abs0(spearman)
                + 50.0 * max(0.0, abs0(auc_oriented) - 0.5)
                + 5.0 * abs0(profile["monotonic_spearman"])
                + 2.0 * min(5.0, abs0(profile["top_bottom_bps"]))
            )
            rows.append(
                {
                    "run_tag": RUN_TAG,
                    "target": target,
                    "feature": feature,
                    "feature_family": factor_family(feature),
                    "valid_rows": valid_rows,
                    "unique_values": int(unique),
                    "nonzero_target_rate": nonzero_target_rate,
                    "pearson": pearson,
                    "spearman": spearman,
                    "auc_raw": auc_raw,
                    "auc_oriented": auc_oriented,
                    "auc_rows": auc_rows,
                    "mutual_info": np.nan,
                    **profile,
                    "method_score": score,
                    "guardrail": GUARDRAIL,
                }
            )
    out = pd.DataFrame(rows).sort_values("method_score", ascending=False)
    if out.empty or max_mi_pairs <= 0:
        return out
    for idx, row in out.head(max_mi_pairs).iterrows():
        feature = str(row["feature"])
        target = str(row["target"])
        x_mi, y_mi = clean_xy(mi_df, feature, target)
        if len(x_mi) >= 200 and np.nanstd(x_mi) > EPS and np.nanstd(y_mi) > EPS:
            try:
                out.loc[idx, "mutual_info"] = float(
                    mutual_info_regression(
                        x_mi.reshape(-1, 1),
                        y_mi,
                        random_state=13,
                        n_neighbors=3,
                    )[0]
                )
            except Exception:
                out.loc[idx, "mutual_info"] = np.nan
    out["method_score"] = (
        100.0 * out["spearman"].abs().fillna(0)
        + 50.0 * (out["auc_oriented"].fillna(0).sub(0.5).clip(lower=0))
        + 5.0 * out["monotonic_spearman"].abs().fillna(0)
        + 2.0 * out["top_bottom_bps"].abs().fillna(0).clip(upper=5.0)
        + 20.0 * out["mutual_info"].abs().fillna(0).clip(upper=0.05)
    )
    return out.sort_values("method_score", ascending=False)


def abs0(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return abs(number) if math.isfinite(number) else 0.0


def split_dates(df: pd.DataFrame) -> dict[str, set[str]]:
    dates = sorted(df["date"].dropna().unique())
    if len(dates) < 3:
        return {"discovery": set(dates), "validation": set(dates), "forward": set(dates)}
    d1 = max(1, int(len(dates) * 0.50))
    d2 = max(d1 + 1, int(len(dates) * 0.75))
    return {
        "discovery": set(dates[:d1]),
        "validation": set(dates[d1:d2]),
        "forward": set(dates[d2:]),
    }


def stability_sweep(stat_df: pd.DataFrame, single: pd.DataFrame, top_n: int = 180) -> pd.DataFrame:
    split_map = split_dates(stat_df)
    candidates = single.head(top_n)[["target", "feature"]].drop_duplicates()
    rows: list[dict[str, object]] = []
    for _, item in candidates.iterrows():
        target = str(item["target"])
        feature = str(item["feature"])
        split_corrs: dict[str, float] = {}
        split_rows: dict[str, int] = {}
        for split, dates in split_map.items():
            g = stat_df[stat_df["date"].isin(dates)]
            x, y = clean_xy(g, feature, target)
            split_corrs[split] = safe_spearman(x, y)
            split_rows[split] = len(x)
        daily = []
        for _, g in stat_df.groupby("date", sort=True):
            x, y = clean_xy(g, feature, target)
            corr = safe_spearman(x, y)
            if math.isfinite(corr):
                daily.append(corr)
        finite_daily = np.asarray(daily, dtype="float64")
        sign_consistency = np.nan
        if len(finite_daily):
            main_sign = 1.0 if finite_mean(finite_daily) >= 0 else -1.0
            sign_consistency = float((np.sign(finite_daily) == main_sign).mean())
        rows.append(
            {
                "run_tag": RUN_TAG,
                "target": target,
                "feature": feature,
                "feature_family": factor_family(feature),
                "discovery_spearman": split_corrs.get("discovery", np.nan),
                "validation_spearman": split_corrs.get("validation", np.nan),
                "forward_spearman": split_corrs.get("forward", np.nan),
                "discovery_rows": split_rows.get("discovery", 0),
                "validation_rows": split_rows.get("validation", 0),
                "forward_rows": split_rows.get("forward", 0),
                "daily_mean_spearman": finite_mean(finite_daily),
                "daily_abs_mean_spearman": finite_mean(np.abs(finite_daily)),
                "daily_sign_consistency": sign_consistency,
                "daily_valid_count": int(len(finite_daily)),
                "guardrail": GUARDRAIL,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["stability_score"] = (
            out["validation_spearman"].abs().fillna(0) * 50
            + out["forward_spearman"].abs().fillna(0) * 70
            + out["daily_sign_consistency"].fillna(0) * 5
        )
        out = out.sort_values("stability_score", ascending=False)
    return out


def negative_controls(
    stat_df: pd.DataFrame,
    single: pd.DataFrame,
    top_pairs: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    candidates = single.head(top_pairs)[["target", "feature"]].drop_duplicates()
    rows: list[dict[str, object]] = []
    for _, item in candidates.iterrows():
        target = str(item["target"])
        feature = str(item["feature"])
        x, y = clean_xy(stat_df, feature, target)
        original = safe_spearman(x, y)

        shuffled = stat_df[[feature, target, "date"]].copy()
        shuffled_values = []
        for _, g in shuffled.groupby("date", sort=False):
            vals = g[feature].to_numpy(dtype="float64").copy()
            rng.shuffle(vals)
            shuffled_values.append(pd.Series(vals, index=g.index))
        shuffled_feature = pd.concat(shuffled_values).sort_index().to_numpy(dtype="float64")
        y_all = shuffled[target].to_numpy(dtype="float64")
        mask = np.isfinite(shuffled_feature) & np.isfinite(y_all)
        shuffled_corr = safe_spearman(shuffled_feature[mask], y_all[mask])

        past_target = target.replace("fwd_", "past_", 1)
        past_corr = np.nan
        if past_target in stat_df.columns:
            xp, yp = clean_xy(stat_df, feature, past_target)
            past_corr = safe_spearman(xp, yp)

        reversed_target = stat_df[target].iloc[::-1].to_numpy(dtype="float64")
        feature_values = stat_df[feature].to_numpy(dtype="float64")
        mask_rev = np.isfinite(feature_values) & np.isfinite(reversed_target)
        reversed_corr = safe_spearman(feature_values[mask_rev], reversed_target[mask_rev])

        rows.extend(
            [
                control_row(target, feature, "original", original, len(x), original, past_corr),
                control_row(target, feature, "shuffle_feature_within_date", shuffled_corr, int(mask.sum()), original, past_corr),
                control_row(target, feature, "reversed_time_target", reversed_corr, int(mask_rev.sum()), original, past_corr),
                control_row(target, feature, "past_return_leakage_probe", past_corr, len(x), original, past_corr),
            ]
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["control_abs_ratio"] = out["control_spearman"].abs() / (
            out["original_spearman"].abs() + EPS
        )
    return out


def control_row(
    target: str,
    feature: str,
    control: str,
    corr: float,
    rows: int,
    original: float,
    past_corr: float,
) -> dict[str, object]:
    return {
        "run_tag": RUN_TAG,
        "target": target,
        "feature": feature,
        "feature_family": factor_family(feature),
        "control": control,
        "rows": rows,
        "control_spearman": corr,
        "original_spearman": original,
        "past_spearman": past_corr,
        "guardrail": GUARDRAIL,
    }


def model_specs(seed: int) -> list[tuple[str, str, object]]:
    specs: list[tuple[str, str, object]] = [
        ("ridge_regression", "regression", make_pipeline(SimpleImputer(), StandardScaler(), Ridge(alpha=10.0))),
        (
            "huber_regression",
            "regression",
            make_pipeline(SimpleImputer(), StandardScaler(), HuberRegressor(alpha=0.001, max_iter=100)),
        ),
        (
            "hist_gradient_boosting_regression",
            "regression",
            HistGradientBoostingRegressor(max_leaf_nodes=31, learning_rate=0.05, max_iter=160, random_state=seed),
        ),
        (
            "random_forest_regression",
            "regression",
            RandomForestRegressor(
                n_estimators=80,
                max_depth=9,
                min_samples_leaf=80,
                n_jobs=-1,
                random_state=seed,
            ),
        ),
        (
            "logistic_l2_direction",
            "classification",
            make_pipeline(
                SimpleImputer(),
                StandardScaler(),
                LogisticRegression(C=0.5, max_iter=300, class_weight="balanced"),
            ),
        ),
        (
            "hist_gradient_boosting_direction",
            "classification",
            HistGradientBoostingClassifier(max_leaf_nodes=31, learning_rate=0.05, max_iter=160, random_state=seed),
        ),
        (
            "random_forest_direction",
            "classification",
            RandomForestClassifier(
                n_estimators=80,
                max_depth=9,
                min_samples_leaf=80,
                n_jobs=-1,
                class_weight="balanced_subsample",
                random_state=seed,
            ),
        ),
    ]
    try:
        from lightgbm import LGBMClassifier, LGBMRegressor

        specs.append(
            (
                "lightgbm_regression",
                "regression",
                LGBMRegressor(
                    n_estimators=180,
                    learning_rate=0.04,
                    num_leaves=31,
                    min_child_samples=100,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=seed,
                    verbosity=-1,
                ),
            )
        )
        specs.append(
            (
                "lightgbm_direction",
                "classification",
                LGBMClassifier(
                    n_estimators=180,
                    learning_rate=0.04,
                    num_leaves=31,
                    min_child_samples=100,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    class_weight="balanced",
                    random_state=seed,
                    verbosity=-1,
                ),
            )
        )
    except Exception:
        pass
    return specs


def model_sweep(
    model_df: pd.DataFrame,
    features: list[str],
    target_cols: list[str],
    single: pd.DataFrame,
    seed: int,
) -> pd.DataFrame:
    split_map = split_dates(model_df)
    rows: list[dict[str, object]] = []
    preferred_targets = pick_model_targets(target_cols, single)
    for target in preferred_targets:
        y_all = model_df[target].to_numpy(dtype="float64")
        valid = np.isfinite(y_all)
        nonzero = np.abs(y_all) > EPS
        base = model_df[valid].copy()
        if len(base) < 2_000:
            continue
        selected_features = pick_model_features(single, target, features, limit=36)
        X = base[selected_features].replace([np.inf, -np.inf], np.nan)
        y = base[target].to_numpy(dtype="float64")
        dates = base["date"].astype(str)
        train_mask = dates.isin(split_map["discovery"]).to_numpy()
        valid_mask = dates.isin(split_map["validation"]).to_numpy()
        forward_mask = dates.isin(split_map["forward"]).to_numpy()
        if train_mask.sum() < 1_000 or valid_mask.sum() < 200:
            continue

        for name, kind, model in model_specs(seed):
            try:
                if kind == "classification":
                    class_mask = np.abs(y) > EPS
                    fit_mask = train_mask & class_mask
                    if fit_mask.sum() < 500:
                        continue
                    y_class = y > 0
                    if len(np.unique(y_class[fit_mask])) < 2:
                        continue
                    model.fit(X.loc[fit_mask], y_class[fit_mask])
                    for split, mask in [
                        ("validation", valid_mask & class_mask),
                        ("forward", forward_mask & class_mask),
                    ]:
                        if mask.sum() < 200 or len(np.unique(y_class[mask])) < 2:
                            continue
                        pred = predict_score(model, X.loc[mask])
                        rows.append(model_metric_row(name, kind, target, split, y[mask], pred, selected_features))
                else:
                    model.fit(X.loc[train_mask], y[train_mask])
                    for split, mask in [("validation", valid_mask), ("forward", forward_mask)]:
                        if mask.sum() < 200:
                            continue
                        pred = np.asarray(model.predict(X.loc[mask]), dtype="float64")
                        rows.append(model_metric_row(name, kind, target, split, y[mask], pred, selected_features))
            except Exception as exc:
                rows.append(
                    {
                        "run_tag": RUN_TAG,
                        "target": target,
                        "model": name,
                        "kind": kind,
                        "split": "error",
                        "rows": 0,
                        "spearman": np.nan,
                        "pearson": np.nan,
                        "direction_auc": np.nan,
                        "r2": np.nan,
                        "mae_bps": np.nan,
                        "top_bottom_bps": np.nan,
                        "feature_count": len(selected_features),
                        "features": " ".join(selected_features),
                        "error": str(exc)[:240],
                        "guardrail": GUARDRAIL,
                    }
                )
    return pd.DataFrame(rows)


def pick_model_targets(target_cols: list[str], single: pd.DataFrame) -> list[str]:
    preferred = [
        "fwd_event_70_bps",
        "fwd_event_250_bps",
        "fwd_time_60s_bps",
        "fwd_time_300s_bps",
        "fwd_time_900s_bps",
    ]
    out = [target for target in preferred if target in target_cols]
    for target in single["target"].drop_duplicates().head(3):
        if target not in out:
            out.append(str(target))
    return out[:6]


def pick_model_features(single: pd.DataFrame, target: str, features: list[str], limit: int) -> list[str]:
    rows = single[single["target"] == target].sort_values("method_score", ascending=False)
    selected = list(rows["feature"].drop_duplicates().head(limit))
    if len(selected) < min(limit, len(features)):
        for feature in features:
            if feature not in selected:
                selected.append(feature)
            if len(selected) >= limit:
                break
    return selected


def predict_score(model: object, X: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        return np.asarray(proba[:, 1], dtype="float64")
    if hasattr(model, "decision_function"):
        return np.asarray(model.decision_function(X), dtype="float64")
    return np.asarray(model.predict(X), dtype="float64")


def model_metric_row(
    name: str,
    kind: str,
    target: str,
    split: str,
    y: np.ndarray,
    pred: np.ndarray,
    features: list[str],
) -> dict[str, object]:
    pearson = safe_pearson(pred, y)
    spearman = safe_spearman(pred, y)
    auc_raw, auc_oriented, auc_rows = safe_auc(pred, y)
    profile = decile_profile(pred, y)
    r2 = np.nan
    if kind == "regression" and len(y) > 10:
        try:
            r2 = float(r2_score(y, pred))
        except Exception:
            r2 = np.nan
    return {
        "run_tag": RUN_TAG,
        "target": target,
        "model": name,
        "kind": kind,
        "split": split,
        "rows": int(len(y)),
        "spearman": spearman,
        "pearson": pearson,
        "direction_auc": auc_oriented,
        "direction_auc_rows": auc_rows,
        "r2": r2,
        "mae_bps": float(mean_absolute_error(y, pred)) if len(y) else np.nan,
        "top_bottom_bps": profile["top_bottom_bps"],
        "monotonic_spearman": profile["monotonic_spearman"],
        "feature_count": len(features),
        "features": " ".join(features),
        "error": "",
        "guardrail": GUARDRAIL,
    }


def render_report(
    paths: Paths,
    quality: pd.DataFrame,
    targets: pd.DataFrame,
    single: pd.DataFrame,
    stability: pd.DataFrame,
    controls: pd.DataFrame,
    models: pd.DataFrame,
    summary: dict[str, object],
) -> None:
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    top_single = single.head(12).copy()
    top_stable = stability.head(10).copy() if not stability.empty else pd.DataFrame()
    bad_controls = controls[
        (controls["control"] != "original") & (controls["control_abs_ratio"] >= 0.75)
    ].head(10) if not controls.empty else pd.DataFrame()
    model_top = (
        models[(models["split"] == "forward") & (models["error"].fillna("") == "")]
        .sort_values(["direction_auc", "spearman"], ascending=False)
        .head(10)
        if not models.empty
        else pd.DataFrame()
    )

    lines = [
        "# CCUSDT Factor Method Sweep",
        "",
        f"Status: `{paths.run_tag}` from source panel `{paths.source_run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This report is a broad diagnostic sweep over the fixed snapshot-frame orderbook panel. It is not queue-position fill evidence, not a live execution simulation, and not an alpha claim.",
        "",
        "## Scope",
        "",
        f"- Panel rows loaded: `{summary['rows']:,}`.",
        f"- Candidate features: `{summary['feature_count']}`.",
        f"- Forward targets: `{summary['target_count']}` across event-count and wall-clock horizons.",
        f"- Statistical sample rows: `{summary['stat_rows']:,}`; MI sample rows: `{summary['mi_rows']:,}`; model sample rows: `{summary['model_rows']:,}`.",
        "",
        "Methods tried: Pearson, Spearman, decile top-bottom, decile monotonicity, directional AUC, mutual information, chronological split stability, daily sign consistency, within-day shuffle controls, reversed-time controls, past-return leakage probes, Ridge, Huber, histogram gradient boosting, random forest, logistic direction classifiers, and LightGBM when installed.",
        "",
        "## Data Semantics",
        "",
        markdown_table(
            quality_summary_rows(quality),
            [
                ("Metric", "metric"),
                ("Value", "value"),
            ],
        ),
        "",
        "The important read is that CCUSDT is a snapshot-frame panel: long unchanged best bid/ask runs are common, while top-of-book sizes and depth can keep drifting. Event-count labels therefore mix actual quote changes with many zero-return frames.",
        "",
        "## Target Activity",
        "",
        markdown_table(
            targets.sort_values("nonzero_rate", ascending=False).head(12).to_dict("records"),
            [
                ("Target", "target"),
                ("Rows", "valid_rows"),
                ("Nonzero", "nonzero_rate"),
                ("Abs P90 bps", "abs_p90_bps"),
                ("Abs P99 bps", "abs_p99_bps"),
            ],
            formatters={"nonzero_rate": pct, "abs_p90_bps": num4, "abs_p99_bps": num4},
        ),
        "",
        "## Top Single-Factor Diagnostics",
        "",
        markdown_table(
            top_single.to_dict("records"),
            [
                ("Target", "target"),
                ("Feature", "feature"),
                ("Family", "feature_family"),
                ("Spearman", "spearman"),
                ("AUC", "auc_oriented"),
                ("Top-Bottom bps", "top_bottom_bps"),
                ("MI", "mutual_info"),
                ("Score", "method_score"),
            ],
            formatters={
                "spearman": num4,
                "auc_oriented": num4,
                "top_bottom_bps": num4,
                "mutual_info": num6,
                "method_score": num2,
            },
        ),
        "",
        "## Stability",
        "",
        markdown_table(
            top_stable.to_dict("records"),
            [
                ("Target", "target"),
                ("Feature", "feature"),
                ("Validation IC", "validation_spearman"),
                ("Forward IC", "forward_spearman"),
                ("Daily Sign", "daily_sign_consistency"),
                ("Score", "stability_score"),
            ],
            formatters={
                "validation_spearman": num4,
                "forward_spearman": num4,
                "daily_sign_consistency": pct,
                "stability_score": num2,
            },
        ),
        "",
        "## Negative Controls",
        "",
        markdown_table(
            bad_controls.to_dict("records"),
            [
                ("Target", "target"),
                ("Feature", "feature"),
                ("Control", "control"),
                ("Control IC", "control_spearman"),
                ("Original IC", "original_spearman"),
                ("Abs Ratio", "control_abs_ratio"),
            ],
            formatters={
                "control_spearman": num4,
                "original_spearman": num4,
                "control_abs_ratio": num2,
            },
        ),
        "",
        "Controls near the original score are treated as artifact warnings. In this panel, past-return and reversed-time controls are especially useful because slow quote changes can make state variables look predictive in both directions of time.",
        "",
        "## Model Readout",
        "",
        markdown_table(
            model_top.to_dict("records"),
            [
                ("Target", "target"),
                ("Model", "model"),
                ("Kind", "kind"),
                ("Rows", "rows"),
                ("Forward IC", "spearman"),
                ("AUC", "direction_auc"),
                ("Top-Bottom bps", "top_bottom_bps"),
            ],
            formatters={
                "spearman": num4,
                "direction_auc": num4,
                "top_bottom_bps": num4,
            },
        ),
        "",
        "## Output Tables",
        "",
        f"- `{rel(paths.quality_csv)}`",
        f"- `{rel(paths.target_csv)}`",
        f"- `{rel(paths.single_factor_csv)}`",
        f"- `{rel(paths.stability_csv)}`",
        f"- `{rel(paths.negative_controls_csv)}`",
        f"- `{rel(paths.model_csv)}`",
        f"- `{rel(paths.summary_json)}`",
        "",
        "## Current Read",
        "",
        current_read(single, stability, controls, models),
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python scripts/ccusdt_factor_method_sweep.py",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def quality_summary_rows(quality: pd.DataFrame) -> list[dict[str, str]]:
    return [
        {"metric": "days", "value": str(len(quality))},
        {"metric": "rows", "value": f"{int(quality['rows'].sum()):,}"},
        {"metric": "snapshot rate", "value": pct(quality["snapshot_rate"].mean())},
        {"metric": "median daily distinct mids", "value": f"{quality['distinct_mid'].median():.0f}"},
        {"metric": "median quote-change rate", "value": pct(quality["quote_change_rate"].median())},
        {"metric": "median top-size-change rate", "value": pct(quality["top_size_change_rate"].median())},
        {"metric": "median trade-present rate", "value": pct(quality["trade_present_rate"].median())},
        {"metric": "max stable quote run", "value": f"{quality['longest_quote_run_frames'].max():.0f} frames / {quality['longest_quote_run_seconds'].max():.1f}s"},
        {"metric": "max stable mid run", "value": f"{quality['longest_mid_run_frames'].max():.0f} frames / {quality['longest_mid_run_seconds'].max():.1f}s"},
    ]


def current_read(single: pd.DataFrame, stability: pd.DataFrame, controls: pd.DataFrame, models: pd.DataFrame) -> str:
    if single.empty:
        return "No usable factor diagnostics were produced."
    best = single.iloc[0]
    warnings_count = 0
    if not controls.empty:
        warnings_count = int(
            ((controls["control"] != "original") & (controls["control_abs_ratio"] >= 0.75)).sum()
        )
    stable = "none"
    if not stability.empty:
        top = stability.iloc[0]
        stable = f"{top['feature']} on {top['target']} (forward IC {num4(top['forward_spearman'])})"
    model_read = "models skipped or no forward rows"
    if not models.empty:
        ok = models[(models["split"] == "forward") & (models["error"].fillna("") == "")]
        if not ok.empty:
            row = ok.sort_values(["direction_auc", "spearman"], ascending=False).iloc[0]
            model_read = f"{row['model']} on {row['target']} (AUC {num4(row['direction_auc'])}, IC {num4(row['spearman'])})"
    return (
        f"Best single-factor score is `{best['feature']}` on `{best['target']}`, but CCUSDT must be read as a snapshot-frame diagnostic panel. "
        f"Most promising stable diagnostic: `{stable}`. "
        f"Model readout: `{model_read}`. "
        f"Artifact warnings from controls: `{warnings_count}` high-ratio rows. "
        "Treat MLOFI/depth/trade-arrival findings as information structure to inspect, not as executable fill evidence."
    )


def markdown_table(
    rows: list[dict[str, object]],
    columns: list[tuple[str, str]],
    formatters: dict[str, object] | None = None,
) -> str:
    if not rows:
        return "_No rows._"
    formatters = formatters or {}
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        vals = []
        for _, key in columns:
            value = row.get(key, "")
            fmt = formatters.get(key)
            vals.append(str(fmt(value) if fmt else value))
        body.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep, *body])


def pct(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NA"
    if not math.isfinite(number):
        return "NA"
    return f"{number * 100:.2f}%"


def num2(value: object) -> str:
    return fmt_num(value, 2)


def num4(value: object) -> str:
    return fmt_num(value, 4)


def num6(value: object) -> str:
    return fmt_num(value, 6)


def fmt_num(value: object, digits: int) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NA"
    if not math.isfinite(number):
        return "NA"
    return f"{number:.{digits}f}"


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root()))
    except ValueError:
        return str(path)


def write_outputs(
    paths: Paths,
    quality: pd.DataFrame,
    targets: pd.DataFrame,
    single: pd.DataFrame,
    stability: pd.DataFrame,
    controls: pd.DataFrame,
    models: pd.DataFrame,
    summary: dict[str, object],
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    quality.to_csv(paths.quality_csv, index=False)
    targets.to_csv(paths.target_csv, index=False)
    single.to_csv(paths.single_factor_csv, index=False)
    stability.to_csv(paths.stability_csv, index=False)
    controls.to_csv(paths.negative_controls_csv, index=False)
    models.to_csv(paths.model_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    render_report(paths, quality, targets, single, stability, controls, models, summary)


def main() -> None:
    global RUN_TAG
    args = parse_args()
    RUN_TAG = args.run_tag
    root = repo_root()
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    event_horizons = parse_ints(args.event_horizons)
    time_horizons_sec = parse_ints(args.time_horizons_sec)

    df, features = load_panel(paths)
    print(f"loaded rows={len(df):,} usable_features={len(features)}", flush=True)
    df, target_cols = add_labels(df, event_horizons, time_horizons_sec)
    print(f"built targets={len(target_cols)}", flush=True)

    quality = quality_rows(df, target_cols)
    targets = target_rows(df, target_cols)

    stat_df = stratified_sample(df, args.max_stat_rows, args.seed)
    mi_df = stratified_sample(df, args.max_mi_rows, args.seed + 1)
    model_df = stratified_sample(df, args.max_model_rows, args.seed + 2)
    print(f"samples stat={len(stat_df):,} mi={len(mi_df):,} model={len(model_df):,}", flush=True)

    single = single_factor_sweep(stat_df, mi_df, features, target_cols, args.max_mi_pairs)
    print(f"single_factor_rows={len(single):,}", flush=True)
    stability = stability_sweep(stat_df, single)
    print(f"stability_rows={len(stability):,}", flush=True)
    controls = negative_controls(stat_df, single, args.top_control_pairs, args.seed)
    print(f"negative_control_rows={len(controls):,}", flush=True)
    models = pd.DataFrame()
    if not args.skip_models:
        models = model_sweep(model_df, features, target_cols, single, args.seed)
        print(f"model_rows={len(models):,}", flush=True)

    summary = {
        "run_tag": args.run_tag,
        "source_run_tag": args.source_run_tag,
        "rows": int(len(df)),
        "feature_count": int(len(features)),
        "target_count": int(len(target_cols)),
        "stat_rows": int(len(stat_df)),
        "mi_rows": int(len(mi_df)),
        "model_rows": int(len(model_df)),
        "event_horizons": event_horizons,
        "time_horizons_sec": time_horizons_sec,
        "quality_csv": rel(paths.quality_csv),
        "target_csv": rel(paths.target_csv),
        "single_factor_csv": rel(paths.single_factor_csv),
        "stability_csv": rel(paths.stability_csv),
        "negative_controls_csv": rel(paths.negative_controls_csv),
        "model_csv": rel(paths.model_csv),
        "report_md": rel(paths.report_md),
        "guardrail": GUARDRAIL,
    }
    write_outputs(paths, quality, targets, single, stability, controls, models, summary)
    print(f"report={paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
