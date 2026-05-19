# BONK Bullish V3 Trade Side Semantics Analysis

状态: 2026-05-13。本文件扩展 `bonk_v3_side_semantics_probe` 到当前本地已有 BONK Bullish raw gzip 覆盖面，只读已有 `bullish_trades` 与 `bullish_book_ticker`，没有拉取新数据，也没有修改现有脚本。

## 输出

本轮输出:

```text
date/bonk_v3_side_semantics_full_sample.csv
date/bonk_v3_side_semantics_full_summary.json
docs/markets/bonk/v1-cex-v3-side-semantics-analysis.md
```

`full_sample.csv` 是 symbol-date 粒度的全量聚合表，不是逐笔交易明细表。本轮没有抽样: 覆盖 `BONK1MUSDC` / `BONK1MUSDT` 在 `data/bonk/v1/external/bullish_trades` 中已有且能匹配 book_ticker 的全部 14 个日期。

## 方法

输入范围:

| symbol | dates | trade rows | book_ticker rows |
| --- | --- | ---: | ---: |
| BONK1MUSDC | 2026-04-29..2026-05-12 | 388,533 | 1,333,645 |
| BONK1MUSDT | 2026-04-29..2026-05-12 | 45,839 | 1,707,714 |
| total | 28 symbol-date groups | 434,372 | 3,041,359 |

Quote-rule side 的构造方式:

```text
1. 对每笔 trade，用 backward merge_asof 找到同 symbol/date 下 timestamp <= trade_timestamp 的最近 book_ticker。
2. 最大 quote age 为 5,000 ms。
3. trade price >= ask 时标记 quote_rule_aggressor_side=buy。
4. trade price <= bid 时标记 quote_rule_aggressor_side=sell。
5. bid < price < ask 时，用 mid 判断: price > mid 为 buy，price < mid 为 sell。
6. mid tie、无 quote、invalid/crossed quote 标记 unknown。
```

这个规则是一个可复现的 inferred aggressor side 近似，不依赖 Bullish reported `side` 字段。它仍然不是交易所官方 aggressor 标记。

## 总体结果

全样本中，quote-rule 可判定的比较为 409,603 笔，占全部 trade 的 94.30%。reported side 与 quote-rule side 的总体关系为:

| metric | rows | share |
| --- | ---: | ---: |
| consistent | 112,469 | 27.46% of known |
| reverse | 297,134 | 72.54% of known |
| unknown comparison | 24,769 | 5.70% of all |

如果只看总数，会得到“reported side 大概率反向”的印象；但这个结论对 `BONK1MUSDT` 不成立。必须按 quote currency 拆开。

## USDC vs USDT

| symbol | known comparisons | consistent | reverse | unknown/all | read |
| --- | ---: | ---: | ---: | ---: | --- |
| BONK1MUSDC | 364,177 | 24.14% | 75.86% | 6.27% | reported side mostly opposite quote-rule side |
| BONK1MUSDT | 45,426 | 54.07% | 45.93% | 0.90% | mixed / inconclusive |

`BONK1MUSDC` 的反向关系在每一天都存在: daily reverse share of known 的范围是 70.75% 到 79.99%。这说明 USDC pair 的 Bullish reported `side` 很可能不是可直接使用的 aggressor side；若在没有 quote 的场景中硬要从 reported side 构造方向，简单 flip 比直接使用更接近 quote-rule，但仍有约 24% known-comparison 错误率。

`BONK1MUSDT` 明显不同: daily reverse share of known 的范围是 38.01% 到 51.56%，全样本为 45.93%。这不是稳定反向，也不是稳定同向。对 USDT pair，不应使用 reported side，也不应使用 flipped reported side 来近似 aggressor side。

## Crosstab

全样本 reported side vs quote-rule side:

| symbol | reported buy -> quote buy | reported buy -> quote sell | reported sell -> quote buy | reported sell -> quote sell |
| --- | ---: | ---: | ---: | ---: |
| BONK1MUSDC | 41,750 | 131,747 | 144,521 | 46,159 |
| BONK1MUSDT | 11,473 | 10,340 | 10,526 | 13,087 |

USDC 的两条 off-diagonal 都大于 diagonal，且很稳定。USDT 的四格更接近平衡，reported side 对 aggressor side 的信息含量不足。

## Inferred Aggressor Side

可以构造 inferred aggressor side，但应该优先使用 quote-rule side，而不是 reported side:

```text
inferred_aggressor_side = quote_rule_aggressor_side
```

适用条件:

```text
book_ticker 在 trade timestamp 前 5 秒内存在；
bid/ask 有效且未 crossed；
trade price 不落在 midpoint tie。
```

本地数据满足这个条件的覆盖率较高:

| symbol | matched quote/all | quote-rule unknown/all | main unknown reason |
| --- | ---: | ---: | --- |
| BONK1MUSDC | 99.01% | 6.27% | mostly midpoint ties |
| BONK1MUSDT | 99.11% | 0.90% | mostly no quote within tolerance |

研究使用建议:

```text
BONK1MUSDC:
  - 有 book_ticker 时，用 quote-rule inferred aggressor side。
  - 无 book_ticker 时，flipped reported side 可作为弱 fallback，但必须带 quality flag。
  - 不要把 raw reported side 当 buy/sell pressure。

BONK1MUSDT:
  - 有 book_ticker 时，用 quote-rule inferred aggressor side。
  - 无 book_ticker 时，不建议从 reported side 构造 aggressor side。
  - 不建议用 simple flip。
```

## 结论

Bullish BONK trade `side` 语义不是一个可跨 `BONK1MUSDC` 与 `BONK1MUSDT` 直接复用的 aggressor-side 字段。

`BONK1MUSDC` 呈现稳定反向，但反向强度约 76%，不足以把 flipped reported side 当成干净逐笔标签。`BONK1MUSDT` 是混合状态，不能安全同向或反向映射。

因此后续 V3 microstructure/activity 因子里，涉及 buy/sell pressure、signed volume、aggressor imbalance 的变量，应基于 book_ticker quote-rule inferred side 构造，并保留 `unknown` / quote age / midpoint tie 质量字段。reported side 只能作为诊断字段，不应直接进入方向性因子。
