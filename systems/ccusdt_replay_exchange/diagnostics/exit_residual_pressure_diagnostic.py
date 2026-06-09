#!/usr/bin/env python
"""Residual pressure diagnostic for ExitControllerV1 wait outcomes.

This is an offline diagnostic, not a trading rule. It tests whether successful
wait exits are associated with exchange-visible residual order-flow pressure at
the original exit decision.

The runtime-safe side uses only pre-exit quote/trade state. The wait outcome
W_t(tau) remains an evaluation label.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from maker_exit_opportunity import DayMarket, date_range, optional_float, repo_path  # type: ignore


US_PER_SEC = 1_000_000
DEFAULT_PANEL = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "conditional_wait_exit_q70_idle01_g1_20260505_18_20260522/"
    "conditional_wait_exit_panel.parquet"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "exit_residual_pressure_q70_idle01_g1_20260505_18_20260522"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-exit-residual-pressure-diagnostic-20260524.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--from-date", default="2026-05-05")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--oos-from-date", default="2026-05-16")
    parser.add_argument("--min-bin-count", type=int, default=30)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    return "" if value is None else f"{value:.{digits}f}"


def signed_flow_features(market: DayMarket, *, entry_side: str, exit_ts_us: int, window_us: int) -> dict[str, float]:
    trades = market.trade_slice(exit_ts_us - window_us, exit_ts_us)
    same_side = "buy" if entry_side == "buy" else "sell"
    seconds = window_us / US_PER_SEC
    if trades.empty:
        same_qty = opp_qty = same_notional = opp_notional = 0.0
        count = 0
    else:
        same = trades[trades["side"] == same_side]
        opp = trades[trades["side"] != same_side]
        same_qty = float(same["qty"].sum())
        opp_qty = float(opp["qty"].sum())
        same_notional = float(same["notional_quote"].sum())
        opp_notional = float(opp["notional_quote"].sum())
        count = int(len(trades))
    qty_total = same_qty + opp_qty
    notional_total = same_notional + opp_notional
    signed_qty = same_qty - opp_qty
    signed_notional = same_notional - opp_notional
    suffix = f"{int(round(seconds * 1000))}ms" if seconds < 1.0 else f"{int(round(seconds))}s"
    return {
        f"pre_trade_count_{suffix}": float(count),
        f"pre_same_qty_{suffix}": same_qty,
        f"pre_opposite_qty_{suffix}": opp_qty,
        f"pre_signed_qty_{suffix}": signed_qty,
        f"pre_signed_notional_{suffix}": signed_notional,
        f"pre_total_notional_{suffix}": notional_total,
        f"pre_flow_imbalance_{suffix}": signed_qty / qty_total if qty_total > 0.0 else 0.0,
        f"pre_notional_imbalance_{suffix}": signed_notional / notional_total if notional_total > 0.0 else 0.0,
        f"pre_trade_intensity_{suffix}": float(count) / max(seconds, 1e-12),
    }


def safe_ratio(numer: float, denom: float) -> float:
    if abs(denom) <= 1e-12:
        return 0.0
    return float(numer / denom)


def capped_positive_ratio(numer: float, denom: float, *, cap: float = 10.0) -> float:
    """Return a stable non-negative ratio without letting near-zero denominators dominate."""
    if denom <= 0.0:
        return 0.0
    value = max(float(numer), 0.0) / float(denom)
    return float(min(value, cap))


def build_exit_pressure(panel: pd.DataFrame, repo_root: Path, symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
    base_cols = [
        "date",
        "exit_profile_source",
        "shadow_position_id",
        "entry_ts_us",
        "exit_ts_us",
        "entry_side",
        "cell",
        "actual_exposure",
        "exit_spread_bps",
        "path_h_bps",
        "path_d_bps",
        "recent_mid_alpha_5s_bps",
        "signed_top_depth_imbalance",
        "decision_frames_since_mid_change",
    ]
    base = panel[base_cols].drop_duplicates(
        ["date", "exit_profile_source", "shadow_position_id", "entry_ts_us", "exit_ts_us"]
    )
    days = set(date_range(from_date, to_date))
    base = base[base["date"].astype(str).isin(days)].copy()
    market_by_day = {day: DayMarket.load(repo_root, symbol, day) for day in sorted(days)}
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(base.itertuples(index=False), start=1):
        day = str(row.date)
        market = market_by_day[day]
        entry_side = str(row.entry_side)
        exit_ts_us = int(row.exit_ts_us)
        features: dict[str, Any] = {
            "date": day,
            "exit_profile_source": str(row.exit_profile_source),
            "shadow_position_id": int(row.shadow_position_id),
            "entry_ts_us": int(row.entry_ts_us),
            "exit_ts_us": exit_ts_us,
            "entry_side": entry_side,
            "cell": str(row.cell),
            "actual_exposure": float(row.actual_exposure),
            "exit_spread_bps": float(row.exit_spread_bps),
            "path_h_bps": float(row.path_h_bps),
            "path_d_bps": float(row.path_d_bps),
            "recent_mid_alpha_5s_bps": float(row.recent_mid_alpha_5s_bps),
            "signed_top_depth_imbalance": float(row.signed_top_depth_imbalance),
            "decision_frames_since_mid_change": optional_float(row.decision_frames_since_mid_change),
        }
        for window_us in [1 * US_PER_SEC, 2 * US_PER_SEC, 5 * US_PER_SEC]:
            features.update(signed_flow_features(market, entry_side=entry_side, exit_ts_us=exit_ts_us, window_us=window_us))
        x1 = float(features["pre_signed_notional_1s"])
        x2 = float(features["pre_signed_notional_2s"])
        x5 = float(features["pre_signed_notional_5s"])
        imb1 = float(features["pre_notional_imbalance_1s"])
        imb2 = float(features["pre_notional_imbalance_2s"])
        imb5 = float(features["pre_notional_imbalance_5s"])
        recent_mid_alpha = float(features["recent_mid_alpha_5s_bps"])
        depth = float(features["signed_top_depth_imbalance"])
        path_d = max(float(features["path_d_bps"]), 0.0)
        path_h = max(float(features["path_h_bps"]), 0.0)
        impact_exhaustion = capped_positive_ratio(path_d, abs(recent_mid_alpha) + 1.0)
        path_exhaustion = capped_positive_ratio(path_d, path_h + 1.0)
        features.update(
            {
                "pressure_persistence_1s_vs_5s": safe_ratio(x1, abs(x5)),
                "pressure_persistence_2s_vs_5s": safe_ratio(x2, abs(x5)),
                "pressure_reversal_1s_vs_5s": 1.0 if x1 * x5 < 0.0 else 0.0,
                "impact_per_1k_notional_5s": safe_ratio(recent_mid_alpha, abs(x5) / 1000.0),
                "impact_exhaustion_ratio": impact_exhaustion,
                "capture_pressure_gap_bps": path_d - max(recent_mid_alpha, 0.0),
                "residual_pressure_score": 0.45 * imb1 + 0.30 * imb2 + 0.15 * imb5 + 0.10 * depth,
                "pressure_exhaustion_score": path_exhaustion - 0.5 * imb1 - 0.25 * imb5,
            }
        )
        rows.append(features)
        if idx % 1000 == 0:
            print(f"residual pressure features processed exits={idx}", flush=True)
    return pd.DataFrame(rows)


def attach_pressure(panel: pd.DataFrame, pressure: pd.DataFrame) -> pd.DataFrame:
    keys = ["date", "exit_profile_source", "shadow_position_id", "entry_ts_us", "exit_ts_us"]
    pressure_cols = [col for col in pressure.columns if col not in {"actual_exposure", "cell"} or col in keys]
    return panel.merge(pressure[pressure_cols], on=keys, how="left", suffixes=("", "_pressure"))


def weighted_sum(df: pd.DataFrame, column: str) -> float:
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return float((weights * values).sum())


def weighted_mean(df: pd.DataFrame, column: str) -> float:
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce")
    ok = values.notna()
    if not ok.any():
        return 0.0
    denom = float(weights[ok].sum())
    if denom <= 0.0:
        return float(values[ok].mean())
    return float((weights[ok] * values[ok]).sum() / denom)


def cvar_left(series: pd.Series, frac: float = 0.10) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().sort_values()
    if values.empty:
        return 0.0
    count = max(1, int(math.ceil(len(values) * frac)))
    return float(values.iloc[:count].mean())


def positive_day_frac(df: pd.DataFrame) -> float:
    values = [float(group["weighted_wait_value_bps"].sum()) for _, group in df.groupby("date", sort=True)]
    return float(sum(1 for value in values if value > 0.0) / len(values)) if values else 0.0


def min_day_sum(df: pd.DataFrame) -> float:
    values = [float(group["weighted_wait_value_bps"].sum()) for _, group in df.groupby("date", sort=True)]
    return min(values) if values else 0.0


def summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    return {
        "n": int(len(group)),
        "exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "weighted_mean_wait_value_bps": weighted_mean(group, "wait_value_bps"),
        "weighted_sum_wait_value_bps": weighted_sum(group, "wait_value_bps"),
        "wait_positive_rate": float((pd.to_numeric(group["wait_value_bps"], errors="coerce").fillna(0.0) > 0.0).mean()),
        "weighted_mean_delay_loss_bps": weighted_mean(group, "delay_loss_bps"),
        "worst_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").min()),
        "cvar10_wait_value_bps": cvar_left(group["wait_value_bps"], 0.10),
        "positive_day_frac": positive_day_frac(group),
        "min_day_wait_sum_bps": min_day_sum(group),
        "mean_residual_pressure_score": float(pd.to_numeric(group["residual_pressure_score"], errors="coerce").mean()),
        "mean_pressure_exhaustion_score": float(pd.to_numeric(group["pressure_exhaustion_score"], errors="coerce").mean()),
    }


def bin_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 5 or numeric.nunique(dropna=True) < 2:
        return pd.Series(["all"] * len(series), index=series.index)
    try:
        return pd.qcut(numeric.rank(method="first"), q=5, labels=["q1", "q2", "q3", "q4", "q5"])
    except ValueError:
        return pd.Series(["all"] * len(series), index=series.index)


def factor_summary(panel: pd.DataFrame, min_count: int) -> pd.DataFrame:
    factors = [
        "pre_notional_imbalance_1s",
        "pre_notional_imbalance_2s",
        "pre_notional_imbalance_5s",
        "pressure_persistence_1s_vs_5s",
        "pressure_persistence_2s_vs_5s",
        "pressure_reversal_1s_vs_5s",
        "impact_per_1k_notional_5s",
        "impact_exhaustion_ratio",
        "capture_pressure_gap_bps",
        "residual_pressure_score",
        "pressure_exhaustion_score",
        "recent_mid_alpha_5s_bps",
        "path_d_bps",
        "exit_spread_bps",
    ]
    rows: list[dict[str, Any]] = []
    for (profile, ttl), ttl_group in panel.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        for factor in factors:
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
                    "factor_bin": str(bin_name),
                    "factor_min": float(numeric.min()) if numeric.notna().any() else None,
                    "factor_max": float(numeric.max()) if numeric.notna().any() else None,
                }
                row.update(summarize_group(group))
                rows.append(row)
    return pd.DataFrame(rows)


def selected_policy_overlap(panel: pd.DataFrame) -> pd.DataFrame:
    """A descriptive readout of the current conservative wait policy's pressure."""
    mask = (
        ((panel["exit_profile_source"] == "fixed30_livecoherent") & (panel["ttl_sec"] == 5.0) & (panel["path_d_bps"] <= panel.groupby(["exit_profile_source", "date"])["path_d_bps"].transform(lambda s: s.quantile(0.30))) & (panel["exit_spread_bps"] >= panel.groupby(["exit_profile_source", "date"])["exit_spread_bps"].transform(lambda s: s.quantile(0.70))))
        | ((panel["exit_profile_source"] == "fixed45_livecoherent") & (panel["ttl_sec"] == 5.0) & (panel["exit_spread_bps"] >= panel.groupby(["exit_profile_source", "date"])["exit_spread_bps"].transform(lambda s: s.quantile(0.90))))
    )
    # This is only a descriptive same-day approximation of the policy shape; the
    # policy report remains the prior-date source of truth.
    selected = panel.loc[mask].copy()
    rows = []
    for (profile, ttl), group in selected.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        row = {"exit_profile_source": profile, "ttl_sec": float(ttl)}
        row.update(summarize_group(group))
        rows.append(row)
    return pd.DataFrame(rows)


def prior_bin_oos_summary(panel: pd.DataFrame, oos_from_date: str, min_count: int) -> pd.DataFrame:
    """Use pre-OOS quantiles for a small anti-post-hoc readout."""
    factors = [
        "residual_pressure_score",
        "pressure_exhaustion_score",
        "pre_notional_imbalance_5s",
        "recent_mid_alpha_5s_bps",
    ]
    rows: list[dict[str, Any]] = []
    for (profile, ttl), ttl_group in panel.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        train = ttl_group[ttl_group["date"].astype(str) < oos_from_date].copy()
        oos = ttl_group[ttl_group["date"].astype(str) >= oos_from_date].copy()
        if train.empty or oos.empty:
            continue
        for factor in factors:
            if factor not in ttl_group.columns:
                continue
            train_values = pd.to_numeric(train[factor], errors="coerce").dropna()
            if train_values.nunique() < 2:
                continue
            q20, q40, q60, q80 = [float(value) for value in train_values.quantile([0.20, 0.40, 0.60, 0.80])]

            def assign_bin(value: Any) -> str:
                value = optional_float(value)
                if value is None:
                    return "na"
                if value <= q20:
                    return "q1"
                if value <= q40:
                    return "q2"
                if value <= q60:
                    return "q3"
                if value <= q80:
                    return "q4"
                return "q5"

            work = oos.copy()
            work["factor_bin"] = work[factor].map(assign_bin)
            for bin_name, group in work.groupby("factor_bin", sort=True):
                if str(bin_name) == "na" or len(group) < min_count:
                    continue
                row = {
                    "exit_profile_source": profile,
                    "ttl_sec": float(ttl),
                    "factor": factor,
                    "factor_bin": str(bin_name),
                    "train_rows": int(len(train)),
                    "oos_from_date": oos_from_date,
                    "oos_rows": int(len(oos)),
                    "q20_train": q20,
                    "q40_train": q40,
                    "q60_train": q60,
                    "q80_train": q80,
                }
                row.update(summarize_group(group))
                rows.append(row)
    return pd.DataFrame(rows)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 40) -> list[str]:
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


def write_report(
    path: Path,
    summary: dict[str, Any],
    factor_rows: pd.DataFrame,
    selected_rows: pd.DataFrame,
    prior_oos_rows: pd.DataFrame,
) -> None:
    score_rows = factor_rows[factor_rows["factor"].isin(["residual_pressure_score", "pressure_exhaustion_score"])].copy()
    score_rows = score_rows.sort_values(
        ["exit_profile_source", "ttl_sec", "factor", "factor_bin"],
        ascending=[True, True, True, True],
    )
    best_runtime = factor_rows.sort_values("weighted_sum_wait_value_bps", ascending=False).head(20)
    selected_view = selected_rows.sort_values("weighted_sum_wait_value_bps", ascending=False)
    if prior_oos_rows.empty:
        oos_view = prior_oos_rows
    else:
        oos_view = prior_oos_rows[
            (prior_oos_rows["factor"].isin(["residual_pressure_score", "pressure_exhaustion_score"]))
            & (prior_oos_rows["ttl_sec"].isin([5.0, 10.0]))
        ].copy()
        oos_view = oos_view.sort_values("weighted_sum_wait_value_bps", ascending=False)
    lines = [
        "# CCUSDT ExitControllerV1 residual pressure diagnostic",
        "",
        "This diagnostic tests the first-principles hypothesis that wait value comes from residual order-flow pressure, not from a price-shape rule.",
        "",
        "\\[",
        "Y_{0:T}=\\int_0^T \\mu_u du + \\int_0^T \\sigma_u dW_u - C,",
        "\\qquad \\mu_u \\approx \\lambda_u X_u.",
        "\\]",
        "",
        "At an exit decision, the runtime-safe question is whether the remaining pressure stock \\(X_t\\) and its persistence still imply positive residual impact.",
        "",
        "## Scope",
        "",
        f"- Input panel: `{summary['panel_path']}`",
        f"- Pressure panel rows: `{summary['pressure_panel_rows']}`",
        f"- Long panel rows: `{summary['long_panel_rows']}`",
        f"- Output directory: `{summary['out_dir']}`",
        "",
        "## Pressure Features",
        "",
        "- `pre_notional_imbalance_{1s,2s,5s}`: signed same-side active notional imbalance before exit.",
        "- `pressure_persistence_1s_vs_5s`: recent pressure stock relative to the 5s stock.",
        "- `impact_per_1k_notional_5s`: recent mid impact per 1k signed notional.",
        "- `impact_exhaustion_ratio`: pre-exit giveback divided by `abs(recent_mid_alpha_5s_bps)+1bp`, capped at `10`, so near-zero alpha cannot dominate.",
        "- `residual_pressure_score`: simple pre-exit composite of 1s/2s/5s pressure plus signed top-depth support.",
        "- `pressure_exhaustion_score`: `path_d_bps/(path_h_bps+1bp)`, capped at `10`, minus pressure support; high means giveback dominates remaining pressure.",
        "",
        "## Residual Pressure / Exhaustion Buckets",
        "",
    ]
    lines.extend(
        markdown_table(
            score_rows,
            [
                "exit_profile_source",
                "ttl_sec",
                "factor",
                "factor_bin",
                "n",
                "exposure",
                "weighted_mean_wait_value_bps",
                "weighted_sum_wait_value_bps",
                "wait_positive_rate",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Best Pressure Buckets", ""])
    lines.extend(
        markdown_table(
            best_runtime,
            [
                "exit_profile_source",
                "ttl_sec",
                "factor",
                "factor_bin",
                "n",
                "exposure",
                "weighted_mean_wait_value_bps",
                "weighted_sum_wait_value_bps",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=30,
        )
    )
    lines.extend(["", "## Current Policy Shape, Descriptive Same-Day Approximation", ""])
    lines.extend(
        markdown_table(
            selected_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "n",
                "exposure",
                "weighted_mean_wait_value_bps",
                "weighted_sum_wait_value_bps",
                "mean_residual_pressure_score",
                "mean_pressure_exhaustion_score",
                "cvar10_wait_value_bps",
                "positive_day_frac",
            ],
            max_rows=20,
        )
    )
    lines.extend(["", f"## Prior-Bin OOS Sanity From {summary['oos_from_date']}", ""])
    lines.extend(
        markdown_table(
            oos_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "factor",
                "factor_bin",
                "n",
                "exposure",
                "weighted_mean_wait_value_bps",
                "weighted_sum_wait_value_bps",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=30,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The pressure hypothesis is only partially supported here. High residual-pressure buckets often have better wait value, and high exhaustion buckets are usually worse, but the currently selected conservative wait shape has only mild average residual pressure. So the existing wait overlay should still be treated as a coarse exit-timing gate, not yet as a true latent residual-pressure controller.",
            "",
            "The next non-overfit step is not to add many more handcrafted pattern flags. It is to test whether a small prior-date pressure admission rule can improve the existing wait overlay without increasing left-tail cost, using only pre-exit pressure state.",
            "",
            "## Files",
            "",
            f"- Pressure panel: `{summary['outputs']['pressure_panel_parquet']}`",
            f"- Long panel: `{summary['outputs']['long_panel_parquet']}`",
            f"- Factor summary: `{summary['outputs']['factor_summary_csv']}`",
            f"- Prior-bin OOS summary: `{summary['outputs']['prior_bin_oos_summary_csv']}`",
            f"- Summary: `{summary['outputs']['summary_json']}`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    panel_path = repo_path(repo_root, args.panel)
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = pq.read_table(panel_path).to_pandas()
    if not bool(panel["runtime_safe"].all()):
        raise ValueError("input panel contains non-runtime-safe rows")
    pressure = build_exit_pressure(panel, repo_root, args.symbol, args.from_date, args.to_date)
    long_panel = attach_pressure(panel, pressure)
    factors = factor_summary(long_panel, args.min_bin_count)
    selected = selected_policy_overlap(long_panel)
    prior_oos = prior_bin_oos_summary(long_panel, args.oos_from_date, args.min_bin_count)

    pressure_parquet = out_dir / "exit_residual_pressure_panel.parquet"
    pressure_csv = out_dir / "exit_residual_pressure_panel.csv"
    long_parquet = out_dir / "exit_residual_pressure_long_panel.parquet"
    factor_csv = out_dir / "exit_residual_pressure_factor_summary.csv"
    selected_csv = out_dir / "exit_residual_pressure_selected_policy_shape.csv"
    prior_oos_csv = out_dir / "exit_residual_pressure_prior_bin_oos_summary.csv"
    write_parquet(pressure_parquet, pressure)
    write_csv(pressure_csv, pressure)
    write_parquet(long_parquet, long_panel)
    write_csv(factor_csv, factors)
    write_csv(selected_csv, selected)
    write_csv(prior_oos_csv, prior_oos)
    summary = {
        "schema_id": "ccusdt_exit_residual_pressure_summary_v1",
        "ok": True,
        "panel_path": str(panel_path),
        "panel_sha256": file_sha256(panel_path),
        "from_date": args.from_date,
        "to_date": args.to_date,
        "oos_from_date": args.oos_from_date,
        "pressure_panel_rows": int(len(pressure)),
        "long_panel_rows": int(len(long_panel)),
        "factor_rows": int(len(factors)),
        "selected_policy_shape_rows": int(len(selected)),
        "prior_bin_oos_rows": int(len(prior_oos)),
        "out_dir": str(out_dir),
        "boundary": "pressure features are pre-exit runtime-safe; wait outcomes are evaluation labels",
        "outputs": {
            "pressure_panel_parquet": str(pressure_parquet),
            "pressure_panel_csv": str(pressure_csv),
            "long_panel_parquet": str(long_parquet),
            "factor_summary_csv": str(factor_csv),
            "selected_policy_shape_csv": str(selected_csv),
            "prior_bin_oos_summary_csv": str(prior_oos_csv),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    summary["summary_hash"] = stable_hash(summary)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_report(report_path, summary, factors, selected, prior_oos)
    print(json.dumps({"ok": True, "summary": str(out_dir / "summary.json"), "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
