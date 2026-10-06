# Trial planning report: 03859427 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 81%.
- Screen failure: 19% (eligibility stage (registry recruitment details stating screened and enrolled counts (myeloma_and_plasma_cell; 12 trials, 2371 screened))); patients to screen: 566 for 460.0 enrolled.

## Accrual

- Target: 460 patients (target_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_68.6_per_year (5.7/month, protocol): 460 enrolled over 6.7 years 6.7 (80% 6.3-7.1); P(complete by) 1y: 0%, 2y: 0%, 3y: 0%, 5y: 0%.
- Historical accrual model (myeloma_and_plasma_cell, PHASE3; matched 'Relapsed or Refractory Multiple Myeloma'; protocol (quoted): 'Approximately 100 investigative sites'): patients/year p10 27.7 | p30 62.3 | p50 110.1 | p70 195.6 | p90 443.9; enrollment of 460 in years p10 1.0 | p30 2.3 | p50 4.2 | p70 7.4 | p90 16.7; P(complete by) 1y: 9%, 2y: 25%, 3y: 38%, 5y: 56%.

## Sample size

- Maximum N 460; evaluable targets [].

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 4.177723512190325, "q10": 1.044467481846216, "q25": 2.01897610417001, "q75": 8.666961468250154, "q90": 16.70237421875884, "percentiles": {"p10": 1.0444674818
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 5.097565824936711, "q10": 1.9643097945926025, "q25": 2.938818416916396, "q75": 9.58680378099654, "q90": 17.622216531505227}, "accrual_h
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 9.177723512190326, "q10": 6.044467481846216, "q25": 7.01897610417001, "q75": 13.666961468250154, "q90": 21.70237421875884}, "accrual_hi

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.0665911934427771, "source": "registry participant flow (myeloma_and_plasma_cell, PHASE3): left by subject decision, loss to follow-up or physician decision; 102 trials, 36525 participants"}, "adverse_event": {"value

## Operational risk

- Trial outcome (historical failure model; INDUSTRY (protocol (quoted): company legal form: 'Amgen Inc.')): P(withdrawn) 14%, P(terminated for poor accrual) 6%, P(terminated, other reason) 18%, P(completed) 62%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.094, "2y": 0.247125, "3y": 0.382125, "5y": 0.564875}
- enrollment_duration_years (historical model, headline): {"median": 4.18, "q10": 1.04, "q25": 2.02, "q75": 8.67, "q90": 16.7, "percentiles": {"p10": 1.044467481846216, "p30": 2.3479511861151625, "p50": 4.177723512190325, "p70": 7.381766869387134, "p90": 16.70237421875884}}
- p_enrollment_complete_by (accrual_historical_68.6_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 68.6142 patients/year | RESOLVED: historical /year: p10 27.7 | p30 62.3 | p50 110.1 | p70 195.6 | p90 443.9 | plausible (protocol/historical median 0.62x) |
