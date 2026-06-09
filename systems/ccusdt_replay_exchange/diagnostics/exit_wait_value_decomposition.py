#!/usr/bin/env python
"""Decompose conditional wait-exit value into mid and crossing components.

This is an offline mathematical diagnostic. It does not change any strategy or
execution code. For an existing taker exit decision it decomposes:

    W_t(tau) = taker_exit_net(t+tau) - taker_exit_net(t)

into:

    direction * log(mid_{t+tau} / mid_t) * 1e4
    + (exit_cross_t - exit_cross_{t+tau})
    + reconstruction_error.

For a long position, exit_cross = log(mid / bid) * 1e4.
For a short position, exit_cross = log(ask / mid) * 1e4.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from maker_exit_opportunity import DayMarket, optional_float, repo_path  # type: ignore


DEFAULT_PANEL = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "exit_residual_pressure_q70_idle01_g1_20260505_18_20260522/"
    "exit_residual_pressure_long_panel.parquet"
)
DEFAULT_SELECTED_EVENTS = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "conditional_wait_exit_policy_q70_idle01_g1_m010_20260516_18_20260522/"
    "conditional_wait_events.parquet"
)
DEFAULT_OUT_DIR = Path(
    "systems/ccusdt_replay_exchange/runs/"
    "exit_wait_value_decomposition_q70_idle01_g1_20260505_18_20260524"
)
DEFAULT_REPORT = Path("docs/markets/ccusdt/v1-tfi-exit-wait-value-decomposition-20260524.md")
EPS = 1e-12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--selected-events", type=Path, default=DEFAULT_SELECTED_EVENTS)
    parser.add_argument("--from-date", default="2026-05-05")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--oos-from-date", default="2026-05-16")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


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


def fmt(value: Any, digits: int = 4) -> str:
    value = optional_float(value)
    return "" if value is None else f"{value:.{digits}f}"


def read_selected_keys(path: Path) -> set[tuple[str, str, int, int, int, float]]:
    if not path.exists():
        return set()
    events = pq.read_table(path).to_pandas()
    keys: set[tuple[str, str, int, int, int, float]] = set()
    for row in events.itertuples(index=False):
        keys.add(
            (
                str(row.exit_profile_source),
                str(row.date),
                int(row.shadow_position_id),
                int(row.entry_ts_us),
                int(row.exit_decision_ts_us),
                float(row.ttl_sec),
            )
        )
    return keys


def exit_cross_bps(entry_side: str, *, bid: float, ask: float, mid: float) -> float:
    if bid <= 0.0 or ask <= 0.0 or mid <= 0.0:
        return 0.0
    if entry_side == "buy":
        return math.log(mid / bid) * 10_000.0
    if entry_side == "sell":
        return math.log(ask / mid) * 10_000.0
    raise ValueError(f"unexpected entry_side={entry_side!r}")


def decompose_panel(
    panel: pd.DataFrame,
    repo_root: Path,
    symbol: str,
    selected_keys: set[tuple[str, str, int, int, int, float]],
) -> pd.DataFrame:
    days = sorted(panel["date"].astype(str).unique())
    market_by_day = {day: DayMarket.load(repo_root, symbol, day) for day in days}
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(panel.itertuples(index=False), start=1):
        day = str(row.date)
        profile = str(row.exit_profile_source)
        shadow_position_id = int(row.shadow_position_id)
        entry_ts_us = int(row.entry_ts_us)
        exit_ts_us = int(row.exit_ts_us)
        ttl_sec = float(row.ttl_sec)
        entry_side = str(row.entry_side).lower()
        direction = 1.0 if entry_side == "buy" else -1.0
        wait_quote = market_by_day[day].quote_at_or_before(int(row.wait_quote_ts_us))

        exit_mid = float(row.exit_mid)
        wait_mid = float(wait_quote.mid_px)
        now_cross = exit_cross_bps(
            entry_side,
            bid=float(row.exit_bid),
            ask=float(row.exit_ask),
            mid=exit_mid,
        )
        wait_cross = exit_cross_bps(
            entry_side,
            bid=float(wait_quote.bid_px),
            ask=float(wait_quote.ask_px),
            mid=wait_mid,
        )
        mid_component = direction * math.log(wait_mid / exit_mid) * 10_000.0 if exit_mid > 0.0 and wait_mid > 0.0 else 0.0
        cross_component = now_cross - wait_cross
        wait_value = float(row.wait_value_bps)
        reconstruction = mid_component + cross_component
        exposure = max(float(row.actual_exposure), 0.0)
        key = (profile, day, shadow_position_id, entry_ts_us, exit_ts_us, ttl_sec)
        out = {
            "schema_id": "ccusdt_exit_wait_value_decomposition_v1",
            "runtime_safe_input": True,
            "date": day,
            "exit_profile_source": profile,
            "shadow_position_id": shadow_position_id,
            "entry_ts_us": entry_ts_us,
            "exit_ts_us": exit_ts_us,
            "ttl_sec": ttl_sec,
            "cell": str(row.cell),
            "entry_side": entry_side,
            "direction": int(direction),
            "actual_exposure": exposure,
            "selected_wait_policy_event": key in selected_keys,
            "exit_quote_ts_us": int(row.exit_quote_ts_us),
            "wait_quote_ts_us": int(wait_quote.local_ts_us),
            "exit_bid": float(row.exit_bid),
            "exit_ask": float(row.exit_ask),
            "exit_mid": exit_mid,
            "exit_spread_bps": float(row.exit_spread_bps),
            "wait_bid": float(wait_quote.bid_px),
            "wait_ask": float(wait_quote.ask_px),
            "wait_mid": wait_mid,
            "wait_spread_bps": float(wait_quote.spread_bps),
            "exit_cross_bps": now_cross,
            "wait_cross_bps": wait_cross,
            "mid_component_bps": mid_component,
            "cross_component_bps": cross_component,
            "wait_value_bps": wait_value,
            "reconstructed_wait_value_bps": reconstruction,
            "reconstruction_error_bps": wait_value - reconstruction,
            "weighted_wait_value_bps": exposure * wait_value,
            "weighted_mid_component_bps": exposure * mid_component,
            "weighted_cross_component_bps": exposure * cross_component,
            "weighted_reconstruction_error_bps": exposure * (wait_value - reconstruction),
            "path_h_bps": float(row.path_h_bps),
            "path_d_bps": float(row.path_d_bps),
            "recent_mid_alpha_5s_bps": float(row.recent_mid_alpha_5s_bps),
            "signed_top_depth_imbalance": float(row.signed_top_depth_imbalance),
        }
        for col in ["residual_pressure_score", "pressure_exhaustion_score", "pre_notional_imbalance_5s"]:
            if hasattr(row, col):
                out[col] = optional_float(getattr(row, col))
        rows.append(out)
        if idx % 5000 == 0:
            print(f"wait value decomposition processed rows={idx}", flush=True)
    return pd.DataFrame(rows)


def cvar_left(series: pd.Series, frac: float = 0.10) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().sort_values()
    if values.empty:
        return 0.0
    count = max(1, int(math.ceil(len(values) * frac)))
    return float(values.iloc[:count].mean())


def day_positive_frac(group: pd.DataFrame, column: str = "weighted_wait_value_bps") -> float:
    values = [float(day_group[column].sum()) for _, day_group in group.groupby("date", sort=True)]
    return float(sum(1 for value in values if value > 0.0) / len(values)) if values else 0.0


def min_day_sum(group: pd.DataFrame, column: str = "weighted_wait_value_bps") -> float:
    values = [float(day_group[column].sum()) for _, day_group in group.groupby("date", sort=True)]
    return min(values) if values else 0.0


def summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    wait_sum = float(pd.to_numeric(group["weighted_wait_value_bps"], errors="coerce").fillna(0.0).sum())
    mid_sum = float(pd.to_numeric(group["weighted_mid_component_bps"], errors="coerce").fillna(0.0).sum())
    cross_sum = float(pd.to_numeric(group["weighted_cross_component_bps"], errors="coerce").fillna(0.0).sum())
    return {
        "n": int(len(group)),
        "exposure": float(pd.to_numeric(group["actual_exposure"], errors="coerce").fillna(0.0).clip(lower=0.0).sum()),
        "weighted_wait_value_bps": wait_sum,
        "weighted_mid_component_bps": mid_sum,
        "weighted_cross_component_bps": cross_sum,
        "weighted_error_bps": float(
            pd.to_numeric(group["weighted_reconstruction_error_bps"], errors="coerce").fillna(0.0).sum()
        ),
        "mid_share_of_positive_total": mid_sum / wait_sum if wait_sum > EPS else None,
        "cross_share_of_positive_total": cross_sum / wait_sum if wait_sum > EPS else None,
        "mean_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").mean()) if len(group) else 0.0,
        "cvar10_wait_value_bps": cvar_left(group["wait_value_bps"], 0.10),
        "worst_wait_value_bps": float(pd.to_numeric(group["wait_value_bps"], errors="coerce").min()) if len(group) else 0.0,
        "positive_day_frac": day_positive_frac(group),
        "min_day_wait_sum_bps": min_day_sum(group),
        "mean_exit_cross_bps": float(pd.to_numeric(group["exit_cross_bps"], errors="coerce").mean()) if len(group) else 0.0,
        "mean_wait_cross_bps": float(pd.to_numeric(group["wait_cross_bps"], errors="coerce").mean()) if len(group) else 0.0,
    }


def grouped_summary(panel: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in panel.groupby(group_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {key: value for key, value in zip(group_cols, keys)}
        row.update(summarize_group(group))
        rows.append(row)
    return pd.DataFrame(rows)


def prior_exhaustion_oos_summary(panel: pd.DataFrame, oos_from_date: str) -> pd.DataFrame:
    if "pressure_exhaustion_score" not in panel.columns:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (profile, ttl), ttl_group in panel.groupby(["exit_profile_source", "ttl_sec"], sort=True):
        train = ttl_group[ttl_group["date"].astype(str) < oos_from_date]
        oos = ttl_group[ttl_group["date"].astype(str) >= oos_from_date].copy()
        values = pd.to_numeric(train["pressure_exhaustion_score"], errors="coerce").dropna()
        if train.empty or oos.empty or values.nunique() < 2:
            continue
        q20, q40, q60, q80 = [float(value) for value in values.quantile([0.20, 0.40, 0.60, 0.80])]

        def assign_bin(value: Any) -> str:
            value = optional_float(value)
            if value is None:
                return "na"
            if value <= q20:
                return "q1"
            if value <= q40:
                return "q2"
            if value <= q60:
                return "q3"
            if value <= q80:
                return "q4"
            return "q5"

        oos["pressure_exhaustion_prior_bin"] = oos["pressure_exhaustion_score"].map(assign_bin)
        for bin_name, group in oos.groupby("pressure_exhaustion_prior_bin", sort=True):
            if str(bin_name) == "na":
                continue
            row = {
                "exit_profile_source": profile,
                "ttl_sec": float(ttl),
                "pressure_exhaustion_prior_bin": str(bin_name),
                "oos_from_date": oos_from_date,
                "q20_train": q20,
                "q40_train": q40,
                "q60_train": q60,
                "q80_train": q80,
            }
            row.update(summarize_group(group))
            rows.append(row)
    return pd.DataFrame(rows)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd")


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 40) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    use_cols = [col for col in columns if col in df.columns]
    view = df.loc[:, use_cols].head(max_rows)
    lines = ["| " + " | ".join(use_cols) + " |", "| " + " | ".join(["---"] * len(use_cols)) + " |"]
    for _, row in view.iterrows():
        cells = []
        for col in use_cols:
            value = row[col]
            cells.append(fmt(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_report(
    path: Path,
    summary: dict[str, Any],
    ttl_summary: pd.DataFrame,
    selected_aggregate: pd.DataFrame,
    selected_day: pd.DataFrame,
    prior_oos: pd.DataFrame,
) -> None:
    ttl_view = ttl_summary.sort_values(["exit_profile_source", "ttl_sec"])
    selected_view = selected_aggregate.sort_values(["exit_profile_source", "ttl_sec"])
    selected_day_view = selected_day.sort_values(["exit_profile_source", "date"])
    if prior_oos.empty:
        prior_view = prior_oos
    else:
        prior_view = prior_oos[
            (prior_oos["exit_profile_source"].isin(["fixed30_livecoherent", "fixed45_livecoherent"]))
            & (prior_oos["ttl_sec"] == 5.0)
        ].sort_values(["exit_profile_source", "pressure_exhaustion_prior_bin"])
    total_selected = {
        "weighted_wait_value_bps": float(selected_aggregate["weighted_wait_value_bps"].sum())
        if not selected_aggregate.empty
        else 0.0,
        "weighted_mid_component_bps": float(selected_aggregate["weighted_mid_component_bps"].sum())
        if not selected_aggregate.empty
        else 0.0,
        "weighted_cross_component_bps": float(selected_aggregate["weighted_cross_component_bps"].sum())
        if not selected_aggregate.empty
        else 0.0,
    }
    lines = [
        "# CCUSDT exit wait-value decomposition",
        "",
        "This diagnostic asks what a wait-before-crossing exit actually earns.",
        "",
        "\\[",
        "W_t(\\tau)",
        "= q\\,10^4\\log\\frac{m_{t+\\tau}}{m_t}",
        "+ \\left(\\kappa_t-\\kappa_{t+\\tau}\\right)",
        "+ \\epsilon_t.",
        "\\]",
        "",
        "Here \\(q=+1\\) for long exits and \\(q=-1\\) for short exits. For a long, \\(\\kappa=10^4\\log(m/bid)\\); for a short, \\(\\kappa=10^4\\log(ask/m)\\).",
        "",
        "## Scope",
        "",
        f"- Input panel: `{summary['panel_path']}`",
        f"- Selected wait events: `{summary['selected_events_path']}`",
        f"- Decomposition rows: `{summary['decomposition_rows']}`",
        f"- Max absolute reconstruction error: `{fmt(summary['max_abs_reconstruction_error_bps'], 8)}` bps",
        f"- Output directory: `{summary['out_dir']}`",
        "",
        "## Selected Wait Policy Decomposition",
        "",
        f"- Total selected wait delta: `{fmt(total_selected['weighted_wait_value_bps'])}` weighted bp-units.",
        f"- Mid component: `{fmt(total_selected['weighted_mid_component_bps'])}`.",
        f"- Crossing/spread component: `{fmt(total_selected['weighted_cross_component_bps'])}`.",
        "",
    ]
    lines.extend(
        markdown_table(
            selected_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "n",
                "exposure",
                "weighted_wait_value_bps",
                "weighted_mid_component_bps",
                "weighted_cross_component_bps",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=20,
        )
    )
    lines.extend(["", "## Selected Wait By Day", ""])
    lines.extend(
        markdown_table(
            selected_day_view,
            [
                "exit_profile_source",
                "date",
                "n",
                "exposure",
                "weighted_wait_value_bps",
                "weighted_mid_component_bps",
                "weighted_cross_component_bps",
                "cvar10_wait_value_bps",
                "min_day_wait_sum_bps",
            ],
            max_rows=20,
        )
    )
    lines.extend(["", "## All Wait Opportunities By TTL", ""])
    lines.extend(
        markdown_table(
            ttl_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "n",
                "exposure",
                "weighted_wait_value_bps",
                "weighted_mid_component_bps",
                "weighted_cross_component_bps",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=40,
        )
    )
    lines.extend(["", f"## Prior-Exhaustion OOS Decomposition From {summary['oos_from_date']}", ""])
    lines.extend(
        markdown_table(
            prior_view,
            [
                "exit_profile_source",
                "ttl_sec",
                "pressure_exhaustion_prior_bin",
                "n",
                "exposure",
                "weighted_wait_value_bps",
                "weighted_mid_component_bps",
                "weighted_cross_component_bps",
                "cvar10_wait_value_bps",
                "positive_day_frac",
                "min_day_wait_sum_bps",
            ],
            max_rows=20,
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The current selected wait overlay is not just spread recovery. Most of its gain comes from favorable mid continuation, while a smaller but meaningful part comes from cheaper crossing after waiting.",
            "",
            "The exhaustion diagnostic is therefore better interpreted as a mid-continuation guard: low exhaustion means the favorable move has not fully decayed, while high exhaustion means waiting mostly inherits adverse mid movement. The crossing term matters, but it is not large enough by itself to explain the selected wait gain.",
            "",
            "## Files",
            "",
            f"- Decomposition panel: `{summary['outputs']['decomposition_parquet']}`",
            f"- TTL summary: `{summary['outputs']['ttl_summary_csv']}`",
            f"- Selected aggregate: `{summary['outputs']['selected_aggregate_csv']}`",
            f"- Prior-exhaustion OOS summary: `{summary['outputs']['prior_exhaustion_oos_csv']}`",
            f"- Summary: `{summary['outputs']['summary_json']}`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    panel_path = repo_path(repo_root, args.panel)
    selected_events_path = repo_path(repo_root, args.selected_events)
    out_dir = repo_path(repo_root, args.out_dir)
    report_path = repo_path(repo_root, args.report_path)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise FileExistsError(f"{out_dir} exists; pass --force to rebuild")
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = pq.read_table(panel_path).to_pandas()
    panel = panel[(panel["date"].astype(str) >= args.from_date) & (panel["date"].astype(str) <= args.to_date)].copy()
    if not bool(panel["runtime_safe"].all()):
        raise ValueError("input panel contains non-runtime-safe rows")
    selected_keys = read_selected_keys(selected_events_path)
    decomp = decompose_panel(panel, repo_root, args.symbol, selected_keys)
    ttl = grouped_summary(decomp, ["exit_profile_source", "ttl_sec"])
    selected = decomp[decomp["selected_wait_policy_event"].astype(bool)].copy()
    selected_aggregate = grouped_summary(selected, ["exit_profile_source", "ttl_sec"]) if not selected.empty else pd.DataFrame()
    selected_day = grouped_summary(selected, ["exit_profile_source", "date"]) if not selected.empty else pd.DataFrame()
    prior_oos = prior_exhaustion_oos_summary(decomp, args.oos_from_date)

    decomp_parquet = out_dir / "exit_wait_value_decomposition_panel.parquet"
    decomp_csv = out_dir / "exit_wait_value_decomposition_panel.csv"
    ttl_csv = out_dir / "exit_wait_value_decomposition_ttl_summary.csv"
    selected_aggregate_csv = out_dir / "exit_wait_value_decomposition_selected_aggregate.csv"
    selected_day_csv = out_dir / "exit_wait_value_decomposition_selected_day.csv"
    prior_oos_csv = out_dir / "exit_wait_value_decomposition_prior_exhaustion_oos.csv"
    write_parquet(decomp_parquet, decomp)
    write_csv(decomp_csv, decomp)
    write_csv(ttl_csv, ttl)
    write_csv(selected_aggregate_csv, selected_aggregate)
    write_csv(selected_day_csv, selected_day)
    write_csv(prior_oos_csv, prior_oos)

    summary = {
        "schema_id": "ccusdt_exit_wait_value_decomposition_summary_v1",
        "ok": True,
        "symbol": args.symbol,
        "panel_path": str(panel_path),
        "panel_sha256": file_sha256(panel_path),
        "selected_events_path": str(selected_events_path),
        "selected_events_sha256": file_sha256(selected_events_path) if selected_events_path.exists() else None,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "oos_from_date": args.oos_from_date,
        "decomposition_rows": int(len(decomp)),
        "selected_event_rows_matched": int(len(selected)),
        "max_abs_reconstruction_error_bps": float(
            pd.to_numeric(decomp["reconstruction_error_bps"], errors="coerce").abs().max()
        ),
        "out_dir": str(out_dir),
        "boundary": "all inputs are exchange-visible wait panel fields plus canonical quote truth; selected events are policy audit labels",
        "outputs": {
            "decomposition_parquet": str(decomp_parquet),
            "decomposition_csv": str(decomp_csv),
            "ttl_summary_csv": str(ttl_csv),
            "selected_aggregate_csv": str(selected_aggregate_csv),
            "selected_day_csv": str(selected_day_csv),
            "prior_exhaustion_oos_csv": str(prior_oos_csv),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    summary["summary_hash"] = stable_hash(summary)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_report(report_path, summary, ttl, selected_aggregate, selected_day, prior_oos)
    print(json.dumps({"ok": True, "summary": str(out_dir / "summary.json"), "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
