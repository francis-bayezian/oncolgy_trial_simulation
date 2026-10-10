# Protocol feasibility: presentation storyline

Generated from the case-study summary of the final run; every number below comes from it.

Nine main figures (`figures/Figure1`–`Figure9`) and six supplementary figures (`S1`–`S6`).

## 1. The question
**Figure 1, protocol to patient journey.** 378 patients randomised 2:1; at least 318 evaluable for AUC and 240 for Ctrough. The strip underneath follows one simulated participant.

## 2. Who can take part
- **Figure 2, attrition.** 10,000 candidates → 7,124 eligible (71%): 1.4 candidates screened per eligible patient; 531 screened to find 378 eligible. Eligible patients who decline are not modelled.
- **Figure 3, subgroups.** Screening yield: women 70%, men 72%, under 65 72%, 65 or older 70%. Eligibility did not materially change representation across the groups examined. The simulated eligible pool is 40% women and 15% Asian.
- **Figure 4, bottlenecks.** The disease definition removes 18% of candidates; relaxing ECOG performance status would add 4.3 points of eligibility.

## 3. Can they be recruited in time
**Figure 5, recruitment.** The plan needs 454 patients a year, the 92nd percentile of comparable trials (median 63); there is a 8% chance of finishing within the planned 10 months.

## 4. Do they stay, and is the data captured
- **Figure 6, evaluable numbers.** At 378 enrolled, 366 patients are evaluable for AUC and 263 for Ctrough; P(≥240 Ctrough-evaluable) is 96.6%.
- **Figure 7, longitudinal feasibility.**
  - **A:** across 4,505 registry trials, longer participation (OR 1.04 per doubling), more frequent visits (1.13) and more assessments (1.10) are associated with more withdrawal (adjusted, observational).
  - **B:** withdrawal risk accumulates over each patient's attended visits; the burden model predicts 6.9% for this protocol, and 7.7% of the simulated cohort withdrew.
  - **C:** treatment delivery 100% of administrations scheduled while on treatment (dose delays and missed doses are not modelled: an upper bound); required visits completed: labs 88%, tumour assessments 87%, follow-up 87%; PK samples captured 97% (AUC) and 93% (Ctrough, of patients whose course reaches the sample).
  - **D:** changing follow-up frequency moves withdrawal from 7.6% to 7.8%; Ctrough-evaluable patients stay near 263.

## 5. What planners can change
**Figure 8, trade-offs** (original protocol: eligible 71%, 72 months to recruit, 150 patients with a serious AE, 263 Ctrough-evaluable):
- Relax: ECOG performance status: eligible 76%, 1.32 screened per eligible patient, 68 months, 150 with a serious AE, 263 Ctrough-evaluable
- 20% more sites: eligible 71%, 1.40 screened per eligible patient, 66 months, 150 with a serious AE, 263 Ctrough-evaluable
- Recruitment window +6 months: eligible 71%, 1.40 screened per eligible patient, 72 months, 150 with a serious AE, 263 Ctrough-evaluable
- Regional mix: +20 points East Asia: eligible 71%, 1.40 screened per eligible patient, 72 months, 150 with a serious AE, 263 Ctrough-evaluable
- 50% female target: eligible 71%, 1.76 screened per eligible patient, 90 months, 150 with a serious AE, 263 Ctrough-evaluable
- Enrolment +10%: eligible 71%, 1.40 screened per eligible patient, 79 months, 165 with a serious AE, 289 Ctrough-evaluable
- One fewer follow-up visit: eligible 71%, 1.40 screened per eligible patient, 72 months, 150 with a serious AE, 263 Ctrough-evaluable

## 6. Comparison with the trial
**Figure 9.** Variability: comparable trials CV 37% / 40% (protocol assumed 50% / 84%). Safety: historical arm-level estimate 39.5%; simulated cohort incidence 39.7% (150 of 378). Synthetic-control panel: control-arm serious AE (and response rate, when added).

## Supplementary figures
S1 one participant's full record · S2 patient-level withdrawal modifiers (arm-level, not applied) · S3 control-arm benchmark · S4 every eligibility criterion · S5 effect of the journey calibration · S6 safety burden.

## Known gaps
1. Generated lab values are not yet used by the lab criteria at screening.
2. The tumour scan schedule is simplified to one 12-week interval.
3. The PK sampling table is redacted in the public protocol.
4. Medications and hypertension are not simulated (no registry evidence).
