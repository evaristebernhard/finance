#!/usr/bin/env python
"""CCUSDT V2 incremental-L2 queue-pressure fill probe.

Research-only execution realism layer for the focused v2 CCUSDT candidates.
This extends the first `book_ticker + trades` fill proxy by reading local
Bullish Tardis `incremental_book_L2` updates at the posted top-of-book price.

Model intent:

- post a small maker order at the best bid/ask after a latency assumption;
- initialize queue ahead from top-of-book size at arrival;
- let same-price L2 amount decreases reduce queue ahead, after first absorbing
  post-arrival additions as behind-us liquidity;
- let opposite-side trades at/through the posted price fill our order only
  after queue ahead is depleted;
- score the original 60s horizon exit after fee/stress bps.

This is still not production execution evidence. It has no private order ack,
real venue queue priority, hidden liquidity, cancel/replace behavior, measured
latency, or real fee tier.
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

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_l2_queue_fill_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_l2_queue_fill_v1"
FRAMEWORK_RUN_TAG = "20260518_ccusdt_v2_framework_v1"
US_PER_MS = 1_000
US_PER_SECOND = 1_000_000
PRICE_SCALE = 100_000_000
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
    def incremental_l2_root(self) -> Path:
        return self.data_root / "external" / "bullish_incremental_book_L2" / "symbol=CCUSDT"

    @property
    def queue_events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_events_{self.run_tag}.csv"

    @property
    def queue_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_summary_{self.run_tag}.csv"

    @property
    def queue_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_l2_queue_fill_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-l2-queue-fill-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 incremental-L2 queue fill probe.")
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
    parser.add_argument("--l2-chunk-rows", type=int, default=750_000)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def price_key(value: float) -> int:
    return int(round(float(value) * PRICE_SCALE))


def price_keys(values: Iterable[float] | np.ndarray | pd.Series) -> np.ndarray:
    arr = np.asarray(values, dtype="float64")
    return np.rint(arr * PRICE_SCALE).astype("int64")


def data_file(root: Path, date: str) -> Path:
    return root / f"dt={date}" / "CCUSDT.csv.gz"


def read_gzip_csv(path: Path, usecols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=usecols)
    with gzip.open(path, "rt", newline="") as handle:
        return pd.read_csv(handle, usecols=usecols)


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
    if "side" in trades.columns:
        trades["side"] = trades["side"].astype(str).str.lower()
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


def build_base_cases(
    entries: pd.DataFrame,
    ticker: pd.DataFrame,
    latency_ms: list[float],
    max_timeout_ms: float,
) -> pd.DataFrame:
    ticker_times = ticker["local_timestamp"].to_numpy(dtype="float64")
    rows: list[dict[str, object]] = []
    base_case_id = 0
    for entry in entries.itertuples(index=False):
        item = entry._asdict()
        direction = int(item["direction"])
        entry_ts = float(item["entry_local_timestamp"])
        horizon_ts = entry_ts + float(item["timeout_sec"]) * US_PER_SECOND
        for latency in latency_ms:
            arrival_ts = entry_ts + latency * US_PER_MS
            deadline_max_ts = arrival_ts + max_timeout_ms * US_PER_MS
            quote_idx = asof_index(ticker_times, arrival_ts)
            exit_idx = asof_index(ticker_times, horizon_ts)
            base = {
                "base_case_id": base_case_id,
                "fold": item["fold"],
                "trigger_class": item["trigger_class"],
                "entry_quality_bin": item["entry_quality_bin"],
                "scorecard_status": item["scorecard_status"],
                "date": item["date"],
                "entry_row": int(item["entry_row"]),
                "direction": direction,
                "latency_ms": latency,
                "entry_local_timestamp": entry_ts,
                "arrival_timestamp": arrival_ts,
                "deadline_max_timestamp": deadline_max_ts,
                "horizon_timestamp": horizon_ts,
                "quote_found": quote_idx >= 0 and exit_idx >= 0,
            }
            if quote_idx >= 0 and exit_idx >= 0:
                quote = ticker.iloc[quote_idx]
                exit_quote = ticker.iloc[exit_idx]
                if direction > 0:
                    post_side = "bid"
                    post_price = float(quote["bid_price"])
                    queue_ahead = float(quote["bid_amount"])
                    exit_price = float(exit_quote["bid_price"])
                    trade_side = "sell"
                else:
                    post_side = "ask"
                    post_price = float(quote["ask_price"])
                    queue_ahead = float(quote["ask_amount"])
                    exit_price = float(exit_quote["ask_price"])
                    trade_side = "buy"
                base.update(
                    {
                        "post_side": post_side,
                        "post_price": post_price,
                        "post_price_key": price_key(post_price),
                        "queue_ahead_base": max(queue_ahead, 0.0),
                        "exit_price": exit_price,
                        "trade_side": trade_side,
                    }
                )
            else:
                base.update(
                    {
                        "post_side": "",
                        "post_price": np.nan,
                        "post_price_key": -1,
                        "queue_ahead_base": np.nan,
                        "exit_price": np.nan,
                        "trade_side": "",
                    }
                )
            rows.append(base)
            base_case_id += 1
    return pd.DataFrame(rows)


def load_reduced_l2(paths: Paths, date: str, base_cases: pd.DataFrame, chunk_rows: int) -> pd.DataFrame:
    valid = base_cases.loc[base_cases["quote_found"].astype(bool)].copy()
    if valid.empty:
        return pd.DataFrame(columns=["local_timestamp", "side", "price_key", "amount", "is_snapshot"])
    path = data_file(paths.incremental_l2_root, date)
    if not path.exists():
        return pd.DataFrame(columns=["local_timestamp", "side", "price_key", "amount", "is_snapshot"])

    min_ts = float(valid["arrival_timestamp"].min())
    max_ts = float(valid["deadline_max_timestamp"].max())
    valid["pair_key"] = valid["post_side"].astype(str) + ":" + valid["post_price_key"].astype(str)
    pair_set = set(valid["pair_key"].astype(str))
    side_set = set(valid["post_side"].astype(str))

    parts: list[pd.DataFrame] = []
    usecols = ["local_timestamp", "is_snapshot", "side", "price", "amount"]
    for chunk in pd.read_csv(path, compression="gzip", usecols=usecols, chunksize=chunk_rows):
        chunk["local_timestamp"] = pd.to_numeric(chunk["local_timestamp"], errors="coerce")
        chunk["price"] = pd.to_numeric(chunk["price"], errors="coerce")
        chunk["amount"] = pd.to_numeric(chunk["amount"], errors="coerce")
        chunk = chunk.dropna(subset=["local_timestamp", "price", "amount"])
        if chunk.empty:
            continue
        chunk["side"] = chunk["side"].astype(str).str.lower()
        mask = (
            chunk["local_timestamp"].between(min_ts, max_ts)
            & chunk["side"].isin(side_set)
            & np.isfinite(chunk["price"].to_numpy(dtype="float64"))
        )
        if not bool(mask.any()):
            continue
        sub = chunk.loc[mask, ["local_timestamp", "is_snapshot", "side", "price", "amount"]].copy()
        sub["price_key"] = price_keys(sub["price"])
        sub["pair_key"] = sub["side"].astype(str) + ":" + sub["price_key"].astype(str)
        sub = sub.loc[sub["pair_key"].isin(pair_set), ["local_timestamp", "side", "price_key", "amount", "is_snapshot"]]
        if sub.empty:
            continue
        sub["is_snapshot"] = sub["is_snapshot"].astype(str).str.lower().isin({"true", "1", "t"})
        parts.append(sub)
    if not parts:
        return pd.DataFrame(columns=["local_timestamp", "side", "price_key", "amount", "is_snapshot"])
    out = pd.concat(parts, ignore_index=True)
    out = out.sort_values(["side", "price_key", "local_timestamp"]).reset_index(drop=True)
    return out


def l2_group_arrays(l2: pd.DataFrame) -> dict[tuple[str, int], tuple[np.ndarray, np.ndarray, np.ndarray]]:
    groups: dict[tuple[str, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    if l2.empty:
        return groups
    for (side, key), g in l2.groupby(["side", "price_key"], sort=False):
        ordered = g.sort_values("local_timestamp")
        groups[(str(side), int(key))] = (
            ordered["local_timestamp"].to_numpy(dtype="float64"),
            ordered["amount"].to_numpy(dtype="float64"),
            ordered["is_snapshot"].to_numpy(dtype=bool),
        )
    return groups


def trade_group_arrays(trades: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    groups: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    if trades.empty:
        return groups
    for side, g in trades.groupby("side", sort=False):
        ordered = g.sort_values("local_timestamp")
        groups[str(side)] = (
            ordered["local_timestamp"].to_numpy(dtype="float64"),
            ordered["price"].to_numpy(dtype="float64"),
            ordered["amount"].to_numpy(dtype="float64"),
        )
    return groups


def slice_l2(
    groups: dict[tuple[str, int], tuple[np.ndarray, np.ndarray, np.ndarray]],
    side: str,
    key: int,
    start_ts: float,
    end_ts: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    found = groups.get((side, key))
    if found is None:
        empty_f = np.asarray([], dtype="float64")
        empty_b = np.asarray([], dtype=bool)
        return empty_f, empty_f, empty_b
    times, amounts, snapshots = found
    left = int(np.searchsorted(times, start_ts, side="left"))
    right = int(np.searchsorted(times, end_ts, side="right"))
    return times[left:right], amounts[left:right], snapshots[left:right]


def slice_trades(
    groups: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    side: str,
    start_ts: float,
    end_ts: float,
    post_price: float,
    direction: int,
) -> tuple[np.ndarray, np.ndarray]:
    found = groups.get(side)
    if found is None:
        empty = np.asarray([], dtype="float64")
        return empty, empty
    times, prices, amounts = found
    left = int(np.searchsorted(times, start_ts, side="left"))
    right = int(np.searchsorted(times, end_ts, side="right"))
    if right <= left:
        empty = np.asarray([], dtype="float64")
        return empty, empty
    t = times[left:right]
    p = prices[left:right]
    a = amounts[left:right]
    if direction > 0:
        mask = p <= post_price + EPS
    else:
        mask = p >= post_price - EPS
    return t[mask], a[mask]


def simulate_queue_fill(
    *,
    direction: int,
    arrival_ts: float,
    deadline_ts: float,
    queue_ahead: float,
    order_size: float,
    l2_times: np.ndarray,
    l2_amounts: np.ndarray,
    l2_snapshots: np.ndarray,
    trade_times: np.ndarray,
    trade_amounts: np.ndarray,
) -> dict[str, object]:
    l2_right = int(np.searchsorted(l2_times, deadline_ts, side="right")) if len(l2_times) else 0
    trade_right = int(np.searchsorted(trade_times, deadline_ts, side="right")) if len(trade_times) else 0

    current_amount = max(float(queue_ahead), 0.0)
    queue_remaining = max(float(queue_ahead), 0.0)
    own_remaining = max(float(order_size), 0.0)
    behind_additions = 0.0
    l2_queue_credit = 0.0
    trade_queue_credit = 0.0
    own_fill_trade = 0.0
    level_additions_ignored = 0.0
    fill_ts = np.nan
    fill_source = ""
    min_queue_remaining = queue_remaining

    i = 0
    j = 0
    while i < l2_right or j < trade_right:
        take_trade = False
        if j < trade_right:
            take_trade = i >= l2_right or trade_times[j] <= l2_times[i]

        if take_trade:
            ts = float(trade_times[j])
            raw_vol = max(float(trade_amounts[j]), 0.0)
            vol = raw_vol
            if queue_remaining > EPS and vol > EPS:
                drain = min(queue_remaining, vol)
                queue_remaining -= drain
                trade_queue_credit += drain
                vol -= drain
            if queue_remaining <= EPS and own_remaining > EPS and vol > EPS:
                fill = min(own_remaining, vol)
                own_remaining -= fill
                own_fill_trade += fill
                vol -= fill
                if own_remaining <= EPS and not np.isfinite(fill_ts):
                    fill_ts = ts
                    fill_source = "trade_after_l2_queue_drain"

            # Avoid double-counting the same visible reduction when the L2
            # update arrives after the trade print.
            visible_hit = min(max(current_amount, 0.0), raw_vol)
            current_amount = max(current_amount - visible_hit, 0.0)
            behind_additions = min(behind_additions, max(current_amount - queue_remaining, 0.0))
            min_queue_remaining = min(min_queue_remaining, queue_remaining)
            j += 1
            if own_remaining <= EPS:
                break
            continue

        ts = float(l2_times[i])
        new_amount = max(float(l2_amounts[i]), 0.0)
        delta = new_amount - current_amount
        if delta > EPS:
            behind_additions += delta
            level_additions_ignored += delta
        elif delta < -EPS:
            decrease = -delta
            behind_reduce = min(behind_additions, decrease)
            behind_additions -= behind_reduce
            residual = decrease - behind_reduce
            if residual > EPS and queue_remaining > EPS:
                credit = min(queue_remaining, residual)
                queue_remaining -= credit
                l2_queue_credit += credit
        current_amount = new_amount
        behind_additions = min(behind_additions, max(current_amount - queue_remaining, 0.0))
        min_queue_remaining = min(min_queue_remaining, queue_remaining)
        i += 1

    filled = bool(own_remaining <= EPS)
    fill_ratio = 1.0 if filled else max(0.0, min(1.0, (order_size - own_remaining) / max(order_size, EPS)))
    return {
        "filled": filled,
        "fill_ratio": fill_ratio,
        "fill_wait_ms": (fill_ts - arrival_ts) / US_PER_MS if filled else np.nan,
        "fill_source": fill_source,
        "queue_drain_l2_decrease_base": l2_queue_credit,
        "queue_drain_trade_base": trade_queue_credit,
        "own_fill_trade_base": own_fill_trade,
        "queue_remaining_base": max(queue_remaining, 0.0),
        "min_queue_remaining_base": max(min_queue_remaining, 0.0),
        "level_additions_ignored_base": level_additions_ignored,
        "l2_rows_considered": int(l2_right),
        "trade_rows_considered": int(trade_right),
    }


def event_base(paths: Paths, base: pd.Series, timeout_ms: float, notional: float, fee: float) -> dict[str, object]:
    post_price = float(base["post_price"]) if pd.notna(base["post_price"]) else np.nan
    order_size = notional / max(post_price, EPS) if np.isfinite(post_price) else np.nan
    return {
        "run_tag": paths.run_tag,
        "framework_run_tag": paths.framework_run_tag,
        "guardrail": GUARDRAIL,
        "fold": base["fold"],
        "trigger_class": base["trigger_class"],
        "entry_quality_bin": base["entry_quality_bin"],
        "scorecard_status": base["scorecard_status"],
        "date": base["date"],
        "entry_row": int(base["entry_row"]),
        "direction": int(base["direction"]),
        "latency_ms": float(base["latency_ms"]),
        "fill_timeout_ms": timeout_ms,
        "order_notional_quote": notional,
        "fee_stress_bps": fee,
        "entry_local_timestamp": float(base["entry_local_timestamp"]),
        "arrival_timestamp": float(base["arrival_timestamp"]),
        "horizon_timestamp": float(base["horizon_timestamp"]),
        "post_side": base["post_side"],
        "post_price": post_price,
        "queue_ahead_base": float(base["queue_ahead_base"]) if pd.notna(base["queue_ahead_base"]) else np.nan,
        "order_size_base": order_size,
        "exit_price": float(base["exit_price"]) if pd.notna(base["exit_price"]) else np.nan,
        "quote_found": bool(base["quote_found"]),
    }


def run_queue_events(
    entries: pd.DataFrame,
    paths: Paths,
    latency_ms: list[float],
    fill_timeouts_ms: list[float],
    notionals: list[float],
    fee_stress_bps: list[float],
    l2_chunk_rows: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    max_timeout_ms = max(fill_timeouts_ms)
    for date, day_entries in entries.groupby("date", sort=True):
        print(f"[ccusdt_l2_queue] load market date={date} entries={len(day_entries)}", flush=True)
        ticker, trades = load_day(paths, str(date))
        base_cases = build_base_cases(day_entries, ticker, latency_ms, max_timeout_ms)
        print(f"[ccusdt_l2_queue] reduce l2 date={date} base_cases={len(base_cases)}", flush=True)
        l2 = load_reduced_l2(paths, str(date), base_cases, l2_chunk_rows)
        print(f"[ccusdt_l2_queue] l2 rows kept date={date} rows={len(l2)}", flush=True)
        l2_groups = l2_group_arrays(l2)
        trade_groups = trade_group_arrays(trades)

        for base_tuple in base_cases.itertuples(index=False):
            base = pd.Series(base_tuple._asdict())
            if not bool(base["quote_found"]):
                for timeout in fill_timeouts_ms:
                    for notional in notionals:
                        for fee in fee_stress_bps:
                            rows.append(
                                {
                                    **event_base(paths, base, timeout, notional, fee),
                                    "filled": False,
                                    "fill_ratio": 0.0,
                                    "fill_wait_ms": np.nan,
                                    "fill_source": "",
                                    "queue_drain_l2_decrease_base": np.nan,
                                    "queue_drain_trade_base": np.nan,
                                    "own_fill_trade_base": np.nan,
                                    "queue_remaining_base": np.nan,
                                    "min_queue_remaining_base": np.nan,
                                    "level_additions_ignored_base": np.nan,
                                    "l2_rows_considered": 0,
                                    "trade_rows_considered": 0,
                                    "fill_gross_bps": np.nan,
                                    "fill_net_bps": np.nan,
                                    "break_even_fee_for_2bps": np.nan,
                                }
                            )
                continue

            max_deadline = float(base["arrival_timestamp"]) + max_timeout_ms * US_PER_MS
            l2_times, l2_amounts, l2_snapshots = slice_l2(
                l2_groups,
                str(base["post_side"]),
                int(base["post_price_key"]),
                float(base["arrival_timestamp"]),
                max_deadline,
            )
            trade_times, trade_amounts = slice_trades(
                trade_groups,
                str(base["trade_side"]),
                float(base["arrival_timestamp"]),
                max_deadline,
                float(base["post_price"]),
                int(base["direction"]),
            )
            for timeout in fill_timeouts_ms:
                deadline = float(base["arrival_timestamp"]) + timeout * US_PER_MS
                for notional in notionals:
                    order_size = notional / max(float(base["post_price"]), EPS)
                    sim = simulate_queue_fill(
                        direction=int(base["direction"]),
                        arrival_ts=float(base["arrival_timestamp"]),
                        deadline_ts=deadline,
                        queue_ahead=float(base["queue_ahead_base"]),
                        order_size=order_size,
                        l2_times=l2_times,
                        l2_amounts=l2_amounts,
                        l2_snapshots=l2_snapshots,
                        trade_times=trade_times,
                        trade_amounts=trade_amounts,
                    )
                    gross = np.nan
                    break_even_fee = np.nan
                    if bool(sim["filled"]):
                        gross = int(base["direction"]) * 10_000.0 * math.log(
                            max(float(base["exit_price"]), EPS) / max(float(base["post_price"]), EPS)
                        )
                        break_even_fee = gross - 2.0
                    for fee in fee_stress_bps:
                        net = gross - fee if np.isfinite(gross) else np.nan
                        rows.append(
                            {
                                **event_base(paths, base, timeout, notional, fee),
                                **sim,
                                "fill_price": float(base["post_price"]),
                                "fill_gross_bps": gross,
                                "fill_net_bps": net,
                                "break_even_fee_for_2bps": break_even_fee,
                            }
                        )
    return pd.DataFrame(rows)


def summarize(events: pd.DataFrame, paths: Paths) -> tuple[pd.DataFrame, pd.DataFrame]:
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
                "run_tag": paths.run_tag,
                "framework_run_tag": paths.framework_run_tag,
                "guardrail": GUARDRAIL,
                **dict(zip(group_cols, key)),
                "signals": int(len(g)),
                "filled": int(filled.sum()),
                "fill_rate": fill_rate,
                "avg_fill_ratio": finite_mean(g["fill_ratio"]),
                "fill_wait_p50_ms": finite_quantile(g.loc[filled, "fill_wait_ms"], 0.50),
                "queue_ahead_p50_base": finite_quantile(g["queue_ahead_base"], 0.50),
                "order_size_base": finite_mean(g["order_size_base"]),
                "l2_rows_p50": finite_quantile(g["l2_rows_considered"], 0.50),
                "trade_rows_p50": finite_quantile(g["trade_rows_considered"], 0.50),
                "queue_drain_l2_decrease_mean_base": finite_mean(g["queue_drain_l2_decrease_base"]),
                "queue_drain_trade_mean_base": finite_mean(g["queue_drain_trade_base"]),
                "own_fill_trade_mean_base": finite_mean(g["own_fill_trade_base"]),
                "queue_remaining_p50_base": finite_quantile(g["queue_remaining_base"], 0.50),
                "level_additions_ignored_p50_base": finite_quantile(g["level_additions_ignored_base"], 0.50),
                "filled_gross_mean_bps": finite_mean(gross),
                "filled_net_mean_bps": finite_mean(fill_net),
                "filled_net_median_bps": finite_quantile(fill_net, 0.50),
                "filled_net_p10_bps": finite_quantile(fill_net, 0.10),
                "filled_net_gt_2bps_rate": safe_rate(fill_net[filled] > 2.0) if filled.any() else np.nan,
                "per_signal_net_mean_bps": fill_rate * finite_mean(fill_net) if np.isfinite(fill_rate) else np.nan,
                "break_even_fee_for_2bps_mean": finite_mean(g["break_even_fee_for_2bps"]),
            }
        )
    summary = pd.DataFrame(rows)

    score_rows: list[dict[str, object]] = []
    for (fold, trigger, quality), g in summary.groupby(["fold", "trigger_class", "entry_quality_bin"], sort=True):
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
        tail_pass = bool(np.isfinite(row["filled_net_p10_bps"]) and row["filled_net_p10_bps"] > -20.0)
        status = (
            "l2_queue_fill_research_continue"
            if fill_pass and net_pass and fee_budget_pass and tail_pass
            else "l2_queue_fill_no_go"
        )
        score_rows.append(
            {
                "run_tag": paths.run_tag,
                "framework_run_tag": paths.framework_run_tag,
                "guardrail": GUARDRAIL,
                "fold": fold,
                "trigger_class": trigger,
                "entry_quality_bin": quality,
                "scorecard_status": row["scorecard_status"],
                "scenario": "latency250ms_timeout5000ms_notional100_fee2bps",
                "signals": int(row["signals"]),
                "fill_rate": row["fill_rate"],
                "avg_fill_ratio": row["avg_fill_ratio"],
                "filled_net_mean_bps": row["filled_net_mean_bps"],
                "filled_net_p10_bps": row["filled_net_p10_bps"],
                "per_signal_net_mean_bps": row["per_signal_net_mean_bps"],
                "break_even_fee_for_2bps_mean": row["break_even_fee_for_2bps_mean"],
                "queue_drain_l2_decrease_mean_base": row["queue_drain_l2_decrease_mean_base"],
                "queue_drain_trade_mean_base": row["queue_drain_trade_mean_base"],
                "own_fill_trade_mean_base": row["own_fill_trade_mean_base"],
                "fill_pass": fill_pass,
                "net_pass": net_pass,
                "per_signal_pass": per_signal_pass,
                "fee_budget_pass": fee_budget_pass,
                "tail_pass": tail_pass,
                "l2_queue_fill_status": status,
            }
        )
    return summary, pd.DataFrame(score_rows)


def write_report(
    paths: Paths,
    entries: pd.DataFrame,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    scorecard: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 L2 Queue Fill")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}` from framework run `{paths.framework_run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This pass uses local Bullish `incremental_book_L2` same-price amount decreases as queue-ahead "
        "pressure, while requiring subsequent opposite-side trades to fill the simulated maker order. "
        "It is stricter than crediting all L2 decreases as fills and less optimistic than midpoint labels."
    )
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Focus entries: `{len(entries)}`.")
    lines.append(f"- Event rows: `{len(events)}`.")
    lines.append(f"- Latency ms: `{args.latency_ms}`.")
    lines.append(f"- Fill timeout ms: `{args.fill_timeout_ms}`.")
    lines.append(f"- Order notionals quote: `{args.order_notional_quote}`.")
    lines.append(f"- Fee stress bps: `{args.fee_stress_bps}`.")
    lines.append(f"- L2 chunk rows: `{args.l2_chunk_rows}`.")
    lines.append("")
    lines.append("## L2 Queue Scorecard")
    lines.append("")
    if scorecard.empty:
        lines.append("_No scorecard rows._")
    else:
        view = scorecard.sort_values(["l2_queue_fill_status", "filled_net_mean_bps"], ascending=[True, False])
        lines.extend(
            markdown_table(
                view,
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "signals",
                    "fill_rate",
                    "avg_fill_ratio",
                    "filled_net_mean_bps",
                    "filled_net_p10_bps",
                    "per_signal_net_mean_bps",
                    "break_even_fee_for_2bps_mean",
                    "fill_pass",
                    "net_pass",
                    "fee_budget_pass",
                    "tail_pass",
                    "l2_queue_fill_status",
                ],
                30,
            )
        )
    lines.append("")
    lines.append("## Practical Scenario Queue Decomposition")
    lines.append("")
    practical = summary[
        summary["latency_ms"].eq(250.0)
        & summary["fill_timeout_ms"].eq(5000.0)
        & summary["order_notional_quote"].eq(100.0)
        & summary["fee_stress_bps"].eq(2.0)
    ]
    if practical.empty:
        lines.append("_No practical scenario rows._")
    else:
        lines.extend(
            markdown_table(
                practical.sort_values("filled_net_mean_bps", ascending=False),
                [
                    "fold",
                    "trigger_class",
                    "entry_quality_bin",
                    "signals",
                    "fill_rate",
                    "avg_fill_ratio",
                    "queue_ahead_p50_base",
                    "queue_drain_l2_decrease_mean_base",
                    "queue_drain_trade_mean_base",
                    "own_fill_trade_mean_base",
                    "filled_net_mean_bps",
                    "per_signal_net_mean_bps",
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
        "This remains research-only. A row still needs real fee tier, measured latency, order acknowledgements "
        "or live/paper fills, and walk-forward continuation before executable status."
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.queue_events_csv, paths.queue_summary_csv, paths.queue_scorecard_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append("python scripts/ccusdt_v2_l2_queue_fill.py")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    paths: Paths,
    entries: pd.DataFrame,
    events: pd.DataFrame,
    summary: pd.DataFrame,
    scorecard: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(paths.queue_events_csv, index=False)
    summary.to_csv(paths.queue_summary_csv, index=False)
    scorecard.to_csv(paths.queue_scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "framework_run_tag": paths.framework_run_tag,
        "guardrail": GUARDRAIL,
        "focus_entries": int(len(entries)),
        "event_rows": int(len(events)),
        "summary_rows": int(len(summary)),
        "scorecard_rows": int(len(scorecard)),
        "latency_ms": fill_base.parse_floats(args.latency_ms),
        "fill_timeout_ms": fill_base.parse_floats(args.fill_timeout_ms),
        "order_notional_quote": fill_base.parse_floats(args.order_notional_quote),
        "fee_stress_bps": fill_base.parse_floats(args.fee_stress_bps),
        "execution_realism_status": "l2_queue_pressure_proxy_no_private_order_ack_no_real_fee_tier",
        "outputs": {
            "queue_events_csv": str(paths.queue_events_csv),
            "queue_summary_csv": str(paths.queue_summary_csv),
            "queue_scorecard_csv": str(paths.queue_scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, entries, events, summary, scorecard, args)


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
    statuses = fill_base.parse_statuses(args.include_status)
    extras = fill_base.parse_extra_rows(args.include_extra)
    entries = choose_entries(paths, statuses, extras)
    print(f"[ccusdt_l2_queue] focus entries={len(entries)}", flush=True)
    events = run_queue_events(
        entries,
        paths,
        fill_base.parse_floats(args.latency_ms),
        fill_base.parse_floats(args.fill_timeout_ms),
        fill_base.parse_floats(args.order_notional_quote),
        fill_base.parse_floats(args.fee_stress_bps),
        args.l2_chunk_rows,
    )
    summary, scorecard = summarize(events, paths)
    write_outputs(paths, entries, events, summary, scorecard, args)
    print(f"[ccusdt_l2_queue] wrote {paths.queue_scorecard_csv}", flush=True)
    print(f"[ccusdt_l2_queue] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
