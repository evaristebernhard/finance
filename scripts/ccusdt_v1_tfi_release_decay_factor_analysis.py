#!/usr/bin/env python
"""Release/decay path factor analysis for CCUSDT V1 TFI entries.

The older 60s label mixes three states: no release, release continuation, and
release followed by decay. This script rebuilds path labels at multiple
horizons and tests whether pre-entry and early-path factors separate release
from post-release decay.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


RUN_TAG = "20260518_ccusdt_v1_tfi_release_decay_factor_v1"
GUARDRAIL = "research_only_release_decay_factor_analysis_no_execution_recommendation"
LATENT_FILE_NAME = "ccusdt_v1_tfi_latent_state_panel_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv"
FACTOR_FILE_NAME = "ccusdt_v1_tfi_factor_decomp_entries_20260518_ccusdt_v1_tfi_factor_decomp_v1.csv"
US_PER_SECOND = 1_000_000.0
EPS = 1e-12

HORIZONS_SEC = [1, 3, 5, 10, 20, 60]
EARLY_INTERVALS_SEC = [(0, 1), (0, 3), (0, 5), (0, 10), (5, 20)]

LATENT_COLS = [
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
    "closed10_delta",
    "closed10_energy",
    "closed10_score_abs",
    "net",
    "gross",
    "cost",
    "weight",
    "target_gamma",
    "target_exposure",
    "target_pnl",
    "same_day_regime",
    "est_mean_net",
    "est_gt2_rate",
    "est_cvar05_net",
    "est_tail_share90",
    "entry_quality_class",
    "entry_event_index",
    "direction",
    "entry_spread_bps",
    "trade_window_count",
    "frames_since_mid_change",
    "past_event_25_bps",
    "x_raw",
    "x_fast_raw",
    "mlofi_raw_aligned",
    "mlofi25_raw_aligned",
    "ofi_raw_aligned",
    "past_release_raw",
    "log_opp_depth5_quote",
    "log_opp_depth25_quote",
    "log_opp_replenish",
    "log_opp_depletion",
    "spread_raw",
    "shock_raw",
    "microprice_raw_aligned",
    "obi5_raw_aligned",
    "X_t",
    "X_fast_t",
    "M_t",
    "O_t",
    "P_t",
    "Theta_t",
    "log_U_t",
    "A_absorption_t",
    "E_exhaustion_t",
    "C_confirm_t",
    "D_divergence_t",
    "release_score_t",
    "lambda_prior_top_u",
    "lambda_prior_top_x",
    "quality_side",
    "release_score",
    "absorption_score",
    "exhaustion_score",
    "vacuum_score",
    "chop_score",
    "bad_state_score",
    "good_state_score",
    "dominant_latent_state",
]

FACTOR_COLS = [
    "date",
    "entry_row",
    "base_weight",
    "overlay_boost",
    "mfe_bps",
    "mae_bps",
    "has_mid_transition",
    "has_quote_transition",
    "first_mid_transition_gross_bps",
    "first_quote_transition_gross_bps",
    "mid_transition_count",
    "quote_transition_count",
    "fixed_gross_bps",
    "fixed_net_maker_bps",
    "closed5_delta",
    "closed5_energy",
    "closed5_score_abs",
    "closed20_delta",
    "closed20_energy",
    "closed20_score_abs",
]

EVENT_COLS = [
    "event_index",
    "timestamp",
    "local_timestamp",
    "mid_price",
    "spread_bps",
    "microprice",
    "microprice_dev_bps",
    "trade_window_count",
    "trade_buy_amount",
    "trade_sell_amount",
    "trade_notional_quote",
    "trade_flow_imbalance",
    "ofi_l1_raw",
    "ofi_l1_depth_norm",
    "mlofi_raw_l1",
    "mlofi_raw_l5",
    "mlofi_raw_l25",
    "queue_imbalance_1",
    "queue_imbalance_5",
    "queue_imbalance_25",
    "bid_depth_5",
    "ask_depth_5",
    "bid_depth_25",
    "ask_depth_25",
    "execute_bid_amount",
    "execute_ask_amount",
    "depletion_bid_amount",
    "depletion_ask_amount",
    "replenish_bid_amount",
    "replenish_ask_amount",
    "liquidity_shock_score",
    "queue_depletion_intensity",
    "replenish_intensity",
    "cancellation_withdrawal_intensity",
]

ENTRY_FEATURES = [
    "entry_spread_bps",
    "trade_window_count",
    "frames_since_mid_change",
    "past_event_25_bps",
    "closed5_delta",
    "closed5_energy",
    "closed5_score_abs",
    "closed10_delta",
    "closed10_energy",
    "closed10_score_abs",
    "closed20_delta",
    "closed20_energy",
    "closed20_score_abs",
    "est_mean_net",
    "est_gt2_rate",
    "est_cvar05_net",
    "est_tail_share90",
    "x_raw",
    "x_fast_raw",
    "mlofi_raw_aligned",
    "mlofi25_raw_aligned",
    "ofi_raw_aligned",
    "past_release_raw",
    "log_opp_depth5_quote",
    "log_opp_depth25_quote",
    "log_opp_replenish",
    "log_opp_depletion",
    "spread_raw",
    "shock_raw",
    "microprice_raw_aligned",
    "obi5_raw_aligned",
    "X_t",
    "X_fast_t",
    "M_t",
    "O_t",
    "P_t",
    "Theta_t",
    "log_U_t",
    "A_absorption_t",
    "E_exhaustion_t",
    "C_confirm_t",
    "D_divergence_t",
    "release_score_t",
    "lambda_prior_top_u",
    "lambda_prior_top_x",
    "release_score",
    "absorption_score",
    "exhaustion_score",
    "vacuum_score",
    "chop_score",
    "bad_state_score",
    "good_state_score",
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
    def latent_csv(self) -> Path:
        return self.date_dir / LATENT_FILE_NAME

    @property
    def factor_csv(self) -> Path:
        return self.date_dir / FACTOR_FILE_NAME

    @property
    def path_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_release_decay_paths_{self.run_tag}.csv"

    @property
    def factor_scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_release_decay_factor_scorecard_{self.run_tag}.csv"

    @property
    def bucket_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_release_decay_buckets_{self.run_tag}.csv"

    @property
    def examples_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_release_decay_examples_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_release_decay_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-release-decay-factor-analysis-{self.run_tag}.md"

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
    parser.add_argument("--max-horizon-sec", type=int, default=60)
    return parser.parse_args()


def resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


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


def rate(values: pd.Series | np.ndarray) -> float:
    arr = pd.Series(values).dropna()
    return float(arr.astype(bool).mean()) if len(arr) else float("nan")


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


def safe_spearman(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    if len(frame) < 20 or frame["x"].nunique() < 3 or frame["y"].nunique() < 3:
        return float("nan")
    result = spearmanr(frame["x"], frame["y"])
    return float(result.correlation) if np.isfinite(result.correlation) else float("nan")


def load_entries(paths: Paths) -> pd.DataFrame:
    latent = pd.read_csv(paths.latent_csv, usecols=lambda col: col in LATENT_COLS)
    factor = pd.read_csv(paths.factor_csv, usecols=lambda col: col in FACTOR_COLS)
    entries = latent.merge(factor, on=["date", "entry_row"], how="left", suffixes=("", "_factor"))
    for col in ["entry_row", "entry_event_index"]:
        entries[col] = pd.to_numeric(entries[col], errors="coerce").astype("Int64")
    numeric_cols = [col for col in entries.columns if col not in {"date", "fold", "cell", "direction_label", "frames_q_bin", "delta10_bin", "energy10_bin", "z10_bin", "loss5_bin", "same_day_regime", "entry_quality_class", "quality_side", "dominant_latent_state"}]
    for col in numeric_cols:
        entries[col] = pd.to_numeric(entries[col], errors="coerce")
    return entries


def load_day_panel(paths: Paths, date: str) -> pd.DataFrame:
    day_dir = paths.day_dir(date)
    frames: list[pd.DataFrame] = []
    if not day_dir.exists():
        return pd.DataFrame(columns=EVENT_COLS)
    for csv_path in sorted(day_dir.glob("*.csv")):
        part = pd.read_csv(csv_path, usecols=lambda col: col in EVENT_COLS)
        if len(part):
            frames.append(part)
    if not frames:
        return pd.DataFrame(columns=EVENT_COLS)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["event_index", "local_timestamp", "mid_price"]).copy()
    panel["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").astype("int64")
    panel = panel.sort_values(["local_timestamp", "event_index"]).drop_duplicates("event_index", keep="last")
    return panel.reset_index(drop=True)


def nan_mean_slice(values: np.ndarray, start: int, end_exclusive: int) -> float:
    if end_exclusive <= start:
        return float("nan")
    arr = values[start:end_exclusive]
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else float("nan")


def nan_sum_slice(values: np.ndarray, start: int, end_exclusive: int) -> float:
    if end_exclusive <= start:
        return float("nan")
    arr = values[start:end_exclusive]
    arr = arr[np.isfinite(arr)]
    return float(arr.sum()) if len(arr) else float("nan")


def interval_pos(times: np.ndarray, t0: float, left_sec: int, right_sec: int) -> tuple[int, int]:
    start = int(np.searchsorted(times, t0 + left_sec * US_PER_SECOND, side="right"))
    end = int(np.searchsorted(times, t0 + right_sec * US_PER_SECOND, side="right"))
    return start, end


def add_interval_features(
    row: dict[str, Any],
    arrays: dict[str, np.ndarray],
    side: int,
    t0: float,
    mid0: float,
    left_sec: int,
    right_sec: int,
) -> None:
    start, end = interval_pos(arrays["local_timestamp"], t0, left_sec, right_sec)
    label = f"{left_sec}_{right_sec}s"
    if end <= start:
        for name in [
            "ret",
            "signed_tfi_mean",
            "signed_ofi_mean",
            "signed_mlofi5_mean",
            "signed_mlofi25_mean",
            "signed_qi5_mean",
            "signed_qi25_mean",
            "target_execute_sum",
            "adverse_execute_sum",
            "target_depletion_sum",
            "target_replenish_sum",
            "release_flow_sum",
            "spread_mean",
            "trade_notional_sum",
        ]:
            row[f"{name}_{label}"] = float("nan")
        return

    final_mid = arrays["mid_price"][end - 1]
    row[f"ret_{label}"] = side * 10_000.0 * np.log(max(final_mid, EPS) / max(mid0, EPS))
    row[f"signed_tfi_mean_{label}"] = side * nan_mean_slice(arrays["trade_flow_imbalance"], start, end)
    row[f"signed_ofi_mean_{label}"] = side * nan_mean_slice(arrays["ofi_l1_raw"], start, end)
    row[f"signed_mlofi5_mean_{label}"] = side * nan_mean_slice(arrays["mlofi_raw_l5"], start, end)
    row[f"signed_mlofi25_mean_{label}"] = side * nan_mean_slice(arrays["mlofi_raw_l25"], start, end)
    row[f"signed_qi5_mean_{label}"] = side * nan_mean_slice(arrays["queue_imbalance_5"], start, end)
    row[f"signed_qi25_mean_{label}"] = side * nan_mean_slice(arrays["queue_imbalance_25"], start, end)
    if side > 0:
        target_execute = arrays["execute_ask_amount"]
        adverse_execute = arrays["execute_bid_amount"]
        target_depletion = arrays["depletion_ask_amount"]
        target_replenish = arrays["replenish_ask_amount"]
    else:
        target_execute = arrays["execute_bid_amount"]
        adverse_execute = arrays["execute_ask_amount"]
        target_depletion = arrays["depletion_bid_amount"]
        target_replenish = arrays["replenish_bid_amount"]
    target_execute_sum = nan_sum_slice(target_execute, start, end)
    target_depletion_sum = nan_sum_slice(target_depletion, start, end)
    target_replenish_sum = nan_sum_slice(target_replenish, start, end)
    row[f"target_execute_sum_{label}"] = target_execute_sum
    row[f"adverse_execute_sum_{label}"] = nan_sum_slice(adverse_execute, start, end)
    row[f"target_depletion_sum_{label}"] = target_depletion_sum
    row[f"target_replenish_sum_{label}"] = target_replenish_sum
    row[f"release_flow_sum_{label}"] = target_execute_sum + target_depletion_sum - target_replenish_sum
    row[f"spread_mean_{label}"] = nan_mean_slice(arrays["spread_bps"], start, end)
    row[f"trade_notional_sum_{label}"] = nan_sum_slice(arrays["trade_notional_quote"], start, end)


def path_for_entry(entry: pd.Series, panel: pd.DataFrame, arrays: dict[str, np.ndarray], max_horizon_sec: int) -> dict[str, Any] | None:
    event_index = int(entry["entry_event_index"])
    event_indices = arrays["event_index"]
    pos = int(np.searchsorted(event_indices, event_index, side="left"))
    if pos >= len(event_indices):
        pos = len(event_indices) - 1
    if pos > 0 and abs(event_indices[pos] - event_index) > abs(event_indices[pos - 1] - event_index):
        pos -= 1
    t0 = float(arrays["local_timestamp"][pos])
    mid0 = float(arrays["mid_price"][pos])
    if not np.isfinite(mid0) or mid0 <= 0:
        return None
    side = 1 if str(entry["direction_label"]) == "long" else -1
    start = int(np.searchsorted(arrays["local_timestamp"], t0, side="right"))
    max_end = int(np.searchsorted(arrays["local_timestamp"], t0 + max_horizon_sec * US_PER_SECOND, side="right"))
    if max_end <= start:
        return None

    row: dict[str, Any] = {
        "date": entry["date"],
        "fold": entry.get("fold"),
        "entry_row": int(entry["entry_row"]),
        "entry_event_index": event_index,
        "matched_event_index": int(event_indices[pos]),
        "matched_event_distance": int(abs(event_indices[pos] - event_index)),
        "cell": entry["cell"],
        "direction_label": entry["direction_label"],
        "direction": side,
        "frames_q_bin": entry["frames_q_bin"],
        "delta10_bin": entry["delta10_bin"],
        "energy10_bin": entry["energy10_bin"],
        "z10_bin": entry["z10_bin"],
        "loss5_bin": entry["loss5_bin"],
        "quality_side": entry["quality_side"],
        "entry_quality_class": entry["entry_quality_class"],
        "dominant_latent_state": entry["dominant_latent_state"],
        "net": float(entry["net"]),
        "gross": float(entry["gross"]),
        "cost": float(entry["cost"]),
        "weight": float(entry["weight"]),
        "target_gamma": float(entry["target_gamma"]),
        "target_exposure": float(entry["target_exposure"]),
        "target_pnl": float(entry["target_pnl"]),
        "entry_mid": mid0,
        "entry_spread_bps_path": float(arrays["spread_bps"][pos]),
    }
    for feature in ENTRY_FEATURES:
        if feature in entry.index:
            try:
                row[feature] = float(entry[feature])
            except (TypeError, ValueError):
                row[feature] = np.nan

    for horizon in HORIZONS_SEC:
        if horizon > max_horizon_sec:
            continue
        end = int(np.searchsorted(arrays["local_timestamp"], t0 + horizon * US_PER_SECOND, side="right"))
        if end <= start:
            row[f"final_{horizon}s_bps"] = np.nan
            row[f"mfe_{horizon}s_bps"] = np.nan
            row[f"mae_{horizon}s_bps"] = np.nan
            row[f"t_mfe_{horizon}s_sec"] = np.nan
            row[f"t_mae_{horizon}s_sec"] = np.nan
            row[f"decay_{horizon}s_bps"] = np.nan
            continue
        mids = arrays["mid_price"][start:end]
        rets = side * 10_000.0 * np.log(np.maximum(mids, EPS) / max(mid0, EPS))
        times = (arrays["local_timestamp"][start:end] - t0) / US_PER_SECOND
        if not np.isfinite(rets).any():
            continue
        mfe_idx = int(np.nanargmax(rets))
        mae_idx = int(np.nanargmin(rets))
        final_ret = float(rets[-1])
        mfe = float(rets[mfe_idx])
        mae = float(rets[mae_idx])
        row[f"final_{horizon}s_bps"] = final_ret
        row[f"mfe_{horizon}s_bps"] = mfe
        row[f"mae_{horizon}s_bps"] = mae
        row[f"t_mfe_{horizon}s_sec"] = float(times[mfe_idx])
        row[f"t_mae_{horizon}s_sec"] = float(times[mae_idx])
        row[f"decay_{horizon}s_bps"] = mfe - final_ret

    for left_sec, right_sec in EARLY_INTERVALS_SEC:
        add_interval_features(row, arrays, side, t0, mid0, left_sec, right_sec)

    row["release_ge2_10s"] = bool(row.get("mfe_10s_bps", np.nan) >= 2.0)
    row["release_ge5_10s"] = bool(row.get("mfe_10s_bps", np.nan) >= 5.0)
    row["release_ge10_60s"] = bool(row.get("mfe_60s_bps", np.nan) >= 10.0)
    row["decay_ge5_60s"] = bool(row.get("decay_60s_bps", np.nan) >= 5.0)
    row["decay_ge10_60s"] = bool(row.get("decay_60s_bps", np.nan) >= 10.0)
    row["release10_then_loss60"] = bool(row.get("mfe_10s_bps", np.nan) >= 5.0 and row.get("final_60s_bps", np.nan) < 0.0)
    row["frontload_10_60_ratio"] = (
        float(row.get("mfe_10s_bps", np.nan) / max(row.get("mfe_60s_bps", np.nan), EPS))
        if np.isfinite(row.get("mfe_10s_bps", np.nan)) and np.isfinite(row.get("mfe_60s_bps", np.nan)) and row.get("mfe_60s_bps", np.nan) > 0
        else np.nan
    )
    return row


def rebuild_paths(entries: pd.DataFrame, paths: Paths, max_horizon_sec: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day_stats: list[dict[str, Any]] = []
    for date, group in entries.groupby("date", sort=True):
        panel = load_day_panel(paths, str(date))
        if panel.empty:
            day_stats.append({"date": str(date), "entries": int(len(group)), "path_rows": 0, "status": "missing_panel"})
            continue
        arrays = {col: pd.to_numeric(panel[col], errors="coerce").to_numpy(dtype="float64") for col in EVENT_COLS if col in panel.columns}
        arrays["event_index"] = pd.to_numeric(panel["event_index"], errors="coerce").to_numpy(dtype="int64")
        day_count_before = len(rows)
        for _, entry in group.iterrows():
            if pd.isna(entry.get("entry_event_index")):
                continue
            rebuilt = path_for_entry(entry, panel, arrays, max_horizon_sec=max_horizon_sec)
            if rebuilt is not None:
                rows.append(rebuilt)
        day_stats.append(
            {
                "date": str(date),
                "entries": int(len(group)),
                "path_rows": int(len(rows) - day_count_before),
                "panel_rows": int(len(panel)),
                "status": "ok",
            }
        )
    path_df = pd.DataFrame(rows)
    return path_df, {"day_stats": day_stats}


def feature_score_row(frame: pd.DataFrame, feature: str, target: str, universe: str, target_kind: str) -> dict[str, Any]:
    work = frame[[feature, target]].copy()
    work[feature] = pd.to_numeric(work[feature], errors="coerce")
    work[target] = pd.to_numeric(work[target], errors="coerce")
    work = work.dropna()
    row: dict[str, Any] = {
        "universe": universe,
        "target": target,
        "target_kind": target_kind,
        "feature": feature,
        "rows": int(len(work)),
    }
    if len(work) < 30 or work[feature].nunique() < 3:
        return row
    q20 = float(work[feature].quantile(0.20))
    q80 = float(work[feature].quantile(0.80))
    bottom = work[work[feature] <= q20]
    top = work[work[feature] >= q80]
    row.update(
        {
            "spearman": safe_spearman(work[feature], work[target]),
            "feature_q20": q20,
            "feature_q80": q80,
            "bottom_entries": int(len(bottom)),
            "top_entries": int(len(top)),
            "bottom_target_mean": finite_mean(bottom[target]),
            "top_target_mean": finite_mean(top[target]),
            "top_minus_bottom_target": finite_mean(top[target]) - finite_mean(bottom[target]),
            "bottom_target_median": finite_quantile(bottom[target], 0.50),
            "top_target_median": finite_quantile(top[target], 0.50),
        }
    )
    return row


def build_factor_scorecard(paths_df: pd.DataFrame) -> pd.DataFrame:
    early_features = [
        col
        for col in paths_df.columns
        if col.startswith(("ret_", "signed_", "target_", "adverse_", "release_flow_", "spread_mean_", "trade_notional_sum_"))
        and any(col.endswith(f"{a}_{b}s") for a, b in EARLY_INTERVALS_SEC)
    ]
    feature_sets = {
        "entry": [feature for feature in ENTRY_FEATURES if feature in paths_df.columns],
        "early_path": early_features,
    }
    specs: list[tuple[str, pd.DataFrame, str, str, str]] = [
        ("all", paths_df, "mfe_10s_bps", "release_continuous", "entry"),
        ("all", paths_df, "mfe_60s_bps", "release_continuous", "entry"),
        ("all", paths_df, "final_60s_bps", "terminal_continuous", "entry"),
        ("all", paths_df, "release10_then_loss60", "decay_flag", "entry"),
        ("released_mfe10_ge5", paths_df[paths_df["mfe_10s_bps"] >= 5.0], "decay_60s_bps", "decay_continuous", "entry"),
        ("released_mfe10_ge5", paths_df[paths_df["mfe_10s_bps"] >= 5.0], "final_60s_bps", "post_release_terminal", "entry"),
        ("released_mfe10_ge5", paths_df[paths_df["mfe_10s_bps"] >= 5.0], "decay_60s_bps", "decay_continuous", "early_path"),
        ("released_mfe10_ge5", paths_df[paths_df["mfe_10s_bps"] >= 5.0], "final_60s_bps", "post_release_terminal", "early_path"),
    ]
    rows: list[dict[str, Any]] = []
    for universe, frame, target, target_kind, feature_scope in specs:
        if target not in frame.columns or frame.empty:
            continue
        tmp = frame.copy()
        if tmp[target].dtype == bool:
            tmp[target] = tmp[target].astype(float)
        for feature in feature_sets[feature_scope]:
            row = feature_score_row(tmp, feature, target, universe, target_kind)
            row["feature_scope"] = feature_scope
            rows.append(row)
    scorecard = pd.DataFrame(rows)
    if scorecard.empty:
        return scorecard
    scorecard["abs_spearman"] = pd.to_numeric(scorecard["spearman"], errors="coerce").abs()
    scorecard["abs_top_minus_bottom"] = pd.to_numeric(scorecard["top_minus_bottom_target"], errors="coerce").abs()
    return scorecard.sort_values(["target", "universe", "abs_spearman", "abs_top_minus_bottom"], ascending=[True, True, False, False]).reset_index(drop=True)


def bucket_stats(group: pd.DataFrame, view: str, key: str) -> dict[str, Any]:
    return {
        "view": view,
        "bucket": key,
        "entries": int(len(group)),
        "exposure": float(pd.to_numeric(group["target_exposure"], errors="coerce").sum()),
        "target_pnl": float(pd.to_numeric(group["target_pnl"], errors="coerce").sum()),
        "net_mean": finite_mean(group["net"]),
        "final_60_mean": finite_mean(group["final_60s_bps"]),
        "final_60_median": finite_quantile(group["final_60s_bps"], 0.50),
        "mfe_5_mean": finite_mean(group["mfe_5s_bps"]),
        "mfe_10_mean": finite_mean(group["mfe_10s_bps"]),
        "mfe_60_mean": finite_mean(group["mfe_60s_bps"]),
        "decay_60_mean": finite_mean(group["decay_60s_bps"]),
        "decay_60_median": finite_quantile(group["decay_60s_bps"], 0.50),
        "release_ge5_10_rate": rate(group["release_ge5_10s"]),
        "release_ge10_60_rate": rate(group["release_ge10_60s"]),
        "decay_ge10_60_rate": rate(group["decay_ge10_60s"]),
        "release10_then_loss60_rate": rate(group["release10_then_loss60"]),
        "frontload_10_60_mean": finite_mean(group["frontload_10_60_ratio"]),
        "cvar05_final_60": cvar(group["final_60s_bps"], 0.05),
    }


def build_bucket_diagnostics(paths_df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("cell", ["cell"]),
        ("direction", ["direction_label"]),
        ("quality_side", ["quality_side"]),
        ("dominant_latent_state", ["dominant_latent_state"]),
        ("cell_x_direction", ["cell", "direction_label"]),
        ("cell_x_direction_x_frames", ["cell", "direction_label", "frames_q_bin"]),
        ("cell_x_direction_x_frames_x_delta10", ["cell", "direction_label", "frames_q_bin", "delta10_bin"]),
        ("quality_x_state", ["quality_side", "dominant_latent_state"]),
    ]
    rows: list[dict[str, Any]] = []
    for view, cols in specs:
        for key, group in paths_df.groupby(cols, dropna=False, sort=True):
            if len(group) < 5:
                continue
            key_text = "|".join(map(str, key if isinstance(key, tuple) else (key,)))
            rows.append(bucket_stats(group, view, key_text))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["release10_then_loss60_rate", "decay_60_mean", "entries"], ascending=[False, False, False]).reset_index(drop=True)


def build_examples(paths_df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "date",
        "entry_row",
        "entry_event_index",
        "cell",
        "direction_label",
        "frames_q_bin",
        "delta10_bin",
        "energy10_bin",
        "z10_bin",
        "quality_side",
        "dominant_latent_state",
        "net",
        "target_exposure",
        "target_pnl",
        "final_60s_bps",
        "mfe_5s_bps",
        "mfe_10s_bps",
        "mfe_60s_bps",
        "decay_60s_bps",
        "t_mfe_60s_sec",
        "release10_then_loss60",
        "ret_0_5s",
        "signed_tfi_mean_0_5s",
        "signed_qi5_mean_0_5s",
        "signed_mlofi5_mean_0_5s",
        "target_replenish_sum_0_5s",
        "release_flow_sum_0_5s",
    ]
    cols = [col for col in cols if col in paths_df.columns]
    release_decay = paths_df[paths_df["release10_then_loss60"]].sort_values("decay_60s_bps", ascending=False).head(40)
    no_release = paths_df[paths_df["mfe_10s_bps"] < 2.0].sort_values("final_60s_bps").head(30)
    continuation = paths_df[(paths_df["mfe_10s_bps"] >= 5.0) & (paths_df["final_60s_bps"] > 5.0)].sort_values("final_60s_bps", ascending=False).head(40)
    parts = []
    for name, frame in [("release_then_decay", release_decay), ("no_release_bad", no_release), ("release_continuation", continuation)]:
        if len(frame):
            tmp = frame.loc[:, cols].copy()
            tmp.insert(0, "example_type", name)
            parts.append(tmp)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["example_type", *cols])


def build_summary(paths_df: pd.DataFrame, scorecard: pd.DataFrame, buckets: pd.DataFrame, path_meta: dict[str, Any], paths: Paths) -> dict[str, Any]:
    rebuilt_dates = sorted(paths_df["date"].astype(str).unique().tolist()) if len(paths_df) else []
    def best_row(target: str, universe: str, scope: str) -> dict[str, Any]:
        subset = scorecard[
            scorecard["target"].eq(target)
            & scorecard["universe"].eq(universe)
            & scorecard["feature_scope"].eq(scope)
        ].copy()
        if subset.empty:
            return {}
        subset = subset.sort_values(["abs_spearman", "abs_top_minus_bottom"], ascending=False)
        return subset.iloc[0].to_dict()

    high_decay_buckets = buckets[
        (buckets["entries"] >= 20)
        & (buckets["release_ge5_10_rate"] >= 0.25)
    ].sort_values(["release10_then_loss60_rate", "decay_60_mean"], ascending=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "path_entries": int(len(paths_df)),
        "rebuilt_dates": rebuilt_dates,
        "day_stats": path_meta.get("day_stats", []),
        "mfe_5_mean": finite_mean(paths_df.get("mfe_5s_bps", pd.Series(dtype=float))),
        "mfe_10_mean": finite_mean(paths_df.get("mfe_10s_bps", pd.Series(dtype=float))),
        "mfe_60_mean": finite_mean(paths_df.get("mfe_60s_bps", pd.Series(dtype=float))),
        "final_60_mean": finite_mean(paths_df.get("final_60s_bps", pd.Series(dtype=float))),
        "decay_60_mean": finite_mean(paths_df.get("decay_60s_bps", pd.Series(dtype=float))),
        "release_ge5_10_rate": rate(paths_df.get("release_ge5_10s", pd.Series(dtype=bool))),
        "release_ge10_60_rate": rate(paths_df.get("release_ge10_60s", pd.Series(dtype=bool))),
        "release10_then_loss60_rate": rate(paths_df.get("release10_then_loss60", pd.Series(dtype=bool))),
        "decay_ge10_60_rate": rate(paths_df.get("decay_ge10_60s", pd.Series(dtype=bool))),
        "released_mfe10_ge5_entries": int((paths_df.get("mfe_10s_bps", pd.Series(dtype=float)) >= 5.0).sum()),
        "best_entry_release_mfe10": best_row("mfe_10s_bps", "all", "entry"),
        "best_entry_decay60": best_row("decay_60s_bps", "released_mfe10_ge5", "entry"),
        "best_early_decay60": best_row("decay_60s_bps", "released_mfe10_ge5", "early_path"),
        "high_decay_buckets": high_decay_buckets.head(10).to_dict(orient="records"),
    }
    return summary


def write_report(
    paths: Paths,
    paths_df: pd.DataFrame,
    scorecard: pd.DataFrame,
    buckets: pd.DataFrame,
    examples: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    best_release = summary.get("best_entry_release_mfe10", {})
    best_entry_decay = summary.get("best_entry_decay60", {})
    best_early_decay = summary.get("best_early_decay60", {})

    release_top = scorecard[
        scorecard["target"].eq("mfe_10s_bps")
        & scorecard["universe"].eq("all")
        & scorecard["feature_scope"].eq("entry")
    ].sort_values("abs_spearman", ascending=False)
    decay_entry_top = scorecard[
        scorecard["target"].eq("decay_60s_bps")
        & scorecard["universe"].eq("released_mfe10_ge5")
        & scorecard["feature_scope"].eq("entry")
    ].sort_values("abs_spearman", ascending=False)
    decay_early_top = scorecard[
        scorecard["target"].eq("decay_60s_bps")
        & scorecard["universe"].eq("released_mfe10_ge5")
        & scorecard["feature_scope"].eq("early_path")
    ].sort_values("abs_spearman", ascending=False)

    bucket_focus = buckets[
        (buckets["entries"] >= 20)
        & (buckets["release_ge5_10_rate"] >= 0.20)
    ].sort_values(["release10_then_loss60_rate", "decay_60_mean"], ascending=False)

    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT TFI Release/Decay Factor Analysis",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This report replaces the blunt 60s terminal read with a path read: whether an entry releases first, and whether that release decays before the 60s mark.",
            "",
            "## Labels",
            "",
            "For entry direction $s_i$, signed path is:",
            "",
            "$$",
            "R_i(\\tau)=s_i\\,10^4\\log\\frac{M_{t_i+\\tau}}{M_{t_i}}.",
            "$$",
            "",
            "Release and decay labels are:",
            "",
            "$$",
            "\\mathrm{MFE}_i(h)=\\max_{0<\\tau\\le h}R_i(\\tau),\\qquad D_i(60)=\\mathrm{MFE}_i(60)-R_i(60).",
            "$$",
            "",
            "The key failure mode is:",
            "",
            "$$",
            "\\mathrm{MFE}_i(10)\\ge 5\\ \\mathrm{bps},\\qquad R_i(60)<0.",
            "$$",
            "",
            "## Scope",
            "",
            f"- Rebuilt path entries: `{summary.get('path_entries')}`.",
            f"- Rebuilt dates: `{', '.join(summary.get('rebuilt_dates', []))}`.",
            f"- Missing panel dates are skipped; in this workspace v3 panel is present through `2026-05-15`.",
            "",
            "## Main Read",
            "",
            f"1. Mean MFE is `{fmt(summary.get('mfe_5_mean'))}` bps at 5s, `{fmt(summary.get('mfe_10_mean'))}` bps at 10s, and `{fmt(summary.get('mfe_60_mean'))}` bps at 60s.",
            f"2. Mean 60s terminal return is `{fmt(summary.get('final_60_mean'))}` bps, while mean 60s decay from peak is `{fmt(summary.get('decay_60_mean'))}` bps.",
            f"3. `P(MFE_10>=5bps)` is `{fmt(summary.get('release_ge5_10_rate'))}`; `P(MFE_10>=5bps and R_60<0)` is `{fmt(summary.get('release10_then_loss60_rate'))}`.",
            f"4. Best entry-time release factor by absolute Spearman is `{best_release.get('feature')}` with Spearman `{fmt(best_release.get('spearman'))}` against `MFE_10`.",
            f"5. Conditional on early release, best entry-time decay factor is `{best_entry_decay.get('feature')}` with Spearman `{fmt(best_entry_decay.get('spearman'))}` against `D_60`.",
            f"6. Conditional on early release, best early-path decay factor is `{best_early_decay.get('feature')}` with Spearman `{fmt(best_early_decay.get('spearman'))}` against `D_60`.",
            "",
            "Interpretation: this is still mostly factor analysis, not a complicated latent model. The important shift is that the factor target is no longer only $R(60)$. We now ask which factors predict `release`, and which factors warn that release is already decaying.",
            "",
            "The first-principles read is simple:",
            "",
            "- Low opposite-side depth / low absorption threshold predicts faster release. This shows up as negative Spearman for `log_opp_depth25_quote`, `log_opp_depth5_quote`, and `Theta_t` against `MFE_10`.",
            "- The same low-depth condition also predicts larger decay after early release. That means part of the edge is a liquidity-vacuum release, not necessarily persistent order-flow continuation.",
            "- After release has happened, the useful dynamic factor is sustained signed flow from 5s to 20s. Higher `signed_tfi_mean_5_20s`, `signed_mlofi5_mean_5_20s`, and `signed_ofi_mean_5_20s` correspond to lower `D_60`.",
            "- Queue imbalance is more ambiguous than flow: in this pass, high signed queue imbalance after release is associated with more decay, so queue shape alone should not be treated as continuation without replenishment/depletion context.",
            "",
            "## Entry Factors For 10s Release",
        ]
    )
    lines.extend(
        markdown_table(
            release_top,
            [
                "feature",
                "rows",
                "spearman",
                "bottom_target_mean",
                "top_target_mean",
                "top_minus_bottom_target",
                "feature_q20",
                "feature_q80",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Entry Factors For 60s Decay After Early Release"])
    lines.extend(
        markdown_table(
            decay_entry_top,
            [
                "feature",
                "rows",
                "spearman",
                "bottom_target_mean",
                "top_target_mean",
                "top_minus_bottom_target",
                "feature_q20",
                "feature_q80",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Early-Path Factors For 60s Decay After Early Release"])
    lines.extend(
        markdown_table(
            decay_early_top,
            [
                "feature",
                "rows",
                "spearman",
                "bottom_target_mean",
                "top_target_mean",
                "top_minus_bottom_target",
                "feature_q20",
                "feature_q80",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Buckets With Release-Then-Decay Risk"])
    lines.extend(
        markdown_table(
            bucket_focus,
            [
                "view",
                "bucket",
                "entries",
                "final_60_mean",
                "mfe_10_mean",
                "decay_60_mean",
                "release_ge5_10_rate",
                "release10_then_loss60_rate",
                "frontload_10_60_mean",
                "target_pnl",
            ],
            max_rows=30,
        )
    )
    lines.extend(["## Examples"])
    lines.extend(
        markdown_table(
            examples,
            [
                "example_type",
                "date",
                "entry_row",
                "cell",
                "direction_label",
                "frames_q_bin",
                "delta10_bin",
                "net",
                "target_exposure",
                "final_60s_bps",
                "mfe_10s_bps",
                "mfe_60s_bps",
                "decay_60s_bps",
                "ret_0_5s",
                "signed_qi5_mean_0_5s",
                "release_flow_sum_0_5s",
            ],
            max_rows=30,
        )
    )
    lines.extend(
        [
            "## Outputs",
            "",
            f"- `{paths.path_csv}`",
            f"- `{paths.factor_scorecard_csv}`",
            f"- `{paths.bucket_csv}`",
            f"- `{paths.examples_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_release_decay_factor_analysis.py",
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
    paths_df, path_meta = rebuild_paths(entries, paths, max_horizon_sec=int(args.max_horizon_sec))
    if paths_df.empty:
        raise RuntimeError("No paths rebuilt; check panel root and run tag.")

    scorecard = build_factor_scorecard(paths_df)
    buckets = build_bucket_diagnostics(paths_df)
    examples = build_examples(paths_df)
    summary = build_summary(paths_df, scorecard, buckets, path_meta, paths)

    paths_df.to_csv(paths.path_csv, index=False)
    scorecard.to_csv(paths.factor_scorecard_csv, index=False)
    buckets.to_csv(paths.bucket_csv, index=False)
    examples.to_csv(paths.examples_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, paths_df, scorecard, buckets, examples, summary)

    print(
        json.dumps(
            {
                "run_tag": paths.run_tag,
                "report": str(paths.report_md),
                "path_entries": int(len(paths_df)),
                "mfe_10_mean": summary["mfe_10_mean"],
                "final_60_mean": summary["final_60_mean"],
                "decay_60_mean": summary["decay_60_mean"],
                "release10_then_loss60_rate": summary["release10_then_loss60_rate"],
                "best_early_decay_feature": summary.get("best_early_decay60", {}).get("feature"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
