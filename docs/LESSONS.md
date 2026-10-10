# Lessons learned

Generated from `data/agent/lessons.jsonl` by `clinical_asset.agent.lessons` on 2026-10-08. Each lesson has a regression check; the agent loop runs them before accepting any change.

## L001 — protocol compiler (PASS)

- **What went wrong:** a Simon stopping bound '< 8/22' was read as 22
- **General rule:** fractions in thresholds count the numerator; strict inequalities shift by one
- **Where:** `design_rules.bound`
- **Check:** `chk_threshold_fraction` — bound('< 8/22', at_most) = [7.0]; expected [7.0] (a count out of 22, not 22)
- **Recorded:** 2026-09-29 (project history)

## L002 — blind selection (PASS)

- **What went wrong:** the 'terminated for safety' category matched 'There were no safety concerns'
- **General rule:** category rules on free text must handle negation
- **Where:** `scripts/select_blind_holdouts.py SAFETY`
- **Check:** `chk_sealing_negation` — the 'terminated for safety' rule matches a negated sentence ('There were no safety concerns')
- **Recorded:** 2026-09-29 (project history)

## L003 — protocol compiler (PASS)

- **What went wrong:** a primary analysis compiled with alpha 1.0 made P(success) meaningless
- **General rule:** statistical parameters get plausibility ranges (alpha in (0, 0.5])
- **Where:** `protocol.compiler._as_fraction protocol.expressions.parse_number`
- **Check:** `chk_alpha_plausible` — all alpha / power quotes convert correctly
- **Recorded:** 2026-09-29 (project history)

## L004 — dose modification (PASS)

- **What went wrong:** grade 3 neutropenia fired the febrile-neutropenia hold rule
- **General rule:** qualifiers that change the condition (febrile) must match on both sides
- **Where:** `trial.dose_modification.term_matches`
- **Check:** `chk_febrile_distinct` — febrile_neutropenia must not match neutropenia; neutropenia must match neutrophil count decreased
- **Recorded:** 2026-09-29 (project history)

## L005 — dose modification (PASS)

- **What went wrong:** a dose-level definition ('after 1 reduction: 40 mg') fired on grade 2 anaemia
- **General rule:** state rules are checked on the patient state, never as event reactions
- **Where:** `trial.dose_modification.decide`
- **Check:** `chk_state_rules_not_ae_reactions` — a dose-level definition fired as an adverse-event reaction: no_rule
- **Recorded:** 2026-09-29 (project history)

## L006 — eligibility (PASS)

- **What went wrong:** 'adult' tested against numeric age marked all patients ineligible
- **General rule:** a category test on a numeric variable is undecidable, not false
- **Where:** `protocol.expressions.evaluate`
- **Check:** `chk_numeric_category_undecidable` — a category test on a numeric variable must be undecidable, got None
- **Recorded:** 2026-09-29 (project history)

## L007 — schedule facts (PASS)

- **What went wrong:** the model quoted 'approximately 8-week intervals' but returned no number
- **General rule:** numbers come from a deterministic parse of the verified quote, not from the model
- **Where:** `trial.schedule_facts.quote_interval`
- **Check:** `chk_quote_interval_parser` — {'every 9 weeks (63 days ± 7 days)': 63.0, 'approximately 8-week intervals': 56.0, 'every 3 cycles': 84.0, 'Q9W': 63.0}
- **Recorded:** 2026-09-29 (project history)

## L008 — validation (PASS)

- **What went wrong:** calibration and scoring needed to be shown on whole held-out trials
- **General rule:** whole trials, never rows, are split; calibrate and report on different trials
- **Where:** `scripts/build_trial_level_splits.py`
- **Check:** `chk_trial_level_splits` — fit / calibrate / report trial sets must be disjoint
- **Recorded:** 2026-09-29 (project history)

## L009 — temporal evaluation (PASS)

- **What went wrong:** the first showcase choice had results published before T0
- **General rule:** a temporal test excludes trials whose results were published before the cut-off
- **Where:** `scripts/select_showcase_trial.py, scripts/build_evidence_cutoff.py`
- **Check:** `chk_showcase_not_in_evidence` — the showcase trial NCT03859427 must be absent from every as-of-T0 evidence source ([])
- **Recorded:** 2026-09-29 (project history)

## L010 — schedule facts (PASS)

- **What went wrong:** one-time windows were rendered 'every N days' and rejected by the verifier
- **General rule:** render one-time and recurring schedule elements differently
- **Where:** `trial.schedule_facts._render`
- **Check:** `chk_schedule_one_time_render` — a one-time window rendered as recurring: 'screening window must be done within 28 days before first dose (a one-time window), for all patients'
- **Recorded:** 2026-09-29 (project history)

## L011 — code hygiene (PASS)

- **What went wrong:** new journey modules embedded clinical terms in code, breaking the vocabulary guard
- **General rule:** clinical vocabulary lives in versioned reference data (clinical_asset/reference), never in pipeline code
- **Where:** `clinical_asset/reference/clinical_vocabulary.json`
- **Check:** `chk_no_vocabulary_in_code` — 1 passed in 3.03s
- **Recorded:** 2026-09-29 (project history)

## L012 — code hygiene (PASS)

- **What went wrong:** a regex edited through a string lost its \b and gained a backspace character, silently failing
- **General rule:** edit regular expressions with the editor or raw strings; scan sources for control characters
- **Where:** `clinical_asset/*`
- **Check:** `chk_no_control_characters` — no control characters in sources
- **Recorded:** 2026-09-29 (project history)

## L013 — evidence (PASS)

- **What went wrong:** new registry corpora contained evaluated trials (e.g. BLIND_2) that evidence readers could use
- **General rule:** evaluated trials are never evidence: every reader drops them, cut-off or not
- **Where:** `clinical_asset/cutoff.py::excluded`
- **Check:** `chk_evaluated_trials_never_evidence` — every evaluated trial is excluded from evidence
- **Recorded:** 2026-09-29 (project history)

## L014 — protocol compiler (PASS)

- **What went wrong:** a PDF typeset in the Symbol font wrote '≤' as U+F0A3, so 'ECOG PS ≤ 2' compiled without a comparator
- **General rule:** map Symbol-font Private Use Area signs to Unicode before reading any comparison
- **Where:** `protocol.expressions.parse_comparator protocol.expressions.symbols`
- **Check:** `chk_symbol_font_comparators` — {'ECOG PS \uf0a3 2': '<=', '\uf0b3 18 years': '>=', '\uf03c 1.5': '<'}
- **Recorded:** 2026-09-29 (project history)

## L015 — operations (PASS)

- **What went wrong:** a safety build crashed twice ('BrokenProcessPool'): its script had no __main__ guard, so Windows workers re-ran it
- **General rule:** scripts that start process pools run their work under if __name__ == '__main__'
- **Where:** `scripts/*.py data/spa_work/*.py`
- **Check:** `chk_scripts_guard_main` — every build script guards its entry point
- **Recorded:** 2026-09-29 (project history)

## L016 — efficacy prediction (PASS)

- **What went wrong:** the showcase's response prior was a mixture of unrelated myeloma regimens (median 32%, 90% range 3-93%): no information
- **General rule:** a family-level mixture is context, not a prediction; use the protocol-cited rate of the same regimen with the asset's same-regimen heterogeneity
- **Where:** `trial.noninferiority.cited_control_prior trial.noninferiority.run`
- **Check:** `chk_family_mixture_not_prediction` — cited prior median 0.799, 90% width 0.209; family-level replacement wired: True
- **Recorded:** 2026-09-29 (project history)

## L017 — planning (PASS)

- **What went wrong:** the showcase plan read a 28-day screening window as a 28-year accrual duration, ignored 'Approximately 100 investigative sites' and the sponsor 'Amgen Inc.'
- **General rule:** a duration needs a time unit and enrolment wording; operational facts the protocol states (sites, sponsor) replace averages over historical trials
- **Where:** `planning.report.accrual_durations_years stated_site_count sponsor_class`
- **Check:** `chk_planning_reads_protocol_operations` — durations [2.0] (want [2.0]); site counts [100, None] (want [100, None]); sponsor INDUSTRY
- **Recorded:** 2026-09-29 (project history)

## L018 — patient journey (PASS)

- **What went wrong:** the showcase journey used a cross-regimen evidence median PFS of 8.7 months though the protocol cites 26.3 months for KRd: 12-month PFS 39% predicted vs 80% observed; 12 cycles completed 45% vs 67%
- **General rule:** the protocol-cited figure for the arm's own regimen comes before any cross-regimen evidence mixture (as L016, for every model input)
- **Where:** `trial.journey_evidence.cited_progression progression_model`
- **Check:** `chk_journey_prefers_cited_progression` — cited (26.3, 'F2', 'XYz'); source: protocol-cited median progression-free survival 26.3 months for XYz (fact F2), exponential
- **Recorded:** 2026-09-29 (project history)

## L019 — arm resolution (PASS)

- **What went wrong:** arm references were matched by substring: bare 'A','B','C' gave pemigatinib to standard-care arms, and 'Once-weekly' never matched 'Arm 1 (once-weekly KRd)', so the showcase journey gave no carfilzomib (0 dose holds)
- **General rule:** resolve arm references once, on whole words (label, designator, named agents); an unmatched reference applies to no arm and is reported
- **Where:** `trial.arms.ArmResolver (safety, journey, visits, journey_evidence)`
- **Check:** `chk_arm_designators_resolve` — {'A': ['ARM1'], 'B': ['ARM2'], 'C': ['ARM4'], 'Arm 5 (once-weekly XY 56 mg/m2)': ['ARM5']}
- **Recorded:** 2026-10-05 (project history)

## L020 — patient generation (PASS)

- **What went wrong:** with no age limit the generator used the MIXED age class, which dropped the disease family: urothelial patients had mean age 38 (real 57-84)
- **General rule:** an unknown value is not a category: mix the age classes of the family's studies
- **Where:** `trial.population.age_class_mixture`
- **Check:** `chk_unknown_age_class_not_mixed` — [('ADULT', 1.0)]
- **Recorded:** 2026-10-05 (project history)

## L021 — patient journey (PASS)

- **What went wrong:** the journey had no adverse-event discontinuation or death (0 deaths vs 47 reported)
- **General rule:** use the registry participant flow for every exit reason it reports: withdrawal, adverse event, death
- **Where:** `trial.journey_evidence.disposition_probability trial.journey.simulate_patient`
- **Check:** `chk_journey_registry_exits` — journey draws registry adverse-event discontinuation and death
- **Recorded:** 2026-10-05 (project history)

## L022 — efficacy prediction (PASS)

- **What went wrong:** a neoadjuvant chemotherapy arm got a response prior pooled from metastatic regimens of other classes (family level)
- **General rule:** L016 applies to every engine: a family-level mixture is context, never the arm's prediction
- **Where:** `trial.binary.evidence_prior`
- **Check:** `chk_family_prior_is_context_in_binary` — binary evidence prior marks a family-level mixture as context
- **Recorded:** 2026-10-05 (project history)

## L023 — efficacy prediction (PASS)

- **What went wrong:** a cited 4/7 response (57%) was used as a point rate; the trial observed 7%
- **General rule:** a cited rate carries its own count: report its interval and flag small samples
- **Where:** `trial.binary.cited_uncertainty`
- **Check:** `chk_cited_count_uncertainty` — 4/7: 90% 0.28-0.83, small sample True
- **Recorded:** 2026-10-05 (project history)

## L024 — planning (PASS)

- **What went wrong:** the operational-risk headline was P(enrolment complete) 1.0 under the protocol's 124/year, 12x the historical median; the trial enrolled 7
- **General rule:** the historical model is the headline; a protocol assumption outside the historical range is flagged
- **Where:** `planning.report._risk`
- **Check:** `chk_risk_headline_historical` — ['p_enrollment_complete_by (historical model, headline)', "p_enrollment_complete_by (s, conditional on the protocol's assumption)", 'protocol_accrual_assumption_outside_history']
- **Recorded:** 2026-10-05 (project history)

## L025 — critic (PASS)

- **What went wrong:** planning unit errors (36-month accrual read as 36 years) and arm-resolution failures were found by hand
- **General rule:** every defect class found by hand becomes an automatic critic check
- **Where:** `agent.critic.check_planning check_arms`
- **Check:** `chk_critic_checks_planning_and_arms` — critic reviews planning units and arm resolution
- **Recorded:** 2026-10-05 (project history)

## L026 — eligibility (PASS)

- **What went wrong:** 0 of 10,000 patients were ever proven eligible in nine protocols: generated patients carry no labs or history
- **General rule:** every patient is decided: criteria the patients cannot answer are calibrated to the registry screen pass rate
- **Where:** `trial.eligibility.resolve_unknowns`
- **Check:** `chk_no_undetermined_patients` — {'ELIGIBLE': 88, 'UNDETERMINED': 0, 'INELIGIBLE': 112}
- **Recorded:** 2026-10-05 (project history)

## L027 — results (PASS)

- **What went wrong:** secondary endpoints, unmodelled binary endpoints and families without evidence were left UNRESOLVED
- **General rule:** one source ladder for every endpoint (protocol-cited > regimen > class > family > all oncology > design hypothesis), results from the simulated patients
- **Where:** `trial.quantify trial.endpoints`
- **Check:** `chk_every_endpoint_classified` — {'Progression-free survival': 'progression_free_survival', 'Overall survival': 'overall_survival', 'Objective response rate': 'objective_response_rate', 'Duration of response': 'duration_of_response', 'Incidence of SAEs': None, 'Quality of Life': 'patient_reported_outcome'}
- **Recorded:** 2026-10-05 (project history)

## L028 — protocol compiler (PASS)

- **What went wrong:** IMPORTANT items the verifiers judged INCORRECT (dose rules, arm-specific interventions) were never repaired, so their rules were lost
- **General rule:** repair every item judged incorrect, not only CRITICAL ones; an incorrect item is never run as compiled
- **Where:** `protocol.compiler.ProtocolCompiler.repair trial.run_forward`
- **Check:** `chk_repair_incorrect_important_items` — repair covers every failing item, whatever its criticality
- **Recorded:** 2026-10-05 (project history)

## L029 — efficacy prediction (PASS)

- **What went wrong:** a pembrolizumab-only cited response rate was taken as the rate of a pemigatinib plus pembrolizumab arm
- **General rule:** a cited figure that names agents is the arm's only when it names exactly the arm's agents
- **Where:** `trial.journey_evidence.same_regimen`
- **Check:** `chk_component_rate_is_not_regimen_rate` — component False, full regimen True, abbreviation True
- **Recorded:** 2026-10-05 (project history)

## L030 — protocol compiler (PASS)

- **What went wrong:** a new protocol extracted at 59% faithful: '296±20%' kept as a fixed 296, 'should occur' made mandatory, 'paired' Wilcoxon lost, the endpoint list's lead-in and the flush order dropped, an investigator-judged exclusion left unresolved, and analyses, sample size and discontinuation never verified
- **General rule:** restore every qualifier the verified quotes hold (deterministically), render it, verify every rule item with three votes, and loop repair until all are faithful or no progress; residual failures go to the agent backlog with a root cause
- **Where:** `protocol.qualifiers protocol.render protocol.compiler.verify repair`
- **Check:** `chk_qualifiers_restored_and_all_verified` — tolerance 20.0, modality, paired, judgement flag, three votes for every item and sample-size verification: True
- **Recorded:** 2026-10-05 (project history)

## L031 — protocol compiler (PASS)

- **What went wrong:** after round 2 of a new protocol: 'within five biological half-lives' had no unit, 'within 14 days of Visit 2' became 'after', a window anchored on its own wording, 'Approximately 60 patients will be screened' became target accrual, a safety endpoint's reporting statement was not rendered, and an item the verifiers unanimously found not to be a rule stayed 'unverified'
- **General rule:** drug-relative units and two-sided windows are kept as stated; a screened count is not enrolment; the reporting statement is rendered; NOT_A_RULE makes an item informational
- **Where:** `protocol.qualifiers.fix_window screening_count protocol.render.endpoint protocol.compiler.verify`
- **Check:** `chk_windows_screening_and_not_a_rule` — two-sided window WITHIN_EITHER, screened count planned_screened, NOT_A_RULE handled: True
- **Recorded:** 2026-10-05 (project history)

## L032 — protocol compiler (PASS)

- **What went wrong:** the L031 two-sided rule turned 'Schedule Visit 2 within 14 days of consent' into 'before or after consent'
- **General rule:** a window measured from a study-entry event (consent, enrolment, registration, randomisation, screening) can only follow it
- **Where:** `protocol.qualifiers.fix_window STUDY_ENTRY`
- **Check:** `chk_window_after_study_entry_one_sided` — of consent: WITHIN_AFTER; of a visit: WITHIN_EITHER
- **Recorded:** 2026-10-06 (project history)

## L033 — protocol compiler (PASS)

- **What went wrong:** fixing one item by recompiling the whole protocol re-extracted everything, cost hundreds of calls, re-broke items that were right, and a deterministic default overrode a direction the protocol's own schedule settled; the renderer added an internal event label ('scan visit') to the protocol's 'Visit 2'
- **General rule:** resolve only the failing items as an agentic RAG loop: retrieve passages, investigate (with more searches when needed), apply quote-backed field corrections, re-extract only when no correction is supported, re-verify only that item; never override a settled direction; render the protocol's own anchor wording
- **Where:** `protocol.resolver protocol.compiler.repair(only) protocol.render.window`
- **Check:** `chk_targeted_resolution` — unsupported patch applied: False; repair limited to targets: True; anchor rendered: "PSA occurs within 14 day before 'Visit 2'"
- **Recorded:** 2026-10-06 (project history)

## L034 — engines (PASS)

- **What went wrong:** a diagnostic imaging protocol (paired Wilcoxon on a continuous measure; PET tracers with no drug class) ran with no primary engine and safety UNRESOLVED
- **General rule:** a continuous primary with a stated design gets its own engine (SD derived from the power statement and checked by simulation); an agent with no drug class uses the protocol's cited incidences, else NO_EVIDENCE
- **Where:** `trial.continuous trial.engine_choice trial.safety.v3_arm_events`
- **Check:** `chk_continuous_engine_and_unclassified_safety` — continuous design RESOLVED, derived SD 25.152637136957445; unclassified agents use protocol-cited incidences: True
- **Recorded:** 2026-10-06 (project history)

## L035 — trial design (PASS)

- **What went wrong:** an intra-patient study (each patient receives both tracers) was simulated as two parallel arms, each tracer was given to every arm, and a 10-day imaging study was followed for 2 years with a progression model
- **General rule:** detect within-patient designs and give every patient one record per arm in the protocol's order; an unreferenced item belongs to the arm naming its product only when every arm names its own; with no cycles, participation ends after the last procedure plus the reporting window
- **Where:** `trial.recruitment.within_patient trial.arms.arms_of_item trial.journey (A22)`
- **Check:** `chk_within_patient_design` — intra-patient order ['ARM1', 'ARM2']; parallel design detected as within-patient: False
- **Recorded:** 2026-10-06 (project history)

## L036 — protocol compiler (PASS)

- **What went wrong:** renderings passed verification by echoing protocol sentences ('as stated: ...', 'listed under ...', '(protocol wording: ...)') instead of the extraction being right
- **General rule:** no verbatim: renderings show structured content only; the resolver agent writes structured values backed by a quote, and a value that copies its quote is rejected
- **Where:** `protocol.render protocol.qualifiers protocol.resolver.copies`
- **Check:** `chk_no_verbatim_echo` — endpoint rendering "secondary endpoint 'Detection rate' (binary); population 'each tracer'"; a copied sentence is rejected: True
- **Recorded:** 2026-10-06 (project history)

## L037 — reporting (PASS)

- **What went wrong:** results were drawn as rates and reported in an ad hoc layout: response was 'not simulated' in the journey, PFS was detected only while on treatment, and safety was not in the FDA standard tables
- **General rule:** derive response from simulated tumour measurements under the protocol's own thresholds (PharmaSUG: SDTM TU/TR/RS, ADaM ADRS/ADTTE with standard censoring), and report safety in the FDA standard tables
- **Where:** `trial.analysis_results scripts/build_ae_soc_map.py`
- **Check:** `chk_response_derived_from_measurements` — protocol thresholds 50.0/25.0; progression detected at the next assessment (day 168); unconfirmed PR is not a response: True
- **Recorded:** 2026-10-06 (project history)

## L038 — reporting (PASS)

- **What went wrong:** results were reported only by arm (one ORR or median for the whole trial), which says little for feasibility and control-arm questions: who is enrolled, who is excluded, and how each group does
- **General rule:** report every result by arm AND by subgroup (the protocol's stratification factors and analysis subgroups by meaning, FDA demographics, baseline disease factors): efficacy, arm-vs-control within each level with forest plots, safety, disposition and screening; every factor states whether the model gives it an effect (evidence-driven) or its levels differ only by chance (mix only), and a protocol subgroup with no patient variable is listed as not generated
- **Where:** `trial.subgroup_report trial.analysis_results`
- **Check:** `chk_results_by_subgroup` — protocol age cut points ['< 70 years', '>= 70 years']; a protocol subgroup with no patient variable is listed as not generated: True; FDA demographics present: True
- **Recorded:** 2026-10-06 (project history)

## L039 — patient generation (PASS)

- **What went wrong:** subgroup results were empty or meaningless: most factors a protocol stratifies by or names as subgroups were never generated for patients, and no patient characteristic changed outcomes within an arm, so every subgroup differed only by chance
- **General rule:** generate each protocol subgroup factor from registry baseline tables (retrieved by meaning, categories mapped to the protocol's levels by three model votes, pooled by disease family and phase; else equal shares, A27), reuse a variable that already carries it, and take prognostic effects from registry results reported by subgroup (class tables, separate measures, and the complement of a whole-population row), applied per patient and centred on the mix (A28); a factor with fewer than 3 trials of effect evidence stays 'mix only'
- **Where:** `trial.subgroup_evidence trial.baseline_extra trial.journey trial.analysis_results`
- **Check:** `chk_subgroup_evidence` — complement from a whole-population row: ('B', 0.24999999999999994); patient effects centred on the mix (mean 1.4e-17); levels from the protocol's wording
- **Recorded:** 2026-10-06 (project history)

## L040 — operations (PASS)

- **What went wrong:** after protocols were renamed by NCT, every new run stopped at the population stage: the facts lock records the PDF's old path, and locks are never edited
- **General rule:** a path a lock records is resolved through the alias manifest (data/manifest/protocol_aliases.json) when it no longer exists; the checksum still decides it is the same file
- **Where:** `trial.lock.resolve trial.population planning.report trial.safety trial.compare`
- **Check:** `chk_lock_paths_follow_renames` — a protocol path recorded before the rename resolves to protocols/NCT00392327.pdf (exists: True)
- **Recorded:** 2026-10-06 (project history)

## L041 — operations (PASS)

- **What went wrong:** the protocol batch stopped every protocol with 'protocol_facts_v1.0.0 is not a locked artefact' although the lock existed: the shell loop read the version from Windows Python output ending in CRLF, so the directory name carried a hidden carriage return
- **General rule:** a shell loop that reads values printed by Python strips the trailing carriage return before using them
- **Where:** `scripts/run_test_protocols.sh`
- **Check:** `chk_shell_loops_strip_cr` — every shell loop reading Python output strips the carriage return
- **Recorded:** 2026-10-06 (project history)

## L042 — protocol compiler (PASS)

- **What went wrong:** nine protocols were audited COMPLETE while 16-97 StudySpec items each were still flagged REVIEW_REQUIRED (verifier INCORRECT, INCOMPLETE or unverified): the audit only counted them, and those specs had been compiled before the targeted resolver existed
- **General rule:** a flagged extraction item is an audit problem; every protocol goes through resolve-protocol (only its unresolved items) before it is run, and a run is COMPLETE only when no item is flagged
- **Where:** `trial.audit protocol.resolver scripts/run_pipeline.sh`
- **Check:** `chk_review_flags_fail_the_audit` — a StudySpec item still flagged REVIEW_REQUIRED is listed as an audit problem (the run is not COMPLETE)
- **Recorded:** 2026-10-06 (project history)

## L043 — protocol compiler (PASS)

- **What went wrong:** renderings the verifiers rejected although the extraction held the facts: a dose range '12.5-50 mg' shown as a fixed 12.5 mg, 'up to 1 x 107 DC' read as 1 'x', 'Thirty minutes prior' rendered 'at least {text: Thirty}', and every endpoint labelled with the compiler's type as if the protocol stated it; the resolver also gave up after one attempt per item
- **General rule:** restore from the verified quotes: a range dose is a range, 'up to' is a maximum, a flattened power of ten is restored, word-number offsets get value and unit (equal bounds are exact); an unstated endpoint type is shown as the compiler's classification; the resolver tries a quote-backed patch and then re-extraction before an item is left; a faithful rule generated patients cannot carry is FAITHFUL_NOT_EXECUTABLE, not REVIEW_REQUIRED
- **Where:** `protocol.qualifiers protocol.render protocol.resolver protocol.compiler._finalise_status`
- **Check:** `chk_doses_offsets_and_types_render_as_stated` — range, exact word-number offset, flattened power of ten and unstated endpoint type rendered as stated: True
- **Recorded:** 2026-10-06 (project history)

## L044 — patient journey (PASS)

- **What went wrong:** QC of 100 replicates of a paired imaging study: 169 scan records ended with 'disease progression' inside a 10-day procedure window, and exits were drawn per scan record, so a participant who left for an adverse event after scan 1 still completed scan 2
- **General rule:** in a procedure-only study disease progression does not end the planned procedures; in a within-patient design exits are person-level: leaving in a period means the later periods are not started (no exposure, no adverse events, the person's death day kept)
- **Where:** `trial.journey.person_level_exits trial.journey (procedure-only exits) trial.export_clinical`
- **Check:** `chk_person_level_exits` — an exit in period 1 ends later periods (not started: left the study in period 1 (adverse event)); progression does not end a procedure-only study
- **Recorded:** 2026-10-06 (project history)

## L045 — recruitment (PASS)

- **What went wrong:** the recruitment stage enrolled at 10.8 patients/year while the planning report predicted 16.4 for the same protocol: recruitment called the accrual model without the protocol's stated site count ('10 centers'), so it averaged over other trials' site counts; and the eligibility calibration used one fixed seed, so per-criterion exclusions were identical across 100 replicates
- **General rule:** every stage that calls the accrual model passes the protocol's stated operational facts (site count, sponsor class) exactly as planning does; stochastic stages take the run's seed
- **Where:** `trial.recruitment.historical_scenario trial.eligibility.build_eligibility cli build-eligibility --seed`
- **Check:** `chk_recruitment_uses_stated_operations` — recruitment passes the protocol's stated site count and sponsor class to the accrual model; eligibility calibration is seeded per run
- **Recorded:** 2026-10-06 (project history)

## L046 — operations (PASS)

- **What went wrong:** the v2 safety build ran out of memory twice on the 5,000-trial corpus (6 workers, then 2): every event's design-matrix copy was built up front and ProcessPoolExecutor.map submitted them all at once; after the main process failed, an orphaned worker kept the chain waiting for hours without logging the failure
- **General rule:** build pool jobs lazily and submit them in bounded batches; watch the step's own log for failure as well as the chain log
- **Where:** `safety3.fit_all JOB_BATCH`
- **Check:** `chk_safety_jobs_batched` — the safety build submits event fits in bounded batches (no up-front list of design-matrix copies)
- **Recorded:** 2026-10-07 (project history)

## L063 — patient-level safety (PASS)

- **What went wrong:** simulated patients had 52% serious adverse events while the arm-level evidence estimate (and the trial) was about 39.5%: the any-serious calibration was done at arm level, then each patient's age, sex and ECOG shift (measured from the corpus-average patient, mean +0.36 to +0.44 on the logit scale) was added on top
- **General rule:** patient-level shifts keep their relative differences, but one arm-level offset is solved so that the arm's expected share with any serious event equals the arm-level evidence estimate
- **Where:** `trial.outputs.adverse_event_rows` (serious_anchor_offset)
- **Check:** the expected any-serious share after anchoring equals the arm target (recorded in trial_outputs.json adverse_event_dependence)
- **Recorded:** 2026-10-09 (NCT05722015 comparison)

## L064 — protocol burden and withdrawal (PASS)

- **What went wrong:** withdrawal was one registry probability per arm drawn on a random day, so protocol burden (visits, duration, assessments) could not change retention; only the first follow-up visit was simulated; deaths after a participant left the study were still observed
- **General rule:** the protocol's trial-level withdrawal share comes from a registry model of withdrawal on protocol burden (participation duration, visit frequency, assessment count) adjusted for phase, disease family, enrolment, start year, sponsor and randomisation; it is distributed over the visits each patient attends (per-visit hazard solved on a pilot pass); schedule scenarios move the share by the registry visit-frequency association for the change in visits per patient-month (a fixed per-visit hazard alone would overstate burden effects against the evidence); follow-up visits continue at the protocol interval until death, withdrawal or the horizon; nothing is observed after a participant leaves; protocol features mirror what registries record (assessment intervals, not dosing; the objectives-and-endpoints list, not the restated statistical endpoints)
- **Where:** `trial.withdrawal_burden`, `trial.journey.simulate_cohort`, `trial.journey.burden_withdrawal`
- **Check:** registry model coefficients and coverage in data/corpus_v2/withdrawal_burden/model.json; the simulated withdrawal share equals the predicted share
- **Recorded:** 2026-10-09

## L065 — baseline variables beyond demographics (PASS)

- **What went wrong:** simulated patients had no comorbidities, vitals or laboratory values although registry baseline tables report several; the generated laboratory values are named by variable (var:hemoglobin) while eligibility criteria name them by concept code (umls:...), so they are not yet used in screening
- **General rule:** generate a baseline variable only from at least 5 comparable trials (disease family, else all oncology), independently, with its source; anything unsupported (e.g. medications, hypertension here) stays not simulated and is reported as such
- **Where:** `trial.baseline_extra` (CONTINUOUS_EXTRA, CATEGORICAL_EXTRA)
- **Check:** baseline_extra_summary.json lists every added variable's source and every not-simulated variable with its reason
- **Recorded:** 2026-10-09

## L066 — data completeness and endpoint capture (PASS)

- **What went wrong:** evaluability was approximated by survival on study; the schedule lost the protocol's in-cycle laboratory days because the header 'Cycle Day: 1' was not recognised; survival PFS evidence used the serious-AE rung order and an 'overlapping drug classes' pool mixing later-line trials
- **General rule:** record every protocol-required visit given the patient's disease course and whether it was attended or lost to withdrawal or death (operational missingness zero unless evidence supports it); accept 'Cycle Day: N' headers; choose survival-median evidence by its own leave-one-study-out ladder, which now includes similar drug-class-set rungs
- **Where:** `trial.journey.simulate_patient` (required visits), `trial.export_clinical` (visit_schedule.csv), `trial.visits.DAY_COL`, `trial.subgroups.choose_median_ladder`
- **Check:** median ladders in data/validation/subgroup_ladder.json (median:*) with held-out errors
- **Recorded:** 2026-10-09

## L067 — disease-specific demographics (PASS)

- **What went wrong:** simulated lung-cancer patients were 52-55% women (all-cancer average) although lung trials enrol about 40%: the population stage passed only the disease family to the demographic model, so the protocol was treated as a new, unseen disease of the family and the family's large between-disease spread (logit SD 1.45) pulled every share towards one half; the lung family also holds lymphangioleiomyomatosis (almost all women), raising the family-level share to 57%
- **General rule:** the demographic query carries the protocol's mapped disease as well as its family, and each context level is resolved to the model's own node name (letter case, else the closest name of the same parent by word overlap, Jaccard at least 0.6)
- **Where:** `trial.population.protocol_query`, `spa3.protocol.query_path`
- **Check:** retrieval records show matched_level 'disease' for a protocol whose condition names a disease the model holds
- **Recorded:** 2026-10-10
