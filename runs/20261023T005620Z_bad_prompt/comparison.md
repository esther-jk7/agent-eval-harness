## Eval comparison

Baseline: `20261023T005243Z_baseline` (d2273b9-dirty)  
Candidate: `20261023T005620Z_bad_prompt` (11608a8-dirty)

| Metric | Baseline | Candidate | Change |
|---|---|---|---|
| judge_pass_rate | 1.0 | 1.0 | +0 |
| consistency_rate | 1.0 | 1.0 | +0 |
| scorer_agreement | 1.0 | 0.875 | -0.125 |
| error_rate | 0.0 | 0.0 | +0 |
| latency_p50_ms | 623.3 | 642.4 | +19.1 |
| latency_p95_ms | 2672.9 | 2798.2 | +125.3 |
| tokens_out_total | 1737 | 2574 | +837 |

**Output drift**
- sec-002: similarity 0.47
- sec-003: similarity 0.36
- sec-005: similarity 0.15
- sec-006: similarity 0.13

**Result: PASS**