# NCT05722015: protocol feasibility (run v1.2.0, feasibility-1.0.0)

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
| Age: <65 years | 65% | 71% | 65% | 66% | 52% (46%-59%) |
| Age: 65 years or older | 35% | 71% | 35% | 34% | 51% (42%-59%) |
| Sex: female | 56% | 71% | 56% | 58% | 52% (45%-58%) |
| Sex: male | 44% | 72% | 44% | 42% | 52% (44%-59%) |
| Race: White | 76% | 72% | 77% | 79% | 49% (44%-55%) |
| Race: Asian | 9% | 72% | 9% | 7% | 61% (42%-76%) |
| Race: Black or African American | 8% | 67% | 7% | 8% | 62% (44%-77%) |
| Race: Other or not reported | 7% | 72% | 7% | 6% | 64% (43%-80%) |
| Ethnicity: Not Hispanic or Latino | 91% | 71% | 91% | 92% | 51% (46%-57%) |
| Ethnicity: Hispanic or Latino | 5% | 72% | 5% | 5% | 58% (36%-77%) |
| Ethnicity: Not reported | 3% | 75% | 3% | 3% | 54% (29%-77%) |
| ECOG: ECOG 1 | 61% | 76% | 65% | 68% | 51% (45%-57%) |
| ECOG: ECOG 0 | 33% | 75% | 35% | 32% | 54% (45%-63%) |
| ECOG: ECOG 2 or more | 6% | 0% | 0% | 0% | — |
| Region: North America/Western Europe/Australia/New Zealand | 45% | 72% | 46% | 45% | 53% (46%-61%) |
| Region: Rest of the World | 38% | 70% | 38% | 40% | 54% (46%-62%) |
| Region: East Asia | 17% | 71% | 17% | 14% | 41% (29%-54%) |

## 5. Recruitment demand

- Required rate 454/year (378 in 10 months) = 92nd percentile of comparable trials (historical median 63/year).
- P(all 378 enrolled within the planned window): 8% (planning report: 8%).
- Site count: SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase.

## 6. Endpoint evaluability

- Cycle 1 AUC0-6wks: 376 of 378 evaluable (99%); rule: on study through day 42 (end of cycle 1's dosing interval); required 318
- Steady-state (Cycle 3) Ctrough: 243 of 378 evaluable (64%); rule: on study through day 126 (end of cycle 3's dosing interval); required 240

| Enrolled | P(Cycle 1 AUC0-6wks ≥ 318) | P(Steady-state (Cycle 3) Ctrough ≥ 240) | P(all) |
| ---: | ---: | ---: | ---: |
| 302 | 0% | 0% | 0% |
| 321 | 86% | 0% | 0% |
| 340 | 100% | 4% | 4% |
| 350 | 100% | 12% | 12% |
| 359 | 100% | 25% | 25% |
| 378 | 100% | 61% | 61% |
| 397 | 100% | 88% | 88% |
| 400 | 100% | 90% | 90% |
| 416 | 100% | 97% | 97% |
| 420 | 100% | 98% | 98% |
| 435 | 100% | 100% | 100% |
| 454 | 100% | 100% | 100% |

## 7. Completeness, burden and safety

| Assessment | On study | Alive |
| --- | ---: | ---: |
| Tumour assessment 1 (day 84) | 98% | 99% |
| Tumour assessment 2 (day 168) | 63% | 97% |
| Tumour assessment 3 (day 252) | 40% | 94% |
| Tumour assessment 4 (day 336) | 24% | 93% |
| Tumour assessment 5 (day 420) | 17% | 90% |
| Tumour assessment 6 (day 504) | 11% | 90% |
| Tumour assessment 7 (day 588) | 7% | 88% |
| Tumour assessment 8 (day 672) | 5% | 87% |
| Cycle 1 AUC0-6wks sampling | 99% | 100% |
| Steady-state (Cycle 3) Ctrough sampling | 64% | 99% |

| Burden per patient | Median | IQR |
| --- | ---: | --- |
| Clinic visit days | 19.0 | 14-24 |
| Drug administrations | 71.0 | 39-104 |
| Laboratory draws | 8.0 | 6-9 |
| Tumour scans | 2.0 | 1-3 |
| Follow-up visits | 1.0 | 1-1 |
| Clinic visit days per month on study | 3.06 | |

Withdrawal rate used by the journey (constant, not burden-dependent): {'ARM1': 0.050964163458226366, 'ARM2': 0.050964163458226366}

| Safety | Share (95% CI) | Patients of the target |
| --- | --- | ---: |
| Serious adverse event | 51.9% (46.8%-56.8%) | 196 |
| Treatment interruption (dose hold) | 5.0% (3.2%-7.7%) | 19 |
| Dose reduction | 0.0% (0.0%-1.0%) | 0 |
| Discontinuation for an adverse event | 1.6% (0.7%-3.4%) | 6 |
| Death during follow-up | 14.0% (10.9%-17.9%) | 53 |
| Death before day 126 (last primary sampling) | 1.3% (0.6%-3.1%) | 5 |

## 8. Scenario stress test

| Scenario | Eligible | Screened/enrollee | Months to recruit | P(in window) | Women | Age ≥65 | Serious AE patients | Visit days | Evaluable Cycle 1 AUC0-6wks | Evaluable Steady-state (Cycle 3) Ctrough | P(objectives) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original protocol | 71% | 1.40 | 72 | 8% | 56% | 35% | 196 | 19 | 377 | 242 | 58% |
| Relax: ECOG performance status | 75% | 1.32 | 68 | 9% | 56% | 36% | 196 | 19 | 377 | 243 | 59% |
| 20% more sites | 71% | 1.40 | 66 | 9% | 56% | 35% | 196 | 19 | 377 | 243 | 58% |
| Recruitment window +6 months | 71% | 1.40 | 72 | 15% | 56% | 35% | 196 | 19 | 377 | 243 | 58% |
| Regional mix: +20 points East Asia | 71% | 1.40 | 72 | 8% | 56% | 35% | 196 | 19 | 376 | 242 | 58% |
| 50% female target | 71% | 1.58 | 81 | 7% | 50% | 35% | 196 | 19 | 377 | 243 | 59% |
| Enrolment +10% | 71% | 1.40 | 79 | 7% | 56% | 35% | 216 | 19 | 414 | 267 | 97% |
| One fewer follow-up visit | 71% | 1.40 | 72 | 8% | 56% | 35% | 196 | 18 | 377 | 242 | 59% |

How each scenario is derived:

- **Original protocol**: the locked simulation
- **Relax: ECOG performance status**: patients failing only EL012 become eligible; enrolment rate scales with the eligible yield at a fixed screening throughput; their adverse-event and evaluability risk follows their age and sex as in the simulated patients
- **20% more sites**: enrolment rate x 1.2^0.468 (the historical accrual model's site coefficient)
- **Recruitment window +6 months**: the planned window extended by 6 months
- **Regional mix: +20 points East Asia**: eligible candidates re-weighted to 37% from East Asia (from 17%)
- **50% female target**: enrolment held to 50% women; the scarcer sex limits accrual
- **Enrolment +10%**: 416 enrolled
- **One fewer follow-up visit**: one follow-up visit removed per patient; the simulated withdrawal rate does not depend on visit burden, so retention is unchanged

## 9. Derivations

- eligibility: each simulated candidate's eligibility outcome; sequential funnel removes a candidate at the first category it fails
- gain_if_relaxed: candidates who fail only that criterion
- evaluable: treated and on study through the endpoint's sampling day (end of treatment or death ends it); sample collection itself is not simulated
- evaluable_probability: Bayesian bootstrap of the simulated patients (4,000 draws), joint across endpoints
- recruitment: log-normal fitted to the planning report's historical accrual percentiles; duration = enrolment / rate
- objectives: P(every evaluable count meets its requirement) x P(all primary hypotheses succeed at the design ratios)

Figures: `figures/Figure1-9` (PNG, SVG, PDF).
