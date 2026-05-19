# MON/USDC V1 数学化因子建模草案

状态: 2026-05-11。本文是研究笔记，不是交易规则，也不是套利系统设计。

## 0. 边界

外部 `external/docs` 里那套模型主要讨论 AMM/MEV 的可执行机会。我们当前机器和数据路径不适合做 near-head arbitrage，也不应该把它照搬成抢跑系统。本笔记只吸收它的数学结构:

$$
\text{gross opportunity}
\to
\text{inclusion / survival / friction / cost filter}
\to
\text{act / wait / abort}
$$

在 MON/USDC 当前阶段，我们要研究的是更弱、更慢、但更可验证的问题:

$$
\text{一个 swap event 是否改变了未来一小段价格路径的条件分布？}
$$

更具体地说，不先问“事件后固定 5m/1h 会不会涨”，而先问:

$$
\text{事件之后是否出现过足够覆盖成本和风险的可执行路径？}
$$

## 1. 从外部文档吸收的对象

外部文档里的 unified kernel 写成:

$$
s_t=(G_t,M_t,C_t,R_t,E_t,F_t),
\qquad
a_t=(P_t,x_t,\ell_t,\pi_t,\overline F_t,d_t).
$$

对我们当前 MON/USDC 历史研究来说，可以先压缩成:

| 外部对象 | 在套利系统里的含义 | 当前低算力研究里的可用投影 |
| --- | --- | --- |
| $G_t$ | AMM 图、池状态、价格几何 | 多池 VWAP、池内价格、pool family、active liquidity / reserve proxy |
| $M_t$ | 提交态、leader、verification | 暂不做 near-head，只用落链 block/order facts |
| $C_t$ | 竞争流、传播环境 | 同块事件密度、gas regime、route crowding proxy |
| $R_t$ | reserve / survival | receipt success、gas used、失败/错误行过滤 |
| $E_t$ | 热点访问、冲突、重执行 | same-block、same-tx、tx path、trace/path proxy |
| $F_t$ | base fee 状态 | base fee、priority fee、gas/base fee ratio |

这意味着我们不复刻完整 Bellman，只做 reduced-form:

$$
z_e=\psi(O_{\le t_e})
$$

其中 $e$ 是事件，$O_{\le t_e}$ 是事件发生前和当下可观测事实，$z_e$ 是该事件的状态摘要。

## 2. 价格参考: VWAP 不是敌人

令第 $m$ 分钟所有 clean swap 的 MON 数量为 $Q_m^{base}$，USDC 名义成交为 $Q_m^{quote}$。当前 minute VWAP 是:

$$
P_m^{vwap}
=
\frac{Q_m^{quote}}{Q_m^{base}}.
$$

如果该分钟无成交，则使用前值:

$$
P_m=P_{m-1}.
$$

VWAP 的作用不是构造 alpha，而是给事件后路径一个相对稳健的 fair-price reference。单笔 swap 价格会被滑点、路由、dust event 污染；VWAP 把分钟内成交压成一个更稳定的价格锚。

真正的问题不是 VWAP，而是 label。如果只看:

$$
R_{e,H}
=
\log P_{m_e+1+H}
-
\log P_{m_e+1},
$$

那它只是固定 horizon 点到点收益，可能抹掉波动路径。

## 3. 路径标签，而不是单点收益

对事件 $e$，设入场参考分钟为:

$$
m_0=m_e+1.
$$

设价格路径的 log return 为:

$$
r_e(u)=\log P_{m_0+u}-\log P_{m_0},
\qquad
u=1,\dots,H.
$$

事件方向记为:

$$
d_e=
\begin{cases}
+1, & \text{buy\_base},\\
-1, & \text{sell\_base}.
\end{cases}
$$

方向对齐后的路径是:

$$
s_e(u)=d_e\,r_e(u).
$$

于是定义:

$$
\operatorname{MFE}_{e,H}=\max_{1\le u\le H}s_e(u),
\qquad
\operatorname{MAE}_{e,H}=\min_{1\le u\le H}s_e(u),
$$

以及固定到期收益:

$$
R^{side}_{e,H}=s_e(H).
$$

注意: `MFE` 不应直接当作 alpha target，因为它带有事后最优出场信息。它更适合做“路径是否给过机会”的诊断。真正更接近交易的问题是 hitting-time label。

## 4. Triple-barrier label

设事件前的短周期 realized volatility 为:

$$
\sigma_{e,\tau}
=
\left(
\sum_{j=1}^{\tau}
(\Delta \log P_{m_e-j})^2
\right)^{1/2}.
$$

设总成本阈值为:

$$
C_e
=
2f
+2\eta
+g_e
+\rho_e,
$$

其中:

- $f$ 是 one-way pool fee bps 的小数形式。
- $\eta$ 是 one-way slippage stress。
- $g_e$ 是 gas/notional proxy。
- $\rho_e$ 是风险缓冲，可先设为 volatility buffer。

定义动态止盈止损:

$$
B_e^+=C_e+\alpha\sigma_{e,\tau},
\qquad
B_e^-=\beta\sigma_{e,\tau}+C_e.
$$

定义首次触达时间:

$$
\tau_e^+
=
\inf\{u\le H: s_e(u)\ge B_e^+\},
$$

$$
\tau_e^-
=
\inf\{u\le H: s_e(u)\le -B_e^-\}.
$$

路径标签:

$$
Y_e=
\begin{cases}
+1, & \tau_e^+<\tau_e^-,\\
-1, & \tau_e^-<\tau_e^+,\\
0, & \tau_e^+,\tau_e^-\text{ 均未触达}.
\end{cases}
$$

这比固定 `fwd_5m` 更接近真实问题，因为它问的是:

$$
\text{这段路径是否先给了足够覆盖成本的有利波动？}
$$

## 5. 先建模可交易性，再建模方向

外部 Bellman 文档里的一步收益可以局部写成:

$$
J_t(a)
=
q_t(a)
\left[
u_t r_t(a)\Gamma_t(a)
-c_t(a)
-(1-u_t r_t(a))L_t(a)
\right]
-\kappa_t(a).
$$

我们当前不估计真实 $q_t,u_t,r_t,\kappa_t$。但可以把它降级成历史事件问题:

$$
\Pr(Y_e=+1\mid z_e)
-
\lambda_-\Pr(Y_e=-1\mid z_e)
-
\lambda_0\Pr(Y_e=0\mid z_e)
>
0.
$$

因此研究顺序应该是:

1. 先估计 `tradable regime`:
   $$
   T_e=\mathbf 1\{Y_e\ne 0,\ \operatorname{MFE}_{e,H}>C_e\}.
   $$
2. 再在 $T_e=1$ 的子样本里估计方向:
   $$
   D_e=\Pr(Y_e=+1\mid T_e=1,z_e).
   $$

这对应交易直觉: 稳定系统里大多数时候应该 `abort` 或 `wait`，不是强行预测方向。

## 6. 无量纲因子族

当前裸因子太平庸，主要因为它们没有除以市场状态。下一版应优先构造无量纲量。

### 6.1 事件冲击强度

令事件 quote notional 为 $Q_e$，过去 $\tau$ 分钟 quote volume 为 $V_{e,\tau}$:

$$
Z^{flow}_{e,\tau}
=
\frac{d_e Q_e}{V_{e,\tau}+\epsilon}.
$$

再按波动率归一:

$$
Z^{shock}_{e,\tau}
=
\frac{d_e Q_e}{(V_{e,\tau}+\epsilon)\sigma_{e,\tau}}.
$$

解释: 同样 10k USDC，在安静市场和高成交市场不是同一个事件。

### 6.2 流动性压力

如果有 active liquidity 或 reserve proxy $L_e$:

$$
Z^{liq}_{e}
=
\frac{Q_e}{L_e+\epsilon}.
$$

如果只有 swap logs，可先用最近窗口成交承载力替代:

$$
\widehat L_{e,\tau}
=
\operatorname{median}_{j\le\tau}(Q_j^{quote}),
\qquad
Z^{liqproxy}_{e,\tau}
=
\frac{Q_e}{\widehat L_{e,\tau}+\epsilon}.
$$

### 6.3 池间错位

设事件所在池价格为 $P_{p,m}$，多池 fair VWAP 为 $P_m^{fair}$:

$$
\delta_{p,m}
=
\log P_{p,m}-\log P_m^{fair}.
$$

方向对齐的错位:

$$
Z^{disloc}_{e}
=
d_e\delta_{p_e,m_e}.
$$

若 $Z^{disloc}_e>0$，表示事件方向把该池推向相对更贵的一侧，后续更可能均值回归；若 $Z^{disloc}_e<0$，可能是相对便宜池被买入，反而可能有延续。

### 6.4 池间集中与领导池

令第 $m$ 分钟池 $p$ 的 quote share 为 $w_{p,m}$:

$$
HHI_m=\sum_p w_{p,m}^2.
$$

高 $HHI$ 表示价格发现集中在单池，低 $HHI$ 表示多池分散。可构造:

$$
Z^{leader}_{e}
=
\mathbf 1\{p_e=\arg\max_p w_{p,m_e-\tau:m_e}\}.
$$

它回答: 事件发生在主导价格发现的池，还是尾部池。

### 6.5 拥挤和冲突 proxy

同块/同分钟事件密度:

$$
Z^{crowd}_{e}
=
\log(1+N_{\text{same block}})
+\log(1+N_{\text{same minute}}).
$$

gas 压力:

$$
Z^{gas}_{e}
=
\frac{\text{gas\_cost}_e}{Q_e+\epsilon}.
$$

这类因子大概率不是方向 alpha，而是 `abort / wait` 过滤器。

### 6.6 记忆核订单流

裸 signed flow 太短视。可以定义指数衰减冲击:

$$
I_{e,\tau}
=
\sum_{i:t_i<t_e}
d_i \min(Q_i,Q_{\max})
\exp\left(-\frac{t_e-t_i}{\tau}\right).
$$

并标准化:

$$
Z^{impulse}_{e,\tau}
=
\frac{I_{e,\tau}}{\sum_{i:t_i<t_e}Q_i\exp(-(t_e-t_i)/\tau)+\epsilon}.
$$

这可以区分“孤立大单”和“连续同向冲击”。

## 7. 因子不是直接预测收益，而是解释路径类型

每个事件先分四类:

| 路径类型 | 数学条件 | 直觉 |
| --- | --- | --- |
| continuation | $\tau^+<\tau^-$ 且 $d_eR_H>0$ | 事件方向延续 |
| reversal | $\tau^-<\tau^+$ 或短期同向后长期反向 | 事件冲击被回补 |
| volatility-only | `MFE` 和 `MAE` 都大，但到期收益小 | 有波动但方向难 |
| dead-zone | `MFE<C_e` 且 `MAE` 小 | 稳定无交易价值 |

因子研究目标应变成:

$$
\Pr(\text{path type}\mid z_e),
$$

而不是只估:

$$
\mathbb E[R_H\mid z_e].
$$

## 8. 拟合方式

第一版不需要复杂模型，先用透明模型:

1. 按日期时间切分 `discovery / validation / forward`。
2. 先单因子 monotonic sanity check。
3. 再做带交互的 logistic / ordinal model:

$$
\Pr(Y_e=+1\mid z_e)
=
\operatorname{logit}^{-1}
\left(
\beta_0
+\beta_1 Z^{shock}
+\beta_2 Z^{disloc}
+\beta_3 Z^{liq}
+\beta_4 Z^{crowd}
+\beta_5 Z^{vol}
+\beta_{12}Z^{shock}Z^{vol}
+\beta_{23}Z^{disloc}Z^{liq}
\right).
$$

4. 再考虑 GBDT，但只作为非线性发现工具，不作为可信结论。
5. 所有结论必须过 forward split 和日期稳定性。

## 9. 失败标准

一个因子族应被降级，如果:

1. 只在 discovery 有效，validation/forward 消失。
2. 只解释 `gas_over_quote_abs` 这种机械成本关系。
3. 只在极小 quote notional 样本有效。
4. 按日期分组后由少数日期贡献全部收益。
5. 换成 triple-barrier label 后信号消失。
6. 对 `dead-zone` 的过滤没有提升。

## 10. 下一步实现清单

先不写大模型，按下面顺序推进:

1. 在现有 enrichment panel 上补充路径 label:
   `MFE/MAE/triple_barrier/time_to_hit/dead_zone`。
2. 构造无量纲因子:
   `shock_over_volume`、`shock_over_vol`、`liquidity_pressure`、`dislocation_z`、`crowding`、`impulse_flow`。
3. 输出一张 path-type summary:
   按 pool、regime、quote bucket、vol bucket、date 交叉。
4. 先研究 `tradable regime filter`，再研究方向。
5. 保留 VWAP 作为 fair price reference，但不把固定 horizon return 当最终策略标签。

本质上，下一版要从:

$$
\text{static factor} \to \text{fixed future return}
$$

升级为:

$$
\text{state-normalized event shock}
\to
\text{stopping-time path label}
\to
\text{act / wait / abort filter}.
$$
