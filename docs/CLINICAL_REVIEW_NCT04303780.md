# NCT04303780: source-fidelity review of the local extraction

Reviewed on 26 September 2026 against the live [ClinicalTrials.gov record](https://clinicaltrials.gov/study/NCT04303780?tab=results). Nothing was written to Neon or any other database. One extraction writes three local files.

| File | Contents |
| --- | --- |
| `data/clinical-asset/NCT04303780.json` | Three clinical profiles holding observed clinical facts only |
| `data/audit/NCT04303780.audit.json` | Question coverage, source conflicts, withheld values, key-event rules and publication retrieval state |
| `data/raw/ctgov/NCT04303780.json` | The unmodified registry record, including full adverse-event tables |

An automated comparison checked 229 values and structural rules in the asset against the raw registry record. Every check passed. Numeric agreement does not amount to clinical acceptance, which still needs expert review and the handbook's gold-set tests.

## Structure of each clinical profile

A clinical profile is any clinically defined group with a reported outcome or behaviour. That includes a randomised arm, a crossover sequence, and later a publication subgroup.

| Section | Meaning |
| --- | --- |
| `patient_profile` | What was observed in these patients, with its population label |
| `selection_context` | Protocol limits such as allowed ECOG and excluded brain metastases. These say where the evidence applies and are not patient distributions |
| `treatment` | The exposure actually given |
| `treatment_ontology` | Canonical drug class and target from the dictionary, kept apart from observations |
| `efficacy` | Endpoints keyed by normalised name, with population and assessment method |
| `toxicity` | Any serious adverse event plus key events. Key events are common events, serious events reaching 2% and two patients, and dictionary class-defining toxicities. Zero counts and progression recorded as adverse events are excluded |
| `mortality_observations` | Death counts, only when registry modules agree. None qualify for this trial |
| `comparisons` | Registry statistical analyses with normalised outcome and measure |

## Defects found in the previous output and corrected

| Defect | Why it mattered clinically | Correction |
| --- | --- | --- |
| The "Docetaxel, Then Switched to AMG 510" group was silently discarded | 46 patients who received sotorasib after docetaxel progression had their safety and death data lost | It is now a separate treatment group with its switch trigger and n = 46 |
| Docetaxel mortality was shown as 78/174 | Deaths after switching were reported in the switched group, so the figure understated deaths among patients randomised to docetaxel | Unreconciled death counts are withheld from the asset and recorded in the audit file |
| Baseline, efficacy and safety facts had no population label | Randomised (174), treated (151) and crossover (46) denominators were mixed without warning | Every section now carries its population and grouping basis |
| Setting was "metastatic" | Eligibility also admitted locally advanced unresectable disease | Setting now comes from the eligibility wording |
| Treatment was the code name "AMG 510" with no regimen | The treatment could not be matched to sotorasib evidence from other trials | Drug names are normalised by dictionary. Dose, route, frequency and cycle length come from the arm descriptions |
| No eligibility phenotype | The question of which patients should exist was unanswered | ECOG 0–1, prior therapy required, age at least 18 and active brain metastases excluded are now structured |
| No adverse-event terms | Toxicity profiles such as diarrhoea and transaminase rises were missing | Serious terms reaching 2% and at least 2 patients, and non-serious terms reaching 10%, in any group are included for all groups |
| Disease progression listed as a serious adverse event | "Non-small cell lung cancer" events would be modelled as treatment toxicity | Neoplasm-class events are listed separately from treatment toxicity |
| A zero-count switch row appeared under AMG 510 | Noise | Zero-count switch rows are dropped |

## Unresolved source conflict

| Randomised arm | Adverse-events module deaths | Participant-flow deaths |
| --- | ---: | ---: |
| AMG 510 | 109 | 104 |
| Docetaxel | 78, plus 17 in the switched group | 85 |

Neither reading reconciles both modules. Until this is resolved, death counts for both arms and the crossover group stay out of the clinical asset. The disputed death count is also left out of each arm's study status.

## Coverage of the nine questions from registry data alone

| Question | Status |
| --- | --- |
| Which patients should exist | Partial. Eligibility limits and KRAS p.G12C selection are structured |
| Baseline characteristics | Partial. Only age, sex, race and ethnicity are posted. ECOG, prior lines, metastatic sites and PD-L1 are absent from registry results |
| Correlations | Not available. Only marginal summaries are posted |
| Response | Not available in the registry. The linked publication reports it |
| Biomarker, laboratory and tumour change | Not available |
| Toxicity | Partial. Any-grade frequencies per treatment received, with no grade or causality |
| Interruption, reduction and discontinuation | Partial. Crossover counts and study-level withdrawal reasons only |
| Progression | Partial. Arm-level median PFS only |
| PFS and OS trajectories | Partial. PFS median and hazard ratio only. OS is not posted as a registry outcome |

The linked Lancet report is retrieved as an abstract only. Its response rate, OS, grade 3 or higher toxicity, dose modification and baseline ECOG distribution are not yet extracted. That is the largest remaining gap for this trial.

## Evidence from the linked publication abstract

The registry links one result publication, [PMID 36764316](https://pubmed.ncbi.nlm.nih.gov/36764316/). Europe PMC has no open full text for it, so only the abstract is used. A deterministic parser reads the Methods and Findings sections. Each count is accepted only if n divided by the arm's denominator reproduces the reported percentage, which also catches values assigned to the wrong arm. A trial with no linked publication or no retrievable abstract gets no publication facts.

| Fact added to the asset | Sotorasib | Docetaxel |
| --- | ---: | ---: |
| Grade 3 or higher treatment-related adverse events | 56/169 | 61/151 |
| Serious treatment-related adverse events | 18/169 | 34/151 |
| Most common grade 3 or higher treatment-related events | Diarrhoea 20, ALT increase 13, AST increase 9 | Neutropenia 13, fatigue 9, febrile neutropenia 8 |
| Median follow-up for all randomised patients | 17.7 months, IQR 16.4 to 20.1 | Same |

The abstract also adds selection context. Prior platinum chemotherapy and a PD-1 or PD-L1 inhibitor were required. Untreated or symptomatic brain metastases, another actionable driver mutation, prior docetaxel and a prior KRAS G12C inhibitor were excluded.

Median PFS, the PFS hazard ratio, randomised and treated counts, and both doses repeat registry values within rounding. They are merged as single observations supported by both sources, not counted twice. The hazard ratio keeps the registry's 0.663 and takes the abstract's more precise p-value of 0.0017.

The abstract does not report objective response rate, overall survival, dose reduction, dose interruption or discontinuation for toxicity. These appear only in the full article, which is not openly accessible through the linked record. They remain gaps rather than inferred values.
