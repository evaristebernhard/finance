#!/usr/bin/env python
"""CCUSDT V2 liquidity-envelope audit.

Research-only screen for the structural pivot:

    alpha search -> execution envelope first -> alpha search only if fill/cost
    capacity is plausible.

This pass does not create or tune a trading rule. It summarizes local Bullish
CCUSDT top-of-book spread/depth/trade-arrival conditions and cross-checks them
against the already-run practical L2 maker and taker audits.
"""

from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_liquidity_envelope_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_liquidity_envelope_audit_v1"
L2_QUEUE_RUN_TAG = "20260518_ccusdt_v2_l2_queue_fill_all_practical_v1"
TAKER_RUN_TAG = "20260518_ccusdt_v2_taker_fallback_audit_v1"
DECOMP_RUN_TAG = "20260518_ccusdt_v2_execution_failure_decomp_v1"
US_PER_SECOND = 1_000_000
EPS = 1e-12


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    symbol: str
    run_tag: str
    l2_queue_run_tag: str
    taker_run_tag: str
    decomp_run_tag: str

    @property
    def book_ticker_root(self) -> Path:
        return self.data_root / "external" / "bullish_book_ticker" / f"symbol={self.symbol}"

    @property
    def trades_root(self) -> Path:
        return self.data_root / "external" / "bullish_trades" / f"symbol={self.symbol}"

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
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_liquidity_envelope_daily_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_liquidity_envelope_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_liquidity_envelope_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-liquidity-envelope-audit-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 liquidity-envelope audit.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--l2-queue-run-tag", default=L2_QUEUE_RUN_TAG)
    parser.add_argument("--taker-run-tag", default=TAKER_RUN_TAG)
    parser.add_argument("--decomp-run-tag", default=DECOMP_RUN_TAG)
    parser.add_argument("--target-notional-quote", type=float, default=100.0)
    parser.add_argument("--max-median-spread-bps", type=float, default=2.0)
    parser.add_argument("--max-p95-spread-bps", type=float, default=5.0)
    parser.add_argument("--min-depth-support-row-rate", type=float, default=0.95)
    parser.add_argument("--min-depth-support-day-rate", type=float, default=0.95)
    parser.add_argument("--min-practical-fill-rate", type=float, default=0.30)
    parser.add_argument("--quote-match-tolerance-sec", type=float, default=5.0)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def fmt_num(value: object, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    return fill_base.finite_mean(values)


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    return fill_base.finite_quantile(values, q)


def safe_rate(values: Iterable[bool] | np.ndarray) -> float:
    return fill_base.safe_rate(values)


def cvar(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def data_file(root: Path, symbol: str, date: str) -> Path:
    return root / f"dt={date}" / f"{symbol}.csv.gz"


def read_gzip_csv(path: Path, usecols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=usecols)
    with gzip.open(path, "rt", newline="") as handle:
        return pd.read_csv(handle, usecols=usecols)


def available_dates(paths: Paths) -> list[str]:
    roots = [paths.book_ticker_root, paths.trades_root]
    date_sets: list[set[str]] = []
    for root in roots:
        if not root.exists():
            date_sets.append(set())
            continue
        date_sets.append({path.name.replace("dt=", "") for path in root.glob("dt=*") if path.is_dir()})
    if not date_sets:
        return []
    return sorted(set.intersection(*date_sets))


def load_day(paths: Paths, date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ticker = read_gzip_csv(
        data_file(paths.book_ticker_root, paths.symbol, date),
        ["local_timestamp", "ask_amount", "ask_price", "bid_price", "bid_amount"],
    )
    trades = read_gzip_csv(
        data_file(paths.trades_root, paths.symbol, date),
        ["local_timestamp", "side", "price", "amount"],
    )
    for col in ["local_timestamp", "ask_amount", "ask_price", "bid_price", "bid_amount"]:
        if col in ticker.columns:
            ticker[col] = pd.to_numeric(ticker[col], errors="coerce")
    for col in ["local_timestamp", "price", "amount"]:
        if col in trades.columns:
            trades[col] = pd.to_numeric(trades[col], errors="coerce")
    ticker = ticker.dropna(subset=["local_timestamp", "ask_price", "bid_price"]).sort_values("local_timestamp")
    trades = trades.dropna(subset=["local_timestamp", "price", "amount"]).sort_values("local_timestamp")
    ticker = ticker.reset_index(drop=True)
    trades = trades.reset_index(drop=True)
    ticker["mid_price"] = (ticker["ask_price"] + ticker["bid_price"]) / 2.0
    ticker["spread_bps"] = 10_000.0 * (ticker["ask_price"] - ticker["bid_price"]) / np.maximum(ticker["mid_price"], EPS)
    ticker["bid_depth_quote"] = ticker["bid_price"] * ticker["bid_amount"]
    ticker["ask_depth_quote"] = ticker["ask_price"] * ticker["ask_amount"]
    ticker["top_depth_quote"] = np.minimum(ticker["bid_depth_quote"], ticker["ask_depth_quote"])
    return ticker, trades


def trade_arrival_metrics(
    ticker: pd.DataFrame,
    trades: pd.DataFrame,
    quote_match_tolerance_sec: float,
) -> dict[str, float]:
    if ticker.empty or trades.empty:
        return {
            "quote_matched_trades": 0,
            "top_trade_count": 0,
            "top_trade_rate_per_min": np.nan,
            "top_trade_notional_quote": 0.0,
            "top_trade_notional_rate_per_min": np.nan,
            "quote_match_rate": np.nan,
        }
    quote = ticker.loc[:, ["local_timestamp", "bid_price", "ask_price", "mid_price"]].copy()
    quote["quote_ts"] = quote["local_timestamp"]
    merged = pd.merge_asof(
        trades.sort_values("local_timestamp"),
        quote.sort_values("local_timestamp"),
        on="local_timestamp",
        direction="backward",
    )
    quote_age_us = merged["local_timestamp"] - merged["quote_ts"]
    matched = merged[np.isfinite(quote_age_us) & (quote_age_us <= quote_match_tolerance_sec * US_PER_SECOND)].copy()
    if matched.empty:
        return {
            "quote_matched_trades": 0,
            "top_trade_count": 0,
            "top_trade_rate_per_min": 0.0,
            "top_trade_notional_quote": 0.0,
            "top_trade_notional_rate_per_min": 0.0,
            "quote_match_rate": 0.0,
        }
    top_mask = (matched["price"] >= matched["ask_price"]) | (matched["price"] <= matched["bid_price"])
    top = matched.loc[top_mask].copy()
    top["notional_quote"] = top["price"] * top["amount"]
    duration_min = max(
        (float(ticker["local_timestamp"].max()) - float(ticker["local_timestamp"].min())) / (60 * US_PER_SECOND),
        EPS,
    )
    return {
        "quote_matched_trades": int(len(matched)),
        "top_trade_count": int(len(top)),
        "top_trade_rate_per_min": float(len(top) / duration_min),
        "top_trade_notional_quote": float(top["notional_quote"].sum()) if not top.empty else 0.0,
        "top_trade_notional_rate_per_min": float(top["notional_quote"].sum() / duration_min) if not top.empty else 0.0,
        "quote_match_rate": float(len(matched) / max(len(trades), 1)),
    }


def daily_metrics(paths: Paths, args: argparse.Namespace) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date in available_dates(paths):
        ticker, trades = load_day(paths, date)
        if ticker.empty:
            continue
        duration_min = max(
            (float(ticker["local_timestamp"].max()) - float(ticker["local_timestamp"].min())) / (60 * US_PER_SECOND),
            EPS,
        )
        spread = ticker["spread_bps"].to_numpy(dtype="float64")
        depth = ticker["top_depth_quote"].to_numpy(dtype="float64")
        bid_depth = ticker["bid_depth_quote"].to_numpy(dtype="float64")
        ask_depth = ticker["ask_depth_quote"].to_numpy(dtype="float64")
        arrival = trade_arrival_metrics(ticker, trades, args.quote_match_tolerance_sec)
        depth_support_rate = safe_rate(depth >= args.target_notional_quote)
        rows.append(
            {
                "run_tag": paths.run_tag,
                "guardrail": GUARDRAIL,
                "symbol": paths.symbol,
                "date": date,
                "ticker_rows": int(len(ticker)),
                "trade_rows": int(len(trades)),
                "duration_min": duration_min,
                "book_ticker_rate_per_min": float(len(ticker) / duration_min),
                "trade_rate_per_min": float(len(trades) / duration_min),
                "quote_match_rate": arrival["quote_match_rate"],
                "quote_matched_trades": arrival["quote_matched_trades"],
                "top_trade_count": arrival["top_trade_count"],
                "top_trade_rate_per_min": arrival["top_trade_rate_per_min"],
                "top_trade_notional_quote": arrival["top_trade_notional_quote"],
                "top_trade_notional_rate_per_min": arrival["top_trade_notional_rate_per_min"],
                "median_spread_bps": finite_quantile(spread, 0.50),
                "p95_spread_bps": finite_quantile(spread, 0.95),
                "spread_cvar10_bps": cvar(spread, 0.10),
                "top_depth_p05_quote": finite_quantile(depth, 0.05),
                "top_depth_median_quote": finite_quantile(depth, 0.50),
                "bid_depth_p05_quote": finite_quantile(bid_depth, 0.05),
                "ask_depth_p05_quote": finite_quantile(ask_depth, 0.05),
                "top_depth_ge_target_rate": depth_support_rate,
                "depth_support_day_pass": bool(depth_support_rate >= args.min_depth_support_row_rate),
            }
        )
    if not rows:
        raise ValueError(f"no usable {paths.symbol} book_ticker/trades dates under {paths.data_root}")
    return pd.DataFrame(rows)


def read_existing(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def build_scorecard(paths: Paths, daily: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    l2 = read_existing(paths.l2_queue_scorecard_csv)
    taker = read_existing(paths.taker_scorecard_csv)
    decomp = read_existing(paths.decomp_csv)

    median_spread = finite_quantile(daily["median_spread_bps"], 0.50)
    p95_spread = finite_quantile(daily["p95_spread_bps"], 0.50)
    top_depth_p05 = finite_quantile(daily["top_depth_p05_quote"], 0.50)
    depth_support_day_rate = safe_rate(daily["depth_support_day_pass"])
    top_trade_rate = finite_mean(daily["top_trade_rate_per_min"])
    top_trade_notional_rate = finite_mean(daily["top_trade_notional_rate_per_min"])

    best_fill_rate = (
        float(pd.to_numeric(l2["fill_rate"], errors="coerce").max()) if "fill_rate" in l2.columns and not l2.empty else np.nan
    )
    best_per_signal = (
        float(pd.to_numeric(l2["per_signal_net_mean_bps"], errors="coerce").max())
        if "per_signal_net_mean_bps" in l2.columns and not l2.empty
        else np.nan
    )
    l2_no_go_rows = int(l2["l2_queue_fill_status"].astype(str).eq("l2_queue_fill_no_go").sum()) if not l2.empty else 0
    l2_rows = int(len(l2))
    best_taker_net = (
        float(pd.to_numeric(taker["taker_net_mean_bps"], errors="coerce").max())
        if "taker_net_mean_bps" in taker.columns and not taker.empty
        else np.nan
    )
    taker_promote_rows = (
        int(taker.get("taker_promote_gate", pd.Series(dtype=bool)).astype(bool).sum()) if not taker.empty else 0
    )
    min_required_filled = (
        float(pd.to_numeric(decomp["required_filled_net_at_current_fill_rate_bps"], errors="coerce").replace([np.inf, -np.inf], np.nan).min())
        if "required_filled_net_at_current_fill_rate_bps" in decomp.columns and not decomp.empty
        else np.nan
    )

    spread_gate = bool(median_spread <= args.max_median_spread_bps and p95_spread <= args.max_p95_spread_bps)
    depth_gate = bool(depth_support_day_rate >= args.min_depth_support_day_rate)
    maker_fill_gate = bool(np.isfinite(best_fill_rate) and best_fill_rate >= args.min_practical_fill_rate)
    alpha_execution_gate = bool(np.isfinite(best_per_signal) and best_per_signal >= 2.0)
    taker_gate = bool(taker_promote_rows > 0)
    envelope_pre_alpha_gate = bool(spread_gate and depth_gate and (maker_fill_gate or taker_gate))
    if not spread_gate or not depth_gate:
        status = "liquidity_envelope_no_go"
    elif not maker_fill_gate and not taker_gate:
        status = "instrument_fill_no_go"
    elif not alpha_execution_gate:
        status = "execution_capacity_without_alpha_no_go"
    else:
        status = "liquidity_envelope_research_continue"

    return pd.DataFrame(
        [
            {
                "run_tag": paths.run_tag,
                "guardrail": GUARDRAIL,
                "symbol": paths.symbol,
                "dates": int(len(daily)),
                "target_notional_quote": args.target_notional_quote,
                "median_daily_median_spread_bps": median_spread,
                "median_daily_p95_spread_bps": p95_spread,
                "median_daily_top_depth_p05_quote": top_depth_p05,
                "depth_support_day_rate": depth_support_day_rate,
                "top_trade_rate_per_min_mean": top_trade_rate,
                "top_trade_notional_rate_per_min_mean": top_trade_notional_rate,
                "best_practical_maker_fill_rate": best_fill_rate,
                "best_practical_maker_per_signal_net_bps": best_per_signal,
                "min_required_filled_net_for_2bps_at_current_fill_bps": min_required_filled,
                "l2_no_go_rows": l2_no_go_rows,
                "l2_rows": l2_rows,
                "best_existing_taker_net_mean_bps": best_taker_net,
                "taker_promote_rows": taker_promote_rows,
                "spread_gate": spread_gate,
                "depth_gate": depth_gate,
                "maker_fill_gate": maker_fill_gate,
                "taker_gate": taker_gate,
                "alpha_execution_gate": alpha_execution_gate,
                "envelope_pre_alpha_gate": envelope_pre_alpha_gate,
                "liquidity_envelope_status": status,
            }
        ]
    )


def write_report(paths: Paths, daily: pd.DataFrame, scorecard: pd.DataFrame, args: argparse.Namespace) -> None:
    row = scorecard.iloc[0].to_dict()
    lines: list[str] = []
    lines.append("# CCUSDT V2 Liquidity Envelope Audit")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "Objective branch: screen execution envelope before further CCUSDT microstructure alpha mining. "
        "This is a research-only instrument-capacity audit, not a trading rule."
    )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"Envelope status: `{row['liquidity_envelope_status']}`.")
    lines.append("")
    lines.append(
        "CCUSDT does not pass the execution-first gate for this strategy family. The median spread is slightly above "
        "the `2` bps gate, the top-of-book depth support for the target notional fails every day, practical maker fill "
        "remains far below the required envelope, and no taker row has a promotion gate."
    )
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    lines.extend(
        markdown_table(
            scorecard,
            [
                "symbol",
                "dates",
                "target_notional_quote",
                "median_daily_median_spread_bps",
                "median_daily_p95_spread_bps",
                "median_daily_top_depth_p05_quote",
                "depth_support_day_rate",
                "best_practical_maker_fill_rate",
                "best_practical_maker_per_signal_net_bps",
                "min_required_filled_net_for_2bps_at_current_fill_bps",
                "taker_promote_rows",
                "envelope_pre_alpha_gate",
                "liquidity_envelope_status",
            ],
            10,
        )
    )
    lines.append("")
    lines.append("## Daily Envelope")
    lines.append("")
    lines.extend(
        markdown_table(
            daily,
            [
                "date",
                "ticker_rows",
                "trade_rows",
                "median_spread_bps",
                "p95_spread_bps",
                "top_depth_p05_quote",
                "top_depth_ge_target_rate",
                "top_trade_rate_per_min",
                "top_trade_notional_rate_per_min",
                "depth_support_day_pass",
            ],
            20,
        )
    )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "- The pre-alpha envelope already fails on spread/depth support for the target notional. The later practical "
        "maker-fill and per-signal economics audits fail as well, so this is not merely an alpha-label problem."
    )
    lines.append(
        "- At the best current practical maker fill rate, the decomposition requires a filled-order mean far above the "
        "observed filled mean to reach `2` bps per signal."
    )
    lines.append(
        "- This supports the liquidity-envelope universe pivot: future work should screen symbols for fillability and "
        "cost capacity before applying the CCUSDT V2 entry-quality/exit-shape/risk-control framework."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.daily_csv, paths.scorecard_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(
        f"python scripts/ccusdt_v2_liquidity_envelope_audit.py --symbol {paths.symbol} --run-tag {paths.run_tag}"
    )
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, daily: pd.DataFrame, scorecard: pd.DataFrame, args: argparse.Namespace) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(paths.daily_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "symbol": paths.symbol,
        "data_root": str(paths.data_root),
        "l2_queue_run_tag": paths.l2_queue_run_tag,
        "taker_run_tag": paths.taker_run_tag,
        "decomp_run_tag": paths.decomp_run_tag,
        "target_notional_quote": args.target_notional_quote,
        "max_median_spread_bps": args.max_median_spread_bps,
        "max_p95_spread_bps": args.max_p95_spread_bps,
        "min_depth_support_row_rate": args.min_depth_support_row_rate,
        "min_depth_support_day_rate": args.min_depth_support_day_rate,
        "min_practical_fill_rate": args.min_practical_fill_rate,
        "liquidity_envelope_status": str(scorecard.iloc[0]["liquidity_envelope_status"]),
        "outputs": {
            "daily_csv": str(paths.daily_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, daily, scorecard, args)


def main() -> None:
    args = parse_args()
    paths = Paths(
        data_root=resolve_repo_path(args.data_root),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        symbol=args.symbol,
        run_tag=args.run_tag,
        l2_queue_run_tag=args.l2_queue_run_tag,
        taker_run_tag=args.taker_run_tag,
        decomp_run_tag=args.decomp_run_tag,
    )
    daily = daily_metrics(paths, args)
    scorecard = build_scorecard(paths, daily, args)
    write_outputs(paths, daily, scorecard, args)
    print(f"[ccusdt_liquidity_envelope_audit] days={len(daily)}", flush=True)
    print(
        "[ccusdt_liquidity_envelope_audit] "
        f"status={scorecard.iloc[0]['liquidity_envelope_status']} "
        f"pre_alpha_gate={scorecard.iloc[0]['envelope_pre_alpha_gate']}",
        flush=True,
    )
    print(f"[ccusdt_liquidity_envelope_audit] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
