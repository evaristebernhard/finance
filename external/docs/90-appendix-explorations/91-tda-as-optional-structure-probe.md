# TDA 作为可选结构探针

## 目的
说明 TDA 为什么仍然值得保留，但只能作为**后期结构探针**，而不能进入当前主线。

## 核心对象
在当前项目里，TDA 最多承担三类可选任务：

1. 机会图的 persistent $H_1$
2. `latest/safe/finalized` 的 zigzag persistence
3. conflict complex 的高阶结构

## 正式定义 / 方程
可选的对象构造示例包括：

### 1. 机会图 filtration
设图边权由结构量定义，则可以构造一族子图

$$
G_t(\epsilon_1)\subseteq G_t(\epsilon_2)\subseteq \cdots
$$

并研究 persistent $H_1$。

### 2. commit-state zigzag
若以后有更细的 commit-state / branch 数据，可以研究

$$
K_t^{\mathrm{latest}}\leftrightarrow K_t^{\mathrm{safe}}\leftrightarrow K_t^{\mathrm{finalized}}
$$

上拓扑特征的 survival。

## 它真正擅长什么
TDA 擅长的是：

- 发现多尺度结构
- 描述 regime 的形状变化
- 提供高阶摘要，而不是单点打分

如果后面你的结构量已经稳定，TDA 很可能对下面两类问题有帮助：

1. 哪些机会结构是“短命噪声”
2. 哪些结构在提交态升级后仍然 survive

## 它为什么不能当主线
当前主线问题是：

$$
\text{searcher 在当前信息和预算约束下是否该 act / wait / abort。}
$$

TDA 并不直接回答这个问题。  
它更像是在主模型外面做：

- 高阶结构摘要
- regime 探测
- 形状变化可视化

所以如果把 TDA 放到主线前面，很容易发生两件事：

1. 先有漂亮结构图，但还没有稳健参数与识别  
2. 读者以为项目核心是拓扑，而不是 Monad 专有控制问题

## 与主线的关系
TDA 的最合理位置是：

$$
\text{主模型稳定之后的结构探针}
$$

它可以读取主模型已经产出的对象，例如：

- $M_C$
- $E_{\mathrm{cycle}}$
- $p,r,q,\kappa$ 的时间序列

但不应反过来定义主模型。

## 数据前提 / 识别边界
TDA 的两个高风险点是：

1. 数据稀疏  
2. 对象构造不稳

因此，它至少应建立在下面这些东西已经稳定之后：

$$
M_C,\quad E_{\mathrm{cycle}},\quad p,\quad r,\quad q,\quad \kappa.
$$

## 下一步
如果未来真的要上 TDA，应该先回到主线，把：

- 对象怎么构造  
- 它对应什么经济含义  
- 它和 belief state 如何对接

这三件事先钉牢，然后再做拓扑分析。
