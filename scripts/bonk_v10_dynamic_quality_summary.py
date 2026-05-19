#!/usr/bin/env python
"""Build lightweight dynamic quality summaries for BONK V10 replay outputs.

The script is intentionally read-mostly and chunked. It summarizes completed
replay state parts plus existing V10 diagnostics without promoting any trading
or alpha conclusion.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    run_tag: str

    @property
    def state_root(self) -> Path:
        return (
            self.data_root
            / "derived"
            / "bonk_v10_replayed_book_state"
            / f"run_tag={self.run_tag}"
        )

    @property
    def replay_manifest(self) -> Path:
        return self.date_dir / f"bonk_v10_replay_state_manifest_{self.run_tag}.csv"

    @property
    def replay_full_summary(self) -> Path:
        return self.date_dir / f"bonk_v10_incremental_replay_full_summary_{self.run_tag}.csv"

    @property
    def raw_inventory(self) -> Path:
        return self.date_dir / f"bonk_v10_raw_inventory_{self.run_tag}.csv"

    @property
    def potential_state(self) -> Path:
        return self.date_dir / f"bonk_v10_potential_state_{self.run_tag}.csv"

    @property
    def filter_state(self) -> Path:
        return self.date_dir / f"bonk_v10_filter_state_{self.run_tag}.csv"

    @property
    def anchor_candidates(self) -> Path:
        return self.date_dir / f"bonk_v10_anchor_candidates_{self.run_tag}.csv"

    @property
    def path_summary(self) -> Path:
        return self.date_dir / f"bonk_v10_long_short_episode_backtest_{self.run_tag}_summary.csv"

    @property
    def negative_controls(self) -> Path:
        return self.date_dir / f"bonk_v10_negative_controls_{self.run_tag}.csv"

    @property
    def spearman(self) -> Path:
        return self.date_dir / f"bonk_v10_spearman_stability_{self.run_tag}.csv"

    @property
    def horizon_decay(self) -> Path:
        return self.date_dir / f"bonk_v10_horizon_decay_{self.run_tag}.csv"

    @property
    def failure_report(self) -> Path:
        return self.date_dir / f"bonk_v10_failure_report_{self.run_tag}.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize BONK V10 dynamic replay quality.")
    parser.add_argument("--data-root", type=Path, default=Path("data/bonk/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--run-tag", default="20260514_bonk_v10_stage1_pilot")
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def read_csv_if_exists(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def local_hour_from_us(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return pd.to_datetime(numeric, unit="us", utc=True, errors="coerce").dt.floor("h")


def csv_header(path: Path) -> list[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def has_multilevel_schema(state_parts: Path) -> bool:
    first_part = state_parts / "part_000001.csv"
    header = csv_header(first_part)
    required = {"bid_top_levels_json", "ask_top_levels_json", "bid_depth_25", "ask_depth_25"}
    return required.issubset(set(header))


def completed_manifest(paths: Paths) -> pd.DataFrame:
    manifest = read_csv_if_exists(paths.replay_manifest)
    if manifest.empty or "status" not in manifest.columns:
        return pd.DataFrame()
    return manifest[manifest["status"].eq("completed")].copy()


def state_part_files(paths: Paths) -> list[Path]:
    manifest = completed_manifest(paths)
    if manifest.empty or "output_path" not in manifest.columns:
        return []
    files: list[Path] = []
    for row in manifest.itertuples(index=False):
        output_path = Path(getattr(row, "output_path"))
        part_files = int(getattr(row, "part_files", 0) or 0)
        files.extend(output_path / f"part_{part_index:06}.csv" for part_index in range(1, part_files + 1))
    files = [path for path in files if path.exists()]
    return files


def completed_state_dirs(paths: Paths) -> list[Path]:
    manifest = completed_manifest(paths)
    if manifest.empty or "output_path" not in manifest.columns:
        return []
    return [Path(value) for value in manifest["output_path"].dropna().astype(str)]


def add_hour_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["hour_utc"] = local_hour_from_us(frame["local_timestamp"])
    frame["date"] = frame["hour_utc"].dt.strftime("%Y-%m-%d")
    frame["hour_utc"] = frame["hour_utc"].dt.strftime("%Y-%m-%dT%H:00:00Z")
    return frame


def summarize_book_hourly(paths: Paths, chunksize: int) -> pd.DataFrame:
    files = state_part_files(paths)
    if not files:
        return pd.DataFrame()
    usecols = [
        "symbol",
        "local_timestamp",
        "best_bid_price",
        "best_ask_price",
        "spread_bps",
        "bid_levels",
        "ask_levels",
        "crossed_levels_removed",
        "bid_depth_5",
        "ask_depth_5",
        "imbalance_5",
        "bid_depth_25",
        "ask_depth_25",
        "imbalance_25",
    ]
    chunks: list[pd.DataFrame] = []
    for path in files:
        header = csv_header(path)
        present_usecols = [col for col in usecols if col in header]
        if "symbol" not in present_usecols or "local_timestamp" not in present_usecols:
            continue
        for chunk in pd.read_csv(path, usecols=present_usecols, chunksize=chunksize):
            for missing in set(usecols) - set(chunk.columns):
                chunk[missing] = pd.NA
            chunk = add_hour_columns(chunk)
            chunk["top_of_book_ok"] = (
                pd.to_numeric(chunk["best_bid_price"], errors="coerce").gt(0)
                & pd.to_numeric(chunk["best_ask_price"], errors="coerce").gt(0)
            ).astype(float)
            group = (
                chunk.groupby(["symbol", "date", "hour_utc"], dropna=False)
                .agg(
                    replay_rows=("spread_bps", "size"),
                    avg_spread_bps=("spread_bps", "mean"),
                    median_spread_bps=("spread_bps", "median"),
                    avg_bid_levels=("bid_levels", "mean"),
                    avg_ask_levels=("ask_levels", "mean"),
                    crossed_level_removals=("crossed_levels_removed", "sum"),
                    top_of_book_coverage=("top_of_book_ok", "mean"),
                    bid_depth_5_mean=("bid_depth_5", "mean"),
                    ask_depth_5_mean=("ask_depth_5", "mean"),
                    imbalance_5_mean=("imbalance_5", "mean"),
                    bid_depth_25_mean=("bid_depth_25", "mean"),
                    ask_depth_25_mean=("ask_depth_25", "mean"),
                    imbalance_25_mean=("imbalance_25", "mean"),
                )
                .reset_index()
            )
            chunks.append(group)
    if not chunks:
        return pd.DataFrame()
    hourly = pd.concat(chunks, ignore_index=True)
    weighted_cols = [
        "avg_spread_bps",
        "avg_bid_levels",
        "avg_ask_levels",
        "top_of_book_coverage",
        "bid_depth_5_mean",
        "ask_depth_5_mean",
        "imbalance_5_mean",
        "bid_depth_25_mean",
        "ask_depth_25_mean",
        "imbalance_25_mean",
    ]
    for col in weighted_cols:
        hourly[f"{col}_weighted"] = hourly[col] * hourly["replay_rows"]
    out = (
        hourly.groupby(["symbol", "date", "hour_utc"], dropna=False)
        .agg(
            replay_rows=("replay_rows", "sum"),
            median_spread_bps=("median_spread_bps", "median"),
            crossed_level_removals=("crossed_level_removals", "sum"),
            **{f"{col}_weighted": (f"{col}_weighted", "sum") for col in weighted_cols},
        )
        .reset_index()
    )
    for col in weighted_cols:
        out[col] = out[f"{col}_weighted"] / out["replay_rows"].clip(lower=1)
        out = out.drop(columns=[f"{col}_weighted"])
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    return out.sort_values(["symbol", "hour_utc"])


def summarize_book_daily(hourly: pd.DataFrame, replay_full_summary: pd.DataFrame) -> pd.DataFrame:
    if hourly.empty:
        return pd.DataFrame()
    weighted_cols = [
        "avg_spread_bps",
        "avg_bid_levels",
        "avg_ask_levels",
        "top_of_book_coverage",
        "bid_depth_5_mean",
        "ask_depth_5_mean",
        "imbalance_5_mean",
        "bid_depth_25_mean",
        "ask_depth_25_mean",
        "imbalance_25_mean",
    ]
    work = hourly.copy()
    for col in weighted_cols:
        work[f"{col}_weighted"] = work[col] * work["replay_rows"]
    out = (
        work.groupby(["run_tag", "symbol", "date"], dropna=False)
        .agg(
            replay_rows=("replay_rows", "sum"),
            hourly_rows=("hour_utc", "nunique"),
            median_spread_bps=("median_spread_bps", "median"),
            crossed_level_removals=("crossed_level_removals", "sum"),
            **{f"{col}_weighted": (f"{col}_weighted", "sum") for col in weighted_cols},
        )
        .reset_index()
    )
    for col in weighted_cols:
        out[col] = out[f"{col}_weighted"] / out["replay_rows"].clip(lower=1)
        out = out.drop(columns=[f"{col}_weighted"])
    if not replay_full_summary.empty:
        cols = [
            "date",
            "symbol",
            "raw_rows_read",
            "snapshot_batches",
            "crossed_batches",
            "crossed_level_removals",
        ]
        have = [col for col in cols if col in replay_full_summary.columns]
        suffix = replay_full_summary[have].rename(
            columns={"crossed_level_removals": "full_summary_crossed_level_removals"}
        )
        out = out.merge(suffix, on=["date", "symbol"], how="left")
    out["guardrail"] = GUARDRAIL
    return out.sort_values(["symbol", "date"])


def summarize_potential_hourly(paths: Paths, chunksize: int) -> pd.DataFrame:
    if not paths.potential_state.exists():
        return pd.DataFrame()
    usecols = [
        "date",
        "symbol",
        "local_timestamp",
        "spread_bps",
        "net_potential",
        "energy_release",
        "fill_realism_score",
        "queue_depth_pressure",
        "cancellation_withdrawal_energy",
        "replenish_relaxation",
        "trade_flow_imbalance",
    ]
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(paths.potential_state, usecols=usecols, chunksize=chunksize):
        chunk = add_hour_columns(chunk.drop(columns=["date"], errors="ignore"))
        group = (
            chunk.groupby(["symbol", "date", "hour_utc"], dropna=False)
            .agg(
                potential_rows=("net_potential", "size"),
                spread_bps_mean=("spread_bps", "mean"),
                net_potential_mean=("net_potential", "mean"),
                net_potential_median=("net_potential", "median"),
                energy_release_mean=("energy_release", "mean"),
                fill_realism_score_mean=("fill_realism_score", "mean"),
                queue_depth_pressure_mean=("queue_depth_pressure", "mean"),
                cancellation_withdrawal_energy_mean=("cancellation_withdrawal_energy", "mean"),
                replenish_relaxation_mean=("replenish_relaxation", "mean"),
                trade_flow_imbalance_mean=("trade_flow_imbalance", "mean"),
            )
            .reset_index()
        )
        chunks.append(group)
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks, ignore_index=True)
    metric_cols = [col for col in out.columns if col.endswith("_mean")]
    for col in metric_cols:
        out[f"{col}_weighted"] = out[col] * out["potential_rows"]
    agg = (
        out.groupby(["symbol", "date", "hour_utc"], dropna=False)
        .agg(
            potential_rows=("potential_rows", "sum"),
            net_potential_median=("net_potential_median", "median"),
            **{f"{col}_weighted": (f"{col}_weighted", "sum") for col in metric_cols},
        )
        .reset_index()
    )
    for col in metric_cols:
        agg[col] = agg[f"{col}_weighted"] / agg["potential_rows"].clip(lower=1)
        agg = agg.drop(columns=[f"{col}_weighted"])
    agg.insert(0, "run_tag", paths.run_tag)
    agg["guardrail"] = GUARDRAIL
    return agg.sort_values(["symbol", "hour_utc"])


def summarize_filter_hourly(paths: Paths, chunksize: int) -> pd.DataFrame:
    if not paths.filter_state.exists():
        return pd.DataFrame()
    usecols = [
        "fold",
        "date",
        "symbol",
        "local_timestamp",
        "net_bucket_train_fit",
        "energy_bucket_train_fit",
        "fill_bucket_train_fit",
        "flow_bucket_train_fit",
        "spread_bucket_train_fit",
    ]
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(paths.filter_state, usecols=usecols, chunksize=chunksize):
        chunk = add_hour_columns(chunk.drop(columns=["date"], errors="ignore"))
        chunk["net_high"] = (chunk["net_bucket_train_fit"] == "high").astype(float)
        chunk["net_low"] = (chunk["net_bucket_train_fit"] == "low").astype(float)
        chunk["energy_high"] = (chunk["energy_bucket_train_fit"] == "high").astype(float)
        chunk["fill_low"] = (chunk["fill_bucket_train_fit"] == "low").astype(float)
        chunk["fill_high"] = (chunk["fill_bucket_train_fit"] == "high").astype(float)
        chunk["flow_high_abs"] = (chunk["flow_bucket_train_fit"] == "high_abs").astype(float)
        chunk["spread_high"] = (chunk["spread_bucket_train_fit"] == "wide").astype(float)
        group = (
            chunk.groupby(["symbol", "date", "hour_utc"], dropna=False)
            .agg(
                filter_rows=("fold", "size"),
                folds=("fold", "nunique"),
                net_high_rate=("net_high", "mean"),
                net_low_rate=("net_low", "mean"),
                energy_high_rate=("energy_high", "mean"),
                fill_low_rate=("fill_low", "mean"),
                fill_high_rate=("fill_high", "mean"),
                flow_high_abs_rate=("flow_high_abs", "mean"),
                spread_high_rate=("spread_high", "mean"),
            )
            .reset_index()
        )
        chunks.append(group)
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks, ignore_index=True)
    rate_cols = [col for col in out.columns if col.endswith("_rate")]
    for col in rate_cols:
        out[f"{col}_weighted"] = out[col] * out["filter_rows"]
    agg = (
        out.groupby(["symbol", "date", "hour_utc"], dropna=False)
        .agg(
            filter_rows=("filter_rows", "sum"),
            folds=("folds", "max"),
            **{f"{col}_weighted": (f"{col}_weighted", "sum") for col in rate_cols},
        )
        .reset_index()
    )
    for col in rate_cols:
        agg[col] = agg[f"{col}_weighted"] / agg["filter_rows"].clip(lower=1)
        agg = agg.drop(columns=[f"{col}_weighted"])
    agg.insert(0, "run_tag", paths.run_tag)
    agg["guardrail"] = GUARDRAIL
    return agg.sort_values(["symbol", "hour_utc"])


def summarize_coverage(paths: Paths) -> pd.DataFrame:
    inventory = read_csv_if_exists(paths.raw_inventory)
    manifest = read_csv_if_exists(paths.replay_manifest)
    if inventory.empty:
        return pd.DataFrame()
    inc = inventory[inventory["data_type"].eq("incremental_book_L2")].copy()
    keep = ["date", "symbol", "status", "bytes", "required_schema_ok", "expected_path"]
    inc = inc[[col for col in keep if col in inc.columns]].rename(columns={"status": "raw_status"})
    if not manifest.empty:
        have = [
            "date",
            "symbol",
            "status",
            "output_path",
            "part_files",
            "raw_rows_read",
            "replay_rows",
        ]
        inc = inc.merge(
            manifest[[col for col in have if col in manifest.columns]].rename(
                columns={"status": "replay_status"}
            ),
            on=["date", "symbol"],
            how="left",
        )
    else:
        inc["replay_status"] = ""
    schema_rows = []
    for state_dir in completed_state_dirs(paths):
        symbol = state_dir.parent.parent.name.removeprefix("symbol=")
        date = state_dir.parent.name.removeprefix("dt=")
        schema_rows.append(
            {
                "date": date,
                "symbol": symbol,
                "state_parts_path": state_dir.as_posix(),
                "multilevel_schema_ok": has_multilevel_schema(state_dir),
                "actual_part_files": len(list(state_dir.glob("part_*.csv"))),
            }
        )
    schema = pd.DataFrame(schema_rows)
    if not schema.empty:
        inc = inc.merge(schema, on=["date", "symbol"], how="left")
    inc["replay_status"] = inc["replay_status"].fillna("pending")
    inc["multilevel_schema_ok"] = inc["multilevel_schema_ok"].fillna(False)
    inc.insert(0, "run_tag", paths.run_tag)
    inc["guardrail"] = GUARDRAIL
    return inc.sort_values(["symbol", "date"])


def artifact_status_rows(paths: Paths) -> pd.DataFrame:
    rows = []
    artifacts = [
        ("replay_manifest", paths.replay_manifest),
        ("replay_full_summary", paths.replay_full_summary),
        ("potential_state", paths.potential_state),
        ("filter_state", paths.filter_state),
        ("anchor_candidates", paths.anchor_candidates),
        ("path_summary", paths.path_summary),
        ("negative_controls", paths.negative_controls),
        ("spearman_stability", paths.spearman),
        ("horizon_decay", paths.horizon_decay),
        ("failure_report", paths.failure_report),
    ]
    for name, path in artifacts:
        row = {
            "run_tag": paths.run_tag,
            "artifact": name,
            "path": path.as_posix(),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "rows": 0,
            "symbols": "",
            "dates": "",
            "guardrail": GUARDRAIL,
        }
        if path.exists() and path.stat().st_size > 0:
            try:
                frame = pd.read_csv(path, usecols=lambda col: col in {"symbol", "date"})
                row["rows"] = int(len(frame))
                if "symbol" in frame.columns:
                    row["symbols"] = "|".join(sorted(frame["symbol"].dropna().astype(str).unique()))
                if "date" in frame.columns:
                    row["dates"] = "|".join(sorted(frame["date"].dropna().astype(str).unique()))
            except Exception as exc:  # pragma: no cover - diagnostic fallback
                row["symbols"] = f"read_error:{type(exc).__name__}"
        rows.append(row)
    return pd.DataFrame(rows)


def write_outputs(paths: Paths, frames: dict[str, pd.DataFrame]) -> dict[str, Path]:
    outputs = {
        "book_hourly": paths.date_dir / f"bonk_v10_dynamic_quality_book_hourly_{paths.run_tag}.csv",
        "book_daily": paths.date_dir / f"bonk_v10_dynamic_quality_book_daily_{paths.run_tag}.csv",
        "potential_hourly": paths.date_dir
        / f"bonk_v10_dynamic_quality_potential_hourly_{paths.run_tag}.csv",
        "filter_hourly": paths.date_dir / f"bonk_v10_dynamic_quality_filter_hourly_{paths.run_tag}.csv",
        "coverage": paths.date_dir / f"bonk_v10_dynamic_quality_coverage_{paths.run_tag}.csv",
        "artifact_status": paths.date_dir
        / f"bonk_v10_dynamic_quality_artifact_status_{paths.run_tag}.csv",
    }
    for key, frame in frames.items():
        out = outputs[key]
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(out, index=False)
    return outputs


def write_markdown(paths: Paths, outputs: dict[str, Path], frames: dict[str, pd.DataFrame]) -> Path:
    coverage = frames.get("coverage", pd.DataFrame())
    completed = int(coverage["replay_status"].eq("completed").sum()) if not coverage.empty else 0
    total = int(len(coverage)) if not coverage.empty else 0
    old_schema = (
        coverage[
            coverage["replay_status"].eq("completed") & ~coverage["multilevel_schema_ok"].astype(bool)
        ][["symbol", "date"]]
        if not coverage.empty and "multilevel_schema_ok" in coverage.columns
        else pd.DataFrame()
    )
    failures = read_csv_if_exists(paths.failure_report)
    blockers = (
        failures[failures["severity"].eq("blocker")]["check_name"].tolist()
        if not failures.empty and "severity" in failures.columns
        else []
    )
    lines = [
        "# BONK V10 Dynamic Quality Summary",
        "",
        f"Run tag: `{paths.run_tag}`",
        "",
        "Research-only diagnostics. No trading advice, execution recommendation, or alpha claim.",
        "",
        "## Replay Coverage",
        "",
        f"- Completed replay state files: `{completed}/{total}`.",
        f"- Failure blockers: `{', '.join(blockers) if blockers else 'none'}`.",
        f"- Completed old-schema rows: `{len(old_schema)}`.",
    ]
    if not old_schema.empty:
        labels = ", ".join(f"{row.symbol} {row.date}" for row in old_schema.itertuples())
        lines.append(f"- Old-schema completed shards: `{labels}`.")
    lines.extend(["", "## Output Tables", ""])
    for key, path in outputs.items():
        frame = frames.get(key, pd.DataFrame())
        lines.append(f"- `{path.as_posix()}` rows=`{len(frame)}`")
    out_md = paths.date_dir / f"bonk_v10_dynamic_quality_summary_{paths.run_tag}.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


def main() -> None:
    args = parse_args()
    paths = Paths(data_root=args.data_root, date_dir=args.date_dir, run_tag=args.run_tag)
    replay_full_summary = read_csv_if_exists(paths.replay_full_summary)
    book_hourly = summarize_book_hourly(paths, args.chunksize)
    frames = {
        "book_hourly": book_hourly,
        "book_daily": summarize_book_daily(book_hourly, replay_full_summary),
        "potential_hourly": summarize_potential_hourly(paths, args.chunksize),
        "filter_hourly": summarize_filter_hourly(paths, args.chunksize),
        "coverage": summarize_coverage(paths),
        "artifact_status": artifact_status_rows(paths),
    }
    outputs = write_outputs(paths, frames)
    summary_md = write_markdown(paths, outputs, frames)
    for key, path in {**outputs, "summary_md": summary_md}.items():
        print(f"{key}={path.as_posix()} rows={len(frames.get(key, [])) if key in frames else ''}")


if __name__ == "__main__":
    main()
