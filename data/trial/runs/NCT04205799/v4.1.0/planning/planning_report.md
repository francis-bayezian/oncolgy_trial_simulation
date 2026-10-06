# Trial planning report: CABOCOL-01 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 77%.
- Screen failure: 23% (eligibility stage (registry recruitment details stating screened and enrolled counts (gynecologic; 32 trials, 10296 screened))); patients to screen: 74 for 57.0 enrolled.

## Accrual

- Target: 57 patients (target_accrual). Accrual durations in the protocol: [1.5] years.
- accrual_historical_7.9_per_year (0.7/month, protocol): 57 enrolled over 7.1 years 7.1 (80% 5.9-8.3); P(complete by) 1.5y: 0%.
- accrual_3_per_year (0.2/month, protocol): 57 enrolled over 18.6 years 18.6 (80% 15.5-22.0); P(complete by) 1.5y: 0%.
- Historical accrual model (gynecologic, PHASE2; matched 'advanced or metastatic cervical carcinoma'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 1.5 | p30 3.6 | p50 7.0 | p70 13.7 | p90 38.9; enrollment of 57 in years p10 1.4 | p30 4.1 | p50 8.1 | p70 15.7 | p90 39.6; P(complete by) 1.5y: 11%.

## Sample size

- Maximum N 57; evaluable targets [22.0, 29.0, 51.0, 19.0].
- DR1 Cabozantinib (Cabozantinib) (A phase II single-arm two-stage multicen): max 51, stage 1 22; p0 (p=0.30): E[N] 31.5, P(early stop) 67%; p1 (p=0.50): E[N] 49.1, P(early stop) 7%
- DR2 Cabozantinib (Cabozantinib) (The total sample size to be enrolled is ): max 51, stage 1 22; p0 (p=0.30): E[N] 31.5, P(early stop) 67%; p1 (p=0.50): E[N] 49.1, P(early stop) 7%
- DR5 BEVACIZUMAB (PATIENTS UNDER BEVACIZUMAB) (19 evaluable bevacizumab pre-treated pat): max 19; p0 (p=0.20): E[N] 19.0, P(early stop) 0%; p1 (p=0.50): E[N] 19.0, P(early stop) 0%

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 8.08104286658447, "q10": 1.4218003668047408, "q25": 3.331933251827011, "q75": 18.81263107498753, "q90": 39.562929099613534, "percentiles": {"p10": 1.42180036
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 8.33104286658447, "q10": 1.6718003668047408, "q25": 3.581933251827011, "q75": 19.06263107498753, "q90": 39.812929099613534}, "accrual_h
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 8.33104286658447, "q10": 1.6718003668047408, "q25": 3.581933251827011, "q75": 19.06263107498753, "q90": 39.812929099613534}, "accrual_h

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.07271292526603469, "source": "registry participant flow (gynecologic): left by subject decision, loss to follow-up or physician decision; 630 trials, 85355 participants"}, "adverse_event": {"value": 0.04272168521985

## Operational risk

- Trial outcome (historical failure model; INDUSTRY (protocol (quoted): company legal form: 'IPSEN Pharma SAS Laboratory')): P(withdrawn) 11%, P(terminated for poor accrual) 5%, P(terminated, other reason) 27%, P(completed) 58%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1.5y": 0.107125}
- enrollment_duration_years (historical model, headline): {"median": 8.08, "q10": 1.42, "q25": 3.33, "q75": 18.81, "q90": 39.56, "percentiles": {"p10": 1.4218003668047408, "p30": 4.083598648312607, "p50": 8.08104286658447, "p70": 15.665406648671874, "p90": 39.562929099613534}}
- p_enrollment_complete_by (accrual_historical_7.9_per_year, conditional on the protocol's assumption): {"1.5y": 0.0}
- p_enrollment_complete_by (accrual_3_per_year, conditional on the protocol's assumption): {"1.5y": 0.0}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 7.85934 patients/year | RESOLVED: historical /year: p10 1.5 | p30 3.6 | p50 7.0 | p70 13.7 | p90 38.9 | plausible (protocol/historical median 1.12x) |
| accrual 3 patients/year | RESOLVED: historical /year: p10 1.5 | p30 3.6 | p50 7.0 | p70 13.7 | p90 38.9 | plausible (protocol/historical median 0.43x) |
