#!/usr/bin/env python
"""Small post-exit watcher for CCUSDT V1 TFI.

The watcher is deliberately not an exit replacement. It starts only after the
small path manager has already made a drawdown exit, then asks whether the path
prints a fresh, observable re-entry trigger.

Two mechanisms are separated:

    impulse re-trigger:
        favorable queue + fresh same-side trade + price reclaim by 5s

    absorption re-trigger:
        favorable queue + adverse trade pressure by 5s, then a small price
        reclaim from the post-exit reset low before chasing too far.

Future returns are labels and PnL accounting only; they are not trigger inputs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ccusdt_v1_tfi_post_exit_retrigger_diagnostic import (
    MANAGER_EVENTS,
    PRIMARY_POLICY,
    Paths,
    build_post_exit_path,
    fmt,
    load_day_panel,
    load_manager_events,
    markdown_table,
    resolve_path,
)


RUN_TAG = "20260519_ccusdt_v1_tfi_post_exit_watcher_v1"
GUARDRAIL = "research_only_post_exit_watcher_no_execution_recommendation"


@dataclass(frozen=True)
class WatcherPolicy:
    name: str
    absorb_enabled: bool
    absorb_qi_threshold: float = 0.70
    absorb_reclaim_bps: float = 2.0
    absorb_cancel_extension_bps: float = 5.0
    absorb_chase_cap_bps: float = 5.0
    min_remaining_sec: float = 5.0


WATCHER_POLICIES = [
    WatcherPolicy(name="impulse_only", absorb_enabled=False),
    WatcherPolicy(name="watcher_q70_absorb_reclaim2", absorb_enabled=True, absorb_qi_threshold=0.70),
    WatcherPolicy(name="watcher_q65_absorb_reclaim2", absorb_enabled=True, absorb_qi_threshold=0.65),
    WatcherPolicy(
        name="watcher_q65_absorb_reclaim3",
        absorb_enabled=True,
        absorb_qi_threshold=0.65,
        absorb_reclaim_bps=3.0,
    ),
]


@dataclass(frozen=True)
class WatcherPaths(Paths):
    @property
    def events_csv(self) -> Path:  # type: ignore[override]
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_watcher_events_{self.run_tag}.csv"

    @property
    def policy_summary_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_watcher_policy_summary_{self.run_tag}.csv"

    @property
    def case_summary_csv(self) -> Path:  # type: ignore[override]
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_watcher_case_summary_{self.run_tag}.csv"

    @property
    def examples_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_post_exit_watcher_examples_{self.run_tag}.csv"

    @property
    def report_md(self) -> Path:  # type: ignore[override]
        return self.doc_dir / f"v1-tfi-post-exit-watcher-{self.run_tag}.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/ccusdt")
    parser.add_argument(
        "--panel-root",
        default="data/ccusdt/v1/derived/ccusdt_v1_fixed_event_factor_panel",
    )
    parser.add_argument("--panel-run-tag", default="20260517_ccusdt_fixed_factors_v3")
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--manager-events", default=MANAGER_EVENTS)
    parser.add_argument("--primary-policy", default=PRIMARY_POLICY)
    parser.add_argument("--obs-sec", type=float, default=5.0)
    parser.add_argument("--impulse-qi-threshold", type=float, default=0.70)
    parser.add_argument("--impulse-reclaim-threshold", type=float, default=1.0)
    return parser.parse_args()


def load_all_policy_events(paths: WatcherPaths, primary_policy: str) -> pd.DataFrame:
    events = pd.read_csv(paths.manager_events_csv)
    events = events[events["policy"].eq(primary_policy)].copy()
    for col in ["entry_row", "target_exposure", "weighted_gross", "baseline_weighted_gross60"]:
        if col in events.columns:
            events[col] = pd.to_numeric(events[col], errors="coerce")
    return events.dropna(subset=["entry_row", "target_exposure", "weighted_gross"])


def obs_features(path: pd.DataFrame, obs_sec: float) -> dict[str, float]:
    obs = path[(path["sec_after_exit"] >= 0) & (path["sec_after_exit"] <= obs_sec)].copy()
    post_obs = obs[obs["sec_after_exit"] > 0].copy()
    if obs.empty:
        return {}
    r_min = float(obs["post_R"].min())
    r_max = float(obs["post_R"].max())
    r_end = float(obs["post_R"].iloc[-1])
    return {
        "obs_R_end": r_end,
        "obs_R_min": r_min,
        "obs_R_max": r_max,
        "obs_reclaim": r_end - r_min,
        "obs_signed_qi5_mean": float(obs["signed_qi5"].mean()),
        "obs_signed_ofi_mean": float(obs["signed_ofi"].mean()),
        "obs_signed_mlofi5_mean": float(obs["signed_mlofi5"].mean()),
        "obs_signed_tfi_sum": float(post_obs["signed_tfi"].sum(skipna=True)),
        "obs_signed_tfi_mean": float(post_obs["signed_tfi"].mean()) if not post_obs.empty else np.nan,
        "obs_signed_trade_amount_sum": float(post_obs["signed_trade_amount"].sum(skipna=True)),
        "obs_target_trade_amount_sum": float(post_obs["target_trade_amount"].sum(skipna=True)),
        "obs_adverse_trade_amount_sum": float(post_obs["adverse_trade_amount"].sum(skipna=True)),
        "obs_trade_notional_sum": float(pd.to_numeric(post_obs["trade_notional_quote"], errors="coerce").sum(skipna=True)),
    }


def first_index_at_or_after(path: pd.DataFrame, sec: float) -> int | None:
    candidates = path[path["sec_after_exit"] >= sec]
    if candidates.empty:
        return None
    return int(candidates.index[0])


def find_absorption_trigger(path: pd.DataFrame, features: dict[str, float], policy: WatcherPolicy, obs_sec: float) -> int | None:
    trigger_level = features["obs_R_min"] + policy.absorb_reclaim_bps
    cancel_level = features["obs_R_min"] - policy.absorb_cancel_extension_bps
    final_sec = float(path["sec_after_exit"].iloc[-1])
    scan = path[path["sec_after_exit"] > obs_sec]
    for idx, row in scan.iterrows():
        sec = float(row["sec_after_exit"])
        post_r = float(row["post_R"])
        if post_r < cancel_level:
            return None
        if post_r < trigger_level:
            continue
        if post_r > policy.absorb_chase_cap_bps:
            continue
        if final_sec - sec < policy.min_remaining_sec:
            continue
        return int(idx)
    return None


def trigger_for_policy(
    path: pd.DataFrame,
    features: dict[str, float],
    policy: WatcherPolicy,
    *,
    obs_sec: float,
    impulse_qi_threshold: float,
    impulse_reclaim_threshold: float,
) -> tuple[str, int] | None:
    impulse_ok = (
        features["obs_signed_qi5_mean"] >= impulse_qi_threshold
        and features["obs_signed_tfi_sum"] > 0
        and features["obs_reclaim"] >= impulse_reclaim_threshold
    )
    if impulse_ok:
        idx = first_index_at_or_after(path, obs_sec)
        return ("impulse_5s", idx) if idx is not None else None

    absorb_setup = (
        policy.absorb_enabled
        and features["obs_signed_qi5_mean"] >= policy.absorb_qi_threshold
        and features["obs_signed_tfi_sum"] < 0
    )
    if not absorb_setup:
        return None
    idx = find_absorption_trigger(path, features, policy, obs_sec)
    return ("absorb_reclaim", idx) if idx is not None else None


def pnl_from_trigger(path: pd.DataFrame, trigger_idx: int) -> dict[str, float]:
    entry_r = float(path.loc[trigger_idx, "post_R"])
    tail = path.loc[trigger_idx:].copy()
    rel = tail["post_R"] - entry_r
    return {
        "watch_entry_sec": float(path.loc[trigger_idx, "sec_after_exit"]),
        "watch_entry_R": entry_r,
        "watch_final_pnl": float(rel.iloc[-1]),
        "watch_mfe": float(rel.max()),
        "watch_mae": float(rel.min()),
        "watch_t_mfe_after_entry": float(tail.loc[rel.idxmax(), "sec_after_exit"] - path.loc[trigger_idx, "sec_after_exit"]),
    }


def build_watcher_events(
    drawdown_events: pd.DataFrame,
    paths: WatcherPaths,
    policies: list[WatcherPolicy],
    *,
    obs_sec: float,
    impulse_qi_threshold: float,
    impulse_reclaim_threshold: float,
) -> pd.DataFrame:
    panel_cache: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for _, event in drawdown_events.iterrows():
        date = str(event["date"])
        if date not in panel_cache:
            panel_cache[date] = load_day_panel(paths, date)
        panel = panel_cache[date]
        if panel.empty:
            continue
        path = build_post_exit_path(event, panel)
        if path.empty:
            continue
        features = obs_features(path, obs_sec)
        if not features:
            continue
        base = {
            "date": date,
            "entry_row": int(event["entry_row"]),
            "cell": event["cell"],
            "direction_label": event["direction_label"],
            "target_exposure": float(event["target_exposure"]),
            "path_case_class": event.get("path_case_class", "unknown"),
            "exit_sec": float(event["exit_sec"]),
            "R_exit": float(event["policy_gross"]),
            "baseline_R60": float(event["baseline_gross60"]),
            "post_total_mfe": float(path["post_R"].max()),
            "post_final": float(path["post_R"].iloc[-1]),
            "post_path_end_sec": float(path["sec_after_exit"].iloc[-1]),
            **features,
        }
        for policy in policies:
            row = {**base, "watcher_policy": policy.name}
            trigger = trigger_for_policy(
                path,
                features,
                policy,
                obs_sec=obs_sec,
                impulse_qi_threshold=impulse_qi_threshold,
                impulse_reclaim_threshold=impulse_reclaim_threshold,
            )
            if trigger is None:
                row.update(
                    {
                        "watch_triggered": False,
                        "watch_mode": "none",
                        "watch_entry_sec": np.nan,
                        "watch_entry_R": np.nan,
                        "watch_final_pnl": 0.0,
                        "watch_mfe": 0.0,
                        "watch_mae": 0.0,
                        "watch_t_mfe_after_entry": np.nan,
                        "watch_weighted_final": 0.0,
                        "watch_weighted_mfe": 0.0,
                        "watch_weighted_mae": 0.0,
                    }
                )
            else:
                mode, trigger_idx = trigger
                pnl = pnl_from_trigger(path, trigger_idx)
                row.update(pnl)
                row.update(
                    {
                        "watch_triggered": True,
                        "watch_mode": mode,
                        "watch_weighted_final": pnl["watch_final_pnl"] * float(event["target_exposure"]),
                        "watch_weighted_mfe": pnl["watch_mfe"] * float(event["target_exposure"]),
                        "watch_weighted_mae": pnl["watch_mae"] * float(event["target_exposure"]),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows)


def build_policy_summary(all_policy_events: pd.DataFrame, watcher_events: pd.DataFrame) -> pd.DataFrame:
    manager_total = float(all_policy_events["weighted_gross"].sum())
    fixed60_total = float(all_policy_events["baseline_weighted_gross60"].sum())
    rows = []
    for policy, group in watcher_events.groupby("watcher_policy", sort=False):
        triggered = group[group["watch_triggered"].astype(bool)]
        rows.append(
            {
                "watcher_policy": policy,
                "drawdown_exits": int(group["entry_row"].nunique()),
                "triggers": int(triggered["entry_row"].nunique()),
                "impulse_triggers": int(triggered["watch_mode"].eq("impulse_5s").sum()),
                "absorb_triggers": int(triggered["watch_mode"].eq("absorb_reclaim").sum()),
                "watch_weighted_final": float(triggered["watch_weighted_final"].sum()),
                "watch_weighted_mfe": float(triggered["watch_weighted_mfe"].sum()),
                "watch_worst_weighted_final": float(triggered["watch_weighted_final"].min()) if not triggered.empty else np.nan,
                "watch_negative_triggers": int((triggered["watch_weighted_final"] < 0).sum()),
                "manager_total": manager_total,
                "manager_plus_watcher_total": manager_total + float(triggered["watch_weighted_final"].sum()),
                "fixed60_total": fixed60_total,
                "vs_manager_delta": float(triggered["watch_weighted_final"].sum()),
                "vs_fixed60_delta": manager_total + float(triggered["watch_weighted_final"].sum()) - fixed60_total,
            }
        )
    return pd.DataFrame(rows)


def build_case_summary(watcher_events: pd.DataFrame) -> pd.DataFrame:
    return (
        watcher_events.groupby(["watcher_policy", "path_case_class", "watch_mode"], sort=True)
        .agg(
            rows=("entry_row", "size"),
            triggered=("watch_triggered", "sum"),
            weighted_final=("watch_weighted_final", "sum"),
            weighted_mfe=("watch_weighted_mfe", "sum"),
            worst_weighted_final=("watch_weighted_final", "min"),
            obs_qi_mean=("obs_signed_qi5_mean", "mean"),
            obs_tfi_sum_mean=("obs_signed_tfi_sum", "mean"),
            obs_R_min_mean=("obs_R_min", "mean"),
            obs_R_end_mean=("obs_R_end", "mean"),
        )
        .reset_index()
    )


def build_examples(watcher_events: pd.DataFrame) -> pd.DataFrame:
    selected_rows = [2583437, 2322885, 2340079, 2361187, 2377379, 2379419, 2383289, 2540829, 1615412]
    selected = watcher_events[watcher_events["entry_row"].isin(selected_rows)].copy()
    triggered = watcher_events[watcher_events["watch_triggered"].astype(bool)].copy()
    selected["example_group"] = "selected_cases"
    triggered["example_group"] = "triggered"
    out = pd.concat([triggered, selected], ignore_index=True)
    return out.drop_duplicates(["example_group", "watcher_policy", "entry_row"]).sort_values(
        ["watcher_policy", "example_group", "entry_row"]
    )


def write_report(
    paths: WatcherPaths,
    *,
    watcher_events: pd.DataFrame,
    policy_summary: pd.DataFrame,
    case_summary: pd.DataFrame,
    examples: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    example_cols = [
        "example_group",
        "watcher_policy",
        "date",
        "entry_row",
        "path_case_class",
        "direction_label",
        "target_exposure",
        "watch_triggered",
        "watch_mode",
        "watch_entry_sec",
        "watch_entry_R",
        "watch_final_pnl",
        "watch_weighted_final",
        "watch_mae",
        "obs_signed_qi5_mean",
        "obs_signed_tfi_sum",
        "obs_R_min",
        "obs_R_end",
        "post_final",
    ]
    policy_params = pd.DataFrame(
        [
            {
                "watcher_policy": policy.name,
                "absorb_enabled": policy.absorb_enabled,
                "absorb_qi_threshold": policy.absorb_qi_threshold if policy.absorb_enabled else np.nan,
                "absorb_reclaim_bps": policy.absorb_reclaim_bps if policy.absorb_enabled else np.nan,
                "absorb_cancel_extension_bps": policy.absorb_cancel_extension_bps if policy.absorb_enabled else np.nan,
                "absorb_chase_cap_bps": policy.absorb_chase_cap_bps if policy.absorb_enabled else np.nan,
                "min_remaining_sec": policy.min_remaining_sec if policy.absorb_enabled else np.nan,
            }
            for policy in WATCHER_POLICIES
        ]
    )
    lines = [
        "# CCUSDT V1 TFI Post-Exit Watcher",
        "",
        f"Status: `{args.run_tag}`.",
        "",
        f"Guardrail: `{GUARDRAIL}`.",
        "",
        "## Question",
        "",
        "The watcher starts after a drawdown exit from the small path manager.",
        "It does not ask whether the first exit was wrong. It asks whether the",
        "post-exit path prints a new entry event.",
        "",
        "Use post-exit coordinates:",
        "",
        "$$",
        r"\widetilde R_i(u)=10^4s_i\log\frac{M_{\tau_i+u}}{M_{\tau_i}}.",
        "$$",
        "",
        r"At \(g=5s\):",
        "",
        "$$",
        r"Q_i(g)=\frac{1}{g}\int_0^g s_iQI_5(\tau_i+u)\,du,\qquad",
        r"F_i(g)=\sum_{0<u\le g}s_iTFI(\tau_i+u).",
        "$$",
        "",
        "The impulse branch is:",
        "",
        "$$",
        rf"Q_i(5)\ge {args.impulse_qi_threshold:g},\quad F_i(5)>0,\quad C_i(5)\ge {args.impulse_reclaim_threshold:g}.",
        "$$",
        "",
        "The absorption branch is:",
        "",
        "$$",
        r"Q_i(5)\ge q_a,\quad F_i(5)<0,",
        "$$",
        "",
        "then wait for a confirmed reclaim from the reset low:",
        "",
        "$$",
        r"\tau_a=\inf\{u>5:\widetilde R_i(u)-L_i(5)\ge r_a,\ \widetilde R_i(u)\le 5,",
        r"\min_{5<v\le u}\widetilde R_i(v)\ge L_i(5)-5,\ T_i-u\ge5\}.",
        "$$",
        "",
        r"where \(L_i(5)=\min_{0\le v\le5}\widetilde R_i(v)\).",
        r"The cap \(\widetilde R_i(u)\le5\) prevents chasing late spikes like `2540829`; the",
        "remaining-time guard prevents opening only at the last print of the path.",
        "",
        "## Watcher Parameters",
        "",
        markdown_table(
            policy_params,
            [
                "watcher_policy",
                "absorb_enabled",
                "absorb_qi_threshold",
                "absorb_reclaim_bps",
                "absorb_cancel_extension_bps",
                "absorb_chase_cap_bps",
                "min_remaining_sec",
            ],
        ),
        "",
        "## Policy Summary",
        "",
        markdown_table(
            policy_summary,
            [
                "watcher_policy",
                "drawdown_exits",
                "triggers",
                "impulse_triggers",
                "absorb_triggers",
                "watch_weighted_final",
                "watch_weighted_mfe",
                "watch_worst_weighted_final",
                "watch_negative_triggers",
                "manager_total",
                "manager_plus_watcher_total",
                "fixed60_total",
                "vs_manager_delta",
                "vs_fixed60_delta",
            ],
        ),
        "",
        "## Case Summary",
        "",
        markdown_table(
            case_summary[case_summary["triggered"] > 0],
            [
                "watcher_policy",
                "path_case_class",
                "watch_mode",
                "triggered",
                "weighted_final",
                "weighted_mfe",
                "worst_weighted_final",
                "obs_qi_mean",
                "obs_tfi_sum_mean",
                "obs_R_min_mean",
                "obs_R_end_mean",
            ],
        ),
        "",
        "## Examples",
        "",
        markdown_table(examples, example_cols, max_rows=80),
        "",
        "## Read",
        "",
        "- `impulse_only` is the previous strict witness, but with a conservative",
        "  re-entry mark at the first event at or after 5s.",
        "- `watcher_q70_absorb_reclaim2` is the cleaner watcher: it catches",
        "  `2583437`, `2322885`, and `2379419` while keeping `1615412`,",
        "  `2377379`, and `2540829` closed.",
        "- `watcher_q65_absorb_reclaim2` is the higher-recall watcher. It also",
        "  catches `2340079` and a small positive re-entry in `2361187`, but the",
        "  lower queue threshold should be treated as a research sensitivity, not",
        "  a live setting.",
        "- The absorption branch is not same-side impulse. It is a reset-low reclaim",
        "  rule after adverse trade pressure fails to keep pushing price against",
        "  the original side.",
        "",
        "## Outputs",
        "",
        f"- `{paths.events_csv}`",
        f"- `{paths.policy_summary_csv}`",
        f"- `{paths.case_summary_csv}`",
        f"- `{paths.examples_csv}`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "python scripts/ccusdt_v1_tfi_post_exit_watcher.py",
        "```",
        "",
    ]
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = WatcherPaths(
        date_dir=resolve_path(args.date_dir),
        doc_dir=resolve_path(args.doc_dir),
        panel_root=resolve_path(args.panel_root),
        panel_run_tag=args.panel_run_tag,
        symbol=args.symbol,
        run_tag=args.run_tag,
        manager_events_name=args.manager_events,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    drawdown_events = load_manager_events(paths, args.primary_policy)
    all_policy_events = load_all_policy_events(paths, args.primary_policy)
    watcher_events = build_watcher_events(
        drawdown_events,
        paths,
        WATCHER_POLICIES,
        obs_sec=float(args.obs_sec),
        impulse_qi_threshold=float(args.impulse_qi_threshold),
        impulse_reclaim_threshold=float(args.impulse_reclaim_threshold),
    )
    policy_summary = build_policy_summary(all_policy_events, watcher_events)
    case_summary = build_case_summary(watcher_events)
    examples = build_examples(watcher_events)

    watcher_events.to_csv(paths.events_csv, index=False)
    policy_summary.to_csv(paths.policy_summary_csv, index=False)
    case_summary.to_csv(paths.case_summary_csv, index=False)
    examples.to_csv(paths.examples_csv, index=False)
    write_report(
        paths,
        watcher_events=watcher_events,
        policy_summary=policy_summary,
        case_summary=case_summary,
        examples=examples,
        args=args,
    )
    print(f"wrote {paths.events_csv}")
    print(f"wrote {paths.policy_summary_csv}")
    print(f"wrote {paths.case_summary_csv}")
    print(f"wrote {paths.examples_csv}")
    print(f"wrote {paths.report_md}")
    print(policy_summary.to_string(index=False))


if __name__ == "__main__":
    main()
