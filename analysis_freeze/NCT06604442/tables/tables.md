# Table 1. Provenance of every simulated quantity

| Quantity | Protocol value | Evidence / source | Generated quantity | Assumption | Used in |
| --- | --- | --- | --- | --- | --- |
| Eligibility rules | 13 inclusion/exclusion criteria (StudySpec, 100% faithful) | protocol | per-patient eligibility of 10,000 generated patients | criteria patients cannot carry resolved to the registry screen-pass rate (A16) | feasibility |
| Age, sex, race, ethnicity | men >= 18 years | simulation parameter asset V3 (registry baselines) | baseline demographics | - | feasibility |
| Performance status | - | registry baseline ECOG (prostate, phase 4) | per-patient ECOG | - | feasibility |
| Evaluable target | 52 (60 to be screened) | protocol section 15 | enrolment stops at 52 participants | - | feasibility |
| Accrual rate | 10 centers (protocol) | historical accrual model historical accrual model operational-2.0.0 (completed and terminated non-holdout trials) | Poisson arrivals, median 16.4/year (p10-p90 4.2-65.9) | site count from the protocol; rate uncertainty from the model | feasibility |
| Exposures and order | piflufolastat then flotufolastat 1-10 days later | protocol | two records per participant | exits person-level (L044) | feasibility, SCA |
| Exits (withdrawal, AE stop, death) | - | registry disposition rates (prostate, phase 4) | per-participant exits in the procedure window | registry whole-trial rates scaled to the window (A22) | feasibility |
| Flotufolastat bladder SUVmean | - | F1: Kuo et al., Mol Imaging Biol 2023 (n=718) | per-participant index value | lognormal from median and IQR | SCA (truth and models) |
| Piflufolastat bladder SUVmean (truth) | - | P1: preprint 2025-05 (n=50, independent) | per-participant comparator value (masked) | lognormal from median and range | SCA truth |
| Piflufolastat bladder SUVmean (independent model) | - | P2: Donswijk 2022 SUVmax (n=51) x 0.731 | synthetic comparator SCA-A | SUVmax-to-SUVmean ratio from flotufolastat | SCA comparator |
| Within-patient correlation | - | none reported | log-scale correlation of the two exposures | 0.5 (A29) | SCA truth |
| Design effect | mean paired difference 10, SD 25, 80% power | protocol (68Ga-PSMA-11 stand-in) | design-assumption endpoint source | reported as a sensitivity, never as truth | feasibility (design check) |
| Primary analysis | two-sided paired Wilcoxon signed rank, alpha 0.05 | protocol | per-trial p-value and success | - | feasibility, SCA |

# Table 2. Frozen simulation vs the completed NCT06604442

| Quantity | Frozen simulation p10 / p50 / p90 | Observed | Percentile of observed | Within p5-p95 |
| --- | --- | --- | --- | --- |
| Screen-pass rate, % (contextual: simulated = eligible share of generated candidates; observed = dosed among formally screened) | 78.1 / 78.7 / 79.2 | 92.5 | not comparable | - |
| Missing paired endpoints, % of enrolled | 0.0 / 1.9 / 3.8 | 11.3 | 100 | no |
| Months to enrol, full prespecified accrual uncertainty (frozen planning report) | 9.3 / 37.5 / 150.7 | 8.0 | 8 | yes |
| Months to enrol, central accrual rate only | 31.7 / 37.4 / 45.8 | 8.0 | 0 | no |
| Paired contrast, median (literature truth) | 9.7 / 11.9 / 14.6 | 15.1 | 94 | yes |
| Paired contrast, median (design assumption) | 5.5 / 9.8 / 14.1 | 15.1 | 94 | yes |
| Synthetic comparator median, SCA-A independent (P2) | 36.4 / 43.9 / 53.8 | 29.0 | 1 | no |
| Synthetic comparator median, SCA-B self-consistency (P1, same evidence as the simulated truth) | 22.8 / 25.9 / 29.2 | 29.0 | 88 | yes |
| Synthetic-comparator contrast, SCA-A independent (P2) | 28.1 / 30.4 / 32.3 | 15.1 | 0 | no |
| Synthetic-comparator contrast, SCA-B self-consistency (P1) | 10.3 / 11.9 / 13.5 | 15.1 | 99 | no |
| Direction (comparator higher) | 100/100 trials (all sources) | 53/55 lower with flotufolastat | - | yes |
| Two-sided rejection at alpha 0.05 (positive-direction success identical here) | literature 100/100; design 74/100; SCA 99-100/100 | yes (p <0.001) | - | yes |
