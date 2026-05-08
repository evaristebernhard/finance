#import "../styles.typ": *
#import "../notation.typ": *

= 附录 A. 术语表

#table(
  columns: (24%, 76%),
  inset: 6pt,
  stroke: 0.45pt + rgb("#c9c9c9"),
  fill: (x, y) => if x == 0 { rgb("#f3f3f3") } else { none },
  [`block`], [区块。最小入门直觉里是区块链数组中的一个元素；更完整地说，是一批交易和其执行结果的组织单元。],
  [`transaction`], [交易。改变链上状态的执行指令。],
  [`state`], [状态。账户余额、合约存储、AMM 池储备、事件推进背景等组成的世界描述。],
  [`execution`], [执行。把交易作用到当前状态，产生新状态、logs、gas 消耗和结果。],
  [`mempool`], [未确认交易可见集合。当前教材中主要当作传播环境的一部分，不被当成协议真值。],
  [`reserve`], [Monad 相关的预算、gas、delegation、admissibility、survival 约束对象。],
  [`AMM`], [自动做市商。由池子库存和数学规则自动报价的链上交易机制。],
  [`CPMM`], [Constant Product Market Maker，常数乘积做市商，如 Uniswap v2 风格池。],
  [`CLMM`], [Concentrated Liquidity Market Maker，集中流动性做市商，如 Uniswap v3 风格池。],
  [`slippage`], [滑点。交易导致价格相对初始边际价格恶化的程度。],
  [`MEV`], [可提取价值。由排序、时机、状态可见性和市场差异诱发的额外收益。],
  [`primitive`], [主模型的一阶对象。本项目中是 `G/M/C/R/E/F`、动作、转移核、belief 等。],
[`projection`], [由 primitive、动作和 kernel 诱导出来的决策相关对象，如 #gamma / #qt / #rt / #kappat / #ut / #pt。],
  [`proxy`], [弱代理。观测不充分时构造的近似量，不能当成协议直接真值。],
  [`calibration`], [校准。用数据、仿真或经验给 latent / projection 选择数值。],
  [`paper execution`], [研究闭环中的纸面执行。生成可回放记录，不做签名、广播和真实资金操作。],
)
