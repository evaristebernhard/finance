#!/usr/bin/env python
"""CCUSDT V2 executable-research framework.

Research-only v2 pass over the fixed CCUSDT CEX L2 factor panel. This script
turns the v1 observations into fold-valid artifacts for quote-transition labels,
residual controls, state-matched random controls, entry-quality bins, exit-shape
diagnostics, risk-control diagnostics, and a no-go/continue scorecard.

It does not simulate queue priority, live fills, fee tiers, or production
execution. Any positive result here remains an information diagnostic until a
separate fill/latency model exists.
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


GUARDRAIL = "research_only_v2_framework_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_framework_v1"
SOURCE_RUN_TAG = base.SOURCE_RUN_TAG
US_PER_SECOND = base.US_PER_SECOND
US_PER_HOUR = 3_600 * US_PER_SECOND
EPS = base.EPS

DEFAULT_TRIGGER_CLASSES = "tfi_follow_flat,tfi_short_flat,tfi_long_flat,tfi_short_stale25,tfi_event_active"
ENTRY_FEATURES = [
    "feature_value",
    "abs_feature_value",
    "entry_spread_bps",
    "frames_since_mid_change",
    "trade_window_count",
    "past_event_25_bps",
    "microprice_dev_bps",
    "queue_imbalance_1",
    "queue_imbalance_5",
    "mlofi_roll10_l1",
    "mlofi_roll10_l25",
    "batch_rows",
    "hour_bucket",
]
RESIDUAL_FEATURES = [
    "spread_bps",
    "frames_since_mid_change",
    "trade_window_count",
    "past_event_25_bps",
    "microprice_dev_bps",
    "queue_imbalance_1",
    "mlofi_roll10_l1",
    "batch_rows",
    "hour_bucket",
]
STOP_LEVELS = [5.0, 8.0, 12.0, 20.0]
COST_ADDERS = [0.0, 1.0, 2.0, 3.0, 5.0]


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def panel_run_root(self) -> Path:
        return self.panel_root / f"run_tag={self.source_run_tag}" / "symbol=CCUSDT"

    @property
    def quote_transition_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_quote_transition_labels_{self.run_tag}.csv"

    @property
    def residual_controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_residual_controls_{self.run_tag}.csv"

    @property
    def matched_controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_matched_controls_{self.run_tag}.csv"

    @property
    def entry_quality_bins_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_entry_quality_bins_{self.run_tag}.csv"

    @property
    def exit_shape_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_exit_shape_{self.run_tag}.csv"

    @property
    def risk_control_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_risk_control_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-framework-run-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 research framework diagnostics.")
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
    parser.add_argument("--trigger-classes", default=DEFAULT_TRIGGER_CLASSES)
    parser.add_argument("--matched-random-iters", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260518)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_strings(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one value")
    return values


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def cvar(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
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
        cells: list[str] = []
        for value in row:
            if isinstance(value, float):
                cells.append(fmt_num(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def add_state_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    local_ts = frame["local_timestamp"].to_numpy(dtype="float64")
    hour = np.floor(np.nan_to_num(local_ts, nan=0.0) / US_PER_HOUR).astype("int64") % 24
    frame["hour_bucket"] = hour
    frame["trade_present_flag"] = (
        frame.get("trade_window_count", pd.Series(np.zeros(len(frame)), index=frame.index)).fillna(0) > 0
    ).astype(int)
    return frame


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


def selected_trigger_specs(trigger_classes: list[str]) -> list[signal_math.TriggerSpec]:
    wanted = set(trigger_classes)
    specs = [spec for spec in signal_math.trigger_specs() if spec.trigger_class in wanted]
    missing = sorted(wanted.difference({spec.trigger_class for spec in specs}))
    if missing:
        raise ValueError(f"unknown trigger classes: {missing}")
    return specs


def cost_one(model: str, entry_spread: float, exit_spread: float) -> float:
    return float(base.cost_array(model, np.asarray([entry_spread]), np.asarray([exit_spread]))[0])


def robust_cost(entry_spread: float, exit_spread: float, adder_bps: float = 0.0) -> float:
    return cost_one("toy_maker_light", entry_spread, exit_spread) + 2.0 + adder_bps


def path_entry_rows(
    df: pd.DataFrame,
    days: dict[int, dict[str, np.ndarray]],
    entry_idx: np.ndarray,
    direction: np.ndarray,
    fold: base.Fold,
    spec: signal_math.TriggerSpec,
    q_low: float,
    q_high: float,
    selected_rows: int,
    phase: str,
    timeout_sec: int,
    entry_bucket_sec: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    stop_rows: list[dict[str, object]] = []

    date_codes = df["date_code"].to_numpy(dtype="int64")
    row_pos = df["row_pos_in_day"].to_numpy(dtype="int64")
    event_index = df.get("event_index", pd.Series(np.arange(len(df)), index=df.index)).to_numpy(dtype="int64")
    timestamp = df["local_timestamp"].to_numpy(dtype="float64")
    spread = df["spread_bps"].to_numpy(dtype="float64")
    feature_values = base.feature_values_for_fold(
        df,
        spec.feature,
        df["date"].isin(fold.train_dates).to_numpy(dtype=bool),
        {},
    )

    field_arrays: dict[str, np.ndarray] = {}
    for col in [
        "trade_window_count",
        "frames_since_mid_change",
        "past_event_25_bps",
        "microprice_dev_bps",
        "queue_imbalance_1",
        "queue_imbalance_5",
        "mlofi_roll10_l1",
        "mlofi_roll10_l25",
        "batch_rows",
        "hour_bucket",
        "trade_present_flag",
    ]:
        if col in df.columns:
            field_arrays[col] = df[col].to_numpy(dtype="float64")
        else:
            field_arrays[col] = np.full(len(df), np.nan, dtype="float64")

    exit_col = f"fwd_time_{entry_bucket_sec}s_bps_exit_idx"
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_idx = df[exit_col].to_numpy(dtype="int64")
    target = df[target_col].to_numpy(dtype="float64")

    for entry in entry_idx:
        entry = int(entry)
        side = int(direction[entry])
        if side == 0:
            continue
        final_exit = int(exit_idx[entry])
        if final_exit < 0 or not np.isfinite(target[entry]):
            continue
        code = int(date_codes[entry])
        day = days.get(code)
        if day is None:
            continue
        local = int(row_pos[entry])
        final_local = int(row_pos[final_exit])
        if final_local <= local or local < 0 or final_local >= len(day["mids"]):
            continue

        path_locals = np.arange(local + 1, final_local + 1, dtype="int64")
        mid0 = max(float(day["mids"][local]), EPS)
        path_rets = side * 10_000.0 * np.log(np.maximum(day["mids"][path_locals], EPS) / mid0)
        if not np.isfinite(path_rets).any():
            continue

        path_idx = day["idx"][path_locals]
        hold_path = (day["times"][path_locals] - day["times"][local]) / US_PER_SECOND
        entry_spread = float(spread[entry]) if np.isfinite(spread[entry]) else np.nan
        final_spread = float(spread[final_exit]) if np.isfinite(spread[final_exit]) else np.nan
        maker_cost = cost_one("toy_maker_light", entry_spread, final_spread)
        taker_cost = cost_one("toy_taker_spread", entry_spread, final_spread)
        robust = robust_cost(entry_spread, final_spread)
        gross = float(path_rets[-1])
        mid_change_path = day["mid_change_prev"][path_locals]
        quote_change_path = day["quote_change_prev"][path_locals]
        first_mid_pos = np.flatnonzero(mid_change_path)
        first_quote_pos = np.flatnonzero(quote_change_path)
        first_mid_ret = float(path_rets[int(first_mid_pos[0])]) if len(first_mid_pos) else np.nan
        first_quote_ret = float(path_rets[int(first_quote_pos[0])]) if len(first_quote_pos) else np.nan
        first_mid_hold = float(hold_path[int(first_mid_pos[0])]) if len(first_mid_pos) else np.nan
        first_quote_hold = float(hold_path[int(first_quote_pos[0])]) if len(first_quote_pos) else np.nan
        mae = float(np.nanmin(path_rets))
        mfe = float(np.nanmax(path_rets))
        post_mid_cont = gross - first_mid_ret if np.isfinite(first_mid_ret) else np.nan
        post_quote_cont = gross - first_quote_ret if np.isfinite(first_quote_ret) else np.nan

        row = {
            "run_tag": RUN_TAG,
            "source_run_tag": SOURCE_RUN_TAG,
            "guardrail": GUARDRAIL,
            "phase": phase,
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
            "entry_event_index": int(event_index[entry]),
            "date": str(df.at[entry, "date"]),
            "date_code": code,
            "entry_local_timestamp": float(timestamp[entry]),
            "direction": side,
            "feature_value": float(feature_values[entry]) if np.isfinite(feature_values[entry]) else np.nan,
            "abs_feature_value": abs(float(feature_values[entry])) if np.isfinite(feature_values[entry]) else np.nan,
            "entry_spread_bps": entry_spread,
            "exit_spread_bps": final_spread,
            "trade_window_count": float(field_arrays["trade_window_count"][entry]),
            "frames_since_mid_change": float(field_arrays["frames_since_mid_change"][entry]),
            "past_event_25_bps": float(field_arrays["past_event_25_bps"][entry]),
            "microprice_dev_bps": float(field_arrays["microprice_dev_bps"][entry]),
            "queue_imbalance_1": float(field_arrays["queue_imbalance_1"][entry]),
            "queue_imbalance_5": float(field_arrays["queue_imbalance_5"][entry]),
            "mlofi_roll10_l1": float(field_arrays["mlofi_roll10_l1"][entry]),
            "mlofi_roll10_l25": float(field_arrays["mlofi_roll10_l25"][entry]),
            "batch_rows": float(field_arrays["batch_rows"][entry]),
            "hour_bucket": int(field_arrays["hour_bucket"][entry]) if np.isfinite(field_arrays["hour_bucket"][entry]) else -1,
            "trade_present_flag": int(field_arrays["trade_present_flag"][entry])
            if np.isfinite(field_arrays["trade_present_flag"][entry])
            else 0,
            "timeout_sec": timeout_sec,
            "entry_bucket_sec": entry_bucket_sec,
            "final_exit_row": final_exit,
            "final_hold_sec": float((timestamp[final_exit] - timestamp[entry]) / US_PER_SECOND),
            "fixed_gross_bps": gross,
            "maker_cost_bps": maker_cost,
            "taker_cost_bps": taker_cost,
            "realistic_proxy_cost_bps": robust,
            "fixed_net_maker_bps": gross - maker_cost,
            "fixed_net_taker_bps": gross - taker_cost,
            "fixed_net_realistic_bps": gross - robust,
            "fixed_net_realistic_plus2_bps": gross - robust_cost(entry_spread, final_spread, 2.0),
            "label_realistic_net_gt_2bps": bool(gross - robust > 2.0),
            "label_cross_realistic_plus_2bps": bool(gross > robust + 2.0),
            "cost_cross_realistic_rate_flag": bool(gross > robust),
            "mfe_bps": mfe,
            "mae_bps": mae,
            "drawup_drawdown_asymmetry_bps": mfe + mae,
            "has_mid_transition": bool(len(first_mid_pos)),
            "has_quote_transition": bool(len(first_quote_pos)),
            "mid_transition_count": int(mid_change_path.sum()),
            "quote_transition_count": int(quote_change_path.sum()),
            "first_mid_transition_hold_sec": first_mid_hold,
            "first_quote_transition_hold_sec": first_quote_hold,
            "first_mid_transition_gross_bps": first_mid_ret,
            "first_quote_transition_gross_bps": first_quote_ret,
            "post_mid_transition_continuation_bps": post_mid_cont,
            "post_quote_transition_continuation_bps": post_quote_cont,
        }
        rows.append(row)

        for stop_bps in STOP_LEVELS:
            hit_pos_arr = np.flatnonzero(path_rets <= -stop_bps)
            stop_hit = bool(len(hit_pos_arr))
            if stop_hit:
                hit_pos = int(hit_pos_arr[0])
                stop_exit = int(path_idx[hit_pos])
                stop_gross = float(path_rets[hit_pos])
                stop_hold = float(hold_path[hit_pos])
                after_rets = path_rets[hit_pos:]
                after_max = float(np.nanmax(after_rets))
                after_final = gross
            else:
                stop_exit = final_exit
                stop_gross = gross
                stop_hold = float((timestamp[final_exit] - timestamp[entry]) / US_PER_SECOND)
                after_max = np.nan
                after_final = np.nan
            stop_spread = float(spread[stop_exit]) if np.isfinite(spread[stop_exit]) else final_spread
            stop_cost = robust_cost(entry_spread, stop_spread)
            stop_net = stop_gross - stop_cost
            fixed_net = gross - robust
            stop_rows.append(
                {
                    "run_tag": RUN_TAG,
                    "source_run_tag": SOURCE_RUN_TAG,
                    "guardrail": GUARDRAIL,
                    "phase": phase,
                    "fold": fold.name,
                    "trigger_class": spec.trigger_class,
                    "entry_row": entry,
                    "date": str(df.at[entry, "date"]),
                    "direction": side,
                    "stop_bps": stop_bps,
                    "stop_hit": stop_hit,
                    "stop_exit_row": stop_exit,
                    "stop_hold_sec": stop_hold,
                    "fixed_net_realistic_bps": fixed_net,
                    "stop_net_realistic_bps": stop_net,
                    "delta_net_bps": stop_net - fixed_net,
                    "fixed_cost_winner": bool(fixed_net > 2.0),
                    "stop_given_fixed_cost_winner": bool(stop_hit and fixed_net > 2.0),
                    "hit_recover_to_cost": bool(stop_hit and after_final > robust),
                    "hit_stop_better": bool(stop_hit and stop_net > fixed_net),
                    "hit_final_above_stop": bool(stop_hit and after_max > stop_bps),
                }
            )
    return rows, stop_rows


def entries_for_phase(
    df: pd.DataFrame,
    days: dict[int, dict[str, np.ndarray]],
    fold: base.Fold,
    spec: signal_math.TriggerSpec,
    phase: str,
    timeout_sec: int,
    entry_bucket_sec: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_mask = df["date"].isin(fold.train_dates).to_numpy(dtype=bool)
    eval_mask = train_mask if phase == "train" else df["date"].isin(fold.test_dates).to_numpy(dtype=bool)
    filters = base.build_filter_masks(df)
    filter_mask = filters[spec.filter_name]
    values = base.feature_values_for_fold(df, spec.feature, train_mask, {})
    mask, direction, q_low, q_high = base.build_policy_mask(
        values,
        train_mask,
        eval_mask,
        filter_mask,
        spec.quantile,
        spec.policy,
    )
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_col = f"{target_col}_exit_idx"
    bucket_col = f"{target_col}_bucket"
    entry_idx, selected_rows = signal_math.build_entry_idx(df, mask, direction, bucket_col, target_col, exit_col)
    entry_rows, stop_rows = path_entry_rows(
        df,
        days,
        entry_idx,
        direction,
        fold,
        spec,
        q_low,
        q_high,
        selected_rows,
        phase,
        timeout_sec,
        entry_bucket_sec,
    )
    return pd.DataFrame(entry_rows), pd.DataFrame(stop_rows)


def clean_feature_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    work = frame.reindex(columns=columns).copy()
    for col in columns:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    return work.replace([np.inf, -np.inf], np.nan)


def fit_predict_entry_quality(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.Series, str, list[float]]:
    if train.empty or test.empty:
        return pd.Series(np.nan, index=test.index), "no_entries", []
    y = train["label_realistic_net_gt_2bps"].astype(int)
    if len(train) < 80 or y.nunique() < 2:
        heuristic = pd.to_numeric(test.get("abs_feature_value", 0.0), errors="coerce").fillna(0.0)
        heuristic -= 0.05 * pd.to_numeric(test.get("entry_spread_bps", 0.0), errors="coerce").fillna(0.0)
        score = heuristic.rank(pct=True).fillna(0.5)
        return score.astype(float), "fallback_feature_rank_insufficient_train_classes", [0.33, 0.66]

    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        x_train = clean_feature_frame(train, ENTRY_FEATURES)
        x_test = clean_feature_frame(test, ENTRY_FEATURES)
        model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(max_iter=500, class_weight="balanced", random_state=17),
        )
        model.fit(x_train, y)
        score = pd.Series(model.predict_proba(x_test)[:, 1], index=test.index)
        train_score = model.predict_proba(x_train)[:, 1]
        edges = [float(np.quantile(train_score, 0.33)), float(np.quantile(train_score, 0.66))]
        return score, "logistic_entry_quality", edges
    except Exception as exc:  # pragma: no cover - defensive fallback
        heuristic = pd.to_numeric(test.get("abs_feature_value", 0.0), errors="coerce").fillna(0.0)
        heuristic -= 0.05 * pd.to_numeric(test.get("entry_spread_bps", 0.0), errors="coerce").fillna(0.0)
        score = heuristic.rank(pct=True).fillna(0.5)
        return score.astype(float), f"fallback_feature_rank_{type(exc).__name__}", [0.33, 0.66]


def assign_quality_bins(score: pd.Series, edges: list[float]) -> pd.Series:
    if not len(score):
        return pd.Series(dtype=object)
    if len(edges) < 2 or not all(np.isfinite(edges)):
        return pd.Series("all", index=score.index)
    bins = np.where(score <= edges[0], "low", np.where(score <= edges[1], "mid", "high"))
    return pd.Series(bins, index=score.index)


def build_entry_quality(
    train_entries: pd.DataFrame,
    test_entries: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if test_entries.empty:
        return test_entries, pd.DataFrame()
    enriched = test_entries.copy()
    enriched["entry_quality_score"] = np.nan
    enriched["entry_quality_bin"] = "all"
    enriched["entry_quality_model"] = "not_fit"
    bin_rows: list[dict[str, object]] = []

    for (fold, trigger), test_g in test_entries.groupby(["fold", "trigger_class"], sort=True):
        train_g = train_entries[
            train_entries["fold"].eq(fold) & train_entries["trigger_class"].eq(trigger)
        ].copy()
        scores, model_name, edges = fit_predict_entry_quality(train_g, test_g)
        bins = assign_quality_bins(scores, edges)
        enriched.loc[test_g.index, "entry_quality_score"] = scores
        enriched.loc[test_g.index, "entry_quality_bin"] = bins
        enriched.loc[test_g.index, "entry_quality_model"] = model_name

        tmp = test_g.copy()
        tmp["entry_quality_score"] = scores
        tmp["entry_quality_bin"] = bins
        for quality_bin, g in tmp.groupby("entry_quality_bin", sort=True):
            net = g["fixed_net_realistic_bps"].to_numpy(dtype="float64")
            plus2 = g["fixed_net_realistic_plus2_bps"].to_numpy(dtype="float64")
            bin_rows.append(
                {
                    "run_tag": RUN_TAG,
                    "source_run_tag": SOURCE_RUN_TAG,
                    "guardrail": GUARDRAIL,
                    "fold": fold,
                    "trigger_class": trigger,
                    "entry_quality_bin": quality_bin,
                    "entry_quality_model": model_name,
                    "train_entries": int(len(train_g)),
                    "entries": int(len(g)),
                    "score_mean": finite_mean(g["entry_quality_score"]),
                    "net_realistic_mean_bps": finite_mean(net),
                    "net_realistic_median_bps": finite_quantile(net, 0.50),
                    "net_realistic_cvar10_bps": cvar(net),
                    "net_realistic_plus2_mean_bps": finite_mean(plus2),
                    "gt_2bps_rate": safe_rate(g["label_realistic_net_gt_2bps"].to_numpy(dtype=bool)),
                    "cost_cross_rate": safe_rate(g["cost_cross_realistic_rate_flag"].to_numpy(dtype=bool)),
                }
            )
    return enriched, pd.DataFrame(bin_rows)


def fit_residual_model(df: pd.DataFrame, fold: base.Fold, target_col: str) -> tuple[np.ndarray, str]:
    train_mask = df["date"].isin(fold.train_dates).to_numpy(dtype=bool)
    valid = train_mask & np.isfinite(df[target_col].to_numpy(dtype="float64"))
    if valid.sum() < 1000:
        return np.full(len(df), np.nan, dtype="float64"), "insufficient_train_rows"
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        x_train = clean_feature_frame(df.loc[valid], RESIDUAL_FEATURES)
        y_train = df.loc[valid, target_col].to_numpy(dtype="float64")
        x_all = clean_feature_frame(df, RESIDUAL_FEATURES)
        model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))
        model.fit(x_train, y_train)
        pred = model.predict(x_all)
        residual = df[target_col].to_numpy(dtype="float64") - pred
        return residual, "ridge_residual_state_model"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return np.full(len(df), np.nan, dtype="float64"), f"residual_model_failed_{type(exc).__name__}"


def build_residual_controls(
    df: pd.DataFrame,
    test_entries: pd.DataFrame,
    folds: list[base.Fold],
    entry_bucket_sec: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if test_entries.empty:
        return pd.DataFrame()
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_col = f"{target_col}_exit_idx"
    spread = df["spread_bps"].to_numpy(dtype="float64")
    for fold in folds:
        residual, model_name = fit_residual_model(df, fold, target_col)
        fold_entries = test_entries[test_entries["fold"].eq(fold.name)].copy()
        for (trigger, quality_bin), g in fold_entries.groupby(["trigger_class", "entry_quality_bin"], sort=True):
            entry_idx = g["entry_row"].to_numpy(dtype="int64")
            exits = df[exit_col].to_numpy(dtype="int64")[entry_idx]
            valid = (entry_idx >= 0) & (exits >= 0) & np.isfinite(residual[entry_idx])
            if not valid.any():
                rows.append(
                    {
                        "run_tag": RUN_TAG,
                        "source_run_tag": SOURCE_RUN_TAG,
                        "guardrail": GUARDRAIL,
                        "fold": fold.name,
                        "trigger_class": trigger,
                        "entry_quality_bin": quality_bin,
                        "residual_model": model_name,
                        "entries": 0,
                    }
                )
                continue
            idx = entry_idx[valid]
            exits = exits[valid]
            side = g.loc[valid, "direction"].to_numpy(dtype="float64")
            residual_gross = side * residual[idx]
            costs = np.asarray(
                [robust_cost(float(spread[i]), float(spread[j])) for i, j in zip(idx, exits)],
                dtype="float64",
            )
            residual_net = residual_gross - costs
            raw_net = g.loc[valid, "fixed_net_realistic_bps"].to_numpy(dtype="float64")
            rows.append(
                {
                    "run_tag": RUN_TAG,
                    "source_run_tag": SOURCE_RUN_TAG,
                    "guardrail": GUARDRAIL,
                    "fold": fold.name,
                    "trigger_class": trigger,
                    "entry_quality_bin": quality_bin,
                    "residual_model": model_name,
                    "entries": int(len(residual_net)),
                    "raw_net_realistic_mean_bps": finite_mean(raw_net),
                    "residual_net_mean_bps": finite_mean(residual_net),
                    "residual_net_median_bps": finite_quantile(residual_net, 0.50),
                    "residual_net_cvar10_bps": cvar(residual_net),
                    "residual_positive_rate": safe_rate(residual_net > 0),
                    "residual_gt_2bps_rate": safe_rate(residual_net > 2.0),
                }
            )
    return pd.DataFrame(rows)


def quantile_bucket(values: np.ndarray, train_mask: np.ndarray, cuts: list[float]) -> np.ndarray:
    out = np.full(len(values), -1, dtype="int16")
    finite_train = values[train_mask & np.isfinite(values)]
    if len(finite_train) < 100:
        return out
    edges = np.quantile(finite_train, cuts)
    finite = np.isfinite(values)
    out[finite] = np.digitize(values[finite], edges, right=True).astype("int16")
    return out


def matched_keys(df: pd.DataFrame, fold: base.Fold) -> dict[str, np.ndarray]:
    train_mask = df["date"].isin(fold.train_dates).to_numpy(dtype=bool)
    frames = df["frames_since_mid_change"].to_numpy(dtype="float64")
    stale = np.where(frames >= 70, 2, np.where(frames >= 25, 1, 0)).astype("int16")
    spread_bucket = quantile_bucket(df["spread_bps"].to_numpy(dtype="float64"), train_mask, [0.33, 0.66])
    past_bucket = quantile_bucket(
        np.abs(df.get("past_event_25_bps", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64")),
        train_mask,
        [0.33, 0.66],
    )
    activity_bucket = quantile_bucket(
        df.get("batch_rows", pd.Series(np.full(len(df), np.nan))).to_numpy(dtype="float64"),
        train_mask,
        [0.33, 0.66],
    )
    date = df["date"].astype(str).to_numpy()
    trade = df["trade_present_flag"].to_numpy(dtype="int16")
    hour = df["hour_bucket"].to_numpy(dtype="int16")
    strict = np.asarray(
        [
            f"{d}|s{st}|t{tr}|sp{sp}|p{pa}|a{ac}|h{hr}"
            for d, st, tr, sp, pa, ac, hr in zip(date, stale, trade, spread_bucket, past_bucket, activity_bucket, hour)
        ],
        dtype=object,
    )
    loose = np.asarray([f"{d}|s{st}|t{tr}|sp{sp}" for d, st, tr, sp in zip(date, stale, trade, spread_bucket)], dtype=object)
    date_state = np.asarray([f"{d}|s{st}|t{tr}" for d, st, tr in zip(date, stale, trade)], dtype=object)
    return {"strict": strict, "loose": loose, "date_state": date_state, "date": date}


def pool_by_key(indices: np.ndarray, keys: np.ndarray) -> dict[str, np.ndarray]:
    pools: dict[str, list[int]] = {}
    for idx in indices:
        pools.setdefault(str(keys[idx]), []).append(int(idx))
    return {key: np.asarray(value, dtype="int64") for key, value in pools.items()}


def sample_matched_net(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    spec: signal_math.TriggerSpec,
    fold: base.Fold,
    rng: np.random.Generator,
    iters: int,
    entry_bucket_sec: int,
) -> dict[str, object]:
    if entries.empty:
        return {}
    filters = base.build_filter_masks(df)
    filter_mask = filters[spec.filter_name]
    test_mask = df["date"].isin(fold.test_dates).to_numpy(dtype=bool)
    target_col = f"fwd_time_{entry_bucket_sec}s_bps"
    exit_col = f"{target_col}_exit_idx"
    target = df[target_col].to_numpy(dtype="float64")
    exit_idx = df[exit_col].to_numpy(dtype="int64")
    spread = df["spread_bps"].to_numpy(dtype="float64")
    valid_pool = np.flatnonzero(test_mask & filter_mask & np.isfinite(target) & (exit_idx >= 0))
    keys = matched_keys(df, fold)
    pools = {level: pool_by_key(valid_pool, arr) for level, arr in keys.items()}

    means: list[float] = []
    medians: list[float] = []
    for _ in range(iters):
        sampled: list[float] = []
        for row in entries.itertuples(index=False):
            entry = int(row.entry_row)
            side = int(row.direction)
            picked = -1
            for level in ("strict", "loose", "date_state", "date"):
                pool = pools[level].get(str(keys[level][entry]))
                if pool is not None and len(pool):
                    picked = int(pool[int(rng.integers(0, len(pool)))])
                    break
            if picked < 0:
                continue
            out = int(exit_idx[picked])
            gross = side * float(target[picked])
            cost = robust_cost(float(spread[picked]), float(spread[out]))
            sampled.append(gross - cost)
        if sampled:
            arr = np.asarray(sampled, dtype="float64")
            means.append(float(arr.mean()))
            medians.append(float(np.median(arr)))
    mean_arr = np.asarray(means, dtype="float64")
    med_arr = np.asarray(medians, dtype="float64")
    signal_mean = float(entries["fixed_net_realistic_bps"].mean())
    return {
        "run_tag": RUN_TAG,
        "source_run_tag": SOURCE_RUN_TAG,
        "guardrail": GUARDRAIL,
        "fold": fold.name,
        "trigger_class": spec.trigger_class,
        "entry_quality_bin": str(entries["entry_quality_bin"].iloc[0]) if "entry_quality_bin" in entries.columns else "all",
        "match_dimensions": "date,stale_bucket,trade_present,spread_bucket,past_return_bucket,event_activity_bucket,hour_bucket",
        "entries": int(len(entries)),
        "iters": int(iters),
        "signal_mean_bps": signal_mean,
        "signal_median_bps": float(entries["fixed_net_realistic_bps"].median()),
        "matched_random_mean_p05_bps": float(np.quantile(mean_arr, 0.05)) if len(mean_arr) else np.nan,
        "matched_random_mean_p50_bps": float(np.quantile(mean_arr, 0.50)) if len(mean_arr) else np.nan,
        "matched_random_mean_p95_bps": float(np.quantile(mean_arr, 0.95)) if len(mean_arr) else np.nan,
        "matched_random_median_p50_bps": float(np.quantile(med_arr, 0.50)) if len(med_arr) else np.nan,
        "prob_random_mean_ge_signal": float((mean_arr >= signal_mean).mean()) if len(mean_arr) else np.nan,
        "signal_minus_random_p50_bps": signal_mean - float(np.quantile(mean_arr, 0.50)) if len(mean_arr) else np.nan,
    }


def build_matched_controls(
    df: pd.DataFrame,
    test_entries: pd.DataFrame,
    folds: list[base.Fold],
    specs: list[signal_math.TriggerSpec],
    rng: np.random.Generator,
    iters: int,
    entry_bucket_sec: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold in folds:
        for spec in specs:
            entries_all = test_entries[
                test_entries["fold"].eq(fold.name) & test_entries["trigger_class"].eq(spec.trigger_class)
            ]
            for _quality_bin, entries in entries_all.groupby("entry_quality_bin", sort=True):
                row = sample_matched_net(df, entries, spec, fold, rng, iters, entry_bucket_sec)
                if row:
                    rows.append(row)
    return pd.DataFrame(rows)


def summarize_exit_shape(entries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if entries.empty:
        return pd.DataFrame()
    for (fold, trigger, quality_bin), g in entries.groupby(["fold", "trigger_class", "entry_quality_bin"], sort=True):
        net = g["fixed_net_realistic_bps"].to_numpy(dtype="float64")
        net_plus2 = g["fixed_net_realistic_plus2_bps"].to_numpy(dtype="float64")
        gross = g["fixed_gross_bps"].to_numpy(dtype="float64")
        top10_cut = finite_quantile(net, 0.90)
        net_sum = float(np.nansum(net))
        top10_share = float(np.nansum(net[net >= top10_cut]) / net_sum) if net_sum > EPS else np.nan
        rows.append(
            {
                "run_tag": RUN_TAG,
                "source_run_tag": SOURCE_RUN_TAG,
                "guardrail": GUARDRAIL,
                "fold": fold,
                "trigger_class": trigger,
                "entry_quality_bin": quality_bin,
                "entries": int(len(g)),
                "gross_mean_bps": finite_mean(gross),
                "net_realistic_mean_bps": finite_mean(net),
                "net_realistic_plus2_mean_bps": finite_mean(net_plus2),
                "net_realistic_median_bps": finite_quantile(net, 0.50),
                "net_realistic_cvar10_bps": cvar(net),
                "gt_2bps_rate": safe_rate(g["label_realistic_net_gt_2bps"].to_numpy(dtype=bool)),
                "cost_cross_rate": safe_rate(g["cost_cross_realistic_rate_flag"].to_numpy(dtype=bool)),
                "top10_net_share_of_total_net": top10_share,
                "has_mid_transition_rate": safe_rate(g["has_mid_transition"].to_numpy(dtype=bool)),
                "has_quote_transition_rate": safe_rate(g["has_quote_transition"].to_numpy(dtype=bool)),
                "first_mid_transition_gross_mean_bps": finite_mean(g["first_mid_transition_gross_bps"]),
                "post_mid_transition_continuation_mean_bps": finite_mean(g["post_mid_transition_continuation_bps"]),
                "mfe_mean_bps": finite_mean(g["mfe_bps"]),
                "mae_mean_bps": finite_mean(g["mae_bps"]),
                "drawup_drawdown_asymmetry_mean_bps": finite_mean(g["drawup_drawdown_asymmetry_bps"]),
            }
        )
    return pd.DataFrame(rows)


def summarize_risk_control(stop_rows: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    if stop_rows.empty or entries.empty:
        return pd.DataFrame()
    enrich_cols = entries[["fold", "trigger_class", "entry_row", "entry_quality_bin"]].drop_duplicates()
    work = stop_rows.merge(enrich_cols, on=["fold", "trigger_class", "entry_row"], how="left")
    work["entry_quality_bin"] = work["entry_quality_bin"].fillna("all")
    rows: list[dict[str, object]] = []
    for (fold, trigger, quality_bin, stop_bps), g in work.groupby(
        ["fold", "trigger_class", "entry_quality_bin", "stop_bps"],
        sort=True,
    ):
        fixed = g["fixed_net_realistic_bps"].to_numpy(dtype="float64")
        stopped = g["stop_net_realistic_bps"].to_numpy(dtype="float64")
        hit = g["stop_hit"].to_numpy(dtype=bool)
        hit_g = g[hit]
        fixed_winners = g["fixed_cost_winner"].to_numpy(dtype=bool)
        killed = g["stop_given_fixed_cost_winner"].to_numpy(dtype=bool)
        saved = hit_g["hit_stop_better"].to_numpy(dtype=bool) if len(hit_g) else np.asarray([], dtype=bool)
        killed_count = int(killed.sum())
        rows.append(
            {
                "run_tag": RUN_TAG,
                "source_run_tag": SOURCE_RUN_TAG,
                "guardrail": GUARDRAIL,
                "fold": fold,
                "trigger_class": trigger,
                "entry_quality_bin": quality_bin,
                "stop_bps": float(stop_bps),
                "entries": int(len(g)),
                "stop_hit_rate": safe_rate(hit),
                "fixed_net_mean_bps": finite_mean(fixed),
                "stop_net_mean_bps": finite_mean(stopped),
                "delta_net_mean_bps": finite_mean(stopped - fixed),
                "fixed_cvar10_bps": cvar(fixed),
                "stop_cvar10_bps": cvar(stopped),
                "delta_cvar10_bps": cvar(stopped) - cvar(fixed),
                "fixed_cost_winner_rate": safe_rate(fixed_winners),
                "stop_given_fixed_cost_winner_rate": safe_rate(killed),
                "hit_recover_to_cost_rate": safe_rate(hit_g["hit_recover_to_cost"].to_numpy(dtype=bool)) if len(hit_g) else np.nan,
                "hit_stop_better_rate": safe_rate(saved) if len(saved) else np.nan,
                "save_to_kill_ratio": float(saved.sum() / killed_count) if killed_count else np.nan,
            }
        )
    return pd.DataFrame(rows)


def scorecard_rows(
    exit_shape: pd.DataFrame,
    matched: pd.DataFrame,
    residual: pd.DataFrame,
    risk: pd.DataFrame,
) -> pd.DataFrame:
    if exit_shape.empty:
        return pd.DataFrame()
    all_rows = exit_shape.copy()
    matched_key = (
        matched.set_index(["fold", "trigger_class", "entry_quality_bin"]) if not matched.empty else pd.DataFrame()
    )
    residual_key = (
        residual.set_index(["fold", "trigger_class", "entry_quality_bin"]) if not residual.empty else pd.DataFrame()
    )
    best_risk = pd.DataFrame()
    if not risk.empty:
        risk_all = risk[risk["entry_quality_bin"].isin(["high", "all"])].copy()
        risk_all["risk_score"] = (
            pd.to_numeric(risk_all["delta_cvar10_bps"], errors="coerce").fillna(-999)
            + pd.to_numeric(risk_all["delta_net_mean_bps"], errors="coerce").fillna(-999)
        )
        best_risk = risk_all.sort_values("risk_score", ascending=False).drop_duplicates(
            ["fold", "trigger_class", "entry_quality_bin"]
        )
        best_risk = best_risk.set_index(["fold", "trigger_class", "entry_quality_bin"])
    rows: list[dict[str, object]] = []
    for row in all_rows.itertuples(index=False):
        key = (row.fold, row.trigger_class, row.entry_quality_bin)
        matched_row = matched_key.loc[key] if not matched_key.empty and key in matched_key.index else None
        residual_row = residual_key.loc[key] if not residual_key.empty and key in residual_key.index else None
        risk_row = best_risk.loc[key] if not best_risk.empty and key in best_risk.index else None

        entries = int(row.entries)
        sparse = "stale" in str(row.trigger_class) or "event_active" in str(row.trigger_class)
        sample_pass = entries >= (100 if sparse else 500)
        economics_pass = float(row.net_realistic_mean_bps) > 2.0 if np.isfinite(row.net_realistic_mean_bps) else False
        cost_stress_pass = False
        controls_pass = False
        residual_pass = False
        tail_pass = False
        risk_pass = False
        if np.isfinite(row.net_realistic_plus2_mean_bps):
            cost_stress_pass = float(row.net_realistic_plus2_mean_bps) > 0.0
        if matched_row is not None:
            prob = float(matched_row["prob_random_mean_ge_signal"])
            margin = float(matched_row["signal_minus_random_p50_bps"])
            controls_pass = np.isfinite(prob) and prob < 0.05 and np.isfinite(margin) and margin > 2.0
        if residual_row is not None:
            residual_mean = float(residual_row["residual_net_mean_bps"])
            residual_pass = np.isfinite(residual_mean) and residual_mean > 0.0
        if np.isfinite(row.top10_net_share_of_total_net):
            tail_pass = float(row.top10_net_share_of_total_net) <= 0.85
        if risk_row is not None:
            delta_cvar = float(risk_row["delta_cvar10_bps"])
            delta_mean = float(risk_row["delta_net_mean_bps"])
            kill = float(risk_row["stop_given_fixed_cost_winner_rate"])
            risk_pass = (
                np.isfinite(delta_cvar)
                and delta_cvar >= 5.0
                and np.isfinite(delta_mean)
                and delta_mean >= -0.5
                and np.isfinite(kill)
                and kill <= 0.10
            )
        execution_realism_pass = False
        positive_bin = bool(np.isfinite(row.net_realistic_mean_bps) and float(row.net_realistic_mean_bps) > 0.0)
        if all([sample_pass, economics_pass, cost_stress_pass, controls_pass, residual_pass, tail_pass, risk_pass]):
            status = "research_pass_execution_blocked_by_fill_model"
        elif controls_pass and residual_pass and positive_bin:
            status = "research_continue_needs_cost_tail_or_risk_repair"
        else:
            status = "research_only_not_promoted"
        rows.append(
            {
                "run_tag": RUN_TAG,
                "source_run_tag": SOURCE_RUN_TAG,
                "guardrail": GUARDRAIL,
                "fold": row.fold,
                "trigger_class": row.trigger_class,
                "entry_quality_bin": row.entry_quality_bin,
                "entries": entries,
                "net_realistic_mean_bps": row.net_realistic_mean_bps,
                "net_realistic_plus2_mean_bps": row.net_realistic_plus2_mean_bps,
                "net_realistic_median_bps": row.net_realistic_median_bps,
                "net_realistic_cvar10_bps": row.net_realistic_cvar10_bps,
                "gt_2bps_rate": row.gt_2bps_rate,
                "top10_net_share_of_total_net": row.top10_net_share_of_total_net,
                "matched_random_prob_ge_signal": matched_row["prob_random_mean_ge_signal"] if matched_row is not None else np.nan,
                "signal_minus_random_p50_bps": matched_row["signal_minus_random_p50_bps"] if matched_row is not None else np.nan,
                "residual_net_mean_bps": residual_row["residual_net_mean_bps"] if residual_row is not None else np.nan,
                "best_stop_bps": risk_row["stop_bps"] if risk_row is not None else np.nan,
                "best_stop_delta_cvar10_bps": risk_row["delta_cvar10_bps"] if risk_row is not None else np.nan,
                "best_stop_delta_net_mean_bps": risk_row["delta_net_mean_bps"] if risk_row is not None else np.nan,
                "sample_pass": sample_pass,
                "economics_pass": economics_pass,
                "cost_stress_pass": cost_stress_pass,
                "controls_pass": controls_pass,
                "residual_pass": residual_pass,
                "tail_pass": tail_pass,
                "risk_pass": risk_pass,
                "execution_realism_pass": execution_realism_pass,
                "scorecard_status": status,
            }
        )
    return pd.DataFrame(rows)


def write_report(
    paths: Paths,
    entries: pd.DataFrame,
    quality_bins: pd.DataFrame,
    matched: pd.DataFrame,
    residual: pd.DataFrame,
    exit_shape: pd.DataFrame,
    risk: pd.DataFrame,
    scorecard: pd.DataFrame,
    folds: list[base.Fold],
    specs: list[signal_math.TriggerSpec],
    args: argparse.Namespace,
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Framework Run")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from source panel `{paths.source_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This is a fold-valid research framework run. It is not queue-position fill evidence, "
        "not a live execution simulation, not trading advice, and not an alpha claim."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Trigger classes: `{', '.join(spec.trigger_class for spec in specs)}`.")
    lines.append(f"- Folds: `{', '.join(fold.name for fold in folds)}`.")
    lines.append(f"- Validation entries with path labels: `{len(entries)}`.")
    lines.append("- Cost proxy: `toy_maker_light + 2bps`, with scorecard retaining execution-realism no-go.")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    if scorecard.empty:
        lines.append("_No scorecard rows._")
    else:
        view = scorecard.sort_values(["scorecard_status", "net_realistic_mean_bps"], ascending=[True, False])
        lines.extend(
            markdown_table(
                view,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "entries",
                    "net_realistic_mean_bps",
                    "net_realistic_plus2_mean_bps",
                    "matched_random_prob_ge_signal",
                    "signal_minus_random_p50_bps",
                    "residual_net_mean_bps",
                    "top10_net_share_of_total_net",
                    "sample_pass",
                    "economics_pass",
                    "controls_pass",
                    "residual_pass",
                    "tail_pass",
                    "risk_pass",
                    "execution_realism_pass",
                    "scorecard_status",
                ],
                30,
            )
        )
    lines.append("")
    lines.append("## Entry Quality")
    lines.append("")
    if quality_bins.empty:
        lines.append("_No entry-quality rows._")
    else:
        top_quality = quality_bins.sort_values("net_realistic_mean_bps", ascending=False)
        lines.extend(
            markdown_table(
                top_quality,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "entry_quality_model",
                    "entries",
                    "net_realistic_mean_bps",
                    "net_realistic_plus2_mean_bps",
                    "gt_2bps_rate",
                    "cost_cross_rate",
                ],
                20,
            )
        )
    lines.append("")
    lines.append("## Matched Controls")
    lines.append("")
    if matched.empty:
        lines.append("_No matched-control rows._")
    else:
        lines.extend(
            markdown_table(
                matched.sort_values("signal_minus_random_p50_bps", ascending=False),
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
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
    lines.append("## Risk Read")
    lines.append("")
    if risk.empty:
        lines.append("_No risk-control rows._")
    else:
        risk_view = risk.sort_values(["delta_cvar10_bps", "delta_net_mean_bps"], ascending=False)
        lines.extend(
            markdown_table(
                risk_view,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "stop_bps",
                    "entries",
                    "stop_hit_rate",
                    "delta_net_mean_bps",
                    "delta_cvar10_bps",
                    "stop_given_fixed_cost_winner_rate",
                    "save_to_kill_ratio",
                ],
                20,
            )
        )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(
        "Execution status remains no-go because this run still uses a snapshot-frame factor panel and no queue/fill/latency model. "
        "Rows that pass research controls are candidates for one further execution-realism pass, not deployable strategies."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [
        paths.quote_transition_csv,
        paths.residual_controls_csv,
        paths.matched_controls_csv,
        paths.entry_quality_bins_csv,
        paths.exit_shape_csv,
        paths.risk_control_csv,
        paths.scorecard_csv,
        paths.summary_json,
    ]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(f"python scripts/ccusdt_v2_research_framework.py --matched-random-iters {int(args.matched_random_iters)}")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    paths: Paths,
    entries: pd.DataFrame,
    residual: pd.DataFrame,
    matched: pd.DataFrame,
    quality_bins: pd.DataFrame,
    exit_shape: pd.DataFrame,
    risk: pd.DataFrame,
    scorecard: pd.DataFrame,
    train_entries: pd.DataFrame,
    folds: list[base.Fold],
    specs: list[signal_math.TriggerSpec],
    args: argparse.Namespace,
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    entries.to_csv(paths.quote_transition_csv, index=False)
    residual.to_csv(paths.residual_controls_csv, index=False)
    matched.to_csv(paths.matched_controls_csv, index=False)
    quality_bins.to_csv(paths.entry_quality_bins_csv, index=False)
    exit_shape.to_csv(paths.exit_shape_csv, index=False)
    risk.to_csv(paths.risk_control_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "source_run_tag": paths.source_run_tag,
        "guardrail": GUARDRAIL,
        "trigger_classes": [spec.trigger_class for spec in specs],
        "folds": [
            {"name": fold.name, "train_dates": list(fold.train_dates), "test_dates": list(fold.test_dates)}
            for fold in folds
        ],
        "train_entries": int(len(train_entries)),
        "validation_entries": int(len(entries)),
        "residual_rows": int(len(residual)),
        "matched_control_rows": int(len(matched)),
        "entry_quality_bin_rows": int(len(quality_bins)),
        "exit_shape_rows": int(len(exit_shape)),
        "risk_control_rows": int(len(risk)),
        "scorecard_rows": int(len(scorecard)),
        "matched_random_iters": int(args.matched_random_iters),
        "timeout_sec": int(args.timeout_sec),
        "entry_bucket_sec": int(args.entry_bucket_sec),
        "execution_realism_status": "no_go_snapshot_frame_panel_no_queue_fill_latency_model",
        "outputs": {
            "quote_transition_csv": str(paths.quote_transition_csv),
            "residual_controls_csv": str(paths.residual_controls_csv),
            "matched_controls_csv": str(paths.matched_controls_csv),
            "entry_quality_bins_csv": str(paths.entry_quality_bins_csv),
            "exit_shape_csv": str(paths.exit_shape_csv),
            "risk_control_csv": str(paths.risk_control_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, entries, quality_bins, matched, residual, exit_shape, risk, scorecard, folds, specs, args)


def main() -> None:
    args = parse_args()
    global RUN_TAG, SOURCE_RUN_TAG
    RUN_TAG = args.run_tag
    SOURCE_RUN_TAG = args.source_run_tag
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    specs = selected_trigger_specs(parse_strings(args.trigger_classes))
    rng = np.random.default_rng(args.seed)

    print("[ccusdt_v2] load panel", flush=True)
    df, _usable = base.load_panel(
        base.Paths(
            panel_root=paths.panel_root,
            source_run_tag=paths.source_run_tag,
            date_dir=paths.date_dir,
            doc_dir=paths.doc_dir,
            run_tag=paths.run_tag,
            method_sweep_run_tag=base.METHOD_SWEEP_RUN_TAG,
        )
    )
    df, _targets = base.add_replay_labels(df, event_horizons=[25], time_horizons_sec=[args.entry_bucket_sec])
    df = add_state_columns(df)
    dates = sorted(df["date"].dropna().astype(str).unique())
    folds = base.make_folds(dates)
    days = day_arrays(df)
    print(f"[ccusdt_v2] rows={len(df)} dates={len(dates)} folds={len(folds)} specs={len(specs)}", flush=True)

    train_entry_frames: list[pd.DataFrame] = []
    test_entry_frames: list[pd.DataFrame] = []
    test_stop_frames: list[pd.DataFrame] = []
    for fold in folds:
        for spec in specs:
            print(f"[ccusdt_v2] build entries fold={fold.name} trigger={spec.trigger_class}", flush=True)
            train_entries, _train_stops = entries_for_phase(
                df,
                days,
                fold,
                spec,
                "train",
                args.timeout_sec,
                args.entry_bucket_sec,
            )
            test_entries, test_stops = entries_for_phase(
                df,
                days,
                fold,
                spec,
                "test",
                args.timeout_sec,
                args.entry_bucket_sec,
            )
            if not train_entries.empty:
                train_entry_frames.append(train_entries)
            if not test_entries.empty:
                test_entry_frames.append(test_entries)
            if not test_stops.empty:
                test_stop_frames.append(test_stops)

    train_entries = pd.concat(train_entry_frames, ignore_index=True) if train_entry_frames else pd.DataFrame()
    test_entries = pd.concat(test_entry_frames, ignore_index=True) if test_entry_frames else pd.DataFrame()
    test_stops = pd.concat(test_stop_frames, ignore_index=True) if test_stop_frames else pd.DataFrame()
    print(
        f"[ccusdt_v2] train_entries={len(train_entries)} test_entries={len(test_entries)} stop_rows={len(test_stops)}",
        flush=True,
    )

    test_entries, quality_bins = build_entry_quality(train_entries, test_entries)
    residual = build_residual_controls(df, test_entries, folds, args.entry_bucket_sec)
    matched = build_matched_controls(
        df,
        test_entries,
        folds,
        specs,
        rng,
        args.matched_random_iters,
        args.entry_bucket_sec,
    )
    exit_shape = summarize_exit_shape(test_entries)
    risk = summarize_risk_control(test_stops, test_entries)
    scorecard = scorecard_rows(exit_shape, matched, residual, risk)
    write_outputs(
        paths,
        test_entries,
        residual,
        matched,
        quality_bins,
        exit_shape,
        risk,
        scorecard,
        train_entries,
        folds,
        specs,
        args,
    )
    print(f"[ccusdt_v2] wrote {paths.scorecard_csv}", flush=True)
    print(f"[ccusdt_v2] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
