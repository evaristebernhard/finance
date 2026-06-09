#!/usr/bin/env python
"""Discover event/regime strategy families from decision_frame_v1 cache.

This is a fast research diagnostic. It scans market-derived decision frames,
extracts structurally different event families, and evaluates both mid labels
and executable top-of-book taker labels. It does not read legacy scored entries,
future labels, PnL/MFE/MAE files, or root research scripts.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DECISION_ROOT = Path("data/canonical_parquet/cex/bullish")
QUOTE_ROOT = Path("data/canonical/cex/bullish")
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/event_regime_discovery")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/strategy/v1-event-regime-discovery-20260601.md")


FRAME_COLUMNS = [
    "observed_seq",
    "local_ts_us",
    "event_index",
    "factor_eligible",
    "best_bid_price",
    "best_bid_amount",
    "best_ask_price",
    "best_ask_amount",
    "mid",
    "spread_bps",
    "bid_levels",
    "ask_levels",
    "trade_window_count",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "mid_change_prev",
    "quote_change_prev",
    "top_size_change_prev",
    "frames_since_mid_change",
    "past_event_25_bps",
]


@dataclass(frozen=True)
class EventSpec:
    name: str
    description: str
    direction: str
    strict_migration: str


@dataclass(frozen=True)
class StateMachineSpec:
    name: str
    mechanism_class: str
    base_family: str
    description: str
    direction: str
    confirmation: str
    strict_migration: str


EVENT_SPECS = [
    EventSpec(
        "spread_shock_reversion",
        "Wide spread after a recent mid move; tests whether the move mean-reverts once crossing cost is explicit.",
        "opposite_recent_mid_move",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "spread_shock_breakout",
        "Wide spread after a recent mid move; tests whether the move continues despite crossing cost.",
        "same_as_recent_mid_move",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "depth_collapse_flow_continuation",
        "Top depth collapses while signed flow is strong; tests vacuum plus aggressive-flow continuation.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "depth_collapse_flow_reversal",
        "Top depth collapses while signed flow is strong; tests whether flow is exhausted and reverses.",
        "opposite_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "depth_collapse_low_spread_continuation",
        "Depth collapse plus signed flow, restricted to below-median rolling spread to avoid pure crossing-cost mirages.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "trade_burst_continuation",
        "Trade intensity jumps with signed imbalance; tests event-driven flow burst continuation.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "trade_burst_reversal",
        "Trade intensity jumps with signed imbalance; tests burst exhaustion and reversal.",
        "opposite_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "trade_burst_low_spread_continuation",
        "Trade burst continuation restricted to below-median rolling spread.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "quote_refresh_burst_continuation",
        "Many quote/top-size changes occur with signed flow; tests quote-refresh regime continuation.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "quote_refresh_burst_reversal",
        "Many quote/top-size changes occur with signed flow; tests refresh burst exhaustion and reversal.",
        "opposite_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "sweep_after_quiet_continuation",
        "A signed trade burst arrives after a quiet book; tests sweep-after-quiet continuation.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "sweep_after_quiet_reversal",
        "A signed trade burst arrives after a quiet book; tests whether the first sweep is faded.",
        "opposite_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "absorption_reversal",
        "Aggressive flow points one way while top-of-book imbalance leans against it; tests absorption/reversal.",
        "opposite_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "absorption_continuation",
        "Aggressive flow points one way while top-of-book imbalance leans against it; tests whether flow overwhelms absorption.",
        "same_as_tfi",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "volatility_expansion_breakout",
        "Recent mid movement expands sharply without an extreme spread shock; tests breakout continuation.",
        "same_as_recent_mid_move",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "volatility_expansion_reversal",
        "Recent mid movement expands sharply without an extreme spread shock; tests post-expansion reversion.",
        "opposite_recent_mid_move",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "vacuum_reversal",
        "Thin top depth and wide spread after a recent mid move; tests fragile vacuum reversal.",
        "opposite_recent_mid_move",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    EventSpec(
        "vacuum_breakout",
        "Thin top depth and wide spread after a recent mid move; tests fragile vacuum continuation.",
        "same_as_recent_mid_move",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
]


STATE_MACHINE_SPECS = [
    StateMachineSpec(
        "depth_collapse_wait_spread_repair_continuation",
        "conditional_wait_depth_collapse",
        "depth_collapse_flow_continuation",
        "Observe depth collapse plus signed flow, then wait for spread to repair before crossing with the flow.",
        "same_as_base_tfi",
        "spread_repaired_and_flow_persists",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    StateMachineSpec(
        "depth_collapse_wait_flow_persistence_continuation",
        "conditional_wait_depth_collapse",
        "depth_collapse_flow_continuation",
        "Observe depth collapse plus signed flow, then require same-side flow persistence before entry.",
        "same_as_base_tfi",
        "flow_persists",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    StateMachineSpec(
        "vacuum_wait_breakout_confirmation",
        "conditional_wait_liquidity_vacuum",
        "vacuum_breakout",
        "Observe a liquidity vacuum breakout, then enter only if the move is still confirmed after a short wait.",
        "same_as_base_past_move",
        "move_persists_and_spread_not_worse",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    StateMachineSpec(
        "spread_shock_wait_repair_reversion",
        "conditional_wait_spread_shock",
        "spread_shock_reversion",
        "Observe a spread shock, wait for spread repair, then test whether the shock can be faded.",
        "opposite_base_past_move",
        "spread_repaired",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    StateMachineSpec(
        "absorption_wait_failed_absorption_continuation",
        "conditional_wait_absorption",
        "absorption_continuation",
        "Observe flow pushing against queue imbalance, then enter with flow only if absorption breaks.",
        "same_as_base_tfi",
        "absorption_breaks_and_flow_persists",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    StateMachineSpec(
        "absorption_wait_confirmed_reversal",
        "conditional_wait_absorption",
        "absorption_reversal",
        "Observe flow pushing against queue imbalance, then fade only if the opposing book pressure remains.",
        "opposite_base_tfi",
        "absorption_holds",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
    StateMachineSpec(
        "sweep_after_quiet_wait_flow_persistence",
        "conditional_wait_sweep_after_quiet",
        "sweep_after_quiet_continuation",
        "Observe a sweep after a quiet book, then enter only if same-side flow persists after the first impulse.",
        "same_as_base_tfi",
        "flow_persists_and_spread_not_worse",
        "panel_sparse_fast_clock_ready_top_of_book_taker_only",
    ),
]


MECHANISM_CLASSES = {
    "spread_shock_reversion": "spread_shock_reversion_or_breakout",
    "spread_shock_breakout": "spread_shock_reversion_or_breakout",
    "depth_collapse_flow_continuation": "depth_collapse_flow",
    "depth_collapse_flow_reversal": "depth_collapse_flow",
    "depth_collapse_low_spread_continuation": "depth_collapse_flow",
    "trade_burst_continuation": "flow_burst",
    "trade_burst_reversal": "flow_burst",
    "trade_burst_low_spread_continuation": "flow_burst",
    "quote_refresh_burst_continuation": "quote_refresh_flow",
    "quote_refresh_burst_reversal": "quote_refresh_flow",
    "sweep_after_quiet_continuation": "sweep_after_quiet",
    "sweep_after_quiet_reversal": "sweep_after_quiet",
    "absorption_reversal": "absorption_or_overwhelm",
    "absorption_continuation": "absorption_or_overwhelm",
    "volatility_expansion_breakout": "volatility_expansion",
    "volatility_expansion_reversal": "volatility_expansion",
    "vacuum_reversal": "liquidity_vacuum",
    "vacuum_breakout": "liquidity_vacuum",
}


def mechanism_class(family: str) -> str:
    return MECHANISM_CLASSES.get(family, "unknown")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-30")
    parser.add_argument("--horizons-sec", default="5,20,60")
    parser.add_argument("--state-machine-waits-sec", default="5,10,20")
    parser.add_argument("--rolling-window", type=int, default=1000)
    parser.add_argument("--min-rolling-periods", type=int, default=200)
    parser.add_argument("--refractory-us", type=int, default=5_000_000)
    parser.add_argument("--min-events", type=int, default=30)
    parser.add_argument("--candidate-horizon-sec", type=int, default=20)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write-events", action="store_true", help="Write full event rows to Parquet.")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
    current = left
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def optional_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return int(number)


def decision_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def decision_manifest_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / DECISION_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "manifest.json"


def quote_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / QUOTE_ROOT / symbol / "quote_frame_v1" / f"dt={day}" / "part_000001.csv.gz"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return raw if isinstance(raw, dict) else {}


class QuoteIndex:
    def __init__(self, rows: list[dict[str, float | int]]) -> None:
        if not rows:
            raise ValueError("empty quote_frame index")
        self.rows = rows
        self.ts = np.array([int(row["local_ts_us"]) for row in rows], dtype=np.int64)

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteIndex":
        path = quote_path(repo_root, symbol, day)
        rows: list[dict[str, float | int]] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                ts = int(raw.get("local_ts_us") or 0)
                bid = optional_float(raw.get("bid_px"))
                ask = optional_float(raw.get("ask_px"))
                mid = optional_float(raw.get("mid_px"))
                if ts <= 0 or bid is None or ask is None or bid <= 0.0 or ask <= 0.0:
                    continue
                rows.append(
                    {
                        "local_ts_us": ts,
                        "bid": bid,
                        "ask": ask,
                        "mid": mid if mid is not None and mid > 0.0 else 0.5 * (bid + ask),
                    }
                )
        return cls(rows)

    def at_or_before(self, local_ts_us: int) -> dict[str, float | int] | None:
        idx = int(np.searchsorted(self.ts, int(local_ts_us), side="right") - 1)
        if idx < 0:
            return None
        return self.rows[idx]


class FrameIndex:
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.ts = df["local_ts_us"].astype("int64").to_numpy()

    def at_or_before(self, local_ts_us: int) -> pd.Series | None:
        idx = int(np.searchsorted(self.ts, int(local_ts_us), side="right") - 1)
        if idx < 0:
            return None
        return self.df.iloc[idx]


def load_decision_frames(repo_root: Path, symbol: str, day: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = decision_path(repo_root, symbol, day)
    manifest = read_json(decision_manifest_path(repo_root, symbol, day))
    table = pq.read_table(path, columns=FRAME_COLUMNS)
    df = table.to_pandas()
    df["date"] = day
    df = df[df["factor_eligible"].fillna(False)].copy()
    for col in [
        "best_bid_price",
        "best_ask_price",
        "mid",
        "spread_bps",
        "best_bid_amount",
        "best_ask_amount",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[
        (df["mid"] > 0.0)
        & (df["best_bid_price"] > 0.0)
        & (df["best_ask_price"] > 0.0)
        & (df["spread_bps"] >= 0.0)
    ].copy()
    df.sort_values("local_ts_us", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df, manifest


def enrich_runtime_features(df: pd.DataFrame, rolling_window: int, min_periods: int) -> pd.DataFrame:
    out = df.copy()
    bid_amt = pd.to_numeric(out["best_bid_amount"], errors="coerce").fillna(0.0).clip(lower=0.0)
    ask_amt = pd.to_numeric(out["best_ask_amount"], errors="coerce").fillna(0.0).clip(lower=0.0)
    top_depth = bid_amt + ask_amt
    out["top_depth"] = top_depth
    out["queue_imbalance"] = np.where(top_depth > 1e-12, (bid_amt - ask_amt) / top_depth, 0.0)
    out["abs_tfi"] = pd.to_numeric(out["trade_flow_imbalance"], errors="coerce").fillna(0.0).abs()
    out["tfi_sign"] = np.sign(pd.to_numeric(out["trade_flow_imbalance"], errors="coerce").fillna(0.0))
    out["past25"] = pd.to_numeric(out["past_event_25_bps"], errors="coerce").fillna(0.0)
    out["past25_sign"] = np.sign(out["past25"])
    out["abs_past25"] = out["past25"].abs()
    out["quote_refresh"] = (
        out["quote_change_prev"].fillna(False).astype(bool)
        | out["top_size_change_prev"].fillna(False).astype(bool)
    ).astype(float)
    out["quote_refresh_count_25"] = out["quote_refresh"].rolling(25, min_periods=1).sum()
    out["prior_trade_mean_25"] = (
        pd.to_numeric(out["trade_window_count"], errors="coerce").fillna(0.0)
        .shift(1)
        .rolling(25, min_periods=1)
        .mean()
    )

    def rolling_z(series: pd.Series, *, log: bool = False) -> pd.Series:
        value = series.astype(float)
        if log:
            value = np.log(value.clip(lower=1e-12))
        base = value.shift(1)
        mean = base.rolling(rolling_window, min_periods=min_periods).mean()
        std = base.rolling(rolling_window, min_periods=min_periods).std(ddof=0)
        return (value - mean) / std.replace(0.0, np.nan)

    out["spread_z"] = rolling_z(out["spread_bps"])
    out["depth_z"] = rolling_z(out["top_depth"], log=True)
    out["trade_count_z"] = rolling_z(pd.to_numeric(out["trade_window_count"], errors="coerce").fillna(0.0))
    out["abs_past25_z"] = rolling_z(out["abs_past25"])
    out["prior_trade_q30"] = (
        pd.to_numeric(out["trade_window_count"], errors="coerce")
        .fillna(0.0)
        .shift(1)
        .rolling(rolling_window, min_periods=min_periods)
        .quantile(0.30)
    )
    out["spread_q50"] = (
        out["spread_bps"]
        .shift(1)
        .rolling(rolling_window, min_periods=min_periods)
        .quantile(0.50)
    )
    return out


def side_from_rule(row: pd.Series, rule: str) -> int:
    tfi_sign = int(row.get("tfi_sign") or 0)
    past_sign = int(row.get("past25_sign") or 0)
    if rule == "same_as_tfi":
        return tfi_sign
    if rule == "opposite_tfi":
        return -tfi_sign
    if rule == "same_as_recent_mid_move":
        return past_sign
    if rule == "opposite_recent_mid_move":
        return -past_sign
    return 0


def side_from_state_machine_rule(base_row: pd.Series, entry_row: pd.Series, rule: str) -> int:
    base_tfi = int(base_row.get("tfi_sign") or 0)
    base_past = int(base_row.get("past25_sign") or 0)
    if rule == "same_as_base_tfi":
        return base_tfi
    if rule == "opposite_base_tfi":
        return -base_tfi
    if rule == "same_as_base_past_move":
        return base_past
    if rule == "opposite_base_past_move":
        return -base_past
    if rule == "same_as_entry_tfi":
        return int(entry_row.get("tfi_sign") or 0)
    return 0


def confirmation_passes(base_row: pd.Series, entry_row: pd.Series, spec: StateMachineSpec) -> bool:
    base_tfi = int(base_row.get("tfi_sign") or 0)
    entry_tfi = int(entry_row.get("tfi_sign") or 0)
    base_past = int(base_row.get("past25_sign") or 0)
    entry_past = int(entry_row.get("past25_sign") or 0)
    base_spread = float(base_row.get("spread_bps") or 0.0)
    entry_spread = float(entry_row.get("spread_bps") or 0.0)
    entry_spread_q50 = optional_float(entry_row.get("spread_q50"))
    entry_qi = float(entry_row.get("queue_imbalance") or 0.0)
    base_abs_tfi = float(base_row.get("abs_tfi") or 0.0)
    entry_abs_tfi = float(entry_row.get("abs_tfi") or 0.0)

    spread_repaired = entry_spread <= base_spread and (
        entry_spread_q50 is None or entry_spread <= entry_spread_q50
    )
    flow_persists = base_tfi != 0 and entry_tfi == base_tfi and entry_abs_tfi >= max(0.35, 0.5 * base_abs_tfi)
    move_persists = base_past != 0 and entry_past == base_past
    spread_not_worse = entry_spread <= base_spread
    absorption_holds = base_tfi != 0 and (base_tfi * entry_qi) <= -0.12
    absorption_breaks = base_tfi != 0 and (base_tfi * entry_qi) > -0.02

    if spec.confirmation == "spread_repaired_and_flow_persists":
        return spread_repaired and flow_persists
    if spec.confirmation == "flow_persists":
        return flow_persists
    if spec.confirmation == "move_persists_and_spread_not_worse":
        return move_persists and spread_not_worse
    if spec.confirmation == "spread_repaired":
        return spread_repaired
    if spec.confirmation == "absorption_breaks_and_flow_persists":
        return absorption_breaks and flow_persists
    if spec.confirmation == "absorption_holds":
        return absorption_holds
    if spec.confirmation == "flow_persists_and_spread_not_worse":
        return flow_persists and spread_not_worse
    return False


def event_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    tfi = pd.to_numeric(df["trade_flow_imbalance"], errors="coerce").fillna(0.0)
    qi = pd.to_numeric(df["queue_imbalance"], errors="coerce").fillna(0.0)
    quiet = df["prior_trade_mean_25"].fillna(np.inf) <= df["prior_trade_q30"].fillna(-np.inf)
    low_spread = df["spread_bps"] <= df["spread_q50"].fillna(-np.inf)
    spread_shock = (
            (df["spread_z"] >= 2.0)
            & (df["spread_bps"] >= 0.5)
            & (df["abs_past25"] >= 0.5)
            & (df["past25_sign"] != 0)
    )
    depth_collapse_flow = (
            (df["depth_z"] <= -2.0)
            & (df["abs_tfi"] >= 0.35)
            & (df["tfi_sign"] != 0)
    )
    trade_burst = (
            (df["trade_count_z"] >= 2.0)
            & (df["abs_tfi"] >= 0.35)
            & (df["tfi_sign"] != 0)
    )
    quote_refresh_burst = (
            (df["quote_refresh_count_25"] >= 10.0)
            & (df["abs_tfi"] >= 0.25)
            & (df["tfi_sign"] != 0)
    )
    sweep_after_quiet = (
            quiet
            & (df["trade_count_z"] >= 1.5)
            & (df["abs_tfi"] >= 0.45)
            & (df["tfi_sign"] != 0)
    )
    absorption = (
            (df["abs_tfi"] >= 0.45)
            & ((tfi * qi) <= -0.12)
            & (df["tfi_sign"] != 0)
    )
    volatility_expansion = (
            (df["abs_past25_z"] >= 2.0)
            & (df["abs_past25"] >= 1.0)
            & (df["spread_z"].fillna(0.0) < 2.5)
            & (df["past25_sign"] != 0)
    )
    vacuum = (
            (df["depth_z"] <= -1.5)
            & (df["spread_z"] >= 1.0)
            & (df["abs_past25"] >= 1.0)
            & (df["past25_sign"] != 0)
    )
    return {
        "spread_shock_reversion": spread_shock,
        "spread_shock_breakout": spread_shock,
        "depth_collapse_flow_continuation": depth_collapse_flow,
        "depth_collapse_flow_reversal": depth_collapse_flow,
        "depth_collapse_low_spread_continuation": depth_collapse_flow & low_spread,
        "trade_burst_continuation": trade_burst,
        "trade_burst_reversal": trade_burst,
        "trade_burst_low_spread_continuation": trade_burst & low_spread,
        "quote_refresh_burst_continuation": quote_refresh_burst,
        "quote_refresh_burst_reversal": quote_refresh_burst,
        "sweep_after_quiet_continuation": sweep_after_quiet,
        "sweep_after_quiet_reversal": sweep_after_quiet,
        "absorption_reversal": absorption,
        "absorption_continuation": absorption,
        "volatility_expansion_breakout": volatility_expansion,
        "volatility_expansion_reversal": volatility_expansion,
        "vacuum_reversal": vacuum,
        "vacuum_breakout": vacuum,
    }


def apply_refractory(df: pd.DataFrame, mask: pd.Series, refractory_us: int) -> list[int]:
    selected: list[int] = []
    last_ts: int | None = None
    indices = df.index[mask.fillna(False)].tolist()
    for idx in indices:
        ts = int(df.at[idx, "local_ts_us"])
        if last_ts is None or ts - last_ts >= refractory_us:
            selected.append(int(idx))
            last_ts = ts
    return selected


def taker_labels(
    *,
    side: int,
    entry_bid: float,
    entry_ask: float,
    entry_mid: float,
    exit_bid: float,
    exit_ask: float,
    exit_mid: float,
) -> dict[str, float]:
    if side > 0:
        mid_bps = math.log(exit_mid / entry_mid) * 10_000.0
        exe_bps = math.log(exit_bid / entry_ask) * 10_000.0
        entry_cross_bps = math.log(entry_ask / entry_mid) * 10_000.0
        exit_cross_bps = math.log(exit_mid / exit_bid) * 10_000.0
    else:
        mid_bps = math.log(entry_mid / exit_mid) * 10_000.0
        exe_bps = math.log(entry_bid / exit_ask) * 10_000.0
        entry_cross_bps = math.log(entry_mid / entry_bid) * 10_000.0
        exit_cross_bps = math.log(exit_ask / exit_mid) * 10_000.0
    return {
        "mid_bps": mid_bps,
        "executable_taker_bps": exe_bps,
        "spread_cost_bps": mid_bps - exe_bps,
        "entry_cross_bps": entry_cross_bps,
        "exit_cross_bps": exit_cross_bps,
    }


def build_event_rows(
    day: str,
    df: pd.DataFrame,
    quote_index: QuoteIndex,
    horizons_sec: list[int],
    refractory_us: int,
) -> list[dict[str, Any]]:
    specs = {spec.name: spec for spec in EVENT_SPECS}
    masks = event_masks(df)
    rows: list[dict[str, Any]] = []
    for family, mask in masks.items():
        spec = specs[family]
        for idx in apply_refractory(df, mask, refractory_us):
            row = df.loc[idx]
            side = side_from_rule(row, spec.direction)
            if side == 0:
                continue
            entry_bid = float(row["best_bid_price"])
            entry_ask = float(row["best_ask_price"])
            entry_mid = float(row["mid"])
            if min(entry_bid, entry_ask, entry_mid) <= 0.0:
                continue
            out: dict[str, Any] = {
                "date": day,
                "family": family,
                "mechanism_class": mechanism_class(family),
                "description": spec.description,
                "direction_rule": spec.direction,
                "side": "buy" if side > 0 else "sell",
                "side_sign": side,
                "strict_migration": spec.strict_migration,
                "observed_seq": optional_int(row.get("observed_seq")),
                "local_ts_us": int(row["local_ts_us"]),
                "event_index": optional_int(row.get("event_index")),
                "entry_bid": entry_bid,
                "entry_ask": entry_ask,
                "entry_mid": entry_mid,
                "entry_spread_bps": float(row.get("spread_bps") or 0.0),
                "top_depth": float(row.get("top_depth") or 0.0),
                "queue_imbalance": float(row.get("queue_imbalance") or 0.0),
                "trade_window_count": int(row.get("trade_window_count") or 0),
                "trade_flow_imbalance": float(row.get("trade_flow_imbalance") or 0.0),
                "frames_since_mid_change": float(row.get("frames_since_mid_change") or 0.0),
                "past_event_25_bps": float(row.get("past_event_25_bps") or 0.0),
                "spread_z": optional_float(row.get("spread_z")),
                "depth_z": optional_float(row.get("depth_z")),
                "trade_count_z": optional_float(row.get("trade_count_z")),
                "abs_past25_z": optional_float(row.get("abs_past25_z")),
                "quote_refresh_count_25": float(row.get("quote_refresh_count_25") or 0.0),
            }
            for horizon in horizons_sec:
                quote = quote_index.at_or_before(int(row["local_ts_us"]) + horizon * 1_000_000)
                if quote is None:
                    continue
                exit_bid = float(quote["bid"])
                exit_ask = float(quote["ask"])
                exit_mid = float(quote["mid"])
                if min(exit_bid, exit_ask, exit_mid) <= 0.0:
                    continue
                labels = taker_labels(
                    side=side,
                    entry_bid=entry_bid,
                    entry_ask=entry_ask,
                    entry_mid=entry_mid,
                    exit_bid=exit_bid,
                    exit_ask=exit_ask,
                    exit_mid=exit_mid,
                )
                prefix = f"h{horizon}s"
                out[f"{prefix}_mid_bps"] = labels["mid_bps"]
                out[f"{prefix}_executable_taker_bps"] = labels["executable_taker_bps"]
                out[f"{prefix}_spread_cost_bps"] = labels["spread_cost_bps"]
                out[f"{prefix}_entry_cross_bps"] = labels["entry_cross_bps"]
                out[f"{prefix}_exit_cross_bps"] = labels["exit_cross_bps"]
            rows.append(out)
    return rows


def build_state_machine_rows(
    day: str,
    df: pd.DataFrame,
    quote_index: QuoteIndex,
    horizons_sec: list[int],
    waits_sec: list[int],
    refractory_us: int,
) -> list[dict[str, Any]]:
    event_spec_by_name = {spec.name: spec for spec in EVENT_SPECS}
    masks = event_masks(df)
    frame_index = FrameIndex(df)
    rows: list[dict[str, Any]] = []
    for spec in STATE_MACHINE_SPECS:
        base_event_spec = event_spec_by_name[spec.base_family]
        base_mask = masks[spec.base_family]
        for base_idx in apply_refractory(df, base_mask, refractory_us):
            base_row = df.loc[base_idx]
            base_side = side_from_rule(base_row, base_event_spec.direction)
            if base_side == 0:
                continue
            base_ts = int(base_row["local_ts_us"])
            base_spread = float(base_row.get("spread_bps") or 0.0)
            for wait in waits_sec:
                entry_row = frame_index.at_or_before(base_ts + wait * 1_000_000)
                if entry_row is None:
                    continue
                entry_ts = int(entry_row["local_ts_us"])
                if entry_ts <= base_ts:
                    continue
                if not confirmation_passes(base_row, entry_row, spec):
                    continue
                side = side_from_state_machine_rule(base_row, entry_row, spec.direction)
                if side == 0:
                    continue
                entry_bid = float(entry_row["best_bid_price"])
                entry_ask = float(entry_row["best_ask_price"])
                entry_mid = float(entry_row["mid"])
                if min(entry_bid, entry_ask, entry_mid) <= 0.0:
                    continue
                out: dict[str, Any] = {
                    "date": day,
                    "family": f"{spec.name}_w{wait}s",
                    "base_family": spec.base_family,
                    "mechanism_class": spec.mechanism_class,
                    "description": spec.description,
                    "direction_rule": spec.direction,
                    "confirmation_rule": spec.confirmation,
                    "wait_sec": wait,
                    "side": "buy" if side > 0 else "sell",
                    "side_sign": side,
                    "strict_migration": spec.strict_migration,
                    "observed_seq": optional_int(entry_row.get("observed_seq")),
                    "base_local_ts_us": base_ts,
                    "local_ts_us": entry_ts,
                    "event_index": optional_int(entry_row.get("event_index")),
                    "base_entry_spread_bps": base_spread,
                    "entry_bid": entry_bid,
                    "entry_ask": entry_ask,
                    "entry_mid": entry_mid,
                    "entry_spread_bps": float(entry_row.get("spread_bps") or 0.0),
                    "top_depth": float(entry_row.get("top_depth") or 0.0),
                    "queue_imbalance": float(entry_row.get("queue_imbalance") or 0.0),
                    "trade_window_count": int(entry_row.get("trade_window_count") or 0),
                    "trade_flow_imbalance": float(entry_row.get("trade_flow_imbalance") or 0.0),
                    "frames_since_mid_change": float(entry_row.get("frames_since_mid_change") or 0.0),
                    "past_event_25_bps": float(entry_row.get("past_event_25_bps") or 0.0),
                    "spread_z": optional_float(entry_row.get("spread_z")),
                    "depth_z": optional_float(entry_row.get("depth_z")),
                    "trade_count_z": optional_float(entry_row.get("trade_count_z")),
                    "abs_past25_z": optional_float(entry_row.get("abs_past25_z")),
                    "quote_refresh_count_25": float(entry_row.get("quote_refresh_count_25") or 0.0),
                }
                for horizon in horizons_sec:
                    quote = quote_index.at_or_before(entry_ts + horizon * 1_000_000)
                    if quote is None:
                        continue
                    exit_bid = float(quote["bid"])
                    exit_ask = float(quote["ask"])
                    exit_mid = float(quote["mid"])
                    if min(exit_bid, exit_ask, exit_mid) <= 0.0:
                        continue
                    labels = taker_labels(
                        side=side,
                        entry_bid=entry_bid,
                        entry_ask=entry_ask,
                        entry_mid=entry_mid,
                        exit_bid=exit_bid,
                        exit_ask=exit_ask,
                        exit_mid=exit_mid,
                    )
                    prefix = f"h{horizon}s"
                    out[f"{prefix}_mid_bps"] = labels["mid_bps"]
                    out[f"{prefix}_executable_taker_bps"] = labels["executable_taker_bps"]
                    out[f"{prefix}_spread_cost_bps"] = labels["spread_cost_bps"]
                    out[f"{prefix}_entry_cross_bps"] = labels["entry_cross_bps"]
                    out[f"{prefix}_exit_cross_bps"] = labels["exit_cross_bps"]
                rows.append(out)
    return rows


def concurrency_stats(events: pd.DataFrame, horizon_sec: int) -> dict[str, float]:
    if events.empty:
        return {"max_concurrency": 0.0, "p95_concurrency": 0.0}
    points: list[tuple[int, int]] = []
    horizon_us = horizon_sec * 1_000_000
    for ts in events["local_ts_us"].astype("int64"):
        points.append((int(ts), 1))
        points.append((int(ts) + horizon_us, -1))
    points.sort(key=lambda item: (item[0], item[1]))
    current = 0
    values: list[int] = []
    max_concurrency = 0
    for _, delta in points:
        current += delta
        max_concurrency = max(max_concurrency, current)
        values.append(current)
    return {
        "max_concurrency": float(max_concurrency),
        "p95_concurrency": float(np.quantile(values, 0.95)) if values else 0.0,
    }


def summarize_events(events: pd.DataFrame, horizons_sec: list[int], min_events: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    if events.empty:
        return summary, candidates
    for family, group in events.groupby("family", sort=True):
        for horizon in horizons_sec:
            exe_col = f"h{horizon}s_executable_taker_bps"
            mid_col = f"h{horizon}s_mid_bps"
            spread_col = f"h{horizon}s_spread_cost_bps"
            valid = group.dropna(subset=[exe_col, mid_col]).copy()
            if valid.empty:
                continue
            daily = valid.groupby("date")[exe_col].sum()
            conc = concurrency_stats(valid, horizon)
            n = int(len(valid))
            mean_exe = float(valid[exe_col].mean())
            worst_day = float(daily.min())
            hit_rate = float((valid[exe_col] > 0.0).mean())
            row = {
                "mechanism_class": str(valid["mechanism_class"].iloc[0])
                if "mechanism_class" in valid.columns
                else mechanism_class(family),
                "family": family,
                "horizon_sec": horizon,
                "n": n,
                "days": int(valid["date"].nunique()),
                "long_count": int((valid["side_sign"] > 0).sum()),
                "short_count": int((valid["side_sign"] < 0).sum()),
                "mean_mid_bps": float(valid[mid_col].mean()),
                "mean_executable_taker_bps": mean_exe,
                "median_executable_taker_bps": float(valid[exe_col].median()),
                "p25_executable_taker_bps": float(valid[exe_col].quantile(0.25)),
                "p75_executable_taker_bps": float(valid[exe_col].quantile(0.75)),
                "hit_rate": hit_rate,
                "total_executable_taker_bps": float(valid[exe_col].sum()),
                "worst_day_executable_taker_bps": worst_day,
                "mean_spread_cost_bps": float(valid[spread_col].mean()),
                "mean_entry_spread_bps": float(valid["entry_spread_bps"].mean()),
                "p25_entry_spread_bps": float(valid["entry_spread_bps"].quantile(0.25)),
                "p75_entry_spread_bps": float(valid["entry_spread_bps"].quantile(0.75)),
                "mean_top_depth": float(valid["top_depth"].mean()),
                "p25_top_depth": float(valid["top_depth"].quantile(0.25)),
                "p75_top_depth": float(valid["top_depth"].quantile(0.75)),
                "mean_abs_tfi": float(valid["trade_flow_imbalance"].abs().mean()),
                "p25_abs_tfi": float(valid["trade_flow_imbalance"].abs().quantile(0.25)),
                "p75_abs_tfi": float(valid["trade_flow_imbalance"].abs().quantile(0.75)),
                "mean_queue_imbalance": float(valid["queue_imbalance"].mean()),
                "p25_queue_imbalance": float(valid["queue_imbalance"].quantile(0.25)),
                "p75_queue_imbalance": float(valid["queue_imbalance"].quantile(0.75)),
                "max_concurrency": conc["max_concurrency"],
                "p95_concurrency": conc["p95_concurrency"],
                "strict_migration": str(valid["strict_migration"].iloc[0]),
            }
            row["candidate_score"] = candidate_score(row, min_events)
            status, reason = promotion_status(row, min_events)
            row["promotion_status"] = status
            row["promotion_reason"] = reason
            summary.append(row)
            if n >= min_events:
                candidates.append(row)
    candidates.sort(key=lambda row: (float(row["candidate_score"]), float(row["mean_executable_taker_bps"])), reverse=True)
    return summary, candidates


def summarize_mechanisms(summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in summary:
        key = (str(row["mechanism_class"]), int(row["horizon_sec"]))
        by_key.setdefault(key, []).append(row)

    out: list[dict[str, Any]] = []
    for (mechanism, horizon), rows in sorted(by_key.items()):
        best = max(rows, key=lambda row: float(row["mean_executable_taker_bps"]))
        out.append(
            {
                "mechanism_class": mechanism,
                "horizon_sec": horizon,
                "family_count": len({str(row["family"]) for row in rows}),
                "positive_family_count": sum(1 for row in rows if float(row["mean_executable_taker_bps"]) > 0.0),
                "rejected_spread_cost_mirage_count": sum(
                    1 for row in rows if row.get("promotion_status") == "rejected_spread_cost_mirage"
                ),
                "rejected_negative_edge_count": sum(
                    1 for row in rows if row.get("promotion_status") == "rejected_negative_edge"
                ),
                "best_family": best["family"],
                "best_status": best["promotion_status"],
                "best_mean_mid_bps": best["mean_mid_bps"],
                "best_mean_executable_taker_bps": best["mean_executable_taker_bps"],
                "best_median_executable_taker_bps": best["median_executable_taker_bps"],
                "best_hit_rate": best["hit_rate"],
                "best_worst_day_executable_taker_bps": best["worst_day_executable_taker_bps"],
                "best_mean_spread_cost_bps": best["mean_spread_cost_bps"],
                "max_concurrency": max(float(row["max_concurrency"]) for row in rows),
                "strict_migration": best["strict_migration"],
            }
        )
    return out


def candidate_score(row: dict[str, Any], min_events: int) -> float:
    n = int(row["n"])
    if n < min_events:
        return -1e9
    mean_exe = float(row["mean_executable_taker_bps"])
    hit_rate = float(row["hit_rate"])
    worst_day = float(row["worst_day_executable_taker_bps"])
    sample_bonus = min(math.sqrt(n / max(1, min_events)), 4.0)
    worst_penalty = min(0.0, worst_day) / 25.0
    return mean_exe * sample_bonus + (hit_rate - 0.5) * 2.0 + worst_penalty


def promotion_status(row: dict[str, Any], min_events: int) -> tuple[str, str]:
    n = int(row["n"])
    if n < min_events:
        return "insufficient_sample", f"n<{min_events}"

    mean_mid = float(row["mean_mid_bps"])
    mean_exe = float(row["mean_executable_taker_bps"])
    median_exe = float(row["median_executable_taker_bps"])
    hit_rate = float(row["hit_rate"])
    worst_day = float(row["worst_day_executable_taker_bps"])

    if mean_exe <= 0.0:
        if mean_mid > 0.0:
            return "rejected_spread_cost_mirage", "mid label is positive but executable taker label is non-positive"
        return "rejected_negative_edge", "both direction and executable economics are weak"

    if median_exe > 0.0 and hit_rate >= 0.5 and worst_day >= 0.0:
        return "promote_candidate", "positive mean/median executable label, hit rate >= 50%, and no negative day"

    reasons: list[str] = ["positive mean executable label"]
    if median_exe <= 0.0:
        reasons.append("median is still negative")
    if hit_rate < 0.5:
        reasons.append("hit rate is below 50%")
    if worst_day < 0.0:
        reasons.append("worst day is negative")
    return "weak_candidate_strict_required", "; ".join(reasons)


def select_family_candidates(candidates: list[dict[str, Any]], preferred_horizon: int, max_candidates: int = 5) -> list[dict[str, Any]]:
    by_family: dict[str, dict[str, Any]] = {}
    for row in candidates:
        if str(row.get("promotion_status")) not in {"promote_candidate", "weak_candidate_strict_required"}:
            continue
        family = str(row["family"])
        existing = by_family.get(family)
        if existing is None:
            by_family[family] = row
            continue
        row_h = int(row["horizon_sec"])
        old_h = int(existing["horizon_sec"])
        row_key = (float(row["candidate_score"]), row_h == preferred_horizon)
        old_key = (float(existing["candidate_score"]), old_h == preferred_horizon)
        if row_key > old_key:
            by_family[family] = row
    selected = list(by_family.values())
    selected.sort(key=lambda row: float(row["candidate_score"]), reverse=True)
    return selected[:max_candidates]


def select_rejected_controls(candidates: list[dict[str, Any]], max_controls: int = 8) -> list[dict[str, Any]]:
    controls = [
        row
        for row in candidates
        if str(row.get("promotion_status", "")).startswith("rejected_")
    ]
    controls.sort(key=lambda row: float(row["candidate_score"]), reverse=True)
    return controls[:max_controls]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_events_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def format_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number) or math.isinf(number):
        return ""
    return f"{number:.{digits}f}"


def rule_draft(family: str) -> str:
    rules = {
        "spread_shock_reversion": "If rolling spread z-score >= 2 and recent 25-frame mid move is non-trivial, trade opposite the recent move; reject if entry spread exceeds prior-date q70.",
        "spread_shock_breakout": "If rolling spread z-score >= 2 and recent 25-frame mid move is non-trivial, trade with the recent move; treat as a breakout control against spread-shock reversion.",
        "depth_collapse_flow_continuation": "If top depth collapses versus rolling history and TFI is strongly signed, trade with TFI for a short taker horizon.",
        "depth_collapse_flow_reversal": "If top depth collapses versus rolling history and TFI is strongly signed, fade TFI and test exhaustion.",
        "depth_collapse_low_spread_continuation": "If top depth collapses with signed TFI while spread is below rolling median, trade with TFI; this is the taker-viable vacuum subset.",
        "trade_burst_continuation": "If trade intensity jumps above rolling baseline and TFI is strongly signed, trade with TFI; throttle repeated triggers with a 5s refractory window.",
        "trade_burst_reversal": "If trade intensity jumps above rolling baseline and TFI is strongly signed, fade TFI; this is an exhaustion control.",
        "trade_burst_low_spread_continuation": "If trade intensity jumps with signed TFI while spread is below rolling median, trade with TFI.",
        "quote_refresh_burst_continuation": "If quote/top-size refresh count over 25 frames is high and TFI is signed, trade with TFI; validate in strict full-stream because refresh semantics depend on L2 updates.",
        "quote_refresh_burst_reversal": "If quote/top-size refresh count over 25 frames is high and TFI is signed, fade TFI; tests quote-refresh exhaustion.",
        "sweep_after_quiet_continuation": "If a quiet prior book is followed by a signed trade burst, trade with the burst direction and test 5s/20s exits first.",
        "sweep_after_quiet_reversal": "If a quiet prior book is followed by a signed trade burst, fade the first burst; tests sweep absorption.",
        "absorption_reversal": "If aggressive flow is strong but queue imbalance leans against it, trade opposite the aggressive flow; require executable label to beat spread before promotion.",
        "absorption_continuation": "If aggressive flow is strong but queue imbalance leans against it, trade with aggressive flow; this is the control for absorption reversal.",
        "volatility_expansion_breakout": "If recent mid move z-score expands sharply without an extreme spread shock, trade with recent move direction.",
        "volatility_expansion_reversal": "If recent mid move z-score expands sharply without an extreme spread shock, trade opposite the recent move; tests post-expansion reversion.",
        "vacuum_reversal": "If top depth is thin and spread is wide after a recent mid move, trade opposite the move; treat as fragile until strict taker cost passes.",
        "vacuum_breakout": "If top depth is thin and spread is wide after a recent mid move, trade with the move; this is the breakout control for vacuum reversal.",
    }
    return rules.get(family, "Runtime-safe rule draft not specified.")


def write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    out_dir: Path,
    source_manifests: list[dict[str, Any]],
    mechanism_summary: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    rejected_controls: list[dict[str, Any]],
    event_count: int,
    elapsed_ms: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# CCUSDT Event / Regime Discovery v0.1")
    lines.append("")
    lines.append("This is a fast diagnostic for new strategy-family discovery. It does not tune the existing TFI/R5/exit policy and it does not enable maker execution.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Symbol: `{args.symbol}`")
    lines.append(f"- Dates: `{args.from_date}` .. `{args.to_date}`")
    lines.append(f"- Horizons: `{args.horizons_sec}` seconds")
    lines.append(f"- Refractory: `{args.refractory_us}` us per family/day")
    lines.append(f"- Event rows: `{event_count}`")
    lines.append(f"- Output directory: `{out_dir}`")
    lines.append(f"- Elapsed wall time: `{elapsed_ms}` ms")
    lines.append("")
    lines.append("Labels are computed from top-of-book executable taker prices:")
    lines.append("")
    lines.append("```text")
    lines.append("long  executable = 10000 * log(exit_bid / entry_ask)")
    lines.append("short executable = 10000 * log(entry_bid / exit_ask)")
    lines.append("mid label        = same direction log return on mid")
    lines.append("spread cost      = mid label - executable label")
    lines.append("```")
    lines.append("")
    lines.append("## Mechanism-Level Map")
    lines.append("")
    lines.append("This section is the first-principles layer: it groups local triggers by the market mechanism they are trying to capture. A mechanism can be economically real on mid but still fail as a taker strategy after crossing spread.")
    lines.append("")
    lines.append("| mechanism | h | positive rows | best family | best status | best mean exe | best median exe | hit | worst day | spread cost | max conc |")
    lines.append("|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for row in mechanism_summary:
        lines.append(
            "| {mechanism} | {horizon_sec} | {positive} | {family} | {status} | {mean} | {median} | {hit} | {worst} | {spread} | {conc} |".format(
                mechanism=row["mechanism_class"],
                horizon_sec=row["horizon_sec"],
                positive=row["positive_family_count"],
                family=row["best_family"],
                status=row["best_status"],
                mean=format_float(row["best_mean_executable_taker_bps"]),
                median=format_float(row["best_median_executable_taker_bps"]),
                hit=format_float(row["best_hit_rate"]),
                worst=format_float(row["best_worst_day_executable_taker_bps"]),
                spread=format_float(row["best_mean_spread_cost_bps"]),
                conc=format_float(row["max_concurrency"], 1),
            )
        )
    lines.append("")
    lines.append("## Candidate Strategy Families")
    lines.append("")
    if not selected:
        lines.append("No family passed the positive executable-taker candidate gate.")
    else:
        lines.append("| status | mechanism | family | horizon | n | mean exe | median exe | hit | worst day | spread cost | max conc | score |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in selected:
            lines.append(
                "| {status} | {mechanism} | {family} | {horizon_sec} | {n} | {mean} | {median} | {hit} | {worst} | {spread} | {conc} | {score} |".format(
                    status=row["promotion_status"],
                    mechanism=row["mechanism_class"],
                    family=row["family"],
                    horizon_sec=row["horizon_sec"],
                    n=row["n"],
                    mean=format_float(row["mean_executable_taker_bps"]),
                    median=format_float(row["median_executable_taker_bps"]),
                    hit=format_float(row["hit_rate"]),
                    worst=format_float(row["worst_day_executable_taker_bps"]),
                    spread=format_float(row["mean_spread_cost_bps"]),
                    conc=format_float(row["max_concurrency"], 1),
                    score=format_float(row["candidate_score"]),
                )
            )
        lines.append("")
        lines.append("None of the selected families is a clean promotion yet. They are positive-mean executable-taker mechanisms that still need strict replay, day split, and capacity validation.")
    lines.append("")
    lines.append("## Rejected Controls")
    lines.append("")
    if not rejected_controls:
        lines.append("No rejected control rows were selected for display.")
    else:
        lines.append("| status | mechanism | family | horizon | n | mean mid | mean exe | hit | spread cost | reason |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|")
        for row in rejected_controls:
            lines.append(
                "| {status} | {mechanism} | {family} | {horizon_sec} | {n} | {mid} | {exe} | {hit} | {spread} | {reason} |".format(
                    status=row["promotion_status"],
                    mechanism=row["mechanism_class"],
                    family=row["family"],
                    horizon_sec=row["horizon_sec"],
                    n=row["n"],
                    mid=format_float(row["mean_mid_bps"]),
                    exe=format_float(row["mean_executable_taker_bps"]),
                    hit=format_float(row["hit_rate"]),
                    spread=format_float(row["mean_spread_cost_bps"]),
                    reason=row["promotion_reason"],
                )
            )
    lines.append("")
    lines.append("## Runtime-Safe Rule Drafts")
    lines.append("")
    for row in selected:
        family = str(row["family"])
        lines.append(f"### {family}")
        lines.append("")
        lines.append(f"- Rule draft: {rule_draft(family)}")
        lines.append(f"- Direction rule: `{next((s.direction for s in EVENT_SPECS if s.name == family), '')}`")
        lines.append(
            "- Condition distribution: "
            f"entry_spread p25/p75={format_float(row.get('p25_entry_spread_bps'))}/{format_float(row.get('p75_entry_spread_bps'))} bps; "
            f"top_depth p25/p75={format_float(row.get('p25_top_depth'))}/{format_float(row.get('p75_top_depth'))}; "
            f"abs_tfi p25/p75={format_float(row.get('p25_abs_tfi'))}/{format_float(row.get('p75_abs_tfi'))}; "
            f"queue_imbalance p25/p75={format_float(row.get('p25_queue_imbalance'))}/{format_float(row.get('p75_queue_imbalance'))}."
        )
        lines.append(f"- Strict gate: `{row.get('strict_migration')}`")
        lines.append("- Next strict replay: implement as a sparse admission/intent profile, then compare fast event timestamps, side, entry bid/ask, capacity, fills, and executable PnL decomposition.")
        lines.append("")
    lines.append("## Full Family Summary")
    lines.append("")
    lines.append("| status | mechanism | family | h | n | mean mid | mean exe | hit | worst day | mean spread cost | p95 conc |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in sorted(summary, key=lambda item: (str(item["family"]), int(item["horizon_sec"]))):
        lines.append(
            "| {status} | {mechanism} | {family} | {horizon_sec} | {n} | {mid} | {exe} | {hit} | {worst} | {spread} | {conc} |".format(
                status=row["promotion_status"],
                mechanism=row["mechanism_class"],
                family=row["family"],
                horizon_sec=row["horizon_sec"],
                n=row["n"],
                mid=format_float(row["mean_mid_bps"]),
                exe=format_float(row["mean_executable_taker_bps"]),
                hit=format_float(row["hit_rate"]),
                worst=format_float(row["worst_day_executable_taker_bps"]),
                spread=format_float(row["mean_spread_cost_bps"]),
                conc=format_float(row["p95_concurrency"], 1),
            )
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- This pass is deliberately a strategy-family discovery pass, not a promotion gate.")
    lines.append("- Positive mid label with negative executable label means the family is likely a spread-cost mirage.")
    lines.append("- Positive executable label is not enough for promotion; median, hit rate, worst-day, capacity overlap, and strict replay identity still matter.")
    lines.append("- A rejected control is useful evidence: it tells us which intuitive market mechanisms do not survive top-of-book crossing.")
    lines.append("- All event triggers here use decision-frame-visible fields. Future labels are diagnostics only and must not enter the Bot.")
    lines.append("- Maker execution is intentionally not modeled in this pass.")
    lines.append("")
    lines.append("## Source Manifests")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(source_manifests, ensure_ascii=False, indent=2)[:12000])
    lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    horizons_sec = [int(part.strip()) for part in args.horizons_sec.split(",") if part.strip()]
    if not horizons_sec:
        raise ValueError("at least one horizon is required")
    out_dir = args.out_dir
    if out_dir is None:
        out_dir = DEFAULT_OUT_ROOT / f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_v0_1"
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    event_rows: list[dict[str, Any]] = []
    source_manifests: list[dict[str, Any]] = []
    for day in date_range(args.from_date, args.to_date):
        print(f"event_regime_discovery day={day}", file=sys.stderr, flush=True)
        frames, manifest = load_decision_frames(repo_root, args.symbol, day)
        quote_index = QuoteIndex.load(repo_root, args.symbol, day)
        enriched = enrich_runtime_features(frames, args.rolling_window, args.min_rolling_periods)
        day_rows = build_event_rows(day, enriched, quote_index, horizons_sec, args.refractory_us)
        event_rows.extend(day_rows)
        source_manifests.append(
            {
                "date": day,
                "decision_frame_manifest": {
                    "path": str(decision_manifest_path(repo_root, args.symbol, day)),
                    "row_count": manifest.get("row_count"),
                    "field_hash_sha256": manifest.get("field_hash_sha256"),
                    "builder_version": manifest.get("builder_version"),
                    "schema_version": manifest.get("schema_version"),
                },
                "quote_frame_path": str(quote_path(repo_root, args.symbol, day)),
                "events_extracted": len(day_rows),
            }
        )

    events = pd.DataFrame(event_rows)
    summary_rows, candidate_rows = summarize_events(events, horizons_sec, args.min_events)
    mechanism_rows = summarize_mechanisms(summary_rows)
    selected = select_family_candidates(candidate_rows, args.candidate_horizon_sec)
    rejected_controls = select_rejected_controls(candidate_rows)
    elapsed_ms = int((time.time() - started) * 1000)

    write_csv(out_dir / "event_family_summary.csv", summary_rows)
    write_csv(out_dir / "mechanism_summary.csv", mechanism_rows)
    write_csv(out_dir / "candidate_families.csv", selected)
    write_csv(out_dir / "rejected_controls.csv", rejected_controls)
    if args.write_events:
        write_events_parquet(out_dir / "events.parquet", event_rows)

    summary_json = {
        "schema_id": "ccusdt_event_regime_discovery_summary_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "horizons_sec": horizons_sec,
        "event_count": len(event_rows),
        "family_summary_rows": len(summary_rows),
        "mechanism_summary_rows": len(mechanism_rows),
        "candidate_count": len(selected),
        "rejected_control_count": len(rejected_controls),
        "out_dir": str(out_dir),
        "report_path": str(report_path),
        "elapsed_wall_ms": elapsed_ms,
        "source_manifests": source_manifests,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(
        report_path,
        args=args,
        out_dir=out_dir,
        source_manifests=source_manifests,
        mechanism_summary=mechanism_rows,
        summary=summary_rows,
        selected=selected,
        rejected_controls=rejected_controls,
        event_count=len(event_rows),
        elapsed_ms=elapsed_ms,
    )
    print(json.dumps(summary_json, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
