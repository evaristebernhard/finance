#!/usr/bin/env python
"""Walk-forward sizing optimization for CCUSDT TFI pre-trade gates."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2"
GUARDRAIL = "research_only_walk_forward_sizing_optimization_no_execution_recommendation_no_alpha_claim"
ROOT = Path(__file__).resolve().parents[1]
DATE_DIR = ROOT / "date"
DOC_DIR = ROOT / "docs" / "markets" / "ccusdt"
SCORED_ENTRIES = DATE_DIR / "ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv"

GAMMA00_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]
GAMMA10_GRID = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
GAMMA01_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]
GAMMA11_GRID = [1.5, 2.0, 2.5, 3.0, 4.0]
MIN_TRAIN_DAYS = 5
FIXED_POLICIES = {
    "locked_baseline_all_1x": (1.0, 1.0, 1.0, 1.0),
    "broad_only_1x": (0.0, 1.0, 0.0, 1.0),
    "stale_only_1x": (0.0, 0.0, 1.0, 1.0),
    "strict_only_1x": (0.0, 0.0, 0.0, 1.0),
    "three_layer_recommended_0_0p75_0_4": (0.0, 0.75, 0.0, 4.0),
    "four_cell_recommended_0_0p5_0p25_4": (0.0, 0.5, 0.25, 4.0),
    "four_cell_stale_half_0_0p75_0p5_4": (0.0, 0.75, 0.5, 4.0),
    "four_cell_stale_full_0_0p75_1_4": (0.0, 0.75, 1.0, 4.0),
    "four_cell_milder_0_0p75_0p5_2p5": (0.0, 0.75, 0.5, 2.5),
    "capped_four_cell_0_1_0p5_2": (0.0, 1.0, 0.5, 2.0),
    "conservative_four_cell_0p25_1_0p25_2": (0.25, 1.0, 0.25, 2.0),
}


def out_variants_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_strategy_sizing_variants_{RUN_TAG}.csv"


def out_walk_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_strategy_sizing_walkforward_{RUN_TAG}.csv"


def out_daily_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_strategy_sizing_daily_{RUN_TAG}.csv"


def out_cells_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_strategy_sizing_cells_{RUN_TAG}.csv"


def out_summary_json() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_strategy_sizing_summary_{RUN_TAG}.json"


def out_report_md() -> Path:
    return DOC_DIR / f"v1-tfi-strategy-sizing-opt-{RUN_TAG}.md"


def fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    cols = [col for col in columns if col in df.columns]
    view = df.loc[:, cols].head(max_rows).copy()
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def max_drawdown(series: pd.Series | np.ndarray) -> float:
    arr = np.asarray(series, dtype=float)
    if len(arr) == 0:
        return np.nan
    curve = np.cumsum(arr)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]
    return float(np.min(curve - peak))


def cvar(values: np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    cutoff = np.quantile(arr, q)
    tail = arr[arr <= cutoff]
    return float(np.mean(tail)) if len(tail) else np.nan


def load_entries() -> pd.DataFrame:
    df = pd.read_csv(SCORED_ENTRIES)
    df = df[(pd.to_numeric(df["weight"], errors="coerce") > 0) & pd.to_numeric(df["net"], errors="coerce").notna()].copy()
    for col in ["net", "weight", "entry_ts", "entry_row"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = df["date"].astype(str)
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
    df["base_weight_locked"] = df["weight"].astype(float)
    df = df.sort_values(["date", "entry_ts", "entry_row"]).reset_index(drop=True)
    return df


def gamma_for_cell(cell: pd.Series, gamma00: float, gamma10: float, gamma01: float, gamma11: float) -> np.ndarray:
    return np.select(
        [cell.eq("11_r5_frames"), cell.eq("10_r5_only"), cell.eq("01_frames_only")],
        [gamma11, gamma10, gamma01],
        default=gamma00,
    ).astype(float)


def evaluate_entries(
    df: pd.DataFrame,
    gamma00: float,
    gamma10: float,
    gamma01: float,
    gamma11: float,
    name: str,
    scope: str,
) -> dict[str, Any]:
    gamma = gamma_for_cell(df["cell"], gamma00, gamma10, gamma01, gamma11)
    exposure = df["base_weight_locked"].to_numpy(dtype=float) * gamma
    net = df["net"].to_numpy(dtype=float)
    pnl = exposure * net
    active = np.isfinite(net) & np.isfinite(exposure) & (exposure > 0)
    exposure = exposure[active]
    net = net[active]
    pnl = pnl[active]
    active_df = df.loc[df.index[active]].copy()
    if len(net) == 0:
        return {
            "variant": name,
            "scope": scope,
            "gamma00_none": gamma00,
            "gamma10_r5_only": gamma10,
            "gamma01_frames_only": gamma01,
            "gamma11_r5_frames": gamma11,
            "entries": 0,
            "exposure": 0.0,
            "total_net": 0.0,
            "mean_net": np.nan,
        }
    daily = active_df.assign(pnl=pnl, exposure=exposure).groupby("date", sort=True).agg(
        daily_net=("pnl", "sum"),
        daily_exposure=("exposure", "sum"),
        entries=("pnl", "size"),
    )
    pos = float(np.sum(pnl[pnl > 0.0]))
    neg = float(np.sum(pnl[pnl < 0.0]))
    return {
        "variant": name,
        "scope": scope,
        "gamma00_none": gamma00,
        "gamma10_r5_only": gamma10,
        "gamma01_frames_only": gamma01,
        "gamma11_r5_frames": gamma11,
        "entries": int(len(net)),
        "exposure": float(np.sum(exposure)),
        "total_net": float(np.sum(pnl)),
        "mean_net": safe_div(float(np.sum(pnl)), float(np.sum(exposure))),
        "median_net_unweighted": float(np.median(net)),
        "gt2_exposure_rate": safe_div(float(np.sum(exposure[net > 2.0])), float(np.sum(exposure))),
        "cost_hit_exposure_rate": safe_div(float(np.sum(exposure[net <= 0.0])), float(np.sum(exposure))),
        "positive_net": pos,
        "negative_net": neg,
        "pos_over_abs_neg": safe_div(pos, abs(neg)),
        "entry_pnl_cvar10": cvar(pnl, 0.10),
        "entry_pnl_p10": float(np.quantile(pnl, 0.10)),
        "entry_pnl_p90": float(np.quantile(pnl, 0.90)),
        "daily_count": int(len(daily)),
        "positive_day_count": int((daily["daily_net"] > 0).sum()),
        "worst_day_net": float(daily["daily_net"].min()),
        "best_day_net": float(daily["daily_net"].max()),
        "daily_cvar20": cvar(daily["daily_net"].to_numpy(dtype=float), 0.20),
        "max_drawdown": max_drawdown(daily["daily_net"].to_numpy(dtype=float)),
        "daily_mean_net": float(daily["daily_net"].mean()),
        "daily_std_net": float(daily["daily_net"].std(ddof=1)) if len(daily) > 1 else np.nan,
        "daily_sharpe_like": safe_div(float(daily["daily_net"].mean()), float(daily["daily_net"].std(ddof=1)))
        if len(daily) > 1
        else np.nan,
    }


def variant_grid() -> list[tuple[str, float, float, float, float]]:
    variants: list[tuple[str, float, float, float, float]] = [
        ("locked_baseline_all_1x", 1.0, 1.0, 1.0, 1.0),
        ("broad_only_1x", 0.0, 1.0, 0.0, 1.0),
        ("stale_only_1x", 0.0, 0.0, 1.0, 1.0),
        ("strict_only_1x", 0.0, 0.0, 0.0, 1.0),
        ("three_layer_recommended_0_0p75_0_4", 0.0, 0.75, 0.0, 4.0),
        ("four_cell_recommended_0_0p5_0p25_4", 0.0, 0.5, 0.25, 4.0),
        ("four_cell_stale_half_0_0p75_0p5_4", 0.0, 0.75, 0.5, 4.0),
        ("four_cell_milder_0_0p75_0p5_2p5", 0.0, 0.75, 0.5, 2.5),
        ("conservative_four_cell_0p25_1_0p25_2", 0.25, 1.0, 0.25, 2.0),
    ]
    for g00, g10, g01, g11 in itertools.product(GAMMA00_GRID, GAMMA10_GRID, GAMMA01_GRID, GAMMA11_GRID):
        if g11 < max(g10, g01):
            continue
        variants.append((f"grid_g00_{g00:g}_g10_{g10:g}_g01_{g01:g}_g11_{g11:g}", g00, g10, g01, g11))
    # Preserve order and uniqueness by gamma tuple.
    seen = set()
    out = []
    for name, g00, g10, g01, g11 in variants:
        key = (g00, g10, g01, g11)
        if key in seen:
            continue
        seen.add(key)
        out.append((name, g00, g10, g01, g11))
    return out


def all_variant_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, g00, g10, g01, g11 in variant_grid():
        row = evaluate_entries(df, g00, g10, g01, g11, name, "all_dates_in_sample")
        # Simple risk-aware score: reward mean and positivity, punish drawdown.
        row["risk_score"] = row["mean_net"] + 0.02 * row["daily_mean_net"] + 0.01 * row["worst_day_net"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["risk_score", "mean_net"], ascending=False)


def choose_variant(train: pd.DataFrame, min_days: int = MIN_TRAIN_DAYS) -> tuple[str, float, float, float, float, dict[str, Any]]:
    rows = []
    for name, g00, g10, g01, g11 in variant_grid():
        row = evaluate_entries(train, g00, g10, g01, g11, name, "train")
        if row.get("daily_count", 0) < min_days or row.get("entries", 0) < 50:
            continue
        if row["total_net"] <= 0 or row["mean_net"] <= 0:
            continue
        if row["positive_day_count"] < max(3, int(np.ceil(row["daily_count"] * 0.50))):
            continue
        # Prefer high mean with non-disastrous training worst day.
        row["selection_score"] = row["mean_net"] + 0.02 * row["daily_mean_net"] + 0.01 * row["worst_day_net"]
        rows.append(row)
    if not rows:
        fallback = ("locked_baseline_all_1x", 1.0, 1.0, 1.0, 1.0)
        return (*fallback, {"selection_status": "fallback_locked_baseline"})
    table = pd.DataFrame(rows).sort_values(["selection_score", "mean_net"], ascending=False)
    best = table.iloc[0].to_dict()
    return (
        str(best["variant"]),
        float(best["gamma00_none"]),
        float(best["gamma10_r5_only"]),
        float(best["gamma01_frames_only"]),
        float(best["gamma11_r5_frames"]),
        {"selection_status": "selected_by_train_score", **best},
    )


def walk_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(df["date"].unique().tolist())
    rows = []
    daily_rows = []
    for i, date in enumerate(dates):
        if i < MIN_TRAIN_DAYS:
            continue
        train_dates = dates[:i]
        train = df[df["date"].isin(train_dates)].copy()
        test = df[df["date"].eq(date)].copy()
        variant, g00, g10, g01, g11, selection = choose_variant(train)
        test_eval = evaluate_entries(test, g00, g10, g01, g11, variant, f"test_{date}")
        fixed_evals = {
            policy: evaluate_entries(test, *gammas, policy, f"test_{date}") for policy, gammas in FIXED_POLICIES.items()
        }
        locked_eval = fixed_evals["locked_baseline_all_1x"]
        broad_eval = fixed_evals["broad_only_1x"]
        stale_eval = fixed_evals["stale_only_1x"]
        strict_eval = fixed_evals["strict_only_1x"]
        row = {
            "test_date": date,
            "train_start": train_dates[0],
            "train_end": train_dates[-1],
            "chosen_variant": variant,
            "gamma00_none": g00,
            "gamma10_r5_only": g10,
            "gamma01_frames_only": g01,
            "gamma11_r5_frames": g11,
            "train_selection_status": selection.get("selection_status"),
            "train_selection_score": selection.get("selection_score", np.nan),
            "test_entries": test_eval["entries"],
            "test_exposure": test_eval["exposure"],
            "test_total_net": test_eval["total_net"],
            "test_mean_net": test_eval["mean_net"],
            "test_gt2_rate": test_eval.get("gt2_exposure_rate", np.nan),
            "test_cost_hit_rate": test_eval.get("cost_hit_exposure_rate", np.nan),
            "locked_total_net": locked_eval["total_net"],
            "locked_mean_net": locked_eval["mean_net"],
            "broad_total_net": broad_eval["total_net"],
            "broad_mean_net": broad_eval["mean_net"],
            "stale_total_net": stale_eval["total_net"],
            "stale_mean_net": stale_eval["mean_net"],
            "strict_total_net": strict_eval["total_net"],
            "strict_mean_net": strict_eval["mean_net"],
        }
        rows.append(row)
        daily_rows.append({"date": date, "policy": "walk_forward_chosen", **test_eval})
        for policy, eval_row in fixed_evals.items():
            daily_rows.append({"date": date, "policy": policy, **eval_row})
    return pd.DataFrame(rows), pd.DataFrame(daily_rows)


def policy_entry_risk(df: pd.DataFrame, walk: pd.DataFrame) -> pd.DataFrame:
    test_dates = sorted(walk["test_date"].astype(str).unique().tolist())
    test = df[df["date"].isin(test_dates)].copy()
    rows = []
    for policy, (g00, g10, g01, g11) in FIXED_POLICIES.items():
        gamma = gamma_for_cell(test["cell"], g00, g10, g01, g11)
        exposure = test["base_weight_locked"].to_numpy(dtype=float) * gamma
        net = test["net"].to_numpy(dtype=float)
        pnl = exposure * net
        active = np.isfinite(pnl) & (exposure > 0)
        rows.append(
            {
                "policy": policy,
                "entry_worst_pnl": float(np.min(pnl[active])) if active.any() else np.nan,
                "entry_cvar05": cvar(pnl[active], 0.05) if active.any() else np.nan,
                "entry_cvar10": cvar(pnl[active], 0.10) if active.any() else np.nan,
                "active_entries": int(np.sum(active)),
            }
        )
    # Walk-forward chosen has varying gammas by day.
    parts = []
    for _, row in walk.iterrows():
        day = test[test["date"].eq(str(row["test_date"]))].copy()
        gamma = gamma_for_cell(
            day["cell"],
            float(row["gamma00_none"]),
            float(row["gamma10_r5_only"]),
            float(row["gamma01_frames_only"]),
            float(row["gamma11_r5_frames"]),
        )
        exposure = day["base_weight_locked"].to_numpy(dtype=float) * gamma
        pnl = exposure * day["net"].to_numpy(dtype=float)
        parts.append(pnl[exposure > 0])
    if parts:
        pnl = np.concatenate(parts)
        rows.append(
            {
                "policy": "walk_forward_chosen",
                "entry_worst_pnl": float(np.min(pnl)) if len(pnl) else np.nan,
                "entry_cvar05": cvar(pnl, 0.05),
                "entry_cvar10": cvar(pnl, 0.10),
                "active_entries": int(len(pnl)),
            }
        )
    return pd.DataFrame(rows)


def leverage_table(daily: pd.DataFrame, entry_risk: pd.DataFrame) -> pd.DataFrame:
    rows = []
    entry_lookup = entry_risk.set_index("policy").to_dict(orient="index") if not entry_risk.empty else {}
    for policy, g in daily.groupby("policy", sort=True):
        nets = pd.to_numeric(g["total_net"], errors="coerce").to_numpy(dtype=float)
        if not len(nets):
            continue
        worst = float(np.min(nets))
        cvar20 = cvar(nets, 0.20)
        maxdd = max_drawdown(nets)
        # If 1 unit of strategy notional maps to 1bp risk budget, these are
        # dimensionless leverage multipliers against bp-unit drawdown budgets.
        for budget in [50.0, 100.0, 200.0]:
            entry_worst = entry_lookup.get(policy, {}).get("entry_worst_pnl", np.nan)
            entry_cvar05 = entry_lookup.get(policy, {}).get("entry_cvar05", np.nan)
            rows.append(
                {
                    "policy": policy,
                    "loss_budget_bps_units": budget,
                    "cap_by_worst_day": safe_div(budget, abs(worst)),
                    "cap_by_daily_cvar20": safe_div(budget, abs(cvar20)),
                    "cap_by_max_drawdown": safe_div(budget, abs(maxdd)),
                    "cap_by_worst_entry": safe_div(budget, abs(entry_worst)),
                    "cap_by_entry_cvar05": safe_div(budget, abs(entry_cvar05)),
                    "conservative_cap_min": np.nanmin(
                        [
                            safe_div(budget, abs(worst)),
                            safe_div(budget, abs(maxdd)),
                            safe_div(budget, abs(entry_worst)),
                            safe_div(budget, abs(entry_cvar05)),
                        ]
                    ),
                    "worst_day_net": worst,
                    "daily_cvar20": cvar20,
                    "max_drawdown": maxdd,
                    "entry_worst_pnl": entry_worst,
                    "entry_cvar05": entry_cvar05,
                    "total_net": float(np.sum(nets)),
                    "positive_days": int(np.sum(nets > 0)),
                    "days": int(len(nets)),
                }
            )
    return pd.DataFrame(rows)


def summarize_policy(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for policy, g in daily.groupby("policy", sort=True):
        nets = pd.to_numeric(g["total_net"], errors="coerce").to_numpy(dtype=float)
        exposures = pd.to_numeric(g["exposure"], errors="coerce").to_numpy(dtype=float)
        rows.append(
            {
                "policy": policy,
                "days": int(len(g)),
                "positive_days": int(np.sum(nets > 0)),
                "total_net": float(np.sum(nets)),
                "exposure": float(np.sum(exposures)),
                "mean_net": safe_div(float(np.sum(nets)), float(np.sum(exposures))),
                "worst_day_net": float(np.min(nets)) if len(nets) else np.nan,
                "best_day_net": float(np.max(nets)) if len(nets) else np.nan,
                "daily_cvar20": cvar(nets, 0.20),
                "max_drawdown": max_drawdown(nets),
                "daily_mean": float(np.mean(nets)) if len(nets) else np.nan,
                "daily_std": float(np.std(nets, ddof=1)) if len(nets) > 1 else np.nan,
                "daily_sharpe_like": safe_div(float(np.mean(nets)), float(np.std(nets, ddof=1))) if len(nets) > 1 else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("total_net", ascending=False)


def summarize_cells(df: pd.DataFrame, scope: str) -> pd.DataFrame:
    rows = []
    order = ["00_none", "10_r5_only", "01_frames_only", "11_r5_frames"]
    for cell in order:
        sub = df[df["cell"].eq(cell)].copy()
        if sub.empty:
            rows.append(
                {
                    "scope": scope,
                    "cell": cell,
                    "A_r5": int(cell.startswith("1")),
                    "B_frames_q90": int(cell.endswith("frames") or cell.startswith("01")),
                    "entries": 0,
                    "exposure": 0.0,
                    "total_net": 0.0,
                    "mean_net": np.nan,
                }
            )
            continue
        exposure = sub["base_weight_locked"].to_numpy(dtype=float)
        net = sub["net"].to_numpy(dtype=float)
        pnl = exposure * net
        active = np.isfinite(exposure) & np.isfinite(net) & (exposure > 0)
        sub = sub.loc[sub.index[active]].copy()
        exposure = exposure[active]
        net = net[active]
        pnl = pnl[active]
        daily = sub.assign(pnl=pnl, exposure=exposure).groupby("date", sort=True).agg(
            daily_net=("pnl", "sum"),
            daily_exposure=("exposure", "sum"),
            entries=("pnl", "size"),
        )
        pos = float(np.sum(pnl[pnl > 0.0]))
        neg = float(np.sum(pnl[pnl < 0.0]))
        rows.append(
            {
                "scope": scope,
                "cell": cell,
                "A_r5": int(cell in {"10_r5_only", "11_r5_frames"}),
                "B_frames_q90": int(cell in {"01_frames_only", "11_r5_frames"}),
                "entries": int(len(net)),
                "exposure": float(np.sum(exposure)),
                "total_net": float(np.sum(pnl)),
                "mean_net": safe_div(float(np.sum(pnl)), float(np.sum(exposure))),
                "median_net_unweighted": float(np.median(net)) if len(net) else np.nan,
                "gt2_exposure_rate": safe_div(float(np.sum(exposure[net > 2.0])), float(np.sum(exposure))),
                "cost_hit_exposure_rate": safe_div(float(np.sum(exposure[net <= 0.0])), float(np.sum(exposure))),
                "positive_net": pos,
                "negative_net": neg,
                "pos_over_abs_neg": safe_div(pos, abs(neg)),
                "days": int(len(daily)),
                "positive_day_count": int((daily["daily_net"] > 0.0).sum()),
                "positive_day_rate": safe_div(float((daily["daily_net"] > 0.0).sum()), float(len(daily))),
                "worst_day_net": float(daily["daily_net"].min()) if len(daily) else np.nan,
                "best_day_net": float(daily["daily_net"].max()) if len(daily) else np.nan,
                "daily_cvar20": cvar(daily["daily_net"].to_numpy(dtype=float), 0.20),
                "entry_worst_pnl": float(np.min(pnl)) if len(pnl) else np.nan,
                "entry_cvar05": cvar(pnl, 0.05),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    variants: pd.DataFrame,
    walk: pd.DataFrame,
    daily: pd.DataFrame,
    cells: pd.DataFrame,
    policy_summary: pd.DataFrame,
    lev: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    lines = [
        "# CCUSDT TFI Strategy Sizing Optimization",
        "",
        f"Status: `{RUN_TAG}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "Mutually exclusive state layers:",
        "",
        r"$$",
        r"A_t=\mathbf{1}\{R_5>1\},\quad B_t=\mathbf{1}\{F_t\ge q_{90}\},\quad \gamma_t=\gamma_{A_tB_t}",
        r"$$",
        "",
        r"$$",
        r"\begin{array}{c|cc}",
        r" & B_t=0 & B_t=1 \\",
        r"\hline",
        r"A_t=0 & \gamma_{00} & \gamma_{01} \\",
        r"A_t=1 & \gamma_{10} & \gamma_{11}",
        r"\end{array}",
        r"$$",
        "",
        "The walk-forward loop chooses \\((\\gamma_{00},\\gamma_{10},\\gamma_{01},\\gamma_{11})\\) using only prior dates, then evaluates the next date.",
        "",
        "## Mutually Exclusive Cell Stats",
        "",
        *markdown_table(
            cells.sort_values(["scope", "A_r5", "B_frames_q90"]),
            [
                "scope",
                "cell",
                "A_r5",
                "B_frames_q90",
                "entries",
                "exposure",
                "total_net",
                "mean_net",
                "gt2_exposure_rate",
                "cost_hit_exposure_rate",
                "positive_day_count",
                "days",
                "positive_day_rate",
                "worst_day_net",
            ],
            max_rows=12,
        ),
        "",
        "## In-Sample Variant Frontier",
        "",
        *markdown_table(
            variants.head(20),
            [
                "variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "entries",
                "exposure",
                "total_net",
                "mean_net",
                "worst_day_net",
                "daily_cvar20",
                "max_drawdown",
                "positive_day_count",
                "risk_score",
            ],
            max_rows=20,
        ),
        "",
        "## Walk-Forward Daily Choices",
        "",
        *markdown_table(
            walk,
            [
                "test_date",
                "chosen_variant",
                "gamma00_none",
                "gamma10_r5_only",
                "gamma01_frames_only",
                "gamma11_r5_frames",
                "test_entries",
                "test_exposure",
                "test_total_net",
                "test_mean_net",
                "locked_total_net",
                "broad_total_net",
                "stale_total_net",
                "strict_total_net",
            ],
            max_rows=30,
        ),
        "",
        "## Policy Summary",
        "",
        *markdown_table(
            policy_summary,
            [
                "policy",
                "days",
                "positive_days",
                "total_net",
                "exposure",
                "mean_net",
                "worst_day_net",
                "daily_cvar20",
                "max_drawdown",
                "daily_sharpe_like",
            ],
            max_rows=20,
        ),
        "",
        "## Leverage Caps",
        "",
        "These caps are dimensionless multipliers under a bp-unit loss budget. They are not account-level trading advice; map them to actual notional only after fill/slippage and exchange margin constraints.",
        "",
        *markdown_table(
            lev[lev["loss_budget_bps_units"].eq(100.0)].sort_values("conservative_cap_min", ascending=False),
            [
                "policy",
                "loss_budget_bps_units",
                "conservative_cap_min",
                "cap_by_worst_day",
                "cap_by_worst_entry",
                "cap_by_entry_cvar05",
                "worst_day_net",
                "entry_worst_pnl",
                "entry_cvar05",
                "total_net",
            ],
            max_rows=20,
        ),
        "",
        "## Read",
        "",
        summary["interpretation"],
        "",
        "## Outputs",
        "",
        f"- `{out_variants_csv()}`",
        f"- `{out_walk_csv()}`",
        f"- `{out_daily_csv()}`",
        f"- `{out_cells_csv()}`",
        f"- `{out_summary_json()}`",
        "",
    ]
    out_report_md().write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    df = load_entries()
    variants = all_variant_scorecard(df)
    walk, daily = walk_forward(df)
    test_dates = sorted(walk["test_date"].astype(str).unique().tolist())
    cells = pd.concat(
        [
            summarize_cells(df, "all_scored_dates"),
            summarize_cells(df[df["date"].isin(test_dates)].copy(), "walkforward_test_9d"),
        ],
        ignore_index=True,
    )
    policy_summary = summarize_policy(daily)
    entry_risk = policy_entry_risk(df, walk)
    lev = leverage_table(daily, entry_risk)

    chosen = policy_summary[policy_summary["policy"].eq("walk_forward_chosen")].iloc[0].to_dict()
    locked = policy_summary[policy_summary["policy"].eq("locked_baseline_all_1x")].iloc[0].to_dict()
    broad = policy_summary[policy_summary["policy"].eq("broad_only_1x")].iloc[0].to_dict()
    stale = policy_summary[policy_summary["policy"].eq("stale_only_1x")].iloc[0].to_dict()
    strict = policy_summary[policy_summary["policy"].eq("strict_only_1x")].iloc[0].to_dict()
    three_layer = policy_summary[policy_summary["policy"].eq("three_layer_recommended_0_0p75_0_4")].iloc[0].to_dict()
    four_cell = policy_summary[policy_summary["policy"].eq("four_cell_recommended_0_0p5_0p25_4")].iloc[0].to_dict()
    cell01 = cells[(cells["scope"].eq("walkforward_test_9d")) & (cells["cell"].eq("01_frames_only"))].iloc[0].to_dict()
    if chosen["total_net"] > locked["total_net"] and chosen["worst_day_net"] >= locked["worst_day_net"]:
        read = "Walk-forward sizing improves total net without worsening worst-day loss versus locked baseline."
    elif four_cell["total_net"] > locked["total_net"]:
        read = (
            "The cleaner simple state-sizing policy is four-cell gamma=(0, 0.5, 0.25, 4): skip 00, keep 10 small, "
            "trade 01 at small size, and boost 11. The old three-layer gamma=(0, 0.75, 0, 4) was too coarse because it "
            "silenced the 01 stale-queue state."
        )
    elif three_layer["total_net"] > locked["total_net"]:
        read = "The old three-layer policy remains profitable, but it should be treated as a nested special case with gamma01=0."
    elif broad["total_net"] > locked["total_net"] or stale["total_net"] > locked["total_net"]:
        read = "The robust simple improvement is broad-only sizing: it captures most profit while avoiding negative non-broad exposure."
    else:
        read = "Locked baseline remains competitive; use gates as diagnostic/sizing overlays rather than hard filters."
    interpretation = (
        f"{read} The 01 cell has {cell01['entries']:.0f} entries, mean {cell01['mean_net']:.4f} bps, "
        f"and positive days {cell01['positive_day_count']:.0f}/{cell01['days']:.0f} in the walk-forward test window. "
        "Strict 11 has high mean but low coverage; it is best treated as an add-on boost, not a standalone strategy. "
        "Leverage should be capped by worst-day/CVaR, not by mean return."
    )

    summary = {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "days": sorted(df["date"].unique().tolist()),
        "variant_count": int(len(variants)),
        "cell_scorecard": cells.to_dict(orient="records"),
        "policy_summary": policy_summary.to_dict(orient="records"),
        "leverage_caps_100_budget": lev[lev["loss_budget_bps_units"].eq(100.0)].to_dict(orient="records"),
        "entry_risk": entry_risk.to_dict(orient="records"),
        "interpretation": interpretation,
        "outputs": {
            "variants_csv": str(out_variants_csv()),
            "walk_csv": str(out_walk_csv()),
            "daily_csv": str(out_daily_csv()),
            "cells_csv": str(out_cells_csv()),
            "summary_json": str(out_summary_json()),
            "report_md": str(out_report_md()),
        },
    }

    variants.to_csv(out_variants_csv(), index=False)
    walk.to_csv(out_walk_csv(), index=False)
    daily.to_csv(out_daily_csv(), index=False)
    cells.to_csv(out_cells_csv(), index=False)
    out_summary_json().write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(variants, walk, daily, cells, policy_summary, lev, summary)
    print(
        "[ccusdt_tfi_strategy_sizing_opt] "
        f"variants={len(variants)} wf_days={len(walk)} "
        f"chosen_total={chosen['total_net']:.4f} locked_total={locked['total_net']:.4f} "
        f"report={out_report_md()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
