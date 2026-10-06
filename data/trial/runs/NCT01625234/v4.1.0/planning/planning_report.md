# Trial planning report: X396-CLI-101 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 75%.
- Screen failure: 25% (eligibility stage (registry recruitment details stating screened and enrolled counts (lung; 41 trials, 20971 screened))); patients to screen: 255 for 190.0 enrolled.

## Accrual

- Target: 190 patients (target_accrual). Accrual durations in the protocol: none stated.
- accrual_historical_8.6_per_year (0.7/month, protocol): 190 enrolled over 21.9 years 21.9 (80% 19.9-24.0); P(complete by) 1y: 0%, 2y: 0%, 3y: 0%, 5y: 0%.
- Historical accrual model (lung, PHASE1+PHASE2; matched 'Advanced Solid Tumors and Expansion Phase in Patients with ALK+ Non-Small Cell Lung Cancer'; protocol (quoted): 'up to 24 sites'): patients/year p10 5.3 | p30 12.0 | p50 20.9 | p70 36.8 | p90 82.7; enrollment of 190 in years p10 2.3 | p30 5.1 | p50 9.1 | p70 15.8 | p90 35.9; P(complete by) 1y: 2%, 2y: 8%, 3y: 15%, 5y: 29%.

## Sample size

- Maximum N 190; evaluable targets [].

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 9.051186391701425, "q10": 2.3035108876755572, "q25": 4.361369520532229, "q75": 18.497658962156496, "q90": 35.929778241715944, "percentiles": {"p10": 2.303510
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 9.551186391701425, "q10": 2.8035108876755572, "q25": 4.861369520532229, "q75": 18.997658962156496, "q90": 36.429778241715944}, "accrual
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 14.051186391701425, "q10": 7.303510887675557, "q25": 9.361369520532229, "q75": 23.497658962156496, "q90": 40.929778241715944}, "accrual

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.07141058376491556, "source": "registry participant flow (lung): left by subject decision, loss to follow-up or physician decision; 1306 trials, 222437 participants"}, "adverse_event": {"value": 0.056583357906702735,

## Operational risk

- Trial outcome (historical failure model; INDUSTRY (protocol (quoted): company legal form: 'Xcovery Holdings, Inc.')): P(withdrawn) 1%, P(terminated for poor accrual) 4%, P(terminated, other reason) 27%, P(completed) 68%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.0195, "2y": 0.07925, "3y": 0.1505, "5y": 0.292}
- enrollment_duration_years (historical model, headline): {"median": 9.05, "q10": 2.3, "q25": 4.36, "q75": 18.5, "q90": 35.93, "percentiles": {"p10": 2.3035108876755572, "p30": 5.135700953393769, "p50": 9.051186391701425, "p70": 15.796378479729853, "p90": 35.929778241715944}}
- p_enrollment_complete_by (accrual_historical_8.6_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.0, "5y": 0.0}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 8.61694 patients/year | RESOLVED: historical /year: p10 5.3 | p30 12.0 | p50 20.9 | p70 36.8 | p90 82.7 | plausible (protocol/historical median 0.41x) |
