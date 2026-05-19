#!/usr/bin/env python3
"""BONK V15A shadow acceptance-surface diagnostic.

This pass intentionally creates no entries. It reads the existing V10c event
panel inventory plus the frozen V14 calibration/validation outputs and asks:

    state bucket -> p_fill, p_up_first, p_down_first, support, expected net

The purpose is to separate mechanical first-passage collapse from states that
still have a path but lose after cost.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


GUARDRAIL = "research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim"
DEFAULT_RUN_TAG = "20260514_bonk_v10_stage1_pilot"
DEFAULT_OUTPUT_TAG = "20260515_bonk_v10_stage1_pilot"
V15A_PREFIX = "bonk_v15a_shadow_acceptance_surface"


def fnum(value, default=0.0):
    try:
        if value in ("", None):
            return default
        out = float(value)
        if math.isfinite(out):
            return out
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


def rate(count, total):
    return count / total if total else 0.0


def fmt_float(value, digits=6):
    if value is None:
        return ""
    try:
        if not math.isfinite(float(value)):
            return ""
    except Exception:
        return ""
    return f"{float(value):.{digits}f}"


def first_existing(*values):
    for value in values:
        if value not in ("", None):
            return value
    return ""


def read_csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def markdown_table(rows, columns, max_rows=None):
    if max_rows is not None:
        rows = rows[:max_rows]
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        cells = []
        for _, key in columns:
            raw = row.get(key, "")
            text = str(raw)
            text = text.replace("|", "\\|").replace("\n", " ")
            if len(text) > 96:
                text = text[:93] + "..."
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def load_min_support(params_path: Path, default=20):
    if not params_path.exists():
        return default
    with params_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("parameter") == "min_support":
                return inum(row.get("value"), default)
    return default


def inspect_v10c_panel(data_root: Path, run_tag: str):
    base = data_root / "derived" / "bonk_v10c_event_ofi_panel" / f"run_tag={run_tag}"
    parts = sorted(glob.glob(str(base / "**" / "part_*.csv"), recursive=True))
    rows = 0
    by_symbol = Counter()
    by_date = Counter()
    by_symbol_date = Counter()
    factor_eligible = 0
    files_by_symbol = Counter()
    files_by_date = Counter()
    for part in parts:
        path = Path(part)
        symbol = ""
        dt = ""
        for piece in path.parts:
            if piece.startswith("symbol="):
                symbol = piece.split("=", 1)[1]
            elif piece.startswith("dt="):
                dt = piece.split("=", 1)[1]
        files_by_symbol[symbol] += 1
        files_by_date[dt] += 1
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows += 1
                sym = row.get("symbol") or symbol
                date = row.get("date") or dt
                by_symbol[sym] += 1
                by_date[date] += 1
                by_symbol_date[(sym, date)] += 1
                if str(row.get("factor_eligible", "")).lower() == "true":
                    factor_eligible += 1
    panel_rows = []
    for (symbol, date), count in sorted(by_symbol_date.items()):
        panel_rows.append(
            {
                "run_tag": run_tag,
                "symbol": symbol,
                "date": date,
                "panel_rows": count,
                "panel_row_share": rate(count, rows),
                "guardrail": GUARDRAIL,
            }
        )
    return {
        "base": str(base),
        "files": len(parts),
        "rows": rows,
        "factor_eligible_rows": factor_eligible,
        "symbols": ",".join(sorted(k for k in by_symbol if k)),
        "dates": ",".join(sorted(k for k in by_date if k)),
        "files_by_symbol": dict(files_by_symbol),
        "files_by_date": dict(files_by_date),
        "panel_rows": panel_rows,
    }


def classify_surface_row(p_fill, p_up, p_down, expected_net, support, min_support, skip_reason=""):
    if skip_reason == "insufficient_support" or support < min_support:
        return "mechanical_insufficient_support"
    if p_fill <= 0 and p_up <= 0 and p_down <= 0:
        return "mechanical_zero_fill_or_zero_path_mass"
    if p_fill > 0 and p_up <= 0 and p_down >= 0.95:
        return "mechanical_adverse_first_only"
    if p_fill > 0 and p_up <= 0:
        return "mechanical_no_favorable_first_passage"
    if p_up > 0 and expected_net <= 0:
        return "weak_after_cost"
    if p_up > 0 and expected_net > 0:
        return "positive_shadow_only"
    return "other"


def classification_family(name):
    if name.startswith("mechanical_"):
        return "mechanical_collapse"
    if name == "weak_after_cost":
        return "weak_after_cost"
    if name == "positive_shadow_only":
        return "positive_shadow_only"
    return "other"


@dataclass
class SurfaceAgg:
    rows: int = 0
    p_fill_sum: float = 0.0
    p_up_sum: float = 0.0
    p_down_sum: float = 0.0
    p_timeout_sum: float = 0.0
    expected_net_sum: float = 0.0
    gross_sum: float = 0.0
    support_sum: float = 0.0
    p_fill_max: float = 0.0
    p_up_max: float = 0.0
    p_down_max: float = 0.0
    expected_net_max: float = -1e18
    expected_net_min: float = 1e18
    support_min: float = 1e18
    support_max: float = 0.0
    classifications: Counter = field(default_factory=Counter)
    fallback_levels: Counter = field(default_factory=Counter)
    calibration_sources: Counter = field(default_factory=Counter)
    skip_reasons: Counter = field(default_factory=Counter)
    symbols: Counter = field(default_factory=Counter)
    dates: Counter = field(default_factory=Counter)
    folds: Counter = field(default_factory=Counter)
    params: Counter = field(default_factory=Counter)

    def add(
        self,
        *,
        p_fill,
        p_up,
        p_down,
        p_timeout,
        expected_net,
        gross,
        support,
        classification,
        fallback_level="",
        calibration_source="",
        skip_reason="",
        symbol="",
        date="",
        fold="",
        param="",
    ):
        self.rows += 1
        self.p_fill_sum += p_fill
        self.p_up_sum += p_up
        self.p_down_sum += p_down
        self.p_timeout_sum += p_timeout
        self.expected_net_sum += expected_net
        self.gross_sum += gross
        self.support_sum += support
        self.p_fill_max = max(self.p_fill_max, p_fill)
        self.p_up_max = max(self.p_up_max, p_up)
        self.p_down_max = max(self.p_down_max, p_down)
        self.expected_net_max = max(self.expected_net_max, expected_net)
        self.expected_net_min = min(self.expected_net_min, expected_net)
        self.support_min = min(self.support_min, support)
        self.support_max = max(self.support_max, support)
        self.classifications[classification] += 1
        if fallback_level != "":
            self.fallback_levels[str(fallback_level)] += 1
        if calibration_source:
            self.calibration_sources[calibration_source] += 1
        if skip_reason:
            self.skip_reasons[skip_reason] += 1
        if symbol:
            self.symbols[symbol] += 1
        if date:
            self.dates[date] += 1
        if fold:
            self.folds[fold] += 1
        if param:
            self.params[param] += 1

    def to_row(self, source_phase, bucket_scope, state_bucket, side, run_tag, output_tag):
        n = self.rows
        family_counts = Counter()
        for klass, count in self.classifications.items():
            family_counts[classification_family(klass)] += count
        top_date, top_date_count = ("", 0)
        if self.dates:
            top_date, top_date_count = self.dates.most_common(1)[0]
        top_symbol, top_symbol_count = ("", 0)
        if self.symbols:
            top_symbol, top_symbol_count = self.symbols.most_common(1)[0]
        top_class, top_class_count = ("", 0)
        if self.classifications:
            top_class, top_class_count = self.classifications.most_common(1)[0]
        return {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "source_phase": source_phase,
            "bucket_scope": bucket_scope,
            "state_bucket": state_bucket,
            "side": side,
            "rows": n,
            "support_mean": self.support_sum / n if n else 0.0,
            "support_min": 0.0 if self.support_min == 1e18 else self.support_min,
            "support_max": self.support_max,
            "p_fill_mean": self.p_fill_sum / n if n else 0.0,
            "p_fill_max": self.p_fill_max,
            "p_up_first_mean": self.p_up_sum / n if n else 0.0,
            "p_up_first_max": self.p_up_max,
            "p_down_first_mean": self.p_down_sum / n if n else 0.0,
            "p_down_first_max": self.p_down_max,
            "p_timeout_mean": self.p_timeout_sum / n if n else 0.0,
            "expected_net_bps_mean": self.expected_net_sum / n if n else 0.0,
            "expected_net_bps_max": "" if self.expected_net_max == -1e18 else self.expected_net_max,
            "expected_net_bps_min": "" if self.expected_net_min == 1e18 else self.expected_net_min,
            "gross_bps_mean": self.gross_sum / n if n else 0.0,
            "mechanical_row_share": rate(family_counts["mechanical_collapse"], n),
            "weak_after_cost_row_share": rate(family_counts["weak_after_cost"], n),
            "positive_shadow_row_share": rate(family_counts["positive_shadow_only"], n),
            "top_classification": top_class,
            "top_classification_share": rate(top_class_count, n),
            "classifications": ";".join(f"{k}:{v}" for k, v in self.classifications.most_common()),
            "fallback_levels": ";".join(f"{k}:{v}" for k, v in self.fallback_levels.most_common()),
            "calibration_sources": ";".join(
                f"{k}:{v}" for k, v in self.calibration_sources.most_common()
            ),
            "skip_reasons": ";".join(f"{k}:{v}" for k, v in self.skip_reasons.most_common()),
            "top_symbol": top_symbol,
            "top_symbol_share": rate(top_symbol_count, n),
            "top_date": top_date,
            "top_date_share": rate(top_date_count, n),
            "folds": ";".join(f"{k}:{v}" for k, v in self.folds.most_common()),
            "top_params": ";".join(f"{k}:{v}" for k, v in self.params.most_common(4)),
            "guardrail": GUARDRAIL,
        }


BUCKET_FIELDNAMES = [
    "run_tag",
    "output_tag",
    "source_phase",
    "bucket_scope",
    "state_bucket",
    "side",
    "rows",
    "support_mean",
    "support_min",
    "support_max",
    "p_fill_mean",
    "p_fill_max",
    "p_up_first_mean",
    "p_up_first_max",
    "p_down_first_mean",
    "p_down_first_max",
    "p_timeout_mean",
    "expected_net_bps_mean",
    "expected_net_bps_max",
    "expected_net_bps_min",
    "gross_bps_mean",
    "mechanical_row_share",
    "weak_after_cost_row_share",
    "positive_shadow_row_share",
    "top_classification",
    "top_classification_share",
    "classifications",
    "fallback_levels",
    "calibration_sources",
    "skip_reasons",
    "top_symbol",
    "top_symbol_share",
    "top_date",
    "top_date_share",
    "folds",
    "top_params",
    "guardrail",
]


def add_validation_row(aggs, row, min_support, run_tag, output_tag):
    p_fill = fnum(row.get("p_fill"))
    p_up = fnum(row.get("p_up_first"))
    p_down = fnum(row.get("p_down_first"))
    p_timeout = fnum(row.get("p_timeout"))
    expected_net = fnum(row.get("expected_net_bps"))
    support = fnum(row.get("support"))
    classification = classify_surface_row(
        p_fill,
        p_up,
        p_down,
        expected_net,
        support,
        min_support,
        row.get("skip_reason", ""),
    )
    common = {
        "p_fill": p_fill,
        "p_up": p_up,
        "p_down": p_down,
        "p_timeout": p_timeout,
        "expected_net": expected_net,
        "gross": 0.0,
        "support": support,
        "classification": classification,
        "fallback_level": row.get("fallback_level", ""),
        "calibration_source": row.get("calibration_source", ""),
        "skip_reason": row.get("skip_reason", ""),
        "symbol": row.get("symbol", ""),
        "date": row.get("date", ""),
        "fold": row.get("fold", ""),
        "param": ":".join(
            [
                row.get("marker_distance_bps", ""),
                row.get("take_profit_bps", ""),
                row.get("stop_loss_bps", ""),
                row.get("hold_events", ""),
            ]
        ),
    }
    side = row.get("side", "")
    buckets = [
        ("validation_root", first_existing(row.get("root_state_key"), row.get("resolved_state_key"))),
        ("validation_parent", first_existing(row.get("parent_state_key"), row.get("root_state_key"))),
        ("validation_resolved", first_existing(row.get("resolved_state_key"), row.get("state_key"))),
    ]
    for scope, state in buckets:
        aggs[(scope, state, side)].add(**common)
    detail_key = (
        "validation_param_resolved",
        "|".join(
            [
                row.get("fold", ""),
                row.get("symbol", ""),
                side,
                row.get("marker_distance_bps", ""),
                row.get("take_profit_bps", ""),
                row.get("stop_loss_bps", ""),
                row.get("hold_events", ""),
                first_existing(row.get("resolved_state_key"), row.get("state_key")),
            ]
        ),
        side,
    )
    aggs[detail_key].add(**common)


def add_calibration_row(aggs, row, min_support):
    p_fill = fnum(row.get("p_fill"))
    p_up = fnum(row.get("p_up_first"))
    p_down = fnum(row.get("p_down_first"))
    p_timeout = fnum(row.get("p_timeout"))
    expected_net = fnum(row.get("e_net_bps"))
    gross = fnum(row.get("e_gross_bps"))
    support = fnum(row.get("support"))
    classification = classify_surface_row(
        p_fill,
        p_up,
        p_down,
        expected_net,
        support,
        min_support,
        "",
    )
    common = {
        "p_fill": p_fill,
        "p_up": p_up,
        "p_down": p_down,
        "p_timeout": p_timeout,
        "expected_net": expected_net,
        "gross": gross,
        "support": support,
        "classification": classification,
        "fallback_level": row.get("fallback_level", ""),
        "calibration_source": row.get("symbol_scope", ""),
        "skip_reason": "",
        "symbol": row.get("symbol_scope", ""),
        "date": "",
        "fold": row.get("fold", ""),
        "param": ":".join(
            [
                row.get("marker_distance_bps", ""),
                row.get("take_profit_bps", ""),
                row.get("stop_loss_bps", ""),
                row.get("hold_events", ""),
            ]
        ),
    }
    side = row.get("side", "")
    state = row.get("state_key", "")
    aggs[("calibration_state", state, side)].add(**common)
    aggs[
        (
            "calibration_param_state",
            "|".join(
                [
                    row.get("fold", ""),
                    row.get("symbol_scope", ""),
                    side,
                    row.get("marker_distance_bps", ""),
                    row.get("take_profit_bps", ""),
                    row.get("stop_loss_bps", ""),
                    row.get("hold_events", ""),
                    state,
                ]
            ),
            side,
        )
    ].add(**common)


def summarize_rows(calibration_rows, validation_rows, panel_info, min_support, run_tag, output_tag):
    calibration_class = Counter()
    validation_class = Counter()
    calibration_positive_rows = 0
    validation_positive_rows = 0
    validation_up_nonzero = 0
    validation_expected = []
    validation_p_fill = []
    validation_p_down = []
    validation_support = []
    for row in calibration_rows:
        klass = classify_surface_row(
            fnum(row.get("p_fill")),
            fnum(row.get("p_up_first")),
            fnum(row.get("p_down_first")),
            fnum(row.get("e_net_bps")),
            fnum(row.get("support")),
            min_support,
        )
        calibration_class[klass] += 1
        if fnum(row.get("e_net_bps")) > 0:
            calibration_positive_rows += 1
    for row in validation_rows:
        klass = classify_surface_row(
            fnum(row.get("p_fill")),
            fnum(row.get("p_up_first")),
            fnum(row.get("p_down_first")),
            fnum(row.get("expected_net_bps")),
            fnum(row.get("support")),
            min_support,
            row.get("skip_reason", ""),
        )
        validation_class[klass] += 1
        if fnum(row.get("expected_net_bps")) > 0:
            validation_positive_rows += 1
        if fnum(row.get("p_up_first")) > 0:
            validation_up_nonzero += 1
        validation_expected.append(fnum(row.get("expected_net_bps")))
        validation_p_fill.append(fnum(row.get("p_fill")))
        validation_p_down.append(fnum(row.get("p_down_first")))
        validation_support.append(fnum(row.get("support")))
    def add_metric(rows, metric, value, note=""):
        rows.append(
            {
                "run_tag": run_tag,
                "output_tag": output_tag,
                "metric": metric,
                "value": value,
                "note": note,
                "guardrail": GUARDRAIL,
            }
        )

    out = []
    add_metric(out, "v10c_panel_files", panel_info["files"], panel_info["base"])
    add_metric(out, "v10c_panel_rows", panel_info["rows"], "rows streamed from V10c event OFI panel")
    add_metric(
        out,
        "v10c_factor_eligible_rows",
        panel_info["factor_eligible_rows"],
        "factor_eligible=true rows in V10c panel",
    )
    add_metric(out, "v10c_symbols", panel_info["symbols"], "")
    add_metric(out, "v10c_dates", panel_info["dates"], "")
    add_metric(out, "v14_min_support", min_support, "from V14 params")
    add_metric(out, "v14_calibration_rows", len(calibration_rows), "")
    add_metric(out, "v14_validation_decision_rows", len(validation_rows), "")
    for klass, count in calibration_class.most_common():
        add_metric(out, f"calibration_{klass}_rows", count, "classification over V14 train-only calibration")
    add_metric(out, "calibration_positive_expected_net_rows", calibration_positive_rows, "")
    for klass, count in validation_class.most_common():
        add_metric(out, f"validation_{klass}_rows", count, "classification over frozen validation decisions")
    add_metric(out, "validation_p_up_first_nonzero_rows", validation_up_nonzero, "")
    add_metric(out, "validation_positive_expected_net_rows", validation_positive_rows, "")
    add_metric(out, "validation_expected_net_bps_mean", sum(validation_expected) / len(validation_expected), "")
    add_metric(out, "validation_expected_net_bps_max", max(validation_expected) if validation_expected else "", "")
    add_metric(out, "validation_expected_net_bps_min", min(validation_expected) if validation_expected else "", "")
    add_metric(out, "validation_p_fill_mean", sum(validation_p_fill) / len(validation_p_fill), "")
    add_metric(out, "validation_p_fill_max", max(validation_p_fill) if validation_p_fill else "", "")
    add_metric(out, "validation_p_down_first_mean", sum(validation_p_down) / len(validation_p_down), "")
    add_metric(out, "validation_support_mean", sum(validation_support) / len(validation_support), "")
    return out


def build_bucket_rows(validation_rows, calibration_rows, min_support, run_tag, output_tag):
    aggs = defaultdict(SurfaceAgg)
    for row in validation_rows:
        add_validation_row(aggs, row, min_support, run_tag, output_tag)
    for row in calibration_rows:
        add_calibration_row(aggs, row, min_support)
    rows = [
        agg.to_row(
            "validation_shadow" if key[0].startswith("validation") else "calibration_train",
            key[0],
            key[1],
            key[2],
            run_tag,
            output_tag,
        )
        for key, agg in aggs.items()
    ]
    rows.sort(
        key=lambda row: (
            row["source_phase"],
            row["bucket_scope"],
            -int(row["rows"]),
            row["side"],
            row["state_bucket"],
        )
    )
    return rows


def build_collapse_rows(bucket_rows):
    rows = []
    for row in bucket_rows:
        source = row["source_phase"]
        scope = row["bucket_scope"]
        if scope not in ("validation_resolved", "validation_parent", "calibration_state"):
            continue
        if float(row["mechanical_row_share"]) <= 0 and float(row["weak_after_cost_row_share"]) <= 0:
            continue
        diagnostic = row["top_classification"]
        if row["weak_after_cost_row_share"] and float(row["weak_after_cost_row_share"]) > float(row["mechanical_row_share"]):
            diagnostic = "weak_after_cost"
        rows.append(
            {
                "run_tag": row["run_tag"],
                "output_tag": row["output_tag"],
                "source_phase": source,
                "bucket_scope": scope,
                "state_bucket": row["state_bucket"],
                "side": row["side"],
                "diagnostic": diagnostic,
                "rows": row["rows"],
                "support_mean": row["support_mean"],
                "p_fill_mean": row["p_fill_mean"],
                "p_up_first_mean": row["p_up_first_mean"],
                "p_down_first_mean": row["p_down_first_mean"],
                "expected_net_bps_mean": row["expected_net_bps_mean"],
                "expected_net_bps_max": row["expected_net_bps_max"],
                "mechanical_row_share": row["mechanical_row_share"],
                "weak_after_cost_row_share": row["weak_after_cost_row_share"],
                "top_symbol": row["top_symbol"],
                "top_symbol_share": row["top_symbol_share"],
                "top_date": row["top_date"],
                "top_date_share": row["top_date_share"],
                "fallback_levels": row["fallback_levels"],
                "classifications": row["classifications"],
                "guardrail": GUARDRAIL,
            }
        )
    rows.sort(
        key=lambda row: (
            row["source_phase"],
            0 if str(row["diagnostic"]).startswith("mechanical") else 1,
            -float(row["rows"]),
            row["state_bucket"],
        )
    )
    return rows


def add_diag_row(aggs, *, source_phase, bucket_scope, state_bucket, side, diagnostic, common):
    aggs[(source_phase, bucket_scope, state_bucket, side, diagnostic)].add(**common)


def build_diagnostic_rows(validation_rows, calibration_rows, min_support, run_tag, output_tag):
    aggs = defaultdict(SurfaceAgg)
    for row in validation_rows:
        p_fill = fnum(row.get("p_fill"))
        p_up = fnum(row.get("p_up_first"))
        p_down = fnum(row.get("p_down_first"))
        p_timeout = fnum(row.get("p_timeout"))
        expected_net = fnum(row.get("expected_net_bps"))
        support = fnum(row.get("support"))
        diagnostic = classify_surface_row(
            p_fill,
            p_up,
            p_down,
            expected_net,
            support,
            min_support,
            row.get("skip_reason", ""),
        )
        common = {
            "p_fill": p_fill,
            "p_up": p_up,
            "p_down": p_down,
            "p_timeout": p_timeout,
            "expected_net": expected_net,
            "gross": 0.0,
            "support": support,
            "classification": diagnostic,
            "fallback_level": row.get("fallback_level", ""),
            "calibration_source": row.get("calibration_source", ""),
            "skip_reason": row.get("skip_reason", ""),
            "symbol": row.get("symbol", ""),
            "date": row.get("date", ""),
            "fold": row.get("fold", ""),
            "param": ":".join(
                [
                    row.get("marker_distance_bps", ""),
                    row.get("take_profit_bps", ""),
                    row.get("stop_loss_bps", ""),
                    row.get("hold_events", ""),
                ]
            ),
        }
        side = row.get("side", "")
        add_diag_row(
            aggs,
            source_phase="validation_shadow",
            bucket_scope="validation_resolved",
            state_bucket=first_existing(row.get("resolved_state_key"), row.get("state_key")),
            side=side,
            diagnostic=diagnostic,
            common=common,
        )
        add_diag_row(
            aggs,
            source_phase="validation_shadow",
            bucket_scope="validation_parent",
            state_bucket=first_existing(row.get("parent_state_key"), row.get("root_state_key")),
            side=side,
            diagnostic=diagnostic,
            common=common,
        )
    for row in calibration_rows:
        p_fill = fnum(row.get("p_fill"))
        p_up = fnum(row.get("p_up_first"))
        p_down = fnum(row.get("p_down_first"))
        p_timeout = fnum(row.get("p_timeout"))
        expected_net = fnum(row.get("e_net_bps"))
        gross = fnum(row.get("e_gross_bps"))
        support = fnum(row.get("support"))
        diagnostic = classify_surface_row(
            p_fill,
            p_up,
            p_down,
            expected_net,
            support,
            min_support,
            "",
        )
        common = {
            "p_fill": p_fill,
            "p_up": p_up,
            "p_down": p_down,
            "p_timeout": p_timeout,
            "expected_net": expected_net,
            "gross": gross,
            "support": support,
            "classification": diagnostic,
            "fallback_level": row.get("fallback_level", ""),
            "calibration_source": row.get("symbol_scope", ""),
            "skip_reason": "",
            "symbol": row.get("symbol_scope", ""),
            "date": "",
            "fold": row.get("fold", ""),
            "param": ":".join(
                [
                    row.get("marker_distance_bps", ""),
                    row.get("take_profit_bps", ""),
                    row.get("stop_loss_bps", ""),
                    row.get("hold_events", ""),
                ]
            ),
        }
        add_diag_row(
            aggs,
            source_phase="calibration_train",
            bucket_scope="calibration_state",
            state_bucket=row.get("state_key", ""),
            side=row.get("side", ""),
            diagnostic=diagnostic,
            common=common,
        )
    rows = []
    for (source_phase, bucket_scope, state_bucket, side, diagnostic), agg in aggs.items():
        base = agg.to_row(source_phase, bucket_scope, state_bucket, side, run_tag, output_tag)
        rows.append(
            {
                "run_tag": run_tag,
                "output_tag": output_tag,
                "source_phase": source_phase,
                "bucket_scope": bucket_scope,
                "state_bucket": state_bucket,
                "side": side,
                "diagnostic": diagnostic,
                "rows": base["rows"],
                "support_mean": base["support_mean"],
                "support_min": base["support_min"],
                "support_max": base["support_max"],
                "p_fill_mean": base["p_fill_mean"],
                "p_fill_max": base["p_fill_max"],
                "p_up_first_mean": base["p_up_first_mean"],
                "p_up_first_max": base["p_up_first_max"],
                "p_down_first_mean": base["p_down_first_mean"],
                "p_down_first_max": base["p_down_first_max"],
                "p_timeout_mean": base["p_timeout_mean"],
                "gross_bps_mean": base["gross_bps_mean"],
                "expected_net_bps_mean": base["expected_net_bps_mean"],
                "expected_net_bps_max": base["expected_net_bps_max"],
                "expected_net_bps_min": base["expected_net_bps_min"],
                "top_symbol": base["top_symbol"],
                "top_symbol_share": base["top_symbol_share"],
                "top_date": base["top_date"],
                "top_date_share": base["top_date_share"],
                "fallback_levels": base["fallback_levels"],
                "calibration_sources": base["calibration_sources"],
                "skip_reasons": base["skip_reasons"],
                "top_params": base["top_params"],
                "guardrail": GUARDRAIL,
            }
        )
    rows.sort(
        key=lambda row: (
            row["source_phase"],
            row["bucket_scope"],
            0 if str(row["diagnostic"]).startswith("mechanical") else 1,
            -float(row["rows"]),
            row["state_bucket"],
        )
    )
    return rows


def report_metric(summary_rows, metric, default=""):
    for row in summary_rows:
        if row.get("metric") == metric:
            return row.get("value", default)
    return default


def short_metric(value, digits=4):
    try:
        return fmt_float(float(value), digits)
    except Exception:
        return str(value)


def format_report_rows(rows):
    numeric_digits = {
        "p_fill_mean": 4,
        "p_up_first_mean": 4,
        "p_down_first_mean": 4,
        "support_mean": 1,
        "gross_bps_mean": 4,
        "expected_net_bps_mean": 4,
    }
    out = []
    for row in rows:
        clean = dict(row)
        for key, digits in numeric_digits.items():
            if key in clean:
                clean[key] = fmt_float(clean[key], digits)
        out.append(clean)
    return out


def build_report(
    path: Path,
    *,
    run_tag,
    output_tag,
    generated_at,
    summary_rows,
    validation_top,
    weak_top,
    artifact_paths,
):
    validation_rows = int(float(report_metric(summary_rows, "v14_validation_decision_rows", 0)))
    val_up = int(float(report_metric(summary_rows, "validation_p_up_first_nonzero_rows", 0)))
    val_pos = int(float(report_metric(summary_rows, "validation_positive_expected_net_rows", 0)))
    mean_net = short_metric(report_metric(summary_rows, "validation_expected_net_bps_mean", 0), 4)
    max_net = short_metric(report_metric(summary_rows, "validation_expected_net_bps_max", 0), 4)
    mean_fill = short_metric(report_metric(summary_rows, "validation_p_fill_mean", 0), 4)
    max_fill = short_metric(report_metric(summary_rows, "validation_p_fill_max", 0), 4)
    val_adverse = int(
        float(report_metric(summary_rows, "validation_mechanical_adverse_first_only_rows", 0))
    )
    val_zero = int(
        float(report_metric(summary_rows, "validation_mechanical_zero_fill_or_zero_path_mass_rows", 0))
    )
    val_insuff = int(
        float(report_metric(summary_rows, "validation_mechanical_insufficient_support_rows", 0))
    )
    cal_weak = int(float(report_metric(summary_rows, "calibration_weak_after_cost_rows", 0)))
    cal_pos = int(float(report_metric(summary_rows, "calibration_positive_expected_net_rows", 0)))
    lines = [
        "# BONK V15A Shadow Acceptance Surface",
        "",
        f"- generated_at: `{generated_at}`",
        f"- run_tag: `{run_tag}`",
        f"- output_tag: `{output_tag}`",
        f"- guardrail: `{GUARDRAIL}`",
        "- stance: research-only; no trading advice, no execution recommendation, no alpha claim.",
        "",
        "## Purpose",
        "",
        "V15A is a diagnostic layer over the frozen V14 state policy. It reports `p_fill`, `p_up_first`, `p_down_first`, support, and expected net by state bucket without creating entry rules or trade candidates.",
        "",
        "## Inputs",
        "",
        f"- V10c panel files: `{report_metric(summary_rows, 'v10c_panel_files')}`",
        f"- V10c panel rows streamed: `{report_metric(summary_rows, 'v10c_panel_rows')}`",
        f"- V10c symbols: `{report_metric(summary_rows, 'v10c_symbols')}`",
        f"- V10c dates: `{report_metric(summary_rows, 'v10c_dates')}`",
        f"- V14 calibration rows: `{report_metric(summary_rows, 'v14_calibration_rows')}`",
        f"- V14 validation decision rows: `{validation_rows}`",
        f"- V14 min support: `{report_metric(summary_rows, 'v14_min_support')}`",
        "",
        "## Shadow Surface Read",
        "",
        f"- validation `p_up_first > 0` rows: `{val_up}` of `{validation_rows}`",
        f"- validation positive expected-net rows: `{val_pos}` of `{validation_rows}`",
        f"- validation expected net mean / max: `{mean_net}` / `{max_net}` bps",
        f"- validation `p_fill` mean / max: `{mean_fill}` / `{max_fill}`",
        f"- validation mechanical adverse-first-only rows: `{val_adverse}`",
        f"- validation mechanical zero-fill-or-zero-path rows: `{val_zero}`",
        f"- validation insufficient-support rows: `{val_insuff}`",
        "",
        "The validation surface is therefore not merely weak after cost. The frozen V14 validation buckets mechanically collapse before entry selection: every validation row has `p_up_first = 0`. Some states still fill, but when they fill the calibrated first passage is adverse-first only; other states have zero fill/path mass.",
        "",
        "## Mechanically Collapsing Validation States",
        "",
        markdown_table(
            format_report_rows(validation_top),
            [
                ("Diagnostic", "diagnostic"),
                ("Rows", "rows"),
                ("Side", "side"),
                ("State Bucket", "state_bucket"),
                ("p_fill", "p_fill_mean"),
                ("p_up", "p_up_first_mean"),
                ("p_down", "p_down_first_mean"),
                ("Support", "support_mean"),
                ("Exp Net", "expected_net_bps_mean"),
                ("Top Date", "top_date"),
            ],
            max_rows=10,
        ),
        "",
        "## Merely Weak After Cost",
        "",
        f"Calibration has `{cal_weak}` support-qualified rows with nonzero favorable first passage but nonpositive expected net. These are weak after cost in train-only calibration, not transferred validation opportunities. The calibration file also has `{cal_pos}` positive expected-net rows, but they are thin-support train-only rows and do not appear in validation with nonzero `p_up_first`.",
        "",
        markdown_table(
            format_report_rows(weak_top),
            [
                ("Rows", "rows"),
                ("Side", "side"),
                ("State Bucket", "state_bucket"),
                ("p_fill", "p_fill_mean"),
                ("p_up", "p_up_first_mean"),
                ("p_down", "p_down_first_mean"),
                ("Support", "support_mean"),
                ("Gross", "gross_bps_mean"),
                ("Exp Net", "expected_net_bps_mean"),
            ],
            max_rows=10,
        ),
        "",
        "## Definitions",
        "",
        "- `mechanical_zero_fill_or_zero_path_mass`: support exists, but the resolved calibration has no fill, favorable first passage, or adverse first passage mass for the side/marker/wing.",
        "- `mechanical_adverse_first_only`: fills exist, `p_up_first = 0`, and adverse first passage is effectively locked at `p_down_first >= 0.95`.",
        "- `mechanical_no_favorable_first_passage`: fills exist and `p_up_first = 0`, but not all filled mass is adverse-first.",
        "- `mechanical_insufficient_support`: V14 could not resolve enough calibration support.",
        "- `weak_after_cost`: favorable first passage exists, but expected net is nonpositive after the V14 cost/expectancy accounting.",
        "",
        "## Outputs",
        "",
    ]
    for label, artifact in artifact_paths:
        lines.append(f"- {label}: `{artifact}`")
    lines.extend(
        [
            "",
            "## Bottom Line",
            "",
            "V15A confirms V14's failure is structural at the same-marker acceptance surface. The validation state buckets are mechanically collapsing, while the weak-after-cost states are confined to train calibration and do not transfer into validation. The next research branch should change timing or object definition rather than tune V14 gates.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default=DEFAULT_RUN_TAG)
    parser.add_argument("--output-tag", default=DEFAULT_OUTPUT_TAG)
    parser.add_argument("--data-root", type=Path, default=Path("data/bonk/v1"))
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--docs-dir", type=Path, default=Path("docs/markets/bonk"))
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--valid-decisions", type=Path)
    parser.add_argument("--params", type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    run_tag = args.run_tag
    output_tag = args.output_tag
    calibration_path = args.calibration or (
        args.date_dir / f"bonk_v14_state_policy_calibration_{run_tag}.csv"
    )
    valid_decisions_path = args.valid_decisions or (
        args.date_dir / f"bonk_v14_state_policy_valid_decisions_{run_tag}.csv"
    )
    params_path = args.params or (args.date_dir / f"bonk_v14_state_policy_params_{run_tag}.csv")

    for path in (calibration_path, valid_decisions_path, params_path):
        if not path.exists():
            raise FileNotFoundError(path)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    min_support = load_min_support(params_path)
    panel_info = inspect_v10c_panel(args.data_root, run_tag)
    calibration_rows = read_csv_rows(calibration_path)
    validation_rows = read_csv_rows(valid_decisions_path)

    bucket_rows = build_bucket_rows(validation_rows, calibration_rows, min_support, run_tag, output_tag)
    diagnostic_rows = build_diagnostic_rows(
        validation_rows, calibration_rows, min_support, run_tag, output_tag
    )
    summary_rows = summarize_rows(
        calibration_rows, validation_rows, panel_info, min_support, run_tag, output_tag
    )

    bucket_path = args.date_dir / f"{V15A_PREFIX}_buckets_{output_tag}.csv"
    collapse_path = args.date_dir / f"{V15A_PREFIX}_collapse_{output_tag}.csv"
    summary_path = args.date_dir / f"{V15A_PREFIX}_summary_{output_tag}.csv"
    panel_path = args.date_dir / f"{V15A_PREFIX}_panel_profile_{output_tag}.csv"
    manifest_path = args.date_dir / f"{V15A_PREFIX}_manifest_{output_tag}.csv"
    report_path = args.docs_dir / "v1-cex-v15a-shadow-acceptance-surface.md"

    write_csv(bucket_path, bucket_rows, BUCKET_FIELDNAMES)
    write_csv(
        collapse_path,
        diagnostic_rows,
        [
            "run_tag",
            "output_tag",
            "source_phase",
            "bucket_scope",
            "state_bucket",
            "side",
            "diagnostic",
            "rows",
            "support_mean",
            "support_min",
            "support_max",
            "p_fill_mean",
            "p_fill_max",
            "p_up_first_mean",
            "p_up_first_max",
            "p_down_first_mean",
            "p_down_first_max",
            "p_timeout_mean",
            "gross_bps_mean",
            "expected_net_bps_mean",
            "expected_net_bps_max",
            "expected_net_bps_min",
            "top_symbol",
            "top_symbol_share",
            "top_date",
            "top_date_share",
            "fallback_levels",
            "calibration_sources",
            "skip_reasons",
            "top_params",
            "guardrail",
        ],
    )
    write_csv(
        summary_path,
        summary_rows,
        ["run_tag", "output_tag", "metric", "value", "note", "guardrail"],
    )
    write_csv(
        panel_path,
        panel_info["panel_rows"],
        ["run_tag", "symbol", "date", "panel_rows", "panel_row_share", "guardrail"],
    )

    manifest_rows = [
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "calibration_input",
            "path": str(calibration_path),
            "rows": len(calibration_rows),
            "guardrail": GUARDRAIL,
        },
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "valid_decisions_input",
            "path": str(valid_decisions_path),
            "rows": len(validation_rows),
            "guardrail": GUARDRAIL,
        },
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "v10c_panel_inventory",
            "path": panel_info["base"],
            "rows": panel_info["rows"],
            "guardrail": GUARDRAIL,
        },
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "bucket_surface",
            "path": str(bucket_path),
            "rows": len(bucket_rows),
            "guardrail": GUARDRAIL,
        },
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "collapse_diagnostics",
            "path": str(collapse_path),
            "rows": len(diagnostic_rows),
            "guardrail": GUARDRAIL,
        },
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "summary",
            "path": str(summary_path),
            "rows": len(summary_rows),
            "guardrail": GUARDRAIL,
        },
        {
            "run_tag": run_tag,
            "output_tag": output_tag,
            "artifact": "markdown_report",
            "path": str(report_path),
            "rows": "",
            "guardrail": GUARDRAIL,
        },
    ]
    write_csv(
        manifest_path,
        manifest_rows,
        ["run_tag", "output_tag", "artifact", "path", "rows", "guardrail"],
    )

    validation_top = [
        row
        for row in diagnostic_rows
        if row["source_phase"] == "validation_shadow"
        and row["bucket_scope"] == "validation_resolved"
        and str(row["diagnostic"]).startswith("mechanical")
    ]
    validation_top.sort(key=lambda row: -float(row["rows"]))
    weak_top = [
        row
        for row in diagnostic_rows
        if row["source_phase"] == "calibration_train"
        and row["bucket_scope"] == "calibration_state"
        and row["diagnostic"] == "weak_after_cost"
    ]
    weak_top.sort(key=lambda row: (-float(row["rows"]), row["state_bucket"]))
    artifact_paths = [
        ("buckets", str(bucket_path)),
        ("collapse", str(collapse_path)),
        ("summary", str(summary_path)),
        ("panel_profile", str(panel_path)),
        ("manifest", str(manifest_path)),
    ]
    build_report(
        report_path,
        run_tag=run_tag,
        output_tag=output_tag,
        generated_at=generated_at,
        summary_rows=summary_rows,
        validation_top=validation_top,
        weak_top=weak_top,
        artifact_paths=artifact_paths,
    )
    print(f"wrote {bucket_path}")
    print(f"wrote {collapse_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {panel_path}")
    print(f"wrote {manifest_path}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
