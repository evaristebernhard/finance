#!/usr/bin/env python
"""CCUSDT taker cross-now vs wait-then-cross value diagnostic.

This is a research-only fast diagnostic. It compares immediate top-of-book
taker entry against waiting a short deterministic delay and then crossing,
using the same fixed terminal horizon:

    G_i(delta, H) = Y_i^wait(delta, H) - Y_i^now(H)

The panel uses runtime-safe candidate features, while future executable labels
are computed inside this diagnostic only. It must not become Runner or Bot
runtime input.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
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
import structure_family_fast_research as sfr


US_PER_SEC = 1_000_000
EPS = 1e-12

DEFAULT_FAST_RUN_ID = "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260516_18_20260521"
DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/taker_wait_value_diagnostic")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/execution/v1-taker-wait-value-diagnostic-20260602.md")


@dataclass(frozen=True)
class Quote:
    seq: int
    exchange_ts_us: int
    local_ts_us: int
    bid: float
    ask: float
    mid: float
    spread_bps: float
    bid_qty: float
    ask_qty: float


class QuoteIndex:
    def __init__(self, quotes: list[Quote]) -> None:
        if not quotes:
            raise ValueError("empty quote index")
        self.quotes = quotes
        self.local_ts = np.array([quote.local_ts_us for quote in quotes], dtype=np.int64)

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "QuoteIndex":
        path = egd.quote_path(repo_root, symbol, day)
        quotes: list[Quote] = []
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for idx, row in enumerate(reader):
                bid = egd.optional_float(row.get("bid_px"))
                ask = egd.optional_float(row.get("ask_px"))
                local_ts_us = int(row.get("local_ts_us") or 0)
                if bid is None or ask is None or bid <= 0.0 or ask <= 0.0 or local_ts_us <= 0:
                    continue
                mid = egd.optional_float(row.get("mid_px"))
                if mid is None or mid <= 0.0:
                    mid = 0.5 * (bid + ask)
                spread_bps = egd.optional_float(row.get("spread_bps"))
                if spread_bps is None:
                    spread_bps = math.log(ask / bid) * 10_000.0
                quotes.append(
                    Quote(
                        seq=int(row.get("seq") or idx),
                        exchange_ts_us=int(row.get("exchange_ts_us") or 0),
                        local_ts_us=local_ts_us,
                        bid=bid,
                        ask=ask,
                        mid=mid,
                        spread_bps=spread_bps,
                        bid_qty=float(egd.optional_float(row.get("bid_qty")) or 0.0),
                        ask_qty=float(egd.optional_float(row.get("ask_qty")) or 0.0),
                    )
                )
        return cls(quotes)

    def at_or_before(self, local_ts_us: int) -> Quote | None:
        idx = int(np.searchsorted(self.local_ts, int(local_ts_us), side="right") - 1)
        if idx < 0:
            return None
        return self.quotes[idx]


class FrameIndex:
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.local_ts = df["local_ts_us"].astype("int64").to_numpy()

    def at_or_before(self, local_ts_us: int) -> pd.Series | None:
        idx = int(np.searchsorted(self.local_ts, int(local_ts_us), side="right") - 1)
        if idx < 0:
            return None
        return self.df.iloc[idx]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--source-scope", choices=["fast", "structure", "both"], default="both")
    parser.add_argument("--fast-run-id", default=DEFAULT_FAST_RUN_ID)
    parser.add_argument("--fast-run-path", type=Path)
    parser.add_argument("--waits-sec", default="1,2,3,5,10,20")
    parser.add_argument("--horizons-sec", default="5,20,60")
    parser.add_argument("--rolling-window", type=int, default=1000)
    parser.add_argument("--min-rolling-periods", type=int, default=200)
    parser.add_argument("--refractory-us", type=int, default=5_000_000)
    parser.add_argument("--margin-bps", type=float, default=0.25)
    parser.add_argument("--min-events", type=int, default=30)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def parse_int_list(value: str) -> list[int]:
    out = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not out:
        raise ValueError("expected at least one integer value")
    return sorted(set(out))


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def file_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {"path": str(path), "exists": True, "byte_size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def side_sign_from_value(value: Any) -> int:
    text = str(value or "").lower()
    if text in {"buy", "long", "1"}:
        return 1
    if text in {"sell", "short", "-1"}:
        return -1
    numeric = optional_float(value)
    if numeric is not None:
        return 1 if numeric > 0.0 else -1 if numeric < 0.0 else 0
    return 0


def entry_cross_bps(side_sign: int, bid: float, ask: float, mid: float) -> float:
    if min(bid, ask, mid) <= 0.0 or side_sign == 0:
        return math.nan
    if side_sign > 0:
        return math.log(ask / mid) * 10_000.0
    return math.log(mid / bid) * 10_000.0


def signed_mid_move_bps(side_sign: int, start_mid: float, end_mid: float) -> float:
    if min(start_mid, end_mid) <= 0.0 or side_sign == 0:
        return math.nan
    return side_sign * math.log(end_mid / start_mid) * 10_000.0


def executable_taker_bps(side_sign: int, entry_bid: float, entry_ask: float, exit_bid: float, exit_ask: float) -> float:
    if min(entry_bid, entry_ask, exit_bid, exit_ask) <= 0.0 or side_sign == 0:
        return math.nan
    if side_sign > 0:
        return math.log(exit_bid / entry_ask) * 10_000.0
    return math.log(entry_bid / exit_ask) * 10_000.0


def terminal_mid_bps(side_sign: int, entry_mid: float, exit_mid: float) -> float:
    if min(entry_mid, exit_mid) <= 0.0 or side_sign == 0:
        return math.nan
    if side_sign > 0:
        return math.log(exit_mid / entry_mid) * 10_000.0
    return math.log(entry_mid / exit_mid) * 10_000.0


def date_allowed(day: str, allowed: set[str]) -> bool:
    return str(day) in allowed


def fast_run_path(repo_root: Path, args: argparse.Namespace) -> Path:
    if args.fast_run_path is not None:
        return args.fast_run_path if args.fast_run_path.is_absolute() else repo_root / args.fast_run_path
    return repo_root / "systems/ccusdt_replay_exchange/runs/experiments" / args.fast_run_id


def feature_from_frame(frame: pd.Series | None, key: str, default: Any = None) -> Any:
    if frame is None:
        return default
    value = frame.get(key, default)
    if pd.isna(value):
        return default
    return value


def candidate_priority(candidate: dict[str, Any]) -> int:
    if candidate["source"] == "fast_entry":
        return 0
    family = str(candidate.get("family_id") or "")
    if family.startswith("S1_"):
        return 1
    if family.startswith("S6_"):
        return 2
    if family.startswith(("S2_", "S3_", "S4_", "S7_")):
        return 3
    return 9


def load_fast_candidates(
    repo_root: Path,
    args: argparse.Namespace,
    allowed_days: set[str],
    frames_by_day: dict[str, pd.DataFrame],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_path = fast_run_path(repo_root, args)
    entries_path = run_path / "entries.parquet"
    if not entries_path.exists():
        raise FileNotFoundError(entries_path)
    df = pq.read_table(entries_path).to_pandas()
    df = df[df["date"].astype(str).map(lambda day: date_allowed(day, allowed_days))].copy()
    df["actual_exposure"] = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0)
    actual = df[df["actual_exposure"] > EPS].copy()
    candidates: list[dict[str, Any]] = []
    frame_indexes = {day: FrameIndex(frames_by_day[day]) for day in frames_by_day}
    for _, row in actual.iterrows():
        day = str(row["date"])
        side_sign = side_sign_from_value(row.get("side") or row.get("direction"))
        entry_ts = int(row["entry_ts_us"])
        frame = frame_indexes.get(day).at_or_before(entry_ts) if day in frame_indexes else None
        entry_bid = float(row["entry_bid"])
        entry_ask = float(row["entry_ask"])
        entry_mid = float(row["entry_mid"])
        if side_sign == 0 or min(entry_bid, entry_ask, entry_mid) <= 0.0:
            continue
        candidate = {
            "candidate_id": f"fast_entry:{args.fast_run_id}:{day}:{int(row['shadow_position_id'])}",
            "source": "fast_entry",
            "source_run_id": args.fast_run_id,
            "date": day,
            "local_ts_us": entry_ts,
            "observed_seq": optional_int(row.get("entry_seq")),
            "side_sign": side_sign,
            "side": "buy" if side_sign > 0 else "sell",
            "family_id": "fast_q70_idle01_g1",
            "variant_id": "fast_entry_fixed60_taker",
            "cell": str(row.get("cell") or ""),
            "trigger_classes": str(row.get("trigger_classes") or ""),
            "actual_exposure": float(row["actual_exposure"]),
            "requested_exposure": optional_float(row.get("requested_exposure")),
            "capacity_source": str(row.get("capacity_source") or ""),
            "entry_bid": entry_bid,
            "entry_ask": entry_ask,
            "entry_mid": entry_mid,
            "entry_spread_bps": float(row.get("entry_spread_bps") or math.log(entry_ask / entry_bid) * 10_000.0),
            "entry_cross_bps": float(row.get("entry_cross_bps") or entry_cross_bps(side_sign, entry_bid, entry_ask, entry_mid)),
            "frames_since_mid_change": optional_float(feature_from_frame(frame, "frames_since_mid_change")),
            "trade_flow_imbalance": optional_float(feature_from_frame(frame, "trade_flow_imbalance")),
            "trade_window_count": optional_float(feature_from_frame(frame, "trade_window_count")),
            "past_event_25_bps": optional_float(feature_from_frame(frame, "past_event_25_bps")),
            "top_depth": optional_float(feature_from_frame(frame, "top_depth")),
            "top_depth_quote_min": optional_float(feature_from_frame(frame, "top_depth_quote_min")),
            "queue_imbalance": optional_float(feature_from_frame(frame, "queue_imbalance")),
            "spread_z": optional_float(feature_from_frame(frame, "spread_z")),
            "depth_z": optional_float(feature_from_frame(frame, "depth_z")),
            "trade_count_z": optional_float(feature_from_frame(frame, "trade_count_z")),
        }
        candidate["source_priority"] = candidate_priority(candidate)
        candidates.append(candidate)
    manifest = {
        "schema_id": "ccusdt_taker_wait_fast_entry_manifest_v1",
        "fast_run_id": args.fast_run_id,
        "run_path": str(run_path),
        "entries": file_manifest(entries_path),
        "raw_entry_rows_in_window": int(len(df)),
        "actual_entry_rows_in_window": int(len(actual)),
        "candidate_count": len(candidates),
    }
    if len(candidates) != len(actual):
        manifest["candidate_drop_count"] = int(len(actual) - len(candidates))
    return candidates, manifest


def build_structure_candidates(
    day: str,
    df: pd.DataFrame,
    refractory_us: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    masks = sfr.variant_masks(df)
    for variant_id, mask in masks.items():
        spec = sfr.SPEC_BY_VARIANT[variant_id]
        for idx in sfr.apply_refractory(df, mask, refractory_us):
            row = df.loc[idx]
            side_sign = sfr.side_from_rule(row, spec.direction_rule)
            entry_bid = float(row["best_bid_price"])
            entry_ask = float(row["best_ask_price"])
            entry_mid = float(row["mid"])
            if side_sign == 0 or min(entry_bid, entry_ask, entry_mid) <= 0.0:
                continue
            entry_ts = int(row["local_ts_us"])
            candidate = {
                "candidate_id": f"structure:{variant_id}:{day}:{entry_ts}:{side_sign}",
                "source": "structure_candidate",
                "source_run_id": "",
                "date": day,
                "local_ts_us": entry_ts,
                "observed_seq": optional_int(row.get("observed_seq")),
                "side_sign": int(side_sign),
                "side": "buy" if side_sign > 0 else "sell",
                "family_id": spec.family_id,
                "variant_id": spec.variant_id,
                "cell": "",
                "trigger_classes": spec.direction_rule,
                "actual_exposure": 1.0,
                "requested_exposure": None,
                "capacity_source": "",
                "entry_bid": entry_bid,
                "entry_ask": entry_ask,
                "entry_mid": entry_mid,
                "entry_spread_bps": float(row.get("spread_bps") or math.log(entry_ask / entry_bid) * 10_000.0),
                "entry_cross_bps": entry_cross_bps(int(side_sign), entry_bid, entry_ask, entry_mid),
                "frames_since_mid_change": optional_float(row.get("frames_since_mid_change")),
                "trade_flow_imbalance": optional_float(row.get("trade_flow_imbalance")),
                "trade_window_count": optional_float(row.get("trade_window_count")),
                "past_event_25_bps": optional_float(row.get("past_event_25_bps")),
                "top_depth": optional_float(row.get("top_depth")),
                "top_depth_quote_min": optional_float(row.get("top_depth_quote_min")),
                "queue_imbalance": optional_float(row.get("queue_imbalance")),
                "spread_z": optional_float(row.get("spread_z")),
                "depth_z": optional_float(row.get("depth_z")),
                "trade_count_z": optional_float(row.get("trade_count_z")),
            }
            candidate["source_priority"] = candidate_priority(candidate)
            candidates.append(candidate)
    return candidates


def dedup_candidate_ids(candidates: list[dict[str, Any]]) -> set[str]:
    ranked = sorted(
        candidates,
        key=lambda row: (
            str(row["date"]),
            int(row["local_ts_us"]),
            int(row["side_sign"]),
            int(row.get("source_priority") or 9),
            str(row.get("variant_id") or ""),
        ),
    )
    keep: dict[tuple[str, int, int], str] = {}
    for row in ranked:
        key = (str(row["date"]), int(row["local_ts_us"]), int(row["side_sign"]))
        keep.setdefault(key, str(row["candidate_id"]))
    return set(keep.values())


def wait_class(wait_gain: float, now_exec: float, wait_exec: float, margin_bps: float) -> str:
    if max(now_exec, wait_exec) <= 0.0:
        return "skip_candidate"
    if wait_gain > margin_bps:
        return "wait_better"
    if wait_gain < -margin_bps:
        return "cross_now_better"
    return "indifferent"


def wait_mechanism(wait_gain: float, repair: float, missed_release: float, margin_bps: float) -> str:
    if wait_gain > margin_bps:
        adverse_preentry = -missed_release
        if repair > margin_bps and repair >= max(adverse_preentry, 0.0) and missed_release >= -margin_bps:
            return "spread_repair_win"
        if adverse_preentry > margin_bps and adverse_preentry > max(repair, 0.0):
            return "adverse_preentry_move_benefit"
        if repair > margin_bps and adverse_preentry > margin_bps:
            return "mixed_repair_and_adverse_move"
        return "wait_better_other"
    if wait_gain < -margin_bps and missed_release > max(repair, 0.0):
        return "missed_release_loss"
    if wait_gain < -margin_bps and repair < -margin_bps:
        return "entry_cross_worsened_loss"
    if wait_gain < -margin_bps:
        return "cross_now_other"
    return "indifferent"


def build_label_rows(
    candidates: list[dict[str, Any]],
    quote_by_day: dict[str, QuoteIndex],
    waits_sec: list[int],
    horizons_sec: list[int],
    margin_bps: float,
    dedup_keep_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        day = str(candidate["date"])
        quote_index = quote_by_day[day]
        side_sign = int(candidate["side_sign"])
        entry_ts = int(candidate["local_ts_us"])
        now_entry_bid = float(candidate["entry_bid"])
        now_entry_ask = float(candidate["entry_ask"])
        now_entry_mid = float(candidate["entry_mid"])
        now_cross = entry_cross_bps(side_sign, now_entry_bid, now_entry_ask, now_entry_mid)
        for horizon in horizons_sec:
            exit_quote = quote_index.at_or_before(entry_ts + horizon * US_PER_SEC)
            if exit_quote is None:
                continue
            now_exec = executable_taker_bps(
                side_sign, now_entry_bid, now_entry_ask, exit_quote.bid, exit_quote.ask
            )
            now_mid = terminal_mid_bps(side_sign, now_entry_mid, exit_quote.mid)
            for wait in waits_sec:
                if wait >= horizon:
                    continue
                wait_entry_quote = quote_index.at_or_before(entry_ts + wait * US_PER_SEC)
                shift_exit_quote = quote_index.at_or_before(entry_ts + (wait + horizon) * US_PER_SEC)
                if wait_entry_quote is None or shift_exit_quote is None:
                    continue
                wait_exec = executable_taker_bps(
                    side_sign, wait_entry_quote.bid, wait_entry_quote.ask, exit_quote.bid, exit_quote.ask
                )
                shift_exec = executable_taker_bps(
                    side_sign,
                    wait_entry_quote.bid,
                    wait_entry_quote.ask,
                    shift_exit_quote.bid,
                    shift_exit_quote.ask,
                )
                wait_cross = entry_cross_bps(
                    side_sign, wait_entry_quote.bid, wait_entry_quote.ask, wait_entry_quote.mid
                )
                repair = now_cross - wait_cross
                missed_release = signed_mid_move_bps(side_sign, now_entry_mid, wait_entry_quote.mid)
                wait_gain = wait_exec - now_exec
                decomp_error = wait_gain - (repair - missed_release)
                row = dict(candidate)
                row.update(
                    {
                        "schema_id": "ccusdt_taker_wait_value_event_v1",
                        "runtime_safe_features": True,
                        "future_labels_runtime_safe": False,
                        "dedup_keep": str(candidate["candidate_id"]) in dedup_keep_ids,
                        "horizon_sec": int(horizon),
                        "wait_sec": int(wait),
                        "now_exit_ts_us": int(exit_quote.local_ts_us),
                        "wait_entry_ts_us": int(wait_entry_quote.local_ts_us),
                        "shift_exit_ts_us": int(shift_exit_quote.local_ts_us),
                        "wait_entry_bid": float(wait_entry_quote.bid),
                        "wait_entry_ask": float(wait_entry_quote.ask),
                        "wait_entry_mid": float(wait_entry_quote.mid),
                        "wait_entry_spread_bps": float(wait_entry_quote.spread_bps),
                        "wait_entry_cross_bps": wait_cross,
                        "exit_bid": float(exit_quote.bid),
                        "exit_ask": float(exit_quote.ask),
                        "exit_mid": float(exit_quote.mid),
                        "exit_spread_bps": float(exit_quote.spread_bps),
                        "shift_exit_bid": float(shift_exit_quote.bid),
                        "shift_exit_ask": float(shift_exit_quote.ask),
                        "shift_exit_mid": float(shift_exit_quote.mid),
                        "now_mid_bps": now_mid,
                        "now_exec_bps": now_exec,
                        "wait_exec_bps": wait_exec,
                        "wait_gain_bps": wait_gain,
                        "shifted_horizon_exec_bps": shift_exec,
                        "shifted_gain_vs_now_bps": shift_exec - now_exec,
                        "entry_cross_repair_bps": repair,
                        "signed_mid_move_to_wait_bps": missed_release,
                        "wait_decomposition_error_bps": decomp_error,
                        "wait_class": wait_class(wait_gain, now_exec, wait_exec, margin_bps),
                        "wait_mechanism": wait_mechanism(wait_gain, repair, missed_release, margin_bps),
                    }
                )
                rows.append(row)
    return rows


def add_best_wait_columns(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel
    out = panel.copy()
    grouped = out.groupby(["candidate_id", "horizon_sec"], sort=False)
    idx = grouped["wait_exec_bps"].idxmax()
    best = out.loc[idx, ["candidate_id", "horizon_sec", "wait_sec", "wait_exec_bps", "wait_gain_bps"]].rename(
        columns={
            "wait_sec": "best_wait_sec",
            "wait_exec_bps": "best_wait_exec_bps",
            "wait_gain_bps": "best_wait_gain_bps",
        }
    )
    out = out.merge(best, on=["candidate_id", "horizon_sec"], how="left", validate="many_to_one")
    return out


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def weighted_mean(group: pd.DataFrame, column: str) -> float:
    values = numeric_series(group, column)
    ok = values.notna()
    if not ok.any():
        return math.nan
    weights = numeric_series(group, "actual_exposure").fillna(0.0).clip(lower=0.0)
    denom = float(weights[ok].sum())
    if denom <= 0.0:
        return float(values[ok].mean())
    return float((weights[ok] * values[ok]).sum() / denom)


def weighted_sum(group: pd.DataFrame, column: str) -> float:
    weights = numeric_series(group, "actual_exposure").fillna(0.0).clip(lower=0.0)
    values = numeric_series(group, column).fillna(0.0)
    return float((weights * values).sum())


def cvar_left(values: pd.Series, frac: float = 0.10) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna().sort_values()
    if clean.empty:
        return math.nan
    count = max(1, int(math.ceil(len(clean) * frac)))
    return float(clean.iloc[:count].mean())


def summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    day_sums = [float(day_group["wait_gain_bps"].sum()) for _, day_group in group.groupby("date", sort=True)]
    weighted_day_sums = [weighted_sum(day_group, "wait_gain_bps") for _, day_group in group.groupby("date", sort=True)]
    mechanisms = group["wait_mechanism"].astype(str).value_counts(normalize=True)
    dominant_mechanism = str(mechanisms.index[0]) if not mechanisms.empty else ""
    mean_gain = float(numeric_series(group, "wait_gain_bps").mean())
    mean_repair = float(numeric_series(group, "entry_cross_repair_bps").mean())
    mean_missed = float(numeric_series(group, "signed_mid_move_to_wait_bps").mean())
    return {
        "n": int(len(group)),
        "candidate_count": int(group["candidate_id"].nunique()),
        "exposure": float(numeric_series(group, "actual_exposure").fillna(0.0).clip(lower=0.0).sum()),
        "mean_now_exec_bps": float(numeric_series(group, "now_exec_bps").mean()),
        "mean_wait_exec_bps": float(numeric_series(group, "wait_exec_bps").mean()),
        "mean_wait_gain_bps": mean_gain,
        "median_wait_gain_bps": float(numeric_series(group, "wait_gain_bps").median()),
        "weighted_mean_wait_gain_bps": weighted_mean(group, "wait_gain_bps"),
        "weighted_sum_wait_gain_bps": weighted_sum(group, "wait_gain_bps"),
        "wait_better_rate": float((numeric_series(group, "wait_gain_bps") > 0.25).mean()),
        "cross_now_better_rate": float((numeric_series(group, "wait_gain_bps") < -0.25).mean()),
        "skip_rate": float((group["wait_class"] == "skip_candidate").mean()),
        "mean_entry_cross_repair_bps": mean_repair,
        "mean_signed_mid_move_to_wait_bps": mean_missed,
        "aggregate_wait_mechanism": wait_mechanism(mean_gain, mean_repair, mean_missed, 0.25),
        "dominant_wait_mechanism": dominant_mechanism,
        "spread_repair_win_rate": float(mechanisms.get("spread_repair_win", 0.0)),
        "adverse_preentry_move_benefit_rate": float(mechanisms.get("adverse_preentry_move_benefit", 0.0)),
        "mixed_repair_and_adverse_move_rate": float(mechanisms.get("mixed_repair_and_adverse_move", 0.0)),
        "missed_release_loss_rate": float(mechanisms.get("missed_release_loss", 0.0)),
        "mean_shifted_horizon_exec_bps": float(numeric_series(group, "shifted_horizon_exec_bps").mean()),
        "cvar10_wait_gain_bps": cvar_left(group["wait_gain_bps"], 0.10),
        "worst_wait_gain_bps": float(numeric_series(group, "wait_gain_bps").min()),
        "positive_day_frac": float(sum(1 for value in day_sums if value > 0.0) / len(day_sums)) if day_sums else 0.0,
        "min_day_wait_gain_sum_bps": min(day_sums) if day_sums else math.nan,
        "min_day_weighted_wait_gain_bps": min(weighted_day_sums) if weighted_day_sums else math.nan,
        "max_abs_decomposition_error_bps": float(numeric_series(group, "wait_decomposition_error_bps").abs().max()),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def grouped_summary(panel: pd.DataFrame, group_cols: list[str], scope: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if panel.empty:
        return rows
    for keys, group in panel.groupby(group_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {"summary_scope": scope}
        row.update({col: value for col, value in zip(group_cols, keys)})
        row.update(summarize_group(group))
        rows.append(row)
    return rows


def make_summary(panel: pd.DataFrame) -> list[dict[str, Any]]:
    group_cols = ["source", "family_id", "variant_id", "cell", "wait_sec", "horizon_sec"]
    rows = grouped_summary(panel, group_cols, "source_specific")
    dedup = panel[panel["dedup_keep"]].copy()
    if not dedup.empty:
        dedup["source"] = "all_dedup"
        rows.extend(grouped_summary(dedup, group_cols, "all_dedup"))
    rows.sort(
        key=lambda row: (
            str(row.get("summary_scope") or ""),
            str(row.get("source") or ""),
            int(row.get("horizon_sec") or 0),
            int(row.get("wait_sec") or 0),
            -float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        )
    )
    return rows


def make_by_day(panel: pd.DataFrame) -> list[dict[str, Any]]:
    group_cols = ["source", "family_id", "variant_id", "cell", "date", "wait_sec", "horizon_sec"]
    rows = grouped_summary(panel, group_cols, "source_specific")
    dedup = panel[panel["dedup_keep"]].copy()
    if not dedup.empty:
        dedup["source"] = "all_dedup"
        rows.extend(grouped_summary(dedup, group_cols, "all_dedup"))
    return rows


def bin_series(series: pd.Series, bins: int = 5) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() < bins or values.nunique(dropna=True) <= 1:
        return pd.Series(["all"] * len(series), index=series.index, dtype="object")
    try:
        out = pd.qcut(values.rank(method="first"), bins, labels=[f"q{i}" for i in range(1, bins + 1)])
        return out.astype("object").fillna("missing")
    except ValueError:
        return pd.Series(["all"] * len(series), index=series.index, dtype="object")


def make_buckets(panel: pd.DataFrame, min_events: int) -> list[dict[str, Any]]:
    factors = [
        "entry_spread_bps",
        "entry_cross_bps",
        "frames_since_mid_change",
        "trade_flow_imbalance",
        "top_depth",
        "top_depth_quote_min",
        "cell",
        "capacity_source",
    ]
    rows: list[dict[str, Any]] = []
    for (source, family_id, variant_id, wait, horizon), base in panel.groupby(
        ["source", "family_id", "variant_id", "wait_sec", "horizon_sec"], sort=True
    ):
        for factor in factors:
            if factor not in base.columns:
                continue
            work = base.copy()
            if factor in {"cell", "capacity_source"}:
                work["factor_bin"] = work[factor].astype(str).replace({"": "missing"})
            else:
                work["factor_bin"] = bin_series(work[factor])
            for factor_bin, group in work.groupby("factor_bin", sort=True):
                if len(group) < min_events:
                    continue
                values = pd.to_numeric(group[factor], errors="coerce") if factor not in {"cell", "capacity_source"} else pd.Series(dtype=float)
                row = {
                    "source": source,
                    "family_id": family_id,
                    "variant_id": variant_id,
                    "wait_sec": int(wait),
                    "horizon_sec": int(horizon),
                    "factor": factor,
                    "factor_bin": str(factor_bin),
                    "factor_min": float(values.min()) if not values.empty and values.notna().any() else None,
                    "factor_max": float(values.max()) if not values.empty and values.notna().any() else None,
                }
                row.update(summarize_group(group))
                rows.append(row)
    rows.sort(key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or -1e9), reverse=True)
    return rows


def policy_status(row: dict[str, Any], min_events: int) -> str:
    n = int(row.get("n") or 0)
    mean_gain = float(row.get("weighted_mean_wait_gain_bps") or math.nan)
    median_gain = float(row.get("median_wait_gain_bps") or math.nan)
    positive_days = float(row.get("positive_day_frac") or 0.0)
    min_day = float(row.get("min_day_weighted_wait_gain_bps") or math.nan)
    now_exec = float(row.get("mean_now_exec_bps") or math.nan)
    wait_exec = float(row.get("mean_wait_exec_bps") or math.nan)
    repair = float(row.get("mean_entry_cross_repair_bps") or 0.0)
    missed = float(row.get("mean_signed_mid_move_to_wait_bps") or 0.0)
    clean_spread_repair = repair > 0.25 and repair >= max(-missed, 0.0) and missed >= -0.25
    adverse_preentry_benefit = missed < -0.25 and (-missed) > max(repair, 0.0)
    if n < min_events:
        return "insufficient_sample"
    if max(now_exec, wait_exec) <= 0.0:
        return "skip_candidate"
    if mean_gain > 0.25 and median_gain > 0.0 and positive_days >= 2.0 / 3.0 and min_day > 0.0:
        if clean_spread_repair:
            return "spread_repair_wait_candidate"
        if adverse_preentry_benefit:
            return "adverse_preentry_move_observe_only"
        return "wait_candidate_other"
    if mean_gain < -0.25 and now_exec > 0.0:
        return "cross_now_candidate"
    return "observe_only"


def make_policy_candidates(summary_rows: list[dict[str, Any]], min_events: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in summary_rows:
        status = policy_status(row, min_events)
        if status in {"observe_only", "insufficient_sample"}:
            continue
        out = dict(row)
        out["policy_status"] = status
        if status == "spread_repair_wait_candidate":
            out["candidate_rule"] = f"spread_repair_wait_{int(row['wait_sec'])}s"
        elif status == "adverse_preentry_move_observe_only":
            out["candidate_rule"] = "requires_adverse_preentry_move_predictor"
        elif status == "cross_now_candidate":
            out["candidate_rule"] = "low_wait_value_cross_now"
        elif status == "skip_candidate":
            out["candidate_rule"] = "skip_unexecutable_candidate"
        else:
            out["candidate_rule"] = f"wait_{int(row['wait_sec'])}s"
        candidates.append(out)
    candidates.sort(
        key=lambda row: (
            str(row.get("policy_status")),
            float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        ),
        reverse=True,
    )
    return candidates


def format_float(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    return "" if value is None else f"{value:.{digits}f}"


def markdown_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int = 30) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows[:max_rows]:
        cells: list[str] = []
        for col in columns:
            value = row.get(col, "")
            cells.append(format_float(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(
    path: Path,
    *,
    summary_json: dict[str, Any],
    summary_rows: list[dict[str, Any]],
    policy_rows: list[dict[str, Any]],
    bucket_rows: list[dict[str, Any]],
) -> None:
    dedup_rows = [row for row in summary_rows if row.get("summary_scope") == "all_dedup"]
    executable_wait = sorted(
        [
            row
            for row in dedup_rows
            if str(row.get("source")) == "all_dedup"
            and float(row.get("weighted_mean_wait_gain_bps") or 0.0) > 0.25
            and max(float(row.get("mean_now_exec_bps") or -1e9), float(row.get("mean_wait_exec_bps") or -1e9)) > 0.0
        ],
        key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        reverse=True,
    )
    clean_spread_wait = sorted(
        [
            row
            for row in policy_rows
            if row.get("policy_status") == "spread_repair_wait_candidate"
            and row.get("summary_scope") == "all_dedup"
        ],
        key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        reverse=True,
    )
    adverse_preentry_wait = sorted(
        [
            row
            for row in dedup_rows
            if str(row.get("source")) == "all_dedup"
            and float(row.get("weighted_mean_wait_gain_bps") or 0.0) > 0.25
            and max(float(row.get("mean_now_exec_bps") or -1e9), float(row.get("mean_wait_exec_bps") or -1e9)) > 0.0
            and float(row.get("mean_signed_mid_move_to_wait_bps") or 0.0) < -0.25
            and -float(row.get("mean_signed_mid_move_to_wait_bps") or 0.0) >= max(
                float(row.get("mean_entry_cross_repair_bps") or 0.0), 0.0
            )
        ],
        key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        reverse=True,
    )
    cross_now = sorted(
        [
            row
            for row in dedup_rows
            if float(row.get("weighted_mean_wait_gain_bps") or 0.0) < -0.25
            and float(row.get("mean_now_exec_bps") or -1e9) > 0.0
        ],
        key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or 0.0),
    )
    skip_like = sorted(
        [
            row
            for row in policy_rows
            if row.get("policy_status") == "skip_candidate" and row.get("summary_scope") == "all_dedup"
        ],
        key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        reverse=True,
    )
    source_top = sorted(
        [
            row
            for row in summary_rows
            if row.get("summary_scope") == "source_specific"
            and max(float(row.get("mean_now_exec_bps") or -1e9), float(row.get("mean_wait_exec_bps") or -1e9)) > 0.0
        ],
        key=lambda row: float(row.get("weighted_mean_wait_gain_bps") or -1e9),
        reverse=True,
    )
    lines = [
        "# CCUSDT Taker/Wait Value Diagnostic v0.1",
        "",
        "Guardrail: `research_only_no_runtime_label_dependency_top_of_book_taker_only`.",
        "",
        "This diagnostic compares crossing immediately with waiting a short delay and then crossing at top of book while keeping the same fixed terminal horizon:",
        "",
        "```text",
        "G_i(delta, H) = Y_i^wait(delta, H) - Y_i^now(H)",
        "              = entry_cross_repair_i(delta) - signed_mid_move_to_wait_i(delta)",
        "```",
        "",
        "Future executable labels are diagnostic labels only. Runner/Bot/Monitor are not changed, maker/passive queue alpha remains paused, and no `date/`, scored entry, PnL, MFE, or MAE files are read as runtime input.",
        "",
        "## Scope",
        "",
        f"- symbol: `{summary_json['symbol']}`",
        f"- dates: `{summary_json['from_date']}..{summary_json['to_date']}`",
        f"- source_scope: `{summary_json['source_scope']}`",
        f"- waits_sec: `{summary_json['waits_sec']}`",
        f"- horizons_sec: `{summary_json['horizons_sec']}`",
        f"- candidate_count: `{summary_json['candidate_count']}`",
        f"- panel_rows: `{summary_json['panel_rows']}`",
        f"- max_abs_decomposition_error_bps: `{format_float(summary_json['max_abs_decomposition_error_bps'], 12)}`",
        f"- out_dir: `{summary_json['out_dir']}`",
        "",
        "## Readout",
        "",
        "- `wait_better` means waiting improves fixed-terminal executable value after paying top-of-book spread at the delayed entry.",
        "- `cross_now_better` means waiting loses more release than it saves in spread/crossing cost.",
        "- `skip_candidate` means neither now nor delayed entry has positive executable economics for that row.",
        "- `entry_cross_repair_bps` is the spread/crossing improvement from waiting; `signed_mid_move_to_wait_bps` is the release missed before delayed entry.",
        "- If `signed_mid_move_to_wait_bps < 0`, the delayed entry benefited because price moved against the intended side before entry. This is `adverse_preentry_move_benefit`, not clean spread repair.",
        "",
        "## Main Conclusion",
        "",
        "There is no clean, promoted spread-repair wait rule in this first pass. The current q70/idle01_g1 fast-entry cohort mostly wants to cross immediately when the stale-release structure is valid; positive wait surfaces are mainly either skip/mirage rows or adverse pre-entry movement rows that would require a separate runtime predictor.",
        "",
        "## Clean Spread-Repair Wait Candidates",
        "",
        "These rows require positive executable value, stable daily gain, and gain dominated by entry crossing repair rather than by price moving against the intended side before delayed entry.",
        "",
    ]
    lines.extend(
        markdown_table(
            clean_spread_wait,
            [
                "source",
                "family_id",
                "variant_id",
                "cell",
                "wait_sec",
                "horizon_sec",
                "n",
                "mean_now_exec_bps",
                "mean_wait_exec_bps",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
            ],
            20,
        )
    )
    lines.extend(
        [
            "",
            "## Adverse Pre-Entry Move Wait Surfaces",
            "",
            "These rows can look like wait value, but the gain is dominated by the mid moving against the intended side before the delayed cross. They are diagnostic evidence for a possible pre-entry adverse-move predictor, not a spread-repair admission rule.",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            adverse_preentry_wait,
            [
                "source",
                "family_id",
                "variant_id",
                "cell",
                "wait_sec",
                "horizon_sec",
                "n",
                "mean_now_exec_bps",
                "mean_wait_exec_bps",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
                "positive_day_frac",
            ],
            20,
        )
    )
    lines.extend(
        [
            "",
        "## Executable Wait Surfaces",
        "",
        "These rows have positive wait value and at least one positive mean executable label. They are not promoted policies; they are the first places where waiting is economically plausible rather than merely losing less.",
        "",
        ]
    )
    lines.extend(
        markdown_table(
            executable_wait,
            [
                "source",
                "family_id",
                "variant_id",
                "cell",
                "wait_sec",
                "horizon_sec",
                "n",
                "mean_now_exec_bps",
                "mean_wait_exec_bps",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
                "positive_day_frac",
            ],
            30,
        )
    )
    lines.extend(["", "## Cross-Now Surfaces", ""])
    lines.extend(
        markdown_table(
            cross_now,
            [
                "source",
                "family_id",
                "variant_id",
                "cell",
                "wait_sec",
                "horizon_sec",
                "n",
                "mean_now_exec_bps",
                "mean_wait_exec_bps",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
                "positive_day_frac",
            ],
            30,
        )
    )
    lines.extend(["", "## Skip / Spread-Cost Mirage Surfaces", ""])
    lines.extend(
        markdown_table(
            skip_like,
            [
                "source",
                "family_id",
                "variant_id",
                "cell",
                "wait_sec",
                "horizon_sec",
                "n",
                "mean_now_exec_bps",
                "mean_wait_exec_bps",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
                "positive_day_frac",
            ],
            30,
        )
    )
    lines.extend(["", "## Source-Specific Executable Top Rows", ""])
    lines.extend(
        markdown_table(
            source_top,
            [
                "source",
                "family_id",
                "variant_id",
                "cell",
                "wait_sec",
                "horizon_sec",
                "n",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
                "skip_rate",
                "positive_day_frac",
            ],
            40,
        )
    )
    lines.extend(["", "## Policy Candidate Rows", ""])
    lines.extend(
        markdown_table(
            policy_rows,
            [
                "summary_scope",
                "source",
                "family_id",
                "variant_id",
                "cell",
                "candidate_rule",
                "policy_status",
                "wait_sec",
                "horizon_sec",
                "n",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "aggregate_wait_mechanism",
                "median_wait_gain_bps",
                "positive_day_frac",
                "min_day_weighted_wait_gain_bps",
            ],
            50,
        )
    )
    lines.extend(["", "## Runtime Feature Buckets", ""])
    lines.extend(
        markdown_table(
            bucket_rows,
            [
                "source",
                "family_id",
                "variant_id",
                "factor",
                "factor_bin",
                "wait_sec",
                "horizon_sec",
                "n",
                "weighted_mean_wait_gain_bps",
                "mean_entry_cross_repair_bps",
                "mean_signed_mid_move_to_wait_bps",
                "positive_day_frac",
            ],
            60,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Rows where wait gain is positive because `entry_cross_repair_bps` dominates are admission candidates: wait for quote/spread repair before crossing.",
            "- Rows where wait gain is positive because `signed_mid_move_to_wait_bps` is negative are not spread repair. They say the market moved against the intended side before the delayed entry, so promotion would require a separate runtime-safe adverse-move predictor.",
            "- Rows where wait gain is negative because `signed_mid_move_to_wait_bps` dominates are cross-now candidates: the structure releases before the delayed entry.",
            "- Rows with positive mid/release intuition but non-positive `now_exec_bps` and `wait_exec_bps` are spread-cost mirages, not executable taker alpha.",
            "- Any candidate from this report still requires strict replay/profile-equivalence before promotion.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    waits_sec = parse_int_list(args.waits_sec)
    horizons_sec = parse_int_list(args.horizons_sec)
    out_dir = args.out_dir or (
        DEFAULT_OUT_ROOT / f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_v0_1"
    )
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    allowed_days = set(egd.date_range(args.from_date, args.to_date))
    frames_by_day: dict[str, pd.DataFrame] = {}
    quote_by_day: dict[str, QuoteIndex] = {}
    source_manifests: list[dict[str, Any]] = []
    for day in sorted(allowed_days):
        print(f"taker_wait_value load day={day}", file=sys.stderr, flush=True)
        raw_frames, manifest = egd.load_decision_frames(repo_root, args.symbol, day)
        enriched = sfr.enrich_structure_features(raw_frames, args.rolling_window, args.min_rolling_periods)
        frames_by_day[day] = enriched
        quote_by_day[day] = QuoteIndex.load(repo_root, args.symbol, day)
        source_manifests.append(
            {
                "date": day,
                "decision_frame_manifest_path": str(egd.decision_manifest_path(repo_root, args.symbol, day)),
                "decision_frame_rows": int(len(raw_frames)),
                "decision_frame_field_hash_sha256": manifest.get("field_hash_sha256"),
                "decision_frame_builder_version": manifest.get("builder_version"),
                "decision_frame_schema_version": manifest.get("schema_version"),
                "quote_frame_path": str(egd.quote_path(repo_root, args.symbol, day)),
            }
        )

    candidates: list[dict[str, Any]] = []
    fast_manifest: dict[str, Any] | None = None
    if args.source_scope in {"fast", "both"}:
        fast_candidates, fast_manifest = load_fast_candidates(repo_root, args, allowed_days, frames_by_day)
        candidates.extend(fast_candidates)
    if args.source_scope in {"structure", "both"}:
        for day, df in frames_by_day.items():
            candidates.extend(build_structure_candidates(day, df, args.refractory_us))

    if not candidates:
        raise ValueError("no candidates generated")

    dedup_keep_ids = dedup_candidate_ids(candidates)
    label_rows = build_label_rows(candidates, quote_by_day, waits_sec, horizons_sec, args.margin_bps, dedup_keep_ids)
    if not label_rows:
        raise ValueError("no valid wait/horizon label rows generated")
    panel = add_best_wait_columns(pd.DataFrame(label_rows))

    max_abs_decomp = float(pd.to_numeric(panel["wait_decomposition_error_bps"], errors="coerce").abs().max())
    if max_abs_decomp > 1e-8:
        raise ValueError(f"wait decomposition error too large: {max_abs_decomp}")

    summary_rows = make_summary(panel)
    by_day_rows = make_by_day(panel)
    bucket_rows = make_buckets(panel, args.min_events)
    policy_rows = make_policy_candidates(summary_rows, args.min_events)
    policy_status_counts: dict[str, int] = {}
    for row in policy_rows:
        status = str(row.get("policy_status") or "")
        policy_status_counts[status] = policy_status_counts.get(status, 0) + 1
    wait_mechanism_counts = {
        str(key): int(value)
        for key, value in panel["wait_mechanism"].astype(str).value_counts().to_dict().items()
    }

    pq.write_table(pa.Table.from_pandas(panel, preserve_index=False), out_dir / "wait_value_events.parquet", compression="zstd")
    write_csv(out_dir / "wait_value_summary.csv", summary_rows)
    write_csv(out_dir / "wait_value_by_day.csv", by_day_rows)
    write_csv(out_dir / "wait_value_buckets.csv", bucket_rows)
    write_csv(out_dir / "wait_policy_candidates.csv", policy_rows)

    fast_actual_count = fast_manifest.get("actual_entry_rows_in_window") if fast_manifest else None
    fast_candidate_count = fast_manifest.get("candidate_count") if fast_manifest else None
    if fast_actual_count is not None and fast_candidate_count != fast_actual_count:
        raise ValueError(f"fast candidate count mismatch: actual={fast_actual_count} candidates={fast_candidate_count}")

    elapsed_ms = int((time.time() - started) * 1000)
    summary_json = {
        "schema_id": "ccusdt_taker_wait_value_diagnostic_summary_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "source_scope": args.source_scope,
        "waits_sec": waits_sec,
        "horizons_sec": horizons_sec,
        "candidate_count": len(candidates),
        "dedup_candidate_count": len(dedup_keep_ids),
        "panel_rows": int(len(panel)),
        "fast_actual_entry_rows_in_window": fast_actual_count,
        "fast_candidate_count": fast_candidate_count,
        "max_abs_decomposition_error_bps": max_abs_decomp,
        "summary_rows": len(summary_rows),
        "by_day_rows": len(by_day_rows),
        "bucket_rows": len(bucket_rows),
        "policy_candidate_rows": len(policy_rows),
        "policy_status_counts": policy_status_counts,
        "wait_mechanism_counts": wait_mechanism_counts,
        "out_dir": str(out_dir),
        "report_path": str(report_path),
        "elapsed_wall_ms": elapsed_ms,
        "input_hash_sha256": stable_hash(
            {
                "args": {
                    "symbol": args.symbol,
                    "from_date": args.from_date,
                    "to_date": args.to_date,
                    "source_scope": args.source_scope,
                    "waits_sec": waits_sec,
                    "horizons_sec": horizons_sec,
                    "fast_run_id": args.fast_run_id,
                },
                "fast_manifest": fast_manifest,
                "source_manifests": source_manifests,
            }
        ),
        "boundary": (
            "research-only diagnostic; runtime features are exchange-visible at candidate time; "
            "future executable labels are computed inside this diagnostic only; "
            "Runner/Bot/Monitor are not modified; maker/passive queue alpha is paused"
        ),
        "fast_manifest": fast_manifest,
        "source_manifests": source_manifests,
        "outputs": {
            "wait_value_events_parquet": str(out_dir / "wait_value_events.parquet"),
            "wait_value_summary_csv": str(out_dir / "wait_value_summary.csv"),
            "wait_value_by_day_csv": str(out_dir / "wait_value_by_day.csv"),
            "wait_value_buckets_csv": str(out_dir / "wait_value_buckets.csv"),
            "wait_policy_candidates_csv": str(out_dir / "wait_policy_candidates.csv"),
            "summary_json": str(out_dir / "summary.json"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(report_path, summary_json=summary_json, summary_rows=summary_rows, policy_rows=policy_rows, bucket_rows=bucket_rows)
    print(json.dumps(summary_json, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
