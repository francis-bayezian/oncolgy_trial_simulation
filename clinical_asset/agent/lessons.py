"""The lessons register: every defect the project found, the general rule it taught, and an executable regression check.

A lesson is learned once and then enforced: `run_checks()` executes every lesson's check, so a change that reintroduces
an old defect fails. Checks are small, deterministic and need no registry results. A lesson whose check fails is OPEN
(a known defect not yet fixed); the improvement loop (agent.loop) works on open lessons and critic findings.

The register is data (data/agent/lessons.jsonl, append-only history); the checks are the functions below, named by
each lesson's `check`.
"""

import json
import re
from datetime import date
from pathlib import Path

REGISTER = Path("data/agent/lessons.jsonl")
LESSONS_MD = Path("docs/LESSONS.md")


# ----------------------------------------------------------------------------- checks (return (passed, detail))


def chk_threshold_fraction():
    from ..protocol.design_rules import bound
    got = bound("< 8/22", "at_most")
    return got == [7.0], f"bound('< 8/22', at_most) = {got}; expected [7.0] (a count out of 22, not 22)"


def chk_sealing_negation():
    src = Path("scripts/select_blind_holdouts.py").read_text(encoding="utf-8")
    m = re.search(r'SAFETY = .*?compile\((r"[^"]+")', src)
    rx = re.compile(eval(m.group(1)), re.I) if m else None                   # noqa: S307 - a regex literal from our own file
    negated = "The study was terminated due to a business decision. There were no safety concerns."
    has_negation_guard = bool(re.search(r"\bno safety|negat|not due to safety", src, re.I))
    return (rx is None or not rx.search(negated) or has_negation_guard,
            "the 'terminated for safety' rule matches a negated sentence ('There were no safety concerns')")


def chk_alpha_plausible():
    """The compiler's conversion of an alpha / power quote to a fraction (the path used for StudySpec analyses)."""
    from ..protocol import expressions as ex
    from ..protocol.compiler import _as_fraction
    cases = {"1-sided 0.025": 0.025, "one-sided alpha of 2.5%": 0.025, "two-sided alpha of 0.05": 0.05, "5%": 0.05,
             "2-sided significance level of 0.05": 0.05, "80% power": 0.8, "power of 0.9": 0.9}
    got = {q: _as_fraction(ex.parse_number(q), q) for q in cases}
    wrong = {q: v for q, v in got.items() if v is None or abs(v - cases[q]) > 1e-9}
    return not wrong, f"wrong conversions: {wrong}" if wrong else "all alpha / power quotes convert correctly"


def chk_febrile_distinct():
    from ..reference import vocabulary
    from ..trial.dose_modification import term_matches
    ex = vocabulary()["regression_examples"]
    ok = not term_matches(ex["qualified_term"], ex["base_term"]) and term_matches(ex["base_term"], ex["base_synonym"])
    return ok, f"{ex['qualified_term']} must not match {ex['base_term']}; {ex['base_term']} must match {ex['base_synonym']}"


def chk_state_rules_not_ae_reactions():
    from ..trial import dose_modification as dm
    rules = [{"rule_id": "X", "agent": "a", "modality": "REQUIRED", "category": "", "state_only": True, "resume": None, "quote": None,
              "action": {"type": "set_dose", "value": 40}, "trigger": {"node": "LEAF", "rule_type": "treatment_state",
                                                                         "canonical": "a_dose_reductions", "op": "==", "value": 1}}]
    from ..reference import vocabulary
    d = dm.decide(rules, "a", {"term": vocabulary()["regression_examples"]["state_rule_event"], "grade": 2}, {"reductions": 1, "held_days": 0})
    return d["action"] == "no_rule", f"a dose-level definition fired as an adverse-event reaction: {d['action']}"


def chk_numeric_category_undecidable():
    from ..protocol import expressions as ex
    leaf = {"node": "LEAF", "kind": "category", "variable": "demographic:age", "op": "in", "categories": ["adult"], "status": "EXECUTABLE"}
    v = ex.evaluate(leaf, {"demographic:age": {"value": 40.0, "unit": "year"}})
    return v is None, f"a category test on a numeric variable must be undecidable, got {v}"


def chk_quote_interval_parser():
    from ..trial.schedule_facts import quote_interval
    cases = {"every 9 weeks (63 days ± 7 days)": 63, "approximately 8-week intervals": 56, "every 3 cycles": 84, "Q9W": 63}
    got = {k: quote_interval(k, 28) for k in cases}
    return all(got[k] == v for k, v in cases.items()), f"{got}"


def chk_trial_level_splits():
    f = Path("data/validation/trial_splits.json")
    if not f.exists():
        return False, "data/validation/trial_splits.json missing"
    s = json.loads(f.read_text(encoding="utf-8"))["safety_asset_v3_1"]
    sets = [set(s["fit_trials"]), set(s["calibrate_trials"]), set(s["report_trials"])]
    return not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]), "fit / calibrate / report trial sets must be disjoint"


def chk_showcase_not_in_evidence():
    m = Path("data/manifest/evidence_cutoff_2024.json")
    if not m.exists():
        return True, "no cut-off manifest yet"
    show = json.loads(m.read_text(encoding="utf-8"))["showcase"]
    leaks = [p for p in ("data/raw/ctgov_t0",) if (Path(p) / f"{show}.json").exists()]
    return not leaks, f"the showcase trial {show} must be absent from every as-of-T0 evidence source ({leaks})"


def chk_schedule_one_time_render():
    from ..trial.schedule_facts import _render
    r = _render({"kind": "screening_window", "interval_days": 28, "time_origin": "first_dose", "applies_to_all_patients": True})
    return "every" not in r, f"a one-time window rendered as recurring: {r!r}"


def chk_evaluated_trials_never_evidence():
    from ..cutoff import evaluated_trials, excluded
    need = {p["nct_id"] for p in json.loads(Path("data/manifest/development_protocols.json").read_text(encoding="utf-8"))["protocols"]}
    show = Path("data/manifest/temporal_showcase_v2.json")
    if show.exists():
        need.add(json.loads(show.read_text(encoding="utf-8"))["chosen"]["nct_id"])
    missing = need - set(excluded()) - set(evaluated_trials())
    return not missing, f"evaluated trials readable as evidence: {sorted(missing)}" if missing else "every evaluated trial is excluded from evidence"


def chk_symbol_font_comparators():
    from ..protocol import expressions as ex
    got = {q: ex.parse_comparator(q) for q in ("ECOG PS  2", " 18 years", " 1.5")}
    return got == {"ECOG PS  2": "<=", " 18 years": ">=", " 1.5": "<"}, f"{got}"


def chk_scripts_guard_main():
    """A script that runs a build with a process pool must run it under `if __name__ == "__main__":` (Windows spawn)."""
    bad = []
    for p in list(Path("scripts").glob("*.py")) + list(Path("data/spa_work").glob("*.py")):
        src = p.read_text(encoding="utf-8")
        calls_build = re.search(r"^(?:\w+\s*=\s*)?(build|build_\w+|main)\(", src, re.M)
        if calls_build and "__name__" not in src:
            bad.append(str(p))
    return not bad, "; ".join(bad) or "every build script guards its entry point"


def chk_family_mixture_not_prediction():
    """With only a family-level match, the NI response prior comes from the protocol-cited rate of the same regimen."""
    import inspect

    import numpy as np

    from clinical_asset.trial import noninferiority as ni

    hist = {"control_rate": (0.8, "F0", "80%"), "var_log_control": 0.0016}
    c = ni.cited_control_prior(hist, np.random.default_rng(1), 5000)
    if c["status"] != "RESOLVED":
        return False, c.get("reason", "cited prior unresolved")
    wide = c["rate"]["q95"] - c["rate"]["q05"]
    wired = 'prior.get("level") == "family"' in inspect.getsource(ni.run)
    ok = abs(c["rate"]["median"] - 0.8) < 0.02 and wide < 0.3 and wired
    return ok, f"cited prior median {c['rate']['median']:.3f}, 90% width {wide:.3f}; family-level replacement wired: {wired}"


def chk_planning_reads_protocol_operations():
    """Accrual durations need a time unit and enrolment wording; stated site counts and sponsor legal forms are used."""
    from clinical_asset.planning.report import accrual_durations_years, sponsor_class, stated_site_count

    spec = {"sample_size": [{"quantity": "accrual_duration", "value": 28.0, "unit": "day", "evidence": {"text": "a screening period of up to 28 days"}},
                            {"quantity": "accrual_duration", "value": 1.0, "unit": "subjects", "evidence": {"text": "when the first 230 subjects have been randomized"}},
                            {"quantity": "accrual_duration", "value": 24.0, "unit": "months", "evidence": {"text": "enrollment is expected to take 24 months"}}],
            "metadata": {"sponsor": {"text": "Example Pharma GmbH"}}}
    d = [round(x["years"], 2) for x in accrual_durations_years(spec)]
    sites = [stated_site_count(t).get("value") for t in ("approximately 100 investigative sites", "3 sites of disease")]
    sp = sponsor_class(spec).get("value")
    ok = d == [2.0] and sites == [100, None] and sp == "INDUSTRY"
    return ok, f"durations {d} (want [2.0]); site counts {sites} (want [100, None]); sponsor {sp}"


def chk_journey_prefers_cited_progression():
    """The journey takes the protocol-cited median PFS of the arm's own regimen before a cross-regimen evidence median,
    and does not take a comparator's figure ('Rd' is not 'KRd')."""
    from clinical_asset.trial.journey_evidence import cited_progression, progression_model

    spec = {"arms": [{"arm_id": "A", "label": "Twice-weekly", "description": ""}],
            "interventions": [{"arms": ["Arm 2 (twice-weekly XYz 27 mg/m2)"]}]}
    fact = lambda fid, cat, v: {"fact_id": fid, "source": "historical_study", "canonical_variable": "progression_free_survival",  # noqa: E731
                                "value": {"value": v, "unit": "months"}, "category": {"text": cat}}
    facts = [fact("F1", "Yz", 17.6), fact("F2", "XYz", 26.3)]
    got = cited_progression(facts, spec, "A")
    src = progression_model({}, None, spec, facts, "A")["source"]
    ok = bool(got) and got[:2] == (26.3, "F2") and "protocol-cited" in src
    return ok, f"cited {got}; source: {src}"


def chk_arm_designators_resolve():
    """Bare designators resolve by the agents their arm's label names; never by substring; unmatched arms get nothing."""
    from clinical_asset.trial.arms import ArmResolver

    lab = lambda aid, t: {"arm_id": aid, "label": {"text": t}, "description": {"text": t}}  # noqa: E731
    iv = lambda agent, ref: {"category": "anticancer_drug", "canonical_agent": agent, "arms": [{"text": ref}]}  # noqa: E731
    spec = {"arms": [lab("ARM1", "Examplinib Plus Otherumab"), lab("ARM2", "Examplinib Alone"), lab("ARM3", "Standard of Care"),
                     lab("ARM4", "Drugone and Drugtwo"), lab("ARM5", "Once-weekly")],
            "interventions": [iv("examplinib", "A"), iv("otherumab", "A"), iv("examplinib", "B"), iv("drugone", "C"), iv("drugtwo", "C"),
                              iv("drugthree", "Arm 5 (once-weekly XY 56 mg/m2)")]}
    r = ArmResolver(spec)
    got = {ref: r.resolve(ref) for ref in ("A", "B", "C", "Arm 5 (once-weekly XY 56 mg/m2)")}
    want = {"A": ["ARM1"], "B": ["ARM2"], "C": ["ARM4"], "Arm 5 (once-weekly XY 56 mg/m2)": ["ARM5"]}
    return got == want, f"{got}"


def chk_unknown_age_class_not_mixed():
    """With no age limit, ages mix the age classes of the disease family's studies; MIXED is not 'unknown'."""
    from types import SimpleNamespace

    from clinical_asset.spa3.protocol import ProtocolQuery
    from clinical_asset.trial.population import age_class_mixture

    nodes = {("ADULT", "fam"): {"studies": 3}, ("ADULT",): {"studies": 10}, ("MIXED",): {"studies": 5}}
    gen = SimpleNamespace(models={"age_mean": SimpleNamespace(nodes=nodes)})
    got = age_class_mixture(gen, ProtocolQuery(disease_family="fam", age_class="MIXED"))
    return got == [("ADULT", 1.0)], f"{got}"


def chk_journey_registry_exits():
    import inspect

    from clinical_asset.trial import journey

    src = inspect.getsource(journey.run) + inspect.getsource(journey.simulate_patient)
    ok = all(w in src for w in ("ae_discontinuation_probability", "death_probability", "ae_stop_day", "death_day"))
    return ok, "journey draws registry adverse-event discontinuation and death" if ok else "journey lacks registry exits"


def chk_family_prior_is_context_in_binary():
    import inspect

    from clinical_asset.trial import binary

    ok = "CONTEXT_ONLY" in inspect.getsource(binary.evidence_prior)
    return ok, "binary evidence prior marks a family-level mixture as context" if ok else "family mixture used as the arm's prediction"


def chk_cited_count_uncertainty():
    import numpy as np

    from clinical_asset.trial.binary import cited_uncertainty

    u = cited_uncertainty({"value": {"numerator": 4, "denominator": 7}}, {"success_if_at_least": None}, np.random.default_rng(0))
    lo, hi = u["true_rate_90_from_cited_count"]
    return u["small_sample"] and lo < 0.3 and hi > 0.8, f"4/7: 90% {lo:.2f}-{hi:.2f}, small sample {u['small_sample']}"


def chk_risk_headline_historical():
    from clinical_asset.planning.report import _risk

    rep = {"accrual": {"historical_model": {"status": "RESOLVED", "p_enrollment_complete_by": {"3y": 0.2},
                                            "patients_per_year": {"median": 10.0, "q10": 2.0, "q90": 50.0}},
                       "protocol_scenarios": [{"scenario": "s", "patients_per_year": 124.0, "p_enrollment_complete_by": {"3y": 1.0}}]}}
    r = _risk(rep)
    ok = "p_enrollment_complete_by (historical model, headline)" in r and r.get("protocol_accrual_assumption_outside_history", [{}])[0].get("direction") == "optimistic"
    return ok, f"{sorted(r)}"


def chk_critic_checks_planning_and_arms():
    import inspect

    from clinical_asset.agent import critic

    src = inspect.getsource(critic.review)
    ok = "check_planning" in src and "check_arms" in src
    return ok, "critic reviews planning units and arm resolution" if ok else "critic misses planning units / arms"


def chk_no_undetermined_patients():
    from clinical_asset.trial import eligibility as el

    leaf = {"node": "LEAF", "kind": "compare", "status": "EXECUTABLE", "variable": "var:lab", "op": ">=", "value": 1}
    spec = {"eligibility": [{"criterion_id": "E1", "kind": "inclusion", "logic": leaf, "status": "EXECUTABLE", "modality": "REQUIRED"}]}
    _, s = el.assess(spec, [{"patient_id": f"P{i}"} for i in range(200)], {"value": 0.5}, seed=0)
    return s["status_counts"]["UNDETERMINED"] == 0, f"{s['status_counts']}"


def chk_every_endpoint_classified():
    from clinical_asset.trial.quantify import classify

    cases = {"Progression-free survival": "progression_free_survival", "Overall survival": "overall_survival",
             "Objective response rate": "objective_response_rate", "Duration of response": "duration_of_response",
             "Incidence of SAEs": None, "Quality of Life": "patient_reported_outcome"}
    got = {k: classify(k, None)[1] for k in cases}
    return got == cases, f"{got}"


def chk_repair_incorrect_important_items():
    import inspect

    from clinical_asset.protocol.compiler import ProtocolCompiler

    src = inspect.getsource(ProtocolCompiler.repair)
    ok = 'item.get("criticality") != "CRITICAL"' not in src and "whatever its criticality" in src
    return ok, "repair covers every failing item, whatever its criticality" if ok else "repair is limited to CRITICAL items"


def chk_component_rate_is_not_regimen_rate():
    from clinical_asset.trial.journey_evidence import same_regimen

    iv = lambda a, ref: {"category": "anticancer_drug", "canonical_agent": a, "arms": [{"text": ref}]}  # noqa: E731
    spec = {"arms": [{"arm_id": "ARM1", "label": {"text": "Examplinib Plus Otherumab"}, "description": {"text": ""}},
                     {"arm_id": "ARM2", "label": {"text": "Arm 2 (XYz twice-weekly)"}, "description": {"text": ""}}],
            "interventions": [iv("examplinib", "Examplinib Plus Otherumab"), iv("otherumab", "Examplinib Plus Otherumab"), iv("drugz", "Arm 2 (XYz twice-weekly)")]}
    got = (same_regimen("otherumab", spec, "ARM1"), same_regimen("examplinib plus otherumab", spec, "ARM1"), same_regimen("XYz", spec, "ARM2"))
    return got == (False, True, True), f"component {got[0]}, full regimen {got[1]}, abbreviation {got[2]}"


def chk_qualifiers_restored_and_all_verified():
    import inspect

    from clinical_asset.protocol import qualifiers as q
    from clinical_asset.protocol.compiler import ProtocolCompiler

    tol = q.dose_tolerance("296±20% MBq") or {}
    leaf = {"kind": "unresolved", "text": "other conditions, as judged by the investigator.", "status": "REVIEW_REQUIRED"}
    src = inspect.getsource(ProtocolCompiler.verify)
    ok = (tol.get("tolerance") == 20 and q.modality("should occur") == "RECOMMENDED" and q.design_qualifiers("paired Wilcoxon") == ["paired"]
          and q.investigator_judgement(leaf) and "votes = self.critical_votes                # every rule item" in src and "sample_size" in src)
    return ok, f"tolerance {tol.get('tolerance')}, modality, paired, judgement flag, three votes for every item and sample-size verification: {ok}"


def chk_windows_screening_and_not_a_rule():
    import inspect

    from clinical_asset.protocol import qualifiers as q
    from clinical_asset.protocol.compiler import ProtocolCompiler

    two = {"kind": "window", "text": "within 14 days of Visit 2", "relation": "WITHIN_AFTER", "offset": {"value": 14.0, "unit": "day"}}
    q.fix_window(two)
    ss = {"quantity": "target_accrual", "value": 60, "evidence": {"text": "60 patients will be screened"}}
    q.screening_count(ss)
    ok = two["relation"] == "WITHIN_EITHER" and ss["quantity"] == "planned_screened" and '"NOT_A_RULE": "NOT_A_RULE"' in inspect.getsource(ProtocolCompiler.verify)
    return ok, f"two-sided window {two['relation']}, screened count {ss['quantity']}, NOT_A_RULE handled: {ok}"


def chk_window_after_study_entry_one_sided():
    from clinical_asset.protocol import qualifiers as q

    a = {"kind": "window", "text": "Schedule Visit 2 within 14 days of consent.", "relation": "WITHIN_AFTER", "anchor": "consent",
         "offset": {"value": 14.0, "unit": "day"}}
    b = {"kind": "window", "text": "within 14 days of Visit 2", "relation": "WITHIN_AFTER", "anchor": "Visit 2", "offset": {"value": 14.0, "unit": "day"}}
    q.fix_window(a)
    q.fix_window(b)
    return (a["relation"], b["relation"]) == ("WITHIN_AFTER", "WITHIN_EITHER"), f"of consent: {a['relation']}; of a visit: {b['relation']}"


def chk_targeted_resolution():
    """The resolver applies only quote-backed corrections, repairs only its target items, and renders the protocol's own
    anchor wording."""
    import inspect

    from clinical_asset.protocol import render, resolver
    from clinical_asset.protocol.compiler import ProtocolCompiler

    class Doc:
        sections = []
    applied = resolver.apply_corrections({"logic": {"node": "LEAF", "kind": "unresolved", "text": "x"}},
                                         [{"target": "L0", "field": "relation", "value": "WITHIN_BEFORE", "evidence_quote": "not in any document"}], [Doc()])
    only = "only: set[str] | None = None" in inspect.getsource(ProtocolCompiler.repair)
    anchor = render.window({"relation": "WITHIN_BEFORE", "offset": {"value": 14, "unit": "day"}, "anchor": "Visit 2", "anchor_event": "scan_visit"}, "PSA")
    ok = applied == [] and only and "scan visit" not in anchor and "'Visit 2'" in anchor
    return ok, f"unsupported patch applied: {bool(applied)}; repair limited to targets: {only}; anchor rendered: {anchor!r}"


def chk_continuous_engine_and_unclassified_safety():
    import inspect

    from clinical_asset.trial import continuous, safety

    spec = {"analyses": [{"analysis_id": "A", "primary": True, "test_family": "wilcoxon", "design_qualifiers": ["paired"], "sidedness": "two_sided",
                          "alpha": {"value": 0.05}, "power": {"value": 0.8}, "effects": [{"text": "a mean of paired differences of 10"}]}],
            "sample_size": [{"quantity": "evaluable_target", "value": 52}]}
    d = continuous.design(spec)
    ok = d.get("status") == "RESOLVED" and abs(d["sd"] - 25.15) < 0.1 and "NO_EVIDENCE" in inspect.getsource(safety.v3_arm_events)
    return ok, f"continuous design {d.get('status')}, derived SD {d.get('sd')}; unclassified agents use protocol-cited incidences: {ok}"


def chk_within_patient_design():
    from clinical_asset.trial.recruitment import within_patient

    lab = lambda aid, t: {"arm_id": aid, "label": {"text": t}, "description": {"text": ""}}  # noqa: E731
    iv = lambda a, ph: {"category": "other", "canonical_agent": a, "agent": {"text": a}, "arms": [], "phase_id": ph, "dose": {"value": 1}}  # noqa: E731
    spec = {"metadata": {"design_summary": {"text": "a prospective intra-patient comparator study"}},
            "arms": [lab("ARM1", "Tracerone injection"), lab("ARM2", "Tracertwo injection")],
            "treatment_phases": [{"phase_id": "PH1", "sequence_number": 1}, {"phase_id": "PH2", "sequence_number": 2}],
            "interventions": [iv("tracertwo", "PH2"), iv("tracerone", "PH1")]}
    parallel = {**spec, "metadata": {"design_summary": {"text": "a randomized two-arm study"}}}
    w, p_ = within_patient(spec), within_patient(parallel)
    ok = bool(w) and w["arm_order"] == ["ARM1", "ARM2"] and p_ is None
    return ok, f"intra-patient order {w and w['arm_order']}; parallel design detected as within-patient: {bool(p_)}"


def chk_no_verbatim_echo():
    """Renderings carry structured content only, and the resolver rejects a free-text value that copies its evidence."""
    from clinical_asset.protocol import render
    from clinical_asset.protocol.resolver import copies

    e = {"role": "secondary", "name": {"text": "Detection rate"}, "type": "binary", "evidence": {"text": "The secondary endpoints will be estimated for each tracer."},
         "lead_in": "The secondary endpoints will be an estimate of the following", "population": {"text": "each tracer"}}
    r = render.endpoint(e)
    sentence = "TEAEs will be summarized overall and by severity and will include the number and percentage of patients"
    ok = "as stated" not in r and "listed under" not in r and copies(sentence, sentence) and not copies("central read", sentence)
    return ok, f"endpoint rendering {r!r}; a copied sentence is rejected: {copies(sentence, sentence)}"


def chk_response_derived_from_measurements():
    import numpy as np

    from clinical_asset.trial import analysis_results as ar

    c = ar.criteria({"response_criteria": {"categories": [
        {"category": {"text": "Partial response (PR)"}, "threshold": {"value": 50.0, "direction": "decrease"}},
        {"category": {"text": "Progressive Disease (PD)"}, "threshold": {"value": 25.0, "direction": "increase"}}]}})
    out = ar.simulate_tumour("S", "A", 400, 56, 0.0, 0.0, 120.0, None, None, ar.criteria({}), np.random.default_rng(1))
    ok = (c["pr"], c["pd"]) == (50.0, 25.0) and out["pd_day"] == 168 and ar.best_overall_response([(56, "PR"), (70, "PD")], True)[0] == "SD"
    return ok, f"protocol thresholds {c['pr']}/{c['pd']}; progression detected at the next assessment (day {out['pd_day']}); unconfirmed PR is not a response: {ok}"


def chk_results_by_subgroup():
    from clinical_asset.trial import subgroup_report as sr

    spec = {"arms": [], "eligibility": [], "stratification": {"factors": [], "strata": []},
            "subgroups": [{"subgroup": {"text": "age (< 70, >= 70)"}}, {"subgroup": {"text": "prior transplant (yes vs no)"}}]}
    bases = [{"demographic:age": {"value": 50 + i}, "demographic:sex": "male" if i % 2 else "female",
              "var:ecog_performance_status": {"value": i % 2}} for i in range(40)]
    fs = {f["factor"]: f for f in sr.factors(spec, bases, {})}
    age = {fs["Age (protocol cut points)"]["level"](b, {}) for b in bases}
    ok = age == {"< 70 years", ">= 70 years"} and fs["prior transplant (yes vs no)"]["level"] is None and "Sex" in fs and "Region" in fs
    return ok, (f"protocol age cut points {sorted(age)}; a protocol subgroup with no patient variable is listed as not generated: "
                f"{fs['prior transplant (yes vs no)']['level'] is None}; FDA demographics present: {'Sex' in fs}")


def chk_subgroup_evidence():
    from clinical_asset.trial import subgroup_evidence as sge

    v = sge.complement({"A": (0.5, 40), sge.ALL: (0.35, 100)}, ["A", "B"], orr=True)
    ev = {"factors": [{"key": "var:m", "kind": "existing", "levels": ["p", "n"], "mix": {"p": 0.3, "n": 0.7},
                       "effects": {"status": "RESOLVED", "reference_level": "p", "log_hazard_ratio": {"n": {"log_effect": 0.5}}}}]}
    mean = 0.3 * sge.patient_log_effects({"var:m": "p"}, ev)[0] + 0.7 * sge.patient_log_effects({"var:m": "n"}, ev)[0]
    ok = v is not None and abs(v[1] - 0.25) < 1e-9 and abs(mean) < 1e-12 and sge.parse_levels("x (yes vs no)") == ["yes", "no"]
    return ok, (f"complement from a whole-population row: {v}; patient effects centred on the mix (mean {mean:.1e}); "
                f"levels from the protocol's wording")


def chk_lock_paths_follow_renames():
    from clinical_asset.trial.lock import resolve

    p = resolve("protocols/Prot_SAP_000.pdf")
    ok = p.as_posix() == "protocols/NCT00392327.pdf" and p.exists()
    return ok, f"a protocol path recorded before the rename resolves to {p.as_posix()} (exists: {p.exists()})"


def chk_shell_loops_strip_cr():
    bad = []
    for p in Path("scripts").glob("*.sh"):
        s = p.read_text(encoding="utf-8")
        if "| while" in s and "read -r" in s and "python" in s.casefold() and "$'\\r'" not in s:
            bad.append(p.name)
    return not bad, "; ".join(bad) or "every shell loop reading Python output strips the carriage return"


def chk_no_control_characters():
    bad = [str(p) for root in ("clinical_asset", "scripts") for p in Path(root).rglob("*.py")
           if any(c < 32 and c not in (9, 10, 13) for c in p.read_bytes())]
    return not bad, "; ".join(bad) or "no control characters in sources"


def chk_no_vocabulary_in_code():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "tests/test_normalisation.py::test_no_trial_specific_medical_vocabulary_in_pipeline_code"],
                       capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": "."})
    return r.returncode == 0, (r.stdout.strip().splitlines() or ["no output"])[-1]


CHECKS = {k: v for k, v in globals().items() if k.startswith("chk_")}


# ----------------------------------------------------------------------------- the seed register

SEED = [
    ("L001", "protocol compiler", "a Simon stopping bound '< 8/22' was read as 22", "fractions in thresholds count the numerator; strict inequalities shift by one",
     "design_rules.bound", "chk_threshold_fraction"),
    ("L002", "blind selection", "the 'terminated for safety' category matched 'There were no safety concerns'", "category rules on free text must handle negation",
     "scripts/select_blind_holdouts.py SAFETY", "chk_sealing_negation"),
    ("L003", "protocol compiler", "a primary analysis compiled with alpha 1.0 made P(success) meaningless", "statistical parameters get plausibility ranges (alpha in (0, 0.5])",
     "StudySpec analyses", "chk_alpha_plausible"),
    ("L004", "dose modification", "a grade 3 cytopenia fired the hold rule of its febrile form", "qualifiers that change the condition must match on both sides",
     "trial.dose_modification.term_matches", "chk_febrile_distinct"),
    ("L005", "dose modification", "a dose-level definition ('after 1 reduction: 40 mg') fired on grade 2 anaemia", "state rules are checked on the patient state, never as event reactions",
     "trial.dose_modification.decide", "chk_state_rules_not_ae_reactions"),
    ("L006", "eligibility", "'adult' tested against numeric age marked all patients ineligible", "a category test on a numeric variable is undecidable, not false",
     "protocol.expressions.evaluate", "chk_numeric_category_undecidable"),
    ("L007", "schedule facts", "the model quoted 'approximately 8-week intervals' but returned no number", "numbers come from a deterministic parse of the verified quote, not from the model",
     "trial.schedule_facts.quote_interval", "chk_quote_interval_parser"),
    ("L008", "validation", "calibration and scoring needed to be shown on whole held-out trials", "whole trials, never rows, are split; calibrate and report on different trials",
     "scripts/build_trial_level_splits.py", "chk_trial_level_splits"),
    ("L009", "temporal evaluation", "the first showcase choice had results published before T0", "a temporal test excludes trials whose results were published before the cut-off",
     "scripts/select_showcase_trial.py, scripts/build_evidence_cutoff.py", "chk_showcase_not_in_evidence"),
    ("L010", "schedule facts", "one-time windows were rendered 'every N days' and rejected by the verifier", "render one-time and recurring schedule elements differently",
     "trial.schedule_facts._render", "chk_schedule_one_time_render"),
    ("L011", "code hygiene", "new journey modules embedded clinical terms in code, breaking the vocabulary guard", "clinical vocabulary lives in versioned reference data (clinical_asset/reference), never in pipeline code",
     "clinical_asset/reference/clinical_vocabulary.json", "chk_no_vocabulary_in_code"),
    ("L012", "code hygiene", "a regex edited through a string lost its \\b and gained a backspace character, silently failing", "edit regular expressions with the editor or raw strings; scan sources for control characters",
     "clinical_asset/*", "chk_no_control_characters"),
    ("L013", "evidence", "new registry corpora contained evaluated trials (e.g. BLIND_2) that evidence readers could use", "evaluated trials are never evidence: every reader drops them, cut-off or not",
     "clinical_asset/cutoff.py::excluded", "chk_evaluated_trials_never_evidence"),
    ("L014", "protocol compiler", "a PDF typeset in the Symbol font wrote '≤' as U+F0A3, so 'ECOG PS ≤ 2' compiled without a comparator", "map Symbol-font Private Use Area signs to Unicode before reading any comparison",
     "protocol.expressions.parse_comparator protocol.expressions.symbols", "chk_symbol_font_comparators"),
    ("L015", "operations", "a safety build crashed twice ('BrokenProcessPool'): its script had no __main__ guard, so Windows workers re-ran it", "scripts that start process pools run their work under if __name__ == '__main__'",
     "scripts/*.py data/spa_work/*.py", "chk_scripts_guard_main"),
    ("L016", "efficacy prediction", "the showcase's response prior was a mixture of unrelated myeloma regimens (median 32%, 90% range 3-93%): no information",
     "a family-level mixture is context, not a prediction; use the protocol-cited rate of the same regimen with the asset's same-regimen heterogeneity",
     "trial.noninferiority.cited_control_prior trial.noninferiority.run", "chk_family_mixture_not_prediction"),
    ("L017", "planning", "the showcase plan read a 28-day screening window as a 28-year accrual duration, ignored 'Approximately 100 investigative sites' and the sponsor 'Amgen Inc.'",
     "a duration needs a time unit and enrolment wording; operational facts the protocol states (sites, sponsor) replace averages over historical trials",
     "planning.report.accrual_durations_years stated_site_count sponsor_class", "chk_planning_reads_protocol_operations"),
    ("L018", "patient journey", "the showcase journey used a cross-regimen evidence median PFS of 8.7 months though the protocol cites 26.3 months for KRd: 12-month PFS 39% predicted vs 80% observed; 12 cycles completed 45% vs 67%",
     "the protocol-cited figure for the arm's own regimen comes before any cross-regimen evidence mixture (as L016, for every model input)",
     "trial.journey_evidence.cited_progression progression_model", "chk_journey_prefers_cited_progression"),
    ("L019", "arm resolution", "arm references were matched by substring: bare 'A','B','C' gave pemigatinib to standard-care arms, and 'Once-weekly' never matched 'Arm 1 (once-weekly KRd)', so the showcase journey gave no carfilzomib (0 dose holds)",
     "resolve arm references once, on whole words (label, designator, named agents); an unmatched reference applies to no arm and is reported",
     "trial.arms.ArmResolver (safety, journey, visits, journey_evidence)", "chk_arm_designators_resolve"),
    ("L020", "patient generation", "with no age limit the generator used the MIXED age class, which dropped the disease family: urothelial patients had mean age 38 (real 57-84)",
     "an unknown value is not a category: mix the age classes of the family's studies",
     "trial.population.age_class_mixture", "chk_unknown_age_class_not_mixed"),
    ("L021", "patient journey", "the journey had no adverse-event discontinuation or death (0 deaths vs 47 reported)",
     "use the registry participant flow for every exit reason it reports: withdrawal, adverse event, death",
     "trial.journey_evidence.disposition_probability trial.journey.simulate_patient", "chk_journey_registry_exits"),
    ("L022", "efficacy prediction", "a neoadjuvant chemotherapy arm got a response prior pooled from metastatic regimens of other classes (family level)",
     "L016 applies to every engine: a family-level mixture is context, never the arm's prediction",
     "trial.binary.evidence_prior", "chk_family_prior_is_context_in_binary"),
    ("L023", "efficacy prediction", "a cited 4/7 response (57%) was used as a point rate; the trial observed 7%",
     "a cited rate carries its own count: report its interval and flag small samples",
     "trial.binary.cited_uncertainty", "chk_cited_count_uncertainty"),
    ("L024", "planning", "the operational-risk headline was P(enrolment complete) 1.0 under the protocol's 124/year, 12x the historical median; the trial enrolled 7",
     "the historical model is the headline; a protocol assumption outside the historical range is flagged",
     "planning.report._risk", "chk_risk_headline_historical"),
    ("L025", "critic", "planning unit errors (36-month accrual read as 36 years) and arm-resolution failures were found by hand",
     "every defect class found by hand becomes an automatic critic check",
     "agent.critic.check_planning check_arms", "chk_critic_checks_planning_and_arms"),
    ("L026", "eligibility", "0 of 10,000 patients were ever proven eligible in nine protocols: generated patients carry no labs or history",
     "every patient is decided: criteria the patients cannot answer are calibrated to the registry screen pass rate",
     "trial.eligibility.resolve_unknowns", "chk_no_undetermined_patients"),
    ("L027", "results", "secondary endpoints, unmodelled binary endpoints and families without evidence were left UNRESOLVED",
     "one source ladder for every endpoint (protocol-cited > regimen > class > family > all oncology > design hypothesis), results from the simulated patients",
     "trial.quantify trial.endpoints", "chk_every_endpoint_classified"),
    ("L028", "protocol compiler", "IMPORTANT items the verifiers judged INCORRECT (dose rules, arm-specific interventions) were never repaired, so their rules were lost",
     "repair every item judged incorrect, not only CRITICAL ones; an incorrect item is never run as compiled",
     "protocol.compiler.ProtocolCompiler.repair trial.run_forward", "chk_repair_incorrect_important_items"),
    ("L029", "efficacy prediction", "a pembrolizumab-only cited response rate was taken as the rate of a pemigatinib plus pembrolizumab arm",
     "a cited figure that names agents is the arm's only when it names exactly the arm's agents",
     "trial.journey_evidence.same_regimen", "chk_component_rate_is_not_regimen_rate"),
    ("L030", "protocol compiler", "a new protocol extracted at 59% faithful: '296±20%' kept as a fixed 296, 'should occur' made mandatory, 'paired' Wilcoxon lost, the endpoint list's lead-in and the flush order dropped, an investigator-judged exclusion left unresolved, and analyses, sample size and discontinuation never verified",
     "restore every qualifier the verified quotes hold (deterministically), render it, verify every rule item with three votes, and loop repair until all are faithful or no progress; residual failures go to the agent backlog with a root cause",
     "protocol.qualifiers protocol.render protocol.compiler.verify repair", "chk_qualifiers_restored_and_all_verified"),
    ("L031", "protocol compiler", "after round 2 of a new protocol: 'within five biological half-lives' had no unit, 'within 14 days of Visit 2' became 'after', a window anchored on its own wording, 'Approximately 60 patients will be screened' became target accrual, a safety endpoint's reporting statement was not rendered, and an item the verifiers unanimously found not to be a rule stayed 'unverified'",
     "drug-relative units and two-sided windows are kept as stated; a screened count is not enrolment; the reporting statement is rendered; NOT_A_RULE makes an item informational",
     "protocol.qualifiers.fix_window screening_count protocol.render.endpoint protocol.compiler.verify", "chk_windows_screening_and_not_a_rule"),
    ("L032", "protocol compiler", "the L031 two-sided rule turned 'Schedule Visit 2 within 14 days of consent' into 'before or after consent'",
     "a window measured from a study-entry event (consent, enrolment, registration, randomisation, screening) can only follow it",
     "protocol.qualifiers.fix_window STUDY_ENTRY", "chk_window_after_study_entry_one_sided"),
    ("L033", "protocol compiler", "fixing one item by recompiling the whole protocol re-extracted everything, cost hundreds of calls, re-broke items that were right, and a deterministic default overrode a direction the protocol's own schedule settled; the renderer added an internal event label ('scan visit') to the protocol's 'Visit 2'",
     "resolve only the failing items as an agentic RAG loop: retrieve passages, investigate (with more searches when needed), apply quote-backed field corrections, re-extract only when no correction is supported, re-verify only that item; never override a settled direction; render the protocol's own anchor wording",
     "protocol.resolver protocol.compiler.repair(only) protocol.render.window", "chk_targeted_resolution"),
    ("L034", "engines", "a diagnostic imaging protocol (paired Wilcoxon on a continuous measure; PET tracers with no drug class) ran with no primary engine and safety UNRESOLVED",
     "a continuous primary with a stated design gets its own engine (SD derived from the power statement and checked by simulation); an agent with no drug class uses the protocol's cited incidences, else NO_EVIDENCE",
     "trial.continuous trial.engine_choice trial.safety.v3_arm_events", "chk_continuous_engine_and_unclassified_safety"),
    ("L035", "trial design", "an intra-patient study (each patient receives both tracers) was simulated as two parallel arms, each tracer was given to every arm, and a 10-day imaging study was followed for 2 years with a progression model",
     "detect within-patient designs and give every patient one record per arm in the protocol's order; an unreferenced item belongs to the arm naming its product only when every arm names its own; with no cycles, participation ends after the last procedure plus the reporting window",
     "trial.recruitment.within_patient trial.arms.arms_of_item trial.journey (A22)", "chk_within_patient_design"),
    ("L036", "protocol compiler", "renderings passed verification by echoing protocol sentences ('as stated: ...', 'listed under ...', '(protocol wording: ...)') instead of the extraction being right",
     "no verbatim: renderings show structured content only; the resolver agent writes structured values backed by a quote, and a value that copies its quote is rejected",
     "protocol.render protocol.qualifiers protocol.resolver.copies", "chk_no_verbatim_echo"),
    ("L037", "reporting", "results were drawn as rates and reported in an ad hoc layout: response was 'not simulated' in the journey, PFS was detected only while on treatment, and safety was not in the FDA standard tables",
     "derive response from simulated tumour measurements under the protocol's own thresholds (PharmaSUG: SDTM TU/TR/RS, ADaM ADRS/ADTTE with standard censoring), and report safety in the FDA standard tables",
     "trial.analysis_results scripts/build_ae_soc_map.py", "chk_response_derived_from_measurements"),
    ("L038", "reporting", "results were reported only by arm (one ORR or median for the whole trial), which says little for feasibility and control-arm questions: who is enrolled, who is excluded, and how each group does",
     "report every result by arm AND by subgroup (the protocol's stratification factors and analysis subgroups by meaning, FDA demographics, baseline disease factors): efficacy, arm-vs-control within each level with forest plots, safety, disposition and screening; every factor states whether the model gives it an effect (evidence-driven) or its levels differ only by chance (mix only), and a protocol subgroup with no patient variable is listed as not generated",
     "trial.subgroup_report trial.analysis_results", "chk_results_by_subgroup"),
    ("L039", "patient generation", "subgroup results were empty or meaningless: most factors a protocol stratifies by or names as subgroups were never generated for patients, and no patient characteristic changed outcomes within an arm, so every subgroup differed only by chance",
     "generate each protocol subgroup factor from registry baseline tables (retrieved by meaning, categories mapped to the protocol's levels by three model votes, pooled by disease family and phase; else equal shares, A27), reuse a variable that already carries it, and take prognostic effects from registry results reported by subgroup (class tables, separate measures, and the complement of a whole-population row), applied per patient and centred on the mix (A28); a factor with fewer than 3 trials of effect evidence stays 'mix only'",
     "trial.subgroup_evidence trial.baseline_extra trial.journey trial.analysis_results", "chk_subgroup_evidence"),
    ("L040", "operations", "after protocols were renamed by NCT, every new run stopped at the population stage: the facts lock records the PDF's old path, and locks are never edited",
     "a path a lock records is resolved through the alias manifest (data/manifest/protocol_aliases.json) when it no longer exists; the checksum still decides it is the same file",
     "trial.lock.resolve trial.population planning.report trial.safety trial.compare", "chk_lock_paths_follow_renames"),
    ("L041", "operations", "the protocol batch stopped every protocol with 'protocol_facts_v1.0.0 is not a locked artefact' although the lock existed: the shell loop read the version from Windows Python output ending in CRLF, so the directory name carried a hidden carriage return",
     "a shell loop that reads values printed by Python strips the trailing carriage return before using them",
     "scripts/run_test_protocols.sh", "chk_shell_loops_strip_cr"),
]


def seed() -> None:
    REGISTER.parent.mkdir(parents=True, exist_ok=True)
    have = {json.loads(line)["id"] for line in open(REGISTER, encoding="utf-8")} if REGISTER.exists() else set()
    with open(REGISTER, "a", encoding="utf-8") as fh:
        for lid, area, symptom, rule, where, check in SEED:
            if lid not in have:
                fh.write(json.dumps({"id": lid, "recorded": str(date.today()), "area": area, "symptom": symptom, "general_rule": rule,
                                     "where": where, "check": check, "origin": "project history"}) + "\n")


def load() -> list[dict]:
    if not REGISTER.exists():
        return []
    latest: dict = {}
    for line in open(REGISTER, encoding="utf-8"):
        r = json.loads(line)
        latest[r["id"]] = {**latest.get(r["id"], {}), **r}
    return list(latest.values())


def add(lesson: dict) -> dict:
    REGISTER.parent.mkdir(parents=True, exist_ok=True)
    ids = [int(x["id"][1:]) for x in load()]
    lesson = {"id": f"L{(max(ids) + 1 if ids else 1):03d}", "recorded": str(date.today()), **lesson}
    with open(REGISTER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(lesson, ensure_ascii=False) + "\n")
    write_markdown()
    return lesson


def write_markdown(results: list[dict] | None = None) -> Path:
    """Render the register (and, when given, the latest check results) to LESSONS_MD, kept in the repository."""
    status = {r["id"]: r for r in results or []}
    lines = ["# Lessons learned", "",
             f"Generated from `{REGISTER.as_posix()}` by `clinical_asset.agent.lessons` on {date.today()}. "
             "Each lesson has a regression check; the agent loop runs them before accepting any change.", ""]
    for x in sorted(load(), key=lambda r: r["id"]):
        s = status.get(x["id"])
        lines += [f"## {x['id']} — {x.get('area', '')}" + (f" ({s['status']})" if s else ""), "",
                  f"- **What went wrong:** {x.get('symptom', '')}",
                  f"- **General rule:** {x.get('general_rule', '')}",
                  f"- **Where:** `{x.get('where', '')}`",
                  f"- **Check:** `{x.get('check', '')}`" + (f" — {s['detail']}" if s else ""),
                  f"- **Recorded:** {x.get('recorded', '')} ({x.get('origin', 'agent')})", ""]
    LESSONS_MD.write_text("\n".join(lines), encoding="utf-8")
    return LESSONS_MD


def run_checks() -> list[dict]:
    out = []
    for lesson in load():
        fn = CHECKS.get(lesson.get("check"))
        if fn is None:
            out.append({"id": lesson["id"], "status": "NO_CHECK", "detail": lesson.get("check")})
            continue
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 - a crashing check is a failing check
            ok, detail = False, f"check raised {type(e).__name__}: {e}"
        out.append({"id": lesson["id"], "status": "PASS" if ok else "OPEN", "detail": detail, "general_rule": lesson["general_rule"]})
    write_markdown(out)
    return out
