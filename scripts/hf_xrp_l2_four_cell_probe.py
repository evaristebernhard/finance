"""Probe Binance futures XRPUSDT L2 data with the old four-cell policy.

The Hugging Face orderbook dataset contains depth snapshots/updates but no
trade stream, so this script uses a clearly named L2 proxy trigger:

    rolling best-level OFI -> discretized +/-1 trigger -> ShadowFourCellPolicy

The four-cell lifecycle, R5 state, frames gate, bucket gating, and gamma sizing
come from the existing runtime-safe shadow policy. Outputs are diagnostics, not
production trading results.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
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
class RollingOfiItem:
    ts_us: int
    ofi_qty: float
    abs_qty: float
    buy_qty: float
    sell_qty: float


class RollingOfi:
    def __init__(self, window_us: int) -> None:
        self.window_us = int(window_us)
        self.items: deque[RollingOfiItem] = deque()
        self.ofi_qty = 0.0
        self.abs_qty = 0.0
        self.buy_qty = 0.0
        self.sell_qty = 0.0

    def add(self, item: RollingOfiItem) -> None:
        self.items.append(item)
        self.ofi_qty += item.ofi_qty
        self.abs_qty += item.abs_qty
        self.buy_qty += item.buy_qty
        self.sell_qty += item.sell_qty
        self.trim(item.ts_us)

    def trim(self, ts_us: int) -> None:
        min_ts = ts_us - self.window_us
        while self.items and self.items[0].ts_us < min_ts:
            old = self.items.popleft()
            self.ofi_qty -= old.ofi_qty
            self.abs_qty -= old.abs_qty
            self.buy_qty -= old.buy_qty
            self.sell_qty -= old.sell_qty

    @property
    def imbalance(self) -> float | None:
        if self.abs_qty <= EPS:
            return None
        return self.ofi_qty / self.abs_qty


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/hf/binance-future-orderbook/XRPUSDT"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/hf_xrp_l2_four_cell_probe"),
    )
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-rows-per-file", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--ofi-window-us", type=int, default=2_000_000)
    parser.add_argument("--proxy-threshold", type=float, default=0.8)
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


def best_level_ofi(
    *,
    bid: float,
    bid_qty: float,
    ask: float,
    ask_qty: float,
    prev_bid: float | None,
    prev_bid_qty: float | None,
    prev_ask: float | None,
    prev_ask_qty: float | None,
) -> tuple[float, float, float, float]:
    if prev_bid is None or prev_ask is None or prev_bid_qty is None or prev_ask_qty is None:
        return 0.0, 0.0, 0.0, 0.0

    if bid > prev_bid:
        bid_contrib = bid_qty
    elif bid < prev_bid:
        bid_contrib = -prev_bid_qty
    else:
        bid_contrib = bid_qty - prev_bid_qty

    if ask < prev_ask:
        ask_contrib = -ask_qty
    elif ask > prev_ask:
        ask_contrib = prev_ask_qty
    else:
        ask_contrib = -(ask_qty - prev_ask_qty)

    ofi = bid_contrib + ask_contrib
    abs_qty = abs(bid_contrib) + abs(ask_contrib)
    buy_qty = max(ofi, 0.0)
    sell_qty = max(-ofi, 0.0)
    return ofi, abs_qty, buy_qty, sell_qty


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


def summarize(values: list[float]) -> dict[str, float | None]:
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
    gross = close.get("pnl_bps")
    entry_spread = close.get("entry_spread_bps")
    try:
        gross_f = float(gross)
        entry_spread_f = float(entry_spread)
        close_spread_f = float(close_spread_bps or 0.0)
    except (TypeError, ValueError):
        return None
    # Taker entry + taker exit pays roughly half spread on each side.
    return gross_f - 0.5 * entry_spread_f - 0.5 * close_spread_f


def main() -> None:
    args = parse_args()
    files = sorted(args.input_dir.glob("*.parquet"))
    if args.max_files > 0:
        files = files[: args.max_files]
    if not files:
        raise SystemExit(f"no parquet files under {args.input_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy = ShadowFourCellPolicy(
        frames_threshold=args.frames_threshold,
        overlay_threshold=args.overlay_threshold,
        gamma_preset=args.gamma_preset,
    )
    rolling = RollingOfi(args.ofi_window_us)

    prev_bid = prev_bid_qty = prev_ask = prev_ask_qty = None
    prev_mid: float | None = None
    last_mid_change_index: int | None = None
    mid_history: deque[float] = deque(maxlen=25)
    event_index = 0

    entries: list[dict[str, Any]] = []
    closes: list[dict[str, Any]] = []
    spread_samples: list[float] = []
    depth1_bid_notional_samples: list[float] = []
    depth1_ask_notional_samples: list[float] = []
    depth20_bid_notional_samples: list[float] = []
    depth20_ask_notional_samples: list[float] = []
    proxy_samples: list[float] = []

    rows_seen = 0
    rows_valid = 0
    rows_trigger_proxy = 0
    file_summaries: list[dict[str, Any]] = []

    for file_idx, file_path in enumerate(files, 1):
        pf = pq.ParquetFile(file_path)
        file_rows = 0
        file_valid = 0
        print(f"[{file_idx}/{len(files)}] {file_path.name} rows={pf.metadata.num_rows}", flush=True)
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
                depth1_bid_notional_samples.append(bid * bid_qty)
                depth1_ask_notional_samples.append(ask * ask_qty)

                if args.sample_depth_stride > 0 and rows_valid % args.sample_depth_stride == 0:
                    bid_levels = levels_from_json(raw_bids)
                    ask_levels = levels_from_json(raw_asks)
                    depth20_bid_notional_samples.append(top20_notional(bid_levels))
                    depth20_ask_notional_samples.append(top20_notional(ask_levels))

                ofi, abs_qty, buy_qty, sell_qty = best_level_ofi(
                    bid=bid,
                    bid_qty=bid_qty,
                    ask=ask,
                    ask_qty=ask_qty,
                    prev_bid=prev_bid,
                    prev_bid_qty=prev_bid_qty,
                    prev_ask=prev_ask,
                    prev_ask_qty=prev_ask_qty,
                )
                rolling.add(
                    RollingOfiItem(
                        ts_us=ts_us,
                        ofi_qty=ofi,
                        abs_qty=abs_qty,
                        buy_qty=buy_qty,
                        sell_qty=sell_qty,
                    )
                )
                proxy = rolling.imbalance
                if proxy is not None:
                    proxy_samples.append(proxy)

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

                trigger_value = None
                if proxy is not None and abs(proxy) >= args.proxy_threshold:
                    trigger_value = 1.0 if proxy > 0.0 else -1.0
                    rows_trigger_proxy += 1

                frame = {
                    "schema_id": "hf_xrp_l2_proxy_decision_frame_v1",
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
                    "trade_window_count": len(rolling.items) if trigger_value is not None else 0,
                    "trade_buy_amount": rolling.buy_qty,
                    "trade_sell_amount": rolling.sell_qty,
                    "trade_notional_quote": 0.0,
                    "trade_flow_imbalance": trigger_value,
                    "l2_proxy_imbalance": proxy,
                    "l2_proxy_ofi_qty": rolling.ofi_qty,
                    "l2_proxy_abs_qty": rolling.abs_qty,
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
                        row["l2_proxy_imbalance"] = proxy
                        row["l2_proxy_abs_qty"] = rolling.abs_qty
                        row["best_bid_price"] = bid
                        row["best_ask_price"] = ask
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
        "schema_id": "hf_xrp_l2_proxy_four_cell_probe_summary_v1",
        "symbol": "XRPUSDT",
        "source_dataset": "predict-quant/binance-future-orderbook",
        "input_dir": str(args.input_dir),
        "files": len(files),
        "rows_seen": rows_seen,
        "rows_valid": rows_valid,
        "rows_trigger_proxy": rows_trigger_proxy,
        "entries": len(entries),
        "closes": len(closes),
        "proxy": {
            "name": "rolling_best_level_ofi_discretized",
            "window_us": args.ofi_window_us,
            "threshold": args.proxy_threshold,
            "note": "HF data has no trades; this is not true TFI.",
            "imbalance": summarize(proxy_samples),
        },
        "policy": policy.policy_params(),
        "gross_mid_bps": summarize([float(c["pnl_bps"]) for c in closes if c.get("pnl_bps") is not None]),
        "net_taker_bps_est": summarize(
            [float(c["net_taker_bps_est"]) for c in closes if c.get("net_taker_bps_est") is not None]
        ),
        "spread_bps": summarize(spread_samples),
        "depth1_bid_notional": summarize(depth1_bid_notional_samples),
        "depth1_ask_notional": summarize(depth1_ask_notional_samples),
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


def render_stat_line(label: str, stats: dict[str, Any]) -> str:
    return (
        f"- {label}: n={stats.get('count')}, mean={fmt(stats.get('mean'))}, "
        f"median={fmt(stats.get('median'))}, p10={fmt(stats.get('p10'))}, "
        f"p90={fmt(stats.get('p90'))}"
    )


def fmt(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# XRPUSDT L2 Proxy Four-Cell Probe",
        "",
        "This is a diagnostic probe. The Hugging Face Binance orderbook data has no trade stream, so the trigger is a rolling best-level OFI proxy, not true TFI.",
        "",
        f"- files: {summary['files']}",
        f"- rows seen: {summary['rows_seen']}",
        f"- rows valid: {summary['rows_valid']}",
        f"- proxy-trigger rows: {summary['rows_trigger_proxy']}",
        f"- entries: {summary['entries']}",
        f"- closes: {summary['closes']}",
        "",
        "## Headline",
        render_stat_line("gross_mid_bps", summary["gross_mid_bps"]),
        render_stat_line("net_taker_bps_est", summary["net_taker_bps_est"]),
        render_stat_line("spread_bps", summary["spread_bps"]),
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
