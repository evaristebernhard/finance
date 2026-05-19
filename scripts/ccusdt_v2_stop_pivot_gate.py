#!/usr/bin/env python
"""Machine-readable stop/pivot gate for the CCUSDT V2 research path."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_stop_pivot_gate_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_stop_pivot_gate_absorption_reversal_v1"


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def gate_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_stop_pivot_gate_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_stop_pivot_gate_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-stop-pivot-gate-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a stop/pivot gate from current CCUSDT V2 evidence.")
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


def fmt(value: Any, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def count_bool(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int(frame[column].astype(bool).sum())


def max_num(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return float("nan")
    return float(pd.to_numeric(frame[column], errors="coerce").max())


def gate_row(
    gate: str,
    evidence: str,
    observed: str,
    pass_condition: str,
    status: str,
    unlock_condition: str,
) -> dict[str, str]:
    return {
        "gate": gate,
        "evidence": evidence,
        "observed": observed,
        "pass_condition": pass_condition,
        "status": status,
        "unlock_condition": unlock_condition,
    }


def build_gate(paths: Paths) -> tuple[pd.DataFrame, dict[str, Any]]:
    date_dir = paths.date_dir
    framework = read_csv(date_dir / "ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv")
    l2 = read_csv(date_dir / "ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv")
    repair = read_csv(date_dir / "ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv")
    taker = read_csv(date_dir / "ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv")
    ccusdt_env = read_csv(date_dir / "ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv")
    universe_100 = read_csv(date_dir / "ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.csv")
    btc_queue = read_csv(date_dir / "ccusdt_v2_queue_release_scorecard_20260518_ccusdt_v2_queue_release_pivot_btcusdc_tob_fast_v1.csv")
    btc_tob = read_csv(date_dir / "ccusdt_v2_tob_factor_scorecard_20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1.csv")
    cross_market = read_csv(date_dir / "ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv")
    absorption = read_csv(date_dir / "ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv")
    completion = read_first_json(
        [
            date_dir / "ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_absorption_reversal_v1.json",
            date_dir / "ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_oos_day20260517_probe_v1.json",
            date_dir / "ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_universe_continuation_v1.json",
        ]
    )
    external_acquisition = read_json(date_dir / "ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json")
    oos_size_probe = read_json(date_dir / "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json")
    oos_day20260517_probe = read_json(date_dir / "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json")
    oos_download = read_json(date_dir / "bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json")
    oos_envelope = read_json(date_dir / "ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json")
    ccusdt_oos_env = read_json(date_dir / "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json")
    ccusdt_oos_env_target10 = read_json(date_dir / "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json")
    oos_envelope_target10 = read_json(date_dir / "ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json")
    oos_envelope_target5 = read_json(date_dir / "ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json")

    framework_promoted = (
        int(framework["scorecard_status"].astype(str).eq("promote").sum())
        if not framework.empty and "scorecard_status" in framework
        else 0
    )
    l2_non_no_go = (
        int(l2["l2_queue_fill_status"].astype(str).ne("l2_queue_fill_no_go").sum())
        if not l2.empty and "l2_queue_fill_status" in l2
        else 0
    )
    repair_pass = count_bool(repair, "passes_execution_gates")
    taker_promote = count_bool(taker, "taker_promote_gate")
    ccusdt_env_status = (
        str(ccusdt_env["liquidity_envelope_status"].iloc[0])
        if not ccusdt_env.empty and "liquidity_envelope_status" in ccusdt_env
        else "missing"
    )
    universe_100_candidates = count_bool(universe_100, "pre_alpha_gate")
    btc_queue_promote = count_bool(btc_queue, "pivot_promote_gate")
    btc_tob_promote = count_bool(btc_tob, "tob_factor_promote_gate")
    cross_market_promote = count_bool(cross_market, "cross_market_promote_gate")
    absorption_promote = count_bool(absorption, "absorption_promote_gate")
    external_planned = int(external_acquisition.get("planned_rows", 0) or 0)
    oos_available = int(oos_size_probe.get("available_rows", 0) or 0)
    oos_missing = int(oos_size_probe.get("missing_rows", 0) or 0)
    oos_total_gb = float(oos_size_probe.get("total_gb", 0.0) or 0.0)
    oos17_planned = int(oos_day20260517_probe.get("planned_rows_probed", 0) or 0)
    oos17_available = int(oos_day20260517_probe.get("available_rows", 0) or 0)
    oos17_missing = int(oos_day20260517_probe.get("missing_rows", 0) or 0)
    oos17_errors = int(oos_day20260517_probe.get("error_rows", 0) or 0)
    oos17_total_gb = float(oos_day20260517_probe.get("total_gb", 0.0) or 0.0)
    oos_download_counts = dict(oos_download.get("counts", {}))
    oos_candidates = list(oos_envelope.get("pre_alpha_candidate_symbols", []))
    ccusdt_oos_status = str(ccusdt_oos_env.get("liquidity_envelope_status", "missing"))
    ccusdt_oos_target10_status = str(ccusdt_oos_env_target10.get("liquidity_envelope_status", "missing"))
    oos_target10_candidates = list(oos_envelope_target10.get("pre_alpha_candidate_symbols", []))
    oos_target5_candidates = list(oos_envelope_target5.get("pre_alpha_candidate_symbols", []))
    completion_status = str(completion.get("completion_status", "missing"))

    rows = [
        gate_row(
            "current_framework_promotion",
            "ccusdt_v2_scorecard_20260518_ccusdt_v2_framework_v1.csv",
            f"promoted_rows={framework_promoted} best_net_realistic_mean_bps={fmt(max_num(framework, 'net_realistic_mean_bps'))}",
            "promoted_rows > 0 and promoted rows clear real-cost +2 bps gates",
            "fail",
            "introduce a new mechanism or new out-of-sample data, then rerun the V2 framework.",
        ),
        gate_row(
            "practical_maker_execution",
            "ccusdt_v2_l2_queue_fill_scorecard_20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.csv",
            f"non_no_go_rows={l2_non_no_go} best_per_signal_net_bps={fmt(max_num(l2, 'per_signal_net_mean_bps'))}",
            "at least one practical L2 queue-fill row is non-no-go and exceeds +2 bps per signal",
            "fail",
            "do not retune maker assumptions; require measured latency/fee/fill evidence or a new entry mechanism.",
        ),
        gate_row(
            "fill_aware_repair",
            "ccusdt_v2_fill_repair_scorecard_20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.csv",
            f"execution_pass_rows={repair_pass}",
            "at least one pre-declared entry-quality repair passes execution gates",
            "fail",
            "do not add more post-hoc filters on the same candidate family.",
        ),
        gate_row(
            "taker_fallback",
            "ccusdt_v2_taker_fallback_scorecard_20260518_ccusdt_v2_taker_fallback_audit_v1.csv",
            f"taker_promote_rows={taker_promote} best_taker_mean_bps={fmt(max_num(taker, 'taker_net_mean_bps'))}",
            "at least one taker row passes sample, controls, tail, risk, and cost gates",
            "fail",
            "do not switch to crossing unless fee/spread assumptions or signal mechanism materially change.",
        ),
        gate_row(
            "ccusdt_liquidity_envelope",
            "ccusdt_v2_liquidity_envelope_scorecard_20260518_ccusdt_v2_liquidity_envelope_audit_v1.csv",
            f"status={ccusdt_env_status}",
            "CCUSDT passes target-notional spread, depth, activity, and execution envelope",
            "fail",
            "continue only with a smaller validated notional, a different instrument, or new liquidity regime evidence.",
        ),
        gate_row(
            "bullish_universe_envelope",
            "ccusdt_v2_universe_liquidity_envelope_scorecard_20260518_ccusdt_v2_universe_liquidity_envelope_tob_universe_v1.csv",
            f"target100_candidates={universe_100_candidates}",
            "at least one local universe symbol passes the $100 pre-alpha execution envelope",
            "fail",
            "screen a broader venue/symbol universe before any alpha search.",
        ),
        gate_row(
            "btcusdc_structural_followup",
            "ccusdt_v2_queue_release_scorecard_*; ccusdt_v2_tob_factor_scorecard_*",
            f"btc_queue_promote={btc_queue_promote} btc_tob_promote={btc_tob_promote}",
            "BTCUSDC small-notional diagnostics promote at least one structurally different row",
            "fail",
            "do not expand BTC incremental L2 until a top-of-book mechanism clears gates.",
        ),
        gate_row(
            "same_venue_cross_market",
            "ccusdt_v2_cross_market_scorecard_20260518_ccusdt_v2_cross_market_lead_lag_btc_eth_sol_smoke_v1.csv",
            f"cross_market_promote_rows={cross_market_promote} best_net_mean_bps={fmt(max_num(cross_market, 'net_mean_bps'))}",
            "at least one leader row survives controls and real-cost +2 bps gates",
            "fail",
            "same-venue leaders are not enough; require external venue data or a materially stronger leader mechanism.",
        ),
        gate_row(
            "absorption_reversal_structural_pivot",
            "ccusdt_v2_absorption_reversal_scorecard_20260518_ccusdt_v2_absorption_reversal_pivot_v1.csv",
            f"rows={len(absorption)} promote_rows={absorption_promote} best_net_mean_bps={fmt(max_num(absorption, 'net_mean_bps'))} best_gross_mean_bps={fmt(max_num(absorption, 'gross_mean_bps'))}",
            "a structurally new absorption/replenishment entry row survives controls and real-cost +2 bps gates",
            "fail" if not absorption.empty and absorption_promote == 0 else ("pass" if absorption_promote else "missing"),
            "do not tune absorption thresholds on the same validation rows; require a new mechanism, better execution envelope, or new data/access.",
        ),
        gate_row(
            "external_cc_l2_acquisition",
            "ccusdt_v2_external_acquisition_summary_20260518_ccusdt_v2_external_acquisition_plan_v1.json",
            f"planned_rows={external_planned} blocked_access_rows={external_acquisition.get('blocked_access_rows', 0)}",
            "planned_rows > 0 so size probe/download can proceed",
            "fail",
            "obtain Tardis access for at least one external CC orderbook venue, then run size probe before download.",
        ),
        gate_row(
            "new_oos_days_unlock_state",
            "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_days_size_probe_v1.json",
            f"available_rows={oos_available} missing_rows={oos_missing} total_gb={fmt(oos_total_gb, 4)}",
            "new OOS files are downloaded, rebuilt, and pass the same V2 gates",
            "unlock_followed_up_failed_envelope" if oos_download and not oos_candidates else ("unlock_available_not_evaluated" if oos_available else "not_available"),
            "do not proceed to alpha modeling from the OOS day unless the envelope produces pre-alpha candidates.",
        ),
        gate_row(
            "oos_day20260517_availability",
            "ccusdt_v2_universe_size_probe_summary_20260518_ccusdt_v2_oos_day20260517_size_probe_v1.json",
            f"planned={oos17_planned} available={oos17_available} missing={oos17_missing} errors={oos17_errors} total_gb={fmt(oos17_total_gb, 4)}",
            "new OOS day has accessible non-empty core L2 files before download/envelope follow-up",
            "unlock_available_not_evaluated" if oos17_available else ("not_available" if oos_day20260517_probe else "missing"),
            "wait for the day to become available, or test a different new day/instrument through the same no-download gate.",
        ),
        gate_row(
            "oos_day20260516_envelope",
            "bonk_bullish_l2_download_completion_20260518_ccusdt_v2_oos_day20260516_download_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_v1.json",
            f"download_counts={oos_download_counts} pre_alpha_candidates={','.join(oos_candidates)}",
            "OOS day produces at least one pre-alpha liquidity candidate before alpha modeling",
            "fail" if oos_download and not oos_candidates else ("pass" if oos_candidates else "missing"),
            "requires a new OOS/instrument envelope pass before framework modeling.",
        ),
        gate_row(
            "ccusdt_oos_day20260516_liquidity_envelope",
            "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_v1.json",
            f"status={ccusdt_oos_status}",
            "canonical CCUSDT OOS-expanded window passes the execution envelope",
            "fail" if ccusdt_oos_status == "liquidity_envelope_no_go" else ("pass" if ccusdt_oos_env else "missing"),
            "requires CCUSDT or a replacement instrument to pass execution envelope before alpha modeling.",
        ),
        gate_row(
            "oos_target_notional_sensitivity",
            "ccusdt_v2_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_liquidity_envelope_target10_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target10_v1.json; ccusdt_v2_universe_liquidity_envelope_summary_20260518_ccusdt_v2_oos_day20260516_envelope_target5_v1.json",
            f"ccusdt_target10={ccusdt_oos_target10_status} small_target10={','.join(oos_target10_candidates)} small_target5={','.join(oos_target5_candidates)}",
            "smaller target notional produces a pre-alpha candidate before modeling",
            "fail" if ccusdt_oos_env_target10 and not oos_target10_candidates and not oos_target5_candidates else "missing",
            "requires smaller-notional envelope pass before alpha modeling.",
        ),
        gate_row(
            "active_goal_completion",
            "ccusdt_v2_goal_completion_audit_20260518_ccusdt_v2_goal_completion_audit_universe_continuation_v1.json",
            f"completion_status={completion_status}",
            "completion_status == achieved",
            "fail",
            "do not mark the active goal complete until the prompt-to-artifact audit passes.",
        ),
    ]
    frame = pd.DataFrame(rows)
    stop_required = bool((frame["status"].astype(str) == "fail").any())
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "decision": "stop_current_ccusdt_path_pivot_or_new_data_required" if stop_required else "continue_current_path",
        "stop_required": stop_required,
        "failed_gates": frame.loc[frame["status"].eq("fail"), "gate"].tolist(),
        "blocked_research_modes": [
            "tp_sl_grid_retuning_on_current_candidates",
            "post_hoc_fill_filters_on_same_validation_entries",
            "maker_taker_assumption_switching_without_new_execution_evidence",
            "same_venue_cross_market_tuning_without_external_data_or_new_mechanism",
            "absorption_threshold_tuning_on_same_validation_entries",
            "alpha_search_before_execution_envelope_passes",
        ],
        "allowed_unlocks": [
            "new_accessible_external_cc_l2_data_then_size_probe_download_cross_venue_framework",
            "new_out_of_sample_or_new_instrument_day_that_passes_pre_alpha_envelope_then_full_v2_framework_and_execution_audit",
            "new_instrument_or_venue_that_passes_execution_envelope_before_alpha_search",
            "structurally_new_entry_mechanism_then_same_walk_forward_cost_control_tail_gates",
        ],
        "absorption_reversal": {
            "scorecard_rows": int(len(absorption)),
            "promote_rows": absorption_promote,
            "best_net_mean_bps": max_num(absorption, "net_mean_bps"),
            "best_gross_mean_bps": max_num(absorption, "gross_mean_bps"),
        },
        "oos_day20260517_probe": {
            "planned_rows_probed": oos17_planned,
            "available_rows": oos17_available,
            "missing_rows": oos17_missing,
            "error_rows": oos17_errors,
            "total_gb": oos17_total_gb,
        },
        "outputs": {
            "gate_csv": str(paths.gate_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    return frame, summary


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 60) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def write_report(paths: Paths, frame: pd.DataFrame, summary: dict[str, Any]) -> None:
    lines: list[str] = [
        "# CCUSDT V2 Stop/Pivot Gate",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decision",
        "",
        f"Decision: `{summary['decision']}`.",
        "",
        "The current CCUSDT execution path should not continue by tuning the same candidate family. Resume only if one of the explicit unlock conditions is satisfied and then rerun the same walk-forward, cost, control, tail, and execution gates.",
        "",
        "## Gate Checklist",
        "",
        *markdown_table(frame, ["gate", "evidence", "observed", "pass_condition", "status", "unlock_condition"], 80),
        "",
        "## Blocked Research Modes",
        "",
        *[f"- `{item}`" for item in summary["blocked_research_modes"]],
        "",
        "## Allowed Unlocks",
        "",
        *[f"- `{item}`" for item in summary["allowed_unlocks"]],
        "",
        "## Output Tables",
        "",
        f"- `{paths.gate_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_stop_pivot_gate.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, frame: pd.DataFrame, summary: dict[str, Any]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(paths.gate_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, frame, summary)


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    frame, summary = build_gate(paths)
    write_outputs(paths, frame, summary)
    print(
        "[ccusdt_stop_pivot_gate] "
        f"decision={summary['decision']} failed_gates={len(summary['failed_gates'])} wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
