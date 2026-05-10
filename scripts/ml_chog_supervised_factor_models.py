from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from ml_chog_factor_analysis import (
    PANEL_CSV,
    RUN_TAG,
    TARGETS,
    clean_numeric_features,
    markdown_table,
    pct,
    raw_num,
    score_prediction,
)
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor


DATE_DIR = Path("date")
DOCS_DIR = Path("docs")

PREDICTIONS_CSV = DATE_DIR / f"chog_ml_supervised_oos_predictions_{RUN_TAG}.csv"
IMPORTANCE_CSV = DATE_DIR / f"chog_ml_supervised_feature_importance_{RUN_TAG}.csv"
SUMMARY_CSV = DATE_DIR / f"chog_ml_supervised_model_summary_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"chog_ml_supervised_factor_research_{RUN_TAG}.md"

TOP_FEATURES_PER_FOLD = 30
N_SPLITS = 5


def model_factories() -> dict[str, Callable[[], object]]:
    return {
        "ridge": lambda: Ridge(alpha=10.0),
        "elastic_net": lambda: ElasticNet(alpha=0.002, l1_ratio=0.20, max_iter=50_000),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=350,
            max_depth=3,
            min_samples_leaf=12,
            random_state=42,
            n_jobs=-1,
        ),
        "lightgbm": lambda: LGBMRegressor(
            n_estimators=250,
            learning_rate=0.025,
            max_depth=3,
            num_leaves=7,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=-1,
            importance_type="gain",
        ),
        "xgboost": lambda: XGBRegressor(
            n_estimators=220,
            learning_rate=0.025,
            max_depth=2,
            min_child_weight=8,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=10.0,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=-1,
            verbosity=0,
            importance_type="gain",
        ),
    }


def rank_features(x_train: pd.DataFrame, y_train: pd.Series, top_k: int) -> list[str]:
    rows: list[tuple[str, float]] = []
    for col in x_train.columns:
        frame = pd.DataFrame({"x": x_train[col], "y": y_train}).replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        if len(frame) < 40 or frame["x"].nunique() < 3:
            continue
        score = frame["x"].corr(frame["y"], method="spearman")
        if pd.notna(score):
            rows.append((col, abs(float(score))))
    rows.sort(key=lambda item: item[1], reverse=True)
    return [col for col, _ in rows[:top_k]]


def extract_importance(model: object, model_name: str, features: list[str]) -> pd.DataFrame:
    signed = np.zeros(len(features), dtype=float)
    raw = np.zeros(len(features), dtype=float)

    if hasattr(model, "coef_"):
        signed = np.asarray(getattr(model, "coef_"), dtype=float).reshape(-1)
        raw = np.abs(signed)
    elif hasattr(model, "feature_importances_"):
        raw = np.asarray(getattr(model, "feature_importances_"), dtype=float).reshape(-1)
        signed = raw.copy()

    if len(raw) != len(features):
        raw = np.zeros(len(features), dtype=float)
        signed = raw.copy()
    denom = float(np.nansum(np.abs(raw)))
    normalized = raw / denom if denom > 0 else raw
    return pd.DataFrame(
        {
            "model": model_name,
            "feature": features,
            "raw_importance": raw,
            "signed_importance": signed,
            "normalized_importance": normalized,
        }
    )


def evaluate_supervised_models(
    panel: pd.DataFrame,
    features: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prediction_frames: list[pd.DataFrame] = []
    importance_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []

    factories = model_factories()
    for target in TARGETS:
        valid_mask = panel[target].replace([np.inf, -np.inf], np.nan).notna()
        x_valid = features.loc[valid_mask].reset_index(drop=True)
        y_valid = panel.loc[valid_mask, target].reset_index(drop=True)
        hour_valid = panel.loc[valid_mask, "hour_utc"].reset_index(drop=True)

        split_count = min(N_SPLITS, max(2, len(y_valid) // 80))
        splitter = TimeSeriesSplit(n_splits=split_count)

        preds_by_model = {
            model_name: pd.Series(np.nan, index=y_valid.index, dtype=float)
            for model_name in factories
        }

        for fold, (train_idx, test_idx) in enumerate(splitter.split(x_valid), start=1):
            x_train = x_valid.iloc[train_idx]
            y_train = y_valid.iloc[train_idx]
            selected = rank_features(x_train, y_train, TOP_FEATURES_PER_FOLD)
            if len(selected) < 5:
                continue

            for model_name, factory in factories.items():
                model = factory()
                model.fit(x_train[selected], y_train)
                preds_by_model[model_name].iloc[test_idx] = model.predict(
                    x_valid.iloc[test_idx][selected]
                )

                importance = extract_importance(model, model_name, selected)
                importance["target"] = target
                importance["fold"] = fold
                importance["train_start_hour"] = hour_valid.iloc[train_idx[0]]
                importance["train_end_hour"] = hour_valid.iloc[train_idx[-1]]
                importance["test_start_hour"] = hour_valid.iloc[test_idx[0]]
                importance["test_end_hour"] = hour_valid.iloc[test_idx[-1]]
                importance_frames.append(importance)

        for model_name, preds in preds_by_model.items():
            prediction_frames.append(
                pd.DataFrame(
                    {
                        "hour_utc": hour_valid,
                        "target": target,
                        "model": model_name,
                        "actual_return": y_valid,
                        "predicted_return": preds,
                    }
                )
            )
            score = score_prediction(y_valid, preds)
            summary_rows.append(
                {
                    "target": target,
                    "model": model_name,
                    "feature_selection": f"train_fold_top_{TOP_FEATURES_PER_FOLD}_spearman",
                    **score,
                    "abs_spearman": np.nan
                    if pd.isna(score["spearman"])
                    else abs(float(score["spearman"])),
                }
            )

    predictions = pd.concat(prediction_frames, ignore_index=True)
    importance = pd.concat(importance_frames, ignore_index=True)
    summary = pd.DataFrame(summary_rows).sort_values(
        ["abs_spearman", "top_minus_bottom"], ascending=[False, False]
    )
    return predictions, importance, summary


def aggregate_importance(importance: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        importance.groupby(["target", "model", "feature"], dropna=False)
        .agg(
            folds_seen=("fold", "nunique"),
            mean_normalized_importance=("normalized_importance", "mean"),
            max_normalized_importance=("normalized_importance", "max"),
            mean_signed_importance=("signed_importance", "mean"),
        )
        .reset_index()
    )
    grouped["stability_score"] = grouped["folds_seen"] * grouped["mean_normalized_importance"]
    return grouped.sort_values(
        ["target", "model", "stability_score"], ascending=[True, True, False]
    )


def summary_table(summary: pd.DataFrame, rows: int = 12) -> list[dict[str, object]]:
    frame = summary.head(rows)
    return [
        {
            "target": row["target"],
            "model": row["model"],
            "n": int(row["n"]),
            "spearman": raw_num(row["spearman"]),
            "pearson": raw_num(row["pearson"]),
            "top_bottom": pct(row["top_minus_bottom"]),
        }
        for _, row in frame.iterrows()
    ]


def importance_table(importance_summary: pd.DataFrame, rows: int = 18) -> list[dict[str, object]]:
    frame = (
        importance_summary.groupby("feature", dropna=False)
        .agg(
            model_targets=("model", "count"),
            mean_score=("stability_score", "mean"),
            max_score=("stability_score", "max"),
        )
        .reset_index()
        .sort_values(["max_score", "mean_score"], ascending=[False, False])
        .head(rows)
    )
    return [
        {
            "feature": row["feature"],
            "model_targets": int(row["model_targets"]),
            "mean_score": raw_num(row["mean_score"]),
            "max_score": raw_num(row["max_score"]),
        }
        for _, row in frame.iterrows()
    ]


def target_importance_table(
    importance_summary: pd.DataFrame,
    target: str,
    rows: int = 8,
) -> list[dict[str, object]]:
    frame = (
        importance_summary[importance_summary["target"].eq(target)]
        .groupby("feature", dropna=False)
        .agg(
            models=("model", "nunique"),
            mean_score=("stability_score", "mean"),
            max_score=("stability_score", "max"),
        )
        .reset_index()
        .sort_values(["max_score", "mean_score"], ascending=[False, False])
        .head(rows)
    )
    return [
        {
            "feature": row["feature"],
            "models": int(row["models"]),
            "mean_score": raw_num(row["mean_score"]),
            "max_score": raw_num(row["max_score"]),
        }
        for _, row in frame.iterrows()
    ]


def build_report(
    panel: pd.DataFrame,
    feature_count: int,
    predictions: pd.DataFrame,
    importance_summary: pd.DataFrame,
    summary: pd.DataFrame,
) -> str:
    prediction_rows = int(predictions["predicted_return"].notna().sum())
    target_sections = []
    for target in TARGETS:
        target_sections.append(
            f"""### {target}

{markdown_table(target_importance_table(importance_summary, target), [("Feature", "feature"), ("Models", "models"), ("Mean Score", "mean_score"), ("Max Score", "max_score")])}
"""
        )

    return f"""# CHOG 监督学习因子研究

状态: 2026-05-09。基于 30 天 memecoin 数据重建后的 `date/chog_factor_panel_v2_{RUN_TAG}.csv`，用监督学习补充因子分析。

这份报告只用于研究候选因子稳定性，不是交易规则。样本仍只有 `{len(panel):,}` 个小时，且价格序列从 2026-04-17 才开始，所以早期链上数据主要影响校准和市场结构。

复现命令:

```bash
python scripts/ml_chog_supervised_factor_models.py
```

输出:

```text
{PREDICTIONS_CSV.as_posix()}
{IMPORTANCE_CSV.as_posix()}
{SUMMARY_CSV.as_posix()}
{REPORT_MD.as_posix()}
```

## 1. 方法

- 输入特征: 清洗后的 `{feature_count}` 个数值因子。
- 目标: `fwd_1h`、`fwd_3h`、`fwd_6h`。
- 切分: expanding `TimeSeriesSplit`，每个 fold 只用训练段选择 top `{TOP_FEATURES_PER_FOLD}` 个 Spearman 因子。
- 模型: Ridge、ElasticNet、RandomForest、LightGBM、XGBoost。
- 评分: OOS Spearman、Pearson、预测值三分位 top-bottom future return。

生成 OOS 预测点数量: `{prediction_rows:,}`。

## 2. OOS 模型结果

{markdown_table(summary_table(summary), [("Target", "target"), ("Model", "model"), ("N", "n"), ("Spearman", "spearman"), ("Pearson", "pearson"), ("Top-Bottom", "top_bottom")])}

## 3. 跨模型稳定因子

下面按 fold 内特征重要性做归一化，再统计跨模型/target 的稳定分数。它不等于可交易 alpha，但能提示哪些原始变量值得手工重构。

{markdown_table(importance_table(importance_summary), [("Feature", "feature"), ("Model-Targets", "model_targets"), ("Mean Score", "mean_score"), ("Max Score", "max_score")])}

## 4. 分目标重要因子

{''.join(target_sections)}

## 5. 当前读法

1. 监督学习没有给出强 OOS alpha；最高 Spearman 仍是弱信号级别，应继续当研究线索。
2. 能跨模型出现的变量比单次 IC 排名更值得看，尤其是和大单占比、主池压力、短期动量/反转有关的变量。
3. Ridge/ElasticNet 适合看线性方向，树模型适合发现非线性切片；两者共同出现的特征优先进入下一版手写因子。
4. 后续应该把 top 特征重构成少数稳定因子，再用按日期切开的 train/validation 做确认。
"""


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    panel = pd.read_csv(PANEL_CSV)
    matrix = clean_numeric_features(panel)
    predictions, raw_importance, summary = evaluate_supervised_models(panel, matrix.frame)
    importance_summary = aggregate_importance(raw_importance)

    predictions.to_csv(PREDICTIONS_CSV, index=False)
    importance_summary.to_csv(IMPORTANCE_CSV, index=False)
    summary.to_csv(SUMMARY_CSV, index=False)
    REPORT_MD.write_text(
        build_report(
            panel=panel,
            feature_count=len(matrix.feature_cols),
            predictions=predictions,
            importance_summary=importance_summary,
            summary=summary,
        ),
        encoding="utf-8",
    )

    print(f"features={len(matrix.feature_cols)}")
    print(f"wrote {PREDICTIONS_CSV} rows={len(predictions)}")
    print(f"wrote {IMPORTANCE_CSV} rows={len(importance_summary)}")
    print(f"wrote {SUMMARY_CSV} rows={len(summary)}")
    print(f"wrote {REPORT_MD}")


if __name__ == "__main__":
    main()
