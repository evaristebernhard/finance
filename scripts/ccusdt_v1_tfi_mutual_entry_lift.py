#!/usr/bin/env python
"""Entry-time lift scan inside mutually exclusive CCUSDT TFI buckets.

This is deliberately scoped to the v1 mutual-exclusion buckets. It answers a
different question than the broader v2 gate: given a positive-EV mutually
exclusive bucket, can entry-time variables identify entries with net > 2 bps or
right-tail capture? If not, the bucket remains the tradable statistical unit.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_mutual_entry_lift_v1"
GUARDRAIL = "research_only_mutual_bucket_entry_lift_no_execution_recommendation_no_alpha_claim"
TRIGGERS = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]
KEY_COLS = ["fold", "date", "entry_row"]
US_PER_HOUR = 3_600_000_000.0

ENTRY_TIME_NUMERIC_FEATURES = [
    "abs_feature_value_max",
    "direction_aligned_feature_mean",
    "entry_spread_bps",
    "trade_window_count",
    "frames_since_mid_change",
    "past_event_25_bps",
    "abs_past_event_25_bps",
    "entry_hour",
]

LEAKAGE_COLUMNS = [
    "fixed_gross_bps",
    "fixed_cost_maker_bps",
    "fixed_cost_taker_bps",
    "fixed_cost_wide_bps",
    "fixed_net_maker_bps",
    "fixed_net_taker_bps",
    "fixed_net_wide_bps",
    "fixed_cross_maker",
    "fixed_cross_taker",
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
    "final_exit_row",
    "final_hold_sec",
]


@dataclass(frozen=True)
class Paths:
    entries_csv: Path
    membership_csv: Path
    buckets_csv: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def baseline_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_entry_lift_baseline_{self.run_tag}.csv"

    @property
    def scan_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_entry_lift_scan_{self.run_tag}.csv"

    @property
    def leakage_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_entry_lift_leakage_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_entry_lift_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-mutual-entry-lift-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan entry-time lift inside CCUSDT TFI mutual buckets.")
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
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--fold", default="expanding_fold3")
    parser.add_argument("--target-net-bps", type=float, default=2.0)
    parser.add_argument("--min-total-net-bps", type=float, default=90.0)
    parser.add_argument("--min-net-mean-bps", type=float, default=0.0)
    parser.add_argument("--shares", default="0.10,0.20,0.30,0.50,0.70")
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


def finite_mean(values: pd.Series | np.ndarray) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: pd.Series | np.ndarray, q: float) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def cvar10(values: pd.Series | np.ndarray) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, 0.10))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def safe_rate(mask: pd.Series | np.ndarray) -> float:
    arr = pd.Series(mask).dropna().astype(bool)
    return float(arr.mean()) if len(arr) else np.nan


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > 1e-12 else np.nan


def build_entry_time_features(entries: pd.DataFrame) -> pd.DataFrame:
    work = entries[entries["trigger_class"].isin(TRIGGERS)].copy()
    for col in [
        "entry_row",
        "entry_event_index",
        "direction",
        "feature_value",
        "entry_spread_bps",
        "trade_window_count",
        "frames_since_mid_change",
        "past_event_25_bps",
        "entry_local_timestamp",
    ]:
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")

    base = (
        work.sort_values(KEY_COLS + ["trigger_class"])
        .drop_duplicates(KEY_COLS, keep="first")
        [
            KEY_COLS
            + [
                "entry_event_index",
                "entry_local_timestamp",
                "direction",
                "entry_spread_bps",
                "trade_window_count",
                "frames_since_mid_change",
                "past_event_25_bps",
            ]
        ]
        .copy()
    )
    feature_groups = work.groupby(KEY_COLS, sort=False)
    feature_agg = feature_groups.agg(
        feature_value_mean=("feature_value", "mean"),
        abs_feature_value_max=("feature_value", lambda x: float(np.nanmax(np.abs(pd.to_numeric(x, errors="coerce"))))),
    ).reset_index()
    aligned = work.assign(direction_aligned_feature=work["direction"] * work["feature_value"])
    aligned_agg = (
        aligned.groupby(KEY_COLS, sort=False)
        .agg(direction_aligned_feature_mean=("direction_aligned_feature", "mean"))
        .reset_index()
    )
    trigger_values = (
        work.pivot_table(index=KEY_COLS, columns="trigger_class", values="feature_value", aggfunc="first")
        .add_prefix("feature_value_")
        .reset_index()
    )
    out = base.merge(feature_agg, on=KEY_COLS, how="left").merge(aligned_agg, on=KEY_COLS, how="left")
    out = out.merge(trigger_values, on=KEY_COLS, how="left")
    out["abs_past_event_25_bps"] = out["past_event_25_bps"].abs()
    out["entry_hour"] = np.floor(out["entry_local_timestamp"].fillna(0.0) / US_PER_HOUR).astype("int64") % 24
    out["side"] = np.where(out["direction"] > 0, "long", np.where(out["direction"] < 0, "short", "flat"))
    return out


def baseline_metrics(scope: str, membership_set: str, group: pd.DataFrame, target_net_bps: float) -> dict[str, Any]:
    net = pd.to_numeric(group["fixed_net_maker_bps"], errors="coerce")
    total_net = float(net.sum())
    target = net > target_net_bps
    top_cut = finite_quantile(net, 0.90)
    left_cut = finite_quantile(net, 0.10)
    return {
        "scope": scope,
        "membership_set": membership_set,
        "entries": int(len(group)),
        "net_mean_bps": finite_mean(net),
        "net_median_bps": finite_quantile(net, 0.50),
        "net_p90_bps": top_cut,
        "net_p10_bps": left_cut,
        "net_cvar10_bps": cvar10(net),
        "gt_target_rate": safe_rate(target),
        "total_net_bps": total_net,
        "top10_count": int((net >= top_cut).sum()) if np.isfinite(top_cut) else 0,
        "top10_net_bps": float(net[net >= top_cut].sum()) if np.isfinite(top_cut) else np.nan,
        "left10_net_bps": float(net[net <= left_cut].sum()) if np.isfinite(left_cut) else np.nan,
    }


def scan_feature(
    scope: str,
    membership_set: str,
    group: pd.DataFrame,
    feature: str,
    shares: list[float],
    target_net_bps: float,
) -> list[dict[str, Any]]:
    if feature not in group.columns:
        return []
    base = group.copy()
    base[feature] = pd.to_numeric(base[feature], errors="coerce")
    base = base[np.isfinite(base[feature].to_numpy(dtype="float64"))].copy()
    if len(base) < 10:
        return []

    net_all = pd.to_numeric(base["fixed_net_maker_bps"], errors="coerce")
    total_net_all = float(net_all.sum())
    total_abs_neg_all = float(abs(net_all[net_all < 0.0].sum()))
    target_rate_all = safe_rate(net_all > target_net_bps)
    top_cut = finite_quantile(net_all, 0.90)
    top_mask_all = net_all >= top_cut if np.isfinite(top_cut) else pd.Series(False, index=base.index)
    top_count_all = int(top_mask_all.sum())
    top_net_all = float(net_all[top_mask_all].sum()) if top_count_all else np.nan
    cvar_all = cvar10(net_all)
    mean_all = finite_mean(net_all)

    rows: list[dict[str, Any]] = []
    for direction in ["high", "low"]:
        ordered = base.sort_values(feature, ascending=direction == "low")
        for share in shares:
            n_select = max(1, int(np.ceil(len(ordered) * share)))
            selected = ordered.head(n_select).copy()
            net_sel = pd.to_numeric(selected["fixed_net_maker_bps"], errors="coerce")
            selected_top_mask = net_sel >= top_cut if np.isfinite(top_cut) else pd.Series(False, index=selected.index)
            total_net_sel = float(net_sel.sum())
            exposure_retention = safe_div(len(selected), len(base))
            target_rate_sel = safe_rate(net_sel > target_net_bps)
            lift = safe_div(target_rate_sel, target_rate_all)
            top_tail_count_capture = safe_div(int(selected_top_mask.sum()), top_count_all)
            selected_top_net = float(net_sel[selected_top_mask].sum()) if int(selected_top_mask.sum()) else 0.0
            top_tail_net_retention = safe_div(selected_top_net, top_net_all)
            total_net_retention = safe_div(total_net_sel, total_net_all)
            selected_abs_neg = float(abs(net_sel[net_sel < 0.0].sum()))
            left_tail_reduction = 1.0 - safe_div(selected_abs_neg, total_abs_neg_all) if total_abs_neg_all > 0 else np.nan
            mean_sel = finite_mean(net_sel)
            cvar_sel = cvar10(net_sel)
            strict_pass = bool(
                np.isfinite(top_tail_count_capture)
                and np.isfinite(exposure_retention)
                and top_tail_count_capture > exposure_retention
                and np.isfinite(lift)
                and lift > 1.5
                and np.isfinite(total_net_retention)
                and total_net_retention >= 0.85
                and np.isfinite(top_tail_net_retention)
                and top_tail_net_retention >= 0.80
                and np.isfinite(left_tail_reduction)
                and left_tail_reduction >= 0.25
                and np.isfinite(mean_sel - mean_all)
                and (mean_sel - mean_all) > 1.0
            )
            weak_pass = bool(
                np.isfinite(top_tail_count_capture)
                and np.isfinite(exposure_retention)
                and top_tail_count_capture > exposure_retention
                and np.isfinite(lift)
                and lift > 1.2
                and np.isfinite(total_net_retention)
                and np.isfinite(exposure_retention)
                and total_net_retention > exposure_retention
                and np.isfinite(mean_sel - mean_all)
                and (mean_sel - mean_all) > 0.5
            )
            if strict_pass:
                status = "strict_rank_signal"
            elif weak_pass:
                status = "weak_rank_signal"
            else:
                status = "keep_full_bucket_no_filter"
            rows.append(
                {
                    "scope": scope,
                    "membership_set": membership_set,
                    "feature": feature,
                    "select_direction": direction,
                    "select_share": share,
                    "entries_all": int(len(base)),
                    "entries_selected": int(len(selected)),
                    "exposure_retention": exposure_retention,
                    "feature_min_selected": finite_quantile(selected[feature], 0.0),
                    "feature_max_selected": finite_quantile(selected[feature], 1.0),
                    "target_rate_all": target_rate_all,
                    "target_rate_selected": target_rate_sel,
                    "target_lift": lift,
                    "net_mean_all_bps": mean_all,
                    "net_mean_selected_bps": mean_sel,
                    "net_per_entry_lift_bps": mean_sel - mean_all,
                    "total_net_all_bps": total_net_all,
                    "total_net_selected_bps": total_net_sel,
                    "total_net_retention": total_net_retention,
                    "top_tail_count_capture_rate": top_tail_count_capture,
                    "top_tail_net_retention": top_tail_net_retention,
                    "left_tail_reduction": left_tail_reduction,
                    "cvar10_all_bps": cvar_all,
                    "cvar10_selected_bps": cvar_sel,
                    "cvar10_improvement_bps": cvar_sel - cvar_all,
                    "status": status,
                }
            )
    return rows


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
    baseline: pd.DataFrame,
    scan: pd.DataFrame,
    leakage: pd.DataFrame,
) -> None:
    strict = scan[scan["status"].eq("strict_rank_signal")].copy()
    weak = scan[scan["status"].eq("weak_rank_signal")].copy()
    status_rank = {"strict_rank_signal": 0, "weak_rank_signal": 1, "keep_full_bucket_no_filter": 2}
    top_scan = scan.assign(status_rank=scan["status"].map(status_rank).fillna(9)).sort_values(
        ["status_rank", "target_lift", "total_net_retention", "top_tail_count_capture_rate", "net_per_entry_lift_bps"],
        ascending=[True, False, False, False, False],
    )
    lines = [
        "# CCUSDT V1 TFI Mutual Entry Lift",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This report works inside already mutually-exclusive positive-EV TFI buckets. It does not discard a bucket because `net_median` is negative. The question is whether entry-time variables can improve the chance of `net > 2 bps` or capture the right tail better than simply trading the whole positive-EV bucket.",
        "",
        "## Scope",
        "",
        f"- Fold: `{args.fold}`.",
        f"- Target: `fixed_net_maker_bps > {args.target_net_bps:g}`.",
        f"- Positive-EV bucket rule: `total_net_bps > {args.min_total_net_bps:g}` and `net_mean_bps > {args.min_net_mean_bps:g}`.",
        f"- Eligible buckets: `{', '.join(eligible_buckets)}`.",
        "",
        "## Baseline Buckets",
        "",
        *markdown_table(
            baseline,
            [
                "scope",
                "membership_set",
                "entries",
                "net_mean_bps",
                "net_median_bps",
                "gt_target_rate",
                "total_net_bps",
                "top10_net_bps",
                "left10_net_bps",
            ],
            20,
        ),
        "",
        "## Ranking Readout",
        "",
        f"- Strict rank signals: `{len(strict)}`.",
        f"- Weak diagnostic rank signals: `{len(weak)}`.",
        "",
        "A strict row must beat exposure on top-tail capture, lift `P(net>2)` by `>1.5x`, retain at least `85%` total net, retain at least `80%` top-tail net, reduce left-tail loss by at least `25%`, and improve selected mean by `>1` bps.",
        "",
        "If no strict row appears for a bucket, the correct read is not to filter it away. The bucket remains the statistical entry unit; ranking can be used only as a sizing diagnostic until walk-forward proof exists.",
        "",
        "## Best Diagnostic Rows",
        "",
        *markdown_table(
            top_scan,
            [
                "scope",
                "membership_set",
                "feature",
                "select_direction",
                "select_share",
                "entries_selected",
                "target_rate_all",
                "target_rate_selected",
                "target_lift",
                "net_per_entry_lift_bps",
                "total_net_retention",
                "top_tail_count_capture_rate",
                "left_tail_reduction",
                "status",
            ],
            40,
        ),
        "",
        "## Leakage Audit",
        "",
        *markdown_table(leakage, ["column", "entry_time_allowed", "reason"], 80),
        "",
        "## Output Tables",
        "",
        f"- `{paths.baseline_csv}`",
        f"- `{paths.scan_csv}`",
        f"- `{paths.leakage_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v1_tfi_mutual_entry_lift.py --run-tag {paths.run_tag}",
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
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    shares = parse_float_list(args.shares)

    entries = pd.read_csv(paths.entries_csv)
    membership = pd.read_csv(paths.membership_csv)
    buckets = pd.read_csv(paths.buckets_csv)
    features = build_entry_time_features(entries)
    work = membership.merge(features, on=KEY_COLS, how="left", suffixes=("", "_entry"))
    fold_buckets = buckets[buckets["fold"].eq(args.fold)].copy()
    for col in ["total_net_bps", "net_mean_bps"]:
        fold_buckets[col] = pd.to_numeric(fold_buckets[col], errors="coerce")
    eligible_buckets = (
        fold_buckets[
            (fold_buckets["total_net_bps"] > args.min_total_net_bps)
            & (fold_buckets["net_mean_bps"] > args.min_net_mean_bps)
        ]["membership_set"]
        .sort_values()
        .tolist()
    )
    fold_work = work[work["fold"].eq(args.fold) & work["membership_set"].isin(eligible_buckets)].copy()
    if fold_work.empty:
        raise ValueError("no eligible rows for requested fold and thresholds")

    baseline_rows: list[dict[str, Any]] = []
    scan_rows: list[dict[str, Any]] = []
    baseline_rows.append(baseline_metrics("eligible_union", "ALL_POSITIVE_EV_BUCKETS", fold_work, args.target_net_bps))
    for feature in ENTRY_TIME_NUMERIC_FEATURES:
        scan_rows.extend(
            scan_feature(
                "eligible_union",
                "ALL_POSITIVE_EV_BUCKETS",
                fold_work,
                feature,
                shares,
                args.target_net_bps,
            )
        )
    for membership_set, group in fold_work.groupby("membership_set", sort=True):
        baseline_rows.append(baseline_metrics("bucket", membership_set, group, args.target_net_bps))
        for feature in ENTRY_TIME_NUMERIC_FEATURES:
            scan_rows.extend(scan_feature("bucket", membership_set, group, feature, shares, args.target_net_bps))

    baseline = pd.DataFrame(baseline_rows)
    scan = pd.DataFrame(scan_rows)
    leakage = pd.DataFrame(
        [{"column": col, "entry_time_allowed": False, "reason": "outcome/path/cost-after-exit information"} for col in LEAKAGE_COLUMNS]
        + [
            {"column": col, "entry_time_allowed": True, "reason": "known at entry or bucket membership state"}
            for col in ENTRY_TIME_NUMERIC_FEATURES + TRIGGERS + ["membership_set", "direction", "side"]
        ]
    )

    baseline.to_csv(paths.baseline_csv, index=False)
    scan.to_csv(paths.scan_csv, index=False)
    leakage.to_csv(paths.leakage_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "fold": args.fold,
        "target_net_bps": args.target_net_bps,
        "eligible_buckets": eligible_buckets,
        "eligible_entries": int(len(fold_work)),
        "baseline_rows": int(len(baseline)),
        "scan_rows": int(len(scan)),
        "strict_rank_signal_rows": int(scan["status"].eq("strict_rank_signal").sum()) if not scan.empty else 0,
        "weak_rank_signal_rows": int(scan["status"].eq("weak_rank_signal").sum()) if not scan.empty else 0,
        "outputs": {
            "baseline_csv": str(paths.baseline_csv),
            "scan_csv": str(paths.scan_csv),
            "leakage_csv": str(paths.leakage_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, args, eligible_buckets, baseline, scan, leakage)
    print(
        "[ccusdt_tfi_mutual_entry_lift] "
        f"eligible_entries={len(fold_work)} buckets={len(eligible_buckets)} "
        f"scan_rows={len(scan)} strict={summary['strict_rank_signal_rows']} weak={summary['weak_rank_signal_rows']} "
        f"wrote={paths.report_md}"
    )


if __name__ == "__main__":
    main()
