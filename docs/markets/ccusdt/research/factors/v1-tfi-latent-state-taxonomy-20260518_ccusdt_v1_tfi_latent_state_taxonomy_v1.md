# CCUSDT TFI Latent State Taxonomy

Status: `20260518_ccusdt_v1_tfi_latent_state_taxonomy_v1`.

Guardrail: `research_only_latent_state_hypotheses_no_execution_recommendation_no_alpha_claim`.

这份报告先不写下一轮程序。目的只有一个：承认 `R5+Q` 不是单一 edge，而是多个潜在微观状态的观测投影；把不同情况拆成数学假设、已有数据证据、可观测代理变量和后续可编程检验。

## 1. 当前困难

现在的问题不是缺一个更精细的 entry 均值估计器。已有严格 as-of entry estimator 已经说明：

$$
\widehat{\mu}_i=\widehat{\mathbb E}[r_i\mid x_i]
$$

本身不够。原因是同一个观测向量

$$
x_i=(cell_i,Q_i,\Delta_i,E_i,Z_i,direction_i)
$$

在不同潜状态下可以有相反收益符号：

$$
\mathbb E[r\mid x,z=\mathrm{release}]>0,
$$

$$
\mathbb E[r\mid x,z=\mathrm{absorption}]<0.
$$

所以真正对象不是单条件均值，而是混合状态：

$$
r_i\mid x_i,\mathcal H_{t_i}
\sim
\sum_{z\in\mathcal Z}\pi_z(t_i)F_z(r\mid x_i),
$$

其中：

$$
\pi_z(t_i)=\mathbb P(z_{t_i}=z\mid \mathcal H_{t_i}).
$$

策略优化最终需要的是：

$$
\mathbb E[r_i\mid x_i,\mathcal H_{t_i}]
=
\sum_z \pi_z(t_i)\mu_z(x_i),
$$

而不是只估：

$$
\mathbb E[r_i\mid x_i].
$$

## 2. 已有数据锚点

最硬的矛盾来自 `2026-05-09` 和 `2026-05-13`。

| date | total target pnl | `10_r5_only` | `01_frames_only` | `11_r5_frames` | entry-estimator high side | entry-estimator reduce side | read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `2026-05-09` | `+69.07` | `+261.65` | `+7.80` | `-200.37` | `-51.71` | `+120.78` | high/`11` 失效，弱侧反而赚钱 |
| `2026-05-13` | `-58.27` | `-110.35` | `-27.71` | `+79.79` | `+44.01` | `-78.35` | `11` 没坏，weak bucket 暴露坏 |

这说明至少有两个不同坏法：

$$
2026\text{-}05\text{-}13:
\quad
\mathrm{weak\ bucket\ overtrade},
$$

$$
2026\text{-}05\text{-}09:
\quad
\mathrm{latent\ regime\ inversion}.
$$

后者更难，因为它不是 entry-local filter 能解决的问题。

另一个锚点来自 entry estimator：

$$
N_{\mathrm{high}}=596,
\quad
G_{\mathrm{high}}=6217.76,
\quad
\bar r_{\mathrm{high}}=5.7432\mathrm{bps},
$$

但：

$$
\min_d G_{\mathrm{high},d}
=G_{\mathrm{high},2026\text{-}05\text{-}09}
=-51.71.
$$

所以 high-quality entry 有明显均值优势，但不是 regime-safe。

第三个锚点来自 momentum conversion 报告。成本大致稳定在 `2bps` 附近，变化主要来自 gross release：

$$
Y=X-C,
$$

而不是成本突然变化。此前二态 release posterior 的粗估结果是：

| segment | weighted mean net | release-state posterior proxy |
| --- | ---: | ---: |
| Fold1 | `-0.9214` | `0.0000` |
| Fold2 | `1.1220` | `0.4430` |
| Fold3 | `3.6909` | `1.0000` |
| OOS `2026-05-16` | `0.2407` | `0.2519` |
| OOS `2026-05-17` | `2.3025` | `0.6990` |

这支持一个判断：TFI 不是稳定 drift，而是 pressure-to-price conversion 在不同状态间切换。

## 3. 潜状态集合

令：

$$
\mathcal Z=
\{
\mathrm{Release},
\mathrm{Absorption},
\mathrm{Exhaustion},
\mathrm{Vacuum},
\mathrm{Chop},
\mathrm{WeakBucketOvertrade}
\}.
$$

这些状态不是为了好看，而是为了回答一个实际问题：

$$
R5+Q
$$

到底意味着“未释放动能”，还是“被吸收动能”。

## 4. 状态一：Release

Release 是我们真正想捕获的状态。

金融含义：

$$
\mathrm{signed\ pressure}
\Rightarrow
\mathrm{quote\ repricing}
\Rightarrow
\mathrm{continuation}.
$$

最小模型：

$$
dM_t=\lambda_t\,dF_t-\kappa_t\,dA_t+\sigma_t\,dW_t,
$$

其中 \(F_t\) 是 signed aggressive pressure，\(A_t\) 是 absorption/replenishment，\(M_t\) 是 mid 或可成交价格。Release 对应：

$$
\lambda_t \uparrow,\quad \kappa_t \downarrow.
$$

可观测特征应当是：

$$
F_t \uparrow,\quad
\frac{dM_t}{dF_t}>0,\quad
\mathrm{opposite\ depth\ depletion}\uparrow,\quad
\mathrm{replenishment}\downarrow.
$$

在这个状态下：

$$
\mathbb E[r\mid 11,z=\mathrm{Release}]>0.
$$

已有支持：`11_r5_frames` 总体最强：

$$
\bar r_{11}=5.1410\mathrm{bps},
\quad
\mathrm{median}_{11}=3.2773\mathrm{bps},
\quad
G_{11}=5850.47.
$$

`2026-05-13` 也是支持样本：当天虽然总亏，但 \(11\) 为正：

$$
G_{11,2026\text{-}05\text{-}13}=+79.79.
$$

## 5. 状态二：Absorption

Absorption 是当前最需要识别的反状态。

表面上它也可能长得像：

$$
R5+Q.
$$

因为有方向压力，也有 stale quote。但 stale 的原因不是“还没释放”，而是“对手方吸收住了”。

数学上：

$$
F_t\uparrow,
\quad
|dM_t|\approx 0,
\quad
\frac{|dM_t|}{|F_t|+\epsilon}\downarrow.
$$

定义一个吸收代理：

$$
A^{proxy}_t
=
\frac{|F_t|}{|dM_t|+\epsilon}.
$$

或者用冲击效率的反向：

$$
\kappa^{impact}_t
=
\frac{d_t\Delta M_t}{|F_t|+\epsilon}.
$$

Absorption 对应：

$$
A^{proxy}_t\uparrow,
\quad
\kappa^{impact}_t\downarrow.
$$

如果 L2 可用，还应当看到：

$$
\mathrm{same\ price\ replenishment}\uparrow,
\quad
\mathrm{opposite\ queue\ not\ depleted},
\quad
\mathrm{spread\ not\ expanding\ in\ signal\ direction}.
$$

在这个状态下：

$$
\mathbb E[r\mid 11,z=\mathrm{Absorption}]<0.
$$

最强怀疑样本是 `2026-05-09`：

$$
G_{11,2026\text{-}05\text{-}09}=-200.37,
$$

且 entry-estimator high side 也亏：

$$
G_{\mathrm{high},2026\text{-}05\text{-}09}=-51.71.
$$

这不像普通 entry 质量问题，更像 latent state inversion。

## 6. 状态三：Exhaustion

Exhaustion 和 absorption 不同。Absorption 是“压力没打动价格”，exhaustion 是“压力已经打完了”。

设过去已经释放的价格位移为：

$$
P^{pre}_t=d_t(M_t-M_{t-L}),
$$

剩余压力为：

$$
F^{rem}_t.
$$

Exhaustion 对应：

$$
P^{pre}_t\uparrow,
\quad
F_t\uparrow,
\quad
\frac{\Delta M_{t,t+h}}{F_t+\epsilon}\downarrow.
$$

也就是看起来很强，但边际转化率已经下降：

$$
\frac{\partial \mathbb E[\Delta M_{t,t+h}]}{\partial F_t}
\downarrow.
$$

它会污染高 \(E,\Delta,Z\) bucket：因为这些变量只能说明压力强，不能说明压力是否还剩下。

一个危险信号是：

$$
E_t\uparrow
\quad\text{but}\quad
q90\ \text{or continuation amplitude does not rise}.
$$

已有弱证据：core quantity 里 naive `high_U` 并不强：

$$
\bar r_{\mathrm{high\_U}}=1.6011\mathrm{bps},
$$

而 `cell_11_low_U` 反而很强：

$$
\bar r_{\mathrm{cell\_11\_low\_U}}=9.0915\mathrm{bps}.
$$

这不一定说明 \(U\) 定义错，但至少说明“压力越大越好”不是可靠叙事；过强压力可能进入 crowded/exhausted 状态。

## 7. 状态四：Liquidity Vacuum

Vacuum 也是 stale quote，但和 absorption 相反。

Vacuum 的金融含义是：

$$
\mathrm{liquidity\ provider\ retreats},
\quad
\mathrm{small\ pressure\ causes\ large\ repricing}.
$$

所以：

$$
Q_t\uparrow
$$

可能既表示 absorption，也可能表示 vacuum。需要拆：

$$
Q_t
=
Q^{absorb}_t+Q^{vacuum}_t.
$$

可观测代理：

$$
\mathrm{top\ depth}\downarrow,
\quad
\mathrm{spread}\uparrow\ \text{or unstable},
\quad
\mathrm{cancel/depletion}\uparrow,
\quad
\frac{|dM_t|}{|F_t|+\epsilon}\uparrow.
$$

这个状态可能解释一部分右尾：

$$
\Pr(r>q_{90}\mid x,z=\mathrm{Vacuum})
\uparrow.
$$

但它也可能 execution-risk 更高，因为 book thin。对研究而言，它是 alpha 状态；对实盘而言，它可能是 capacity/liquidity risk 状态。

## 8. 状态五：Chop / Cost-Eating Noise

Chop 是最普通但最危险的成本状态：

$$
\mathrm{many\ transitions},
\quad
\mathrm{low\ amplitude},
\quad
X<C.
$$

已有 path math 指出一个很重要的事实：Fold1 也有很高 mid transition rate，但 amplitude 不够。也就是说：

$$
\mathrm{transition\ rate}\not\Rightarrow \mathrm{edge}.
$$

真正重要的是：

$$
X_H=X_{\tau_1}+(X_H-X_{\tau_1}),
$$

其中第一次跳动之后是否扩散，最终是否保留 MFE，才决定右尾是否覆盖成本。

Chop 的可观测特征：

$$
\mathrm{mid\ transition\ count}\uparrow,
\quad
\mathrm{first\ transition\ amplitude}\downarrow,
\quad
\mathrm{post\ transition\ release}\downarrow,
\quad
\mathrm{spread/cost}\approx 2\mathrm{bps}.
$$

在这个状态下：

$$
\mathbb E[Y]=\mathbb E[X-C]<0
$$

即使 entry trigger 看起来频繁有效。

## 9. 状态六：Weak-Bucket Overtrade

这个状态不是市场本身，而是策略暴露错误。

定义策略暴露：

$$
G_d=\sum_{i\in d}\gamma_{c_i}r_i.
$$

如果主 cell 有正期望，但弱 cell 暴露太多：

$$
G_{11,d}>0,
\quad
G_{10,d}+G_{01,d}\ll 0,
$$

则：

$$
G_d<0.
$$

`2026-05-13` 就是这个形态：

$$
G_{11}=+79.79,
\quad
G_{10}=-110.35,
\quad
G_{01}=-27.71.
$$

这类问题可以用 entry-quality 或 cell-specific sizing 部分解决，不需要非常复杂的潜变量。

但它不能解释 `2026-05-09`，因为那天是：

$$
G_{11}<0,
\quad
G_{10}>0.
$$

所以 `2026-05-09` 必须由更深的 regime state 解释。

## 10. 一个统一判别框架

下一轮编程不应该直接训练黑盒模型。更稳妥的是先生成一组可解释 latent-state proxy。

### 10.1 Pressure

方向压力：

$$
F_t=d_t\cdot \mathrm{OFI/TFI/MLOFI}_t.
$$

绝对强度：

$$
E_t=|F_t|,
\quad
Z_t=\frac{F_t}{\sqrt{E_t+\epsilon}}.
$$

### 10.2 Conversion

前验价格响应：

$$
K^{pre}_t
=
\frac{d_t(M_t-M_{t-L})}{|F_{t-L,t}|+\epsilon}.
$$

后验检验标签：

$$
K^{post}_t
=
\frac{d_t(M_{t+h}-M_t)}{|F_t|+\epsilon}.
$$

研究时用 \(K^{post}\) 做 label，不可用于 entry。

### 10.3 Absorption

吸收代理：

$$
B_t
=
\frac{|F_t|}{|d_t(M_t-M_{t-L})|+\epsilon}.
$$

L2 版：

$$
B^{L2}_t
=
w_1\mathrm{oppDepth}_t
+w_2\mathrm{oppReplenishment}_t
-w_3\mathrm{oppDepletion}_t.
$$

### 10.4 Exhaustion

末端拥挤：

$$
H_t
=
\frac{d_t(M_t-M_{t-L})}{|F_t|+\epsilon}
\cdot
\mathbf 1\{E_t\ \mathrm{high}\}.
$$

或者：

$$
H_t
=
\mathrm{rank}(P^{pre}_t)
-\mathrm{rank}(K^{recent}_t).
$$

含义是：过去已经走了，但边际冲击效率在下降。

### 10.5 Vacuum

流动性真空：

$$
V_t
=
z(\mathrm{spread}_t)
-z(\mathrm{topDepth}_t)
+z(\mathrm{cancel/depletion}_t)
-z(\mathrm{replenishment}_t).
$$

Vacuum 和 absorption 都可能 stale，但区别是：

$$
\mathrm{Vacuum}: K_t\uparrow,\quad B_t\downarrow,
$$

$$
\mathrm{Absorption}: K_t\downarrow,\quad B_t\uparrow.
$$

### 10.6 Chop

噪声状态：

$$
C_t
=
z(\mathrm{transition\ count})
-z(\mathrm{transition\ amplitude})
-z(\mathrm{post\ transition\ release}).
$$

Chop 的典型形态是“动很多，但每次都不够付成本”。

## 11. 状态预期收益符号

| latent state | observable surface | expected sign for `11` | expected sign for `10` | main risk |
| --- | --- | ---: | ---: | --- |
| Release | high pressure, stale, low replenishment, positive conversion | positive | sometimes positive | right-tail dependence |
| Absorption | high pressure, stale, low price response, high replenishment | negative | mixed | strong signal false positive |
| Exhaustion | high pressure after prior move, falling marginal impact | negative or weak | mixed | buying/selling the last impulse |
| Vacuum | stale/thin book, high impact per flow | positive but jumpy | right-tail positive | execution/capacity risk |
| Chop | many quote/mid transitions, low amplitude | weak/negative | weak/negative | cost eating |
| Weak-bucket overtrade | `11` ok, `10/01` bad | positive | negative | sizing/composition |

This table is the key: the same `R5+Q` surface can map to different \(z\), and therefore different payoff sign.

## 12. How This Explains Existing Contradictions

### `2026-05-13`

Likely diagnosis:

$$
z\approx \mathrm{Release}
\quad\text{for }11,
$$

but:

$$
\gamma_{10},\gamma_{01}\ \text{too large for that day's weak buckets}.
$$

Evidence:

$$
G_{11}=+79.79,
\quad
G_{10}+G_{01}=-138.06.
$$

This is a composition/sizing problem.

### `2026-05-09`

Likely diagnosis:

$$
z\approx \mathrm{Absorption/Exhaustion}
\quad\text{inside high-quality or }11\text{ buckets}.
$$

Evidence:

$$
G_{11}=-200.37,
\quad
G_{10}=+261.65,
$$

and:

$$
G_{\mathrm{high}}=-51.71,
\quad
G_{\mathrm{reduce}}=+120.78.
$$

This is not fixed by ordinary entry quality. It requires regime confirmation.

## 13. Programming Design for Next Round

The next script should not begin as a strategy optimizer. It should create a latent-state diagnostic panel.

Required entry-level rows:

```text
entry_id/date/time/direction/cell/Q_bin/Delta/E/Z/net/gross/cost
pre_pressure
pre_price_displacement
pre_impact_efficiency
absorption_proxy
replenishment_proxy
depletion_proxy
vacuum_proxy
exhaustion_proxy
chop_proxy
post_release_label
post_absorption_label
```

Minimum tests:

1. Split `11` by absorption proxy:

$$
\mathbb E[r\mid 11,B_t\ \mathrm{high}]
\quad\text{vs}\quad
\mathbb E[r\mid 11,B_t\ \mathrm{low}].
$$

2. Split high-quality estimator rows by regime proxy:

$$
\mathbb E[r\mid \mathrm{high},z^{proxy}]
$$

and specifically test whether `2026-05-09` moves from unexplained to high absorption/exhaustion.

3. Measure state inversion:

$$
I_d
=
G_{\mathrm{high},d}-G_{\mathrm{reduce},d}.
$$

We need a prior-only proxy that predicts:

$$
I_{2026\text{-}05\text{-}09}<0,
\quad
I_{2026\text{-}05\text{-}13}>0.
$$

4. Do not promote if the proxy only explains one of those two days.

The minimum success criterion for the next research pass is not total PnL. It is:

$$
\operatorname{sign}(\widehat I_d)
=
\operatorname{sign}(I_d)
$$

for the two contradictory cases, without using future labels.

## 14. Research Stance

The honest current stance is:

$$
\text{entry quality has weak-to-moderate information,}
$$

but:

$$
\text{regime state controls the sign of that information.}
$$

Therefore:

$$
\gamma_i=f(c_i,\widehat\mu_i,\widehat p_i,\widehat L_i)
$$

is still incomplete. A more realistic form is:

$$
\gamma_i
=
\sum_z
\pi_z(t_i)\gamma(c_i,z,\widehat\mu_i,\widehat p_i,\widehat L_i).
$$

This is the right difficulty level. We should not pretend the next step is just a better threshold on \(R5,Q,E,\Delta,Z\). The hard part is estimating:

$$
\pi_{\mathrm{Release}}(t),
\quad
\pi_{\mathrm{Absorption}}(t),
\quad
\pi_{\mathrm{Exhaustion}}(t),
\quad
\pi_{\mathrm{Vacuum}}(t),
\quad
\pi_{\mathrm{Chop}}(t).
$$

Only after that should the work return to sizing/Pareto.

## Related Artifacts

- `docs/markets/ccusdt/v1-tfi-factor-decomposition-20260518_ccusdt_v1_tfi_factor_decomp_v1.md`
- `docs/markets/ccusdt/v1-tfi-entry-estimation-20260518_ccusdt_v1_tfi_entry_estimation_v1.md`
- `docs/markets/ccusdt/v1-tfi-momentum-conversion-first-principles-20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.md`
- `docs/markets/ccusdt/v1-tfi-core-quantity-estimation-20260518_ccusdt_v1_tfi_core_quantity_estimation_v1.md`
