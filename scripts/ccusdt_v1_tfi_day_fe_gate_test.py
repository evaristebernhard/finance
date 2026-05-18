#!/usr/bin/env python
"""Day fixed-effect tests for CCUSDT TFI pre-trade gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_day_fe_gate_test_v1"
GUARDRAIL = "research_only_day_fixed_effect_gate_test_no_execution_recommendation_no_alpha_claim"
ROOT = Path(__file__).resolve().parents[1]
DATE_DIR = ROOT / "date"
DOC_DIR = ROOT / "docs" / "markets" / "ccusdt"
SCORED_ENTRIES = DATE_DIR / "ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv"


def out_coef_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_day_fe_gate_coefficients_{RUN_TAG}.csv"


def out_cells_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_day_fe_gate_cells_{RUN_TAG}.csv"


def out_permutation_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_day_fe_gate_permutation_{RUN_TAG}.csv"


def out_summary_json() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_day_fe_gate_summary_{RUN_TAG}.json"


def out_report_md() -> Path:
    return DOC_DIR / f"v1-tfi-day-fe-gate-test-{RUN_TAG}.md"


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


def load_oos() -> pd.DataFrame:
    df = pd.read_csv(SCORED_ENTRIES)
    oos = df[df["segment"].isin(["OOS_2026_05_16", "OOS_2026_05_17"])].copy()
    oos = oos[(pd.to_numeric(oos["weight"], errors="coerce") > 0) & pd.to_numeric(oos["net"], errors="coerce").notna()]
    oos["net"] = pd.to_numeric(oos["net"], errors="coerce")
    oos["weight"] = pd.to_numeric(oos["weight"], errors="coerce")
    oos["A_r5"] = oos["gate_r_n5"].astype(bool).astype(float)
    oos["B_frames_q90"] = oos["gate_frames_q90"].astype(bool).astype(float)
    oos["AB"] = oos["A_r5"] * oos["B_frames_q90"]
    oos["day_0517"] = oos["segment"].eq("OOS_2026_05_17").astype(float)
    return oos.sort_values(["segment", "entry_ts", "entry_row"]).reset_index(drop=True)


def design_matrix(df: pd.DataFrame, with_day_fe: bool = True, with_main_effects: bool = True) -> tuple[np.ndarray, list[str]]:
    cols = [np.ones(len(df))]
    names = ["intercept"]
    if with_day_fe:
        cols.append(df["day_0517"].to_numpy(dtype=float))
        names.append("day_0517")
    if with_main_effects:
        cols.append(df["A_r5"].to_numpy(dtype=float))
        names.append("A_r5")
        cols.append(df["B_frames_q90"].to_numpy(dtype=float))
        names.append("B_frames_q90")
    cols.append(df["AB"].to_numpy(dtype=float))
    names.append("A_x_B")
    return np.column_stack(cols), names


def weighted_lstsq(
    y: np.ndarray,
    X: np.ndarray,
    weights: np.ndarray,
    names: list[str],
) -> tuple[pd.DataFrame, np.ndarray]:
    ok = np.isfinite(y) & np.isfinite(weights) & (weights > 0) & np.isfinite(X).all(axis=1)
    y = y[ok]
    X = X[ok]
    weights = weights[ok]
    sw = np.sqrt(weights)
    Xw = X * sw[:, None]
    yw = y * sw
    beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    xtwx_inv = np.linalg.pinv(Xw.T @ Xw)

    # HC1 sandwich for WLS, using the weighted score x_i * w_i * e_i.
    meat = np.zeros((k, k), dtype=float)
    for xi, wi, ei in zip(X, weights, resid):
        score = xi[:, None] @ xi[None, :] * (wi * ei) ** 2
        meat += score
    hc1 = n / max(n - k, 1)
    cov = hc1 * xtwx_inv @ meat @ xtwx_inv
    se = np.sqrt(np.clip(np.diag(cov), 0, np.inf))
    tstat = beta / se
    out = pd.DataFrame(
        {
            "term": names,
            "coef_bps": beta,
            "robust_se_bps": se,
            "t_stat": tstat,
            "n": int(n),
            "weight_sum": float(weights.sum()),
        }
    )
    return out, beta


def cell_table(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for segment, gday in df.groupby("segment", sort=True):
        for a in [0.0, 1.0]:
            for b in [0.0, 1.0]:
                g = gday[(gday["A_r5"].eq(a)) & (gday["B_frames_q90"].eq(b))]
                if g.empty:
                    continue
                w = g["weight"].to_numpy(dtype=float)
                y = g["net"].to_numpy(dtype=float)
                wy = w * y
                rows.append(
                    {
                        "segment": segment,
                        "A_r5": int(a),
                        "B_frames_q90": int(b),
                        "entries": int(len(g)),
                        "exposure": float(w.sum()),
                        "total_net_bps": float(wy.sum()),
                        "weighted_mean_net_bps": safe_div(float(wy.sum()), float(w.sum())),
                        "weighted_gt2_rate": safe_div(float(w[y > 2.0].sum()), float(w.sum())),
                        "cost_hit_rate": safe_div(float(w[y <= 0.0].sum()), float(w.sum())),
                    }
                )
    out = pd.DataFrame(rows)
    combined: list[dict[str, Any]] = []
    for a in [0.0, 1.0]:
        for b in [0.0, 1.0]:
            g = df[(df["A_r5"].eq(a)) & (df["B_frames_q90"].eq(b))]
            if g.empty:
                continue
            w = g["weight"].to_numpy(dtype=float)
            y = g["net"].to_numpy(dtype=float)
            wy = w * y
            combined.append(
                {
                    "segment": "OOS_combined",
                    "A_r5": int(a),
                    "B_frames_q90": int(b),
                    "entries": int(len(g)),
                    "exposure": float(w.sum()),
                    "total_net_bps": float(wy.sum()),
                    "weighted_mean_net_bps": safe_div(float(wy.sum()), float(w.sum())),
                    "weighted_gt2_rate": safe_div(float(w[y > 2.0].sum()), float(w.sum())),
                    "cost_hit_rate": safe_div(float(w[y <= 0.0].sum()), float(w.sum())),
                }
            )
    return pd.concat([out, pd.DataFrame(combined)], ignore_index=True)


def day_fe_did_from_cells(cells: pd.DataFrame) -> dict[str, float]:
    vals: dict[str, float] = {}
    dids = []
    weights = []
    for segment in ["OOS_2026_05_16", "OOS_2026_05_17", "OOS_combined"]:
        sub = cells[cells["segment"].eq(segment)]
        lookup = {
            (int(row["A_r5"]), int(row["B_frames_q90"])): float(row["weighted_mean_net_bps"])
            for _, row in sub.iterrows()
        }
        if all(key in lookup for key in [(1, 1), (1, 0), (0, 1), (0, 0)]):
            did = lookup[(1, 1)] - lookup[(1, 0)] - lookup[(0, 1)] + lookup[(0, 0)]
            vals[f"did_{segment}"] = did
            if segment != "OOS_combined":
                exp11 = float(sub[(sub["A_r5"].eq(1)) & (sub["B_frames_q90"].eq(1))]["exposure"].iloc[0])
                dids.append(did)
                weights.append(exp11)
    vals["did_day_fe_weighted_by_ab_exposure"] = float(np.average(dids, weights=weights)) if dids else np.nan
    return vals


def permutation_test(df: pd.DataFrame, observed_beta: float, n_perm: int = 5000, seed: int = 7) -> tuple[pd.DataFrame, dict[str, float]]:
    rng = np.random.default_rng(seed)
    X, names = design_matrix(df, with_day_fe=True, with_main_effects=True)
    weights = df["weight"].to_numpy(dtype=float)
    y0 = df["net"].to_numpy(dtype=float)
    beta_idx = names.index("A_x_B")
    rows = []
    perm_betas = np.empty(n_perm, dtype=float)
    day_arrays = {day: idx.to_numpy() for day, idx in df.groupby("segment").groups.items()}
    for i in range(n_perm):
        y = y0.copy()
        for idx in day_arrays.values():
            y[idx] = rng.permutation(y[idx])
        _, beta = weighted_lstsq(y, X, weights, names)
        perm_betas[i] = beta[beta_idx]
    p_right = (1.0 + float(np.sum(perm_betas >= observed_beta))) / (n_perm + 1.0)
    p_two = (1.0 + float(np.sum(np.abs(perm_betas) >= abs(observed_beta)))) / (n_perm + 1.0)
    rows.append(
        {
            "test": "within_day_shuffle_y",
            "n_perm": n_perm,
            "observed_beta_A_x_B": observed_beta,
            "perm_mean": float(np.mean(perm_betas)),
            "perm_std": float(np.std(perm_betas, ddof=1)),
            "perm_p95": float(np.quantile(perm_betas, 0.95)),
            "perm_p99": float(np.quantile(perm_betas, 0.99)),
            "p_right_tail": p_right,
            "p_two_sided": p_two,
            "seed": seed,
        }
    )
    return pd.DataFrame(rows), {"p_right_tail": p_right, "p_two_sided": p_two}


def write_report(
    coeffs: pd.DataFrame,
    cells: pd.DataFrame,
    permutation: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    fe = coeffs[coeffs["model"].eq("day_fe_main_interaction")]
    nofe = coeffs[coeffs["model"].eq("no_day_fe_main_interaction")]
    ab = fe[fe["term"].eq("A_x_B")].iloc[0]
    lines = [
        "# CCUSDT TFI Gate Day Fixed-Effect Test",
        "",
        f"Status: `{RUN_TAG}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "Test target:",
        "",
        r"$$",
        r"Y_{d,i}=\alpha_d+\beta_A A_{d,i}+\beta_B B_{d,i}+\beta_{AB}A_{d,i}B_{d,i}+\varepsilon_{d,i}.",
        r"$$",
        "",
        r"Here \(A=\mathbf{1}\{R_5>1\}\), \(B=\mathbf{1}\{frames\_since\_mid\_change\ge q90\}\). The regression is WLS using the locked strategy exposure weight.",
        "",
        "## Coefficients",
        "",
        *markdown_table(
            fe,
            ["model", "term", "coef_bps", "robust_se_bps", "t_stat", "n", "weight_sum"],
            max_rows=10,
        ),
        "",
        "No-day-FE reference:",
        "",
        *markdown_table(
            nofe,
            ["model", "term", "coef_bps", "robust_se_bps", "t_stat", "n", "weight_sum"],
            max_rows=10,
        ),
        "",
        "## 2x2 Cells",
        "",
        *markdown_table(
            cells.sort_values(["segment", "A_r5", "B_frames_q90"]),
            [
                "segment",
                "A_r5",
                "B_frames_q90",
                "entries",
                "exposure",
                "total_net_bps",
                "weighted_mean_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
            ],
            max_rows=20,
        ),
        "",
        "## Permutation Check",
        "",
        "Null: within each day, the future net labels are exchangeable with respect to the gates. This preserves day-level distribution and gate counts, and asks whether the observed interaction is unusually high.",
        "",
        *markdown_table(
            permutation,
            [
                "test",
                "n_perm",
                "observed_beta_A_x_B",
                "perm_mean",
                "perm_std",
                "perm_p95",
                "perm_p99",
                "p_right_tail",
                "p_two_sided",
            ],
        ),
        "",
        "## Read",
        "",
        f"- Day-FE interaction beta: `{fmt(ab['coef_bps'])}` bps.",
        f"- Robust t-stat: `{fmt(ab['t_stat'])}`.",
        f"- Within-day permutation right-tail p-value: `{fmt(float(permutation['p_right_tail'].iloc[0]))}`.",
        f"- Cell DiD, combined: `{fmt(summary['did']['did_OOS_combined'])}` bps; day-FE exposure-weighted day DiD: `{fmt(summary['did']['did_day_fe_weighted_by_ab_exposure'])}` bps.",
        "",
        summary["interpretation"],
        "",
        "## Outputs",
        "",
        f"- `{out_coef_csv()}`",
        f"- `{out_cells_csv()}`",
        f"- `{out_permutation_csv()}`",
        f"- `{out_summary_json()}`",
        "",
    ]
    out_report_md().write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    df = load_oos()
    cells = cell_table(df)

    coef_rows = []
    for model_name, with_day_fe in [
        ("day_fe_main_interaction", True),
        ("no_day_fe_main_interaction", False),
        ("day_fe_interaction_only", True),
    ]:
        with_main = model_name != "day_fe_interaction_only"
        X, names = design_matrix(df, with_day_fe=with_day_fe, with_main_effects=with_main)
        coefs, beta = weighted_lstsq(
            df["net"].to_numpy(dtype=float),
            X,
            df["weight"].to_numpy(dtype=float),
            names,
        )
        coefs.insert(0, "model", model_name)
        coef_rows.append(coefs)
    coeffs = pd.concat(coef_rows, ignore_index=True)
    observed_ab = float(
        coeffs[(coeffs["model"].eq("day_fe_main_interaction")) & (coeffs["term"].eq("A_x_B"))]["coef_bps"].iloc[0]
    )
    permutation, pvals = permutation_test(df, observed_ab)
    did = day_fe_did_from_cells(cells)

    if observed_ab > 0 and pvals["p_right_tail"] <= 0.05:
        interpretation = (
            "Result: the interaction survives day fixed effects and is high relative to within-day shuffled labels. "
            "This supports the state-conditioned interpretation over a pure day effect explanation, with the caveat that OOS has only two days and the strict cell has low count."
        )
    elif observed_ab > 0:
        interpretation = (
            "Result: the interaction remains positive after day fixed effects, but permutation evidence is not strong enough for a hard statistical claim. "
            "Treat it as a promising local-state effect that needs more OOS days."
        )
    else:
        interpretation = (
            "Result: the interaction does not survive day fixed effects. The strict gate may be mostly day composition rather than local state."
        )

    summary = {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "n_entries": int(len(df)),
        "weight_sum": float(df["weight"].sum()),
        "formula": "Y_di = alpha_d + beta_A A_di + beta_B B_di + beta_AB A_di B_di + epsilon_di",
        "observed_beta_A_x_B_day_fe_bps": observed_ab,
        "did": did,
        "permutation": permutation.iloc[0].to_dict(),
        "interpretation": interpretation,
        "outputs": {
            "coef_csv": str(out_coef_csv()),
            "cells_csv": str(out_cells_csv()),
            "permutation_csv": str(out_permutation_csv()),
            "summary_json": str(out_summary_json()),
            "report_md": str(out_report_md()),
        },
    }

    coeffs.to_csv(out_coef_csv(), index=False)
    cells.to_csv(out_cells_csv(), index=False)
    permutation.to_csv(out_permutation_csv(), index=False)
    out_summary_json().write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(coeffs, cells, permutation, summary)
    print(
        "[ccusdt_tfi_day_fe_gate_test] "
        f"n={len(df)} beta_ab={observed_ab:.4f} "
        f"p_right={float(permutation['p_right_tail'].iloc[0]):.4f} report={out_report_md()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
