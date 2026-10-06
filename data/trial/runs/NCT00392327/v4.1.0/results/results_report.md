# Simulated trial results (results-1.0.0)

1000 complete simulated trials per accrual scenario and true effect (seed 20260927).
True effect: S_experimental(t) = S_control(t) ** HR (proportional hazards on the whole EFS curve). The protocol's design hypothesis is never used as the truth.
Asset evidence on the effect: insufficient evidence: shown for reference, not used (user decision 2026-09-27) (2 comparisons).

## Probability of success of the primary analysis by true hazard ratio

| true HR | accrual_35_per_year | accrual_60_per_year |
| ---: | ---: | ---: |
| 0.489 | 0.966 ± 0.006 | 0.960 ± 0.006 |
| 0.500 | 0.961 ± 0.006 | 0.956 ± 0.006 |
| 0.543 | 0.917 ± 0.009 | 0.885 ± 0.010 |
| 0.547 | 0.874 ± 0.010 | 0.899 ± 0.010 |
| 0.550 | 0.894 ± 0.010 | 0.902 ± 0.009 |
| 0.591 | 0.842 ± 0.012 | 0.808 ± 0.012 |
| 0.600 | 0.814 ± 0.012 | 0.813 ± 0.012 |
| 0.650 | 0.700 ± 0.014 | 0.677 ± 0.015 |
| 0.700 | 0.568 ± 0.016 | 0.551 ± 0.016 |
| 0.750 | 0.434 ± 0.016 | 0.433 ± 0.016 |
| 0.800 | 0.328 ± 0.015 | 0.295 ± 0.014 |
| 0.850 | 0.187 ± 0.012 | 0.229 ± 0.013 |
| 0.900 | 0.137 ± 0.011 | 0.122 ± 0.010 |
| 0.950 | 0.077 ± 0.008 | 0.086 ± 0.009 |
| 1.000 | 0.059 ± 0.007 | 0.060 ± 0.008 |
| 1.100 | 0.022 ± 0.005 | 0.019 ± 0.004 |
| 1.200 | 0.003 ± 0.002 | 0.001 ± 0.001 |
| 1.300 | 0.000 ± 0.000 | 0.002 ± 0.001 |

## Checks against the protocol's own design

- accrual_35_per_year: type I error at HR 1: simulated 0.059 ± 0.007 (expected 0.05, consistent: True)
- accrual_35_per_year: power at design alternative HR 0.591 (15% increase in long-term EFS (56% to 71%, RFR=0.591)): simulated 0.842 ± 0.012 (protocol claims at least 0.8) - consistent: True
- accrual_35_per_year: power at design alternative HR 0.543 (17% increase (56% to 73%, RFR=0.543)): simulated 0.917 ± 0.009 (protocol claims at least 0.9) - consistent: True
- accrual_35_per_year: power at design alternative HR 0.547 (14% increase in long-term EFS (65% to 79%, RFR=0.547)): simulated 0.874 ± 0.010 (protocol claims at least 0.8) - the protocol computed this power for a control long-term EFS of 65%; the simulated control is 56%, so the claim is not comparable
- accrual_35_per_year: power at design alternative HR 0.489 (16% increase (65% to 81%, RFR=0.489)): simulated 0.966 ± 0.006 (protocol claims at least 0.9) - the protocol computed this power for a control long-term EFS of 65%; the simulated control is 56%, so the claim is not comparable
- accrual_60_per_year: type I error at HR 1: simulated 0.060 ± 0.008 (expected 0.05, consistent: True)
- accrual_60_per_year: power at design alternative HR 0.591 (15% increase in long-term EFS (56% to 71%, RFR=0.591)): simulated 0.808 ± 0.012 (protocol claims at least 0.8) - consistent: True
- accrual_60_per_year: power at design alternative HR 0.543 (17% increase (56% to 73%, RFR=0.543)): simulated 0.885 ± 0.010 (protocol claims at least 0.9) - consistent: True
- accrual_60_per_year: power at design alternative HR 0.547 (14% increase in long-term EFS (65% to 79%, RFR=0.547)): simulated 0.899 ± 0.010 (protocol claims at least 0.8) - the protocol computed this power for a control long-term EFS of 65%; the simulated control is 56%, so the claim is not comparable
- accrual_60_per_year: power at design alternative HR 0.489 (16% increase (65% to 81%, RFR=0.489)): simulated 0.960 ± 0.006 (protocol claims at least 0.9) - the protocol computed this power for a control long-term EFS of 65%; the simulated control is 56%, so the claim is not comparable

## Stated limitations

- EFS events are observed at their true time: detection at the next scheduled assessment is not applied
- enrollment (= randomization): the protocol does not state the EFS time origin (user decision 2026-09-27)
- Strata are unresolved for enrolled subjects, so the stratified log-rank test runs unstratified.
- Only the randomized arms open in this protocol version are simulated.
- Secondary endpoints are computed from the simulated patients by the endpoint stage.
- Adverse events come from adult class-level evidence and are identical in distribution for both arms.
