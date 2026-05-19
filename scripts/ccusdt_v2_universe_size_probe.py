#!/usr/bin/env python
"""Estimate Bullish universe download size from a dry-run manifest.

This script reads the dry-run manifest produced by `bonk_bullish_l2_download.py`
and performs authenticated HTTP HEAD requests for planned files only, falling
back to one-byte Range GET probes where HEAD is not supported. It does not
download dataset bodies and does not print the Tardis API key.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_universe_size_probe_metadata_or_range_no_body_download_no_execution_recommendation"
RUN_TAG = "20260518_ccusdt_v2_universe_size_probe_v1"
DEFAULT_MANIFEST = Path("date/bonk_bullish_l2_download_manifest_20260518_ccusdt_v2_universe_preflight_v1.csv")
DEFAULT_ENV_FILE = Path(".env.chog.local")


@dataclass(frozen=True)
class Paths:
    manifest_csv: Path
    env_file: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def files_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_universe_size_probe_files_{self.run_tag}.csv"

    @property
    def summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_universe_size_probe_summary_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_universe_size_probe_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-universe-size-probe-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Metadata/Range size probe for Bullish universe dry-run manifest.")
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-jobs", type=int, default=0, help="Optional cap for smoke probes; 0 means all planned jobs.")
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol filter.")
    parser.add_argument("--data-types", default="", help="Optional comma-separated data type filter.")
    parser.add_argument("--from-date", default="", help="Optional inclusive YYYY-MM-DD start filter.")
    parser.add_argument("--to-date", default="", help="Optional inclusive YYYY-MM-DD end filter.")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def load_tardis_key(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r'(?im)^\s*TARDIS_API_KEY\s*=\s*["\']?([^\r\n"\']+)', text)
    if not match:
        raise SystemExit(f"TARDIS_API_KEY not found in {path}")
    key = match.group(1).strip()
    if len(key) < 20:
        raise SystemExit("TARDIS_API_KEY exists but is too short")
    return key


def parse_list(raw: str) -> set[str]:
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def read_manifest(
    path: Path,
    max_jobs: int,
    symbols: set[str],
    data_types: set[str],
    from_date: str,
    to_date: str,
) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"manifest not found: {path}")
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("status") != "planned":
                continue
            if symbols and row.get("symbol", "").upper() not in symbols:
                continue
            if data_types and row.get("data_type", "") not in data_types:
                continue
            if from_date and row.get("date", "") < from_date:
                continue
            if to_date and row.get("date", "") > to_date:
                continue
            rows.append(dict(row))
            if max_jobs > 0 and len(rows) >= max_jobs:
                break
    if not rows:
        raise SystemExit(f"no planned rows found in {path}")
    return rows


def head_once(row: dict[str, str], key: str, timeout_seconds: float) -> dict[str, object]:
    request = urllib.request.Request(
        row["url"],
        method="HEAD",
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "finance-chain-ccusdt-v2-universe-size-probe/0.1",
            "Accept": "*/*",
        },
    )
    out: dict[str, object] = {
        "exchange": row.get("exchange", ""),
        "data_type": row.get("data_type", ""),
        "symbol": row.get("symbol", ""),
        "date": row.get("date", ""),
        "url": row.get("url", ""),
        "path": row.get("path", ""),
        "probe_status": "error",
        "probe_method": "HEAD",
        "http_status": None,
        "content_length": 0,
        "accept_ranges": "",
        "etag": "",
        "last_modified": "",
        "error": "",
    }
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            out["probe_status"] = "available"
            out["http_status"] = int(response.status)
            raw_length = response.headers.get("Content-Length") or "0"
            try:
                out["content_length"] = int(raw_length)
            except ValueError:
                out["content_length"] = 0
            out["accept_ranges"] = response.headers.get("Accept-Ranges") or ""
            out["etag"] = response.headers.get("ETag") or ""
            out["last_modified"] = response.headers.get("Last-Modified") or ""
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 404, 405}:
            return range_once(row, key, timeout_seconds, f"HEAD {exc.code}: {exc.reason or ''}".strip())
        out["probe_status"] = "error"
        out["http_status"] = int(exc.code)
        out["error"] = f"HEAD {exc.code}: {exc.reason or ''}".strip()
    except Exception as exc:  # noqa: BLE001
        return range_once(row, key, timeout_seconds, f"HEAD {type(exc).__name__}: {exc}")
    return out


def parse_content_range(value: str) -> int:
    match = re.search(r"/(\d+)\s*$", value or "")
    return int(match.group(1)) if match else 0


def range_once(row: dict[str, str], key: str, timeout_seconds: float, head_error: str) -> dict[str, object]:
    request = urllib.request.Request(
        row["url"],
        method="GET",
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "finance-chain-ccusdt-v2-universe-size-probe/0.1",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Range": "bytes=0-0",
        },
    )
    out: dict[str, object] = {
        "exchange": row.get("exchange", ""),
        "data_type": row.get("data_type", ""),
        "symbol": row.get("symbol", ""),
        "date": row.get("date", ""),
        "url": row.get("url", ""),
        "path": row.get("path", ""),
        "probe_status": "error",
        "probe_method": "RANGE_GET",
        "http_status": None,
        "content_length": 0,
        "accept_ranges": "",
        "etag": "",
        "last_modified": "",
        "error": head_error,
    }
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read(1)
            out["probe_status"] = "available"
            out["http_status"] = int(response.status)
            content_range = response.headers.get("Content-Range") or ""
            raw_length = parse_content_range(content_range)
            if raw_length <= 0:
                try:
                    raw_length = int(response.headers.get("Content-Length") or "0")
                except ValueError:
                    raw_length = 0
            out["content_length"] = raw_length
            out["accept_ranges"] = response.headers.get("Accept-Ranges") or ""
            out["etag"] = response.headers.get("ETag") or ""
            out["last_modified"] = response.headers.get("Last-Modified") or ""
            out["error"] = head_error
    except urllib.error.HTTPError as exc:
        out["probe_status"] = "missing" if exc.code == 404 or head_error.startswith("HEAD 404") else "error"
        out["http_status"] = int(exc.code)
        out["error"] = f"{head_error}; RANGE {exc.code}: {exc.reason or ''}".strip("; ")
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{head_error}; RANGE {type(exc).__name__}: {exc}".strip("; ")
    return out


def run_probe(rows: list[dict[str, str]], key: str, timeout_seconds: float, workers: int) -> pd.DataFrame:
    workers = max(1, workers)
    if workers == 1:
        return pd.DataFrame([head_once(row, key, timeout_seconds) for row in rows])
    out: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(head_once, row, key, timeout_seconds) for row in rows]
        for future in as_completed(futures):
            out.append(future.result())
    return pd.DataFrame(out).sort_values(["symbol", "data_type", "date"]).reset_index(drop=True)


def summarize(files: pd.DataFrame, paths: Paths) -> tuple[pd.DataFrame, dict[str, object]]:
    frame = files.copy()
    frame["content_length"] = pd.to_numeric(frame["content_length"], errors="coerce").fillna(0).astype("int64")
    grouped = (
        frame.groupby(["symbol", "data_type"], dropna=False)
        .agg(
            files=("url", "count"),
            available_files=("probe_status", lambda values: int((values.astype(str) == "available").sum())),
            missing_files=("probe_status", lambda values: int((values.astype(str) == "missing").sum())),
            error_files=("probe_status", lambda values: int((values.astype(str) == "error").sum())),
            bytes=("content_length", "sum"),
        )
        .reset_index()
    )
    grouped["gb"] = grouped["bytes"] / 1_000_000_000.0
    symbol_totals = (
        grouped.groupby("symbol", dropna=False)
        .agg(files=("files", "sum"), available_files=("available_files", "sum"), bytes=("bytes", "sum"), gb=("gb", "sum"))
        .reset_index()
    )
    symbol_totals.insert(1, "data_type", "ALL")
    summary = pd.concat([grouped, symbol_totals], ignore_index=True).sort_values(["data_type", "gb"], ascending=[True, False])
    available = int((frame["probe_status"].astype(str) == "available").sum())
    missing = int((frame["probe_status"].astype(str) == "missing").sum())
    errors = int((frame["probe_status"].astype(str) == "error").sum())
    meta = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "manifest_csv": str(paths.manifest_csv),
        "planned_rows_probed": int(len(frame)),
        "available_rows": available,
        "missing_rows": missing,
        "error_rows": errors,
        "total_bytes": int(frame["content_length"].sum()),
        "total_gb": float(frame["content_length"].sum() / 1_000_000_000.0),
        "outputs": {
            "files_csv": str(paths.files_csv),
            "summary_csv": str(paths.summary_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    return summary, meta


def write_report(paths: Paths, files: pd.DataFrame, summary: pd.DataFrame, meta: dict[str, object]) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Bullish Universe Size Probe")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append(
        "This is a metadata/one-byte Range size probe over the dry-run universe manifest. It estimates download size "
        "without downloading dataset bodies; Range GET is used only when HEAD is not usable."
    )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(
        f"Probed `{meta['planned_rows_probed']}` planned files: `{meta['available_rows']}` available, "
        f"`{meta['missing_rows']}` missing, `{meta['error_rows']}` errors. Estimated total size is "
        f"`{float(meta['total_gb']):.2f}` GB."
    )
    lines.append("")
    lines.append("This makes the universe pivot data step explicit, but it is still not evidence of an executable edge.")
    lines.append("")
    lines.append("## Size Summary")
    lines.append("")
    lines.extend(
        markdown_table(
            summary,
            ["symbol", "data_type", "files", "available_files", "missing_files", "error_files", "gb"],
            60,
        )
    )
    lines.append("")
    lines.append("## Probe Status")
    lines.append("")
    status = (
        files.groupby(["probe_status", "http_status"], dropna=False)
        .size()
        .reset_index(name="rows")
        .sort_values(["probe_status", "http_status"])
    )
    lines.extend(markdown_table(status, ["probe_status", "http_status", "rows"], 20))
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.files_csv, paths.summary_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    extra = ""
    if int(meta.get("max_jobs", 0) or 0) > 0:
        extra += f" --max-jobs {int(meta['max_jobs'])}"
    if meta.get("symbols_filter"):
        extra += f" --symbols \"{meta['symbols_filter']}\""
    if meta.get("data_types_filter"):
        extra += f" --data-types \"{meta['data_types_filter']}\""
    if meta.get("from_date"):
        extra += f" --from-date {meta['from_date']}"
    if meta.get("to_date"):
        extra += f" --to-date {meta['to_date']}"
    extra += f" --workers {int(meta.get('workers', 8) or 8)}"
    extra += f" --timeout-seconds {float(meta.get('timeout_seconds', 30.0) or 30.0):.0f}"
    lines.append(f"python scripts/ccusdt_v2_universe_size_probe.py --run-tag {paths.run_tag}{extra}")
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, files: pd.DataFrame, summary: pd.DataFrame, meta: dict[str, object]) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    files.to_csv(paths.files_csv, index=False)
    summary.to_csv(paths.summary_csv, index=False)
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, files, summary, meta)


def main() -> None:
    args = parse_args()
    paths = Paths(
        manifest_csv=resolve_repo_path(args.manifest_csv),
        env_file=resolve_repo_path(args.env_file),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    rows = read_manifest(
        paths.manifest_csv,
        args.max_jobs,
        parse_list(args.symbols),
        {item.strip() for item in args.data_types.split(",") if item.strip()},
        args.from_date,
        args.to_date,
    )
    key = load_tardis_key(paths.env_file)
    files = run_probe(rows, key, args.timeout_seconds, args.workers)
    summary, meta = summarize(files, paths)
    meta["max_jobs"] = int(args.max_jobs)
    meta["symbols_filter"] = args.symbols
    meta["data_types_filter"] = args.data_types
    meta["from_date"] = args.from_date
    meta["to_date"] = args.to_date
    meta["workers"] = int(args.workers)
    meta["timeout_seconds"] = float(args.timeout_seconds)
    write_outputs(paths, files, summary, meta)
    print(
        "[ccusdt_universe_size_probe] "
        f"probed={meta['planned_rows_probed']} available={meta['available_rows']} "
        f"errors={meta['error_rows']} total_gb={float(meta['total_gb']):.2f}",
        flush=True,
    )
    print(f"[ccusdt_universe_size_probe] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
