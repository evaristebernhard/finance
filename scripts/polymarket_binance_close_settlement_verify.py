"""Verify paper Polymarket Binance-close signals after settlement.

Input is a `signals.csv` produced by `polymarket_binance_close_signal_scan.py`.
The verifier fetches the Binance Vision 1-minute candle used by the market
rules, computes the realized binary outcome, and marks the paper PnL that would
have resulted from crossing the quoted CLOB asks in the scan.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BINANCE_DATA_BASE = "https://data-api.binance.vision"
REPO_ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--signals-csv",
        type=Path,
        default=Path("output/polymarket_binance_close_signal_scan/signals.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--candidate-only", action="store_true")
    parser.add_argument("--http-timeout", type=float, default=20.0)
    parser.add_argument("--sleep-ms", type=int, default=40)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def http_get_json(base: str, path: str, params: dict[str, Any] | None, timeout: float) -> Any:
    query = ""
    if params:
        query = "?" + urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    req = Request(
        base.rstrip("/") + "/" + path.lstrip("/") + query,
        headers={"User-Agent": "finance-chain-polymarket-binance-close-verify/0.1"},
        method="GET",
    )
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable http_get_json state")


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_ts(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def iso_ts(ts: int | None) -> str:
    if ts is None:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def binance_server_ts(timeout: float) -> int:
    body = http_get_json(BINANCE_DATA_BASE, "/api/v3/time", None, timeout)
    return int(body["serverTime"]) // 1000


def fetch_binance_klines(symbol: str, limit: int, timeout: float, start_ms: int | None = None) -> list[list[Any]]:
    params: dict[str, Any] = {"symbol": symbol, "interval": "1m", "limit": limit}
    if start_ms is not None:
        params["startTime"] = start_ms
    return http_get_json(BINANCE_DATA_BASE, "/api/v3/klines", params, timeout)


def historical_close(symbol: str, ts: int, timeout: float) -> float | None:
    rows = fetch_binance_klines(symbol, 1, timeout, start_ms=ts * 1000)
    if not rows:
        return None
    return safe_float(rows[0][4] if len(rows[0]) > 4 else None)


def event_yes_won(row: dict[str, Any], close_price: float, timeout: float) -> tuple[bool | None, str]:
    kind = str(row.get("kind") or "")
    threshold = safe_float(row.get("model_threshold"))
    lower = safe_float(row.get("lower"))
    upper = safe_float(row.get("upper"))

    if kind == "above_close":
        if threshold is None:
            return None, "missing_threshold"
        return close_price > threshold, f"close>{threshold:g}"
    if kind == "below_close":
        if threshold is None:
            return None, "missing_threshold"
        return close_price < threshold, f"close<{threshold:g}"
    if kind == "range_close":
        if lower is None or upper is None:
            return None, "missing_range"
        return lower <= close_price < upper, f"{lower:g}<=close<{upper:g}"
    if kind == "updown_close":
        if threshold is None:
            symbol = str(row.get("symbol") or "")
            settle_ts = parse_ts(row.get("settle_time_utc"))
            if not symbol or settle_ts is None:
                return None, "missing_previous_close_inputs"
            threshold = historical_close(symbol, settle_ts - 24 * 3600, timeout)
        if threshold is None:
            return None, "missing_previous_close"
        return close_price > threshold, f"close>{threshold:g}"
    return None, f"unsupported_kind:{kind}"


def outcome_won(row: dict[str, Any], yes_won: bool) -> tuple[bool | None, str]:
    outcome = str(row.get("outcome") or "").strip().lower()
    if outcome in {"yes", "up"}:
        return yes_won, "yes_side" if outcome == "yes" else "up_side"
    if outcome in {"no", "down"}:
        return not yes_won, "no_side" if outcome == "no" else "down_side"
    return None, f"unsupported_outcome:{outcome}"


def realized_for_row(
    row: dict[str, Any],
    server_ts: int,
    close_cache: dict[tuple[str, int], float | None],
    timeout: float,
) -> dict[str, Any]:
    out = dict(row)
    symbol = str(row.get("symbol") or "")
    settle_ts = parse_ts(row.get("settle_time_utc"))
    out["verification_generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    out["verification_server_time_utc"] = iso_ts(server_ts)
    out["settlement_status"] = "error"
    out["binance_settle_close"] = ""
    out["yes_won"] = ""
    out["paper_outcome_won"] = ""
    out["paper_payout_usd"] = ""
    out["paper_realized_profit_usd"] = ""
    out["paper_realized_roi_on_cost"] = ""
    out["settlement_rule"] = ""
    out["settlement_error"] = ""

    if not symbol or settle_ts is None:
        out["settlement_error"] = "missing_symbol_or_settle_time"
        return out
    # The 16:00 candle final close is only final after the minute has ended.
    if server_ts < settle_ts + 60:
        out["settlement_status"] = "pending"
        out["settlement_error"] = f"server_time_before_candle_close:{iso_ts(settle_ts + 60)}"
        return out

    key = (symbol, settle_ts)
    if key not in close_cache:
        close_cache[key] = historical_close(symbol, settle_ts, timeout)
    close_price = close_cache[key]
    if close_price is None:
        out["settlement_error"] = "missing_binance_close"
        return out

    yes_result, rule = event_yes_won(row, close_price, timeout)
    out["binance_settle_close"] = close_price
    out["settlement_rule"] = rule
    if yes_result is None:
        out["settlement_error"] = rule
        return out
    won, side_rule = outcome_won(row, yes_result)
    out["yes_won"] = yes_result
    out["settlement_rule"] = f"{rule}; {side_rule}"
    if won is None:
        out["settlement_error"] = side_rule
        return out

    shares = safe_float(row.get("shares"))
    cost = safe_float(row.get("cost_usd"))
    if cost is None:
        cost = safe_float(row.get("target_notional_usd"))
    fee = safe_float(row.get("fee_usd")) or 0.0
    if shares is None or cost is None:
        out["settlement_error"] = "missing_fill_for_pnl"
        return out

    payout = shares if won else 0.0
    profit = payout - cost - fee
    out["settlement_status"] = "settled"
    out["paper_outcome_won"] = won
    out["paper_payout_usd"] = payout
    out["paper_realized_profit_usd"] = profit
    out["paper_realized_roi_on_cost"] = profit / cost if cost > EPS else ""
    return out


def read_csv(path: Path) -> list[dict[str, Any]]:
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


def fmt(value: Any) -> str:
    if value is None or value == "":
        return ""
    number = safe_float(value)
    if number is not None:
        return f"{number:.6g}"
    return str(value)


def summarize(rows: list[dict[str, Any]], input_path: Path, server_ts: int) -> dict[str, Any]:
    settled = [row for row in rows if row.get("settlement_status") == "settled"]
    pending = [row for row in rows if row.get("settlement_status") == "pending"]
    errors = [row for row in rows if row.get("settlement_status") == "error"]
    candidates = [row for row in rows if safe_bool(row.get("candidate"))]
    settled_candidates = [row for row in candidates if row.get("settlement_status") == "settled"]

    def total(key: str, sample: list[dict[str, Any]]) -> float:
        return sum(safe_float(row.get(key)) or 0.0 for row in sample)

    candidate_cost = total("cost_usd", settled_candidates)
    candidate_profit = total("paper_realized_profit_usd", settled_candidates)
    expected_candidate_profit = total("expected_profit_usd", settled_candidates)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_csv": str(input_path),
        "server_time_utc": iso_ts(server_ts),
        "rows": len(rows),
        "settled_rows": len(settled),
        "pending_rows": len(pending),
        "error_rows": len(errors),
        "candidate_rows": len(candidates),
        "settled_candidate_rows": len(settled_candidates),
        "winning_settled_candidates": sum(1 for row in settled_candidates if safe_bool(row.get("paper_outcome_won"))),
        "settled_candidate_expected_profit_usd": expected_candidate_profit,
        "settled_candidate_realized_profit_usd": candidate_profit,
        "settled_candidate_cost_usd": candidate_cost,
        "settled_candidate_realized_roi_on_cost": candidate_profit / candidate_cost if candidate_cost > EPS else None,
    }


def write_summary_md(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    candidates = [row for row in rows if safe_bool(row.get("candidate"))]
    settled_candidates = [row for row in candidates if row.get("settlement_status") == "settled"]
    lines = [
        "# Polymarket Binance Close Settlement Verification",
        "",
        f"Generated: {summary['generated_at_utc']}",
        "",
        "Read-only settlement check for paper signals. It uses Binance Vision 1-minute candles and does not submit orders.",
        "",
        "## Counts",
        "",
        f"- Input CSV: `{summary['input_csv']}`",
        f"- Binance server time UTC: {summary['server_time_utc']}",
        f"- Rows: {summary['rows']}",
        f"- Settled rows: {summary['settled_rows']}",
        f"- Pending rows: {summary['pending_rows']}",
        f"- Error rows: {summary['error_rows']}",
        f"- Candidate rows: {summary['candidate_rows']}",
        f"- Settled candidate rows: {summary['settled_candidate_rows']}",
        "",
        "## Candidate PnL",
        "",
        f"- Expected PnL on settled candidates: {fmt(summary['settled_candidate_expected_profit_usd'])}",
        f"- Realized paper PnL on settled candidates: {fmt(summary['settled_candidate_realized_profit_usd'])}",
        f"- Realized ROI on settled candidate cost: {fmt(summary['settled_candidate_realized_roi_on_cost'])}",
        f"- Winning settled candidates: {summary['winning_settled_candidates']}",
        "",
    ]
    if settled_candidates:
        lines.extend(
            [
                "## Settled Candidate Rows",
                "",
                "| rank | won | symbol | outcome | close | avg | expected | realized | roi | question |",
                "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for idx, row in enumerate(settled_candidates[:20], start=1):
            lines.append(
                "| {idx} | {won} | {symbol} | {outcome} | {close} | {avg} | {expected} | {realized} | {roi} | {question} |".format(
                    idx=idx,
                    won=row.get("paper_outcome_won", ""),
                    symbol=row.get("symbol", ""),
                    outcome=row.get("outcome", ""),
                    close=fmt(row.get("binance_settle_close")),
                    avg=fmt(row.get("avg_price")),
                    expected=fmt(row.get("expected_profit_usd")),
                    realized=fmt(row.get("paper_realized_profit_usd")),
                    roi=fmt(row.get("paper_realized_roi_on_cost")),
                    question=str(row.get("question", ""))[:90].replace("|", "/"),
                )
            )
    else:
        lines.extend(
            [
                "## Settled Candidate Rows",
                "",
                "No candidate rows have settled yet. Re-run this verifier after `settle_time_utc + 60s`.",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
    input_path = args.signals_csv if args.signals_csv.is_absolute() else REPO_ROOT / args.signals_csv
    rows = read_csv(input_path)
    if args.candidate_only:
        rows = [row for row in rows if safe_bool(row.get("candidate"))]
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = input_path.parent
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir

    server_ts = binance_server_ts(args.http_timeout)
    close_cache: dict[tuple[str, int], float | None] = {}
    verified: list[dict[str, Any]] = []
    for row in rows:
        verified.append(realized_for_row(row, server_ts, close_cache, args.http_timeout))
        if args.sleep_ms > 0 and row is not rows[-1]:
            time.sleep(args.sleep_ms / 1000.0)
    summary = summarize(verified, input_path, server_ts)
    return verified, summary, output_dir


def self_test() -> None:
    above = {"kind": "above_close", "model_threshold": "100", "outcome": "Yes"}
    yes, rule = event_yes_won(above, 101.0, 1.0)
    assert yes is True and rule == "close>100"
    won, _ = outcome_won(above, yes)
    assert won is True

    range_row = {"kind": "range_close", "lower": "100", "upper": "110", "outcome": "No"}
    yes, _ = event_yes_won(range_row, 110.0, 1.0)
    assert yes is False
    won, _ = outcome_won(range_row, yes)
    assert won is True

    below = {"kind": "below_close", "model_threshold": "50", "outcome": "Yes"}
    yes, _ = event_yes_won(below, 50.0, 1.0)
    assert yes is False
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    rows, summary, output_dir = verify(args)
    write_csv(output_dir / "settled_signals.csv", rows)
    write_json(output_dir / "settlement_summary.json", summary)
    write_summary_md(output_dir / "settlement_summary.md", rows, summary)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
