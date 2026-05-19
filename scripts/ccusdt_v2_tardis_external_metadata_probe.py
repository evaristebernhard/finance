#!/usr/bin/env python
"""Metadata-only Tardis probe for external CCUSDT venue feasibility."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_tardis_external_metadata_probe_no_download_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_tardis_external_metadata_probe_v1"
DEFAULT_ENV_FILE = Path(".env.chog.local")
DEFAULT_EXCHANGES = "bullish,binance,binance-futures,bybit,bybit-futures,okex,okex-futures,kucoin,gate-io,mexc,coinbase"
DEFAULT_SYMBOLS = "ccusdt,ccusdc,cc-usdt,cc-usdc,CCUSDT,CCUSDC"


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def probe_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tardis_external_metadata_probe_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tardis_external_metadata_probe_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-tardis-external-metadata-probe-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Tardis metadata for external CCUSDT venue feasibility.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--exchanges", default=DEFAULT_EXCHANGES)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 80) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def load_tardis_key(env_file: Path) -> str:
    env_key = os.environ.get("TARDIS_API_KEY", "").strip()
    if env_key:
        if len(env_key) < 20:
            raise SystemExit("TARDIS_API_KEY exists in environment but is too short")
        return env_key
    if not env_file.exists():
        raise SystemExit(f"TARDIS_API_KEY not found; env file does not exist: {env_file}")
    text = env_file.read_text(encoding="utf-8")
    match = re.search(r'(?im)^\s*TARDIS_API_KEY\s*=\s*["\']?([^\r\n"\']+)', text)
    if not match:
        raise SystemExit(f"TARDIS_API_KEY not found in {env_file}")
    key = match.group(1).strip()
    if len(key) < 20:
        raise SystemExit("TARDIS_API_KEY exists but is too short")
    return key


def request_json(url: str, api_key: str, timeout_seconds: float) -> tuple[int | None, Any, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "finance-chain-ccusdt-tardis-metadata-probe/0.1",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", errors="replace")
            return response.status, json.loads(text) if text else None, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read()[:400]
        return exc.code, None, raw.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"


def access_exchanges(body: Any) -> set[str]:
    if not isinstance(body, list):
        return set()
    out: set[str] = set()
    for item in body:
        if isinstance(item, dict) and item.get("exchange"):
            out.add(str(item["exchange"]))
    return out


def extract_symbols(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    raw_symbols = body.get("availableSymbols") or body.get("symbols") or []
    out: list[dict[str, Any]] = []
    if not isinstance(raw_symbols, list):
        return out
    for item in raw_symbols:
        if isinstance(item, str):
            out.append({"id": item})
        elif isinstance(item, dict):
            symbol_id = str(item.get("id") or item.get("symbol") or "")
            row = dict(item)
            row["id"] = symbol_id
            out.append(row)
    return out


def summarize_exchange(exchange: str, body: Any, target_symbols: list[str], requested_access: bool) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {
            "exchange": exchange,
            "external_exchange": exchange != "bullish",
            "requested_exchange_access": requested_access,
            "symbol_count": 0,
            "matched_symbols": "",
            "cc_symbol_present": False,
            "available_channels": "",
            "has_l2_channel": False,
        }
    channels = body.get("availableChannels") or body.get("channels") or []
    if not isinstance(channels, list):
        channels = []
    symbols = extract_symbols(body)
    target_set = {symbol.lower() for symbol in target_symbols}
    matches: list[str] = []
    for item in symbols:
        symbol_id = str(item.get("id") or "").strip()
        if symbol_id.lower() in target_set:
            matches.append(symbol_id)

    def is_orderbook_channel(channel: Any) -> bool:
        normalized = str(channel).strip().lower()
        if normalized in {
            "depth",
            "depthsnapshot",
            "bookticker",
            "book_ticker",
            "incremental_book_l2",
            "v1talevel2",
            "market/level2",
            "market/level2snapshot",
            "l2update",
            "snapshot",
            "bbo-tbt",
            "books",
            "books-l2-tbt",
            "spot/depth",
            "spot/depth_l2_tbt",
            "order_book_update",
            "obu",
        }:
            return True
        return (
            normalized.startswith("orderbook.")
            or normalized.startswith("orderbook_")
            or normalized.startswith("orderbook")
            or "orderbook" in normalized
            or "level2" in normalized
            or "l2" in normalized
        )

    has_l2 = any(is_orderbook_channel(channel) for channel in channels)
    return {
        "exchange": exchange,
        "external_exchange": exchange != "bullish",
        "requested_exchange_access": requested_access,
        "symbol_count": len(symbols),
        "matched_symbols": ",".join(sorted(set(matches))),
        "cc_symbol_present": bool(matches),
        "available_channels": ",".join(str(channel) for channel in channels),
        "has_l2_channel": bool(has_l2),
    }


def run_probe(exchanges: list[str], target_symbols: list[str], api_key: str, timeout_seconds: float) -> tuple[pd.DataFrame, dict[str, Any]]:
    access_status, access_body, access_error = request_json("https://api.tardis.dev/v1/api-key-info", api_key, timeout_seconds)
    access_set = access_exchanges(access_body)
    rows: list[dict[str, Any]] = []
    for exchange in exchanges:
        status, body, error = request_json(f"https://api.tardis.dev/v1/exchanges/{exchange}", api_key, timeout_seconds)
        row = summarize_exchange(exchange, body, target_symbols, exchange in access_set)
        row.update(
            {
                "metadata_http_status": status,
                "metadata_error": error[:240],
            }
        )
        rows.append(row)
    frame = pd.DataFrame(rows)
    cc_l2 = frame[frame["cc_symbol_present"].astype(bool) & frame["has_l2_channel"].astype(bool)]
    cc_external_l2 = cc_l2[cc_l2["external_exchange"].astype(bool)]
    cc_accessible_l2 = cc_l2[cc_l2["requested_exchange_access"].astype(bool)]
    cc_accessible_external_l2 = cc_external_l2[cc_external_l2["requested_exchange_access"].astype(bool)]
    summary = {
        "api_key_info_status": access_status,
        "api_key_info_error": access_error[:240],
        "exchanges_checked": exchanges,
        "target_symbols": target_symbols,
        "metadata_rows": int(len(frame)),
        "cc_l2_metadata_exchanges": sorted(cc_l2["exchange"].astype(str).tolist()) if not cc_l2.empty else [],
        "cc_external_l2_metadata_exchanges": sorted(cc_external_l2["exchange"].astype(str).tolist()) if not cc_external_l2.empty else [],
        "cc_accessible_l2_metadata_exchanges": sorted(cc_accessible_l2["exchange"].astype(str).tolist()) if not cc_accessible_l2.empty else [],
        "cc_accessible_external_l2_metadata_exchanges": (
            sorted(cc_accessible_external_l2["exchange"].astype(str).tolist()) if not cc_accessible_external_l2.empty else []
        ),
        "decision": (
            "external_tardis_cc_l2_metadata_blocked"
            if cc_accessible_external_l2.empty
            else "external_tardis_cc_l2_metadata_available"
        ),
    }
    return frame, summary


def write_report(paths: Paths, frame: pd.DataFrame, summary: dict[str, Any]) -> None:
    lines: list[str] = [
        "# CCUSDT V2 Tardis External Metadata Probe",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decision",
        "",
        f"Decision: `{summary['decision']}`.",
        "",
        "This is metadata-only. It does not download dataset bodies and does not print the Tardis API key.",
        "",
        "## Summary",
        "",
        f"- exchanges_checked: `{','.join(summary['exchanges_checked'])}`",
        f"- target_symbols: `{','.join(summary['target_symbols'])}`",
        f"- cc_l2_metadata_exchanges: `{','.join(summary['cc_l2_metadata_exchanges'])}`",
        f"- cc_external_l2_metadata_exchanges: `{','.join(summary['cc_external_l2_metadata_exchanges'])}`",
        f"- cc_accessible_l2_metadata_exchanges: `{','.join(summary['cc_accessible_l2_metadata_exchanges'])}`",
        f"- cc_accessible_external_l2_metadata_exchanges: `{','.join(summary['cc_accessible_external_l2_metadata_exchanges'])}`",
        "",
        "## Probe Rows",
        "",
        *markdown_table(
            frame,
            [
                "exchange",
                "external_exchange",
                "metadata_http_status",
                "requested_exchange_access",
                "symbol_count",
                "matched_symbols",
                "cc_symbol_present",
                "has_l2_channel",
                "metadata_error",
            ],
            80,
        ),
        "",
        "## Output Tables",
        "",
        f"- `{paths.probe_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_tardis_external_metadata_probe.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, frame: pd.DataFrame, summary: dict[str, Any]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(paths.probe_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        **summary,
        "outputs": {
            "probe_csv": str(paths.probe_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, frame, summary)


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    api_key = load_tardis_key(resolve_repo_path(args.env_file))
    exchanges = parse_csv_list(args.exchanges)
    target_symbols = parse_csv_list(args.symbols)
    frame, summary = run_probe(exchanges, target_symbols, api_key, args.timeout_seconds)
    write_outputs(paths, frame, summary)
    print(
        "[ccusdt_tardis_external_metadata_probe] "
        f"rows={len(frame)} decision={summary['decision']} wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
