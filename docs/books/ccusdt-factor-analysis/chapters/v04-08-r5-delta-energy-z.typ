#import "../styles.typ": definition, proposition, evidence, remark, factor

= 第 8 章：R5/R10 为什么不是质量分数

== 本章要解决的困惑

R5 曾经被误解成“最近表现好，所以当前 entry 好”的质量分数。更准确地说，R5 是路径形状比率。它描述最近已关闭 entry 的有利路径和不利路径的比例，但隐藏了规模、能量和估计稳定性。

== 一个具体例子

考虑两组历史：

```text
A: P=2,   N=1
B: P=200, N=100
```

如果只看比例：

$ R = P / (N + epsilon) $

两组都约等于 2。但 A 可能只是很薄的样本噪声，B 才表示最近路径有较强的活动能量。比例一样，不代表信息质量一样。

再看：

```text
C: P=1, N=0.05
D: P=12, N=6
```

C 的 R 非常高，D 的 R 只有 2。但 C 的高 R 可能只是 denominator 太小，不是强质量。

== 从例子推导数学对象

对 entry $i$，只允许使用在它之前已经关闭的历史 entry。若 horizon 是 60 秒，合法历史集合是：

$ cal(I)_i = { j : t_j + 60s < t_i } $

最近 $k$ 个历史 entry 的有利质量和不利质量记为：

$ P_(i,k) = sum_(j in "last-k"(cal(I)_i)) P_j $

$ N_(i,k) = sum_(j in "last-k"(cal(I)_i)) N_j $

路径形状比率为：

$ R_(i,k) = P_(i,k) / (N_(i,k) + epsilon) $

为了不被比例欺骗，需要同时看：

$ Delta_(i,k) = P_(i,k) - N_(i,k) $

$ E_(i,k) = P_(i,k) + N_(i,k) $

$ Z_(i,k) = Delta_(i,k) / sqrt(E_(i,k) + epsilon) $

Delta 测净优势，Energy 测路径活动强度，Z 测能量调整后的净优势。

== 正式定义

#definition("路径形状比率", [
  R5/R10 是最近 5 个或 10 个已关闭历史 entry 的有利路径质量与不利路径质量之比。它是路径记忆变量，不是 entry 的绝对质量分数。
])

#definition("预序贯 R5", [
  预序贯表示 entry $i$ 的 R5 只能使用 $t_j+h<t_i$ 的历史 entry。尚未走完 horizon 的 entry 不能进入 R5。
])

#proposition("R5 不识别能量", [
  对任意正数 $c$，$(P,N)$ 与 $(c P,c N)$ 给出近似相同的 R，但二者的估计稳定性和金融含义不同。因此 R 必须与 Delta、Energy、Z 一起解释。
])

== CCUSDT 实证证据

#evidence("R5 与四象限", [
  TFI factor decomposition 报告中，`11_r5_frames` mean 约 5.1410、total 约 5850.4711；`10_r5_only` mean 约 1.8514；`01_frames_only` mean 约 1.7760。`closed5_energy` 是强 metric spread 变量之一，支持把 R5 拆成 ratio 与 energy。
])

== 失败机制

R5 失败主要有五类。

第一，低能量比例膨胀。分母太小导致 R 很高。

第二，局部状态断裂。最近几个 entry 的环境和当前不同。

第三，更新时钟错误。若把尚未关闭的 entry 放入 R5，就泄漏未来。

第四，与退出混淆。R5 可能预测早期释放，但 fixed60 退出仍然失败。

第五，sizing 放大左尾。高 R5 和高 frames 同时出现时，若权重过高，个别回吐会被放大。

== 策略/runtime 边界

R5 可以运行时安全，但必须由 Bot 自己维护 closed-entry 队列。不能从旧研究 panel 读取 R5 seed，也不能用同日未来 entry 修正当前 R5。

== 因子卡片

#factor("路径形状比率 R5/R10", [
  中文名：路径形状比率。英文/代码名：R5、R10。它测量最近已关闭 entry 的路径形状记忆。它可能有效，是因为短期市场状态有局部自相关。它会失败，是因为比例隐藏能量、易受低分母膨胀影响，并且容易和退出失败混淆。
])

== 本章小结

R5 的正确用法不是“R5 大就加仓”，而是把它作为路径记忆的一部分，并同时观察 Delta、Energy、Z、frames、价差和容量。R5 是分解语言，不是质量标签。
