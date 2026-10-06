# Pipeline v4: one run, any protocol, nothing left undetermined

Updated 2026-10-05, from what failed on the nine test protocols: ACNS0332, NCT01391962, NCT01616875, NCT01625234, NCT02224599, NCT04003610, NCT04205799, NCT04083170 and NCT03859427. All nine are test data. The fixes are general; none is specific to one protocol. Each fix is a lesson with a regression check (L019–L029, `docs/LESSONS.md`).

## Run it

```
scripts/run_pipeline.sh <ID> <protocol.pdf> [VERSION] [SAP.pdf]   # compile + every stage + completeness audit
scripts/run_test_protocols.sh [VERSION]                           # the nine test protocols from their compiled specs
```

Every stage is locked under `data/locked/<ID>/<stage>_v<VERSION>`. The audit is in `data/trial/runs/<ID>/v<VERSION>/audit/completeness.md`. It is **COMPLETE** only when:

- all 12 stages are locked;
- every patient is ELIGIBLE or INELIGIBLE;
- no output carries an UNRESOLVED, UNDETERMINED, PENDING or ERROR status;
- the critic finds no error.

The audit exits with code 3 otherwise.

## Stages

1. **Protocol extraction.** The compiler and facts work from the PDF only. Repair now also re-extracts IMPORTANT items the verifiers judged INCORRECT (L028).
2. **Run-forward policy** (`trial/run_forward.py`). An item the verifiers flagged is handled by their verdict:
   - FAITHFUL or INCOMPLETE: it runs as compiled, with a flag.
   - INCORRECT: its logic is never used, and the item is treated as unknown.
   - An implausible alpha is re-parsed from its verified quote (L003).
3. **Patient generation.** With no age limit, ages mix the age classes of the disease family's studies. Before, the MIXED class dropped the family and gave generic ages (L020).
4. **Screening and eligibility.** Criteria are evaluated three-valued, then resolved:
   - Criteria a generated patient cannot answer are calibrated so that the eligible share equals the registry screen pass rate for the disease family and phase (L026, A16).
   - No patient stays UNDETERMINED.
   - Screen failure and patients-to-screen follow from this.
5. **Cohort.** Two changes:
   - The historical accrual model's median rate is always a scenario, and it is the headline (L024).
   - A stratum the patient data cannot decide is drawn at random among the strata, and flagged.
6. **Arms** (`trial/arms.py`, L019). One resolver serves every stage:
   - References are matched on whole words, labels and designators. A designator is matched by the agents the arm's label names.
   - An arm that names no agent is the comparator. It gets the regimen of the arms without the investigational agent: the agent given in the most arms, with ties broken by the agent the title names first (A19).
7. **Primary engine** (time-to-event, binary, non-inferiority or escalation), chosen from the StudySpec:
   - An uncompilable escalation table falls back to the standard 3+3 (A17).
   - A binary endpoint with no evidence variable uses the protocol's design rate.
8. **Safety and planning.**
   - The planning headline is the historical model; a protocol accrual assumption outside history is flagged (L024).
   - Retention comes from the registry participant flow.
   - Loss to follow-up comes from the registry when the protocol states none (A18).
9. **Patient journey.**
   - Registry exits for adverse-event discontinuation and death are added (L021, A14, A15).
   - Each arm gets its own resolved agents.
10. **Endpoint results** (`trial/endpoints.py`, L027). Every endpoint is computed from the simulated patients, and its input is labelled with the rung of one source ladder (`trial/quantify.py`):
    1. a protocol-cited figure for the arm's exact regimen (L018, L029);
    2. evidence for the same regimen, then overlapping drug classes, age group and phase;
    3. the disease family's evidence (marked weak);
    4. all oncology;
    5. the protocol's design hypothesis.

    Endpoints the patients cannot carry are listed as NOT_SIMULATED with their kind, by design: patient-reported, pharmacokinetic, biomarker, economic and physiological measures.

## How results are reported

- **Predictive results** are five percentiles: p10, p30, p50, p70 and p90 (`trial/predictive.py`).
- **Estimates** keep their 95% CI.
- **Endpoint percentiles** come from 200 replicate simulated trials.
- **Matching** of endpoints, events, arms and regimens is by meaning: endpoint classes, UMLS concepts and whole-word agent sets. It never relies on a registry's exact wording.

## Assumptions added (registered in `trial/patient_state.ASSUMPTIONS`)

| Id | Assumption |
| --- | --- |
| A14 | Treatment stops for an adverse event with the registry probability, at a uniform time. |
| A15 | Death in the study period has the registry probability and occurs at a uniform time over the horizon. |
| A16 | Criteria the patients cannot answer pass independently, calibrated to the registry screen pass rate. |
| A17 | When the escalation table cannot be compiled, the standard 3+3 is simulated. |
| A18 | The registry study-period withdrawal share is spread over 2 years. |
| A19 | An arm that names no agent is the comparator. |
