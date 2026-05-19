#!/usr/bin/env python
"""CCUSDT per-entry tail and stop diagnostics.

Research-only diagnostics for the fixed snapshot-frame CCUSDT panel. This is
not an execution model, not queue-position fill evidence, not trading advice,
and not an alpha claim.

The purpose is narrower than the signal-path summary: rebuild selected entries
at per-entry granularity, then inspect right-tail dependence, cost stress,
quote-transition dependence, and whether stop-only exits save failed paths or
kill paths that recover by the fixed 60s exit.
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_signal_path_math as signal_math
import ccusdt_strategy_research as base


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)


RUN_TAG = "20260517_ccusdt_tail_stop_deep_dive_v1"
SOURCE_RUN_TAG = base.SOURCE_RUN_TAG
GUARDRAIL = "research_only_per_entry_tail_stop_diagnostics_no_execution_recommendation_no_alpha_claim"
US_PER_SECOND = base.US_PER_SECOND
EPS = base.EPS

TRIGGER_CLASSES = {
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
}


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def entry_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_entries_{self.run_tag}.csv"

    @property
    def stop_event_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_stop_events_{self.run_tag}.csv"

    @property
    def summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_summary_{self.run_tag}.csv"

    @property
    def cost_stress_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_cost_stress_{self.run_tag}.csv"

    @property
    def topk_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_topk_removal_{self.run_tag}.csv"

    @property
    def stop_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_stop_summary_{self.run_tag}.csv"

    @property
    def adverse_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_adverse_excursion_{self.run_tag}.csv"

    @property
    def day_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_day_leaveout_{self.run_tag}.csv"

    @property
    def matched_random_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_matched_random_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tail_stop_deep_dive_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / "v1-tail-stop-deep-dive.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT per-entry tail/stop deep-dive diagnostics.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--entry-bucket-sec", type=int, default=60)
    parser.add_argument("--stop-levels-bps", default="5,8,12,20")
    parser.add_argument("--stop-grace-sec", default="0,5,10")
    parser.add_argument("--cost-adders-bps", default="0,0.5,1,2,3,4,5")
    parser.add_argument("--bootstrap-iters", type=int, default=2000)
    parser.add_argument("--matched-random-iters", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260517)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_floats(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one float")
    return sorted(set(values))


def parse_ints(raw: str) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one integer")
    return sorted(set(values))


def finite(values: Iterable[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype="float64")
    return arr[np.isfinite(arr)]


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    arr = finite(values)
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    arr = finite(values)
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def lower_tail_mean(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = finite(values)
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def safe_rate(mask: Iterable[bool] | np.ndarray) -> float:
    arr = np.asarray(mask, dtype=bool)
    return float(arr.mean()) if len(arr) else np.nan


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    view = df.loc[:, [col for col in columns if col in df.columns]].head(max_rows).copy()
    lines = ["| " + " | ".join(view.columns) + " |", "| " + " | ".join(["---"] * len(view.columns)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for value in row:
            if isinstance(value, float):
                cells.append(fmt_num(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def day_arrays(df: pd.DataFrame) -> dict[int, dict[str, np.ndarray]]:
    out: dict[int, dict[str, np.ndarray]] = {}
    for code, g in df.groupby("date_code", sort=False):
        out[int(code)] = {
            "idx": g.index.to_numpy(dtype="int64"),
            "times": g["local_timestamp"].to_numpy(dtype="float64"),
            "mids": g["mid_price"].to_numpy(dtype="float64"),
            "spreads": g["spread_bps"].to_numpy(dtype="float64"),
            "mid_change_prev": g["mid_change_prev"].fillna(False).to_numpy(dtype=bool),
            "quote_change_prev": g["quote_change_prev"].fillna(False).to_numpy(dtype=bool),
        }
    return out


def cost_one(model: str, entry_spread: float, exit_spread: float) -> float:
    return float(base.cost_array(model, np.asarray([entry_spread]), np.asarray([exit_spread]))[0])


def build_specs() -> list[signal_math.TriggerSpec]:
    return [spec for spec in signal_math.trigger_specs() if spec.trigger_class in TRIGGER_CLASSES]


def build_entries_for_spec(
    df: pd.DataFrame,
    days: dict[int, dict[str, np.ndarray]],
    fold: base.Fold,
    spec: signal_math.TriggerSpec,
    stop_levels: list[float],
    stop_graces: list[int],
    timeout_sec: int,
    entry_bucket_sec: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_col = f"{target_col}_exit_idx"
    bucket_col = f"{target_col}_bucket"

    train_mask = df["date"].isin(fold.train_dates).to_numpy(dtype=bool)
    test_mask = df["date"].isin(fold.test_dates).to_numpy(dtype=bool)
    filters = base.build_filter_masks(df)
    filter_mask = filters[spec.filter_name]
    values = base.feature_values_for_fold(df, spec.feature, train_mask, {})
    mask, direction, q_low, q_high = base.build_policy_mask(
        values,
        train_mask,
        test_mask,
        filter_mask,
        spec.quantile,
        spec.policy,
    )
    entry_idx, selected_rows = signal_math.build_entry_idx(df, mask, direction, bucket_col, target_col, exit_col)

    date_codes_all = df["date_code"].to_numpy(dtype="int64")
    row_pos_all = df["row_pos_in_day"].to_numpy(dtype="int64")
    event_index_all = df.get("event_index", pd.Series(np.arange(len(df)))).to_numpy(dtype="int64")
    timestamp_all = df["local_timestamp"].to_numpy(dtype="float64")
    spread_all = df["spread_bps"].to_numpy(dtype="float64")
    feature_all = values
    trade_count_all = df.get("trade_window_count", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")
    frames_since_all = df.get("frames_since_mid_change", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")
    past25_all = df.get("past_event_25_bps", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")

    entry_rows: list[dict[str, object]] = []
    stop_rows: list[dict[str, object]] = []
    timeout_us = timeout_sec * US_PER_SECOND

    for entry in entry_idx:
        entry = int(entry)
        side = int(direction[entry])
        code = int(date_codes_all[entry])
        day = days.get(code)
        if side == 0 or day is None:
            continue
        local = int(row_pos_all[entry])
        times = day["times"]
        mids = day["mids"]
        idx = day["idx"]
        if local < 0 or local >= len(times) - 1:
            continue
        end_local = int(np.searchsorted(times, times[local] + timeout_us, side="left"))
        if end_local >= len(times):
            continue
        path_locals = np.arange(local + 1, end_local + 1, dtype="int64")
        if not len(path_locals):
            continue
        mid0 = max(float(mids[local]), EPS)
        path_rets = side * 10_000.0 * np.log(np.maximum(mids[path_locals], EPS) / mid0)
        if not np.isfinite(path_rets).any():
            continue

        path_idx = idx[path_locals]
        hold_path = (times[path_locals] - times[local]) / US_PER_SECOND
        final_exit = int(idx[end_local])
        final_gross = float(path_rets[-1])
        entry_spread = float(spread_all[entry]) if np.isfinite(spread_all[entry]) else np.nan
        final_spread = float(spread_all[final_exit]) if np.isfinite(spread_all[final_exit]) else np.nan
        maker_cost = cost_one("toy_maker_light", entry_spread, final_spread)
        taker_cost = cost_one("toy_taker_spread", entry_spread, final_spread)
        wide_cost = cost_one("toy_wide_stress", entry_spread, final_spread)
        mid_change_path = day["mid_change_prev"][path_locals]
        quote_change_path = day["quote_change_prev"][path_locals]
        first_mid_pos = np.flatnonzero(mid_change_path)
        first_quote_pos = np.flatnonzero(quote_change_path)
        first_mid_ret = float(path_rets[int(first_mid_pos[0])]) if len(first_mid_pos) else np.nan
        first_quote_ret = float(path_rets[int(first_quote_pos[0])]) if len(first_quote_pos) else np.nan
        first_mid_hold = float(hold_path[int(first_mid_pos[0])]) if len(first_mid_pos) else np.nan
        first_quote_hold = float(hold_path[int(first_quote_pos[0])]) if len(first_quote_pos) else np.nan

        base_row = {
            "run_tag": RUN_TAG,
            "source_run_tag": SOURCE_RUN_TAG,
            "guardrail": GUARDRAIL,
            "fold": fold.name,
            "train_start_date": fold.train_dates[0],
            "train_end_date": fold.train_dates[-1],
            "test_start_date": fold.test_dates[0],
            "test_end_date": fold.test_dates[-1],
            "trigger_class": spec.trigger_class,
            "mechanism": spec.mechanism,
            "feature": spec.feature,
            "policy": spec.policy,
            "filter": spec.filter_name,
            "quantile": spec.quantile,
            "q_low": q_low,
            "q_high": q_high,
            "selected_rows": selected_rows,
            "entries_before_path_filter": int(len(entry_idx)),
            "entry_row": entry,
            "entry_event_index": int(event_index_all[entry]),
            "date": str(df.at[entry, "date"]),
            "date_code": code,
            "entry_local_timestamp": float(timestamp_all[entry]),
            "direction": side,
            "feature_value": float(feature_all[entry]) if np.isfinite(feature_all[entry]) else np.nan,
            "entry_spread_bps": entry_spread,
            "trade_window_count": float(trade_count_all[entry]) if np.isfinite(trade_count_all[entry]) else np.nan,
            "frames_since_mid_change": float(frames_since_all[entry]) if np.isfinite(frames_since_all[entry]) else np.nan,
            "past_event_25_bps": float(past25_all[entry]) if np.isfinite(past25_all[entry]) else np.nan,
            "timeout_sec": timeout_sec,
            "final_exit_row": final_exit,
            "final_hold_sec": float((timestamp_all[final_exit] - timestamp_all[entry]) / US_PER_SECOND),
            "fixed_gross_bps": final_gross,
            "fixed_cost_maker_bps": maker_cost,
            "fixed_cost_taker_bps": taker_cost,
            "fixed_cost_wide_bps": wide_cost,
            "fixed_net_maker_bps": final_gross - maker_cost,
            "fixed_net_taker_bps": final_gross - taker_cost,
            "fixed_net_wide_bps": final_gross - wide_cost,
            "fixed_cross_maker": bool(final_gross > maker_cost),
            "fixed_cross_taker": bool(final_gross > taker_cost),
            "mfe_bps": float(np.nanmax(path_rets)),
            "mae_bps": float(np.nanmin(path_rets)),
            "has_mid_transition": bool(len(first_mid_pos)),
            "has_quote_transition": bool(len(first_quote_pos)),
            "mid_transition_count": int(mid_change_path.sum()),
            "quote_transition_count": int(quote_change_path.sum()),
            "first_mid_transition_hold_sec": first_mid_hold,
            "first_quote_transition_hold_sec": first_quote_hold,
            "first_mid_transition_gross_bps": first_mid_ret,
            "first_quote_transition_gross_bps": first_quote_ret,
        }
        entry_rows.append(base_row)

        for stop_bps in stop_levels:
            for grace_sec in stop_graces:
                stop_candidates = np.flatnonzero((hold_path >= float(grace_sec)) & (path_rets <= -float(stop_bps)))
                stop_hit = bool(len(stop_candidates))
                if stop_hit:
                    hit_pos = int(stop_candidates[0])
                    stop_exit = int(path_idx[hit_pos])
                    stop_gross = float(path_rets[hit_pos])
                    stop_hold = float(hold_path[hit_pos])
                    after_rets = path_rets[hit_pos:]
                    after_max = float(np.nanmax(after_rets))
                    after_final = final_gross
                else:
                    stop_exit = final_exit
                    stop_gross = final_gross
                    stop_hold = float((timestamp_all[final_exit] - timestamp_all[entry]) / US_PER_SECOND)
                    after_max = np.nan
                    after_final = np.nan
                stop_spread = float(spread_all[stop_exit]) if np.isfinite(spread_all[stop_exit]) else np.nan
                stop_cost = cost_one("toy_maker_light", entry_spread, stop_spread)
                stop_net = stop_gross - stop_cost
                fixed_net = final_gross - maker_cost
                stop_rows.append(
                    {
                        **{k: base_row[k] for k in [
                            "run_tag",
                            "source_run_tag",
                            "guardrail",
                            "fold",
                            "trigger_class",
                            "mechanism",
                            "feature",
                            "policy",
                            "filter",
                            "date",
                            "date_code",
                            "entry_row",
                            "direction",
                            "timeout_sec",
                        ]},
                        "stop_bps": stop_bps,
                        "grace_sec": grace_sec,
                        "stop_hit": stop_hit,
                        "stop_exit_row": stop_exit,
                        "stop_hold_sec": stop_hold,
                        "fixed_gross_bps": final_gross,
                        "fixed_cost_maker_bps": maker_cost,
                        "fixed_net_maker_bps": fixed_net,
                        "fixed_cross_maker": bool(final_gross > maker_cost),
                        "stop_gross_bps": stop_gross,
                        "stop_cost_maker_bps": stop_cost,
                        "stop_net_maker_bps": stop_net,
                        "delta_net_bps": stop_net - fixed_net,
                        "left_tail_saved_bps": max(stop_net - fixed_net, 0.0),
                        "recovery_killed_bps": max(fixed_net - stop_net, 0.0),
                        "stop_hit_fixed_cost_winner": bool(stop_hit and final_gross > maker_cost),
                        "stop_hit_fixed_net_positive": bool(stop_hit and fixed_net > 0.0),
                        "stop_hit_final_above_stop": bool(stop_hit and final_gross > stop_gross),
                        "after_stop_max_gross_bps": after_max,
                        "after_stop_final_gross_bps": after_final,
                    }
                )

    meta = {
        "fold": fold.name,
        "trigger_class": spec.trigger_class,
        "q_low": q_low,
        "q_high": q_high,
        "selected_rows": selected_rows,
        "entries_before_path_filter": int(len(entry_idx)),
        "filter_mask": filter_mask,
        "test_mask": test_mask,
        "target_col": target_col,
        "exit_col": exit_col,
    }
    return entry_rows, stop_rows, meta


def group_cols() -> list[str]:
    return ["fold", "trigger_class"]


def bootstrap_entry_mean(net: np.ndarray, rng: np.random.Generator, iters: int) -> tuple[float, float, float, float]:
    arr = finite(net)
    if len(arr) < 2:
        return np.nan, np.nan, np.nan, np.nan
    sample_idx = rng.integers(0, len(arr), size=(iters, len(arr)))
    means = arr[sample_idx].mean(axis=1)
    return (
        float(np.quantile(means, 0.05)),
        float(np.quantile(means, 0.50)),
        float(np.quantile(means, 0.95)),
        float((means > 0.0).mean()),
    )


def bootstrap_day_mean(g: pd.DataFrame, rng: np.random.Generator, iters: int) -> tuple[float, float, float, float]:
    daily = g.groupby("date", sort=True).agg(net=("fixed_net_maker_bps", "sum"), n=("fixed_net_maker_bps", "size"))
    if len(daily) < 2:
        return np.nan, np.nan, np.nan, np.nan
    net = daily["net"].to_numpy(dtype="float64")
    n = daily["n"].to_numpy(dtype="float64")
    sample_idx = rng.integers(0, len(daily), size=(iters, len(daily)))
    total_net = net[sample_idx].sum(axis=1)
    total_n = n[sample_idx].sum(axis=1)
    means = total_net / np.maximum(total_n, 1.0)
    return (
        float(np.quantile(means, 0.05)),
        float(np.quantile(means, 0.50)),
        float(np.quantile(means, 0.95)),
        float((means > 0.0).mean()),
    )


def winner_count_to_cover_total(net: np.ndarray) -> float:
    arr = finite(net)
    total = float(arr.sum()) if len(arr) else np.nan
    if not np.isfinite(total) or total <= 0.0:
        return np.nan
    winners = np.sort(arr[arr > 0.0])[::-1]
    if not len(winners):
        return np.nan
    cum = np.cumsum(winners)
    return float(np.searchsorted(cum, total, side="left") + 1)


def build_summary(entries: pd.DataFrame, rng: np.random.Generator, bootstrap_iters: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in entries.groupby(group_cols(), sort=True):
        fold, trigger = keys
        net = g["fixed_net_maker_bps"].to_numpy(dtype="float64")
        gross = g["fixed_gross_bps"].to_numpy(dtype="float64")
        total_net = float(np.nansum(net))
        sorted_net = np.sort(finite(net))[::-1]
        n = len(g)
        top1 = float(sorted_net[:1].sum() / total_net) if total_net > EPS and len(sorted_net) else np.nan
        top5 = float(sorted_net[: min(5, len(sorted_net))].sum() / total_net) if total_net > EPS and len(sorted_net) else np.nan
        top10n = max(1, int(math.ceil(n * 0.10))) if n else 0
        top10_net = float(sorted_net[:top10n].sum() / total_net) if total_net > EPS and len(sorted_net) else np.nan
        gross_sum = float(np.nansum(gross))
        q90_gross = finite_quantile(gross, 0.90)
        top10_gross = float(np.nansum(gross[gross >= q90_gross]) / gross_sum) if abs(gross_sum) > EPS else np.nan
        daily = g.groupby("date", sort=True)["fixed_net_maker_bps"].sum()
        entry_p05, entry_p50, entry_p95, entry_prob = bootstrap_entry_mean(net, rng, bootstrap_iters)
        day_p05, day_p50, day_p95, day_prob = bootstrap_day_mean(g, rng, bootstrap_iters)
        rows.append(
            {
                "fold": fold,
                "trigger_class": trigger,
                "entries": n,
                "net_mean_bps": finite_mean(net),
                "net_median_bps": finite_quantile(net, 0.50),
                "net_p10_bps": finite_quantile(net, 0.10),
                "net_cvar10_bps": lower_tail_mean(net, 0.10),
                "gross_mean_bps": finite_mean(gross),
                "cost_cross_rate": safe_rate(g["fixed_cross_maker"].to_numpy(dtype=bool)),
                "win_rate": safe_rate(net > 0.0),
                "profit_factor": float(net[net > 0].sum() / max(-net[net < 0].sum(), EPS)),
                "mfe_mean_bps": finite_mean(g["mfe_bps"]),
                "mae_mean_bps": finite_mean(g["mae_bps"]),
                "has_mid_transition_rate": safe_rate(g["has_mid_transition"].to_numpy(dtype=bool)),
                "has_quote_transition_rate": safe_rate(g["has_quote_transition"].to_numpy(dtype=bool)),
                "first_mid_transition_gross_mean_bps": finite_mean(g["first_mid_transition_gross_bps"]),
                "first_quote_transition_gross_mean_bps": finite_mean(g["first_quote_transition_gross_bps"]),
                "top1_net_share_of_total_net": top1,
                "top5_net_share_of_total_net": top5,
                "top10pct_net_share_of_total_net": top10_net,
                "top10_gross_share": top10_gross,
                "winner_count_to_cover_total_net": winner_count_to_cover_total(net),
                "positive_day_rate": safe_rate(daily.to_numpy(dtype="float64") > 0.0),
                "max_single_day_abs_share": float(np.abs(daily).max() / max(float(np.abs(daily).sum()), EPS)) if len(daily) else np.nan,
                "entry_boot_mean_p05_bps": entry_p05,
                "entry_boot_mean_p50_bps": entry_p50,
                "entry_boot_mean_p95_bps": entry_p95,
                "entry_boot_prob_mean_gt0": entry_prob,
                "day_boot_mean_p05_bps": day_p05,
                "day_boot_mean_p50_bps": day_p50,
                "day_boot_mean_p95_bps": day_p95,
                "day_boot_prob_mean_gt0": day_prob,
            }
        )
    return pd.DataFrame(rows).sort_values(["fold", "net_mean_bps"], ascending=[True, False])


def build_cost_stress(entries: pd.DataFrame, adders: list[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in entries.groupby(group_cols(), sort=True):
        fold, trigger = keys
        gross = g["fixed_gross_bps"].to_numpy(dtype="float64")
        base_cost = g["fixed_cost_maker_bps"].to_numpy(dtype="float64")
        for adder in adders:
            cost = base_cost + adder
            net = gross - cost
            cross = gross > cost
            winners = gross[cross] - cost[cross]
            losers = cost[~cross] - gross[~cross]
            a = safe_rate(cross)
            b = finite_mean(winners)
            d = finite_mean(losers)
            rows.append(
                {
                    "fold": fold,
                    "trigger_class": trigger,
                    "cost_adder_bps": adder,
                    "entries": len(g),
                    "net_mean_bps": finite_mean(net),
                    "net_median_bps": finite_quantile(net, 0.50),
                    "net_cvar10_bps": lower_tail_mean(net, 0.10),
                    "A_cost_cross_rate": a,
                    "B_winner_excess_bps": b,
                    "D_loser_shortfall_bps": d,
                    "E_edge_bps": a * b - (1.0 - a) * d if np.isfinite(a) and np.isfinite(b) and np.isfinite(d) else np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values(["fold", "trigger_class", "cost_adder_bps"])


def build_topk(entries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in entries.groupby(group_cols(), sort=True):
        fold, trigger = keys
        ordered = g.sort_values("fixed_net_maker_bps", ascending=False).reset_index(drop=True)
        n = len(ordered)
        ks = sorted(set([0, 1, 3, 5, 10, max(1, math.ceil(n * 0.01)), max(1, math.ceil(n * 0.05)), max(1, math.ceil(n * 0.10))]))
        for k in ks:
            rem = ordered.iloc[k:] if k else ordered
            net = rem["fixed_net_maker_bps"].to_numpy(dtype="float64")
            rows.append(
                {
                    "fold": fold,
                    "trigger_class": trigger,
                    "removed_top_net_winners": k,
                    "remaining_entries": len(rem),
                    "net_mean_bps": finite_mean(net),
                    "net_median_bps": finite_quantile(net, 0.50),
                    "net_sum_bps": float(np.nansum(net)) if len(net) else np.nan,
                    "win_rate": safe_rate(net > 0.0),
                }
            )
    return pd.DataFrame(rows).sort_values(["fold", "trigger_class", "removed_top_net_winners"])


def build_stop_summary(stops: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in stops.groupby(["fold", "trigger_class", "stop_bps", "grace_sec"], sort=True):
        fold, trigger, stop_bps, grace_sec = keys
        hit = g["stop_hit"].to_numpy(dtype=bool)
        fixed_cross = g["fixed_cross_maker"].to_numpy(dtype=bool)
        fixed_net = g["fixed_net_maker_bps"].to_numpy(dtype="float64")
        stop_net = g["stop_net_maker_bps"].to_numpy(dtype="float64")
        delta = stop_net - fixed_net
        hit_g = g[hit]
        saved_mean = finite_mean(g["left_tail_saved_bps"])
        killed_mean = finite_mean(g["recovery_killed_bps"])
        save_to_kill = saved_mean / killed_mean if np.isfinite(killed_mean) and killed_mean > EPS else np.nan
        rows.append(
            {
                "fold": fold,
                "trigger_class": trigger,
                "stop_bps": stop_bps,
                "grace_sec": grace_sec,
                "entries": len(g),
                "stop_hit_rate": safe_rate(hit),
                "fixed_net_mean_bps": finite_mean(fixed_net),
                "stop_net_mean_bps": finite_mean(stop_net),
                "delta_net_mean_bps": finite_mean(delta),
                "fixed_net_median_bps": finite_quantile(fixed_net, 0.50),
                "stop_net_median_bps": finite_quantile(stop_net, 0.50),
                "fixed_cvar10_bps": lower_tail_mean(fixed_net, 0.10),
                "stop_cvar10_bps": lower_tail_mean(stop_net, 0.10),
                "delta_cvar10_bps": lower_tail_mean(stop_net, 0.10) - lower_tail_mean(fixed_net, 0.10),
                "left_tail_saved_bps": saved_mean,
                "recovery_killed_bps": killed_mean,
                "save_to_kill_ratio": save_to_kill,
                "stop_hit_fixed_cost_winner_uncond_rate": safe_rate(hit & fixed_cross),
                "stop_given_fixed_cost_winner_rate": float((hit & fixed_cross).sum() / max(fixed_cross.sum(), 1)),
                "hit_recover_to_cost_rate": safe_rate(hit_g["fixed_cross_maker"].to_numpy(dtype=bool)) if len(hit_g) else np.nan,
                "hit_stop_better_rate": safe_rate(hit_g["delta_net_bps"].to_numpy(dtype="float64") > 0.0) if len(hit_g) else np.nan,
                "hit_final_above_stop_rate": safe_rate(hit_g["stop_hit_final_above_stop"].to_numpy(dtype=bool)) if len(hit_g) else np.nan,
                "hit_recovery_killed_mean_bps": finite_mean(hit_g["recovery_killed_bps"]) if len(hit_g) else np.nan,
                "hit_left_tail_saved_mean_bps": finite_mean(hit_g["left_tail_saved_bps"]) if len(hit_g) else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["fold", "trigger_class", "stop_bps", "grace_sec"])


def build_adverse_excursion(entries: pd.DataFrame, levels: list[float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in entries.groupby(group_cols(), sort=True):
        fold, trigger = keys
        for level in levels:
            touched = g["mae_bps"].to_numpy(dtype="float64") <= -float(level)
            sub = g[touched]
            net = sub["fixed_net_maker_bps"].to_numpy(dtype="float64") if len(sub) else np.asarray([], dtype="float64")
            rows.append(
                {
                    "fold": fold,
                    "trigger_class": trigger,
                    "adverse_level_bps": level,
                    "entries": len(g),
                    "touch_rate": safe_rate(touched),
                    "touched_entries": int(touched.sum()),
                    "touched_final_net_mean_bps": finite_mean(net),
                    "touched_final_net_median_bps": finite_quantile(net, 0.50),
                    "touched_recover_to_cost_rate": safe_rate(sub["fixed_cross_maker"].to_numpy(dtype=bool)) if len(sub) else np.nan,
                    "touched_positive_net_rate": safe_rate(net > 0.0) if len(sub) else np.nan,
                    "touched_cvar10_bps": lower_tail_mean(net, 0.10),
                }
            )
    return pd.DataFrame(rows).sort_values(["fold", "trigger_class", "adverse_level_bps"])


def build_day_leaveout(entries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for keys, g in entries.groupby(group_cols(), sort=True):
        fold, trigger = keys
        daily = g.groupby("date", sort=True).agg(day_net_sum_bps=("fixed_net_maker_bps", "sum"), day_entries=("fixed_net_maker_bps", "size"))
        total_net = float(daily["day_net_sum_bps"].sum())
        total_n = int(daily["day_entries"].sum())
        for date, row in daily.iterrows():
            n_wo = total_n - int(row["day_entries"])
            rows.append(
                {
                    "fold": fold,
                    "trigger_class": trigger,
                    "date": date,
                    "day_entries": int(row["day_entries"]),
                    "day_net_sum_bps": float(row["day_net_sum_bps"]),
                    "day_net_mean_bps": float(row["day_net_sum_bps"] / max(int(row["day_entries"]), 1)),
                    "mean_without_day_bps": float((total_net - float(row["day_net_sum_bps"])) / max(n_wo, 1)) if n_wo else np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values(["fold", "trigger_class", "date"])


def matched_random_for_spec(
    df: pd.DataFrame,
    spec_meta: dict[str, object],
    signal_entries: pd.DataFrame,
    rng: np.random.Generator,
    iters: int,
) -> dict[str, object]:
    if signal_entries.empty:
        return {}
    filter_mask = np.asarray(spec_meta["filter_mask"], dtype=bool)
    test_mask = np.asarray(spec_meta["test_mask"], dtype=bool)
    target_col = str(spec_meta["target_col"])
    exit_col = str(spec_meta["exit_col"])
    valid = filter_mask & test_mask & np.isfinite(df[target_col].to_numpy(dtype="float64")) & (df[exit_col].to_numpy(dtype="int64") >= 0)
    date_values = df["date"].astype(str).to_numpy()
    spread = df["spread_bps"].to_numpy(dtype="float64")
    target = df[target_col].to_numpy(dtype="float64")
    exit_idx = df[exit_col].to_numpy(dtype="int64")
    pools: dict[str, np.ndarray] = {}
    for date in signal_entries["date"].unique():
        pools[str(date)] = np.flatnonzero(valid & (date_values == str(date)))

    signal_mean = float(signal_entries["fixed_net_maker_bps"].mean())
    means: list[float] = []
    medians: list[float] = []
    for _ in range(iters):
        sampled_net: list[float] = []
        for row in signal_entries.itertuples(index=False):
            pool = pools.get(str(row.date))
            if pool is None or not len(pool):
                continue
            picked = int(pool[int(rng.integers(0, len(pool)))])
            side = int(row.direction)
            gross = side * float(target[picked])
            cost = cost_one("toy_maker_light", float(spread[picked]), float(spread[int(exit_idx[picked])]))
            sampled_net.append(gross - cost)
        if sampled_net:
            arr = np.asarray(sampled_net, dtype="float64")
            means.append(float(arr.mean()))
            medians.append(float(np.median(arr)))
    mean_arr = np.asarray(means, dtype="float64")
    med_arr = np.asarray(medians, dtype="float64")
    return {
        "fold": spec_meta["fold"],
        "trigger_class": spec_meta["trigger_class"],
        "entries": len(signal_entries),
        "signal_mean_bps": signal_mean,
        "signal_median_bps": float(signal_entries["fixed_net_maker_bps"].median()),
        "matched_random_mean_p05_bps": float(np.quantile(mean_arr, 0.05)) if len(mean_arr) else np.nan,
        "matched_random_mean_p50_bps": float(np.quantile(mean_arr, 0.50)) if len(mean_arr) else np.nan,
        "matched_random_mean_p95_bps": float(np.quantile(mean_arr, 0.95)) if len(mean_arr) else np.nan,
        "matched_random_median_p50_bps": float(np.quantile(med_arr, 0.50)) if len(med_arr) else np.nan,
        "prob_random_mean_ge_signal": float((mean_arr >= signal_mean).mean()) if len(mean_arr) else np.nan,
        "signal_minus_random_p50_bps": signal_mean - float(np.quantile(mean_arr, 0.50)) if len(mean_arr) else np.nan,
    }


def build_report(
    paths: Paths,
    summary: pd.DataFrame,
    cost_stress: pd.DataFrame,
    topk: pd.DataFrame,
    stop_summary: pd.DataFrame,
    adverse: pd.DataFrame,
    day_leaveout: pd.DataFrame,
    matched_random: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT Tail And Stop Deep Dive")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from source panel `{paths.source_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This is a per-entry research diagnostic over a snapshot-frame factor panel. It is not queue-position fill evidence, not a live execution simulation, not trading advice, and not an alpha claim."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Per-entry rows: `{int(summary['entries'].sum()) if not summary.empty else 0}` across `{len(summary)}` fold/trigger groups.")
    lines.append("- Trigger focus: `tfi_follow_flat`, `tfi_short_flat`, `tfi_long_flat`, `tfi_short_stale25`, `tfi_event_active`.")
    lines.append("- Horizon: fixed `60s` entries, first signal per `60s` bucket.")
    lines.append("- Stop-only levels: `5, 8, 12, 20` bps with `0s, 5s, 10s` grace.")
    lines.append("")

    lines.append("## Per-Entry Summary")
    lines.extend(
        markdown_table(
            summary.sort_values(["fold", "net_mean_bps"], ascending=[True, False]),
            [
                "fold",
                "trigger_class",
                "entries",
                "net_mean_bps",
                "net_median_bps",
                "net_cvar10_bps",
                "has_mid_transition_rate",
                "top5_net_share_of_total_net",
                "top10pct_net_share_of_total_net",
                "winner_count_to_cover_total_net",
                "day_boot_mean_p05_bps",
                "day_boot_prob_mean_gt0",
            ],
            20,
        )
    )
    lines.append("")

    lines.append("## Cost Stress")
    stress_view = cost_stress[cost_stress["cost_adder_bps"].isin([0.0, 1.0, 2.0, 3.0, 5.0])].copy()
    lines.extend(
        markdown_table(
            stress_view,
            [
                "fold",
                "trigger_class",
                "cost_adder_bps",
                "entries",
                "net_mean_bps",
                "net_median_bps",
                "A_cost_cross_rate",
                "B_winner_excess_bps",
                "D_loser_shortfall_bps",
            ],
            40,
        )
    )
    lines.append("")

    lines.append("## Top Winner Removal")
    topk_view = topk[topk["removed_top_net_winners"].isin([0, 1, 3, 5, 10])].copy()
    lines.extend(
        markdown_table(
            topk_view,
            [
                "fold",
                "trigger_class",
                "removed_top_net_winners",
                "remaining_entries",
                "net_mean_bps",
                "net_median_bps",
                "win_rate",
            ],
            60,
        )
    )
    lines.append("")

    lines.append("## Stop Deep Read")
    stop_view = stop_summary[
        (stop_summary["stop_bps"].isin([5.0, 20.0])) & (stop_summary["grace_sec"].isin([0, 5]))
    ].copy()
    lines.extend(
        markdown_table(
            stop_view,
            [
                "fold",
                "trigger_class",
                "stop_bps",
                "grace_sec",
                "stop_hit_rate",
                "delta_net_mean_bps",
                "delta_cvar10_bps",
                "stop_net_median_bps",
                "hit_recover_to_cost_rate",
                "hit_stop_better_rate",
                "hit_final_above_stop_rate",
                "save_to_kill_ratio",
            ],
            60,
        )
    )
    lines.append("")

    lines.append("## Adverse Excursion Recovery")
    adverse_view = adverse[adverse["adverse_level_bps"].isin([5.0, 8.0, 20.0])].copy()
    lines.extend(
        markdown_table(
            adverse_view,
            [
                "fold",
                "trigger_class",
                "adverse_level_bps",
                "touch_rate",
                "touched_entries",
                "touched_final_net_mean_bps",
                "touched_recover_to_cost_rate",
                "touched_positive_net_rate",
            ],
            60,
        )
    )
    lines.append("")

    lines.append("## Matched Random")
    lines.extend(
        markdown_table(
            matched_random,
            [
                "fold",
                "trigger_class",
                "entries",
                "signal_mean_bps",
                "matched_random_mean_p50_bps",
                "matched_random_mean_p95_bps",
                "prob_random_mean_ge_signal",
                "signal_minus_random_p50_bps",
            ],
            20,
        )
    )
    lines.append("")

    lines.append("## Output Tables")
    lines.append("")
    for path in [
        paths.entry_csv,
        paths.stop_event_csv,
        paths.summary_csv,
        paths.cost_stress_csv,
        paths.topk_csv,
        paths.stop_summary_csv,
        paths.adverse_csv,
        paths.day_csv,
        paths.matched_random_csv,
        paths.summary_json,
    ]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("python scripts/ccusdt_tail_stop_deep_dive.py")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    stop_levels = parse_floats(args.stop_levels_bps)
    stop_graces = parse_ints(args.stop_grace_sec)
    cost_adders = parse_floats(args.cost_adders_bps)
    rng = np.random.default_rng(args.seed)

    base_paths = base.Paths(
        panel_root=paths.panel_root,
        source_run_tag=paths.source_run_tag,
        date_dir=paths.date_dir,
        doc_dir=paths.doc_dir,
        run_tag=base.RUN_TAG,
        method_sweep_run_tag=base.METHOD_SWEEP_RUN_TAG,
    )
    df, usable = base.load_panel(base_paths)
    if "trade_flow_imbalance" not in usable:
        raise RuntimeError("trade_flow_imbalance missing from panel")
    df, _targets = base.add_replay_labels(df, event_horizons=[25], time_horizons_sec=[args.timeout_sec])
    dates = sorted(df["date"].unique())
    folds = base.make_folds(dates)
    days = day_arrays(df)
    specs = build_specs()
    print(
        f"tail stop deep dive specs={len(specs)} folds={len(folds)} stop_levels={stop_levels} graces={stop_graces}",
        flush=True,
    )

    entry_rows: list[dict[str, object]] = []
    stop_rows: list[dict[str, object]] = []
    metas: list[dict[str, object]] = []
    for fold in folds:
        print(f"fold={fold.name} test={fold.test_dates[0]}..{fold.test_dates[-1]}", flush=True)
        for spec in specs:
            rows, stops, meta = build_entries_for_spec(
                df,
                days,
                fold,
                spec,
                stop_levels,
                stop_graces,
                args.timeout_sec,
                args.entry_bucket_sec,
            )
            print(f"  {spec.trigger_class} entries={len(rows)} selected={meta['selected_rows']}", flush=True)
            entry_rows.extend(rows)
            stop_rows.extend(stops)
            metas.append(meta)

    entries = pd.DataFrame(entry_rows)
    stops = pd.DataFrame(stop_rows)
    if entries.empty:
        raise RuntimeError("no entries built")

    summary = build_summary(entries, rng, args.bootstrap_iters)
    cost_stress = build_cost_stress(entries, cost_adders)
    topk = build_topk(entries)
    stop_summary = build_stop_summary(stops)
    adverse = build_adverse_excursion(entries, stop_levels)
    day_leaveout = build_day_leaveout(entries)

    matched_rows: list[dict[str, object]] = []
    for meta in metas:
        sig = entries[(entries["fold"] == meta["fold"]) & (entries["trigger_class"] == meta["trigger_class"])]
        row = matched_random_for_spec(df, meta, sig, rng, args.matched_random_iters)
        if row:
            matched_rows.append(row)
    matched_random = pd.DataFrame(matched_rows).sort_values(["fold", "trigger_class"])

    entries.to_csv(paths.entry_csv, index=False)
    stops.to_csv(paths.stop_event_csv, index=False)
    summary.to_csv(paths.summary_csv, index=False)
    cost_stress.to_csv(paths.cost_stress_csv, index=False)
    topk.to_csv(paths.topk_csv, index=False)
    stop_summary.to_csv(paths.stop_summary_csv, index=False)
    adverse.to_csv(paths.adverse_csv, index=False)
    day_leaveout.to_csv(paths.day_csv, index=False)
    matched_random.to_csv(paths.matched_random_csv, index=False)

    summary_payload = {
        "run_tag": paths.run_tag,
        "source_run_tag": paths.source_run_tag,
        "guardrail": GUARDRAIL,
        "entry_rows": int(len(entries)),
        "stop_event_rows": int(len(stops)),
        "summary_rows": int(len(summary)),
        "cost_stress_rows": int(len(cost_stress)),
        "topk_rows": int(len(topk)),
        "stop_summary_rows": int(len(stop_summary)),
        "adverse_rows": int(len(adverse)),
        "day_leaveout_rows": int(len(day_leaveout)),
        "matched_random_rows": int(len(matched_random)),
        "outputs": {
            "entries": str(paths.entry_csv),
            "stop_events": str(paths.stop_event_csv),
            "summary": str(paths.summary_csv),
            "cost_stress": str(paths.cost_stress_csv),
            "topk": str(paths.topk_csv),
            "stop_summary": str(paths.stop_summary_csv),
            "adverse": str(paths.adverse_csv),
            "day_leaveout": str(paths.day_csv),
            "matched_random": str(paths.matched_random_csv),
            "report": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    build_report(paths, summary, cost_stress, topk, stop_summary, adverse, day_leaveout, matched_random)
    print(f"wrote {paths.report_md}", flush=True)
    print(f"wrote {paths.summary_csv}", flush=True)


if __name__ == "__main__":
    main()
