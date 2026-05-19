#!/usr/bin/env python
"""Gross/cost decomposition for top-of-book factor framework rows."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_tob_factor_decomposition_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_tob_factor_decomp_btcusdc_smoke_v1"
SOURCE_RUN_TAG = "20260518_ccusdt_v2_tob_factor_framework_btcusdc_smoke_v1"
EPS = 1e-12


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    source_run_tag: str
    run_tag: str

    @property
    def panel_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_panel_{self.source_run_tag}.csv"

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_events_{self.source_run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_scorecard_{self.source_run_tag}.csv"

    @property
    def decomposition_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_decomposition_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_decomposition_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-tob-factor-decomposition-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decompose top-of-book factor scorecard rows into gross/cost/net.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    return fill_base.finite_mean(values)


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    return fill_base.finite_quantile(values, q)


def fmt_num(value: object, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def read_inputs(paths: Paths) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if not paths.panel_csv.exists():
        raise FileNotFoundError(paths.panel_csv)
    if not paths.events_csv.exists():
        raise FileNotFoundError(paths.events_csv)
    if not paths.scorecard_csv.exists():
        raise FileNotFoundError(paths.scorecard_csv)
    panel_cols = ["row_id", "date", "second", "mid_price"]
    event_cols = [
        "fold",
        "date",
        "row_id",
        "trigger_class",
        "direction",
        "threshold_quantile",
        "horizon_sec",
        "net_bps",
    ]
    panel = pd.read_csv(paths.panel_csv, usecols=panel_cols)
    events = pd.read_csv(paths.events_csv, usecols=event_cols)
    scorecard = pd.read_csv(paths.scorecard_csv)
    return panel, events, scorecard


def add_gross_cost(panel: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values("row_id").set_index("row_id", drop=False)
    rows: list[pd.DataFrame] = []
    for horizon, group in events.groupby("horizon_sec", sort=True):
        h = int(round(float(horizon)))
        entry = panel.reindex(group["row_id"].astype("int64").to_numpy())
        future = panel.reindex(group["row_id"].astype("int64").to_numpy() + h)
        work = group.reset_index(drop=True).copy()
        same_date = entry["date"].to_numpy(dtype=str) == future["date"].to_numpy(dtype=str)
        entry_mid = entry["mid_price"].to_numpy(dtype="float64")
        future_mid = future["mid_price"].to_numpy(dtype="float64")
        valid = same_date & np.isfinite(entry_mid) & np.isfinite(future_mid) & (entry_mid > 0) & (future_mid > 0)
        work = work.loc[valid].copy()
        gross = work["direction"].to_numpy(dtype="float64") * 10_000.0 * np.log(
            np.maximum(future_mid[valid], EPS) / np.maximum(entry_mid[valid], EPS)
        )
        work["gross_bps"] = gross
        work["cost_bps"] = gross - work["net_bps"].to_numpy(dtype="float64")
        work["required_gross_for_net2_bps"] = work["cost_bps"] + 2.0
        work["gross_shortfall_to_net2_bps"] = work["gross_bps"] - work["required_gross_for_net2_bps"]
        rows.append(work)
    return pd.concat(rows, ignore_index=True) if rows else events.head(0).copy()


def decompose(labeled: pd.DataFrame, scorecard: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    keys = ["fold", "trigger_class", "horizon_sec", "threshold_quantile"]
    for key, group in labeled.groupby(keys, sort=True):
        row = {
            "run_tag": RUN_TAG,
            "guardrail": GUARDRAIL,
            "fold": key[0],
            "trigger_class": key[1],
            "horizon_sec": key[2],
            "threshold_quantile": key[3],
            "entries": int(len(group)),
            "gross_mean_bps": finite_mean(group["gross_bps"]),
            "gross_median_bps": finite_quantile(group["gross_bps"], 0.50),
            "cost_mean_bps": finite_mean(group["cost_bps"]),
            "net_mean_bps": finite_mean(group["net_bps"]),
            "net_median_bps": finite_quantile(group["net_bps"], 0.50),
            "required_gross_for_net2_mean_bps": finite_mean(group["required_gross_for_net2_bps"]),
            "gross_shortfall_to_net2_mean_bps": finite_mean(group["gross_shortfall_to_net2_bps"]),
        }
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    merge_cols = keys
    keep_cols = merge_cols + [
        "sample_pass",
        "economics_pass",
        "controls_pass",
        "median_pass",
        "risk_pass",
        "tob_factor_promote_gate",
        "tob_factor_status",
        "matched_random_prob_ge_signal",
        "signal_minus_random_p50_bps",
    ]
    keep_cols = [col for col in keep_cols if col in scorecard.columns]
    out = out.merge(scorecard.loc[:, keep_cols], on=merge_cols, how="left")
    return out.sort_values(["net_mean_bps", "gross_shortfall_to_net2_mean_bps"], ascending=[False, False])


def write_report(paths: Paths, decomp: pd.DataFrame, summary: dict[str, object]) -> None:
    lines: list[str] = [
        "# CCUSDT V2 Top-Of-Book Factor Decomposition",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decision",
        "",
        f"Promote-gate rows in source scorecard: `{summary['promote_gate_rows']}`.",
        "",
        "The top rows show small positive gross movement at best, but the gross move is far below the cost plus `2` bps hurdle.",
        "",
        "## Decomposition",
        "",
        *markdown_table(
            decomp,
            [
                "fold",
                "trigger_class",
                "horizon_sec",
                "entries",
                "gross_mean_bps",
                "cost_mean_bps",
                "net_mean_bps",
                "required_gross_for_net2_mean_bps",
                "gross_shortfall_to_net2_mean_bps",
                "matched_random_prob_ge_signal",
                "signal_minus_random_p50_bps",
                "tob_factor_promote_gate",
            ],
            40,
        ),
        "",
        "## Output Tables",
        "",
        f"- `{paths.decomposition_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_tob_factor_decomposition.py --source-run-tag {paths.source_run_tag} --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, decomp: pd.DataFrame) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    decomp.to_csv(paths.decomposition_csv, index=False)
    promoted = int(decomp.get("tob_factor_promote_gate", pd.Series(dtype=bool)).astype(bool).sum()) if not decomp.empty else 0
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "source_run_tag": paths.source_run_tag,
        "rows": int(len(decomp)),
        "promote_gate_rows": promoted,
        "best_net_mean_bps": float(pd.to_numeric(decomp.get("net_mean_bps", pd.Series(dtype=float)), errors="coerce").max()) if not decomp.empty else None,
        "best_gross_mean_bps": float(pd.to_numeric(decomp.get("gross_mean_bps", pd.Series(dtype=float)), errors="coerce").max()) if not decomp.empty else None,
        "outputs": {
            "decomposition_csv": str(paths.decomposition_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, decomp, summary)


def main() -> None:
    args = parse_args()
    global RUN_TAG
    RUN_TAG = args.run_tag
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        source_run_tag=args.source_run_tag,
        run_tag=args.run_tag,
    )
    panel, events, scorecard = read_inputs(paths)
    labeled = add_gross_cost(panel, events)
    decomp = decompose(labeled, scorecard)
    write_outputs(paths, decomp)
    print(
        "[ccusdt_tob_factor_decomposition] "
        f"rows={len(decomp)} promote={int(decomp['tob_factor_promote_gate'].astype(bool).sum()) if not decomp.empty and 'tob_factor_promote_gate' in decomp else 0} "
        f"wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
