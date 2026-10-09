# Protocol feasibility before the trial: NCT05722015 storyline

Run v1.2.0, locked before the registry results were read (predictions locked 2026-10-08 21:02 UTC, registry fetched
21:10 UTC). All figures are in `figures/`. Numbers come from `FEASIBILITY.md` and `../COMPARISON.md`.

**The message:** a protocol-driven simulation, run before the trial, gave planners the right warning on recruitment and
the right inputs for variability and safety burden. It also showed that the protocol does not restrict who can take part:
the population mix is set by where the trial recruits. Two patient-level outputs are shown as known limitations.

---

## Part 1: The question (1 slide)

**Figure 1: From protocol requirements to a feasible patient journey.**
The protocol asks for 378 patients randomised 2:1. At least 318 must be evaluable for AUC and at least 240 for
Ctrough. The feasibility question runs along the whole pathway, not just enrolment.

## Part 2: What the assessment got right (4 findings)

**1. Recruitment was demanding (Figure 5).**
- Planned 454 patients per year (378 in about 10 months). That is the 92nd percentile of comparable phase 3 lung
  trials, whose median is 63 per year.
- Chance of enrolling all 378 within 10 months: 8%.
- *Planning value:* the plan needed upper-tail recruitment. Check sites and countries and prepare contingency.
- *What happened:* 377 enrolled at least 268 per year, which is upper-tail performance. The warning was the right one,
  and the sponsor delivered.

**2. The protocol's variability assumptions were too pessimistic (Figure 9, row 2).**
- Comparable pembrolizumab trials: geometric CV 37% for AUC (30 trials) and 40% for Ctrough (13 trials).
- The protocol's power statement implied 50% and 84%.
- *What happened:* observed CV 36% and 44%. External evidence gave better design inputs than the protocol's own
  assumption.

**3. Safety burden for sites (Figure 9, row 3).**
- Comparable trials: 39.5% of patients with a serious adverse event, about 149 of 378.
- *What happened:* 39.0% (subcutaneous) and 40.5% (intravenous). Sites could have planned SAE management, reporting and
  monitoring capacity accurately.

**4. The protocol is neutral across patient groups; geography decides the mix (Figure 3).**
- Screening yield is 71-72% for women and men, for under-65s and older patients, and for White, Asian and Hispanic
  patients. The eligibility criteria do not disproportionately remove any group.
- *Planning value:* representation will not be limited by the protocol. It will be set by the countries and sites
  chosen, so diversity is an operational decision.
- *What happened:* the trial's site footprint produced 29% Asian and 31% Hispanic participants, far more than a generic
  population mix (9% and 5%).

## Part 3: How the assessment works (3 slides)

**Figure 2: Patient attrition across the trial pathway.**
10,000 candidates → 7,125 eligible (71%). That means 1.4 screened per enrollee, or 531 screened for 378. The largest
losses are the disease and stage definition (19%) and performance status (6%).

**Figure 4: Which criteria create the bottleneck.**
Apart from the disease definition, only the ECOG 0-1 requirement matters: relaxing it would add 4.2 points of
eligibility. Every other criterion removes 0.3% or less.

**Figure 8: Protocol changes create measurable trade-offs.**
Each row is a scenario computed from the same simulated patients:
- relax ECOG;
- 20% more sites;
- a longer recruitment window;
- a regional mix;
- a 50% female target;
- 10% more enrolment;
- one fewer follow-up visit.

*Caveat for the speaker:* the evaluable and serious-AE columns inherit the two limitations in Part 4. Use this figure to
show the method of comparing scenarios, not the exact enrolment recommendation.

## Part 4: Known limitations (2 slides, shown honestly)

**Figure 6: evaluable patients.** The simulation gave 64% evaluable for Ctrough at 378 enrolled, and suggested about 400
enrolled for 90% assurance. The trial had 80% (303 of 377). Simulated patients leave treatment earlier than real
patients did: progression is modelled from a 4.9-month median PFS, and treatment ends at progression. The figure
carries this note.

**Figure 7: patient-level safety.** Simulated patients had 52% serious adverse events against the 39.5% evidence
estimate and the trial's 39-40%. The arm-level estimate was right; the patient-level event generation overshoots it.
The figure carries this note.

Reweighting the simulated patients to the trial's actual mix (29% women, about 49% aged 65 or older, 29% Asian) does
not close either gap: serious AE 51% and Ctrough evaluable 64%. The gaps sit in the patient-journey model, not in the
population mix.

## Part 5: Close (1 slide)

**Figure 9: Retrospective evaluation of pre-trial feasibility signals.**
The pre-trial assessment flagged the demanding recruitment and gave realistic variability and safety inputs. It also
showed that composition depends on geography. The evaluable-number and patient-level safety estimates need the two
calibrations below.

**Next step (paper):** two general fixes to the patient journey, neither specific to this trial:
- anchor each patient's serious-adverse-event risk to the arm-level evidence estimate;
- calibrate how long patients stay on study.

The paper reruns the case study with both fixes and reports the before and after.
