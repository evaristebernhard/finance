#!/usr/bin/env python
"""Strategy optimization prototype for mutually exclusive CCUSDT TFI buckets.

The unit of trade is the mutually-exclusive positive-EV bucket. This script
does not optimize by deleting buckets with negative net median. It tries
bucket weights and weak entry-time sizing overlays while keeping every
eligible bucket available.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import ccusdt_v1_tfi_mutual_entry_lift as lift


RUN_TAG = "20260518_ccusdt_v1_tfi_mutual_strategy_opt_v1"
GUARDRAIL = "research_only_mutual_bucket_strategy_optimization_no_execution_recommendation_no_alpha_claim"
KEY_COLS = ["fold", "date", "entry_row"]
DEFAULT_BASE_WEIGHTS = "0.5,1.0,1.5,2.0"


@dataclass(frozen=True)
class Paths:
    entries_csv: Path
    membership_csv: Path
    buckets_csv: Path
    lift_scan_csv: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def variants_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_strategy_variants_{self.run_tag}.csv"

    @property
    def scorecard_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_strategy_scorecard_{self.run_tag}.csv"

    @property
    def weights_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_strategy_weights_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_strategy_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-mutual-strategy-opt-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize CCUSDT TFI mutually-exclusive positive-EV strategy variants.")
    parser.add_argument(
        "--entries-csv",
        type=Path,
        default=Path("date/ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv"),
    )
    parser.add_argument(
        "--membership-csv",
        type=Path,
        default=Path("date/ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv"),
    )
    parser.add_argument(
        "--buckets-csv",
        type=Path,
        default=Path("date/ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv"),
    )
    parser.add_argument(
        "--lift-scan-csv",
        type=Path,
        default=Path("date/ccusdt_v1_tfi_mutual_entry_lift_scan_20260518_ccusdt_v1_tfi_mutual_entry_lift_v1.csv"),
    )
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--selection-fold", default="expanding_fold3")
    parser.add_argument("--min-total-net-bps", type=float, default=90.0)
    parser.add_argument("--min-net-mean-bps", type=float, default=0.0)
    parser.add_argument("--target-net-bps", type=float, default=2.0)
    parser.add_argument("--base-weights", default=DEFAULT_BASE_WEIGHTS)
    parser.add_argument("--max-grid-variants", type=int, default=20)
    parser.add_argument("--max-weak-overlays", type=int, default=12)
    parser.add_argument("--weak-boost", type=float, default=0.5)
    parser.add_argument("--weak-status", default="weak_rank_signal")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def parse_float_list(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("expected at least one float")
    return sorted(set(values))


def fmt_num(value: object, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return np.nan
    v = values[mask]
    w = weights[mask]
    order = np.argsort(v)
    v = v[order]
    w = w[order]
    cum = np.cumsum(w)
    cutoff = q * cum[-1]
    return float(v[np.searchsorted(cum, cutoff, side="left")])


def weighted_cvar(values: np.ndarray, weights: np.ndarray, q: float = 0.10) -> float:
    cutoff = weighted_quantile(values, weights, q)
    if not np.isfinite(cutoff):
        return np.nan
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0) & (values <= cutoff)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))


def max_drawdown(weighted_net: pd.Series) -> float:
    if weighted_net.empty:
        return np.nan
    curve = weighted_net.cumsum().to_numpy(dtype="float64")
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    return float(dd.min()) if len(dd) else np.nan


def eligible_bucket_list(buckets: pd.DataFrame, args: argparse.Namespace) -> list[str]:
    fold_buckets = buckets[buckets["fold"].eq(args.selection_fold)].copy()
    for col in ["total_net_bps", "net_mean_bps"]:
        fold_buckets[col] = pd.to_numeric(fold_buckets[col], errors="coerce")
    return (
        fold_buckets[
            (fold_buckets["total_net_bps"] > args.min_total_net_bps)
            & (fold_buckets["net_mean_bps"] > args.min_net_mean_bps)
        ]["membership_set"]
        .sort_values()
        .tolist()
    )


def prepare_work(paths: Paths, eligible_buckets: list[str]) -> pd.DataFrame:
    entries = pd.read_csv(paths.entries_csv)
    membership = pd.read_csv(paths.membership_csv)
    features = lift.build_entry_time_features(entries)
    work = membership.merge(features, on=KEY_COLS, how="left", suffixes=("", "_entry"))
    work = work[work["membership_set"].isin(eligible_buckets)].copy()
    for col in ["entry_row", "entry_event_index", "entry_local_timestamp", "fixed_net_maker_bps", "entry_spread_bps"]:
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work["date"] = work["date"].astype(str)
    work = work.sort_values(["date", "entry_local_timestamp", "entry_row"]).reset_index(drop=True)
    return work


def apply_bucket_weights(work: pd.DataFrame, bucket_weights: dict[str, float]) -> pd.Series:
    return work["membership_set"].map(bucket_weights).fillna(0.0).astype(float)


def selected_mask_for_scan(group: pd.DataFrame, scan_row: pd.Series) -> pd.Series:
    feature = str(scan_row["feature"])
    direction = str(scan_row["select_direction"])
    share = float(scan_row["select_share"])
    if feature not in group:
        return pd.Series(False, index=group.index)
    values = pd.to_numeric(group[feature], errors="coerce")
    valid = values[np.isfinite(values.to_numpy(dtype="float64"))]
    if valid.empty:
        return pd.Series(False, index=group.index)
    n_select = max(1, int(np.ceil(len(valid) * share)))
    selected_idx = valid.sort_values(ascending=direction == "low").head(n_select).index
    mask = pd.Series(False, index=group.index)
    mask.loc[selected_idx] = True
    return mask


def apply_weak_overlay(work: pd.DataFrame, weights: pd.Series, scan_row: pd.Series, boost: float) -> pd.Series:
    out = weights.copy()
    scope = str(scan_row["scope"])
    membership_set = str(scan_row["membership_set"])
    if scope == "eligible_union":
        scope_mask = pd.Series(True, index=work.index)
    else:
        scope_mask = work["membership_set"].eq(membership_set)
    selected = selected_mask_for_scan(work[scope_mask], scan_row)
    out.loc[selected.index[selected]] = out.loc[selected.index[selected]] * (1.0 + boost)
    return out


def evaluate_variant(
    work: pd.DataFrame,
    variant_name: str,
    variant_kind: str,
    weights: pd.Series,
    target_net_bps: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    scopes = [("all_folds", work)]
    scopes.extend([(fold, group) for fold, group in work.groupby("fold", sort=True)])
    for eval_scope, group in scopes:
        w = weights.loc[group.index].to_numpy(dtype="float64")
        net = pd.to_numeric(group["fixed_net_maker_bps"], errors="coerce").to_numpy(dtype="float64")
        active = np.isfinite(net) & np.isfinite(w) & (w > 0)
        if not active.any():
            continue
        net = net[active]
        w = w[active]
        active_group = group.loc[group.index[active]].copy()
        weighted_net = pd.Series(w * net, index=active_group.index)
        total_weight = float(w.sum())
        total_net = float(weighted_net.sum())
        mean_net = safe_div(total_net, total_weight)
        p10 = weighted_quantile(net, w, 0.10)
        cvar10 = weighted_cvar(net, w, 0.10)
        gt2_rate = safe_div(float(w[net > target_net_bps].sum()), total_weight)
        win_rate = safe_div(float(w[net > 0.0].sum()), total_weight)
        cost_hit_rate = safe_div(float(w[net <= 0.0].sum()), total_weight)
        neg_sum = float((w * np.minimum(net, 0.0)).sum())
        pos_sum = float((w * np.maximum(net, 0.0)).sum())
        top_cut = weighted_quantile(net, w, 0.90)
        top_mask = net >= top_cut if np.isfinite(top_cut) else np.zeros(len(net), dtype=bool)
        top_net = float((w[top_mask] * net[top_mask]).sum()) if top_mask.any() else np.nan
        top_share = safe_div(top_net, total_net)
        rows.append(
            {
                "run_tag": RUN_TAG,
                "guardrail": GUARDRAIL,
                "variant": variant_name,
                "variant_kind": variant_kind,
                "eval_scope": eval_scope,
                "entries": int(len(net)),
                "exposure_units": total_weight,
                "total_weighted_net_bps": total_net,
                "weighted_mean_net_bps": mean_net,
                "weighted_median_net_bps": weighted_quantile(net, w, 0.50),
                "weighted_p10_net_bps": p10,
                "weighted_cvar10_net_bps": cvar10,
                "weighted_gt2_rate": gt2_rate,
                "weighted_win_rate": win_rate,
                "cost_hit_rate": cost_hit_rate,
                "positive_net_bps": pos_sum,
                "negative_net_bps": neg_sum,
                "top10_weighted_net_bps": top_net,
                "top10_share_of_total_net": top_share,
                "max_drawdown_bps_units": max_drawdown(weighted_net.loc[active_group.sort_values(["date", "entry_local_timestamp", "entry_row"]).index]),
            }
        )
    return rows


def grid_bucket_variants(
    work: pd.DataFrame,
    eligible_buckets: list[str],
    base_weights: list[float],
    target_net_bps: float,
    max_variants: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[str, dict[str, float]]]]:
    candidates: list[tuple[float, str, dict[str, float], dict[str, Any]]] = []
    fold3 = work[work["fold"].eq("expanding_fold3")].copy()
    for combo in itertools.product(base_weights, repeat=len(eligible_buckets)):
        bucket_weights = dict(zip(eligible_buckets, combo))
        weights = apply_bucket_weights(fold3, bucket_weights)
        metrics = evaluate_variant(fold3, "tmp", "bucket_weight_grid", weights, target_net_bps)
        fold_metrics = next(row for row in metrics if row["eval_scope"] == "all_folds")
        # Unit-exposure objective; total net alone would choose max leverage.
        score = (
            float(fold_metrics["weighted_mean_net_bps"])
            + 0.30 * float(fold_metrics["weighted_gt2_rate"])
            + 0.02 * float(fold_metrics["weighted_cvar10_net_bps"])
            + 0.001 * float(fold_metrics["max_drawdown_bps_units"])
        )
        candidates.append((score, "", bucket_weights, fold_metrics))
    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = candidates[:max_variants]
    variant_metrics: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    variants: list[tuple[str, dict[str, float]]] = []
    for idx, (score, _name, bucket_weights, _fold_metrics) in enumerate(chosen, start=1):
        name = f"bucket_grid_rank{idx:02d}"
        variants.append((name, bucket_weights))
        weights = apply_bucket_weights(work, bucket_weights)
        variant_metrics.extend(evaluate_variant(work, name, "bucket_weight_grid", weights, target_net_bps))
        for bucket, weight in bucket_weights.items():
            weight_rows.append(
                {
                    "variant": name,
                    "variant_kind": "bucket_weight_grid",
                    "membership_set": bucket,
                    "base_weight": weight,
                    "overlay_feature": "",
                    "overlay_direction": "",
                    "overlay_share": np.nan,
                    "overlay_boost": np.nan,
                    "selection_score": score,
                }
            )
    return variant_metrics, weight_rows, variants


def weak_overlay_variants(
    work: pd.DataFrame,
    scan: pd.DataFrame,
    base_bucket_weights: dict[str, float],
    target_net_bps: float,
    max_overlays: int,
    weak_status: str,
    weak_boost: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if scan.empty:
        return [], []
    weak = scan[scan["status"].eq(weak_status)].copy()
    if weak.empty:
        return [], []
    for col in ["target_lift", "net_per_entry_lift_bps", "total_net_retention", "top_tail_count_capture_rate"]:
        weak[col] = pd.to_numeric(weak[col], errors="coerce")
    weak["overlay_score"] = (
        weak["target_lift"].fillna(0.0)
        + 0.10 * weak["net_per_entry_lift_bps"].fillna(0.0)
        + 0.25 * weak["total_net_retention"].fillna(0.0)
        + 0.25 * weak["top_tail_count_capture_rate"].fillna(0.0)
    )
    weak = weak.sort_values("overlay_score", ascending=False).head(max_overlays)
    base_weights = apply_bucket_weights(work, base_bucket_weights)
    variant_metrics: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(weak.iterrows(), start=1):
        name = f"weak_overlay_rank{idx:02d}"
        weights = apply_weak_overlay(work, base_weights, row, weak_boost)
        variant_metrics.extend(evaluate_variant(work, name, "weak_signal_sizing", weights, target_net_bps))
        for bucket, weight in base_bucket_weights.items():
            weight_rows.append(
                {
                    "variant": name,
                    "variant_kind": "weak_signal_sizing",
                    "membership_set": bucket,
                    "base_weight": weight,
                    "overlay_feature": row["feature"],
                    "overlay_direction": row["select_direction"],
                    "overlay_share": row["select_share"],
                    "overlay_boost": weak_boost,
                    "overlay_scope": row["scope"],
                    "overlay_membership_set": row["membership_set"],
                    "selection_score": row["overlay_score"],
                }
            )
    return variant_metrics, weight_rows


def build_scorecard(variants: pd.DataFrame) -> pd.DataFrame:
    if variants.empty:
        return variants
    piv = variants.pivot_table(
        index=["variant", "variant_kind"],
        columns="eval_scope",
        values=[
            "weighted_mean_net_bps",
            "total_weighted_net_bps",
            "weighted_cvar10_net_bps",
            "weighted_gt2_rate",
            "max_drawdown_bps_units",
            "cost_hit_rate",
            "top10_share_of_total_net",
        ],
        aggfunc="first",
    )
    piv.columns = [f"{metric}_{scope}" for metric, scope in piv.columns]
    out = piv.reset_index()
    mean_cols = [col for col in out.columns if col.startswith("weighted_mean_net_bps_expanding_fold")]
    out["positive_fold_count"] = out[mean_cols].gt(0.0).sum(axis=1) if mean_cols else 0
    out["min_fold_mean_bps"] = out[mean_cols].min(axis=1) if mean_cols else np.nan
    out["mean_fold_mean_bps"] = out[mean_cols].mean(axis=1) if mean_cols else np.nan
    fold3_mean = out.get("weighted_mean_net_bps_expanding_fold3", pd.Series(np.nan, index=out.index))
    out["optimization_status"] = "diagnostic_only"
    out.loc[(out["positive_fold_count"] == len(mean_cols)) & (fold3_mean > 2.0), "optimization_status"] = (
        "stable_usable_prototype"
    )
    out.loc[(out["positive_fold_count"] >= 2) & (fold3_mean > 2.0) & (out["optimization_status"].eq("diagnostic_only")), "optimization_status"] = (
        "recent_usable_prototype_fold1_weak"
    )
    sort_cols = [
        "optimization_status",
        "weighted_mean_net_bps_expanding_fold3",
        "weighted_cvar10_net_bps_expanding_fold3",
        "total_weighted_net_bps_expanding_fold3",
    ]
    sort_cols = [col for col in sort_cols if col in out.columns]
    return out.sort_values(sort_cols, ascending=[False, False, False, False][: len(sort_cols)])


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    view = df.loc[:, [col for col in columns if col in df.columns]].head(max_rows).copy()
    lines = ["| " + " | ".join(view.columns) + " |", "| " + " | ".join(["---"] * len(view.columns)) + " |"]
    for _, row in view.iterrows():
        cells: list[str] = []
        for value in row:
            if isinstance(value, float):
                cells.append(fmt_num(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(
    paths: Paths,
    args: argparse.Namespace,
    eligible_buckets: list[str],
    variants: pd.DataFrame,
    scorecard: pd.DataFrame,
    weights: pd.DataFrame,
) -> None:
    fold3 = variants[variants["eval_scope"].eq(args.selection_fold)].copy()
    fold3 = fold3.sort_values(
        ["weighted_mean_net_bps", "weighted_cvar10_net_bps", "total_weighted_net_bps"],
        ascending=[False, False, False],
    )
    lines = [
        "# CCUSDT V1 TFI Mutual Strategy Optimization",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This is a strategy-optimization prototype on already mutually-exclusive positive-EV TFI buckets. It allows cost-dragged entries and does not reject a bucket because its cost-adjusted median is negative.",
        "",
        "## Scope",
        "",
        f"- Selection fold for eligible buckets and optimization ranking: `{args.selection_fold}`.",
        f"- Eligible bucket rule: `total_net_bps > {args.min_total_net_bps:g}` and `net_mean_bps > {args.min_net_mean_bps:g}`.",
        f"- Target label for hit-rate reporting: `net > {args.target_net_bps:g}`.",
        f"- Base bucket weights searched: `{args.base_weights}`.",
        f"- Eligible buckets: `{', '.join(eligible_buckets)}`.",
        "",
        "## Readout",
        "",
        "The optimization keeps every eligible positive-EV bucket available. Bucket-grid variants tune relative weight from `0.5x` to `2.0x`; weak-signal variants apply a sizing boost to entries selected by previously measured weak entry-time lift rows. No hard filter is applied.",
        "",
        "Practical read: the strongest recent-fold form is to keep the broad `follow+short` and `follow+long` buckets at reduced size, overweight the clean `follow+short+stale25+event_active` child, and treat weak entry-time signals as sizing boosts only. Fold1 remains negative for this family, so the optimized result is a recent-regime usable prototype, not a three-fold stable final strategy.",
        "",
        "## Best Fold3 Variants",
        "",
        *markdown_table(
            fold3,
            [
                "variant",
                "variant_kind",
                "entries",
                "exposure_units",
                "total_weighted_net_bps",
                "weighted_mean_net_bps",
                "weighted_median_net_bps",
                "weighted_gt2_rate",
                "cost_hit_rate",
                "weighted_cvar10_net_bps",
                "max_drawdown_bps_units",
                "top10_share_of_total_net",
            ],
            30,
        ),
        "",
        "## Cross-Fold Scorecard",
        "",
        *markdown_table(
            scorecard,
            [
                "variant",
                "variant_kind",
                "optimization_status",
                "weighted_mean_net_bps_expanding_fold1",
                "weighted_mean_net_bps_expanding_fold2",
                "weighted_mean_net_bps_expanding_fold3",
                "positive_fold_count",
                "min_fold_mean_bps",
                "total_weighted_net_bps_expanding_fold3",
                "weighted_cvar10_net_bps_expanding_fold3",
                "max_drawdown_bps_units_expanding_fold3",
            ],
            40,
        ),
        "",
        "## Selected Weights",
        "",
        *markdown_table(
            weights,
            [
                "variant",
                "variant_kind",
                "membership_set",
                "base_weight",
                "overlay_feature",
                "overlay_direction",
                "overlay_share",
                "overlay_boost",
                "overlay_scope",
                "overlay_membership_set",
            ],
            80,
        ),
        "",
        "## Output Tables",
        "",
        f"- `{paths.variants_csv}`",
        f"- `{paths.scorecard_csv}`",
        f"- `{paths.weights_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v1_tfi_mutual_strategy_opt.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        entries_csv=resolve_repo_path(args.entries_csv),
        membership_csv=resolve_repo_path(args.membership_csv),
        buckets_csv=resolve_repo_path(args.buckets_csv),
        lift_scan_csv=resolve_repo_path(args.lift_scan_csv),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    buckets = pd.read_csv(paths.buckets_csv)
    eligible_buckets = eligible_bucket_list(buckets, args)
    if not eligible_buckets:
        raise ValueError("no eligible buckets found")
    work = prepare_work(paths, eligible_buckets)
    base_weights = parse_float_list(args.base_weights)

    variant_rows: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []

    equal_weights = {bucket: 1.0 for bucket in eligible_buckets}
    equal_series = apply_bucket_weights(work, equal_weights)
    variant_rows.extend(evaluate_variant(work, "full_bucket_equal_1x", "baseline", equal_series, args.target_net_bps))
    for bucket, weight in equal_weights.items():
        weight_rows.append(
            {
                "variant": "full_bucket_equal_1x",
                "variant_kind": "baseline",
                "membership_set": bucket,
                "base_weight": weight,
                "overlay_feature": "",
                "overlay_direction": "",
                "overlay_share": np.nan,
                "overlay_boost": np.nan,
                "selection_score": np.nan,
            }
        )

    grid_rows, grid_weight_rows, grid_variants = grid_bucket_variants(
        work,
        eligible_buckets,
        base_weights,
        args.target_net_bps,
        args.max_grid_variants,
    )
    variant_rows.extend(grid_rows)
    weight_rows.extend(grid_weight_rows)

    # Use the best bucket-grid variant as the base for weak sizing overlays.
    if grid_variants:
        weak_base = grid_variants[0][1]
    else:
        weak_base = equal_weights
    scan = pd.read_csv(paths.lift_scan_csv) if paths.lift_scan_csv.exists() else pd.DataFrame()
    weak_rows, weak_weight_rows = weak_overlay_variants(
        work,
        scan,
        weak_base,
        args.target_net_bps,
        args.max_weak_overlays,
        args.weak_status,
        args.weak_boost,
    )
    variant_rows.extend(weak_rows)
    weight_rows.extend(weak_weight_rows)

    variants = pd.DataFrame(variant_rows)
    weights = pd.DataFrame(weight_rows)
    scorecard = build_scorecard(variants)

    variants.to_csv(paths.variants_csv, index=False)
    weights.to_csv(paths.weights_csv, index=False)
    scorecard.to_csv(paths.scorecard_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "selection_fold": args.selection_fold,
        "eligible_buckets": eligible_buckets,
        "eligible_entries_all_folds": int(len(work)),
        "variant_rows": int(len(variants)),
        "strategy_count": int(variants["variant"].nunique()) if not variants.empty else 0,
        "scorecard_rows": int(len(scorecard)),
        "outputs": {
            "variants_csv": str(paths.variants_csv),
            "scorecard_csv": str(paths.scorecard_csv),
            "weights_csv": str(paths.weights_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, args, eligible_buckets, variants, scorecard, weights)
    print(
        "[ccusdt_tfi_mutual_strategy_opt] "
        f"eligible_entries={len(work)} strategies={summary['strategy_count']} "
        f"scorecard_rows={len(scorecard)} wrote={paths.report_md}"
    )


if __name__ == "__main__":
    main()
