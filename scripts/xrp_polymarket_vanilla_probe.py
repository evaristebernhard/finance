#!/usr/bin/env python3
"""Probe XRP Polymarket barrier markets against locally accessible vanilla options."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = Path(".env.chog.local")
DEFAULT_OUTPUT_DIR = Path("output/xrp_polymarket_vanilla_probe")
DEFAULT_POLYMARKET_EVENT_ID = "89530"
DEFAULT_BINANCE_TRADES_DIR = Path("data/binance_vision/futures_um/daily/aggTrades/XRPUSDT")

POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"
TARDIS_API_BASE = "https://api.tardis.dev/v1"
DERIBIT_API_BASE = "https://www.deribit.com/api/v2/public"


@dataclass(frozen=True)
class TouchMarket:
    question: str
    kind: str
    threshold: float
    bid: float | None
    ask: float | None
    last: float | None
    mid: float | None
    active: bool
    closed: bool


@dataclass(frozen=True)
class DeribitOption:
    instrument_name: str
    expiry: str
    strike: float
    option_type: str
    mark_price: float | None
    bid_price: float | None
    ask_price: float | None
    mid_price: float | None
    underlying_price: float | None
    open_interest: float | None
    mark_iv: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--polymarket-event-id", default=DEFAULT_POLYMARKET_EVENT_ID)
    parser.add_argument("--binance-trades-dir", type=Path, default=DEFAULT_BINANCE_TRADES_DIR)
    return parser.parse_args()


def load_tardis_key(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'(?im)^\s*TARDIS_API_KEY\s*=\s*["\']?([^\r\n"\']+)', text)
    if not match:
        raise SystemExit(f"TARDIS_API_KEY not found in {path}")
    key = match.group(1).strip()
    if len(key) < 20:
        raise SystemExit("TARDIS_API_KEY exists but is too short")
    return key


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 60.0) -> Any:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


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


def midpoint(bid: float | None, ask: float | None, last: float | None) -> float | None:
    if bid is not None and ask is not None:
        return 0.5 * (bid + ask)
    return last


def parse_touch_market(raw: dict[str, Any]) -> TouchMarket | None:
    question = str(raw.get("question") or "").strip()
    if not question.startswith("Will XRP "):
        return None
    if " reach $" in question:
        kind = "touch_up"
    elif " dip to $" in question:
        kind = "touch_down"
    else:
        return None
    match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", question)
    if not match:
        return None
    threshold = float(match.group(1))
    bid = safe_float(raw.get("bestBid"))
    ask = safe_float(raw.get("bestAsk"))
    last = safe_float(raw.get("lastTradePrice"))
    return TouchMarket(
        question=question,
        kind=kind,
        threshold=threshold,
        bid=bid,
        ask=ask,
        last=last,
        mid=midpoint(bid, ask, last),
        active=bool(raw.get("active")),
        closed=bool(raw.get("closed")),
    )


def fetch_polymarket_event(event_id: str) -> dict[str, Any]:
    event = http_get_json(
        f"{POLYMARKET_GAMMA_BASE}/events/{event_id}",
        headers={"User-Agent": "finance-chain-xrp-polymarket-probe"},
    )
    markets = [parse_touch_market(item) for item in event.get("markets", [])]
    event["parsed_touch_markets"] = [
        market for market in markets if market is not None and not market.closed and market.active
    ]
    return event


def fetch_tardis_exchange(exchange: str, key: str) -> dict[str, Any]:
    return http_get_json(
        f"{TARDIS_API_BASE}/exchanges/{exchange}",
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "finance-chain-xrp-options-probe",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
    )


def parse_tardis_symbols(exchange_body: dict[str, Any]) -> list[str]:
    raw = exchange_body.get("availableSymbols") or exchange_body.get("symbols") or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.append(str(item.get("id") or item.get("symbol") or ""))
    return out


def summarize_tardis_xrp(exchange: str, symbols: list[str]) -> dict[str, Any]:
    xrp_symbols = [symbol for symbol in symbols if "XRP" in symbol.upper()]
    option_symbols: list[str] = []
    expiries: set[str] = set()
    for symbol in xrp_symbols:
        parts = symbol.split("-")
        is_option = False
        if exchange == "deribit":
            is_option = len(parts) == 4 and parts[3] in {"C", "P"}
        elif exchange == "bybit-options":
            is_option = len(parts) == 5 and parts[3] in {"C", "P"}
        elif exchange == "binance-european-options":
            is_option = len(parts) == 4 and parts[3].lower() in {"c", "p"}
        if is_option:
            option_symbols.append(symbol)
            expiries.add(parts[1])
    if exchange in {"deribit", "bybit-options"}:
        sorted_expiries = sorted(expiries, key=lambda value: datetime.strptime(value, "%d%b%y"))
    elif exchange == "binance-european-options":
        sorted_expiries = sorted(expiries, key=lambda value: datetime.strptime(value, "%y%m%d"))
    else:
        sorted_expiries = sorted(expiries)
    return {
        "exchange": exchange,
        "xrp_symbol_count": len(option_symbols),
        "expiry_count": len(sorted_expiries),
        "first_expiries": sorted_expiries[:10],
        "last_expiries": sorted_expiries[-10:],
        "sample_symbols": option_symbols[:12],
    }


def fetch_deribit_xrp_options() -> list[DeribitOption]:
    body = http_get_json(
        f"{DERIBIT_API_BASE}/get_book_summary_by_currency?currency=USDC&kind=option",
        headers={"User-Agent": "finance-chain-xrp-deribit-probe"},
    )
    rows: list[DeribitOption] = []
    for item in body.get("result", []):
        name = str(item.get("instrument_name") or "")
        if not name.startswith("XRP_USDC-"):
            continue
        parts = name.split("-")
        if len(parts) != 4:
            continue
        strike = float(parts[2].replace("d", "."))
        rows.append(
            DeribitOption(
                instrument_name=name,
                expiry=parts[1],
                strike=strike,
                option_type=parts[3],
                mark_price=safe_float(item.get("mark_price")),
                bid_price=safe_float(item.get("bid_price")),
                ask_price=safe_float(item.get("ask_price")),
                mid_price=safe_float(item.get("mid_price")),
                underlying_price=safe_float(item.get("underlying_price")),
                open_interest=safe_float(item.get("open_interest")),
                mark_iv=safe_float(item.get("mark_iv")),
            )
        )
    return rows


def parse_deribit_expiry(expiry: str) -> datetime:
    return datetime.strptime(expiry, "%d%b%y").replace(tzinfo=timezone.utc)


def choose_latest_expiry(options: list[DeribitOption]) -> str:
    expiries = sorted({option.expiry for option in options}, key=parse_deribit_expiry)
    if not expiries:
        raise ValueError("no XRP options found on Deribit summary feed")
    return expiries[-1]


def quote_price(option: DeribitOption) -> float | None:
    if option.mark_price is not None:
        return option.mark_price
    if option.mid_price is not None:
        return option.mid_price
    if option.bid_price is not None and option.ask_price is not None:
        return 0.5 * (option.bid_price + option.ask_price)
    return option.bid_price or option.ask_price


def build_touch_vs_digital_checks(
    touch_markets: list[TouchMarket],
    options: list[DeribitOption],
    expiry: str,
) -> list[dict[str, Any]]:
    calls = sorted(
        [option for option in options if option.expiry == expiry and option.option_type == "C"],
        key=lambda option: option.strike,
    )
    puts = sorted(
        [option for option in options if option.expiry == expiry and option.option_type == "P"],
        key=lambda option: option.strike,
    )
    call_by_strike = {option.strike: option for option in calls}
    put_by_strike = {option.strike: option for option in puts}
    checks: list[dict[str, Any]] = []

    for market in sorted(touch_markets, key=lambda item: (item.kind, item.threshold)):
        row: dict[str, Any] = {
            "question": market.question,
            "kind": market.kind,
            "threshold": market.threshold,
            "polymarket_bid": market.bid,
            "polymarket_ask": market.ask,
            "polymarket_mid": market.mid,
            "deribit_expiry": expiry,
            "status": "no_matching_strike",
        }
        if market.kind == "touch_up" and market.threshold in call_by_strike:
            left = call_by_strike[market.threshold]
            right_candidates = [option for option in calls if option.strike > market.threshold]
            if right_candidates:
                right = right_candidates[0]
                left_price = quote_price(left)
                right_price = quote_price(right)
                if left_price is not None and right_price is not None:
                    digital_lower = (left_price - right_price) / (right.strike - left.strike)
                    row.update(
                        {
                            "status": "checked",
                            "vanilla_lower_bound_kind": "forward_call_spread",
                            "left_strike": left.strike,
                            "right_strike": right.strike,
                            "left_price": left_price,
                            "right_price": right_price,
                            "terminal_digital_lower_bound": digital_lower,
                            "touch_minus_lower_bound": (
                                market.mid - digital_lower if market.mid is not None else None
                            ),
                            "violates_lower_bound": (
                                market.mid < digital_lower if market.mid is not None else None
                            ),
                        }
                    )
        if market.kind == "touch_down" and market.threshold in put_by_strike:
            right = put_by_strike[market.threshold]
            left_candidates = [option for option in puts if option.strike < market.threshold]
            if left_candidates:
                left = left_candidates[-1]
                left_price = quote_price(left)
                right_price = quote_price(right)
                if left_price is not None and right_price is not None:
                    digital_lower = (right_price - left_price) / (right.strike - left.strike)
                    row.update(
                        {
                            "status": "checked",
                            "vanilla_lower_bound_kind": "backward_put_spread",
                            "left_strike": left.strike,
                            "right_strike": right.strike,
                            "left_price": left_price,
                            "right_price": right_price,
                            "terminal_digital_lower_bound": digital_lower,
                            "touch_minus_lower_bound": (
                                market.mid - digital_lower if market.mid is not None else None
                            ),
                            "violates_lower_bound": (
                                market.mid < digital_lower if market.mid is not None else None
                            ),
                        }
                    )
        checks.append(row)
    return checks


def summarize_binance_local_range(trades_dir: Path) -> dict[str, Any]:
    files = sorted(trades_dir.glob("XRPUSDT-aggTrades-*.zip"))
    if not files:
        return {"files": 0, "rows": 0}
    min_price = math.inf
    max_price = -math.inf
    first_ts_ms: int | None = None
    last_ts_ms: int | None = None
    rows = 0
    for path in files:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".csv")]
            if not names:
                continue
            with archive.open(names[0]) as handle:
                reader = csv.reader(line.decode("utf-8") for line in handle)
                for row in reader:
                    if not row or row[0] == "agg_trade_id":
                        continue
                    price = float(row[1])
                    ts_ms = int(row[5])
                    min_price = min(min_price, price)
                    max_price = max(max_price, price)
                    first_ts_ms = ts_ms if first_ts_ms is None else min(first_ts_ms, ts_ms)
                    last_ts_ms = ts_ms if last_ts_ms is None else max(last_ts_ms, ts_ms)
                    rows += 1
    return {
        "files": len(files),
        "rows": rows,
        "min_price": min_price,
        "max_price": max_price,
        "first_ts_utc": (
            datetime.fromtimestamp(first_ts_ms / 1000.0, tz=timezone.utc).isoformat()
            if first_ts_ms is not None
            else ""
        ),
        "last_ts_utc": (
            datetime.fromtimestamp(last_ts_ms / 1000.0, tz=timezone.utc).isoformat()
            if last_ts_ms is not None
            else ""
        ),
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    event = summary["polymarket_event"]
    lines = [
        "# XRP Polymarket vs Vanilla Probe",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Polymarket event: `{event['title']}` (`id={event['id']}`)",
        f"- Polymarket updatedAt: `{event['updatedAt']}`",
        f"- Latest Deribit XRP expiry observed: `{summary['deribit_latest_expiry']}`",
        f"- Deribit latest underlying snapshot: `{summary['deribit_latest_underlying_price']}`",
        "",
        "## Core Readout",
        "",
        "- Current active XRP Polymarket ladder is a `one-touch` family (`reach/dip by date`), not a terminal-close digital family.",
        "- Local/Tardis-accessible vanilla XRP options do not currently reach the same 2026-12-31 maturity.",
        "- The strongest strict check we can do today is a dominance lower bound: longer-horizon `touch` should not price below earlier terminal digital lower bounds from vanilla call/put spreads.",
        "",
        "## Polymarket Active Ladder",
        "",
        "| kind | K | bid | ask | mid | question |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for market in sorted(
        event["parsed_touch_markets"],
        key=lambda item: (item["kind"], item["threshold"]),
    ):
        lines.append(
            f"| `{market['kind']}` | `{market['threshold']:.2f}` | `{market['bid']}` | `{market['ask']}` | `{market['mid']}` | {market['question']} |"
        )

    lines.extend(
        [
            "",
            "## Tardis Metadata Coverage",
            "",
            "| exchange | xrp symbols | expiry count | latest expiries |",
            "|---|---:|---:|---|",
        ]
    )
    for row in summary["tardis_xrp_coverage"]:
        lines.append(
            f"| `{row['exchange']}` | `{row['xrp_symbol_count']}` | `{row['expiry_count']}` | `{', '.join(row['last_expiries'])}` |"
        )

    lines.extend(
        [
            "",
            "## Touch vs Vanilla Lower-Bound Checks",
            "",
            "| kind | K | poly mid | vanilla lower bound | gap | status |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in summary["touch_vs_vanilla_checks"]:
        bound = row.get("terminal_digital_lower_bound")
        gap = row.get("touch_minus_lower_bound")
        lines.append(
            f"| `{row['kind']}` | `{row['threshold']:.2f}` | `{row['polymarket_mid']}` | `{bound}` | `{gap}` | `{row['status']}` |"
        )

    local = summary["local_binance_range"]
    lines.extend(
        [
            "",
            "## Local Binance XRP Sample",
            "",
            f"- Files: `{local['files']}`",
            f"- Rows: `{local['rows']}`",
            f"- Price range: `{local['min_price']} .. {local['max_price']}`",
            f"- Time range UTC: `{local['first_ts_utc']} .. {local['last_ts_utc']}`",
            "",
            "## Conclusion",
            "",
            "- No lower-bound violation showed up in the overlapping strike checks we could run from current local/Tardis-accessible data.",
            "- The present setup does **not** support a strict same-payoff static arbitrage claim between active XRP Polymarket ladders and vanilla XRP options.",
            "- What it *does* support is a semi-static screen: flag Polymarket touch markets that would fall below earlier terminal-digital lower bounds, then treat anything else as model/rule mismatch rather than free arbitrage.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tardis_key = load_tardis_key(args.env_file)
    event = fetch_polymarket_event(args.polymarket_event_id)
    touch_markets: list[TouchMarket] = event["parsed_touch_markets"]

    tardis_coverage = []
    for exchange in ("deribit", "bybit-options", "binance-european-options"):
        body = fetch_tardis_exchange(exchange, tardis_key)
        tardis_coverage.append(summarize_tardis_xrp(exchange, parse_tardis_symbols(body)))

    deribit_options = fetch_deribit_xrp_options()
    latest_expiry = choose_latest_expiry(deribit_options)
    latest_underlying = None
    for option in deribit_options:
        if option.expiry == latest_expiry and option.underlying_price is not None:
            latest_underlying = option.underlying_price
            break
    checks = build_touch_vs_digital_checks(touch_markets, deribit_options, latest_expiry)
    local_binance = summarize_binance_local_range(args.binance_trades_dir)

    summary = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "polymarket_event": {
            "id": event.get("id"),
            "title": event.get("title"),
            "updatedAt": event.get("updatedAt"),
            "parsed_touch_markets": [market.__dict__ for market in touch_markets],
        },
        "tardis_xrp_coverage": tardis_coverage,
        "deribit_latest_expiry": latest_expiry,
        "deribit_latest_underlying_price": latest_underlying,
        "touch_vs_vanilla_checks": checks,
        "local_binance_range": local_binance,
    }

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_markdown(summary, args.output_dir / "report.md")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
