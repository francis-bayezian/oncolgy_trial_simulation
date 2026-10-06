# Trial planning report: KIROVAX-003 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 77%.
- Screen failure: 23% (eligibility stage (registry recruitment details stating screened and enrolled counts (all oncology; 468 trials, 162721 screened))); patients to screen: 23 for 17.0 enrolled.

## Accrual

- Target: 17 patients (target_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_7.8_per_year (0.6/month, protocol): 17 enrolled over 2.0 years 2.0 (80% 1.4-2.7); P(complete by) 1y: 1%, 2y: 49%, 3y: 95%, 5y: 100%.
- Historical accrual model (mixed_solid_tumors, PHASE1+PHASE2; matched 'Progressive and/or Refractory Solid Malignancies'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 1.7 | p30 4.1 | p50 7.9 | p70 14.4 | p90 39.9; enrollment of 17 in years p10 0.4 | p30 1.1 | p50 2.1 | p70 4.1 | p90 10.3; P(complete by) 1y: 27%, 2y: 48%, 3y: 61%, 5y: 75%.

## Sample size

- Maximum N 17; evaluable targets [].
- DR1 Phase I/II Study of Low Dose Cyclophosphamide, Tum (total of 17 patients): max 17, stage 1 6; p0 (p=0.05): E[N] 8.9, P(early stop) 74%; p1 (p=0.35): E[N] 16.2, P(early stop) 8%
- DR2 Phase I/II Study of Low Dose Cyclophosphamide, Tum (up to six (6) consecutive subjects): max 6; single stage, no early stop (descriptive estimate)

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 2.1192228863434304, "q10": 0.40156349442503364, "q25": 0.9121064129765312, "q75": 4.962742202398307, "q90": 10.272668527184965, "percentiles": {"p10": 0.4015
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 2.1767130308900797, "q10": 0.4590536389716828, "q25": 0.9695965575231803, "q75": 5.020232346944956, "q90": 10.330158671731615}, "accrua
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 7.11922288634343, "q10": 5.401563494425034, "q25": 5.912106412976531, "q75": 9.962742202398307, "q90": 15.272668527184965}, "accrual_hi

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.05415558869336486, "source": "registry participant flow (mixed_solid_tumors): left by subject decision, loss to follow-up or physician decision; 27 trials, 3813 participants"}, "adverse_event": {"value": 0.118690028

## Operational risk

- Trial outcome (historical failure model; INDUSTRY (protocol (quoted): company legal form: 'Kiromic, Inc')): P(withdrawn) 11%, P(terminated for poor accrual) 6%, P(terminated, other reason) 25%, P(completed) 57%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.2715, "2y": 0.481125, "3y": 0.608625, "5y": 0.752625}
- enrollment_duration_years (historical model, headline): {"median": 2.12, "q10": 0.4, "q25": 0.91, "q75": 4.96, "q90": 10.27, "percentiles": {"p10": 0.40156349442503364, "p30": 1.1162875259137095, "p50": 2.1192228863434304, "p70": 4.055560798660697, "p90": 10.272668527184965}}
- p_enrollment_complete_by (accrual_historical_7.8_per_year, conditional on the protocol's assumption): {"1y": 0.008, "2y": 0.4922, "3y": 0.952, "5y": 1.0}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 7.77736 patients/year | RESOLVED: historical /year: p10 1.7 | p30 4.1 | p50 7.9 | p70 14.4 | p90 39.9 | plausible (protocol/historical median 0.99x) |
