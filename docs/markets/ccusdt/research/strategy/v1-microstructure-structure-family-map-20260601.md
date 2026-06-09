# CCUSDT Microstructure Structure Family Map

Status: `20260601_structure_family_map_v0_1`.

Guardrail:
`research_only_structure_map_no_strategy_promotion_no_runtime_label_dependency`.

本文的目标不是继续调参，也不是把新因子硬塞回旧四象限。本文把旧四象限重新定义为一个已经发现的结构族，并建立一套可以继续扩展的结构族语言：

```text
factor primitive
-> composition form
-> market mechanism
-> release / decay / cost role
-> strategy component
```

核心判断：

```text
四象限是一种结构族，不是策略全集。
```

它抓住的是一类 `active-flow stale-release` 现象；后续 OFI、MLOFI、depth、spread、frames、past_event、trade_arrival_alignment 等因子，不应该都被理解成“四象限的补丁”。它们在不同结构族里可以承担完全不同的角色：entry alpha、cost filter、decay-risk guard、exit-wait signal、capacity sizing input，或者只是 control。

## 1. 旧四象限到底是什么

旧四象限由两层组成。

第一层是触发层。它不是四象限本身，而是从主动成交流和价格未释放程度里挑出一些候选时刻：

```text
TFI >= 1                         -> long pressure
TFI <= -1                        -> short pressure
past_event_25_bps close to zero  -> price has not already moved much
frames_since_mid_change >= 25    -> stale / latent-pressure state
trade_window_count > 0           -> active trade event exists
```

对应的旧触发类包括：

```text
tfi_follow_flat
tfi_short_flat
tfi_long_flat
tfi_short_stale25
tfi_event_active
```

第二层才是四象限。设：

```text
A_t = 1{R5_t >= 1}
B_t = 1{frames_since_mid_change_t >= threshold}
C_t = (A_t, B_t)
```

则：

```text
00_none        = not R5, not stale
10_r5_only     = R5 only
01_frames_only = stale only
11_r5_frames   = R5 and stale
```

其中 `R5` 必须是 runtime-safe 的 closed-entry memory：只能使用当前 entry timestamp 之前已经闭合的历史 entry outcome，不能使用未来 entry、future return、MFE、MAE 或 scored entries。

旧四象限的经济含义不是“两个布尔变量很神奇”，而是：

```text
主动成交压力已经出现
价格未必已经充分响应
盘口停滞可能表示潜在压力
最近闭合路径记忆给出结构质量估计
gamma 把结构质量转成 sizing
```

因此旧四象限可以写成：

```text
S_1(t) = trigger_TFI(t) * memory_R5(t) * stale_state(t)
side_1(t) = sign(TFI_t) or trigger-defined side
exposure_1(t) = base_weight_t * gamma_{C_t}
```

这就是 `S1 active-flow stale-release` 结构族。

### 1.1 成功点

旧四象限有效，说明这些条件组合确实捕捉到一种 release 机制：

```text
E[release | C_t] differs across cells.
```

特别是 `R5` 和 `frames` 的组合，把“近期路径记忆”和“当前盘口停滞”叠在一起。它不是单纯 TFI，也不是单纯 staleness。

已有 handoff 中的四象限结果显示，`11_r5_frames` 在旧 zero-fee walk-forward cell stats 中有更高 mean：

```text
11_r5_frames entries=171 exposure=272.0000 total=1971.8641 mean=7.2495 positive_days=9/9
```

这说明 `R5 + stale` 不是噪声组合。

### 1.2 失败点

旧四象限的问题也很清楚：它把不同任务绑在同一个 cell 里。

```text
entry trigger
sizing gamma
fixed60 exit
taker crossing cost
tail risk
```

这些不应该由同一个 `C_t` 同时决定。典型失败案例是 `2026-05-09 / entry_row=1615412 / 11_r5_frames / short`：

```text
MFE=+12.5612 bps at 4.7051s
R_60=-27.8923 bps
decay_60=40.4535 bps
exposure=8
```

这不是普通 bad entry。它说明：

```text
结构能 release
但 fixed60 hold 和大 gamma 把 release 后的 decay 放大成左尾
```

因此旧四象限应保留为结构族，而不应继续作为唯一策略语言。

## 2. 结构族通用框架

设 `X_t` 是 exchange-visible filtration `F_t` 下可观测的 runtime-safe 状态：

```text
X_t = {
  TFI, R5, R10, Delta, Energy, Z,
  spread, depth, QI,
  OFI, MLOFI,
  frames_since_mid_change,
  past_event,
  trade_arrival_alignment,
  ...
}
```

一个结构族不是一个单因子，而是一组机制条件：

```text
S_k(t) = trigger_k(X_t) * confirmation_k(X_t) * cost_gate_k(X_t)
```

方向由该结构族自己的方向规则给出：

```text
side_k(t) = direction_rule_k(X_t)
```

结构族角色必须显式标注：

```text
role_k in {entry, admission, exit, sizing, risk, control}
```

每个结构族必须拆开看四类证据：

```text
release evidence
decay evidence
executable cost evidence
tail / capacity evidence
```

不要再用单个 `60s return` 判定结构好坏。更合适的路径对象是：

```text
Release_t = max favorable mid excursion in [0, tau_r]
Terminal_t = signed mid return at tau
Decay_t = Release_t - Terminal_t
Executable_t = top-of-book taker entry + exit return
```

一个结构可能只提升 release，但不提升 executable；这种结构不应该被删除，而应该被归类为 `release-only` 或 `exit-wait` 候选。

## 3. 首版结构族 taxonomy

### S1 active-flow stale-release

市场机制：

```text
主动成交流已经有方向，但价格还没有充分释放；盘口停滞和闭合路径记忆共同提示潜在 release。
```

数学定义：

```text
trigger_1(t) = 1{|TFI_t| >= threshold and past_event_25_bps is small}
memory_1(t)  = 1{R5_t >= 1} or ramp(Delta/Energy/Z)
stale_1(t)   = 1{frames_since_mid_change_t >= threshold}
S_1(t)       = trigger_1(t) * g(memory_1(t), stale_1(t))
side_1(t)    = sign(TFI_t)
```

关键因子：

```text
TFI
R5/R10
Delta/Energy/Z
frames_since_mid_change
past_event_25_bps
```

为什么可能有效：

```text
主动流提供方向；
past_event 小表示还没追完；
frames 高表示价格停滞或潜压；
closed memory 表示类似结构最近是否释放过。
```

失败模式：

```text
release 后 decay 快；
R5 ratio 忽略绝对能量；
gamma 把左尾放大；
spread/crossing cost 没被 cell 本身控制；
同一个 cell 混合真潜压、假真空和高成本状态。
```

runtime-safe 边界：

```text
可 runtime-safe，但 R5 必须来自 Bot-owned closed-entry state。
不可读取 date/scored_entries/future labels。
```

策略角色：

```text
entry + sizing base structure
```

### S2 flow-book confirmation

市场机制：

```text
主动成交流和被动盘口流同向时，价格冲击更可能持续；如果 TFI 强但 OFI/MLOFI 不确认，主动流可能被吸收。
```

数学定义：

```text
trigger_2(t)      = 1{|TFI_t| >= threshold}
confirmation_2(t) = 1{sign(TFI_t) = sign(OFI_t or MLOFI_t)}
S_2(t)            = trigger_2(t) * confirmation_2(t) * cost_gate(t)
side_2(t)         = sign(TFI_t)
```

关键因子：

```text
TFI
OFI_L1
MLOFI_L1/L5/L25
depletion / replenishment / withdrawal
spread
```

为什么可能有效：

```text
TFI 是主动吃单压力；
OFI/MLOFI 是订单簿被动流的响应；
两者同向说明成交不只是打印，而是在改变可见流动性。
```

失败模式：

```text
OFI/MLOFI 可能只说明市场会动，不说明 crossing 后赚钱；
多层盘口变化可能滞后；
强同向流可能已经释放完，成为 chase。
```

runtime-safe 边界：

```text
需要 Bot 在线维护 L1/L5/L25 OFI/MLOFI 或使用 validated decision_frame/L2 sidecar。
不能依赖 fixed panel 专有字段进入 runtime。
```

策略角色：

```text
entry confirmation
admission boost
exit continuation check
```

### S3 liquidity-vacuum release

市场机制：

```text
对手方深度低或突然塌陷时，同样的主动流可以造成更快 release。
```

数学定义：

```text
opposite_depth_t(side) = ask_depth_t if side=long else bid_depth_t
vacuum_t = 1{opposite_depth_t <= q_low}
flow_t   = 1{signed_flow_t is aligned with side}
S_3(t)   = vacuum_t * flow_t * spread_gate(t)
```

关键因子：

```text
top_depth_quote_min
depth25_quote_min
depth collapse
depletion_pressure
TFI / MLOFI
spread_bps
```

为什么可能有效：

```text
价格冲击近似与 signed aggressive flow / opposite depth 成正比；
depth 薄时，短时间 MFE 容易放大。
```

失败模式：

```text
vacuum 不等于 continuation；
薄盘口也意味着反向补单和回撤风险；
wide spread 会把 vacuum release 吃掉；
event-regime discovery 中 vacuum 很多行是 spread-cost mirage。
```

runtime-safe 边界：

```text
top-of-book depth 可 runtime-safe；
多档 depth collapse 需要 L2 stream 或 validated sidecar。
```

策略角色：

```text
release-only entry candidate
fast exit / wait model candidate
cost-sensitive admission
```

### S4 absorption / failed-continuation

市场机制：

```text
主动流很强，但价格不动、对手方深度持续补充，说明流被吸收。它可能不是 continuation，而是 failed continuation 或反转前兆。
```

数学定义：

```text
strong_flow_t = 1{|TFI_t| >= threshold}
no_move_t     = 1{|past_event_t| small and frames high}
absorb_t      = 1{replenishment against side is high or MLOFI not aligned}
S_4(t)        = strong_flow_t * no_move_t * absorb_t
```

关键因子：

```text
TFI
frames_since_mid_change
past_event_25_bps
replenish_pressure
MLOFI divergence
microprice_dev_bps
```

为什么可能有效：

```text
如果主动成交不能推动 mid，说明另一侧存在隐藏/补充流动性；
这可能降低 continuation edge，或者提示反向风险。
```

失败模式：

```text
absorption 和 delayed release 很像；
过早反向会被真正 breakout 打穿；
需要区分 passive replenishment 与普通静态 depth。
```

runtime-safe 边界：

```text
需要在线 L2 update 或可验证 replenishment/depletion summary。
不能用事后是否反转作为 runtime 条件。
```

策略角色：

```text
risk guard
entry suppressor
possible reversal research control
```

### S5 post-release continuation / exit-wait

市场机制：

```text
entry 后已经发生 release；此时问题从 entry 选择变成 stopping problem：继续等、立刻 cross exit，还是转 maker/wait。
```

数学定义：

```text
R_t(u) = signed mid return since entry
H_t(u) = max favorable excursion since entry
D_t(u) = H_t(u) - R_t(u)

continue_t = 1{sustained flow after release is aligned}
exit_t     = 1{reverse flow or replenishment against position appears}
```

关键因子：

```text
post-entry TFI
post-entry OFI/MLOFI
drawdown from MFE
spread at exit
depth/replenishment after release
```

为什么可能有效：

```text
旧 fixed60 把 fast release 和 post-release decay 混在一起；
1615412 说明 entry 可以对，但 stopping 错。
```

失败模式：

```text
exit 因子容易使用 future path 造成 oracle；
等待可能减少 crossing cost，也可能增加 adverse move；
不同结构族的 optimal tau 不同。
```

runtime-safe 边界：

```text
只允许使用 entry 后实时可见的 quote/trade/L2/private fill state。
MFE/MAE/time-to-MFE 只能做 diagnostic label。
```

策略角色：

```text
exit
wait
tail control
```

### S6 execution-cost admission

市场机制：

```text
方向有 edge 不等于值得成交。spread、depth、quote stability 决定 taker crossing 是否可接受。
```

数学定义：

```text
cost_long(t)  = 10^4 log(ask_t / mid_t)
cost_short(t) = 10^4 log(mid_t / bid_t)
admit_t       = 1{spread_t <= q and depth_t >= d and quote_stable_t}
S_6(t)        = admit_t
```

关键因子：

```text
spread_bps
top_depth_quote_min
depth25_quote_min
frames_since_mid_change
arrival_quote_lag
```

为什么可能有效：

```text
当前树 diagnostic 和 factor diagnostic 都显示 release 可以存在，但 executable 经常被 crossing cost 吃掉；
spread 是 cost，不是 alpha。
```

失败模式：

```text
过强 cost gate 会错过大 release；
低 spread 可能对应低 volatility，edge 也变小；
depth 充足可能意味着阻力强，不一定好。
```

runtime-safe 边界：

```text
quote/depth 是 exchange-visible，可 runtime-safe。
但 realized slippage、future spread、PnL 只能作为 evaluation。
```

策略角色：

```text
admission
size cap
fill-profile selection
```

### S7 volatility / decay-risk regime

市场机制：

```text
有些状态主要说明市场会剧烈运动或回吐，而不是说明某个方向能赚钱。
```

数学定义：

```text
vol_regime_t = f(trade_arrival_alignment, spread shock, past_event, trade burst)
decay_risk_t = P(D_t(tau) large | vol_regime_t, structure)
```

关键因子：

```text
trade_arrival_alignment
spread shock
past_event_25_bps
trade_window_count
volatility expansion
```

为什么可能有效：

```text
tree/factor diagnostics 中部分变量对 release 或 decay 有明显解释力；
但它们可能更像 risk regime，而不是 entry alpha。
```

失败模式：

```text
把 volatility 因子当 direction 因子，会得到 high release + high decay；
trade_arrival_alignment 的强行 continuation 在旧结果中容易变成 negative executable。
```

runtime-safe 边界：

```text
event count、past_event、spread shock 可 runtime-safe。
decay label 不可 runtime。
```

策略角色：

```text
decay-risk guard
exit urgency
position size suppressor
control variable
```

## 4. 新迁移因子的使用方式

同一个因子在不同结构族中可以有不同意义。不要做“一因子一解释”。

| 因子族 | 在 S1 中 | 在 S2 中 | 在 S3 中 | 在 S4/S5 中 | 在 S6/S7 中 |
| --- | --- | --- | --- | --- | --- |
| `TFI` | 主动压力 trigger | 与 OFI/MLOFI 交叉确认 | vacuum 中的推动流 | release 后 continuation | trade burst / volatility input |
| `R5/R10` | closed memory | 结构质量 prior | 不直接解释 vacuum | sizing prior | 不应作为 cost |
| `Delta/Energy/Z` | 绝对强度修正 | flow strength | pressure scale | tail/sizing | volatility control |
| `OFI/MLOFI` | 可作为增强项 | 核心确认 | depth-flow collapse | release 后延续/反转 | execution realism sidecar |
| `spread` | 不应藏在 gamma 中 | cost filter | vacuum risk | exit cost | admission 主因子 |
| `depth` | stale pressure context | confirmation context | 核心机制 | absorption/replenishment | size/cost cap |
| `frames` | stale-release 核心 | no-move context | quiet-before-break | delayed release vs absorption | quote stability |
| `past_event` | 是否已经释放 | chase guard | breakout context | post-release state | volatility/decay risk |
| `trade_arrival_alignment` | 不应直接替代 R5 | flow synchronization | event intensity | decay-risk clue | volatility regime |

这张表的意思是：迁移因子不是被塞进旧四象限，而是帮助我们发现、确认、否决或管理不同结构。

## 5. 结构组合模型

最终策略不应该是一个结构，而应该是结构族组合：

```text
raw_exposure_t = sum_k gamma_k * S_k(t) * side_k(t)
```

然后进入 online exposure ledger：

```text
actual_exposure_t = capacity_clip(raw_exposure_t, open_positions_t, risk_limits)
```

冲突处理必须优先级明确：

```text
1. execution-cost gate can veto entry structures.
2. exit/risk structures override entry structures for existing lots.
3. same-side entry structures can merge but must share capacity.
4. opposite-side structures either net out or select the higher-confidence structure.
5. sizing structures may scale exposure but must not create side by themselves.
```

因此结构角色必须分开：

```text
entry-alpha       -> can create new directional intent
release-only      -> can create candidate only with cost/exit support
cost-filter       -> can veto or scale but not create direction
exit-wait         -> manages open lot, not new entry
decay-risk        -> suppresses size or forces exit
control           -> used for diagnostics / matching, not policy
```

## 6. 树模型的位置

树模型不应作为当前主策略模型。它的正确位置是：

```text
structure interaction discovery
rule mining
candidate-conditional residual analysis
```

也就是说，树应该回答：

```text
在某个结构族内部，哪些 factor split 解释 release / decay / executable residual？
```

而不是：

```text
在全市场所有 frame 中直接预测 buy/sell。
```

当前 tree diagnostic 的读法也应如此：release 的 OOS rank 明显强，但 executable 仍被 cost/decay 压住。这支持“非线性 release 结构存在”，不支持“直接上树当策略”。

## 7. 下一步研究协议

后续任何结构族候选都应按同一个表格描述：

```text
structure_id
mechanism
trigger
direction_rule
confirmation
cost_gate
role
runtime_safe_inputs
release_lift
decay_lift
executable_lift
tail / capacity read
promotion_status
```

最低要求：

```text
1. 先说明市场机制，再写条件。
2. 分开报告 release、decay、executable、tail。
3. 明确 role：entry/admission/exit/sizing/risk/control。
4. 明确哪些字段能进 Bot runtime，哪些只是 diagnostic label。
5. 不同结构族不能只按 total PnL 排名；必须看它们承担的策略职责。
```

## 8. Evidence Layer

当前应引用的证据层：

```text
docs/markets/ccusdt/current/v1-current-tfi-strategy-handoff-20260518.md
docs/markets/ccusdt/current/v1-tfi-current-research-map-20260519.md
docs/markets/ccusdt/research/factors/v1-microstructure-factor-atlas-20260601.md
docs/markets/ccusdt/research/factors/v1-microstructure-factor-diagnostic-20260601.md
docs/markets/ccusdt/research/factors/v1-microstructure-tree-diagnostic-20260601.md
docs/markets/ccusdt/research/factors/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md
docs/markets/ccusdt/research/strategy/v1-event-regime-discovery-20260601.md
```

这些报告的关系：

```text
current handoff       -> 旧四象限当前策略和失败案例
current research map  -> path-first / release-decay 第一性原理
factor atlas          -> primitive 和 factor transform
factor diagnostic     -> release/decay/executable 分层因子证据
tree diagnostic       -> 非线性交互与 release 探针
release-decay report  -> fixed60 为什么混淆 entry 和 exit
event discovery       -> 结构族初筛与 spread-cost mirage 证据
```

## 9. Working Conclusion

旧四象限应保留，但它的身份要改变：

```text
from: the TFI strategy
to:   S1 active-flow stale-release structure family
```

新因子分析的目标也要改变：

```text
from: find a stronger single factor
to:   discover multiple market structures and assign factors to roles
```

最终方向不是“一个大模型决定一切”，而是：

```text
多结构 entry
+ cost admission
+ exit/wait
+ capacity ledger
+ strict execution audit
```

这才符合目前证据：不同结构族确实存在显著差异，但它们不一定都表现为同一种 entry alpha。
