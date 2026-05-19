#!/usr/bin/env python3
"""Longbridge-style microstructure diagnostics for BONK V15 level events."""

from __future__ import annotations

import argparse
import csv
import glob
import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"


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


def median(values):
    values = sorted(v for v in values if math.isfinite(v))
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return 0.5 * (values[mid - 1] + values[mid])


def mean(values):
    values = [v for v in values if math.isfinite(v)]
    if not values:
        return 0.0
    return sum(values) / len(values)


def ratio(a, b):
    denom = abs(a) + abs(b)
    return 0.0 if denom <= 1e-12 else max(-1.0, min(1.0, (a - b) / denom))


def load_base_events(path: Path):
    rows = []
    keys = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("negative_control_type") != "base":
                continue
            rows.append(row)
            keys.add(
                (
                    row.get("date", ""),
                    row.get("symbol", ""),
                    inum(row.get("event_index")),
                    inum(row.get("event_ts")),
                )
            )
    return rows, keys


def load_controls(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_levels(raw):
    try:
        levels = json.loads(raw or "[]")
        return [
            (fnum(level[0]), fnum(level[1]))
            for level in levels
            if isinstance(level, list) and len(level) >= 2
        ]
    except Exception:
        return []


def wall_score(levels):
    amounts = [amount for _, amount in levels if amount > 0]
    if not amounts:
        return 0.0
    avg = sum(amounts) / len(amounts)
    if avg <= 1e-12:
        return 0.0
    return max(amounts) / avg


def nearest_wall(levels, level_price, mid_price):
    if not levels or mid_price <= 0:
        return 0.0, 0.0, 0.0
    amounts = [amount for _, amount in levels if amount > 0]
    avg = sum(amounts) / len(amounts) if amounts else 0.0
    best = min(levels, key=lambda item: abs(item[0] - level_price))
    dist_bps = abs(best[0] - level_price) / mid_price * 10_000.0
    score = best[1] / avg if avg > 1e-12 else 0.0
    return best[0], dist_bps, score


def stream_panel(data_root: Path, run_tag: str, symbols, event_keys):
    base = data_root / "derived" / "bonk_v10c_event_ofi_panel" / f"run_tag={run_tag}"
    parts = []
    for symbol in symbols:
        parts.extend(glob.glob(str(base / f"symbol={symbol}" / "**" / "part_*.csv"), recursive=True))
    parts = sorted(parts)
    daily = defaultdict(lambda: defaultdict(list))
    daily_sum = defaultdict(lambda: defaultdict(float))
    event_panel = {}
    for part in parts:
        with open(part, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                date = row.get("date", "")
                symbol = row.get("symbol", "")
                key = (date, symbol)
                spread = fnum(row.get("spread_bps"))
                bid_depth = fnum(row.get("bid_depth_25"))
                ask_depth = fnum(row.get("ask_depth_25"))
                depth = bid_depth + ask_depth
                qimb = fnum(row.get("queue_imbalance_25"))
                buy = fnum(row.get("trade_buy_amount"))
                sell = fnum(row.get("trade_sell_amount"))
                daily[key]["spread_bps"].append(spread)
                daily[key]["depth_25"].append(depth)
                daily[key]["queue_imbalance_25"].append(qimb)
                daily[key]["mlofi_roll10_l10"].append(fnum(row.get("mlofi_roll10_l10")))
                daily[key]["liquidity_shock_score"].append(fnum(row.get("liquidity_shock_score")))
                daily_sum[key]["rows"] += 1
                daily_sum[key]["buy_amount"] += buy
                daily_sum[key]["sell_amount"] += sell
                daily_sum[key]["trade_count"] += inum(row.get("trade_window_count"))
                daily_sum[key]["trade_notional"] += fnum(row.get("trade_notional_quote"))
                daily_sum[key]["snapshot_rows"] += 1 if row.get("is_snapshot_batch") == "true" else 0
                daily_sum[key]["crossed_removed"] += inum(row.get("crossed_levels_removed"))
                ekey = (
                    date,
                    symbol,
                    inum(row.get("event_index")),
                    inum(row.get("local_timestamp")),
                )
                if ekey in event_keys:
                    event_panel[ekey] = row
    daily_rows = []
    for (date, symbol), cols in sorted(daily.items()):
        sums = daily_sum[(date, symbol)]
        buy = sums["buy_amount"]
        sell = sums["sell_amount"]
        daily_rows.append(
            {
                "date": date,
                "symbol": symbol,
                "rows": int(sums["rows"]),
                "spread_bps_mean": mean(cols["spread_bps"]),
                "spread_bps_median": median(cols["spread_bps"]),
                "depth_25_mean": mean(cols["depth_25"]),
                "depth_25_median": median(cols["depth_25"]),
                "depth_asymmetry_mean": mean(cols["queue_imbalance_25"]),
                "buy_initiated_amount_ratio": buy / (buy + sell) if buy + sell > 0 else 0.0,
                "large_order_net_pressure": buy - sell,
                "trade_count": int(sums["trade_count"]),
                "trade_notional": sums["trade_notional"],
                "mlofi_roll10_l10_mean": mean(cols["mlofi_roll10_l10"]),
                "liquidity_shock_score_mean": mean(cols["liquidity_shock_score"]),
                "snapshot_row_rate": sums["snapshot_rows"] / sums["rows"] if sums["rows"] else 0.0,
                "crossed_removed_per_1k": sums["crossed_removed"] / sums["rows"] * 1000.0
                if sums["rows"]
                else 0.0,
                "guardrail": GUARDRAIL,
            }
        )
    return parts, daily_rows, event_panel


def enrich_events(events, event_panel):
    out = []
    for event in events:
        key = (
            event.get("date", ""),
            event.get("symbol", ""),
            inum(event.get("event_index")),
            inum(event.get("event_ts")),
        )
        panel = event_panel.get(key, {})
        bid_levels = parse_levels(panel.get("bid_top_levels_json"))
        ask_levels = parse_levels(panel.get("ask_top_levels_json"))
        side_sign = inum(event.get("side_sign"))
        level_price = fnum(event.get("level_price"))
        mid = fnum(event.get("mid_price"))
        if side_sign >= 0:
            defending = bid_levels
            opposing = ask_levels
            defending_name = "bid"
        else:
            defending = ask_levels
            opposing = bid_levels
            defending_name = "ask"
        _, defending_dist, defending_near_score = nearest_wall(defending, level_price, mid)
        _, opposing_dist, opposing_near_score = nearest_wall(opposing, level_price, mid)
        buy = fnum(panel.get("trade_buy_amount"))
        sell = fnum(panel.get("trade_sell_amount"))
        active_pressure = ratio(buy, sell) * (1 if side_sign >= 0 else -1)
        enriched = {
            "run_tag": event.get("run_tag", ""),
            "variant": event.get("variant", ""),
            "date": event.get("date", ""),
            "symbol": event.get("symbol", ""),
            "event_index": event.get("event_index", ""),
            "side": event.get("side", ""),
            "path_label": event.get("path_label", ""),
            "favorable_first": event.get("favorable_first", ""),
            "side_return_bps": fnum(event.get("side_return_bps")),
            "spread_bps": fnum(event.get("spread_bps")),
            "depth_asymmetry": fnum(event.get("queue_imbalance_25")),
            "mlofi_roll10_l10": fnum(event.get("mlofi_roll10_l10")),
            "trade_flow_imbalance": fnum(event.get("trade_flow_imbalance")),
            "book_confirm_score": fnum(event.get("book_confirm_score")),
            "absorption_score": fnum(event.get("absorption_score")),
            "active_pressure": active_pressure,
            "buy_initiated_amount_ratio": buy / (buy + sell) if buy + sell > 0 else 0.0,
            "defending_side": defending_name,
            "defending_wall_score": wall_score(defending),
            "opposing_wall_score": wall_score(opposing),
            "defending_nearest_wall_dist_bps": defending_dist,
            "defending_nearest_wall_score": defending_near_score,
            "opposing_nearest_wall_dist_bps": opposing_dist,
            "opposing_nearest_wall_score": opposing_near_score,
            "execute_cancel_confidence": event.get("execute_cancel_confidence", ""),
            "snapshot_batch": event.get("snapshot_batch", ""),
            "guardrail": GUARDRAIL,
        }
        out.append(enriched)
    return out


def group_event_summary(event_rows):
    grouped = defaultdict(list)
    for row in event_rows:
        grouped[row["variant"]].append(row)
    out = []
    for variant, rows in sorted(grouped.items()):
        n = len(rows)
        out.append(
            {
                "variant": variant,
                "events": n,
                "favorable_rate": sum(1 for r in rows if r["favorable_first"] == "true") / n if n else 0.0,
                "mean_side_return_bps": mean([r["side_return_bps"] for r in rows]),
                "mean_spread_bps": mean([r["spread_bps"] for r in rows]),
                "mean_depth_asymmetry": mean([r["depth_asymmetry"] for r in rows]),
                "mean_active_pressure": mean([r["active_pressure"] for r in rows]),
                "mean_book_confirm_score": mean([r["book_confirm_score"] for r in rows]),
                "mean_absorption_score": mean([r["absorption_score"] for r in rows]),
                "mean_defending_wall_score": mean([r["defending_wall_score"] for r in rows]),
                "mean_defending_nearest_wall_score": mean(
                    [r["defending_nearest_wall_score"] for r in rows]
                ),
                "mean_defending_nearest_wall_dist_bps": mean(
                    [r["defending_nearest_wall_dist_bps"] for r in rows]
                ),
                "max_date_share": max(Counter(r["date"] for r in rows).values()) / n if n else 0.0,
                "max_symbol_share": max(Counter(r["symbol"] for r in rows).values()) / n if n else 0.0,
                "guardrail": GUARDRAIL,
            }
        )
    return out


def write_csv(path: Path, rows):
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
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="#F8FAFC"/>\n'
        f'<text x="30" y="36" font-size="20" font-family="Georgia,serif" '
        f'font-weight="700" fill="#0F172A">{html.escape(title)}</text>\n'
    )


def svg_axis(x, y, w, h):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#CBD5E1"/>\n'
        f'<line x1="{x}" y1="{y+h}" x2="{x+w}" y2="{y+h}" stroke="#64748B"/>\n'
        f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+h}" stroke="#64748B"/>\n'
    )


def write_spread_liquidity_svg(path: Path, daily_rows):
    width, height = 1120, 520
    x, y, w, h = 80, 72, 940, 310
    rows = daily_rows
    max_spread = max([r["spread_bps_median"] for r in rows] + [1.0])
    max_depth = max([r["depth_25_median"] for r in rows] + [1.0])
    group_w = w / max(1, len(rows))
    svg = svg_header(width, height, "BONK Microstructure: Spread and Liquidity by Symbol-Day")
    svg += svg_axis(x, y, w, h)
    for i, r in enumerate(rows):
        bx = x + i * group_w + 4
        spread_h = r["spread_bps_median"] / max_spread * h
        depth_h = r["depth_25_median"] / max_depth * h
        svg += (
            f'<rect x="{bx:.1f}" y="{y+h-spread_h:.1f}" width="{group_w*0.32:.1f}" '
            f'height="{spread_h:.1f}" fill="#D97706" rx="3"/>\n'
            f'<rect x="{bx+group_w*0.36:.1f}" y="{y+h-depth_h:.1f}" width="{group_w*0.32:.1f}" '
            f'height="{depth_h:.1f}" fill="#2563EB" rx="3"/>\n'
        )
        label = f'{r["date"][5:]} {r["symbol"].replace("BONK1M", "")}'
        svg += (
            f'<text x="{bx+group_w*0.35:.1f}" y="{y+h+72:.1f}" transform="rotate(-45 '
            f'{bx+group_w*0.35:.1f} {y+h+72:.1f})" font-size="10" fill="#334155">'
            f"{html.escape(label)}</text>\n"
        )
    svg += legend(800, 24, [("median spread", "#D97706"), ("median depth25", "#2563EB")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_flow_depth_svg(path: Path, event_summary):
    width, height = 900, 520
    x, y, w, h = 90, 70, 700, 330
    max_abs_x = max([abs(r["mean_depth_asymmetry"]) for r in event_summary] + [0.1])
    max_abs_y = max([abs(r["mean_active_pressure"]) for r in event_summary] + [0.1])
    max_n = max([r["events"] for r in event_summary] + [1])
    svg = svg_header(width, height, "V15 Level Events: Depth Asymmetry vs Active Pressure")
    svg += svg_axis(x, y, w, h)
    mid_x, mid_y = x + w / 2, y + h / 2
    svg += f'<line x1="{mid_x}" y1="{y}" x2="{mid_x}" y2="{y+h}" stroke="#CBD5E1"/>\n'
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#CBD5E1"/>\n'
    for r in event_summary:
        px = mid_x + (r["mean_depth_asymmetry"] / max_abs_x) * (w * 0.42)
        py = mid_y - (r["mean_active_pressure"] / max_abs_y) * (h * 0.42)
        radius = 9 + 22 * math.sqrt(r["events"] / max_n)
        color = "#287C5E" if r["mean_side_return_bps"] >= 0 else "#B84A4A"
        svg += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{radius:.1f}" fill="{color}" opacity="0.72"/>\n'
        svg += (
            f'<text x="{px+radius+4:.1f}" y="{py+4:.1f}" font-size="12" fill="#0F172A">'
            f'{html.escape(r["variant"])}</text>\n'
        )
    svg += '<text x="90" y="435" font-size="12" fill="#475569">x: depth asymmetry, y: active trade pressure aligned with event side, bubble: event count</text>\n'
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_event_confirmation_svg(path: Path, event_summary):
    width, height = 980, 520
    x, y, w, h = 90, 72, 780, 300
    svg = svg_header(width, height, "V15 Event Confirmation Scores")
    svg += svg_axis(x, y, w, h)
    max_abs = max(
        [
            abs(v)
            for r in event_summary
            for v in (
                r["mean_book_confirm_score"],
                r["mean_absorption_score"],
                r["mean_side_return_bps"] / 10.0,
            )
        ]
        + [1.0]
    )
    group_w = w / max(1, len(event_summary))
    mid_y = y + h / 2
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#334155"/>\n'
    colors = [("#2563EB", "book"), ("#7C3AED", "absorption"), ("#287C5E", "return/10")]
    for i, r in enumerate(event_summary):
        vals = [r["mean_book_confirm_score"], r["mean_absorption_score"], r["mean_side_return_bps"] / 10.0]
        for j, value in enumerate(vals):
            bar_h = abs(value) / max_abs * h * 0.42
            bx = x + i * group_w + 12 + j * group_w * 0.22
            by = mid_y - bar_h if value >= 0 else mid_y
            svg += (
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{group_w*0.17:.1f}" height="{bar_h:.1f}" '
                f'fill="{colors[j][0]}" rx="3"/>\n'
            )
        label_x = x + i * group_w + group_w * 0.35
        svg += (
            f'<text x="{label_x:.1f}" y="{y+h+78:.1f}" transform="rotate(-35 {label_x:.1f} {y+h+78:.1f})" '
            f'font-size="10" fill="#334155">{html.escape(r["variant"])}</text>\n'
        )
    svg += legend(710, 24, colors)
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_date_concentration_svg(path: Path, event_rows):
    width, height = 980, 500
    x, y, w, h = 80, 70, 820, 300
    counts = Counter(r["date"] for r in event_rows)
    returns = defaultdict(list)
    for r in event_rows:
        returns[r["date"]].append(r["side_return_bps"])
    dates = sorted(counts)
    max_count = max(counts.values() or [1])
    max_abs_ret = max([abs(mean(returns[d])) for d in dates] + [1.0])
    group_w = w / max(1, len(dates))
    svg = svg_header(width, height, "V15 Base Events: Date Concentration and Mean Return")
    svg += svg_axis(x, y, w, h)
    for i, d in enumerate(dates):
        bx = x + i * group_w + 10
        count_h = counts[d] / max_count * h
        ret = mean(returns[d])
        ret_h = abs(ret) / max_abs_ret * h
        ret_color = "#287C5E" if ret >= 0 else "#B84A4A"
        svg += f'<rect x="{bx:.1f}" y="{y+h-count_h:.1f}" width="{group_w*0.32:.1f}" height="{count_h:.1f}" fill="#94A3B8" rx="3"/>\n'
        svg += f'<rect x="{bx+group_w*0.38:.1f}" y="{y+h-ret_h:.1f}" width="{group_w*0.32:.1f}" height="{ret_h:.1f}" fill="{ret_color}" rx="3"/>\n'
        svg += f'<text x="{bx+group_w*0.3:.1f}" y="{y+h+25:.1f}" font-size="11" fill="#334155">{html.escape(d[5:])}</text>\n'
    svg += legend(720, 24, [("event count", "#94A3B8"), ("abs mean return", "#287C5E")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def legend(x, y, items):
    out = ""
    for i, (label, color) in enumerate(items):
        yy = y + i * 20
        out += f'<rect x="{x}" y="{yy}" width="12" height="12" fill="{color}" rx="2"/>\n'
        out += f'<text x="{x+18}" y="{yy+11}" font-size="12" fill="#334155">{html.escape(label)}</text>\n'
    return out


def write_report(path, run_tag, panel_parts, daily_rows, event_summary, controls, outputs):
    def p(value):
        return Path(value).as_posix()

    best = max(event_summary, key=lambda r: r["mean_side_return_bps"], default=None)
    control_bad = [c for c in controls if c.get("control_abs_ge_base_abs") == "true"]
    lines = [
        "# BONK V15 Longbridge-Style Microstructure Analysis",
        "",
        f"- run_tag: `{run_tag}`",
        f"- guardrail: `{GUARDRAIL}`",
        "- stance: research-only diagnostics; no trading advice, no execution recommendation, no alpha claim.",
        "- note: this applies the `longbridge-market-microstructure` framework to local BONK V10c historical event panels rather than Longbridge live CLI snapshots.",
        "",
        "## 价差与流动性",
        "",
        f"- panel part files: `{len(panel_parts)}`",
        f"- symbol-days: `{len(daily_rows)}`",
        f"- median spread range: `{min(r['spread_bps_median'] for r in daily_rows):.4f}` to `{max(r['spread_bps_median'] for r in daily_rows):.4f}` bps",
        f"- median depth25 range: `{min(r['depth_25_median'] for r in daily_rows):.4f}` to `{max(r['depth_25_median'] for r in daily_rows):.4f}`",
        "",
        f"![Spread and liquidity]({p(outputs['spread_svg'])})",
        "",
        "## 盘口不对称",
        "",
        "- `queue_imbalance_25` is used as the local depth asymmetry proxy: positive means bid-side depth dominates, negative means ask-side depth dominates.",
        "- In V15 level events, asymmetry is not yet sufficient as a standalone discriminator; the strongest rows still have high date concentration.",
        "",
        f"![Flow depth quadrant]({p(outputs['flow_svg'])})",
        "",
        "## 订单流压力",
        "",
        "- `trade_buy_amount / trade_sell_amount`, `trade_flow_imbalance`, and `mlofi_roll10_l10` are used as active-flow pressure proxies.",
        "- The visual result says the event timestamps are often inside a common directional state; controls must separate this before any factor claim.",
        "",
        "## 挂单墙",
        "",
        "- Top-of-book JSON is parsed around V15 base events. The report estimates defending-side wall score and nearest-wall distance to the dynamic level.",
        "- Current evidence is diagnostic only: walls help explain some touches, but same-time/wrong-symbol controls are still too strong.",
        "",
        f"![Confirmation scores]({p(outputs['confirm_svg'])})",
        "",
        "## 短线方向偏向",
        "",
    ]
    if best:
        lines.extend(
            [
                f"- strongest base variant by mean path return: `{best['variant']}`",
                f"- events: `{best['events']}`",
                f"- favorable rate: `{best['favorable_rate']:.4f}`",
                f"- mean side return: `{best['mean_side_return_bps']:.4f}` bps",
                f"- max date share: `{best['max_date_share']:.4f}`",
                f"- max symbol share: `{best['max_symbol_share']:.4f}`",
            ]
        )
    lines.extend(
        [
            f"- negative controls with abs(control) >= abs(base): `{len(control_bad)}` / `{len(controls)}`",
            "- interpretation: if wrong-symbol or same-anchor controls are close to base, the signal is probably common market state or event-time trend, not unique level geometry.",
            "",
            f"![Date concentration]({p(outputs['date_svg'])})",
            "",
            "## Outputs",
            "",
            f"- daily microstructure CSV: `{p(outputs['daily_csv'])}`",
            f"- event confirmation CSV: `{p(outputs['event_csv'])}`",
            f"- event summary CSV: `{p(outputs['summary_csv'])}`",
            "",
            "## Bottom Line",
            "",
            "This microstructure pass supports the V15 interpretation: the charts show real directional/event-time structure, but they do not yet prove Fibonacci or order-book levels are independently causal. The next useful step is stricter random-touch controls within the same date/regime and beta-neutral wrong-symbol adjustment.",
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

    events_path = date_dir / f"bonk_v15_fib_rsi_book_events_{args.run_tag}.csv"
    controls_path = date_dir / f"bonk_v15_fib_rsi_book_negative_controls_{args.run_tag}.csv"
    events, keys = load_base_events(events_path)
    controls = load_controls(controls_path)
    panel_parts, daily_rows, event_panel = stream_panel(data_root, args.run_tag, symbols, keys)
    event_rows = enrich_events(events, event_panel)
    event_summary = group_event_summary(event_rows)

    outputs = {
        "daily_csv": date_dir / f"bonk_v15_microstructure_skill_daily_{args.run_tag}.csv",
        "event_csv": date_dir / f"bonk_v15_microstructure_skill_events_{args.run_tag}.csv",
        "summary_csv": date_dir / f"bonk_v15_microstructure_skill_summary_{args.run_tag}.csv",
        "spread_svg": fig_dir / f"bonk_v15_microstructure_spread_liquidity_{args.run_tag}.svg",
        "flow_svg": fig_dir / f"bonk_v15_microstructure_flow_depth_{args.run_tag}.svg",
        "confirm_svg": fig_dir / f"bonk_v15_microstructure_confirmation_{args.run_tag}.svg",
        "date_svg": fig_dir / f"bonk_v15_microstructure_date_concentration_{args.run_tag}.svg",
        "report_md": doc_dir / "v1-cex-v15-longbridge-microstructure-analysis.md",
    }

    write_csv(outputs["daily_csv"], daily_rows)
    write_csv(outputs["event_csv"], event_rows)
    write_csv(outputs["summary_csv"], event_summary)
    write_spread_liquidity_svg(outputs["spread_svg"], daily_rows)
    write_flow_depth_svg(outputs["flow_svg"], event_summary)
    write_event_confirmation_svg(outputs["confirm_svg"], event_summary)
    write_date_concentration_svg(outputs["date_svg"], event_rows)
    write_report(outputs["report_md"], args.run_tag, panel_parts, daily_rows, event_summary, controls, outputs)

    print(f"panel_parts={len(panel_parts)}")
    print(f"base_events={len(events)}")
    print(f"event_panel_matches={len(event_panel)}")
    print(f"daily_rows={len(daily_rows)}")
    print(f"event_summary_rows={len(event_summary)}")
    print(f"report_md={outputs['report_md']}")
    for key in ["spread_svg", "flow_svg", "confirm_svg", "date_svg"]:
        print(f"{key}={outputs[key]}")


if __name__ == "__main__":
    main()
