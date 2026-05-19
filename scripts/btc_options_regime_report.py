#!/usr/bin/env python3
"""
Build a BTC/ETH Deribit options regime sample report from local Tardis parquet.

This script intentionally uses the already-extracted 5m options snapshots and
1m index OHLC. It does not download new data and does not depend on
CryoBacktester at runtime.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_RUN_TAG = "20260512_options_regime_v0"
DEFAULT_DATA_ROOT = Path("data/tardis/v1")
DEFAULT_DATE_DIR = Path("date")
DEFAULT_DOC_DIR = Path("docs/markets/btc")
DEFAULT_HORIZON_HOURS = 12
DEFAULT_UNDERLYINGS = "BTC,ETH"


@dataclass(frozen=True)
class OutputPaths:
    regime_parquet: Path
    labels_parquet: Path
    summary_csv: Path
    factor_tests_csv: Path
    spearman_csv: Path
    report_md: Path
    figures_dir: Path


BASE_FACTOR_COLS = [
    "atm_iv",
    "skew_25d",
    "term_slope",
    "trailing_realized_vol_1h_bps",
    "trailing_realized_vol_6h_bps",
    "trailing_realized_vol_12h_bps",
    "compressed_range_6h",
    "quote_coverage",
    "option_spread_median_bps",
]

EXTENDED_FACTOR_COLS = [
    "trailing_realized_vol_12h_ann_pct",
    "iv_richness_12h",
    "iv_rv_ratio_12h",
    "implied_move_12h_bps",
    "vol_premium_gap_12h_bps",
    "term_stress",
    "abs_term_slope",
    "abs_skew_25d",
    "atm_iv_change_1h",
    "skew_25d_change_1h",
    "term_slope_change_1h",
    "iv_richness_change_1h",
    "atm_iv_rank_pct",
    "skew_25d_rank_pct",
    "term_slope_rank_pct",
    "compression_rank_pct",
    "compression_rel_to_rv_6h",
]

FACTOR_COLS = BASE_FACTOR_COLS + EXTENDED_FACTOR_COLS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build BTC/ETH options regime state, 12h path labels, charts, and a Chinese report."
    )
    parser.add_argument("--run-tag", default=DEFAULT_RUN_TAG)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--date-dir", type=Path, default=DEFAULT_DATE_DIR)
    parser.add_argument("--doc-dir", type=Path, default=DEFAULT_DOC_DIR)
    parser.add_argument("--underlyings", default=DEFAULT_UNDERLYINGS)
    parser.add_argument("--horizon-hours", type=int, default=DEFAULT_HORIZON_HOURS)
    parser.add_argument("--barrier-floor-bps", type=float, default=75.0)
    parser.add_argument("--barrier-vol-multiple", type=float, default=0.75)
    parser.add_argument("--vol-expansion-multiple", type=float, default=1.25)
    return parser.parse_args()


def normalized_underlyings(raw: str) -> list[str]:
    values = [value.strip().upper() for value in raw.split(",") if value.strip()]
    if not values:
        raise ValueError("--underlyings cannot be empty")
    return list(dict.fromkeys(values))


def output_paths(data_root: Path, date_dir: Path, doc_dir: Path, run_tag: str) -> OutputPaths:
    return OutputPaths(
        regime_parquet=(
            data_root
            / "derived"
            / "btc_options_regime_state"
            / f"btc_options_regime_state_{run_tag}.parquet"
        ),
        labels_parquet=(
            data_root
            / "derived"
            / "btc_12h_path_labels"
            / f"btc_12h_path_labels_{run_tag}.parquet"
        ),
        summary_csv=date_dir / f"btc_options_regime_summary_{run_tag}.csv",
        factor_tests_csv=date_dir / f"btc_options_regime_factor_tests_{run_tag}.csv",
        spearman_csv=date_dir / f"btc_options_regime_spearman_{run_tag}.csv",
        report_md=doc_dir / "v1-options-regime-report.md",
        figures_dir=doc_dir / "figures",
    )


def read_parquet_glob(root: Path, pattern: str) -> pd.DataFrame:
    paths = sorted(root.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"no parquet files matched {root / pattern}")
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)


def parse_expiry_datetime(expiry: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(expiry, format="%d%b%y", utc=True, errors="coerce")
    return parsed + pd.Timedelta(hours=8)


def choose_by_delta(frame: pd.DataFrame, target_delta: float) -> pd.Series | None:
    if frame.empty:
        return None
    values = frame[np.isfinite(frame["delta"]) & np.isfinite(frame["mark_iv"]) & (frame["mark_iv"] > 0)]
    if values.empty:
        return None
    idx = (values["delta"] - target_delta).abs().idxmin()
    return values.loc[idx]


def choose_atm_iv(frame: pd.DataFrame) -> float:
    call = choose_by_delta(frame[frame["is_call"]], 0.50)
    put = choose_by_delta(frame[~frame["is_call"]], -0.50)
    values = []
    if call is not None:
        values.append(float(call["mark_iv"]))
    if put is not None:
        values.append(float(put["mark_iv"]))
    return float(np.nanmean(values)) if values else np.nan


def build_surface_state(options: pd.DataFrame, underlyings: Iterable[str]) -> pd.DataFrame:
    options = options.copy()
    options["ts"] = pd.to_datetime(options["timestamp_utc"], utc=True)
    options["expiry_dt"] = parse_expiry_datetime(options["expiry"])
    options["dte_hours"] = (options["expiry_dt"] - options["ts"]).dt.total_seconds() / 3600.0
    options = options[
        options["underlying"].isin(list(underlyings))
        & (options["dte_hours"] > 0)
        & np.isfinite(options["mark_iv"])
        & (options["mark_iv"] > 0)
    ].copy()
    if options.empty:
        raise ValueError("no usable option rows after filtering")

    rows: list[dict[str, object]] = []
    group_cols = ["underlying", "ts"]
    for (underlying, ts), group in options.groupby(group_cols, sort=True):
        expiries = sorted(group["expiry_dt"].dropna().unique())
        if not expiries:
            continue
        front_expiry = expiries[0]
        next_expiry = expiries[1] if len(expiries) > 1 else pd.NaT
        front = group[group["expiry_dt"] == front_expiry]
        nxt = group[group["expiry_dt"] == next_expiry] if pd.notna(next_expiry) else group.iloc[0:0]

        call_25d = choose_by_delta(front[front["is_call"]], 0.25)
        put_25d = choose_by_delta(front[~front["is_call"]], -0.25)
        atm_iv = choose_atm_iv(front)
        next_atm_iv = choose_atm_iv(nxt)
        call_25d_iv = float(call_25d["mark_iv"]) if call_25d is not None else np.nan
        put_25d_iv = float(put_25d["mark_iv"]) if put_25d is not None else np.nan

        quoted = front[
            ((front["bid_price"].fillna(0.0) > 0.0) | (front["ask_price"].fillna(0.0) > 0.0))
            & (front["mark_price"].fillna(0.0) > 0.0)
        ]
        spread = (front["ask_price"] - front["bid_price"]).clip(lower=0.0)

        rows.append(
            {
                "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "timestamp_us": int(ts.timestamp() * 1_000_000),
                "underlying": underlying,
                "front_expiry": pd.Timestamp(front_expiry).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "front_dte_hours": float(front["dte_hours"].median()),
                "next_expiry": (
                    pd.Timestamp(next_expiry).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if pd.notna(next_expiry)
                    else ""
                ),
                "next_dte_hours": float(nxt["dte_hours"].median()) if not nxt.empty else np.nan,
                "atm_iv": atm_iv,
                "put_25d_iv": put_25d_iv,
                "call_25d_iv": call_25d_iv,
                "skew_25d": put_25d_iv - call_25d_iv,
                "term_slope": next_atm_iv - atm_iv,
                "option_spread_median": float(spread.median()) if len(spread) else np.nan,
                "option_spread_median_bps": float(spread.median() * 10_000.0) if len(spread) else np.nan,
                "quote_coverage": float(len(quoted) / len(front)) if len(front) else np.nan,
                "front_instruments": int(len(front)),
                "run_tag": "",
            }
        )

    return pd.DataFrame(rows).sort_values(["underlying", "timestamp_us"]).reset_index(drop=True)


def build_index_features(index_ohlc: pd.DataFrame, underlyings: Iterable[str]) -> pd.DataFrame:
    index_ohlc = index_ohlc[index_ohlc["underlying"].isin(list(underlyings))].copy()
    index_ohlc["ts"] = pd.to_datetime(index_ohlc["timestamp_utc"], utc=True)
    index_ohlc = index_ohlc.sort_values(["underlying", "ts"]).reset_index(drop=True)
    pieces: list[pd.DataFrame] = []
    for underlying, group in index_ohlc.groupby("underlying", sort=True):
        group = group.sort_values("ts").copy()
        close = group["close"].astype(float)
        high = group["high"].astype(float)
        low = group["low"].astype(float)
        log_close = np.log(close)
        ret = log_close.diff()
        for minutes in (60, 360, 720):
            group[f"trailing_realized_vol_{minutes // 60}h_bps"] = (
                np.sqrt((ret**2).rolling(minutes, min_periods=max(2, minutes // 3)).sum()) * 10_000.0
            )
        group["compressed_range_6h"] = (
            np.log(high.rolling(360, min_periods=120).max())
            - np.log(low.rolling(360, min_periods=120).min())
        ) * 10_000.0
        group["underlying"] = underlying
        pieces.append(group)
    return pd.concat(pieces, ignore_index=True)


def merge_regime_with_index(surface: pd.DataFrame, index_features: pd.DataFrame, run_tag: str) -> pd.DataFrame:
    idx = index_features[
        [
            "underlying",
            "ts",
            "open",
            "high",
            "low",
            "close",
            "trailing_realized_vol_1h_bps",
            "trailing_realized_vol_6h_bps",
            "trailing_realized_vol_12h_bps",
            "compressed_range_6h",
        ]
    ].copy()
    surface = surface.copy()
    surface["ts"] = pd.to_datetime(surface["timestamp_utc"], utc=True)
    merged = surface.merge(idx, on=["underlying", "ts"], how="left")
    merged["run_tag"] = run_tag
    merged = merged.rename(columns={"close": "index_close"})
    return merged.drop(columns=["ts"]).sort_values(["underlying", "timestamp_us"]).reset_index(drop=True)


def window_bps_to_annual_pct(values: pd.Series, hours: float) -> pd.Series:
    return pd.to_numeric(values, errors="coerce") * math.sqrt(8760.0 / hours) / 100.0


def implied_move_bps(iv_pct: pd.Series, hours: float) -> pd.Series:
    return pd.to_numeric(iv_pct, errors="coerce") * math.sqrt(hours / 8760.0) * 100.0


def safe_div(numer: pd.Series, denom: pd.Series) -> pd.Series:
    numer = pd.to_numeric(numer, errors="coerce")
    denom = pd.to_numeric(denom, errors="coerce")
    out = numer / denom.replace(0.0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


def sample_rank_pct(values: pd.Series) -> pd.Series:
    values = pd.to_numeric(values, errors="coerce")
    if values.dropna().nunique() < 2:
        return pd.Series(np.nan, index=values.index)
    return values.rank(pct=True) * 100.0


def add_extended_regime_factors(regime: pd.DataFrame, horizon_hours: int) -> pd.DataFrame:
    regime = regime.sort_values(["underlying", "timestamp_us"]).copy()
    regime["trailing_realized_vol_1h_ann_pct"] = window_bps_to_annual_pct(
        regime["trailing_realized_vol_1h_bps"], 1.0
    )
    regime["trailing_realized_vol_6h_ann_pct"] = window_bps_to_annual_pct(
        regime["trailing_realized_vol_6h_bps"], 6.0
    )
    regime["trailing_realized_vol_12h_ann_pct"] = window_bps_to_annual_pct(
        regime["trailing_realized_vol_12h_bps"], 12.0
    )
    regime["iv_richness_12h"] = regime["atm_iv"] - regime["trailing_realized_vol_12h_ann_pct"]
    regime["iv_rv_ratio_12h"] = safe_div(regime["atm_iv"], regime["trailing_realized_vol_12h_ann_pct"])
    regime["implied_move_12h_bps"] = implied_move_bps(regime["atm_iv"], float(horizon_hours))
    regime["vol_premium_gap_12h_bps"] = (
        regime["implied_move_12h_bps"] - regime["trailing_realized_vol_12h_bps"]
    )
    regime["term_stress"] = -regime["term_slope"]
    regime["abs_term_slope"] = regime["term_slope"].abs()
    regime["abs_skew_25d"] = regime["skew_25d"].abs()
    regime["compression_rel_to_rv_6h"] = safe_div(
        regime["compressed_range_6h"], regime["trailing_realized_vol_6h_bps"]
    )

    for _, group in regime.groupby("underlying", sort=False):
        idx = group.index
        regime.loc[idx, "atm_iv_change_1h"] = group["atm_iv"].diff(12)
        regime.loc[idx, "skew_25d_change_1h"] = group["skew_25d"].diff(12)
        regime.loc[idx, "term_slope_change_1h"] = group["term_slope"].diff(12)
        regime.loc[idx, "iv_richness_change_1h"] = group["iv_richness_12h"].diff(12)
        regime.loc[idx, "atm_iv_rank_pct"] = sample_rank_pct(group["atm_iv"])
        regime.loc[idx, "skew_25d_rank_pct"] = sample_rank_pct(group["skew_25d"])
        regime.loc[idx, "term_slope_rank_pct"] = sample_rank_pct(group["term_slope"])
        regime.loc[idx, "compression_rank_pct"] = sample_rank_pct(group["compressed_range_6h"])

    return regime.replace([np.inf, -np.inf], np.nan).reset_index(drop=True)


def future_window_arrays(values: np.ndarray, start: int, horizon_minutes: int) -> np.ndarray:
    lo = start + 1
    hi = min(len(values), start + horizon_minutes + 1)
    return values[lo:hi]


def first_hit_outcome(
    close0: float,
    future_high: np.ndarray,
    future_low: np.ndarray,
    barrier_bps: float,
) -> tuple[str, float, float]:
    if not np.isfinite(close0) or close0 <= 0 or len(future_high) == 0 or len(future_low) == 0:
        return "future_missing", np.nan, np.nan
    up_path = np.log(future_high / close0) * 10_000.0
    down_path = np.log(future_low / close0) * 10_000.0
    mfe = float(np.nanmax(up_path)) if len(up_path) else np.nan
    mae = float(np.nanmin(down_path)) if len(down_path) else np.nan
    upper_hits = np.flatnonzero(up_path >= barrier_bps)
    lower_hits = np.flatnonzero(down_path <= -barrier_bps)
    upper_first = int(upper_hits[0]) if len(upper_hits) else None
    lower_first = int(lower_hits[0]) if len(lower_hits) else None
    if upper_first is None and lower_first is None:
        outcome = "none"
    elif upper_first is not None and lower_first is None:
        outcome = "upper_first"
    elif upper_first is None and lower_first is not None:
        outcome = "lower_first"
    elif upper_first == lower_first:
        outcome = "both_or_ambiguous"
    elif upper_first < lower_first:
        outcome = "upper_first"
    else:
        outcome = "lower_first"
    return outcome, mfe, mae


def build_path_labels(
    regime: pd.DataFrame,
    index_features: pd.DataFrame,
    horizon_hours: int,
    barrier_floor_bps: float,
    barrier_vol_multiple: float,
    vol_expansion_multiple: float,
    run_tag: str,
) -> pd.DataFrame:
    horizon_minutes = horizon_hours * 60
    rows: list[dict[str, object]] = []
    regime = regime.copy()
    regime["ts"] = pd.to_datetime(regime["timestamp_utc"], utc=True)
    index_features = index_features.sort_values(["underlying", "ts"])

    for underlying, idx_group in index_features.groupby("underlying", sort=True):
        idx_group = idx_group.sort_values("ts").reset_index(drop=True)
        pos_by_ts = {ts: i for i, ts in enumerate(idx_group["ts"])}
        close = idx_group["close"].astype(float).to_numpy()
        high = idx_group["high"].astype(float).to_numpy()
        low = idx_group["low"].astype(float).to_numpy()
        log_close = np.log(close)
        ret = pd.Series(log_close).diff().to_numpy()
        reg_group = regime[regime["underlying"] == underlying].sort_values("ts")
        for row in reg_group.itertuples(index=False):
            ts = row.ts
            pos = pos_by_ts.get(ts)
            trailing_vol = float(getattr(row, "trailing_realized_vol_12h_bps"))
            barrier_bps = max(
                barrier_floor_bps,
                barrier_vol_multiple * trailing_vol if np.isfinite(trailing_vol) else barrier_floor_bps,
            )
            if pos is None or pos + horizon_minutes >= len(idx_group):
                status = "future_missing"
                outcome = "future_missing"
                future_return = np.nan
                mfe = np.nan
                mae = np.nan
                future_rv = np.nan
                vol_expansion = False
            else:
                close0 = float(close[pos])
                close_h = float(close[pos + horizon_minutes])
                future_return = float(np.log(close_h / close0) * 10_000.0)
                future_high = future_window_arrays(high, pos, horizon_minutes)
                future_low = future_window_arrays(low, pos, horizon_minutes)
                future_ret = future_window_arrays(ret, pos, horizon_minutes)
                outcome, mfe, mae = first_hit_outcome(close0, future_high, future_low, barrier_bps)
                future_rv = float(np.sqrt(np.nansum(future_ret**2)) * 10_000.0)
                vol_expansion = bool(
                    np.isfinite(trailing_vol)
                    and trailing_vol > 0.0
                    and future_rv > trailing_vol * vol_expansion_multiple
                )
                status = "ok"

            rows.append(
                {
                    "timestamp_utc": row.timestamp_utc,
                    "timestamp_us": int(row.timestamp_us),
                    "underlying": underlying,
                    "horizon_hours": int(horizon_hours),
                    "index_close": float(row.index_close) if np.isfinite(row.index_close) else np.nan,
                    "barrier_bps": float(barrier_bps),
                    "future_12h_return_bps": future_return,
                    "mfe_up_bps": mfe,
                    "mae_down_bps": mae,
                    "future_realized_vol_12h_bps": future_rv,
                    "barrier_first_hit": outcome,
                    "vol_expansion": vol_expansion,
                    "label_status": status,
                    "run_tag": run_tag,
                }
            )

    return pd.DataFrame(rows).sort_values(["underlying", "timestamp_us"]).reset_index(drop=True)


def qbucket(series: pd.Series, labels: tuple[str, str, str] = ("low", "mid", "high")) -> pd.Series:
    result = pd.Series("missing", index=series.index, dtype="object")
    valid = series.replace([np.inf, -np.inf], np.nan).dropna()
    if valid.nunique() < 3:
        result.loc[valid.index] = "flat"
        return result
    try:
        bins = pd.qcut(valid, q=3, labels=labels, duplicates="drop")
        result.loc[bins.index] = bins.astype(str)
    except ValueError:
        result.loc[valid.index] = "flat"
    return result


def build_summaries(regime: pd.DataFrame, labels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    joined = regime.merge(
        labels[
            [
                "underlying",
                "timestamp_us",
                "future_12h_return_bps",
                "mfe_up_bps",
                "mae_down_bps",
                "future_realized_vol_12h_bps",
                "barrier_first_hit",
                "label_status",
                "vol_expansion",
            ]
        ],
        on=["underlying", "timestamp_us"],
        how="left",
    )

    summary_rows: list[dict[str, object]] = []
    for underlying, group in joined.groupby("underlying", sort=True):
        valid = group[group["label_status"] == "ok"]
        rows = len(group)
        valid_rows = len(valid)
        summary_rows.append(
            {
                "underlying": underlying,
                "rows": rows,
                "valid_label_rows": valid_rows,
                "future_missing_rows": int((group["label_status"] == "future_missing").sum()),
                "upper_first_rate": rate(valid, "upper_first"),
                "lower_first_rate": rate(valid, "lower_first"),
                "barrier_hit_rate": rate(valid, "upper_first")
                + rate(valid, "lower_first")
                + rate(valid, "both_or_ambiguous"),
                "none_rate": rate(valid, "none"),
                "vol_expansion_rate": float(valid["vol_expansion"].mean()) if valid_rows else np.nan,
                "median_future_return_bps": med(valid["future_12h_return_bps"]),
                "median_abs_future_return_bps": med(valid["future_12h_return_bps"].abs()),
                "median_mfe_up_bps": med(valid["mfe_up_bps"]),
                "median_mae_down_bps": med(valid["mae_down_bps"]),
                "median_future_rv_12h_bps": med(valid["future_realized_vol_12h_bps"]),
                "median_atm_iv": med(group["atm_iv"]),
                "median_skew_25d": med(group["skew_25d"]),
                "median_term_slope": med(group["term_slope"]),
                "median_quote_coverage": med(group["quote_coverage"]),
            }
        )
    summary = pd.DataFrame(summary_rows)

    factor_rows: list[dict[str, object]] = []
    bucketed = joined.copy()
    for factor in FACTOR_COLS:
        if factor not in bucketed.columns:
            continue
        bucketed[f"{factor}_bucket"] = bucketed.groupby("underlying", group_keys=False)[factor].apply(qbucket)
        for (underlying, bucket), group in bucketed.groupby(["underlying", f"{factor}_bucket"], sort=True):
            valid = group[group["label_status"] == "ok"]
            if group.empty:
                continue
            factor_rows.append(
                {
                    "underlying": underlying,
                    "factor": factor,
                    "bucket": bucket,
                    "rows": int(len(group)),
                    "valid_label_rows": int(len(valid)),
                    "barrier_hit_rate": rate(valid, "upper_first")
                    + rate(valid, "lower_first")
                    + rate(valid, "both_or_ambiguous"),
                    "upper_first_rate": rate(valid, "upper_first"),
                    "lower_first_rate": rate(valid, "lower_first"),
                    "vol_expansion_rate": float(valid["vol_expansion"].mean()) if len(valid) else np.nan,
                    "median_factor": med(group[factor]),
                    "median_future_return_bps": med(valid["future_12h_return_bps"]),
                    "median_abs_future_return_bps": med(valid["future_12h_return_bps"].abs()),
                    "median_mfe_up_bps": med(valid["mfe_up_bps"]),
                    "median_mae_down_bps": med(valid["mae_down_bps"]),
                }
            )
    factor_tests = pd.DataFrame(factor_rows)
    return summary, factor_tests, joined


def build_spearman(joined: pd.DataFrame) -> pd.DataFrame:
    frame = joined[joined["label_status"] == "ok"].copy()
    frame["abs_future_12h_return_bps"] = frame["future_12h_return_bps"].abs()
    frame["barrier_hit"] = frame["barrier_first_hit"].isin(
        ["upper_first", "lower_first", "both_or_ambiguous"]
    ).astype(float)
    frame["upper_first"] = (frame["barrier_first_hit"] == "upper_first").astype(float)
    frame["lower_first"] = (frame["barrier_first_hit"] == "lower_first").astype(float)
    frame["vol_expansion_num"] = frame["vol_expansion"].astype(float)

    targets = [
        ("future_12h_return_bps", "rho_future_12h_return_bps"),
        ("abs_future_12h_return_bps", "rho_abs_future_12h_return_bps"),
        ("future_realized_vol_12h_bps", "rho_future_realized_vol_12h_bps"),
        ("barrier_hit", "rho_barrier_hit"),
        ("upper_first", "rho_upper_first"),
        ("lower_first", "rho_lower_first"),
        ("vol_expansion_num", "rho_vol_expansion"),
    ]

    rows: list[dict[str, object]] = []
    for underlying, group in frame.groupby("underlying", sort=True):
        for factor in FACTOR_COLS:
            if factor not in group.columns:
                continue
            x = pd.to_numeric(group[factor], errors="coerce").replace([np.inf, -np.inf], np.nan)
            valid_x = x.notna()
            if valid_x.sum() < 20 or x[valid_x].nunique() < 3:
                continue
            row: dict[str, object] = {
                "underlying": underlying,
                "factor": factor,
                "n": int(valid_x.sum()),
                "factor_median": med(x),
                "factor_p10": float(x.dropna().quantile(0.10)),
                "factor_p90": float(x.dropna().quantile(0.90)),
            }
            for target, out_col in targets:
                y = pd.to_numeric(group[target], errors="coerce").replace([np.inf, -np.inf], np.nan)
                mask = valid_x & y.notna()
                if mask.sum() < 20 or y[mask].nunique() < 2:
                    row[out_col] = np.nan
                else:
                    row[out_col] = float(x[mask].corr(y[mask], method="spearman"))
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["underlying", "factor"]).reset_index(drop=True)


def rate(frame: pd.DataFrame, outcome: str) -> float:
    if frame.empty:
        return np.nan
    return float((frame["barrier_first_hit"] == outcome).mean())


def med(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(clean.median()) if len(clean) else np.nan


def save_outputs(
    regime: pd.DataFrame,
    labels: pd.DataFrame,
    summary: pd.DataFrame,
    factor_tests: pd.DataFrame,
    spearman: pd.DataFrame,
    paths: OutputPaths,
) -> None:
    for path in (
        paths.regime_parquet,
        paths.labels_parquet,
        paths.summary_csv,
        paths.factor_tests_csv,
        paths.spearman_csv,
        paths.report_md,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    paths.figures_dir.mkdir(parents=True, exist_ok=True)
    regime.to_parquet(paths.regime_parquet, index=False)
    labels.to_parquet(paths.labels_parquet, index=False)
    summary.to_csv(paths.summary_csv, index=False)
    factor_tests.to_csv(paths.factor_tests_csv, index=False)
    spearman.to_csv(paths.spearman_csv, index=False)


def set_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 140,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
        }
    )


def make_figures(joined: pd.DataFrame, factor_tests: pd.DataFrame, spearman: pd.DataFrame, paths: OutputPaths) -> list[Path]:
    set_style()
    joined = joined.copy()
    joined["ts"] = pd.to_datetime(joined["timestamp_utc"], utc=True)
    valid = joined[joined["label_status"] == "ok"].copy()
    figures: list[Path] = []

    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    for underlying, group in joined.groupby("underlying", sort=True):
        group = group.sort_values("ts")
        base = group["index_close"].iloc[0]
        axes[0].plot(group["ts"], group["index_close"] / base * 100.0, label=f"{underlying} index")
        axes[1].plot(group["ts"], group["trailing_realized_vol_12h_bps"], label=f"{underlying} RV 12h")
    axes[0].set_title("Index price, normalized to 100")
    axes[0].set_ylabel("normalized")
    axes[1].set_title("Trailing realized volatility, 12h")
    axes[1].set_ylabel("bps")
    axes[1].legend()
    axes[0].legend()
    fig.autofmt_xdate()
    price_fig = paths.figures_dir / "btc_eth_price_rv12h.png"
    fig.tight_layout()
    fig.savefig(price_fig)
    plt.close(fig)
    figures.append(price_fig)

    for underlying, group in joined.groupby("underlying", sort=True):
        group = group.sort_values("ts")
        fig, axes = plt.subplots(3, 1, figsize=(11, 7.2), sharex=True)
        axes[0].plot(group["ts"], group["atm_iv"], color="#1565c0")
        axes[0].set_title(f"{underlying} ATM IV")
        axes[0].set_ylabel("IV %")
        axes[1].plot(group["ts"], group["skew_25d"], color="#8e24aa")
        axes[1].axhline(0, color="#666666", linewidth=0.8)
        axes[1].set_title("25d skew: put IV - call IV")
        axes[1].set_ylabel("IV pt")
        axes[2].plot(group["ts"], group["term_slope"], color="#2e7d32")
        axes[2].axhline(0, color="#666666", linewidth=0.8)
        axes[2].set_title("Term slope: next ATM IV - front ATM IV")
        axes[2].set_ylabel("IV pt")
        fig.autofmt_xdate()
        fig.tight_layout()
        path = paths.figures_dir / f"{underlying.lower()}_surface_state.png"
        fig.savefig(path)
        plt.close(fig)
        figures.append(path)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for underlying, group in valid.groupby("underlying", sort=True):
        axes[0].hist(group["mfe_up_bps"].dropna(), bins=30, alpha=0.55, label=underlying)
        axes[1].hist(group["mae_down_bps"].dropna(), bins=30, alpha=0.55, label=underlying)
    axes[0].set_title("12h MFE up")
    axes[0].set_xlabel("bps")
    axes[1].set_title("12h MAE down")
    axes[1].set_xlabel("bps")
    axes[0].legend()
    axes[1].legend()
    fig.tight_layout()
    path = paths.figures_dir / "mfe_mae_distribution.png"
    fig.savefig(path)
    plt.close(fig)
    figures.append(path)

    scatter_specs = [
        ("atm_iv", "ATM IV"),
        ("skew_25d", "25d skew"),
        ("term_slope", "term slope"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    colors = {"BTC": "#1565c0", "ETH": "#ef6c00"}
    for ax, (factor, title) in zip(axes, scatter_specs):
        for underlying, group in valid.groupby("underlying", sort=True):
            ax.scatter(
                group[factor],
                group["future_12h_return_bps"],
                s=12,
                alpha=0.55,
                label=underlying,
                color=colors.get(underlying),
            )
        ax.axhline(0, color="#666666", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel(factor)
    axes[0].set_ylabel("future 12h return bps")
    axes[0].legend()
    fig.tight_layout()
    path = paths.figures_dir / "scatter_surface_vs_12h_move.png"
    fig.savefig(path)
    plt.close(fig)
    figures.append(path)

    heat = factor_tests[factor_tests["bucket"].isin(["low", "mid", "high", "flat"])].copy()
    if not heat.empty:
        factors = list(dict.fromkeys(heat["factor"].tolist()))
        buckets = ["low", "mid", "high"]
        fig, axes = plt.subplots(1, len(sorted(heat["underlying"].unique())), figsize=(12, 4), squeeze=False)
        for ax, underlying in zip(axes[0], sorted(heat["underlying"].unique())):
            mat = np.full((len(factors), len(buckets)), np.nan)
            sub = heat[heat["underlying"] == underlying]
            for i, factor in enumerate(factors):
                for j, bucket in enumerate(buckets):
                    row = sub[(sub["factor"] == factor) & (sub["bucket"] == bucket)]
                    if not row.empty:
                        mat[i, j] = float(row["barrier_hit_rate"].iloc[0])
            im = ax.imshow(mat, aspect="auto", vmin=0, vmax=1, cmap="viridis")
            ax.set_title(f"{underlying} barrier hit rate")
            ax.set_xticks(range(len(buckets)), buckets)
            ax.set_yticks(range(len(factors)), factors)
            for i in range(len(factors)):
                for j in range(len(buckets)):
                    val = mat[i, j]
                    if np.isfinite(val):
                        ax.text(j, i, f"{val:.0%}", ha="center", va="center", color="white", fontsize=8)
        fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.75)
        path = paths.figures_dir / "regime_bucket_label_rates.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        figures.append(path)

    if not spearman.empty:
        display_factors = [
            "atm_iv",
            "iv_richness_12h",
            "iv_rv_ratio_12h",
            "skew_25d",
            "term_stress",
            "abs_term_slope",
            "trailing_realized_vol_12h_bps",
            "compressed_range_6h",
            "vol_premium_gap_12h_bps",
            "compression_rel_to_rv_6h",
        ]
        metric = "rho_abs_future_12h_return_bps"
        underlyings = sorted(spearman["underlying"].unique())
        fig, axes = plt.subplots(1, len(underlyings), figsize=(12, 4.8), squeeze=False)
        for ax, underlying in zip(axes[0], underlyings):
            sub = spearman[spearman["underlying"] == underlying].set_index("factor")
            factors = [factor for factor in display_factors if factor in sub.index]
            values = np.array([[float(sub.loc[factor, metric])] for factor in factors])
            im = ax.imshow(values, aspect="auto", vmin=-1, vmax=1, cmap="coolwarm")
            ax.set_title(f"{underlying} Spearman vs |12h return|")
            ax.set_xticks([0], ["rho"])
            ax.set_yticks(range(len(factors)), factors)
            for i, factor in enumerate(factors):
                val = values[i, 0]
                if np.isfinite(val):
                    ax.text(0, i, f"{val:+.2f}", ha="center", va="center", color="black", fontsize=8)
        fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.75)
        path = paths.figures_dir / "spearman_abs_move_heatmap.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        figures.append(path)

    return figures


def pct(value: float) -> str:
    return "n/a" if not np.isfinite(value) else f"{value * 100:.1f}%"


def num(value: float, digits: int = 1) -> str:
    return "n/a" if not np.isfinite(value) else f"{value:.{digits}f}"


def rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def render_report(
    paths: OutputPaths,
    summary: pd.DataFrame,
    factor_tests: pd.DataFrame,
    spearman: pd.DataFrame,
    joined: pd.DataFrame,
    figures: list[Path],
    run_tag: str,
    horizon_hours: int,
    barrier_floor_bps: float,
    barrier_vol_multiple: float,
    vol_expansion_multiple: float,
) -> None:
    lines: list[str] = []
    lines.append("# BTC/ETH Options Regime 样例报告 v0")
    lines.append("")
    lines.append(f"- `run_tag`: `{run_tag}`")
    lines.append("- 数据范围：当前本地 Deribit Tardis 样例数据 `2025-05-01..2025-05-02`。")
    lines.append("- 结论边界：两天样本只用于验证期权 surface、12h path label 和图表管线，不能证明因子有效。")
    lines.append(f"- 12h barrier：`max({barrier_floor_bps:.0f}bps, {barrier_vol_multiple:.2f} * trailing_realized_vol_12h_bps)`。")
    lines.append(f"- `vol_expansion`：`future_realized_vol_12h_bps > {vol_expansion_multiple:.2f} * trailing_realized_vol_12h_bps`。")
    lines.append("")

    lines.append("## 输出文件")
    lines.append("")
    lines.append(f"- Regime state parquet：`{paths.regime_parquet.as_posix()}`")
    lines.append(f"- 12h path label parquet：`{paths.labels_parquet.as_posix()}`")
    lines.append(f"- Summary CSV：`{paths.summary_csv.as_posix()}`")
    lines.append(f"- Factor tests CSV：`{paths.factor_tests_csv.as_posix()}`")
    lines.append(f"- Spearman CSV：`{paths.spearman_csv.as_posix()}`")
    lines.append("")

    lines.append("## 覆盖与标签分解")
    lines.append("")
    lines.append("| underlying | rows | valid labels | future missing | barrier hit | upper first | lower first | median 12h abs move bps | median ATM IV |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in summary.itertuples(index=False):
        lines.append(
            "| "
            f"{row.underlying} | {row.rows} | {row.valid_label_rows} | {row.future_missing_rows} | "
            f"{pct(row.barrier_hit_rate)} | {pct(row.upper_first_rate)} | {pct(row.lower_first_rate)} | "
            f"{num(row.median_abs_future_return_bps)} | {num(row.median_atm_iv)} |"
        )
    lines.append("")

    lines.append("## 样例图")
    lines.append("")
    for figure in figures:
        lines.append(f"![{figure.stem}]({rel(figure, paths.report_md.parent)})")
        lines.append("")

    lines.append("## Spearman IC 快读")
    lines.append("")
    lines.append("`bps` 是变量单位，表示价格或波动幅度；`Spearman rho` 是无单位的排序相关，表示因子高低和未来目标高低是否单调一致。")
    lines.append("两日样本高度自相关，所以这里的 `rho` 只用于排查建模方向，不用于显著性判断。")
    lines.append("")
    if spearman.empty:
        lines.append("当前样本不足，未生成 Spearman 表。")
        lines.append("")
    else:
        display_factors = [
            "atm_iv",
            "iv_richness_12h",
            "iv_rv_ratio_12h",
            "skew_25d",
            "term_stress",
            "abs_term_slope",
            "trailing_realized_vol_12h_bps",
            "compressed_range_6h",
            "vol_premium_gap_12h_bps",
            "compression_rel_to_rv_6h",
        ]
        display = spearman[spearman["factor"].isin(display_factors)].copy()
        display["abs_rho"] = display["rho_abs_future_12h_return_bps"].abs()
        display = display.sort_values(["underlying", "abs_rho"], ascending=[True, False])
        lines.append("| underlying | factor | n | rho signed return | rho abs return | rho future RV | rho hit |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for row in display.itertuples(index=False):
            lines.append(
                "| "
                f"{row.underlying} | `{row.factor}` | {row.n} | "
                f"{num(row.rho_future_12h_return_bps, 2)} | {num(row.rho_abs_future_12h_return_bps, 2)} | "
                f"{num(row.rho_future_realized_vol_12h_bps, 2)} | {num(row.rho_barrier_hit, 2)} |"
            )
        lines.append("")

    lines.append("## 扩展因子说明")
    lines.append("")
    lines.append("| factor | 含义 |")
    lines.append("|---|---|")
    lines.append("| `iv_richness_12h` | `atm_iv - trailing_realized_vol_12h_ann_pct`，衡量期权 IV 相对过去 12h 已实现波动是否偏贵。 |")
    lines.append("| `iv_rv_ratio_12h` | `atm_iv / trailing_realized_vol_12h_ann_pct`，相对波动定价倍数。 |")
    lines.append("| `implied_move_12h_bps` | 用 ATM IV 折算出的 12h 隐含一标准差波动，单位 bps。 |")
    lines.append("| `vol_premium_gap_12h_bps` | `implied_move_12h_bps - trailing_realized_vol_12h_bps`，隐含路径空间相对已实现路径的差。 |")
    lines.append("| `term_stress` | `front ATM IV - next ATM IV`，近端 IV 相对远端越贵，短期压力越强。 |")
    lines.append("| `abs_term_slope` / `abs_skew_25d` | 不关心方向，只看期限结构或偏斜是否处于极端状态。 |")
    lines.append("| `*_change_1h` | 过去 1h 的 surface 变化，捕捉 IV、skew、term 是否在快速重定价。 |")
    lines.append("| `*_rank_pct` | 当前值在本样本中的百分位，仅用于 v0 诊断，长窗后应改成滚动历史百分位。 |")
    lines.append("| `compression_rel_to_rv_6h` | 6h 价格区间相对 6h realized vol 的比例，粗略描述“震荡路径是否被压扁”。 |")
    lines.append("")

    lines.append("## Regime Bucket 快读")
    lines.append("")
    lines.append("下面只展示每个因子的 low/mid/high 分桶后，12h 内先触发任一方向 barrier 的比例。它是研究诊断，不是策略胜率。")
    lines.append("")
    lines.append("| underlying | factor | bucket | rows | valid | hit rate | median factor | median abs 12h move bps |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    display = factor_tests[factor_tests["bucket"].isin(["low", "mid", "high"])].copy()
    for row in display.itertuples(index=False):
        lines.append(
            "| "
            f"{row.underlying} | `{row.factor}` | {row.bucket} | {row.rows} | {row.valid_label_rows} | "
            f"{pct(row.barrier_hit_rate)} | {num(row.median_factor)} | {num(row.median_abs_future_return_bps)} |"
        )
    lines.append("")

    lines.append("## 建模含义")
    lines.append("")
    lines.append("这版把问题从“单个链上事件是否推价格”切到更稳的价格序列问题：")
    lines.append("")
    lines.append("- 用 Deribit options surface 描述市场对未来波动、偏斜和期限结构的定价。")
    lines.append("- 用 12h path label 描述之后是否真的走出足够路径，而不是只看固定时点 return。")
    lines.append("- 用分桶表先看变量和路径标签有没有单调性或平台感，暂时不碰机器学习。")
    lines.append("")
    lines.append("当前两日样本中，最后 12h 被明确标成 `future_missing`，避免用不存在的未来数据伪造标签。")
    lines.append("如果要判断是否有真实机会，下一步至少需要 30 天以上数据，并按 discovery / validation / forward 分开。")
    lines.append("")

    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    underlyings = normalized_underlyings(args.underlyings)
    paths = output_paths(args.data_root, args.date_dir, args.doc_dir, args.run_tag)

    options_root = args.data_root / "derived" / "deribit_options_snapshots_5m"
    index_root = args.data_root / "derived" / "deribit_index_ohlc_1m"
    options = read_parquet_glob(options_root, "dt=*/*.parquet")
    index_ohlc = read_parquet_glob(index_root, "dt=*/*.parquet")

    surface = build_surface_state(options, underlyings)
    index_features = build_index_features(index_ohlc, underlyings)
    regime = merge_regime_with_index(surface, index_features, args.run_tag)
    regime = add_extended_regime_factors(regime, args.horizon_hours)
    labels = build_path_labels(
        regime,
        index_features,
        args.horizon_hours,
        args.barrier_floor_bps,
        args.barrier_vol_multiple,
        args.vol_expansion_multiple,
        args.run_tag,
    )
    summary, factor_tests, joined = build_summaries(regime, labels)
    spearman = build_spearman(joined)

    save_outputs(regime, labels, summary, factor_tests, spearman, paths)
    figures = make_figures(joined, factor_tests, spearman, paths)
    render_report(
        paths,
        summary,
        factor_tests,
        spearman,
        joined,
        figures,
        args.run_tag,
        args.horizon_hours,
        args.barrier_floor_bps,
        args.barrier_vol_multiple,
        args.vol_expansion_multiple,
    )

    print(f"regime_rows={len(regime)} labels_rows={len(labels)}")
    for row in summary.itertuples(index=False):
        print(
            f"{row.underlying}: rows={row.rows} valid={row.valid_label_rows} "
            f"future_missing={row.future_missing_rows} hit_rate={pct(row.barrier_hit_rate)}"
        )
    print(f"regime_parquet={paths.regime_parquet}")
    print(f"labels_parquet={paths.labels_parquet}")
    print(f"summary_csv={paths.summary_csv}")
    print(f"factor_tests_csv={paths.factor_tests_csv}")
    print(f"spearman_csv={paths.spearman_csv}")
    print(f"report_md={paths.report_md}")


if __name__ == "__main__":
    main()
