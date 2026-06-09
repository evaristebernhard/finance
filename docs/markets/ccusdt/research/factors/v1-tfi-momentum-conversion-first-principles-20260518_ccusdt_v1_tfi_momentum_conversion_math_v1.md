# CCUSDT TFI 动能转换第一性原理分析

Status: `20260518_ccusdt_v1_tfi_momentum_conversion_math_v1`.

Guardrail: `research_only_momentum_conversion_math_no_execution_recommendation_no_alpha_claim`.

这份报告只解释结构和数学机制，不是执行建议。核心对象是已经互斥分解后的 TFI entry family；`net_median` 已经扣成本，负数不是丢弃理由。

## 1. 变量定义

对每个 entry 定义：

```text
s_i ∈ {-1,+1}                       # entry 方向
X_i = s_i * 10000 * log(M_exit/M_entry)  # gross release，价格是否沿 entry 方向释放
C_i = maker-light cost proxy             # 成本/价差/执行缓冲
Y_i = X_i - C_i                          # net after cost
```

所以策略是否有价值不是问 `median(Y)>0`，而是问：

```text
E[Y | A] = E[X | A] - E[C | A]
        = P(Y>0) * E[Y | Y>0,A] - P(Y<0) * E[-Y | Y<0,A]
```

右尾策略的自然形态是：大量 entry 被成本吃掉，小部分 entry 的释放幅度覆盖全部成本。关键是右尾是否稳定存在、左尾是否失控，而不是中位数是否好看。

## 2. 经验分解：成本基本稳定，变化来自 gross release

| segment | entries | gross_mean_bps | cost_mean_bps | gross_cost_ratio | net_mean_bps | net_median_bps | gt2_rate | cost_hit_rate | pos_over_abs_neg | avg_positive_net_bps | avg_negative_abs_net_bps | breakeven_win_rate_by_magnitude | top10_avg_net_bps | rest90_avg_net_bps | top10_over_abs_left10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fold1 | 780 | 0.8487 | 2.1199 | 0.4003 | -1.2713 | -1.8321 | 0.2474 | 0.7179 | 0.5533 | 5.5827 | 3.9639 | 0.4152 | 10.0471 | -2.5289 | 0.7846 |
| Fold2 | 961 | 3.4763 | 2.0905 | 1.6629 | 1.3858 | -0.6992 | 0.4058 | 0.5567 | 1.4071 | 10.8048 | 6.1143 | 0.3614 | 28.9416 | -1.7079 | 1.4315 |
| Fold3 | 1164 | 4.5447 | 2.0417 | 2.2260 | 2.5031 | -0.3931 | 0.4579 | 0.5163 | 1.6030 | 13.7580 | 8.0402 | 0.3688 | 38.4359 | -1.5123 | 1.5404 |
| OOS_2026_05_16 | 261 | 1.7714 | 2.1251 | 0.8336 | -0.3537 | -1.1584 | 0.4061 | 0.5632 | 0.9283 | 10.4858 | 8.7598 | 0.4552 | 25.3659 | -3.3213 | 0.9041 |
| OOS_2026_05_17 | 199 | 3.7992 | 2.1301 | 1.7836 | 1.6691 | 1.2687 | 0.4774 | 0.4774 | 1.5385 | 9.1242 | 6.4923 | 0.4157 | 22.1233 | -0.6163 | 1.0714 |

第一层结论很硬：`C` 一直在 2.0bps 左右，状态切换主要不是成本突然变贵，而是 `X` 的转换效率变了。Fold1 的 gross/cost 只有吸收态水平；5/16 已经接近 break-even；5/17 的 gross/cost 重新大于 1，说明同一类 TFI 脉冲又能转成真实价格位移。

## 3. 第一性原理模型：TFI 不是动能，TFI 是待转换的压力

把 TFI 看成 signed latent demand impulse。价格不是因为有 TFI 就动，而是因为 TFI 对应的主动流穿透了可恢复流动性：

```text
dP_t = λ_t dQ_t - κ_t dR_t + σ_t dW_t

Q_t: signed aggressive demand / inventory transfer
R_t: maker replenishment, passive absorption, opposing inventory
λ_t: impact per unit flow，近似 inverse resilient depth
κ_t: absorption/replenishment strength
```

entry 的金融含义可以写成一个转换不等式：

```text
E[X_H | A_t] ≈ E[∫_0^H λ_{t+u} dQ_{t+u} | A_t]
            - E[∫_0^H κ_{t+u} dR_{t+u} | A_t]

entry worthiness: E[X_H | A_t] > E[C_t]
```

Fold1 失败不是因为结构没有金融意义，而是 `λ dQ` 被 `κ dR` 吃掉：gross release 只有成本的三分之一到一半。Fold3/5-17 有利润，是因为同样的 TFI family 落在 maker 撤退、queue stale、或 replenishment 弱的状态里，`λ` 上升或 `κ` 下降，冲击转成了位移。

## 4. 非线性阈值：肥尾从哪里来

如果把盘口看成有恢复力的队列系统，动能转换更像 first-passage problem，而不是线性回归：

```text
B_u = J_u - A_u
J_u = cumulative signed impulse from TFI-side demand
A_u = cumulative absorption / replenishment / opposing inventory
D_u = effective resilient depth until next repricing

τ = inf{u <= H : B_u > D_u}
X_H ≈ α (B_τ - D_τ)^+ + β * repricing_cascade_τ,H + ε_H
```

这会天然产生右尾：当 `B_u` 没过 `D_u`，结果只是成本摩擦和小幅来回跳；一旦过阈值，best quote 被穿透、maker 撤单/补价、后续交易者追随，`X_H` 对 `B-D` 呈凸函数。于是 Fold1 到 Fold3 的差异，不需要假设信号本身变了，只需要 `D` 或 `A` 略变，就能把同一批 TFI entry 从成本噪声推到释放态。

这也解释为什么 top10 很重要。真正的数学对象是：

```text
E[Y] = q * W - (1-q) * L
q* = L / (W + L)

W = E[Y | Y>0], L = E[-Y | Y<0]
```

如果实际 win_rate 低于 `q*`，结构被成本和左尾吃掉；如果 win_rate 或 W 上升，哪怕 median 仍负，期望也可以转正。报告表里的 `breakeven_win_rate_by_magnitude` 就是这个 `q*`。

## 5. 路径分解：mid transition 很多，但 amplitude 才是核心

| segment | mid_transition_rate | mid_transition_count_mean | first_mid_hold_mean_sec | first_mid_gross_mean_bps | post_first_mid_release_mean_bps | first_mid_capture_ratio | mfe_mean_bps | mae_mean_bps | winner_final_over_mfe_mean | adverse_over_cost_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fold1 | 0.9436 | 6.6333 | 7.7900 | 0.3396 | 0.5599 | 0.4001 | 3.1081 | -2.0566 | 0.8522 | 1.1749 |
| Fold2 | 0.9521 | 9.7222 | 7.5422 | 1.2134 | 2.4377 | 0.3490 | 8.2272 | -3.4383 | 0.8469 | 1.9430 |
| Fold3 | 0.9665 | 11.3918 | 6.1777 | 1.2359 | 3.4664 | 0.2719 | 11.1810 | -5.0172 | 0.8255 | 2.8047 |
| OOS_2026_05_16 | 0.9387 | 9.0651 | 7.5966 | 0.4820 | 1.4051 | 0.2721 | 7.7847 | -5.0602 | 0.8396 | 2.8795 |
| OOS_2026_05_17 | 0.9397 | 7.7186 | 8.8332 | 1.3320 | 2.7110 | 0.3506 | 8.1090 | -2.6967 | 0.8649 | 1.7958 |

这里最重要的点：Fold1 也有很高的 mid/quote transition rate，所以“发生过跳动”不是 edge。edge 是 `X_H = X_{τ1} + (X_H - X_{τ1})` 里的幅度项：第一次跳动有多大，跳动之后有没有继续扩散，最后保留了多少 MFE。吸收态里 transition 可以频繁发生，但大多只是来回重定价；释放态里 transition 才会变成连续 displacement。

## 6. 隐状态混合：不是 alive/dead，而是 release probability

用 Fold1 作为 absorption state，用 Fold3 作为 release state，对 locked weighted strategy 建一个最小二态模型：

```text
Y | signal ~ π_t * Release + (1 - π_t) * Absorption
m_t = E[Y_t | signal]
π_t = (m_t - m_absorb) / (m_release - m_absorb)
```

这里 `m_absorb=-0.9214` bps，`m_release=3.6909` bps。break-even 所需 `π>0.1998`；要让 weighted mean 超过 2bps，约需 `π>0.6334`。

| segment | weighted_mean_net_bps | total_weighted_net_bps | weighted_gt2_rate | cost_hit_rate | release_state_pi_from_weighted_mean | pos_over_abs_neg | top10_over_abs_left10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Fold1 | -0.9214 | -420.1420 | 0.2873 | 0.6831 | 0.0000 |  |  |
| Fold2 | 1.1220 | 720.3126 | 0.4081 | 0.5592 | 0.4430 |  |  |
| Fold3 | 3.6909 | 3168.6474 | 0.4843 | 0.4950 | 1.0000 |  |  |
| OOS_2026_05_16 | 0.2407 | 39.2337 | 0.4141 | 0.5613 | 0.2519 | 1.0570 | 1.0822 |
| OOS_2026_05_17 | 2.3025 | 280.9097 | 0.5123 | 0.4508 | 0.6990 | 1.8029 | 1.4833 |

这个模型解释了 5/16 和 5/17 的差异：5/16 的 `π≈0.2519`，高于 break-even 但远低于 2bps mean 阈值，所以表现为小正或接近吸收；5/17 的 `π≈0.6990`，已经超过 2bps mean 阈值，右尾/中部释放都回来了。它不是简单“一波流已经没了”，更像脉冲式 regime。

## 7. 互斥结构的金融含义

| segment | membership_set | entries | gross_mean_bps | cost_mean_bps | net_mean_bps | net_median_bps | gt2_rate | total_net_bps | top10_avg_net_bps | rest90_avg_net_bps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Fold1 | tfi_follow_flat+tfi_long_flat+tfi_event_active | 33 | 3.2713 | 2.0438 | 1.2274 | -0.8306 | 0.3939 | 40.5049 | 13.3166 | -0.4400 |
| Fold1 | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 24 | 3.4193 | 2.2309 | 1.1883 | 2.5750 | 0.5417 | 28.5194 | 8.6650 | 0.1202 |
| Fold1 | tfi_long_flat | 27 | -0.8864 | 1.9506 | -2.8370 | -2.0059 | 0.1111 | -76.5982 | 6.5482 | -4.0101 |
| Fold1 | tfi_follow_flat+tfi_long_flat | 342 | 0.7032 | 2.1229 | -1.4198 | -1.8402 | 0.2398 | -485.5573 | 11.0601 | -2.8425 |
| Fold1 | tfi_follow_flat+tfi_short_flat | 354 | 0.7215 | 2.1295 | -1.4080 | -1.8406 | 0.2316 | -498.4496 | 8.5291 | -2.5330 |
| Fold2 | tfi_follow_flat+tfi_short_flat | 515 | 3.7108 | 2.0792 | 1.6315 | -0.6788 | 0.4388 | 840.2323 | 30.1716 | -1.5738 |
| Fold2 | tfi_follow_flat+tfi_long_flat | 298 | 3.3117 | 2.1133 | 1.1984 | -1.1600 | 0.3456 | 357.1123 | 26.8358 | -1.6715 |
| Fold2 | tfi_follow_flat+tfi_long_flat+tfi_event_active | 48 | 6.4872 | 2.1454 | 4.3418 | 3.1040 | 0.5625 | 208.4088 | 40.2990 | 0.1608 |
| Fold2 | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 65 | 2.3583 | 2.0620 | 0.2964 | -0.5152 | 0.4154 | 19.2630 | 15.5002 | -1.5386 |
| Fold2 | tfi_long_flat | 35 | -0.6245 | 2.0406 | -2.6651 | -2.1823 | 0.2000 | -93.2788 | 15.4827 | -5.0068 |
| Fold3 | tfi_follow_flat+tfi_short_flat | 559 | 4.0249 | 2.0414 | 1.9835 | -0.5124 | 0.4526 | 1108.7730 | 31.5559 | -1.3089 |
| Fold3 | tfi_follow_flat+tfi_long_flat | 390 | 4.2218 | 2.0602 | 2.1615 | -0.6752 | 0.4385 | 843.0004 | 40.7772 | -2.1291 |
| Fold3 | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 114 | 7.8982 | 2.0179 | 5.8804 | 2.8471 | 0.5175 | 670.3600 | 58.9129 | -0.3588 |
| Fold3 | tfi_follow_flat+tfi_long_flat+tfi_event_active | 66 | 4.9561 | 1.9579 | 2.9983 | 2.2486 | 0.5000 | 197.8854 | 34.6988 | -0.7628 |
| Fold3 | tfi_long_flat | 35 | 4.7475 | 2.0738 | 2.6736 | 0.9939 | 0.4857 | 93.5768 | 41.4786 | -2.3335 |
| OOS_2026_05_16 | tfi_follow_flat+tfi_long_flat+tfi_event_active | 8 | 7.9032 | 2.0098 | 5.8934 | 1.5256 | 0.5000 | 47.1470 | 65.8943 | -2.6782 |
| OOS_2026_05_16 | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 17 | 3.3662 | 1.9809 | 1.3853 | -0.6831 | 0.4118 | 23.5499 | 13.6152 | -0.2454 |
| OOS_2026_05_16 | tfi_long_flat | 15 | 1.8163 | 2.3661 | -0.5498 | -0.1680 | 0.4667 | -8.2477 | 15.2484 | -2.9803 |
| OOS_2026_05_16 | tfi_follow_flat+tfi_short_flat | 111 | 1.7064 | 2.0653 | -0.3589 | -1.1576 | 0.3964 | -39.8364 | 20.2153 | -2.8527 |
| OOS_2026_05_16 | tfi_follow_flat+tfi_long_flat | 110 | 1.1384 | 2.1831 | -1.0447 | -1.3300 | 0.4000 | -114.9157 | 28.2950 | -4.3046 |
| OOS_2026_05_17 | tfi_follow_flat+tfi_long_flat | 72 | 4.3214 | 2.1244 | 2.1970 | 2.9550 | 0.5278 | 158.1841 | 16.2947 | 0.4348 |
| OOS_2026_05_17 | tfi_follow_flat+tfi_short_flat | 104 | 3.2161 | 2.1369 | 1.0793 | -0.2752 | 0.4135 | 112.2438 | 25.7085 | -1.8339 |
| OOS_2026_05_17 | tfi_follow_flat+tfi_short_flat+tfi_short_stale25+tfi_event_active | 12 | 7.3161 | 2.1137 | 5.2024 | 7.5700 | 0.6667 | 62.4289 | 14.4472 | 3.3535 |
| OOS_2026_05_17 | tfi_follow_flat+tfi_long_flat+tfi_event_active | 9 | 7.5557 | 2.1717 | 5.3840 | 3.7240 | 0.6667 | 48.4564 | 18.4717 | 3.7481 |
| OOS_2026_05_17 | tfi_long_flat | 2 | -22.6857 | 1.8955 | -24.5812 | -24.5812 | 0.0000 | -49.1625 | -1.1627 | -47.9998 |

互斥 bucket 的意义不是互相替代，而是把同一个 signed pressure 拆成不同流动性状态。`follow+long/short` 是 broad latent pressure；`+event_active` 或 `+stale25` 是释放条件更强的子状态。Fold3 里这些桶都可贡献，说明它们不是必须互斥地只选一个，而是同一族 pressure-release 机制在不同状态投影上的分解。

## 8. 实盘前的数学监控逻辑

如果明天实盘，不能问“这个结构昨天活不活”，要在线估计 `π_t` 和 `ρ_t=E[X]/E[C]`：

```text
rolling window W:
ρ_t = mean_W(X_i) / mean_W(C_i)
r_t = sum_W(Y_i^+) / |sum_W(Y_i^-)|
b_t = P_W(Y_i > 2bps)
a_t = top10_W(Y) / |left10_W(Y)|

logit(π_t) = logit(π_{t-1}) + log f_release(z_i) - log f_absorb(z_i)
z_i = winsorized [X_i, 1{Y_i>2}, Y_i^+, Y_i^-, X_i-X_{τ1}]
```

最小可执行判据应当是 state sizing，而不是把 entry family 丢掉：

- `π_t < 0.1998`：吸收态，停或极小探针。
- `0.1998 <= π_t < 0.6334`：正 EV 但不足 2bps mean，低权重收集 regime evidence。
- `π_t >= 0.6334` 且 `ρ_t>1`、`r_t>1`：释放态，可以按互斥 bucket 下单/加权。

这也回答“哪些指标达到什么值值得 entry”：不是 `net_median>0`，而是互斥结构本身作为 candidate，叠加当下 release-state posterior。中位数负只说明成本打掉了多数小波动；只要右尾和正负总额比仍覆盖左侧，它仍然是可用的右尾捕获结构。

## Outputs

- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_momentum_conversion_segments_20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_momentum_conversion_buckets_20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_momentum_conversion_weighted_regime_20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.csv`
- `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\date\ccusdt_v1_tfi_momentum_conversion_summary_20260518_ccusdt_v1_tfi_momentum_conversion_math_v1.json`
