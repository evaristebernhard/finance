# MON/USDC Live Order Book Collector

状态: `live_orderbook_l2_v1` 使用 `strict_l2` 模式运行；旧的 `live_orderbook_v1` partial top20 数据保留。

这条路径从当前时间开始记录 Binance USD-M futures `MONUSDT` 的实时订单簿。当前 `https://fapi.binance.com` 的 REST depth snapshot 已可用；`fapi1/fapi2/fapi3/fapi4.binance.com` 当前会返回空 `202`，strict 模式默认只使用 `https://fapi.binance.com`。

## 两种模式

`strict_l2`:

- REST snapshot: `GET /fapi/v1/depth?symbol=MONUSDT&limit=1000`
- WebSocket: `monusdt@depth@100ms`
- WebSocket: `monusdt@bookTicker`
- WebSocket: `monusdt@aggTrade`
- 本地维护 price -> qty map，输出 top5/top20/top100/top500/top1000 notional、WOBI、microprice、spread、depth slope。

`partial_top20`:

- WebSocket: `monusdt@depth20@100ms`
- WebSocket: `monusdt@bookTicker`
- WebSocket: `monusdt@aggTrade`
- 仅用于 REST snapshot 不可用时的 fallback；它不是严格 full L2。

## 严格 L2 对齐规则

启动时先打开 `monusdt@depth@100ms` 并缓冲 diff events，再拉 REST snapshot。拿到 `lastUpdateId` 后:

- 丢弃 `u < lastUpdateId` 的 diff event。
- 第一条可用 diff 必须满足 `U <= lastUpdateId <= u`。
- 之后每条 diff 必须满足 `pu == previous_u`。
- 如果 `pu` 断裂、snapshot 失败或 bootstrap 超时，collector 必须 resync/reconnect；不会继续伪造连续 book。

## 输出

- raw diff/bookTicker/aggTrade stream:
  `data/mon_usdc/v1/raw/binance_live_orderbook_events`
- raw REST snapshot:
  `data/mon_usdc/v1/raw/binance_live_orderbook_snapshots`
- 1s features:
  `data/mon_usdc/v1/derived/mon_usdc_live_orderbook_features_1s`
- strict checkpoint:
  `data/mon_usdc/v1/_checkpoints/mon_usdc_live_orderbook_MONUSDT_live_orderbook_l2_v1.json`
- old partial checkpoint:
  `data/mon_usdc/v1/_checkpoints/mon_usdc_live_orderbook_MONUSDT_live_orderbook_v1.json`
- logs:
  `data/mon_usdc/v1/_work/live_orderbook_logs`

## 启动

前台运行:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_mon_usdc_live_orderbook.ps1 `
  -Mode strict_l2 `
  -RunTag live_orderbook_l2_v1 `
  -RestBase https://fapi.binance.com
```

后台启动:

```powershell
Start-Process -FilePath powershell.exe -ArgumentList @(
  '-NoProfile',
  '-ExecutionPolicy',
  'Bypass',
  '-File',
  'scripts\run_mon_usdc_live_orderbook.ps1',
  '-Mode',
  'strict_l2',
  '-RunTag',
  'live_orderbook_l2_v1',
  '-RestBase',
  'https://fapi.binance.com'
) -WindowStyle Hidden
```

若只想回退到 partial top20:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_mon_usdc_live_orderbook.ps1 `
  -Mode partial_top20 `
  -RunTag live_orderbook_v1
```

## 停止

查看相关进程:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*mon_usdc_live_orderbook*' } |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine
```

停止某个 run tag 时，先确认 `CommandLine` 包含对应 `-RunTag`，再停止 wrapper 与其子 Python 进程。

## 查看状态

```powershell
Get-Content data\mon_usdc\v1\_checkpoints\mon_usdc_live_orderbook_MONUSDT_live_orderbook_l2_v1.json
```

重点看:

- `mode`
- `counters.status`
- `counters.messages`
- `counters.features_written`
- `counters.last_event_utc`
- `counters.strict_l2_ready`
- `counters.snapshot_last_update_id`
- `counters.resync_count`
- `counters.sequence_gaps`
- `snapshot_current_part`

`strict_l2_ready=true` 且 `best_bid < best_ask` 时，才把 1s feature 视为严格 L2 产物。

## 当前特征

1s feature CSV 包含:

- `mode`
- `snapshot_last_update_id`
- `strict_l2_ready`
- `resync_count`
- `book_levels_bid/book_levels_ask`
- `best_bid/best_ask`
- `spread_bps`
- `microprice`
- `bid_notional_top5/top20/top100/top500/top1000`
- `ask_notional_top5/top20/top100/top500/top1000`
- `wobi_top5/top20/top100/top500/top1000`
- `depth_slope_bid/depth_slope_ask`
- `taker_buy_quote/taker_sell_quote`
- `trade_imbalance`
- `max_trade_quote`
- `sweep_intensity`
- `sequence_gaps`

这些特征适合研究 CEX 主导动力学、DEX 偏离恢复和实时 regime filter，不直接等价于可执行交易策略。
