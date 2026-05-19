#!/usr/bin/env python3
"""
Download Bullish BONK L2 CSV files from Tardis downloadable datasets.

The downloader intentionally stores the compressed CSV files unchanged. It
validates gzip integrity before reusing an existing file, and writes a completion
manifest so missing/forbidden/truncated files are auditable without printing the
Tardis API key.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DATA_ROOT = Path("data/bonk/v1")
DEFAULT_DATE_DIR = Path("date")
DEFAULT_ENV_FILE = Path(".env.chog.local")
DEFAULT_FROM_DATE = "2026-04-29"
DEFAULT_TO_DATE = "2026-05-12"
DEFAULT_SYMBOLS = (
    "BONK1MUSDC,BONK1MUSDT,"
    "BTCUSDC,ETHUSDC,SOLUSDC,"
    "DOGEUSDC,PENGUUSDC,"
    "PEPE1MUSDC,SHIB1MUSDC,WIFUSDC,"
    "SUIUSDC,APTUSDC,ARBUSDC,OPUSDC"
)
DEFAULT_DATA_TYPES = "book_snapshot_25,book_ticker,trades"
DEFAULT_RUN_TAG = "20260513_bullish_l2_v1"
DATASETS_BASE = "https://datasets.tardis.dev/v1"
EXCHANGE = "bullish"
USER_AGENT = "finance-chain-bonk-bullish-l2-downloader/0.1"


@dataclass
class FileResult:
    exchange: str
    data_type: str
    symbol: str
    date: str
    url: str
    path: str
    status: str
    http_status: int | None = None
    bytes: int = 0
    gzip_ok: bool = False
    header: list[str] | None = None
    sample_rows: int = 0
    error: str = ""


@dataclass(frozen=True)
class DownloadJob:
    day: dt.date
    data_type: str
    symbol: str
    url: str
    path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Bullish downloadable CSV.gz L2 files from Tardis."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--date-dir", type=Path, default=DEFAULT_DATE_DIR)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--from-date", default=DEFAULT_FROM_DATE)
    parser.add_argument("--to-date", default=DEFAULT_TO_DATE)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument(
        "--extra-symbols",
        default="",
        help="Optional comma-separated additional Bullish symbols to fetch if disk space allows.",
    )
    parser.add_argument("--data-types", default=DEFAULT_DATA_TYPES)
    parser.add_argument("--run-tag", default=DEFAULT_RUN_TAG)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel file download/validation workers.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip Bullish metadata symbol availability preflight.",
    )
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=5.0,
        help="Abort before downloading if the data root drive has less free space.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_list(raw: str) -> list[str]:
    values = [value.strip().upper() for value in raw.split(",") if value.strip()]
    return list(dict.fromkeys(values))


def parse_data_types(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    return list(dict.fromkeys(values))


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def date_range(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    if start > end:
        raise SystemExit(f"--from-date {start} is after --to-date {end}")
    current = start
    one_day = dt.timedelta(days=1)
    while current <= end:
        yield current
        current += one_day


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


def request_json(url: str, api_key: str, timeout_seconds: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text) if text else None


def bullish_symbol_metadata(api_key: str, timeout_seconds: float) -> dict[str, dict[str, Any]]:
    body = request_json(
        f"https://api.tardis.dev/v1/exchanges/{EXCHANGE}",
        api_key,
        timeout_seconds,
    )
    symbols = body.get("availableSymbols") or body.get("symbols") or [] if isinstance(body, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for item in symbols:
        if isinstance(item, str):
            symbol_id = item.upper()
            out[symbol_id] = {"id": symbol_id}
        elif isinstance(item, dict):
            symbol_id = str(item.get("id") or item.get("symbol") or "").upper()
            if symbol_id:
                out[symbol_id] = dict(item)
    return out


def preflight_symbols(
    symbols: list[str],
    api_key: str,
    timeout_seconds: float,
    skip_preflight: bool,
) -> tuple[list[str], list[dict[str, Any]]]:
    if skip_preflight:
        return symbols, [
            {
                "symbol": symbol,
                "status": "not_checked",
                "exchange": EXCHANGE,
                "type": "",
                "availableSince": "",
            }
            for symbol in symbols
        ]
    metadata = bullish_symbol_metadata(api_key, timeout_seconds)
    rows: list[dict[str, Any]] = []
    available: list[str] = []
    for symbol in symbols:
        item = metadata.get(symbol.upper())
        if item is None:
            rows.append(
                {
                    "symbol": symbol,
                    "status": "missing",
                    "exchange": EXCHANGE,
                    "type": "",
                    "availableSince": "",
                }
            )
        else:
            available.append(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "status": "available",
                    "exchange": EXCHANGE,
                    "type": item.get("type", ""),
                    "availableSince": item.get("availableSince", ""),
                }
            )
    return available, rows


def dataset_url(data_type: str, day: dt.date, symbol: str) -> str:
    return (
        f"{DATASETS_BASE}/{EXCHANGE}/{data_type}/"
        f"{day.year:04d}/{day.month:02d}/{day.day:02d}/{symbol}.csv.gz"
    )


def raw_path(data_root: Path, data_type: str, day: dt.date, symbol: str) -> Path:
    return (
        data_root
        / "external"
        / f"{EXCHANGE}_{data_type}"
        / f"symbol={symbol}"
        / f"dt={day.isoformat()}"
        / f"{symbol}.csv.gz"
    )


def validate_gzip_csv(path: Path) -> tuple[bool, list[str], int, str]:
    try:
        sample_rows = 0
        with gzip.open(path, "rb") as handle:
            header_line = handle.readline()
            if not header_line:
                return False, [], 0, "empty gzip payload"
            header = next(csv.reader([header_line.decode("utf-8-sig", errors="replace")]))
            for _ in range(3):
                line = handle.readline()
                if not line:
                    break
                if line.strip():
                    sample_rows += 1
            while handle.read(1024 * 1024):
                pass
        return True, header, sample_rows, ""
    except Exception as exc:  # noqa: BLE001
        return False, [], 0, f"{type(exc).__name__}: {exc}"


def disk_free_gb(path: Path) -> float:
    probe = path.resolve()
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return usage.free / (1024.0**3)


def sleep_for_attempt(attempt: int) -> None:
    delays = [2.0, 5.0, 15.0, 45.0]
    time.sleep(delays[min(attempt, len(delays) - 1)])


def download_once(url: str, path: Path, api_key: str, timeout_seconds: float) -> tuple[int, int]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
            "Accept": "text/csv,application/gzip,*/*",
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    part_path = Path(f"{path}.part")
    if part_path.exists():
        part_path.unlink()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status = int(response.status)
        expected = response.headers.get("Content-Length")
        with part_path.open("wb") as out:
            bytes_written = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                bytes_written += len(chunk)
        if expected is not None and bytes_written != int(expected):
            part_path.unlink(missing_ok=True)
            raise IOError(f"truncated download: got {bytes_written}, expected {expected}")
        if bytes_written == 0:
            part_path.unlink(missing_ok=True)
            raise IOError("empty download")
        if path.exists():
            path.unlink()
        part_path.replace(path)
        return status, bytes_written


def download_file(
    url: str,
    path: Path,
    api_key: str,
    timeout_seconds: float,
    max_retries: int,
) -> tuple[str, int | None, int, bool, list[str], int, str]:
    last_error = ""
    for attempt in range(max(1, max_retries)):
        try:
            http_status, bytes_written = download_once(url, path, api_key, timeout_seconds)
            gzip_ok, header, sample_rows, gzip_error = validate_gzip_csv(path)
            if not gzip_ok:
                if "empty gzip payload" in gzip_error:
                    return "empty", http_status, bytes_written, False, header, sample_rows, gzip_error
                path.unlink(missing_ok=True)
                return "error", http_status, bytes_written, False, header, sample_rows, gzip_error
            if sample_rows == 0:
                return "empty", http_status, bytes_written, True, header, sample_rows, ""
            return "downloaded", http_status, bytes_written, True, header, sample_rows, ""
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(240).decode("utf-8", errors="replace")
            if status == 400 and '"code": 140' in body:
                return "unavailable", status, 0, False, None, 0, body
            if status == 404:
                return "missing", status, 0, False, None, 0, body
            if status in {401, 403}:
                return "error", status, 0, False, None, 0, body
            last_error = f"HTTP {status}: {body}"
            if 400 <= status < 500:
                return "error", status, 0, False, None, 0, last_error
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt + 1 < max_retries:
            sleep_for_attempt(attempt)
    return "error", None, 0, False, None, 0, last_error


def build_jobs(
    data_root: Path,
    dates: list[dt.date],
    data_types: list[str],
    symbols: list[str],
) -> list[DownloadJob]:
    jobs: list[DownloadJob] = []
    for day in dates:
        for data_type in data_types:
            for symbol in symbols:
                jobs.append(
                    DownloadJob(
                        day=day,
                        data_type=data_type,
                        symbol=symbol,
                        url=dataset_url(data_type, day, symbol),
                        path=raw_path(data_root, data_type, day, symbol),
                    )
                )
    return jobs


def missing_symbol_results(
    data_root: Path,
    dates: list[dt.date],
    data_types: list[str],
    missing_symbols: list[str],
) -> list[FileResult]:
    results: list[FileResult] = []
    for job in build_jobs(data_root, dates, data_types, missing_symbols):
        results.append(
            FileResult(
                exchange=EXCHANGE,
                data_type=job.data_type,
                symbol=job.symbol,
                date=job.day.isoformat(),
                url=job.url,
                path=job.path.as_posix(),
                status="missing",
                error="symbol not present in Bullish metadata preflight",
            )
        )
    return results


def process_job(job: DownloadJob, args: argparse.Namespace, api_key: str) -> FileResult:
    if args.dry_run:
        return FileResult(
            exchange=EXCHANGE,
            data_type=job.data_type,
            symbol=job.symbol,
            date=job.day.isoformat(),
            url=job.url,
            path=job.path.as_posix(),
            status="planned",
        )
    if job.path.exists() and job.path.stat().st_size > 0 and not args.force:
        gzip_ok, header, sample_rows, error = validate_gzip_csv(job.path)
        result = FileResult(
            exchange=EXCHANGE,
            data_type=job.data_type,
            symbol=job.symbol,
            date=job.day.isoformat(),
            url=job.url,
            path=job.path.as_posix(),
            status="skipped" if gzip_ok and sample_rows > 0 else "empty" if gzip_ok else "error",
            bytes=job.path.stat().st_size,
            gzip_ok=gzip_ok,
            header=header,
            sample_rows=sample_rows,
            error=error,
        )
        if gzip_ok:
            return result
    status, http_status, bytes_written, gzip_ok, header, sample_rows, error = download_file(
        job.url,
        job.path,
        api_key,
        args.timeout_seconds,
        args.max_retries,
    )
    return FileResult(
        exchange=EXCHANGE,
        data_type=job.data_type,
        symbol=job.symbol,
        date=job.day.isoformat(),
        url=job.url,
        path=job.path.as_posix(),
        status=status,
        http_status=http_status,
        bytes=bytes_written,
        gzip_ok=gzip_ok,
        header=header,
        sample_rows=sample_rows,
        error=error,
    )


def run_jobs(jobs: list[DownloadJob], args: argparse.Namespace, api_key: str) -> list[FileResult]:
    workers = max(1, int(args.workers))
    if workers == 1 or len(jobs) <= 1:
        results = []
        for job in jobs:
            result = process_job(job, args, api_key)
            print(f"{result.date} {result.data_type} {result.symbol}: {result.status} bytes={result.bytes}")
            results.append(result)
        return results
    results: list[FileResult] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_job, job, args, api_key): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            print(f"{result.date} {result.data_type} {result.symbol}: {result.status} bytes={result.bytes}")
            results.append(result)
    return results


def write_outputs(
    results: list[FileResult],
    args: argparse.Namespace,
    free_gb: float,
    requested_symbols: list[str],
    scheduled_symbols: list[str],
    symbol_preflight: list[dict[str, Any]],
) -> tuple[Path, Path]:
    args.date_dir.mkdir(parents=True, exist_ok=True)
    completion_path = args.date_dir / f"bonk_bullish_l2_download_completion_{args.run_tag}.json"
    manifest_path = args.date_dir / f"bonk_bullish_l2_download_manifest_{args.run_tag}.csv"
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    payload = {
        "run_tag": args.run_tag,
        "started_at_utc": STARTED_AT_UTC,
        "finished_at_utc": utc_now(),
        "data_root": args.data_root.as_posix(),
        "date_dir": args.date_dir.as_posix(),
        "from_date": args.from_date,
        "to_date": args.to_date,
        "symbols": requested_symbols,
        "scheduled_symbols": scheduled_symbols,
        "workers": max(1, int(args.workers)),
        "skip_preflight": bool(args.skip_preflight),
        "symbol_preflight": symbol_preflight,
        "data_types": parse_data_types(args.data_types),
        "dry_run": bool(args.dry_run),
        "free_gb_before": free_gb,
        "counts": counts,
        "files": [asdict(result) for result in sorted_results(results)],
    }
    completion_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = list(asdict(results[0]).keys()) if results else list(FileResult.__annotations__.keys())
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in sorted_results(results):
            row = asdict(result)
            row["header"] = "|".join(row["header"] or [])
            writer.writerow(row)
    return completion_path, manifest_path


def sorted_results(results: list[FileResult]) -> list[FileResult]:
    return sorted(results, key=lambda item: (item.date, item.data_type, item.symbol, item.path))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


STARTED_AT_UTC = utc_now()


def main() -> int:
    args = parse_args()
    from_date = parse_date(args.from_date)
    to_date = parse_date(args.to_date)
    symbols = parse_list(args.symbols) + parse_list(args.extra_symbols)
    symbols = list(dict.fromkeys(symbols))
    data_types = parse_data_types(args.data_types)
    dates = list(date_range(from_date, to_date))
    if not symbols:
        raise SystemExit("at least one symbol is required")
    if not data_types:
        raise SystemExit("at least one data type is required")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")

    free_gb = disk_free_gb(args.data_root)
    if not args.dry_run and free_gb < args.min_free_gb:
        raise SystemExit(
            f"free disk space is {free_gb:.2f} GB, below --min-free-gb {args.min_free_gb:.2f}"
        )
    api_key = load_tardis_key(args.env_file) if not args.dry_run or not args.skip_preflight else ""
    if args.dry_run and not api_key:
        scheduled_symbols = symbols
        symbol_preflight = [
            {
                "symbol": symbol,
                "status": "not_checked",
                "exchange": EXCHANGE,
                "type": "",
                "availableSince": "",
            }
            for symbol in symbols
        ]
    else:
        scheduled_symbols, symbol_preflight = preflight_symbols(
            symbols,
            api_key,
            args.timeout_seconds,
            args.skip_preflight,
        )

    missing_symbols = [row["symbol"] for row in symbol_preflight if row.get("status") == "missing"]
    results = missing_symbol_results(args.data_root, dates, data_types, missing_symbols)
    jobs = build_jobs(args.data_root, dates, data_types, scheduled_symbols)
    for result in results:
        print(f"{result.date} {result.data_type} {result.symbol}: {result.status} bytes={result.bytes}")
    results.extend(run_jobs(jobs, args, api_key))

    completion_path, manifest_path = write_outputs(
        results,
        args,
        free_gb,
        symbols,
        scheduled_symbols,
        symbol_preflight,
    )
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"completion_json={completion_path}")
    print(f"manifest_csv={manifest_path}")
    print(f"counts={json.dumps(counts, sort_keys=True)}")
    if any(result.status == "error" for result in results):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
