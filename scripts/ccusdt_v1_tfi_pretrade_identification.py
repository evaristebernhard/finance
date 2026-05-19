#!/usr/bin/env python
"""Strict pre-trade identification tests for the CCUSDT TFI family.

The key rule is prequential: for each entry, detectors can use only current
entry-time fields and previously closed entries. The current entry's future
gross/net label is used only for evaluation.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import ccusdt_v1_tfi_momentum_conversion_math as conv


RUN_TAG = "20260518_ccusdt_v1_tfi_pretrade_identification_v1"
GUARDRAIL = "research_only_strict_pretrade_identification_no_execution_recommendation_no_alpha_claim"
COST_MODE = "stored_net"
WINDOWS = [5, 10, 20, 30, 50, 100]
PI_BREAK_EVEN = 0.1998
PI_2BPS = 0.6334


ROOT = Path(__file__).resolve().parents[1]
DATE_DIR = ROOT / "date"
DOC_DIR = ROOT / "docs" / "markets" / "ccusdt"


def out_scored_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_pretrade_scored_entries_{RUN_TAG}.csv"


def out_gate_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_pretrade_gate_scorecard_{RUN_TAG}.csv"


def out_static_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_pretrade_static_feature_scorecard_{RUN_TAG}.csv"


def out_summary_json() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_pretrade_identification_summary_{RUN_TAG}.json"


def out_report_md() -> Path:
    return DOC_DIR / f"v1-tfi-pretrade-identification-{RUN_TAG}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument(
        "--cost-mode",
        choices=["stored_net", "zero_fee"],
        default=COST_MODE,
        help="stored_net uses fixed_net_maker_bps; zero_fee sets fixed_net_maker_bps := fixed_gross_bps and cost := 0.",
    )
    return parser.parse_args()


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def finite(values: pd.Series | np.ndarray) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return arr[np.isfinite(arr)]


def mean(values: pd.Series | np.ndarray) -> float:
    arr = finite(values)
    return float(arr.mean()) if len(arr) else np.nan


def q(values: pd.Series | np.ndarray, quantile: float) -> float:
    arr = finite(values)
    return float(np.quantile(arr, quantile)) if len(arr) else np.nan


def fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    cols = [col for col in columns if col in df.columns]
    view = df.loc[:, cols].head(max_rows).copy()
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    ok = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not ok.any():
        return np.nan
    v = values[ok]
    w = weights[ok]
    order = np.argsort(v)
    v = v[order]
    w = w[order]
    cdf = np.cumsum(w) / np.sum(w)
    return float(v[np.searchsorted(cdf, quantile, side="left").clip(0, len(v) - 1)])


def load_data(cost_mode: str = COST_MODE) -> tuple[pd.DataFrame, list[str], dict[str, float], dict[str, float]]:
    eligible, base_weight_map = conv.load_weights()
    all_rows = conv.load_all_memberships(eligible).copy()
    all_rows["source_fixed_net_maker_bps"] = pd.to_numeric(all_rows["fixed_net_maker_bps"], errors="coerce")
    all_rows["source_fixed_cost_maker_bps"] = pd.to_numeric(all_rows["fixed_cost_maker_bps"], errors="coerce")
    all_rows["cost_mode"] = cost_mode
    if cost_mode == "zero_fee":
        all_rows["fixed_net_maker_bps"] = pd.to_numeric(all_rows["fixed_gross_bps"], errors="coerce")
        all_rows["fixed_cost_maker_bps"] = 0.0
    all_rows["entry_ts"] = pd.to_numeric(all_rows["entry_local_timestamp"], errors="coerce")
    # The fixed-path diagnostic uses a 60s timeout. Require prior labels to be
    # closed before they can influence the next score.
    all_rows["label_available_ts"] = all_rows["entry_ts"] + 60_000_000.0
    all_rows["net"] = pd.to_numeric(all_rows["fixed_net_maker_bps"], errors="coerce")
    all_rows["gross"] = pd.to_numeric(all_rows["fixed_gross_bps"], errors="coerce")
    all_rows["cost"] = pd.to_numeric(all_rows["fixed_cost_maker_bps"], errors="coerce")
    all_rows["base_weight"] = all_rows["membership_set"].astype(str).map(base_weight_map).fillna(0.0).astype(float)
    overlay_threshold = locked_overlay_threshold(eligible)
    all_rows["overlay_boost"] = 0.0
    if np.isfinite(overlay_threshold):
        frames = pd.to_numeric(all_rows["frames_since_mid_change"], errors="coerce")
        all_rows.loc[all_rows["base_weight"].gt(0.0) & frames.ge(overlay_threshold), "overlay_boost"] = 0.5
    all_rows["weight"] = all_rows["base_weight"] + all_rows["overlay_boost"]
    all_rows["weighted_net"] = all_rows["weight"] * all_rows["net"]
    all_rows["is_oos"] = all_rows["segment"].isin(["OOS_2026_05_16", "OOS_2026_05_17"])
    all_rows = all_rows.sort_values(["entry_ts", "segment", "entry_row"]).reset_index(drop=True)
    all_rows["row_id"] = np.arange(len(all_rows), dtype="int64")

    seg = conv.attach_gross_mixture(conv.build_segment_table(all_rows, base_weight_map))
    refs = {
        "fold1_net_mean": float(seg.loc[seg["segment"].eq("Fold1"), "net_mean_bps"].iloc[0]),
        "fold3_net_mean": float(seg.loc[seg["segment"].eq("Fold3"), "net_mean_bps"].iloc[0]),
        "fold1_gross_mean": float(seg.loc[seg["segment"].eq("Fold1"), "gross_mean_bps"].iloc[0]),
        "fold3_gross_mean": float(seg.loc[seg["segment"].eq("Fold3"), "gross_mean_bps"].iloc[0]),
        "overlay_threshold_frames_since_mid_change": overlay_threshold,
    }
    return all_rows, eligible, base_weight_map, refs


def locked_overlay_threshold(eligible: list[str]) -> float:
    entries = pd.read_csv(conv.HIST_ENTRIES, usecols=conv.KEY_COLS + ["frames_since_mid_change"])
    membership = pd.read_csv(conv.HIST_MEMBERSHIP, usecols=conv.KEY_COLS + ["membership_set"])
    work = membership[
        membership["fold"].eq("expanding_fold3") & membership["membership_set"].astype(str).isin(eligible)
    ].merge(entries, on=conv.KEY_COLS, how="left")
    vals = finite(work["frames_since_mid_change"])
    return float(np.quantile(vals, 0.90)) if len(vals) else np.nan


def summarize_window(prev: pd.DataFrame, n: int, refs: dict[str, float], prefix: str) -> dict[str, float]:
    window = prev.tail(n)
    if window.empty:
        return {
            f"{prefix}_count": 0.0,
            f"{prefix}_mean_net": np.nan,
            f"{prefix}_gross_cost_ratio": np.nan,
            f"{prefix}_gt2_rate": np.nan,
            f"{prefix}_pos_abs_ratio": np.nan,
            f"{prefix}_pi_net": np.nan,
        }
    net = pd.to_numeric(window["net"], errors="coerce").to_numpy(dtype="float64")
    gross = pd.to_numeric(window["gross"], errors="coerce").to_numpy(dtype="float64")
    cost = pd.to_numeric(window["cost"], errors="coerce").to_numpy(dtype="float64")
    ok_net = net[np.isfinite(net)]
    pos = float(np.sum(ok_net[ok_net > 0])) if len(ok_net) else np.nan
    neg = float(np.sum(ok_net[ok_net < 0])) if len(ok_net) else np.nan
    net_mean = float(np.mean(ok_net)) if len(ok_net) else np.nan
    den = refs["fold3_net_mean"] - refs["fold1_net_mean"]
    return {
        f"{prefix}_count": float(len(window)),
        f"{prefix}_mean_net": net_mean,
        f"{prefix}_gross_cost_ratio": safe_div(float(np.nanmean(gross)), float(np.nanmean(cost))),
        f"{prefix}_gt2_rate": float(np.mean(ok_net > 2.0)) if len(ok_net) else np.nan,
        f"{prefix}_pos_abs_ratio": safe_div(pos, abs(neg)),
        f"{prefix}_pi_net": safe_div(net_mean - refs["fold1_net_mean"], den),
    }


def score_prequential(rows: pd.DataFrame, refs: dict[str, float]) -> pd.DataFrame:
    scored_rows: list[dict[str, Any]] = []
    closed = rows.sort_values("label_available_ts").reset_index(drop=True)
    close_ptr = 0
    available_idx: list[int] = []
    timeline = rows.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)
    for _, current in timeline.iterrows():
        entry_ts = float(current["entry_ts"])
        while close_ptr < len(closed) and float(closed.loc[close_ptr, "label_available_ts"]) < entry_ts:
            available_idx.append(int(closed.loc[close_ptr, "row_id"]))
            close_ptr += 1
        prev = rows[rows["row_id"].isin(available_idx)].sort_values("label_available_ts")
        item = current.to_dict()
        for n in WINDOWS:
            item.update(summarize_window(prev, n, refs, f"roll{n}"))
        scored_rows.append(item)
    scored = pd.DataFrame(scored_rows)
    for n in WINDOWS:
        scored[f"gate_pi2_n{n}"] = scored[f"roll{n}_pi_net"].ge(PI_2BPS)
        scored[f"gate_pibe_n{n}"] = scored[f"roll{n}_pi_net"].ge(PI_BREAK_EVEN)
        scored[f"gate_rho_n{n}"] = scored[f"roll{n}_gross_cost_ratio"].ge(1.0)
        scored[f"gate_r_n{n}"] = scored[f"roll{n}_pos_abs_ratio"].ge(1.0)
        scored[f"gate_hot_n{n}"] = scored[f"roll{n}_mean_net"].gt(0.0) & scored[f"roll{n}_gt2_rate"].ge(0.40)
        scored[f"gate_combo_n{n}"] = (
            scored[f"roll{n}_pi_net"].ge(PI_BREAK_EVEN)
            & scored[f"roll{n}_gross_cost_ratio"].ge(1.0)
            & scored[f"roll{n}_pos_abs_ratio"].ge(1.0)
        )
    return scored


def add_entry_time_composite_gates(scored: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    out = scored.copy()
    hist = out[out["segment"].isin(["Fold1", "Fold2", "Fold3"])].copy()
    frame_q90 = q(hist["frames_since_mid_change"], 0.90)
    frame_q80 = q(hist["frames_since_mid_change"], 0.80)
    spread_q25 = q(hist["entry_spread_bps"], 0.25)
    out["gate_frames_q90"] = pd.to_numeric(out["frames_since_mid_change"], errors="coerce").ge(frame_q90)
    out["gate_frames_q80"] = pd.to_numeric(out["frames_since_mid_change"], errors="coerce").ge(frame_q80)
    out["gate_spread_low_q25"] = pd.to_numeric(out["entry_spread_bps"], errors="coerce").le(spread_q25)
    out["gate_r5_and_frames_q90"] = out["gate_r_n5"].fillna(False).astype(bool) & out["gate_frames_q90"]
    out["gate_r5_or_frames_q90"] = out["gate_r_n5"].fillna(False).astype(bool) | out["gate_frames_q90"]
    out["gate_r5_and_spread_low_q25"] = out["gate_r_n5"].fillna(False).astype(bool) & out["gate_spread_low_q25"]
    return out, {
        "frames_since_mid_change_q90": frame_q90,
        "frames_since_mid_change_q80": frame_q80,
        "entry_spread_bps_q25": spread_q25,
    }


def eval_subset(group: pd.DataFrame, mask: pd.Series, label: str, gate: str, baseline: dict[str, float]) -> dict[str, Any]:
    active = group[mask & group["weight"].gt(0.0) & np.isfinite(group["net"])].copy()
    net = pd.to_numeric(active["net"], errors="coerce").to_numpy(dtype="float64")
    weights = pd.to_numeric(active["weight"], errors="coerce").to_numpy(dtype="float64")
    weighted_net = net * weights
    exposure = float(np.sum(weights)) if len(weights) else 0.0
    total = float(np.sum(weighted_net)) if len(weighted_net) else 0.0
    gt2 = safe_div(float(np.sum(weights[net > 2.0])), exposure) if exposure else np.nan
    cost_hit = safe_div(float(np.sum(weights[net <= 0.0])), exposure) if exposure else np.nan
    pos = float(np.sum(weighted_net[weighted_net > 0.0])) if len(weighted_net) else np.nan
    neg = float(np.sum(weighted_net[weighted_net < 0.0])) if len(weighted_net) else np.nan
    return {
        "scope": label,
        "gate": gate,
        "entries": int(len(active)),
        "select_rate": safe_div(float(len(active)), float(len(group))),
        "exposure_units": exposure,
        "weighted_total_net_bps": total,
        "weighted_mean_net_bps": safe_div(total, exposure),
        "weighted_median_net_bps": weighted_quantile(net, weights, 0.50),
        "weighted_gt2_rate": gt2,
        "cost_hit_rate": cost_hit,
        "positive_net_bps": pos,
        "negative_net_bps": neg,
        "pos_over_abs_neg": safe_div(pos, abs(neg)),
        "mean_lift_vs_baseline": safe_div(safe_div(total, exposure), baseline["weighted_mean_net_bps"]),
        "gt2_lift_vs_baseline": safe_div(gt2, baseline["weighted_gt2_rate"]),
    }


def baseline_for(group: pd.DataFrame, label: str) -> dict[str, Any]:
    base = eval_subset(group, pd.Series(True, index=group.index), label, "baseline_all", {"weighted_mean_net_bps": np.nan, "weighted_gt2_rate": np.nan})
    base["mean_lift_vs_baseline"] = 1.0
    base["gt2_lift_vs_baseline"] = 1.0
    return base


def gate_scorecard(scored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = [
        ("OOS_2026_05_16", scored["segment"].eq("OOS_2026_05_16")),
        ("OOS_2026_05_17", scored["segment"].eq("OOS_2026_05_17")),
        ("OOS_combined", scored["segment"].isin(["OOS_2026_05_16", "OOS_2026_05_17"])),
    ]
    gate_cols = [
        col
        for col in scored.columns
        if col.startswith("gate_")
    ]
    for label, scope_mask in scopes:
        group = scored[scope_mask].copy()
        if group.empty:
            continue
        baseline = baseline_for(group, label)
        rows.append(baseline)
        for gate in gate_cols:
            rows.append(eval_subset(group, group[gate].fillna(False).astype(bool), label, gate, baseline))
    out = pd.DataFrame(rows)
    return out.sort_values(["scope", "weighted_mean_net_bps", "entries"], ascending=[True, False, False])


def static_feature_scorecard(scored: pd.DataFrame) -> pd.DataFrame:
    hist = scored[scored["segment"].isin(["Fold1", "Fold2", "Fold3"])].copy()
    oos_scopes = [
        ("OOS_2026_05_16", scored["segment"].eq("OOS_2026_05_16")),
        ("OOS_2026_05_17", scored["segment"].eq("OOS_2026_05_17")),
        ("OOS_combined", scored["segment"].isin(["OOS_2026_05_16", "OOS_2026_05_17"])),
    ]
    specs = [
        ("frames_since_mid_change", "high", 0.90),
        ("frames_since_mid_change", "high", 0.80),
        ("entry_spread_bps", "low", 0.50),
        ("entry_spread_bps", "low", 0.25),
        ("trade_window_count", "low", 0.50),
        ("trade_window_count", "high", 0.75),
        ("past_event_25_bps", "abs_low", 0.50),
    ]
    rows: list[dict[str, Any]] = []
    for feature, direction, quant in specs:
        if feature not in hist:
            continue
        values = pd.to_numeric(hist[feature], errors="coerce")
        if direction == "abs_low":
            threshold = q(values.abs(), quant)
        elif direction == "high":
            threshold = q(values, quant)
        else:
            threshold = q(values, quant)
        for label, scope_mask in oos_scopes:
            group = scored[scope_mask].copy()
            baseline = baseline_for(group, label)
            vals = pd.to_numeric(group[feature], errors="coerce")
            if direction == "high":
                mask = vals.ge(threshold)
            elif direction == "low":
                mask = vals.le(threshold)
            else:
                mask = vals.abs().le(threshold)
            row = eval_subset(group, mask.fillna(False), label, f"static_{feature}_{direction}_q{quant:g}", baseline)
            row["feature"] = feature
            row["direction"] = direction
            row["hist_threshold"] = threshold
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["scope", "weighted_mean_net_bps", "entries"], ascending=[True, False, False])


def write_report(scored: pd.DataFrame, gate_scores: pd.DataFrame, static_scores: pd.DataFrame, summary: dict[str, Any]) -> None:
    short_top = gate_scores[
        gate_scores["scope"].eq("OOS_combined")
        & gate_scores["gate"].ne("baseline_all")
        & gate_scores["entries"].ge(20)
    ].sort_values(["weighted_mean_net_bps", "weighted_gt2_rate"], ascending=False)
    day_top = gate_scores[
        gate_scores["scope"].isin(["OOS_2026_05_16", "OOS_2026_05_17"])
        & gate_scores["gate"].ne("baseline_all")
        & gate_scores["entries"].ge(10)
    ].sort_values(["scope", "weighted_mean_net_bps"], ascending=[True, False])
    static_top = static_scores[
        static_scores["scope"].eq("OOS_combined") & static_scores["entries"].ge(20)
    ].sort_values("weighted_mean_net_bps", ascending=False)

    lines = [
        "# CCUSDT TFI 前验识别：短窗口在线检测",
        "",
        f"Status: `{RUN_TAG}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        f"Cost mode: `{summary['cost_mode']}`.",
        "",
        "If cost mode is `zero_fee`, the upstream path label is rebuilt before scoring as `net := gross` and `cost := 0`; all rolling detectors and gates in this report are then recomputed from those zero-fee prior labels.",
        "",
        "这份报告严格区分后验解释和前验识别。每个 entry 的 score 只允许使用：entry 前可见字段，以及在该 entry 时间之前已经过 60s timeout、可闭合的历史 entry 标签。当前 entry 的未来 `gross/net` 只在评估阶段使用。",
        "",
        f"执行权重口径使用已锁定的 `{conv.VARIANT}`：base bucket weights 加上 entry 前可见的 `frames_since_mid_change` 高 10% overlay，历史 Fold3 阈值为 `{fmt(summary['overlay_threshold_frames_since_mid_change'])}`。",
        "",
        "## 方法",
        "",
        "对每个新 entry，取此前已经闭合的 last-N entries，N 为 `5/10/20/30/50/100`，计算：",
        "",
        "```text",
        "roll_mean_net_N",
        "roll_gross_cost_ratio_N = mean(X) / mean(C)",
        "roll_gt2_rate_N = P(Y > 2bps)",
        "roll_pos_abs_ratio_N = sum(Y+) / abs(sum(Y-))",
        "roll_pi_N = (roll_mean_net_N - Fold1_mean) / (Fold3_mean - Fold1_mean)",
        "```",
        "",
        "这不是用当天最终结果反推状态，而是在每个 entry 前只看已闭合样本。它对应实盘里的一个很短 regime detector。",
        "",
        "## OOS Baseline",
        "",
        *markdown_table(
            gate_scores[gate_scores["gate"].eq("baseline_all")],
            [
                "scope",
                "entries",
                "exposure_units",
                "weighted_total_net_bps",
                "weighted_mean_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
                "pos_over_abs_neg",
            ],
        ),
        "",
        "## 短窗口 Detector：OOS Combined Top",
        "",
        *markdown_table(
            short_top,
            [
                "gate",
                "entries",
                "select_rate",
                "exposure_units",
                "weighted_total_net_bps",
                "weighted_mean_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
                "pos_over_abs_neg",
                "gt2_lift_vs_baseline",
            ],
            max_rows=20,
        ),
        "",
        "## 短窗口 + 当前队列状态交叉",
        "",
        *markdown_table(
            gate_scores[
                gate_scores["scope"].isin(["OOS_2026_05_16", "OOS_2026_05_17", "OOS_combined"])
                & gate_scores["gate"].isin(
                    [
                        "gate_r5_and_frames_q90",
                        "gate_r5_or_frames_q90",
                        "gate_frames_q90",
                        "gate_frames_q80",
                        "gate_spread_low_q25",
                    ]
                )
            ].sort_values(["scope", "weighted_mean_net_bps"], ascending=[True, False]),
            [
                "scope",
                "gate",
                "entries",
                "select_rate",
                "exposure_units",
                "weighted_total_net_bps",
                "weighted_mean_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
            ],
            max_rows=30,
        ),
        "",
        "## 分日 Top",
        "",
        *markdown_table(
            day_top,
            [
                "scope",
                "gate",
                "entries",
                "select_rate",
                "weighted_total_net_bps",
                "weighted_mean_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
            ],
            max_rows=30,
        ),
        "",
        "## Entry-Time Static Feature Gates",
        "",
        "这些 gate 只用当前 entry 前字段，阈值来自历史样本分位数，不用 OOS 结果调参。",
        "",
        *markdown_table(
            static_top,
            [
                "gate",
                "entries",
                "select_rate",
                "hist_threshold",
                "weighted_total_net_bps",
                "weighted_mean_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
            ],
            max_rows=20,
        ),
        "",
        "## 结论",
        "",
        summary["interpretation"],
        "",
        "## Outputs",
        "",
        f"- `{out_scored_csv()}`",
        f"- `{out_gate_csv()}`",
        f"- `{out_static_csv()}`",
        f"- `{out_summary_json()}`",
        "",
    ]
    out_report_md().write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    global RUN_TAG, COST_MODE
    RUN_TAG = args.run_tag
    COST_MODE = args.cost_mode

    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    rows, eligible, base_weight_map, refs = load_data(COST_MODE)
    scored = score_prequential(rows, refs)
    scored, entry_gate_thresholds = add_entry_time_composite_gates(scored)
    gate_scores = gate_scorecard(scored)
    static_scores = static_feature_scorecard(scored)

    combined_baseline = gate_scores[
        gate_scores["scope"].eq("OOS_combined") & gate_scores["gate"].eq("baseline_all")
    ].iloc[0]
    viable = gate_scores[
        gate_scores["scope"].eq("OOS_combined")
        & gate_scores["gate"].ne("baseline_all")
        & gate_scores["entries"].ge(20)
        & gate_scores["weighted_mean_net_bps"].gt(combined_baseline["weighted_mean_net_bps"])
        & gate_scores["weighted_gt2_rate"].gt(combined_baseline["weighted_gt2_rate"])
    ].copy()
    top = viable.sort_values(["weighted_mean_net_bps", "weighted_gt2_rate"], ascending=False).head(1)
    broad = gate_scores[
        gate_scores["scope"].eq("OOS_combined") & gate_scores["gate"].eq("gate_r_n5")
    ].head(1)
    if top.empty:
        interpretation = (
            "短窗口前验 detector 目前没有稳定超过 baseline 的证据。含义不是结构不可用，而是 entry 前过滤能力不足；更合理的是保留互斥 bucket，"
            "用低权重/状态 sizing 忍受一部分 cost-hit。"
        )
        top_gate = None
    else:
        row = top.iloc[0]
        top_gate = row["gate"]
        broad_text = ""
        if not broad.empty:
            brow = broad.iloc[0]
            broad_text = (
                f" 覆盖更大的纯短窗口 detector 是 `{brow['gate']}`，选择 {int(brow['entries'])} entries，"
                f"weighted mean `{fmt(brow['weighted_mean_net_bps'])}` bps；这更适合做状态 sizing。"
            )
        interpretation = (
            f"短窗口前验识别有初步信号：最高精度 gate `{top_gate}` 在 OOS combined 选择 {int(row['entries'])} entries，"
            f"weighted mean `{fmt(row['weighted_mean_net_bps'])}` bps，gt2 rate `{fmt(row['weighted_gt2_rate'])}`，"
            f"相对 baseline gt2 lift `{fmt(row['gt2_lift_vs_baseline'])}`。{broad_text}"
            "这说明 regime 识别可能确实很短，但高精度 gate 样本很少；它应作为 sizing/quality layer，不应替代全部互斥 bucket。"
        )

    summary = {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "cost_mode": COST_MODE,
        "eligible_buckets": eligible,
        "windows": WINDOWS,
        "prequential_rule": "only current pre-entry fields plus entries whose 60s fixed label was already available",
        "execution_weight_rule": (
            "weak_overlay_rank12 base weights plus +0.5 weight when frames_since_mid_change is above Fold3 historical p90"
        ),
        "overlay_threshold_frames_since_mid_change": refs["overlay_threshold_frames_since_mid_change"],
        "entry_gate_thresholds": entry_gate_thresholds,
        "baseline_oos_combined": combined_baseline.to_dict(),
        "top_viable_gate": top_gate,
        "top_viable_gate_row": top.iloc[0].to_dict() if not top.empty else None,
        "top_broad_gate_row": broad.iloc[0].to_dict() if not broad.empty else None,
        "interpretation": interpretation,
        "outputs": {
            "scored_csv": str(out_scored_csv()),
            "gate_scorecard_csv": str(out_gate_csv()),
            "static_feature_scorecard_csv": str(out_static_csv()),
            "summary_json": str(out_summary_json()),
            "report_md": str(out_report_md()),
        },
    }

    scored.to_csv(out_scored_csv(), index=False)
    gate_scores.to_csv(out_gate_csv(), index=False)
    static_scores.to_csv(out_static_csv(), index=False)
    out_summary_json().write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(scored, gate_scores, static_scores, summary)
    print(
        "[ccusdt_tfi_pretrade_identification] "
        f"scored={len(scored)} gate_rows={len(gate_scores)} static_rows={len(static_scores)} "
        f"top_gate={top_gate} report={out_report_md()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
