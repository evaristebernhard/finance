#!/usr/bin/env python
"""Estimate CCUSDT TFI pressure/absorption core quantities.

The estimates are pre-trade quantities: they use event-panel order-flow and
book-state fields available at or before the entry event. Future gross/net
labels are used only for diagnostic readouts.
"""

from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)


RUN_TAG = "20260518_ccusdt_v1_tfi_core_quantity_estimation_v1"
GUARDRAIL = "research_only_core_quantity_estimation_no_execution_recommendation_no_alpha_claim"
SYMBOL = "CCUSDT"
EPS = 1e-12
MIN_PRIOR_PANEL_ROWS = 10_000

DEFAULT_PANEL_RUN_TAGS = [
    "20260517_ccusdt_fixed_factors_v3",
    "20260518_ccusdt_fixed_factors_oos_day20260516_v1",
    "20260518_ccusdt_fixed_factors_oos_day20260517_v1",
]

ENTRY_FILE_NAME = "ccusdt_v1_tfi_pretrade_scored_entries_20260518_ccusdt_v1_tfi_pretrade_identification_v1.csv"

PANEL_COLS = [
    "date",
    "event_index",
    "local_timestamp",
    "mid_price",
    "spread_bps",
    "trade_flow_imbalance",
    "ofi_l1_depth_norm",
    "mlofi_roll10_l1",
    "mlofi_roll10_l5",
    "mlofi_roll10_l25",
    "bid_depth_5",
    "ask_depth_5",
    "bid_depth_25",
    "ask_depth_25",
    "replenish_bid_amount",
    "replenish_ask_amount",
    "depletion_bid_amount",
    "depletion_ask_amount",
    "cancel_bid_amount",
    "cancel_ask_amount",
    "liquidity_shock_score",
    "queue_depletion_intensity",
    "replenish_intensity",
    "cancellation_withdrawal_intensity",
    "microprice_dev_bps",
    "queue_imbalance_5",
]

ENTRY_COLS = [
    "fold",
    "date",
    "entry_row",
    "entry_event_index",
    "entry_local_timestamp",
    "direction",
    "entry_spread_bps",
    "fixed_gross_bps",
    "fixed_cost_maker_bps",
    "fixed_net_maker_bps",
    "mfe_bps",
    "mae_bps",
    "membership_set",
    "feature_value",
    "trade_window_count",
    "frames_since_mid_change",
    "past_event_25_bps",
    "segment",
    "net",
    "gross",
    "cost",
    "weight",
    "gate_r_n5",
    "gate_frames_q90",
    "gate_r5_and_frames_q90",
]


@dataclass(frozen=True)
class Paths:
    panel_root: Path
    panel_run_tags: tuple[str, ...]
    date_dir: Path
    doc_dir: Path
    entries_csv: Path
    symbol: str
    run_tag: str

    @property
    def scored_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_core_quantity_scored_entries_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_core_quantity_scorecard_{self.run_tag}.csv"

    @property
    def joint_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_core_quantity_joint_bins_{self.run_tag}.csv"

    @property
    def direction_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_core_quantity_direction_{self.run_tag}.csv"

    @property
    def lambda_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_core_quantity_lambda_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_core_quantity_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-core-quantity-estimation-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate TFI pressure/absorption core quantities.")
    parser.add_argument(
        "--panel-root",
        type=Path,
        default=Path("data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel"),
    )
    parser.add_argument("--panel-run-tags", default=",".join(DEFAULT_PANEL_RUN_TAGS))
    parser.add_argument("--entries-csv", type=Path, default=Path("date") / ENTRY_FILE_NAME)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--pressure-span-events", type=int, default=25)
    parser.add_argument("--fast-pressure-span-events", type=int, default=10)
    parser.add_argument("--past-event-horizon", type=int, default=25)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def finite(values: Iterable[float] | np.ndarray | pd.Series) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return arr[np.isfinite(arr)]


def finite_mean(values: Iterable[float] | np.ndarray | pd.Series) -> float:
    arr = finite(values)
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: Iterable[float] | np.ndarray | pd.Series, q: float) -> float:
    arr = finite(values)
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def cvar(values: Iterable[float] | np.ndarray | pd.Series, q: float = 0.05) -> float:
    arr = finite(values)
    if not len(arr):
        return np.nan
    cutoff = np.quantile(arr, q)
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > EPS else np.nan


def robust_params(values: pd.Series | np.ndarray) -> tuple[float, float]:
    arr = finite(values)
    if len(arr) < 100:
        return np.nan, np.nan
    med = float(np.median(arr))
    q75 = float(np.quantile(arr, 0.75))
    q25 = float(np.quantile(arr, 0.25))
    scale = q75 - q25
    if not np.isfinite(scale) or scale <= EPS:
        scale = float(np.std(arr))
    if not np.isfinite(scale) or scale <= EPS:
        scale = 1.0
    return med, scale


def robust_z(values: pd.Series | np.ndarray, med: float, scale: float) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    if not np.isfinite(med) or not np.isfinite(scale) or scale <= EPS:
        return np.full(len(arr), np.nan)
    return (arr - med) / scale


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 25) -> list[str]:
    if df.empty:
        return ["", "_No rows._", ""]
    cols = [col for col in columns if col in df.columns]
    view = df.loc[:, cols].head(max_rows).copy()
    lines = ["", "| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        cells: list[str] = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def discover_panel_files(paths: Paths) -> list[Path]:
    files: list[Path] = []
    for run_tag in paths.panel_run_tags:
        root = paths.panel_root / f"run_tag={run_tag}" / f"symbol={paths.symbol}"
        files.extend(sorted(root.rglob("*.csv")))
    if not files:
        raise FileNotFoundError(f"no panel files under {paths.panel_root}")
    return files


def load_panel(paths: Paths, pressure_span: int, fast_span: int, past_event_horizon: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in discover_panel_files(paths):
        header = pd.read_csv(path, nrows=0).columns
        usecols = [col for col in PANEL_COLS if col in header]
        chunk = pd.read_csv(path, usecols=usecols)
        frames.append(chunk)
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = panel["date"].astype(str)
    for col in panel.columns:
        if col != "date":
            panel[col] = pd.to_numeric(panel[col], errors="coerce")
    panel = panel.dropna(subset=["date", "event_index", "mid_price"]).copy()
    panel["event_index"] = panel["event_index"].astype("int64")
    panel = panel.sort_values(["date", "event_index", "local_timestamp"]).drop_duplicates(["date", "event_index"], keep="last")
    panel = panel.sort_values(["date", "event_index"]).reset_index(drop=True)

    out_frames: list[pd.DataFrame] = []
    for _, day in panel.groupby("date", sort=True):
        day = day.copy()
        tfi = pd.to_numeric(day["trade_flow_imbalance"], errors="coerce").fillna(0.0)
        day["x_tfi_ewm"] = tfi.ewm(span=pressure_span, adjust=False).mean()
        day["x_tfi_fast_ewm"] = tfi.ewm(span=fast_span, adjust=False).mean()
        day["past_event_panel_bps"] = 10_000.0 * np.log(day["mid_price"] / day["mid_price"].shift(past_event_horizon))
        out_frames.append(day)
    return pd.concat(out_frames, ignore_index=True)


def load_entries(paths: Paths) -> pd.DataFrame:
    header = pd.read_csv(paths.entries_csv, nrows=0).columns
    usecols = [col for col in ENTRY_COLS if col in header]
    df = pd.read_csv(paths.entries_csv, usecols=usecols)
    df["date"] = df["date"].astype(str)
    for col in df.columns:
        if col not in ["fold", "date", "membership_set", "segment"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["direction"] = df["direction"].astype("int64")
    df["entry_event_index"] = df["entry_event_index"].astype("int64")
    if "net" not in df.columns:
        df["net"] = df["fixed_net_maker_bps"]
    if "gross" not in df.columns:
        df["gross"] = df["fixed_gross_bps"]
    if "cost" not in df.columns:
        df["cost"] = df["fixed_cost_maker_bps"]
    return df.sort_values(["date", "entry_event_index", "entry_row"]).reset_index(drop=True)


def add_directional_raw(panel: pd.DataFrame, direction: int) -> pd.DataFrame:
    out = panel.copy()
    d = float(direction)
    if direction > 0:
        opp_depth5 = out["ask_depth_5"]
        opp_depth25 = out["ask_depth_25"]
        opp_replenish = out["replenish_ask_amount"]
        opp_depletion = out["depletion_ask_amount"].fillna(0.0) + out["cancel_ask_amount"].fillna(0.0)
    else:
        opp_depth5 = out["bid_depth_5"]
        opp_depth25 = out["bid_depth_25"]
        opp_replenish = out["replenish_bid_amount"]
        opp_depletion = out["depletion_bid_amount"].fillna(0.0) + out["cancel_bid_amount"].fillna(0.0)
    mid = out["mid_price"].replace(0.0, np.nan)
    out["direction"] = direction
    out["x_raw"] = d * out["x_tfi_ewm"]
    out["x_fast_raw"] = d * out["x_tfi_fast_ewm"]
    out["mlofi_raw_aligned"] = d * out["mlofi_roll10_l1"]
    out["mlofi25_raw_aligned"] = d * out["mlofi_roll10_l25"]
    out["ofi_raw_aligned"] = d * out["ofi_l1_depth_norm"]
    out["past_release_raw"] = d * out["past_event_panel_bps"]
    out["opp_depth5_quote_raw"] = opp_depth5 * mid
    out["opp_depth25_quote_raw"] = opp_depth25 * mid
    out["log_opp_depth5_quote"] = np.log1p(out["opp_depth5_quote_raw"].clip(lower=0.0))
    out["log_opp_depth25_quote"] = np.log1p(out["opp_depth25_quote_raw"].clip(lower=0.0))
    out["log_opp_replenish"] = np.log1p(opp_replenish.fillna(0.0).clip(lower=0.0))
    out["log_opp_depletion"] = np.log1p(opp_depletion.fillna(0.0).clip(lower=0.0))
    out["spread_raw"] = out["spread_bps"]
    out["shock_raw"] = out["liquidity_shock_score"]
    out["microprice_raw_aligned"] = d * out["microprice_dev_bps"]
    out["obi5_raw_aligned"] = d * out["queue_imbalance_5"]
    return out


def build_entry_base(panel: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    directional_frames = [add_directional_raw(panel, direction) for direction in [1, -1]]
    directional = pd.concat(directional_frames, ignore_index=True)
    cols = [
        "date",
        "event_index",
        "direction",
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
    ]
    base = directional.loc[:, cols]
    merged = entries.merge(
        base,
        left_on=["date", "entry_event_index", "direction"],
        right_on=["date", "event_index", "direction"],
        how="left",
        validate="many_to_one",
    )
    if merged["x_raw"].isna().mean() > 0.05:
        missing = merged.loc[merged["x_raw"].isna(), ["date", "entry_event_index", "direction"]].head(10)
        raise ValueError(f"too many entries missing event-panel merge; examples={missing.to_dict(orient='records')}")
    return merged


def train_directional_panel(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([add_directional_raw(panel, direction) for direction in [1, -1]], ignore_index=True)


NORMALIZE_COLS = [
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
]


def add_expanding_z(entries: pd.DataFrame, directional_panel: pd.DataFrame) -> pd.DataFrame:
    out_frames: list[pd.DataFrame] = []
    dates = sorted(entries["date"].dropna().astype(str).unique())
    for date in dates:
        for direction in [-1, 1]:
            test_mask = entries["date"].eq(date) & entries["direction"].eq(direction)
            if not test_mask.any():
                continue
            train = directional_panel[(directional_panel["date"] < date) & directional_panel["direction"].eq(direction)]
            if len(train) < MIN_PRIOR_PANEL_ROWS:
                train = directional_panel[directional_panel["direction"].eq(direction)]
            test = entries.loc[test_mask].copy()
            for col in NORMALIZE_COLS:
                med, scale = robust_params(train[col])
                test[f"{col}_z"] = robust_z(test[col], med, scale)
            out_frames.append(test)
    out = pd.concat(out_frames, ignore_index=True)
    out = out.sort_values(["date", "entry_event_index", "entry_row"]).reset_index(drop=True)
    return out


def add_core_scores(entries: pd.DataFrame) -> pd.DataFrame:
    out = entries.copy()
    out["X_t"] = out["x_raw_z"]
    out["X_fast_t"] = out["x_fast_raw_z"]
    out["M_t"] = out["mlofi_raw_aligned_z"]
    out["O_t"] = out["ofi_raw_aligned_z"]
    out["P_t"] = out["past_release_raw_z"]
    out["Theta_t"] = (
        0.80 * out["log_opp_depth5_quote_z"]
        + 0.50 * out["log_opp_replenish_z"]
        + 0.30 * out["spread_raw_z"]
        - 0.70 * out["log_opp_depletion_z"]
    )
    out["log_U_t"] = out["X_t"] - out["Theta_t"]
    out["U_t"] = np.exp(np.clip(out["log_U_t"], -5.0, 5.0))
    out["A_absorption_t"] = (
        out["X_t"]
        + 0.70 * out["log_opp_replenish_z"]
        + 0.40 * out["log_opp_depth5_quote_z"]
        - 0.70 * np.maximum(out["P_t"], 0.0)
        - 0.30 * out["log_opp_depletion_z"]
    )
    out["E_exhaustion_t"] = (
        np.maximum(out["P_t"], 0.0)
        + 0.50 * out["spread_raw_z"]
        + 0.30 * out["shock_raw_z"]
        - 0.60 * np.maximum(out["X_t"], 0.0)
    )
    out["C_confirm_t"] = 0.60 * out["M_t"] + 0.40 * out["O_t"]
    out["D_divergence_t"] = out["X_t"] - out["C_confirm_t"]
    out["release_score_t"] = out["log_U_t"] + 0.50 * out["C_confirm_t"] - 0.35 * out["E_exhaustion_t"]
    out["aligned_gross_bps"] = out["gross"]
    out["aligned_net_bps"] = out["net"]
    return out


def add_prior_lambda(entries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = entries.copy()
    lambda_rows: list[dict[str, Any]] = []
    out["lambda_prior_top_u"] = np.nan
    out["lambda_prior_top_x"] = np.nan
    for date in sorted(out["date"].dropna().astype(str).unique()):
        for direction in [-1, 1]:
            prior = out[(out["date"] < date) & out["direction"].eq(direction)].copy()
            current_mask = out["date"].eq(date) & out["direction"].eq(direction)
            row: dict[str, Any] = {
                "date": date,
                "direction": direction,
                "prior_entries": int(len(prior)),
                "lambda_top_u_gross_per_logu": np.nan,
                "lambda_top_x_gross_per_x": np.nan,
                "top_u_mean_gross": np.nan,
                "top_x_mean_gross": np.nan,
            }
            if len(prior) >= 50:
                u_cut = finite_quantile(prior["log_U_t"], 0.70)
                x_cut = finite_quantile(prior["X_t"], 0.70)
                top_u = prior[prior["log_U_t"].ge(u_cut) & prior["log_U_t"].gt(0.0)]
                top_x = prior[prior["X_t"].ge(x_cut) & prior["X_t"].gt(0.0)]
                if len(top_u):
                    den = finite_mean(np.maximum(top_u["log_U_t"], EPS))
                    row["lambda_top_u_gross_per_logu"] = safe_div(finite_mean(top_u["gross"]), den)
                    row["top_u_mean_gross"] = finite_mean(top_u["gross"])
                if len(top_x):
                    den = finite_mean(np.maximum(top_x["X_t"], EPS))
                    row["lambda_top_x_gross_per_x"] = safe_div(finite_mean(top_x["gross"]), den)
                    row["top_x_mean_gross"] = finite_mean(top_x["gross"])
            out.loc[current_mask, "lambda_prior_top_u"] = row["lambda_top_u_gross_per_logu"]
            out.loc[current_mask, "lambda_prior_top_x"] = row["lambda_top_x_gross_per_x"]
            lambda_rows.append(row)
    return out, pd.DataFrame(lambda_rows)


def subset_stats(frame: pd.DataFrame) -> dict[str, Any]:
    exposure = pd.to_numeric(frame.get("weight", 1.0), errors="coerce").fillna(1.0).to_numpy(dtype="float64")
    net = pd.to_numeric(frame["net"], errors="coerce").to_numpy(dtype="float64")
    pnl = exposure * net
    return {
        "entries": int(len(frame)),
        "exposure": float(np.nansum(exposure)),
        "net_mean_bps": safe_div(float(np.nansum(pnl)), float(np.nansum(exposure))),
        "net_median_bps": finite_quantile(frame["net"], 0.50),
        "gt2_rate": float(np.nanmean(net > 2.0)) if len(net) else np.nan,
        "q90_net_bps": finite_quantile(frame["net"], 0.90),
        "cvar05_net_bps": cvar(frame["net"], 0.05),
        "total_weighted_net": float(np.nansum(pnl)),
        "gross_mean_bps": finite_mean(frame["gross"]),
    }


def score_feature(entries: pd.DataFrame, feature: str) -> dict[str, Any]:
    x = pd.to_numeric(entries[feature], errors="coerce").to_numpy(dtype="float64")
    y = pd.to_numeric(entries["net"], errors="coerce").to_numpy(dtype="float64")
    ok = np.isfinite(x) & np.isfinite(y)
    out: dict[str, Any] = {
        "feature": feature,
        "rows": int(ok.sum()),
        "spearman_net": np.nan,
        "top_bottom_net_bps": np.nan,
        "top_mean_net_bps": np.nan,
        "bottom_mean_net_bps": np.nan,
        "top_gt2_rate": np.nan,
        "top_cvar05_net_bps": np.nan,
    }
    if ok.sum() < 50:
        return out
    try:
        out["spearman_net"] = float(spearmanr(x[ok], y[ok]).statistic)
    except Exception:
        out["spearman_net"] = np.nan
    work = entries.loc[ok].copy()
    top_cut = finite_quantile(work[feature], 0.80)
    bottom_cut = finite_quantile(work[feature], 0.20)
    top = work[work[feature].ge(top_cut)]
    bottom = work[work[feature].le(bottom_cut)]
    top_stats = subset_stats(top)
    bottom_stats = subset_stats(bottom)
    out["top_entries"] = top_stats["entries"]
    out["bottom_entries"] = bottom_stats["entries"]
    out["top_mean_net_bps"] = top_stats["net_mean_bps"]
    out["bottom_mean_net_bps"] = bottom_stats["net_mean_bps"]
    out["top_bottom_net_bps"] = top_stats["net_mean_bps"] - bottom_stats["net_mean_bps"]
    out["top_gt2_rate"] = top_stats["gt2_rate"]
    out["top_cvar05_net_bps"] = top_stats["cvar05_net_bps"]
    return out


def build_scorecard(entries: pd.DataFrame) -> pd.DataFrame:
    features = [
        "X_t",
        "Theta_t",
        "log_U_t",
        "A_absorption_t",
        "E_exhaustion_t",
        "C_confirm_t",
        "D_divergence_t",
        "release_score_t",
        "lambda_prior_top_u",
    ]
    rows = [score_feature(entries, feature) for feature in features if feature in entries.columns]
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("top_bottom_net_bps", ascending=False).reset_index(drop=True)
    return out


def build_joint_bins(entries: pd.DataFrame) -> pd.DataFrame:
    work = entries.copy()
    rows: list[dict[str, Any]] = []
    q = {
        "x20": finite_quantile(work["X_t"], 0.20),
        "x50": finite_quantile(work["X_t"], 0.50),
        "x70": finite_quantile(work["X_t"], 0.70),
        "x80": finite_quantile(work["X_t"], 0.80),
        "u20": finite_quantile(work["log_U_t"], 0.20),
        "u50": finite_quantile(work["log_U_t"], 0.50),
        "u70": finite_quantile(work["log_U_t"], 0.70),
        "u80": finite_quantile(work["log_U_t"], 0.80),
        "theta20": finite_quantile(work["Theta_t"], 0.20),
        "theta50": finite_quantile(work["Theta_t"], 0.50),
        "theta70": finite_quantile(work["Theta_t"], 0.70),
        "theta80": finite_quantile(work["Theta_t"], 0.80),
        "a20": finite_quantile(work["A_absorption_t"], 0.20),
        "a50": finite_quantile(work["A_absorption_t"], 0.50),
        "a70": finite_quantile(work["A_absorption_t"], 0.70),
        "a80": finite_quantile(work["A_absorption_t"], 0.80),
        "e20": finite_quantile(work["E_exhaustion_t"], 0.20),
        "e50": finite_quantile(work["E_exhaustion_t"], 0.50),
        "e70": finite_quantile(work["E_exhaustion_t"], 0.70),
        "e80": finite_quantile(work["E_exhaustion_t"], 0.80),
        "c20": finite_quantile(work["C_confirm_t"], 0.20),
        "c50": finite_quantile(work["C_confirm_t"], 0.50),
        "c70": finite_quantile(work["C_confirm_t"], 0.70),
        "c80": finite_quantile(work["C_confirm_t"], 0.80),
    }
    cell11 = work["gate_r5_and_frames_q90"].astype(bool)
    specs = [
        ("high_U", work["log_U_t"].ge(q["u80"])),
        ("high_X", work["X_t"].ge(q["x80"])),
        ("low_Theta", work["Theta_t"].le(q["theta20"])),
        ("high_Theta", work["Theta_t"].ge(q["theta80"])),
        ("low_E", work["E_exhaustion_t"].le(q["e20"])),
        ("high_E", work["E_exhaustion_t"].ge(q["e80"])),
        ("high_C_confirm", work["C_confirm_t"].ge(q["c80"])),
        ("low_C_confirm", work["C_confirm_t"].le(q["c20"])),
        ("high_U_low_E", work["log_U_t"].ge(q["u70"]) & work["E_exhaustion_t"].le(q["e50"])),
        ("high_X_high_Theta", work["X_t"].ge(q["x70"]) & work["Theta_t"].ge(q["theta70"])),
        ("high_X_low_Theta", work["X_t"].ge(q["x70"]) & work["Theta_t"].le(q["theta50"])),
        ("high_U_confirmed", work["log_U_t"].ge(q["u70"]) & work["C_confirm_t"].ge(q["c70"])),
        ("high_U_low_confirm", work["log_U_t"].ge(q["u70"]) & work["C_confirm_t"].le(q["c50"])),
        ("low_U_or_exhausted", work["log_U_t"].le(finite_quantile(work["log_U_t"], 0.30)) | work["E_exhaustion_t"].ge(q["e80"])),
        ("cell_11_all", cell11),
        ("cell_11_low_U", cell11 & work["log_U_t"].le(q["u50"])),
        ("cell_11_high_U", cell11 & work["log_U_t"].ge(q["u70"])),
        ("cell_11_high_Theta", cell11 & work["Theta_t"].ge(q["theta70"])),
        ("cell_11_low_Theta", cell11 & work["Theta_t"].le(q["theta50"])),
        ("cell_11_high_A", cell11 & work["A_absorption_t"].ge(q["a70"])),
        ("cell_11_low_A", cell11 & work["A_absorption_t"].le(q["a50"])),
        ("cell_11_low_C", cell11 & work["C_confirm_t"].le(q["c50"])),
        ("cell_11_high_C", cell11 & work["C_confirm_t"].ge(q["c70"])),
    ]
    for name, mask in specs:
        subset = work[mask.fillna(False)].copy()
        row = {"bucket": name, **subset_stats(subset)}
        row["short_entries"] = int((subset["direction"] < 0).sum()) if len(subset) else 0
        row["long_entries"] = int((subset["direction"] > 0).sum()) if len(subset) else 0
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("net_mean_bps", ascending=False).reset_index(drop=True)


def build_direction_table(entries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for direction, group in entries.groupby("direction", sort=True):
        row = {"direction": int(direction), **subset_stats(group)}
        for col in ["X_t", "Theta_t", "log_U_t", "A_absorption_t", "E_exhaustion_t", "C_confirm_t", "release_score_t"]:
            row[f"median_{col}"] = finite_quantile(group[col], 0.50)
            row[f"top20_{col}"] = finite_quantile(group[col], 0.80)
        rows.append(row)
    return pd.DataFrame(rows)


def write_report(
    paths: Paths,
    entries: pd.DataFrame,
    scorecard: pd.DataFrame,
    joint: pd.DataFrame,
    direction: pd.DataFrame,
    lambdas: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT TFI Core Quantity Estimation",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This report estimates pressure/absorption quantities for the TFI branch. The quantities are computed from current and prior order-book/order-flow state; future gross/net labels are used only after the fact to inspect payoff shape.",
            "",
            "## Model",
            "",
            "The working first-principles model is:",
            "",
            "$$",
            "r_{t,t+h}=d_t\\lambda_t\\left(X_t-\\Theta_t\\right)^++\\epsilon_t,",
            "$$",
            "",
            "where $d_t\\in\\{-1,+1\\}$ is the entry direction, $X_t$ is accumulated same-direction flow pressure, $\\Theta_t$ is the same-side book's absorption threshold, and $\\lambda_t$ is pressure-to-price conversion.",
            "",
            "Estimated quantities:",
            "",
            "- $X_t=z(d_t\\cdot EMA_{25}(TFI_t))$.",
            "- $\\Theta_t=0.8z(oppDepth_5)+0.5z(oppReplenish)+0.3z(spread)-0.7z(oppDepletion)$.",
            "- $\\log U_t=X_t-\\Theta_t$, so $U_t=\\exp(\\log U_t)$ is a robust-scale release ratio.",
            "- $A_t=X_t+0.7z(oppReplenish)+0.4z(oppDepth_5)-0.7(P_t)^+-0.3z(oppDepletion)$.",
            "- $E_t=(P_t)^++0.5z(spread)+0.3z(liquidityShock)-0.6(X_t)^+$.",
            "- $C_t=0.6z(d_tMLOFI_{1})+0.4z(d_tOFI_1)$.",
            "",
            "Here $P_t=z(d_t r_{t-25,t})$ is already-released same-direction price movement. Normalization uses expanding prior panel rows by date and direction; if insufficient, it falls back to the same-direction panel distribution.",
            "",
            "## Scope",
            "",
            f"- Entry rows: `{len(entries)}`.",
            f"- Date range: `{summary.get('date_min')}` to `{summary.get('date_max')}`.",
            f"- Merged event-panel coverage: `{fmt(summary.get('event_merge_coverage'), 4)}`.",
            f"- Short entries: `{summary.get('short_entries')}`; long entries: `{summary.get('long_entries')}`.",
            "",
            "## Main Read",
            "",
            f"1. The strongest positive diagnostic is `{summary.get('best_feature')}` with top-bottom net `{fmt(summary.get('best_top_bottom_net_bps'), 4)}` bps and Spearman `{fmt(summary.get('best_spearman_net'), 4)}`.",
            f"2. The best joint bucket is `{summary.get('best_joint_bucket')}`: entries `{summary.get('best_joint_entries')}`, mean net `{fmt(summary.get('best_joint_mean_net_bps'), 4)}` bps, q90 `{fmt(summary.get('best_joint_q90_net_bps'), 4)}` bps, CVaR5 `{fmt(summary.get('best_joint_cvar05_net_bps'), 4)}` bps.",
            f"3. Directional conversion remains asymmetric: short mean net `{fmt(summary.get('short_mean_net_bps'), 4)}` bps versus long mean net `{fmt(summary.get('long_mean_net_bps'), 4)}` bps in this entry universe.",
            "4. These are state estimates, not a final strategy. The useful next step is to use $X_t,\\Theta_t,U_t,A_t,E_t,C_t$ as decomposition controls around the existing TFI cells, while not assuming that high $U_t$ or high $C_t$ alone is sufficient.",
            "",
            "## Single-Quantity Scorecard",
        ]
    )
    lines.extend(
        markdown_table(
            scorecard,
            [
                "feature",
                "rows",
                "spearman_net",
                "top_entries",
                "top_mean_net_bps",
                "bottom_mean_net_bps",
                "top_bottom_net_bps",
                "top_gt2_rate",
                "top_cvar05_net_bps",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Joint Buckets"])
    lines.extend(
        markdown_table(
            joint,
            [
                "bucket",
                "entries",
                "short_entries",
                "long_entries",
                "exposure",
                "net_mean_bps",
                "net_median_bps",
                "gt2_rate",
                "q90_net_bps",
                "cvar05_net_bps",
                "total_weighted_net",
            ],
            max_rows=20,
        )
    )
    lines.extend(["## Direction Split"])
    lines.extend(
        markdown_table(
            direction,
            [
                "direction",
                "entries",
                "exposure",
                "net_mean_bps",
                "net_median_bps",
                "gt2_rate",
                "q90_net_bps",
                "cvar05_net_bps",
                "median_X_t",
                "median_Theta_t",
                "median_log_U_t",
                "median_E_exhaustion_t",
            ],
            max_rows=10,
        )
    )
    lines.extend(["## Prior Lambda Estimates"])
    lines.extend(
        markdown_table(
            lambdas.tail(20),
            [
                "date",
                "direction",
                "prior_entries",
                "lambda_top_u_gross_per_logu",
                "lambda_top_x_gross_per_x",
                "top_u_mean_gross",
                "top_x_mean_gross",
            ],
            max_rows=20,
        )
    )
    lines.extend(
        [
            "## Outputs",
            "",
            f"- `{paths.scored_csv}`",
            f"- `{paths.scorecard_csv}`",
            f"- `{paths.joint_csv}`",
            f"- `{paths.direction_csv}`",
            f"- `{paths.lambda_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_core_quantity_estimation.py",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        panel_root=resolve_repo_path(args.panel_root),
        panel_run_tags=tuple(parse_strings(args.panel_run_tags)),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        entries_csv=resolve_repo_path(args.entries_csv),
        symbol=args.symbol,
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    panel = load_panel(paths, args.pressure_span_events, args.fast_pressure_span_events, args.past_event_horizon)
    entries = load_entries(paths)
    merged = build_entry_base(panel, entries)
    directional_panel = train_directional_panel(panel)
    scored = add_expanding_z(merged, directional_panel)
    scored = add_core_scores(scored)
    scored, lambdas = add_prior_lambda(scored)

    scorecard = build_scorecard(scored)
    joint = build_joint_bins(scored)
    direction = build_direction_table(scored)

    best = scorecard.iloc[0].to_dict() if len(scorecard) else {}
    best_joint = joint.iloc[0].to_dict() if len(joint) else {}
    dir_rows = direction.set_index("direction").to_dict(orient="index") if len(direction) else {}
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "entry_rows": int(len(scored)),
        "date_min": str(scored["date"].min()),
        "date_max": str(scored["date"].max()),
        "event_merge_coverage": float(scored["x_raw"].notna().mean()),
        "short_entries": int((scored["direction"] < 0).sum()),
        "long_entries": int((scored["direction"] > 0).sum()),
        "best_feature": best.get("feature"),
        "best_top_bottom_net_bps": best.get("top_bottom_net_bps"),
        "best_spearman_net": best.get("spearman_net"),
        "best_joint_bucket": best_joint.get("bucket"),
        "best_joint_entries": best_joint.get("entries"),
        "best_joint_mean_net_bps": best_joint.get("net_mean_bps"),
        "best_joint_q90_net_bps": best_joint.get("q90_net_bps"),
        "best_joint_cvar05_net_bps": best_joint.get("cvar05_net_bps"),
        "short_mean_net_bps": dir_rows.get(-1, {}).get("net_mean_bps"),
        "long_mean_net_bps": dir_rows.get(1, {}).get("net_mean_bps"),
        "top_scorecard": scorecard.head(12).to_dict(orient="records"),
        "joint": joint.to_dict(orient="records"),
    }

    scored.to_csv(paths.scored_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    joint.to_csv(paths.joint_csv, index=False)
    direction.to_csv(paths.direction_csv, index=False)
    lambdas.to_csv(paths.lambda_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, scored, scorecard, joint, direction, lambdas, summary)

    print(json.dumps({"run_tag": paths.run_tag, "report": str(paths.report_md), "entries": len(scored)}, indent=2))


if __name__ == "__main__":
    main()
