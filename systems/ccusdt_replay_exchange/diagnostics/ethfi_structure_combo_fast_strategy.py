#!/usr/bin/env python
"""ETHFIUSDC structure-combo fast strategy diagnostic.

Research-only. This script reads decision_frame_v1 and quote_frame_v1, builds
E0 active-flow flat-release episodes, evaluates low-degree memory sizing, and
computes diagnostic-only path labels. It must not become Runner/Bot runtime
input.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import random
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
QUOTE_FRAME_ROOT = Path("data/canonical/cex/bullish")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/ethfi_structure_combo_fast_strategy")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/strategy/v1-ethfiusdc-structure-combo-strategy-20260602.md")
DEFAULT_ADMISSION_THRESHOLDS = Path(
    "systems/ccusdt_replay_exchange/runs/admission_thresholds/"
    "ethfiusdc_entry_spread_q70_20260525_31_20260602.json"
)
DEFAULT_OLD_FOURCELL_RUN = Path(
    "systems/ccusdt_replay_exchange/runs/experiments/"
    "ethfiusdc_old_fourcell_idle01_g1_fixed60_taker_q70_20260525_31_rustdf_v0_1"
)

SCHEMA_ID = "ethfi_structure_combo_fast_strategy_v0_1"
US_PER_SEC = 1_000_000
EPS = 1e-12


@dataclass(frozen=True)
class AdmissionThreshold:
    entry_cross_threshold_bps: float
    threshold_source: str


class QuoteFrameIndex:
    def __init__(self, frames: list[dict[str, Any]]) -> None:
        if not frames:
            raise ValueError("quote_frame_v1 index is empty")
        self.local_ts = np.array([int(row["local_ts_us"]) for row in frames], dtype=np.int64)
        self.bid = np.array([float(row["bid_px"]) for row in frames], dtype=float)
        self.ask = np.array([float(row["ask_px"]) for row in frames], dtype=float)
        self.mid = np.array([float(row["mid_px"]) for row in frames], dtype=float)

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteFrameIndex":
        path = quote_frame_path(repo_root, symbol, day)
        frames: list[dict[str, Any]] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                bid = optional_float(row.get("bid_px"))
                ask = optional_float(row.get("ask_px"))
                local_ts_us = optional_int(row.get("local_ts_us")) or 0
                if bid is None or ask is None or bid <= 0.0 or ask <= 0.0 or local_ts_us <= 0:
                    continue
                mid = optional_float(row.get("mid_px"))
                if mid is None or mid <= 0.0:
                    mid = 0.5 * (bid + ask)
                frames.append(
                    {
                        "local_ts_us": local_ts_us,
                        "bid_px": bid,
                        "ask_px": ask,
                        "mid_px": mid,
                    }
                )
        return cls(frames)

    def index_at_or_before(self, local_ts_us: int) -> int:
        idx = int(np.searchsorted(self.local_ts, int(local_ts_us), side="right") - 1)
        return max(0, min(idx, len(self.local_ts) - 1))

    def labels(self, local_ts_us: int, side_sign: int) -> dict[str, Any]:
        entry_idx = self.index_at_or_before(local_ts_us)
        entry_ts = int(self.local_ts[entry_idx])
        entry_bid = float(self.bid[entry_idx])
        entry_ask = float(self.ask[entry_idx])
        entry_mid = float(self.mid[entry_idx])
        entry_cross_bps = 0.5 * 10_000.0 * math.log(entry_ask / entry_bid)

        out: dict[str, Any] = {
            "entry_quote_ts_us": entry_ts,
            "entry_bid": entry_bid,
            "entry_ask": entry_ask,
            "entry_mid": entry_mid,
            "entry_cross_bps": entry_cross_bps,
            "label_valid": True,
        }
        for horizon in [5, 20, 60, 120]:
            idx = self.index_at_or_before(local_ts_us + horizon * US_PER_SEC)
            exit_bid = float(self.bid[idx])
            exit_ask = float(self.ask[idx])
            exit_mid = float(self.mid[idx])
            mid_ret = side_sign * 10_000.0 * math.log(exit_mid / entry_mid)
            exec_ret = (
                10_000.0 * math.log(exit_bid / entry_ask)
                if side_sign > 0
                else 10_000.0 * math.log(entry_bid / exit_ask)
            )
            exit_cross = 0.5 * 10_000.0 * math.log(exit_ask / exit_bid)
            out[f"exit{horizon}_quote_ts_us"] = int(self.local_ts[idx])
            out[f"exit{horizon}_bid"] = exit_bid
            out[f"exit{horizon}_ask"] = exit_ask
            out[f"exit{horizon}_mid"] = exit_mid
            out[f"mid_return_{horizon}s_bps"] = mid_ret
            out[f"executable_return_{horizon}s_bps"] = exec_ret
            out[f"exit_cross_{horizon}s_bps"] = exit_cross
            if idx <= entry_idx:
                out["label_valid"] = False

        for horizon in [5, 10, 20]:
            idx = self.index_at_or_before(local_ts_us + horizon * US_PER_SEC)
            path = self.mid[entry_idx : idx + 1]
            if side_sign > 0:
                signed_path = 10_000.0 * np.log(path / entry_mid)
            else:
                signed_path = 10_000.0 * np.log(entry_mid / path)
            mfe = float(np.nanmax(signed_path)) if len(signed_path) else 0.0
            mae = float(np.nanmin(signed_path)) if len(signed_path) else 0.0
            mfe_idx = int(np.nanargmax(signed_path)) if len(signed_path) else 0
            out[f"release_mfe_{horizon}s_bps"] = mfe
            out[f"mae_{horizon}s_bps"] = mae
            if horizon == 20:
                out["time_to_mfe_20s"] = float((int(self.local_ts[entry_idx + mfe_idx]) - entry_ts) / US_PER_SEC)

        out["mae_60s_bps"] = self._mae(local_ts_us, side_sign, 60, entry_idx, entry_mid)
        out["decay_after_mfe_60s_bps"] = out["release_mfe_10s_bps"] - out["mid_return_60s_bps"]
        out["mid_minus_executable_60s_bps"] = out["mid_return_60s_bps"] - out["executable_return_60s_bps"]

        now_exec60 = float(out["executable_return_60s_bps"])
        for wait_sec in [1, 2, 3, 5, 10]:
            wait_idx = self.index_at_or_before(local_ts_us + wait_sec * US_PER_SEC)
            wait_bid = float(self.bid[wait_idx])
            wait_ask = float(self.ask[wait_idx])
            exit60_bid = float(out["exit60_bid"])
            exit60_ask = float(out["exit60_ask"])
            wait_exec = (
                10_000.0 * math.log(exit60_bid / wait_ask)
                if side_sign > 0
                else 10_000.0 * math.log(wait_bid / exit60_ask)
            )
            out[f"wait_exec_{wait_sec}s_fixed60_bps"] = wait_exec
            out[f"wait_gain_{wait_sec}s_bps"] = wait_exec - now_exec60
        return out

    def _mae(self, local_ts_us: int, side_sign: int, horizon: int, entry_idx: int, entry_mid: float) -> float:
        idx = self.index_at_or_before(local_ts_us + horizon * US_PER_SEC)
        path = self.mid[entry_idx : idx + 1]
        if not len(path):
            return 0.0
        if side_sign > 0:
            signed_path = 10_000.0 * np.log(path / entry_mid)
        else:
            signed_path = 10_000.0 * np.log(entry_mid / path)
        return float(np.nanmin(signed_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="ETHFIUSDC")
    parser.add_argument("--from-date", default="2026-05-25")
    parser.add_argument("--to-date", default="2026-05-31")
    parser.add_argument("--default-episode-sec", type=int, default=5)
    parser.add_argument("--episode-sensitivity-sec", default="2,5,10")
    parser.add_argument("--max-rows-per-day", type=int, default=0)
    parser.add_argument("--leverage-cap", type=float, default=3.0)
    parser.add_argument("--admission-thresholds-json", type=Path, default=DEFAULT_ADMISSION_THRESHOLDS)
    parser.add_argument("--old-fourcell-run-dir", type=Path, default=DEFAULT_OLD_FOURCELL_RUN)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--run-id")
    parser.add_argument("--random-seed", type=int, default=20260602)
    return parser.parse_args()


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def optional_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def date_range(start: str, end: str) -> list[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    out: list[str] = []
    while cur <= last:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def previous_day(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def decision_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def quote_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / QUOTE_FRAME_ROOT / symbol / "quote_frame_v1" / f"dt={day}" / "part_000001.csv.gz"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows) if rows else pa.table({})
    pq.write_table(table, path, compression="zstd")


def load_decision_frame(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> pd.DataFrame:
    path = decision_frame_path(repo_root, symbol, day)
    if not path.exists():
        raise FileNotFoundError(path)
    schema = pq.read_schema(path)
    columns = [
        "runtime_safe",
        "observed_seq",
        "event_index",
        "factor_eligible",
        "local_ts_us",
        "local_timestamp",
        "best_bid_price",
        "best_bid_amount",
        "best_ask_price",
        "best_ask_amount",
        "mid",
        "mid_price",
        "spread_bps",
        "trade_window_count",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]
    table = pq.read_table(path, columns=[col for col in columns if col in schema.names])
    df = table.to_pandas()
    if "factor_eligible" in df.columns:
        df = df[df["factor_eligible"].fillna(False)].copy()
    if "local_ts_us" not in df.columns and "local_timestamp" in df.columns:
        df["local_ts_us"] = df["local_timestamp"]
    if "mid" not in df.columns and "mid_price" in df.columns:
        df["mid"] = df["mid_price"]
    df = df.rename(
        columns={
            "best_bid_price": "bid",
            "best_ask_price": "ask",
            "best_bid_amount": "bid_amount",
            "best_ask_amount": "ask_amount",
        }
    )
    for col in [
        "observed_seq",
        "event_index",
        "local_ts_us",
        "bid",
        "ask",
        "bid_amount",
        "ask_amount",
        "mid",
        "spread_bps",
        "trade_window_count",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["local_ts_us", "bid", "ask", "mid"]).copy()
    df = df[(df["bid"] > 0.0) & (df["ask"] > 0.0) & (df["mid"] > 0.0)].copy()
    df["local_ts_us"] = df["local_ts_us"].astype("int64")
    df["date"] = day
    df["entry_cross_bps"] = 0.5 * 10_000.0 * np.log(df["ask"].astype(float) / df["bid"].astype(float))
    df = df.sort_values("local_ts_us").reset_index(drop=True)
    if max_rows > 0 and len(df) > max_rows:
        stride = max(1, int(math.ceil(len(df) / max_rows)))
        df = df.iloc[::stride].head(max_rows).reset_index(drop=True)
    return df


def load_admission_thresholds(repo_root: Path, path: Path) -> dict[str, AdmissionThreshold]:
    raw = read_json(path if path.is_absolute() else repo_root / path)
    rows = raw.get("thresholds", raw)
    out: dict[str, AdmissionThreshold] = {}
    if not isinstance(rows, dict):
        return out
    for day, value in rows.items():
        if isinstance(value, dict):
            threshold = optional_float(value.get("entry_cross_threshold_bps") or value.get("threshold_bps"))
            source = str(value.get("threshold_source") or value.get("source") or "")
        else:
            threshold = optional_float(value)
            source = ""
        if threshold is not None:
            out[str(day)] = AdmissionThreshold(threshold, source or f"{path}:{day}")
    return out


def e0_mask(df: pd.DataFrame, threshold_bps: float) -> pd.Series:
    tfi = df["trade_flow_imbalance"].fillna(0.0)
    past = df["past_event_25_bps"].fillna(np.inf)
    trade_count = df["trade_window_count"].fillna(0.0)
    return (
        (tfi.abs() >= 1.0)
        & (past.abs() <= 0.5)
        & (trade_count > 0)
        & (df["entry_cross_bps"] <= threshold_bps)
    )


def side_from_tfi(value: float) -> int:
    return 1 if value >= 0.0 else -1


def hour_bucket(local_ts_us: int) -> int:
    return int((local_ts_us // (3600 * US_PER_SEC)) % 24)


def activity_bucket(trade_count: float) -> str:
    if trade_count <= 0:
        return "zero"
    if trade_count <= 2:
        return "low"
    if trade_count <= 8:
        return "mid"
    return "high"


def cell_from_memory(r5: float | None, frames: float, r5_threshold: float = 1.0, frames_threshold: float = 31.0) -> str:
    a = bool(r5 is not None and math.isfinite(r5) and r5 >= r5_threshold)
    b = bool(frames >= frames_threshold)
    if a and b:
        return "11_r5_frames"
    if a:
        return "10_r5_only"
    if b:
        return "01_frames_only"
    return "00_none"


def memory_snapshot(values: deque[float]) -> dict[str, Any]:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    pos = [v for v in vals if v > 0.0]
    neg = [v for v in vals if v < 0.0]
    p = float(sum(pos))
    n = float(sum(-v for v in neg))
    energy = p + n
    delta = p - n
    r5 = None if n <= EPS else p / n
    return {
        "memory_count": len(vals),
        "positive_count": len(pos),
        "negative_count": len(neg),
        "positive_bps": p,
        "negative_abs_bps": n,
        "delta5_bps": delta,
        "energy5_bps": energy,
        "z5_bps": delta / math.sqrt(energy + EPS) if energy > 0.0 else 0.0,
        "r5": r5,
        "r5_ready": len(vals) >= 5,
    }


def build_episodes(
    *,
    repo_root: Path,
    symbol: str,
    days: list[str],
    thresholds: dict[str, AdmissionThreshold],
    compression_sec: int,
    max_rows_per_day: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, pd.DataFrame]]:
    episodes: list[dict[str, Any]] = []
    raw_counts: dict[str, Any] = {}
    frames_by_day: dict[str, pd.DataFrame] = {}
    episode_id = 1
    for day in days:
        df = load_decision_frame(repo_root, symbol, day, max_rows_per_day)
        frames_by_day[day] = df
        threshold = thresholds.get(day)
        if threshold is None:
            prev_df = load_decision_frame(repo_root, symbol, previous_day(day), max_rows_per_day)
            threshold_value = float(prev_df["entry_cross_bps"].quantile(0.70))
            threshold_source = f"computed_prior_day_q70:{previous_day(day)}"
        else:
            threshold_value = threshold.entry_cross_threshold_bps
            threshold_source = threshold.threshold_source
        mask = e0_mask(df, threshold_value)
        raw = df[mask].copy()
        raw_counts[day] = {"raw_e0_rows": int(len(raw)), "admission_q70_bps": threshold_value}
        last_by_side: dict[int, int] = {}
        for _, row in raw.iterrows():
            side = side_from_tfi(float(row["trade_flow_imbalance"]))
            ts = int(row["local_ts_us"])
            last_ts = last_by_side.get(side)
            if last_ts is not None and ts - last_ts <= compression_sec * US_PER_SEC:
                continue
            last_by_side[side] = ts
            episodes.append(
                {
                    "episode_id": episode_id,
                    "date": day,
                    "local_ts_us": ts,
                    "observed_seq": optional_int(row.get("observed_seq")) or 0,
                    "event_index": optional_int(row.get("event_index")) or 0,
                    "side_sign": side,
                    "side": "buy" if side > 0 else "sell",
                    "trade_flow_imbalance": float(row["trade_flow_imbalance"]),
                    "past_event_25_bps": float(row["past_event_25_bps"]),
                    "frames_since_mid_change": float(row["frames_since_mid_change"]),
                    "trade_window_count": float(row["trade_window_count"]),
                    "entry_cross_bps": float(row["entry_cross_bps"]),
                    "admission_q70_bps": float(threshold_value),
                    "admission_threshold_source": threshold_source,
                    "hour_bucket": hour_bucket(ts),
                    "activity_bucket": activity_bucket(float(row["trade_window_count"])),
                }
            )
            episode_id += 1
    return episodes, raw_counts, frames_by_day


def attach_labels(
    repo_root: Path,
    symbol: str,
    episodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quote_by_day: dict[str, QuoteFrameIndex] = {}
    out: list[dict[str, Any]] = []
    for episode in episodes:
        day = str(episode["date"])
        if day not in quote_by_day:
            quote_by_day[day] = QuoteFrameIndex.load(repo_root, symbol, day)
        labels = quote_by_day[day].labels(int(episode["local_ts_us"]), int(episode["side_sign"]))
        flipped = quote_by_day[day].labels(int(episode["local_ts_us"]), -int(episode["side_sign"]))
        row = dict(episode)
        row.update(labels)
        row["side_flip_executable_60s_bps"] = flipped["executable_return_60s_bps"]
        row["side_flip_mid_60s_bps"] = flipped["mid_return_60s_bps"]
        row["path_class"] = classify_path(row)
        row["wait_class"] = classify_wait(row)
        out.append(row)
    return out


def classify_wait(row: dict[str, Any]) -> str:
    gains = [float(row.get(f"wait_gain_{sec}s_bps") or 0.0) for sec in [1, 2, 3, 5, 10]]
    best = max(gains) if gains else 0.0
    worst = min(gains) if gains else 0.0
    if best > 0.25:
        return "wait_better"
    if worst < -0.25:
        return "cross_now_better"
    return "indifferent"


def classify_path(row: dict[str, Any]) -> str:
    exec60 = float(row.get("executable_return_60s_bps") or 0.0)
    mid60 = float(row.get("mid_return_60s_bps") or 0.0)
    mfe10 = float(row.get("release_mfe_10s_bps") or 0.0)
    decay = float(row.get("decay_after_mfe_60s_bps") or 0.0)
    if mid60 > 0.0 and exec60 <= 0.0:
        return "spread_cost_mirage"
    if mfe10 <= 1.0 and exec60 <= 0.0:
        return "bad_entry"
    if mfe10 >= 2.0 and (exec60 <= 0.0 or decay >= max(5.0, 0.75 * mfe10)):
        return "fast_release_decay"
    if exec60 > 0.0 and mfe10 > 0.0 and decay <= max(5.0, 0.5 * mfe10):
        return "good_release_hold"
    return "neutral"


def cost_q50_by_day(repo_root: Path, symbol: str, days: list[str], max_rows_per_day: int) -> dict[str, float]:
    out: dict[str, float] = {}
    for day in days:
        source_day = previous_day(day)
        try:
            df = load_decision_frame(repo_root, symbol, source_day, max_rows_per_day)
        except FileNotFoundError:
            df = load_decision_frame(repo_root, symbol, day, max_rows_per_day)
        out[day] = float(df["entry_cross_bps"].quantile(0.50))
    return out


def add_memory_and_thresholds(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: deque[tuple[int, float]] = deque()
    memory: deque[float] = deque(maxlen=5)
    snapshots_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    thresholds_by_day: dict[str, dict[str, float | None]] = {}
    out: list[dict[str, Any]] = []
    for episode in sorted(episodes, key=lambda row: (str(row["date"]), int(row["local_ts_us"]), int(row["episode_id"]))):
        ts = int(episode["local_ts_us"])
        while pending and pending[0][0] < ts:
            _, outcome = pending.popleft()
            memory.append(float(outcome))
        snap = memory_snapshot(memory)
        day = str(episode["date"])
        if day not in thresholds_by_day:
            prev = previous_day(day)
            prev_snaps = snapshots_by_day.get(prev, [])
            thresholds_by_day[day] = {
                "delta_q70": quantile([row["delta5_bps"] for row in prev_snaps if row["r5_ready"]], 0.70),
                "energy_q70": quantile([row["energy5_bps"] for row in prev_snaps if row["r5_ready"]], 0.70),
            }
        thresholds = thresholds_by_day[day]
        delta_thr = thresholds["delta_q70"]
        energy_thr = thresholds["energy_q70"]
        row = dict(episode)
        row.update(snap)
        row["memory_delta_q70_prior_day"] = delta_thr
        row["memory_energy_q70_prior_day"] = energy_thr
        row["delta_high"] = bool(delta_thr is not None and snap["delta5_bps"] >= float(delta_thr))
        row["energy_high"] = bool(energy_thr is not None and snap["energy5_bps"] >= float(energy_thr))
        row["cell"] = cell_from_memory(snap["r5"], float(row.get("frames_since_mid_change") or 0.0))
        out.append(row)
        snapshots_by_day[day].append(row)
        pending.append((ts + 60 * US_PER_SEC, float(row["mid_return_60s_bps"])))
    return out


def quantile(values: list[float], q: float) -> float | None:
    clean = [float(v) for v in values if math.isfinite(float(v))]
    if not clean:
        return None
    return float(np.quantile(clean, q))


def requested_exposure(variant_id: str, row: dict[str, Any], q50_by_day: dict[str, float]) -> float:
    if variant_id == "A_fixed_small":
        return 0.50
    if variant_id == "C_memory_sized":
        exposure = 0.50
        r5 = row.get("r5")
        r5_good = bool(r5 is not None and math.isfinite(float(r5)) and float(r5) >= 1.0)
        if r5_good and row.get("delta_high"):
            exposure = 0.75
        if r5_good and row.get("delta_high") and row.get("energy_high"):
            exposure = 1.00
        if row.get("cell") == "11_r5_frames" and not row.get("delta_high"):
            exposure = min(exposure, 0.50)
        q50 = q50_by_day.get(str(row["date"]))
        if q50 is not None and float(row.get("entry_cross_bps") or 0.0) <= q50:
            exposure += 0.25
        return min(exposure, 1.25)
    raise ValueError(f"unknown variant: {variant_id}")


def simulate_variant(
    variant_id: str,
    episodes: list[dict[str, Any]],
    *,
    leverage_cap: float,
    q50_by_day: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    open_positions: deque[dict[str, Any]] = deque()
    open_exposure = 0.0
    entries: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    for row in sorted(episodes, key=lambda item: (str(item["date"]), int(item["local_ts_us"]), int(item["episode_id"]))):
        ts = int(row["local_ts_us"])
        while open_positions and int(open_positions[0]["due_ts_us"]) <= ts:
            pos = open_positions.popleft()
            open_exposure -= float(pos["actual_exposure"])
            exit_row = dict(pos)
            exit_row.update(
                {
                    "exit_ts_us": int(pos["due_ts_us"]),
                    "net_bps": float(pos["executable_return_60s_bps"]),
                    "net_weighted_bps": float(pos["actual_exposure"]) * float(pos["executable_return_60s_bps"]),
                }
            )
            exits.append(exit_row)
        req = requested_exposure(variant_id, row, q50_by_day)
        actual = max(0.0, min(req, leverage_cap - open_exposure))
        entry = {
            "variant_id": variant_id,
            "episode_id": row["episode_id"],
            "date": row["date"],
            "local_ts_us": row["local_ts_us"],
            "side": row["side"],
            "side_sign": row["side_sign"],
            "cell": row["cell"],
            "path_class": row["path_class"],
            "wait_class": row["wait_class"],
            "requested_exposure": req,
            "actual_exposure": actual,
            "skipped": actual <= 0.0,
            "open_exposure_before": open_exposure,
            "entry_cross_bps": row["entry_cross_bps"],
            "r5": row["r5"],
            "delta5_bps": row["delta5_bps"],
            "energy5_bps": row["energy5_bps"],
            "z5_bps": row["z5_bps"],
            "delta_high": row["delta_high"],
            "energy_high": row["energy_high"],
            "executable_return_20s_bps": row["executable_return_20s_bps"],
            "executable_return_60s_bps": row["executable_return_60s_bps"],
            "executable_return_120s_bps": row["executable_return_120s_bps"],
            "mid_return_60s_bps": row["mid_return_60s_bps"],
            "release_mfe_10s_bps": row["release_mfe_10s_bps"],
            "decay_after_mfe_60s_bps": row["decay_after_mfe_60s_bps"],
            "due_ts_us": int(row["local_ts_us"]) + 60 * US_PER_SEC,
        }
        entries.append(entry)
        if actual > 0.0:
            open_exposure += actual
            open_positions.append(entry)
    while open_positions:
        pos = open_positions.popleft()
        open_exposure -= float(pos["actual_exposure"])
        exit_row = dict(pos)
        exit_row.update(
            {
                "exit_ts_us": int(pos["due_ts_us"]),
                "net_bps": float(pos["executable_return_60s_bps"]),
                "net_weighted_bps": float(pos["actual_exposure"]) * float(pos["executable_return_60s_bps"]),
            }
        )
        exits.append(exit_row)
    return entries, exits


def summarize_variant(variant_id: str, entries: list[dict[str, Any]], exits: list[dict[str, Any]]) -> dict[str, Any]:
    actual = [row for row in entries if float(row["actual_exposure"]) > 0.0]
    exit_bps = [float(row["net_bps"]) for row in exits if float(row.get("actual_exposure") or 0.0) > 0.0]
    total_exposure = sum(float(row["actual_exposure"]) for row in actual)
    weighted_bps = sum(float(row["net_weighted_bps"]) for row in exits)
    days = sorted({str(row["date"]) for row in entries})
    daily = daily_summary(entries, exits, variant_id)
    return {
        "variant_id": variant_id,
        "entries": len(entries),
        "actual_entries": len(actual),
        "total_actual_exposure": total_exposure,
        "mean_unit_exec60_bps": mean(exit_bps),
        "median_unit_exec60_bps": median(exit_bps),
        "hit_rate": hit_rate(exit_bps),
        "net_weighted_bps": weighted_bps,
        "weighted_bps_per_exposure": weighted_bps / total_exposure if total_exposure > 0.0 else 0.0,
        "positive_days": sum(1 for row in daily if float(row["net_weighted_bps"]) > 0.0),
        "days": len(days),
        "worst_day_net_weighted_bps": min([float(row["net_weighted_bps"]) for row in daily], default=0.0),
    }


def daily_summary(entries: list[dict[str, Any]], exits: list[dict[str, Any]], variant_id: str) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, Any]] = {}
    for entry in entries:
        day = str(entry["date"])
        row = by_day.setdefault(
            day,
            {"variant_id": variant_id, "date": day, "entries": 0, "actual_entries": 0, "actual_exposure": 0.0, "net_weighted_bps": 0.0},
        )
        row["entries"] += 1
        if float(entry["actual_exposure"]) > 0.0:
            row["actual_entries"] += 1
            row["actual_exposure"] += float(entry["actual_exposure"])
    for exit_row in exits:
        day = str(exit_row["date"])
        row = by_day.setdefault(
            day,
            {"variant_id": variant_id, "date": day, "entries": 0, "actual_entries": 0, "actual_exposure": 0.0, "net_weighted_bps": 0.0},
        )
        row["net_weighted_bps"] += float(exit_row["net_weighted_bps"])
    return [by_day[day] for day in sorted(by_day)]


def mean(values: list[float]) -> float:
    clean = [v for v in values if math.isfinite(v)]
    return float(np.mean(clean)) if clean else 0.0


def median(values: list[float]) -> float:
    clean = [v for v in values if math.isfinite(v)]
    return float(np.median(clean)) if clean else 0.0


def hit_rate(values: list[float]) -> float:
    clean = [v for v in values if math.isfinite(v)]
    return float(sum(1 for v in clean if v > 0.0) / len(clean)) if clean else 0.0


def group_summary(rows: list[dict[str, Any]], group_cols: list[str], value_col: str = "executable_return_60s_bps") -> list[dict[str, Any]]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    out: list[dict[str, Any]] = []
    for keys, group in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = pd.to_numeric(group[value_col], errors="coerce").dropna()
        row = {col: key for col, key in zip(group_cols, keys)}
        row.update(
            {
                "n": int(len(group)),
                f"mean_{value_col}": float(values.mean()) if len(values) else 0.0,
                f"median_{value_col}": float(values.median()) if len(values) else 0.0,
                "hit_rate": float((values > 0.0).mean()) if len(values) else 0.0,
                "mean_mid60_bps": float(pd.to_numeric(group["mid_return_60s_bps"], errors="coerce").mean()),
                "mean_release_mfe10_bps": float(pd.to_numeric(group["release_mfe_10s_bps"], errors="coerce").mean()),
                "mean_decay60_bps": float(pd.to_numeric(group["decay_after_mfe_60s_bps"], errors="coerce").mean()),
            }
        )
        out.append(row)
    return out


def memory_bucket(row: dict[str, Any]) -> str:
    if not row.get("r5_ready"):
        return "not_ready"
    if row.get("delta_high") and row.get("energy_high"):
        return "high_delta_high_energy"
    if row.get("delta_high"):
        return "high_delta"
    if row.get("energy_high"):
        return "high_energy"
    return "low_memory"


def build_controls(
    *,
    frames_by_day: dict[str, pd.DataFrame],
    episodes: list[dict[str, Any]],
    quote_by_day: dict[str, QuoteFrameIndex],
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    side_flip = [
        {
            "control": "side_flip",
            "episode_id": row["episode_id"],
            "date": row["date"],
            "side": "sell" if row["side"] == "buy" else "buy",
            "exec60_bps": row["side_flip_executable_60s_bps"],
            "mid60_bps": row["side_flip_mid_60s_bps"],
        }
        for row in episodes
    ]
    matched: list[dict[str, Any]] = []
    for row in episodes:
        day = str(row["date"])
        df = frames_by_day[day]
        hour = int(row["hour_bucket"])
        activity = str(row["activity_bucket"])
        pool = df.copy()
        pool["hour_bucket"] = pool["local_ts_us"].map(hour_bucket)
        pool["activity_bucket"] = pool["trade_window_count"].map(activity_bucket)
        mask = (pool["hour_bucket"] == hour) & (pool["activity_bucket"] == activity)
        sample_pool = pool[mask]
        if sample_pool.empty:
            sample_pool = pool[pool["hour_bucket"] == hour]
        if sample_pool.empty:
            sample_pool = pool
        candidates = sample_pool.sample(n=min(len(sample_pool), 25), random_state=rng.randint(1, 1_000_000))
        idx = (candidates["entry_cross_bps"] - float(row["entry_cross_bps"])).abs().idxmin()
        pick = candidates.loc[idx]
        labels = quote_by_day[day].labels(int(pick["local_ts_us"]), int(row["side_sign"]))
        matched.append(
            {
                "control": "matched_time_spread_activity",
                "episode_id": row["episode_id"],
                "date": day,
                "matched_ts_us": int(pick["local_ts_us"]),
                "side": row["side"],
                "entry_cross_bps": float(pick["entry_cross_bps"]),
                "trade_window_count": float(pick["trade_window_count"]),
                "exec60_bps": labels["executable_return_60s_bps"],
                "mid60_bps": labels["mid_return_60s_bps"],
            }
        )
    return side_flip, matched


def cost_stress(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for variant in sorted({str(row["variant_id"]) for row in rows}):
        subset = [row for row in rows if str(row["variant_id"]) == variant and float(row.get("actual_exposure") or 0.0) > 0.0]
        for extra in [0.0, 1.0, 2.0, 3.0]:
            adjusted = [float(row["actual_exposure"]) * (float(row["executable_return_60s_bps"]) - extra) for row in subset]
            out.append(
                {
                    "variant_id": variant,
                    "extra_roundtrip_cost_bps": extra,
                    "actual_entries": len(subset),
                    "net_weighted_bps_after_stress": sum(adjusted),
                    "mean_unit_bps_after_stress": mean([float(row["executable_return_60s_bps"]) - extra for row in subset]),
                    "hit_rate_after_stress": hit_rate([float(row["executable_return_60s_bps"]) - extra for row in subset]),
                }
            )
    return out


def load_old_fourcell_summary(repo_root: Path, run_dir: Path) -> dict[str, Any] | None:
    path = run_dir if run_dir.is_absolute() else repo_root / run_dir
    summary = read_json(path / "summary.json")
    if not summary:
        return None
    return {
        "variant_id": "B_old_fourcell_reference",
        "entries": summary.get("entries"),
        "actual_entries": summary.get("actual_entries"),
        "total_actual_exposure": None,
        "mean_unit_exec60_bps": None,
        "median_unit_exec60_bps": None,
        "hit_rate": None,
        "net_weighted_bps": summary.get("net_weighted_bps"),
        "weighted_bps_per_exposure": None,
        "positive_days": summary.get("positive_days"),
        "days": summary.get("days"),
        "worst_day_net_weighted_bps": summary.get("worst_day_net_weighted_bps"),
        "source_run_dir": str(path),
    }


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    if not rows:
        return ["No rows."]
    lines = ["|" + "|".join(columns) + "|", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
        vals = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                vals.append(f"{value:.4f}")
            else:
                vals.append(str(value))
        lines.append("|" + "|".join(vals) + "|")
    return lines


def compact_path_rows(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[:limit]:
        out.append(
            {
                "episode_id": row.get("episode_id"),
                "date": row.get("date"),
                "side": row.get("side"),
                "cell": row.get("cell"),
                "memory_bucket": row.get("memory_bucket"),
                "path_class": row.get("path_class"),
                "exec60": row.get("executable_return_60s_bps"),
                "mid60": row.get("mid_return_60s_bps"),
                "mfe10": row.get("release_mfe_10s_bps"),
                "decay60": row.get("decay_after_mfe_60s_bps"),
                "entry_cross": row.get("entry_cross_bps"),
            }
        )
    return out


def write_casebook(path: Path, top_good: list[dict[str, Any]], worst_bad: list[dict[str, Any]], out_dir: Path) -> None:
    lines = [
        "# ETHFIUSDC Path Casebook",
        "",
        "These examples are diagnostic labels, not runtime inputs.",
        "",
        f"- top_good_paths parquet: `{out_dir / 'top_good_paths.parquet'}`",
        f"- worst_bad_paths parquet: `{out_dir / 'worst_bad_paths.parquet'}`",
        "",
        "## Top Good Paths",
        "",
    ]
    lines.extend(
        markdown_table(
            compact_path_rows(top_good, 12),
            ["episode_id", "date", "side", "cell", "memory_bucket", "path_class", "exec60", "mid60", "mfe10", "decay60", "entry_cross"],
        )
    )
    lines.extend(["", "## Worst Bad Paths", ""])
    lines.extend(
        markdown_table(
            compact_path_rows(worst_bad, 12),
            ["episode_id", "date", "side", "cell", "memory_bucket", "path_class", "exec60", "mid60", "mfe10", "decay60", "entry_cross"],
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def conclusion_lines(variant_summary: list[dict[str, Any]]) -> list[str]:
    by_id = {str(row.get("variant_id")): row for row in variant_summary}
    a = by_id.get("A_fixed_small", {})
    c = by_id.get("C_memory_sized", {})
    a_unit = optional_float(a.get("mean_unit_exec60_bps")) or 0.0
    c_unit = optional_float(c.get("mean_unit_exec60_bps")) or 0.0
    a_total = optional_float(a.get("net_weighted_bps")) or 0.0
    c_total = optional_float(c.get("net_weighted_bps")) or 0.0
    a_exposure = optional_float(a.get("total_actual_exposure")) or 0.0
    c_exposure = optional_float(c.get("total_actual_exposure")) or 0.0
    unit_lift = c_unit - a_unit
    total_lift = c_total - a_total
    exposure_lift = c_exposure - a_exposure
    lines = [
        "The v0.1 result is E0-centered.",
        "",
        "```text",
        f"C_memory_sized - A_fixed_small unit lift   = {unit_lift:.4f} bps",
        f"C_memory_sized - A_fixed_small total lift  = {total_lift:.4f} weighted bps",
        f"C_memory_sized - A_fixed_small exposure    = {exposure_lift:.4f}",
        "```",
        "",
    ]
    if abs(unit_lift) < 0.25 and total_lift > 0.0:
        lines.extend(
            [
                "Memory sizing increases total weighted PnL mostly by allocating more exposure to already-positive E0 episodes. It does not yet prove a new independent alpha layer.",
                "",
                "Therefore the first ETHFI strategy should remain `E0 active-flow flat-release` centered. `R5/Delta/Energy/Z` should be treated as sizing/risk state until stricter controls show unit edge improvement.",
            ]
        )
    elif unit_lift > 0.25:
        lines.extend(
            [
                "Memory sizing improves both total weighted PnL and unit executable return. This justifies a second-pass profile with memory state as a true sizing component.",
            ]
        )
    else:
        lines.extend(
            [
                "Memory sizing does not improve unit quality. Keep it out of promotion candidates and use it only for interpretation.",
            ]
        )
    return lines


def write_report(
    path: Path,
    *,
    symbol: str,
    days: list[str],
    raw_counts: dict[str, Any],
    variant_summary: list[dict[str, Any]],
    path_class_summary: list[dict[str, Any]],
    memory_summary: list[dict[str, Any]],
    cost_summary: list[dict[str, Any]],
    controls_summary: dict[str, Any],
    out_dir: Path,
) -> None:
    lines: list[str] = [
        "# ETHFIUSDC Structure Combo Strategy v0.1",
        "",
        "Status: `research_result_20260602`.",
        "",
        "Boundary: research-only. This diagnostic reads `decision_frame_v1` and `quote_frame_v1`; labels are diagnostic-only and must not enter Runner/Bot runtime.",
        "",
        "## Setup",
        "",
        f"- symbol: `{symbol}`",
        f"- dates: `{days[0]}..{days[-1]}`",
        f"- output: `{out_dir}`",
        "- entry center: `E0 active-flow flat-release`",
        "- default episode compression: `5s`",
        "",
        "Raw E0 counts by day:",
        "",
    ]
    lines.extend(markdown_table([{"date": day, **raw_counts[day]} for day in days], ["date", "raw_e0_rows", "admission_q70_bps"]))
    lines.extend(
        [
            "",
            "## Strategy Variant Summary",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            variant_summary,
            [
                "variant_id",
                "entries",
                "actual_entries",
                "total_actual_exposure",
                "mean_unit_exec60_bps",
                "weighted_bps_per_exposure",
                "median_unit_exec60_bps",
                "hit_rate",
                "net_weighted_bps",
                "positive_days",
                "days",
                "worst_day_net_weighted_bps",
            ],
        )
    )
    lines.extend(["", "## Path Classes", ""])
    lines.extend(markdown_table(path_class_summary, ["path_class", "n", "mean_executable_return_60s_bps", "hit_rate", "mean_mid60_bps", "mean_release_mfe10_bps", "mean_decay60_bps"]))
    lines.extend(["", "## Memory Buckets", ""])
    lines.extend(markdown_table(memory_summary, ["memory_bucket", "n", "mean_executable_return_60s_bps", "hit_rate", "mean_mid60_bps", "mean_release_mfe10_bps", "mean_decay60_bps"]))
    lines.extend(["", "## Cost Stress", ""])
    lines.extend(markdown_table(cost_summary, ["variant_id", "extra_roundtrip_cost_bps", "actual_entries", "net_weighted_bps_after_stress", "mean_unit_bps_after_stress", "hit_rate_after_stress"]))
    lines.extend(
        [
            "",
            "## Controls",
            "",
            "```text",
            json.dumps(controls_summary, indent=2, sort_keys=True),
            "```",
            "",
            "## Interpretation",
            "",
        ]
    )
    lines.extend(conclusion_lines(variant_summary))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    days = date_range(args.from_date, args.to_date)
    run_id = args.run_id or f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_v0_1"
    out_dir = args.out_dir or repo_root / DEFAULT_OUT_ROOT / run_id
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()

    thresholds = load_admission_thresholds(repo_root, args.admission_thresholds_json)
    episodes_by_compression: dict[int, int] = {}
    default_episodes: list[dict[str, Any]] = []
    frames_by_day: dict[str, pd.DataFrame] = {}
    raw_counts: dict[str, Any] = {}
    for compression_sec in parse_int_list(args.episode_sensitivity_sec):
        episodes, raw_counts_tmp, frames_tmp = build_episodes(
            repo_root=repo_root,
            symbol=args.symbol,
            days=days,
            thresholds=thresholds,
            compression_sec=compression_sec,
            max_rows_per_day=args.max_rows_per_day,
        )
        episodes_by_compression[compression_sec] = len(episodes)
        if compression_sec == args.default_episode_sec:
            default_episodes = episodes
            raw_counts = raw_counts_tmp
            frames_by_day = frames_tmp
    if not default_episodes:
        raise RuntimeError("default compression produced no episodes")

    labeled = attach_labels(repo_root, args.symbol, default_episodes)
    labeled = add_memory_and_thresholds(labeled)
    q50_by_day = cost_q50_by_day(repo_root, args.symbol, days, args.max_rows_per_day)
    for row in labeled:
        row["entry_cross_q50_prior_day"] = q50_by_day.get(str(row["date"]))
        row["memory_bucket"] = memory_bucket(row)

    variant_entries: list[dict[str, Any]] = []
    variant_exits: list[dict[str, Any]] = []
    variant_summary: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    for variant in ["A_fixed_small", "C_memory_sized"]:
        entries, exits = simulate_variant(
            variant,
            labeled,
            leverage_cap=float(args.leverage_cap),
            q50_by_day=q50_by_day,
        )
        variant_entries.extend(entries)
        variant_exits.extend(exits)
        variant_summary.append(summarize_variant(variant, entries, exits))
        daily_rows.extend(daily_summary(entries, exits, variant))
    old = load_old_fourcell_summary(repo_root, args.old_fourcell_run_dir)
    if old is not None:
        variant_summary.insert(1, old)

    quote_by_day = {day: QuoteFrameIndex.load(repo_root, args.symbol, day) for day in days}
    side_flip, matched = build_controls(
        frames_by_day=frames_by_day,
        episodes=labeled,
        quote_by_day=quote_by_day,
        seed=int(args.random_seed),
    )
    controls_summary = {
        "side_flip_mean_exec60_bps": mean([float(row["exec60_bps"]) for row in side_flip]),
        "side_flip_hit_rate": hit_rate([float(row["exec60_bps"]) for row in side_flip]),
        "matched_mean_exec60_bps": mean([float(row["exec60_bps"]) for row in matched]),
        "matched_hit_rate": hit_rate([float(row["exec60_bps"]) for row in matched]),
    }

    path_class_summary = group_summary(labeled, ["path_class"])
    memory_summary = group_summary(labeled, ["memory_bucket"])
    cost_summary = cost_stress(variant_entries)

    top_good = sorted(labeled, key=lambda row: float(row["executable_return_60s_bps"]), reverse=True)[:50]
    worst_bad = sorted(labeled, key=lambda row: float(row["executable_return_60s_bps"]))[:50]

    write_parquet(out_dir / "episode_entries.parquet", variant_entries)
    write_parquet(out_dir / "episode_exits.parquet", variant_exits)
    write_parquet(out_dir / "path_label_panel.parquet", labeled)
    write_parquet(out_dir / "top_good_paths.parquet", top_good)
    write_parquet(out_dir / "worst_bad_paths.parquet", worst_bad)
    write_csv(out_dir / "strategy_variant_summary.csv", variant_summary)
    write_csv(out_dir / "daily.csv", daily_rows)
    write_csv(out_dir / "path_class_summary.csv", path_class_summary)
    write_csv(out_dir / "memory_bucket_summary.csv", memory_summary)
    write_csv(out_dir / "cost_stress_summary.csv", cost_summary)
    write_csv(out_dir / "side_flip_control.csv", side_flip)
    write_csv(out_dir / "matched_time_control.csv", matched)

    write_casebook(out_dir / "path_casebook.md", top_good, worst_bad, out_dir)

    summary = {
        "schema_id": SCHEMA_ID,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "run_id": run_id,
        "out_dir": str(out_dir),
        "episode_compression_counts": episodes_by_compression,
        "default_episode_sec": args.default_episode_sec,
        "raw_counts": raw_counts,
        "strategy_variant_summary": variant_summary,
        "controls_summary": controls_summary,
        "forbidden_runtime_inputs": ["date/", "scored_entries", "future_labels", "PnL", "MFE", "MAE"],
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
    }
    write_json(out_dir / "summary.json", summary)

    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    write_report(
        report_path,
        symbol=args.symbol,
        days=days,
        raw_counts=raw_counts,
        variant_summary=variant_summary,
        path_class_summary=path_class_summary,
        memory_summary=memory_summary,
        cost_summary=cost_summary,
        controls_summary=controls_summary,
        out_dir=out_dir,
    )
    print(json.dumps({"ok": True, "out_dir": str(out_dir), "report_path": str(report_path)}, indent=2))
    return 0


def parse_int_list(raw: str) -> list[int]:
    out = sorted({int(part.strip()) for part in str(raw).split(",") if part.strip()})
    if not out:
        raise ValueError("expected at least one integer")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
