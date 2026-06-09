"""Polymarket crypto close-price signal scanner using Binance Vision.

This read-only scanner targets Polymarket markets that settle from Binance
1-minute candle close prices, such as:

- "Bitcoin above ___ on June 8?"
- "Solana price on June 8?"
- "Bitcoin Up or Down on June 8?"

It compares live CLOB asks against a simple Binance-based fair probability
model. The output is a paper signal table, not an execution path.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
BINANCE_DATA_BASE = "https://data-api.binance.vision"
REPO_ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-12

SYMBOL_BY_TEXT = {
    "bitcoin": "BTCUSDT",
    "btc": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "eth": "ETHUSDT",
    "solana": "SOLUSDT",
    "sol": "SOLUSDT",
    "xrp": "XRPUSDT",
    "dogecoin": "DOGEUSDT",
    "doge": "DOGEUSDT",
    "cardano": "ADAUSDT",
    "ada": "ADAUSDT",
    "bnb": "BNBUSDT",
}


@dataclass
class MarketCase:
    event_id: str
    event_title: str
    event_slug: str
    market_id: str
    question: str
    slug: str
    description: str
    end_ts: int
    symbol: str
    kind: str
    lower: float | None
    upper: float | None
    threshold: float | None
    outcomes: list[str]
    token_ids: list[str]
    fee_rates: list[float]


@dataclass
class BinanceState:
    symbol: str
    server_ts: int
    price: float
    stdev_logret_1m: float
    n_returns: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/polymarket_binance_close_signal_scan"),
    )
    parser.add_argument("--event-limit", type=int, default=120)
    parser.add_argument("--market-limit", type=int, default=80)
    parser.add_argument("--book-token-limit", type=int, default=80)
    parser.add_argument("--target-notional-usd", type=float, default=100.0)
    parser.add_argument("--vol-lookback-minutes", type=int, default=180)
    parser.add_argument("--min-minutes-to-settle", type=float, default=0.0)
    parser.add_argument("--max-hours-to-settle", type=float, default=30.0)
    parser.add_argument("--min-edge-cents", type=float, default=0.0)
    parser.add_argument("--min-expected-profit-usd", type=float, default=0.0)
    parser.add_argument("--min-model-prob", type=float, default=0.0)
    parser.add_argument("--query", default="")
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
        headers={"User-Agent": "finance-chain-polymarket-binance-close-scan/0.1"},
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


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_ts(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def parse_fee_schedule(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def market_fee_rate(market: dict[str, Any]) -> float:
    if market.get("feesEnabled") is False:
        return 0.0
    schedule = parse_fee_schedule(market.get("feeSchedule"))
    rate = safe_float(schedule.get("rate"))
    if rate is not None and rate >= 0:
        return rate
    return 0.07 if "crypto" in str(market.get("feeType") or "").lower() else 0.0


def infer_symbol(*texts: str) -> str | None:
    blob = " ".join(texts).lower()
    for key, symbol in SYMBOL_BY_TEXT.items():
        if re.search(rf"\b{re.escape(key)}\b", blob):
            return symbol
    for symbol in set(SYMBOL_BY_TEXT.values()):
        if symbol.replace("USDT", "/USDT").lower() in blob or symbol.lower() in blob:
            return symbol
    return None


def parse_money(raw: str) -> float | None:
    text = raw.strip().lower().replace(",", "")
    mult = 1.0
    if text.endswith("k"):
        mult = 1000.0
        text = text[:-1]
    elif text.endswith("m"):
        mult = 1_000_000.0
        text = text[:-1]
    value = safe_float(text)
    return value * mult if value is not None else None


def classify_market(question: str, description: str, outcomes: list[str]) -> tuple[str, float | None, float | None, float | None]:
    q = question.lower()
    desc = description.lower()
    outcome_blob = " ".join(outcomes).lower()

    if "final \"close\"" not in desc and 'final "close"' not in desc:
        return "unsupported", None, None, None
    if "high price" in desc or "low price" in desc or "immediately resolve" in desc:
        return "unsupported", None, None, None

    between = re.search(r"between\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)\s+and\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)", q)
    if between:
        lo = parse_money(between.group(1))
        hi = parse_money(between.group(2))
        if lo is not None and hi is not None and hi > lo:
            return "range_close", lo, hi, None

    less = re.search(r"(?:less than|below|under|<)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)", q)
    if less:
        threshold = parse_money(less.group(1))
        if threshold is not None:
            return "below_close", None, None, threshold

    above = re.search(r"(?:above|higher than|greater than|>)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)", q)
    if above:
        threshold = parse_money(above.group(1))
        if threshold is not None:
            return "above_close", None, None, threshold

    if "up or down" in q or ("up" in outcome_blob and "down" in outcome_blob):
        return "updown_close", None, None, None

    return "unsupported", None, None, None


def fetch_events(limit: int, timeout: float) -> list[dict[str, Any]]:
    return http_get_json(
        GAMMA_BASE,
        "/events",
        {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        },
        timeout,
    )


def build_market_cases(args: argparse.Namespace, now_ts: int) -> list[MarketCase]:
    query = args.query.lower().strip()
    cases: list[MarketCase] = []
    for event in fetch_events(args.event_limit, args.http_timeout):
        event_title = str(event.get("title") or "")
        event_slug = str(event.get("slug") or "")
        if query and query not in f"{event_title} {event_slug}".lower():
            continue
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            if market.get("closed") is True or market.get("active") is False:
                continue
            question = str(market.get("question") or "")
            description = str(market.get("description") or event.get("description") or "")
            outcomes = [str(x) for x in parse_json_list(market.get("outcomes"))]
            token_ids = [str(x) for x in parse_json_list(market.get("clobTokenIds"))]
            end_ts = parse_ts(str(market.get("endDate") or event.get("endDate") or ""))
            symbol = infer_symbol(question, description, event_title, event_slug)
            kind, lower, upper, threshold = classify_market(question, description, outcomes)
            if kind == "unsupported" or end_ts is None or symbol is None or len(token_ids) < 2 or len(outcomes) < 2:
                continue
            minutes_to_settle = (end_ts - now_ts) / 60.0
            if minutes_to_settle < args.min_minutes_to_settle or minutes_to_settle > args.max_hours_to_settle * 60.0:
                continue
            fee_rate = market_fee_rate(market)
            cases.append(
                MarketCase(
                    event_id=str(event.get("id") or ""),
                    event_title=event_title,
                    event_slug=event_slug,
                    market_id=str(market.get("id") or market.get("conditionId") or ""),
                    question=question,
                    slug=str(market.get("slug") or ""),
                    description=description,
                    end_ts=end_ts,
                    symbol=symbol,
                    kind=kind,
                    lower=lower,
                    upper=upper,
                    threshold=threshold,
                    outcomes=outcomes,
                    token_ids=token_ids,
                    fee_rates=[fee_rate for _ in token_ids],
                )
            )
            if len(cases) >= args.market_limit:
                return cases
    return cases


def binance_server_ts(timeout: float) -> int:
    body = http_get_json(BINANCE_DATA_BASE, "/api/v3/time", None, timeout)
    return int(body["serverTime"]) // 1000


def fetch_binance_klines(symbol: str, limit: int, timeout: float, start_ms: int | None = None) -> list[list[Any]]:
    params: dict[str, Any] = {"symbol": symbol, "interval": "1m", "limit": limit}
    if start_ms is not None:
        params["startTime"] = start_ms
    return http_get_json(BINANCE_DATA_BASE, "/api/v3/klines", params, timeout)


def fetch_binance_state(symbol: str, server_ts: int, lookback: int, timeout: float) -> BinanceState:
    ticker = http_get_json(BINANCE_DATA_BASE, "/api/v3/ticker/price", {"symbol": symbol}, timeout)
    price = float(ticker["price"])
    klines = fetch_binance_klines(symbol, max(lookback, 10), timeout)
    closes: list[float] = []
    for row in klines:
        close = safe_float(row[4] if len(row) > 4 else None)
        if close is not None and close > 0:
            closes.append(close)
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0 and closes[i] > 0]
    stdev = statistics.pstdev(rets) if len(rets) >= 2 else 0.0
    return BinanceState(symbol=symbol, server_ts=server_ts, price=price, stdev_logret_1m=stdev, n_returns=len(rets))


def historical_close(symbol: str, ts: int, timeout: float) -> float | None:
    # Polymarket rules refer to the Binance 1m candle at the specified minute.
    rows = fetch_binance_klines(symbol, 1, timeout, start_ms=ts * 1000)
    if not rows:
        return None
    return safe_float(rows[0][4] if len(rows[0]) > 4 else None)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def prob_above(current_price: float, threshold: float, stdev_1m: float, horizon_seconds: float) -> float:
    if threshold <= 0 or current_price <= 0:
        return 0.5
    if horizon_seconds <= 0 or stdev_1m <= EPS:
        return 1.0 if current_price > threshold else 0.0
    sigma = stdev_1m * math.sqrt(max(horizon_seconds, 0.0) / 60.0)
    if sigma <= EPS:
        return 1.0 if current_price > threshold else 0.0
    z = (math.log(current_price) - math.log(threshold)) / sigma
    return max(0.0, min(1.0, norm_cdf(z)))


def prob_between(current_price: float, lower: float, upper: float, stdev_1m: float, horizon_seconds: float) -> float:
    if lower <= 0 or upper <= lower or current_price <= 0:
        return 0.0
    if horizon_seconds <= 0 or stdev_1m <= EPS:
        return 1.0 if lower <= current_price < upper else 0.0
    p_lo = prob_above(current_price, lower, stdev_1m, horizon_seconds)
    p_hi = prob_above(current_price, upper, stdev_1m, horizon_seconds)
    return max(0.0, min(1.0, p_lo - p_hi))


def model_yes_probability(case: MarketCase, state: BinanceState, timeout: float) -> tuple[float | None, str, float | None]:
    horizon = case.end_ts - state.server_ts
    if case.kind == "above_close" and case.threshold is not None:
        return prob_above(state.price, case.threshold, state.stdev_logret_1m, horizon), "lognormal_close", case.threshold
    if case.kind == "below_close" and case.threshold is not None:
        return 1.0 - prob_above(state.price, case.threshold, state.stdev_logret_1m, horizon), "lognormal_close", case.threshold
    if case.kind == "range_close" and case.lower is not None and case.upper is not None:
        return prob_between(state.price, case.lower, case.upper, state.stdev_logret_1m, horizon), "lognormal_close", None
    if case.kind == "updown_close":
        prev_close = historical_close(case.symbol, case.end_ts - 24 * 3600, timeout)
        if prev_close is None:
            return None, "missing_previous_close", None
        return prob_above(state.price, prev_close, state.stdev_logret_1m, horizon), "previous_noon_close", prev_close
    return None, "unsupported", None


def sorted_asks(levels: list[dict[str, Any]]) -> list[dict[str, float]]:
    out = []
    for level in levels:
        price = safe_float(level.get("price"))
        size = safe_float(level.get("size"))
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        out.append({"price": price, "size": size})
    out.sort(key=lambda x: x["price"])
    return out


def consume_notional(levels: list[dict[str, Any]], notional: float, fee_rate: float) -> dict[str, Any]:
    remaining = notional
    cost = 0.0
    shares = 0.0
    fee = 0.0
    best_ask = None
    available_notional = 0.0
    for level in sorted_asks(levels):
        if best_ask is None:
            best_ask = level["price"]
        level_notional = level["price"] * level["size"]
        available_notional += level_notional
        if remaining <= EPS:
            continue
        take_notional = min(remaining, level_notional)
        take_shares = take_notional / level["price"]
        cost += take_notional
        shares += take_shares
        fee += take_shares * fee_rate * level["price"] * (1.0 - level["price"])
        remaining -= take_notional
    ok = remaining <= EPS
    return {
        "ok": ok,
        "best_ask": best_ask,
        "avg_price": cost / shares if ok and shares > EPS else None,
        "shares": shares if ok else None,
        "cost_usd": cost if ok else None,
        "fee_usd": fee if ok else None,
        "available_notional_usd": available_notional,
    }


def fetch_book_fill(token_id: str, notional: float, fee_rate: float, timeout: float) -> dict[str, Any]:
    try:
        book = http_get_json(CLOB_BASE, "/book", {"token_id": token_id}, timeout)
        return {**consume_notional(book.get("asks") or [], notional, fee_rate), "book_error": ""}
    except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
        return {"ok": False, "book_error": type(exc).__name__}


def side_probability(case: MarketCase, yes_prob: float, side_index: int) -> float:
    if side_index == 0:
        return yes_prob
    return 1.0 - yes_prob


def scan(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    server_ts = binance_server_ts(args.http_timeout)
    cases = build_market_cases(args, server_ts)
    states: dict[str, BinanceState] = {}
    for symbol in sorted({case.symbol for case in cases}):
        states[symbol] = fetch_binance_state(symbol, server_ts, args.vol_lookback_minutes, args.http_timeout)
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000.0)

    rows: list[dict[str, Any]] = []
    books_used = 0
    for case in cases:
        state = states.get(case.symbol)
        if state is None:
            continue
        yes_prob, model_source, model_threshold = model_yes_probability(case, state, args.http_timeout)
        if yes_prob is None:
            continue
        for idx, token_id in enumerate(case.token_ids[:2]):
            if books_used >= args.book_token_limit:
                fill = {"ok": False, "book_error": "book_token_limit"}
            else:
                fill = fetch_book_fill(token_id, args.target_notional_usd, case.fee_rates[idx], args.http_timeout)
                books_used += 1
                if args.sleep_ms > 0:
                    time.sleep(args.sleep_ms / 1000.0)
            prob = side_probability(case, yes_prob, idx)
            shares = safe_float(fill.get("shares"))
            cost = safe_float(fill.get("cost_usd"))
            fee = safe_float(fill.get("fee_usd"))
            expected_profit = None
            roi = None
            edge_cents = None
            avg_price = safe_float(fill.get("avg_price"))
            if shares is not None and cost is not None and fee is not None and avg_price is not None:
                expected_profit = shares * prob - cost - fee
                roi = expected_profit / cost if cost > EPS else None
                fee_per_share = fee / shares if shares > EPS else 0.0
                edge_cents = (prob - avg_price - fee_per_share) * 100.0
            minutes_to_settle = (case.end_ts - server_ts) / 60.0
            rows.append(
                {
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "server_time_utc": datetime.fromtimestamp(server_ts, timezone.utc).isoformat(),
                    "event_id": case.event_id,
                    "event_title": case.event_title,
                    "event_slug": case.event_slug,
                    "market_id": case.market_id,
                    "question": case.question,
                    "slug": case.slug,
                    "symbol": case.symbol,
                    "kind": case.kind,
                    "outcome": case.outcomes[idx] if idx < len(case.outcomes) else str(idx),
                    "token_id": token_id,
                    "settle_time_utc": datetime.fromtimestamp(case.end_ts, timezone.utc).isoformat(),
                    "minutes_to_settle": minutes_to_settle,
                    "binance_price": state.price,
                    "model_threshold": model_threshold,
                    "lower": case.lower,
                    "upper": case.upper,
                    "stdev_logret_1m": state.stdev_logret_1m,
                    "vol_lookback_returns": state.n_returns,
                    "model_source": model_source,
                    "model_prob": prob,
                    "fee_rate": case.fee_rates[idx],
                    "target_notional_usd": args.target_notional_usd,
                    "book_ok": fill.get("ok") is True,
                    "best_ask": fill.get("best_ask"),
                    "avg_price": avg_price,
                    "shares": shares,
                    "fee_usd": fee,
                    "available_notional_usd": fill.get("available_notional_usd"),
                    "expected_profit_usd": expected_profit,
                    "roi_on_cost": roi,
                    "edge_cents": edge_cents,
                    "candidate": (
                        fill.get("ok") is True
                        and edge_cents is not None
                        and expected_profit is not None
                        and edge_cents >= args.min_edge_cents
                        and expected_profit >= args.min_expected_profit_usd
                        and prob >= args.min_model_prob
                    ),
                    "book_error": fill.get("book_error", ""),
                }
            )
    rows.sort(
        key=lambda row: (
            row.get("candidate") is True,
            safe_float(row.get("expected_profit_usd")) or -1e9,
            safe_float(row.get("edge_cents")) or -1e9,
        ),
        reverse=True,
    )
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "server_time_utc": datetime.fromtimestamp(server_ts, timezone.utc).isoformat(),
        "cases": len(cases),
        "symbols": sorted(states.keys()),
        "rows": len(rows),
        "candidates": sum(1 for row in rows if row.get("candidate") is True),
        "books_used": min(books_used, args.book_token_limit),
    }
    return rows, summary


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
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def write_summary_md(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any], args: argparse.Namespace) -> None:
    candidates = [row for row in rows if row.get("candidate") is True]
    lines = [
        "# Polymarket Binance Close Signal Scan",
        "",
        f"Generated: {summary['generated_at_utc']}",
        "",
        "Read-only paper signal scan. Binance reference data is from `data-api.binance.vision`, because `api.binance.com` returned HTTP 451 from this environment.",
        "",
        "## Model",
        "",
        "For each Binance-settled close-price market, the scanner estimates:",
        "",
        "```text",
        "P(close_T > K) from current Binance price and recent 1m log-return volatility",
        "expected_profit = shares * model_probability - fill_cost - taker_fee",
        "```",
        "",
        "This is a rough short-horizon model; positive rows require forward-paper settlement before live use.",
        "",
        "## Counts",
        "",
        f"- Server time UTC: {summary['server_time_utc']}",
        f"- Parsed markets: {summary['cases']}",
        f"- Signal rows: {summary['rows']}",
        f"- Candidate rows: {summary['candidates']}",
        f"- Symbols: {', '.join(summary['symbols'])}",
        f"- Book token limit: {args.book_token_limit}",
        f"- Target notional USD: {args.target_notional_usd}",
        "",
        "## Top Rows",
        "",
        "| rank | cand | symbol | outcome | minutes | prob | avg | edge_c | exp_pnl | roi | question |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(rows[:20], start=1):
        lines.append(
            "| {idx} | {cand} | {symbol} | {outcome} | {minutes} | {prob} | {avg} | {edge} | {pnl} | {roi} | {question} |".format(
                idx=idx,
                cand=row.get("candidate", ""),
                symbol=row.get("symbol", ""),
                outcome=row.get("outcome", ""),
                minutes=fmt(safe_float(row.get("minutes_to_settle"))),
                prob=fmt(safe_float(row.get("model_prob"))),
                avg=fmt(safe_float(row.get("avg_price"))),
                edge=fmt(safe_float(row.get("edge_cents"))),
                pnl=fmt(safe_float(row.get("expected_profit_usd"))),
                roi=fmt(safe_float(row.get("roi_on_cost"))),
                question=str(row.get("question", ""))[:90].replace("|", "/"),
            )
        )
    if candidates:
        lines.extend(["", "## Candidate Rule", ""])
        lines.append(
            f"Rows require `edge_cents >= {args.min_edge_cents}`, `expected_profit_usd >= {args.min_expected_profit_usd}`, and `model_prob >= {args.min_model_prob}`."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    kind, lo, hi, th = classify_market(
        "Will the price of Solana be between $30 and $40 on June 8?",
        'This market will resolve according to the final "Close" price.',
        ["Yes", "No"],
    )
    assert kind == "range_close" and lo == 30 and hi == 40 and th is None
    kind, _lo, _hi, th = classify_market(
        "Will the price of Bitcoin be above $64,000 on June 8?",
        'This market will resolve to "Yes" if the Binance 1 minute candle has a final "Close" price higher.',
        ["Yes", "No"],
    )
    assert kind == "above_close" and th == 64000
    p = prob_above(105.0, 100.0, 0.001, 60.0)
    assert p > 0.99
    fill = consume_notional([{"price": "0.40", "size": "100"}, {"price": "0.50", "size": "100"}], 60.0, 0.0)
    assert fill["ok"] is True
    assert round(float(fill["avg_price"]), 8) == round(60.0 / 140.0, 8)
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    rows, summary = scan(args)
    write_csv(output_dir / "signals.csv", rows)
    write_json(
        output_dir / "summary.json",
        {
            "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            **summary,
            "top_rows": rows[:20],
        },
    )
    write_summary_md(output_dir / "summary.md", rows, summary, args)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
