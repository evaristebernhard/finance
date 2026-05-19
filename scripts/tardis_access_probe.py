#!/usr/bin/env python3
"""
Probe the local Tardis API key without printing the secret.

This is intentionally tiny and stdlib-only so it can be run from a fresh
Windows shell:

    python scripts\\tardis_access_probe.py --env-file .env.chog.local
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = Path(".env.chog.local")
DEFAULT_EXCHANGE = "binance-futures"
DEFAULT_SYMBOL = "monusdt"


def load_tardis_key(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r'(?im)^\s*TARDIS_API_KEY\s*=\s*["\']?([^\r\n"\']+)', text)
    if not match:
        raise SystemExit(f"TARDIS_API_KEY not found in {path}")
    key = match.group(1).strip()
    if len(key) < 20:
        raise SystemExit("TARDIS_API_KEY exists but is too short to be a usable key")
    return key


def request_json(url: str, key: str, timeout: float) -> tuple[int | None, Any, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "mon-usdc-tardis-access-probe",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
            return response.status, json.loads(text) if text else None, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read()[:500]
        return exc.code, None, raw.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"


def summarize_access_info(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "exchange": item.get("exchange"),
                "accessType": item.get("accessType"),
                "from": item.get("from"),
                "to": item.get("to"),
                "symbols": item.get("symbols") or "all_or_unspecified",
                "channels": item.get("channels") or "all_or_unspecified",
            }
        )
    return rows


def summarize_exchange(body: Any, symbol: str) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {"type": type(body).__name__}
    channels = body.get("availableChannels") or body.get("channels") or []
    symbols = body.get("availableSymbols") or body.get("symbols") or []
    symbol_ids: list[str] = []
    if isinstance(symbols, list):
        for value in symbols:
            if isinstance(value, str):
                symbol_ids.append(value)
            elif isinstance(value, dict):
                symbol_ids.append(str(value.get("id") or value.get("symbol") or ""))
    symbol_lc = symbol.lower()
    return {
        "id": body.get("id"),
        "name": body.get("name"),
        "enabled": body.get("enabled"),
        "channels_have_depth": "depth" in channels,
        "channels_have_depthSnapshot": "depthSnapshot" in channels,
        "channels_have_bookTicker": "bookTicker" in channels,
        "symbol_count": len(symbol_ids),
        "symbol_present": any(item.lower() == symbol_lc for item in symbol_ids),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Probe Tardis API key access safely.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args(argv)

    key = load_tardis_key(args.env_file)
    api_status, api_body, api_error = request_json(
        "https://api.tardis.dev/v1/api-key-info", key, args.timeout_seconds
    )
    exchange_status, exchange_body, exchange_error = request_json(
        f"https://api.tardis.dev/v1/exchanges/{args.exchange}", key, args.timeout_seconds
    )
    access_rows = summarize_access_info(api_body)
    output = {
        "env_file": str(args.env_file),
        "key_length": len(key),
        "api_key_info_status": api_status,
        "api_key_info_error": api_error[:240],
        "access": access_rows,
        "exchange_status": exchange_status,
        "exchange_error": exchange_error[:240],
        "exchange_summary": summarize_exchange(exchange_body, args.symbol)
        if exchange_status == 200
        else {},
        "requested_exchange_access": any(
            row.get("exchange") == args.exchange for row in access_rows
        ),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
