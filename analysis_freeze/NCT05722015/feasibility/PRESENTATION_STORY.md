# Protocol feasibility before the trial: presentation storyline

Nine main figures (`figures/Figure1`–`Figure9`) and six supplementary figures (`S1`–`S6`).

**Which results each figure uses:**
- **Figures 1–8:** the calibrated patient journey. This simulation was refined after the trial's results became available, with three general changes:
  1. serious adverse events anchored to the evidence estimate;
  2. progression taken from validated evidence;
  3. withdrawal that depends on protocol burden.
- **Figure 9:** the assessment produced before the results were known. It is the retrospective test.
- **Supplementary Figure S5:** shows how much the calibration changed.

**Message.** A protocol-driven simulation turns a protocol into a feasibility chain:

available patients → eligible → enrolled → treatment delivered → burden → retention → safety and progression → visits completed → endpoint captured.

Before the trial, it gave the right warning on recruitment and the right inputs for variability and safety. It also showed that the protocol does not restrict who can take part: site geography decides the population mix.

## 1. The question
**Figure 1, protocol to patient journey.**
- 378 patients randomised 2:1; at least 318 evaluable for AUC and 240 for Ctrough.
- The strip underneath follows one simulated participant: screening, randomisation, an adverse event and dose hold, scans, progression, end of treatment, follow-up.

## 2. Who can take part
- **Figure 2, attrition.** 10,000 candidates → 7,125 eligible (71%), so 1.4 screened per enrollee and 531 screened for 378.
- **Figure 3, subgroups.** Screening yield is 71–72% for women and men, younger and older patients, and White, Asian and Hispanic patients. The criteria do not remove any group disproportionately.
- **Figure 4, bottlenecks.**
  - The disease definition removes 18% of candidates; ECOG 0–1 removes 6%.
  - Relaxing ECOG would add 4.2 points of eligibility.
  - Every other criterion removes 0.3% or less.

## 3. Can they be recruited in time
**Figure 5, recruitment.**
- The plan needs 454 patients a year: the 92nd percentile of comparable trials, whose median is 63.
- There is an 8% chance of finishing within the planned 10 months.

## 4. Do they stay, and is the data captured
- **Figure 6, evaluable numbers.** At 378 enrolled:
  - 97.6% are evaluable for AUC and 71.7% for Ctrough;
  - P(≥240 Ctrough-evaluable) is 99.6%.
  - Note on the figure: the trial itself had 80% Ctrough-evaluable. The simulation assumes the 12-week scan schedule, which is simpler than the protocol's.
- **Figure 7, longitudinal feasibility.**
  - **A: what the registry shows.** Across 4,505 registry trials (753,000 participants), longer participation (OR 1.04 per doubling), more frequent visits (1.13) and more assessments (1.10) are associated with more withdrawal. These are adjusted, observational associations.
  - **B: withdrawal over time.** Withdrawal risk accumulates over each patient's attended visits. This protocol's predicted withdrawal is 6.9% (95% CI 5.8–8.3%).
  - **C: delivery and completeness.**
    - Scheduled doses are 100% received. Dose holds (4.2% of patients) fell between dosing days, and delays are not modelled.
    - Required visits completed: 89% of labs, 88% of tumour assessments and 89% of follow-up visits. The rest were lost to withdrawal or death; operational missed visits are not modelled.
    - PK samples captured: 98% (AUC); 94% of the patients whose disease course reaches the Ctrough sampling day.
  - **D: the consequence for the endpoint.** Halving or doubling follow-up frequency moves expected withdrawal by under 0.2 points. Endpoint feasibility here is barely sensitive to follow-up burden.

## 5. What planners can change
**Figure 8, trade-offs** (all scenarios on the same simulated patients):

| Change | Effect |
|---|---|
| Relax ECOG | eligible 71% → 75% |
| 20% more sites | 72 → 66 months to recruit |
| 50% women target | more screening (1.58 per enrollee) |
| 10% more enrolment | 15 more patients with a serious AE |
| One fewer follow-up visit | retention barely changes |

## 6. What happened
**Figure 9, retrospective** (the pre-trial assessment):

| Question | Assessment before the trial | What happened |
|---|---|---|
| Recruitment | demanding | upper-tail rate achieved |
| Variability (CV) | comparable trials 37% / 40% (protocol assumed 50% / 84%) | 36% / 44% |
| Serious AEs | evidence estimate 39.5% | 39.0% / 40.5% |
| Population mix | the protocol's criteria were neutral across groups | geography shaped the mix: 29% Asian, 31% Hispanic |

Synthetic-control panel: generating a control arm is feasible, but its uncertainty is too wide to replace the real one.

## Supplementary figures
- **S1:** one participant's full record.
- **S2:** patient-level withdrawal modifiers. Arm-level (ecological), not applied.
- **S3:** control-arm benchmark across registry trials.
- **S4:** every eligibility criterion.
- **S5:** effect of the journey calibration.
- **S6:** safety burden.

## Known gaps
1. Generated lab values are not yet used in the lab criteria at screening.
2. The tumour scan schedule is simplified (one 12-week interval instead of weeks 6/12/18, then every 9 weeks to week 45, then every 12 weeks).
3. The PK sampling table is redacted in the public protocol.
4. Medications and hypertension are not simulated: there is no registry evidence for them.
