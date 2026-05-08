# 实现边界与 Workspace Adapter

## 目的
说明当前研究主文档与 workspace 内部实现 crate 之间的职责边界，避免再次把某个局部 adapter 写成并行项目主线。

## 当前库职责
当前仓库 `monad_mev` 负责：

- 研究主文档
- 参数建模
- 机制说明
- 观测与识别边界

它同时承载实现代码，但实现必须服从研究主线，而不能反向定义研究对象。

## Workspace adapter 职责
当前 RPC-only 观测入口是 workspace 内部 crate：

- `crates/monad-mev-rpc`
- `crates/monad-mev-cli`

该 adapter 层负责：

- RPC 数据抓取
- `cpmm / clmm` pool state 结构化快照
- 面向研究流程的 CLI 子命令

当前阶段它只提供 workspace 内部的最小观测入口，不复制研究正文，也不再保留独立工程形态。

## 研究与实现的关系
当前工作区内部关系固定为：

- `docs/` 定义研究对象、参数、机制与识别边界
- `crates/monad-mev-rpc` 提供对这些对象的 RPC-only 观测与抽取工具
- `crates/monad-mev-cli` 提供用户入口
- 文档先行，代码跟随；adapter crate 不反向定义主模型

## 下一步
若要继续从实现角度阅读，请前往：

- 根 [README](../../README.md)
- [System Architecture](../architecture/00-system-architecture.md)
- [monad-mev-rpc crate](../../crates/monad-mev-rpc)
