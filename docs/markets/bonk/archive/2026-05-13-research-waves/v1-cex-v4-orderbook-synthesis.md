# BONK V4 Orderbook Synthesis

Status: 2026-05-13. Run tag: `20260513_bullish_l2_basket_price_v1`.

This memo summarizes the orderbook-focused V4 analysis wave. It is not a trading rule, not an execution plan, not a sizing rule, and not an alpha claim.

## Main Answer

Use the orderbook as four things:

1. State filters: what market regime are we in?
2. Path-risk diagnostics: does the path avoid lower-first outcomes?
3. Execution constraints: does displayed depth survive spread, slippage, and lower-first risk?
4. Cross-venue controls: is BONK special, or just venue / meme / market state?

The current strongest object remains:

```text
BONK1MUSDT H4 depth_high + rv_low
BONK1MUSDT H4 depth_high + rv_low + cv_spread
```

But V4 makes the interpretation more precise: this is a deep/quiet orderbook regime with cross-venue state information. It is not a clean quote-to-quote lead-lag or a global model signal.

## What Held Up

Exact labels do not materially change the H4 state. The timestamp-exact audit compared `241,380` rows across BONK1MUSDC/BONK1MUSDT, H1/H4/H12, and 50/100bps barriers. Strict mismatch rate is `0.205%`, and active H4 gate reads changed in `0 / 10` focused symbol/gate combinations.

Missing minutes do not explain the current focus gate. BONK1MUSDC has `99.72%` observed-minute coverage and BONK1MUSDT has `99.84%`; the primary fold2/fold3 BONK1MUSDT H4 gates have `0` affected selected rows out of `1,127`.

The state taxonomy is coherent. The active `depth_high+rv_low+cv_spread` gate has `82.0%` of selected rows in `BONK1MUSDT_S1`, labeled `deep_quiet_wide_common_off_cv_mixed`. This is exactly the kind of orderbook state we expected: deep and quiet, but not necessarily tight or aligned.

## What Did Not Hold Up

Cross-venue is not a clean lead-lag signal. Max quote-lead asymmetry is only `0.0047` Spearman, and every tested lag is classified as `no_clear_quote_leader`. Cross-venue variables are useful as basis-convergence / venue-state controls, not standalone direction predictors.

Adding every orderbook feature is worse than selective use. In the feature-family ablation, `cross_venue` is the cleanest incremental family after context controls, while the combined all-orderbook family underperforms. The practical lesson is to use a small set of interpretable orderbook state variables rather than a large feature dump.

Short horizons are feasible but not automatically tradable. 5m/15m/30m labels with 20/30bps barriers have strong coverage. The best short-horizon bucket reads are mostly spread/depth/activity/microprice state diagnostics; context/RV controls still dominate many proper-score checks.

## Capacity Read

H4 active gates are not zero-capacity, but they are small. Under the displayed-depth stress screen:

- H4 active/mirror gates are classified `capacity_research_ok`.
- Top-of-book envelope is effectively `0`.
- 5-level depth envelope is about `50` quote.
- 25-level wide-stress envelope is about `500` quote.

This keeps the state in execution-research territory. The orderbook suggests where a phenomenon might exist, but it also says the displayed-size envelope is narrow and path risk remains real.

## Practical Interpretation

The orderbook is saying:

```text
when BONK on Bullish is deep, quiet, and in a specific USDC/USDT venue state,
the 4h path is more favorable than average,
mostly through residual-positive behavior and lower-first suppression.
```

It is not saying:

```text
USDC leads USDT, or this minute should be bought, or a large model should trade it.
```

## Promotion Rules

Keep the candidate as `research_state` until all of these pass:

- Timestamp-exact labels are canonical.
- The frozen H4 state survives negative controls and phase rotation.
- BONK remains positive relative to meme / market / SOL context.
- Cross-venue variables add value as controls without becoming a post-hoc direction story.
- Displayed-depth stress gives a nontrivial size envelope.
- A next-window retest confirms the same state without changing thresholds.

## Next Work

1. Move timestamp-exact and short-horizon labels into the Rust/Python canonical pipeline.
2. Rebuild the research panel with exact labels.
3. Rerun V4 orderbook checks with frozen gates.
4. Keep the model feature set small: context + depth/RV + selected cross-venue state + a few short-horizon spread/activity diagnostics.
5. Collect more L2 only after the frozen candidate survives the rebuilt-label rerun.
