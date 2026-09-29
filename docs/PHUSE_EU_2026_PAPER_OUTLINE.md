# PHUSE EU Connect 2026: paper and presentation plan (v2)

The accepted title and abstract are kept word for word. This version rebuilds the plan around what award-winning PHUSE presentations have in common, and keeps every scientific safeguard from v1. v1 is archived outside the repository.

In this plan:

- Numbers marked **[VERIFIED: path]** exist in a locked artifact.
- Items marked **[TO COMPUTE]** must be produced by a pipeline stage before they appear in the paper.
- No number is to be typed in by hand.

## Accepted title

Protocol-Informed Synthetic EHR Generation for Clinical Trial Feasibility Assessment and Synthetic Control Arm Simulation

## Accepted abstract

Clinical trial feasibility decisions are often made before suitable patient-level data are available, making it difficult to assess how eligibility criteria, visit schedules, safety monitoring and endpoint rules may affect recruitment, retention and data completeness.

We present a protocol-informed synthetic EHR pipeline that converts a trial protocol into a structured simulation specification covering screening rules, treatment arms, visit windows, procedures, dosing constraints and safety requirements. Baseline patients are generated with protocol-relevant demographics, comorbidities, medications, laboratory values and vitals, then screened to distinguish eligible patients from screen failures with reasons captured.

For enrolled patients, a traceable longitudinal simulation generates EHR-style visit histories across arms, including disease progression, adherence, treatment exposure, adverse events, dose changes, dropout and endpoint capture. The system also produces cohort feasibility metrics, parameter tables, validation outputs and patient-level traces, supporting protocol stress-testing, scenario analysis and synthetic control arm exploration.

---

## 1. What the award-winning examples did, and how we go further

The patterns below come from six recognised PHUSE presentations. They are listed by the pattern each one used.

| Pattern | Example | What it did | How we match it, then exceed it |
| --- | --- | --- | --- |
| **A pain the audience recognises, in one image** | SA02 (Novo Nordisk): "bomb from a blue sky" | Opens on a situation every programmer has lived through, with a recurring character | Open on a protocol that promised 124 patients a year and managed about 7. Everyone in the room has seen a trial fail on recruitment. |
| **One pipeline diagram, repeated as a progress map** | DH02 (Chrestos): raw → vendor → SDTM → unique variants → ADaM, with the current step highlighted | The audience never gets lost | One strip, **PDF → StudySpec → population → screening → cohort → simulation → ADaM-style datasets → feasibility report**, shown on every section slide with the current stage lit |
| **Simulated case study run through every step** | DH02: crizotinib resistance | Same example at each stage | One running trial through every stage (section 3), plus the same registry record through the evidence layers (sections 4–5) |
| **Honest comparison of approaches** | ET05 (Syneos): A/B/C approaches, traffic lights, failure-mode table | Shows why the structured approach is safer | Three ways to estimate feasibility: **(A)** the protocol's own assumption, **(B)** a naive registry average, **(C)** the pipeline, scored against what actually happened. Also free-text-to-LLM versus our compile, verify, lock route, with a failure-mode table. |
| **Head-to-head numbers** | RE06 (Pfizer): PostgreSQL vs Neo4j timings on 80,000 synthetic patients | Real, reproducible measurements | Coverage and error on 658 / 21,820 / 31,267 held-out registry observations, with the older model (V2) as a comparator |
| **One headline metric plus a shown failure** | ML09 (Merck): MRR 0.97 overall, 0.82 on hard cases, and a failure case with RR = 0 | A number judges remember, with credibility from the failure | The headline calibration numbers, **plus the blind misses shown in full** (any serious adverse event, 14.5% predicted vs 48% observed) |
| **Plain disclaimer and human in the loop** | ML09: "proof of concept … not incorporated into any standard processes" | Protects credibility | Disclaimer slide: research prototype, synthetic records, no causal claim, protocol-derived rules flagged REVIEW_REQUIRED |
| **CDISC relevance** | DH02 (SDTM GF → ADaM), ET05 (ADAE, TRT01P, SAFFL) | Speaks the audience's language | ADSL / ADAE / ADTTE-style outputs from simulated patients. Screening status maps to eligibility flags. |
| **Before and after, quantified** | SA02: 5.0 → 2.4 person-hours per thread | Concrete benefit | Time from PDF to locked feasibility package **[TO COMPUTE: wall-clock from the stage logs]**. Recruitment error of the protocol assumption vs the pipeline **[VERIFIED for 2 blind trials]**. |
| **A takeaway line** | SA02: "Thoughtful integration > revolutionary technology" | Memorable close | "**Lock the prediction before you look.**" Feasibility tools should be judged the way trials are: pre-specified, blinded and scored. |
| **Speaker authenticity** | LI05: personal, simple four-quadrant framework | Relatable delivery | A simple four-box framework for any feasibility estimate: *Where did the number come from? How sure is it? What would change it? Was it tested blind?* |

**Where none of the six went, and our distinctive contribution:** a **pre-registered blind test**. Predictions are locked by checksum before the registry results are fetched. Trial categories are sealed with salted hash commitments, and the order is verified by the unsealing step. None of the six examples evaluated against outcomes that were hidden at prediction time. This is the part judges have not seen before, so it leads section 6 and the talk's second half.

## 2. The story in one line, and its arc

**One-line message:** *A protocol PDF can be turned automatically into a locked, testable feasibility forecast. When we tested it blind, it caught unrealistic recruitment assumptions, and it showed plainly where its safety and efficacy estimates were still wrong.*

**Arc** (problem, pipeline, proof, limits, takeaways):

1. **Hook:** a real protocol's recruitment assumption against reality (BLIND_1).
2. **Why protocols can't answer feasibility on their own:** thresholds are not distributions.
3. **The pipeline:** one strip diagram.
4. **Walk-through:** one trial, every stage.
5. **Where the probabilities come from:** the evidence and parameter layers, one worked record.
6. **Proof:** registry-scale calibration, then the blind test.
7. **What failed, and why that's useful.**
8. **What's implemented, what isn't, and how to reuse it.**

## 3. Running examples (fixed across paper and slides)

| Role | Trial | Why this one | Constraint |
| --- | --- | --- | --- |
| **Hook and feasibility headline** | BLIND_1, NCT04003610 (randomized phase 2, urothelial) | Recruitment assumption vs pipeline vs reality; blind | Registry data are public. The protocol text is not for redistribution: quote a sentence at most, and only after checking permission. |
| **End-to-end walk-through** | ACNS0332, NCT00392327 (development set) | Richest completed chain; control arm predicted within the reported CI | Label it as **development (unblinded)** on every slide. Same quotation constraint. |
| **Evidence-layer worked record** | NCT00091572 (124/419 serious events) | Fully traced from raw registry record to parameter | Public registry data |
| **Shown failure** | BLIND_2, NCT04205799 (any serious event 14.5% vs 48%) | The honest miss | Public registry data |

## 4. Paper structure (target 3,800–4,300 words; check the PHUSE template)

### 4.1 Introduction: "124 a year, on paper" (350 words)

- Open with BLIND_1. The protocol-derived accrual implied about 124 patients a year. The locked pipeline forecast was 9.9 a year (80% interval 2.1–53.5). The registry shows the trial stopped after 7 patients, at least 7.5 a year. **[VERIFIED: data/trial/blind/blind_results.md]**
- State the problem: a protocol gives rules (an haemoglobin threshold, a target response rate), not distributions. Feasibility needs both.
- Three contributions:
  1. **Protocol compiler:** PDF to a locked, executable specification, with unresolved items left visible rather than guessed.
  2. **Evidence and parameter layers:** registry findings kept with their statistical context and fitted to calibrated distributions.
  3. **Blind evaluation protocol:** sealed trial categories, checksummed predictions, verified order.
- Related work, compared on concrete properties: rule-based EHR generators (e.g. Synthea), LLM spec-to-code workflows, and recruitment-prediction models. Compare inputs, evidence traceability and validation design.
- **Figure 1:** the pipeline strip. This same strip is reused as the progress map.

### 4.2 From protocol PDF to executable specification (500 words)

- Ingest, including an OCR fallback for PDFs whose text layer cannot be read (BLIND_3).
- Compile to StudySpec and verify with a three-vote check.
- Resolve or leave: a rule is either executable or explicitly UNRESOLVED / REVIEW_REQUIRED. Nothing is filled in silently.
- **Table 1 (ET05-style failure modes):** rows are denominator or threshold misread, wrong population filter, invented value, ambiguous rule, audit gap. Columns are a free-text LLM prompt vs our compile, verify and lock route.
  - Use only failure modes we actually observed. For example, "< 8/22" was once read as 22 and fixed by the threshold parser; alpha was misread as 1.0 in BLIND_1 and not caught.
  - Report both what the route catches and what it missed.
- One executable rule and one unresolved rule, shown side by side.

### 4.3 Where the probabilities come from: evidence and parameter layers (900 words)

This condenses v1 sections 2–4. Keep it rigorous but reduce it to one worked lane.

- **Source controls, in one table (Table 2):** 1,000 trials; 2,771 profiles; 229 repairs; 0 schema errors; 160 retained flags; 106,185 evidence rows after removing 692 duplicates. **[VERIFIED: data/asset_v1/manifest.json, data/simulation_parameters_v1/manifest.json]** Rows are observations, not patients.
- **Worked lane (Figure 2):** the NCT00091572 registry group reports 124 affected out of 419.
  - The evidence row is `d9b934b17937e424`.
  - The V3 parameter is `3b1473de78a0a559`.
  - It has three summaries: within-study Beta(124.5, 295.5); population posterior 27.3% (8.5–56.8); future-study probability 26.3% (2.5–84.9).
  - Keep the point that the 429-patient efficacy denominator is not the 419-patient safety denominator.
- The binomial hierarchy is stated in one equation, with the implementation in the supplement.
- The operational (accrual and failure) and safety assets are separate corpora, and are drawn as separate branches.

### 4.4 Walk-through: one protocol, every stage (450 words, CDISC-facing)

This follows DH02's structure: the same strip with one stage lit at a time, using ACNS0332 (development).

1. The population is drawn from the parameters.
2. Screening gives ELIGIBLE / INELIGIBLE / UNDETERMINED, with the failed or unchecked criteria named.
3. Enrolment at an accrual scenario, then randomisation.
4. Simulation of the endpoints and adverse events.
5. **ADSL / ADAE / ADTTE-style datasets**, with a short extract as **Table 3**: variable, source parameter, protocol rule.
6. Feasibility report: screening funnel, sites needed, time to target, failure risk.

**Figure 3:** a parameter-to-patient trace showing the source record, parameter version, sampled value, eligibility result and output field.

Dependence assumptions, stated plainly:
- Demographics are independent where no patient-level evidence exists.
- Adverse events use a one-factor copula matched to the any-serious-event estimate.

### 4.5 Evaluation I: registry-scale calibration (500 words)

This is the RE06/ML09-style headline table.

**Table 4** **[VERIFIED: data/validation/scorecard.md]**

| Component | Held out | Coverage at nominal | Sharpness |
| --- | ---: | --- | --- |
| Accrual rate | 658 | 52 / 82 / 94% at 50 / 80 / 95% | median relative error 60% |
| Trial accrual failure | 21,820 | calibrated | AUC 0.68 |
| Adverse-event counts (V3.1) | 31,267 obs. | 94% at 90% | log score −1.90 vs −2.77 for V2 (in-sample) |
| Baseline mean age / share female | 80 | 91% / 95% at 95% | MAE 5.2 y / 0.107 |
| Outcome proportions | 312 | 96% at 95% | median 95% width 0.82 |
| Survival (medians, landmarks) | 355 | 95% at 95% | consistency check only (the HR posterior includes the trial) |

- Say plainly that **coverage passes and sharpness is poor.** Wide intervals are honest but less useful.
- **Comparison of approaches (ET05 A/B/C):** on the same held-out trials, score
  - (A) the rate the protocol states, where one exists,
  - (B) a naive pooled registry mean,
  - (C) the pipeline.

  **[TO COMPUTE: a predeclared pipeline stage; report whatever it shows]**

### 4.6 Evaluation II: the blind test (600 words; the distinctive section)

- **Design, Figure 4:** 5 development protocols (unblinded, used for fixing). Then 3 trials chosen by script, one per category (terminated for accrual, terminated for safety, completed), with the categories held as salted commitments. Then lock, fetch, unseal, verify order.
- **Results, Table 5.** Each quantity against the registry.

  | Quantity | Result | Verdict |
  |---|---|---|
  | Individual adverse events | 41/43 inside 90% intervals | hit (intervals wide) |
  | Accrual | 2 of 2 scoreable trials inside 80% intervals | hit; pipeline beat the protocol's own assumption both times |
  | Any serious adverse event | 58.8% vs 2/7; 14.5% vs 26/54 | two misses |
  | BLIND_1 control-arm PFS median | 4.5 vs 2.1 months (n = 6) | miss |
  | Failure model | did not flag either terminated trial | miss |

  Accrual detail:
  - BLIND_1: 9.9/y against at least 7.5 observed; the protocol implied 124/y.
  - BLIND_2: 7.3/y against at least 19 observed; the protocol stated 3/y.
- **Figure 5:** predicted vs observed, with the protocol assumption as a third marker, for each scoreable quantity.
- **What limits the claim (keep it in the main text, not a footnote):**
  - n = 3, two of which enrolled 7 patients and 1 patient.
  - Pipeline code was fixed during the run, before any fetch.
  - One scoring stage was written after unsealing; it scores locked predictions and changes none.
  - The sealing rule matched "safety" inside a negated sentence, so BLIND_1 was actually a business termination.
  - The alpha = 1.0 misread made BLIND_1's success probability invalid.
  - There was no planning-date evidence cutoff, and public information may be present in model pretraining.

### 4.7 Synthetic control arm: what it can and cannot do (300 words)

- The control curve is derived from evidence: BLIND_1 used 3 urothelial studies.
- Report the estimand, time origin and borrowing level.
- The 2.4-month miss at n = 6 is shown, not hidden.
- No exchangeability or causal claim.

### 4.8 Discussion, reuse and limits (350 words)

- **Reusable:**
  - the resolve-or-leave compiler pattern;
  - the evidence-row schema;
  - the parameter records with borrowing metadata;
  - the lock-and-seal blind evaluation protocol, which works with any feasibility tool.
- **Capability boundary (Table 6, condensed from v1's capability map):**

  | Status | Capabilities |
  |---|---|
  | Implemented and evaluated | demographics, screening, accrual, adverse events, time-to-event, ADaM-style outputs |
  | Implemented, not validated | escalation ladders |
  | Not implemented | labs, vitals, comorbidities and medications as generated distributions; visit-driven endpoint capture; adherence |

  The accepted abstract names these; the body states the implemented subset.
- **Takeaway line:** "Lock the prediction before you look."

## 5. Presentation plan (about 20 minutes, about 18 slides)

| # | Slide | Pattern borrowed |
| --- | --- | --- |
| 1 | Title (accepted wording) + subtitle hook: *"Would this protocol have recruited?"* | – |
| 2 | Disclaimer: research prototype, synthetic records, no causal claims | ML09 |
| 3 | **Hook:** 124/year on paper vs 7 patients in reality, as one big-number slide | SA02 pain point |
| 4 | Why a protocol can't answer this alone: rules ≠ distributions (the haemoglobin example) | – |
| 5 | Four questions to ask of any feasibility number (source / certainty / sensitivity / tested blind?) | LI05 four-box |
| 6 | **Pipeline strip** (the recurring map) | DH02 |
| 7 | Stage 1 lit: PDF → StudySpec; one executable rule and one UNRESOLVED rule | DH02 + ET05 |
| 8 | Free-text LLM vs compile, verify, lock: the failure-mode table (traffic lights) | ET05 |
| 9 | Stage 2 lit: where probabilities come from, with the 124/419 lane (one image) | DH02 |
| 10 | Stages 3–5 lit: screening funnel → cohort → ADSL/ADAE/ADTTE extract | DH02 CDISC tables |
| 11 | Feasibility report page (a real artifact screenshot) | RE06 practical output |
| 12 | Registry-scale scorecard: coverage vs nominal plot, with sharpness beside it | RE06/ML09 headline |
| 13 | A/B/C: protocol assumption vs naive average vs pipeline **[TO COMPUTE]** | ET05 comparison |
| 14 | **Blind test design:** seal → lock → fetch → unseal (hash diagram) | *new: our distinctive slide* |
| 15 | Blind results: hits (accrual, individual AEs) | – |
| 16 | **Blind misses, shown in full** (any-SAE, control PFS, failure model, sealing flaw) | ML09 failure case |
| 17 | What's implemented / what isn't (capability boundary) | ML09 honesty |
| 18 | Takeaways + "Lock the prediction before you look." | SA02 closing line |

Optional: a 60–90 second **recorded run** from PDF to the locked feasibility report. Neither RE06 nor DH02 showed a live pipeline, so this would be distinctive. Record it in advance; don't demo live.

**Visual language:**
- Colours: blue = reported evidence, purple = fitted distribution, teal = synthetic output, grey = unknown or unresolved. Use labels as well as colour.
- One recurring motif: the strip, and optionally a simple original mascot, as SA02 did.
- Plots are generated from the artifacts, not drawn.

## 6. Figures and tables (generated by script from locked artifacts)

| Item | Content | Source |
| --- | --- | --- |
| Fig 1 | Pipeline strip | diagram |
| Fig 2 | 124/419 lane: raw → row → three distributions (from stored draws) | V1 evidence table, V3 parameter index and draws |
| Fig 3 | Parameter-to-patient trace | ACNS0332 locks |
| Fig 4 | Blind-test design (seal / lock / fetch / unseal) | blind manifest, unsealing.json |
| Fig 5 | Predicted vs observed vs protocol assumption | blind locks + comparisons |
| Fig 6 | Coverage vs nominal, with interval width | scorecard |
| Tab 1 | Failure modes: free-text vs compiled route | observed defects log |
| Tab 2 | Source-quality controls | asset V1 manifest |
| Tab 3 | ADaM-style extract | outputs lock |
| Tab 4 | Registry-scale scorecard | data/validation/scorecard.md |
| Tab 5 | Blind results | data/trial/blind/blind_results.md |
| Tab 6 | Capability boundary | this plan |

## 7. Rules that stay from v1

- Do not change the accepted wording, or fill missing distributions to make the software match it.
- The development set is always labelled unblinded. The blind results are not re-scored after any pipeline change; new blind claims need new sealed trials.
- Don't claim uniqueness over other systems without examining them. Compare concrete properties.
- Protocol PDFs are not redistributed or quoted at length. Blind and holdout results are shown only as locked and unsealed.
- Don't claim causal validity, exchangeability or replacement of randomized controls.
- Don't claim awards or productivity gains; report only measured quantities.

## 8. Work remaining before drafting

1. **[TO COMPUTE]** A/B/C feasibility comparison stage, predeclared, run on held-out trials.
2. **[TO COMPUTE]** Wall-clock time from PDF to locked package, from the stage logs.
3. Figure and table scripts (section 6), reading only the locked artifacts.
4. Check the PHUSE paper template, the word limit and the policy on protocol quotations.
5. Presenter details, affiliation and conflict-of-interest statement.

## 9. Artifact map

| Purpose | Artifact |
| --- | --- |
| Asset scope and quality counts | data/asset_v1/manifest.json; profiles.jsonl |
| Registry SAE source (124/419) | data/raw/ctgov/NCT00091572.json → adverseEventsModule.eventGroups[EG000] |
| Evidence row / counts | data/simulation_parameters_v1/evidence_table.parquet; manifest.json |
| V3 parameter + draws | data/simulation_parameters_v3/proportions/parameter_index.jsonl; posterior_draws.parquet; parent_contributions.parquet |
| Baseline assumptions | data/simulation_parameters_v3/baseline/dependency_registry.json |
| Operational / safety assets | data/locked/planning_asset/operational_v2.2.0; data/locked/safety_asset/v3.1.0 |
| Registry-scale scorecard | data/validation/scorecard.md; scripts/validation_scorecard.py |
| Development results | data/trial/unblinded/results_record.md |
| Blind manifest, locks, unsealing | data/manifest/blind_holdout.json; data/locked/BLIND_*; data/trial/blind/BLIND_*/v*/unsealing.json |
| Blind results | data/trial/blind/blind_results.md |
| Pipeline code | clinical_asset/protocol/, clinical_asset/trial/, clinical_asset/planning/ |
