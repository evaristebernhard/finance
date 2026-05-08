# 弱观测逆问题、识别与鲁棒 Bellman

## 目的
本页把无节点阶段的弱观测路线严格写成一个数学问题。  
它回答的不是：

$$
\text{还能再接多少 API 或 feature？}
$$

而是：

$$
\text{在给定 unified kernel 的前提下，如何把弱观测数据写成一个可识别、可过滤、可控制的逆问题？}
$$

因此，本页的角色不是重新定义主模型，而是把 [弱观测后验推断](./37-weak-observation-posterior-inference.md) 数学化，并为 [统一核下的估计程序](./34-estimation-program.md) 提供 formal problem statement。

## 证据分层速览
| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| `s_t=(G_t,M_t,C_t,R_t,E_t,F_t)` | 研究latent | 当前仓库代码 + 外部官方资料 + 建模假设 | [统一核主模型](../20-core-model/20-monad-mev-main-model.md) | primitive |
| `O_t` | 可直接观测 + RPC弱代理 | 当前仓库代码 + 外部官方资料 | [弱观测后验推断](./37-weak-observation-posterior-inference.md) | observation object |
| `\theta=(\theta_{\mathrm{obs}},\theta_{\mathrm{env}},\theta_{\mathrm{cal}})` | 研究latent | 建模假设 | 本页、[参数建模总页](./30-parameter-map.md) | 建模 / 校准对象 |
| `\mathcal Q_\theta` | 研究latent | 建模假设 | 本页、[观测、belief 与 reduced-form 压缩](../20-core-model/21-state-space-and-observation.md) | observation kernel |
| `b_t` | 研究latent | 建模假设 | [观测、belief 与 reduced-form 压缩](../20-core-model/21-state-space-and-observation.md) | canonical belief |
| `\tilde b_t,\tilde p_t,\tilde u_t,\tilde q_t,\tilde r_t,\tilde\kappa_t` | 研究latent | 建模假设 + 校准 | [弱观测后验推断](./37-weak-observation-posterior-inference.md)、[统一核下的估计程序](./34-estimation-program.md) | posterior summary |
| `\mathfrak M` | 研究latent | 建模假设 | 本页 | ambiguity set / identified-set carrier |

## 问题定义
### 1. primitive 保持不变
本页继续接受 unified kernel 的 canonical primitive：

$$
s_t=(G_t,M_t,C_t,R_t,E_t,F_t),\qquad a_t,\qquad \mathcal K_t(ds',dy\mid s_t,a_t),\qquad b_t.
$$

这里必须保持一个硬边界：  
即使本页要引入更严格的统计与控制记号，也**不**增加新的 primitive。

### 2. 参数块只作为建模 / 校准对象进入
为了写清观测误差、环境过程与后续校准，需要引入：

$$
\theta=(\theta_{\mathrm{obs}},\theta_{\mathrm{env}},\theta_{\mathrm{cal}}).
$$

其中：

- $\theta_{\mathrm{obs}}$：观测误差、provider-specific distortion、proxy mapping 等对象
- $\theta_{\mathrm{env}}$：环境过程与对手环境相关参数
- $\theta_{\mathrm{cal}}$：最终需要以后验或强观测样本校准的对象

但它们的地位必须被固定为：  
**`θ` 不是新的 primitive，而是 observation / environment / calibration 层的建模对象。**

### 3. 多通道观测
无节点阶段观察到的不是单一信号，而是一组异质通道：

$$
O_t=(O_t^{rpc},O_t^{logs},O_t^{rcpt},O_t^{trace},O_t^{nh},O_t^{px}),
$$

其中可分别对应：

- `rpc`：RPC snapshot 与 block metadata
- `logs`：DEX / pool / transfer logs
- `rcpt`：receipt、gas used、effective gas price、success
- `trace`：call frame、touched contracts、revert path
- `nh`：near-head provider signal
- `px`：外部价格与 route context 补充

这些通道由观测核统一组织：

$$
\mathcal Q_\theta(dO_t\mid s_t,a_{t-1}).
$$

如果以后为了计算方便，把各通道近似写成条件独立，

$$
\mathcal Q_\theta
\approx
\mathcal Q_\theta^{rpc}
\mathcal Q_\theta^{logs}
\mathcal Q_\theta^{rcpt}
\mathcal Q_\theta^{trace}
\mathcal Q_\theta^{nh}
\mathcal Q_\theta^{px},
$$

那也只是建模假设，而不是协议真值。

### 4. belief 与 filtering
canonical belief 继续写成：

$$
b_t=\Pr(s_t\mid \mathcal F_t^{\mathrm{obs}}).
$$

令

$$
\overline{\mathcal K}_t(ds'\mid s_t,a_t)
:=
\int \mathcal K_t(ds',dy\mid s_t,a_t)
$$

表示由 unified kernel 诱导出的边际状态转移核，则 Bayes filtering 可写成：

$$
b_{t+1}(ds')
\propto
\mathcal Q_\theta(dO_{t+1}\mid s',a_t)
\int \overline{\mathcal K}_t(ds'\mid s,a_t)\,b_t(ds).
$$

抽象地写：

$$
b_{t+1}=\mathcal U_\theta(b_t,O_{t+1},a_t),
$$

其中 $\mathcal U_\theta$ 是由转移核与观测核共同诱导出的 filtering operator。

### 5. posterior summary 只属于 reduced-form 层
策略层通常不直接消费完整 belief，而消费压缩对象：

$$
\tilde b_t=\psi(b_t),\qquad
\tilde p_t,\ \tilde u_t,\ \tilde q_t(a),\ \tilde r_t(a),\ \tilde\kappa_t(a).
$$

这里必须再次强调：

- 它们是 posterior summary
- 它们可以服务 Bellman
- 但它们不是机制真值，也不是新的 primitive

这意味着本页真正要解的是：

$$
O_{1:t}
\to
b_t
\to
\tilde b_t
\to
\text{Bellman inputs}.
$$

## 基本假设
### 1. 当前可直接成立的事实
从当前仓库与主线文档出发，本页直接接受以下事实：

- block commit-state 与 access 相关的原生强观测锚点存在于 Execution Events schema 中，但无节点阶段通常拿不到完整原生流
- RPC snapshot、logs、receipts、traces、near-head provider signal 可以作为 observed facts 或 weak proxies
- 第三方 provider signal 不能被直接写成 `BlockVerified`、`AccountAccess`、`StorageAccess` 等原生强观测

因此，本页允许把无节点阶段写成后验推断问题，但不允许把 proxy 伪装成真值。

### 2. `M_t` 的结构假设
对 commit-state 的 reduced-form 数学化，采用有序有限状态链：

$$
\mathcal M=
\{\text{unseen},\text{proposed\_proxy},\text{voted\_proxy},\text{finalized\_proxy},\text{verified\_proxy},\text{dropped}\}.
$$

并施加最小单调性约束：

$$
\Pr(M_{t+1}=j\mid M_t=i)=0
\quad\text{若 } j\prec i,\ j\neq \text{dropped}.
$$

其中 `verified_proxy` 与 `dropped` 可视为吸收态。  
这不是协议原式，而是服务无节点阶段 filtering 的结构假设。

### 3. `E_t` 的结构假设
对访问与冲突环境，采用 latent conflict graph 表示。  
令

$$
E_t \equiv A_t\in\mathbb R_+^{n_t\times n_t},
$$

其中：

$$
A_t=A_t^\top,\qquad \mathrm{diag}(A_t)=0.
$$

并进一步允许：

$$
\|A_t\|_0\le s_E
\qquad\text{或}\qquad
\mathrm{rank}(A_t)\le r_E,
$$

以表达稀疏性或低复杂度约束。  
这表示 `E_t` 更像一个潜在图对象，而不是单一标量。

### 4. `R_t` 的结构假设
对 reserve / admissibility / survival 结构，采用二阶段分解：

$$
r_t(a)=\chi_t(a)\rho_t(a),
$$

其中：

- $\chi_t(a)$：admissibility
- $\rho_t(a)$：在 admissible 条件下的 survival

若写成 hazard / survival 模型，可定义：

$$
\tilde r_t(a)=\Pr(\mathrm{survive}\mid \mathcal F_t^{obs},a),
\qquad
\lambda_t(a)=\Pr(\mathrm{non\mbox{-}survival}\mid \mathcal F_t^{obs},a).
$$

并施加方向性约束：

$$
\frac{\partial \tilde r_t(a)}{\partial \mathrm{size}}\le 0,\qquad
\frac{\partial \tilde r_t(a)}{\partial \mathrm{delay}}\le 0,\qquad
\frac{\partial \tilde r_t(a)}{\partial \mathrm{reserve\ slack}}\ge 0.
$$

### 5. 观测误差与 ambiguity
provider-specific signal 的误差核不默认已知。  
尤其是 near-head phase signal、trace coverage、pending visibility 与 provider-side filtering，当前更合理的做法是：

- 若证据充分，可把它们纳入 $\theta_{\mathrm{obs}}$ 做名义估计
- 若证据不足，应把它们降级到 ambiguity set，而不是假装点识别

### 6. 反场景
如果研究目标只是“预测某个 tx 会不会成功”或“某条路径会不会消失”，那问题可以退化成：

- 分类
- 回归
- hazard / survival model

这些局部模型在工程上可以有用，但它们只预测单一结果，不重建潜状态，也不直接给出 belief-driven control。  
因此，对本项目主线而言，更准确的定义仍然是：

$$
\text{潜状态后验推断} + \text{belief-state control}.
$$

## 识别问题
### 1. 三种识别层次
本页区分三种不同层次：

#### point identification
若给定观测序列后，某个对象只有唯一可行值，则称其点识别。

#### partial / set identification
若存在一族彼此不同但都与观测一致的结构，则只能集合识别。

#### posterior summary identification
若完整潜状态不能点识别，但某些 summary 在给定模型类下可以被稳定恢复，则把它们视为 posterior summary identification。

### 2. 模型类与 identified set
令

$$
\mathfrak M
=
\left\{
(\mathcal K,\mathcal Q,\theta):
\text{满足证据边界、单调性、稀疏性、方向性与误差率约束}
\right\}.
$$

则对任意 reduced-form summary $\eta=\psi(b_t)$，其 identified set 定义为：

$$
\mathcal I_t(O_{1:t})
=
\left\{
\eta:\exists(\mathcal K,\mathcal Q)\in\mathfrak M
\text{ 与观测一致且 } \eta=\psi(b_t)
\right\}.
$$

若 $\mathcal I_t$ 退化为单点，则可近似视为点识别；否则就应承认它是 set-valued object。

### 3. 对象级识别判断
#### `M_t`
在无原生 Execution Events 的阶段，`M_t` 通常不能被事件重建，只能以后验形式进入：

$$
\Pr(M_t=\text{phase}\mid O_{1:t}).
$$

因此，对 `M_t` 更合理的表述是 posterior identification，而不是 direct observation。

#### `E_t`
`E_t` 在无节点阶段通常表现为 latent graph weak identification。  
logs、traces、gas anomaly、same-path congestion 都只能给出 noisy projection，而不能唯一恢复真实访问结构。

#### `R_t`
`R_t` 更适合被写成 survival / hazard summary identification。  
在很多情形下，点识别的并不是完整 reserve process，而是：

- survival probability
- failure hazard
- admissibility proxy

### 4. 识别失败时的降级规则
以下情况必须触发降级：

1. 某个 proxy 对 out-of-sample 结果没有解释力。  
   它应降级为 exploratory feature，不进入 Bellman 主输入。
2. 某个 provider signal 与落链事实频繁冲突。  
   它应从 transition prior 降级为弱提示。
3. 某个 summary 无法稳定改善 `act / wait / abort` 边界。  
   它不应替代更简单的 baseline。

识别层的任务不是证明“我们已经知道真值”，而是明确：

$$
\text{当前能识别到什么程度，以及哪些结论只在模型类 } \mathfrak M \text{ 内成立。}
$$

## 鲁棒 Bellman
### 1. nominal belief-state reward
令一步 reward 写成：

$$
\rho(s_t,a)=q(s_t,a)\Big(u(s_t)r(s_t,a)\Gamma(s_t,a)-c(a)-(1-u(s_t)r(s_t,a))L(s_t,a)\Big)-\kappa(s_t,a).
$$

这条式子延续了 [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md) 的 reduced-form 分解，但这里把它显式提升为 belief-control 的一步回报核。

### 2. 提升到 belief 上的 action-value
对 belief $b$ 与动作 $a$，定义：

$$
Q_t(b,a)=\int \rho(x,a)b(dx)+\beta\,\mathbb E[V_{t+1}(b_{t+1})\mid b_t=b,a_t=a].
$$

这里的关键变化是：  
控制对象不再是假定已知的单一状态，而是 belief 本身。

### 3. chance-constrained 动作集
由于 reserve / admissibility 等对象本身是 latent，因此动作集不应继续写成“已知真值下的硬约束”，而应写成 belief 下的 chance constraint：

$$
\mathcal A_\epsilon(b)=
\left\{
a:
\Pr_b(\mathrm{admissible}(s_t,a)=1)\ge 1-\epsilon,\ 
\Pr_b(c(s_t,a)\le B_t)\ge 1-\epsilon
\right\}.
$$

其中：

- 第一项约束 admissibility 风险
- 第二项约束 upfront cost / reserve slack 风险

### 4. 鲁棒值函数
在 ambiguity set $\mathfrak M$ 下，鲁棒 Bellman 写成：

$$
V_t^{rob}(b)=
\sup_{a\in\mathcal A_\epsilon(b)}
\inf_{(\mathcal K,\mathcal Q)\in\mathfrak M}
\left\{
\int \rho(x,a)b(dx)+
\beta\,\mathbb E[V_{t+1}^{rob}(b_{t+1})]
\right\}.
$$

这里的意义是：

- 外层 `sup`：searcher 在 belief 下选动作
- 内层 `inf`：对无法点识别的误差核、转移核或 proxy distortion 采取保守处理

如果 ambiguity set 退化为单元素，且 $\epsilon=0$，则：

$$
\mathfrak M=\{(\mathcal K,\mathcal Q)\}
\quad\Longrightarrow\quad
V_t^{rob}(b)=V_t(b),
$$

即鲁棒 Bellman 退化回普通 belief Bellman。

### 5. one-step conservative act 规则
若暂时只做 one-step myopic 判定，可定义：

$$
\inf_{\eta\in\mathcal I_t(O_{1:t})}J_t(\eta,a)\ge 0
\quad\Rightarrow\quad
\text{act}.
$$

这条规则的含义是：  
只有当 identified set 中最保守的可行 summary 仍支持正收益时，才执行 `act`。  
它是本页与 [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md) 之间最直接的桥梁。

## 建议算法
### 1. `M_t`：ordered-state HMM / hidden semi-Markov filtering
适用对象：

- near-head phase posterior
- block-state confidence
- drop risk

输入可用：

- `monadNewHeads`
- `monadLogs`
- receipts continuity
- block continuity

输出应是：

$$
\Pr(M_t=\text{phase}\mid O_{1:t})
$$

以及 phase confidence、drop risk、visible execution confidence。  
如果阶段停留时间的重要性较高，可从 ordered-state HMM 升级到 hidden semi-Markov filtering。

### 2. `E_t`：sparse latent graph inference / variational MAP / message passing
适用对象：

- hotspot score
- overlap score
- route crowding
- conflict density

输入可用：

- trace overlap
- log co-occurrence
- same-block tx cluster
- gas anomaly resonance

推荐起点是稀疏 latent graph inference。  
若图规模较大且需要快速在线更新，可采用 variational MAP 或 message passing 近似。

### 3. `R_t`：hazard model / logistic survival model with monotonicity constraints
适用对象：

- survival probability
- failure hazard
- admissibility proxy

输入可用：

- receipt success / failure
- gas used
- effective gas price
- route size
- execution delay
- revert / fail traces

优先采用带单调性约束的 hazard 或 logistic survival baseline，原因是：

- 方向性约束清晰
- 解释性较强
- 便于与后续强观测样本做 weak-to-strong calibration

### 4. 联合层：Rao-Blackwellized particle filtering 或 variational filtering
当 `M_t`、`E_t`、`R_t` 之间耦合显著时，不应完全分开估计。  
更合理的路线是：

- 对离散有序状态 `M_t` 做精确或半精确 filtering
- 对连续 / 图结构子块做 particle 或 variational approximation
- 从联合 posterior 中再派生 $\tilde p_t,\tilde u_t,\tilde q_t,\tilde r_t,\tilde\kappa_t$

若数据量有限、计算预算紧，可以先做分层近似；若后验耦合很强，则更应保留联合过滤结构。

### 5. 什么时候用哪条路
- 数据少、near-head 强：先做 `ordered-state HMM + hazard baseline`
- traces 丰富、同块交互密：再上 `latent graph inference`
- provider mismatch 大、误差核不稳：启用 `ambiguity-set + robust Bellman`
- 有小样本强观测：做 `weak-to-strong calibration`

### 6. 理论参照
下面这些外部理论只提供数学框架，不替代本项目主线：

- Smallwood and Sondik, POMDP belief-state control: [Operations Research 1973](https://doi.org/10.1287/opre.21.5.1071)
- Kaelbling, Littman, and Cassandra, POMDP survey: [Artificial Intelligence 1998](https://doi.org/10.1016/S0004-3702(98)00023-X)
- Stuart, Bayesian inverse problems: [Acta Numerica 2010](https://doi.org/10.1017/S0962492910000061)
- Arulampalam et al., particle filtering tutorial: [IEEE Transactions on Signal Processing 2002](https://doi.org/10.1109/78.978374)
- Manski, partial identification: [Springer 2003](https://doi.org/10.1007/b97478)

## 与主线的关系
本页服务于下面这条链：

$$
\text{弱观测后验推断}
\to
\text{formal inverse problem}
\to
\text{robust Bellman}
\to
\text{estimation program}.
$$

它具体服务：

- [观测、belief 与 reduced-form 压缩](../20-core-model/21-state-space-and-observation.md)
- [最小 Bellman 系统与状态压缩](../20-core-model/25-minimal-bellman-system.md)
- [弱观测后验推断](./37-weak-observation-posterior-inference.md)
- [统一核下的估计程序](./34-estimation-program.md)

它不替代：

- unified kernel 主模型
- Execution Events 强观测层
- 近头实时 API handover 页

## 下一步
若需要先回到 observed facts、weak proxies 与 posterior objects 的经验组织，请读 [弱观测后验推断](./37-weak-observation-posterior-inference.md)。  
若当前阶段要准备实现输入与访问合同，请继续读 [近头实时数据 API 提供清单](./38-near-head-realtime-api-checklist.md)。  
若当前阶段要安排 filtering、calibration 与算法顺序，请继续读 [统一核下的估计程序](./34-estimation-program.md)。
