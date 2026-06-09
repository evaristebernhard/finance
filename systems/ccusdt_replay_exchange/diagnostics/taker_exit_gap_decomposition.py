#!/usr/bin/env python
"""Runtime-safe taker-exit gap decomposition.

This is an offline diagnostic. It joins a runtime-safe stopping panel with
label-only fixed-60/oracle columns, then decomposes the value of exiting at a
candidate horizon u instead of fixed 60s:

    G_i(u) = Y_i(u) - Y_i(60)
           = avoided_alpha_decay_i(u) - additional_exit_cross_i(u).

The output is meant to decide whether decay is pretrade/runtime identifiable.
It must not become a strategy runtime input.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


DEFAULT_DIAGNOSTIC_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "taker_exit_runtime_safe_stopping_diag_q70_idle01_g1_20260516_18_20260522"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "taker_exit_gap_decomp_q70_idle01_g1_20260516_18_20260522"
)

KEY_COLUMNS = [
    "date",
    "shadow_position_id",
    "entry_ts_us",
    "state_ts_us",
    "target_horizon_sec",
]

NUMERIC_FACTORS = [
    "running_high_taker_net_bps",
    "drawdown_from_high_bps",
    "current_exit_cross_bps",
    "state_spread_bps",
    "recent_mid_alpha_5s_bps",
    "trade_qty_imbalance",
    "trade_notional_imbalance",
    "recent5s_trade_qty_imbalance",
    "recent5s_trade_notional_imbalance",
    "age_sec",
]

CATEGORICAL_FACTORS = [
    "cell",
    "capacity_source",
]

LABEL_COLUMNS = {
    "fixed60_taker_net_bps",
    "fixed60_delta_from_now_bps",
    "alpha_decay_to_60_bps",
    "oracle_best_net_bps",
    "oracle_best_exit_sec",
    "best_future_net_bps",
    "best_future_exit_sec",
    "best_future_net_gain_bps",
    "spread_blocked_exit",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--margin-bps", type=float, default=0.25)
    parser.add_argument("--min-count", type=int, default=30)
    parser.add_argument("--min-exposure", type=float, default=10.0)
    parser.add_argument("--min-day-positive-frac", type=float, default=2.0 / 3.0)
    return parser.parse_args()


def read_panel(diagnostic_dir: Path) -> pd.DataFrame:
    panel_path = diagnostic_dir / "stopping_panel.parquet"
    label_path = diagnostic_dir / "stopping_labels.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(panel_path)
    if not label_path.exists():
        raise FileNotFoundError(label_path)

    panel = pq.read_table(panel_path).to_pandas()
    labels = pq.read_table(label_path).to_pandas()
    illegal_overlap = sorted((set(panel.columns) & LABEL_COLUMNS) - set(KEY_COLUMNS))
    if illegal_overlap:
        raise ValueError(f"runtime panel contains label-only columns: {illegal_overlap}")
    merged = panel.merge(labels, on=KEY_COLUMNS, how="inner", validate="one_to_one")
    if len(merged) != len(panel):
        raise ValueError(f"panel/label merge lost rows: panel={len(panel)} merged={len(merged)}")
    return merged


def add_gap_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    horizon60 = out[out["target_horizon_sec"] == 60][
        ["shadow_position_id", "current_exit_cross_bps"]
    ].rename(columns={"current_exit_cross_bps": "exit60_cross_bps"})
    out = out.merge(horizon60, on="shadow_position_id", how="left", validate="many_to_one")
    if out["exit60_cross_bps"].isna().any():
        missing = int(out["exit60_cross_bps"].isna().sum())
        raise ValueError(f"missing 60s exit cross for {missing} rows")

    out["actual_exposure"] = pd.to_numeric(out["actual_exposure"], errors="coerce").fillna(0.0)
    out["g_vs60_bps"] = out["current_taker_net_bps"] - out["fixed60_taker_net_bps"]
    out["additional_exit_cross_bps"] = out["current_exit_cross_bps"] - out["exit60_cross_bps"]
    out["avoided_alpha_decay_bps"] = out["alpha_decay_to_60_bps"]
    out["gap_reconstruction_error_bps"] = out["g_vs60_bps"] - (
        out["avoided_alpha_decay_bps"] - out["additional_exit_cross_bps"]
    )
    out["is_candidate_horizon"] = out["target_horizon_sec"] < 60
    return out


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


def weighted_mean(group: pd.DataFrame, column: str) -> float:
    weights = group["actual_exposure"].astype(float).clip(lower=0.0)
    total = float(weights.sum())
    if total <= 0.0:
        return float(group[column].mean()) if len(group) else 0.0
    return float((weights * group[column].astype(float)).sum() / total)


def weighted_sum(group: pd.DataFrame, column: str) -> float:
    weights = group["actual_exposure"].astype(float).clip(lower=0.0)
    return float((weights * group[column].astype(float)).sum())


def summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    exposure = float(group["actual_exposure"].clip(lower=0.0).sum())
    day_means = []
    day_exposures = []
    for _, day_group in group.groupby("date", sort=True):
        day_exposure = float(day_group["actual_exposure"].clip(lower=0.0).sum())
        day_exposures.append(day_exposure)
        day_means.append(weighted_mean(day_group, "g_vs60_bps"))
    positive_days = sum(1 for value in day_means if value > 0.0)
    day_count = len(day_means)
    return {
        "n": int(len(group)),
        "position_count": int(group["shadow_position_id"].nunique()),
        "exposure": exposure,
        "weighted_sum_g_bps": weighted_sum(group, "g_vs60_bps"),
        "weighted_mean_g_bps": weighted_mean(group, "g_vs60_bps"),
        "median_g_bps": float(group["g_vs60_bps"].median()) if len(group) else 0.0,
        "positive_rate": float((group["g_vs60_bps"] > 0.0).mean()) if len(group) else 0.0,
        "weighted_sum_avoided_alpha_bps": weighted_sum(group, "avoided_alpha_decay_bps"),
        "weighted_mean_avoided_alpha_bps": weighted_mean(group, "avoided_alpha_decay_bps"),
        "weighted_sum_additional_exit_cross_bps": weighted_sum(group, "additional_exit_cross_bps"),
        "weighted_mean_additional_exit_cross_bps": weighted_mean(group, "additional_exit_cross_bps"),
        "mean_exit_cross_bps": float(group["current_exit_cross_bps"].mean()) if len(group) else 0.0,
        "mean_spread_bps": float(group["state_spread_bps"].mean()) if len(group) else 0.0,
        "day_count": day_count,
        "positive_day_count": positive_days,
        "positive_day_frac": float(positive_days / day_count) if day_count else 0.0,
        "min_day_exposure": min(day_exposures) if day_exposures else 0.0,
        "max_abs_reconstruction_error_bps": float(group["gap_reconstruction_error_bps"].abs().max())
        if len(group)
        else 0.0,
    }


def horizon_summary(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for horizon, group in df[df["target_horizon_sec"] < 60].groupby("target_horizon_sec", sort=True):
        row = {"target_horizon_sec": float(horizon)}
        row.update(summarize_group(group))
        rows.append(row)
    return rows


def grouped_summary(df: pd.DataFrame, group_cols: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(group_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {key: value for key, value in zip(group_cols, keys)}
        row.update(summarize_group(group))
        rows.append(row)
    return rows


def make_numeric_bins(series: pd.Series, bins: int = 5) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.nunique(dropna=True) <= 1:
        return pd.Series(["all"], index=series.index)
    if (values == 0.0).mean() > 0.35 and (values > 0.0).any():
        out = pd.Series("zero", index=series.index, dtype="object")
        positive = values > 0.0
        positive_values = values[positive]
        try:
            positive_bins = pd.qcut(positive_values.rank(method="first"), bins - 1, labels=False)
            out.loc[positive] = [f"pos_q{int(item) + 1}" for item in positive_bins]
            out.loc[values < 0.0] = "negative"
            return out
        except ValueError:
            pass
    try:
        quantiles = pd.qcut(values.rank(method="first"), bins, labels=False)
        return pd.Series([f"q{int(item) + 1}" for item in quantiles], index=series.index)
    except ValueError:
        return pd.Series(["all"], index=series.index)


def factor_bin_rows(
    df: pd.DataFrame,
    *,
    scope_name: str,
    horizon: float | None,
    factor: str,
    categorical: bool,
) -> list[dict[str, Any]]:
    source = df if horizon is None else df[df["target_horizon_sec"] == horizon]
    if source.empty or factor not in source.columns:
        return []
    work = source.copy()
    if categorical:
        work["_factor_bin"] = work[factor].fillna("<NA>").astype(str)
    else:
        work["_factor_bin"] = make_numeric_bins(work[factor])
    rows: list[dict[str, Any]] = []
    for bin_name, group in work.groupby("_factor_bin", sort=True):
        row = {
            "scope": scope_name,
            "target_horizon_sec": "" if horizon is None else float(horizon),
            "factor": factor,
            "factor_bin": str(bin_name),
        }
        if categorical:
            row["factor_min"] = ""
            row["factor_max"] = ""
        else:
            numeric = pd.to_numeric(group[factor], errors="coerce")
            row["factor_min"] = float(numeric.min()) if len(numeric.dropna()) else ""
            row["factor_max"] = float(numeric.max()) if len(numeric.dropna()) else ""
        row.update(summarize_group(group))
        rows.append(row)
    return rows


def conditional_summaries(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate = df[df["target_horizon_sec"] < 60].copy()
    rows: list[dict[str, Any]] = []
    monotonic_rows: list[dict[str, Any]] = []
    horizons = [float(item) for item in sorted(candidate["target_horizon_sec"].unique())]
    scopes: list[tuple[str, float | None]] = [("all_lt60", None)] + [(f"u={h:g}", h) for h in horizons]

    for scope_name, horizon in scopes:
        scope_rows: list[dict[str, Any]] = []
        for factor in NUMERIC_FACTORS:
            factor_rows = factor_bin_rows(
                candidate,
                scope_name=scope_name,
                horizon=horizon,
                factor=factor,
                categorical=False,
            )
            rows.extend(factor_rows)
            scope_rows = factor_rows
            if len(scope_rows) >= 3:
                means = np.array([float(row["weighted_mean_g_bps"]) for row in scope_rows], dtype=float)
                idx = np.arange(len(means), dtype=float)
                if float(np.std(means)) > 1e-12:
                    corr = float(np.corrcoef(idx, means)[0, 1])
                else:
                    corr = 0.0
                monotonic_rows.append(
                    {
                        "scope": scope_name,
                        "target_horizon_sec": "" if horizon is None else float(horizon),
                        "factor": factor,
                        "bin_count": len(scope_rows),
                        "ordered_bin_mean_g_corr": corr,
                        "first_bin_mean_g_bps": float(means[0]),
                        "last_bin_mean_g_bps": float(means[-1]),
                        "range_last_minus_first_bps": float(means[-1] - means[0]),
                    }
                )
        for factor in CATEGORICAL_FACTORS:
            rows.extend(
                factor_bin_rows(
                    candidate,
                    scope_name=scope_name,
                    horizon=horizon,
                    factor=factor,
                    categorical=True,
                )
            )
    return rows, monotonic_rows


def by_day_factor_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    candidate = df[df["target_horizon_sec"] < 60].copy()
    rows: list[dict[str, Any]] = []
    for factor in NUMERIC_FACTORS + CATEGORICAL_FACTORS:
        if factor not in candidate.columns:
            continue
        work = candidate.copy()
        categorical = factor in CATEGORICAL_FACTORS
        work["_factor_bin"] = work[factor].fillna("<NA>").astype(str) if categorical else make_numeric_bins(work[factor])
        for (day, bin_name), group in work.groupby(["date", "_factor_bin"], sort=True):
            row = {"date": day, "factor": factor, "factor_bin": str(bin_name)}
            row.update(summarize_group(group))
            rows.append(row)
    return rows


def cost_condition_candidates(
    conditional_rows: list[dict[str, Any]],
    *,
    margin_bps: float,
    min_count: int,
    min_exposure: float,
    min_day_positive_frac: float,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in conditional_rows:
        scope = str(row.get("scope", ""))
        if not scope.startswith("u="):
            continue
        if int(row.get("n", 0)) < min_count:
            continue
        if float(row.get("exposure", 0.0)) < min_exposure:
            continue
        if float(row.get("positive_day_frac", 0.0)) < min_day_positive_frac:
            continue
        expected_edge = float(row.get("weighted_mean_g_bps", 0.0))
        if expected_edge <= margin_bps:
            continue
        avoided = float(row.get("weighted_mean_avoided_alpha_bps", 0.0))
        extra_cross = float(row.get("weighted_mean_additional_exit_cross_bps", 0.0))
        if avoided <= extra_cross + margin_bps:
            continue
        candidate = dict(row)
        candidate["margin_bps"] = margin_bps
        candidate["cost_condition_pass"] = True
        candidate["expected_avoided_decay_minus_cost_margin_bps"] = avoided - extra_cross - margin_bps
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            float(item.get("weighted_sum_g_bps", 0.0)),
            float(item.get("weighted_mean_g_bps", 0.0)),
        ),
        reverse=True,
    )
    return candidates


def main() -> None:
    args = parse_args()
    diagnostic_dir = args.diagnostic_dir
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    df = add_gap_columns(read_panel(diagnostic_dir))
    candidate = df[df["target_horizon_sec"] < 60].copy()
    horizon_rows = horizon_summary(df)
    conditional_rows, monotonic_rows = conditional_summaries(df)
    candidates = cost_condition_candidates(
        conditional_rows,
        margin_bps=args.margin_bps,
        min_count=args.min_count,
        min_exposure=args.min_exposure,
        min_day_positive_frac=args.min_day_positive_frac,
    )

    outputs = {
        "horizon_summary_csv": out_dir / "horizon_gap_summary.csv",
        "horizon_by_day_csv": out_dir / "horizon_gap_by_day.csv",
        "horizon_by_cell_csv": out_dir / "horizon_gap_by_cell.csv",
        "conditional_summary_csv": out_dir / "conditional_gap_summary.csv",
        "conditional_by_day_csv": out_dir / "conditional_gap_by_day.csv",
        "monotonicity_csv": out_dir / "factor_monotonicity.csv",
        "cost_candidates_csv": out_dir / "cost_condition_candidates.csv",
        "summary_json": out_dir / "summary.json",
    }
    write_csv(outputs["horizon_summary_csv"], horizon_rows)
    write_csv(outputs["horizon_by_day_csv"], grouped_summary(candidate, ["target_horizon_sec", "date"]))
    write_csv(outputs["horizon_by_cell_csv"], grouped_summary(candidate, ["target_horizon_sec", "cell"]))
    write_csv(outputs["conditional_summary_csv"], conditional_rows)
    write_csv(outputs["conditional_by_day_csv"], by_day_factor_rows(df))
    write_csv(outputs["monotonicity_csv"], monotonic_rows)
    write_csv(outputs["cost_candidates_csv"], candidates[:200])

    best_horizon = max(horizon_rows, key=lambda row: float(row["weighted_sum_g_bps"]))
    summary = {
        "schema_id": "ccusdt_taker_exit_gap_decomposition_v1",
        "diagnostic_dir": str(diagnostic_dir),
        "rows": int(len(df)),
        "positions": int(df["shadow_position_id"].nunique()),
        "candidate_rows": int(len(candidate)),
        "candidate_horizons": [float(item) for item in sorted(candidate["target_horizon_sec"].unique())],
        "actual_exposure": float(df[df["target_horizon_sec"] == 60]["actual_exposure"].sum()),
        "max_abs_gap_reconstruction_error_bps": float(df["gap_reconstruction_error_bps"].abs().max()),
        "best_fixed_horizon_vs60": best_horizon,
        "top_cost_condition_candidates": candidates[:20],
        "margin_bps": args.margin_bps,
        "min_count": args.min_count,
        "min_exposure": args.min_exposure,
        "min_day_positive_frac": args.min_day_positive_frac,
        "outputs": {key: str(value) for key, value in outputs.items()},
    }
    with outputs["summary_json"].open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
