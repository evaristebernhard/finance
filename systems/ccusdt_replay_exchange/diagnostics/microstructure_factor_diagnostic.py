#!/usr/bin/env python
"""Build a first-principles microstructure factor diagnostic table.

This diagnostic is deliberately outside the Runner/Bot runtime. It reads
market-derived decision frames and, when requested, the fixed event-orderbook
panel. It evaluates factor transforms against separated label layers:

- signed mid terminal path
- signed release / decay path diagnostics
- signed top-of-book taker executable terminal path
- unsigned regime/control labels

No future label produced here is a runtime input.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
FIXED_EVENT_ROOT = Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/microstructure_factor_diagnostic")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/factors/v1-microstructure-factor-diagnostic-20260601.md")

EPS = 1e-12


@dataclass(frozen=True)
class FactorSpec:
    family: str
    primitive: str
    column: str
    signed: bool
    runtime_safe: bool
    source_layer: str
    description: str


DECISION_FACTOR_SPECS = [
    FactorSpec(
        "active_trade_flow_memory",
        "TFI",
        "trade_flow_imbalance",
        True,
        True,
        "decision_frame_v1",
        "Active trade-flow imbalance from the market-derived decision clock.",
    ),
    FactorSpec(
        "pressure_to_price_conversion",
        "past_event_25_bps",
        "past_event_25_bps",
        True,
        True,
        "decision_frame_v1",
        "Already-realized recent event return; a control, not standalone future evidence.",
    ),
    FactorSpec(
        "passive_book_state",
        "queue_imbalance_1",
        "queue_imbalance_1",
        True,
        True,
        "decision_frame_v1",
        "Top-of-book queue imbalance reconstructed from best bid/ask amount.",
    ),
    FactorSpec(
        "passive_book_state",
        "spread_bps",
        "spread_bps",
        False,
        True,
        "decision_frame_v1",
        "Current crossing-cost regime.",
    ),
    FactorSpec(
        "pressure_to_price_conversion",
        "frames_since_mid_change",
        "frames_since_mid_change",
        False,
        True,
        "decision_frame_v1",
        "Quote staleness / latent-pressure proxy.",
    ),
    FactorSpec(
        "passive_book_state",
        "top_depth_quote_min",
        "top_depth_quote_min",
        False,
        True,
        "decision_frame_v1",
        "Minimum visible top-of-book quote notional on either side.",
    ),
    FactorSpec(
        "active_trade_flow_memory",
        "trade_window_count",
        "trade_window_count",
        False,
        True,
        "decision_frame_v1",
        "Recent trade-arrival activity count.",
    ),
]


FIXED_EVENT_FACTOR_SPECS = [
    FactorSpec("active_trade_flow_memory", "TFI", "trade_flow_imbalance", True, True, "fixed_event_panel", "Trade-flow imbalance from fixed event panel."),
    FactorSpec("dynamic_book_flow", "OFI_L1", "ofi_l1_depth_norm", True, True, "fixed_event_panel", "Depth-normalized best-level OFI."),
    FactorSpec("dynamic_book_flow", "MLOFI_L1", "mlofi_roll10_l1", True, True, "fixed_event_panel", "Rolling multi-level OFI at L1."),
    FactorSpec("dynamic_book_flow", "MLOFI_L5", "mlofi_roll10_l5", True, True, "fixed_event_panel", "Rolling multi-level OFI at L5."),
    FactorSpec("dynamic_book_flow", "MLOFI_L25", "mlofi_roll10_l25", True, True, "fixed_event_panel", "Rolling multi-level OFI at L25."),
    FactorSpec("dynamic_book_flow", "trade_arrival_alignment", "trade_arrival_alignment", True, True, "fixed_event_panel", "Trade arrival aligned to book movement."),
    FactorSpec("passive_book_state", "queue_imbalance_5", "queue_imbalance_5", True, True, "fixed_event_panel", "Five-level queue imbalance."),
    FactorSpec("passive_book_state", "microprice_dev_bps", "microprice_dev_bps", True, True, "fixed_event_panel", "Microprice deviation from mid in bps."),
    FactorSpec("dynamic_book_flow", "depletion_pressure", "depletion_pressure", True, True, "fixed_event_panel", "Ask depletion minus bid depletion; positive is upward pressure."),
    FactorSpec("dynamic_book_flow", "replenish_pressure", "replenish_pressure", True, True, "fixed_event_panel", "Bid replenish minus ask replenish; positive is upward support."),
    FactorSpec("dynamic_book_flow", "withdrawal_pressure", "withdrawal_pressure", True, True, "fixed_event_panel", "Ask cancellation minus bid cancellation; positive is upward withdrawal."),
    FactorSpec("passive_book_state", "spread_bps", "spread_bps", False, True, "fixed_event_panel", "Current crossing-cost regime."),
    FactorSpec("passive_book_state", "depth25_quote_min", "depth25_quote_min", False, True, "fixed_event_panel", "Minimum 25-level quote depth on either side."),
    FactorSpec("dynamic_book_flow", "queue_depletion_intensity", "queue_depletion_intensity", False, True, "fixed_event_panel", "Unsigned queue depletion intensity."),
    FactorSpec("dynamic_book_flow", "replenish_intensity", "replenish_intensity", False, True, "fixed_event_panel", "Unsigned replenishment intensity."),
    FactorSpec("dynamic_book_flow", "cancellation_withdrawal_intensity", "cancellation_withdrawal_intensity", False, True, "fixed_event_panel", "Unsigned cancellation/withdrawal intensity."),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--source", choices=["decision_frame", "fixed_event", "both"], default="both")
    parser.add_argument("--horizon-sec", type=int, default=60)
    parser.add_argument("--release-sec", type=int, default=10)
    parser.add_argument("--memory-windows", default="5,10")
    parser.add_argument("--top-quantile", type=float, default=0.8)
    parser.add_argument("--bottom-quantile", type=float, default=0.2)
    parser.add_argument("--max-rows-per-day", type=int, default=0, help="Optional deterministic stride sample per source/day.")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def date_range(start: str, end: str) -> Iterable[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while cur <= last:
        yield cur.isoformat()
        cur += timedelta(days=1)


def format_float(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def decision_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def decision_manifest_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "manifest.json"


def fixed_event_day_dir(repo_root: Path, symbol: str, day: str) -> Path | None:
    candidates = []
    for run_dir in (repo_root / FIXED_EVENT_ROOT).glob("run_tag=*"):
        day_dir = run_dir / f"symbol={symbol}" / f"dt={day}"
        if day_dir.exists():
            candidates.append(day_dir)
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.parts[-3])[-1]


def maybe_stride(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.reset_index(drop=True)
    stride = max(1, int(math.ceil(len(df) / max_rows)))
    return df.iloc[::stride].head(max_rows).reset_index(drop=True)


def load_decision_frames(repo_root: Path, symbol: str, day: str, max_rows: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = decision_frame_path(repo_root, symbol, day)
    if not path.exists():
        raise FileNotFoundError(path)
    columns = [
        "local_ts_us",
        "event_index",
        "factor_eligible",
        "best_bid_price",
        "best_bid_amount",
        "best_ask_price",
        "best_ask_amount",
        "mid",
        "spread_bps",
        "trade_window_count",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]
    df = pq.read_table(path, columns=columns).to_pandas()
    df = df[df["factor_eligible"].fillna(False)].copy()
    df["date"] = day
    df["source_layer"] = "decision_frame_v1"
    denom = df["best_bid_amount"].astype(float) + df["best_ask_amount"].astype(float)
    df["queue_imbalance_1"] = (df["best_bid_amount"].astype(float) - df["best_ask_amount"].astype(float)) / (denom + EPS)
    df["top_depth_quote_min"] = np.minimum(
        df["best_bid_amount"].astype(float) * df["best_bid_price"].astype(float),
        df["best_ask_amount"].astype(float) * df["best_ask_price"].astype(float),
    )
    df = normalize_market_columns(df)
    return maybe_stride(df, max_rows), read_json(decision_manifest_path(repo_root, symbol, day))


def fixed_event_usecols() -> list[str]:
    return [
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
        "bid_depth_25",
        "ask_depth_25",
        "queue_imbalance_5",
        "trade_window_count",
        "trade_flow_imbalance",
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
        "queue_depletion_intensity",
        "replenish_intensity",
        "cancellation_withdrawal_intensity",
    ]


def load_fixed_event_panel(repo_root: Path, symbol: str, day: str, max_rows: int) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    day_dir = fixed_event_day_dir(repo_root, symbol, day)
    if day_dir is None:
        return None, {"missing": True, "date": day, "source_layer": "fixed_event_panel"}
    parts = sorted(day_dir.glob("part_*.csv"))
    frames = []
    for part in parts:
        frames.append(pd.read_csv(part, usecols=fixed_event_usecols()))
    if not frames:
        return None, {"missing": True, "date": day, "source_layer": "fixed_event_panel", "path": str(day_dir)}
    df = pd.concat(frames, ignore_index=True)
    df = df[df["factor_eligible"].fillna(False)].copy()
    df["local_ts_us"] = df["local_timestamp"].astype("int64")
    df["mid"] = df["mid_price"].astype(float)
    df["depletion_pressure"] = df["depletion_ask_amount"].astype(float) - df["depletion_bid_amount"].astype(float)
    df["replenish_pressure"] = df["replenish_bid_amount"].astype(float) - df["replenish_ask_amount"].astype(float)
    df["withdrawal_pressure"] = df["cancel_ask_amount"].astype(float) - df["cancel_bid_amount"].astype(float)
    df["depth25_quote_min"] = np.minimum(
        df["bid_depth_25"].astype(float) * df["best_bid_price"].astype(float),
        df["ask_depth_25"].astype(float) * df["best_ask_price"].astype(float),
    )
    df["source_layer"] = "fixed_event_panel"
    df = normalize_market_columns(df)
    manifest = {
        "missing": False,
        "date": day,
        "source_layer": "fixed_event_panel",
        "path": str(day_dir),
        "parts": len(parts),
        "rows_loaded": int(len(df)),
        "run_tag": day_dir.parts[-3],
    }
    return maybe_stride(df, max_rows), manifest


def normalize_market_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "best_bid_price": "bid",
        "best_ask_price": "ask",
    }
    out = df.rename(columns=rename).copy()
    out["local_ts_us"] = out["local_ts_us"].astype("int64")
    out["bid"] = out["bid"].astype(float)
    out["ask"] = out["ask"].astype(float)
    out["mid"] = out["mid"].astype(float)
    out["spread_bps"] = out["spread_bps"].astype(float)
    out = out.sort_values("local_ts_us").drop_duplicates("local_ts_us", keep="last").reset_index(drop=True)
    return out


def search_exit_indices(ts: np.ndarray, horizon_sec: int) -> np.ndarray:
    target = ts + int(horizon_sec * 1_000_000)
    idx = np.searchsorted(ts, target, side="left")
    return idx


def forward_window_extreme(ts: np.ndarray, values: np.ndarray, horizon_sec: int, mode: str) -> np.ndarray:
    horizon_us = int(horizon_sec * 1_000_000)
    n = len(values)
    out = np.full(n, np.nan, dtype=float)
    queue: deque[int] = deque()
    j = 0
    better = (lambda a, b: a >= b) if mode == "max" else (lambda a, b: a <= b)
    for i in range(n):
        limit = ts[i] + horizon_us
        while j < n and ts[j] <= limit:
            while queue and better(values[j], values[queue[-1]]):
                queue.pop()
            queue.append(j)
            j += 1
        while queue and queue[0] < i:
            queue.popleft()
        if queue:
            out[i] = values[queue[0]]
    return out


def add_labels(df: pd.DataFrame, horizon_sec: int, release_sec: int) -> pd.DataFrame:
    out = df.copy()
    ts = out["local_ts_us"].to_numpy(dtype=np.int64)
    mid = out["mid"].to_numpy(dtype=float)
    bid = out["bid"].to_numpy(dtype=float)
    ask = out["ask"].to_numpy(dtype=float)

    exit_idx = search_exit_indices(ts, horizon_sec)
    valid_exit = exit_idx < len(out)
    out["valid_terminal_label"] = valid_exit
    safe_exit = np.minimum(exit_idx, len(out) - 1)
    exit_mid = mid[safe_exit]
    exit_bid = bid[safe_exit]
    exit_ask = ask[safe_exit]
    out["fwd_mid_return_bps"] = np.where(valid_exit, 10000.0 * np.log(exit_mid / mid), np.nan)
    out["fwd_abs_mid_return_bps"] = np.abs(out["fwd_mid_return_bps"].astype(float))
    out["long_executable_bps"] = np.where(valid_exit, 10000.0 * np.log(exit_bid / ask), np.nan)
    out["short_executable_bps"] = np.where(valid_exit, 10000.0 * np.log(bid / exit_ask), np.nan)

    max_mid = forward_window_extreme(ts, mid, release_sec, "max")
    min_mid = forward_window_extreme(ts, mid, release_sec, "min")
    out["long_mfe_bps"] = 10000.0 * np.log(max_mid / mid)
    out["short_mfe_bps"] = 10000.0 * np.log(mid / min_mid)
    return out


def memory_transforms(series: pd.Series, windows: list[int]) -> dict[str, pd.Series]:
    x = pd.to_numeric(series, errors="coerce").astype(float)
    transforms: dict[str, pd.Series] = {"raw": x}
    pos = x.clip(lower=0.0)
    neg = (-x).clip(lower=0.0)
    for window in windows:
        p = pos.rolling(window, min_periods=window).sum()
        n = neg.rolling(window, min_periods=window).sum()
        delta = p - n
        energy = p + n
        transforms[f"r{window}_log_ratio"] = np.log((p + EPS) / (n + EPS))
        transforms[f"r{window}_delta"] = delta
        transforms[f"r{window}_energy_delta_side"] = np.sign(delta) * energy
        transforms[f"r{window}_z"] = delta / np.sqrt(energy + EPS)
    return transforms


def cvar05(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return math.nan
    threshold = clean.quantile(0.05)
    tail = clean[clean <= threshold]
    if tail.empty:
        return math.nan
    return float(tail.mean())


def safe_spearman(score: pd.Series, label: pd.Series) -> float:
    aligned = pd.concat([score, label], axis=1).dropna()
    if len(aligned) < 3:
        return math.nan
    if aligned.iloc[:, 0].nunique() < 2 or aligned.iloc[:, 1].nunique() < 2:
        return math.nan
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman"))


def top_bottom_summary(
    df: pd.DataFrame,
    score: pd.Series,
    label: pd.Series,
    *,
    top_q: float,
    bottom_q: float,
) -> dict[str, Any]:
    data = pd.DataFrame({"date": df["date"], "score": score, "label": label}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 20 or data["score"].nunique() < 3:
        return {
            "n": int(len(data)),
            "mean": math.nan,
            "median": math.nan,
            "top_bottom": math.nan,
            "cvar05": math.nan,
            "daily_sign_rate": math.nan,
            "spearman": math.nan,
        }
    top_cut = data["score"].quantile(top_q)
    bottom_cut = data["score"].quantile(bottom_q)
    top = data[data["score"] >= top_cut]
    bottom = data[data["score"] <= bottom_cut]
    daily: list[float] = []
    for _, group in data.groupby("date"):
        if len(group) < 20 or group["score"].nunique() < 3:
            continue
        tcut = group["score"].quantile(top_q)
        bcut = group["score"].quantile(bottom_q)
        t = group[group["score"] >= tcut]["label"]
        b = group[group["score"] <= bcut]["label"]
        if len(t) and len(b):
            daily.append(float(t.mean() - b.mean()))
    return {
        "n": int(len(data)),
        "mean": float(top["label"].mean()) if len(top) else math.nan,
        "median": float(top["label"].median()) if len(top) else math.nan,
        "top_bottom": float(top["label"].mean() - bottom["label"].mean()) if len(top) and len(bottom) else math.nan,
        "cvar05": cvar05(top["label"]),
        "daily_sign_rate": float(np.mean([value > 0 for value in daily])) if daily else math.nan,
        "spearman": safe_spearman(data["score"], data["label"]),
    }


def status_for_row(label_name: str, signed: bool, summary: dict[str, Any], mid_minus_exe: float | None) -> str:
    mean = float(summary.get("mean", math.nan))
    top_bottom = float(summary.get("top_bottom", math.nan))
    daily = float(summary.get("daily_sign_rate", math.nan))
    if not signed:
        return "control_only_no_direction"
    if not math.isfinite(mean) or not math.isfinite(top_bottom):
        return "insufficient_data"
    if label_name.startswith("decay"):
        if top_bottom > 0:
            return "decay_risk_higher_for_top_bucket"
        if top_bottom < 0:
            return "decay_lower_for_top_bucket_not_promoted"
        return "decay_neutral"
    if label_name.startswith("top_of_book") and mean <= 0 and mid_minus_exe is not None and math.isfinite(mid_minus_exe) and mid_minus_exe > 0:
        return "spread_cost_mirage_or_negative_executable"
    if mean > 0 and top_bottom > 0 and (not math.isfinite(daily) or daily >= 0.6):
        return "diagnostic_positive_not_promoted"
    return "weak_or_negative"


def summarize_factor(
    df: pd.DataFrame,
    spec: FactorSpec,
    transform_name: str,
    transformed: pd.Series,
    *,
    horizon_sec: int,
    release_sec: int,
    top_q: float,
    bottom_q: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw = pd.to_numeric(transformed, errors="coerce").astype(float)
    if spec.signed:
        side = np.sign(raw)
        score = raw.abs()
        long_mask = side > 0
        short_mask = side < 0
        mid_terminal = pd.Series(np.where(long_mask, df["fwd_mid_return_bps"], np.where(short_mask, -df["fwd_mid_return_bps"], np.nan)), index=df.index)
        executable = pd.Series(np.where(long_mask, df["long_executable_bps"], np.where(short_mask, df["short_executable_bps"], np.nan)), index=df.index)
        release = pd.Series(np.where(long_mask, df["long_mfe_bps"], np.where(short_mask, df["short_mfe_bps"], np.nan)), index=df.index)
        decay = release - mid_terminal
        labels = [
            (f"mid_terminal_{horizon_sec}s", mid_terminal, None),
            (f"release_mfe_{release_sec}s", release, None),
            (f"decay_{horizon_sec}s_after_mfe", decay, None),
            (f"top_of_book_executable_{horizon_sec}s", executable, mid_terminal),
        ]
    else:
        score = raw
        labels = [
            (f"abs_mid_terminal_{horizon_sec}s", df["fwd_abs_mid_return_bps"], None),
            ("entry_spread_bps", df["spread_bps"], None),
        ]

    for label_name, label, mid_reference in labels:
        summary = top_bottom_summary(df, score, label, top_q=top_q, bottom_q=bottom_q)
        mid_minus_exe = math.nan
        if mid_reference is not None:
            mid_summary = top_bottom_summary(df, score, mid_reference, top_q=top_q, bottom_q=bottom_q)
            if math.isfinite(float(mid_summary.get("mean", math.nan))) and math.isfinite(float(summary.get("mean", math.nan))):
                mid_minus_exe = float(mid_summary["mean"]) - float(summary["mean"])
        rows.append(
            {
                "factor_family": spec.family,
                "factor_name": f"{spec.primitive}__{transform_name}",
                "primitive": spec.primitive,
                "transform": transform_name,
                "label": label_name,
                "horizon": horizon_sec if str(label_name).endswith(f"{horizon_sec}s") else release_sec if "release" in label_name else "",
                "n": summary["n"],
                "mean": summary["mean"],
                "median": summary["median"],
                "top_bottom": summary["top_bottom"],
                "cvar05": summary["cvar05"],
                "daily_sign_rate": summary["daily_sign_rate"],
                "spearman": summary["spearman"],
                "mid_minus_executable_bps": mid_minus_exe,
                "runtime_safe": spec.runtime_safe,
                "status": status_for_row(label_name, spec.signed, summary, mid_minus_exe if math.isfinite(mid_minus_exe) else None),
                "source_layer": spec.source_layer,
                "source_status": "loaded",
                "description": spec.description,
            }
        )
    return rows


def summarize_source(
    df: pd.DataFrame,
    specs: list[FactorSpec],
    *,
    aggregation_scope: str,
    date_window: str,
    source_status: str,
    horizon_sec: int,
    release_sec: int,
    windows: list[int],
    top_q: float,
    bottom_q: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    labelled = add_labels(df, horizon_sec, release_sec)
    for spec in specs:
        if spec.column not in labelled.columns:
            rows.append(
                {
                    "aggregation_scope": aggregation_scope,
                    "date_window": date_window,
                    "factor_family": spec.family,
                    "factor_name": f"{spec.primitive}__missing",
                    "primitive": spec.primitive,
                    "transform": "missing",
                    "label": "",
                    "horizon": "",
                    "n": 0,
                    "mean": math.nan,
                    "median": math.nan,
                    "top_bottom": math.nan,
                    "cvar05": math.nan,
                    "daily_sign_rate": math.nan,
                    "spearman": math.nan,
                    "mid_minus_executable_bps": math.nan,
                    "runtime_safe": spec.runtime_safe,
                    "status": "source_column_missing",
                    "source_layer": spec.source_layer,
                    "source_status": source_status,
                    "description": spec.description,
                }
            )
            continue
        transforms = memory_transforms(labelled[spec.column], windows) if spec.signed else {"raw": pd.to_numeric(labelled[spec.column], errors="coerce")}
        for transform_name, transformed in transforms.items():
            factor_rows = summarize_factor(
                labelled,
                spec,
                transform_name,
                transformed,
                horizon_sec=horizon_sec,
                release_sec=release_sec,
                top_q=top_q,
                bottom_q=bottom_q,
            )
            for row in factor_rows:
                scoped_row = {
                    "aggregation_scope": aggregation_scope,
                    "date_window": date_window,
                }
                scoped_row.update(row)
                scoped_row["source_status"] = source_status
                rows.append(scoped_row)
    return rows


def source_missing_rows(
    specs: list[FactorSpec],
    *,
    aggregation_scope: str,
    date_window: str,
    source_status: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        rows.append(
            {
                "aggregation_scope": aggregation_scope,
                "date_window": date_window,
                "factor_family": spec.family,
                "factor_name": f"{spec.primitive}__source_missing",
                "primitive": spec.primitive,
                "transform": "source_missing",
                "label": "",
                "horizon": "",
                "n": 0,
                "mean": math.nan,
                "median": math.nan,
                "top_bottom": math.nan,
                "cvar05": math.nan,
                "daily_sign_rate": math.nan,
                "spearman": math.nan,
                "mid_minus_executable_bps": math.nan,
                "runtime_safe": spec.runtime_safe,
                "status": "source_missing_or_external_panel",
                "source_layer": spec.source_layer,
                "source_status": source_status,
                "description": spec.description,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    lines: list[str] = []
    lines.append("# CCUSDT Microstructure Factor Diagnostic v0.1")
    lines.append("")
    lines.append("Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    for key in ["symbol", "from_date", "to_date", "source", "horizon_sec", "release_sec", "out_dir"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("This report is a diagnostic table generator output. Future path labels are used only as labels; they must not enter Runner or Bot runtime.")
    lines.append("")
    lines.append("Aggregation semantics:")
    lines.append("")
    lines.append("- `aggregation_scope=pooled` means one quantile cut and one summary over the full requested date window.")
    lines.append("- `aggregation_scope=daily` means the same statistic was computed on a single day. Do not compare pooled and daily rows as if they were the same estimator.")
    lines.append("")
    lines.append("## Status Counts")
    lines.append("")
    if df.empty:
        lines.append("No rows.")
    else:
        counts = df.groupby(["aggregation_scope", "source_layer", "status"]).size().reset_index(name="rows")
        lines.append("| scope | source | status | rows |")
        lines.append("|---|---|---|---:|")
        for row in counts.to_dict("records"):
            lines.append(f"| {row['aggregation_scope']} | {row['source_layer']} | {row['status']} | {row['rows']} |")
    lines.append("")
    lines.append("## Top Pooled Diagnostic Rows")
    lines.append("")
    if df.empty:
        lines.append("No rows.")
    else:
        display_df = df[df["aggregation_scope"].astype(str) == "pooled"].copy()
        if display_df.empty:
            display_df = df.copy()
        focus = display_df[display_df["label"].astype(str).str.startswith("top_of_book")].copy()
        if focus.empty:
            focus = display_df.copy()
        focus["mean_num"] = pd.to_numeric(focus["mean"], errors="coerce")
        focus["top_bottom_num"] = pd.to_numeric(focus["top_bottom"], errors="coerce")
        focus = focus.sort_values(["mean_num", "top_bottom_num"], ascending=False).head(20)
        lines.append("| window | source | factor | label | n | mean | median | top-bottom | cvar05 | daily sign | status |")
        lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|")
        for row in focus.to_dict("records"):
            lines.append(
                "| {window} | {source} | {factor} | {label} | {n} | {mean} | {median} | {tb} | {cvar} | {daily} | {status} |".format(
                    window=row["date_window"],
                    source=row["source_layer"],
                    factor=row["factor_name"],
                    label=row["label"],
                    n=row["n"],
                    mean=format_float(row["mean"]),
                    median=format_float(row["median"]),
                    tb=format_float(row["top_bottom"]),
                    cvar=format_float(row["cvar05"]),
                    daily=format_float(row["daily_sign_rate"]),
                    status=row["status"],
                )
            )
    lines.append("")
    lines.append("## Data Boundary")
    lines.append("")
    lines.append("- Full trade-flow diagnostics require `trade_event_v1`; current canonical CSV coverage is known through `2026-05-18`.")
    lines.append("- Quote-only recent windows must not be mixed with full TFI/OFI/MLOFI evidence.")
    lines.append("- `fixed_event_panel` rows come from derived research panels and remain diagnostics, not runtime inputs.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    windows = [int(part.strip()) for part in args.memory_windows.split(",") if part.strip()]
    if not windows:
        windows = [5, 10]
    out_dir = args.out_dir
    if out_dir is None:
        out_dir = DEFAULT_OUT_ROOT / f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_{args.source}_v0_1"
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    source_manifests: list[dict[str, Any]] = []
    days = list(date_range(args.from_date, args.to_date))
    pooled_window = args.from_date if args.from_date == args.to_date else f"{args.from_date}..{args.to_date}"
    source_frames: dict[str, list[pd.DataFrame]] = {
        "decision_frame_v1": [],
        "fixed_event_panel": [],
    }

    for day in days:
        if args.source in {"decision_frame", "both"}:
            print(f"microstructure_factor_diagnostic source=decision_frame day={day}", file=sys.stderr, flush=True)
            df, manifest = load_decision_frames(repo_root, args.symbol, day, args.max_rows_per_day)
            source_frames["decision_frame_v1"].append(df)
            rows.extend(
                summarize_source(
                    df,
                    DECISION_FACTOR_SPECS,
                    aggregation_scope="daily",
                    date_window=day,
                    source_status="loaded",
                    horizon_sec=args.horizon_sec,
                    release_sec=args.release_sec,
                    windows=windows,
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
            print(f"microstructure_factor_diagnostic source=fixed_event day={day}", file=sys.stderr, flush=True)
            fixed_df, fixed_manifest = load_fixed_event_panel(repo_root, args.symbol, day, args.max_rows_per_day)
            source_manifests.append(fixed_manifest)
            if fixed_df is None:
                rows.extend(
                    source_missing_rows(
                        FIXED_EVENT_FACTOR_SPECS,
                        aggregation_scope="daily",
                        date_window=day,
                        source_status="missing",
                    )
                )
            else:
                source_frames["fixed_event_panel"].append(fixed_df)
                rows.extend(
                    summarize_source(
                        fixed_df,
                        FIXED_EVENT_FACTOR_SPECS,
                        aggregation_scope="daily",
                        date_window=day,
                        source_status="loaded",
                        horizon_sec=args.horizon_sec,
                        release_sec=args.release_sec,
                        windows=windows,
                        top_q=args.top_quantile,
                        bottom_q=args.bottom_quantile,
                    )
                )

    if args.source in {"decision_frame", "both"} and source_frames["decision_frame_v1"]:
        print(
            f"microstructure_factor_diagnostic source=decision_frame pooled={pooled_window}",
            file=sys.stderr,
            flush=True,
        )
        pooled_df = pd.concat(source_frames["decision_frame_v1"], ignore_index=True)
        rows.extend(
            summarize_source(
                pooled_df,
                DECISION_FACTOR_SPECS,
                aggregation_scope="pooled",
                date_window=pooled_window,
                source_status="loaded",
                horizon_sec=args.horizon_sec,
                release_sec=args.release_sec,
                windows=windows,
                top_q=args.top_quantile,
                bottom_q=args.bottom_quantile,
            )
        )

    if args.source in {"fixed_event", "both"}:
        if source_frames["fixed_event_panel"]:
            print(
                f"microstructure_factor_diagnostic source=fixed_event pooled={pooled_window}",
                file=sys.stderr,
                flush=True,
            )
            pooled_df = pd.concat(source_frames["fixed_event_panel"], ignore_index=True)
            fixed_source_status = "loaded" if len(source_frames["fixed_event_panel"]) == len(days) else "partial_loaded"
            rows.extend(
                summarize_source(
                    pooled_df,
                    FIXED_EVENT_FACTOR_SPECS,
                    aggregation_scope="pooled",
                    date_window=pooled_window,
                    source_status=fixed_source_status,
                    horizon_sec=args.horizon_sec,
                    release_sec=args.release_sec,
                    windows=windows,
                    top_q=args.top_quantile,
                    bottom_q=args.bottom_quantile,
                )
            )
        else:
            rows.extend(
                source_missing_rows(
                    FIXED_EVENT_FACTOR_SPECS,
                    aggregation_scope="pooled",
                    date_window=pooled_window,
                    source_status="missing",
                )
            )

    summary = {
        "schema_id": "ccusdt_microstructure_factor_diagnostic_summary_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "source": args.source,
        "horizon_sec": args.horizon_sec,
        "release_sec": args.release_sec,
        "memory_windows": windows,
        "top_quantile": args.top_quantile,
        "bottom_quantile": args.bottom_quantile,
        "max_rows_per_day": args.max_rows_per_day,
        "diagnostic_rows": len(rows),
        "out_dir": str(out_dir),
        "report_path": str(report_path),
        "elapsed_wall_ms": int((time.perf_counter() - started) * 1000),
        "source_manifests": source_manifests,
        "outputs": {
            "factor_diagnostics_csv": str(out_dir / "factor_diagnostics.csv"),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    write_csv(out_dir / "factor_diagnostics.csv", rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(report_path, summary, rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
