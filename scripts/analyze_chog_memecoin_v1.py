from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path("data/chog/v1")
DATE_DIR = Path("date")
DOCS_DIR = Path("docs")
RUN_TAG = "20260508"

EVENT_FEATURES = ROOT / "derived" / "memecoin_event_features"
HOURLY_FEATURES = ROOT / "derived" / "memecoin_hourly_features"
PRICE_CSV = DATE_DIR / "chog_prices_476h_1h.csv"

POOL_SUMMARY_CSV = DATE_DIR / f"chog_memecoin_v1_pool_summary_{RUN_TAG}.csv"
DAILY_SUMMARY_CSV = DATE_DIR / f"chog_memecoin_v1_daily_summary_{RUN_TAG}.csv"
HOURLY_MARKET_CSV = DATE_DIR / f"chog_memecoin_v1_hourly_market_features_{RUN_TAG}.csv"
FACTOR_TESTS_CSV = DATE_DIR / f"chog_memecoin_v1_factor_tests_{RUN_TAG}.csv"
REPORT_MD = DOCS_DIR / f"chog_memecoin_first_analysis_{RUN_TAG}.md"


def read_parquet_parts(path: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(part) for part in sorted(path.rglob("*.parquet"))]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def pct(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value) * 100:.{digits}f}%"


def num(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "NA"
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.{digits}f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.{digits}f}k"
    return f"{value:.{digits}f}"


def raw_num(value: float | int | None, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def short_hex(value: str, chars: int = 6) -> str:
    if not isinstance(value, str) or len(value) <= 2 * chars + 2:
        return value
    return f"{value[: chars + 2]}...{value[-chars:]}"


def markdown_table(rows: list[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(key, "")) for _, key in columns) + " |")
    return "\n".join([header, sep, *body])


def prepare_events(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    events["block_dt"] = pd.to_datetime(events["block_datetime_utc"], utc=True)
    events["hour_utc"] = events["block_dt"].dt.floor("h").dt.strftime("%Y-%m-%dT%H:00:00Z")
    events["date"] = events["block_dt"].dt.strftime("%Y-%m-%d")
    events["is_buy"] = events["direction"].eq("buy_chog")
    events["is_sell"] = events["direction"].eq("sell_chog")
    events["buy_chog_event"] = events["chog_amount"].where(events["is_buy"], 0.0)
    events["sell_chog_event"] = events["chog_amount"].where(events["is_sell"], 0.0)
    events["effective_gas_gwei"] = events["effective_gas_price"].astype(float) / 1e9
    events["priority_fee_gwei"] = events["priority_fee_per_gas_proxy"].astype(float) / 1e9
    return events


def build_pool_summary(events: pd.DataFrame) -> pd.DataFrame:
    pool = (
        events.groupby(["dex_id", "pool_address", "quote_symbol"], dropna=False)
        .agg(
            events=("transaction_hash", "size"),
            txs=("transaction_hash", "nunique"),
            buy_events=("is_buy", "sum"),
            sell_events=("is_sell", "sum"),
            buy_chog=("buy_chog_event", "sum"),
            sell_chog=("sell_chog_event", "sum"),
            net_buy_chog=("signed_chog_flow", "sum"),
            chog_volume=("chog_amount", "sum"),
            quote_volume=("quote_amount", "sum"),
            first_seen=("block_datetime_utc", "min"),
            last_seen=("block_datetime_utc", "max"),
        )
        .reset_index()
    )
    pool["event_share"] = pool["events"] / pool["events"].sum()
    pool["volume_share"] = pool["chog_volume"] / pool["chog_volume"].sum()
    pool["net_flow_ratio"] = pool["net_buy_chog"] / pool["chog_volume"].replace(0, np.nan)
    return pool.sort_values(["chog_volume", "events"], ascending=False)


def build_daily_summary(events: pd.DataFrame) -> pd.DataFrame:
    daily = (
        events.groupby("date", dropna=False)
        .agg(
            events=("transaction_hash", "size"),
            txs=("transaction_hash", "nunique"),
            pools=("pool_address", "nunique"),
            buy_events=("is_buy", "sum"),
            sell_events=("is_sell", "sum"),
            buy_chog=("buy_chog_event", "sum"),
            sell_chog=("sell_chog_event", "sum"),
            net_buy_chog=("signed_chog_flow", "sum"),
            chog_volume=("chog_amount", "sum"),
            quote_volume=("quote_amount", "sum"),
            effective_gas_gwei_mean=("effective_gas_gwei", "mean"),
            priority_fee_gwei_mean=("priority_fee_gwei", "mean"),
        )
        .reset_index()
    )
    daily["net_flow_ratio"] = daily["net_buy_chog"] / daily["chog_volume"].replace(0, np.nan)
    return daily


def build_hourly_market(events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    hourly = (
        events.groupby("hour_utc", dropna=False)
        .agg(
            events=("transaction_hash", "size"),
            unique_txs=("transaction_hash", "nunique"),
            pools=("pool_address", "nunique"),
            dexes=("dex_id", "nunique"),
            active_blocks=("block_number", "nunique"),
            buy_events=("is_buy", "sum"),
            sell_events=("is_sell", "sum"),
            buy_chog=("buy_chog_event", "sum"),
            sell_chog=("sell_chog_event", "sum"),
            net_buy_chog=("signed_chog_flow", "sum"),
            chog_volume=("chog_amount", "sum"),
            quote_volume=("quote_amount", "sum"),
            effective_gas_gwei_mean=("effective_gas_gwei", "mean"),
            priority_fee_gwei_mean=("priority_fee_gwei", "mean"),
            same_block_pool_event_count_mean=("same_block_pool_event_count", "mean"),
            same_block_pool_event_count_max=("same_block_pool_event_count", "max"),
            receipt_success_rate=("receipt_status", "mean"),
        )
        .reset_index()
    )
    hourly["buy_event_ratio"] = hourly["buy_events"] / hourly["events"].replace(0, np.nan)
    hourly["net_flow_ratio"] = hourly["net_buy_chog"] / hourly["chog_volume"].replace(0, np.nan)
    hourly["log_chog_volume"] = np.log1p(hourly["chog_volume"])

    price_frame = prices[["hour_utc", "price_usd", "fill_method"]].copy()
    price_frame["return_1h"] = price_frame["price_usd"].pct_change()
    for horizon in [1, 3, 6, 12, 24]:
        price_frame[f"fwd_{horizon}h"] = (
            price_frame["price_usd"].shift(-horizon) / price_frame["price_usd"] - 1
        )

    merged = price_frame.merge(hourly, on="hour_utc", how="left")
    zero_cols = [
        "events",
        "unique_txs",
        "pools",
        "dexes",
        "active_blocks",
        "buy_events",
        "sell_events",
        "buy_chog",
        "sell_chog",
        "net_buy_chog",
        "chog_volume",
        "quote_volume",
    ]
    merged[zero_cols] = merged[zero_cols].fillna(0)
    merged.loc[merged["events"].eq(0), ["buy_event_ratio", "net_flow_ratio"]] = 0
    merged["log_chog_volume"] = np.log1p(merged["chog_volume"])
    merged["net_buy_usd_at_hour_price"] = merged["net_buy_chog"] * merged["price_usd"]
    merged["chog_volume_usd_at_hour_price"] = merged["chog_volume"] * merged["price_usd"]
    return merged


def build_factor_tests(hourly_market: pd.DataFrame) -> pd.DataFrame:
    factors = [
        "events",
        "log_chog_volume",
        "net_buy_chog",
        "net_flow_ratio",
        "buy_event_ratio",
        "effective_gas_gwei_mean",
        "priority_fee_gwei_mean",
        "active_blocks",
        "pools",
    ]
    targets = ["return_1h", "fwd_1h", "fwd_3h", "fwd_6h", "fwd_12h", "fwd_24h"]
    rows: list[dict[str, object]] = []
    for factor in factors:
        for target in targets:
            frame = hourly_market[[factor, target]].replace([np.inf, -np.inf], np.nan).dropna()
            if len(frame) < 30 or frame[factor].nunique() < 3:
                continue
            try:
                tercile = pd.qcut(frame[factor], 3, labels=False, duplicates="drop")
            except ValueError:
                continue
            if tercile.nunique(dropna=True) < 2:
                continue
            frame = frame.assign(tercile=tercile)
            low = frame.loc[frame["tercile"].eq(frame["tercile"].min()), target].mean()
            high = frame.loc[frame["tercile"].eq(frame["tercile"].max()), target].mean()
            rows.append(
                {
                    "factor": factor,
                    "target": target,
                    "n": len(frame),
                    "pearson": frame[factor].corr(frame[target], method="pearson"),
                    "spearman": frame[factor].corr(frame[target], method="spearman"),
                    "top_minus_bottom": high - low,
                    "bottom_mean": low,
                    "top_mean": high,
                }
            )
    return pd.DataFrame(rows)


def build_report(
    events: pd.DataFrame,
    hourly_features: pd.DataFrame,
    prices: pd.DataFrame,
    pool_summary: pd.DataFrame,
    daily_summary: pd.DataFrame,
    hourly_market: pd.DataFrame,
    factor_tests: pd.DataFrame,
) -> str:
    total_buy = float(events["buy_chog_event"].sum())
    total_sell = float(events["sell_chog_event"].sum())
    total_volume = float(events["chog_amount"].sum())
    net_buy = float(events["signed_chog_flow"].sum())
    fill_counts = prices["fill_method"].value_counts().to_dict()
    observed = int(fill_counts.get("observed", 0))
    forward_fill = int(fill_counts.get("forward_fill", 0))

    q_rows = []
    for q in [0.50, 0.90, 0.95, 0.99]:
        threshold = events["chog_amount"].quantile(q)
        selected = events["chog_amount"].ge(threshold)
        q_rows.append(
            {
                "quantile": f"top {pct(1 - q, 0)}",
                "threshold": num(threshold),
                "events": int(selected.sum()),
                "volume_share": pct(events.loc[selected, "chog_amount"].sum() / total_volume),
            }
        )

    top_pools = pool_summary.head(5).copy()
    pool_rows = []
    for _, row in top_pools.iterrows():
        pool_rows.append(
            {
                "dex": row["dex_id"],
                "pool": short_hex(row["pool_address"]),
                "quote": row["quote_symbol"],
                "events": int(row["events"]),
                "event_share": pct(row["event_share"]),
                "volume": num(row["chog_volume"]),
                "volume_share": pct(row["volume_share"]),
                "net_buy": num(row["net_buy_chog"]),
            }
        )

    top_daily_volume = daily_summary.sort_values("chog_volume", ascending=False).head(5)
    daily_volume_rows = [
        {
            "date": row["date"],
            "events": int(row["events"]),
            "volume": num(row["chog_volume"]),
            "net_buy": num(row["net_buy_chog"]),
            "net_ratio": pct(row["net_flow_ratio"]),
        }
        for _, row in top_daily_volume.iterrows()
    ]

    top_net_buy = daily_summary.sort_values("net_buy_chog", ascending=False).head(5)
    top_net_sell = daily_summary.sort_values("net_buy_chog").head(5)
    flow_rows = []
    for _, row in top_net_buy.iterrows():
        flow_rows.append(
            {
                "side": "net buy",
                "date": row["date"],
                "events": int(row["events"]),
                "net_buy": num(row["net_buy_chog"]),
                "volume": num(row["chog_volume"]),
                "net_ratio": pct(row["net_flow_ratio"]),
            }
        )
    for _, row in top_net_sell.iterrows():
        flow_rows.append(
            {
                "side": "net sell",
                "date": row["date"],
                "events": int(row["events"]),
                "net_buy": num(row["net_buy_chog"]),
                "volume": num(row["chog_volume"]),
                "net_ratio": pct(row["net_flow_ratio"]),
            }
        )

    same_hour = (
        factor_tests[factor_tests["target"].eq("return_1h")]
        .assign(abs_spearman=lambda frame: frame["spearman"].abs())
        .sort_values("abs_spearman", ascending=False)
        .head(6)
    )
    same_hour_rows = [
        {
            "factor": row["factor"],
            "n": int(row["n"]),
            "pearson": raw_num(row["pearson"]),
            "spearman": raw_num(row["spearman"]),
            "top_bottom": pct(row["top_minus_bottom"]),
        }
        for _, row in same_hour.iterrows()
    ]

    future = (
        factor_tests[~factor_tests["target"].eq("return_1h")]
        .assign(abs_spearman=lambda frame: frame["spearman"].abs())
        .sort_values("abs_spearman", ascending=False)
        .head(10)
    )
    future_rows = [
        {
            "factor": row["factor"],
            "target": row["target"],
            "n": int(row["n"]),
            "pearson": raw_num(row["pearson"]),
            "spearman": raw_num(row["spearman"]),
            "top_bottom": pct(row["top_minus_bottom"]),
        }
        for _, row in future.iterrows()
    ]

    top_trades = events.sort_values("chog_amount", ascending=False).head(8)
    trade_rows = [
        {
            "time": row["block_datetime_utc"],
            "dex": row["dex_id"],
            "dir": row["direction"],
            "chog": num(row["chog_amount"]),
            "quote": num(row["quote_amount"]),
            "tx": short_hex(row["transaction_hash"]),
        }
        for _, row in top_trades.iterrows()
    ]

    coverage_rows = [
        {"metric": "event feature rows", "value": f"{len(events):,}"},
        {"metric": "hourly pool feature rows", "value": f"{len(hourly_features):,}"},
        {"metric": "unique txs", "value": f"{events['transaction_hash'].nunique():,}"},
        {"metric": "pools / DEXes", "value": f"{events['pool_address'].nunique()} / {events['dex_id'].nunique()}"},
        {"metric": "event block window", "value": f"{int(events['block_number'].min())}..{int(events['block_number'].max())}"},
        {"metric": "event time window", "value": f"{events['block_datetime_utc'].min()} -> {events['block_datetime_utc'].max()}"},
        {"metric": "price hours", "value": f"{len(prices):,} ({observed} observed, {forward_fill} forward_fill)"},
        {"metric": "price time window", "value": f"{prices['hour_utc'].min()} -> {prices['hour_utc'].max()}"},
    ]

    price_return = prices["price_usd"].iloc[-1] / prices["price_usd"].iloc[0] - 1
    event_hours_with_price = int(hourly_market["events"].gt(0).sum())

    return f"""# CHOG Memecoin 第一版数据分析

状态: 2026-05-08。基于当前 `data/chog/v1` 里已经质量检查通过的 memecoin 路径数据，以及 `date/chog_prices_476h_1h.csv` 小时价格序列。

本报告是第一版研究结论，不是交易信号。当前可做的是识别市场结构、流量解释力和候选因子方向；还不够做稳健实盘判断。

## 1. 数据范围

{markdown_table(coverage_rows, [("指标", "metric"), ("值", "value")])}

本次脚本产物:

```text
{POOL_SUMMARY_CSV.as_posix()}
{DAILY_SUMMARY_CSV.as_posix()}
{HOURLY_MARKET_CSV.as_posix()}
{FACTOR_TESTS_CSV.as_posix()}
```

复现命令:

```bash
python scripts/analyze_chog_memecoin_v1.py
```

价格样本从 `{prices['hour_utc'].min()}` 到 `{prices['hour_utc'].max()}`，累计收益约 `{pct(price_return)}`。价格样本和链上小时特征重叠 `{event_hours_with_price}` 个小时。

## 2. 核心结论

1. CHOG 仍然是高度主池驱动市场。`nad-fun` 主池占 `{pct(pool_summary.iloc[0]['event_share'])}` 的 swap 事件和 `{pct(pool_summary.iloc[0]['volume_share'])}` 的 CHOG 成交量，其他池子更多是补充流动性。
2. 事件笔数偏卖出，但金额只轻微偏净买入。全样本 `buy_chog={num(total_buy)}`，`sell_chog={num(total_sell)}`，净买入 `{num(net_buy)}`，只占总成交 `{pct(net_buy / total_volume)}`。因此单看 buy/sell count 会误导。
3. 成交额极度肥尾。Top 1% swap 贡献 `{q_rows[-1]['volume_share']}` 的 CHOG 成交量，top 5% 贡献 `{q_rows[2]['volume_share']}`。后续因子要区分“大单冲击”和“小单噪声”。
4. 同小时解释力强，预测力还弱。`net_buy_chog` 对同小时价格收益 Spearman IC 为 `{raw_num(same_hour.iloc[0]['spearman'])}`；但未来收益里最强的单因子 Spearman 也只有 `{raw_num(future.iloc[0]['spearman'])}` 左右，第一版只能作为候选方向。

## 3. 池子结构

{markdown_table(pool_rows, [("DEX", "dex"), ("Pool", "pool"), ("Quote", "quote"), ("Events", "events"), ("Event Share", "event_share"), ("CHOG Volume", "volume"), ("Volume Share", "volume_share"), ("Net Buy", "net_buy")])}

解释:

- `nad-fun` 主池占绝大多数真实成交量，适合作为 CHOG 市场方向的主因子来源。
- `atlantis-dex` 事件数不低，但成交量只占 `{pct(pool_summary.iloc[1]['volume_share'])}`，更多反映碎片化交易。
- 其他池子事件占比高于成交量占比，说明小额交易比较多，不能用事件数直接代表市场冲击。

## 4. 日级流量

成交量最高的日期:

{markdown_table(daily_volume_rows, [("Date", "date"), ("Events", "events"), ("CHOG Volume", "volume"), ("Net Buy", "net_buy"), ("Net/Volume", "net_ratio")])}

净买入/净卖出最极端的日期:

{markdown_table(flow_rows, [("Side", "side"), ("Date", "date"), ("Events", "events"), ("Net Buy", "net_buy"), ("CHOG Volume", "volume"), ("Net/Volume", "net_ratio")])}

解释:

- `2026-05-06` 是当前样本里成交量最高日，且净买入明显，和价格样本末端的上行阶段一致。
- `2026-04-24` 同时是高成交和强净买入日，属于后续需要重点回放的上涨冲击样本。
- `2026-04-18`、`2026-04-12`、`2026-04-27` 是较强净卖出日，适合作为风险控制样本。

## 5. 大单集中度

按单笔 `chog_amount` 看成交集中度:

{markdown_table(q_rows, [("Bucket", "quantile"), ("Threshold", "threshold"), ("Events", "events"), ("Volume Share", "volume_share")])}

最大单笔交易:

{markdown_table(trade_rows, [("Time", "time"), ("DEX", "dex"), ("Direction", "dir"), ("CHOG", "chog"), ("Quote", "quote"), ("Tx", "tx")])}

解释:

大单占比太高，所以后续信号最好拆成:

```text
large_trade_net_flow
small_trade_count_imbalance
large_trade_follow_through
large_sell_absorption
```

而不是只用总 `net_buy_chog`。

## 6. 价格与链上因子

同小时相关性只能说明解释力，不能当预测:

{markdown_table(same_hour_rows, [("Factor", "factor"), ("N", "n"), ("Pearson", "pearson"), ("Spearman", "spearman"), ("Top-Bottom", "top_bottom")])}

未来收益候选因子:

{markdown_table(future_rows, [("Factor", "factor"), ("Target", "target"), ("N", "n"), ("Pearson", "pearson"), ("Spearman", "spearman"), ("Top-Bottom", "top_bottom")])}

第一版解读:

- `net_buy_chog` 对同小时收益解释力最强，符合 swap 是价格发现源的直觉。
- 对未来 3h，`net_buy_chog` 有弱正相关，top/bottom 三分位差约 `{pct(future[future['factor'].eq('net_buy_chog') & future['target'].eq('fwd_3h')]['top_minus_bottom'].iloc[0])}`。
- 24h 上 `log_chog_volume` 和事件活跃度偏正，像“波动扩张后趋势延续”，但样本仍短。
- gas/priority fee 的 12h/24h Spearman 偏正，但 Pearson 接近 0，可能是 regime 或时间趋势，不应单独使用。

## 7. 下一版建议

1. 在 memecoin features 里加入大单分层: top 1%、top 5%、固定 CHOG/USD 阈值。
2. 增加池子流动性和成交额 USD 标准化，构建 `net_buy_usd / liquidity_usd`。
3. 把价格小时序列继续向前补到 `2026-04-12`，否则前五天链上数据不能进入因子检验。
4. 做事件后路径研究: 大额买入/卖出后的 1h、3h、6h、24h 平均路径。
5. 分开测试主池和非主池，避免小池事件数污染主池成交量信号。

## 8. 局限

- 价格样本只有 476 小时，其中 `{forward_fill}` 小时是 forward fill。
- 链上样本覆盖 25 天，但价格可检验窗口从 `2026-04-17T06:00:00Z` 才开始。
- 当前只做单因子 IC 和三分位差，没有做费用、滑点、容量、成交延迟和 out-of-sample。
- `quote_amount` 主要是 MON，不是统一 USD；报告里成交量排序主要用 CHOG 数量。
"""


def main() -> None:
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    events = prepare_events(read_parquet_parts(EVENT_FEATURES))
    hourly_features = read_parquet_parts(HOURLY_FEATURES)
    prices = pd.read_csv(PRICE_CSV)

    pool_summary = build_pool_summary(events)
    daily_summary = build_daily_summary(events)
    hourly_market = build_hourly_market(events, prices)
    factor_tests = build_factor_tests(hourly_market)

    pool_summary.to_csv(POOL_SUMMARY_CSV, index=False)
    daily_summary.to_csv(DAILY_SUMMARY_CSV, index=False)
    hourly_market.to_csv(HOURLY_MARKET_CSV, index=False)
    factor_tests.to_csv(FACTOR_TESTS_CSV, index=False)

    report = build_report(
        events=events,
        hourly_features=hourly_features,
        prices=prices,
        pool_summary=pool_summary,
        daily_summary=daily_summary,
        hourly_market=hourly_market,
        factor_tests=factor_tests,
    )
    REPORT_MD.write_text(report, encoding="utf-8")

    print(f"wrote {POOL_SUMMARY_CSV}")
    print(f"wrote {DAILY_SUMMARY_CSV}")
    print(f"wrote {HOURLY_MARKET_CSV}")
    print(f"wrote {FACTOR_TESTS_CSV}")
    print(f"wrote {REPORT_MD}")


if __name__ == "__main__":
    main()
