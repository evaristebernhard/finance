# BONK Bullish L2 + CEX Regime 研究计划 v1

状态: 2026-05-13。当前主线从 BTC options 样例框架转向 BONK CEX 数据研究。本文只定义研究架构和可用数据，不承诺交易收益。

## 当前实现状态

Rust 主链路已经完成第一版 Bullish L2 basket 与 Binance spot kline context。最新 run tag:

```text
20260513_bullish_l2_basket_price_v1
```

核心产物:

```text
docs/markets/bonk/v1-cex-l2-report.md
docs/markets/bonk/v1-cex-l2-analysis.md
data/bonk/v1/derived/bonk_cex_l2_state
data/bonk/v1/derived/bonk_cex_covariance_state
data/bonk/v1/derived/bonk_path_labels
data/bonk/v1/derived/bonk_cex_price_context
```

第一版保持边界: 不拉 options，不使用 Binance Futures replay，不输出交易规则，也不声称 alpha。`incremental_book_L2` 继续后置，直到需要严格 OFI 或 queue-level reconstruction。

## 研究对象

设 BONK 的 CEX 主价格过程为

\[
X_t=\log S_t.
\]

目标不是直接预测单点收益

\[
X_{t+H}-X_t,
\]

而是估计给定当前状态后的未来路径分布:

\[
Z_t^{\mathrm{CEX}},Z_t^{\mathrm{L2}},Z_t^{\mathrm{BONK}}
\longmapsto
\mathcal L\left(
\{X_{t+u}-X_t:0\le u\le H\}\mid Z_t
\right).
\]

路径标签优先使用 first-passage 形式:

\[
\tau_a^+(t)=\inf\{u\in[0,H]:X_{t+u}-X_t\ge a\},
\]

\[
\tau_b^-(t)=\inf\{u\in[0,H]:X_{t+u}-X_t\le -b\}.
\]

核心问题是:

\[
\mathbb P(\tau_a^+<\tau_b^-\mid Z_t\in A)
-
\mathbb P(\tau_a^+<\tau_b^-)
\]

是否在跨日期、跨参数、跨市场状态下稳定为正。

## Bullish Tardis 数据

当前 `.env.chog.local` 的 `TARDIS_API_KEY` 已探测到 `bullish` academic access:

\[
2026\text{-}04\text{-}29
\le t <
2026\text{-}07\text{-}12.
\]

同一 key 当前不支持 `binance-futures` data-feeds replay。`binance-futures` metadata 能看到 `1000bonkusdt` 与 `depth/depthSnapshot/bookTicker` 等通道，但实际 data-feeds 请求会返回:

```text
The provided API key does not allow access to the data feed of 'binance-futures' exchange.
```

因此 BONK 第一版历史 L2 数据入口以 Bullish downloadable CSV 为准，不以 Binance Futures 为准。

Bullish datasets 当前已导出到:

\[
2026\text{-}05\text{-}12T00:00:00Z.
\]

BONK symbols:

\[
\mathrm{BONK1MUSDC},\qquad \mathrm{BONK1MUSDT}.
\]

注意: Bullish 的 BONK 报价单位是每 \(10^6\) BONK 的 USDC/USDT 价格。例如:

\[
P_{\mathrm{BONK1MUSDC}}=7.245
\quad\Longleftrightarrow\quad
P_{\mathrm{BONK}}\approx 7.245\times 10^{-6}\ \mathrm{USDC}.
\]

可用 datasets data types:

| data type | 用途 | 第一版优先级 |
| --- | --- | --- |
| `book_snapshot_25` | 每次快照含 top 25 bid/ask，低成本构造 spread、depth、WOBI、microprice | 高 |
| `book_ticker` | best bid/ask 与数量，适合做 1s/minute top-of-book 状态 | 高 |
| `trades` | 成交方向、价格、数量，构造主动买卖流 | 高 |
| `book_snapshot_5` | 更轻的 top 5 快照，可做 smoke 或低成本备选 | 中 |
| `quotes` | quote 更新流，适合后续细化盘口状态 | 中 |
| `incremental_book_L2` | L2 增量订单簿，可重建严格本地 book / OFI，但文件更大 | 后置 |

Tardis downloadable CSV 路径形态:

\[
\texttt{https://datasets.tardis.dev/v1/bullish/}
\{dataType\}
\texttt{/YYYY/MM/DD/BONK1MUSDC.csv.gz}.
\]

例如:

```text
https://datasets.tardis.dev/v1/bullish/book_snapshot_25/2026/05/10/BONK1MUSDC.csv.gz
https://datasets.tardis.dev/v1/bullish/book_ticker/2026/05/10/BONK1MUSDC.csv.gz
https://datasets.tardis.dev/v1/bullish/trades/2026/05/10/BONK1MUSDC.csv.gz
https://datasets.tardis.dev/v1/bullish/incremental_book_L2/2026/05/10/BONK1MUSDC.csv.gz
```

当前 key 对 `bullish` 是 downloadable CSV 权限。`data-feeds` replay API smoke 返回:

```text
Solo and academic subscriptions do not provide access to the data feed API,
but to downloadable CSV files only.
```

因此第一版应实现 CSV download/extract，不写成 streaming replay。

2026-05-10 `BONK1MUSDC` 文件量级示例:

| data type | compressed size |
| --- | ---: |
| `incremental_book_L2` | about `277 MB/day` |
| `book_snapshot_25` | about `21 MB/day` |
| `book_ticker` | about `1.8 MB/day` |
| `trades` | about `0.8 MB/day` |

第一版建议:

\[
\texttt{book\_snapshot\_25}
+
\texttt{book\_ticker}
+
\texttt{trades}.
\]

只有当需要严格订单簿重建、严格 OFI 或 queue-level 分析时，才启用:

\[
\texttt{incremental\_book\_L2}.
\]

## L2 状态变量

设 top \(n\) 层 bid notional 与 ask notional 为

\[
D_{bid,t}^{(n)}
=
\sum_{i=1}^n B_{i,t}q_{bid,i,t},
\]

\[
D_{ask,t}^{(n)}
=
\sum_{i=1}^n A_{i,t}q_{ask,i,t}.
\]

加权订单簿不平衡:

\[
\mathrm{WOBI}_t^{(n)}
=
\frac{D_{bid,t}^{(n)}-D_{ask,t}^{(n)}}
{D_{bid,t}^{(n)}+D_{ask,t}^{(n)}+\varepsilon}.
\]

最优盘口 mid 与 spread:

\[
m_t=\frac{A_t+B_t}{2},
\]

\[
s_t=A_t-B_t.
\]

Microprice:

\[
\mathrm{MicroPrice}_t
=
\frac{A_t q_{bid,t}+B_t q_{ask,t}}
{q_{bid,t}+q_{ask,t}+\varepsilon}.
\]

Microprice 偏移:

\[
\Delta_t^{micro}
=
10^4\left(
\frac{\mathrm{MicroPrice}_t}{m_t}-1
\right).
\]

简化 OFI 可由 best level 更新近似:

\[
\mathrm{OFI}_t
=
\Delta q_{bid,t}\mathbf 1_{\Delta B_t\ge0}
-
\Delta q_{ask,t}\mathbf 1_{\Delta A_t\le0}.
\]

如果使用 `incremental_book_L2` 重建完整 book，可进一步定义多层 OFI:

\[
\mathrm{OFI}_t^{(n)}
=
\sum_{i=1}^n w_i
\left(
\Delta q_{bid,i,t}
-
\Delta q_{ask,i,t}
\right),
\qquad
w_i=e^{-\alpha(i-1)}.
\]

主动成交流:

\[
\mathrm{TFI}_t
=
\frac{Q_{buy,t}-Q_{sell,t}}
{Q_{buy,t}+Q_{sell,t}+\varepsilon}.
\]

其中 `trades.side` 可用于构造 \(Q_{buy,t}\) 与 \(Q_{sell,t}\)，但需要先确认 Bullish side 语义是 taker side 还是 maker side。第一版报告必须记录该语义，不确认则只称为 exchange-reported side。

## CEX 协方差层

BONK 不应被当作孤立过程。设多资产 CEX return vector:

\[
r_t=
\begin{pmatrix}
r_t^{BTC}\\
r_t^{ETH}\\
r_t^{SOL}\\
r_t^{DOGE}\\
r_t^{SHIB}\\
r_t^{PEPE}\\
r_t^{WIF}\\
r_t^{FLOKI}\\
r_t^{BONK}
\end{pmatrix}.
\]

用 EWMA 协方差:

\[
\Sigma_t
=
\lambda\Sigma_{t-1}
+
(1-\lambda)r_t r_t^\top,
\qquad
\lambda\in[0.94,0.99].
\]

市场共振强度:

\[
\bar\rho_t
=
\frac{2}{N(N-1)}
\sum_{i<j}\rho_{ij,t}.
\]

第一特征值占比:

\[
\phi_t
=
\frac{\lambda_{1,t}}
{\operatorname{tr}(\Sigma_t)}.
\]

当

\[
\phi_t\to 1
\]

时，市场由共同因子主导，BONK 局部信号应降权。

BONK residual 可用 rolling ridge:

\[
r_t^{BONK}
=
\beta_{BTC,t}r_t^{BTC}
+
\beta_{SOL,t}r_t^{SOL}
+
\beta_{MEME,t}r_t^{MEME}
+
\epsilon_t^{BONK}.
\]

其中

\[
r_t^{MEME}
=
\frac{1}{M}\sum_{j=1}^M r_t^{j}.
\]

研究重点是:

\[
\epsilon_t^{BONK}
\]

而不是裸 BONK return。

## Maker 执行层

本文的 maker 不是高频 market making，而是 signal-based limit order trading。

给定状态 \(Z_t\) 和 mid \(m_t\)，挂单价格:

\[
p_{bid,t}=m_t-\delta_t,
\]

或

\[
p_{ask,t}=m_t+\delta_t.
\]

成交不是随机抽样。被动成交条件本身携带信息:

\[
\mathbb E[\Delta X_{t\to t+H}\mid Z_t,\mathrm{fill}]
\ne
\mathbb E[\Delta X_{t\to t+H}\mid Z_t].
\]

因此策略研究必须拆成两层:

\[
\mathbb P(\mathrm{fill}\mid Z_t,\delta_t),
\]

\[
\mathbb E[\mathrm{PnL}\mid Z_t,\delta_t,\mathrm{fill}].
\]

保守成本模型:

\[
C_t
=
2f
+
2\eta_t
+
\mathrm{adverse}_t
+
\mathrm{funding}_t.
\]

其中 \(f\) 为交易费率，\(\eta_t\) 为有效半价差或挂单偏移损耗，\(\mathrm{adverse}_t\) 为 maker fill 后的逆向选择成本。

只有当

\[
\mathbb E[\mathrm{payoff}\mid Z_t,\delta_t,\mathrm{fill}]
-
C_t
>
0
\]

且跨日期稳定，才进入小额实盘验证。

## 第一版输出建议

第一版只构造数据面板与研究报告，不自动交易:

```text
data/bonk/v1/external/bullish_book_snapshot_25
data/bonk/v1/external/bullish_book_ticker
data/bonk/v1/external/bullish_trades
data/bonk/v1/derived/bonk_cex_l2_state
data/bonk/v1/derived/bonk_cex_covariance_state
data/bonk/v1/derived/bonk_path_labels
date/bonk_v1_cex_l2_summary_<run_tag>.csv
date/bonk_v1_cex_l2_factor_tests_<run_tag>.csv
docs/markets/bonk/v1-cex-l2-report.md
```

默认 horizons:

\[
H\in\{1h,4h,12h\}.
\]

默认 barriers:

\[
a,b\in\{50,100,200,300\}\ \mathrm{bps}
\]

并单独测试 volatility-adjusted barrier:

\[
B_t=\max(B_0,c\widehat\sigma_t).
\]

## 风险边界

BONK 的优势是:

\[
\mathrm{path\ space}\gg \mathrm{small\ account\ friction}.
\]

但 BONK 的噪声也更强。任何两周样本结果必须过:

\[
\mathrm{non\ overlap},
\qquad
\mathrm{placebo\ shift},
\qquad
\mathrm{forward\ split},
\qquad
\mathrm{fixed\ barrier\ sensitivity}.
\]

如果某个状态只在单日或单个行情段有效，则不视为因子。
