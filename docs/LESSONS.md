# Lessons learned

Generated from `data/agent/lessons.jsonl` by `clinical_asset.agent.lessons` on 2026-09-29. Each lesson has a regression check; the agent loop runs them before accepting any change.

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
- **Check:** `chk_no_vocabulary_in_code` — 1 passed in 1.35s
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
