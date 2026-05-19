#!/usr/bin/env python
"""Chunked BONK V10 dynamic orderbook analysis.

Research-only diagnostics. This script reads existing V10 replay/downstream
artifacts and writes compact summary tables for a dynamic orderbook report.
It does not download raw data, replay incremental books, or emit trading
recommendations.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    run_tag: str

    @property
    def replay_manifest(self) -> Path:
        return self.date_dir / f"bonk_v10_replay_state_manifest_{self.run_tag}.csv"

    @property
    def replay_full_summary(self) -> Path:
        return self.date_dir / f"bonk_v10_incremental_replay_full_summary_{self.run_tag}.csv"

    @property
    def book_hourly(self) -> Path:
        return self.date_dir / f"bonk_v10_dynamic_quality_book_hourly_{self.run_tag}.csv"

    @property
    def book_daily(self) -> Path:
        return self.date_dir / f"bonk_v10_dynamic_quality_book_daily_{self.run_tag}.csv"

    @property
    def coverage(self) -> Path:
        return self.date_dir / f"bonk_v10_dynamic_quality_coverage_{self.run_tag}.csv"

    @property
    def potential_state(self) -> Path:
        return self.date_dir / f"bonk_v10_potential_state_{self.run_tag}.csv"

    @property
    def filter_state(self) -> Path:
        return self.date_dir / f"bonk_v10_filter_state_{self.run_tag}.csv"

    @property
    def path_trades(self) -> Path:
        return self.date_dir / f"bonk_v10_long_short_episode_backtest_{self.run_tag}_trades.csv"

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

    def out(self, stem: str, suffix: str = "csv") -> Path:
        return self.date_dir / f"bonk_v10_dynamic_orderbook_analysis_{stem}_{self.run_tag}.{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize BONK V10 dynamic orderbook state.")
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--run-tag", default="20260514_bonk_v10_stage1_pilot")
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def read_csv_if_exists(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def csv_header(path: Path) -> list[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def present_usecols(path: Path, usecols: list[str]) -> list[str]:
    header = set(csv_header(path))
    return [col for col in usecols if col in header]


def to_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def add_hour_columns(frame: pd.DataFrame, timestamp_col: str = "local_timestamp") -> pd.DataFrame:
    frame = frame.copy()
    numeric = pd.to_numeric(frame[timestamp_col], errors="coerce")
    hour = pd.to_datetime(numeric, unit="us", utc=True, errors="coerce").dt.floor("h")
    frame["hour_utc"] = hour.dt.strftime("%Y-%m-%dT%H:00:00Z")
    if "date" not in frame.columns:
        frame["date"] = hour.dt.strftime("%Y-%m-%d")
    else:
        frame["date"] = frame["date"].astype(str)
    return frame


def finalize_mean_stats(frame: pd.DataFrame, metric_cols: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in metric_cols:
        sum_col = f"{col}_sum"
        count_col = f"{col}_count"
        sq_col = f"{col}_sq_sum"
        if sum_col not in out.columns or count_col not in out.columns:
            continue
        denom = out[count_col].replace(0, np.nan)
        out[f"{col}_mean"] = out[sum_col] / denom
        if sq_col in out.columns:
            variance = (out[sq_col] / denom) - out[f"{col}_mean"].pow(2)
            out[f"{col}_std"] = np.sqrt(variance.clip(lower=0))
    return out


def corr_from_sums(frame: pd.DataFrame, prefix: str) -> pd.Series:
    n = frame[f"{prefix}_n"].replace(0, np.nan)
    numerator = frame[f"{prefix}_xy_sum"] - frame[f"{prefix}_x_sum"] * frame[f"{prefix}_y_sum"] / n
    x_var = frame[f"{prefix}_x2_sum"] - frame[f"{prefix}_x_sum"].pow(2) / n
    y_var = frame[f"{prefix}_y2_sum"] - frame[f"{prefix}_y_sum"].pow(2) / n
    denom = np.sqrt(x_var.clip(lower=0) * y_var.clip(lower=0))
    return numerator / denom.replace(0, np.nan)


def weighted_group_mean(frame: pd.DataFrame, keys: list[str], weight_col: str, value_cols: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    for col in [weight_col, *value_cols]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    for col in value_cols:
        work[f"{col}_weighted"] = work[col] * work[weight_col]
    agg = work.groupby(keys, dropna=False).agg(
        rows=(weight_col, "sum"),
        **{f"{col}_weighted": (f"{col}_weighted", "sum") for col in value_cols},
    )
    out = agg.reset_index()
    for col in value_cols:
        out[col] = out[f"{col}_weighted"] / out["rows"].replace(0, np.nan)
        out = out.drop(columns=[f"{col}_weighted"])
    return out


def summarize_potential_state(paths: Paths, chunksize: int) -> pd.DataFrame:
    usecols = [
        "date",
        "symbol",
        "local_timestamp",
        "spread_bps",
        "microprice_bps",
        "microprice_impulse_bps",
        "bid_depth_5",
        "ask_depth_5",
        "bid_depth_25",
        "ask_depth_25",
        "imbalance_25",
        "queue_depth_pressure",
        "cancellation_withdrawal_energy",
        "replenish_relaxation",
        "trade_flow_imbalance",
        "net_potential",
        "potential_gradient",
        "potential_curvature",
        "energy_release",
        "fill_realism_score",
    ]
    usecols = present_usecols(paths.potential_state, usecols)
    metric_cols = [
        col
        for col in usecols
        if col not in {"date", "symbol", "local_timestamp"}
    ]
    keys = ["symbol", "date", "hour_utc"]
    partials: list[pd.DataFrame] = []
    for chunk in pd.read_csv(paths.potential_state, usecols=usecols, chunksize=chunksize):
        chunk = add_hour_columns(chunk)
        chunk = to_numeric(chunk, metric_cols)
        for col in metric_cols:
            chunk[f"{col}_sq"] = chunk[col].pow(2)
        chunk["spread_tight"] = chunk["spread_bps"].le(2.0).astype(float)
        chunk["spread_wide"] = chunk["spread_bps"].gt(5.0).astype(float)
        chunk["imbalance_abs_high"] = chunk["imbalance_25"].abs().ge(0.35).astype(float)
        chunk["queue_pressure_positive"] = chunk["queue_depth_pressure"].gt(0).astype(float)
        chunk["energy_release_positive"] = chunk["energy_release"].gt(0).astype(float)
        chunk["potential_positive"] = chunk["net_potential"].gt(0).astype(float)
        align_obs = chunk["trade_flow_imbalance"].ne(0) & chunk["net_potential"].ne(0)
        align_match = np.sign(chunk["trade_flow_imbalance"]) == np.sign(chunk["net_potential"])
        chunk["trade_flow_alignment_obs"] = align_obs.astype(float)
        chunk["trade_flow_alignment_match"] = (align_obs & align_match).astype(float)

        valid = chunk[["net_potential", "trade_flow_imbalance"]].notna().all(axis=1)
        chunk["flow_potential_x"] = chunk["net_potential"].where(valid)
        chunk["flow_potential_y"] = chunk["trade_flow_imbalance"].where(valid)
        chunk["flow_potential_xy"] = chunk["flow_potential_x"] * chunk["flow_potential_y"]
        chunk["flow_potential_x2"] = chunk["flow_potential_x"].pow(2)
        chunk["flow_potential_y2"] = chunk["flow_potential_y"].pow(2)

        valid_micro = chunk[["net_potential", "microprice_impulse_bps"]].notna().all(axis=1)
        chunk["micro_potential_x"] = chunk["net_potential"].where(valid_micro)
        chunk["micro_potential_y"] = chunk["microprice_impulse_bps"].where(valid_micro)
        chunk["micro_potential_xy"] = chunk["micro_potential_x"] * chunk["micro_potential_y"]
        chunk["micro_potential_x2"] = chunk["micro_potential_x"].pow(2)
        chunk["micro_potential_y2"] = chunk["micro_potential_y"].pow(2)

        agg_spec = {"potential_rows": ("symbol", "size")}
        for col in metric_cols:
            agg_spec[f"{col}_sum"] = (col, "sum")
            agg_spec[f"{col}_count"] = (col, "count")
            agg_spec[f"{col}_sq_sum"] = (f"{col}_sq", "sum")
        for col in [
            "spread_tight",
            "spread_wide",
            "imbalance_abs_high",
            "queue_pressure_positive",
            "energy_release_positive",
            "potential_positive",
            "trade_flow_alignment_obs",
            "trade_flow_alignment_match",
        ]:
            agg_spec[f"{col}_sum"] = (col, "sum")
        for prefix in ["flow_potential", "micro_potential"]:
            agg_spec[f"{prefix}_n"] = (f"{prefix}_x", "count")
            agg_spec[f"{prefix}_x_sum"] = (f"{prefix}_x", "sum")
            agg_spec[f"{prefix}_y_sum"] = (f"{prefix}_y", "sum")
            agg_spec[f"{prefix}_xy_sum"] = (f"{prefix}_xy", "sum")
            agg_spec[f"{prefix}_x2_sum"] = (f"{prefix}_x2", "sum")
            agg_spec[f"{prefix}_y2_sum"] = (f"{prefix}_y2", "sum")
        partials.append(chunk.groupby(keys, dropna=False).agg(**agg_spec).reset_index())

    if not partials:
        return pd.DataFrame()
    sum_cols = [col for col in partials[0].columns if col not in keys]
    out = pd.concat(partials, ignore_index=True).groupby(keys, dropna=False)[sum_cols].sum().reset_index()
    out = finalize_mean_stats(out, metric_cols)
    for col in [
        "spread_tight",
        "spread_wide",
        "imbalance_abs_high",
        "queue_pressure_positive",
        "energy_release_positive",
        "potential_positive",
    ]:
        out[f"{col}_rate"] = out[f"{col}_sum"] / out["potential_rows"].replace(0, np.nan)
    out["trade_flow_alignment_rate"] = (
        out["trade_flow_alignment_match_sum"]
        / out["trade_flow_alignment_obs_sum"].replace(0, np.nan)
    )
    out["flow_potential_corr"] = corr_from_sums(out, "flow_potential")
    out["micro_potential_corr"] = corr_from_sums(out, "micro_potential")
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    keep = [
        "run_tag",
        "symbol",
        "date",
        "hour_utc",
        "potential_rows",
        "spread_bps_mean",
        "spread_bps_std",
        "spread_tight_rate",
        "spread_wide_rate",
        "bid_depth_5_mean",
        "ask_depth_5_mean",
        "bid_depth_25_mean",
        "ask_depth_25_mean",
        "imbalance_25_mean",
        "imbalance_25_std",
        "imbalance_abs_high_rate",
        "queue_depth_pressure_mean",
        "cancellation_withdrawal_energy_mean",
        "replenish_relaxation_mean",
        "trade_flow_imbalance_mean",
        "net_potential_mean",
        "net_potential_std",
        "energy_release_mean",
        "fill_realism_score_mean",
        "microprice_bps_mean",
        "microprice_impulse_bps_mean",
        "microprice_impulse_bps_std",
        "queue_pressure_positive_rate",
        "energy_release_positive_rate",
        "potential_positive_rate",
        "trade_flow_alignment_rate",
        "flow_potential_corr",
        "micro_potential_corr",
        "guardrail",
    ]
    keep = [col for col in keep if col in out.columns]
    return out[keep].sort_values(["symbol", "date", "hour_utc"])


def summarize_filter_state(paths: Paths, chunksize: int) -> pd.DataFrame:
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
    usecols = present_usecols(paths.filter_state, usecols)
    keys = ["symbol", "date", "hour_utc", "fold"]
    partials: list[pd.DataFrame] = []
    for chunk in pd.read_csv(paths.filter_state, usecols=usecols, chunksize=chunksize):
        chunk = add_hour_columns(chunk)
        chunk["net_high"] = chunk["net_bucket_train_fit"].eq("high").astype(float)
        chunk["net_low"] = chunk["net_bucket_train_fit"].eq("low").astype(float)
        chunk["energy_high"] = chunk["energy_bucket_train_fit"].eq("high").astype(float)
        chunk["fill_low"] = chunk["fill_bucket_train_fit"].eq("low").astype(float)
        chunk["fill_high"] = chunk["fill_bucket_train_fit"].eq("high").astype(float)
        chunk["flow_high_abs"] = chunk["flow_bucket_train_fit"].eq("high_abs").astype(float)
        chunk["spread_wide"] = chunk["spread_bucket_train_fit"].eq("wide").astype(float)
        agg_spec = {"filter_rows": ("symbol", "size")}
        for col in [
            "net_high",
            "net_low",
            "energy_high",
            "fill_low",
            "fill_high",
            "flow_high_abs",
            "spread_wide",
        ]:
            agg_spec[f"{col}_sum"] = (col, "sum")
        partials.append(chunk.groupby(keys, dropna=False).agg(**agg_spec).reset_index())
    if not partials:
        return pd.DataFrame()
    sum_cols = [col for col in partials[0].columns if col not in keys]
    out = pd.concat(partials, ignore_index=True).groupby(keys, dropna=False)[sum_cols].sum().reset_index()
    for col in [
        "net_high",
        "net_low",
        "energy_high",
        "fill_low",
        "fill_high",
        "flow_high_abs",
        "spread_wide",
    ]:
        out[f"{col}_rate"] = out[f"{col}_sum"] / out["filter_rows"].replace(0, np.nan)
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    keep = [
        "run_tag",
        "symbol",
        "date",
        "hour_utc",
        "fold",
        "filter_rows",
        "net_high_rate",
        "net_low_rate",
        "energy_high_rate",
        "fill_low_rate",
        "fill_high_rate",
        "flow_high_abs_rate",
        "spread_wide_rate",
        "guardrail",
    ]
    return out[keep].sort_values(["symbol", "date", "hour_utc", "fold"])


def summarize_path_trades(paths: Paths, chunksize: int) -> pd.DataFrame:
    usecols = [
        "fold",
        "date",
        "symbol",
        "anchor_type",
        "side",
        "execution_model",
        "entry_local_timestamp",
        "exit_reason",
        "gross_bps",
        "cost_bps",
        "queue_penalty_bps",
        "fill_realism_score",
        "net_bps",
        "pnl_quote",
    ]
    usecols = present_usecols(paths.path_trades, usecols)
    keys = ["symbol", "date", "hour_utc", "anchor_type", "side", "execution_model"]
    metric_cols = ["gross_bps", "cost_bps", "queue_penalty_bps", "fill_realism_score", "net_bps", "pnl_quote"]
    partials: list[pd.DataFrame] = []
    exit_partials: list[pd.DataFrame] = []
    for chunk in pd.read_csv(paths.path_trades, usecols=usecols, chunksize=chunksize):
        chunk = chunk.rename(columns={"entry_local_timestamp": "local_timestamp"})
        chunk = add_hour_columns(chunk)
        chunk = to_numeric(chunk, metric_cols)
        chunk["wins"] = chunk["net_bps"].gt(0).astype(float)
        agg_spec = {"path_trades": ("symbol", "size"), "wins_sum": ("wins", "sum")}
        for col in metric_cols:
            agg_spec[f"{col}_sum"] = (col, "sum")
            agg_spec[f"{col}_count"] = (col, "count")
        partials.append(chunk.groupby(keys, dropna=False).agg(**agg_spec).reset_index())
        exit_partials.append(
            chunk.groupby([*keys, "exit_reason"], dropna=False)
            .size()
            .rename("exit_reason_count")
            .reset_index()
        )
    if not partials:
        return pd.DataFrame()
    sum_cols = [col for col in partials[0].columns if col not in keys]
    out = pd.concat(partials, ignore_index=True).groupby(keys, dropna=False)[sum_cols].sum().reset_index()
    for col in metric_cols:
        out[f"{col}_mean"] = out[f"{col}_sum"] / out[f"{col}_count"].replace(0, np.nan)
    out["win_rate"] = out["wins_sum"] / out["path_trades"].replace(0, np.nan)
    if exit_partials:
        exits = pd.concat(exit_partials, ignore_index=True)
        exits = exits.groupby([*keys, "exit_reason"], dropna=False)["exit_reason_count"].sum().reset_index()
        total = exits.groupby(keys, dropna=False)["exit_reason_count"].transform("sum")
        exits["exit_reason_rate"] = exits["exit_reason_count"] / total.replace(0, np.nan)
        dominant = (
            exits.sort_values(["exit_reason_rate", "exit_reason_count"], ascending=[False, False])
            .groupby(keys, dropna=False)
            .head(1)
            .rename(columns={"exit_reason": "dominant_exit_reason", "exit_reason_rate": "dominant_exit_reason_rate"})
        )
        out = out.merge(dominant[[*keys, "dominant_exit_reason", "dominant_exit_reason_rate"]], on=keys, how="left")
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    keep = [
        "run_tag",
        "symbol",
        "date",
        "hour_utc",
        "anchor_type",
        "side",
        "execution_model",
        "path_trades",
        "gross_bps_mean",
        "cost_bps_mean",
        "queue_penalty_bps_mean",
        "fill_realism_score_mean",
        "net_bps_mean",
        "pnl_quote_sum",
        "pnl_quote_mean",
        "win_rate",
        "dominant_exit_reason",
        "dominant_exit_reason_rate",
        "guardrail",
    ]
    keep = [col for col in keep if col in out.columns]
    return out[keep].sort_values(["symbol", "date", "hour_utc", "anchor_type", "side", "execution_model"])


def build_quality_tables(paths: Paths, potential_hourly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    hourly = read_csv_if_exists(paths.book_hourly)
    daily = read_csv_if_exists(paths.book_daily)
    coverage = read_csv_if_exists(paths.coverage)
    if hourly.empty:
        return pd.DataFrame(), pd.DataFrame()
    numeric_cols = [
        "replay_rows",
        "median_spread_bps",
        "crossed_level_removals",
        "top_of_book_coverage",
        "bid_depth_5_mean",
        "ask_depth_5_mean",
        "bid_depth_25_mean",
        "ask_depth_25_mean",
        "avg_bid_levels",
        "avg_ask_levels",
    ]
    hourly = to_numeric(hourly, numeric_cols)
    hourly["depth_5_total_mean"] = hourly["bid_depth_5_mean"] + hourly["ask_depth_5_mean"]
    hourly["depth_25_total_mean"] = hourly["bid_depth_25_mean"] + hourly["ask_depth_25_mean"]
    hourly["crossed_cleanup_per_10k"] = (
        hourly["crossed_level_removals"] / hourly["replay_rows"].replace(0, np.nan) * 10_000.0
    )
    if not potential_hourly.empty:
        keep = [
            "symbol",
            "date",
            "hour_utc",
            "imbalance_abs_high_rate",
            "queue_depth_pressure_mean",
            "trade_flow_alignment_rate",
            "flow_potential_corr",
        ]
        hourly = hourly.merge(potential_hourly[[col for col in keep if col in potential_hourly.columns]], on=["symbol", "date", "hour_utc"], how="left")
    hourly["quality_tier"] = np.select(
        [
            hourly["top_of_book_coverage"].ge(0.995)
            & hourly["replay_rows"].ge(500)
            & hourly["median_spread_bps"].le(5.0)
            & hourly["crossed_cleanup_per_10k"].le(200.0),
            hourly["top_of_book_coverage"].ge(0.98)
            & hourly["replay_rows"].ge(100)
            & hourly["median_spread_bps"].le(10.0),
        ],
        ["high_trust", "usable_watch"],
        default="fragile",
    )
    hourly["guardrail"] = GUARDRAIL

    if not daily.empty:
        daily = to_numeric(
            daily,
            [
                "replay_rows",
                "median_spread_bps",
                "crossed_level_removals",
                "top_of_book_coverage",
                "avg_bid_levels",
                "avg_ask_levels",
            ],
        )
        symbol_total = daily.groupby("symbol")["replay_rows"].transform("sum")
        daily["symbol_replay_share"] = daily["replay_rows"] / symbol_total.replace(0, np.nan)
        daily["crossed_cleanup_per_10k"] = (
            daily["crossed_level_removals"] / daily["replay_rows"].replace(0, np.nan) * 10_000.0
        )
        if not coverage.empty:
            daily = daily.merge(
                coverage[
                    [
                        col
                        for col in [
                            "date",
                            "symbol",
                            "replay_status",
                            "multilevel_schema_ok",
                            "part_files",
                            "actual_part_files",
                        ]
                        if col in coverage.columns
                    ]
                ],
                on=["date", "symbol"],
                how="left",
            )
        daily["guardrail"] = GUARDRAIL
    return hourly.sort_values(["symbol", "date", "hour_utc"]), daily.sort_values(["symbol", "date"])


def build_state_summary(paths: Paths, potential_hourly: pd.DataFrame, filter_hourly: pd.DataFrame) -> pd.DataFrame:
    if potential_hourly.empty:
        return pd.DataFrame()
    p_value_cols = [
        "spread_tight_rate",
        "spread_wide_rate",
        "imbalance_abs_high_rate",
        "queue_depth_pressure_mean",
        "cancellation_withdrawal_energy_mean",
        "replenish_relaxation_mean",
        "trade_flow_imbalance_mean",
        "net_potential_mean",
        "energy_release_mean",
        "fill_realism_score_mean",
        "microprice_impulse_bps_mean",
        "trade_flow_alignment_rate",
        "flow_potential_corr",
        "micro_potential_corr",
    ]
    summary = weighted_group_mean(
        potential_hourly,
        ["symbol"],
        "potential_rows",
        [col for col in p_value_cols if col in potential_hourly.columns],
    ).rename(columns={"rows": "potential_rows"})
    if not filter_hourly.empty:
        f_value_cols = [
            "net_high_rate",
            "net_low_rate",
            "energy_high_rate",
            "fill_low_rate",
            "fill_high_rate",
            "flow_high_abs_rate",
            "spread_wide_rate",
        ]
        f_summary = weighted_group_mean(
            filter_hourly,
            ["symbol"],
            "filter_rows",
            [col for col in f_value_cols if col in filter_hourly.columns],
        ).rename(columns={"rows": "filter_rows"})
        rename = {col: f"filter_{col}" for col in f_value_cols if col in f_summary.columns}
        f_summary = f_summary.rename(columns=rename)
        summary = summary.merge(f_summary, on="symbol", how="left")
    summary.insert(0, "run_tag", paths.run_tag)
    summary["guardrail"] = GUARDRAIL
    return summary.sort_values(["symbol"])


def build_spearman_horizon(paths: Paths) -> pd.DataFrame:
    spearman = read_csv_if_exists(paths.spearman)
    decay = read_csv_if_exists(paths.horizon_decay)
    if spearman.empty:
        return pd.DataFrame()
    spearman = to_numeric(spearman, ["horizon_seconds", "spearman", "abs_spearman", "n"])
    spearman["positive_sign"] = spearman["spearman"].gt(0).astype(float)
    out = (
        spearman.groupby(["symbol", "feature_name", "horizon_seconds"], dropna=False)
        .agg(
            spearman_rows=("spearman", "size"),
            mean_spearman=("spearman", "mean"),
            mean_abs_spearman=("abs_spearman", "mean"),
            max_abs_spearman=("abs_spearman", "max"),
            total_n=("n", "sum"),
            positive_sign_rate=("positive_sign", "mean"),
        )
        .reset_index()
    )
    if not decay.empty:
        decay = to_numeric(decay, ["horizon_seconds", "abs_spearman", "n", "decay_rank"])
        out = out.merge(
            decay.rename(
                columns={
                    "abs_spearman": "decay_abs_spearman",
                    "n": "decay_n",
                    "decay_rank": "decay_rank",
                }
            )[["symbol", "feature_name", "horizon_seconds", "decay_abs_spearman", "decay_n", "decay_rank"]],
            on=["symbol", "feature_name", "horizon_seconds"],
            how="left",
        )
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    return out.sort_values(["symbol", "feature_name", "horizon_seconds"])


def build_negative_control_summary(paths: Paths) -> pd.DataFrame:
    controls = read_csv_if_exists(paths.negative_controls)
    if controls.empty:
        return pd.DataFrame()
    controls = to_numeric(controls, ["base_trade_count", "base_total_pnl_quote", "control_total_pnl_quote"])
    controls["control_minus_base_pnl_quote"] = controls["control_total_pnl_quote"] - controls["base_total_pnl_quote"]
    controls["control_abs_ge_base_abs"] = (
        controls["control_total_pnl_quote"].abs().ge(controls["base_total_pnl_quote"].abs())
    ).astype(float)
    controls["same_sign_as_base"] = (
        np.sign(controls["control_total_pnl_quote"]) == np.sign(controls["base_total_pnl_quote"])
    ).astype(float)
    keys = ["symbol", "anchor_type", "side", "execution_model", "control_type"]
    out = (
        controls.groupby(keys, dropna=False)
        .agg(
            rows=("control_type", "size"),
            base_trade_count_mean=("base_trade_count", "mean"),
            base_total_pnl_quote_mean=("base_total_pnl_quote", "mean"),
            control_total_pnl_quote_mean=("control_total_pnl_quote", "mean"),
            control_minus_base_pnl_quote_mean=("control_minus_base_pnl_quote", "mean"),
            control_abs_ge_base_abs_rate=("control_abs_ge_base_abs", "mean"),
            same_sign_as_base_rate=("same_sign_as_base", "mean"),
        )
        .reset_index()
    )
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    return out.sort_values(["symbol", "anchor_type", "side", "execution_model", "control_type"])


def build_path_summary(paths: Paths, path_hourly: pd.DataFrame) -> pd.DataFrame:
    summary = read_csv_if_exists(paths.path_summary)
    if summary.empty:
        return pd.DataFrame()
    summary = to_numeric(
        summary,
        [
            "trade_count",
            "total_pnl_quote",
            "avg_net_bps",
            "median_net_bps",
            "win_rate",
            "profit_factor",
            "trades_per_day",
            "max_drawdown_quote",
        ],
    )
    keys = ["symbol", "anchor_type", "side", "execution_model"]
    out = (
        summary.groupby(keys, dropna=False)
        .agg(
            summary_rows=("summary_scope", "size"),
            trade_count_sum=("trade_count", "sum"),
            avg_net_bps_mean=("avg_net_bps", "mean"),
            median_net_bps_mean=("median_net_bps", "mean"),
            win_rate_mean=("win_rate", "mean"),
            profit_factor_mean=("profit_factor", "mean"),
            trades_per_day_mean=("trades_per_day", "mean"),
            max_drawdown_quote_max=("max_drawdown_quote", "max"),
        )
        .reset_index()
    )
    if not path_hourly.empty:
        h = (
            path_hourly.groupby(keys, dropna=False)
            .agg(
                path_hours=("hour_utc", "nunique"),
                path_trades=("path_trades", "sum"),
                net_bps_mean_hourly=("net_bps_mean", "mean"),
                cost_bps_mean_hourly=("cost_bps_mean", "mean"),
                queue_penalty_bps_mean_hourly=("queue_penalty_bps_mean", "mean"),
                fill_realism_score_mean_hourly=("fill_realism_score_mean", "mean"),
                win_rate_hourly_mean=("win_rate", "mean"),
            )
            .reset_index()
        )
        out = out.merge(h, on=keys, how="left")
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    return out.sort_values(keys)


def build_blockers(
    paths: Paths,
    quality_hourly: pd.DataFrame,
    quality_daily: pd.DataFrame,
    state_summary: pd.DataFrame,
    path_summary: pd.DataFrame,
    negative_summary: pd.DataFrame,
    spearman_horizon: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    manifest = read_csv_if_exists(paths.replay_manifest)
    completed = 0 if manifest.empty or "status" not in manifest.columns else int(manifest["status"].eq("completed").sum())
    total = len(manifest)
    if total == 0 or completed < total:
        rows.append(
            {
                "blocker": "replay_coverage",
                "severity": "critical",
                "evidence": f"completed={completed} total={total}",
                "next_action": "complete fixed-window replay before model work",
            }
        )
    if not quality_hourly.empty:
        fragile = quality_hourly["quality_tier"].eq("fragile").mean()
        if fragile > 0.05:
            rows.append(
                {
                    "blocker": "hourly_quality_fragility",
                    "severity": "medium",
                    "evidence": f"fragile_hour_share={fragile:.3f}",
                    "next_action": "inspect low coverage or high cleanup hours before using them in folds",
                }
            )
    if not quality_daily.empty and "symbol_replay_share" in quality_daily.columns:
        max_share = pd.to_numeric(quality_daily["symbol_replay_share"], errors="coerce").max()
        if pd.notna(max_share) and max_share > 0.20:
            rows.append(
                {
                    "blocker": "single_day_dominance",
                    "severity": "medium",
                    "evidence": f"max_symbol_day_replay_share={max_share:.3f}",
                    "next_action": "keep day-aware validation and avoid treating all rows as independent",
                }
            )
    if not state_summary.empty and "trade_flow_alignment_rate" in state_summary.columns:
        min_align = pd.to_numeric(state_summary["trade_flow_alignment_rate"], errors="coerce").min()
        if pd.isna(min_align) or min_align < 0.52:
            rows.append(
                {
                    "blocker": "weak_trade_flow_alignment",
                    "severity": "medium",
                    "evidence": f"min_trade_flow_alignment_rate={min_align:.3f}",
                    "next_action": "revisit potential sign conventions and trade-flow alignment before modeling",
                }
            )
    if not spearman_horizon.empty:
        short = spearman_horizon[pd.to_numeric(spearman_horizon["horizon_seconds"], errors="coerce").eq(30)]
        max_short = pd.to_numeric(short["mean_abs_spearman"], errors="coerce").max()
        if pd.isna(max_short) or max_short < 0.05:
            rows.append(
                {
                    "blocker": "weak_short_horizon_rank_signal",
                    "severity": "high",
                    "evidence": f"max_30s_mean_abs_spearman={max_short:.4f}",
                    "next_action": "do not promote state definitions until short-horizon rank signal is stronger",
                }
            )
    if not path_summary.empty:
        maker = path_summary[path_summary["execution_model"].eq("maker_light")]
        maker_net = pd.to_numeric(maker["avg_net_bps_mean"], errors="coerce").mean()
        if pd.notna(maker_net) and maker_net <= 0:
            rows.append(
                {
                    "blocker": "after_cost_path_fragility",
                    "severity": "high",
                    "evidence": f"maker_light_avg_net_bps_mean={maker_net:.4f}",
                    "next_action": "fix state selectivity/path construction before adding more model complexity",
                }
            )
    if not negative_summary.empty:
        worse = pd.to_numeric(negative_summary["control_abs_ge_base_abs_rate"], errors="coerce").mean()
        if pd.notna(worse) and worse > 0.40:
            rows.append(
                {
                    "blocker": "negative_controls_not_cleanly_separated",
                    "severity": "high",
                    "evidence": f"control_abs_ge_base_abs_rate_mean={worse:.3f}",
                    "next_action": "treat path results as unstable until controls are clearly worse or structurally separated",
                }
            )
    rows.append(
        {
            "blocker": "research_guardrail",
            "severity": "info",
            "evidence": "diagnostics only; no trading advice, no execution recommendation, no alpha claim",
            "next_action": "use outputs only for research triage and next experiment design",
        }
    )
    out = pd.DataFrame(rows)
    out.insert(0, "run_tag", paths.run_tag)
    out["guardrail"] = GUARDRAIL
    return out


def write_markdown_summary(
    paths: Paths,
    outputs: dict[str, Path],
    quality_hourly: pd.DataFrame,
    quality_daily: pd.DataFrame,
    state_summary: pd.DataFrame,
    path_summary: pd.DataFrame,
    negative_summary: pd.DataFrame,
    spearman_horizon: pd.DataFrame,
    blockers: pd.DataFrame,
) -> None:
    manifest = read_csv_if_exists(paths.replay_manifest)
    completed = 0 if manifest.empty or "status" not in manifest.columns else int(manifest["status"].eq("completed").sum())
    total = len(manifest)
    quality_counts = (
        quality_hourly["quality_tier"].value_counts().to_dict() if "quality_tier" in quality_hourly.columns else {}
    )
    max_day_share = (
        pd.to_numeric(quality_daily.get("symbol_replay_share", pd.Series(dtype=float)), errors="coerce").max()
        if not quality_daily.empty
        else np.nan
    )
    top_spearman = (
        spearman_horizon.sort_values("mean_abs_spearman", ascending=False).head(8)
        if not spearman_horizon.empty
        else pd.DataFrame()
    )
    maker_net = np.nan
    if not path_summary.empty:
        maker = path_summary[path_summary["execution_model"].eq("maker_light")]
        maker_net = pd.to_numeric(maker["avg_net_bps_mean"], errors="coerce").mean()
    md = [
        "# BONK V10 Dynamic Orderbook Analysis Summary",
        "",
        f"Run tag: `{paths.run_tag}`",
        "",
        "Research-only diagnostics. No trading advice, execution recommendation, or alpha claim.",
        "",
        "## Coverage",
        "",
        f"- Replay state manifest completed: `{completed}/{total}`.",
        f"- Hourly quality tiers: `{quality_counts}`.",
        f"- Max same-symbol single-day replay share: `{max_day_share:.3f}`.",
        "",
        "## Stable Microstructure Candidates",
        "",
    ]
    if top_spearman.empty:
        md.append("- Spearman diagnostics unavailable.")
    else:
        for row in top_spearman.itertuples(index=False):
            md.append(
                f"- `{row.symbol}` `{row.feature_name}` horizon `{int(row.horizon_seconds)}s`: "
                f"mean_abs_spearman=`{row.mean_abs_spearman:.4f}`, sign_positive_rate=`{row.positive_sign_rate:.2f}`."
            )
    md.extend(["", "## Path/Control Fragility", ""])
    md.append(f"- Maker-light mean after-cost net bps across path summaries: `{maker_net:.4f}`.")
    if not negative_summary.empty:
        worse = pd.to_numeric(negative_summary["control_abs_ge_base_abs_rate"], errors="coerce").mean()
        md.append(f"- Negative-control abs >= base abs rate mean: `{worse:.3f}`.")
    md.extend(["", "## Blockers", ""])
    for row in blockers.itertuples(index=False):
        md.append(f"- `{row.blocker}` `{row.severity}`: {row.evidence}; next={row.next_action}.")
    md.extend(["", "## Output Tables", ""])
    for name, path in outputs.items():
        rows = ""
        if path.exists() and path.suffix == ".csv":
            try:
                rows = f" rows=`{sum(1 for _ in path.open('r', encoding='utf-8')) - 1}`"
            except OSError:
                rows = ""
        md.append(f"- `{path.as_posix()}`{rows}")
    md.append("")
    outputs["summary_md"].write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(date_dir=args.date_dir, run_tag=args.run_tag)

    potential_hourly = summarize_potential_state(paths, args.chunksize)
    filter_hourly = summarize_filter_state(paths, args.chunksize)
    path_hourly = summarize_path_trades(paths, args.chunksize)
    quality_hourly, quality_daily = build_quality_tables(paths, potential_hourly)
    state_summary = build_state_summary(paths, potential_hourly, filter_hourly)
    spearman_horizon = build_spearman_horizon(paths)
    negative_summary = build_negative_control_summary(paths)
    path_summary = build_path_summary(paths, path_hourly)
    blockers = build_blockers(
        paths,
        quality_hourly,
        quality_daily,
        state_summary,
        path_summary,
        negative_summary,
        spearman_horizon,
    )

    outputs = {
        "quality_hourly": paths.out("quality_hourly"),
        "quality_daily": paths.out("quality_daily"),
        "state_hourly": paths.out("state_hourly"),
        "state_summary": paths.out("state_summary"),
        "filter_hourly": paths.out("filter_hourly"),
        "path_hourly": paths.out("path_hourly"),
        "path_summary": paths.out("path_summary"),
        "negative_controls": paths.out("negative_controls"),
        "spearman_horizon": paths.out("spearman_horizon"),
        "blockers": paths.out("blockers"),
        "summary_md": paths.out("summary", "md"),
    }
    tables = {
        "quality_hourly": quality_hourly,
        "quality_daily": quality_daily,
        "state_hourly": potential_hourly,
        "state_summary": state_summary,
        "filter_hourly": filter_hourly,
        "path_hourly": path_hourly,
        "path_summary": path_summary,
        "negative_controls": negative_summary,
        "spearman_horizon": spearman_horizon,
        "blockers": blockers,
    }
    for name, table in tables.items():
        table.to_csv(outputs[name], index=False)
    write_markdown_summary(
        paths,
        outputs,
        quality_hourly,
        quality_daily,
        state_summary,
        path_summary,
        negative_summary,
        spearman_horizon,
        blockers,
    )
    for name, path in outputs.items():
        if path.suffix == ".csv":
            rows = sum(1 for _ in path.open("r", encoding="utf-8")) - 1
            print(f"{name}={path.as_posix()} rows={rows}")
        else:
            print(f"{name}={path.as_posix()}")


if __name__ == "__main__":
    main()
