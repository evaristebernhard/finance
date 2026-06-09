= 附录 B：继续写作说明与证据纪律

== 本版定位

v0.4 的定位是中文推导式专业讲义。它不再把英文术语和形式化定义放在最前面，而是先从订单、盘口、成交、价差、深度、主动流和路径出发，再推导 TFI、R5、四象限、分布估计、停时和策略边界。

写作时应保持一个原则：如果读者不能说出这个量“测量了市场中的哪一件事”，就不要急着给它英文缩写。

== 证据使用纪律

本书是解释层，不是证据层。正文只摘关键数字；完整表格、脚本和参数应留在研究报告中。继续写作时优先引用以下类型的事实：

- 机制事实：例如 TFI 是主动流分子，depth 是冲击分母。
- 估计事实：例如 IC、AUC、Spearman、CVaR、tail_share。
- 路径事实：例如 release、decay、MFE、固定 horizon 回吐。
- 执行事实：例如 entry spread、exit spread、taker crossing、latency、depth sweep。
- 容量事实：例如 3x 上限、FIFO clipping、idle sleeve。

不要把不同层的数字混成一个“总收益故事”。总收益只能说明组合结果，不能直接证明某个因子有效或无效。

== 推荐补写方向

- 为第 2 章增加一页更真实的 CCUSDT 盘口截图或表格。
- 为第 6 章增加 TFI 的手算例题：同一组成交分别计算 raw、notional、share、Z 四种口径。
- 为第 8 章增加 R5 的 closed-entry 队列图，说明为什么尚未关闭的 entry 不能进入 R5。
- 为第 11 章增加 `1615412`、`2377379`、`2361187`、`2583437` 的路径小图。
- 为第 13 章增加 fast-vs-strict 分解图：mid edge、entry spread、exit spread、capacity、latency。

== 禁止回退的写法

- 不要用英文缩写替代解释。
- 不要一章开头就抛 Definition/Proposition。
- 不要把 oracle 诊断写成 runtime rule。
- 不要因为 `net_median < 0` 直接删除右尾结构。
- 不要把 q60/q65 sensitivity 写成主线结论。
- 不要把策略 PnL 等同于因子质量。

== 编译命令

```powershell
typst compile docs/books/ccusdt-factor-analysis/book.typ docs/books/ccusdt-factor-analysis/out/ccusdt-factor-analysis-v0.4.pdf
```
