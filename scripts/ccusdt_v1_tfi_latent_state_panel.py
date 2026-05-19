#!/usr/bin/env python
"""Latent-state diagnostic panel for CCUSDT TFI entries.

This is a research diagnostic, not a strategy optimizer. It merges the existing
strict as-of entry estimates with pre-trade core quantity proxies, creates
prior-date percentile state scores, and tests whether those scores help explain
the daily inversion variable I_d = G_high - G_reduce.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_latent_state_panel_v1"
GUARDRAIL = "research_only_prior_proxy_latent_state_diagnostic_no_execution_recommendation"

CORE_FILE_NAME = "ccusdt_v1_tfi_core_quantity_scored_entries_20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.csv"
ENTRY_EST_FILE_NAME = "ccusdt_v1_tfi_entry_estimates_20260518_ccusdt_v1_tfi_entry_estimation_v1.csv"
EPS = 1e-12

HIGH_CLASSES = {"strong_positive", "positive_right_tail_fragile"}
REDUCE_CLASSES = {"weak_positive_mean", "avoid_or_reduce", "insufficient_history"}

CORE_COLS = [
    "date",
    "entry_row",
    "entry_event_index",
    "direction",
    "frames_since_mid_change",
    "trade_window_count",
    "entry_spread_bps",
    "past_event_25_bps",
    "x_raw",
    "x_fast_raw",
    "mlofi_raw_aligned",
    "mlofi25_raw_aligned",
    "ofi_raw_aligned",
    "past_release_raw",
    "log_opp_depth5_quote",
    "log_opp_depth25_quote",
    "log_opp_replenish",
    "log_opp_depletion",
    "spread_raw",
    "shock_raw",
    "microprice_raw_aligned",
    "obi5_raw_aligned",
    "X_t",
    "X_fast_t",
    "M_t",
    "O_t",
    "P_t",
    "Theta_t",
    "log_U_t",
    "A_absorption_t",
    "E_exhaustion_t",
    "C_confirm_t",
    "D_divergence_t",
    "release_score_t",
    "lambda_prior_top_u",
    "lambda_prior_top_x",
]

ENTRY_COLS = [
    "fold",
    "date",
    "entry_row",
    "entry_ts",
    "cell",
    "direction_label",
    "frames_q_bin",
    "delta10_bin",
    "energy10_bin",
    "z10_bin",
    "loss5_bin",
    "closed10_delta",
    "closed10_energy",
    "closed10_score_abs",
    "net",
    "gross",
    "cost",
    "weight",
    "target_gamma",
    "target_exposure",
    "target_pnl",
    "entry_quality_class",
    "est_mean_net",
    "est_gt2_rate",
    "est_cvar05_net",
    "est_tail_share90",
    "same_day_regime",
]

BASE_PROXY_COLS = [
    "X_t",
    "X_fast_t",
    "M_t",
    "O_t",
    "P_t",
    "Theta_t",
    "log_U_t",
    "A_absorption_t",
    "E_exhaustion_t",
    "C_confirm_t",
    "D_divergence_t",
    "release_score_t",
    "lambda_prior_top_u",
    "lambda_prior_top_x",
    "log_opp_depth5_quote",
    "log_opp_depth25_quote",
    "log_opp_replenish",
    "log_opp_depletion",
    "spread_raw",
    "shock_raw",
    "microprice_raw_aligned",
    "obi5_raw_aligned",
    "frames_since_mid_change",
    "trade_window_count",
    "past_event_25_bps",
]


@dataclass(frozen=True)
class Paths:
    core_csv: Path
    entry_estimates_csv: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def panel_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_latent_state_panel_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_latent_state_daily_{self.run_tag}.csv"

    @property
    def quality_state_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_latent_state_quality_{self.run_tag}.csv"

    @property
    def score_tests_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_latent_state_score_tests_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_latent_state_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-latent-state-panel-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CCUSDT TFI latent-state diagnostic panel.")
    parser.add_argument("--core-csv", type=Path, default=Path("date") / CORE_FILE_NAME)
    parser.add_argument("--entry-estimates-csv", type=Path, default=Path("date") / ENTRY_EST_FILE_NAME)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > EPS else np.nan


def finite(values: Iterable[float] | pd.Series | np.ndarray) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return arr[np.isfinite(arr)]


def weighted_mean(values: pd.Series, weights: pd.Series | None = None) -> float:
    x = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64")
    if weights is None:
        ok = np.isfinite(x)
        return float(x[ok].mean()) if ok.sum() else np.nan
    w = pd.to_numeric(weights, errors="coerce").to_numpy(dtype="float64")
    ok = np.isfinite(x) & np.isfinite(w) & (w > 0.0)
    return safe_div(float(np.sum(x[ok] * w[ok])), float(np.sum(w[ok]))) if ok.sum() else np.nan


def cvar(values: pd.Series | np.ndarray, q: float = 0.05) -> float:
    arr = finite(values)
    if not len(arr):
        return np.nan
    cutoff = np.quantile(arr, q)
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["", "_No rows._", ""]
    cols = [col for col in columns if col in df.columns]
    view = df.loc[:, cols].head(max_rows).copy()
    lines = ["", "| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        cells: list[str] = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def read_csv_usecols(path: Path, columns: list[str]) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0).columns
    usecols = [col for col in columns if col in header]
    return pd.read_csv(path, usecols=usecols)


def load_inputs(paths: Paths) -> pd.DataFrame:
    entries = read_csv_usecols(paths.entry_estimates_csv, ENTRY_COLS)
    core = read_csv_usecols(paths.core_csv, CORE_COLS)
    for df in [entries, core]:
        df["date"] = df["date"].astype(str)
        if "entry_row" in df.columns:
            df["entry_row"] = pd.to_numeric(df["entry_row"], errors="coerce").astype("Int64")
    for col in entries.columns:
        if col not in {"fold", "date", "cell", "direction_label", "frames_q_bin", "delta10_bin", "energy10_bin", "z10_bin", "loss5_bin", "entry_quality_class", "same_day_regime"}:
            entries[col] = pd.to_numeric(entries[col], errors="coerce")
    for col in core.columns:
        if col != "date":
            core[col] = pd.to_numeric(core[col], errors="coerce")
    merged = entries.merge(core, on=["date", "entry_row"], how="left", suffixes=("", "_core"))
    merged["quality_side"] = np.select(
        [
            merged["entry_quality_class"].isin(HIGH_CLASSES),
            merged["entry_quality_class"].isin(REDUCE_CLASSES),
        ],
        ["high", "reduce"],
        default="neutral",
    )
    merged["prior_proxy_available"] = merged["X_t"].notna() & merged["Theta_t"].notna()
    return merged.sort_values(["date", "entry_ts", "entry_row"]).reset_index(drop=True)


def prior_percentiles(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[f"q_{col}"] = np.nan
    out["prior_n_for_state"] = 0
    dates = sorted(out["date"].dropna().unique().tolist())
    for date in dates:
        day_idx = out.index[out["date"].eq(date)]
        hist = out[out["date"] < date]
        out.loc[day_idx, "prior_n_for_state"] = len(hist)
        if hist.empty:
            continue
        for col in columns:
            if col not in out.columns:
                continue
            hist_values = finite(hist[col])
            if len(hist_values) == 0:
                continue
            hist_values.sort()
            vals = pd.to_numeric(out.loc[day_idx, col], errors="coerce").to_numpy(dtype="float64")
            ok = np.isfinite(vals)
            pct = np.full(len(vals), np.nan)
            pct[ok] = np.searchsorted(hist_values, vals[ok], side="right") / len(hist_values)
            out.loc[day_idx, f"q_{col}"] = pct
    return out


def q(df: pd.DataFrame, col: str) -> pd.Series:
    name = f"q_{col}"
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").fillna(0.5)
    return pd.Series(0.5, index=df.index)


def q_low(df: pd.DataFrame, col: str) -> pd.Series:
    return 1.0 - q(df, col)


def row_mean(parts: list[pd.Series]) -> pd.Series:
    mat = pd.concat(parts, axis=1)
    return mat.mean(axis=1, skipna=True)


def add_latent_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = prior_percentiles(df, BASE_PROXY_COLS)
    lambda_q = pd.concat([q(out, "lambda_prior_top_u"), q(out, "lambda_prior_top_x")], axis=1).max(axis=1)
    lambda_low = 1.0 - lambda_q
    pressure_q = row_mean([q(out, "X_t"), q(out, "X_fast_t"), q(out, "M_t")])
    depth_q = row_mean([q(out, "log_opp_depth5_quote"), q(out, "log_opp_depth25_quote")])
    low_depth = 1.0 - depth_q

    out["latent_pressure_q"] = pressure_q
    out["latent_lambda_q"] = lambda_q
    out["latent_depth_q"] = depth_q
    out["latent_low_depth_q"] = low_depth

    out["release_score"] = row_mean(
        [
            pressure_q,
            q_low(out, "Theta_t"),
            q_low(out, "A_absorption_t"),
            q_low(out, "E_exhaustion_t"),
            q(out, "release_score_t"),
            lambda_q,
            q(out, "log_opp_depletion"),
            q_low(out, "log_opp_replenish"),
        ]
    )
    out["absorption_score"] = row_mean(
        [
            pressure_q,
            q(out, "A_absorption_t"),
            q(out, "Theta_t"),
            depth_q,
            q(out, "log_opp_replenish"),
            q_low(out, "log_opp_depletion"),
            q_low(out, "release_score_t"),
            lambda_low,
        ]
    )
    out["exhaustion_score"] = row_mean(
        [
            pressure_q,
            q(out, "E_exhaustion_t"),
            q(out, "P_t"),
            q(out, "past_release_raw"),
            q(out, "spread_raw"),
            lambda_low,
            q_low(out, "release_score_t"),
        ]
    )
    out["vacuum_score"] = row_mean(
        [
            pressure_q,
            q(out, "spread_raw"),
            q(out, "shock_raw"),
            low_depth,
            q(out, "log_opp_depletion"),
            q_low(out, "log_opp_replenish"),
            q(out, "D_divergence_t"),
            lambda_q,
        ]
    )
    out["chop_score"] = row_mean(
        [
            q(out, "spread_raw"),
            q(out, "C_confirm_t"),
            q(out, "frames_since_mid_change"),
            q_low(out, "X_t"),
            q_low(out, "release_score_t"),
            q_low(out, "D_divergence_t"),
        ]
    )
    out["bad_state_score"] = row_mean([out["absorption_score"], out["exhaustion_score"], out["chop_score"]]) - row_mean(
        [out["release_score"], out["vacuum_score"]]
    )
    out["good_state_score"] = -out["bad_state_score"]
    state_cols = ["release_score", "absorption_score", "exhaustion_score", "vacuum_score", "chop_score"]
    labels = ["release", "absorption", "exhaustion", "vacuum", "chop"]
    out["dominant_latent_state"] = pd.DataFrame({label: out[col] for label, col in zip(labels, state_cols)}).idxmax(axis=1)
    out["release_minus_absorption"] = out["release_score"] - out["absorption_score"]
    out["release_vacuum_minus_abs_exh_chop"] = row_mean([out["release_score"], out["vacuum_score"]]) - row_mean(
        [out["absorption_score"], out["exhaustion_score"], out["chop_score"]]
    )
    return out


def subset_stats(frame: pd.DataFrame) -> dict[str, Any]:
    exp = pd.to_numeric(frame["target_exposure"], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(frame["target_pnl"], errors="coerce").fillna(0.0)
    net = pd.to_numeric(frame["net"], errors="coerce")
    return {
        "entries": int(len(frame)),
        "exposure": float(exp.sum()),
        "total_net": float(pnl.sum()),
        "weighted_mean_net": safe_div(float(pnl.sum()), float(exp.sum())),
        "mean_net": float(net.mean()) if net.notna().any() else np.nan,
        "median_net": float(net.quantile(0.5)) if net.notna().any() else np.nan,
        "gt2_rate": float((net > 2.0).mean()) if net.notna().any() else np.nan,
        "cvar05_net": cvar(net),
    }


def state_aggregates(prefix: str, frame: pd.DataFrame) -> dict[str, Any]:
    w = frame["target_exposure"]
    out: dict[str, Any] = {}
    for col in [
        "release_score",
        "absorption_score",
        "exhaustion_score",
        "vacuum_score",
        "chop_score",
        "bad_state_score",
        "release_minus_absorption",
        "release_vacuum_minus_abs_exh_chop",
    ]:
        out[f"{prefix}_{col}"] = weighted_mean(frame[col], w)
    for state in ["release", "absorption", "exhaustion", "vacuum", "chop"]:
        sub = frame[frame["dominant_latent_state"].eq(state)]
        out[f"{prefix}_{state}_exposure_share"] = safe_div(float(sub["target_exposure"].sum()), float(w.sum()))
    out[f"{prefix}_entries"] = int(len(frame))
    out[f"{prefix}_exposure"] = float(w.sum())
    out[f"{prefix}_total_net"] = float(frame["target_pnl"].sum())
    out[f"{prefix}_weighted_mean_net"] = safe_div(float(frame["target_pnl"].sum()), float(w.sum()))
    return out


def build_daily(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, day in panel.groupby("date", sort=True):
        high = day[day["quality_side"].eq("high")]
        reduce = day[day["quality_side"].eq("reduce")]
        neutral = day[day["quality_side"].eq("neutral")]
        row: dict[str, Any] = {"date": date}
        row.update({f"all_{k}": v for k, v in subset_stats(day).items()})
        row.update(state_aggregates("high", high))
        row.update(state_aggregates("reduce", reduce))
        row.update(state_aggregates("neutral", neutral))
        row["I_high_minus_reduce"] = row["high_total_net"] - row["reduce_total_net"]
        row["I_sign"] = int(np.sign(row["I_high_minus_reduce"])) if np.isfinite(row["I_high_minus_reduce"]) else 0
        row["state_gap_bad_high_minus_reduce"] = row["high_bad_state_score"] - row["reduce_bad_state_score"]
        row["state_gap_good_high_minus_reduce"] = row["high_release_vacuum_minus_abs_exh_chop"] - row[
            "reduce_release_vacuum_minus_abs_exh_chop"
        ]
        row["state_gap_absorption_high_minus_reduce"] = row["high_absorption_score"] - row["reduce_absorption_score"]
        row["state_gap_exhaustion_high_minus_reduce"] = row["high_exhaustion_score"] - row["reduce_exhaustion_score"]
        row["state_gap_release_high_minus_reduce"] = row["high_release_score"] - row["reduce_release_score"]
        row["state_gap_vacuum_high_minus_reduce"] = row["high_vacuum_score"] - row["reduce_vacuum_score"]
        row["state_gap_chop_high_minus_reduce"] = row["high_chop_score"] - row["reduce_chop_score"]
        row["high_bad_pressure_combo"] = row_mean(
            [
                pd.Series([row["high_absorption_score"]]),
                pd.Series([row["high_exhaustion_score"]]),
                pd.Series([row["high_chop_score"]]),
            ]
        ).iloc[0]
        row["high_good_pressure_combo"] = row_mean([pd.Series([row["high_release_score"]]), pd.Series([row["high_vacuum_score"]])]).iloc[
            0
        ]
        rows.append(row)
    daily = pd.DataFrame(rows)
    daily["pred_I_from_state_gap"] = (-np.sign(pd.to_numeric(daily["state_gap_bad_high_minus_reduce"], errors="coerce")).fillna(0)).astype(int)
    daily["pred_I_from_good_gap"] = np.sign(pd.to_numeric(daily["state_gap_good_high_minus_reduce"], errors="coerce")).fillna(0).astype(int)
    daily["pred_I_from_high_good_minus_bad"] = np.sign(
        pd.to_numeric(daily["high_good_pressure_combo"], errors="coerce")
        - pd.to_numeric(daily["high_bad_pressure_combo"], errors="coerce")
    ).fillna(0).astype(int)
    return daily


def build_quality_state(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in panel.groupby(["quality_side", "entry_quality_class", "dominant_latent_state"], dropna=False, sort=True):
        quality_side, quality, state = keys
        row = {
            "quality_side": quality_side,
            "entry_quality_class": quality,
            "dominant_latent_state": state,
        }
        row.update(subset_stats(group))
        for col in ["release_score", "absorption_score", "exhaustion_score", "vacuum_score", "chop_score", "bad_state_score"]:
            row[f"mean_{col}"] = weighted_mean(group[col], group["target_exposure"])
        rows.append(row)
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["quality_side", "weighted_mean_net"], ascending=[True, False]).reset_index(drop=True)
    return out


def corr(x: pd.Series, y: pd.Series, method: str = "pearson") -> float:
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    if len(frame) < 3:
        return np.nan
    if method == "spearman":
        frame = frame.rank(method="average")
    return float(frame["x"].corr(frame["y"]))


def prior_centered_score(daily: pd.DataFrame, score_col: str) -> pd.Series:
    work = daily.sort_values("date").copy()
    centered = pd.Series(np.nan, index=work.index, dtype="float64")
    values = pd.to_numeric(work[score_col], errors="coerce")
    for idx in work.index:
        date = work.at[idx, "date"]
        hist = values[work["date"] < date].dropna()
        if len(hist) >= 3 and np.isfinite(values.at[idx]):
            centered.at[idx] = float(values.at[idx] - hist.median())
    return centered.reindex(daily.index)


def score_test_row(daily: pd.DataFrame, score_col: str, positive_means_positive_I: bool = True) -> dict[str, Any]:
    work = daily[pd.to_numeric(daily[score_col], errors="coerce").notna()].copy()
    if work.empty:
        return {"score": score_col}
    centered = prior_centered_score(work, score_col)
    work = work.assign(score_centered=centered)
    work = work[pd.to_numeric(work["score_centered"], errors="coerce").notna()].copy()
    if work.empty:
        return {"score": score_col}
    sign = np.sign(pd.to_numeric(work["score_centered"], errors="coerce")).astype(int)
    pred = sign if positive_means_positive_I else -sign
    actual = np.sign(pd.to_numeric(work["I_high_minus_reduce"], errors="coerce")).astype(int)
    valid = actual.ne(0) & pred.ne(0)
    acc = float((pred[valid] == actual[valid]).mean()) if valid.any() else np.nan
    row: dict[str, Any] = {
        "score": score_col,
        "direction": "positive_means_positive_I" if positive_means_positive_I else "positive_means_negative_I",
        "centering": "expanding_prior_date_median",
        "rows": int(len(work)),
        "pearson_I": corr(work["score_centered"], work["I_high_minus_reduce"], "pearson"),
        "spearman_I": corr(work["score_centered"], work["I_high_minus_reduce"], "spearman"),
        "sign_accuracy": acc,
    }
    for date in ["2026-05-09", "2026-05-13"]:
        sub = work[work["date"].eq(date)]
        if len(sub):
            val = float(sub.iloc[0][score_col])
            centered_val = float(sub.iloc[0]["score_centered"])
            i_val = float(sub.iloc[0]["I_high_minus_reduce"])
            p = int(np.sign(centered_val))
            if not positive_means_positive_I:
                p = -p
            row[f"{date}_score"] = val
            row[f"{date}_centered_score"] = centered_val
            row[f"{date}_I"] = i_val
            row[f"{date}_pred_sign"] = p
            row[f"{date}_actual_sign"] = int(np.sign(i_val))
    row["distinguishes_0509_0513"] = (
        row.get("2026-05-09_pred_sign") == row.get("2026-05-09_actual_sign")
        and row.get("2026-05-13_pred_sign") == row.get("2026-05-13_actual_sign")
    )
    return row


def build_score_tests(daily: pd.DataFrame) -> pd.DataFrame:
    score_cols = [
        "state_gap_bad_high_minus_reduce",
        "state_gap_good_high_minus_reduce",
        "state_gap_absorption_high_minus_reduce",
        "state_gap_exhaustion_high_minus_reduce",
        "state_gap_release_high_minus_reduce",
        "state_gap_vacuum_high_minus_reduce",
        "state_gap_chop_high_minus_reduce",
        "high_release_vacuum_minus_abs_exh_chop",
        "high_bad_state_score",
        "high_good_pressure_combo",
        "high_bad_pressure_combo",
        "high_release_score",
        "high_absorption_score",
        "high_exhaustion_score",
        "high_vacuum_score",
        "high_chop_score",
        "reduce_release_score",
        "reduce_absorption_score",
        "reduce_exhaustion_score",
        "reduce_vacuum_score",
        "reduce_chop_score",
        "high_release_exposure_share",
        "high_absorption_exposure_share",
        "high_exhaustion_exposure_share",
        "high_vacuum_exposure_share",
        "high_chop_exposure_share",
        "reduce_release_exposure_share",
        "reduce_absorption_exposure_share",
        "reduce_exhaustion_exposure_share",
        "reduce_vacuum_exposure_share",
        "reduce_chop_exposure_share",
    ]
    rows = []
    for col in score_cols:
        if col not in daily.columns:
            continue
        rows.append(score_test_row(daily, col, True))
        rows.append(score_test_row(daily, col, False))
    out = pd.DataFrame(rows)
    if len(out):
        out["abs_spearman_I"] = pd.to_numeric(out["spearman_I"], errors="coerce").abs()
        out = out.sort_values(
            ["distinguishes_0509_0513", "sign_accuracy", "abs_spearman_I"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
    return out


def build_summary(panel: pd.DataFrame, daily: pd.DataFrame, tests: pd.DataFrame) -> dict[str, Any]:
    i_0509 = daily[daily["date"].eq("2026-05-09")].iloc[0].to_dict() if daily["date"].eq("2026-05-09").any() else {}
    i_0513 = daily[daily["date"].eq("2026-05-13")].iloc[0].to_dict() if daily["date"].eq("2026-05-13").any() else {}
    best = tests.head(1).iloc[0].to_dict() if len(tests) else {}
    distinguish = tests[tests["distinguishes_0509_0513"].eq(True)].copy() if len(tests) else pd.DataFrame()
    rank_distinguish = (
        distinguish.sort_values(["abs_spearman_I", "sign_accuracy"], ascending=[False, False]).head(1)
        if len(distinguish)
        else pd.DataFrame()
    )
    best_rank = rank_distinguish.iloc[0].to_dict() if len(rank_distinguish) else {}
    nontrivial = distinguish[pd.to_numeric(distinguish["abs_spearman_I"], errors="coerce") >= 0.30] if len(distinguish) else pd.DataFrame()
    return {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "entries": int(len(panel)),
        "date_min": str(panel["date"].min()) if len(panel) else None,
        "date_max": str(panel["date"].max()) if len(panel) else None,
        "I_2026_05_09": i_0509.get("I_high_minus_reduce"),
        "I_2026_05_13": i_0513.get("I_high_minus_reduce"),
        "state_gap_bad_2026_05_09": i_0509.get("state_gap_bad_high_minus_reduce"),
        "state_gap_bad_2026_05_13": i_0513.get("state_gap_bad_high_minus_reduce"),
        "best_sign_score": best.get("score"),
        "best_sign_score_direction": best.get("direction"),
        "best_sign_score_sign_accuracy": best.get("sign_accuracy"),
        "best_sign_score_spearman_I": best.get("spearman_I"),
        "best_rank_distinguishing_score": best_rank.get("score"),
        "best_rank_distinguishing_direction": best_rank.get("direction"),
        "best_rank_distinguishing_sign_accuracy": best_rank.get("sign_accuracy"),
        "best_rank_distinguishing_spearman_I": best_rank.get("spearman_I"),
        "scores_distinguishing_0509_0513": int(len(distinguish)),
        "nontrivial_rank_scores_distinguishing_0509_0513": int(len(nontrivial)),
        "distinguishing_scores": distinguish["score"].head(10).tolist() if len(distinguish) else [],
    }


def write_report(paths: Paths, panel: pd.DataFrame, daily: pd.DataFrame, quality_state: pd.DataFrame, tests: pd.DataFrame, summary: dict[str, Any]) -> None:
    contradiction = daily[daily["date"].isin(["2026-05-09", "2026-05-13"])].copy()
    dominant = (
        panel.groupby(["date", "quality_side", "dominant_latent_state"], sort=True)
        .agg(entries=("net", "size"), exposure=("target_exposure", "sum"), total_net=("target_pnl", "sum"))
        .reset_index()
    )
    dominant["weighted_mean_net"] = dominant["total_net"] / dominant["exposure"].replace(0.0, np.nan)
    dominant_focus = dominant[dominant["date"].isin(["2026-05-09", "2026-05-13"])].copy()
    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT TFI Latent-State Diagnostic Panel",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This pass builds prior-date percentile proxies for release, absorption, exhaustion, liquidity vacuum, and chop, then checks whether the proxy mix helps explain the daily inversion variable:",
            "",
            "$$",
            "I_d=G_{high,d}-G_{reduce,d}.",
            "$$",
            "",
            "Here `high = strong_positive + positive_right_tail_fragile`, while `reduce = weak_positive_mean + avoid_or_reduce + insufficient_history` from the strict as-of entry estimator.",
            "",
            "## Main Read",
            "",
            f"1. Entry-level latent panel rows: `{summary.get('entries')}`.",
            f"2. `2026-05-09` has `I_d={fmt(summary.get('I_2026_05_09'), 4)}`; `2026-05-13` has `I_d={fmt(summary.get('I_2026_05_13'), 4)}`.",
            f"3. Best sign screen: `{summary.get('best_sign_score')}` with sign accuracy `{fmt(summary.get('best_sign_score_sign_accuracy'), 4)}` and Spearman `{fmt(summary.get('best_sign_score_spearman_I'), 4)}`.",
            f"4. Best rank-aligned contradiction screen: `{summary.get('best_rank_distinguishing_score')}` with sign accuracy `{fmt(summary.get('best_rank_distinguishing_sign_accuracy'), 4)}` and Spearman `{fmt(summary.get('best_rank_distinguishing_spearman_I'), 4)}`.",
            f"5. Scores that correctly distinguish both contradiction days: `{summary.get('scores_distinguishing_0509_0513')}`; with `|Spearman| >= 0.30`: `{summary.get('nontrivial_rank_scores_distinguishing_0509_0513')}`.",
            "",
            "## Contradiction Days",
        ]
    )
    lines.extend(
        markdown_table(
            contradiction,
            [
                "date",
                "all_total_net",
                "high_total_net",
                "reduce_total_net",
                "I_high_minus_reduce",
                "high_release_score",
                "high_absorption_score",
                "high_exhaustion_score",
                "high_vacuum_score",
                "high_chop_score",
                "state_gap_bad_high_minus_reduce",
                "pred_I_from_state_gap",
                "pred_I_from_good_gap",
            ],
            max_rows=10,
        )
    )
    lines.extend(["## Score Tests"])
    lines.extend(
        markdown_table(
            tests,
            [
                "score",
                "direction",
                "centering",
                "rows",
                "spearman_I",
                "sign_accuracy",
                "2026-05-09_score",
                "2026-05-09_centered_score",
                "2026-05-09_pred_sign",
                "2026-05-09_actual_sign",
                "2026-05-13_score",
                "2026-05-13_centered_score",
                "2026-05-13_pred_sign",
                "2026-05-13_actual_sign",
                "distinguishes_0509_0513",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Dominant State On Contradiction Days"])
    lines.extend(
        markdown_table(
            dominant_focus.sort_values(["date", "quality_side", "total_net"], ascending=[True, True, False]),
            [
                "date",
                "quality_side",
                "dominant_latent_state",
                "entries",
                "exposure",
                "total_net",
                "weighted_mean_net",
            ],
            max_rows=40,
        )
    )
    lines.extend(["## Quality X State"])
    lines.extend(
        markdown_table(
            quality_state,
            [
                "quality_side",
                "entry_quality_class",
                "dominant_latent_state",
                "entries",
                "exposure",
                "total_net",
                "weighted_mean_net",
                "mean_release_score",
                "mean_absorption_score",
                "mean_exhaustion_score",
                "mean_vacuum_score",
                "mean_chop_score",
            ],
            max_rows=35,
        )
    )
    lines.extend(
        [
            "## Interpretation",
            "",
            "- A useful prior proxy does not need to maximize PnL in this pass; it first needs to give the correct sign for the two opposite cases: `2026-05-09` and `2026-05-13`.",
            "- If a proxy only explains `2026-05-13`, it is probably an entry-quality or weak-bucket sizing proxy.",
            "- If it also explains `2026-05-09`, it is closer to a true latent-regime proxy, because `2026-05-09` is the high/`11` inversion case.",
            "- These scores are percentile diagnostics over existing pre-trade proxies. They are not calibrated posteriors and should not be used directly as live sizing.",
            "",
            "## Outputs",
            "",
            f"- `{paths.panel_csv}`",
            f"- `{paths.daily_csv}`",
            f"- `{paths.quality_state_csv}`",
            f"- `{paths.score_tests_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_latent_state_panel.py",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        core_csv=resolve_repo_path(args.core_csv),
        entry_estimates_csv=resolve_repo_path(args.entry_estimates_csv),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    base = load_inputs(paths)
    panel = add_latent_scores(base)
    daily = build_daily(panel)
    quality_state = build_quality_state(panel)
    tests = build_score_tests(daily)
    summary = build_summary(panel, daily, tests)
    summary["run_tag"] = paths.run_tag
    summary["core_csv"] = str(paths.core_csv)
    summary["entry_estimates_csv"] = str(paths.entry_estimates_csv)

    panel.to_csv(paths.panel_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    quality_state.to_csv(paths.quality_state_csv, index=False)
    tests.to_csv(paths.score_tests_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, panel, daily, quality_state, tests, summary)

    print(json.dumps({"run_tag": paths.run_tag, "entries": int(len(panel)), "report": str(paths.report_md)}, indent=2))


if __name__ == "__main__":
    main()
