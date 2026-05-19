#!/usr/bin/env python
"""CCUSDT triple-barrier strategy sweep.

Research-only diagnostics over the fixed snapshot-frame CCUSDT factor panel.
This script turns the strongest toy replay rules into first-hit TP/SL/timeout
experiments. It does not download data, modify raw files, model queue position,
or emit trading advice.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_strategy_research as base


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)


GUARDRAIL = "research_only_barrier_sweep_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260517_ccusdt_barrier_sweep_v1"
SOURCE_RUN_TAG = base.SOURCE_RUN_TAG
STRATEGY_RUN_TAG = base.RUN_TAG
US_PER_SECOND = base.US_PER_SECOND
EPS = base.EPS


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    run_tag: str
    strategy_run_tag: str
    method_sweep_run_tag: str

    @property
    def quality_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_barrier_sweep_quality_{self.run_tag}.csv"

    @property
    def entry_specs_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_barrier_sweep_entry_specs_{self.run_tag}.csv"

    @property
    def candidate_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_barrier_sweep_candidates_{self.run_tag}.csv"

    @property
    def control_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_barrier_sweep_controls_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_barrier_sweep_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / "v1-barrier-sweep.md"

    @property
    def prior_candidate_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_strategy_research_candidates_{self.strategy_run_tag}.csv"


@dataclass(frozen=True)
class EntrySpec:
    feature: str
    policy: str
    filter_name: str
    quantile: float
    source: str

    @property
    def key(self) -> tuple[str, str, str, float]:
        return (self.feature, self.policy, self.filter_name, round(float(self.quantile), 6))


@dataclass
class PathOutcomes:
    entry_idx: np.ndarray
    direction: np.ndarray
    date_codes: np.ndarray
    final_exit_idx: np.ndarray
    final_return_bps: np.ndarray
    final_hold_sec: np.ndarray
    mfe_bps: np.ndarray
    mae_bps: np.ndarray
    entry_spread_bps: np.ndarray
    up_exit_idx: np.ndarray
    down_exit_idx: np.ndarray
    up_return_bps: np.ndarray
    down_return_bps: np.ndarray
    up_hold_sec: np.ndarray
    down_hold_sec: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT triple-barrier strategy sweep.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--strategy-run-tag", default=STRATEGY_RUN_TAG)
    parser.add_argument("--method-sweep-run-tag", default=base.METHOD_SWEEP_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--timeouts-sec", default="10,60")
    parser.add_argument("--upper-bps", default="2,5,8,12")
    parser.add_argument("--lower-bps", default="2,5,8,12")
    parser.add_argument("--quantiles", default="0.8,0.9")
    parser.add_argument(
        "--features",
        default="trade_flow_imbalance,mlofi_roll10_l1,combo_trade_mlofi_l1,combo_book_pressure",
    )
    parser.add_argument(
        "--filters",
        default="past25_abs_le_0p5bps,trade_present_stale_mid_ge25,stale_mid_ge25,stale_mid_ge70",
    )
    parser.add_argument("--policies", default="follow_extremes,short_low,long_high")
    parser.add_argument("--max-entry-specs", type=int, default=6)
    parser.add_argument("--top-control-rows", type=int, default=30)
    parser.add_argument("--control-shift-events", type=int, default=500)
    parser.add_argument("--account-quote", type=float, default=100.0)
    parser.add_argument("--settlement-modes", default="observed_mid")
    parser.add_argument("--cost-models", default="toy_mid,toy_maker_light,toy_taker_spread,toy_wide_stress")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_strings(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one string")
    return values


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


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def quality_rows(df: pd.DataFrame, timeouts_sec: list[int]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, g in df.groupby("date", sort=True):
        row: dict[str, object] = {
            "run_tag": RUN_TAG,
            "source_run_tag": SOURCE_RUN_TAG,
            "date": date,
            "rows": int(len(g)),
            "distinct_mid": int(g["mid_price"].nunique(dropna=True)),
            "quote_change_rate": base.finite_mean(g["quote_change_prev"].astype(float).to_numpy()),
            "top_size_change_rate": base.finite_mean(g["top_size_change_prev"].astype(float).to_numpy()),
            "trade_present_rate": base.finite_mean((g["trade_window_count"].fillna(0) > 0).astype(float).to_numpy()),
            "spread_p50_bps": base.finite_quantile(g["spread_bps"].to_numpy(dtype="float64"), 0.50),
            "spread_p95_bps": base.finite_quantile(g["spread_bps"].to_numpy(dtype="float64"), 0.95),
            "guardrail": GUARDRAIL,
        }
        for timeout in timeouts_sec:
            target = f"fwd_time_{timeout}s_bps"
            if target in g.columns:
                values = g[target].to_numpy(dtype="float64")
                valid = np.isfinite(values)
                row[f"{target}_valid_rows"] = int(valid.sum())
                row[f"{target}_abs_p90_bps"] = base.finite_quantile(np.abs(values[valid]), 0.90)
        rows.append(row)
    return pd.DataFrame(rows)


def append_spec(specs: list[EntrySpec], seen: set[tuple[str, str, str, float]], spec: EntrySpec) -> None:
    if spec.key in seen:
        return
    seen.add(spec.key)
    specs.append(spec)


def build_entry_specs(
    paths: Paths,
    features: list[str],
    filters: list[str],
    policies: list[str],
    quantiles: list[float],
    max_entry_specs: int,
) -> pd.DataFrame:
    allowed_features = set(features)
    allowed_filters = set(filters)
    allowed_policies = set(policies)
    allowed_quantiles = {round(q, 6) for q in quantiles}
    specs: list[EntrySpec] = []
    seen: set[tuple[str, str, str, float]] = set()

    manual_specs = [
        ("trade_flow_imbalance", "follow_extremes", "past25_abs_le_0p5bps", 0.8),
        ("trade_flow_imbalance", "short_low", "past25_abs_le_0p5bps", 0.8),
        ("trade_flow_imbalance", "follow_extremes", "stale_mid_ge25", 0.8),
        ("trade_flow_imbalance", "short_low", "stale_mid_ge25", 0.8),
        ("trade_flow_imbalance", "long_high", "trade_present_stale_mid_ge25", 0.8),
        ("mlofi_roll10_l1", "follow_extremes", "trade_present_stale_mid_ge25", 0.9),
        ("mlofi_roll10_l1", "short_low", "trade_present_stale_mid_ge25", 0.9),
        ("combo_trade_mlofi_l1", "follow_extremes", "trade_present_stale_mid_ge25", 0.9),
        ("combo_trade_mlofi_l1", "short_low", "trade_present_stale_mid_ge25", 0.9),
        ("combo_book_pressure", "short_low", "trade_present_stale_mid_ge25", 0.9),
    ]
    for feature, policy, filter_name, quantile in manual_specs:
        if (
            feature in allowed_features
            and policy in allowed_policies
            and filter_name in allowed_filters
            and round(quantile, 6) in allowed_quantiles
        ):
            append_spec(specs, seen, EntrySpec(feature, policy, filter_name, quantile, "manual_primary"))

    if paths.prior_candidate_csv.exists():
        prior = pd.read_csv(paths.prior_candidate_csv)
        for col in ["score", "entries", "net_mean_bps", "gross_mean_bps"]:
            prior[col] = pd.to_numeric(prior[col], errors="coerce")
        prior["quantile"] = pd.to_numeric(prior["quantile"], errors="coerce")
        status_rank = {
            "survives_toy_cost_research_probe": 4,
            "gross_positive_research_probe": 3,
            "gross_only_cost_failed": 2,
            "negative_or_flat": 1,
        }
        prior["status_rank"] = prior["research_status"].map(status_rank).fillna(0)
        prior = prior[
            prior["feature"].isin(allowed_features)
            & prior["filter"].isin(allowed_filters)
            & prior["policy"].isin(allowed_policies)
            & prior["quantile"].round(6).isin(allowed_quantiles)
            & prior["cost_model"].isin(["toy_maker_light", "toy_taker_spread", "toy_mid"])
            & prior["entries"].ge(40)
        ].copy()
        prior = prior.sort_values(["status_rank", "score", "net_mean_bps", "entries"], ascending=False)
        for row in prior.itertuples(index=False):
            append_spec(
                specs,
                seen,
                EntrySpec(str(row.feature), str(row.policy), str(row.filter), float(row.quantile), "prior_ranked"),
            )
            if len(specs) >= max_entry_specs:
                break

    for feature in features:
        for policy in policies:
            for filter_name in filters:
                for quantile in quantiles:
                    append_spec(specs, seen, EntrySpec(feature, policy, filter_name, quantile, "fallback_grid"))
                    if len(specs) >= max_entry_specs:
                        break
                if len(specs) >= max_entry_specs:
                    break
            if len(specs) >= max_entry_specs:
                break
        if len(specs) >= max_entry_specs:
            break

    return pd.DataFrame([spec.__dict__ for spec in specs[:max_entry_specs]])


def day_arrays(df: pd.DataFrame) -> dict[int, dict[str, np.ndarray]]:
    out: dict[int, dict[str, np.ndarray]] = {}
    for code, g in df.groupby("date_code", sort=False):
        idx = g.index.to_numpy(dtype="int64")
        out[int(code)] = {
            "idx": idx,
            "times": g["local_timestamp"].to_numpy(dtype="float64"),
            "mids": g["mid_price"].to_numpy(dtype="float64"),
        }
    return out


def flat_to_flat_keep(entry_idx: np.ndarray, exit_idx: np.ndarray) -> np.ndarray:
    keep: list[int] = []
    last_exit = -1
    for pos, (entry, exit_) in enumerate(zip(entry_idx, exit_idx)):
        if int(entry) > last_exit:
            keep.append(pos)
            last_exit = int(exit_)
    return np.asarray(keep, dtype="int64")


def build_path_outcomes(
    df: pd.DataFrame,
    days: dict[int, dict[str, np.ndarray]],
    candidate_idx: np.ndarray,
    direction: np.ndarray,
    timeout_sec: int,
    upper_bps: list[float],
    lower_bps: list[float],
) -> PathOutcomes:
    date_codes_all = df["date_code"].to_numpy(dtype="int64")
    row_pos_all = df["row_pos_in_day"].to_numpy(dtype="int64")
    times_all = df["local_timestamp"].to_numpy(dtype="float64")
    mids_all = df["mid_price"].to_numpy(dtype="float64")
    spread_all = df["spread_bps"].to_numpy(dtype="float64")
    timeout_us = timeout_sec * US_PER_SECOND

    valid_entries: list[int] = []
    valid_dirs: list[int] = []
    valid_date_codes: list[int] = []
    final_exits: list[int] = []
    final_rets: list[float] = []
    final_holds: list[float] = []
    mfe_values: list[float] = []
    mae_values: list[float] = []
    entry_spreads: list[float] = []
    up_exit_rows: list[list[int]] = []
    down_exit_rows: list[list[int]] = []
    up_ret_rows: list[list[float]] = []
    down_ret_rows: list[list[float]] = []
    up_hold_rows: list[list[float]] = []
    down_hold_rows: list[list[float]] = []

    for entry in candidate_idx:
        entry = int(entry)
        side = int(direction[entry])
        if side == 0:
            continue
        code = int(date_codes_all[entry])
        day = days.get(code)
        if day is None:
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
        if len(path_locals) == 0:
            continue
        mid0 = max(float(mids[local]), EPS)
        path_rets = side * 10_000.0 * np.log(np.maximum(mids[path_locals], EPS) / mid0)
        if not np.isfinite(path_rets).any():
            continue

        up_exits: list[int] = []
        down_exits: list[int] = []
        up_rets: list[float] = []
        down_rets: list[float] = []
        up_holds: list[float] = []
        down_holds: list[float] = []
        for upper in upper_bps:
            hit = np.flatnonzero(path_rets >= upper)
            if len(hit):
                hit_local = int(path_locals[int(hit[0])])
                up_exits.append(int(idx[hit_local]))
                up_rets.append(float(path_rets[int(hit[0])]))
                up_holds.append(float((times[hit_local] - times[local]) / US_PER_SECOND))
            else:
                up_exits.append(-1)
                up_rets.append(np.nan)
                up_holds.append(np.nan)
        for lower in lower_bps:
            hit = np.flatnonzero(path_rets <= -lower)
            if len(hit):
                hit_local = int(path_locals[int(hit[0])])
                down_exits.append(int(idx[hit_local]))
                down_rets.append(float(path_rets[int(hit[0])]))
                down_holds.append(float((times[hit_local] - times[local]) / US_PER_SECOND))
            else:
                down_exits.append(-1)
                down_rets.append(np.nan)
                down_holds.append(np.nan)

        final_exit = int(idx[end_local])
        valid_entries.append(entry)
        valid_dirs.append(side)
        valid_date_codes.append(code)
        final_exits.append(final_exit)
        final_rets.append(float(path_rets[-1]))
        final_holds.append(float((times_all[final_exit] - times_all[entry]) / US_PER_SECOND))
        mfe_values.append(float(np.nanmax(path_rets)))
        mae_values.append(float(np.nanmin(path_rets)))
        entry_spreads.append(float(spread_all[entry]) if np.isfinite(spread_all[entry]) else np.nan)
        up_exit_rows.append(up_exits)
        down_exit_rows.append(down_exits)
        up_ret_rows.append(up_rets)
        down_ret_rows.append(down_rets)
        up_hold_rows.append(up_holds)
        down_hold_rows.append(down_holds)

    n = len(valid_entries)
    if n == 0:
        empty_i = np.empty((0,), dtype="int64")
        empty_f = np.empty((0,), dtype="float64")
        return PathOutcomes(
            empty_i,
            empty_i.astype("int8"),
            empty_i,
            empty_i,
            empty_f,
            empty_f,
            empty_f,
            empty_f,
            empty_f,
            np.empty((0, len(upper_bps)), dtype="int64"),
            np.empty((0, len(lower_bps)), dtype="int64"),
            np.empty((0, len(upper_bps)), dtype="float64"),
            np.empty((0, len(lower_bps)), dtype="float64"),
            np.empty((0, len(upper_bps)), dtype="float64"),
            np.empty((0, len(lower_bps)), dtype="float64"),
        )

    return PathOutcomes(
        entry_idx=np.asarray(valid_entries, dtype="int64"),
        direction=np.asarray(valid_dirs, dtype="int8"),
        date_codes=np.asarray(valid_date_codes, dtype="int64"),
        final_exit_idx=np.asarray(final_exits, dtype="int64"),
        final_return_bps=np.asarray(final_rets, dtype="float64"),
        final_hold_sec=np.asarray(final_holds, dtype="float64"),
        mfe_bps=np.asarray(mfe_values, dtype="float64"),
        mae_bps=np.asarray(mae_values, dtype="float64"),
        entry_spread_bps=np.asarray(entry_spreads, dtype="float64"),
        up_exit_idx=np.asarray(up_exit_rows, dtype="int64"),
        down_exit_idx=np.asarray(down_exit_rows, dtype="int64"),
        up_return_bps=np.asarray(up_ret_rows, dtype="float64"),
        down_return_bps=np.asarray(down_ret_rows, dtype="float64"),
        up_hold_sec=np.asarray(up_hold_rows, dtype="float64"),
        down_hold_sec=np.asarray(down_hold_rows, dtype="float64"),
    )


def profit_factor(net: np.ndarray) -> float:
    gains = float(net[net > 0].sum())
    losses = float(-net[net < 0].sum())
    if losses <= EPS:
        return np.inf if gains > EPS else np.nan
    return gains / losses


def row_status(row: dict[str, object]) -> str:
    entries = int(row["entries"])
    net_mean = float(row["net_mean_bps"])
    gross_mean = float(row["gross_mean_bps"])
    positive_day_rate = float(row["positive_day_rate"]) if np.isfinite(float(row["positive_day_rate"])) else np.nan
    max_day_share = float(row["max_single_day_abs_share"]) if np.isfinite(float(row["max_single_day_abs_share"])) else np.nan
    pf = float(row["profit_factor"]) if np.isfinite(float(row["profit_factor"])) else np.nan
    cost_model = str(row["cost_model"])
    if entries < 40:
        return "too_few_flat_entries"
    if (
        cost_model != "toy_mid"
        and net_mean > 0.0
        and positive_day_rate >= 0.55
        and max_day_share <= 0.45
        and pf > 1.0
    ):
        return "survives_toy_cost_barrier_probe"
    if gross_mean > 0.0 and net_mean <= 0.0:
        return "gross_only_cost_failed"
    if gross_mean > 0.0:
        return "gross_positive_barrier_probe"
    return "negative_or_flat"


def metric_row(
    df: pd.DataFrame,
    outcomes: PathOutcomes,
    selected_rows: int,
    upper: float,
    lower: float,
    upper_i: int,
    lower_i: int,
    timeout_sec: int,
    settlement: str,
    cost_model: str,
    base_fields: dict[str, object],
    account_quote: float,
) -> dict[str, object]:
    up_idx = outcomes.up_exit_idx[:, upper_i]
    down_idx = outcomes.down_exit_idx[:, lower_i]
    up_hit = up_idx >= 0
    down_hit = down_idx >= 0
    up_first = up_hit & (~down_hit | (up_idx < down_idx))
    down_first = down_hit & (~up_hit | (down_idx < up_idx))
    timeout = ~(up_first | down_first)

    exit_idx = np.where(up_first, up_idx, np.where(down_first, down_idx, outcomes.final_exit_idx))
    if settlement == "observed_mid":
        gross = np.where(
            up_first,
            outcomes.up_return_bps[:, upper_i],
            np.where(down_first, outcomes.down_return_bps[:, lower_i], outcomes.final_return_bps),
        )
    elif settlement == "clipped_barrier":
        gross = np.where(up_first, upper, np.where(down_first, -lower, outcomes.final_return_bps))
    else:
        raise ValueError(f"unknown settlement mode {settlement}")
    hold_sec = np.where(
        up_first,
        outcomes.up_hold_sec[:, upper_i],
        np.where(down_first, outcomes.down_hold_sec[:, lower_i], outcomes.final_hold_sec),
    )

    valid = np.isfinite(gross) & (exit_idx >= 0)
    if not valid.any():
        row = {
            **base_fields,
            "timeout_sec": timeout_sec,
            "upper_bps": upper,
            "lower_bps": lower,
            "settlement": settlement,
            "cost_model": cost_model,
            "selected_rows": selected_rows,
            "entries": 0,
            "tp_rate": np.nan,
            "sl_rate": np.nan,
            "timeout_rate": np.nan,
            "gross_mean_bps": np.nan,
            "gross_median_bps": np.nan,
            "net_mean_bps": np.nan,
            "net_median_bps": np.nan,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "positive_day_rate": np.nan,
            "daily_net_mean_bps": np.nan,
            "daily_net_t_stat": np.nan,
            "max_single_day_abs_share": np.nan,
            "avg_cost_bps": np.nan,
            "avg_hold_sec": np.nan,
            "mfe_mean_bps": np.nan,
            "mae_mean_bps": np.nan,
            "net_mean_usd_per_100": np.nan,
            "linear_1000_trades_pct": np.nan,
            "score": np.nan,
            "research_status": "no_entries",
            "guardrail": GUARDRAIL,
        }
        return row

    keep0 = np.flatnonzero(valid)
    keep = keep0[flat_to_flat_keep(outcomes.entry_idx[valid], exit_idx[valid])]
    if len(keep) == 0:
        valid = np.zeros_like(valid, dtype=bool)
    else:
        valid = np.zeros_like(valid, dtype=bool)
        valid[keep] = True

    gross = gross[valid]
    exit_idx = exit_idx[valid].astype("int64")
    hold_sec = hold_sec[valid]
    entry_spread = outcomes.entry_spread_bps[valid]
    exit_spread = df["spread_bps"].to_numpy(dtype="float64")[exit_idx]
    costs = base.cost_array(cost_model, entry_spread, exit_spread)
    net = gross - costs
    date_codes = outcomes.date_codes[valid]
    positive_day_rate, daily_mean, daily_t, max_share = base.daily_stats(net, date_codes)
    entries = len(net)
    score = base.finite_mean(net)
    if np.isfinite(score):
        consistency = positive_day_rate - 0.5 if np.isfinite(positive_day_rate) else 0.0
        concentration_penalty = max(0.0, max_share - 0.45) if np.isfinite(max_share) else 0.0
        score = score * math.sqrt(min(entries, 2000) / 500.0) + 2.0 * consistency - 2.0 * concentration_penalty

    row = {
        **base_fields,
        "timeout_sec": timeout_sec,
        "upper_bps": upper,
        "lower_bps": lower,
        "settlement": settlement,
        "cost_model": cost_model,
        "selected_rows": selected_rows,
        "entries": int(entries),
        "tp_rate": float(up_first[valid].mean()) if entries else np.nan,
        "sl_rate": float(down_first[valid].mean()) if entries else np.nan,
        "timeout_rate": float(timeout[valid].mean()) if entries else np.nan,
        "gross_mean_bps": base.finite_mean(gross),
        "gross_median_bps": base.finite_quantile(gross, 0.50),
        "net_mean_bps": base.finite_mean(net),
        "net_median_bps": base.finite_quantile(net, 0.50),
        "win_rate": float((net > 0.0).mean()) if entries else np.nan,
        "profit_factor": profit_factor(net),
        "positive_day_rate": positive_day_rate,
        "daily_net_mean_bps": daily_mean,
        "daily_net_t_stat": daily_t,
        "max_single_day_abs_share": max_share,
        "avg_cost_bps": base.finite_mean(costs),
        "avg_hold_sec": base.finite_mean(hold_sec),
        "mfe_mean_bps": base.finite_mean(outcomes.mfe_bps[valid]),
        "mae_mean_bps": base.finite_mean(outcomes.mae_bps[valid]),
        "net_mean_usd_per_100": base.finite_mean(net) * (account_quote / 10_000.0),
        "linear_1000_trades_pct": base.finite_mean(net) * 10.0,
        "score": score,
        "guardrail": GUARDRAIL,
    }
    row["research_status"] = row_status(row)
    return row


def evaluate_one_config(
    df: pd.DataFrame,
    days: dict[int, dict[str, np.ndarray]],
    candidate_idx: np.ndarray,
    direction: np.ndarray,
    selected_rows: int,
    timeout_sec: int,
    upper: float,
    lower: float,
    upper_bps: list[float],
    lower_bps: list[float],
    settlement: str,
    cost_models: list[str],
    base_fields: dict[str, object],
    account_quote: float,
) -> list[dict[str, object]]:
    outcomes = build_path_outcomes(df, days, candidate_idx, direction, timeout_sec, upper_bps, lower_bps)
    if len(outcomes.entry_idx) == 0:
        upper_i = upper_bps.index(upper)
        lower_i = lower_bps.index(lower)
        return [
            metric_row(
                df,
                outcomes,
                selected_rows,
                upper,
                lower,
                upper_i,
                lower_i,
                timeout_sec,
                settlement,
                cost_model,
                base_fields,
                account_quote,
            )
            for cost_model in cost_models
        ]
    upper_i = upper_bps.index(upper)
    lower_i = lower_bps.index(lower)
    return [
        metric_row(
            df,
            outcomes,
            selected_rows,
            upper,
            lower,
            upper_i,
            lower_i,
            timeout_sec,
            settlement,
            cost_model,
            base_fields,
            account_quote,
        )
        for cost_model in cost_models
    ]


def run_sweep(
    df: pd.DataFrame,
    folds: list[base.Fold],
    entry_specs: pd.DataFrame,
    filters: dict[str, np.ndarray],
    timeouts_sec: list[int],
    upper_bps: list[float],
    lower_bps: list[float],
    settlement_modes: list[str],
    cost_models: list[str],
    account_quote: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    days = day_arrays(df)
    dates = df["date"].astype(str).to_numpy()
    feature_cache: dict[tuple[str, bytes], np.ndarray] = {}
    for fold in folds:
        train_mask = np.isin(dates, fold.train_dates)
        test_mask = np.isin(dates, fold.test_dates)
        print(f"barrier fold={fold.name} train_days={len(fold.train_dates)} test_days={len(fold.test_dates)}", flush=True)
        for spec_row in entry_specs.itertuples(index=False):
            spec = EntrySpec(
                feature=str(spec_row.feature),
                policy=str(spec_row.policy),
                filter_name=str(spec_row.filter_name),
                quantile=float(spec_row.quantile),
                source=str(spec_row.source),
            )
            values = base.feature_values_for_fold(df, spec.feature, train_mask, feature_cache)
            mask, direction, q_low, q_high = base.build_policy_mask(
                values,
                train_mask,
                test_mask,
                filters[spec.filter_name],
                spec.quantile,
                spec.policy,
            )
            candidate_idx = np.flatnonzero(mask & (direction != 0))
            selected_rows = int(len(candidate_idx))
            if selected_rows == 0:
                continue
            base_fields = {
                "run_tag": RUN_TAG,
                "source_run_tag": SOURCE_RUN_TAG,
                "fold": fold.name,
                "train_start_date": fold.train_dates[0],
                "train_end_date": fold.train_dates[-1],
                "test_start_date": fold.test_dates[0],
                "test_end_date": fold.test_dates[-1],
                "entry_source": spec.source,
                "feature": spec.feature,
                "feature_family": base.feature_family(spec.feature),
                "policy": spec.policy,
                "filter": spec.filter_name,
                "quantile": spec.quantile,
                "q_low": q_low,
                "q_high": q_high,
            }
            for timeout_sec in timeouts_sec:
                outcomes = build_path_outcomes(df, days, candidate_idx, direction, timeout_sec, upper_bps, lower_bps)
                print(
                    f"  spec={spec.feature}/{spec.policy}/{spec.filter_name}/q{spec.quantile:g} "
                    f"timeout={timeout_sec}s candidates={selected_rows} valid={len(outcomes.entry_idx)}",
                    flush=True,
                )
                for upper_i, upper in enumerate(upper_bps):
                    for lower_i, lower in enumerate(lower_bps):
                        for settlement in settlement_modes:
                            for cost_model in cost_models:
                                rows.append(
                                    metric_row(
                                        df,
                                        outcomes,
                                        selected_rows,
                                        upper,
                                        lower,
                                        upper_i,
                                        lower_i,
                                        timeout_sec,
                                        settlement,
                                        cost_model,
                                        base_fields,
                                        account_quote,
                                    )
                                )
    return pd.DataFrame(rows)


def run_controls(
    df: pd.DataFrame,
    folds: list[base.Fold],
    candidates: pd.DataFrame,
    filters: dict[str, np.ndarray],
    timeouts_sec: list[int],
    upper_bps: list[float],
    lower_bps: list[float],
    account_quote: float,
    top_n: int,
    shift_events: int,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    work = candidates.copy()
    for col in ["score", "entries", "net_mean_bps", "gross_mean_bps"]:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work[
        work["cost_model"].eq("toy_mid")
        & work["settlement"].eq("observed_mid")
        & work["entries"].ge(40)
        & np.isfinite(work["score"])
    ].sort_values("score", ascending=False)
    work = work.drop_duplicates(subset=["fold", "feature", "policy", "filter", "quantile", "timeout_sec", "upper_bps", "lower_bps"])
    top = work.head(top_n)
    if top.empty:
        return pd.DataFrame()

    days = day_arrays(df)
    dates = df["date"].astype(str).to_numpy()
    date_codes = df["date_code"].to_numpy(dtype="int64")
    fold_map = {fold.name: fold for fold in folds}
    feature_cache: dict[tuple[str, bytes], np.ndarray] = {}
    rows: list[dict[str, object]] = []

    for row in top.itertuples(index=False):
        fold = fold_map[str(row.fold)]
        train_mask = np.isin(dates, fold.train_dates)
        test_mask = np.isin(dates, fold.test_dates)
        values = base.feature_values_for_fold(df, str(row.feature), train_mask, feature_cache)
        mask, direction, _, _ = base.build_policy_mask(
            values,
            train_mask,
            test_mask,
            filters[str(row.filter)],
            float(row.quantile),
            str(row.policy),
        )
        controls: dict[str, tuple[np.ndarray, np.ndarray]] = {
            "base_toy_mid_barrier": (mask, direction),
            "reversed_side": (mask, (direction * -1).astype("int8")),
        }
        long_shift = base.shifted_within_day(direction > 0, date_codes, shift_events)
        short_shift = base.shifted_within_day(direction < 0, date_codes, shift_events)
        shifted_direction = np.zeros_like(direction, dtype="int8")
        shifted_direction[long_shift] = 1
        shifted_direction[short_shift] = -1
        shifted_mask = (shifted_direction != 0) & test_mask
        controls["within_day_shifted_signal"] = (shifted_mask, shifted_direction)
        if "past_event_25_bps" in df.columns:
            past_values = df["past_event_25_bps"].to_numpy(dtype="float64")
            past_mask, past_direction, _, _ = base.build_policy_mask(
                past_values,
                train_mask,
                test_mask,
                filters[str(row.filter)],
                float(row.quantile),
                "follow_extremes",
            )
            controls["past_return_gate"] = (past_mask, past_direction)

        for control_name, (control_mask, control_direction) in controls.items():
            candidate_idx = np.flatnonzero(control_mask & (control_direction != 0))
            selected_rows = int(len(candidate_idx))
            base_fields = {
                "run_tag": RUN_TAG,
                "source_run_tag": SOURCE_RUN_TAG,
                "fold": str(row.fold),
                "feature": str(row.feature),
                "policy": str(row.policy),
                "filter": str(row.filter),
                "quantile": float(row.quantile),
                "control": control_name,
            }
            rows.extend(
                evaluate_one_config(
                    df,
                    days,
                    candidate_idx,
                    control_direction,
                    selected_rows,
                    int(row.timeout_sec),
                    float(row.upper_bps),
                    float(row.lower_bps),
                    upper_bps,
                    lower_bps,
                    "observed_mid",
                    ["toy_mid"],
                    base_fields,
                    account_quote,
                )
            )
    return pd.DataFrame(rows)


def top_table(df: pd.DataFrame, rows: int, cols: list[str]) -> list[str]:
    if df.empty:
        return ["No rows."]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in df.head(rows).itertuples(index=False):
        values = []
        for col in cols:
            value = getattr(row, col)
            if isinstance(value, float):
                values.append(fmt_num(value, 4))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def write_report(
    paths: Paths,
    quality: pd.DataFrame,
    entry_specs: pd.DataFrame,
    candidates: pd.DataFrame,
    controls: pd.DataFrame,
    account_quote: float,
    timeouts_sec: list[int],
    upper_bps: list[float],
    lower_bps: list[float],
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT Barrier Sweep")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from source panel `{paths.source_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This is a triple-barrier toy replay overlay. It is not queue-position fill evidence, "
        "not live execution simulation, not trading advice, and not an alpha claim."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Panel rows loaded: `{int(quality['rows'].sum()) if not quality.empty else 0}`.")
    lines.append(f"- Entry specs tested: `{len(entry_specs)}`.")
    lines.append(f"- Timeouts: `{', '.join(str(v) + 's' for v in timeouts_sec)}`.")
    lines.append(f"- Upper barriers: `{', '.join(fmt_num(v, 1) for v in upper_bps)}` bps.")
    lines.append(f"- Lower barriers: `{', '.join(fmt_num(v, 1) for v in lower_bps)}` bps.")
    lines.append(f"- Account scale column uses `{fmt_num(account_quote, 2)}` quote notional.")
    lines.append("- Entries are flat-to-flat: after an entry, later signals are ignored until the barrier exit.")
    lines.append("")
    lines.append("## Data Read")
    lines.append("")
    if not quality.empty:
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| median quote-change rate | {fmt_num(quality['quote_change_rate'].median() * 100, 2)}% |")
        lines.append(f"| median trade-present rate | {fmt_num(quality['trade_present_rate'].median() * 100, 2)}% |")
        lines.append(f"| median spread | {fmt_num(quality['spread_p50_bps'].median(), 4)} bps |")
        lines.append(f"| p95 spread median-by-day | {fmt_num(quality['spread_p95_bps'].median(), 4)} bps |")
    lines.append("")

    if not candidates.empty:
        work = candidates.copy()
        for col in [
            "entries",
            "net_mean_bps",
            "gross_mean_bps",
            "net_median_bps",
            "score",
            "tp_rate",
            "sl_rate",
            "timeout_rate",
            "linear_1000_trades_pct",
        ]:
            work[col] = pd.to_numeric(work[col], errors="coerce")
        display_dupe = [
            "fold",
            "feature",
            "policy",
            "filter",
            "timeout_sec",
            "upper_bps",
            "lower_bps",
            "settlement",
            "cost_model",
            "entries",
            "net_mean_bps",
        ]
        top_mid = (
            work[work["cost_model"].eq("toy_mid") & work["entries"].ge(40)]
            .sort_values("score", ascending=False)
            .drop_duplicates(subset=display_dupe)
        )
        survivors = (
            work[work["research_status"].eq("survives_toy_cost_barrier_probe") & work["entries"].ge(40)]
            .sort_values("score", ascending=False)
            .drop_duplicates(subset=display_dupe)
        )
        maker = survivors[survivors["cost_model"].eq("toy_maker_light")]
        taker = survivors[survivors["cost_model"].eq("toy_taker_spread")]
        wide = survivors[survivors["cost_model"].eq("toy_wide_stress")]
        gross_failed = (
            work[work["research_status"].eq("gross_only_cost_failed") & work["entries"].ge(40)]
            .sort_values("gross_mean_bps", ascending=False)
            .drop_duplicates(subset=display_dupe)
        )

        lines.append("## Top Toy-Mid Barrier Rows")
        lines.append("")
        lines.extend(
            top_table(
                top_mid,
                12,
                [
                    "fold",
                    "feature",
                    "policy",
                    "filter",
                    "timeout_sec",
                    "upper_bps",
                    "lower_bps",
                    "settlement",
                    "entries",
                    "gross_mean_bps",
                    "tp_rate",
                    "sl_rate",
                    "score",
                ],
            )
        )
        lines.append("")
        lines.append("## Toy-Cost Survivors")
        lines.append("")
        lines.extend(
            top_table(
                survivors,
                16,
                [
                    "fold",
                    "feature",
                    "policy",
                    "filter",
                    "timeout_sec",
                    "upper_bps",
                    "lower_bps",
                    "cost_model",
                    "entries",
                    "net_mean_bps",
                    "net_median_bps",
                    "tp_rate",
                    "sl_rate",
                    "linear_1000_trades_pct",
                    "score",
                ],
            )
        )
        lines.append("")
        lines.append("## Wide-Stress Survivors")
        lines.append("")
        if wide.empty:
            lines.append("No row survived `toy_wide_stress`.")
        else:
            lines.extend(
                top_table(
                    wide,
                    8,
                    [
                        "fold",
                        "feature",
                        "policy",
                        "filter",
                        "timeout_sec",
                        "upper_bps",
                        "lower_bps",
                        "entries",
                        "net_mean_bps",
                        "score",
                    ],
                )
            )
        lines.append("")
        lines.append("## Gross-Only Cost Failures")
        lines.append("")
        lines.extend(
            top_table(
                gross_failed,
                10,
                [
                    "fold",
                    "feature",
                    "policy",
                    "filter",
                    "timeout_sec",
                    "upper_bps",
                    "lower_bps",
                    "cost_model",
                    "entries",
                    "gross_mean_bps",
                    "net_mean_bps",
                    "research_status",
                ],
            )
        )
        lines.append("")
        lines.append("## Strategy Read")
        lines.append("")
        counts = (
            survivors.groupby(["fold", "cost_model"], sort=True).size().reset_index(name="rows")
            if not survivors.empty
            else pd.DataFrame(columns=["fold", "cost_model", "rows"])
        )
        lines.append(
            f"- Barrier survivor rows: `{len(survivors)}`; by fold/cost: "
            + (
                ", ".join(f"{row.fold}/{row.cost_model}={int(row.rows)}" for row in counts.itertuples(index=False))
                if not counts.empty
                else "none"
            )
            + "."
        )
        if not maker.empty:
            row = maker.iloc[0]
            lines.append(
                "- Best maker-light barrier probe: "
                f"`{row['feature']} / {row['policy']} / {row['filter']} / U={fmt_num(row['upper_bps'], 1)} / "
                f"L={fmt_num(row['lower_bps'], 1)} / T={int(row['timeout_sec'])}s`, entries `{int(row['entries'])}`, "
                f"net `{fmt_num(row['net_mean_bps'])}` bps, median `{fmt_num(row['net_median_bps'])}` bps, "
                f"linear 1000-trade read `{fmt_num(row['linear_1000_trades_pct'], 2)}%`."
            )
        if not taker.empty:
            row = taker.iloc[0]
            lines.append(
                "- Best taker-spread barrier probe: "
                f"`{row['feature']} / {row['policy']} / {row['filter']} / U={fmt_num(row['upper_bps'], 1)} / "
                f"L={fmt_num(row['lower_bps'], 1)} / T={int(row['timeout_sec'])}s`, entries `{int(row['entries'])}`, "
                f"net `{fmt_num(row['net_mean_bps'])}` bps, median `{fmt_num(row['net_median_bps'])}` bps."
            )
        if not survivors.empty:
            feature_counts = survivors.groupby("feature", sort=True).size().sort_values(ascending=False).head(5)
            lines.append(
                "- Survivor concentration by feature: "
                + ", ".join(f"`{feature}`={int(count)}" for feature, count in feature_counts.items())
                + "."
            )
        lines.append(
            "- Read: if the best rows choose tight upper barriers and still have negative medians, the prior fixed-time edge "
            "is mostly right-tail capture. If barrier rows improve median net, upper/lower exits are adding useful path control."
        )
        lines.append("")

    if not controls.empty:
        control_work = controls.copy()
        for col in ["entries", "net_mean_bps", "score"]:
            control_work[col] = pd.to_numeric(control_work[col], errors="coerce")
        control_summary = (
            control_work.groupby("control", sort=True)
            .agg(
                rows=("control", "size"),
                median_entries=("entries", "median"),
                median_net_mean_bps=("net_mean_bps", "median"),
                p90_abs_net_mean_bps=("net_mean_bps", lambda s: float(np.nanpercentile(np.abs(s), 90))),
            )
            .reset_index()
            .sort_values("p90_abs_net_mean_bps", ascending=False)
        )
        lines.append("## Controls")
        lines.append("")
        lines.extend(top_table(control_summary, 12, list(control_summary.columns)))
        lines.append("")
        lines.append(
            "If `past_return_gate` or `within_day_shifted_signal` stays close to the base rows, the barrier result is still a "
            "state-persistence artifact warning rather than a clean strategy candidate."
        )
        lines.append("")

    lines.append("## Current Read")
    lines.append("")
    lines.append(
        "This barrier sweep is a path-shape filter, not an execution model. Any promoted row still needs a quote-transition-only "
        "and fillability pass before it can leave research status."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    lines.append(f"- `{paths.quality_csv}`")
    lines.append(f"- `{paths.entry_specs_csv}`")
    lines.append(f"- `{paths.candidate_csv}`")
    lines.append(f"- `{paths.control_csv}`")
    lines.append(f"- `{paths.summary_json}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("python scripts/ccusdt_barrier_sweep.py")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    paths: Paths,
    quality: pd.DataFrame,
    entry_specs: pd.DataFrame,
    candidates: pd.DataFrame,
    controls: pd.DataFrame,
    account_quote: float,
    timeouts_sec: list[int],
    upper_bps: list[float],
    lower_bps: list[float],
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    quality.to_csv(paths.quality_csv, index=False)
    entry_specs.to_csv(paths.entry_specs_csv, index=False)
    candidates.to_csv(paths.candidate_csv, index=False)
    controls.to_csv(paths.control_csv, index=False)
    best: dict[str, object] = {}
    if not candidates.empty:
        work = candidates.copy()
        work["score"] = pd.to_numeric(work["score"], errors="coerce")
        work = work[work["research_status"].eq("survives_toy_cost_barrier_probe")].sort_values("score", ascending=False)
        if not work.empty:
            best = work.head(1).to_dict(orient="records")[0]
    summary = {
        "run_tag": paths.run_tag,
        "source_run_tag": paths.source_run_tag,
        "strategy_run_tag": paths.strategy_run_tag,
        "guardrail": GUARDRAIL,
        "rows": int(quality["rows"].sum()) if not quality.empty else 0,
        "dates": int(quality["date"].nunique()) if not quality.empty else 0,
        "entry_specs": int(len(entry_specs)),
        "candidate_rows": int(len(candidates)),
        "control_rows": int(len(controls)),
        "timeouts_sec": timeouts_sec,
        "upper_bps": upper_bps,
        "lower_bps": lower_bps,
        "account_quote": account_quote,
        "survivor_rows": int(candidates["research_status"].eq("survives_toy_cost_barrier_probe").sum())
        if not candidates.empty
        else 0,
        "best_barrier_probe": best,
        "outputs": {
            "quality_csv": str(paths.quality_csv),
            "entry_specs_csv": str(paths.entry_specs_csv),
            "candidate_csv": str(paths.candidate_csv),
            "control_csv": str(paths.control_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, quality, entry_specs, candidates, controls, account_quote, timeouts_sec, upper_bps, lower_bps)


def main() -> None:
    global RUN_TAG, SOURCE_RUN_TAG, STRATEGY_RUN_TAG
    args = parse_args()
    RUN_TAG = args.run_tag
    SOURCE_RUN_TAG = args.source_run_tag
    STRATEGY_RUN_TAG = args.strategy_run_tag
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
        strategy_run_tag=args.strategy_run_tag,
        method_sweep_run_tag=args.method_sweep_run_tag,
    )
    timeouts_sec = parse_ints(args.timeouts_sec)
    upper_bps = parse_floats(args.upper_bps)
    lower_bps = parse_floats(args.lower_bps)
    quantiles = parse_floats(args.quantiles)
    features = parse_strings(args.features)
    filter_names = parse_strings(args.filters)
    policies = parse_strings(args.policies)
    settlement_modes = parse_strings(args.settlement_modes)
    cost_models = parse_strings(args.cost_models)
    invalid_costs = [model for model in cost_models if model not in base.COST_MODELS]
    if invalid_costs:
        raise ValueError(f"unknown cost models: {invalid_costs}; available={base.COST_MODELS}")
    invalid_settlements = [mode for mode in settlement_modes if mode not in {"observed_mid", "clipped_barrier"}]
    if invalid_settlements:
        raise ValueError(f"unknown settlement modes: {invalid_settlements}")

    base_paths = base.Paths(
        panel_root=paths.panel_root,
        source_run_tag=paths.source_run_tag,
        date_dir=paths.date_dir,
        doc_dir=paths.doc_dir,
        run_tag=base.RUN_TAG,
        method_sweep_run_tag=paths.method_sweep_run_tag,
    )
    df, usable_features = base.load_panel(base_paths)
    event_horizons = [25]
    df, _targets = base.add_replay_labels(df, event_horizons, timeouts_sec)
    folds = base.make_folds(sorted(df["date"].dropna().astype(str).unique()))
    filter_masks_all = base.build_filter_masks(df)
    missing_filters = [name for name in filter_names if name not in filter_masks_all]
    if missing_filters:
        raise ValueError(f"unknown filters: {missing_filters}; available={sorted(filter_masks_all)}")
    filters = {name: filter_masks_all[name] for name in filter_names}

    for feature in features:
        if feature not in usable_features and feature not in base.COMPOSITE_SPECS:
            raise ValueError(f"feature not available in panel or composite specs: {feature}")
    entry_specs = build_entry_specs(paths, features, filter_names, policies, quantiles, args.max_entry_specs)
    print(
        f"barrier sweep specs={len(entry_specs)} folds={len(folds)} timeouts={timeouts_sec} "
        f"upper={upper_bps} lower={lower_bps}",
        flush=True,
    )
    quality = quality_rows(df, timeouts_sec)
    candidates = run_sweep(
        df,
        folds,
        entry_specs,
        filters,
        timeouts_sec,
        upper_bps,
        lower_bps,
        settlement_modes,
        cost_models,
        args.account_quote,
    )
    print(f"barrier candidate rows={len(candidates)}", flush=True)
    controls = run_controls(
        df,
        folds,
        candidates,
        filters,
        timeouts_sec,
        upper_bps,
        lower_bps,
        args.account_quote,
        args.top_control_rows,
        args.control_shift_events,
    )
    print(f"barrier control rows={len(controls)}", flush=True)
    write_outputs(paths, quality, entry_specs, candidates, controls, args.account_quote, timeouts_sec, upper_bps, lower_bps)
    print(f"wrote {paths.candidate_csv}", flush=True)
    print(f"wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
