#import "../styles.typ": *

= 附录 G 字段扩展检查清单

#chapter_problem[
  这一附录给出一个实际开发时可直接使用的检查清单：当你准备增加一个字段时，怎样确认自己没有越过对象边界、没有漏掉 artifact，也没有破坏测试？
]

== G.1 先判断对象地位

新增字段前先勾选：

- 它是 direct observation 吗？
- 它是 event reconstruction 吗？
- 它是 RPC weak proxy 吗？
- 它是 latent / calibration target 吗？

只要这一步判断不清楚，后面的 crate 落点就不可靠。

== G.2 再判断落在哪层

#anchor_table((
  [`观测原始输入`], [`observation / rpc`],
  [`primitive 字段`], [`domain/state.rs + state/builder.rs`],
  [`projection 字段`], [`domain/state.rs + projection`],
  [`策略压缩输入`], [`domain/state.rs + state/compressed.rs + strategy`],
  [`评估输出字段`], [`eval + cli artifact`]
))

== G.3 最小同步面

一个新字段通常至少要核对下面这些地方：

```text
类型定义
构造逻辑
validation
CLI artifact
单元测试 / smoke test
```

如果只改了其中一个地方，往往说明你还没把字段的完整生命周期想清楚。

== G.4 三个停止信号

一旦出现下面任一情况，应该暂停继续改动：

1. 你发现自己想把 projection 直接塞进 primitive。
2. 你发现自己只能先改 JSON，而解释不清类型层应该怎么表示。
3. 你发现自己无法说明该字段错了会影响哪条测试和哪类 artifact。

#chapter_summary[
  好的最小改动，永远先从对象地位开始，再落到类型、构造、artifact 与测试。检查清单的价值，就在于帮你把这个顺序固定下来。
]
