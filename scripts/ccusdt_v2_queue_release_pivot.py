#!/usr/bin/env python
"""CCUSDT V2 queue-release pivot prototype.

Research-only prototype for the structural pivot drafted in
`ccusdt_v2_pivot_queue_release_continuation.yaml`.

Instead of entering before queue movement, this diagnostic waits for observable
top-of-book amount depletion at an unchanged best price:

- ask amount drop at same ask price -> long quote-release candidate;
- bid amount drop at same bid price -> short quote-release candidate.

It then scores short-horizon continuation after a taker-style cost proxy and
state-matched random controls. This is a lightweight book_ticker prototype, not
the final incremental_book_L2 queue-release model.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_queue_release_pivot_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_queue_release_pivot_v1"
US_PER_SECOND = 1_000_000
EPS = 1e-12

FOLDS = [
    ("expanding_fold1", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03"], ["2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"]),
    ("expanding_fold2", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07"], ["2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11"]),
    ("expanding_fold3", ["2026-04-29", "2026-04-30", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08", "2026-05-09", "2026-05-10", "2026-05-11"], ["2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"]),
]


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
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_queue_release_events_{self.run_tag}.csv"

    @property
    def summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_queue_release_summary_{self.run_tag}.csv"

    @property
    def controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_queue_release_controls_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_queue_release_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_queue_release_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-queue-release-pivot-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CCUSDT v2 queue-release pivot prototype.")
    parser.add_argument("--data-root", type=Path, default=Path("data/ccusdt/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--quantiles", default="0.95,0.975,0.99")
    parser.add_argument("--horizons-sec", default="1,5,10")
    parser.add_argument("--fee-stress-bps", type=float, default=2.0)
    parser.add_argument("--entry-bucket-sec", type=int, default=10)
    parser.add_argument("--matched-random-iters", type=int, default=200)
    parser.add_argument(
        "--candidate-prefilter-quantile",
        type=float,
        default=0.0,
        help="Optional release-side drop_frac quantile prefilter for large symbols; 0 disables it.",
    )
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


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 20) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def cvar(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def data_file(root: Path, date: str, symbol: str) -> Path:
    return root / f"dt={date}" / f"{symbol}.csv.gz"


def load_ticker_day(paths: Paths, date: str) -> pd.DataFrame:
    path = data_file(paths.book_ticker_root, date, paths.symbol)
    usecols = ["local_timestamp", "ask_amount", "ask_price", "bid_price", "bid_amount"]
    if not path.exists():
        return pd.DataFrame(columns=usecols)
    with gzip.open(path, "rt", newline="") as handle:
        df = pd.read_csv(handle, usecols=usecols)
    for col in usecols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=usecols).sort_values("local_timestamp").reset_index(drop=True)
    df["symbol"] = paths.symbol
    df["date"] = date
    df["mid_price"] = (df["ask_price"] + df["bid_price"]) / 2.0
    df["spread_bps"] = 10_000.0 * (df["ask_price"] - df["bid_price"]) / np.maximum(df["mid_price"], EPS)
    df["hour_bucket"] = (np.floor(df["local_timestamp"] / (3600 * US_PER_SECOND)).astype("int64") % 24).astype(int)
    return df


def load_all_ticker(paths: Paths) -> pd.DataFrame:
    dates = sorted(path.name.replace("dt=", "") for path in paths.book_ticker_root.glob("dt=*") if path.is_dir())
    parts = [load_ticker_day(paths, date) for date in dates]
    parts = [part for part in parts if not part.empty]
    if not parts:
        raise ValueError(f"no book_ticker files found under {paths.book_ticker_root}")
    out = pd.concat(parts, ignore_index=True)
    out["row_id"] = np.arange(len(out), dtype="int64")
    return out


def build_release_candidates(ticker: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, g in ticker.groupby("date", sort=True):
        ordered = g.sort_values("local_timestamp").reset_index(drop=True)
        prev = ordered.shift(1)
        for side_name, direction, price_col, amount_col in [
            ("ask_release_long", 1, "ask_price", "ask_amount"),
            ("bid_release_short", -1, "bid_price", "bid_amount"),
        ]:
            same_price = np.isclose(ordered[price_col], prev[price_col], rtol=0, atol=1e-12)
            prev_amount = pd.to_numeric(prev[amount_col], errors="coerce")
            amount = pd.to_numeric(ordered[amount_col], errors="coerce")
            drop = prev_amount - amount
            drop_frac = drop / prev_amount.replace(0, np.nan)
            mask = same_price & np.isfinite(drop_frac) & (drop > 0) & (drop_frac > 0)
            sub = ordered.loc[mask, ["row_id", "symbol", "date", "local_timestamp", "mid_price", "spread_bps", "hour_bucket"]].copy()
            if sub.empty:
                continue
            sub["release_side"] = side_name
            sub["direction"] = direction
            sub["drop_base"] = drop.loc[mask].to_numpy(dtype="float64")
            sub["drop_frac"] = drop_frac.loc[mask].to_numpy(dtype="float64")
            sub["queue_amount_after"] = amount.loc[mask].to_numpy(dtype="float64")
            rows.extend(sub.to_dict("records"))
    return pd.DataFrame(rows)


def prefilter_candidates(candidates: pd.DataFrame, quantile: float) -> pd.DataFrame:
    if candidates.empty or quantile <= 0.0:
        return candidates
    q = min(max(float(quantile), 0.0), 1.0)
    frames: list[pd.DataFrame] = []
    for _side, group in candidates.groupby("release_side", sort=False):
        threshold = float(group["drop_frac"].quantile(q))
        frames.append(group[group["drop_frac"] >= threshold].copy())
    return pd.concat(frames, ignore_index=True) if frames else candidates.head(0).copy()


def label_events(candidates: pd.DataFrame, ticker: pd.DataFrame, horizons: list[float], fee_stress_bps: float) -> pd.DataFrame:
    day_arrays: dict[str, dict[str, np.ndarray]] = {}
    for date, g in ticker.groupby("date", sort=True):
        ordered = g.sort_values("local_timestamp")
        day_arrays[str(date)] = {
            "times": ordered["local_timestamp"].to_numpy(dtype="float64"),
            "mids": ordered["mid_price"].to_numpy(dtype="float64"),
            "spreads": ordered["spread_bps"].to_numpy(dtype="float64"),
        }

    frames: list[pd.DataFrame] = []
    for date, events in candidates.groupby("date", sort=True):
        day = day_arrays[str(date)]
        times = day["times"]
        if not len(times) or events.empty:
            continue
        event_times = events["local_timestamp"].to_numpy(dtype="float64")
        entry_idx = np.searchsorted(times, event_times, side="left")
        entry_ok = (entry_idx >= 0) & (entry_idx < len(times))
        if not entry_ok.any():
            continue
        direction = events["direction"].to_numpy(dtype="int64")
        for horizon in horizons:
            exit_idx = np.searchsorted(times, event_times + horizon * US_PER_SECOND, side="left")
            ok = entry_ok & (exit_idx >= 0) & (exit_idx < len(times))
            if not ok.any():
                continue
            entry_mid = np.maximum(day["mids"][entry_idx[ok]], EPS)
            exit_mid = np.maximum(day["mids"][exit_idx[ok]], EPS)
            entry_spread = day["spreads"][entry_idx[ok]]
            exit_spread = day["spreads"][exit_idx[ok]]
            gross = direction[ok] * 10_000.0 * np.log(exit_mid / entry_mid)
            taker_cost = 0.5 * entry_spread + 0.5 * exit_spread + fee_stress_bps
            net = gross - taker_cost
            frame = events.loc[ok, [
                "row_id",
                "symbol",
                "date",
                "local_timestamp",
                "release_side",
                "direction",
                "hour_bucket",
                "drop_base",
                "drop_frac",
                "queue_amount_after",
            ]].copy()
            frame["horizon_sec"] = horizon
            frame["entry_mid"] = entry_mid
            frame["exit_mid"] = exit_mid
            frame["entry_spread_bps"] = entry_spread
            frame["exit_spread_bps"] = exit_spread
            frame["gross_bps"] = gross
            frame["taker_cost_bps"] = taker_cost
            frame["net_bps"] = net
            frame["net_plus2_bps"] = net - 2.0
            frame["entry_bucket"] = (frame["local_timestamp"] // (10 * US_PER_SECOND)).astype("int64")
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def nonoverlap(frame: pd.DataFrame, bucket_sec: int) -> pd.DataFrame:
    out = frame.copy()
    out["entry_bucket"] = (out["local_timestamp"] // (bucket_sec * US_PER_SECOND)).astype("int64")
    return out.sort_values("local_timestamp").drop_duplicates(["date", "release_side", "horizon_sec", "entry_bucket"], keep="first")


def summarize(values: pd.Series | np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype="float64")
    return {
        "net_mean_bps": finite_mean(arr),
        "net_plus2_mean_bps": finite_mean(arr - 2.0),
        "net_median_bps": finite_quantile(arr, 0.50),
        "net_cvar10_bps": cvar(arr, 0.10),
        "gt_2bps_rate": safe_rate(arr > 2.0),
    }


def run_framework(
    labeled: pd.DataFrame,
    quantiles: list[float],
    horizons: list[float],
    matched_random_iters: int,
    seed: int,
    bucket_sec: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    event_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    control_rows: list[dict[str, object]] = []

    for fold_name, train_dates, test_dates in FOLDS:
        train = labeled[labeled["date"].isin(train_dates)]
        test = labeled[labeled["date"].isin(test_dates)]
        if train.empty or test.empty:
            continue
        for release_side in sorted(labeled["release_side"].dropna().unique()):
            side_train = train[train["release_side"].eq(release_side)]
            if side_train.empty:
                continue
            thresholds = {q: float(side_train["drop_frac"].quantile(q)) for q in quantiles}
            for horizon in horizons:
                side_test = test[(test["release_side"].eq(release_side)) & np.isclose(test["horizon_sec"], horizon)].copy()
                if side_test.empty:
                    continue
                for q, threshold in thresholds.items():
                    selected = side_test[side_test["drop_frac"] >= threshold].copy()
                    selected = nonoverlap(selected, bucket_sec)
                    if selected.empty:
                        continue
                    selected["run_tag"] = RUN_TAG
                    selected["guardrail"] = GUARDRAIL
                    selected["fold"] = fold_name
                    selected["threshold_quantile"] = q
                    selected["threshold_drop_frac"] = threshold
                    event_rows.extend(selected.to_dict("records"))

                    stats = summarize(selected["net_bps"])
                    summary = {
                        "run_tag": RUN_TAG,
                        "guardrail": GUARDRAIL,
                        "fold": fold_name,
                        "release_side": release_side,
                        "horizon_sec": horizon,
                        "threshold_quantile": q,
                        "threshold_drop_frac": threshold,
                        "entries": int(len(selected)),
                        **stats,
                    }

                    random_means: list[float] = []
                    control_pool = nonoverlap(side_test, bucket_sec)
                    for _ in range(matched_random_iters):
                        samples: list[pd.DataFrame] = []
                        for (_, hour), g in selected.groupby(["date", "hour_bucket"], sort=False):
                            pool = control_pool[(control_pool["date"].eq(_)) & (control_pool["hour_bucket"].eq(hour))]
                            if pool.empty:
                                continue
                            take = min(len(g), len(pool))
                            samples.append(pool.sample(n=take, replace=len(pool) < len(g), random_state=int(rng.integers(0, 2**31 - 1))))
                        if samples:
                            sampled = pd.concat(samples, ignore_index=True)
                            random_means.append(float(sampled["net_bps"].mean()))
                    random_arr = np.asarray(random_means, dtype="float64")
                    summary["matched_random_mean_p50_bps"] = finite_quantile(random_arr, 0.50)
                    summary["matched_random_mean_p95_bps"] = finite_quantile(random_arr, 0.95)
                    summary["matched_random_prob_ge_signal"] = (
                        safe_rate(random_arr >= summary["net_mean_bps"]) if len(random_arr) else np.nan
                    )
                    summary["signal_minus_random_p50_bps"] = summary["net_mean_bps"] - summary["matched_random_mean_p50_bps"]
                    summary_rows.append(summary)
                    control_rows.append(
                        {
                            "run_tag": RUN_TAG,
                            "guardrail": GUARDRAIL,
                            "fold": fold_name,
                            "release_side": release_side,
                            "horizon_sec": horizon,
                            "threshold_quantile": q,
                            "random_iters": int(len(random_arr)),
                            "signal_mean_bps": summary["net_mean_bps"],
                            "random_mean_p50_bps": summary["matched_random_mean_p50_bps"],
                            "random_mean_p95_bps": summary["matched_random_mean_p95_bps"],
                            "prob_random_ge_signal": summary["matched_random_prob_ge_signal"],
                        }
                    )
    return pd.DataFrame(event_rows), pd.DataFrame(summary_rows), pd.DataFrame(control_rows)


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
    out["pivot_promote_gate"] = (
        out["sample_pass"]
        & out["economics_pass"]
        & out["stress_pass"]
        & out["controls_pass"]
        & out["median_pass"]
        & out["risk_pass"]
    )
    out["queue_release_status"] = np.where(out["pivot_promote_gate"], "queue_release_research_continue", "queue_release_no_go")
    return out.sort_values(
        ["pivot_promote_gate", "net_mean_bps", "signal_minus_random_p50_bps", "entries"],
        ascending=[False, False, False, False],
    )


def write_report(paths: Paths, events: pd.DataFrame, summary: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    lines: list[str] = []
    lines.append("# CCUSDT V2 Queue Release Pivot")
    lines.append("")
    lines.append(f"Status: `{paths.run_tag}`.")
    lines.append("")
    lines.append(f"Guardrail: `{GUARDRAIL}`.")
    lines.append("")
    lines.append("This is a lightweight `book_ticker` prototype for the queue-release continuation pivot. It is not an executable strategy.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Symbol: `{paths.symbol}`.")
    lines.append(f"- Data root: `{paths.data_root}`.")
    lines.append(f"- Event rows: `{len(events)}`.")
    lines.append(f"- Summary rows: `{len(summary)}`.")
    lines.append(f"- Horizons sec: `{args.horizons_sec}`.")
    lines.append(f"- Threshold quantiles: `{args.quantiles}`.")
    lines.append(f"- Candidate prefilter quantile: `{args.candidate_prefilter_quantile}`.")
    lines.append(f"- Fee stress bps: `{args.fee_stress_bps}`.")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    if scores.empty:
        lines.append("_No scorecard rows._")
    else:
        lines.extend(
            markdown_table(
                scores,
                [
                    "fold",
                    "release_side",
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
                    "pivot_promote_gate",
                    "queue_release_status",
                ],
                40,
            )
        )
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    promoted = int(scores["pivot_promote_gate"].sum()) if not scores.empty else 0
    if promoted:
        lines.append("At least one queue-release diagnostic row passed local gates. It still needs full incremental-L2 validation before promotion.")
    else:
        lines.append("No queue-release prototype row passed the combined sample, economics, stress, control, median, and risk gates.")
    lines.append("")
    lines.append("## Output Tables")
    lines.append("")
    for path in [paths.events_csv, paths.summary_csv, paths.controls_csv, paths.scorecard_csv, paths.summary_json]:
        lines.append(f"- `{path}`")
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```powershell")
    lines.append(
        f"python scripts/ccusdt_v2_queue_release_pivot.py --data-root {paths.data_root} --symbol {paths.symbol} "
        f"--run-tag {paths.run_tag} --quantiles \"{args.quantiles}\" --horizons-sec \"{args.horizons_sec}\" "
        f"--fee-stress-bps {args.fee_stress_bps:g} --entry-bucket-sec {args.entry_bucket_sec} "
        f"--matched-random-iters {args.matched_random_iters} "
        f"--candidate-prefilter-quantile {args.candidate_prefilter_quantile:g}"
    )
    lines.append("```")
    lines.append("")
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, events: pd.DataFrame, summary: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(paths.events_csv, index=False)
    summary.to_csv(paths.summary_csv, index=False)
    controls.to_csv(paths.controls_csv, index=False)
    scores.to_csv(paths.scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "symbol": paths.symbol,
        "data_root": str(paths.data_root),
        "event_rows": int(len(events)),
        "summary_rows": int(len(summary)),
        "control_rows": int(len(controls)),
        "scorecard_rows": int(len(scores)),
        "candidate_prefilter_quantile": float(args.candidate_prefilter_quantile),
        "pivot_promote_gate_rows": int(scores["pivot_promote_gate"].sum()) if not scores.empty else 0,
        "outputs": {
            "events_csv": str(paths.events_csv),
            "summary_csv": str(paths.summary_csv),
            "controls_csv": str(paths.controls_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, events, summary, controls, scores, args)


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
    ticker = load_all_ticker(paths)
    candidates = build_release_candidates(ticker)
    candidates = prefilter_candidates(candidates, args.candidate_prefilter_quantile)
    labeled = label_events(candidates, ticker, parse_floats(args.horizons_sec), args.fee_stress_bps)
    events, summary, controls = run_framework(
        labeled,
        parse_floats(args.quantiles),
        parse_floats(args.horizons_sec),
        args.matched_random_iters,
        args.seed,
        args.entry_bucket_sec,
    )
    scores = scorecard(summary)
    write_outputs(paths, events, summary, controls, scores, args)
    print(f"[ccusdt_queue_release] candidates={len(candidates)} events={len(events)} scorecard={len(scores)}", flush=True)
    print(f"[ccusdt_queue_release] promote gate rows={int(scores['pivot_promote_gate'].sum()) if not scores.empty else 0}", flush=True)
    print(f"[ccusdt_queue_release] wrote {paths.report_md}", flush=True)


if __name__ == "__main__":
    main()
