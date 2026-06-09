#!/usr/bin/env python
"""Entry-trigger family diagnostic for CCUSDT.

Research-only diagnostic. It compares entry trigger families directly instead
of forcing every new structure through the old TFI-flat trigger. Inputs are
decision_frame_v1 and quote_frame_v1 only; future labels are diagnostic labels
computed inside this script and must not enter Runner or Bot runtime.
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
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/entry_trigger_family_diagnostic")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/strategy/v1-entry-trigger-family-diagnostic-20260602.md")
DEFAULT_BASELINE = Path(
    "systems/ccusdt_replay_exchange/runs/experiments/"
    "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521"
)
DEFAULT_ADMISSION_THRESHOLDS = Path(
    "systems/ccusdt_replay_exchange/runs/admission_thresholds/entry_spread_q70_20260516_18_20260521.json"
)

SCHEMA_ID = "ccusdt_entry_trigger_family_diagnostic_v0_1"
EPS = 1e-12
ETA = 1e-6
FIXED_EXIT_US = 60_000_000
FRAMES_THRESHOLD = 31.0

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
class TriggerSpec:
    family_id: str
    variant_id: str
    role: str
    score_metric: str | None = None
    window_sec: int | None = None
    score_quantile: float | None = None
    cost_quantile: float | None = None


class QuoteFrameIndex:
    def __init__(self, frames: list[dict[str, Any]]) -> None:
        if not frames:
            raise ValueError("quote_frame_v1 index is empty")
        self.frames = frames
        self.local_ts_us = np.array([int(row["local_ts_us"]) for row in frames], dtype=np.int64)
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
                mid = optional_float(row.get("mid_px"))
                local_ts_us = optional_int(row.get("local_ts_us")) or 0
                if local_ts_us <= 0 or bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
                    continue
                frames.append(
                    {
                        "local_ts_us": local_ts_us,
                        "bid_px": bid,
                        "ask_px": ask,
                        "mid_px": mid if mid is not None and mid > 0.0 else 0.5 * (bid + ask),
                    }
                )
        return cls(frames)

    def at_or_before(self, local_ts_us: int) -> dict[str, Any]:
        idx = bisect.bisect_right(self.local_ts_us, int(local_ts_us))
        if idx <= 0:
            idx = 1
        frame_idx = idx - 1
        return self.row_at(frame_idx)

    def row_at(self, idx: int) -> dict[str, Any]:
        idx = max(0, min(int(idx), len(self.local_ts_us) - 1))
        return {
            "local_ts_us": int(self.local_ts_us[idx]),
            "bid_px": float(self.bid[idx]),
            "ask_px": float(self.ask[idx]),
            "mid_px": float(self.mid[idx]),
        }

    def index_at_or_before(self, local_ts_us: int) -> int:
        idx = bisect.bisect_right(self.local_ts_us, int(local_ts_us))
        return max(0, idx - 1)

    def labels(self, local_ts_us: int, side_sign: int) -> dict[str, Any]:
        entry_idx = self.index_at_or_before(local_ts_us)
        entry_ts = int(self.local_ts_us[entry_idx])
        entry_bid = float(self.bid[entry_idx])
        entry_ask = float(self.ask[entry_idx])
        entry_mid = float(self.mid[entry_idx])

        idx20 = self.index_at_or_before(local_ts_us + 20_000_000)
        idx60 = self.index_at_or_before(local_ts_us + 60_000_000)
        exit20_mid = float(self.mid[idx20])
        exit60_bid = float(self.bid[idx60])
        exit60_ask = float(self.ask[idx60])
        exit60_mid = float(self.mid[idx60])

        mid20 = side_sign * 10_000.0 * math.log(exit20_mid / entry_mid)
        mid60 = side_sign * 10_000.0 * math.log(exit60_mid / entry_mid)
        if side_sign > 0:
            exec60 = 10_000.0 * math.log(exit60_bid / entry_ask)
        else:
            exec60 = 10_000.0 * math.log(entry_bid / exit60_ask)

        idx10 = self.index_at_or_before(local_ts_us + 10_000_000)
        path_mid = self.mid[entry_idx : idx10 + 1]
        if side_sign > 0:
            favorable = 10_000.0 * np.log(path_mid / entry_mid)
        else:
            favorable = 10_000.0 * np.log(entry_mid / path_mid)
        release_mfe10 = float(np.nanmax(favorable)) if len(favorable) else 0.0
        return {
            "entry_quote_ts_us": entry_ts,
            "entry_bid": entry_bid,
            "entry_ask": entry_ask,
            "entry_mid": entry_mid,
            "exit60_ts_us": int(self.local_ts_us[idx60]),
            "exit60_bid": exit60_bid,
            "exit60_ask": exit60_ask,
            "exit60_mid": exit60_mid,
            "mid_return_20s_bps": mid20,
            "mid_return_60s_bps": mid60,
            "top_of_book_executable_60s_bps": exec60,
            "release_mfe_10s_bps": release_mfe10,
            "decay_after_mfe_60s_bps": release_mfe10 - mid60,
            "mid_minus_executable_bps": mid60 - exec60,
            "label_valid": bool(idx60 > entry_idx),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--windows-sec", default="30,60")
    parser.add_argument("--score-quantiles", default="0.70,0.80")
    parser.add_argument("--cost-quantiles", default="0.50,0.70")
    parser.add_argument(
        "--families",
        default="",
        help="Optional comma-separated family_id filter, e.g. I1_pure_book_giveway.",
    )
    parser.add_argument("--max-rows-per-day", type=int, default=0)
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--admission-thresholds-json", type=Path, default=DEFAULT_ADMISSION_THRESHOLDS)
    parser.add_argument("--leverage-cap", type=float, default=3.0)
    parser.add_argument("--capacity-profile", choices=["fifo_clip", "core_idle01"], default="core_idle01")
    parser.add_argument("--idle01-gamma", type=float, default=1.0)
    parser.add_argument("--idle01-reserve", type=float, default=0.0)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--run-id")
    return parser.parse_args()


def parse_int_list(raw: str) -> list[int]:
    out = sorted({int(part.strip()) for part in raw.split(",") if part.strip()})
    if not out:
        raise ValueError("expected integer list")
    return out


def parse_float_list(raw: str) -> list[float]:
    out = sorted({float(part.strip()) for part in raw.split(",") if part.strip()})
    if not out:
        raise ValueError("expected float list")
    return out


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


def date_range(start: str, end: str) -> Iterable[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    while cur <= last:
        yield cur.isoformat()
        cur += timedelta(days=1)


def previous_day(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


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
        "trade_notional_quote",
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
    rename = {
        "best_bid_price": "bid",
        "best_ask_price": "ask",
        "best_bid_amount": "bid_amount",
        "best_ask_amount": "ask_amount",
    }
    df = df.rename(columns={key: value for key, value in rename.items() if key in df.columns})
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


def rolling_sum(ts_us: np.ndarray, values: np.ndarray, window_sec: int) -> np.ndarray:
    values = np.nan_to_num(values.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    csum = np.concatenate([[0.0], np.cumsum(values)])
    starts = np.searchsorted(ts_us, ts_us - int(window_sec * 1_000_000), side="left")
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


def add_path_features(df: pd.DataFrame, windows_sec: list[int]) -> pd.DataFrame:
    out = df.copy()
    ts_us = out["local_ts_us"].to_numpy(dtype=np.int64)
    tfi = pd.to_numeric(out["trade_flow_imbalance"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    side = np.sign(tfi)
    side[np.abs(tfi) < EPS] = 0.0
    out["side_sign"] = side.astype(int)
    out["abs_tfi"] = np.abs(tfi)
    out["entry_cross_bps"] = 0.5 * pd.to_numeric(out["spread_bps"], errors="coerce").fillna(np.nan)
    bid_depth = pd.to_numeric(out["bid_amount"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    ask_depth = pd.to_numeric(out["ask_amount"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    out["opposite_depth"] = np.where(side > 0, ask_depth, np.where(side < 0, bid_depth, np.nan))

    spread = pd.to_numeric(out["spread_bps"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    d_spread = np.diff(spread, prepend=spread[0])
    out["spread_worsening_30s"] = rolling_sum(ts_us, np.maximum(d_spread, 0.0), 30)

    for window in windows_sec:
        metrics: dict[int, dict[str, np.ndarray]] = {}
        for s in (1, -1):
            depth = ask_depth if s > 0 else bid_depth
            g = -safe_log_change(depth)
            p = rolling_sum(ts_us, np.maximum(g, 0.0), window)
            n = rolling_sum(ts_us, np.maximum(-g, 0.0), window)
            e = p + n
            metrics[s] = {
                "L": np.log(p + ETA) - np.log(n + ETA),
                "Z": (p - n) / np.sqrt(e + EPS),
                "E": e,
                "P": p,
                "N": n,
            }
        for metric in ["L", "Z", "E", "P", "N"]:
            values = np.full(len(out), np.nan, dtype=float)
            for s in (1, -1):
                mask = side == s
                values[mask] = metrics[s][metric][mask]
            out[f"giveway_{metric.lower()}_w{window}"] = values
            long_values = metrics[1][metric]
            short_values = metrics[-1][metric]
            out[f"pure_book_long_{metric.lower()}_w{window}"] = long_values
            out[f"pure_book_short_{metric.lower()}_w{window}"] = short_values
            best_is_long = long_values >= short_values
            out[f"pure_book_best_{metric.lower()}_w{window}"] = np.where(best_is_long, long_values, short_values)
            out[f"pure_book_other_{metric.lower()}_w{window}"] = np.where(best_is_long, short_values, long_values)
            out[f"pure_book_margin_{metric.lower()}_w{window}"] = np.abs(long_values - short_values)
            out[f"pure_book_side_{metric.lower()}_w{window}"] = np.where(best_is_long, 1, -1)
    return out


def old_trigger_membership(row: pd.Series) -> tuple[list[str], str, float]:
    tfi = optional_float(row.get("trade_flow_imbalance")) or 0.0
    high = tfi >= 1.0 - 1e-12
    low = tfi <= -1.0 + 1e-12
    if not high and not low:
        return [], "", 0.0
    direction = 1 if high else -1
    flat = abs(optional_float(row.get("past_event_25_bps")) or 999.0) <= 0.5
    stale25 = (optional_float(row.get("frames_since_mid_change")) or 0.0) >= 25.0
    trade_present = (optional_float(row.get("trade_window_count")) or 0.0) > 0.0
    active: dict[str, int] = {}
    if flat:
        active["tfi_follow_flat"] = direction
        if low:
            active["tfi_short_flat"] = -1
        if high:
            active["tfi_long_flat"] = 1
    if low and stale25:
        active["tfi_short_stale25"] = -1
    if trade_present and stale25:
        active["tfi_event_active"] = direction
    selected = [name for name in TRIGGER_ORDER if name in active and active[name] == direction]
    membership = "+".join(selected)
    return selected, membership, BASE_WEIGHTS.get(membership, 0.0)


def build_trigger_specs(windows_sec: list[int], score_quantiles: list[float], cost_quantiles: list[float]) -> list[TriggerSpec]:
    specs = [
        TriggerSpec("E0_old_tfi_flat", "E0_old_tfi_flat_q70", "baseline-trigger"),
        TriggerSpec("E5_static_low_depth_control", "E5_static_low_depth_control_q30", "control"),
    ]
    for metric in ["L", "Z"]:
        for window in windows_sec:
            for q in score_quantiles:
                specs.append(
                    TriggerSpec(
                        family_id="I1_pure_book_giveway",
                        variant_id=f"I1_pure_book_giveway_{metric.lower()}_w{window}_q{int(round(q * 100))}_marginq70",
                        role="independent-book-entry",
                        score_metric=metric,
                        window_sec=window,
                        score_quantile=q,
                    )
                )
    for family_id, role in [
        ("E1_tfi_giveway_confirm", "confirmation"),
        ("E2_mild_pressure_giveway", "new-entry-candidate"),
        ("E3_stale_giveway_release", "new-entry-candidate"),
    ]:
        for metric in ["L", "Z"]:
            for window in windows_sec:
                for q in score_quantiles:
                    specs.append(
                        TriggerSpec(
                            family_id=family_id,
                            variant_id=f"{family_id}_{metric.lower()}_w{window}_q{int(round(q * 100))}",
                            role=role,
                            score_metric=metric,
                            window_sec=window,
                            score_quantile=q,
                        )
                    )
    for metric in ["L", "Z"]:
        for window in windows_sec:
            for score_q in score_quantiles:
                for cost_q in cost_quantiles:
                    specs.append(
                        TriggerSpec(
                            family_id="E4_cost_allowed_giveway",
                            variant_id=(
                                f"E4_cost_allowed_giveway_{metric.lower()}_w{window}"
                                f"_q{int(round(score_q * 100))}_costq{int(round(cost_q * 100))}"
                            ),
                            role="cost-aware-entry",
                            score_metric=metric,
                            window_sec=window,
                            score_quantile=score_q,
                            cost_quantile=cost_q,
                        )
                    )
    return specs


def load_threshold_json(repo_root: Path, path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    resolved = path if path.is_absolute() else repo_root / path
    raw = read_json(resolved)
    rows = raw.get("thresholds", raw)
    if not isinstance(rows, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for day, value in rows.items():
        if isinstance(value, dict):
            threshold = optional_float(value.get("entry_cross_threshold_bps"))
            source = value.get("threshold_source")
        else:
            threshold = optional_float(value)
            source = str(resolved)
        if threshold is not None:
            out[str(day)] = {"q70": threshold, "q70_source": source or str(resolved)}
    return out


def thresholds_for_day(
    prior_df: pd.DataFrame,
    specs: list[TriggerSpec],
    day: str,
    spread_q70_loaded: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pressure = prior_df[prior_df["abs_tfi"] >= 0.5].copy()
    out: dict[str, Any] = {"date": day, "prior_day": previous_day(day)}
    entry_cross = pd.to_numeric(prior_df["entry_cross_bps"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    out["entry_cross_q50"] = float(entry_cross.quantile(0.50))
    if day in spread_q70_loaded:
        out["entry_cross_q70"] = float(spread_q70_loaded[day]["q70"])
        out["entry_cross_q70_source"] = spread_q70_loaded[day]["q70_source"]
    else:
        out["entry_cross_q70"] = float(entry_cross.quantile(0.70))
        out["entry_cross_q70_source"] = f"computed_prior_day_entry_cross_q70:{previous_day(day)}"
    out["opposite_depth_q30"] = float(
        pd.to_numeric(pressure["opposite_depth"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().quantile(0.30)
    )
    out["spread_worsening_q70"] = float(
        pd.to_numeric(pressure["spread_worsening_30s"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().quantile(0.70)
    )
    for spec in specs:
        if spec.score_metric is None or spec.window_sec is None or spec.score_quantile is None:
            continue
        metric = spec.score_metric.lower()
        if spec.family_id == "I1_pure_book_giveway":
            best_col = f"pure_book_best_{metric}_w{spec.window_sec}"
            margin_col = f"pure_book_margin_{metric}_w{spec.window_sec}"
            best_sample = pd.to_numeric(prior_df[best_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            margin_sample = pd.to_numeric(prior_df[margin_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            out[f"{best_col}_q{int(round(spec.score_quantile * 100))}"] = float(best_sample.quantile(spec.score_quantile))
            out[f"{best_col}_sample_count"] = int(len(best_sample))
            out[f"{margin_col}_q70"] = float(margin_sample.quantile(0.70))
            out[f"{margin_col}_sample_count"] = int(len(margin_sample))
        else:
            col = f"giveway_{metric}_w{spec.window_sec}"
            sample = pd.to_numeric(pressure[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            out[f"{col}_q{int(round(spec.score_quantile * 100))}"] = float(sample.quantile(spec.score_quantile))
            out[f"{col}_sample_count"] = int(len(sample))
    return out


def score_threshold(thresholds: dict[str, Any], spec: TriggerSpec) -> float | None:
    if spec.score_metric is None or spec.window_sec is None or spec.score_quantile is None:
        return None
    if spec.family_id == "I1_pure_book_giveway":
        key = f"pure_book_best_{spec.score_metric.lower()}_w{spec.window_sec}_q{int(round(spec.score_quantile * 100))}"
    else:
        key = f"giveway_{spec.score_metric.lower()}_w{spec.window_sec}_q{int(round(spec.score_quantile * 100))}"
    return optional_float(thresholds.get(key))


def margin_threshold(thresholds: dict[str, Any], spec: TriggerSpec) -> float | None:
    if spec.score_metric is None or spec.window_sec is None:
        return None
    key = f"pure_book_margin_{spec.score_metric.lower()}_w{spec.window_sec}_q70"
    return optional_float(thresholds.get(key))


def trigger_match(row: pd.Series, spec: TriggerSpec, thresholds: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    tfi = optional_float(row.get("trade_flow_imbalance")) or 0.0
    abs_tfi = abs(tfi)
    side_sign = 1 if tfi > 0 else (-1 if tfi < 0 else 0)
    entry_cross = optional_float(row.get("entry_cross_bps"))
    q70 = float(thresholds["entry_cross_q70"])
    q50 = float(thresholds["entry_cross_q50"])
    spread_ok_q70 = entry_cross is not None and entry_cross <= q70
    spread_ok_q50 = entry_cross is not None and entry_cross <= q50
    frames = optional_float(row.get("frames_since_mid_change")) or 0.0
    past = optional_float(row.get("past_event_25_bps"))
    old_selected, old_membership, old_base_weight = old_trigger_membership(row)

    score = math.nan
    score_ok = False
    score_thr = None
    margin = math.nan
    margin_thr = None
    margin_ok = False
    independent_side_sign = 0
    if spec.family_id == "I1_pure_book_giveway":
        if spec.score_metric is None or spec.window_sec is None:
            return False, {}
        metric = spec.score_metric.lower()
        score = optional_float(row.get(f"pure_book_best_{metric}_w{spec.window_sec}")) or math.nan
        margin = optional_float(row.get(f"pure_book_margin_{metric}_w{spec.window_sec}")) or math.nan
        independent_side_sign = optional_int(row.get(f"pure_book_side_{metric}_w{spec.window_sec}")) or 0
        score_thr = score_threshold(thresholds, spec)
        margin_thr = margin_threshold(thresholds, spec)
        score_ok = score_thr is not None and math.isfinite(score) and score >= score_thr
        margin_ok = margin_thr is not None and math.isfinite(margin) and margin >= margin_thr
        side_sign = independent_side_sign
    if side_sign == 0:
        return False, {}
    if spec.score_metric and spec.window_sec:
        if spec.family_id != "I1_pure_book_giveway":
            score = optional_float(row.get(f"giveway_{spec.score_metric.lower()}_w{spec.window_sec}")) or math.nan
            score_thr = score_threshold(thresholds, spec)
            score_ok = score_thr is not None and math.isfinite(score) and score >= score_thr

    matched = False
    reason = ""
    if spec.family_id == "I1_pure_book_giveway":
        matched = score_ok and margin_ok and spread_ok_q70
        reason = "pure_book_giveway_score_margin_q70"
    elif spec.family_id == "E0_old_tfi_flat":
        matched = abs_tfi >= 1.0 and past is not None and abs(past) <= 0.5 and spread_ok_q70
        reason = "old_tfi_flat_q70"
    elif spec.family_id == "E1_tfi_giveway_confirm":
        matched = abs_tfi >= 1.0 and score_ok and spread_ok_q70
        reason = "strong_tfi_giveway_q70"
    elif spec.family_id == "E2_mild_pressure_giveway":
        matched = abs_tfi >= 0.5 and score_ok and past is not None and abs(past) <= 1.5 and spread_ok_q70
        reason = "mild_pressure_flatish_giveway_q70"
    elif spec.family_id == "E3_stale_giveway_release":
        matched = abs_tfi >= 0.5 and score_ok and frames >= 25.0 and spread_ok_q70
        reason = "mild_pressure_stale_giveway_q70"
    elif spec.family_id == "E4_cost_allowed_giveway":
        cost_ok = spread_ok_q50 if spec.cost_quantile == 0.5 else spread_ok_q70
        matched = (
            abs_tfi >= 0.5
            and score_ok
            and cost_ok
            and (optional_float(row.get("spread_worsening_30s")) or 0.0) <= float(thresholds["spread_worsening_q70"])
        )
        reason = "mild_pressure_giveway_cost_allowed"
    elif spec.family_id == "E5_static_low_depth_control":
        depth = optional_float(row.get("opposite_depth"))
        matched = abs_tfi >= 0.5 and depth is not None and depth <= float(thresholds["opposite_depth_q30"]) and spread_ok_q70
        reason = "static_low_opposite_depth_control"
        score_ok = matched
        score = depth if depth is not None else math.nan
        score_thr = float(thresholds["opposite_depth_q30"])

    if not matched:
        return False, {}

    if spec.family_id == "E0_old_tfi_flat":
        memory_ok = False
        base_weight = old_base_weight if old_base_weight > 0.0 else 0.5
    elif spec.family_id == "I1_pure_book_giveway":
        memory_ok = True
        base_weight = 0.5
    elif spec.family_id == "E5_static_low_depth_control":
        memory_ok = True
        base_weight = 0.5
    else:
        memory_ok = bool(score_ok)
        base_weight = 0.5
    frames_ok = frames >= FRAMES_THRESHOLD
    cell = make_cell(memory_ok, frames_ok)
    return True, {
        "side_sign": side_sign,
        "side": "buy" if side_sign > 0 else "sell",
        "entry_cross_bps": entry_cross,
        "score_value": score,
        "score_threshold": score_thr,
        "margin_value": margin,
        "margin_threshold": margin_thr,
        "margin_ok": margin_ok,
        "memory_ok": memory_ok,
        "frames_ok": frames_ok,
        "cell": cell,
        "base_weight": base_weight,
        "old_trigger_membership": old_membership,
        "old_trigger_classes": "+".join(old_selected),
        "trigger_reason": reason,
    }


def make_cell(memory_ok: bool, frames_ok: bool) -> str:
    if memory_ok and frames_ok:
        return "11_r5_frames"
    if memory_ok:
        return "10_r5_only"
    if frames_ok:
        return "01_frames_only"
    return "00_none"


def build_event_rows(
    df: pd.DataFrame,
    specs: list[TriggerSpec],
    thresholds: dict[str, Any],
    quote_index: QuoteFrameIndex,
    day: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        for spec in specs:
            matched, info = trigger_match(row, spec, thresholds)
            if not matched:
                continue
            side_sign = int(info["side_sign"])
            labels = quote_index.labels(int(row["local_ts_us"]), side_sign)
            rows.append(
                {
                    "schema_id": "ccusdt_entry_trigger_event_v1",
                    "date": day,
                    "variant_id": spec.variant_id,
                    "family_id": spec.family_id,
                    "role": spec.role,
                    "score_metric": spec.score_metric,
                    "window_sec": spec.window_sec,
                    "score_quantile": spec.score_quantile,
                    "cost_quantile": spec.cost_quantile,
                    "local_ts_us": int(row["local_ts_us"]),
                    "observed_seq": optional_int(row.get("observed_seq")) or optional_int(row.get("event_index")) or int(idx),
                    "side_sign": side_sign,
                    "side": info["side"],
                    "cell": info["cell"],
                    "memory_ok": bool(info["memory_ok"]),
                    "frames_ok": bool(info["frames_ok"]),
                    "trigger_reason": info["trigger_reason"],
                    "old_trigger_membership": info["old_trigger_membership"],
                    "old_trigger_classes": info["old_trigger_classes"],
                    "base_weight": float(info["base_weight"]),
                    "score_value": info["score_value"],
                    "score_threshold": info["score_threshold"],
                    "margin_value": info.get("margin_value"),
                    "margin_threshold": info.get("margin_threshold"),
                    "margin_ok": info.get("margin_ok"),
                    "entry_cross_bps": info["entry_cross_bps"],
                    "entry_cross_q70": thresholds["entry_cross_q70"],
                    "trade_flow_imbalance": optional_float(row.get("trade_flow_imbalance")),
                    "abs_tfi": optional_float(row.get("abs_tfi")),
                    "trade_window_count": optional_float(row.get("trade_window_count")),
                    "trade_notional_quote": optional_float(row.get("trade_notional_quote")),
                    "past_event_25_bps": optional_float(row.get("past_event_25_bps")),
                    "frames_since_mid_change": optional_float(row.get("frames_since_mid_change")),
                    "opposite_depth": (
                        optional_float(row.get("ask_amount"))
                        if side_sign > 0
                        else optional_float(row.get("bid_amount"))
                    ),
                    "spread_worsening_30s": optional_float(row.get("spread_worsening_30s")),
                    **labels,
                }
            )
    return rows


def load_baseline(run_dir: Path) -> tuple[dict[str, Any], set[tuple[str, int, int]], pd.DataFrame]:
    summary = read_json(run_dir / "summary.json")
    entries_path = run_dir / "entries.parquet"
    exits_path = run_dir / "exits.parquet"
    if not entries_path.exists():
        return summary, set(), pd.DataFrame()
    entries = pd.read_parquet(entries_path)
    entries = entries[entries["actual_exposure"] > EPS].copy()
    keys = set(zip(entries["date"].astype(str), entries["entry_ts_us"].astype("int64"), entries["direction"].astype("int64")))
    exits = pd.read_parquet(exits_path) if exits_path.exists() else pd.DataFrame()
    return summary, keys, exits


def summarize_unit(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return rows
    for (variant_id, family_id), g in panel.groupby(["variant_id", "family_id"], sort=True):
        daily = g.groupby("date")["top_of_book_executable_60s_bps"].mean()
        rows.append(
            {
                "variant_id": variant_id,
                "family_id": family_id,
                "role": g["role"].iloc[0],
                "n": int(len(g)),
                "mean_exec60_bps": float(g["top_of_book_executable_60s_bps"].mean()),
                "median_exec60_bps": float(g["top_of_book_executable_60s_bps"].median()),
                "mean_mid20_bps": float(g["mid_return_20s_bps"].mean()),
                "mean_mid60_bps": float(g["mid_return_60s_bps"].mean()),
                "mean_release_mfe10_bps": float(g["release_mfe_10s_bps"].mean()),
                "mean_decay_after_mfe60_bps": float(g["decay_after_mfe_60s_bps"].mean()),
                "mean_entry_cross_bps": float(g["entry_cross_bps"].mean()),
                "mean_mid_minus_exec_bps": float(g["mid_minus_executable_bps"].mean()),
                "hit_rate_exec60": float((g["top_of_book_executable_60s_bps"] > 0.0).mean()),
                "positive_days": int((daily > 0.0).sum()),
                "days": int(daily.size),
                "daily_sign_rate": float((daily > 0.0).mean()) if daily.size else math.nan,
                "worst_day_mean_exec60_bps": float(daily.min()) if daily.size else math.nan,
                "status": unit_status(g, daily),
            }
        )
    return rows


def unit_status(g: pd.DataFrame, daily: pd.Series) -> str:
    mean_exec = float(g["top_of_book_executable_60s_bps"].mean())
    mean_mid = float(g["mid_return_60s_bps"].mean())
    if mean_mid > 0.0 and mean_exec <= 0.0:
        return "spread_cost_mirage"
    if mean_exec > 0.0 and daily.size > 0 and (daily > 0.0).all():
        return "unit_positive_all_days"
    if mean_exec > 0.0:
        return "unit_positive_unstable"
    return "weak_or_negative"


def summarize_by_day(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return rows
    for (variant_id, day), g in panel.groupby(["variant_id", "date"], sort=True):
        rows.append(
            {
                "variant_id": variant_id,
                "family_id": g["family_id"].iloc[0],
                "date": day,
                "n": int(len(g)),
                "mean_exec60_bps": float(g["top_of_book_executable_60s_bps"].mean()),
                "median_exec60_bps": float(g["top_of_book_executable_60s_bps"].median()),
                "mean_mid60_bps": float(g["mid_return_60s_bps"].mean()),
                "mean_release_mfe10_bps": float(g["release_mfe_10s_bps"].mean()),
                "hit_rate_exec60": float((g["top_of_book_executable_60s_bps"] > 0.0).mean()),
            }
        )
    return rows


def summarize_cells(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return rows
    for (variant_id, cell), g in panel.groupby(["variant_id", "cell"], sort=True):
        rows.append(
            {
                "variant_id": variant_id,
                "family_id": g["family_id"].iloc[0],
                "cell": cell,
                "n": int(len(g)),
                "mean_exec60_bps": float(g["top_of_book_executable_60s_bps"].mean()),
                "mean_mid60_bps": float(g["mid_return_60s_bps"].mean()),
                "mean_release_mfe10_bps": float(g["release_mfe_10s_bps"].mean()),
                "hit_rate_exec60": float((g["top_of_book_executable_60s_bps"] > 0.0).mean()),
            }
        )
    return rows


def capacity_backtest(panel: pd.DataFrame, specs: list[TriggerSpec], args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return rows
    for spec in specs:
        g = panel[panel["variant_id"] == spec.variant_id].sort_values("local_ts_us")
        capacity = build_capacity_allocator(
            capacity_profile=args.capacity_profile,
            leverage_cap=args.leverage_cap,
            idle01_gamma=args.idle01_gamma,
            idle01_reserve=args.idle01_reserve,
        )
        open_positions: list[tuple[int, float]] = []
        net = 0.0
        mid = 0.0
        actual_exposure = 0.0
        actual_entries = 0
        clipped = 0
        skipped = 0
        daily_net: dict[str, float] = {}
        for _, row in g.iterrows():
            now = int(row["local_ts_us"])
            still_open: list[tuple[int, float]] = []
            for pos_id, due_ts in open_positions:
                if due_ts <= now:
                    capacity.close(pos_id)
                else:
                    still_open.append((pos_id, due_ts))
            open_positions = still_open
            cell = str(row["cell"])
            gamma = GAMMA_CORE_IDLE01_G1.get(cell, 0.0)
            requested = float(row["base_weight"]) * gamma
            signal = {
                "shadow_position_id": int(len(rows) * 1_000_000 + actual_entries + skipped + clipped + 1),
                "target_exposure": requested,
                "weak_overlay_weight": float(row["base_weight"]),
                "cell": cell,
            }
            decision = capacity.decide(signal).to_dict()
            actual = float(decision["actual_exposure"])
            if actual <= EPS:
                skipped += 1
                continue
            if float(decision["clipped_exposure"]) > EPS:
                clipped += 1
            actual_entries += 1
            actual_exposure += actual
            exec_bps = float(row["top_of_book_executable_60s_bps"])
            mid_bps = float(row["mid_return_60s_bps"])
            weighted = actual * exec_bps
            net += weighted
            mid += actual * mid_bps
            day = str(row["date"])
            daily_net[day] = daily_net.get(day, 0.0) + weighted
            open_positions.append((int(signal["shadow_position_id"]), int(row["local_ts_us"]) + FIXED_EXIT_US))
        daily_values = list(daily_net.values())
        rows.append(
            {
                "variant_id": spec.variant_id,
                "family_id": spec.family_id,
                "role": spec.role,
                "candidate_n": int(len(g)),
                "actual_entries": actual_entries,
                "skipped_entries": skipped,
                "clipped_entries": clipped,
                "actual_exposure": actual_exposure,
                "net_weighted_bps": net,
                "mid_weighted_bps": mid,
                "mean_unit_net_bps": net / actual_exposure if actual_exposure > EPS else math.nan,
                "positive_days": sum(1 for value in daily_values if value > 0.0),
                "days": len(daily_values),
                "worst_day_net_weighted_bps": min(daily_values) if daily_values else math.nan,
            }
        )
    return rows


def overlap_rows(panel: pd.DataFrame, baseline_keys: set[tuple[str, int, int]], baseline_exits: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return rows
    baseline_exit_by_key = pd.DataFrame()
    if not baseline_exits.empty and {"date", "entry_ts_us", "direction", "net_weighted_bps", "actual_exposure"}.issubset(baseline_exits.columns):
        baseline_exit_by_key = baseline_exits.copy()
        baseline_exit_by_key["key"] = list(
            zip(
                baseline_exit_by_key["date"].astype(str),
                baseline_exit_by_key["entry_ts_us"].astype("int64"),
                baseline_exit_by_key["direction"].astype("int64"),
            )
        )
    for variant_id, g in panel.groupby("variant_id", sort=True):
        keys = set(zip(g["date"].astype(str), g["local_ts_us"].astype("int64"), g["side_sign"].astype("int64")))
        g = g.copy()
        g["overlap_bucket"] = [
            "old_overlap" if key in baseline_keys else "new_only"
            for key in zip(g["date"].astype(str), g["local_ts_us"].astype("int64"), g["side_sign"].astype("int64"))
        ]
        for bucket, sub in g.groupby("overlap_bucket", sort=True):
            rows.append(
                {
                    "variant_id": variant_id,
                    "family_id": sub["family_id"].iloc[0],
                    "bucket": bucket,
                    "n": int(len(sub)),
                    "mean_exec60_bps": float(sub["top_of_book_executable_60s_bps"].mean()),
                    "mean_mid60_bps": float(sub["mid_return_60s_bps"].mean()),
                    "hit_rate_exec60": float((sub["top_of_book_executable_60s_bps"] > 0.0).mean()),
                }
            )
        old_only = baseline_keys - keys
        if not baseline_exit_by_key.empty:
            old = baseline_exit_by_key[baseline_exit_by_key["key"].isin(old_only)]
            rows.append(
                {
                    "variant_id": variant_id,
                    "family_id": g["family_id"].iloc[0],
                    "bucket": "old_only",
                    "n": int(len(old)),
                    "mean_exec60_bps": (
                        float(old["net_weighted_bps"].sum() / old["actual_exposure"].sum()) if len(old) and old["actual_exposure"].sum() > EPS else math.nan
                    ),
                    "mean_mid60_bps": math.nan,
                    "hit_rate_exec60": float((old["net_bps_after_cost"] > 0.0).mean()) if "net_bps_after_cost" in old.columns and len(old) else math.nan,
                }
            )
    return rows


def markdown_table(rows: list[dict[str, Any]], columns: list[str], limit: int = 20) -> str:
    rows = rows[:limit]
    if not rows:
        return "_No rows._"
    lines = ["|" + "|".join(columns) + "|", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
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
    family_rows: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]],
    overlap: list[dict[str, Any]],
    capacity_rows: list[dict[str, Any]],
) -> None:
    top_unit = sorted(family_rows, key=lambda row: float(row.get("mean_exec60_bps") or -1e18), reverse=True)
    top_capacity = sorted(capacity_rows, key=lambda row: float(row.get("net_weighted_bps") or -1e18), reverse=True)
    top_cells = sorted(cell_rows, key=lambda row: float(row.get("mean_exec60_bps") or -1e18), reverse=True)
    new_only = sorted(
        [row for row in overlap if row.get("bucket") == "new_only"],
        key=lambda row: float(row.get("mean_exec60_bps") or -1e18),
        reverse=True,
    )
    lines = [
        "# CCUSDT Entry Trigger Family Diagnostic",
        "",
        f"Status: `{summary['schema_id']}`.",
        "",
        "Boundary: research-only; inputs are decision_frame_v1 and quote_frame_v1; future labels are diagnostic only.",
        "",
        "## Setup",
        "",
        f"- dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- trigger variants: `{summary['trigger_variant_count']}`",
        f"- event rows: `{summary['event_rows']}`",
        f"- baseline: `{summary['baseline'].get('run_id')}`",
        "",
        "## Top Unit Evidence",
        "",
        markdown_table(
            top_unit,
            ["variant_id", "family_id", "n", "mean_exec60_bps", "mean_mid60_bps", "hit_rate_exec60", "positive_days", "days", "status"],
            15,
        ),
        "",
        "## Top Capacity Evidence",
        "",
        markdown_table(
            top_capacity,
            ["variant_id", "family_id", "actual_entries", "net_weighted_bps", "mean_unit_net_bps", "positive_days", "days"],
            15,
        ),
        "",
        "## Top Cells",
        "",
        markdown_table(top_cells, ["variant_id", "family_id", "cell", "n", "mean_exec60_bps", "hit_rate_exec60"], 15),
        "",
        "## New-only Candidates vs Old Baseline",
        "",
        markdown_table(new_only, ["variant_id", "family_id", "bucket", "n", "mean_exec60_bps", "hit_rate_exec60"], 15),
        "",
        "## Guardrails",
        "",
        "- Unit evidence evaluates trigger quality before capacity.",
        "- Capacity evidence is a diagnostic approximation, not Bot promotion.",
        "- Dynamic giveway is compared against static low-depth control.",
        "- Runner, Bot, Monitor, legacy `date/`, scored entries, PnL, MFE, and MAE are not runtime inputs.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    start = time.perf_counter()
    args = parse_args()
    repo_root = args.repo_root.resolve()
    windows_sec = parse_int_list(args.windows_sec)
    score_quantiles = parse_float_list(args.score_quantiles)
    cost_quantiles = parse_float_list(args.cost_quantiles)
    specs = build_trigger_specs(windows_sec, score_quantiles, cost_quantiles)
    if args.families.strip():
        wanted = {part.strip() for part in args.families.split(",") if part.strip()}
        specs = [spec for spec in specs if spec.family_id in wanted]
        if not specs:
            raise ValueError(f"--families selected no trigger specs: {sorted(wanted)}")
    days = list(date_range(args.from_date, args.to_date))
    run_id = args.run_id or f"ccusdt_{args.from_date}_{args.to_date}_v0_1"
    out_dir = args.out_dir if args.out_dir else DEFAULT_OUT_ROOT / run_id
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    baseline_dir = args.baseline_run_dir if args.baseline_run_dir.is_absolute() else repo_root / args.baseline_run_dir
    baseline_summary, baseline_keys, baseline_exits = load_baseline(baseline_dir)
    threshold_json = args.admission_thresholds_json if args.admission_thresholds_json.is_absolute() else repo_root / args.admission_thresholds_json
    loaded_spread_thresholds = load_threshold_json(repo_root, threshold_json)

    event_rows: list[dict[str, Any]] = []
    data_manifests: list[dict[str, Any]] = []
    threshold_manifests: list[dict[str, Any]] = []

    for day in days:
        prior = previous_day(day)
        prior_df = add_path_features(load_decision_frame(repo_root, args.symbol, prior, args.max_rows_per_day), windows_sec)
        thresholds = thresholds_for_day(prior_df, specs, day, loaded_spread_thresholds)
        threshold_manifests.append(thresholds)
        df = add_path_features(load_decision_frame(repo_root, args.symbol, day, args.max_rows_per_day), windows_sec)
        quote_index = QuoteFrameIndex.load(repo_root, args.symbol, day)
        event_rows.extend(build_event_rows(df, specs, thresholds, quote_index, day))
        manifest = read_json(decision_manifest_path(repo_root, args.symbol, day))
        data_manifests.append(
            {
                "date": day,
                "rows_loaded": int(len(df)),
                "decision_manifest_path": str(decision_manifest_path(repo_root, args.symbol, day)),
                "quote_frame_path": str(quote_frame_path(repo_root, args.symbol, day)),
                "field_hash_sha256": manifest.get("field_hash_sha256"),
                "builder_version": manifest.get("builder_version"),
                "schema_version": manifest.get("schema_version"),
            }
        )

    panel = pd.DataFrame(event_rows)
    family_rows = summarize_unit(panel)
    by_day_rows = summarize_by_day(panel)
    cell_rows = summarize_cells(panel)
    capacity_rows = capacity_backtest(panel, specs, args)
    overlap = overlap_rows(panel, baseline_keys, baseline_exits)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(out_dir / "trigger_event_panel.parquet", event_rows)
    write_csv(out_dir / "trigger_family_summary.csv", family_rows)
    write_csv(out_dir / "trigger_by_day.csv", by_day_rows)
    write_csv(out_dir / "trigger_cell_summary.csv", cell_rows)
    write_csv(out_dir / "trigger_overlap_vs_old_q70.csv", overlap)
    write_csv(out_dir / "trigger_capacity_backtest_summary.csv", capacity_rows)

    summary = {
        "schema_id": SCHEMA_ID,
        "ok": True,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "run_id": run_id,
        "trigger_variant_count": len(specs),
        "event_rows": len(event_rows),
        "baseline": {
            "run_id": baseline_summary.get("run_id"),
            "actual_entries": baseline_summary.get("actual_entries"),
            "net_weighted_bps": baseline_summary.get("net_weighted_bps"),
            "positive_days": baseline_summary.get("positive_days"),
            "days": baseline_summary.get("days"),
        },
        "data_manifests": data_manifests,
        "threshold_manifests": threshold_manifests,
        "boundary": "research-only; inputs decision_frame_v1 and quote_frame_v1; no date/scored entries/PnL/MFE/MAE runtime inputs",
        "outputs": {
            "trigger_event_panel_parquet": str(out_dir / "trigger_event_panel.parquet"),
            "trigger_family_summary_csv": str(out_dir / "trigger_family_summary.csv"),
            "trigger_by_day_csv": str(out_dir / "trigger_by_day.csv"),
            "trigger_cell_summary_csv": str(out_dir / "trigger_cell_summary.csv"),
            "trigger_overlap_vs_old_q70_csv": str(out_dir / "trigger_overlap_vs_old_q70.csv"),
            "trigger_capacity_backtest_summary_csv": str(out_dir / "trigger_capacity_backtest_summary.csv"),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report_path, summary, family_rows, cell_rows, overlap, capacity_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
