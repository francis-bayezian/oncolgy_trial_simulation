# Trial planning report: 1004070 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 77%.
- Screen failure: 23% (eligibility stage (registry recruitment details stating screened and enrolled counts (all oncology; 468 trials, 162721 screened))); patients to screen: 13 for 10.0 enrolled.

## Accrual

- Target: 10 patients (target_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_8.3_per_year (0.7/month, protocol): 10 enrolled over 1.0 years 1.0 (80% 0.6-1.6); P(complete by) 1y: 45%, 2y: 98%, 3y: 100%, 5y: 100%.
- Historical accrual model (mixed_hematologic, PHASE2; matched 'HIV and hematological malignancies'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 1.6 | p30 3.8 | p50 7.2 | p70 14.1 | p90 38.6; enrollment of 10 in years p10 0.2 | p30 0.7 | p50 1.3 | p70 2.6 | p90 6.4; P(complete by) 1y: 41%, 2y: 62%, 3y: 74%, 5y: 86%.

## Sample size

- Maximum N 10; evaluable targets [].
- DR1 Regimen A (High dose consisting of 1320 cGy TBI pl (A total of 10 patients will be enrolled ): max 9, stage 1 8; single stage, no early stop (descriptive estimate)
- DR2 RegimenB (Intermediatedoseconsistingof400cGyTBIplu (A total of 10 patients will be enrolled ): max 9, stage 1 8; single stage, no early stop (descriptive estimate)
- DR3 Regimen A (High dose consisting of 1320 cGy TBI pl (A total of 10 patients will be enrolled ): max 10, stage 1 5; single stage, no early stop (descriptive estimate)
- DR4 RegimenB (Intermediatedoseconsistingof400cGyTBIplu (A total of 10 patients will be enrolled ): max 10, stage 1 5; single stage, no early stop (descriptive estimate)

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 1.3119681304543325, "q10": 0.23410620253715886, "q25": 0.5446080433440783, "q75": 3.113014248157577, "q90": 6.4436236048899875, "percentiles": {"p10": 0.2341
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 1.8119681304543325, "q10": 0.7341062025371589, "q25": 1.0446080433440783, "q75": 3.613014248157577, "q90": 6.9436236048899875}, "accrua
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 6.311968130454332, "q10": 5.234106202537159, "q25": 5.544608043344079, "q75": 8.113014248157576, "q90": 11.443623604889988}, "accrual_h

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.08703911544480288, "source": "registry participant flow (mixed_hematologic): left by subject decision, loss to follow-up or physician decision; 143 trials, 25248 participants"}, "adverse_event": {"value": 0.04312915

## Operational risk

- Trial outcome (historical failure model; OTHER (protocol (quoted): academic, cooperative-group or public sponsor: 'Fred Hutchinson Cancer Center')): P(withdrawn) 20%, P(terminated for poor accrual) 12%, P(terminated, other reason) 14%, P(completed) 54%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.4135, "2y": 0.623875, "3y": 0.739375, "5y": 0.85825}
- enrollment_duration_years (historical model, headline): {"median": 1.31, "q10": 0.23, "q25": 0.54, "q75": 3.11, "q90": 6.44, "percentiles": {"p10": 0.23410620253715886, "p30": 0.6706111989132225, "p50": 1.3119681304543325, "p70": 2.58917327129319, "p90": 6.4436236048899875}}
- p_enrollment_complete_by (accrual_historical_8.3_per_year, conditional on the protocol's assumption): {"1y": 0.4548, "2y": 0.9838, "3y": 1.0, "5y": 1.0}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 8.31978 patients/year | RESOLVED: historical /year: p10 1.6 | p30 3.8 | p50 7.2 | p70 14.1 | p90 38.6 | plausible (protocol/historical median 1.16x) |
