# NCT05722015: protocol feasibility (run v1.3.3, feasibility-1.0.0)

Every number below comes from the locked simulation run (screened population, eligibility, enrolled cohort, patient journey, planning report, primary-engine results). How each is derived is stated with it and in section 9.

## 0. Case-study values (canonical: every figure and table uses these)

| Quantity | Value |
| --- | ---: |
| Enrolled | 378 |
| Eligible rate | 71.2% |
| Candidates screened per eligible patient | 1.40 |
| Evaluable: Cycle 1 AUC0-6wks | 366 |
| Evaluable: Steady-state (Cycle 3) Ctrough | 263 |
| P(evaluable Cycle 1 AUC0-6wks meets its requirement) | 100.0% |
| P(evaluable Steady-state (Cycle 3) Ctrough meets its requirement) | 96.6% |
| P(all requirements met) | 96.6% |
| Serious AE, simulated cohort incidence | 39.7% (150 of 378) |
| Withdrawal, simulated cohort | 7.7% |
| Withdrawal, registry burden model prediction | 6.9% |
| Death, simulated cohort | 12.4% |

Historical evidence (not simulated values): serious AE arm-level estimate 39.5%; recruitment median 63/year; PK CV 37% (AUC) and 40% (Ctrough) in comparable trials, 50% and 84% assumed by the protocol.

## 1. What the protocol demands

- Target enrolment 378, allocation 2:1, arms: Subcutaneous Pembrolizumab Coformulated With Hyaluronidase (MK-3475A); Intravenous Pembrolizumab, Administered With Chemotherapy
- Primary endpoints and required evaluable participants: Cycle 1 AUC0-6wks (318); Steady-state (Cycle 3) Ctrough (240)
- 45 executable eligibility criteria; cycle 42.0 days, up to 18 cycles; tumour assessment every 84.0 days; follow-up every 84.0 days

## 2. Screening funnel

| Step | Lost | Remaining | % of candidates | Lost at this step |
| --- | ---: | ---: | ---: | ---: |
| Potential candidates |  | 10,000 | 100.0% |  |
| Disease and stage | 1936 | 8,064 | 80.6% | 19.4% |
| Prior treatment | 177 | 7,887 | 78.9% | 2.2% |
| Performance status | 460 | 7,427 | 74.3% | 5.8% |
| Laboratory and organ function | 50 | 7,377 | 73.8% | 0.7% |
| Reproductive and contraception | 20 | 7,357 | 73.6% | 0.3% |
| Comorbidity and other exclusions | 233 | 7,124 | 71.2% | 3.2% |

Eligibility yield **71.2%**; candidates screened per eligible patient **1.40**; candidates screened to find 378 eligible patients: **531** (eligible patients who decline or are not enrolled are not modelled).

## 3. Criterion bottlenecks

| Criterion | Category | Excluded | Gain if relaxed (points) |
| --- | --- | ---: | ---: |
| EL005 Non small cell lung cancer diagnosis; disease… | Disease and stage | 18.4% | +16.1 |
| EL012 ECOG performance status | Performance status | 5.7% | +4.3 |
| EL020 Systemic anticancer therapy for metastatic nsclc | Prior treatment | 0.4% | +0.3 |
| EL027 Immunologic Deficiency Syndromes; chronic syst… | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL011 Archival tumor tissue sample; new tumor biopsy | Disease and stage | 0.3% | +0.2 |
| EL064 Sperm production capability; local label contr… | Prior treatment | 0.3% | +0.2 |
| EL058 Hearing impairment | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL038 Major surgery; ongoing surgical complications | Prior treatment | 0.3% | +0.2 |
| EL017 Erythropoietin dependency; packed red blood ce… | Laboratory and organ function | 0.3% | +0.2 |
| EL029 Active CNS metastases; Meningeal Carcinomatosis | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL016 Absolute neutrophil count; Blood Platelets | Laboratory and organ function | 0.3% | +0.2 |
| EL014 Adverse events due to previous anticancer ther… | Prior treatment | 0.3% | +0.2 |
| EL035 History of hepatitis B; active hepatitis c vir… | Comorbidity and other exclusions | 0.3% | +0.2 |
| EL024 Radiation therapy to lung; radiation therapy t… | Prior treatment | 0.2% | +0.2 |
| EL031 Active autoimmune disease requiring systemic t… | Comorbidity and other exclusions | 0.2% | +0.2 |

## 4. Subgroups: availability, screening yield, representation, safety

| Subgroup | Candidates | P(eligible) | Eligible share | Enrolled share | Serious AE (95% CI) |
| --- | ---: | ---: | ---: | ---: | --- |
| Age: <65 years | 57% | 72% | 58% | 62% | 42% (36%-48%) |
| Age: 65 years or older | 43% | 70% | 42% | 38% | 36% (29%-45%) |
| Sex: male | 60% | 72% | 60% | 61% | 39% (33%-46%) |
| Sex: female | 40% | 70% | 40% | 39% | 40% (33%-48%) |
| Race: White | 68% | 71% | 67% | 66% | 39% (33%-45%) |
| Race: Asian | 15% | 72% | 15% | 16% | 40% (29%-53%) |
| Race: Black or African American | 9% | 69% | 9% | 8% | 47% (30%-64%) |
| Race: Other or not reported | 8% | 73% | 9% | 9% | 40% (26%-56%) |
| Ethnicity: Not Hispanic or Latino | 91% | 71% | 91% | 91% | 39% (34%-44%) |
| Ethnicity: Hispanic or Latino | 5% | 73% | 5% | 5% | 53% (32%-73%) |
| Ethnicity: Not reported | 3% | 74% | 4% | 4% | 44% (23%-67%) |
| ECOG: ECOG 1 | 61% | 75% | 64% | 60% | 38% (32%-45%) |
| ECOG: ECOG 0 | 33% | 76% | 36% | 40% | 42% (34%-50%) |
| ECOG: ECOG 2 or more | 6% | 0% | 0% | 0% | — |
| Region: North America/Western Europe/Australia/New Zealand | 45% | 72% | 45% | 50% | 44% (37%-51%) |
| Region: Rest of the World | 38% | 71% | 38% | 36% | 32% (25%-40%) |
| Region: East Asia | 17% | 72% | 17% | 15% | 44% (31%-57%) |

## 5. Recruitment demand

- Required rate 454/year (378 in 10 months) = 92nd percentile of comparable trials (historical median 63/year).
- P(all 378 enrolled within the planned window): 8% (planning report: 8%).
- Site count: SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase.

## 6. Endpoint evaluability

- Cycle 1 AUC0-6wks: 366 of 378 evaluable (97%); rule: on study through day 42 (end of cycle 1's dosing interval); required 318
- Steady-state (Cycle 3) Ctrough: 263 of 378 evaluable (70%); rule: on study through day 126 (end of cycle 3's dosing interval); required 240

| Enrolled | P(Cycle 1 AUC0-6wks ≥ 318) | P(Steady-state (Cycle 3) Ctrough ≥ 240) | P(all) |
| ---: | ---: | ---: | ---: |
| 302 | 0% | 0% | 0% |
| 321 | 3% | 7% | 0% |
| 340 | 99% | 41% | 41% |
| 350 | 100% | 63% | 63% |
| 359 | 100% | 81% | 81% |
| 378 | 100% | 97% | 97% |
| 397 | 100% | 100% | 100% |
| 400 | 100% | 100% | 100% |
| 416 | 100% | 100% | 100% |
| 420 | 100% | 100% | 100% |
| 435 | 100% | 100% | 100% |
| 454 | 100% | 100% | 100% |

## 7. Completeness, burden and safety

| Assessment | On study | Alive |
| --- | ---: | ---: |
| Tumour assessment 1 (day 84) | 94% | 97% |
| Tumour assessment 2 (day 168) | 68% | 96% |
| Tumour assessment 3 (day 252) | 47% | 96% |
| Tumour assessment 4 (day 336) | 33% | 94% |
| Tumour assessment 5 (day 420) | 24% | 92% |
| Tumour assessment 6 (day 504) | 17% | 90% |
| Tumour assessment 7 (day 588) | 14% | 89% |
| Tumour assessment 8 (day 672) | 11% | 88% |
| Cycle 1 AUC0-6wks sampling | 97% | 99% |
| Steady-state (Cycle 3) Ctrough sampling | 70% | 97% |

| Burden per patient | Median | IQR |
| --- | ---: | --- |
| Clinic visit days | 23.0 | 18-28 |
| Drug administrations | 71.0 | 39-135 |
| Laboratory draws | 8.0 | 7-9 |
| Tumour scans | 2.0 | 1-4 |
| Follow-up visits | 5.0 | 1-6 |
| Clinic visit days per month on study | 3.54 | |

Withdrawal depends on protocol burden: the registry protocol-burden model predicts 6.9% (95% CI 5.8%-8.3%) for this protocol's participation duration, visit frequency and assessment count (adjusted for phase, disease family, enrolment, start year, sponsor and randomisation); the share is distributed over the visits each patient attends, so longer exposure to scheduled visits carries more risk.

Treatment delivery and exposure (not adherence in the full sense: dose delays and missed doses are not modelled, so delivery is an upper bound): 100.0% of administrations scheduled while on treatment were given; 5.0% of patients had a dose hold; 0.0% a dose reduction.

| Protocol-required visits | Required | Attended | Lost: withdrawal | Lost: death |
| --- | ---: | ---: | ---: | ---: |
| Cycle day-1 clinic visits | 3,113 | 88.7% | 4.8% | 6.6% |
| Drug administration visits | 49,636 | 88.2% | 4.9% | 6.9% |
| Laboratory (safety) assessments | 5,850 | 88.3% | 4.9% | 6.9% |
| Tumour assessments | 1,342 | 86.7% | 5.7% | 7.5% |
| Survival follow-up visits | 1,680 | 87.1% | 6.0% | 6.9% |

Missed visits among participants on study are not modelled (no evidence): losses are from withdrawal and death only.

| Safety | Share (95% CI) | Patients of the target |
| --- | --- | ---: |
| Serious adverse event | 39.7% (34.9%-44.7%) | 150 |
| Treatment interruption (dose hold) | 5.0% (3.2%-7.7%) | 19 |
| Dose reduction | 0.0% (0.0%-1.0%) | 0 |
| Discontinuation for an adverse event | 0.8% (0.3%-2.3%) | 3 |
| Death during follow-up | 12.4% (9.5%-16.1%) | 47 |
| Death before day 126 (last primary sampling) | 3.2% (1.8%-5.5%) | 12 |

## 8. Scenario stress test

| Scenario | Eligible | Screened per eligible | Months to recruit | P(in window) | Women | Age ≥65 | Serious AE patients | Visit days | Evaluable Cycle 1 AUC0-6wks | Evaluable Steady-state (Cycle 3) Ctrough | P(objectives) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original protocol | 71% | 1.40 | 72 | 8% | 40% | 42% | 150 | 23 | 366 | 263 | 97% |
| Relax: ECOG performance status | 76% | 1.32 | 68 | 9% | 40% | 43% | 150 | 23 | 366 | 263 | 97% |
| 20% more sites | 71% | 1.40 | 66 | 9% | 40% | 42% | 150 | 23 | 366 | 263 | 97% |
| Recruitment window +6 months | 71% | 1.40 | 72 | 15% | 40% | 42% | 150 | 23 | 366 | 263 | 97% |
| Regional mix: +20 points East Asia | 71% | 1.40 | 72 | 8% | 40% | 42% | 150 | 23 | 366 | 263 | 97% |
| 50% female target | 71% | 1.76 | 90 | 6% | 50% | 42% | 150 | 23 | 366 | 263 | 97% |
| Enrolment +10% | 71% | 1.40 | 79 | 7% | 40% | 42% | 165 | 23 | 403 | 289 | 100% |
| One fewer follow-up visit | 71% | 1.40 | 72 | 8% | 40% | 42% | 150 | 22 | 366 | 263 | 97% |

How each scenario is derived:

- **Original protocol**: the locked simulation
- **Relax: ECOG performance status**: patients failing only EL012 become eligible; enrolment rate scales with the eligible yield at a fixed screening throughput; their adverse-event and evaluability risk follows their age and sex as in the simulated patients
- **20% more sites**: enrolment rate x 1.2^0.468 (the historical accrual model's site coefficient)
- **Recruitment window +6 months**: the planned window extended by 6 months
- **Regional mix: +20 points East Asia**: eligible candidates re-weighted to 37% from East Asia (from 17%)
- **50% female target**: enrolment held to 50% women; the scarcer sex limits accrual
- **Enrolment +10%**: 416 enrolled
- **One fewer follow-up visit**: the first survival follow-up visit after treatment dropped; withdrawal from the registry burden association for the change in visits per patient-month, distributed over each patient's attended visits; reported as the original protocol's value plus the schedule's expected change

## 9. Derivations

- eligibility: each simulated candidate's eligibility outcome; sequential funnel removes a candidate at the first category it fails
- gain_if_relaxed: candidates who fail only that criterion
- evaluable: treated and on study through the endpoint's sampling day (end of treatment or death ends it); sample collection itself is not simulated
- evaluable_probability: Bayesian bootstrap of the simulated patients (4,000 draws), joint across endpoints
- recruitment: log-normal fitted to the planning report's historical accrual percentiles; duration = enrolment / rate
- objectives: P(every evaluable count meets its requirement) x P(all primary hypotheses succeed at the design ratios)

Figures: `figures/Figure1-9` (PNG, SVG, PDF).
