#!/usr/bin/env python
"""Conditional wait / exit-timing diagnostic for CCUSDT q70 idle01_g1.

This is an offline diagnostic for existing-position exits only. It does not
model maker orders. For each exit decision it compares immediate top-of-book
taker exit with waiting tau seconds and then crossing:

    W_t(tau) = Y^T_{t+tau} - Y^T_t.

The resulting panel is market-derived and runtime-safe on the feature side;
post-exit path/flow fields are diagnostic labels, not strategy inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from maker_exit_opportunity import (  # type: ignore
    DayMarket,
    date_range,
    load_exit_candidates,
    optional_float,
    parse_run_specs,
    parse_ttls,
    path_hd,
    recent_features,
    repo_path,
    taker_net,
)


US_PER_SEC = 1_000_000

DEFAULT_RUN_SPECS = [
    (
        "fixed30_livecoherent",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_fixed30_taker_quoteidx_20260505_18_20260522",
    ),
    (
        "fixed45_livecoherent",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_fixed45_taker_quoteidx_20260505_18_20260522",
    ),
    (
        "fixed60_taker",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_20260505_18_20260522",
    ),
    (
        "stopping_rule_v1",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_stopping_rule_v1_quoteidx_20260505_18_20260522",
    ),
]

DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "conditional_wait_exit_q70_idle01_g1_20260505_18_20260522"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-conditional-wait-exit-opportunity-20260522.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-05")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--run-spec", action="append", help="Optional profile=path fast-run exits.")
    parser.add_argument("--ttl-sec", default="0.5,1,2,5,10")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--min-bin-count", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def file_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {"path": str(path), "exists": True, "byte_size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def wait_taker_price(entry_side: str, quote: Any) -> float:
    return float(quote.bid_px if entry_side == "buy" else quote.ask_px)


def post_path_features(
    market: DayMarket,
    *,
    entry_side: str,
    entry_bid: float,
    entry_ask: float,
    exit_ts_us: int,
    ttl_us: int,
    immediate_taker_net_bps: float,
    wait_taker_net_bps: float,
) -> dict[str, float]:
    path = market.quote_slice(exit_ts_us, exit_ts_us + ttl_us)
    if path.empty:
        deltas = np.asarray([0.0], dtype="float64")
    elif entry_side == "buy":
        values = np.log(path["bid_px"].to_numpy(dtype="float64") / entry_ask) * 10_000.0
        deltas = values - immediate_taker_net_bps
    else:
        values = np.log(entry_bid / path["ask_px"].to_numpy(dtype="float64")) * 10_000.0
        deltas = values - immediate_taker_net_bps
    deltas = deltas[np.isfinite(deltas)]
    if len(deltas) == 0:
        deltas = np.asarray([0.0], dtype="float64")
    peak = float(max(np.max(deltas), wait_taker_net_bps - immediate_taker_net_bps))
    trough = float(min(np.min(deltas), wait_taker_net_bps - immediate_taker_net_bps))
    final = float(wait_taker_net_bps - immediate_taker_net_bps)
    return {
        "post_wait_peak_bps": peak,
        "post_wait_trough_bps": trough,
        "post_wait_reclaim_bps": final - trough,
        "post_wait_peak_giveback_bps": peak - final,
        "post_wait_left_tail_bps": min(final, trough),
        "post_wait_max_delay_loss_bps": max(0.0, -trough),
    }


def post_flow_features(market: DayMarket, *, entry_side: str, exit_ts_us: int, ttl_us: int) -> dict[str, float]:
    trades = market.trade_slice(exit_ts_us, exit_ts_us + ttl_us)
    same_side = "buy" if entry_side == "buy" else "sell"
    if trades.empty:
        same_qty = 0.0
        opp_qty = 0.0
        same_notional = 0.0
        opp_notional = 0.0
        count = 0
    else:
        same = trades[trades["side"] == same_side]
        opp = trades[trades["side"] != same_side]
        same_qty = float(same["qty"].sum())
        opp_qty = float(opp["qty"].sum())
        same_notional = float(same["notional_quote"].sum())
        opp_notional = float(opp["notional_quote"].sum())
        count = int(len(trades))
    qty_denom = same_qty + opp_qty
    notional_denom = same_notional + opp_notional
    return {
        "post_trade_count": float(count),
        "post_same_flow_qty": same_qty,
        "post_opposite_flow_qty": opp_qty,
        "post_same_minus_opposite_qty": same_qty - opp_qty,
        "post_same_flow_imbalance": (same_qty - opp_qty) / qty_denom if qty_denom > 0.0 else 0.0,
        "post_same_notional_imbalance": (same_notional - opp_notional) / notional_denom
        if notional_denom > 0.0
        else 0.0,
    }


def top_depth_imbalance(entry_side: str, quote: Any) -> tuple[float, float]:
    denom = max(float(quote.bid_qty) + float(quote.ask_qty), 1e-12)
    raw = (float(quote.bid_qty) - float(quote.ask_qty)) / denom
    signed = raw if entry_side == "buy" else -raw
    return raw, signed


def build_panel(args: argparse.Namespace, repo_root: Path, run_specs: list[tuple[str, Path]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    days = date_range(args.from_date, args.to_date)
    ttls = parse_ttls(args.ttl_sec)
    exits = load_exit_candidates(run_specs, set(days))
    market_by_day = {day: DayMarket.load(repo_root, args.symbol, day) for day in days}
    rows: list[dict[str, Any]] = []
    for idx, exit_row in exits.iterrows():
        day = str(exit_row["date"])
        market = market_by_day[day]
        entry_side = str(exit_row["side"]).lower()
        direction = int(exit_row["direction"])
        entry_ts_us = int(exit_row["entry_ts_us"])
        exit_ts_us = int(exit_row["exit_ts_us"])
        entry_bid = float(exit_row["entry_bid"])
        entry_ask = float(exit_row["entry_ask"])
        exit_quote = market.quote_at_or_before(exit_ts_us)
        immediate_price = wait_taker_price(entry_side, exit_quote)
        immediate_net = taker_net(entry_side, entry_bid, entry_ask, immediate_price)
        h_bps, d_bps, l_bps = path_hd(
            market,
            entry_side=entry_side,
            entry_bid=entry_bid,
            entry_ask=entry_ask,
            entry_ts_us=entry_ts_us,
            exit_ts_us=exit_ts_us,
            immediate_taker_net_bps=immediate_net,
        )
        recent = recent_features(
            market,
            entry_side=entry_side,
            direction=direction,
            exit_ts_us=exit_ts_us,
            current_mid=float(exit_quote.mid_px),
        )
        decision_frame = market.decision_frame_at_or_before(exit_ts_us)
        depth_imbalance, signed_depth_imbalance = top_depth_imbalance(entry_side, exit_quote)
        base = {
            "schema_id": "ccusdt_conditional_wait_exit_event_v1",
            "runtime_safe": True,
            "date": day,
            "exit_profile_source": str(exit_row["exit_profile_source"]),
            "source_run_id": str(exit_row["source_run_id"]),
            "shadow_position_id": int(exit_row["shadow_position_id"]),
            "entry_seq": int(exit_row["entry_seq"]),
            "close_seq": int(exit_row["close_seq"]),
            "entry_ts_us": entry_ts_us,
            "exit_ts_us": exit_ts_us,
            "held_us": int(exit_row["held_us"]),
            "exit_sec": optional_float(exit_row.get("exit_sec")),
            "exit_reason": str(exit_row["exit_reason"]),
            "entry_side": entry_side,
            "exit_action": "sell" if entry_side == "buy" else "buy",
            "direction": direction,
            "cell": str(exit_row["cell"]),
            "membership_set": str(exit_row["membership_set"]),
            "actual_exposure": float(exit_row["actual_exposure"]),
            "requested_exposure": optional_float(exit_row.get("requested_exposure")),
            "capacity_source": str(exit_row["capacity_source"]),
            "entry_bid": entry_bid,
            "entry_ask": entry_ask,
            "entry_mid": float(exit_row["entry_mid"]),
            "exit_quote_ts_us": int(exit_quote.local_ts_us),
            "exit_bid": float(exit_quote.bid_px),
            "exit_ask": float(exit_quote.ask_px),
            "exit_mid": float(exit_quote.mid_px),
            "exit_spread_bps": float(exit_quote.spread_bps),
            "exit_bid_qty": float(exit_quote.bid_qty),
            "exit_ask_qty": float(exit_quote.ask_qty),
            "top_depth_imbalance": depth_imbalance,
            "signed_top_depth_imbalance": signed_depth_imbalance,
            "immediate_taker_price": immediate_price,
            "immediate_taker_net_bps": immediate_net,
            "path_h_bps": h_bps,
            "path_d_bps": d_bps,
            "path_l_bps": l_bps,
            "decision_trade_window_count": optional_float(decision_frame.get("trade_window_count")),
            "decision_trade_flow_imbalance": optional_float(decision_frame.get("trade_flow_imbalance")),
            "decision_frames_since_mid_change": optional_float(decision_frame.get("frames_since_mid_change")),
            "decision_past_event_25_bps": optional_float(decision_frame.get("past_event_25_bps")),
        }
        base.update(recent)
        for ttl in ttls:
            ttl_us = int(round(ttl * US_PER_SEC))
            wait_quote = market.quote_at_or_before(exit_ts_us + ttl_us)
            wait_price = wait_taker_price(entry_side, wait_quote)
            wait_net = taker_net(entry_side, entry_bid, entry_ask, wait_price)
            wait_value = wait_net - immediate_net
            row = dict(base)
            row.update(
                {
                    "ttl_sec": float(ttl),
                    "wait_quote_ts_us": int(wait_quote.local_ts_us),
                    "wait_taker_price": wait_price,
                    "wait_taker_net_bps": wait_net,
                    "wait_value_bps": wait_value,
                    "wait_benefit_bps": max(wait_value, 0.0),
                    "delay_loss_bps": max(-wait_value, 0.0),
                    "weighted_wait_value_bps": wait_value * float(exit_row["actual_exposure"]),
                    "weighted_delay_loss_bps": max(-wait_value, 0.0) * float(exit_row["actual_exposure"]),
                }
            )
            row.update(
                post_path_features(
                    market,
                    entry_side=entry_side,
                    entry_bid=entry_bid,
                    entry_ask=entry_ask,
                    exit_ts_us=exit_ts_us,
                    ttl_us=ttl_us,
                    immediate_taker_net_bps=immediate_net,
                    wait_taker_net_bps=wait_net,
                )
            )
            row.update(post_flow_features(market, entry_side=entry_side, exit_ts_us=exit_ts_us, ttl_us=ttl_us))
            rows.append(row)
        if (idx + 1) % 500 == 0:
            print(f"conditional wait panel processed exits={idx + 1}", flush=True)
    panel = pd.DataFrame(rows)
    manifest = {
        "schema_id": "ccusdt_conditional_wait_exit_input_manifest_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "run_specs": [{"profile": profile, "path": str(path), "exits": file_manifest(path / "exits.parquet")} for profile, path in run_specs],
        "ttl_sec": ttls,
        "boundary": (
            "runtime features are observed at or before exit decision; "
            "post-exit path/flow fields are diagnostic labels, not strategy inputs; "
            "no date/scored/future-label/PnL path files are read as runtime input"
        ),
    }
    return panel, manifest


def weighted_mean(df: pd.DataFrame, column: str) -> float:
    if df.empty:
        return 0.0
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce")
    ok = values.notna()
    if not ok.any():
        return 0.0
    denom = float(weights[ok].sum())
    if denom <= 0.0:
        return float(values[ok].mean())
    return float((weights[ok] * values[ok]).sum() / denom)


def weighted_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty:
        return 0.0
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return float((weights * values).sum())


def day_positive_frac(df: pd.DataFrame, column: str = "weighted_wait_value_bps") -> float:
    if df.empty:
        return 0.0
    values = [float(group[column].sum()) for _, group in df.groupby("date", sort=True)]
    return float(sum(1 for value in values if value > 0.0) / len(values)) if values else 0.0


def min_day_sum(df: pd.DataFrame, column: str = "weighted_wait_value_bps") -> float:
    if df.empty:
        return 0.0
    values = [float(group[column].sum()) for _, group in df.groupby("date", sort=True)]
    return min(values) if values else 0.0


def cvar_left(values: pd.Series, frac: float = 0.10) -> float:
    vals = pd.to_numeric(values, errors="coerce").dropna().sort_values()
    if vals.empty:
        return 0.0
    count = max(1, int(math.ceil(len(vals) * frac)))
    return float(vals.iloc[:count].mean())


def summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {}
    return {
        "n": int(len(group)),
        "exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "wait_positive_rate": float((pd.to_numeric(group["wait_value_bps"], errors="coerce").fillna(0.0) > 0.0).mean()),
        "weighted_mean_wait_value_bps": weighted_mean(group, "wait_value_bps"),
        "weighted_sum_wait_value_bps": weighted_sum(group, "wait_value_bps"),
        "weighted_mean_delay_loss_bps": weighted_mean(group, "delay_loss_bps"),
        "weighted_sum_delay_loss_bps": weighted_sum(group, "delay_loss_bps"),
        "mean_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").mean()),
        "p10_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").quantile(0.10)),
        "p50_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").quantile(0.50)),
        "p90_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").quantile(0.90)),
        "cvar10_wait_value_bps": cvar_left(group["wait_value_bps"], 0.10),
        "worst_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").min()),
        "weighted_mean_post_max_delay_loss_bps": weighted_mean(group, "post_wait_max_delay_loss_bps"),
        "weighted_mean_post_peak_giveback_bps": weighted_mean(group, "post_wait_peak_giveback_bps"),
        "weighted_mean_post_reclaim_bps": weighted_mean(group, "post_wait_reclaim_bps"),
        "positive_day_frac": day_positive_frac(group),
        "min_day_wait_sum_bps": min_day_sum(group),
    }


def ttl_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (profile, ttl), group in panel.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        row = {"exit_profile_source": profile, "ttl_sec": float(ttl)}
        row.update(summarize_group(group))
        rows.append(row)
    return pd.DataFrame(rows)


def by_day_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (profile, day, ttl), group in panel.groupby(["exit_profile_source", "date", "ttl_sec"], sort=True):
        row = {"exit_profile_source": profile, "date": day, "ttl_sec": float(ttl)}
        row.update(summarize_group(group))
        rows.append(row)
    return pd.DataFrame(rows)


def by_cell_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (profile, ttl, cell), group in panel.groupby(["exit_profile_source", "ttl_sec", "cell"], sort=True):
        row = {"exit_profile_source": profile, "ttl_sec": float(ttl), "cell": cell}
        row.update(summarize_group(group))
        rows.append(row)
    return pd.DataFrame(rows)


def bin_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 5 or numeric.nunique(dropna=True) < 2:
        return pd.Series(["all"] * len(series), index=series.index)
    try:
        return pd.qcut(numeric.rank(method="first"), q=5, labels=["q1", "q2", "q3", "q4", "q5"])
    except ValueError:
        return pd.Series(["all"] * len(series), index=series.index)


def factor_summary(panel: pd.DataFrame, min_count: int) -> pd.DataFrame:
    runtime_factors = [
        "path_h_bps",
        "path_d_bps",
        "exit_spread_bps",
        "signed_top_depth_imbalance",
        "same_flow_imbalance_5s",
        "same_minus_opposite_qty_5s",
        "recent_mid_alpha_5s_bps",
        "decision_frames_since_mid_change",
    ]
    diagnostic_factors = [
        "post_same_flow_imbalance",
        "post_same_minus_opposite_qty",
        "post_wait_reclaim_bps",
        "post_wait_peak_giveback_bps",
    ]
    rows = []
    for (profile, ttl), ttl_group in panel.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        for factor in runtime_factors + diagnostic_factors:
            if factor not in ttl_group.columns:
                continue
            work = ttl_group.copy()
            work["factor_bin"] = bin_series(work[factor])
            for bin_name, group in work.groupby("factor_bin", sort=True):
                if len(group) < min_count:
                    continue
                numeric = pd.to_numeric(group[factor], errors="coerce")
                row = {
                    "exit_profile_source": profile,
                    "ttl_sec": float(ttl),
                    "factor": factor,
                    "factor_role": "runtime_safe" if factor in runtime_factors else "post_exit_diagnostic_label",
                    "factor_bin": str(bin_name),
                    "factor_min": float(numeric.min()) if numeric.notna().any() else None,
                    "factor_max": float(numeric.max()) if numeric.notna().any() else None,
                }
                row.update(summarize_group(group))
                rows.append(row)
    return pd.DataFrame(rows)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    return "" if value is None else f"{value:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    use_cols = [col for col in columns if col in df.columns]
    view = df.loc[:, use_cols].head(max_rows)
    lines = ["| " + " | ".join(use_cols) + " |", "| " + " | ".join(["---"] * len(use_cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for col in use_cols:
            value = row[col]
            cells.append(fmt(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(path: Path, *, summary: dict[str, Any], ttl: pd.DataFrame, day: pd.DataFrame, cell: pd.DataFrame, factors: pd.DataFrame) -> None:
    ttl_view = ttl.sort_values(["exit_profile_source", "ttl_sec"])
    day_view = day.sort_values(["exit_profile_source", "ttl_sec", "date"])
    cell_view = cell.sort_values(["exit_profile_source", "ttl_sec", "weighted_sum_wait_value_bps"], ascending=[True, True, False])
    runtime_factor_view = factors[factors["factor_role"] == "runtime_safe"].sort_values(
        "weighted_sum_wait_value_bps", ascending=False
    )
    diag_factor_view = factors[factors["factor_role"] == "post_exit_diagnostic_label"].sort_values(
        "weighted_sum_wait_value_bps", ascending=False
    )
    best = runtime_factor_view.iloc[0].to_dict() if not runtime_factor_view.empty else {}
    lines = [
        "# CCUSDT q70 idle01_g1 conditional wait exit opportunity",
        "",
        "This diagnostic removes maker execution entirely. It compares immediate taker exit with wait-then-taker exit:",
        "",
        "\\[",
        "W_t(\\tau)=Y^T_{t+\\tau}-Y^T_t.",
        "\\]",
        "",
        "Runtime-safe bucket features are measured at or before the exit decision. Post-exit flow and reclaim fields are diagnostic labels only.",
        "",
        "## Scope",
        "",
        f"- Dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- Exit profiles: `{', '.join(summary['exit_profile_sources'])}`",
        f"- Actual exit candidates: `{summary['actual_exit_candidates']}`",
        f"- Panel rows: `{summary['panel_rows']}`",
        f"- TTL seconds: `{summary['ttl_sec']}`",
        f"- Output directory: `{summary['out_dir']}`",
        "",
        "## Readout",
        "",
        "- Whole-profile wait timing is a diagnostic surface, not a strategy by itself.",
        (
            f"- Strongest runtime-safe bucket: `{best.get('exit_profile_source', '')} / TTL={fmt(best.get('ttl_sec'), 1)}s / "
            f"{best.get('factor', '')}={best.get('factor_bin', '')}`, n `{best.get('n', '')}`, "
            f"weighted sum `{fmt(best.get('weighted_sum_wait_value_bps'))}`, "
            f"positive-day fraction `{fmt(best.get('positive_day_frac'))}`, "
            f"worst day `{fmt(best.get('min_day_wait_sum_bps'))}`."
            if best
            else "- No runtime-safe factor bucket available."
        ),
        "",
        "## TTL Summary",
        "",
    ]
    lines.extend(
        markdown_table(
            ttl_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "n",
                "exposure",
                "wait_positive_rate",
                "weighted_mean_wait_value_bps",
                "weighted_sum_wait_value_bps",
                "weighted_mean_delay_loss_bps",
                "worst_wait_value_bps",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Day Stability", ""])
    lines.extend(
        markdown_table(
            day_view,
            [
                "exit_profile_source",
                "date",
                "ttl_sec",
                "n",
                "exposure",
                "weighted_sum_wait_value_bps",
                "weighted_mean_wait_value_bps",
                "weighted_sum_delay_loss_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Cell Readout", ""])
    lines.extend(
        markdown_table(
            cell_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "cell",
                "n",
                "exposure",
                "weighted_sum_wait_value_bps",
                "weighted_mean_wait_value_bps",
                "worst_wait_value_bps",
                "positive_day_frac",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Runtime-Safe Factor Buckets", ""])
    lines.extend(
        markdown_table(
            runtime_factor_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "factor",
                "factor_bin",
                "n",
                "exposure",
                "weighted_sum_wait_value_bps",
                "weighted_mean_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Post-Exit Diagnostic Labels", ""])
    lines.extend(
        markdown_table(
            diag_factor_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "factor",
                "factor_bin",
                "n",
                "exposure",
                "weighted_sum_wait_value_bps",
                "weighted_mean_wait_value_bps",
                "positive_day_frac",
            ],
            max_rows=60,
        )
    )
    lines.extend(
        [
            "",
            "## Files",
            "",
            f"- Panel: `{summary['outputs']['panel_parquet']}`",
            f"- TTL summary: `{summary['outputs']['ttl_summary_csv']}`",
            f"- Factor summary: `{summary['outputs']['factor_summary_csv']}`",
            f"- Manifest: `{summary['outputs']['summary_json']}`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    start = time.perf_counter()
    repo_root = args.repo_root.resolve()
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    run_specs = parse_run_specs(args, repo_root)
    if args.run_spec is None:
        run_specs = [(name, repo_path(repo_root, Path(path))) for name, path in DEFAULT_RUN_SPECS]
    panel, input_manifest = build_panel(args, repo_root, run_specs)
    ttl = ttl_summary(panel)
    day = by_day_summary(panel)
    cell = by_cell_summary(panel)
    factors = factor_summary(panel, args.min_bin_count)

    panel_parquet = out_dir / "conditional_wait_exit_panel.parquet"
    panel_csv = out_dir / "conditional_wait_exit_panel.csv"
    ttl_csv = out_dir / "conditional_wait_exit_ttl_summary.csv"
    day_csv = out_dir / "conditional_wait_exit_by_day.csv"
    cell_csv = out_dir / "conditional_wait_exit_by_cell.csv"
    factor_csv = out_dir / "conditional_wait_exit_factor_summary.csv"
    write_parquet(panel_parquet, panel)
    write_csv(panel_csv, panel)
    write_csv(ttl_csv, ttl)
    write_csv(day_csv, day)
    write_csv(cell_csv, cell)
    write_csv(factor_csv, factors)
    (out_dir / "input_manifest.json").write_text(json.dumps(input_manifest, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "schema_id": "ccusdt_conditional_wait_exit_summary_v1",
        "ok": True,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "exit_profile_sources": [profile for profile, _ in run_specs],
        "actual_exit_candidates": int(panel[["exit_profile_source", "shadow_position_id", "exit_ts_us"]].drop_duplicates().shape[0]),
        "panel_rows": int(len(panel)),
        "ttl_sec": parse_ttls(args.ttl_sec),
        "out_dir": str(out_dir),
        "input_manifest_hash": stable_hash(input_manifest),
        "elapsed_wall_ms": int(round((time.perf_counter() - start) * 1000)),
        "outputs": {
            "panel_parquet": str(panel_parquet),
            "panel_csv": str(panel_csv),
            "ttl_summary_csv": str(ttl_csv),
            "by_day_csv": str(day_csv),
            "by_cell_csv": str(cell_csv),
            "factor_summary_csv": str(factor_csv),
            "summary_json": str(out_dir / "summary.json"),
            "input_manifest_json": str(out_dir / "input_manifest.json"),
            "report_md": str(report_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_report(report_path, summary=summary, ttl=ttl, day=day, cell=cell, factors=factors)
    print(json.dumps({"ok": True, "summary": str(out_dir / "summary.json"), "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
