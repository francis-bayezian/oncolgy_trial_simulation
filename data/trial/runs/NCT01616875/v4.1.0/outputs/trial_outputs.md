# Trial outputs: NCT01616875 (outputs-1.0.0)

Datasets (one simulated trial, seed 20260927): adsl.csv (30 rows), adae.csv (381 rows), adtte.csv (0 rows).

## Participant flow

- ARM1: 30 enrolled

## Baseline characteristics

| group | n | age mean (sd) | age median (range) | sex % | race % (top 3) | ethnicity % |
| --- | ---: | --- | --- | --- | --- | --- |
| ARM1 | 30 | 63.2 (9.4) | 63.4 (45.0-81.7) | {'male': 80.0, 'female': 20.0} | {'white': 76.7, 'asian': 16.7, 'black_or_african_american': 3.3} | {'not_hispanic_or_latino': 90.0, 'hispanic_or_latino': 10.0} |
| TOTAL | 30 | 63.2 (9.4) | 63.4 (45.0-81.7) | {'male': 80.0, 'female': 20.0} | {'white': 76.7, 'asian': 16.7, 'black_or_african_american': 3.3} | {'not_hispanic_or_latino': 90.0, 'hispanic_or_latino': 10.0} |

## Adverse events (simulated patients)

- ARM1 (n = 30): any serious 36.7%, any other 100.0%; top: creatinine 96.7%; hyperglycemia 93.3%; myalgia 93.3%; rash_erythematous_macules_or_papules 83.3%; vomiting 80.0%; alanine_aminotransferase_increased 73.3%; rash/desquamation 70.0%; decreased_platelet_count 50.0%

## Feasibility

- Eligible share of the source population: 77% to 77%; patients to screen for the target: {'at_least': 39, 'at_most': 39}. the upper bound needs every unchecked criterion to be met; the lower bound counts only patients proven eligible. Narrowing them needs the variables the unchecked criteria use.
- Criteria the simulated population cannot check: EL002; EL003; EL004; EL005; EL010; EL013; EL015; EL016; EL017; EL018; EL019; EL020; EL021; EL022; EL023
- Accrual (historical model): patients/year p10 1.7 | p30 4.0 | p50 7.4 | p70 14.2 | p90 38.8; years to target p10 0.8 | p30 2.0 | p50 4.0 | p70 7.5 | p90 18.3.
- Sites needed for an 80% chance of reaching the target of 30: within 2y: 100; within 3y: 60; within 5y: 15 (sites as listed in registry records; the model's site effect is observational (trials that list more sites recruit faster)).
- Trial outcome risk: withdrawn 13%, terminated for poor accrual 20%, terminated otherwise 13%, completed 54%.

## Subgroup estimates (most similar studies)

estimates are the random-effects average of the most similar subgroup of studies; the 95% confidence interval is for that average, the single-trial range for one new trial (held-out studies: median absolute error 0.16 for any serious event).

- ARM1 serious_adverse_event: 35.5% (95% CI 20.8%-53.6%; single trial p10 11% | p30 23% | p50 35% | p70 50% | p90 71%) from 8 studies, subgroup 'adult trials with overlapping drug classes'.
    - by age group: adult 38% (16 studies); mixed 12% (2 studies)
    - by phase: PHASE2 40% (16 studies); PHASE3 24% (2 studies)
    - by drug classes: not overlapping 38% (10 studies); overlapping 33% (9 studies)
- ARM1 objective_response_rate: 28.4% (95% CI 22.1%-35.8%; single trial p10 22% | p30 25% | p50 28% | p70 32% | p90 36%) from 3 studies, subgroup 'adult trials'. **ATTENTION: the evidence holds too few trials like this protocol: the headline borrows from other subgroups**
    - by age group: adult 28% (3 studies)
    - by phase: PHASE2 14% (2 studies); PHASE3 31% (1 studies)
    - by drug classes: not overlapping 28% (3 studies)
- DR1: P(of interest) at p0/p1 {'0.35': 0.037703329593720705, '0.6': 0.8006400384662486}; evidence prior: CONTEXT_ONLY (only a urothelial family-level mixture over other regimens (cabozantinib, carotuximab, pembrolizumab + lenvatinib, pembrolizumab + placebo for lenvatinib); no same-regimen or same-class evidence for this arm)
