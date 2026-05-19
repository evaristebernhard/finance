#!/usr/bin/env python
"""CCUSDT strategy research overlay.

Research-only strategy diagnostics over the fixed snapshot-frame factor panel.
This script does not download data, mutate raw files, infer queue-position fill
evidence, or emit trading advice. It converts factor opportunities into toy
replay rules so they can be stress-tested for fold stability, costs, activity
conditioning, stale-quote behavior, and simple negative controls.
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


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=PerformanceWarning)


GUARDRAIL = "research_only_toy_replay_no_execution_recommendation_no_alpha_claim"
SOURCE_RUN_TAG = "20260517_ccusdt_fixed_factors_v3"
METHOD_SWEEP_RUN_TAG = "20260517_ccusdt_method_sweep_v1"
RUN_TAG = "20260517_ccusdt_strategy_research_v1"
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

HARDCODED_FEATURE_ORDER = [
    "trade_flow_imbalance",
    "mlofi_roll10_l1",
    "mlofi_roll10_l2",
    "mlofi_roll10_l10",
    "mlofi_roll10_l25",
    "trade_arrival_alignment",
    "ofi_l1_raw",
    "ofi_l1_depth_norm",
    "queue_imbalance_1",
    "queue_imbalance_5",
    "queue_imbalance_25",
    "microprice_dev_bps",
    "best_bid_amount",
    "best_ask_amount",
    "bid_depth_1",
    "ask_depth_1",
    "liquidity_shock_score",
    "queue_depletion_intensity",
]

COMPOSITE_SPECS: dict[str, list[str]] = {
    "combo_trade_mlofi_l1": ["trade_flow_imbalance", "mlofi_roll10_l1"],
    "combo_mlofi_l1_l25": ["mlofi_roll10_l1", "mlofi_roll10_l25"],
    "combo_book_pressure": ["queue_imbalance_1", "microprice_dev_bps", "ofi_l1_depth_norm"],
}

COST_MODELS = [
    "toy_mid",
    "toy_maker_light",
    "toy_taker_spread",
    "toy_wide_stress",
]


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    run_tag: str
    method_sweep_run_tag: str

    @property
    def panel_run_root(self) -> Path:
        return self.panel_root / f"run_tag={self.source_run_tag}" / "symbol=CCUSDT"

    @property
    def quality_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_strategy_research_quality_{self.run_tag}.csv"

    @property
    def candidate_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_strategy_research_candidates_{self.run_tag}.csv"

    @property
    def control_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_strategy_research_controls_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_strategy_research_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / "v1-strategy-research.md"

    @property
    def method_single_factor_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_factor_method_sweep_single_factor_{self.method_sweep_run_tag}.csv"

    @property
    def path_ranking_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_fixed_event_factors_path_ranking_{self.source_run_tag}.csv"


@dataclass(frozen=True)
class Fold:
    name: str
    train_dates: tuple[str, ...]
    test_dates: tuple[str, ...]


@dataclass(frozen=True)
class TargetSpec:
    name: str
    horizon_kind: str
    horizon_value: int

    @property
    def exit_col(self) -> str:
        return f"{self.name}_exit_idx"

    @property
    def bucket_col(self) -> str:
        return f"{self.name}_bucket"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT toy strategy research diagnostics.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--method-sweep-run-tag", default=METHOD_SWEEP_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--event-horizons", default="25,70")
    parser.add_argument("--time-horizons-sec", default="10,60")
    parser.add_argument("--quantiles", default="0.80,0.90")
    parser.add_argument("--max-auto-features", type=int, default=8)
    parser.add_argument(
        "--filters",
        default="all,trade_present,stale_mid_ge25,stale_mid_ge70,past25_abs_le_0p5bps,trade_present_stale_mid_ge25",
        help="Comma-separated filter names. Use names emitted by build_filter_masks.",
    )
    parser.add_argument(
        "--policies",
        default="follow_extremes,fade_extremes,long_high,short_low",
        help="Comma-separated policies: follow_extremes,fade_extremes,long_high,short_low,long_low,short_high.",
    )
    parser.add_argument("--extra-composites", action="store_true", default=True)
    parser.add_argument("--top-control-strategies", type=int, default=80)
    parser.add_argument("--control-shift-events", type=int, default=500)
    parser.add_argument("--seed", type=int, default=17)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_ints(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if text:
            values.append(int(text))
    if not values:
        raise ValueError("expected at least one integer")
    return values


def parse_floats(raw: str) -> list[float]:
    values: list[float] = []
    for part in raw.split(","):
        text = part.strip()
        if text:
            values.append(float(text))
    values = sorted(set(values))
    if not values:
        raise ValueError("expected at least one quantile")
    for value in values:
        if not 0.50 < value < 1.0:
            raise ValueError(f"quantile must be in (0.5, 1.0), got {value}")
    return values


def parse_strings(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one string value")
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
    print(f"loading CCUSDT factor panel files={len(files)} columns={len(usecols)}", flush=True)
    lf = (
        pl.scan_csv(
            pattern,
            infer_schema_length=1000,
            null_values=["", "NaN", "nan", "NA"],
            ignore_errors=True,
        )
        .select(usecols)
        .sort(["date", "event_index"])
    )
    frame = lf.collect(engine="streaming")
    df = frame.to_pandas()
    del frame
    df = df.reset_index(drop=True)
    df["date"] = df["date"].astype(str)
    usable_features = [col for col in FEATURE_COLS if col in df.columns]
    for col in sorted(set([*usable_features, *META_COLS])):
        if col in {"run_tag", "date", "symbol", "factor_eligible", "is_snapshot_batch"}:
            continue
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "spread_bps" in df.columns:
        df["spread_bps"] = df["spread_bps"].clip(lower=0.0)
    return df, usable_features


def add_replay_labels(
    df: pd.DataFrame,
    event_horizons: list[int],
    time_horizons_sec: list[int],
) -> tuple[pd.DataFrame, list[TargetSpec]]:
    n = len(df)
    new_cols: dict[str, np.ndarray] = {
        "row_pos_in_day": np.zeros(n, dtype="int64"),
        "mid_change_prev": np.zeros(n, dtype=bool),
        "quote_change_prev": np.zeros(n, dtype=bool),
        "top_size_change_prev": np.zeros(n, dtype=bool),
        "frames_since_mid_change": np.full(n, np.nan, dtype="float64"),
        "gap_sec": np.full(n, np.nan, dtype="float64"),
        "date_code": np.zeros(n, dtype="int64"),
    }
    targets: list[TargetSpec] = []
    for horizon in event_horizons:
        target = TargetSpec(f"fwd_event_{horizon}_bps", "event", horizon)
        targets.append(target)
        new_cols[target.name] = np.full(n, np.nan, dtype="float64")
        new_cols[target.exit_col] = np.full(n, -1, dtype="int64")
        new_cols[target.bucket_col] = np.full(n, -1, dtype="int64")
        new_cols[f"past_event_{horizon}_bps"] = np.full(n, np.nan, dtype="float64")
    for seconds in time_horizons_sec:
        target = TargetSpec(f"fwd_time_{seconds}s_bps", "time", seconds)
        targets.append(target)
        new_cols[target.name] = np.full(n, np.nan, dtype="float64")
        new_cols[target.exit_col] = np.full(n, -1, dtype="int64")
        new_cols[target.bucket_col] = np.full(n, -1, dtype="int64")
        new_cols[f"past_time_{seconds}s_bps"] = np.full(n, np.nan, dtype="float64")

    date_to_code = {date: code for code, date in enumerate(sorted(df["date"].unique()))}

    for date, idx in df.groupby("date", sort=False).groups.items():
        pos = np.asarray(idx, dtype="int64")
        if len(pos) == 0:
            continue
        date_code = date_to_code[str(date)]
        mids = df.loc[pos, "mid_price"].to_numpy(dtype="float64")
        times = df.loc[pos, "local_timestamp"].to_numpy(dtype="float64")
        bids = df.loc[pos, "best_bid_price"].to_numpy(dtype="float64")
        asks = df.loc[pos, "best_ask_price"].to_numpy(dtype="float64")
        bid_amt = df.loc[pos, "best_bid_amount"].to_numpy(dtype="float64")
        ask_amt = df.loc[pos, "best_ask_amount"].to_numpy(dtype="float64")
        row_pos = np.arange(len(pos), dtype="int64")

        new_cols["row_pos_in_day"][pos] = row_pos
        new_cols["date_code"][pos] = date_code

        if len(pos) > 1:
            prev_mid = np.r_[np.nan, mids[:-1]]
            prev_bid = np.r_[np.nan, bids[:-1]]
            prev_ask = np.r_[np.nan, asks[:-1]]
            prev_bid_amt = np.r_[np.nan, bid_amt[:-1]]
            prev_ask_amt = np.r_[np.nan, ask_amt[:-1]]
            mid_change = np.isfinite(prev_mid) & (np.abs(mids - prev_mid) > EPS)
            quote_change = (
                np.isfinite(prev_bid)
                & np.isfinite(prev_ask)
                & ((np.abs(bids - prev_bid) > EPS) | (np.abs(asks - prev_ask) > EPS))
            )
            top_size_change = (
                np.isfinite(prev_bid_amt)
                & np.isfinite(prev_ask_amt)
                & ((np.abs(bid_amt - prev_bid_amt) > EPS) | (np.abs(ask_amt - prev_ask_amt) > EPS))
            )
            new_cols["mid_change_prev"][pos] = mid_change
            new_cols["quote_change_prev"][pos] = quote_change
            new_cols["top_size_change_prev"][pos] = top_size_change
            new_cols["gap_sec"][pos[1:]] = np.diff(times) / US_PER_SECOND
            last_mid_change = -10**9
            frames_since = np.zeros(len(pos), dtype="float64")
            for i, changed in enumerate(mid_change):
                if changed:
                    last_mid_change = i
                frames_since[i] = i - last_mid_change if last_mid_change > -10**8 else np.inf
            new_cols["frames_since_mid_change"][pos] = frames_since
        else:
            new_cols["frames_since_mid_change"][pos] = np.inf

        for horizon in event_horizons:
            target = TargetSpec(f"fwd_event_{horizon}_bps", "event", horizon)
            bucket = row_pos // max(1, horizon)
            new_cols[target.bucket_col][pos] = date_code * 10_000_000 + bucket
            if len(pos) > horizon:
                valid_now = np.arange(0, len(pos) - horizon, dtype="int64")
                valid_future = valid_now + horizon
                ret = 10_000.0 * np.log(np.maximum(mids[valid_future], EPS) / np.maximum(mids[valid_now], EPS))
                new_cols[target.name][pos[valid_now]] = ret
                new_cols[target.exit_col][pos[valid_now]] = pos[valid_future]
                new_cols[f"past_event_{horizon}_bps"][pos[valid_future]] = ret

        for seconds in time_horizons_sec:
            target = TargetSpec(f"fwd_time_{seconds}s_bps", "time", seconds)
            horizon_us = seconds * US_PER_SECOND
            day_start = times[0]
            bucket = np.floor((times - day_start) / max(1, horizon_us)).astype("int64")
            new_cols[target.bucket_col][pos] = date_code * 10_000_000 + bucket
            fwd_idx = np.searchsorted(times, times + horizon_us, side="left")
            valid = fwd_idx < len(pos)
            src = np.flatnonzero(valid)
            dst = fwd_idx[valid]
            if len(src):
                ret = 10_000.0 * np.log(np.maximum(mids[dst], EPS) / np.maximum(mids[src], EPS))
                new_cols[target.name][pos[src]] = ret
                new_cols[target.exit_col][pos[src]] = pos[dst]
            past_idx = np.searchsorted(times, times - horizon_us, side="right") - 1
            valid_past = past_idx >= 0
            src_past = np.flatnonzero(valid_past)
            dst_past = past_idx[valid_past]
            if len(src_past):
                past = 10_000.0 * np.log(np.maximum(mids[src_past], EPS) / np.maximum(mids[dst_past], EPS))
                new_cols[f"past_time_{seconds}s_bps"][pos[src_past]] = past

    return pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1), targets


def finite_mean(values: Iterable[float]) -> float:
    arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float], q: float) -> float:
    arr = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator and np.isfinite(denominator) else np.nan


def feature_family(feature: str) -> str:
    if feature.startswith("combo_"):
        return "composite"
    if "mlofi" in feature:
        return "MLOFI"
    if feature in {"trade_flow_imbalance", "trade_arrival_alignment"}:
        return "trade_arrival"
    if "queue" in feature:
        return "queue"
    if "depth" in feature or feature.endswith("_amount"):
        return "depth"
    if "microprice" in feature or "ofi" in feature:
        return "book_pressure"
    return "other"


def strip_transform(feature: str) -> str:
    for prefix in ("pos__", "neg__", "abs__", "signed_sq__"):
        if feature.startswith(prefix):
            return feature[len(prefix) :]
    return feature


def select_candidate_features(paths: Paths, usable_features: list[str], max_auto_features: int) -> list[str]:
    usable = set(usable_features)
    features: list[str] = []

    def append(feature: str) -> None:
        base = strip_transform(feature)
        if base in usable and base not in features:
            features.append(base)

    if paths.method_single_factor_csv.exists():
        try:
            sweep = pd.read_csv(paths.method_single_factor_csv)
            sweep["method_score"] = pd.to_numeric(sweep.get("method_score"), errors="coerce")
            sweep = sweep.sort_values("method_score", ascending=False)
            for feature in sweep["feature"].dropna().astype(str):
                append(feature)
                if len(features) >= max_auto_features:
                    break
        except Exception as exc:  # pragma: no cover - defensive diagnostics path
            print(f"warning: could not read method sweep features: {exc}", flush=True)

    if len(features) < max_auto_features and paths.path_ranking_csv.exists():
        try:
            ranking = pd.read_csv(paths.path_ranking_csv, usecols=["feature_name", "score"])
            ranking["score"] = pd.to_numeric(ranking["score"], errors="coerce")
            ranking = ranking.sort_values("score", ascending=False)
            for feature in ranking["feature_name"].dropna().astype(str):
                append(feature)
                if len(features) >= max_auto_features:
                    break
        except Exception as exc:  # pragma: no cover - defensive diagnostics path
            print(f"warning: could not read path ranking features: {exc}", flush=True)

    for feature in HARDCODED_FEATURE_ORDER:
        append(feature)
        if len(features) >= max_auto_features:
            break

    for composite, cols in COMPOSITE_SPECS.items():
        if all(col in usable for col in cols):
            features.append(composite)

    return features


def make_folds(dates: list[str]) -> list[Fold]:
    if len(dates) < 6:
        raise ValueError("need at least six dates for walk-forward folds")
    folds: list[Fold] = []
    min_train = min(max(5, len(dates) // 3), len(dates) - 2)
    test_size = max(2, math.ceil((len(dates) - min_train) / 3))
    train_end = min_train
    fold_no = 1
    while train_end < len(dates):
        test_end = min(len(dates), train_end + test_size)
        if test_end <= train_end:
            break
        folds.append(
            Fold(
                name=f"expanding_fold{fold_no}",
                train_dates=tuple(dates[:train_end]),
                test_dates=tuple(dates[train_end:test_end]),
            )
        )
        fold_no += 1
        train_end = test_end
    if not folds:
        folds.append(Fold("expanding_fold1", tuple(dates[: len(dates) // 2]), tuple(dates[len(dates) // 2 :])))
    return folds


def build_filter_masks(df: pd.DataFrame) -> dict[str, np.ndarray]:
    n = len(df)
    trade_present = df.get("trade_window_count", pd.Series(np.zeros(n))).fillna(0).to_numpy(dtype="float64") > 0
    quote_change = df["quote_change_prev"].fillna(False).to_numpy(dtype=bool)
    top_size_change = df["top_size_change_prev"].fillna(False).to_numpy(dtype=bool)
    frames_since_mid = df["frames_since_mid_change"].to_numpy(dtype="float64")
    past_25 = df.get("past_event_25_bps", pd.Series(np.full(n, np.nan))).to_numpy(dtype="float64")
    return {
        "all": np.ones(n, dtype=bool),
        "trade_present": trade_present,
        "quote_change_prev": quote_change,
        "top_size_change_prev": top_size_change,
        "stale_mid_ge25": frames_since_mid >= 25,
        "stale_mid_ge70": frames_since_mid >= 70,
        "trade_present_stale_mid_ge25": trade_present & (frames_since_mid >= 25),
        "past25_abs_le_0p5bps": np.isfinite(past_25) & (np.abs(past_25) <= 0.5),
    }


def zscore_from_train(raw: np.ndarray, train_mask: np.ndarray) -> np.ndarray:
    train = raw[train_mask & np.isfinite(raw)]
    if len(train) < 100:
        return np.full_like(raw, np.nan, dtype="float64")
    median = np.nanmedian(train)
    q75 = np.nanpercentile(train, 75)
    q25 = np.nanpercentile(train, 25)
    scale = (q75 - q25) / 1.349
    if not np.isfinite(scale) or scale <= EPS:
        scale = np.nanstd(train)
    if not np.isfinite(scale) or scale <= EPS:
        return np.full_like(raw, np.nan, dtype="float64")
    return (raw - median) / scale


def feature_values_for_fold(
    df: pd.DataFrame,
    feature: str,
    train_mask: np.ndarray,
    cache: dict[tuple[str, bytes], np.ndarray],
) -> np.ndarray:
    cache_key = (feature, train_mask.tobytes())
    if cache_key in cache:
        return cache[cache_key]
    if feature in COMPOSITE_SPECS:
        pieces = []
        for col in COMPOSITE_SPECS[feature]:
            raw = df[col].to_numpy(dtype="float64")
            pieces.append(zscore_from_train(raw, train_mask))
        values = np.nanmean(np.vstack(pieces), axis=0)
    else:
        values = df[feature].to_numpy(dtype="float64")
    cache[cache_key] = values
    return values


def build_policy_mask(
    values: np.ndarray,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    filter_mask: np.ndarray,
    quantile: float,
    policy: str,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    train_values = values[train_mask & np.isfinite(values)]
    if len(train_values) < 100:
        return np.zeros_like(test_mask, dtype=bool), np.zeros_like(values, dtype="int8"), np.nan, np.nan
    q_low = float(np.quantile(train_values, 1.0 - quantile))
    q_high = float(np.quantile(train_values, quantile))
    finite = np.isfinite(values)
    high = finite & (values >= q_high)
    low = finite & (values <= q_low)
    direction = np.zeros(len(values), dtype="int8")
    if policy == "follow_extremes":
        mask = high | low
        direction[high] = 1
        direction[low] = -1
    elif policy == "fade_extremes":
        mask = high | low
        direction[high] = -1
        direction[low] = 1
    elif policy == "long_high":
        mask = high
        direction[high] = 1
    elif policy == "short_low":
        mask = low
        direction[low] = -1
    elif policy == "long_low":
        mask = low
        direction[low] = 1
    elif policy == "short_high":
        mask = high
        direction[high] = -1
    else:
        raise ValueError(f"unknown policy {policy}")
    mask = mask & test_mask & filter_mask
    return mask, direction, q_low, q_high


def first_per_bucket(candidate_idx: np.ndarray, bucket: np.ndarray) -> np.ndarray:
    if len(candidate_idx) == 0:
        return candidate_idx
    candidate_bucket = bucket[candidate_idx]
    keep = np.r_[True, candidate_bucket[1:] != candidate_bucket[:-1]]
    return candidate_idx[keep]


def shifted_within_day(mask: np.ndarray, date_codes: np.ndarray, shift: int) -> np.ndarray:
    if shift <= 0:
        return mask.copy()
    out = np.zeros_like(mask, dtype=bool)
    for code in np.unique(date_codes):
        idx = np.flatnonzero(date_codes == code)
        if len(idx) <= shift:
            continue
        day_mask = mask[idx]
        shifted = np.zeros_like(day_mask, dtype=bool)
        shifted[shift:] = day_mask[:-shift]
        out[idx] = shifted
    return out


def cost_array(
    model: str,
    entry_spread: np.ndarray,
    exit_spread: np.ndarray,
) -> np.ndarray:
    entry = np.nan_to_num(entry_spread, nan=np.nanmedian(entry_spread[np.isfinite(entry_spread)]) if np.isfinite(entry_spread).any() else 0.0)
    exit_ = np.nan_to_num(exit_spread, nan=np.nanmedian(exit_spread[np.isfinite(exit_spread)]) if np.isfinite(exit_spread).any() else 0.0)
    spread_pair = entry + exit_
    if model == "toy_mid":
        return np.zeros_like(entry, dtype="float64")
    if model == "toy_maker_light":
        return 1.0 + 0.25 * spread_pair
    if model == "toy_taker_spread":
        return 2.0 + 0.50 * spread_pair
    if model == "toy_wide_stress":
        return 5.0 + spread_pair
    raise ValueError(f"unknown cost model {model}")


def profit_factor(net: np.ndarray) -> float:
    gains = net[net > 0].sum()
    losses = -net[net < 0].sum()
    if losses <= EPS:
        return np.inf if gains > EPS else np.nan
    return float(gains / losses)


def daily_stats(net: np.ndarray, date_codes: np.ndarray) -> tuple[float, float, float, float]:
    if len(net) == 0:
        return np.nan, np.nan, np.nan, np.nan
    daily = pd.DataFrame({"date_code": date_codes, "net": net}).groupby("date_code", sort=True)["net"].sum()
    vals = daily.to_numpy(dtype="float64")
    positive_day_rate = float((vals > 0).mean()) if len(vals) else np.nan
    mean_daily = float(vals.mean()) if len(vals) else np.nan
    std_daily = float(vals.std(ddof=1)) if len(vals) > 1 else np.nan
    t_stat = float(mean_daily / (std_daily / math.sqrt(len(vals)))) if len(vals) > 1 and std_daily > EPS else np.nan
    denom = float(np.abs(vals).sum())
    max_share = float(np.abs(vals).max() / denom) if denom > EPS else np.nan
    return positive_day_rate, mean_daily, t_stat, max_share


def status_for_row(row: dict[str, object]) -> str:
    entries = int(row["entries"])
    net = float(row["net_mean_bps"])
    gross = float(row["gross_mean_bps"])
    positive_day_rate = float(row["positive_day_rate"]) if row["positive_day_rate"] != "" else np.nan
    max_single_day = float(row["max_single_day_abs_share"]) if row["max_single_day_abs_share"] != "" else np.nan
    cost_model = str(row["cost_model"])
    if entries < 40:
        return "too_few_nonoverlap_entries"
    if cost_model != "toy_mid" and net > 0.0 and positive_day_rate >= 0.55 and max_single_day <= 0.45:
        return "survives_toy_cost_research_probe"
    if gross > 0.0 and net <= 0.0:
        return "gross_only_cost_failed"
    if gross > 0.0:
        return "gross_positive_research_probe"
    return "negative_or_flat"


def evaluate_entries(
    df: pd.DataFrame,
    target: TargetSpec,
    mask: np.ndarray,
    direction: np.ndarray,
    cost_models: list[str],
    base_fields: dict[str, object],
) -> list[dict[str, object]]:
    target_values = df[target.name].to_numpy(dtype="float64")
    exit_idx = df[target.exit_col].to_numpy(dtype="int64")
    buckets = df[target.bucket_col].to_numpy(dtype="int64")
    spread = df["spread_bps"].to_numpy(dtype="float64")
    date_codes = df["date_code"].to_numpy(dtype="int64")
    valid_mask = mask & np.isfinite(target_values) & (exit_idx >= 0) & (direction != 0)
    selected_rows = int(valid_mask.sum())
    candidate_idx = np.flatnonzero(valid_mask)
    entry_idx = first_per_bucket(candidate_idx, buckets)
    if len(entry_idx) == 0:
        rows = []
        for model in cost_models:
            row = {
                **base_fields,
                "cost_model": model,
                "selected_rows": selected_rows,
                "entries": 0,
                "gross_mean_bps": np.nan,
                "gross_median_bps": np.nan,
                "net_mean_bps": np.nan,
                "net_median_bps": np.nan,
                "win_rate": np.nan,
                "profit_factor": np.nan,
                "positive_day_rate": np.nan,
                "daily_net_mean_bps": np.nan,
                "daily_net_t_stat": np.nan,
                "max_single_day_abs_share": np.nan,
                "avg_cost_bps": np.nan,
                "score": np.nan,
                "research_status": "no_entries",
                "guardrail": GUARDRAIL,
            }
            rows.append(row)
        return rows

    exits = exit_idx[entry_idx]
    gross = direction[entry_idx].astype("float64") * target_values[entry_idx]
    entry_spread = spread[entry_idx]
    exit_spread = spread[exits]
    entry_dates = date_codes[entry_idx]
    rows = []
    for model in cost_models:
        costs = cost_array(model, entry_spread, exit_spread)
        net = gross - costs
        positive_day_rate, daily_mean, daily_t, max_share = daily_stats(net, entry_dates)
        score = float(np.nanmean(net)) if len(net) else np.nan
        if np.isfinite(score):
            consistency = (positive_day_rate - 0.5) if np.isfinite(positive_day_rate) else 0.0
            concentration_penalty = max(0.0, max_share - 0.45) if np.isfinite(max_share) else 0.0
            score = score * math.sqrt(min(len(net), 5000) / 500.0) + 2.0 * consistency - 2.0 * concentration_penalty
        row = {
            **base_fields,
            "cost_model": model,
            "selected_rows": selected_rows,
            "entries": int(len(net)),
            "gross_mean_bps": finite_mean(gross),
            "gross_median_bps": finite_quantile(gross, 0.50),
            "net_mean_bps": finite_mean(net),
            "net_median_bps": finite_quantile(net, 0.50),
            "win_rate": float((net > 0).mean()) if len(net) else np.nan,
            "profit_factor": profit_factor(net),
            "positive_day_rate": positive_day_rate,
            "daily_net_mean_bps": daily_mean,
            "daily_net_t_stat": daily_t,
            "max_single_day_abs_share": max_share,
            "avg_cost_bps": finite_mean(costs),
            "score": score,
            "guardrail": GUARDRAIL,
        }
        row["research_status"] = status_for_row(row)
        rows.append(row)
    return rows


def run_strategy_grid(
    df: pd.DataFrame,
    features: list[str],
    targets: list[TargetSpec],
    folds: list[Fold],
    filter_masks: dict[str, np.ndarray],
    quantiles: list[float],
    policies: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    dates = df["date"].astype(str).to_numpy()
    cache: dict[tuple[str, bytes], np.ndarray] = {}
    for fold in folds:
        train_mask = np.isin(dates, fold.train_dates)
        test_mask = np.isin(dates, fold.test_dates)
        print(
            f"strategy grid fold={fold.name} train_days={len(fold.train_dates)} test_days={len(fold.test_dates)}",
            flush=True,
        )
        for feature in features:
            values = feature_values_for_fold(df, feature, train_mask, cache)
            for target in targets:
                finite_target = np.isfinite(df[target.name].to_numpy(dtype="float64"))
                effective_test = test_mask & finite_target
                for quantile in quantiles:
                    for policy in policies:
                        for filter_name, filter_mask in filter_masks.items():
                            mask, direction, q_low, q_high = build_policy_mask(
                                values,
                                train_mask,
                                effective_test,
                                filter_mask,
                                quantile,
                                policy,
                            )
                            base = {
                                "run_tag": RUN_TAG,
                                "source_run_tag": SOURCE_RUN_TAG,
                                "fold": fold.name,
                                "train_start_date": fold.train_dates[0],
                                "train_end_date": fold.train_dates[-1],
                                "test_start_date": fold.test_dates[0],
                                "test_end_date": fold.test_dates[-1],
                                "feature": feature,
                                "feature_family": feature_family(feature),
                                "target": target.name,
                                "horizon_kind": target.horizon_kind,
                                "horizon_value": target.horizon_value,
                                "policy": policy,
                                "filter": filter_name,
                                "quantile": quantile,
                                "q_low": q_low,
                                "q_high": q_high,
                            }
                            rows.extend(evaluate_entries(df, target, mask, direction, COST_MODELS, base))
    return pd.DataFrame(rows)


def run_controls(
    df: pd.DataFrame,
    candidate_rows: pd.DataFrame,
    features: list[str],
    targets: list[TargetSpec],
    folds: list[Fold],
    filter_masks: dict[str, np.ndarray],
    quantiles: list[float],
    policies: list[str],
    top_n: int,
    control_shift_events: int,
) -> pd.DataFrame:
    if candidate_rows.empty:
        return pd.DataFrame()
    target_map = {target.name: target for target in targets}
    fold_map = {fold.name: fold for fold in folds}
    dates = df["date"].astype(str).to_numpy()
    date_codes = df["date_code"].to_numpy(dtype="int64")
    cache: dict[tuple[str, bytes], np.ndarray] = {}
    ranked = candidate_rows[
        candidate_rows["cost_model"].eq("toy_mid")
        & candidate_rows["entries"].ge(40)
        & np.isfinite(pd.to_numeric(candidate_rows["gross_mean_bps"], errors="coerce"))
    ].copy()
    if ranked.empty:
        return pd.DataFrame()
    ranked["abs_gross"] = pd.to_numeric(ranked["gross_mean_bps"], errors="coerce").abs()
    ranked = ranked.sort_values(["abs_gross", "entries"], ascending=[False, False]).head(top_n)
    rows: list[dict[str, object]] = []
    for row in ranked.itertuples(index=False):
        fold = fold_map[row.fold]
        target = target_map[row.target]
        train_mask = np.isin(dates, fold.train_dates)
        test_mask = np.isin(dates, fold.test_dates) & np.isfinite(df[target.name].to_numpy(dtype="float64"))
        filter_mask = filter_masks[row.filter]
        values = feature_values_for_fold(df, row.feature, train_mask, cache)
        base_mask, base_direction, _, _ = build_policy_mask(
            values,
            train_mask,
            test_mask,
            filter_mask,
            float(row.quantile),
            row.policy,
        )
        controls = {
            "base_toy_mid": (base_mask, base_direction),
            "reversed_side": (base_mask, (base_direction * -1).astype("int8")),
            "within_day_shifted_signal": (
                shifted_within_day(base_mask, date_codes, control_shift_events),
                shifted_within_day(base_direction != 0, date_codes, control_shift_events).astype("int8")
                * np.where(shifted_within_day(base_direction > 0, date_codes, control_shift_events), 1, -1).astype("int8"),
            ),
        }
        past_col = f"past_{target.horizon_kind}_{target.horizon_value}{'s' if target.horizon_kind == 'time' else ''}_bps"
        if past_col in df.columns:
            past_values = df[past_col].to_numpy(dtype="float64")
            past_mask, past_direction, _, _ = build_policy_mask(
                past_values,
                train_mask,
                test_mask,
                filter_mask,
                float(row.quantile),
                "follow_extremes",
            )
            controls["past_return_gate"] = (past_mask, past_direction)

        for control_name, (mask, direction) in controls.items():
            base = {
                "run_tag": RUN_TAG,
                "source_run_tag": SOURCE_RUN_TAG,
                "fold": row.fold,
                "feature": row.feature,
                "target": row.target,
                "policy": row.policy,
                "filter": row.filter,
                "quantile": row.quantile,
                "control": control_name,
            }
            control_rows = evaluate_entries(df, target, mask, direction, ["toy_mid"], base)
            rows.extend(control_rows)
    return pd.DataFrame(rows)


def quality_rows(df: pd.DataFrame, features: list[str], targets: list[TargetSpec], folds: list[Fold]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, g in df.groupby("date", sort=True):
        row = {
            "run_tag": RUN_TAG,
            "source_run_tag": SOURCE_RUN_TAG,
            "date": date,
            "rows": len(g),
            "distinct_mid": int(g["mid_price"].nunique(dropna=True)),
            "mid_change_rate": finite_mean(g["mid_change_prev"].astype(float).to_numpy()),
            "quote_change_rate": finite_mean(g["quote_change_prev"].astype(float).to_numpy()),
            "top_size_change_rate": finite_mean(g["top_size_change_prev"].astype(float).to_numpy()),
            "trade_present_rate": finite_mean((g["trade_window_count"].fillna(0) > 0).astype(float).to_numpy()),
            "spread_p50_bps": finite_quantile(g["spread_bps"].to_numpy(dtype="float64"), 0.50),
            "spread_p95_bps": finite_quantile(g["spread_bps"].to_numpy(dtype="float64"), 0.95),
            "features_tested": " ".join(features),
            "folds": " ".join(fold.name for fold in folds),
            "guardrail": GUARDRAIL,
        }
        for target in targets:
            vals = g[target.name].to_numpy(dtype="float64")
            valid = np.isfinite(vals)
            row[f"{target.name}_valid_rows"] = int(valid.sum())
            row[f"{target.name}_nonzero_rate"] = float((np.abs(vals[valid]) > EPS).mean()) if valid.any() else np.nan
            row[f"{target.name}_abs_p90_bps"] = finite_quantile(np.abs(vals[valid]), 0.90)
        rows.append(row)
    return pd.DataFrame(rows)


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def top_table(df: pd.DataFrame, rows: int, cols: list[str]) -> list[str]:
    if df.empty:
        return ["No rows."]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in df.head(rows).itertuples(index=False):
        values = []
        for col in cols:
            value = getattr(row, col)
            if isinstance(value, float):
                values.append(fmt_num(value, 4))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def write_report(
    paths: Paths,
    quality: pd.DataFrame,
    candidates: pd.DataFrame,
    controls: pd.DataFrame,
    features: list[str],
    targets: list[TargetSpec],
    folds: list[Fold],
    quantiles: list[float],
    policies: list[str],
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT Strategy Research Overlay")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from source panel `{paths.source_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This is a toy replay research overlay. It is not queue-position fill evidence, not live execution simulation, "
        "not trading advice, and not an alpha claim."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Panel rows loaded: `{int(quality['rows'].sum()) if not quality.empty else 0}`.")
    lines.append(f"- Dates: `{quality['date'].nunique() if not quality.empty else 0}`.")
    lines.append(f"- Features tested: `{len(features)}` -> `{', '.join(features)}`.")
    lines.append(f"- Targets: `{', '.join(target.name for target in targets)}`.")
    lines.append(f"- Walk-forward folds: `{', '.join(fold.name for fold in folds)}`.")
    lines.append(f"- Quantile gates: `{', '.join(fmt_num(q, 2) for q in quantiles)}`.")
    lines.append(
        f"- Policy families: `{', '.join(policies)}`; activity/stale filters; "
        "non-overlap first-entry-per-horizon buckets."
    )
    lines.append("- Toy costs: `toy_mid`, `toy_maker_light`, `toy_taker_spread`, `toy_wide_stress`.")
    lines.append("")
    lines.append("## Data Read")
    lines.append("")
    if not quality.empty:
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| median quote-change rate | {fmt_num(quality['quote_change_rate'].median() * 100, 2)}% |")
        lines.append(f"| median top-size-change rate | {fmt_num(quality['top_size_change_rate'].median() * 100, 2)}% |")
        lines.append(f"| median trade-present rate | {fmt_num(quality['trade_present_rate'].median() * 100, 2)}% |")
        lines.append(f"| median spread | {fmt_num(quality['spread_p50_bps'].median(), 4)} bps |")
        lines.append(f"| p95 spread median-by-day | {fmt_num(quality['spread_p95_bps'].median(), 4)} bps |")
    lines.append("")
    lines.append(
        "The important semantic caveat is unchanged: CCUSDT is a snapshot-frame factor panel. A positive toy-mid row can be a "
        "valid information diagnostic while still failing as an executable strategy once spread/fee/fill uncertainty is applied."
    )
    lines.append("")

    if not candidates.empty:
        numeric_cols = [
            "entries",
            "gross_mean_bps",
            "net_mean_bps",
            "win_rate",
            "positive_day_rate",
            "max_single_day_abs_share",
            "score",
        ]
        for col in numeric_cols:
            candidates[col] = pd.to_numeric(candidates[col], errors="coerce")
        mid = candidates[candidates["cost_model"].eq("toy_mid")].copy()
        cost = candidates[
            candidates["cost_model"].isin(["toy_maker_light", "toy_taker_spread", "toy_wide_stress"])
        ].copy()
        top_mid = mid[mid["entries"].ge(40)].sort_values("score", ascending=False)
        top_cost = cost[
            cost["research_status"].eq("survives_toy_cost_research_probe") & cost["entries"].ge(40)
        ].sort_values("score", ascending=False)
        gross_failed = candidates[
            candidates["research_status"].eq("gross_only_cost_failed") & candidates["entries"].ge(40)
        ].sort_values("gross_mean_bps", ascending=False)
        display_dupe_cols = [
            "fold",
            "feature",
            "target",
            "policy",
            "cost_model",
            "entries",
            "gross_mean_bps",
            "net_mean_bps",
        ]
        top_mid_display = top_mid.drop_duplicates(subset=[col for col in display_dupe_cols if col in top_mid.columns])
        top_cost_display = top_cost.drop_duplicates(subset=[col for col in display_dupe_cols if col in top_cost.columns])
        gross_failed_display = gross_failed.drop_duplicates(
            subset=[col for col in display_dupe_cols if col in gross_failed.columns]
        )

        lines.append("## Top Toy-Mid Probes")
        lines.append("")
        lines.extend(
            top_table(
                top_mid_display,
                12,
                [
                    "fold",
                    "feature",
                    "target",
                    "policy",
                    "filter",
                    "quantile",
                    "entries",
                    "gross_mean_bps",
                    "positive_day_rate",
                    "score",
                ],
            )
        )
        lines.append("")
        lines.append("## Toy-Cost Survivors")
        lines.append("")
        if top_cost_display.empty:
            lines.append("No row cleared the toy-cost research-probe gate.")
        else:
            lines.extend(
                top_table(
                    top_cost_display,
                    12,
                    [
                        "fold",
                        "feature",
                        "target",
                        "policy",
                        "filter",
                        "cost_model",
                        "entries",
                        "net_mean_bps",
                        "positive_day_rate",
                        "score",
                    ],
                )
            )
        lines.append("")
        lines.append("## Gross-Only Cost Failures")
        lines.append("")
        lines.extend(
            top_table(
                gross_failed_display,
                12,
                [
                    "fold",
                    "feature",
                    "target",
                    "policy",
                    "filter",
                    "cost_model",
                    "entries",
                    "gross_mean_bps",
                    "net_mean_bps",
                    "avg_cost_bps",
                    "research_status",
                ],
            )
        )
        lines.append("")
    if not controls.empty:
        for col in ["entries", "gross_mean_bps", "net_mean_bps", "score"]:
            controls[col] = pd.to_numeric(controls[col], errors="coerce")
        lines.append("## Controls")
        lines.append("")
        control_summary = (
            controls.groupby("control", sort=True)
            .agg(
                rows=("control", "size"),
                median_entries=("entries", "median"),
                median_net_mean_bps=("net_mean_bps", "median"),
                p90_abs_net_mean_bps=("net_mean_bps", lambda s: float(np.nanpercentile(np.abs(s), 90))),
            )
            .reset_index()
            .sort_values("p90_abs_net_mean_bps", ascending=False)
        )
        lines.extend(top_table(control_summary, 12, list(control_summary.columns)))
        lines.append("")
        lines.append(
            "If `past_return_gate` or `within_day_shifted_signal` remains strong, the factor opportunity should be read as "
            "state persistence or recent-move structure rather than a standalone tradable rule."
        )
        lines.append("")

    lines.append("## Strategy Read")
    lines.append("")
    if candidates.empty:
        lines.append("No candidate rows were produced.")
    else:
        work = candidates.copy()
        for col in ["entries", "gross_mean_bps", "net_mean_bps", "score", "positive_day_rate"]:
            work[col] = pd.to_numeric(work[col], errors="coerce")
        survivors = work[work["research_status"].eq("survives_toy_cost_research_probe")].copy()
        survivor_counts = (
            survivors.groupby(["fold", "cost_model"], sort=True).size().reset_index(name="rows")
            if not survivors.empty
            else pd.DataFrame(columns=["fold", "cost_model", "rows"])
        )
        lines.append(
            f"- Toy-cost survivor rows: `{len(survivors)}`; by fold/cost: "
            + (
                ", ".join(
                    f"{row.fold}/{row.cost_model}={int(row.rows)}"
                    for row in survivor_counts.itertuples(index=False)
                )
                if not survivor_counts.empty
                else "none"
            )
            + "."
        )
        maker = survivors[survivors["cost_model"].eq("toy_maker_light")].sort_values("score", ascending=False)
        taker = survivors[survivors["cost_model"].eq("toy_taker_spread")].sort_values("score", ascending=False)
        if not maker.empty:
            row = maker.iloc[0]
            lines.append(
                "- Best maker-light research probe: "
                f"`{row['feature']} / {row['target']} / {row['policy']} / {row['filter']}` "
                f"in `{row['fold']}`, entries `{int(row['entries'])}`, "
                f"net `{fmt_num(row['net_mean_bps'])}` bps, positive-day `{fmt_num(row['positive_day_rate'] * 100, 2)}%`."
            )
        if not taker.empty:
            row = taker.iloc[0]
            lines.append(
                "- Best taker-spread research probe: "
                f"`{row['feature']} / {row['target']} / {row['policy']} / {row['filter']}` "
                f"in `{row['fold']}`, entries `{int(row['entries'])}`, "
                f"net `{fmt_num(row['net_mean_bps'])}` bps, positive-day `{fmt_num(row['positive_day_rate'] * 100, 2)}%`."
            )
        if not survivors.empty:
            feature_counts = survivors.groupby("feature", sort=True).size().sort_values(ascending=False).head(5)
            lines.append(
                "- Survivor concentration by feature: "
                + ", ".join(f"`{feature}`={int(count)}" for feature, count in feature_counts.items())
                + "."
            )
        lines.append(
            "- Conservative read: `trade_flow_imbalance` is the only primary strategy-research thread. MLOFI and book-pressure "
            "composites are secondary confirmation/probe material, not standalone strategy evidence."
        )
        lines.append(
            "- Promotion blocker: the passing rows still use midpoint labels over a `factor_panel_only` snapshot panel. "
            "Queue priority, partial fills, latency, and real fee tier are not represented."
        )
    lines.append("")

    lines.append("## Current Read")
    lines.append("")
    lines.append(
        "There are real factor opportunities worth studying, but none should be promoted to executable strategy status from this "
        "overlay alone. The useful next step is a quote-transition/residual-target pass: evaluate only true post-signal quote moves, "
        "remove recent-return state explicitly, and keep stale snapshot runs separate from event-active rows."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    lines.append(f"- `{paths.quality_csv}`")
    lines.append(f"- `{paths.candidate_csv}`")
    lines.append(f"- `{paths.control_csv}`")
    lines.append(f"- `{paths.summary_json}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("python scripts/ccusdt_strategy_research.py")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    paths: Paths,
    quality: pd.DataFrame,
    candidates: pd.DataFrame,
    controls: pd.DataFrame,
    features: list[str],
    targets: list[TargetSpec],
    folds: list[Fold],
    quantiles: list[float],
    policies: list[str],
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    quality.to_csv(paths.quality_csv, index=False)
    candidates.to_csv(paths.candidate_csv, index=False)
    controls.to_csv(paths.control_csv, index=False)

    survived = int(candidates["research_status"].eq("survives_toy_cost_research_probe").sum()) if not candidates.empty else 0
    gross_only = int(candidates["research_status"].eq("gross_only_cost_failed").sum()) if not candidates.empty else 0
    best_mid: dict[str, object] = {}
    if not candidates.empty:
        mid = candidates[candidates["cost_model"].eq("toy_mid")].copy()
        mid["score"] = pd.to_numeric(mid["score"], errors="coerce")
        mid = mid.sort_values("score", ascending=False)
        if not mid.empty:
            best_mid = mid.head(1).to_dict(orient="records")[0]

    summary = {
        "run_tag": paths.run_tag,
        "source_run_tag": paths.source_run_tag,
        "guardrail": GUARDRAIL,
        "rows": int(quality["rows"].sum()) if not quality.empty else 0,
        "dates": int(quality["date"].nunique()) if not quality.empty else 0,
        "features": features,
        "targets": [target.name for target in targets],
        "folds": [
            {"name": fold.name, "train_dates": list(fold.train_dates), "test_dates": list(fold.test_dates)}
            for fold in folds
        ],
        "quantiles": quantiles,
        "policies": policies,
        "candidate_rows": int(len(candidates)),
        "control_rows": int(len(controls)),
        "toy_cost_survivor_rows": survived,
        "gross_only_cost_failed_rows": gross_only,
        "best_toy_mid_probe": best_mid,
        "outputs": {
            "quality_csv": str(paths.quality_csv),
            "candidate_csv": str(paths.candidate_csv),
            "control_csv": str(paths.control_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, quality, candidates, controls, features, targets, folds, quantiles, policies)


def main() -> None:
    args = parse_args()
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
        method_sweep_run_tag=args.method_sweep_run_tag,
    )
    event_horizons = parse_ints(args.event_horizons)
    time_horizons = parse_ints(args.time_horizons_sec)
    quantiles = parse_floats(args.quantiles)

    df, usable_features = load_panel(paths)
    df, targets = add_replay_labels(df, event_horizons, time_horizons)
    dates = sorted(df["date"].dropna().astype(str).unique())
    folds = make_folds(dates)
    features = select_candidate_features(paths, usable_features, args.max_auto_features)
    filters = build_filter_masks(df)
    requested_filters = parse_strings(args.filters)
    missing_filters = [name for name in requested_filters if name not in filters]
    if missing_filters:
        raise ValueError(f"unknown filters: {missing_filters}; available={sorted(filters)}")
    filter_masks = {name: filters[name] for name in requested_filters}
    policies = parse_strings(args.policies)
    valid_policies = {"follow_extremes", "fade_extremes", "long_high", "short_low", "long_low", "short_high"}
    unknown_policies = [policy for policy in policies if policy not in valid_policies]
    if unknown_policies:
        raise ValueError(f"unknown policies: {unknown_policies}; available={sorted(valid_policies)}")

    print(
        f"features={len(features)} targets={len(targets)} folds={len(folds)} "
        f"filters={len(filter_masks)} policies={len(policies)}",
        flush=True,
    )
    quality = quality_rows(df, features, targets, folds)
    candidates = run_strategy_grid(df, features, targets, folds, filter_masks, quantiles, policies)
    print(f"candidate rows={len(candidates)}", flush=True)
    controls = run_controls(
        df,
        candidates,
        features,
        targets,
        folds,
        filter_masks,
        quantiles,
        policies,
        args.top_control_strategies,
        args.control_shift_events,
    )
    print(f"control rows={len(controls)}", flush=True)
    write_outputs(paths, quality, candidates, controls, features, targets, folds, quantiles, policies)
    print(f"wrote {paths.candidate_csv}", flush=True)
    print(f"wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
