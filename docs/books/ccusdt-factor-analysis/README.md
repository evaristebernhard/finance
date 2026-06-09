# CCUSDT 第一性原理因子分析 v0.4

这是一本独立的 CCUSDT 因子分析专著，不是 replay exchange 系统书。v0.4 将正文改写为中文推导式专业讲义：先从订单、盘口、成交、价差、深度和主动流建立直觉，再推导 TFI、R5、四象限、入场质量、释放/衰减、停时和运行时边界。

## 编译

```powershell
typst compile docs/books/ccusdt-factor-analysis/book.typ docs/books/ccusdt-factor-analysis/out/ccusdt-factor-analysis-v0.4.pdf
```

## 写作原则

- 正文使用中文主名，英文术语只在首次出现时括号标注。
- 每个公式必须先有问题和例子，再给正式符号。
- 每个因子必须说明它测量 alpha、execution、capacity、tail 还是 diagnostic label。
- `net_median < 0` 不是丢弃结构的充分理由。
- 未来标签、oracle path、MFE/MAE/decay 不能进入运行时信号。

## 边界

- 不修改 Runner、Bot、研究脚本。
- 不修改 `data/`、`date/`、`runs/`、`rpc.txt`、`.env*`。
- 本书是解释层；研究报告和复现实验是证据层。
