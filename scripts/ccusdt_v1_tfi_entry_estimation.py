#!/usr/bin/env python
"""Entry-level conditional estimates for the CCUSDT TFI R5+Q structure.

The estimator is intentionally plain: every entry is mapped into observable
factor buckets, then assigned a strict as-of conditional estimate from entries
whose labels were already available before that entry timestamp.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


RUN_TAG = "20260518_ccusdt_v1_tfi_entry_estimation_v1"
INPUT_RUN_TAG = "20260518_ccusdt_v1_tfi_factor_decomp_v1"
GUARDRAIL = "strict_asof_entry_level_factor_estimation_no_future_labels_no_execution_recommendation"
INPUT_FILE_NAME = f"ccusdt_v1_tfi_factor_decomp_entries_{INPUT_RUN_TAG}.csv"
EPS = 1e-12

TARGET_POLICY = {
    "00_none": 0.0,
    "10_r5_only": 0.75,
    "01_frames_only": 0.25,
    "11_r5_frames": 4.0,
}

LEVELS: list[tuple[str, list[str]]] = [
    ("global", []),
    ("cell", ["cell"]),
    ("cell_direction", ["cell", "direction_label"]),
    ("cell_direction_q", ["cell", "direction_label", "frames_q_bin"]),
    ("cell_direction_q_delta10", ["cell", "direction_label", "frames_q_bin", "delta10_bin"]),
    ("cell_direction_q_energy10", ["cell", "direction_label", "frames_q_bin", "energy10_bin"]),
    ("cell_direction_q_z10", ["cell", "direction_label", "frames_q_bin", "z10_bin"]),
    (
        "cell_direction_q_delta10_energy10",
        ["cell", "direction_label", "frames_q_bin", "delta10_bin", "energy10_bin"],
    ),
]


@dataclass(frozen=True)
class Paths:
    entries_csv: Path
    date_dir: Path
    doc_dir: Path
    run_tag: str

    @property
    def entry_scores_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_entry_estimates_{self.run_tag}.csv"

    @property
    def diagnostics_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_entry_estimator_diagnostics_{self.run_tag}.csv"

    @property
    def daily_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_entry_estimator_daily_{self.run_tag}.csv"

    @property
    def bucket_snapshot_csv(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_entry_bucket_snapshot_{self.run_tag}.csv"

    @property
    def summary_json(self) -> Path:
        return self.date_dir / f"ccusdt_v1_tfi_entry_estimation_summary_{self.run_tag}.json"

    @property
    def report_md(self) -> Path:
        return self.doc_dir / f"v1-tfi-entry-estimation-{self.run_tag}.md"


@dataclass
class Bucket:
    values: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        if np.isfinite(value):
            self.values.append(float(value))

    def stats(self) -> dict[str, float]:
        return stats_from_values(self.values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict as-of entry estimator for CCUSDT TFI R5+Q entries.")
    parser.add_argument("--entries-csv", type=Path, default=Path("date") / INPUT_FILE_NAME)
    parser.add_argument("--date-dir", type=Path, default=Path("date"))
    parser.add_argument("--doc-dir", type=Path, default=Path("docs/markets/ccusdt"))
    parser.add_argument("--run-tag", default=RUN_TAG)
    parser.add_argument("--min-global-n", type=int, default=50)
    parser.add_argument("--min-bucket-n", type=int, default=25)
    parser.add_argument("--shrink-k", type=float, default=25.0)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else repo_root() / path


def fmt(value: Any, digits: int = 4) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(f):
        return ""
    return f"{f:.{digits}f}"


def finite_array(values: list[float] | np.ndarray | pd.Series) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype="float64")
    return arr[np.isfinite(arr)]


def safe_div(num: float, den: float) -> float:
    return float(num / den) if np.isfinite(num) and np.isfinite(den) and abs(den) > EPS else np.nan


def cvar(values: np.ndarray, q: float = 0.05) -> float:
    if len(values) == 0:
        return np.nan
    cutoff = float(np.quantile(values, q))
    tail = values[values <= cutoff]
    return float(tail.mean()) if len(tail) else np.nan


def top_tail_share(values: np.ndarray, q: float = 0.90) -> float:
    if len(values) == 0:
        return np.nan
    total = float(values.sum())
    if total <= EPS:
        return np.nan
    cutoff = float(np.quantile(values, q))
    return float(values[values >= cutoff].sum() / total)


def stats_from_values(values: list[float] | np.ndarray | pd.Series) -> dict[str, float]:
    arr = finite_array(values)
    if len(arr) == 0:
        return {
            "hist_n": 0.0,
            "mean_net": np.nan,
            "median_net": np.nan,
            "gt2_rate": np.nan,
            "q90_net": np.nan,
            "cvar05_net": np.nan,
            "tail_share90": np.nan,
            "total_net": 0.0,
        }
    return {
        "hist_n": float(len(arr)),
        "mean_net": float(arr.mean()),
        "median_net": float(np.quantile(arr, 0.50)),
        "gt2_rate": float(np.mean(arr > 2.0)),
        "q90_net": float(np.quantile(arr, 0.90)),
        "cvar05_net": cvar(arr, 0.05),
        "tail_share90": top_tail_share(arr, 0.90),
        "total_net": float(arr.sum()),
    }


def shrink(raw: dict[str, float] | None, parent: dict[str, float] | None, shrink_k: float) -> dict[str, float] | None:
    if raw is None:
        return parent.copy() if parent is not None else None
    n = float(raw.get("hist_n", 0.0))
    if parent is None:
        return raw.copy()
    lam = n / (n + shrink_k) if n > 0 else 0.0
    out = raw.copy()
    for col in ["mean_net", "gt2_rate", "q90_net", "cvar05_net", "tail_share90"]:
        r = raw.get(col, np.nan)
        p = parent.get(col, np.nan)
        if np.isfinite(r) and np.isfinite(p):
            out[col] = float(lam * r + (1.0 - lam) * p)
        elif np.isfinite(p):
            out[col] = float(p)
        elif np.isfinite(r):
            out[col] = float(r)
        else:
            out[col] = np.nan
    out["raw_hist_n"] = n
    out["shrink_lambda"] = lam
    return out


def is_missing(value: Any) -> bool:
    if pd.isna(value):
        return True
    text = str(value)
    return text == "" or text.lower() in {"missing", "nan", "none"}


def key_for(row: pd.Series, columns: list[str]) -> tuple[Any, ...] | None:
    if not columns:
        return ("__global__",)
    vals: list[Any] = []
    for col in columns:
        value = row.get(col)
        if is_missing(value):
            return None
        vals.append(value)
    return tuple(vals)


def key_label(level: str, key: tuple[Any, ...] | None) -> str:
    if key is None:
        return ""
    if level == "global":
        return "global"
    return "|".join(str(x) for x in key)


def bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def load_entries(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in [
        "entry_ts",
        "label_available_ts",
        "entry_row",
        "direction",
        "net",
        "gross",
        "cost",
        "weight",
        "frames_since_mid_change",
        "closed5_delta",
        "closed5_energy",
        "closed5_score_abs",
        "closed10_delta",
        "closed10_energy",
        "closed10_score_abs",
        "closed5_loss_abs_max",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["trade_universe"] = bool_series(df["trade_universe"])
    df = df[df["trade_universe"] & df["net"].notna()].copy()
    df["date"] = df["date"].astype(str)
    df["direction_label"] = df["direction_label"].astype(str)
    df["target_gamma"] = df["cell"].map(TARGET_POLICY).fillna(0.0)
    df["target_exposure"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0.0) * df["target_gamma"]
    df["target_pnl"] = df["target_exposure"] * df["net"]
    return df.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)


def classify_estimate(row: dict[str, Any], global_p_gt2: float, global_cvar: float, min_bucket_n: int) -> str:
    n = float(row.get("est_hist_n", 0.0))
    mu = float(row.get("est_mean_net", np.nan))
    p = float(row.get("est_gt2_rate", np.nan))
    cvar05 = float(row.get("est_cvar05_net", np.nan))
    tail = float(row.get("est_tail_share90", np.nan))
    if n < min_bucket_n or not np.isfinite(mu) or not np.isfinite(p):
        return "insufficient_history"
    if mu > 2.0 and p > global_p_gt2 + 0.05 and np.isfinite(cvar05) and cvar05 >= global_cvar:
        return "strong_positive"
    if mu > 0.0 and p > global_p_gt2:
        if np.isfinite(tail) and tail > 1.25:
            return "positive_right_tail_fragile"
        return "positive_balanced"
    if mu > 0.0:
        return "weak_positive_mean"
    return "avoid_or_reduce"


def update_bucket_maps(
    buckets: dict[str, dict[tuple[Any, ...], Bucket]],
    row: pd.Series,
    value: float,
) -> None:
    for level, columns in LEVELS:
        key = key_for(row, columns)
        if key is not None:
            buckets[level][key].add(value)


def build_entry_estimates(df: pd.DataFrame, min_global_n: int, min_bucket_n: int, shrink_k: float) -> pd.DataFrame:
    by_entry = df.sort_values(["entry_ts", "entry_row"]).reset_index(drop=True)
    by_label = df.sort_values(["label_available_ts", "entry_row"]).reset_index(drop=True)
    buckets: dict[str, dict[tuple[Any, ...], Bucket]] = {level: defaultdict(Bucket) for level, _ in LEVELS}
    same_day_values: dict[str, list[float]] = defaultdict(list)
    same_day_pnl: dict[str, float] = defaultdict(float)
    same_day_exposure: dict[str, float] = defaultdict(float)

    rows: list[dict[str, Any]] = []
    j = 0
    for _, current in by_entry.iterrows():
        entry_ts = float(current["entry_ts"])
        while j < len(by_label) and float(by_label.at[j, "label_available_ts"]) <= entry_ts:
            hist = by_label.iloc[j]
            value = float(hist["net"])
            update_bucket_maps(buckets, hist, value)
            date = str(hist["date"])
            same_day_values[date].append(value)
            same_day_pnl[date] += float(hist.get("target_pnl", 0.0))
            same_day_exposure[date] += float(hist.get("target_exposure", 0.0))
            j += 1

        parent: dict[str, float] | None = None
        level_rows: list[dict[str, Any]] = []
        for depth, (level, columns) in enumerate(LEVELS):
            key = key_for(current, columns)
            raw = buckets[level][key].stats() if key is not None and key in buckets[level] else None
            est = shrink(raw, parent, shrink_k)
            if est is not None:
                rec = {
                    "level": level,
                    "depth": depth,
                    "key": key,
                    "key_label": key_label(level, key),
                    "hist_n": float(est.get("hist_n", 0.0)),
                    "raw_hist_n": float(est.get("raw_hist_n", est.get("hist_n", 0.0))),
                    "mean_net": float(est.get("mean_net", np.nan)),
                    "median_net": float(est.get("median_net", np.nan)),
                    "gt2_rate": float(est.get("gt2_rate", np.nan)),
                    "q90_net": float(est.get("q90_net", np.nan)),
                    "cvar05_net": float(est.get("cvar05_net", np.nan)),
                    "tail_share90": float(est.get("tail_share90", np.nan)),
                    "shrink_lambda": float(est.get("shrink_lambda", 1.0)),
                }
                level_rows.append(rec)
                parent = est
            elif parent is not None:
                level_rows.append(
                    {
                        "level": level,
                        "depth": depth,
                        "key": key,
                        "key_label": key_label(level, key),
                        "hist_n": 0.0,
                        "raw_hist_n": 0.0,
                        "mean_net": float(parent.get("mean_net", np.nan)),
                        "median_net": float(parent.get("median_net", np.nan)),
                        "gt2_rate": float(parent.get("gt2_rate", np.nan)),
                        "q90_net": float(parent.get("q90_net", np.nan)),
                        "cvar05_net": float(parent.get("cvar05_net", np.nan)),
                        "tail_share90": float(parent.get("tail_share90", np.nan)),
                        "shrink_lambda": 0.0,
                    }
                )

        global_row = next((x for x in level_rows if x["level"] == "global"), None)
        if global_row is None or global_row["hist_n"] < min_global_n:
            chosen = None
        else:
            candidates = [x for x in level_rows if x["raw_hist_n"] >= min_bucket_n and np.isfinite(x["mean_net"])]
            chosen = max(candidates, key=lambda x: x["depth"]) if candidates else global_row

        date = str(current["date"])
        same_vals = same_day_values.get(date, [])
        same_n = len(same_vals)
        same_mean = float(np.mean(same_vals)) if same_n else np.nan
        same_target_mean = safe_div(same_day_pnl[date], same_day_exposure[date])
        if same_n < 10:
            same_regime = "same_day_low_history"
        elif np.isfinite(same_target_mean) and same_target_mean < 0.0:
            same_regime = "same_day_negative"
        elif np.isfinite(same_target_mean) and same_target_mean > 2.0:
            same_regime = "same_day_strong"
        else:
            same_regime = "same_day_neutral"

        out = {
            "fold": current.get("fold", ""),
            "date": date,
            "entry_row": current.get("entry_row", np.nan),
            "entry_ts": current.get("entry_ts", np.nan),
            "label_available_ts": current.get("label_available_ts", np.nan),
            "cell": current.get("cell", ""),
            "direction_label": current.get("direction_label", ""),
            "frames_q_bin": current.get("frames_q_bin", ""),
            "delta10_bin": current.get("delta10_bin", ""),
            "energy10_bin": current.get("energy10_bin", ""),
            "z10_bin": current.get("z10_bin", ""),
            "loss5_bin": current.get("loss5_bin", ""),
            "closed10_delta": current.get("closed10_delta", np.nan),
            "closed10_energy": current.get("closed10_energy", np.nan),
            "closed10_score_abs": current.get("closed10_score_abs", np.nan),
            "net": current.get("net", np.nan),
            "gross": current.get("gross", np.nan),
            "cost": current.get("cost", np.nan),
            "weight": current.get("weight", np.nan),
            "target_gamma": current.get("target_gamma", np.nan),
            "target_exposure": current.get("target_exposure", np.nan),
            "target_pnl": current.get("target_pnl", np.nan),
            "same_day_prior_n": same_n,
            "same_day_prior_mean_net": same_mean,
            "same_day_prior_target_mean_net": same_target_mean,
            "same_day_regime": same_regime,
        }
        if chosen is None:
            out.update(
                {
                    "estimate_level": "none",
                    "estimate_key": "",
                    "est_hist_n": 0.0,
                    "est_raw_hist_n": 0.0,
                    "est_mean_net": np.nan,
                    "est_median_net": np.nan,
                    "est_gt2_rate": np.nan,
                    "est_q90_net": np.nan,
                    "est_cvar05_net": np.nan,
                    "est_tail_share90": np.nan,
                    "est_shrink_lambda": np.nan,
                    "global_hist_n": global_row["hist_n"] if global_row else 0.0,
                    "global_gt2_rate": global_row["gt2_rate"] if global_row else np.nan,
                    "global_cvar05_net": global_row["cvar05_net"] if global_row else np.nan,
                    "entry_quality_class": "insufficient_history",
                }
            )
        else:
            global_p = float(global_row["gt2_rate"]) if global_row is not None else np.nan
            global_c = float(global_row["cvar05_net"]) if global_row is not None else np.nan
            out.update(
                {
                    "estimate_level": chosen["level"],
                    "estimate_key": chosen["key_label"],
                    "est_hist_n": chosen["hist_n"],
                    "est_raw_hist_n": chosen["raw_hist_n"],
                    "est_mean_net": chosen["mean_net"],
                    "est_median_net": chosen["median_net"],
                    "est_gt2_rate": chosen["gt2_rate"],
                    "est_q90_net": chosen["q90_net"],
                    "est_cvar05_net": chosen["cvar05_net"],
                    "est_tail_share90": chosen["tail_share90"],
                    "est_shrink_lambda": chosen["shrink_lambda"],
                    "global_hist_n": global_row["hist_n"],
                    "global_gt2_rate": global_p,
                    "global_cvar05_net": global_c,
                }
            )
            out["entry_quality_class"] = classify_estimate(out, global_p, global_c, min_bucket_n)
        rows.append(out)

    return pd.DataFrame(rows)


def subset_stats(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "entries": 0,
            "exposure": 0.0,
            "total_net": 0.0,
            "mean_net": np.nan,
            "median_net": np.nan,
            "gt2_rate": np.nan,
            "q90_net": np.nan,
            "cvar05_net": np.nan,
            "tail_share90": np.nan,
            "hit_est_gt0_rate": np.nan,
        }
    net = finite_array(frame["net"])
    pnl = pd.to_numeric(frame["target_pnl"], errors="coerce").to_numpy(dtype="float64")
    exposure = pd.to_numeric(frame["target_exposure"], errors="coerce").to_numpy(dtype="float64")
    finite_pnl = pnl[np.isfinite(pnl)]
    finite_exp = exposure[np.isfinite(exposure)]
    return {
        "entries": int(len(frame)),
        "exposure": float(finite_exp.sum()) if len(finite_exp) else 0.0,
        "total_net": float(finite_pnl.sum()) if len(finite_pnl) else 0.0,
        "mean_net": float(net.mean()) if len(net) else np.nan,
        "weighted_mean_net": safe_div(float(finite_pnl.sum()), float(finite_exp.sum())) if len(finite_exp) else np.nan,
        "median_net": float(np.quantile(net, 0.50)) if len(net) else np.nan,
        "gt2_rate": float(np.mean(net > 2.0)) if len(net) else np.nan,
        "q90_net": float(np.quantile(net, 0.90)) if len(net) else np.nan,
        "cvar05_net": cvar(net, 0.05),
        "tail_share90": top_tail_share(net, 0.90),
        "hit_est_gt0_rate": float(np.mean(pd.to_numeric(frame["est_mean_net"], errors="coerce") > 0.0)),
    }


def grouped_table(df: pd.DataFrame, columns: list[str], name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(columns, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {"view": name}
        row.update(dict(zip(columns, keys)))
        row.update(subset_stats(group))
        rows.append(row)
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["weighted_mean_net", "entries"], ascending=[False, False]).reset_index(drop=True)
    return out


def add_estimate_bins(scores: pd.DataFrame) -> pd.DataFrame:
    out = scores.copy()
    valid = out["est_mean_net"].notna()
    if valid.sum() >= 10:
        out.loc[valid, "est_mean_decile"] = pd.qcut(
            out.loc[valid, "est_mean_net"].rank(method="first"),
            q=10,
            labels=[f"d{i}" for i in range(1, 11)],
        ).astype(str)
    else:
        out["est_mean_decile"] = "missing"
    valid_p = out["est_gt2_rate"].notna()
    if valid_p.sum() >= 10:
        out.loc[valid_p, "est_gt2_decile"] = pd.qcut(
            out.loc[valid_p, "est_gt2_rate"].rank(method="first"),
            q=10,
            labels=[f"d{i}" for i in range(1, 11)],
        ).astype(str)
    else:
        out["est_gt2_decile"] = "missing"
    out["est_mean_decile"] = out["est_mean_decile"].fillna("missing")
    out["est_gt2_decile"] = out["est_gt2_decile"].fillna("missing")
    return out


def build_diagnostics(scores: pd.DataFrame) -> pd.DataFrame:
    tables = [
        grouped_table(scores, ["entry_quality_class"], "entry_quality_class"),
        grouped_table(scores, ["estimate_level"], "estimate_level"),
        grouped_table(scores, ["est_mean_decile"], "est_mean_decile"),
        grouped_table(scores, ["est_gt2_decile"], "est_gt2_decile"),
        grouped_table(scores, ["cell", "entry_quality_class"], "cell_x_quality"),
        grouped_table(scores, ["same_day_regime", "entry_quality_class"], "same_day_regime_x_quality"),
    ]
    return pd.concat(tables, ignore_index=True)


def build_daily(scores: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (date, quality), group in scores.groupby(["date", "entry_quality_class"], sort=True):
        row = {"date": date, "entry_quality_class": quality}
        row.update(subset_stats(group))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["date", "entry_quality_class"]).reset_index(drop=True)


def build_bucket_snapshot(df: pd.DataFrame, shrink_k: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    global_stats = stats_from_values(df["net"])
    for level, columns in LEVELS:
        if level == "global":
            row = {"level": level, "key": "global"}
            row.update(global_stats)
            rows.append(row)
            continue
        for keys, group in df.groupby(columns, dropna=False, sort=True):
            if not isinstance(keys, tuple):
                keys = (keys,)
            if any(is_missing(v) for v in keys):
                continue
            raw = stats_from_values(group["net"])
            shrunk = shrink(raw, global_stats, shrink_k) or raw
            row = {"level": level, "key": "|".join(str(x) for x in keys)}
            row.update({f"raw_{k}": v for k, v in raw.items()})
            row.update({f"shrunk_{k}": v for k, v in shrunk.items() if k not in {"raw_hist_n", "shrink_lambda"}})
            row["shrink_lambda"] = shrunk.get("shrink_lambda", 1.0)
            rows.append(row)
    out = pd.DataFrame(rows)
    if len(out):
        mean_col = "shrunk_mean_net" if "shrunk_mean_net" in out.columns else "mean_net"
        out = out.sort_values([mean_col, "key"], ascending=[False, True]).reset_index(drop=True)
    return out


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> list[str]:
    if df.empty:
        return ["", "_No rows._", ""]
    cols = [col for col in columns if col in df.columns]
    view = df.loc[:, cols].head(max_rows).copy()
    lines = ["", "| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        cells: list[str] = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                cells.append(fmt(value))
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def write_report(
    paths: Paths,
    scores: pd.DataFrame,
    diagnostics: pd.DataFrame,
    daily: pd.DataFrame,
    snapshot: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.extend(
        [
            "# CCUSDT TFI Entry-Level Estimation",
            "",
            f"Status: `{paths.run_tag}`.",
            "",
            f"Guardrail: `{GUARDRAIL}`.",
            "",
            "This report estimates each candidate entry from observable factor buckets using only labels available before the entry timestamp.",
            "",
            "## Estimator",
            "",
            "For entry `i` at time `t_i`, the admissible history is:",
            "",
            "$$",
            "\\mathcal{H}_{t_i}=\\{j:\\ label\\_available\\_ts_j\\le t_i\\}.",
            "$$",
            "",
            "For a bucket `A(x_i)`, raw estimates are:",
            "",
            "$$",
            "\\mu_A=\\mathbb{E}[r\\mid A],\\quad p_A=\\mathbb{P}(r>2\\mathrm{bps}\\mid A),\\quad L_A=\\operatorname{CVaR}_{5\\%}(r\\mid A).",
            "$$",
            "",
            "The reported estimate uses hierarchical shrinkage to the parent bucket:",
            "",
            "$$",
            "\\widehat\\mu_A=\\lambda_A\\bar r_A+(1-\\lambda_A)\\widehat\\mu_{\\pi(A)},\\quad \\lambda_A=\\frac{n_A}{n_A+k}.",
            "$$",
            "",
            "The hierarchy is:",
            "",
            "`global -> cell -> cell_direction -> cell_direction_q -> cell_direction_q_delta10/energy10/z10 -> cell_direction_q_delta10_energy10`.",
            "",
            "## Main Read",
            "",
            f"1. Active entries scored: `{summary.get('entries')}`; entries with strict estimates: `{summary.get('estimated_entries')}`.",
            f"2. Best realized quality class by weighted mean: `{summary.get('best_quality_class')}` with `{fmt(summary.get('best_quality_weighted_mean'), 4)}` bps.",
            f"3. Worst realized quality class by weighted mean: `{summary.get('worst_quality_class')}` with `{fmt(summary.get('worst_quality_weighted_mean'), 4)}` bps.",
            f"4. Worst day remains `{summary.get('worst_day')}` with total `{fmt(summary.get('worst_day_total_net'), 4)}` under target exposure.",
            f"5. Core high-quality classes (`strong_positive + positive_right_tail_fragile`) have total `{fmt(summary.get('core_high_total_net'), 4)}`, weighted mean `{fmt(summary.get('core_high_weighted_mean'), 4)}` bps, and worst daily total `{fmt(summary.get('core_high_worst_day_total_net'), 4)}`.",
            f"6. Reduce-side classes (`weak_positive_mean + avoid_or_reduce + insufficient_history`) have total `{fmt(summary.get('reduce_side_total_net'), 4)}`, weighted mean `{fmt(summary.get('reduce_side_weighted_mean'), 4)}` bps, and worst daily total `{fmt(summary.get('reduce_side_worst_day_total_net'), 4)}`.",
            "",
            "## Diagnostics",
        ]
    )
    diag_view = diagnostics[diagnostics["view"].isin(["entry_quality_class", "est_mean_decile", "cell_x_quality"])].copy()
    lines.extend(
        markdown_table(
            diag_view,
            [
                "view",
                "entry_quality_class",
                "est_mean_decile",
                "cell",
                "entries",
                "exposure",
                "total_net",
                "weighted_mean_net",
                "mean_net",
                "median_net",
                "gt2_rate",
                "cvar05_net",
                "tail_share90",
            ],
            max_rows=45,
        )
    )
    lines.extend(["## Daily Quality Attribution"])
    lines.extend(
        markdown_table(
            daily,
            [
                "date",
                "entry_quality_class",
                "entries",
                "exposure",
                "total_net",
                "weighted_mean_net",
                "mean_net",
                "gt2_rate",
                "cvar05_net",
            ],
            max_rows=60,
        )
    )
    lines.extend(["## Current Bucket Snapshot"])
    lines.extend(
        markdown_table(
            snapshot,
            [
                "level",
                "key",
                "raw_hist_n",
                "raw_mean_net",
                "raw_gt2_rate",
                "raw_cvar05_net",
                "raw_tail_share90",
                "shrunk_mean_net",
                "shrunk_gt2_rate",
                "shrunk_cvar05_net",
                "shrink_lambda",
            ],
            max_rows=40,
        )
    )
    lines.extend(
        [
            "## Interpretation",
            "",
            "- `strong_positive` means prior bucket mean is above `2` bps, right-tail rate is better than global, and left tail is not worse than global.",
            "- `positive_right_tail_fragile` means expected value is positive but top-tail dependence is high; these entries can be profitable while still fragile.",
            "- `avoid_or_reduce` is a statistical estimate class, not a proof that the signal has no value; it says this exact as-of bucket did not justify full exposure.",
            "",
            "## Outputs",
            "",
            f"- `{paths.entry_scores_csv}`",
            f"- `{paths.diagnostics_csv}`",
            f"- `{paths.daily_csv}`",
            f"- `{paths.bucket_snapshot_csv}`",
            f"- `{paths.summary_json}`",
            "",
            "## Reproduce",
            "",
            "```powershell",
            "python scripts/ccusdt_v1_tfi_entry_estimation.py",
            "```",
            "",
        ]
    )
    paths.report_md.write_text("\n".join(lines), encoding="utf-8")


def build_summary(scores: pd.DataFrame, diagnostics: pd.DataFrame) -> dict[str, Any]:
    qdiag = diagnostics[diagnostics["view"].eq("entry_quality_class")].copy()
    estimated = scores[scores["estimate_level"].ne("none")]
    best = qdiag.sort_values(["weighted_mean_net", "entries"], ascending=[False, False]).head(1)
    worst = qdiag.sort_values(["weighted_mean_net", "entries"], ascending=[True, False]).head(1)
    daily_total = scores.groupby("date", sort=True).agg(total_net=("target_pnl", "sum"), entries=("net", "size")).reset_index()
    worst_day = daily_total.sort_values("total_net").head(1)
    top_decile = diagnostics[(diagnostics["view"].eq("est_mean_decile")) & (diagnostics["est_mean_decile"].eq("d10"))]
    bottom_decile = diagnostics[(diagnostics["view"].eq("est_mean_decile")) & (diagnostics["est_mean_decile"].eq("d1"))]
    def group_summary(classes: list[str]) -> dict[str, Any]:
        sub = scores[scores["entry_quality_class"].isin(classes)].copy()
        stats = subset_stats(sub)
        if len(sub):
            daily = sub.groupby("date", sort=True).agg(total_net=("target_pnl", "sum")).reset_index()
            worst_daily = daily.sort_values("total_net").head(1)
            positive_days = int((daily["total_net"] > 0.0).sum())
            day_count = int(len(daily))
        else:
            worst_daily = pd.DataFrame()
            positive_days = 0
            day_count = 0
        return {
            "entries": stats["entries"],
            "exposure": stats["exposure"],
            "total_net": stats["total_net"],
            "weighted_mean": stats["weighted_mean_net"],
            "worst_day": worst_daily.iloc[0]["date"] if len(worst_daily) else None,
            "worst_day_total_net": worst_daily.iloc[0]["total_net"] if len(worst_daily) else None,
            "positive_days": positive_days,
            "day_count": day_count,
        }

    core_high = group_summary(["strong_positive", "positive_right_tail_fragile"])
    positive_all = group_summary(["strong_positive", "positive_right_tail_fragile", "positive_balanced"])
    reduce_side = group_summary(["weak_positive_mean", "avoid_or_reduce", "insufficient_history"])
    summary = {
        "run_tag": RUN_TAG,
        "guardrail": GUARDRAIL,
        "entries": int(len(scores)),
        "estimated_entries": int(len(estimated)),
        "date_min": str(scores["date"].min()) if len(scores) else None,
        "date_max": str(scores["date"].max()) if len(scores) else None,
        "best_quality_class": best.iloc[0]["entry_quality_class"] if len(best) else None,
        "best_quality_weighted_mean": best.iloc[0]["weighted_mean_net"] if len(best) else None,
        "worst_quality_class": worst.iloc[0]["entry_quality_class"] if len(worst) else None,
        "worst_quality_weighted_mean": worst.iloc[0]["weighted_mean_net"] if len(worst) else None,
        "worst_day": worst_day.iloc[0]["date"] if len(worst_day) else None,
        "worst_day_total_net": worst_day.iloc[0]["total_net"] if len(worst_day) else None,
        "top_est_mean_decile_weighted_mean": top_decile.iloc[0]["weighted_mean_net"] if len(top_decile) else None,
        "bottom_est_mean_decile_weighted_mean": bottom_decile.iloc[0]["weighted_mean_net"] if len(bottom_decile) else None,
    }
    for prefix, stats in [
        ("core_high", core_high),
        ("positive_all", positive_all),
        ("reduce_side", reduce_side),
    ]:
        for key, value in stats.items():
            summary[f"{prefix}_{key}"] = value
    return summary


def main() -> None:
    args = parse_args()
    paths = Paths(
        entries_csv=resolve_repo_path(args.entries_csv),
        date_dir=resolve_repo_path(args.date_dir),
        doc_dir=resolve_repo_path(args.doc_dir),
        run_tag=args.run_tag,
    )
    paths.date_dir.mkdir(parents=True, exist_ok=True)
    paths.doc_dir.mkdir(parents=True, exist_ok=True)

    entries = load_entries(paths.entries_csv)
    scores = build_entry_estimates(entries, args.min_global_n, args.min_bucket_n, args.shrink_k)
    scores = add_estimate_bins(scores)
    diagnostics = build_diagnostics(scores)
    daily = build_daily(scores)
    snapshot = build_bucket_snapshot(entries, args.shrink_k)
    summary = build_summary(scores, diagnostics)
    summary["run_tag"] = paths.run_tag
    summary["input_entries_csv"] = str(paths.entries_csv)
    summary["min_global_n"] = args.min_global_n
    summary["min_bucket_n"] = args.min_bucket_n
    summary["shrink_k"] = args.shrink_k

    scores.to_csv(paths.entry_scores_csv, index=False)
    diagnostics.to_csv(paths.diagnostics_csv, index=False)
    daily.to_csv(paths.daily_csv, index=False)
    snapshot.to_csv(paths.bucket_snapshot_csv, index=False)
    paths.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(paths, scores, diagnostics, daily, snapshot, summary)

    print(
        json.dumps(
            {
                "run_tag": paths.run_tag,
                "entries": int(len(scores)),
                "estimated_entries": int(scores["estimate_level"].ne("none").sum()),
                "report": str(paths.report_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
