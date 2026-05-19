#!/usr/bin/env python
"""Build a no-download acquisition gate for external CC L2 venues."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_external_acquisition_plan_no_download_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_external_acquisition_plan_v1"
DEFAULT_METADATA_RUN_TAG = "20260518_ccusdt_v2_tardis_external_metadata_probe_v1"
DATASETS_BASE = "https://datasets.tardis.dev/v1"


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    data_root: Path
    run_tag: str

    @property
    def manifest_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_external_acquisition_manifest_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_external_acquisition_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-external-acquisition-plan-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an external CC L2 acquisition manifest from Tardis metadata.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt_external/v1"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--metadata-run-tag", default=DEFAULT_METADATA_RUN_TAG)
    parser.add_argument("--from-date", default="2026-04-29")
    parser.add_argument("--to-date", default="2026-05-15")
    parser.add_argument("--data-types", default="book_ticker,trades,incremental_book_L2")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def date_range(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    if start > end:
        raise SystemExit(f"--from-date {start} is after --to-date {end}")
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def dataset_url(exchange: str, data_type: str, day: dt.date, symbol: str) -> str:
    return f"{DATASETS_BASE}/{exchange}/{data_type}/{day.year:04d}/{day.month:02d}/{day.day:02d}/{symbol}.csv.gz"


def raw_path(data_root: Path, exchange: str, data_type: str, day: dt.date, symbol: str) -> Path:
    return (
        data_root
        / "external"
        / f"{exchange}_{data_type}"
        / f"symbol={symbol}"
        / f"dt={day.isoformat()}"
        / f"{symbol}.csv.gz"
    )


def metadata_paths(date_dir: Path, run_tag: str) -> tuple[Path, Path]:
    csv_path = date_dir / f"ccusdt_v2_tardis_external_metadata_probe_{run_tag}.csv"
    json_path = date_dir / f"ccusdt_v2_tardis_external_metadata_probe_{run_tag}.json"
    return csv_path, json_path


def read_metadata(date_dir: Path, run_tag: str) -> tuple[pd.DataFrame, dict[str, object]]:
    csv_path, json_path = metadata_paths(date_dir, run_tag)
    if not csv_path.exists():
        raise SystemExit(f"metadata probe CSV not found: {csv_path}")
    if not json_path.exists():
        raise SystemExit(f"metadata probe JSON not found: {json_path}")
    return pd.read_csv(csv_path), json.loads(json_path.read_text(encoding="utf-8"))


def build_manifest(
    metadata: pd.DataFrame,
    data_root: Path,
    dates: list[dt.date],
    data_types: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if metadata.empty:
        return pd.DataFrame(rows)
    candidate = metadata[
        metadata.get("external_exchange", pd.Series(dtype=bool)).astype(bool)
        & metadata.get("cc_symbol_present", pd.Series(dtype=bool)).astype(bool)
        & metadata.get("has_l2_channel", pd.Series(dtype=bool)).astype(bool)
    ].copy()
    for _, row in candidate.iterrows():
        exchange = str(row.get("exchange", "")).strip()
        symbols = parse_list(str(row.get("matched_symbols", "")))
        access = bool(row.get("requested_exchange_access", False))
        status = "planned" if access else "blocked_access"
        for symbol in symbols:
            for data_type in data_types:
                for day in dates:
                    path = raw_path(data_root, exchange, data_type, day, symbol)
                    rows.append(
                        {
                            "exchange": exchange,
                            "data_type": data_type,
                            "symbol": symbol,
                            "date": day.isoformat(),
                            "url": dataset_url(exchange, data_type, day, symbol),
                            "path": str(path),
                            "status": status,
                            "requested_exchange_access": access,
                            "metadata_http_status": row.get("metadata_http_status", ""),
                            "available_channels": row.get("available_channels", ""),
                        }
                    )
    if not rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(rows).sort_values(["status", "exchange", "symbol", "data_type", "date"]).reset_index(drop=True)


def summarize(paths: Paths, manifest: pd.DataFrame, metadata_summary: dict[str, object], metadata_run_tag: str) -> dict[str, object]:
    planned = int(manifest["status"].astype(str).eq("planned").sum()) if not manifest.empty else 0
    blocked = int(manifest["status"].astype(str).eq("blocked_access").sum()) if not manifest.empty else 0
    exchanges = sorted(manifest["exchange"].dropna().astype(str).unique().tolist()) if not manifest.empty else []
    symbols = sorted(manifest["symbol"].dropna().astype(str).unique().tolist()) if not manifest.empty else []
    planned_exchanges = (
        sorted(manifest.loc[manifest["status"].astype(str).eq("planned"), "exchange"].dropna().astype(str).unique().tolist())
        if not manifest.empty
        else []
    )
    decision = "external_acquisition_ready_for_size_probe" if planned > 0 else "external_acquisition_blocked_by_access"
    return {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "metadata_run_tag": metadata_run_tag,
        "metadata_decision": metadata_summary.get("decision", "missing"),
        "cc_external_l2_metadata_exchanges": metadata_summary.get("cc_external_l2_metadata_exchanges", []),
        "cc_accessible_external_l2_metadata_exchanges": metadata_summary.get(
            "cc_accessible_external_l2_metadata_exchanges", []
        ),
        "manifest_rows": int(len(manifest)),
        "planned_rows": planned,
        "blocked_access_rows": blocked,
        "candidate_exchanges": exchanges,
        "candidate_symbols": symbols,
        "planned_exchanges": planned_exchanges,
        "decision": decision,
        "outputs": {
            "manifest_csv": str(paths.manifest_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 50) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def write_report(paths: Paths, manifest: pd.DataFrame, summary: dict[str, object]) -> None:
    status = (
        manifest.groupby(["exchange", "symbol", "status"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["status", "exchange", "symbol"])
        if not manifest.empty
        else pd.DataFrame(columns=["exchange", "symbol", "status", "rows"])
    )
    lines: list[str] = [
        "# CCUSDT V2 External Acquisition Plan",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Decision",
        "",
        f"Decision: `{summary['decision']}`.",
        "",
        "This is a no-download acquisition gate. It converts the Tardis external metadata probe into a dataset manifest, but rows stay `blocked_access` until the API key has requested access for an external CC L2 venue.",
        "",
        "## Summary",
        "",
        f"- metadata_decision: `{summary['metadata_decision']}`",
        f"- cc_external_l2_metadata_exchanges: `{','.join(summary['cc_external_l2_metadata_exchanges'])}`",
        f"- cc_accessible_external_l2_metadata_exchanges: `{','.join(summary['cc_accessible_external_l2_metadata_exchanges'])}`",
        f"- manifest_rows: `{summary['manifest_rows']}`",
        f"- planned_rows: `{summary['planned_rows']}`",
        f"- blocked_access_rows: `{summary['blocked_access_rows']}`",
        f"- candidate_exchanges: `{','.join(summary['candidate_exchanges'])}`",
        f"- candidate_symbols: `{','.join(summary['candidate_symbols'])}`",
        "",
        "## Manifest Status",
        "",
        *markdown_table(status, ["exchange", "symbol", "status", "rows"], 80),
        "",
        "## Next Gate",
        "",
        "When `planned_rows > 0`, run the metadata/Range size probe against this manifest before any dataset body download:",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_universe_size_probe.py --manifest-csv {paths.manifest_csv} --run-tag {paths.run_tag}_size_probe --workers 8 --timeout-seconds 30",
        "```",
        "",
        "## Output Tables",
        "",
        f"- `{paths.manifest_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v2_external_acquisition_plan.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, manifest: pd.DataFrame, summary: dict[str, object]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(paths.manifest_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, manifest, summary)


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        data_root=resolve_repo_path(args.data_root),
        run_tag=args.run_tag,
    )
    metadata, metadata_summary = read_metadata(paths.date_dir, args.metadata_run_tag)
    dates = list(date_range(dt.date.fromisoformat(args.from_date), dt.date.fromisoformat(args.to_date)))
    data_types = parse_list(args.data_types)
    manifest = build_manifest(metadata, paths.data_root, dates, data_types)
    summary = summarize(paths, manifest, metadata_summary, args.metadata_run_tag)
    write_outputs(paths, manifest, summary)
    print(
        "[ccusdt_external_acquisition_plan] "
        f"rows={len(manifest)} planned={summary['planned_rows']} "
        f"blocked_access={summary['blocked_access_rows']} decision={summary['decision']} "
        f"wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
