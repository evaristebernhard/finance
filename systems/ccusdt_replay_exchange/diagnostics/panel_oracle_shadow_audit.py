#!/usr/bin/env python
"""Panel-oracle audit for accurately translating the old CCUSDT four-cell TFI policy.

This diagnostic intentionally reads legacy fixed factor panel artifacts and
research CSVs. It is not a runtime strategy input. Its job is to prove whether
the old panel-clock entry universe, four-cell state, and weights can be
reproduced before building an online exchange-visible panel builder.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TRIGGERS = [
    "tfi_follow_flat",
    "tfi_short_flat",
    "tfi_long_flat",
    "tfi_short_stale25",
    "tfi_event_active",
]
KEY_COLS = ["fold", "date", "entry_row"]
TARGET_EXPECTED_COUNTS = {
    "2026-05-16": 261,
    "2026-05-17": 199,
    "2026-05-18": 304,
}
OOS_PANEL_RUN_TAGS = {
    "2026-05-16": "20260518_ccusdt_fixed_factors_oos_day20260516_v1",
    "2026-05-17": "20260518_ccusdt_fixed_factors_oos_day20260517_v1",
    "2026-05-18": "20260519_ccusdt_fixed_factors_oos_day20260518_v1",
}
REFERENCE_ALL = (
    "ccusdt_v1_tfi_pretrade_scored_entries_"
    "20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_oos_day20260518_v1.csv"
)
HIST_WARMUP_REFERENCE = (
    "ccusdt_v1_tfi_pretrade_scored_entries_"
    "20260519_ccusdt_v1_tfi_pretrade_identification_zero_fee_v1.csv"
)
US_PER_SECOND = 1_000_000
FIXED_EXIT_US = 60_000_000.0
EPS = 1e-12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--warmup-from", default="2026-05-04")
    parser.add_argument("--run-prefix", default="panel_oracle_shadow_audit")
    parser.add_argument("--entry-bucket-sec", type=int, default=60)
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--cost-mode", choices=["zero_fee"], default="zero_fee")
    return parser.parse_args()


def date_range(start: str, end: str) -> list[str]:
    left = date.fromisoformat(start)
    right = date.fromisoformat(end)
    out: list[str] = []
    current = left
    while current <= right:
        out.append(current.isoformat())
        current += timedelta(days=1)
    return out


def import_legacy_modules(repo_root: Path) -> tuple[Any, Any, Any, Any]:
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import ccusdt_signal_path_math as signal_math
    import ccusdt_strategy_research as strategy_research
    import ccusdt_v1_tfi_momentum_conversion_math as conv
    import ccusdt_v1_tfi_oos_decay_check as oos_decay

    return signal_math, strategy_research, conv, oos_decay


def finite_quantile(values: pd.Series | np.ndarray, q: float) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    arr = arr[np.isfinite(arr)]
    return float(np.quantile(arr, q)) if len(arr) else np.nan


def float_or_nan(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out if np.isfinite(out) else np.nan


def bool_value(raw: Any) -> bool:
    return str(raw).strip().lower() in {"true", "1", "yes"}


def cell_from_gates(a_r5: bool, b_frames: bool) -> str:
    if a_r5 and b_frames:
        return "11_r5_frames"
    if a_r5:
        return "10_r5_only"
    if b_frames:
        return "01_frames_only"
    return "00_none"


def membership_set_from_flags(row: pd.Series) -> str:
    parts = [trigger for trigger in TRIGGERS if bool(row.get(trigger, False))]
    return "+".join(parts) if parts else "none"


def build_membership_from_trigger_entries(entries: pd.DataFrame, segment: str) -> pd.DataFrame:
    entries = entries[entries["trigger_class"].isin(TRIGGERS)].copy()
    base_cols = KEY_COLS + [
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
    for col in base_cols:
        if col not in entries:
            entries[col] = np.nan
    base = entries.sort_values(KEY_COLS + ["trigger_class"]).drop_duplicates(KEY_COLS, keep="first")
    base = base[base_cols].copy()
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


def load_reference(repo_root: Path, name: str) -> pd.DataFrame:
    path = repo_root / "date" / name
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def load_weight_map(conv: Any) -> tuple[list[str], dict[str, float]]:
    eligible, base_weight_map = conv.load_weights()
    return list(eligible), {str(key): float(value) for key, value in base_weight_map.items()}


def locked_overlay_threshold(repo_root: Path, eligible: list[str]) -> float:
    entries = pd.read_csv(
        repo_root
        / "date"
        / "ccusdt_v1_tail_stop_deep_dive_entries_20260517_ccusdt_tail_stop_deep_dive_v1.csv",
        usecols=KEY_COLS + ["frames_since_mid_change"],
    )
    membership = pd.read_csv(
        repo_root
        / "date"
        / "ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv",
        usecols=KEY_COLS + ["membership_set"],
    )
    work = membership[
        membership["fold"].eq("expanding_fold3")
        & membership["membership_set"].astype(str).isin(eligible)
    ].merge(entries, on=KEY_COLS, how="left")
    vals = pd.to_numeric(work["frames_since_mid_change"], errors="coerce").to_numpy(dtype="float64")
    vals = vals[np.isfinite(vals)]
    return float(np.quantile(vals, 0.90)) if len(vals) else np.nan


def generate_panel_oracle_oos_day(repo_root: Path, day: str, args: argparse.Namespace, modules: tuple[Any, Any, Any, Any]) -> pd.DataFrame:
    _signal_math, strategy_research, _conv, oos_decay = modules
    if day not in OOS_PANEL_RUN_TAGS:
        raise ValueError(f"no OOS panel run tag configured for {day}")
    paths = oos_decay.Paths(
        panel_root=repo_root / "data" / "ccusdt" / "v1" / "derived" / "ccusdt_v1_fixed_event_factor_panel",
        oos_source_run_tag=OOS_PANEL_RUN_TAGS[day],
        oos_date=day,
        date_dir=repo_root / "date",
        doc_dir=repo_root / "docs" / "markets" / "ccusdt",
        run_tag=f"panel_oracle_{day.replace('-', '')}",
        hist_entries=repo_root / oos_decay.HIST_ENTRIES,
        hist_buckets=repo_root / oos_decay.HIST_BUCKETS,
        hist_membership=repo_root / oos_decay.HIST_MEMBERSHIP,
        hist_scorecard=repo_root / oos_decay.HIST_SCORECARD,
        hist_weights=repo_root / oos_decay.HIST_WEIGHTS,
    )
    df = oos_decay.load_oos_panel(paths)
    thresholds = oos_decay.load_locked_trigger_thresholds(paths.hist_entries)
    trigger_entries = oos_decay.build_oos_entries(
        df,
        thresholds,
        timeout_sec=args.timeout_sec,
        entry_bucket_sec=args.entry_bucket_sec,
    )
    # The old zero-fee reference uses gross as net. Keep the original maker cost
    # columns for audit, but score the shadow lifecycle under C_fee=0.
    trigger_entries["source_fixed_net_maker_bps"] = pd.to_numeric(
        trigger_entries["fixed_net_maker_bps"], errors="coerce"
    )
    trigger_entries["source_fixed_cost_maker_bps"] = pd.to_numeric(
        trigger_entries["fixed_cost_maker_bps"], errors="coerce"
    )
    trigger_entries["fixed_net_maker_bps"] = pd.to_numeric(trigger_entries["fixed_gross_bps"], errors="coerce")
    trigger_entries["fixed_cost_maker_bps"] = 0.0
    membership = build_membership_from_trigger_entries(trigger_entries, f"OOS_{day.replace('-', '_')}")
    # Match the historical scored file convention.
    membership["fold"] = f"oos_day{day.replace('-', '')}"
    membership["cost_mode"] = "zero_fee"
    membership["net"] = pd.to_numeric(membership["fixed_gross_bps"], errors="coerce")
    membership["gross"] = pd.to_numeric(membership["fixed_gross_bps"], errors="coerce")
    membership["cost"] = 0.0
    membership["entry_ts"] = pd.to_numeric(membership["entry_local_timestamp"], errors="coerce")
    membership["label_available_ts"] = membership["entry_ts"] + FIXED_EXIT_US
    return membership.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)


def apply_weights_and_overlay(rows: pd.DataFrame, base_weight_map: dict[str, float], overlay_threshold: float) -> pd.DataFrame:
    out = rows.copy()
    out["base_weight"] = out["membership_set"].astype(str).map(base_weight_map).fillna(0.0).astype(float)
    out["overlay_boost"] = 0.0
    frames = pd.to_numeric(out["frames_since_mid_change"], errors="coerce")
    if np.isfinite(overlay_threshold):
        out.loc[out["base_weight"].gt(0.0) & frames.ge(overlay_threshold), "overlay_boost"] = 0.5
    out["weight"] = out["base_weight"] + out["overlay_boost"]
    out["weighted_net"] = out["weight"] * pd.to_numeric(out["net"], errors="coerce")
    return out


def recompute_prequential_r5(rows: pd.DataFrame, frame_q90: float) -> pd.DataFrame:
    work = rows.copy().sort_values(["entry_ts", "date", "entry_row"]).reset_index(drop=True)
    work["row_id"] = np.arange(len(work), dtype="int64")
    work["label_available_ts"] = pd.to_numeric(work["entry_ts"], errors="coerce") + FIXED_EXIT_US
    closed = work.sort_values(["label_available_ts", "entry_ts", "entry_row"]).reset_index(drop=True)
    close_ptr = 0
    available: list[int] = []
    by_id = work.set_index("row_id", drop=False)

    out: list[dict[str, Any]] = []
    for _, current in work.iterrows():
        entry_ts = float(current["entry_ts"])
        while close_ptr < len(closed) and float(closed.loc[close_ptr, "label_available_ts"]) < entry_ts:
            available.append(int(closed.loc[close_ptr, "row_id"]))
            close_ptr += 1
        window_ids = available[-5:]
        prev = by_id.loc[window_ids] if window_ids else pd.DataFrame(columns=work.columns)
        net = pd.to_numeric(prev.get("net", pd.Series(dtype=float)), errors="coerce").to_numpy(dtype="float64")
        net = net[np.isfinite(net)]
        pos = float(net[net > 0].sum()) if len(net) else 0.0
        neg = float(net[net < 0].sum()) if len(net) else 0.0
        r5 = pos / abs(neg) if abs(neg) > EPS else np.nan
        item = current.to_dict()
        item["roll5_count"] = float(len(prev))
        item["roll5_pos_abs_ratio"] = r5
        item["gate_r_n5"] = bool(np.isfinite(r5) and r5 >= 1.0)
        item["gate_frames_q90"] = bool(float_or_nan(item.get("frames_since_mid_change")) >= frame_q90)
        item["cell"] = cell_from_gates(bool(item["gate_r_n5"]), bool(item["gate_frames_q90"]))
        out.append(item)
    return pd.DataFrame(out)


def reference_cell(row: pd.Series) -> str:
    return cell_from_gates(bool_value(row.get("gate_r_n5")), bool_value(row.get("gate_frames_q90")))


def comparable_key(row: pd.Series) -> tuple[str, int]:
    return str(row["date"]), int(round(float(row["entry_local_timestamp"])))


def compare_target(oracle: pd.DataFrame, reference: pd.DataFrame, target_dates: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mismatches: list[dict[str, Any]] = []
    per_day: dict[str, Any] = {}
    oracle = oracle[oracle["date"].astype(str).isin(target_dates)].copy()
    reference = reference[reference["date"].astype(str).isin(target_dates)].copy()
    reference["cell"] = reference.apply(reference_cell, axis=1)
    reference["key"] = reference.apply(comparable_key, axis=1)
    oracle["key"] = oracle.apply(comparable_key, axis=1)

    oracle_by_key = {key: row for key, row in oracle.set_index("key", drop=False).iterrows()}
    reference_by_key = {key: row for key, row in reference.set_index("key", drop=False).iterrows()}

    for day in target_dates:
        o_day = oracle[oracle["date"].astype(str).eq(day)]
        r_day = reference[reference["date"].astype(str).eq(day)]
        o_keys = set(o_day["key"])
        r_keys = set(r_day["key"])
        shared = o_keys & r_keys
        missing = sorted(r_keys - o_keys)
        extra = sorted(o_keys - r_keys)
        field_mismatch_count = 0
        for key in sorted(shared):
            o = oracle_by_key[key]
            r = reference_by_key[key]
            checks = {
                "entry_row": int(float_or_nan(o.get("entry_row"))) == int(float_or_nan(r.get("entry_row"))),
                "membership_set": str(o.get("membership_set")) == str(r.get("membership_set")),
                "direction": int(float_or_nan(o.get("direction"))) == int(float_or_nan(r.get("direction"))),
                "cell": str(o.get("cell")) == str(r.get("cell")),
                "gate_r_n5": bool(o.get("gate_r_n5")) == bool_value(r.get("gate_r_n5")),
                "gate_frames_q90": bool(o.get("gate_frames_q90")) == bool_value(r.get("gate_frames_q90")),
                "base_weight": close(o.get("base_weight"), r.get("base_weight")),
                "overlay_boost": close(o.get("overlay_boost"), r.get("overlay_boost")),
                "weight": close(o.get("weight"), r.get("weight")),
                "feature_value": close(o.get("feature_value"), r.get("feature_value")),
                "frames_since_mid_change": close(o.get("frames_since_mid_change"), r.get("frames_since_mid_change")),
                "past_event_25_bps": close(o.get("past_event_25_bps"), r.get("past_event_25_bps")),
            }
            bad = [field for field, ok in checks.items() if not ok]
            if bad:
                field_mismatch_count += 1
                mismatches.append(
                    {
                        "date": day,
                        "key": str(key),
                        "kind": "field_mismatch",
                        "fields": "+".join(bad),
                        "oracle_membership_set": o.get("membership_set"),
                        "reference_membership_set": r.get("membership_set"),
                        "oracle_cell": o.get("cell"),
                        "reference_cell": r.get("cell"),
                        "oracle_weight": o.get("weight"),
                        "reference_weight": r.get("weight"),
                    }
                )
        for key in missing[:200]:
            row = reference_by_key[key]
            mismatches.append(
                {
                    "date": day,
                    "key": str(key),
                    "kind": "missing_oracle_entry",
                    "reference_membership_set": row.get("membership_set"),
                    "reference_cell": row.get("cell"),
                }
            )
        for key in extra[:200]:
            row = oracle_by_key[key]
            mismatches.append(
                {
                    "date": day,
                    "key": str(key),
                    "kind": "extra_oracle_entry",
                    "oracle_membership_set": row.get("membership_set"),
                    "oracle_cell": row.get("cell"),
                }
            )
        per_day[day] = {
            "oracle_entries": int(len(o_day)),
            "reference_entries": int(len(r_day)),
            "expected_entries": TARGET_EXPECTED_COUNTS.get(day),
            "exact_timestamp_matches": int(len(shared)),
            "missing_oracle_entries": int(len(missing)),
            "extra_oracle_entries": int(len(extra)),
            "field_mismatch_rows": int(field_mismatch_count),
            "oracle_cell_counts": dict(Counter(o_day["cell"].astype(str))),
            "reference_cell_counts": dict(Counter(r_day["cell"].astype(str))),
        }
    totals = {
        "oracle_entries": int(len(oracle)),
        "reference_entries": int(len(reference)),
        "exact_timestamp_matches": int(sum(per_day[day]["exact_timestamp_matches"] for day in target_dates)),
        "missing_oracle_entries": int(sum(per_day[day]["missing_oracle_entries"] for day in target_dates)),
        "extra_oracle_entries": int(sum(per_day[day]["extra_oracle_entries"] for day in target_dates)),
        "field_mismatch_rows": int(sum(per_day[day]["field_mismatch_rows"] for day in target_dates)),
    }
    return {"totals": totals, "per_day": per_day}, mismatches


def close(left: Any, right: Any, tol: float = 1e-8) -> bool:
    a = float_or_nan(left)
    b = float_or_nan(right)
    if np.isnan(a) and np.isnan(b):
        return True
    if np.isnan(a) or np.isnan(b):
        return False
    return abs(a - b) <= tol


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    modules = import_legacy_modules(repo_root)
    _signal_math, _strategy_research, conv, _oos_decay = modules
    target_dates = date_range(args.from_date, args.to_date)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = repo_root / "systems" / "ccusdt_replay_exchange" / "runs" / f"{args.run_prefix}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    eligible, base_weight_map = load_weight_map(conv)
    reference_all = load_reference(repo_root, REFERENCE_ALL)
    reference_all["date"] = reference_all["date"].astype(str)
    reference_all["entry_ts"] = pd.to_numeric(reference_all["entry_local_timestamp"], errors="coerce")
    reference_all["net"] = pd.to_numeric(reference_all["fixed_gross_bps"], errors="coerce")
    reference_all["gross"] = pd.to_numeric(reference_all["fixed_gross_bps"], errors="coerce")
    reference_all["cost"] = 0.0
    overlay_threshold = locked_overlay_threshold(repo_root, eligible)
    frame_q90 = float(
        reference_all[reference_all["segment"].isin(["Fold1", "Fold2", "Fold3"])]["frames_since_mid_change"]
        .dropna()
        .quantile(0.90)
    )

    warmup = reference_all[
        reference_all["date"].ge(args.warmup_from)
        & reference_all["date"].lt(args.from_date)
        & reference_all["membership_set"].astype(str).isin(eligible)
    ].copy()
    generated_target_frames = [
        generate_panel_oracle_oos_day(repo_root, day, args, modules) for day in target_dates
    ]
    generated_targets = pd.concat(generated_target_frames, ignore_index=True, sort=False)
    oracle_rows = pd.concat([warmup, generated_targets], ignore_index=True, sort=False)
    oracle_rows = oracle_rows[oracle_rows["membership_set"].astype(str).isin(eligible)].copy()
    oracle_rows = apply_weights_and_overlay(oracle_rows, base_weight_map, overlay_threshold)
    oracle_scored = recompute_prequential_r5(oracle_rows, frame_q90)

    comparison, mismatches = compare_target(oracle_scored, reference_all, target_dates)
    ok = (
        comparison["totals"]["oracle_entries"] == comparison["totals"]["reference_entries"]
        and comparison["totals"]["missing_oracle_entries"] == 0
        and comparison["totals"]["extra_oracle_entries"] == 0
        and comparison["totals"]["field_mismatch_rows"] == 0
        and all(
            comparison["per_day"][day]["oracle_entries"] == TARGET_EXPECTED_COUNTS.get(day)
            for day in target_dates
            if day in TARGET_EXPECTED_COUNTS
        )
    )
    report = {
        "ok": ok,
        "run_tag": f"{args.run_prefix}_{timestamp}",
        "guardrail": "diagnostic_only_panel_oracle_reads_legacy_fixed_panel_not_runtime_input",
        "target_dates": target_dates,
        "warmup_from": args.warmup_from,
        "reference_file": str(repo_root / "date" / REFERENCE_ALL),
        "cost_mode": args.cost_mode,
        "entry_bucket_sec": args.entry_bucket_sec,
        "fixed_exit_us": int(FIXED_EXIT_US),
        "r5_rule": "last 5 entries with entry_ts+60s < current_entry_ts, scored on zero-fee gross/net",
        "eligible_membership_sets": eligible,
        "overlay_threshold_frames_since_mid_change": overlay_threshold,
        "frames_q90_threshold": frame_q90,
        **comparison,
        "outputs": {
            "summary_json": str(out_dir / "summary.json"),
            "oracle_entries_csv": str(out_dir / "panel_oracle_entries.csv"),
            "mismatches_csv": str(out_dir / "panel_oracle_mismatches.csv"),
        },
    }
    target_out = oracle_scored[oracle_scored["date"].astype(str).isin(target_dates)].copy()
    target_out.to_csv(out_dir / "panel_oracle_entries.csv", index=False)
    write_csv(out_dir / "panel_oracle_mismatches.csv", mismatches)
    (out_dir / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
