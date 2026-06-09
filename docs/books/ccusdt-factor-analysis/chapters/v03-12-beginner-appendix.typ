#import "../styles.typ": definition, remark

= Appendix A：订单簿基础速览

本附录服务没有订单簿基础的读者。它不是正文主线；若已经熟悉 CEX LOB、maker/taker、spread、depth，可以跳过。

== 最小撮合模型

限价单指定可接受价格，不能成交时留在订单簿。市价单或 taker IOC 追求立即成交，会消耗订单簿中的流动性。

买方最高愿意出的价格是 best bid，卖方最低愿意接受的价格是 best ask。若 best bid < best ask，订单簿存在 spread。

== Bid、Ask、Mid、Spread

令 $b$ 为 best bid，$a$ 为 best ask：

$ m=(a+b)/2 $

$ s=(a-b)/m*10^4 $

Mid 是研究价格，不是成交价格。Taker buy 通常在 ask 成交；taker sell 通常在 bid 成交。

== Depth 与 sweeping

Depth 是某个价格上可成交数量。如果 market buy 数量小于 best ask depth，则可近似 top-of-book fill；若数量超过 best ask depth，就会扫到更高 ask，形成 depth slippage。

== Maker 与 Taker

Maker 提供流动性，taker 消耗流动性。Maker 策略面对 queue position 与 fill uncertainty；taker 策略面对 spread 与 depth slippage。Bullish 显式 fee 为零时，taker 仍然支付 crossing spread。

== Trade、Quote、L2

Quote 给出 best bid/ask。Trade 给出真实成交及方向。L2 update 给出多档订单簿数量变化。TFI 来自 trade；spread/top depth 来自 quote；QI/OFI/MLOFI/depth sweep 来自 L2。

== 研究数字速览

- bps：1 bps = 0.01%。
- IC：因子与未来收益的相关性。
- AUC：因子区分正负 outcome 的能力。
- MFE：最大有利波动。
- MAE：最大不利波动。
- decay：从 MFE 高点回吐到 horizon 的部分。
- CVaR：左尾条件平均损失。
- tail_share：右尾贡献集中度。

== 本附录结论

订单簿基础只服务一个目标：理解因子测量的市场对象。Spread 是成本，depth 是阻力，trade flow 是主动压力，L2 update 是流动性供给变化，mid 是研究状态而非成交承诺。

