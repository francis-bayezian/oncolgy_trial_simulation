# Trial planning report: BED-PSMA-411 (planning-report-1.1.0)

**planning predictions locked before any registry timeline was read**

## Population feasibility

- Eligible share of the screened population: 79%.
- Screen failure: 21% (eligibility stage (registry recruitment details stating screened and enrolled counts (prostate; 23 trials, 7838 screened))); patients to screen: 67 for 52.0 enrolled.

## Accrual

- Target: 52 patients (evaluable target (no stated accrual target)). Accrual durations in the protocol: none stated.
- accrual_historical_10.8_per_year (0.9/month, protocol): 52 enrolled over 4.7 years 4.7 (80% 3.9-5.6); P(complete by) 1y: 0%, 2y: 0%, 3y: 0%, 5y: 67%.
- Historical accrual model (prostate, PHASE4; matched 'prostate cancer'; protocol (quoted): '10 centers'): patients/year p10 4.2 | p30 9.4 | p50 16.4 | p70 29.4 | p90 65.9; enrollment of 52 in years p10 0.8 | p30 1.7 | p50 3.1 | p70 5.5 | p90 12.6; P(complete by) 1y: 15%, 2y: 35%, 3y: 48%, 5y: 67%.

## Sample size

- Maximum N 52; evaluable targets [52.0].

## Timelines (years from first patient in)

- last_patient_in: {"historical model (headline)": {"median": 3.1225812768419656, "q10": 0.7728396999285178, "q25": 1.4748478712043922, "q75": 6.456090866164226, "q90": 12.556327467376203, "percentiles": {"p10": 0.77283
- primary_analysis: {"years_after_start": {"historical model (headline)": {"median": 3.6225812768419656, "q10": 1.2728396999285176, "q25": 1.9748478712043922, "q75": 6.956090866164226, "q90": 13.056327467376203}, "accrua
- study_completion: {"years_after_start": {"historical model (headline)": {"median": 8.122581276841967, "q10": 5.772839699928518, "q25": 6.474847871204393, "q75": 11.456090866164226, "q90": 17.556327467376203}, "accrual_

## Retention

- {"discontinuation_before_endpoint": {"status": "RESOLVED", "withdrawal": {"value": 0.0988880352526682, "source": "registry participant flow (prostate, PHASE4): left by subject decision, loss to follow-up or physician decision; 14 trials, 1713 participants"}, "adverse_event": {"value": 0.052261049574

## Operational risk

- Trial outcome (historical failure model; SPONSOR_CLASS_UNKNOWN: averaged over the sponsor classes of historical trials of the same phase): P(withdrawn) 35%, P(terminated for poor accrual) 8%, P(terminated, other reason) 23%, P(completed) 33%. Base rates: accrual failure 15%; model AUC for accrual failure 0.68.
- p_enrollment_complete_by (historical model, headline): {"1y": 0.14925, "2y": 0.346, "3y": 0.484625, "5y": 0.6685}
- enrollment_duration_years (historical model, headline): {"median": 3.12, "q10": 0.77, "q25": 1.47, "q75": 6.46, "q90": 12.56, "percentiles": {"p10": 0.7728396999285178, "p30": 1.7425814026851116, "p50": 3.1225812768419656, "p70": 5.543603516739909, "p90": 12.556327467376203}}
- p_enrollment_complete_by (accrual_historical_10.8_per_year, conditional on the protocol's assumption): {"1y": 0.0, "2y": 0.0, "3y": 0.001, "5y": 0.6726}

## Protocol assumption stress test

| assumption | evidence estimate | status |
| --- | --- | --- |
| accrual 10.8039 patients/year | RESOLVED: historical /year: p10 4.2 | p30 9.4 | p50 16.4 | p70 29.4 | p90 65.9 | plausible (protocol/historical median 0.66x) |
