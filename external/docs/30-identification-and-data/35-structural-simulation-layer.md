# 结构仿真伴随层

## 目的
说明结构仿真在这套研究中的地位：  
它是 unified kernel 的伴随页，不是新的主模型页。

结构仿真的职责只有两类：

1. 帮助理解 kernel 的局部比较静态
2. 在真实观测不足时，为 projection 与环境过程提供校准、压力测试与 regime sweep

## 它不负责什么
结构仿真不再承担下面这些职责：

- 定义 canonical state
- 定义 canonical action
- 定义主线 Bellman
- 把 proxy、情景轴或实验模块写成新的理论总纲

这些都属于 unified kernel 主模型。

## 仿真与主线的接口
结构仿真应围绕 unified state 分模块设计：

### 1. $G_t$ 模块
模拟：

- AMM 图
- 池状态
- 路径机会几何

输出：

- $\Gamma_t(P,x)$
- $M_{\max,t},E_{\mathrm{cycle},t}$ 等 summary

### 2. $M_t,C_t$ 模块
模拟：

- block state 升级
- leader window
- 传播与竞争环境

输出：

- $p_t,u_t,q_t(a)$ 的局部行为

### 3. $R_t$ 模块
模拟：

- reserve slack
- delegation / authority
- exception 与 budget 约束

输出：

- $r_t(a)$ 的局部行为
- 可行动作集变化

### 4. $E_t$ 模块
模拟：

- 访问热点
- 冲突与重执行环境

输出：

- $\kappa_t(a)$ 的局部行为

## 仿真输出应是什么
结构仿真最合适的输出不是新的“主模型参数表”，而是：

- projection surface
- comparative statics
- phase diagram
- admissibility region
- stress-test panel

## 与经验层的关系
结构仿真和经验校准的关系应写成：

$$
\text{主线 kernel}
\to
\text{projection}
\to
\text{simulation / observation}
\to
\text{calibration}.
$$

其中：

- 仿真帮助理解和缩小可能区间
- 数据帮助把这些区间进一步校准到现实

## 直觉解释
这层真正的价值，不在于“替代真实世界”，而在于：

$$
\text{先看清 unified kernel 的局部机制，再决定该去观测和校准哪些对象。}
$$

## 与主线的关系
本页明确降级为方法论伴随页，只服务统一核主线，不再与主模型竞争总纲地位。

## 下一步
回到 [统一核下的估计程序](./34-estimation-program.md)，将仿真输出接入估计与校准程序。
