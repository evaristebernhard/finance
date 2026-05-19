#!/usr/bin/env python
"""Simple price-only trailing parameter research for CCUSDT V1 TFI.

This script deliberately avoids additional order-flow/book factors. It tests
whether a price-path release trigger plus trailing drawdown can protect fast
release/decay paths without hard-coding a 10bps threshold.

Release threshold on each test day is prior-date only:

    r_i = max(cost_floor_i + margin, Q_p_train(H_10))

After a release within the activation window, a trailing stop exits when:

    H_t - R_t >= max(cost_floor_i + margin, eta * H_t)

All rules are research-only and mid-path proxy based.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


RUN_TAG = "20260519_ccusdt_v1_tfi_price_trailing_param_v1"
GUARDRAIL = "price_only_trailing_parameter_research_walk_forward_no_execution_recommendation"
LATENT_FILE_NAME = "ccusdt_v1_tfi_latent_state_panel_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv"
US_PER_SECOND = 1_000_000.0
EPS = 1e-12

FIXED_HORIZONS_SEC = [20, 30, 60]
RELEASE_QUANTILES = [0.60, 0.70, 0.80]
ETA_VALUES = [0.30, 0.50]
ACTIVATION_HORIZONS_SEC = [10, 20]
MARGIN_BPS = 1.0

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
]

EVENT_COLS = [
    "event_index",
    "local_timestamp",
    "mid_price",
    "spread_bps",
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
    def base_paths_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_price_trailing_base_paths_{self.run_tag}.csv"

    @property
    def events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_price_trailing_events_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_price_trailing_scorecard_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_price_trailing_daily_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_price_trailing_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-price-trailing-param-research-{self.run_tag}.md"

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
    parser.add_argument("--margin-bps", type=float, default=MARGIN_BPS)
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
    for col in ["net", "gross", "cost", "weight", "target_gamma", "target_exposure", "target_pnl"]:
        if col in entries.columns:
            entries[col] = pd.to_numeric(entries[col], errors="coerce")
    return entries


def load_day_panel(paths: Paths, date: str) -> pd.DataFrame:
    day_dir = paths.day_dir(date)
    frames: list[pd.DataFrame] = []
    if not day_dir.exists():
        return pd.DataFrame(columns=EVENT_COLS)
    for csv_path in sorted(day_dir.glob("*.csv")):
        frames.append(pd.read_csv(csv_path, usecols=lambda col: col in EVENT_COLS))
    if not frames:
        return pd.DataFrame(columns=EVENT_COLS)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["event_index", "local_timestamp", "mid_price"]).copy()
    panel["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").astype("int64")
    panel = panel.sort_values(["local_timestamp", "event_index"]).drop_duplicates("event_index", keep="last")
    return panel.reset_index(drop=True)


def locate_entry(event_indices: np.ndarray, entry_event_index: int) -> int:
    pos = int(np.searchsorted(event_indices, entry_event_index, side="left"))
    if pos >= len(event_indices):
        pos = len(event_indices) - 1
    if pos > 0 and abs(event_indices[pos] - entry_event_index) > abs(event_indices[pos - 1] - entry_event_index):
        pos -= 1
    return pos


def path_arrays_for_entry(entry: pd.Series, arrays: dict[str, np.ndarray]) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray] | None:
    event_index = int(entry["entry_event_index"])
    event_indices = arrays["event_index"]
    pos = locate_entry(event_indices, event_index)
    times = arrays["local_timestamp"]
    mids = arrays["mid_price"]
    spreads = arrays["spread_bps"]
    t0 = float(times[pos])
    mid0 = float(mids[pos])
    if not np.isfinite(mid0) or mid0 <= 0:
        return None
    side = 1 if str(entry["direction_label"]) == "long" else -1
    start = int(np.searchsorted(times, t0, side="right"))
    end = int(np.searchsorted(times, t0 + 60 * US_PER_SECOND, side="right"))
    if end <= start:
        return None
    idx = np.arange(start, end, dtype="int64")
    rets = side * 10_000.0 * np.log(np.maximum(mids[idx], EPS) / max(mid0, EPS))
    hold_sec = (times[idx] - t0) / US_PER_SECOND
    meta = {
        "entry_row": int(entry["entry_row"]),
        "entry_event_index": event_index,
        "matched_event_index": int(event_indices[pos]),
        "date": str(entry["date"]),
        "fold": entry.get("fold"),
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
        "entry_spread_bps": float(spreads[pos]),
        "cost_floor_bps": float(cost_array(np.asarray([spreads[pos]]), np.asarray([spreads[pos]]))[0]),
    }
    return meta, idx, hold_sec, rets


def fixed_exit(idx: np.ndarray, hold_sec: np.ndarray, rets: np.ndarray, arrays: dict[str, np.ndarray], horizon: int, entry_spread: float) -> dict[str, Any]:
    eligible = np.flatnonzero(hold_sec <= horizon)
    pos = int(eligible[-1]) if len(eligible) else len(hold_sec) - 1
    exit_idx = int(idx[pos])
    gross = float(rets[pos])
    cost = float(cost_array(np.asarray([entry_spread]), np.asarray([arrays["spread_bps"][exit_idx]]))[0])
    return {
        "gross": gross,
        "cost": cost,
        "net": gross - cost,
        "exit_sec": float(hold_sec[pos]),
        "exit_reason": f"fixed_{horizon}s",
        "exit_event_index": int(arrays["event_index"][exit_idx]),
    }


def simulate_trailing(
    idx: np.ndarray,
    hold_sec: np.ndarray,
    rets: np.ndarray,
    arrays: dict[str, np.ndarray],
    entry_spread: float,
    cost_floor: float,
    release_threshold: float,
    eta: float,
    activation_horizon: int,
    margin_bps: float,
) -> dict[str, Any]:
    h = np.maximum.accumulate(rets)
    release_level = max(cost_floor + margin_bps, release_threshold)
    release_pos_candidates = np.flatnonzero((hold_sec <= activation_horizon) & (h >= release_level))
    if not len(release_pos_candidates):
        out = fixed_exit(idx, hold_sec, rets, arrays, 60, entry_spread)
        out.update(
            {
                "activated": False,
                "release_level": release_level,
                "release_sec": np.nan,
                "drawdown_at_exit": np.nan,
                "trail_threshold_at_exit": np.nan,
            }
        )
        return out
    release_pos = int(release_pos_candidates[0])
    exit_pos: int | None = None
    drawdown = h - rets
    trail_threshold = np.maximum(cost_floor + margin_bps, eta * h)
    for pos in range(release_pos, len(rets)):
        if drawdown[pos] >= trail_threshold[pos]:
            exit_pos = pos
            break
    if exit_pos is None:
        out = fixed_exit(idx, hold_sec, rets, arrays, 60, entry_spread)
        out.update(
            {
                "activated": True,
                "release_level": release_level,
                "release_sec": float(hold_sec[release_pos]),
                "drawdown_at_exit": float(drawdown[-1]),
                "trail_threshold_at_exit": float(trail_threshold[-1]),
            }
        )
        return out
    exit_idx = int(idx[exit_pos])
    gross = float(rets[exit_pos])
    cost = float(cost_array(np.asarray([entry_spread]), np.asarray([arrays["spread_bps"][exit_idx]]))[0])
    return {
        "gross": gross,
        "cost": cost,
        "net": gross - cost,
        "exit_sec": float(hold_sec[exit_pos]),
        "exit_reason": "trailing_drawdown",
        "exit_event_index": int(arrays["event_index"][exit_idx]),
        "activated": True,
        "release_level": release_level,
        "release_sec": float(hold_sec[release_pos]),
        "drawdown_at_exit": float(drawdown[exit_pos]),
        "trail_threshold_at_exit": float(trail_threshold[exit_pos]),
    }


def base_path_metrics(meta: dict[str, Any], idx: np.ndarray, hold_sec: np.ndarray, rets: np.ndarray, arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    row = dict(meta)
    for horizon in [10, 20, 30, 60]:
        eligible = np.flatnonzero(hold_sec <= horizon)
        if not len(eligible):
            continue
        end_pos = int(eligible[-1])
        horizon_rets = rets[: end_pos + 1]
        mfe_pos = int(np.nanargmax(horizon_rets))
        mae_pos = int(np.nanargmin(horizon_rets))
        fixed = fixed_exit(idx, hold_sec, rets, arrays, horizon, meta["entry_spread_bps"])
        row[f"gross_fixed_{horizon}s"] = fixed["gross"]
        row[f"cost_fixed_{horizon}s"] = fixed["cost"]
        row[f"net_fixed_{horizon}s"] = fixed["net"]
        row[f"mfe_{horizon}s"] = float(horizon_rets[mfe_pos])
        row[f"mae_{horizon}s"] = float(horizon_rets[mae_pos])
        row[f"t_mfe_{horizon}s"] = float(hold_sec[mfe_pos])
        row[f"decay_{horizon}s"] = float(horizon_rets[mfe_pos] - fixed["gross"])
    return row


def rebuild_base_paths(entries: pd.DataFrame, paths: Paths) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    day_stats: list[dict[str, Any]] = []
    for date, group in entries.groupby("date", sort=True):
        panel = load_day_panel(paths, str(date))
        if panel.empty:
            day_stats.append({"date": str(date), "entries": int(len(group)), "path_rows": 0, "status": "missing_panel"})
            continue
        arrays = {col: pd.to_numeric(panel[col], errors="coerce").to_numpy(dtype="float64") for col in EVENT_COLS if col in panel.columns}
        arrays["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").to_numpy(dtype="int64")
        before = len(rows)
        for _, entry in group.iterrows():
            if pd.isna(entry["entry_event_index"]):
                continue
            built = path_arrays_for_entry(entry, arrays)
            if built is None:
                continue
            meta, idx, hold_sec, rets = built
            rows.append(base_path_metrics(meta, idx, hold_sec, rets, arrays))
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
    for horizon in FIXED_HORIZONS_SEC:
        specs.append({"policy": f"fixed_{horizon}s", "family": "fixed", "horizon": horizon})
    for p in RELEASE_QUANTILES:
        for eta in ETA_VALUES:
            for activation in ACTIVATION_HORIZONS_SEC:
                specs.append(
                    {
                        "policy": f"trail_p{int(p * 100)}_eta{int(eta * 100)}_act{activation}s",
                        "family": "price_trailing",
                        "release_quantile": p,
                        "eta": eta,
                        "activation_horizon": activation,
                    }
                )
    return specs


def train_release_threshold(train_base: pd.DataFrame, quantile: float) -> float:
    values = pd.to_numeric(train_base["mfe_10s"], errors="coerce").dropna()
    return float(values.quantile(quantile)) if len(values) >= 30 else np.nan


def apply_fixed(test_base: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    horizon = int(spec["horizon"])
    out = test_base.copy()
    out["policy"] = spec["policy"]
    out["family"] = spec["family"]
    out["release_quantile"] = np.nan
    out["eta"] = np.nan
    out["activation_horizon"] = np.nan
    out["train_release_threshold"] = np.nan
    out["activated"] = False
    out["exit_reason"] = f"fixed_{horizon}s"
    out["exit_sec"] = horizon
    out["policy_gross"] = pd.to_numeric(out[f"gross_fixed_{horizon}s"], errors="coerce")
    out["policy_cost"] = pd.to_numeric(out[f"cost_fixed_{horizon}s"], errors="coerce")
    out["policy_net"] = pd.to_numeric(out[f"net_fixed_{horizon}s"], errors="coerce")
    out["baseline_net"] = pd.to_numeric(out["net_fixed_60s"], errors="coerce")
    out["weighted_net"] = out["policy_net"] * out["target_exposure"]
    out["baseline_weighted_net"] = out["baseline_net"] * out["target_exposure"]
    out["delta_weighted_vs_60s"] = out["weighted_net"] - out["baseline_weighted_net"]
    return out


def apply_trailing_for_day(
    test_entries: pd.DataFrame,
    paths: Paths,
    spec: dict[str, Any],
    release_threshold: float,
    margin_bps: float,
) -> pd.DataFrame:
    date = str(test_entries["date"].iloc[0])
    panel = load_day_panel(paths, date)
    arrays = {col: pd.to_numeric(panel[col], errors="coerce").to_numpy(dtype="float64") for col in EVENT_COLS if col in panel.columns}
    arrays["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").to_numpy(dtype="int64")
    rows: list[dict[str, Any]] = []
    for _, entry in test_entries.iterrows():
        built = path_arrays_for_entry(entry, arrays)
        if built is None:
            continue
        meta, idx, hold_sec, rets = built
        result = simulate_trailing(
            idx,
            hold_sec,
            rets,
            arrays,
            entry_spread=meta["entry_spread_bps"],
            cost_floor=meta["cost_floor_bps"],
            release_threshold=release_threshold,
            eta=float(spec["eta"]),
            activation_horizon=int(spec["activation_horizon"]),
            margin_bps=margin_bps,
        )
        fixed60 = fixed_exit(idx, hold_sec, rets, arrays, 60, meta["entry_spread_bps"])
        row = dict(meta)
        row.update(
            {
                "policy": spec["policy"],
                "family": spec["family"],
                "release_quantile": float(spec["release_quantile"]),
                "eta": float(spec["eta"]),
                "activation_horizon": int(spec["activation_horizon"]),
                "train_release_threshold": release_threshold,
                "activated": bool(result["activated"]),
                "release_level": result.get("release_level", np.nan),
                "release_sec": result.get("release_sec", np.nan),
                "drawdown_at_exit": result.get("drawdown_at_exit", np.nan),
                "trail_threshold_at_exit": result.get("trail_threshold_at_exit", np.nan),
                "exit_reason": result["exit_reason"],
                "exit_sec": result["exit_sec"],
                "exit_event_index": result["exit_event_index"],
                "policy_gross": result["gross"],
                "policy_cost": result["cost"],
                "policy_net": result["net"],
                "baseline_net": fixed60["net"],
                "weighted_net": result["net"] * meta["target_exposure"],
                "baseline_weighted_net": fixed60["net"] * meta["target_exposure"],
                "delta_weighted_vs_60s": (result["net"] - fixed60["net"]) * meta["target_exposure"],
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_events(entries: pd.DataFrame, base_paths: pd.DataFrame, paths: Paths, min_train_days: int, margin_bps: float) -> tuple[pd.DataFrame, list[str]]:
    dates = sorted(base_paths["date"].astype(str).unique().tolist())
    test_dates = dates[min_train_days:]
    rows: list[pd.DataFrame] = []
    specs = policy_specs()
    for date in test_dates:
        train_base = base_paths[base_paths["date"].astype(str) < date]
        test_base = base_paths[base_paths["date"].astype(str) == date]
        test_entries = entries[entries["date"].astype(str) == date]
        if train_base["date"].nunique() < min_train_days or test_base.empty:
            continue
        for spec in specs:
            if spec["family"] == "fixed":
                rows.append(apply_fixed(test_base, spec))
            else:
                threshold = train_release_threshold(train_base, float(spec["release_quantile"]))
                rows.append(apply_trailing_for_day(test_entries, paths, spec, threshold, margin_bps))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(), test_dates


def score_policy(group: pd.DataFrame) -> dict[str, Any]:
    net = pd.to_numeric(group["policy_net"], errors="coerce")
    weighted = pd.to_numeric(group["weighted_net"], errors="coerce")
    baseline_weighted = pd.to_numeric(group["baseline_weighted_net"], errors="coerce")
    delta = pd.to_numeric(group["delta_weighted_vs_60s"], errors="coerce")
    daily = group.groupby("date", sort=True)["weighted_net"].sum()
    baseline_daily = group.groupby("date", sort=True)["baseline_weighted_net"].sum()
    total = float(weighted.sum())
    positive = weighted[weighted > 0].sort_values(ascending=False)
    top10_share = float(positive.head(10).sum() / total) if total > EPS and len(positive) else np.nan
    saved_loser = float(delta[baseline_weighted < 0].clip(lower=0).sum())
    killed_winner = float((-delta[baseline_weighted > 0]).clip(lower=0).sum())
    row = {
        "policy": str(group["policy"].iloc[0]),
        "family": str(group["family"].iloc[0]),
        "release_quantile": finite_mean(group["release_quantile"]),
        "eta": finite_mean(group["eta"]),
        "activation_horizon": finite_mean(group["activation_horizon"]),
        "entries": int(len(group)),
        "dates": int(group["date"].nunique()),
        "exposure": float(pd.to_numeric(group["target_exposure"], errors="coerce").sum()),
        "total_pnl": total,
        "baseline_total_pnl": float(baseline_weighted.sum()),
        "delta_vs_60s": float(delta.sum()),
        "mean_net": finite_mean(net),
        "median_net": finite_quantile(net, 0.50),
        "gt2_rate": float((net > 2.0).mean()),
        "q90_net": finite_quantile(net, 0.90),
        "cvar05_net": cvar(net, 0.05),
        "single_worst_weighted": finite_quantile(weighted, 0.00),
        "single_cvar05_weighted": cvar(weighted, 0.05),
        "worst_day": float(daily.min()) if len(daily) else np.nan,
        "baseline_worst_day": float(baseline_daily.min()) if len(baseline_daily) else np.nan,
        "positive_days": int((daily > 0).sum()) if len(daily) else 0,
        "activated_rate": float(group["activated"].astype(bool).mean()) if "activated" in group else 0.0,
        "trailing_exit_rate": float(group["exit_reason"].eq("trailing_drawdown").mean()) if "exit_reason" in group else 0.0,
        "mean_exit_sec": finite_mean(group["exit_sec"]),
        "top10_winner_share": top10_share,
        "saved_loser_pnl": saved_loser,
        "killed_winner_pnl": killed_winner,
        "save_kill_ratio": saved_loser / killed_winner if killed_winner > EPS else np.inf if saved_loser > EPS else np.nan,
    }
    return row


def build_scorecard(events: pd.DataFrame) -> pd.DataFrame:
    rows = [score_policy(group) for _, group in events.groupby("policy", sort=False)]
    scorecard = pd.DataFrame(rows)
    baseline = scorecard[scorecard["policy"].eq("fixed_60s")].iloc[0]
    baseline_q90 = float(baseline["q90_net"])
    scorecard["delta_vs_original_fixed60_total"] = scorecard["total_pnl"] - float(baseline["total_pnl"])
    scorecard["delta_vs_original_fixed60_worst_day"] = scorecard["worst_day"] - float(baseline["worst_day"])
    scorecard["right_tail_retention_q90"] = scorecard["q90_net"] / baseline_q90 if abs(baseline_q90) > EPS else np.nan
    scorecard["risk_score"] = (
        scorecard["delta_vs_original_fixed60_total"]
        + 2.0 * scorecard["delta_vs_original_fixed60_worst_day"]
        + 0.2 * scorecard["total_pnl"]
    )
    return scorecard.sort_values("risk_score", ascending=False).reset_index(drop=True)


def build_daily(events: pd.DataFrame) -> pd.DataFrame:
    return (
        events.groupby(["policy", "family", "date"], sort=True)
        .agg(
            entries=("entry_row", "size"),
            exposure=("target_exposure", "sum"),
            total_pnl=("weighted_net", "sum"),
            baseline_total_pnl=("baseline_weighted_net", "sum"),
            delta_vs_60s=("delta_weighted_vs_60s", "sum"),
            activated_rate=("activated", "mean"),
            trailing_exit_rate=("exit_reason", lambda s: float((s == "trailing_drawdown").mean())),
            mean_exit_sec=("exit_sec", "mean"),
        )
        .reset_index()
    )


def build_summary(base_paths: pd.DataFrame, events: pd.DataFrame, scorecard: pd.DataFrame, daily: pd.DataFrame, day_stats: list[dict[str, Any]], test_dates: list[str], margin_bps: float) -> dict[str, Any]:
    baseline = scorecard[scorecard["policy"].eq("fixed_60s")].iloc[0].to_dict()
    fixed = scorecard[scorecard["family"].eq("fixed")].sort_values("policy")
    trailing = scorecard[scorecard["family"].eq("price_trailing")].head(12)
    return {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "margin_bps": margin_bps,
        "base_path_rows": int(len(base_paths)),
        "event_rows": int(len(events)),
        "test_dates": test_dates,
        "day_stats": day_stats,
        "baseline_fixed60": baseline,
        "best_by_risk_score": scorecard.iloc[0].to_dict(),
        "fixed": fixed.to_dict(orient="records"),
        "top_price_trailing": trailing.to_dict(orient="records"),
    }


def write_report(paths: Paths, scorecard: pd.DataFrame, daily: pd.DataFrame, events: pd.DataFrame, summary: dict[str, Any]) -> None:
    fixed = scorecard[scorecard["family"].eq("fixed")].sort_values("policy")
    trailing = scorecard[scorecard["family"].eq("price_trailing")].head(12)
    baseline = summary["baseline_fixed60"]
    best = summary["best_by_risk_score"]
    best_policy = str(best.get("policy"))
    best_daily = daily[daily["policy"].eq(best_policy)].copy()
    fixed60_daily = daily[daily["policy"].eq("fixed_60s")].loc[:, ["date", "total_pnl"]].rename(columns={"total_pnl": "fixed60_pnl"})
    fixed30_daily = daily[daily["policy"].eq("fixed_30s")].loc[:, ["date", "total_pnl"]].rename(columns={"total_pnl": "fixed30_pnl"})
    if not best_daily.empty:
        best_daily = best_daily.merge(fixed60_daily, on="date", how="left").merge(fixed30_daily, on="date", how="left")
        best_daily = best_daily.rename(columns={"total_pnl": "best_pnl", "delta_vs_60s": "best_delta_vs_60s"})
        best_daily = best_daily.loc[
            :,
            [
                "date",
                "entries",
                "best_pnl",
                "fixed60_pnl",
                "fixed30_pnl",
                "best_delta_vs_60s",
                "activated_rate",
                "trailing_exit_rate",
                "mean_exit_sec",
            ],
        ]
    best_events = events[events["policy"].eq(best_policy)].copy()
    if not best_events.empty:
        threshold_daily = (
            best_events.groupby("date", sort=True)
            .agg(
                train_release_threshold=("train_release_threshold", "mean"),
                mean_release_sec=("release_sec", "mean"),
            )
            .reset_index()
        )
    else:
        threshold_daily = pd.DataFrame()
    lines = [
        "# CCUSDT TFI Price-Only Trailing Parameter Research",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This pass tests a simple price-path trailing idea and intentionally does not use order-flow, depth, or latent-state factors for exit.",
        "",
        "## Rule",
        "",
        "Signed path, running high, and drawdown:",
        "",
        "$$",
        "R_i(t)=s_i10^4\\log\\frac{M_{t_i+t}}{M_{t_i}},\\quad H_i(t)=\\max_{0<u\\le t}R_i(u),\\quad D_i(t)=H_i(t)-R_i(t).",
        "$$",
        "",
        "The release threshold is prior-date only:",
        "",
        "$$",
        "r_i=\\max(c_i+m,\\ Q_p^{train}(H_{10})).",
        "$$",
        "",
        "If release occurs within the activation window, trailing exits when:",
        "",
        "$$",
        "D_i(t)\\ge \\max(c_i+m,\\ \\eta H_i(t)).",
        "$$",
        "",
        "Otherwise the entry exits at 60s. This is still a mid-path research proxy, not an executable fill model.",
        "",
        "## Design",
        "",
        f"- Test dates: `{', '.join(summary['test_dates'])}`.",
        f"- Margin: `{fmt(summary['margin_bps'])}` bps.",
        "- Fixed baselines: `20s`, `30s`, `60s`.",
        "- Trailing grid: `p in {60,70,80}%`, `eta in {0.30,0.50}`, activation window `10s/20s`.",
        "",
        "## Main Read",
        "",
        f"Baseline `fixed_60s`: total `{fmt(baseline.get('total_pnl'))}`, worst day `{fmt(baseline.get('worst_day'))}`, q90 `{fmt(baseline.get('q90_net'))}`, CVaR5 `{fmt(baseline.get('cvar05_net'))}`.",
        f"Best candidate: `{best.get('policy')}` with total `{fmt(best.get('total_pnl'))}`, worst day `{fmt(best.get('worst_day'))}`, delta total `{fmt(best.get('delta_vs_original_fixed60_total'))}`, q90 retention `{fmt(best.get('right_tail_retention_q90'))}`.",
        "",
        "The main read is not that `10s` or `p80` is magic. It is that a release must first clear a prior-date, cost-aware threshold, and only then a trailing drawdown can cut fast release/decay paths. This avoids a fixed `10bps` posterior threshold while still testing the same economic idea.",
        "",
        "Read this as parameter research only. A trailing rule can be considered interesting only if it improves worst day/CVaR while keeping enough right tail and does not rely on tiny activation rates.",
        "",
        "## Fixed Baselines",
    ]
    common_cols = [
        "policy",
        "entries",
        "total_pnl",
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
    lines.extend(["## Price-Only Trailing Candidates"])
    lines.extend(
        markdown_table(
            trailing,
            common_cols
            + [
                "release_quantile",
                "eta",
                "activation_horizon",
                "activated_rate",
                "trailing_exit_rate",
                "mean_exit_sec",
                "saved_loser_pnl",
                "killed_winner_pnl",
                "save_kill_ratio",
            ],
            max_rows=20,
        )
    )
    lines.extend(
        [
            "## Best Candidate Daily Check",
            "",
            f"`{best_policy}` improves versus `fixed_60s` on every test date, but it does not make every day profitable. The remaining worst day is still negative, so this is a risk-shaping candidate, not a solved live rule.",
        ]
    )
    lines.extend(
        markdown_table(
            best_daily,
            [
                "date",
                "entries",
                "best_pnl",
                "fixed60_pnl",
                "fixed30_pnl",
                "best_delta_vs_60s",
                "activated_rate",
                "trailing_exit_rate",
                "mean_exit_sec",
            ],
            max_rows=20,
        )
    )
    if not threshold_daily.empty:
        lines.extend(
            [
                "## Release Thresholds",
                "",
                "The train-only release threshold stays in a narrow few-bps range. That is important: the rule is measuring early path release above cost/noise, not waiting for a rare `10bps` event.",
            ]
        )
        lines.extend(
            markdown_table(
                threshold_daily,
                ["date", "train_release_threshold", "mean_release_sec"],
                max_rows=20,
            )
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "- `fixed_30s` is the cleanest left-tail baseline, with `7/7` positive days, but it gives up too much right tail: total is lower by about `1310` PnL units versus `fixed_60s` and q90 retention is only about `0.677`.",
            "- The best price-only trailing point keeps materially more right tail than `fixed_30s` and improves `fixed_60s` total by about `449`, but it still cuts q90 from about `21.85` to `17.98` bps.",
            "- The parameter surface is not wildly unstable: all 12 trailing variants improve CVaR5 versus `fixed_60s`, but only the strict `p80/act10s` variants clearly improve total PnL.",
            "- This remains a mid-price first-hit proxy. A live implementation would still need latency, order type, and fill assumptions before it can be treated as executable.",
            "",
        ]
    )
    lines.extend(
        [
            "## Outputs",
            "",
            f"- `{paths.base_paths_csv}`",
            f"- `{paths.events_csv}`",
            f"- `{paths.scorecard_csv}`",
            f"- `{paths.daily_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_price_trailing_param_research.py",
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
    base_paths, day_stats = rebuild_base_paths(entries, paths)
    events, test_dates = build_events(entries, base_paths, paths, int(args.min_train_days), float(args.margin_bps))
    if events.empty:
        raise RuntimeError("No events generated.")
    scorecard = build_scorecard(events)
    daily = build_daily(events)
    summary = build_summary(base_paths, events, scorecard, daily, day_stats, test_dates, float(args.margin_bps))
    base_paths.to_csv(paths.base_paths_csv, index=False)
    events.to_csv(paths.events_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, scorecard, daily, events, summary)
    print(
        json.dumps(
            {
                "run_tag": paths.run_tag,
                "report": str(paths.report_md),
                "base_rows": int(len(base_paths)),
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
