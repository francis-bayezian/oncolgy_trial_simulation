# Trial planning and feasibility status

The planning layer reads the locked StudySpec and existing simulation results. It writes a unified JSON and Markdown report to `data/trial/<trial>/planning/`. Historical data exclude the 28 registry holdouts before extraction.

## What is available

| Component | Current evidence and behavior |
| --- | --- |
| Historical accrual | 1,000 non-holdout raw registry records reviewed; 63 contain a candidate explicit recruitment period, while 937 have only a completion bound. An unadjusted benchmark is available for context. No disease and site adjusted prediction is claimed. |
| Screening | One direct screened-to-enrolled conversion, six direct screened-to-randomized conversions, one lower bound, and 992 unresolved records. No trial-specific screening model is fitted. |
| Retention | 2,008 cumulative participant-flow groups across 1,000 trials. These are completion fractions for the first or overall period, not time to dropout or endpoint evaluability. Reasons are normalized and kept with their original group. |
| Sites | Candidate rates per *listed* site are exported. Activation dates, active-site exposure, site dropout, and catchment are absent, so no site productivity model is fitted. |
| Protocol timing | When a locked protocol states an accrual rate, the report simulates the Nth Poisson arrival and gives conditional enrollment duration intervals. Rate uncertainty and activation are excluded. |
| Decision rules | Locked binary-rule results provide expected N and early-stop probability at hypothetical true response rates for each rule. They are not collapsed into one trial-wide expectation. |
| Events | The ACNS0332 report simulates 25, 50, and 110 event thresholds using its locked cure model, fixed HR=1, and the protocol's two accrual rates. These thresholds are scenario inputs, not its primary analysis rule. |
| Scenario runner | Explicit total or site-based rates, a screening conversion, target N, deadline, site underperformance, and event thresholds can be varied. Outputs are conditional on the supplied values and are included in the ACNS0332 unified report. |
| Blind planning validation | Not done. The planning code and outputs were produced after prior registry comparisons, so retrospective checks cannot be called blind. |

## Rebuild

```powershell
.\.venv-asset\Scripts\python.exe -m clinical_asset.cli build-planning-asset
.\.venv-asset\Scripts\python.exe -m clinical_asset.cli build-planning-operations
.\.venv-asset\Scripts\python.exe -m clinical_asset.cli build-planning-report --studyspec data/locked/NCT01625234/studyspec_v1.1.0 --cohorts data/locked/NCT01625234/cohorts_v1.1.0 --eligibility data/locked/NCT01625234/eligibility_v1.1.0 --out data/trial/NCT01625234/planning
.\.venv-asset\Scripts\python.exe -m clinical_asset.cli simulate-planning-scenarios --studyspec data/locked/ACNS0332/studyspec_v1.1.0 --scenarios data/trial/ACNS0332/planning/scenarios.json --outcomes data/locked/ACNS0332/outcomes_v1.0.0 --out data/trial/ACNS0332/planning/scenarios
```

The other three locked trials have been rerun in their respective planning directories. `NCT02224599.pdf` was reviewed directly and has a preliminary report with a source-cited maximum N=17. Its local StudySpec compilation failed at the model-service connection. Automatic approval review rejected an escalated call because it would send extracted protocol text to `api.openai.com` without explicit destination-specific authorization, so it cannot enter the locked planning pipeline yet. `Prot_SAP_000.pdf` is supporting material for ACNS0332, which has a compiled StudySpec.

The four compiled planning reports are sealed under `data/locked/<trial>/planning_v1.0.0/` with input and code checksums. These locks establish reproducibility of this planning run; they do not make the results a blind validation, because the earlier registry comparisons predate them.

## Required next evidence and validation

The 63 candidate recruitment periods still need a source-level audit of whole-trial versus arm or cohort windows and active-site exposure. A hierarchical accrual model should be fitted and calibrated only after that audit. Screening conversion needs more direct denominators, and retention needs endpoint-specific timing before either can support predictive screened or evaluable counts. Event maturity needs treatment-specific survival uncertainty and protocol analysis triggers for wider use. A prospective holdout sequence must lock planning predictions before fetching timeline outcomes. Until those steps pass, the reports label unsupported estimates unresolved.
