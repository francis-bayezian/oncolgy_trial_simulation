# Stress tests: NCT06604442 (base v4.1.0)

## (a) Eligibility: one criterion removed at a time (counterfactual feasibility)

The three criteria excluding the most generated patients over 50 replicates. Criteria the generated patients cannot decide are resolved by the screen-pass calibration (A16): their exclusion rates are calibrated, not evidence about that criterion. Enrolment time does not change in these scenarios (the accrual model's rate does not depend on the eligible share).

| Scenario | Criterion text | Eligible % p10 / p50 / p90 | Screened to reach the target p10 / p50 / p90 |
| --- | --- | --- | --- |
| baseline (all criteria) |  | 78.2 / 78.8 / 79.3 | 61 / 65 / 71 |
| without EL011 | previously undergone a cystectomy or have renal failure or have other conditions | 80.6 / 81.2 / 81.6 | 59 / 64 / 68 |
| without EL009 | 4. Patients participating in an interventional clinical trial within 30 days and | 80.7 / 81.2 / 81.7 | 60 / 63 / 68 |
| without EL003 | Low PSA BCR defined as PSA ≤0.5 ng/mL. | 80.7 / 81.2 / 81.7 | 60 / 63 / 69 |

## (b) Recruitment: slow / central / fast accrual

Rates are the historical accrual model's p10 / p50 / p90 for this protocol (4.2 / 16.4 / 65.9 patients per year). Time to enrol 52 participants, Poisson arrivals, 100 replicates.

| Scenario | Patients / year | Months to enrol the target p10 / p50 / p90 | Trials enrolled within 12 months |
| --- | ---: | --- | ---: |
| slow | 4.2 | 119.6 / 152.5 / 181.1 | 0/100 |
| central | 16.4 | 30.3 / 38.7 / 46.0 | 0/100 |
| fast | 65.9 | 7.6 / 9.6 / 11.5 | 96/100 |

## (c) Endpoint completeness: extra loss of the paired endpoint (missing completely at random)

| Endpoint source | Extra loss | Usable pairs p10 / p50 / p90 | Trials reaching significance |
| --- | ---: | --- | ---: |
| design | 0% | 50 / 51 / 52 | 74/100 |
| design | 10% | 43 / 46 / 49 | 74/100 |
| design | 20% | 37 / 41 / 44 | 64/100 |
| literature | 0% | 50 / 51 / 52 | 100/100 |
| literature | 10% | 43 / 46 / 49 | 100/100 |
| literature | 20% | 37 / 41 / 44 | 100/100 |
| prestart | 0% | 50 / 51 / 52 | 100/100 |
| prestart | 10% | 43 / 46 / 49 | 100/100 |
| prestart | 20% | 37 / 41 / 44 | 100/100 |

## (d) Effect-size curve (the protocol's test, design SD)

Paired Wilcoxon signed-rank, alpha 0.05, SD of differences 25.15; 4,000 simulated trials per point.

| True effect | Power at n = 52 (MC SE) | Power at n = 47 |
| ---: | --- | --- |
| 0 | 0.022 (0.002) | 0.021 |
| 2.5 | 0.104 (0.005) | 0.094 |
| 5 | 0.279 (0.007) | 0.254 |
| 7.5 | 0.547 (0.008) | 0.507 |
| 10 | 0.783 (0.007) | 0.735 |
| 12.5 | 0.939 (0.004) | 0.910 |
| 15 | 0.985 (0.002) | 0.974 |
