#!/usr/bin/env python3
"""Polymarket Binance-close EV ensemble runner.

Read-only tool. It runs the existing Binance-close scanner over multiple
realized-volatility lookback windows, joins rows by market/outcome, and applies
robust-min gates so a signal must survive volatility-regime assumptions.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("output/polymarket_binance_close_ensemble")
DEFAULT_LOOKBACKS = [60, 180, 360]


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def signal_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("event_slug") or ""),
        str(row.get("slug") or ""),
        str(row.get("outcome") or ""),
        str(row.get("token_id") or ""),
    )


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def coerce_lookback(row: dict[str, Any]) -> int | None:
    for key in ("vol_lookback_minutes", "lookback_minutes", "vol_lookback"):
        value = safe_float(row.get(key))
        if value is not None:
            return int(value)
    return None


def representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if safe_bool(row.get("book_ok")):
            return row
    return rows[0]


def build_ensemble_rows(
    rows: list[dict[str, Any]],
    required_lookbacks: list[int],
    min_robust_pnl: float,
    min_robust_edge_cents: float,
    min_probability: float = 0.0,
    max_probability: float = 1.0,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[int, dict[str, Any]]] = {}
    for row in rows:
        lookback = coerce_lookback(row)
        if lookback is None:
            continue
        grouped.setdefault(signal_key(row), {})[lookback] = row

    out: list[dict[str, Any]] = []
    for key, by_lookback in grouped.items():
        base = representative(list(by_lookback.values()))
        present = sorted(by_lookback)
        required_present = [lb for lb in required_lookbacks if lb in by_lookback]
        missing = [lb for lb in required_lookbacks if lb not in by_lookback]
        pnls = [safe_float(by_lookback[lb].get("expected_profit_usd"), -1e9) for lb in required_present]
        edges = [safe_float(by_lookback[lb].get("edge_cents"), -1e9) for lb in required_present]
        probs = [safe_float(by_lookback[lb].get("model_prob"), 0.0) for lb in required_present]
        pnls_f = [float(x) for x in pnls if x is not None]
        edges_f = [float(x) for x in edges if x is not None]
        probs_f = [float(x) for x in probs if x is not None]
        has_all = not missing
        all_positive = has_all and all(x > 0 for x in pnls_f) and len(pnls_f) == len(required_lookbacks)
        robust_min_pnl = min(pnls_f) if pnls_f else None
        robust_min_edge = min(edges_f) if edges_f else None
        min_prob = min(probs_f) if probs_f else None
        max_prob = max(probs_f) if probs_f else None
        probability_extreme = False
        if min_prob is not None and max_prob is not None:
            probability_extreme = min_prob < min_probability or max_prob > max_probability
        ensemble_candidate = (
            has_all
            and all_positive
            and robust_min_pnl is not None
            and robust_min_edge is not None
            and robust_min_pnl >= min_robust_pnl
            and robust_min_edge >= min_robust_edge_cents
            and not probability_extreme
        )
        row_out: dict[str, Any] = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "event_id": base.get("event_id", ""),
            "event_title": base.get("event_title", ""),
            "event_slug": base.get("event_slug", ""),
            "market_id": base.get("market_id", ""),
            "question": base.get("question", ""),
            "slug": base.get("slug", ""),
            "symbol": base.get("symbol", ""),
            "kind": base.get("kind", ""),
            "outcome": base.get("outcome", ""),
            "token_id": base.get("token_id", ""),
            "settle_time_utc": base.get("settle_time_utc", ""),
            "minutes_to_settle": safe_float(base.get("minutes_to_settle")),
            "binance_price": safe_float(base.get("binance_price")),
            "model_threshold": safe_float(base.get("model_threshold")),
            "avg_price": safe_float(base.get("avg_price")),
            "best_ask": safe_float(base.get("best_ask")),
            "available_notional_usd": safe_float(base.get("available_notional_usd")),
            "required_lookbacks": ",".join(str(x) for x in required_lookbacks),
            "present_lookbacks": ",".join(str(x) for x in present),
            "missing_lookbacks": ",".join(str(x) for x in missing),
            "has_all_required_lookbacks": has_all,
            "all_lookbacks_positive": all_positive,
            "probability_extreme": probability_extreme,
            "robust_min_expected_profit_usd": robust_min_pnl,
            "robust_min_edge_cents": robust_min_edge,
            "min_model_prob": min_prob,
            "max_model_prob": max_prob,
            "mean_model_prob": sum(probs_f) / len(probs_f) if probs_f else None,
            "ensemble_candidate": ensemble_candidate,
        }
        for lb in required_lookbacks:
            r = by_lookback.get(lb, {})
            row_out[f"pnl_{lb}m"] = safe_float(r.get("expected_profit_usd")) if r else None
            row_out[f"edge_{lb}m_cents"] = safe_float(r.get("edge_cents")) if r else None
            row_out[f"prob_{lb}m"] = safe_float(r.get("model_prob")) if r else None
            row_out[f"stdev_{lb}m_logret_1m"] = safe_float(r.get("stdev_logret_1m")) if r else None
        out.append(row_out)
    out.sort(key=lambda r: (bool(r["ensemble_candidate"]), float(r.get("robust_min_expected_profit_usd") or -1e9)), reverse=True)
    return out


def parse_lookbacks(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def run_scanner_for_lookback(args: argparse.Namespace, lookback: int, scan_dir: Path) -> Path:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "polymarket_binance_close_signal_scan.py"),
        "--output-dir",
        str(scan_dir),
        "--event-limit",
        str(args.event_limit),
        "--market-limit",
        str(args.market_limit),
        "--book-token-limit",
        str(args.book_token_limit),
        "--target-notional-usd",
        str(args.target_notional_usd),
        "--vol-lookback-minutes",
        str(lookback),
        "--min-minutes-to-settle",
        str(args.min_minutes_to_settle),
        "--max-hours-to-settle",
        str(args.max_hours_to_settle),
        "--min-edge-cents",
        str(args.scan_min_edge_cents),
        "--min-expected-profit-usd",
        str(args.scan_min_expected_profit_usd),
        "--min-model-prob",
        str(args.scan_min_model_prob),
        "--http-timeout",
        str(args.http_timeout),
        "--sleep-ms",
        str(args.sleep_ms),
    ]
    if args.query:
        cmd += ["--query", args.query]
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    return scan_dir / "signals.csv"


def summarize(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    candidates = [r for r in rows if r.get("ensemble_candidate") is True]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "required_lookbacks": parse_lookbacks(args.lookbacks),
        "rows": len(rows),
        "ensemble_candidates": len(candidates),
        "min_robust_expected_profit_usd": args.min_robust_expected_profit_usd,
        "min_robust_edge_cents": args.min_robust_edge_cents,
        "min_probability": args.min_probability,
        "max_probability": args.max_probability,
        "top_candidates": candidates[:10],
    }


def write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Polymarket Binance Close Ensemble",
        "",
        f"Generated: {summary['generated_at_utc']}",
        "",
        "Read-only paper research. No orders are signed or submitted.",
        "",
        "## Counts",
        "",
        f"- Required lookbacks: {summary['required_lookbacks']}",
        f"- Ensemble rows: {summary['rows']}",
        f"- Ensemble candidates: {summary['ensemble_candidates']}",
        f"- Min robust expected profit USD: {summary['min_robust_expected_profit_usd']}",
        f"- Min robust edge cents: {summary['min_robust_edge_cents']}",
        f"- Probability band: {summary['min_probability']} -> {summary['max_probability']}",
        "",
        "## Top Candidates",
        "",
        "| rank | robust_pnl | robust_edge_c | prob_band | symbol | outcome | question |",
        "|---:|---:|---:|---|---|---|---|",
    ]
    for i, row in enumerate(summary["top_candidates"], 1):
        lines.append(
            f"| {i} | {float(row.get('robust_min_expected_profit_usd') or 0):.4g} | "
            f"{float(row.get('robust_min_edge_cents') or 0):.4g} | "
            f"{float(row.get('min_model_prob') or 0):.4g}-{float(row.get('max_model_prob') or 0):.4g} | "
            f"{row.get('symbol','')} | {row.get('outcome','')} | {str(row.get('question',''))[:100]} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build robust Binance-close EV ensemble from multiple vol lookbacks.")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--lookbacks", default=",".join(str(x) for x in DEFAULT_LOOKBACKS))
    p.add_argument("--input-signals-csv", action="append", default=[], help="Optional precomputed signals CSV; may be repeated.")
    p.add_argument("--event-limit", type=int, default=180)
    p.add_argument("--market-limit", type=int, default=120)
    p.add_argument("--book-token-limit", type=int, default=120)
    p.add_argument("--target-notional-usd", type=float, default=100.0)
    p.add_argument("--min-minutes-to-settle", type=float, default=5.0)
    p.add_argument("--max-hours-to-settle", type=float, default=48.0)
    p.add_argument("--scan-min-edge-cents", type=float, default=-2.0)
    p.add_argument("--scan-min-expected-profit-usd", type=float, default=-1.0)
    p.add_argument("--scan-min-model-prob", type=float, default=0.0)
    p.add_argument("--min-robust-expected-profit-usd", type=float, default=0.5)
    p.add_argument("--min-robust-edge-cents", type=float, default=0.25)
    p.add_argument("--min-probability", type=float, default=0.01)
    p.add_argument("--max-probability", type=float, default=0.99)
    p.add_argument("--query", default="")
    p.add_argument("--http-timeout", type=float, default=20.0)
    p.add_argument("--sleep-ms", type=int, default=25)
    p.add_argument("--self-test", action="store_true")
    return p.parse_args()


def self_test() -> None:
    rows = []
    for lb, pnl in [(60, 2.0), (180, 1.0), (360, 0.6)]:
        rows.append({"event_slug": "e", "slug": "s", "outcome": "Yes", "token_id": "t", "vol_lookback_minutes": lb, "expected_profit_usd": pnl, "edge_cents": pnl, "model_prob": 0.5})
    out = build_ensemble_rows(rows, [60, 180, 360], 0.5, 0.25, 0.01, 0.99)
    assert len(out) == 1 and out[0]["ensemble_candidate"] is True
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    lookbacks = parse_lookbacks(args.lookbacks)
    all_rows: list[dict[str, Any]] = []
    if args.input_signals_csv:
        for path_raw in args.input_signals_csv:
            path = Path(path_raw)
            if not path.is_absolute():
                path = REPO_ROOT / path
            all_rows.extend(read_csv(path))
    else:
        scans_dir = output_dir / "scans"
        for lb in lookbacks:
            path = run_scanner_for_lookback(args, lb, scans_dir / f"lookback_{lb}m")
            rows = read_csv(path)
            for row in rows:
                row["vol_lookback_minutes"] = str(lb)
            all_rows.extend(rows)
    ensemble = build_ensemble_rows(
        all_rows,
        lookbacks,
        args.min_robust_expected_profit_usd,
        args.min_robust_edge_cents,
        args.min_probability,
        args.max_probability,
    )
    write_csv(output_dir / "ensemble_signals.csv", ensemble)
    summary = summarize(ensemble, args)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_summary_md(output_dir / "summary.md", summary)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
