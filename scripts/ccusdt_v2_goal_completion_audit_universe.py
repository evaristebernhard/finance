#!/usr/bin/env python
"""Completion audit for the CCUSDT V2 objective after universe/OOS continuation.

This is a hard prompt-to-artifact checklist. It should only report completion
when every explicit objective requirement is covered by real artifacts and the
execution scorecards actually pass the target gates.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_goal_completion_audit_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1"


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def checklist_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_goal_completion_checklist_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_goal_completion_audit_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-goal-completion-audit-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit CCUSDT V2 goal completion after universe continuation.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_first_json(paths: list[Path]) -> dict[str, Any]:
    for path in paths:
        if path.exists():
            return read_json(path)
    return {}


def status_row(
    requirement: str,
    evidence: str,
    observed: str,
    status: str,
    gap: str,
) -> dict[str, str]:
    return {
        "requirement": requirement,
        "evidence": evidence,
        "observed": observed,
        "status": status,
        "gap": gap,
    }


def fmt(value: Any, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def audit(paths: Paths) -> tuple[pd.DataFrame, dict[str, Any]]:
    date_dir = paths.date_dir
    framework = read_csv(date_dir / "ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv")
    matched = read_csv(date_dir / "ccusdt_v2_matched_controls_20260518_ccusdt_v2_framework_v1.csv")
    residual = read_csv(date_dir / "ccusdt_v2_residual_controls_20260518_ccusdt_v2_framework_v1.csv")
    quality = read_csv(date_dir / "ccusdt_v2_entry_quality_bins_20260518_ccusdt_v2_framework_v1.csv")
    exit_shape = read_csv(date_dir / "ccusdt_v2_exit_shape_20260518_ccusdt_v2_framework_v1.csv")
    risk = read_csv(date_dir / "ccusdt_v2_risk_control_20260518_ccusdt_v2_framework_v1.csv")
    l2 = read_csv(date_dir / "ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv")
    repair = read_csv(date_dir / "ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv")
    taker = read_csv(date_dir / "ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv")
    decomp = read_csv(date_dir / "ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv")
    ccusdt_env = read_csv(date_dir / "ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv")
    universe_100 = read_csv(date_dir / "ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.csv")
    universe_10 = read_csv(date_dir / "ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_target10_v1.csv")
    btc_queue = read_csv(date_dir / "ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv")
    btc_tob = read_csv(date_dir / "ccusdt_v2_tob_factor_scorecard_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv")
    btc_tob_decomp = read_csv(date_dir / "ccusdt_v2_tob_factor_decomposition_20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.csv")
    cross_market = read_csv(date_dir / "ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv")
    absorption = read_csv(date_dir / "ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv")
    current_inventory = read_json(date_dir / "ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_after_oos_v1.json")
    oos_size_probe = read_json(date_dir / "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json")
    oos_day20260517_probe = read_json(date_dir / "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json")
    oos_download = read_json(date_dir / "bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json")
    oos_envelope = read_json(date_dir / "ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json")
    ccusdt_oos_env = read_json(date_dir / "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json")
    ccusdt_oos_env_target10 = read_json(date_dir / "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json")
    oos_envelope_target10 = read_json(date_dir / "ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json")
    oos_envelope_target5 = read_json(date_dir / "ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json")
    external_inventory = read_json(date_dir / "ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.json")
    tardis_metadata = read_json(date_dir / "ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.json")
    external_acquisition = read_json(date_dir / "ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json")
    stop_pivot_gate = read_first_json(
        [
            date_dir / "ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.json",
            date_dir / "ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_oos_day20260517_probe_v1.json",
            date_dir / "ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_v1.json",
        ]
    )
    small_download = read_json(date_dir / "bonk_bullish_l2_download_completion_20260518_ccusdt_v2_small_tier_download_v1.json")
    tob_download = read_json(date_dir / "bonk_bullish_l2_download_completion_20260518_ccusdt_v2_remaining_tob_trades_download_v1.json")

    promoted = int(framework["scorecard_status"].astype(str).eq("promote").sum()) if not framework.empty else 0
    research_continue = (
        int(framework["scorecard_status"].astype(str).str.contains("research_continue").sum())
        if not framework.empty
        else 0
    )
    best_framework_mean = (
        float(pd.to_numeric(framework.get("net_realistic_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not framework.empty
        else float("nan")
    )
    l2_promote = (
        int(l2.get("l2_queue_fill_status", pd.Series(dtype=str)).astype(str).ne("l2_queue_fill_no_go").sum())
        if not l2.empty
        else 0
    )
    l2_best = (
        float(pd.to_numeric(l2.get("per_signal_net_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not l2.empty
        else float("nan")
    )
    repair_pass = (
        int(repair.get("passes_execution_gates", pd.Series(dtype=bool)).astype(bool).sum())
        if not repair.empty
        else 0
    )
    taker_promote = (
        int(taker.get("taker_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not taker.empty
        else 0
    )
    required_filled = (
        float(pd.to_numeric(decomp.get("required_filled_net_at_current_fill_rate_bps", pd.Series(dtype=float)), errors="coerce").min())
        if not decomp.empty
        else float("nan")
    )
    ccusdt_env_status = (
        str(ccusdt_env["liquidity_envelope_status"].iloc[0]) if "liquidity_envelope_status" in ccusdt_env and not ccusdt_env.empty else "missing"
    )
    uni100_candidates = (
        int(universe_100.get("pre_alpha_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not universe_100.empty
        else 0
    )
    uni10_candidates = (
        universe_10.loc[universe_10.get("pre_alpha_gate", pd.Series(dtype=bool)).astype(bool), "symbol"].astype(str).tolist()
        if not universe_10.empty and "symbol" in universe_10
        else []
    )
    btc_queue_promote = (
        int(btc_queue.get("pivot_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not btc_queue.empty
        else 0
    )
    btc_queue_best = (
        float(pd.to_numeric(btc_queue.get("net_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not btc_queue.empty
        else float("nan")
    )
    btc_tob_promote = (
        int(btc_tob.get("tob_factor_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not btc_tob.empty
        else 0
    )
    btc_tob_best = (
        float(pd.to_numeric(btc_tob.get("net_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not btc_tob.empty
        else float("nan")
    )
    btc_tob_decomp_promote = (
        int(btc_tob_decomp.get("tob_factor_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not btc_tob_decomp.empty
        else 0
    )
    btc_tob_decomp_best_gross = (
        float(pd.to_numeric(btc_tob_decomp.get("gross_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not btc_tob_decomp.empty
        else float("nan")
    )
    btc_tob_decomp_best_shortfall = (
        float(
            pd.to_numeric(
                btc_tob_decomp.get("gross_shortfall_to_net2_mean_bps", pd.Series(dtype=float)),
                errors="coerce",
            ).max()
        )
        if not btc_tob_decomp.empty
        else float("nan")
    )
    cross_market_promote = (
        int(cross_market.get("cross_market_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not cross_market.empty
        else 0
    )
    cross_market_best = (
        float(pd.to_numeric(cross_market.get("net_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not cross_market.empty
        else float("nan")
    )
    cross_market_best_gross = (
        float(pd.to_numeric(cross_market.get("gross_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not cross_market.empty
        else float("nan")
    )
    absorption_promote = (
        int(absorption.get("absorption_promote_gate", pd.Series(dtype=bool)).astype(bool).sum())
        if not absorption.empty
        else 0
    )
    absorption_best_net = (
        float(pd.to_numeric(absorption.get("net_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not absorption.empty
        else float("nan")
    )
    absorption_best_gross = (
        float(pd.to_numeric(absorption.get("gross_mean_bps", pd.Series(dtype=float)), errors="coerce").max())
        if not absorption.empty
        else float("nan")
    )
    if not absorption.empty and "net_mean_bps" in absorption and "cost_mean_bps" in absorption:
        absorption_net_series = pd.to_numeric(absorption["net_mean_bps"], errors="coerce")
        absorption_best_cost = float(pd.to_numeric(absorption.loc[absorption_net_series.idxmax(), "cost_mean_bps"], errors="coerce"))
    else:
        absorption_best_cost = float("nan")
    current_core_ready_symbols = list(current_inventory.get("core_l2_ready_symbol_list", []))
    current_core_ready_count = int(current_inventory.get("core_l2_ready_symbols", 0) or 0)
    current_inventory_status = str(current_inventory.get("local_universe_status", "missing"))
    oos_available_rows = int(oos_size_probe.get("available_rows", 0) or 0)
    oos_missing_rows = int(oos_size_probe.get("missing_rows", 0) or 0)
    oos_error_rows = int(oos_size_probe.get("error_rows", 0) or 0)
    oos_total_gb = float(oos_size_probe.get("total_gb", 0.0) or 0.0)
    oos17_planned_rows = int(oos_day20260517_probe.get("planned_rows_probed", 0) or 0)
    oos17_available_rows = int(oos_day20260517_probe.get("available_rows", 0) or 0)
    oos17_missing_rows = int(oos_day20260517_probe.get("missing_rows", 0) or 0)
    oos17_error_rows = int(oos_day20260517_probe.get("error_rows", 0) or 0)
    oos17_total_gb = float(oos_day20260517_probe.get("total_gb", 0.0) or 0.0)
    oos_download_counts = dict(oos_download.get("counts", {}))
    oos_envelope_candidates = list(oos_envelope.get("pre_alpha_candidate_symbols", []))
    ccusdt_oos_env_status = str(ccusdt_oos_env.get("liquidity_envelope_status", "missing"))
    ccusdt_oos_target10_status = str(ccusdt_oos_env_target10.get("liquidity_envelope_status", "missing"))
    oos_target10_candidates = list(oos_envelope_target10.get("pre_alpha_candidate_symbols", []))
    oos_target5_candidates = list(oos_envelope_target5.get("pre_alpha_candidate_symbols", []))
    external_ccusdt_l2_ready = bool(external_inventory.get("external_ccusdt_l2_ready", False))
    external_inventory_decision = str(external_inventory.get("decision", "missing"))
    tardis_metadata_decision = str(tardis_metadata.get("decision", "missing"))
    tardis_cc_external_l2 = list(tardis_metadata.get("cc_external_l2_metadata_exchanges", []))
    tardis_cc_accessible_external_l2 = list(tardis_metadata.get("cc_accessible_external_l2_metadata_exchanges", []))
    external_acquisition_decision = str(external_acquisition.get("decision", "missing"))
    external_acquisition_planned = int(external_acquisition.get("planned_rows", 0) or 0)
    external_acquisition_blocked = int(external_acquisition.get("blocked_access_rows", 0) or 0)
    stop_pivot_decision = str(stop_pivot_gate.get("decision", "missing"))
    stop_required = bool(stop_pivot_gate.get("stop_required", False))
    stop_failed_gates = list(stop_pivot_gate.get("failed_gates", []))

    rows = [
        status_row(
            "strict_walk_forward_framework",
            "ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv",
            f"framework_rows={len(framework)} promoted={promoted} research_continue={research_continue}",
            "covered_but_not_successful" if len(framework) else "missing",
            "Framework exists, but no row is promoted.",
        ),
        status_row(
            "cost_pressure_after_cost_gt_2bps",
            "ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv",
            f"best_framework_net_realistic_mean_bps={fmt(best_framework_mean)} promoted={promoted}",
            "failed",
            "No framework row clears all after-cost promotion gates.",
        ),
        status_row(
            "matched_controls_and_residual_controls",
            "ccusdt_v2_matched_controls_*.csv; ccusdt_v2_residual_controls_*.csv",
            f"matched_rows={len(matched)} residual_rows={len(residual)}",
            "covered_but_not_sufficient",
            "Controls are present, but promoted execution rows remain zero.",
        ),
        status_row(
            "mathematical_execution_decomposition",
            "ccusdt_v2_execution_failure_decomposition_20260518_ccusdt_v2_execution_failure_decomp_v1.csv",
            f"best_l2_per_signal_net_bps={fmt(l2_best)} min_required_filled_net_bps={fmt(required_filled)}",
            "covered_and_failed",
            "Decomposition shows current fill rate would require far higher filled-order edge than observed.",
        ),
        status_row(
            "entry_quality_model",
            "ccusdt_v2_entry_quality_bins_20260518_ccusdt_v2_framework_v1.csv",
            f"entry_quality_rows={len(quality)} repair_filters_passing_execution={repair_pass}",
            "covered_but_not_successful",
            "Entry-quality bins exist, but fill-aware repair found no executable filter.",
        ),
        status_row(
            "exit_shape_model",
            "ccusdt_v2_exit_shape_20260518_ccusdt_v2_framework_v1.csv",
            f"exit_shape_rows={len(exit_shape)}",
            "covered_but_not_promoted",
            "Exit-shape diagnostics exist, but no promoted executable row depends on them.",
        ),
        status_row(
            "risk_control_model_left_tail",
            "ccusdt_v2_risk_control_20260518_ccusdt_v2_framework_v1.csv",
            f"risk_rows={len(risk)}",
            "covered_but_not_successful",
            "Risk-control diagnostics exist, but no row passes the combined execution objective.",
        ),
        status_row(
            "maker_queue_execution_realism",
            "ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv",
            f"rows={len(l2)} non_no_go_rows={l2_promote} best_per_signal_net_bps={fmt(l2_best)}",
            "failed",
            "All practical L2 queue rows are no-go and the best per-signal result is below the +2 bps target.",
        ),
        status_row(
            "taker_fallback_execution_realism",
            "ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv",
            f"rows={len(taker)} taker_promote_rows={taker_promote}",
            "failed",
            "Crossing/taker fallback has no promote-gate rows.",
        ),
        status_row(
            "ccusdt_instrument_liquidity_envelope",
            "ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv",
            f"status={ccusdt_env_status}",
            "failed",
            "CCUSDT itself fails the execution-first envelope.",
        ),
        status_row(
            "universe_download_and_screen",
            "bonk_bullish_l2_download_completion_*; ccusdt_v2_universe_liquidity_envelope_scorecard_*",
            f"small_counts={small_download.get('counts', {})} tob_counts={tob_download.get('counts', {})} target100_candidates={uni100_candidates} target10_candidates={','.join(uni10_candidates)}",
            "covered_but_not_successful",
            "Expanded universe has zero candidates at $100; only BTCUSDC passes pre-alpha envelope at $10.",
        ),
        status_row(
            "current_local_bullish_universe_inventory",
            "ccusdt_v2_local_bullish_universe_summary_20260518_ccusdt_v2_local_universe_inventory_current_v1.json",
            f"status={current_inventory_status} core_l2_ready_symbols={current_core_ready_count} symbols={','.join(current_core_ready_symbols)}",
            "covered_but_envelope_failed" if current_inventory else "missing",
            "Current local inventory has a multi-symbol core L2 set, but the universe liquidity envelope and follow-up alpha diagnostics still fail.",
        ),
        status_row(
            "new_oos_days_availability",
            "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json",
            f"planned=36 available={oos_available_rows} missing={oos_missing_rows} errors={oos_error_rows} total_gb={fmt(oos_total_gb, 4)}",
            "available_and_followed_up" if oos_download else ("available_but_not_collected_or_evaluated" if oos_available_rows else ("missing" if not oos_size_probe else "blocked")),
            "One new OOS day was available by no-download probe; follow-up download/envelope evidence determines whether it unlocks modeling.",
        ),
        status_row(
            "oos_day20260517_availability_probe",
            "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json",
            f"planned={oos17_planned_rows} available={oos17_available_rows} missing={oos17_missing_rows} errors={oos17_error_rows} total_gb={fmt(oos17_total_gb, 4)}",
            "available_but_not_collected_or_evaluated" if oos17_available_rows else ("blocked" if oos_day20260517_probe else "missing"),
            "The latest no-download check found no accessible 2026-05-17 core L2 files, so it does not unlock a new OOS modeling pass.",
        ),
        status_row(
            "oos_day20260516_download_and_envelope",
            "bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json",
            f"download_counts={oos_download_counts} pre_alpha_candidates={','.join(oos_envelope_candidates)}",
            "failed" if oos_download and not oos_envelope_candidates else ("covered" if oos_envelope_candidates else "missing"),
            "The available OOS day was downloaded and screened, but the 18-day small-tier envelope still has zero pre-alpha candidates.",
        ),
        status_row(
            "ccusdt_oos_day20260516_liquidity_envelope",
            "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json",
            f"status={ccusdt_oos_env_status}",
            "failed" if ccusdt_oos_env_status == "liquidity_envelope_no_go" else ("covered" if ccusdt_oos_env else "missing"),
            "After adding the available OOS day to the canonical CCUSDT tree, the 18-day CCUSDT execution envelope still fails.",
        ),
        status_row(
            "oos_target_notional_sensitivity",
            "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json",
            (
                f"ccusdt_target10_status={ccusdt_oos_target10_status} "
                f"small_target10_candidates={','.join(oos_target10_candidates)} "
                f"small_target5_candidates={','.join(oos_target5_candidates)}"
            ),
            "failed" if ccusdt_oos_env_target10 and not oos_target10_candidates and not oos_target5_candidates else "missing",
            "Lower target notionals do not create a pre-alpha candidate for CCUSDT or the OOS small-tier set.",
        ),
        status_row(
            "btcusdc_small_notional_structural_pivot",
            "ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv",
            f"rows={len(btc_queue)} promote_rows={btc_queue_promote} best_net_mean_bps={fmt(btc_queue_best)}",
            "failed",
            "The first BTCUSDC top-of-book queue-release diagnostic has no promote-gate rows; it does not justify BTC incremental-L2 download by itself.",
        ),
        status_row(
            "btcusdc_top_of_book_factor_framework",
            "ccusdt_v2_tob_factor_scorecard_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv",
            f"rows={len(btc_tob)} promote_rows={btc_tob_promote} best_net_mean_bps={fmt(btc_tob_best)}",
            "failed",
            "The BTCUSDC top-of-book factor smoke has no promote-gate rows; best after-cost mean remains negative.",
        ),
        status_row(
            "btcusdc_top_of_book_gross_cost_decomposition",
            "ccusdt_v2_tob_factor_decomposition_20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1.csv",
            f"rows={len(btc_tob_decomp)} promote_rows={btc_tob_decomp_promote} best_gross_mean_bps={fmt(btc_tob_decomp_best_gross)} best_gross_shortfall_to_net2_mean_bps={fmt(btc_tob_decomp_best_shortfall)}",
            "covered_and_failed" if len(btc_tob_decomp) else "missing",
            "BTCUSDC top-of-book gross movement is below the fee-stress plus +2 bps hurdle; the best gross shortfall remains negative.",
        ),
        status_row(
            "cross_market_lead_lag_structural_pivot",
            "ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv",
            f"rows={len(cross_market)} promote_rows={cross_market_promote} best_net_mean_bps={fmt(cross_market_best)} best_gross_mean_bps={fmt(cross_market_best_gross)}",
            "failed" if len(cross_market) else "missing",
            "BTC/ETH/SOL leader features show some directional movement, but CCUSDT cost pressure dominates and no cross-market row passes economics or controls.",
        ),
        status_row(
            "absorption_replenishment_reversal_pivot",
            "ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv",
            f"rows={len(absorption)} promote_rows={absorption_promote} best_net_mean_bps={fmt(absorption_best_net)} best_gross_mean_bps={fmt(absorption_best_gross)} best_cost_mean_bps={fmt(absorption_best_cost)}",
            "failed" if len(absorption) and absorption_promote == 0 else ("covered" if absorption_promote else "missing"),
            "The structurally new absorption/replenishment reversal mechanism has no promote rows; gross movement is defeated by cost pressure and sample limits.",
        ),
        status_row(
            "external_venue_ccusdt_l2_inventory",
            "ccusdt_v2_external_venue_inventory_20260518_ccusdt_v2_external_venue_inventory_v1.json",
            f"decision={external_inventory_decision} external_ccusdt_l2_ready={external_ccusdt_l2_ready}",
            "blocked" if external_inventory and not external_ccusdt_l2_ready else ("covered" if external_ccusdt_l2_ready else "missing"),
            "Local files do not contain synchronized external-venue CCUSDT L2; external-venue lead/lag validation is data-blocked.",
        ),
        status_row(
            "external_venue_tardis_metadata_feasibility",
            "ccusdt_v2_tardis_external_metadata_probe_20260518_ccusdt_v2_tardis_external_metadata_probe_v1.json",
            (
                f"decision={tardis_metadata_decision} "
                f"cc_external_l2_metadata={','.join(tardis_cc_external_l2)} "
                f"cc_accessible_external_l2={','.join(tardis_cc_accessible_external_l2)}"
            ),
            "blocked" if tardis_metadata and not tardis_cc_accessible_external_l2 else ("covered" if tardis_cc_accessible_external_l2 else "missing"),
            "Tardis metadata has external CC orderbook symbols, but the current API access has no external CC L2 venue; acquisition/access is still required.",
        ),
        status_row(
            "external_venue_acquisition_gate",
            "ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json",
            (
                f"decision={external_acquisition_decision} "
                f"planned_rows={external_acquisition_planned} "
                f"blocked_access_rows={external_acquisition_blocked}"
            ),
            "blocked" if external_acquisition and external_acquisition_planned == 0 else ("covered" if external_acquisition_planned > 0 else "missing"),
            "The no-download acquisition manifest has candidate rows, but none can advance to size probe/download under current access.",
        ),
        status_row(
            "stop_pivot_gate",
            "ccusdt_v2_stop_pivot_gate_20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1.json",
            f"decision={stop_pivot_decision} stop_required={stop_required} failed_gates={len(stop_failed_gates)}",
            "blocked" if stop_pivot_gate and stop_required else ("covered" if stop_pivot_gate else "missing"),
            "The machine-readable gate says the current CCUSDT path must stop unless new data, access, instrument, or mechanism unlocks it.",
        ),
        status_row(
            "stable_identification_and_capture_real_cost_gt_2bps",
            "all scorecards",
            f"framework_promoted={promoted} l2_non_no_go={l2_promote} repair_pass={repair_pass} taker_promote={taker_promote} universe100_candidates={uni100_candidates} btc_queue_promote={btc_queue_promote} btc_tob_promote={btc_tob_promote} btc_tob_decomp_promote={btc_tob_decomp_promote} cross_market_promote={cross_market_promote} absorption_promote={absorption_promote} tardis_accessible_external_l2={len(tardis_cc_accessible_external_l2)} external_acquisition_planned={external_acquisition_planned} stop_required={stop_required}",
            "failed",
            "No artifact demonstrates stable real-cost capture above +2 bps.",
        ),
    ]
    frame = pd.DataFrame(rows)
    completion_status = "achieved" if frame["status"].eq("passed").all() else "not_achieved"
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "completion_status": completion_status,
        "objective": (
            "Systematize observed CCUSDT/CEX L2 short-horizon microstructure edge into an executable research "
            "framework with strict walk-forward, cost pressure, matched controls, mathematical decomposition, "
            "entry-quality, exit-shape, and risk-control models, and stably capture real-cost >2 bps while "
            "filtering low-quality entries and controlling left-tail risk."
        ),
        "promoted_rows": promoted,
        "all_practical_l2_non_no_go_rows": l2_promote,
        "fill_repair_execution_pass_rows": repair_pass,
        "taker_promote_rows": taker_promote,
        "universe_target100_candidates": uni100_candidates,
        "universe_target10_candidates": uni10_candidates,
        "current_local_universe_status": current_inventory_status,
        "current_local_core_l2_ready_symbols": current_core_ready_symbols,
        "current_local_core_l2_ready_count": current_core_ready_count,
        "oos_days_probe_available_rows": oos_available_rows,
        "oos_days_probe_missing_rows": oos_missing_rows,
        "oos_days_probe_error_rows": oos_error_rows,
        "oos_days_probe_total_gb": oos_total_gb,
        "oos_day20260517_probe_planned_rows": oos17_planned_rows,
        "oos_day20260517_probe_available_rows": oos17_available_rows,
        "oos_day20260517_probe_missing_rows": oos17_missing_rows,
        "oos_day20260517_probe_error_rows": oos17_error_rows,
        "oos_day20260517_probe_total_gb": oos17_total_gb,
        "oos_day20260516_download_counts": oos_download_counts,
        "oos_day20260516_pre_alpha_candidates": oos_envelope_candidates,
        "ccusdt_oos_day20260516_liquidity_envelope_status": ccusdt_oos_env_status,
        "ccusdt_oos_target10_liquidity_envelope_status": ccusdt_oos_target10_status,
        "oos_small_tier_target10_candidates": oos_target10_candidates,
        "oos_small_tier_target5_candidates": oos_target5_candidates,
        "btcusdc_queue_release_promote_rows": btc_queue_promote,
        "btcusdc_queue_release_best_net_mean_bps": btc_queue_best,
        "btcusdc_tob_factor_promote_rows": btc_tob_promote,
        "btcusdc_tob_factor_best_net_mean_bps": btc_tob_best,
        "btcusdc_tob_factor_decomposition_promote_rows": btc_tob_decomp_promote,
        "btcusdc_tob_factor_decomposition_best_gross_mean_bps": btc_tob_decomp_best_gross,
        "btcusdc_tob_factor_decomposition_best_gross_shortfall_to_net2_mean_bps": btc_tob_decomp_best_shortfall,
        "cross_market_promote_rows": cross_market_promote,
        "cross_market_best_net_mean_bps": cross_market_best,
        "cross_market_best_gross_mean_bps": cross_market_best_gross,
        "absorption_reversal_promote_rows": absorption_promote,
        "absorption_reversal_best_net_mean_bps": absorption_best_net,
        "absorption_reversal_best_gross_mean_bps": absorption_best_gross,
        "absorption_reversal_best_cost_mean_bps": absorption_best_cost,
        "external_venue_inventory_decision": external_inventory_decision,
        "external_ccusdt_l2_ready": external_ccusdt_l2_ready,
        "tardis_external_metadata_decision": tardis_metadata_decision,
        "tardis_cc_external_l2_metadata_exchanges": tardis_cc_external_l2,
        "tardis_cc_accessible_external_l2_metadata_exchanges": tardis_cc_accessible_external_l2,
        "external_acquisition_decision": external_acquisition_decision,
        "external_acquisition_planned_rows": external_acquisition_planned,
        "external_acquisition_blocked_access_rows": external_acquisition_blocked,
        "stop_pivot_decision": stop_pivot_decision,
        "stop_pivot_stop_required": stop_required,
        "stop_pivot_failed_gates": stop_failed_gates,
        "missing_or_failed_requirements": frame.loc[frame["status"].ne("passed"), "requirement"].tolist(),
        "outputs": {
            "checklist_csv": str(paths.checklist_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    return frame, summary


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 50) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def write_report(paths: Paths, checklist: pd.DataFrame, summary: dict[str, Any]) -> None:
    lines: list[str] = [
        "# CCUSDT V2 Goal Completion Audit After Universe/OOS Continuation",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decision",
        "",
        f"Completion status: `{summary['completion_status']}`.",
        "",
        "The active objective is not achieved. The framework and verification artifacts exist, but the execution and universe gates do not demonstrate stable real-cost `>2` bps capture.",
        "",
        "## Checklist",
        "",
        *markdown_table(checklist, ["requirement", "evidence", "observed", "status", "gap"], 60),
        "",
        "## Key Counts",
        "",
        f"- framework_promoted_rows: `{summary['promoted_rows']}`",
        f"- all_practical_l2_non_no_go_rows: `{summary['all_practical_l2_non_no_go_rows']}`",
        f"- fill_repair_execution_pass_rows: `{summary['fill_repair_execution_pass_rows']}`",
        f"- taker_promote_rows: `{summary['taker_promote_rows']}`",
        f"- universe_target100_candidates: `{summary['universe_target100_candidates']}`",
        f"- universe_target10_candidates: `{','.join(summary['universe_target10_candidates'])}`",
        f"- current_local_universe_status: `{summary['current_local_universe_status']}`",
        f"- current_local_core_l2_ready_symbols: `{','.join(summary['current_local_core_l2_ready_symbols'])}`",
        f"- oos_days_probe_available_rows: `{summary['oos_days_probe_available_rows']}`",
        f"- oos_days_probe_missing_rows: `{summary['oos_days_probe_missing_rows']}`",
        f"- oos_days_probe_total_gb: `{fmt(summary['oos_days_probe_total_gb'])}`",
        f"- oos_day20260517_probe_available_rows: `{summary['oos_day20260517_probe_available_rows']}`",
        f"- oos_day20260517_probe_missing_rows: `{summary['oos_day20260517_probe_missing_rows']}`",
        f"- oos_day20260517_probe_total_gb: `{fmt(summary['oos_day20260517_probe_total_gb'])}`",
        f"- oos_day20260516_download_counts: `{summary['oos_day20260516_download_counts']}`",
        f"- oos_day20260516_pre_alpha_candidates: `{','.join(summary['oos_day20260516_pre_alpha_candidates'])}`",
        f"- ccusdt_oos_day20260516_liquidity_envelope_status: `{summary['ccusdt_oos_day20260516_liquidity_envelope_status']}`",
        f"- ccusdt_oos_target10_liquidity_envelope_status: `{summary['ccusdt_oos_target10_liquidity_envelope_status']}`",
        f"- oos_small_tier_target10_candidates: `{','.join(summary['oos_small_tier_target10_candidates'])}`",
        f"- oos_small_tier_target5_candidates: `{','.join(summary['oos_small_tier_target5_candidates'])}`",
        f"- btcusdc_queue_release_promote_rows: `{summary['btcusdc_queue_release_promote_rows']}`",
        f"- btcusdc_queue_release_best_net_mean_bps: `{fmt(summary['btcusdc_queue_release_best_net_mean_bps'])}`",
        f"- btcusdc_tob_factor_promote_rows: `{summary['btcusdc_tob_factor_promote_rows']}`",
        f"- btcusdc_tob_factor_best_net_mean_bps: `{fmt(summary['btcusdc_tob_factor_best_net_mean_bps'])}`",
        f"- btcusdc_tob_factor_decomposition_promote_rows: `{summary['btcusdc_tob_factor_decomposition_promote_rows']}`",
        f"- btcusdc_tob_factor_decomposition_best_gross_mean_bps: `{fmt(summary['btcusdc_tob_factor_decomposition_best_gross_mean_bps'])}`",
        f"- btcusdc_tob_factor_decomposition_best_gross_shortfall_to_net2_mean_bps: `{fmt(summary['btcusdc_tob_factor_decomposition_best_gross_shortfall_to_net2_mean_bps'])}`",
        f"- cross_market_promote_rows: `{summary['cross_market_promote_rows']}`",
        f"- cross_market_best_net_mean_bps: `{fmt(summary['cross_market_best_net_mean_bps'])}`",
        f"- cross_market_best_gross_mean_bps: `{fmt(summary['cross_market_best_gross_mean_bps'])}`",
        f"- absorption_reversal_promote_rows: `{summary['absorption_reversal_promote_rows']}`",
        f"- absorption_reversal_best_net_mean_bps: `{fmt(summary['absorption_reversal_best_net_mean_bps'])}`",
        f"- absorption_reversal_best_gross_mean_bps: `{fmt(summary['absorption_reversal_best_gross_mean_bps'])}`",
        f"- absorption_reversal_best_cost_mean_bps: `{fmt(summary['absorption_reversal_best_cost_mean_bps'])}`",
        f"- external_venue_inventory_decision: `{summary['external_venue_inventory_decision']}`",
        f"- external_ccusdt_l2_ready: `{summary['external_ccusdt_l2_ready']}`",
        f"- tardis_external_metadata_decision: `{summary['tardis_external_metadata_decision']}`",
        f"- tardis_cc_external_l2_metadata_exchanges: `{','.join(summary['tardis_cc_external_l2_metadata_exchanges'])}`",
        f"- tardis_cc_accessible_external_l2_metadata_exchanges: `{','.join(summary['tardis_cc_accessible_external_l2_metadata_exchanges'])}`",
        f"- external_acquisition_decision: `{summary['external_acquisition_decision']}`",
        f"- external_acquisition_planned_rows: `{summary['external_acquisition_planned_rows']}`",
        f"- external_acquisition_blocked_access_rows: `{summary['external_acquisition_blocked_access_rows']}`",
        f"- stop_pivot_decision: `{summary['stop_pivot_decision']}`",
        f"- stop_pivot_stop_required: `{summary['stop_pivot_stop_required']}`",
        f"- stop_pivot_failed_gates: `{','.join(summary['stop_pivot_failed_gates'])}`",
        "",
        "## Output Tables",
        "",
        f"- `{paths.checklist_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_goal_completion_audit_universe.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, checklist: pd.DataFrame, summary: dict[str, Any]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    checklist.to_csv(paths.checklist_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, checklist, summary)


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    checklist, summary = audit(paths)
    write_outputs(paths, checklist, summary)
    print(
        "[ccusdt_goal_completion_audit_universe] "
        f"status={summary['completion_status']} rows={len(checklist)} wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
