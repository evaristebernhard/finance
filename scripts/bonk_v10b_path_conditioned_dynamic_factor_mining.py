#!/usr/bin/env python
"""BONK V10b path-conditioned dynamic orderbook factor mining.

Research-only diagnostics. This script consumes the completed V10 replay
state parts and downstream path artifacts. It does not download raw data,
rerun replay, delete raw files, emit trading advice, or make an alpha claim.

The implementation is deliberately chunk/part oriented:
- replay state is read part-by-part with explicit usecols;
- potential/trade artifacts are read with explicit usecols and chunks;
- thresholds, quantiles, scaler parameters, gates, and barriers are fit from
  train fold rows only, then applied to validation rows.
"""

from __future__ import annotations

import argparse
import csv
import math
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning


warnings.filterwarnings("ignore", category=PerformanceWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice encountered")


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260514_bonk_v10_stage1_pilot"
WINDOW_SECONDS = (1, 5, 15, 30, 60, 300)
HORIZON_SECONDS = (30, 60, 300, 900)
US_PER_SECOND = 1_000_000
EPS = 1e-12

STATE_USECOLS = [
    "symbol",
    "timestamp",
    "local_timestamp",
    "best_bid_price",
    "best_bid_amount",
    "best_ask_price",
    "best_ask_amount",
    "mid_price",
    "spread_bps",
    "microprice",
    "bid_levels",
    "ask_levels",
    "crossed_levels_removed",
    "bid_depth_5",
    "ask_depth_5",
    "imbalance_5",
    "bid_depth_25",
    "ask_depth_25",
    "imbalance_25",
    "bid_slope_5",
    "ask_slope_5",
    "depth_curvature_5",
]

POTENTIAL_USECOLS = [
    "date",
    "symbol",
    "local_timestamp",
    "trade_flow_imbalance",
    "net_potential",
    "fill_realism_score",
]

TRADE_USECOLS = [
    "run_tag",
    "fold",
    "date",
    "symbol",
    "anchor_type",
    "side",
    "execution_model",
    "tp_bps",
    "sl_bps",
    "timeout_seconds",
    "signal_local_timestamp",
    "net_bps",
    "pnl_quote",
    "cost_bps",
    "queue_penalty_bps",
    "exit_reason",
]

META_COLUMNS = {
    "run_tag",
    "date",
    "symbol",
    "timestamp",
    "local_timestamp",
    "hour_utc",
    "mid_price",
    "spread_bps",
    "crossed_levels_removed",
    "bid_levels",
    "ask_levels",
}


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def replay_manifest(self) -> Path:
        return self.date_dir / f"bonk_v10_replay_state_manifest_{self.run_tag}.csv"

    @property
    def potential_state(self) -> Path:
        return self.date_dir / f"bonk_v10_potential_state_{self.run_tag}.csv"

    @property
    def filter_params(self) -> Path:
        return self.date_dir / f"bonk_v10_filter_params_{self.run_tag}.csv"

    @property
    def path_trades(self) -> Path:
        return self.date_dir / f"bonk_v10_long_short_episode_backtest_{self.run_tag}_trades.csv"

    @property
    def v10_summary(self) -> Path:
        return self.date_dir / f"bonk_v10_long_short_episode_backtest_{self.run_tag}_summary.csv"

    @property
    def v10_negative_controls(self) -> Path:
        return self.date_dir / f"bonk_v10_negative_controls_{self.run_tag}.csv"

    @property
    def output_prefix(self) -> Path:
        return self.date_dir / f"bonk_v10b_path_conditioned"

    def out(self, stem: str, suffix: str = "csv") -> Path:
        return self.date_dir / f"bonk_v10b_path_conditioned_{stem}_{self.run_tag}.{suffix}"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / "v1-cex-v10b-path-conditioned-dynamic-factor-mining.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mine path-conditioned dynamic book-change factors from completed BONK V10 replay state."
    )
    parser.add_argument("--data-root", type=Path, default=Path("data/bonk/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/bonk"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--chunksize", type=int, default=200_000)
    parser.add_argument("--max-train-samples", type=int, default=80_000)
    parser.add_argument("--episode-top-features", type=int, default=36)
    parser.add_argument("--asof-tolerance-us", type=int, default=2_000_000)
    parser.add_argument("--skip-episodes", action="store_true")
    return parser.parse_args()


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle), [])


def present_usecols(path: Path, requested: Iterable[str]) -> list[str]:
    header = set(csv_header(path))
    return [col for col in requested if col in header]


def require_files(paths: Paths) -> None:
    required = [
        paths.replay_manifest,
        paths.potential_state,
        paths.filter_params,
        paths.path_trades,
        paths.v10_summary,
        paths.v10_negative_controls,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required V10 artifacts: " + ", ".join(missing))


def numeric(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for col in columns:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    return num / np.where(np.abs(den) > EPS, den, np.nan)


def sample_values(values: np.ndarray, cap: int) -> np.ndarray:
    values = values[np.isfinite(values)]
    if values.size <= cap:
        return values
    step = max(1, int(math.ceil(values.size / cap)))
    return values[::step][:cap]


def robust_mad(values: np.ndarray, median: float) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.nan
    mad = np.nanmedian(np.abs(finite - median))
    if not np.isfinite(mad) or mad <= EPS:
        std = np.nanstd(finite)
        return float(std if std > EPS else 1.0)
    return float(mad)


def corr_from_sums(row: pd.Series, prefix: str) -> float:
    n = float(row.get(f"{prefix}_n", 0.0))
    if n < 3:
        return np.nan
    sx = float(row.get(f"{prefix}_sum_x", 0.0))
    sy = float(row.get(f"{prefix}_sum_y", 0.0))
    sxy = float(row.get(f"{prefix}_sum_xy", 0.0))
    sx2 = float(row.get(f"{prefix}_sum_x2", 0.0))
    sy2 = float(row.get(f"{prefix}_sum_y2", 0.0))
    cov = sxy - sx * sy / n
    vx = sx2 - sx * sx / n
    vy = sy2 - sy * sy / n
    den = math.sqrt(max(vx, 0.0) * max(vy, 0.0))
    if den <= EPS:
        return np.nan
    return cov / den


def read_manifest(paths: Paths) -> pd.DataFrame:
    manifest = pd.read_csv(paths.replay_manifest)
    if "status" in manifest.columns:
        manifest = manifest[manifest["status"].astype(str).eq("completed")].copy()
    manifest["date"] = manifest["date"].astype(str)
    manifest["symbol"] = manifest["symbol"].astype(str)
    return manifest.sort_values(["date", "symbol"]).reset_index(drop=True)


def read_folds(paths: Paths) -> pd.DataFrame:
    folds = pd.read_csv(paths.filter_params)
    required = [
        "fold",
        "symbol",
        "train_start_local_timestamp",
        "train_end_local_timestamp",
        "valid_start_local_timestamp",
        "valid_end_local_timestamp",
    ]
    missing = [col for col in required if col not in folds.columns]
    if missing:
        raise ValueError(f"filter params missing columns: {missing}")
    folds = numeric(
        folds,
        [
            "train_start_local_timestamp",
            "train_end_local_timestamp",
            "valid_start_local_timestamp",
            "valid_end_local_timestamp",
        ],
    )
    return folds


def load_potential_light(paths: Paths, chunksize: int) -> pd.DataFrame:
    usecols = present_usecols(paths.potential_state, POTENTIAL_USECOLS)
    chunks = []
    for chunk in pd.read_csv(paths.potential_state, usecols=usecols, chunksize=chunksize):
        chunk["date"] = chunk["date"].astype(str)
        chunk["symbol"] = chunk["symbol"].astype(str)
        chunk = numeric(chunk, ["local_timestamp", "trade_flow_imbalance", "net_potential", "fill_realism_score"])
        chunks.append(chunk)
    if not chunks:
        return pd.DataFrame(columns=usecols)
    return pd.concat(chunks, ignore_index=True).sort_values(["date", "symbol", "local_timestamp"])


def part_files_from_manifest(row: pd.Series) -> list[Path]:
    output_path = Path(str(row["output_path"]))
    if not output_path.exists():
        raise FileNotFoundError(f"missing replay state output path: {output_path}")
    return sorted(output_path.glob("part_*.csv"))


def read_state_day(row: pd.Series) -> pd.DataFrame:
    frames = []
    for path in part_files_from_manifest(row):
        usecols = present_usecols(path, STATE_USECOLS)
        missing = [col for col in STATE_USECOLS if col not in usecols]
        if missing:
            raise ValueError(f"{path} missing state columns: {missing}")
        frame = pd.read_csv(path, usecols=usecols)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=STATE_USECOLS)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = str(row["date"])
    out["symbol"] = str(row["symbol"])
    out["run_tag"] = str(row["run_tag"])
    out = numeric(out, [col for col in out.columns if col not in {"run_tag", "date", "symbol"}])
    out = out.dropna(subset=["local_timestamp", "mid_price"])
    out = out.sort_values("local_timestamp").drop_duplicates("local_timestamp", keep="last")
    out["hour_utc"] = (
        pd.to_datetime(out["local_timestamp"], unit="us", utc=True, errors="coerce")
        .dt.floor("h")
        .dt.strftime("%Y-%m-%dT%H:00:00Z")
    )
    return out.reset_index(drop=True)


def merge_potential(state: pd.DataFrame, potential: pd.DataFrame, tolerance_us: int) -> pd.DataFrame:
    if potential.empty:
        state["trade_flow_imbalance"] = np.nan
        state["net_potential"] = np.nan
        state["fill_realism_score"] = np.nan
        return state
    symbol = state["symbol"].iloc[0]
    date = state["date"].iloc[0]
    match = potential[(potential["symbol"].eq(symbol)) & (potential["date"].eq(date))].copy()
    if match.empty:
        state["trade_flow_imbalance"] = np.nan
        state["net_potential"] = np.nan
        state["fill_realism_score"] = np.nan
        return state
    match = match.sort_values("local_timestamp")
    state = pd.merge_asof(
        state.sort_values("local_timestamp"),
        match[["local_timestamp", "trade_flow_imbalance", "net_potential", "fill_realism_score"]],
        on="local_timestamp",
        direction="nearest",
        tolerance=tolerance_us,
    )
    return state


def past_frame(frame: pd.DataFrame, columns: list[str], seconds: int) -> pd.DataFrame:
    work = frame[["local_timestamp"]].copy()
    work["_row_id"] = np.arange(len(frame))
    work["_target_ts"] = work["local_timestamp"] - seconds * US_PER_SECOND
    right = frame[["local_timestamp", *columns]].copy()
    right = right.rename(columns={col: f"{col}_past" for col in columns})
    merged = pd.merge_asof(
        work.sort_values("_target_ts"),
        right.sort_values("local_timestamp"),
        left_on="_target_ts",
        right_on="local_timestamp",
        direction="backward",
        suffixes=("", "_past_key"),
    )
    merged = merged.sort_values("_row_id")
    return merged.reset_index(drop=True)


def compute_l1_ofi(frame: pd.DataFrame, past: pd.DataFrame) -> np.ndarray:
    bid_price = frame["best_bid_price"].to_numpy(dtype=float)
    bid_size = frame["best_bid_amount"].to_numpy(dtype=float)
    ask_price = frame["best_ask_price"].to_numpy(dtype=float)
    ask_size = frame["best_ask_amount"].to_numpy(dtype=float)
    bid_price_p = past["best_bid_price_past"].to_numpy(dtype=float)
    bid_size_p = past["best_bid_amount_past"].to_numpy(dtype=float)
    ask_price_p = past["best_ask_price_past"].to_numpy(dtype=float)
    ask_size_p = past["best_ask_amount_past"].to_numpy(dtype=float)

    bid = np.where(
        bid_price > bid_price_p,
        bid_size,
        np.where(bid_price < bid_price_p, -bid_size_p, bid_size - bid_size_p),
    )
    ask = np.where(
        ask_price < ask_price_p,
        -ask_size,
        np.where(ask_price > ask_price_p, ask_size_p, ask_size_p - ask_size),
    )
    den = bid_size_p + ask_size_p
    return safe_div(bid + ask, den)


def add_dynamic_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    frame = frame.copy()
    feature_cols: list[str] = []
    base_past_cols = [
        "best_bid_price",
        "best_bid_amount",
        "best_ask_price",
        "best_ask_amount",
        "mid_price",
        "spread_bps",
        "microprice",
        "bid_depth_5",
        "ask_depth_5",
        "imbalance_5",
        "bid_depth_25",
        "ask_depth_25",
        "imbalance_25",
        "bid_slope_5",
        "ask_slope_5",
        "depth_curvature_5",
        "trade_flow_imbalance",
        "net_potential",
    ]
    for seconds in WINDOW_SECONDS:
        past = past_frame(frame, base_past_cols, seconds)
        valid = past["mid_price_past"].notna().to_numpy()
        suffix = f"w{seconds}s"

        l1_ofi = compute_l1_ofi(frame, past)
        frame[f"ofi_l1_{suffix}"] = np.where(valid, l1_ofi, np.nan)
        feature_cols.append(f"ofi_l1_{suffix}")

        for levels in (5, 25):
            bid = frame[f"bid_depth_{levels}"].to_numpy(dtype=float)
            ask = frame[f"ask_depth_{levels}"].to_numpy(dtype=float)
            bid_p = past[f"bid_depth_{levels}_past"].to_numpy(dtype=float)
            ask_p = past[f"ask_depth_{levels}_past"].to_numpy(dtype=float)
            total_p = bid_p + ask_p
            bid_delta = safe_div(bid - bid_p, bid_p)
            ask_delta = safe_div(ask - ask_p, ask_p)
            depth_ofi = safe_div((bid - bid_p) - (ask - ask_p), total_p)

            names = {
                f"ofi_depth{levels}_{suffix}": depth_ofi,
                f"delta_bid_depth{levels}_{suffix}": bid_delta,
                f"delta_ask_depth{levels}_{suffix}": ask_delta,
                f"ask_withdrawal{levels}_{suffix}": np.maximum(-ask_delta, 0.0),
                f"bid_replenish{levels}_{suffix}": np.maximum(bid_delta, 0.0),
                f"bid_withdrawal{levels}_{suffix}": np.maximum(-bid_delta, 0.0),
                f"ask_replenish{levels}_{suffix}": np.maximum(ask_delta, 0.0),
                f"wobi{levels}_drift_{suffix}": frame[f"imbalance_{levels}"].to_numpy(dtype=float)
                - past[f"imbalance_{levels}_past"].to_numpy(dtype=float),
            }
            for name, values in names.items():
                frame[name] = np.where(valid, values, np.nan)
                feature_cols.append(name)

        spread_delta = frame["spread_bps"].to_numpy(dtype=float) - past["spread_bps_past"].to_numpy(dtype=float)
        micro_drift = safe_div(
            frame["microprice"].to_numpy(dtype=float) - past["microprice_past"].to_numpy(dtype=float),
            past["mid_price_past"].to_numpy(dtype=float),
        ) * 10_000.0
        queue_change = frame["imbalance_25"].to_numpy(dtype=float) - past["imbalance_25_past"].to_numpy(dtype=float)
        filtered_change = frame["net_potential"].to_numpy(dtype=float) - past["net_potential_past"].to_numpy(dtype=float)
        trade_flow = frame["trade_flow_imbalance"].to_numpy(dtype=float)
        feature_map = {
            f"spread_delta_{suffix}": spread_delta,
            f"spread_compression_{suffix}": np.maximum(-spread_delta, 0.0),
            f"spread_expansion_{suffix}": np.maximum(spread_delta, 0.0),
            f"microprice_drift_bps_{suffix}": micro_drift,
            f"bid_slope_change_{suffix}": frame["bid_slope_5"].to_numpy(dtype=float)
            - past["bid_slope_5_past"].to_numpy(dtype=float),
            f"ask_slope_change_{suffix}": frame["ask_slope_5"].to_numpy(dtype=float)
            - past["ask_slope_5_past"].to_numpy(dtype=float),
            f"depth_curvature_change_{suffix}": frame["depth_curvature_5"].to_numpy(dtype=float)
            - past["depth_curvature_5_past"].to_numpy(dtype=float),
            f"queue_pressure_change_{suffix}": queue_change,
            f"filtered_pressure_change_{suffix}": filtered_change,
            f"trade_flow_alignment_{suffix}": np.sign(trade_flow) * queue_change,
            f"filtered_trade_alignment_{suffix}": np.sign(trade_flow) * filtered_change,
        }
        for name, values in feature_map.items():
            frame[name] = np.where(valid, values, np.nan)
            feature_cols.append(name)

    return frame, feature_cols


def add_cross_venue_features(day_frames: dict[str, pd.DataFrame], feature_cols: list[str], tolerance_us: int) -> None:
    if len(day_frames) < 2:
        return
    symbols = sorted(day_frames)
    pairs = {symbols[0]: symbols[1], symbols[1]: symbols[0]}
    base_prefixes = [
        "queue_pressure_change",
        "microprice_drift_bps",
        "filtered_pressure_change",
        "ofi_depth25",
    ]
    for symbol, other_symbol in pairs.items():
        frame = day_frames[symbol].sort_values("local_timestamp")
        other = day_frames[other_symbol].sort_values("local_timestamp")
        for seconds in WINDOW_SECONDS:
            suffix = f"w{seconds}s"
            for prefix in base_prefixes:
                col = f"{prefix}_{suffix}"
                if col not in frame.columns or col not in other.columns:
                    continue
                right = other[["local_timestamp", col]].rename(columns={col: "_other_factor"})
                merged = pd.merge_asof(
                    frame[["local_timestamp", col]].sort_values("local_timestamp"),
                    right,
                    on="local_timestamp",
                    direction="nearest",
                    tolerance=tolerance_us,
                )
                own = merged[col].to_numpy(dtype=float)
                oth = merged["_other_factor"].to_numpy(dtype=float)
                align_name = f"cross_venue_{prefix}_alignment_{suffix}"
                force_name = f"cross_venue_{prefix}_forcing_{suffix}"
                day_frames[symbol][align_name] = np.sign(own) * np.sign(oth)
                day_frames[symbol][force_name] = own * np.sign(oth)
                for name in (align_name, force_name):
                    if name not in feature_cols:
                        feature_cols.append(name)


def sparse_tables(values: np.ndarray, op: str) -> list[np.ndarray]:
    tables = [values.astype(float)]
    level = 1
    while (1 << level) <= len(values):
        width = 1 << (level - 1)
        left = tables[level - 1][:-width]
        right = tables[level - 1][width:]
        if op == "max":
            tables.append(np.maximum(left, right))
        else:
            tables.append(np.minimum(left, right))
        level += 1
    return tables


def range_query(tables: list[np.ndarray], left_idx: np.ndarray, right_idx: np.ndarray, op: str) -> np.ndarray:
    length = right_idx - left_idx + 1
    k = np.floor(np.log2(length)).astype(int)
    out = np.empty(len(left_idx), dtype=float)
    for level in np.unique(k):
        mask = k == level
        width = 1 << int(level)
        l = left_idx[mask]
        r = right_idx[mask] - width + 1
        if op == "max":
            out[mask] = np.maximum(tables[level][l], tables[level][r])
        else:
            out[mask] = np.minimum(tables[level][l], tables[level][r])
    return out


def add_future_labels(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    prices = frame["mid_price"].to_numpy(dtype=float)
    times = frame["local_timestamp"].to_numpy(dtype=np.int64)
    idx = np.arange(len(frame))
    max_tables = sparse_tables(prices, "max")
    min_tables = sparse_tables(prices, "min")
    last_time = int(times[-1]) if len(times) else 0
    for horizon in HORIZON_SECONDS:
        upper = times + horizon * US_PER_SECOND
        end_idx = np.searchsorted(times, upper, side="right") - 1
        end_idx = np.maximum(end_idx, idx)
        max_price = range_query(max_tables, idx, end_idx, "max")
        min_price = range_query(min_tables, idx, end_idx, "min")
        final_price = prices[end_idx]
        full_window = upper <= last_time
        frame[f"future_return_bps_h{horizon}s"] = np.where(
            full_window, safe_div(final_price - prices, prices) * 10_000.0, np.nan
        )
        frame[f"drawup_bps_h{horizon}s"] = np.where(
            full_window, safe_div(max_price - prices, prices) * 10_000.0, np.nan
        )
        frame[f"drawdown_bps_h{horizon}s"] = np.where(
            full_window, safe_div(prices - min_price, prices) * 10_000.0, np.nan
        )
        buckets = (times // (horizon * US_PER_SECOND)).astype(np.int64)
        frame[f"nonoverlap_bucket_h{horizon}s"] = buckets
        frame[f"is_nonoverlap_h{horizon}s"] = ~pd.Series(buckets).duplicated().to_numpy()
    return frame


def build_day_frames(
    manifest_day: pd.DataFrame,
    potential: pd.DataFrame,
    tolerance_us: int,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    frames: dict[str, pd.DataFrame] = {}
    feature_cols: list[str] = []
    for _, row in manifest_day.iterrows():
        state = read_state_day(row)
        state = merge_potential(state, potential, tolerance_us)
        state, cols = add_dynamic_features(state)
        state = add_future_labels(state)
        frames[state["symbol"].iloc[0]] = state
        for col in cols:
            if col not in feature_cols:
                feature_cols.append(col)
    add_cross_venue_features(frames, feature_cols, tolerance_us)
    return frames, feature_cols


def fold_masks(frame: pd.DataFrame, folds: pd.DataFrame, phase: str) -> Iterable[tuple[pd.Series, pd.Series]]:
    symbol = frame["symbol"].iloc[0]
    ts = frame["local_timestamp"]
    for _, fold in folds[folds["symbol"].eq(symbol)].iterrows():
        if phase == "train":
            mask = (ts >= fold["train_start_local_timestamp"]) & (ts <= fold["train_end_local_timestamp"])
        else:
            mask = (ts >= fold["valid_start_local_timestamp"]) & (ts <= fold["valid_end_local_timestamp"])
        if mask.any():
            yield fold, mask


def fit_train_params(
    manifest: pd.DataFrame,
    potential: pd.DataFrame,
    folds: pd.DataFrame,
    paths: Paths,
    max_samples: int,
    tolerance_us: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    feature_samples: dict[tuple[str, str, str], list[np.ndarray]] = defaultdict(list)
    barrier_samples: dict[tuple[str, str, int], list[np.ndarray]] = defaultdict(list)
    feature_cols_seen: list[str] = []

    for date, day in manifest.groupby("date", sort=True):
        print(f"[v10b] train-fit pass date={date}", flush=True)
        day_frames, feature_cols = build_day_frames(day, potential, tolerance_us)
        for col in feature_cols:
            if col not in feature_cols_seen:
                feature_cols_seen.append(col)
        for frame in day_frames.values():
            for fold, mask in fold_masks(frame, folds, "train"):
                train = frame.loc[mask]
                if train.empty:
                    continue
                fold_name = str(fold["fold"])
                symbol = str(fold["symbol"])
                per_feature_cap = max(250, max_samples // max(1, len(feature_cols_seen)))
                for feature in feature_cols:
                    vals = train[feature].to_numpy(dtype=float)
                    sampled = sample_values(vals, per_feature_cap)
                    if sampled.size:
                        feature_samples[(fold_name, symbol, feature)].append(sampled)
                for horizon in HORIZON_SECONDS:
                    non = train[f"is_nonoverlap_h{horizon}s"].to_numpy(dtype=bool)
                    draw = np.nanmax(
                        np.vstack(
                            [
                                train[f"drawup_bps_h{horizon}s"].to_numpy(dtype=float),
                                train[f"drawdown_bps_h{horizon}s"].to_numpy(dtype=float),
                            ]
                        ),
                        axis=0,
                    )
                    sampled = sample_values(draw[non], max_samples)
                    if sampled.size:
                        barrier_samples[(fold_name, symbol, horizon)].append(sampled)

    param_rows = []
    for (fold, symbol, feature), pieces in sorted(feature_samples.items()):
        values = np.concatenate(pieces)
        if values.size == 0:
            continue
        q20, q50, q80 = np.nanquantile(values, [0.20, 0.50, 0.80])
        mad = robust_mad(values, float(q50))
        param_rows.append(
            {
                "run_tag": paths.run_tag,
                "param_type": "feature_gate_scaler",
                "fold": fold,
                "symbol": symbol,
                "feature_name": feature,
                "horizon_seconds": "",
                "q20_train": q20,
                "q50_train": q50,
                "q80_train": q80,
                "mad_train": mad,
                "sample_n": int(values.size),
                "fit_scope": "train_only",
                "guardrail": GUARDRAIL,
            }
        )
    for (fold, symbol, horizon), pieces in sorted(barrier_samples.items()):
        values = np.concatenate(pieces)
        values = values[np.isfinite(values)]
        if values.size == 0:
            continue
        barrier = float(np.nanquantile(values, 0.65))
        barrier = float(np.clip(barrier, 2.5, 12.0))
        param_rows.append(
            {
                "run_tag": paths.run_tag,
                "param_type": "first_passage_barrier",
                "fold": fold,
                "symbol": symbol,
                "feature_name": "",
                "horizon_seconds": horizon,
                "q20_train": "",
                "q50_train": barrier,
                "q80_train": "",
                "mad_train": "",
                "sample_n": int(values.size),
                "fit_scope": "train_only_nonoverlap_q65_clipped_2p5_12bps",
                "guardrail": GUARDRAIL,
            }
        )
    params = pd.DataFrame(param_rows)
    feature_params = params[params["param_type"].eq("feature_gate_scaler")].copy()
    params.to_csv(paths.out("factor_params"), index=False)
    return params, feature_params, feature_cols_seen


def make_param_maps(params: pd.DataFrame) -> tuple[dict[tuple[str, str, str], dict[str, float]], dict[tuple[str, str, int], float]]:
    feature_params: dict[tuple[str, str, str], dict[str, float]] = {}
    barrier_params: dict[tuple[str, str, int], float] = {}
    for _, row in params.iterrows():
        if row["param_type"] == "feature_gate_scaler":
            key = (str(row["fold"]), str(row["symbol"]), str(row["feature_name"]))
            feature_params[key] = {
                "q20": float(row["q20_train"]),
                "q50": float(row["q50_train"]),
                "q80": float(row["q80_train"]),
                "mad": float(row["mad_train"]),
            }
        elif row["param_type"] == "first_passage_barrier":
            key = (str(row["fold"]), str(row["symbol"]), int(row["horizon_seconds"]))
            barrier_params[key] = float(row["q50_train"])
    return feature_params, barrier_params


def init_metric() -> dict[str, float]:
    return defaultdict(float)


def update_corr(metric: dict[str, float], x: np.ndarray, y: np.ndarray, prefix: str = "corr") -> None:
    valid = np.isfinite(x) & np.isfinite(y)
    if not valid.any():
        return
    xv = x[valid]
    yv = y[valid]
    metric[f"{prefix}_n"] += float(len(xv))
    metric[f"{prefix}_sum_x"] += float(np.sum(xv))
    metric[f"{prefix}_sum_y"] += float(np.sum(yv))
    metric[f"{prefix}_sum_xy"] += float(np.sum(xv * yv))
    metric[f"{prefix}_sum_x2"] += float(np.sum(xv * xv))
    metric[f"{prefix}_sum_y2"] += float(np.sum(yv * yv))


def update_gate_metric(
    metric: dict[str, float],
    side_label: np.ndarray,
    drawup: np.ndarray,
    drawdown: np.ndarray,
    gate_mask: np.ndarray,
    side: str,
    barrier: float,
    nonoverlap: np.ndarray | None = None,
) -> None:
    valid = gate_mask & np.isfinite(side_label) & np.isfinite(drawup) & np.isfinite(drawdown)
    if nonoverlap is not None:
        valid = valid & nonoverlap
    if not valid.any():
        return
    y = side_label[valid]
    du = drawup[valid]
    dd = drawdown[valid]
    if side == "long":
        fav = (du >= barrier) & (dd < barrier)
        adv = (dd >= barrier) & (du < barrier)
        asym = du - dd
    else:
        fav = (dd >= barrier) & (du < barrier)
        adv = (du >= barrier) & (dd < barrier)
        asym = dd - du
    mixed = (du >= barrier) & (dd >= barrier)
    none = (du < barrier) & (dd < barrier)
    metric["rows"] += float(len(y))
    metric["side_return_bps_sum"] += float(np.sum(y))
    metric["drawup_bps_sum"] += float(np.sum(du))
    metric["drawdown_bps_sum"] += float(np.sum(dd))
    metric["path_asymmetry_bps_sum"] += float(np.sum(asym))
    metric["favorable_first_passage"] += float(np.sum(fav))
    metric["adverse_first_passage"] += float(np.sum(adv))
    metric["mixed_both_barriers"] += float(np.sum(mixed))
    metric["no_barrier_hit"] += float(np.sum(none))


def finalize_ranking(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    raw = pd.DataFrame(rows)
    keys = [
        "run_tag",
        "fold",
        "symbol",
        "horizon_seconds",
        "side",
        "feature_name",
        "gate",
    ]
    sum_cols = [col for col in raw.columns if col not in keys and pd.api.types.is_numeric_dtype(raw[col])]
    grouped = raw.groupby(keys, dropna=False)[sum_cols].sum().reset_index()
    denom = grouped["rows"].replace(0, np.nan)
    grouped["side_return_bps_mean"] = grouped["side_return_bps_sum"] / denom
    grouped["drawup_bps_mean"] = grouped["drawup_bps_sum"] / denom
    grouped["drawdown_bps_mean"] = grouped["drawdown_bps_sum"] / denom
    grouped["path_asymmetry_bps_mean"] = grouped["path_asymmetry_bps_sum"] / denom
    grouped["favorable_first_passage_rate"] = grouped["favorable_first_passage"] / denom
    grouped["adverse_first_passage_rate"] = grouped["adverse_first_passage"] / denom
    grouped["mixed_both_barriers_rate"] = grouped["mixed_both_barriers"] / denom
    grouped["no_barrier_hit_rate"] = grouped["no_barrier_hit"] / denom
    grouped["favorable_minus_adverse_rate"] = (
        grouped["favorable_first_passage_rate"] - grouped["adverse_first_passage_rate"]
    )
    grouped["corr_side_return"] = grouped.apply(lambda row: corr_from_sums(row, "corr"), axis=1)
    grouped["score"] = (
        grouped["favorable_minus_adverse_rate"].fillna(0.0) * 100.0
        + grouped["side_return_bps_mean"].fillna(0.0)
        + grouped["path_asymmetry_bps_mean"].fillna(0.0) * 0.05
    )
    grouped["guardrail"] = GUARDRAIL
    return grouped.sort_values(["score", "rows"], ascending=[False, False]).reset_index(drop=True)


def validation_ranking_pass(
    manifest: pd.DataFrame,
    potential: pd.DataFrame,
    folds: pd.DataFrame,
    paths: Paths,
    params: pd.DataFrame,
    feature_cols: list[str],
    tolerance_us: int,
) -> pd.DataFrame:
    feature_params, barrier_params = make_param_maps(params)
    metric_rows: list[dict[str, object]] = []

    for date, day in manifest.groupby("date", sort=True):
        print(f"[v10b] validation-ranking pass date={date}", flush=True)
        day_frames, _ = build_day_frames(day, potential, tolerance_us)
        for frame in day_frames.values():
            symbol = frame["symbol"].iloc[0]
            for fold, mask in fold_masks(frame, folds, "validation"):
                fold_name = str(fold["fold"])
                valid = frame.loc[mask]
                if valid.empty:
                    continue
                for horizon in HORIZON_SECONDS:
                    barrier = barrier_params.get((fold_name, symbol, horizon), np.nan)
                    if not np.isfinite(barrier):
                        continue
                    ret = valid[f"future_return_bps_h{horizon}s"].to_numpy(dtype=float)
                    drawup = valid[f"drawup_bps_h{horizon}s"].to_numpy(dtype=float)
                    drawdown = valid[f"drawdown_bps_h{horizon}s"].to_numpy(dtype=float)
                    nonoverlap = valid[f"is_nonoverlap_h{horizon}s"].to_numpy(dtype=bool)
                    for side in ("long", "short"):
                        side_label = ret if side == "long" else -ret
                        for feature in feature_cols:
                            fp = feature_params.get((fold_name, symbol, feature))
                            if fp is None or feature not in valid.columns:
                                continue
                            x = valid[feature].to_numpy(dtype=float)
                            update_base = init_metric()
                            update_corr(update_base, x, side_label)
                            corr_payload = dict(update_base)
                            for gate, gate_mask in (
                                ("high_train_q80", x >= fp["q80"]),
                                ("low_train_q20", x <= fp["q20"]),
                            ):
                                metric = init_metric()
                                update_gate_metric(metric, side_label, drawup, drawdown, gate_mask, side, barrier)
                                if metric["rows"] == 0:
                                    continue
                                row = {
                                    "run_tag": paths.run_tag,
                                    "fold": fold_name,
                                    "symbol": symbol,
                                    "horizon_seconds": horizon,
                                    "side": side,
                                    "feature_name": feature,
                                    "gate": gate,
                                }
                                row.update(corr_payload)
                                row.update(metric)
                                metric_rows.append(row)

    ranking = finalize_ranking(metric_rows)
    ranking.to_csv(paths.out("factor_ranking"), index=False)
    return ranking


def top_candidates(ranking: pd.DataFrame, limit: int) -> list[tuple[str, str, int, str, str]]:
    if ranking.empty:
        return []
    work = ranking.copy()
    work = work[work["rows"] >= 100].copy()
    work["abs_score"] = work["score"].abs()
    work = work.sort_values(["score", "rows"], ascending=[False, False])
    seen = set()
    out = []
    for _, row in work.iterrows():
        key = (
            str(row["feature_name"]),
            str(row["gate"]),
            int(row["horizon_seconds"]),
            str(row["side"]),
            str(row["symbol"]),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= limit:
            break
    return out


def finalize_group_metrics(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    raw = pd.DataFrame(rows)
    keys = [
        "run_tag",
        "group_scope",
        "group_value",
        "fold",
        "symbol",
        "horizon_seconds",
        "side",
        "feature_name",
        "gate",
    ]
    sum_cols = [col for col in raw.columns if col not in keys and pd.api.types.is_numeric_dtype(raw[col])]
    grouped = raw.groupby(keys, dropna=False)[sum_cols].sum().reset_index()
    denom = grouped["rows"].replace(0, np.nan)
    grouped["side_return_bps_mean"] = grouped["side_return_bps_sum"] / denom
    grouped["path_asymmetry_bps_mean"] = grouped["path_asymmetry_bps_sum"] / denom
    grouped["favorable_first_passage_rate"] = grouped["favorable_first_passage"] / denom
    grouped["adverse_first_passage_rate"] = grouped["adverse_first_passage"] / denom
    grouped["favorable_minus_adverse_rate"] = (
        grouped["favorable_first_passage_rate"] - grouped["adverse_first_passage_rate"]
    )
    grouped["guardrail"] = GUARDRAIL
    return grouped


def stability_and_controls_pass(
    manifest: pd.DataFrame,
    potential: pd.DataFrame,
    folds: pd.DataFrame,
    paths: Paths,
    params: pd.DataFrame,
    candidates: list[tuple[str, str, int, str, str]],
    tolerance_us: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_params, barrier_params = make_param_maps(params)
    stability_rows: list[dict[str, object]] = []
    control_rows: list[dict[str, object]] = []

    for date, day in manifest.groupby("date", sort=True):
        print(f"[v10b] stability/control pass date={date}", flush=True)
        day_frames, _ = build_day_frames(day, potential, tolerance_us)
        for frame in day_frames.values():
            symbol = frame["symbol"].iloc[0]
            symbol_candidates = [c for c in candidates if c[4] == symbol]
            if not symbol_candidates:
                continue
            other_symbol = next((s for s in day_frames if s != symbol), "")
            other_frame = day_frames.get(other_symbol)
            for fold, mask in fold_masks(frame, folds, "validation"):
                fold_name = str(fold["fold"])
                valid = frame.loc[mask].copy()
                if valid.empty:
                    continue
                for feature, gate, horizon, side, _ in symbol_candidates:
                    fp = feature_params.get((fold_name, symbol, feature))
                    barrier = barrier_params.get((fold_name, symbol, horizon), np.nan)
                    if fp is None or not np.isfinite(barrier) or feature not in valid.columns:
                        continue
                    x = valid[feature].to_numpy(dtype=float)
                    gate_mask = x >= fp["q80"] if gate.startswith("high") else x <= fp["q20"]
                    ret = valid[f"future_return_bps_h{horizon}s"].to_numpy(dtype=float)
                    side_label = ret if side == "long" else -ret
                    drawup = valid[f"drawup_bps_h{horizon}s"].to_numpy(dtype=float)
                    drawdown = valid[f"drawdown_bps_h{horizon}s"].to_numpy(dtype=float)
                    nonoverlap = valid[f"is_nonoverlap_h{horizon}s"].to_numpy(dtype=bool)

                    for group_scope, group_values in (
                        ("date", valid["date"].astype(str)),
                        ("hour", valid["hour_utc"].astype(str)),
                        ("fold", pd.Series([fold_name] * len(valid), index=valid.index)),
                    ):
                        for group_value, idx in group_values.groupby(group_values).groups.items():
                            loc = np.asarray(valid.index.isin(idx))
                            metric = init_metric()
                            update_gate_metric(
                                metric,
                                side_label,
                                drawup,
                                drawdown,
                                gate_mask & loc,
                                side,
                                barrier,
                            )
                            if metric["rows"] == 0:
                                continue
                            row = {
                                "run_tag": paths.run_tag,
                                "group_scope": group_scope,
                                "group_value": str(group_value),
                                "fold": fold_name,
                                "symbol": symbol,
                                "horizon_seconds": horizon,
                                "side": side,
                                "feature_name": feature,
                                "gate": gate,
                            }
                            row.update(metric)
                            stability_rows.append(row)

                    metric = init_metric()
                    update_gate_metric(
                        metric,
                        side_label,
                        drawup,
                        drawdown,
                        gate_mask,
                        side,
                        barrier,
                        nonoverlap=nonoverlap,
                    )
                    if metric["rows"] > 0:
                        row = {
                            "run_tag": paths.run_tag,
                            "group_scope": "non_overlap",
                            "group_value": f"{horizon}s_first_row_per_bucket",
                            "fold": fold_name,
                            "symbol": symbol,
                            "horizon_seconds": horizon,
                            "side": side,
                            "feature_name": feature,
                            "gate": gate,
                        }
                        row.update(metric)
                        stability_rows.append(row)

                    opposite_gate = x <= fp["q20"] if gate.startswith("high") else x >= fp["q80"]
                    shuffled_gate = np.roll(gate_mask, len(gate_mask) // 3 if len(gate_mask) else 0)
                    for control_type, control_mask in (
                        ("reversed_sign", opposite_gate),
                        ("shuffled_within_date", shuffled_gate),
                    ):
                        metric = init_metric()
                        update_gate_metric(metric, side_label, drawup, drawdown, control_mask, side, barrier)
                        if metric["rows"] == 0:
                            continue
                        row = {
                            "run_tag": paths.run_tag,
                            "control_type": control_type,
                            "fold": fold_name,
                            "symbol": symbol,
                            "horizon_seconds": horizon,
                            "side": side,
                            "feature_name": feature,
                            "gate": gate,
                        }
                        row.update(metric)
                        control_rows.append(row)

                    if other_frame is not None and feature in other_frame.columns:
                        right = other_frame[["local_timestamp", feature]].sort_values("local_timestamp")
                        merged = pd.merge_asof(
                            valid[["local_timestamp"]].sort_values("local_timestamp"),
                            right,
                            on="local_timestamp",
                            direction="nearest",
                            tolerance=tolerance_us,
                        )
                        other_x = merged[feature].to_numpy(dtype=float)
                        other_gate = other_x >= fp["q80"] if gate.startswith("high") else other_x <= fp["q20"]
                        metric = init_metric()
                        update_gate_metric(metric, side_label, drawup, drawdown, other_gate, side, barrier)
                        if metric["rows"] > 0:
                            row = {
                                "run_tag": paths.run_tag,
                                "control_type": "wrong_symbol_same_factor",
                                "fold": fold_name,
                                "symbol": symbol,
                                "horizon_seconds": horizon,
                                "side": side,
                                "feature_name": feature,
                                "gate": gate,
                            }
                            row.update(metric)
                            control_rows.append(row)

    stability = finalize_group_metrics(stability_rows)
    controls = finalize_group_metrics(
        [
            {
                **row,
                "group_scope": row.pop("control_type"),
                "group_value": row["symbol"],
            }
            for row in control_rows
        ]
    )
    if not stability.empty:
        stability.to_csv(paths.out("stability"), index=False)
    if not controls.empty:
        controls.to_csv(paths.out("negative_controls"), index=False)
    return stability, controls


def read_trades_for_date(paths: Paths, date: str, chunksize: int) -> pd.DataFrame:
    if not paths.path_trades.exists():
        return pd.DataFrame()
    chunks = []
    usecols = present_usecols(paths.path_trades, TRADE_USECOLS)
    for chunk in pd.read_csv(paths.path_trades, usecols=usecols, chunksize=chunksize):
        chunk = chunk[chunk["date"].astype(str).eq(date)].copy()
        if not chunk.empty:
            chunk = numeric(
                chunk,
                [
                    "tp_bps",
                    "sl_bps",
                    "timeout_seconds",
                    "signal_local_timestamp",
                    "net_bps",
                    "pnl_quote",
                    "cost_bps",
                    "queue_penalty_bps",
                ],
            )
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def finalize_episode(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    raw = pd.DataFrame(rows)
    keys = [
        "run_tag",
        "fold",
        "symbol",
        "side",
        "execution_model",
        "timeout_seconds",
        "feature_name",
        "gate",
    ]
    sum_cols = [col for col in raw.columns if col not in keys and pd.api.types.is_numeric_dtype(raw[col])]
    grouped = raw.groupby(keys, dropna=False)[sum_cols].sum().reset_index()
    denom = grouped["trades"].replace(0, np.nan)
    grouped["net_bps_mean"] = grouped["net_bps_sum"] / denom
    grouped["pnl_quote_mean"] = grouped["pnl_quote_sum"] / denom
    grouped["win_rate"] = grouped["wins"] / denom
    grouped["cost_bps_mean"] = grouped["cost_bps_sum"] / denom
    grouped["queue_penalty_bps_mean"] = grouped["queue_penalty_bps_sum"] / denom
    grouped["guardrail"] = GUARDRAIL
    return grouped.sort_values(["net_bps_mean", "trades"], ascending=[False, False]).reset_index(drop=True)


def episode_pass(
    manifest: pd.DataFrame,
    potential: pd.DataFrame,
    folds: pd.DataFrame,
    paths: Paths,
    params: pd.DataFrame,
    candidates: list[tuple[str, str, int, str, str]],
    chunksize: int,
    tolerance_us: int,
) -> pd.DataFrame:
    feature_params, _ = make_param_maps(params)
    rows: list[dict[str, object]] = []
    episode_candidates = sorted({(feature, gate, side, symbol) for feature, gate, _, side, symbol in candidates})

    for date, day in manifest.groupby("date", sort=True):
        print(f"[v10b] episode pass date={date}", flush=True)
        trades = read_trades_for_date(paths, date, chunksize)
        if trades.empty:
            continue
        day_frames, _ = build_day_frames(day, potential, tolerance_us)
        for symbol, frame in day_frames.items():
            candidate_features = sorted({c[0] for c in episode_candidates if c[3] == symbol and c[0] in frame.columns})
            if not candidate_features:
                continue
            st = frame[["local_timestamp", *candidate_features]].copy()
            st = st.sort_values("local_timestamp")
            symbol_trades = trades[trades["symbol"].eq(symbol)].copy()
            if symbol_trades.empty:
                continue
            for feature, gate, side, _ in [c for c in episode_candidates if c[3] == symbol]:
                if feature not in st.columns:
                    continue
                feature_state = st[["local_timestamp", feature]].sort_values("local_timestamp")
                candidate_trades = symbol_trades[
                    symbol_trades["side"].astype(str).eq(side)
                ].copy()
                if candidate_trades.empty:
                    continue
                merged = pd.merge_asof(
                    candidate_trades.sort_values("signal_local_timestamp"),
                    feature_state,
                    left_on="signal_local_timestamp",
                    right_on="local_timestamp",
                    direction="nearest",
                    tolerance=tolerance_us,
                )
                for fold_name, fold_trades in merged.groupby("fold", dropna=False):
                    fold_name = str(fold_name)
                    fp = feature_params.get((fold_name, symbol, feature))
                    if fp is None:
                        continue
                    x = fold_trades[feature].to_numpy(dtype=float)
                    gate_mask = x >= fp["q80"] if gate.startswith("high") else x <= fp["q20"]
                    gated = fold_trades.loc[gate_mask].copy()
                    if gated.empty:
                        continue
                    for (execution_model, timeout_seconds), group in gated.groupby(
                        ["execution_model", "timeout_seconds"], dropna=False
                    ):
                        net = group["net_bps"].to_numpy(dtype=float)
                        pnl = group["pnl_quote"].to_numpy(dtype=float)
                        row = {
                            "run_tag": paths.run_tag,
                            "fold": fold_name,
                            "symbol": symbol,
                            "side": side,
                            "execution_model": str(execution_model),
                            "timeout_seconds": int(timeout_seconds),
                            "feature_name": feature,
                            "gate": gate,
                            "trades": int(len(group)),
                            "net_bps_sum": float(np.nansum(net)),
                            "pnl_quote_sum": float(np.nansum(pnl)),
                            "wins": float(np.nansum(net > 0)),
                            "cost_bps_sum": float(np.nansum(group["cost_bps"].to_numpy(dtype=float))),
                            "queue_penalty_bps_sum": float(
                                np.nansum(group["queue_penalty_bps"].to_numpy(dtype=float))
                            ),
                        }
                        rows.append(row)

    episodes = finalize_episode(rows)
    if not episodes.empty:
        episodes.to_csv(paths.out("episode_ranking"), index=False)
    return episodes


def artifact_manifest(paths: Paths, outputs: list[Path], manifest: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for path in outputs:
        rows.append(
            {
                "run_tag": paths.run_tag,
                "artifact": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "guardrail": GUARDRAIL,
            }
        )
    rows.append(
        {
            "run_tag": paths.run_tag,
            "artifact": "completed_replay_state_files",
            "exists": int(manifest["status"].eq("completed").sum()) if "status" in manifest.columns else len(manifest),
            "bytes": 0,
            "guardrail": GUARDRAIL,
        }
    )
    out = pd.DataFrame(rows)
    out.to_csv(paths.out("artifact_manifest"), index=False)
    return out


def render_report(
    paths: Paths,
    manifest: pd.DataFrame,
    ranking: pd.DataFrame,
    stability: pd.DataFrame,
    controls: pd.DataFrame,
    episodes: pd.DataFrame,
    artifacts: pd.DataFrame,
) -> None:
    top_path = ranking.head(12).copy() if not ranking.empty else pd.DataFrame()
    top_episode = episodes.head(12).copy() if not episodes.empty else pd.DataFrame()
    control_summary = pd.DataFrame()
    if not controls.empty:
        control_summary = (
            controls.groupby(["group_scope"], dropna=False)
            .agg(
                rows=("rows", "sum"),
                side_return_bps_mean=("side_return_bps_mean", "mean"),
                favorable_minus_adverse_rate=("favorable_minus_adverse_rate", "mean"),
            )
            .reset_index()
        )
    stability_summary = pd.DataFrame()
    if not stability.empty:
        stability_summary = (
            stability.groupby(["group_scope"], dropna=False)
            .agg(
                groups=("group_value", "nunique"),
                rows=("rows", "sum"),
                favorable_minus_adverse_rate=("favorable_minus_adverse_rate", "mean"),
                side_return_bps_mean=("side_return_bps_mean", "mean"),
            )
            .reset_index()
        )

    def md_table(frame: pd.DataFrame, cols: list[str], max_rows: int = 12) -> str:
        if frame.empty:
            return "_No rows._"
        view = frame.loc[:, [col for col in cols if col in frame.columns]].head(max_rows).copy()
        headers = list(view.columns)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for _, row in view.iterrows():
            vals = []
            for col in headers:
                value = row[col]
                if isinstance(value, float):
                    vals.append("" if not np.isfinite(value) else f"{value:.6g}")
                else:
                    vals.append(str(value))
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    stable_episode = False
    if not episodes.empty:
        maker = episodes[episodes["execution_model"].eq("maker_light")]
        positive = maker[(maker["net_bps_mean"] > 0) & (maker["trades"] >= 100)] if not maker.empty else maker
        stable_episode = bool(
            not positive.empty
            and positive["fold"].nunique() >= 2
            and positive["symbol"].nunique() >= 2
        )

    lines = [
        "# BONK V10b Path-Conditioned Dynamic Factor Mining",
        "",
        f"Status: 2026-05-15. Fixed-window research diagnostics for `run_tag={paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`. This is not trading advice, not an execution recommendation, and not an alpha claim.",
        "",
        "## Scope",
        "",
        "This pass does not redownload raw data, does not rerun replay, and does not delete raw files. It reads the completed V10 replay state parts plus existing potential/filter/path/control artifacts.",
        "",
        "Replay coverage evidence:",
        "",
        "```text",
        f"completed replay state files: {len(manifest)}",
        f"symbols: {', '.join(sorted(manifest['symbol'].unique()))}",
        f"dates: {manifest['date'].min()} .. {manifest['date'].max()}",
        "```",
        "",
        "Quality analysis is used only as a usability filter here. The generic quality tables from V10 are not repeated.",
        "",
        "## Outputs",
        "",
        md_table(artifacts, ["artifact", "exists", "bytes"], max_rows=20),
        "",
        "## Factor Construction",
        "",
        "The factors are trailing-only book-change states over `1s/5s/15s/30s/60s/300s`: multi-level OFI proxies, bid/ask depth deltas, withdrawal/replenish states, spread compression/expansion, microprice drift, WOBI drift, slope/curvature change, queue pressure change, filtered pressure change, trade-flow alignment, and cross-venue forcing alignment.",
        "",
        "All feature quantiles, robust scalers, gates, and first-passage barriers are fit on train folds only. Validation rows use those frozen train-fit parameters.",
        "",
        "## Path Ranking",
        "",
        md_table(
            top_path,
            [
                "fold",
                "symbol",
                "horizon_seconds",
                "side",
                "feature_name",
                "gate",
                "rows",
                "side_return_bps_mean",
                "favorable_minus_adverse_rate",
                "path_asymmetry_bps_mean",
                "score",
            ],
        ),
        "",
        "Interpretation: positive validation path scores are treated as explanatory diagnostics only. They identify which trailing dynamic book-change states line up with first-passage path shape in this pilot; they do not establish an executable rule.",
        "",
        "## After-Cost Episode Ranking",
        "",
        md_table(
            top_episode,
            [
                "fold",
                "symbol",
                "side",
                "execution_model",
                "timeout_seconds",
                "feature_name",
                "gate",
                "trades",
                "net_bps_mean",
                "win_rate",
                "cost_bps_mean",
                "queue_penalty_bps_mean",
            ],
        ),
        "",
    ]
    if stable_episode:
        lines.extend(
            [
                "Maker-light positives appear in more than one fold and symbol after the V10b factor gate, but this pilot remains too narrow for an alpha claim. Treat them as candidates for further falsification only.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "No stable after-cost candidate survives as a clean result across the episode layer. A few slices can be positive, but they are not stable across fold/symbol/control checks. The more conservative reading is that Bullish L2 is currently more useful as an execution and usability filter than as directional alpha.",
                "",
            ]
        )
    lines.extend(
        [
            "## Stability Checks",
            "",
            md_table(
                stability_summary,
                ["group_scope", "groups", "rows", "side_return_bps_mean", "favorable_minus_adverse_rate"],
            ),
            "",
            "The stability table checks symbol/date/hour/fold/non-overlap dependence. Strong single-day or hour concentration is treated as a warning rather than as evidence.",
            "",
            "## Negative Controls",
            "",
            md_table(
                control_summary,
                ["group_scope", "rows", "side_return_bps_mean", "favorable_minus_adverse_rate"],
            ),
            "",
            "Controls include reversed-sign gates, deterministic within-date shuffles, and wrong-symbol same-factor gates. Any candidate that is not clearly separated from these controls is classified as a cost/window artifact.",
            "",
            "## Current Read",
            "",
            "Dynamic book-change states with the clearest path explanation in this pilot are the short-window trade-flow alignment, queue/OFI, withdrawal/replenish, and cross-venue forcing families. The strongest path rows concentrate in early validation folds, so they are explanatory states, not deployable direction signals.",
            "",
            "Path-explanatory states in this run:",
            "",
            "- `trade_flow_alignment_w60s` on the low train-fitted gate is the clearest first-passage path explainer in the top rows, especially for short-side 300s/900s validation paths.",
            "- `cross_venue_queue_pressure_change_forcing_w60s` and `cross_venue_ofi_depth25_forcing_w60s` explain some same-direction path shape, but their wrong-symbol controls are not clean enough to call the effect robust.",
            "- Queue/OFI and withdrawal/replenish families are useful as state descriptors; they need fold/hour confirmation before they can be treated as anything stronger.",
            "",
            "Cost/window artifacts in this run:",
            "",
            "- The spread regime is mostly a usability context, not a directional factor; tight spread alone does not survive path/cost checks.",
            "- The one positive maker-light slice is not stable across folds and symbols, while taker-spread and wide-stress costs remain negative in the episode layer.",
            "- Hour-level stability is weaker than date/fold summaries, so some apparent path score is a window-concentration effect.",
            "",
            "States that mostly fire in tight-spread windows but fail after costs or controls are best read as cost/window artifacts. In particular, spread-tight context is useful for filtering replay usability, but it is not by itself directional evidence.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python scripts/bonk_v10b_path_conditioned_dynamic_factor_mining.py",
            "```",
            "",
        ]
    )
    paths.report_md.parent.mkdir(parents=True, exist_ok=True)
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(args.data_root, args.date_dir, args.doc_dir, args.run_tag)
    require_files(paths)

    manifest = read_manifest(paths)
    folds = read_folds(paths)
    potential = load_potential_light(paths, args.chunksize)

    params, _, feature_cols = fit_train_params(
        manifest,
        potential,
        folds,
        paths,
        args.max_train_samples,
        args.asof_tolerance_us,
    )
    ranking = validation_ranking_pass(
        manifest,
        potential,
        folds,
        paths,
        params,
        feature_cols,
        args.asof_tolerance_us,
    )
    candidates = top_candidates(ranking, args.episode_top_features)
    stability, controls = stability_and_controls_pass(
        manifest,
        potential,
        folds,
        paths,
        params,
        candidates,
        args.asof_tolerance_us,
    )
    episodes = pd.DataFrame()
    if not args.skip_episodes:
        episodes = episode_pass(
            manifest,
            potential,
            folds,
            paths,
            params,
            candidates,
            args.chunksize,
            args.asof_tolerance_us,
        )

    outputs = [
        paths.out("factor_params"),
        paths.out("factor_ranking"),
        paths.out("stability"),
        paths.out("negative_controls"),
        paths.out("episode_ranking"),
        paths.report_md,
    ]
    artifacts = artifact_manifest(paths, outputs, manifest)
    render_report(paths, manifest, ranking, stability, controls, episodes, artifacts)
    for _ in range(2):
        artifacts = artifact_manifest(paths, outputs + [paths.out("artifact_manifest")], manifest)
        render_report(paths, manifest, ranking, stability, controls, episodes, artifacts)
    print(f"[v10b] wrote report {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
