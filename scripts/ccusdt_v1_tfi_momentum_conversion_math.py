#!/usr/bin/env python
"""First-principles momentum-conversion diagnostics for CCUSDT TFI buckets."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_momentum_conversion_math_v1"
VARIANT = "weak_overlay_rank12"
GUARDRAIL = "research_only_momentum_conversion_math_no_execution_recommendation_no_alpha_claim"

KEY_COLS = ["fold", "date", "entry_row"]
TRIGGERS = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]
PATH_COLS = [
    "entry_event_index",
    "entry_local_timestamp",
    "direction",
    "feature_value",
    "entry_spread_bps",
    "trade_window_count",
    "frames_since_mid_change",
    "past_event_25_bps",
    "fixed_gross_bps",
    "fixed_cost_maker_bps",
    "fixed_net_maker_bps",
    "mfe_bps",
    "mae_bps",
    "has_mid_transition",
    "has_quote_transition",
    "mid_transition_count",
    "quote_transition_count",
    "first_mid_transition_hold_sec",
    "first_quote_transition_hold_sec",
    "first_mid_transition_gross_bps",
    "first_quote_transition_gross_bps",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
DATE_DIR = ROOT / "date"
DOC_DIR = ROOT / "docs" / "markets" / "ccusdt"
HIST_ENTRIES = DATE_DIR / "ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv"
HIST_MEMBERSHIP = DATE_DIR / "ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv"
HIST_WEIGHTS = DATE_DIR / "ccusdt_v1_tfi_mutual_strategy_weights_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv"
HIST_SCORECARD = DATE_DIR / "ccusdt_v1_tfi_mutual_strategy_scorecard_20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1.csv"
OOS_ENTRY_FILES = {
    "OOS_2026_05_16": DATE_DIR
    / "ccusdt_v1_tfi_oos_decay_entries_20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1.csv",
    "OOS_2026_05_17": DATE_DIR
    / "ccusdt_v1_tfi_oos_decay_entries_20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1.csv",
}
OOS_UNION_FILES = {
    "OOS_2026_05_16": DATE_DIR
    / "ccusdt_v1_tfi_oos_decay_union_20260518_ccusdt_v1_tfi_oos_decay_day20260516_v1.csv",
    "OOS_2026_05_17": DATE_DIR
    / "ccusdt_v1_tfi_oos_decay_union_20260518_ccusdt_v1_tfi_oos_decay_day20260517_v1.csv",
}


def out_segment_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_momentum_conversion_segments_{RUN_TAG}.csv"


def out_bucket_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_momentum_conversion_buckets_{RUN_TAG}.csv"


def out_weighted_csv() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_momentum_conversion_weighted_regime_{RUN_TAG}.csv"


def out_summary_json() -> Path:
    return DATE_DIR / f"ccusdt_v1_tfi_momentum_conversion_summary_{RUN_TAG}.json"


def out_report_md() -> Path:
    return DOC_DIR / f"v1-tfi-momentum-conversion-first-principles-{RUN_TAG}.md"


def numeric(series: pd.Series | np.ndarray | list[Any]) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(series), errors="coerce").to_numpy(dtype="float64")
    return arr


def finite(series: pd.Series | np.ndarray | list[Any]) -> np.ndarray:
    arr = numeric(series)
    return arr[np.isfinite(arr)]


def mean(series: pd.Series | np.ndarray | list[Any]) -> float:
    arr = finite(series)
    return float(arr.mean()) if len(arr) else np.nan


def quantile(series: pd.Series | np.ndarray | list[Any], q: float) -> float:
    arr = finite(series)
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def bool_rate(series: pd.Series) -> float:
    if series.empty:
        return np.nan
    if series.dtype == bool:
        return float(series.mean())
    lowered = series.astype(str).str.lower()
    valid = lowered[lowered.isin(["true", "false", "1", "0"])]
    if valid.empty:
        return np.nan
    return float(valid.isin(["true", "1"]).mean())


def fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30, digits: int = 4) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    cols = [col for col in columns if col in df.columns]
    view = df.loc[:, cols].head(max_rows).copy()
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(fmt(value, digits))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def load_weights() -> tuple[list[str], dict[str, float]]:
    weights = pd.read_csv(HIST_WEIGHTS)
    weights = weights[weights["variant"].eq(VARIANT)].copy()
    weights["base_weight"] = pd.to_numeric(weights["base_weight"], errors="coerce").fillna(0.0)
    eligible = weights["membership_set"].astype(str).tolist()
    return eligible, dict(zip(weights["membership_set"].astype(str), weights["base_weight"].astype(float)))


def load_path_rows(path: Path) -> pd.DataFrame:
    keep = set(KEY_COLS + PATH_COLS + ["trigger_class"])
    df = pd.read_csv(path, usecols=lambda col: col in keep)
    if "trigger_class" in df:
        df = df[df["trigger_class"].isin(TRIGGERS)].copy()
    sort_cols = [col for col in KEY_COLS + ["trigger_class"] if col in df.columns]
    df = df.sort_values(sort_cols).drop_duplicates(KEY_COLS, keep="first")
    for col in PATH_COLS:
        if col not in df:
            df[col] = np.nan
    return df[KEY_COLS + PATH_COLS].copy()


def merge_path_columns(membership: pd.DataFrame, path_rows: pd.DataFrame) -> pd.DataFrame:
    merged = membership.merge(path_rows, on=KEY_COLS, how="left", suffixes=("", "_path"))
    for col in PATH_COLS:
        path_col = f"{col}_path"
        if path_col not in merged:
            continue
        if col in membership.columns:
            merged[col] = merged[col].combine_first(merged[path_col])
        else:
            merged[col] = merged[path_col]
        merged = merged.drop(columns=[path_col])
    return merged


def membership_set_from_flags(row: pd.Series) -> str:
    parts = [trigger for trigger in TRIGGERS if bool(row.get(trigger, False))]
    return "+".join(parts) if parts else "none"


def build_oos_membership(path: Path, segment: str) -> pd.DataFrame:
    entries = pd.read_csv(path)
    entries = entries[entries["trigger_class"].isin(TRIGGERS)].copy()
    for col in PATH_COLS:
        if col not in entries:
            entries[col] = np.nan
    base = entries.sort_values(KEY_COLS + ["trigger_class"]).drop_duplicates(KEY_COLS, keep="first")
    base = base[KEY_COLS + PATH_COLS].copy()
    flags = (
        entries.assign(present=True)
        .pivot_table(index=KEY_COLS, columns="trigger_class", values="present", aggfunc="max", fill_value=False)
        .reset_index()
    )
    for trigger in TRIGGERS:
        if trigger not in flags:
            flags[trigger] = False
    out = base.merge(flags[KEY_COLS + TRIGGERS], on=KEY_COLS, how="left")
    for trigger in TRIGGERS:
        out[trigger] = out[trigger].fillna(False).astype(bool)
    out["membership_count"] = out[TRIGGERS].sum(axis=1).astype(int)
    out["membership_set"] = out.apply(membership_set_from_flags, axis=1)
    out["segment"] = segment
    return out


def load_historical_membership() -> pd.DataFrame:
    membership = pd.read_csv(HIST_MEMBERSHIP)
    path_rows = load_path_rows(HIST_ENTRIES)
    membership = merge_path_columns(membership, path_rows)
    fold_map = {
        "expanding_fold1": "Fold1",
        "expanding_fold2": "Fold2",
        "expanding_fold3": "Fold3",
    }
    membership["segment"] = membership["fold"].map(fold_map).fillna(membership["fold"])
    return membership


def standardize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in PATH_COLS + ["entry_row", "entry_event_index", "membership_count"]:
        if col in out and col not in ["has_mid_transition", "has_quote_transition"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def tail_stats(values: pd.Series) -> dict[str, float]:
    arr = finite(values)
    if not len(arr):
        return {
            "top10_net_bps": np.nan,
            "rest90_net_bps": np.nan,
            "left10_net_bps": np.nan,
            "top10_avg_net_bps": np.nan,
            "rest90_avg_net_bps": np.nan,
            "left10_avg_net_bps": np.nan,
            "top10_over_abs_rest90": np.nan,
            "top10_over_abs_left10": np.nan,
        }
    n_top = max(1, int(math.ceil(len(arr) * 0.10)))
    desc = np.sort(arr)[::-1]
    asc = np.sort(arr)
    top = desc[:n_top]
    rest = desc[n_top:]
    left = asc[:n_top]
    top_sum = float(np.sum(top))
    rest_sum = float(np.sum(rest)) if len(rest) else np.nan
    left_sum = float(np.sum(left))
    return {
        "top10_net_bps": top_sum,
        "rest90_net_bps": rest_sum,
        "left10_net_bps": left_sum,
        "top10_avg_net_bps": float(np.mean(top)),
        "rest90_avg_net_bps": float(np.mean(rest)) if len(rest) else np.nan,
        "left10_avg_net_bps": float(np.mean(left)),
        "top10_over_abs_rest90": safe_div(top_sum, abs(rest_sum)) if np.isfinite(rest_sum) else np.nan,
        "top10_over_abs_left10": safe_div(top_sum, abs(left_sum)),
    }


def summarize(label: str, group: pd.DataFrame, base_weight_map: dict[str, float] | None = None) -> dict[str, Any]:
    gross = numeric(group["fixed_gross_bps"])
    cost = numeric(group["fixed_cost_maker_bps"])
    net = numeric(group["fixed_net_maker_bps"])
    mfe = numeric(group["mfe_bps"])
    mae = numeric(group["mae_bps"])
    first_mid = numeric(group["first_mid_transition_gross_bps"])
    first_quote = numeric(group["first_quote_transition_gross_bps"])

    finite_net = net[np.isfinite(net)]
    positive_net = float(np.sum(finite_net[finite_net > 0.0])) if len(finite_net) else np.nan
    negative_net = float(np.sum(finite_net[finite_net < 0.0])) if len(finite_net) else np.nan
    pos_values = finite_net[finite_net > 0.0]
    neg_values = finite_net[finite_net < 0.0]
    avg_pos = float(np.mean(pos_values)) if len(pos_values) else np.nan
    avg_neg_abs = float(np.mean(np.abs(neg_values))) if len(neg_values) else np.nan
    win_eff_mask = np.isfinite(gross) & np.isfinite(mfe) & (gross > 0.0) & (mfe > 0.0)
    adverse_mask = np.isfinite(mae) & np.isfinite(cost) & (cost > 0.0)
    post_first_mask = np.isfinite(gross) & np.isfinite(first_mid)

    row: dict[str, Any] = {
        "segment": label,
        "entries": int(len(group)),
        "gross_mean_bps": mean(gross),
        "gross_median_bps": quantile(gross, 0.50),
        "gross_p90_bps": quantile(gross, 0.90),
        "cost_mean_bps": mean(cost),
        "gross_cost_ratio": safe_div(mean(gross), mean(cost)),
        "net_mean_bps": mean(net),
        "net_median_bps": quantile(net, 0.50),
        "net_p10_bps": quantile(net, 0.10),
        "net_p90_bps": quantile(net, 0.90),
        "gt2_rate": float(np.mean(finite_net > 2.0)) if len(finite_net) else np.nan,
        "win_rate": float(np.mean(finite_net > 0.0)) if len(finite_net) else np.nan,
        "cost_hit_rate": float(np.mean(finite_net <= 0.0)) if len(finite_net) else np.nan,
        "total_net_bps": float(np.sum(finite_net)) if len(finite_net) else np.nan,
        "positive_net_bps": positive_net,
        "negative_net_bps": negative_net,
        "pos_over_abs_neg": safe_div(positive_net, abs(negative_net)),
        "avg_positive_net_bps": avg_pos,
        "avg_negative_abs_net_bps": avg_neg_abs,
        "breakeven_win_rate_by_magnitude": safe_div(avg_neg_abs, avg_pos + avg_neg_abs),
        "mfe_mean_bps": mean(mfe),
        "mae_mean_bps": mean(mae),
        "mid_transition_rate": bool_rate(group["has_mid_transition"]) if "has_mid_transition" in group else np.nan,
        "quote_transition_rate": bool_rate(group["has_quote_transition"]) if "has_quote_transition" in group else np.nan,
        "mid_transition_count_mean": mean(group.get("mid_transition_count", pd.Series(dtype=float))),
        "first_mid_hold_mean_sec": mean(group.get("first_mid_transition_hold_sec", pd.Series(dtype=float))),
        "first_mid_gross_mean_bps": mean(first_mid),
        "first_quote_gross_mean_bps": mean(first_quote),
        "post_first_mid_release_mean_bps": float(np.mean(gross[post_first_mask] - first_mid[post_first_mask]))
        if post_first_mask.any()
        else np.nan,
        "first_mid_capture_ratio": safe_div(mean(first_mid), mean(gross)),
        "winner_final_over_mfe_mean": float(np.mean(gross[win_eff_mask] / mfe[win_eff_mask]))
        if win_eff_mask.any()
        else np.nan,
        "adverse_over_cost_mean": float(np.mean(np.abs(mae[adverse_mask]) / cost[adverse_mask]))
        if adverse_mask.any()
        else np.nan,
    }
    row.update(tail_stats(group["fixed_net_maker_bps"]))
    if base_weight_map is not None:
        weights = group["membership_set"].astype(str).map(base_weight_map).fillna(0.0).to_numpy(dtype="float64")
        active = np.isfinite(net) & np.isfinite(weights) & (weights > 0)
        row["base_exposure_units"] = float(np.sum(weights[active])) if active.any() else np.nan
        row["base_weighted_net_bps"] = float(np.sum(weights[active] * net[active])) if active.any() else np.nan
        row["base_weighted_mean_net_bps"] = (
            safe_div(float(np.sum(weights[active] * net[active])), float(np.sum(weights[active]))) if active.any() else np.nan
        )
    return row


def load_all_memberships(eligible: list[str]) -> pd.DataFrame:
    frames = [load_historical_membership()]
    for segment, path in OOS_ENTRY_FILES.items():
        frames.append(build_oos_membership(path, segment))
    all_rows = standardize_numeric(pd.concat(frames, ignore_index=True, sort=False))
    return all_rows[all_rows["membership_set"].astype(str).isin(eligible)].copy()


def build_segment_table(all_rows: pd.DataFrame, base_weight_map: dict[str, float]) -> pd.DataFrame:
    rows = []
    order = ["Fold1", "Fold2", "Fold3", "OOS_2026_05_16", "OOS_2026_05_17"]
    for segment in order:
        group = all_rows[all_rows["segment"].eq(segment)].copy()
        if not group.empty:
            rows.append(summarize(segment, group, base_weight_map))
    return pd.DataFrame(rows)


def build_bucket_table(all_rows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    order = ["Fold1", "Fold2", "Fold3", "OOS_2026_05_16", "OOS_2026_05_17"]
    for segment in order:
        seg = all_rows[all_rows["segment"].eq(segment)].copy()
        for bucket, group in seg.groupby("membership_set", sort=True):
            row = summarize(segment, group)
            row["membership_set"] = bucket
            rows.append(row)
    return pd.DataFrame(rows)


def weighted_refs() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    score = pd.read_csv(HIST_SCORECARD)
    row = score[score["variant"].eq(VARIANT)].iloc[0].to_dict()
    fold_map = {
        "Fold1": "expanding_fold1",
        "Fold2": "expanding_fold2",
        "Fold3": "expanding_fold3",
    }
    for segment, fold in fold_map.items():
        rows.append(
            {
                "segment": segment,
                "source": "historical_strategy_scorecard",
                "weighted_mean_net_bps": row.get(f"weighted_mean_net_bps_{fold}", np.nan),
                "total_weighted_net_bps": row.get(f"total_weighted_net_bps_{fold}", np.nan),
                "weighted_gt2_rate": row.get(f"weighted_gt2_rate_{fold}", np.nan),
                "cost_hit_rate": row.get(f"cost_hit_rate_{fold}", np.nan),
                "weighted_cvar10_net_bps": row.get(f"weighted_cvar10_net_bps_{fold}", np.nan),
                "max_drawdown_bps_units": row.get(f"max_drawdown_bps_units_{fold}", np.nan),
            }
        )
    for segment, path in OOS_UNION_FILES.items():
        comp = pd.read_csv(path)
        wrow = comp[comp["scope"].astype(str).str.contains("weighted_locked", na=False)].iloc[0].to_dict()
        rows.append(
            {
                "segment": segment,
                "source": "locked_oos_decay_check",
                "weighted_mean_net_bps": wrow.get("weighted_mean_net_bps", np.nan),
                "total_weighted_net_bps": wrow.get("total_weighted_net_bps", np.nan),
                "weighted_gt2_rate": wrow.get("weighted_gt2_rate", np.nan),
                "cost_hit_rate": wrow.get("cost_hit_rate", np.nan),
                "positive_net_bps": wrow.get("positive_net_bps", np.nan),
                "negative_net_bps": wrow.get("negative_net_bps", np.nan),
                "top10_weighted_net_bps": wrow.get("top10_weighted_net_bps", np.nan),
                "left10_weighted_net_bps": wrow.get("left10_weighted_net_bps", np.nan),
                "weighted_p10_net_bps": wrow.get("weighted_p10_net_bps", np.nan),
                "weighted_p90_net_bps": wrow.get("weighted_p90_net_bps", np.nan),
            }
        )
    out = pd.DataFrame(rows)
    for col in out.columns:
        if col not in ["segment", "source"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    m_abs = float(out.loc[out["segment"].eq("Fold1"), "weighted_mean_net_bps"].iloc[0])
    m_rel = float(out.loc[out["segment"].eq("Fold3"), "weighted_mean_net_bps"].iloc[0])
    den = m_rel - m_abs
    out["release_state_pi_from_weighted_mean"] = (out["weighted_mean_net_bps"] - m_abs) / den
    out["release_state_pi_from_weighted_mean_clipped"] = out["release_state_pi_from_weighted_mean"].clip(0.0, 1.0)
    out["break_even_pi_for_mean_gt_0"] = safe_div(0.0 - m_abs, den)
    out["pi_for_mean_gt_2bps"] = safe_div(2.0 - m_abs, den)
    out["pos_over_abs_neg"] = out.apply(
        lambda r: safe_div(r.get("positive_net_bps", np.nan), abs(r.get("negative_net_bps", np.nan))), axis=1
    )
    out["top10_over_abs_left10"] = out.apply(
        lambda r: safe_div(r.get("top10_weighted_net_bps", np.nan), abs(r.get("left10_weighted_net_bps", np.nan))),
        axis=1,
    )
    return out


def attach_gross_mixture(segment: pd.DataFrame) -> pd.DataFrame:
    out = segment.copy()
    g_abs = float(out.loc[out["segment"].eq("Fold1"), "gross_mean_bps"].iloc[0])
    g_rel = float(out.loc[out["segment"].eq("Fold3"), "gross_mean_bps"].iloc[0])
    den = g_rel - g_abs
    out["release_state_pi_from_gross_mean"] = (out["gross_mean_bps"] - g_abs) / den
    out["release_state_pi_from_gross_mean_clipped"] = out["release_state_pi_from_gross_mean"].clip(0.0, 1.0)
    return out


def write_report(segment: pd.DataFrame, buckets: pd.DataFrame, weighted: pd.DataFrame, eligible: list[str]) -> None:
    fold1_w = weighted[weighted["segment"].eq("Fold1")].iloc[0]
    fold3_w = weighted[weighted["segment"].eq("Fold3")].iloc[0]
    oos16_w = weighted[weighted["segment"].eq("OOS_2026_05_16")].iloc[0]
    oos17_w = weighted[weighted["segment"].eq("OOS_2026_05_17")].iloc[0]
    pi0 = float(weighted["break_even_pi_for_mean_gt_0"].iloc[0])
    pi2 = float(weighted["pi_for_mean_gt_2bps"].iloc[0])

    lines = [
        "# CCUSDT TFI 动能转换第一性原理分析",
        "",
        f"Status: `{RUN_TAG}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "这份报告只解释结构和数学机制，不是执行建议。核心对象是已经互斥分解后的 TFI entry family；`net_median` 已经扣成本，负数不是丢弃理由。",
        "",
        "## 1. 变量定义",
        "",
        "对每个 entry 定义：",
        "",
        "```text",
        "s_i ∈ {-1,+1}                       # entry 方向",
        "X_i = s_i * 10000 * log(M_exit/M_entry)  # gross release，价格是否沿 entry 方向释放",
        "C_i = maker-light cost proxy             # 成本/价差/执行缓冲",
        "Y_i = X_i - C_i                          # net after cost",
        "```",
        "",
        "所以策略是否有价值不是问 `median(Y)>0`，而是问：",
        "",
        "```text",
        "E[Y | A] = E[X | A] - E[C | A]",
        "        = P(Y>0) * E[Y | Y>0,A] - P(Y<0) * E[-Y | Y<0,A]",
        "```",
        "",
        "右尾策略的自然形态是：大量 entry 被成本吃掉，小部分 entry 的释放幅度覆盖全部成本。关键是右尾是否稳定存在、左尾是否失控，而不是中位数是否好看。",
        "",
        "## 2. 经验分解：成本基本稳定，变化来自 gross release",
        "",
        *markdown_table(
            segment,
            [
                "segment",
                "entries",
                "gross_mean_bps",
                "cost_mean_bps",
                "gross_cost_ratio",
                "net_mean_bps",
                "net_median_bps",
                "gt2_rate",
                "cost_hit_rate",
                "pos_over_abs_neg",
                "avg_positive_net_bps",
                "avg_negative_abs_net_bps",
                "breakeven_win_rate_by_magnitude",
                "top10_avg_net_bps",
                "rest90_avg_net_bps",
                "top10_over_abs_left10",
            ],
        ),
        "",
        "第一层结论很硬：`C` 一直在 2.0bps 左右，状态切换主要不是成本突然变贵，而是 `X` 的转换效率变了。Fold1 的 gross/cost 只有吸收态水平；5/16 已经接近 break-even；5/17 的 gross/cost 重新大于 1，说明同一类 TFI 脉冲又能转成真实价格位移。",
        "",
        "## 3. 第一性原理模型：TFI 不是动能，TFI 是待转换的压力",
        "",
        "把 TFI 看成 signed latent demand impulse。价格不是因为有 TFI 就动，而是因为 TFI 对应的主动流穿透了可恢复流动性：",
        "",
        "```text",
        "dP_t = λ_t dQ_t - κ_t dR_t + σ_t dW_t",
        "",
        "Q_t: signed aggressive demand / inventory transfer",
        "R_t: maker replenishment, passive absorption, opposing inventory",
        "λ_t: impact per unit flow，近似 inverse resilient depth",
        "κ_t: absorption/replenishment strength",
        "```",
        "",
        "entry 的金融含义可以写成一个转换不等式：",
        "",
        "```text",
        "E[X_H | A_t] ≈ E[∫_0^H λ_{t+u} dQ_{t+u} | A_t]",
        "            - E[∫_0^H κ_{t+u} dR_{t+u} | A_t]",
        "",
        "entry worthiness: E[X_H | A_t] > E[C_t]",
        "```",
        "",
        "Fold1 失败不是因为结构没有金融意义，而是 `λ dQ` 被 `κ dR` 吃掉：gross release 只有成本的三分之一到一半。Fold3/5-17 有利润，是因为同样的 TFI family 落在 maker 撤退、queue stale、或 replenishment 弱的状态里，`λ` 上升或 `κ` 下降，冲击转成了位移。",
        "",
        "## 4. 非线性阈值：肥尾从哪里来",
        "",
        "如果把盘口看成有恢复力的队列系统，动能转换更像 first-passage problem，而不是线性回归：",
        "",
        "```text",
        "B_u = J_u - A_u",
        "J_u = cumulative signed impulse from TFI-side demand",
        "A_u = cumulative absorption / replenishment / opposing inventory",
        "D_u = effective resilient depth until next repricing",
        "",
        "τ = inf{u <= H : B_u > D_u}",
        "X_H ≈ α (B_τ - D_τ)^+ + β * repricing_cascade_τ,H + ε_H",
        "```",
        "",
        "这会天然产生右尾：当 `B_u` 没过 `D_u`，结果只是成本摩擦和小幅来回跳；一旦过阈值，best quote 被穿透、maker 撤单/补价、后续交易者追随，`X_H` 对 `B-D` 呈凸函数。于是 Fold1 到 Fold3 的差异，不需要假设信号本身变了，只需要 `D` 或 `A` 略变，就能把同一批 TFI entry 从成本噪声推到释放态。",
        "",
        "这也解释为什么 top10 很重要。真正的数学对象是：",
        "",
        "```text",
        "E[Y] = q * W - (1-q) * L",
        "q* = L / (W + L)",
        "",
        "W = E[Y | Y>0], L = E[-Y | Y<0]",
        "```",
        "",
        "如果实际 win_rate 低于 `q*`，结构被成本和左尾吃掉；如果 win_rate 或 W 上升，哪怕 median 仍负，期望也可以转正。报告表里的 `breakeven_win_rate_by_magnitude` 就是这个 `q*`。",
        "",
        "## 5. 路径分解：mid transition 很多，但 amplitude 才是核心",
        "",
        *markdown_table(
            segment,
            [
                "segment",
                "mid_transition_rate",
                "mid_transition_count_mean",
                "first_mid_hold_mean_sec",
                "first_mid_gross_mean_bps",
                "post_first_mid_release_mean_bps",
                "first_mid_capture_ratio",
                "mfe_mean_bps",
                "mae_mean_bps",
                "winner_final_over_mfe_mean",
                "adverse_over_cost_mean",
            ],
        ),
        "",
        "这里最重要的点：Fold1 也有很高的 mid/quote transition rate，所以“发生过跳动”不是 edge。edge 是 `X_H = X_{τ1} + (X_H - X_{τ1})` 里的幅度项：第一次跳动有多大，跳动之后有没有继续扩散，最后保留了多少 MFE。吸收态里 transition 可以频繁发生，但大多只是来回重定价；释放态里 transition 才会变成连续 displacement。",
        "",
        "## 6. 隐状态混合：不是 alive/dead，而是 release probability",
        "",
        "用 Fold1 作为 absorption state，用 Fold3 作为 release state，对 locked weighted strategy 建一个最小二态模型：",
        "",
        "```text",
        "Y | signal ~ π_t * Release + (1 - π_t) * Absorption",
        "m_t = E[Y_t | signal]",
        "π_t = (m_t - m_absorb) / (m_release - m_absorb)",
        "```",
        "",
        f"这里 `m_absorb={fmt(fold1_w['weighted_mean_net_bps'])}` bps，`m_release={fmt(fold3_w['weighted_mean_net_bps'])}` bps。break-even 所需 `π>{fmt(pi0)}`；要让 weighted mean 超过 2bps，约需 `π>{fmt(pi2)}`。",
        "",
        *markdown_table(
            weighted,
            [
                "segment",
                "weighted_mean_net_bps",
                "total_weighted_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
                "release_state_pi_from_weighted_mean",
                "pos_over_abs_neg",
                "top10_over_abs_left10",
            ],
        ),
        "",
        f"这个模型解释了 5/16 和 5/17 的差异：5/16 的 `π≈{fmt(oos16_w['release_state_pi_from_weighted_mean'])}`，高于 break-even 但远低于 2bps mean 阈值，所以表现为小正或接近吸收；5/17 的 `π≈{fmt(oos17_w['release_state_pi_from_weighted_mean'])}`，已经超过 2bps mean 阈值，右尾/中部释放都回来了。它不是简单“一波流已经没了”，更像脉冲式 regime。",
        "",
        "## 7. 互斥结构的金融含义",
        "",
        *markdown_table(
            buckets.sort_values(["segment", "total_net_bps"], ascending=[True, False]),
            [
                "segment",
                "membership_set",
                "entries",
                "gross_mean_bps",
                "cost_mean_bps",
                "net_mean_bps",
                "net_median_bps",
                "gt2_rate",
                "total_net_bps",
                "top10_avg_net_bps",
                "rest90_avg_net_bps",
            ],
            max_rows=40,
        ),
        "",
        "互斥 bucket 的意义不是互相替代，而是把同一个 signed pressure 拆成不同流动性状态。`follow+long/short` 是 broad latent pressure；`+event_active` 或 `+stale25` 是释放条件更强的子状态。Fold3 里这些桶都可贡献，说明它们不是必须互斥地只选一个，而是同一族 pressure-release 机制在不同状态投影上的分解。",
        "",
        "## 8. 实盘前的数学监控逻辑",
        "",
        "如果明天实盘，不能问“这个结构昨天活不活”，要在线估计 `π_t` 和 `ρ_t=E[X]/E[C]`：",
        "",
        "```text",
        "rolling window W:",
        "ρ_t = mean_W(X_i) / mean_W(C_i)",
        "r_t = sum_W(Y_i^+) / |sum_W(Y_i^-)|",
        "b_t = P_W(Y_i > 2bps)",
        "a_t = top10_W(Y) / |left10_W(Y)|",
        "",
        "logit(π_t) = logit(π_{t-1}) + log f_release(z_i) - log f_absorb(z_i)",
        "z_i = winsorized [X_i, 1{Y_i>2}, Y_i^+, Y_i^-, X_i-X_{τ1}]",
        "```",
        "",
        "最小可执行判据应当是 state sizing，而不是把 entry family 丢掉：",
        "",
        f"- `π_t < {fmt(pi0)}`：吸收态，停或极小探针。",
        f"- `{fmt(pi0)} <= π_t < {fmt(pi2)}`：正 EV 但不足 2bps mean，低权重收集 regime evidence。",
        f"- `π_t >= {fmt(pi2)}` 且 `ρ_t>1`、`r_t>1`：释放态，可以按互斥 bucket 下单/加权。",
        "",
        "这也回答“哪些指标达到什么值值得 entry”：不是 `net_median>0`，而是互斥结构本身作为 candidate，叠加当下 release-state posterior。中位数负只说明成本打掉了多数小波动；只要右尾和正负总额比仍覆盖左侧，它仍然是可用的右尾捕获结构。",
        "",
        "## Outputs",
        "",
        f"- `{out_segment_csv()}`",
        f"- `{out_bucket_csv()}`",
        f"- `{out_weighted_csv()}`",
        f"- `{out_summary_json()}`",
        "",
    ]
    out_report_md().write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    eligible, base_weight_map = load_weights()
    all_rows = load_all_memberships(eligible)
    segment = attach_gross_mixture(build_segment_table(all_rows, base_weight_map))
    buckets = build_bucket_table(all_rows)
    weighted = weighted_refs()

    segment.to_csv(out_segment_csv(), index=False)
    buckets.to_csv(out_bucket_csv(), index=False)
    weighted.to_csv(out_weighted_csv(), index=False)

    summary = {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "variant": VARIANT,
        "eligible_buckets": eligible,
        "segment_csv": str(out_segment_csv()),
        "bucket_csv": str(out_bucket_csv()),
        "weighted_csv": str(out_weighted_csv()),
        "report_md": str(out_report_md()),
        "key_read": {
            "fold1_weighted_mean_bps": float(weighted.loc[weighted["segment"].eq("Fold1"), "weighted_mean_net_bps"].iloc[0]),
            "fold3_weighted_mean_bps": float(weighted.loc[weighted["segment"].eq("Fold3"), "weighted_mean_net_bps"].iloc[0]),
            "oos_2026_05_16_release_pi": float(
                weighted.loc[weighted["segment"].eq("OOS_2026_05_16"), "release_state_pi_from_weighted_mean"].iloc[0]
            ),
            "oos_2026_05_17_release_pi": float(
                weighted.loc[weighted["segment"].eq("OOS_2026_05_17"), "release_state_pi_from_weighted_mean"].iloc[0]
            ),
            "break_even_pi": float(weighted["break_even_pi_for_mean_gt_0"].iloc[0]),
            "pi_for_mean_gt_2bps": float(weighted["pi_for_mean_gt_2bps"].iloc[0]),
        },
    }
    out_summary_json().write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(segment, buckets, weighted, eligible)
    print(
        "[ccusdt_tfi_momentum_conversion] "
        f"segments={len(segment)} buckets={len(buckets)} "
        f"pi_0516={summary['key_read']['oos_2026_05_16_release_pi']:.4f} "
        f"pi_0517={summary['key_read']['oos_2026_05_17_release_pi']:.4f} "
        f"report={out_report_md()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
