"""Read-only Polymarket mutually-exclusive price-range basket scanner.

This targets events like "XRP price on June 10?" where every market is a
binary range bucket and exactly one bucket should resolve Yes. It scans two
mechanical baskets:

- buy one YES share in every bucket: payout is 1
- buy one NO share in every bucket: payout is N - 1

The scanner uses live CLOB asks and Polymarket taker fees. It never signs or
submits orders.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
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
REPO_ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-12


@dataclass
class RangeLeg:
    market_id: str
    condition_id: str
    question: str
    slug: str
    lower: float | None
    upper: float | None
    yes_token_id: str
    no_token_id: str
    yes_gamma_price: float | None
    no_gamma_price: float | None
    fee_rate: float
    yes_book_best_ask: float | None = None
    yes_target_avg_price: float | None = None
    yes_target_cost_usd: float | None = None
    yes_target_fee_usd: float | None = None
    yes_target_ok: bool = False
    yes_available_shares: float = 0.0
    yes_book_error: str = ""
    no_book_best_ask: float | None = None
    no_target_avg_price: float | None = None
    no_target_cost_usd: float | None = None
    no_target_fee_usd: float | None = None
    no_target_ok: bool = False
    no_available_shares: float = 0.0
    no_book_error: str = ""


@dataclass
class RangeEvent:
    event_id: str
    title: str
    slug: str
    end_date: str
    settlement_source: str
    completeness_error: str
    legs: list[RangeLeg]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/polymarket_range_basket_arbitrage_scan"),
    )
    parser.add_argument("--event-limit", type=int, default=600)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--book-event-limit", type=int, default=5)
    parser.add_argument("--target-shares", type=float, default=100.0)
    parser.add_argument("--min-markets", type=int, default=3)
    parser.add_argument("--max-markets", type=int, default=80)
    parser.add_argument("--min-profit-usd", type=float, default=0.0)
    parser.add_argument("--query", default="")
    parser.add_argument("--slug", action="append", default=[])
    parser.add_argument("--include-discovery-with-slug", action="store_true")
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
        headers={"User-Agent": "finance-chain-polymarket-range-basket-scan/0.1"},
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


def classify_range_bucket(question: str, description: str) -> tuple[str, float | None, float | None]:
    q = question.lower()
    desc = description.lower()
    if "final \"close\"" not in desc and 'final "close"' not in desc:
        return "unsupported", None, None
    if "high price" in desc or "low price" in desc or "immediately resolve" in desc:
        return "unsupported", None, None

    between = re.search(
        r"between\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)\s+and\s+\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)",
        q,
    )
    if between:
        lower = parse_money(between.group(1))
        upper = parse_money(between.group(2))
        if lower is not None and upper is not None and upper > lower:
            return "range", lower, upper

    less = re.search(r"(?:less than|below|under|<)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)", q)
    if less:
        upper = parse_money(less.group(1))
        if upper is not None:
            return "below", None, upper

    above = re.search(r"(?:above|higher than|greater than|>)\s*\$?([0-9][0-9,]*(?:\.[0-9]+)?[km]?)", q)
    if above:
        lower = parse_money(above.group(1))
        if lower is not None:
            return "above", lower, None

    return "unsupported", None, None


def close_enough(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1e-9, 1e-8 * max(1.0, abs(a), abs(b)))


def interval_sort_key(leg: RangeLeg) -> float:
    if leg.lower is None:
        return -float("inf")
    return leg.lower


def completeness_error(legs: list[RangeLeg]) -> str:
    below = [leg for leg in legs if leg.lower is None and leg.upper is not None]
    above = [leg for leg in legs if leg.lower is not None and leg.upper is None]
    ranges = sorted([leg for leg in legs if leg.lower is not None and leg.upper is not None], key=interval_sort_key)
    if len(below) != 1:
        return f"expected_one_below_got_{len(below)}"
    if len(above) != 1:
        return f"expected_one_above_got_{len(above)}"
    if not ranges:
        return "missing_middle_ranges"
    if not close_enough(below[0].upper, ranges[0].lower):
        return "gap_between_below_and_first_range"
    for left, right in zip(ranges, ranges[1:]):
        if not close_enough(left.upper, right.lower):
            return f"gap_or_overlap_between_{left.upper}_and_{right.lower}"
    if not close_enough(ranges[-1].upper, above[0].lower):
        return "gap_between_last_range_and_above"
    return ""


def market_to_leg(market: dict[str, Any], event_description: str) -> RangeLeg | None:
    if market.get("closed") is True or market.get("active") is False:
        return None
    if market.get("enableOrderBook") is False or market.get("acceptingOrders") is False:
        return None
    question = str(market.get("question") or "")
    description = str(market.get("description") or event_description or "")
    kind, lower, upper = classify_range_bucket(question, description)
    if kind == "unsupported":
        return None

    outcomes = [str(x).strip().lower() for x in parse_json_list(market.get("outcomes"))]
    token_ids = [str(x) for x in parse_json_list(market.get("clobTokenIds"))]
    prices = [safe_float(x) for x in parse_json_list(market.get("outcomePrices"))]
    if len(outcomes) < 2 or len(token_ids) < 2:
        return None
    try:
        yes_idx = outcomes.index("yes")
        no_idx = outcomes.index("no")
    except ValueError:
        return None
    if yes_idx >= len(token_ids) or no_idx >= len(token_ids):
        return None

    return RangeLeg(
        market_id=str(market.get("id") or ""),
        condition_id=str(market.get("conditionId") or ""),
        question=question,
        slug=str(market.get("slug") or ""),
        lower=lower,
        upper=upper,
        yes_token_id=token_ids[yes_idx],
        no_token_id=token_ids[no_idx],
        yes_gamma_price=prices[yes_idx] if yes_idx < len(prices) else None,
        no_gamma_price=prices[no_idx] if no_idx < len(prices) else None,
        fee_rate=market_fee_rate(market),
    )


def fetch_events(limit: int, page_size: int, timeout: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < limit:
        rows = http_get_json(
            GAMMA_BASE,
            "/events",
            {
                "limit": min(page_size, limit - len(out)),
                "offset": offset,
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
            },
            timeout,
        )
        if not isinstance(rows, list) or not rows:
            break
        out.extend(row for row in rows if isinstance(row, dict))
        offset += len(rows)
        if len(rows) < page_size:
            break
    return out


def fetch_event_by_slug(slug: str, timeout: float) -> dict[str, Any] | None:
    rows = http_get_json(GAMMA_BASE, "/events", {"slug": slug}, timeout)
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def fetch_event_detail(event: dict[str, Any], timeout: float) -> dict[str, Any]:
    slug = str(event.get("slug") or "")
    if not slug:
        return event
    detail = fetch_event_by_slug(slug, timeout)
    if detail is not None and len(detail.get("markets") or []) >= len(event.get("markets") or []):
        return detail
    return event


def build_range_events(args: argparse.Namespace) -> list[RangeEvent]:
    seen: set[str] = set()
    source_events: list[dict[str, Any]] = []
    for slug in args.slug:
        event = fetch_event_by_slug(slug, args.http_timeout)
        if event is not None:
            source_events.append(event)
    if not args.slug or args.include_discovery_with_slug:
        source_events.extend(fetch_events(args.event_limit, args.page_size, args.http_timeout))

    query = args.query.lower().strip()
    events: list[RangeEvent] = []
    for raw_event in source_events:
        event_id = str(raw_event.get("id") or raw_event.get("slug") or "")
        if event_id in seen:
            continue
        seen.add(event_id)
        blob = " ".join(
            [
                str(raw_event.get("title") or ""),
                str(raw_event.get("slug") or ""),
                str(raw_event.get("description") or ""),
            ]
        ).lower()
        if query and query not in blob:
            continue
        event = fetch_event_detail(raw_event, args.http_timeout)
        markets = [m for m in (event.get("markets") or []) if isinstance(m, dict)]
        if len(markets) < args.min_markets or len(markets) > args.max_markets:
            continue
        description = str(event.get("description") or "")
        legs = [leg for leg in (market_to_leg(m, description) for m in markets) if leg is not None]
        if len(legs) < args.min_markets:
            continue
        err = completeness_error(legs)
        if err:
            continue
        events.append(
            RangeEvent(
                event_id=str(event.get("id") or ""),
                title=str(event.get("title") or ""),
                slug=str(event.get("slug") or ""),
                end_date=str(event.get("endDate") or ""),
                settlement_source="binance_final_close",
                completeness_error=err,
                legs=sorted(legs, key=interval_sort_key),
            )
        )
    return events


def taker_fee_for_fill(shares: float, price: float, fee_rate: float) -> float:
    return shares * fee_rate * price * (1.0 - price)


def sorted_asks(levels: list[dict[str, Any]]) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for level in levels:
        price = safe_float(level.get("price"))
        size = safe_float(level.get("size"))
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        out.append({"price": price, "size": size})
    out.sort(key=lambda item: item["price"])
    return out


def consume_asks_for_shares(levels: list[dict[str, Any]], shares: float, fee_rate: float) -> dict[str, Any]:
    remaining = shares
    cost = 0.0
    fee = 0.0
    available = 0.0
    best_ask = None
    for level in sorted_asks(levels):
        if best_ask is None:
            best_ask = level["price"]
        available += level["size"]
        if remaining <= EPS:
            continue
        take = min(remaining, level["size"])
        cost += take * level["price"]
        fee += taker_fee_for_fill(take, level["price"], fee_rate)
        remaining -= take
    ok = remaining <= EPS
    return {
        "ok": ok,
        "best_ask": best_ask,
        "avg_price": cost / shares if ok and shares > EPS else None,
        "cost_usd": cost if ok else None,
        "fee_usd": fee if ok else None,
        "available_shares": available,
    }


def collect_book(token_id: str, target_shares: float, fee_rate: float, timeout: float) -> dict[str, Any]:
    book = http_get_json(CLOB_BASE, "/book", {"token_id": token_id}, timeout)
    return consume_asks_for_shares(book.get("asks") or [], target_shares, fee_rate)


def analyze_live_books(events: list[RangeEvent], args: argparse.Namespace) -> None:
    for event in events[: args.book_event_limit]:
        for leg in event.legs:
            try:
                yes = collect_book(leg.yes_token_id, args.target_shares, leg.fee_rate, args.http_timeout)
                leg.yes_book_best_ask = yes.get("best_ask")
                leg.yes_target_avg_price = yes.get("avg_price")
                leg.yes_target_cost_usd = yes.get("cost_usd")
                leg.yes_target_fee_usd = yes.get("fee_usd")
                leg.yes_target_ok = yes.get("ok") is True
                leg.yes_available_shares = float(yes.get("available_shares") or 0.0)
            except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
                leg.yes_book_error = type(exc).__name__
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)
            try:
                no = collect_book(leg.no_token_id, args.target_shares, leg.fee_rate, args.http_timeout)
                leg.no_book_best_ask = no.get("best_ask")
                leg.no_target_avg_price = no.get("avg_price")
                leg.no_target_cost_usd = no.get("cost_usd")
                leg.no_target_fee_usd = no.get("fee_usd")
                leg.no_target_ok = no.get("ok") is True
                leg.no_available_shares = float(no.get("available_shares") or 0.0)
            except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
                leg.no_book_error = type(exc).__name__
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)


def gamma_edge(prices: list[float | None], payout: float) -> float | None:
    if any(price is None for price in prices):
        return None
    return payout - sum(float(price or 0.0) for price in prices)


def event_summary_row(event: RangeEvent, target_shares: float, min_profit_usd: float) -> dict[str, Any]:
    n = len(event.legs)
    yes_gamma = gamma_edge([leg.yes_gamma_price for leg in event.legs], 1.0)
    no_gamma = gamma_edge([leg.no_gamma_price for leg in event.legs], float(n - 1))

    yes_complete = all(leg.yes_target_ok for leg in event.legs)
    no_complete = all(leg.no_target_ok for leg in event.legs)
    yes_cost = sum(float(leg.yes_target_cost_usd or 0.0) for leg in event.legs) if yes_complete else None
    yes_fee = sum(float(leg.yes_target_fee_usd or 0.0) for leg in event.legs) if yes_complete else None
    no_cost = sum(float(leg.no_target_cost_usd or 0.0) for leg in event.legs) if no_complete else None
    no_fee = sum(float(leg.no_target_fee_usd or 0.0) for leg in event.legs) if no_complete else None
    yes_profit = target_shares - yes_cost - yes_fee if yes_cost is not None and yes_fee is not None else None
    no_profit = (n - 1) * target_shares - no_cost - no_fee if no_cost is not None and no_fee is not None else None
    yes_best_sum = sum(float(leg.yes_book_best_ask or 0.0) for leg in event.legs) if all(leg.yes_book_best_ask is not None for leg in event.legs) else None
    no_best_sum = sum(float(leg.no_book_best_ask or 0.0) for leg in event.legs) if all(leg.no_book_best_ask is not None for leg in event.legs) else None
    best_direction = ""
    best_profit = None
    for direction, profit in [("buy_all_yes", yes_profit), ("buy_all_no", no_profit)]:
        if profit is None:
            continue
        if best_profit is None or profit > best_profit:
            best_profit = profit
            best_direction = direction

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_id": event.event_id,
        "title": event.title,
        "slug": event.slug,
        "end_date": event.end_date,
        "settlement_source": event.settlement_source,
        "num_buckets": n,
        "target_shares_per_bucket": target_shares,
        "buy_all_yes_gamma_edge_cents": yes_gamma * 100.0 if yes_gamma is not None else None,
        "buy_all_no_gamma_edge_cents": no_gamma * 100.0 if no_gamma is not None else None,
        "buy_all_yes_complete": yes_complete,
        "buy_all_yes_best_ask_sum": yes_best_sum,
        "buy_all_yes_cost_usd": yes_cost,
        "buy_all_yes_fee_usd": yes_fee,
        "buy_all_yes_profit_usd": yes_profit,
        "buy_all_yes_edge_cents": (yes_profit / target_shares) * 100.0 if yes_profit is not None and target_shares > EPS else None,
        "buy_all_yes_min_available_shares": min((leg.yes_available_shares for leg in event.legs), default=0.0),
        "buy_all_yes_error_count": sum(1 for leg in event.legs if leg.yes_book_error),
        "buy_all_yes_candidate": yes_profit is not None and yes_profit >= min_profit_usd,
        "buy_all_no_complete": no_complete,
        "buy_all_no_best_ask_sum": no_best_sum,
        "buy_all_no_cost_usd": no_cost,
        "buy_all_no_fee_usd": no_fee,
        "buy_all_no_profit_usd": no_profit,
        "buy_all_no_edge_cents": (no_profit / ((n - 1) * target_shares)) * 100.0 if no_profit is not None and n > 1 else None,
        "buy_all_no_min_available_shares": min((leg.no_available_shares for leg in event.legs), default=0.0),
        "buy_all_no_error_count": sum(1 for leg in event.legs if leg.no_book_error),
        "buy_all_no_candidate": no_profit is not None and no_profit >= min_profit_usd,
        "best_direction": best_direction,
        "best_profit_usd": best_profit,
    }


def leg_rows(event: RangeEvent) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for leg in event.legs:
        rows.append(
            {
                "event_id": event.event_id,
                "event_title": event.title,
                "event_slug": event.slug,
                "market_id": leg.market_id,
                "condition_id": leg.condition_id,
                "question": leg.question,
                "slug": leg.slug,
                "lower": leg.lower,
                "upper": leg.upper,
                "fee_rate": leg.fee_rate,
                "yes_token_id": leg.yes_token_id,
                "yes_gamma_price": leg.yes_gamma_price,
                "yes_book_best_ask": leg.yes_book_best_ask,
                "yes_target_avg_price": leg.yes_target_avg_price,
                "yes_target_cost_usd": leg.yes_target_cost_usd,
                "yes_target_fee_usd": leg.yes_target_fee_usd,
                "yes_target_ok": leg.yes_target_ok,
                "yes_available_shares": leg.yes_available_shares,
                "yes_book_error": leg.yes_book_error,
                "no_token_id": leg.no_token_id,
                "no_gamma_price": leg.no_gamma_price,
                "no_book_best_ask": leg.no_book_best_ask,
                "no_target_avg_price": leg.no_target_avg_price,
                "no_target_cost_usd": leg.no_target_cost_usd,
                "no_target_fee_usd": leg.no_target_fee_usd,
                "no_target_ok": leg.no_target_ok,
                "no_available_shares": leg.no_available_shares,
                "no_book_error": leg.no_book_error,
            }
        )
    return rows


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


def write_summary_md(path: Path, rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    yes_candidates = [row for row in rows if row.get("buy_all_yes_candidate") is True]
    no_candidates = [row for row in rows if row.get("buy_all_no_candidate") is True]
    lines = [
        "# Polymarket Range Basket Arbitrage Scan",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Read-only scan for exhaustive mutually-exclusive price-range events. No orders are signed or submitted.",
        "",
        "## Math",
        "",
        "For `N` exhaustive buckets where exactly one bucket resolves Yes:",
        "",
        "```text",
        "buy_all_yes_profit = Q - sum(yes_cost_i) - sum(yes_fee_i)",
        "buy_all_no_profit  = (N - 1) * Q - sum(no_cost_i) - sum(no_fee_i)",
        "fee_i = shares_i * feeRate_i * price_i * (1 - price_i)",
        "```",
        "",
        "The interval parser requires a complete chain: `<a`, `a-b`, ..., `>z`.",
        "",
        "## Counts",
        "",
        f"- Range events: {len(rows)}",
        f"- Live book events requested: {args.book_event_limit}",
        f"- Target shares per bucket: {args.target_shares}",
        f"- Buy-all-YES non-negative candidates: {len(yes_candidates)}",
        f"- Buy-all-NO non-negative candidates: {len(no_candidates)}",
        "",
        "## Events",
        "",
        "| rank | buckets | yes_profit | yes_edge_c | no_profit | no_edge_c | best | title |",
        "|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for idx, row in enumerate(rows[:30], start=1):
        lines.append(
            "| {idx} | {buckets} | {yes_profit} | {yes_edge} | {no_profit} | {no_edge} | {best} | {title} |".format(
                idx=idx,
                buckets=row.get("num_buckets", ""),
                yes_profit=fmt(row.get("buy_all_yes_profit_usd")),
                yes_edge=fmt(row.get("buy_all_yes_edge_cents")),
                no_profit=fmt(row.get("buy_all_no_profit_usd")),
                no_edge=fmt(row.get("buy_all_no_edge_cents")),
                best=row.get("best_direction", ""),
                title=str(row.get("title", ""))[:90].replace("|", "/"),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    desc = 'This market will resolve according to the Binance final "Close" price.'
    assert classify_range_bucket("Will XRP be less than $0.80?", desc) == ("below", None, 0.8)
    assert classify_range_bucket("Will XRP be between $0.80 and $0.90?", desc) == ("range", 0.8, 0.9)
    assert classify_range_bucket("Will XRP be above $1.70?", desc) == ("above", 1.7, None)
    legs = [
        RangeLeg("", "", "", "", None, 0.8, "y", "n", None, None, 0.07),
        RangeLeg("", "", "", "", 0.8, 0.9, "y", "n", None, None, 0.07),
        RangeLeg("", "", "", "", 0.9, 1.0, "y", "n", None, None, 0.07),
        RangeLeg("", "", "", "", 1.0, None, "y", "n", None, None, 0.07),
    ]
    assert completeness_error(legs) == ""
    broken = legs[:2] + [RangeLeg("", "", "", "", 1.1, None, "y", "n", None, None, 0.07)]
    assert completeness_error(broken) != ""
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    events = build_range_events(args)
    analyze_live_books(events, args)
    rows = [event_summary_row(event, args.target_shares, args.min_profit_usd) for event in events]
    rows.sort(key=lambda row: safe_float(row.get("best_profit_usd")) or -1e18, reverse=True)
    legs = [leg_row for event in events for leg_row in leg_rows(event)]
    write_csv(output_dir / "range_events.csv", rows)
    write_csv(output_dir / "range_legs.csv", legs)
    write_json(
        output_dir / "summary.json",
        {
            "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "events": len(events),
            "buy_all_yes_candidates": sum(1 for row in rows if row.get("buy_all_yes_candidate") is True),
            "buy_all_no_candidates": sum(1 for row in rows if row.get("buy_all_no_candidate") is True),
            "top_rows": rows[:20],
        },
    )
    write_summary_md(output_dir / "summary.md", rows, args)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
