# Polylens External Repo Index

Date: 2026-06-08

This page indexes local Git submodule references for Polymarket / Polylens-like
wallet intelligence research. The goal is not to copy an outside product. The
goal is to keep a clean map of designs that can improve the local read-only
Polymarket wallet factor lane:

```text
scripts/polymarket_wallet_factor_probe.py
docs/markets/onchain/polymarket-wallet-factor-lab-20260607.md
docs/markets/onchain/strategy-factor-scout-20260607.md
```

All external repos below are references only. Do not run their services,
install their dependencies, or import execution paths into this repo without a
separate review.

## Direct Copyability Systems

| Repo | Local path | Useful design points | Local use |
|---|---|---|---|
| [KSonny4/trader_evaluator](https://github.com/KSonny4/trader_evaluator) | `external/polymarket_research_repos/KSonny4__trader_evaluator` | Full funnel from event scoring to wallet discovery, long-term tracking, paper copy, WScore, copy fidelity, follower slippage, and exclusion reasons. | Best blueprint for turning the current one-shot probe into a closed-loop evaluator. |
| [YOPHackathon/PolyCopy](https://github.com/YOPHackathon/PolyCopy) | `external/polymarket_research_repos/YOPHackathon__PolyCopy` | Wallet crawler, metrics agent, copy-trading simulation with latency/slippage/spread estimates, and LLM due-diligence stages. | Good reference for separating metric computation from narrative wallet review. |

## Smart-Money Consensus

| Repo | Local path | Useful design points | Local use |
|---|---|---|---|
| [Gonzih/poly-scout](https://github.com/Gonzih/poly-scout) | `external/polymarket_research_repos/Gonzih__poly-scout` | Lightweight smart wallet scan, ROI proxy, consensus map, late-money detection, Data/Gamma API use. | Closest compact analogue to `wallet_scores.csv` and `follow_candidates.csv`. |
| [gavindumas-gif/polymarket-smart-money-tracker](https://github.com/gavindumas-gif/polymarket-smart-money-tracker) | `external/polymarket_research_repos/gavindumas-gif__polymarket-smart-money-tracker` | Local-first SQLite pipeline, raw/normalized event separation, consensus scoring, alerts, dashboard, health checks. | Useful for durable state, dedupe, restart safety, and alert history. |

## Behavioral Factor Research

| Repo | Local path | Useful design points | Local use |
|---|---|---|---|
| [darrnhard/polymarket-smart-money](https://github.com/darrnhard/polymarket-smart-money) | `external/polymarket_research_repos/darrnhard__polymarket-smart-money` | Deep wallet behavior study: lead/follow hierarchy, burst windows, category specialization, DCA sessions, copy window realism. | Best reference for new wallet factors beyond simple recent-trade edge. |

## Full Workbench And Market Surface

| Repo | Local path | Useful design points | Local use |
|---|---|---|---|
| [NYTEMODEONLY/polyterm](https://github.com/NYTEMODEONLY/polyterm) | `external/polymarket_research_repos/NYTEMODEONLY__polyterm` | Broad terminal workbench: wallet analysis, risk scoring, order book tools, alerts, local SQLite, agent-facing tool contracts. | Product-shape reference for a future Polylens workbench, not the first implementation target. |
| [nimoolee/polymarket-radar](https://github.com/nimoolee/polymarket-radar) | `external/polymarket_research_repos/nimoolee__polymarket-radar` | CLOB-first dashboard with spread, liquidity, stale price, lane grouping, scanner controls, and time-aware market logic. | Good reference for improving `market_suitability.csv` with tradable book quality. |

## Wallet Cluster Risk

| Repo | Local path | Useful design points | Local use |
|---|---|---|---|
| [gozuray/Cluster-Analyzer](https://github.com/gozuray/Cluster-Analyzer) | `external/polymarket_research_repos/gozuray__Cluster-Analyzer` | EVM wallet cluster graph, relayer-style fan-out, timing bursts, fund concentration, cluster-level risk scoring. | Add optional cluster-risk penalties before trusting a wallet as independent smart money. |

## Do Not Port Blindly

Keep these out of the local Polylens line unless explicitly reviewed:

- live order execution, signing, custody, relayer, or account setup paths;
- promotional claims, fee-referral copy, or guaranteed-return language;
- generic agent wrapper text that does not improve wallet copyability evidence;
- full hosted product flows when a read-only local table is enough;
- leaderboards without delayed-copy paper evidence;
- whale-size heuristics that ignore wallet history, market rules, and book capacity.

## Local Integration Direction

The next local design step should be small and evidence-first:

```text
current public trades/activity/books
-> wallet copyability features
-> market suitability features
-> delayed-copy paper ledger
-> copy fidelity and follower slippage
-> follow candidates with exclusion reasons
```

The local lane should remain read-only until paper records show stable positive
edge after delay, spread, slippage, and capacity checks.
