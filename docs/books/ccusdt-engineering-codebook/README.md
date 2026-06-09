# CCUSDT Replay Exchange 工程代码导读 v0.1

这是一本独立工程教材，目标是帮助未来自己和新 Codex 看懂 `systems/ccusdt_replay_exchange` 当前代码。

它不是系统白皮书，也不是完整 runbook。主线是：

```text
文件树 -> 数据层 -> fast backtest -> Python Bot -> Rust Runner -> event log -> fast vs strict
```

## 编译

```powershell
typst compile docs/books/ccusdt-engineering-codebook/book.typ docs/books/ccusdt-engineering-codebook/out/ccusdt-engineering-codebook-v0.1.pdf
```

## 写作边界

- 不修改 Runner、Bot、diagnostics 代码。
- 不修改 `data/`、`date/`、`runs/`、`.env*`、`rpc.txt`。
- 代码路径、函数名、profile 名保留英文；解释用中文。
- 先讲读代码路径，再讲设计理由。
