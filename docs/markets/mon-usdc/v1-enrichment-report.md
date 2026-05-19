# MON/USDC V1 Enrichment 报告

状态: `20260511_reconstruct_v1`。

## 覆盖率

- tx bodies 覆盖: `1701634/1701634`，missing `0`，errors `0`
- receipt log bundles 覆盖: `1701634/1701634`，log rows `15635501`，missing `0`，errors `17150`
- derived 行数: price paths `2147000`，tx paths `1701625`，cross-pool `2147000`
- pool state samples: success `5924`，failed `19816`
- trace samples: success `3399`，failed `1701`
- reconstructed execution panel 行数: rows `2147000`，usable `2147000`，tiers A_observed `4037`，B_reconstructed `2142963`

## 最终状态

- base_enrichment_passed: `false`
- sample_enrichment_passed: `true`

输出清单见 `date/mon_usdc_v1_enrichment_completion_20260511_reconstruct_v1.json`。
