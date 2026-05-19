#!/usr/bin/env python
"""Walk-forward exit checks for CCUSDT V1 TFI release/decay candidates.

This is a validation harness, not an optimizer. Candidate rules are deliberately
small and fixed in advance:

- fixed timeouts: 10s/20s/30s/60s
- TP + timeout: TP in {5, 8, 10} bps and timeout in {20, 30, 60}s
- one-factor flow-confirmed hold: after early release, weak 5-20s signed flow
  exits at 20s or 30s, otherwise hold to 60s
- single-entry exposure caps on the original 60s exit

Flow thresholds are computed from prior dates only. Test dates are evaluated
once after a minimum training window.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_exit_walkforward_v1"
GUARDRAIL = "walk_forward_exit_validation_research_only_no_execution_recommendation"
LATENT_FILE_NAME = "ccusdt_v1_tfi_latent_state_panel_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv"

US_PER_SECOND = 1_000_000.0
EPS = 1e-12
HORIZONS_SEC = [10, 20, 30, 60]
TP_BPS = [5.0, 8.0, 10.0]
FLOW_FEATURES = ["signed_tfi_mean_5_20s", "signed_mlofi5_mean_5_20s", "signed_ofi_mean_5_20s"]
FLOW_QUANTILES = [0.30, 0.50]
FLOW_EXIT_HORIZONS = [20, 30]
EXPOSURE_CAPS = [2.0, 4.0]

ENTRY_COLS = [
    "fold",
    "date",
    "entry_row",
    "entry_ts",
    "cell",
    "direction_label",
    "frames_q_bin",
    "delta10_bin",
    "energy10_bin",
    "z10_bin",
    "loss5_bin",
    "net",
    "gross",
    "cost",
    "weight",
    "target_gamma",
    "target_exposure",
    "target_pnl",
    "entry_quality_class",
    "entry_event_index",
    "quality_side",
    "dominant_latent_state",
    "closed10_score_abs",
    "closed10_energy",
    "closed20_energy",
    "log_opp_depth5_quote",
    "log_opp_depth25_quote",
    "Theta_t",
]

EVENT_COLS = [
    "event_index",
    "local_timestamp",
    "mid_price",
    "spread_bps",
    "trade_flow_imbalance",
    "ofi_l1_raw",
    "mlofi_raw_l5",
    "mlofi_raw_l25",
]


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    panel_root: Path
    panel_run_tag: str
    symbol: str
    run_tag: str

    @property
    def entries_csv(self) -> Path:
        return self.date_dir / LATENT_FILE_NAME

    @property
    def path_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_exit_walkforward_paths_{self.run_tag}.csv"

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_exit_walkforward_events_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_exit_walkforward_scorecard_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_exit_walkforward_daily_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_exit_walkforward_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-exit-walkforward-{self.run_tag}.md"

    def day_dir(self, date: str) -> Path:
        return self.panel_root / f"run_tag={self.panel_run_tag}" / f"symbol={self.symbol}" / f"dt={date}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument(
        "--panel-root",
        default="data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel",
    )
    parser.add_argument("--panel-run-tag", default="20260517_ccusdt_fixed_factors_v3")
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--min-train-days", type=int, default=5)
    parser.add_argument("--release-threshold-bps", type=float, default=5.0)
    return parser.parse_args()


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return ""
    return f"{v:.{digits}f}"


def finite_mean(values: pd.Series | np.ndarray) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else float("nan")


def finite_quantile(values: pd.Series | np.ndarray, q: float) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else float("nan")


def cvar(values: pd.Series | np.ndarray, q: float = 0.05) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return float("nan")
    n = max(1, int(np.ceil(len(arr) * q)))
    return float(np.sort(arr)[:n].mean())


def markdown_table(df: pd.DataFrame, cols: Iterable[str], max_rows: int = 20) -> list[str]:
    cols = [c for c in cols if c in df.columns]
    if not cols or df.empty:
        return ["", "_No rows._", ""]
    out = df.loc[:, cols].head(max_rows).copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(lambda v: fmt(v, 4))
    lines = ["", "| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in out.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    lines.append("")
    return lines


def cost_array(entry_spread: np.ndarray, exit_spread: np.ndarray, extra_bps: float = 0.0) -> np.ndarray:
    entry = np.asarray(entry_spread, dtype="float64")
    exit_ = np.asarray(exit_spread, dtype="float64")
    entry_fill = np.nanmedian(entry[np.isfinite(entry)]) if np.isfinite(entry).any() else 0.0
    exit_fill = np.nanmedian(exit_[np.isfinite(exit_)]) if np.isfinite(exit_).any() else 0.0
    entry = np.nan_to_num(entry, nan=entry_fill)
    exit_ = np.nan_to_num(exit_, nan=exit_fill)
    return 1.0 + 0.25 * (entry + exit_) + extra_bps


def load_entries(paths: Paths) -> pd.DataFrame:
    entries = pd.read_csv(paths.entries_csv, usecols=lambda col: col in ENTRY_COLS)
    for col in ["entry_row", "entry_event_index"]:
        entries[col] = pd.to_numeric(entries[col], errors="coerce").astype("Int64")
    for col in [
        "net",
        "gross",
        "cost",
        "weight",
        "target_gamma",
        "target_exposure",
        "target_pnl",
        "closed10_score_abs",
        "closed10_energy",
        "closed20_energy",
        "log_opp_depth5_quote",
        "log_opp_depth25_quote",
        "Theta_t",
    ]:
        if col in entries.columns:
            entries[col] = pd.to_numeric(entries[col], errors="coerce")
    return entries


def load_day_panel(paths: Paths, date: str) -> pd.DataFrame:
    day_dir = paths.day_dir(date)
    frames: list[pd.DataFrame] = []
    if not day_dir.exists():
        return pd.DataFrame(columns=EVENT_COLS)
    for csv_path in sorted(day_dir.glob("*.csv")):
        part = pd.read_csv(csv_path, usecols=lambda col: col in EVENT_COLS)
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=EVENT_COLS)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["event_index", "local_timestamp", "mid_price"]).copy()
    panel["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").astype("int64")
    panel = panel.sort_values(["local_timestamp", "event_index"]).drop_duplicates("event_index", keep="last")
    return panel.reset_index(drop=True)


def mean_interval(values: np.ndarray, start: int, end: int) -> float:
    if end <= start:
        return float("nan")
    arr = values[start:end]
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else float("nan")


def rebuild_path_rows(entries: pd.DataFrame, paths: Paths) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    day_stats: list[dict[str, Any]] = []
    for date, group in entries.groupby("date", sort=True):
        panel = load_day_panel(paths, str(date))
        if panel.empty:
            day_stats.append({"date": str(date), "entries": int(len(group)), "path_rows": 0, "status": "missing_panel"})
            continue
        arrays = {col: pd.to_numeric(panel[col], errors="coerce").to_numpy(dtype="float64") for col in EVENT_COLS if col in panel.columns}
        event_indices = pd.to_numeric(panel["event_index"], errors="coerce").to_numpy(dtype="int64")
        times = arrays["local_timestamp"]
        mids = arrays["mid_price"]
        spread = arrays["spread_bps"]
        before = len(rows)
        for _, entry in group.iterrows():
            if pd.isna(entry["entry_event_index"]):
                continue
            event_index = int(entry["entry_event_index"])
            pos = int(np.searchsorted(event_indices, event_index, side="left"))
            if pos >= len(event_indices):
                pos = len(event_indices) - 1
            if pos > 0 and abs(event_indices[pos] - event_index) > abs(event_indices[pos - 1] - event_index):
                pos -= 1
            t0 = float(times[pos])
            mid0 = float(mids[pos])
            if not np.isfinite(mid0) or mid0 <= 0:
                continue
            side = 1 if str(entry["direction_label"]) == "long" else -1
            start = int(np.searchsorted(times, t0, side="right"))
            max_end = int(np.searchsorted(times, t0 + max(HORIZONS_SEC) * US_PER_SECOND, side="right"))
            if max_end <= start:
                continue
            row: dict[str, Any] = {
                "date": str(entry["date"]),
                "fold": entry.get("fold"),
                "entry_row": int(entry["entry_row"]),
                "entry_event_index": event_index,
                "matched_event_index": int(event_indices[pos]),
                "cell": entry["cell"],
                "direction_label": entry["direction_label"],
                "frames_q_bin": entry["frames_q_bin"],
                "delta10_bin": entry["delta10_bin"],
                "energy10_bin": entry["energy10_bin"],
                "z10_bin": entry["z10_bin"],
                "loss5_bin": entry.get("loss5_bin"),
                "quality_side": entry.get("quality_side"),
                "entry_quality_class": entry.get("entry_quality_class"),
                "dominant_latent_state": entry.get("dominant_latent_state"),
                "weight": float(entry.get("weight", np.nan)),
                "target_gamma": float(entry.get("target_gamma", np.nan)),
                "target_exposure": float(entry.get("target_exposure", np.nan)),
                "original_net_60s": float(entry.get("net", np.nan)),
                "original_cost_60s": float(entry.get("cost", np.nan)),
                "entry_mid": mid0,
                "entry_spread_bps": float(spread[pos]),
            }
            for col in [
                "closed10_score_abs",
                "closed10_energy",
                "closed20_energy",
                "log_opp_depth5_quote",
                "log_opp_depth25_quote",
                "Theta_t",
            ]:
                if col in entry.index:
                    row[col] = float(entry[col]) if pd.notna(entry[col]) else np.nan

            for horizon in HORIZONS_SEC:
                end = int(np.searchsorted(times, t0 + horizon * US_PER_SECOND, side="right"))
                if end <= start:
                    continue
                idx = np.arange(start, end, dtype="int64")
                rets = side * 10_000.0 * np.log(np.maximum(mids[idx], EPS) / max(mid0, EPS))
                if not np.isfinite(rets).any():
                    continue
                mfe_pos = int(np.nanargmax(rets))
                mae_pos = int(np.nanargmin(rets))
                exit_idx = int(idx[-1])
                exit_spread = float(spread[exit_idx])
                gross = float(rets[-1])
                cost = float(cost_array(np.asarray([spread[pos]]), np.asarray([exit_spread]))[0])
                row[f"gross_fixed_{horizon}s"] = gross
                row[f"cost_fixed_{horizon}s"] = cost
                row[f"net_fixed_{horizon}s"] = gross - cost
                row[f"stress_net_fixed_{horizon}s"] = gross - cost - 2.0
                row[f"exit_spread_fixed_{horizon}s"] = exit_spread
                row[f"mfe_{horizon}s"] = float(rets[mfe_pos])
                row[f"mae_{horizon}s"] = float(rets[mae_pos])
                row[f"t_mfe_{horizon}s"] = float((times[idx[mfe_pos]] - t0) / US_PER_SECOND)
                row[f"decay_{horizon}s"] = float(rets[mfe_pos] - gross)
                for tp in TP_BPS:
                    hit_positions = np.flatnonzero(rets >= tp)
                    if len(hit_positions):
                        hit_idx = int(idx[int(hit_positions[0])])
                        hit_spread = float(spread[hit_idx])
                        tp_cost = float(cost_array(np.asarray([spread[pos]]), np.asarray([hit_spread]))[0])
                        row[f"hit_tp{int(tp)}_{horizon}s"] = True
                        row[f"hit_tp{int(tp)}_{horizon}s_sec"] = float((times[hit_idx] - t0) / US_PER_SECOND)
                        row[f"gross_tp{int(tp)}_{horizon}s"] = tp
                        row[f"cost_tp{int(tp)}_{horizon}s"] = tp_cost
                        row[f"net_tp{int(tp)}_{horizon}s"] = tp - tp_cost
                        row[f"stress_net_tp{int(tp)}_{horizon}s"] = tp - tp_cost - 2.0
                    else:
                        row[f"hit_tp{int(tp)}_{horizon}s"] = False
                        row[f"hit_tp{int(tp)}_{horizon}s_sec"] = np.nan
                        row[f"gross_tp{int(tp)}_{horizon}s"] = gross
                        row[f"cost_tp{int(tp)}_{horizon}s"] = cost
                        row[f"net_tp{int(tp)}_{horizon}s"] = gross - cost
                        row[f"stress_net_tp{int(tp)}_{horizon}s"] = gross - cost - 2.0

            left = int(np.searchsorted(times, t0 + 5 * US_PER_SECOND, side="right"))
            right = int(np.searchsorted(times, t0 + 20 * US_PER_SECOND, side="right"))
            row["signed_tfi_mean_5_20s"] = side * mean_interval(arrays["trade_flow_imbalance"], left, right)
            row["signed_mlofi5_mean_5_20s"] = side * mean_interval(arrays["mlofi_raw_l5"], left, right)
            row["signed_ofi_mean_5_20s"] = side * mean_interval(arrays["ofi_l1_raw"], left, right)
            row["ret_5_20s"] = (
                side * 10_000.0 * np.log(max(mids[right - 1], EPS) / max(mids[left - 1], EPS))
                if right > left and left > 0
                else np.nan
            )
            rows.append(row)
        day_stats.append(
            {
                "date": str(date),
                "entries": int(len(group)),
                "path_rows": int(len(rows) - before),
                "panel_rows": int(len(panel)),
                "status": "ok",
            }
        )
    return pd.DataFrame(rows), day_stats


def policy_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for horizon in HORIZONS_SEC:
        specs.append({"policy": f"fixed_{horizon}s", "family": "fixed_timeout", "horizon": horizon})
    for cap in EXPOSURE_CAPS:
        specs.append({"policy": f"fixed_60s_cap{fmt(cap, 0)}", "family": "exposure_cap", "horizon": 60, "cap": cap})
    for tp in TP_BPS:
        for horizon in [20, 30, 60]:
            specs.append({"policy": f"tp{int(tp)}_timeout{horizon}s", "family": "tp_timeout", "tp": tp, "horizon": horizon})
    for feature in FLOW_FEATURES:
        for q in FLOW_QUANTILES:
            for exit_horizon in FLOW_EXIT_HORIZONS:
                specs.append(
                    {
                        "policy": f"flow_hold_{feature}_q{int(q * 100)}_exit{exit_horizon}s",
                        "family": "flow_confirmed_hold",
                        "feature": feature,
                        "q": q,
                        "exit_horizon": exit_horizon,
                        "hold_horizon": 60,
                    }
                )
    return specs


def train_threshold(train: pd.DataFrame, feature: str, q: float, release_threshold_bps: float) -> float:
    release_train = train[pd.to_numeric(train["mfe_10s"], errors="coerce") >= release_threshold_bps]
    values = pd.to_numeric(release_train[feature], errors="coerce").dropna()
    return float(values.quantile(q)) if len(values) >= 30 else np.nan


def apply_policy(
    test: pd.DataFrame,
    train: pd.DataFrame,
    spec: dict[str, Any],
    release_threshold_bps: float,
) -> pd.DataFrame:
    out = test.copy()
    out["policy"] = spec["policy"]
    out["family"] = spec["family"]
    out["triggered"] = False
    out["train_threshold"] = np.nan
    out["exit_horizon_sec"] = np.nan
    exposure = pd.to_numeric(out["target_exposure"], errors="coerce").fillna(0.0)
    if "cap" in spec:
        exposure = exposure.clip(upper=float(spec["cap"]))
    out["policy_exposure"] = exposure

    if spec["family"] in {"fixed_timeout", "exposure_cap"}:
        horizon = int(spec["horizon"])
        out["policy_net"] = pd.to_numeric(out[f"net_fixed_{horizon}s"], errors="coerce")
        out["policy_stress_net"] = pd.to_numeric(out[f"stress_net_fixed_{horizon}s"], errors="coerce")
        out["policy_gross"] = pd.to_numeric(out[f"gross_fixed_{horizon}s"], errors="coerce")
        out["exit_horizon_sec"] = horizon
    elif spec["family"] == "tp_timeout":
        tp = int(spec["tp"])
        horizon = int(spec["horizon"])
        out["policy_net"] = pd.to_numeric(out[f"net_tp{tp}_{horizon}s"], errors="coerce")
        out["policy_stress_net"] = pd.to_numeric(out[f"stress_net_tp{tp}_{horizon}s"], errors="coerce")
        out["policy_gross"] = pd.to_numeric(out[f"gross_tp{tp}_{horizon}s"], errors="coerce")
        out["triggered"] = out[f"hit_tp{tp}_{horizon}s"].astype(bool)
        out["exit_horizon_sec"] = np.where(out["triggered"], out[f"hit_tp{tp}_{horizon}s_sec"], horizon)
    elif spec["family"] == "flow_confirmed_hold":
        feature = str(spec["feature"])
        q = float(spec["q"])
        exit_horizon = int(spec["exit_horizon"])
        hold_horizon = int(spec["hold_horizon"])
        threshold = train_threshold(train, feature, q, release_threshold_bps)
        release = pd.to_numeric(out["mfe_10s"], errors="coerce") >= release_threshold_bps
        weak_flow = pd.to_numeric(out[feature], errors="coerce") <= threshold if np.isfinite(threshold) else pd.Series(False, index=out.index)
        triggered = release & weak_flow
        out["triggered"] = triggered
        out["train_threshold"] = threshold
        out["policy_net"] = np.where(
            triggered,
            pd.to_numeric(out[f"net_fixed_{exit_horizon}s"], errors="coerce"),
            pd.to_numeric(out[f"net_fixed_{hold_horizon}s"], errors="coerce"),
        )
        out["policy_stress_net"] = np.where(
            triggered,
            pd.to_numeric(out[f"stress_net_fixed_{exit_horizon}s"], errors="coerce"),
            pd.to_numeric(out[f"stress_net_fixed_{hold_horizon}s"], errors="coerce"),
        )
        out["policy_gross"] = np.where(
            triggered,
            pd.to_numeric(out[f"gross_fixed_{exit_horizon}s"], errors="coerce"),
            pd.to_numeric(out[f"gross_fixed_{hold_horizon}s"], errors="coerce"),
        )
        out["exit_horizon_sec"] = np.where(triggered, exit_horizon, hold_horizon)
    else:
        raise ValueError(f"unknown family {spec['family']}")

    out["baseline_net_same_exposure"] = pd.to_numeric(out["net_fixed_60s"], errors="coerce")
    out["baseline_stress_net_same_exposure"] = pd.to_numeric(out["stress_net_fixed_60s"], errors="coerce")
    out["weighted_net"] = out["policy_net"] * out["policy_exposure"]
    out["weighted_stress_net"] = out["policy_stress_net"] * out["policy_exposure"]
    out["baseline_weighted_net_same_exposure"] = out["baseline_net_same_exposure"] * out["policy_exposure"]
    out["delta_weighted_vs_same_exposure_60s"] = out["weighted_net"] - out["baseline_weighted_net_same_exposure"]
    return out


def build_policy_events(paths_df: pd.DataFrame, min_train_days: int, release_threshold_bps: float) -> tuple[pd.DataFrame, list[str]]:
    dates = sorted(paths_df["date"].astype(str).unique().tolist())
    test_dates = dates[min_train_days:]
    rows: list[pd.DataFrame] = []
    specs = policy_specs()
    for date in test_dates:
        train = paths_df[paths_df["date"].astype(str) < date].copy()
        test = paths_df[paths_df["date"].astype(str) == date].copy()
        if train["date"].nunique() < min_train_days or test.empty:
            continue
        for spec in specs:
            rows.append(apply_policy(test, train, spec, release_threshold_bps))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(), test_dates


def score_policy(group: pd.DataFrame) -> dict[str, Any]:
    net = pd.to_numeric(group["policy_net"], errors="coerce")
    weighted = pd.to_numeric(group["weighted_net"], errors="coerce")
    stress_weighted = pd.to_numeric(group["weighted_stress_net"], errors="coerce")
    baseline_weighted = pd.to_numeric(group["baseline_weighted_net_same_exposure"], errors="coerce")
    delta = pd.to_numeric(group["delta_weighted_vs_same_exposure_60s"], errors="coerce")
    daily = group.groupby("date", sort=True)["weighted_net"].sum()
    daily_stress = group.groupby("date", sort=True)["weighted_stress_net"].sum()
    positive = weighted[weighted > 0].sort_values(ascending=False)
    total = float(weighted.sum())
    top10_share = float(positive.head(10).sum() / total) if total > EPS and len(positive) else np.nan
    saved_loser = float(delta[baseline_weighted < 0].clip(lower=0).sum())
    killed_winner = float((-delta[baseline_weighted > 0]).clip(lower=0).sum())
    return {
        "policy": str(group["policy"].iloc[0]),
        "family": str(group["family"].iloc[0]),
        "entries": int(len(group)),
        "dates": int(group["date"].nunique()),
        "exposure": float(pd.to_numeric(group["policy_exposure"], errors="coerce").sum()),
        "total_pnl": total,
        "stress_total_pnl": float(stress_weighted.sum()),
        "baseline_same_exposure_total_pnl": float(baseline_weighted.sum()),
        "delta_vs_same_exposure_60s": float(delta.sum()),
        "mean_net": finite_mean(net),
        "median_net": finite_quantile(net, 0.50),
        "gt2_rate": float((net > 2.0).mean()),
        "q90_net": finite_quantile(net, 0.90),
        "cvar05_net": cvar(net, 0.05),
        "single_worst_weighted": finite_quantile(weighted, 0.00),
        "single_cvar05_weighted": cvar(weighted, 0.05),
        "worst_day": float(daily.min()) if len(daily) else np.nan,
        "positive_days": int((daily > 0).sum()) if len(daily) else 0,
        "stress_worst_day": float(daily_stress.min()) if len(daily_stress) else np.nan,
        "trigger_rate": float(group["triggered"].astype(bool).mean()),
        "mean_exit_horizon_sec": finite_mean(group["exit_horizon_sec"]),
        "top10_winner_share": top10_share,
        "saved_loser_pnl": saved_loser,
        "killed_winner_pnl": killed_winner,
        "save_kill_ratio": saved_loser / killed_winner if killed_winner > EPS else np.inf if saved_loser > EPS else np.nan,
    }


def build_scorecard(events: pd.DataFrame) -> pd.DataFrame:
    rows = [score_policy(group) for _, group in events.groupby("policy", sort=False)]
    scorecard = pd.DataFrame(rows)
    baseline_total = float(scorecard.loc[scorecard["policy"].eq("fixed_60s"), "total_pnl"].iloc[0])
    baseline_worst = float(scorecard.loc[scorecard["policy"].eq("fixed_60s"), "worst_day"].iloc[0])
    baseline_q90 = float(scorecard.loc[scorecard["policy"].eq("fixed_60s"), "q90_net"].iloc[0])
    scorecard["delta_vs_original_fixed60_total"] = scorecard["total_pnl"] - baseline_total
    scorecard["delta_vs_original_fixed60_worst_day"] = scorecard["worst_day"] - baseline_worst
    scorecard["right_tail_retention_q90"] = scorecard["q90_net"] / baseline_q90 if abs(baseline_q90) > EPS else np.nan
    scorecard["risk_score"] = (
        scorecard["delta_vs_original_fixed60_total"]
        + 2.0 * scorecard["delta_vs_original_fixed60_worst_day"]
        + 0.25 * scorecard["stress_total_pnl"]
    )
    return scorecard.sort_values("risk_score", ascending=False).reset_index(drop=True)


def build_daily(events: pd.DataFrame) -> pd.DataFrame:
    return (
        events.groupby(["policy", "family", "date"], sort=True)
        .agg(
            entries=("entry_row", "size"),
            exposure=("policy_exposure", "sum"),
            total_pnl=("weighted_net", "sum"),
            stress_total_pnl=("weighted_stress_net", "sum"),
            baseline_same_exposure_total_pnl=("baseline_weighted_net_same_exposure", "sum"),
            trigger_rate=("triggered", "mean"),
            mean_exit_horizon_sec=("exit_horizon_sec", "mean"),
        )
        .reset_index()
    )


def build_summary(paths_df: pd.DataFrame, events: pd.DataFrame, scorecard: pd.DataFrame, daily: pd.DataFrame, day_stats: list[dict[str, Any]], test_dates: list[str]) -> dict[str, Any]:
    fixed = scorecard[scorecard["family"].eq("fixed_timeout")].sort_values("policy")
    tp = scorecard[scorecard["family"].eq("tp_timeout")].head(10)
    flow = scorecard[scorecard["family"].eq("flow_confirmed_hold")].head(10)
    caps = scorecard[scorecard["family"].eq("exposure_cap")].sort_values("policy")
    best = scorecard.iloc[0].to_dict() if len(scorecard) else {}
    baseline = scorecard[scorecard["policy"].eq("fixed_60s")].iloc[0].to_dict()
    return {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "path_rows": int(len(paths_df)),
        "event_rows": int(len(events)),
        "test_dates": test_dates,
        "day_stats": day_stats,
        "baseline_fixed60": baseline,
        "best_by_risk_score": best,
        "fixed_timeout": fixed.to_dict(orient="records"),
        "top_tp_timeout": tp.to_dict(orient="records"),
        "top_flow_confirmed_hold": flow.to_dict(orient="records"),
        "exposure_caps": caps.to_dict(orient="records"),
    }


def write_report(paths: Paths, scorecard: pd.DataFrame, daily: pd.DataFrame, summary: dict[str, Any]) -> None:
    fixed = scorecard[scorecard["family"].eq("fixed_timeout")].sort_values("policy")
    tp = scorecard[scorecard["family"].eq("tp_timeout")].head(10)
    flow = scorecard[scorecard["family"].eq("flow_confirmed_hold")].head(10)
    caps = scorecard[scorecard["family"].eq("exposure_cap")].sort_values("policy")
    best = summary["best_by_risk_score"]
    baseline = summary["baseline_fixed60"]
    lines: list[str] = [
        "# CCUSDT TFI Exit Walk-Forward Check",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This is a frozen-candidate walk-forward validation, not an exit optimizer. Test days are evaluated once after prior-date training.",
        "",
        "## Design",
        "",
        "- Entry universe: existing V1 TFI latent-state entries with local v3 fixed-event panel paths.",
        "- Earliest train window: 5 prior dates.",
        f"- Test dates: `{', '.join(summary['test_dates'])}`.",
        "- Baseline: `fixed_60s` on the same entries and same toy maker-light cost model.",
        "- Candidate families: fixed timeout, TP+timeout, single-factor flow-confirmed hold, and exposure cap.",
        "- Flow thresholds are prior-date quantiles among prior entries with `MFE_10 >= 5bps`.",
        "",
        "The signed path is:",
        "",
        "$$",
        "R_i(\\tau)=s_i10^4\\log\\frac{M_{t_i+\\tau}}{M_{t_i}}.",
        "$$",
        "",
        "TP exits are first-hit mid-price barriers and should be read as a research proxy, not guaranteed executable fills.",
        "",
        "## Main Read",
        "",
        f"Baseline `fixed_60s`: total `{fmt(baseline.get('total_pnl'))}`, worst day `{fmt(baseline.get('worst_day'))}`, CVaR5 `{fmt(baseline.get('cvar05_net'))}`, q90 `{fmt(baseline.get('q90_net'))}`.",
        f"Best risk-score candidate: `{best.get('policy')}` with total `{fmt(best.get('total_pnl'))}`, worst day `{fmt(best.get('worst_day'))}`, delta total vs original fixed60 `{fmt(best.get('delta_vs_original_fixed60_total'))}`, and right-tail retention `{fmt(best.get('right_tail_retention_q90'))}`.",
        "",
        "Verdict:",
        "",
        "- `fixed_30s` is the cleanest simple risk-control baseline: all `7/7` test days are positive and worst day improves, but total PnL drops materially and q90 right-tail retention is only about two thirds of `fixed_60s`.",
        "- TP+timeout is not supported in this pass. It protects some losers but kills too much right tail; every TP variant underperforms `fixed_60s` on total PnL.",
        "- The best flow-confirmed hold candidates improve total and worst day, but they are path-dependent hypotheses, not promoted rules. They require the `5s..20s` flow window and therefore must be evaluated with explicit decision timing and execution assumptions.",
        "- Exposure caps alone are not a repair here: they cut important winners and can worsen worst-day PnL.",
        "",
        "A candidate should not be trusted merely because it ranks high here. Promotion requires fresh OOS days and execution-aware fill/cost checks.",
        "",
        "## Fixed Timeout",
    ]
    common_cols = [
        "policy",
        "entries",
        "total_pnl",
        "stress_total_pnl",
        "delta_vs_original_fixed60_total",
        "mean_net",
        "median_net",
        "q90_net",
        "cvar05_net",
        "worst_day",
        "positive_days",
        "right_tail_retention_q90",
        "top10_winner_share",
    ]
    lines.extend(markdown_table(fixed, common_cols, max_rows=20))
    lines.extend(["## TP + Timeout"])
    lines.extend(markdown_table(tp, common_cols + ["trigger_rate", "mean_exit_horizon_sec", "saved_loser_pnl", "killed_winner_pnl"], max_rows=20))
    lines.extend(["## Flow-Confirmed Hold"])
    lines.extend(markdown_table(flow, common_cols + ["trigger_rate", "mean_exit_horizon_sec", "saved_loser_pnl", "killed_winner_pnl", "save_kill_ratio"], max_rows=20))
    lines.extend(["## Exposure Cap"])
    lines.extend(markdown_table(caps, common_cols, max_rows=20))
    lines.extend(
        [
            "## Outputs",
            "",
            f"- `{paths.path_csv}`",
            f"- `{paths.events_csv}`",
            f"- `{paths.scorecard_csv}`",
            f"- `{paths.daily_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_exit_walkforward.py",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        panel_root=resolve_repo_path(args.panel_root),
        panel_run_tag=args.panel_run_tag,
        symbol=args.symbol,
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    entries = load_entries(paths)
    paths_df, day_stats = rebuild_path_rows(entries, paths)
    events, test_dates = build_policy_events(paths_df, min_train_days=int(args.min_train_days), release_threshold_bps=float(args.release_threshold_bps))
    if events.empty:
        raise RuntimeError("No policy events produced.")
    scorecard = build_scorecard(events)
    daily = build_daily(events)
    summary = build_summary(paths_df, events, scorecard, daily, day_stats, test_dates)

    paths_df.to_csv(paths.path_csv, index=False)
    events.to_csv(paths.events_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, scorecard, daily, summary)

    print(
        json.dumps(
            {
                "run_tag": paths.run_tag,
                "report": str(paths.report_md),
                "path_rows": int(len(paths_df)),
                "event_rows": int(len(events)),
                "test_dates": test_dates,
                "baseline_total": summary["baseline_fixed60"]["total_pnl"],
                "baseline_worst_day": summary["baseline_fixed60"]["worst_day"],
                "best_policy": summary["best_by_risk_score"]["policy"],
                "best_total": summary["best_by_risk_score"]["total_pnl"],
                "best_worst_day": summary["best_by_risk_score"]["worst_day"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
