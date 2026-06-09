"""Probe XRPUSDT Binance futures with true aggTrade TFI + four-cell policy.

Inputs:
- Binance Vision USD-M futures aggTrades zip files.
- Hugging Face Binance futures XRPUSDT depth20 orderbook parquet files.

The strategy clock is the L2 event clock. Trades are streamed into a rolling
window before each L2 frame, producing the original trade-flow imbalance:

    TFI = (taker_buy_qty - taker_sell_qty) / (taker_buy_qty + taker_sell_qty)

For Binance aggTrades, ``is_buyer_maker=true`` means the buyer was maker, so
the taker was seller.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


REPO_ROOT = Path(__file__).resolve().parents[1]
STRATEGY_DIR = (
    REPO_ROOT
    / "systems"
    / "ccusdt_replay_exchange"
    / "strategies"
    / "python"
    / "ccusdt_tfi_core_idle01"
)
sys.path.insert(0, str(STRATEGY_DIR))

from shadow_policy import ShadowFourCellPolicy  # noqa: E402


EPS = 1e-12


@dataclass
class Trade:
    ts_us: int
    side: str
    price: float
    qty: float


class RollingTfi:
    def __init__(self, window_us: int) -> None:
        self.window_us = int(window_us)
        self.trades: deque[Trade] = deque()
        self.buy_qty = 0.0
        self.sell_qty = 0.0
        self.notional = 0.0

    def add(self, trade: Trade) -> None:
        self.trades.append(trade)
        if trade.side == "buy":
            self.buy_qty += trade.qty
        elif trade.side == "sell":
            self.sell_qty += trade.qty
        self.notional += trade.price * trade.qty
        self.trim(trade.ts_us)

    def trim(self, ts_us: int) -> None:
        min_ts = ts_us - self.window_us
        while self.trades and self.trades[0].ts_us < min_ts:
            old = self.trades.popleft()
            if old.side == "buy":
                self.buy_qty -= old.qty
            elif old.side == "sell":
                self.sell_qty -= old.qty
            self.notional -= old.price * old.qty
        if abs(self.buy_qty) <= EPS:
            self.buy_qty = 0.0
        if abs(self.sell_qty) <= EPS:
            self.sell_qty = 0.0
        if abs(self.notional) <= EPS:
            self.notional = 0.0

    @property
    def count(self) -> int:
        return len(self.trades)

    @property
    def abs_qty(self) -> float:
        return self.buy_qty + self.sell_qty

    @property
    def tfi(self) -> float | None:
        denom = self.abs_qty
        if denom <= EPS:
            return None
        return (self.buy_qty - self.sell_qty) / denom


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--l2-dir",
        type=Path,
        default=Path("data/hf/binance-future-orderbook/XRPUSDT"),
    )
    parser.add_argument(
        "--trades-dir",
        type=Path,
        default=Path("data/binance_vision/futures_um/daily/aggTrades/XRPUSDT"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/binance_xrp_true_tfi_four_cell_probe"),
    )
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-rows-per-file", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--trade-window-us", type=int, default=2_000_000)
    parser.add_argument("--frames-threshold", type=float, default=31.0)
    parser.add_argument("--overlay-threshold", type=float, default=59.8)
    parser.add_argument(
        "--gamma-preset",
        choices=("core_q70", "full_anchor", "high_gamma_q70_capacity"),
        default="core_q70",
    )
    parser.add_argument("--sample-depth-stride", type=int, default=1000)
    return parser.parse_args()


def first_level(raw: str | None) -> tuple[float | None, float | None]:
    if not raw:
        return None, None
    try:
        parts = raw.split('"', 4)
        return float(parts[1]), float(parts[3])
    except (IndexError, TypeError, ValueError):
        return None, None


def levels_from_json(raw: str | None) -> list[tuple[float, float]]:
    if not raw:
        return []
    try:
        return [(float(price), float(qty)) for price, qty in json.loads(raw)]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def top20_notional(levels: list[tuple[float, float]]) -> float:
    return sum(price * qty for price, qty in levels[:20])


def date_from_l2_file(path: Path) -> str:
    return path.name.split("_", 1)[0]


def load_trades(trades_dir: Path, date: str) -> list[Trade]:
    path = trades_dir / f"XRPUSDT-aggTrades-{date}.zip"
    if not path.exists():
        raise FileNotFoundError(path)
    out: list[Trade] = []
    with zipfile.ZipFile(path) as zf:
        names = [name for name in zf.namelist() if name.endswith(".csv")]
        if not names:
            raise ValueError(f"missing csv inside {path}")
        with zf.open(names[0]) as handle:
            reader = csv.reader(line.decode("utf-8") for line in handle)
            for row in reader:
                if not row or row[0] == "agg_trade_id":
                    continue
                is_buyer_maker = str(row[6]).strip().lower() == "true"
                out.append(
                    Trade(
                        ts_us=int(row[5]) * 1000,
                        side="sell" if is_buyer_maker else "buy",
                        price=float(row[1]),
                        qty=float(row[2]),
                    )
                )
    return out


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def summarize(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": percentile(values, 0.5),
        "p10": percentile(values, 0.1),
        "p90": percentile(values, 0.9),
    }


def close_net_bps(close: dict[str, Any], close_spread_bps: float | None) -> float | None:
    try:
        gross = float(close["pnl_bps"])
        entry_spread = float(close["entry_spread_bps"])
        close_spread = float(close_spread_bps or 0.0)
    except (KeyError, TypeError, ValueError):
        return None
    return gross - 0.5 * entry_spread - 0.5 * close_spread


def main() -> None:
    args = parse_args()
    files = sorted(args.l2_dir.glob("*.parquet"))
    if args.max_files > 0:
        files = files[: args.max_files]
    if not files:
        raise SystemExit(f"no parquet files under {args.l2_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        gamma_preset=args.gamma_preset,
    )

    rolling = RollingTfi(args.trade_window_us)
    prev_mid: float | None = None
    prev_bid: float | None = None
    prev_ask: float | None = None
    prev_bid_qty: float | None = None
    prev_ask_qty: float | None = None
    last_mid_change_index: int | None = None
    mid_history: deque[float] = deque(maxlen=25)
    event_index = 0

    entries: list[dict[str, Any]] = []
    closes: list[dict[str, Any]] = []
    spread_samples: list[float] = []
    depth20_bid_notional_samples: list[float] = []
    depth20_ask_notional_samples: list[float] = []
    tfi_samples: list[float] = []

    rows_seen = 0
    rows_valid = 0
    rows_with_trades = 0
    rows_pure_tfi = 0
    trades_loaded_total = 0
    file_summaries: list[dict[str, Any]] = []

    for file_idx, file_path in enumerate(files, 1):
        date = date_from_l2_file(file_path)
        day_trades = load_trades(args.trades_dir, date)
        trades_loaded_total += len(day_trades)
        trade_idx = 0
        pf = pq.ParquetFile(file_path)
        file_rows = 0
        file_valid = 0
        file_frames_with_trades = 0
        print(
            f"[{file_idx}/{len(files)}] {file_path.name} l2_rows={pf.metadata.num_rows} trades={len(day_trades)}",
            flush=True,
        )
        for batch in pf.iter_batches(
            batch_size=args.batch_size,
            columns=["E", "T", "bids", "asks"],
        ):
            data = batch.to_pydict()
            for raw_e, raw_t, raw_bids, raw_asks in zip(
                data["E"], data["T"], data["bids"], data["asks"]
            ):
                if args.max_rows_per_file and file_rows >= args.max_rows_per_file:
                    break
                file_rows += 1
                rows_seen += 1
                ts_ms = raw_e or raw_t
                if ts_ms is None:
                    continue
                ts_us = int(ts_ms) * 1000
                while trade_idx < len(day_trades) and day_trades[trade_idx].ts_us <= ts_us:
                    rolling.add(day_trades[trade_idx])
                    trade_idx += 1
                rolling.trim(ts_us)

                bid, bid_qty = first_level(raw_bids)
                ask, ask_qty = first_level(raw_asks)
                if (
                    bid is None
                    or ask is None
                    or bid_qty is None
                    or ask_qty is None
                    or bid <= 0.0
                    or ask <= 0.0
                    or bid >= ask
                ):
                    continue

                rows_valid += 1
                file_valid += 1
                event_index += 1
                mid = 0.5 * (bid + ask)
                spread_bps = (ask - bid) / mid * 10_000.0
                spread_samples.append(spread_bps)
                if args.sample_depth_stride > 0 and rows_valid % args.sample_depth_stride == 0:
                    depth20_bid_notional_samples.append(top20_notional(levels_from_json(raw_bids)))
                    depth20_ask_notional_samples.append(top20_notional(levels_from_json(raw_asks)))

                tfi = rolling.tfi
                trade_count = rolling.count
                if tfi is not None:
                    tfi_samples.append(tfi)
                if trade_count > 0:
                    rows_with_trades += 1
                    file_frames_with_trades += 1
                if tfi is not None and abs(tfi) >= 1.0 - 1e-12:
                    rows_pure_tfi += 1

                mid_changed = prev_mid is not None and abs(mid - prev_mid) > EPS
                if mid_changed:
                    last_mid_change_index = event_index - 1
                frames_since_mid_change = (
                    math.inf
                    if last_mid_change_index is None
                    else float((event_index - 1) - last_mid_change_index)
                )

                past_event_25_bps = None
                if len(mid_history) >= 25:
                    past_mid = mid_history[0]
                    if past_mid > 0.0:
                        past_event_25_bps = math.log(mid / past_mid) * 10_000.0
                mid_history.append(mid)

                frame = {
                    "schema_id": "binance_xrp_true_tfi_decision_frame_v1",
                    "runtime_safe": True,
                    "observed_seq": event_index,
                    "exchange_ts_us": ts_us,
                    "local_ts_us": ts_us,
                    "local_timestamp": ts_us,
                    "event_index": event_index,
                    "factor_eligible": True,
                    "best_bid_price": bid,
                    "best_bid_amount": bid_qty,
                    "best_ask_price": ask,
                    "best_ask_amount": ask_qty,
                    "mid_price": mid,
                    "mid": mid,
                    "spread_bps": spread_bps,
                    "bid_levels": 20,
                    "ask_levels": 20,
                    "trade_window_count": trade_count,
                    "trade_buy_amount": rolling.buy_qty,
                    "trade_sell_amount": rolling.sell_qty,
                    "trade_notional_quote": rolling.notional,
                    "trade_flow_imbalance": tfi,
                    "mid_change_prev": mid_changed,
                    "quote_change_prev": (
                        prev_bid is not None
                        and prev_ask is not None
                        and (abs(bid - prev_bid) > EPS or abs(ask - prev_ask) > EPS)
                    ),
                    "top_size_change_prev": (
                        prev_bid_qty is not None
                        and prev_ask_qty is not None
                        and (
                            abs(bid_qty - prev_bid_qty) > EPS
                            or abs(ask_qty - prev_ask_qty) > EPS
                        )
                    ),
                    "frames_since_mid_change": frames_since_mid_change,
                    "past_event_25_bps": past_event_25_bps,
                    "fwd_time_60s_bucket": int(ts_us // 60_000_000),
                }

                signal = policy.on_decision_frame(frame, event_index)
                if signal is not None:
                    for close in signal.get("closed_now") or []:
                        row = dict(close)
                        row["close_spread_bps"] = spread_bps
                        row["net_taker_bps_est"] = close_net_bps(close, spread_bps)
                        closes.append(row)
                    if signal.get("event_kind") == "shadow_entry":
                        row = {
                            key: signal.get(key)
                            for key in (
                                "shadow_position_id",
                                "observed_seq",
                                "local_ts_us",
                                "direction",
                                "side",
                                "membership_set",
                                "cell",
                                "feature_value",
                                "past_event_25_bps",
                                "frames_since_mid_change",
                                "entry_spread_bps",
                                "a_r5_raw",
                                "a_r5_ready",
                                "b_frames_ge_q90",
                                "base_weight",
                                "weak_overlay_weight",
                                "gamma",
                                "target_exposure",
                            )
                        }
                        row["mid"] = mid
                        row["trade_window_count"] = trade_count
                        row["trade_buy_amount"] = rolling.buy_qty
                        row["trade_sell_amount"] = rolling.sell_qty
                        row["trade_notional_quote"] = rolling.notional
                        row["best_bid_notional"] = bid * bid_qty
                        row["best_ask_notional"] = ask * ask_qty
                        entries.append(row)

                prev_bid, prev_bid_qty, prev_ask, prev_ask_qty, prev_mid = (
                    bid,
                    bid_qty,
                    ask,
                    ask_qty,
                    mid,
                )
            if args.max_rows_per_file and file_rows >= args.max_rows_per_file:
                break
        file_summaries.append(
            {
                "file": file_path.name,
                "rows_seen": file_rows,
                "rows_valid": file_valid,
                "trades_loaded": len(day_trades),
                "frames_with_trade_window": file_frames_with_trades,
            }
        )

    by_cell: dict[str, list[float]] = {}
    by_cell_net: dict[str, list[float]] = {}
    by_membership: dict[str, list[float]] = {}
    for close in closes:
        cell = str(close.get("cell") or "")
        membership = str(close.get("membership_set") or "")
        pnl = close.get("pnl_bps")
        net = close.get("net_taker_bps_est")
        if pnl is not None:
            by_cell.setdefault(cell, []).append(float(pnl))
            by_membership.setdefault(membership, []).append(float(pnl))
        if net is not None:
            by_cell_net.setdefault(cell, []).append(float(net))

    summary = {
        "schema_id": "binance_xrp_true_tfi_four_cell_probe_summary_v1",
        "symbol": "XRPUSDT",
        "l2_source": "predict-quant/binance-future-orderbook",
        "trade_source": "Binance Vision USD-M futures daily aggTrades",
        "l2_dir": str(args.l2_dir),
        "trades_dir": str(args.trades_dir),
        "files": len(files),
        "rows_seen": rows_seen,
        "rows_valid": rows_valid,
        "trades_loaded": trades_loaded_total,
        "rows_with_trade_window": rows_with_trades,
        "rows_pure_tfi": rows_pure_tfi,
        "entries": len(entries),
        "closes": len(closes),
        "tfi": {
            "window_us": args.trade_window_us,
            "definition": "(taker_buy_qty - taker_sell_qty)/(taker_buy_qty + taker_sell_qty)",
            "source": "aggTrades is_buyer_maker; true => taker sell, false => taker buy",
            "samples": summarize(tfi_samples),
        },
        "policy": policy.policy_params(),
        "gross_mid_bps": summarize([float(c["pnl_bps"]) for c in closes if c.get("pnl_bps") is not None]),
        "net_taker_bps_est": summarize(
            [float(c["net_taker_bps_est"]) for c in closes if c.get("net_taker_bps_est") is not None]
        ),
        "spread_bps": summarize(spread_samples),
        "depth20_bid_notional_sampled": summarize(depth20_bid_notional_samples),
        "depth20_ask_notional_sampled": summarize(depth20_ask_notional_samples),
        "by_cell_gross_mid_bps": {cell: summarize(vals) for cell, vals in sorted(by_cell.items())},
        "by_cell_net_taker_bps_est": {
            cell: summarize(vals) for cell, vals in sorted(by_cell_net.items())
        },
        "by_membership_gross_mid_bps": {
            key: summarize(vals) for key, vals in sorted(by_membership.items())
        },
        "file_summaries": file_summaries,
    }

    entries_path = args.output_dir / "entries.csv"
    closes_path = args.output_dir / "closes.csv"
    summary_path = args.output_dir / "summary.json"
    md_path = args.output_dir / "summary.md"

    if entries:
        with entries_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted(entries[0].keys()))
            writer.writeheader()
            writer.writerows(entries)
    if closes:
        with closes_path.open("w", newline="", encoding="utf-8") as handle:
            fieldnames = sorted({key for row in closes for key in row.keys()})
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(closes)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, allow_nan=False)
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(render_markdown(summary))

    print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))


def fmt(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def render_stat_line(label: str, stats: dict[str, Any]) -> str:
    return (
        f"- {label}: n={stats.get('count')}, mean={fmt(stats.get('mean'))}, "
        f"median={fmt(stats.get('median'))}, p10={fmt(stats.get('p10'))}, "
        f"p90={fmt(stats.get('p90'))}"
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# XRPUSDT True TFI Four-Cell Probe",
        "",
        "This diagnostic uses Binance Vision USD-M futures aggTrades for true taker-flow TFI, aligned to the L2 orderbook event clock.",
        "",
        f"- files: {summary['files']}",
        f"- L2 rows seen: {summary['rows_seen']}",
        f"- trades loaded: {summary['trades_loaded']}",
        f"- rows with non-empty trade window: {summary['rows_with_trade_window']}",
        f"- pure TFI rows: {summary['rows_pure_tfi']}",
        f"- entries: {summary['entries']}",
        f"- closes: {summary['closes']}",
        "",
        "## Headline",
        render_stat_line("gross_mid_bps", summary["gross_mid_bps"]),
        render_stat_line("net_taker_bps_est", summary["net_taker_bps_est"]),
        render_stat_line("spread_bps", summary["spread_bps"]),
        render_stat_line("tfi_samples", summary["tfi"]["samples"]),
        render_stat_line("depth20_bid_notional_sampled", summary["depth20_bid_notional_sampled"]),
        render_stat_line("depth20_ask_notional_sampled", summary["depth20_ask_notional_sampled"]),
        "",
        "## By Cell Gross Mid Bps",
    ]
    for cell, stats in summary["by_cell_gross_mid_bps"].items():
        lines.append(render_stat_line(cell, stats))
    lines.extend(["", "## By Cell Net Taker Bps Est"])
    for cell, stats in summary["by_cell_net_taker_bps_est"].items():
        lines.append(render_stat_line(cell, stats))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
