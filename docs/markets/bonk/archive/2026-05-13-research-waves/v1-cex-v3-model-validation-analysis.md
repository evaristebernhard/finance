# BONK CEX V3 Model Validation Design Analysis

状态: 2026-05-13。本文只做模型验证设计分析，不输出交易规则，也不声称 alpha。

## Inputs And Outputs

输入:

```text
date/bonk_v3_phase_validation_probe.csv
date/bonk_v1_model_metrics_20260513_bullish_l2_basket_price_v1.csv
data/bonk/v1/derived/bonk_l2_label_context_panel/bonk_l2_label_context_panel_20260513_bullish_l2_basket_price_v1.parquet
```

输出:

```text
date/bonk_v3_model_validation_design.csv
docs/markets/bonk/v1-cex-v3-model-validation-analysis.md
```

## Executive Read

- 当前保守模型读法仍是 `diagnostic_only`: fold2/3 的 non-overlap 配对里，`context+L2` 相对 `context-only` 只有 `3/8` 个组合同时改善 logloss 与 brier。
- 这个 `3/8` 对“稳定预测模型/alpha claim”很重要，足以阻止把当前 `context+L2` 写成稳定胜出的模型。
- 这个 `3/8` 对“激进短半衰期现象研究”没有一票否决力，因为当前验证只看 1h/4h、100bps，并且 non-overlap 只用了一个 phase offset；短半衰期候选需要 lag/decay、phase distribution、regime gate 和 path-width 专表。
- phase sample size 是当前最大限制: 1h phase 每相位约 59-72 行，top decile 只有约 6-8 点；4h phase 每相位约 14-18 行，top decile 约 1-2 点，不能承载 decile lift 或 calibration 的单相位推断。

## Phase Sample Size

`phase_count_design` 不是新样本，它只是列出每个 horizon stride 的所有 phase offset 会有多少行。`full_ok_rows` 是这些 phase 行数求和后回到原 fold 内可用分钟数。

| fold | symbol | H | phases | phase rows min/median/max | full ok rows | base rates | median future return bps |
| --- | --- | ---: | ---: | --- | ---: | --- | ---: |
| fold1 | BONK1MUSDC | 1h | 60 | 59/60/60 | 3599 | upper 12.3%, lower 10.4% | 5.5 |
| fold1 | BONK1MUSDC | 4h | 240 | 14/15/15 | 3599 | upper 45.4%, lower 29.1% | 21.3 |
| fold1 | BONK1MUSDT | 1h | 60 | 60/60/60 | 3600 | upper 12.2%, lower 10.7% | 5.4 |
| fold1 | BONK1MUSDT | 4h | 240 | 15/15/15 | 3600 | upper 45.6%, lower 29.5% | 21.2 |
| fold2 | BONK1MUSDC | 1h | 60 | 59/60/60 | 3589 | upper 25.8%, lower 18.7% | 6.7 |
| fold2 | BONK1MUSDC | 4h | 240 | 14/15/15 | 3589 | upper 59.7%, lower 28.6% | 44.4 |
| fold2 | BONK1MUSDT | 1h | 60 | 59/60/60 | 3589 | upper 25.9%, lower 18.9% | 6.7 |
| fold2 | BONK1MUSDT | 4h | 240 | 14/15/15 | 3589 | upper 59.8%, lower 28.9% | 44.6 |
| fold3 | BONK1MUSDC | 1h | 60 | 70/72/72 | 4315 | upper 15.8%, lower 18.3% | -5.2 |
| fold3 | BONK1MUSDC | 4h | 240 | 17/18/18 | 4315 | upper 36.9%, lower 42.6% | -4.8 |
| fold3 | BONK1MUSDT | 1h | 60 | 72/72/72 | 4320 | upper 15.9%, lower 18.6% | -5.4 |
| fold3 | BONK1MUSDT | 4h | 240 | 18/18/18 | 4320 | upper 37.1%, lower 42.8% | -4.6 |

Interpretation:

- 1h 的 phase offset 适合做 smoke 和 phase-sensitivity 摘要，但单个 phase 的 top-decile 样本仍很薄。
- 4h 的单 phase 样本太小，fold1/fold2 只有约 15 行、fold3 约 18 行。任何 4h top-decile lift 都可能由 1-2 个点决定。
- phase averaging 可以帮助发现“某个 phase 碰巧好”的风险，但不能把 240 个 4h phase 当成 240 份独立验证。
- fold2 与 fold3 的标签 regime 差异很明显: fold2 的 4h upper rate 约 60%，fold3 的 4h lower rate 约 43%。这解释了为什么 forward fold 读法会比全样本更严厉。

## Paired Delta

下面只列最关键的 fold2/3 non-overlap paired delta。负的 `delta_log_loss` 和 `delta_brier` 才是 proper-score 改善；positive lift 只能说明排序/分桶诊断，不等于概率模型胜出。

| fold | symbol | H | rows | d_logloss | d_brier | d_lift | d_upper_minus_lower | proper |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| fold2 | BONK1MUSDC | 1h | 60 | -0.0026 | -0.0019 | 0.1667 | 0.1667 | pass |
| fold2 | BONK1MUSDC | 4h | 15 | -0.0472 | -0.0199 | 0.0000 | 0.0000 | pass |
| fold2 | BONK1MUSDT | 1h | 60 | 0.0213 | 0.0019 | 0.1667 | 0.1667 | fail |
| fold2 | BONK1MUSDT | 4h | 15 | -0.0135 | -0.0111 | 0.0000 | 0.0000 | pass |
| fold3 | BONK1MUSDC | 1h | 72 | 0.0070 | 0.0040 | 0.0000 | 0.0000 | fail |
| fold3 | BONK1MUSDC | 4h | 18 | 0.0541 | 0.0198 | 0.0000 | 0.0000 | fail |
| fold3 | BONK1MUSDT | 1h | 72 | 0.0223 | 0.0060 | 0.1250 | 0.1250 | fail |
| fold3 | BONK1MUSDT | 4h | 18 | 0.0606 | 0.0252 | 0.5000 | 0.5000 | fail |

Aggregate read:

| sample | proper-score wins | lift nonnegative | median d_logloss | median d_brier | median d_lift |
| --- | ---: | ---: | ---: | ---: | ---: |
| full minute all | 1/12 | 7/12 | 0.0263 | 0.0074 | 0.0418 |
| full minute fold2/3 | 1/8 | 5/8 | 0.0263 | 0.0074 | 0.0418 |
| non-overlap all | 6/12 | 11/12 | 0.0022 | 0.0001 | 0.0625 |
| non-overlap fold2/3 | 3/8 | 8/8 | 0.0141 | 0.0029 | 0.0625 |

## Why 3/8 Matters

`3/8` matters under the conservative validation question: “Does `context+L2` stably beat `context-only` as a probability model on non-overlapping forward folds?” The answer is no. Fold2 has 3 proper-score wins out of 4, but fold3 has 0 out of 4. The fold3 reversal means current `context+L2` cannot be promoted beyond diagnostic/model-smoke status.

It also matters because full-minute results are not a rescue: overlapping labels show only 1/8 proper-score wins in fold2/3, and median proper-score deltas are worse. Positive top-decile lift in several rows is interesting, but when logloss and brier worsen it should be read as ranking/path-state information, not calibrated forecast improvement.

## Why 3/8 Does Not Kill Aggressive Short-Half-Life Research

The aggressive V3 question is narrower: “Are there L2 states with short-lived, regime-local, or path-width value that deserve pre-registered next-window validation?” Current `3/8` does not answer that question cleanly.

Reasons:

- The current model table uses 1h and 4h labels. A 5m or 15m microstructure effect can decay before a 1h/4h first-passage label resolves.
- The current non-overlap metric uses one stride phase. That is good for a conservative smoke test, but it can reject or accept a candidate because of offset luck.
- Phase rows are tiny, especially for 4h. Single-phase decile lift is too noisy to decide a short-half-life candidate.
- V3 candidates may be useful as path-width or regime classifiers even when direction is not stable.

So the correct stance is: `3/8` blocks alpha/model claims; it does not block candidate-registry work. The next evaluation must directly measure half-life decay, phase robustness, residual/context control, and path-width classification.

## Next Evaluation Table Design

The next model evaluation should have two layers:

1. Paired metric rows: one row per candidate/model pair, fold, symbol, horizon, barrier, label target, sample mode, phase, lag, and regime gate.
2. Candidate aggregate rows: phase distribution, pass rate, median delta, IQR, decay shape, failure flags, and final V3 status.

Required field groups:

| group | required columns | purpose |
| --- | --- | --- |
| identity | `run_tag`, `eval_version`, `candidate_id`, `baseline_model`, `candidate_model`, `feature_set_id` | Every metric maps to an exact candidate and model pair. |
| time split | `fold`, `train_start_utc`, `train_end_utc`, `valid_start_utc`, `valid_end_utc`, `forward_window_id` | Prevents mixing in-sample, validation, and next-window results. |
| label | `symbol`, `horizon_minutes`, `barrier_bps`, `label_target`, `vol_adj_barrier_bps` | Allows 5m/15m/30m/60m/240m, not only 1h/4h. |
| sample/phase | `sample_mode`, `phase_id`, `phase_rows`, `effective_independent_rows`, `top_decile_count` | Makes thin phase samples visible. |
| half-life | `half_life_assumption_minutes`, `feature_lag_minutes`, `decay_slope`, `lag0_metric`, `lag60_metric` | Separates short-lived effect from slow regime persistence. |
| regime gate | `regime_gate_id`, `regime_gate_expr`, `gate_rows`, context/RV/common-mode buckets | Forces predeclared gates. |
| proper scores | `delta_log_loss`, `delta_brier`, `delta_calibration_slope` | Keeps model validation honest. |
| ranking/path | `delta_top_decile_lift`, `delta_upper_edge_minus_lower_edge`, `median_future_return_top_decile_bps` | Preserves ranking/path diagnostics without calling them alpha. |
| residual/context | `residual_label_target`, `delta_residual_ic`, future market/meme/SOL context fields | Controls broad BONK/market regime. |
| path-width | `delta_path_width_bps`, `upper_lift`, `lower_lift`, `path_width_not_direction_flag` | Keeps movement-width states separate from direction states. |
| decision | `validation_level`, `status`, `failure_flags`, `reasoned_candidate_score`, `next_window_pre_registered` | Converts evidence into V3 candidate status. |

Suggested acceptance read:

- Stable model: needs negative median `delta_log_loss` and `delta_brier`, positive phase pass rate, no forward-fold reversal, and enough phase rows.
- Short-half-life research candidate: may survive proper-score instability only if lag/decay shape is explicit, phase robustness is reported, and next-window gate is pre-registered.
- Path-width candidate: can survive without directional stability when both upper and lower movement probabilities rise and `path_width_not_direction_flag=true`.
- Discard/wait: tiny bucket/phase rows, post-hoc gate, market-wide-only effect, or side-semantics dependency without confirmation.

## Bottom Line

Current evidence says: keep BONK V3 as candidate validation design, not a tradable model. The next table should make sample size, paired deltas, phase offset, short-half-life decay, regime gate, and path-width status first-class columns so that later results cannot hide behind one good fold or one lucky phase.
