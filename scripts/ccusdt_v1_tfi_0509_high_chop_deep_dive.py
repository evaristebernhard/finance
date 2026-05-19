#!/usr/bin/env python
"""Deep dive for the 2026-05-09 high/chop TFI accident group.

This diagnostic isolates whether the 2026-05-09 high/chop loss was a broad
state failure or a concentrated single-entry / matched-bucket failure. It uses
only already-produced entry panels and the fixed event factor panel for local
path reconstruction.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1"
GUARDRAIL = "research_only_0509_high_chop_accident_diagnostic_no_execution_recommendation"

LATENT_FILE_NAME = "ccusdt_v1_tfi_latent_state_panel_20260518_ccusdt_v1_tfi_latent_state_panel_v1.csv"
FACTOR_FILE_NAME = "ccusdt_v1_tfi_factor_decomp_entries_20260518_ccusdt_v1_tfi_factor_decomp_v1.csv"
US_PER_SECOND = 1_000_000.0
EPS = 1e-12

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
    "mfe_bps",
    "mae_bps",
    "has_mid_transition",
    "has_quote_transition",
    "first_mid_transition_gross_bps",
    "first_quote_transition_gross_bps",
    "mid_transition_count",
    "quote_transition_count",
    "first_mid_transition_hold_sec",
    "first_quote_transition_hold_sec",
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
    "microprice_dev_bps",
    "trade_window_count",
    "trade_flow_imbalance",
    "queue_imbalance_5",
    "queue_imbalance_25",
    "mlofi_raw_l5",
    "mlofi_raw_l25",
    "ofi_l1_raw",
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
]


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    panel_root: Path
    panel_run_tag: str
    symbol: str
    target_date: str
    run_tag: str

    @property
    def latent_csv(self) -> Path:
        return self.date_dir / LATENT_FILE_NAME

    @property
    def factor_csv(self) -> Path:
        return self.date_dir / FACTOR_FILE_NAME

    @property
    def panel_day_dir(self) -> Path:
        return (
            self.panel_root
            / f"run_tag={self.panel_run_tag}"
            / f"symbol={self.symbol}"
            / f"dt={self.target_date}"
        )

    @property
    def focus_entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_0509_high_chop_entries_{self.run_tag}.csv"

    @property
    def controls_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_0509_high_chop_controls_{self.run_tag}.csv"

    @property
    def same_bucket_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_0509_high_chop_same_bucket_{self.run_tag}.csv"

    @property
    def path_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_0509_high_chop_path_summary_{self.run_tag}.csv"

    @property
    def path_samples_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_0509_high_chop_path_samples_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_0509_high_chop_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-0509-high-chop-deep-dive-{self.run_tag}.md"


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
    parser.add_argument("--target-date", default="2026-05-09")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--path-window-sec", type=int, default=60)
    parser.add_argument("--sample-step-sec", type=int, default=5)
    parser.add_argument("--event-padding", type=int, default=10_000)
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


def load_entries(paths: Paths) -> pd.DataFrame:
    latent = pd.read_csv(paths.latent_csv, usecols=lambda col: col in LATENT_COLS)
    factor = pd.read_csv(paths.factor_csv, usecols=lambda col: col in FACTOR_COLS)
    merged = latent.merge(factor, on=["date", "entry_row"], how="left", suffixes=("", "_factor"))
    for col in ["entry_row", "entry_event_index"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").astype("Int64")
    for col in ["net", "gross", "cost", "target_exposure", "target_pnl"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    return merged


def focus_mask(df: pd.DataFrame, target_date: str) -> pd.Series:
    return (
        df["date"].eq(target_date)
        & df["quality_side"].eq("high")
        & df["dominant_latent_state"].eq("chop")
    )


def bucket_masks(df: pd.DataFrame, disaster: pd.Series, target_date: str) -> dict[str, pd.Series]:
    delta_bucket = (
        df["cell"].eq(disaster["cell"])
        & df["direction_label"].eq(disaster["direction_label"])
        & df["frames_q_bin"].eq(disaster["frames_q_bin"])
        & df["delta10_bin"].eq(disaster["delta10_bin"])
    )
    full_strength_bucket = (
        delta_bucket
        & df["energy10_bin"].eq(disaster["energy10_bin"])
        & df["z10_bin"].eq(disaster["z10_bin"])
    )
    focus = focus_mask(df, target_date)
    return {
        "focus_0509_high_chop": focus,
        "focus_without_top1": focus & df["entry_row"].ne(disaster["entry_row"]),
        "disaster_row": df["entry_row"].eq(disaster["entry_row"]),
        "0509_high_non_chop": (
            df["date"].eq(target_date)
            & df["quality_side"].eq("high")
            & ~df["dominant_latent_state"].eq("chop")
        ),
        "0509_reduce_chop": (
            df["date"].eq(target_date)
            & df["quality_side"].eq("reduce")
            & df["dominant_latent_state"].eq("chop")
        ),
        "other_days_high_chop": (
            ~df["date"].eq(target_date)
            & df["quality_side"].eq("high")
            & df["dominant_latent_state"].eq("chop")
        ),
        "all_high_chop": (
            df["quality_side"].eq("high")
            & df["dominant_latent_state"].eq("chop")
        ),
        "same_delta_bucket_all_days": delta_bucket,
        "same_delta_bucket_0509": delta_bucket & df["date"].eq(target_date),
        "same_delta_bucket_ex0509": delta_bucket & ~df["date"].eq(target_date),
        "same_full_strength_bucket_all_days": full_strength_bucket,
        "same_full_strength_bucket_0509": full_strength_bucket & df["date"].eq(target_date),
        "same_full_strength_bucket_ex0509": full_strength_bucket & ~df["date"].eq(target_date),
    }


def group_stats(df: pd.DataFrame, name: str, mask: pd.Series) -> dict[str, Any]:
    group = df.loc[mask].copy()
    row: dict[str, Any] = {"group": name, "entries": int(len(group))}
    if group.empty:
        return row
    pnl = pd.to_numeric(group["target_pnl"], errors="coerce")
    exposure = pd.to_numeric(group["target_exposure"], errors="coerce").abs()
    total_pnl = float(pnl.sum())
    row.update(
        {
            "exposure": float(exposure.sum()),
            "total_pnl": total_pnl,
            "weighted_mean_net": float(total_pnl / exposure.sum()) if exposure.sum() > 0 else float("nan"),
            "net_mean": finite_mean(group["net"]),
            "net_median": finite_quantile(group["net"], 0.50),
            "gt2_rate": float((pd.to_numeric(group["net"], errors="coerce") > 2.0).mean()),
            "q90_net": finite_quantile(group["net"], 0.90),
            "cvar05_net": cvar(group["net"], 0.05),
            "mfe_mean": finite_mean(group.get("mfe_bps", pd.Series(dtype=float))),
            "mae_mean": finite_mean(group.get("mae_bps", pd.Series(dtype=float))),
            "first_mid_transition_mean": finite_mean(
                group.get("first_mid_transition_gross_bps", pd.Series(dtype=float))
            ),
            "chop_score_mean": finite_mean(group["chop_score"]),
            "release_score_mean": finite_mean(group["release_score"]),
            "vacuum_score_mean": finite_mean(group["vacuum_score"]),
            "X_t_mean": finite_mean(group["X_t"]),
            "Theta_t_mean": finite_mean(group["Theta_t"]),
            "log_U_t_mean": finite_mean(group["log_U_t"]),
            "C_confirm_t_mean": finite_mean(group["C_confirm_t"]),
            "D_divergence_t_mean": finite_mean(group["D_divergence_t"]),
            "closed10_delta_mean": finite_mean(group["closed10_delta"]),
            "closed10_energy_mean": finite_mean(group["closed10_energy"]),
            "closed10_score_abs_mean": finite_mean(group["closed10_score_abs"]),
        }
    )
    return row


def same_bucket_daily(df: pd.DataFrame, masks: dict[str, pd.Series]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for bucket_name in ["same_delta_bucket_all_days", "same_full_strength_bucket_all_days"]:
        group = df.loc[masks[bucket_name]].copy()
        if group.empty:
            continue
        daily = (
            group.groupby("date", sort=True)
            .agg(
                entries=("net", "size"),
                exposure=("target_exposure", "sum"),
                total_pnl=("target_pnl", "sum"),
                net_mean=("net", "mean"),
                net_median=("net", "median"),
                mfe_mean=("mfe_bps", "mean"),
                mae_mean=("mae_bps", "mean"),
                chop_score_mean=("chop_score", "mean"),
                release_score_mean=("release_score", "mean"),
                vacuum_score_mean=("vacuum_score", "mean"),
                X_t_mean=("X_t", "mean"),
                Theta_t_mean=("Theta_t", "mean"),
                log_U_t_mean=("log_U_t", "mean"),
                C_confirm_t_mean=("C_confirm_t", "mean"),
                D_divergence_t_mean=("D_divergence_t", "mean"),
            )
            .reset_index()
        )
        daily.insert(0, "bucket", bucket_name.replace("_all_days", ""))
        rows.append(daily)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def load_event_window(paths: Paths, min_event_index: int, max_event_index: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for csv_path in sorted(paths.panel_day_dir.glob("*.csv")):
        part = pd.read_csv(csv_path, usecols=lambda col: col in EVENT_COLS)
        part["event_index"] = pd.to_numeric(part["event_index"], errors="coerce")
        part = part[part["event_index"].between(min_event_index, max_event_index)]
        if len(part):
            frames.append(part)
    if not frames:
        return pd.DataFrame(columns=EVENT_COLS)
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["event_index", "local_timestamp", "mid_price"]).copy()
    out["event_index"] = out["event_index"].astype("int64")
    out = out.sort_values("event_index").drop_duplicates("event_index", keep="last").reset_index(drop=True)
    return out


def build_path_tables(
    entries: pd.DataFrame,
    paths: Paths,
    path_window_sec: int,
    sample_step_sec: int,
    event_padding: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if entries.empty:
        return pd.DataFrame(), pd.DataFrame()
    min_event = int(pd.to_numeric(entries["entry_event_index"], errors="coerce").min()) - event_padding
    max_event = int(pd.to_numeric(entries["entry_event_index"], errors="coerce").max()) + event_padding
    panel = load_event_window(paths, min_event, max_event)
    if panel.empty:
        return pd.DataFrame(), pd.DataFrame()

    summary_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    sample_targets = np.arange(-path_window_sec, path_window_sec + sample_step_sec, sample_step_sec)

    for _, entry in entries.sort_values("entry_event_index").iterrows():
        event_index = int(entry["entry_event_index"])
        nearest_pos = int((panel["event_index"] - event_index).abs().argmin())
        entry_event = panel.iloc[nearest_pos]
        entry_mid = float(entry_event["mid_price"])
        entry_ts = float(entry_event["local_timestamp"])
        side = 1 if entry["direction_label"] == "long" else -1
        window = panel[
            panel["local_timestamp"].between(
                entry_ts - path_window_sec * US_PER_SECOND,
                entry_ts + path_window_sec * US_PER_SECOND,
            )
        ].copy()
        if window.empty:
            continue
        window["hold_sec"] = (pd.to_numeric(window["local_timestamp"], errors="coerce") - entry_ts) / US_PER_SECOND
        window["signed_mid_bps"] = side * 10_000.0 * np.log(
            np.maximum(pd.to_numeric(window["mid_price"], errors="coerce"), EPS) / max(entry_mid, EPS)
        )
        pre = window[window["hold_sec"] < 0]
        post = window[window["hold_sec"] > 0]
        if len(post):
            mfe_idx = post["signed_mid_bps"].idxmax()
            mae_idx = post["signed_mid_bps"].idxmin()
        else:
            mfe_idx = mae_idx = None
        summary_rows.append(
            {
                "entry_row": int(entry["entry_row"]),
                "entry_event_index": event_index,
                "path_scope": entry.get("path_scope", ""),
                "cell": entry["cell"],
                "direction_label": entry["direction_label"],
                "quality_side": entry["quality_side"],
                "dominant_latent_state": entry["dominant_latent_state"],
                "net": float(entry["net"]),
                "target_exposure": float(entry["target_exposure"]),
                "target_pnl": float(entry["target_pnl"]),
                "entry_mid": entry_mid,
                "entry_spread_bps_path": float(entry_event.get("spread_bps", np.nan)),
                "window_rows": int(len(window)),
                "post_rows": int(len(post)),
                "pre_60s_signed_bps": float(pre["signed_mid_bps"].iloc[0]) if len(pre) else float("nan"),
                "pre_60s_range_bps": (
                    float(pre["signed_mid_bps"].max() - pre["signed_mid_bps"].min()) if len(pre) else float("nan")
                ),
                "post_60s_final_bps": float(post["signed_mid_bps"].iloc[-1]) if len(post) else float("nan"),
                "post_60s_mfe_bps": float(post["signed_mid_bps"].max()) if len(post) else float("nan"),
                "post_60s_mae_bps": float(post["signed_mid_bps"].min()) if len(post) else float("nan"),
                "time_to_mfe_sec": float(post.loc[mfe_idx, "hold_sec"]) if mfe_idx is not None else float("nan"),
                "time_to_mae_sec": float(post.loc[mae_idx, "hold_sec"]) if mae_idx is not None else float("nan"),
                "post_trade_flow_mean": finite_mean(post.get("trade_flow_imbalance", pd.Series(dtype=float))),
                "post_qi5_mean": finite_mean(post.get("queue_imbalance_5", pd.Series(dtype=float))),
                "post_qi25_mean": finite_mean(post.get("queue_imbalance_25", pd.Series(dtype=float))),
                "post_mlofi5_mean": finite_mean(post.get("mlofi_raw_l5", pd.Series(dtype=float))),
                "post_mlofi25_mean": finite_mean(post.get("mlofi_raw_l25", pd.Series(dtype=float))),
            }
        )
        for target in sample_targets:
            idx = (window["hold_sec"] - target).abs().idxmin()
            point = window.loc[idx]
            sample_rows.append(
                {
                    "entry_row": int(entry["entry_row"]),
                    "entry_event_index": event_index,
                    "path_scope": entry.get("path_scope", ""),
                    "target_hold_sec": int(target),
                    "hold_sec": float(point["hold_sec"]),
                    "event_index": int(point["event_index"]),
                    "signed_mid_bps": float(point["signed_mid_bps"]),
                    "mid_price": float(point["mid_price"]),
                    "spread_bps": float(point.get("spread_bps", np.nan)),
                    "trade_flow_imbalance": float(point.get("trade_flow_imbalance", np.nan)),
                    "queue_imbalance_5": float(point.get("queue_imbalance_5", np.nan)),
                    "queue_imbalance_25": float(point.get("queue_imbalance_25", np.nan)),
                    "mlofi_raw_l5": float(point.get("mlofi_raw_l5", np.nan)),
                    "mlofi_raw_l25": float(point.get("mlofi_raw_l25", np.nan)),
                }
            )
    return pd.DataFrame(summary_rows), pd.DataFrame(sample_rows)


def build_report(
    paths: Paths,
    focus_entries: pd.DataFrame,
    controls: pd.DataFrame,
    same_bucket: pd.DataFrame,
    path_summary: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    disaster = summary["disaster_row"]
    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT TFI 2026-05-09 High/Chop Deep Dive",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This report deep-dives the `2026-05-09` high/chop accident group in the CCUSDT V1 TFI branch. It is a diagnostic, not an execution recommendation.",
            "",
            "## Definitions",
            "",
            "The focus set is:",
            "",
            "$$",
            "\\mathcal A=\\{i:d_i=\\mathrm{2026-05-09},\\ q_i=\\mathrm{high},\\ z_i=\\mathrm{chop}\\}.",
            "$$",
            "",
            "Contribution is measured with the already cost-adjusted entry net and target exposure:",
            "",
            "$$",
            "G(S)=\\sum_{i\\in S}\\gamma_i r_i,\\qquad \\kappa_1=\\frac{\\max_{i\\in S}|\\gamma_i r_i|}{|G(S)|}.",
            "$$",
            "",
            "The signed path around an entry is:",
            "",
            "$$",
            "R_i(\\tau)=s_i\\,10^4\\log\\frac{M_{t_i+\\tau}}{M_{t_i}},\\qquad s_i=+1\\ (\\mathrm{long}),\\ s_i=-1\\ (\\mathrm{short}).",
            "$$",
            "",
            "## Main Read",
            "",
            f"1. The high/chop focus set has `{summary['focus_entries']}` entries and total target PnL `{fmt(summary['focus_total_pnl'])}` bps-equivalent exposure units.",
            f"2. The largest absolute contributor is `entry_row={disaster['entry_row']}` with target PnL `{fmt(disaster['target_pnl'])}` and target exposure `{fmt(disaster['target_exposure'])}`.",
            f"3. The top-1 concentration is `{fmt(summary['top1_abs_share'])}`. Since this is above `1`, the single row explains more than all of the focus loss; the remaining focus entries sum to `{fmt(summary['focus_without_top1_pnl'])}`.",
            f"4. This is not a broad high/chop failure: `other_days_high_chop` is `{fmt(summary['other_days_high_chop_pnl'])}`, while `2026-05-09 high_non_chop` is `{fmt(summary['high_non_chop_0509_pnl'])}`.",
            f"5. The more precise accident surface is the matched `11_r5_frames / short / q70_85 / delta10=s80_100` bucket. On `2026-05-09` it has `{summary['same_delta_0509_entries']}` entries, total PnL `{fmt(summary['same_delta_0509_pnl'])}`, and `gt2_rate` `{fmt(summary['same_delta_0509_gt2'])}`; excluding `2026-05-09`, the same bucket is `{fmt(summary['same_delta_ex0509_pnl'])}`.",
            "",
            "So the clean read is: `2026-05-09 high/chop` is one oversized `11` loss, but that row belongs to a same-day `11/short/q70_85/high-delta` bucket inversion. The bad day is not random noise only, and also not enough evidence to ban the bucket globally.",
            "",
            "## Focus Entries",
        ]
    )
    lines.extend(
        markdown_table(
            focus_entries.sort_values("target_pnl"),
            [
                "entry_row",
                "entry_event_index",
                "cell",
                "direction_label",
                "frames_q_bin",
                "delta10_bin",
                "energy10_bin",
                "z10_bin",
                "net",
                "gross",
                "cost",
                "target_exposure",
                "target_pnl",
                "mfe_bps",
                "mae_bps",
                "dominant_latent_state",
                "chop_score",
                "release_score",
            ],
            max_rows=30,
        )
    )
    lines.extend(["## Matched Controls"])
    lines.extend(
        markdown_table(
            controls,
            [
                "group",
                "entries",
                "exposure",
                "total_pnl",
                "weighted_mean_net",
                "net_mean",
                "net_median",
                "gt2_rate",
                "mfe_mean",
                "mae_mean",
                "chop_score_mean",
                "release_score_mean",
                "X_t_mean",
                "log_U_t_mean",
                "C_confirm_t_mean",
                "D_divergence_t_mean",
            ],
            max_rows=30,
        )
    )
    lines.extend(["## Same-Bucket Daily"])
    lines.extend(
        markdown_table(
            same_bucket,
            [
                "bucket",
                "date",
                "entries",
                "exposure",
                "total_pnl",
                "net_mean",
                "net_median",
                "mfe_mean",
                "mae_mean",
                "chop_score_mean",
                "release_score_mean",
                "X_t_mean",
                "log_U_t_mean",
                "C_confirm_t_mean",
                "D_divergence_t_mean",
            ],
            max_rows=40,
        )
    )
    if len(path_summary):
        lines.extend(
            [
                "## Path Shape",
                "",
                "The disaster row was not instantly hopeless. It had a fast favorable excursion, then a full reversal within the same 60-second label horizon:",
                "",
            ]
        )
        lines.extend(
            markdown_table(
                path_summary.sort_values("target_pnl"),
                [
                    "entry_row",
                    "path_scope",
                    "cell",
                    "direction_label",
                    "net",
                    "target_exposure",
                    "target_pnl",
                    "pre_60s_signed_bps",
                    "post_60s_final_bps",
                    "post_60s_mfe_bps",
                    "post_60s_mae_bps",
                    "time_to_mfe_sec",
                    "time_to_mae_sec",
                    "post_qi5_mean",
                    "post_mlofi5_mean",
                ],
                max_rows=40,
            )
        )
    lines.extend(
        [
            "## Mechanism Hypotheses",
            "",
            "1. **Concentration hypothesis**: the focus loss is primarily a sizing problem. `gamma_11` gives a single row exposure `8`, so one path reversal dominates the apparent regime failure.",
            "2. **Same-bucket inversion hypothesis**: the local bad surface is not all high/chop. It is `11_r5_frames / short / q70_85 / delta10=s80_100` on `2026-05-09`, where every same-day matched row is negative.",
            "3. **Exit-shape hypothesis**: the disaster row reaches positive MFE before the large MAE. That points more toward take-profit/trailing-risk research than an entry-only veto.",
            "4. **Weak evidence warning**: the matched bucket is tiny. Excluding `2026-05-09`, the same bucket is strongly positive, mostly because of `2026-05-14`. A global ban would be post-hoc and likely destroys real right-tail exposure.",
            "",
            "## Outputs",
            "",
            f"- `{paths.focus_entries_csv}`",
            f"- `{paths.controls_csv}`",
            f"- `{paths.same_bucket_csv}`",
            f"- `{paths.path_summary_csv}`",
            f"- `{paths.path_samples_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_0509_high_chop_deep_dive.py",
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
        target_date=args.target_date,
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    entries = load_entries(paths)
    focus = focus_mask(entries, paths.target_date)
    focus_entries = entries.loc[focus].copy()
    if focus_entries.empty:
        raise RuntimeError(f"No focus entries found for {paths.target_date} high/chop")

    disaster = (
        focus_entries.assign(abs_target_pnl=lambda frame: frame["target_pnl"].abs())
        .sort_values("abs_target_pnl", ascending=False)
        .iloc[0]
    )
    masks = bucket_masks(entries, disaster, paths.target_date)
    controls = pd.DataFrame([group_stats(entries, name, mask) for name, mask in masks.items()])
    same_daily = same_bucket_daily(entries, masks)

    same_delta_0509 = entries.loc[masks["same_delta_bucket_0509"]].copy()
    path_entries = pd.concat([focus_entries, same_delta_0509], ignore_index=True)
    path_entries = path_entries.drop_duplicates("entry_row").copy()
    path_entries["path_scope"] = np.select(
        [
            path_entries["entry_row"].isin(focus_entries["entry_row"]) & path_entries["entry_row"].isin(same_delta_0509["entry_row"]),
            path_entries["entry_row"].isin(focus_entries["entry_row"]),
            path_entries["entry_row"].isin(same_delta_0509["entry_row"]),
        ],
        ["focus_and_same_delta_bucket_0509", "focus_0509_high_chop", "same_delta_bucket_0509"],
        default="other",
    )
    path_summary, path_samples = build_path_tables(
        path_entries,
        paths,
        path_window_sec=int(args.path_window_sec),
        sample_step_sec=int(args.sample_step_sec),
        event_padding=int(args.event_padding),
    )

    focus_total_pnl = float(focus_entries["target_pnl"].sum())
    disaster_pnl = float(disaster["target_pnl"])
    focus_without_top1_pnl = float(focus_entries.loc[focus_entries["entry_row"].ne(disaster["entry_row"]), "target_pnl"].sum())
    control_lookup = controls.set_index("group").to_dict(orient="index")
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "target_date": paths.target_date,
        "focus_entries": int(len(focus_entries)),
        "focus_total_pnl": focus_total_pnl,
        "focus_exposure": float(focus_entries["target_exposure"].sum()),
        "focus_without_top1_pnl": focus_without_top1_pnl,
        "top1_abs_share": float(abs(disaster_pnl) / max(abs(focus_total_pnl), EPS)),
        "disaster_row": {
            "entry_row": int(disaster["entry_row"]),
            "entry_event_index": int(disaster["entry_event_index"]),
            "cell": str(disaster["cell"]),
            "direction_label": str(disaster["direction_label"]),
            "frames_q_bin": str(disaster["frames_q_bin"]),
            "delta10_bin": str(disaster["delta10_bin"]),
            "energy10_bin": str(disaster["energy10_bin"]),
            "z10_bin": str(disaster["z10_bin"]),
            "net": float(disaster["net"]),
            "gross": float(disaster["gross"]),
            "cost": float(disaster["cost"]),
            "target_exposure": float(disaster["target_exposure"]),
            "target_pnl": disaster_pnl,
            "mfe_bps": float(disaster.get("mfe_bps", np.nan)),
            "mae_bps": float(disaster.get("mae_bps", np.nan)),
            "chop_score": float(disaster["chop_score"]),
            "release_score": float(disaster["release_score"]),
            "X_t": float(disaster["X_t"]),
            "Theta_t": float(disaster["Theta_t"]),
            "log_U_t": float(disaster["log_U_t"]),
            "C_confirm_t": float(disaster["C_confirm_t"]),
            "D_divergence_t": float(disaster["D_divergence_t"]),
        },
        "high_non_chop_0509_pnl": control_lookup.get("0509_high_non_chop", {}).get("total_pnl"),
        "other_days_high_chop_pnl": control_lookup.get("other_days_high_chop", {}).get("total_pnl"),
        "same_delta_0509_entries": control_lookup.get("same_delta_bucket_0509", {}).get("entries"),
        "same_delta_0509_pnl": control_lookup.get("same_delta_bucket_0509", {}).get("total_pnl"),
        "same_delta_0509_gt2": control_lookup.get("same_delta_bucket_0509", {}).get("gt2_rate"),
        "same_delta_ex0509_pnl": control_lookup.get("same_delta_bucket_ex0509", {}).get("total_pnl"),
        "path_entries": int(len(path_summary)),
        "top_controls": controls.to_dict(orient="records"),
    }

    focus_entries.to_csv(paths.focus_entries_csv, index=False)
    controls.to_csv(paths.controls_csv, index=False)
    same_daily.to_csv(paths.same_bucket_csv, index=False)
    path_summary.to_csv(paths.path_summary_csv, index=False)
    path_samples.to_csv(paths.path_samples_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    build_report(paths, focus_entries, controls, same_daily, path_summary, summary)

    print(
        json.dumps(
            {
                "run_tag": paths.run_tag,
                "report": str(paths.report_md),
                "focus_entries": int(len(focus_entries)),
                "focus_total_pnl": focus_total_pnl,
                "top1_abs_share": summary["top1_abs_share"],
                "same_delta_0509_pnl": summary["same_delta_0509_pnl"],
                "same_delta_ex0509_pnl": summary["same_delta_ex0509_pnl"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
