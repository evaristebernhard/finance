#!/usr/bin/env python
"""CCUSDT medium-horizon path-structure factor fast diagnostic.

Research-only diagnostic. It builds R5-class path operators over market-visible
microstructure primitives and evaluates them against future path labels. Future
labels are diagnostic only; do not promote them into Runner or Bot runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
FIXED_EVENT_ROOT = Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/path_structure_factor_fast_diagnostic")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/factors/v1-path-structure-factor-fast-diagnostic-20260602.md")

SCHEMA_ID = "ccusdt_path_structure_factor_fast_diagnostic_v0_1"
EPS = 1e-12


@dataclass(frozen=True)
class FactorDef:
    factor_id: str
    family: str
    signed: bool
    runtime_status: str
    description: str


FACTOR_DEFS: list[FactorDef] = [
    FactorDef("price_path_efficiency", "path_geometry", False, "decision_frame_safe", "Directional efficiency of recent mid path."),
    FactorDef("signed_price_path_ratio", "path_geometry", True, "decision_frame_safe", "R-style ratio of signed recent price path."),
    FactorDef("signed_price_energy", "path_geometry", True, "decision_frame_safe", "Absolute energy in the signed recent price path."),
    FactorDef("pullback_after_release", "path_geometry", False, "decision_frame_safe", "Already-realized pullback after the best in-window move."),
    FactorDef("price_path_acceleration", "path_geometry", True, "decision_frame_safe", "Recent half-window price Z minus full-window price Z."),
    FactorDef("pressure_to_price_efficiency", "pressure_conversion", True, "decision_frame_safe", "How much mid moved per unit of signed flow pressure."),
    FactorDef("pressure_price_alignment_ratio", "pressure_conversion", True, "decision_frame_safe", "Whether pressure and quote movement agreed over the window."),
    FactorDef("absorption_rate", "absorption", True, "decision_frame_safe", "Large pressure that did not move mid inside the window."),
    FactorDef("absorption_failure_delta", "absorption", True, "decision_frame_safe", "Recent absorption weakening versus the longer window."),
    FactorDef("pressure_exhaustion_gap", "absorption", True, "decision_frame_safe", "Pressure energy not converted into price energy."),
    FactorDef("opposite_depth_giveway_ratio", "liquidity_supply", True, "decision_frame_safe_top_of_book_proxy", "Whether opposite-side depth persistently gives way."),
    FactorDef("same_side_support_ratio", "liquidity_supply", True, "decision_frame_safe_top_of_book_proxy", "Whether same-side depth support persistently strengthens."),
    FactorDef("vacuum_release_energy", "liquidity_supply", True, "decision_frame_safe_top_of_book_proxy", "Price release scaled by opposite-side visible depth."),
    FactorDef("book_asymmetry_drift_z", "liquidity_supply", True, "decision_frame_safe_top_of_book_proxy", "Path Z of book-side asymmetry drift."),
    FactorDef("opposite_depth_recovery_speed", "liquidity_supply", True, "decision_frame_safe_top_of_book_proxy", "Depth recovery after recent local minimum."),
    FactorDef("spread_compression_ratio", "execution_cost", False, "decision_frame_safe", "Whether spread/crossing cost has compressed over the window."),
    FactorDef("spread_worsening_energy", "execution_cost", False, "decision_frame_safe", "Energy of spread widening episodes."),
    FactorDef("low_cost_persistence", "execution_cost", False, "decision_frame_safe", "Share of window where spread was below trailing q70."),
    FactorDef("release_to_cost_ratio", "execution_cost", True, "decision_frame_safe", "Signed price energy normalized by average spread cost."),
    FactorDef("cost_repair_release_combo", "execution_cost", True, "decision_frame_safe", "Price-path Z times spread-compression ratio."),
    FactorDef("trade_activity_z", "activity", False, "decision_frame_safe", "Z-style path statistic of recent trade activity."),
    FactorDef("trade_burst_persistence", "activity", False, "decision_frame_safe", "R-style persistence of trade-count increases."),
    FactorDef("signed_notional_energy", "activity", True, "decision_frame_safe", "Signed notional pressure energy."),
    FactorDef("sparse_trade_noise_penalty", "activity", False, "decision_frame_safe", "Penalty flag for sparse trade windows."),
    FactorDef("quote_trade_sync_rate", "pressure_conversion", True, "decision_frame_safe", "Share of quote moves aligned with pressure direction."),
    FactorDef("vacuum_release_structure", "composite_structure", True, "decision_frame_safe_top_of_book_proxy", "Pressure, depth giveway, and path efficiency together."),
    FactorDef("absorption_failure_structure", "composite_structure", True, "decision_frame_safe", "Absorption failure with pressure and price acceleration."),
    FactorDef("cost_allowed_trend_structure", "composite_structure", True, "decision_frame_safe", "Directional path structure under acceptable cost."),
    FactorDef("chop_decay_risk", "risk_structure", False, "decision_frame_safe", "Low path efficiency plus spread-worsening risk."),
    FactorDef("executable_structure_score", "composite_structure", True, "decision_frame_safe_top_of_book_proxy", "Composite diagnostic score, not a policy model."),
]

FACTOR_BY_ID = {spec.factor_id: spec for spec in FACTOR_DEFS}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--source", choices=["decision_frame", "fixed_event", "both"], default="both")
    parser.add_argument("--windows-sec", default="30,60,120")
    parser.add_argument("--mid-horizons-sec", default="20,60")
    parser.add_argument("--release-sec", type=int, default=10)
    parser.add_argument("--executable-horizon-sec", type=int, default=60)
    parser.add_argument("--top-quantile", type=float, default=0.8)
    parser.add_argument("--bottom-quantile", type=float, default=0.2)
    parser.add_argument("--max-rows-per-day", type=int, default=0)
    parser.add_argument("--correlation-sample-rows", type=int, default=100_000)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def parse_int_list(value: str) -> list[int]:
    out = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    if not out:
        raise ValueError("expected at least one integer")
    return out


def date_range(start: str, end: str) -> Iterable[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while cur <= last:
        yield cur.isoformat()
        cur += timedelta(days=1)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def decision_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def decision_manifest_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "manifest.json"


def fixed_event_day_dir(repo_root: Path, symbol: str, day: str) -> Path | None:
    candidates: list[Path] = []
    root = repo_root / FIXED_EVENT_ROOT
    if not root.exists():
        return None
    for run_dir in root.glob("run_tag=*"):
        day_dir = run_dir / f"symbol={symbol}" / f"dt={day}"
        if day_dir.exists():
            candidates.append(day_dir)
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: str(path))[-1]


def maybe_stride(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.reset_index(drop=True)
    stride = max(1, int(math.ceil(len(df) / max_rows)))
    return df.iloc[::stride].head(max_rows).reset_index(drop=True)


def normalize_market_columns(df: pd.DataFrame, day: str, source_layer: str) -> pd.DataFrame:
    out = df.copy()
    if "local_timestamp" in out.columns and "local_ts_us" not in out.columns:
        out["local_ts_us"] = out["local_timestamp"]
    if "mid_price" in out.columns and "mid" not in out.columns:
        out["mid"] = out["mid_price"]
    if "best_bid_price" in out.columns:
        out["bid"] = out["best_bid_price"]
    if "best_ask_price" in out.columns:
        out["ask"] = out["best_ask_price"]
    if "best_bid_amount" in out.columns:
        out["bid_amount"] = out["best_bid_amount"]
    if "best_ask_amount" in out.columns:
        out["ask_amount"] = out["best_ask_amount"]

    out["date"] = str(day)
    out["source_layer"] = source_layer
    out["local_ts_us"] = pd.to_numeric(out["local_ts_us"], errors="coerce").astype("int64")
    for col in ["bid", "ask", "mid", "spread_bps", "bid_amount", "ask_amount"]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce").astype(float)

    if "bid_depth_25" in out.columns:
        out["bid_depth"] = pd.to_numeric(out["bid_depth_25"], errors="coerce").astype(float)
        out["ask_depth"] = pd.to_numeric(out["ask_depth_25"], errors="coerce").astype(float)
    elif "bid_depth_5" in out.columns:
        out["bid_depth"] = pd.to_numeric(out["bid_depth_5"], errors="coerce").astype(float)
        out["ask_depth"] = pd.to_numeric(out["ask_depth_5"], errors="coerce").astype(float)
    else:
        out["bid_depth"] = out["bid_amount"]
        out["ask_depth"] = out["ask_amount"]

    for col in [
        "trade_flow_imbalance",
        "trade_window_count",
        "trade_buy_amount",
        "trade_sell_amount",
        "trade_notional_quote",
        "ofi_l1_depth_norm",
        "mlofi_roll10_l1",
        "mlofi_roll10_l5",
        "mlofi_roll10_l25",
        "microprice_dev_bps",
        "queue_imbalance_1",
        "queue_imbalance_5",
        "depletion_bid_amount",
        "depletion_ask_amount",
        "replenish_bid_amount",
        "replenish_ask_amount",
        "cancel_bid_amount",
        "cancel_ask_amount",
    ]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype(float)

    if "trade_notional_quote" in out.columns:
        out["signed_notional"] = np.sign(out["trade_flow_imbalance"]) * out["trade_notional_quote"].abs()
    else:
        out["signed_notional"] = np.sign(out["trade_flow_imbalance"]) * (
            out["trade_buy_amount"].abs() + out["trade_sell_amount"].abs()
        )
    out["queue_imbalance_top"] = (out["bid_depth"] - out["ask_depth"]) / (out["bid_depth"] + out["ask_depth"] + EPS)
    out["primary_pressure"] = out["trade_flow_imbalance"].astype(float)
    if source_layer == "fixed_event_panel":
        ofi = pd.to_numeric(out.get("ofi_l1_depth_norm", 0.0), errors="coerce").fillna(0.0)
        out["primary_pressure"] = np.where(out["primary_pressure"].abs() > EPS, out["primary_pressure"], ofi)
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=["local_ts_us", "bid", "ask", "mid"])
    out = out[(out["bid"] > 0.0) & (out["ask"] > 0.0) & (out["mid"] > 0.0)]
    out = out.sort_values("local_ts_us").drop_duplicates("local_ts_us", keep="last").reset_index(drop=True)
    return out


def load_decision_frames(repo_root: Path, symbol: str, day: str, max_rows: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = decision_frame_path(repo_root, symbol, day)
    if not path.exists():
        raise FileNotFoundError(path)
    columns = [
        "observed_seq",
        "local_ts_us",
        "event_index",
        "factor_eligible",
        "best_bid_price",
        "best_bid_amount",
        "best_ask_price",
        "best_ask_amount",
        "mid",
        "mid_price",
        "spread_bps",
        "trade_window_count",
        "trade_buy_amount",
        "trade_sell_amount",
        "trade_notional_quote",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]
    table = pq.read_table(path, columns=[col for col in columns if col in pq.read_schema(path).names])
    df = table.to_pandas()
    if "factor_eligible" in df.columns:
        df = df[df["factor_eligible"].fillna(False)].copy()
    out = normalize_market_columns(df, day, "decision_frame_v1")
    return maybe_stride(out, max_rows), read_json(decision_manifest_path(repo_root, symbol, day))


def fixed_event_usecols(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
    desired = {
        "date",
        "local_timestamp",
        "event_index",
        "factor_eligible",
        "best_bid_price",
        "best_bid_amount",
        "best_ask_price",
        "best_ask_amount",
        "mid_price",
        "spread_bps",
        "microprice_dev_bps",
        "bid_depth_1",
        "ask_depth_1",
        "bid_depth_5",
        "ask_depth_5",
        "bid_depth_25",
        "ask_depth_25",
        "queue_imbalance_1",
        "queue_imbalance_5",
        "trade_window_count",
        "trade_flow_imbalance",
        "trade_buy_amount",
        "trade_sell_amount",
        "trade_notional_quote",
        "trade_arrival_alignment",
        "ofi_l1_depth_norm",
        "mlofi_roll10_l1",
        "mlofi_roll10_l5",
        "mlofi_roll10_l25",
        "depletion_bid_amount",
        "depletion_ask_amount",
        "replenish_bid_amount",
        "replenish_ask_amount",
        "cancel_bid_amount",
        "cancel_ask_amount",
    }
    return [col for col in header if col in desired]


def load_fixed_event_panel(repo_root: Path, symbol: str, day: str, max_rows: int) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    day_dir = fixed_event_day_dir(repo_root, symbol, day)
    if day_dir is None:
        return None, {"date": day, "source_layer": "fixed_event_panel", "missing": True}
    parts = sorted(day_dir.glob("part_*.csv"))
    if not parts:
        return None, {"date": day, "source_layer": "fixed_event_panel", "missing": True, "path": str(day_dir)}
    usecols = fixed_event_usecols(parts[0])
    frames = []
    for part in parts:
        frames.append(pd.read_csv(part, usecols=usecols))
    df = pd.concat(frames, ignore_index=True)
    if "factor_eligible" in df.columns:
        df = df[df["factor_eligible"].fillna(False)].copy()
    out = normalize_market_columns(df, day, "fixed_event_panel")
    manifest = {
        "date": day,
        "source_layer": "fixed_event_panel",
        "missing": False,
        "path": str(day_dir),
        "parts": len(parts),
        "rows_loaded": int(len(out)),
        "run_tag": day_dir.parts[-3],
    }
    return maybe_stride(out, max_rows), manifest


def index_for_ts(ts: np.ndarray, offset_sec: int) -> np.ndarray:
    return np.searchsorted(ts, ts + int(offset_sec * 1_000_000), side="left")


def lookback_index(ts: np.ndarray, window_sec: int) -> np.ndarray:
    return np.searchsorted(ts, ts - int(window_sec * 1_000_000), side="left")


def rolling_sum(ts: np.ndarray, values: np.ndarray, window_sec: int) -> np.ndarray:
    x = np.nan_to_num(values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    cs = np.concatenate([[0.0], np.cumsum(x)])
    start = lookback_index(ts, window_sec)
    end = np.arange(len(x)) + 1
    return cs[end] - cs[start]


def rolling_mean(ts: np.ndarray, values: np.ndarray, window_sec: int) -> np.ndarray:
    start = lookback_index(ts, window_sec)
    count = np.arange(len(values)) - start + 1
    return rolling_sum(ts, values, window_sec) / np.maximum(count, 1)


def rolling_min_pd(ts: np.ndarray, values: np.ndarray, window_sec: int) -> np.ndarray:
    idx = pd.to_datetime(ts, unit="us")
    return pd.Series(values, index=idx).rolling(f"{window_sec}s", min_periods=1).min().to_numpy()


def rolling_max_pd(ts: np.ndarray, values: np.ndarray, window_sec: int) -> np.ndarray:
    idx = pd.to_datetime(ts, unit="us")
    return pd.Series(values, index=idx).rolling(f"{window_sec}s", min_periods=1).max().to_numpy()


def rolling_quantile_pd(ts: np.ndarray, values: np.ndarray, window_sec: int, q: float) -> np.ndarray:
    idx = pd.to_datetime(ts, unit="us")
    return pd.Series(values, index=idx).shift(1).rolling(f"{window_sec}s", min_periods=10).quantile(q).to_numpy()


def path_stats(ts: np.ndarray, signed_values: np.ndarray, window_sec: int) -> dict[str, np.ndarray]:
    x = np.nan_to_num(signed_values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    p = rolling_sum(ts, np.clip(x, 0.0, None), window_sec)
    n = rolling_sum(ts, np.clip(-x, 0.0, None), window_sec)
    delta = p - n
    energy = p + n
    return {
        "pos": p,
        "neg": n,
        "delta": delta,
        "energy": energy,
        "z": delta / np.sqrt(energy + EPS),
        "log_ratio": np.log((p + EPS) / (n + EPS)),
    }


def forward_window_extreme(ts: np.ndarray, values: np.ndarray, horizon_sec: int, mode: str) -> np.ndarray:
    horizon_us = int(horizon_sec * 1_000_000)
    out = np.full(len(values), np.nan, dtype=float)
    from collections import deque

    queue: deque[int] = deque()
    j = 0
    better = (lambda a, b: a >= b) if mode == "max" else (lambda a, b: a <= b)
    for i in range(len(values)):
        limit = ts[i] + horizon_us
        while j < len(values) and ts[j] <= limit:
            while queue and better(values[j], values[queue[-1]]):
                queue.pop()
            queue.append(j)
            j += 1
        while queue and queue[0] < i:
            queue.popleft()
        if queue:
            out[i] = values[queue[0]]
    return out


def add_labels(df: pd.DataFrame, mid_horizons_sec: list[int], release_sec: int, executable_horizon_sec: int) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    ts = out["local_ts_us"].to_numpy(dtype=np.int64)
    mid = out["mid"].to_numpy(dtype=float)
    bid = out["bid"].to_numpy(dtype=float)
    ask = out["ask"].to_numpy(dtype=float)
    invalid = 0
    for horizon in mid_horizons_sec:
        idx = index_for_ts(ts, horizon)
        valid = idx < len(out)
        invalid += int((~valid).sum())
        safe = np.minimum(idx, len(out) - 1)
        out[f"fwd_mid_return_{horizon}s_bps"] = np.where(valid, 10_000.0 * np.log(mid[safe] / mid), np.nan)
        out[f"abs_mid_terminal_{horizon}s_bps"] = out[f"fwd_mid_return_{horizon}s_bps"].abs()
    idx = index_for_ts(ts, executable_horizon_sec)
    valid = idx < len(out)
    invalid += int((~valid).sum())
    safe = np.minimum(idx, len(out) - 1)
    out[f"long_executable_{executable_horizon_sec}s_bps"] = np.where(valid, 10_000.0 * np.log(bid[safe] / ask), np.nan)
    out[f"short_executable_{executable_horizon_sec}s_bps"] = np.where(valid, 10_000.0 * np.log(bid / ask[safe]), np.nan)
    out[f"fwd_mid_return_{executable_horizon_sec}s_bps"] = np.where(valid, 10_000.0 * np.log(mid[safe] / mid), np.nan)
    max_mid = forward_window_extreme(ts, mid, release_sec, "max")
    min_mid = forward_window_extreme(ts, mid, release_sec, "min")
    out[f"long_mfe_{release_sec}s_bps"] = 10_000.0 * np.log(max_mid / mid)
    out[f"short_mfe_{release_sec}s_bps"] = 10_000.0 * np.log(mid / min_mid)
    two_sided_mfe = np.maximum(out[f"long_mfe_{release_sec}s_bps"], out[f"short_mfe_{release_sec}s_bps"])
    out[f"two_sided_decay_after_mfe_{executable_horizon_sec}s_bps"] = two_sided_mfe - out[
        f"fwd_mid_return_{executable_horizon_sec}s_bps"
    ].abs()
    return out, invalid


def add_factor_columns(df: pd.DataFrame, windows_sec: list[int]) -> pd.DataFrame:
    out = df.copy()
    ts = out["local_ts_us"].to_numpy(dtype=np.int64)
    mid = out["mid"].to_numpy(dtype=float)
    spread = out["spread_bps"].to_numpy(dtype=float)
    bid_depth = out["bid_depth"].to_numpy(dtype=float)
    ask_depth = out["ask_depth"].to_numpy(dtype=float)
    pressure = out["primary_pressure"].to_numpy(dtype=float)
    trade_count = out["trade_window_count"].to_numpy(dtype=float)
    signed_notional = out["signed_notional"].to_numpy(dtype=float)

    d_mid = np.concatenate([[0.0], 10_000.0 * np.diff(np.log(mid))])
    d_spread = np.concatenate([[0.0], np.diff(spread)])
    d_bid_depth = np.concatenate([[0.0], np.diff(bid_depth)])
    d_ask_depth = np.concatenate([[0.0], np.diff(ask_depth)])
    d_trade_count = np.concatenate([[0.0], np.diff(trade_count)])
    small_move = (np.abs(d_mid) < 0.05).astype(float)
    pressure_abs = np.abs(pressure)
    pressure_side = np.sign(rolling_sum(ts, pressure, min(windows_sec)))

    for window in windows_sec:
        start = lookback_index(ts, window)
        start_mid = mid[start]
        price_ret = 10_000.0 * np.log(mid / start_mid)
        price_side = np.sign(price_ret)
        price_stats = path_stats(ts, d_mid, window)
        price_abs_path = rolling_sum(ts, np.abs(d_mid), window)
        pressure_sum = rolling_sum(ts, pressure, window)
        pressure_side = np.sign(pressure_sum)
        pressure_energy = rolling_sum(ts, pressure_abs, window)
        pressure_stats = path_stats(ts, pressure, window)
        notional_stats = path_stats(ts, signed_notional, window)
        trade_count_stats = path_stats(ts, d_trade_count, window)
        spread_compression = path_stats(ts, -d_spread, window)
        spread_worsening = rolling_sum(ts, np.clip(d_spread, 0.0, None), window)
        spread_mean = rolling_mean(ts, spread, window)
        spread_q70 = rolling_quantile_pd(ts, spread, max(300, window * 5), 0.70)
        low_cost = np.where(np.isfinite(spread_q70), (spread <= spread_q70).astype(float), np.nan)
        low_cost_persistence = rolling_mean(ts, np.nan_to_num(low_cost, nan=0.0), window)

        path_max = rolling_max_pd(ts, price_ret, window)
        path_min = rolling_min_pd(ts, price_ret, window)
        favorable = np.maximum(np.abs(path_max), np.abs(path_min))
        pullback = np.where(favorable > EPS, (favorable - np.abs(price_ret)) / (favorable + EPS), np.nan)

        half = max(1, int(window / 2))
        price_half = path_stats(ts, d_mid, half)
        absorption = rolling_sum(ts, pressure_abs * small_move, window) / (pressure_energy + EPS)
        absorption_half = rolling_sum(ts, pressure_abs * small_move, half) / (rolling_sum(ts, pressure_abs, half) + EPS)
        absorption_failure = pressure_side * (absorption - absorption_half)

        align = np.sign(pressure) * d_mid
        align_stats = path_stats(ts, align, window)
        quote_trade_sync = rolling_mean(ts, (align > 0.0).astype(float), window)

        ask_give_stats = path_stats(ts, -d_ask_depth, window)
        bid_give_stats = path_stats(ts, -d_bid_depth, window)
        ask_give_pos = rolling_sum(ts, np.clip(-d_ask_depth, 0.0, None), window)
        bid_give_pos = rolling_sum(ts, np.clip(-d_bid_depth, 0.0, None), window)
        give_energy = ask_give_pos + bid_give_pos
        bid_support_pos = rolling_sum(ts, np.clip(d_bid_depth, 0.0, None), window)
        ask_support_pos = rolling_sum(ts, np.clip(d_ask_depth, 0.0, None), window)
        support_energy = bid_support_pos + ask_support_pos
        asym = (bid_depth - ask_depth) / (bid_depth + ask_depth + EPS)
        asym_stats = path_stats(ts, np.concatenate([[0.0], np.diff(asym)]), window)

        bid_min = rolling_min_pd(ts, bid_depth, window)
        ask_min = rolling_min_pd(ts, ask_depth, window)
        bid_recovery = (bid_depth - bid_min) / max(window, 1)
        ask_recovery = (ask_depth - ask_min) / max(window, 1)
        up_scaled = np.clip(d_mid, 0.0, None) / (ask_depth + EPS)
        down_scaled = np.clip(-d_mid, 0.0, None) / (bid_depth + EPS)
        vacuum_release = rolling_sum(ts, up_scaled, window) - rolling_sum(ts, down_scaled, window)

        price_energy = price_stats["energy"]
        signed_energy = np.sign(price_stats["delta"]) * price_energy
        release_to_cost = signed_energy / (spread_mean + EPS)
        pressure_to_price = pressure_side * price_ret / (pressure_energy + EPS)
        pressure_exhaustion = pressure_side * (pressure_energy - price_energy)
        opposite_giveway = (ask_give_pos - bid_give_pos) / np.sqrt(give_energy + EPS)
        same_support = (bid_support_pos - ask_support_pos) / np.sqrt(support_energy + EPS)
        depth_recovery = bid_recovery - ask_recovery
        price_eff = np.abs(price_ret) / (price_abs_path + EPS)
        activity_level = rolling_sum(ts, trade_count, window)
        activity_scale = float(np.nanstd(activity_level))
        activity_z = (activity_level - float(np.nanmean(activity_level))) / (activity_scale + EPS)
        sparse_penalty = (activity_level < max(3.0, window / 10.0)).astype(float)

        cols = {
            "price_path_efficiency": price_eff,
            "signed_price_path_ratio": price_stats["log_ratio"],
            "signed_price_energy": signed_energy,
            "pullback_after_release": pullback,
            "price_path_acceleration": price_half["z"] - price_stats["z"],
            "pressure_to_price_efficiency": pressure_to_price,
            "pressure_price_alignment_ratio": align_stats["log_ratio"],
            "absorption_rate": pressure_side * absorption,
            "absorption_failure_delta": absorption_failure,
            "pressure_exhaustion_gap": pressure_exhaustion,
            "opposite_depth_giveway_ratio": opposite_giveway,
            "same_side_support_ratio": same_support,
            "vacuum_release_energy": vacuum_release,
            "book_asymmetry_drift_z": asym_stats["z"],
            "opposite_depth_recovery_speed": depth_recovery,
            "spread_compression_ratio": spread_compression["log_ratio"],
            "spread_worsening_energy": spread_worsening,
            "low_cost_persistence": low_cost_persistence,
            "release_to_cost_ratio": release_to_cost,
            "cost_repair_release_combo": price_stats["z"] * spread_compression["log_ratio"],
            "trade_activity_z": activity_z,
            "trade_burst_persistence": trade_count_stats["log_ratio"],
            "signed_notional_energy": np.sign(notional_stats["delta"]) * notional_stats["energy"],
            "sparse_trade_noise_penalty": sparse_penalty,
            "quote_trade_sync_rate": pressure_side * quote_trade_sync,
            "vacuum_release_structure": pressure_stats["z"] * opposite_giveway * price_eff,
            "absorption_failure_structure": absorption_failure * pressure_stats["z"] * (price_half["z"] - price_stats["z"]),
            "cost_allowed_trend_structure": price_stats["z"] * low_cost_persistence * release_to_cost,
            "chop_decay_risk": (1.0 - price_eff) * spread_worsening,
            "executable_structure_score": (price_stats["z"] + pressure_stats["z"] + opposite_giveway) * price_eff / (spread_mean + EPS),
        }
        for factor_id, values in cols.items():
            out[f"{factor_id}__w{window}"] = np.asarray(values, dtype=float)
    return out.replace([np.inf, -np.inf], np.nan)


def cvar05(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return math.nan
    threshold = clean.quantile(0.05)
    tail = clean[clean <= threshold]
    return float(tail.mean()) if not tail.empty else math.nan


def safe_spearman(a: pd.Series, b: pd.Series) -> float:
    data = pd.concat([a, b], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 30 or data.iloc[:, 0].nunique() < 3 or data.iloc[:, 1].nunique() < 3:
        return math.nan
    return float(data.iloc[:, 0].corr(data.iloc[:, 1], method="spearman"))


def top_bottom_summary(data: pd.DataFrame, score: pd.Series, label: pd.Series, top_q: float, bottom_q: float) -> dict[str, Any]:
    work = pd.DataFrame({"date": data["date"], "score": score, "label": label}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(work) < 50 or work["score"].nunique() < 5:
        return {"n": int(len(work)), "mean": math.nan, "median": math.nan, "top_bottom": math.nan, "cvar05": math.nan, "daily_sign_rate": math.nan, "spearman": math.nan}
    top_cut = work["score"].quantile(top_q)
    bottom_cut = work["score"].quantile(bottom_q)
    top = work[work["score"] >= top_cut]
    bottom = work[work["score"] <= bottom_cut]
    daily = []
    for _, group in work.groupby("date", sort=True):
        if len(group) < 50 or group["score"].nunique() < 5:
            continue
        tcut = group["score"].quantile(top_q)
        bcut = group["score"].quantile(bottom_q)
        t = group[group["score"] >= tcut]["label"]
        b = group[group["score"] <= bcut]["label"]
        if len(t) and len(b):
            daily.append(float(t.mean() - b.mean()))
    return {
        "n": int(len(work)),
        "mean": float(top["label"].mean()) if len(top) else math.nan,
        "median": float(top["label"].median()) if len(top) else math.nan,
        "top_bottom": float(top["label"].mean() - bottom["label"].mean()) if len(top) and len(bottom) else math.nan,
        "cvar05": cvar05(top["label"]),
        "daily_sign_rate": float(np.mean([value > 0 for value in daily])) if daily else math.nan,
        "spearman": safe_spearman(work["score"], work["label"]),
    }


def labels_for_factor(df: pd.DataFrame, values: pd.Series, signed: bool, mid_horizons: list[int], release_sec: int, exec_horizon: int) -> list[tuple[str, pd.Series, pd.Series | None]]:
    if signed:
        side = np.sign(pd.to_numeric(values, errors="coerce").astype(float))
        labels: list[tuple[str, pd.Series, pd.Series | None]] = []
        for horizon in mid_horizons:
            mid_label = pd.Series(side * df[f"fwd_mid_return_{horizon}s_bps"], index=df.index)
            labels.append((f"mid_terminal_{horizon}s", mid_label, None))
        release = pd.Series(
            np.where(side > 0, df[f"long_mfe_{release_sec}s_bps"], np.where(side < 0, df[f"short_mfe_{release_sec}s_bps"], np.nan)),
            index=df.index,
        )
        mid60 = pd.Series(side * df[f"fwd_mid_return_{exec_horizon}s_bps"], index=df.index)
        executable = pd.Series(
            np.where(side > 0, df[f"long_executable_{exec_horizon}s_bps"], np.where(side < 0, df[f"short_executable_{exec_horizon}s_bps"], np.nan)),
            index=df.index,
        )
        labels.extend(
            [
                (f"release_mfe_{release_sec}s", release, None),
                (f"decay_after_mfe_{exec_horizon}s", release - mid60, None),
                (f"top_of_book_executable_{exec_horizon}s", executable, mid60),
            ]
        )
        return labels
    labels = []
    for horizon in mid_horizons:
        labels.append((f"abs_mid_terminal_{horizon}s", df[f"abs_mid_terminal_{horizon}s_bps"], None))
    labels.extend(
        [
            ("entry_spread_bps", df["spread_bps"], None),
            (f"two_sided_decay_after_mfe_{exec_horizon}s", df[f"two_sided_decay_after_mfe_{exec_horizon}s_bps"], None),
        ]
    )
    return labels


def status_for_row(spec: FactorDef, label_name: str, summary: dict[str, Any], mid_minus_exe: float) -> str:
    mean = float(summary.get("mean", math.nan))
    top_bottom = float(summary.get("top_bottom", math.nan))
    daily = float(summary.get("daily_sign_rate", math.nan))
    if not math.isfinite(mean) or not math.isfinite(top_bottom):
        return "weak_or_negative"
    if label_name.startswith("entry_spread") or spec.factor_id in {"spread_compression_ratio", "low_cost_persistence"}:
        return "cost_gate_only"
    if "decay" in label_name and top_bottom > 0.0:
        return "decay_risk_only"
    if label_name.startswith("top_of_book") and mean <= 0.0 and math.isfinite(mid_minus_exe) and mid_minus_exe > 0.0:
        return "spread_cost_mirage"
    if mean > 0.0 and top_bottom > 0.0 and (not math.isfinite(daily) or daily >= 2.0 / 3.0):
        return "research_panel_only" if spec.runtime_status == "research_panel_only" else "diagnostic_positive"
    return "weak_or_negative"


def summarize_panel(
    df: pd.DataFrame,
    *,
    aggregation_scope: str,
    date_window: str,
    windows_sec: list[int],
    mid_horizons: list[int],
    release_sec: int,
    exec_horizon: int,
    top_q: float,
    bottom_q: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_layer, source_df in df.groupby("source_layer", sort=True):
        for spec in FACTOR_DEFS:
            runtime_status = "research_panel_only" if source_layer == "fixed_event_panel" else spec.runtime_status
            for window in windows_sec:
                col = f"{spec.factor_id}__w{window}"
                if col not in source_df.columns or source_df[col].notna().sum() < 50:
                    rows.append(
                        {
                            "aggregation_scope": aggregation_scope,
                            "date_window": date_window,
                            "source_layer": source_layer,
                            "factor_id": spec.factor_id,
                            "factor_family": spec.family,
                            "window_sec": window,
                            "label": "",
                            "n": 0,
                            "mean": math.nan,
                            "median": math.nan,
                            "top_bottom": math.nan,
                            "spearman": math.nan,
                            "cvar05": math.nan,
                            "daily_sign_rate": math.nan,
                            "mid_minus_executable_bps": math.nan,
                            "spread_cost_mirage": False,
                            "signed": spec.signed,
                            "runtime_status": runtime_status,
                            "status": "source_column_missing",
                            "description": spec.description,
                        }
                    )
                    continue
                values = pd.to_numeric(source_df[col], errors="coerce")
                score = values.abs() if spec.signed else values
                for label_name, label, mid_reference in labels_for_factor(source_df, values, spec.signed, mid_horizons, release_sec, exec_horizon):
                    summary = top_bottom_summary(source_df, score, label, top_q, bottom_q)
                    mid_minus_exe = math.nan
                    if mid_reference is not None:
                        mid_summary = top_bottom_summary(source_df, score, mid_reference, top_q, bottom_q)
                        if math.isfinite(float(mid_summary.get("mean", math.nan))) and math.isfinite(float(summary.get("mean", math.nan))):
                            mid_minus_exe = float(mid_summary["mean"]) - float(summary["mean"])
                    rows.append(
                        {
                            "aggregation_scope": aggregation_scope,
                            "date_window": date_window,
                            "source_layer": source_layer,
                            "factor_id": spec.factor_id,
                            "factor_family": spec.family,
                            "window_sec": window,
                            "label": label_name,
                            "n": summary["n"],
                            "mean": summary["mean"],
                            "median": summary["median"],
                            "top_bottom": summary["top_bottom"],
                            "spearman": summary["spearman"],
                            "cvar05": summary["cvar05"],
                            "daily_sign_rate": summary["daily_sign_rate"],
                            "mid_minus_executable_bps": mid_minus_exe,
                            "spread_cost_mirage": bool(label_name.startswith("top_of_book") and math.isfinite(mid_minus_exe) and mid_minus_exe > 0.0),
                            "signed": spec.signed,
                            "runtime_status": runtime_status,
                            "status": status_for_row(
                                FactorDef(spec.factor_id, spec.family, spec.signed, runtime_status, spec.description),
                                label_name,
                                summary,
                                mid_minus_exe,
                            ),
                            "description": spec.description,
                        }
                    )
    return rows


def qbucket(series: pd.Series, q: int = 3) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() < q or values.nunique(dropna=True) < q:
        return pd.Series(["all"] * len(values), index=series.index, dtype="object")
    return pd.qcut(values.rank(method="first"), q, labels=[f"q{i}" for i in range(1, q + 1)]).astype("object").fillna("missing")


def conditional_lift_rows(df: pd.DataFrame, windows_sec: list[int], exec_horizon: int, top_q: float, bottom_q: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_layer, source_df in df.groupby("source_layer", sort=True):
        controls = {
            "spread_bucket": qbucket(source_df["spread_bps"], 3),
            "activity_bucket": qbucket(source_df["trade_window_count"], 3),
            "tfi_bucket": qbucket(source_df["trade_flow_imbalance"], 3),
        }
        if source_layer == "fixed_event_panel":
            controls["ofi_bucket"] = qbucket(source_df["ofi_l1_depth_norm"], 3)
            controls["mlofi_bucket"] = qbucket(source_df["mlofi_roll10_l1"], 3)
        for spec in FACTOR_DEFS:
            if not spec.signed:
                continue
            for window in windows_sec:
                col = f"{spec.factor_id}__w{window}"
                if col not in source_df.columns:
                    continue
                values = pd.to_numeric(source_df[col], errors="coerce")
                side = np.sign(values)
                score = values.abs()
                label = pd.Series(
                    np.where(
                        side > 0,
                        source_df[f"long_executable_{exec_horizon}s_bps"],
                        np.where(side < 0, source_df[f"short_executable_{exec_horizon}s_bps"], np.nan),
                    ),
                    index=source_df.index,
                )
                for control_name, buckets in controls.items():
                    work = pd.DataFrame({"bucket": buckets, "score": score, "label": label}).replace([np.inf, -np.inf], np.nan).dropna()
                    for bucket, group in work.groupby("bucket", sort=True):
                        if len(group) < 100 or group["score"].nunique() < 5:
                            continue
                        summary = top_bottom_summary(
                            pd.DataFrame({"date": [str(source_df["date"].iloc[0])] * len(group)}, index=group.index),
                            group["score"],
                            group["label"],
                            top_q,
                            bottom_q,
                        )
                        rows.append(
                            {
                                "source_layer": source_layer,
                                "factor_id": spec.factor_id,
                                "window_sec": window,
                                "control_name": control_name,
                                "control_bucket": str(bucket),
                                "label": f"top_of_book_executable_{exec_horizon}s",
                                "n": summary["n"],
                                "top_bottom": summary["top_bottom"],
                                "mean": summary["mean"],
                                "median": summary["median"],
                                "runtime_status": "research_panel_only" if source_layer == "fixed_event_panel" else spec.runtime_status,
                            }
                        )
    rows.sort(key=lambda row: float(row.get("top_bottom") or -1e9), reverse=True)
    return rows


def correlation_rows(df: pd.DataFrame, windows_sec: list[int], max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(20260602)
    for source_layer, source_df in df.groupby("source_layer", sort=True):
        sample = source_df
        if max_rows > 0 and len(sample) > max_rows:
            idx = rng.choice(len(sample), size=max_rows, replace=False)
            sample = sample.iloc[np.sort(idx)].copy()
        for window in windows_sec:
            cols = [f"{spec.factor_id}__w{window}" for spec in FACTOR_DEFS if f"{spec.factor_id}__w{window}" in sample.columns]
            if len(cols) < 2:
                continue
            corr = sample[cols].corr(method="spearman", min_periods=100)
            for i, left in enumerate(cols):
                for right in cols[i + 1 :]:
                    value = corr.loc[left, right]
                    if not math.isfinite(float(value)):
                        continue
                    rows.append(
                        {
                            "source_layer": source_layer,
                            "window_sec": window,
                            "factor_left": left.rsplit("__w", 1)[0],
                            "factor_right": right.rsplit("__w", 1)[0],
                            "spearman": float(value),
                            "abs_spearman": abs(float(value)),
                        }
                    )
    rows.sort(key=lambda row: row["abs_spearman"], reverse=True)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_float(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def markdown_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int = 25) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows[:max_rows]:
        cells = []
        for col in columns:
            value = row.get(col, "")
            cells.append(format_float(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(path: Path, summary: dict[str, Any], summary_rows: list[dict[str, Any]], conditional_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(summary_rows)
    lines = [
        "# CCUSDT Path-Structure Factor Fast Diagnostic v0.1",
        "",
        "Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.",
        "",
        "## Scope",
        "",
        f"- symbol: `{summary['symbol']}`",
        f"- dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- source: `{summary['source']}`",
        f"- windows_sec: `{summary['windows_sec']}`",
        f"- mid_horizons_sec: `{summary['mid_horizons_sec']}`",
        f"- release_sec: `{summary['release_sec']}`",
        f"- executable_horizon_sec: `{summary['executable_horizon_sec']}`",
        f"- factor_count: `{summary['factor_count']}`",
        f"- event_panel_rows: `{summary['event_panel_rows']}`",
        f"- max_label_validity_drop_count: `{summary['max_label_validity_drop_count']}`",
        f"- out_dir: `{summary['out_dir']}`",
        "",
        "This diagnostic tests medium-horizon path operators. `fixed_event_panel` rows are research evidence only; they do not prove Bot runtime reconstructability.",
        "",
        "## Status Counts",
        "",
    ]
    if df.empty:
        lines.append("_No rows._")
    else:
        counts = df.groupby(["aggregation_scope", "source_layer", "status"]).size().reset_index(name="rows")
        lines.extend(markdown_table(counts.to_dict("records"), ["aggregation_scope", "source_layer", "status", "rows"], 80))
    lines.extend(["", "## Executable Layer Readout", ""])
    if not df.empty:
        exec_rows = df[(df["aggregation_scope"] == "pooled") & (df["label"].astype(str).str.startswith("top_of_book"))].copy()
        if exec_rows.empty:
            lines.append("_No pooled top-of-book rows._")
        else:
            exec_counts = exec_rows.groupby(["source_layer", "status"]).size().reset_index(name="rows")
            lines.extend(markdown_table(exec_counts.to_dict("records"), ["source_layer", "status", "rows"], 20))
            positive_exec = exec_rows[
                (pd.to_numeric(exec_rows["mean"], errors="coerce") > 0.0)
                & (pd.to_numeric(exec_rows["top_bottom"], errors="coerce") > 0.0)
                & (exec_rows["status"].isin(["diagnostic_positive", "research_panel_only"]))
            ]
            if positive_exec.empty:
                lines.extend(
                    [
                        "",
                        "No pooled top-of-book row has both positive top-bucket mean and positive top-bottom lift. In this pass, the largest executable lifts are mostly `spread_cost_mirage`: the bucket loses less, but does not yet produce positive taker economics.",
                    ]
                )
            else:
                lines.extend(["", "Positive pooled executable rows:"])
                positive_exec = positive_exec.sort_values("mean", ascending=False)
                lines.extend(
                    markdown_table(
                        positive_exec.to_dict("records"),
                        ["source_layer", "factor_id", "window_sec", "n", "mean", "top_bottom", "runtime_status", "status"],
                        15,
                    )
                )
    lines.extend(["", "## Top Executable Diagnostic Rows", ""])
    if not df.empty:
        focus = df[
            (df["aggregation_scope"] == "pooled")
            & (df["label"].astype(str).str.startswith("top_of_book"))
            & (df["status"].isin(["diagnostic_positive", "research_panel_only", "spread_cost_mirage"]))
        ].copy()
        focus["top_bottom_num"] = pd.to_numeric(focus["top_bottom"], errors="coerce")
        focus["mean_num"] = pd.to_numeric(focus["mean"], errors="coerce")
        focus = focus.sort_values(["status", "top_bottom_num", "mean_num"], ascending=[True, False, False])
        lines.extend(
            markdown_table(
                focus.to_dict("records"),
                ["source_layer", "factor_id", "window_sec", "label", "n", "mean", "top_bottom", "spearman", "daily_sign_rate", "runtime_status", "status"],
                35,
            )
        )
    else:
        lines.append("_No rows._")
    lines.extend(["", "## Best Conditional Lifts", ""])
    lines.extend(
        markdown_table(
            conditional_rows,
            ["source_layer", "factor_id", "window_sec", "control_name", "control_bucket", "n", "mean", "top_bottom", "runtime_status"],
            30,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- `diagnostic_positive` means the factor survived the diagnostic estimator, not that it is a strategy input.",
            "- `research_panel_only` means the evidence uses fixed-event derived fields and must be reconstructed or rejected before runtime use.",
            "- `spread_cost_mirage` means mid/release evidence exists but top-of-book taker economics are non-positive.",
            "- `decay_risk_only` and `cost_gate_only` are controls or gates, not standalone alpha.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    windows_sec = parse_int_list(args.windows_sec)
    mid_horizons = parse_int_list(args.mid_horizons_sec)
    out_dir = args.out_dir or DEFAULT_OUT_ROOT / f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_{args.source}_v0_1"
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    panels: list[pd.DataFrame] = []
    by_day_rows: list[dict[str, Any]] = []
    source_manifests: list[dict[str, Any]] = []
    label_invalid_counts: list[int] = []

    for day in date_range(args.from_date, args.to_date):
        if args.source in {"decision_frame", "both"}:
            print(f"path_structure load source=decision_frame day={day}", file=sys.stderr, flush=True)
            df, manifest = load_decision_frames(repo_root, args.symbol, day, args.max_rows_per_day)
            df, invalid = add_labels(df, mid_horizons, args.release_sec, args.executable_horizon_sec)
            df = add_factor_columns(df, windows_sec)
            panels.append(df)
            label_invalid_counts.append(invalid)
            by_day_rows.extend(
                summarize_panel(
                    df,
                    aggregation_scope="daily",
                    date_window=day,
                    windows_sec=windows_sec,
                    mid_horizons=mid_horizons,
                    release_sec=args.release_sec,
                    exec_horizon=args.executable_horizon_sec,
                    top_q=args.top_quantile,
                    bottom_q=args.bottom_quantile,
                )
            )
            source_manifests.append(
                {
                    "date": day,
                    "source_layer": "decision_frame_v1",
                    "row_count": int(len(df)),
                    "manifest_path": str(decision_manifest_path(repo_root, args.symbol, day)),
                    "field_hash_sha256": manifest.get("field_hash_sha256"),
                    "builder_version": manifest.get("builder_version"),
                    "schema_version": manifest.get("schema_version"),
                }
            )
        if args.source in {"fixed_event", "both"}:
            print(f"path_structure load source=fixed_event day={day}", file=sys.stderr, flush=True)
            fixed, manifest = load_fixed_event_panel(repo_root, args.symbol, day, args.max_rows_per_day)
            source_manifests.append(manifest)
            if fixed is not None:
                fixed, invalid = add_labels(fixed, mid_horizons, args.release_sec, args.executable_horizon_sec)
                fixed = add_factor_columns(fixed, windows_sec)
                panels.append(fixed)
                label_invalid_counts.append(invalid)
                by_day_rows.extend(
                    summarize_panel(
                        fixed,
                        aggregation_scope="daily",
                        date_window=day,
                        windows_sec=windows_sec,
                        mid_horizons=mid_horizons,
                        release_sec=args.release_sec,
                        exec_horizon=args.executable_horizon_sec,
                        top_q=args.top_quantile,
                        bottom_q=args.bottom_quantile,
                    )
                )

    if not panels:
        raise ValueError("no source panels loaded")
    panel = pd.concat(panels, ignore_index=True, sort=False)
    pooled_rows = summarize_panel(
        panel,
        aggregation_scope="pooled",
        date_window=f"{args.from_date}..{args.to_date}",
        windows_sec=windows_sec,
        mid_horizons=mid_horizons,
        release_sec=args.release_sec,
        exec_horizon=args.executable_horizon_sec,
        top_q=args.top_quantile,
        bottom_q=args.bottom_quantile,
    )
    summary_rows = by_day_rows + pooled_rows
    conditional_rows = conditional_lift_rows(panel, windows_sec, args.executable_horizon_sec, args.top_quantile, args.bottom_quantile)
    corr_rows = correlation_rows(panel, windows_sec, args.correlation_sample_rows)

    pq.write_table(pa.Table.from_pandas(panel, preserve_index=False), out_dir / "factor_event_panel.parquet", compression="zstd")
    write_csv(out_dir / "factor_summary.csv", summary_rows)
    write_csv(out_dir / "factor_by_day.csv", by_day_rows)
    write_csv(out_dir / "factor_conditional_lift.csv", conditional_rows)
    write_csv(out_dir / "factor_correlation.csv", corr_rows)

    factors_in_summary = sorted({row["factor_id"] for row in summary_rows})
    missing_factors = sorted(set(FACTOR_BY_ID) - set(factors_in_summary))
    if missing_factors:
        raise ValueError(f"missing factors from summary: {missing_factors}")

    summary = {
        "schema_id": "ccusdt_path_structure_factor_fast_diagnostic_summary_v1",
        "factor_schema_id": SCHEMA_ID,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "source": args.source,
        "windows_sec": windows_sec,
        "mid_horizons_sec": mid_horizons,
        "release_sec": args.release_sec,
        "executable_horizon_sec": args.executable_horizon_sec,
        "top_quantile": args.top_quantile,
        "bottom_quantile": args.bottom_quantile,
        "factor_count": len(FACTOR_DEFS),
        "factors_in_summary_count": len(factors_in_summary),
        "event_panel_rows": int(len(panel)),
        "summary_rows": len(summary_rows),
        "by_day_rows": len(by_day_rows),
        "conditional_lift_rows": len(conditional_rows),
        "correlation_rows": len(corr_rows),
        "max_label_validity_drop_count": max(label_invalid_counts) if label_invalid_counts else 0,
        "out_dir": str(out_dir),
        "report_path": str(report_path),
        "elapsed_wall_ms": int((time.perf_counter() - started) * 1000),
        "source_manifests": source_manifests,
        "boundary": "research-only; future labels are diagnostic only; fixed_event_panel is research evidence only; Runner/Bot/Monitor not modified",
        "outputs": {
            "factor_event_panel_parquet": str(out_dir / "factor_event_panel.parquet"),
            "factor_summary_csv": str(out_dir / "factor_summary.csv"),
            "factor_by_day_csv": str(out_dir / "factor_by_day.csv"),
            "factor_conditional_lift_csv": str(out_dir / "factor_conditional_lift.csv"),
            "factor_correlation_csv": str(out_dir / "factor_correlation.csv"),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(report_path, summary, summary_rows, conditional_rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
