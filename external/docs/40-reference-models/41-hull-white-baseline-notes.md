# Hull-White baseline 笔记

## 目的
说明为什么 Hull-White 在当前项目里有参考价值，但只能作为 **baseline / reduced-form 对照**，不能进入主方程。

## 核心对象
Hull-White / OU 类模型的典型形式是：

$$
dX_t=-\alpha(X_t-c)\,dt+\sigma\,dW_t.
$$

它的优点不在“利率”二字，而在三个结构特征：

1. 均值回复  
2. 低维参数化  
3. 易于滤波与校准

## 对 Monad 最值得借的地方
### 1. 当作失衡修复的零阶基线
在 Monad 语境下，最自然的借法不是建原始价格模型，而是拿结构量做 OU baseline，例如：

$$
dE_{\mathrm{cycle},t}=-\alpha(E_{\mathrm{cycle},t}-c_t)\,dt+\sigma\,dW_t
$$

或者

$$
dM_{\max,t}=-\alpha(M_{\max,t}-c_t)\,dt+\sigma\,dW_t.
$$

这样做的解释是：

- $\alpha$：套利修复速度
- $c_t$：当前 regime 下的平衡水平
- $\sigma$：未解释的扰动

### 2. 当作部分信息滤波的线性骨架
如果未来要给某个潜在状态做线性高斯过滤，Hull-White / OU 形式是很好的基线。例如：

$$
dx_t=-\alpha(x_t-c_t)\,dt+\sigma\,dW_t,
\qquad
y_t=x_t+\varepsilon_t.
$$

这类模型很适合做：

- Kalman filter
- baseline state-space
- jump / regime-switching 升级前的对照

## 为什么它不能成为主模型
Hull-White 不能做主模型，原因很明确：

1. 它没有 branch canonical 风险  
2. 它没有 partial-information control 的结构  
3. 它没有 local mempool / leader-path  
4. 它没有 reserve / revert / conflict  
5. 它是连续路径近似，而 Monad 的关键是事件驱动与跳变

因此，它最多只能回答：

$$
\text{“某个结构量是否呈均值回复，以及均值回复速度是多少？”}
$$

而不能回答：

$$
\text{“当前在 Proposed 阶段是否该出手？”}
$$

## 与主线的关系
在整套文档里，Hull-White 只应当出现在：

- reduced-form 对照
- baseline 动态层
- 滤波方法参考

它绝不应当进入 `20-core-model/` 的主方程。

## 数据前提 / 识别边界
RPC-only 层就足以拟合 Hull-White baseline，因为它不要求强识别 branch 与 execution outputs。  
但这也恰好说明：它不够 Monad-native。

## 下一步
如果要看更广的文献脉络，请读 [相关论文地图](./42-related-papers-map.md)。
