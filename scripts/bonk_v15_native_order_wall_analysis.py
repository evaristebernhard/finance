#!/usr/bin/env python3
"""Native order-wall diagnostics for BONK V10c panels.

This deliberately does not start from Fibonacci levels. It starts from the book:
bid/ask top-level JSON -> wall levels -> touch -> path and controls.
"""

from __future__ import annotations

import argparse
import csv
import glob
import html
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"
WALL_SCORE_MIN = 3.0
EVENT_GAP = 30
HORIZON_EVENTS = 150
SHIFT_60S_US = 60_000_000


def fnum(value, default=0.0):
    try:
        if value in ("", None):
            return default
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return default


def inum(value, default=0):
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except Exception:
        return default


def mean(values):
    values = [v for v in values if math.isfinite(v)]
    return sum(values) / len(values) if values else 0.0


def median(values):
    values = sorted(v for v in values if math.isfinite(v))
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return 0.5 * (values[mid - 1] + values[mid])


def rate(count, total):
    return count / total if total else 0.0


def signed_ratio(a, b):
    denom = abs(a) + abs(b)
    return 0.0 if denom <= 1e-12 else max(-1.0, min(1.0, (a - b) / denom))


def parse_levels(raw):
    try:
        levels = json.loads(raw or "[]")
        return [
            (fnum(item[0]), fnum(item[1]))
            for item in levels
            if isinstance(item, list) and len(item) >= 2
        ]
    except Exception:
        return []


def strongest_wall(levels):
    amounts = [amount for _, amount in levels if amount > 0]
    if not amounts:
        return 0.0, 0.0, 0.0
    avg = sum(amounts) / len(amounts)
    if avg <= 1e-12:
        return 0.0, 0.0, 0.0
    price, amount = max(levels, key=lambda item: item[1])
    return price, amount, amount / avg


@dataclass
class Row:
    date: str
    symbol: str
    ts: int
    event_index: int
    mid: float
    spread_bps: float
    qimb25: float
    mlofi10: float
    buy: float
    sell: float
    bid_wall_price: float
    bid_wall_amount: float
    bid_wall_score: float
    ask_wall_price: float
    ask_wall_amount: float
    ask_wall_score: float
    factor_eligible: bool
    confidence: str


def load_folds(path: Path, run_tag: str, symbols):
    intervals = defaultdict(list)
    if not path.exists():
        return intervals
    symbol_set = set(symbols)
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("run_tag") != run_tag or row.get("symbol") not in symbol_set:
                continue
            intervals[row["symbol"]].append(
                (
                    row.get("fold", ""),
                    inum(row.get("valid_start_local_timestamp")),
                    inum(row.get("valid_end_local_timestamp")),
                )
            )
    return intervals


def fold_for_ts(intervals, symbol, ts):
    for fold, start, end in intervals.get(symbol, []):
        if start <= ts <= end:
            return fold
    return ""


def load_panel(data_root: Path, run_tag: str, symbols):
    base = data_root / "derived" / "bonk_v10c_event_ofi_panel" / f"run_tag={run_tag}"
    by_symbol = defaultdict(list)
    parts = []
    for symbol in symbols:
        parts.extend(glob.glob(str(base / f"symbol={symbol}" / "**" / "part_*.csv"), recursive=True))
    for part in sorted(parts):
        with open(part, newline="", encoding="utf-8") as f:
            for raw in csv.DictReader(f):
                mid = fnum(raw.get("mid_price"))
                if mid <= 0:
                    continue
                bid_levels = parse_levels(raw.get("bid_top_levels_json"))
                ask_levels = parse_levels(raw.get("ask_top_levels_json"))
                bid_p, bid_a, bid_s = strongest_wall(bid_levels)
                ask_p, ask_a, ask_s = strongest_wall(ask_levels)
                row = Row(
                    date=raw.get("date", ""),
                    symbol=raw.get("symbol", ""),
                    ts=inum(raw.get("local_timestamp")),
                    event_index=inum(raw.get("event_index")),
                    mid=mid,
                    spread_bps=fnum(raw.get("spread_bps")),
                    qimb25=fnum(raw.get("queue_imbalance_25")),
                    mlofi10=fnum(raw.get("mlofi_roll10_l10")),
                    buy=fnum(raw.get("trade_buy_amount")),
                    sell=fnum(raw.get("trade_sell_amount")),
                    bid_wall_price=bid_p,
                    bid_wall_amount=bid_a,
                    bid_wall_score=bid_s,
                    ask_wall_price=ask_p,
                    ask_wall_amount=ask_a,
                    ask_wall_score=ask_s,
                    factor_eligible=raw.get("factor_eligible") == "true",
                    confidence=raw.get("execute_cancel_confidence", ""),
                )
                by_symbol[row.symbol].append(row)
    for rows in by_symbol.values():
        rows.sort(key=lambda row: (row.ts, row.event_index))
    return sorted(parts), by_symbol


def wall_distance_bps(row: Row, side: str):
    if side == "bid":
        if row.bid_wall_price <= 0 or row.bid_wall_price > row.mid:
            return math.inf
        return (row.mid - row.bid_wall_price) / row.mid * 10_000.0
    if row.ask_wall_price <= 0 or row.ask_wall_price < row.mid:
        return math.inf
    return (row.ask_wall_price - row.mid) / row.mid * 10_000.0


def side_path(rows, pos, side_sign, barrier_bps):
    entry = rows[pos].mid
    end = min(len(rows) - 1, pos + HORIZON_EVENTS)
    mfe = 0.0
    mae = 0.0
    first = None
    for idx in range(pos + 1, end + 1):
        ret = side_sign * (rows[idx].mid - entry) / entry * 10_000.0
        mfe = max(mfe, ret)
        mae = min(mae, ret)
        if first is None:
            if ret <= -barrier_bps:
                first = ("adverse_first", idx - pos)
            elif ret >= barrier_bps:
                first = ("favorable_first", idx - pos)
    side_return = side_sign * (rows[end].mid - entry) / entry * 10_000.0
    label, latency = first if first else ("timeout", "")
    return {
        "path_label": label,
        "favorable_first": label == "favorable_first",
        "adverse_first": label == "adverse_first",
        "timeout": label == "timeout",
        "reaction_latency_events": latency,
        "mfe_bps": mfe,
        "mae_bps": mae,
        "side_return_bps": side_return,
    }


def wall_survival(rows, pos, side, wall_price):
    end = min(len(rows) - 1, pos + 30)
    for idx in range(pos + 1, end + 1):
        row = rows[idx]
        if side == "bid":
            if abs(row.bid_wall_price - wall_price) <= 1e-9 and row.bid_wall_score >= 2.0:
                return True
        else:
            if abs(row.ask_wall_price - wall_price) <= 1e-9 and row.ask_wall_score >= 2.0:
                return True
    return False


def nearest_pos(rows, target_ts):
    if not rows:
        return None
    lo, hi = 0, len(rows)
    while lo < hi:
        mid = (lo + hi) // 2
        if rows[mid].ts < target_ts:
            lo = mid + 1
        else:
            hi = mid
    candidates = [max(0, lo - 1), min(len(rows) - 1, lo)]
    return min(candidates, key=lambda idx: abs(rows[idx].ts - target_ts))


def event_record(run_tag, fold, rows, pos, wall_side, control_type, control_group):
    row = rows[pos]
    if wall_side == "bid":
        side_sign = 1
        wall_price = row.bid_wall_price
        wall_amount = row.bid_wall_amount
        wall_score = row.bid_wall_score
        distance = wall_distance_bps(row, "bid")
        active_pressure = signed_ratio(row.sell, row.buy)
        depth_pressure = row.qimb25
    else:
        side_sign = -1
        wall_price = row.ask_wall_price
        wall_amount = row.ask_wall_amount
        wall_score = row.ask_wall_score
        distance = wall_distance_bps(row, "ask")
        active_pressure = signed_ratio(row.buy, row.sell)
        depth_pressure = -row.qimb25
    barrier = max(1.5, 2.0 * row.spread_bps)
    outcome = side_path(rows, pos, side_sign, barrier)
    return {
        "run_tag": run_tag,
        "fold": fold,
        "date": row.date,
        "symbol": row.symbol,
        "event_ts": row.ts,
        "event_index": row.event_index,
        "control_type": control_type,
        "control_group_id": control_group,
        "wall_side": wall_side,
        "side": "long" if side_sign > 0 else "short",
        "mid_price": row.mid,
        "spread_bps": row.spread_bps,
        "wall_price": wall_price,
        "wall_amount": wall_amount,
        "wall_score_vs_avg_level": wall_score,
        "wall_distance_bps": distance,
        "touch_band_bps": max(1.5, 2.0 * row.spread_bps),
        "wall_survives_30_events": wall_survival(rows, pos, wall_side, wall_price),
        "depth_pressure_aligned": depth_pressure,
        "active_pressure_against_wall": active_pressure,
        "mlofi_roll10_l10": row.mlofi10,
        "buy_amount": row.buy,
        "sell_amount": row.sell,
        "path_barrier_bps": barrier,
        **outcome,
        "factor_eligible": row.factor_eligible,
        "execute_cancel_confidence": row.confidence,
        "guardrail": GUARDRAIL,
    }


def build_events(run_tag, by_symbol, intervals):
    base_events = []
    controls = []
    for symbol, rows in by_symbol.items():
        last_by_side = {"bid": -10**9, "ask": -10**9}
        for pos, row in enumerate(rows):
            fold = fold_for_ts(intervals, symbol, row.ts)
            if not fold or not row.factor_eligible or pos + HORIZON_EVENTS >= len(rows):
                continue
            for wall_side in ["bid", "ask"]:
                score = row.bid_wall_score if wall_side == "bid" else row.ask_wall_score
                distance = wall_distance_bps(row, wall_side)
                band = max(1.5, 2.0 * row.spread_bps)
                if score < WALL_SCORE_MIN or not (0.0 <= distance <= band):
                    continue
                if pos - last_by_side[wall_side] < EVENT_GAP:
                    continue
                last_by_side[wall_side] = pos
                group = f"{fold}|{symbol}|{row.event_index}|{wall_side}"
                base = event_record(run_tag, fold, rows, pos, wall_side, "base", group)
                base_events.append(base)
                controls.extend(control_events(run_tag, fold, by_symbol, symbol, rows, pos, wall_side, group))
    return base_events, controls


def control_events(run_tag, fold, by_symbol, symbol, rows, pos, wall_side, group):
    out = []
    out.append(event_record(run_tag, fold, rows, pos, "ask" if wall_side == "bid" else "bid", "side_flip", group))
    for name, offset in [("timestamp_shift_plus_60s", SHIFT_60S_US), ("timestamp_shift_minus_60s", -SHIFT_60S_US)]:
        target = rows[pos].ts + offset
        if target <= 0:
            continue
        cpos = nearest_pos(rows, target)
        if cpos is not None and cpos + HORIZON_EVENTS < len(rows):
            out.append(event_record(run_tag, fold, rows, cpos, wall_side, name, group))
    cpos = (pos + 997) % len(rows)
    if cpos + HORIZON_EVENTS < len(rows):
        out.append(event_record(run_tag, fold, rows, cpos, wall_side, "random_time_same_symbol", group))
    for other_symbol, other_rows in by_symbol.items():
        if other_symbol == symbol:
            continue
        cpos = nearest_pos(other_rows, rows[pos].ts)
        if cpos is not None and cpos + HORIZON_EVENTS < len(other_rows):
            out.append(event_record(run_tag, fold, other_rows, cpos, wall_side, "wrong_symbol_same_time", group))
            break
    return out


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        key = (row["control_type"], row["wall_side"])
        grouped[key].append(row)
    out = []
    for (control_type, wall_side), items in sorted(grouped.items()):
        n = len(items)
        out.append(
            {
                "control_type": control_type,
                "wall_side": wall_side,
                "events": n,
                "favorable_rate": rate(sum(1 for r in items if r["favorable_first"]), n),
                "adverse_rate": rate(sum(1 for r in items if r["adverse_first"]), n),
                "timeout_rate": rate(sum(1 for r in items if r["timeout"]), n),
                "mean_side_return_bps": mean([r["side_return_bps"] for r in items]),
                "median_side_return_bps": median([r["side_return_bps"] for r in items]),
                "mean_wall_score": mean([r["wall_score_vs_avg_level"] for r in items]),
                "mean_wall_distance_bps": mean([r["wall_distance_bps"] for r in items]),
                "wall_survival_rate_30_events": rate(sum(1 for r in items if r["wall_survives_30_events"]), n),
                "mean_depth_pressure_aligned": mean([r["depth_pressure_aligned"] for r in items]),
                "mean_active_pressure_against_wall": mean([r["active_pressure_against_wall"] for r in items]),
                "max_date_share": max(Counter(r["date"] for r in items).values()) / n if n else 0.0,
                "max_symbol_share": max(Counter(r["symbol"] for r in items).values()) / n if n else 0.0,
                "guardrail": GUARDRAIL,
            }
        )
    return out


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def svg_header(width, height, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="#F8FAFC"/>\n'
        f'<text x="30" y="36" font-size="20" font-family="Georgia,serif" font-weight="700" fill="#0F172A">{html.escape(title)}</text>\n'
    )


def legend(x, y, items):
    out = ""
    for i, (label, color) in enumerate(items):
        yy = y + i * 20
        out += f'<rect x="{x}" y="{yy}" width="12" height="12" fill="{color}" rx="2"/>\n'
        out += f'<text x="{x+18}" y="{yy+11}" font-size="12" fill="#334155">{html.escape(label)}</text>\n'
    return out


def axis(x, y, w, h):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#CBD5E1"/>\n'
        f'<line x1="{x}" y1="{y+h}" x2="{x+w}" y2="{y+h}" stroke="#64748B"/>\n'
        f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+h}" stroke="#64748B"/>\n'
    )


def write_wall_path_svg(path, summary):
    rows = [r for r in summary if r["control_type"] == "base"]
    width, height = 900, 440
    x, y, w, h = 90, 70, 650, 260
    group_w = w / max(1, len(rows))
    svg = svg_header(width, height, "Native Order Walls: Path Mix")
    svg += axis(x, y, w, h)
    for i, row in enumerate(rows):
        vals = [
            ("fav", row["favorable_rate"], "#287C5E"),
            ("adv", row["adverse_rate"], "#B84A4A"),
            ("timeout", row["timeout_rate"], "#94A3B8"),
        ]
        for j, (_, value, color) in enumerate(vals):
            bh = value * h
            bx = x + i * group_w + 18 + j * group_w * 0.20
            svg += f'<rect x="{bx:.1f}" y="{y+h-bh:.1f}" width="{group_w*0.16:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>\n'
        svg += f'<text x="{x+i*group_w+group_w*0.35:.1f}" y="{y+h+30}" font-size="12" fill="#334155">{row["wall_side"]}</text>\n'
    svg += legend(760, 24, [("fav", "#287C5E"), ("adv", "#B84A4A"), ("timeout", "#94A3B8")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_wall_score_svg(path, events):
    width, height = 900, 480
    x, y, w, h = 90, 70, 690, 300
    base = [r for r in events if r["control_type"] == "base"]
    max_score = max([r["wall_score_vs_avg_level"] for r in base] + [1.0])
    max_abs_ret = max([abs(r["side_return_bps"]) for r in base] + [1.0])
    svg = svg_header(width, height, "Native Order Walls: Wall Score vs Path Return")
    svg += axis(x, y, w, h)
    mid_y = y + h / 2
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#CBD5E1"/>\n'
    for r in base:
        px = x + r["wall_score_vs_avg_level"] / max_score * w
        py = mid_y - r["side_return_bps"] / max_abs_ret * h * 0.45
        color = "#2563EB" if r["wall_side"] == "bid" else "#D97706"
        svg += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{color}" opacity="0.45"/>\n'
    svg += '<text x="90" y="410" font-size="12" fill="#475569">x: wall score vs average level, y: side return bps</text>\n'
    svg += legend(740, 24, [("bid wall", "#2563EB"), ("ask wall", "#D97706")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_control_svg(path, summary):
    base = {(r["wall_side"]): r for r in summary if r["control_type"] == "base"}
    rows = [r for r in summary if r["control_type"] != "base"]
    width, height = 1100, 500
    x, y, w, h = 80, 70, 900, 280
    max_abs = max([abs(r["mean_side_return_bps"]) for r in summary] + [1.0])
    group_w = w / max(1, len(rows))
    mid_y = y + h / 2
    svg = svg_header(width, height, "Native Order Walls: Base vs Controls")
    svg += axis(x, y, w, h)
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#334155"/>\n'
    for i, r in enumerate(rows):
        b = base.get(r["wall_side"])
        base_v = b["mean_side_return_bps"] if b else 0.0
        ctrl_v = r["mean_side_return_bps"]
        bx = x + i * group_w + 4
        for j, (v, color) in enumerate([(base_v, "#2563EB"), (ctrl_v, "#D97706")]):
            bh = abs(v) / max_abs * h * 0.45
            by = mid_y - bh if v >= 0 else mid_y
            svg += f'<rect x="{bx+j*group_w*0.28:.1f}" y="{by:.1f}" width="{group_w*0.22:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>\n'
        label = f'{r["wall_side"]}:{r["control_type"]}'
        svg += f'<text x="{bx+group_w*0.2:.1f}" y="{y+h+92}" transform="rotate(-45 {bx+group_w*0.2:.1f} {y+h+92})" font-size="9" fill="#334155">{html.escape(label)}</text>\n'
    svg += legend(920, 24, [("base", "#2563EB"), ("control", "#D97706")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_report(path, run_tag, parts, base_events, controls, summary, outputs):
    base_summary = [r for r in summary if r["control_type"] == "base"]
    control_bad = 0
    by_base = {r["wall_side"]: r for r in base_summary}
    for row in summary:
        if row["control_type"] == "base":
            continue
        base = by_base.get(row["wall_side"])
        if base and abs(row["mean_side_return_bps"]) >= abs(base["mean_side_return_bps"]):
            control_bad += 1
    lines = [
        "# BONK V15 Native Order-Wall Microstructure Analysis",
        "",
        f"- run_tag: `{run_tag}`",
        f"- guardrail: `{GUARDRAIL}`",
        "- stance: research-only diagnostics; no trading advice, no execution recommendation, no alpha claim.",
        "- method: native order-wall first; Fibonacci is not used to select events.",
        "",
        "## What Changed",
        "",
        "- This report finds walls directly from `bid_top_levels_json` / `ask_top_levels_json`.",
        f"- A wall is a level whose amount is at least `{WALL_SCORE_MIN:.1f}x` the average amount of that side's top levels.",
        "- A touch event is kept only when mid is within `max(1.5 bps, 2 * spread_bps)` of that wall.",
        "",
        "## Spread & Liquidity",
        "",
        f"- panel parts: `{len(parts)}`",
        f"- native wall base events: `{len(base_events)}`",
        f"- control events: `{len(controls)}`",
        "",
        "## Order Walls",
        "",
    ]
    for row in base_summary:
        lines.extend(
            [
                f"- `{row['wall_side']}` wall events: `{row['events']}`",
                f"  mean wall score: `{row['mean_wall_score']:.4f}x`; mean distance: `{row['mean_wall_distance_bps']:.4f}` bps; survival 30 events: `{row['wall_survival_rate_30_events']:.4f}`",
                f"  favorable/adverse/timeout: `{row['favorable_rate']:.4f}` / `{row['adverse_rate']:.4f}` / `{row['timeout_rate']:.4f}`",
                f"  mean side return: `{row['mean_side_return_bps']:.4f}` bps; max_date_share: `{row['max_date_share']:.4f}`",
            ]
        )
    lines.extend(
        [
            "",
            f"![Wall path mix]({outputs['path_svg'].as_posix()})",
            "",
            f"![Wall score scatter]({outputs['score_svg'].as_posix()})",
            "",
            "## Negative Controls",
            "",
            f"- controls with abs(control mean) >= abs(base mean): `{control_bad}`",
            "- If timestamp/wrong-symbol controls stay close, the wall is mostly identifying market state, not a standalone wall reaction.",
            "",
            f"![Wall controls]({outputs['control_svg'].as_posix()})",
            "",
            "## Outputs",
            "",
            f"- events CSV: `{outputs['events_csv'].as_posix()}`",
            f"- summary CSV: `{outputs['summary_csv'].as_posix()}`",
            f"- controls CSV: `{outputs['controls_csv'].as_posix()}`",
            "",
            "## Bottom Line",
            "",
            "This is the cleaner wall-first analysis. It should replace the earlier wording where Fibonacci and walls were blended together. The first question is now whether actual detected walls survive and alter path distribution; only after that should any Fibonacci confluence be considered.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/bonk/v1")
    parser.add_argument("--date-dir", default="date")
    parser.add_argument("--doc-dir", default="docs/markets/bonk")
    parser.add_argument("--run-tag", default="20260514_bonk_v10_stage1_pilot")
    parser.add_argument("--symbols", default="BONK1MUSDC,BONK1MUSDT")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    date_dir = Path(args.date_dir)
    doc_dir = Path(args.doc_dir)
    fig_dir = doc_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    intervals = load_folds(date_dir / f"bonk_v10_filter_params_{args.run_tag}.csv", args.run_tag, symbols)
    parts, by_symbol = load_panel(data_root, args.run_tag, symbols)
    base_events, control_events_ = build_events(args.run_tag, by_symbol, intervals)
    all_events = base_events + control_events_
    summary = summarize(all_events)

    outputs = {
        "events_csv": date_dir / f"bonk_v15_native_order_wall_events_{args.run_tag}.csv",
        "summary_csv": date_dir / f"bonk_v15_native_order_wall_summary_{args.run_tag}.csv",
        "controls_csv": date_dir / f"bonk_v15_native_order_wall_controls_{args.run_tag}.csv",
        "path_svg": fig_dir / f"bonk_v15_native_order_wall_path_mix_{args.run_tag}.svg",
        "score_svg": fig_dir / f"bonk_v15_native_order_wall_score_scatter_{args.run_tag}.svg",
        "control_svg": fig_dir / f"bonk_v15_native_order_wall_controls_{args.run_tag}.svg",
        "report_md": doc_dir / "v1-cex-v15-native-order-wall-analysis.md",
    }
    write_csv(outputs["events_csv"], all_events)
    write_csv(outputs["summary_csv"], summary)
    write_csv(outputs["controls_csv"], control_events_)
    write_wall_path_svg(outputs["path_svg"], summary)
    write_wall_score_svg(outputs["score_svg"], all_events)
    write_control_svg(outputs["control_svg"], summary)
    write_report(outputs["report_md"], args.run_tag, parts, base_events, control_events_, summary, outputs)

    print(f"panel_parts={len(parts)}")
    print(f"symbols={len(by_symbol)}")
    print(f"base_events={len(base_events)}")
    print(f"control_events={len(control_events_)}")
    print(f"summary_rows={len(summary)}")
    print(f"report_md={outputs['report_md']}")


if __name__ == "__main__":
    main()
