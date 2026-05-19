# BONK Controlled L2 Modeling Report v2

- `run_tag`: `20260513_bullish_l2_basket_price_v1`
- 本报告只做 market-controlled modeling diagnostics，不输出交易规则，也不声称 alpha。
- 主任务: `1h/100bps` 与 `4h/100bps`; `12h` 仍只作为 regime/path-width 诊断。
- 模型阶梯: constant baseline -> context-only ridge logistic -> L2-only ridge logistic -> context+L2 ridge logistic。

## Outputs

- Metrics CSV: `date/bonk_v1_model_metrics_20260513_bullish_l2_basket_price_v1.csv`
- Stability CSV: `date/bonk_v1_model_stability_20260513_bullish_l2_basket_price_v1.csv`
- Panel parquet: `data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet`

## Non-overlap Smoke

| symbol | H | fold | model | rows | logloss | brier | top decile lift | upper-lower edge | calib slope |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| BONK1MUSDC | 1h | fold1 | `constant` | 60 | 0.5110 | 0.1492 | -16.7% | -6.7% | 0.000 |
| BONK1MUSDC | 1h | fold1 | `context_only_ridge_logistic` | 60 | 0.4426 | 0.1287 | 16.7% | 26.7% | 0.087 |
| BONK1MUSDC | 1h | fold1 | `l2_only_ridge_logistic` | 60 | 0.4945 | 0.1410 | 33.3% | 10.0% | 0.192 |
| BONK1MUSDC | 1h | fold1 | `context_plus_l2_ridge_logistic` | 60 | 0.4298 | 0.1270 | 33.3% | 43.3% | 0.104 |
| BONK1MUSDC | 4h | fold1 | `constant` | 15 | 0.7269 | 0.2657 | -46.7% | -26.7% | 0.000 |
| BONK1MUSDC | 4h | fold1 | `context_only_ridge_logistic` | 15 | 0.6824 | 0.2459 | 53.3% | 73.3% | 0.125 |
| BONK1MUSDC | 4h | fold1 | `l2_only_ridge_logistic` | 15 | 0.9646 | 0.3443 | -46.7% | -26.7% | -0.144 |
| BONK1MUSDC | 4h | fold1 | `context_plus_l2_ridge_logistic` | 15 | 0.8688 | 0.2781 | 53.3% | 73.3% | 0.061 |
| BONK1MUSDT | 1h | fold1 | `constant` | 60 | 0.5089 | 0.1489 | -16.7% | -5.0% | 0.000 |
| BONK1MUSDT | 1h | fold1 | `context_only_ridge_logistic` | 60 | 0.4710 | 0.1343 | 33.3% | 45.0% | 0.065 |
| BONK1MUSDT | 1h | fold1 | `l2_only_ridge_logistic` | 60 | 0.4582 | 0.1358 | 50.0% | 28.3% | 0.288 |
| BONK1MUSDT | 1h | fold1 | `context_plus_l2_ridge_logistic` | 60 | 0.4514 | 0.1251 | 50.0% | 61.7% | 0.085 |
| BONK1MUSDT | 4h | fold1 | `constant` | 15 | 0.6813 | 0.2438 | -40.0% | -20.0% | 0.333 |
| BONK1MUSDT | 4h | fold1 | `context_only_ridge_logistic` | 15 | 0.6154 | 0.2171 | 60.0% | 80.0% | 0.168 |
| BONK1MUSDT | 4h | fold1 | `l2_only_ridge_logistic` | 15 | 0.7945 | 0.2741 | 10.0% | 30.0% | 0.059 |
| BONK1MUSDT | 4h | fold1 | `context_plus_l2_ridge_logistic` | 15 | 0.6061 | 0.2036 | 10.0% | 30.0% | 0.163 |
| BONK1MUSDC | 1h | fold2 | `constant` | 60 | 0.6446 | 0.2011 | -23.3% | -38.3% | 0.014 |
| BONK1MUSDC | 1h | fold2 | `context_only_ridge_logistic` | 60 | 0.7346 | 0.2087 | -23.3% | -21.7% | -0.039 |
| BONK1MUSDC | 1h | fold2 | `l2_only_ridge_logistic` | 60 | 0.6214 | 0.1967 | -6.7% | -21.7% | 0.033 |
| BONK1MUSDC | 1h | fold2 | `context_plus_l2_ridge_logistic` | 60 | 0.7320 | 0.2068 | -6.7% | -5.0% | -0.025 |
| BONK1MUSDC | 4h | fold2 | `constant` | 15 | 0.6743 | 0.2406 | -40.0% | -56.7% | 0.000 |
| BONK1MUSDC | 4h | fold2 | `context_only_ridge_logistic` | 15 | 0.6724 | 0.2331 | 60.0% | 93.3% | 0.151 |
| BONK1MUSDC | 4h | fold2 | `l2_only_ridge_logistic` | 15 | 0.6693 | 0.2389 | 10.0% | -6.7% | 0.256 |
| BONK1MUSDC | 4h | fold2 | `context_plus_l2_ridge_logistic` | 15 | 0.6252 | 0.2132 | 60.0% | 93.3% | 0.174 |
| BONK1MUSDT | 1h | fold2 | `constant` | 60 | 0.6432 | 0.2009 | -23.3% | -38.3% | n/a |
| BONK1MUSDT | 1h | fold2 | `context_only_ridge_logistic` | 60 | 0.7316 | 0.2086 | -23.3% | -21.7% | -0.041 |
| BONK1MUSDT | 1h | fold2 | `l2_only_ridge_logistic` | 60 | 0.6464 | 0.2009 | -6.7% | -21.7% | -0.106 |
| BONK1MUSDT | 1h | fold2 | `context_plus_l2_ridge_logistic` | 60 | 0.7528 | 0.2104 | -6.7% | -5.0% | -0.046 |
| BONK1MUSDT | 4h | fold2 | `constant` | 15 | 0.6742 | 0.2405 | -40.0% | -56.7% | 0.000 |
| BONK1MUSDT | 4h | fold2 | `context_only_ridge_logistic` | 15 | 0.6780 | 0.2347 | 60.0% | 93.3% | 0.144 |
| BONK1MUSDT | 4h | fold2 | `l2_only_ridge_logistic` | 15 | 0.6838 | 0.2450 | 10.0% | -6.7% | -0.175 |
| BONK1MUSDT | 4h | fold2 | `context_plus_l2_ridge_logistic` | 15 | 0.6645 | 0.2237 | 60.0% | 93.3% | 0.149 |
| BONK1MUSDC | 1h | fold3 | `constant` | 72 | 0.4773 | 0.1493 | -5.6% | 0.0% | -0.043 |
| BONK1MUSDC | 1h | fold3 | `context_only_ridge_logistic` | 72 | 0.4489 | 0.1354 | 31.9% | 25.0% | 0.121 |
| BONK1MUSDC | 1h | fold3 | `l2_only_ridge_logistic` | 72 | 0.4237 | 0.1298 | 31.9% | 25.0% | 0.299 |
| BONK1MUSDC | 1h | fold3 | `context_plus_l2_ridge_logistic` | 72 | 0.4558 | 0.1393 | 31.9% | 25.0% | 0.111 |
| BONK1MUSDC | 4h | fold3 | `constant` | 18 | 0.6740 | 0.2404 | 11.1% | 5.6% | -1.111 |
| BONK1MUSDC | 4h | fold3 | `context_only_ridge_logistic` | 18 | 0.7589 | 0.2802 | -38.9% | -94.4% | -0.119 |
| BONK1MUSDC | 4h | fold3 | `l2_only_ridge_logistic` | 18 | 0.7129 | 0.2594 | -38.9% | -94.4% | -0.255 |
| BONK1MUSDC | 4h | fold3 | `context_plus_l2_ridge_logistic` | 18 | 0.8130 | 0.3000 | -38.9% | -94.4% | -0.082 |
| BONK1MUSDT | 1h | fold3 | `constant` | 72 | 0.4772 | 0.1493 | -5.6% | 1.4% | -0.008 |
| BONK1MUSDT | 1h | fold3 | `context_only_ridge_logistic` | 72 | 0.4949 | 0.1530 | 19.4% | 1.4% | 0.048 |
| BONK1MUSDT | 1h | fold3 | `l2_only_ridge_logistic` | 72 | 0.4843 | 0.1508 | 6.9% | 1.4% | 0.021 |
| BONK1MUSDT | 1h | fold3 | `context_plus_l2_ridge_logistic` | 72 | 0.5173 | 0.1590 | 31.9% | 13.9% | 0.015 |
| BONK1MUSDT | 4h | fold3 | `constant` | 18 | 0.6742 | 0.2406 | 11.1% | 5.6% | -1.111 |
| BONK1MUSDT | 4h | fold3 | `context_only_ridge_logistic` | 18 | 0.7487 | 0.2750 | -38.9% | -44.4% | -0.074 |
| BONK1MUSDT | 4h | fold3 | `l2_only_ridge_logistic` | 18 | 0.7207 | 0.2631 | 11.1% | 5.6% | -0.691 |
| BONK1MUSDT | 4h | fold3 | `context_plus_l2_ridge_logistic` | 18 | 0.8093 | 0.3002 | 11.1% | 5.6% | -0.120 |

## Interpretation Guardrails

- `context+L2` 必须在 Fold 2/3 的 non-overlap 上稳定优于 `context-only`，否则只保留为现象诊断。
- 若 top-decile 同时提高 upper 与 lower first-passage，则标记为 path-width 状态，不解释为方向性。
- Binance/Bullish context 只使用 t 及以前信息；future market/meme/SOL 只用于 residual labels 和事后归因。

## Acceptance Read

| symbol | H | fold | context+L2 vs context-only | logloss delta | brier delta | top-decile lift delta |
|---|---:|---|---|---:|---:|---:|
| BONK1MUSDC | 1h | fold2 | pass | -0.0026 | -0.0019 | 16.7% |
| BONK1MUSDC | 4h | fold2 | pass | -0.0472 | -0.0199 | 0.0% |
| BONK1MUSDT | 1h | fold2 | diagnostic_only | 0.0213 | 0.0019 | 16.7% |
| BONK1MUSDT | 4h | fold2 | pass | -0.0135 | -0.0111 | 0.0% |
| BONK1MUSDC | 1h | fold3 | diagnostic_only | 0.0070 | 0.0040 | 0.0% |
| BONK1MUSDC | 4h | fold3 | diagnostic_only | 0.0541 | 0.0198 | 0.0% |
| BONK1MUSDT | 1h | fold3 | diagnostic_only | 0.0223 | 0.0060 | 12.5% |
| BONK1MUSDT | 4h | fold3 | diagnostic_only | 0.0606 | 0.0252 | 50.0% |

- Fold 2/3 non-overlap stable wins: `3/8`. Unless this is consistently positive, the result stays a phenomenon diagnostic rather than an alpha claim.
- Best context+L2 non-overlap top-decile lift observed: `60.0%` for `BONK1MUSDT` 4h fold2. Treat as smoke only.
- Daily stability rows: `160`.