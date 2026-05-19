#!/usr/bin/env python
"""CCUSDT V2 execution failure decomposition.

Quantifies why the current CCUSDT candidates fail the real-cost `>2bps`
capture objective after all-practical L2 queue-fill and taker fallback audits.

The core maker identity is:

    per_signal_net = fill_rate * E[net_bps | filled]

This script computes the gap to a 2 bps per-signal target and the impossible or
required fill/net levels implied by the current practical execution evidence.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_execution_failure_decomposition_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_execution_failure_decomp_v1"
FRAMEWORK_RUN_TAG = "20260518_ccusdt_v2_framework_v1"
L2_QUEUE_RUN_TAG = "20260518_ccusdt_v2_l2_queue_fill_all_practical_v1"
TAKER_RUN_TAG = "20260518_ccusdt_v2_taker_fallback_audit_v1"
TARGET_BPS = 2.0


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    framework_run_tag: str
    l2_queue_run_tag: str
    taker_run_tag: str
    run_tag: str

    @property
    def framework_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_scorecard_{self.framework_run_tag}.csv"

    @property
    def l2_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_scorecard_{self.l2_queue_run_tag}.csv"

    @property
    def taker_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_taker_fallback_scorecard_{self.taker_run_tag}.csv"

    @property
    def decomposition_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_execution_failure_decomposition_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_execution_failure_decomposition_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-execution-failure-decomposition-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 execution failure decomposition.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--framework-run-tag", default=FRAMEWORK_RUN_TAG)
    parser.add_argument("--l2-queue-run-tag", default=L2_QUEUE_RUN_TAG)
    parser.add_argument("--taker-run-tag", default=TAKER_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--target-bps", type=float, default=TARGET_BPS)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def fmt_num(value: object, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def safe_float(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out if np.isfinite(out) else np.nan


def build_decomposition(paths: Paths, target_bps: float) -> pd.DataFrame:
    framework = pd.read_csv(paths.framework_scorecard_csv)
    maker = pd.read_csv(paths.l2_scorecard_csv)
    taker = pd.read_csv(paths.taker_scorecard_csv)

    keys = ["fold", "trigger_class", "entry_quality_bin"]
    framework_cols = [
        *keys,
        "scorecard_status",
        "net_realistic_mean_bps",
        "net_realistic_plus2_mean_bps",
        "controls_pass",
        "residual_pass",
        "risk_pass",
        "tail_pass",
    ]
    taker_cols = [
        *keys,
        "taker_net_mean_bps",
        "taker_net_plus2_mean_bps",
        "taker_net_median_bps",
        "taker_gt_2bps_rate",
        "top10_taker_share_of_total_net",
        "taker_promote_gate",
        "fail_reasons",
        "taker_fallback_status",
    ]
    maker_cols = [
        *keys,
        "signals",
        "fill_rate",
        "filled_net_mean_bps",
        "filled_net_p10_bps",
        "per_signal_net_mean_bps",
        "break_even_fee_for_2bps_mean",
        "l2_queue_fill_status",
    ]
    out = maker.loc[:, maker_cols].merge(framework.loc[:, framework_cols], on=keys, how="left")
    out = out.merge(taker.loc[:, taker_cols], on=keys, how="left")

    fill_rate = pd.to_numeric(out["fill_rate"], errors="coerce")
    filled_mean = pd.to_numeric(out["filled_net_mean_bps"], errors="coerce")
    per_signal = pd.to_numeric(out["per_signal_net_mean_bps"], errors="coerce")
    out["target_bps"] = target_bps
    out["maker_gap_to_target_bps"] = target_bps - per_signal
    out["required_filled_net_at_current_fill_rate_bps"] = np.where(
        fill_rate > 0,
        target_bps / fill_rate,
        np.inf,
    )
    out["required_fill_rate_at_current_filled_net"] = np.where(
        filled_mean > 0,
        target_bps / filled_mean,
        np.inf,
    )
    out["required_fill_rate_feasible"] = out["required_fill_rate_at_current_filled_net"] <= 1.0
    out["filled_mean_positive"] = filled_mean > 0
    out["per_signal_positive"] = per_signal > 0
    out["maker_failure_mode"] = np.select(
        [
            filled_mean <= 0,
            out["required_fill_rate_at_current_filled_net"] > 1.0,
            out["required_filled_net_at_current_fill_rate_bps"] > 50.0,
        ],
        [
            "filled_net_nonpositive",
            "requires_impossible_fill_rate",
            "requires_extreme_filled_net",
        ],
        default="below_target",
    )
    out["taker_gap_to_target_bps"] = target_bps - pd.to_numeric(out["taker_net_mean_bps"], errors="coerce")
    out["execution_decomp_status"] = np.where(
        (out["per_signal_net_mean_bps"] > target_bps) | (out["taker_promote_gate"].astype(bool)),
        "unexpected_recheck",
        "execution_gap_not_repaired",
    )
    return out.sort_values(
        ["per_signal_net_mean_bps", "taker_net_mean_bps", "net_realistic_mean_bps"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def write_report(paths: Paths, decomp: pd.DataFrame, target_bps: float) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Execution Failure Decomposition")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append("Core maker identity:")
    lines.append("")
    lines.append("```text")
    lines.append("per_signal_net_bps = fill_rate * E[net_bps | filled]")
    lines.append("```")
    lines.append("")
    lines.append(f"Target per-signal capture: `{target_bps}` bps.")
    lines.append("")
    lines.append("## Maker Practical Gap")
    lines.append("")
    maker_cols = [
        "fold",
        "trigger_class",
        "entry_quality_bin",
        "signals",
        "fill_rate",
        "filled_net_mean_bps",
        "per_signal_net_mean_bps",
        "maker_gap_to_target_bps",
        "required_filled_net_at_current_fill_rate_bps",
        "required_fill_rate_at_current_filled_net",
        "maker_failure_mode",
    ]
    lines.extend(markdown_table(decomp.sort_values("per_signal_net_mean_bps", ascending=False), maker_cols, 25))
    lines.append("")
    lines.append("## Taker Fallback Context")
    lines.append("")
    taker_cols = [
        "fold",
        "trigger_class",
        "entry_quality_bin",
        "taker_net_mean_bps",
        "taker_net_plus2_mean_bps",
        "taker_net_median_bps",
        "top10_taker_share_of_total_net",
        "taker_promote_gate",
        "fail_reasons",
    ]
    lines.extend(markdown_table(decomp.sort_values("taker_net_mean_bps", ascending=False), taker_cols, 20))
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    best_maker = safe_float(decomp["per_signal_net_mean_bps"].max()) if not decomp.empty else np.nan
    best_taker_gate = bool(decomp["taker_promote_gate"].astype(bool).any()) if "taker_promote_gate" in decomp else False
    lines.append(
        f"Best practical maker per-signal net is `{fmt_num(best_maker)}` bps, below the `{fmt_num(target_bps)}` bps target. "
        f"Taker promote gate present: `{best_taker_gate}`. Current candidates remain execution-no-go."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.decomposition_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(
        f"python scripts/ccusdt_v2_execution_failure_decomposition.py --run-tag {paths.run_tag} --target-bps {target_bps:g}"
    )
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, decomp: pd.DataFrame, target_bps: float) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    decomp.to_csv(paths.decomposition_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "framework_run_tag": paths.framework_run_tag,
        "l2_queue_run_tag": paths.l2_queue_run_tag,
        "taker_run_tag": paths.taker_run_tag,
        "guardrail": GUARDRAIL,
        "target_bps": target_bps,
        "rows": int(len(decomp)),
        "best_maker_per_signal_net_bps": safe_float(decomp["per_signal_net_mean_bps"].max()) if not decomp.empty else np.nan,
        "best_taker_net_mean_bps": safe_float(decomp["taker_net_mean_bps"].max()) if not decomp.empty else np.nan,
        "taker_promote_gate_rows": int(decomp["taker_promote_gate"].astype(bool).sum()) if not decomp.empty else 0,
        "outputs": {
            "decomposition_csv": str(paths.decomposition_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, decomp, target_bps)


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        framework_run_tag=args.framework_run_tag,
        l2_queue_run_tag=args.l2_queue_run_tag,
        taker_run_tag=args.taker_run_tag,
        run_tag=args.run_tag,
    )
    decomp = build_decomposition(paths, args.target_bps)
    write_outputs(paths, decomp, args.target_bps)
    print(f"[ccusdt_exec_decomp] rows={len(decomp)}", flush=True)
    print(f"[ccusdt_exec_decomp] best maker per-signal={decomp['per_signal_net_mean_bps'].max():.4f}", flush=True)
    print(f"[ccusdt_exec_decomp] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
