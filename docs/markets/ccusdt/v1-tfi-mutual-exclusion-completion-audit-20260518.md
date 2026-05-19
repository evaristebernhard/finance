# CCUSDT V1 TFI Mutual-Exclusion Completion Audit

Status: `20260518_ccusdt_v1_tfi_mutual_exclusion_completion_audit_v1`.

Objective audited:

```text
对 CCUSDT/CEX L2 短周期 TFI 结构做 entry 级互斥分解，并从一阶公式与金融含义解释各结构的父子关系、成本拖累和右尾来源
```

## Success Criteria

| Requirement | Evidence | Status |
| --- | --- | --- |
| Entry-level mutual-exclusion decomposition exists | `scripts/ccusdt_v1_tfi_mutual_exclusion.py`; source keys are `fold,date,entry_row`; rerun output: `unique_entries=3052 buckets=28 pairwise=75` | pass |
| Decomposition output tables exist | `date/ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`; `date/ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`; `date/ccusdt_v1_tfi_pairwise_overlap_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`; `date/ccusdt_v1_tfi_mutual_exclusion_summary_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.json` | pass |
| Unique entry accounting is verified | Current inspection: `membership_rows=3052`, `unique_composite_entry_keys=3052`, `bucket_rows=28`, `fold3_bucket_rows=10`, `pairwise_rows=75`, `fold3_pairwise_rows=25` | pass |
| Parent-child relations are explained | `docs/markets/ccusdt/v1-tfi-mutual-exclusion-interpretation-20260518.md`, section `Parent-Child Map`; includes `short_flat` inside `follow_flat` `673/716`, `long_flat` inside `follow_flat` `456/493`, `short_stale25` inside `event_active` `131/131` | pass |
| First-principles formula is present | `Core Formula` section defines `r_i(h)`, `G_i(h)`, `N_i(h)`, `Edge(S)`, `Tradable(S)` | pass |
| Financial meaning of each structure is explained | `Trigger Meaning` and `What Each Structure Means` sections explain `follow_flat`, `short_flat`, `long_flat`, `event_active`, and `short_stale25` | pass |
| Cost drag is separated from gross signal | Interpretation report states positive gross median can become negative net median after roughly `2` bps cost; fold3 bucket table separates `gross_mean`, `gross_median`, `net_mean`, `net_median`, and total net | pass |
| Right-tail source is quantified | `Right-Tail Source` section reports top `10%` net / total net: `follow_flat=1.5327`, `short_flat=1.5397`, `long_flat=1.7587`, `event_active=1.1612`, `short_stale25=1.1273` | pass |
| Original structures are not discarded | Interpretation report explicitly treats `follow_flat` as parent, `short_flat`/`long_flat` as directional children, `event_active` as state slice, `short_stale25` as nested high-quality child | pass |
| Reproducibility checked | `python -m py_compile scripts\ccusdt_v1_tfi_mutual_exclusion.py` passed; `python scripts\ccusdt_v1_tfi_mutual_exclusion.py --run-tag 20260518_ccusdt_v1_tfi_mutual_exclusion_v1` reran successfully | pass |

## Files Inspected

- `docs/markets/ccusdt/v1-tfi-mutual-exclusion-20260518_ccusdt_v1_tfi_mutual_exclusion_v1.md`
- `docs/markets/ccusdt/v1-tfi-mutual-exclusion-interpretation-20260518.md`
- `scripts/ccusdt_v1_tfi_mutual_exclusion.py`
- `date/ccusdt_v1_tfi_membership_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`
- `date/ccusdt_v1_tfi_mutual_buckets_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`
- `date/ccusdt_v1_tfi_pairwise_overlap_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.csv`
- `date/ccusdt_v1_tfi_mutual_exclusion_summary_20260518_ccusdt_v1_tfi_mutual_exclusion_v1.json`
- `date/ccusdt_v1_tail_stop_deep_dive_summary_20260517_ccusdt_tail_stop_deep_dive_v1.csv`

## Completion Finding

The objective is achieved for the current research scope. The deliverables cover entry-level mutual exclusion, first-principles formulas, financial meaning, parent-child relations, cost drag, and right-tail source. No execution recommendation is made.

