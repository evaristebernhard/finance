#!/usr/bin/env python3
"""Join Polymarket option EV, smart money, momentum, and microstructure factors.

Read-only research combiner. It does not fetch private data, sign orders, or
submit trades. Inputs are CSV artifacts from the local Polymarket research
pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.polymarket.join.claim_join import group_follow_rows_for_ev

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("output/polymarket_combined_strategy_join")


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def safe_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def ev_score(row: dict[str, Any]) -> float:
    pnl = safe_float(row.get("robust_min_expected_profit_usd"))
    edge = safe_float(row.get("robust_min_edge_cents"))
    prob_span = safe_float(row.get("max_model_prob")) - safe_float(row.get("min_model_prob"))
    stability_bonus = max(0.0, 1.0 - prob_span) * 0.5
    return max(0.0, pnl) * 2.0 + max(0.0, edge) * 1.5 + stability_bonus


def group_follow_rows(follow_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in follow_rows:
        asset = str(row.get("asset") or row.get("token_id") or "")
        if not asset:
            continue
        grouped.setdefault(asset, []).append(row)
    return grouped


def smart_flow_features(ev: dict[str, Any], flows: list[dict[str, Any]], join_mode: str = "token") -> dict[str, Any]:
    ev_outcome = str(ev.get("outcome") or "").lower()
    ev_direction = str(ev.get("direction") or "").lower()
    same = []
    opposite = []
    for row in flows:
        outcome = str(row.get("outcome") or "").lower()
        direction = str(row.get("direction") or "").lower()
        is_same = outcome == ev_outcome
        if join_mode == "claim" and ev_direction and direction:
            is_same = is_same or direction == ev_direction
        if is_same:
            same.append(row)
        elif outcome or direction:
            opposite.append(row)
    same_score = sum(max(0.0, safe_float(r.get("follow_score"))) for r in same)
    opp_score = sum(max(0.0, safe_float(r.get("follow_score"))) for r in opposite)
    same_edge = sum(max(0.0, safe_float(r.get("wallet_delay_robust_edge_cents"))) for r in same)
    opp_edge = sum(max(0.0, safe_float(r.get("wallet_delay_robust_edge_cents"))) for r in opposite)
    wallets = {str(r.get("wallet") or "") for r in same if r.get("wallet")}
    flow_score = math.log1p(same_score) + 0.5 * math.log1p(same_edge) + 0.25 * len(wallets) - math.log1p(opp_score) - 0.5 * math.log1p(opp_edge)
    return {
        "smart_flow_count": len(flows),
        "smart_flow_same_side_count": len(same),
        "smart_flow_opposite_count": len(opposite),
        "unique_same_side_wallets": len(wallets),
        "same_side_follow_score_sum": same_score,
        "opposite_follow_score_sum": opp_score,
        "smart_flow_score": flow_score,
    }


def momentum_score_from_flows(flows: list[dict[str, Any]], outcome: str) -> float:
    outcome_l = outcome.lower()
    vals = []
    for row in flows:
        if str(row.get("outcome") or "").lower() != outcome_l:
            continue
        for key in ("trade_proxy_edge_300s_cents", "trade_proxy_edge_120s_cents", "wallet_copy_edge_5m_cents"):
            vals.append(safe_float(row.get(key)))
    if not vals:
        return 0.0
    return clamp(sum(vals) / len(vals), -10.0, 10.0) / 2.0


def microstructure_score(ev: dict[str, Any], flows: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    available = safe_float(ev.get("available_notional_usd"))
    avg_price = safe_float(ev.get("avg_price"))
    depth_score = clamp(math.log1p(max(available, 0.0)) / 10.0, 0.0, 1.5)
    price_penalty = 0.0
    if avg_price <= 0.02 or avg_price >= 0.98:
        price_penalty = 1.0
    spreads = [safe_float(r.get("spread_cents"), 0.0) for r in flows if r.get("spread_cents") not in (None, "")]
    spread = sum(spreads) / len(spreads) if spreads else 0.0
    spread_penalty = clamp(spread / 5.0, 0.0, 2.0)
    crowd = [safe_float(r.get("crowd_exit_risk"), 0.0) for r in flows if r.get("crowd_exit_risk") not in (None, "")]
    crowd_risk = sum(crowd) / len(crowd) if crowd else 0.0
    crowd_penalty = clamp(crowd_risk, 0.0, 2.0)
    score = depth_score - price_penalty - spread_penalty - crowd_penalty
    return score, {
        "micro_depth_score": depth_score,
        "avg_flow_spread_cents": spread,
        "avg_crowd_exit_risk": crowd_risk,
        "micro_price_extreme_penalty": price_penalty,
        "microstructure_score": score,
    }


def build_combined_candidates(
    ev_rows: list[dict[str, Any]],
    follow_rows: list[dict[str, Any]],
    min_combined_score: float = 0.0,
    join_mode: str = "token",
) -> list[dict[str, Any]]:
    grouped_flows = group_follow_rows(follow_rows) if join_mode == "token" else group_follow_rows_for_ev(ev_rows, follow_rows, join_mode=join_mode)
    out: list[dict[str, Any]] = []
    for ev in ev_rows:
        token = str(ev.get("token_id") or ev.get("asset") or "")
        flows = grouped_flows.get(token, [])
        smart = smart_flow_features(ev, flows, join_mode=join_mode)
        mom = momentum_score_from_flows(flows, str(ev.get("outcome") or ""))
        micro_score, micro = microstructure_score(ev, flows)
        e_score = ev_score(ev)
        rule_scores = [safe_float(r.get("rule_ambiguity_score"), 0.0) for r in flows if r.get("rule_ambiguity_score") not in (None, "")]
        rule_risk = sum(rule_scores) / len(rule_scores) if rule_scores else 0.0
        rule_penalty = clamp(rule_risk / 2.0, 0.0, 3.0)
        combined = e_score + smart["smart_flow_score"] + mom + micro_score - rule_penalty
        reject: list[str] = []
        ensemble_candidate = safe_bool(ev.get("ensemble_candidate"))
        if not ensemble_candidate:
            reject.append("not_ensemble_candidate")
        if smart["smart_flow_opposite_count"] > smart["smart_flow_same_side_count"]:
            reject.append("opposite_smart_flow")
        if smart["smart_flow_same_side_count"] == 0:
            reject.append("no_same_side_smart_flow")
        if micro_score < -1.0:
            reject.append("weak_microstructure")
        if rule_risk >= 4.0:
            reject.append("high_rule_risk")
        if combined < min_combined_score:
            reject.append("combined_score_too_low")
        row = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "event_id": ev.get("event_id", ""),
            "event_title": ev.get("event_title", ""),
            "slug": ev.get("slug", ""),
            "question": ev.get("question", ""),
            "symbol": ev.get("symbol", ""),
            "outcome": ev.get("outcome", ""),
            "token_id": token,
            "claim_id": ev.get("claim_id", ""),
            "join_mode": join_mode,
            "settle_time_utc": ev.get("settle_time_utc", ""),
            "minutes_to_settle": safe_float(ev.get("minutes_to_settle")),
            "ensemble_candidate": ensemble_candidate,
            "robust_min_expected_profit_usd": safe_float(ev.get("robust_min_expected_profit_usd")),
            "robust_min_edge_cents": safe_float(ev.get("robust_min_edge_cents")),
            "min_model_prob": safe_float(ev.get("min_model_prob")),
            "max_model_prob": safe_float(ev.get("max_model_prob")),
            "avg_price": safe_float(ev.get("avg_price")),
            "available_notional_usd": safe_float(ev.get("available_notional_usd")),
            "ev_score": e_score,
            "momentum_score": mom,
            "rule_risk_score": rule_risk,
            "rule_penalty": rule_penalty,
            "combined_score": combined,
            "reject_reason": ";".join(reject),
            **smart,
            **micro,
        }
        out.append(row)
    out.sort(key=lambda r: (r["reject_reason"] == "", r["combined_score"]), reverse=True)
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [r for r in rows if not r.get("reject_reason")]
    reasons: dict[str, int] = {}
    for row in rows:
        for reason in str(row.get("reject_reason") or "").split(";"):
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "accepted_candidates": len(accepted),
        "reject_counts": reasons,
        "top_rows": rows[:20],
    }


def write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Polymarket Combined Strategy Join",
        "",
        f"Generated: {summary['generated_at_utc']}",
        "",
        "Read-only research: options EV + smart money + momentum + microstructure.",
        "",
        "## Counts",
        "",
        f"- Rows: {summary['rows']}",
        f"- Accepted candidates: {summary['accepted_candidates']}",
        f"- Reject counts: {summary['reject_counts']}",
        "",
        "## Top Rows",
        "",
        "| rank | score | reject | ev | smart | mom | micro | symbol | outcome | question |",
        "|---:|---:|---|---:|---:|---:|---:|---|---|---|",
    ]
    for i, row in enumerate(summary["top_rows"], 1):
        lines.append(
            f"| {i} | {float(row.get('combined_score') or 0):.4g} | {row.get('reject_reason','')} | "
            f"{float(row.get('ev_score') or 0):.4g} | {float(row.get('smart_flow_score') or 0):.4g} | "
            f"{float(row.get('momentum_score') or 0):.4g} | {float(row.get('microstructure_score') or 0):.4g} | "
            f"{row.get('symbol','')} | {row.get('outcome','')} | {str(row.get('question',''))[:100]} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Join Polymarket EV, smart money, momentum, and microstructure factors.")
    p.add_argument("--ensemble-csv", type=Path, default=Path("output/polymarket_binance_close_ensemble_20260609_live/ensemble_signals.csv"))
    p.add_argument("--follow-candidates-csv", type=Path, default=Path("output/polymarket_wallet_factor_probe_deep_20260608/follow_candidates.csv"))
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--min-combined-score", type=float, default=0.0)
    p.add_argument("--join-mode", choices=["token", "claim"], default="token")
    p.add_argument("--self-test", action="store_true")
    return p.parse_args()


def self_test() -> None:
    ev = [{"token_id": "t", "outcome": "Yes", "ensemble_candidate": "True", "robust_min_expected_profit_usd": "1", "robust_min_edge_cents": "1", "min_model_prob": "0.4", "max_model_prob": "0.6", "available_notional_usd": "1000", "avg_price": "0.5"}]
    fl = [{"asset": "t", "outcome": "Yes", "follow_score": "3", "wallet_delay_robust_edge_cents": "1", "trade_proxy_edge_300s_cents": "1", "wallet_copy_edge_5m_cents": "1", "spread_cents": "1", "crowd_exit_risk": "0"}]
    rows = build_combined_candidates(ev, fl)
    assert rows and rows[0]["combined_score"] > 0
    print("self-test ok")


def main() -> None:
    args = parse_args()
    if args.self_test:
        self_test()
        return
    ensemble_csv = args.ensemble_csv if args.ensemble_csv.is_absolute() else REPO_ROOT / args.ensemble_csv
    follow_csv = args.follow_candidates_csv if args.follow_candidates_csv.is_absolute() else REPO_ROOT / args.follow_candidates_csv
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir
    ev_rows = read_csv(ensemble_csv)
    follow_rows = read_csv(follow_csv)
    rows = build_combined_candidates(ev_rows, follow_rows, args.min_combined_score, args.join_mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "combined_candidates.csv", rows)
    summary = summarize(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_summary_md(output_dir / "summary.md", summary)
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    main()
