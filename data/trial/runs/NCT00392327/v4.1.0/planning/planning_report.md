# Trial planning report: ACNS0332 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 87%.
- Screen failure: 13% (eligibility stage (registry recruitment details stating screened and enrolled counts (central_nervous_system; 14 trials, 5511 screened))); patients to screen: 458 for 400.0 enrolled.

## Accrual

- Target: 400 patients (maximum_accrual). Accrual durations in the protocol: [5.0, 8.0] years.
- accrual_historical_92.2_per_year (7.7/month, protocol): 311 enrolled over 3.4 years 3.4 (80% 3.1-3.6); P(complete by) 5y: 100%, 8y: 100%.
- accrual_35_per_year (2.9/month, protocol): 311 enrolled over 8.9 years 8.9 (80% 8.2-9.6); P(complete by) 5y: 0%, 8y: 5%.
- accrual_60_per_year (5.0/month, protocol): 311 enrolled over 5.2 years 5.2 (80% 4.8-5.6); P(complete by) 5y: 30%, 8y: 100%.
- Historical accrual model (central_nervous_system, PHASE3; matched 'Other Than Average Risk Medulloblastoma/PNET'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 16.1 | p30 50.1 | p50 103.0 | p70 207.2 | p90 544.1; enrollment of 400 in years p10 0.7 | p30 1.9 | p50 3.9 | p70 8.0 | p90 24.9; P(complete by) 5y: 58%, 8y: 70%.

## Sample size

- Maximum N 400; evaluable targets [280.0, 100.0, 50.0, 73.0].

## Timelines (years from first patient in)

- Event targets (protocol): [110]. event timing depends on the unknown true effect: shown under no effect and under the protocol's design alternative; all times are years from first patient in.
- accrual_historical_92.2_per_year, no effect (HR 1): last patient in 3.4; primary analysis 4.4 4.4 (80% 4.1-4.6); 110 events 3.7 3.7 (80% 3.3-4.2), ever reached 100%; study completion (off-study limit) 13.4.
- accrual_historical_92.2_per_year, design alternative HR 0.591: last patient in 3.4; primary analysis 4.4 4.4 (80% 4.1-4.6); 110 events 6.9 6.9 (80% 5.9-8.8), ever reached 1%; study completion (off-study limit) 13.4.
- accrual_35_per_year, no effect (HR 1): last patient in 8.9; primary analysis 9.9 9.9 (80% 9.2-10.6); 110 events 8.1 8.1 (80% 7.2-9.1), ever reached 100%; study completion (off-study limit) 18.9.
- accrual_35_per_year, design alternative HR 0.591: last patient in 8.9; primary analysis 9.9 9.9 (80% 9.1-10.5); 110 events 11.0 11.0 (80% 9.8-12.7), ever reached 1%; study completion (off-study limit) 18.9.
- accrual_60_per_year, no effect (HR 1): last patient in 5.2; primary analysis 6.2 6.2 (80% 5.8-6.6); 110 events 5.1 5.1 (80% 4.6-5.7), ever reached 100%; study completion (off-study limit) 15.2.
- accrual_60_per_year, design alternative HR 0.591: last patient in 5.2; primary analysis 6.2 6.2 (80% 5.8-6.6); 110 events 6.8 6.8 (80% 6.0-8.7), ever reached 0%; study completion (off-study limit) 15.2.

## Retention

- {"loss_to_follow_up_per_year": 0.01, "source": "protocol (quoted)", "wording": "with an annual 1% censoring rate.", "discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.0825282599314728, "source": "registry participant flow (central_nervous_system): left by subject dec

## Operational risk

- Trial outcome (historical failure model; OTHER (protocol (quoted): academic, cooperative-group or public sponsor: 'CHILDREN’S ONCOLOGY GROUP')): P(withdrawn) 2%, P(terminated for poor accrual) 8%, P(terminated, other reason) 7%, P(completed) 84%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"5y": 0.575875, "8y": 0.70075}
- enrollment_duration_years (historical model, headline): {"median": 3.87, "q10": 0.73, "q25": 1.58, "q75": 10.07, "q90": 24.92, "percentiles": {"p10": 0.732733401642261, "p30": 1.918320247364891, "p50": 3.866601861131609, "p70": 7.965467113322052, "p90": 24.92328775718279}}
- p_enrollment_complete_by (accrual_historical_92.2_per_year, conditional on the protocol's assumption): {"5y": 1.0, "8y": 1.0}
- p_enrollment_complete_by (accrual_35_per_year, conditional on the protocol's assumption): {"5y": 0.0, "8y": 0.052}
- p_enrollment_complete_by (accrual_60_per_year, conditional on the protocol's assumption): {"5y": 0.3026, "8y": 1.0}
- p_primary_analysis_by (accrual_historical_92.2_per_year, no effect (HR 1)): {"5y": 0.999, "8y": 1.0, "10y": 1.0}
- p_110_events_by (accrual_historical_92.2_per_year, no effect (HR 1)): {"5y": 0.986, "8y": 1.0, "10y": 1.0}
- p_primary_analysis_by (accrual_historical_92.2_per_year, design alternative HR 0.591): {"5y": 0.999, "8y": 1.0, "10y": 1.0}
- p_110_events_by (accrual_historical_92.2_per_year, design alternative HR 0.591): {"5y": 0.0, "8y": 0.005, "10y": 0.006}
- p_primary_analysis_by (accrual_35_per_year, no effect (HR 1)): {"5y": 0.0, "8y": 0.0, "10y": 0.591}
- p_110_events_by (accrual_35_per_year, no effect (HR 1)): {"5y": 0.0, "8y": 0.461, "10y": 0.993}
- p_primary_analysis_by (accrual_35_per_year, design alternative HR 0.591): {"5y": 0.0, "8y": 0.0, "10y": 0.607}
- p_110_events_by (accrual_35_per_year, design alternative HR 0.591): {"5y": 0.0, "8y": 0.0, "10y": 0.002}
- p_primary_analysis_by (accrual_60_per_year, no effect (HR 1)): {"5y": 0.0, "8y": 1.0, "10y": 1.0}
- p_110_events_by (accrual_60_per_year, no effect (HR 1)): {"5y": 0.378, "8y": 0.997, "10y": 0.997}
- p_primary_analysis_by (accrual_60_per_year, design alternative HR 0.591): {"5y": 0.0, "8y": 1.0, "10y": 1.0}
- p_110_events_by (accrual_60_per_year, design alternative HR 0.591): {"5y": 0.0, "8y": 0.004, "10y": 0.005}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 92.1897 patients/year | RESOLVED: historical /year: p10 16.1 | p30 50.1 | p50 103.0 | p70 207.2 | p90 544.1 | plausible (protocol/historical median 0.90x) |
| accrual 35 patients/year | RESOLVED: historical /year: p10 16.1 | p30 50.1 | p50 103.0 | p70 207.2 | p90 544.1 | plausible (protocol/historical median 0.34x) |
| accrual 60 patients/year | RESOLVED: historical /year: p10 16.1 | p30 50.1 | p50 103.0 | p70 207.2 | p90 544.1 | plausible (protocol/historical median 0.58x) |
