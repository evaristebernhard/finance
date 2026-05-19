#!/usr/bin/env python
"""Mutually exclusive decomposition for CCUSDT TFI structures.

This script starts from per-entry tail/stop diagnostics and decomposes the TFI
family by exact entry-level set membership. It is meant to clarify financial
meaning before any execution gate or strategy promotion discussion.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import ccusdt_v2_fill_realism as fill_base


GUARDRAIL = "research_only_tfi_mutual_exclusion_no_execution_recommendation_no_alpha_claim"
RUN_TAG = "20260518_ccusdt_v1_tfi_mutual_exclusion_v1"
TRIGGERS = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]
KEY_COLS = ["fold", "date", "entry_row"]
METRIC_COLS = [
    "fixed_gross_bps",
    "fixed_cost_maker_bps",
    "fixed_net_maker_bps",
    "mfe_bps",
    "mae_bps",
    "first_mid_transition_gross_bps",
    "first_quote_transition_gross_bps",
]


@dataclass(frozen=True)
class Paths:
    entries_csv: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def membership_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_membership_{self.run_tag}.csv"

    @property
    def buckets_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_buckets_{self.run_tag}.csv"

    @property
    def pairwise_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_pairwise_overlap_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_mutual_exclusion_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-mutual-exclusion-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build mutually exclusive CCUSDT TFI structure decomposition.")
    parser.add_argument(
        "--entries-csv",
        type=Path,
        default=Path("date/ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv"),
    )
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def fmt(value: Any, digits: int = 4) -> str:
    return fill_base.fmt_num(value, digits)


def finite_mean(values: pd.Series | np.ndarray) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def finite_quantile(values: pd.Series | np.ndarray, q: float) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def safe_rate(values: pd.Series | np.ndarray) -> float:
    arr = pd.Series(values).dropna()
    return float(arr.astype(bool).mean()) if len(arr) else np.nan


def cvar10(values: pd.Series | np.ndarray) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return np.nan
    cutoff = float(np.quantile(arr, 0.10))
    tail = arr[arr <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    net = group["fixed_net_maker_bps"]
    gross = group["fixed_gross_bps"]
    return {
        "entries": int(len(group)),
        "gross_mean_bps": finite_mean(gross),
        "gross_median_bps": finite_quantile(gross, 0.50),
        "gross_p90_bps": finite_quantile(gross, 0.90),
        "cost_mean_bps": finite_mean(group["fixed_cost_maker_bps"]),
        "net_mean_bps": finite_mean(net),
        "net_median_bps": finite_quantile(net, 0.50),
        "net_p10_bps": finite_quantile(net, 0.10),
        "net_p90_bps": finite_quantile(net, 0.90),
        "net_cvar10_bps": cvar10(net),
        "net_win_rate": safe_rate(pd.to_numeric(net, errors="coerce") > 0.0),
        "mfe_mean_bps": finite_mean(group["mfe_bps"]),
        "mae_mean_bps": finite_mean(group["mae_bps"]),
        "mid_transition_rate": safe_rate(group["has_mid_transition"].astype(str).str.lower().eq("true")),
        "quote_transition_rate": safe_rate(group["has_quote_transition"].astype(str).str.lower().eq("true")),
        "first_mid_transition_gross_mean_bps": finite_mean(group["first_mid_transition_gross_bps"]),
        "first_quote_transition_gross_mean_bps": finite_mean(group["first_quote_transition_gross_bps"]),
    }


def load_entries(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["trigger_class"].isin(TRIGGERS)].copy()
    for col in ["entry_row", "entry_event_index"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in METRIC_COLS + ["direction", "feature_value", "entry_spread_bps", "mfe_bps", "mae_bps"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_membership(entries: pd.DataFrame) -> pd.DataFrame:
    # Prefer one metric row per exact entry. If the same entry belongs to several
    # structures, metrics are identical for same-side overlaps and the first row
    # still represents the realized path.
    base_cols = KEY_COLS + [
        "entry_event_index",
        "entry_local_timestamp",
        "direction",
        "entry_spread_bps",
        "fixed_gross_bps",
        "fixed_cost_maker_bps",
        "fixed_net_maker_bps",
        "mfe_bps",
        "mae_bps",
        "has_mid_transition",
        "has_quote_transition",
        "first_mid_transition_gross_bps",
        "first_quote_transition_gross_bps",
    ]
    base = entries.sort_values(["fold", "date", "entry_row", "trigger_class"]).drop_duplicates(KEY_COLS, keep="first")[
        base_cols
    ].copy()
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
    out["membership_set"] = out[TRIGGERS].apply(lambda row: "+".join([col for col, yes in row.items() if yes]), axis=1)
    out["membership_set"] = out["membership_set"].replace("", "none")
    return out


def build_buckets(membership: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (fold, bucket), group in membership.groupby(["fold", "membership_set"], sort=True):
        row = {"run_tag": RUN_TAG, "guardrail": GUARDRAIL, "fold": fold, "membership_set": bucket}
        row["membership_count"] = int(group["membership_count"].iloc[0]) if len(group) else 0
        for trigger in TRIGGERS:
            row[f"has_{trigger}"] = bool(trigger in bucket.split("+"))
        row.update(summarize_group(group))
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["total_net_bps"] = out["entries"] * out["net_mean_bps"]
    return out.sort_values(["fold", "net_mean_bps", "entries"], ascending=[True, False, False])


def build_pairwise(membership: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fold, group in membership.groupby("fold", sort=True):
        for left in TRIGGERS:
            left_mask = group[left]
            left_n = int(left_mask.sum())
            for right in TRIGGERS:
                right_mask = group[right]
                right_n = int(right_mask.sum())
                both = group[left_mask & right_mask]
                both_n = int(len(both))
                row = {
                    "run_tag": RUN_TAG,
                    "guardrail": GUARDRAIL,
                    "fold": fold,
                    "left_trigger": left,
                    "right_trigger": right,
                    "left_entries": left_n,
                    "right_entries": right_n,
                    "overlap_entries": both_n,
                    "left_overlap_rate": both_n / left_n if left_n else np.nan,
                    "right_overlap_rate": both_n / right_n if right_n else np.nan,
                }
                row.update({f"overlap_{key}": value for key, value in summarize_group(both).items()})
                rows.append(row)
    return pd.DataFrame(rows)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 80) -> list[str]:
    return fill_base.markdown_table(df, columns, max_rows)


def write_report(paths: Paths, membership: pd.DataFrame, buckets: pd.DataFrame, pairwise: pd.DataFrame) -> None:
    fold3_buckets = buckets[buckets["fold"].eq("expanding_fold3")].copy()
    fold3_pairwise = pairwise[
        pairwise["fold"].eq("expanding_fold3") & pairwise["left_trigger"].ne(pairwise["right_trigger"])
    ].copy()
    fold3_pairwise = fold3_pairwise.sort_values(["overlap_entries", "left_trigger", "right_trigger"], ascending=[False, True, True])
    lines = [
        "# CCUSDT V1 TFI Mutual Exclusion",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "This report decomposes the TFI family by exact entry-level membership. It is a structure-understanding artifact, not an execution recommendation.",
        "",
        "## Objective",
        "",
        "Clarify whether the profitable TFI structures are separate effects, parent/child states, or overlapping views of the same entries.",
        "",
        "## Scope",
        "",
        f"- Source entries: `{paths.entries_csv}`.",
        f"- Unique entry keys: `{len(membership)}`.",
        f"- Structures: `{', '.join(TRIGGERS)}`.",
        "",
        "## Fold3 Mutual Buckets",
        "",
        *markdown_table(
            fold3_buckets,
            [
                "membership_set",
                "entries",
                "gross_mean_bps",
                "gross_median_bps",
                "cost_mean_bps",
                "net_mean_bps",
                "net_median_bps",
                "net_cvar10_bps",
                "mfe_mean_bps",
                "mae_mean_bps",
                "total_net_bps",
            ],
            60,
        ),
        "",
        "## Fold3 Pairwise Overlap",
        "",
        *markdown_table(
            fold3_pairwise,
            [
                "left_trigger",
                "right_trigger",
                "left_entries",
                "right_entries",
                "overlap_entries",
                "left_overlap_rate",
                "right_overlap_rate",
                "overlap_net_mean_bps",
                "overlap_gross_mean_bps",
            ],
            80,
        ),
        "",
        "## Output Tables",
        "",
        f"- `{paths.membership_csv}`",
        f"- `{paths.buckets_csv}`",
        f"- `{paths.pairwise_csv}`",
        f"- `{paths.summary_json}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        f"python scripts/ccusdt_v1_tfi_mutual_exclusion.py --run-tag {paths.run_tag}",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(paths: Paths, membership: pd.DataFrame, buckets: pd.DataFrame, pairwise: pd.DataFrame) -> None:
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)
    membership.to_csv(paths.membership_csv, index=False)
    buckets.to_csv(paths.buckets_csv, index=False)
    pairwise.to_csv(paths.pairwise_csv, index=False)
    summary = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "entries_csv": str(paths.entries_csv),
        "unique_entry_keys": int(len(membership)),
        "bucket_rows": int(len(buckets)),
        "pairwise_rows": int(len(pairwise)),
        "triggers": TRIGGERS,
        "outputs": {
            "membership_csv": str(paths.membership_csv),
            "buckets_csv": str(paths.buckets_csv),
            "pairwise_csv": str(paths.pairwise_csv),
            "summary_json": str(paths.summary_json),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(paths, membership, buckets, pairwise)


def main() -> None:
    args = parse_args()
    global RUN_TAG
    RUN_TAG = args.run_tag
    paths = Paths(
        entries_csv=resolve_repo_path(args.entries_csv),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    entries = load_entries(paths.entries_csv)
    membership = build_membership(entries)
    buckets = build_buckets(membership)
    pairwise = build_pairwise(membership)
    write_outputs(paths, membership, buckets, pairwise)
    print(
        "[ccusdt_tfi_mutual_exclusion] "
        f"unique_entries={len(membership)} buckets={len(buckets)} pairwise={len(pairwise)} wrote={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
