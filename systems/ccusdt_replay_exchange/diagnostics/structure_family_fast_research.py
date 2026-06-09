#!/usr/bin/env python
"""Research-only fast scan for CCUSDT microstructure structure families.

This script reads market-derived decision_frame_v1 plus canonical quote_frame_v1
top-of-book prices. It evaluates deterministic structure-family variants from
the structure-family map. Future path labels are computed inside this diagnostic
only; they must not become Runner or Bot runtime inputs.
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
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import event_regime_discovery as egd


DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/structure_family_fast_research")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/strategy/v1-structure-family-fast-research-20260601.md")


@dataclass(frozen=True)
class VariantSpec:
    family_id: str
    variant_id: str
    role: str
    mechanism: str
    direction_rule: str
    runtime_safe_status: str
    notes: str


VARIANTS = [
    VariantSpec(
        "S1_active_flow_stale_release",
        "S1_tfi_follow_flat",
        "entry-alpha",
        "Signed TFI while recent price movement is still small.",
        "same_as_tfi",
        "decision_frame_safe_r5_unavailable_proxy_only",
        "Old four-cell trigger layer without Bot-owned closed R5.",
    ),
    VariantSpec(
        "S1_active_flow_stale_release",
        "S1_tfi_follow_flat_stale31",
        "entry-alpha",
        "Signed TFI, flat recent price, and stale mid.",
        "same_as_tfi",
        "decision_frame_safe_r5_unavailable_proxy_only",
        "Closest decision-frame proxy for the old stale-release structure.",
    ),
    VariantSpec(
        "S1_active_flow_stale_release",
        "S1_tfi_event_stale25",
        "entry-alpha",
        "Signed TFI with active trades while mid has been stale.",
        "same_as_tfi",
        "decision_frame_safe_r5_unavailable_proxy_only",
        "Tests event-active stale release without closed R5.",
    ),
    VariantSpec(
        "S2_flow_book_confirmation",
        "S2_tfi_queue_confirm",
        "entry-alpha",
        "Signed TFI confirmed by same-side top-of-book queue imbalance.",
        "same_as_tfi",
        "decision_frame_safe_l1_proxy_for_ofi_mlofi",
        "Decision-frame proxy for flow-book confirmation.",
    ),
    VariantSpec(
        "S2_flow_book_confirmation",
        "S2_tfi_microprice_confirm",
        "entry-alpha",
        "Signed TFI confirmed by microprice displacement.",
        "same_as_tfi",
        "decision_frame_safe_l1_proxy_for_ofi_mlofi",
        "Decision-frame proxy for microprice confirmation.",
    ),
    VariantSpec(
        "S2_flow_book_confirmation",
        "S2_tfi_queue_divergence_control",
        "control",
        "Signed TFI opposed by visible queue imbalance.",
        "same_as_tfi",
        "decision_frame_safe_l1_proxy_for_absorption",
        "Control row for failed confirmation.",
    ),
    VariantSpec(
        "S3_liquidity_vacuum_release",
        "S3_depth_collapse_tfi",
        "release-only",
        "Depth collapses while signed flow is present.",
        "same_as_tfi",
        "decision_frame_safe_top_depth_proxy",
        "Tests whether low resistance produces fast release.",
    ),
    VariantSpec(
        "S3_liquidity_vacuum_release",
        "S3_low_depth_low_spread_tfi",
        "entry-alpha",
        "Low top depth, low spread, and signed flow.",
        "same_as_tfi",
        "decision_frame_safe_top_depth_proxy",
        "Taker-viable subset of the vacuum idea.",
    ),
    VariantSpec(
        "S3_liquidity_vacuum_release",
        "S3_vacuum_recent_breakout",
        "release-only",
        "Thin depth and wider spread after a recent move.",
        "same_as_recent_mid_move",
        "decision_frame_safe_top_depth_proxy",
        "Fragile vacuum continuation probe.",
    ),
    VariantSpec(
        "S4_absorption_failed_continuation",
        "S4_absorption_continuation_test",
        "decay-risk",
        "Strong flow pushes against visible queue pressure; test continuation.",
        "same_as_tfi",
        "decision_frame_safe_l1_proxy_for_absorption",
        "Continuation is expected to be fragile if absorption holds.",
    ),
    VariantSpec(
        "S4_absorption_failed_continuation",
        "S4_absorption_reversal_test",
        "control",
        "Strong flow pushes against visible queue pressure; test fade.",
        "opposite_tfi",
        "decision_frame_safe_l1_proxy_for_absorption",
        "Reversal control for absorption.",
    ),
    VariantSpec(
        "S4_absorption_failed_continuation",
        "S4_stale_absorption_suppressor",
        "decay-risk",
        "Stale signed flow with queue pressure against the flow.",
        "same_as_tfi",
        "decision_frame_safe_l1_proxy_for_absorption",
        "Candidate suppressor for stale-release entries.",
    ),
    VariantSpec(
        "S6_execution_cost_admission",
        "S6_s1_low_spread_admission",
        "cost-filter",
        "S1 flat-flow candidates admitted only under low spread.",
        "same_as_tfi",
        "decision_frame_safe_quote_cost_gate",
        "Cost filter applied to the S1 trigger layer.",
    ),
    VariantSpec(
        "S6_execution_cost_admission",
        "S6_s3_low_spread_admission",
        "cost-filter",
        "S3 depth-collapse candidates admitted only under low spread.",
        "same_as_tfi",
        "decision_frame_safe_quote_cost_gate",
        "Cost filter applied to the S3 vacuum layer.",
    ),
    VariantSpec(
        "S6_execution_cost_admission",
        "S6_low_spread_tfi_control",
        "cost-filter",
        "Generic low-spread signed TFI control.",
        "same_as_tfi",
        "decision_frame_safe_quote_cost_gate",
        "Checks whether low spread alone rescues signed flow.",
    ),
    VariantSpec(
        "S7_volatility_decay_risk",
        "S7_past_event_continuation",
        "decay-risk",
        "Large recent move continuation probe.",
        "same_as_recent_mid_move",
        "decision_frame_safe_volatility_control",
        "Tests chase/continuation after realized movement.",
    ),
    VariantSpec(
        "S7_volatility_decay_risk",
        "S7_trade_burst_decay_probe",
        "decay-risk",
        "Trade-count expansion with signed TFI.",
        "same_as_tfi",
        "decision_frame_safe_trade_count_control",
        "Expected to capture volatility and possible decay risk.",
    ),
    VariantSpec(
        "S7_volatility_decay_risk",
        "S7_spread_shock_breakout",
        "decay-risk",
        "Wide spread shock after a recent move.",
        "same_as_recent_mid_move",
        "decision_frame_safe_spread_control",
        "Tests whether spread shock is signal or just crossing cost.",
    ),
]


SPEC_BY_VARIANT = {spec.variant_id: spec for spec in VARIANTS}


class QuoteBook:
    def __init__(self, rows: list[dict[str, float | int]]) -> None:
        if not rows:
            raise ValueError("quote_frame_v1 index is empty")
        self.rows = rows
        self.ts = np.array([int(row["local_ts_us"]) for row in rows], dtype=np.int64)
        self.bid = np.array([float(row["bid"]) for row in rows], dtype=float)
        self.ask = np.array([float(row["ask"]) for row in rows], dtype=float)
        self.mid = np.array([float(row["mid"]) for row in rows], dtype=float)

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteBook":
        rows: list[dict[str, float | int]] = []
        with gzip.open(egd.quote_path(repo_root, symbol, day), "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                ts = int(raw.get("local_ts_us") or 0)
                bid = egd.optional_float(raw.get("bid_px"))
                ask = egd.optional_float(raw.get("ask_px"))
                mid = egd.optional_float(raw.get("mid_px"))
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

    def release_mfe_bps(self, *, side: int, entry_ts_us: int, entry_mid: float, release_sec: int) -> float:
        if side == 0 or entry_mid <= 0.0:
            return math.nan
        left = int(np.searchsorted(self.ts, int(entry_ts_us), side="left"))
        right = int(np.searchsorted(self.ts, int(entry_ts_us) + release_sec * 1_000_000, side="right"))
        if right <= left:
            return 0.0
        mids = self.mid[left:right]
        if side > 0:
            best_mid = float(np.nanmax(mids))
            return math.log(best_mid / entry_mid) * 10_000.0
        best_mid = float(np.nanmin(mids))
        return math.log(entry_mid / best_mid) * 10_000.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--horizons-sec", default="5,20,60")
    parser.add_argument("--release-sec", type=int, default=10)
    parser.add_argument("--rolling-window", type=int, default=1000)
    parser.add_argument("--min-rolling-periods", type=int, default=200)
    parser.add_argument("--refractory-us", type=int, default=5_000_000)
    parser.add_argument("--min-events", type=int, default=30)
    parser.add_argument("--examples-per-variant", type=int, default=50)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def parse_int_list(value: str) -> list[int]:
    out = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not out:
        raise ValueError("expected at least one horizon")
    return out


def format_float(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def rolling_quantile(series: pd.Series, window: int, min_periods: int, q: float) -> pd.Series:
    return series.shift(1).rolling(window, min_periods=min_periods).quantile(q)


def enrich_structure_features(df: pd.DataFrame, rolling_window: int, min_periods: int) -> pd.DataFrame:
    out = egd.enrich_runtime_features(df, rolling_window, min_periods)
    bid_amt = pd.to_numeric(out["best_bid_amount"], errors="coerce").fillna(0.0).clip(lower=0.0)
    ask_amt = pd.to_numeric(out["best_ask_amount"], errors="coerce").fillna(0.0).clip(lower=0.0)
    bid_px = pd.to_numeric(out["best_bid_price"], errors="coerce").astype(float)
    ask_px = pd.to_numeric(out["best_ask_price"], errors="coerce").astype(float)
    mid = pd.to_numeric(out["mid"], errors="coerce").astype(float)
    denom = bid_amt + ask_amt
    microprice = np.where(
        denom > 1e-12,
        (ask_px * bid_amt + bid_px * ask_amt) / denom,
        mid,
    )
    out["microprice_dev_bps"] = 10_000.0 * np.log(np.where(microprice > 0.0, microprice, mid) / mid)
    out["top_depth_quote_min"] = np.minimum(bid_amt * bid_px, ask_amt * ask_px)
    out["top_depth_quote_sum"] = bid_amt * bid_px + ask_amt * ask_px
    out["top_depth_quote_min_q20"] = rolling_quantile(out["top_depth_quote_min"], rolling_window, min_periods, 0.20)
    out["top_depth_quote_min_q50"] = rolling_quantile(out["top_depth_quote_min"], rolling_window, min_periods, 0.50)
    out["frames"] = pd.to_numeric(out["frames_since_mid_change"], errors="coerce").fillna(0.0)
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


def variant_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    tfi = pd.to_numeric(df["trade_flow_imbalance"], errors="coerce").fillna(0.0)
    tfi_sign = pd.to_numeric(df["tfi_sign"], errors="coerce").fillna(0.0)
    qi = pd.to_numeric(df["queue_imbalance"], errors="coerce").fillna(0.0)
    micro_dev = pd.to_numeric(df["microprice_dev_bps"], errors="coerce").fillna(0.0)
    spread = pd.to_numeric(df["spread_bps"], errors="coerce").fillna(np.inf)
    spread_q50 = pd.to_numeric(df["spread_q50"], errors="coerce")
    depth_q20 = pd.to_numeric(df["top_depth_quote_min_q20"], errors="coerce")
    low_spread = spread <= spread_q50.fillna(-np.inf)
    low_depth = pd.to_numeric(df["top_depth_quote_min"], errors="coerce") <= depth_q20.fillna(-np.inf)
    abs_tfi_ge_1 = tfi.abs() >= 1.0 - 1e-12
    signed_tfi = tfi_sign != 0
    flat = pd.to_numeric(df["abs_past25"], errors="coerce").fillna(np.inf) <= 0.5
    stale25 = pd.to_numeric(df["frames"], errors="coerce").fillna(0.0) >= 25.0
    stale31 = pd.to_numeric(df["frames"], errors="coerce").fillna(0.0) >= 31.0
    trade_present = pd.to_numeric(df["trade_window_count"], errors="coerce").fillna(0.0) > 0.0
    queue_confirm = (tfi_sign * qi) >= 0.12
    queue_diverge = (tfi_sign * qi) <= -0.12
    micro_confirm = (tfi_sign * micro_dev) >= 0.03
    depth_collapse_flow = (
        (pd.to_numeric(df["depth_z"], errors="coerce").fillna(0.0) <= -1.5)
        & (tfi.abs() >= 0.35)
        & signed_tfi
    )
    vacuum_recent = (
        (pd.to_numeric(df["depth_z"], errors="coerce").fillna(0.0) <= -1.5)
        & (pd.to_numeric(df["spread_z"], errors="coerce").fillna(0.0) >= 1.0)
        & (pd.to_numeric(df["abs_past25"], errors="coerce").fillna(0.0) >= 1.0)
        & (pd.to_numeric(df["past25_sign"], errors="coerce").fillna(0.0) != 0.0)
    )
    absorption = (tfi.abs() >= 0.45) & queue_diverge & signed_tfi
    s1_flat = abs_tfi_ge_1 & signed_tfi & flat
    s1_stale = s1_flat & stale31
    s3_low = low_depth & (tfi.abs() >= 0.35) & signed_tfi
    past_event_continuation = (
        (pd.to_numeric(df["abs_past25_z"], errors="coerce").fillna(0.0) >= 2.0)
        & (pd.to_numeric(df["abs_past25"], errors="coerce").fillna(0.0) >= 1.0)
        & (pd.to_numeric(df["past25_sign"], errors="coerce").fillna(0.0) != 0.0)
    )
    trade_burst = (
        (pd.to_numeric(df["trade_count_z"], errors="coerce").fillna(0.0) >= 2.0)
        & (tfi.abs() >= 0.35)
        & signed_tfi
    )
    spread_shock = (
        (pd.to_numeric(df["spread_z"], errors="coerce").fillna(0.0) >= 2.0)
        & (spread >= 0.5)
        & (pd.to_numeric(df["abs_past25"], errors="coerce").fillna(0.0) >= 0.5)
        & (pd.to_numeric(df["past25_sign"], errors="coerce").fillna(0.0) != 0.0)
    )
    return {
        "S1_tfi_follow_flat": s1_flat,
        "S1_tfi_follow_flat_stale31": s1_stale,
        "S1_tfi_event_stale25": abs_tfi_ge_1 & signed_tfi & trade_present & stale25,
        "S2_tfi_queue_confirm": abs_tfi_ge_1 & signed_tfi & queue_confirm,
        "S2_tfi_microprice_confirm": abs_tfi_ge_1 & signed_tfi & micro_confirm,
        "S2_tfi_queue_divergence_control": abs_tfi_ge_1 & signed_tfi & queue_diverge,
        "S3_depth_collapse_tfi": depth_collapse_flow,
        "S3_low_depth_low_spread_tfi": s3_low & low_spread,
        "S3_vacuum_recent_breakout": vacuum_recent,
        "S4_absorption_continuation_test": absorption,
        "S4_absorption_reversal_test": absorption,
        "S4_stale_absorption_suppressor": absorption & stale31 & flat,
        "S6_s1_low_spread_admission": s1_flat & low_spread,
        "S6_s3_low_spread_admission": depth_collapse_flow & low_spread,
        "S6_low_spread_tfi_control": (tfi.abs() >= 0.35) & signed_tfi & low_spread & ~low_depth.fillna(False),
        "S7_past_event_continuation": past_event_continuation,
        "S7_trade_burst_decay_probe": trade_burst,
        "S7_spread_shock_breakout": spread_shock,
    }


def apply_refractory(df: pd.DataFrame, mask: pd.Series, refractory_us: int) -> list[int]:
    selected: list[int] = []
    last_ts: int | None = None
    for idx in df.index[mask.fillna(False)].tolist():
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


def build_structure_rows(
    day: str,
    df: pd.DataFrame,
    quote_book: QuoteBook,
    horizons_sec: list[int],
    release_sec: int,
    refractory_us: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    masks = variant_masks(df)
    for variant_id, mask in masks.items():
        spec = SPEC_BY_VARIANT[variant_id]
        for idx in apply_refractory(df, mask, refractory_us):
            row = df.loc[idx]
            side = side_from_rule(row, spec.direction_rule)
            if side == 0:
                continue
            entry_bid = float(row["best_bid_price"])
            entry_ask = float(row["best_ask_price"])
            entry_mid = float(row["mid"])
            if min(entry_bid, entry_ask, entry_mid) <= 0.0:
                continue
            entry_ts = int(row["local_ts_us"])
            release = quote_book.release_mfe_bps(
                side=side,
                entry_ts_us=entry_ts,
                entry_mid=entry_mid,
                release_sec=release_sec,
            )
            out: dict[str, Any] = {
                "date": day,
                "family_id": spec.family_id,
                "variant_id": spec.variant_id,
                "role": spec.role,
                "mechanism": spec.mechanism,
                "direction_rule": spec.direction_rule,
                "side": "buy" if side > 0 else "sell",
                "side_sign": side,
                "runtime_safe_status": spec.runtime_safe_status,
                "notes": spec.notes,
                "observed_seq": egd.optional_int(row.get("observed_seq")),
                "local_ts_us": entry_ts,
                "event_index": egd.optional_int(row.get("event_index")),
                "entry_bid": entry_bid,
                "entry_ask": entry_ask,
                "entry_mid": entry_mid,
                "entry_spread_bps": float(row.get("spread_bps") or 0.0),
                "top_depth": float(row.get("top_depth") or 0.0),
                "top_depth_quote_min": float(row.get("top_depth_quote_min") or 0.0),
                "queue_imbalance": float(row.get("queue_imbalance") or 0.0),
                "microprice_dev_bps": float(row.get("microprice_dev_bps") or 0.0),
                "trade_window_count": int(row.get("trade_window_count") or 0),
                "trade_flow_imbalance": float(row.get("trade_flow_imbalance") or 0.0),
                "frames_since_mid_change": float(row.get("frames_since_mid_change") or 0.0),
                "past_event_25_bps": float(row.get("past_event_25_bps") or 0.0),
                "spread_z": egd.optional_float(row.get("spread_z")),
                "depth_z": egd.optional_float(row.get("depth_z")),
                "trade_count_z": egd.optional_float(row.get("trade_count_z")),
                "abs_past25_z": egd.optional_float(row.get("abs_past25_z")),
                "release_mfe_10s": release,
            }
            for horizon in horizons_sec:
                quote = quote_book.at_or_before(entry_ts + horizon * 1_000_000)
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
            if "h60s_mid_bps" in out and math.isfinite(float(release)):
                out["decay_60s_after_mfe"] = float(release) - float(out["h60s_mid_bps"])
            rows.append(out)
    return rows


def daily_stats(group: pd.DataFrame, value_col: str) -> dict[str, float]:
    daily = group.groupby("date")[value_col].sum()
    if daily.empty:
        return {
            "worst_day": math.nan,
            "daily_sign_rate": math.nan,
            "max_day_concentration": math.nan,
        }
    denom = float(daily.abs().sum())
    return {
        "worst_day": float(daily.min()),
        "daily_sign_rate": float((daily > 0.0).mean()),
        "max_day_concentration": float(daily.abs().max() / denom) if denom > 0.0 else 0.0,
    }


def status_for_variant(row: dict[str, Any], min_events: int) -> str:
    n = int(row.get("n") or 0)
    role = str(row.get("role") or "")
    mean_mid = float(row.get("mean_mid_60") or math.nan)
    mean_exe = float(row.get("mean_executable_60") or math.nan)
    median = float(row.get("median") or math.nan)
    release = float(row.get("release_mfe_10s") or math.nan)
    decay = float(row.get("decay_60s_after_mfe") or math.nan)
    daily = float(row.get("daily_sign_rate") or math.nan)
    worst = float(row.get("worst_day") or math.nan)
    spread_cost = float(row.get("mean_spread_cost") or math.nan)

    if n < min_events:
        return "insufficient_sample"
    if math.isfinite(mean_mid) and math.isfinite(mean_exe) and mean_mid > 0.0 and mean_exe <= 0.0:
        return "spread-cost-mirage"
    if role == "control":
        return "control-only"
    if role == "cost-filter":
        if math.isfinite(spread_cost) and spread_cost <= 1.8 and mean_exe > 0.0:
            return "cost-filter-positive-executable"
        return "cost-filter-only"
    if role == "release-only":
        if mean_exe > 0.0 and median > 0.0 and daily >= 0.6 and worst >= 0.0:
            return "release-to-entry-candidate"
        return "release-only"
    if role == "decay-risk":
        if math.isfinite(decay) and math.isfinite(release) and decay > max(1.0, release):
            return "decay-risk"
        if mean_exe <= 0.0:
            return "risk-control-not-entry"
        return "decay-risk-control"
    if mean_exe > 0.0 and median > 0.0 and daily >= 0.6 and worst >= 0.0:
        return "entry-alpha-candidate"
    if mean_exe > 0.0:
        return "weak-entry-candidate"
    if math.isfinite(release) and release > 0.0:
        return "release-only"
    return "reject"


def summarize_variants(events: pd.DataFrame, horizons_sec: list[int], min_events: int) -> list[dict[str, Any]]:
    if events.empty:
        return []
    rows: list[dict[str, Any]] = []
    for variant_id, group in events.groupby("variant_id", sort=True):
        spec = SPEC_BY_VARIANT[str(variant_id)]
        row: dict[str, Any] = {
            "family_id": spec.family_id,
            "variant_id": spec.variant_id,
            "role": spec.role,
            "mechanism": spec.mechanism,
            "n": int(len(group)),
            "days": int(group["date"].nunique()),
            "long_count": int((group["side_sign"] > 0).sum()),
            "short_count": int((group["side_sign"] < 0).sum()),
            "runtime_safe_status": spec.runtime_safe_status,
            "notes": spec.notes,
        }
        for horizon in horizons_sec:
            mid_col = f"h{horizon}s_mid_bps"
            exe_col = f"h{horizon}s_executable_taker_bps"
            spread_col = f"h{horizon}s_spread_cost_bps"
            valid = group.dropna(subset=[mid_col, exe_col]).copy()
            row[f"mean_mid_{horizon}"] = float(valid[mid_col].mean()) if not valid.empty else math.nan
            row[f"mean_executable_{horizon}"] = float(valid[exe_col].mean()) if not valid.empty else math.nan
            row[f"median_executable_{horizon}"] = float(valid[exe_col].median()) if not valid.empty else math.nan
            row[f"hit_rate_{horizon}"] = float((valid[exe_col] > 0.0).mean()) if not valid.empty else math.nan
            row[f"mean_spread_cost_{horizon}"] = float(valid[spread_col].mean()) if not valid.empty else math.nan
        row["release_mfe_10s"] = float(group["release_mfe_10s"].mean())
        row["decay_60s_after_mfe"] = float(group["decay_60s_after_mfe"].mean()) if "decay_60s_after_mfe" in group else math.nan
        row["mean_spread_cost"] = row.get("mean_spread_cost_60", math.nan)
        row["median"] = row.get("median_executable_60", math.nan)
        row["hit_rate"] = row.get("hit_rate_60", math.nan)
        daily = daily_stats(group.dropna(subset=["h60s_executable_taker_bps"]), "h60s_executable_taker_bps")
        row.update(daily)
        row["promotion_status"] = status_for_variant(row, min_events)
        rows.append(row)
    rows.sort(key=lambda item: (str(item["family_id"]), float(item.get("mean_executable_60") or -1e9)), reverse=False)
    return rows


def summarize_families(variant_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in variant_rows:
        by_family.setdefault(str(row["family_id"]), []).append(row)
    out: list[dict[str, Any]] = []
    for family_id, rows in sorted(by_family.items()):
        best = max(rows, key=lambda item: float(item.get("mean_executable_60") or -1e9))
        out.append(
            {
                "family_id": family_id,
                "variant_count": len(rows),
                "best_variant_id": best["variant_id"],
                "best_role": best["role"],
                "best_promotion_status": best["promotion_status"],
                "best_n": best["n"],
                "best_mean_mid_60": best.get("mean_mid_60"),
                "best_mean_executable_60": best.get("mean_executable_60"),
                "best_release_mfe_10s": best.get("release_mfe_10s"),
                "best_decay_60s_after_mfe": best.get("decay_60s_after_mfe"),
                "best_mean_spread_cost": best.get("mean_spread_cost"),
                "best_median": best.get("median"),
                "best_hit_rate": best.get("hit_rate"),
                "best_worst_day": best.get("worst_day"),
                "best_daily_sign_rate": best.get("daily_sign_rate"),
                "best_max_day_concentration": best.get("max_day_concentration"),
            }
        )
    if "S5_post_release_exit_wait" not in by_family:
        out.append(
            {
                "family_id": "S5_post_release_exit_wait",
                "variant_count": 0,
                "best_variant_id": "second_stage_not_implemented",
                "best_role": "exit-wait-candidate",
                "best_promotion_status": "second-stage-path-study-required",
                "best_n": 0,
                "best_mean_mid_60": math.nan,
                "best_mean_executable_60": math.nan,
                "best_release_mfe_10s": math.nan,
                "best_decay_60s_after_mfe": math.nan,
                "best_mean_spread_cost": math.nan,
                "best_median": math.nan,
                "best_hit_rate": math.nan,
                "best_worst_day": math.nan,
                "best_daily_sign_rate": math.nan,
                "best_max_day_concentration": math.nan,
            }
        )
    return sorted(out, key=lambda item: str(item["family_id"]))


def select_examples(events: pd.DataFrame, examples_per_variant: int) -> pd.DataFrame:
    if events.empty or examples_per_variant <= 0:
        return pd.DataFrame()
    chunks: list[pd.DataFrame] = []
    for _, group in events.groupby("variant_id", sort=True):
        sort_col = "h60s_executable_taker_bps" if "h60s_executable_taker_bps" in group else "local_ts_us"
        chunks.append(group.sort_values(sort_col, ascending=False).head(examples_per_variant))
    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()


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


def write_report(path: Path, summary: dict[str, Any], family_rows: list[dict[str, Any]], variant_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# CCUSDT Structure Family Fast Research v0.1")
    lines.append("")
    lines.append("Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    for key in ["symbol", "from_date", "to_date", "horizons_sec", "release_sec", "out_dir"]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("This diagnostic reads `decision_frame_v1` plus canonical `quote_frame_v1`. It does not read `date/`, scored entries, future labels, PnL/MFE/MAE files, or strategy runtime state. `S5 post-release exit/wait` is marked as a required second-stage path study.")
    lines.append("")
    lines.append("Important data caveat: this first pass uses decision-frame fields and L1/top-of-book proxies. Bot-owned closed-entry `R5` and full OFI/MLOFI sidecars are not in this path, so S1 is a stale-release proxy and S2 is a queue/microprice confirmation proxy.")
    lines.append("")
    lines.append("## Family Summary")
    lines.append("")
    lines.append("| family | best variant | role | status | n | mean mid60 | mean exe60 | release10 | decay60 | spread cost | median | hit | worst day | daily sign |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in family_rows:
        lines.append(
            "| {family} | {variant} | {role} | {status} | {n} | {mid} | {exe} | {release} | {decay} | {cost} | {median} | {hit} | {worst} | {daily} |".format(
                family=row["family_id"],
                variant=row["best_variant_id"],
                role=row["best_role"],
                status=row["best_promotion_status"],
                n=row["best_n"],
                mid=format_float(row["best_mean_mid_60"]),
                exe=format_float(row["best_mean_executable_60"]),
                release=format_float(row["best_release_mfe_10s"]),
                decay=format_float(row["best_decay_60s_after_mfe"]),
                cost=format_float(row["best_mean_spread_cost"]),
                median=format_float(row["best_median"]),
                hit=format_float(row["best_hit_rate"]),
                worst=format_float(row["best_worst_day"]),
                daily=format_float(row["best_daily_sign_rate"]),
            )
        )
    lines.append("")
    lines.append("## First-Pass Reading")
    lines.append("")
    status_by_family = {str(row["family_id"]): row for row in family_rows}
    s1 = status_by_family.get("S1_active_flow_stale_release")
    if s1:
        lines.append(
            f"- `S1 active-flow stale-release`: best variant `{s1['best_variant_id']}` is `{s1['best_promotion_status']}`. This is still the only family in this pass with a clean entry-alpha read after top-of-book crossing, but it is the narrower stale subset rather than generic TFI."
        )
    s2 = status_by_family.get("S2_flow_book_confirmation")
    if s2:
        lines.append(
            f"- `S2 flow-book confirmation`: best executable mean is {format_float(s2['best_mean_executable_60'])}bps, with status `{s2['best_promotion_status']}`. The L1 confirmation proxy improves release but does not yet solve median, worst-day, or spread-cost economics."
        )
    s3 = status_by_family.get("S3_liquidity_vacuum_release")
    if s3:
        lines.append(
            f"- `S3 liquidity vacuum`: best row is `{s3['best_promotion_status']}`. Thin depth appears to explain fast release, but the robust role remains release/admission research, not direct entry promotion."
        )
    s4 = status_by_family.get("S4_absorption_failed_continuation")
    if s4:
        lines.append(
            f"- `S4 absorption`: best row is `{s4['best_promotion_status']}`. Treat it as a failed-continuation or suppressor family until larger samples and path-conditioned exit evidence justify otherwise."
        )
    s6 = status_by_family.get("S6_execution_cost_admission")
    if s6:
        lines.append(
            f"- `S6 execution-cost admission`: best row is `{s6['best_promotion_status']}`. Low spread can reduce crossing damage, but it is a gate on another structure rather than a standalone alpha source."
        )
    s7 = status_by_family.get("S7_volatility_decay_risk")
    if s7:
        lines.append(
            f"- `S7 volatility / decay-risk`: best row is `{s7['best_promotion_status']}`. Its primary use is risk/exclusion or exit urgency, because realized movement and trade bursts are usually eaten by spread and decay."
        )
    lines.append("")
    lines.append("## Variant Summary")
    lines.append("")
    lines.append("| family | variant | role | n | mean mid60 | mean exe60 | release10 | decay60 | spread cost | median | hit | worst day | status |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in variant_rows:
        lines.append(
            "| {family} | {variant} | {role} | {n} | {mid} | {exe} | {release} | {decay} | {cost} | {median} | {hit} | {worst} | {status} |".format(
                family=row["family_id"],
                variant=row["variant_id"],
                role=row["role"],
                n=row["n"],
                mid=format_float(row.get("mean_mid_60")),
                exe=format_float(row.get("mean_executable_60")),
                release=format_float(row.get("release_mfe_10s")),
                decay=format_float(row.get("decay_60s_after_mfe")),
                cost=format_float(row.get("mean_spread_cost")),
                median=format_float(row.get("median")),
                hit=format_float(row.get("hit_rate")),
                worst=format_float(row.get("worst_day")),
                status=row["promotion_status"],
            )
        )
    lines.append("")
    lines.append("## Interpretation Rules")
    lines.append("")
    lines.append("- `spread-cost-mirage`: positive mid label but non-positive top-of-book taker executable label.")
    lines.append("- `release-only`: favorable excursion exists, but executable evidence does not justify entry promotion.")
    lines.append("- `release-to-entry-candidate`: a release family also passes the stronger entry-alpha stability checks; none should be promoted without strict replay.")
    lines.append("- `cost-filter`: a gate that may veto or scale entries, not create direction by itself.")
    lines.append("- `decay-risk`: a regime useful for suppression or exit urgency, not direct entry alpha.")
    lines.append("- `decay-risk-control`: positive executable mean exists, but the row is role-classified as risk/control because median, hit-rate, or mechanism is not entry-alpha clean.")
    lines.append("- `control-only`: a contrast row used to understand mechanism direction, not a strategy candidate.")
    lines.append("- Positive executable evidence still requires later strict replay, capacity, and profile-equivalence checks.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    horizons_sec = parse_int_list(args.horizons_sec)
    out_dir = args.out_dir
    if out_dir is None:
        out_dir = DEFAULT_OUT_ROOT / f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_decision_frame_v0_1"
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    events_by_day: list[pd.DataFrame] = []
    source_manifests: list[dict[str, Any]] = []
    for day in egd.date_range(args.from_date, args.to_date):
        print(f"structure_family_fast_research day={day}", file=sys.stderr, flush=True)
        raw_df, manifest = egd.load_decision_frames(repo_root, args.symbol, day)
        df = enrich_structure_features(raw_df, args.rolling_window, args.min_rolling_periods)
        quote_book = QuoteBook.load(repo_root, args.symbol, day)
        rows = build_structure_rows(day, df, quote_book, horizons_sec, args.release_sec, args.refractory_us)
        if rows:
            events_by_day.append(pd.DataFrame(rows))
        source_manifests.append(
            {
                "date": day,
                "decision_frame_manifest_path": str(egd.decision_manifest_path(repo_root, args.symbol, day)),
                "quote_frame_path": str(egd.quote_path(repo_root, args.symbol, day)),
                "decision_frame_rows": int(len(df)),
                "event_rows": int(len(rows)),
                "decision_frame_field_hash_sha256": manifest.get("field_hash_sha256"),
                "decision_frame_builder_version": manifest.get("builder_version"),
                "decision_frame_schema_version": manifest.get("schema_version"),
            }
        )

    events = pd.concat(events_by_day, ignore_index=True) if events_by_day else pd.DataFrame()
    variant_rows = summarize_variants(events, horizons_sec, args.min_events)
    family_rows = summarize_families(variant_rows)
    examples = select_examples(events, args.examples_per_variant)

    family_csv = out_dir / "structure_family_summary.csv"
    variant_csv = out_dir / "structure_variant_summary.csv"
    examples_path = out_dir / "structure_event_examples.parquet"
    write_csv(family_csv, family_rows)
    write_csv(variant_csv, variant_rows)
    if examples.empty:
        pq.write_table(pa.Table.from_pandas(pd.DataFrame({"empty": []})), examples_path)
    else:
        pq.write_table(pa.Table.from_pandas(examples, preserve_index=False), examples_path)

    summary = {
        "schema_id": "ccusdt_structure_family_fast_research_summary_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "horizons_sec": horizons_sec,
        "release_sec": args.release_sec,
        "rolling_window": args.rolling_window,
        "min_rolling_periods": args.min_rolling_periods,
        "refractory_us": args.refractory_us,
        "min_events": args.min_events,
        "event_rows": int(len(events)),
        "variant_rows": len(variant_rows),
        "family_rows": len(family_rows),
        "s5_status": "second_stage_path_study_required_not_implemented",
        "out_dir": str(out_dir),
        "report_path": str(report_path),
        "elapsed_wall_ms": int((time.perf_counter() - started) * 1000),
        "source_manifests": source_manifests,
        "outputs": {
            "structure_family_summary_csv": str(family_csv),
            "structure_variant_summary_csv": str(variant_csv),
            "structure_event_examples_parquet": str(examples_path),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(report_path, summary, family_rows, variant_rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
