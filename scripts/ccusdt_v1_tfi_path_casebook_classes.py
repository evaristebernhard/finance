#!/usr/bin/env python
"""Path casebook classes for CCUSDT V1 TFI entries.

This pass treats a "case" as a path mechanism, not as a losing label.
Profitable entries can therefore belong to the same case class as losing
entries if the release/decay geometry is the same.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260519_ccusdt_v1_tfi_path_casebook_v1"
GUARDRAIL = "research_only_path_casebook_no_execution_recommendation"
DEFAULT_INPUT = (
    "date/"
    "ccusdt_v1_tfi_release_decay_paths_"
    "20260518_ccusdt_v1_tfi_release_decay_factor_v1.csv"
)

EPS = 1e-9


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument("--run-tag", default=RUN_TAG)
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def fmt(value: Any, digits: int = 4) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_table(df: pd.DataFrame, columns: list[str], digits: int = 4) -> str:
    if df.empty:
        return "_empty_"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = []
    for _, row in df[columns].iterrows():
        rows.append("| " + " | ".join(fmt(row[col], digits) for col in columns) + " |")
    return "\n".join([header, sep, *rows])


def add_path_geometry(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for horizon in [1, 3, 5, 10, 20, 60]:
        out[f"R{horizon}"] = out[f"final_{horizon}s_bps"]
        out[f"H{horizon}"] = out[f"mfe_{horizon}s_bps"]
        out[f"D{horizon}"] = out[f"decay_{horizon}s_bps"]
        out[f"E{horizon}"] = out[f"R{horizon}"] / (out[f"H{horizon}"].abs() + EPS)

    out["tau_H60"] = out["t_mfe_60s_sec"]
    out["A60"] = 60.0 - out["tau_H60"]
    out["release_speed_60"] = out["H60"] / (out["tau_H60"] + EPS)
    out["decay_speed_after_peak_60"] = out["D60"] / (out["A60"].clip(lower=0.1))
    out["delta_H_20_60"] = out["H60"] - out["H20"]
    out["weighted_gross60"] = out["target_exposure"] * out["R60"]
    out["weighted_stored_net60"] = out["target_exposure"] * out["net"]
    out["gross60_positive"] = out["R60"] > 0
    return out


def classify_cases(df: pd.DataFrame) -> pd.DataFrame:
    out = add_path_geometry(df)
    case = pd.Series("00_non_case", index=out.index, dtype=object)
    rule = pd.Series("residual path; useful as control", index=out.index, dtype=object)
    read = pd.Series(
        "no obvious release/decay pathology under the simple rules",
        index=out.index,
        dtype=object,
    )

    no_release = out["H60"] < 3.0
    case.loc[no_release] = "01_no_release_flat"
    rule.loc[no_release] = "H60 < 3"
    read.loc[no_release] = "no meaningful favorable release inside 60s"

    large_plateau = (
        (case == "00_non_case")
        & (out["H20"] >= 10.0)
        & (out["E20"] >= 0.75)
        & (out["tau_H60"] <= 20.0)
        & (out["D60"] >= 10.0)
    )
    case.loc[large_plateau] = "03_large_release_plateau_decay"
    rule.loc[large_plateau] = "H20 >= 10, E20 >= 0.75, tau_H60 <= 20, D60 >= 10"
    read.loc[large_plateau] = "large release is still present by 20s, then decays before 60s"

    late_release = (
        (case == "00_non_case")
        & (out["H60"] >= 5.0)
        & (out["tau_H60"] >= 20.0)
        & (out["D60"] >= 8.0)
    )
    case.loc[late_release] = "04_late_release_collapse"
    rule.loc[late_release] = "H60 >= 5, tau_H60 >= 20, D60 >= 8"
    read.loc[late_release] = "meaningful peak arrives late, but much is given back by 60s"

    fast_release = (
        (case == "00_non_case")
        & (out["H60"] >= 4.0)
        & (out["tau_H60"] <= 5.0)
        & (out["D60"] >= 8.0)
    )
    case.loc[fast_release] = "02_fast_release_reversal"
    rule.loc[fast_release] = "H60 >= 4, tau_H60 <= 5, D60 >= 8"
    read.loc[fast_release] = "early favorable release is real but reverses hard within 60s"

    out["path_case_class"] = case
    out["path_case_rule"] = rule
    out["path_case_read"] = read
    out["is_path_case"] = out["path_case_class"] != "00_non_case"
    return out


def pct(series: pd.Series) -> float:
    if len(series) == 0:
        return np.nan
    return float(series.mean())


def summarize_class(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("path_case_class", dropna=False)
    summary = grouped.agg(
        entries=("entry_row", "size"),
        gross60_positive_entries=("gross60_positive", "sum"),
        gross60_weighted_total=("weighted_gross60", "sum"),
        stored_net60_weighted_total=("weighted_stored_net60", "sum"),
        R60_mean=("R60", "mean"),
        R60_median=("R60", "median"),
        H60_mean=("H60", "mean"),
        tau_H60_mean=("tau_H60", "mean"),
        D60_mean=("D60", "mean"),
        E60_median=("E60", "median"),
        exposure_mean=("target_exposure", "mean"),
        exposure_max=("target_exposure", "max"),
        worst_weighted_gross60=("weighted_gross60", "min"),
        best_weighted_gross60=("weighted_gross60", "max"),
    ).reset_index()
    summary["entry_share"] = summary["entries"] / len(df)
    summary["gross60_positive_rate"] = (
        summary["gross60_positive_entries"] / summary["entries"]
    )
    order = [
        "path_case_class",
        "entries",
        "entry_share",
        "gross60_positive_entries",
        "gross60_positive_rate",
        "gross60_weighted_total",
        "stored_net60_weighted_total",
        "R60_mean",
        "R60_median",
        "H60_mean",
        "tau_H60_mean",
        "D60_mean",
        "E60_median",
        "exposure_mean",
        "exposure_max",
        "worst_weighted_gross60",
        "best_weighted_gross60",
    ]
    return summary[order].sort_values("path_case_class")


def summarize_group(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    out = (
        df.groupby(group_cols, dropna=False)
        .agg(
            entries=("entry_row", "size"),
            path_cases=("is_path_case", "sum"),
            gross60_positive_entries=("gross60_positive", "sum"),
            gross60_weighted_total=("weighted_gross60", "sum"),
            R60_mean=("R60", "mean"),
            H60_mean=("H60", "mean"),
            D60_mean=("D60", "mean"),
            exposure_mean=("target_exposure", "mean"),
        )
        .reset_index()
    )
    out["gross60_positive_rate"] = out["gross60_positive_entries"] / out["entries"]
    out["path_case_rate"] = out["path_cases"] / out["entries"]
    return out


def build_examples(df: pd.DataFrame, per_side: int = 5) -> pd.DataFrame:
    frames = []
    for case_name, group in df[df["is_path_case"]].groupby("path_case_class"):
        worst = group.nsmallest(per_side, "weighted_gross60").copy()
        worst["example_side"] = "worst_weighted_gross60"
        best = group.nlargest(per_side, "weighted_gross60").copy()
        best["example_side"] = "best_weighted_gross60"
        frames.extend([worst, best])
    if not frames:
        return pd.DataFrame()
    examples = pd.concat(frames, ignore_index=True)
    cols = [
        "path_case_class",
        "example_side",
        "date",
        "entry_row",
        "cell",
        "direction_label",
        "target_exposure",
        "R5",
        "R10",
        "R20",
        "R60",
        "H60",
        "tau_H60",
        "D60",
        "E60",
        "weighted_gross60",
        "weighted_stored_net60",
        "path_case_rule",
        "path_case_read",
    ]
    return examples[cols].sort_values(
        ["path_case_class", "example_side", "weighted_gross60"],
        ascending=[True, True, True],
    )


def write_report(
    *,
    out_path: Path,
    input_path: Path,
    events: pd.DataFrame,
    class_summary: pd.DataFrame,
    daily_summary: pd.DataFrame,
    cell_summary: pd.DataFrame,
    examples: pd.DataFrame,
    run_tag: str,
) -> None:
    case_only = events[events["is_path_case"]]
    total_entries = len(events)
    total_cases = len(case_only)
    total_weighted_gross = events["weighted_gross60"].sum()
    case_weighted_gross = case_only["weighted_gross60"].sum()
    non_case_weighted_gross = events.loc[
        ~events["is_path_case"], "weighted_gross60"
    ].sum()

    class_cols = [
        "path_case_class",
        "entries",
        "entry_share",
        "gross60_positive_rate",
        "gross60_weighted_total",
        "R60_mean",
        "H60_mean",
        "tau_H60_mean",
        "D60_mean",
        "exposure_mean",
        "worst_weighted_gross60",
        "best_weighted_gross60",
    ]
    daily_cols = [
        "date",
        "path_case_class",
        "entries",
        "gross60_positive_rate",
        "gross60_weighted_total",
        "R60_mean",
        "H60_mean",
        "D60_mean",
    ]
    cell_cols = [
        "path_case_class",
        "cell",
        "entries",
        "gross60_positive_rate",
        "gross60_weighted_total",
        "R60_mean",
        "H60_mean",
        "D60_mean",
        "exposure_mean",
    ]
    example_cols = [
        "path_case_class",
        "example_side",
        "date",
        "entry_row",
        "cell",
        "direction_label",
        "target_exposure",
        "R5",
        "R10",
        "R20",
        "R60",
        "H60",
        "tau_H60",
        "D60",
        "weighted_gross60",
    ]

    top_daily = daily_summary[daily_summary["path_case_class"] != "00_non_case"].copy()
    top_daily = top_daily.sort_values("gross60_weighted_total").head(20)
    cell_view = cell_summary[cell_summary["path_case_class"] != "00_non_case"].copy()
    cell_view = cell_view.sort_values(["path_case_class", "cell"])

    lines = [
        "# CCUSDT V1 TFI Path Casebook Classes",
        "",
        f"Status: `{run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        f"Input: `{input_path.as_posix()}`.",
        "",
        "## Purpose",
        "",
        "This report classifies entries by path mechanism, not by whether the",
        "60s terminal result is negative. A profitable entry can still be a",
        "case if it has the same release/decay geometry as a losing entry.",
        "",
        "The path object is:",
        "",
        "$$",
        r"R_i(t)=10^4s_i\log\frac{M_{t_i+t}}{M_{t_i}},",
        "$$",
        "",
        "with:",
        "",
        "$$",
        r"H_i(t)=\max_{0<u\le t}R_i(u),\quad",
        r"D_i(t)=H_i(t)-R_i(t),\quad",
        r"E_i(t)=\frac{R_i(t)}{H_i(t)+\epsilon}.",
        "$$",
        "",
        "## Rules",
        "",
        "The classes are deliberately simple and mutually exclusive:",
        "",
        r"1. `01_no_release_flat`: \(H_{60}<3\).",
        "2. `03_large_release_plateau_decay`: "
        r"\(H_{20}\ge10,\ E_{20}\ge0.75,\ \tau_H\le20,\ D_{60}\ge10\).",
        "3. `04_late_release_collapse`: "
        r"\(H_{60}\ge5,\ \tau_H\ge20,\ D_{60}\ge8\).",
        "4. `02_fast_release_reversal`: "
        r"\(H_{60}\ge4,\ \tau_H\le5,\ D_{60}\ge8\).",
        "",
        "Priority is the order above. The plateau class is checked before the",
        "fast-release class so that large moves that remain alive through 20s",
        "are not mixed with immediate flash reversals.",
        "",
        "## Headline",
        "",
        f"Total entries: `{total_entries}`.",
        "",
        f"Path cases: `{total_cases}` "
        f"({total_cases / total_entries:.2%} of entries).",
        "",
        f"Weighted gross 60s total, all entries: `{total_weighted_gross:.4f}`.",
        "",
        f"Weighted gross 60s total, path cases: `{case_weighted_gross:.4f}`.",
        "",
        f"Weighted gross 60s total, non-cases: `{non_case_weighted_gross:.4f}`.",
        "",
        "The weighted gross metric uses the stored `target_exposure` and raw",
        r"\(R_{60}\). It is a path-severity lens, not a fresh sizing proposal.",
        "",
        "## Class Summary",
        "",
        markdown_table(class_summary, class_cols),
        "",
        "## Worst Daily Case Buckets",
        "",
        markdown_table(top_daily[daily_cols], daily_cols),
        "",
        "## Case Classes By Cell",
        "",
        markdown_table(cell_view[cell_cols], cell_cols),
        "",
        "## Examples",
        "",
        "Each class keeps both the worst and best weighted examples. The best",
        "examples are important because they show that the class is a mechanism,",
        "not just a losing-label filter.",
        "",
        markdown_table(examples[example_cols], example_cols),
        "",
        "## Interpretation",
        "",
        "- `01_no_release_flat` is mostly an entry/size problem: the entry did not",
        "  receive a meaningful favorable price release within 60s.",
        "- `02_fast_release_reversal` is the closest to the canonical flash/transient",
        "  pathology: peak arrives very early and the terminal giveback is large.",
        "- `03_large_release_plateau_decay` is not simply bad. It can be positive",
        "  in aggregate, but it shows the exact window where profit has already",
        "  been released and then remains exposed to reversal.",
        "- `04_late_release_collapse` contains many profitable entries. The issue is",
        "  not entry invalidity; it is that fixed 60s holding mixes late peak",
        "  capture with late giveback.",
        "",
        "The next useful programming step is not a larger model. It is to test",
        "whether simple path actions map to these classes: reduce no-release",
        "exposure, protect fast transients quickly, and harvest plateau/late",
        "release after the peak stops improving.",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_path = resolve_path(args.input)
    date_dir = resolve_path(args.date_dir)
    doc_dir = resolve_path(args.doc_dir)
    date_dir.mkdir(parents=True, exist_ok=True)
    doc_dir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(input_path)
    events = classify_cases(raw)
    class_summary = summarize_class(events)
    daily_summary = summarize_group(events, ["date", "path_case_class"])
    cell_summary = summarize_group(events, ["path_case_class", "cell"])
    examples = build_examples(events)

    event_cols = [
        "date",
        "fold",
        "entry_row",
        "entry_event_index",
        "matched_event_index",
        "cell",
        "direction_label",
        "target_exposure",
        "R1",
        "R3",
        "R5",
        "R10",
        "R20",
        "R60",
        "H1",
        "H3",
        "H5",
        "H10",
        "H20",
        "H60",
        "tau_H60",
        "A60",
        "D10",
        "D20",
        "D60",
        "E10",
        "E20",
        "E60",
        "release_speed_60",
        "decay_speed_after_peak_60",
        "delta_H_20_60",
        "weighted_gross60",
        "weighted_stored_net60",
        "gross60_positive",
        "path_case_class",
        "path_case_rule",
        "path_case_read",
        "is_path_case",
        "frames_q_bin",
        "delta10_bin",
        "energy10_bin",
        "z10_bin",
        "loss5_bin",
        "quality_side",
        "entry_quality_class",
        "dominant_latent_state",
        "closed10_score_abs",
        "closed10_energy",
        "signed_tfi_mean_5_20s",
        "signed_ofi_mean_5_20s",
        "signed_mlofi5_mean_5_20s",
    ]
    existing_event_cols = [col for col in event_cols if col in events.columns]

    event_path = date_dir / f"ccusdt_v1_tfi_path_casebook_events_{args.run_tag}.csv"
    class_path = date_dir / f"ccusdt_v1_tfi_path_casebook_class_summary_{args.run_tag}.csv"
    daily_path = date_dir / f"ccusdt_v1_tfi_path_casebook_daily_{args.run_tag}.csv"
    cell_path = date_dir / f"ccusdt_v1_tfi_path_casebook_cell_summary_{args.run_tag}.csv"
    examples_path = date_dir / f"ccusdt_v1_tfi_path_casebook_examples_{args.run_tag}.csv"
    report_path = doc_dir / f"v1-tfi-path-casebook-{args.run_tag}.md"

    events[existing_event_cols].to_csv(event_path, index=False)
    class_summary.to_csv(class_path, index=False)
    daily_summary.to_csv(daily_path, index=False)
    cell_summary.to_csv(cell_path, index=False)
    examples.to_csv(examples_path, index=False)

    write_report(
        out_path=report_path,
        input_path=input_path,
        events=events,
        class_summary=class_summary,
        daily_summary=daily_summary,
        cell_summary=cell_summary,
        examples=examples,
        run_tag=args.run_tag,
    )

    print(f"wrote {event_path}")
    print(f"wrote {class_path}")
    print(f"wrote {daily_path}")
    print(f"wrote {cell_path}")
    print(f"wrote {examples_path}")
    print(f"wrote {report_path}")
    print(class_summary.to_string(index=False))


if __name__ == "__main__":
    main()
