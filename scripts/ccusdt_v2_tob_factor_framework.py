#!/usr/bin/env python
"""Symbol-parameterized top-of-book factor framework for the CCUSDT V2 pivot.

This is a lightweight continuation after the universe liquidity-envelope
screen. It does not use incremental L2 or claim execution readiness. It checks
whether a symbol that passes a small-notional top-of-book capacity screen has
any short-horizon signal family worth upgrading to a heavier L2 queue model.
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


GUARDRAIL = "research_only_tob_factor_framework_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_tob_factor_framework_v1"
US_PER_SECOND = 1_000_000
EPS = 1e-12

FOLDS = [
    ("expanding_fold1", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03"], ["2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"]),
    ("expanding_fold2", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"], ["2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11"]),
    ("expanding_fold3", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11"], ["2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"]),
]

FEATURE_SPECS = {
    "microprice_follow": "microprice_dev_bps",
    "obi_follow": "queue_imbalance",
    "trade_flow_follow_5s": "trade_flow_imbalance_5s",
    "trade_flow_follow_10s": "trade_flow_imbalance_10s",
    "ret_reversal_5s": "ret_reversal_5s",
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
        return self.date_dir / f"ccusdt_v2_tob_factor_panel_{self.run_tag}.csv"

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_events_{self.run_tag}.csv"

    @property
    def controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_controls_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_tob_factor_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-tob-factor-framework-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run symbol top-of-book short-horizon factor framework.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt_universe/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--symbol", default="BTCUSDC")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--threshold-quantiles", default="0.95,0.99")
    parser.add_argument("--horizons-sec", default="1,5,10")
    parser.add_argument("--entry-bucket-sec", type=int, default=10)
    parser.add_argument("--fee-stress-bps", type=float, default=2.0)
    parser.add_argument("--matched-random-iters", type=int, default=100)
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


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
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
        micro = (day["ask_price"] * day["bid_amount"] + day["bid_price"] * day["ask_amount"]) / (
            day["bid_amount"] + day["ask_amount"]
        ).replace(0.0, np.nan)
        day["microprice_dev_bps"] = 10_000.0 * (micro - day["mid_price"]) / np.maximum(day["mid_price"], EPS)
        for window in [1, 5, 10]:
            buy = day["buy_notional"].rolling(window, min_periods=1).sum()
            sell = day["sell_notional"].rolling(window, min_periods=1).sum()
            total = buy + sell
            day[f"trade_flow_imbalance_{window}s"] = (buy - sell) / total.replace(0.0, np.nan)
            day[f"trade_notional_{window}s"] = total
            day[f"ret_{window}s_bps"] = 10_000.0 * np.log(day["mid_price"] / day["mid_price"].shift(window))
        day["ret_reversal_5s"] = -day["ret_5s_bps"]
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


def run_framework(
    panel: pd.DataFrame,
    thresholds: list[float],
    horizons: list[float],
    bucket_sec: int,
    matched_random_iters: int,
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
        for trigger, feature in FEATURE_SPECS.items():
            train_values = pd.to_numeric(train[feature], errors="coerce").abs().replace([np.inf, -np.inf], np.nan).dropna()
            if train_values.empty:
                continue
            for q in thresholds:
                threshold = float(train_values.quantile(q))
                base = test[np.isfinite(pd.to_numeric(test[feature], errors="coerce"))].copy()
                base["feature_value"] = pd.to_numeric(base[feature], errors="coerce")
                base["direction"] = np.sign(base["feature_value"]).astype("int64")
                base = base[(base["direction"] != 0) & (base["feature_value"].abs() >= threshold)].copy()
                if base.empty:
                    continue
                for horizon in horizons_i:
                    net_col = f"net_long_{horizon}s_bps"
                    if net_col not in base:
                        continue
                    work = base.dropna(subset=[f"net_long_{horizon}s_bps", f"net_short_{horizon}s_bps"]).copy()
                    if work.empty:
                        continue
                    work["net_bps"] = np.where(
                        work["direction"] > 0,
                        work[f"net_long_{horizon}s_bps"],
                        work[f"net_short_{horizon}s_bps"],
                    )
                    selected = nonoverlap(work, ["date", "trigger_class", "direction", "entry_bucket"]) if "trigger_class" in work else nonoverlap(work, ["date", "direction", "entry_bucket"])
                    selected["trigger_class"] = trigger
                    selected["fold"] = fold
                    selected["threshold_quantile"] = q
                    selected["threshold_value"] = threshold
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
                                "feature_value",
                                "direction",
                                "threshold_quantile",
                                "threshold_value",
                                "horizon_sec",
                                "spread_bps",
                                "queue_imbalance",
                                "microprice_dev_bps",
                                "trade_flow_imbalance_5s",
                                "trade_flow_imbalance_10s",
                                "net_bps",
                            ]
                        ].copy()
                    )
                    stats = summarize(selected["net_bps"])
                    pool = test.dropna(subset=[f"net_long_{horizon}s_bps", f"net_short_{horizon}s_bps"]).copy()
                    pool["direction"] = selected["direction"].mode().iloc[0]
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
                        "threshold_value": threshold,
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


def scorecard(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    out = summary.copy()
    out["sample_pass"] = out["entries"] >= 300
    out["economics_pass"] = out["net_mean_bps"] > 2.0
    out["stress_pass"] = out["net_plus2_mean_bps"] > 0.0
    out["controls_pass"] = (out["matched_random_prob_ge_signal"] < 0.05) & (out["signal_minus_random_p50_bps"] > 2.0)
    out["median_pass"] = out["net_median_bps"] >= 0.0
    out["risk_pass"] = out["net_cvar10_bps"] > -20.0
    out["tob_factor_promote_gate"] = (
        out["sample_pass"]
        & out["economics_pass"]
        & out["stress_pass"]
        & out["controls_pass"]
        & out["median_pass"]
        & out["risk_pass"]
    )
    out["tob_factor_status"] = np.where(out["tob_factor_promote_gate"], "tob_factor_research_continue", "tob_factor_no_go")
    return out.sort_values(
        ["tob_factor_promote_gate", "net_mean_bps", "signal_minus_random_p50_bps", "entries"],
        ascending=[False, False, False, False],
    )


def write_report(paths: Paths, panel: pd.DataFrame, events: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    promoted = int(scores["tob_factor_promote_gate"].sum()) if not scores.empty else 0
    lines: list[str] = [
        "# CCUSDT V2 Top-Of-Book Factor Framework",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This is a symbol-parameterized top-of-book diagnostic. It is not an executable strategy and does not replace incremental-L2 queue validation.",
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
        f"- Matched-random iters: `{args.matched_random_iters}`.",
        "",
        "## Decision",
        "",
        f"Promote-gate rows: `{promoted}`.",
        "",
    ]
    if promoted:
        lines.append("At least one top-of-book diagnostic row passed local gates. It still requires full queue/execution validation.")
    else:
        lines.append("No top-of-book factor row passed the combined sample, economics, stress, matched-control, median, and risk gates.")
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
                    "net_mean_bps",
                    "net_plus2_mean_bps",
                    "net_median_bps",
                    "matched_random_prob_ge_signal",
                    "signal_minus_random_p50_bps",
                    "sample_pass",
                    "economics_pass",
                    "controls_pass",
                    "tob_factor_promote_gate",
                    "tob_factor_status",
                ],
                40,
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
            f"python scripts/ccusdt_v2_tob_factor_framework.py --data-root {paths.data_root} --symbol {paths.symbol} --run-tag {paths.run_tag} --threshold-quantiles \"{args.threshold_quantiles}\" --horizons-sec \"{args.horizons_sec}\" --fee-stress-bps {args.fee_stress_bps:g} --entry-bucket-sec {args.entry_bucket_sec} --matched-random-iters {args.matched_random_iters}",
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
        "promote_gate_rows": int(scores["tob_factor_promote_gate"].sum()) if not scores.empty else 0,
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
    events, _summary, controls = run_framework(
        panel,
        parse_floats(args.threshold_quantiles),
        horizons,
        args.entry_bucket_sec,
        args.matched_random_iters,
        args.seed,
    )
    scores = scorecard(_summary)
    write_outputs(paths, panel, events, controls, scores, args)
    print(
        "[ccusdt_tob_factor_framework] "
        f"symbol={paths.symbol} panel={len(panel)} events={len(events)} scorecard={len(scores)} "
        f"promote={int(scores['tob_factor_promote_gate'].sum()) if not scores.empty else 0}",
        flush=True,
    )
    print(f"[ccusdt_tob_factor_framework] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
