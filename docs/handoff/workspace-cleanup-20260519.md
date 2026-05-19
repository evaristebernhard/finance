# Workspace Cleanup Map 2026-05-19

Status: `workspace_cleanup_branch`.

Branch:

```text
codex/workspace-cleanup-20260519
```

This file records how the current dirty workspace should be read before adding
the next standalone replay/paper-exchange system.

## Principle

Do not treat every untracked file as the same kind of work.

```text
research outputs != reusable scripts != engineering systems != local caches
```

The cleanup direction is:

```text
keep source/docs that define current research state
ignore local caches and heavy downloaded/generated data
stage/commit by domain, not with one blind `git add .`
```

## Current Domains

### CCUSDT V1 TFI Research

Primary first read:

```text
docs/markets/ccusdt/README.md
docs/markets/ccusdt/v1-tfi-current-research-map-20260519.md
docs/markets/ccusdt/v1-tfi-leverage-constrained-opt-20260519_ccusdt_v1_tfi_leverage_constrained_opt_v1.md
docs/markets/ccusdt/v1-tfi-current-strategy-oos-day20260518-20260519_ccusdt_v1_tfi_current_strategy_oos_day20260518_v1.md
```

Key scripts:

```text
scripts/ccusdt_v1_tfi_leverage_constrained_opt.py
scripts/ccusdt_v1_tfi_current_strategy_oos.py
scripts/ccusdt_v1_tfi_capacity_manager.py
scripts/ccusdt_v1_tfi_watcher_pareto.py
```

Current modeling stance:

```text
path-first TFI model
3x leverage cap as first-order capacity constraint
01_frames_only is an idle-capacity sleeve, not a dead cell
C=0 is venue-fee baseline; C=1/C=2 are pressure reserves
```

### CCUSDT V2 Execution References

The V2 docs are retained as no-go/execution-envelope references. They should
not be the first read for current TFI work.

Canonical first read remains:

```text
docs/markets/ccusdt/v2-current-execution-no-go-handoff.md
```

### MON/USDC Enrichment

This is a separate engineering/data path, not part of CCUSDT TFI. Keep it in
the Rust workspace and MON/USDC docs.

Primary docs:

```text
docs/markets/mon-usdc/README.md
docs/markets/mon-usdc/v1-data-plan.md
docs/markets/mon-usdc/v1-enrichment-report.md
```

Primary code areas:

```text
crates/mon_usdc_collectors/
crates/mon_usdc_research/
scripts/run_mon_usdc_enrichment.ps1
```

### Frontend / Backend Workbench

The existing frontend/backend directories are legacy workbench/application
material. They should not be used as the base for the future independent
CCUSDT replay exchange unless explicitly migrated.

Future replay exchange should live under a new top-level path such as:

```text
systems/ccusdt_replay_exchange/
```

### Local Caches And Heavy Artifacts

These should remain local and ignored:

```text
data/
date/
tmp/
target/
crate/target/
.playwright-cli/
/archive/
/arxiv/
/output/
/CryoBacktester/
/external/github_lob_research/
```

Private runtime files remain unprinted and should not be blindly staged:

```text
.env*
rpc.txt
```

## Suggested Commit Buckets

Use categorized checkpoint commits instead of one giant mixed commit:

```text
1. docs: refresh market research handoffs and indexes
2. research(ccusdt): add TFI path/capacity/leverage reports and scripts
3. data(mon-usdc): add enrichment collectors and docs
4. app: add existing replay workbench frontend/backend, if still wanted
5. chore: ignore local caches and generated outputs
```

Do not stage private config or local data bundles unless the user explicitly
asks for a self-use archive.

