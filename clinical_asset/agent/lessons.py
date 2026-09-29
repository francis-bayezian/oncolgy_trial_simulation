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
