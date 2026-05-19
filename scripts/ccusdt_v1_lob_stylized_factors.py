#!/usr/bin/env python
"""CCUSDT classic LOB stylized-factor diagnostics.

This is an independent research pass inspired by BTC/USD LOB stylized-fact
work. It deliberately stays separate from the current TFI strategy branch:
the outputs are distribution, stability, and short-horizon diagnostic tables,
not execution recommendations.
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=PerformanceWarning)


GUARDRAIL = "research_only_lob_stylized_factors_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v1_lob_stylized_factors_v1"
SOURCE_RUN_TAG = "20260517_ccusdt_fixed_factors_v3"
US_PER_SECOND = 1_000_000
EPS = 1e-12
LEVELS = 25

SNAPSHOT_FEATURES: dict[str, str] = {
    "spread_bps": "spread",
    "top_depth_quote": "depth",
    "depth25_quote": "depth",
    "depth_near_share_5_25": "depth_shape",
    "bid_concentration_1_25": "depth_shape",
    "ask_concentration_1_25": "depth_shape",
    "bid_slope_quote_per_bps": "depth_shape",
    "ask_slope_quote_per_bps": "depth_shape",
    "depth_slope_imbalance": "depth_shape",
    "obi_1": "imbalance",
    "obi_5": "imbalance",
    "obi_10": "imbalance",
    "obi_25": "imbalance",
    "obi_5_minus_25": "imbalance_shape",
    "microprice_dev_bps": "microprice",
    "buy_lc_5_bps": "liquidity_cost",
    "sell_lc_5_bps": "liquidity_cost",
    "two_sided_lc_5_bps": "liquidity_cost",
    "buy_lc_25_bps": "liquidity_cost",
    "sell_lc_25_bps": "liquidity_cost",
    "two_sided_lc_25_bps": "liquidity_cost",
    "buy_lc_100_bps": "liquidity_cost",
    "sell_lc_100_bps": "liquidity_cost",
    "two_sided_lc_100_bps": "liquidity_cost",
}

EVENT_FEATURES: dict[str, str] = {
    "spread_bps": "spread",
    "microprice_dev_bps": "microprice",
    "queue_imbalance_1": "imbalance",
    "queue_imbalance_5": "imbalance",
    "queue_imbalance_25": "imbalance",
    "ofi_l1_depth_norm": "ofi",
    "mlofi_roll10_l1": "mlofi",
    "mlofi_roll10_l5": "mlofi",
    "mlofi_roll10_l25": "mlofi",
    "trade_flow_imbalance": "trade_flow",
    "trade_arrival_alignment": "trade_flow",
    "queue_depletion_intensity": "depletion",
    "replenish_intensity": "resiliency",
    "cancellation_withdrawal_intensity": "cancel_withdraw",
    "liquidity_shock_score": "liquidity_shock",
}


@dataclass(frozen=True)
class Paths:
    data_root: Path
    panel_root: Path
    source_run_tag: str
    date_dir: Path
    doc_dir: Path
    symbol: str
    run_tag: str

    @property
    def snapshot_root(self) -> Path:
        return self.data_root / "external" / "bullish_book_snapshot_25" / f"symbol={self.symbol}"

    @property
    def event_panel_root(self) -> Path:
        return self.panel_root / f"run_tag={self.source_run_tag}" / f"symbol={self.symbol}"

    @property
    def snapshot_daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_lob_stylized_snapshot_daily_{self.run_tag}.csv"

    @property
    def snapshot_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_lob_stylized_snapshot_scorecard_{self.run_tag}.csv"

    @property
    def event_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_lob_stylized_event_scorecard_{self.run_tag}.csv"

    @property
    def factor_corr_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_lob_stylized_factor_corr_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_lob_stylized_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-lob-stylized-factors-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT classic LOB stylized-factor diagnostics.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt/v1"))
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--source-run-tag", default=SOURCE_RUN_TAG)
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--horizons-sec", default="1,10,60")
    parser.add_argument("--event-horizons", default="25")
    parser.add_argument("--quote-notionals", default="5,25,100")
    parser.add_argument("--dates", default="", help="Optional comma-separated dates for smoke runs, e.g. 2026-05-15")
    parser.add_argument("--max-snapshot-sample-per-day", type=int, default=25_000)
    parser.add_argument("--max-event-sample-per-day", type=int, default=25_000)
    parser.add_argument("--seed", type=int, default=20260518)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_ints(raw: str) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one integer")
    return sorted(set(values))


def parse_floats(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one float")
    return sorted(set(values))


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    out = np.full_like(num, np.nan, dtype="float64")
    mask = np.isfinite(num) & np.isfinite(den) & (np.abs(den) > EPS)
    out[mask] = num[mask] / den[mask]
    return out


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def finite_rate(mask: Iterable[bool] | np.ndarray) -> float:
    arr = np.asarray(mask)
    return float(arr.mean()) if len(arr) else np.nan


def available_snapshot_dates(paths: Paths) -> list[str]:
    if not paths.snapshot_root.exists():
        return []
    return sorted(path.name.replace("dt=", "") for path in paths.snapshot_root.glob("dt=*") if path.is_dir())


def snapshot_path(paths: Paths, date: str) -> Path:
    return paths.snapshot_root / f"dt={date}" / f"{paths.symbol}.csv.gz"


def snapshot_usecols() -> list[str]:
    cols = ["timestamp", "local_timestamp"]
    for level in range(LEVELS):
        cols.extend(
            [
                f"asks[{level}].price",
                f"asks[{level}].amount",
                f"bids[{level}].price",
                f"bids[{level}].amount",
            ]
        )
    return cols


def load_snapshot_day(paths: Paths, date: str) -> pd.DataFrame:
    df = pd.read_csv(snapshot_path(paths, date), usecols=snapshot_usecols(), compression="gzip")
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["local_timestamp", "asks[0].price", "bids[0].price"])
    df = df.sort_values(["local_timestamp", "timestamp"]).drop_duplicates("local_timestamp", keep="last")
    df["date"] = date
    return df.reset_index(drop=True)


def matrix_from_levels(df: pd.DataFrame, side: str, field: str) -> np.ndarray:
    cols = [f"{side}s[{level}].{field}" for level in range(LEVELS)]
    return df[cols].to_numpy(dtype="float64", copy=True)


def vwap_cost_bps(prices: np.ndarray, amounts: np.ndarray, mid: np.ndarray, quote_notional: float, side: str) -> np.ndarray:
    quote_levels = prices * amounts
    cum_quote = np.cumsum(quote_levels, axis=1)
    cum_amount = np.cumsum(amounts, axis=1)
    ok = np.isfinite(cum_quote[:, -1]) & (cum_quote[:, -1] >= quote_notional)
    hit = cum_quote >= quote_notional
    idx = np.argmax(hit, axis=1)

    rows = np.arange(len(prices))
    prev_quote = np.zeros(len(prices), dtype="float64")
    prev_amount = np.zeros(len(prices), dtype="float64")
    has_prev = idx > 0
    prev_quote[has_prev] = cum_quote[rows[has_prev], idx[has_prev] - 1]
    prev_amount[has_prev] = cum_amount[rows[has_prev], idx[has_prev] - 1]

    level_price = prices[rows, idx]
    rem_quote = quote_notional - prev_quote
    filled_amount = prev_amount + rem_quote / np.maximum(level_price, EPS)
    vwap = quote_notional / np.maximum(filled_amount, EPS)

    if side == "buy":
        cost = 10_000.0 * (vwap - mid) / np.maximum(mid, EPS)
    elif side == "sell":
        cost = 10_000.0 * (mid - vwap) / np.maximum(mid, EPS)
    else:
        raise ValueError(side)
    cost[~ok] = np.nan
    return cost


def add_future_and_past_returns(frame: pd.DataFrame, horizons_sec: list[int]) -> pd.DataFrame:
    times = frame["local_timestamp"].to_numpy(dtype="int64")
    mid = frame["mid_price"].to_numpy(dtype="float64")
    out = frame.copy()
    for horizon in horizons_sec:
        target = times + horizon * US_PER_SECOND
        idx = np.searchsorted(times, target, side="left")
        future = np.full(len(frame), np.nan, dtype="float64")
        valid = idx < len(frame)
        future[valid] = mid[idx[valid]]
        out[f"fwd_time_{horizon}s_bps"] = 10_000.0 * np.log(future / mid)

        past_target = times - horizon * US_PER_SECOND
        past_idx = np.searchsorted(times, past_target, side="right") - 1
        past = np.full(len(frame), np.nan, dtype="float64")
        past_valid = past_idx >= 0
        past[past_valid] = mid[past_idx[past_valid]]
        out[f"past_time_{horizon}s_bps"] = 10_000.0 * np.log(mid / past)
    return out


def compute_snapshot_features(df: pd.DataFrame, quote_notionals: list[float]) -> pd.DataFrame:
    ask_p = matrix_from_levels(df, "ask", "price")
    ask_q = matrix_from_levels(df, "ask", "amount")
    bid_p = matrix_from_levels(df, "bid", "price")
    bid_q = matrix_from_levels(df, "bid", "amount")

    mid = (ask_p[:, 0] + bid_p[:, 0]) / 2.0
    spread_bps = 10_000.0 * (ask_p[:, 0] - bid_p[:, 0]) / np.maximum(mid, EPS)

    out = pd.DataFrame(
        {
            "date": df["date"].to_numpy(),
            "timestamp": df["timestamp"].to_numpy(),
            "local_timestamp": df["local_timestamp"].to_numpy(),
            "mid_price": mid,
            "spread_bps": spread_bps,
        }
    )

    bid_quote = bid_p * bid_q
    ask_quote = ask_p * ask_q
    for k in [1, 5, 10, 25]:
        bq = np.nansum(bid_quote[:, :k], axis=1)
        aq = np.nansum(ask_quote[:, :k], axis=1)
        out[f"bid_depth{k}_quote"] = bq
        out[f"ask_depth{k}_quote"] = aq
        out[f"obi_{k}"] = safe_div(bq - aq, bq + aq)

    out["top_depth_quote"] = out["bid_depth1_quote"] + out["ask_depth1_quote"]
    out["depth25_quote"] = out["bid_depth25_quote"] + out["ask_depth25_quote"]
    out["depth_near_share_5_25"] = safe_div(
        (out["bid_depth5_quote"] + out["ask_depth5_quote"]).to_numpy(dtype="float64"),
        out["depth25_quote"].to_numpy(dtype="float64"),
    )
    out["bid_concentration_1_25"] = safe_div(
        out["bid_depth1_quote"].to_numpy(dtype="float64"),
        out["bid_depth25_quote"].to_numpy(dtype="float64"),
    )
    out["ask_concentration_1_25"] = safe_div(
        out["ask_depth1_quote"].to_numpy(dtype="float64"),
        out["ask_depth25_quote"].to_numpy(dtype="float64"),
    )
    bid_span_bps = 10_000.0 * (bid_p[:, 0] - bid_p[:, -1]) / np.maximum(mid, EPS)
    ask_span_bps = 10_000.0 * (ask_p[:, -1] - ask_p[:, 0]) / np.maximum(mid, EPS)
    out["bid_slope_quote_per_bps"] = safe_div(out["bid_depth25_quote"].to_numpy(dtype="float64"), bid_span_bps)
    out["ask_slope_quote_per_bps"] = safe_div(out["ask_depth25_quote"].to_numpy(dtype="float64"), ask_span_bps)
    out["depth_slope_imbalance"] = safe_div(
        out["bid_slope_quote_per_bps"].to_numpy(dtype="float64") - out["ask_slope_quote_per_bps"].to_numpy(dtype="float64"),
        out["bid_slope_quote_per_bps"].to_numpy(dtype="float64") + out["ask_slope_quote_per_bps"].to_numpy(dtype="float64"),
    )
    out["obi_5_minus_25"] = out["obi_5"] - out["obi_25"]

    micro = (ask_p[:, 0] * bid_q[:, 0] + bid_p[:, 0] * ask_q[:, 0]) / np.maximum(bid_q[:, 0] + ask_q[:, 0], EPS)
    out["microprice_dev_bps"] = 10_000.0 * (micro - mid) / np.maximum(mid, EPS)

    for notional in quote_notionals:
        name = str(int(notional)) if float(notional).is_integer() else str(notional).replace(".", "p")
        buy_cost = vwap_cost_bps(ask_p, ask_q, mid, notional, side="buy")
        sell_cost = vwap_cost_bps(bid_p, bid_q, mid, notional, side="sell")
        out[f"buy_lc_{name}_bps"] = buy_cost
        out[f"sell_lc_{name}_bps"] = sell_cost
        out[f"two_sided_lc_{name}_bps"] = buy_cost + sell_cost

    return out


def summarize_snapshot_day(features: pd.DataFrame, date: str) -> dict[str, object]:
    mid = features["mid_price"].to_numpy(dtype="float64")
    quote_change_rate = finite_rate(np.r_[False, np.diff(mid) != 0])
    gaps_ms = np.diff(features["local_timestamp"].to_numpy(dtype="int64")) / 1000.0
    return {
        "date": date,
        "rows": int(len(features)),
        "mid_distinct": int(pd.Series(mid).nunique()),
        "quote_change_rate": quote_change_rate,
        "median_gap_ms": finite_quantile(gaps_ms, 0.50),
        "p95_gap_ms": finite_quantile(gaps_ms, 0.95),
        "median_spread_bps": finite_quantile(features["spread_bps"], 0.50),
        "p95_spread_bps": finite_quantile(features["spread_bps"], 0.95),
        "median_top_depth_quote": finite_quantile(features["top_depth_quote"], 0.50),
        "p05_top_depth_quote": finite_quantile(features["top_depth_quote"], 0.05),
        "median_depth25_quote": finite_quantile(features["depth25_quote"], 0.50),
        "median_depth_near_share_5_25": finite_quantile(features["depth_near_share_5_25"], 0.50),
        "median_obi_1": finite_quantile(features["obi_1"], 0.50),
        "median_obi_5": finite_quantile(features["obi_5"], 0.50),
        "median_obi_25": finite_quantile(features["obi_25"], 0.50),
        "p95_abs_microprice_dev_bps": finite_quantile(np.abs(features["microprice_dev_bps"]), 0.95),
        "median_two_sided_lc_5_bps": finite_quantile(features.get("two_sided_lc_5_bps", pd.Series(dtype=float)), 0.50),
        "median_two_sided_lc_25_bps": finite_quantile(features.get("two_sided_lc_25_bps", pd.Series(dtype=float)), 0.50),
        "median_two_sided_lc_100_bps": finite_quantile(features.get("two_sided_lc_100_bps", pd.Series(dtype=float)), 0.50),
        "p95_two_sided_lc_100_bps": finite_quantile(features.get("two_sided_lc_100_bps", pd.Series(dtype=float)), 0.95),
    }


def score_feature_pair(df: pd.DataFrame, feature: str, target: str, past_target: str | None = None) -> dict[str, object]:
    x = pd.to_numeric(df[feature], errors="coerce").to_numpy(dtype="float64")
    y = pd.to_numeric(df[target], errors="coerce").to_numpy(dtype="float64")
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    dates = df.loc[mask, "date"].astype(str).to_numpy()
    if len(x) < 200:
        return {
            "rows": int(len(x)),
            "spearman": np.nan,
            "auc": np.nan,
            "top_bottom_bps": np.nan,
            "daily_sign_rate": np.nan,
            "daily_valid_days": 0,
            "past_ic": np.nan,
            "past_over_forward_abs_ratio": np.nan,
        }

    try:
        spearman = float(spearmanr(x, y).statistic)
    except Exception:
        spearman = np.nan

    try:
        y_bin = y > 0
        auc = float(roc_auc_score(y_bin, x)) if y_bin.any() and (~y_bin).any() else np.nan
    except Exception:
        auc = np.nan

    rank = pd.Series(x).rank(method="first", pct=True).to_numpy()
    top = y[rank >= 0.90]
    bottom = y[rank <= 0.10]
    top_bottom = float(np.nanmean(top) - np.nanmean(bottom)) if len(top) and len(bottom) else np.nan

    daily_ics: list[float] = []
    tmp = pd.DataFrame({"date": dates, "x": x, "y": y})
    for _, day in tmp.groupby("date", sort=True):
        if len(day) < 100 or day["x"].nunique(dropna=True) < 5 or day["y"].nunique(dropna=True) < 5:
            continue
        try:
            daily_ics.append(float(spearmanr(day["x"], day["y"]).statistic))
        except Exception:
            continue
    valid_daily = [v for v in daily_ics if np.isfinite(v)]
    if np.isfinite(spearman) and valid_daily:
        sign = 1.0 if spearman >= 0 else -1.0
        daily_sign_rate = float(np.mean([np.sign(v) == sign for v in valid_daily]))
    else:
        daily_sign_rate = np.nan

    past_ic = np.nan
    ratio = np.nan
    if past_target and past_target in df.columns:
        yp = pd.to_numeric(df.loc[mask, past_target], errors="coerce").to_numpy(dtype="float64")
        pmask = np.isfinite(x) & np.isfinite(yp)
        if pmask.sum() >= 200:
            try:
                past_ic = float(spearmanr(x[pmask], yp[pmask]).statistic)
                ratio = abs(past_ic) / max(abs(spearman), EPS) if np.isfinite(spearman) else np.nan
            except Exception:
                past_ic = np.nan

    return {
        "rows": int(len(x)),
        "spearman": spearman,
        "auc": auc,
        "top_bottom_bps": top_bottom,
        "daily_sign_rate": daily_sign_rate,
        "daily_valid_days": int(len(valid_daily)),
        "past_ic": past_ic,
        "past_over_forward_abs_ratio": ratio,
    }


def score_features(
    df: pd.DataFrame,
    features: dict[str, str],
    targets: list[str],
    family_prefix: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    present_features = [feature for feature in features if feature in df.columns]
    for target in targets:
        if target not in df.columns:
            continue
        past_target = target.replace("fwd_time_", "past_time_") if target.startswith("fwd_time_") else None
        for feature in present_features:
            metrics = score_feature_pair(df, feature, target, past_target=past_target)
            score = 0.0
            if np.isfinite(metrics["spearman"]):
                score += 80.0 * abs(float(metrics["spearman"]))
            if np.isfinite(metrics["auc"]):
                score += 8.0 * max(float(metrics["auc"]) - 0.5, 0.0)
            if np.isfinite(metrics["top_bottom_bps"]):
                score += min(abs(float(metrics["top_bottom_bps"])), 10.0)
            if np.isfinite(metrics["daily_sign_rate"]):
                score += 5.0 * float(metrics["daily_sign_rate"])
            rows.append(
                {
                    "panel": family_prefix,
                    "target": target,
                    "feature": feature,
                    "family": features[feature],
                    **metrics,
                    "diagnostic_score": score,
                    "guardrail": GUARDRAIL,
                }
            )
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["diagnostic_score", "rows"], ascending=[False, False]).reset_index(drop=True)
    return out


def event_panel_files(paths: Paths) -> list[Path]:
    files = sorted(paths.event_panel_root.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no event panel CSV files under {paths.event_panel_root}")
    return files


def load_event_panel_sample(
    paths: Paths,
    horizons_sec: list[int],
    event_horizons: list[int],
    max_per_day: int,
    seed: int,
    date_filter: set[str] | None = None,
) -> pd.DataFrame:
    usecols = [
        "date",
        "timestamp",
        "local_timestamp",
        "event_index",
        "mid_price",
        *EVENT_FEATURES.keys(),
    ]
    frames: list[pd.DataFrame] = []
    for path in event_panel_files(paths):
        if date_filter:
            dt_parts = [part for part in path.parts if part.startswith("dt=")]
            if dt_parts and dt_parts[-1].replace("dt=", "") not in date_filter:
                continue
        header = pd.read_csv(path, nrows=0).columns
        cols = [col for col in usecols if col in header]
        frames.append(pd.read_csv(path, usecols=cols))
    if not frames:
        raise FileNotFoundError(f"no event panel files after date filter under {paths.event_panel_root}")
    panel = pd.concat(frames, ignore_index=True)
    for col in panel.columns:
        if col != "date":
            panel[col] = pd.to_numeric(panel[col], errors="coerce")
    panel = panel.dropna(subset=["date", "local_timestamp", "mid_price"])
    panel = panel.sort_values(["date", "local_timestamp", "event_index"]).reset_index(drop=True)

    day_frames: list[pd.DataFrame] = []
    rng = np.random.default_rng(seed)
    for date, day in panel.groupby("date", sort=True):
        day = day.copy().reset_index(drop=True)
        day = add_future_and_past_returns(day, horizons_sec)
        for horizon in event_horizons:
            future = day["mid_price"].shift(-horizon)
            day[f"fwd_event_{horizon}_bps"] = 10_000.0 * np.log(future / day["mid_price"])
        if max_per_day and len(day) > max_per_day:
            idx = rng.choice(len(day), size=max_per_day, replace=False)
            day = day.iloc[np.sort(idx)]
        day_frames.append(day)
    return pd.concat(day_frames, ignore_index=True)


def correlation_table(df: pd.DataFrame, features: dict[str, str], prefix: str) -> pd.DataFrame:
    cols = [col for col in features if col in df.columns]
    if len(cols) < 2:
        return pd.DataFrame()
    corr = df[cols].corr(method="spearman", min_periods=500)
    rows: list[dict[str, object]] = []
    for i, left in enumerate(cols):
        for right in cols[i + 1 :]:
            value = corr.loc[left, right]
            if np.isfinite(value):
                rows.append(
                    {
                        "panel": prefix,
                        "feature_left": left,
                        "family_left": features[left],
                        "feature_right": right,
                        "family_right": features[right],
                        "spearman_corr": float(value),
                        "abs_corr": abs(float(value)),
                    }
                )
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("abs_corr", ascending=False).reset_index(drop=True)
    return out


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20, digits: int = 4) -> list[str]:
    if df.empty:
        return ["", "_No rows._", ""]
    display = df.loc[:, [col for col in columns if col in df.columns]].head(max_rows).copy()
    lines = ["", "| " + " | ".join(display.columns) + " |", "| " + " | ".join(["---"] * len(display.columns)) + " |"]
    for _, row in display.iterrows():
        vals: list[str] = []
        for col in display.columns:
            val = row[col]
            if isinstance(val, (float, np.floating)):
                vals.append(fmt_num(val, digits))
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def top_metric(scores: pd.DataFrame, feature: str, target: str, metric: str) -> float:
    if scores.empty or metric not in scores.columns:
        return np.nan
    mask = scores["feature"].eq(feature) & scores["target"].eq(target)
    if not mask.any():
        return np.nan
    return float(scores.loc[mask, metric].iloc[0])


def aggregate_daily(daily: pd.DataFrame) -> dict[str, object]:
    if daily.empty:
        return {}
    return {
        "snapshot_days": int(len(daily)),
        "snapshot_rows": int(daily["rows"].sum()),
        "median_daily_rows": finite_quantile(daily["rows"], 0.50),
        "median_daily_quote_change_rate": finite_quantile(daily["quote_change_rate"], 0.50),
        "median_daily_median_spread_bps": finite_quantile(daily["median_spread_bps"], 0.50),
        "median_daily_p95_spread_bps": finite_quantile(daily["p95_spread_bps"], 0.50),
        "median_daily_p05_top_depth_quote": finite_quantile(daily["p05_top_depth_quote"], 0.50),
        "median_daily_median_depth25_quote": finite_quantile(daily["median_depth25_quote"], 0.50),
        "median_daily_depth_near_share_5_25": finite_quantile(daily["median_depth_near_share_5_25"], 0.50),
        "median_daily_median_obi_1": finite_quantile(daily["median_obi_1"], 0.50),
        "median_daily_median_obi_25": finite_quantile(daily["median_obi_25"], 0.50),
        "median_daily_two_sided_lc_5_bps": finite_quantile(daily["median_two_sided_lc_5_bps"], 0.50),
        "median_daily_two_sided_lc_25_bps": finite_quantile(daily["median_two_sided_lc_25_bps"], 0.50),
        "median_daily_two_sided_lc_100_bps": finite_quantile(daily["median_two_sided_lc_100_bps"], 0.50),
    }


def write_report(
    paths: Paths,
    args: argparse.Namespace,
    daily: pd.DataFrame,
    snapshot_scores: pd.DataFrame,
    event_scores: pd.DataFrame,
    corr: pd.DataFrame,
    summary: dict[str, object],
) -> None:
    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT Classic LOB Stylized-Factor Diagnostics",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This is an independent BTC-style LOB factor pass on CCUSDT. It does not attach the findings to the current TFI strategy branch, does not simulate queue-position execution, and does not make a trading recommendation.",
            "",
            "## Factor Map",
            "",
            "Let best ask/bid be $a_t,b_t$, mid be $m_t=(a_t+b_t)/2$, and cumulative quote depth to level $K$ be $D^a_{K,t},D^b_{K,t}$.",
            "",
            "- Spread: $s_t=10^4(a_t-b_t)/m_t$.",
            "- Depth imbalance: $I_{K,t}=(D^b_{K,t}-D^a_{K,t})/(D^b_{K,t}+D^a_{K,t})$.",
            "- Microprice deviation: $10^4(MP_t-m_t)/m_t$, with $MP_t=(a_t q^b_{1,t}+b_t q^a_{1,t})/(q^b_{1,t}+q^a_{1,t})$.",
            "- Liquidity cost: $LC^+_{\\omega,t}=10^4(VWAP^+_{\\omega,t}/m_t-1)$ for buying quote notional $\\omega$; sell-side cost is symmetric.",
            "- Shape: near-depth concentration, $D_5/D_{25}$, 25-level quote-depth slope per bps, and shallow-versus-deep imbalance drift $I_5-I_{25}$.",
            "- Dynamic order flow: OFI/MLOFI, trade-flow imbalance, depletion, replenishment, cancellation-withdrawal, and liquidity-shock fields from the fixed event panel.",
            "",
            "## Scope",
            "",
            f"- Snapshot source: `{paths.snapshot_root}`.",
            f"- Event panel source: `{paths.event_panel_root}`.",
            f"- Snapshot sample per day: `{args.max_snapshot_sample_per_day}`.",
            f"- Event sample per day: `{args.max_event_sample_per_day}`.",
            f"- Time horizons: `{args.horizons_sec}` seconds.",
            f"- Event horizons: `{args.event_horizons}` events.",
            "",
            "## Static Book Shape",
        ]
    )
    daily_cols = [
        "date",
        "rows",
        "mid_distinct",
        "quote_change_rate",
        "median_spread_bps",
        "p95_spread_bps",
        "p05_top_depth_quote",
        "median_depth25_quote",
        "median_two_sided_lc_100_bps",
    ]
    lines.extend(markdown_table(daily, daily_cols, max_rows=25))

    agg_items = [
        ("snapshot_days", "snapshot days"),
        ("snapshot_rows", "snapshot rows"),
        ("median_daily_quote_change_rate", "median daily quote-change rate"),
        ("median_daily_median_spread_bps", "median daily median spread bps"),
        ("median_daily_p95_spread_bps", "median daily p95 spread bps"),
        ("median_daily_p05_top_depth_quote", "median daily p05 top depth quote"),
        ("median_daily_median_depth25_quote", "median daily median 25-level depth quote"),
        ("median_daily_depth_near_share_5_25", "median daily near-share $D_5/D_{25}$"),
        ("median_daily_two_sided_lc_100_bps", "median daily two-sided LC 100 quote bps"),
    ]
    lines.extend(["## Aggregate Read", ""])
    for key, label in agg_items:
        val = summary.get(key)
        if isinstance(val, float):
            lines.append(f"- {label}: `{fmt_num(val, 4)}`")
        else:
            lines.append(f"- {label}: `{val}`")
    lines.append("")

    tfi_event_ic = top_metric(event_scores, "trade_flow_imbalance", "fwd_event_25_bps", "spearman")
    tfi_event_auc = top_metric(event_scores, "trade_flow_imbalance", "fwd_event_25_bps", "auc")
    tfi_event_tb = top_metric(event_scores, "trade_flow_imbalance", "fwd_event_25_bps", "top_bottom_bps")
    tfi_time_ic = top_metric(event_scores, "trade_flow_imbalance", "fwd_time_10s_bps", "spearman")
    tfi_time_past_ratio = top_metric(event_scores, "trade_flow_imbalance", "fwd_time_10s_bps", "past_over_forward_abs_ratio")
    mlofi_ic = top_metric(event_scores, "mlofi_roll10_l1", "fwd_time_10s_bps", "spearman")
    snapshot_best = snapshot_scores.iloc[0].to_dict() if len(snapshot_scores) else {}
    lines.extend(
        [
            "## Main Findings",
            "",
            f"1. CCUSDT is a sparse-moving snapshot book: median daily quote-change rate is `{fmt_num(summary.get('median_daily_quote_change_rate'), 4)}`, while the median daily median spread is `{fmt_num(summary.get('median_daily_median_spread_bps'), 4)}` bps and median p95 spread is `{fmt_num(summary.get('median_daily_p95_spread_bps'), 4)}` bps.",
            f"2. Top-of-book depth is thin relative to the 25-level book: median daily p05 top depth is `{fmt_num(summary.get('median_daily_p05_top_depth_quote'), 4)}` quote, but median 25-level depth is `{fmt_num(summary.get('median_daily_median_depth25_quote'), 4)}` quote. The median two-sided liquidity cost for 100 quote notional is `{fmt_num(summary.get('median_daily_two_sided_lc_100_bps'), 4)}` bps.",
            f"3. Static BTC-style book-shape factors are weak as standalone forward predictors. The best snapshot row is `{snapshot_best.get('feature', '')}` on `{snapshot_best.get('target', '')}` with Spearman `{fmt_num(snapshot_best.get('spearman'), 4)}`, AUC `{fmt_num(snapshot_best.get('auc'), 4)}`, top-bottom `{fmt_num(snapshot_best.get('top_bottom_bps'), 4)}` bps, and past/forward IC ratio `{fmt_num(snapshot_best.get('past_over_forward_abs_ratio'), 4)}`.",
            f"4. Dynamic order-flow is the strongest LOB family: `trade_flow_imbalance` on `fwd_event_25_bps` has IC `{fmt_num(tfi_event_ic, 4)}`, AUC `{fmt_num(tfi_event_auc, 4)}`, and top-bottom `{fmt_num(tfi_event_tb, 4)}` bps. On `fwd_time_10s_bps`, its IC is `{fmt_num(tfi_time_ic, 4)}`, but the past/forward IC ratio is `{fmt_num(tfi_time_past_ratio, 4)}`, so a large part of the signal is recent-flow persistence rather than a clean innovation.",
            f"5. MLOFI is a secondary family, not a replacement for trade flow: `mlofi_roll10_l1` on `fwd_time_10s_bps` has IC `{fmt_num(mlofi_ic, 4)}`. OBI/microprice/shape variables are highly redundant and should be compressed before any future model.",
            "",
        ]
    )

    lines.extend(["## Snapshot Factor Diagnostics"])
    score_cols = [
        "target",
        "feature",
        "family",
        "rows",
        "spearman",
        "auc",
        "top_bottom_bps",
        "daily_sign_rate",
        "past_ic",
        "past_over_forward_abs_ratio",
        "diagnostic_score",
    ]
    lines.extend(markdown_table(snapshot_scores, score_cols, max_rows=30))

    lines.extend(["## Event-Panel Dynamic Diagnostics"])
    lines.extend(markdown_table(event_scores, score_cols, max_rows=30))

    lines.extend(["## Factor Redundancy"])
    corr_cols = ["panel", "feature_left", "feature_right", "spearman_corr", "abs_corr"]
    lines.extend(markdown_table(corr, corr_cols, max_rows=20))

    lines.extend(
        [
            "## Current Read",
            "",
            "- This pass is descriptive and diagnostic. A high IC/top-bottom row means the factor is worth understanding; it is not an executable edge by itself.",
            "- The most relevant negative-control column is `past_over_forward_abs_ratio`: values above `1` mean the factor explains recent past movement at least as strongly as future movement.",
            "- Static book-shape factors should be interpreted as venue-state variables. They can condition spread/depth/regime, but they should not be forced into the TFI micro-structure found earlier.",
            "- Dynamic OFI/MLOFI/trade-flow rows overlap conceptually with the earlier event-factor sweep, but this report treats them as a separate LOB-stylized-fact block.",
            "",
            "## Outputs",
            "",
            f"- `{paths.snapshot_daily_csv}`",
            f"- `{paths.snapshot_scorecard_csv}`",
            f"- `{paths.event_scorecard_csv}`",
            f"- `{paths.factor_corr_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_lob_stylized_factors.py",
            "```",
            "",
            "## Reference",
            "",
            "- Schnaubelt, Rende, and Krauss, `Testing Stylized Facts of Bitcoin Limit Order Books`, Journal of Risk and Financial Management, 2019: https://www.mdpi.com/1911-8074/12/1/25",
            "",
        ]
    )
    paths.report_md.parent.mkdir(parents=True, exist_ok=True)
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        data_root=resolve_repo_path(args.data_root),
        panel_root=resolve_repo_path(args.panel_root),
        source_run_tag=args.source_run_tag,
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        symbol=args.symbol,
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    horizons_sec = parse_ints(args.horizons_sec)
    event_horizons = parse_ints(args.event_horizons)
    quote_notionals = parse_floats(args.quote_notionals)
    requested_dates = parse_strings(args.dates)

    dates = available_snapshot_dates(paths)
    if requested_dates:
        requested = set(requested_dates)
        dates = [date for date in dates if date in requested]
    if not dates:
        raise FileNotFoundError(f"no snapshot dates under {paths.snapshot_root}")

    daily_rows: list[dict[str, object]] = []
    snapshot_samples: list[pd.DataFrame] = []
    rng = np.random.default_rng(args.seed)
    needed_snapshot_cols = [
        "date",
        "local_timestamp",
        "mid_price",
        *SNAPSHOT_FEATURES.keys(),
        *[f"fwd_time_{h}s_bps" for h in horizons_sec],
        *[f"past_time_{h}s_bps" for h in horizons_sec],
    ]
    for date in dates:
        raw = load_snapshot_day(paths, date)
        features = compute_snapshot_features(raw, quote_notionals)
        features = add_future_and_past_returns(features, horizons_sec)
        daily_rows.append(summarize_snapshot_day(features, date))
        sample_cols = [col for col in needed_snapshot_cols if col in features.columns]
        sample = features.loc[:, sample_cols]
        if args.max_snapshot_sample_per_day and len(sample) > args.max_snapshot_sample_per_day:
            idx = rng.choice(len(sample), size=args.max_snapshot_sample_per_day, replace=False)
            sample = sample.iloc[np.sort(idx)]
        snapshot_samples.append(sample)

    daily = pd.DataFrame(daily_rows)
    snapshot_sample = pd.concat(snapshot_samples, ignore_index=True)
    snapshot_targets = [f"fwd_time_{h}s_bps" for h in horizons_sec]
    snapshot_scores = score_features(snapshot_sample, SNAPSHOT_FEATURES, snapshot_targets, "snapshot_25")

    event_sample = load_event_panel_sample(
        paths,
        horizons_sec=horizons_sec,
        event_horizons=event_horizons,
        max_per_day=args.max_event_sample_per_day,
        seed=args.seed + 1,
        date_filter=set(dates),
    )
    event_targets = [f"fwd_time_{h}s_bps" for h in horizons_sec] + [f"fwd_event_{h}_bps" for h in event_horizons]
    event_scores = score_features(event_sample, EVENT_FEATURES, event_targets, "event_panel")

    corr = pd.concat(
        [
            correlation_table(snapshot_sample, SNAPSHOT_FEATURES, "snapshot_25"),
            correlation_table(event_sample, EVENT_FEATURES, "event_panel"),
        ],
        ignore_index=True,
    )
    if len(corr):
        corr = corr.sort_values("abs_corr", ascending=False).reset_index(drop=True)

    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "source_run_tag": paths.source_run_tag,
        "snapshot_dates": dates,
        "snapshot_sample_rows": int(len(snapshot_sample)),
        "event_sample_rows": int(len(event_sample)),
        "horizons_sec": horizons_sec,
        "event_horizons": event_horizons,
        "quote_notionals": quote_notionals,
        **aggregate_daily(daily),
        "top_snapshot_rows": snapshot_scores.head(12).to_dict(orient="records"),
        "top_event_rows": event_scores.head(12).to_dict(orient="records"),
    }

    daily.to_csv(paths.snapshot_daily_csv, index=False)
    snapshot_scores.to_csv(paths.snapshot_scorecard_csv, index=False)
    event_scores.to_csv(paths.event_scorecard_csv, index=False)
    corr.to_csv(paths.factor_corr_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, args, daily, snapshot_scores, event_scores, corr, summary)

    print(json.dumps({"run_tag": paths.run_tag, "report": str(paths.report_md), "summary": str(paths.summary_json)}, indent=2))


if __name__ == "__main__":
    main()
