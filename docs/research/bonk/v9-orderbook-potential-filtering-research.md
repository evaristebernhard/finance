# BONK V9 Order-Book Potential And Filtering Research

Status: research design notes for the V9 canonical runner. Research infrastructure only: no trading advice, no execution recommendation, and no alpha claim.

## External Practice Review

- GitHub order-book practice is less about isolated indicators and more about replay/fill realism. `hftbacktest` explicitly accounts for limit orders, queue position, and latency using L2/L3 tick data, which is a useful warning that maker rows without queue/latency stress are optimistic.
- The GitHub `limit-order-book` topic contains reconstructors, heatmaps, feature-analysis projects, matching engines, RL environments, and DeepLOB-style prediction code. That suggests the V9 pipeline should separate book reconstruction/state estimation from execution simulation instead of blending them into one flat feature table.
- Multi-Level Order-Flow Imbalance (MLOFI) treats imbalance as a vector over book levels rather than a single top-of-book scalar. V9 only has derived 5/25-depth summaries, so it uses a compressed potential-field proxy and marks this as an approximation until deeper raw book data is approved.
- Latent liquidity work distinguishes the displayed book from hidden/intended liquidity and studies how latent volume reveals itself near the current price. V9 uses `kalman_pressure`/`yau_pressure` as observable-book latent-pressure proxies, not as a full latent order-book estimator.
- Resiliency literature frames the book as a replenishment process after liquidity shocks. This maps directly to V9 `cancellation_withdrawal_energy`, `replenish_relaxation`, `event_time_decay`, and `post_event` anchors.
- Queue-reactive Hawkes work combines current queue state with self-exciting order-flow memory. V9 does not fit a full Hawkes process yet; it approximates this with event-time decay plus train-fitted first-passage/energy anchors.
- Kalman/EKF/UKF are appropriate baselines for latent pressure when observations are noisy. V9 includes train-fitted one-dimensional Kalman-family pressure filters over the potential observation.
- Yau-Yau nonlinear filtering is a density-filtering framework built around offline propagation and online observation correction. V9 includes a lightweight Yau-Yau-inspired log-domain correction and restart heuristic, explicitly labeled experimental rather than a faithful DMZ PDE solver.

## Source Pointers

- hftbacktest: https://github.com/nkaz001/hftbacktest
- GitHub limit-order-book topic: https://github.com/topics/limit-order-book
- Multi-Level Order-Flow Imbalance: https://arxiv.org/abs/1907.06230
- Latent liquidity revelation: https://arxiv.org/abs/1808.09677
- Queue-reactive Hawkes models for order flow: https://arxiv.org/abs/1901.08938
- Measuring the resiliency of an electronic limit order book: https://www.sciencedirect.com/science/article/pii/S1386418106000528
- Improved Yau-Yau nonlinear filtering reference: https://arxiv.org/abs/2509.16896

## V9 Definitions

- `Phi_bid`: compressed demand-side potential from queue pressure, microprice/WOBI impulse, bid replenishment, flow pressure, cross-venue forcing, and regime pressure.
- `Phi_ask`: compressed supply/resistance potential from opposite queue pressure, cancellation/withdrawal energy, spread-depth resistance, and opposing cross-venue/regime pressure.
- `net_potential = Phi_bid - Phi_ask`: signed book pressure.
- `potential_gradient` and `potential_curvature`: first and second differences in signed pressure.
- `energy_release`: absolute potential movement plus cancellation, replenishment, notional burst, and spread expansion.
- `liquidity_barrier`: spread/depth/fragility resistance proxy.
- `queue_depth_pressure`: bid/ask 25-level pressure proxy.
- `cancellation_withdrawal_energy`: ask/bid withdrawal and spread-expansion pressure.
- `replenish_relaxation`: bid/ask replenishment and spread compression.
- `cross_venue_forcing`: basis, microprice disagreement, lead-lag catch-up, and relative market/meme pressure.
- `event_time_decay`: Hawkes-like memory proxy for recent energy release.
- `kalman_pressure`: train-fitted latent pressure baseline.
- `yau_pressure`: experimental online log-domain nonlinear correction with restart when the state leaves a train-fitted local region.

## Movable Anchors

- `pre_event`: pressure gradient builds before a barrier break.
- `event`: energy release coincides with signed potential pressure.
- `post_event`: replenishment/relaxation after a shock.
- `first_passage`: hidden pressure crosses train-fitted state boundaries.
- `potential_barrier_break`: signed potential clears liquidity resistance.

## Canonical Discipline

All thresholds, filter parameters, buckets, and anchor selectors are fit on train folds only and applied to validation folds after the purge gap. Python is reserved for visualization/search only; V9 executable labels and backtests are Rust canonical.