# Trial planning report: NCT01391962 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 86%.
- Screen failure: 14% (eligibility stage (registry recruitment details stating screened and enrolled counts (sarcoma; 6 trials, 548 screened))); patients to screen: 82 for 70.0 enrolled.

## Accrual

- Target: 70 patients (maximum_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_11.8_per_year (1.0/month, protocol): 70 enrolled over 5.8 years 5.8 (80% 5.0-6.7); P(complete by) 1y: 0%, 2y: 0%, 3y: 0%, 5y: 11%.
- accrual_14_per_year (1.2/month, protocol): 70 enrolled over 4.9 years 4.9 (80% 4.2-5.7); P(complete by) 1y: 0%, 2y: 0%, 3y: 0%, 5y: 57%.
- Historical accrual model (sarcoma, PHASE2; matched 'Alveolar soft part sarcoma (ASPS)'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 2.2 | p30 5.5 | p50 10.7 | p70 20.9 | p90 59.3; enrollment of 70 in years p10 1.2 | p30 3.3 | p50 6.5 | p70 12.7 | p90 31.6; P(complete by) 1y: 8%, 2y: 18%, 3y: 27%, 5y: 42%.

## Sample size

- Maximum N 70; evaluable targets [10.0, 22.0, 22.0, 8.0, 11.0].
- DR1 cediranib (30 mg) (cediranib (30 mg)) (For patients who are not newly diagnosed): max 22, stage 1 10; p0 (p=0.15): E[N] 15.5, P(early stop) 54%; p1 (p=0.40): E[N] 21.4, P(early stop) 5%
- DR2 sunitinib malate (37.5 mg) (sunitinib malate (37.5 (For patients who are not newly diagnosed): max 22, stage 1 10; p0 (p=0.15): E[N] 15.5, P(early stop) 54%; p1 (p=0.40): E[N] 21.4, P(early stop) 5%
- DR3 cediranib (30 mg) (cediranib (30 mg)) (newly diagnosed ASPS cohort): max 11, stage 1 8; p0 (p=0.15): E[N] 9.0, P(early stop) 66%; p1 (p=0.45): E[N] 10.8, P(early stop) 6%; cited F079 (p=0.57): E[N] 11.0, P(early stop) 1%
- DR4 sunitinib malate (37.5 mg) (sunitinib malate (37.5 (newly diagnosed ASPS cohort): max 11, stage 1 8; p0 (p=0.15): E[N] 9.0, P(early stop) 66%; p1 (p=0.45): E[N] 10.8, P(early stop) 6%

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 6.544395951651493, "q10": 1.1913279390386584, "q25": 2.735328316904138, "q75": 15.073334129233254, "q90": 31.620271902283925, "percentiles": {"p10": 1.191327
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 7.044395951651493, "q10": 1.6913279390386584, "q25": 3.235328316904138, "q75": 15.573334129233254, "q90": 32.120271902283925}, "accrual
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 11.544395951651493, "q10": 6.191327939038659, "q25": 7.735328316904138, "q75": 20.073334129233253, "q90": 36.620271902283925}, "accrual

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.08729603612247909, "source": "registry participant flow (sarcoma): left by subject decision, loss to follow-up or physician decision; 403 trials, 28713 participants"}, "adverse_event": {"value": 0.07135913240864586,

## Operational risk

- Trial outcome (historical failure model; OTHER (protocol (quoted): academic, cooperative-group or public sponsor: 'National Cancer Institute')): P(withdrawn) 15%, P(terminated for poor accrual) 12%, P(terminated, other reason) 12%, P(completed) 61%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.08225, "2y": 0.18125, "3y": 0.274375, "5y": 0.41825}
- enrollment_duration_years (historical model, headline): {"median": 6.54, "q10": 1.19, "q25": 2.74, "q75": 15.07, "q90": 31.62, "percentiles": {"p10": 1.1913279390386584, "p30": 3.2976961781789695, "p50": 6.544395951651493, "p70": 12.666631792916295, "p90": 31.620271902283925}}
- p_enrollment_complete_by (accrual_historical_11.8_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.1136}
- p_enrollment_complete_by (accrual_14_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.5662}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 11.8267 patients/year | RESOLVED: historical /year: p10 2.2 | p30 5.5 | p50 10.7 | p70 20.9 | p90 59.3 | plausible (protocol/historical median 1.10x) |
| accrual 14 patients/year | RESOLVED: historical /year: p10 2.2 | p30 5.5 | p50 10.7 | p70 20.9 | p90 59.3 | plausible (protocol/historical median 1.30x) |
| response rate 57% cited for cediranib (30 mg) (cediranib (30 mg)) | CITED_COUNT: 4/7: true rate 90% 28%-83% | small sample: a conditional scenario, not a prediction |
