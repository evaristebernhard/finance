#!/usr/bin/env python3
"""Technical-analysis diagnostics for BONK V10c panels.

This report follows the technical-analysis skill posture:
- price structure first;
- RSI is context/filter, not a standalone predictor;
- Fibonacci levels are zones, not exact prices;
- every pattern gets statistical/path diagnostics and controls.
"""

from __future__ import annotations

import argparse
import csv
import glob
import html
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"
FIB_RATIOS = (0.382, 0.500, 0.618, 0.786)
EXT_RATIOS = (1.272, 1.618)
BAR_SIZE_EVENTS = 300
SWING_LOOKBACK_BARS = 48
PATH_HORIZON_BARS = 12
EVENT_GAP_BARS = 6


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


@dataclass
class Bar:
    run_tag: str
    symbol: str
    date: str
    bar_id: int
    start_ts: int
    end_ts: int
    start_event_index: int
    end_event_index: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    rows: int = 0
    spread_sum: float = 0.0
    qimb_sum: float = 0.0
    mlofi_sum: float = 0.0
    trade_flow_sum: float = 0.0
    vwap: float = 0.0
    rsi_fast: float = 50.0
    rsi_slow: float = 50.0
    rsi_diff: float = 0.0
    rsi_diff_delta: float = 0.0
    volume_sma20: float = 0.0
    structure_state: str = "unknown"

    @classmethod
    def first(cls, raw):
        mid = fnum(raw.get("mid_price"))
        return cls(
            run_tag=raw.get("run_tag", ""),
            symbol=raw.get("symbol", ""),
            date=raw.get("date", ""),
            bar_id=inum(raw.get("event_index")) // BAR_SIZE_EVENTS,
            start_ts=inum(raw.get("local_timestamp")),
            end_ts=inum(raw.get("local_timestamp")),
            start_event_index=inum(raw.get("event_index")),
            end_event_index=inum(raw.get("event_index")),
            open=mid,
            high=mid,
            low=mid,
            close=mid,
        )

    def update(self, raw):
        mid = fnum(raw.get("mid_price"))
        if mid <= 0:
            return
        self.end_ts = inum(raw.get("local_timestamp"))
        self.end_event_index = inum(raw.get("event_index"))
        self.high = max(self.high, mid)
        self.low = min(self.low, mid)
        self.close = mid
        self.volume += fnum(raw.get("trade_notional_quote"))
        self.rows += 1
        self.spread_sum += fnum(raw.get("spread_bps"))
        self.qimb_sum += fnum(raw.get("queue_imbalance_25"))
        self.mlofi_sum += fnum(raw.get("mlofi_roll10_l10"))
        self.trade_flow_sum += fnum(raw.get("trade_flow_imbalance"))

    @property
    def spread_mean(self):
        return self.spread_sum / self.rows if self.rows else 0.0

    @property
    def qimb_mean(self):
        return self.qimb_sum / self.rows if self.rows else 0.0

    @property
    def mlofi_mean(self):
        return self.mlofi_sum / self.rows if self.rows else 0.0

    @property
    def trade_flow_mean(self):
        return self.trade_flow_sum / self.rows if self.rows else 0.0


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


def load_bars(data_root: Path, run_tag: str, symbols):
    base = data_root / "derived" / "bonk_v10c_event_ofi_panel" / f"run_tag={run_tag}"
    parts = []
    for symbol in symbols:
        parts.extend(glob.glob(str(base / f"symbol={symbol}" / "**" / "part_*.csv"), recursive=True))
    grouped: dict[tuple[str, str, int], Bar] = {}
    for part in sorted(parts):
        with open(part, newline="", encoding="utf-8") as f:
            for raw in csv.DictReader(f):
                if raw.get("run_tag") != run_tag:
                    continue
                mid = fnum(raw.get("mid_price"))
                if mid <= 0:
                    continue
                key = (
                    raw.get("symbol", ""),
                    raw.get("date", ""),
                    inum(raw.get("event_index")) // BAR_SIZE_EVENTS,
                )
                if key not in grouped:
                    grouped[key] = Bar.first(raw)
                grouped[key].update(raw)
    by_symbol = defaultdict(list)
    for bar in grouped.values():
        by_symbol[bar.symbol].append(bar)
    for bars in by_symbol.values():
        bars.sort(key=lambda b: (b.start_ts, b.start_event_index))
        enrich_indicators(bars)
        enrich_structure(bars)
    return sorted(parts), by_symbol


def enrich_indicators(bars):
    gains14, losses14 = deque(), deque()
    gains42, losses42 = deque(), deque()
    vol20 = deque()
    prev_close = None
    prev_diff = 0.0
    day_cum_pv = defaultdict(float)
    day_cum_vol = defaultdict(float)
    for bar in bars:
        if prev_close is not None and prev_close > 0:
            ret = (bar.close - prev_close) / prev_close
            push_rsi(ret, gains14, losses14, 14)
            push_rsi(ret, gains42, losses42, 42)
        bar.rsi_fast = rsi(gains14, losses14)
        bar.rsi_slow = rsi(gains42, losses42)
        bar.rsi_diff = bar.rsi_fast - bar.rsi_slow
        bar.rsi_diff_delta = bar.rsi_diff - prev_diff
        prev_diff = bar.rsi_diff
        typical = (bar.high + bar.low + bar.close) / 3.0
        day_cum_pv[bar.date] += typical * max(bar.volume, 1.0)
        day_cum_vol[bar.date] += max(bar.volume, 1.0)
        bar.vwap = day_cum_pv[bar.date] / day_cum_vol[bar.date]
        vol20.append(bar.volume)
        while len(vol20) > 20:
            vol20.popleft()
        bar.volume_sma20 = mean(vol20)
        prev_close = bar.close


def push_rsi(ret, gains, losses, window):
    gains.append(max(ret, 0.0))
    losses.append(max(-ret, 0.0))
    while len(gains) > window:
        gains.popleft()
    while len(losses) > window:
        losses.popleft()


def rsi(gains, losses):
    if not gains:
        return 50.0
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss <= 1e-12:
        return 100.0 if avg_gain > 1e-12 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def enrich_structure(bars):
    for i, bar in enumerate(bars):
        if i < 2 * SWING_LOOKBACK_BARS:
            continue
        recent = bars[i - SWING_LOOKBACK_BARS : i]
        prev = bars[i - 2 * SWING_LOOKBACK_BARS : i - SWING_LOOKBACK_BARS]
        recent_high = max(b.high for b in recent)
        recent_low = min(b.low for b in recent)
        prev_high = max(b.high for b in prev)
        prev_low = min(b.low for b in prev)
        if recent_high > prev_high and recent_low > prev_low:
            bar.structure_state = "higher_high_higher_low"
        elif recent_high < prev_high and recent_low < prev_low:
            bar.structure_state = "lower_high_lower_low"
        elif bar.close > recent_high:
            bar.structure_state = "bullish_breakout"
        elif bar.close < recent_low:
            bar.structure_state = "bearish_breakdown"
        else:
            bar.structure_state = "range"


def trailing_swing(bars, i, lookback=SWING_LOOKBACK_BARS):
    start = max(0, i - lookback)
    window = bars[start:i]
    if len(window) < lookback // 2:
        return None
    low_idx, low_bar = min(enumerate(window, start), key=lambda item: item[1].low)
    high_idx, high_bar = max(enumerate(window, start), key=lambda item: item[1].high)
    if high_bar.high <= low_bar.low:
        return None
    direction = "up" if low_idx < high_idx else "down"
    return {
        "low": low_bar.low,
        "high": high_bar.high,
        "low_idx": low_idx,
        "high_idx": high_idx,
        "direction": direction,
        "range": high_bar.high - low_bar.low,
    }


def side_path(bars, i, side_sign, barrier_bps):
    entry = bars[i].close
    end = min(len(bars) - 1, i + PATH_HORIZON_BARS)
    mfe, mae = 0.0, 0.0
    first = None
    for j in range(i + 1, end + 1):
        ret = side_sign * (bars[j].close - entry) / entry * 10_000.0
        mfe = max(mfe, ret)
        mae = min(mae, ret)
        if first is None:
            if ret <= -barrier_bps:
                first = ("adverse_first", j - i)
            elif ret >= barrier_bps:
                first = ("favorable_first", j - i)
    side_return = side_sign * (bars[end].close - entry) / entry * 10_000.0
    label, latency = first if first else ("timeout", "")
    return {
        "path_label": label,
        "favorable_first": label == "favorable_first",
        "adverse_first": label == "adverse_first",
        "timeout": label == "timeout",
        "reaction_latency_bars": latency,
        "mfe_bps": mfe,
        "mae_bps": mae,
        "side_return_bps": side_return,
    }


def build_event(run_tag, fold, symbol, bars, i, pattern, side_sign, level_price, trigger, control_type="base", group_id=""):
    bar = bars[i]
    barrier = max(3.0, 1.5 * bar.spread_mean)
    dist_bps = (bar.close - level_price) / bar.close * 10_000.0 if bar.close else 0.0
    outcome = side_path(bars, i, side_sign, barrier)
    return {
        "run_tag": run_tag,
        "fold": fold,
        "date": bar.date,
        "symbol": symbol,
        "bar_index": i,
        "bar_id": bar.bar_id,
        "event_ts": bar.end_ts,
        "pattern": pattern,
        "control_type": control_type,
        "control_group_id": group_id,
        "side": "long" if side_sign > 0 else "short",
        "side_sign": side_sign,
        "close": bar.close,
        "level_price": level_price,
        "level_dist_bps": dist_bps,
        "touch_band_bps": max(5.0, 2.0 * bar.spread_mean),
        "trigger": trigger,
        "rsi_fast": bar.rsi_fast,
        "rsi_slow": bar.rsi_slow,
        "rsi_diff": bar.rsi_diff,
        "rsi_diff_delta": bar.rsi_diff_delta,
        "vwap_dist_bps": (bar.close - bar.vwap) / bar.close * 10_000.0 if bar.close else 0.0,
        "volume_rel20": bar.volume / bar.volume_sma20 if bar.volume_sma20 > 0 else 0.0,
        "structure_state": bar.structure_state,
        "qimb_mean": bar.qimb_mean,
        "mlofi_mean": bar.mlofi_mean,
        "trade_flow_mean": bar.trade_flow_mean,
        "path_horizon_bars": PATH_HORIZON_BARS,
        "path_barrier_bps": barrier,
        **outcome,
        "guardrail": GUARDRAIL,
    }


def build_events(run_tag, by_symbol, intervals):
    base, controls = [], []
    for symbol, bars in by_symbol.items():
        last_pattern = defaultdict(lambda: -10**9)
        for i in range(SWING_LOOKBACK_BARS + 1, len(bars) - PATH_HORIZON_BARS):
            bar = bars[i]
            fold = fold_for_ts(intervals, symbol, bar.end_ts)
            if not fold:
                continue
            swing = trailing_swing(bars, i)
            if not swing:
                continue
            band = max(5.0, 2.0 * bar.spread_mean)
            candidates = []
            for ratio in FIB_RATIOS:
                if swing["direction"] == "up":
                    level = swing["high"] - ratio * swing["range"]
                    side_sign = 1
                else:
                    level = swing["low"] + ratio * swing["range"]
                    side_sign = -1
                dist = abs((bar.close - level) / bar.close * 10_000.0)
                if dist <= band:
                    candidates.append(("fib_retracement_zone", side_sign, level, f"fib_{ratio:.3f}_zone"))
            for ratio in EXT_RATIOS:
                if swing["direction"] == "up":
                    level = swing["high"] + (ratio - 1.0) * swing["range"]
                    side_sign = 1
                else:
                    level = swing["low"] - (ratio - 1.0) * swing["range"]
                    side_sign = -1
                dist = abs((bar.close - level) / bar.close * 10_000.0)
                if dist <= band:
                    candidates.append(("fib_extension_zone", side_sign, level, f"extension_{ratio:.3f}_zone"))
            if is_rsi_divergence(bars, i, swing):
                side_sign = 1 if swing["direction"] == "down" else -1
                level = swing["low"] if side_sign > 0 else swing["high"]
                candidates.append(("rsi_diff_divergence_with_structure", side_sign, level, "rsi_diff_divergence_near_structure"))
            if is_structure_break(bars, i):
                side_sign = 1 if bar.structure_state == "bullish_breakout" else -1
                level = max(b.high for b in bars[i - SWING_LOOKBACK_BARS : i]) if side_sign > 0 else min(b.low for b in bars[i - SWING_LOOKBACK_BARS : i])
                candidates.append(("market_structure_break", side_sign, level, bar.structure_state))
            if is_vwap_deviation(bar):
                side_sign = -1 if bar.close > bar.vwap else 1
                candidates.append(("vwap_deviation_reaction", side_sign, bar.vwap, "vwap_2sigma_proxy_deviation"))

            for pattern, side_sign, level, trigger in candidates:
                if i - last_pattern[pattern] < EVENT_GAP_BARS:
                    continue
                last_pattern[pattern] = i
                group_id = f"{fold}|{symbol}|{i}|{pattern}"
                event = build_event(run_tag, fold, symbol, bars, i, pattern, side_sign, level, trigger, "base", group_id)
                base.append(event)
                controls.extend(build_controls(run_tag, fold, symbol, bars, i, event))
    return base, controls


def is_rsi_divergence(bars, i, swing):
    if i < 12:
        return False
    bar = bars[i]
    prev = bars[i - 12]
    price_delta_bps = (bar.close - prev.close) / prev.close * 10_000.0 if prev.close else 0.0
    if swing["direction"] == "down":
        return price_delta_bps < -5.0 and bar.rsi_diff_delta > 0.3 and bar.close > min(b.close for b in bars[i - 6 : i + 1])
    return price_delta_bps > 5.0 and bar.rsi_diff_delta < -0.3 and bar.close < max(b.close for b in bars[i - 6 : i + 1])


def is_structure_break(bars, i):
    bar = bars[i]
    volume_rel20 = bar.volume / bar.volume_sma20 if bar.volume_sma20 > 0 else 0.0
    return bar.structure_state in {"bullish_breakout", "bearish_breakdown"} and volume_rel20 >= 1.2


def is_vwap_deviation(bar):
    if bar.close <= 0 or bar.vwap <= 0:
        return False
    volume_rel20 = bar.volume / bar.volume_sma20 if bar.volume_sma20 > 0 else 0.0
    return abs((bar.close - bar.vwap) / bar.close * 10_000.0) >= 25.0 and volume_rel20 >= 1.0


def build_controls(run_tag, fold, symbol, bars, i, event):
    out = []
    out.append(
        build_event(
            run_tag,
            fold,
            symbol,
            bars,
            i,
            event["pattern"],
            -event["side_sign"],
            event["level_price"],
            "side_flip",
            "side_flip",
            event["control_group_id"],
        )
    )
    for label, offset in [("timestamp_shift_plus_12bars", 12), ("timestamp_shift_minus_12bars", -12)]:
        j = i + offset
        if 0 <= j < len(bars) - PATH_HORIZON_BARS:
            out.append(
                build_event(
                    run_tag,
                    fold,
                    symbol,
                    bars,
                    j,
                    event["pattern"],
                    event["side_sign"],
                    event["level_price"],
                    label,
                    label,
                    event["control_group_id"],
                )
            )
    j = (i + 997) % max(1, len(bars) - PATH_HORIZON_BARS)
    out.append(
        build_event(
            run_tag,
            fold,
            symbol,
            bars,
            j,
            event["pattern"],
            event["side_sign"],
            event["level_price"],
            "random_bar_same_symbol",
            "random_bar_same_symbol",
            event["control_group_id"],
        )
    )
    return out


def summarize(events):
    grouped = defaultdict(list)
    for event in events:
        grouped[(event["pattern"], event["control_type"])].append(event)
    rows = []
    for (pattern, control), items in sorted(grouped.items()):
        n = len(items)
        rows.append(
            {
                "pattern": pattern,
                "control_type": control,
                "events": n,
                "favorable_rate": rate(sum(1 for e in items if e["favorable_first"]), n),
                "adverse_rate": rate(sum(1 for e in items if e["adverse_first"]), n),
                "timeout_rate": rate(sum(1 for e in items if e["timeout"]), n),
                "mean_side_return_bps": mean([e["side_return_bps"] for e in items]),
                "median_side_return_bps": median([e["side_return_bps"] for e in items]),
                "mean_mfe_bps": mean([e["mfe_bps"] for e in items]),
                "mean_mae_bps": mean([e["mae_bps"] for e in items]),
                "mean_rsi_diff": mean([e["rsi_diff"] for e in items]),
                "mean_rsi_diff_delta": mean([e["rsi_diff_delta"] for e in items]),
                "mean_vwap_dist_bps": mean([e["vwap_dist_bps"] for e in items]),
                "mean_volume_rel20": mean([e["volume_rel20"] for e in items]),
                "max_date_share": max(Counter(e["date"] for e in items).values()) / n if n else 0.0,
                "max_symbol_share": max(Counter(e["symbol"] for e in items).values()) / n if n else 0.0,
                "guardrail": GUARDRAIL,
            }
        )
    return rows


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


def axis(x, y, w, h):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#CBD5E1"/>\n'
        f'<line x1="{x}" y1="{y+h}" x2="{x+w}" y2="{y+h}" stroke="#64748B"/>\n'
        f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y+h}" stroke="#64748B"/>\n'
    )


def legend(x, y, items):
    out = ""
    for i, (label, color) in enumerate(items):
        yy = y + i * 20
        out += f'<rect x="{x}" y="{yy}" width="12" height="12" fill="{color}" rx="2"/>\n'
        out += f'<text x="{x+18}" y="{yy+11}" font-size="12" fill="#334155">{html.escape(label)}</text>\n'
    return out


def write_pattern_return_svg(path, summary):
    rows = [r for r in summary if r["control_type"] == "base"]
    width, height = 980, 480
    x, y, w, h = 90, 70, 760, 290
    max_abs = max([abs(r["mean_side_return_bps"]) for r in rows] + [1.0])
    group_w = w / max(1, len(rows))
    mid_y = y + h / 2
    svg = svg_header(width, height, "Technical Patterns: Mean Side Return")
    svg += axis(x, y, w, h)
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#334155"/>\n'
    for i, r in enumerate(rows):
        value = r["mean_side_return_bps"]
        bh = abs(value) / max_abs * h * 0.45
        bx = x + i * group_w + group_w * 0.28
        by = mid_y - bh if value >= 0 else mid_y
        color = "#287C5E" if value >= 0 else "#B84A4A"
        svg += f'<rect x="{bx:.1f}" y="{by:.1f}" width="{group_w*0.42:.1f}" height="{bh:.1f}" fill="{color}" rx="4"/>\n'
        lx = x + i * group_w + group_w * 0.45
        svg += f'<text x="{lx:.1f}" y="{y+h+92}" transform="rotate(-38 {lx:.1f} {y+h+92})" font-size="10" fill="#334155">{html.escape(r["pattern"])}</text>\n'
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_pattern_mix_svg(path, summary):
    rows = [r for r in summary if r["control_type"] == "base"]
    width, height = 980, 480
    x, y, w, h = 90, 70, 760, 290
    group_w = w / max(1, len(rows))
    svg = svg_header(width, height, "Technical Patterns: First-Passage Mix")
    svg += axis(x, y, w, h)
    for i, r in enumerate(rows):
        vals = [
            ("fav", r["favorable_rate"], "#287C5E"),
            ("adv", r["adverse_rate"], "#B84A4A"),
            ("timeout", r["timeout_rate"], "#94A3B8"),
        ]
        for j, (_, value, color) in enumerate(vals):
            bh = value * h
            bx = x + i * group_w + 12 + j * group_w * 0.21
            svg += f'<rect x="{bx:.1f}" y="{y+h-bh:.1f}" width="{group_w*0.17:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>\n'
        lx = x + i * group_w + group_w * 0.38
        svg += f'<text x="{lx:.1f}" y="{y+h+92}" transform="rotate(-38 {lx:.1f} {y+h+92})" font-size="10" fill="#334155">{html.escape(r["pattern"])}</text>\n'
    svg += legend(820, 24, [("fav", "#287C5E"), ("adv", "#B84A4A"), ("timeout", "#94A3B8")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_rsi_scatter_svg(path, events):
    base = [e for e in events if e["control_type"] == "base"]
    width, height = 900, 500
    x, y, w, h = 90, 70, 680, 310
    max_x = max([abs(e["rsi_diff_delta"]) for e in base] + [1.0])
    max_y = max([abs(e["side_return_bps"]) for e in base] + [1.0])
    mid_x, mid_y = x + w / 2, y + h / 2
    svg = svg_header(width, height, "RSI Diff Delta vs Path Return")
    svg += axis(x, y, w, h)
    svg += f'<line x1="{mid_x}" y1="{y}" x2="{mid_x}" y2="{y+h}" stroke="#CBD5E1"/>\n'
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#CBD5E1"/>\n'
    for e in base:
        px = mid_x + e["rsi_diff_delta"] / max_x * w * 0.45
        py = mid_y - e["side_return_bps"] / max_y * h * 0.45
        color = "#7C3AED" if "rsi" in e["pattern"] else "#2563EB"
        svg += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{color}" opacity="0.45"/>\n'
    svg += '<text x="90" y="420" font-size="12" fill="#475569">x: RSI diff delta, y: path side return bps. RSI is context, not trigger.</text>\n'
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_control_svg(path, summary):
    rows = [r for r in summary if r["control_type"] != "base"]
    base = {r["pattern"]: r for r in summary if r["control_type"] == "base"}
    width, height = 1180, 520
    x, y, w, h = 80, 70, 960, 300
    max_abs = max([abs(r["mean_side_return_bps"]) for r in summary] + [1.0])
    group_w = w / max(1, len(rows))
    mid_y = y + h / 2
    svg = svg_header(width, height, "Technical Patterns: Base vs Controls")
    svg += axis(x, y, w, h)
    svg += f'<line x1="{x}" y1="{mid_y}" x2="{x+w}" y2="{mid_y}" stroke="#334155"/>\n'
    for i, r in enumerate(rows):
        b = base.get(r["pattern"])
        base_v = b["mean_side_return_bps"] if b else 0.0
        ctrl_v = r["mean_side_return_bps"]
        bx = x + i * group_w + 3
        for j, (value, color) in enumerate([(base_v, "#2563EB"), (ctrl_v, "#D97706")]):
            bh = abs(value) / max_abs * h * 0.45
            by = mid_y - bh if value >= 0 else mid_y
            svg += f'<rect x="{bx + j*group_w*0.30:.1f}" y="{by:.1f}" width="{group_w*0.23:.1f}" height="{bh:.1f}" fill="{color}" rx="3"/>\n'
        label = f'{r["pattern"]}:{r["control_type"]}'
        svg += f'<text x="{bx+group_w*0.2:.1f}" y="{y+h+104}" transform="rotate(-50 {bx+group_w*0.2:.1f} {y+h+104})" font-size="8" fill="#334155">{html.escape(label[:42])}</text>\n'
    svg += legend(1040, 24, [("base", "#2563EB"), ("control", "#D97706")])
    svg += "</svg>\n"
    path.write_text(svg, encoding="utf-8")


def write_report(path, run_tag, parts, bars_count, base_events, controls, summary, outputs):
    base_rows = [r for r in summary if r["control_type"] == "base"]
    best = max(base_rows, key=lambda r: r["mean_side_return_bps"], default=None)
    bad_controls = 0
    base_map = {r["pattern"]: r for r in base_rows}
    for r in summary:
        if r["control_type"] == "base":
            continue
        b = base_map.get(r["pattern"])
        if b and abs(r["mean_side_return_bps"]) >= abs(b["mean_side_return_bps"]):
            bad_controls += 1
    lines = [
        "# BONK V15 Technical Analysis Skill Report",
        "",
        f"- run_tag: `{run_tag}`",
        f"- guardrail: `{GUARDRAIL}`",
        "- stance: research-only diagnostics; no trading advice, no execution recommendation, no alpha claim.",
        "- method: event-time OHLCV bars, fixed TA constructs, causal trailing swings only.",
        "",
        "## Method",
        "",
        f"- panel part files: `{len(parts)}`",
        f"- event-time bar size: `{BAR_SIZE_EVENTS}` L2 events",
        f"- bars: `{bars_count}`",
        f"- base pattern events: `{len(base_events)}`",
        f"- control events: `{len(controls)}`",
        "- Patterns tested: Fibonacci retracement zone, Fibonacci extension zone, RSI diff divergence with structure, market structure break, VWAP deviation reaction.",
        "",
        "## Sharp Edges Applied",
        "",
        "- Fibonacci levels are treated as zones, not exact prices.",
        "- RSI is lagging context; divergence requires structure context and is not used alone.",
        "- Every row has side-flip, time-shift, and random-bar controls.",
        "- Positive-looking rows with high date concentration or control overlap are rejected as path diagnostics only.",
        "",
        "## Pattern Read",
        "",
    ]
    if best:
        lines.extend(
            [
                f"- best mean-return base pattern: `{best['pattern']}`",
                f"- events: `{best['events']}`",
                f"- favorable/adverse/timeout: `{best['favorable_rate']:.4f}` / `{best['adverse_rate']:.4f}` / `{best['timeout_rate']:.4f}`",
                f"- mean side return: `{best['mean_side_return_bps']:.4f}` bps",
                f"- max_date_share: `{best['max_date_share']:.4f}`; max_symbol_share: `{best['max_symbol_share']:.4f}`",
            ]
        )
    lines.extend(
        [
            f"- controls with abs(control mean) >= abs(base mean): `{bad_controls}`",
            "- important rejection: the top mean-return row is not automatically useful; sample count, date concentration, and control overlap dominate the verdict.",
            "",
            "| pattern | events | mean return bps | favorable | adverse | max date | control overlap | read |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in base_rows:
        overlaps = 0
        for candidate in summary:
            if candidate["pattern"] == row["pattern"] and candidate["control_type"] != "base":
                if abs(candidate["mean_side_return_bps"]) >= abs(row["mean_side_return_bps"]):
                    overlaps += 1
        if row["events"] < 30:
            read = "too few samples"
        elif row["max_date_share"] > 0.50:
            read = "date concentrated"
        elif overlaps > 0:
            read = "controls too strong"
        elif row["mean_side_return_bps"] > 0:
            read = "path candidate only"
        else:
            read = "failed direction"
        lines.append(
            f"| `{row['pattern']}` | {row['events']} | {row['mean_side_return_bps']:.4f} | {row['favorable_rate']:.4f} | {row['adverse_rate']:.4f} | {row['max_date_share']:.4f} | {overlaps} | {read} |"
        )
    lines.extend(
        [
            "",
            f"![Pattern returns]({outputs['return_svg'].as_posix()})",
            "",
            f"![Pattern path mix]({outputs['mix_svg'].as_posix()})",
            "",
            f"![RSI scatter]({outputs['rsi_svg'].as_posix()})",
            "",
            f"![Controls]({outputs['control_svg'].as_posix()})",
            "",
            "## Outputs",
            "",
            f"- bars CSV: `{outputs['bars_csv'].as_posix()}`",
            f"- events CSV: `{outputs['events_csv'].as_posix()}`",
            f"- summary CSV: `{outputs['summary_csv'].as_posix()}`",
            f"- controls CSV: `{outputs['controls_csv'].as_posix()}`",
            "",
            "## Bottom Line",
            "",
            "This TA pass is more honest than drawing lines on raw events. It shows whether standard structures survive controls on event-time bars. If controls overlap base or date concentration dominates, the result remains a visual/path phenomenon rather than a strategy candidate.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def bars_to_rows(by_symbol):
    rows = []
    for bars in by_symbol.values():
        for b in bars:
            rows.append(
                {
                    "run_tag": b.run_tag,
                    "symbol": b.symbol,
                    "date": b.date,
                    "bar_id": b.bar_id,
                    "start_ts": b.start_ts,
                    "end_ts": b.end_ts,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "spread_mean": b.spread_mean,
                    "qimb_mean": b.qimb_mean,
                    "mlofi_mean": b.mlofi_mean,
                    "trade_flow_mean": b.trade_flow_mean,
                    "vwap": b.vwap,
                    "rsi_fast": b.rsi_fast,
                    "rsi_slow": b.rsi_slow,
                    "rsi_diff": b.rsi_diff,
                    "rsi_diff_delta": b.rsi_diff_delta,
                    "volume_rel20": b.volume / b.volume_sma20 if b.volume_sma20 > 0 else 0.0,
                    "structure_state": b.structure_state,
                    "guardrail": GUARDRAIL,
                }
            )
    return rows


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
    parts, by_symbol = load_bars(data_root, args.run_tag, symbols)
    bars_rows = bars_to_rows(by_symbol)
    base_events, controls = build_events(args.run_tag, by_symbol, intervals)
    all_events = base_events + controls
    summary = summarize(all_events)
    outputs = {
        "bars_csv": date_dir / f"bonk_v15_technical_analysis_bars_{args.run_tag}.csv",
        "events_csv": date_dir / f"bonk_v15_technical_analysis_events_{args.run_tag}.csv",
        "summary_csv": date_dir / f"bonk_v15_technical_analysis_summary_{args.run_tag}.csv",
        "controls_csv": date_dir / f"bonk_v15_technical_analysis_controls_{args.run_tag}.csv",
        "return_svg": fig_dir / f"bonk_v15_technical_pattern_returns_{args.run_tag}.svg",
        "mix_svg": fig_dir / f"bonk_v15_technical_pattern_mix_{args.run_tag}.svg",
        "rsi_svg": fig_dir / f"bonk_v15_technical_rsi_scatter_{args.run_tag}.svg",
        "control_svg": fig_dir / f"bonk_v15_technical_controls_{args.run_tag}.svg",
        "report_md": doc_dir / "v1-cex-v15-technical-analysis-skill-report.md",
    }
    write_csv(outputs["bars_csv"], bars_rows)
    write_csv(outputs["events_csv"], all_events)
    write_csv(outputs["summary_csv"], summary)
    write_csv(outputs["controls_csv"], controls)
    write_pattern_return_svg(outputs["return_svg"], summary)
    write_pattern_mix_svg(outputs["mix_svg"], summary)
    write_rsi_scatter_svg(outputs["rsi_svg"], all_events)
    write_control_svg(outputs["control_svg"], summary)
    write_report(outputs["report_md"], args.run_tag, parts, len(bars_rows), base_events, controls, summary, outputs)
    print(f"panel_parts={len(parts)}")
    print(f"bars={len(bars_rows)}")
    print(f"base_events={len(base_events)}")
    print(f"control_events={len(controls)}")
    print(f"summary_rows={len(summary)}")
    print(f"report_md={outputs['report_md']}")


if __name__ == "__main__":
    main()
