# Frozen simulation vs the completed trial: NCT06604442

Observed: Eur J Nucl Med Mol Imaging. 2026 Feb 23;53(6):3529-3541 (PMC13121232; doi 10.1007/s00259-025-07732-y). Frozen outputs verified against the freeze manifests: all checksums match.

## Step 13: synthetic comparator vs the actual comparator (aggregate level)

Public data are aggregates (no individual patients), so this is location, dispersion, contrast and direction, not individual-level prediction.

| Analysis | Comparator median (IQR) | Paired contrast (median) | Direction | Significant (alpha 0.05) |
| --- | --- | --- | --- | --- |
| **Observed trial** | **29.0 (18.9-40.8)** | **15.1** | lower with index in 53/55 | yes (p <0.001) |
| SCA-A, independent model (P2 evidence): synthetic comparator (median over 100 trials) | 43.9 (23.8-78.8) | 30.4 (p10-p90 28.1-32.3) | comparator higher in 100/100 trials | 100/100 trials |
| SCA-B, self-consistency check (same P1 evidence as the simulated truth; not independent): synthetic comparator (median over 100 trials) | 25.9 (18.1-36.8) | 11.9 (p10-p90 10.3-13.5) | comparator higher in 100/100 trials | 100/100 trials |
| SCA-R, reverse independent check (P1 model, P2 truth): synthetic comparator (median over 100 trials) | 26.1 (18.2-36.6) | 11.9 (p10-p90 10.3-13.4) | comparator higher in 100/100 trials | 99/100 trials |
| simulated truth, `design` source (frozen) | - | 9.8 (p10-p90 5.5-14.1); observed at percentile 94 | - | 74/100 trials |
| simulated truth, `literature` source (frozen) | - | 11.9 (p10-p90 9.7-14.6); observed at percentile 94 | - | 100/100 trials |
| simulated truth, `prestart` source (frozen) | - | 32.2 (p10-p90 23.1-40.2); observed at percentile 0 | - | 100/100 trials |

Index exposure (flotufolastat), frozen evidence F1 simulated: median 12.7 (IQR 7.7-20.6); observed 10.9 (6.0-18.5).

## Step 14: feasibility reality check (separate from the comparator check)

Where the observed conduct falls in the frozen predictive distributions (percentile 0-100; outside 5-95 is outside the simulated plausible range).

| Quantity | Frozen simulation p10 / p50 / p90 | Observed | Percentile of observed |
| --- | --- | --- | ---: |
| screen-pass (CONTEXTUAL, denominators differ: simulated = eligible share of 10,000 generated candidates; observed = dosed among formally screened, after any site prescreening) | 78.1% / 78.7% / 79.2% | 92.5% (62 dosed of 67 screened) | not a calibration check |
| missing paired endpoints (share of enrolled) | 0.0% / 1.9% / 3.8% | 11.3% (7/62: 5 without the flotufolastat scan; 2 non-evaluable scans) | 100 |
| usable pairs | 50 / 51 / 52 (of 52 enrolled) | 55 (of 62 dosed; the trial over-enrolled) | - |
| **months to enrol, full prespecified accrual uncertainty** (frozen planning report: rate uncertainty x Poisson arrivals) | 9.3 / 37.5 / 150.7 | ~8 (October 2024 to June 2025, 9 sites) | 8 |
| months to enrol, central accrual rate only (replicates) | 31.7 / 37.4 / 45.8 | ~8 | 0 |
| months to enrol, slow accrual (4.2/year) | 119.6 / 152.5 / 181.1 | ~8 | - |
| months to enrol, central accrual (16.4/year) | 30.3 / 38.7 / 46.0 | ~8 | - |
| months to enrol, fast accrual (65.9/year) | 7.6 / 9.6 / 11.5 | ~8 | - |
