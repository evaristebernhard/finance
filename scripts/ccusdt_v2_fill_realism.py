#!/usr/bin/env python
"""CCUSDT V2 fill-realism probe.

Research-only execution realism layer over the v2 entry labels. It uses local
Bullish Tardis `book_ticker` and `trades` files to estimate whether a small
maker order posted after signal latency could plausibly fill at the top of book
before the original 60s horizon.

This is still not a production queue simulator. It approximates queue ahead from
top-of-book amount and consumes it with subsequent opposite-side trades at or
through the posted price. It does not use private order acknowledgements, hidden
liquidity, real fee tier, cancel/replace behavior, or latency measurements.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


GUARDRAIL = "research_only_fill_realism_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_fill_realism_v1"
FRAMEWORK_RUN_TAG = "20260518_ccusdt_v2_framework_v1"
US_PER_MS = 1_000
US_PER_SECOND = 1_000_000
EPS = 1e-12


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    framework_run_tag: str
    run_tag: str

    @property
    def entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_quote_transition_labels_{self.framework_run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_scorecard_{self.framework_run_tag}.csv"

    @property
    def book_ticker_root(self) -> Path:
        return self.data_root / "external" / "bullish_book_ticker" / "symbol=CCUSDT"

    @property
    def trades_root(self) -> Path:
        return self.data_root / "external" / "bullish_trades" / "symbol=CCUSDT"

    @property
    def fill_events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_fill_realism_events_{self.run_tag}.csv"

    @property
    def fill_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_fill_realism_summary_{self.run_tag}.csv"

    @property
    def fill_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_fill_realism_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_fill_realism_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-fill-realism-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 fill-realism probe.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--framework-run-tag", default=FRAMEWORK_RUN_TAG)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--latency-ms", default="0,250,1000")
    parser.add_argument("--fill-timeout-ms", default="1000,5000,10000")
    parser.add_argument("--order-notional-quote", default="50,100,250")
    parser.add_argument("--fee-stress-bps", default="0,2,5")
    parser.add_argument("--include-status", default="research_continue_needs_cost_tail_or_risk_repair")
    parser.add_argument(
        "--include-extra",
        default="expanding_fold3:tfi_event_active:mid",
        help="Comma-separated fold:trigger:entry_quality_bin rows to include in addition to status filter.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_floats(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one numeric value")
    return values


def parse_statuses(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_extra_rows(raw: str) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        pieces = text.split(":")
        if len(pieces) != 3:
            raise ValueError(f"expected fold:trigger:entry_quality_bin, got {text}")
        out.add((pieces[0], pieces[1], pieces[2]))
    return out


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def safe_rate(values: Iterable[bool] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=bool)
    return float(arr.mean()) if len(arr) else np.nan


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    view = df.loc[:, [col for col in columns if col in df.columns]].head(max_rows).copy()
    lines = ["| " + " | ".join(view.columns) + " |", "| " + " | ".join(["---"] * len(view.columns)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for value in row:
            if isinstance(value, float):
                cells.append(fmt_num(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def read_gzip_csv(path: Path, usecols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=usecols)
    with gzip.open(path, "rt", newline="") as handle:
        return pd.read_csv(handle, usecols=usecols)


def data_file(root: Path, date: str) -> Path:
    return root / f"dt={date}" / "CCUSDT.csv.gz"


def load_day(paths: Paths, date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ticker = read_gzip_csv(
        data_file(paths.book_ticker_root, date),
        ["local_timestamp", "ask_amount", "ask_price", "bid_price", "bid_amount"],
    )
    trades = read_gzip_csv(
        data_file(paths.trades_root, date),
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
    return ticker.reset_index(drop=True), trades.reset_index(drop=True)


def choose_entries(paths: Paths, statuses: set[str], extras: set[tuple[str, str, str]]) -> pd.DataFrame:
    entries = pd.read_csv(paths.entries_csv)
    scorecard = pd.read_csv(paths.scorecard_csv)
    keep = scorecard["scorecard_status"].astype(str).isin(statuses)
    if extras:
        extra_mask = pd.Series(False, index=scorecard.index)
        for fold, trigger, quality in extras:
            extra_mask |= (
                scorecard["fold"].astype(str).eq(fold)
                & scorecard["trigger_class"].astype(str).eq(trigger)
                & scorecard["entry_quality_bin"].astype(str).eq(quality)
            )
        keep |= extra_mask
    focus = scorecard.loc[keep, ["fold", "trigger_class", "entry_quality_bin", "scorecard_status"]].copy()
    if focus.empty:
        raise ValueError("no scorecard rows matched include filters")
    out = entries.merge(focus, on=["fold", "trigger_class", "entry_quality_bin"], how="inner")
    return out.sort_values(["date", "entry_local_timestamp"]).reset_index(drop=True)


def asof_index(times: np.ndarray, ts: float) -> int:
    idx = int(np.searchsorted(times, ts, side="left"))
    return idx if 0 <= idx < len(times) else -1


def fill_probe_one(
    entry: pd.Series,
    ticker: pd.DataFrame,
    trades: pd.DataFrame,
    latency_ms: float,
    fill_timeout_ms: float,
    order_notional_quote: float,
    fee_stress_bps: float,
) -> dict[str, object]:
    direction = int(entry["direction"])
    entry_ts = float(entry["entry_local_timestamp"])
    arrival_ts = entry_ts + latency_ms * US_PER_MS
    deadline_ts = arrival_ts + fill_timeout_ms * US_PER_MS
    horizon_ts = entry_ts + float(entry["timeout_sec"]) * US_PER_SECOND

    ticker_times = ticker["local_timestamp"].to_numpy(dtype="float64")
    quote_idx = asof_index(ticker_times, arrival_ts)
    exit_idx = asof_index(ticker_times, horizon_ts)
    base = {
        "run_tag": RUN_TAG,
        "framework_run_tag": FRAMEWORK_RUN_TAG,
        "guardrail": GUARDRAIL,
        "fold": entry["fold"],
        "trigger_class": entry["trigger_class"],
        "entry_quality_bin": entry["entry_quality_bin"],
        "scorecard_status": entry["scorecard_status"],
        "date": entry["date"],
        "entry_row": int(entry["entry_row"]),
        "direction": direction,
        "latency_ms": latency_ms,
        "fill_timeout_ms": fill_timeout_ms,
        "order_notional_quote": order_notional_quote,
        "fee_stress_bps": fee_stress_bps,
        "entry_local_timestamp": entry_ts,
        "arrival_timestamp": arrival_ts,
        "horizon_timestamp": horizon_ts,
    }
    if quote_idx < 0 or exit_idx < 0 or trades.empty:
        return {
            **base,
            "quote_found": False,
            "filled": False,
            "fill_ratio": 0.0,
            "fill_wait_ms": np.nan,
            "queue_ahead_base": np.nan,
            "order_size_base": np.nan,
            "fill_price": np.nan,
            "exit_price": np.nan,
            "fill_gross_bps": np.nan,
            "fill_net_bps": np.nan,
            "break_even_fee_for_2bps": np.nan,
        }

    quote = ticker.iloc[quote_idx]
    if direction > 0:
        post_price = float(quote["bid_price"])
        queue_ahead = float(quote["bid_amount"])
        exit_price = float(ticker.iloc[exit_idx]["bid_price"])
        side_mask = trades["side"].astype(str).str.lower().eq("sell").to_numpy()
        price_mask = trades["price"].to_numpy(dtype="float64") <= post_price + EPS
    else:
        post_price = float(quote["ask_price"])
        queue_ahead = float(quote["ask_amount"])
        exit_price = float(ticker.iloc[exit_idx]["ask_price"])
        side_mask = trades["side"].astype(str).str.lower().eq("buy").to_numpy()
        price_mask = trades["price"].to_numpy(dtype="float64") >= post_price - EPS

    order_size = order_notional_quote / max(post_price, EPS)
    trade_times = trades["local_timestamp"].to_numpy(dtype="float64")
    window = (trade_times >= arrival_ts) & (trade_times <= deadline_ts) & side_mask & price_mask
    candidates = trades.loc[window, ["local_timestamp", "amount"]]
    cumulative = candidates["amount"].cumsum().to_numpy(dtype="float64") if not candidates.empty else np.asarray([])
    needed = max(queue_ahead, 0.0) + order_size
    filled = bool(len(cumulative) and cumulative[-1] >= needed)
    if filled:
        hit_pos = int(np.searchsorted(cumulative, needed, side="left"))
        fill_ts = float(candidates.iloc[hit_pos]["local_timestamp"])
        fill_ratio = 1.0
        fill_wait_ms = (fill_ts - arrival_ts) / US_PER_MS
        gross = direction * 10_000.0 * math.log(max(exit_price, EPS) / max(post_price, EPS))
        net = gross - fee_stress_bps
        break_even_fee = gross - 2.0
    else:
        fill_ts = np.nan
        consumed_after_queue = max(float(cumulative[-1]) - queue_ahead, 0.0) if len(cumulative) else 0.0
        fill_ratio = min(1.0, consumed_after_queue / order_size) if order_size > EPS else 0.0
        fill_wait_ms = np.nan
        gross = np.nan
        net = np.nan
        break_even_fee = np.nan
    return {
        **base,
        "quote_found": True,
        "filled": filled,
        "fill_ratio": fill_ratio,
        "fill_wait_ms": fill_wait_ms,
        "queue_ahead_base": queue_ahead,
        "order_size_base": order_size,
        "fill_price": post_price,
        "exit_price": exit_price,
        "fill_gross_bps": gross,
        "fill_net_bps": net,
        "break_even_fee_for_2bps": break_even_fee,
    }


def run_fill_events(
    entries: pd.DataFrame,
    paths: Paths,
    latency_ms: list[float],
    fill_timeouts_ms: list[float],
    notionals: list[float],
    fee_stress_bps: list[float],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, day_entries in entries.groupby("date", sort=True):
        print(f"[ccusdt_fill] load raw date={date} entries={len(day_entries)}", flush=True)
        ticker, trades = load_day(paths, str(date))
        if ticker.empty:
            print(f"[ccusdt_fill] warning: empty ticker date={date}", flush=True)
        for entry in day_entries.itertuples(index=False):
            s = pd.Series(entry._asdict())
            for latency in latency_ms:
                for timeout in fill_timeouts_ms:
                    for notional in notionals:
                        for fee in fee_stress_bps:
                            rows.append(fill_probe_one(s, ticker, trades, latency, timeout, notional, fee))
    return pd.DataFrame(rows)


def summarize(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if events.empty:
        return pd.DataFrame(), pd.DataFrame()
    group_cols = [
        "fold",
        "trigger_class",
        "entry_quality_bin",
        "scorecard_status",
        "latency_ms",
        "fill_timeout_ms",
        "order_notional_quote",
        "fee_stress_bps",
    ]
    rows: list[dict[str, object]] = []
    for key, g in events.groupby(group_cols, sort=True):
        filled = g["filled"].astype(bool)
        fill_net = pd.to_numeric(g["fill_net_bps"], errors="coerce")
        gross = pd.to_numeric(g["fill_gross_bps"], errors="coerce")
        fill_rate = safe_rate(filled)
        rows.append(
            {
                "run_tag": RUN_TAG,
                "framework_run_tag": FRAMEWORK_RUN_TAG,
                "guardrail": GUARDRAIL,
                **dict(zip(group_cols, key)),
                "signals": int(len(g)),
                "filled": int(filled.sum()),
                "fill_rate": fill_rate,
                "avg_fill_ratio": finite_mean(g["fill_ratio"]),
                "fill_wait_p50_ms": finite_quantile(g.loc[filled, "fill_wait_ms"], 0.50),
                "queue_ahead_p50_base": finite_quantile(g["queue_ahead_base"], 0.50),
                "order_size_base": finite_mean(g["order_size_base"]),
                "filled_gross_mean_bps": finite_mean(gross),
                "filled_net_mean_bps": finite_mean(fill_net),
                "filled_net_median_bps": finite_quantile(fill_net, 0.50),
                "filled_net_gt_2bps_rate": safe_rate(fill_net[filled] > 2.0) if filled.any() else np.nan,
                "per_signal_net_mean_bps": fill_rate * finite_mean(fill_net) if np.isfinite(fill_rate) else np.nan,
                "break_even_fee_for_2bps_mean": finite_mean(g["break_even_fee_for_2bps"]),
            }
        )
    summary = pd.DataFrame(rows)
    score_rows: list[dict[str, object]] = []
    for (fold, trigger, quality), g in summary.groupby(["fold", "trigger_class", "entry_quality_bin"], sort=True):
        # Pick the least optimistic scenario among the practical defaults:
        # 250ms latency, 5000ms fill timeout, 100 quote notional, 2 bps fee stress.
        target = g[
            g["latency_ms"].eq(250.0)
            & g["fill_timeout_ms"].eq(5000.0)
            & g["order_notional_quote"].eq(100.0)
            & g["fee_stress_bps"].eq(2.0)
        ]
        if target.empty:
            target = g.sort_values(["latency_ms", "fill_timeout_ms", "order_notional_quote", "fee_stress_bps"]).head(1)
        row = target.iloc[0]
        fill_pass = bool(row["fill_rate"] >= 0.30)
        net_pass = bool(np.isfinite(row["filled_net_mean_bps"]) and row["filled_net_mean_bps"] > 2.0)
        per_signal_pass = bool(np.isfinite(row["per_signal_net_mean_bps"]) and row["per_signal_net_mean_bps"] > 1.0)
        fee_budget_pass = bool(np.isfinite(row["break_even_fee_for_2bps_mean"]) and row["break_even_fee_for_2bps_mean"] >= 2.0)
        status = (
            "fill_realism_research_continue"
            if fill_pass and net_pass and fee_budget_pass
            else "fill_realism_no_go"
        )
        score_rows.append(
            {
                "run_tag": RUN_TAG,
                "framework_run_tag": FRAMEWORK_RUN_TAG,
                "guardrail": GUARDRAIL,
                "fold": fold,
                "trigger_class": trigger,
                "entry_quality_bin": quality,
                "scorecard_status": row["scorecard_status"],
                "scenario": "latency250ms_timeout5000ms_notional100_fee2bps",
                "signals": int(row["signals"]),
                "fill_rate": row["fill_rate"],
                "filled_net_mean_bps": row["filled_net_mean_bps"],
                "per_signal_net_mean_bps": row["per_signal_net_mean_bps"],
                "break_even_fee_for_2bps_mean": row["break_even_fee_for_2bps_mean"],
                "fill_pass": fill_pass,
                "net_pass": net_pass,
                "per_signal_pass": per_signal_pass,
                "fee_budget_pass": fee_budget_pass,
                "fill_realism_status": status,
            }
        )
    return summary, pd.DataFrame(score_rows)


def write_report(paths: Paths, entries: pd.DataFrame, summary: pd.DataFrame, scorecard: pd.DataFrame, args: argparse.Namespace) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Fill Realism")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from framework run `{paths.framework_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This pass estimates maker top-of-book fill plausibility from local Bullish `book_ticker` and `trades`. "
        "It is still not a production queue simulator and does not assert a real fee tier."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Focus entries: `{len(entries)}`.")
    lines.append(f"- Latency ms: `{args.latency_ms}`.")
    lines.append(f"- Fill timeout ms: `{args.fill_timeout_ms}`.")
    lines.append(f"- Order notionals quote: `{args.order_notional_quote}`.")
    lines.append(f"- Fee stress bps: `{args.fee_stress_bps}`.")
    lines.append("")
    lines.append("## Fill Scorecard")
    lines.append("")
    if scorecard.empty:
        lines.append("_No scorecard rows._")
    else:
        view = scorecard.sort_values(["fill_realism_status", "filled_net_mean_bps"], ascending=[True, False])
        lines.extend(
            markdown_table(
                view,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "signals",
                    "fill_rate",
                    "filled_net_mean_bps",
                    "per_signal_net_mean_bps",
                    "break_even_fee_for_2bps_mean",
                    "fill_pass",
                    "net_pass",
                    "fee_budget_pass",
                    "fill_realism_status",
                ],
                30,
            )
        )
    lines.append("")
    lines.append("## Top Scenario Rows")
    lines.append("")
    if summary.empty:
        lines.append("_No summary rows._")
    else:
        top = summary.sort_values("filled_net_mean_bps", ascending=False)
        lines.extend(
            markdown_table(
                top,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "latency_ms",
                    "fill_timeout_ms",
                    "order_notional_quote",
                    "fee_stress_bps",
                    "signals",
                    "fill_rate",
                    "filled_net_mean_bps",
                    "per_signal_net_mean_bps",
                    "break_even_fee_for_2bps_mean",
                ],
                30,
            )
        )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(
        "Use this as an execution-realism filter only. A row can leave research-no-go only after this proxy is replaced "
        "or confirmed by a full incremental-book queue replay, real fee tier, and latency/fill evidence."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.fill_events_csv, paths.fill_summary_csv, paths.fill_scorecard_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("python scripts/ccusdt_v2_fill_realism.py")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, entries: pd.DataFrame, events: pd.DataFrame, summary: pd.DataFrame, scorecard: pd.DataFrame, args: argparse.Namespace) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(paths.fill_events_csv, index=False)
    summary.to_csv(paths.fill_summary_csv, index=False)
    scorecard.to_csv(paths.fill_scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "framework_run_tag": paths.framework_run_tag,
        "guardrail": GUARDRAIL,
        "focus_entries": int(len(entries)),
        "event_rows": int(len(events)),
        "summary_rows": int(len(summary)),
        "scorecard_rows": int(len(scorecard)),
        "latency_ms": parse_floats(args.latency_ms),
        "fill_timeout_ms": parse_floats(args.fill_timeout_ms),
        "order_notional_quote": parse_floats(args.order_notional_quote),
        "fee_stress_bps": parse_floats(args.fee_stress_bps),
        "execution_realism_status": "proxy_only_no_full_incremental_queue_replay_no_real_fee_tier",
        "outputs": {
            "fill_events_csv": str(paths.fill_events_csv),
            "fill_summary_csv": str(paths.fill_summary_csv),
            "fill_scorecard_csv": str(paths.fill_scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, entries, summary, scorecard, args)


def main() -> None:
    args = parse_args()
    global RUN_TAG, FRAMEWORK_RUN_TAG
    RUN_TAG = args.run_tag
    FRAMEWORK_RUN_TAG = args.framework_run_tag
    paths = Paths(
        data_root=resolve_repo_path(args.data_root),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        framework_run_tag=args.framework_run_tag,
        run_tag=args.run_tag,
    )
    statuses = parse_statuses(args.include_status)
    extras = parse_extra_rows(args.include_extra)
    entries = choose_entries(paths, statuses, extras)
    print(f"[ccusdt_fill] focus entries={len(entries)}", flush=True)
    events = run_fill_events(
        entries,
        paths,
        parse_floats(args.latency_ms),
        parse_floats(args.fill_timeout_ms),
        parse_floats(args.order_notional_quote),
        parse_floats(args.fee_stress_bps),
    )
    summary, scorecard = summarize(events)
    write_outputs(paths, entries, events, summary, scorecard, args)
    print(f"[ccusdt_fill] wrote {paths.fill_scorecard_csv}", flush=True)
    print(f"[ccusdt_fill] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
