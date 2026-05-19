#!/usr/bin/env python
"""Plain factor decomposition for the CCUSDT TFI R5 + Q structure.

This intentionally avoids hand-built latent microstructure models. It uses
pre-trade, prequential factors already present in the TFI scored-entry table:
R5/R10, Delta/Energy/Z-score style strength, frames quantile Q, cell,
direction, hour/day, and entry-level net labels for attribution.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


RUN_TAG = "20260518_ccusdt_v1_tfi_factor_decomp_v1"
GUARDRAIL = "research_only_plain_factor_decomposition_no_execution_recommendation_no_alpha_claim"
ENTRY_FILE_NAME = "ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv"
EPS = 1e-12
MIN_TRAIN_DAYS = 5
US_PER_HOUR = 3_600_000_000

TARGET_POLICY = {
    "00_none": 0.0,
    "10_r5_only": 0.75,
    "01_frames_only": 0.25,
    "11_r5_frames": 4.0,
}

PARETO_POLICY = {
    "00_none": 0.0,
    "10_r5_only": 1.25,
    "01_frames_only": 0.75,
    "11_r5_frames": 5.0,
}


@dataclass(frozen=True)
class Paths:
    entries_csv: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def scored_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_entries_{self.run_tag}.csv"

    @property
    def factor_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_factor_bins_{self.run_tag}.csv"

    @property
    def interaction_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_interactions_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_daily_{self.run_tag}.csv"

    @property
    def attribution_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_worst_day_attribution_{self.run_tag}.csv"

    @property
    def metric_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_metric_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_factor_decomp_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-factor-decomposition-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plain R5+Q factor decomposition for CCUSDT TFI entries.")
    parser.add_argument("--entries-csv", type=Path, default=Path("date") / ENTRY_FILE_NAME)
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


def finite(values: Iterable[float] | np.ndarray | pd.Series) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return arr[np.isfinite(arr)]


def finite_mean(values: Iterable[float] | np.ndarray | pd.Series) -> float:
    arr = finite(values)
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray | pd.Series, q: float) -> float:
    arr = finite(values)
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def cvar(values: Iterable[float] | np.ndarray | pd.Series, q: float = 0.05) -> float:
    arr = finite(values)
    if not len(arr):
        return np.nan
    cutoff = np.quantile(arr, q)
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > EPS else np.nan


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


def load_entries(paths: Paths) -> pd.DataFrame:
    df = pd.read_csv(paths.entries_csv)
    df = df[(pd.to_numeric(df["weight"], errors="coerce") > 0) & pd.to_numeric(df["net"], errors="coerce").notna()].copy()
    df["date"] = df["date"].astype(str)
    numeric_cols = [
        "direction",
        "entry_ts",
        "entry_row",
        "entry_event_index",
        "entry_local_timestamp",
        "net",
        "gross",
        "cost",
        "weight",
        "frames_since_mid_change",
        "past_event_25_bps",
        "roll5_pos_abs_ratio",
        "roll5_mean_net",
        "roll10_pos_abs_ratio",
        "roll10_mean_net",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["direction"] = df["direction"].astype("int64")
    df["A_r5"] = df["gate_r_n5"].astype(bool)
    df["B_frames_q90"] = df["gate_frames_q90"].astype(bool)
    df["cell"] = np.select(
        [
            df["A_r5"] & df["B_frames_q90"],
            df["A_r5"] & ~df["B_frames_q90"],
            ~df["A_r5"] & df["B_frames_q90"],
        ],
        ["11_r5_frames", "10_r5_only", "01_frames_only"],
        default="00_none",
    )
    df["trade_universe"] = df["cell"].ne("00_none")
    df["hour"] = ((df["entry_local_timestamp"] // US_PER_HOUR).astype("int64") % 24).astype(int)
    df["direction_label"] = np.where(df["direction"] > 0, "long", "short")
    return df.sort_values(["date", "entry_ts", "entry_row"]).reset_index(drop=True)


def add_closed_roll_stats(df: pd.DataFrame, windows: list[int] = [5, 10, 20]) -> pd.DataFrame:
    out = df.copy()
    order_entry = out.sort_values(["entry_ts", "entry_row"]).index.to_numpy()
    order_label = out.sort_values(["label_available_ts", "entry_row"]).index.to_numpy()
    label_ts = out["label_available_ts"].to_numpy(dtype="float64")
    entry_ts = out["entry_ts"].to_numpy(dtype="float64")
    net = out["net"].to_numpy(dtype="float64")
    available: list[float] = []
    j = 0

    stats: dict[str, list[float]] = {}
    names = [
        "count",
        "pos_sum",
        "neg_abs_sum",
        "delta",
        "energy",
        "ratio",
        "rho",
        "mean",
        "min",
        "loss_abs_max",
        "score_abs",
    ]
    for window in windows:
        for name in names:
            stats[f"closed{window}_{name}"] = [np.nan] * len(out)

    for idx in order_entry:
        t = entry_ts[idx]
        while j < len(order_label) and label_ts[order_label[j]] <= t:
            available.append(float(net[order_label[j]]))
            j += 1
        for window in windows:
            vals = np.asarray(available[-window:], dtype="float64")
            vals = vals[np.isfinite(vals)]
            key = f"closed{window}"
            stats[f"{key}_count"][idx] = float(len(vals))
            if len(vals) == 0:
                continue
            pos = float(np.sum(vals[vals > 0.0]))
            neg = float(-np.sum(vals[vals < 0.0]))
            delta = pos - neg
            energy = pos + neg
            stats[f"{key}_pos_sum"][idx] = pos
            stats[f"{key}_neg_abs_sum"][idx] = neg
            stats[f"{key}_delta"][idx] = delta
            stats[f"{key}_energy"][idx] = energy
            stats[f"{key}_ratio"][idx] = safe_div(pos, neg)
            stats[f"{key}_rho"][idx] = safe_div(delta, energy)
            stats[f"{key}_mean"][idx] = float(np.mean(vals))
            stats[f"{key}_min"][idx] = float(np.min(vals))
            stats[f"{key}_loss_abs_max"][idx] = float(np.max(np.maximum(-vals, 0.0)))
            stats[f"{key}_score_abs"][idx] = safe_div(delta, math.sqrt(energy + EPS))

    for col, values in stats.items():
        out[col] = values
    return out


def expanding_quantile_bins(
    df: pd.DataFrame,
    value_col: str,
    out_col: str,
    quantiles: list[float],
    labels: list[str],
    train_mask_col: str = "trade_universe",
) -> pd.DataFrame:
    out = df.copy()
    out[out_col] = "missing"
    dates = sorted(out["date"].dropna().astype(str).unique())
    for i, date in enumerate(dates):
        current = out["date"].eq(date)
        train = out[out["date"].isin(dates[:i]) & out[train_mask_col].astype(bool)]
        vals = pd.to_numeric(train[value_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        current_vals = pd.to_numeric(out.loc[current, value_col], errors="coerce")
        if i < MIN_TRAIN_DAYS or len(vals) < 50:
            vals = pd.to_numeric(out.loc[out[train_mask_col].astype(bool), value_col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if len(vals) < 10:
            continue
        cuts = [-np.inf, *[float(vals.quantile(q)) for q in quantiles], np.inf]
        out.loc[current, out_col] = pd.cut(current_vals, bins=cuts, labels=labels, include_lowest=True).astype(str).fillna("missing")
    return out


def add_factor_bins(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    q_labels = ["q0_50", "q50_70", "q70_85", "q85_90", "q90_95", "q95_99", "q99_100"]
    out = expanding_quantile_bins(
        out,
        "frames_since_mid_change",
        "frames_q_bin",
        [0.50, 0.70, 0.85, 0.90, 0.95, 0.99],
        q_labels,
    )
    strength_labels = ["s0_20", "s20_40", "s40_60", "s60_80", "s80_100"]
    for src, dst in [
        ("closed5_ratio", "r5_bin"),
        ("closed5_delta", "delta5_bin"),
        ("closed5_energy", "energy5_bin"),
        ("closed5_score_abs", "z5_bin"),
        ("closed10_ratio", "r10_bin"),
        ("closed10_delta", "delta10_bin"),
        ("closed10_energy", "energy10_bin"),
        ("closed10_score_abs", "z10_bin"),
        ("closed5_loss_abs_max", "loss5_bin"),
    ]:
        out = expanding_quantile_bins(out, src, dst, [0.20, 0.40, 0.60, 0.80], strength_labels)
    return out


def policy_exposure(frame: pd.DataFrame, policy: dict[str, float]) -> np.ndarray:
    gamma = frame["cell"].map(policy).fillna(0.0).to_numpy(dtype="float64")
    return frame["weight"].to_numpy(dtype="float64") * gamma


def subset_stats(frame: pd.DataFrame, policy_name: str = "target") -> dict[str, Any]:
    if policy_name == "target":
        exposure = policy_exposure(frame, TARGET_POLICY)
    elif policy_name == "pareto":
        exposure = policy_exposure(frame, PARETO_POLICY)
    else:
        exposure = frame["weight"].to_numpy(dtype="float64")
    net = frame["net"].to_numpy(dtype="float64")
    pnl = exposure * net
    active = np.isfinite(pnl) & np.isfinite(exposure) & (exposure > 0)
    exposure_active = exposure[active]
    net_active = net[active]
    pnl_active = pnl[active]
    return {
        "entries": int(active.sum()),
        "exposure": float(np.sum(exposure_active)),
        "total_net": float(np.sum(pnl_active)),
        "mean_net": safe_div(float(np.sum(pnl_active)), float(np.sum(exposure_active))),
        "median_net": finite_quantile(net_active, 0.50),
        "gt2_rate": float(np.mean(net_active > 2.0)) if len(net_active) else np.nan,
        "q90_net": finite_quantile(net_active, 0.90),
        "cvar05_net": cvar(net_active, 0.05),
        "gross_mean": finite_mean(frame.loc[active, "gross"]) if "gross" in frame.columns else np.nan,
        "cost_mean": finite_mean(frame.loc[active, "cost"]) if "cost" in frame.columns else np.nan,
    }


def grouped_stats(df: pd.DataFrame, group_cols: list[str], policy_name: str = "target", min_entries: int = 0) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(group_cols, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_cols, keys))
        row.update(subset_stats(group, policy_name=policy_name))
        if row["entries"] >= min_entries:
            rows.append(row)
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["mean_net", "entries"], ascending=[False, False]).reset_index(drop=True)
    return out


def metric_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "frames_since_mid_change",
        "closed5_ratio",
        "closed5_delta",
        "closed5_energy",
        "closed5_score_abs",
        "closed5_loss_abs_max",
        "closed10_ratio",
        "closed10_delta",
        "closed10_energy",
        "closed10_score_abs",
        "closed10_loss_abs_max",
        "past_event_25_bps",
    ]
    rows: list[dict[str, Any]] = []
    work = df[df["trade_universe"]].copy()
    for metric in metrics:
        if metric not in work.columns:
            continue
        x = pd.to_numeric(work[metric], errors="coerce").to_numpy(dtype="float64")
        y = work["net"].to_numpy(dtype="float64")
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 100:
            continue
        try:
            ic = float(spearmanr(x[ok], y[ok]).statistic)
        except Exception:
            ic = np.nan
        top_cut = np.quantile(x[ok], 0.80)
        bottom_cut = np.quantile(x[ok], 0.20)
        top = work.loc[ok].loc[x[ok] >= top_cut]
        bottom = work.loc[ok].loc[x[ok] <= bottom_cut]
        top_stats = subset_stats(top, policy_name="target")
        bottom_stats = subset_stats(bottom, policy_name="target")
        rows.append(
            {
                "metric": metric,
                "rows": int(ok.sum()),
                "spearman_net": ic,
                "top_entries": top_stats["entries"],
                "top_mean_net": top_stats["mean_net"],
                "bottom_mean_net": bottom_stats["mean_net"],
                "top_bottom_mean_net": top_stats["mean_net"] - bottom_stats["mean_net"],
                "top_cvar05_net": top_stats["cvar05_net"],
                "bottom_cvar05_net": bottom_stats["cvar05_net"],
            }
        )
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("top_bottom_mean_net", ascending=False).reset_index(drop=True)
    return out


def build_factor_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_tables: list[pd.DataFrame] = []
    for name, cols in [
        ("cell", ["cell"]),
        ("direction", ["direction_label"]),
        ("frames_q", ["frames_q_bin"]),
        ("r5", ["r5_bin"]),
        ("delta5", ["delta5_bin"]),
        ("energy5", ["energy5_bin"]),
        ("z5", ["z5_bin"]),
        ("r10", ["r10_bin"]),
        ("delta10", ["delta10_bin"]),
        ("energy10", ["energy10_bin"]),
        ("z10", ["z10_bin"]),
        ("loss5", ["loss5_bin"]),
        ("hour", ["hour"]),
    ]:
        table = grouped_stats(df, cols, policy_name="target", min_entries=1)
        table.insert(0, "factor_view", name)
        factor_tables.append(table)
    factors = pd.concat(factor_tables, ignore_index=True)

    interactions: list[pd.DataFrame] = []
    for name, cols in [
        ("cell_x_direction", ["cell", "direction_label"]),
        ("cell_x_frames_q", ["cell", "frames_q_bin"]),
        ("cell_x_delta10", ["cell", "delta10_bin"]),
        ("cell_x_z10", ["cell", "z10_bin"]),
        ("cell_x_energy10", ["cell", "energy10_bin"]),
        ("cell_x_loss5", ["cell", "loss5_bin"]),
        ("frames_q_x_delta10", ["frames_q_bin", "delta10_bin"]),
        ("direction_x_cell_x_frames_q", ["direction_label", "cell", "frames_q_bin"]),
    ]:
        table = grouped_stats(df, cols, policy_name="target", min_entries=10)
        table.insert(0, "factor_view", name)
        interactions.append(table)
    interaction = pd.concat(interactions, ignore_index=True)
    return factors, interaction


def daily_table(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for date, group in df.groupby("date", sort=True):
        row = {"date": date}
        row.update(subset_stats(group, policy_name="target"))
        for cell, cell_group in group.groupby("cell", sort=True):
            stats = subset_stats(cell_group, policy_name="target")
            row[f"{cell}_entries"] = stats["entries"]
            row[f"{cell}_exposure"] = stats["exposure"]
            row[f"{cell}_total_net"] = stats["total_net"]
            row[f"{cell}_mean_net"] = stats["mean_net"]
        for direction, dir_group in group.groupby("direction_label", sort=True):
            stats = subset_stats(dir_group, policy_name="target")
            row[f"{direction}_entries"] = stats["entries"]
            row[f"{direction}_total_net"] = stats["total_net"]
            row[f"{direction}_mean_net"] = stats["mean_net"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def attribution_table(df: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    test_dates = sorted(daily["date"].tolist())[MIN_TRAIN_DAYS:]
    baseline_dates = sorted(daily["date"].tolist())[:MIN_TRAIN_DAYS]
    # Attribute the target policy because it is the last pre-Pareto baseline
    # where the worst day was visible.
    active = df.copy()
    active["exposure"] = policy_exposure(active, TARGET_POLICY)
    active["pnl"] = active["exposure"] * active["net"]
    active = active[active["exposure"] > 0].copy()
    group_cols = ["cell", "direction_label", "frames_q_bin", "delta10_bin"]
    base = active[active["date"].isin(baseline_dates)].copy()
    test = active[active["date"].isin(test_dates)].copy()
    global_mean = safe_div(float(base["pnl"].sum()), float(base["exposure"].sum()))
    base_group = base.groupby(group_cols, dropna=False).agg(
        base_entries=("pnl", "size"),
        base_exposure=("exposure", "sum"),
        base_total_net=("pnl", "sum"),
    ).reset_index()
    base_group["base_mean_net"] = base_group["base_total_net"] / base_group["base_exposure"].replace(0.0, np.nan)
    base_group["base_exposure_share"] = base_group["base_exposure"] / max(base_group["base_exposure"].sum(), EPS)

    rows: list[dict[str, Any]] = []
    for date in test_dates:
        day = test[test["date"].eq(date)].copy()
        day_group = day.groupby(group_cols, dropna=False).agg(
            day_entries=("pnl", "size"),
            day_exposure=("exposure", "sum"),
            day_total_net=("pnl", "sum"),
        ).reset_index()
        day_group["day_mean_net"] = day_group["day_total_net"] / day_group["day_exposure"].replace(0.0, np.nan)
        merged = day_group.merge(base_group, on=group_cols, how="outer")
        for col in ["day_entries", "day_exposure", "day_total_net", "base_entries", "base_exposure", "base_total_net", "base_exposure_share"]:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
        merged["base_mean_net"] = pd.to_numeric(merged["base_mean_net"], errors="coerce").fillna(global_mean)
        merged["day_mean_net"] = pd.to_numeric(merged["day_mean_net"], errors="coerce").fillna(0.0)
        day_exposure = float(merged["day_exposure"].sum())
        day_total = float(merged["day_total_net"].sum())
        expected_by_base_means = float((merged["day_exposure"] * merged["base_mean_net"]).sum())
        composition_effect = expected_by_base_means - day_exposure * global_mean
        payoff_effect = day_total - expected_by_base_means
        rows.append(
            {
                "date": date,
                "day_entries": int(day["pnl"].size),
                "day_exposure": day_exposure,
                "day_total_net": day_total,
                "day_mean_net": safe_div(day_total, day_exposure),
                "baseline_global_mean": global_mean,
                "expected_total_at_global_mean": day_exposure * global_mean,
                "expected_total_by_base_bucket_means": expected_by_base_means,
                "composition_effect": composition_effect,
                "payoff_decay_effect": payoff_effect,
                "worst_bucket": "",
                "worst_bucket_payoff_effect": np.nan,
            }
        )
        merged["bucket_payoff_effect"] = merged["day_exposure"] * (merged["day_mean_net"] - merged["base_mean_net"])
        if len(merged):
            worst = merged.sort_values("bucket_payoff_effect").iloc[0]
            label = "|".join(str(worst[col]) for col in group_cols)
            rows[-1]["worst_bucket"] = label
            rows[-1]["worst_bucket_payoff_effect"] = float(worst["bucket_payoff_effect"])
    out = pd.DataFrame(rows).sort_values("day_total_net").reset_index(drop=True)
    return out


def write_report(
    paths: Paths,
    df: pd.DataFrame,
    factors: pd.DataFrame,
    interactions: pd.DataFrame,
    daily: pd.DataFrame,
    attribution: pd.DataFrame,
    metrics: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT TFI R5+Q Factor Decomposition",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This report goes back to plain factors: R5/R10 strength, frames quantile Q, mutually exclusive cells, direction, and day-level attribution. It deliberately avoids hand-built latent variables.",
            "",
            "## Factor Definitions",
            "",
            "$$",
            "R_k=\\frac{P_k}{N_k+\\epsilon},\\quad \\Delta_k=P_k-N_k,\\quad E_k=P_k+N_k,\\quad Z_k=\\frac{\\Delta_k}{\\sqrt{E_k+\\epsilon}}.",
            "$$",
            "",
            "The frame variable is treated as an expanding-prior quantile bucket:",
            "",
            "$$",
            "Q_t=F_{train}(frames\\_since\\_mid\\_change_t).",
            "$$",
            "",
            "The target-policy exposure used for decomposition is:",
            "",
            "$$",
            "(\\gamma_{00},\\gamma_{10},\\gamma_{01},\\gamma_{11})=(0,0.75,0.25,4).",
            "$$",
            "",
            "## Main Read",
            "",
            f"1. Worst target-policy day is `{summary.get('worst_day')}` with total `{fmt(summary.get('worst_day_total_net'), 4)}` and mean `{fmt(summary.get('worst_day_mean_net'), 4)}` bps.",
            f"2. Worst-day attribution: composition effect `{fmt(summary.get('worst_day_composition_effect'), 4)}`, within-bucket payoff decay `{fmt(summary.get('worst_day_payoff_decay_effect'), 4)}`. Negative payoff decay means the same buckets behaved worse than their prior means.",
            f"3. Best single metric by top-bottom target-policy mean is `{summary.get('best_metric')}` with spread `{fmt(summary.get('best_metric_top_bottom'), 4)}` bps.",
            f"4. Best interaction bucket is `{summary.get('best_interaction_label')}` with entries `{summary.get('best_interaction_entries')}` and mean `{fmt(summary.get('best_interaction_mean'), 4)}` bps.",
            "",
            "## Metric Scorecard",
        ]
    )
    lines.extend(
        markdown_table(
            metrics,
            [
                "metric",
                "rows",
                "spearman_net",
                "top_entries",
                "top_mean_net",
                "bottom_mean_net",
                "top_bottom_mean_net",
                "top_cvar05_net",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Single-Factor Bins"])
    lines.extend(
        markdown_table(
            factors,
            [
                "factor_view",
                "cell",
                "direction_label",
                "frames_q_bin",
                "delta10_bin",
                "z10_bin",
                "loss5_bin",
                "hour",
                "entries",
                "exposure",
                "mean_net",
                "median_net",
                "gt2_rate",
                "q90_net",
                "cvar05_net",
                "total_net",
            ],
            max_rows=35,
        )
    )
    lines.extend(["## Interaction Bins"])
    lines.extend(
        markdown_table(
            interactions,
            [
                "factor_view",
                "cell",
                "direction_label",
                "frames_q_bin",
                "delta10_bin",
                "z10_bin",
                "energy10_bin",
                "loss5_bin",
                "entries",
                "exposure",
                "mean_net",
                "median_net",
                "gt2_rate",
                "q90_net",
                "cvar05_net",
                "total_net",
            ],
            max_rows=45,
        )
    )
    lines.extend(["## Daily Target-Policy Table"])
    lines.extend(
        markdown_table(
            daily,
            [
                "date",
                "entries",
                "exposure",
                "total_net",
                "mean_net",
                "10_r5_only_total_net",
                "01_frames_only_total_net",
                "11_r5_frames_total_net",
                "short_total_net",
                "long_total_net",
            ],
            max_rows=25,
        )
    )
    lines.extend(["## Worst-Day Attribution"])
    lines.extend(
        markdown_table(
            attribution,
            [
                "date",
                "day_entries",
                "day_exposure",
                "day_total_net",
                "day_mean_net",
                "expected_total_at_global_mean",
                "expected_total_by_base_bucket_means",
                "composition_effect",
                "payoff_decay_effect",
                "worst_bucket",
                "worst_bucket_payoff_effect",
            ],
            max_rows=20,
        )
    )
    lines.extend(
        [
            "## Interpretation",
            "",
            "- If composition dominates, the bad day came from trading too much of normally weak buckets.",
            "- If payoff decay dominates, the same buckets became worse on that day; this is a regime problem, not solved by a static clip alone.",
            "- R5 is kept as a shape ratio, but the decomposition emphasizes Delta/Energy/Z and Q buckets because those are closer to absolute evidence and stale-state intensity.",
            "",
            "## Outputs",
            "",
            f"- `{paths.scored_csv}`",
            f"- `{paths.factor_csv}`",
            f"- `{paths.interaction_csv}`",
            f"- `{paths.daily_csv}`",
            f"- `{paths.attribution_csv}`",
            f"- `{paths.metric_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_factor_decomposition.py",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        entries_csv=resolve_repo_path(args.entries_csv),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    entries = load_entries(paths)
    entries = add_closed_roll_stats(entries)
    entries = add_factor_bins(entries)
    factors, interactions = build_factor_tables(entries)
    daily = daily_table(entries)
    attribution = attribution_table(entries, daily)
    metrics = metric_scorecard(entries)

    worst_daily = daily.sort_values("total_net").iloc[0].to_dict() if len(daily) else {}
    worst_attr = attribution[attribution["date"].eq(worst_daily.get("date"))].iloc[0].to_dict() if len(attribution) and worst_daily else {}
    best_metric = metrics.iloc[0].to_dict() if len(metrics) else {}
    best_interaction = interactions.sort_values(["mean_net", "entries"], ascending=[False, False]).iloc[0].to_dict() if len(interactions) else {}
    best_interaction_label = "|".join(
        str(best_interaction.get(col))
        for col in ["factor_view", "cell", "direction_label", "frames_q_bin", "delta10_bin", "z10_bin", "energy10_bin", "loss5_bin"]
        if col in best_interaction and pd.notna(best_interaction.get(col))
    )
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "entry_rows": int(len(entries)),
        "date_min": str(entries["date"].min()),
        "date_max": str(entries["date"].max()),
        "worst_day": worst_daily.get("date"),
        "worst_day_total_net": worst_daily.get("total_net"),
        "worst_day_mean_net": worst_daily.get("mean_net"),
        "worst_day_composition_effect": worst_attr.get("composition_effect"),
        "worst_day_payoff_decay_effect": worst_attr.get("payoff_decay_effect"),
        "best_metric": best_metric.get("metric"),
        "best_metric_top_bottom": best_metric.get("top_bottom_mean_net"),
        "best_metric_spearman": best_metric.get("spearman_net"),
        "best_interaction_label": best_interaction_label,
        "best_interaction_entries": best_interaction.get("entries"),
        "best_interaction_mean": best_interaction.get("mean_net"),
    }

    entries.to_csv(paths.scored_csv, index=False)
    factors.to_csv(paths.factor_csv, index=False)
    interactions.to_csv(paths.interaction_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    attribution.to_csv(paths.attribution_csv, index=False)
    metrics.to_csv(paths.metric_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, entries, factors, interactions, daily, attribution, metrics, summary)

    print(json.dumps({"run_tag": paths.run_tag, "report": str(paths.report_md), "entries": len(entries)}, indent=2))


if __name__ == "__main__":
    main()
