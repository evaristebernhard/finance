#!/usr/bin/env python
"""CCUSDT V2 taker fallback audit.

Research-only check for the obvious follow-up after maker queue-fill no-go:
could the observed information edge survive immediate crossing / taker-style
costs instead?

This script reuses the v2 quote-transition entry labels and framework scorecard.
It does not model depth sweep slippage, real venue fees, order acknowledgements,
or live latency. Positive rows are diagnostic only and must still pass the
framework controls, sample, tail, and risk gates.
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


GUARDRAIL = "research_only_taker_fallback_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_taker_fallback_audit_v1"
FRAMEWORK_RUN_TAG = "20260518_ccusdt_v2_framework_v1"


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    framework_run_tag: str
    run_tag: str

    @property
    def entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_quote_transition_labels_{self.framework_run_tag}.csv"

    @property
    def framework_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_scorecard_{self.framework_run_tag}.csv"

    @property
    def taker_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_taker_fallback_summary_{self.run_tag}.csv"

    @property
    def taker_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_taker_fallback_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_taker_fallback_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-taker-fallback-audit-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 taker fallback audit.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--framework-run-tag", default=FRAMEWORK_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--min-large-sample", type=int, default=500)
    parser.add_argument("--min-sparse-sample", type=int, default=100)
    parser.add_argument("--tail-share-limit", type=float, default=0.85)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


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


def cvar(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def top_share(values: Iterable[float] | np.ndarray, top_frac: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    total = float(arr.sum()) if len(arr) else np.nan
    if not len(arr) or not np.isfinite(total) or total <= 0:
        return np.nan
    n = max(1, int(np.ceil(len(arr) * top_frac)))
    winners = np.sort(arr)[-n:]
    return float(winners.sum() / total)


def summarize_taker(entries: pd.DataFrame, framework_scorecard: pd.DataFrame, args: argparse.Namespace, run_tag: str) -> pd.DataFrame:
    group_cols = ["fold", "trigger_class", "entry_quality_bin"]
    rows: list[dict[str, object]] = []
    controls = framework_scorecard.set_index(group_cols)
    for key, g in entries.groupby(group_cols, sort=True):
        taker = pd.to_numeric(g["fixed_net_taker_bps"], errors="coerce")
        gross = pd.to_numeric(g["fixed_gross_bps"], errors="coerce")
        rec = controls.loc[key] if key in controls.index else pd.Series(dtype=object)
        trigger = str(key[1])
        sparse_family = "stale" in trigger or "event_active" in trigger
        min_needed = args.min_sparse_sample if sparse_family else args.min_large_sample
        sample_pass = len(g) >= min_needed
        mean = finite_mean(taker)
        mean_plus2 = mean - 2.0 if np.isfinite(mean) else np.nan
        share = top_share(taker)
        economics_pass = bool(np.isfinite(mean) and mean > 2.0)
        stress_pass = bool(np.isfinite(mean_plus2) and mean_plus2 > 0.0)
        tail_pass = bool(np.isfinite(share) and share <= args.tail_share_limit)
        controls_pass = bool(rec.get("controls_pass", False))
        residual_pass = bool(rec.get("residual_pass", False))
        risk_pass = bool(rec.get("risk_pass", False))
        promoted_by_taker = bool(
            sample_pass and economics_pass and stress_pass and controls_pass and residual_pass and tail_pass and risk_pass
        )
        rows.append(
            {
                "run_tag": run_tag,
                "framework_run_tag": FRAMEWORK_RUN_TAG,
                "guardrail": GUARDRAIL,
                "fold": key[0],
                "trigger_class": key[1],
                "entry_quality_bin": key[2],
                "entries": int(len(g)),
                "sparse_family": sparse_family,
                "min_entries_required": min_needed,
                "taker_net_mean_bps": mean,
                "taker_net_plus2_mean_bps": mean_plus2,
                "taker_net_median_bps": finite_quantile(taker, 0.50),
                "taker_net_cvar10_bps": cvar(taker, 0.10),
                "taker_net_p10_bps": finite_quantile(taker, 0.10),
                "taker_gt_2bps_rate": safe_rate(taker > 2.0),
                "gross_mean_bps": finite_mean(gross),
                "top10_taker_share_of_total_net": share,
                "framework_scorecard_status": rec.get("scorecard_status", ""),
                "framework_controls_pass": controls_pass,
                "framework_residual_pass": residual_pass,
                "framework_risk_pass": risk_pass,
                "sample_pass": sample_pass,
                "economics_pass": economics_pass,
                "stress_pass": stress_pass,
                "tail_pass": tail_pass,
                "taker_promote_gate": promoted_by_taker,
                "taker_fallback_status": "taker_fallback_research_continue" if promoted_by_taker else "taker_fallback_no_go",
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values(
        ["taker_promote_gate", "taker_net_mean_bps", "taker_net_plus2_mean_bps", "entries"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def make_scorecard(summary: pd.DataFrame, run_tag: str) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for _, row in summary.iterrows():
        fail_reasons: list[str] = []
        for col, label in [
            ("sample_pass", "sample"),
            ("economics_pass", "economics"),
            ("stress_pass", "plus2_stress"),
            ("framework_controls_pass", "controls"),
            ("framework_residual_pass", "residual"),
            ("tail_pass", "tail"),
            ("framework_risk_pass", "risk"),
        ]:
            if not bool(row[col]):
                fail_reasons.append(label)
        rows.append(
            {
                "run_tag": run_tag,
                "framework_run_tag": row["framework_run_tag"],
                "guardrail": GUARDRAIL,
                "fold": row["fold"],
                "trigger_class": row["trigger_class"],
                "entry_quality_bin": row["entry_quality_bin"],
                "entries": int(row["entries"]),
                "taker_net_mean_bps": row["taker_net_mean_bps"],
                "taker_net_plus2_mean_bps": row["taker_net_plus2_mean_bps"],
                "taker_net_median_bps": row["taker_net_median_bps"],
                "taker_net_cvar10_bps": row["taker_net_cvar10_bps"],
                "taker_gt_2bps_rate": row["taker_gt_2bps_rate"],
                "top10_taker_share_of_total_net": row["top10_taker_share_of_total_net"],
                "sample_pass": bool(row["sample_pass"]),
                "economics_pass": bool(row["economics_pass"]),
                "stress_pass": bool(row["stress_pass"]),
                "controls_pass": bool(row["framework_controls_pass"]),
                "residual_pass": bool(row["framework_residual_pass"]),
                "tail_pass": bool(row["tail_pass"]),
                "risk_pass": bool(row["framework_risk_pass"]),
                "taker_promote_gate": bool(row["taker_promote_gate"]),
                "fail_reasons": ",".join(fail_reasons),
                "taker_fallback_status": row["taker_fallback_status"],
            }
        )
    return pd.DataFrame(rows)


def write_report(paths: Paths, summary: pd.DataFrame, scorecard: pd.DataFrame, args: argparse.Namespace) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Taker Fallback Audit")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from framework run `{paths.framework_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This pass asks whether immediate crossing can rescue the signal after maker queue-fill no-go. "
        "It uses the framework's `fixed_net_taker_bps` labels and inherits framework controls/risk gates."
    )
    lines.append("")
    lines.append("## Taker Scorecard")
    lines.append("")
    if scorecard.empty:
        lines.append("_No scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                scorecard.sort_values(
                    ["taker_promote_gate", "taker_net_mean_bps", "taker_net_plus2_mean_bps"],
                    ascending=[False, False, False],
                ),
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "entries",
                    "taker_net_mean_bps",
                    "taker_net_plus2_mean_bps",
                    "taker_net_median_bps",
                    "taker_gt_2bps_rate",
                    "top10_taker_share_of_total_net",
                    "sample_pass",
                    "economics_pass",
                    "stress_pass",
                    "controls_pass",
                    "tail_pass",
                    "risk_pass",
                    "fail_reasons",
                    "taker_fallback_status",
                ],
                35,
            )
        )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    promoted = int(scorecard["taker_promote_gate"].sum()) if not scorecard.empty else 0
    if promoted:
        lines.append(
            "At least one taker diagnostic row passed the local gate, but it is still research-only until real fees, "
            "depth/slippage, and fresh walk-forward validation are added."
        )
    else:
        lines.append(
            "No taker fallback row passes the combined sample, economics, stress, control, tail, and risk gates. "
            "Crossing the spread does not rescue the current CCUSDT candidates."
        )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.taker_summary_csv, paths.taker_scorecard_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(f"python scripts/ccusdt_v2_taker_fallback_audit.py --run-tag {paths.run_tag}")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, summary: pd.DataFrame, scorecard: pd.DataFrame, args: argparse.Namespace) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(paths.taker_summary_csv, index=False)
    scorecard.to_csv(paths.taker_scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "framework_run_tag": paths.framework_run_tag,
        "guardrail": GUARDRAIL,
        "summary_rows": int(len(summary)),
        "scorecard_rows": int(len(scorecard)),
        "taker_promote_gate_rows": int(scorecard["taker_promote_gate"].sum()) if not scorecard.empty else 0,
        "min_large_sample": args.min_large_sample,
        "min_sparse_sample": args.min_sparse_sample,
        "tail_share_limit": args.tail_share_limit,
        "outputs": {
            "taker_summary_csv": str(paths.taker_summary_csv),
            "taker_scorecard_csv": str(paths.taker_scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, summary, scorecard, args)


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        framework_run_tag=args.framework_run_tag,
        run_tag=args.run_tag,
    )
    entries = pd.read_csv(paths.entries_csv)
    framework_scorecard = pd.read_csv(paths.framework_scorecard_csv)
    summary = summarize_taker(entries, framework_scorecard, args, args.run_tag)
    scorecard = make_scorecard(summary, args.run_tag)
    write_outputs(paths, summary, scorecard, args)
    print(f"[ccusdt_taker_fallback] scorecard rows={len(scorecard)}", flush=True)
    print(f"[ccusdt_taker_fallback] promote gate rows={int(scorecard['taker_promote_gate'].sum())}", flush=True)
    print(f"[ccusdt_taker_fallback] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
