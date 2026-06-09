#!/usr/bin/env python
"""Build runtime-safe admission thresholds from market-derived caches.

The first admission profile is intentionally small: for each trading date, use
the prior date's decision_frame_v1 spread distribution and set

    entry_cross_threshold_bps = quantile(spread_bps / 2, q)

No legacy fixed panel, labels, scored entries, PnL, MFE, MAE, or root scripts
are read here.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


PARQUET_ROOT = Path("data/canonical_parquet/cex/bullish")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--quantile", type=float, default=0.70)
    parser.add_argument("--out", type=Path, required=True)
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


def prior_day(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def cache_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / PARQUET_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "part_000001.parquet"


def manifest_path(repo_root: Path, symbol: str, day: str) -> Path:
    return repo_root / PARQUET_ROOT / symbol / "decision_frame_v1" / f"dt={day}" / "manifest.json"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def finite_quantile(values: list[float], q: float) -> float:
    clean = sorted(v for v in values if math.isfinite(v))
    if not clean:
        raise ValueError("no finite values for quantile")
    if len(clean) == 1:
        return clean[0]
    pos = max(0.0, min(1.0, q)) * (len(clean) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return clean[lo]
    frac = pos - lo
    return clean[lo] * (1.0 - frac) + clean[hi] * frac


def threshold_from_prior_cache(repo_root: Path, symbol: str, target_day: str, q: float) -> dict[str, Any]:
    source_day = prior_day(target_day)
    parquet_path = cache_path(repo_root, symbol, source_day)
    manifest_file = manifest_path(repo_root, symbol, source_day)
    if not parquet_path.exists():
        raise FileNotFoundError(parquet_path)
    if not manifest_file.exists():
        raise FileNotFoundError(manifest_file)
    table = pq.read_table(parquet_path, columns=["spread_bps"])
    spread = table.column("spread_bps").to_pylist()
    entry_cross = [0.5 * float(value) for value in spread if value is not None and float(value) >= 0.0]
    threshold = finite_quantile(entry_cross, q)
    manifest = read_json(manifest_file)
    return {
        "entry_cross_threshold_bps": threshold,
        "threshold_source": f"prior_day_decision_frame_spread_cross_q{q:.2f}:{source_day}",
        "source_date": source_day,
        "source_row_count": manifest.get("row_count"),
        "source_builder_version": manifest.get("builder_version"),
        "source_schema_version": manifest.get("schema_version"),
        "source_field_hash_sha256": manifest.get("field_hash_sha256"),
        "source_cache_file_sha256": manifest.get("cache_file_sha256"),
        "quantile": q,
        "sample_count": len(entry_cross),
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    out_path = args.out if args.out.is_absolute() else repo_root / args.out
    thresholds = {
        day: threshold_from_prior_cache(repo_root, args.symbol, day, args.quantile)
        for day in date_range(args.from_date, args.to_date)
    }
    payload = {
        "schema_id": "ccusdt_entry_spread_admission_thresholds_v1",
        "symbol": args.symbol,
        "profile": "entry_spread_q70_v1" if abs(args.quantile - 0.70) < 1e-12 else "entry_spread_quantile_v1",
        "rule": "accept if entry_spread_bps / 2 <= prior-date decision_frame spread_cross quantile",
        "quantile": args.quantile,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "runtime_safe": True,
        "forbidden_inputs": ["date/", "scored_entries", "future_labels", "PnL", "MFE", "MAE", "root scripts"],
        "thresholds": thresholds,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
