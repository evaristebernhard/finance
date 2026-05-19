#!/usr/bin/env python
"""Cross-market lead/lag pivot for the CCUSDT V2 research framework.

This is a research-only structural pivot. It treats CCUSDT as a follower and
tests whether already-downloaded Bullish top-of-book/trade data from larger
symbols leads short-horizon CCUSDT movement after taker-style cost stress.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base
import ccusdt_v2_tob_factor_framework as tob_base


GUARDRAIL = "research_only_cross_market_lead_lag_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v2_cross_market_lead_lag_v1"
EPS = 1e-12

FEATURE_SPECS = {
    "leader_ret_1s_follow": "leader_ret_1s_bps",
    "leader_ret_5s_follow": "leader_ret_5s_bps",
    "leader_trade_flow_5s_follow": "leader_trade_flow_imbalance_5s",
    "leader_microprice_follow": "leader_microprice_dev_bps",
    "lag_residual_5s_follow": "leader_minus_target_ret_5s_bps",
}


@dataclass(frozen=True)
class Paths:
    target_data_root: Path
    leader_data_root: Path
    date_dir: Path
    doc_dir: Path
    target_symbol: str
    run_tag: str

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_cross_market_events_{self.run_tag}.csv"

    @property
    def controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_cross_market_controls_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v2_cross_market_scorecard_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v2_cross_market_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v2-cross-market-lead-lag-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a CCUSDT cross-market lead/lag pivot.")
    parser.add_argument("--target-data-root", type=Path, default=Path("data/ccusdt/v1"))
    parser.add_argument("--leader-data-root", type=Path, default=Path("data/ccusdt_universe/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--target-symbol", default="CCUSDT")
    parser.add_argument("--leaders", default="BTCUSDC,ETHUSDC,SOLUSDC")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--threshold-quantiles", default="0.99")
    parser.add_argument("--horizons-sec", default="1,5,10")
    parser.add_argument("--entry-bucket-sec", type=int, default=10)
    parser.add_argument("--fee-stress-bps", type=float, default=2.0)
    parser.add_argument("--matched-random-iters", type=int, default=50)
    parser.add_argument("--control-selected-cap", type=int, default=2000)
    parser.add_argument("--control-pool-cap", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20260518)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


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


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 35) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def cvar(values: Iterable[float] | np.ndarray, q: float = 0.10) -> float:
    arr = np.asarray(values, dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, q))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def qbin(values: pd.Series, bins: int = 3) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    ranked = numeric.rank(method="first")
    try:
        return pd.qcut(ranked, bins, labels=False, duplicates="drop")
    except ValueError:
        return pd.Series(np.nan, index=values.index)


def summarize(values: pd.Series | np.ndarray) -> dict[str, float]:
    arr = np.asarray(values, dtype="float64")
    return {
        "net_mean_bps": finite_mean(arr),
        "net_plus2_mean_bps": finite_mean(arr - 2.0),
        "net_median_bps": finite_quantile(arr, 0.50),
        "net_cvar10_bps": cvar(arr, 0.10),
        "gt_2bps_rate": safe_rate(arr > 2.0),
    }


def build_symbol_panel(data_root: Path, date_dir: Path, doc_dir: Path, symbol: str, horizons: list[float], entry_bucket_sec: int, fee_stress_bps: float) -> pd.DataFrame:
    paths = tob_base.Paths(
        data_root=data_root,
        date_dir=date_dir,
        doc_dir=doc_dir,
        symbol=symbol,
        run_tag=f"{RUN_TAG}_{symbol.lower()}_scratch",
    )
    return tob_base.build_panel(paths, horizons, entry_bucket_sec, fee_stress_bps)


def add_target_decomposition(panel: pd.DataFrame, horizons: list[int], fee_stress_bps: float) -> pd.DataFrame:
    out = panel.sort_values(["date", "second"]).copy()
    for horizon in horizons:
        future_mid = out.groupby("date", sort=False)["mid_price"].shift(-horizon)
        future_spread = out.groupby("date", sort=False)["spread_bps"].shift(-horizon)
        gross_long = 10_000.0 * np.log(np.maximum(future_mid, EPS) / np.maximum(out["mid_price"], EPS))
        cost = 0.5 * out["spread_bps"] + 0.5 * future_spread + fee_stress_bps
        out[f"gross_long_{horizon}s_bps"] = gross_long
        out[f"gross_short_{horizon}s_bps"] = -gross_long
        out[f"cost_{horizon}s_bps"] = cost
    return out


def leader_feature_frame(leader_panel: pd.DataFrame, leader_symbol: str) -> pd.DataFrame:
    cols = [
        "date",
        "second",
        "mid_price",
        "ret_1s_bps",
        "ret_5s_bps",
        "microprice_dev_bps",
        "trade_flow_imbalance_5s",
        "trade_notional_5s",
    ]
    out = leader_panel.loc[:, [col for col in cols if col in leader_panel.columns]].copy()
    out = out.rename(
        columns={
            "mid_price": "leader_mid_price",
            "ret_1s_bps": "leader_ret_1s_bps",
            "ret_5s_bps": "leader_ret_5s_bps",
            "microprice_dev_bps": "leader_microprice_dev_bps",
            "trade_flow_imbalance_5s": "leader_trade_flow_imbalance_5s",
            "trade_notional_5s": "leader_trade_notional_5s",
        }
    )
    out["leader_symbol"] = leader_symbol
    return out


def pair_panel(target: pd.DataFrame, leader: pd.DataFrame, leader_symbol: str) -> pd.DataFrame:
    target_cols = [
        "date",
        "second",
        "row_id",
        "symbol",
        "mid_price",
        "spread_bps",
        "spread_bin",
        "hour_bucket",
        "entry_bucket",
        "activity_bin",
        "ret_1s_bps",
        "ret_5s_bps",
    ]
    target_cols.extend([col for col in target.columns if col.startswith(("net_long_", "net_short_", "gross_long_", "gross_short_", "cost_"))])
    left = target.loc[:, list(dict.fromkeys(target_cols))].copy()
    left = left.rename(
        columns={
            "symbol": "target_symbol",
            "mid_price": "target_mid_price",
            "ret_1s_bps": "target_ret_1s_bps",
            "ret_5s_bps": "target_ret_5s_bps",
        }
    )
    merged = left.merge(leader_feature_frame(leader, leader_symbol), on=["date", "second"], how="inner")
    merged["leader_minus_target_ret_1s_bps"] = merged["leader_ret_1s_bps"] - merged["target_ret_1s_bps"]
    merged["leader_minus_target_ret_5s_bps"] = merged["leader_ret_5s_bps"] - merged["target_ret_5s_bps"]
    merged["target_ret_5s_bin"] = qbin(merged["target_ret_5s_bps"])
    merged["leader_activity_bin"] = qbin(merged["leader_trade_notional_5s"])
    merged["leader_vol_bin"] = qbin(merged["leader_ret_5s_bps"].abs())
    return merged


def nonoverlap(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values("second").drop_duplicates(["date", "leader_symbol", "trigger_class", "direction", "entry_bucket"], keep="first")


def control_distribution(
    selected: pd.DataFrame,
    pool: pd.DataFrame,
    horizon: int,
    iters: int,
    rng: np.random.Generator,
    selected_cap: int,
    pool_cap: int,
) -> list[float]:
    match_cols = ["date", "hour_bucket", "spread_bin", "target_ret_5s_bin", "leader_activity_bin", "direction"]
    selected = selected.dropna(subset=match_cols)
    pool = pool.dropna(subset=match_cols)
    if selected.empty or pool.empty:
        return []
    if selected_cap > 0 and len(selected) > selected_cap:
        selected = selected.sample(n=selected_cap, random_state=int(rng.integers(0, 2**31 - 1)))
    if pool_cap > 0 and len(pool) > pool_cap:
        pool = pool.sample(n=pool_cap, random_state=int(rng.integers(0, 2**31 - 1)))
    pool_groups = {key: group for key, group in pool.groupby(match_cols, sort=False)}
    selected_groups = list(selected.groupby(match_cols, sort=False))
    samples: list[float] = []
    for _ in range(iters):
        parts: list[pd.Series] = []
        for key, group in selected_groups:
            candidates = pool_groups.get(key)
            if candidates is None or candidates.empty:
                continue
            sampled = candidates.sample(
                n=len(group),
                replace=len(candidates) < len(group),
                random_state=int(rng.integers(0, 2**31 - 1)),
            )
            net_col = f"net_long_{horizon}s_bps" if int(key[-1]) > 0 else f"net_short_{horizon}s_bps"
            parts.append(sampled[net_col])
        if parts:
            samples.append(float(pd.concat(parts, ignore_index=True).mean()))
    return samples


def scorecard(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    out = summary.copy()
    out["sample_pass"] = out["entries"] >= 100
    out["economics_pass"] = out["net_mean_bps"] > 2.0
    out["stress_pass"] = out["net_plus2_mean_bps"] > 0.0
    out["controls_pass"] = (
        (out["matched_random_prob_ge_signal"] < 0.05)
        & (out["signal_minus_random_p50_bps"] > 2.0)
        & (out["signal_minus_reversed_bps"] > 2.0)
    )
    out["median_pass"] = out["net_median_bps"] >= 0.0
    out["risk_pass"] = out["net_cvar10_bps"] > -20.0
    out["cross_market_promote_gate"] = (
        out["sample_pass"]
        & out["economics_pass"]
        & out["stress_pass"]
        & out["controls_pass"]
        & out["median_pass"]
        & out["risk_pass"]
    )
    out["cross_market_status"] = np.where(out["cross_market_promote_gate"], "cross_market_research_continue", "cross_market_no_go")
    return out.sort_values(
        ["cross_market_promote_gate", "net_mean_bps", "signal_minus_random_p50_bps", "entries"],
        ascending=[False, False, False, False],
    )


def run_pair(
    panel: pd.DataFrame,
    thresholds: list[float],
    horizons: list[int],
    matched_random_iters: int,
    control_selected_cap: int,
    control_pool_cap: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    event_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    control_rows: list[dict[str, object]] = []
    for fold, train_dates, test_dates in tob_base.FOLDS:
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
                base["trigger_class"] = trigger
                base["feature_value"] = pd.to_numeric(base[feature], errors="coerce")
                base["direction"] = np.sign(base["feature_value"]).astype("int64")
                base = base[(base["direction"] != 0) & (base["feature_value"].abs() >= threshold)].copy()
                if base.empty:
                    continue
                for horizon in horizons:
                    required_cols = [f"net_long_{horizon}s_bps", f"net_short_{horizon}s_bps", f"cost_{horizon}s_bps"]
                    if any(col not in base.columns for col in required_cols):
                        continue
                    work = base.dropna(subset=required_cols).copy()
                    if work.empty:
                        continue
                    work["net_bps"] = np.where(
                        work["direction"] > 0,
                        work[f"net_long_{horizon}s_bps"],
                        work[f"net_short_{horizon}s_bps"],
                    )
                    work["reversed_net_bps"] = np.where(
                        work["direction"] > 0,
                        work[f"net_short_{horizon}s_bps"],
                        work[f"net_long_{horizon}s_bps"],
                    )
                    work["gross_bps"] = np.where(
                        work["direction"] > 0,
                        work[f"gross_long_{horizon}s_bps"],
                        work[f"gross_short_{horizon}s_bps"],
                    )
                    work["cost_bps"] = work[f"cost_{horizon}s_bps"]
                    selected = nonoverlap(work)
                    selected["fold"] = fold
                    selected["threshold_quantile"] = q
                    selected["threshold_value"] = threshold
                    selected["horizon_sec"] = horizon
                    selected["run_tag"] = RUN_TAG
                    selected["guardrail"] = GUARDRAIL
                    event_cols = [
                        "run_tag",
                        "guardrail",
                        "target_symbol",
                        "leader_symbol",
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
                        "target_ret_5s_bps",
                        "leader_ret_5s_bps",
                        "leader_trade_flow_imbalance_5s",
                        "gross_bps",
                        "cost_bps",
                        "net_bps",
                        "reversed_net_bps",
                    ]
                    event_rows.append(selected.loc[:, event_cols].copy())
                    stats = summarize(selected["net_bps"])
                    pool = test.dropna(subset=[f"net_long_{horizon}s_bps", f"net_short_{horizon}s_bps"]).copy()
                    pool_frames: list[pd.DataFrame] = []
                    for direction in [-1, 1]:
                        tmp = pool.copy()
                        tmp["direction"] = direction
                        pool_frames.append(tmp)
                    control_pool = pd.concat(pool_frames, ignore_index=True)
                    random_arr = np.asarray(
                        control_distribution(
                            selected,
                            control_pool,
                            horizon,
                            matched_random_iters,
                            rng,
                            control_selected_cap,
                            control_pool_cap,
                        ),
                        dtype="float64",
                    )
                    summary = {
                        "run_tag": RUN_TAG,
                        "guardrail": GUARDRAIL,
                        "target_symbol": str(selected["target_symbol"].iloc[0]),
                        "leader_symbol": str(selected["leader_symbol"].iloc[0]),
                        "fold": fold,
                        "trigger_class": trigger,
                        "horizon_sec": horizon,
                        "threshold_quantile": q,
                        "threshold_value": threshold,
                        "entries": int(len(selected)),
                        "gross_mean_bps": finite_mean(selected["gross_bps"]),
                        "cost_mean_bps": finite_mean(selected["cost_bps"]),
                        **stats,
                        "reversed_mean_bps": finite_mean(selected["reversed_net_bps"]),
                        "matched_random_iters": int(len(random_arr)),
                        "matched_random_mean_p50_bps": finite_quantile(random_arr, 0.50),
                        "matched_random_mean_p95_bps": finite_quantile(random_arr, 0.95),
                        "matched_random_prob_ge_signal": safe_rate(random_arr >= stats["net_mean_bps"]) if len(random_arr) else np.nan,
                    }
                    summary["signal_minus_random_p50_bps"] = summary["net_mean_bps"] - summary["matched_random_mean_p50_bps"]
                    summary["signal_minus_reversed_bps"] = summary["net_mean_bps"] - summary["reversed_mean_bps"]
                    summary_rows.append(summary)
                    control_rows.append(
                        {
                            "run_tag": RUN_TAG,
                            "guardrail": GUARDRAIL,
                            "target_symbol": summary["target_symbol"],
                            "leader_symbol": summary["leader_symbol"],
                            "fold": fold,
                            "trigger_class": trigger,
                            "horizon_sec": horizon,
                            "threshold_quantile": q,
                            "signal_mean_bps": summary["net_mean_bps"],
                            "reversed_mean_bps": summary["reversed_mean_bps"],
                            "random_iters": int(len(random_arr)),
                            "random_mean_p50_bps": summary["matched_random_mean_p50_bps"],
                            "random_mean_p95_bps": summary["matched_random_mean_p95_bps"],
                            "prob_random_ge_signal": summary["matched_random_prob_ge_signal"],
                        }
                    )
    events = pd.concat(event_rows, ignore_index=True) if event_rows else pd.DataFrame()
    return events, pd.DataFrame(summary_rows), pd.DataFrame(control_rows)


def write_report(paths: Paths, leaders: list[str], events: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    promoted = int(scores["cross_market_promote_gate"].sum()) if not scores.empty else 0
    best = scores.iloc[0].to_dict() if not scores.empty else {}
    lines: list[str] = [
        "# CCUSDT V2 Cross-Market Lead/Lag Pivot",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Inputs",
        "",
        f"- Target: `{paths.target_symbol}` from `{paths.target_data_root}`.",
        f"- Leaders: `{','.join(leaders)}` from `{paths.leader_data_root}`.",
        f"- Threshold quantiles: `{args.threshold_quantiles}`.",
        f"- Horizons sec: `{args.horizons_sec}`.",
        f"- Fee stress bps: `{args.fee_stress_bps}`.",
        f"- Matched-random iters: `{args.matched_random_iters}`.",
        f"- Control selected cap: `{args.control_selected_cap}`.",
        f"- Control pool cap: `{args.control_pool_cap}`.",
        "",
        "## Decision",
        "",
        f"Promote-gate rows: `{promoted}`.",
        "",
        "This is a structural cross-market diagnostic, not an execution recommendation. A row must pass sample, economics, stress, matched-random, reversed-side, median, and left-tail gates before it can move to heavier execution research.",
        "",
    ]
    if best:
        lines.extend(
            [
                "Best row:",
                "",
                "```text",
                f"leader/trigger/fold/horizon: {best.get('leader_symbol')} / {best.get('trigger_class')} / {best.get('fold')} / {best.get('horizon_sec')}s",
                f"entries:                     {best.get('entries')}",
                f"gross_mean_bps:              {fmt_num(best.get('gross_mean_bps'))}",
                f"cost_mean_bps:               {fmt_num(best.get('cost_mean_bps'))}",
                f"net_mean_bps:                {fmt_num(best.get('net_mean_bps'))}",
                f"net_median_bps:              {fmt_num(best.get('net_median_bps'))}",
                f"signal_minus_random_p50_bps: {fmt_num(best.get('signal_minus_random_p50_bps'))}",
                f"signal_minus_reversed_bps:   {fmt_num(best.get('signal_minus_reversed_bps'))}",
                f"status:                      {best.get('cross_market_status')}",
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Scorecard",
            "",
            *markdown_table(
                scores,
                [
                    "leader_symbol",
                    "fold",
                    "trigger_class",
                    "horizon_sec",
                    "entries",
                    "gross_mean_bps",
                    "cost_mean_bps",
                    "net_mean_bps",
                    "net_plus2_mean_bps",
                    "net_median_bps",
                    "matched_random_prob_ge_signal",
                    "signal_minus_random_p50_bps",
                    "signal_minus_reversed_bps",
                    "sample_pass",
                    "economics_pass",
                    "controls_pass",
                    "cross_market_promote_gate",
                    "cross_market_status",
                ],
                50,
            ),
            "",
            "## Output Tables",
            "",
            f"- `{paths.events_csv}`",
            f"- `{paths.controls_csv}`",
            f"- `{paths.scorecard_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            f"python scripts/ccusdt_v2_cross_market_lead_lag.py --target-data-root {paths.target_data_root} --leader-data-root {paths.leader_data_root} --target-symbol {paths.target_symbol} --leaders \"{','.join(leaders)}\" --run-tag {paths.run_tag} --threshold-quantiles \"{args.threshold_quantiles}\" --horizons-sec \"{args.horizons_sec}\" --fee-stress-bps {args.fee_stress_bps:g} --entry-bucket-sec {args.entry_bucket_sec} --matched-random-iters {args.matched_random_iters} --control-selected-cap {args.control_selected_cap} --control-pool-cap {args.control_pool_cap}",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, leaders: list[str], events: pd.DataFrame, controls: pd.DataFrame, scores: pd.DataFrame, args: argparse.Namespace) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    events.to_csv(paths.events_csv, index=False)
    controls.to_csv(paths.controls_csv, index=False)
    scores.to_csv(paths.scorecard_csv, index=False)
    meta = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "target_symbol": paths.target_symbol,
        "leaders": leaders,
        "event_rows": int(len(events)),
        "control_rows": int(len(controls)),
        "scorecard_rows": int(len(scores)),
        "promote_gate_rows": int(scores["cross_market_promote_gate"].sum()) if not scores.empty else 0,
        "best_net_mean_bps": float(pd.to_numeric(scores.get("net_mean_bps", pd.Series(dtype=float)), errors="coerce").max()) if not scores.empty else None,
        "outputs": {
            "events_csv": str(paths.events_csv),
            "controls_csv": str(paths.controls_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    write_report(paths, leaders, events, controls, scores, args)


def main() -> None:
    args = parse_args()
    global RUN_TAG
    RUN_TAG = args.run_tag
    paths = Paths(
        target_data_root=resolve_repo_path(args.target_data_root),
        leader_data_root=resolve_repo_path(args.leader_data_root),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        target_symbol=args.target_symbol,
        run_tag=args.run_tag,
    )
    leaders = parse_csv_list(args.leaders)
    horizons = [int(round(item)) for item in parse_floats(args.horizons_sec)]
    thresholds = parse_floats(args.threshold_quantiles)
    target = build_symbol_panel(paths.target_data_root, paths.date_dir, paths.doc_dir, paths.target_symbol, horizons, args.entry_bucket_sec, args.fee_stress_bps)
    target = add_target_decomposition(target, horizons, args.fee_stress_bps)
    all_events: list[pd.DataFrame] = []
    all_summary: list[pd.DataFrame] = []
    all_controls: list[pd.DataFrame] = []
    for index, leader_symbol in enumerate(leaders):
        leader = build_symbol_panel(paths.leader_data_root, paths.date_dir, paths.doc_dir, leader_symbol, horizons, args.entry_bucket_sec, args.fee_stress_bps)
        panel = pair_panel(target, leader, leader_symbol)
        events, summary, controls = run_pair(
            panel,
            thresholds,
            horizons,
            args.matched_random_iters,
            args.control_selected_cap,
            args.control_pool_cap,
            args.seed + index,
        )
        all_events.append(events)
        all_summary.append(summary)
        all_controls.append(controls)
    events_out = pd.concat([item for item in all_events if not item.empty], ignore_index=True) if all_events else pd.DataFrame()
    summary_out = pd.concat([item for item in all_summary if not item.empty], ignore_index=True) if all_summary else pd.DataFrame()
    controls_out = pd.concat([item for item in all_controls if not item.empty], ignore_index=True) if all_controls else pd.DataFrame()
    scores = scorecard(summary_out)
    write_outputs(paths, leaders, events_out, controls_out, scores, args)
    print(
        "[ccusdt_cross_market_lead_lag] "
        f"events={len(events_out)} scorecard={len(scores)} "
        f"promote={int(scores['cross_market_promote_gate'].sum()) if not scores.empty else 0} "
        f"wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
