# NCT05722015: protocol feasibility (run v1.3.2, feasibility-1.0.0)

Every number below comes from the locked simulation run (screened population, eligibility, enrolled cohort, patient journey, planning report, primary-engine results). How each is derived is stated with it and in section 9.

## 1. What the protocol demands

- Target enrolment 378, allocation 2:1, arms: Subcutaneous Pembrolizumab Coformulated With Hyaluronidase (MK-3475A); Intravenous Pembrolizumab, Administered With Chemotherapy
- Primary endpoints and required evaluable participants: Cycle 1 AUC0-6wks (318); Steady-state (Cycle 3) Ctrough (240)
- 45 executable eligibility criteria; cycle 42.0 days, up to 18 cycles; tumour assessment every 84.0 days; follow-up every 84.0 days

## 2. Screening funnel

| Step | Lost | Remaining | % of candidates | Lost at this step |
| --- | ---: | ---: | ---: | ---: |
| Potential candidates |  | 10,000 | 100.0% |  |
| Disease and stage | 1930 | 8,070 | 80.7% | 19.3% |
| Prior treatment | 183 | 7,887 | 78.9% | 2.3% |
| Performance status | 462 | 7,425 | 74.2% | 5.9% |
| Laboratory and organ function | 47 | 7,378 | 73.8% | 0.6% |
| Reproductive and contraception | 20 | 7,358 | 73.6% | 0.3% |
| Comorbidity and other exclusions | 233 | 7,125 | 71.2% | 3.2% |

Eligibility yield **71.2%**; patients screened per enrollee **1.40**; screened to enrol 378: **531**.

## 3. Criterion bottlenecks

| Criterion | Category | Excluded | Gain if relaxed (points) |
| --- | --- | ---: | ---: |
| EL005 Non small cell lung cancer diagnosis; disease… | Disease and stage | 18.4% | +16.1 |
| EL012 ECOG performance status | Performance status | 5.7% | +4.2 |
| EL039 Allogenic tissue or solid organ transplant | Prior treatment | 0.3% | +0.2 |
| EL017 Erythropoietin dependency; packed red blood ce… | Laboratory and organ function | 0.3% | +0.2 |
| EL066 HIV infection history | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL031 Active autoimmune disease requiring systemic t… | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL013 Life Expectancy | Performance status | 0.3% | +0.2 |
| EL036 Potential excluding circumstance; might confou… | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL021 Prior Therapy | Prior treatment | 0.3% | +0.2 |
| EL019 Small cell carcinoma of lung; small cell eleme… | Disease and stage | 0.3% | +0.2 |
| EL037 Psychiatric or substance abuse disorder interf… | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL033 Active infection requiring systemic therapy | Comorbidity and other exclusions | 0.2% | +0.2 |
| EL024 Radiation therapy to lung; radiation therapy t… | Prior treatment | 0.2% | +0.2 |
| EL030 Hypersensitivity grade; hypersensitivity target | Comorbidity and other exclusions | 0.2% | +0.2 |
| EL058 Hearing impairment | Comorbidity and other exclusions | 0.2% | +0.2 |

## 4. Subgroups: availability, screening yield, representation, safety

| Subgroup | Candidates | P(eligible) | Eligible share | Enrolled share | Serious AE (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| Age: <65 years | 65% | 71% | 65% | 66% | 40% (34%-46%) |
| Age: 65 years or older | 35% | 71% | 35% | 34% | 36% (28%-45%) |
| Sex: female | 56% | 71% | 56% | 58% | 38% (31%-44%) |
| Sex: male | 44% | 72% | 44% | 42% | 39% (32%-47%) |
| Race: White | 76% | 72% | 77% | 79% | 37% (32%-42%) |
| Race: Asian | 9% | 72% | 9% | 7% | 50% (33%-67%) |
| Race: Black or African American | 8% | 67% | 7% | 8% | 38% (23%-56%) |
| Race: Other or not reported | 7% | 72% | 7% | 6% | 45% (27%-65%) |
| Ethnicity: Not Hispanic or Latino | 91% | 71% | 91% | 92% | 38% (33%-43%) |
| Ethnicity: Hispanic or Latino | 5% | 72% | 5% | 5% | 53% (32%-73%) |
| Ethnicity: Not reported | 3% | 75% | 3% | 3% | 38% (18%-64%) |
| ECOG: ECOG 1 | 61% | 76% | 65% | 68% | 38% (33%-44%) |
| ECOG: ECOG 0 | 33% | 75% | 35% | 32% | 38% (30%-47%) |
| ECOG: ECOG 2 or more | 6% | 0% | 0% | 0% | — |
| Region: North America/Western Europe/Australia/New Zealand | 45% | 72% | 46% | 45% | 40% (33%-47%) |
| Region: Rest of the World | 38% | 70% | 38% | 40% | 39% (32%-47%) |
| Region: East Asia | 17% | 71% | 17% | 14% | 31% (21%-45%) |

## 5. Recruitment demand

- Required rate 454/year (378 in 10 months) = 92nd percentile of comparable trials (historical median 63/year).
- P(all 378 enrolled within the planned window): 8% (planning report: 8%).
- Site count: SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase.

## 6. Endpoint evaluability

- Cycle 1 AUC0-6wks: 369 of 378 evaluable (98%); rule: on study through day 42 (end of cycle 1's dosing interval); required 318
- Steady-state (Cycle 3) Ctrough: 271 of 378 evaluable (72%); rule: on study through day 126 (end of cycle 3's dosing interval); required 240

| Enrolled | P(Cycle 1 AUC0-6wks ≥ 318) | P(Steady-state (Cycle 3) Ctrough ≥ 240) | P(all) |
| ---: | ---: | ---: | ---: |
| 302 | 0% | 1% | 0% |
| 321 | 12% | 20% | 4% |
| 340 | 100% | 66% | 66% |
| 350 | 100% | 83% | 83% |
| 359 | 100% | 92% | 92% |
| 378 | 100% | 100% | 100% |
| 397 | 100% | 100% | 100% |
| 400 | 100% | 100% | 100% |
| 416 | 100% | 100% | 100% |
| 420 | 100% | 100% | 100% |
| 435 | 100% | 100% | 100% |
| 454 | 100% | 100% | 100% |

## 7. Completeness, burden and safety

| Assessment | On study | Alive |
| --- | ---: | ---: |
| Tumour assessment 1 (day 84) | 96% | 98% |
| Tumour assessment 2 (day 168) | 70% | 97% |
| Tumour assessment 3 (day 252) | 47% | 97% |
| Tumour assessment 4 (day 336) | 31% | 95% |
| Tumour assessment 5 (day 420) | 23% | 94% |
| Tumour assessment 6 (day 504) | 18% | 92% |
| Tumour assessment 7 (day 588) | 15% | 91% |
| Tumour assessment 8 (day 672) | 10% | 91% |
| Cycle 1 AUC0-6wks sampling | 98% | 99% |
| Steady-state (Cycle 3) Ctrough sampling | 72% | 98% |

| Burden per patient | Median | IQR |
| --- | ---: | --- |
| Clinic visit days | 23.0 | 17-28 |
| Drug administrations | 71.0 | 39-135 |
| Laboratory draws | 8.0 | 6-9 |
| Tumour scans | 2.0 | 1-4 |
| Follow-up visits | 5.0 | 1-6 |
| Clinic visit days per month on study | 3.10 | |

Withdrawal rate used by the journey (constant, not burden-dependent): {'ARM1': 0.06926478693405927, 'ARM2': 0.06926478693405927}

| Safety | Share (95% CI) | Patients of the target |
| --- | --- | ---: |
| Serious adverse event | 38.4% (33.6%-43.4%) | 145 |
| Treatment interruption (dose hold) | 4.2% (2.6%-6.8%) | 16 |
| Dose reduction | 0.0% (0.0%-1.0%) | 0 |
| Discontinuation for an adverse event | 0.8% (0.3%-2.3%) | 3 |
| Death during follow-up | 9.3% (6.7%-12.6%) | 35 |
| Death before day 126 (last primary sampling) | 2.4% (1.3%-4.5%) | 9 |

## 8. Scenario stress test

| Scenario | Eligible | Screened/enrollee | Months to recruit | P(in window) | Women | Age ≥65 | Serious AE patients | Visit days | Evaluable Cycle 1 AUC0-6wks | Evaluable Steady-state (Cycle 3) Ctrough | P(objectives) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original protocol | 71% | 1.40 | 72 | 8% | 56% | 35% | 146 | 23 | 370 | 272 | 99% |
| Relax: ECOG performance status | 75% | 1.32 | 68 | 9% | 56% | 36% | 146 | 23 | 370 | 272 | 99% |
| 20% more sites | 71% | 1.40 | 66 | 9% | 56% | 35% | 146 | 23 | 370 | 272 | 99% |
| Recruitment window +6 months | 71% | 1.40 | 72 | 15% | 56% | 35% | 146 | 23 | 370 | 272 | 100% |
| Regional mix: +20 points East Asia | 71% | 1.40 | 72 | 8% | 56% | 35% | 146 | 23 | 370 | 272 | 99% |
| 50% female target | 71% | 1.58 | 81 | 7% | 50% | 35% | 146 | 23 | 370 | 272 | 100% |
| Enrolment +10% | 71% | 1.40 | 79 | 7% | 56% | 35% | 160 | 23 | 407 | 299 | 100% |
| One fewer follow-up visit | 71% | 1.40 | 72 | 8% | 56% | 35% | 146 | 22 | 371 | 274 | 100% |

How each scenario is derived:

- **Original protocol**: the locked simulation
- **Relax: ECOG performance status**: patients failing only EL012 become eligible; enrolment rate scales with the eligible yield at a fixed screening throughput; their adverse-event and evaluability risk follows their age and sex as in the simulated patients
- **20% more sites**: enrolment rate x 1.2^0.468 (the historical accrual model's site coefficient)
- **Recruitment window +6 months**: the planned window extended by 6 months
- **Regional mix: +20 points East Asia**: eligible candidates re-weighted to 37% from East Asia (from 17%)
- **50% female target**: enrolment held to 50% women; the scarcer sex limits accrual
- **Enrolment +10%**: 416 enrolled
- **One fewer follow-up visit**: the first survival follow-up visit after treatment dropped; withdrawal from the registry burden association for the change in visits per patient-month, distributed over each patient's attended visits

## 9. Derivations

- eligibility: each simulated candidate's eligibility outcome; sequential funnel removes a candidate at the first category it fails
- gain_if_relaxed: candidates who fail only that criterion
- evaluable: treated and on study through the endpoint's sampling day (end of treatment or death ends it); sample collection itself is not simulated
- evaluable_probability: Bayesian bootstrap of the simulated patients (4,000 draws), joint across endpoints
- recruitment: log-normal fitted to the planning report's historical accrual percentiles; duration = enrolment / rate
- objectives: P(every evaluable count meets its requirement) x P(all primary hypotheses succeed at the design ratios)

Figures: `figures/Figure1-9` (PNG, SVG, PDF).
