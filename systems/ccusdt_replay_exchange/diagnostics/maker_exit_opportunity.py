#!/usr/bin/env python
"""Maker-first exit opportunity diagnostic for the CCUSDT q70 idle01_g1 line.

This is an offline execution diagnostic. It reads only runtime-safe fast-run
exit rows plus canonical market truth, then asks whether an existing position
should try a passive touch exit before falling back to a taker exit.

It must not become a source of strategy labels. The output panel is a research
artifact for estimating fill hazard, unfilled decay, and selection cost.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


TTL_SEC = [1.0, 2.0, 5.0]
US_PER_SEC = 1_000_000
EPS = 1e-12

DEFAULT_RUN_SPECS = [
    (
        "fixed30_livecoherent",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_fixed30_taker_livecoherent_quoteidx_20260516_18_20260522",
    ),
    (
        "fixed45_livecoherent",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_fixed45_taker_livecoherent_quoteidx_20260516_18_20260522",
    ),
    (
        "fixed60_taker",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_fixed60_taker_quoteidx_v2_20260516_18_20260521",
    ),
    (
        "stopping_rule_v1",
        "systems/ccusdt_replay_exchange/runs/experiments/"
        "fast_adm_q70_idle01_g1_stopping_rule_v1_quoteidx_20260516_18_20260522",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument(
        "--run-spec",
        action="append",
        help="Optional profile=path. Defaults to fixed30/fixed45/fixed60/stopping_rule q70 idle01_g1 runs.",
    )
    parser.add_argument("--ttl-sec", default="1,2,5")
    parser.add_argument("--selection-window-sec", type=float, default=1.0)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(
            "systems/ccusdt_replay_exchange/runs/"
            "maker_exit_opportunity_q70_idle01_g1_20260516_18_20260522"
        ),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/markets/ccusdt/v1-tfi-maker-first-exit-opportunity-20260522.md"),
    )
    parser.add_argument("--min-bin-count", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def parse_ttls(raw: str) -> list[float]:
    out = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not out:
        raise ValueError("expected at least one TTL")
    return sorted(set(out))


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
    current = left
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def file_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "byte_size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def quote_path(repo_root: Path, symbol: str, day: str) -> Path:
    return (
        repo_root
        / "data"
        / "canonical"
        / "cex"
        / "bullish"
        / symbol
        / "quote_frame_v1"
        / f"dt={day}"
        / "part_000001.csv.gz"
    )


def trade_path(repo_root: Path, symbol: str, day: str) -> Path:
    return (
        repo_root
        / "data"
        / "canonical"
        / "cex"
        / "bullish"
        / symbol
        / "trade_event_v1"
        / f"dt={day}"
        / "part_000001.csv.gz"
    )


def decision_frame_path(repo_root: Path, symbol: str, day: str) -> Path:
    return (
        repo_root
        / "data"
        / "canonical_parquet"
        / "cex"
        / "bullish"
        / symbol
        / "decision_frame_v1"
        / f"dt={day}"
        / "part_000001.parquet"
    )


@dataclass
class QuotePoint:
    local_ts_us: int
    bid_px: float
    bid_qty: float
    ask_px: float
    ask_qty: float
    mid_px: float
    spread_bps: float


@dataclass
class FillProbe:
    touch_fill: bool
    touch_fill_ts_us: int | None
    touch_fill_delay_us: int | None
    touch_trade_qty: float
    touch_trade_count: int
    queue_fill: bool
    queue_fill_ts_us: int | None
    queue_fill_delay_us: int | None
    queue_consumed_qty: float
    queue_ahead_qty: float
    queue_fill_ratio: float


class DayMarket:
    def __init__(self, quotes: pd.DataFrame, trades: pd.DataFrame, decision_frames: pd.DataFrame) -> None:
        if quotes.empty:
            raise ValueError("quote frame is empty")
        self.quotes = quotes.sort_values("local_ts_us").reset_index(drop=True)
        self.quote_ts = self.quotes["local_ts_us"].to_numpy(dtype="int64")
        self.trades = trades.sort_values("local_ts_us").reset_index(drop=True)
        self.trade_ts = self.trades["local_ts_us"].to_numpy(dtype="int64")
        self.decision_frames = decision_frames.sort_values("local_ts_us").reset_index(drop=True)
        self.decision_ts = (
            self.decision_frames["local_ts_us"].to_numpy(dtype="int64")
            if not self.decision_frames.empty
            else np.asarray([], dtype="int64")
        )

    @classmethod
    def load(cls, repo_root: Path, symbol: str, day: str) -> "DayMarket":
        q_path = quote_path(repo_root, symbol, day)
        t_path = trade_path(repo_root, symbol, day)
        d_path = decision_frame_path(repo_root, symbol, day)
        quotes = read_quotes(q_path)
        trades = read_trades(t_path)
        decision_frames = read_decision_frames(d_path)
        return cls(quotes, trades, decision_frames)

    def quote_at_or_before(self, ts_us: int) -> QuotePoint:
        idx = bisect.bisect_right(self.quote_ts, int(ts_us)) - 1
        if idx < 0:
            idx = 0
        row = self.quotes.iloc[idx]
        return QuotePoint(
            local_ts_us=int(row["local_ts_us"]),
            bid_px=float(row["bid_px"]),
            bid_qty=max(float(row["bid_qty"]), 0.0),
            ask_px=float(row["ask_px"]),
            ask_qty=max(float(row["ask_qty"]), 0.0),
            mid_px=float(row["mid_px"]),
            spread_bps=float(row["spread_bps"]),
        )

    def quote_slice(self, start_us: int, end_us: int) -> pd.DataFrame:
        left = bisect.bisect_left(self.quote_ts, int(start_us))
        right = bisect.bisect_right(self.quote_ts, int(end_us))
        return self.quotes.iloc[left:right]

    def trade_slice(self, start_us: int, end_us: int) -> pd.DataFrame:
        left = bisect.bisect_right(self.trade_ts, int(start_us))
        right = bisect.bisect_right(self.trade_ts, int(end_us))
        return self.trades.iloc[left:right]

    def decision_frame_at_or_before(self, ts_us: int) -> dict[str, Any]:
        if self.decision_frames.empty:
            return {}
        idx = bisect.bisect_right(self.decision_ts, int(ts_us)) - 1
        if idx < 0:
            idx = 0
        return self.decision_frames.iloc[idx].to_dict()

    def fill_probe(self, *, side: str, post_price: float, queue_ahead_qty: float, start_us: int, ttl_us: int) -> FillProbe:
        trades = self.trade_slice(start_us, start_us + ttl_us)
        if trades.empty:
            return FillProbe(False, None, None, 0.0, 0, False, None, None, 0.0, queue_ahead_qty, 0.0)
        if side == "buy":
            mask = (trades["side"] == "sell") & (trades["price"] <= post_price + 1e-12)
        else:
            mask = (trades["side"] == "buy") & (trades["price"] >= post_price - 1e-12)
        hits = trades.loc[mask]
        if hits.empty:
            return FillProbe(False, None, None, 0.0, 0, False, None, None, 0.0, queue_ahead_qty, 0.0)
        touch_row = hits.iloc[0]
        cum_qty = hits["qty"].astype(float).cumsum()
        touch_ts = int(touch_row["local_ts_us"])
        touch_qty = float(hits["qty"].astype(float).sum())
        queue_threshold = max(float(queue_ahead_qty), 0.0)
        queue_fill_idx = np.flatnonzero(cum_qty.to_numpy(dtype="float64") >= queue_threshold)
        queue_fill = len(queue_fill_idx) > 0
        queue_ts: int | None = None
        queue_delay: int | None = None
        if queue_fill:
            queue_ts = int(hits.iloc[int(queue_fill_idx[0])]["local_ts_us"])
            queue_delay = queue_ts - int(start_us)
        ratio = float(touch_qty / max(queue_threshold, EPS))
        return FillProbe(
            touch_fill=True,
            touch_fill_ts_us=touch_ts,
            touch_fill_delay_us=touch_ts - int(start_us),
            touch_trade_qty=touch_qty,
            touch_trade_count=int(len(hits)),
            queue_fill=queue_fill,
            queue_fill_ts_us=queue_ts,
            queue_fill_delay_us=queue_delay,
            queue_consumed_qty=touch_qty,
            queue_ahead_qty=queue_threshold,
            queue_fill_ratio=ratio,
        )


def read_quotes(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        df = pd.read_csv(handle)
    keep = ["local_ts_us", "bid_px", "bid_qty", "ask_px", "ask_qty", "mid_px", "spread_bps"]
    df = df.loc[:, keep].copy()
    for col in keep:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["local_ts_us", "bid_px", "ask_px", "mid_px"])
    df["local_ts_us"] = df["local_ts_us"].astype("int64")
    return df


def read_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        df = pd.read_csv(handle)
    keep = ["local_ts_us", "side", "price", "qty", "notional_quote"]
    df = df.loc[:, keep].copy()
    for col in ["local_ts_us", "price", "qty", "notional_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["side"] = df["side"].astype(str).str.lower()
    df = df.dropna(subset=["local_ts_us", "price", "qty"])
    df["local_ts_us"] = df["local_ts_us"].astype("int64")
    return df


def read_decision_frames(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    columns = [
        "local_ts_us",
        "best_bid_amount",
        "best_ask_amount",
        "trade_window_count",
        "trade_flow_imbalance",
        "frames_since_mid_change",
        "past_event_25_bps",
    ]
    available = pq.ParquetFile(path).schema_arrow.names
    columns = [col for col in columns if col in available]
    table = pq.read_table(path, columns=columns)
    df = table.to_pandas()
    if "local_ts_us" in df.columns:
        df["local_ts_us"] = pd.to_numeric(df["local_ts_us"], errors="coerce").fillna(0).astype("int64")
    return df


def parse_run_specs(args: argparse.Namespace, repo_root: Path) -> list[tuple[str, Path]]:
    raw_specs = args.run_spec or [f"{name}={path}" for name, path in DEFAULT_RUN_SPECS]
    out: list[tuple[str, Path]] = []
    for item in raw_specs:
        if "=" not in item:
            raise ValueError(f"run spec must be profile=path, got {item!r}")
        profile, raw_path = item.split("=", 1)
        path = repo_path(repo_root, Path(raw_path))
        if not path.exists():
            raise FileNotFoundError(path)
        out.append((profile.strip(), path))
    return out


def load_exit_candidates(run_specs: list[tuple[str, Path]], days: set[str]) -> pd.DataFrame:
    allowed_columns = [
        "date",
        "shadow_position_id",
        "entry_seq",
        "close_seq",
        "entry_ts_us",
        "exit_ts_us",
        "held_us",
        "exit_sec",
        "exit_reason",
        "side",
        "direction",
        "cell",
        "membership_set",
        "entry_mid",
        "entry_bid",
        "entry_ask",
        "requested_exposure",
        "actual_exposure",
        "capacity_source",
    ]
    frames: list[pd.DataFrame] = []
    for profile, run_dir in run_specs:
        path = run_dir / "exits.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        available = set(pq.ParquetFile(path).schema_arrow.names)
        missing = sorted(set(allowed_columns) - available)
        if missing:
            raise ValueError(f"{path} missing runtime-safe columns: {missing}")
        df = pq.read_table(path, columns=allowed_columns).to_pandas()
        df["exit_profile_source"] = profile
        df["source_run_dir"] = str(run_dir)
        df["source_run_id"] = run_dir.name
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out[out["date"].astype(str).isin(days)].copy()
    for col in ["actual_exposure", "entry_ts_us", "exit_ts_us", "entry_bid", "entry_ask", "entry_mid"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out[out["actual_exposure"].fillna(0.0) > 0.0].copy()
    out = out[out["entry_ts_us"].notna() & out["exit_ts_us"].notna()]
    return out.sort_values(["date", "exit_ts_us", "exit_profile_source", "shadow_position_id"]).reset_index(drop=True)


def taker_net(entry_side: str, entry_bid: float, entry_ask: float, exit_price: float) -> float:
    if entry_side == "buy":
        return math.log(exit_price / entry_ask) * 10_000.0
    return math.log(entry_bid / exit_price) * 10_000.0


def maker_side_and_prices(entry_side: str, quote: QuotePoint) -> tuple[str, float, float, float]:
    if entry_side == "buy":
        return "sell", quote.bid_px, quote.ask_px, quote.ask_qty
    return "buy", quote.ask_px, quote.bid_px, quote.bid_qty


def path_hd(
    market: DayMarket,
    *,
    entry_side: str,
    entry_bid: float,
    entry_ask: float,
    entry_ts_us: int,
    exit_ts_us: int,
    immediate_taker_net_bps: float,
) -> tuple[float, float, float]:
    path = market.quote_slice(entry_ts_us, exit_ts_us)
    if path.empty:
        return immediate_taker_net_bps, 0.0, immediate_taker_net_bps
    if entry_side == "buy":
        values = np.log(path["bid_px"].to_numpy(dtype="float64") / entry_ask) * 10_000.0
    else:
        values = np.log(entry_bid / path["ask_px"].to_numpy(dtype="float64")) * 10_000.0
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return immediate_taker_net_bps, 0.0, immediate_taker_net_bps
    h_bps = float(max(np.max(values), immediate_taker_net_bps))
    d_bps = h_bps - immediate_taker_net_bps
    return h_bps, d_bps, float(np.min(values))


def recent_features(market: DayMarket, *, entry_side: str, direction: int, exit_ts_us: int, current_mid: float) -> dict[str, Any]:
    prior_quote = market.quote_at_or_before(exit_ts_us - 5 * US_PER_SEC)
    recent_mid_alpha = float(direction) * math.log(current_mid / prior_quote.mid_px) * 10_000.0
    trades = market.trade_slice(exit_ts_us - 5 * US_PER_SEC, exit_ts_us)
    same_side = "buy" if entry_side == "buy" else "sell"
    if trades.empty:
        same_qty = 0.0
        opp_qty = 0.0
        same_notional = 0.0
        opp_notional = 0.0
        count = 0
    else:
        same = trades[trades["side"] == same_side]
        opp = trades[trades["side"] != same_side]
        same_qty = float(same["qty"].sum())
        opp_qty = float(opp["qty"].sum())
        same_notional = float(same["notional_quote"].sum())
        opp_notional = float(opp["notional_quote"].sum())
        count = int(len(trades))
    qty_denom = same_qty + opp_qty
    notional_denom = same_notional + opp_notional
    return {
        "recent_mid_alpha_5s_bps": recent_mid_alpha,
        "recent_trade_count_5s": count,
        "same_flow_qty_5s": same_qty,
        "opposite_flow_qty_5s": opp_qty,
        "same_minus_opposite_qty_5s": same_qty - opp_qty,
        "same_flow_notional_5s": same_notional,
        "opposite_flow_notional_5s": opp_notional,
        "same_flow_imbalance_5s": (same_qty - opp_qty) / qty_denom if qty_denom > 0.0 else 0.0,
        "same_notional_imbalance_5s": (same_notional - opp_notional) / notional_denom
        if notional_denom > 0.0
        else 0.0,
    }


def build_panel(args: argparse.Namespace, repo_root: Path, run_specs: list[tuple[str, Path]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    days = date_range(args.from_date, args.to_date)
    ttls = parse_ttls(args.ttl_sec)
    exits = load_exit_candidates(run_specs, set(days))
    market_by_day = {day: DayMarket.load(repo_root, args.symbol, day) for day in days}
    rows: list[dict[str, Any]] = []
    for idx, exit_row in exits.iterrows():
        day = str(exit_row["date"])
        market = market_by_day[day]
        entry_side = str(exit_row["side"]).lower()
        direction = int(exit_row["direction"])
        entry_ts_us = int(exit_row["entry_ts_us"])
        exit_ts_us = int(exit_row["exit_ts_us"])
        entry_bid = float(exit_row["entry_bid"])
        entry_ask = float(exit_row["entry_ask"])
        quote = market.quote_at_or_before(exit_ts_us)
        exit_action, immediate_taker_price, maker_touch_price, queue_ahead_qty = maker_side_and_prices(entry_side, quote)
        immediate_taker_net = taker_net(entry_side, entry_bid, entry_ask, immediate_taker_price)
        maker_touch_net = taker_net(entry_side, entry_bid, entry_ask, maker_touch_price)
        spread_saving = maker_touch_net - immediate_taker_net
        h_bps, d_bps, l_bps = path_hd(
            market,
            entry_side=entry_side,
            entry_bid=entry_bid,
            entry_ask=entry_ask,
            entry_ts_us=entry_ts_us,
            exit_ts_us=exit_ts_us,
            immediate_taker_net_bps=immediate_taker_net,
        )
        recent = recent_features(
            market,
            entry_side=entry_side,
            direction=direction,
            exit_ts_us=exit_ts_us,
            current_mid=quote.mid_px,
        )
        depth_denom = quote.bid_qty + quote.ask_qty
        top_depth_imbalance = (quote.bid_qty - quote.ask_qty) / depth_denom if depth_denom > 0.0 else 0.0
        signed_depth_imbalance = float(direction) * top_depth_imbalance
        decision_frame = market.decision_frame_at_or_before(exit_ts_us)
        base = {
            "schema_id": "ccusdt_maker_exit_opportunity_v1",
            "runtime_safe": True,
            "date": day,
            "exit_profile_source": exit_row["exit_profile_source"],
            "source_run_id": exit_row["source_run_id"],
            "shadow_position_id": int(exit_row["shadow_position_id"]),
            "entry_seq": int(exit_row["entry_seq"]) if not pd.isna(exit_row["entry_seq"]) else None,
            "close_seq": int(exit_row["close_seq"]) if not pd.isna(exit_row["close_seq"]) else None,
            "entry_ts_us": entry_ts_us,
            "exit_ts_us": exit_ts_us,
            "held_us": int(exit_row["held_us"]) if not pd.isna(exit_row["held_us"]) else None,
            "exit_sec": float(exit_row["exit_sec"]) if not pd.isna(exit_row["exit_sec"]) else None,
            "exit_reason": exit_row.get("exit_reason"),
            "entry_side": entry_side,
            "exit_action": exit_action,
            "direction": direction,
            "cell": exit_row["cell"],
            "membership_set": exit_row["membership_set"],
            "actual_exposure": float(exit_row["actual_exposure"]),
            "requested_exposure": float(exit_row["requested_exposure"]),
            "capacity_source": exit_row.get("capacity_source"),
            "entry_bid": entry_bid,
            "entry_ask": entry_ask,
            "entry_mid": float(exit_row["entry_mid"]),
            "exit_quote_ts_us": quote.local_ts_us,
            "exit_bid": quote.bid_px,
            "exit_ask": quote.ask_px,
            "exit_mid": quote.mid_px,
            "exit_spread_bps": quote.spread_bps,
            "exit_bid_qty": quote.bid_qty,
            "exit_ask_qty": quote.ask_qty,
            "top_depth_imbalance": top_depth_imbalance,
            "signed_top_depth_imbalance": signed_depth_imbalance,
            "maker_queue_ahead_qty": queue_ahead_qty,
            "immediate_taker_price": immediate_taker_price,
            "maker_touch_price": maker_touch_price,
            "immediate_taker_net_bps": immediate_taker_net,
            "maker_touch_net_bps": maker_touch_net,
            "spread_saving_bps": spread_saving,
            "path_h_bps": h_bps,
            "path_d_bps": d_bps,
            "path_l_bps": l_bps,
            "decision_trade_window_count": optional_float(decision_frame.get("trade_window_count")),
            "decision_trade_flow_imbalance": optional_float(decision_frame.get("trade_flow_imbalance")),
            "decision_frames_since_mid_change": optional_float(decision_frame.get("frames_since_mid_change")),
            "decision_past_event_25_bps": optional_float(decision_frame.get("past_event_25_bps")),
        }
        base.update(recent)
        for ttl in ttls:
            ttl_us = int(round(ttl * US_PER_SEC))
            fallback_quote = market.quote_at_or_before(exit_ts_us + ttl_us)
            fallback_price = fallback_quote.bid_px if entry_side == "buy" else fallback_quote.ask_px
            fallback_net = taker_net(entry_side, entry_bid, entry_ask, fallback_price)
            unfilled_decay = immediate_taker_net - fallback_net
            probe = market.fill_probe(
                side=exit_action,
                post_price=maker_touch_price,
                queue_ahead_qty=queue_ahead_qty,
                start_us=exit_ts_us,
                ttl_us=ttl_us,
            )
            selection_ts = (
                probe.touch_fill_ts_us + int(round(args.selection_window_sec * US_PER_SEC))
                if probe.touch_fill_ts_us is not None
                else exit_ts_us + ttl_us
            )
            selection_quote = market.quote_at_or_before(selection_ts)
            selection_price = selection_quote.bid_px if entry_side == "buy" else selection_quote.ask_px
            selection_net = taker_net(entry_side, entry_bid, entry_ask, selection_price)
            selection_cost = selection_net - maker_touch_net if probe.touch_fill else 0.0
            touch_delta = spread_saving if probe.touch_fill else -unfilled_decay
            queue_delta = spread_saving if probe.queue_fill else -unfilled_decay
            row = dict(base)
            row.update(
                {
                    "ttl_sec": float(ttl),
                    "fallback_quote_ts_us": fallback_quote.local_ts_us,
                    "fallback_taker_price": fallback_price,
                    "fallback_taker_net_bps": fallback_net,
                    "unfilled_decay_bps": unfilled_decay,
                    "touch_fill": probe.touch_fill,
                    "touch_fill_ts_us": probe.touch_fill_ts_us,
                    "touch_fill_delay_us": probe.touch_fill_delay_us,
                    "touch_trade_qty": probe.touch_trade_qty,
                    "touch_trade_count": probe.touch_trade_count,
                    "queue_fill": probe.queue_fill,
                    "queue_fill_ts_us": probe.queue_fill_ts_us,
                    "queue_fill_delay_us": probe.queue_fill_delay_us,
                    "queue_consumed_qty": probe.queue_consumed_qty,
                    "queue_fill_ratio": probe.queue_fill_ratio,
                    "selection_window_sec": float(args.selection_window_sec),
                    "selection_quote_ts_us": selection_quote.local_ts_us,
                    "selection_taker_net_bps": selection_net,
                    "selection_cost_bps": selection_cost,
                    "selection_cost_positive_bps": max(selection_cost, 0.0),
                    "maker_first_touch_delta_vs_taker_bps": touch_delta,
                    "maker_first_queue_delta_vs_taker_bps": queue_delta,
                    "touch_spread_term_bps": spread_saving if probe.touch_fill else 0.0,
                    "touch_unfilled_decay_term_bps": 0.0 if probe.touch_fill else unfilled_decay,
                    "touch_selection_term_bps": selection_cost if probe.touch_fill else 0.0,
                    "touch_selection_adjusted_delta_bps": touch_delta - (selection_cost if probe.touch_fill else 0.0),
                    "queue_spread_term_bps": spread_saving if probe.queue_fill else 0.0,
                    "queue_unfilled_decay_term_bps": 0.0 if probe.queue_fill else unfilled_decay,
                    "queue_selection_term_bps": selection_cost if probe.queue_fill else 0.0,
                    "queue_selection_adjusted_delta_bps": queue_delta - (selection_cost if probe.queue_fill else 0.0),
                }
            )
            rows.append(row)
        if (idx + 1) % 250 == 0:
            print(f"maker exit diagnostic processed exits={idx + 1}", flush=True)
    panel = pd.DataFrame(rows)
    input_manifest = {
        "schema_id": "ccusdt_maker_exit_opportunity_input_manifest_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "run_specs": [{"profile": profile, "path": str(path), "exits": file_manifest(path / "exits.parquet")} for profile, path in run_specs],
        "market_files": {
            day: {
                "quote_frame_v1": file_manifest(quote_path(repo_root, args.symbol, day)),
                "trade_event_v1": file_manifest(trade_path(repo_root, args.symbol, day)),
                "decision_frame_v1": file_manifest(decision_frame_path(repo_root, args.symbol, day)),
            }
            for day in days
        },
        "ttl_sec": ttls,
        "selection_window_sec": args.selection_window_sec,
        "fill_models": ["touch_trade_proxy_v1", "queue_ahead_trade_proxy_v1"],
        "runtime_boundary": (
            "inputs are fast runtime-safe exits and canonical market truth; "
            "no date/scored/future-label/PnL path files are read as runtime input"
        ),
    }
    input_manifest["manifest_hash"] = stable_hash(input_manifest)
    return panel, input_manifest


def weighted_mean(df: pd.DataFrame, column: str) -> float:
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce")
    ok = values.notna()
    if not ok.any():
        return 0.0
    denom = float(weights[ok].sum())
    if denom <= 0.0:
        return float(values[ok].mean())
    return float((weights[ok] * values[ok]).sum() / denom)


def weighted_sum(df: pd.DataFrame, column: str) -> float:
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return float((weights * values).sum())


def summarize_group(df: pd.DataFrame, model: str) -> dict[str, Any]:
    fill_col = f"{model}_fill" if model == "touch" else "queue_fill"
    delta_col = (
        "maker_first_touch_delta_vs_taker_bps"
        if model == "touch"
        else "maker_first_queue_delta_vs_taker_bps"
    )
    adjusted_col = (
        "touch_selection_adjusted_delta_bps"
        if model == "touch"
        else "queue_selection_adjusted_delta_bps"
    )
    spread_term = "touch_spread_term_bps" if model == "touch" else "queue_spread_term_bps"
    decay_term = "touch_unfilled_decay_term_bps" if model == "touch" else "queue_unfilled_decay_term_bps"
    selection_term = "touch_selection_term_bps" if model == "touch" else "queue_selection_term_bps"
    exposure = float(pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum())
    day_values = []
    for _, day_group in df.groupby("date", sort=True):
        day_values.append(weighted_sum(day_group, delta_col))
    positive_days = sum(1 for value in day_values if value > 0.0)
    filled = df[df[fill_col].astype(bool)]
    unfilled = df[~df[fill_col].astype(bool)]
    return {
        "n": int(len(df)),
        "position_count": int(df["shadow_position_id"].nunique()),
        "exposure": exposure,
        "fill_rate": float(df[fill_col].astype(bool).mean()) if len(df) else 0.0,
        "weighted_fill_rate": weighted_mean(df, fill_col),
        "mean_fill_delay_ms": float(pd.to_numeric(filled[f"{model}_fill_delay_us"], errors="coerce").mean() / 1000.0)
        if len(filled) and f"{model}_fill_delay_us" in filled.columns
        else 0.0,
        "mean_spread_saving_bps": float(df["spread_saving_bps"].mean()) if len(df) else 0.0,
        "weighted_mean_spread_saving_bps": weighted_mean(df, "spread_saving_bps"),
        "weighted_mean_spread_term_bps": weighted_mean(df, spread_term),
        "weighted_mean_unfilled_decay_term_bps": weighted_mean(df, decay_term),
        "weighted_mean_selection_term_bps": weighted_mean(df, selection_term),
        "weighted_mean_selection_positive_bps_filled": weighted_mean(filled, "selection_cost_positive_bps") if len(filled) else 0.0,
        "weighted_mean_unfilled_decay_bps_unfilled": weighted_mean(unfilled, "unfilled_decay_bps") if len(unfilled) else 0.0,
        "weighted_mean_delta_vs_taker_bps": weighted_mean(df, delta_col),
        "weighted_sum_delta_vs_taker_bps": weighted_sum(df, delta_col),
        "weighted_mean_selection_adjusted_delta_bps": weighted_mean(df, adjusted_col),
        "weighted_sum_selection_adjusted_delta_bps": weighted_sum(df, adjusted_col),
        "median_delta_vs_taker_bps": float(pd.to_numeric(df[delta_col], errors="coerce").median()) if len(df) else 0.0,
        "positive_delta_rate": float((pd.to_numeric(df[delta_col], errors="coerce") > 0.0).mean()) if len(df) else 0.0,
        "day_count": int(len(day_values)),
        "positive_day_count": int(positive_days),
        "positive_day_frac": float(positive_days / len(day_values)) if day_values else 0.0,
        "min_day_delta_sum_bps": float(min(day_values)) if day_values else 0.0,
        "max_day_delta_sum_bps": float(max(day_values)) if day_values else 0.0,
    }


def grouped_summary(panel: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model in ["touch", "queue"]:
        for keys, group in panel.groupby(group_cols, sort=True):
            if not isinstance(keys, tuple):
                keys = (keys,)
            row = {"fill_model": f"{model}_trade_proxy_v1"}
            row.update({col: value for col, value in zip(group_cols, keys)})
            row.update(summarize_group(group, model))
            rows.append(row)
    return pd.DataFrame(rows)


def bin_series(series: pd.Series, bins: int = 5) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if values.nunique(dropna=True) <= 1:
        return pd.Series(["all"], index=series.index)
    try:
        labels = pd.qcut(values.rank(method="first"), bins, labels=False)
        return pd.Series([f"q{int(label) + 1}" for label in labels], index=series.index)
    except ValueError:
        return pd.Series(["all"], index=series.index)


def factor_summary(panel: pd.DataFrame, min_count: int) -> pd.DataFrame:
    factors = [
        "path_h_bps",
        "path_d_bps",
        "exit_spread_bps",
        "maker_queue_ahead_qty",
        "signed_top_depth_imbalance",
        "same_flow_imbalance_5s",
        "same_minus_opposite_qty_5s",
        "recent_mid_alpha_5s_bps",
        "decision_frames_since_mid_change",
    ]
    rows: list[dict[str, Any]] = []
    for (profile, ttl), ttl_group in panel.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        for factor in factors:
            if factor not in ttl_group.columns:
                continue
            work = ttl_group.copy()
            work["factor_bin"] = bin_series(work[factor])
            for bin_name, group in work.groupby("factor_bin", sort=True):
                if len(group) < min_count:
                    continue
                numeric = pd.to_numeric(group[factor], errors="coerce")
                for model in ["touch", "queue"]:
                    row = {
                        "exit_profile_source": profile,
                        "ttl_sec": float(ttl),
                        "factor": factor,
                        "factor_bin": str(bin_name),
                        "factor_min": float(numeric.min()) if numeric.notna().any() else None,
                        "factor_max": float(numeric.max()) if numeric.notna().any() else None,
                        "fill_model": f"{model}_trade_proxy_v1",
                    }
                    row.update(summarize_group(group, model))
                    rows.append(row)
    return pd.DataFrame(rows)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    use_cols = [col for col in columns if col in df.columns]
    view = df.loc[:, use_cols].head(max_rows)
    lines = ["| " + " | ".join(use_cols) + " |", "| " + " | ".join(["---"] * len(use_cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for col in use_cols:
            value = row[col]
            if isinstance(value, float):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(
    path: Path,
    *,
    summary: dict[str, Any],
    ttl_summary: pd.DataFrame,
    by_day: pd.DataFrame,
    by_cell: pd.DataFrame,
    factor_rows: pd.DataFrame,
) -> None:
    ttl_view = ttl_summary.sort_values(["exit_profile_source", "ttl_sec", "fill_model"])
    day_view = by_day.sort_values(["exit_profile_source", "ttl_sec", "fill_model", "date"])
    cell_view = by_cell.sort_values(
        ["exit_profile_source", "ttl_sec", "fill_model", "weighted_sum_delta_vs_taker_bps"],
        ascending=[True, True, True, False],
    )
    factor_view = factor_rows.sort_values(
        ["exit_profile_source", "ttl_sec", "fill_model", "weighted_sum_selection_adjusted_delta_bps"],
        ascending=[True, True, True, False],
    )
    queue_ttl = ttl_summary[ttl_summary["fill_model"] == "queue_trade_proxy_v1"].copy()
    queue_ttl = queue_ttl.sort_values("weighted_sum_delta_vs_taker_bps", ascending=False)
    best_global = queue_ttl.iloc[0].to_dict() if not queue_ttl.empty else {}
    positive_queue = queue_ttl[queue_ttl["weighted_sum_delta_vs_taker_bps"] > 0.0]
    queue_factor = factor_rows[factor_rows["fill_model"] == "queue_trade_proxy_v1"].copy()
    queue_factor = queue_factor.sort_values("weighted_sum_selection_adjusted_delta_bps", ascending=False)
    best_factor = queue_factor.iloc[0].to_dict() if not queue_factor.empty else {}
    lines = [
        "# CCUSDT q70 idle01_g1 maker-first exit opportunity",
        "",
        "This is an offline execution diagnostic for existing-position exits only. It does not study maker entry, and it does not read `date/`, scored entries, future labels, MFE/MAE, or root research scripts as runtime inputs.",
        "",
        "## Model",
        "",
        "At an exit decision time \\(t\\), compare immediate taker exit \\(Y^T_t\\) with a passive touch exit \\(Y^M_t\\). For a long position, taker sells bid and maker posts sell at ask; for a short position, taker buys ask and maker posts buy at bid.",
        "",
        "\\[",
        "\\Delta^{spread}_t = Y^M_t - Y^T_t.",
        "\\]",
        "",
        "For TTL \\(\\tau\\), the maker-first controller has two risks: no fill followed by fallback decay, and fill-side adverse selection. The diagnostic estimates the signed decomposition",
        "",
        "\\[",
        "\\mathbb E[\\Delta_t(\\tau)] \\approx p_t(\\tau)\\Delta^{spread}_t - (1-p_t(\\tau))L^{unfilled}_t(\\tau) - A^{selection}_t(\\tau).",
        "\\]",
        "",
        "`touch_trade_proxy_v1` fills when any opposite aggressor trade reaches the posted touch. `queue_ahead_trade_proxy_v1` additionally requires cumulative opposite trade quantity to consume the displayed top-of-book queue ahead. The second proxy is deliberately harsher.",
        "",
        "## Scope",
        "",
        f"- Symbol: `{summary['symbol']}`",
        f"- Dates: `{summary['from_date']}..{summary['to_date']}`",
        f"- Candidate profiles: `{', '.join(summary['exit_profile_sources'])}`",
        f"- Candidate exits with actual exposure: `{summary['actual_exit_candidates']}`",
        f"- Panel rows: `{summary['panel_rows']}`",
        f"- Output directory: `{summary['out_dir']}`",
        "",
        "## Readout",
        "",
        (
            f"- Global queue-ahead maker-first is not promoted: best whole-profile row is "
            f"`{best_global.get('exit_profile_source', '')} / TTL={fmt(best_global.get('ttl_sec'), 1)}s`, "
            f"weighted delta `{fmt(best_global.get('weighted_sum_delta_vs_taker_bps'))}` bp-units, "
            f"mean `{fmt(best_global.get('weighted_mean_delta_vs_taker_bps'))}` bps, "
            f"positive-day fraction `{fmt(best_global.get('positive_day_frac'))}`."
            if best_global
            else "- Global queue-ahead maker-first has no rows."
        ),
        (
            f"- Positive whole-profile queue rows: `{len(positive_queue)}` out of `{len(queue_ttl)}`. "
            "The full-sample controller should therefore remain direct taker unless a narrow runtime-safe gate is used."
        ),
        (
            f"- Strongest queue-aware factor bucket is "
            f"`{best_factor.get('exit_profile_source', '')} / TTL={fmt(best_factor.get('ttl_sec'), 1)}s / "
            f"{best_factor.get('factor', '')}={best_factor.get('factor_bin', '')}`, "
            f"n `{best_factor.get('n', '')}`, exposure `{fmt(best_factor.get('exposure'))}`, "
            f"fill rate `{fmt(best_factor.get('fill_rate'))}`, "
            f"delta sum `{fmt(best_factor.get('weighted_sum_delta_vs_taker_bps'))}`, "
            f"selection-adjusted sum `{fmt(best_factor.get('weighted_sum_selection_adjusted_delta_bps'))}`, "
            f"positive-day fraction `{fmt(best_factor.get('positive_day_frac'))}`."
            if best_factor
            else "- No queue-aware factor bucket was available."
        ),
        "- This is a diagnostic bucket read, not a live rule: factor thresholds must be re-expressed as prior-date/runtime-safe gates before `maker_first_exit_v1` can be enabled.",
        "",
        "## TTL Summary",
        "",
    ]
    lines.extend(
        markdown_table(
            ttl_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "fill_model",
                "n",
                "exposure",
                "fill_rate",
                "weighted_mean_spread_term_bps",
                "weighted_mean_unfilled_decay_term_bps",
                "weighted_mean_selection_term_bps",
                "weighted_mean_delta_vs_taker_bps",
                "weighted_sum_delta_vs_taker_bps",
                "positive_day_frac",
                "min_day_delta_sum_bps",
            ],
            max_rows=40,
        )
    )
    lines.extend(["", "## Day Stability", ""])
    lines.extend(
        markdown_table(
            day_view,
            [
                "exit_profile_source",
                "date",
                "ttl_sec",
                "fill_model",
                "n",
                "exposure",
                "fill_rate",
                "weighted_sum_delta_vs_taker_bps",
                "weighted_mean_delta_vs_taker_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Cell Readout", ""])
    lines.extend(
        markdown_table(
            cell_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "fill_model",
                "cell",
                "n",
                "exposure",
                "fill_rate",
                "weighted_sum_delta_vs_taker_bps",
                "weighted_mean_selection_adjusted_delta_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Strongest Factor Buckets", ""])
    lines.extend(
        markdown_table(
            factor_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "fill_model",
                "factor",
                "factor_bin",
                "n",
                "exposure",
                "fill_rate",
                "weighted_mean_delta_vs_taker_bps",
                "weighted_mean_selection_adjusted_delta_bps",
                "positive_day_frac",
            ],
            max_rows=50,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation Rule",
            "",
            "A maker-first exit is not promoted by spread saving alone. A bucket is interesting only when it has enough sample, stable positive days, and positive selection-adjusted value under the queue-ahead proxy. If only the touch proxy works while the queue proxy fails, the result is a fill-optimism warning, not a strategy.",
            "",
            "The next implementation step is `maker_first_exit_v1` only if these tables show a simple runtime-safe gate where queue-aware expected value remains positive after decay and selection.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    run_specs = parse_run_specs(args, repo_root)
    panel, input_manifest = build_panel(args, repo_root, run_specs)
    ttl_summary = grouped_summary(panel, ["exit_profile_source", "ttl_sec"])
    by_day = grouped_summary(panel, ["exit_profile_source", "date", "ttl_sec"])
    by_cell = grouped_summary(panel, ["exit_profile_source", "cell", "ttl_sec"])
    factor_rows = factor_summary(panel, args.min_bin_count)
    summary = {
        "schema_id": "ccusdt_maker_exit_opportunity_summary_v1",
        "ok": True,
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "exit_profile_sources": [profile for profile, _ in run_specs],
        "actual_exit_candidates": int(panel[["exit_profile_source", "shadow_position_id"]].drop_duplicates().shape[0]),
        "panel_rows": int(len(panel)),
        "ttl_sec": parse_ttls(args.ttl_sec),
        "selection_window_sec": args.selection_window_sec,
        "out_dir": str(out_dir),
        "input_manifest_hash": input_manifest["manifest_hash"],
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        "outputs": {
            "panel_parquet": str(out_dir / "maker_exit_opportunity_panel.parquet"),
            "panel_csv": str(out_dir / "maker_exit_opportunity_panel.csv"),
            "ttl_summary_csv": str(out_dir / "maker_exit_ttl_summary.csv"),
            "by_day_csv": str(out_dir / "maker_exit_by_day.csv"),
            "by_cell_csv": str(out_dir / "maker_exit_by_cell.csv"),
            "factor_summary_csv": str(out_dir / "maker_exit_factor_summary.csv"),
            "summary_json": str(out_dir / "summary.json"),
            "input_manifest_json": str(out_dir / "input_manifest.json"),
            "report_md": str(report_path),
        },
    }
    write_parquet(out_dir / "maker_exit_opportunity_panel.parquet", panel)
    write_csv(out_dir / "maker_exit_opportunity_panel.csv", panel)
    write_csv(out_dir / "maker_exit_ttl_summary.csv", ttl_summary)
    write_csv(out_dir / "maker_exit_by_day.csv", by_day)
    write_csv(out_dir / "maker_exit_by_cell.csv", by_cell)
    write_csv(out_dir / "maker_exit_factor_summary.csv", factor_rows)
    (out_dir / "input_manifest.json").write_text(json.dumps(input_manifest, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(
        report_path,
        summary=summary,
        ttl_summary=ttl_summary,
        by_day=by_day,
        by_cell=by_cell,
        factor_rows=factor_rows,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
