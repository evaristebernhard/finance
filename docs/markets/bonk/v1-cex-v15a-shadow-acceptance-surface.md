# BONK V15A Shadow Acceptance Surface

- generated_at: `2026-05-15T15:37:39Z`
- run_tag: `20260514_bonk_v10_stage1_pilot`
- output_tag: `20260515_bonk_v10_stage1_pilot`
- guardrail: `research_only_not_trading_rule_no_execution_recommendation_no_alpha_claim`
- stance: research-only; no trading advice, no execution recommendation, no alpha claim.

## Purpose

V15A is a diagnostic layer over the frozen V14 state policy. It reports `p_fill`, `p_up_first`, `p_down_first`, support, and expected net by state bucket without creating entry rules or trade candidates.

## Inputs

- V10c panel files: `86`
- V10c panel rows streamed: `1945574`
- V10c symbols: `BONK1MUSDC,BONK1MUSDT`
- V10c dates: `2026-05-06,2026-05-07,2026-05-08,2026-05-09,2026-05-10,2026-05-11,2026-05-12`
- V14 calibration rows: `30840`
- V14 validation decision rows: `72000`
- V14 min support: `20`

## Shadow Surface Read

- validation `p_up_first > 0` rows: `0` of `72000`
- validation positive expected-net rows: `0` of `72000`
- validation expected net mean / max: `-0.5227` / `0.0000` bps
- validation `p_fill` mean / max: `0.0324` / `0.1864`
- validation mechanical adverse-first-only rows: `47072`
- validation mechanical zero-fill-or-zero-path rows: `24890`
- validation insufficient-support rows: `38`

The validation surface is therefore not merely weak after cost. The frozen V14 validation buckets mechanically collapse before entry selection: every validation row has `p_up_first = 0`. Some states still fill, but when they fill the calibrated first passage is adverse-first only; other states have zero fill/path mass.

## Mechanically Collapsing Validation States

| Diagnostic | Rows | Side | State Bucket | p_fill | p_up | p_down | Support | Exp Net | Top Date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mechanical_adverse_first_only | 12759 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong\|micro=... | 0.0291 | 0.0000 | 1.0000 | 120.1 | -0.3783 | 2026-05-11 |
| mechanical_zero_fill_or_zero_path_mass | 7222 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong\|micro=... | 0.0000 | 0.0000 | 0.0000 | 58.6 | -0.0002 | 2026-05-11 |
| mechanical_adverse_first_only | 5870 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=toxic\|cross=neg_strong\|micro=... | 0.0445 | 0.0000 | 1.0000 | 83.1 | -0.8769 | 2026-05-11 |
| mechanical_adverse_first_only | 5317 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=toxic\|cross=neg_strong | 0.0555 | 0.0000 | 1.0000 | 177.4 | -0.9119 | 2026-05-10 |
| mechanical_adverse_first_only | 4699 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong\|micro=... | 0.1076 | 0.0000 | 1.0000 | 66.0 | -0.8661 | 2026-05-10 |
| mechanical_adverse_first_only | 4037 | long | vol=normal\|spread=normal\|liq=deep | 0.0029 | 0.0000 | 1.0000 | 699.2 | -0.2870 | 2026-05-12 |
| mechanical_adverse_first_only | 3427 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong | 0.0637 | 0.0000 | 1.0000 | 427.5 | -0.6934 | 2026-05-10 |
| mechanical_zero_fill_or_zero_path_mass | 3019 | long | vol=normal\|spread=normal\|liq=deep\|pressure=neg\|tox=quiet\|cross=neg | 0.0000 | 0.0000 | 0.0000 | 61.1 | -0.1026 | 2026-05-12 |
| mechanical_zero_fill_or_zero_path_mass | 2920 | long | vol=normal\|spread=normal\|liq=deep\|pressure=neg\|tox=toxic\|cross=neg | 0.0000 | 0.0000 | 0.0000 | 62.5 | -0.4087 | 2026-05-12 |
| mechanical_zero_fill_or_zero_path_mass | 2341 | long | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong\|micro=... | 0.0000 | 0.0000 | 0.0000 | 65.7 | -0.5193 | 2026-05-10 |

## Merely Weak After Cost

Calibration has `131` support-qualified rows with nonzero favorable first passage but nonpositive expected net. These are weak after cost in train-only calibration, not transferred validation opportunities. The calibration file also has `19` positive expected-net rows, but they are thin-support train-only rows and do not appear in validation with nonzero `p_up_first`.

| Rows | Side | State Bucket | p_fill | p_up | p_down | Support | Gross | Exp Net |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 34 | short | vol=normal\|spread=normal\|liq=deep | 0.8618 | 0.0062 | 0.1858 | 946.6 | -0.5151 | -2.5449 |
| 24 | long | vol=normal\|spread=normal\|liq=deep | 0.0038 | 0.2833 | 0.7167 | 1049.3 | -0.0013 | -0.0103 |
| 20 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong | 0.8176 | 0.0101 | 0.2005 | 349.9 | -0.5101 | -2.4358 |
| 14 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong\|micro=... | 0.4975 | 0.0489 | 0.0662 | 105.9 | -0.0702 | -1.2400 |
| 13 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=toxic\|cross=neg_strong | 0.8497 | 0.0096 | 0.2233 | 304.1 | -0.6038 | -2.6059 |
| 9 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=quiet\|cross=neg_strong\|micro=... | 1.0000 | 0.0622 | 0.0769 | 23.1 | -0.0341 | -2.3890 |
| 8 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=toxic\|cross=neg_strong\|micro=... | 0.8132 | 0.0615 | 0.2625 | 27.0 | -0.4043 | -2.3206 |
| 3 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=mixed\|cross=neg_strong | 0.8718 | 0.0294 | 0.2353 | 39.0 | -0.5461 | -2.5981 |
| 3 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=toxic\|cross=neg_strong\|micro=... | 0.4500 | 0.0519 | 0.2000 | 100.0 | -0.1638 | -1.2151 |
| 3 | short | vol=normal\|spread=normal\|liq=deep\|pressure=neg_strong\|tox=toxic\|cross=neg_strong\|micro=... | 1.0000 | 0.0227 | 0.1591 | 44.0 | -0.4885 | -2.8437 |

## Definitions

- `mechanical_zero_fill_or_zero_path_mass`: support exists, but the resolved calibration has no fill, favorable first passage, or adverse first passage mass for the side/marker/wing.
- `mechanical_adverse_first_only`: fills exist, `p_up_first = 0`, and adverse first passage is effectively locked at `p_down_first >= 0.95`.
- `mechanical_no_favorable_first_passage`: fills exist and `p_up_first = 0`, but not all filled mass is adverse-first.
- `mechanical_insufficient_support`: V14 could not resolve enough calibration support.
- `weak_after_cost`: favorable first passage exists, but expected net is nonpositive after the V14 cost/expectancy accounting.

## Outputs

- buckets: `date\bonk_v15a_shadow_acceptance_surface_buckets_20260515_bonk_v10_stage1_pilot.csv`
- collapse: `date\bonk_v15a_shadow_acceptance_surface_collapse_20260515_bonk_v10_stage1_pilot.csv`
- summary: `date\bonk_v15a_shadow_acceptance_surface_summary_20260515_bonk_v10_stage1_pilot.csv`
- panel_profile: `date\bonk_v15a_shadow_acceptance_surface_panel_profile_20260515_bonk_v10_stage1_pilot.csv`
- manifest: `date\bonk_v15a_shadow_acceptance_surface_manifest_20260515_bonk_v10_stage1_pilot.csv`

## Bottom Line

V15A confirms V14's failure is structural at the same-marker acceptance surface. The validation state buckets are mechanically collapsing, while the weak-after-cost states are confined to train calibration and do not transfer into validation. The next research branch should change timing or object definition rather than tune V14 gates.
