#!/usr/bin/env python
"""Batch pre-alpha liquidity-envelope screen for the CCUSDT V2 universe pivot.

This script deliberately stops before alpha modeling. It answers a narrower
question: which locally downloaded Bullish symbols have enough spread, top-book
depth, and trade-arrival activity to justify running the heavier
entry-quality/exit-shape/risk-control framework?
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import ccusdt_v2_liquidity_envelope_audit as single


GUARDRAIL = "research_only_universe_liquidity_envelope_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_universe_liquidity_envelope_small_tier_v1"
DEFAULT_SYMBOLS = "SUIUSDC,DOGEUSDC,PEPE1MUSDC,SHIB1MUSDC,WIFUSDC"


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_universe_liquidity_envelope_daily_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_universe_liquidity_envelope_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_universe_liquidity_envelope_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-universe-liquidity-envelope-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch liquidity-envelope screen for locally downloaded Bullish symbols.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt_universe/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--target-notional-quote", type=float, default=100.0)
    parser.add_argument("--max-median-spread-bps", type=float, default=2.0)
    parser.add_argument("--max-p95-spread-bps", type=float, default=5.0)
    parser.add_argument("--min-depth-support-row-rate", type=float, default=0.95)
    parser.add_argument("--min-depth-support-day-rate", type=float, default=0.95)
    parser.add_argument("--min-dates", type=int, default=10)
    parser.add_argument("--min-median-trade-rows", type=int, default=100)
    parser.add_argument("--min-quote-match-rate", type=float, default=0.80)
    parser.add_argument("--min-top-trade-notional-rate-per-min", type=float, default=100.0)
    parser.add_argument("--quote-match-tolerance-sec", type=float, default=5.0)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_symbols(raw: str) -> list[str]:
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def finite_quantile(values: pd.Series, q: float) -> float:
    return single.finite_quantile(pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64"), q)


def finite_mean(values: pd.Series) -> float:
    return single.finite_mean(pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64"))


def safe_rate(values: pd.Series) -> float:
    return single.safe_rate(values.astype(bool).to_numpy())


def symbol_daily(symbol: str, paths: Paths, args: argparse.Namespace) -> pd.DataFrame:
    symbol_paths = single.Paths(
        data_root=paths.data_root,
        date_dir=paths.date_dir,
        doc_dir=paths.doc_dir,
        symbol=symbol,
        run_tag=paths.run_tag,
        l2_queue_run_tag="unused_for_universe_pre_alpha",
        taker_run_tag="unused_for_universe_pre_alpha",
        decomp_run_tag="unused_for_universe_pre_alpha",
    )
    daily = single.daily_metrics(symbol_paths, args)
    daily.insert(0, "universe_run_tag", paths.run_tag)
    daily["guardrail"] = GUARDRAIL
    return daily


def symbol_scorecard(symbol: str, daily: pd.DataFrame, args: argparse.Namespace) -> dict[str, object]:
    dates = int(len(daily))
    median_daily_median_spread = finite_quantile(daily["median_spread_bps"], 0.50)
    median_daily_p95_spread = finite_quantile(daily["p95_spread_bps"], 0.50)
    median_depth_p05 = finite_quantile(daily["top_depth_p05_quote"], 0.50)
    median_depth_median = finite_quantile(daily["top_depth_median_quote"], 0.50)
    depth_support_day_rate = safe_rate(daily["depth_support_day_pass"])
    median_trade_rows = finite_quantile(daily["trade_rows"], 0.50)
    mean_quote_match_rate = finite_mean(daily["quote_match_rate"])
    mean_top_trade_rate = finite_mean(daily["top_trade_rate_per_min"])
    mean_top_trade_notional_rate = finite_mean(daily["top_trade_notional_rate_per_min"])

    coverage_gate = bool(dates >= args.min_dates)
    spread_gate = bool(
        median_daily_median_spread <= args.max_median_spread_bps
        and median_daily_p95_spread <= args.max_p95_spread_bps
    )
    depth_gate = bool(depth_support_day_rate >= args.min_depth_support_day_rate)
    activity_gate = bool(
        median_trade_rows >= args.min_median_trade_rows
        and mean_quote_match_rate >= args.min_quote_match_rate
        and mean_top_trade_notional_rate >= args.min_top_trade_notional_rate_per_min
    )
    pre_alpha_gate = bool(coverage_gate and spread_gate and depth_gate and activity_gate)

    failed_gates = [
        gate
        for gate, passed in [
            ("coverage", coverage_gate),
            ("spread", spread_gate),
            ("depth", depth_gate),
            ("activity", activity_gate),
        ]
        if not passed
    ]

    if not coverage_gate:
        status = "missing_or_insufficient_coverage_no_go"
    elif not spread_gate and not depth_gate and not activity_gate:
        status = "spread_depth_activity_no_go"
    elif not spread_gate and not depth_gate:
        status = "spread_and_depth_no_go"
    elif not spread_gate and not activity_gate:
        status = "spread_and_activity_no_go"
    elif not depth_gate and not activity_gate:
        status = "depth_and_activity_no_go"
    elif not spread_gate:
        status = "spread_no_go"
    elif not depth_gate:
        status = "depth_no_go"
    elif not activity_gate:
        status = "thin_activity_no_go"
    else:
        status = "pre_alpha_liquidity_candidate"

    return {
        "run_tag": args.run_tag,
        "guardrail": GUARDRAIL,
        "symbol": symbol,
        "dates": dates,
        "target_notional_quote": args.target_notional_quote,
        "median_daily_median_spread_bps": median_daily_median_spread,
        "median_daily_p95_spread_bps": median_daily_p95_spread,
        "median_daily_top_depth_p05_quote": median_depth_p05,
        "median_daily_top_depth_median_quote": median_depth_median,
        "depth_support_day_rate": depth_support_day_rate,
        "median_trade_rows_per_day": median_trade_rows,
        "mean_quote_match_rate": mean_quote_match_rate,
        "mean_top_trade_rate_per_min": mean_top_trade_rate,
        "mean_top_trade_notional_rate_per_min": mean_top_trade_notional_rate,
        "coverage_gate": coverage_gate,
        "spread_gate": spread_gate,
        "depth_gate": depth_gate,
        "activity_gate": activity_gate,
        "pre_alpha_gate": pre_alpha_gate,
        "failed_gates": ",".join(failed_gates),
        "universe_liquidity_status": status,
    }


def error_scorecard(symbol: str, args: argparse.Namespace, error: Exception) -> dict[str, object]:
    return {
        "run_tag": args.run_tag,
        "guardrail": GUARDRAIL,
        "symbol": symbol,
        "dates": 0,
        "target_notional_quote": args.target_notional_quote,
        "median_daily_median_spread_bps": np.nan,
        "median_daily_p95_spread_bps": np.nan,
        "median_daily_top_depth_p05_quote": np.nan,
        "median_daily_top_depth_median_quote": np.nan,
        "depth_support_day_rate": np.nan,
        "median_trade_rows_per_day": np.nan,
        "mean_quote_match_rate": np.nan,
        "mean_top_trade_rate_per_min": np.nan,
        "mean_top_trade_notional_rate_per_min": np.nan,
        "coverage_gate": False,
        "spread_gate": False,
        "depth_gate": False,
        "activity_gate": False,
        "pre_alpha_gate": False,
        "failed_gates": "coverage,spread,depth,activity",
        "universe_liquidity_status": "missing_or_unreadable_data_no_go",
        "error": str(error),
    }


def build_outputs(paths: Paths, args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_frames: list[pd.DataFrame] = []
    score_rows: list[dict[str, object]] = []
    for symbol in parse_symbols(args.symbols):
        try:
            daily = symbol_daily(symbol, paths, args)
        except Exception as exc:  # keep batch audit moving across sparse symbols
            score_rows.append(error_scorecard(symbol, args, exc))
            continue
        daily_frames.append(daily)
        score_rows.append(symbol_scorecard(symbol, daily, args))

    daily_frame = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    scorecard = pd.DataFrame(score_rows)
    if not scorecard.empty:
        scorecard = scorecard.sort_values(
            ["pre_alpha_gate", "depth_gate", "spread_gate", "activity_gate", "median_daily_top_depth_p05_quote"],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
    return daily_frame, scorecard


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return single.markdown_table(df, columns, max_rows)


def write_report(paths: Paths, args: argparse.Namespace, daily: pd.DataFrame, scorecard: pd.DataFrame) -> None:
    candidate_count = int(scorecard["pre_alpha_gate"].astype(bool).sum()) if "pre_alpha_gate" in scorecard else 0
    lines: list[str] = [
        "# CCUSDT V2 Universe Liquidity Envelope Audit",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "Objective branch: screen the downloaded small-tier Bullish universe before any entry-quality, exit-shape, or risk-control modeling. This is not an alpha claim or execution recommendation.",
        "",
        "## Decision",
        "",
        f"Pre-alpha liquidity candidates: `{candidate_count}`.",
        "",
    ]
    if candidate_count:
        lines.append("At least one symbol passes the first spread/depth/activity envelope and can be queued for symbol-specific execution modeling.")
    else:
        lines.append("No downloaded symbol passes the first spread/depth/activity envelope, so alpha mining should remain blocked until a better execution universe is available.")
    lines.extend(
        [
            "",
            "## Scorecard",
            "",
            *markdown_table(
                scorecard,
                [
                    "symbol",
                    "dates",
                    "median_daily_median_spread_bps",
                    "median_daily_p95_spread_bps",
                    "median_daily_top_depth_p05_quote",
                    "depth_support_day_rate",
                    "median_trade_rows_per_day",
                    "mean_top_trade_notional_rate_per_min",
                    "pre_alpha_gate",
                    "failed_gates",
                    "universe_liquidity_status",
                ],
                40,
            ),
            "",
            "## Thresholds",
            "",
            f"- target_notional_quote: `{args.target_notional_quote}`",
            f"- max_median_spread_bps: `{args.max_median_spread_bps}`",
            f"- max_p95_spread_bps: `{args.max_p95_spread_bps}`",
            f"- min_depth_support_row_rate: `{args.min_depth_support_row_rate}`",
            f"- min_depth_support_day_rate: `{args.min_depth_support_day_rate}`",
            f"- min_dates: `{args.min_dates}`",
            f"- min_median_trade_rows: `{args.min_median_trade_rows}`",
            f"- min_quote_match_rate: `{args.min_quote_match_rate}`",
            f"- min_top_trade_notional_rate_per_min: `{args.min_top_trade_notional_rate_per_min}`",
            "",
            "## Output Tables",
            "",
            f"- `{paths.daily_csv}`",
            f"- `{paths.scorecard_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            f"python scripts/ccusdt_v2_universe_liquidity_envelope_audit.py --data-root {paths.data_root} --symbols \"{args.symbols}\" --target-notional-quote {args.target_notional_quote:g} --run-tag {paths.run_tag}",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, args: argparse.Namespace, daily: pd.DataFrame, scorecard: pd.DataFrame) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(paths.daily_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "data_root": str(paths.data_root),
        "symbols": parse_symbols(args.symbols),
        "symbols_total": int(len(scorecard)),
        "pre_alpha_candidate_symbols": scorecard.loc[scorecard["pre_alpha_gate"].astype(bool), "symbol"].astype(str).tolist()
        if "pre_alpha_gate" in scorecard
        else [],
        "thresholds": {
            "target_notional_quote": args.target_notional_quote,
            "max_median_spread_bps": args.max_median_spread_bps,
            "max_p95_spread_bps": args.max_p95_spread_bps,
            "min_depth_support_row_rate": args.min_depth_support_row_rate,
            "min_depth_support_day_rate": args.min_depth_support_day_rate,
            "min_dates": args.min_dates,
            "min_median_trade_rows": args.min_median_trade_rows,
            "min_quote_match_rate": args.min_quote_match_rate,
            "min_top_trade_notional_rate_per_min": args.min_top_trade_notional_rate_per_min,
        },
        "outputs": {
            "daily_csv": str(paths.daily_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, args, daily, scorecard)


def main() -> None:
    args = parse_args()
    paths = Paths(
        data_root=resolve_repo_path(args.data_root),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    daily, scorecard = build_outputs(paths, args)
    write_outputs(paths, args, daily, scorecard)
    candidate_count = int(scorecard["pre_alpha_gate"].astype(bool).sum()) if "pre_alpha_gate" in scorecard else 0
    print(
        "[ccusdt_universe_liquidity_envelope] "
        f"symbols={len(scorecard)} candidates={candidate_count} wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
