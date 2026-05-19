#!/usr/bin/env python
"""CCUSDT V2 absorption/replenishment reversal pivot.

Research-only diagnostic for a structurally different microstructure entry:
large recent aggressive flow that fails to move price and is met by visible
top-of-book replenishment. The hypothesis is reversal/failed-breakout, not the
previous trade-flow continuation or queue-release continuation family.
"""

from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_absorption_reversal_pivot_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_absorption_reversal_pivot_v1"
US_PER_SECOND = 1_000_000
EPS = 1e-12

FOLDS = [
    ("expanding_fold1", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03"], ["2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"]),
    ("expanding_fold2", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"], ["2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11"]),
    ("expanding_fold3", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11"], ["2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"]),
    ("expanding_fold4_oos", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"], ["2026-05-16"]),
]

ABSORPTION_SPECS = {
    "buy_absorption_short": {
        "pressure_col": "buy_notional_5s",
        "replenish_col": "ask_depth_change_5s_frac",
        "direction": -1,
        "ret_side": "buy",
    },
    "sell_absorption_long": {
        "pressure_col": "sell_notional_5s",
        "replenish_col": "bid_depth_change_5s_frac",
        "direction": 1,
        "ret_side": "sell",
    },
}


@dataclass(frozen=True)
class Paths:
    data_root: Path
    date_dir: Path
    doc_dir: Path
    symbol: str
    run_tag: str

    @property
    def book_ticker_root(self) -> Path:
        return self.data_root / "external" / "bullish_book_ticker" / f"symbol={self.symbol}"

    @property
    def trades_root(self) -> Path:
        return self.data_root / "external" / "bullish_trades" / f"symbol={self.symbol}"

    @property
    def panel_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_absorption_reversal_panel_{self.run_tag}.csv"

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_absorption_reversal_events_{self.run_tag}.csv"

    @property
    def controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_absorption_reversal_controls_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_absorption_reversal_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_absorption_reversal_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-absorption-reversal-pivot-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT V2 absorption/replenishment reversal pivot.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--threshold-quantiles", default="0.95,0.975,0.99")
    parser.add_argument("--horizons-sec", default="1,5,10")
    parser.add_argument("--entry-bucket-sec", type=int, default=10)
    parser.add_argument("--fee-stress-bps", type=float, default=2.0)
    parser.add_argument("--absorption-ret-quantile", type=float, default=0.50)
    parser.add_argument("--max-absorption-ret-bps", type=float, default=1.0)
    parser.add_argument("--matched-random-iters", type=int, default=100)
    parser.add_argument("--min-entries", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260518)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_floats(raw: str) -> list[float]:
    return fill_base.parse_floats(raw)


def finite_mean(values: Iterable[float] | np.ndarray) -> float:
    return fill_base.finite_mean(values)


def finite_quantile(values: Iterable[float] | np.ndarray, q: float) -> float:
    return fill_base.finite_quantile(values, q)


def safe_rate(values: Iterable[bool] | np.ndarray) -> float:
    return fill_base.safe_rate(values)


def fmt_num(value: object, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 40) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def cvar(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def file_path(root: Path, symbol: str, date: str) -> Path:
    return root / f"dt={date}" / f"{symbol}.csv.gz"


def available_dates(paths: Paths) -> list[str]:
    roots = [paths.book_ticker_root, paths.trades_root]
    date_sets: list[set[str]] = []
    for root in roots:
        if not root.exists():
            return []
        date_sets.append({path.name.replace("dt=", "") for path in root.glob("dt=*") if path.is_dir()})
    return sorted(set.intersection(*date_sets))


def load_book_day(paths: Paths, date: str) -> pd.DataFrame:
    path = file_path(paths.book_ticker_root, paths.symbol, date)
    usecols = ["local_timestamp", "ask_amount", "ask_price", "bid_price", "bid_amount"]
    with gzip.open(path, "rt", newline="") as handle:
        df = pd.read_csv(handle, usecols=usecols)
    for col in usecols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=usecols).sort_values("local_timestamp")
    df["second"] = (df["local_timestamp"] // US_PER_SECOND).astype("int64")
    grouped = df.groupby("second", sort=True).agg(
        ask_amount=("ask_amount", "last"),
        ask_price=("ask_price", "last"),
        bid_price=("bid_price", "last"),
        bid_amount=("bid_amount", "last"),
        book_updates=("local_timestamp", "count"),
    )
    full_index = pd.RangeIndex(int(grouped.index.min()), int(grouped.index.max()) + 1, name="second")
    out = grouped.reindex(full_index)
    for col in ["ask_amount", "ask_price", "bid_price", "bid_amount"]:
        out[col] = out[col].ffill()
    out["book_updates"] = out["book_updates"].fillna(0)
    out = out.dropna(subset=["ask_price", "bid_price"]).reset_index()
    out["date"] = date
    out["symbol"] = paths.symbol
    return out


def load_trades_day(paths: Paths, date: str) -> pd.DataFrame:
    path = file_path(paths.trades_root, paths.symbol, date)
    usecols = ["local_timestamp", "side", "price", "amount"]
    with gzip.open(path, "rt", newline="") as handle:
        df = pd.read_csv(handle, usecols=usecols)
    for col in ["local_timestamp", "price", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["local_timestamp", "price", "amount"]).copy()
    df["second"] = (df["local_timestamp"] // US_PER_SECOND).astype("int64")
    df["side"] = df["side"].astype(str).str.lower()
    df["notional"] = df["price"] * df["amount"]
    df["buy_notional"] = np.where(df["side"].eq("buy"), df["notional"], 0.0)
    df["sell_notional"] = np.where(df["side"].eq("sell"), df["notional"], 0.0)
    return df.groupby("second", sort=True).agg(
        trade_count=("notional", "count"),
        trade_notional=("notional", "sum"),
        buy_notional=("buy_notional", "sum"),
        sell_notional=("sell_notional", "sum"),
    ).reset_index()


def build_panel(paths: Paths, horizons: list[float], entry_bucket_sec: int, fee_stress_bps: float) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for date in available_dates(paths):
        book = load_book_day(paths, date)
        trades = load_trades_day(paths, date)
        day = book.merge(trades, on="second", how="left")
        for col in ["trade_count", "trade_notional", "buy_notional", "sell_notional"]:
            day[col] = day[col].fillna(0.0)
        day = day.sort_values("second").reset_index(drop=True)
        day["mid_price"] = (day["ask_price"] + day["bid_price"]) / 2.0
        day["spread_bps"] = 10_000.0 * (day["ask_price"] - day["bid_price"]) / np.maximum(day["mid_price"], EPS)
        day["bid_depth_quote"] = day["bid_price"] * day["bid_amount"]
        day["ask_depth_quote"] = day["ask_price"] * day["ask_amount"]
        depth_sum = day["bid_depth_quote"] + day["ask_depth_quote"]
        day["queue_imbalance"] = (day["bid_depth_quote"] - day["ask_depth_quote"]) / depth_sum.replace(0.0, np.nan)
        day["ret_1s_bps"] = 10_000.0 * np.log(day["mid_price"] / day["mid_price"].shift(1))
        for window in [5, 10]:
            day[f"buy_notional_{window}s"] = day["buy_notional"].rolling(window, min_periods=1).sum()
            day[f"sell_notional_{window}s"] = day["sell_notional"].rolling(window, min_periods=1).sum()
            day[f"trade_notional_{window}s"] = day[f"buy_notional_{window}s"] + day[f"sell_notional_{window}s"]
            day[f"ret_{window}s_bps"] = 10_000.0 * np.log(day["mid_price"] / day["mid_price"].shift(window))
        prev_bid_depth = day["bid_depth_quote"].shift(5)
        prev_ask_depth = day["ask_depth_quote"].shift(5)
        day["bid_depth_change_5s_frac"] = (day["bid_depth_quote"] - prev_bid_depth) / prev_bid_depth.replace(0.0, np.nan)
        day["ask_depth_change_5s_frac"] = (day["ask_depth_quote"] - prev_ask_depth) / prev_ask_depth.replace(0.0, np.nan)
        day["hour_bucket"] = ((day["second"] // 3600).astype("int64") % 24).astype(int)
        day["entry_bucket"] = (day["second"] // entry_bucket_sec).astype("int64")
        day["spread_bin"] = pd.qcut(day["spread_bps"].rank(method="first"), 3, labels=False, duplicates="drop")
        day["activity_bin"] = pd.qcut(day["trade_notional_5s"].rank(method="first"), 3, labels=False, duplicates="drop")
        for horizon in horizons:
            steps = int(round(horizon))
            future_mid = day["mid_price"].shift(-steps)
            future_spread = day["spread_bps"].shift(-steps)
            gross_long = 10_000.0 * np.log(future_mid / day["mid_price"])
            cost = 0.5 * day["spread_bps"] + 0.5 * future_spread + fee_stress_bps
            day[f"gross_long_{steps}s_bps"] = gross_long
            day[f"cost_{steps}s_bps"] = cost
            day[f"net_long_{steps}s_bps"] = gross_long - cost
            day[f"net_short_{steps}s_bps"] = -gross_long - cost
        frames.append(day)
    if not frames:
        raise ValueError(f"no usable {paths.symbol} book_ticker/trades dates under {paths.data_root}")
    panel = pd.concat(frames, ignore_index=True)
    panel["row_id"] = np.arange(len(panel), dtype="int64")
    return panel


def nonoverlap(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return frame.sort_values("second").drop_duplicates(keys, keep="first")


def summarize(values: pd.Series | np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype="float64")
    return {
        "net_mean_bps": finite_mean(arr),
        "net_plus2_mean_bps": finite_mean(arr - 2.0),
        "net_median_bps": finite_quantile(arr, 0.50),
        "net_cvar10_bps": cvar(arr, 0.10),
        "gt_2bps_rate": safe_rate(arr > 2.0),
    }


def control_distribution(
    selected: pd.DataFrame,
    pool: pd.DataFrame,
    horizon: int,
    iters: int,
    rng: np.random.Generator,
) -> list[float]:
    samples: list[float] = []
    match_cols = ["date", "hour_bucket", "spread_bin", "activity_bin", "direction"]
    pool = pool.dropna(subset=["spread_bin", "activity_bin"])
    selected = selected.dropna(subset=["spread_bin", "activity_bin"])
    if pool.empty or selected.empty:
        return samples
    pool_groups = {key: group for key, group in pool.groupby(match_cols, sort=False)}
    selected_groups = list(selected.groupby(match_cols, sort=False))
    for _ in range(iters):
        parts: list[pd.Series] = []
        for key, group in selected_groups:
            candidates = pool_groups.get(key)
            if candidates is None or candidates.empty:
                continue
            take = len(group)
            sampled = candidates.sample(
                n=take,
                replace=len(candidates) < take,
                random_state=int(rng.integers(0, 2**31 - 1)),
            )
            net_col = f"net_long_{horizon}s_bps" if int(key[-1]) > 0 else f"net_short_{horizon}s_bps"
            parts.append(sampled[net_col])
        if parts:
            samples.append(float(pd.concat(parts, ignore_index=True).mean()))
    return samples


def absorption_mask(frame: pd.DataFrame, trigger: str, pressure_threshold: float, weak_ret_threshold: float) -> pd.Series:
    spec = ABSORPTION_SPECS[trigger]
    pressure = pd.to_numeric(frame[spec["pressure_col"]], errors="coerce")
    replenish = pd.to_numeric(frame[spec["replenish_col"]], errors="coerce")
    ret_1s = pd.to_numeric(frame["ret_1s_bps"], errors="coerce")
    base = pressure >= pressure_threshold
    if spec["ret_side"] == "buy":
        weak_move = ret_1s <= weak_ret_threshold
    else:
        weak_move = ret_1s >= -weak_ret_threshold
    return base & weak_move & (replenish >= 0.0)


def run_framework(
    panel: pd.DataFrame,
    thresholds: list[float],
    horizons: list[float],
    matched_random_iters: int,
    absorption_ret_quantile: float,
    max_absorption_ret_bps: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    event_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    control_rows: list[dict[str, object]] = []
    horizons_i = [int(round(item)) for item in horizons]
    for fold, train_dates, test_dates in FOLDS:
        train = panel[panel["date"].isin(train_dates)].copy()
        test = panel[panel["date"].isin(test_dates)].copy()
        if train.empty or test.empty:
            continue
        for trigger, spec in ABSORPTION_SPECS.items():
            train_pressure = pd.to_numeric(train[spec["pressure_col"]], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            train_pressure = train_pressure[train_pressure > 0.0]
            if train_pressure.empty:
                continue
            for q in thresholds:
                pressure_threshold = float(train_pressure.quantile(q))
                pressured_train = train[pd.to_numeric(train[spec["pressure_col"]], errors="coerce") >= pressure_threshold]
                weak_ret_values = pd.to_numeric(pressured_train["ret_1s_bps"], errors="coerce").abs().replace([np.inf, -np.inf], np.nan).dropna()
                if weak_ret_values.empty:
                    continue
                weak_ret_threshold = min(float(max_absorption_ret_bps), float(weak_ret_values.quantile(absorption_ret_quantile)))
                base = test[absorption_mask(test, trigger, pressure_threshold, weak_ret_threshold)].copy()
                if base.empty:
                    continue
                base["trigger_class"] = trigger
                base["direction"] = int(spec["direction"])
                base["pressure_threshold"] = pressure_threshold
                base["weak_ret_threshold_bps"] = weak_ret_threshold
                base["pressure_value"] = pd.to_numeric(base[spec["pressure_col"]], errors="coerce")
                base["replenish_value"] = pd.to_numeric(base[spec["replenish_col"]], errors="coerce")
                for horizon in horizons_i:
                    if f"net_long_{horizon}s_bps" not in base:
                        continue
                    work = base.dropna(subset=[f"net_long_{horizon}s_bps", f"net_short_{horizon}s_bps"]).copy()
                    if work.empty:
                        continue
                    work["net_bps"] = np.where(
                        work["direction"] > 0,
                        work[f"net_long_{horizon}s_bps"],
                        work[f"net_short_{horizon}s_bps"],
                    )
                    work["gross_bps"] = np.where(
                        work["direction"] > 0,
                        work[f"gross_long_{horizon}s_bps"],
                        -work[f"gross_long_{horizon}s_bps"],
                    )
                    work["cost_bps"] = work[f"cost_{horizon}s_bps"]
                    selected = nonoverlap(work, ["date", "trigger_class", "direction", "entry_bucket"])
                    selected["fold"] = fold
                    selected["threshold_quantile"] = q
                    selected["horizon_sec"] = horizon
                    selected["run_tag"] = RUN_TAG
                    selected["guardrail"] = GUARDRAIL
                    event_rows.append(
                        selected[
                            [
                                "run_tag",
                                "guardrail",
                                "symbol",
                                "fold",
                                "date",
                                "row_id",
                                "second",
                                "trigger_class",
                                "direction",
                                "threshold_quantile",
                                "pressure_threshold",
                                "weak_ret_threshold_bps",
                                "horizon_sec",
                                "spread_bps",
                                "queue_imbalance",
                                "pressure_value",
                                "replenish_value",
                                "ret_1s_bps",
                                "gross_bps",
                                "cost_bps",
                                "net_bps",
                            ]
                        ].copy()
                    )
                    stats = summarize(selected["net_bps"])
                    stats["gross_mean_bps"] = finite_mean(selected["gross_bps"])
                    stats["cost_mean_bps"] = finite_mean(selected["cost_bps"])
                    pool = test.dropna(subset=[f"net_long_{horizon}s_bps", f"net_short_{horizon}s_bps"]).copy()
                    pool_frames: list[pd.DataFrame] = []
                    for direction in [-1, 1]:
                        tmp = pool.copy()
                        tmp["direction"] = direction
                        pool_frames.append(tmp)
                    control_pool = pd.concat(pool_frames, ignore_index=True)
                    random_means = control_distribution(selected, control_pool, horizon, matched_random_iters, rng)
                    random_arr = np.asarray(random_means, dtype="float64")
                    summary = {
                        "run_tag": RUN_TAG,
                        "guardrail": GUARDRAIL,
                        "fold": fold,
                        "trigger_class": trigger,
                        "horizon_sec": horizon,
                        "threshold_quantile": q,
                        "pressure_threshold": pressure_threshold,
                        "weak_ret_threshold_bps": weak_ret_threshold,
                        "entries": int(len(selected)),
                        **stats,
                        "matched_random_iters": int(len(random_arr)),
                        "matched_random_mean_p50_bps": finite_quantile(random_arr, 0.50),
                        "matched_random_mean_p95_bps": finite_quantile(random_arr, 0.95),
                        "matched_random_prob_ge_signal": safe_rate(random_arr >= stats["net_mean_bps"]) if len(random_arr) else np.nan,
                    }
                    summary["signal_minus_random_p50_bps"] = summary["net_mean_bps"] - summary["matched_random_mean_p50_bps"]
                    summary_rows.append(summary)
                    control_rows.append(
                        {
                            "run_tag": RUN_TAG,
                            "guardrail": GUARDRAIL,
                            "fold": fold,
                            "trigger_class": trigger,
                            "horizon_sec": horizon,
                            "threshold_quantile": q,
                            "random_iters": int(len(random_arr)),
                            "signal_mean_bps": summary["net_mean_bps"],
                            "random_mean_p50_bps": summary["matched_random_mean_p50_bps"],
                            "random_mean_p95_bps": summary["matched_random_mean_p95_bps"],
                            "prob_random_ge_signal": summary["matched_random_prob_ge_signal"],
                        }
                    )
    events = pd.concat(event_rows, ignore_index=True) if event_rows else pd.DataFrame()
    return events, pd.DataFrame(summary_rows), pd.DataFrame(control_rows)


def scorecard(summary: pd.DataFrame, min_entries: int) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    out = summary.copy()
    out["sample_pass"] = out["entries"] >= int(min_entries)
    out["economics_pass"] = out["net_mean_bps"] > 2.0
    out["stress_pass"] = out["net_plus2_mean_bps"] > 0.0
    out["controls_pass"] = (out["matched_random_prob_ge_signal"] < 0.05) & (out["signal_minus_random_p50_bps"] > 2.0)
    out["median_pass"] = out["net_median_bps"] >= 0.0
    out["risk_pass"] = out["net_cvar10_bps"] > -20.0
    out["absorption_promote_gate"] = (
        out["sample_pass"]
        & out["economics_pass"]
        & out["stress_pass"]
        & out["controls_pass"]
        & out["median_pass"]
        & out["risk_pass"]
    )
    out["absorption_status"] = np.where(out["absorption_promote_gate"], "absorption_research_continue", "absorption_no_go")
    return out.sort_values(
        ["absorption_promote_gate", "net_mean_bps", "signal_minus_random_p50_bps", "entries"],
        ascending=[False, False, False, False],
    )


def write_report(paths: Paths, panel: pd.DataFrame, events: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    promoted = int(scores["absorption_promote_gate"].sum()) if not scores.empty else 0
    lines: list[str] = [
        "# CCUSDT V2 Absorption/Replenishment Reversal Pivot",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This is a structurally new entry diagnostic: large aggressive flow that fails to move price and is met by visible top-of-book replenishment. It is not an execution recommendation and does not replace L2 queue/fill validation.",
        "",
        "## Scope",
        "",
        f"- Symbol: `{paths.symbol}`.",
        f"- Data root: `{paths.data_root}`.",
        f"- Panel rows: `{len(panel)}`.",
        f"- Event rows: `{len(events)}`.",
        f"- Scorecard rows: `{len(scores)}`.",
        f"- Threshold quantiles: `{args.threshold_quantiles}`.",
        f"- Horizons sec: `{args.horizons_sec}`.",
        f"- Fee stress bps: `{args.fee_stress_bps}`.",
        f"- Absorption ret quantile: `{args.absorption_ret_quantile}`.",
        f"- Max absorption ret bps: `{args.max_absorption_ret_bps}`.",
        f"- Matched-random iters: `{args.matched_random_iters}`.",
        f"- Min entries: `{args.min_entries}`.",
        "",
        "## Decision",
        "",
        f"Promote-gate rows: `{promoted}`.",
        "",
    ]
    if promoted:
        lines.append("At least one absorption diagnostic row passed local research gates. It still requires practical maker/taker and L2 queue execution validation.")
    else:
        lines.append("No absorption/replenishment row passed the combined sample, economics, stress, matched-control, median, and risk gates.")
    lines.extend(
        [
            "",
            "## Scorecard",
            "",
            *markdown_table(
                scores,
                [
                    "fold",
                    "trigger_class",
                    "horizon_sec",
                    "threshold_quantile",
                    "entries",
                    "gross_mean_bps",
                    "cost_mean_bps",
                    "net_mean_bps",
                    "net_plus2_mean_bps",
                    "net_median_bps",
                    "matched_random_prob_ge_signal",
                    "signal_minus_random_p50_bps",
                    "sample_pass",
                    "economics_pass",
                    "controls_pass",
                    "absorption_promote_gate",
                    "absorption_status",
                ],
                50,
            ),
            "",
            "## Output Tables",
            "",
            f"- `{paths.panel_csv}`",
            f"- `{paths.events_csv}`",
            f"- `{paths.controls_csv}`",
            f"- `{paths.scorecard_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            f"python scripts/ccusdt_v2_absorption_reversal_pivot.py --data-root {paths.data_root} --symbol {paths.symbol} --run-tag {paths.run_tag} --threshold-quantiles \"{args.threshold_quantiles}\" --horizons-sec \"{args.horizons_sec}\" --fee-stress-bps {args.fee_stress_bps:g} --entry-bucket-sec {args.entry_bucket_sec} --absorption-ret-quantile {args.absorption_ret_quantile:g} --max-absorption-ret-bps {args.max_absorption_ret_bps:g} --matched-random-iters {args.matched_random_iters} --min-entries {args.min_entries}",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, panel: pd.DataFrame, events: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(paths.panel_csv, index=False)
    events.to_csv(paths.events_csv, index=False)
    controls.to_csv(paths.controls_csv, index=False)
    scores.to_csv(paths.scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "symbol": paths.symbol,
        "data_root": str(paths.data_root),
        "panel_rows": int(len(panel)),
        "event_rows": int(len(events)),
        "control_rows": int(len(controls)),
        "scorecard_rows": int(len(scores)),
        "promote_gate_rows": int(scores["absorption_promote_gate"].sum()) if not scores.empty else 0,
        "outputs": {
            "panel_csv": str(paths.panel_csv),
            "events_csv": str(paths.events_csv),
            "controls_csv": str(paths.controls_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, panel, events, controls, scores, args)


def main() -> None:
    args = parse_args()
    global RUN_TAG
    RUN_TAG = args.run_tag
    paths = Paths(
        data_root=resolve_repo_path(args.data_root),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        symbol=args.symbol.upper(),
        run_tag=args.run_tag,
    )
    horizons = parse_floats(args.horizons_sec)
    panel = build_panel(paths, horizons, args.entry_bucket_sec, args.fee_stress_bps)
    events, summary, controls = run_framework(
        panel,
        parse_floats(args.threshold_quantiles),
        horizons,
        args.matched_random_iters,
        args.absorption_ret_quantile,
        args.max_absorption_ret_bps,
        args.seed,
    )
    scores = scorecard(summary, args.min_entries)
    write_outputs(paths, panel, events, controls, scores, args)
    print(
        "[ccusdt_absorption_reversal] "
        f"symbol={paths.symbol} panel={len(panel)} events={len(events)} scorecard={len(scores)} "
        f"promote={int(scores['absorption_promote_gate'].sum()) if not scores.empty else 0}",
        flush=True,
    )
    print(f"[ccusdt_absorption_reversal] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
