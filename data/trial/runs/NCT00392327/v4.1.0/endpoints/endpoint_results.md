# Simulated trial results

## Participant flow

| Arm | Started | Deaths | End of treatment |
| --- | ---: | ---: | --- |
| ARM1 REGIMEN A | 202 | 13 | completed planned treatment: 143; disease progression: 29; withdrawal (subject, loss to follow-up or physician decision): 15; adverse event (registry discontinuation rate): 11; death: 4 |
| ARM2 REGIMEN B | 198 | 13 | completed planned treatment: 141; disease progression: 33; withdrawal (subject, loss to follow-up or physician decision): 14; adverse event (registry discontinuation rate): 8; death: 2 |

## Endpoints

### primary: event-free survival (EFS) percentage
- ARM1: median not reached; event-free at 12m 72.2%, 24m 61.7%, 36m 59.7%, 60m 58.1%; 84 events / 202; input: journey progression model - locked outcome model control curve: cure_model
- ARM2: median not reached; event-free at 12m 72.6%, 24m 66.4%, 36m 64.3%, 60m 61.0%; 76 events / 198; input: journey progression model - locked outcome model control curve: cure_model

### secondary: tumor response to radiation therapy ± carboplatin
- ARM1: 62/202 (30.7%, 95% CI 24.4%-37.6%; predictive p10 24% | p30 28% | p50 31% | p70 34% | p90 38%); input: trials with overlapping drug classes - evidence arms reporting objective_response_rate (3 studies)
- ARM2: 61/198 (30.8%, 95% CI 24.5%-37.7%; predictive p10 24% | p30 28% | p50 30% | p70 33% | p90 39%); input: trials with overlapping drug classes - evidence arms reporting objective_response_rate (3 studies)

### secondary: time to death
- ARM1: median 7.85 months (95% CI [6.71, 8.87]; predictive p10 7.1 | p30 7.6 | p50 7.8 | p70 8.4 | p90 9.0); event-free at 12m 33.9%, 24m 10.8%, 36m 3.1%, 60m 0.5%; 197 events / 202; input: journey progression rate - taken from the simulated patients' event times (no reported median for this endpoint)
- ARM2: median 7.73 months (95% CI [7.1, 9.41]; predictive p10 6.4 | p30 6.8 | p50 7.6 | p70 8.7 | p90 9.1); event-free at 12m 36.9%, 24m 14.3%, 36m 3.7%; 194 events / 198; input: journey progression rate - taken from the simulated patients' event times (no reported median for this endpoint)

### safety: grade 4 ototoxicity rates
- ARM1: any serious AE 76/202, any grade >= 3 76, stopped for an AE 11
- ARM2: any serious AE 88/198, any grade >= 3 88, stopped for an AE 8

### exploratory: two-year QOL and NP assessment
Not simulated (patient_reported_outcome): the generated patients carry no such measurement.

