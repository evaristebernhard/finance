#!/usr/bin/env python
"""Run a research-only tree diagnostic on CCUSDT microstructure factors.

This diagnostic is intentionally outside Runner/Bot runtime. It uses only
exchange-visible feature columns as model inputs, then evaluates future path
labels as research labels. The output is an OOS diagnostic table, not a strategy
promotion artifact.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

import microstructure_factor_diagnostic as mfd


DEFAULT_OUT_ROOT = Path("systems/ccusdt_replay_exchange/runs/microstructure_tree_diagnostic")
DEFAULT_REPORT = Path("docs/markets/ccusdt/research/factors/v1-microstructure-tree-diagnostic-20260601.md")


@dataclass(frozen=True)
class TreeLabelSpec:
    name: str
    long_column: str
    short_column: str
    description: str


TREE_LABELS = {
    "mid_terminal_60s": TreeLabelSpec(
        "mid_terminal_60s",
        "fwd_mid_return_bps",
        "short_mid_return_bps",
        "Directional terminal mid return over the configured horizon.",
    ),
    "release_mfe_10s": TreeLabelSpec(
        "release_mfe_10s",
        "long_mfe_bps",
        "short_mfe_bps",
        "Directional maximum favorable mid excursion over the release window.",
    ),
    "top_of_book_executable_60s": TreeLabelSpec(
        "top_of_book_executable_60s",
        "long_executable_bps",
        "short_executable_bps",
        "Directional top-of-book taker entry plus fixed-horizon exit return.",
    ),
    "decay_avoidance_60s_after_mfe": TreeLabelSpec(
        "decay_avoidance_60s_after_mfe",
        "long_decay_avoidance_bps",
        "short_decay_avoidance_bps",
        "Negative directional decay after release; higher means less release was given back.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--symbol", default="CCUSDT")
    parser.add_argument("--from-date", default="2026-05-16")
    parser.add_argument("--to-date", default="2026-05-18")
    parser.add_argument("--source", choices=["decision_frame", "fixed_event"], default="fixed_event")
    parser.add_argument("--horizon-sec", type=int, default=60)
    parser.add_argument("--release-sec", type=int, default=10)
    parser.add_argument("--memory-windows", default="5,10")
    parser.add_argument("--labels", default="mid_terminal_60s,release_mfe_10s,top_of_book_executable_60s,decay_avoidance_60s_after_mfe")
    parser.add_argument("--fold-mode", choices=["leave_one_day_out", "walk_forward"], default="leave_one_day_out")
    parser.add_argument("--top-quantile", type=float, default=0.8)
    parser.add_argument("--bottom-quantile", type=float, default=0.2)
    parser.add_argument("--max-train-rows", type=int, default=120_000)
    parser.add_argument("--max-test-rows", type=int, default=0)
    parser.add_argument("--n-estimators", type=int, default=48)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--min-samples-leaf", type=int, default=500)
    parser.add_argument("--random-state", type=int, default=20260601)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def parse_csv_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def format_float(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def stride_sample_frame(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if max_rows <= 0 or len(df) <= max_rows:
        return df
    stride = max(1, int(math.ceil(len(df) / max_rows)))
    return df.iloc[::stride].head(max_rows)


def make_model(args: argparse.Namespace, salt: int) -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "tree",
                ExtraTreesRegressor(
                    n_estimators=args.n_estimators,
                    max_depth=args.max_depth,
                    min_samples_leaf=args.min_samples_leaf,
                    max_features=0.7,
                    random_state=args.random_state + salt,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def load_source_day(repo_root: Path, symbol: str, source: str, day: str, max_rows: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    if source == "decision_frame":
        return mfd.load_decision_frames(repo_root, symbol, day, max_rows)
    fixed_df, manifest = mfd.load_fixed_event_panel(repo_root, symbol, day, max_rows)
    if fixed_df is None:
        raise FileNotFoundError(f"fixed_event_panel missing for {symbol} {day}")
    return fixed_df, manifest


def add_tree_labels(df: pd.DataFrame, horizon_sec: int, release_sec: int) -> pd.DataFrame:
    labelled = mfd.add_labels(df, horizon_sec, release_sec)
    labelled["short_mid_return_bps"] = -labelled["fwd_mid_return_bps"].astype(float)
    labelled["long_decay_avoidance_bps"] = -(
        labelled["long_mfe_bps"].astype(float) - labelled["fwd_mid_return_bps"].astype(float)
    )
    labelled["short_decay_avoidance_bps"] = -(
        labelled["short_mfe_bps"].astype(float) + labelled["fwd_mid_return_bps"].astype(float)
    )
    return labelled


def build_feature_frame(df: pd.DataFrame, specs: list[mfd.FactorSpec], windows: list[int]) -> pd.DataFrame:
    features: dict[str, pd.Series] = {}
    for spec in specs:
        if spec.column not in df.columns:
            continue
        transforms = (
            mfd.memory_transforms(df[spec.column], windows)
            if spec.signed
            else {"raw": pd.to_numeric(df[spec.column], errors="coerce")}
        )
        for transform_name, transformed in transforms.items():
            features[f"{spec.primitive}__{transform_name}"] = pd.to_numeric(transformed, errors="coerce")
    return pd.DataFrame(features, index=df.index).replace([np.inf, -np.inf], np.nan)


def prepare_dataset(
    repo_root: Path,
    symbol: str,
    source: str,
    days: list[str],
    windows: list[int],
    horizon_sec: int,
    release_sec: int,
    max_rows_per_day: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[str]]:
    specs = mfd.DECISION_FACTOR_SPECS if source == "decision_frame" else mfd.FIXED_EVENT_FACTOR_SPECS
    frames: list[pd.DataFrame] = []
    manifests: list[dict[str, Any]] = []
    feature_names: list[str] | None = None
    for day in days:
        print(f"microstructure_tree_diagnostic source={source} day={day}", file=sys.stderr, flush=True)
        raw_df, manifest = load_source_day(repo_root, symbol, source, day, max_rows_per_day)
        labelled = add_tree_labels(raw_df, horizon_sec, release_sec)
        features = build_feature_frame(labelled, specs, windows)
        if feature_names is None:
            feature_names = list(features.columns)
        else:
            for name in feature_names:
                if name not in features.columns:
                    features[name] = np.nan
            extra = [name for name in features.columns if name not in feature_names]
            if extra:
                feature_names.extend(extra)
        labels = labelled[
            [
                "date",
                "local_ts_us",
                "fwd_mid_return_bps",
                "short_mid_return_bps",
                "long_mfe_bps",
                "short_mfe_bps",
                "long_executable_bps",
                "short_executable_bps",
                "long_decay_avoidance_bps",
                "short_decay_avoidance_bps",
                "spread_bps",
            ]
        ].reset_index(drop=True)
        day_frame = pd.concat([labels, features.reset_index(drop=True)], axis=1)
        frames.append(day_frame)
        manifest = dict(manifest)
        manifest["date"] = day
        manifest["source"] = source
        manifest["row_count"] = int(len(day_frame))
        manifests.append(manifest)
    if not frames:
        raise RuntimeError("no source frames loaded")
    all_features = feature_names or []
    for idx, frame in enumerate(frames):
        for name in all_features:
            if name not in frame.columns:
                frame[name] = np.nan
        frames[idx] = frame
    return pd.concat(frames, ignore_index=True), manifests, all_features


def finite_mask(*arrays: pd.Series | np.ndarray) -> np.ndarray:
    mask: np.ndarray | None = None
    for array in arrays:
        values = np.asarray(array, dtype=float)
        current = np.isfinite(values)
        mask = current if mask is None else (mask & current)
    return mask if mask is not None else np.array([], dtype=bool)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    data = pd.DataFrame({"a": a, "b": b}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 3 or data["a"].nunique() < 2 or data["b"].nunique() < 2:
        return math.nan
    return float(data["a"].corr(data["b"], method="spearman"))


def cvar05(values: np.ndarray) -> float:
    clean = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return math.nan
    threshold = clean.quantile(0.05)
    return float(clean[clean <= threshold].mean())


def summarize_prediction(
    *,
    pred_long: np.ndarray,
    pred_short: np.ndarray,
    actual_long: np.ndarray,
    actual_short: np.ndarray,
    top_q: float,
    bottom_q: float,
) -> dict[str, Any]:
    pred_edge = np.maximum(pred_long, pred_short)
    pred_contrast = pred_long - pred_short
    actual_contrast = actual_long - actual_short
    long_side = pred_long >= pred_short
    actual_value = np.where(long_side, actual_long, actual_short)
    data = pd.DataFrame(
        {
            "pred_edge": pred_edge,
            "pred_contrast": pred_contrast,
            "actual_contrast": actual_contrast,
            "actual_value": actual_value,
            "long_side": long_side.astype(float),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 20 or data["pred_edge"].nunique() < 3:
        return {
            "n_test": int(len(data)),
            "pred_edge_spearman": math.nan,
            "pred_side_spearman": math.nan,
            "all_mean_bps": math.nan,
            "top_mean_bps": math.nan,
            "top_median_bps": math.nan,
            "top_bottom_bps": math.nan,
            "top_cvar05_bps": math.nan,
            "long_share": math.nan,
        }
    top_cut = data["pred_edge"].quantile(top_q)
    bottom_cut = data["pred_edge"].quantile(bottom_q)
    top = data[data["pred_edge"] >= top_cut]["actual_value"]
    bottom = data[data["pred_edge"] <= bottom_cut]["actual_value"]
    return {
        "n_test": int(len(data)),
        "pred_edge_spearman": spearman(data["pred_edge"].to_numpy(), data["actual_value"].to_numpy()),
        "pred_side_spearman": spearman(data["pred_contrast"].to_numpy(), data["actual_contrast"].to_numpy()),
        "all_mean_bps": float(data["actual_value"].mean()),
        "top_mean_bps": float(top.mean()) if len(top) else math.nan,
        "top_median_bps": float(top.median()) if len(top) else math.nan,
        "top_bottom_bps": float(top.mean() - bottom.mean()) if len(top) and len(bottom) else math.nan,
        "top_cvar05_bps": cvar05(top.to_numpy()) if len(top) else math.nan,
        "long_share": float(data["long_side"].mean()),
    }


def build_folds(days: list[str], mode: str) -> list[tuple[list[str], str]]:
    folds: list[tuple[list[str], str]] = []
    if mode == "walk_forward":
        for idx in range(1, len(days)):
            folds.append((days[:idx], days[idx]))
        return folds
    for day in days:
        folds.append(([other for other in days if other != day], day))
    return folds


def run_label_fold(
    data: pd.DataFrame,
    feature_names: list[str],
    label_spec: TreeLabelSpec,
    train_days: list[str],
    test_day: str,
    args: argparse.Namespace,
    salt: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], pd.DataFrame]:
    train = data[data["date"].isin(train_days)].copy()
    test = data[data["date"].eq(test_day)].copy()
    train = stride_sample_frame(train, args.max_train_rows)
    test = stride_sample_frame(test, args.max_test_rows)

    train_mask = finite_mask(train[label_spec.long_column], train[label_spec.short_column])
    test_mask = finite_mask(test[label_spec.long_column], test[label_spec.short_column])
    train = train.loc[train_mask].reset_index(drop=True)
    test = test.loc[test_mask].reset_index(drop=True)
    if len(train) < 100 or len(test) < 100:
        empty = {
            "label": label_spec.name,
            "test_date": test_day,
            "train_dates": ",".join(train_days),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "status": "insufficient_data",
        }
        return empty, [], pd.DataFrame()

    x_train = train[feature_names]
    x_test = test[feature_names]
    model_long = make_model(args, salt * 2)
    model_short = make_model(args, salt * 2 + 1)
    model_long.fit(x_train, train[label_spec.long_column].astype(float))
    model_short.fit(x_train, train[label_spec.short_column].astype(float))
    pred_long = model_long.predict(x_test)
    pred_short = model_short.predict(x_test)
    metrics = summarize_prediction(
        pred_long=pred_long,
        pred_short=pred_short,
        actual_long=test[label_spec.long_column].to_numpy(dtype=float),
        actual_short=test[label_spec.short_column].to_numpy(dtype=float),
        top_q=args.top_quantile,
        bottom_q=args.bottom_quantile,
    )
    row = {
        "label": label_spec.name,
        "test_date": test_day,
        "train_dates": ",".join(train_days),
        "n_train": int(len(train)),
        "status": "research_only_oos_tree_diagnostic",
    }
    row.update(metrics)

    long_importance = model_long.named_steps["tree"].feature_importances_
    short_importance = model_short.named_steps["tree"].feature_importances_
    importance_rows = []
    for name, long_value, short_value in zip(feature_names, long_importance, short_importance):
        importance_rows.append(
            {
                "label": label_spec.name,
                "test_date": test_day,
                "feature": name,
                "importance_mean": float((long_value + short_value) / 2.0),
                "importance_long": float(long_value),
                "importance_short": float(short_value),
            }
        )

    pred_frame = pd.DataFrame(
        {
            "date": test_day,
            "label": label_spec.name,
            "pred_long": pred_long,
            "pred_short": pred_short,
            "actual_long": test[label_spec.long_column].to_numpy(dtype=float),
            "actual_short": test[label_spec.short_column].to_numpy(dtype=float),
        }
    )
    return row, importance_rows, pred_frame


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict[str, Any], metric_rows: list[dict[str, Any]], importance_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = pd.DataFrame(metric_rows)
    importances = pd.DataFrame(importance_rows)
    lines: list[str] = []
    lines.append("# CCUSDT Microstructure Tree Diagnostic v0.1")
    lines.append("")
    lines.append("Guardrail: `research_only_no_strategy_promotion_no_runtime_label_dependency`.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    for key in [
        "symbol",
        "from_date",
        "to_date",
        "source",
        "fold_mode",
        "horizon_sec",
        "release_sec",
        "max_train_rows",
        "model",
        "out_dir",
    ]:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")
    lines.append("Interpretation: each tree predicts long-side and short-side future values separately from runtime-safe feature columns. The chosen diagnostic side is the side with higher predicted value. These future values are labels only; they are not runtime inputs.")
    lines.append("")
    lines.append("## OOS Metrics")
    lines.append("")
    if metrics.empty:
        lines.append("No metric rows.")
    else:
        display = metrics.sort_values(["label", "test_date"]).copy()
        lines.append("| label | test date | train dates | n train | n test | edge rho | side rho | top mean | top-bottom | cvar05 | long share |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in display.to_dict("records"):
            lines.append(
                "| {label} | {test} | {train} | {n_train} | {n_test} | {edge} | {side} | {top} | {tb} | {cvar} | {long_share} |".format(
                    label=row.get("label", ""),
                    test=row.get("test_date", ""),
                    train=row.get("train_dates", ""),
                    n_train=row.get("n_train", ""),
                    n_test=row.get("n_test", ""),
                    edge=format_float(row.get("pred_edge_spearman")),
                    side=format_float(row.get("pred_side_spearman")),
                    top=format_float(row.get("top_mean_bps")),
                    tb=format_float(row.get("top_bottom_bps")),
                    cvar=format_float(row.get("top_cvar05_bps")),
                    long_share=format_float(row.get("long_share")),
                )
            )
    lines.append("")
    lines.append("## Top Feature Importances")
    lines.append("")
    if importances.empty:
        lines.append("No feature importances.")
    else:
        imp = importances.groupby(["label", "feature"], as_index=False)["importance_mean"].mean()
        for label in sorted(imp["label"].unique()):
            lines.append(f"### {label}")
            lines.append("")
            top = imp[imp["label"].eq(label)].sort_values("importance_mean", ascending=False).head(12)
            lines.append("| feature | mean importance |")
            lines.append("|---|---:|")
            for row in top.to_dict("records"):
                lines.append(f"| `{row['feature']}` | {format_float(row['importance_mean'], 6)} |")
            lines.append("")
    lines.append("## Boundary")
    lines.append("")
    lines.append("- Tree outputs are diagnostics for non-linear interaction structure.")
    lines.append("- Runner still must not read labels; Bot still must not read `date/` or derived future diagnostics.")
    lines.append("- A positive release model does not imply executable edge; top-of-book executable labels must be checked separately.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    windows = [int(part) for part in parse_csv_list(args.memory_windows)]
    labels = parse_csv_list(args.labels)
    unknown_labels = [label for label in labels if label not in TREE_LABELS]
    if unknown_labels:
        raise ValueError(f"unknown labels: {unknown_labels}")
    days = list(mfd.date_range(args.from_date, args.to_date))
    if len(days) < 2:
        raise ValueError("tree diagnostic needs at least two dates for OOS folds")
    out_dir = args.out_dir
    if out_dir is None:
        out_dir = DEFAULT_OUT_ROOT / f"{args.symbol.lower()}_{args.from_date}_{args.to_date}_{args.source}_{args.fold_mode}_v0_1"
    out_dir = out_dir if out_dir.is_absolute() else repo_root / out_dir
    report_path = args.report_path if args.report_path.is_absolute() else repo_root / args.report_path
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    data, manifests, feature_names = prepare_dataset(
        repo_root,
        args.symbol,
        args.source,
        days,
        windows,
        args.horizon_sec,
        args.release_sec,
        max_rows_per_day=0,
    )
    folds = build_folds(days, args.fold_mode)
    metric_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    for label_index, label in enumerate(labels):
        label_spec = TREE_LABELS[label]
        for fold_index, (train_days, test_day) in enumerate(folds):
            print(
                f"microstructure_tree_diagnostic label={label} train={','.join(train_days)} test={test_day}",
                file=sys.stderr,
                flush=True,
            )
            metric_row, fold_importances, pred_frame = run_label_fold(
                data,
                feature_names,
                label_spec,
                train_days,
                test_day,
                args,
                salt=1000 * label_index + fold_index,
            )
            metric_rows.append(metric_row)
            importance_rows.extend(fold_importances)
            if not pred_frame.empty:
                prediction_frames.append(pred_frame)

    if prediction_frames:
        predictions = pd.concat(prediction_frames, ignore_index=True)
        for label in labels:
            label_predictions = predictions[predictions["label"].eq(label)]
            if label_predictions.empty:
                continue
            pooled = summarize_prediction(
                pred_long=label_predictions["pred_long"].to_numpy(dtype=float),
                pred_short=label_predictions["pred_short"].to_numpy(dtype=float),
                actual_long=label_predictions["actual_long"].to_numpy(dtype=float),
                actual_short=label_predictions["actual_short"].to_numpy(dtype=float),
                top_q=args.top_quantile,
                bottom_q=args.bottom_quantile,
            )
            row = {
                "label": label,
                "test_date": "ALL_OOS",
                "train_dates": args.fold_mode,
                "n_train": "",
                "status": "research_only_oos_tree_diagnostic",
            }
            row.update(pooled)
            metric_rows.append(row)

    summary = {
        "schema_id": "ccusdt_microstructure_tree_diagnostic_summary_v1",
        "symbol": args.symbol,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "source": args.source,
        "fold_mode": args.fold_mode,
        "horizon_sec": args.horizon_sec,
        "release_sec": args.release_sec,
        "memory_windows": windows,
        "labels": labels,
        "model": {
            "type": "ExtraTreesRegressor_pair_long_short",
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "min_samples_leaf": args.min_samples_leaf,
            "max_features": 0.7,
            "random_state": args.random_state,
        },
        "max_train_rows": args.max_train_rows,
        "max_test_rows": args.max_test_rows,
        "feature_count": len(feature_names),
        "row_count": int(len(data)),
        "metric_rows": len(metric_rows),
        "out_dir": str(out_dir),
        "report_path": str(report_path),
        "elapsed_wall_ms": int((time.perf_counter() - started) * 1000),
        "source_manifests": manifests,
        "outputs": {
            "metrics_csv": str(out_dir / "tree_oos_metrics.csv"),
            "feature_importance_csv": str(out_dir / "tree_feature_importance.csv"),
            "summary_json": str(out_dir / "summary.json"),
            "report_md": str(report_path),
        },
    }
    write_csv(out_dir / "tree_oos_metrics.csv", metric_rows)
    write_csv(out_dir / "tree_feature_importance.csv", importance_rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(report_path, summary, metric_rows, importance_rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
