"""Causal paper ledger for a Polymarket delayed-copy wallet strategy.

Inputs are produced by scripts/polymarket_wallet_factor_probe.py. The strategy
uses only wallet outcomes that would already be known at signal time, then
records a read-only paper trade with explicit delay, spread/slippage buffers,
and portfolio caps. It never signs, submits, or prepares live orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-12


@dataclass
class PaperMetric:
    row_index: int
    timestamp: int
    ready_timestamp: int
    wallet: str
    asset: str
    condition_id: str
    direction: str
    entry_proxy_price: float
    exit_proxy_price: float
    entry_exec_price: float
    exit_exec_price: float
    gross_edge_cents: float
    total_cost_cents: float
    net_edge_cents: float


@dataclass
class WalletStats:
    net_edges_cents: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        if math.isfinite(value):
            self.net_edges_cents.append(value)

    @property
    def count(self) -> int:
        return len(self.net_edges_cents)

    @property
    def mean(self) -> float | None:
        return statistics.fmean(self.net_edges_cents) if self.net_edges_cents else None

    @property
    def median(self) -> float | None:
        return statistics.median(self.net_edges_cents) if self.net_edges_cents else None

    @property
    def win_rate(self) -> float | None:
        if not self.net_edges_cents:
            return None
        return sum(1 for value in self.net_edges_cents if value > 0.0) / len(self.net_edges_cents)

    @property
    def one_hit_penalty(self) -> float:
        positives = [value for value in self.net_edges_cents if value > 0.0]
        total = sum(positives)
        return max(positives) / total if positives and total > EPS else 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--probe-output-dir",
        type=Path,
        default=Path("output/polymarket_wallet_factor_probe"),
        help="Directory containing trade_edges.csv and market_suitability.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/polymarket_delayed_copy_paper_strategy"),
    )
    parser.add_argument("--input-csv", type=Path, default=None)
    parser.add_argument("--entry-delay-seconds", type=int, default=30)
    parser.add_argument("--exit-delay-seconds", type=int, default=120)
    parser.add_argument("--direction", choices=["copy", "fade"], default="copy")
    parser.add_argument("--category", default="crypto", help="Use 'all' to disable category filtering.")
    parser.add_argument("--capital-usd", type=float, default=10_000.0)
    parser.add_argument("--stake-usd", type=float, default=100.0)
    parser.add_argument("--max-stake-usd", type=float, default=100.0)
    parser.add_argument("--max-open-notional-usd", type=float, default=2_000.0)
    parser.add_argument("--max-wallet-open-notional-usd", type=float, default=300.0)
    parser.add_argument("--max-market-open-notional-usd", type=float, default=300.0)
    parser.add_argument("--min-entry-price", type=float, default=0.05)
    parser.add_argument("--max-entry-price", type=float, default=0.92)
    parser.add_argument("--min-prior-trades", type=int, default=3)
    parser.add_argument("--min-prior-mean-net-edge-cents", type=float, default=0.5)
    parser.add_argument("--min-prior-win-rate", type=float, default=0.55)
    parser.add_argument("--max-prior-one-hit-penalty", type=float, default=0.75)
    parser.add_argument("--entry-cost-cents", type=float, default=0.5)
    parser.add_argument("--exit-cost-cents", type=float, default=0.5)
    parser.add_argument("--safety-cost-cents", type=float, default=0.5)
    parser.add_argument("--fallback-spread-cents", type=float, default=1.0)
    parser.add_argument("--min-total-cost-cents", type=float, default=1.5)
    parser.add_argument("--dedupe-seconds", type=int, default=60)
    parser.add_argument("--max-skipped-rows", type=int, default=10_000)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)
    return int(number) if number is not None else None


def parse_timestamp(row: dict[str, Any]) -> int | None:
    direct = safe_int(row.get("timestamp"))
    if direct is not None:
        return direct
    raw = str(row.get("timestamp_utc") or "")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(dt.timestamp())


def timestamp_utc(ts: int | float | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def edge_cents(row: dict[str, Any], delay_seconds: int) -> float | None:
    return safe_float(row.get(f"edge_{delay_seconds}s_cents")) or safe_float(
        row.get(f"trade_proxy_edge_{delay_seconds}s_cents")
    )


def price_at_delay(row: dict[str, Any], delay_seconds: int) -> float | None:
    direct = safe_float(row.get(f"future_price_{delay_seconds}s"))
    if direct is not None:
        return direct
    entry = safe_float(row.get("entry_price"))
    edge = edge_cents(row, delay_seconds)
    if entry is None or edge is None:
        return None
    return entry + edge / 100.0


def total_cost_cents(row: dict[str, Any], args: argparse.Namespace) -> float:
    spread = safe_float(row.get("spread_cents"))
    if spread is None:
        spread = args.fallback_spread_cents
    slippage = safe_float(row.get("capacity_1000_slippage_cents")) or 0.0
    fixed = args.entry_cost_cents + args.exit_cost_cents + args.safety_cost_cents
    total = fixed + max(spread, 0.0) + 2.0 * max(slippage, 0.0)
    return max(total, args.min_total_cost_cents)


def build_metric(row_index: int, row: dict[str, Any], args: argparse.Namespace) -> PaperMetric | None:
    ts = parse_timestamp(row)
    entry_proxy = price_at_delay(row, args.entry_delay_seconds)
    exit_proxy = price_at_delay(row, args.exit_delay_seconds)
    if ts is None or entry_proxy is None or exit_proxy is None:
        return None
    if not (0.0 < entry_proxy < 1.0 and 0.0 < exit_proxy < 1.0):
        return None
    if args.direction == "fade":
        entry_proxy = 1.0 - entry_proxy
        exit_proxy = 1.0 - exit_proxy
    cost = total_cost_cents(row, args)
    entry_cost = args.entry_cost_cents + 0.5 * max(args.safety_cost_cents, 0.0)
    exit_cost = cost - entry_cost
    entry_exec = entry_proxy + entry_cost / 100.0
    exit_exec = exit_proxy - exit_cost / 100.0
    if not (0.0 < entry_exec < 1.0 and 0.0 < exit_exec < 1.0):
        return None
    gross = (exit_proxy - entry_proxy) * 100.0
    net = (exit_exec - entry_exec) * 100.0
    return PaperMetric(
        row_index=row_index,
        timestamp=ts,
        ready_timestamp=ts + args.exit_delay_seconds,
        wallet=str(row.get("wallet") or "").lower(),
        asset=str(row.get("asset") or ""),
        condition_id=str(row.get("condition_id") or ""),
        direction=args.direction,
        entry_proxy_price=entry_proxy,
        exit_proxy_price=exit_proxy,
        entry_exec_price=entry_exec,
        exit_exec_price=exit_exec,
        gross_edge_cents=gross,
        total_cost_cents=cost,
        net_edge_cents=net,
    )


def load_market_by_asset(probe_dir: Path) -> dict[str, dict[str, Any]]:
    path = probe_dir / "market_suitability.csv"
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in read_csv_rows(path):
        asset = str(row.get("asset") or "")
        if asset:
            out[asset] = row
    return out


def merge_market_fields(rows: list[dict[str, Any]], market_by_asset: dict[str, dict[str, Any]]) -> None:
    fields = [
        "spread_cents",
        "capacity_1000_ok",
        "capacity_1000_slippage_cents",
        "ask_depth_usd",
        "crowd_exit_risk",
        "rule_ambiguity_score",
        "market_suitability_score",
    ]
    for row in rows:
        market = market_by_asset.get(str(row.get("asset") or ""))
        if not market:
            continue
        for field_name in fields:
            if row.get(field_name) in (None, ""):
                row[field_name] = market.get(field_name)


def skip_row(
    skipped: list[dict[str, Any]],
    counts: Counter[str],
    row: dict[str, Any],
    reason: str,
    max_rows: int,
) -> None:
    counts[reason] += 1
    if len(skipped) >= max_rows:
        return
    skipped.append(
        {
            "timestamp_utc": row.get("timestamp_utc") or timestamp_utc(parse_timestamp(row)),
            "wallet": row.get("wallet", ""),
            "asset": row.get("asset", ""),
            "condition_id": row.get("condition_id", ""),
            "category": row.get("category", ""),
            "entry_price": row.get("entry_price", ""),
            "reason": reason,
            "title": row.get("title", ""),
        }
    )


def active_notional(active: list[dict[str, Any]], key: str | None = None, value: str | None = None) -> float:
    total = 0.0
    for item in active:
        if key is not None and item.get(key) != value:
            continue
        total += float(item.get("stake_usd") or 0.0)
    return total


def trade_stake(stats: WalletStats, args: argparse.Namespace) -> float:
    mean_edge = stats.mean or 0.0
    if args.min_prior_mean_net_edge_cents <= EPS:
        multiplier = 1.0
    else:
        multiplier = mean_edge / args.min_prior_mean_net_edge_cents
    multiplier = max(0.5, min(multiplier, 2.0))
    return min(args.max_stake_usd, args.stake_usd * multiplier)


def run_strategy(rows: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rows = list(rows)
    rows.sort(key=lambda row: (parse_timestamp(row) or 0, str(row.get("tx") or ""), str(row.get("wallet") or "")))

    metrics_by_index: dict[int, PaperMetric] = {}
    pending: list[PaperMetric] = []
    pending_cursor = 0
    wallet_stats: defaultdict[str, WalletStats] = defaultdict(WalletStats)
    active: list[dict[str, Any]] = []
    last_entry_by_wallet_asset: dict[tuple[str, str], int] = {}
    ledger: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    skip_counts: Counter[str] = Counter()

    for row_index, row in enumerate(rows):
        ts = parse_timestamp(row)
        if ts is None:
            skip_row(skipped, skip_counts, row, "missing_timestamp", args.max_skipped_rows)
            continue

        while pending_cursor < len(pending) and pending[pending_cursor].ready_timestamp <= ts:
            ready = pending[pending_cursor]
            if ready.wallet:
                wallet_stats[ready.wallet].add(ready.net_edge_cents)
            pending_cursor += 1

        active = [item for item in active if float(item.get("exit_timestamp") or 0.0) > ts + args.entry_delay_seconds]

        metric = build_metric(row_index, row, args)
        if metric is not None:
            metrics_by_index[row_index] = metric
            pending.append(metric)

        category = str(row.get("category") or "").lower()
        if args.category.lower() != "all" and category != args.category.lower():
            skip_row(skipped, skip_counts, row, "category_filter", args.max_skipped_rows)
            continue

        wallet = str(row.get("wallet") or "").lower()
        asset = str(row.get("asset") or "")
        condition_id = str(row.get("condition_id") or "")
        if not wallet or not asset:
            skip_row(skipped, skip_counts, row, "missing_wallet_or_asset", args.max_skipped_rows)
            continue

        if metric is None:
            skip_row(skipped, skip_counts, row, "unclosed_or_invalid_delay_proxy", args.max_skipped_rows)
            continue

        if not (args.min_entry_price <= metric.entry_exec_price <= args.max_entry_price):
            skip_row(skipped, skip_counts, row, "entry_price_filter", args.max_skipped_rows)
            continue

        stats = wallet_stats[wallet]
        prior_mean = stats.mean
        prior_win_rate = stats.win_rate
        prior_median = stats.median
        prior_one_hit = stats.one_hit_penalty
        if stats.count < args.min_prior_trades:
            skip_row(skipped, skip_counts, row, "not_enough_prior_trades", args.max_skipped_rows)
            continue
        if prior_mean is None or prior_mean < args.min_prior_mean_net_edge_cents:
            skip_row(skipped, skip_counts, row, "prior_edge_too_low", args.max_skipped_rows)
            continue
        if prior_win_rate is None or prior_win_rate < args.min_prior_win_rate:
            skip_row(skipped, skip_counts, row, "prior_win_rate_too_low", args.max_skipped_rows)
            continue
        if prior_one_hit > args.max_prior_one_hit_penalty:
            skip_row(skipped, skip_counts, row, "prior_one_hit_too_high", args.max_skipped_rows)
            continue

        dedupe_key = (wallet, asset)
        entry_ts = ts + args.entry_delay_seconds
        last_entry = last_entry_by_wallet_asset.get(dedupe_key)
        if last_entry is not None and entry_ts - last_entry < args.dedupe_seconds:
            skip_row(skipped, skip_counts, row, "dedupe_window", args.max_skipped_rows)
            continue

        stake = trade_stake(stats, args)
        if active_notional(active) + stake > args.max_open_notional_usd:
            skip_row(skipped, skip_counts, row, "portfolio_open_cap", args.max_skipped_rows)
            continue
        if active_notional(active, "wallet", wallet) + stake > args.max_wallet_open_notional_usd:
            skip_row(skipped, skip_counts, row, "wallet_open_cap", args.max_skipped_rows)
            continue
        if active_notional(active, "condition_id", condition_id) + stake > args.max_market_open_notional_usd:
            skip_row(skipped, skip_counts, row, "market_open_cap", args.max_skipped_rows)
            continue

        shares = stake / metric.entry_exec_price
        pnl = shares * (metric.exit_exec_price - metric.entry_exec_price)
        roi = pnl / stake if stake > EPS else 0.0
        last_entry_by_wallet_asset[dedupe_key] = entry_ts
        active.append(
            {
                "wallet": wallet,
                "condition_id": condition_id,
                "asset": asset,
                "stake_usd": stake,
                "exit_timestamp": metric.ready_timestamp,
            }
        )
        ledger.append(
            {
                "signal_timestamp_utc": timestamp_utc(ts),
                "entry_timestamp_utc": timestamp_utc(entry_ts),
                "exit_timestamp_utc": timestamp_utc(metric.ready_timestamp),
                "wallet": wallet,
                "pseudonym": row.get("pseudonym", ""),
                "category": category,
                "title": row.get("title", ""),
                "slug": row.get("slug", ""),
                "outcome": row.get("outcome", ""),
                "asset": asset,
                "condition_id": condition_id,
                "direction": metric.direction,
                "stake_usd": stake,
                "shares": shares,
                "leader_entry_price": safe_float(row.get("entry_price")),
                "entry_proxy_price": metric.entry_proxy_price,
                "exit_proxy_price": metric.exit_proxy_price,
                "entry_exec_price": metric.entry_exec_price,
                "exit_exec_price": metric.exit_exec_price,
                "gross_edge_cents": metric.gross_edge_cents,
                "total_cost_cents": metric.total_cost_cents,
                "net_edge_cents": metric.net_edge_cents,
                "pnl_usd": pnl,
                "roi": roi,
                "prior_trade_count": stats.count,
                "prior_mean_net_edge_cents": prior_mean,
                "prior_median_net_edge_cents": prior_median,
                "prior_win_rate": prior_win_rate,
                "prior_one_hit_penalty": prior_one_hit,
                "spread_cents": row.get("spread_cents", ""),
                "capacity_1000_slippage_cents": row.get("capacity_1000_slippage_cents", ""),
                "rule_ambiguity_score": row.get("rule_ambiguity_score", ""),
            }
        )

    summary = summarize(ledger, skipped, skip_counts, rows, args)
    return ledger, skipped, summary


def summarize(
    ledger: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    skip_counts: Counter[str],
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    pnl_values = [float(row["pnl_usd"]) for row in ledger]
    wins = [value for value in pnl_values if value > 0.0]
    losses = [value for value in pnl_values if value < 0.0]
    deployed = sum(float(row["stake_usd"]) for row in ledger)
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in sorted(ledger, key=lambda item: str(item.get("exit_timestamp_utc") or "")):
        equity += float(row.get("pnl_usd") or 0.0)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    by_wallet: defaultdict[str, dict[str, float]] = defaultdict(lambda: {"trades": 0.0, "pnl_usd": 0.0, "stake_usd": 0.0})
    for row in ledger:
        wallet = str(row.get("wallet") or "")
        by_wallet[wallet]["trades"] += 1.0
        by_wallet[wallet]["pnl_usd"] += float(row.get("pnl_usd") or 0.0)
        by_wallet[wallet]["stake_usd"] += float(row.get("stake_usd") or 0.0)
    top_wallets = [
        {
            "wallet": wallet,
            "trades": int(values["trades"]),
            "pnl_usd": values["pnl_usd"],
            "roi_on_deployed": values["pnl_usd"] / values["stake_usd"] if values["stake_usd"] > EPS else None,
        }
        for wallet, values in by_wallet.items()
    ]
    top_wallets.sort(key=lambda row: row["pnl_usd"], reverse=True)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_rows": len(rows),
        "closed_paper_trades": len(ledger),
        "skipped_rows_recorded": len(skipped),
        "skip_counts": dict(skip_counts.most_common()),
        "entry_delay_seconds": args.entry_delay_seconds,
        "exit_delay_seconds": args.exit_delay_seconds,
        "direction": args.direction,
        "category": args.category,
        "capital_usd": args.capital_usd,
        "stake_usd": args.stake_usd,
        "deployed_notional_usd": deployed,
        "net_pnl_usd": sum(pnl_values),
        "roi_on_deployed": sum(pnl_values) / deployed if deployed > EPS else None,
        "win_rate": len(wins) / len(ledger) if ledger else None,
        "average_pnl_usd": statistics.fmean(pnl_values) if pnl_values else None,
        "average_net_edge_cents": statistics.fmean([float(row["net_edge_cents"]) for row in ledger]) if ledger else None,
        "profit_factor": gross_profit / gross_loss if gross_loss > EPS else None,
        "max_closed_trade_drawdown_usd": max_drawdown,
        "top_wallets": top_wallets[:10],
    }


def write_summary_md(path: Path, summary: dict[str, Any], ledger: list[dict[str, Any]]) -> None:
    def fmt(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    lines = [
        "# Polymarket Delayed-Copy Paper Strategy",
        "",
        f"Generated: {summary['generated_at_utc']}",
        "",
        "## Strategy Equation",
        "",
        "For a wallet BUY at time `t`, this paper strategy copies only if that wallet already has enough matured prior trades:",
        "",
        "```text",
        "entry = P_next_trade(t + entry_delay) + entry_cost",
        "exit  = P_next_trade(t + exit_delay) - exit_cost",
        "shares = stake_usd / entry",
        "pnl = shares * (exit - entry)",
        "```",
        "",
        "The decision layer uses only prior wallet records whose `t + exit_delay` is already in the past at signal time.",
        "",
        "## Result",
        "",
        f"- Input rows: {summary['input_rows']}",
        f"- Closed paper trades: {summary['closed_paper_trades']}",
        f"- Entry/exit delay seconds: {summary['entry_delay_seconds']} / {summary['exit_delay_seconds']}",
        f"- Direction: {summary['direction']}",
        f"- Category filter: {summary['category']}",
        f"- Deployed notional USD: {fmt(summary['deployed_notional_usd'])}",
        f"- Net PnL USD: {fmt(summary['net_pnl_usd'])}",
        f"- ROI on deployed: {fmt(summary['roi_on_deployed'])}",
        f"- Win rate: {fmt(summary['win_rate'])}",
        f"- Average net edge cents/share: {fmt(summary['average_net_edge_cents'])}",
        f"- Profit factor: {fmt(summary['profit_factor'])}",
        f"- Max closed-trade drawdown USD: {fmt(summary['max_closed_trade_drawdown_usd'])}",
        "",
        "## Skip Counts",
        "",
        "| reason | count |",
        "|---|---:|",
    ]
    for reason, count in summary["skip_counts"].items():
        lines.append(f"| {reason} | {count} |")

    lines.extend(
        [
            "",
            "## Top Wallets In Ledger",
            "",
            "| wallet | trades | pnl_usd | roi_on_deployed |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in summary["top_wallets"]:
        lines.append(
            "| {wallet} | {trades} | {pnl} | {roi} |".format(
                wallet=row["wallet"],
                trades=row["trades"],
                pnl=fmt(row["pnl_usd"]),
                roi=fmt(row["roi_on_deployed"]),
            )
        )

    lines.extend(
        [
            "",
            "## First Ledger Rows",
            "",
            "| signal | wallet | stake | entry | exit | pnl | prior_n | title |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in ledger[:12]:
        lines.append(
            "| {signal} | {wallet} | {stake} | {entry} | {exit} | {pnl} | {prior_n} | {title} |".format(
                signal=str(row.get("signal_timestamp_utc", ""))[:19],
                wallet=str(row.get("wallet", ""))[:12] + "...",
                stake=fmt(float(row.get("stake_usd") or 0.0)),
                entry=fmt(float(row.get("entry_exec_price") or 0.0)),
                exit=fmt(float(row.get("exit_exec_price") or 0.0)),
                pnl=fmt(float(row.get("pnl_usd") or 0.0)),
                prior_n=row.get("prior_trade_count", ""),
                title=str(row.get("title", ""))[:70].replace("|", "/"),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    rows = [
        {
            "timestamp": "1000",
            "wallet": "0xa",
            "asset": "asset1",
            "condition_id": "market1",
            "category": "crypto",
            "entry_price": "0.40",
            "edge_30s_cents": "1.0",
            "edge_120s_cents": "4.0",
        },
        {
            "timestamp": "1200",
            "wallet": "0xa",
            "asset": "asset1",
            "condition_id": "market1",
            "category": "crypto",
            "entry_price": "0.40",
            "edge_30s_cents": "1.0",
            "edge_120s_cents": "4.0",
        },
        {
            "timestamp": "1400",
            "wallet": "0xa",
            "asset": "asset1",
            "condition_id": "market1",
            "category": "crypto",
            "entry_price": "0.40",
            "edge_30s_cents": "1.0",
            "edge_120s_cents": "4.0",
        },
        {
            "timestamp": "1700",
            "wallet": "0xa",
            "asset": "asset2",
            "condition_id": "market2",
            "category": "crypto",
            "entry_price": "0.40",
            "edge_30s_cents": "1.0",
            "edge_120s_cents": "5.0",
            "title": "Synthetic signal",
        },
        {
            "timestamp": "1800",
            "wallet": "0xb",
            "asset": "asset3",
            "condition_id": "market3",
            "category": "crypto",
            "entry_price": "0.40",
            "edge_30s_cents": "1.0",
            "edge_120s_cents": "5.0",
        },
    ]
    args = argparse.Namespace(
        entry_delay_seconds=30,
        exit_delay_seconds=120,
        category="crypto",
        direction="copy",
        capital_usd=10_000.0,
        stake_usd=100.0,
        max_stake_usd=100.0,
        max_open_notional_usd=1_000.0,
        max_wallet_open_notional_usd=500.0,
        max_market_open_notional_usd=500.0,
        min_entry_price=0.05,
        max_entry_price=0.92,
        min_prior_trades=3,
        min_prior_mean_net_edge_cents=0.4,
        min_prior_win_rate=0.55,
        max_prior_one_hit_penalty=0.75,
        entry_cost_cents=0.5,
        exit_cost_cents=0.5,
        safety_cost_cents=0.5,
        fallback_spread_cents=1.0,
        min_total_cost_cents=1.5,
        dedupe_seconds=60,
        max_skipped_rows=100,
    )
    ledger, _skipped, summary = run_strategy(rows, args)
    assert len(ledger) == 1, ledger
    assert summary["closed_paper_trades"] == 1
    assert ledger[0]["pnl_usd"] > 0.0
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return

    probe_dir = args.probe_output_dir if args.probe_output_dir.is_absolute() else REPO_ROOT / args.probe_output_dir
    input_csv = args.input_csv or (probe_dir / "trade_edges.csv")
    input_csv = input_csv if input_csv.is_absolute() else REPO_ROOT / input_csv
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir

    rows = read_csv_rows(input_csv)
    merge_market_fields(rows, load_market_by_asset(probe_dir))
    ledger, skipped, summary = run_strategy(rows, args)

    write_csv(output_dir / "paper_ledger.csv", ledger)
    write_csv(output_dir / "skipped_signals.csv", skipped)
    write_json(
        output_dir / "summary.json",
        {
            "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            "input_csv": str(input_csv),
            **summary,
        },
    )
    write_summary_md(output_dir / "summary.md", summary, ledger)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
