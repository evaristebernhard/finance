from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from factor_analyzer import calculate_bartlett_sphericity, calculate_kmo
from lightgbm import LGBMRegressor
from sklearn.decomposition import FactorAnalysis as SklearnFactorAnalysis
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit


DATE_DIR = Path("date")
DOCS_DIR = Path("docs")
RUN_TAG = "20260508"

PANEL_CSV = DATE_DIR / f"chog_factor_panel_v2_{RUN_TAG}.csv"
LOADINGS_CSV = DATE_DIR / f"chog_ml_factor_loadings_{RUN_TAG}.csv"
SCORES_CSV = DATE_DIR / f"chog_ml_factor_scores_{RUN_TAG}.csv"
MODEL_TESTS_CSV = DATE_DIR / f"chog_ml_factor_model_tests_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"chog_ml_factor_analysis_{RUN_TAG}.md"

TARGETS = ["fwd_1h", "fwd_3h", "fwd_6h"]
MAX_EFA_FACTORS = 6
MAX_PCA_COMPONENTS = 8
MIN_VALID_FEATURE_SHARE = 0.65
HIGH_CORR_THRESHOLD = 0.985

EXCLUDE_PREFIXES = ("fwd_", "resid_")
EXCLUDE_COLUMNS = {
    "hour_timestamp",
    "price_usd",
    "source_timestamp",
    "source_offset_seconds",
    "confidence",
    "calibration_events",
    "large_p01_threshold_chog",
    "large_p05_threshold_chog",
    "large_p10_threshold_chog",
    "small_threshold_chog",
}


@dataclass(frozen=True)
class FeatureMatrix:
    frame: pd.DataFrame
    feature_cols: list[str]
    dropped_for_corr: list[str]
    medians: pd.Series
    lower: pd.Series
    upper: pd.Series


def raw_num(value: float | int | None, digits: int = 4) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value) * 100:.{digits}f}%"


def markdown_table(rows: list[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(key, "")) for _, key in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def clean_numeric_features(panel: pd.DataFrame) -> FeatureMatrix:
    numeric_cols = [
        col
        for col in panel.select_dtypes(include=[np.number]).columns
        if col not in EXCLUDE_COLUMNS and not col.startswith(EXCLUDE_PREFIXES)
    ]

    usable_cols: list[str] = []
    for col in numeric_cols:
        series = panel[col].replace([np.inf, -np.inf], np.nan)
        if series.notna().mean() < MIN_VALID_FEATURE_SHARE:
            continue
        if series.nunique(dropna=True) < 3:
            continue
        usable_cols.append(col)

    features = panel[usable_cols].replace([np.inf, -np.inf], np.nan).copy()
    medians = features.median(numeric_only=True)
    features = features.fillna(medians)

    lower = features.quantile(0.01)
    upper = features.quantile(0.99)
    features = features.clip(lower=lower, upper=upper, axis=1)

    std = features.std(ddof=0).replace(0, np.nan)
    features = (features - features.mean()) / std
    features = features.dropna(axis=1, how="any")

    dropped_for_corr = drop_high_correlation(features)
    if dropped_for_corr:
        features = features.drop(columns=dropped_for_corr)

    return FeatureMatrix(
        frame=features,
        feature_cols=list(features.columns),
        dropped_for_corr=dropped_for_corr,
        medians=medians,
        lower=lower,
        upper=upper,
    )


def drop_high_correlation(features: pd.DataFrame) -> list[str]:
    corr = features.corr().abs()
    upper_mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    upper = corr.where(upper_mask)
    return [col for col in upper.columns if (upper[col] > HIGH_CORR_THRESHOLD).any()]


def choose_factor_count(features: pd.DataFrame) -> tuple[int, np.ndarray]:
    corr = features.corr().fillna(0.0)
    eigenvalues = np.linalg.eigvalsh(corr.to_numpy())[::-1]
    kaiser = int(np.sum(eigenvalues > 1.0))
    n_factors = max(2, min(MAX_EFA_FACTORS, kaiser))
    return n_factors, eigenvalues


def varimax(loadings: np.ndarray, gamma: float = 1.0, q: int = 50, tol: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    p, k = loadings.shape
    rotation = np.eye(k)
    previous = 0.0
    for _ in range(q):
        rotated = loadings @ rotation
        u, s, vh = np.linalg.svd(
            loadings.T
            @ (
                rotated**3
                - (gamma / p) * rotated @ np.diag(np.diag(rotated.T @ rotated))
            )
        )
        rotation = u @ vh
        current = float(np.sum(s))
        if previous and current < previous * (1.0 + tol):
            break
        previous = current
    return loadings @ rotation, rotation


def fit_factor_analysis(
    features: pd.DataFrame,
) -> tuple[SklearnFactorAnalysis, pd.DataFrame, pd.DataFrame]:
    n_factors, _ = choose_factor_count(features)
    analyzer = SklearnFactorAnalysis(n_components=n_factors, random_state=42)
    analyzer.fit(features)

    factor_cols = [f"efa_factor_{i + 1}" for i in range(n_factors)]
    rotated_loadings, rotation = varimax(analyzer.components_.T)
    loadings = pd.DataFrame(rotated_loadings, index=features.columns, columns=factor_cols)
    communalities = np.sum(rotated_loadings**2, axis=1)
    loadings["communality"] = communalities
    loadings["uniqueness"] = np.maximum(0.0, 1.0 - communalities)
    loading_values = loadings[factor_cols]
    loadings["primary_factor"] = loading_values.abs().idxmax(axis=1)
    primary_col_idx = loading_values.columns.get_indexer(loadings["primary_factor"])
    loadings["primary_loading"] = loading_values.to_numpy()[
        np.arange(len(loading_values)), primary_col_idx
    ]
    loadings = (
        loadings.reset_index(names="feature")
        .assign(abs_primary_loading=lambda frame: frame["primary_loading"].abs())
        .sort_values(["primary_factor", "abs_primary_loading"], ascending=[True, False])
        .drop(columns=["abs_primary_loading"])
        .reset_index(drop=True)
    )

    scores = pd.DataFrame(analyzer.transform(features) @ rotation, columns=factor_cols)
    return analyzer, loadings, scores


def fit_pca(features: pd.DataFrame) -> tuple[PCA, pd.DataFrame]:
    n_components = min(MAX_PCA_COMPONENTS, features.shape[1], features.shape[0] - 1)
    pca = PCA(n_components=n_components, random_state=42)
    scores = pd.DataFrame(
        pca.fit_transform(features),
        columns=[f"pca_{i + 1}" for i in range(n_components)],
    )
    return pca, scores


def score_prediction(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float | int]:
    frame = pd.DataFrame({"y": y_true, "pred": y_pred}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(frame) < 40 or frame["pred"].nunique() < 3:
        return {
            "n": int(len(frame)),
            "pearson": np.nan,
            "spearman": np.nan,
            "top_minus_bottom": np.nan,
            "top_mean": np.nan,
            "bottom_mean": np.nan,
        }
    buckets = pd.qcut(frame["pred"], 3, labels=False, duplicates="drop")
    frame = frame.assign(bucket=buckets)
    if frame["bucket"].nunique(dropna=True) < 2:
        top_minus_bottom = np.nan
        top_mean = np.nan
        bottom_mean = np.nan
    else:
        bottom = frame.loc[frame["bucket"].eq(frame["bucket"].min()), "y"].mean()
        top = frame.loc[frame["bucket"].eq(frame["bucket"].max()), "y"].mean()
        top_minus_bottom = top - bottom
        top_mean = top
        bottom_mean = bottom
    return {
        "n": int(len(frame)),
        "pearson": float(frame["pred"].corr(frame["y"], method="pearson")),
        "spearman": float(frame["pred"].corr(frame["y"], method="spearman")),
        "top_minus_bottom": float(top_minus_bottom),
        "top_mean": float(top_mean),
        "bottom_mean": float(bottom_mean),
    }


def evaluate_score_columns(panel: pd.DataFrame, scores: pd.DataFrame, label: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for factor in scores.columns:
        for target in TARGETS:
            row = score_prediction(panel[target], scores[factor])
            rows.append(
                {
                    "test_type": "unsupervised_score_ic",
                    "model": label,
                    "feature_set": factor,
                    "target": target,
                    **row,
                }
            )
    return pd.DataFrame(rows)


def oos_predictions(
    x: pd.DataFrame,
    y: pd.Series,
    make_model: Callable[[], object],
    splits: int = 5,
) -> pd.Series:
    valid = y.replace([np.inf, -np.inf], np.nan).notna()
    x_valid = x.loc[valid].reset_index(drop=True)
    y_valid = y.loc[valid].reset_index(drop=True)
    preds = pd.Series(np.nan, index=y_valid.index, dtype=float)

    split_count = min(splits, max(2, len(y_valid) // 80))
    tscv = TimeSeriesSplit(n_splits=split_count)
    for train_idx, test_idx in tscv.split(x_valid):
        if len(train_idx) < 60:
            continue
        model = make_model()
        model.fit(x_valid.iloc[train_idx], y_valid.iloc[train_idx])
        preds.iloc[test_idx] = model.predict(x_valid.iloc[test_idx])

    out = pd.Series(np.nan, index=y.index, dtype=float)
    out.loc[y.index[valid]] = preds.to_numpy()
    return out


def evaluate_models(panel: pd.DataFrame, feature_sets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    model_factories: dict[str, Callable[[], object]] = {
        "ridge": lambda: Ridge(alpha=10.0),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=300,
            max_depth=3,
            min_samples_leaf=12,
            random_state=42,
            n_jobs=-1,
        ),
        "lightgbm": lambda: LGBMRegressor(
            n_estimators=200,
            learning_rate=0.03,
            max_depth=3,
            num_leaves=7,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=-1,
        ),
    }

    rows: list[dict[str, object]] = []
    for feature_set, x in feature_sets.items():
        for target in TARGETS:
            for model_name, factory in model_factories.items():
                pred = oos_predictions(x, panel[target], factory)
                row = score_prediction(panel[target], pred)
                rows.append(
                    {
                        "test_type": "time_series_oos_prediction",
                        "model": model_name,
                        "feature_set": feature_set,
                        "target": target,
                        **row,
                    }
                )
    return pd.DataFrame(rows)


def top_loading_rows(loadings: pd.DataFrame, top_n: int = 6) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    factor_cols = [col for col in loadings.columns if col.startswith("efa_factor_")]
    for factor in factor_cols:
        top = loadings.reindex(loadings[factor].abs().sort_values(ascending=False).index).head(top_n)
        features = ", ".join(
            f"{row.feature} ({raw_num(getattr(row, factor), 2)})"
            for row in top.itertuples(index=False)
        )
        rows.append({"factor": factor, "top_loadings": features})
    return rows


def model_rows(model_tests: pd.DataFrame, rows: int = 12) -> list[dict[str, object]]:
    frame = (
        model_tests[model_tests["n"].ge(40)]
        .assign(abs_spearman=lambda df: df["spearman"].abs())
        .sort_values(["abs_spearman", "top_minus_bottom"], ascending=[False, False])
        .head(rows)
    )
    return [
        {
            "type": row["test_type"],
            "model": row["model"],
            "features": row["feature_set"],
            "target": row["target"],
            "n": int(row["n"]),
            "spearman": raw_num(row["spearman"]),
            "top_bottom": pct(row["top_minus_bottom"]),
        }
        for _, row in frame.iterrows()
    ]


def build_report(
    panel: pd.DataFrame,
    matrix: FeatureMatrix,
    loadings: pd.DataFrame,
    efa_scores: pd.DataFrame,
    pca: PCA,
    eigenvalues: np.ndarray,
    kmo_value: float | None,
    bartlett_p: float | None,
    model_tests: pd.DataFrame,
) -> str:
    pca_rows = [
        {
            "component": f"pca_{i + 1}",
            "explained": pct(value),
            "cumulative": pct(np.sum(pca.explained_variance_ratio_[: i + 1])),
        }
        for i, value in enumerate(pca.explained_variance_ratio_[:6])
    ]
    eigen_rows = [
        {"rank": i + 1, "eigenvalue": raw_num(value)}
        for i, value in enumerate(eigenvalues[:8])
    ]
    target_rows = [
        {
            "target": target,
            "valid_rows": int(panel[target].notna().sum()),
            "mean": pct(panel[target].mean()),
            "std": pct(panel[target].std()),
        }
        for target in TARGETS
    ]

    return f"""# CHOG 机器学习因子分析

状态: 2026-05-09。基于 `date/chog_factor_panel_v2_20260508.csv` 做第一版机器学习/因子分解研究，新增依赖见 `requirements-ml.txt`。

这份报告仍是研究稿，不是交易规则。样本只有 `{len(panel):,}` 个小时，时间跨度短，所有结论都应等继续补齐 30 天以上数据后复测。

复现命令:

```bash
python scripts/ml_chog_factor_analysis.py
```

输出:

```text
{LOADINGS_CSV.as_posix()}
{SCORES_CSV.as_posix()}
{MODEL_TESTS_CSV.as_posix()}
{REPORT_MD.as_posix()}
```

## 1. 输入和清洗

原始面板行数 `{len(panel):,}`，数值列经缺失率、常数列、极端相关过滤后保留 `{len(matrix.feature_cols)}` 个候选因子；高相关剔除 `{len(matrix.dropped_for_corr)}` 个。每列做 1%/99% winsorize、median fill、z-score。

目标收益:

{markdown_table(target_rows, [("Target", "target"), ("Valid Rows", "valid_rows"), ("Mean", "mean"), ("Std", "std")])}

## 2. EFA 适配度

KMO overall: `{raw_num(kmo_value) if kmo_value is not None else "NA"}`。

Bartlett p-value: `{raw_num(bartlett_p) if bartlett_p is not None else "NA"}`。

相关矩阵前 8 个特征值:

{markdown_table(eigen_rows, [("Rank", "rank"), ("Eigenvalue", "eigenvalue")])}

本轮按 Kaiser rule 并上限裁剪，提取 `{efa_scores.shape[1]}` 个 varimax 旋转因子。KMO 若偏低，说明这些链上因子不是典型心理量表式 latent factor，更适合当“流量/波动/拥堵/池子结构”几个可解释簇来用。

## 3. EFA 因子载荷

{markdown_table(top_loading_rows(loadings), [("Factor", "factor"), ("Top Loadings", "top_loadings")])}

读法:

1. 同一 factor 里绝对载荷高的变量可以看作一个市场状态簇。
2. 正负号本身不重要，重要的是同簇变量方向是否稳定；换样本后 factor 符号可能整体翻转。
3. 高 communality 的变量更适合被低维因子解释，低 communality 的变量更适合作为单独特征保留。

## 4. PCA 参考

{markdown_table(pca_rows, [("Component", "component"), ("Explained", "explained"), ("Cumulative", "cumulative")])}

PCA 解释方差主要说明“链上变量之间有多少冗余”，不直接代表预测力。若前几个 PCA 已解释大部分方差，后续建模可以先压缩再做稳健性测试。

## 5. IC / 机器学习检验

评分包含两类:

1. `unsupervised_score_ic`: 直接看 EFA/PCA score 与未来收益的相关和三分位差。
2. `time_series_oos_prediction`: 用 expanding time split 做 out-of-sample 预测，模型包括 Ridge、RandomForest、LightGBM。

当前绝对 Spearman 排名前列:

{markdown_table(model_rows(model_tests), [("Type", "type"), ("Model", "model"), ("Features", "features"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Top-Bottom", "top_bottom")])}

## 6. 当前结论

1. 这组链上变量确实有明显共线性，低维压缩是必要的；否则很多“新因子”只是成交量、活跃度和大单流量的重复表达。
2. EFA/PCA 更适合先做因子族归纳，再回到可解释变量设计，而不是直接把 factor score 当交易信号。
3. out-of-sample ML 检验如果强度明显低于 full-sample IC，说明当前样本容易被少数高成交小时支配。
4. 下一步最好继续补历史窗口，然后把训练/验证按日期切开，确认大单、主池、gas regime 是否跨窗口稳定。

## 7. 后续研究建议

1. 把 `efa_factor_*` 分数并回 hourly panel，作为 regime/filter 候选。
2. 对 top loading 变量做人工重构，形成更少、更稳的手写因子，比如 `activity_regime`、`large_flow_pressure`、`main_pool_absorption`。
3. 至少补到 30 天以上后再重跑本脚本，并比较 factor loading 是否换组。
4. LightGBM/RandomForest 只看特征重要性和非线性提示，不要在当前短样本上直接调参追高 IC。
"""


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    panel = pd.read_csv(PANEL_CSV)
    matrix = clean_numeric_features(panel)
    n_factors, eigenvalues = choose_factor_count(matrix.frame)

    kmo_value: float | None = None
    bartlett_p: float | None = None
    try:
        _, kmo_model = calculate_kmo(matrix.frame)
        _, bartlett_p_value = calculate_bartlett_sphericity(matrix.frame)
        kmo_value = float(kmo_model)
        bartlett_p = float(bartlett_p_value)
    except Exception:
        pass

    _, loadings, efa_scores = fit_factor_analysis(matrix.frame)
    pca, pca_scores = fit_pca(matrix.frame)

    score_frame = pd.concat(
        [
            panel[["hour_utc", *TARGETS]].reset_index(drop=True),
            efa_scores.reset_index(drop=True),
            pca_scores.reset_index(drop=True),
        ],
        axis=1,
    )

    feature_sets = {
        "efa_scores": efa_scores,
        "pca_scores": pca_scores,
        "raw_standardized_factors": matrix.frame,
    }
    model_tests = pd.concat(
        [
            evaluate_score_columns(panel, efa_scores, "efa"),
            evaluate_score_columns(panel, pca_scores, "pca"),
            evaluate_models(panel, feature_sets),
        ],
        ignore_index=True,
    )

    loadings.to_csv(LOADINGS_CSV, index=False)
    score_frame.to_csv(SCORES_CSV, index=False)
    model_tests.to_csv(MODEL_TESTS_CSV, index=False)
    REPORT_MD.write_text(
        build_report(
            panel=panel,
            matrix=matrix,
            loadings=loadings,
            efa_scores=efa_scores,
            pca=pca,
            eigenvalues=eigenvalues,
            kmo_value=kmo_value,
            bartlett_p=bartlett_p,
            model_tests=model_tests,
        ),
        encoding="utf-8",
    )

    print(f"features={len(matrix.feature_cols)} efa_factors={n_factors}")
    print(f"wrote {LOADINGS_CSV} rows={len(loadings)}")
    print(f"wrote {SCORES_CSV} rows={len(score_frame)}")
    print(f"wrote {MODEL_TESTS_CSV} rows={len(model_tests)}")
    print(f"wrote {REPORT_MD}")


if __name__ == "__main__":
    main()
