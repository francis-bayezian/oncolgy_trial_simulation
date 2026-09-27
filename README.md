# Clinical Evidence Asset v1

The new trial planning layer builds an evidence-quality accrual asset, extracts screening and retention flow, and writes unified planning reports from locked StudySpecs. Its current results and limitations are documented in [planning status](docs/PLANNING_STATUS.md).

This project extracts source-supported clinical evidence from completed interventional oncology trials with posted ClinicalTrials.gov results. Its purpose is to support later patient modelling, not to generate patients from unreported associations. The current workflow is **local only**. It does not read from or write to Neon, and it has no database initialisation or publish command.

The output groups reported facts by treatment. A demographic or clinical subgroup is added only when a source explicitly links that subgroup, treatment and outcome. Baseline and outcome analysis descriptions remain context for a measurement; they do not create extra patient groups. If the source does not establish a relationship, the JSON says so instead of estimating it.

## Run one trial locally

Use Python 3.11 and `uv` on Windows:

```powershell
uv venv --python 3.11 .venv-asset
uv pip install --python .venv-asset\Scripts\python.exe -e ".[dev]"
.\.venv-asset\Scripts\python.exe -m clinical_asset.cli extract NCT04303780
```

The result is written to `data/clinical-asset/NCT04303780.json`. Use `--output` to choose another local path. The command fetches the registry study and its result publications linked in the study record. `--skip-publications` makes a registry-only run. Neither option calls OpenAI or connects to Neon. The `.env` file is not required for this command. `discover --condition "non-small cell lung cancer" --limit 20` lists study candidates without ingesting them.

The extraction keeps compact patient phenotype, baseline demographics, reported response and survival results, serious adverse-event counts, all-cause mortality, reported treatment switches and comparative effects. Each numerical result retains its denominator and, where relevant, its time frame. A treatment-specific subgroup is included only if its outcome is explicit. For safety, all-cause deaths are never labelled treatment-caused toxicity. Study completion and withdrawal counts are not represented as treatment discontinuation.

The linked publication is recorded as a source, but article findings are not yet added to the clinical facts because arm, population, timepoint and duplicate reconciliation are incomplete. A publication reference alone does not validate a clinical relationship.

## What the evidence can answer

The JSON is organised around the nine intended questions: patient phenotype, baseline characteristics, dependence between characteristics, response, longitudinal change, toxicity, treatment changes, progression, and PFS or OS. It includes only facts actually supported by this extraction. `not_established_by_this_extraction` names questions that cannot be answered from the available structured results. For example, separate age and sex summaries do not reveal age by sex or response by sex. A median PFS does not determine an individual PFS trajectory or an OS curve.

The [NCT04303780 source-fidelity review](docs/CLINICAL_REVIEW_NCT04303780.md) compares the sample with the registry and linked trial report. The [handbook status](HANDBOOK_IMPLEMENTATION.md) records remaining work: extracting and reconciling linked article findings, clinically meaningful term-level safety, broader phenotype and longitudinal evidence, scalable trial discovery, and evaluation across diverse trials. No clinical acceptance claim is made from this one example.

Generated files under `data/`, local terminology and `.env` remain outside Git. The previous SQLite pipeline removal is recorded in [REMOVAL_MANIFEST.md](REMOVAL_MANIFEST.md). Neon publication will be designed only after the local clinical JSON is agreed and validated.
