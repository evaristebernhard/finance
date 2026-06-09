#!/usr/bin/env python
"""Build and validate typed Parquet decision_frame_v1 caches.

This cache is market-derived: canonical trades + canonical L2 updates are
replayed through the runtime-safe Bot decision frame builder. It must not read
legacy fixed panels, scored entries, labels, PnL, MFE, or MAE.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq


BOT_DIR = Path(__file__).resolve().parents[1] / "strategies" / "python" / "ccusdt_tfi_core_idle01"
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from decision_frame import BUILDER_VERSION, CACHE_FIELDS  # noqa: E402
from decision_frame import DecisionFrameBuilder  # noqa: E402
from decision_frame_parity import canonical_path, iter_decision_frames  # noqa: E402


PARQUET_ROOT = "data/canonical_parquet/cex/bullish"
SCHEMA_VERSION = "decision_frame_v1.parquet.schema_v1"
PARQUET_SCHEMA = pa.schema(
    [
        ("schema_id", pa.string()),
        ("runtime_safe", pa.bool_()),
        ("observed_seq", pa.int64()),
        ("exchange_ts_us", pa.int64()),
        ("local_ts_us", pa.int64()),
        ("local_timestamp", pa.int64()),
        ("event_index", pa.int64()),
        ("is_snapshot_batch", pa.bool_()),
        ("factor_eligible", pa.bool_()),
        ("batch_rows", pa.int64()),
        ("crossed_levels_removed", pa.int64()),
        ("best_bid_price", pa.float64()),
        ("best_bid_amount", pa.float64()),
        ("best_ask_price", pa.float64()),
        ("best_ask_amount", pa.float64()),
        ("mid_price", pa.float64()),
        ("mid", pa.float64()),
        ("spread_bps", pa.float64()),
        ("bid_levels", pa.int64()),
        ("ask_levels", pa.int64()),
        ("trade_window_count", pa.int64()),
        ("trade_buy_amount", pa.float64()),
        ("trade_sell_amount", pa.float64()),
        ("trade_notional_quote", pa.float64()),
        ("trade_flow_imbalance", pa.float64()),
        ("mid_change_prev", pa.bool_()),
        ("quote_change_prev", pa.bool_()),
        ("top_size_change_prev", pa.bool_()),
        ("frames_since_mid_change", pa.float64()),
        ("past_event_25_bps", pa.float64()),
        ("fwd_time_60s_bucket", pa.int64()),
    ]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "validate", "parity", "export-ndjson"])
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--input-layer", choices=["canonical", "raw"], default="canonical")
    parser.add_argument("--parity-left", choices=["raw", "canonical"], default="raw")
    parser.add_argument("--parity-right", choices=["cache", "canonical", "raw"], default="cache")
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--progress-interval", type=int, default=50_000)
    parser.add_argument("--float-tol", type=float, default=1e-8)
    parser.add_argument("--max-mismatches", type=int, default=20)
    parser.add_argument("--deep-source-hash", action="store_true")
    parser.add_argument("--deep-field-hash", action="store_true")
    parser.add_argument("--deep-cache-hash", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--cleanup-tmp", action="store_true")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
    current = left
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def cache_dir(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / PARQUET_ROOT / symbol / "decision_frame_v1" / f"dt={day}"


def cache_path(repo_root: Path, symbol: str, day: str) -> Path:
    return cache_dir(repo_root, symbol, day) / "part_000001.parquet"


def manifest_path(repo_root: Path, symbol: str, day: str) -> Path:
    return cache_dir(repo_root, symbol, day) / "manifest.json"


def tmp_dir(repo_root: Path, symbol: str, day: str) -> Path:
    return cache_dir(repo_root, symbol, day) / ".tmp_build"


def failed_path(repo_root: Path, symbol: str, day: str) -> Path:
    return cache_dir(repo_root, symbol, day) / "build.failed.json"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_json_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return format(value, ".17g")
    return str(value)


def update_field_hash(digest: Any, frame: dict[str, Any]) -> None:
    digest.update(
        json.dumps(
            [normalize_value(frame.get(field)) for field in CACHE_FIELDS],
            separators=(",", ":"),
        ).encode("utf-8")
    )
    digest.update(b"\n")


def source_manifest(repo_root: Path, symbol: str, day: str, input_layer: str) -> dict[str, Any]:
    if input_layer == "raw":
        trade_path = raw_path(repo_root, "bullish_trades", symbol, day)
        l2_path = raw_path(repo_root, "bullish_incremental_book_L2", symbol, day)
        return {
            "input_layer": "raw",
            "bullish_trades": file_manifest(repo_root, trade_path),
            "bullish_incremental_book_L2": file_manifest(repo_root, l2_path),
        }
    trade_path = canonical_path(repo_root, symbol, "trade_event_v1", day)
    l2_path = canonical_path(repo_root, symbol, "l2_level_update_v1", day)
    return {
        "input_layer": "canonical_csv_gz",
        "trade_event_v1": file_manifest(repo_root, trade_path),
        "l2_level_update_v1": file_manifest(repo_root, l2_path),
    }


def manifest_input_layer(manifest: dict[str, Any]) -> str:
    raw = str(manifest.get("input_layer") or "").strip().lower()
    if raw in {"raw", "canonical"}:
        return raw
    if manifest.get("source_canonical") or raw == "canonical_csv_gz":
        return "canonical"
    source = manifest.get("source")
    if isinstance(source, dict):
        source_layer = str(source.get("input_layer") or "").strip().lower()
        if source_layer == "raw":
            return "raw"
        if source_layer in {"canonical", "canonical_csv_gz"}:
            return "canonical"
    return "canonical"


def manifest_source(manifest: dict[str, Any]) -> dict[str, Any] | None:
    source = manifest.get("source") or manifest.get("source_canonical")
    return source if isinstance(source, dict) else None


def data_manifest_for_hash(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": manifest.get("schema_version"),
        "builder_version": manifest.get("builder_version"),
        "input_layer": manifest_input_layer(manifest),
        "source": manifest_source(manifest),
        "fields": manifest.get("fields"),
    }


def raw_path(repo_root: Path, dataset: str, symbol: str, day: str) -> Path:
    return (
        repo_root
        / "data"
        / "ccusdt"
        / "v1"
        / "external"
        / dataset
        / f"symbol={symbol}"
        / f"dt={day}"
        / f"{symbol}.csv.gz"
    )


def file_manifest(repo_root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(repo_root)),
        "sha256": hash_file(path),
        "bytes": path.stat().st_size,
    }


def shallow_file_manifest(repo_root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(repo_root)),
        "bytes": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
    }


def shallow_source_manifest(repo_root: Path, symbol: str, day: str, input_layer: str) -> dict[str, Any]:
    if input_layer == "raw":
        return {
            "input_layer": "raw",
            "bullish_trades": shallow_file_manifest(
                repo_root,
                raw_path(repo_root, "bullish_trades", symbol, day),
            ),
            "bullish_incremental_book_L2": shallow_file_manifest(
                repo_root,
                raw_path(repo_root, "bullish_incremental_book_L2", symbol, day),
            ),
        }
    return {
        "input_layer": "canonical_csv_gz",
        "trade_event_v1": shallow_file_manifest(
            repo_root,
            canonical_path(repo_root, symbol, "trade_event_v1", day),
        ),
        "l2_level_update_v1": shallow_file_manifest(
            repo_root,
            canonical_path(repo_root, symbol, "l2_level_update_v1", day),
        ),
    }


def typed_row(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        field.name: coerce_value(frame.get(field.name), field.type)
        for field in PARQUET_SCHEMA
    }


def coerce_value(value: Any, arrow_type: pa.DataType) -> Any:
    if value is None:
        return None
    if pa.types.is_boolean(arrow_type):
        return bool(value)
    if pa.types.is_integer(arrow_type):
        return int(value)
    if pa.types.is_floating(arrow_type):
        return float(value)
    return str(value)


def iter_raw_decision_frames(repo_root: Path, symbol: str, day: str) -> Iterator[dict[str, Any]]:
    trades = read_raw_trades(repo_root, symbol, day)
    trade_pos = 0
    builder = DecisionFrameBuilder()
    for batch in iter_raw_l2_batches(repo_root, symbol, day):
        ts = int(batch[0]["local_ts_us"])
        while trade_pos < len(trades) and int(trades[trade_pos]["local_ts_us"]) <= ts:
            builder.observe_trade(trades[trade_pos])
            trade_pos += 1
        frame = builder.build_from_l2_updates(batch)
        if frame is not None:
            yield frame


def read_raw_trades(repo_root: Path, symbol: str, day: str) -> list[dict[str, Any]]:
    path = raw_path(repo_root, "bullish_trades", symbol, day)
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "local_ts_us": int(row["local_timestamp"]),
                    "side": row["side"],
                    "price": float(row["price"]),
                    "qty": float(row["amount"]),
                }
            )
    rows.sort(key=lambda item: int(item["local_ts_us"]))
    return rows


def iter_raw_l2_batches(repo_root: Path, symbol: str, day: str) -> Iterator[list[dict[str, Any]]]:
    path = raw_path(repo_root, "bullish_incremental_book_L2", symbol, day)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        batch: list[dict[str, Any]] = []
        current_ts: int | None = None
        for row in csv.DictReader(handle):
            ts = int(row["local_timestamp"])
            if current_ts is not None and ts != current_ts and batch:
                yield batch
                batch = []
            current_ts = ts
            batch.append(
                {
                    "seq": None,
                    "exchange_ts_us": int(row["timestamp"]),
                    "local_ts_us": ts,
                    "is_snapshot": str(row["is_snapshot"]).strip().lower() == "true",
                    "side": row["side"],
                    "price": float(row["price"]),
                    "qty": float(row["amount"]),
                }
            )
        if batch:
            yield batch


def frame_iter(repo_root: Path, symbol: str, day: str, input_layer: str) -> Iterator[dict[str, Any]]:
    if input_layer == "raw":
        return iter_raw_decision_frames(repo_root, symbol, day)
    return iter_decision_frames(repo_root, symbol, day)


def build_one(
    repo_root: Path,
    symbol: str,
    day: str,
    progress_interval: int,
    input_layer: str,
    batch_size: int,
    force: bool,
    cleanup_tmp: bool,
) -> dict[str, Any]:
    out_dir = cache_dir(repo_root, symbol, day)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_path(repo_root, symbol, day)
    manifest_file = manifest_path(repo_root, symbol, day)
    if not force:
        validation = validate_one(repo_root, symbol, day)
        if validation.get("ok") and validation.get("input_layer") == input_layer:
            return {
                "schema_id": "decision_frame_parquet_cache_manifest_v1",
                "symbol": symbol,
                "date": day,
                "dataset": "decision_frame_v1",
                "status": "skipped_valid_cache",
                "row_count": validation.get("row_count"),
                "cache_file": str(out_path.relative_to(repo_root)),
                "elapsed_wall_ms": 0,
            }
    temp_dir = tmp_dir(repo_root, symbol, day)
    if cleanup_tmp and temp_dir.exists():
        shutil.rmtree(temp_dir)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=False)
    temp_out = temp_dir / "part_000001.parquet"
    temp_manifest = temp_dir / "manifest.json"
    fail_file = failed_path(repo_root, symbol, day)
    if fail_file.exists():
        fail_file.unlink()
    field_digest = hashlib.sha256()
    batch_rows: list[dict[str, Any]] = []
    rows = 0
    start = time.perf_counter()
    timing: dict[str, int] = {}
    source_start = time.perf_counter()
    source = source_manifest(repo_root, symbol, day, input_layer)
    timing["source_hash_ms"] = int((time.perf_counter() - source_start) * 1000)
    writer: pq.ParquetWriter | None = None
    try:
        for frame in frame_iter(repo_root, symbol, day, input_layer):
            batch_rows.append(typed_row(frame))
            update_field_hash(field_digest, frame)
            rows += 1
            if len(batch_rows) >= batch_size:
                writer = write_batch(writer, temp_out, batch_rows)
                batch_rows = []
            if progress_interval > 0 and rows % progress_interval == 0:
                print(
                    f"decision_frame parquet build day={day} rows={rows}",
                    file=sys.stderr,
                    flush=True,
                )
        if batch_rows:
            writer = write_batch(writer, temp_out, batch_rows)
        if writer is None:
            writer = pq.ParquetWriter(temp_out, PARQUET_SCHEMA, compression="zstd")
        writer.close()
        writer = None
        timing["build_write_ms"] = int((time.perf_counter() - start) * 1000) - timing["source_hash_ms"]
        cache_hash_start = time.perf_counter()
        cache_sha = hash_file(temp_out)
        timing["cache_hash_ms"] = int((time.perf_counter() - cache_hash_start) * 1000)
        data_manifest = {
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "input_layer": input_layer,
            "source": source,
            "fields": CACHE_FIELDS,
        }
        manifest = {
            "schema_id": "decision_frame_parquet_cache_manifest_v1",
            "symbol": symbol,
            "date": day,
            "dataset": "decision_frame_v1",
            "schema_version": SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "input_layer": input_layer,
            "fields": CACHE_FIELDS,
            "row_count": rows,
            "field_hash_sha256": field_digest.hexdigest(),
            "cache_file": str(out_path.relative_to(repo_root)),
            "cache_file_sha256": cache_sha,
            "source": source,
            "data_manifest_hash": stable_json_hash(data_manifest),
            "timing_ms": timing,
            "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        }
        temp_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.replace(temp_out, out_path)
        os.replace(temp_manifest, manifest_file)
        shutil.rmtree(temp_dir)
        return manifest
    except Exception as exc:
        if writer is not None:
            writer.close()
        failed = {
            "schema_id": "decision_frame_cache_build_failed_v1",
            "symbol": symbol,
            "date": day,
            "input_layer": input_layer,
            "error": repr(exc),
            "rows_written_before_failure": rows,
            "tmp_dir": str(temp_dir),
            "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        }
        fail_file.write_text(json.dumps(failed, indent=2), encoding="utf-8")
        raise


def write_batch(
    writer: pq.ParquetWriter | None,
    path: Path,
    rows: list[dict[str, Any]],
) -> pq.ParquetWriter:
    table = pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA)
    if writer is None:
        writer = pq.ParquetWriter(path, PARQUET_SCHEMA, compression="zstd")
    writer.write_table(table)
    return writer


def iter_cached_decision_frames(repo_root: Path, symbol: str, day: str) -> Iterator[dict[str, Any]]:
    validation = validate_one(repo_root, symbol, day)
    if not validation.get("ok"):
        raise RuntimeError(f"invalid decision_frame parquet cache for {day}: {validation}")
    parquet_file = pq.ParquetFile(cache_path(repo_root, symbol, day))
    for batch in parquet_file.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            yield row


def export_ndjson(repo_root: Path, symbol: str, day: str) -> dict[str, Any]:
    validation = validate_one(repo_root, symbol, day)
    if not validation.get("ok"):
        raise RuntimeError(f"invalid decision_frame parquet cache for {day}: {validation}")
    rows = 0
    for frame in iter_cached_decision_frames(repo_root, symbol, day):
        print(json.dumps(json_ready(frame), separators=(",", ":"), allow_nan=False))
        rows += 1
    return {
        "date": day,
        "ok": True,
        "status": "exported_ndjson",
        "row_count": rows,
        "cache_file": validation.get("cache_file"),
    }


def json_ready(value: Any) -> Any:
    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        if math.isnan(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


def validate_one(
    repo_root: Path,
    symbol: str,
    day: str,
    *,
    deep_source_hash: bool = False,
    deep_field_hash: bool = False,
    deep_cache_hash: bool = False,
) -> dict[str, Any]:
    manifest_file = manifest_path(repo_root, symbol, day)
    if not manifest_file.exists():
        return {"date": day, "ok": False, "status": "missing_manifest"}
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    path = cache_path(repo_root, symbol, day)
    if not path.exists():
        return {"date": day, "ok": False, "status": "missing_cache"}
    input_layer = manifest_input_layer(manifest)
    stored_source = manifest_source(manifest)
    source_ok: bool | None = None
    if deep_source_hash:
        actual_source = source_manifest(repo_root, symbol, day, input_layer)
        if isinstance(stored_source, dict) and "input_layer" not in stored_source:
            actual_source = {
                key: value for key, value in actual_source.items() if key != "input_layer"
            }
        source_ok = actual_source == stored_source
    parquet_file = pq.ParquetFile(path)
    cache_file_hash: str | None = hash_file(path) if deep_cache_hash else None
    field_hash: str | None = None
    field_ok: bool | None = None
    if deep_field_hash:
        table = pq.read_table(path, schema=PARQUET_SCHEMA)
        field_digest = hashlib.sha256()
        for row in table.to_pylist():
            update_field_hash(field_digest, row)
        field_hash = field_digest.hexdigest()
        field_ok = field_hash == manifest.get("field_hash_sha256")
    row_count = parquet_file.metadata.num_rows
    schema_names = parquet_file.schema_arrow.names
    expected_names = [field.name for field in PARQUET_SCHEMA]
    data_manifest_hash_ok: bool | None = None
    stored_data_manifest_hash = manifest.get("data_manifest_hash")
    if stored_data_manifest_hash:
        data_manifest_hash_ok = (
            stable_json_hash(data_manifest_for_hash(manifest)) == stored_data_manifest_hash
        )
    source_pass = True if source_ok is None else source_ok
    field_pass = True if field_ok is None else field_ok
    data_manifest_pass = True if data_manifest_hash_ok is None else data_manifest_hash_ok
    ok = (
        manifest.get("schema_version") == SCHEMA_VERSION
        and manifest.get("builder_version") == BUILDER_VERSION
        and manifest.get("fields") == CACHE_FIELDS
        and schema_names == expected_names
        and row_count == int(manifest.get("row_count") or -1)
        and (cache_file_hash is None or cache_file_hash == manifest.get("cache_file_sha256"))
        and source_pass
        and field_pass
        and data_manifest_pass
    )
    return {
        "date": day,
        "ok": ok,
        "status": "ok" if ok else "invalid_cache_or_manifest",
        "input_layer": input_layer,
        "schema_version": manifest.get("schema_version"),
        "builder_version": manifest.get("builder_version"),
        "row_count": row_count,
        "field_hash_sha256": field_hash,
        "source_ok": source_ok,
        "field_ok": field_ok,
        "data_manifest_hash_ok": data_manifest_hash_ok,
        "cache_file_hash_ok": None
        if cache_file_hash is None
        else cache_file_hash == manifest.get("cache_file_sha256"),
        "validation_mode": {
            "deep_source_hash": deep_source_hash,
            "deep_field_hash": deep_field_hash,
            "deep_cache_hash": deep_cache_hash,
        },
        "cache_file": str(path),
    }


def iter_parity_frames(
    repo_root: Path,
    symbol: str,
    day: str,
    source: str,
) -> Iterator[dict[str, Any]]:
    if source == "cache":
        return iter_cached_decision_frames(repo_root, symbol, day)
    if source in {"raw", "canonical"}:
        return frame_iter(repo_root, symbol, day, source)
    raise ValueError(f"unsupported parity source: {source}")


def compare_values(left: Any, right: Any, *, float_tol: float) -> tuple[bool, float | None]:
    if left is None or right is None:
        return left is None and right is None, None
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right), None
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            left_float = float(left)
            right_float = float(right)
        except (TypeError, ValueError):
            return str(left) == str(right), None
        if math.isnan(left_float) or math.isnan(right_float):
            return math.isnan(left_float) and math.isnan(right_float), None
        if math.isinf(left_float) or math.isinf(right_float):
            return left_float == right_float, None
        diff = right_float - left_float
        return abs(diff) <= float_tol, diff
    return str(left) == str(right), None


def parity_one(
    repo_root: Path,
    symbol: str,
    day: str,
    left_source: str,
    right_source: str,
    *,
    float_tol: float,
    max_mismatches: int,
    progress_interval: int,
) -> dict[str, Any]:
    left_iter = iter_parity_frames(repo_root, symbol, day, left_source)
    right_iter = iter_parity_frames(repo_root, symbol, day, right_source)
    left_hash = hashlib.sha256()
    right_hash = hashlib.sha256()
    field_counts: dict[str, int] = {}
    field_max_abs_diff: dict[str, float] = {}
    samples: list[dict[str, Any]] = []
    rows = 0
    left_rows = 0
    right_rows = 0
    row_mismatch_count = 0
    while True:
        try:
            left = next(left_iter)
            left_rows += 1
        except StopIteration:
            left = None
        try:
            right = next(right_iter)
            right_rows += 1
        except StopIteration:
            right = None
        if left is None and right is None:
            break
        rows += 1
        if progress_interval > 0 and rows % progress_interval == 0:
            print(
                (
                    f"decision_frame parity day={day} rows={rows} "
                    f"{left_source}->{right_source} mismatches={row_mismatch_count}"
                ),
                file=sys.stderr,
                flush=True,
            )
        if left is None or right is None:
            row_mismatch_count += 1
            if len(samples) < max_mismatches:
                samples.append(
                    {
                        "date": day,
                        "row": rows,
                        "kind": "row_count_mismatch",
                        "left_present": left is not None,
                        "right_present": right is not None,
                    }
                )
            continue
        update_field_hash(left_hash, left)
        update_field_hash(right_hash, right)
        bad_fields: list[str] = []
        for field in CACHE_FIELDS:
            ok, diff = compare_values(left.get(field), right.get(field), float_tol=float_tol)
            if diff is not None:
                field_max_abs_diff[field] = max(field_max_abs_diff.get(field, 0.0), abs(diff))
            if not ok:
                field_counts[field] = field_counts.get(field, 0) + 1
                bad_fields.append(field)
        if bad_fields:
            row_mismatch_count += 1
            if len(samples) < max_mismatches:
                sample: dict[str, Any] = {
                    "date": day,
                    "row": rows,
                    "kind": "field_mismatch",
                    "fields": bad_fields[:12],
                    "left_local_ts_us": left.get("local_ts_us"),
                    "right_local_ts_us": right.get("local_ts_us"),
                    "left_event_index": left.get("event_index"),
                    "right_event_index": right.get("event_index"),
                }
                for field in bad_fields[:6]:
                    sample[f"left_{field}"] = left.get(field)
                    sample[f"right_{field}"] = right.get(field)
                samples.append(sample)
    left_field_hash = left_hash.hexdigest()
    right_field_hash = right_hash.hexdigest()
    ok = (
        left_rows == right_rows
        and row_mismatch_count == 0
        and left_field_hash == right_field_hash
    )
    return {
        "date": day,
        "ok": ok,
        "left_source": left_source,
        "right_source": right_source,
        "rows_compared": rows,
        "left_rows": left_rows,
        "right_rows": right_rows,
        "row_mismatch_count": row_mismatch_count,
        "field_mismatch_counts": dict(sorted(field_counts.items())),
        "field_max_abs_diff": dict(sorted(field_max_abs_diff.items())),
        "left_field_hash": left_field_hash,
        "right_field_hash": right_field_hash,
        "sample_mismatches": samples,
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    days = date_range(args.from_date, args.to_date)
    per_day = []
    for day in days:
        if args.command == "export-ndjson":
            if len(days) != 1:
                raise SystemExit("export-ndjson expects exactly one date")
            export_ndjson(repo_root, args.symbol, day)
            return 0
        if args.command == "build":
            print(f"decision_frame parquet build day={day}", file=sys.stderr, flush=True)
            per_day.append(
                build_one(
                    repo_root,
                    args.symbol,
                    day,
                    args.progress_interval,
                    args.input_layer,
                    args.batch_size,
                    args.force,
                    args.cleanup_tmp,
                )
            )
        elif args.command == "parity":
            print(
                (
                    f"decision_frame parity day={day} "
                    f"{args.parity_left}->{args.parity_right}"
                ),
                file=sys.stderr,
                flush=True,
            )
            per_day.append(
                parity_one(
                    repo_root,
                    args.symbol,
                    day,
                    args.parity_left,
                    args.parity_right,
                    float_tol=args.float_tol,
                    max_mismatches=args.max_mismatches,
                    progress_interval=args.progress_interval,
                )
            )
        else:
            per_day.append(
                validate_one(
                    repo_root,
                    args.symbol,
                    day,
                    deep_source_hash=args.deep_source_hash,
                    deep_field_hash=args.deep_field_hash,
                    deep_cache_hash=args.deep_cache_hash,
                )
            )
    ok = all(item.get("ok", True) for item in per_day)
    summary = {
        "ok": ok,
        "command": args.command,
        "symbol": args.symbol,
        "dates": days,
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "per_day": per_day,
        "total_rows": sum(int(item.get("row_count") or item.get("rows_compared") or 0) for item in per_day),
    }
    print(json.dumps(summary, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
