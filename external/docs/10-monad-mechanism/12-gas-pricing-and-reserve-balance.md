# Gas Pricing 与 Reserve Balance

## 目的
把 Monad 的 gas / fee / reserve 机制整理成研究语言，并明确区分：

1. 当前代码已经能直接验证的规则
2. 为了进入控制问题而做的 reduced-form 压缩

## 证据分层速览
| 对象 | 当前状态 | 证据来源 | 当前锚点/外部锚点 | 在模型中的角色 |
| --- | --- | --- | --- | --- |
| gas fee 按 `gas_limit * gas_price(tx, base_fee)` 计入 reserve 检查 | 可直接观测 | 当前仓库代码 | `external/monad-official/monad/category/execution/monad/reserve_balance.cpp` | reserve 规则事实 |
| revision gating、delegated account 限制、pending-block 检查、init selfdestruct exemption | 可直接观测 | 当前仓库代码 | 同上 | reserve 规则事实 |
| `get_max_reserve` 当前默认占位逻辑 | 可直接观测 | 当前仓库代码 | 同上 | reserve 上限占位事实 |
| `\mathcal R_t, m_t^{(1)}, m_t^{(2)}, k=3` | 研究latent | 建模假设 | 本页、控制页、Bellman 页 | reduced-form 压缩 |
| `r_t(a)` | 研究latent | 当前仓库代码 + 建模假设 | 参数页、推导页 | survival projection |

## 核心对象
本篇把 Monad 的 reserve 相关研究语言分成两层：

- 代码规则层：当前执行代码里真的能看到什么
- 控制压缩层：为了进入 Bellman 和比较静态而引入的 reduced-form 记号

## 一、当前代码已验证规则
当前工作区里的 execution 代码已经能较明确地给出下面几类规则事实。

### 1. reserve tracking 受 revision gating 约束
- `tracking_enabled` 只在 `MONAD_FOUR` 及之后打开
- `use_recent_code_hash` 只在 `MONAD_EIGHT` 及之后打开
- `allow_init_selfdestruct_exemption` 只在 `MONAD_NINE` 及之后打开

因此，reserve 规则不是一个不变的单行公式，而是带有 protocol revision 条件的实现。

### 2. delegated account 不能 dip into reserve
当前代码明确检查 sender 是否 delegated；若是，则不能 dip into reserve。  
这意味着 delegation 不是文档背景信息，而是当前实现里的直接约束。

### 3. sender 是否允许 dip，需要检查 pending block 与当前块环境
当前代码会检查：

- `grandparent_senders_and_authorities`
- `parent_senders_and_authorities`
- 当前块内的 `senders` 与 `authorities`

因此，reserve 约束并不只取决于“当前这笔交易”，还取决于相邻 pending block 和当前块上下文。

### 4. init selfdestruct exemption 是显式实现逻辑
在较新 revision 下，init 期间 selfdestruct 的合约会触发 exemption 分支。  
这类语义在控制模型里只能被压成状态或指示器，不能反过来把压缩量当成协议原式。

### 5. 当前 max reserve 还是占位逻辑
当前 `get_max_reserve` 使用的是默认 `10 MON` 的占位返回，并带有 `TODO: implement precompile`。  
因此，文档里若写“reserve 上限由协议稳定给出”，就会高估当前代码锚点的确定性。

## 二、代码规则层的局部研究写法
若把交易的 upfront gas-style 占用写成研究层局部量，可记为

$$
c_t^{\mathrm{gas}}(a_t)=\ell_t\cdot \min(F_t+\pi_t^{\mathrm{prio}},\overline F_t).
$$

但必须同时声明：  
这条式子是为了进入控制问题而做的局部写法，不是对当前实现逐行逻辑的逐字翻译。  
当前代码真正检查的是 `gas_limit * gas_price(tx, base_fee)` 与 reserve-balance 规则的组合。

## 三、控制问题的 reduced-form 压缩
为了把 reserve 机制并入统一核与 Bellman，本项目把它压成下面的 reduced-form 表示：

$$
F_t,\qquad \mathcal R_t,\qquad m_t=(m_t^{(1)},m_t^{(2)}),\qquad k=3.
$$

它们分别表示：

- $F_t$：base fee 状态
- $\mathcal R_t$：当前可用 gas / reserve 预算的压缩表达
- $m_t$：最近两块遗留 obligations 的压缩表达
- $k=3$：为了做控制分析而引入的滚动窗口长度

在这个压缩层里，可以把 Reserve Balance 逻辑写成滚动三块预算约束：

$$
c_t(a_t)+m_t^{(1)}+m_t^{(2)}\le \mathcal R_t.
$$

相应的 queue 更新写成

$$
m_{t+1}^{(1)}=c_t(a_t),\qquad
m_{t+1}^{(2)}=m_t^{(1)}.
$$

这里必须明确：

- `k=3`、`m_t^{(1)}`、`m_t^{(2)}` 是控制问题里的分析压缩
- 它们用于表达“reserve 影响跨 block 可行域”
- 它们**不是**当前协议代码中的原生状态变量名

## 直觉解释
这条约束意味着：

$$
\text{你不能只问“这笔机会值不值得打”，还要问“它是否挤占未来几块的预算”。}
$$

这件事对 MEV 控制问题是结构性的，不是一个边角成本修正。  
一旦把 reserve 规则压成跨 block 预算状态，决策就从单笔贪心变成组合选择问题。

## 与主线的关系
这篇文档提供的是 unified kernel 中 $R_t$ 与 $F_t$ 的关键局部坐标。  
其中：

- `当前代码已验证规则` 负责说明 $R_t$ 能由哪些代码事实支撑
- `reduced-form 压缩` 负责把这些事实装入控制问题

对应的控制形式见 [Reserve 子结构与可行动作集](../20-core-model/23-reserve-constrained-control-k3.md)。

## 数据前提 / 识别边界
- RPC-only：可直接观察 base fee、gas limit、priority fee、max fee cap 等稳定链上字段
- 节点级代码锚点：可核对 revision gating、delegation 约束、pending-block 检查、selfdestruct exemption、max reserve 占位逻辑
- `\mathcal R_t`、`m_t`、`r_t(a)`：进入控制问题后仍需要进一步压缩、映射和校准

## 下一步
接下来进入主模型：

- [统一核主模型](../20-core-model/20-monad-mev-main-model.md)
- [Reserve 子结构与可行动作集](../20-core-model/23-reserve-constrained-control-k3.md)
