"""Parameter sweep for the Polymarket delayed-copy paper strategy.

This is a research helper. It reuses the causal paper ledger engine and ranks
configurations on the same public probe output. Positive rows from this script
are hypotheses to paper-forward, not proof of a live edge.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[0]
sys.path.insert(0, str(SCRIPT_DIR))

from polymarket_delayed_copy_paper_strategy import (  # noqa: E402
    load_market_by_asset,
    merge_market_fields,
    read_csv_rows,
    run_strategy,
    write_csv,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-output-dir", type=Path, default=Path("output/polymarket_wallet_factor_probe"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/polymarket_delayed_copy_parameter_sweep"),
    )
    parser.add_argument("--input-csv", type=Path, default=None)
    parser.add_argument("--directions", default="copy,fade")
    parser.add_argument("--entry-delays", default="30,120")
    parser.add_argument("--exit-delays", default="120,300")
    parser.add_argument("--min-prior-trades-list", default="2,3,5,8")
    parser.add_argument("--min-prior-mean-net-edge-cents-list", default="0.5,1.5,3,5")
    parser.add_argument("--min-prior-win-rates", default="0.5,0.6,0.7")
    parser.add_argument("--max-prior-one-hit-penalties", default="0.5,0.75,1.0")
    parser.add_argument("--category", default="crypto")
    parser.add_argument("--capital-usd", type=float, default=10_000.0)
    parser.add_argument("--stake-usd", type=float, default=100.0)
    parser.add_argument("--max-stake-usd", type=float, default=100.0)
    parser.add_argument("--max-open-notional-usd", type=float, default=2_000.0)
    parser.add_argument("--max-wallet-open-notional-usd", type=float, default=300.0)
    parser.add_argument("--max-market-open-notional-usd", type=float, default=300.0)
    parser.add_argument("--min-entry-price", type=float, default=0.05)
    parser.add_argument("--max-entry-price", type=float, default=0.92)
    parser.add_argument("--entry-cost-cents", type=float, default=0.5)
    parser.add_argument("--exit-cost-cents", type=float, default=0.5)
    parser.add_argument("--safety-cost-cents", type=float, default=0.5)
    parser.add_argument("--fallback-spread-cents", type=float, default=1.0)
    parser.add_argument("--min-total-cost-cents", type=float, default=1.5)
    parser.add_argument("--dedupe-seconds", type=int, default=60)
    parser.add_argument("--min-closed-trades-for-rank", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=20)
    return parser.parse_args()


def parse_ints(raw: str) -> list[int]:
    return [int(float(item.strip())) for item in raw.split(",") if item.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def parse_strings(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.6g}"
    return str(value)


def config_namespace(args: argparse.Namespace, params: dict[str, Any]) -> argparse.Namespace:
    return argparse.Namespace(
        entry_delay_seconds=params["entry_delay_seconds"],
        exit_delay_seconds=params["exit_delay_seconds"],
        direction=params["direction"],
        category=args.category,
        capital_usd=args.capital_usd,
        stake_usd=args.stake_usd,
        max_stake_usd=args.max_stake_usd,
        max_open_notional_usd=args.max_open_notional_usd,
        max_wallet_open_notional_usd=args.max_wallet_open_notional_usd,
        max_market_open_notional_usd=args.max_market_open_notional_usd,
        min_entry_price=args.min_entry_price,
        max_entry_price=args.max_entry_price,
        min_prior_trades=params["min_prior_trades"],
        min_prior_mean_net_edge_cents=params["min_prior_mean_net_edge_cents"],
        min_prior_win_rate=params["min_prior_win_rate"],
        max_prior_one_hit_penalty=params["max_prior_one_hit_penalty"],
        entry_cost_cents=args.entry_cost_cents,
        exit_cost_cents=args.exit_cost_cents,
        safety_cost_cents=args.safety_cost_cents,
        fallback_spread_cents=args.fallback_spread_cents,
        min_total_cost_cents=args.min_total_cost_cents,
        dedupe_seconds=args.dedupe_seconds,
        max_skipped_rows=0,
    )


def result_row(params: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        **params,
        "closed_paper_trades": summary["closed_paper_trades"],
        "deployed_notional_usd": summary["deployed_notional_usd"],
        "net_pnl_usd": summary["net_pnl_usd"],
        "roi_on_deployed": summary["roi_on_deployed"],
        "win_rate": summary["win_rate"],
        "average_net_edge_cents": summary["average_net_edge_cents"],
        "profit_factor": summary["profit_factor"],
        "max_closed_trade_drawdown_usd": summary["max_closed_trade_drawdown_usd"],
    }


def rank_key(row: dict[str, Any], min_trades: int) -> tuple[int, float, float, float]:
    closed = int(row.get("closed_paper_trades") or 0)
    valid = 1 if closed >= min_trades else 0
    pnl = float(row.get("net_pnl_usd") or 0.0)
    roi = float(row.get("roi_on_deployed") or 0.0)
    drawdown = float(row.get("max_closed_trade_drawdown_usd") or 0.0)
    return valid, pnl, roi, -drawdown


def write_summary_md(path: Path, results: list[dict[str, Any]], args: argparse.Namespace) -> None:
    ranked = sorted(results, key=lambda row: rank_key(row, args.min_closed_trades_for_rank), reverse=True)
    lines = [
        "# Polymarket Delayed-Copy Parameter Sweep",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "This is an exploratory sweep over causal paper-ledger parameters. A positive row is a forward-paper hypothesis, not live-trading proof.",
        "",
        f"- Configurations tested: {len(results)}",
        f"- Ranking minimum closed trades: {args.min_closed_trades_for_rank}",
        f"- Category: {args.category}",
        "",
        "## Top Configurations",
        "",
        "| rank | direction | entry_s | exit_s | prior_n | prior_edge_c | prior_win | one_hit | trades | pnl | roi | win | pf | dd |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(ranked[: args.top_n], start=1):
        lines.append(
            "| {idx} | {direction} | {entry} | {exit} | {prior_n} | {edge} | {win_req} | {one_hit} | {trades} | {pnl} | {roi} | {win} | {pf} | {dd} |".format(
                idx=idx,
                direction=row["direction"],
                entry=row["entry_delay_seconds"],
                exit=row["exit_delay_seconds"],
                prior_n=row["min_prior_trades"],
                edge=fmt(row["min_prior_mean_net_edge_cents"]),
                win_req=fmt(row["min_prior_win_rate"]),
                one_hit=fmt(row["max_prior_one_hit_penalty"]),
                trades=row["closed_paper_trades"],
                pnl=fmt(row["net_pnl_usd"]),
                roi=fmt(row["roi_on_deployed"]),
                win=fmt(row["win_rate"]),
                pf=fmt(row["profit_factor"]),
                dd=fmt(row["max_closed_trade_drawdown_usd"]),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    probe_dir = args.probe_output_dir if args.probe_output_dir.is_absolute() else REPO_ROOT / args.probe_output_dir
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    input_csv = args.input_csv or (probe_dir / "trade_edges.csv")
    input_csv = input_csv if input_csv.is_absolute() else REPO_ROOT / input_csv

    rows = read_csv_rows(input_csv)
    merge_market_fields(rows, load_market_by_asset(probe_dir))

    directions = parse_strings(args.directions)
    entry_delays = parse_ints(args.entry_delays)
    exit_delays = parse_ints(args.exit_delays)
    min_prior_trades = parse_ints(args.min_prior_trades_list)
    min_prior_edges = parse_floats(args.min_prior_mean_net_edge_cents_list)
    min_win_rates = parse_floats(args.min_prior_win_rates)
    max_one_hits = parse_floats(args.max_prior_one_hit_penalties)

    results: list[dict[str, Any]] = []
    for direction, entry_delay, exit_delay, prior_n, prior_edge, min_win, max_one_hit in itertools.product(
        directions,
        entry_delays,
        exit_delays,
        min_prior_trades,
        min_prior_edges,
        min_win_rates,
        max_one_hits,
    ):
        if exit_delay <= entry_delay:
            continue
        params = {
            "direction": direction,
            "entry_delay_seconds": entry_delay,
            "exit_delay_seconds": exit_delay,
            "min_prior_trades": prior_n,
            "min_prior_mean_net_edge_cents": prior_edge,
            "min_prior_win_rate": min_win,
            "max_prior_one_hit_penalty": max_one_hit,
        }
        cfg = config_namespace(args, params)
        _ledger, _skipped, summary = run_strategy(rows, cfg)
        results.append(result_row(params, summary))

    ranked = sorted(results, key=lambda row: rank_key(row, args.min_closed_trades_for_rank), reverse=True)
    write_csv(output_dir / "sweep_results.csv", ranked)
    write_json(
        output_dir / "summary.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_csv": str(input_csv),
            "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            "configurations_tested": len(results),
            "top_configurations": ranked[: args.top_n],
        },
    )
    write_summary_md(output_dir / "summary.md", results, args)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
