#import "../styles.typ": *

= 12 从读懂到改动：怎样安全做最小修改

#chapter_problem[
  读懂代码只是第一步。真正能说明你理解了仓库，是你能做一个不破坏对象地位的小改动。本章要解决的问题是：在当前闭环里，如何安全地增加字段、补校验或扩展 artifact，而不把系统边界弄坏？
]

#reading_goal[
  你要掌握一套最小修改方法：先判断对象地位，再定位 crate 边界，再决定哪些测试和 artifact 需要同步调整。
]

== 12.1 改动前先问三个问题

任何小改动开始前，先回答：

1. 这个对象属于 primitive、projection、proxy，还是 calibration target？
2. 它应该先出现在 observation、state、projection，还是 strategy / eval？
3. 如果它错了，会影响哪几个 artifact 与测试？

只要这三个问题没答清楚，就不要急着写代码。

== 12.2 最常见的小改动类型

本仓库最适合新手练习的改动有三类：

- 给 primitive 增加一个真正可观测字段
- 给 projection 增加一个新的 synthetic / proxy 字段
- 给 artifact 阅读或测试补更清楚的说明与断言

不适合作为第一练习的改动包括：

- 引入 live signing / broadcast
- 修改研究对象地位
- 把 synthetic 值伪装成直接观测

== 12.3 例子：给 primitive 增加一个可观测字段

假设你想给 `GeometryPrimitiveView` 增加一个新的 direct observation 字段。正确思路通常是：

```text
先确认数据面里真的有这个字段
  -> domain::state.rs 增加字段
    -> state builder 填值
      -> validation 看是否要补边界检查
        -> fixture / test / artifact 同步更新
```

这里最重要的是：如果它真的是 direct observation，就该进 primitive；如果它其实是推断值，就不该强行塞进去。

== 12.4 例子：不要把 projection 塞回 primitive

这是最容易犯的大错。比如你发现 `gamma_t` 很常用，就想把它直接放进 `PrimitiveStateView`，这样后面访问更方便。

这会同时破坏：

- 理论边界
- validation 约束
- artifact 解释方式

因为 `gamma_t` 在当前阶段属于 projection，不是 primitive。

#warningbox[
  “为了写代码方便，把 projection 塞回 primitive” 是当前仓库最需要避免的错误之一。方便性不能反向定义研究对象。
]

== 12.5 例子：增加一个策略输入字段

如果你想增加某个策略输入，比如新的 penalty、budget 或 route summary，通常要问：

- 它是 primitive 派生压缩，还是 modeling assumption？
- 它应该放在 `CompressedDecisionState` 还是 `ProjectionStateView`？
- `PaperBellmanPolicy` 和 `DecisionArtifact` 是否需要同步理解它？

这类改动往往不止改一个文件，而是会牵动：

- `domain`
- `state`
- `strategy`
- `cli`
- test / artifact

== 12.6 推荐的最小修改流程

对新手来说，推荐顺序是：

```text
先补领域类型
  -> 再补构造逻辑
    -> 再补 CLI 输出
      -> 最后补测试
```

而不是上来就先改 CLI 或先改 artifact。因为 artifact 只是结果，真正的语义在类型和构造逻辑里。

#changetask[
  本章建议的第一个真实练习不是加新算法，而是选一个现有字段，逆向追踪它的全路径：

  ```text
  fixture / snapshot
    -> raw observation
      -> primitive state
        -> projection / decision state
          -> decision artifact
            -> replay / eval
  ```

  等你能追清一条字段路径，再做新字段改动会安全得多。
]

#source_map_box[
  ```text
  新字段进入系统的安全路径
    -> 先定对象地位
    -> domain 定类型
    -> builder / projection 定构造
    -> cli 定输出
    -> test 定断言
  ```
]

#artifactbox[
  改完字段后，至少检查三类产物：

  - 对应 JSON artifact 是否出现了新字段
  - `role / strength / evidence` 是否仍然合理
  - smoke test 或单测是否覆盖了新行为
]

#checkpoint[
  你现在应该能解释：

  - 小改动为什么也必须先判断对象地位。
  - 为什么“先改类型，再改构造，再改输出，再补测试”更安全。
  - 为什么 projection 不能因为方便而被塞回 primitive。
]

#exercise[
  1. 假设要给 `PrimitiveStateView` 增加一个新的 direct observation 字段，列出你会先看的 4 个文件。
  2. 假设要给 `CompressedDecisionState` 增加一个新的 penalty 字段，说明你预计至少会牵动哪些 crate。
  3. 用一句话说明：为什么修改 artifact 不是第一步，而通常是最后几步之一。
]

#chapter_summary[
  真正成熟的代码阅读，不是“知道函数做什么”，而是知道一个改动应该从哪层开始、在哪层停止。当前仓库最重要的安全习惯，就是永远先判断对象地位，再动手改代码。
]
