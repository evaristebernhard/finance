#import "../styles.typ": *

= 06 `monad-mev-rpc`：RPC 观测适配器

#chapter_problem[
  很多读者一看到 RPC 就会误以为“真正的项目主体在这里”。本章要解决的问题是：`monad-mev-rpc` 到底做了哪些工作，为什么它只是观测适配器而不是主模型？
]

#reading_goal[
  你要读懂 `RpcClient`、`AmmSnapshotService`、`AmmSnapshotEnvelope` 和 `PoolFamily`，并能解释为什么 snapshot crate 的边界必须停在“采集并标准化局部可观测状态”。
]

== 6.1 先看导出面

`crates/monad-mev-rpc/src/lib.rs` 很直接：

```rust
pub mod abi;
pub mod amm_snapshot;
pub mod client;
```

这三块分别对应：

- ABI 编解码
- snapshot 领域对象与 service
- JSON-RPC 客户端

没有策略、没有 Bellman、没有评估。这本身已经在提醒你：它只是适配器。

== 6.2 `RpcClient`：最底层 transport

`client.rs` 里的 `RpcClient` 负责：

- 拼 JSON-RPC 请求
- 发送 HTTP
- 解析 `eth_chainId`、`eth_blockNumber`、`eth_call`

例如：

```rust
pub async fn eth_call(
    &self,
    to: Address,
    data: &[u8],
    block: &BlockTag,
) -> Result<Vec<u8>, RpcError>
```

这层只回答：“如何向节点发请求并拿回字节或错误”。

== 6.3 `AmmSnapshotEnvelope`：统一 snapshot 壳

再往上走，`amm_snapshot.rs` 把 transport 层结果组织成更高一级的对象：

```rust
pub struct AmmSnapshotEnvelope {
    pub family: PoolFamily,
    pub pool_address: String,
    pub chain_id: u64,
    pub block_number: u64,
    pub snapshot: AmmSnapshot,
}
```

注意这个对象仍然只是 snapshot，不是 primitive state。它表达的是：

- 我读的是哪个 family
- 哪个池子
- 哪个链、哪个块
- 读出了哪种 family-specific 的局部状态

== 6.4 family-specific snapshot

`AmmSnapshot` 是一个带分支的 `enum`：

```rust
pub enum AmmSnapshot {
    Cpmm(CpmmSnapshot),
    Clmm(ClmmSnapshot),
    NotYetSupported { family: String },
}
```

这非常适合教学，因为它把“不同 family 有不同局部几何”直接变成类型差异。

CPMM snapshot 里重点是：

- `token0`
- `token1`
- `reserve0`
- `reserve1`

CLMM snapshot 里重点则变成：

- `sqrt_price_x96`
- `tick`
- `liquidity`
- `fee`

== 6.5 `AmmSnapshotService`：把调用串起来

`AmmSnapshotService::snapshot` 是最值得通读的函数之一。它大致流程是：

```text
先读 chain id
  -> 校验 block tag
  -> 按 family 选择 cpmm / clmm 读取逻辑
  -> 组装 AmmSnapshotEnvelope
```

也就是说，这一层已经开始带一点“领域语义”，但仍然停在 snapshot 级别，而不是 primitive 级别。

#source_map_box[
  ```text
  RpcClient
    -> eth_chainId / eth_blockNumber / eth_call
      -> abi::decode_*
        -> snapshot_cpmm / snapshot_clmm
          -> AmmSnapshotEnvelope
  ```
]

== 6.6 为什么这里不是主模型

这是本章最关键的认识论问题。即使 `monad-mev-rpc` 能读到：

- reserves
- tick
- liquidity
- fee

它仍然不能直接告诉你：

- #qt
- #rt
- #kappat
- #ut
- #pt

更不能直接定义完整 #st。因为这些对象要么是 projection，要么需要事件、建模或校准。

#warningbox[
  RPC adapter 的成功，不等于项目主体已经完成。它只是在观测层把“可直接拿到的局部几何”取出来，并放进统一 snapshot schema。
]

== 6.7 从 CLI 到 RawObservation

在 `main.rs` 里，`snapshot` 命令会把 `AmmSnapshotEnvelope` 再包成 `RawObservation`，写进 `data/raw/*.jsonl`。这一步的含义是：

- snapshot crate 负责“把节点结果标准化”
- observation crate 负责“把标准化结果记成原始观测”

之后才轮到 state builder 解释它们。

#commandbox[
  最适合本章的命令是：

  ```powershell
  cargo run -p monad-mev-cli -- snapshot --family cpmm --address 0x... --rpc-url https://...
  ```

  即使你当前不连真实 RPC，也要先从 `cpmm-snapshot.fixture.json` 读懂 `AmmSnapshotEnvelope` 的形状，因为后面 `build-state` 和 `build-decision-state` 都依赖这个 schema。
]

#checkpoint[
  你现在应该能解释：

  - `RpcClient` 与 `AmmSnapshotService` 的职责差别。
  - 为什么 `AmmSnapshotEnvelope` 是统一 snapshot carrier。
  - 为什么 RPC crate 只能停在局部观测适配器，而不能越级定义 projection 或 Bellman 输入。
]

#exercise[
  1. 在 `amm_snapshot.rs` 中找出 `CpmmSnapshot` 和 `ClmmSnapshot`，比较它们的字段差异，并解释这种差异对应哪种 AMM 几何差异。
  2. 打开 `client.rs`，指出 `eth_chain_id`、`eth_block_number`、`eth_call` 分别返回什么。
  3. 用一句话解释：为什么 `AmmSnapshotEnvelope` 是唯一 RPC-only snapshot carrier，而不是可以随便再造第二套 schema。
]

#chapter_summary[
  `monad-mev-rpc` 的工作是把 RPC 节点视角中的 AMM 局部状态变成统一 snapshot schema。它对闭环很重要，但它不是研究主体，更不是 Bellman 层。
]
