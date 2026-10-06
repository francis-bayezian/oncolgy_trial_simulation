# Trial planning report: INCB 54828-205 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 78%.
- Screen failure: 22% (eligibility stage (registry recruitment details stating screened and enrolled counts (all oncology, PHASE2; 185 trials, 26902 screened))); patients to screen: 478 for 372.0 enrolled.

## Accrual

- Target: 372 patients (target_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_11.4_per_year (0.9/month, protocol): 372 enrolled over 32.7 years 32.7 (80% 30.5-34.9); P(complete by) 1y: 0%, 2y: 0%, 3y: 0%, 5y: 0%.
- accrual_124_per_year_derived (10.3/month, protocol): 372 enrolled over 3.0 years 3.0 (80% 2.8-3.2); P(complete by) 1y: 0%, 2y: 0%, 3y: 52%, 5y: 100%.
- Historical accrual model (urothelial, PHASE2; matched 'Urothelial Carcinoma'; SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase): patients/year p10 2.1 | p30 5.2 | p50 9.9 | p70 19.5 | p90 54.1; enrollment of 372 in years p10 6.9 | p30 19.2 | p50 37.4 | p70 72.2 | p90 175.6; P(complete by) 1y: 0%, 2y: 1%, 3y: 3%, 5y: 7%.

## Sample size

- Maximum N 372; evaluable targets [].

## Timelines (years from first patient in)

- Event targets (protocol): [210, 210, 194, 169]. event timing depends on the unknown true effect: shown under no effect and under the protocol's design alternative; all times are years from first patient in.
- accrual_historical_11.4_per_year, no effect (HR 1): last patient in 32.7; primary analysis 32.7 32.7 (80% 30.4-34.9); 210 events 19.1 19.1 (80% 17.4-20.7), ever reached 100%; 194 events 17.7 17.7 (80% 16.0-19.2), ever reached 100%; 169 events 15.4 15.4 (80% 13.9-16.9), ever reached 100%.
- accrual_124_per_year_derived, no effect (HR 1): last patient in 3.0; primary analysis 3.0 3.0 (80% 2.8-3.2); 210 events 2.1 2.1 (80% 2.0-2.3), ever reached 100%; 194 events 2.0 2.0 (80% 1.8-2.1), ever reached 100%; 169 events 1.8 1.8 (80% 1.6-1.9), ever reached 100%.

## Retention

- {"loss_to_follow_up_per_year": 0.03661909069721547, "source": "protocol (quoted)", "wording": "registry participant flow (urothelial, PHASE2): left by subject decision, loss to follow-up or physician decision; 132 trials, 7508 participants: 7.2% over the study, spread over 2 years (assumption A18)",

## Operational risk

- Trial outcome (historical failure model; INDUSTRY (protocol (quoted): company legal form: 'Incyte Corporation')): P(withdrawn) 10%, P(terminated for poor accrual) 9%, P(terminated, other reason) 24%, P(completed) 58%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.00325, "2y": 0.014375, "3y": 0.02975, "5y": 0.0665}
- enrollment_duration_years (historical model, headline): {"median": 37.43, "q10": 6.9, "q25": 15.7, "q75": 87.19, "q90": 175.57, "percentiles": {"p10": 6.9041669967121715, "p30": 19.1794327975807, "p50": 37.426198628125626, "p70": 72.24750755716592, "p90": 175.565790742168}}
- protocol_accrual_assumption_outside_history: [{"scenario": "accrual_124_per_year_derived", "patients_per_year": 124.0, "vs_historical_median": 12.56, "direction": "optimistic"}]
- p_enrollment_complete_by (accrual_historical_11.4_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0}
- p_enrollment_complete_by (accrual_124_per_year_derived, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.5196, "5y": 1.0}
- p_primary_analysis_by (accrual_historical_11.4_per_year, no effect (HR 1)): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0, "10y": 0.0}
- p_210_events_by (accrual_historical_11.4_per_year, no effect (HR 1)): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0, "10y": 0.0}
- p_194_events_by (accrual_historical_11.4_per_year, no effect (HR 1)): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0, "10y": 0.0}
- p_169_events_by (accrual_historical_11.4_per_year, no effect (HR 1)): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0, "10y": 0.0}
- p_primary_analysis_by (accrual_124_per_year_derived, no effect (HR 1)): {"1y": 0.0, "2y": 0.0, "3y": 0.521, "5y": 1.0, "10y": 1.0}
- p_210_events_by (accrual_124_per_year_derived, no effect (HR 1)): {"1y": 0.0, "2y": 0.145, "3y": 1.0, "5y": 1.0, "10y": 1.0}
- p_194_events_by (accrual_124_per_year_derived, no effect (HR 1)): {"1y": 0.0, "2y": 0.535, "3y": 1.0, "5y": 1.0, "10y": 1.0}
- p_169_events_by (accrual_124_per_year_derived, no effect (HR 1)): {"1y": 0.0, "2y": 0.979, "3y": 1.0, "5y": 1.0, "10y": 1.0}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 11.3526 patients/year | RESOLVED: historical /year: p10 2.1 | p30 5.2 | p50 9.9 | p70 19.5 | p90 54.1 | plausible (protocol/historical median 1.15x) |
| accrual 124 patients/year | RESOLVED: historical /year: p10 2.1 | p30 5.2 | p50 9.9 | p70 19.5 | p90 54.1 | optimistic (protocol/historical median 12.56x) |
