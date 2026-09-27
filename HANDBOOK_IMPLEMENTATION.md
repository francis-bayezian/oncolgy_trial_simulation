# Clinical Evidence Asset v1: implementation status

The supplied Developer Handbook defines evidence for future oncology patient modelling. A clinically useful output must preserve the treatment, phenotype, population, denominator, endpoint and timepoint of every reported fact. It must never infer how a demographic group responds from an overall treatment result.

## Current local workflow

`clinical-asset extract NCT_ID` retrieves one eligible ClinicalTrials.gov study and its linked result publications, extracts conservative registry facts and writes a local JSON report. The eligibility gate requires an interventional oncology study that is completed and has posted results. The runnable CLI contains no Neon command. There is no review-status field in the JSON or active schema code.

The base unit is a treatment group. A second profile is created only for a source-defined clinical or demographic subgroup with its own treatment-linked outcome. Baseline, full analysis set and safety population descriptions qualify measurements but do not create profiles. A reported crossover group, such as patients switched from the comparator to the experimental drug, becomes its own treatment group. The parser structures eligibility limits, normalised drug names and regimens, baseline demographic counts, outcome measures and comparisons with their assessment method, selected serious and common adverse-event terms, per-group death counts and treatment switches. Every fact carries its analysis population. Disagreements between registry modules are listed as source conflicts rather than resolved silently. Unsupported population descriptions and impossible event counts are excluded from clinical facts and retained in parser audit information.

The JSON separates evidence from missing relationships. It can report an arm-level PFS median and serious adverse-event frequency without claiming an individual trajectory, a treatment-caused death or an age-specific response. The linked article identifier is recorded, but publication findings are not promoted into clinical facts until source-priority, arm, population, timepoint and duplicate reconciliation are implemented. The original source order remains structured registry results, linked full text, accessible supplements, then abstract.

## Questions and evidence requirements

| Intended question | Minimum evidence before a claim is made |
| --- | --- |
| Which patients should exist? | Explicit disease, histology, stage or setting, biomarkers, prior therapy and subgroup definitions from source wording. |
| What are realistic baseline characteristics? | Reported distributions with arm, population, units and denominators. |
| How are characteristics correlated? | Reported joint distributions, cross-tabulations or participant-level data. Marginal summaries are insufficient. |
| How do patients respond? | Treatment-linked response endpoints in the appropriate overall or reported subgroup population. |
| How do biomarkers, laboratories and tumour burden change? | Paired time-indexed measurements for the stated population and treatment. |
| Who develops toxicity? | Event type, severity, causality when reported, treatment, denominator and time frame. |
| Who interrupts, reduces or stops treatment? | Explicit treatment-change events, distinct from study withdrawal. |
| Who progresses? | Reported progression counts, time-to-event data or subgroup relationships. Median PFS alone is insufficient for individual progression. |
| What are PFS and OS trajectories? | Survival estimates over time, Kaplan-Meier data or participant-level time-to-event records. A single median does not define a curve. |

## Remaining work before clinical acceptance

The local extractor does not yet enumerate all oncology trials, integrate article facts, parse supplements, select clinically meaningful term-level adverse events, extract longitudinal observations, or validate patient-level dependence. NCT04303780 has only age, sex, ethnicity and race as posted baseline measures and PFS as its posted registry outcome. The [source-fidelity review](docs/CLINICAL_REVIEW_NCT04303780.md) records what can be supported from that trial and what cannot.

The handbook calls for 20-study engineering, 100-study architecture and 250 to 500 study expert-reviewed evaluation stages, with numerical accuracy, treatment and population attribution, relationship precision and recall, clinical noise and duplication checks. These gates remain outstanding. A locally generated JSON file is a candidate for validation, not a claim that every one of the nine questions has been answered.

The old pipeline removal is recorded in [REMOVAL_MANIFEST.md](REMOVAL_MANIFEST.md). `.env` and user-generated `data/` were preserved. The project owner has asked that Neon remain empty during local testing; no current CLI action writes to it. The local scispaCy UMLS 2022AB linker and optional NLP modules remain available for later validated publication extraction.

## Normalisation without hard-coded medical vocabulary

The pipeline code contains no drug, disease, gene, biomarker or adverse-event names. A test fails if any are added. Identities come from the trial's own sources and UMLS:

| Need | Source |
| --- | --- |
| Drug identity | Registry MeSH intervention mapping and the registry's own alias wording, such as "proposed INN" |
| Disease, gene, variant, events, endpoints | UMLS 2022AB concepts, selected by semantic-type code |
| Drug class and target | Quoted by GPT-5.6 Luna from the UMLS definition and checked against it |
| Eligibility criteria | Quoted by GPT-5.6 Luna, then normalised through UMLS; unmatched criteria keep their source wording |
| Unresolved abstract sentences | GPT-5.6 Luna with quote, arm and denominator validation |

Reporting grammar such as "n=.. [..%] vs", hazard ratios, CTCAE grade wording, RECIST and analysis-population labels is generic and remains rule-based.

## Speed

Run `clinical-asset build-index` once. It builds a 1.3 GB SQLite index of UMLS aliases in about 3 minutes. Exact alias lookup then takes milliseconds. The slow scispaCy fuzzy linker, which takes about 3 minutes to load, and the scispaCy NER models, which take about 40 seconds, are optional through `--fuzzy` and `--ner-models`. Model calls run in parallel and are cached.

| Run of NCT04303780 | Wall time |
| --- | ---: |
| New trial, including GPT-5.6 Luna calls | about 33 s |
| Rerun with cached model answers | about 14 s |

## Database build and test holdout

The database covers completed interventional oncology trials with posted results, primary purpose treatment, Phase 2 or 3, and a registry-marked result publication. That was 1,047 trials on 26 September 2026. The list is in `data/manifest/subset_treatment_phase23_result_pub.json`.

The test holdout is in `data/manifest/holdout_test_trials.json`. It holds 28 trials: the 20 most recent by results-first-posted date, which include every 2026 posting, plus 8 trials whose completion date is in 2026. The build refuses these trials, and the database loader refuses them even if their JSON exists.

`clinical-asset build-database` processes the remaining 1,019 trials in parallel. It resumes after interruption and logs failures to `data/build/failures.jsonl` without stopping. It then loads every clinical profile into `data/clinical_asset.sqlite`, table `clinical_evidence_profile`. The indexed columns follow handbook section 32 and the clinical sections are stored as JSON. Nothing is written to Neon.

Result groups are matched to protocol arms by exact label, then by normalised label, by a drug that only one arm received, by the single placebo arm, and by close label overlap. A group that still has no arm becomes its own `result_group` profile, never a merge. So does a second group in the same module that maps to an already-matched arm. Its treatment is the drugs named in its title, and a placebo group's treatment is placebo.

## Asset v1.0.0

Built on 26 September 2026 with `clinical-asset release --version 1.0.0` into `data/asset_v1/`. It contains 1,000 trials and 2,771 clinical profiles. The 28 holdout trials and 19 non-oncology trials are excluded and listed in `manifest.json`.

| File | Contents |
| --- | --- |
| `profiles.jsonl` | Cleaned profiles in the frozen v1 schema. Every profile has a stable `profile_id` |
| `schema/clinical_profile.schema.json` | The frozen schema. All profiles validate against it |
| `vocabularies/*.json` | Canonical vocabularies built from the corpus: cancers, drugs, regimens, biomarkers, outcomes, toxicities, treatment-course reasons, units and statistics |
| `asset.sqlite` | Indexed lookup tables: `profile`, `observation`, `toxicity_event`, `comparison` and `vocabulary`, with internal `qa_issue`, `repair_log` and `metadata` tables kept separate |
| `parquet/*.parquet` | Analytical exports of the lookup tables |
| `manifest.json` | Version, scope, counts, holdout and exclusion lists, QA summary and SHA-256 checksums |

Every efficacy outcome is a list of observations. Each observation keeps its own statistic, unit, rate, N, category, interval type (CI, IQR or range, never relabelled), population, time frame and source. Registry categories and classes stay separate, with no `_1`/`_2` keys. Safety-titled outcomes sit under `toxicity.registry_safety_outcomes`. Pharmacokinetic measures are recorded in the audit and left out of the asset. Each observation row in the lookup layer carries an `evidence_level` of marginal or subgroup for the synthesis layer.

Quality gates at release:

| Gate | Result |
| --- | --- |
| Trials with integrity errors | 0 of 1,000 |
| Schema validation errors | 0 |
| Registry outcome values traced to the raw record | 15,998 of 15,998 |
| Registry denominators traced | 15,998 of 15,998 |
| Adverse-event counts traced | 55,584 of 55,584 |
| Registry comparisons traced | 1,040 of 1,040 |

160 flagged warnings remain in `qa_issue`: outcome N above the arm's n without a stated population, intervals of unspecified type, and terms whose at-risk count equals the affected count.

Known limitations of v1:

- Only 2 biomarker variants are structured, because condition text rarely states a variant in gene-variant form.
- 15% of observations carry an outcome UMLS concept. The rest use cleaned outcome phrases, so near-synonyms such as objective and overall response rate remain separate keys.
- Publication facts reach 169 trials.
- 1,177 profiles are result groups that could not be tied to a protocol arm.

## Simulation Parameter Asset V1, milestone 1

`clinical-asset build-parameters` reads the frozen Asset V1 and refuses to run if the checksum of `profiles.jsonl` differs from its manifest. It writes `data/simulation_parameters_v1/`. The Asset V1 files are read-only and are never modified.

| File | Contents |
| --- | --- |
| `evidence_table.parquet` | Layer B: 106,185 statistical observations with inherited clinical context, canonical variable, statistic family, timepoint, evidence type and a scientific observation ID after deduplication |
| `canonical_outcome_dictionary.parquet` | Every raw measure name with its canonical variable, domain and mapping method |
| `parameter_index.parquet` / `.jsonl` | One record per clinical context, variable and model: posterior and predictive summaries, heterogeneity, support, evidence level, evidence type and validation |
| `posterior_draws/*.parquet` | 1,000 draws per parameter for evidence levels A and B, one file per model family |
| `parameter_sources.parquet` | Parameter to scientific-observation and profile provenance |
| `validation_report.json`, `manifest.json` | Diagnostics, calibration and build metadata |

Canonicalisation uses the controlled vocabulary in `clinical_asset/spa/canonical_outcomes.json`. Rules run first. GPT-5.6 Luna labels the remaining measure names, and only mappings at confidence 0.8 or above are accepted; it never supplies values. Safeguards: a death count or rate is never read as a survival probability, safety wording never becomes efficacy, and distinct survival endpoints are never merged.

Models are exact Bayesian posteriors computed on grids, with importance sampling for categories:

- hierarchical beta-binomial for proportions
- normal random effects for continuous means and log hazard, odds and risk ratios
- hierarchical Dirichlet-multinomial for mutually exclusive categories

Evidence levels are A for three or more studies, B for two, C for one (a conservative study-informed posterior) and D for no usable observation, published as NO_RELIABLE_PARAMETER. Fits failing a diagnostic (grid boundary mass above 1% or importance effective sample size below 200) are not published.

| Result at build | Value |
| --- | --- |
| Published parameters, levels A / B / C | 338 / 578 / 51,053 |
| NO_RELIABLE_PARAMETER | 1,571 |
| Withheld for failed diagnostics | 64 |
| Leave-one-study-out 95% coverage | 96.3% over 958 held-out observations |
| Posterior predictive 95% coverage, level A | 99.5% |

Not yet modelled, and left for later stages: median survival and time-to-event summaries (3,386 observations, survival stage), 6,222 observations of non-canonical outcomes, mean and risk differences, longitudinal trajectories, subgroup modifiers, dependency and copula layers. Most contexts are single-study because exact regimens rarely repeat across trials. Treatment-class and disease-hierarchy borrowing is the next step that would move them to levels A and B.

## Simulation Parameter Asset V2, milestone 2

`clinical-asset build-parameters-v2` writes `data/simulation_parameters_v2/`. It reads the frozen Clinical Evidence Asset V1 and the frozen Parameter Asset V1 evidence table; both are read-only. The build runs in stages: borrowing, toxicity and survival. A stage can be rerun alone, and a stage that is not rerun keeps its stored results.

**Borrowing (2A).** Diseases map to 26 disease families and interventions to 46 drug classes and 12 modalities, using controlled vocabularies in `clinical_asset/spa2/taxonomy.json`. GPT-5.6 Luna assigns labels using UMLS definitions; code names and regimen strings stay "other" and add no borrowing. `hierarchy_rules.json` sets the ordered hierarchy levels and the heterogeneity prior scale for each target group. Each target is fitted as one nested Gaussian tree: logit scale for proportions, years for age, log scale for ratios. Upward and downward passes are exact given the level heterogeneities, and those heterogeneities have a posterior from adaptive importance sampling.

Every parameter separates its within-study posterior (exact, Jeffreys prior), its hierarchical posterior and a future-study predictive. The future-study predictive uses heterogeneity estimated across the target hierarchy, so a single-study parameter never claims to estimate its own heterogeneity. Each parameter also records its shrinkage. There are 4,243 parameters over 498 targets. The 144 parameters in 3 targets whose heterogeneity sampling stayed below an effective sample of 100 are withheld.

**Toxicity (2C).** Event evidence is rebuilt from each study's full registry tables, 299,914 arm-term observations over 95,716 event, seriousness and class contexts. A non-serious event that a study did not list contributes a left-censored term, Y at most the study's threshold times N; all 994 studies state a threshold. An unlisted serious event is an exact zero. Censored beta-binomial fits are made at treatment-class level, and regimen estimates borrow from them. On held-out arms that did not list an event, the censored model gives a mean 80% probability to staying below the threshold, against 45% for a model of listed rates only; listed arms are predicted equally well by both. 186 contexts that failed the grid diagnostic are withheld.

**Survival (2B).** All 3,386 deferred time observations are classified: 2,644 used, 374 with a non-canonical endpoint, 227 follow-up times and 141 mean times. 2,021 contexts get Weibull, log-normal, log-logistic and Gompertz fits to their medians and landmark survival probabilities. Families are model-averaged where there are at least three distinct times, and weighted equally otherwise. The shape is borrowed from 140 empirical priors by endpoint and disease family. Between-study heterogeneity, 0.46 on the log-median scale, is estimated from 89 pairs of studies in the same context. Identifiability is 28 HIGH, 522 MEDIUM and 1,471 LOW, and 142 contexts are withheld for grid diagnostics. Hazard ratios remain separate relative evidence.

**Validation.** Metrics are coverage at 50% and 95%, interval width, absolute error, CRPS, log predictive density and Brier score, reported by evidence level and by family in `validation/`.

| Check | 95% coverage | Mean CRPS |
| --- | ---: | ---: |
| Proportions, hierarchical, 312 held-out studies | 91.7% | 0.124 |
| Same, global pooled-rate baseline | 37.2% | 0.210 |
| Proportions with leaf evidence, hierarchical, 161 held-out | 88.2% | 0.105 |
| Same, leaf-only beta-binomial | 95.7% | 0.115 |
| Age, 120 held-out | 93.3% | 5.7 years |
| Log ratios, 56 held-out | 92.9% | 0.233 |
| Survival, 300 held-out constraints | 97.0% | 0.287 |

Known limitations:

- Hierarchical proportions are slightly overconfident, at 92% against 95%. The normal approximation to the binomial on the logit scale is the likely cause.
- The age predictive is wide because trials within a disease mix children and adults.
- Asset V1 labels every baseline age as years. Four trials report days or months (NCT00311584, NCT00372593, NCT01056341, NCT01290484). Milestone 2 converts them from the raw registry records; the Milestone 1 age parameters for those trials are wrong.
- Survival curves are mostly LOW identifiability, because most contexts report a median only.

## Simulation Parameter Asset V3, milestone 3

`clinical-asset build-parameters-v3` writes `data/simulation_parameters_v3/`; `--resume` reuses stored 3A fits after a later-stage failure. Parameter Asset V2 is now frozen read-only, and V3 reads it for survival curves, hazard-ratio posteriors and toxicity. V2 toxicity is retained unchanged and referenced by checksum in the V3 manifest.

**Exact binomial proportions (3A).** Efficacy, safety, sex, race and ethnicity proportions use the exact binomial likelihood at the arm level, in place of V2's Gaussian approximation on the empirical logit. The tree is solved by expectation propagation with quadrature, started from a Laplace fit; against brute-force integration it agrees to about 0.001 in log marginal likelihood. The level heterogeneities are sampled by adaptive importance sampling on log tau, with a defensive prior component. Each of the 4,693 parameters publishes a population posterior, a future-study predictive, a within-study posterior and its parent contribution (the share of its precision borrowed from each level above). None is withheld. Normal and Student-t new-study tails were compared by leave-one-study-out log predictive density: Student-t with 7 degrees of freedom was chosen for efficacy and sex, normal for safety.

Calibration uses the randomized probability integral transform, which is exact for count outcomes; plain interval coverage counts ties as covered and is inflated for small arms. The results are in `validation/proportion_calibration.json`.

| 312 held-out studies | 95% coverage | 50% coverage | Mean CRPS |
| --- | ---: | ---: | ---: |
| Milestone 3, all groups | 95.2% | 62.2% | 0.114 |
| Milestone 2, all groups | 90.1% | 54.8% | 0.111 |
| Global pooled rate | 34.6% | 11.2% | 0.193 |
| Milestone 3, efficacy and safety only | 94.3% | 57.3% | 0.136 |
| Milestone 2, efficacy and safety only | 90.1% | 50.0% | 0.135 |

Sex predictions are slightly wide in the centre, with 70% coverage at 50%; the user reviewed this and accepted it on 2026-09-27, so the 50% coverage and CRPS acceptance checks are judged on efficacy and safety. Rare events (below 5%) now reach 95% coverage, against 90% in Milestone 2.

**Survival fusion (3B).** The 336 V2 hazard-ratio contexts are linked to absolute survival curves draw by draw:

- 145 use Route A: both arm curves come from absolute data, and the hazard ratio only validates them.
- 6 use Route B: the treatment curve is S1 = S0^HR, flagged assumption-based.
- 185 have no absolute comparator curve and are marked ABSOLUTE_BASELINE_REQUIRED; no curve is produced.

Each curve carries S, H and h on a monthly grid to 60 months, the median, survival at 6, 12 and 24 months and RMST at 24 and 60 months. Proportional-hazards support is INCONCLUSIVE for all Route A contexts, because most curves rest on a single median. Predicting the treatment arm's reported medians and landmarks from S0^HR gives 95% coverage on 355 values; this checks fusion consistency, since the HR includes the same trial.

**Baseline generator (3C, 3D).** Age is modelled as a latent normal whose truncation to each trial's eligibility range reproduces the reported mean and SD. The top level of the age hierarchy is the population class (PEDIATRIC, AYA, ADULT, MIXED), taken from the eligibility age range. Sex is one binomial tree; race and ethnicity are stick-breaking binomial trees, with category sets taken from the data. The dependency registry keeps baseline-to-baseline pairs separate from predictor-to-outcome evidence. No source reports within-patient correlations, so all six pairs are PRIOR_DOMINATED at zero and the copula is the identity. Arm-level associations are recorded as ecological and are not used.

`generate_baseline_population(protocol, n_patients, posterior_draw=None)` takes a `ProtocolQuery` (disease, disease family, setting, age range, sex, allowed categories). Expected-world mode uses posterior expectations; with a posterior draw, trial-level parameters are drawn once per trial, with a new-study deviation. Eligibility is applied by direct conditional sampling. Each result reports the extrapolation level (0 to 4), direct studies and patients, borrowed parent studies, effective information, and the share of the evidence population that meets the protocol; that share is flagged PROTOCOL_OUTSIDE_EVIDENCE below 0.1%.

Backtests on 80 held-out studies, each refitted without the study and regenerated from its protocol, are in `validation/baseline_backtests.json`:

| Measure | Hierarchical | Global pooling |
| --- | ---: | ---: |
| Age mean, absolute error | 5.2 years | |
| Age mean, 95% coverage | 91% | 44% |
| Age mean, CRPS | 4.0 | 5.3 |
| Age mean, median 95% width | 22 years (V2: 39) | |
| Age distribution, Wasserstein | 5.5 | 7.3 |
| Female share, 95% coverage | 95% | 31% |
| Female share, CRPS | 0.084 | 0.197 |
| Race, log score per patient | -0.22 | -0.56 |

All nine acceptance checks in `validation/acceptance.json` pass.

Known limitations:

- Race and ethnicity Brier scores are close to global pooling; the gain is in log score.
- Only 16 paediatric and 42 mixed-age arms exist, so those classes are thinly supported.
- The generator covers age, sex, race and ethnicity only; registries do not report performance status, stage or biomarkers consistently.
- Outcome parameters are not yet attached to generated patients. That is Milestone 4, which has not been started.

## Protocol compiler, milestone 4

`clinical-asset compile-protocol --protocol <pdf> [--sap <pdf>]` compiles a protocol, and optionally a separate SAP, into an executable StudySpec in `data/protocol_specs/<protocol id>/`. The code is in `clinical_asset/protocol/`. Nothing in it is specific to one protocol or disease; the no-medical-vocabulary guard test now scans every subpackage.

**Scope decisions.** The compiler reads protocol sections with GPT-5.6 Luna, one component at a time; approved by the user on 2026-09-27. Only the version in the file is compiled (for ACNS0332, Amendment #6 of 4/11/18); notes about earlier amendments are kept as provenance only. No gold-standard StudySpec exists yet, so the Milestone 4 accuracy targets are **not measured**; the report says so explicitly.

**Pipeline.**

1. Ingestion (pdfplumber): lines with positions, superscripts kept inline, repeated headers and footers removed, contents pages skipped, tables extracted as grids, and a numbered outline accepted only when it is consistent. The result is cached by file hash.
2. Section classification into controlled section types (one model call).
3. Extraction per component: metadata and arms, eligibility, randomization and strata, treatment phases and interventions, dose modifications, assessment grids, discontinuation, statistics, response criteria and scale definitions. The model returns only verbatim quotes and choices from controlled lists; logic is a flat node tree (AND, OR, NOT, IF, LEAF).
4. Normalisation: numbers, comparators, ranges, units and timing windows are parsed deterministically from the quotes. Variables are linked to UMLS only when the concept's semantic group can be a patient variable, and age and sex are canonical keys. Every quote is verified against the PDF with page provenance.
5. Independent verification: each compiled item is rendered in plain language and judged by a separate model call against the protocol text, with its related items (other criteria, alternative agents, rules for the same agent) as context. Anything not judged FAITHFUL becomes REVIEW_REQUIRED with the problem quoted.
6. Validation: structure, cross-references, executability on synthetic patients, and completeness checks.

**Rule language.** Leaves are compare (with optional multiple of a reference such as ULN), range with strict or inclusive bounds, category, flag, table lookup and timing window. The evaluator is three-valued: missing data gives UNKNOWN, never pass or fail, and a rule that is not EXECUTABLE is never evaluated.

**Outputs.**

| File | Content |
| --- | --- |
| studyspec.json | the executable specification, with provenance ids |
| audit.json | every quote with document hash, page, section, verification and compiler version |
| review_required.json | every unresolved, unverified or not-faithful item |
| validation_report.json | checks and summary |
| studyspec_review.md | plain-language review report for a clinician |
| extraction_raw.json | raw model outputs |

**ACNS0332 result** (96 pages, 70 model calls, fully reproducible from cache):

| Component | Compiled | Executable and verified |
| --- | ---: | ---: |
| Eligibility criteria (patient-level) | 20 | 15 |
| Eligibility notes, restrictions, administrative | 21 | not executable by design |
| Strata | 3 | 3 |
| Treatment phases | 4 | 1 |
| Interventions | 18 | 7 |
| Dose-modification rules | 26 | 15 |
| Rule leaves | 123 | 119 |
| Quotes | 1,748 | 1,738 found in the PDF |

Arms (A and B open, C and D closed), the primary endpoint (event-free survival with its events), the stratified one-sided log-rank analysis, sample-size targets, interim rules with their status in this version, and the 10-year off-study limit are all compiled. 49 items are REVIEW_REQUIRED and listed with reasons.

Known limitations:

- No gold standard exists, so precision and recall are unmeasured. The review report is the starting point for building one.
- The rule language cannot yet express calendar logic ("the following business day", "on any Friday ... Friday to Sunday") or dose-dependent alternatives by route. These stay REVIEW_REQUIRED.
- Some extraction errors remain, for example 31 radiation fractions attributed to craniospinal irradiation alone. The verifier catches them, but they are not corrected automatically.
- The verifier is a model and is not fully deterministic: it has judged two identical items differently. A second independent vote would reduce this.
- Only one protocol has been compiled. Generality will be tested on the protocols the user adds.

## Protocol compiler 1.1

Compiler 1.1 (`protocol-compiler-1.1.0`, StudySpec `spec_version` 1.1.0) extends the rule language and adds static semantics. The use case is a sponsor checking a draft protocol for feasibility. The protocol PDF is the only input: no registry and no human approval step. Every fact is either resolved from the PDF automatically or left marked as unresolved; nothing is assumed.

**What the IR can now express** (`ir.py`, `schemas.py`, `normalise.py`):

- **Modality** of every requirement: REQUIRED, PROHIBITED, RECOMMENDED, STRONGLY_RECOMMENDED, OPTIONAL. Permissive wording compiled as REQUIRED is a static error.
- **Event-relative timing:** a typed relation to a canonical anchor event (before, after, within, on a cycle day), with strict or inclusive bounds. It also records calendar adjustments (next business day, days of the week).
- **Treatment:**
  - interventions with route alternatives and their durations
  - linked events such as premedication and hydration
  - schedule rules and minimum durations
  - interventions that are alternatives to each other
  - stop conditions
- **Radiotherapy:** courses and targets, with dose per fraction, fraction counts and conditional boosts.
- **Dose modification as workflows:** a trigger followed by ordered steps, such as hold, reduce, resume at a level or discontinue. "Until symptoms resolve" compiles as the trigger flags becoming absent.
- **Treatment event states** (DUE, GIVEN, HELD, and so on) and event counts, which the simulator owns under the `event:`, `count:`, `timing:` and `calendar:` prefixes.
- **Grade definitions** stated by the protocol, linked to the rules that use them.
- **Endpoints** with a time origin, events and censoring. Analyses with power scenarios. Interim monitors that can be executed (Bayesian Beta prior, conditional power, alpha spending) when the PDF states their parameters.
- **Canonical values** of demographic variables. For example, "Males" and "female patients" become `male` and `female`, so rules match simulated patients.

**Separate status axes per item:**

| Axis | Values |
| --- | --- |
| semantic_status (verifier) | FAITHFUL, INCOMPLETE, INCORRECT, UNVERIFIED |
| runtime_status | EXECUTABLE_NOW, EXECUTABLE_AFTER_VARIABLE_AVAILABLE, OPTIONAL_POLICY, UNSUPPORTED_RULE_TYPE, UNRESOLVED_IN_SOURCE, NON_EXECUTABLE_INFORMATIONAL |
| static_status (`typecheck.py`) | PASS, FAIL |
| criticality | CRITICAL, IMPORTANT, INFORMATIONAL |

The summary `status` is EXECUTABLE only when an item is FAITHFUL, passes static checks and is executable. Any item the verifier rejected is REVIEW_REQUIRED.

**Static type checker** (`typecheck.py`) checks:

- valid units, and one dimension per variable
- that a variable is not used both numerically and categorically
- phase and linked-event references
- doses with values
- dose-rule structure
- radiotherapy arithmetic (fractions × dose per fraction, whole fractions)
- time-to-event completeness
- an allocation ratio for randomized designs
- that active monitors have their parameters

**Pipeline additions:**

- **PDF-only resolver.** Resolves the time origin, censoring and allocation ratio for each endpoint as STATED, IMPLIED_BY_TEXT (with the supporting quote) or NOT_STATED. The allocation ratio is never assumed to be 1:1.
- **Automatic repair.** Every CRITICAL item that the verifier rejected, that failed a static check or that could not be expressed is re-extracted from its own sections, with the reason attached. Up to two rounds. The normal builders rebuild it under the same id (so every quote is checked again), and it is verified again.
- **Repair guard.** A repair cannot lower the bar. A repaired item keeps the more severe of its old and new criticality until the verifier confirms the new version. This covers a repair that changes a REQUIRED rule to OPTIONAL, or recompiles it as an informational note.
- **Majority-vote verification.** Every CRITICAL item is judged by three independent verifier calls (`--verifier-votes`, default 3). An item is FAITHFUL only if at least two of the three votes say so. A majority that rejects the item but disagrees on how is reported as the most severe rejection. Without a majority (for example, when a call fails), the item is UNVERIFIED. Non-critical items keep one vote. The votes are stored with the verdict.
- **Treatment completeness pass.** The verifier judges only what was extracted, so an administration the extraction left out would never be reported. After extraction, the compiler looks for phases with no administration (no intervention and no radiotherapy course) and for agents that have dose-modification rules but no administration. If it finds any, each treatment chunk is extracted once more with those gaps named. The new results merge into the existing phases by name. A radiotherapy course is added only for a phase that had no administration, and never when an existing course has no phase. Gaps that remain are spec-level issues and fail the gate. They are no longer blamed on the dose rule, which is not at fault.
- **Day-scoped linked events.** A dependency on another event can be limited to some administrations. For example, "On Day 2, cyclophosphamide should be given at least 24 hours after CISplatin" applies to Day 2 only, not to every day of the schedule.
- **Evidence fallback for verification.** When an item's evidence quote cannot be located, the verifier receives all of the item's verified quotes instead of empty evidence.

**Gate.**

- **PASS** requires all of the following:
  - zero CRITICAL verifier failures
  - zero CRITICAL unverified items
  - zero CRITICAL static failures
  - zero CRITICAL unresolved rules
  - zero unsupported rules marked executable
  - complete primary time-to-event endpoints
  - no spec-level static issues, including treatment completeness
- **PASS_WITH_SOURCE_GAPS** means the only gaps are facts the PDF does not state.
- **FAIL** otherwise.

**ACNS0332 result** (final run, 2026-09-27):

| | |
| --- | --- |
| Critical items executable and faithful (majority vote) | 39 of 44 |
| Source gaps | EP1 and EP3: the PDF does not state the event-free survival time origin or censoring rule |
| Allocation | equal (1:1), IMPLIED_BY_TEXT ("50 each receiving XRT alone or XRT+CBDCA") |
| Interventions | 12, of which 7 were recovered by the completeness pass after the first extraction missed them |
| Rule leaves | 173 of 178 executable |
| Quotes | 2,443 of 2,447 found in the PDF |
| Repaired automatically | 12 items |
| Gate | **FAIL** |

How the votes split on critical items: 35 unanimous FAITHFUL; 5 FAITHFUL with one dissent (accepted by majority, whereas a single vote would have failed them at random); 3 unanimous INCORRECT; 1 split rejection.

The gate fails on genuine extraction errors, each confirmed by the verifier majority and not fixed by two automatic repair rounds:

| Item | Error |
| --- | --- |
| EL022 | A permitted waiver of CSF cytology compiled as an eligibility condition |
| PH3 | Maintenance duration rendered as "4 consecutive" without the unit (weeks) |
| TX010 | The carboplatin no-makeup-dose rule compiled without its condition (radiation omitted because of sedation or technical issues) |
| RT1.T4 | The 3.6 Gy diffuse-disease spinal boost compiled as a per-fraction dose. This also causes the spec-level fraction-count mismatch (20 vs 31 fractions) |

Development history on this protocol: before voting, a single verifier call decided each item, and the gate result changed from run to run. One run showed PASS_WITH_SOURCE_GAPS only because a rejected repair had lowered an item's criticality. The repair guard fixed that. Another run's treatment extraction silently dropped seven interventions (all radiotherapy-phase chemotherapy). Nothing flagged it until the completeness pass was added.

Known limitations:

- **Extraction is not deterministic.** Two extractions of the same sections can differ. The completeness pass, the verifier majority and the repair rounds catch and fix much of this, but not all of it: four critical items remain wrong on ACNS0332.
- **Waivers are not expressible.** The rule language has no construct for "this test may be waived when ...".
- **Accuracy is unmeasured.** No gold standard exists, so precision and recall are still unknown.
- **One protocol so far.** Only one protocol has been compiled.

## End-to-end simulation of ACNS0332, milestones 5-16

On 2026-09-27 the user chose ACNS0332 (`protocols/Prot_SAP_000.pdf`) as the one protocol to run through the whole pipeline, with results locked before any comparison with the real trial. The code is in `clinical_asset/trial/`. Every stage is general; ACNS0332 is only its input.

**User decisions that shape the results**

- Inputs are our own assets and the protocol PDF only.
- The real registry results are used for nothing except the final comparison, and are read only after the predictions are locked.
- The EFS time origin, which the protocol does not state, is enrollment. Here enrollment and randomization are the same day. This is flagged in every output.
- Adverse events come from the protocol plus asset drug-class rates, flagged as adult evidence applied to children.
- The carboplatin effect is reported as a curve over the true hazard ratio, not a single value. The asset has only two EFS comparisons of a drug added to radiotherapy, and one of them has a doubtful direction; that prior is shown as insufficient evidence and not used.

**Locking.** `lock.py` copies a stage's outputs into `data/locked/<protocol>/<stage>_v<version>/` and makes them read-only. It records the SHA-256 of:

- every file;
- every input (the upstream `lock.json`, the PDF and the asset manifests);
- every source file of the code that produced them.

`verify` recomputes the checksums before any read, and a locked version is never overwritten. CLI: `lock-studyspec`, `lock-facts`, `lock-stage`.

| Stage | Lock | Content |
| --- | --- | --- |
| M4 | studyspec_v1.1.0 | StudySpec: 39/42 critical items faithful; PH2 and TX009 not executable; EP1 and EP3 source gaps |
| - | protocol_facts_v1.0.0 | 91 usable quantitative facts from the PDF |
| M5 | population_v1.1.0 | 10,000 source-population patients |
| M6 | eligibility_v1.0.0 | three-valued eligibility and feasibility bounds |
| M7-M8 | cohorts_v1.0.0 | enrolled cohorts for two accrual scenarios |
| M11 | outcomes_v1.0.0 | outcome model |
| M9-M16 | results_v1.0.0 | 36,000 simulated trials, success curve, registry-style records |
| comparison | registry_comparison_v1.0.0 | blind comparison with NCT00392327 |

StudySpec v1.0.0 and population v1.0.0 stay locked as the record of the first version. M6 exposed the error that v1.1.0 corrects: EL039 and EL040 were compiled as "female AND ...", which excluded every male (see below).

**Protocol facts** (`protocol/facts.py`, `extract-facts`). The extractor reads the statistics, design, background, objectives and enrollment sections and returns one fact per stated number: characteristic distributions, accrual, historical EFS, toxicity rates and each cell of the projected enrollment table. Each fact carries verbatim quotes and a deterministic number, which the reviewers see exactly as written ("50 of 146 (34%)"; the computed proportion is shown in brackets and is not judged). The extractor also records a qualifier (approximately, at least, less than), and a range where one is stated. Facts are verified by three votes and automatically repaired (up to two rounds).

A number stated as a bound ("less than 30%") is never sampled as a value. Result: 111 facts, 91 usable.

**Binding facts to the simulation.** M5 and M11 link facts to StudySpec variables and roles in three steps:

1. A model proposes each link.
2. Deterministic checks confirm that the variable, category or quote exists.
3. Three reviewer votes judge the link. The reviewers see the protocol section and its tables, and judge only the link.

**M5 source population** (`population.py`, `build-population`):

- **Age:** from Simulation Parameter Asset V3, in the paediatric class. "Less than 22 years" is the same population as "21 years or younger" in completed years. V3's `ProtocolQuery` gained an optional `age_class` override for this; the V3 data is unchanged.
- **Sex, race and ethnicity:** from the protocol's projected enrollment table, sampled given sex.
- **Diagnosis:** 211 of 296 medulloblastoma.
- **Residual tumour:** 34% at least 1.5 cm² (CCG-99701). This is an interval value; the evaluator was extended to judge interval data three-valued.
- **Everything else:** 40 variables (labs, metastatic stage, histology and others) are unknown for every patient.

**M6 eligibility** (`eligibility.py`). Criteria are evaluated three-valued. Enrollment rules:

- OPTIONAL and not-executable criteria are not enforced.
- Criteria on simulator-owned timing variables are procedural and satisfied by the schedule.

Feasibility is a bound: 0% of the population is proven eligible and 100% is not proven ineligible, because no source states the variables the criteria test. A plausibility check reports any criterion that excludes a whole demographic group. It found the compiler error behind StudySpec v1.1.0. A new static check (inclusion rules that pin one sex together with other conditions) and repair rule 6 (a subgroup requirement is IF subgroup THEN requirement) fixed it generally.

**M7-M8 recruitment and cohort** (`recruitment.py`):

- **Target:** the maximum accrual of 400.
- **Accrual scenarios:** 35 per year (observed as of Amendment #2) and 60 per year (projected). "50/year or less will be of concern" is a threshold, not an estimate, and is excluded.
- **Randomization:** 1:1 between the open arms A and B. No balancing method is stated, so allocation is independent.
- **Strata:** unresolved, because metastatic stage and histology are unknown.

**M11 outcome model** (`outcomes.py`, `build-outcome-model`):

- **Control EFS:** the protocol's own PCM cure model ("best represented by a PCM with long-term EFS (cure) rate of 56%, and two-year EFS of 61%"). pi = 0.56, lambda = 1.087 per year among non-cured patients.
- **Experimental arm:** S_B(t) = S_A(t)^HR. Under this model the protocol's relative failure rate equals HR (ln 0.71 / ln 0.56 = 0.591).
- **Loss to follow-up:** 1% per year (stated).
- **Off study:** at 10 years (DC11).
- **Analysis rule:** "once 280 eligible and evaluable medulloblastoma patients have been enrolled and all have been followed for at least 1 year", with about 10% excluded at central review.
- **Ototoxicity:** the protocol's historical 25-30% grade 3 was rejected by the reviewers, because the protocol monitors ototoxicity separately by arm.
- **Asset adverse events:** from the nearest drug-class combination (platinum + radiotherapy + vinca, without the alkylating agent). These are mostly adult thoracic chemoradiation trials, and both arms get the same rates.

**M9-M16 engine** (`simulate.py`, `results.py`, `run-trials`). Each replicate is a complete trial:

- arrivals, allocation and strata are drawn again from the enrollable pool;
- about 10% of subjects are not evaluable;
- accrual stops at 280 evaluable patients (311 enrolled);
- the final analysis is 1 year after the last enrollment;
- EFS, loss to follow-up and the 10-year off-study limit apply;
- the protocol's primary one-sided log-rank test runs at alpha 0.05. It is unstratified because strata are unresolved, and this is reported.

The run covers 1,000 trials for each of 18 hazard ratios and 2 scenarios. The Cox, log-rank and Kaplan-Meier implementations are tested against known truth.

**Validation against the protocol's own design**

| | Protocol states | Simulated (35/yr and 60/yr) |
| --- | --- | --- |
| Type I error | 5% | 5.0% and 6.1% (within Monte Carlo error) |
| Power, 56% -> 71% (RFR 0.591) | at least 80% | 83.3% and 82.6% |
| Power, 56% -> 73% (RFR 0.543) | at least 90% | 91.2% and 90.3% |
| Enrolled for 280 evaluable | (211+100) = 311 | 311 |
| Events at analysis | full information 110 | median 97-118 |

Two design scenarios assume a 65% control rate (the isotretinoin scenario). They are reported as not comparable.

**Success curve (M16).** Probability that the primary analysis succeeds, by true HR (35/yr scenario):

| True HR | P(success) |
| --- | --- |
| 0.50 | 0.94 |
| 0.60 | 0.79 |
| 0.70 | 0.58 |
| 0.80 | 0.34 |
| 0.90 | 0.13 |
| 1.00 | 0.05 |

**Blind comparison with the registry** (`compare.py`, `compare-registry`). The predictions were locked at 13:33:00 UTC. NCT00392327 was fetched at 13:33:29 UTC; its study id is ACNS0332, and it is stored in `data/holdout_comparison/`, outside the evidence build.

- **Control arm (Regimen A, medulloblastoma), 5-year EFS:** predicted 56.2% (90% interval 48.9-63.1), registry 57.5% (95% CI 43.6-71.4). Each value lies within the other's interval.
- **Regimen B:** registry 65.3%. This implies HR 0.77 against A, where the simulation predicts 64.6% EFS and a success probability of 0.40-0.50.
- **Baseline:**
  - Sex: 60.8% vs 63.8% male.
  - Median age: 12.1 vs 8.8 years. V3's paediatric class is older than this disease population.
  - White: 86.5% vs 72.2%. The protocol's projected table had fewer reported "unknown" (0.8% vs 10.5%).
- **Participants:** 311 simulated vs 294 medulloblastoma participants registered. Per-arm counts are not comparable, because the registered trial also ran Regimens C and D before they closed.
- **Adverse events:** 21 predicted terms matched a registry term, with a mean absolute error of 19.3 percentage points. The class-level adult evidence overstates GI and oesophageal events (vomiting 73% vs 16%, oesophagitis 40% vs 2%) and understates marrow toxicity (neutropenia 49% vs 67%, febrile neutropenia 15% vs 38%). This is the weakest part of the simulation, as flagged beforehand.
- **Unresolved endpoints:** response, overall survival and neurocognitive endpoints were declared unresolved. The comparison lists the registry values for them.

**Known limitations**

- EFS events are observed at their true time; no scheduled-assessment delay is applied.
- The maintenance phase (PH2) is not executable in the StudySpec, so completion of protocol therapy is unresolved.
- Strata, and all disease variables except diagnosis and residual tumour, are unknown.
- Only the arms open in the compiled protocol version are simulated.
- Secondary endpoints and grade 4 ototoxicity have no source.
- The effect of the experimental treatment has no usable evidence in the assets, so it is reported as a curve.

## Four-protocol blind run (2026-09-27)

The results record is [data/trial/results_record.md](data/trial/results_record.md). Engines added for these designs:

- clinical_asset/protocol/design_rules.py: decision rules with exact operating characteristics.
- clinical_asset/trial/binary.py: per-arm binary rules, and descriptive estimation when no rule is executable.
- clinical_asset/trial/escalation.py: 3+3 over a grid of hypothetical DLT truths.
- compare-registry-binary and compare-registry-unresolved in clinical_asset/trial/compare.py.

| Protocol | Trial | Design and engine | Registry result | Locked prediction | Verdict |
| --- | --- | --- | --- | --- | --- |
| ACNS0332 (NCT00392327) | Carboplatin with RT in high-risk medulloblastoma | Two-arm time-to-event comparison (log-rank, cure model) | Regimen A 5-year EFS 57.5% (95% CI 43.6-71.4); Regimen B 65.3% | Control 5-year EFS 56.2% (90% interval 48.9-63.1); effect reported as a curve | Control arm correct; the implied HR of 0.77 lies on the curve (P(success) 0.40-0.50) |
| NCT01391962 | Sunitinib vs cediranib in alveolar soft part sarcoma | Simon two-stage rule per arm and cohort | Cediranib 1/15 (6.7%); sunitinib 1/14 (7.1%) | Exact curves; conditional on the cited 4/7 (57%) cediranib response, 41-73% predicted | The rate cited in the protocol (a small early report) was far too high; the curve at about 5% (P(of interest) < 1%) matches |
| NCT01616875 | Neoadjuvant cabazitaxel + cisplatin in bladder cancer | No stated decision rule, so the rate is estimated descriptively (n = 26) | Pathological response 15/26 (57.7%) | Observed-rate distribution per true rate; no rate cited for this combination | Consistent with the protocol's 60% target; no decision to test |
| NCT01625234 | Ensartinib (X-396) phase I/II | Dose escalation (3+3) | MTD 250 mg | Unresolved: the escalation rule is not executable and dose levels are defined by increments, not listed | The primary endpoint could not be predicted from the PDF |
