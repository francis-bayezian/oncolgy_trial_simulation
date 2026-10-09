# NCT05722015: locked simulation (v1.2.0) against the actual trial results

**Order:** every prediction stage was locked by 2026-10-08T21:02:53Z; the ClinicalTrials.gov record
(`data/holdout_comparison/NCT05722015.json`) was fetched at 2026-10-08T21:10:21Z: order verified. The study is in the
2023+ hold-out (started 2023-02-14), so it was never in the evidence base. Registry status: ACTIVE_NOT_RECRUITING,
primary completion 2024-07-12, results posted for the PK endpoints, baseline, participant flow and adverse events.
**Not yet posted:** ORR, PFS, OS, DOR, AE-discontinuation, quality of life. Those predictions cannot be scored yet.

Comparison outputs (each locked as `data/locked/NCT05722015/<kind>_v1.2.0`): `comparison/ratio_ni/`,
`comparison/safety/`, `comparison/baseline/`, `comparison/planning/`.

## 1. Primary endpoints: PK noninferiority (GMR, SC / IV, margin 0.8)

| Endpoint | Predicted P(noninferior) | Simulated GMR (p10-p90), protocol / registry variability | **Actual GMR (CI)** | Actual noninferior |
| --- | ---: | --- | --- | --- |
| Cycle 1 AUC0-6 wk | 1.00 | 1.00-1.15 / 1.01-1.13 (centred on design 1.07) | **1.14 (96% CI 1.06-1.22)** | yes |
| Cycle 3 Ctrough | 1.00 | 1.14-1.47 / 1.20-1.38 (centred on design 1.29) | **1.67 (94% CI 1.52-1.84)** | yes |
| Both | 0.998-1.00 | | | **yes** |

- **Conclusion: correct.** Both hypotheses met, as predicted with probability ~1.
- **Size of the ratio: underestimated.** The engine takes the true ratio from the protocol's design assumption.
  The actual AUC ratio sits at the top of the predicted range (p70-p90 under protocol variability; above p90 under
  registry variability). The actual Ctrough ratio (1.67) is above both predicted ranges: the protocol's assumption of
  1.29 was conservative.
- **Variability: the registry estimate was right; the protocol's power statement was not.**

  | Endpoint | Pooled actual CV | Registry estimate | Protocol power statement |
  | --- | ---: | ---: | ---: |
  | AUC | 36% | 37% (30 trials) | 50% |
  | Ctrough | 44% | 40% (13 trials) | 84% |

- **Evaluable participants:** 371 (AUC) and 303 (Ctrough) against the protocol's 318 and 240.

## 2. Enrolment and baseline

| | Simulated (enrolled) | Actual |
| --- | --- | --- |
| Enrolled | 378 | 377 (target 378) |
| Arm split (SC / IV) | outputs 238 / 140; analysis 261 / 117 | **251 / 126 (exact 2:1)** |
| Age, mean (SD) | 61.2 (10.6) | 64.8 (9.2) |
| Female | 54.8% | **28.9%** |
| White / Asian | 76.7% / 10.8% | 62.6% / 29.2% |
| Hispanic or Latino | 5.3% | **30.5%** |

- The registry-level baseline predictor (median and 90% interval for a lung trial) covered 12 of 13 quantities. Its
  only miss was Hispanic ethnicity (predicted 4%, actual 30.5%).
- **The simulated patients are off on sex, race and ethnicity:**
  - **Sex:** 55% female against 29%. The enrolled sex mix does not reflect NSCLC trials, which are male-dominant.
  - **Race and ethnicity:** the actual trial recruited heavily in Asia and Latin America; the simulation drew from a
    US-like mix.
- **Inconsistency found:** two locked stages carry different arm sizes, outputs 238 / 140 and analysis 261 / 117,
  and neither matches 2:1 well. The analysis and outputs stages should share one randomisation.

## 3. Accrual

- The actual trial enrolled 377 within its 1.41-year start-to-primary-completion window, at least 268 patients/year.
  That window includes follow-up, so the true rate was higher.
- **The protocol's plan (~454/year, ~10 months) was much closer to reality than the historical model:**
  - The historical model predicted a median of 67/year (80% interval 10-371) and a median of 5.7 years to target.
  - The actual rate fell at the model's 83rd percentile, inside the 80% interval but far from its median.
  - The model gave only 16.5% probability of reaching the target within the window.
- The "6.8 times the historical median, optimistic" flag in the final analysis was **wrong for this sponsor and
  trial**: a large-sponsor bridging study with many sites recruits far faster than the historical phase 3 lung median.

## 4. Safety

| | Simulated patients (outputs / analysis) | Registry evidence estimate | **Actual** |
| --- | --- | --- | --- |
| Any serious AE, SC | 55.0% / 51.0% | 39.5% (single trial p10-p90 24-58%) | **39.0% (98/251)** |
| Any serious AE, IV | 46.4% / 53.8% | 39.5% | **40.5% (51/126)** |
| Deaths, SC | 13.0% | | 24.3% (61/251) |
| Deaths, IV | 16.2% | | 29.4% (37/126) |

- **Serious AEs:** the registry evidence estimate was almost exact (39.5% against 39.0% and 40.5%). The simulated
  patients overstated serious AEs by 6-15 points. The patient-level event generation adds risk on top of a
  well-calibrated arm rate.
- **Deaths:** the actual counts are all-cause deaths over ~28 months of AE reporting. The simulated deaths are at the
  simulated data cut-off, so the windows differ. Still, the simulation **underpredicts mortality** by about 11-13
  points.
- **Per event** (58 terms matched, pooled arms):
  - 53 of 58 fell inside the 90% predictive interval, and all 24 predicted-but-unlisted terms were consistent.
  - The 5 misses are all non-serious events over-predicted at 6-9% where the registry lists 1 case: stomatitis,
    abdominal pain, hypertension, haemoptysis, hypotension.
- **Accuracy and informativeness:** serious-event rates have a median absolute error of 0.9 points (12 terms).
  Non-serious rates have a median absolute error of 6.3 points and run high (33 of 46 over). The intervals are wide:
  the median 90% interval spans 163 of 377 patients, so the coverage is cheap and the estimates are not informative.
- **Not predicted:** 100 registry terms, e.g. lymphocyte count decreased 34, hyperthyroidism 26, LDH increased 26.

## 5. Not yet comparable

ORR (predicted 18.8% / 16.2%), PFS (HR 0.97, medians 5.5 months), OS (HR 0.98, medians 14.5 / 14.3 months): the
registry lists these outcomes without data. They can be scored when posted, or from the publication if you supply it.

## 6. What this says about the pipeline (general, not trial-specific)

1. **Primary conclusion right.** The ratio-NI engine was right on the decision. It was also right to offer the
   registry variability as the sensitivity case: that CV matched reality and the power-statement CV did not.
2. **Patient generation needs disease-specific demographics.** Sex and region/ethnicity mix should come from
   comparable trials' baseline tables (as ECOG and disease variables already do), not from a general population.
3. **One randomisation.** Arm allocation must be a single shared draw across stages.
4. **Patient-level AE generation inflates the arm totals.** It should be anchored so that arm-level any-serious rates
   match the calibrated arm estimate, which was accurate here.
5. **Mortality is under-simulated.** Deaths should be compared on a matched follow-up window.
6. **The accrual model ignores sponsor scale.** It is too pessimistic for large industry trials. Sponsor class and
   site count were already inputs, so this needs investigation across more trials before any change; one trial is
   not a calibration.

## 7. Hidden-control benchmark on this trial's control arm (IV pembrolizumab + chemotherapy)

Each benchmark method predicts the control arm without seeing it. Inputs:
- **Control-arm context:** lung, phase 3, PD-1/PD-L1 inhibitor + platinum + taxane + antimetabolite, start 2023,
  multinational.
- **Population:** either the experimental arm's posted baseline (the benchmark's definition) or the simulated
  experimental arm (protocol only).
- **Training:** the contextual model's settings were learned on all corpus trials; this trial is outside the corpus.

Full table: `comparison/control/control_external.md`.

| Method | Serious AE: predicted mean (95% interval) | Deaths: predicted mean (95% interval) |
| --- | --- | --- |
| **Actual control arm** | **40.5% (51/126)** | **29.4% (37/126)** |
| contextual_robust | 52% (6-95) | 76% (9-100) |
| evidence_calibrated | 46% (2-97) | 72% (6-100) |
| outcome_regression | 52% (44-61), **miss** | 90% (84-94), **miss** |
| map_prior | 32% (13-57) | 55% (10-94) |
| naive_pooled | 33% (25-41) | 60% (51-68), **miss** |

Population: the experimental arm's posted baseline. With the simulated population (protocol only) the means move
1-8 points the same way: higher women share, lower age.

- **Serious AEs:** every method except outcome regression covers the actual rate, but only naive pooling and the
  meta-analytic prior are informative. The contextual and evidence-calibrated intervals span nearly 0-100%: covered,
  but useless (their interval score is high because of width).
- **Deaths: all methods are biased high**, at 55-95% against an actual 29%. Historical lung control arms report deaths
  over long follow-up, while this trial reported at ~28 months with an active, modern immunotherapy control. The
  outcome "death" is not time-matched, so this is the same window problem as in section 4. It is not fixable by
  weighting.
- **Conclusion for the control model:** on this trial it gives coverage only through very wide intervals. It does not
  yet deliver the informative estimates wanted. The two general gaps are a follow-up-time adjustment for deaths, and
  recency or immunotherapy-era context. Start year is in the model, but there are few comparable 2019+ arms with this
  regimen.
