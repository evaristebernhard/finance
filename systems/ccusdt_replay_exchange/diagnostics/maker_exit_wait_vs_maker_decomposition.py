#!/usr/bin/env python
"""Decompose maker-first exit value into waiting versus passive fill.

This diagnostic is deliberately offline. It takes the oracle-free selected
maker-first exit events, optionally joins the full maker opportunity panel for
the touch-trade proxy and the L2 queue diagnostic for the displayed-queue
proxy, then writes a causal decomposition:

    final - immediate_taker
      = (fallback_taker_after_TTL - immediate_taker)
      + fill_proxy * (maker_touch - fallback_taker_after_TTL)

The first term is pure waiting. The second term is the incremental value of a
passive fill versus simply waiting and crossing at TTL.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_EVENTS = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_first_exit_policy_q70_idle01_g1_warmup_strict_20260516_18_20260522/"
    "maker_first_exit_events.parquet"
)
DEFAULT_PANEL = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_exit_opportunity_q70_idle01_g1_20260505_18_20260522/"
    "maker_exit_opportunity_panel.parquet"
)
DEFAULT_L2_EVENTS = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_exit_l2_queue_q70_idle01_g1_warmup_strict_20260516_18_20260522/"
    "maker_first_exit_l2_events.parquet"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-maker-exit-wait-vs-maker-20260522.md")

KEY_COLUMNS = [
    "exit_profile_source",
    "date",
    "shadow_position_id",
    "entry_ts_us",
    "exit_decision_ts_us",
    "ttl_sec",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--l2-events", type=Path, default=DEFAULT_L2_EVENTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()


def file_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "byte_size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": file_sha256(path),
    }


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


def optional_fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def safe_div(numer: float, denom: float) -> float:
    if abs(denom) <= 1e-12:
        return 0.0
    return float(numer / denom)


def normalize_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def key_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "exit_ts_us" in out.columns and "exit_decision_ts_us" not in out.columns:
        out = out.rename(columns={"exit_ts_us": "exit_decision_ts_us"})
    for column in ["shadow_position_id", "entry_ts_us", "exit_decision_ts_us"]:
        out[column] = pd.to_numeric(out[column], errors="coerce").astype("int64")
    out["ttl_key_us"] = (pd.to_numeric(out["ttl_sec"], errors="coerce") * 1_000_000).round().astype("int64")
    out["_event_key"] = (
        out["exit_profile_source"].astype(str)
        + "|"
        + out["date"].astype(str)
        + "|"
        + out["shadow_position_id"].astype(str)
        + "|"
        + out["entry_ts_us"].astype(str)
        + "|"
        + out["exit_decision_ts_us"].astype(str)
        + "|"
        + out["ttl_key_us"].astype(str)
    )
    return out


def weighted_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    weights = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return float((weights * values).sum())


def weighted_mean(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
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


def read_selected_events(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    events = pq.read_table(path).to_pandas()
    if events.empty:
        raise ValueError(f"empty selected events: {path}")
    required = {
        "exit_profile_source",
        "date",
        "shadow_position_id",
        "entry_ts_us",
        "exit_decision_ts_us",
        "ttl_sec",
        "pure_taker_net_bps",
        "maker_touch_net_bps",
        "fallback_taker_net_bps",
        "actual_exposure",
        "maker_filled",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"events missing required columns: {missing}")
    return key_frame(events)


def join_touch_proxy(events: pd.DataFrame, panel_path: Path) -> pd.DataFrame:
    if not panel_path.exists():
        events["touch_fill"] = pd.NA
        events["touch_fill_ts_us"] = pd.NA
        events["touch_selection_cost_bps"] = 0.0
        return events
    panel_columns = [
        "date",
        "exit_profile_source",
        "shadow_position_id",
        "entry_ts_us",
        "exit_ts_us",
        "ttl_sec",
        "touch_fill",
        "touch_fill_ts_us",
        "touch_fill_delay_us",
        "touch_trade_qty",
        "touch_trade_count",
        "selection_cost_bps",
        "selection_taker_net_bps",
    ]
    panel = pq.read_table(panel_path, columns=panel_columns).to_pandas()
    panel = key_frame(panel)
    panel = panel.drop_duplicates("_event_key", keep="first")
    panel = panel.rename(
        columns={
            "selection_cost_bps": "touch_selection_cost_bps",
            "selection_taker_net_bps": "touch_selection_taker_net_bps",
        }
    )
    keep = [
        "_event_key",
        "touch_fill",
        "touch_fill_ts_us",
        "touch_fill_delay_us",
        "touch_trade_qty",
        "touch_trade_count",
        "touch_selection_cost_bps",
        "touch_selection_taker_net_bps",
    ]
    return events.merge(panel[keep], on="_event_key", how="left", validate="one_to_one")


def join_l2_proxy(events: pd.DataFrame, l2_path: Path) -> pd.DataFrame:
    if not l2_path.exists():
        events["l2_queue_depleted"] = pd.NA
        events["l2_queue_depleted_ts_us"] = pd.NA
        events["l2_queue_depleted_delay_us"] = pd.NA
        events["l2_depleted_qty"] = 0.0
        events["l2_queue_remaining"] = pd.NA
        events["l2_adverse_selection_bps"] = 0.0
        return events
    l2_columns = [
        "date",
        "exit_profile_source",
        "shadow_position_id",
        "entry_ts_us",
        "exit_decision_ts_us",
        "ttl_sec",
        "l2_queue_depleted",
        "l2_queue_depleted_ts_us",
        "l2_queue_depleted_delay_us",
        "l2_update_count",
        "l2_queue_ahead_qty",
        "l2_depleted_qty",
        "l2_queue_remaining",
        "l2_adverse_selection_bps",
    ]
    l2 = pq.read_table(l2_path, columns=l2_columns).to_pandas()
    l2 = key_frame(l2)
    l2 = l2.drop_duplicates("_event_key", keep="first")
    keep = ["_event_key"] + [column for column in l2_columns if column not in KEY_COLUMNS]
    return events.merge(l2[keep], on="_event_key", how="left", validate="one_to_one")


def model_terms(df: pd.DataFrame, model: str, fill_column: str, selection_column: str) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    fill = normalize_bool(df[fill_column]) if fill_column in df.columns else pd.Series(False, index=df.index)
    pure = pd.to_numeric(df["pure_taker_net_bps"], errors="coerce").fillna(0.0)
    fallback = pd.to_numeric(df["fallback_taker_net_bps"], errors="coerce").fillna(0.0)
    maker = pd.to_numeric(df["maker_touch_net_bps"], errors="coerce").fillna(0.0)
    exposure = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    selection = (
        pd.to_numeric(df[selection_column], errors="coerce").fillna(0.0)
        if selection_column in df.columns
        else pd.Series(0.0, index=df.index)
    )
    selection = selection.where(fill, 0.0)
    delay_delta = fallback - pure
    passive_increment = (maker - fallback).where(fill, 0.0)
    final_delta = delay_delta + passive_increment
    out["exit_model"] = model
    out["fill_proxy"] = fill
    out["model_final_net_bps"] = pure + final_delta
    out["model_final_delta_vs_taker_bps"] = final_delta
    out["model_delay_only_delta_bps"] = delay_delta
    out["model_passive_increment_vs_delay_bps"] = passive_increment
    out["model_selection_cost_bps"] = selection
    out["model_selection_cost_positive_bps"] = selection.clip(lower=0.0)
    out["model_selection_adjusted_delta_bps"] = final_delta - selection
    out["weighted_model_final_delta_vs_taker_bps"] = final_delta * exposure
    out["weighted_model_delay_only_delta_bps"] = delay_delta * exposure
    out["weighted_model_passive_increment_vs_delay_bps"] = passive_increment * exposure
    out["weighted_model_selection_cost_bps"] = selection * exposure
    out["weighted_model_selection_cost_positive_bps"] = selection.clip(lower=0.0) * exposure
    out["weighted_model_selection_adjusted_delta_bps"] = (final_delta - selection) * exposure
    out["weighted_model_final_net_bps"] = (pure + final_delta) * exposure
    return out


def build_decomposition(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = events.copy()
    pure = pd.to_numeric(df["pure_taker_net_bps"], errors="coerce").fillna(0.0)
    fallback = pd.to_numeric(df["fallback_taker_net_bps"], errors="coerce").fillna(0.0)
    maker = pd.to_numeric(df["maker_touch_net_bps"], errors="coerce").fillna(0.0)
    exposure = pd.to_numeric(df["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0)
    df["delay_only_taker_net_bps"] = fallback
    df["delay_only_delta_vs_taker_bps"] = fallback - pure
    df["fallback_decay_cost_bps"] = (pure - fallback).clip(lower=0.0)
    df["fallback_wait_benefit_bps"] = (fallback - pure).clip(lower=0.0)
    df["maker_touch_delta_vs_taker_bps"] = maker - pure
    df["maker_touch_increment_vs_delay_bps"] = maker - fallback
    df["trade_queue_fill"] = normalize_bool(df["maker_filled"])
    df["touch_trade_fill"] = normalize_bool(df["touch_fill"]) if "touch_fill" in df.columns else False
    df["l2_queue_fill"] = normalize_bool(df["l2_queue_depleted"]) if "l2_queue_depleted" in df.columns else False
    df["weighted_delay_only_delta_vs_taker_bps"] = df["delay_only_delta_vs_taker_bps"] * exposure
    df["weighted_fallback_decay_cost_bps"] = df["fallback_decay_cost_bps"] * exposure
    df["weighted_fallback_wait_benefit_bps"] = df["fallback_wait_benefit_bps"] * exposure
    df["weighted_maker_touch_increment_vs_delay_bps"] = df["maker_touch_increment_vs_delay_bps"] * exposure

    common_columns = [
        "schema_id",
        "exit_profile_source",
        "date",
        "shadow_position_id",
        "entry_ts_us",
        "exit_decision_ts_us",
        "ttl_sec",
        "gate_name",
        "cell",
        "entry_side",
        "exit_action",
        "actual_exposure",
        "pure_taker_net_bps",
        "delay_only_taker_net_bps",
        "maker_touch_net_bps",
        "delay_only_delta_vs_taker_bps",
        "fallback_decay_cost_bps",
        "fallback_wait_benefit_bps",
        "maker_touch_delta_vs_taker_bps",
        "maker_touch_increment_vs_delay_bps",
        "exit_spread_bps",
        "path_h_bps",
        "path_d_bps",
        "signed_top_depth_imbalance",
        "same_flow_imbalance_5s",
        "recent_mid_alpha_5s_bps",
        "touch_trade_fill",
        "trade_queue_fill",
        "l2_queue_fill",
    ]
    existing_common = [column for column in common_columns if column in df.columns]

    event_rows: list[pd.DataFrame] = []
    for model, fill_column, selection_column in [
        ("touch_trade_proxy_v1", "touch_trade_fill", "touch_selection_cost_bps"),
        ("trade_queue_proxy_v1", "trade_queue_fill", "adverse_selection_bps"),
        ("l2_depletion_proxy_v1", "l2_queue_fill", "l2_adverse_selection_bps"),
    ]:
        terms = model_terms(df, model, fill_column, selection_column)
        model_df = pd.concat([df[existing_common].reset_index(drop=True), terms.reset_index(drop=True)], axis=1)
        model_df["schema_id"] = "ccusdt_maker_exit_wait_vs_maker_event_v1"
        event_rows.append(model_df)
    long_events = pd.concat(event_rows, ignore_index=True)
    return df, long_events


def summarize_model(group: pd.DataFrame) -> dict[str, Any]:
    final_delta = float(group["weighted_model_final_delta_vs_taker_bps"].sum())
    delay_delta = float(group["weighted_model_delay_only_delta_bps"].sum())
    passive_increment = float(group["weighted_model_passive_increment_vs_delay_bps"].sum())
    selection_cost = float(group["weighted_model_selection_cost_bps"].sum())
    selection_adj = float(group["weighted_model_selection_adjusted_delta_bps"].sum())
    return {
        "attempts": int(len(group)),
        "exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "fill_rate": float(group["fill_proxy"].mean()) if len(group) else 0.0,
        "weighted_pure_taker_net_bps": weighted_sum(group, "pure_taker_net_bps"),
        "weighted_delay_only_net_bps": weighted_sum(group, "delay_only_taker_net_bps"),
        "weighted_model_final_net_bps": float(group["weighted_model_final_net_bps"].sum()),
        "weighted_final_delta_vs_taker_bps": final_delta,
        "weighted_delay_only_delta_bps": delay_delta,
        "weighted_passive_increment_vs_delay_bps": passive_increment,
        "weighted_selection_cost_bps": selection_cost,
        "weighted_selection_cost_positive_bps": float(group["weighted_model_selection_cost_positive_bps"].sum()),
        "weighted_selection_adjusted_delta_bps": selection_adj,
        "weighted_fallback_decay_cost_bps": weighted_sum(group, "fallback_decay_cost_bps"),
        "weighted_fallback_wait_benefit_bps": weighted_sum(group, "fallback_wait_benefit_bps"),
        "mean_exit_spread_bps": float(pd.to_numeric(group["exit_spread_bps"], errors="coerce").mean())
        if "exit_spread_bps" in group.columns
        else 0.0,
        "wait_share_of_final_delta": safe_div(delay_delta, final_delta),
        "passive_share_of_final_delta": safe_div(passive_increment, final_delta),
        "selection_share_of_final_delta": safe_div(selection_cost, final_delta),
    }


def build_summary(long_events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_cols = ["exit_profile_source", "date", "gate_name", "exit_model"]
    daily_rows: list[dict[str, Any]] = []
    for keys, group in long_events.groupby(group_cols, sort=True):
        row = dict(zip(group_cols, keys, strict=True))
        row.update(summarize_model(group))
        daily_rows.append(row)
    daily = pd.DataFrame(daily_rows)

    overall_cols = ["exit_profile_source", "gate_name", "exit_model"]
    overall_rows: list[dict[str, Any]] = []
    for keys, group in long_events.groupby(overall_cols, sort=True):
        row = dict(zip(overall_cols, keys, strict=True))
        row["date"] = "ALL"
        row.update(summarize_model(group))
        overall_rows.append(row)
    overall = pd.DataFrame(overall_rows)
    return daily, overall


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> str:
    if df.empty:
        return "_No rows._\n"
    rows = df.loc[:, columns].head(max_rows)
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for _, row in rows.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(optional_fmt(value))
            else:
                values.append(str(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep, *body]) + "\n"


def mechanism_label(row: pd.Series) -> str:
    final_delta = optional_float(row.get("weighted_final_delta_vs_taker_bps")) or 0.0
    passive = optional_float(row.get("weighted_passive_increment_vs_delay_bps")) or 0.0
    delay = optional_float(row.get("weighted_delay_only_delta_bps")) or 0.0
    fill_rate = optional_float(row.get("fill_rate")) or 0.0
    if fill_rate < 0.01 and abs(passive) < 1e-9:
        return "wait/fallback only"
    if final_delta > 0.0 and abs(delay) >= abs(passive) * 2.0:
        return "mostly wait"
    if final_delta > 0.0 and passive > abs(delay):
        return "passive fill led"
    if final_delta < 0.0 and passive < 0.0:
        return "passive fill hurt"
    return "mixed"


def write_report(
    path: Path,
    summary: dict[str, Any],
    daily: pd.DataFrame,
    overall: pd.DataFrame,
) -> None:
    focus = overall.copy()
    if not focus.empty:
        focus["mechanism"] = focus.apply(mechanism_label, axis=1)
        focus = focus.sort_values(
            ["exit_profile_source", "exit_model", "weighted_final_delta_vs_taker_bps"],
            ascending=[True, True, False],
        )
    fixed30_l2 = focus[
        (focus["exit_profile_source"].astype(str) == "fixed30_livecoherent")
        & (focus["exit_model"].astype(str) == "l2_depletion_proxy_v1")
    ]
    fixed30_note = ""
    if not fixed30_l2.empty:
        row = fixed30_l2.iloc[0]
        fixed30_note = (
            f"For `fixed30_livecoherent` under `l2_depletion_proxy_v1`, fill rate is "
            f"{optional_fmt(100.0 * float(row['fill_rate']), 2)}%, final delta is "
            f"{optional_fmt(row['weighted_final_delta_vs_taker_bps'])}, delay-only delta is "
            f"{optional_fmt(row['weighted_delay_only_delta_bps'])}, and passive increment is "
            f"{optional_fmt(row['weighted_passive_increment_vs_delay_bps'])}. "
            f"Mechanism label: `{row['mechanism']}`."
        )

    columns = [
        "exit_profile_source",
        "date",
        "gate_name",
        "exit_model",
        "attempts",
        "exposure",
        "fill_rate",
        "weighted_final_delta_vs_taker_bps",
        "weighted_delay_only_delta_bps",
        "weighted_passive_increment_vs_delay_bps",
        "weighted_selection_cost_bps",
        "weighted_selection_adjusted_delta_bps",
        "mechanism",
    ]
    overall_display = focus.copy()
    daily_display = daily.copy()
    if not daily_display.empty:
        daily_display["mechanism"] = daily_display.apply(mechanism_label, axis=1)
        daily_display = daily_display.sort_values(
            ["exit_profile_source", "date", "exit_model", "weighted_final_delta_vs_taker_bps"],
            ascending=[True, True, True, False],
        )

    text = r"""# CCUSDT q70 idle01_g1 maker exit: wait vs maker decomposition

Run id: `__RUN_ID__`

This diagnostic tests whether the current maker-first exit candidate is really
passive execution alpha or merely a delayed taker exit.

For an exit decision at time $t$:

$$
Y_0 = Y^T_t, \qquad
Y_\tau = Y^T_{t+\tau}, \qquad
Y_M = Y^M_t.
$$

For fill proxy $k$ with indicator $I^k_t(\tau)$:

$$
\Delta^k_t =
Y^k_t - Y_0 =
\underbrace{(Y_\tau-Y_0)}_{\text{wait / fallback}}
+
\underbrace{I^k_t(\tau)(Y_M-Y_\tau)}_{\text{passive fill increment}}.
$$

So if $I^k_t(\tau)=0$ but $\Delta^k_t>0$, the mechanism is not maker fill;
it is the wait/fallback path.

__FIXED30_NOTE__

## Overall decomposition

__OVERALL_TABLE__

## Daily decomposition

__DAILY_TABLE__

## Interpretation

- `delay_only_delta` is the value of waiting until TTL and then crossing,
  with no maker order.
- `passive_increment_vs_delay` is the incremental value of a passive fill
  compared with that same wait-then-cross path.
- `touch_trade_proxy_v1` is optimistic: any opposite trade reaching the touch
  counts as fill.
- `trade_queue_proxy_v1` is stricter: opposite trade quantity must consume the
  displayed top queue ahead.
- `l2_depletion_proxy_v1` is a fast-line L2 proxy: same-price displayed-size
  depletion can include cancels, so it is diagnostic evidence, not a strict
  private-order fill proof.

## Decision gate

This run does not promote maker-first exit into the strict Runner maker
lifecycle. The current positive fixed30 result is explained by the wait/fallback
term under the stricter L2 proxy, while trade/touch fill proxies show negative
passive increments after the same decomposition.

The next strict-Runner maker implementation should require a prior-date rule
whose L2 or stricter proxy has positive `passive_increment_vs_delay`, acceptable
selection-adjusted delta, and non-trivial fill probability. If the positive
term remains `delay_only_delta`, the correct next model is a conditional
wait/exit-timing controller, not a maker execution controller.

## Files

- Events: `__EVENTS_PARQUET__`
- Daily summary: `__DAILY_SUMMARY_CSV__`
- Overall summary: `__OVERALL_SUMMARY_CSV__`
- Manifest: `__SUMMARY_JSON__`
"""
    text = (
        text.replace("__RUN_ID__", str(summary["run_id"]))
        .replace("__FIXED30_NOTE__", fixed30_note)
        .replace("__OVERALL_TABLE__", markdown_table(overall_display, columns))
        .replace("__DAILY_TABLE__", markdown_table(daily_display, columns, max_rows=60))
        .replace("__EVENTS_PARQUET__", str(summary["outputs"]["events_parquet"]))
        .replace("__DAILY_SUMMARY_CSV__", str(summary["outputs"]["daily_summary_csv"]))
        .replace("__OVERALL_SUMMARY_CSV__", str(summary["outputs"]["overall_summary_csv"]))
        .replace("__SUMMARY_JSON__", str(summary["outputs"]["summary_json"]))
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    start = time.perf_counter()
    repo_root = args.repo_root.resolve()
    events_path = repo_path(repo_root, args.events)
    panel_path = repo_path(repo_root, args.panel)
    l2_path = repo_path(repo_root, args.l2_events)
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to overwrite")
    out_dir.mkdir(parents=True, exist_ok=True)

    events = read_selected_events(events_path)
    events = join_touch_proxy(events, panel_path)
    events = join_l2_proxy(events, l2_path)
    per_event, long_events = build_decomposition(events)
    daily, overall = build_summary(long_events)

    events_csv = out_dir / "maker_exit_wait_vs_maker_events.csv"
    events_parquet = out_dir / "maker_exit_wait_vs_maker_events.parquet"
    daily_csv = out_dir / "maker_exit_wait_vs_maker_daily_summary.csv"
    daily_parquet = out_dir / "maker_exit_wait_vs_maker_daily_summary.parquet"
    overall_csv = out_dir / "maker_exit_wait_vs_maker_overall_summary.csv"
    overall_parquet = out_dir / "maker_exit_wait_vs_maker_overall_summary.parquet"
    per_event_csv = out_dir / "maker_exit_wait_vs_maker_base_events.csv"
    per_event_parquet = out_dir / "maker_exit_wait_vs_maker_base_events.parquet"

    write_csv(events_csv, long_events)
    write_parquet(events_parquet, long_events)
    write_csv(per_event_csv, per_event)
    write_parquet(per_event_parquet, per_event)
    write_csv(daily_csv, daily)
    write_parquet(daily_parquet, daily)
    write_csv(overall_csv, overall)
    write_parquet(overall_parquet, overall)

    run_id = "maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522"
    summary = {
        "schema_id": "ccusdt_maker_exit_wait_vs_maker_summary_v1",
        "run_id": run_id,
        "ok": True,
        "events_path": str(events_path),
        "panel_path": str(panel_path),
        "l2_events_path": str(l2_path),
        "out_dir": str(out_dir),
        "attempts": int(len(events)),
        "long_event_rows": int(len(long_events)),
        "daily_summary_rows": int(len(daily)),
        "overall_summary_rows": int(len(overall)),
        "input_manifest": {
            "selected_events": file_manifest(events_path),
            "maker_opportunity_panel": file_manifest(panel_path),
            "l2_events": file_manifest(l2_path),
        },
        "output_hashes": {
            "events_parquet": file_sha256(events_parquet),
            "daily_summary_csv": file_sha256(daily_csv),
            "overall_summary_csv": file_sha256(overall_csv),
        },
        "decomposition_identity": "final_delta = delay_only_delta + fill_proxy * (maker_touch - fallback_taker_after_ttl)",
        "elapsed_wall_ms": int(round((time.perf_counter() - start) * 1000)),
        "outputs": {
            "events_csv": str(events_csv),
            "events_parquet": str(events_parquet),
            "base_events_csv": str(per_event_csv),
            "base_events_parquet": str(per_event_parquet),
            "daily_summary_csv": str(daily_csv),
            "daily_summary_parquet": str(daily_parquet),
            "overall_summary_csv": str(overall_csv),
            "overall_summary_parquet": str(overall_parquet),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    summary_path = out_dir / "summary.json"
    summary["summary_hash"] = stable_hash(summary)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_report(report_path, summary, daily, overall)
    print(json.dumps({"ok": True, "summary": str(summary_path), "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
