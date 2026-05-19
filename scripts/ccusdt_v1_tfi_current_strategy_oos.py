#!/usr/bin/env python
"""Apply locked CCUSDT V1 TFI current strategy variants to one OOS day.

This is a small evaluation harness, not a new optimizer. It uses:

1. pretrade-scored entries from the existing strict prequential scorer;
2. the existing small path manager policy;
3. the existing q70 post-exit watcher;
4. the existing 3x capacity allocator.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ccusdt_v1_tfi_capacity_manager import (
    assign_fifo_clip,
    assign_global_scale,
    assign_raw,
    build_legs,
    summarize_assignment,
)
from ccusdt_v1_tfi_post_exit_watcher import (
    WATCHER_POLICIES,
    WatcherPaths,
    build_watcher_events,
)
from ccusdt_v1_tfi_post_exit_retrigger_diagnostic import load_manager_events, resolve_path
from ccusdt_v1_tfi_small_path_manager import simulate_entries


RUN_TAG = "20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1"
GUARDRAIL = "research_only_locked_strategy_oos_no_execution_recommendation"
OOS_DATE = "2026-05-18"
PANEL_RUN_TAG = "20260519_ccusdt_fixed_factors_oos_day20260518_v1"
SCORED_ENTRIES = (
    "ccusdt_v1_tfi_pretrade_scored_entries_"
    "20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.csv"
)
PRIMARY_MANAGER = "pm_11_drawdown_h4_peakguard"
MAIN_WATCHER = "watcher_q70_absorb_reclaim2"
MAX_LEVERAGE = 3.0
PRESSURES = [0.0, 1.0, 2.0]

VARIANTS = {
    "clean_q70_low_concurrency": {
        "00_none": 1.25,
        "10_r5_only": 0.75,
        "01_frames_only": 0.0,
        "11_r5_frames": 0.75,
    },
    "anchor_q70_old_shape": {
        "00_none": 1.0,
        "10_r5_only": 0.75,
        "01_frames_only": 0.25,
        "11_r5_frames": 4.0,
    },
    "high_gamma_q70_capacity": {
        "00_none": 1.25,
        "10_r5_only": 2.0,
        "01_frames_only": 1.0,
        "11_r5_frames": 5.0,
    },
}


@dataclass(frozen=True)
class Paths:
    date_dir: Path
    doc_dir: Path
    panel_root: Path
    panel_run_tag: str
    scored_entries_name: str
    run_tag: str
    symbol: str

    @property
    def scored_entries_csv(self) -> Path:
        return self.date_dir / self.scored_entries_name

    @property
    def manager_events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_manager_events_{self.run_tag}.csv"

    @property
    def watcher_events_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_watcher_events_{self.run_tag}.csv"

    @property
    def unit_entries_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_unit_entries_{self.run_tag}.csv"

    @property
    def summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_summary_{self.run_tag}.csv"

    @property
    def cell_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_cell_{self.run_tag}.csv"

    @property
    def clipped_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_clipped_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_current_oos_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-current-strategy-oos-day20260518-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument("--panel-root", default="data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel")
    parser.add_argument("--panel-run-tag", default=PANEL_RUN_TAG)
    parser.add_argument("--scored-entries", default=SCORED_ENTRIES)
    parser.add_argument("--oos-date", default=OOS_DATE)
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--max-leverage", type=float, default=MAX_LEVERAGE)
    return parser.parse_args()


def fmt(value: Any, digits: int = 4) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return ""
    return f"{v:.{digits}f}"


def markdown_table(df: pd.DataFrame, cols: list[str], max_rows: int = 40) -> str:
    cols = [c for c in cols if c in df.columns]
    if df.empty or not cols:
        return "_empty_"
    view = df.loc[:, cols].head(max_rows).copy()
    for col in view.columns:
        if pd.api.types.is_float_dtype(view[col]):
            view[col] = view[col].map(lambda x: fmt(x))
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def load_scored_entries(paths: Paths, oos_date: str) -> pd.DataFrame:
    scored = pd.read_csv(paths.scored_entries_csv)
    scored = scored[scored["date"].astype(str).eq(oos_date)].copy()
    if scored.empty:
        raise ValueError(f"no scored entries for {oos_date} in {paths.scored_entries_csv}")
    for col in [
        "entry_row",
        "entry_event_index",
        "entry_ts",
        "label_available_ts",
        "weight",
        "gross",
        "net",
        "direction",
    ]:
        scored[col] = pd.to_numeric(scored[col], errors="coerce")
    scored["entry_row"] = scored["entry_row"].astype("int64")
    scored["entry_event_index"] = scored["entry_event_index"].astype("int64")
    scored["cell"] = np.select(
        [
            scored["gate_r_n5"].astype(bool) & scored["gate_frames_q90"].astype(bool),
            scored["gate_r_n5"].astype(bool) & ~scored["gate_frames_q90"].astype(bool),
            ~scored["gate_r_n5"].astype(bool) & scored["gate_frames_q90"].astype(bool),
        ],
        ["11_r5_frames", "10_r5_only", "01_frames_only"],
        default="00_none",
    )
    scored["direction_label"] = np.where(scored["direction"] > 0, "long", "short")
    scored["base_weight"] = pd.to_numeric(scored["weight"], errors="coerce").fillna(0.0)
    return scored.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)


def manager_input(scored: pd.DataFrame) -> pd.DataFrame:
    out = scored[
        [
            "date",
            "fold",
            "entry_row",
            "entry_event_index",
            "cell",
            "direction_label",
            "base_weight",
            "gross",
        ]
    ].copy()
    out["matched_event_index"] = out["entry_event_index"]
    out["target_exposure"] = out["base_weight"]
    return out


def build_unit_entries(scored: pd.DataFrame, manager_events: pd.DataFrame, watcher_events: pd.DataFrame) -> pd.DataFrame:
    out = scored[
        [
            "date",
            "entry_row",
            "entry_event_index",
            "entry_ts",
            "label_available_ts",
            "cost_mode",
            "cell",
            "base_weight",
            "net",
            "gross",
            "direction",
            "direction_label",
        ]
    ].copy()
    out["baseline_gross60"] = out["gross"]
    out["policy_gross"] = out["gross"]
    out["exit_sec"] = 60.0
    out["path_case_class"] = "not_rebuilt"
    out["path_overlay_source"] = "fixed60_fallback"
    primary = manager_events[manager_events["policy"].eq(PRIMARY_MANAGER)].copy()
    keep = [
        "date",
        "entry_row",
        "policy_gross",
        "baseline_gross60",
        "exit_sec",
        "path_case_class",
    ]
    primary = primary[keep].rename(
        columns={
            "policy_gross": "manager_policy_gross",
            "baseline_gross60": "manager_baseline_gross60",
            "exit_sec": "manager_exit_sec",
            "path_case_class": "manager_path_case_class",
        }
    )
    out = out.merge(primary, on=["date", "entry_row"], how="left", validate="one_to_one")
    has_manager = out["manager_policy_gross"].notna()
    out.loc[has_manager, "policy_gross"] = out.loc[has_manager, "manager_policy_gross"]
    out.loc[has_manager, "baseline_gross60"] = out.loc[has_manager, "manager_baseline_gross60"]
    out.loc[has_manager, "exit_sec"] = out.loc[has_manager, "manager_exit_sec"]
    out.loc[has_manager, "path_case_class"] = out.loc[has_manager, "manager_path_case_class"]
    out.loc[has_manager, "path_overlay_source"] = "path_manager_rebuilt"
    out["entry_end_ts"] = out["entry_ts"] + out["exit_sec"].clip(lower=0, upper=60) * 1_000_000.0

    triggered = watcher_events[watcher_events["watch_triggered"].astype(str).str.lower().eq("true")].copy()
    if triggered.empty:
        pivot = pd.DataFrame(columns=["date", "entry_row"])
    else:
        pivot = triggered.pivot_table(
            index=["date", "entry_row"],
            columns="watcher_policy",
            values=["watch_final_pnl", "watch_entry_sec", "watch_mode"],
            aggfunc="first",
        )
        pivot.columns = [f"{a}_{b}" for a, b in pivot.columns.to_flat_index()]
        pivot = pivot.reset_index()
    out = out.merge(pivot, on=["date", "entry_row"], how="left")
    for name in ["impulse_only", MAIN_WATCHER, "watcher_q65_absorb_reclaim2"]:
        pnl_col = f"watch_final_pnl_{name}"
        sec_col = f"watch_entry_sec_{name}"
        mode_col = f"watch_mode_{name}"
        if pnl_col not in out:
            out[pnl_col] = 0.0
            out[sec_col] = np.nan
            out[mode_col] = "none"
        out[pnl_col] = pd.to_numeric(out[pnl_col], errors="coerce").fillna(0.0)
        out[sec_col] = pd.to_numeric(out[sec_col], errors="coerce")
        out[mode_col] = out[mode_col].fillna("none")
        out[f"watch_trigger_{name}"] = out[pnl_col].abs() > 0
        out[f"watch_start_ts_{name}"] = out["entry_ts"] + (
            out["exit_sec"].clip(lower=0, upper=60).fillna(60) + out[sec_col].fillna(np.nan)
        ) * 1_000_000.0
        out[f"watch_end_ts_{name}"] = out["label_available_ts"]
    return out.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)


def variant_series(name: str, gammas: dict[str, float], pressure: float) -> pd.Series:
    return pd.Series(
        {
            "strategy": "manager_plus_q70_watcher",
            "variant": name,
            "pressure_bps": pressure,
            "gamma00_none": gammas["00_none"],
            "gamma10_r5_only": gammas["10_r5_only"],
            "gamma01_frames_only": gammas["01_frames_only"],
            "gamma11_r5_frames": gammas["11_r5_frames"],
        }
    )


def exact_simple_bp_units(assigned: pd.DataFrame) -> float:
    exposure = pd.to_numeric(assigned["actual_exposure"], errors="coerce").to_numpy(dtype=float)
    unit = pd.to_numeric(assigned["unit"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(exposure) & np.isfinite(unit)
    return float(np.sum(exposure[ok] * (np.exp(unit[ok] / 10_000.0) - 1.0) * 10_000.0))


def evaluate(unit_entries: pd.DataFrame, max_leverage: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    cell_rows: list[pd.DataFrame] = []
    clipped_rows: list[pd.DataFrame] = []
    policies = [
        assign_raw,
        assign_global_scale,
        lambda legs, lev: assign_fifo_clip(legs, lev, priority_order=False),
        lambda legs, lev: assign_fifo_clip(legs, lev, priority_order=True),
    ]
    for name, gammas in VARIANTS.items():
        for pressure in PRESSURES:
            variant = variant_series(name, gammas, pressure)
            legs = build_legs(unit_entries, variant)
            global_total = np.nan
            local_rows = []
            for assign in policies:
                assigned = assign(legs, max_leverage)
                row, _daily, cell, clipped = summarize_assignment(assigned, variant=variant, max_leverage=max_leverage)
                row["exact_simple_bp_units"] = exact_simple_bp_units(
                    assigned.assign(
                        actual_pnl=assigned["actual_exposure"] * assigned["unit"],
                    )
                )
                row["approx_account_log_return"] = row["actual_total"] / 10_000.0
                row["approx_account_simple_return"] = math.exp(row["approx_account_log_return"]) - 1.0
                if row["capacity_policy"] == "global_downscale":
                    global_total = row["actual_total"]
                local_rows.append(row)
                cell["strategy"] = variant["strategy"]
                cell["variant"] = name
                cell["pressure_bps"] = pressure
                cell_rows.append(cell)
                clipped["strategy"] = variant["strategy"]
                clipped["variant"] = name
                clipped["pressure_bps"] = pressure
                clipped["capacity_policy"] = row["capacity_policy"]
                clipped_rows.append(clipped.head(25))
            for row in local_rows:
                row["actual_vs_global_gain"] = (
                    row["actual_total"] - global_total if np.isfinite(global_total) else np.nan
                )
            rows.extend(local_rows)
    return (
        pd.DataFrame(rows),
        pd.concat(cell_rows, ignore_index=True) if cell_rows else pd.DataFrame(),
        pd.concat(clipped_rows, ignore_index=True) if clipped_rows else pd.DataFrame(),
    )


def write_report(paths: Paths, summary: pd.DataFrame, unit_entries: pd.DataFrame, watcher_events: pd.DataFrame) -> None:
    main = summary[
        summary["variant"].eq("clean_q70_low_concurrency")
        & summary["capacity_policy"].isin(["raw_no_cap", "global_downscale", "online_fifo_clip", "priority_arrival_clip"])
    ].sort_values(["pressure_bps", "capacity_policy"])
    c0 = summary[
        summary["pressure_bps"].eq(0)
        & summary["capacity_policy"].isin(["online_fifo_clip", "global_downscale"])
    ].sort_values(["variant", "capacity_policy"])
    counts = unit_entries.groupby("cell").agg(
        entries=("entry_row", "size"),
        base_exposure=("base_weight", "sum"),
        fixed60_gross=("gross", "sum"),
        manager_gross=("policy_gross", "sum"),
    ).reset_index()
    triggers = watcher_events[watcher_events["watch_triggered"].astype(str).str.lower().eq("true")]
    lines = [
        "# CCUSDT V1 TFI Current Strategy OOS",
        "",
        f"Status: `{paths.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        f"OOS date: `{OOS_DATE}`.",
        "",
        "This applies locked strategy variants to the new OOS day. It does not",
        "optimize gamma or thresholds on 2026-05-18.",
        "",
        "## Entry Universe",
        "",
        markdown_table(counts, ["cell", "entries", "base_exposure", "fixed60_gross", "manager_gross"]),
        "",
        f"Watcher triggered rows: `{len(triggers)}`.",
        "",
        "## Cleaner q70 Result",
        "",
        markdown_table(
            main,
            [
                "pressure_bps",
                "capacity_policy",
                "desired_total",
                "actual_total",
                "exact_simple_bp_units",
                "approx_account_simple_return",
                "actual_vs_global_gain",
                "desired_max_concurrent",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
                "leg_worst",
            ],
        ),
        "",
        "## C0 Variant Comparison",
        "",
        markdown_table(
            c0,
            [
                "variant",
                "capacity_policy",
                "desired_total",
                "actual_total",
                "exact_simple_bp_units",
                "approx_account_simple_return",
                "actual_vs_global_gain",
                "desired_max_concurrent",
                "actual_max_concurrent",
                "clipped_legs",
                "skipped_legs",
                "leg_worst",
            ],
        ),
        "",
        "## Interpretation",
        "",
        "- `actual_total` is weighted log-bp units, i.e. sum of exposure times log-bps.",
        "- `exact_simple_bp_units` converts each leg by `exp(unit/10000)-1` before weighting.",
        "- `approx_account_simple_return` treats the total log-bp units as if it were an account log return; it is an intuition aid, not a margin-account simulator.",
        "- `online_fifo_clip` is the first implementable 3x capacity model; `global_downscale` is the conservative lower bound.",
        "",
        "## Outputs",
        "",
        f"- `{paths.summary_csv}`",
        f"- `{paths.unit_entries_csv}`",
        f"- `{paths.manager_events_csv}`",
        f"- `{paths.watcher_events_csv}`",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = Paths(
        date_dir=resolve_path(args.date_dir),
        doc_dir=resolve_path(args.doc_dir),
        panel_root=resolve_path(args.panel_root),
        panel_run_tag=args.panel_run_tag,
        scored_entries_name=args.scored_entries,
        run_tag=args.run_tag,
        symbol=args.symbol,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    scored = load_scored_entries(paths, args.oos_date)
    manager_events, _manager_days = simulate_entries(
        manager_input(scored),
        paths.panel_root,
        paths.panel_run_tag,
        paths.symbol,
    )
    manager_events.to_csv(paths.manager_events_csv, index=False)

    watcher_paths = WatcherPaths(
        date_dir=paths.date_dir,
        doc_dir=paths.doc_dir,
        panel_root=paths.panel_root,
        panel_run_tag=paths.panel_run_tag,
        symbol=paths.symbol,
        run_tag=paths.run_tag,
        manager_events_name=paths.manager_events_csv.name,
    )
    drawdown_events = load_manager_events(watcher_paths, PRIMARY_MANAGER)
    watcher_events = build_watcher_events(
        drawdown_events,
        watcher_paths,
        WATCHER_POLICIES,
        obs_sec=5.0,
        impulse_qi_threshold=0.70,
        impulse_reclaim_threshold=1.0,
    )
    watcher_events.to_csv(paths.watcher_events_csv, index=False)

    unit_entries = build_unit_entries(scored, manager_events, watcher_events)
    unit_entries.to_csv(paths.unit_entries_csv, index=False)
    summary, cell, clipped = evaluate(unit_entries, float(args.max_leverage))
    summary = summary.sort_values(["pressure_bps", "variant", "capacity_policy"]).reset_index(drop=True)
    summary.to_csv(paths.summary_csv, index=False)
    cell.to_csv(paths.cell_csv, index=False)
    clipped.to_csv(paths.clipped_csv, index=False)
    payload = {
        "run_tag": paths.run_tag,
        "guardrail": GUARDRAIL,
        "oos_date": args.oos_date,
        "panel_run_tag": paths.panel_run_tag,
        "scored_entries": str(paths.scored_entries_csv),
        "entries": int(len(unit_entries)),
        "watcher_triggers": int(watcher_events["watch_triggered"].astype(bool).sum()) if not watcher_events.empty else 0,
        "outputs": {
            "summary_csv": str(paths.summary_csv),
            "cell_csv": str(paths.cell_csv),
            "clipped_csv": str(paths.clipped_csv),
            "unit_entries_csv": str(paths.unit_entries_csv),
            "manager_events_csv": str(paths.manager_events_csv),
            "watcher_events_csv": str(paths.watcher_events_csv),
            "report_md": str(paths.report_md),
        },
    }
    paths.summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(paths, summary, unit_entries, watcher_events)
    main_row = summary[
        summary["variant"].eq("clean_q70_low_concurrency")
        & summary["pressure_bps"].eq(0)
        & summary["capacity_policy"].eq("online_fifo_clip")
    ].iloc[0]
    print(
        f"[ccusdt_current_oos] entries={len(unit_entries)} "
        f"watcher_triggers={payload['watcher_triggers']} "
        f"clean_q70_c0_online={main_row['actual_total']:.4f} "
        f"simple_bp_units={main_row['exact_simple_bp_units']:.4f} "
        f"approx_simple_return={main_row['approx_account_simple_return']:.6f} "
        f"report={paths.report_md}",
        flush=True,
    )


if __name__ == "__main__":
    main()
