# Trial planning report: NCT01616875 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 77%.
- Screen failure: 23% (eligibility stage (registry recruitment details stating screened and enrolled counts (all oncology; 468 trials, 162721 screened))); patients to screen: 39 for 30.0 enrolled.

## Accrual

- Target: 30 patients (maximum_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_8.4_per_year (0.7/month, protocol): 30 enrolled over 3.4 years 3.4 (80% 2.7-4.3); P(complete by) 1y: 0%, 2y: 0%, 3y: 25%, 5y: 99%.
- Historical accrual model (urothelial, PHASE2; matched 'Transitional Cell Carcinoma of the Urinary Bladder'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 1.7 | p30 4.0 | p50 7.4 | p70 14.2 | p90 38.8; enrollment of 30 in years p10 0.8 | p30 2.0 | p50 4.0 | p70 7.5 | p90 18.3; P(complete by) 1y: 15%, 2y: 29%, 3y: 41%, 5y: 57%.

## Sample size

- Maximum N 30; evaluable targets [26.0].
- DR1 Cabazitaxel 15 mg/m2 day 1 + cisplatin 70mg/ m2 da (26 patients): max 26, stage 1 9; p0 (p=0.35): E[N] 25.6, P(early stop) 2%; p1 (p=0.60): E[N] 26.0, P(early stop) 0%

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 3.9624603373367244, "q10": 0.7523539338219157, "q25": 1.6967075126606714, "q75": 8.862146755068357, "q90": 18.254984101964904, "percentiles": {"p10": 0.75235
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 4.192420915523321, "q10": 0.9823145120085123, "q25": 1.926668090847268, "q75": 9.092107333254955, "q90": 18.4849446801515}, "accrual_hi
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 8.962460337336724, "q10": 5.752353933821916, "q25": 6.696707512660671, "q75": 13.862146755068357, "q90": 23.254984101964904}, "accrual_

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.07780155251715126, "source": "registry participant flow (urothelial): left by subject decision, loss to follow-up or physician decision; 221 trials, 25195 participants"}, "adverse_event": {"value": 0.039835449421509

## Operational risk

- Trial outcome (historical failure model; OTHER (protocol (quoted): academic, cooperative-group or public sponsor: 'University Hospitals Bristol and Weston NHS Foundation Trust')): P(withdrawn) 13%, P(terminated for poor accrual) 20%, P(terminated, other reason) 13%, P(completed) 54%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.146625, "2y": 0.292875, "3y": 0.4075, "5y": 0.571625}
- enrollment_duration_years (historical model, headline): {"median": 3.96, "q10": 0.75, "q25": 1.7, "q75": 8.86, "q90": 18.25, "percentiles": {"p10": 0.7523539338219157, "p30": 2.0474940116612315, "p50": 3.9624603373367244, "p70": 7.4761141964757245, "p90": 18.254984101964904}}
- p_enrollment_complete_by (accrual_historical_8.4_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.004, "3y": 0.2528, "5y": 0.9874}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 8.39549 patients/year | RESOLVED: historical /year: p10 1.7 | p30 4.0 | p50 7.4 | p70 14.2 | p90 38.8 | plausible (protocol/historical median 1.14x) |
