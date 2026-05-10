from __future__ import annotations

from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import chog_cost_aware_event_factor_research as base


DATE_DIR = Path("date")
DOCS_DIR = Path("docs")
RUN_TAG = "20260509"

LABELS_CSV = DATE_DIR / f"chog_event_cost_labels_{RUN_TAG}.csv"
FACTOR_SCORES_CSV = DATE_DIR / f"chog_first_principles_factor_scores_{RUN_TAG}.csv"

PHENOMENA_CSV = DATE_DIR / f"chog_event_factor_phenomena_{RUN_TAG}.csv"
PATH_PROFILES_CSV = DATE_DIR / f"chog_event_factor_path_profiles_{RUN_TAG}.csv"
DAILY_CONCENTRATION_CSV = DATE_DIR / f"chog_event_factor_daily_concentration_{RUN_TAG}.csv"
UNTRADABLE_REASONS_CSV = DATE_DIR / f"chog_event_factor_untradable_reasons_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"chog_event_factor_phenomena_{RUN_TAG}.md"

HORIZONS = ["5m", "15m", "1h", "3h", "6h"]


def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value) * 100:.{digits}f}%"


def raw_num(value: float | int | None, digits: int = 4) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def num(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    value = float(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}{value / 1_000_000:.{digits}f}M"
    if value >= 1_000:
        return f"{sign}{value / 1_000:.{digits}f}k"
    return f"{sign}{value:.{digits}f}"


def markdown_table(rows: list[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(key, "")) for _, key in columns)
        + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def ensure_cost_outputs() -> None:
    missing = [path for path in [LABELS_CSV, FACTOR_SCORES_CSV] if not path.exists()]
    if missing:
        base.main()


def load_features() -> tuple[pd.DataFrame, base.MainPool]:
    raw = base.read_parquet_parts(base.EVENT_FEATURES)
    prepared, main_pool = base.prepare_events(raw)
    features = base.build_feature_frame(prepared)
    return features, main_pool


def add_group_flags(features: pd.DataFrame) -> pd.DataFrame:
    frame = features.copy()
    main = frame["is_main_pool"].fillna(False)
    thresholds: dict[str, float] = {}
    for col in [
        "log_main_quote_volume_15m",
        "all_event_density_per_min_15m",
        "small_trade_count_share_15m",
        "gas_regime_percentile_past",
        "non_main_volume_share_15m",
    ]:
        values = frame.loc[main, col].replace([np.inf, -np.inf], np.nan).dropna()
        thresholds[col] = float(values.quantile(0.90)) if len(values) else np.nan

    frame["group_all_tradable"] = 1.0
    frame["group_current_buy"] = frame["current_is_buy"].astype(float)
    frame["group_current_sell"] = frame["current_is_sell"].astype(float)
    frame["group_large_buy_p90"] = frame["current_large_buy_p90"].astype(float)
    frame["group_large_sell_p90"] = frame["current_large_sell_p90"].astype(float)
    frame["group_large_trade_p90"] = frame["current_is_large_trade_p90"].astype(float)
    frame["group_high_prior_main_volume_p90"] = frame["log_main_quote_volume_15m"].ge(
        thresholds["log_main_quote_volume_15m"]
    ).astype(float)
    frame["group_high_event_density_p90"] = frame["all_event_density_per_min_15m"].ge(
        thresholds["all_event_density_per_min_15m"]
    ).astype(float)
    frame["group_high_small_noise_p90"] = frame["small_trade_count_share_15m"].ge(
        thresholds["small_trade_count_share_15m"]
    ).astype(float)
    frame["group_high_gas_regime_p90"] = frame["gas_regime_percentile_past"].ge(
        thresholds["gas_regime_percentile_past"]
    ).astype(float)
    frame["group_high_non_main_share_p90"] = frame["non_main_volume_share_15m"].ge(
        thresholds["non_main_volume_share_15m"]
    ).astype(float)
    frame["group_low_activity"] = frame["low_activity_flag"].astype(float)
    frame["signal_date"] = frame["block_dt"].dt.strftime("%Y-%m-%d")
    return frame


def group_specs() -> list[tuple[str, str, str]]:
    return [
        ("all_tradable", "baseline", "all tradable main-pool signal events"),
        ("current_buy", "event_side", "current main-pool buy"),
        ("current_sell", "event_side", "current main-pool sell"),
        ("large_buy_p90", "liquidity_impact", "current top-decile buy"),
        ("large_sell_p90", "liquidity_impact", "current top-decile sell"),
        ("large_trade_p90", "liquidity_impact", "current top-decile trade"),
        ("high_prior_main_volume_p90", "liquidity_state", "top decile prior 15m main quote volume"),
        ("high_event_density_p90", "attention_crowding", "top decile prior 15m event density"),
        ("high_small_noise_p90", "noise_filter", "top decile prior 15m small-trade share"),
        ("high_gas_regime_p90", "attention_crowding", "top decile prior gas percentile"),
        ("high_non_main_share_p90", "main_pool_absorption", "top decile prior non-main volume share"),
        ("low_activity", "untradable_filter", "low prior activity or volume flag"),
    ]


def prepare_joined(labels: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [
        "event_id",
        "signal_date",
        "chog_amount",
        "quote_amount",
        "trade_size_percentile_past",
        "log_main_quote_volume_15m",
        "all_event_density_per_min_15m",
        "small_trade_count_share_15m",
        "gas_regime_percentile_past",
        "non_main_volume_share_15m",
        "low_activity_flag",
        *[f"group_{name}" for name, _, _ in group_specs()],
    ]
    joined = labels.merge(features[feature_cols], on="event_id", how="left")
    joined["signal_ts"] = pd.to_datetime(joined["signal_time"], utc=True, errors="coerce")
    joined["entry_ts"] = pd.to_datetime(joined["entry_time"], utc=True, errors="coerce")
    joined["exit_ts"] = pd.to_datetime(joined["exit_time"], utc=True, errors="coerce")
    joined["entry_delay_seconds"] = (
        joined["entry_ts"] - joined["signal_ts"]
    ).dt.total_seconds()
    joined["actual_exit_seconds"] = (
        joined["exit_ts"] - joined["signal_ts"]
    ).dt.total_seconds()
    return joined


def describe_subset(subset: pd.DataFrame, group: str, family: str, description: str) -> dict[str, object]:
    return {
        "group": group,
        "group_family": family,
        "description": description,
        "horizon": subset["horizon"].iloc[0] if len(subset) else "",
        "n_labels": int(len(subset)),
        "n_events": int(subset["event_id"].nunique()),
        "mean_quote_amount": float(subset["reference_quote_amount"].mean()) if len(subset) else np.nan,
        "median_quote_amount": float(subset["reference_quote_amount"].median()) if len(subset) else np.nan,
        "mean_gross_return": float(subset["gross_return"].mean()) if len(subset) else np.nan,
        "median_gross_return": float(subset["gross_return"].median()) if len(subset) else np.nan,
        "p25_gross_return": float(subset["gross_return"].quantile(0.25)) if len(subset) else np.nan,
        "p75_gross_return": float(subset["gross_return"].quantile(0.75)) if len(subset) else np.nan,
        "gross_positive_rate": float(subset["gross_return"].gt(0).mean()) if len(subset) else np.nan,
        "mean_net_0bps": float(subset["net_return_slip_0bps"].mean()) if len(subset) else np.nan,
        "mean_net_100bps": float(subset["net_return_slip_100bps"].mean()) if len(subset) else np.nan,
        "net_0bps_positive_rate": float(subset["net_return_slip_0bps"].gt(0).mean()) if len(subset) else np.nan,
        "net_100bps_positive_rate": float(subset["net_return_slip_100bps"].gt(0).mean()) if len(subset) else np.nan,
        "net_0bps_gt_2pct_rate": float(subset["net_return_slip_0bps"].gt(0.02).mean()) if len(subset) else np.nan,
        "gas_cost_return_median": float(subset["gas_cost_return"].median()) if len(subset) else np.nan,
        "cost_drag_0bps": float((subset["gross_return"] - subset["net_return_slip_0bps"]).mean())
        if len(subset)
        else np.nan,
        "cost_drag_100bps": float((subset["gross_return"] - subset["net_return_slip_100bps"]).mean())
        if len(subset)
        else np.nan,
        "entry_delay_seconds_median": float(subset["entry_delay_seconds"].median()) if len(subset) else np.nan,
        "actual_exit_seconds_median": float(subset["actual_exit_seconds"].median()) if len(subset) else np.nan,
    }


def build_phenomena(joined: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    valid = joined["label_valid"].fillna(False)
    tradable = joined["is_tradable_sample"].fillna(False)
    for group, family, description in group_specs():
        group_mask = joined[f"group_{group}"].fillna(0).gt(0)
        for horizon in HORIZONS:
            scope = valid & tradable & joined["horizon"].eq(horizon) & group_mask
            subset = joined[scope].copy()
            if len(subset) < 40:
                continue
            rows.append(describe_subset(subset, group, family, description))
    return pd.DataFrame(rows)


def path_shape(gross_values: list[float]) -> str:
    if any(pd.isna(value) for value in gross_values):
        return "incomplete"
    gross_5m, gross_15m, gross_1h, gross_3h, gross_6h = gross_values
    if gross_5m < 0 and gross_6h > 0:
        return "short_reversal_late_continuation"
    if gross_6h > gross_3h > gross_1h and gross_6h > 0:
        return "delayed_continuation"
    if max(gross_values) <= 0:
        return "negative_decay"
    if gross_5m > 0 and gross_6h < gross_5m:
        return "early_pop_fades"
    return "mixed"


def build_path_profiles(phenomena: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, group_frame in phenomena.groupby("group", dropna=False):
        row: dict[str, object] = {
            "group": group,
            "group_family": group_frame["group_family"].iloc[0],
            "description": group_frame["description"].iloc[0],
        }
        gross_values: list[float] = []
        for horizon in HORIZONS:
            item = group_frame[group_frame["horizon"].eq(horizon)]
            if item.empty:
                gross = np.nan
                net0 = np.nan
                net100 = np.nan
                n_events = 0
            else:
                gross = float(item["mean_gross_return"].iloc[0])
                net0 = float(item["mean_net_0bps"].iloc[0])
                net100 = float(item["mean_net_100bps"].iloc[0])
                n_events = int(item["n_events"].iloc[0])
            row[f"gross_{horizon}"] = gross
            row[f"net0_{horizon}"] = net0
            row[f"net100_{horizon}"] = net100
            row[f"n_events_{horizon}"] = n_events
            gross_values.append(gross)
        row["gross_6h_minus_15m"] = row["gross_6h"] - row["gross_15m"]
        row["net0_6h_minus_15m"] = row["net0_6h"] - row["net0_15m"]
        row["path_shape"] = path_shape(gross_values)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["gross_6h", "gross_6h_minus_15m"], ascending=[False, False]
    )


def build_daily_concentration(joined: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    valid = joined["label_valid"].fillna(False)
    tradable = joined["is_tradable_sample"].fillna(False)
    for group in [
        "large_buy_p90",
        "large_trade_p90",
        "high_prior_main_volume_p90",
        "high_event_density_p90",
        "high_small_noise_p90",
    ]:
        mask = (
            valid
            & tradable
            & joined["horizon"].eq("6h")
            & joined[f"group_{group}"].fillna(0).gt(0)
        )
        subset = joined[mask].copy()
        if subset.empty:
            continue
        total_events = subset["event_id"].nunique()
        daily = (
            subset.groupby("signal_date", dropna=False)
            .agg(
                n_labels=("event_id", "size"),
                n_events=("event_id", "nunique"),
                mean_quote_amount=("reference_quote_amount", "mean"),
                gross_6h_mean=("gross_return", "mean"),
                net0_6h_mean=("net_return_slip_0bps", "mean"),
                net100_6h_mean=("net_return_slip_100bps", "mean"),
                net0_positive_rate=("net_return_slip_0bps", lambda s: float(s.gt(0).mean())),
            )
            .reset_index()
        )
        daily["group"] = group
        daily["event_share_in_group"] = daily["n_events"] / total_events
        rows.extend(daily.to_dict("records"))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["group", "event_share_in_group", "net0_6h_mean"], ascending=[True, False, False]
    )


def build_untradable_reasons(labels: pd.DataFrame) -> pd.DataFrame:
    event_level = labels[labels["label_valid"]].drop_duplicates("event_id").copy()
    reasons = {
        "small_reference_quote_lt_10": event_level["reference_quote_amount"].lt(10),
        "prior_15m_main_events_lt_2": event_level["main_event_count_15m"].lt(2),
        "prior_15m_main_quote_volume_lt_50": event_level["main_quote_volume_15m"].lt(50),
        "round_trip_gas_gt_5pct": event_level["gas_cost_return"].gt(0.05),
    }
    rows = []
    untradable = ~event_level["is_tradable_sample"].fillna(False)
    for reason, mask in reasons.items():
        hit = untradable & mask.fillna(False)
        rows.append(
            {
                "reason": reason,
                "events": int(hit.sum()),
                "share_of_valid_events": float(hit.mean()),
                "share_of_untradable_events": float(hit.sum() / max(int(untradable.sum()), 1)),
            }
        )
    rows.append(
        {
            "reason": "any_untradable",
            "events": int(untradable.sum()),
            "share_of_valid_events": float(untradable.mean()),
            "share_of_untradable_events": 1.0,
        }
    )
    return pd.DataFrame(rows).sort_values("events", ascending=False)


def format_path_rows(path_profiles: pd.DataFrame, rows: int = 10) -> list[dict[str, object]]:
    frame = path_profiles.head(rows)
    return [
        {
            "group": row["group"],
            "shape": row["path_shape"],
            "5m": pct(row["gross_5m"]),
            "15m": pct(row["gross_15m"]),
            "1h": pct(row["gross_1h"]),
            "3h": pct(row["gross_3h"]),
            "6h": pct(row["gross_6h"]),
            "net6h": pct(row["net0_6h"]),
        }
        for _, row in frame.iterrows()
    ]


def format_phenomena_rows(phenomena: pd.DataFrame, horizon: str, rows: int = 12) -> list[dict[str, object]]:
    frame = phenomena[phenomena["horizon"].eq(horizon)].sort_values(
        ["mean_gross_return", "mean_net_0bps"], ascending=False
    ).head(rows)
    return [
        {
            "group": row["group"],
            "events": int(row["n_events"]),
            "gross": pct(row["mean_gross_return"]),
            "net0": pct(row["mean_net_0bps"]),
            "net100": pct(row["mean_net_100bps"]),
            "gross_pos": pct(row["gross_positive_rate"]),
            "net_pos": pct(row["net_0bps_positive_rate"]),
            "cost_drag": pct(row["cost_drag_0bps"]),
            "quote": num(row["median_quote_amount"]),
        }
        for _, row in frame.iterrows()
    ]


def format_daily_rows(daily: pd.DataFrame, group: str, rows: int = 8) -> list[dict[str, object]]:
    frame = daily[daily["group"].eq(group)].sort_values(
        ["event_share_in_group", "net0_6h_mean"], ascending=False
    ).head(rows)
    return [
        {
            "date": row["signal_date"],
            "events": int(row["n_events"]),
            "share": pct(row["event_share_in_group"]),
            "gross6h": pct(row["gross_6h_mean"]),
            "net0": pct(row["net0_6h_mean"]),
            "net100": pct(row["net100_6h_mean"]),
            "hit": pct(row["net0_positive_rate"]),
        }
        for _, row in frame.iterrows()
    ]


def format_untradable_rows(reasons: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {
            "reason": row["reason"],
            "events": int(row["events"]),
            "valid_share": pct(row["share_of_valid_events"]),
            "untradable_share": pct(row["share_of_untradable_events"]),
        }
        for _, row in reasons.iterrows()
    ]


def family_failure_rows(factor_scores: pd.DataFrame) -> list[dict[str, object]]:
    frame = (
        factor_scores[factor_scores["slippage_bps_per_side"].eq(0)]
        .groupby(["factor_family", "horizon"], dropna=False)
        .agg(
            tests=("factor", "size"),
            cost_failed=("gross_positive_net_failed", "sum"),
            best_net=("favorable_net_mean", "max"),
            mean_net=("favorable_net_mean", "mean"),
            best_gross=("favorable_gross_mean", "max"),
        )
        .reset_index()
        .sort_values(["horizon", "best_net"], ascending=[True, False])
    )
    return [
        {
            "family": row["factor_family"],
            "horizon": row["horizon"],
            "tests": int(row["tests"]),
            "cost_failed": int(row["cost_failed"]),
            "best_gross": pct(row["best_gross"]),
            "best_net": pct(row["best_net"]),
            "mean_net": pct(row["mean_net"]),
        }
        for _, row in frame.iterrows()
    ]


def build_report(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    factor_scores: pd.DataFrame,
    phenomena: pd.DataFrame,
    path_profiles: pd.DataFrame,
    daily: pd.DataFrame,
    reasons: pd.DataFrame,
    main_pool: base.MainPool,
) -> str:
    large_buy = path_profiles[path_profiles["group"].eq("large_buy_p90")]
    large_buy_gross_6h = float(large_buy["gross_6h"].iloc[0]) if not large_buy.empty else np.nan
    large_buy_net_6h = float(large_buy["net0_6h"].iloc[0]) if not large_buy.empty else np.nan
    large_buy_shape = str(large_buy["path_shape"].iloc[0]) if not large_buy.empty else "NA"

    all_path = path_profiles[path_profiles["group"].eq("all_tradable")]
    all_gross_6h = float(all_path["gross_6h"].iloc[0]) if not all_path.empty else np.nan
    all_net_6h = float(all_path["net0_6h"].iloc[0]) if not all_path.empty else np.nan

    family_rows = family_failure_rows(factor_scores)
    short_family_rows = [row for row in family_rows if row["horizon"] in {"15m", "6h"}]

    valid_events = labels[labels["label_valid"]]["event_id"].nunique()
    tradable_events = labels[labels["label_valid"] & labels["is_tradable_sample"]][
        "event_id"
    ].nunique()

    return f"""# CHOG 事件因子现象拆解

状态: 2026-05-09。这个补充报告继续研究事件级因子分析的“原理结果现象”，不展开 maker/LP/双向挂单研究。输入复用上一版成本感知事件 label 和本地 `derived/memecoin_event_features`。

复现命令:

```bash
python scripts/chog_event_factor_phenomena_analysis.py
```

输出:

```text
{PHENOMENA_CSV.as_posix()}
{PATH_PROFILES_CSV.as_posix()}
{DAILY_CONCENTRATION_CSV.as_posix()}
{UNTRADABLE_REASONS_CSV.as_posix()}
{REPORT_MD.as_posix()}
```

## 1. 当前现象总览

- 主池仍是研究中心: `{main_pool.dex_id}` / `{main_pool.quote_symbol}` 成交量占 `{pct(main_pool.volume_share)}`。
- 有效事件 `{valid_events:,}`，可交易事件 `{tradable_events:,}`。不可交易样本不是丢弃数据，而是先标记为“不适合 taker 方向研究”。
- 全部可交易事件 6h gross 平均 `{pct(all_gross_6h)}`，扣 2% fee + gas 后 net 平均 `{pct(all_net_6h)}`。
- `large_buy_p90` 是当前最像“现象”的切片: 路径形态 `{large_buy_shape}`，6h gross `{pct(large_buy_gross_6h)}`，0 bps net `{pct(large_buy_net_6h)}`。

这说明当前不是“所有大单都有 alpha”，而是**大额买入在更长 horizon 有延迟延续，短 horizon 和额外滑点下很容易被成本吃掉**。

## 2. 事件路径形态

下面是各事件组从 5m 到 6h 的 gross path。`net6h` 只扣 2% fee + gas，不加额外滑点。

{markdown_table(format_path_rows(path_profiles), [("Group", "group"), ("Shape", "shape"), ("5m", "5m"), ("15m", "15m"), ("1h", "1h"), ("3h", "3h"), ("6h", "6h"), ("Net 6h", "net6h")])}

读法:

1. 如果 5m/15m 弱而 6h 转强，这不是秒级冲击，而像“事件后迟滞延续”。
2. 如果 6h gross 仍不够覆盖 2% fee + gas，它只能解释市场结构，不能当方向信号。
3. `high_small_noise_p90`、`high_event_density_p90` 即使 gross 有时为正，也更像 regime/过滤变量。

## 3. 6h 现象排名

6h 是目前唯一能露出弱正边际的 horizon。下面按 6h gross 排序:

{markdown_table(format_phenomena_rows(phenomena, "6h"), [("Group", "group"), ("Events", "events"), ("Gross", "gross"), ("Net0", "net0"), ("Net100", "net100"), ("Gross >0", "gross_pos"), ("Net >0", "net_pos"), ("Cost Drag", "cost_drag"), ("Median Quote", "quote")])}

关键点:

- 大额买入和高成交/高拥挤状态在 6h gross 上更强，但 `Net100` 普遍显著下降。
- `current_buy` 优于 `current_sell`，但这个差异主要在 6h 才有研究价值。
- 中短 horizon 的 gross 边际太薄，更多是在测成本约束，而不是测 alpha。

## 4. 15m 失败现象

15m 是“看起来有微弱解释力但过不了成本”的典型 horizon:

{markdown_table(format_phenomena_rows(phenomena, "15m"), [("Group", "group"), ("Events", "events"), ("Gross", "gross"), ("Net0", "net0"), ("Net100", "net100"), ("Gross >0", "gross_pos"), ("Net >0", "net_pos"), ("Cost Drag", "cost_drag"), ("Median Quote", "quote")])}

这解释了为什么之前小时级 IC 容易误导: 方向排序可能存在，但平均 gross 只有几十 bps，固定 2% round-trip fee 直接把它压成负数。

## 5. 样本集中度

`large_buy_p90` 的 6h 现象是否由少数日期驱动:

{markdown_table(format_daily_rows(daily, "large_buy_p90"), [("Date", "date"), ("Events", "events"), ("Share", "share"), ("Gross 6h", "gross6h"), ("Net0", "net0"), ("Net100", "net100"), ("Hit", "hit")])}

`high_event_density_p90` 的 6h 集中度:

{markdown_table(format_daily_rows(daily, "high_event_density_p90"), [("Date", "date"), ("Events", "events"), ("Share", "share"), ("Gross 6h", "gross6h"), ("Net0", "net0"), ("Net100", "net100"), ("Hit", "hit")])}

读法: 如果某个切片的正收益高度集中在少数日期，它应被视作“候选现象”，而不是稳健因子。

## 6. 不可交易样本原因

按有效事件去重后的不可交易原因:

{markdown_table(format_untradable_rows(reasons), [("Reason", "reason"), ("Events", "events"), ("Valid Share", "valid_share"), ("Untradable Share", "untradable_share")])}

这些原因解释了为什么不能把所有事件直接塞进方向回测。dust quote、低活跃和 gas 占比异常会制造非常夸张的 net label，需要先作为过滤层。

## 7. 因子族失败图谱

按 0 bps slippage 统计部分 horizon 的因子族表现:

{markdown_table(short_family_rows, [("Family", "family"), ("Horizon", "horizon"), ("Tests", "tests"), ("Cost Failed", "cost_failed"), ("Best Gross", "best_gross"), ("Best Net", "best_net"), ("Mean Net", "mean_net")])}

## 8. 目前因子结论更新

1. **大额买入不是立即可交易信号，而是 6h 迟滞延续现象。** 它值得扩数据验证，但不能直接追。
2. **成本失败不是噪声，而是结构性结果。** 5m/15m 的 gross 空间太薄，2% fee 本身就足以否定大部分方向交易。
3. **拥挤/高成交量是双刃剑。** 它提高 6h gross 排名，但也可能对应更高滑点和状态切换风险。
4. **小单噪声和低活跃应先做过滤层。** 它们对方向解释弱，主要帮助识别“不该研究/不该交易”的样本。
5. **暂不展开 maker。** 当前下一步仍应沿事件原理继续: 扩历史样本、检查大额买入是否跨日期稳定、把 6h 迟滞现象拆成大额买入后连续买盘、卖压吸收、非主池背离三类。
"""


def main() -> None:
    warnings.filterwarnings("ignore", category=PerformanceWarning)
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_cost_outputs()

    labels = pd.read_csv(LABELS_CSV)
    factor_scores = pd.read_csv(FACTOR_SCORES_CSV)
    features, main_pool = load_features()
    features = add_group_flags(features)
    joined = prepare_joined(labels, features)

    phenomena = build_phenomena(joined)
    path_profiles = build_path_profiles(phenomena)
    daily = build_daily_concentration(joined)
    reasons = build_untradable_reasons(labels)

    phenomena.to_csv(PHENOMENA_CSV, index=False)
    path_profiles.to_csv(PATH_PROFILES_CSV, index=False)
    daily.to_csv(DAILY_CONCENTRATION_CSV, index=False)
    reasons.to_csv(UNTRADABLE_REASONS_CSV, index=False)
    REPORT_MD.write_text(
        build_report(
            features=features,
            labels=labels,
            factor_scores=factor_scores,
            phenomena=phenomena,
            path_profiles=path_profiles,
            daily=daily,
            reasons=reasons,
            main_pool=main_pool,
        ),
        encoding="utf-8",
    )

    print(f"wrote {PHENOMENA_CSV} rows={len(phenomena)}")
    print(f"wrote {PATH_PROFILES_CSV} rows={len(path_profiles)}")
    print(f"wrote {DAILY_CONCENTRATION_CSV} rows={len(daily)}")
    print(f"wrote {UNTRADABLE_REASONS_CSV} rows={len(reasons)}")
    print(f"wrote {REPORT_MD}")


if __name__ == "__main__":
    main()
