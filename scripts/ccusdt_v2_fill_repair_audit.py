#!/usr/bin/env python
"""CCUSDT V2 fill-aware repair and completion audit.

This script does not create a trading rule. It audits the active CCUSDT
research objective against current artifacts and runs a post-hoc diagnostic over
the practical incremental-L2 queue-fill scenario to see whether simple
entry-time filters could plausibly repair execution economics.

Any filter selected here is validation-side and therefore not promotable. A
positive row would only define the next walk-forward experiment.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_fill_repair_audit_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_fill_repair_audit_v1"
FRAMEWORK_RUN_TAG = "20260518_ccusdt_v2_framework_v1"
L2_QUEUE_RUN_TAG = "20260518_ccusdt_v2_l2_queue_fill_v1"
TAKER_RUN_TAG = "20260518_ccusdt_v2_taker_fallback_audit_v1"
DECOMP_RUN_TAG = "20260518_ccusdt_v2_execution_failure_decomp_v1"
QUEUE_RELEASE_RUN_TAG = "20260518_ccusdt_v2_queue_release_pivot_fast_v1"
LIQUIDITY_ENVELOPE_RUN_TAG = "20260518_ccusdt_v2_liquidity_envelope_audit_v1"

PRACTICAL_SCENARIO = {
    "latency_ms": 250.0,
    "fill_timeout_ms": 5000.0,
    "order_notional_quote": 100.0,
    "fee_stress_bps": 2.0,
}

FILTER_FEATURES = [
    "entry_quality_score",
    "feature_value",
    "abs_feature_value",
    "entry_spread_bps",
    "trade_window_count",
    "frames_since_mid_change",
    "past_event_25_bps",
    "abs_past_event_25_bps",
    "microprice_dev_bps",
    "signed_microprice_dev_bps",
    "queue_imbalance_1",
    "signed_queue_imbalance_1",
    "queue_imbalance_5",
    "signed_queue_imbalance_5",
    "mlofi_roll10_l1",
    "signed_mlofi_roll10_l1",
    "mlofi_roll10_l25",
    "signed_mlofi_roll10_l25",
    "batch_rows",
    "hour_bucket",
]


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    framework_run_tag: str
    l2_queue_run_tag: str
    taker_run_tag: str
    decomp_run_tag: str
    queue_release_run_tag: str
    liquidity_envelope_run_tag: str
    run_tag: str

    @property
    def entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_quote_transition_labels_{self.framework_run_tag}.csv"

    @property
    def framework_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_scorecard_{self.framework_run_tag}.csv"

    @property
    def l2_queue_events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_events_{self.l2_queue_run_tag}.csv"

    @property
    def l2_queue_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_scorecard_{self.l2_queue_run_tag}.csv"

    @property
    def taker_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_taker_fallback_scorecard_{self.taker_run_tag}.csv"

    @property
    def decomp_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_execution_failure_decomposition_{self.decomp_run_tag}.csv"

    @property
    def queue_release_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_queue_release_scorecard_{self.queue_release_run_tag}.csv"

    @property
    def liquidity_envelope_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_liquidity_envelope_scorecard_{self.liquidity_envelope_run_tag}.csv"

    @property
    def repair_filters_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_fill_repair_filters_{self.run_tag}.csv"

    @property
    def repair_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_fill_repair_scorecard_{self.run_tag}.csv"

    @property
    def audit_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_goal_completion_audit_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-goal-completion-audit-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 fill repair and completion audit.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--framework-run-tag", default=FRAMEWORK_RUN_TAG)
    parser.add_argument("--l2-queue-run-tag", default=L2_QUEUE_RUN_TAG)
    parser.add_argument("--taker-run-tag", default=TAKER_RUN_TAG)
    parser.add_argument("--decomp-run-tag", default=DECOMP_RUN_TAG)
    parser.add_argument("--queue-release-run-tag", default=QUEUE_RELEASE_RUN_TAG)
    parser.add_argument("--liquidity-envelope-run-tag", default=LIQUIDITY_ENVELOPE_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--min-signals", type=int, default=30)
    parser.add_argument("--quantiles", default="0.2,0.4,0.6,0.8")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_floats(raw: str) -> list[float]:
    return fill_base.parse_floats(raw)


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    return fill_base.finite_mean(values)


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    return fill_base.finite_quantile(values, q)


def safe_rate(values: Iterable[bool] | np.ndarray) -> float:
    return fill_base.safe_rate(values)


def fmt_num(value: object, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def read_inputs(
    paths: Paths,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    entries = pd.read_csv(paths.entries_csv)
    framework_scorecard = pd.read_csv(paths.framework_scorecard_csv)
    l2_events = pd.read_csv(paths.l2_queue_events_csv)
    l2_scorecard = pd.read_csv(paths.l2_queue_scorecard_csv)
    taker_scorecard = pd.read_csv(paths.taker_scorecard_csv) if paths.taker_scorecard_csv.exists() else pd.DataFrame()
    decomp = pd.read_csv(paths.decomp_csv) if paths.decomp_csv.exists() else pd.DataFrame()
    queue_release = (
        pd.read_csv(paths.queue_release_scorecard_csv) if paths.queue_release_scorecard_csv.exists() else pd.DataFrame()
    )
    liquidity_envelope = (
        pd.read_csv(paths.liquidity_envelope_scorecard_csv)
        if paths.liquidity_envelope_scorecard_csv.exists()
        else pd.DataFrame()
    )
    return entries, framework_scorecard, l2_events, l2_scorecard, taker_scorecard, decomp, queue_release, liquidity_envelope


def practical_l2_events(l2_events: pd.DataFrame) -> pd.DataFrame:
    frame = l2_events.copy()
    for col, value in PRACTICAL_SCENARIO.items():
        frame = frame[np.isclose(pd.to_numeric(frame[col], errors="coerce"), value)]
    return frame.reset_index(drop=True)


def add_filter_features(entries: pd.DataFrame) -> pd.DataFrame:
    frame = entries.copy()
    direction = pd.to_numeric(frame["direction"], errors="coerce").fillna(0.0)
    frame["abs_past_event_25_bps"] = pd.to_numeric(frame["past_event_25_bps"], errors="coerce").abs()
    for col in ["microprice_dev_bps", "queue_imbalance_1", "queue_imbalance_5", "mlofi_roll10_l1", "mlofi_roll10_l25"]:
        frame[f"signed_{col}"] = pd.to_numeric(frame[col], errors="coerce") * direction
    return frame


def join_practical(entries: pd.DataFrame, practical_events: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [
        "fold",
        "trigger_class",
        "entry_quality_bin",
        "date",
        "entry_row",
        "direction",
        *[col for col in FILTER_FEATURES if col in entries.columns],
    ]
    left = entries.loc[:, feature_cols].copy()
    key = ["fold", "trigger_class", "entry_quality_bin", "date", "entry_row", "direction"]
    event_cols = [
        *key,
        "scorecard_status",
        "latency_ms",
        "fill_timeout_ms",
        "order_notional_quote",
        "fee_stress_bps",
        "filled",
        "fill_ratio",
        "fill_wait_ms",
        "queue_ahead_base",
        "queue_drain_l2_decrease_base",
        "queue_drain_trade_base",
        "own_fill_trade_base",
        "fill_gross_bps",
        "fill_net_bps",
        "break_even_fee_for_2bps",
    ]
    event_cols = [col for col in event_cols if col in practical_events.columns]
    out = practical_events.loc[:, event_cols].merge(left, on=key, how="left")
    return out


def subset_metrics(g: pd.DataFrame, filter_name: str, filter_expr: str, run_tag: str) -> dict[str, object]:
    filled = g["filled"].astype(bool)
    fill_net = pd.to_numeric(g["fill_net_bps"], errors="coerce")
    fill_rate = safe_rate(filled)
    return {
        "run_tag": run_tag,
        "guardrail": GUARDRAIL,
        "filter_name": filter_name,
        "filter_expr": filter_expr,
        "signals": int(len(g)),
        "filled": int(filled.sum()),
        "fill_rate": fill_rate,
        "avg_fill_ratio": finite_mean(g["fill_ratio"]),
        "filled_net_mean_bps": finite_mean(fill_net),
        "filled_net_median_bps": finite_quantile(fill_net, 0.50),
        "filled_net_p10_bps": finite_quantile(fill_net, 0.10),
        "per_signal_net_mean_bps": fill_rate * finite_mean(fill_net) if np.isfinite(fill_rate) else np.nan,
        "break_even_fee_for_2bps_mean": finite_mean(g["break_even_fee_for_2bps"]),
        "queue_drain_l2_decrease_mean_base": finite_mean(g["queue_drain_l2_decrease_base"]),
        "queue_drain_trade_mean_base": finite_mean(g["queue_drain_trade_base"]),
        "own_fill_trade_mean_base": finite_mean(g["own_fill_trade_base"]),
    }


def gate_metrics(row: dict[str, object] | pd.Series) -> dict[str, bool]:
    fill_rate = float(row.get("fill_rate", np.nan))
    filled_net = float(row.get("filled_net_mean_bps", np.nan))
    per_signal = float(row.get("per_signal_net_mean_bps", np.nan))
    break_even = float(row.get("break_even_fee_for_2bps_mean", np.nan))
    p10 = float(row.get("filled_net_p10_bps", np.nan))
    return {
        "fill_pass": bool(np.isfinite(fill_rate) and fill_rate >= 0.30),
        "net_pass": bool(np.isfinite(filled_net) and filled_net > 2.0),
        "per_signal_pass": bool(np.isfinite(per_signal) and per_signal > 1.0),
        "fee_budget_pass": bool(np.isfinite(break_even) and break_even >= 2.0),
        "tail_pass": bool(np.isfinite(p10) and p10 > -20.0),
    }


def evaluate_repair_filters(joined: pd.DataFrame, min_signals: int, quantiles: list[float], run_tag: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_cols = ["fold", "trigger_class", "entry_quality_bin"]
    for key, g in joined.groupby(group_cols, sort=True):
        base = subset_metrics(g, "baseline", "all focused practical-scenario entries", run_tag)
        base.update(dict(zip(group_cols, key)))
        base.update(gate_metrics(base))
        base["post_hoc_validation_filter"] = False
        rows.append(base)

        for feature in FILTER_FEATURES:
            if feature not in g.columns:
                continue
            values = pd.to_numeric(g[feature], errors="coerce")
            finite = values[np.isfinite(values)]
            if finite.nunique(dropna=True) < 3:
                continue
            cuts = sorted({float(finite.quantile(q)) for q in quantiles if np.isfinite(float(finite.quantile(q)))})
            for cut in cuts:
                for op in ["<=", ">="]:
                    mask = values <= cut if op == "<=" else values >= cut
                    sub = g.loc[mask.fillna(False)].copy()
                    if len(sub) < min_signals:
                        continue
                    item = subset_metrics(sub, f"{feature}_{op}_{fmt_num(cut, 6)}", f"{feature} {op} {cut:.10g}", run_tag)
                    item.update(dict(zip(group_cols, key)))
                    item.update(gate_metrics(item))
                    item["post_hoc_validation_filter"] = True
                    rows.append(item)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["all_execution_gates_pass"] = (
        out["fill_pass"].astype(bool)
        & out["net_pass"].astype(bool)
        & out["per_signal_pass"].astype(bool)
        & out["fee_budget_pass"].astype(bool)
        & out["tail_pass"].astype(bool)
    )
    out = out.sort_values(
        ["all_execution_gates_pass", "per_signal_net_mean_bps", "filled_net_mean_bps", "fill_rate", "signals"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    return out


def repair_scorecard(filters: pd.DataFrame, run_tag: str) -> pd.DataFrame:
    if filters.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for key, g in filters.groupby(["fold", "trigger_class", "entry_quality_bin"], sort=True):
        best = g.sort_values(
            ["all_execution_gates_pass", "per_signal_net_mean_bps", "filled_net_mean_bps", "fill_rate", "signals"],
            ascending=[False, False, False, False, False],
        ).iloc[0]
        baseline = g.loc[g["filter_name"].eq("baseline")].head(1)
        base_per_signal = float(baseline.iloc[0]["per_signal_net_mean_bps"]) if not baseline.empty else np.nan
        status = (
            "post_hoc_repair_candidate_needs_walk_forward"
            if bool(best["all_execution_gates_pass"])
            else "no_simple_fill_filter_repair"
        )
        rows.append(
            {
                "run_tag": run_tag,
                "guardrail": GUARDRAIL,
                "fold": key[0],
                "trigger_class": key[1],
                "entry_quality_bin": key[2],
                "best_filter_name": best["filter_name"],
                "best_filter_expr": best["filter_expr"],
                "signals": int(best["signals"]),
                "filled": int(best["filled"]),
                "fill_rate": best["fill_rate"],
                "filled_net_mean_bps": best["filled_net_mean_bps"],
                "filled_net_p10_bps": best["filled_net_p10_bps"],
                "per_signal_net_mean_bps": best["per_signal_net_mean_bps"],
                "per_signal_lift_vs_baseline_bps": best["per_signal_net_mean_bps"] - base_per_signal
                if np.isfinite(base_per_signal)
                else np.nan,
                "break_even_fee_for_2bps_mean": best["break_even_fee_for_2bps_mean"],
                "fill_pass": bool(best["fill_pass"]),
                "net_pass": bool(best["net_pass"]),
                "per_signal_pass": bool(best["per_signal_pass"]),
                "fee_budget_pass": bool(best["fee_budget_pass"]),
                "tail_pass": bool(best["tail_pass"]),
                "all_execution_gates_pass": bool(best["all_execution_gates_pass"]),
                "repair_status": status,
                "post_hoc_validation_filter": bool(best["post_hoc_validation_filter"]),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["all_execution_gates_pass", "per_signal_net_mean_bps", "filled_net_mean_bps"],
        ascending=[False, False, False],
    )


def completion_audit(
    paths: Paths,
    framework_scorecard: pd.DataFrame,
    l2_scorecard: pd.DataFrame,
    taker_scorecard: pd.DataFrame,
    decomp: pd.DataFrame,
    queue_release: pd.DataFrame,
    liquidity_envelope: pd.DataFrame,
    repair: pd.DataFrame,
) -> list[dict[str, object]]:
    promoted = int((framework_scorecard["scorecard_status"].astype(str) == "promote").sum())
    research_continue = int(framework_scorecard["scorecard_status"].astype(str).str.contains("research_continue").sum())
    l2_no_go = bool(l2_scorecard["l2_queue_fill_status"].astype(str).eq("l2_queue_fill_no_go").all())
    any_repair = bool((repair.get("all_execution_gates_pass", pd.Series(dtype=bool)).astype(bool)).any()) if not repair.empty else False
    taker_gate_rows = int(taker_scorecard.get("taker_promote_gate", pd.Series(dtype=bool)).astype(bool).sum()) if not taker_scorecard.empty else 0
    best_maker_per_signal = (
        float(pd.to_numeric(decomp["per_signal_net_mean_bps"], errors="coerce").max()) if not decomp.empty else np.nan
    )
    queue_release_gate_rows = (
        int(queue_release.get("pivot_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not queue_release.empty
        else 0
    )
    best_queue_release_mean = (
        float(pd.to_numeric(queue_release["net_mean_bps"], errors="coerce").max()) if not queue_release.empty else np.nan
    )
    liquidity_status = (
        str(liquidity_envelope["liquidity_envelope_status"].iloc[0])
        if "liquidity_envelope_status" in liquidity_envelope.columns and not liquidity_envelope.empty
        else "missing"
    )
    depth_support_day_rate = (
        float(pd.to_numeric(liquidity_envelope["depth_support_day_rate"], errors="coerce").iloc[0])
        if "depth_support_day_rate" in liquidity_envelope.columns and not liquidity_envelope.empty
        else np.nan
    )
    best_envelope_fill_rate = (
        float(pd.to_numeric(liquidity_envelope["best_practical_maker_fill_rate"], errors="coerce").iloc[0])
        if "best_practical_maker_fill_rate" in liquidity_envelope.columns and not liquidity_envelope.empty
        else np.nan
    )
    return [
        {
            "requirement": "strict_walk_forward_framework",
            "status": "partial_pass",
            "evidence": str(paths.framework_scorecard_csv),
            "detail": "V2 framework emits expanding folds and fold-valid scorecards, but current execution realism is only a focused post-framework proxy.",
        },
        {
            "requirement": "cost_pressure_and_realistic_cost_ladder",
            "status": "partial_pass",
            "evidence": str(paths.framework_scorecard_csv),
            "detail": "Framework has realistic proxy and +2bps stress; L2 practical fill economics are negative.",
        },
        {
            "requirement": "matched_controls_and_residual_controls",
            "status": "partial_pass",
            "evidence": str(paths.framework_scorecard_csv),
            "detail": f"{research_continue} rows pass enough controls for research_continue, but no promoted row exists.",
        },
        {
            "requirement": "mathematical_decomposition",
            "status": "partial_pass",
            "evidence": "docs/markets/ccusdt/v2-executable-research-framework.md",
            "detail": "Entry/exit/risk decomposition is specified and framework artifacts exist; decomposition is still proxy-label based.",
        },
        {
            "requirement": "entry_quality_model",
            "status": "partial_pass",
            "evidence": str(paths.entries_csv),
            "detail": "Fold-valid logistic entry-quality bins exist, but they do not produce fill-aware execution pass.",
        },
        {
            "requirement": "exit_shape_model",
            "status": "partial_pass",
            "evidence": str(paths.framework_scorecard_csv),
            "detail": "Quote-transition and path-shape diagnostics exist; no executable exit after real fill is validated.",
        },
        {
            "requirement": "risk_control_model",
            "status": "partial_pass",
            "evidence": str(paths.framework_scorecard_csv),
            "detail": "Stop/risk diagnostics exist on proxy path labels; L2 practical filled tails remain poor.",
        },
        {
            "requirement": "stable_after_real_cost_gt_2bps_capture",
            "status": "fail",
            "evidence": str(paths.l2_queue_scorecard_csv),
            "detail": "All practical L2 queue scorecard rows are no-go; filled-net and per-signal net are negative.",
        },
        {
            "requirement": "taker_or_crossing_fallback",
            "status": "fail",
            "evidence": str(paths.taker_scorecard_csv),
            "detail": f"Taker promote-gate rows: {taker_gate_rows}; crossing does not rescue current candidates.",
        },
        {
            "requirement": "execution_failure_decomposition",
            "status": "fail",
            "evidence": str(paths.decomp_csv),
            "detail": f"Best practical maker per-signal net is {best_maker_per_signal:.4f} bps versus the 2 bps target.",
        },
        {
            "requirement": "structural_queue_release_pivot",
            "status": "fail",
            "evidence": str(paths.queue_release_scorecard_csv),
            "detail": f"Queue-release promote-gate rows: {queue_release_gate_rows}; best mean is {best_queue_release_mean:.4f} bps.",
        },
        {
            "requirement": "liquidity_envelope_universe_pivot",
            "status": "fail",
            "evidence": str(paths.liquidity_envelope_scorecard_csv),
            "detail": (
                f"Envelope status: {liquidity_status}; depth-support day rate: {depth_support_day_rate:.4f}; "
                f"best practical maker fill rate: {best_envelope_fill_rate:.4f}."
            ),
        },
        {
            "requirement": "filter_low_quality_entries",
            "status": "incomplete",
            "evidence": str(paths.repair_scorecard_csv),
            "detail": "Current fill-aware repair scan found a post-hoc diagnostic only; no promotable walk-forward filter yet.",
        },
        {
            "requirement": "control_left_tail_risk",
            "status": "incomplete",
            "evidence": str(paths.l2_queue_scorecard_csv),
            "detail": "Proxy risk controls exist, but practical filled p10/tail metrics fail for most rows.",
        },
        {
            "requirement": "promotion_or_completion",
            "status": "not_achieved",
            "evidence": str(paths.framework_scorecard_csv),
            "detail": (
                f"Promoted rows: {promoted}. L2 all no-go: {l2_no_go}. "
                f"Taker gate rows: {taker_gate_rows}. Queue-release gate rows: {queue_release_gate_rows}. "
                f"Liquidity envelope status: {liquidity_status}. Any post-hoc repair pass: {any_repair}."
            ),
        },
    ]


def write_report(
    paths: Paths,
    audit: list[dict[str, object]],
    l2_scorecard: pd.DataFrame,
    taker_scorecard: pd.DataFrame,
    decomp: pd.DataFrame,
    queue_release: pd.DataFrame,
    liquidity_envelope: pd.DataFrame,
    repair_filters: pd.DataFrame,
    repair_scores: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Goal Completion Audit")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "Objective: systematize the observed CCUSDT/CEX L2 short-horizon microstructure edge into an executable "
        "research framework with strict walk-forward validation, cost pressure, matched controls, mathematical "
        "decomposition, entry-quality, exit-shape, and risk-control models, and stable real-cost `>2` bps capture."
    )
    lines.append("")
    lines.append("## Completion Checklist")
    lines.append("")
    audit_df = pd.DataFrame(audit)
    lines.extend(markdown_table(audit_df, ["requirement", "status", "evidence", "detail"], 20))
    lines.append("")
    lines.append("## Practical L2 Queue Evidence")
    lines.append("")
    if l2_scorecard.empty:
        lines.append("_No L2 scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                l2_scorecard,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "signals",
                    "fill_rate",
                    "filled_net_mean_bps",
                    "filled_net_p10_bps",
                    "per_signal_net_mean_bps",
                    "l2_queue_fill_status",
                ],
                20,
            )
        )
    lines.append("")
    lines.append("## Taker And Execution Decomposition")
    lines.append("")
    if taker_scorecard.empty:
        lines.append("_No taker scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                taker_scorecard.sort_values("taker_net_mean_bps", ascending=False),
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "entries",
                    "taker_net_mean_bps",
                    "taker_net_plus2_mean_bps",
                    "taker_promote_gate",
                    "fail_reasons",
                ],
                12,
            )
        )
    lines.append("")
    if decomp.empty:
        lines.append("_No execution decomposition rows._")
    else:
        lines.extend(
            markdown_table(
                decomp.sort_values("per_signal_net_mean_bps", ascending=False),
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "fill_rate",
                    "filled_net_mean_bps",
                    "per_signal_net_mean_bps",
                    "maker_gap_to_target_bps",
                    "maker_failure_mode",
                ],
                12,
            )
        )
    lines.append("")
    lines.append("## Structural Queue-Release Pivot")
    lines.append("")
    lines.append(
        "This lightweight pivot tests book-ticker queue-release continuation as a structurally different signal family. "
        "It is diagnostic only and does not promote execution."
    )
    lines.append("")
    if queue_release.empty:
        lines.append("_No queue-release scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                queue_release.sort_values("net_mean_bps", ascending=False),
                [
                    "fold",
                    "release_side",
                    "horizon_sec",
                    "threshold_quantile",
                    "entries",
                    "net_mean_bps",
                    "net_plus2_mean_bps",
                    "net_cvar10_bps",
                    "signal_minus_random_p50_bps",
                    "pivot_promote_gate",
                    "queue_release_status",
                ],
                12,
            )
        )
    lines.append("")
    lines.append("## Liquidity Envelope Pivot")
    lines.append("")
    lines.append(
        "This execution-first screen checks whether CCUSDT itself supports the target notional and practical fill "
        "profile before more alpha mining."
    )
    lines.append("")
    if liquidity_envelope.empty:
        lines.append("_No liquidity-envelope scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                liquidity_envelope,
                [
                    "symbol",
                    "dates",
                    "target_notional_quote",
                    "median_daily_median_spread_bps",
                    "median_daily_top_depth_p05_quote",
                    "depth_support_day_rate",
                    "best_practical_maker_fill_rate",
                    "best_practical_maker_per_signal_net_bps",
                    "taker_promote_rows",
                    "envelope_pre_alpha_gate",
                    "liquidity_envelope_status",
                ],
                10,
            )
        )
    lines.append("")
    lines.append("## Fill-Aware Repair Scan")
    lines.append("")
    lines.append(
        "This scan is post-hoc on validation-side practical fill rows. It is useful for triage, but a positive row "
        "would still need a new walk-forward run before promotion."
    )
    lines.append("")
    if repair_scores.empty:
        lines.append("_No repair scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                repair_scores,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "best_filter_expr",
                    "signals",
                    "fill_rate",
                    "filled_net_mean_bps",
                    "filled_net_p10_bps",
                    "per_signal_net_mean_bps",
                    "all_execution_gates_pass",
                    "repair_status",
                ],
                20,
            )
        )
    lines.append("")
    lines.append("## Top Diagnostic Filters")
    lines.append("")
    if repair_filters.empty:
        lines.append("_No filter rows._")
    else:
        top = repair_filters.sort_values(
            ["all_execution_gates_pass", "per_signal_net_mean_bps", "filled_net_mean_bps", "fill_rate"],
            ascending=[False, False, False, False],
        )
        lines.extend(
            markdown_table(
                top,
                [
                    "trigger_class",
                    "entry_quality_bin",
                    "filter_expr",
                    "signals",
                    "fill_rate",
                    "filled_net_mean_bps",
                    "filled_net_p10_bps",
                    "per_signal_net_mean_bps",
                    "all_execution_gates_pass",
                ],
                30,
            )
        )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(
        "The active goal is not complete. The research framework is substantially systematized, but the explicit "
        "`stable real-cost >2bps capture` requirement is not satisfied by current L2 queue-fill evidence."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.repair_filters_csv, paths.repair_scorecard_csv, paths.audit_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(
        f"python scripts/ccusdt_v2_fill_repair_audit.py --l2-queue-run-tag {paths.l2_queue_run_tag} "
        f"--queue-release-run-tag {paths.queue_release_run_tag} "
        f"--liquidity-envelope-run-tag {paths.liquidity_envelope_run_tag} --run-tag {paths.run_tag}"
    )
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    paths: Paths,
    audit: list[dict[str, object]],
    repair_filters: pd.DataFrame,
    repair_scores: pd.DataFrame,
    l2_scorecard: pd.DataFrame,
    taker_scorecard: pd.DataFrame,
    decomp: pd.DataFrame,
    queue_release: pd.DataFrame,
    liquidity_envelope: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    repair_filters.to_csv(paths.repair_filters_csv, index=False)
    repair_scores.to_csv(paths.repair_scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "framework_run_tag": paths.framework_run_tag,
        "l2_queue_run_tag": paths.l2_queue_run_tag,
        "taker_run_tag": paths.taker_run_tag,
        "decomp_run_tag": paths.decomp_run_tag,
        "queue_release_run_tag": paths.queue_release_run_tag,
        "liquidity_envelope_run_tag": paths.liquidity_envelope_run_tag,
        "guardrail": GUARDRAIL,
        "practical_scenario": PRACTICAL_SCENARIO,
        "min_signals": args.min_signals,
        "quantiles": parse_floats(args.quantiles),
        "completion_status": "not_achieved",
        "audit": audit,
        "outputs": {
            "repair_filters_csv": str(paths.repair_filters_csv),
            "repair_scorecard_csv": str(paths.repair_scorecard_csv),
            "audit_json": str(paths.audit_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.audit_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(
        paths,
        audit,
        l2_scorecard,
        taker_scorecard,
        decomp,
        queue_release,
        liquidity_envelope,
        repair_filters,
        repair_scores,
        args,
    )


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        framework_run_tag=args.framework_run_tag,
        l2_queue_run_tag=args.l2_queue_run_tag,
        taker_run_tag=args.taker_run_tag,
        decomp_run_tag=args.decomp_run_tag,
        queue_release_run_tag=args.queue_release_run_tag,
        liquidity_envelope_run_tag=args.liquidity_envelope_run_tag,
        run_tag=args.run_tag,
    )
    (
        entries,
        framework_scorecard,
        l2_events,
        l2_scorecard,
        taker_scorecard,
        decomp,
        queue_release,
        liquidity_envelope,
    ) = read_inputs(paths)
    practical = practical_l2_events(l2_events)
    joined = join_practical(add_filter_features(entries), practical)
    repair_filters = evaluate_repair_filters(joined, args.min_signals, parse_floats(args.quantiles), args.run_tag)
    repair_scores = repair_scorecard(repair_filters, args.run_tag)
    audit = completion_audit(
        paths,
        framework_scorecard,
        l2_scorecard,
        taker_scorecard,
        decomp,
        queue_release,
        liquidity_envelope,
        repair_scores,
    )
    write_outputs(
        paths,
        audit,
        repair_filters,
        repair_scores,
        l2_scorecard,
        taker_scorecard,
        decomp,
        queue_release,
        liquidity_envelope,
        args,
    )
    print(f"[ccusdt_fill_repair_audit] practical rows={len(practical)}", flush=True)
    print(f"[ccusdt_fill_repair_audit] repair filter rows={len(repair_filters)}", flush=True)
    print(f"[ccusdt_fill_repair_audit] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
