# CCUSDT 当前策略真相页

Status: `current_runtime_plain_20260603`.

这页只回答一个问题：**当前 CCUSDT runtime 策略实际在做什么。**

先说结论：它不是深度学习模型，不是动态 L2 path model，也不是复杂微观结构预测器。当前策略很简单，本质上是一个手写状态机：

```text
TFI 触发
+ past_event / frames 过滤
+ spread q70 admission
+ R5 / frames 四象限 sizing
+ 3x capacity ledger
+ fixed60 / 简单 exit
```

旧研究报告里有很多因子、路径、Pareto、maker、OFI/MLOFI、Delta/Energy、深度学习方向的讨论。那些是研究参考，不等于当前 Bot 已经实现。

## 当前 Runtime 实际流程

当前策略先等一个主动成交流信号。方向来自 `TFI`：

```text
TFI > 0 -> long / buy
TFI < 0 -> short / sell
```

然后检查几个很朴素的条件：

```text
abs(TFI) >= 1
abs(past_event_25_bps) <= 0.5
trade_window_count > 0
entry_cross_bps <= prior-day q70
```

这句话翻译成人话就是：

```text
最近确实有主动成交；
主动方向足够明显；
价格刚才还没明显释放；
现在吃单的 spread 成本不算太贵。
```

如果通过，就产生一个 entry 候选。之后策略用 `R5` 和 `frames_since_mid_change` 分四象限：

```text
00_none        = R5 不好，mid 也不 stale
10_r5_only     = R5 好，但 mid 不 stale
01_frames_only = R5 不好，但 mid stale
11_r5_frames   = R5 好，且 mid stale
```

四象限不决定方向，只决定目标仓位倍率 `gamma`。目标仓位大致是：

```text
target_exposure = weak_overlay_weight * gamma[cell]
```

最后进入 3x 杠杆账本：

```text
actual_exposure = min(target_exposure, 3 - open_exposure)
```

账本满了就剪裁或跳过。到期后用 fixed60 或简单 exit 逻辑退出。

## Runtime 已用因子

当前 CC runtime 实际用到这些东西：

```text
TFI
past_event_25_bps
trade_window_count
spread / entry_cross_bps / prior-day q70
frames_since_mid_change
R5
cell = 00 / 10 / 01 / 11
gamma
capacity ledger
```

其中 `R5` 只来自已经闭合的 shadow entry outcome，不读 future label，不读 `date/`，不读 scored entries。

## Runtime 没用上的内容

下面这些内容可能在研究报告里出现，但**没有进入当前 CC runtime 控制**：

```text
Delta_bps / Energy_bps
OFI / MLOFI
动态 L2 path prediction
深度学习模型
maker 策略
L2 容量曲线
path distribution model
```

特别注意：

```text
Delta_bps / Energy_bps 目前没有进入 CC runtime 控制。
OFI / MLOFI 不是当前 entry trigger。
当前策略不是动态 L2 path model。
当前策略不是深度学习。
```

`Delta/Energy/Z` 的价值目前主要在研究层：它们说明 `R5` 这个比例太粗，应该拆成强度和能量。但这还没有完整迁移成 Bot 的 runtime sizing/admission profile。

## 它简单在哪里

当前策略简单到可以概括为：

```text
看到主动流；
确认价格没明显动；
确认 spread 不太贵；
按 R5/frames 给一点仓位；
3x 账本控制总 exposure；
固定或简单退出。
```

它没有真正预测：

```text
entry 后最大能涨多少；
最大值什么时候出现；
从最大值回落到 0bps 要多久；
哪些路径会延续，哪些路径会快速回吐；
不同 L2 动态结构下路径分布是否不同。
```

所以它不是一个完整预测模型，只是一个最小可运行状态机。

## 当前最大缺口

当前最该补的不是继续调 `gamma`，也不是先谈容量，而是建立预测对象和路径分布：

```text
entry 时刻状态 X_t
-> 后续路径最大值
-> 最大值时间
-> 峰值后回零时间
-> fixed60 只是其中一个终点读数
```

在这个基础上，才值得讨论：

```text
Delta/Energy 是否进入控制；
是否需要动态 L2 特征；
是否需要机器学习或深度学习；
exit 是否比 entry 更重要。
```

换句话说，当前策略的真实状态是：

```text
已经有一个简单可运行的 TFI 状态机；
还没有一个严肃的路径预测模型。
```

## 阅读顺序

新 Codex 或读者应该先读这一页，再读旧 handoff 和研究报告。旧报告有证据和历史脉络，但里面很多内容是研究方向，不是 runtime truth。
