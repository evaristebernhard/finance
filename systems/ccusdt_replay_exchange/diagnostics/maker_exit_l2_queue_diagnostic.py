#!/usr/bin/env python
"""L2 queue-depletion diagnostic for selected maker-first exit events.

This is the fast-line L2 replay layer. It refines selected maker-first exit
events by streaming canonical incremental L2 updates and estimating whether the
displayed queue ahead at the posted touch was depleted inside TTL.

It is still an approximation: same-price displayed-size decreases can include
cancels as well as trades. The strict Runner maker lifecycle remains separate.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


PRICE_SCALE = 100_000_000
DEFAULT_EVENTS = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_first_exit_policy_q70_idle01_g1_warmup_strict_20260516_18_20260522/"
    "maker_first_exit_events.parquet"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_exit_l2_queue_q70_idle01_g1_warmup_strict_20260516_18_20260522"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-maker-first-exit-l2-queue-20260522.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--chunk-rows", type=int, default=750_000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def l2_path(repo_root: Path, symbol: str, day: str) -> Path:
    return (
        repo_root
        / "data"
        / "canonical"
        / "cex"
        / "bullish"
        / symbol
        / "l2_level_update_v1"
        / f"dt={day}"
        / "part_000001.csv.gz"
    )


def price_key(value: Any) -> int:
    return int(round(float(value) * PRICE_SCALE))


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def read_events(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pq.read_table(path).to_pandas()
    if df.empty:
        return df
    df = df.copy()
    df["l2_side"] = df["exit_action"].astype(str).str.lower().map({"sell": "sell", "buy": "buy"})
    df["price_key"] = df["maker_post_price"].map(price_key)
    df["deadline_ts_us"] = (
        pd.to_numeric(df["exit_decision_ts_us"], errors="coerce").astype("int64")
        + (pd.to_numeric(df["ttl_sec"], errors="coerce") * 1_000_000).round().astype("int64")
    )
    return df


def initialize_states(events: pd.DataFrame) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for idx, row in events.reset_index(drop=True).iterrows():
        queue_ahead = max(float(row["maker_queue_ahead_qty"]), 0.0)
        states.append(
            {
                "event_idx": int(idx),
                "date": str(row["date"]),
                "shadow_position_id": int(row["shadow_position_id"]),
                "l2_side": str(row["l2_side"]),
                "price_key": int(row["price_key"]),
                "start_ts_us": int(row["exit_decision_ts_us"]),
                "deadline_ts_us": int(row["deadline_ts_us"]),
                "prev_qty": queue_ahead,
                "queue_remaining": queue_ahead,
                "queue_ahead_qty": queue_ahead,
                "l2_depleted_qty": 0.0,
                "l2_update_count": 0,
                "l2_queue_depleted": queue_ahead <= 0.0,
                "l2_queue_depleted_ts_us": int(row["exit_decision_ts_us"]) if queue_ahead <= 0.0 else None,
            }
        )
    return states


def stream_day_l2(repo_root: Path, symbol: str, day: str, states: list[dict[str, Any]], chunk_rows: int) -> dict[str, Any]:
    path = l2_path(repo_root, symbol, day)
    if not path.exists():
        raise FileNotFoundError(path)
    active_by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for state in states:
        key = (state["l2_side"], state["price_key"])
        active_by_key.setdefault(key, []).append(state)
    if not active_by_key:
        return {"path": str(path), "rows_read": 0, "matched_rows": 0}
    sides = {key[0] for key in active_by_key}
    prices = {key[1] for key in active_by_key}
    min_ts = min(state["start_ts_us"] for state in states)
    max_ts = max(state["deadline_ts_us"] for state in states)
    rows_read = 0
    matched_rows = 0
    usecols = ["local_ts_us", "side", "price", "qty"]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = pd.read_csv(handle, usecols=usecols, chunksize=chunk_rows)
        for chunk in reader:
            rows_read += int(len(chunk))
            chunk["local_ts_us"] = pd.to_numeric(chunk["local_ts_us"], errors="coerce")
            chunk = chunk[(chunk["local_ts_us"] > min_ts) & (chunk["local_ts_us"] <= max_ts)]
            if chunk.empty:
                continue
            chunk["side"] = chunk["side"].astype(str).str.lower()
            chunk = chunk[chunk["side"].isin(sides)]
            if chunk.empty:
                continue
            chunk["price_key"] = (pd.to_numeric(chunk["price"], errors="coerce") * PRICE_SCALE).round().astype("Int64")
            chunk = chunk[chunk["price_key"].isin(prices)]
            if chunk.empty:
                continue
            chunk["qty"] = pd.to_numeric(chunk["qty"], errors="coerce").fillna(0.0)
            chunk = chunk.sort_values("local_ts_us")
            for row in chunk.itertuples(index=False):
                ts = int(row.local_ts_us)
                key = (str(row.side), int(row.price_key))
                candidates = active_by_key.get(key)
                if not candidates:
                    continue
                qty = max(float(row.qty), 0.0)
                for state in candidates:
                    if state["l2_queue_depleted"]:
                        continue
                    if ts <= state["start_ts_us"] or ts > state["deadline_ts_us"]:
                        continue
                    state["l2_update_count"] += 1
                    delta = qty - float(state["prev_qty"])
                    state["prev_qty"] = qty
                    if delta >= 0.0:
                        continue
                    depletion = -delta
                    state["l2_depleted_qty"] += depletion
                    state["queue_remaining"] = max(0.0, float(state["queue_remaining"]) - depletion)
                    matched_rows += 1
                    if state["queue_remaining"] <= 1e-12:
                        state["l2_queue_depleted"] = True
                        state["l2_queue_depleted_ts_us"] = ts
    return {"path": str(path), "rows_read": rows_read, "matched_rows": matched_rows}


def build_l2_events(events: pd.DataFrame, states: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = events.reset_index(drop=True)
    for state in states:
        source = base.iloc[int(state["event_idx"])]
        l2_fill = bool(state["l2_queue_depleted"])
        l2_fill_ts = state["l2_queue_depleted_ts_us"]
        final_net = float(source["maker_touch_net_bps"]) if l2_fill else float(source["fallback_taker_net_bps"])
        pure_taker = float(source["pure_taker_net_bps"])
        saved_spread = float(source["saved_spread_bps"]) if l2_fill else 0.0
        missed_decay = 0.0 if l2_fill else float(source["missed_fill_decay_bps"])
        adverse_selection = float(source["adverse_selection_bps"]) if l2_fill else 0.0
        actual = float(source["actual_exposure"])
        row = source.to_dict()
        row.update(
            {
                "schema_id": "ccusdt_maker_first_exit_l2_queue_event_v1",
                "l2_fill_model": "same_price_l2_depletion_v1",
                "l2_queue_depleted": l2_fill,
                "l2_queue_depleted_ts_us": l2_fill_ts,
                "l2_queue_depleted_delay_us": (
                    int(l2_fill_ts) - int(source["exit_decision_ts_us"]) if l2_fill_ts is not None else None
                ),
                "l2_update_count": int(state["l2_update_count"]),
                "l2_queue_ahead_qty": float(state["queue_ahead_qty"]),
                "l2_depleted_qty": float(state["l2_depleted_qty"]),
                "l2_queue_remaining": float(state["queue_remaining"]),
                "l2_final_net_bps": final_net,
                "l2_final_delta_vs_taker_bps": final_net - pure_taker,
                "l2_saved_spread_bps": saved_spread,
                "l2_missed_fill_decay_bps": missed_decay,
                "l2_adverse_selection_bps": adverse_selection,
                "l2_weighted_final_delta_vs_taker_bps": (final_net - pure_taker) * actual,
                "l2_weighted_saved_spread_bps": saved_spread * actual,
                "l2_weighted_missed_fill_decay_bps": missed_decay * actual,
                "l2_weighted_adverse_selection_bps": adverse_selection * actual,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    return (
        events.groupby(["exit_profile_source", "date", "gate_name"], sort=True)
        .agg(
            maker_attempts=("shadow_position_id", "count"),
            exposure=("actual_exposure", "sum"),
            trade_queue_fill_rate=("maker_filled", "mean"),
            l2_queue_fill_rate=("l2_queue_depleted", "mean"),
            trade_queue_weighted_delta=("weighted_final_delta_vs_taker_bps", "sum"),
            l2_queue_weighted_delta=("l2_weighted_final_delta_vs_taker_bps", "sum"),
            l2_saved_spread=("l2_weighted_saved_spread_bps", "sum"),
            l2_missed_decay=("l2_weighted_missed_fill_decay_bps", "sum"),
            l2_adverse_selection=("l2_weighted_adverse_selection_bps", "sum"),
        )
        .reset_index()
    )


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def optional_fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 60) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    use_cols = [col for col in columns if col in df.columns]
    lines = ["| " + " | ".join(use_cols) + " |", "| " + " | ".join(["---"] * len(use_cols)) + " |"]
    for _, row in df.loc[:, use_cols].head(max_rows).iterrows():
        cells = []
        for col in use_cols:
            value = row[col]
            cells.append(optional_fmt(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(path: Path, summary: dict[str, Any], grouped: pd.DataFrame) -> None:
    lines = [
        "# CCUSDT maker-first exit L2 queue diagnostic",
        "",
        "This fast-line diagnostic streams canonical `l2_level_update_v1` for selected maker-first exit events and estimates displayed queue depletion at the posted touch.",
        "",
        "It is not a strict private-order fill simulator. Same-price displayed-size decreases can include cancellations, so this is a queue-pressure diagnostic between the trade-only proxy and the future strict Runner maker lifecycle.",
        "",
        "## Scope",
        "",
        f"- Events: `{summary['events_path']}`",
        f"- Attempts: `{summary['attempts']}`",
        f"- L2 rows read: `{summary['l2_rows_read']}`",
        f"- L2 matched depletion rows: `{summary['l2_matched_rows']}`",
        f"- Output directory: `{summary['out_dir']}`",
        "",
        "## Summary",
        "",
    ]
    lines.extend(
        markdown_table(
            grouped,
            [
                "exit_profile_source",
                "date",
                "gate_name",
                "maker_attempts",
                "exposure",
                "trade_queue_fill_rate",
                "l2_queue_fill_rate",
                "trade_queue_weighted_delta",
                "l2_queue_weighted_delta",
                "l2_saved_spread",
                "l2_missed_decay",
                "l2_adverse_selection",
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Readout",
            "",
            "If L2 depletion materially disagrees with the trade-queue proxy, maker-first exit must stay diagnostic-only until strict Runner maker orders can model post-only ack, cancel, fallback, and private fill causality.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    event_path = repo_path(repo_root, args.events)
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    events = read_events(event_path)
    states = initialize_states(events)
    l2_stats = []
    for day in sorted(events["date"].astype(str).unique()) if not events.empty else []:
        day_states = [state for state in states if state["date"] == day]
        l2_stats.append(stream_day_l2(repo_root, args.symbol, day, day_states, args.chunk_rows))
    l2_events = build_l2_events(events, states)
    grouped = summarize(l2_events)
    summary = {
        "schema_id": "ccusdt_maker_first_exit_l2_queue_summary_v1",
        "ok": True,
        "events_path": str(event_path),
        "out_dir": str(out_dir),
        "attempts": int(len(events)),
        "l2_rows_read": int(sum(item["rows_read"] for item in l2_stats)),
        "l2_matched_rows": int(sum(item["matched_rows"] for item in l2_stats)),
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        "per_day_l2_stats": l2_stats,
        "aggregate": grouped.to_dict(orient="records"),
        "outputs": {
            "events_csv": str(out_dir / "maker_first_exit_l2_events.csv"),
            "events_parquet": str(out_dir / "maker_first_exit_l2_events.parquet"),
            "summary_csv": str(out_dir / "maker_first_exit_l2_summary.csv"),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    write_csv(out_dir / "maker_first_exit_l2_events.csv", l2_events)
    write_parquet(out_dir / "maker_first_exit_l2_events.parquet", l2_events)
    write_csv(out_dir / "maker_first_exit_l2_summary.csv", grouped)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report_path, summary, grouped)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
