# MON/USDC Tardis Access Notes

状态: 已接入本地 `TARDIS_API_KEY`，但当前 key 不包含 `binance-futures` 历史 data feed 权限。

## 本地配置

私有 key 放在:

```text
.env.chog.local
```

变量名固定为:

```text
TARDIS_API_KEY="..."
```

不要使用 Python 风格的多行括号拼接；普通 shell、PowerShell wrapper 和轻量 Python 脚本都按单行 env 变量读取。

快速检查:

```powershell
python scripts\tardis_access_probe.py --env-file .env.chog.local
```

## 当前 Key 权限

当前可用 access scope:

| exchange | accessType | from | to |
| --- | --- | --- | --- |
| deribit | academic | 2025-04-11 | 2026-07-12 |
| bybit-options | academic | 2025-04-11 | 2026-07-12 |
| binance-european-options | academic | 2025-04-11 | 2026-07-12 |
| okex-options | academic | 2025-04-11 | 2026-07-12 |
| huobi-dm-options | academic | 2025-04-11 | 2026-07-12 |
| bullish | academic | 2026-04-29 | 2026-07-12 |

当前不可用:

```text
binance-futures data feed
```

这意味着它不能直接拉 `binance-futures` 的 `MONUSDT` 历史 `depth/depthSnapshot/bookTicker`。`binance-futures` metadata 能看到 `monusdt`，也能看到 `depth`、`depthSnapshot`、`bookTicker` channel，但 data-feed 权限不包含该交易所。

## 对 MON/USDC 的价值

直接价值:

- 暂时不能补 `MONUSDT` 历史逐笔 L2。
- 不能替代当前自建的 Binance strict live L2 collector。

间接价值:

- 可用 Deribit、Binance European Options 等期权市场构造全市场 risk regime。
- 可观察 BTC/ETH options implied volatility、skew、term structure、event risk。
- 这些变量适合作为外部状态过滤器，例如判断当前是否处在高波动、波动率上行、尾部风险偏高的 regime。

对 MON/USDC 的推荐用法:

```text
Binance strict live L2: MONUSDT 订单簿主数据
Tardis options feeds: 市场风险状态与波动率背景
DEX MON/USDC: 局部偏离、恢复速度、成本后可交易空间
```

## 若要购买 Binance Futures 历史 L2

Tardis 当前定价页显示:

- Perpetuals Solo: CSV download，约 `700 USD/month`
- Perpetuals Professional: CSV download + raw tick data replay API，约 `900 USD/month`

本项目需要自动化使用 `data-feeds` API 和历史 tick replay，所以应按 `Perpetuals Professional` 口径评估。

购买/申请时要明确要求:

```text
exchange: binance-futures
symbol: monusdt / all perpetuals
channels: depth, depthSnapshot, bookTicker, trades or aggTrades equivalent
date range: at least 2026-02-01 onward
```

如果只买 CSV download，研究仍可做，但需要另写 CSV 下载/解析路径，不能直接复用 Tardis `data-feeds` replay。

## 与 Live Collector 的关系

当前本机已经运行:

```text
live_orderbook_l2_v1
```

它使用 Binance USD-M futures REST snapshot + diff depth stream 自建严格 L2，只覆盖启动后的实时数据。Tardis 的价值主要是补历史；如果没有 `binance-futures` 权限，就继续靠 live collector 累积本地历史。
