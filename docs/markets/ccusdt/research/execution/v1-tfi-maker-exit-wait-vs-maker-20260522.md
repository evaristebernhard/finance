# CCUSDT q70 idle01_g1 maker exit: wait vs maker decomposition

Run id: `maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522`

This diagnostic tests whether the current maker-first exit candidate is really
passive execution alpha or merely a delayed taker exit.

For an exit decision at time $t$:

$$
Y_0 = Y^T_t, \qquad
Y_\tau = Y^T_{t+\tau}, \qquad
Y_M = Y^M_t.
$$

For fill proxy $k$ with indicator $I^k_t(\tau)$:

$$
\Delta^k_t =
Y^k_t - Y_0 =
\underbrace{(Y_\tau-Y_0)}_{\text{wait / fallback}}
+
\underbrace{I^k_t(\tau)(Y_M-Y_\tau)}_{\text{passive fill increment}}.
$$

So if $I^k_t(\tau)=0$ but $\Delta^k_t>0$, the mechanism is not maker fill;
it is the wait/fallback path.

For `fixed30_livecoherent` under `l2_depletion_proxy_v1`, fill rate is 0.00%, final delta is 12.1434, delay-only delta is 12.1434, and passive increment is 0.0000. Mechanism label: `wait/fallback only`.

## Overall decomposition

| exit_profile_source | date | gate_name | exit_model | attempts | exposure | fill_rate | weighted_final_delta_vs_taker_bps | weighted_delay_only_delta_bps | weighted_passive_increment_vs_delay_bps | weighted_selection_cost_bps | weighted_selection_adjusted_delta_bps | mechanism |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | ALL | spread_q90 | l2_depletion_proxy_v1 | 51 | 27.8750 | 0.0000 | 12.1434 | 12.1434 | 0.0000 | 0.0000 | 12.1434 | wait/fallback only |
| fixed30_livecoherent | ALL | spread_q90 | touch_trade_proxy_v1 | 51 | 27.8750 | 0.1176 | 6.0115 | 12.1434 | -6.1319 | 4.4242 | 1.5874 | mixed |
| fixed30_livecoherent | ALL | spread_q90 | trade_queue_proxy_v1 | 51 | 27.8750 | 0.0784 | 9.6039 | 12.1434 | -2.5395 | 0.8318 | 8.7721 | mostly wait |
| fixed45_livecoherent | ALL | spread_q80_same_flow_q70 | l2_depletion_proxy_v1 | 42 | 27.5000 | 0.0714 | 33.4538 | 34.1848 | -0.7310 | 1.2174 | 32.2364 | mostly wait |
| fixed45_livecoherent | ALL | spread_q90 | l2_depletion_proxy_v1 | 17 | 8.5000 | 0.0000 | -0.4803 | -0.4803 | 0.0000 | 0.0000 | -0.4803 | wait/fallback only |
| fixed45_livecoherent | ALL | spread_q80_same_flow_q70 | touch_trade_proxy_v1 | 42 | 27.5000 | 0.1429 | 14.5433 | 34.1848 | -19.6415 | 20.6150 | -6.0717 | mixed |
| fixed45_livecoherent | ALL | spread_q90 | touch_trade_proxy_v1 | 17 | 8.5000 | 0.0588 | -1.2315 | -0.4803 | -0.7512 | 0.7512 | -1.9826 | passive fill hurt |
| fixed45_livecoherent | ALL | spread_q80_same_flow_q70 | trade_queue_proxy_v1 | 42 | 27.5000 | 0.1429 | 14.5433 | 34.1848 | -19.6415 | 20.6150 | -6.0717 | mixed |
| fixed45_livecoherent | ALL | spread_q90 | trade_queue_proxy_v1 | 17 | 8.5000 | 0.0588 | -1.2315 | -0.4803 | -0.7512 | 0.7512 | -1.9826 | passive fill hurt |


## Daily decomposition

| exit_profile_source | date | gate_name | exit_model | attempts | exposure | fill_rate | weighted_final_delta_vs_taker_bps | weighted_delay_only_delta_bps | weighted_passive_increment_vs_delay_bps | weighted_selection_cost_bps | weighted_selection_adjusted_delta_bps | mechanism |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed30_livecoherent | 2026-05-16 | spread_q90 | l2_depletion_proxy_v1 | 12 | 6.8750 | 0.0000 | 0.8406 | 0.8406 | 0.0000 | 0.0000 | 0.8406 | wait/fallback only |
| fixed30_livecoherent | 2026-05-16 | spread_q90 | touch_trade_proxy_v1 | 12 | 6.8750 | 0.0000 | 0.8406 | 0.8406 | 0.0000 | 0.0000 | 0.8406 | wait/fallback only |
| fixed30_livecoherent | 2026-05-16 | spread_q90 | trade_queue_proxy_v1 | 12 | 6.8750 | 0.0000 | 0.8406 | 0.8406 | 0.0000 | 0.0000 | 0.8406 | wait/fallback only |
| fixed30_livecoherent | 2026-05-17 | spread_q90 | l2_depletion_proxy_v1 | 17 | 9.8750 | 0.0000 | 1.9293 | 1.9293 | 0.0000 | 0.0000 | 1.9293 | wait/fallback only |
| fixed30_livecoherent | 2026-05-17 | spread_q90 | touch_trade_proxy_v1 | 17 | 9.8750 | 0.1765 | -0.1180 | 1.9293 | -2.0473 | 0.3396 | -0.4576 | passive fill hurt |
| fixed30_livecoherent | 2026-05-17 | spread_q90 | trade_queue_proxy_v1 | 17 | 9.8750 | 0.1765 | -0.1180 | 1.9293 | -2.0473 | 0.3396 | -0.4576 | passive fill hurt |
| fixed30_livecoherent | 2026-05-18 | spread_q90 | l2_depletion_proxy_v1 | 22 | 11.1250 | 0.0000 | 9.3735 | 9.3735 | 0.0000 | 0.0000 | 9.3735 | wait/fallback only |
| fixed30_livecoherent | 2026-05-18 | spread_q90 | touch_trade_proxy_v1 | 22 | 11.1250 | 0.1364 | 5.2889 | 9.3735 | -4.0846 | 4.0846 | 1.2044 | mostly wait |
| fixed30_livecoherent | 2026-05-18 | spread_q90 | trade_queue_proxy_v1 | 22 | 11.1250 | 0.0455 | 8.8813 | 9.3735 | -0.4922 | 0.4922 | 8.3892 | mostly wait |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | l2_depletion_proxy_v1 | 17 | 8.5000 | 0.0000 | -0.4803 | -0.4803 | 0.0000 | 0.0000 | -0.4803 | wait/fallback only |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | touch_trade_proxy_v1 | 17 | 8.5000 | 0.0588 | -1.2315 | -0.4803 | -0.7512 | 0.7512 | -1.9826 | passive fill hurt |
| fixed45_livecoherent | 2026-05-16 | spread_q90 | trade_queue_proxy_v1 | 17 | 8.5000 | 0.0588 | -1.2315 | -0.4803 | -0.7512 | 0.7512 | -1.9826 | passive fill hurt |
| fixed45_livecoherent | 2026-05-17 | spread_q80_same_flow_q70 | l2_depletion_proxy_v1 | 42 | 27.5000 | 0.0714 | 33.4538 | 34.1848 | -0.7310 | 1.2174 | 32.2364 | mostly wait |
| fixed45_livecoherent | 2026-05-17 | spread_q80_same_flow_q70 | touch_trade_proxy_v1 | 42 | 27.5000 | 0.1429 | 14.5433 | 34.1848 | -19.6415 | 20.6150 | -6.0717 | mixed |
| fixed45_livecoherent | 2026-05-17 | spread_q80_same_flow_q70 | trade_queue_proxy_v1 | 42 | 27.5000 | 0.1429 | 14.5433 | 34.1848 | -19.6415 | 20.6150 | -6.0717 | mixed |


## Interpretation

- `delay_only_delta` is the value of waiting until TTL and then crossing,
  with no maker order.
- `passive_increment_vs_delay` is the incremental value of a passive fill
  compared with that same wait-then-cross path.
- `touch_trade_proxy_v1` is optimistic: any opposite trade reaching the touch
  counts as fill.
- `trade_queue_proxy_v1` is stricter: opposite trade quantity must consume the
  displayed top queue ahead.
- `l2_depletion_proxy_v1` is a fast-line L2 proxy: same-price displayed-size
  depletion can include cancels, so it is diagnostic evidence, not a strict
  private-order fill proof.

## Decision gate

This run does not promote maker-first exit into the strict Runner maker
lifecycle. The current positive fixed30 result is explained by the wait/fallback
term under the stricter L2 proxy, while trade/touch fill proxies show negative
passive increments after the same decomposition.

The next strict-Runner maker implementation should require a prior-date rule
whose L2 or stricter proxy has positive `passive_increment_vs_delay`, acceptable
selection-adjusted delta, and non-trivial fill probability. If the positive
term remains `delay_only_delta`, the correct next model is a conditional
wait/exit-timing controller, not a maker execution controller.

## Files

- Events: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522\maker_exit_wait_vs_maker_events.parquet`
- Daily summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522\maker_exit_wait_vs_maker_daily_summary.csv`
- Overall summary: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522\maker_exit_wait_vs_maker_overall_summary.csv`
- Manifest: `C:\Users\jiang\Desktop\finance_chain_full_handoff_20260508_r2\systems\ccusdt_replay_exchange\runs\maker_exit_wait_vs_maker_q70_idle01_g1_warmup_strict_20260516_18_20260522\summary.json`
