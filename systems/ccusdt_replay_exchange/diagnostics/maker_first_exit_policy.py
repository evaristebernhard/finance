#!/usr/bin/env python
"""Prior-date maker-first exit prototype over the maker opportunity panel.

The opportunity panel contains realized fill/decay labels for diagnostics. This
script turns it into an oracle-free fast prototype by fitting simple
runtime-safe gates only on dates strictly before the test date, then evaluating
the selected maker-first exits on the test date.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_PANEL = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_exit_opportunity_q70_idle01_g1_20260516_18_20260522/"
    "maker_exit_opportunity_panel.parquet"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_first_exit_policy_q70_idle01_g1_20260516_18_20260522"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-maker-first-exit-policy-prototype-20260522.md")

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

LABEL_COLUMNS = {
    "queue_fill",
    "queue_fill_delay_us",
    "unfilled_decay_bps",
    "selection_cost_bps",
    "selection_cost_positive_bps",
    "maker_first_queue_delta_vs_taker_bps",
    "queue_selection_adjusted_delta_bps",
}


@dataclass(frozen=True)
class GateSpec:
    name: str
    description: str
    quantiles: dict[str, float]
    cell: str | None = None


GATES = [
    GateSpec("all", "no feature gate", {}),
    GateSpec("cell_11", "11_r5_frames only", {}, cell="11_r5_frames"),
    GateSpec("spread_q70", "exit spread >= prior q70", {"exit_spread_bps": 0.70}),
    GateSpec("spread_q80", "exit spread >= prior q80", {"exit_spread_bps": 0.80}),
    GateSpec("spread_q90", "exit spread >= prior q90", {"exit_spread_bps": 0.90}),
    GateSpec("same_flow_q70", "same-side 5s flow imbalance >= prior q70", {"same_flow_imbalance_5s": 0.70}),
    GateSpec("recent_alpha_q70", "recent 5s same-direction mid alpha >= prior q70", {"recent_mid_alpha_5s_bps": 0.70}),
    GateSpec("depth_support_q70", "signed top-depth imbalance >= prior q70", {"signed_top_depth_imbalance": 0.70}),
    GateSpec(
        "spread_q70_same_flow_q70",
        "exit spread and same-side flow both >= prior q70",
        {"exit_spread_bps": 0.70, "same_flow_imbalance_5s": 0.70},
    ),
    GateSpec(
        "spread_q80_same_flow_q70",
        "exit spread >= prior q80 and same-side flow >= prior q70",
        {"exit_spread_bps": 0.80, "same_flow_imbalance_5s": 0.70},
    ),
    GateSpec(
        "cell_11_spread_q70",
        "11_r5_frames and exit spread >= prior q70",
        {"exit_spread_bps": 0.70},
        cell="11_r5_frames",
    ),
]
GATE_BY_NAME = {gate.name: gate for gate in GATES}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--eval-from-date")
    parser.add_argument("--eval-to-date")
    parser.add_argument("--fill-model", choices=["queue"], default="queue")
    parser.add_argument("--margin-bps", type=float, default=0.05)
    parser.add_argument("--min-train-n", type=int, default=20)
    parser.add_argument("--min-train-exposure", type=float, default=10.0)
    parser.add_argument("--min-prior-days", type=int, default=1)
    parser.add_argument("--min-positive-day-frac", type=float, default=1.0)
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


def day_positive_frac(df: pd.DataFrame, column: str) -> float:
    if df.empty:
        return 0.0
    values = [weighted_sum(group, column) for _, group in df.groupby("date", sort=True)]
    if not values:
        return 0.0
    return float(sum(1 for value in values if value > 0.0) / len(values))


def day_count(df: pd.DataFrame) -> int:
    return int(df["date"].nunique()) if not df.empty else 0


def compute_thresholds(train: pd.DataFrame, gate: GateSpec) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for feature, quantile in gate.quantiles.items():
        values = pd.to_numeric(train[feature], errors="coerce").dropna()
        if values.empty:
            thresholds[feature] = float("nan")
        else:
            thresholds[feature] = float(values.quantile(quantile))
    return thresholds


def apply_gate(df: pd.DataFrame, gate: GateSpec, thresholds: dict[str, float]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    if gate.cell is not None:
        mask &= df["cell"].astype(str).eq(gate.cell)
    for feature, threshold in thresholds.items():
        if not math.isfinite(threshold):
            mask &= False
        else:
            mask &= pd.to_numeric(df[feature], errors="coerce") >= threshold
    return mask


def train_stats(group: pd.DataFrame) -> dict[str, Any]:
    return {
        "train_n": int(len(group)),
        "train_position_count": int(group["shadow_position_id"].nunique()) if not group.empty else 0,
        "train_exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "train_prior_days": day_count(group),
        "train_fill_rate": float(pd.to_numeric(group["queue_fill"], errors="coerce").fillna(False).astype(bool).mean())
        if len(group)
        else 0.0,
        "train_weighted_mean_delta_bps": weighted_mean(group, "maker_first_queue_delta_vs_taker_bps"),
        "train_weighted_sum_delta_bps": weighted_sum(group, "maker_first_queue_delta_vs_taker_bps"),
        "train_weighted_mean_selection_adjusted_bps": weighted_mean(group, "queue_selection_adjusted_delta_bps"),
        "train_weighted_sum_selection_adjusted_bps": weighted_sum(group, "queue_selection_adjusted_delta_bps"),
        "train_positive_day_frac": day_positive_frac(group, "queue_selection_adjusted_delta_bps"),
        "train_weighted_mean_spread_saving_bps": weighted_mean(group, "spread_saving_bps"),
        "train_weighted_mean_unfilled_decay_bps": weighted_mean(group[~group["queue_fill"].astype(bool)], "unfilled_decay_bps")
        if len(group)
        else 0.0,
        "train_weighted_mean_selection_cost_bps": weighted_mean(group[group["queue_fill"].astype(bool)], "selection_cost_bps")
        if len(group)
        else 0.0,
    }


def test_stats(group: pd.DataFrame, selected_mask: pd.Series) -> dict[str, Any]:
    selected = group.loc[selected_mask]
    baseline = weighted_sum(group, "immediate_taker_net_bps")
    maker_delta = weighted_sum(selected, "maker_first_queue_delta_vs_taker_bps")
    maker_adj_delta = weighted_sum(selected, "queue_selection_adjusted_delta_bps")
    return {
        "test_n": int(len(group)),
        "test_exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "maker_attempts": int(len(selected)),
        "maker_attempt_exposure": float(pd.to_numeric(selected["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "maker_fill_rate": float(pd.to_numeric(selected["queue_fill"], errors="coerce").fillna(False).astype(bool).mean())
        if len(selected)
        else 0.0,
        "pure_taker_weighted_net_bps": baseline,
        "maker_delta_weighted_bps": maker_delta,
        "maker_selection_adjusted_delta_weighted_bps": maker_adj_delta,
        "maker_first_weighted_net_bps": baseline + maker_delta,
        "maker_first_selection_adjusted_net_bps": baseline + maker_adj_delta,
        "maker_weighted_mean_delta_bps": weighted_mean(selected, "maker_first_queue_delta_vs_taker_bps")
        if len(selected)
        else 0.0,
        "maker_weighted_mean_selection_adjusted_bps": weighted_mean(selected, "queue_selection_adjusted_delta_bps")
        if len(selected)
        else 0.0,
        "saved_spread_weighted_bps": weighted_sum(selected[selected["queue_fill"].astype(bool)], "spread_saving_bps")
        if len(selected)
        else 0.0,
        "missed_fill_decay_weighted_bps": weighted_sum(selected[~selected["queue_fill"].astype(bool)], "unfilled_decay_bps")
        if len(selected)
        else 0.0,
        "adverse_selection_weighted_bps": weighted_sum(selected[selected["queue_fill"].astype(bool)], "selection_cost_bps")
        if len(selected)
        else 0.0,
    }


def promote(stats: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str]:
    if stats["train_prior_days"] < args.min_prior_days:
        return False, "insufficient_prior_days"
    if stats["train_n"] < args.min_train_n:
        return False, "insufficient_train_n"
    if stats["train_exposure"] < args.min_train_exposure:
        return False, "insufficient_train_exposure"
    if stats["train_positive_day_frac"] + 1e-12 < args.min_positive_day_frac:
        return False, "unstable_prior_days"
    if stats["train_weighted_mean_selection_adjusted_bps"] <= args.margin_bps:
        return False, "edge_below_margin"
    return True, "promoted_prior_edge"


def build_candidate_rows(panel: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    eval_from = str(args.eval_from_date) if args.eval_from_date else None
    eval_to = str(args.eval_to_date) if args.eval_to_date else None
    for profile in sorted(panel["exit_profile_source"].unique()):
        profile_panel = panel[panel["exit_profile_source"] == profile]
        for test_date in sorted(profile_panel["date"].unique()):
            if eval_from is not None and str(test_date) < eval_from:
                continue
            if eval_to is not None and str(test_date) > eval_to:
                continue
            train_profile = profile_panel[profile_panel["date"] < test_date]
            test_profile = profile_panel[profile_panel["date"] == test_date]
            day_candidates: list[dict[str, Any]] = []
            for ttl in sorted(test_profile["ttl_sec"].unique()):
                train_ttl = train_profile[train_profile["ttl_sec"] == ttl]
                test_ttl = test_profile[test_profile["ttl_sec"] == ttl]
                for gate in GATES:
                    thresholds = compute_thresholds(train_ttl, gate)
                    train_mask = apply_gate(train_ttl, gate, thresholds) if not train_ttl.empty else pd.Series([], dtype=bool)
                    test_mask = apply_gate(test_ttl, gate, thresholds) if not test_ttl.empty else pd.Series([], dtype=bool)
                    train_group = train_ttl.loc[train_mask]
                    stats = train_stats(train_group)
                    is_promoted, reason = promote(stats, args)
                    effective_test_mask = test_mask if is_promoted else pd.Series(False, index=test_ttl.index)
                    row = {
                        "schema_id": "ccusdt_maker_first_exit_candidate_v1",
                        "runtime_safe_gate": True,
                        "oracle_free_test": True,
                        "exit_profile_source": profile,
                        "test_date": test_date,
                        "ttl_sec": float(ttl),
                        "gate_name": gate.name,
                        "gate_description": gate.description,
                        "gate_cell": gate.cell,
                        "gate_thresholds_json": json.dumps(thresholds, sort_keys=True),
                        "margin_bps": args.margin_bps,
                        "promoted": is_promoted,
                        "promote_reason": reason,
                    }
                    row.update(stats)
                    row.update(test_stats(test_ttl, effective_test_mask))
                    rows.append(row)
                    if is_promoted:
                        day_candidates.append(row)
            baseline_by_date = {
                "exit_profile_source": profile,
                "test_date": test_date,
                "pure_taker_weighted_net_bps": weighted_sum(
                    test_profile[test_profile["ttl_sec"] == sorted(test_profile["ttl_sec"].unique())[0]],
                    "immediate_taker_net_bps",
                ),
                "test_n": int(test_profile[test_profile["ttl_sec"] == sorted(test_profile["ttl_sec"].unique())[0]].shape[0]),
            }
            if day_candidates:
                chosen = max(
                    day_candidates,
                    key=lambda item: (
                        float(item["train_weighted_mean_selection_adjusted_bps"]),
                        float(item["train_exposure"]),
                        -float(item["ttl_sec"]),
                    ),
                )
                selected_rows.append({"selected": True, **chosen})
            else:
                selected_rows.append(
                    {
                        "schema_id": "ccusdt_maker_first_exit_selected_v1",
                        "runtime_safe_gate": True,
                        "oracle_free_test": True,
                        "selected": False,
                        "exit_profile_source": profile,
                        "test_date": test_date,
                        "ttl_sec": None,
                        "gate_name": "direct_taker",
                        "gate_description": "no prior-date maker gate passed",
                        "promoted": False,
                        "promote_reason": "no_promoted_prior_gate",
                        "maker_attempts": 0,
                        "maker_attempt_exposure": 0.0,
                        "maker_fill_rate": 0.0,
                        "maker_delta_weighted_bps": 0.0,
                        "maker_selection_adjusted_delta_weighted_bps": 0.0,
                        "maker_first_weighted_net_bps": baseline_by_date["pure_taker_weighted_net_bps"],
                        "maker_first_selection_adjusted_net_bps": baseline_by_date["pure_taker_weighted_net_bps"],
                        **baseline_by_date,
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(selected_rows)


def aggregate_selected(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile, group in selected.groupby("exit_profile_source", sort=True):
        baseline = float(pd.to_numeric(group["pure_taker_weighted_net_bps"], errors="coerce").fillna(0.0).sum())
        delta = float(pd.to_numeric(group["maker_delta_weighted_bps"], errors="coerce").fillna(0.0).sum())
        adj_delta = float(pd.to_numeric(group["maker_selection_adjusted_delta_weighted_bps"], errors="coerce").fillna(0.0).sum())
        rows.append(
            {
                "exit_profile_source": profile,
                "days": int(group["test_date"].nunique()),
                "selected_maker_days": int((group["selected"].astype(bool)).sum()),
                "maker_attempts": int(pd.to_numeric(group["maker_attempts"], errors="coerce").fillna(0).sum()),
                "maker_attempt_exposure": float(pd.to_numeric(group["maker_attempt_exposure"], errors="coerce").fillna(0.0).sum()),
                "pure_taker_weighted_net_bps": baseline,
                "maker_delta_weighted_bps": delta,
                "maker_first_weighted_net_bps": baseline + delta,
                "maker_selection_adjusted_delta_weighted_bps": adj_delta,
                "maker_first_selection_adjusted_net_bps": baseline + adj_delta,
                "saved_spread_weighted_bps": float(pd.to_numeric(group.get("saved_spread_weighted_bps"), errors="coerce").fillna(0.0).sum()),
                "missed_fill_decay_weighted_bps": float(pd.to_numeric(group.get("missed_fill_decay_weighted_bps"), errors="coerce").fillna(0.0).sum()),
                "adverse_selection_weighted_bps": float(pd.to_numeric(group.get("adverse_selection_weighted_bps"), errors="coerce").fillna(0.0).sum()),
            }
        )
    return pd.DataFrame(rows)


def build_event_rows(panel: pd.DataFrame, selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for selected_row in selected.to_dict(orient="records"):
        if not bool(selected_row.get("selected")):
            continue
        gate_name = str(selected_row.get("gate_name") or "")
        gate = GATE_BY_NAME.get(gate_name)
        if gate is None:
            continue
        ttl = optional_float(selected_row.get("ttl_sec"))
        if ttl is None:
            continue
        thresholds = json.loads(str(selected_row.get("gate_thresholds_json") or "{}"))
        profile = str(selected_row["exit_profile_source"])
        test_date = str(selected_row["test_date"])
        day_panel = panel[
            (panel["exit_profile_source"].astype(str) == profile)
            & (panel["date"].astype(str) == test_date)
            & (pd.to_numeric(panel["ttl_sec"], errors="coerce") == ttl)
        ].copy()
        mask = apply_gate(day_panel, gate, thresholds)
        attempts = day_panel.loc[mask].copy()
        for _, row in attempts.iterrows():
            filled = bool(row["queue_fill"])
            final_net = (
                float(row["maker_touch_net_bps"]) if filled else float(row["fallback_taker_net_bps"])
            )
            saved_spread = float(row["spread_saving_bps"]) if filled else 0.0
            missed_decay = 0.0 if filled else float(row["unfilled_decay_bps"])
            adverse_selection = float(row["selection_cost_bps"]) if filled else 0.0
            event = {
                "schema_id": "ccusdt_maker_first_exit_event_v1",
                "runtime_safe_gate": True,
                "oracle_free_test": True,
                "exit_profile_source": profile,
                "date": test_date,
                "shadow_position_id": int(row["shadow_position_id"]),
                "entry_ts_us": int(row["entry_ts_us"]),
                "exit_decision_ts_us": int(row["exit_ts_us"]),
                "ttl_sec": ttl,
                "gate_name": gate_name,
                "gate_thresholds_json": json.dumps(thresholds, sort_keys=True),
                "cell": row["cell"],
                "entry_side": row["entry_side"],
                "exit_action": row["exit_action"],
                "actual_exposure": float(row["actual_exposure"]),
                "maker_order_posted": True,
                "maker_order_type": "post_only_reduce_at_touch",
                "maker_post_price": float(row["maker_touch_price"]),
                "maker_queue_ahead_qty": float(row["maker_queue_ahead_qty"]),
                "maker_filled": filled,
                "maker_fill_ts_us": int(row["queue_fill_ts_us"]) if pd.notna(row["queue_fill_ts_us"]) else None,
                "maker_fill_delay_us": int(row["queue_fill_delay_us"]) if pd.notna(row["queue_fill_delay_us"]) else None,
                "cancel_reprice": False,
                "taker_fallback": not filled,
                "fallback_ts_us": int(row["fallback_quote_ts_us"]) if not filled else None,
                "fallback_taker_price": float(row["fallback_taker_price"]) if not filled else None,
                "pure_taker_net_bps": float(row["immediate_taker_net_bps"]),
                "maker_touch_net_bps": float(row["maker_touch_net_bps"]),
                "fallback_taker_net_bps": float(row["fallback_taker_net_bps"]),
                "final_net_bps": final_net,
                "final_delta_vs_taker_bps": final_net - float(row["immediate_taker_net_bps"]),
                "selection_adjusted_delta_bps": float(row["queue_selection_adjusted_delta_bps"]),
                "saved_spread_bps": saved_spread,
                "missed_fill_decay_bps": missed_decay,
                "adverse_selection_bps": adverse_selection,
                "weighted_final_delta_vs_taker_bps": (
                    final_net - float(row["immediate_taker_net_bps"])
                )
                * float(row["actual_exposure"]),
                "weighted_selection_adjusted_delta_bps": float(row["queue_selection_adjusted_delta_bps"])
                * float(row["actual_exposure"]),
                "weighted_saved_spread_bps": saved_spread * float(row["actual_exposure"]),
                "weighted_missed_fill_decay_bps": missed_decay * float(row["actual_exposure"]),
                "weighted_adverse_selection_bps": adverse_selection * float(row["actual_exposure"]),
                "exit_spread_bps": float(row["exit_spread_bps"]),
                "path_h_bps": float(row["path_h_bps"]),
                "path_d_bps": float(row["path_d_bps"]),
                "signed_top_depth_imbalance": float(row["signed_top_depth_imbalance"]),
                "same_flow_imbalance_5s": float(row["same_flow_imbalance_5s"]),
                "recent_mid_alpha_5s_bps": float(row["recent_mid_alpha_5s_bps"]),
            }
            rows.append(event)
    return pd.DataFrame(rows)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    use_cols = [col for col in columns if col in df.columns]
    lines = ["| " + " | ".join(use_cols) + " |", "| " + " | ".join(["---"] * len(use_cols)) + " |"]
    for _, row in df.loc[:, use_cols].head(max_rows).iterrows():
        cells = []
        for col in use_cols:
            value = row[col]
            if isinstance(value, float):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(
    path: Path,
    summary: dict[str, Any],
    candidates: pd.DataFrame,
    selected: pd.DataFrame,
    aggregate: pd.DataFrame,
    events: pd.DataFrame,
) -> None:
    promoted = candidates[candidates["promoted"].astype(bool)].copy()
    promoted = promoted.sort_values(
        ["test_date", "exit_profile_source", "train_weighted_mean_selection_adjusted_bps"],
        ascending=[True, True, False],
    )
    selected_view = selected.sort_values(["exit_profile_source", "test_date"])
    aggregate_view = aggregate.sort_values("maker_delta_weighted_bps", ascending=False)
    event_view = (
        events.groupby(["exit_profile_source", "date", "gate_name"], sort=True)
        .agg(
            maker_attempts=("shadow_position_id", "count"),
            exposure=("actual_exposure", "sum"),
            maker_fill_rate=("maker_filled", "mean"),
            weighted_delta=("weighted_final_delta_vs_taker_bps", "sum"),
            weighted_selection_adjusted_delta=("weighted_selection_adjusted_delta_bps", "sum"),
            saved_spread=("weighted_saved_spread_bps", "sum"),
            missed_decay=("weighted_missed_fill_decay_bps", "sum"),
            adverse_selection=("weighted_adverse_selection_bps", "sum"),
        )
        .reset_index()
        if not events.empty
        else pd.DataFrame()
    )
    lines = [
        "# CCUSDT q70 idle01_g1 maker-first exit policy prototype",
        "",
        "This is a fast-line, prior-date prototype over the maker exit opportunity panel. It is not a strict Runner maker lifecycle yet.",
        "",
        "## Rule",
        "",
        "For each test date, exit profile, TTL, and predefined runtime-safe gate, estimate from dates strictly before the test date:",
        "",
        "\\[",
        "\\widehat E[\\Delta(\\tau)] = \\widehat p(\\tau)\\Delta^{spread} - \\widehat L^{unfilled}(\\tau) - \\widehat A^{selection}(\\tau).",
        "\\]",
        "",
        "The prototype promotes a maker-first exit only if prior sample, exposure, day stability, and margin gates pass. Current-day realized fill/decay labels are used only for evaluation.",
        "",
        "## Scope",
        "",
        f"- Panel: `{summary['panel_path']}`",
        f"- Evaluation dates: `{summary.get('eval_from_date') or 'panel_start'}..{summary.get('eval_to_date') or 'panel_end'}`",
        f"- Fill model: `{summary['fill_model']}`",
        f"- Margin: `{fmt(summary['margin_bps'])}` bps",
        f"- Min train n/exposure: `{summary['min_train_n']}` / `{fmt(summary['min_train_exposure'])}`",
        f"- Min prior days / positive-day fraction: `{summary['min_prior_days']}` / `{fmt(summary['min_positive_day_frac'])}`",
        f"- Candidate rows: `{summary['candidate_rows']}`",
        f"- Promoted candidate rows: `{summary['promoted_candidate_rows']}`",
        "",
        "## Selected Prior-Date Policy",
        "",
    ]
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
                "train_weighted_mean_selection_adjusted_bps",
                "maker_attempts",
                "maker_attempt_exposure",
                "maker_fill_rate",
                "pure_taker_weighted_net_bps",
                "maker_delta_weighted_bps",
                "maker_first_weighted_net_bps",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Aggregate", ""])
    lines.extend(
        markdown_table(
            aggregate_view,
            [
                "exit_profile_source",
                "days",
                "selected_maker_days",
                "maker_attempts",
                "maker_attempt_exposure",
                "pure_taker_weighted_net_bps",
                "maker_delta_weighted_bps",
                "maker_first_weighted_net_bps",
                "saved_spread_weighted_bps",
                "missed_fill_decay_weighted_bps",
                "adverse_selection_weighted_bps",
            ],
            max_rows=20,
        )
    )
    lines.extend(["", "## Event-Chain Summary", ""])
    lines.extend(
        markdown_table(
            event_view,
            [
                "exit_profile_source",
                "date",
                "gate_name",
                "maker_attempts",
                "exposure",
                "maker_fill_rate",
                "weighted_delta",
                "weighted_selection_adjusted_delta",
                "saved_spread",
                "missed_decay",
                "adverse_selection",
            ],
            max_rows=80,
        )
    )
    lines.extend(["", "## Promoted Candidate Diagnostics", ""])
    lines.extend(
        markdown_table(
            promoted,
            [
                "exit_profile_source",
                "test_date",
                "ttl_sec",
                "gate_name",
                "train_n",
                "train_exposure",
                "train_fill_rate",
                "train_weighted_mean_selection_adjusted_bps",
                "test_n",
                "maker_attempts",
                "maker_delta_weighted_bps",
                "maker_selection_adjusted_delta_weighted_bps",
            ],
            max_rows=100,
        )
    )
    lines.extend(
        [
            "",
            "## Readout",
            "",
            "The output should be read as a no-leakage gate test, not as optimized strategy evidence. For every test date, promotion uses only panel rows from strictly earlier dates; current-date fill, decay, selection, and PnL columns are evaluation labels only. A positive selected delta is still only a candidate until a stricter fill proxy and mechanism decomposition confirm that the gain comes from passive execution rather than delayed taker fallback. A negative selected delta is a fast no-go for this simple maker-first family.",
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
    if out_dir.exists() and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    panel = pq.read_table(panel_path).to_pandas()
    if not bool(panel["runtime_safe"].all()):
        raise ValueError("maker opportunity panel contains non-runtime-safe rows")
    needed = set(RUNTIME_FEATURES) | LABEL_COLUMNS | {
        "date",
        "exit_profile_source",
        "ttl_sec",
        "shadow_position_id",
        "actual_exposure",
        "immediate_taker_net_bps",
        "spread_saving_bps",
    }
    missing = sorted(needed - set(panel.columns))
    if missing:
        raise ValueError(f"panel missing columns: {missing}")
    candidate_rows, selected_rows = build_candidate_rows(panel, args)
    aggregate_rows = aggregate_selected(selected_rows)
    event_rows = build_event_rows(panel, selected_rows)
    config = {
        "schema_id": "ccusdt_maker_first_exit_policy_config_v1",
        "fill_model": "queue_trade_proxy_v1",
        "gate_specs": [
            {
                "name": gate.name,
                "description": gate.description,
                "quantiles": gate.quantiles,
                "cell": gate.cell,
            }
            for gate in GATES
        ],
        "margin_bps": args.margin_bps,
        "eval_from_date": args.eval_from_date,
        "eval_to_date": args.eval_to_date,
        "min_train_n": args.min_train_n,
        "min_train_exposure": args.min_train_exposure,
        "min_prior_days": args.min_prior_days,
        "min_positive_day_frac": args.min_positive_day_frac,
    }
    data_manifest = {
        "schema_id": "ccusdt_maker_first_exit_policy_data_manifest_v1",
        "panel_path": str(panel_path),
        "panel_sha256": file_sha256(panel_path),
        "panel_rows": int(len(panel)),
        "runtime_columns": sorted(RUNTIME_FEATURES),
        "diagnostic_label_columns": sorted(LABEL_COLUMNS),
        "boundary": (
            "policy gates use current runtime-safe features and prior-date label estimates; "
            "current-date labels are used only for evaluation"
        ),
    }
    summary = {
        "schema_id": "ccusdt_maker_first_exit_policy_summary_v1",
        "ok": True,
        "panel_path": str(panel_path),
        "fill_model": "queue_trade_proxy_v1",
        "margin_bps": args.margin_bps,
        "eval_from_date": args.eval_from_date,
        "eval_to_date": args.eval_to_date,
        "min_train_n": args.min_train_n,
        "min_train_exposure": args.min_train_exposure,
        "min_prior_days": args.min_prior_days,
        "min_positive_day_frac": args.min_positive_day_frac,
        "candidate_rows": int(len(candidate_rows)),
        "promoted_candidate_rows": int(candidate_rows["promoted"].astype(bool).sum()),
        "selected_rows": int(len(selected_rows)),
        "profile_aggregates": aggregate_rows.to_dict(orient="records"),
        "config_hash": stable_hash(config),
        "data_manifest_hash": stable_hash(data_manifest),
        "elapsed_wall_ms": int((time.perf_counter() - start) * 1000),
        "outputs": {
            "config_json": str(out_dir / "config.json"),
            "data_manifest_json": str(out_dir / "data_manifest.json"),
            "summary_json": str(out_dir / "summary.json"),
            "candidate_daily_csv": str(out_dir / "maker_first_exit_candidate_daily.csv"),
            "candidate_daily_parquet": str(out_dir / "maker_first_exit_candidate_daily.parquet"),
            "selected_daily_csv": str(out_dir / "maker_first_exit_selected_daily.csv"),
            "aggregate_csv": str(out_dir / "maker_first_exit_aggregate.csv"),
            "events_csv": str(out_dir / "maker_first_exit_events.csv"),
            "events_parquet": str(out_dir / "maker_first_exit_events.parquet"),
            "report_md": str(report_path),
        },
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (out_dir / "data_manifest.json").write_text(json.dumps(data_manifest, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(out_dir / "maker_first_exit_candidate_daily.csv", candidate_rows)
    write_parquet(out_dir / "maker_first_exit_candidate_daily.parquet", candidate_rows)
    write_csv(out_dir / "maker_first_exit_selected_daily.csv", selected_rows)
    write_csv(out_dir / "maker_first_exit_aggregate.csv", aggregate_rows)
    write_csv(out_dir / "maker_first_exit_events.csv", event_rows)
    write_parquet(out_dir / "maker_first_exit_events.parquet", event_rows)
    write_report(report_path, summary, candidate_rows, selected_rows, aggregate_rows, event_rows)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
