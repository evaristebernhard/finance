#!/usr/bin/env python
"""Interpretable grid optimization and Pareto frontier for CCUSDT TFI states."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1"
GUARDRAIL = "research_only_interpretable_grid_walk_forward_pareto_no_execution_recommendation_no_alpha_claim"
COST_MODE = "stored_net"
ROOT = Path(__file__).resolve().parents[1]
DATE_DIR = ROOT / "date"
DOC_DIR = ROOT / "docs" / "markets" / "ccusdt"
SCORED_ENTRIES = DATE_DIR / "ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv"

EPS = 1e-9
MIN_TRAIN_DAYS = 5

GAMMA10_GRID = [0.50, 0.75, 1.00, 1.25]
GAMMA01_GRID = [0.00, 0.25, 0.50, 0.75]
GAMMA11_GRID = [2.00, 3.00, 4.00, 5.00]
STRENGTH_METRICS = ["closed5_delta", "closed5_score_abs", "closed10_delta", "closed10_score_abs"]


@dataclass(frozen=True)
class StrengthSpec:
    kind: str
    metric: str = "none"
    q_low: float = np.nan
    q_high: float = np.nan
    floor: float = 1.0

    @property
    def name(self) -> str:
        if self.kind == "none":
            return "strength_none"
        if self.kind == "hard":
            return f"hard_{self.metric}_ge_q{self.q_low:g}"
        return f"ramp_{self.metric}_q{self.q_low:g}_{self.q_high:g}_floor{self.floor:g}"


@dataclass(frozen=True)
class LossSpec:
    kind: str
    metric: str = "closed5_loss_abs_max"
    q_low: float = np.nan
    q_high: float = np.nan
    eta: float = 0.0
    floor: float = 1.0

    @property
    def name(self) -> str:
        if self.kind == "none":
            return "loss_none"
        return f"loss_soft_{self.metric}_q{self.q_low:g}_{self.q_high:g}_eta{self.eta:g}_floor{self.floor:g}"


@dataclass(frozen=True)
class Candidate:
    gamma10: float
    gamma01: float
    gamma11: float
    strength: StrengthSpec
    loss: LossSpec

    @property
    def variant_id(self) -> str:
        return (
            f"g00_0_g10_{self.gamma10:g}_g01_{self.gamma01:g}_g11_{self.gamma11:g}"
            f"__{self.strength.name}__{self.loss.name}"
        )


def out_variants_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_interpretable_grid_variants_{RUN_TAG}.csv"


def out_pareto_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_interpretable_grid_pareto_{RUN_TAG}.csv"


def out_daily_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_interpretable_grid_daily_top_{RUN_TAG}.csv"


def out_report_md() -> Path:
    return DOC_DIR / f"v1-tfi-interpretable-grid-pareto-{RUN_TAG}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--scored-entries", default=str(SCORED_ENTRIES))
    parser.add_argument(
        "--cost-mode",
        choices=["stored_net", "zero_fee"],
        default=COST_MODE,
        help="stored_net uses the scored-entry net labels; zero_fee uses gross labels and recomputes R5 cells.",
    )
    return parser.parse_args()


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


def recompute_r5_gate(df: pd.DataFrame, net_col: str = "net") -> pd.Series:
    work = df.reset_index(drop=False).rename(columns={"index": "_orig_index"}).copy()
    work["_row_key"] = np.arange(len(work), dtype="int64")
    closed = work.sort_values(["label_available_ts", "entry_row"]).reset_index(drop=True)
    timeline = work.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)
    net_by_key = pd.to_numeric(work[net_col], errors="coerce").to_numpy(dtype=float)
    gates = np.zeros(len(work), dtype=bool)
    available_keys: list[int] = []
    close_ptr = 0
    for _, current in timeline.iterrows():
        entry_ts = float(current["entry_ts"])
        while close_ptr < len(closed) and float(closed.loc[close_ptr, "label_available_ts"]) < entry_ts:
            available_keys.append(int(closed.loc[close_ptr, "_row_key"]))
            close_ptr += 1
        vals = net_by_key[np.asarray(available_keys[-5:], dtype=int)] if available_keys else np.asarray([], dtype=float)
        vals = vals[np.isfinite(vals)]
        pos = float(np.sum(vals[vals > 0.0])) if len(vals) else 0.0
        neg_abs = float(-np.sum(vals[vals < 0.0])) if len(vals) else 0.0
        gates[int(current["_row_key"])] = safe_div(pos, neg_abs) >= 1.0
    return pd.Series(gates, index=df.index)


def load_entries(scored_entries: Path = SCORED_ENTRIES, cost_mode: str = COST_MODE) -> pd.DataFrame:
    df = pd.read_csv(scored_entries)
    df = df[(pd.to_numeric(df["weight"], errors="coerce") > 0) & pd.to_numeric(df["net"], errors="coerce").notna()].copy()
    for col in ["net", "gross", "cost", "weight", "entry_ts", "entry_row", "label_available_ts"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["source_net"] = df["net"]
    df["source_cost"] = df["cost"]
    df["cost_mode"] = cost_mode
    if cost_mode == "zero_fee":
        df["net"] = df["gross"]
        df["cost"] = 0.0
        df["weighted_net"] = pd.to_numeric(df["weight"], errors="coerce") * df["net"]
        df["gate_r_n5"] = recompute_r5_gate(df, "net")
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
    df["trade_universe"] = df["cell"].ne("00_none")
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
            stats[f"{key}_pos_sum"][idx] = pos
            stats[f"{key}_neg_abs_sum"][idx] = neg
            stats[f"{key}_delta"][idx] = delta
            stats[f"{key}_energy"][idx] = energy
            stats[f"{key}_ratio"][idx] = safe_div(pos, neg)
            stats[f"{key}_rho"][idx] = safe_div(delta, energy)
            stats[f"{key}_mean"][idx] = float(np.mean(vals))
            stats[f"{key}_min"][idx] = float(np.min(vals))
            stats[f"{key}_loss_abs_max"][idx] = float(np.max(np.maximum(-vals, 0.0)))
            stats[f"{key}_score_abs"][idx] = safe_div(delta, np.sqrt(energy + EPS))

    for col, values in stats.items():
        out[col] = values
    return out


def build_candidates() -> list[Candidate]:
    strength_specs: list[StrengthSpec] = [StrengthSpec("none")]
    for metric in STRENGTH_METRICS:
        for q in [0.10, 0.20, 0.30, 0.40]:
            strength_specs.append(StrengthSpec("hard", metric=metric, q_low=q, floor=0.0))
        for q_low in [0.10, 0.20, 0.30]:
            for q_high in [0.50]:
                for floor in [0.0, 0.25, 0.50]:
                    strength_specs.append(StrengthSpec("ramp", metric=metric, q_low=q_low, q_high=q_high, floor=floor))

    loss_specs: list[LossSpec] = [LossSpec("none")]
    for eta in [0.50, 1.00]:
        for floor in [0.25, 0.50]:
            loss_specs.append(
                LossSpec("soft", metric="closed5_loss_abs_max", q_low=0.75, q_high=0.90, eta=eta, floor=floor)
            )

    candidates = []
    for gamma10 in GAMMA10_GRID:
        for gamma01 in GAMMA01_GRID:
            for gamma11 in GAMMA11_GRID:
                for strength in strength_specs:
                    for loss in loss_specs:
                        candidates.append(Candidate(gamma10, gamma01, gamma11, strength, loss))
    return candidates


def quantile(series: pd.Series, q: float) -> float:
    vals = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(vals.quantile(q)) if len(vals) else np.nan


def threshold_map(df: pd.DataFrame, dates: list[str]) -> dict[tuple[str, str, float], float]:
    out: dict[tuple[str, str, float], float] = {}
    metrics = set(STRENGTH_METRICS + ["closed5_loss_abs_max"])
    quantiles = {0.10, 0.20, 0.30, 0.40, 0.50, 0.75, 0.90}
    for i, date in enumerate(dates):
        if i < MIN_TRAIN_DAYS:
            continue
        train_dates = dates[:i]
        train = df[df["date"].isin(train_dates) & df["trade_universe"]].copy()
        for metric in metrics:
            for q in quantiles:
                out[(date, metric, q)] = quantile(train[metric], q)
    return out


def gamma_for_candidate(cell: pd.Series, cand: Candidate) -> np.ndarray:
    return np.select(
        [cell.eq("11_r5_frames"), cell.eq("10_r5_only"), cell.eq("01_frames_only")],
        [cand.gamma11, cand.gamma10, cand.gamma01],
        default=0.0,
    ).astype(float)


def strength_scale(test: pd.DataFrame, cand: Candidate, date: str, thresholds: dict[tuple[str, str, float], float]) -> np.ndarray:
    spec = cand.strength
    if spec.kind == "none":
        return np.ones(len(test), dtype=float)
    vals = pd.to_numeric(test[spec.metric], errors="coerce").to_numpy(dtype=float)
    low = thresholds.get((date, spec.metric, float(spec.q_low)), np.nan)
    if not np.isfinite(low):
        return np.zeros(len(test), dtype=float)
    if spec.kind == "hard":
        return np.where(np.isfinite(vals) & (vals >= low), 1.0, 0.0)
    high = thresholds.get((date, spec.metric, float(spec.q_high)), np.nan)
    if not np.isfinite(high) or high <= low + EPS:
        return np.where(np.isfinite(vals) & (vals >= low), 1.0, spec.floor)
    raw = np.clip((vals - low) / (high - low), 0.0, 1.0)
    raw = np.where(np.isfinite(raw), raw, 0.0)
    return spec.floor + (1.0 - spec.floor) * raw


def loss_scale(test: pd.DataFrame, cand: Candidate, date: str, thresholds: dict[tuple[str, str, float], float]) -> np.ndarray:
    spec = cand.loss
    if spec.kind == "none":
        return np.ones(len(test), dtype=float)
    vals = pd.to_numeric(test[spec.metric], errors="coerce").to_numpy(dtype=float)
    low = thresholds.get((date, spec.metric, float(spec.q_low)), np.nan)
    high = thresholds.get((date, spec.metric, float(spec.q_high)), np.nan)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low + EPS:
        return np.ones(len(test), dtype=float)
    stress = np.clip((vals - low) / (high - low), 0.0, 1.0)
    stress = np.where(np.isfinite(stress), stress, 0.0)
    return np.clip(1.0 - spec.eta * stress, spec.floor, 1.0)


def evaluate_candidate(
    df: pd.DataFrame,
    dates: list[str],
    thresholds: dict[tuple[str, str, float], float],
    cand: Candidate,
    keep_daily: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    daily_rows: list[dict[str, Any]] = []
    entry_pnls: list[np.ndarray] = []
    for i, date in enumerate(dates):
        if i < MIN_TRAIN_DAYS:
            continue
        test = df[df["date"].eq(date)].copy()
        gamma = gamma_for_candidate(test["cell"], cand)
        base_exposure = test["weight"].to_numpy(dtype=float) * gamma
        scale = strength_scale(test, cand, date, thresholds) * loss_scale(test, cand, date, thresholds)
        exposure = base_exposure * scale
        net = test["net"].to_numpy(dtype=float)
        pnl = exposure * net
        active = np.isfinite(pnl) & np.isfinite(exposure) & (exposure > 0)
        entry_pnls.append(pnl[active])
        daily_rows.append(
            {
                "variant_id": cand.variant_id,
                "date": date,
                "entries": int(np.sum(active)),
                "exposure": float(np.sum(exposure[active])),
                "total_net": float(np.sum(pnl[active])),
                "mean_net": safe_div(float(np.sum(pnl[active])), float(np.sum(exposure[active]))),
            }
        )

    daily_net = np.asarray([row["total_net"] for row in daily_rows], dtype=float)
    daily_exposure = np.asarray([row["exposure"] for row in daily_rows], dtype=float)
    pnls = np.concatenate(entry_pnls) if entry_pnls else np.array([], dtype=float)
    row = {
        "variant_id": cand.variant_id,
        "gamma00": 0.0,
        "gamma10": cand.gamma10,
        "gamma01": cand.gamma01,
        "gamma11": cand.gamma11,
        "strength_kind": cand.strength.kind,
        "strength_metric": cand.strength.metric,
        "strength_q_low": cand.strength.q_low,
        "strength_q_high": cand.strength.q_high,
        "strength_floor": cand.strength.floor,
        "loss_kind": cand.loss.kind,
        "loss_metric": cand.loss.metric,
        "loss_q_low": cand.loss.q_low,
        "loss_q_high": cand.loss.q_high,
        "loss_eta": cand.loss.eta,
        "loss_floor": cand.loss.floor,
        "test_days": int(len(daily_rows)),
        "positive_days": int(np.sum(daily_net > 0.0)),
        "entries": int(sum(row["entries"] for row in daily_rows)),
        "exposure": float(np.sum(daily_exposure)),
        "total_net": float(np.sum(daily_net)),
        "mean_net": safe_div(float(np.sum(daily_net)), float(np.sum(daily_exposure))),
        "worst_day_net": float(np.min(daily_net)) if len(daily_net) else np.nan,
        "daily_cvar20": cvar(daily_net, 0.20),
        "max_drawdown": max_drawdown(daily_net),
        "entry_worst_pnl": float(np.min(pnls)) if len(pnls) else np.nan,
        "entry_cvar05": cvar(pnls, 0.05),
    }
    row["risk_score"] = (
        row["total_net"]
        + 8.0 * min(row["worst_day_net"], 0.0)
        + 4.0 * min(row["daily_cvar20"], 0.0)
        + 2.0 * min(row["max_drawdown"], 0.0)
    )
    return row, daily_rows if keep_daily else []


def pareto_total_worst(df: pd.DataFrame) -> pd.DataFrame:
    work = df[(df["total_net"] > 0) & (df["entries"] > 0)].copy()
    work = work.sort_values(["total_net", "worst_day_net"], ascending=[False, False]).reset_index(drop=True)
    best_worst = -np.inf
    keep = []
    for _, row in work.iterrows():
        worst = float(row["worst_day_net"])
        if worst > best_worst + EPS:
            keep.append(True)
            best_worst = worst
        else:
            keep.append(False)
    out = work.loc[keep].copy()
    out["pareto_rank_total_desc"] = np.arange(1, len(out) + 1)
    return out


def selected_daily(variants: pd.DataFrame, df: pd.DataFrame, dates: list[str], thresholds: dict[tuple[str, str, float], float]) -> pd.DataFrame:
    top_ids = set()
    for source in [
        variants.sort_values("risk_score", ascending=False).head(12),
        variants.sort_values("total_net", ascending=False).head(12),
        variants.sort_values("worst_day_net", ascending=False).head(12),
    ]:
        top_ids.update(source["variant_id"].tolist())
    rows = []
    candidates = {cand.variant_id: cand for cand in build_candidates()}
    for variant_id in sorted(top_ids):
        cand = candidates[variant_id]
        _, daily_rows = evaluate_candidate(df, dates, thresholds, cand, keep_daily=True)
        rows.extend(daily_rows)
    return pd.DataFrame(rows)


def write_report(variants: pd.DataFrame, pareto: pd.DataFrame, daily: pd.DataFrame, cost_mode: str, scored_entries: Path) -> None:
    old = variants[
        variants["variant_id"].str.startswith("g00_0_g10_0.75_g01_0.25_g11_4__strength_none__loss_none")
    ]
    old_row = old.iloc[0] if not old.empty else variants.iloc[0]
    best_score = variants.sort_values("risk_score", ascending=False).head(15)
    best_total = variants.sort_values("total_net", ascending=False).head(12)
    best_worst = variants.sort_values(["worst_day_net", "total_net"], ascending=[False, False]).head(12)
    compact_pareto = pareto.head(20)
    best_score_row = best_score.iloc[0]
    best_worst_row = best_worst.iloc[0]

    lines = [
        "# CCUSDT TFI Interpretable Grid Pareto",
        "",
        f"Status: `{RUN_TAG}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        f"Cost mode: `{cost_mode}`.",
        "",
        f"Scored entries: `{scored_entries}`.",
        "",
        "For the full zero-fee pipeline, first regenerate the scored entries with `ccusdt_v1_tfi_pretrade_identification.py --cost-mode zero_fee`, then run this Pareto script with `--scored-entries <that file> --cost-mode stored_net`. In that mode, `stored_net` already means the upstream label is `net := gross` and `cost := 0`, with rolling detectors and `R5` recomputed upstream.",
        "",
        "This models the current Bullish CC/USDT promotional fee assumption only; it does not prove fill, latency, queue, or adverse-selection costs are zero.",
        "",
        "## Model Family",
        "",
        r"$$",
        r"w_t=b_t\cdot\gamma_{A_tB_t}\cdot\psi_t\cdot\phi_t",
        r"$$",
        "",
        r"$$",
        r"A_t=\mathbf{1}\{R_5>1\},\quad B_t=\mathbf{1}\{F_t\ge q_{90}\}",
        r"$$",
        "",
        "Strength scaler:",
        "",
        r"$$",
        r"\psi_t\in\left\{1,\ \mathbf{1}\{M_t\ge Q_q^{train}(M)\},\ \psi_{\min}+(1-\psi_{\min})\operatorname{clip}\frac{M_t-Q_l^{train}}{Q_h^{train}-Q_l^{train}}\right\}",
        r"$$",
        "",
        "Recent-loss suppressor:",
        "",
        r"$$",
        r"\phi_t=\operatorname{clip}\left(1-\eta\operatorname{clip}\frac{L_t-Q_{75}^{train}(L)}{Q_{90}^{train}(L)-Q_{75}^{train}(L)},\phi_{\min},1\right)",
        r"$$",
        "",
        "Every train quantile is estimated only from prior dates in the main trading universe \\((A_t\\lor B_t)\\).",
        "",
        "## Main Read",
        "",
        f"Old anchor total `{fmt(old_row['total_net'])}`, worst day `{fmt(old_row['worst_day_net'])}`, positive days `{int(old_row['positive_days'])}`.",
        f"Risk-score leader `{best_score_row['variant_id']}`: total `{fmt(best_score_row['total_net'])}`, mean `{fmt(best_score_row['mean_net'])}`, worst day `{fmt(best_score_row['worst_day_net'])}`, positive days `{int(best_score_row['positive_days'])}`.",
        f"Worst-day leader `{best_worst_row['variant_id']}`: total `{fmt(best_worst_row['total_net'])}`, mean `{fmt(best_worst_row['mean_net'])}`, worst day `{fmt(best_worst_row['worst_day_net'])}`.",
        "",
        "The frontier is still a sizing and selection research surface. `C=0` only removes the explicit fee/cost label from this replay; it does not remove spread crossing, fill probability, latency, or adverse-selection risk from a live implementation.",
        "",
        "## Old Main Policy Anchor",
        "",
        *markdown_table(
            pd.DataFrame([old_row]),
            [
                "variant_id",
                "gamma10",
                "gamma01",
                "gamma11",
                "total_net",
                "mean_net",
                "worst_day_net",
                "daily_cvar20",
                "max_drawdown",
                "positive_days",
                "entries",
            ],
            1,
        ),
        "",
        "## Risk-Score Leaders",
        "",
        *markdown_table(
            best_score,
            [
                "variant_id",
                "gamma10",
                "gamma01",
                "gamma11",
                "strength_kind",
                "strength_metric",
                "strength_q_low",
                "strength_floor",
                "loss_kind",
                "loss_eta",
                "total_net",
                "mean_net",
                "worst_day_net",
                "daily_cvar20",
                "max_drawdown",
                "positive_days",
                "risk_score",
            ],
            15,
        ),
        "",
        "## Total Leaders",
        "",
        *markdown_table(
            best_total,
            ["variant_id", "total_net", "mean_net", "worst_day_net", "daily_cvar20", "max_drawdown", "positive_days", "exposure"],
            12,
        ),
        "",
        "## Worst-Day Leaders",
        "",
        *markdown_table(
            best_worst,
            ["variant_id", "total_net", "mean_net", "worst_day_net", "daily_cvar20", "max_drawdown", "positive_days", "exposure"],
            12,
        ),
        "",
        "## Pareto Frontier: Total vs Worst Day",
        "",
        *markdown_table(
            compact_pareto,
            [
                "pareto_rank_total_desc",
                "variant_id",
                "total_net",
                "mean_net",
                "worst_day_net",
                "daily_cvar20",
                "max_drawdown",
                "positive_days",
                "exposure",
            ],
            20,
        ),
        "",
        "## Read",
        "",
        "This is an interpretable frontier, not a black-box model. The old coefficient vector is included as an anchor, but the frontier lets the absolute-strength scaler and recent-loss suppressor compete jointly with the four state gammas.",
        "",
        "## Outputs",
        "",
        f"- `{out_variants_csv()}`",
        f"- `{out_pareto_csv()}`",
        f"- `{out_daily_csv()}`",
        "",
    ]
    out_report_md().write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    args = parse_args()
    global RUN_TAG, COST_MODE, SCORED_ENTRIES
    RUN_TAG = args.run_tag
    COST_MODE = args.cost_mode
    SCORED_ENTRIES = Path(args.scored_entries)
    if not SCORED_ENTRIES.is_absolute():
        SCORED_ENTRIES = ROOT / SCORED_ENTRIES

    df = add_closed_roll_stats(load_entries(SCORED_ENTRIES, COST_MODE))
    dates = sorted(df["date"].unique().tolist())
    thresholds = threshold_map(df, dates)
    candidates = build_candidates()

    rows = []
    for i, cand in enumerate(candidates, start=1):
        row, _ = evaluate_candidate(df, dates, thresholds, cand, keep_daily=False)
        rows.append(row)
        if i % 2500 == 0:
            print(f"[grid] evaluated {i}/{len(candidates)}", flush=True)

    variants = pd.DataFrame(rows)
    pareto = pareto_total_worst(variants)
    daily = selected_daily(variants, df, dates, thresholds)

    variants.sort_values("risk_score", ascending=False).to_csv(out_variants_csv(), index=False)
    pareto.to_csv(out_pareto_csv(), index=False)
    daily.to_csv(out_daily_csv(), index=False)
    write_report(variants, pareto, daily, COST_MODE, SCORED_ENTRIES)

    old = variants[
        variants["variant_id"].str.startswith("g00_0_g10_0.75_g01_0.25_g11_4__strength_none__loss_none")
    ].iloc[0]
    best = variants.sort_values("risk_score", ascending=False).iloc[0]
    top_pareto = pareto.iloc[0]
    print(
        "[ccusdt_tfi_interpretable_grid_pareto] "
        f"candidates={len(variants)} pareto={len(pareto)} "
        f"old_total={old['total_net']:.4f} old_worst={old['worst_day_net']:.4f} "
        f"best_score_total={best['total_net']:.4f} best_score_worst={best['worst_day_net']:.4f} "
        f"top_pareto_total={top_pareto['total_net']:.4f} top_pareto_worst={top_pareto['worst_day_net']:.4f} "
        f"report={out_report_md()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
