#!/usr/bin/env python
"""R5-style low-degree path-factor fast backtest for CCUSDT.

Research-only diagnostic. It imitates the old four-cell R5 workflow with new
runtime-safe path primitives:

old TFI trigger + primitive memory operator + frames cell + prior-day q70 spread
gate + fixed60 top-of-book taker label.

The script reads only decision_frame_v1 and quote_frame_v1. Future returns are
computed inside this diagnostic only and must not enter Runner/Bot runtime.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
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


BOT_DIR = Path(__file__).resolve().parents[1] / "strategies" / "python" / "ccusdt_tfi_core_idle01"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from execution_runtime import build_capacity_allocator  # noqa: E402


DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
QUOTE_FRAME_ROOT = Path("data/canonical/cex/bullish")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/r5_style_path_factor_backtest")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/strategy/v1-r5-style-path-factor-backtest-20260602.md")
DEFAULT_ADMISSION_THRESHOLDS = Path(
    "systems/ccusdt_replay_exchange/runs/admission_thresholds/entry_spread_q70_20260516_18_20260521.json"
)
DEFAULT_BASELINE = Path(
    "systems/ccusdt_replay_exchange/runs/experiments/"
    "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521"
)

SCHEMA_ID = "ccusdt_r5_style_path_factor_backtest_v0_1"
EPS = 1e-12
FIXED_EXIT_US = 60_000_000
FRAMES_THRESHOLD = 31.0
OVERLAY_THRESHOLD = 59.80000000000018

TRIGGER_ORDER = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]

BASE_WEIGHTS = {
    "tfi_follow_flat+tfi_long_flat": 0.5,
    "tfi_follow_flat+tfi_long_flat+tfi_event_active": 0.5,
    "tfi_follow_flat+tfi_short_flat": 0.5,
    "tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active": 2.0,
    "tfi_long_flat": 0.5,
}

GAMMA_CORE_IDLE01_G1 = {
    "00_none": 1.25,
    "10_r5_only": 0.75,
    "01_frames_only": 1.0,
    "11_r5_frames": 0.75,
}


@dataclass(frozen=True)
class VariantSpec:
    primitive_id: str
    metric: str
    window_sec: int
    threshold_quantile: float

    @property
    def variant_id(self) -> str:
        q = int(round(self.threshold_quantile * 100))
        return f"{self.primitive_id}_{self.metric.lower()}_w{self.window_sec}_q{q}"


@dataclass
class OpenPosition:
    row: dict[str, Any]
    due_ts_us: int


class QuoteFrameIndex:
    def __init__(self, frames: list[dict[str, Any]]) -> None:
        if not frames:
            raise ValueError("quote_frame_v1 index is empty")
        self.frames = frames
        self.local_ts_us = [int(frame["local_ts_us"]) for frame in frames]

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteFrameIndex":
        path = quote_frame_path(repo_root, symbol, day)
        frames: list[dict[str, Any]] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                bid = optional_float(row.get("bid_px"))
                ask = optional_float(row.get("ask_px"))
                mid = optional_float(row.get("mid_px"))
                local_ts_us = int(float(row.get("local_ts_us") or 0))
                if local_ts_us <= 0 or bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
                    continue
                frames.append(
                    {
                        "seq": int(float(row.get("seq") or len(frames))),
                        "exchange_ts_us": int(float(row.get("exchange_ts_us") or 0)),
                        "local_ts_us": local_ts_us,
                        "bid_px": bid,
                        "ask_px": ask,
                        "mid_px": mid if mid is not None else 0.5 * (bid + ask),
                        "spread_bps": optional_float(row.get("spread_bps")),
                    }
                )
        return cls(frames)

    def at_or_before(self, local_ts_us: int) -> dict[str, Any]:
        idx = bisect.bisect_right(self.local_ts_us, int(local_ts_us))
        if idx <= 0:
            return self.frames[0]
        return self.frames[idx - 1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--windows-sec", default="30,60")
    parser.add_argument("--threshold-quantiles", default="0.70,0.80")
    parser.add_argument("--max-rows-per-day", type=int, default=0)
    parser.add_argument("--leverage-cap", type=float, default=3.0)
    parser.add_argument("--capacity-profile", choices=["fifo_clip", "core_idle01"], default="core_idle01")
    parser.add_argument("--idle01-gamma", type=float, default=1.0)
    parser.add_argument("--idle01-reserve", type=float, default=0.0)
    parser.add_argument("--fee-bps", type=float, default=0.0)
    parser.add_argument("--pressure-bps", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--admission-thresholds-json", type=Path, default=DEFAULT_ADMISSION_THRESHOLDS)
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--progress-interval", type=int, default=50_000)
    parser.add_argument("--run-id")
    return parser.parse_args()


def parse_int_list(raw: str) -> list[int]:
    out = sorted({int(part.strip()) for part in raw.split(",") if part.strip()})
    if not out:
        raise ValueError("expected at least one window")
    return out


def parse_float_list(raw: str) -> list[float]:
    out = sorted({float(part.strip()) for part in raw.split(",") if part.strip()})
    if not out:
        raise ValueError("expected at least one quantile")
    for value in out:
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"quantile must be in (0, 1): {value}")
    return out


def date_range(start: str, end: str) -> Iterable[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while cur <= last:
        yield cur.isoformat()
        cur += timedelta(days=1)


def previous_day(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def optional_int(value: Any) -> int | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return int(out)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


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
    pq.write_table(table, path)


def decision_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def decision_manifest_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "manifest.json"


def quote_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / QUOTE_FRAME_ROOT / symbol / "quote_frame_v1" / f"dt={day}" / "part_000001.csv.gz"


def maybe_stride(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df.reset_index(drop=True)
    stride = max(1, int(math.ceil(len(df) / max_rows)))
    return df.iloc[::stride].head(max_rows).reset_index(drop=True)


def load_decision_frame(repo_root: Path, symbol: str, day: str, max_rows: int = 0) -> pd.DataFrame:
    path = decision_frame_path(repo_root, symbol, day)
    if not path.exists():
        raise FileNotFoundError(path)
    schema = pq.read_schema(path)
    want = [
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
        "trade_buy_amount",
        "trade_sell_amount",
        "trade_notional_quote",
        "trade_flow_imbalance",
        "mid_change_prev",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]
    table = pq.read_table(path, columns=[col for col in want if col in schema.names])
    df = table.to_pandas()
    if "factor_eligible" in df.columns:
        df = df[df["factor_eligible"].fillna(False)].copy()
    if "local_ts_us" not in df.columns and "local_timestamp" in df.columns:
        df["local_ts_us"] = df["local_timestamp"]
    if "mid" not in df.columns and "mid_price" in df.columns:
        df["mid"] = df["mid_price"]
    for src, dst in [
        ("best_bid_price", "bid"),
        ("best_ask_price", "ask"),
        ("best_bid_amount", "bid_amount"),
        ("best_ask_amount", "ask_amount"),
    ]:
        if src in df.columns:
            df[dst] = df[src]
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
        "trade_buy_amount",
        "trade_sell_amount",
        "trade_notional_quote",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["local_ts_us"] = df["local_ts_us"].astype("int64")
    df["date"] = day
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["local_ts_us", "bid", "ask", "mid"])
    df = df[(df["bid"] > 0.0) & (df["ask"] > 0.0) & (df["mid"] > 0.0)]
    df = df.sort_values("local_ts_us").drop_duplicates("local_ts_us", keep="last").reset_index(drop=True)
    return maybe_stride(df, max_rows)


def load_admission_thresholds(repo_root: Path, path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    resolved = path if path.is_absolute() else repo_root / path
    raw = read_json(resolved)
    rows = raw.get("thresholds", raw)
    if not isinstance(rows, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for day, row in rows.items():
        if isinstance(row, dict):
            threshold = optional_float(row.get("entry_cross_threshold_bps"))
            source = row.get("threshold_source")
        else:
            threshold = optional_float(row)
            source = str(resolved)
        if threshold is not None:
            out[str(day)] = {
                "entry_cross_threshold_bps": threshold,
                "threshold_source": source or str(resolved),
            }
    return out


def spread_threshold_for_day(
    repo_root: Path,
    symbol: str,
    day: str,
    loaded: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if day in loaded:
        return loaded[day]
    prior = previous_day(day)
    df = load_decision_frame(repo_root, symbol, prior)
    cross = 0.5 * pd.to_numeric(df["spread_bps"], errors="coerce").dropna()
    threshold = float(cross.quantile(0.70))
    return {
        "entry_cross_threshold_bps": threshold,
        "threshold_source": f"computed_prior_day_decision_frame_spread_cross_q0.70:{prior}",
    }


def trigger_for_row(row: pd.Series) -> tuple[int, list[str], str, float] | None:
    tfi = optional_float(row.get("trade_flow_imbalance"))
    if tfi is None:
        return None
    high = tfi >= 1.0 - 1e-12
    low = tfi <= -1.0 + 1e-12
    if not high and not low:
        return None
    direction = 1 if high else -1
    trade_count = optional_float(row.get("trade_window_count")) or 0.0
    frames = optional_float(row.get("frames_since_mid_change"))
    past25 = optional_float(row.get("past_event_25_bps"))
    flat = past25 is not None and abs(past25) <= 0.5
    stale25 = frames is not None and frames >= 25.0
    active: dict[str, int] = {}
    if flat:
        active["tfi_follow_flat"] = direction
        if low:
            active["tfi_short_flat"] = -1
        if high:
            active["tfi_long_flat"] = 1
    if low and stale25:
        active["tfi_short_stale25"] = -1
    if trade_count > 0 and stale25:
        active["tfi_event_active"] = direction
    selected = [name for name in TRIGGER_ORDER if name in active and active[name] == direction]
    membership = "+".join(selected)
    base_weight = BASE_WEIGHTS.get(membership, 0.0)
    if base_weight <= 0.0:
        return None
    return direction, selected, membership, base_weight


def add_trigger_columns(df: pd.DataFrame) -> pd.DataFrame:
    directions: list[int] = []
    memberships: list[str] = []
    selecteds: list[str] = []
    weights: list[float] = []
    trigger_ok: list[bool] = []
    for _, row in df.iterrows():
        trig = trigger_for_row(row)
        if trig is None:
            directions.append(0)
            memberships.append("")
            selecteds.append("")
            weights.append(0.0)
            trigger_ok.append(False)
            continue
        direction, selected, membership, base_weight = trig
        directions.append(direction)
        memberships.append(membership)
        selecteds.append("+".join(selected))
        weights.append(base_weight)
        trigger_ok.append(True)
    out = df.copy()
    out["trigger_ok"] = trigger_ok
    out["direction"] = directions
    out["membership_set"] = memberships
    out["trigger_classes"] = selecteds
    out["base_weight"] = weights
    return out


def rolling_sum(ts_us: np.ndarray, values: np.ndarray, window_sec: int) -> np.ndarray:
    window_us = int(window_sec * 1_000_000)
    values = np.nan_to_num(values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    csum = np.concatenate([[0.0], np.cumsum(values)])
    starts = np.searchsorted(ts_us, ts_us - window_us, side="left")
    ends = np.arange(len(values)) + 1
    return csum[ends] - csum[starts]


def safe_log_change(values: np.ndarray) -> np.ndarray:
    values = np.nan_to_num(values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    prev = np.roll(values, 1)
    prev[0] = values[0]
    valid = (values > 0.0) & (prev > 0.0)
    out = np.zeros(len(values), dtype=float)
    out[valid] = np.log(values[valid] / prev[valid])
    return np.clip(out, -10.0, 10.0)


def primitive_series(df: pd.DataFrame, side: int, primitive_id: str) -> np.ndarray:
    tfi = pd.to_numeric(df["trade_flow_imbalance"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    mid = pd.to_numeric(df["mid"], errors="coerce").to_numpy(dtype=float)
    spread = pd.to_numeric(df["spread_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bid_amount = pd.to_numeric(df["bid_amount"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    ask_amount = pd.to_numeric(df["ask_amount"], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    mid_prev = np.roll(mid, 1)
    mid_prev[0] = mid[0]
    d_mid_bps = np.zeros(len(mid), dtype=float)
    valid_mid = (mid > 0.0) & (mid_prev > 0.0)
    d_mid_bps[valid_mid] = 10_000.0 * np.log(mid[valid_mid] / mid_prev[valid_mid])
    aligned_tfi = side * tfi

    if primitive_id in {"flow_pressure_memory", "absolute_pressure_energy"}:
        return aligned_tfi

    if primitive_id == "pressure_without_price_response":
        response_penalty = np.exp(-np.abs(d_mid_bps) / (np.maximum(spread, 0.05) + EPS))
        return np.maximum(aligned_tfi, 0.0) * response_penalty - np.maximum(-aligned_tfi, 0.0)

    if primitive_id == "liquidity_giveway_memory":
        opposite = ask_amount if side > 0 else bid_amount
        return -10_000.0 * safe_log_change(opposite)

    if primitive_id == "cost_allowed_release_memory":
        half_spread = np.maximum(0.5 * spread, 0.05)
        return side * d_mid_bps / (half_spread + EPS)

    raise ValueError(f"unknown primitive_id={primitive_id}")


def add_variant_scores(df: pd.DataFrame, specs: list[VariantSpec]) -> pd.DataFrame:
    out = df.copy()
    ts_us = out["local_ts_us"].to_numpy(dtype=np.int64)
    by_key: dict[tuple[str, int], list[VariantSpec]] = {}
    for spec in specs:
        by_key.setdefault((spec.primitive_id, spec.window_sec), []).append(spec)

    for primitive_id, window_sec in by_key:
        values_by_metric: dict[int, dict[str, np.ndarray]] = {}
        for side in (1, -1):
            h = primitive_series(out, side, primitive_id)
            pos = rolling_sum(ts_us, np.maximum(h, 0.0), window_sec)
            neg = rolling_sum(ts_us, np.maximum(-h, 0.0), window_sec)
            energy = pos + neg
            values_by_metric[side] = {
                "R": pos / (neg + EPS),
                "E": energy,
                "Z": (pos - neg) / np.sqrt(energy + EPS),
            }
        direction = out["direction"].fillna(0).astype(int).to_numpy()
        for metric in sorted({spec.metric for spec in by_key[(primitive_id, window_sec)]}):
            score = np.full(len(out), np.nan, dtype=float)
            for side in (1, -1):
                mask = direction == side
                score[mask] = values_by_metric[side][metric][mask]
            col = f"{primitive_id}_{metric.lower()}_w{window_sec}"
            out[col] = score
    return out


def build_variant_specs(windows_sec: list[int], quantiles: list[float]) -> list[VariantSpec]:
    primitive_metrics = {
        "flow_pressure_memory": ["R", "Z"],
        "absolute_pressure_energy": ["E"],
        "pressure_without_price_response": ["R", "Z"],
        "liquidity_giveway_memory": ["R", "Z"],
        "cost_allowed_release_memory": ["R", "Z"],
    }
    specs: list[VariantSpec] = []
    for primitive_id, metrics in primitive_metrics.items():
        for metric in metrics:
            for window_sec in windows_sec:
                for q in quantiles:
                    specs.append(VariantSpec(primitive_id, metric, window_sec, q))
    return specs


def score_column(spec: VariantSpec) -> str:
    return f"{spec.primitive_id}_{spec.metric.lower()}_w{spec.window_sec}"


def threshold_for_spec(df: pd.DataFrame, spec: VariantSpec) -> dict[str, Any]:
    col = score_column(spec)
    sample = pd.to_numeric(df.loc[df["trigger_ok"], col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    sample = sample[sample > -1e30]
    if len(sample) == 0:
        return {"threshold": math.nan, "sample_count": 0}
    return {
        "threshold": float(sample.quantile(spec.threshold_quantile)),
        "sample_count": int(len(sample)),
    }


def make_cell(memory_ok: bool, frames_ok: bool) -> str:
    if memory_ok and frames_ok:
        return "11_r5_frames"
    if memory_ok:
        return "10_r5_only"
    if frames_ok:
        return "01_frames_only"
    return "00_none"


def taker_bps(direction: int, entry_bid: float, entry_ask: float, exit_bid: float, exit_ask: float) -> float:
    if direction > 0:
        return 10_000.0 * math.log(exit_bid / entry_ask)
    return 10_000.0 * math.log(entry_bid / exit_ask)


def mid_bps(direction: int, entry_mid: float, exit_mid: float) -> float:
    return direction * 10_000.0 * math.log(exit_mid / entry_mid)


def close_due_positions(
    *,
    variant_id: str,
    now_ts_us: int,
    quote_index: QuoteFrameIndex,
    capacity: Any,
    open_positions: list[OpenPosition],
    exits: list[dict[str, Any]],
    daily_acc: dict[tuple[str, str], dict[str, Any]],
    cost_bps: float,
    force_all: bool = False,
) -> list[OpenPosition]:
    remaining: list[OpenPosition] = []
    for position in open_positions:
        if not force_all and position.due_ts_us > now_ts_us:
            remaining.append(position)
            continue
        entry = position.row
        exit_quote = quote_index.at_or_before(position.due_ts_us if not force_all else now_ts_us)
        capacity.close(int(entry["shadow_position_id"]))
        actual = float(entry["actual_exposure"])
        direction = int(entry["direction"])
        entry_bid = float(entry["entry_bid"])
        entry_ask = float(entry["entry_ask"])
        entry_mid = float(entry["entry_mid"])
        exit_bid = float(exit_quote["bid_px"])
        exit_ask = float(exit_quote["ask_px"])
        exit_mid = float(exit_quote["mid_px"])
        raw_exec = taker_bps(direction, entry_bid, entry_ask, exit_bid, exit_ask)
        raw_mid = mid_bps(direction, entry_mid, exit_mid)
        net = raw_exec - cost_bps
        gross_weighted = actual * raw_exec
        net_weighted = actual * net
        mid_weighted = actual * raw_mid
        row = {
            **{key: entry.get(key) for key in [
                "variant_id",
                "primitive_id",
                "metric",
                "window_sec",
                "threshold_quantile",
                "threshold",
                "date",
                "shadow_position_id",
                "entry_seq",
                "entry_ts_us",
                "side",
                "direction",
                "cell",
                "membership_set",
                "trigger_classes",
                "base_weight",
                "weak_overlay_weight",
                "gamma",
                "requested_exposure",
                "actual_exposure",
                "clipped_exposure",
                "capacity_profile",
                "capacity_source",
                "entry_spread_bps",
                "entry_cross_bps",
                "score_value",
                "frames_since_mid_change",
            ]},
            "exit_ts_us": int(exit_quote["local_ts_us"]),
            "due_ts_us": int(position.due_ts_us),
            "held_us": int(exit_quote["local_ts_us"]) - int(entry["entry_ts_us"]),
            "exit_reason": "forced_last_quote" if force_all and int(exit_quote["local_ts_us"]) < position.due_ts_us else "fixed60_taker",
            "entry_bid": entry_bid,
            "entry_ask": entry_ask,
            "entry_mid": entry_mid,
            "exit_bid": exit_bid,
            "exit_ask": exit_ask,
            "exit_mid": exit_mid,
            "raw_bps_mid_fixed60": raw_mid,
            "raw_bps": raw_exec,
            "fee_bps": entry["fee_bps"],
            "pressure_bps": entry["pressure_bps"],
            "slippage_bps": entry["slippage_bps"],
            "cost_bps": cost_bps,
            "net_bps_after_cost": net,
            "gross_weighted_bps": gross_weighted,
            "net_weighted_bps": net_weighted,
            "mid_weighted_bps": mid_weighted,
            "mid_minus_executable_bps": raw_mid - raw_exec,
        }
        exits.append(row)
        acc = daily_acc.setdefault((variant_id, str(entry["date"])), new_accumulator(variant_id, str(entry["date"])))
        acc["exits"] += 1
        acc["gross_weighted_bps"] += gross_weighted
        acc["net_weighted_bps"] += net_weighted
        acc["mid_weighted_bps"] += mid_weighted
        if actual > 0.0:
            acc["worst_actual_leg_net_bps"] = min(acc["worst_actual_leg_net_bps"], net_weighted)
            acc["worst_unit_net_bps"] = min(acc["worst_unit_net_bps"], net)
    return remaining


def new_accumulator(variant_id: str, day: str | None = None, cell: str | None = None) -> dict[str, Any]:
    return {
        "variant_id": variant_id,
        "date": day,
        "cell": cell,
        "entries": 0,
        "actual_entries": 0,
        "admission_accepted_entries": 0,
        "admission_rejected_entries": 0,
        "skipped_entries": 0,
        "clipped_entries": 0,
        "exits": 0,
        "requested_exposure": 0.0,
        "actual_exposure": 0.0,
        "gross_weighted_bps": 0.0,
        "net_weighted_bps": 0.0,
        "mid_weighted_bps": 0.0,
        "worst_actual_leg_net_bps": 0.0,
        "worst_unit_net_bps": 0.0,
    }


def update_entry_acc(acc: dict[str, Any], row: dict[str, Any]) -> None:
    actual = float(row["actual_exposure"])
    requested = float(row["requested_exposure"])
    acc["entries"] += 1
    acc["requested_exposure"] += requested
    acc["actual_exposure"] += actual
    acc["actual_entries"] += 1 if actual > EPS else 0
    acc["admission_accepted_entries"] += 1 if row["admission_accepted"] else 0
    acc["admission_rejected_entries"] += 0 if row["admission_accepted"] else 1
    acc["skipped_entries"] += 1 if row["skipped"] else 0
    acc["clipped_entries"] += 1 if float(row["clipped_exposure"]) > EPS else 0


def finalize_accumulators(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        actual = float(row.get("actual_exposure") or 0.0)
        exits = int(row.get("exits") or 0)
        net = float(row.get("net_weighted_bps") or 0.0)
        gross = float(row.get("gross_weighted_bps") or 0.0)
        mid = float(row.get("mid_weighted_bps") or 0.0)
        row = dict(row)
        row["mean_unit_net_bps"] = net / actual if actual > EPS else math.nan
        row["mean_unit_raw_bps"] = gross / actual if actual > EPS else math.nan
        row["mean_unit_mid_bps"] = mid / actual if actual > EPS else math.nan
        row["mid_minus_executable_weighted_bps"] = (mid - gross) / actual if actual > EPS else math.nan
        row["avg_actual_exposure_per_exit"] = actual / exits if exits else math.nan
        out.append(row)
    return out


def make_daily_rows(daily_acc: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    return finalize_accumulators(daily_acc.values())


def summarize_variants(
    specs: list[VariantSpec],
    entries: list[dict[str, Any]],
    exits: list[dict[str, Any]],
    daily_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entry_df = pd.DataFrame(entries)
    exit_df = pd.DataFrame(exits)
    daily_df = pd.DataFrame(daily_rows)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        vid = spec.variant_id
        e = entry_df[entry_df["variant_id"] == vid] if not entry_df.empty else pd.DataFrame()
        x = exit_df[exit_df["variant_id"] == vid] if not exit_df.empty else pd.DataFrame()
        d = daily_df[daily_df["variant_id"] == vid] if not daily_df.empty else pd.DataFrame()
        actual_exposure = float(e["actual_exposure"].sum()) if not e.empty else 0.0
        gross = float(x["gross_weighted_bps"].sum()) if not x.empty else 0.0
        net = float(x["net_weighted_bps"].sum()) if not x.empty else 0.0
        mid = float(x["mid_weighted_bps"].sum()) if not x.empty else 0.0
        positive_days = int((d["net_weighted_bps"] > 0.0).sum()) if not d.empty else 0
        days = int(d["date"].nunique()) if not d.empty else 0
        row = {
            "variant_id": vid,
            "primitive_id": spec.primitive_id,
            "metric": spec.metric,
            "window_sec": spec.window_sec,
            "threshold_quantile": spec.threshold_quantile,
            "entries": int(len(e)),
            "actual_entries": int((e["actual_exposure"] > EPS).sum()) if not e.empty else 0,
            "admission_accepted_entries": int(e["admission_accepted"].sum()) if not e.empty else 0,
            "admission_rejected_entries": int((~e["admission_accepted"].astype(bool)).sum()) if not e.empty else 0,
            "skipped_entries": int(e["skipped"].sum()) if not e.empty else 0,
            "clipped_entries": int((e["clipped_exposure"] > EPS).sum()) if not e.empty else 0,
            "exits": int(len(x)),
            "actual_exposure": actual_exposure,
            "gross_weighted_bps": gross,
            "net_weighted_bps": net,
            "mid_weighted_bps": mid,
            "mean_unit_net_bps": net / actual_exposure if actual_exposure > EPS else math.nan,
            "mean_unit_raw_bps": gross / actual_exposure if actual_exposure > EPS else math.nan,
            "mean_unit_mid_bps": mid / actual_exposure if actual_exposure > EPS else math.nan,
            "mid_minus_executable_weighted_bps": (mid - gross) / actual_exposure if actual_exposure > EPS else math.nan,
            "median_unit_net_bps": float(x["net_bps_after_cost"].median()) if not x.empty else math.nan,
            "hit_rate": float((x["net_bps_after_cost"] > 0.0).mean()) if not x.empty else math.nan,
            "positive_days": positive_days,
            "days": days,
            "daily_sign_rate": positive_days / days if days else math.nan,
            "worst_day_net_weighted_bps": float(d["net_weighted_bps"].min()) if not d.empty else math.nan,
            "worst_actual_leg_net_bps": float(x["net_weighted_bps"].min()) if not x.empty else math.nan,
            "spread_cost_mirage": bool(mid > 0.0 and net <= 0.0),
            "status": status_for_variant(net, actual_exposure, positive_days, days, mid, gross),
        }
        rows.append(row)
    return rows


def summarize_cells(entries: list[dict[str, Any]], exits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return []
    entry_df = pd.DataFrame(entries)
    exit_df = pd.DataFrame(exits)
    rows: list[dict[str, Any]] = []
    for (vid, cell), e in entry_df.groupby(["variant_id", "cell"], sort=True):
        x = exit_df[(exit_df["variant_id"] == vid) & (exit_df["cell"] == cell)] if not exit_df.empty else pd.DataFrame()
        actual = float(e["actual_exposure"].sum())
        gross = float(x["gross_weighted_bps"].sum()) if not x.empty else 0.0
        net = float(x["net_weighted_bps"].sum()) if not x.empty else 0.0
        mid = float(x["mid_weighted_bps"].sum()) if not x.empty else 0.0
        rows.append(
            {
                "variant_id": vid,
                "cell": cell,
                "entries": int(len(e)),
                "actual_entries": int((e["actual_exposure"] > EPS).sum()),
                "exits": int(len(x)),
                "actual_exposure": actual,
                "net_weighted_bps": net,
                "gross_weighted_bps": gross,
                "mid_weighted_bps": mid,
                "mean_unit_net_bps": net / actual if actual > EPS else math.nan,
                "mean_unit_raw_bps": gross / actual if actual > EPS else math.nan,
                "mean_unit_mid_bps": mid / actual if actual > EPS else math.nan,
                "median_unit_net_bps": float(x["net_bps_after_cost"].median()) if not x.empty else math.nan,
                "hit_rate": float((x["net_bps_after_cost"] > 0.0).mean()) if not x.empty else math.nan,
            }
        )
    return rows


def status_for_variant(net: float, actual: float, positive_days: int, days: int, mid: float, gross: float) -> str:
    if actual <= EPS:
        return "no_actual_exposure"
    if mid > 0.0 and net <= 0.0:
        return "spread_cost_mirage"
    if net > 0.0 and days > 0 and positive_days == days:
        return "diagnostic_positive_all_days"
    if net > 0.0 and positive_days > 0:
        return "diagnostic_positive_unstable"
    if gross > 0.0 and net <= 0.0:
        return "execution_cost_reject"
    return "weak_or_negative"


def load_baseline(path: Path) -> dict[str, Any]:
    summary = read_json(path / "summary.json")
    if not summary:
        return {}
    return {
        "baseline_run_id": summary.get("run_id"),
        "baseline_actual_entries": summary.get("actual_entries"),
        "baseline_net_weighted_bps": summary.get("net_weighted_bps"),
        "baseline_positive_days": summary.get("positive_days"),
        "baseline_days": summary.get("days"),
        "baseline_worst_day_net_weighted_bps": summary.get("worst_day_net_weighted_bps"),
    }


def comparison_rows(variant_rows: list[dict[str, Any]], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    base_net = optional_float(baseline.get("baseline_net_weighted_bps"))
    base_entries = optional_float(baseline.get("baseline_actual_entries"))
    base_worst = optional_float(baseline.get("baseline_worst_day_net_weighted_bps"))
    rows: list[dict[str, Any]] = []
    for row in variant_rows:
        net = optional_float(row.get("net_weighted_bps"))
        entries = optional_float(row.get("actual_entries"))
        worst = optional_float(row.get("worst_day_net_weighted_bps"))
        rows.append(
            {
                "variant_id": row["variant_id"],
                "primitive_id": row["primitive_id"],
                "metric": row["metric"],
                "window_sec": row["window_sec"],
                "threshold_quantile": row["threshold_quantile"],
                "actual_entries": row["actual_entries"],
                "net_weighted_bps": row["net_weighted_bps"],
                "mean_unit_net_bps": row["mean_unit_net_bps"],
                "positive_days": row["positive_days"],
                "days": row["days"],
                "worst_day_net_weighted_bps": row["worst_day_net_weighted_bps"],
                "baseline_run_id": baseline.get("baseline_run_id"),
                "baseline_actual_entries": baseline.get("baseline_actual_entries"),
                "baseline_net_weighted_bps": baseline.get("baseline_net_weighted_bps"),
                "delta_net_weighted_bps": (net - base_net) if net is not None and base_net is not None else math.nan,
                "delta_actual_entries": (entries - base_entries) if entries is not None and base_entries is not None else math.nan,
                "delta_worst_day_net_weighted_bps": (worst - base_worst) if worst is not None and base_worst is not None else math.nan,
                "beats_baseline_net": bool(net is not None and base_net is not None and net > base_net),
                "status": row["status"],
            }
        )
    return rows


def markdown_table(rows: list[dict[str, Any]], columns: list[str], limit: int = 20) -> str:
    shown = rows[:limit]
    if not shown:
        return "_No rows._"
    lines = ["|" + "|".join(columns) + "|", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in shown:
        vals = []
        for col in columns:
            value = row.get(col)
            if isinstance(value, float):
                vals.append("" if math.isnan(value) else f"{value:.4f}")
            else:
                vals.append(str(value))
        lines.append("|" + "|".join(vals) + "|")
    return "\n".join(lines)


def write_report(
    path: Path,
    summary: dict[str, Any],
    variant_rows: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]],
    comparison: list[dict[str, Any]],
) -> None:
    top = sorted(variant_rows, key=lambda row: float(row.get("net_weighted_bps") or -1e18), reverse=True)
    top_cells = sorted(cell_rows, key=lambda row: float(row.get("net_weighted_bps") or -1e18), reverse=True)
    memory_cells = sorted(
        [row for row in cell_rows if row.get("cell") in {"10_r5_only", "11_r5_frames"}],
        key=lambda row: float(row.get("net_weighted_bps") or -1e18),
        reverse=True,
    )
    status_counts: dict[str, int] = {}
    for row in variant_rows:
        status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1
    status_rows = [{"status": key, "variants": value} for key, value in sorted(status_counts.items())]

    lines = [
        "# CCUSDT R5-style path factor fast backtest",
        "",
        f"Status: `{summary['schema_id']}`.",
        "",
        "Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.",
        "",
        "## Setup",
        "",
        f"- symbol: `{summary['symbol']}`",
        f"- dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- windows_sec: `{summary['windows_sec']}`",
        f"- threshold_quantiles: `{summary['threshold_quantiles']}`",
        f"- variants: `{summary['variant_count']}`",
        f"- baseline: `{summary.get('baseline', {}).get('baseline_run_id')}`",
        "",
        "## Status counts",
        "",
        markdown_table(status_rows, ["status", "variants"], 20),
        "",
        "## Top variants by net weighted bps",
        "",
        markdown_table(
            top,
            [
                "variant_id",
                "actual_entries",
                "net_weighted_bps",
                "mean_unit_net_bps",
                "positive_days",
                "days",
                "worst_day_net_weighted_bps",
                "status",
            ],
            15,
        ),
        "",
        "## Best cells",
        "",
        markdown_table(
            top_cells,
            ["variant_id", "cell", "actual_entries", "net_weighted_bps", "mean_unit_net_bps", "hit_rate"],
            20,
        ),
        "",
        "## Best memory cells",
        "",
        "These rows isolate the cells where the new primitive threshold is active. They are closer to the R5 imitation question than `01_frames_only`.",
        "",
        markdown_table(
            memory_cells,
            ["variant_id", "cell", "actual_entries", "net_weighted_bps", "mean_unit_net_bps", "hit_rate"],
            20,
        ),
        "",
        "## Comparison vs old q70/R5 baseline",
        "",
        markdown_table(
            sorted(comparison, key=lambda row: float(row.get("delta_net_weighted_bps") or -1e18), reverse=True),
            [
                "variant_id",
                "actual_entries",
                "net_weighted_bps",
                "baseline_net_weighted_bps",
                "delta_net_weighted_bps",
                "beats_baseline_net",
                "status",
            ],
            15,
        ),
        "",
        "## Interpretation guardrails",
        "",
        "- A positive row is not strategy promotion. It means the low-degree primitive deserves a second pass.",
        "- A `spread_cost_mirage` row means the mid path looked useful but top-of-book taker economics rejected it.",
        "- Thresholds are prior-day candidate-distribution quantiles; they are not fitted on same-day labels.",
        "- Runner, Bot, Monitor, scored entries, and legacy `date/` files are not inputs.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    start = time.perf_counter()
    args = parse_args()
    repo_root = args.repo_root.resolve()
    windows_sec = parse_int_list(args.windows_sec)
    quantiles = parse_float_list(args.threshold_quantiles)
    specs = build_variant_specs(windows_sec, quantiles)
    days = list(date_range(args.from_date, args.to_date))
    run_id = args.run_id or f"ccusdt_{args.from_date}_{args.to_date}_v0_1"
    out_dir = (args.out_dir if args.out_dir else DEFAULT_OUT_ROOT / run_id)
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path

    threshold_json = args.admission_thresholds_json
    admission_thresholds = load_admission_thresholds(repo_root, threshold_json)
    baseline_dir = args.baseline_run_dir if args.baseline_run_dir.is_absolute() else repo_root / args.baseline_run_dir
    baseline = load_baseline(baseline_dir)
    cost_bps = float(args.fee_bps + args.pressure_bps + args.slippage_bps)

    entries: list[dict[str, Any]] = []
    exits: list[dict[str, Any]] = []
    daily_acc: dict[tuple[str, str], dict[str, Any]] = {}
    data_manifests: list[dict[str, Any]] = []
    variant_thresholds: dict[tuple[str, str], dict[str, Any]] = {}

    for day in days:
        prior = previous_day(day)
        prior_df = add_trigger_columns(load_decision_frame(repo_root, args.symbol, prior, args.max_rows_per_day))
        prior_df = add_variant_scores(prior_df, specs)
        day_thresholds: dict[str, dict[str, Any]] = {}
        for spec in specs:
            info = threshold_for_spec(prior_df, spec)
            info.update(
                {
                    "threshold_source": f"prior_day_trigger_candidates:{prior}",
                    "threshold_quantile": spec.threshold_quantile,
                }
            )
            day_thresholds[spec.variant_id] = info
            variant_thresholds[(day, spec.variant_id)] = info

        spread_threshold = spread_threshold_for_day(repo_root, args.symbol, day, admission_thresholds)
        quote_index = QuoteFrameIndex.load(repo_root, args.symbol, day)
        df = add_trigger_columns(load_decision_frame(repo_root, args.symbol, day, args.max_rows_per_day))
        df = add_variant_scores(df, specs)
        data_manifests.append(
            {
                "date": day,
                "decision_manifest_path": str(decision_manifest_path(repo_root, args.symbol, day)),
                **read_json(decision_manifest_path(repo_root, args.symbol, day)),
                "quote_frame_path": str(quote_frame_path(repo_root, args.symbol, day)),
                "rows_loaded": int(len(df)),
                "prior_threshold_day": prior,
                "spread_threshold": spread_threshold,
            }
        )

        capacities = {
            spec.variant_id: build_capacity_allocator(
                capacity_profile=args.capacity_profile,
                leverage_cap=args.leverage_cap,
                idle01_gamma=args.idle01_gamma,
                idle01_reserve=args.idle01_reserve,
            )
            for spec in specs
        }
        open_by_variant: dict[str, list[OpenPosition]] = {spec.variant_id: [] for spec in specs}
        position_id = 1

        for idx, row in df.iterrows():
            local_ts_us = int(row["local_ts_us"])
            if args.progress_interval > 0 and idx > 0 and idx % args.progress_interval == 0:
                print(f"r5-style day={day} rows={idx} entries={len(entries)}", file=sys.stderr, flush=True)
            for spec in specs:
                vid = spec.variant_id
                open_by_variant[vid] = close_due_positions(
                    variant_id=vid,
                    now_ts_us=local_ts_us,
                    quote_index=quote_index,
                    capacity=capacities[vid],
                    open_positions=open_by_variant[vid],
                    exits=exits,
                    daily_acc=daily_acc,
                    cost_bps=cost_bps,
                )

            if not bool(row["trigger_ok"]):
                continue

            direction = int(row["direction"])
            side = "buy" if direction > 0 else "sell"
            frames = optional_float(row.get("frames_since_mid_change")) or 0.0
            frames_ok = frames >= FRAMES_THRESHOLD
            entry_spread = optional_float(row.get("spread_bps"))
            if entry_spread is None or entry_spread < 0.0:
                entry_cross = math.nan
                admission_ok = False
            else:
                entry_cross = 0.5 * entry_spread
                admission_ok = entry_cross <= float(spread_threshold["entry_cross_threshold_bps"])

            for spec in specs:
                vid = spec.variant_id
                threshold_info = day_thresholds[vid]
                threshold = optional_float(threshold_info.get("threshold"))
                score = optional_float(row.get(score_column(spec)))
                memory_ok = bool(score is not None and threshold is not None and score >= threshold)
                cell = make_cell(memory_ok, frames_ok)
                gamma = GAMMA_CORE_IDLE01_G1[cell]
                overlay_boost = 0.5 if frames >= OVERLAY_THRESHOLD else 0.0
                weak_overlay_weight = float(row["base_weight"]) + overlay_boost
                target_exposure = weak_overlay_weight * gamma
                signal = {
                    "shadow_position_id": position_id,
                    "target_exposure": target_exposure,
                    "weak_overlay_weight": weak_overlay_weight,
                    "cell": cell,
                }
                position_id += 1
                if admission_ok:
                    decision = capacities[vid].decide(signal).to_dict()
                else:
                    decision = capacities[vid].reject_decision(signal, capacity_source="admission_reject").to_dict()
                actual = float(decision["actual_exposure"])
                entry_quote = quote_index.at_or_before(local_ts_us)
                entry_row = {
                    "schema_id": "ccusdt_r5_style_path_factor_entry_v1",
                    "variant_id": vid,
                    "primitive_id": spec.primitive_id,
                    "metric": spec.metric,
                    "window_sec": spec.window_sec,
                    "threshold_quantile": spec.threshold_quantile,
                    "threshold": threshold,
                    "threshold_source": threshold_info.get("threshold_source"),
                    "threshold_sample_count": threshold_info.get("sample_count"),
                    "date": day,
                    "shadow_position_id": int(decision["shadow_position_id"]),
                    "entry_seq": optional_int(row.get("observed_seq"))
                    or optional_int(row.get("event_index"))
                    or int(idx),
                    "entry_ts_us": local_ts_us,
                    "due_ts_us": local_ts_us + FIXED_EXIT_US,
                    "side": side,
                    "direction": direction,
                    "cell": cell,
                    "memory_ok": memory_ok,
                    "frames_ok": frames_ok,
                    "membership_set": row["membership_set"],
                    "trigger_classes": row["trigger_classes"],
                    "base_weight": float(row["base_weight"]),
                    "overlay_boost": overlay_boost,
                    "weak_overlay_weight": weak_overlay_weight,
                    "gamma": gamma,
                    "score_value": score,
                    "frames_since_mid_change": frames,
                    "past_event_25_bps": optional_float(row.get("past_event_25_bps")),
                    "trade_flow_imbalance": optional_float(row.get("trade_flow_imbalance")),
                    "trade_window_count": optional_float(row.get("trade_window_count")),
                    "entry_spread_bps": entry_spread,
                    "entry_cross_bps": entry_cross,
                    "admission_profile": "entry_spread_q70_v1",
                    "admission_accepted": admission_ok,
                    "admission_reason": "accepted" if admission_ok else "entry_cross_above_q70_or_missing",
                    "admission_entry_cross_threshold_bps": spread_threshold["entry_cross_threshold_bps"],
                    "admission_threshold_source": spread_threshold["threshold_source"],
                    "requested_exposure": float(decision["requested_exposure"]),
                    "actual_exposure": actual,
                    "clipped_exposure": float(decision["clipped_exposure"]),
                    "skipped": bool(decision["skipped"]),
                    "open_exposure_before": float(decision["open_exposure_before"]),
                    "open_exposure_after": float(decision["open_exposure_after"]),
                    "capacity_profile": decision["capacity_profile"],
                    "capacity_source": decision["capacity_source"],
                    "idle_capacity_before": decision.get("idle_capacity_before"),
                    "entry_bid": float(entry_quote["bid_px"]),
                    "entry_ask": float(entry_quote["ask_px"]),
                    "entry_mid": float(entry_quote["mid_px"]),
                    "fee_bps": args.fee_bps,
                    "pressure_bps": args.pressure_bps,
                    "slippage_bps": args.slippage_bps,
                }
                entries.append(entry_row)
                acc = daily_acc.setdefault((vid, day), new_accumulator(vid, day))
                update_entry_acc(acc, entry_row)
                if actual > EPS:
                    open_by_variant[vid].append(OpenPosition(entry_row, local_ts_us + FIXED_EXIT_US))

        last_ts_us = int(quote_index.local_ts_us[-1])
        for spec in specs:
            vid = spec.variant_id
            open_by_variant[vid] = close_due_positions(
                variant_id=vid,
                now_ts_us=last_ts_us,
                quote_index=quote_index,
                capacity=capacities[vid],
                open_positions=open_by_variant[vid],
                exits=exits,
                daily_acc=daily_acc,
                cost_bps=cost_bps,
                force_all=True,
            )

    daily_rows = make_daily_rows(daily_acc)
    variant_rows = summarize_variants(specs, entries, exits, daily_rows)
    cell_rows = summarize_cells(entries, exits)
    comparison = comparison_rows(variant_rows, baseline)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(out_dir / "entries.parquet", entries)
    write_parquet(out_dir / "exits.parquet", exits)
    write_csv(out_dir / "daily.csv", daily_rows)
    write_csv(out_dir / "variant_summary.csv", variant_rows)
    write_csv(out_dir / "cell_summary.csv", cell_rows)
    write_csv(out_dir / "comparison_vs_old_q70.csv", comparison)

    summary = {
        "schema_id": SCHEMA_ID,
        "ok": True,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "run_id": run_id,
        "out_dir": str(out_dir),
        "windows_sec": windows_sec,
        "threshold_quantiles": quantiles,
        "variant_count": len(specs),
        "entries": len(entries),
        "exits": len(exits),
        "actual_entries": sum(1 for row in entries if float(row["actual_exposure"]) > EPS),
        "actual_exposure": sum(float(row["actual_exposure"]) for row in entries),
        "net_weighted_bps": sum(float(row["net_weighted_bps"]) for row in exits),
        "gross_weighted_bps": sum(float(row["gross_weighted_bps"]) for row in exits),
        "mid_weighted_bps": sum(float(row["mid_weighted_bps"]) for row in exits),
        "baseline": baseline,
        "boundary": "research-only; inputs decision_frame_v1 and quote_frame_v1; no date/scored entries/PnL/MFE/MAE runtime inputs",
        "data_manifests": data_manifests,
        "outputs": {
            "summary_json": str(out_dir / "summary.json"),
            "variant_summary_csv": str(out_dir / "variant_summary.csv"),
            "cell_summary_csv": str(out_dir / "cell_summary.csv"),
            "daily_csv": str(out_dir / "daily.csv"),
            "entries_parquet": str(out_dir / "entries.parquet"),
            "exits_parquet": str(out_dir / "exits.parquet"),
            "comparison_vs_old_q70_csv": str(out_dir / "comparison_vs_old_q70.csv"),
            "report_md": str(report_path),
        },
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report_path, summary, variant_rows, cell_rows, comparison)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
