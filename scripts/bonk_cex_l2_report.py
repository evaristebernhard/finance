#!/usr/bin/env python3
"""
Build a BONK Bullish L2 state panel, path labels, diagnostics, and report.

The script consumes raw Tardis downloadable CSV.gz files produced by
bonk_bullish_l2_download.py. It keeps the first research version conservative:
prices are stored in Bullish's native per-1M BONK quote unit and, for 1M symbols,
also as price_per_token = price / 1_000_000. Trade side is treated as
exchange-reported side until the Bullish convention is independently confirmed.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_DATA_ROOT = Path("data/bonk/v1")
DEFAULT_DATE_DIR = Path("date")
DEFAULT_DOC_DIR = Path("docs/markets/bonk")
DEFAULT_RUN_TAG = "20260513_bullish_l2_v1"
DEFAULT_SYMBOLS = (
    "BONK1MUSDC,BONK1MUSDT,"
    "BTCUSDC,ETHUSDC,SOLUSDC,"
    "DOGEUSDC,PENGUUSDC,"
    "PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,"
    "SUIUSDC,APTUSDC,ARBUSDC,OPUSDC"
)
DEFAULT_LABEL_SYMBOLS = "BONK1MUSDC,BONK1MUSDT"
DEFAULT_HORIZONS = "1,4,12"
DEFAULT_BARRIERS = "50,100,200,300"
DEFAULT_CHUNKSIZE = 200_000
EXCHANGE = "bullish"
RAW_DATA_TYPES = ("book_snapshot_25", "book_ticker", "trades")
FACTOR_COLS = [
    "spread_bps_median",
    "spread_bps_last",
    "microprice_offset_bps_mean",
    "wobi5_mean",
    "wobi25_mean",
    "depth_imbalance_5_mean",
    "depth_imbalance_25_mean",
    "trade_flow_imbalance",
    "reported_buy_share",
    "trade_notional_quote_sum",
    "book_ticker_count",
    "snapshot_count",
    "trade_count",
]


@dataclass
class OutputPaths:
    l2_state_parquet: Path
    covariance_parquet: Path
    labels_parquet: Path
    quality_csv: Path
    summary_csv: Path
    factor_tests_csv: Path
    stability_csv: Path
    completion_json: Path
    report_md: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build BONK Bullish CEX L2 state, path labels, factor diagnostics, and report."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--date-dir", type=Path, default=DEFAULT_DATE_DIR)
    parser.add_argument("--doc-dir", type=Path, default=DEFAULT_DOC_DIR)
    parser.add_argument("--run-tag", default=DEFAULT_RUN_TAG)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument(
        "--label-symbols",
        default=DEFAULT_LABEL_SYMBOLS,
        help="Optional comma-separated symbols to label/test. Defaults to BONK1MUSDC,BONK1MUSDT.",
    )
    parser.add_argument("--horizons-hours", default=DEFAULT_HORIZONS)
    parser.add_argument("--barriers-bps", default=DEFAULT_BARRIERS)
    parser.add_argument("--chunksize", type=int, default=DEFAULT_CHUNKSIZE)
    parser.add_argument("--abnormal-spread-bps", type=float, default=1_000.0)
    parser.add_argument("--max-forward-fill-minutes", type=int, default=5)
    return parser.parse_args()


def parse_list(raw: str) -> list[str]:
    values = [value.strip().upper() for value in raw.split(",") if value.strip()]
    return list(dict.fromkeys(values))


def parse_int_list(raw: str) -> list[int]:
    values = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not values:
        raise ValueError("empty integer list")
    return list(dict.fromkeys(values))


def output_paths(data_root: Path, date_dir: Path, doc_dir: Path, run_tag: str) -> OutputPaths:
    return OutputPaths(
        l2_state_parquet=data_root
        / "derived"
        / "bonk_cex_l2_state"
        / f"bonk_cex_l2_state_{run_tag}.parquet",
        covariance_parquet=data_root
        / "derived"
        / "bonk_cex_covariance_state"
        / f"bonk_cex_covariance_state_{run_tag}.parquet",
        labels_parquet=data_root
        / "derived"
        / "bonk_path_labels"
        / f"bonk_path_labels_{run_tag}.parquet",
        quality_csv=date_dir / f"bonk_v1_cex_l2_quality_{run_tag}.csv",
        summary_csv=date_dir / f"bonk_v1_cex_l2_summary_{run_tag}.csv",
        factor_tests_csv=date_dir / f"bonk_v1_cex_l2_factor_tests_{run_tag}.csv",
        stability_csv=date_dir / f"bonk_v1_cex_l2_stability_{run_tag}.csv",
        completion_json=date_dir / f"bonk_v1_cex_l2_completion_{run_tag}.json",
        report_md=doc_dir / "v1-cex-l2-report.md",
    )


def raw_dir(data_root: Path, data_type: str) -> Path:
    return data_root / "external" / f"{EXCHANGE}_{data_type}"


def raw_files(data_root: Path, data_type: str, symbols: list[str]) -> list[Path]:
    root = raw_dir(data_root, data_type)
    paths: list[Path] = []
    for symbol in symbols:
        paths.extend(sorted((root / f"symbol={symbol}").glob("dt=*/*.csv.gz")))
    return paths


def source_date_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("dt="):
            return part.split("=", 1)[1]
    return ""


def symbol_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("symbol="):
            return part.split("=", 1)[1]
    return path.stem.replace(".csv", "").upper()


def base_asset(symbol: str) -> str:
    value = symbol.upper()
    for quote in ("USDC", "USDT", "USD"):
        if value.endswith(quote):
            value = value[: -len(quote)]
            break
    if value.endswith("1M"):
        value = value[:-2]
    return value


def price_scale(symbol: str) -> float:
    stripped = symbol.upper()
    for quote in ("USDC", "USDT", "USD"):
        if stripped.endswith(quote):
            stripped = stripped[: -len(quote)]
            break
    return 1_000_000.0 if stripped.endswith("1M") else 1.0


def utc_from_us(timestamp_us: pd.Series) -> pd.Series:
    return pd.to_datetime(timestamp_us, unit="us", utc=True, errors="coerce")


def read_csv_chunks(path: Path, chunksize: int) -> Iterable[pd.DataFrame]:
    try:
        reader = pd.read_csv(path, compression="gzip", chunksize=chunksize, low_memory=False)
    except pd.errors.EmptyDataError:
        return
    for chunk in reader:
        yield chunk


def as_numeric(frame: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(frame[col], errors="coerce") if col in frame.columns else pd.Series(np.nan, index=frame.index)


def top_spread(frame: pd.DataFrame, ask_col: str, bid_col: str) -> pd.Series:
    ask = as_numeric(frame, ask_col)
    bid = as_numeric(frame, bid_col)
    mid = (ask + bid) / 2.0
    return (ask - bid) / mid.replace(0.0, np.nan) * 10_000.0


def inspect_raw_file(path: Path, data_type: str, chunksize: int, abnormal_spread_bps: float) -> dict[str, object]:
    symbol = symbol_from_path(path)
    row: dict[str, object] = {
        "data_type": data_type,
        "symbol": symbol,
        "source_date": source_date_from_path(path),
        "path": path.as_posix(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "status": "ok",
        "rows": 0,
        "timestamp_min_us": np.nan,
        "timestamp_max_us": np.nan,
        "timestamp_monotonic_violations": 0,
        "duplicate_rows_in_chunks": 0,
        "empty_price_rows": 0,
        "negative_amount_rows": 0,
        "abnormal_spread_rows": 0,
        "header": "",
        "error": "",
    }
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
        row["header"] = "|".join(header)
    except Exception as exc:  # noqa: BLE001
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row

    prev_ts: float | None = None
    price_re = re.compile(r"(price|bid|ask)", re.IGNORECASE)
    amount_re = re.compile(r"(amount|qty|quantity|size)", re.IGNORECASE)
    try:
        for chunk in read_csv_chunks(path, chunksize):
            row["rows"] = int(row["rows"]) + len(chunk)
            if chunk.empty:
                continue
            ts = as_numeric(chunk, "timestamp")
            clean_ts = ts.dropna()
            if not clean_ts.empty:
                row["timestamp_min_us"] = np.nanmin([row["timestamp_min_us"], clean_ts.min()])
                row["timestamp_max_us"] = np.nanmax([row["timestamp_max_us"], clean_ts.max()])
                diffs = clean_ts.diff()
                row["timestamp_monotonic_violations"] = int(row["timestamp_monotonic_violations"]) + int((diffs < 0).sum())
                if prev_ts is not None and float(clean_ts.iloc[0]) < prev_ts:
                    row["timestamp_monotonic_violations"] = int(row["timestamp_monotonic_violations"]) + 1
                prev_ts = float(clean_ts.iloc[-1])
            row["duplicate_rows_in_chunks"] = int(row["duplicate_rows_in_chunks"]) + int(chunk.duplicated().sum())

            price_cols = [col for col in chunk.columns if price_re.search(col)]
            if price_cols:
                prices = chunk[price_cols].apply(pd.to_numeric, errors="coerce")
                row["empty_price_rows"] = int(row["empty_price_rows"]) + int((prices.isna() | (prices <= 0.0)).any(axis=1).sum())
            amount_cols = [col for col in chunk.columns if amount_re.search(col)]
            if amount_cols:
                amounts = chunk[amount_cols].apply(pd.to_numeric, errors="coerce")
                row["negative_amount_rows"] = int(row["negative_amount_rows"]) + int((amounts < 0.0).any(axis=1).sum())
            if data_type == "book_ticker":
                spread = top_spread(chunk, "ask_price", "bid_price")
                row["abnormal_spread_rows"] = int(row["abnormal_spread_rows"]) + int(
                    ((spread < 0.0) | (spread > abnormal_spread_bps)).fillna(False).sum()
                )
            elif data_type == "book_snapshot_25":
                spread = top_spread(chunk, "asks[0].price", "bids[0].price")
                row["abnormal_spread_rows"] = int(row["abnormal_spread_rows"]) + int(
                    ((spread < 0.0) | (spread > abnormal_spread_bps)).fillna(False).sum()
                )
    except Exception as exc:  # noqa: BLE001
        row["status"] = "error"
        row["error"] = f"{type(exc).__name__}: {exc}"
    if int(row["rows"]) == 0 and row["status"] == "ok":
        row["status"] = "empty"
    return row


def inspect_raw_files(data_root: Path, symbols: list[str], chunksize: int, abnormal_spread_bps: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for data_type in RAW_DATA_TYPES:
        for path in raw_files(data_root, data_type, symbols):
            rows.append(inspect_raw_file(path, data_type, chunksize, abnormal_spread_bps))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["data_type", "symbol", "source_date"]).reset_index(drop=True)


def add_time_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["timestamp_us"] = as_numeric(frame, "timestamp").astype("Int64")
    frame["ts"] = utc_from_us(frame["timestamp_us"].astype("float64"))
    frame = frame[frame["ts"].notna()].copy()
    frame["minute"] = frame["ts"].dt.floor("min")
    return frame


def aggregate_book_ticker_file(path: Path, chunksize: int) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    symbol = symbol_from_path(path)
    scale = price_scale(symbol)
    for chunk in read_csv_chunks(path, chunksize):
        if chunk.empty:
            continue
        frame = add_time_columns(chunk)
        if frame.empty:
            continue
        frame["symbol"] = frame.get("symbol", symbol)
        frame["asset"] = base_asset(symbol)
        frame["bid_price"] = as_numeric(frame, "bid_price")
        frame["ask_price"] = as_numeric(frame, "ask_price")
        frame["bid_amount"] = as_numeric(frame, "bid_amount")
        frame["ask_amount"] = as_numeric(frame, "ask_amount")
        frame["mid_price_per_unit"] = (frame["bid_price"] + frame["ask_price"]) / 2.0
        frame["mid_price_per_token"] = frame["mid_price_per_unit"] / scale
        frame["spread_bps"] = (frame["ask_price"] - frame["bid_price"]) / frame["mid_price_per_unit"].replace(0.0, np.nan) * 10_000.0
        frame["top_depth_bid_notional"] = frame["bid_price"] * frame["bid_amount"]
        frame["top_depth_ask_notional"] = frame["ask_price"] * frame["ask_amount"]
        frame["microprice"] = (
            frame["ask_price"] * frame["bid_amount"] + frame["bid_price"] * frame["ask_amount"]
        ) / (frame["bid_amount"] + frame["ask_amount"]).replace(0.0, np.nan)
        frame["microprice_offset_bps"] = (
            frame["microprice"] / frame["mid_price_per_unit"].replace(0.0, np.nan) - 1.0
        ) * 10_000.0
        grouped = frame.groupby(["symbol", "asset", "minute"], sort=True)
        out = grouped.agg(
            book_ticker_count=("timestamp_us", "count"),
            bid_price_last=("bid_price", "last"),
            ask_price_last=("ask_price", "last"),
            mid_price_per_unit_open=("mid_price_per_unit", "first"),
            mid_price_per_unit_high=("mid_price_per_unit", "max"),
            mid_price_per_unit_low=("mid_price_per_unit", "min"),
            mid_price_per_unit_close=("mid_price_per_unit", "last"),
            mid_price_per_token_close=("mid_price_per_token", "last"),
            spread_bps_median=("spread_bps", "median"),
            spread_bps_last=("spread_bps", "last"),
            top_depth_bid_notional_median=("top_depth_bid_notional", "median"),
            top_depth_ask_notional_median=("top_depth_ask_notional", "median"),
            microprice_offset_bps_mean=("microprice_offset_bps", "mean"),
        ).reset_index()
        pieces.append(out)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def aggregate_snapshot_file(path: Path, chunksize: int) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    symbol = symbol_from_path(path)
    for chunk in read_csv_chunks(path, chunksize):
        if chunk.empty:
            continue
        frame = add_time_columns(chunk)
        if frame.empty:
            continue
        frame["symbol"] = frame.get("symbol", symbol)
        frame["asset"] = base_asset(symbol)
        bid_notional_5 = pd.Series(0.0, index=frame.index)
        ask_notional_5 = pd.Series(0.0, index=frame.index)
        bid_notional_25 = pd.Series(0.0, index=frame.index)
        ask_notional_25 = pd.Series(0.0, index=frame.index)
        for level in range(25):
            bid_price = as_numeric(frame, f"bids[{level}].price")
            bid_amount = as_numeric(frame, f"bids[{level}].amount")
            ask_price = as_numeric(frame, f"asks[{level}].price")
            ask_amount = as_numeric(frame, f"asks[{level}].amount")
            bid_notional = (bid_price * bid_amount).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            ask_notional = (ask_price * ask_amount).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            bid_notional_25 += bid_notional
            ask_notional_25 += ask_notional
            if level < 5:
                bid_notional_5 += bid_notional
                ask_notional_5 += ask_notional
        top_bid = as_numeric(frame, "bids[0].price")
        top_ask = as_numeric(frame, "asks[0].price")
        top_bid_amount = as_numeric(frame, "bids[0].amount")
        top_ask_amount = as_numeric(frame, "asks[0].amount")
        mid = (top_bid + top_ask) / 2.0
        frame["snapshot_spread_bps"] = (top_ask - top_bid) / mid.replace(0.0, np.nan) * 10_000.0
        frame["wobi5"] = (bid_notional_5 - ask_notional_5) / (bid_notional_5 + ask_notional_5).replace(0.0, np.nan)
        frame["wobi25"] = (bid_notional_25 - ask_notional_25) / (bid_notional_25 + ask_notional_25).replace(0.0, np.nan)
        frame["depth_imbalance_5"] = frame["wobi5"]
        frame["depth_imbalance_25"] = frame["wobi25"]
        frame["depth_bid_notional_5"] = bid_notional_5
        frame["depth_ask_notional_5"] = ask_notional_5
        frame["depth_bid_notional_25"] = bid_notional_25
        frame["depth_ask_notional_25"] = ask_notional_25
        frame["snapshot_microprice"] = (
            top_ask * top_bid_amount + top_bid * top_ask_amount
        ) / (top_bid_amount + top_ask_amount).replace(0.0, np.nan)
        frame["snapshot_microprice_offset_bps"] = (
            frame["snapshot_microprice"] / mid.replace(0.0, np.nan) - 1.0
        ) * 10_000.0
        grouped = frame.groupby(["symbol", "asset", "minute"], sort=True)
        out = grouped.agg(
            snapshot_count=("timestamp_us", "count"),
            snapshot_spread_bps_median=("snapshot_spread_bps", "median"),
            wobi5_mean=("wobi5", "mean"),
            wobi25_mean=("wobi25", "mean"),
            depth_imbalance_5_mean=("depth_imbalance_5", "mean"),
            depth_imbalance_25_mean=("depth_imbalance_25", "mean"),
            depth_bid_notional_5_median=("depth_bid_notional_5", "median"),
            depth_ask_notional_5_median=("depth_ask_notional_5", "median"),
            depth_bid_notional_25_median=("depth_bid_notional_25", "median"),
            depth_ask_notional_25_median=("depth_ask_notional_25", "median"),
            snapshot_microprice_offset_bps_mean=("snapshot_microprice_offset_bps", "mean"),
        ).reset_index()
        pieces.append(out)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def aggregate_trades_file(path: Path, chunksize: int) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    symbol = symbol_from_path(path)
    scale = price_scale(symbol)
    for chunk in read_csv_chunks(path, chunksize):
        if chunk.empty:
            continue
        frame = add_time_columns(chunk)
        if frame.empty:
            continue
        frame["symbol"] = frame.get("symbol", symbol)
        frame["asset"] = base_asset(symbol)
        frame["price"] = as_numeric(frame, "price")
        frame["amount"] = as_numeric(frame, "amount")
        frame["trade_notional_quote"] = frame["price"] * frame["amount"]
        frame["price_per_token"] = frame["price"] / scale
        side = frame.get("side", pd.Series("", index=frame.index)).astype(str).str.lower()
        frame["reported_buy_amount"] = np.where(side == "buy", frame["amount"], 0.0)
        frame["reported_sell_amount"] = np.where(side == "sell", frame["amount"], 0.0)
        frame["reported_unknown_amount"] = np.where(~side.isin(["buy", "sell"]), frame["amount"], 0.0)
        grouped = frame.groupby(["symbol", "asset", "minute"], sort=True)
        out = grouped.agg(
            trade_count=("timestamp_us", "count"),
            trade_amount_sum=("amount", "sum"),
            trade_notional_quote_sum=("trade_notional_quote", "sum"),
            reported_buy_amount=("reported_buy_amount", "sum"),
            reported_sell_amount=("reported_sell_amount", "sum"),
            reported_unknown_amount=("reported_unknown_amount", "sum"),
            trade_price_per_unit_vwap=("price", lambda x: np.nan),
            trade_price_per_token_last=("price_per_token", "last"),
        ).reset_index()
        amount_sum = grouped["amount"].sum().reset_index(name="_amount_sum")
        notional_sum = grouped["trade_notional_quote"].sum().reset_index(name="_notional_sum")
        vwap = amount_sum.merge(notional_sum, on=["symbol", "asset", "minute"], how="left")
        vwap["trade_price_per_unit_vwap"] = vwap["_notional_sum"] / vwap["_amount_sum"].replace(0.0, np.nan)
        out = out.drop(columns=["trade_price_per_unit_vwap"]).merge(
            vwap[["symbol", "asset", "minute", "trade_price_per_unit_vwap"]],
            on=["symbol", "asset", "minute"],
            how="left",
        )
        pieces.append(out)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def collapse_duplicate_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    numeric_cols = [col for col in frame.columns if col not in {"symbol", "asset", "minute"}]
    agg: dict[str, str] = {}
    for col in numeric_cols:
        if col.endswith("_count") or col.endswith("_sum") or col in {
            "trade_count",
            "trade_amount_sum",
            "trade_notional_quote_sum",
            "reported_buy_amount",
            "reported_sell_amount",
            "reported_unknown_amount",
            "snapshot_count",
            "book_ticker_count",
        }:
            agg[col] = "sum"
        elif col.endswith("_open"):
            agg[col] = "first"
        elif col.endswith("_high"):
            agg[col] = "max"
        elif col.endswith("_low"):
            agg[col] = "min"
        elif col.endswith("_close") or col.endswith("_last"):
            agg[col] = "last"
        else:
            agg[col] = "mean"
    return frame.groupby(["symbol", "asset", "minute"], sort=True).agg(agg).reset_index()


def aggregate_all(data_root: Path, symbols: list[str], chunksize: int) -> pd.DataFrame:
    ticker_frames = [aggregate_book_ticker_file(path, chunksize) for path in raw_files(data_root, "book_ticker", symbols)]
    snapshot_frames = [aggregate_snapshot_file(path, chunksize) for path in raw_files(data_root, "book_snapshot_25", symbols)]
    trade_frames = [aggregate_trades_file(path, chunksize) for path in raw_files(data_root, "trades", symbols)]

    ticker = collapse_duplicate_minutes(pd.concat([x for x in ticker_frames if not x.empty], ignore_index=True)) if any(not x.empty for x in ticker_frames) else pd.DataFrame()
    snapshot = collapse_duplicate_minutes(pd.concat([x for x in snapshot_frames if not x.empty], ignore_index=True)) if any(not x.empty for x in snapshot_frames) else pd.DataFrame()
    trades = collapse_duplicate_minutes(pd.concat([x for x in trade_frames if not x.empty], ignore_index=True)) if any(not x.empty for x in trade_frames) else pd.DataFrame()

    if ticker.empty and snapshot.empty and trades.empty:
        raise FileNotFoundError("no usable Bullish raw files found")
    state = ticker
    for extra in (snapshot, trades):
        if state.empty:
            state = extra
        elif not extra.empty:
            state = state.merge(extra, on=["symbol", "asset", "minute"], how="outer")
    state = state.sort_values(["symbol", "minute"]).reset_index(drop=True)
    state["timestamp_utc"] = state["minute"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    state["timestamp_us"] = (state["minute"].astype("int64") // 1_000).astype("int64")
    state["price_unit"] = np.where(state["symbol"].map(price_scale) == 1_000_000.0, "per_1m_base", "per_base")
    if "mid_price_per_unit_close" not in state.columns and "trade_price_per_unit_vwap" in state.columns:
        state["mid_price_per_unit_close"] = state["trade_price_per_unit_vwap"]
        state["mid_price_per_token_close"] = state["mid_price_per_unit_close"] / state["symbol"].map(price_scale)
    if "spread_bps_median" not in state.columns and "snapshot_spread_bps_median" in state.columns:
        state["spread_bps_median"] = state["snapshot_spread_bps_median"]
    if "microprice_offset_bps_mean" in state.columns and "snapshot_microprice_offset_bps_mean" in state.columns:
        state["microprice_offset_bps_mean"] = state["microprice_offset_bps_mean"].fillna(
            state["snapshot_microprice_offset_bps_mean"]
        )
    elif "snapshot_microprice_offset_bps_mean" in state.columns:
        state["microprice_offset_bps_mean"] = state["snapshot_microprice_offset_bps_mean"]
    for col in [
        "book_ticker_count",
        "snapshot_count",
        "trade_count",
        "trade_amount_sum",
        "trade_notional_quote_sum",
        "reported_buy_amount",
        "reported_sell_amount",
        "reported_unknown_amount",
    ]:
        if col in state.columns:
            state[col] = state[col].fillna(0.0)
    if {"reported_buy_amount", "reported_sell_amount"}.issubset(state.columns):
        denom = state["reported_buy_amount"] + state["reported_sell_amount"]
        state["trade_flow_imbalance"] = (state["reported_buy_amount"] - state["reported_sell_amount"]) / denom.replace(0.0, np.nan)
        state["reported_buy_share"] = state["reported_buy_amount"] / denom.replace(0.0, np.nan)
    state["run_tag"] = ""
    return state.replace([np.inf, -np.inf], np.nan)


def add_returns(state: pd.DataFrame) -> pd.DataFrame:
    state = state.sort_values(["symbol", "minute"]).copy()
    state["ret_1m_bps"] = np.nan
    for symbol, group in state.groupby("symbol", sort=False):
        price = pd.to_numeric(group["mid_price_per_token_close"], errors="coerce")
        state.loc[group.index, "ret_1m_bps"] = np.log(price / price.shift(1)) * 10_000.0
    return state


def build_covariance_state(state: pd.DataFrame) -> pd.DataFrame:
    pivot = state.pivot_table(index="minute", columns="symbol", values="mid_price_per_token_close", aggfunc="last")
    pivot = pivot.sort_index()
    returns = np.log(pivot / pivot.shift(1)).replace([np.inf, -np.inf], np.nan)
    rows: list[dict[str, object]] = []
    symbols = list(pivot.columns)
    for idx in range(len(returns)):
        ts = returns.index[idx]
        window = returns.iloc[max(0, idx - 59) : idx + 1].dropna(how="all")
        valid_symbols = [col for col in symbols if window[col].notna().sum() >= 20]
        if len(valid_symbols) < 2:
            rows.append(
                {
                    "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "timestamp_us": int(ts.value // 1_000),
                    "n_symbols": len(valid_symbols),
                    "symbols": ",".join(valid_symbols),
                    "avg_corr_60m": np.nan,
                    "first_eigen_share_60m": np.nan,
                    "cross_symbol_abs_ret_mean_bps": np.nan,
                    "run_tag": "",
                }
            )
            continue
        sub = window[valid_symbols].dropna()
        if len(sub) < 20:
            avg_corr = np.nan
            eigen_share = np.nan
        else:
            corr = sub.corr()
            vals = corr.to_numpy()
            upper = vals[np.triu_indices_from(vals, k=1)]
            avg_corr = float(np.nanmean(upper)) if len(upper) else np.nan
            cov = sub.cov().to_numpy()
            eig = np.linalg.eigvalsh(cov)
            total = float(np.nansum(eig))
            eigen_share = float(np.nanmax(eig) / total) if total > 0.0 else np.nan
        rows.append(
            {
                "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timestamp_us": int(ts.value // 1_000),
                "n_symbols": len(valid_symbols),
                "symbols": ",".join(valid_symbols),
                "avg_corr_60m": avg_corr,
                "first_eigen_share_60m": eigen_share,
                "cross_symbol_abs_ret_mean_bps": float(window[valid_symbols].abs().mean(axis=1).mean() * 10_000.0),
                "run_tag": "",
            }
        )
    return pd.DataFrame(rows)


def first_hit(price0: float, future: np.ndarray, barrier_bps: float) -> tuple[str, float, float, float]:
    if not np.isfinite(price0) or price0 <= 0.0 or len(future) == 0:
        return "future_missing", np.nan, np.nan, np.nan
    path = np.log(future / price0) * 10_000.0
    if np.all(~np.isfinite(path)):
        return "future_missing", np.nan, np.nan, np.nan
    mfe = float(np.nanmax(path))
    mae = float(np.nanmin(path))
    final_return = float(path[-1]) if np.isfinite(path[-1]) else np.nan
    up_hits = np.flatnonzero(path >= barrier_bps)
    down_hits = np.flatnonzero(path <= -barrier_bps)
    up = int(up_hits[0]) if len(up_hits) else None
    down = int(down_hits[0]) if len(down_hits) else None
    if up is None and down is None:
        outcome = "none"
    elif up is not None and down is None:
        outcome = "upper_first"
    elif up is None and down is not None:
        outcome = "lower_first"
    elif up == down:
        outcome = "both_or_ambiguous"
    elif up < down:
        outcome = "upper_first"
    else:
        outcome = "lower_first"
    return outcome, mfe, mae, final_return


def build_path_labels(state: pd.DataFrame, horizons: list[int], barriers: list[int]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for symbol, group in state.groupby("symbol", sort=True):
        group = group.sort_values("minute").reset_index(drop=True)
        price = pd.to_numeric(group["mid_price_per_token_close"], errors="coerce").to_numpy()
        minutes = pd.to_datetime(group["minute"], utc=True)
        for horizon_hours in horizons:
            horizon_minutes = horizon_hours * 60
            for barrier_bps in barriers:
                for i in range(len(group)):
                    status = "ok"
                    if i + horizon_minutes >= len(group):
                        status = "future_missing"
                    elif minutes.iloc[i + horizon_minutes] - minutes.iloc[i] < pd.Timedelta(minutes=horizon_minutes):
                        status = "future_missing"
                    if status == "future_missing":
                        outcome, mfe, mae, final_return = "future_missing", np.nan, np.nan, np.nan
                    else:
                        future = price[i + 1 : i + horizon_minutes + 1]
                        outcome, mfe, mae, final_return = first_hit(float(price[i]), future, float(barrier_bps))
                        if outcome == "future_missing":
                            status = "future_missing"
                    rows.append(
                        {
                            "timestamp_utc": group.loc[i, "timestamp_utc"],
                            "timestamp_us": int(group.loc[i, "timestamp_us"]),
                            "symbol": symbol,
                            "asset": group.loc[i, "asset"],
                            "horizon_hours": horizon_hours,
                            "barrier_bps": barrier_bps,
                            "price_per_token": float(price[i]) if np.isfinite(price[i]) else np.nan,
                            "future_return_bps": final_return,
                            "mfe_up_bps": mfe,
                            "mae_down_bps": mae,
                            "barrier_first_hit": outcome,
                            "label_status": status,
                            "run_tag": "",
                        }
                    )
    return pd.DataFrame(rows)


def qbucket(values: pd.Series) -> pd.Series:
    result = pd.Series("missing", index=values.index, dtype="object")
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.nunique() < 3:
        result.loc[clean.index] = "flat"
        return result
    try:
        buckets = pd.qcut(clean, q=3, labels=["low", "mid", "high"], duplicates="drop")
        result.loc[buckets.index] = buckets.astype(str)
    except ValueError:
        result.loc[clean.index] = "flat"
    return result


def rate(series: pd.Series, value: str) -> float:
    return float((series == value).mean()) if len(series) else np.nan


def build_summary(state: pd.DataFrame, labels: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    label_summary = (
        labels.groupby(["symbol", "horizon_hours", "barrier_bps"], sort=True)
        .agg(
            label_rows=("symbol", "count"),
            valid_label_rows=("label_status", lambda x: int((x == "ok").sum())),
            future_missing_rows=("label_status", lambda x: int((x == "future_missing").sum())),
            upper_first_rate=("barrier_first_hit", lambda x: rate(x, "upper_first")),
            lower_first_rate=("barrier_first_hit", lambda x: rate(x, "lower_first")),
        )
        .reset_index()
    )
    state_summary = (
        state.groupby("symbol", sort=True)
        .agg(
            asset=("asset", "first"),
            state_rows=("symbol", "count"),
            first_timestamp_utc=("timestamp_utc", "min"),
            last_timestamp_utc=("timestamp_utc", "max"),
            median_mid_price_per_unit=("mid_price_per_unit_close", "median"),
            median_price_per_token=("mid_price_per_token_close", "median"),
            median_spread_bps=("spread_bps_median", "median"),
            total_book_ticker_rows=("book_ticker_count", "sum"),
            total_snapshot_rows=("snapshot_count", "sum"),
            total_trades=("trade_count", "sum"),
            total_trade_notional_quote=("trade_notional_quote_sum", "sum"),
        )
        .reset_index()
    )
    quality_counts = (
        quality.groupby("symbol", sort=True)
        .agg(
            raw_files=("path", "count"),
            raw_rows=("rows", "sum"),
            raw_error_files=("status", lambda x: int((x == "error").sum())),
            raw_empty_files=("status", lambda x: int((x == "empty").sum())),
            timestamp_monotonic_violations=("timestamp_monotonic_violations", "sum"),
            duplicate_rows_in_chunks=("duplicate_rows_in_chunks", "sum"),
            empty_price_rows=("empty_price_rows", "sum"),
            negative_amount_rows=("negative_amount_rows", "sum"),
            abnormal_spread_rows=("abnormal_spread_rows", "sum"),
        )
        .reset_index()
        if not quality.empty
        else pd.DataFrame()
    )
    out = state_summary.merge(quality_counts, on="symbol", how="left") if not quality_counts.empty else state_summary
    label_pivot = label_summary[
        (label_summary["horizon_hours"] == 12) & (label_summary["barrier_bps"] == 100)
    ][["symbol", "valid_label_rows", "future_missing_rows", "upper_first_rate", "lower_first_rate"]]
    out = out.merge(label_pivot, on="symbol", how="left")
    return out


def build_factor_tests(state: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    joined = labels[labels["label_status"] == "ok"].merge(
        state.drop(columns=["timestamp_utc"], errors="ignore"),
        on=["symbol", "asset", "timestamp_us"],
        how="left",
        suffixes=("", "_state"),
    )
    rows: list[dict[str, object]] = []
    for (symbol, horizon, barrier), group in joined.groupby(["symbol", "horizon_hours", "barrier_bps"], sort=True):
        baseline_upper = rate(group["barrier_first_hit"], "upper_first")
        baseline_lower = rate(group["barrier_first_hit"], "lower_first")
        for factor in FACTOR_COLS:
            if factor not in group.columns:
                continue
            bucket = qbucket(group[factor])
            for bucket_name, sub in group.groupby(bucket, sort=True):
                if bucket_name == "missing":
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "horizon_hours": horizon,
                        "barrier_bps": barrier,
                        "factor": factor,
                        "bucket": bucket_name,
                        "rows": int(len(sub)),
                        "upper_first_rate": rate(sub["barrier_first_hit"], "upper_first"),
                        "lower_first_rate": rate(sub["barrier_first_hit"], "lower_first"),
                        "baseline_upper_first_rate": baseline_upper,
                        "baseline_lower_first_rate": baseline_lower,
                        "edge_vs_baseline_upper": rate(sub["barrier_first_hit"], "upper_first") - baseline_upper,
                        "median_factor": float(pd.to_numeric(sub[factor], errors="coerce").median()),
                        "median_future_return_bps": float(pd.to_numeric(sub["future_return_bps"], errors="coerce").median()),
                        "median_mfe_up_bps": float(pd.to_numeric(sub["mfe_up_bps"], errors="coerce").median()),
                        "median_mae_down_bps": float(pd.to_numeric(sub["mae_down_bps"], errors="coerce").median()),
                    }
                )
    return pd.DataFrame(rows)


def high_bucket_edge(frame: pd.DataFrame, factor: str) -> tuple[int, float, float]:
    values = pd.to_numeric(frame[factor], errors="coerce")
    bucket = qbucket(values)
    valid = frame[bucket == "high"]
    if valid.empty:
        return 0, np.nan, np.nan
    baseline = rate(frame["barrier_first_hit"], "upper_first")
    edge = rate(valid["barrier_first_hit"], "upper_first") - baseline
    return int(len(valid)), rate(valid["barrier_first_hit"], "upper_first"), edge


def build_stability_checks(state: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    joined = labels[labels["label_status"] == "ok"].merge(
        state.drop(columns=["timestamp_utc"], errors="ignore"),
        on=["symbol", "asset", "timestamp_us"],
        how="left",
        suffixes=("", "_state"),
    )
    joined["minute"] = pd.to_datetime(joined["timestamp_us"], unit="us", utc=True)
    rows: list[dict[str, object]] = []
    for (symbol, horizon, barrier), group in joined.groupby(["symbol", "horizon_hours", "barrier_bps"], sort=True):
        horizon_minutes = int(horizon) * 60
        for factor in FACTOR_COLS:
            if factor not in group.columns:
                continue
            clean = group[pd.to_numeric(group[factor], errors="coerce").notna()].sort_values("minute").copy()
            if len(clean) < 30 or pd.to_numeric(clean[factor], errors="coerce").nunique() < 3:
                continue
            n, high_rate, edge = high_bucket_edge(clean, factor)
            rows.append(
                {
                    "check": "full_sample_reference",
                    "symbol": symbol,
                    "horizon_hours": horizon,
                    "barrier_bps": barrier,
                    "factor": factor,
                    "slice": "all",
                    "rows": int(len(clean)),
                    "high_bucket_rows": n,
                    "upper_first_rate_high": high_rate,
                    "edge_vs_baseline_upper": edge,
                }
            )
            stride = max(1, horizon_minutes)
            non_overlap = clean.iloc[::stride].copy()
            n, high_rate, edge = high_bucket_edge(non_overlap, factor)
            rows.append(
                {
                    "check": "non_overlap",
                    "symbol": symbol,
                    "horizon_hours": horizon,
                    "barrier_bps": barrier,
                    "factor": factor,
                    "slice": f"stride_{stride}m",
                    "rows": int(len(non_overlap)),
                    "high_bucket_rows": n,
                    "upper_first_rate_high": high_rate,
                    "edge_vs_baseline_upper": edge,
                }
            )
            shifted = clean.copy()
            shifted[factor] = shifted.groupby("symbol")[factor].shift(60)
            shifted = shifted[pd.to_numeric(shifted[factor], errors="coerce").notna()]
            n, high_rate, edge = high_bucket_edge(shifted, factor)
            rows.append(
                {
                    "check": "placebo_shift",
                    "symbol": symbol,
                    "horizon_hours": horizon,
                    "barrier_bps": barrier,
                    "factor": factor,
                    "slice": "factor_shifted_60m",
                    "rows": int(len(shifted)),
                    "high_bucket_rows": n,
                    "upper_first_rate_high": high_rate,
                    "edge_vs_baseline_upper": edge,
                }
            )
            midpoint = clean["minute"].min() + (clean["minute"].max() - clean["minute"].min()) / 2
            for name, sub in (("first_half", clean[clean["minute"] <= midpoint]), ("second_half", clean[clean["minute"] > midpoint])):
                n, high_rate, edge = high_bucket_edge(sub, factor)
                rows.append(
                    {
                        "check": "forward_split",
                        "symbol": symbol,
                        "horizon_hours": horizon,
                        "barrier_bps": barrier,
                        "factor": factor,
                        "slice": name,
                        "rows": int(len(sub)),
                        "high_bucket_rows": n,
                        "upper_first_rate_high": high_rate,
                        "edge_vs_baseline_upper": edge,
                    }
                )
    if rows:
        out = pd.DataFrame(rows)
    else:
        out = pd.DataFrame(
            columns=[
                "check",
                "symbol",
                "horizon_hours",
                "barrier_bps",
                "factor",
                "slice",
                "rows",
                "high_bucket_rows",
                "upper_first_rate_high",
                "edge_vs_baseline_upper",
            ]
        )
    barrier = (
        joined.groupby(["symbol", "horizon_hours", "barrier_bps"], sort=True)
        .agg(
            rows=("symbol", "count"),
            upper_first_rate=("barrier_first_hit", lambda x: rate(x, "upper_first")),
            lower_first_rate=("barrier_first_hit", lambda x: rate(x, "lower_first")),
        )
        .reset_index()
    )
    barrier["check"] = "barrier_sensitivity"
    barrier["factor"] = "baseline"
    barrier["slice"] = "all"
    barrier = barrier.rename(
        columns={
            "upper_first_rate": "upper_first_rate_high",
            "lower_first_rate": "edge_vs_baseline_upper",
            "rows": "rows",
        }
    )
    barrier["high_bucket_rows"] = barrier["rows"]
    return pd.concat([out, barrier[out.columns]], ignore_index=True)


def save_outputs(
    state: pd.DataFrame,
    covariance: pd.DataFrame,
    labels: pd.DataFrame,
    quality: pd.DataFrame,
    summary: pd.DataFrame,
    factor_tests: pd.DataFrame,
    stability: pd.DataFrame,
    paths: OutputPaths,
    run_tag: str,
) -> None:
    for path in asdict(paths).values():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    state = state.copy()
    covariance = covariance.copy()
    labels = labels.copy()
    for frame in (state, covariance, labels):
        if "run_tag" in frame.columns:
            frame["run_tag"] = run_tag
    state.to_parquet(paths.l2_state_parquet, index=False)
    covariance.to_parquet(paths.covariance_parquet, index=False)
    labels.to_parquet(paths.labels_parquet, index=False)
    quality.to_csv(paths.quality_csv, index=False)
    summary.to_csv(paths.summary_csv, index=False)
    factor_tests.to_csv(paths.factor_tests_csv, index=False)
    stability.to_csv(paths.stability_csv, index=False)
    completion = {
        "run_tag": run_tag,
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "outputs": {key: Path(value).as_posix() for key, value in asdict(paths).items()},
        "rows": {
            "l2_state": int(len(state)),
            "covariance_state": int(len(covariance)),
            "path_labels": int(len(labels)),
            "quality": int(len(quality)),
            "summary": int(len(summary)),
            "factor_tests": int(len(factor_tests)),
            "stability": int(len(stability)),
        },
    }
    paths.completion_json.write_text(json.dumps(completion, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_num(value: object, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def fmt_pct(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(number):
        return "n/a"
    return f"{number * 100.0:.1f}%"


def render_report(
    paths: OutputPaths,
    state: pd.DataFrame,
    labels: pd.DataFrame,
    quality: pd.DataFrame,
    summary: pd.DataFrame,
    factor_tests: pd.DataFrame,
    stability: pd.DataFrame,
    run_tag: str,
    horizons: list[int],
    barriers: list[int],
) -> None:
    lines: list[str] = []
    lines.append("# BONK Bullish L2 + CEX Regime 报告 v1")
    lines.append("")
    lines.append(f"- `run_tag`: `{run_tag}`")
    lines.append("- 数据源：Tardis downloadable CSV，exchange=`bullish`。")
    lines.append("- 当前版本只使用 `book_snapshot_25`、`book_ticker`、`trades`，没有使用 Binance Futures data-feeds replay，也没有采 `incremental_book_L2`。")
    lines.append("- Bullish `BONK1M*` 价格按每 1M BONK 报价保存，同时派生 `price_per_token = price / 1_000_000`。")
    lines.append("- `trades.side` 暂记为 exchange-reported side；未在本报告中断言 taker buy/sell 语义。")
    lines.append("- 本报告只评价数据质量和现象稳定性入口，不输出交易规则或收益承诺。")
    lines.append(f"- State/covariance symbols: `{','.join(sorted(state['symbol'].dropna().unique()))}`；下方 summary/factor tests 聚焦 path-labeled symbols。")
    lines.append("")
    lines.append("## 输出文件")
    lines.append("")
    lines.append(f"- L2 state parquet: `{paths.l2_state_parquet.as_posix()}`")
    lines.append(f"- Covariance state parquet: `{paths.covariance_parquet.as_posix()}`")
    lines.append(f"- Path labels parquet: `{paths.labels_parquet.as_posix()}`")
    lines.append(f"- Quality CSV: `{paths.quality_csv.as_posix()}`")
    lines.append(f"- Summary CSV: `{paths.summary_csv.as_posix()}`")
    lines.append(f"- Factor tests CSV: `{paths.factor_tests_csv.as_posix()}`")
    lines.append(f"- Stability CSV: `{paths.stability_csv.as_posix()}`")
    lines.append("")
    lines.append("## 覆盖与质量")
    lines.append("")
    lines.append("| symbol | state rows | raw files | raw rows | first ts | last ts | median price/1M | median price/token | median spread bps | trades | abnormal spread rows | future missing 12h/100bps |")
    lines.append("|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for row in summary.itertuples(index=False):
        lines.append(
            "| "
            f"{row.symbol} | {int(row.state_rows)} | {int(row.raw_files) if np.isfinite(row.raw_files) else 0} | "
            f"{int(row.raw_rows) if np.isfinite(row.raw_rows) else 0} | {row.first_timestamp_utc} | {row.last_timestamp_utc} | "
            f"{fmt_num(row.median_mid_price_per_unit, 6)} | {fmt_num(row.median_price_per_token, 12)} | "
            f"{fmt_num(row.median_spread_bps, 2)} | {int(row.total_trades) if np.isfinite(row.total_trades) else 0} | "
            f"{int(row.abnormal_spread_rows) if np.isfinite(row.abnormal_spread_rows) else 0} | "
            f"{int(row.future_missing_rows) if np.isfinite(row.future_missing_rows) else 0} |"
        )
    lines.append("")
    raw_errors = int((quality["status"] == "error").sum()) if not quality.empty else 0
    raw_empty = int((quality["status"] == "empty").sum()) if not quality.empty else 0
    lines.append(f"- Raw file errors: `{raw_errors}`; empty raw files: `{raw_empty}`.")
    lines.append(f"- Label horizons: `{horizons}` hours; fixed first-passage barriers: `{barriers}` bps.")
    lines.append("- 最后 H 小时样本会被标成 `future_missing`，避免用不存在的未来路径。")
    lines.append("")
    lines.append("## 因子诊断快读")
    lines.append("")
    display = factor_tests[
        (factor_tests["bucket"] == "high")
        & (factor_tests["horizon_hours"].isin([1, 4, 12]))
        & (factor_tests["barrier_bps"] == 100)
    ].copy()
    if display.empty:
        lines.append("当前样本没有足够分桶结果。")
    else:
        display["abs_edge"] = display["edge_vs_baseline_upper"].abs()
        display = display.sort_values(["symbol", "horizon_hours", "abs_edge"], ascending=[True, True, False])
        lines.append("| symbol | H | factor | high rows | high upper first | baseline upper | edge | median factor |")
        lines.append("|---|---:|---|---:|---:|---:|---:|---:|")
        for row in display.groupby(["symbol", "horizon_hours"], sort=True).head(6).itertuples(index=False):
            lines.append(
                "| "
                f"{row.symbol} | {row.horizon_hours}h | `{row.factor}` | {int(row.rows)} | "
                f"{fmt_pct(row.upper_first_rate)} | {fmt_pct(row.baseline_upper_first_rate)} | "
                f"{fmt_pct(row.edge_vs_baseline_upper)} | {fmt_num(row.median_factor, 4)} |"
            )
    lines.append("")
    lines.append("## 稳定性检查入口")
    lines.append("")
    lines.append("报告和 CSV 已显式输出四类稳定性检查入口：")
    lines.append("")
    lines.append("- `non_overlap`: 按 horizon stride 抽样，降低重叠标签自相关。")
    lines.append("- `placebo_shift`: 因子整体滞后 60 分钟后重测，排查伪相关。")
    lines.append("- `forward_split`: 前半窗口和后半窗口分别计算 high-bucket edge。")
    lines.append("- `barrier_sensitivity`: 50/100/200/300 bps barrier 的 baseline first-passage 变化。")
    lines.append("")
    stable_display = stability[
        stability["check"].isin(["non_overlap", "placebo_shift", "forward_split"])
        & (stability["barrier_bps"] == 100)
        & (stability["horizon_hours"].isin([1, 4, 12]))
    ].copy()
    if not stable_display.empty:
        stable_display["abs_edge"] = stable_display["edge_vs_baseline_upper"].abs()
        stable_display = stable_display.sort_values("abs_edge", ascending=False).head(20)
        lines.append("| check | symbol | H | factor | slice | rows | high rows | edge |")
        lines.append("|---|---|---:|---|---|---:|---:|---:|")
        for row in stable_display.itertuples(index=False):
            lines.append(
                "| "
                f"{row.check} | {row.symbol} | {row.horizon_hours}h | `{row.factor}` | {row.slice} | "
                f"{int(row.rows)} | {int(row.high_bucket_rows)} | {fmt_pct(row.edge_vs_baseline_upper)} |"
            )
        lines.append("")
    lines.append("## 当前边界")
    lines.append("")
    lines.append("- CEX covariance v1 先基于已下载 symbols 的 1m returns；如果后续下载 DOGE/PEPE/WIF/SHIB 等 Bullish L2，可直接把 symbols 加进同一脚本重建。")
    lines.append("- 没有 `incremental_book_L2` 时，OFI 只能用 top-of-book/深度快照近似；严格 queue-level book reconstruction 仍需后续单独采增量订单簿。")
    lines.append("- 因子表用于找现象，不代表可执行策略。任何候选现象都需要更长窗口和交易成本/成交条件建模。")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    symbols = parse_list(args.symbols)
    label_symbols = parse_list(args.label_symbols) if args.label_symbols else symbols
    horizons = parse_int_list(args.horizons_hours)
    barriers = parse_int_list(args.barriers_bps)
    paths = output_paths(args.data_root, args.date_dir, args.doc_dir, args.run_tag)

    quality = inspect_raw_files(args.data_root, symbols, args.chunksize, args.abnormal_spread_bps)
    state = aggregate_all(args.data_root, symbols, args.chunksize)
    state = add_returns(state)
    covariance = build_covariance_state(state)
    label_state = state[state["symbol"].isin(label_symbols)].copy()
    label_quality = quality[quality["symbol"].isin(label_symbols)].copy() if not quality.empty else quality
    labels = build_path_labels(label_state, horizons, barriers)
    summary = build_summary(label_state, labels, label_quality)
    factor_tests = build_factor_tests(label_state, labels)
    stability = build_stability_checks(label_state, labels)
    save_outputs(state, covariance, labels, quality, summary, factor_tests, stability, paths, args.run_tag)
    render_report(paths, state, labels, quality, summary, factor_tests, stability, args.run_tag, horizons, barriers)

    print(f"l2_state_rows={len(state)} path_label_rows={len(labels)}")
    for row in summary.itertuples(index=False):
        print(
            f"{row.symbol}: state_rows={row.state_rows} raw_files={row.raw_files} "
            f"raw_rows={row.raw_rows} median_spread_bps={fmt_num(row.median_spread_bps, 2)}"
        )
    print(f"l2_state_parquet={paths.l2_state_parquet}")
    print(f"covariance_parquet={paths.covariance_parquet}")
    print(f"labels_parquet={paths.labels_parquet}")
    print(f"summary_csv={paths.summary_csv}")
    print(f"factor_tests_csv={paths.factor_tests_csv}")
    print(f"stability_csv={paths.stability_csv}")
    print(f"report_md={paths.report_md}")


if __name__ == "__main__":
    main()
