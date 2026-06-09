"""Public Polymarket wallet copyability factor probe.

This is a read-only research scanner. It only calls public market/data
endpoints, writes local output tables, and never signs or submits orders.

The v0 copy-decay backtest uses the next public trade on the same outcome
token as a price proxy. That is intentionally conservative in labeling:
historical order book depth is not assumed unless we collected it ourselves.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
import time
from http.client import RemoteDisconnected
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATA_BASE = "https://data-api.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
REPO_ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-12
MIN_SHARPE_STD_CENTS = 0.25


@dataclass(frozen=True)
class Trade:
    wallet: str
    side: str
    asset: str
    condition_id: str
    size: float
    price: float
    timestamp: int
    title: str
    slug: str
    event_slug: str
    outcome: str
    outcome_index: int | None
    name: str
    pseudonym: str
    tx: str
    category: str = "other"

    @property
    def notional(self) -> float:
        return self.size * self.price

    @property
    def signed_side(self) -> int:
        return 1 if self.side.upper() == "BUY" else -1


@dataclass
class MarketMeta:
    condition_id: str
    market_id: str = ""
    event_id: str = ""
    title: str = ""
    event_title: str = ""
    slug: str = ""
    event_slug: str = ""
    category: str = "other"
    description: str = ""
    end_date: str = ""
    liquidity: float | None = None
    volume24h: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    outcomes: list[str] = field(default_factory=list)
    token_ids: list[str] = field(default_factory=list)
    token_to_outcome: dict[str, str] = field(default_factory=dict)


@dataclass
class BookStats:
    asset: str
    condition_id: str = ""
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    bid_depth_usd: float | None = None
    ask_depth_usd: float | None = None
    capacity: dict[float, dict[str, float | bool | None]] = field(default_factory=dict)
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/polymarket_wallet_factor_probe"),
    )
    parser.add_argument("--trade-limit", type=int, default=10_000)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--top-wallets", type=int, default=80)
    parser.add_argument("--wallet-history-wallets", type=int, default=60)
    parser.add_argument("--wallet-history-limit", type=int, default=300)
    parser.add_argument("--min-wallet-buy-trades", type=int, default=3)
    parser.add_argument("--min-category-trades", type=int, default=2)
    parser.add_argument("--gamma-event-limit", type=int, default=80)
    parser.add_argument("--book-token-limit", type=int, default=120)
    parser.add_argument("--candidate-lookback-hours", type=float, default=24.0)
    parser.add_argument("--delay-seconds", default="0,30,120,300,1800")
    parser.add_argument("--capacity-notional", default="1000,5000,10000")
    parser.add_argument("--max-capacity-slippage-cents", type=float, default=2.0)
    parser.add_argument("--allow-unknown-capacity", action="store_true")
    parser.add_argument("--max-one-hit-penalty", type=float, default=0.75)
    parser.add_argument("--min-5m-edge-cents", type=float, default=0.0)
    parser.add_argument("--http-timeout", type=float, default=20.0)
    parser.add_argument("--sleep-ms", type=int, default=80)
    parser.add_argument("--skip-books", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def http_get_json(
    base: str,
    path: str,
    params: dict[str, Any] | None,
    timeout: float,
) -> Any:
    query = ""
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        query = "?" + urlencode(clean, doseq=True)
    req = Request(
        base.rstrip("/") + "/" + path.lstrip("/") + query,
        headers={"User-Agent": "finance-chain-polymarket-wallet-probe/0.1"},
        method="GET",
    )
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)
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
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(out):
        return out
    return None


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def classify_category(*texts: str) -> str:
    text = " ".join(t for t in texts if t).lower()
    rules = [
        ("crypto", ["bitcoin", "btc", "ethereum", "eth", "solana", "sol ", "xrp", "crypto", "binance", "up or down"]),
        ("sports", ["sports", "world cup", "nba", "nfl", "mlb", "ufc", "tennis", "atp", "fifa", "game", "match", "championship"]),
        ("politics", ["politics", "election", "trump", "biden", "senate", "congress", "parliament", "president", "minister", "party"]),
        ("macro", ["macro", "fed", "cpi", "inflation", "rate cut", "unemployment", "gdp", "treasury", "recession"]),
        ("weather", ["hurricane", "temperature", "rain", "snow", "weather", "storm", "heat"]),
        ("entertainment", ["entertainment", "movie", "oscar", "grammy", "box office", "album", "streaming"]),
        ("tech", ["tech", "openai", "apple", "tesla", "nvidia", "google", "ai", "model"]),
    ]
    for category, needles in rules:
        if any(needle in text for needle in needles):
            return category
    return "other"


def rule_ambiguity_score(meta: MarketMeta | None, title: str = "") -> float:
    text = " ".join(
        [
            title,
            meta.title if meta else "",
            meta.event_title if meta else "",
            meta.description if meta else "",
        ]
    ).lower()
    if not text.strip():
        return 0.0
    weights = {
        "50-50": 2.0,
        "consensus": 1.2,
        "credible reporting": 1.2,
        "permanently canceled": 1.0,
        "canceled": 1.0,
        "cancelled": 1.0,
        "delayed": 0.9,
        "not completed": 1.0,
        "ambiguous": 1.5,
        "primary resolution source": 0.5,
        "if at any point": 0.5,
        "will resolve immediately": 0.4,
        "other": 0.2,
    }
    return sum(weight for needle, weight in weights.items() if needle in text)


def fetch_recent_trades(limit: int, page_size: int, timeout: float) -> list[Trade]:
    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    offset = 0
    while len(records) < limit:
        batch_limit = min(max(page_size, 1), limit - len(records))
        try:
            batch = http_get_json(
                DATA_BASE,
                "/trades",
                {"limit": batch_limit, "offset": offset, "takerOnly": "true"},
                timeout,
            )
        except HTTPError as exc:
            if exc.code == 400 and records:
                break
            raise
        if not batch:
            break
        new_count = 0
        for row in batch:
            key = (
                row.get("transactionHash"),
                row.get("proxyWallet"),
                row.get("asset"),
                row.get("side"),
                row.get("price"),
                row.get("size"),
                row.get("timestamp"),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            records.append(row)
            new_count += 1
            if len(records) >= limit:
                break
        if new_count == 0:
            break
        offset += len(batch)
        if offset > 10000:
            break
    trades: list[Trade] = []
    for row in records:
        trade = trade_from_public_row(row)
        if trade is not None:
            trades.append(trade)
    return sorted(trades, key=lambda x: (x.timestamp, x.tx, x.wallet))


def trade_from_public_row(row: dict[str, Any]) -> Trade | None:
    price = safe_float(row.get("price"))
    size = safe_float(row.get("size"))
    ts = safe_int(row.get("timestamp"))
    wallet = str(row.get("proxyWallet") or "").lower()
    asset = str(row.get("asset") or "")
    condition_id = str(row.get("conditionId") or "").lower()
    side = str(row.get("side") or "").upper()
    if not wallet or not asset or not condition_id or price is None or size is None or ts is None:
        return None
    if side not in {"BUY", "SELL"} or price <= 0 or price >= 1 or size <= 0:
        return None
    title = str(row.get("title") or "")
    slug = str(row.get("slug") or "")
    event_slug = str(row.get("eventSlug") or "")
    return Trade(
        wallet=wallet,
        side=side,
        asset=asset,
        condition_id=condition_id,
        size=size,
        price=price,
        timestamp=ts,
        title=title,
        slug=slug,
        event_slug=event_slug,
        outcome=str(row.get("outcome") or ""),
        outcome_index=safe_int(row.get("outcomeIndex")),
        name=str(row.get("name") or ""),
        pseudonym=str(row.get("pseudonym") or ""),
        tx=str(row.get("transactionHash") or ""),
        category=classify_category(title, slug, event_slug),
    )


def trade_key(trade: Trade) -> tuple[Any, ...]:
    return (
        trade.tx,
        trade.wallet,
        trade.asset,
        trade.side,
        round(trade.price, 10),
        round(trade.size, 10),
        trade.timestamp,
    )


def merge_trades(*trade_lists: list[Trade]) -> list[Trade]:
    out: list[Trade] = []
    seen: set[tuple[Any, ...]] = set()
    for trades in trade_lists:
        for trade in trades:
            key = trade_key(trade)
            if key in seen:
                continue
            seen.add(key)
            out.append(trade)
    return sorted(out, key=lambda x: (x.timestamp, x.tx, x.wallet))


def select_seed_wallets(trades: list[Trade], limit: int) -> list[str]:
    scores: dict[str, float] = {}
    counts: dict[str, int] = {}
    for trade in trades:
        scores[trade.wallet] = scores.get(trade.wallet, 0.0) + trade.notional
        counts[trade.wallet] = counts.get(trade.wallet, 0) + 1
    ranked = sorted(scores, key=lambda wallet: (counts[wallet], scores[wallet]), reverse=True)
    return ranked[:limit]


def fetch_wallet_activity_trades(
    wallets: list[str],
    limit_per_wallet: int,
    timeout: float,
    sleep_ms: int,
) -> list[Trade]:
    if limit_per_wallet <= 0 or not wallets:
        return []
    trades: list[Trade] = []
    for wallet in wallets:
        try:
            rows = http_get_json(
                DATA_BASE,
                "/activity",
                {
                    "user": wallet,
                    "type": "TRADE",
                    "limit": min(limit_per_wallet, 500),
                    "sortDirection": "DESC",
                    "sortBy": "TIMESTAMP",
                },
                timeout,
            )
        except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError):
            rows = []
        for row in rows:
            trade = trade_from_public_row(row)
            if trade is not None:
                trades.append(trade)
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
    return merge_trades(trades)


def fetch_market_meta(limit: int, timeout: float) -> dict[str, MarketMeta]:
    out: dict[str, MarketMeta] = {}
    if limit <= 0:
        return out
    events = http_get_json(
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
    for event in events:
        event_id = str(event.get("id") or "")
        event_title = str(event.get("title") or "")
        event_slug = str(event.get("slug") or "")
        tags = event.get("tags") or []
        tag_text = " ".join(str(t.get("label") or t.get("slug") or "") for t in tags if isinstance(t, dict))
        event_category = classify_category(event_title, event_slug, tag_text)
        for market in event.get("markets") or []:
            condition_id = str(market.get("conditionId") or "").lower()
            if not condition_id:
                continue
            outcomes = [str(x) for x in parse_json_list(market.get("outcomes"))]
            token_ids = [str(x) for x in parse_json_list(market.get("clobTokenIds"))]
            token_to_outcome: dict[str, str] = {}
            for idx, token_id in enumerate(token_ids):
                if idx < len(outcomes):
                    token_to_outcome[token_id] = outcomes[idx]
            title = str(market.get("question") or market.get("title") or event_title)
            slug = str(market.get("slug") or "")
            out[condition_id] = MarketMeta(
                condition_id=condition_id,
                market_id=str(market.get("id") or ""),
                event_id=event_id,
                title=title,
                event_title=event_title,
                slug=slug,
                event_slug=event_slug,
                category=classify_category(title, slug, event_category),
                description=str(market.get("description") or event.get("description") or ""),
                end_date=str(market.get("endDate") or event.get("endDate") or ""),
                liquidity=safe_float(market.get("liquidityNum") or market.get("liquidity")),
                volume24h=safe_float(market.get("volume24hrClob") or market.get("volume24hr")),
                best_bid=safe_float(market.get("bestBid")),
                best_ask=safe_float(market.get("bestAsk")),
                spread=safe_float(market.get("spread")),
                outcomes=outcomes,
                token_ids=token_ids,
                token_to_outcome=token_to_outcome,
            )
    return out


def enrich_trade_categories(trades: list[Trade], meta_by_condition: dict[str, MarketMeta]) -> list[Trade]:
    enriched: list[Trade] = []
    for trade in trades:
        meta = meta_by_condition.get(trade.condition_id)
        category = meta.category if meta else trade.category
        outcome = trade.outcome
        if meta and not outcome:
            outcome = meta.token_to_outcome.get(trade.asset, outcome)
        enriched.append(
            Trade(
                wallet=trade.wallet,
                side=trade.side,
                asset=trade.asset,
                condition_id=trade.condition_id,
                size=trade.size,
                price=trade.price,
                timestamp=trade.timestamp,
                title=trade.title,
                slug=trade.slug,
                event_slug=trade.event_slug,
                outcome=outcome,
                outcome_index=trade.outcome_index,
                name=trade.name,
                pseudonym=trade.pseudonym,
                tx=trade.tx,
                category=category,
            )
        )
    return enriched


def orderbook_depth_usd(levels: list[dict[str, Any]]) -> float:
    total = 0.0
    for level in levels:
        price = safe_float(level.get("price"))
        size = safe_float(level.get("size"))
        if price is None or size is None:
            continue
        total += price * size
    return total


def sorted_book_levels(levels: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    return sorted(
        levels,
        key=lambda level: safe_float(level.get("price")) if safe_float(level.get("price")) is not None else -1.0,
        reverse=reverse,
    )


def consume_book(levels: list[dict[str, Any]], notional: float) -> dict[str, float | bool | None]:
    remaining = notional
    tokens = 0.0
    cost = 0.0
    first_price: float | None = None
    for level in levels:
        price = safe_float(level.get("price"))
        size = safe_float(level.get("size"))
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        if first_price is None:
            first_price = price
        level_cost = price * size
        take_cost = min(remaining, level_cost)
        take_tokens = take_cost / price
        tokens += take_tokens
        cost += take_cost
        remaining -= take_cost
        if remaining <= EPS:
            break
    if remaining > EPS or tokens <= EPS or first_price is None:
        return {
            "ok": False,
            "avg_price": None,
            "slippage_cents": None,
            "filled_notional": cost,
        }
    avg_price = cost / tokens
    return {
        "ok": True,
        "avg_price": avg_price,
        "slippage_cents": (avg_price - first_price) * 100.0,
        "filled_notional": cost,
    }


def fetch_book_stats(
    asset: str,
    capacity_notional: list[float],
    timeout: float,
    max_capacity_slippage_cents: float,
) -> BookStats:
    try:
        book = http_get_json(CLOB_BASE, "/book", {"token_id": asset}, timeout)
    except (HTTPError, URLError, TimeoutError, RemoteDisconnected, json.JSONDecodeError) as exc:
        return BookStats(asset=asset, error=str(exc))
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bids_sorted = sorted_book_levels(bids, reverse=True)
    asks_sorted = sorted_book_levels(asks, reverse=False)
    best_bid = safe_float(bids_sorted[0].get("price")) if bids_sorted else None
    best_ask = safe_float(asks_sorted[0].get("price")) if asks_sorted else None
    capacity: dict[float, dict[str, float | bool | None]] = {}
    for notional in capacity_notional:
        raw = consume_book(asks_sorted, notional)
        ok = bool(raw["ok"]) and (
            raw["slippage_cents"] is not None and raw["slippage_cents"] <= max_capacity_slippage_cents
        )
        capacity[notional] = {**raw, "capacity_ok": ok}
    return BookStats(
        asset=asset,
        condition_id=str(book.get("market") or "").lower(),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=(best_ask - best_bid) if best_bid is not None and best_ask is not None else None,
        bid_depth_usd=orderbook_depth_usd(bids),
        ask_depth_usd=orderbook_depth_usd(asks),
        capacity=capacity,
    )


def build_asset_price_index(trades: list[Trade]) -> dict[str, list[Trade]]:
    by_asset: dict[str, list[Trade]] = {}
    for trade in trades:
        by_asset.setdefault(trade.asset, []).append(trade)
    for rows in by_asset.values():
        rows.sort(key=lambda x: (x.timestamp, x.tx, x.wallet))
    return by_asset


def future_trade_for_delay(rows: list[Trade], signal: Trade, delay_seconds: int) -> Trade | None:
    timestamps = [x.timestamp for x in rows]
    target = signal.timestamp + delay_seconds
    idx = bisect.bisect_left(timestamps, target)
    while idx < len(rows):
        candidate = rows[idx]
        if candidate.timestamp > signal.timestamp or candidate.tx != signal.tx or candidate.wallet != signal.wallet:
            return candidate
        idx += 1
    return None


def trade_copy_edges(
    trades: list[Trade],
    delays: list[int],
) -> dict[tuple[int, str], dict[int, dict[str, float | int | None]]]:
    by_asset = build_asset_price_index(trades)
    out: dict[tuple[int, str], dict[int, dict[str, float | int | None]]] = {}
    for idx, trade in enumerate(trades):
        if trade.side != "BUY":
            continue
        rows = by_asset.get(trade.asset, [])
        edge_by_delay: dict[int, dict[str, float | int | None]] = {}
        for delay in delays:
            future = future_trade_for_delay(rows, trade, delay)
            if future is None:
                edge_by_delay[delay] = {"future_price": None, "edge_cents": None, "return_pct": None, "seconds_wait": None}
                continue
            edge = future.price - trade.price
            edge_by_delay[delay] = {
                "future_price": future.price,
                "edge_cents": edge * 100.0,
                "return_pct": edge / max(trade.price, EPS),
                "seconds_wait": future.timestamp - trade.timestamp,
            }
        out[(idx, trade.tx)] = edge_by_delay
    return out


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def stdev(values: list[float]) -> float:
    return statistics.pstdev(values) if len(values) >= 2 else 0.0


def sharpe(values: list[float]) -> float | None:
    if not values:
        return None
    sd = stdev(values)
    if sd < MIN_SHARPE_STD_CENTS:
        return None
    return statistics.fmean(values) / sd


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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


def wallet_name(trades: list[Trade]) -> tuple[str, str]:
    for trade in reversed(trades):
        if trade.name or trade.pseudonym:
            return trade.name, trade.pseudonym
    return "", ""


def compute_wallet_scores(
    trades: list[Trade],
    edges: dict[tuple[int, str], dict[int, dict[str, float | int | None]]],
    delays: list[int],
    min_category_trades: int,
) -> list[dict[str, Any]]:
    indexed = list(enumerate(trades))
    by_wallet: dict[str, list[tuple[int, Trade]]] = {}
    for idx, trade in indexed:
        by_wallet.setdefault(trade.wallet, []).append((idx, trade))

    rows: list[dict[str, Any]] = []
    for wallet, items in by_wallet.items():
        buy_items = [(idx, t) for idx, t in items if t.side == "BUY"]
        trade_edges_by_delay: dict[int, list[float]] = {d: [] for d in delays}
        pnl_proxy_300: list[float] = []
        category_edges: dict[str, list[float]] = {}
        for idx, trade in buy_items:
            edge_by_delay = edges.get((idx, trade.tx), {})
            for delay in delays:
                edge = edge_by_delay.get(delay, {}).get("edge_cents")
                if isinstance(edge, (int, float)) and math.isfinite(edge):
                    trade_edges_by_delay[delay].append(float(edge))
            use_delay = 300 if 300 in delays else max(delays)
            edge_300 = edge_by_delay.get(use_delay, {}).get("edge_cents")
            if isinstance(edge_300, (int, float)) and math.isfinite(edge_300):
                pnl = float(edge_300) / 100.0 * trade.size
                pnl_proxy_300.append(pnl)
                category_edges.setdefault(trade.category, []).append(float(edge_300))

        mean_by_delay = {delay: mean(vals) for delay, vals in trade_edges_by_delay.items()}
        robust_delays = [d for d in (30, 120, 300) if d in mean_by_delay]
        valid_robust = [mean_by_delay[d] for d in robust_delays if mean_by_delay[d] is not None]
        delay_robust = min(valid_robust) if len(valid_robust) == len(robust_delays) and valid_robust else None
        copy_decay_300 = None
        if mean_by_delay.get(0) is not None and mean_by_delay.get(300) is not None:
            copy_decay_300 = mean_by_delay[0] - mean_by_delay[300]  # type: ignore[operator]

        cat_sharpes: dict[str, float] = {}
        for category, vals in category_edges.items():
            if len(vals) >= min_category_trades:
                s = sharpe(vals)
                if s is not None:
                    cat_sharpes[category] = s
        best_category = ""
        category_specialization = None
        if cat_sharpes:
            best_category = max(cat_sharpes, key=lambda k: cat_sharpes[k])
            rest_vals = [
                value
                for category, vals in category_edges.items()
                if category != best_category
                for value in vals
            ]
            rest_sharpe = sharpe(rest_vals)
            category_specialization = clamp(cat_sharpes[best_category] - (rest_sharpe or 0.0), -10.0, 10.0)

        pos_pnl = [x for x in pnl_proxy_300 if x > 0]
        one_hit = max(pos_pnl) / sum(pos_pnl) if pos_pnl and sum(pos_pnl) > EPS else 1.0
        buy_eval_count_300 = len(trade_edges_by_delay.get(300, []))
        copyable_score = None
        if delay_robust is not None:
            copyable_score = (
                delay_robust
                + 0.35 * (category_specialization or 0.0)
                + 0.08 * math.log1p(buy_eval_count_300)
                - 1.0 * one_hit
            )
        name, pseudonym = wallet_name([trade for _, trade in items])
        notional = sum(t.notional for _, t in items)
        category_counts: dict[str, int] = {}
        for _, trade in items:
            category_counts[trade.category] = category_counts.get(trade.category, 0) + 1
        rows.append(
            {
                "wallet": wallet,
                "name": name,
                "pseudonym": pseudonym,
                "trade_count": len(items),
                "buy_trade_count": len(buy_items),
                "sell_trade_count": len(items) - len(buy_items),
                "buy_eval_count_300s": buy_eval_count_300,
                "market_count": len({t.condition_id for _, t in items}),
                "asset_count": len({t.asset for _, t in items}),
                "notional_usd_proxy": notional,
                "best_category": best_category,
                "category_counts_json": json.dumps(category_counts, sort_keys=True),
                "category_specialization": category_specialization,
                "one_hit_wonder_penalty": one_hit,
                "copy_decay_300s_cents": copy_decay_300,
                "delay_robust_edge_cents": delay_robust,
                "copyable_wallet_score": copyable_score,
                **{f"copy_edge_{delay}s_cents": mean_by_delay.get(delay) for delay in delays},
            }
        )
    rows.sort(
        key=lambda r: (
            r["copyable_wallet_score"] is not None,
            r["copyable_wallet_score"] if r["copyable_wallet_score"] is not None else -1e9,
            r["buy_eval_count_300s"],
        ),
        reverse=True,
    )
    return rows


def eligible_wallet_set(
    wallet_scores: list[dict[str, Any]],
    *,
    min_wallet_buy_trades: int,
    min_5m_edge_cents: float,
    max_one_hit_penalty: float,
) -> set[str]:
    return {
        row["wallet"]
        for row in wallet_scores
        if row.get("copy_edge_300s_cents") is not None
        and row.get("copy_edge_300s_cents") > min_5m_edge_cents
        and row.get("one_hit_wonder_penalty", 1.0) <= max_one_hit_penalty
        and row.get("buy_eval_count_300s", 0) >= min_wallet_buy_trades
    }


def select_assets_for_books(
    trades: list[Trade],
    limit: int,
    eligible_wallets: set[str],
) -> list[str]:
    score: dict[str, float] = {}
    latest_ts = max((trade.timestamp for trade in trades), default=0)
    for trade in trades:
        if trade.side == "BUY":
            recent = latest_ts - trade.timestamp <= 24 * 3600
            recency_weight = 10.0 if recent else 1.0
            eligible_weight = 25.0 if trade.wallet in eligible_wallets and recent else 1.0
            score[trade.asset] = score.get(trade.asset, 0.0) + trade.notional * recency_weight * eligible_weight
    return [asset for asset, _ in sorted(score.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


def compute_market_suitability(
    trades: list[Trade],
    wallet_scores: list[dict[str, Any]],
    books: dict[str, BookStats],
    meta_by_condition: dict[str, MarketMeta],
    capacity_notional: list[float],
) -> list[dict[str, Any]]:
    top_wallets = {
        row["wallet"]
        for row in wallet_scores
        if row.get("copyable_wallet_score") is not None
    }
    smart_recent_by_asset: dict[str, float] = {}
    latest_ts = max((t.timestamp for t in trades), default=0)
    for trade in trades:
        if trade.wallet in top_wallets and trade.side == "BUY" and latest_ts - trade.timestamp <= 24 * 3600:
            smart_recent_by_asset[trade.asset] = smart_recent_by_asset.get(trade.asset, 0.0) + trade.notional

    by_asset: dict[str, list[Trade]] = {}
    for trade in trades:
        by_asset.setdefault(trade.asset, []).append(trade)

    rows: list[dict[str, Any]] = []
    for asset, items in by_asset.items():
        first = items[-1]
        meta = meta_by_condition.get(first.condition_id)
        book = books.get(asset)
        spread = (book.spread if book else None) or (meta.spread if meta else None)
        ask_depth = book.ask_depth_usd if book else None
        smart_notional = smart_recent_by_asset.get(asset, 0.0)
        crowd_exit_risk = smart_notional / ask_depth if ask_depth and ask_depth > EPS else None
        rule_score = rule_ambiguity_score(meta, first.title)
        market_suitability = None
        if spread is not None:
            market_suitability = 1.0 - 10.0 * spread - 0.08 * rule_score
            if crowd_exit_risk is not None:
                market_suitability -= min(crowd_exit_risk, 3.0) * 0.2
        row = {
            "asset": asset,
            "condition_id": first.condition_id,
            "title": meta.title if meta else first.title,
            "slug": meta.slug if meta and meta.slug else first.slug,
            "outcome": meta.token_to_outcome.get(asset, first.outcome) if meta else first.outcome,
            "category": meta.category if meta else first.category,
            "trade_count_recent_sample": len(items),
            "notional_usd_recent_sample": sum(t.notional for t in items),
            "best_bid": book.best_bid if book else (meta.best_bid if meta else None),
            "best_ask": book.best_ask if book else (meta.best_ask if meta else None),
            "spread_cents": spread * 100.0 if spread is not None else None,
            "bid_depth_usd": book.bid_depth_usd if book else None,
            "ask_depth_usd": ask_depth,
            "smart_recent_notional_usd": smart_notional,
            "crowd_exit_risk": crowd_exit_risk,
            "rule_ambiguity_score": rule_score,
            "market_suitability_score": market_suitability,
            "book_error": book.error if book else "not_collected",
        }
        for notional in capacity_notional:
            cap = book.capacity.get(notional, {}) if book else {}
            key = int(notional)
            row[f"capacity_{key}_ok"] = cap.get("capacity_ok")
            row[f"capacity_{key}_avg_price"] = cap.get("avg_price")
            row[f"capacity_{key}_slippage_cents"] = cap.get("slippage_cents")
        rows.append(row)
    rows.sort(
        key=lambda r: (
            r["market_suitability_score"] is not None,
            r["market_suitability_score"] if r["market_suitability_score"] is not None else -1e9,
            r["notional_usd_recent_sample"],
        ),
        reverse=True,
    )
    return rows


def compute_follow_candidates(
    trades: list[Trade],
    edges: dict[tuple[int, str], dict[int, dict[str, float | int | None]]],
    wallet_scores: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    candidate_lookback_hours: float,
    min_wallet_buy_trades: int,
    min_5m_edge_cents: float,
    max_one_hit_penalty: float,
    capacity_notional: list[float],
    allow_unknown_capacity: bool,
) -> list[dict[str, Any]]:
    wallet_by_id = {row["wallet"]: row for row in wallet_scores}
    market_by_asset = {row["asset"]: row for row in market_rows}
    latest_ts = max((t.timestamp for t in trades), default=0)
    min_ts = latest_ts - int(candidate_lookback_hours * 3600)
    out: list[dict[str, Any]] = []
    for idx, trade in enumerate(trades):
        if trade.timestamp < min_ts or trade.side != "BUY":
            continue
        wallet = wallet_by_id.get(trade.wallet)
        market = market_by_asset.get(trade.asset)
        if not wallet or not market:
            continue
        edge_5m = wallet.get("copy_edge_300s_cents")
        if wallet.get("buy_eval_count_300s", 0) < min_wallet_buy_trades:
            continue
        if edge_5m is None or edge_5m <= min_5m_edge_cents:
            continue
        if wallet.get("one_hit_wonder_penalty", 1.0) > max_one_hit_penalty:
            continue
        rule_score = market.get("rule_ambiguity_score")
        if rule_score is not None and rule_score >= 4.0:
            continue
        if not allow_unknown_capacity and market.get("capacity_1000_ok") is not True:
            continue
        market_score = market.get("market_suitability_score")
        wallet_score = wallet.get("copyable_wallet_score")
        liquidity_edge = None
        spread_cents = market.get("spread_cents")
        slippage_1k = market.get("capacity_1000_slippage_cents")
        if edge_5m is not None and spread_cents is not None:
            denom = max(float(spread_cents) + float(slippage_1k or 0.0), 0.01)
            liquidity_edge = float(edge_5m) / denom
        follow_score = None
        if wallet_score is not None and market_score is not None and liquidity_edge is not None:
            follow_score = float(wallet_score) * max(float(market_score), 0.0) * float(liquidity_edge)

        edge_by_delay = edges.get((idx, trade.tx), {})
        row = {
            "timestamp_utc": datetime.fromtimestamp(trade.timestamp, tz=timezone.utc).isoformat(),
            "wallet": trade.wallet,
            "name": trade.name,
            "pseudonym": trade.pseudonym,
            "title": market.get("title") or trade.title,
            "slug": market.get("slug") or trade.slug,
            "category": market.get("category") or trade.category,
            "outcome": market.get("outcome") or trade.outcome,
            "asset": trade.asset,
            "condition_id": trade.condition_id,
            "entry_price": trade.price,
            "trade_size": trade.size,
            "trade_notional_usd": trade.notional,
            "wallet_copy_edge_5m_cents": edge_5m,
            "wallet_delay_robust_edge_cents": wallet.get("delay_robust_edge_cents"),
            "wallet_copyable_score": wallet_score,
            "market_suitability_score": market_score,
            "liquidity_adjusted_copy_edge": liquidity_edge,
            "follow_score": follow_score,
            "one_hit_wonder_penalty": wallet.get("one_hit_wonder_penalty"),
            "spread_cents": market.get("spread_cents"),
            "ask_depth_usd": market.get("ask_depth_usd"),
            "crowd_exit_risk": market.get("crowd_exit_risk"),
            "rule_ambiguity_score": rule_score,
        }
        for delay in (30, 120, 300, 1800):
            row[f"trade_proxy_edge_{delay}s_cents"] = edge_by_delay.get(delay, {}).get("edge_cents")
        for notional in capacity_notional:
            key = int(notional)
            row[f"capacity_{key}_ok"] = market.get(f"capacity_{key}_ok")
            row[f"capacity_{key}_slippage_cents"] = market.get(f"capacity_{key}_slippage_cents")
        out.append(row)
    out.sort(
        key=lambda r: (
            r["follow_score"] is not None,
            r["follow_score"] if r["follow_score"] is not None else -1e9,
            r["wallet_copy_edge_5m_cents"] if r["wallet_copy_edge_5m_cents"] is not None else -1e9,
        ),
        reverse=True,
    )
    return out


def compute_trade_edge_rows(
    trades: list[Trade],
    edges: dict[tuple[int, str], dict[int, dict[str, float | int | None]]],
    delays: list[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, trade in enumerate(trades):
        if trade.side != "BUY":
            continue
        edge_by_delay = edges.get((idx, trade.tx), {})
        row: dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(trade.timestamp, tz=timezone.utc).isoformat(),
            "timestamp": trade.timestamp,
            "wallet": trade.wallet,
            "name": trade.name,
            "pseudonym": trade.pseudonym,
            "title": trade.title,
            "slug": trade.slug,
            "category": trade.category,
            "outcome": trade.outcome,
            "asset": trade.asset,
            "condition_id": trade.condition_id,
            "entry_price": trade.price,
            "trade_size": trade.size,
            "trade_notional_usd": trade.notional,
            "tx": trade.tx,
        }
        for delay in delays:
            delay_row = edge_by_delay.get(delay, {})
            row[f"future_price_{delay}s"] = delay_row.get("future_price")
            row[f"edge_{delay}s_cents"] = delay_row.get("edge_cents")
            row[f"return_{delay}s_pct"] = delay_row.get("return_pct")
            row[f"seconds_wait_{delay}s"] = delay_row.get("seconds_wait")
        rows.append(row)
    rows.sort(key=lambda r: (r.get("timestamp") or 0, r.get("tx") or "", r.get("wallet") or ""))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def top_n(rows: list[dict[str, Any]], n: int = 10) -> list[dict[str, Any]]:
    return rows[: min(n, len(rows))]


def write_summary(
    output_dir: Path,
    *,
    trades: list[Trade],
    recent_trade_count: int,
    wallet_activity_trade_count: int,
    wallet_activity_wallet_count: int,
    wallet_scores: list[dict[str, Any]],
    market_rows: list[dict[str, Any]],
    follow_candidates: list[dict[str, Any]],
    trade_edge_count: int,
    args: argparse.Namespace,
    book_errors: int,
) -> None:
    latest_ts = max((t.timestamp for t in trades), default=0)
    earliest_ts = min((t.timestamp for t in trades), default=0)
    eligible_wallets = [
        row
        for row in wallet_scores
        if row.get("copy_edge_300s_cents") is not None
        and row.get("copy_edge_300s_cents") > args.min_5m_edge_cents
        and row.get("one_hit_wonder_penalty", 1.0) <= args.max_one_hit_penalty
        and row.get("buy_eval_count_300s", 0) >= args.min_wallet_buy_trades
    ]
    liquid_markets = [
        row
        for row in market_rows
        if row.get("capacity_1000_ok") is True
    ]
    lines = [
        "# Polymarket Wallet Factor Probe",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Inputs",
        "",
        f"- Recent public trades requested: {args.trade_limit}",
        f"- Global recent trades parsed: {recent_trade_count}",
        f"- Wallet activity seed wallets requested: {wallet_activity_wallet_count}",
        f"- Wallet activity trades parsed: {wallet_activity_trade_count}",
        f"- Merged unique trades used for factors: {len(trades)}",
        "- Note: public `/trades` pagination may stop before the requested limit when the API returns a paging-window 400.",
        f"- Time span UTC: {datetime.fromtimestamp(earliest_ts, timezone.utc).isoformat() if earliest_ts else 'n/a'} -> {datetime.fromtimestamp(latest_ts, timezone.utc).isoformat() if latest_ts else 'n/a'}",
        f"- Gamma active events requested: {args.gamma_event_limit}",
        f"- Orderbook token limit: {0 if args.skip_books else args.book_token_limit}",
        f"- Book errors: {book_errors}",
        "",
        "## Outputs",
        "",
        "- `wallet_scores.csv`: wallet-level copyability proxies.",
        "- `market_suitability.csv`: market/outcome liquidity, ambiguity, and capacity checks.",
        "- `follow_candidates.csv`: recent buy trades passing v0 risk filters.",
        "- `trade_edges.csv`: BUY trade rows with delayed next-trade price proxies for causal paper simulation.",
        "- `raw_snapshot.json`: compact raw run metadata and top rows.",
        "",
        "## Important V0 Boundaries",
        "",
        "- No private API, signing, or order placement is used.",
        "- `CopyPnL` uses the next public trade on the same outcome token as the delayed price proxy.",
        "- Historical orderbook is not assumed; depth is current live book only when collected.",
        "- SELL trades are scored as wallet behavior but not emitted as copy candidates in v0.",
        "",
        "## Current Counts",
        "",
        f"- Wallets scored: {len(wallet_scores)}",
        f"- Eligible wallets after 5m/one-hit/min-count filters: {len(eligible_wallets)}",
        f"- Markets/assets scored: {len(market_rows)}",
        f"- Markets with 1k capacity under slippage threshold: {len(liquid_markets)}",
        f"- Follow candidates: {len(follow_candidates)}",
        f"- BUY trade edge rows: {trade_edge_count}",
        "",
        "## Top Wallets",
        "",
        "| wallet | pseudonym | buy_eval_300s | edge_5m_cents | delay_robust_cents | one_hit | score | best_category |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in top_n(wallet_scores, 12):
        lines.append(
            "| {wallet} | {pseudonym} | {buy_eval_count_300s} | {edge} | {robust} | {one_hit} | {score} | {cat} |".format(
                wallet=row.get("wallet", ""),
                pseudonym=row.get("pseudonym", ""),
                buy_eval_count_300s=row.get("buy_eval_count_300s", 0),
                edge=fmt(row.get("copy_edge_300s_cents")),
                robust=fmt(row.get("delay_robust_edge_cents")),
                one_hit=fmt(row.get("one_hit_wonder_penalty")),
                score=fmt(row.get("copyable_wallet_score")),
                cat=row.get("best_category", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Top Follow Candidates",
            "",
            "| time | wallet | category | outcome | entry | edge_5m_cents | liq_edge | follow_score | capacity_1k | title |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in top_n(follow_candidates, 12):
        lines.append(
            "| {time} | {wallet} | {cat} | {outcome} | {entry} | {edge} | {liq} | {score} | {cap} | {title} |".format(
                time=str(row.get("timestamp_utc", ""))[:19],
                wallet=str(row.get("wallet", ""))[:12] + "...",
                cat=row.get("category", ""),
                outcome=row.get("outcome", ""),
                entry=fmt(row.get("entry_price")),
                edge=fmt(row.get("wallet_copy_edge_5m_cents")),
                liq=fmt(row.get("liquidity_adjusted_copy_edge")),
                score=fmt(row.get("follow_score")),
                cap=row.get("capacity_1000_ok"),
                title=str(row.get("title", ""))[:80].replace("|", "/"),
            )
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return ""
        return f"{float(value):.4g}"
    return str(value)


def parse_number_list(raw: str, cast: type[int] | type[float]) -> list[Any]:
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        out.append(cast(float(item)) if cast is int else cast(item))
    return out


def self_test() -> None:
    trades = [
        Trade("0xa", "BUY", "asset1", "0xc", 100, 0.40, 1000, "BTC up", "btc", "btc", "Yes", 0, "A", "A", "tx1", "crypto"),
        Trade("0xb", "BUY", "asset1", "0xc", 100, 0.42, 1030, "BTC up", "btc", "btc", "Yes", 0, "B", "B", "tx2", "crypto"),
        Trade("0xc", "BUY", "asset1", "0xc", 100, 0.45, 1300, "BTC up", "btc", "btc", "Yes", 0, "C", "C", "tx3", "crypto"),
        Trade("0xa", "BUY", "asset1", "0xc", 50, 0.44, 1400, "BTC up", "btc", "btc", "Yes", 0, "A", "A", "tx4", "crypto"),
        Trade("0xd", "BUY", "asset1", "0xc", 100, 0.43, 1700, "BTC up", "btc", "btc", "Yes", 0, "D", "D", "tx5", "crypto"),
    ]
    edges = trade_copy_edges(trades, [0, 30, 300])
    first = edges[(0, "tx1")]
    assert round(first[30]["edge_cents"], 8) == 2.0
    assert round(first[300]["edge_cents"], 8) == 5.0
    levels = [{"price": "0.50", "size": "1000"}, {"price": "0.52", "size": "1000"}]
    cap = consume_book(levels, 750)
    assert cap["ok"] is True
    assert round(float(cap["avg_price"]), 8) == 0.50649351
    wallet_rows = compute_wallet_scores(trades, edges, [0, 30, 300], 1)
    row_a = next(row for row in wallet_rows if row["wallet"] == "0xa")
    assert row_a["buy_eval_count_300s"] == 2
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return

    delays = parse_number_list(args.delay_seconds, int)
    capacity_notional = parse_number_list(args.capacity_notional, float)
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    recent_trades = fetch_recent_trades(args.trade_limit, args.page_size, args.http_timeout)
    seed_wallets = select_seed_wallets(recent_trades, args.wallet_history_wallets)
    wallet_activity_trades = fetch_wallet_activity_trades(
        seed_wallets,
        args.wallet_history_limit,
        args.http_timeout,
        args.sleep_ms,
    )
    trades = merge_trades(recent_trades, wallet_activity_trades)
    meta_by_condition = fetch_market_meta(args.gamma_event_limit, args.http_timeout)
    trades = enrich_trade_categories(trades, meta_by_condition)

    edges = trade_copy_edges(trades, delays)
    wallet_scores = compute_wallet_scores(
        trades,
        edges,
        delays,
        min_category_trades=args.min_category_trades,
    )
    wallet_scores = wallet_scores[: args.top_wallets]

    books: dict[str, BookStats] = {}
    if not args.skip_books:
        eligible_wallets = eligible_wallet_set(
            wallet_scores,
            min_wallet_buy_trades=args.min_wallet_buy_trades,
            min_5m_edge_cents=args.min_5m_edge_cents,
            max_one_hit_penalty=args.max_one_hit_penalty,
        )
        for asset in select_assets_for_books(trades, args.book_token_limit, eligible_wallets):
            books[asset] = fetch_book_stats(
                asset,
                capacity_notional,
                args.http_timeout,
                args.max_capacity_slippage_cents,
            )
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)

    market_rows = compute_market_suitability(
        trades,
        wallet_scores,
        books,
        meta_by_condition,
        capacity_notional,
    )
    follow_candidates = compute_follow_candidates(
        trades,
        edges,
        wallet_scores,
        market_rows,
        args.candidate_lookback_hours,
        args.min_wallet_buy_trades,
        args.min_5m_edge_cents,
        args.max_one_hit_penalty,
        capacity_notional,
        args.allow_unknown_capacity,
    )
    trade_edge_rows = compute_trade_edge_rows(trades, edges, delays)

    write_csv(output_dir / "wallet_scores.csv", wallet_scores)
    write_csv(output_dir / "market_suitability.csv", market_rows)
    write_csv(output_dir / "follow_candidates.csv", follow_candidates)
    write_csv(output_dir / "trade_edges.csv", trade_edge_rows)
    write_json(
        output_dir / "raw_snapshot.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            "trade_count": len(trades),
            "recent_trade_count": len(recent_trades),
            "wallet_activity_trade_count": len(wallet_activity_trades),
            "wallet_activity_wallet_count": len(seed_wallets),
            "wallet_count": len(wallet_scores),
            "market_asset_count": len(market_rows),
            "follow_candidate_count": len(follow_candidates),
            "trade_edge_count": len(trade_edge_rows),
            "book_count": len(books),
            "book_error_count": sum(1 for book in books.values() if book.error),
            "top_wallets": top_n(wallet_scores, 20),
            "top_markets": top_n(market_rows, 20),
            "top_follow_candidates": top_n(follow_candidates, 20),
        },
    )
    write_summary(
        output_dir,
        trades=trades,
        recent_trade_count=len(recent_trades),
        wallet_activity_trade_count=len(wallet_activity_trades),
        wallet_activity_wallet_count=len(seed_wallets),
        wallet_scores=wallet_scores,
        market_rows=market_rows,
        follow_candidates=follow_candidates,
        trade_edge_count=len(trade_edge_rows),
        args=args,
        book_errors=sum(1 for book in books.values() if book.error),
    )
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
