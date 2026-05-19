#!/usr/bin/env python
"""CCUSDT signal taxonomy and path-math diagnostics.

Research-only diagnostics for the fixed snapshot-frame CCUSDT panel. This is
not an execution model, not queue-position fill evidence, and not trading
advice. The script keeps the search surface deliberately small: classify the
current trigger families, measure cost-threshold crossing, and decompose a few
barrier candidates relative to the fixed-time exit.
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

import ccusdt_barrier_sweep as barrier
import ccusdt_strategy_research as base


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)


GUARDRAIL = "research_only_signal_path_math_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260517_ccusdt_signal_path_math_v1"
SOURCE_RUN_TAG = base.SOURCE_RUN_TAG
US_PER_SECOND = base.US_PER_SECOND
EPS = base.EPS


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def fixed_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_signal_path_math_fixed_{self.run_tag}.csv"

    @property
    def barrier_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_signal_path_math_barrier_{self.run_tag}.csv"

    @property
    def entry_refinement_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_signal_path_math_entry_refinement_{self.run_tag}.csv"

    @property
    def stop_policy_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_signal_path_math_stop_policy_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_signal_path_math_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / "v1-signal-path-math.md"


@dataclass(frozen=True)
class TriggerSpec:
    trigger_class: str
    feature: str
    policy: str
    filter_name: str
    quantile: float
    mechanism: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT signal path-math diagnostics.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--time-horizons-sec", default="10,30,60")
    parser.add_argument("--entry-bucket-sec", type=int, default=60)
    parser.add_argument("--barrier-pairs", default="8:5,12:5,12:8")
    parser.add_argument("--upper-bps", default="5,8,12")
    parser.add_argument("--lower-bps", default="5,8,12")
    parser.add_argument("--stop-levels-bps", default="5,8,12,20")
    parser.add_argument("--stop-grace-sec", default="0,5,10")
    parser.add_argument("--control-shift-events", type=int, default=500)
    parser.add_argument("--include-controls", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_ints(raw: str) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one integer")
    return sorted(set(values))


def parse_floats(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one float")
    return sorted(set(values))


def parse_barrier_pairs(raw: str) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for part in raw.split(","):
        if not part.strip():
            continue
        left, right = part.split(":", 1)
        pairs.append((float(left), float(right)))
    if not pairs:
        raise ValueError("expected at least one U:L pair")
    return pairs


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def lower_tail_mean(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def safe_rate(mask: np.ndarray) -> float:
    return float(mask.mean()) if len(mask) else np.nan


def safe_cond_rate(numerator: np.ndarray, denominator: np.ndarray) -> float:
    denom = denominator.astype(bool)
    return float(numerator[denom].mean()) if denom.any() else np.nan


def trigger_specs() -> list[TriggerSpec]:
    return [
        TriggerSpec(
            "tfi_short_flat",
            "trade_flow_imbalance",
            "short_low",
            "past25_abs_le_0p5bps",
            0.8,
            "trade_flow_continuation_cost_threshold",
        ),
        TriggerSpec(
            "tfi_long_flat",
            "trade_flow_imbalance",
            "long_high",
            "past25_abs_le_0p5bps",
            0.8,
            "trade_flow_continuation_cost_threshold",
        ),
        TriggerSpec(
            "tfi_follow_flat",
            "trade_flow_imbalance",
            "follow_extremes",
            "past25_abs_le_0p5bps",
            0.8,
            "aggregate_short_long_flat",
        ),
        TriggerSpec(
            "tfi_short_stale70",
            "trade_flow_imbalance",
            "short_low",
            "stale_mid_ge70",
            0.8,
            "state_release_short",
        ),
        TriggerSpec(
            "tfi_short_stale25",
            "trade_flow_imbalance",
            "short_low",
            "stale_mid_ge25",
            0.8,
            "state_release_short_looser_stale",
        ),
        TriggerSpec(
            "tfi_follow_stale70",
            "trade_flow_imbalance",
            "follow_extremes",
            "stale_mid_ge70",
            0.8,
            "state_release_follow",
        ),
        TriggerSpec(
            "tfi_event_active",
            "trade_flow_imbalance",
            "follow_extremes",
            "trade_present_stale_mid_ge25",
            0.8,
            "event_active_quote_catchup",
        ),
        TriggerSpec(
            "mlofi_l1_short_active",
            "mlofi_roll10_l1",
            "short_low",
            "trade_present_stale_mid_ge25",
            0.9,
            "book_pressure_secondary",
        ),
        TriggerSpec(
            "combo_trade_mlofi_long_active",
            "combo_trade_mlofi_l1",
            "long_high",
            "trade_present_stale_mid_ge25",
            0.8,
            "trade_flow_book_confirmation",
        ),
        TriggerSpec(
            "combo_trade_mlofi_short_flat",
            "combo_trade_mlofi_l1",
            "short_low",
            "past25_abs_le_0p5bps",
            0.8,
            "trade_flow_book_confirmation_flat_short",
        ),
        TriggerSpec(
            "combo_trade_mlofi_short_stale25",
            "combo_trade_mlofi_l1",
            "short_low",
            "stale_mid_ge25",
            0.8,
            "trade_flow_book_confirmation_stale_short",
        ),
        TriggerSpec(
            "combo_trade_mlofi_short_stale70",
            "combo_trade_mlofi_l1",
            "short_low",
            "stale_mid_ge70",
            0.8,
            "trade_flow_book_confirmation_deep_stale_short",
        ),
        TriggerSpec(
            "combo_book_pressure_short_active",
            "combo_book_pressure",
            "short_low",
            "trade_present_stale_mid_ge25",
            0.8,
            "book_pressure_confirmation",
        ),
    ]


def base_fields_for_spec(
    fold: base.Fold,
    spec: TriggerSpec,
    control: str,
    q_low: float,
    q_high: float,
    selected_rows: int,
    entry_bucket_sec: int,
) -> dict[str, object]:
    return {
        "run_tag": RUN_TAG,
        "source_run_tag": SOURCE_RUN_TAG,
        "fold": fold.name,
        "train_start_date": fold.train_dates[0],
        "train_end_date": fold.train_dates[-1],
        "test_start_date": fold.test_dates[0],
        "test_end_date": fold.test_dates[-1],
        "trigger_class": spec.trigger_class,
        "mechanism": spec.mechanism,
        "feature": spec.feature,
        "feature_family": base.feature_family(spec.feature),
        "policy": spec.policy,
        "filter": spec.filter_name,
        "quantile": spec.quantile,
        "q_low": q_low,
        "q_high": q_high,
        "control": control,
        "selected_rows": selected_rows,
        "entry_bucket_sec": entry_bucket_sec,
        "guardrail": GUARDRAIL,
    }


def build_entry_idx(
    df: pd.DataFrame,
    mask: np.ndarray,
    direction: np.ndarray,
    bucket_col: str,
    target_col: str,
    exit_col: str,
) -> tuple[np.ndarray, int]:
    valid = (
        mask
        & (direction != 0)
        & np.isfinite(df[target_col].to_numpy(dtype="float64"))
        & (df[exit_col].to_numpy(dtype="int64") >= 0)
    )
    candidate_idx = np.flatnonzero(valid)
    selected_rows = int(len(candidate_idx))
    if not len(candidate_idx):
        return candidate_idx, selected_rows
    buckets = df[bucket_col].to_numpy(dtype="int64")
    return base.first_per_bucket(candidate_idx, buckets), selected_rows


def control_variants(
    df: pd.DataFrame,
    spec: TriggerSpec,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    filter_mask: np.ndarray,
    base_mask: np.ndarray,
    base_direction: np.ndarray,
    shift_events: int,
    include_controls: bool,
) -> list[tuple[str, np.ndarray, np.ndarray, float, float]]:
    variants: list[tuple[str, np.ndarray, np.ndarray, float, float]] = [
        ("signal", base_mask, base_direction, np.nan, np.nan)
    ]
    if not include_controls:
        return variants

    variants.append(("reversed_side", base_mask, (base_direction * -1).astype("int8"), np.nan, np.nan))

    date_codes = df["date_code"].to_numpy(dtype="int64")
    shifted_direction = np.zeros_like(base_direction, dtype="int8")
    shifted_long = base.shifted_within_day(base_mask & (base_direction > 0), date_codes, shift_events)
    shifted_short = base.shifted_within_day(base_mask & (base_direction < 0), date_codes, shift_events)
    shifted_direction[shifted_long] = 1
    shifted_direction[shifted_short] = -1
    shifted_mask = (shifted_direction != 0) & test_mask
    variants.append((f"shifted_{shift_events}_events", shifted_mask, shifted_direction, np.nan, np.nan))

    if "past_event_25_bps" in df.columns:
        past_values = df["past_event_25_bps"].to_numpy(dtype="float64")
        past_mask, past_direction, q_low, q_high = base.build_policy_mask(
            past_values,
            train_mask,
            test_mask,
            filter_mask,
            spec.quantile,
            spec.policy,
        )
        variants.append(("past_return_gate", past_mask, past_direction, q_low, q_high))
    return variants


def fixed_math_row(
    df: pd.DataFrame,
    outcomes: barrier.PathOutcomes,
    base_fields: dict[str, object],
    timeout_sec: int,
) -> dict[str, object]:
    if len(outcomes.entry_idx) == 0:
        return {
            **base_fields,
            "timeout_sec": timeout_sec,
            "entries": 0,
            "gross_mean_bps": np.nan,
            "gross_median_bps": np.nan,
            "net_mean_bps": np.nan,
            "net_median_bps": np.nan,
            "cost_cross_rate": np.nan,
            "winner_excess_mean_bps": np.nan,
            "loser_shortfall_mean_bps": np.nan,
            "edge_decomp_bps": np.nan,
            "top10_gross_share": np.nan,
            "mfe_mean_bps": np.nan,
            "mae_mean_bps": np.nan,
        }

    spread = df["spread_bps"].to_numpy(dtype="float64")
    exit_spread = spread[outcomes.final_exit_idx.astype("int64")]
    costs = base.cost_array("toy_maker_light", outcomes.entry_spread_bps, exit_spread)
    gross = outcomes.final_return_bps
    net = gross - costs
    crosses = gross > costs
    winner_excess = gross[crosses] - costs[crosses]
    loser_shortfall = costs[~crosses] - gross[~crosses]
    gross_sum = float(np.nansum(gross))
    q90 = finite_quantile(gross, 0.90)
    top10_share = float(np.nansum(gross[gross >= q90]) / gross_sum) if abs(gross_sum) > EPS else np.nan
    edge_decomp = safe_rate(crosses) * finite_mean(winner_excess) - (1.0 - safe_rate(crosses)) * finite_mean(loser_shortfall)
    return {
        **base_fields,
        "timeout_sec": timeout_sec,
        "entries": int(len(gross)),
        "gross_mean_bps": finite_mean(gross),
        "gross_median_bps": finite_quantile(gross, 0.50),
        "gross_p10_bps": finite_quantile(gross, 0.10),
        "gross_p90_bps": q90,
        "net_mean_bps": finite_mean(net),
        "net_median_bps": finite_quantile(net, 0.50),
        "net_p10_bps": finite_quantile(net, 0.10),
        "net_p90_bps": finite_quantile(net, 0.90),
        "net_cvar10_bps": lower_tail_mean(net, 0.10),
        "net_win_rate": safe_rate(net > 0.0),
        "avg_cost_bps": finite_mean(costs),
        "cost_cross_rate": safe_rate(crosses),
        "winner_excess_mean_bps": finite_mean(winner_excess),
        "loser_shortfall_mean_bps": finite_mean(loser_shortfall),
        "edge_decomp_bps": edge_decomp,
        "top10_gross_share": top10_share,
        "mfe_mean_bps": finite_mean(outcomes.mfe_bps),
        "mfe_median_bps": finite_quantile(outcomes.mfe_bps, 0.50),
        "mae_mean_bps": finite_mean(outcomes.mae_bps),
        "mae_median_bps": finite_quantile(outcomes.mae_bps, 0.50),
        "mfe_ge_8_rate": safe_rate(outcomes.mfe_bps >= 8.0),
        "mfe_ge_12_rate": safe_rate(outcomes.mfe_bps >= 12.0),
        "mae_le_neg5_rate": safe_rate(outcomes.mae_bps <= -5.0),
        "mae_le_neg8_rate": safe_rate(outcomes.mae_bps <= -8.0),
        "avg_hold_sec": finite_mean(outcomes.final_hold_sec),
    }


def barrier_math_row(
    df: pd.DataFrame,
    outcomes: barrier.PathOutcomes,
    base_fields: dict[str, object],
    timeout_sec: int,
    upper: float,
    lower: float,
    upper_i: int,
    lower_i: int,
) -> dict[str, object]:
    if len(outcomes.entry_idx) == 0:
        return {
            **base_fields,
            "timeout_sec": timeout_sec,
            "upper_bps": upper,
            "lower_bps": lower,
            "entries": 0,
            "delta_net_mean_bps": np.nan,
        }

    spread = df["spread_bps"].to_numpy(dtype="float64")
    up_idx = outcomes.up_exit_idx[:, upper_i]
    down_idx = outcomes.down_exit_idx[:, lower_i]
    up_hit = up_idx >= 0
    down_hit = down_idx >= 0
    up_first = up_hit & (~down_hit | (up_idx < down_idx))
    down_first = down_hit & (~up_hit | (down_idx < up_idx))
    timeout = ~(up_first | down_first)
    exit_idx = np.where(up_first, up_idx, np.where(down_first, down_idx, outcomes.final_exit_idx)).astype("int64")

    fixed_gross = outcomes.final_return_bps
    barrier_gross = np.where(up_first, upper, np.where(down_first, -lower, fixed_gross))
    fixed_cost = base.cost_array("toy_maker_light", outcomes.entry_spread_bps, spread[outcomes.final_exit_idx])
    barrier_cost = base.cost_array("toy_maker_light", outcomes.entry_spread_bps, spread[exit_idx])
    fixed_net = fixed_gross - fixed_cost
    barrier_net = barrier_gross - barrier_cost
    fixed_cross = fixed_gross > fixed_cost

    tp_save_giveback = finite_mean(np.maximum(upper - fixed_gross, 0.0) * up_first.astype("float64"))
    tp_clip_right_tail = finite_mean(np.maximum(fixed_gross - upper, 0.0) * up_first.astype("float64"))
    sl_save_left_tail = finite_mean(np.maximum(-lower - fixed_gross, 0.0) * down_first.astype("float64"))
    sl_kill_recovery = finite_mean(np.maximum(fixed_gross + lower, 0.0) * down_first.astype("float64"))
    delta_gross = barrier_gross - fixed_gross
    delta_cost = barrier_cost - fixed_cost
    clipped_terminal = np.minimum(upper, np.maximum(-lower, fixed_gross))
    terminal_delta = clipped_terminal - fixed_gross
    race_effect = delta_gross - terminal_delta

    return {
        **base_fields,
        "timeout_sec": timeout_sec,
        "upper_bps": upper,
        "lower_bps": lower,
        "entries": int(len(fixed_gross)),
        "tp_rate": safe_rate(up_first),
        "sl_rate": safe_rate(down_first),
        "timeout_rate": safe_rate(timeout),
        "fixed_net_mean_bps": finite_mean(fixed_net),
        "barrier_net_mean_bps": finite_mean(barrier_net),
        "delta_net_mean_bps": finite_mean(barrier_net - fixed_net),
        "fixed_net_median_bps": finite_quantile(fixed_net, 0.50),
        "barrier_net_median_bps": finite_quantile(barrier_net, 0.50),
        "fixed_win_rate": safe_rate(fixed_net > 0.0),
        "barrier_win_rate": safe_rate(barrier_net > 0.0),
        "delta_gross_mean_bps": finite_mean(delta_gross),
        "delta_cost_mean_bps": finite_mean(delta_cost),
        "tp_save_giveback_bps": tp_save_giveback,
        "tp_clip_right_tail_bps": tp_clip_right_tail,
        "sl_save_left_tail_bps": sl_save_left_tail,
        "sl_kill_recovery_bps": sl_kill_recovery,
        "terminal_delta_mean_bps": finite_mean(terminal_delta),
        "race_effect_mean_bps": finite_mean(race_effect),
        "sl_given_fixed_cost_winner_rate": safe_cond_rate(down_first, fixed_cross),
        "sl_given_fixed_gt_upper_rate": safe_cond_rate(down_first, fixed_gross > upper),
        "tp_given_fixed_cost_loser_rate": safe_cond_rate(up_first, ~fixed_cross),
        "tp_rescue_uncond_rate": safe_rate(up_first & ~fixed_cross),
        "sl_kill_cost_winner_uncond_rate": safe_rate(down_first & fixed_cross),
        "timeout_cost_cross_rate": safe_cond_rate(fixed_cross, timeout),
        "avg_barrier_cost_bps": finite_mean(barrier_cost),
    }


def stop_policy_name(stop_bps: float | None, grace_sec: int) -> str:
    if stop_bps is None:
        return "fixed_no_stop"
    if stop_bps >= 20:
        return "catastrophic_stop" if grace_sec == 0 else "delayed_catastrophic_stop"
    return "stop_only" if grace_sec == 0 else "delayed_stop"


def stop_policy_math_row(
    df: pd.DataFrame,
    days: dict[int, dict[str, np.ndarray]],
    entry_idx: np.ndarray,
    direction: np.ndarray,
    base_fields: dict[str, object],
    timeout_sec: int,
    stop_bps: float | None,
    grace_sec: int,
) -> dict[str, object]:
    date_codes_all = df["date_code"].to_numpy(dtype="int64")
    row_pos_all = df["row_pos_in_day"].to_numpy(dtype="int64")
    spread_all = df["spread_bps"].to_numpy(dtype="float64")
    timeout_us = timeout_sec * US_PER_SECOND

    fixed_gross_values: list[float] = []
    stop_gross_values: list[float] = []
    fixed_exit_spreads: list[float] = []
    stop_exit_spreads: list[float] = []
    entry_spreads: list[float] = []
    date_codes: list[int] = []
    stop_hits: list[bool] = []
    hold_seconds: list[float] = []

    for entry in entry_idx:
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

        final_local = int(path_locals[-1])
        final_exit_idx = int(idx[final_local])
        final_gross = float(path_rets[-1])
        exit_local = final_local
        stop_gross = final_gross
        stop_hit = False
        hold_path = (times[path_locals] - times[local]) / US_PER_SECOND
        if stop_bps is not None:
            stop_candidates = np.flatnonzero((hold_path >= float(grace_sec)) & (path_rets <= -float(stop_bps)))
            if len(stop_candidates):
                hit_pos = int(stop_candidates[0])
                exit_local = int(path_locals[hit_pos])
                stop_gross = float(path_rets[hit_pos])
                stop_hit = True

        stop_exit_idx = int(idx[exit_local])
        fixed_gross_values.append(final_gross)
        stop_gross_values.append(stop_gross)
        fixed_exit_spreads.append(float(spread_all[final_exit_idx]) if np.isfinite(spread_all[final_exit_idx]) else np.nan)
        stop_exit_spreads.append(float(spread_all[stop_exit_idx]) if np.isfinite(spread_all[stop_exit_idx]) else np.nan)
        entry_spreads.append(float(spread_all[entry]) if np.isfinite(spread_all[entry]) else np.nan)
        date_codes.append(code)
        stop_hits.append(stop_hit)
        hold_seconds.append(float((times[exit_local] - times[local]) / US_PER_SECOND))

    policy = stop_policy_name(stop_bps, grace_sec)
    if not fixed_gross_values:
        return {
            **base_fields,
            "timeout_sec": timeout_sec,
            "stop_policy": policy,
            "stop_bps": np.nan if stop_bps is None else stop_bps,
            "grace_sec": grace_sec,
            "entries": 0,
            "stop_net_mean_bps": np.nan,
            "delta_net_mean_bps": np.nan,
        }

    fixed_gross = np.asarray(fixed_gross_values, dtype="float64")
    stop_gross = np.asarray(stop_gross_values, dtype="float64")
    entry_spread = np.asarray(entry_spreads, dtype="float64")
    fixed_exit_spread = np.asarray(fixed_exit_spreads, dtype="float64")
    stop_exit_spread = np.asarray(stop_exit_spreads, dtype="float64")
    fixed_cost = base.cost_array("toy_maker_light", entry_spread, fixed_exit_spread)
    stop_cost = base.cost_array("toy_maker_light", entry_spread, stop_exit_spread)
    fixed_net = fixed_gross - fixed_cost
    stop_net = stop_gross - stop_cost
    stop_hit_mask = np.asarray(stop_hits, dtype=bool)
    fixed_cross = fixed_gross > fixed_cost
    date_code_arr = np.asarray(date_codes, dtype="int64")
    positive_day_rate, daily_mean, daily_t, max_share = base.daily_stats(stop_net, date_code_arr)
    left_tail_saved = np.maximum(stop_gross - fixed_gross, 0.0) * stop_hit_mask.astype("float64")
    recovery_killed = np.maximum(fixed_gross - stop_gross, 0.0) * stop_hit_mask.astype("float64")
    fixed_cvar10 = lower_tail_mean(fixed_net, 0.10)
    stop_cvar10 = lower_tail_mean(stop_net, 0.10)
    fixed_net_mean = finite_mean(fixed_net)
    stop_net_mean = finite_mean(stop_net)
    delta_net_mean = finite_mean(stop_net - fixed_net)
    delta_cvar10 = stop_cvar10 - fixed_cvar10
    stop_kill_winner_rate = safe_cond_rate(stop_hit_mask, fixed_cross)
    if stop_bps is None:
        status = "fixed_baseline_no_stop"
    elif len(stop_net) < 30:
        status = "too_few_entries"
    elif delta_cvar10 > 0.0 and stop_net_mean <= 0.0:
        status = "left_tail_repair_negative_mean"
    elif delta_cvar10 > 0.0 and delta_net_mean >= -0.5 and (not np.isfinite(stop_kill_winner_rate) or stop_kill_winner_rate <= 0.10):
        status = "left_tail_improved_low_mean_cost"
    elif delta_cvar10 > 0.0 and delta_net_mean < 0.0:
        status = "left_tail_tradeoff"
    elif delta_net_mean > 0.0:
        status = "mean_improved"
    else:
        status = "not_helpful"
    stop_score = delta_cvar10 + min(delta_net_mean, 0.0)
    if np.isfinite(stop_kill_winner_rate):
        stop_score -= max(0.0, stop_kill_winner_rate - 0.10) * 10.0

    return {
        **base_fields,
        "timeout_sec": timeout_sec,
        "stop_policy": policy,
        "stop_bps": np.nan if stop_bps is None else float(stop_bps),
        "grace_sec": int(grace_sec),
        "entries": int(len(stop_net)),
        "stop_hit_rate": safe_rate(stop_hit_mask),
        "timeout_rate": safe_rate(~stop_hit_mask),
        "fixed_net_mean_bps": fixed_net_mean,
        "stop_net_mean_bps": stop_net_mean,
        "delta_net_mean_bps": delta_net_mean,
        "fixed_net_median_bps": finite_quantile(fixed_net, 0.50),
        "stop_net_median_bps": finite_quantile(stop_net, 0.50),
        "fixed_net_p10_bps": finite_quantile(fixed_net, 0.10),
        "stop_net_p10_bps": finite_quantile(stop_net, 0.10),
        "fixed_cvar10_bps": fixed_cvar10,
        "stop_cvar10_bps": stop_cvar10,
        "delta_cvar10_bps": delta_cvar10,
        "fixed_win_rate": safe_rate(fixed_net > 0.0),
        "stop_win_rate": safe_rate(stop_net > 0.0),
        "left_tail_saved_bps": finite_mean(left_tail_saved),
        "recovery_killed_bps": finite_mean(recovery_killed),
        "stop_given_fixed_cost_winner_rate": stop_kill_winner_rate,
        "stop_kill_cost_winner_uncond_rate": safe_rate(stop_hit_mask & fixed_cross),
        "positive_day_rate": positive_day_rate,
        "daily_net_mean_bps": daily_mean,
        "daily_net_t_stat": daily_t,
        "max_single_day_abs_share": max_share,
        "avg_cost_bps": finite_mean(stop_cost),
        "avg_hold_sec": finite_mean(hold_seconds),
        "stop_score": stop_score,
        "research_status": status,
        "guardrail": GUARDRAIL,
    }


def run_diagnostics(
    df: pd.DataFrame,
    folds: list[base.Fold],
    filters: dict[str, np.ndarray],
    specs: list[TriggerSpec],
    timeouts_sec: list[int],
    entry_bucket_sec: int,
    upper_bps: list[float],
    lower_bps: list[float],
    barrier_pairs: list[tuple[float, float]],
    stop_levels_bps: list[float],
    stop_grace_sec: list[int],
    shift_events: int,
    include_controls: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    days = barrier.day_arrays(df)
    dates = df["date"].astype(str).to_numpy()
    feature_cache: dict[tuple[str, bytes], np.ndarray] = {}
    fixed_rows: list[dict[str, object]] = []
    barrier_rows: list[dict[str, object]] = []
    stop_rows: list[dict[str, object]] = []
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_col = f"{target_col}_exit_idx"
    bucket_col = f"{target_col}_bucket"

    for fold in folds:
        train_mask = np.isin(dates, fold.train_dates)
        test_mask = np.isin(dates, fold.test_dates)
        print(f"path math fold={fold.name} train_days={len(fold.train_dates)} test_days={len(fold.test_dates)}", flush=True)
        for spec in specs:
            values = base.feature_values_for_fold(df, spec.feature, train_mask, feature_cache)
            filter_mask = filters[spec.filter_name]
            base_mask, base_direction, q_low, q_high = base.build_policy_mask(
                values,
                train_mask,
                test_mask,
                filter_mask,
                spec.quantile,
                spec.policy,
            )
            variants = control_variants(
                df,
                spec,
                train_mask,
                test_mask,
                filter_mask,
                base_mask,
                base_direction,
                shift_events,
                include_controls,
            )
            for control, mask, direction, control_q_low, control_q_high in variants:
                entry_idx, selected_rows = build_entry_idx(df, mask, direction, bucket_col, target_col, exit_col)
                if control == "signal":
                    out_q_low, out_q_high = q_low, q_high
                else:
                    out_q_low = q_low if not np.isfinite(control_q_low) else control_q_low
                    out_q_high = q_high if not np.isfinite(control_q_high) else control_q_high
                fields = base_fields_for_spec(fold, spec, control, out_q_low, out_q_high, selected_rows, entry_bucket_sec)
                print(
                    f"  {spec.trigger_class}/{control} candidates={selected_rows} entries={len(entry_idx)}",
                    flush=True,
                )
                if control == "signal":
                    stop_rows.append(
                        stop_policy_math_row(df, days, entry_idx, direction, fields, entry_bucket_sec, None, 0)
                    )
                    for stop_level in stop_levels_bps:
                        for grace_sec in stop_grace_sec:
                            stop_rows.append(
                                stop_policy_math_row(
                                    df,
                                    days,
                                    entry_idx,
                                    direction,
                                    fields,
                                    entry_bucket_sec,
                                    stop_level,
                                    grace_sec,
                                )
                            )
                for timeout_sec in timeouts_sec:
                    outcomes = barrier.build_path_outcomes(df, days, entry_idx, direction, timeout_sec, upper_bps, lower_bps)
                    fixed_rows.append(fixed_math_row(df, outcomes, fields, timeout_sec))
                    for upper, lower in barrier_pairs:
                        upper_i = upper_bps.index(upper)
                        lower_i = lower_bps.index(lower)
                        barrier_rows.append(barrier_math_row(df, outcomes, fields, timeout_sec, upper, lower, upper_i, lower_i))
    return pd.DataFrame(fixed_rows), pd.DataFrame(barrier_rows), pd.DataFrame(stop_rows)


def build_entry_refinement_table(fixed: pd.DataFrame, entry_bucket_sec: int) -> pd.DataFrame:
    if fixed.empty:
        return pd.DataFrame()
    work = fixed[fixed["timeout_sec"] == entry_bucket_sec].copy()
    if work.empty:
        return pd.DataFrame()
    keys = ["fold", "trigger_class", "feature", "policy", "filter", "quantile"]
    signal = work[work["control"] == "signal"].copy()
    controls = work[work["control"] != "signal"].copy()
    if signal.empty:
        return pd.DataFrame()
    for col in [
        "entries",
        "selected_rows",
        "net_mean_bps",
        "net_median_bps",
        "net_p10_bps",
        "net_cvar10_bps",
        "cost_cross_rate",
        "winner_excess_mean_bps",
        "loser_shortfall_mean_bps",
        "edge_decomp_bps",
        "top10_gross_share",
        "mfe_mean_bps",
        "mae_mean_bps",
    ]:
        if col in signal.columns:
            signal[col] = pd.to_numeric(signal[col], errors="coerce")

    if not controls.empty:
        controls["net_mean_bps"] = pd.to_numeric(controls["net_mean_bps"], errors="coerce")
        pivot = (
            controls.pivot_table(index=keys, columns="control", values="net_mean_bps", aggfunc="first")
            .reset_index()
            .rename_axis(None, axis=1)
        )
        signal = signal.merge(pivot, on=keys, how="left")
    for col in ["reversed_side", "shifted_500_events", "past_return_gate"]:
        if col not in signal.columns:
            signal[col] = np.nan
        signal[col] = pd.to_numeric(signal[col], errors="coerce")

    control_cols = ["reversed_side", "shifted_500_events", "past_return_gate"]
    control_values = signal[control_cols].to_numpy(dtype="float64")
    with np.errstate(all="ignore"):
        signal["control_max_net_mean_bps"] = np.nanmax(control_values, axis=1)
    signal["control_margin_bps"] = signal["net_mean_bps"] - signal["control_max_net_mean_bps"]
    signal["A_cost_cross_rate"] = signal["cost_cross_rate"]
    signal["B_winner_excess_bps"] = signal["winner_excess_mean_bps"]
    signal["D_loser_shortfall_bps"] = signal["loser_shortfall_mean_bps"]
    signal["E_edge_bps"] = signal["edge_decomp_bps"]
    tail_penalty = np.maximum(np.abs(signal["top10_gross_share"].fillna(0.0)) - 0.85, 0.0)
    sample_scale = np.sqrt(np.minimum(signal["entries"].fillna(0.0), 2000.0) / 500.0)
    signal["entry_score"] = signal["E_edge_bps"] * sample_scale + 0.25 * signal["control_margin_bps"].fillna(0.0) - 2.0 * tail_penalty

    statuses: list[str] = []
    for row in signal.itertuples(index=False):
        entries = int(getattr(row, "entries", 0) or 0)
        net_mean = float(getattr(row, "net_mean_bps", np.nan))
        net_median = float(getattr(row, "net_median_bps", np.nan))
        control_margin = float(getattr(row, "control_margin_bps", np.nan))
        top10 = float(getattr(row, "top10_gross_share", np.nan))
        if entries < 30:
            status = "too_few_entries"
        elif not np.isfinite(net_mean) or net_mean <= 0.0:
            status = "negative_or_flat"
        elif np.isfinite(control_margin) and control_margin <= 0.0:
            status = "control_not_separated"
        elif np.isfinite(net_median) and net_median > 0.0 and np.isfinite(top10) and abs(top10) <= 0.85:
            status = "mean_median_entry_candidate"
        elif np.isfinite(net_median) and net_median > 0.0:
            status = "right_tail_with_positive_median"
        else:
            status = "right_tail_entry_candidate"
        statuses.append(status)
    signal["research_status"] = statuses

    ordered = [
        "run_tag",
        "source_run_tag",
        "fold",
        "train_start_date",
        "train_end_date",
        "test_start_date",
        "test_end_date",
        "trigger_class",
        "mechanism",
        "feature",
        "policy",
        "filter",
        "quantile",
        "q_low",
        "q_high",
        "selected_rows",
        "entries",
        "net_mean_bps",
        "net_median_bps",
        "net_p10_bps",
        "net_cvar10_bps",
        "A_cost_cross_rate",
        "B_winner_excess_bps",
        "D_loser_shortfall_bps",
        "E_edge_bps",
        "top10_gross_share",
        "mfe_mean_bps",
        "mae_mean_bps",
        "reversed_side",
        "shifted_500_events",
        "past_return_gate",
        "control_max_net_mean_bps",
        "control_margin_bps",
        "entry_score",
        "research_status",
        "guardrail",
    ]
    present = [col for col in ordered if col in signal.columns]
    return signal[present].sort_values(["entry_score", "entries"], ascending=False)


def top_table(df: pd.DataFrame, rows: int, cols: list[str]) -> list[str]:
    if df.empty:
        return ["No rows."]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in df.head(rows).itertuples(index=False):
        values: list[str] = []
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
    fixed: pd.DataFrame,
    barrier_df: pd.DataFrame,
    entry_refinement: pd.DataFrame,
    stop_policy: pd.DataFrame,
    timeouts_sec: list[int],
    barrier_pairs: list[tuple[float, float]],
    stop_levels_bps: list[float],
    stop_grace_sec: list[int],
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT Signal Path Math")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from source panel `{paths.source_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This is a cost-threshold and barrier path-shape diagnostic over a snapshot-frame factor panel. "
        "It is not queue-position fill evidence, not a live execution simulation, not trading advice, and not an alpha claim."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Fixed diagnostic rows: `{len(fixed)}`.")
    lines.append(f"- Barrier diagnostic rows: `{len(barrier_df)}`.")
    lines.append(f"- Entry refinement rows: `{len(entry_refinement)}`.")
    lines.append(f"- Stop-policy rows: `{len(stop_policy)}`.")
    lines.append(f"- Timeouts: `{', '.join(str(v) + 's' for v in timeouts_sec)}`.")
    lines.append(f"- Barrier pairs: `{', '.join(f'{u:g}/{l:g}' for u, l in barrier_pairs)}`.")
    lines.append(f"- Stop levels: `{', '.join(f'{v:g}' for v in stop_levels_bps)}` bps; grace windows `{', '.join(str(v) + 's' for v in stop_grace_sec)}`.")
    lines.append("- Entry stream uses first signal per 60s bucket; barrier rows compare path exits on that same entry set.")
    lines.append("")

    signal = fixed[(fixed["control"] == "signal") & (fixed["timeout_sec"] == 60)].copy()
    if not signal.empty:
        for col in [
            "entries",
            "net_mean_bps",
            "net_median_bps",
            "cost_cross_rate",
            "winner_excess_mean_bps",
            "loser_shortfall_mean_bps",
            "top10_gross_share",
        ]:
            signal[col] = pd.to_numeric(signal[col], errors="coerce")
        signal = signal.sort_values(["net_mean_bps", "entries"], ascending=False)
        lines.append("## Cost-Threshold Read")
        lines.append("")
        lines.extend(
            top_table(
                signal,
                14,
                [
                    "fold",
                    "trigger_class",
                    "entries",
                    "gross_mean_bps",
                    "gross_median_bps",
                    "net_mean_bps",
                    "net_median_bps",
                    "cost_cross_rate",
                    "winner_excess_mean_bps",
                    "loser_shortfall_mean_bps",
                    "top10_gross_share",
                ],
            )
        )
        lines.append("")

    if not entry_refinement.empty:
        entry_top = entry_refinement.copy()
        for col in ["entry_score", "entries", "control_margin_bps", "E_edge_bps"]:
            entry_top[col] = pd.to_numeric(entry_top[col], errors="coerce")
        entry_top = entry_top.sort_values(["entry_score", "entries"], ascending=False)
        lines.append("## Entry Refinement")
        lines.append("")
        lines.extend(
            top_table(
                entry_top,
                14,
                [
                    "fold",
                    "trigger_class",
                    "entries",
                    "net_mean_bps",
                    "net_median_bps",
                    "A_cost_cross_rate",
                    "B_winner_excess_bps",
                    "D_loser_shortfall_bps",
                    "E_edge_bps",
                    "control_margin_bps",
                    "top10_gross_share",
                    "entry_score",
                    "research_status",
                ],
            )
        )
        lines.append("")

    signal_barrier = barrier_df[(barrier_df["control"] == "signal") & (barrier_df["timeout_sec"] == 60)].copy()
    if not signal_barrier.empty:
        for col in ["delta_net_mean_bps", "barrier_net_median_bps", "entries", "sl_given_fixed_cost_winner_rate"]:
            signal_barrier[col] = pd.to_numeric(signal_barrier[col], errors="coerce")
        signal_barrier = signal_barrier.sort_values(["delta_net_mean_bps", "entries"], ascending=False)
        lines.append("## Barrier Increment")
        lines.append("")
        lines.extend(
            top_table(
                signal_barrier,
                14,
                [
                    "fold",
                    "trigger_class",
                    "upper_bps",
                    "lower_bps",
                    "entries",
                    "tp_rate",
                    "sl_rate",
                    "timeout_rate",
                    "fixed_net_mean_bps",
                    "barrier_net_mean_bps",
                    "delta_net_mean_bps",
                    "fixed_net_median_bps",
                    "barrier_net_median_bps",
                    "sl_given_fixed_cost_winner_rate",
                ],
            )
        )
        lines.append("")

        lines.append("## Decomposition")
        lines.append("")
        lines.extend(
            top_table(
                signal_barrier,
                10,
                [
                    "fold",
                    "trigger_class",
                    "upper_bps",
                    "lower_bps",
                    "tp_save_giveback_bps",
                    "tp_clip_right_tail_bps",
                    "sl_save_left_tail_bps",
                    "sl_kill_recovery_bps",
                    "race_effect_mean_bps",
                    "delta_cost_mean_bps",
                ],
            )
        )
        lines.append("")

    if not stop_policy.empty:
        stop_top = stop_policy[stop_policy["stop_policy"] != "fixed_no_stop"].copy()
        if not stop_top.empty:
            for col in [
                "stop_score",
                "delta_cvar10_bps",
                "delta_net_mean_bps",
                "stop_net_mean_bps",
                "entries",
                "stop_given_fixed_cost_winner_rate",
            ]:
                stop_top[col] = pd.to_numeric(stop_top[col], errors="coerce")
            preferred = stop_top[stop_top["stop_net_mean_bps"] > 0.0].copy()
            if not preferred.empty:
                stop_top = preferred
            stop_top = stop_top.sort_values(["stop_score", "entries"], ascending=False)
            lines.append("## Stop-Only And Delayed Stop")
            lines.append("")
            lines.extend(
                top_table(
                    stop_top,
                    14,
                    [
                        "fold",
                        "trigger_class",
                        "stop_policy",
                        "stop_bps",
                        "grace_sec",
                        "entries",
                        "stop_hit_rate",
                        "fixed_net_mean_bps",
                        "stop_net_mean_bps",
                        "delta_net_mean_bps",
                        "fixed_cvar10_bps",
                        "stop_cvar10_bps",
                        "delta_cvar10_bps",
                        "stop_given_fixed_cost_winner_rate",
                        "research_status",
                    ],
                )
            )
            lines.append("")

    controls = fixed[fixed["control"] != "signal"].copy()
    if not controls.empty:
        controls["net_mean_bps"] = pd.to_numeric(controls["net_mean_bps"], errors="coerce")
        controls["entries"] = pd.to_numeric(controls["entries"], errors="coerce")
        summary = (
            controls.groupby("control", sort=True)
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
        lines.extend(top_table(summary, 12, list(summary.columns)))
        lines.append("")

    lines.append("## Mathematical Read")
    lines.append("")
    lines.append(
        "The primary question is whether each trigger class crosses the maker-light cost threshold, not whether gross "
        "return is merely positive. For each class, the fixed rows estimate `A = Pr(X_T > c)`, winner excess, loser "
        "shortfall, and top-tail concentration."
    )
    lines.append("")
    lines.append(
        "Barrier rows should be read as incremental path-shape evidence. A useful barrier needs TP giveback saving plus "
        "SL left-tail saving to exceed TP right-tail clipping, SL recovery killing, and any cost increase. The key warning "
        "column is `sl_given_fixed_cost_winner_rate`: if it is high, the stop loss kills the samples that already crossed cost."
    )
    lines.append("")
    lines.append(
        "The entry-refinement table keeps the same `E = A*B - (1-A)*D` objective and adds simple control separation. "
        "The stop-policy table has no take-profit leg; it asks whether immediate, delayed, or catastrophic stops improve "
        "left-tail/CVaR without paying too much mean-return cost."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    lines.append(f"- `{paths.fixed_csv}`")
    lines.append(f"- `{paths.barrier_csv}`")
    lines.append(f"- `{paths.entry_refinement_csv}`")
    lines.append(f"- `{paths.stop_policy_csv}`")
    lines.append(f"- `{paths.summary_json}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("python scripts/ccusdt_signal_path_math.py")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    paths: Paths,
    fixed: pd.DataFrame,
    barrier_df: pd.DataFrame,
    entry_refinement: pd.DataFrame,
    stop_policy: pd.DataFrame,
    timeouts_sec: list[int],
    barrier_pairs: list[tuple[float, float]],
    stop_levels_bps: list[float],
    stop_grace_sec: list[int],
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    fixed.to_csv(paths.fixed_csv, index=False)
    barrier_df.to_csv(paths.barrier_csv, index=False)
    entry_refinement.to_csv(paths.entry_refinement_csv, index=False)
    stop_policy.to_csv(paths.stop_policy_csv, index=False)
    best_fixed: dict[str, object] = {}
    best_barrier: dict[str, object] = {}
    best_entry: dict[str, object] = {}
    best_stop: dict[str, object] = {}
    if not fixed.empty:
        work = fixed[(fixed["control"] == "signal") & (fixed["timeout_sec"] == 60)].copy()
        work["net_mean_bps"] = pd.to_numeric(work["net_mean_bps"], errors="coerce")
        work = work.sort_values("net_mean_bps", ascending=False)
        if not work.empty:
            best_fixed = work.head(1).to_dict(orient="records")[0]
    if not barrier_df.empty:
        work_b = barrier_df[(barrier_df["control"] == "signal") & (barrier_df["timeout_sec"] == 60)].copy()
        work_b["delta_net_mean_bps"] = pd.to_numeric(work_b["delta_net_mean_bps"], errors="coerce")
        work_b = work_b.sort_values("delta_net_mean_bps", ascending=False)
        if not work_b.empty:
            best_barrier = work_b.head(1).to_dict(orient="records")[0]
    if not entry_refinement.empty:
        work_e = entry_refinement.copy()
        work_e["entry_score"] = pd.to_numeric(work_e["entry_score"], errors="coerce")
        work_e = work_e.sort_values("entry_score", ascending=False)
        if not work_e.empty:
            best_entry = work_e.head(1).to_dict(orient="records")[0]
    if not stop_policy.empty:
        work_s = stop_policy[stop_policy["stop_policy"] != "fixed_no_stop"].copy()
        work_s["stop_score"] = pd.to_numeric(work_s["stop_score"], errors="coerce")
        work_s["stop_net_mean_bps"] = pd.to_numeric(work_s["stop_net_mean_bps"], errors="coerce")
        preferred_s = work_s[work_s["stop_net_mean_bps"] > 0.0].copy()
        if not preferred_s.empty:
            work_s = preferred_s
        work_s = work_s.sort_values("stop_score", ascending=False)
        if not work_s.empty:
            best_stop = work_s.head(1).to_dict(orient="records")[0]
    summary = {
        "run_tag": paths.run_tag,
        "source_run_tag": paths.source_run_tag,
        "guardrail": GUARDRAIL,
        "fixed_rows": int(len(fixed)),
        "barrier_rows": int(len(barrier_df)),
        "entry_refinement_rows": int(len(entry_refinement)),
        "stop_policy_rows": int(len(stop_policy)),
        "timeouts_sec": timeouts_sec,
        "barrier_pairs": [{"upper_bps": upper, "lower_bps": lower} for upper, lower in barrier_pairs],
        "stop_levels_bps": stop_levels_bps,
        "stop_grace_sec": stop_grace_sec,
        "best_fixed_60s_signal": best_fixed,
        "best_barrier_60s_delta_signal": best_barrier,
        "best_entry_refinement": best_entry,
        "best_stop_policy": best_stop,
        "outputs": {
            "fixed_csv": str(paths.fixed_csv),
            "barrier_csv": str(paths.barrier_csv),
            "entry_refinement_csv": str(paths.entry_refinement_csv),
            "stop_policy_csv": str(paths.stop_policy_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(
        paths,
        fixed,
        barrier_df,
        entry_refinement,
        stop_policy,
        timeouts_sec,
        barrier_pairs,
        stop_levels_bps,
        stop_grace_sec,
    )


def main() -> None:
    global RUN_TAG, SOURCE_RUN_TAG
    args = parse_args()
    RUN_TAG = args.run_tag
    SOURCE_RUN_TAG = args.source_run_tag
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    timeouts_sec = parse_ints(args.time_horizons_sec)
    entry_bucket_sec = int(args.entry_bucket_sec)
    if entry_bucket_sec not in timeouts_sec:
        timeouts_sec = sorted(set([*timeouts_sec, entry_bucket_sec]))
    upper_bps = parse_floats(args.upper_bps)
    lower_bps = parse_floats(args.lower_bps)
    barrier_pairs = parse_barrier_pairs(args.barrier_pairs)
    stop_levels_bps = parse_floats(args.stop_levels_bps)
    stop_grace_sec = parse_ints(args.stop_grace_sec)
    missing_upper = [upper for upper, _lower in barrier_pairs if upper not in upper_bps]
    missing_lower = [lower for _upper, lower in barrier_pairs if lower not in lower_bps]
    if missing_upper or missing_lower:
        raise ValueError(f"barrier pairs must use values in upper/lower lists: missing {missing_upper} {missing_lower}")

    base_paths = base.Paths(
        panel_root=paths.panel_root,
        source_run_tag=paths.source_run_tag,
        date_dir=paths.date_dir,
        doc_dir=paths.doc_dir,
        run_tag=base.RUN_TAG,
        method_sweep_run_tag=base.METHOD_SWEEP_RUN_TAG,
    )
    df, usable_features = base.load_panel(base_paths)
    df, _targets = base.add_replay_labels(df, event_horizons=[25], time_horizons_sec=timeouts_sec)
    folds = base.make_folds(sorted(df["date"].dropna().astype(str).unique()))
    filters = base.build_filter_masks(df)
    specs = trigger_specs()
    for spec in specs:
        if spec.feature not in usable_features and spec.feature not in base.COMPOSITE_SPECS:
            raise ValueError(f"feature not available: {spec.feature}")
        if spec.filter_name not in filters:
            raise ValueError(f"filter not available: {spec.filter_name}")

    print(
        f"signal path math specs={len(specs)} folds={len(folds)} timeouts={timeouts_sec} "
        f"barriers={barrier_pairs} stops={stop_levels_bps} grace={stop_grace_sec}",
        flush=True,
    )
    fixed, barrier_df, stop_policy = run_diagnostics(
        df,
        folds,
        filters,
        specs,
        timeouts_sec,
        entry_bucket_sec,
        upper_bps,
        lower_bps,
        barrier_pairs,
        stop_levels_bps,
        stop_grace_sec,
        args.control_shift_events,
        args.include_controls,
    )
    entry_refinement = build_entry_refinement_table(fixed, entry_bucket_sec)
    write_outputs(paths, fixed, barrier_df, entry_refinement, stop_policy, timeouts_sec, barrier_pairs, stop_levels_bps, stop_grace_sec)
    print(f"wrote {paths.fixed_csv}", flush=True)
    print(f"wrote {paths.barrier_csv}", flush=True)
    print(f"wrote {paths.entry_refinement_csv}", flush=True)
    print(f"wrote {paths.stop_policy_csv}", flush=True)
    print(f"wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
