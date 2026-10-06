# Trial outputs: KIROVAX-003 (outputs-1.0.0)

Datasets (one simulated trial, seed 20260927): adsl.csv (17 rows), adae.csv (141 rows), adtte.csv (0 rows).

## Participant flow

- ARM1: 17 enrolled

## Baseline characteristics

| group | n | age mean (sd) | age median (range) | sex % | race % (top 3) | ethnicity % |
| --- | ---: | --- | --- | --- | --- | --- |
| ARM1 | 17 | 61.7 (15.0) | 59.1 (30.5-103.4) | {'male': 58.8, 'female': 41.2} | {'white': 76.5, 'black_or_african_american': 17.6, 'asian': 5.9} | {'not_hispanic_or_latino': 82.4, 'hispanic_or_latino': 11.8, 'unknown_or_not_reported': 5.9} |
| TOTAL | 17 | 61.7 (15.0) | 59.1 (30.5-103.4) | {'male': 58.8, 'female': 41.2} | {'white': 76.5, 'black_or_african_american': 17.6, 'asian': 5.9} | {'not_hispanic_or_latino': 82.4, 'hispanic_or_latino': 11.8, 'unknown_or_not_reported': 5.9} |

## Adverse events (simulated patients)

- ARM1 (n = 17): any serious 29.4%, any other 94.1%; top: alopecia 88.2%; edema 82.4%; anorexia 76.5%; aspartate_aminotransferase_increased 76.5%; decrease_in_appetite 64.7%; headache 52.9%; febrile_neutropenia 41.2%; anemia 35.3%

## Feasibility

- Eligible share of the source population: 77% to 77%; patients to screen for the target: {'at_least': 23, 'at_most': 23}. the upper bound needs every unchecked criterion to be met; the lower bound counts only patients proven eligible. Narrowing them needs the variables the unchecked criteria use.
- Criteria the simulated population cannot check: EL005; EL006; EL007; EL008; EL009; EL010; EL011; EL012; EL013; EL014; EL015; EL016; EL017; EL018; EL019
- Accrual (historical model): patients/year p10 1.7 | p30 4.1 | p50 7.9 | p70 14.4 | p90 39.9; years to target p10 0.4 | p30 1.1 | p50 2.1 | p70 4.1 | p90 10.3.
- Sites needed for an 80% chance of reaching the target of 17: within 2y: 30; within 3y: 15; within 5y: 5 (sites as listed in registry records; the model's site effect is observational (trials that list more sites recruit faster)).
- Trial outcome risk: withdrawn 11%, terminated for poor accrual 6%, terminated otherwise 25%, completed 57%.

## Subgroup estimates (most similar studies)

estimates are the random-effects average of the most similar subgroup of studies; the 95% confidence interval is for that average, the single-trial range for one new trial (held-out studies: median absolute error 0.16 for any serious event).

- ARM1 serious_adverse_event: 42.9% (95% CI 37.6%-48.4%; single trial p10 29% | p30 37% | p50 43% | p70 49% | p90 58%) from 9 studies, subgroup 'whole disease family'. **ATTENTION: the evidence holds too few trials like this protocol: the headline borrows from other subgroups**
    - by age group: adult 43% (9 studies)
    - by phase: PHASE2 42% (6 studies); PHASE1+PHASE2 39% (2 studies); PHASE3 57% (1 studies)
    - by drug classes: not overlapping 43% (9 studies)
- DR1: P(of interest) at p0/p1 {'0.05': 0.03905363467212025, '0.35': 0.9069492500184148}; evidence prior: DESIGN_HYPOTHESIS (the endpoint 'immune response' has no evidence variable: the protocol's design rate is used)
- DR2: P(of interest) at p0/p1 {}; evidence prior: NOT_APPLICABLE (a toxicity rule)
