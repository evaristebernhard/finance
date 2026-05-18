#!/usr/bin/env python
"""Pre-trade worst-day frontier analysis for CCUSDT TFI sizing states."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_worst_day_frontier_v1"
GUARDRAIL = "research_only_pretrade_worst_day_frontier_no_execution_recommendation_no_alpha_claim"
ROOT = Path(__file__).resolve().parents[1]
DATE_DIR = ROOT / "date"
DOC_DIR = ROOT / "docs" / "markets" / "ccusdt"
SCORED_ENTRIES = DATE_DIR / "ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv"

MIN_TRAIN_DAYS = 5
EPS = 1e-9
TARGET_POLICY = "keep075_add025_0_0p75_0p25_4"
POLICIES = {
    "three_layer_0_0p75_0_4": (0.0, 0.75, 0.0, 4.0),
    TARGET_POLICY: (0.0, 0.75, 0.25, 4.0),
    "keep075_add050_0_0p75_0p5_4": (0.0, 0.75, 0.5, 4.0),
    "conservative_0_0p5_0p25_4": (0.0, 0.5, 0.25, 4.0),
}


@dataclass(frozen=True)
class GateSpec:
    name: str
    metric: str | None
    op: str
    q: float | None = None
    metric2: str | None = None
    op2: str | None = None
    q2: float | None = None


def out_frontier_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_worst_day_frontier_{RUN_TAG}.csv"


def out_daily_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_worst_day_daily_{RUN_TAG}.csv"


def out_diag_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_worst_day_diagnostics_{RUN_TAG}.csv"


def out_report_md() -> Path:
    return DOC_DIR / f"v1-tfi-worst-day-frontier-{RUN_TAG}.md"


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


def cvar(values: np.ndarray, q: float = 0.20) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    cutoff = np.quantile(arr, q)
    tail = arr[arr <= cutoff]
    return float(np.mean(tail)) if len(tail) else np.nan


def max_drawdown(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    curve = np.cumsum(arr)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]
    return float(np.min(curve - peak))


def load_entries() -> pd.DataFrame:
    df = pd.read_csv(SCORED_ENTRIES)
    df = df[(pd.to_numeric(df["weight"], errors="coerce") > 0) & pd.to_numeric(df["net"], errors="coerce").notna()].copy()
    for col in ["net", "weight", "entry_ts", "entry_row", "label_available_ts"]:
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
    return df.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)


def add_closed_roll_stats(df: pd.DataFrame, windows: list[int] = [5, 10, 20]) -> pd.DataFrame:
    out = df.copy()
    order_entry = out.sort_values(["entry_ts", "entry_row"]).index.to_numpy()
    order_label = out.sort_values(["label_available_ts", "entry_row"]).index.to_numpy()
    label_ts = out["label_available_ts"].to_numpy(dtype=float)
    entry_ts = out["entry_ts"].to_numpy(dtype=float)
    net = out["net"].to_numpy(dtype=float)
    available: list[float] = []
    j = 0

    stats: dict[str, list[float]] = {}
    for w in windows:
        for name in [
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
        ]:
            stats[f"closed{w}_{name}"] = [np.nan] * len(out)

    for idx in order_entry:
        t = entry_ts[idx]
        while j < len(order_label) and label_ts[order_label[j]] <= t:
            available.append(float(net[order_label[j]]))
            j += 1
        for w in windows:
            vals = np.asarray(available[-w:], dtype=float)
            vals = vals[np.isfinite(vals)]
            n = len(vals)
            key = f"closed{w}"
            stats[f"{key}_count"][idx] = float(n)
            if n == 0:
                continue
            pos = float(np.sum(vals[vals > 0.0]))
            neg = float(-np.sum(vals[vals < 0.0]))
            delta = pos - neg
            energy = pos + neg
            ratio = safe_div(pos, neg)
            rho = safe_div(delta, energy)
            stats[f"{key}_pos_sum"][idx] = pos
            stats[f"{key}_neg_abs_sum"][idx] = neg
            stats[f"{key}_delta"][idx] = delta
            stats[f"{key}_energy"][idx] = energy
            stats[f"{key}_ratio"][idx] = ratio
            stats[f"{key}_rho"][idx] = rho
            stats[f"{key}_mean"][idx] = float(np.mean(vals))
            stats[f"{key}_min"][idx] = float(np.min(vals))
            stats[f"{key}_loss_abs_max"][idx] = float(np.max(np.maximum(-vals, 0.0)))
            stats[f"{key}_score_abs"][idx] = safe_div(delta, np.sqrt(energy + EPS))

    for col, values in stats.items():
        out[col] = values
    return out


def gamma_for_cell(cell: pd.Series, gamma00: float, gamma10: float, gamma01: float, gamma11: float) -> np.ndarray:
    return np.select(
        [cell.eq("11_r5_frames"), cell.eq("10_r5_only"), cell.eq("01_frames_only")],
        [gamma11, gamma10, gamma01],
        default=gamma00,
    ).astype(float)


def active_view(df: pd.DataFrame, policy: str) -> pd.DataFrame:
    g00, g10, g01, g11 = POLICIES[policy]
    out = df.copy()
    out["gamma"] = gamma_for_cell(out["cell"], g00, g10, g01, g11)
    out["exposure"] = out["weight"].astype(float) * out["gamma"]
    out["pnl"] = out["exposure"] * out["net"].astype(float)
    return out[out["exposure"] > 0].copy()


def apply_gate(df: pd.DataFrame, spec: GateSpec, train: pd.DataFrame) -> tuple[pd.Series, dict[str, float]]:
    if spec.metric is None:
        return pd.Series(True, index=df.index), {}

    thresholds: dict[str, float] = {}
    train_metric = pd.to_numeric(train[spec.metric], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if train_metric.empty:
        return pd.Series(False, index=df.index), {}
    thr = float(train_metric.quantile(float(spec.q)))
    thresholds[f"{spec.metric}_{spec.op}_q{spec.q:g}"] = thr
    vals = pd.to_numeric(df[spec.metric], errors="coerce")
    mask = vals.ge(thr) if spec.op == "ge" else vals.le(thr)

    if spec.metric2 is not None and spec.op2 is not None and spec.q2 is not None:
        train_metric2 = pd.to_numeric(train[spec.metric2], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if train_metric2.empty:
            return pd.Series(False, index=df.index), thresholds
        thr2 = float(train_metric2.quantile(float(spec.q2)))
        thresholds[f"{spec.metric2}_{spec.op2}_q{spec.q2:g}"] = thr2
        vals2 = pd.to_numeric(df[spec.metric2], errors="coerce")
        mask2 = vals2.ge(thr2) if spec.op2 == "ge" else vals2.le(thr2)
        mask = mask & mask2

    return mask.fillna(False), thresholds


def gate_specs() -> list[GateSpec]:
    specs = [GateSpec("no_extra_gate", None, "ge", None)]
    for metric in ["closed5_delta", "closed5_energy", "closed5_rho", "closed5_score_abs", "closed10_delta", "closed10_score_abs"]:
        for q in [0.10, 0.20, 0.30, 0.40, 0.50]:
            specs.append(GateSpec(f"{metric}_ge_q{q:g}", metric, "ge", q))
    for q_delta, q_energy in itertools.product([0.10, 0.20, 0.30, 0.40], [0.10, 0.20, 0.30, 0.40]):
        specs.append(
            GateSpec(
                f"closed5_delta_ge_q{q_delta:g}_and_energy_ge_q{q_energy:g}",
                "closed5_delta",
                "ge",
                q_delta,
                "closed5_energy",
                "ge",
                q_energy,
            )
        )
    for q in [0.50, 0.60, 0.70, 0.80]:
        specs.append(GateSpec(f"closed5_loss_abs_max_le_q{q:g}", "closed5_loss_abs_max", "le", q))
    return specs


def summarize_daily(active: pd.DataFrame, policy: str, gate_name: str) -> pd.DataFrame:
    if active.empty:
        return pd.DataFrame()
    daily = active.groupby("date", sort=True).agg(
        total_net=("pnl", "sum"),
        exposure=("exposure", "sum"),
        entries=("pnl", "size"),
        mean_closed5_delta=("closed5_delta", "mean"),
        mean_closed5_energy=("closed5_energy", "mean"),
        low_abs_cushion_share=("low_abs_cushion_flag", "mean"),
        low_energy_share=("low_energy_flag", "mean"),
        high_recent_loss_share=("high_recent_loss_flag", "mean"),
    )
    daily = daily.reset_index()
    daily["policy"] = policy
    daily["gate"] = gate_name
    daily["mean_net"] = daily["total_net"] / daily["exposure"].replace(0, np.nan)
    return daily


def walk_forward_gate(active: pd.DataFrame, spec: GateSpec) -> tuple[dict[str, Any], pd.DataFrame]:
    dates = sorted(active["date"].unique().tolist())
    daily_parts = []
    threshold_rows = []
    for i, date in enumerate(dates):
        if i < MIN_TRAIN_DAYS:
            continue
        train_dates = dates[:i]
        train = active[active["date"].isin(train_dates)].copy()
        test = active[active["date"].eq(date)].copy()
        mask, thresholds = apply_gate(test, spec, train)
        selected = test[mask].copy()
        daily = summarize_daily(selected, TARGET_POLICY, spec.name)
        if daily.empty:
            daily = pd.DataFrame(
                [
                    {
                        "date": date,
                        "total_net": 0.0,
                        "exposure": 0.0,
                        "entries": 0,
                        "mean_closed5_delta": np.nan,
                        "mean_closed5_energy": np.nan,
                        "low_abs_cushion_share": np.nan,
                        "low_energy_share": np.nan,
                        "high_recent_loss_share": np.nan,
                        "policy": TARGET_POLICY,
                        "gate": spec.name,
                        "mean_net": np.nan,
                    }
                ]
            )
        daily_parts.append(daily)
        threshold_rows.append({"date": date, "gate": spec.name, **thresholds})

    daily_all = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    nets = daily_all["total_net"].to_numpy(dtype=float) if not daily_all.empty else np.array([])
    exposure = daily_all["exposure"].to_numpy(dtype=float) if not daily_all.empty else np.array([])
    row = {
        "gate": spec.name,
        "test_days": int(len(daily_all)),
        "positive_days": int(np.sum(nets > 0.0)) if len(nets) else 0,
        "total_net": float(np.sum(nets)) if len(nets) else 0.0,
        "exposure": float(np.sum(exposure)) if len(exposure) else 0.0,
        "mean_net": safe_div(float(np.sum(nets)), float(np.sum(exposure))) if len(nets) else np.nan,
        "worst_day_net": float(np.min(nets)) if len(nets) else np.nan,
        "daily_cvar20": cvar(nets, 0.20),
        "max_drawdown": max_drawdown(nets),
        "entries": int(daily_all["entries"].sum()) if not daily_all.empty else 0,
        "threshold_count": len(threshold_rows),
    }
    return row, daily_all


def add_fragility_flags(active: pd.DataFrame) -> pd.DataFrame:
    out = active.copy()
    train = out[out["date"] < "2026-05-09"].copy()
    if train.empty:
        train = out.copy()
    q_delta = float(train["closed5_delta"].replace([np.inf, -np.inf], np.nan).dropna().quantile(0.25))
    q_energy = float(train["closed5_energy"].replace([np.inf, -np.inf], np.nan).dropna().quantile(0.25))
    q_loss = float(train["closed5_loss_abs_max"].replace([np.inf, -np.inf], np.nan).dropna().quantile(0.75))
    out["low_abs_cushion_flag"] = out["closed5_delta"] <= q_delta
    out["low_energy_flag"] = out["closed5_energy"] <= q_energy
    out["high_recent_loss_flag"] = out["closed5_loss_abs_max"] >= q_loss
    out.attrs["fragility_thresholds"] = {
        "closed5_delta_q25_train": q_delta,
        "closed5_energy_q25_train": q_energy,
        "closed5_loss_abs_max_q75_train": q_loss,
    }
    return out


def diagnostics(active: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date, g in active.groupby("date", sort=True):
        for cell, sub in g.groupby("cell", sort=True):
            rows.append(
                {
                    "date": date,
                    "cell": cell,
                    "entries": int(len(sub)),
                    "exposure": float(sub["exposure"].sum()),
                    "total_net": float(sub["pnl"].sum()),
                    "mean_net": safe_div(float(sub["pnl"].sum()), float(sub["exposure"].sum())),
                    "mean_closed5_delta": float(sub["closed5_delta"].mean()),
                    "mean_closed5_energy": float(sub["closed5_energy"].mean()),
                    "mean_closed5_rho": float(sub["closed5_rho"].mean()),
                    "low_abs_cushion_share": float(sub["low_abs_cushion_flag"].mean()),
                    "low_energy_share": float(sub["low_energy_flag"].mean()),
                    "high_recent_loss_share": float(sub["high_recent_loss_flag"].mean()),
                }
            )
    return pd.DataFrame(rows)


def write_report(frontier: pd.DataFrame, daily: pd.DataFrame, diag: pd.DataFrame, thresholds: dict[str, float]) -> None:
    base = frontier[frontier["gate"].eq("no_extra_gate")].iloc[0]
    best_worst = frontier.sort_values(["worst_day_net", "total_net"], ascending=[False, False]).head(12)
    best_balanced = frontier[(frontier["total_net"] > 0) & (frontier["exposure"] > 0)].copy()
    best_balanced["frontier_score"] = best_balanced["mean_net"] + 0.002 * best_balanced["total_net"] + 0.02 * best_balanced["worst_day_net"]
    best_balanced = best_balanced.sort_values(["frontier_score", "worst_day_net"], ascending=False).head(12)
    worst_date = str(daily[daily["gate"].eq("no_extra_gate")].sort_values("total_net").iloc[0]["date"])
    worst_diag = diag[diag["date"].eq(worst_date)].sort_values("total_net")

    lines = [
        "# CCUSDT TFI Worst-Day Frontier",
        "",
        f"Status: `{RUN_TAG}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decomposition",
        "",
        r"$$",
        r"R_5=\frac{P_5}{N_5},\quad \Delta_5=P_5-N_5,\quad E_5=P_5+N_5,\quad \rho_5=\frac{\Delta_5}{E_5+\epsilon}",
        r"$$",
        "",
        "`R5` is a shape ratio. `Delta5` is absolute cushion; `E5` is recent realized energy. A high ratio with low absolute cushion should not get the same risk budget as high ratio with large cushion.",
        "",
        "Target policy for this frontier:",
        "",
        r"$$",
        r"(\gamma_{00},\gamma_{10},\gamma_{01},\gamma_{11})=(0,0.75,0.25,4)",
        r"$$",
        "",
        "## Baseline",
        "",
        *markdown_table(pd.DataFrame([base]), ["gate", "test_days", "positive_days", "entries", "exposure", "total_net", "mean_net", "worst_day_net", "daily_cvar20", "max_drawdown"], 1),
        "",
        "## Best Worst-Day Frontier",
        "",
        *markdown_table(best_worst, ["gate", "test_days", "positive_days", "entries", "exposure", "total_net", "mean_net", "worst_day_net", "daily_cvar20", "max_drawdown"], 12),
        "",
        "## Balanced Frontier",
        "",
        *markdown_table(best_balanced, ["gate", "test_days", "positive_days", "entries", "exposure", "total_net", "mean_net", "worst_day_net", "daily_cvar20", "max_drawdown", "frontier_score"], 12),
        "",
        f"## Worst Date Diagnostics: {worst_date}",
        "",
        *markdown_table(worst_diag, ["date", "cell", "entries", "exposure", "total_net", "mean_net", "mean_closed5_delta", "mean_closed5_energy", "mean_closed5_rho", "low_abs_cushion_share", "low_energy_share", "high_recent_loss_share"], 12),
        "",
        "## Fragility Thresholds",
        "",
        *markdown_table(pd.DataFrame([thresholds]), list(thresholds.keys()), 1),
        "",
        "## Read",
        "",
        "The largest failure mode is not that `R5` is false; it is that `R5` has no absolute scale. The proposed next layer is therefore a risk-budget scaler based on `Delta5` and `E5`, not a replacement for the TFI state.",
        "",
        "## Outputs",
        "",
        f"- `{out_frontier_csv()}`",
        f"- `{out_daily_csv()}`",
        f"- `{out_diag_csv()}`",
        "",
    ]
    out_report_md().write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    df = add_closed_roll_stats(load_entries())
    active = add_fragility_flags(active_view(df, TARGET_POLICY))
    thresholds = active.attrs.get("fragility_thresholds", {})

    frontier_rows = []
    daily_parts = []
    for spec in gate_specs():
        row, daily = walk_forward_gate(active, spec)
        frontier_rows.append(row)
        daily_parts.append(daily)

    frontier = pd.DataFrame(frontier_rows).sort_values(["worst_day_net", "total_net"], ascending=[False, False])
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    diag = diagnostics(active)

    frontier.to_csv(out_frontier_csv(), index=False)
    daily.to_csv(out_daily_csv(), index=False)
    diag.to_csv(out_diag_csv(), index=False)
    write_report(frontier, daily, diag, thresholds)

    base = frontier[frontier["gate"].eq("no_extra_gate")].iloc[0]
    top = frontier.iloc[0]
    print(
        "[ccusdt_tfi_worst_day_frontier] "
        f"base_total={base['total_net']:.4f} base_worst={base['worst_day_net']:.4f} "
        f"top_gate={top['gate']} top_total={top['total_net']:.4f} top_worst={top['worst_day_net']:.4f} "
        f"report={out_report_md()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
