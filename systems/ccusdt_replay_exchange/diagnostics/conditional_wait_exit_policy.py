#!/usr/bin/env python
"""Prior-date conditional wait exit prototype for ExitControllerV1.

This script consumes the wait-only opportunity panel and tests a minimal
runtime-safe controller:

    cross_now, unless a prior-date gate says wait tau then cross.

Post-exit path and flow columns remain diagnostic labels. They are never used
to form runtime gates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_PANEL = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "conditional_wait_exit_q70_idle01_g1_20260505_18_20260522/"
    "conditional_wait_exit_panel.parquet"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "conditional_wait_exit_policy_q70_idle01_g1_20260516_18_20260522"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-exit-controller-v1-conditional-wait-20260522.md")

RUNTIME_FEATURES = {
    "cell",
    "exit_spread_bps",
    "path_h_bps",
    "path_d_bps",
    "signed_top_depth_imbalance",
    "same_flow_imbalance_5s",
    "same_minus_opposite_qty_5s",
    "recent_mid_alpha_5s_bps",
    "decision_frames_since_mid_change",
}

DIAGNOSTIC_LABEL_COLUMNS = {
    "wait_value_bps",
    "wait_benefit_bps",
    "delay_loss_bps",
    "post_wait_peak_bps",
    "post_wait_trough_bps",
    "post_wait_reclaim_bps",
    "post_wait_peak_giveback_bps",
    "post_wait_left_tail_bps",
    "post_wait_max_delay_loss_bps",
    "post_same_flow_imbalance",
    "post_same_minus_opposite_qty",
}


@dataclass(frozen=True)
class Condition:
    feature: str
    quantile: float
    op: str = "gte"


@dataclass(frozen=True)
class GateSpec:
    name: str
    description: str
    conditions: tuple[Condition, ...]
    cell: str | None = None


GATES = [
    GateSpec("all", "no runtime feature gate", ()),
    GateSpec("cell_00", "00_none only", (), cell="00_none"),
    GateSpec("cell_10", "10_r5_only only", (), cell="10_r5_only"),
    GateSpec("cell_01", "01_frames_only only", (), cell="01_frames_only"),
    GateSpec("cell_11", "11_r5_frames only", (), cell="11_r5_frames"),
    GateSpec("spread_q70", "exit spread >= prior q70", (Condition("exit_spread_bps", 0.70),)),
    GateSpec("spread_q80", "exit spread >= prior q80", (Condition("exit_spread_bps", 0.80),)),
    GateSpec("spread_q90", "exit spread >= prior q90", (Condition("exit_spread_bps", 0.90),)),
    GateSpec("recent_alpha_q70", "recent same-direction mid alpha >= prior q70", (Condition("recent_mid_alpha_5s_bps", 0.70),)),
    GateSpec("recent_alpha_q80", "recent same-direction mid alpha >= prior q80", (Condition("recent_mid_alpha_5s_bps", 0.80),)),
    GateSpec("same_flow_q70", "pre-exit same-side flow imbalance >= prior q70", (Condition("same_flow_imbalance_5s", 0.70),)),
    GateSpec("same_flow_q80", "pre-exit same-side flow imbalance >= prior q80", (Condition("same_flow_imbalance_5s", 0.80),)),
    GateSpec("depth_support_q70", "signed top depth imbalance >= prior q70", (Condition("signed_top_depth_imbalance", 0.70),)),
    GateSpec("frames_q70", "frames since mid change >= prior q70", (Condition("decision_frames_since_mid_change", 0.70),)),
    GateSpec("frames_q80", "frames since mid change >= prior q80", (Condition("decision_frames_since_mid_change", 0.80),)),
    GateSpec("path_d_low_q30", "pre-exit giveback D <= prior q30", (Condition("path_d_bps", 0.30, "lte"),)),
    GateSpec("path_d_low_q50", "pre-exit giveback D <= prior median", (Condition("path_d_bps", 0.50, "lte"),)),
    GateSpec(
        "spread_q80_recent_alpha_q70",
        "exit spread >= q80 and recent alpha >= q70",
        (Condition("exit_spread_bps", 0.80), Condition("recent_mid_alpha_5s_bps", 0.70)),
    ),
    GateSpec(
        "spread_q80_same_flow_q70",
        "exit spread >= q80 and same-side flow >= q70",
        (Condition("exit_spread_bps", 0.80), Condition("same_flow_imbalance_5s", 0.70)),
    ),
    GateSpec(
        "recent_alpha_q70_frames_q70",
        "recent alpha >= q70 and frames >= q70",
        (Condition("recent_mid_alpha_5s_bps", 0.70), Condition("decision_frames_since_mid_change", 0.70)),
    ),
    GateSpec(
        "path_d_low_q30_spread_q70",
        "low pre-exit giveback and spread >= q70",
        (Condition("path_d_bps", 0.30, "lte"), Condition("exit_spread_bps", 0.70)),
    ),
]
GATE_BY_NAME = {gate.name: gate for gate in GATES}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--eval-from-date", default="2026-05-16")
    parser.add_argument("--eval-to-date", default="2026-05-18")
    parser.add_argument("--margin-bps", type=float, default=0.05)
    parser.add_argument("--min-train-n", type=int, default=80)
    parser.add_argument("--min-train-exposure", type=float, default=40.0)
    parser.add_argument("--min-prior-days", type=int, default=8)
    parser.add_argument("--min-positive-day-frac", type=float, default=0.67)
    parser.add_argument("--min-cvar10-bps", type=float, default=-5.0)
    parser.add_argument("--min-worst-bps", type=float, default=-60.0)
    parser.add_argument("--min-day-sum-bps", type=float, default=-75.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def optional_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    return "" if value is None else f"{value:.{digits}f}"


def weighted_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty:
        return 0.0
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return float((weights * values).sum())


def weighted_mean(df: pd.DataFrame, column: str) -> float:
    if df.empty:
        return 0.0
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce")
    ok = values.notna()
    if not ok.any():
        return 0.0
    denom = float(weights[ok].sum())
    if denom <= 0.0:
        return float(values[ok].mean())
    return float((weights[ok] * values[ok]).sum() / denom)


def day_values(df: pd.DataFrame, column: str = "weighted_wait_value_bps") -> list[float]:
    if df.empty:
        return []
    return [float(group[column].sum()) for _, group in df.groupby("date", sort=True)]


def day_count(df: pd.DataFrame) -> int:
    return int(df["date"].nunique()) if not df.empty else 0


def positive_day_frac(df: pd.DataFrame) -> float:
    values = day_values(df)
    return float(sum(1 for value in values if value > 0.0) / len(values)) if values else 0.0


def min_day_sum(df: pd.DataFrame) -> float:
    values = day_values(df)
    return min(values) if values else 0.0


def cvar_left(series: pd.Series, frac: float = 0.10) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().sort_values()
    if values.empty:
        return 0.0
    count = max(1, int(math.ceil(len(values) * frac)))
    return float(values.iloc[:count].mean())


def compute_thresholds(train: pd.DataFrame, gate: GateSpec) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for condition in gate.conditions:
        values = pd.to_numeric(train[condition.feature], errors="coerce").dropna()
        thresholds[condition.feature] = float(values.quantile(condition.quantile)) if not values.empty else float("nan")
    return thresholds


def apply_gate(df: pd.DataFrame, gate: GateSpec, thresholds: dict[str, float]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    if gate.cell is not None:
        mask &= df["cell"].astype(str).eq(gate.cell)
    for condition in gate.conditions:
        threshold = thresholds.get(condition.feature, float("nan"))
        if not math.isfinite(threshold):
            mask &= False
            continue
        values = pd.to_numeric(df[condition.feature], errors="coerce")
        if condition.op == "lte":
            mask &= values <= threshold
        else:
            mask &= values >= threshold
    return mask.fillna(False)


def train_stats(group: pd.DataFrame) -> dict[str, Any]:
    return {
        "train_n": int(len(group)),
        "train_position_count": int(group["shadow_position_id"].nunique()) if not group.empty else 0,
        "train_exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "train_prior_days": day_count(group),
        "train_wait_positive_rate": float((pd.to_numeric(group["wait_value_bps"], errors="coerce").fillna(0.0) > 0.0).mean())
        if len(group)
        else 0.0,
        "train_weighted_mean_wait_value_bps": weighted_mean(group, "wait_value_bps"),
        "train_weighted_sum_wait_value_bps": weighted_sum(group, "wait_value_bps"),
        "train_weighted_mean_delay_loss_bps": weighted_mean(group, "delay_loss_bps"),
        "train_weighted_sum_delay_loss_bps": weighted_sum(group, "delay_loss_bps"),
        "train_cvar10_wait_value_bps": cvar_left(group["wait_value_bps"], 0.10) if len(group) else 0.0,
        "train_worst_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").min()) if len(group) else 0.0,
        "train_positive_day_frac": positive_day_frac(group),
        "train_min_day_wait_sum_bps": min_day_sum(group),
    }


def test_stats(day_group: pd.DataFrame, selected_mask: pd.Series) -> dict[str, Any]:
    selected = day_group.loc[selected_mask]
    pure_taker = weighted_sum(day_group, "immediate_taker_net_bps")
    wait_delta = weighted_sum(selected, "wait_value_bps")
    return {
        "test_n": int(len(day_group)),
        "test_exposure": float(pd.to_numeric(day_group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "wait_attempts": int(len(selected)),
        "wait_attempt_exposure": float(pd.to_numeric(selected["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "wait_positive_rate": float((pd.to_numeric(selected["wait_value_bps"], errors="coerce").fillna(0.0) > 0.0).mean())
        if len(selected)
        else 0.0,
        "pure_taker_weighted_net_bps": pure_taker,
        "wait_delta_weighted_bps": wait_delta,
        "wait_controller_weighted_net_bps": pure_taker + wait_delta,
        "wait_weighted_mean_value_bps": weighted_mean(selected, "wait_value_bps") if len(selected) else 0.0,
        "wait_weighted_delay_loss_bps": weighted_sum(selected, "delay_loss_bps") if len(selected) else 0.0,
        "wait_worst_value_bps": float(pd.to_numeric(selected["wait_value_bps"], errors="coerce").min()) if len(selected) else 0.0,
        "wait_cvar10_value_bps": cvar_left(selected["wait_value_bps"], 0.10) if len(selected) else 0.0,
        "wait_post_peak_giveback_weighted_bps": weighted_sum(selected, "post_wait_peak_giveback_bps") if len(selected) else 0.0,
        "wait_post_max_delay_loss_weighted_bps": weighted_sum(selected, "post_wait_max_delay_loss_bps") if len(selected) else 0.0,
    }


def promote(stats: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str]:
    checks = [
        (stats["train_n"] >= args.min_train_n, "min_train_n"),
        (stats["train_exposure"] >= args.min_train_exposure, "min_train_exposure"),
        (stats["train_prior_days"] >= args.min_prior_days, "min_prior_days"),
        (stats["train_positive_day_frac"] >= args.min_positive_day_frac, "min_positive_day_frac"),
        (stats["train_weighted_mean_wait_value_bps"] > args.margin_bps, "margin"),
        (stats["train_cvar10_wait_value_bps"] >= args.min_cvar10_bps, "cvar10"),
        (stats["train_worst_wait_value_bps"] >= args.min_worst_bps, "worst"),
        (stats["train_min_day_wait_sum_bps"] >= args.min_day_sum_bps, "min_day_sum"),
    ]
    failed = [name for ok, name in checks if not ok]
    if failed:
        return False, "failed_" + ",".join(failed)
    return True, "promoted_prior_wait_edge"


def candidate_score(row: pd.Series) -> float:
    return (
        float(row["train_weighted_mean_wait_value_bps"])
        + 0.10 * float(row["train_cvar10_wait_value_bps"])
        + 0.001 * float(row["train_min_day_wait_sum_bps"])
        + 0.05 * float(row["train_positive_day_frac"])
    )


def build_candidate_rows(panel: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    eval_from = str(args.eval_from_date) if args.eval_from_date else None
    eval_to = str(args.eval_to_date) if args.eval_to_date else None
    for profile in sorted(panel["exit_profile_source"].unique()):
        profile_panel = panel[panel["exit_profile_source"] == profile]
        for test_date in sorted(profile_panel["date"].astype(str).unique()):
            if eval_from is not None and test_date < eval_from:
                continue
            if eval_to is not None and test_date > eval_to:
                continue
            for ttl in sorted(profile_panel["ttl_sec"].unique()):
                ttl_panel = profile_panel[pd.to_numeric(profile_panel["ttl_sec"], errors="coerce") == float(ttl)]
                train_ttl = ttl_panel[ttl_panel["date"].astype(str) < test_date]
                test_ttl = ttl_panel[ttl_panel["date"].astype(str) == test_date]
                if test_ttl.empty:
                    continue
                for gate in GATES:
                    thresholds = compute_thresholds(train_ttl, gate)
                    train_mask = apply_gate(train_ttl, gate, thresholds) if not train_ttl.empty else pd.Series(False, index=train_ttl.index)
                    test_mask = apply_gate(test_ttl, gate, thresholds)
                    train_group = train_ttl.loc[train_mask]
                    stats = train_stats(train_group)
                    promoted, reason = promote(stats, args)
                    row = {
                        "exit_profile_source": profile,
                        "test_date": test_date,
                        "ttl_sec": float(ttl),
                        "gate_name": gate.name,
                        "gate_description": gate.description,
                        "gate_thresholds_json": json.dumps(thresholds, sort_keys=True),
                        "promoted": promoted,
                        "promote_reason": reason,
                    }
                    row.update(stats)
                    row.update(test_stats(test_ttl, test_mask))
                    row["candidate_score"] = candidate_score(pd.Series(row)) if promoted else float("-inf")
                    rows.append(row)
    candidate_rows = pd.DataFrame(rows)
    selected_rows: list[dict[str, Any]] = []
    for (profile, test_date), group in candidate_rows.groupby(["exit_profile_source", "test_date"], sort=True):
        promoted = group[group["promoted"].astype(bool)].copy()
        if promoted.empty:
            baseline = group.iloc[0].to_dict()
            selected_rows.append(
                {
                    "exit_profile_source": profile,
                    "test_date": test_date,
                    "selected": False,
                    "ttl_sec": None,
                    "gate_name": "cross_now",
                    "gate_description": "default immediate taker exit",
                    "gate_thresholds_json": "{}",
                    "promote_reason": "no_promoted_prior_gate",
                    "candidate_score": None,
                    **{
                        key: baseline.get(key)
                        for key in [
                            "test_n",
                            "test_exposure",
                            "pure_taker_weighted_net_bps",
                        ]
                    },
                    "wait_attempts": 0,
                    "wait_attempt_exposure": 0.0,
                    "wait_delta_weighted_bps": 0.0,
                    "wait_controller_weighted_net_bps": baseline.get("pure_taker_weighted_net_bps", 0.0),
                }
            )
        else:
            best = promoted.sort_values(
                ["candidate_score", "train_weighted_mean_wait_value_bps", "train_n"],
                ascending=[False, False, False],
            ).iloc[0].to_dict()
            best["selected"] = True
            selected_rows.append(best)
    selected = pd.DataFrame(selected_rows)
    return candidate_rows, selected


def build_event_rows(panel: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for selected_row in selected.itertuples(index=False):
        if not bool(getattr(selected_row, "selected")):
            continue
        profile = str(getattr(selected_row, "exit_profile_source"))
        test_date = str(getattr(selected_row, "test_date"))
        ttl = float(getattr(selected_row, "ttl_sec"))
        gate_name = str(getattr(selected_row, "gate_name"))
        gate = GATE_BY_NAME[gate_name]
        thresholds = json.loads(str(getattr(selected_row, "gate_thresholds_json")))
        day_panel = panel[
            (panel["exit_profile_source"].astype(str) == profile)
            & (panel["date"].astype(str) == test_date)
            & (pd.to_numeric(panel["ttl_sec"], errors="coerce") == ttl)
        ]
        mask = apply_gate(day_panel, gate, thresholds)
        attempts = day_panel.loc[mask].copy()
        for _, row in attempts.iterrows():
            exposure = float(row["actual_exposure"])
            wait_value = float(row["wait_value_bps"])
            out = {
                "schema_id": "ccusdt_exit_controller_v1_wait_event_v1",
                "runtime_safe_gate": True,
                "oracle_free_test": True,
                "exit_profile_source": profile,
                "date": test_date,
                "shadow_position_id": int(row["shadow_position_id"]),
                "entry_ts_us": int(row["entry_ts_us"]),
                "exit_decision_ts_us": int(row["exit_ts_us"]),
                "cell": str(row["cell"]),
                "entry_side": str(row["entry_side"]),
                "exit_action": str(row["exit_action"]),
                "actual_exposure": exposure,
                "controller_action": "wait_then_cross",
                "ttl_sec": ttl,
                "gate_name": gate_name,
                "gate_thresholds_json": str(getattr(selected_row, "gate_thresholds_json")),
                "cross_now_price": float(row["immediate_taker_price"]),
                "cross_now_net_bps": float(row["immediate_taker_net_bps"]),
                "wait_cross_ts_us": int(row["wait_quote_ts_us"]),
                "wait_cross_price": float(row["wait_taker_price"]),
                "wait_cross_net_bps": float(row["wait_taker_net_bps"]),
                "final_net_bps": float(row["wait_taker_net_bps"]),
                "wait_value_bps": wait_value,
                "delay_loss_bps": float(row["delay_loss_bps"]),
                "post_wait_peak_bps": float(row["post_wait_peak_bps"]),
                "post_wait_trough_bps": float(row["post_wait_trough_bps"]),
                "post_wait_reclaim_bps": float(row["post_wait_reclaim_bps"]),
                "post_wait_peak_giveback_bps": float(row["post_wait_peak_giveback_bps"]),
                "post_wait_max_delay_loss_bps": float(row["post_wait_max_delay_loss_bps"]),
                "weighted_wait_value_bps": wait_value * exposure,
                "weighted_delay_loss_bps": float(row["delay_loss_bps"]) * exposure,
                "exit_spread_bps": float(row["exit_spread_bps"]),
                "path_h_bps": float(row["path_h_bps"]),
                "path_d_bps": float(row["path_d_bps"]),
                "signed_top_depth_imbalance": float(row["signed_top_depth_imbalance"]),
                "same_flow_imbalance_5s": float(row["same_flow_imbalance_5s"]),
                "recent_mid_alpha_5s_bps": float(row["recent_mid_alpha_5s_bps"]),
                "decision_frames_since_mid_change": optional_float(row.get("decision_frames_since_mid_change")),
            }
            rows.append(out)
    return pd.DataFrame(rows)


def aggregate_rows(selected: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile, group in selected.groupby("exit_profile_source", sort=True):
        profile_events = events[events["exit_profile_source"] == profile] if not events.empty else pd.DataFrame()
        baseline = float(pd.to_numeric(group["pure_taker_weighted_net_bps"], errors="coerce").fillna(0.0).sum())
        wait_delta = float(pd.to_numeric(group["wait_delta_weighted_bps"], errors="coerce").fillna(0.0).sum())
        row = {
            "exit_profile_source": profile,
            "days": int(group["test_date"].nunique()),
            "selected_wait_days": int(group["selected"].astype(bool).sum()),
            "wait_attempts": int(pd.to_numeric(group["wait_attempts"], errors="coerce").fillna(0).sum()),
            "wait_attempt_exposure": float(pd.to_numeric(group["wait_attempt_exposure"], errors="coerce").fillna(0.0).sum()),
            "pure_taker_weighted_net_bps": baseline,
            "wait_delta_weighted_bps": wait_delta,
            "wait_controller_weighted_net_bps": baseline + wait_delta,
            "wait_weighted_delay_loss_bps": float(pd.to_numeric(group["wait_weighted_delay_loss_bps"], errors="coerce").fillna(0.0).sum()),
            "event_worst_wait_value_bps": float(pd.to_numeric(profile_events.get("wait_value_bps", pd.Series(dtype=float)), errors="coerce").min())
            if not profile_events.empty
            else 0.0,
            "event_cvar10_wait_value_bps": cvar_left(profile_events["wait_value_bps"], 0.10) if not profile_events.empty else 0.0,
            "event_weighted_post_peak_giveback_bps": float(
                pd.to_numeric(profile_events.get("post_wait_peak_giveback_bps", pd.Series(dtype=float)), errors="coerce")
                .fillna(0.0)
                .mul(pd.to_numeric(profile_events.get("actual_exposure", pd.Series(dtype=float)), errors="coerce").fillna(0.0))
                .sum()
            )
            if not profile_events.empty
            else 0.0,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 40) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    use_cols = [col for col in columns if col in df.columns]
    view = df.loc[:, use_cols].head(max_rows)
    lines = ["| " + " | ".join(use_cols) + " |", "| " + " | ".join(["---"] * len(use_cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for col in use_cols:
            value = row[col]
            cells.append(fmt(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(path: Path, summary: dict[str, Any], selected: pd.DataFrame, aggregate: pd.DataFrame, events: pd.DataFrame) -> None:
    selected_view = selected.sort_values(["exit_profile_source", "test_date"])
    aggregate_view = aggregate.sort_values("wait_delta_weighted_bps", ascending=False)
    total_baseline = float(pd.to_numeric(aggregate["pure_taker_weighted_net_bps"], errors="coerce").fillna(0.0).sum())
    total_delta = float(pd.to_numeric(aggregate["wait_delta_weighted_bps"], errors="coerce").fillna(0.0).sum())
    total_controller = total_baseline + total_delta
    positive_profiles = aggregate[pd.to_numeric(aggregate["wait_delta_weighted_bps"], errors="coerce").fillna(0.0) > 0.0]
    wait_profiles = aggregate[pd.to_numeric(aggregate["wait_attempts"], errors="coerce").fillna(0.0) > 0.0]
    no_wait_profiles = aggregate[pd.to_numeric(aggregate["wait_attempts"], errors="coerce").fillna(0.0) == 0.0]
    positive_text = (
        ", ".join(
            f"{row.exit_profile_source} (+{float(row.wait_delta_weighted_bps):.4f})"
            for row in positive_profiles.itertuples(index=False)
        )
        if not positive_profiles.empty
        else "none"
    )
    no_wait_text = (
        ", ".join(str(row.exit_profile_source) for row in no_wait_profiles.itertuples(index=False))
        if not no_wait_profiles.empty
        else "none"
    )
    event_view = (
        events.groupby(["exit_profile_source", "date", "gate_name", "ttl_sec"], sort=True)
        .agg(
            wait_attempts=("shadow_position_id", "count"),
            exposure=("actual_exposure", "sum"),
            weighted_wait_value=("weighted_wait_value_bps", "sum"),
            weighted_delay_loss=("weighted_delay_loss_bps", "sum"),
            worst_wait_value=("wait_value_bps", "min"),
        )
        .reset_index()
        if not events.empty
        else pd.DataFrame()
    )
    lines = [
        "# CCUSDT q70 idle01_g1 ExitControllerV1 conditional wait policy",
        "",
        "This is the first unified exit-controller prototype. It only enables:",
        "",
        "\\[",
        "a_t \\in \\{\\text{cross now},\\ \\text{wait }\\tau\\text{ then cross}\\}.",
        "\\]",
        "",
        "Maker/post-only fallback is intentionally disabled.",
        "",
        "## Rule",
        "",
        "For each test date, exit profile, TTL, and predefined runtime-safe gate, train on dates strictly before the test date. Promote wait only if prior evidence satisfies:",
        "",
        "\\[",
        "\\mathbb E[W_t(\\tau)\\mid X_t] > m",
        "\\]",
        "",
        "plus positive-day, CVaR, worst-event, and worst-day guards.",
        "",
        "## Scope",
        "",
        f"- Panel: `{summary['panel_path']}`",
        f"- Evaluation dates: `{summary['eval_from_date']}..{summary['eval_to_date']}`",
        f"- Margin: `{fmt(summary['margin_bps'])}` bps",
        f"- Min train n/exposure: `{summary['min_train_n']}` / `{fmt(summary['min_train_exposure'])}`",
        f"- Min prior days / positive-day fraction: `{summary['min_prior_days']}` / `{fmt(summary['min_positive_day_frac'])}`",
        f"- Min CVaR10 / worst event / worst day: `{fmt(summary['min_cvar10_bps'])}` / `{fmt(summary['min_worst_bps'])}` / `{fmt(summary['min_day_sum_bps'])}`",
        f"- Candidate rows: `{summary['candidate_rows']}`",
        f"- Promoted candidate rows: `{summary['promoted_candidate_rows']}`",
        "",
        "## Readout",
        "",
        f"- Pure taker baseline across profiles: `{fmt(total_baseline)}` weighted bp-units.",
        f"- ExitControllerV1 wait delta: `{fmt(total_delta)}`; controller total: `{fmt(total_controller)}`.",
        f"- Positive profile deltas: `{positive_text}`.",
        f"- Profiles left at `cross_now`: `{no_wait_text}`.",
        "- Treat selected waits as fast-line candidates. Strict runner validation is still required before execution promotion.",
        "",
        "## Aggregate",
        "",
    ]
    lines.extend(
        markdown_table(
            aggregate_view,
            [
                "exit_profile_source",
                "days",
                "selected_wait_days",
                "wait_attempts",
                "wait_attempt_exposure",
                "pure_taker_weighted_net_bps",
                "wait_delta_weighted_bps",
                "wait_controller_weighted_net_bps",
                "wait_weighted_delay_loss_bps",
                "event_worst_wait_value_bps",
                "event_cvar10_wait_value_bps",
            ],
            max_rows=20,
        )
    )
    lines.extend(["", "## Selected Prior-Date Policy", ""])
    lines.extend(
        markdown_table(
            selected_view,
            [
                "exit_profile_source",
                "test_date",
                "selected",
                "ttl_sec",
                "gate_name",
                "promote_reason",
                "train_n",
                "train_weighted_mean_wait_value_bps",
                "train_cvar10_wait_value_bps",
                "train_worst_wait_value_bps",
                "train_positive_day_frac",
                "train_min_day_wait_sum_bps",
                "wait_attempts",
                "wait_delta_weighted_bps",
                "wait_controller_weighted_net_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Event Summary", ""])
    lines.extend(
        markdown_table(
            event_view,
            [
                "exit_profile_source",
                "date",
                "gate_name",
                "ttl_sec",
                "wait_attempts",
                "exposure",
                "weighted_wait_value",
                "weighted_delay_loss",
                "worst_wait_value",
            ],
            max_rows=80,
        )
    )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Runtime gates use only exit-decision-visible fields. Post-exit flow, reclaim, wait value, delay loss, and PnL-like outcomes are evaluation labels only.",
            "",
            "## Files",
            "",
            f"- Candidate daily: `{summary['outputs']['candidate_daily_csv']}`",
            f"- Selected daily: `{summary['outputs']['selected_daily_csv']}`",
            f"- Events: `{summary['outputs']['events_parquet']}`",
            f"- Summary: `{summary['outputs']['summary_json']}`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    panel_path = repo_path(repo_root, args.panel)
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = pq.read_table(panel_path).to_pandas()
    if not bool(panel["runtime_safe"].all()):
        raise ValueError("conditional wait panel contains non-runtime-safe rows")
    needed = {
        "exit_profile_source",
        "date",
        "ttl_sec",
        "wait_value_bps",
        "weighted_wait_value_bps",
        "immediate_taker_net_bps",
        "actual_exposure",
        *RUNTIME_FEATURES,
    }
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise ValueError(f"panel missing columns: {missing}")
    candidate_rows, selected_rows = build_candidate_rows(panel, args)
    event_rows = build_event_rows(panel, selected_rows)
    aggregates = aggregate_rows(selected_rows, event_rows)

    config = {
        "schema_id": "ccusdt_exit_controller_v1_wait_policy_config_v1",
        "action_space": ["cross_now", "wait_tau_then_cross"],
        "maker_enabled": False,
        "gate_specs": [
            {
                "name": gate.name,
                "description": gate.description,
                "cell": gate.cell,
                "conditions": [condition.__dict__ for condition in gate.conditions],
            }
            for gate in GATES
        ],
        "runtime_features": sorted(RUNTIME_FEATURES),
        "diagnostic_label_columns": sorted(DIAGNOSTIC_LABEL_COLUMNS),
        "margin_bps": args.margin_bps,
        "eval_from_date": args.eval_from_date,
        "eval_to_date": args.eval_to_date,
        "min_train_n": args.min_train_n,
        "min_train_exposure": args.min_train_exposure,
        "min_prior_days": args.min_prior_days,
        "min_positive_day_frac": args.min_positive_day_frac,
        "min_cvar10_bps": args.min_cvar10_bps,
        "min_worst_bps": args.min_worst_bps,
        "min_day_sum_bps": args.min_day_sum_bps,
    }
    data_manifest = {
        "schema_id": "ccusdt_exit_controller_v1_wait_policy_data_manifest_v1",
        "panel_path": str(panel_path),
        "panel_sha256": file_sha256(panel_path),
        "panel_rows": int(len(panel)),
        "boundary": (
            "policy gates use current runtime-safe features and prior-date wait labels; "
            "current-date wait/path labels are used only for evaluation"
        ),
    }
    summary = {
        "schema_id": "ccusdt_exit_controller_v1_wait_policy_summary_v1",
        "ok": True,
        "panel_path": str(panel_path),
        "eval_from_date": args.eval_from_date,
        "eval_to_date": args.eval_to_date,
        "margin_bps": args.margin_bps,
        "min_train_n": args.min_train_n,
        "min_train_exposure": args.min_train_exposure,
        "min_prior_days": args.min_prior_days,
        "min_positive_day_frac": args.min_positive_day_frac,
        "min_cvar10_bps": args.min_cvar10_bps,
        "min_worst_bps": args.min_worst_bps,
        "min_day_sum_bps": args.min_day_sum_bps,
        "candidate_rows": int(len(candidate_rows)),
        "promoted_candidate_rows": int(candidate_rows["promoted"].astype(bool).sum()),
        "selected_rows": int(len(selected_rows)),
        "event_rows": int(len(event_rows)),
        "profile_aggregates": aggregates.to_dict(orient="records"),
        "config_hash": stable_hash(config),
        "data_manifest_hash": stable_hash(data_manifest),
        "outputs": {
            "config_json": str(out_dir / "config.json"),
            "data_manifest_json": str(out_dir / "data_manifest.json"),
            "summary_json": str(out_dir / "summary.json"),
            "candidate_daily_csv": str(out_dir / "conditional_wait_candidate_daily.csv"),
            "candidate_daily_parquet": str(out_dir / "conditional_wait_candidate_daily.parquet"),
            "selected_daily_csv": str(out_dir / "conditional_wait_selected_daily.csv"),
            "aggregate_csv": str(out_dir / "conditional_wait_aggregate.csv"),
            "events_csv": str(out_dir / "conditional_wait_events.csv"),
            "events_parquet": str(out_dir / "conditional_wait_events.parquet"),
            "report_md": str(report_path),
        },
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "data_manifest.json").write_text(json.dumps(data_manifest, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_csv(out_dir / "conditional_wait_candidate_daily.csv", candidate_rows)
    write_parquet(out_dir / "conditional_wait_candidate_daily.parquet", candidate_rows)
    write_csv(out_dir / "conditional_wait_selected_daily.csv", selected_rows)
    write_csv(out_dir / "conditional_wait_aggregate.csv", aggregates)
    write_csv(out_dir / "conditional_wait_events.csv", event_rows)
    write_parquet(out_dir / "conditional_wait_events.parquet", event_rows)
    write_report(report_path, summary, selected_rows, aggregates, event_rows)
    print(json.dumps({"ok": True, "summary": str(out_dir / "summary.json"), "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
