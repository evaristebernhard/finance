# CCUSDT Replay Exchange 研究专著

这是面向未来自己和新 Codex 的研究专著，不是原始报告归档。原始报告仍然留在 `docs/markets/ccusdt/` 和 `systems/ccusdt_replay_exchange/docs/`；本书负责把它们整理成一条可理解、可复现、可继续研究的主线。

## 编译

```powershell
typst compile docs/books/ccusdt-replay-exchange/book.typ docs/books/ccusdt-replay-exchange/out/ccusdt-replay-exchange-v0.1.pdf
```

## 写作原则

- 中文为主，保留 `Runner`、`Bot`、`decision_frame`、`runtime-safe` 等工程术语。
- 公式使用 Typst 原生 math。
- 每章默认结构：问题、第一性原理、数学对象、工程映射、当前证据、未解决问题。
- 书稿只引用 run/report 路径，不复制大体量 `runs/` artifacts。
- 书稿是解释层，报告和 parquet/csv 是证据层。

## 第一版内容

- 第 1 章精写：从第一性原理定义 edge。
- 第 2 章精写：因子语言与 Python 研究循环。
- 第 3 章精写：本地 Replay Exchange 与双轨回测。
- 第 4 章为后续章节提纲：停时、杠杆、执行现实性、Monitor、失败案例与研究纪律。

## 主要源材料

- `docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md`
- `docs/markets/ccusdt/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md`
- `docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md`
- `docs/markets/ccusdt/v1-tfi-exit-wait-value-decomposition-20260524.md`
- `systems/ccusdt_replay_exchange/docs/architecture.md`

