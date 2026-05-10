from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any


getcontext().prec = 60

RUN_TAG = "20260509"
DATE_DIR = Path("date")
DOCS_DIR = Path("docs")

MON_TOKEN = "0x3bd359C1119dA7Da1D913D1C4D2B7c461115433A"
USDC_TOKEN = "0x754704Bc059F8C67012fEd69BC8A327a5aafb603"
DEX_CHAIN = "monad"
PUBLIC_RPC = "https://rpc.monad.xyz"

V2_SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe61363d4b8e3ee75a7d8e5be0c7f3b6a"
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
PANCAKE_V3_SWAP_TOPIC = "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83"
TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"
DECIMALS_SELECTOR = "0x313ce567"

POOL_CANDIDATES_CSV = DATE_DIR / f"mon_usdc_pool_candidates_{RUN_TAG}.csv"
SWAPS_SAMPLE_CSV = DATE_DIR / f"mon_usdc_v1_swaps_sample_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"mon_usdc_v1_data_plan_{RUN_TAG}.md"


@dataclass(frozen=True)
class PoolCandidate:
    fetched_at_utc: str
    chain_id: str
    dex_id: str
    labels: str
    pair_address: str
    base_address: str
    base_symbol: str
    quote_address: str
    quote_symbol: str
    price_usd: str
    liquidity_usd: float
    volume_m5_usd: float
    volume_h1_usd: float
    volume_h6_usd: float
    volume_h24_usd: float
    m5_buys: int
    m5_sells: int
    h1_buys: int
    h1_sells: int
    h6_buys: int
    h6_sells: int
    h24_buys: int
    h24_sells: int
    pair_created_at: str
    url: str

    @property
    def family_hint(self) -> str:
        label_set = {label.strip().lower() for label in self.labels.split("|") if label.strip()}
        if "v3" in label_set:
            return "v3"
        if "v2" in label_set or "v2.2" in label_set:
            return "v2"
        return "unknown"


@dataclass(frozen=True)
class PoolMetadata:
    candidate: PoolCandidate
    token0_address: str
    token1_address: str
    token0_decimals: int
    token1_decimals: int
    mon_token_index: int
    usdc_token_index: int


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover MON/USDC pools and collect a small swap-only v1 sample."
    )
    parser.add_argument("--chain", default=DEX_CHAIN)
    parser.add_argument("--blocks", type=int, default=5_000)
    parser.add_argument("--from-block", type=int)
    parser.add_argument("--to-block", type=int)
    parser.add_argument("--pool-address", action="append", default=[])
    parser.add_argument("--top-pools", type=int, default=2)
    parser.add_argument("--log-range-blocks", type=int, default=250)
    parser.add_argument("--log-batch-size", type=int, default=8)
    parser.add_argument("--rpc-url", action="append", default=[])
    parser.add_argument("--env-file", default=".env.chog.local")
    parser.add_argument("--skip-swaps", action="store_true")
    args = parser.parse_args()

    if args.blocks <= 0:
        raise SystemExit("--blocks must be positive")
    if args.log_range_blocks <= 0:
        raise SystemExit("--log-range-blocks must be positive")
    if args.log_batch_size <= 0:
        raise SystemExit("--log-batch-size must be positive")

    DATE_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    fetched_at = utc_now()

    rpc_urls = resolve_rpc_urls(args.rpc_url, Path(args.env_file))
    candidates = discover_mon_usdc_pools(args.chain, fetched_at)
    write_pool_candidates(candidates, POOL_CANDIDATES_CSV)

    selected = select_pools(candidates, args.pool_address, args.top_pools)
    rows: list[dict[str, Any]] = []
    from_block = args.from_block
    to_block = args.to_block

    if not args.skip_swaps and selected:
        client = RpcClient(rpc_urls)
        latest_block = client.call("eth_blockNumber", [])
        latest_block_int = int(latest_block, 16)
        if to_block is None:
            to_block = latest_block_int
        if from_block is None:
            from_block = max(0, to_block - args.blocks + 1)
        if from_block > to_block:
            raise SystemExit("--from-block must be <= --to-block")

        metadata = []
        skipped_metadata: list[str] = []
        for pool in selected:
            try:
                metadata.append(resolve_pool_metadata(client, pool))
            except Exception as exc:
                skipped_metadata.append(f"{pool.pair_address}: {exc}")
        rows = collect_swap_rows(
            client=client,
            metadata=metadata,
            from_block=from_block,
            to_block=to_block,
            log_range_blocks=args.log_range_blocks,
            log_batch_size=args.log_batch_size,
            fetched_at_utc=fetched_at,
        )
        write_swap_rows(rows, SWAPS_SAMPLE_CSV)
    else:
        write_swap_rows(rows, SWAPS_SAMPLE_CSV)

    write_report(
        candidates=candidates,
        selected=selected,
        rows=rows,
        from_block=from_block,
        to_block=to_block,
        report_path=REPORT_MD,
    )

    print(f"pool candidates: {len(candidates)} -> {POOL_CANDIDATES_CSV}")
    print(f"selected pools: {len(selected)}")
    print(f"swap rows: {len(rows)} -> {SWAPS_SAMPLE_CSV}")
    print(f"report: {REPORT_MD}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json",
            "user-agent": "finance-chain-mon-usdc-v1/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_mon_usdc_pools(chain: str, fetched_at_utc: str) -> list[PoolCandidate]:
    rows: dict[str, PoolCandidate] = {}
    for token in (MON_TOKEN, USDC_TOKEN):
        url = f"https://api.dexscreener.com/token-pairs/v1/{chain}/{token}"
        for pair in http_json(url):
            candidate = pair_to_candidate(pair, fetched_at_utc)
            if is_mon_usdc_candidate(candidate):
                rows[candidate.pair_address.lower()] = candidate
    candidates = list(rows.values())
    candidates.sort(
        key=lambda row: (
            row.liquidity_usd,
            row.volume_h24_usd,
            row.pair_address.lower(),
        ),
        reverse=True,
    )
    return candidates


def pair_to_candidate(pair: dict[str, Any], fetched_at_utc: str) -> PoolCandidate:
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    liquidity = pair.get("liquidity") or {}
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    m5 = txns.get("m5") or {}
    h1 = txns.get("h1") or {}
    h6 = txns.get("h6") or {}
    h24 = txns.get("h24") or {}
    return PoolCandidate(
        fetched_at_utc=fetched_at_utc,
        chain_id=str(pair.get("chainId") or ""),
        dex_id=str(pair.get("dexId") or ""),
        labels="|".join(pair.get("labels") or []),
        pair_address=str(pair.get("pairAddress") or ""),
        base_address=str(base.get("address") or ""),
        base_symbol=str(base.get("symbol") or ""),
        quote_address=str(quote.get("address") or ""),
        quote_symbol=str(quote.get("symbol") or ""),
        price_usd=str(pair.get("priceUsd") or ""),
        liquidity_usd=float_or_zero(liquidity.get("usd")),
        volume_m5_usd=float_or_zero(volume.get("m5")),
        volume_h1_usd=float_or_zero(volume.get("h1")),
        volume_h6_usd=float_or_zero(volume.get("h6")),
        volume_h24_usd=float_or_zero(volume.get("h24")),
        m5_buys=int_or_zero(m5.get("buys")),
        m5_sells=int_or_zero(m5.get("sells")),
        h1_buys=int_or_zero(h1.get("buys")),
        h1_sells=int_or_zero(h1.get("sells")),
        h6_buys=int_or_zero(h6.get("buys")),
        h6_sells=int_or_zero(h6.get("sells")),
        h24_buys=int_or_zero(h24.get("buys")),
        h24_sells=int_or_zero(h24.get("sells")),
        pair_created_at=str(pair.get("pairCreatedAt") or ""),
        url=str(pair.get("url") or ""),
    )


def is_mon_usdc_candidate(row: PoolCandidate) -> bool:
    addresses = {row.base_address.lower(), row.quote_address.lower()}
    return MON_TOKEN.lower() in addresses and USDC_TOKEN.lower() in addresses


def float_or_zero(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def int_or_zero(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def write_pool_candidates(rows: list[PoolCandidate], path: Path) -> None:
    fieldnames = [
        "fetched_at_utc",
        "rank_liquidity",
        "chain_id",
        "dex_id",
        "labels",
        "family_hint",
        "pair_address",
        "base_address",
        "base_symbol",
        "quote_address",
        "quote_symbol",
        "price_usd",
        "liquidity_usd",
        "volume_m5_usd",
        "volume_h1_usd",
        "volume_h6_usd",
        "volume_h24_usd",
        "m5_buys",
        "m5_sells",
        "h1_buys",
        "h1_sells",
        "h6_buys",
        "h6_sells",
        "h24_buys",
        "h24_sells",
        "pair_created_at",
        "url",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            payload = row.__dict__.copy()
            payload["rank_liquidity"] = index
            payload["family_hint"] = row.family_hint
            writer.writerow(payload)


def select_pools(
    candidates: list[PoolCandidate], addresses: list[str], top_pools: int
) -> list[PoolCandidate]:
    if addresses:
        wanted = {address.lower() for address in addresses}
        return [pool for pool in candidates if pool.pair_address.lower() in wanted]
    return candidates[:top_pools]


class RpcClient:
    def __init__(self, rpc_urls: list[str]) -> None:
        if not rpc_urls:
            raise ValueError("at least one RPC URL is required")
        self.rpc_urls = rpc_urls
        self.index = 0
        self.next_id = 1

    def call(self, method: str, params: list[Any]) -> Any:
        response = self.batch([{"method": method, "params": params}])[0]
        if "error" in response:
            raise RuntimeError(f"{method} failed: {response['error']}")
        return response.get("result")

    def batch(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not calls:
            return []
        body = []
        for call in calls:
            body.append(
                {
                    "jsonrpc": "2.0",
                    "id": self.next_id,
                    "method": call["method"],
                    "params": call.get("params", []),
                }
            )
            self.next_id += 1

        last_error: Exception | None = None
        attempts = max(1, len(self.rpc_urls) * 3)
        for attempt in range(attempts):
            rpc_url = self.rpc_urls[self.index % len(self.rpc_urls)]
            self.index += 1
            try:
                return rpc_post_json(rpc_url, body)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"RPC batch failed after {attempts} attempts: {last_error}")


def rpc_post_json(rpc_url: str, body: Any) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        rpc_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "finance-chain-mon-usdc-v1/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"RPC HTTP {exc.code}: {text[:500]}") from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected RPC response shape: {data!r}")
    by_id = {item.get("id"): item for item in data}
    return [by_id.get(item["id"], {"error": "missing batch response"}) for item in body]


def resolve_pool_metadata(client: RpcClient, pool: PoolCandidate) -> PoolMetadata:
    token0 = decode_address_word(
        client.call("eth_call", [{"to": pool.pair_address, "data": TOKEN0_SELECTOR}, "latest"])
    )
    token1 = decode_address_word(
        client.call("eth_call", [{"to": pool.pair_address, "data": TOKEN1_SELECTOR}, "latest"])
    )
    token0_decimals = int(
        client.call("eth_call", [{"to": token0, "data": DECIMALS_SELECTOR}, "latest"]), 16
    )
    token1_decimals = int(
        client.call("eth_call", [{"to": token1, "data": DECIMALS_SELECTOR}, "latest"]), 16
    )
    token0_lower = token0.lower()
    token1_lower = token1.lower()
    mon = MON_TOKEN.lower()
    usdc = USDC_TOKEN.lower()
    if token0_lower == mon:
        mon_index = 0
    elif token1_lower == mon:
        mon_index = 1
    else:
        raise ValueError(f"token0/token1 do not include MON: {token0}/{token1}")
    if token0_lower == usdc:
        usdc_index = 0
    elif token1_lower == usdc:
        usdc_index = 1
    else:
        raise ValueError(f"token0/token1 do not include USDC: {token0}/{token1}")
    return PoolMetadata(
        candidate=pool,
        token0_address=token0,
        token1_address=token1,
        token0_decimals=token0_decimals,
        token1_decimals=token1_decimals,
        mon_token_index=mon_index,
        usdc_token_index=usdc_index,
    )


def decode_address_word(value: str) -> str:
    word = value.removeprefix("0x")
    if len(word) < 64:
        raise ValueError(f"address return is shorter than 32 bytes: {value}")
    return "0x" + word[-40:].lower()


def collect_swap_rows(
    client: RpcClient,
    metadata: list[PoolMetadata],
    from_block: int,
    to_block: int,
    log_range_blocks: int,
    log_batch_size: int,
    fetched_at_utc: str,
) -> list[dict[str, Any]]:
    if not metadata:
        return []
    by_address = {pool.candidate.pair_address.lower(): pool for pool in metadata}
    addresses = [pool.candidate.pair_address for pool in metadata]
    ranges: list[tuple[int, int]] = []
    start = from_block
    while start <= to_block:
        end = min(to_block, start + log_range_blocks - 1)
        ranges.append((start, end))
        start = end + 1

    logs: list[dict[str, Any]] = []
    for offset in range(0, len(ranges), log_batch_size):
        batch_ranges = ranges[offset : offset + log_batch_size]
        calls = [
            {
                "method": "eth_getLogs",
                "params": [
                    {
                        "address": addresses,
                        "fromBlock": hex(start_block),
                        "toBlock": hex(end_block),
                        "topics": [[V2_SWAP_TOPIC, V3_SWAP_TOPIC, PANCAKE_V3_SWAP_TOPIC]],
                    }
                ],
            }
            for start_block, end_block in batch_ranges
        ]
        responses = client.batch(calls)
        for response in responses:
            if response.get("error"):
                raise RuntimeError(f"eth_getLogs failed: {response['error']}")
            logs.extend(response.get("result") or [])

    block_timestamps = fetch_block_timestamps(client, sorted({int(log["blockNumber"], 16) for log in logs}))
    rows = []
    for log in logs:
        pool = by_address.get(str(log.get("address", "")).lower())
        if pool is None:
            continue
        row = parse_swap_log(fetched_at_utc, pool, log, block_timestamps)
        rows.append(row)
    rows.sort(
        key=lambda row: (
            int(row["block_number"]),
            int(row["transaction_index"]),
            int(row["log_index"]),
            row["pool_address"],
        )
    )
    return rows


def fetch_block_timestamps(client: RpcClient, blocks: list[int]) -> dict[int, int]:
    timestamps: dict[int, int] = {}
    batch_size = 50
    for offset in range(0, len(blocks), batch_size):
        chunk = blocks[offset : offset + batch_size]
        calls = [
            {"method": "eth_getBlockByNumber", "params": [hex(block), False]} for block in chunk
        ]
        responses = client.batch(calls)
        for block, response in zip(chunk, responses):
            if response.get("error") or not response.get("result"):
                continue
            timestamps[block] = int(response["result"].get("timestamp", "0x0"), 16)
    return timestamps


def parse_swap_log(
    fetched_at_utc: str,
    pool: PoolMetadata,
    log: dict[str, Any],
    block_timestamps: dict[int, int],
) -> dict[str, Any]:
    topics = [str(topic).lower() for topic in log.get("topics") or []]
    if len(topics) < 3:
        raise ValueError(f"swap log has fewer than 3 topics: {topics}")
    topic0 = topics[0]
    if topic0 == V2_SWAP_TOPIC:
        family = "v2"
        amount0_delta_raw, amount1_delta_raw, sqrt_price_x96, liquidity_raw, tick = parse_v2_deltas(
            str(log["data"])
        )
    elif topic0 == V3_SWAP_TOPIC:
        family = "v3"
        amount0_delta_raw, amount1_delta_raw, sqrt_price_x96, liquidity_raw, tick = parse_v3_deltas(
            str(log["data"])
        )
    elif topic0 == PANCAKE_V3_SWAP_TOPIC:
        family = "pancake_v3"
        amount0_delta_raw, amount1_delta_raw, sqrt_price_x96, liquidity_raw, tick = parse_v3_deltas(
            str(log["data"])
        )
    else:
        raise ValueError(f"unknown swap topic: {topic0}")

    block_number = int(log["blockNumber"], 16)
    block_timestamp = block_timestamps.get(block_number, 0)
    block_datetime = (
        datetime.fromtimestamp(block_timestamp, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
        if block_timestamp
        else ""
    )
    mon_delta_raw = amount0_delta_raw if pool.mon_token_index == 0 else amount1_delta_raw
    usdc_delta_raw = amount0_delta_raw if pool.usdc_token_index == 0 else amount1_delta_raw
    mon_decimals = pool.token0_decimals if pool.mon_token_index == 0 else pool.token1_decimals
    usdc_decimals = pool.token0_decimals if pool.usdc_token_index == 0 else pool.token1_decimals
    mon_abs = scale_decimal(abs(mon_delta_raw), mon_decimals)
    usdc_abs = scale_decimal(abs(usdc_delta_raw), usdc_decimals)
    price = usdc_abs / mon_abs if mon_abs != 0 else Decimal(0)
    direction = "sell_mon" if mon_delta_raw > 0 else "buy_mon" if mon_delta_raw < 0 else "unknown"

    return {
        "fetched_at_utc": fetched_at_utc,
        "block_number": block_number,
        "block_timestamp": block_timestamp,
        "block_datetime_utc": block_datetime,
        "transaction_hash": log.get("transactionHash", ""),
        "transaction_index": int(log.get("transactionIndex", "0x0"), 16),
        "log_index": int(log.get("logIndex", "0x0"), 16),
        "pool_address": str(log.get("address", "")).lower(),
        "dex_id": pool.candidate.dex_id,
        "family": family,
        "swap_topic": topic0,
        "sender": topic_to_address(topics[1]),
        "recipient": topic_to_address(topics[2]),
        "token0_address": pool.token0_address,
        "token1_address": pool.token1_address,
        "token0_decimals": pool.token0_decimals,
        "token1_decimals": pool.token1_decimals,
        "amount0_delta_raw": amount0_delta_raw,
        "amount1_delta_raw": amount1_delta_raw,
        "amount0_delta_token": decimal_to_string(
            scale_decimal_signed(amount0_delta_raw, pool.token0_decimals)
        ),
        "amount1_delta_token": decimal_to_string(
            scale_decimal_signed(amount1_delta_raw, pool.token1_decimals)
        ),
        "direction": direction,
        "mon_abs": decimal_to_string(mon_abs),
        "usdc_abs": decimal_to_string(usdc_abs),
        "price_usdc_per_mon": decimal_to_string(price),
        "sqrt_price_x96": sqrt_price_x96,
        "liquidity_raw": liquidity_raw,
        "tick": tick,
        "removed": bool(log.get("removed", False)),
    }


def parse_v2_deltas(data: str) -> tuple[int, int, str, str, str]:
    chunks = data_chunks(data)
    if len(chunks) < 4:
        raise ValueError(f"v2 data has fewer than 4 words: {data}")
    amount0_in = int(chunks[0], 16)
    amount1_in = int(chunks[1], 16)
    amount0_out = int(chunks[2], 16)
    amount1_out = int(chunks[3], 16)
    return amount0_in - amount0_out, amount1_in - amount1_out, "", "", ""


def parse_v3_deltas(data: str) -> tuple[int, int, str, str, str]:
    chunks = data_chunks(data)
    if len(chunks) < 5:
        raise ValueError(f"v3 data has fewer than 5 words: {data}")
    return (
        parse_i256(chunks[0]),
        parse_i256(chunks[1]),
        str(int(chunks[2], 16)),
        str(int(chunks[3], 16)),
        str(parse_i256(chunks[4])),
    )


def data_chunks(data: str) -> list[str]:
    text = data.removeprefix("0x")
    if len(text) % 64 != 0:
        raise ValueError(f"data length is not a multiple of 32 bytes: {data}")
    return [text[index : index + 64] for index in range(0, len(text), 64)]


def parse_i256(word: str) -> int:
    value = int(word, 16)
    if value >= 1 << 255:
        value -= 1 << 256
    return value


def scale_decimal(value: int, decimals: int) -> Decimal:
    return Decimal(value) / (Decimal(10) ** decimals)


def scale_decimal_signed(value: int, decimals: int) -> Decimal:
    sign = Decimal(-1) if value < 0 else Decimal(1)
    return sign * scale_decimal(abs(value), decimals)


def decimal_to_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def topic_to_address(topic: str) -> str:
    text = topic.removeprefix("0x")
    if len(text) != 64:
        return ""
    return "0x" + text[-40:]


def write_swap_rows(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "fetched_at_utc",
        "block_number",
        "block_timestamp",
        "block_datetime_utc",
        "transaction_hash",
        "transaction_index",
        "log_index",
        "pool_address",
        "dex_id",
        "family",
        "swap_topic",
        "sender",
        "recipient",
        "token0_address",
        "token1_address",
        "token0_decimals",
        "token1_decimals",
        "amount0_delta_raw",
        "amount1_delta_raw",
        "amount0_delta_token",
        "amount1_delta_token",
        "direction",
        "mon_abs",
        "usdc_abs",
        "price_usdc_per_mon",
        "sqrt_price_x96",
        "liquidity_raw",
        "tick",
        "removed",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    candidates: list[PoolCandidate],
    selected: list[PoolCandidate],
    rows: list[dict[str, Any]],
    from_block: int | None,
    to_block: int | None,
    report_path: Path,
) -> None:
    total_rows = len(rows)
    buy_rows = sum(1 for row in rows if row.get("direction") == "buy_mon")
    sell_rows = sum(1 for row in rows if row.get("direction") == "sell_mon")
    total_usdc = sum(Decimal(str(row.get("usdc_abs") or "0")) for row in rows)
    by_pool: dict[str, dict[str, Any]] = {}
    for row in rows:
        pool = str(row["pool_address"])
        item = by_pool.setdefault(
            pool,
            {"dex_id": row["dex_id"], "rows": 0, "usdc": Decimal(0), "buy": 0, "sell": 0},
        )
        item["rows"] += 1
        item["usdc"] += Decimal(str(row.get("usdc_abs") or "0"))
        if row.get("direction") == "buy_mon":
            item["buy"] += 1
        elif row.get("direction") == "sell_mon":
            item["sell"] += 1

    top_candidates = candidates[:8]
    lines = [
        "# MON/USDC V1 Data Plan",
        "",
        f"Status: {utc_now()}",
        "",
        "## Why Pivot",
        "",
        "CHOG 的事件因子更适合作为研究样本，不适合作为第一阶段可执行市场。MON/USDC 的池子明显更深，且 USDC 计价让净收益、盘口冲击、库存风险和资金费率都更容易建模。",
        "",
        "## Pool Discovery",
        "",
        f"- Candidate CSV: `{POOL_CANDIDATES_CSV.as_posix()}`",
        f"- MON token: `{MON_TOKEN}`",
        f"- USDC token: `{USDC_TOKEN}`",
        "",
        "| rank | dex | family | pair | liquidity_usd | volume_h24_usd | h24 txns |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for index, pool in enumerate(top_candidates, start=1):
        txns = pool.h24_buys + pool.h24_sells
        lines.append(
            f"| {index} | {pool.dex_id} | {pool.family_hint} | `{short_hex(pool.pair_address)}` | "
            f"{pool.liquidity_usd:,.2f} | {pool.volume_h24_usd:,.2f} | {txns:,} |"
        )
    lines.extend(
        [
            "",
            "## V1 Collection Shape",
            "",
            "本版只做 swap-only:",
            "",
            "- 从 DexScreener 发现 MON/USDC 池。",
            "- 对选中的池直接抓 `eth_getLogs`，topic 覆盖 Uniswap V2/V3 Swap 和 Pancake v3 扩展 Swap。",
            "- 用 `token0()` / `token1()` / `decimals()` 解析真实池内顺序，避免把 DexScreener base/quote 误当 AMM token0/token1。",
            "- 输出方向只定义为 `buy_mon` / `sell_mon`，先不假设 maker/挂单，也不做 CHOG 那套高成本 taker 因子。",
            "",
            "## Sample Result",
            "",
            f"- Swap CSV: `{SWAPS_SAMPLE_CSV.as_posix()}`",
            f"- Block window: `{from_block}`..`{to_block}`",
            f"- Selected pools: {len(selected)}",
            f"- Swap rows: {total_rows:,}",
            f"- Direction counts: buy_mon={buy_rows:,}, sell_mon={sell_rows:,}",
            f"- Decoded notional: {total_usdc:,.2f} USDC",
            "",
        ]
    )
    if by_pool:
        lines.extend(
            [
                "| pool | dex | rows | usdc_abs | buy | sell |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for pool, item in sorted(
            by_pool.items(), key=lambda pair: (pair[1]["usdc"], pair[1]["rows"]), reverse=True
        ):
            lines.append(
                f"| `{short_hex(pool)}` | {item['dex_id']} | {item['rows']:,} | "
                f"{item['usdc']:,.2f} | {item['buy']:,} | {item['sell']:,} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Next Step",
            "",
            "如果这个样本稳定，下一步应把 MON/USDC 做成独立 market 数据根，而不是塞进 `data/chog/v1`:",
            "",
            "```text",
            "data/mon_usdc/v1/raw/pool_swap_logs",
            "data/mon_usdc/v1/raw/event_block_headers",
            "data/mon_usdc/v1/raw/tx_receipts",
            "data/mon_usdc/v1/derived/swap_event_features",
            "```",
            "",
            "策略研究上应先研究可执行微观结构因子: 成交强度、买卖冲击、短周期波动、池间价差、gas/拥挤和库存偏移。CHOG 的第一性原理因子框架可以复用，但成本模型要换成 MON/USDC 的真实池 fee、tick liquidity 和下单方式。",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def short_hex(value: str, chars: int = 6) -> str:
    if not value or len(value) <= 2 * chars + 2:
        return value
    return f"{value[: chars + 2]}...{value[-chars:]}"


def resolve_rpc_urls(cli_urls: list[str], env_file: Path) -> list[str]:
    urls: list[str] = []
    urls.extend(url for url in cli_urls if url)
    for name in (
        "MON_USDC_RPC_URLS",
        "MONAD_RPC_URLS",
        "CHOG_LOG_RPCS",
        "CHOG_PUBLIC_LOG_RPCS",
        "CHOG_HEADER_RPC",
        "RPC_URL",
    ):
        value = os.environ.get(name)
        if value:
            urls.extend(split_env_values(value))
    if env_file.exists():
        values = parse_env_file(env_file)
        for name in (
            "MON_USDC_RPC_URLS",
            "MONAD_RPC_URLS",
            "CHOG_LOG_RPCS",
            "CHOG_PUBLIC_LOG_RPCS",
            "CHOG_HEADER_RPC",
            "RPC_URL",
        ):
            if name in values:
                urls.extend(split_env_values(values[name]))
    if not urls:
        urls.append(PUBLIC_RPC)
    deduped = []
    seen = set()
    for url in urls:
        stripped = url.strip().strip("\"'")
        if stripped and stripped not in seen:
            deduped.append(stripped)
            seen.add(stripped)
    return deduped


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index].strip()
        index += 1
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
        if value.startswith("[") and not value.endswith("]"):
            parts = [value]
            while index < len(lines):
                parts.append(lines[index].strip())
                if lines[index].strip().endswith("]"):
                    index += 1
                    break
                index += 1
            value = " ".join(parts)
        values[name] = strip_inline_comment(value).strip()
    return values


def strip_inline_comment(value: str) -> str:
    quote: str | None = None
    for index, char in enumerate(value):
        if char in ("'", '"'):
            quote = None if quote == char else char if quote is None else quote
        elif char == "#" and quote is None:
            return value[:index]
    return value


def split_env_values(value: str) -> list[str]:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.replace("\n", ",")
    parts = re.split(r",|\s+", text)
    return [part.strip().strip("\"'") for part in parts if part.strip().strip("\"'")]


if __name__ == "__main__":
    main()
