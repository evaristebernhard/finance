#!/usr/bin/env python
"""OOS decay check for the locked CCUSDT TFI mutual-bucket prototype.

This script intentionally does not rediscover buckets or optimize parameters on
the OOS day. It applies the previously observed Fold3 TFI trigger thresholds,
mutual positive-EV bucket set, and weak-overlay weights to a new single-day
fixed-event panel.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import ccusdt_signal_path_math as signal_math
import ccusdt_strategy_research as base
import ccusdt_v1_tfi_mutual_exclusion as mutual


RUN_TAG = "20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1"
GUARDRAIL = "research_only_oos_decay_check_locked_prior_no_execution_recommendation_no_alpha_claim"
HIST_ENTRIES = Path("date/ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv")
HIST_BUCKETS = Path("date/ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv")
HIST_MEMBERSHIP = Path("date/ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv")
HIST_SCORECARD = Path("date/ccusdt_v1_tfi_mutual_strategy_scorecard_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv")
HIST_WEIGHTS = Path("date/ccusdt_v1_tfi_mutual_strategy_weights_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv")
TRIGGERS = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]
KEY_COLS = ["fold", "date", "entry_row"]
OLD_FOLD = "expanding_fold3"
VARIANT = "weak_overlay_rank12"


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    oos_source_run_tag: str
    oos_date: str
    date_dir: Path
    doc_dir: Path
    run_tag: str
    hist_entries: Path
    hist_buckets: Path
    hist_membership: Path
    hist_scorecard: Path
    hist_weights: Path

    @property
    def entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_oos_decay_entries_{self.run_tag}.csv"

    @property
    def buckets_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_oos_decay_buckets_{self.run_tag}.csv"

    @property
    def union_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_oos_decay_union_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_oos_decay_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        compact = self.oos_date.replace("-", "")
        return self.doc_dir / f"v1-tfi-oos-decay-day{compact}-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply locked CCUSDT TFI mutual buckets to an OOS day.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--oos-source-run-tag", default="20260518_ccusdt_fixed_factors_oos_day20260516_v1")
    parser.add_argument("--oos-date", default="2026-05-16")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--hist-entries", type=Path, default=HIST_ENTRIES)
    parser.add_argument("--hist-buckets", type=Path, default=HIST_BUCKETS)
    parser.add_argument("--hist-membership", type=Path, default=HIST_MEMBERSHIP)
    parser.add_argument("--hist-scorecard", type=Path, default=HIST_SCORECARD)
    parser.add_argument("--hist-weights", type=Path, default=HIST_WEIGHTS)
    parser.add_argument("--min-total-net-bps", type=float, default=90.0)
    parser.add_argument("--min-net-mean-bps", type=float, default=0.0)
    parser.add_argument("--target-net-bps", type=float, default=2.0)
    parser.add_argument("--entry-bucket-sec", type=int, default=60)
    parser.add_argument("--timeout-sec", type=int, default=60)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def finite(values: pd.Series | np.ndarray) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return arr[np.isfinite(arr)]


def finite_mean(values: pd.Series | np.ndarray) -> float:
    arr = finite(values)
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: pd.Series | np.ndarray, q: float) -> float:
    arr = finite(values)
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def cvar10(values: pd.Series | np.ndarray) -> float:
    arr = finite(values)
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, 0.10))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def safe_rate(mask: pd.Series | np.ndarray) -> float:
    arr = pd.Series(mask).dropna().astype(bool).to_numpy()
    return float(arr.mean()) if len(arr) else np.nan


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    ok = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values = values[ok]
    weights = weights[ok]
    if not len(values):
        return np.nan
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cdf = np.cumsum(weights) / np.sum(weights)
    return float(values[np.searchsorted(cdf, q, side="left").clip(0, len(values) - 1)])


def load_oos_panel(paths: Paths) -> pd.DataFrame:
    panel_paths = base.Paths(
        panel_root=paths.panel_root,
        source_run_tag=paths.oos_source_run_tag,
        date_dir=paths.date_dir,
        doc_dir=paths.doc_dir,
        run_tag=paths.run_tag,
        method_sweep_run_tag="unused",
    )
    df, _ = base.load_panel(panel_paths)
    df, _targets = base.add_replay_labels(df, event_horizons=[25], time_horizons_sec=[60])
    return df


def load_locked_trigger_thresholds(hist_entries: Path) -> dict[str, tuple[float, float]]:
    hist = pd.read_csv(hist_entries, usecols=["fold", "trigger_class", "q_low", "q_high"])
    hist = hist[hist["fold"].eq(OLD_FOLD) & hist["trigger_class"].isin(TRIGGERS)].copy()
    out: dict[str, tuple[float, float]] = {}
    for trigger, group in hist.groupby("trigger_class", sort=True):
        q_low = finite_quantile(group["q_low"], 0.50)
        q_high = finite_quantile(group["q_high"], 0.50)
        out[str(trigger)] = (q_low, q_high)
    missing = [trigger for trigger in TRIGGERS if trigger not in out]
    if missing:
        raise ValueError(f"missing locked thresholds for {missing}")
    return out


def locked_policy_mask(
    values: np.ndarray,
    filter_mask: np.ndarray,
    q_low: float,
    q_high: float,
    policy: str,
) -> tuple[np.ndarray, np.ndarray]:
    finite_mask = np.isfinite(values)
    high = finite_mask & (values >= q_high)
    low = finite_mask & (values <= q_low)
    direction = np.zeros(len(values), dtype="int8")
    if policy == "follow_extremes":
        mask = high | low
        direction[high] = 1
        direction[low] = -1
    elif policy == "short_low":
        mask = low
        direction[low] = -1
    elif policy == "long_high":
        mask = high
        direction[high] = 1
    else:
        raise ValueError(f"unexpected locked TFI policy {policy}")
    return mask & filter_mask, direction


def day_arrays(df: pd.DataFrame) -> dict[int, dict[str, np.ndarray]]:
    out: dict[int, dict[str, np.ndarray]] = {}
    for code, group in df.groupby("date_code", sort=False):
        out[int(code)] = {
            "idx": group.index.to_numpy(dtype="int64"),
            "times": group["local_timestamp"].to_numpy(dtype="float64"),
            "mids": group["mid_price"].to_numpy(dtype="float64"),
            "mid_change_prev": group["mid_change_prev"].fillna(False).to_numpy(dtype=bool),
            "quote_change_prev": group["quote_change_prev"].fillna(False).to_numpy(dtype=bool),
        }
    return out


def cost_one(model: str, entry_spread: float, exit_spread: float) -> float:
    return float(base.cost_array(model, np.asarray([entry_spread]), np.asarray([exit_spread]))[0])


def build_oos_entries(
    df: pd.DataFrame,
    thresholds: dict[str, tuple[float, float]],
    timeout_sec: int,
    entry_bucket_sec: int,
) -> pd.DataFrame:
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_col = f"{target_col}_exit_idx"
    bucket_col = f"{target_col}_bucket"
    filters = base.build_filter_masks(df)
    days = day_arrays(df)
    rows: list[dict[str, Any]] = []
    event_index_all = df.get("event_index", pd.Series(np.arange(len(df)))).to_numpy(dtype="int64")
    date_codes_all = df["date_code"].to_numpy(dtype="int64")
    row_pos_all = df["row_pos_in_day"].to_numpy(dtype="int64")
    timestamp_all = df["local_timestamp"].to_numpy(dtype="float64")
    spread_all = df["spread_bps"].to_numpy(dtype="float64")
    trade_count_all = df.get("trade_window_count", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")
    frames_since_all = df.get("frames_since_mid_change", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")
    past25_all = df.get("past_event_25_bps", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")
    timeout_us = timeout_sec * base.US_PER_SECOND

    for spec in [spec for spec in signal_math.trigger_specs() if spec.trigger_class in TRIGGERS]:
        q_low, q_high = thresholds[spec.trigger_class]
        values = df[spec.feature].to_numpy(dtype="float64")
        mask, direction = locked_policy_mask(values, filters[spec.filter_name], q_low, q_high, spec.policy)
        entry_idx, selected_rows = signal_math.build_entry_idx(df, mask, direction, bucket_col, target_col, exit_col)
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
            mid0 = max(float(mids[local]), base.EPS)
            path_rets = side * 10_000.0 * np.log(np.maximum(mids[path_locals], base.EPS) / mid0)
            if not np.isfinite(path_rets).any():
                continue
            final_exit = int(idx[end_local])
            final_gross = float(path_rets[-1])
            entry_spread = float(spread_all[entry]) if np.isfinite(spread_all[entry]) else np.nan
            final_spread = float(spread_all[final_exit]) if np.isfinite(spread_all[final_exit]) else np.nan
            maker_cost = cost_one("toy_maker_light", entry_spread, final_spread)
            mid_change_path = day["mid_change_prev"][path_locals]
            quote_change_path = day["quote_change_prev"][path_locals]
            first_mid_pos = np.flatnonzero(mid_change_path)
            first_quote_pos = np.flatnonzero(quote_change_path)
            rows.append(
                {
                    "run_tag": RUN_TAG,
                    "source_run_tag": "locked_fold3_thresholds",
                    "guardrail": GUARDRAIL,
                    "fold": f"oos_day{str(df.at[entry, 'date']).replace('-', '')}",
                    "train_start_date": "2026-04-29",
                    "train_end_date": "2026-05-15",
                    "test_start_date": str(df.at[entry, "date"]),
                    "test_end_date": str(df.at[entry, "date"]),
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
                    "feature_value": float(values[entry]) if np.isfinite(values[entry]) else np.nan,
                    "entry_spread_bps": entry_spread,
                    "trade_window_count": float(trade_count_all[entry]) if np.isfinite(trade_count_all[entry]) else np.nan,
                    "frames_since_mid_change": float(frames_since_all[entry]) if np.isfinite(frames_since_all[entry]) else np.nan,
                    "past_event_25_bps": float(past25_all[entry]) if np.isfinite(past25_all[entry]) else np.nan,
                    "timeout_sec": timeout_sec,
                    "final_exit_row": final_exit,
                    "final_hold_sec": float((timestamp_all[final_exit] - timestamp_all[entry]) / base.US_PER_SECOND),
                    "fixed_gross_bps": final_gross,
                    "fixed_cost_maker_bps": maker_cost,
                    "fixed_net_maker_bps": final_gross - maker_cost,
                    "mfe_bps": float(np.nanmax(path_rets)),
                    "mae_bps": float(np.nanmin(path_rets)),
                    "has_mid_transition": bool(len(first_mid_pos)),
                    "has_quote_transition": bool(len(first_quote_pos)),
                    "mid_transition_count": int(mid_change_path.sum()),
                    "quote_transition_count": int(quote_change_path.sum()),
                    "first_mid_transition_hold_sec": (
                        float((times[path_locals[int(first_mid_pos[0])]] - times[local]) / base.US_PER_SECOND)
                        if len(first_mid_pos)
                        else np.nan
                    ),
                    "first_quote_transition_hold_sec": (
                        float((times[path_locals[int(first_quote_pos[0])]] - times[local]) / base.US_PER_SECOND)
                        if len(first_quote_pos)
                        else np.nan
                    ),
                    "first_mid_transition_gross_bps": float(path_rets[int(first_mid_pos[0])])
                    if len(first_mid_pos)
                    else np.nan,
                    "first_quote_transition_gross_bps": float(path_rets[int(first_quote_pos[0])])
                    if len(first_quote_pos)
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def summarize(group: pd.DataFrame, target_net_bps: float) -> dict[str, Any]:
    net = pd.to_numeric(group.get("fixed_net_maker_bps", pd.Series(dtype=float)), errors="coerce")
    gross = pd.to_numeric(group.get("fixed_gross_bps", pd.Series(dtype=float)), errors="coerce")
    cost = pd.to_numeric(group.get("fixed_cost_maker_bps", pd.Series(dtype=float)), errors="coerce")
    top_n = int(math.ceil(len(group) * 0.10)) if len(group) else 0
    top_net = net.sort_values(ascending=False).head(top_n).sum() if top_n else np.nan
    left_net = net.sort_values(ascending=True).head(top_n).sum() if top_n else np.nan
    return {
        "entries": int(len(group)),
        "gross_mean_bps": finite_mean(gross),
        "gross_median_bps": finite_quantile(gross, 0.50),
        "gross_p90_bps": finite_quantile(gross, 0.90),
        "cost_mean_bps": finite_mean(cost),
        "net_mean_bps": finite_mean(net),
        "net_median_bps": finite_quantile(net, 0.50),
        "net_p10_bps": finite_quantile(net, 0.10),
        "net_p90_bps": finite_quantile(net, 0.90),
        "net_cvar10_bps": cvar10(net),
        "gt2_rate": safe_rate(net > target_net_bps),
        "win_rate": safe_rate(net > 0.0),
        "cost_hit_rate": safe_rate(net <= 0.0),
        "positive_net_bps": float(net[net > 0].sum()) if len(net) else np.nan,
        "negative_net_bps": float(net[net < 0].sum()) if len(net) else np.nan,
        "total_net_bps": float(net.sum()) if len(net) else np.nan,
        "top10_net_bps": float(top_net) if np.isfinite(top_net) else np.nan,
        "left10_net_bps": float(left_net) if np.isfinite(left_net) else np.nan,
        "mid_transition_rate": safe_rate(group.get("has_mid_transition", pd.Series(dtype=bool))),
        "quote_transition_rate": safe_rate(group.get("has_quote_transition", pd.Series(dtype=bool))),
    }


def eligible_buckets(hist_buckets: Path, min_total: float, min_mean: float) -> list[str]:
    buckets = pd.read_csv(hist_buckets)
    for col in ["total_net_bps", "net_mean_bps"]:
        buckets[col] = pd.to_numeric(buckets[col], errors="coerce")
    chosen = buckets[
        buckets["fold"].eq(OLD_FOLD)
        & buckets["membership_set"].astype(str).ne("none")
        & buckets["total_net_bps"].gt(min_total)
        & buckets["net_mean_bps"].gt(min_mean)
    ].copy()
    return sorted(chosen["membership_set"].astype(str).unique().tolist())


def historical_overlay_threshold(hist_entries: Path, hist_membership: Path, eligible: list[str]) -> float:
    entries = pd.read_csv(hist_entries, usecols=KEY_COLS + ["frames_since_mid_change"])
    membership = pd.read_csv(hist_membership, usecols=KEY_COLS + ["membership_set"])
    work = membership[
        membership["fold"].eq(OLD_FOLD) & membership["membership_set"].astype(str).isin(eligible)
    ].merge(entries, on=KEY_COLS, how="left")
    vals = finite(work["frames_since_mid_change"])
    return float(np.quantile(vals, 0.90)) if len(vals) else np.nan


def apply_strategy_weights(
    membership: pd.DataFrame,
    hist_weights: Path,
    overlay_threshold: float,
    variant: str = VARIANT,
) -> pd.DataFrame:
    weights = pd.read_csv(hist_weights)
    weights = weights[weights["variant"].eq(variant)].copy()
    weights["base_weight"] = pd.to_numeric(weights["base_weight"], errors="coerce").fillna(0.0)
    weight_map = dict(zip(weights["membership_set"].astype(str), weights["base_weight"].astype(float)))
    work = membership.copy()
    work["base_weight"] = work["membership_set"].astype(str).map(weight_map).fillna(0.0)
    work["overlay_boost"] = 0.0
    if np.isfinite(overlay_threshold):
        work.loc[
            work["base_weight"].gt(0.0)
            & pd.to_numeric(work["frames_since_mid_change"], errors="coerce").ge(overlay_threshold),
            "overlay_boost",
        ] = 0.5
    work["weight"] = work["base_weight"] + work["overlay_boost"]
    work["weighted_net_bps"] = work["weight"] * pd.to_numeric(work["fixed_net_maker_bps"], errors="coerce")
    return work


def weighted_summary(work: pd.DataFrame, target_net_bps: float) -> dict[str, Any]:
    active = work[work["weight"].gt(0.0)].copy()
    net = pd.to_numeric(active["fixed_net_maker_bps"], errors="coerce").to_numpy(dtype="float64")
    weights = pd.to_numeric(active["weight"], errors="coerce").to_numpy(dtype="float64")
    weighted_net = net * weights
    exposure = float(np.nansum(weights))
    top_n = int(math.ceil(len(weighted_net) * 0.10)) if len(weighted_net) else 0
    ordered = np.sort(weighted_net[np.isfinite(weighted_net)])[::-1]
    left = np.sort(weighted_net[np.isfinite(weighted_net)])
    return {
        "variant": VARIANT,
        "entries": int(len(active)),
        "exposure_units": exposure,
        "total_weighted_net_bps": float(np.nansum(weighted_net)),
        "weighted_mean_net_bps": float(np.nansum(weighted_net) / exposure) if exposure > 0 else np.nan,
        "weighted_median_net_bps": weighted_quantile(net, weights, 0.50),
        "weighted_p10_net_bps": weighted_quantile(net, weights, 0.10),
        "weighted_p90_net_bps": weighted_quantile(net, weights, 0.90),
        "weighted_gt2_rate": float(np.nansum(weights[net > target_net_bps]) / exposure) if exposure > 0 else np.nan,
        "cost_hit_rate": float(np.nansum(weights[net <= 0.0]) / exposure) if exposure > 0 else np.nan,
        "positive_net_bps": float(np.nansum(weighted_net[weighted_net > 0])),
        "negative_net_bps": float(np.nansum(weighted_net[weighted_net < 0])),
        "top10_weighted_net_bps": float(np.nansum(ordered[:top_n])) if top_n else np.nan,
        "left10_weighted_net_bps": float(np.nansum(left[:top_n])) if top_n else np.nan,
    }


def comparison_rows(
    hist_scorecard: Path,
    oos_union: dict[str, Any],
    oos_weighted: dict[str, Any],
    oos_date: str,
) -> pd.DataFrame:
    score = pd.read_csv(hist_scorecard)
    if "eval_scope" in score.columns:
        fold3 = score[(score["variant"].eq(VARIANT)) & (score["eval_scope"].eq(OLD_FOLD))].iloc[0].to_dict()
        fold1 = score[(score["variant"].eq(VARIANT)) & (score["eval_scope"].eq("expanding_fold1"))].iloc[0].to_dict()
    else:
        row = score[score["variant"].eq(VARIANT)].iloc[0].to_dict()

        def wide_ref(fold: str) -> dict[str, Any]:
            return {
                "variant": VARIANT,
                "eval_scope": fold,
                "entries": np.nan,
                "exposure_units": np.nan,
                "total_weighted_net_bps": row.get(f"total_weighted_net_bps_{fold}", np.nan),
                "weighted_mean_net_bps": row.get(f"weighted_mean_net_bps_{fold}", np.nan),
                "weighted_median_net_bps": np.nan,
                "weighted_gt2_rate": row.get(f"weighted_gt2_rate_{fold}", np.nan),
                "cost_hit_rate": row.get(f"cost_hit_rate_{fold}", np.nan),
                "positive_net_bps": np.nan,
                "negative_net_bps": np.nan,
                "weighted_cvar10_net_bps": row.get(f"weighted_cvar10_net_bps_{fold}", np.nan),
                "max_drawdown_bps_units": row.get(f"max_drawdown_bps_units_{fold}", np.nan),
            }

        fold3 = wide_ref(OLD_FOLD)
        fold1 = wide_ref("expanding_fold1")
    rows = [
        {"scope": "fold1_weighted_reference", **fold1},
        {"scope": "fold3_weighted_reference", **fold3},
        {"scope": f"oos_{oos_date.replace('-', '_')}_weighted_locked", **oos_weighted},
        {"scope": f"oos_{oos_date.replace('-', '_')}_equal_union_locked", **oos_union},
    ]
    return pd.DataFrame(rows)


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
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


def write_report(
    paths: Paths,
    eligible: list[str],
    thresholds: dict[str, tuple[float, float]],
    overlay_threshold: float,
    buckets: pd.DataFrame,
    comparison: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    lines = [
        f"# CCUSDT TFI OOS Decay Check: {paths.oos_date}",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        f"This check applies locked Fold3 TFI thresholds, mutually-exclusive positive-EV buckets, and the existing weak-overlay strategy weights to the OOS day. It does not optimize on {paths.oos_date}.",
        "",
        "## Locked Inputs",
        "",
        f"- OOS panel: `{paths.panel_root / ('run_tag=' + paths.oos_source_run_tag)}`.",
        f"- Historical entries: `{paths.hist_entries}`.",
        f"- Historical mutual buckets: `{paths.hist_buckets}`.",
        f"- Eligible buckets: `{', '.join(eligible)}`.",
        f"- Overlay: `{VARIANT}`, frames_since_mid_change high 10%, historical threshold `{fmt_num(overlay_threshold)}`.",
        f"- Trigger thresholds: `{json.dumps(thresholds, sort_keys=True)}`.",
        "",
        "## OOS Bucket Readout",
        "",
        *markdown_table(
            buckets.sort_values("total_net_bps", ascending=False),
            [
                "membership_set",
                "entries",
                "gross_mean_bps",
                "cost_mean_bps",
                "net_mean_bps",
                "net_median_bps",
                "net_p90_bps",
                "gt2_rate",
                "cost_hit_rate",
                "total_net_bps",
            ],
            max_rows=20,
        ),
        "",
        "## Decay Comparison",
        "",
        *markdown_table(
            comparison,
            [
                "scope",
                "entries",
                "exposure_units",
                "total_weighted_net_bps",
                "weighted_mean_net_bps",
                "weighted_median_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
                "positive_net_bps",
                "negative_net_bps",
                "total_net_bps",
                "net_mean_bps",
                "net_median_bps",
                "gt2_rate",
            ],
            max_rows=10,
        ),
        "",
        "## Interpretation",
        "",
        f"- Decision: `{summary['decay_state']}`.",
        f"- Weighted OOS mean: `{fmt_num(summary['oos_weighted']['weighted_mean_net_bps'])}` bps versus Fold3 `{fmt_num(summary['fold3_reference'].get('weighted_mean_net_bps'))}` bps and Fold1 `{fmt_num(summary['fold1_reference'].get('weighted_mean_net_bps'))}` bps.",
        f"- Weighted OOS cost-hit rate: `{fmt_num(summary['oos_weighted']['cost_hit_rate'])}` versus Fold3 `{fmt_num(summary['fold3_reference'].get('cost_hit_rate'))}`.",
        f"- OOS equal-union net p90: `{fmt_num(summary['oos_union']['net_p90_bps'])}` bps; net median `{fmt_num(summary['oos_union']['net_median_bps'])}` bps.",
        "",
        "## Outputs",
        "",
        f"- `{paths.entries_csv}`",
        f"- `{paths.buckets_csv}`",
        f"- `{paths.union_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v1_tfi_oos_decay_check.py --oos-source-run-tag {paths.oos_source_run_tag} --oos-date {paths.oos_date} --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        oos_source_run_tag=args.oos_source_run_tag,
        oos_date=args.oos_date,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
        hist_entries=resolve_repo_path(args.hist_entries),
        hist_buckets=resolve_repo_path(args.hist_buckets),
        hist_membership=resolve_repo_path(args.hist_membership),
        hist_scorecard=resolve_repo_path(args.hist_scorecard),
        hist_weights=resolve_repo_path(args.hist_weights),
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    df = load_oos_panel(paths)
    thresholds = load_locked_trigger_thresholds(paths.hist_entries)
    entries = build_oos_entries(df, thresholds, timeout_sec=args.timeout_sec, entry_bucket_sec=args.entry_bucket_sec)
    if entries.empty:
        raise ValueError("no OOS entries produced")
    membership = mutual.build_membership(entries)
    entry_time_cols = KEY_COLS + ["frames_since_mid_change", "trade_window_count", "entry_spread_bps"]
    entry_time = entries[entry_time_cols].drop_duplicates(KEY_COLS, keep="first")
    membership = membership.merge(entry_time, on=KEY_COLS, how="left", suffixes=("", "_entry"))
    eligible = eligible_buckets(paths.hist_buckets, args.min_total_net_bps, args.min_net_mean_bps)
    overlay_threshold = historical_overlay_threshold(paths.hist_entries, paths.hist_membership, eligible)

    bucket_rows: list[dict[str, Any]] = []
    for bucket, group in membership.groupby("membership_set", sort=True):
        row = {
            "run_tag": paths.run_tag,
            "guardrail": GUARDRAIL,
            "fold": f"oos_day{args.oos_date.replace('-', '')}",
            "membership_set": bucket,
            "eligible_from_fold3": bucket in eligible,
        }
        row.update(summarize(group, args.target_net_bps))
        bucket_rows.append(row)
    buckets = pd.DataFrame(bucket_rows).sort_values(["eligible_from_fold3", "total_net_bps"], ascending=[False, False])
    eligible_membership = membership[membership["membership_set"].isin(eligible)].copy()
    oos_union = {"scope": "eligible_union", **summarize(eligible_membership, args.target_net_bps)}
    weighted = apply_strategy_weights(membership, paths.hist_weights, overlay_threshold, VARIANT)
    oos_weighted = weighted_summary(weighted, args.target_net_bps)
    comparison = comparison_rows(paths.hist_scorecard, oos_union, oos_weighted, args.oos_date)

    fold3_ref = comparison[comparison["scope"].eq("fold3_weighted_reference")].iloc[0].to_dict()
    fold1_ref = comparison[comparison["scope"].eq("fold1_weighted_reference")].iloc[0].to_dict()
    mean = float(oos_weighted["weighted_mean_net_bps"])
    gt2 = float(oos_weighted["weighted_gt2_rate"])
    cost_hit = float(oos_weighted["cost_hit_rate"])
    if mean <= 0.0 or gt2 < 0.35 or cost_hit > 0.63:
        decay_state = "decayed_or_fold1_like_throttle_broad"
    elif mean < float(fold3_ref["weighted_mean_net_bps"]) * 0.60:
        decay_state = "partial_decay_trade_smaller"
    else:
        decay_state = "right_tail_still_present"

    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "oos_source_run_tag": paths.oos_source_run_tag,
        "oos_date": paths.oos_date,
        "eligible_buckets": eligible,
        "locked_thresholds": thresholds,
        "overlay_threshold_frames_since_mid_change": overlay_threshold,
        "oos_entries": int(len(entries)),
        "oos_unique_entries": int(len(membership)),
        "eligible_oos_entries": int(len(eligible_membership)),
        "oos_union": oos_union,
        "oos_weighted": oos_weighted,
        "fold3_reference": fold3_ref,
        "fold1_reference": fold1_ref,
        "decay_state": decay_state,
        "outputs": {
            "entries_csv": str(paths.entries_csv),
            "buckets_csv": str(paths.buckets_csv),
            "union_csv": str(paths.union_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }

    entries.to_csv(paths.entries_csv, index=False)
    buckets.to_csv(paths.buckets_csv, index=False)
    comparison.to_csv(paths.union_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(paths, eligible, thresholds, overlay_threshold, buckets, comparison, summary)
    print(
        "[ccusdt_tfi_oos_decay] "
        f"entries={len(entries)} unique={len(membership)} eligible={len(eligible_membership)} "
        f"weighted_mean={oos_weighted['weighted_mean_net_bps']:.4f} "
        f"weighted_total={oos_weighted['total_weighted_net_bps']:.4f} "
        f"gt2={oos_weighted['weighted_gt2_rate']:.4f} "
        f"cost_hit={oos_weighted['cost_hit_rate']:.4f} "
        f"state={decay_state} report={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
