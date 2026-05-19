#!/usr/bin/env python
"""Inventory local external venue data for the CCUSDT V2 cross-market pivot."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_external_venue_inventory_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_external_venue_inventory_v1"
DATE_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})")
BINANCE_KLINE_RE = re.compile(r"(?P<symbol>[A-Z0-9]+)-(?P<interval>\d+[mhd])-?(?P<date>\d{4}-\d{2}-\d{2})\.csv$")


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def inventory_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_external_venue_inventory_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_external_venue_inventory_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-external-venue-inventory-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory local external venue data for CCUSDT cross-market research.")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 40) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def infer_venue_dataset(dataset: str) -> tuple[str, str]:
    if "_" not in dataset:
        return dataset, dataset
    venue, data_type = dataset.split("_", 1)
    return venue, data_type


def market_root_for(path: Path, data_root: Path) -> str:
    rel = path.relative_to(data_root)
    parts = rel.parts
    return parts[0] if parts else ""


def collect_symbol_dirs(data_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol_dir in data_root.glob("**/external/*/symbol=*"):
        if not symbol_dir.is_dir():
            continue
        dataset = symbol_dir.parent.name
        venue, data_type = infer_venue_dataset(dataset)
        symbol = symbol_dir.name.replace("symbol=", "")
        dates = sorted(
            match.group(1)
            for item in symbol_dir.glob("dt=*")
            if item.is_dir()
            for match in [DATE_RE.match(item.name)]
            if match
        )
        files = list(symbol_dir.glob("dt=*/*"))
        rows.append(
            {
                "market_root": market_root_for(symbol_dir, data_root),
                "venue": venue,
                "dataset": dataset,
                "data_type": data_type,
                "symbol": symbol,
                "date_count": len(set(dates)),
                "first_date": dates[0] if dates else "",
                "last_date": dates[-1] if dates else "",
                "file_count": len(files),
                "path": str(symbol_dir),
            }
        )
    return rows


def collect_binance_klines(data_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups: dict[tuple[str, str], list[Path]] = {}
    for path in data_root.glob("**/external/binance_spot_klines/*.csv"):
        match = BINANCE_KLINE_RE.match(path.name)
        if not match:
            continue
        groups.setdefault((match.group("symbol"), match.group("interval")), []).append(path)
    for (symbol, interval), files in sorted(groups.items()):
        dates = sorted(
            BINANCE_KLINE_RE.match(path.name).group("date")
            for path in files
            if BINANCE_KLINE_RE.match(path.name)
        )
        rows.append(
            {
                "market_root": market_root_for(files[0], data_root),
                "venue": "binance",
                "dataset": "binance_spot_klines",
                "data_type": f"spot_klines_{interval}",
                "symbol": symbol,
                "date_count": len(set(dates)),
                "first_date": dates[0] if dates else "",
                "last_date": dates[-1] if dates else "",
                "file_count": len(files),
                "path": str(files[0].parent),
            }
        )
    return rows


def build_inventory(data_root: Path) -> pd.DataFrame:
    rows = collect_symbol_dirs(data_root)
    rows.extend(collect_binance_klines(data_root))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["venue", "dataset", "symbol", "market_root"]).reset_index(drop=True)


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "ccusdt_l2_venues": [],
            "external_ccusdt_l2_ready": False,
            "same_venue_leader_symbols": [],
            "binance_kline_symbols": [],
        }
    l2_types = {"book_ticker", "trades", "incremental_book_L2", "book_snapshot_25"}
    cc = frame[frame["symbol"].astype(str).str.upper().eq("CCUSDT")].copy()
    cc_l2 = cc[cc["data_type"].isin(l2_types)]
    external_cc_l2 = cc_l2[cc_l2["venue"].ne("bullish")]
    same_venue = frame[(frame["venue"].eq("bullish")) & (frame["data_type"].isin({"book_ticker", "trades"}))]
    binance = frame[frame["dataset"].eq("binance_spot_klines")]
    return {
        "rows": int(len(frame)),
        "venues": sorted(frame["venue"].dropna().astype(str).unique().tolist()),
        "ccusdt_l2_venues": sorted(cc_l2["venue"].dropna().astype(str).unique().tolist()),
        "external_ccusdt_l2_ready": bool(len(external_cc_l2)),
        "external_ccusdt_l2_rows": int(len(external_cc_l2)),
        "same_venue_leader_symbols": sorted(same_venue["symbol"].dropna().astype(str).unique().tolist()),
        "binance_kline_symbols": sorted(binance["symbol"].dropna().astype(str).unique().tolist()),
        "decision": "external_venue_ccusdt_l2_data_blocked" if external_cc_l2.empty else "external_venue_ccusdt_l2_available",
    }


def write_report(paths: Paths, frame: pd.DataFrame, summary: dict[str, Any]) -> None:
    lines: list[str] = [
        "# CCUSDT V2 External Venue Inventory",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decision",
        "",
        f"Decision: `{summary['decision']}`.",
        "",
        "Local data does not contain CCUSDT L2 on an external venue. The cross-market pivot can use same-venue Bullish leaders and coarse Binance 1m context, but not a synchronized external CCUSDT/CC-related L2 market from current local files.",
        "",
        "## Summary",
        "",
        f"- inventory_rows: `{summary['rows']}`",
        f"- venues: `{','.join(summary.get('venues', []))}`",
        f"- ccusdt_l2_venues: `{','.join(summary['ccusdt_l2_venues'])}`",
        f"- external_ccusdt_l2_ready: `{summary['external_ccusdt_l2_ready']}`",
        f"- same_venue_leader_symbols: `{','.join(summary['same_venue_leader_symbols'])}`",
        f"- binance_kline_symbols: `{','.join(summary['binance_kline_symbols'])}`",
        "",
        "## Inventory",
        "",
        *markdown_table(
            frame,
            ["market_root", "venue", "dataset", "data_type", "symbol", "date_count", "first_date", "last_date", "file_count"],
            80,
        ),
        "",
        "## Output Tables",
        "",
        f"- `{paths.inventory_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_external_venue_inventory.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, frame: pd.DataFrame, summary: dict[str, Any]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(paths.inventory_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        **summary,
        "outputs": {
            "inventory_csv": str(paths.inventory_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, frame, summary)


def main() -> None:
    args = parse_args()
    paths = Paths(
        data_root=resolve_repo_path(args.data_root),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    frame = build_inventory(paths.data_root)
    summary = summarize(frame)
    write_outputs(paths, frame, summary)
    print(
        "[ccusdt_external_venue_inventory] "
        f"rows={len(frame)} decision={summary['decision']} wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
