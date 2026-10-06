# Simulated trial results (results-1.0.0)

1000 complete simulated trials per accrual scenario and true effect (seed 20260927).
True effect: S_experimental(t) = S_control(t) ** HR (proportional hazards on the whole EFS curve). The protocol's design hypothesis is never used as the truth.
Asset evidence on the effect: insufficient evidence: shown for reference, not used (user decision 2026-09-27) (2 comparisons).

## Probability of success of the primary analysis by true hazard ratio

| true HR | accrual_124_per_year_derived |
| ---: | ---: |
| 0.500 | 0.994 ± 0.002 |
| 0.550 | 0.970 ± 0.005 |
| 0.600 | 0.911 ± 0.009 |
| 0.650 | 0.768 ± 0.013 |
| 0.700 | 0.639 ± 0.015 |
| 0.750 | 0.444 ± 0.016 |
| 0.800 | 0.306 ± 0.015 |
| 0.850 | 0.199 ± 0.013 |
| 0.900 | 0.108 ± 0.010 |
| 0.950 | 0.057 ± 0.007 |
| 1.000 | 0.034 ± 0.006 |
| 1.100 | 0.009 ± 0.003 |
| 1.200 | 0.001 ± 0.001 |
| 1.300 | 0.000 ± 0.000 |

## Checks against the protocol's own design

- accrual_124_per_year_derived: type I error at HR 1: simulated 0.034 ± 0.006 (expected 1.0, consistent: False)

## Stated limitations

- EFS events are observed at their true time: detection at the next scheduled assessment is not applied
- enrollment (= randomization): the protocol does not state the EFS time origin (user decision 2026-09-27)
- Strata are unresolved for enrolled subjects, so the stratified log-rank test runs unstratified.
- Only the randomized arms open in this protocol version are simulated.
- Secondary endpoints are computed from the simulated patients by the endpoint stage.
- Adverse events come from adult class-level evidence and are identical in distribution for both arms.
