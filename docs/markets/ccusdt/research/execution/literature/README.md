# CCUSDT Taker Execution Literature Sources

Status: `20260602_literature_source_index`.

This folder stores source-available optimal-execution references for the
CCUSDT taker / exit / admission research line. The arXiv source packages were
downloaded with:

```powershell
Invoke-WebRequest https://arxiv.org/e-print/<arxiv_id>
tar -xf <arxiv_id>.tar.gz
```

## Source-Available Papers

| paper | arXiv | local source |
| --- | --- | --- |
| Cont and Kukanov, optimal order placement | `1210.1625` | `taker_execution_sources/cont_kukanov_2012_optimal_order_placement/OrderRouting.tex` |
| Gueant, Lehalle, Fernandez-Tapia, limit-order liquidation | `1106.3279` | `taker_execution_sources/gueant_lehalle_fernandez_tapia_2011_limit_order_liquidation/Best_execution_review2.tex` |
| Bulthuis et al., market/limit orders with fill uncertainty | `1604.04963` | `taker_execution_sources/bulthuis_etal_2016_fill_uncertainty_limit_market_orders/Optimal_Execution_v17__July_23_2016_.tex` |
| Lee and Lee, liquidity risk in a diffusive order book | `2004.10951` | `taker_execution_sources/lee_lee_2020_liquidity_risk_diffusive_order_book/Hyoeun_Kiseop_ArxivVer.tex` |
| Toth et al., adaptive liquidity taking | `1403.0842` | `taker_execution_sources/toth_etal_2014_adaptive_liquidity_taking/Adaptive_Liquidity.tex` |

## No Public LaTeX Source Found

| paper | status | useful public source |
| --- | --- | --- |
| Harris and Hasbrouck, market vs limit orders | SSRN page reports not available for download | `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7758` |
| Obizhaeva and Wang, supply/demand dynamics | PDF/SSRN/NBER available, no arXiv source found | `https://www.nber.org/papers/w11444.pdf` |
| Maglaras, Moallemi, Zheng, queueing LOB execution | PDF/SSRN available, no arXiv source found | `https://moallemi.com/ciamac/papers/fluid-ms-2015.pdf` |

## CCUSDT Reading Note

The project-level synthesis is:

```text
docs/markets/ccusdt/research/execution/v1-taker-execution-literature-notes-20260602.md
```

