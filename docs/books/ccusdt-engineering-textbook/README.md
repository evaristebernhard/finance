# CCUSDT 工程回测教材 v0.2

这本书是独立 LaTeX 工程教材，不替代旧 Typst codebook。目标是让“Python 会一点、Rust 新人”从 L2 订单簿第一性原理出发，完整理解当前 CCUSDT 简单策略、fast backtest、Python Bot 和 Rust Runner。

核心主线：

```text
L2 order book / trades
-> strategy definitions
-> canonical quote/trade/L2
-> DecisionL2Book / DecisionFrameBuilder
-> decision_frame_v1 Parquet
-> fast_strategy_backtest
-> Python Bot
-> Rust Runner
-> event log / artifacts
```

编译：

```powershell
xelatex -interaction=nonstopmode -output-directory docs/books/ccusdt-engineering-textbook/out docs/books/ccusdt-engineering-textbook/book.tex
xelatex -interaction=nonstopmode -output-directory docs/books/ccusdt-engineering-textbook/out docs/books/ccusdt-engineering-textbook/book.tex
Copy-Item -Force docs/books/ccusdt-engineering-textbook/out/book.pdf docs/books/ccusdt-engineering-textbook/out/ccusdt-engineering-textbook-v0.2.pdf
```

输出：

```text
docs/books/ccusdt-engineering-textbook/out/ccusdt-engineering-textbook-v0.2.pdf
```

边界：

```text
本书只解释当前策略和回测链路。
不修改 Runner/Bot/Monitor/diagnostics。
不读取或修改 data/date/runs/.env*/rpc.txt。
研究报告不是 runtime truth。
```
