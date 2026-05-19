#!/usr/bin/env python
"""Inventory local Bullish L2 universe coverage for the CCUSDT V2 pivot.

This is a research-only availability probe. It does not download data or read
private credentials. Its purpose is to make the liquidity-envelope universe
pivot explicit: before alpha mining can move beyond CCUSDT, the workspace needs
local multi-symbol Bullish book/trade/L2 coverage.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_local_universe_inventory_no_download_no_execution_recommendation"
RUN_TAG = "20260518_ccusdt_v2_local_universe_inventory_v1"
DATA_TYPES = ["book_ticker", "trades", "incremental_book_L2", "book_snapshot_25"]
CORE_TYPES = ["book_ticker", "trades", "incremental_book_L2"]


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def inventory_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_local_bullish_universe_inventory_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_local_bullish_universe_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-local-universe-inventory-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory local Bullish L2 universe coverage.")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--min-core-dates", type=int, default=10)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def date_dirs(symbol_root: Path) -> set[str]:
    if not symbol_root.exists():
        return set()
    return {item.name.replace("dt=", "") for item in symbol_root.glob("dt=*") if item.is_dir()}


def market_dirs(data_root: Path) -> list[Path]:
    if not data_root.exists():
        return []
    out: list[Path] = []
    for item in sorted(data_root.iterdir()):
        if item.is_dir() and (item / "v1" / "external").exists():
            out.append(item)
    return out


def inventory(paths: Paths, min_core_dates: int) -> pd.DataFrame:
    by_key: dict[tuple[str, str], dict[str, object]] = {}
    for market_dir in market_dirs(paths.data_root):
        market = market_dir.name
        external = market_dir / "v1" / "external"
        for data_type in DATA_TYPES:
            root = external / f"bullish_{data_type}"
            if not root.exists():
                continue
            for symbol_dir in sorted(root.glob("symbol=*")):
                if not symbol_dir.is_dir():
                    continue
                symbol = symbol_dir.name.replace("symbol=", "")
                key = (market, symbol)
                row = by_key.setdefault(
                    key,
                    {
                        "run_tag": paths.run_tag,
                        "guardrail": GUARDRAIL,
                        "market": market,
                        "symbol": symbol,
                    },
                )
                dates = sorted(date_dirs(symbol_dir))
                row[f"{data_type}_dates"] = len(dates)
                row[f"{data_type}_first_date"] = dates[0] if dates else ""
                row[f"{data_type}_last_date"] = dates[-1] if dates else ""
                row[f"_{data_type}_date_set"] = set(dates)

    rows: list[dict[str, object]] = []
    for row in by_key.values():
        core_sets = [row.get(f"_{data_type}_date_set", set()) for data_type in CORE_TYPES]
        full_sets = [row.get(f"_{data_type}_date_set", set()) for data_type in DATA_TYPES]
        common_core = sorted(set.intersection(*core_sets)) if all(core_sets) else []
        common_full = sorted(set.intersection(*full_sets)) if all(full_sets) else []
        clean = {key: value for key, value in row.items() if not key.startswith("_")}
        for data_type in DATA_TYPES:
            clean.setdefault(f"{data_type}_dates", 0)
            clean.setdefault(f"{data_type}_first_date", "")
            clean.setdefault(f"{data_type}_last_date", "")
        clean["common_core_dates"] = len(common_core)
        clean["common_core_first_date"] = common_core[0] if common_core else ""
        clean["common_core_last_date"] = common_core[-1] if common_core else ""
        clean["common_full_dates"] = len(common_full)
        clean["common_full_first_date"] = common_full[0] if common_full else ""
        clean["common_full_last_date"] = common_full[-1] if common_full else ""
        clean["core_l2_ready"] = bool(len(common_core) >= min_core_dates)
        clean["full_l2_ready"] = bool(len(common_full) >= min_core_dates)
        rows.append(clean)

    columns = [
        "run_tag",
        "guardrail",
        "market",
        "symbol",
        "book_ticker_dates",
        "trades_dates",
        "incremental_book_L2_dates",
        "book_snapshot_25_dates",
        "common_core_dates",
        "common_core_first_date",
        "common_core_last_date",
        "common_full_dates",
        "common_full_first_date",
        "common_full_last_date",
        "core_l2_ready",
        "full_l2_ready",
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return frame.loc[:, columns].sort_values(["core_l2_ready", "common_core_dates", "market", "symbol"], ascending=[False, False, True, True])


def build_summary(frame: pd.DataFrame, paths: Paths, min_core_dates: int) -> dict[str, object]:
    core_ready = frame[frame["core_l2_ready"].astype(bool)] if not frame.empty else frame
    full_ready = frame[frame["full_l2_ready"].astype(bool)] if not frame.empty else frame
    return {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "data_root": str(paths.data_root),
        "min_core_dates": min_core_dates,
        "symbols_total": int(len(frame)),
        "core_l2_ready_symbols": int(len(core_ready)),
        "full_l2_ready_symbols": int(len(full_ready)),
        "core_l2_ready_symbol_list": core_ready["symbol"].astype(str).tolist() if not core_ready.empty else [],
        "multi_symbol_core_ready": bool(len(core_ready) >= 2),
        "local_universe_status": "multi_symbol_ready" if len(core_ready) >= 2 else "single_or_no_symbol_only",
        "outputs": {
            "inventory_csv": str(paths.inventory_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }


def write_report(paths: Paths, frame: pd.DataFrame, summary: dict[str, object]) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Local Bullish Universe Inventory")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "Objective branch: determine whether the local workspace has a multi-symbol Bullish L2 universe for the "
        "liquidity-envelope pivot. This pass only inventories paths; it does not download or inspect private data."
    )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"Local universe status: `{summary['local_universe_status']}`.")
    lines.append("")
    if summary["multi_symbol_core_ready"]:
        lines.append(
            "A local multi-symbol core L2 universe exists. The next step is to run the liquidity-envelope audit per symbol "
            "before any symbol-level alpha mining."
        )
    else:
        lines.append(
            "The local workspace does not contain a multi-symbol Bullish core L2 universe. Current execution-envelope "
            "screening can only evaluate the available symbol set, so stable `>2` bps capture cannot be proven through "
            "universe selection from this local inventory alone."
        )
    lines.append("")
    lines.append("## Inventory")
    lines.append("")
    lines.extend(
        markdown_table(
            frame,
            [
                "market",
                "symbol",
                "book_ticker_dates",
                "trades_dates",
                "incremental_book_L2_dates",
                "book_snapshot_25_dates",
                "common_core_dates",
                "common_core_first_date",
                "common_core_last_date",
                "core_l2_ready",
                "full_l2_ready",
            ],
            40,
        )
    )
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.inventory_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(f"python scripts/ccusdt_v2_local_universe_inventory.py --run-tag {paths.run_tag}")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, frame: pd.DataFrame, summary: dict[str, object]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(paths.inventory_csv, index=False)
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
    frame = inventory(paths, args.min_core_dates)
    summary = build_summary(frame, paths, args.min_core_dates)
    write_outputs(paths, frame, summary)
    print(
        "[ccusdt_local_universe_inventory] "
        f"symbols={summary['symbols_total']} core_ready={summary['core_l2_ready_symbols']} "
        f"status={summary['local_universe_status']}",
        flush=True,
    )
    print(f"[ccusdt_local_universe_inventory] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
