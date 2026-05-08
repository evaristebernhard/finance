#import "../styles.typ": *
#import "../notation.typ": *

= 附录 J. 练习题详细解答

== 第 1 章详细解答

1. 为什么 `block[i]` 本身不足以定义交易后余额？

   因为 `block[i]` 只告诉你“有哪些交易要执行”，但不告诉你执行前的状态是什么，也不告诉你执行规则如何作用。  
   若没有 `S_i`，你连 Alice 原本有多少钱都不知道；若没有执行规则 `F`，你也不知道交易失败时该如何处理。

2. `Alice=12, Bob=1`，先 `Alice -> Bob = 4`，再 `Bob -> Alice = 2`，结果是什么？

   第一步后：

   ```text
   Alice = 8
   Bob = 5
   ```

   第二步后：

   ```text
   Alice = 10
   Bob = 3
   ```

3. 哪个文档写出了 `G/M/C/R/E/F`？

   `docs/20-core-model/20-monad-mev-main-model.md`。

4. 为什么完整状态 `S_i` 不适合作为策略直接输入？

   因为它过于高维、不可完整直接观测，而且策略真正需要的是与行动相关的压缩对象，而不是世界的全量底层描述。

== 第 2 章详细解答

1. 为什么 gas 是执行模型的第一性对象？

   因为没有 gas，就没有执行资源边界和成本信号，任何合约都可以无限消耗计算资源。

2. `gas_used=120000`，`gas_price=25 gwei`，费用是多少？

   $120000 times 25 = 3,000,000$ gwei。

3. 当前 normalized event schema 中哪个对象记录 `success` 与 `gas_used`？

   `TxnOutcomeObservation`。

4. 为什么 `gas_used` 是事实，而 #rof($a$) 是 projection？

   `gas_used` 是执行后直接记录下来的结果。#rof($a$) 则是根据规则结构、状态和不确定性形成的 survival belief。

== 第 3 章详细解答

1. 为什么“更快的链”不是 Monad MEV 建模的充分描述？

   因为本项目关心的不是单一速度参数，而是 block state、传播、reserve、冲突和 verified output 如何进入决策问题。

2. $Gamma=10, q=0.35, u=0.7, r=0.8, L=3, c=2, kappa=1.5$，为什么会比“净边 8”小很多？

   先算：

   $u r = 0.56$

   成功项：

   $0.56 times 10 = 5.6$

   失败项：

   $(1 - 0.56) times 3 = 1.32$

   括号内：

   $5.6 - 2 - 1.32 = 2.28$

   乘 `q`：

   $0.35 times 2.28 = 0.798$

   再减 `kappa=1.5`：

   结果约为 `-0.702`。  
   所以“毛机会 10”完全不等于“净边 8”。

3. 哪一页最明确解释了 block-related events 与 commit-state？

   `docs/10-monad-mechanism/10-block-states-and-speculative-execution.md`。

4. 为什么“Monad 更快”不够？

   因为研究对象不只改变在时间尺度，还改变在状态层次与执行结构。

== 第 4 章详细解答

1. 为什么 `BlockQC` 是事实，而 #pt 是 projection？

   `BlockQC` 是某个事件是否发生的事实。#pt 则是观察者根据现有信息形成的“最终 canonical 概率”。

2. 若 `#pt = 0.75`、`d_t = 0.8`，则 #ut 是多少？

   $0.75 times 0.8 = 0.6$。

3. 当前 normalized event 中哪类最贴近 commit-state 更新？

   `CommitStateUpdate`。

4. 为什么 verified 不能消除事前不确定性？

   因为 verified 是事后结果，事前决策时刻并不知道它一定会发生。

== 第 5 章详细解答

1. 为什么 gas 不是单纯利润扣减项？

   因为 gas 既进入收益函数，又进入可行动作集合的预算约束。

2. `b=120, c_gas=50, m_1=30, m_2=20`，动作是否可行？

   $50 + 30 + 20 = 100 <= 120$，因此可行。

3. 若 `chi=0.95`、`rho=0.8`，则 #rof($a$) 是多少？

   $0.95 times 0.8 = 0.76$。

4. reserve-balance 的本地代码锚点是什么？

   `external/monad-official/monad/category/execution/monad/reserve_balance.cpp`。

== 第 6 章详细解答

1. 为什么 AMM 需要不变量？

   因为没有不变量，池子无法在库存变化时维持一致报价，也容易被免费掏空。

2. 边际价格和平均价格有什么区别？

   边际价格是下一点点交易的价格，平均价格是整笔交易总输入除以总输出。

3. 初始价格 1，平均成交价 1.05，滑点是多少？

   $(1.05 - 1) / 1 = 5%$。

4. Uniswap v2 本地锚点目录？

   `external/amm-official/uniswap-v2-core`。

== 第 7 章详细解答

1. `x=500, y=1000, fee=0.3%, Delta x=20`，求有效输入。

   $20 times 0.997 = 19.94$。

2. 求新储备与输出。

   $x' = 519.94$。

   若 `k = 500000`，则：

   $y' approx 500000 / 519.94 approx 961.65$

   所以：

   $Delta y approx 1000 - 961.65 = 38.35$

3. 若 $Gamma(x)=0.03x-0.0005x^2$，最优规模是多少？

   一阶条件：

   $0.03 - 0.001x = 0$

   所以 `x = 30`。

4. 为什么 `A/B` 不是协议原生字段？

   因为它们是局部近似系数，不是合约直接暴露的状态变量。

== 第 8 章详细解答

1. 为什么 CLMM 的关键对象不是 `(reserve0, reserve1)`？

   因为 CLMM 的核心几何来自 tick、active liquidity、liquidity by tick 等分段结构。

2. stable AMM 为什么在锚定附近滑点更低？

   因为其曲线在锚定附近更平坦，对小额交易的价格响应更柔和。

3. weighted pool 为什么不能当成 50/50 的 CPMM？

   因为权重直接改变库存和价格响应关系。

4. stable 和 weighted 锚点示例？

   `external/amm-official/curve-core/contracts/amm/stableswap`  
   `external/amm-official/balancer-v3-monorepo/pkg/pool-weighted/contracts/WeightedPool.sol`

== 第 9 章详细解答

1. 为什么 #gamma 不能代表最终收益？

   因为它只是毛机会，还没经过 #qt/#ut/#rt 过滤，也没扣 gas、失败损失和 #kappat。

2. $Gamma=6, q=0.5, u=0.8, r=0.75, c=1, L=2, kappa=0.5$，一步分数是多少？

   $u r = 0.6$

   成功项：

   $0.6 times 6 = 3.6$

   失败项：

   $(1 - 0.6) times 2 = 0.8$

   括号内：

   $3.6 - 1 - 0.8 = 1.8$

   乘 `q`：

   $0.5 times 1.8 = 0.9$

   再减 `0.5`：

   最终约为 `0.4`。

3. #kappat 更主要回指哪里？

   更主要回指 #et / #ct。

4. 当前 CLI 哪一步开始把 primitive state 压成 decision state？

   `build-decision-state`。

== 第 10 章详细解答

1. 为什么 #gamma 重要但不是 primitive？

   因为它依赖状态、路径和规模，是由世界诱导出来的对象，而不是世界本身的原生状态分量。

2. 为什么 #qof($a$) 天然依赖动作？

   因为动作的 bid、gas、路径和时机都会影响 included 概率。

3. 当前哪个类型只承载 `g_t/m_t/c_t/r_t/e_t/f_t`？

   `PrimitiveStateView`。

4. 如果把 #qt 错当 primitive，会怎样？

   会把传播与竞争结构误写成协议直接给定的状态真值。

== 第 11 章详细解答

1. `theta_proto/theta_env/theta_cal` 的区别？

   分别对应协议给定结构、环境过程和最终校准对象。

2. 为什么 `txpool_*` 最多只能作为 #qt 的弱代理？

   因为它是 provider 或基础设施暴露的局部视角，不是协议保证接口。

3. 哪几章解释了 #gamma/#qt/#rt/#kappat/#ut/#pt 不是 primitive？

   第 10 章与第 11 章最直接。

4. 为什么 decision state 要保留 evidence/role/strength？

   因为否则压缩态里的数值会被误当同层真值。

== 第 12 章详细解答

1. 标准 act 分数怎么手算？

   $u r = 0.72$

   $u r Gamma = 7.2$

   失败项：`0.84`

   括号内：`4.36`

   乘 `q=0.7` 得 `3.052`

   减 `kappa=1.2` 得 `1.852`

2. 若 `q=0.4`，结果是多少？

   $0.4 times 4.36 - 1.2 = 0.544$

3. 当前 CLI 主链？

   `snapshot -> ingest-events -> build-decision-state -> decide -> paper-execute -> replay -> eval`

4. 为什么 `paper execution` 不能讲成 live trading？

   因为当前闭环不处理签名、广播、nonce、私钥和真实资金执行，只解决研究对象的闭环验证问题。
