# Trial outputs: CABOCOL-01 (outputs-1.0.0)

Datasets (one simulated trial, seed 20260927): adsl.csv (57 rows), adae.csv (769 rows), adtte.csv (0 rows).

## Participant flow

- ARM1: 26 enrolled
- ARM2: 31 enrolled

## Baseline characteristics

| group | n | age mean (sd) | age median (range) | sex % | race % (top 3) | ethnicity % |
| --- | ---: | --- | --- | --- | --- | --- |
| ARM1 | 26 | 55.1 (10.4) | 53.1 (36.7-79.3) | {'female': 96.2, 'male': 3.8} | {'white': 73.1, 'black_or_african_american': 19.2, 'unknown_or_not_reported': 3.8} | {'not_hispanic_or_latino': 88.5, 'hispanic_or_latino': 11.5} |
| ARM2 | 31 | 56.5 (11.8) | 54.0 (36.9-91.4) | {'female': 100.0} | {'white': 93.5, 'unknown_or_not_reported': 3.2, 'black_or_african_american': 3.2} | {'not_hispanic_or_latino': 96.8, 'unknown_or_not_reported': 3.2} |
| TOTAL | 57 | 55.9 (11.1) | 53.7 (36.7-91.4) | {'female': 98.2, 'male': 1.8} | {'white': 84.2, 'black_or_african_american': 10.5, 'unknown_or_not_reported': 3.5} | {'not_hispanic_or_latino': 93.0, 'hispanic_or_latino': 5.3, 'unknown_or_not_reported': 1.8} |

## Adverse events (simulated patients)

- ARM2 (n = 31): any serious 16.1%, any other 100.0%; top: pain:_abdominal_pain_nos 93.5%; constipation 64.5%; diarrhea 61.3%; thrombocytopenia 54.8%; sensory_neuropathy 54.8%; anemia 51.6%; pruritus 51.6%; arthralgia 48.4%
- ARM1 (n = 26): any serious 11.5%, any other 100.0%; top: palmar_plantar_erythrodysesthesia_syndrome 100.0%; rash/desquamation 92.3%; acneiform_eruptions 92.3%; thrombocytopenia 88.5%; alanine_aminotransferase_increased 84.6%; dyspnea 80.8%; hypertension_variable 76.9%; asthenia 69.2%

## Feasibility

- Eligible share of the source population: 77% to 77%; patients to screen for the target: {'at_least': 74, 'at_most': 74}. the upper bound needs every unchecked criterion to be met; the lower bound counts only patients proven eligible. Narrowing them needs the variables the unchecked criteria use.
- Criteria the simulated population cannot check: EL001; EL002; EL008; EL009; EL011; EL012; EL013; EL014; EL016; EL018; EL019; EL020; EL021; EL022; EL023
- Accrual (historical model): patients/year p10 1.5 | p30 3.6 | p50 7.0 | p70 13.7 | p90 38.9; years to target p10 1.4 | p30 4.1 | p50 8.1 | p70 15.7 | p90 39.6.
- Sites needed for an 80% chance of reaching the target of 57: within 1.5y: >200 (sites as listed in registry records; the model's site effect is observational (trials that list more sites recruit faster)).
- Trial outcome risk: withdrawn 11%, terminated for poor accrual 5%, terminated otherwise 27%, completed 58%.

## Subgroup estimates (most similar studies)

estimates are the random-effects average of the most similar subgroup of studies; the 95% confidence interval is for that average, the single-trial range for one new trial (held-out studies: median absolute error 0.16 for any serious event).

- ARM1 serious_adverse_event: 14.5% (95% CI 4.7%-36.7%; single trial p10 2% | p30 6% | p50 14% | p70 30% | p90 61%) from 5 studies, subgroup 'mixed trials'. **ATTENTION: the evidence holds too few trials like this protocol: the headline borrows from other subgroups**
    - by age group: adult 30% (32 studies); mixed 14% (5 studies)
    - by phase: PHASE2 24% (29 studies); PHASE1+PHASE2 54% (4 studies); PHASE3 15% (4 studies)
    - by drug classes: not overlapping 28% (37 studies)
- ARM2 serious_adverse_event: 14.5% (95% CI 4.7%-36.7%; single trial p10 2% | p30 6% | p50 14% | p70 30% | p90 61%) from 5 studies, subgroup 'mixed trials'. **ATTENTION: the evidence holds too few trials like this protocol: the headline borrows from other subgroups**
    - by age group: adult 30% (32 studies); mixed 14% (5 studies)
    - by phase: PHASE2 24% (29 studies); PHASE1+PHASE2 54% (4 studies); PHASE3 15% (4 studies)
    - by drug classes: not overlapping 28% (37 studies)
- DR1: P(of interest) at p0/p1 {'0.3': 0.050834477926282824, '0.5': 0.8818267681045971}; evidence prior: CONTEXT_ONLY (only a gynecologic family-level mixture over other regimens (ixabepilone, ixabepilone + bevacizumab, ixabepilone + liposomal doxorubicin, pembrolizumab); no same-regimen or same-class evidence for this arm)
- DR2: P(of interest) at p0/p1 {'0.3': 0.050834477926282824, '0.5': 0.8818267681045971}; evidence prior: DESIGN_HYPOTHESIS (the endpoint 'The main objective will be based on joint primary endpoints of efficacy and safe' has no evidence variable: the protocol's design rate is used)
- DR5: P(of interest) at p0/p1 {'0.2': 0.02327831237681484, '0.5': 0.8203582763671877}; evidence prior: CONTEXT_ONLY (only a gynecologic family-level mixture over other regimens (ixabepilone, ixabepilone + bevacizumab, ixabepilone + liposomal doxorubicin, pembrolizumab); no same-regimen or same-class evidence for this arm)
