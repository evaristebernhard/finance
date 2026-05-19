# AGENTS.md

This repo is a private CHOG/Monad data-collection workspace. Read this file first in every new Codex session so the user does not need to restate the current plan.

## Current Goal

Move CHOG v1 collection from full per-block header backfill to a memecoin strategy-first path:

```text
logs -> event_block_headers -> tx_receipts -> memecoin features -> quality check
```

The latest live handoff is in:

```text
docs/handoff/live-collection.md
```

The supporting strategy/runbook handoff is in:

```text
docs/handoff/memecoin-strategy.md
docs/runbooks/chog-memecoin-collection.md
docs/runbooks/chog-v1-backfill.md
```

The human-readable docs index is in `docs/README.md`. Start there when the task is documentation or orientation.
The current dirty-worktree organization map is in:

```text
docs/handoff/workspace-cleanup-20260519.md
```

## Documentation Organization Note

Latest documentation direction from the user: keep frontend/backend engineering,
historical research, and factor analysis separated. For BONK UI/API work, start
with:

```text
docs/engineering/README.md
docs/markets/bonk/v1-replay-workbench.md
docs/markets/bonk/README.md
```

For factor research, start with:

```text
docs/research/README.md
```

Treat older CHOG and MON/USDC handoffs as collection/research references unless
the user explicitly asks to continue those data paths.

## Important Local Context

- This handoff copy has been running on a stronger Windows machine. If moved back to the Raspberry Pi-class machine, avoid heavy `cargo build --bins`, `cargo test`, or large RPC/data jobs unless the user explicitly asks.
- `cargo test --manifest-path crate/Cargo.toml` passed after the receipt batching/receipt-only optimization.
- `cargo build --manifest-path crate/Cargo.toml --bin receipt_sample` passed after the receipt optimization.
- Local git is intended for categorized checkpoint commits. Keep private `.env*` ignored.
- Current clean memecoin-path coverage is about thirty days: `66507947..72992946`.
- Latest event-factor research artifacts are:
  - `docs/research/chog/2026-05-09-cost-aware-event-factors.md`
  - `docs/research/chog/2026-05-09-event-factor-phenomena.md`
  - `date/chog_event_cost_labels_20260509.csv`
  - `date/chog_first_principles_factor_scores_20260509.csv`
  - `date/chog_cost_aware_ml_summary_20260509.csv`
  - `date/chog_event_factor_phenomena_20260509.csv`
  - `date/chog_event_factor_path_profiles_20260509.csv`
  - `date/chog_event_factor_daily_concentration_20260509.csv`
  - `date/chog_event_factor_untradable_reasons_20260509.csv`
- Current factor-research stance: continue event-level, first-principles factor analysis; do not start maker/LP/two-sided quoting research unless the user explicitly redirects. The main observed phenomenon is `large_buy_p90` as a 6h delayed-continuation candidate, not an immediate trading rule.
- Latest user direction: pivot executable strategy research toward MON/USDC instead of CHOG because CHOG liquidity is too small. The first Python sampler remains at `scripts/mon_usdc_v1_swap_sample.py`, and a Rust V1 collector path now exists in `crates/mon_usdc_collectors`.
- Latest MON/USDC v1 artifacts:
  - `docs/markets/mon-usdc/v1-data-plan.md`
  - `docs/markets/mon-usdc/v1-factor-analysis.md`
  - `docs/markets/mon-usdc/v1-enrichment-report.md`
  - `date/mon_usdc_pool_candidates_20260509.csv`
  - `date/mon_usdc_v1_swaps_sample_20260509.csv`
  - `data/mon_usdc/v1/raw/pool_snapshots`
  - `data/mon_usdc/v1/raw/pool_swap_logs`
  - `data/mon_usdc/v1/raw/event_block_headers`
  - `data/mon_usdc/v1/raw/tx_receipts`
  - `data/mon_usdc/v1/raw/tx_bodies`
  - `data/mon_usdc/v1/_work`
  - Initial top pools: Uniswap v3 `0x659bD0BC4167BA25c62E05656F78043E7eD4a9da`, Pancake v3 `0x63e48B725540A3Db24ACF6682a29f877808C53F2`, TraderJoe v2.2 `0x5AFD3EC861f6104af26e8755aBcc1f876de77620`, and TraderJoe v2.2 `0x5E60BC3F7a7303BC4dfE4dc2220bdC90bc04fE22`.
  - Pancake v3 on Monad uses an extended Swap topic `0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83`, not the standard Uniswap v3 Swap topic.
  - TraderJoe/LFJ v2.2 uses Liquidity Book metadata (`getTokenX()` / `getTokenY()`) and Swap topic `0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70`; `bytes32` amounts are decoded as X in the low 128 bits and Y in the high 128 bits.
  - Latest range-scoped Rust MON/USDC result completed `54574455..60190454`: `pool_swap_logs=634009`, `event_block_headers=383994`, `tx_receipts=493760`, `missing_event_headers=0`, `missing_receipts=0`, and `mon_usdc_quality_check` passed with `files=33013 rows=1511798`. An earlier `592099` swap-row estimate was superseded by the local range-scoped quality result `634009`.
- MON/USDC tx body collector engineering status:
  - `mon_usdc_tx_body_sample` now supports `--workers`; CLI default is `1`.
  - `scripts/run_mon_usdc_enrichment.ps1` defaults tx bodies to `--workers 4 --batch-size 50 --rpc-batch-size 50`.
  - Queue cache lives in `data/mon_usdc/v1/_work/mon_usdc_tx_body_queue_v1_<from>_<to>.tsv`.
  - Full-window dry-run for `54574468..73366454` now succeeds using the compact TSV queue cache: `source swap txs=1701634`.
  - Canonical `raw/tx_bodies` is drained for the full `54574468..73366454` queue: all bounded batches plus `--max-txs 744634` completed with `0` failed rows.
  - Latest dry-run after drain: `source swap txs=1701634`, `existing tx body hashes=1701634`, `queued hashes after dedupe=0`, `raw/tx_bodies parquet files=33930`.
  - Validation passed: `cargo fmt --all --manifest-path Cargo.toml`, `cargo test -p mon_usdc_collectors -p mon_usdc_research`, and `cargo build --release -p mon_usdc_collectors -p mon_usdc_research`.
  - Copied-root RPC smoke for `73365455..73366454` wrote 81 tx bodies into `target/tmp`, 2 parquet parts, 0 failed rows, about 32 rows/sec, and rerun dry-run queued 0.
  - Next enrichment continuation should move to `mon_usdc_receipt_log_bundle`; tx bodies no longer need more collection for this window unless new swap logs are added.
- Latest CCUSDT/CEX L2 V1 TFI strategy-optimization status:
  - Start with `docs/markets/ccusdt/v1-current-tfi-strategy-handoff-20260518.md`.
  - Then read `docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md`; the active model is now path-first, not aggregate-Pareto-first.
  - This is the active CCUSDT branch from the latest conversation; it supersedes the older v2 execution no-go framing for current TFI strategy work unless the user explicitly redirects back to v2.
  - Canonical failure row to remember: `2026-05-09 / entry_row=1615412 / 11_r5_frames / short` reached `MFE=+12.5612bps` in `4.7051s`, then ended at `R_60=-27.8923bps`; with exposure `8`, target PnL was `-242.4187`. This is a release/decay plus sizing problem, not a simple bad-entry problem.
  - Current model family:
    - `A_t = 1{R5 > 1}` where `R5` uses only entries already closed before the current entry.
    - `B_t = 1{frames_since_mid_change >= q90}`.
    - Four mutually exclusive cells: `00`, `10`, `01`, `11`.
    - Final size: `w_t = b_t * gamma_{A_tB_t} * psi_t * phi_t`.
    - `R5` is only a shape ratio; decompose it into `Delta_k=P_k-N_k`, `E_k=P_k+N_k`, and `Z_k=Delta_k/sqrt(E_k+eps)`.
  - Do not discard states only because `net_median < 0`; net median is already cost-adjusted and this branch is right-tail/left-tail-control oriented.
  - Do not call zero fee misleading: `C_fee=0` is the current venue-fee baseline. A reasonable strategy should still be chosen under an extra pressure term `y_i(c)=R_i(exit)-C_fee-c`, with `c>0` reserved for spread/fill/latency/adverse selection and post-release decay.
  - Do not treat `C=0` sizing as the mechanism. It removes explicit fee only; spread/fill/latency/adverse selection and post-release decay remain separate.
  - Latest path-casebook classification is `docs/markets/ccusdt/v1-tfi-path-casebook-20260519_ccusdt_v1_tfi_path_casebook_v1.md`, generated by `scripts/ccusdt_v1_tfi_path_casebook_classes.py`.
    - A case is a path mechanism, not a losing label; profitable entries can be cases too.
    - Counts on `1455` entries: `non_case=738`, `no_release_flat=558`, `fast_release_reversal=41`, `large_release_plateau_decay=25`, `late_release_collapse=93`.
    - C=0 stored-exposure weighted gross: non-case `+10454.4421`, no-release `-1812.0376`, fast-reversal `-936.2399`, large-plateau `+306.4902`, late-release `+892.1041`.
    - Canonical placements: `1615412` and `2377379` are `fast_release_reversal`; `2361187` is `large_release_plateau_decay`; `1604781/1580108/1642948/2032427/2577885` are `no_release_flat`; `1785626/2334597/2540829` are `late_release_collapse`.
  - Latest small path manager is `docs/markets/ccusdt/v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md`, generated by `scripts/ccusdt_v1_tfi_small_path_manager.py`.
    - Do not treat broad `pm_full_tiny` or `pm_drawdown_plateau` as the answer; they overcut right tail.
    - Current candidate is `pm_11_drawdown_h4_peakguard`: only manage `11_r5_frames`, exit when `H>=4` and `D>=max(2,0.35H)`, but for small releases require the peak not be an opening flicker: `H<8 => tau_H>=1.5`.
    - C=0 stored-exposure result: fixed60 total `8904.7590`; `pm_11_drawdown_h4_peakguard` total `9554.1874`, delta `+649.4284`, q90 retention `0.9966`, action exit rate `2.82%`, positive days `12/12`.
    - Case transfer for the candidate: non-case `-438.1403`, no-release `0`, fast-reversal `+605.7351`, large-plateau `+346.6153`, late-release `+135.2182`.
    - It rescues `1615412`, `2377379`, and `2361187`; remaining notable overcut is `2583437`, where early drawdown precedes a much larger late continuation.
    - Deep dive for `2583437` is `docs/markets/ccusdt/v1-tfi-2583437-path-deep-dive-20260519.md`: special shape is dormant vacuum -> first release -> drawdown/reset -> multi-pulse continuation; it has the largest sample-wide `H60-H20` at `110.2681bps`.
  - Latest post-exit re-trigger diagnostic is `docs/markets/ccusdt/v1-tfi-post-exit-retrigger-diagnostic-20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.md`, generated by `scripts/ccusdt_v1_tfi_post_exit_retrigger_diagnostic.py`.
    - This asks whether a fresh second trigger is observable after a natural drawdown exit; do not reinterpret it as "the first exit was wrong".
    - Strict 5s rule uses `Q_i(5)>=0.7`, strict post-exit `F_i(5)>0` over `0<u<=5`, and `C_i(5)>=1`.
    - On `41` drawdown exits: predicted retriggers `1`, productive labels `6`, TP `1`, FP `0`, FN `5`, precision `1.0000`, recall `0.1667`.
    - The only strict 5s re-trigger is `2583437`: `obs_qi5=0.8876`, `obs_tfi_sum=+11`, `obs_reclaim=1.6094`, future MFE after 5s `+95.7742`, future final after 5s `+50.0836`.
    - Negative controls: `2377379` has favorable queue but negative post-exit same-side TFI; `1615412` has a bounce but bad queue/flow; `2361187` lacks post-exit flow/reclaim. All are rejected.
  - Latest post-exit watcher is `docs/markets/ccusdt/v1-tfi-post-exit-watcher-20260519_ccusdt_v1_tfi_post_exit_watcher_v1.md`, generated by `scripts/ccusdt_v1_tfi_post_exit_watcher.py`.
    - This is a watcher after exit, not an exit override. It separates `impulse_5s` from `absorb_reclaim`.
    - Absorption branch requires `Q_i(5)>=q_a`, post-exit `F_i(5)<0`, then a reclaim of at least `2bps` from the reset low, with no new low beyond `L_i(5)-5`, at least `5s` left, and no chasing above post-exit `+5bps`.
    - `impulse_only`: `1` trigger, weighted final `+220.9383`, no negative trigger.
    - Cleaner watcher `watcher_q70_absorb_reclaim2`: `3` triggers (`2583437`, `2322885`, `2379419`), weighted final `+522.1939`, worst trigger `+87.6881`, negative triggers `0`, manager total `9554.1874 -> 10076.3813`.
    - Higher-recall sensitivity `watcher_q65_absorb_reclaim2`: `5` triggers, weighted final `+803.2748`, worst trigger `+32.7318`, negative triggers `0`, manager total `9554.1874 -> 10357.4622`; it additionally opens `2340079` and `2361187`.
    - Important controls remain closed under both q70 and q65: `1615412`, `2377379`, `2383289`, and `2540829`. Treat q70 as the cleaner candidate and q65 as sensitivity, not live-ready.
  - Latest watcher-aware Pareto is `docs/markets/ccusdt/v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md`, generated by `scripts/ccusdt_v1_tfi_watcher_pareto.py`; it supersedes the earlier A/B-only watcher Pareto and the 7x sensitivity because public Bullish CC/USDT spot/margin docs support a 3x cap, not the perpetuals 7x cap.
    - Scope is the full scored four-cell universe: `3365` entries over `2026-05-04..2026-05-17`; counts are `00_none=1234`, `10_r5_only=1796`, `01_frames_only=135`, `11_r5_frames=200`.
    - Path overlay coverage: `1455` path-manager rebuilt rows and `1910` fixed60 fallback rows. `00_none` is included for gamma/concurrency/risk; rows without rebuilt paths do not get watcher logic.
    - Full anchor is `gamma00=1`, `gamma10=0.75`, `gamma01=0.25`, `gamma11=4`. At this anchor, q70 improves manager-only total `13277.3761 -> 13799.5700`, delta `+522.1939`, but max concurrency is `18`, so 100-budget + 3x scaled total is only `2299.9283`.
    - Cleaner q70 scaled leader under 3x: `manager_plus_q70_watcher` with `gamma00=1.25`, `gamma10=0.75`, `gamma01=0`, `gamma11=0.75`; raw total `6042.8705`, mean `3.4965`, worst day `+8.2022`, entry worst `-76.0697`, max concurrency `3.375`, scaled100 `5371.4405`.
    - At the q70 scaled leader, `00_none` contributes `+1935.3368` raw PnL at exposure `793.75` and mean `2.4382`; `01_frames_only` is dropped at C=0 under the 3x cap.
    - q65 sensitivity leader has scaled100 `5418.2873`, only `+46.8468` over q70, so do not promote q65; it remains recall sensitivity.
    - Under 1bps pressure, q70 still prefers the same low-concurrency point (`scaled100=3832.8849`); under 2bps pressure it drops `gamma00` and shifts to `gamma00=0`, `gamma10=1.25`, `gamma01=0.75`, `gamma11=1.5`, scaled100 `1999.7536`.
    - Walk-forward sanity chooses `manager_only` through `2026-05-14`, then q70 on `2026-05-15..2026-05-17`; treat this as historical sanity, not live readiness.
  - Latest 3x capacity-manager diagnostic is `docs/markets/ccusdt/v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md`, generated by `scripts/ccusdt_v1_tfi_capacity_manager.py`.
    - It reframes the leverage issue as an overlap allocator: `sum_open w_tilde <= 3`. Global `scaled100` is a conservative lower bound because one peak interval scales every leg in history.
    - For the cleaner q70 point `gamma00=1.25, gamma10=0.75, gamma01=0, gamma11=0.75`, raw total is `6042.8705`, max concurrency is `3.375`, global downscale is `5371.4405`, and online FIFO/arrival clip is `6038.2000` with only `4` clipped legs and `0` skipped legs.
    - For high-gamma q70 `gamma00=1.25, gamma10=2, gamma01=1, gamma11=5`, online FIFO reaches `12556.9297` versus raw `21096.4649`, but clips `240` legs, skips `26`, and has `leg_worst=-146.1132`; do not promote without pressure, OOS, and single-leg-tail review.
    - Pressure sanity for the low-concurrency q70 point under online FIFO: `C=0 total 6038.2000, worst day +8.2022`; `C=1 total 4308.0750, worst day -68.7978`; `C=2 total 2577.9500, worst day -145.7978`.
  - Latest leverage-constrained strategy optimization is `docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md`, generated by `scripts/ccusdt_v1_tfi_leverage_constrained_opt.py`.
    - It fixes the modeling mistake where high-concurrency intervals made a single global `gamma01` delete all `01_frames_only` entries.
    - Model: current q70 core keeps `gamma00=1.25, gamma10=0.75, gamma11=0.75`; `01` becomes an idle-capacity sleeve `w01=min(b_i gamma01, [3-L(t_i^-)-m]_+)`.
    - Historical C=0: core-only online total `6038.2000`; `idle01_g1_r0` total `6907.5648`, delta `+869.3648`, worst day `+48.3285`, positive days `14/14`, leg worst `-84.5942`.
    - Historical C=0 displacement: `idle01_g1_r0` adds `216.75` actual 01 exposure while reducing core exposure by only `4.125` (`1.90%` displacement ratio), so it mostly consumes idle leverage rather than stealing core capacity.
    - 2026-05-18 OOS C=0: core-only `415.8276`; `idle01_g1_r0` `472.5926`, delta `+56.7649`. Under pressure: C=1 delta `+39.3899`, C=2 delta `+22.0149`.
    - Treat `idle01_g1_r0` as a research candidate/upper sleeve, not live-ready; it adds more clipped legs (`29` historical C=0) and has slightly worse leg tail than core-only.
  - Latest 2026-05-18 OOS current-strategy check is `docs/markets/ccusdt/v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md`, generated by `scripts/ccusdt_v1_tfi_current_strategy_oos.py`.
    - 2026-05-18 Bullish `CCUSDT` `trades`, `book_ticker`, and `incremental_book_L2` were downloaded; the fixed-factor panel run tag is `20260519_ccusdt_fixed_factors_oos_day20260518_v1`.
    - Locked cleaner q70 3x strategy, C=0 online FIFO clip: `304` entries, actual total `415.8276` weighted log-bp units, exact simple bp-units `416.6424`, approximate account simple return `4.2459%`, max concurrency `3.0`, clipped legs `3`, skipped legs `1`, leg worst `-21.1977`.
    - Pressure sensitivity on the same locked cleaner q70 online rule: `C=1 total 257.7026`; `C=2 total 99.5776`.
    - Watcher triggers on 2026-05-18 were `0`, so this OOS day mostly tests the base entry/path-manager/capacity policy, not post-exit re-entry.
    - Do not call this live-ready: it is one fresh OOS day and the new evaluator should be treated as a research harness, not a margin-account simulator.
  - Reference C=0 four-quadrant sizing rerun / 7x sensitivity is `docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md`.
    - It allows `gamma00` and uses zero-fee scored entries plus a 60s-concurrency 7x leverage diagnostic; do not treat it as the current CC/USDT spot/margin cap unless venue/account evidence shows 7x is actually available for CC/USDT.
    - Raw walk-forward chosen `gamma=(1,2,1,4)` has total `15664.1450`, worst day `+277.4534`, positive days `9/9`, but max concurrent exposure `18` caps scale at `7/18=0.3889`.
    - Under 100 bp-unit loss budget plus 7x cap, `locked_baseline_all_1x` has the highest simple fixed-policy scaled total (`8230.8434`); high-gamma variants are concurrency-capped.
    - Earlier zero-fee `interpretable_grid_pareto` diagnostics are archived under `docs/markets/ccusdt/archive/diagnostics/` because that family fixed `gamma00=0` and is not the current four-quadrant answer.
  - Latest interpretable grid/Pareto search tested `16960` candidates with prior-date quantile thresholds only:
    - Old anchor `gamma10=0.75`, `gamma01=0.25`, `gamma11=4`: total `6808.4686`, mean `4.4171bps`, worst day `-58.2736`, positive days `8/9`.
    - Pareto/risk-score leader `gamma10=1.25`, `gamma01=0.75`, `gamma11=5`, with `closed10_score_abs >= Q30_train`: total `9001.3476`, mean `5.0248bps`, worst day `+12.8156`, positive days `9/9`.
    - More conservative point `gamma10=1.25`, `gamma01=0.25`, `gamma11=5`, same strength gate: total `8819.5895`, mean `5.0372bps`, worst day `+23.5851`, positive days `9/9`.
    - No-strength high-gamma point has total `9123.4940` but worst day `-167.3131`, so absolute-strength gating is structural.
  - Latest scripts:
    - `scripts/ccusdt_v1_tfi_price_trailing_param_research.py`
    - `scripts/ccusdt_v1_tfi_release_decay_factor_analysis.py`
    - `scripts/ccusdt_v1_tfi_path_casebook_classes.py`
    - `scripts/ccusdt_v1_tfi_small_path_manager.py`
    - `scripts/ccusdt_v1_tfi_post_exit_retrigger_diagnostic.py`
    - `scripts/ccusdt_v1_tfi_post_exit_watcher.py`
    - `scripts/ccusdt_v1_tfi_watcher_pareto.py`
    - `scripts/ccusdt_v1_tfi_capacity_manager.py`
    - `scripts/ccusdt_v1_tfi_leverage_constrained_opt.py`
    - `scripts/ccusdt_v1_tfi_current_strategy_oos.py`
    - `scripts/ccusdt_v1_tfi_exit_walkforward.py`
    - `scripts/ccusdt_v1_tfi_interpretable_grid_pareto.py`
    - `scripts/ccusdt_v1_tfi_worst_day_frontier.py`
    - `scripts/ccusdt_v1_tfi_strategy_sizing_opt.py`
    - `scripts/ccusdt_v1_tfi_pretrade_identification.py`
    - `scripts/ccusdt_v1_tfi_momentum_conversion_math.py`
  - Latest reports:
    - `docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md`
    - `docs/markets/ccusdt/v1-tfi-0509-high-chop-deep-dive-20260518_ccusdt_v1_tfi_0509_high_chop_deep_dive_v1.md`
    - `docs/markets/ccusdt/v1-tfi-release-decay-factor-analysis-20260518_ccusdt_v1_tfi_release_decay_factor_v1.md`
    - `docs/markets/ccusdt/v1-tfi-path-casebook-20260519_ccusdt_v1_tfi_path_casebook_v1.md`
    - `docs/markets/ccusdt/v1-tfi-small-path-manager-20260519_ccusdt_v1_tfi_small_path_manager_v1.md`
    - `docs/markets/ccusdt/v1-tfi-post-exit-retrigger-diagnostic-20260519_ccusdt_v1_tfi_post_exit_retrigger_v1.md`
    - `docs/markets/ccusdt/v1-tfi-post-exit-watcher-20260519_ccusdt_v1_tfi_post_exit_watcher_v1.md`
    - `docs/markets/ccusdt/v1-tfi-watcher-pareto-20260519_ccusdt_v1_tfi_watcher_pareto_4quad_lev3_v1.md`
    - `docs/markets/ccusdt/v1-tfi-capacity-manager-20260519_ccusdt_v1_tfi_capacity_manager_lev3_v1.md`
    - `docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md`
    - `docs/markets/ccusdt/v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md`
    - `docs/markets/ccusdt/v1-tfi-exit-walkforward-20260518_ccusdt_v1_tfi_exit_walkforward_v1.md`
    - `docs/markets/ccusdt/v1-tfi-price-trailing-param-research-20260519_ccusdt_v1_tfi_price_trailing_param_v1.md`
    - `docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260519_ccusdt_v1_tfi_strategy_sizing_zero_fee_4quad_lev7_v1.md`
    - `docs/markets/ccusdt/v1-tfi-interpretable-grid-pareto-20260518_ccusdt_v1_tfi_interpretable_grid_pareto_v1.md`
    - `docs/markets/ccusdt/v1-tfi-worst-day-frontier-20260518_ccusdt_v1_tfi_worst_day_frontier_v1.md`
    - `docs/markets/ccusdt/v1-tfi-strategy-sizing-opt-20260518_ccusdt_v1_tfi_strategy_sizing_opt_v2.md`
  - Important caveat: the daily Pareto leader has a larger single-entry left tail, but the deeper issue is fixed-horizon release/decay. Next work should keep candidate exit families small: fixed 30s left-tail baseline, prior-threshold release/trailing, and 5s..20s flow-confirmed hold.
- Latest CCUSDT/CEX L2 V2 execution-research status:
  - Start with `docs/markets/ccusdt/v2-current-execution-no-go-handoff.md`.
  - Current active objective is not achieved: the framework is systematized, but stable real-cost `>2bps` capture is not present.
  - Key docs:
    - `docs/markets/ccusdt/v2-executable-research-framework.md`
    - `docs/markets/ccusdt/v2-goal-completion-audit-20260518_ccusdt_v2_fill_repair_audit_all_practical_v1.md`
    - `docs/markets/ccusdt/v2-l2-queue-fill-20260518_ccusdt_v2_l2_queue_fill_all_practical_v1.md`
    - `docs/markets/ccusdt/v2-taker-fallback-audit-20260518_ccusdt_v2_taker_fallback_audit_v1.md`
    - `docs/markets/ccusdt/v2-execution-failure-decomposition-20260518_ccusdt_v2_execution_failure_decomp_v1.md`
    - `docs/markets/ccusdt/v2-structural-pivot-proposals-20260518.md`
    - `docs/markets/ccusdt/v2-queue-release-pivot-20260518_ccusdt_v2_queue_release_pivot_fast_v1.md`
    - `docs/markets/ccusdt/v2-liquidity-envelope-audit-20260518_ccusdt_v2_liquidity_envelope_audit_v1.md`
    - `docs/markets/ccusdt/v2-local-universe-inventory-20260518_ccusdt_v2_local_universe_inventory_v1.md`
    - `docs/markets/ccusdt/v2-universe-preflight-20260518_ccusdt_v2_universe_preflight_v1.md`
    - `docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_smoke_v1.md`
    - `docs/markets/ccusdt/v2-universe-size-probe-20260518_ccusdt_v2_universe_size_probe_small_tier_v1.md`
  - Hard no-go evidence:
    - Framework scorecard: `0` promoted rows; `4` research-continue rows only.
    - All-practical L2 queue fill: `45/45` framework bins no-go over `6447` validation entries.
    - Fill-aware repair scan: `0/3741` post-hoc filters pass execution gates.
    - Taker fallback: `45/45` bins no-go; `0` taker promote-gate rows.
    - Execution decomposition: best maker per-signal net is `-0.0038bps` versus the `2bps` target.
    - Queue-release pivot prototype: `0/24` rows pass; best mean is `-1.7573bps`.
    - Liquidity-envelope audit: `liquidity_envelope_no_go`; median daily median spread is `2.0148bps`; `0/17` days pass `$100` top-depth support.
    - Local Bullish L2 universe inventory: `single_or_no_symbol_only`; only `CCUSDT` is local core L2-ready, so universe selection is data-blocked locally.
    - Bullish universe preflight dry-run: `11` metadata-available scheduled symbols, `3` missing requested symbols, `561` planned file jobs, no files downloaded.
    - Bullish universe size smoke: first date `33/33` planned files available, estimated `3.61GB`; full universe data step should be staged deliberately.
    - Small-tier universe size probe: `SUIUSDC`, `DOGEUSDC`, `PEPE1MUSDC`, `SHIB1MUSDC`, and `WIFUSDC` full-window core L2 totals about `0.40GB`; `SUIUSDC`/`DOGEUSDC` are the practical pilot candidates, while `PEPE/SHIB/WIF` look near-empty and need row validation.
  - Do not continue CCUSDT by tuning TP/SL grids, narrowing post-hoc filters, or switching maker/taker assumptions on the same candidates. Only resume if new out-of-sample days, real venue fee/fill/latency evidence, a structurally different signal, or a broader instrument universe is introduced.
- The user wants self-use zip archives to include local `.env*` and `data/`. Do not assume zips must be sanitized unless the user asks for a shareable package.

## Implemented Code Path

Key files:

```text
crate/src/bin/event_header_sample.rs
crate/src/bin/receipt_sample.rs
crate/src/bin/chog_collect.rs
crate/src/bin/dex_rebuild.rs
crate/src/bin/chog_quality_check.rs
crate/src/memecoin_features.rs
crate/src/lib.rs
scripts/run_chog_memecoin_days.ps1
Cargo.toml
crates/finance_chain_core
crates/mon_usdc_collectors
```

Implemented behavior:

```text
chog_collect --header-mode event|full|skip
event is default
event_header_sample writes raw/event_block_headers
receipt_sample defaults to --source-scope chog-pool-txs
receipt_sample defaults to --timestamp-source local-first
receipt_sample supports --rpc-batch-size and --receipt-only
dex_rebuild memecoin-features writes derived/memecoin_event_features and derived/memecoin_hourly_features
chog_quality_check includes the new raw/derived datasets
```

## Packaging

There are two package intents:

```text
finance_chain_memecoin_strategy_20260508.zip
```

This earlier package is a small source/docs snapshot and intentionally excludes `data/`, private env files, `.git/`, and `crate/target/`.

For the user's own migration/archive package, create a full handoff zip that includes local `.env*`, `data/`, `date/`, source, docs, scripts, and lightweight root metadata, while excluding:

```text
.git/
crate/target/
target/
existing .zip/.tar/.tar.gz archives
```

Suggested command pattern:

```bash
zip -r finance_chain_full_handoff_YYYYMMDD.zip \
  AGENTS.md Cargo.toml crate crates docs scripts data date \
  .env.local.example .env.chog.local.example .gitignore rpc.txt rpc.monad.capacity.tsv github_monad_alchemy_repos.txt \
  -x 'crate/target/*' 'target/*' '.git/*' '*.zip' '*.tar' '*.tar.gz'
```

If real private env files such as `.env.chog.local` exist, include them only for the user's self-use archive and do not print their contents.

## Next Validation

If changing code, validate with:

```bash
cargo fmt --manifest-path crate/Cargo.toml
cargo test --manifest-path crate/Cargo.toml
```

For the next data continuation, use:

```text
FROM=66291947
TO=66507946
DAY_TAG=day20260406
```

Receipts should usually use `--receipt-only --rpc-batch-size 50` for memecoin feature collection unless the user needs transaction body fields.

## Safety

- Do not print private RPC keys, env contents, OpenAI tokens, or browser session JSON.
- Do not delete `data/` or existing archives unless the user explicitly asks.
- Do not run destructive Git commands.
- Preserve existing user data and local generated datasets.
