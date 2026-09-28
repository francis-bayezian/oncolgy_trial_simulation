"""Design rules: the decision rules a protocol's design applies to accumulating data.

Two families are compiled:

* binary decision rules for an arm or cohort (single-stage or two-stage designs such as Simon's): stage sizes,
  the number of responses at or below which a stage stops the arm, the number at or above which the arm is
  declared of interest, and the design's stated null and alternative rates, type I and type II error and
  probability of early termination;
* rule-based dose escalation: cohort size, the escalate / expand / stop rules as 'x of n' patient counts, the
  maximum tolerated dose definition and the dose-limiting toxicity window. When the protocol lists no dose levels,
  the dose ladder is compiled from the starting dose and the stated increments (per stage, e.g. an accelerated
  titration that doubles the dose until a stated toxicity, and per escalate row of the rule table); an increment
  stated as a maximum ('increase of <=33%') is applied at that maximum, rounded down to the stated dosage forms.

Every number is parsed deterministically from a verbatim quote. For binary rules the exact operating
characteristics are computed from the binomial distribution and checked against what the protocol states: a
stated design whose computed error rates or early-termination probability disagree with the protocol's own
figures is a static error (usually a misread threshold), which triggers automatic repair.
"""

import re
from typing import Any

from scipy import stats

from . import expressions as ex
from .schemas import QUOTES, TEXT, enum, obj

DESIGN_RULES = obj({
    "binary_rules": {"type": "array", "items": obj({
        "rule_id": TEXT, "role": enum("primary", "secondary"), "arm_label_quotes": QUOTES, "cohort_quote": TEXT,
        "design_family": enum("simon_optimal", "simon_minimax", "two_stage_other", "single_stage", "other"),
        "outcome": enum("response", "toxicity"), "early_stop_binding": enum("binding", "non_binding", "not_stated"),
        "endpoint_quote": TEXT, "p0_quote": TEXT, "p1_quote": TEXT, "alpha_quote": TEXT, "beta_quote": TEXT,
        "stages": {"type": "array", "items": obj({"stage_quote": TEXT, "cumulative_n_quote": TEXT, "stop_if_at_most_quote": TEXT,
                                                  "continue_if_at_least_quote": TEXT, "stop_if_events_at_least_quote": TEXT})},
        "success_if_at_least_quote": TEXT, "decision_quote": TEXT, "early_termination_probability_quote": TEXT, "evidence_quote": TEXT})},
    "dose_escalation": {"type": "array", "items": obj({
        "rule_id": TEXT, "design_family": enum("three_plus_three", "accelerated_titration", "rolling_six", "other"),
        "applies_to_quote": TEXT, "cohort_size_quote": TEXT, "dose_level_quotes": QUOTES, "starting_dose_quote": TEXT,
        "max_dose_quote": TEXT, "dosage_form_quotes": QUOTES, "increment_sequence_quote": TEXT,
        "stages": {"type": "array", "items": obj({
            "stage_kind": enum("accelerated_titration", "rule_based"), "cohort_size_quote": TEXT, "increment_quote": TEXT,
            "switch_condition_quote": TEXT, "evidence_quote": TEXT})},
        "rules": {"type": "array", "items": obj({
            "action": enum("escalate", "expand_cohort", "stop_dose_exceeds_mtd", "expand_previous_level", "declare_mtd"),
            "dlt_count_quote": TEXT, "dlt_count_comparator": enum("exactly", "at_most", "at_least"),
            "patients_quote": TEXT, "increment_quote": TEXT, "evidence_quote": TEXT})},
        "mtd_definition_quote": TEXT, "dlt_window_quote": TEXT, "evidence_quote": TEXT})}})
DESIGN_RULES_INSTRUCTIONS = (
    "Extract the DECISION RULES of the trial design. binary_rules: every single-stage or two-stage rule that decides "
    "from the number of responders (or other binary outcomes) whether an arm or cohort stops early or is declared of "
    "interest; one rule per arm and cohort it applies to (an identical design stated 'in each arm' gives one rule per "
    "arm). role 'primary' for the primary objective. For each stage copy stage_quote, the words that state that stage "
    "exactly as written ('the study will initially enroll 10 evaluable patients in each arm'), and the cumulative number "
    "of patients "
    "(cumulative_n_quote, e.g. '10', then '22') and the threshold as written: stop_if_at_most_quote when the text says "
    "'if 0 or 1 of the 10 ... no further patients' (quote '0 or 1'), continue_if_at_least_quote when it says 'if 2 or "
    "more ... accrual continues' (quote '2 or more'); success_if_at_least_quote the final number of responses that "
    "declares the arm of interest, as a NUMBER of responses, with decision_quote the sentence stating that final "
    "decision ('6 or more'; leave the number empty when the text gives only a "
    "percentage or a test); p0/p1 the rates to rule out and to detect, alpha/beta as written (beta_quote may state the "
    "power instead, e.g. 'power of 0.9': copy it as written); outcome 'response' when more events are good (responses), "
    "'toxicity' when the rule counts harmful events (DLTs, toxicities) and stops when too MANY occur: then give each "
    "stage's stop_if_events_at_least_quote ('two or more', quote '2 or more') instead of the response thresholds; "
    "early_stop_binding 'non_binding' when an interim stop is only considered or recommended ('termination will be "
    "considered', 'may be stopped'), 'binding' when the text says the arm or study stops, else 'not_stated'; "
    "early_termination_probability_quote ONLY when the text states the probability of stopping early under the null "
    "rate. When the primary analysis is an exact test of a single proportion (stated p0, p1, alpha and sample size) "
    "and the protocol also states an early stopping rule for that endpoint ('if no patients respond, the study will "
    "stop at the point at which 9 patients results are known'), return ONE rule: first the stopping stage (9, stop "
    "if at most 0), then the final stage with the full sample size; leave the success count empty when it is not "
    "written as a number (it is derived from the exact test). dose_escalation: rule-based escalation designs (3+3, "
    "accelerated titration, rolling six): cohort size, dose levels only when the protocol lists fixed doses (e.g. "
    "'25 mg', '50 mg'; leave empty when doses are defined by increments), and one entry in 'rules' for EVERY row of "
    "the escalation rule or table, including escalate, expand and stop rows at both 3 and 6 patients "
    "(e.g. a table 'number of patients with DLT / action'): action; dlt_count_quote the number of patients with a "
    "DLT as written ('0', '1', '2 or more', 'no'); dlt_count_comparator (exactly / at_most / at_least); "
    "patients_quote the number of patients it refers to ('3', '6', 'up to 6'); increment_quote, for an escalate row, the "
    "dose increase that row states ('increase of <=33%', 'doubling'), else empty. Use action 'expand_previous_level' for "
    "a row that says the current dose exceeds the MTD AND more patients are added at the PREVIOUS (lower) dose level "
    "('add 3 additional patients at the previous dose level'); 'stop_dose_exceeds_mtd' when no patients are added. "
    "When doses are defined by a starting dose and increments rather than listed: starting_dose_quote ('Starting dose of "
    "25 mg'), max_dose_quote only if a maximum dose is stated, dosage_form_quotes the available dose strengths if stated "
    "('25 mg and 100 mg capsules'; list EVERY strength stated), increment_sequence_quote a named sequence if used ('modified Fibonacci'), and one "
    "entry in 'stages' per escalation stage in order: stage_kind 'accelerated_titration' (single-patient or small "
    "cohorts with fixed large increments) or 'rule_based' (the 3+3 or similar table), its cohort_size_quote (the words "
    "giving the minimum and, if stated, the maximum number of patients per dose level), its "
    "increment_quote ('Twice the Previous Dose', 'increase of <=50%'), and switch_condition_quote, the condition that "
    "ends the stage ('until 1 patient experiences a study drug related toxicity of >= Grade 2 or experiences a DLT'). "
    "Every *_quote is copied verbatim (contiguous words), or empty."
)

_OF = re.compile(r"(\d+|\bno\b|\bnone\b|\bzero\b)\s*(?:or more|or fewer|or less)?\s*(?:of|out of|/)\s*(?:the\s+)?(?:first\s+)?(\d+)", re.IGNORECASE)


def _numbers(text: str | None) -> list[float]:
    values = [v for _, v, _ in ex.number_spans(text or "")]
    if not values and re.search(r"\b(no|none|zero)\b", text or "", re.IGNORECASE):
        return [0.0]
    return values


def _count(text: str | None) -> list[float]:
    """Counts of patients: a percentage is a rate, never a count."""
    return [] if "%" in (text or "") else _numbers(text)


_FRACTION = re.compile(r"(\d+)\s*/\s*(\d+)")
_STRICT_LESS = re.compile(r"(?<![<≤])<(?!=)|\bfewer than\b|\bless than\b|\bbelow\b", re.IGNORECASE)
_STRICT_MORE = re.compile(r"(?<![>≥])>(?!=)|\bmore than\b|\bgreater than\b|\babove\b|\bexceed", re.IGNORECASE)
_INCLUSIVE = re.compile(r"≤|<=|≥|>=|or fewer|or less|or more|at least|at most", re.IGNORECASE)


def bound(text: str | None, kind: str) -> list[float]:
    """A count threshold as the rule uses it. 'k/n' counts k; for an 'at_most' threshold a strict '< k' / 'fewer than
    k' is at most k - 1; for an 'at_least' threshold a strict '> k' / 'more than k' is at least k + 1 (a failure
    condition written as '< k' leaves the success threshold at k). '2 or more', '<= 3' are taken as written."""
    t = text or ""
    frac = _FRACTION.search(t)
    values = [float(frac.group(1))] if frac else _numbers(t)
    if not values:
        return []
    inclusive = bool(_INCLUSIVE.search(t))
    if kind == "at_most":
        v = max(values)
        return [v - 1 if _STRICT_LESS.search(t) and not inclusive else v]
    v = min(values)
    return [v + 1 if _STRICT_MORE.search(t) and not inclusive else v]


def _rate(text: str | None) -> float | None:
    """'15%' -> 0.15, 'p0=0.15' -> 0.15, '0.10' -> 0.10."""
    if not text:
        return None
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if pct:
        return float(pct.group(1)) / 100
    nums = [v for v in _numbers(text) if 0 <= v <= 1]
    return nums[-1] if nums else None


DESIGN_RULES_VERIFY_NOTE = (
    " Here each item is a compiled DECISION RULE of the trial design. Numbers marked 'derived' (a success threshold "
    "computed from the stated exact test, alpha, p0 and sample size) are calculated deterministically by the compiler "
    "and are not additions: judge whether the stages, the stopping rules, the sample sizes and the stated design "
    "parameters are what the protocol text states, and whether any stated rule is missing. For a dose escalation whose "
    "doses are defined by a starting dose and increments, the dose ladder is computed by the compiler from the quoted "
    "starting dose and increments (an increment stated as 'up to' or '<=' is applied at its maximum, rounded down to "
    "the stated dosage forms); judge whether the starting dose, the increments, the stage switch and the rule rows "
    "are what the text states."
)

MODIFIED_FIBONACCI = [2.0, 1.67, 1.5, 1.4, 1.33]           # the conventional sequence; 1.33 repeats after the fifth step
_UNIT = r"(mg/m\s?2|mg/m²|mg/kg|mcg/kg|µg/kg|ug/kg|mg|mcg|µg|ug|g|gy|iu|units?)"
_DOSE = re.compile(r"(\d+(?:\.\d+)?)\s*" + _UNIT + r"(?![a-z])", re.IGNORECASE)
_AT_MOST = re.compile(r"≤|<=|up to|no more than|not (?:to )?exceed|maximum|at most|as close to", re.IGNORECASE)


def parse_dose(text: str | None) -> dict | None:
    m = _DOSE.search(text or "")
    if not m:
        return None
    unit = m.group(2).casefold().replace(" ", "").replace("²", "2").replace("µ", "u").replace("mcg", "ug")
    return {"value": float(m.group(1)), "unit": unit}


def parse_increment(text: str | None) -> dict | None:
    """'Twice the previous dose' -> x2; 'increase of <=33%' -> up to x1.33; '3-fold' -> x3; 'modified Fibonacci' ->
    the conventional sequence; 'increments of 50 mg' -> +50 mg."""
    t = " ".join((text or "").split())
    if not t:
        return None
    bound = "at_most" if _AT_MOST.search(t) else "exact"
    if re.search(r"modified\s+fibonacci", t, re.IGNORECASE):
        return {"sequence": MODIFIED_FIBONACCI, "bound": "exact"}
    if re.search(r"\b(doubl\w*|twice)\b", t, re.IGNORECASE):
        return {"factor": 2.0, "bound": bound}
    m = re.search(r"(\d+(?:\.\d+)?)\s*-?\s*fold", t, re.IGNORECASE)
    if m:
        return {"factor": float(m.group(1)), "bound": bound}
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
    if m:
        return {"factor": 1 + float(m.group(1)) / 100, "bound": bound}
    d = parse_dose(t)
    if d and re.search(r"increase|increment|\bby\b|\+", t, re.IGNORECASE):
        return {"add": d["value"], "unit": d["unit"], "bound": bound}
    return None


def patient_counts(text: str | None) -> list[float]:
    """Numbers of patients in a cohort-size quote: numbers attached to a patient word ('1 patient', 'up to 3 patients',
    '3 evaluable patients'), or the quote itself when it is only a number; other numbers ('28 days') are not counts."""
    t = " ".join((text or "").split())
    found = [float(m.group(1)) for m in re.finditer(r"(\d+)\s+(?:[a-z-]+\s+){0,2}?(?:patients?|subjects?|participants?)\b", t, re.IGNORECASE)]
    if not found and re.fullmatch(r"\(?\d+\)?", t):
        found = [float(t.strip("()"))]
    return found


def parse_switch(text: str | None) -> dict | None:
    """'until 1 patient experiences a ... toxicity of >= Grade 2 or experiences a DLT' -> {patients 1, grade 2, or DLT}."""
    t = " ".join((text or "").split())
    if not t:
        return None
    n = re.search(r"(\d+)\s+(?:\w+\s+){0,2}?(?:patients?|subjects?|participants?)", t, re.IGNORECASE)
    g = re.search(r"grade\s*(?:≥|>=|of at least)?\s*(\d)|(?:≥|>=)\s*\w*\s*(\d)", t, re.IGNORECASE)
    grade = next((int(x) for x in (g.groups() if g else ()) if x), None)
    dlt = bool(re.search(r"\bDLT\b|dose[- ]limiting", t, re.IGNORECASE))
    if grade is None and not dlt:
        return None
    return {"patients": int(n.group(1)) if n else 1, "grade_at_least": grade, "or_dlt": dlt,
            "drug_related": bool(re.search(r"related|attribut", t, re.IGNORECASE))}


def binary_rule(raw: dict) -> dict:
    """Stage sizes and thresholds from the quotes; issues when they are incomplete or inconsistent."""
    issues, stages = [], []
    toxicity = raw.get("outcome") == "toxicity"
    for k, s in enumerate(raw["stages"]):
        n = _numbers(s["cumulative_n_quote"])
        if toxicity:
            # a toxicity rule stops when at least k patients have the event; it is held as the equivalent rule on patients
            # WITHOUT the event (at most n - k of them), so the same exact computations apply to the complement rate
            ev = bound(s.get("stop_if_events_at_least_quote"), "at_least")
            at_most = (int(n[-1]) - int(min(ev))) if n and ev else None
            stages.append({"n": int(n[-1]) if n else None, "stop_if_at_most": at_most, "stop_if_events_at_least": int(min(ev)) if ev else None})
            if not n:
                issues.append(f"stage {k + 1}: no cumulative sample size")
            continue
        stop = bound(s["stop_if_at_most_quote"], "at_most")
        cont = bound(s["continue_if_at_least_quote"], "at_least")
        at_most = max(stop) if stop else (min(cont) - 1 if cont else None)
        if not n:
            issues.append(f"stage {k + 1}: no cumulative sample size")
        stages.append({"n": int(n[-1]) if n else None, "stop_if_at_most": None if at_most is None else int(at_most)})
    beta, beta_note = _rate(raw["beta_quote"]), None
    if beta is not None and (re.search(r"power", raw["beta_quote"] or "", re.IGNORECASE) or beta > 0.5):
        beta, beta_note = round(1 - beta, 10), f"the protocol states the power ({beta:g}); beta = 1 - power"
    if toxicity:
        final = stages[-1] if stages else {}
        success = [final["n"] - final["stop_if_events_at_least"] + 1] if final.get("n") and final.get("stop_if_events_at_least") else []
        if stages:
            stages[-1] = {**final, "stop_if_at_most": None}
    else:
        success = [] if "%" in (raw["success_if_at_least_quote"] or "") else bound(raw["success_if_at_least_quote"], "at_least")
    rule = {"stages": stages, "success_if_at_least": int(min(success)) if success else None, "family": raw.get("family", ""),
            "outcome": "toxicity" if toxicity else "response", "early_stop_binding": raw.get("early_stop_binding") or "not_stated",
            "p0": _rate(raw["p0_quote"]), "p1": _rate(raw["p1_quote"]), "alpha": _rate(raw["alpha_quote"]), "beta": beta,
            "beta_derivation": beta_note, "stated_early_termination": _rate(raw["early_termination_probability_quote"])}
    if not stages or any(s["n"] is None for s in stages):
        issues.append("stage sizes incomplete")
    if rule["success_if_at_least"] is None and stages and stages[-1]["n"] and rule["p0"] is not None and rule["alpha"] is not None:
        # the final analysis is an exact one-sided test of a single proportion, which defines its own critical value
        n, p0, alpha = stages[-1]["n"], rule["p0"], rule["alpha"]
        rule["success_if_at_least"] = next(r for r in range(n + 2) if r > n or stats.binom.sf(r - 1, n, p0) <= alpha)
        rule["success_derivation"] = f"smallest r with exact P(X >= r | p0 = {p0}) <= alpha = {alpha} among {n} (final exact test)"
    if rule["success_if_at_least"] is None:
        issues.append("no success threshold")
    if len(stages) > 1 and any(s["stop_if_at_most"] is None for s in stages[:-1]):
        issues.append("an interim stage has no stopping threshold")
    ns = [s["n"] for s in stages if s["n"] is not None]
    if ns != sorted(ns):
        issues.append("cumulative stage sizes must increase")
    rule["issues"] = issues
    if not issues:
        rule["operating_characteristics"] = operating_characteristics(rule)
        rule["issues"] += design_consistency(rule)
    return rule


def prob_success(rule: dict, p: float) -> float:
    """Exact probability that the arm is declared of interest when the true rate is p."""
    stages = rule["stages"]
    dist = {0: 1.0}                 # number of responses so far -> probability of reaching this point without stopping
    prev_n = 0
    for k, s in enumerate(stages):
        m = s["n"] - prev_n
        new: dict[int, float] = {}
        for x, px in dist.items():
            for y in range(m + 1):
                q = px * stats.binom.pmf(y, m, p)
                new[x + y] = new.get(x + y, 0.0) + q
        prev_n = s["n"]
        last = k == len(stages) - 1
        if not last:
            dist = {x: q for x, q in new.items() if x > s["stop_if_at_most"]}
        else:
            dist = new
    return float(sum(q for x, q in dist.items() if x >= rule["success_if_at_least"]))


def prob_early_stop(rule: dict, p: float) -> float:
    if len(rule["stages"]) < 2:
        return 0.0
    first = rule["stages"][0]
    return float(stats.binom.cdf(first["stop_if_at_most"], first["n"], p))


def expected_n(rule: dict, p: float) -> float:
    if len(rule["stages"]) < 2:
        return float(rule["stages"][0]["n"])
    pet = prob_early_stop(rule, p)
    return rule["stages"][0]["n"] * pet + rule["stages"][-1]["n"] * (1 - pet)


def final_only(rule: dict) -> dict:
    """The rule with its interim stops ignored (how the error rates of a non-binding design are defined)."""
    return {**rule, "stages": [{**rule["stages"][-1], "stop_if_at_most": None}]}


def operating_characteristics(rule: dict) -> dict:
    out = {}
    for name, p in (("at_p0", rule["p0"]), ("at_p1", rule["p1"])):
        if p is not None:
            out[name] = {"p": p, "prob_success": prob_success(rule, p), "prob_early_stop": prob_early_stop(rule, p), "expected_n": expected_n(rule, p)}
            if rule.get("early_stop_binding") == "non_binding" and len(rule["stages"]) > 1:
                out[name]["prob_success_ignoring_interim"] = prob_success(final_only(rule), p)
    return out


def design_consistency(rule: dict) -> list[str]:
    """The stated design's error rates and early-termination probability against the exact computation."""
    oc, issues = rule["operating_characteristics"], []
    if rule.get("early_stop_binding") == "non_binding":          # error rates of a non-binding design ignore the interim stop
        oc = {k: {**v, "prob_success": v.get("prob_success_ignoring_interim", v["prob_success"])} for k, v in oc.items()}
    if rule["alpha"] is not None and "at_p0" in oc and oc["at_p0"]["prob_success"] > rule["alpha"] + 0.01:
        issues.append(f"exact type I error {oc['at_p0']['prob_success']:.3f} exceeds the stated alpha {rule['alpha']}")
    if rule["beta"] is not None and "at_p1" in oc and oc["at_p1"]["prob_success"] < 1 - rule["beta"] - 0.01:
        issues.append(f"exact power {oc['at_p1']['prob_success']:.3f} is below the stated 1 - beta {1 - rule['beta']:.2f}")
    pet = rule.get("stated_early_termination")
    if rule.get("family", "").startswith("simon") and pet is not None and "at_p0" in oc and abs(oc["at_p0"]["prob_early_stop"] - pet) > 0.02:
        # a Simon design's probability of early termination under p0 is part of its definition; other designs are not checked
        issues.append(f"exact early-termination probability {oc['at_p0']['prob_early_stop']:.3f} differs from the stated {pet}")
    return issues


def count_rules(text: str | None) -> list[dict]:
    """'if 1 of 3 patients ...' / '2 or more of 6' -> [{'events': 1, 'of': 3, 'or_more': False}, ...]."""
    out = []
    for m in _OF.finditer(text or ""):
        k = m.group(1).casefold()
        events = 0 if k in {"no", "none", "zero"} else int(k)
        out.append({"events": events, "of": int(m.group(2)), "or_more": "or more" in m.group(0).casefold()})
    return out


def escalation_rule(raw: dict) -> dict:
    cohort = _numbers(raw["cohort_size_quote"])
    rows = []
    for index, r in enumerate(raw.get("rules") or []):
        k, n = _numbers(r["dlt_count_quote"]), _numbers(r["patients_quote"])
        if k and n:
            rows.append({"action": r["action"], "dlt": int(k[0]), "comparator": r["dlt_count_comparator"], "patients": int(max(n)), "quote_index": index,
                         "increment": parse_increment(r.get("increment_quote")) if r["action"] == "escalate" else None})
    doses = [q for q in raw["dose_level_quotes"] if _numbers(q)]
    if len(doses) < 2:              # a single stated dose is the starting dose, not a list of dose levels
        doses = []
    stages = []
    for st in raw.get("stages") or []:
        c = patient_counts(st.get("cohort_size_quote"))    # '1 patient (up to 3 may be enrolled)': at least 1, at most 3
        stages.append({"kind": st["stage_kind"], "cohort_size": int(min(c)) if c else None,
                       "cohort_max": int(max(c)) if c and max(c) > min(c) else None, "increment": parse_increment(st.get("increment_quote")),
                       "switch": parse_switch(st.get("switch_condition_quote"))})
    sequence = parse_increment(raw.get("increment_sequence_quote"))
    ladder = {"start": parse_dose(raw.get("starting_dose_quote")), "max": parse_dose(raw.get("max_dose_quote")),
              "dosage_forms": [d for d in (parse_dose(x) for x in raw.get("dosage_form_quotes") or []) if d],
              "sequence": sequence["sequence"] if sequence and "sequence" in sequence else None, "stages": stages}
    rule = {"design_family": raw["design_family"], "cohort_size": int(cohort[0]) if cohort else None, "rules": rows,
            "dose_levels": doses, "ladder": ladder, "issues": []}
    # the cohort of a rule table is its first decision point ('0 of 3 ...'); a stated size above it is the level's cap
    # ('each cohort will enroll up to 6 patients'), kept as written
    if rows:
        first = min(r["patients"] for r in rows)
        if rule["cohort_size"] != first:
            rule["cohort_size_stated"] = rule["cohort_size"]
            rule["cohort_size"] = first
        for s in stages:
            if s["kind"] == "rule_based" and (s["cohort_size"] is None or s["cohort_size"] > first):
                s["cohort_size_stated"], s["cohort_size"] = s["cohort_size"], first
    actions = {r["action"] for r in rows}
    if raw["design_family"] in {"three_plus_three", "rolling_six", "accelerated_titration"} and (
            (rule["cohort_size"] is None and not any(s["cohort_size"] for s in stages))
            or "escalate" not in actions or not actions & {"stop_dose_exceeds_mtd", "expand_previous_level"}):
        rule["issues"].append("escalation rule incomplete: cohort size and both an escalate and a stop rule are required")
    if not doses:
        escalates = [r for r in rows if r["action"] == "escalate"]
        has_increment = (bool(ladder["sequence"]) or bool(escalates) and all(r["increment"] for r in escalates)
                         or any(s["increment"] for s in stages if s["kind"] == "rule_based"))
        if ladder["start"] is None or not has_increment:
            rule["issues"].append("dose ladder incomplete: neither listed dose levels nor a starting dose with the escalation increments")
        for s in stages:
            if s["kind"] == "accelerated_titration" and (s["increment"] is None or s["switch"] is None):
                rule["issues"].append("accelerated titration stage incomplete: its increment and the condition that ends it are required")
    return rule


def increment_text(inc: dict | None) -> str:
    if not inc:
        return "no increment"
    if "sequence" in inc:
        return f"sequence x{inc['sequence']}"
    if "add" in inc:
        return f"+{inc['add']:g} {inc['unit']}" + (" at most" if inc["bound"] == "at_most" else "")
    return f"x{inc['factor']:g}" + (" at most" if inc["bound"] == "at_most" else "")


def _said(record) -> str:
    text = record.get("text") if isinstance(record, dict) else record
    return " ".join((text or "").split())


def _ladder_text(e: dict, r: dict | None = None) -> str:
    lad = e.get("ladder") or {}
    stage_quotes = (r or {}).get("stage_quotes") or []
    start = lad.get("start")
    parts = [f"doses computed from the starting dose {start['value']:g} {start['unit']}" if start else "no starting dose"]
    if lad.get("sequence"):
        parts.append(f"increments by the sequence x{lad['sequence']}")
    row_increments = any(x.get("increment") for x in e.get("rules") or [])
    for k, s in enumerate(lad.get("stages") or []):
        dose = (f"dose {increment_text(s['increment'])}" if s.get("increment") else
                "dose increments as stated in the escalate rows of the rule table" if row_increments else "dose no increment")
        size = (f"at least {s['cohort_size']} and up to {s['cohort_max']} patients per dose level (simulated at the minimum, "
                f"{s['cohort_size']}, required before escalating)" if s.get("cohort_max") else f"cohorts of {s['cohort_size']}")
        text = f"stage {k + 1} {s['kind']}: {size}" + (
            f" (as written: up to {s['cohort_size_stated']} per dose level)" if s.get("cohort_size_stated") else "") + f", {dose}"
        sq = stage_quotes[k] if k < len(stage_quotes) else {}
        said = [_said(sq.get(f)) for f in ("cohort_size_quote", "increment_quote", "switch_condition_quote", "evidence_quote") if _said(sq.get(f))]
        if said:
            text += " (as written: " + " | ".join(f"'{x}'" for x in dict.fromkeys(said)) + ")"
        if s.get("switch"):
            sw = s["switch"]
            related = "study-drug-related " if sw.get("drug_related") else ""
            text += (f", ends when {sw['patients']} patient(s) have a {related}toxicity of grade >= {sw['grade_at_least']}" if sw["grade_at_least"] else
                     f", ends when {sw['patients']} patient(s)") + (" or a DLT" if sw["or_dlt"] else "")
        parts.append(text)
    if lad.get("max"):
        parts.append(f"maximum dose {lad['max']['value']:g} {lad['max']['unit']}")
    if lad.get("dosage_forms"):
        parts.append("dosage forms " + ", ".join(f"{d['value']:g} {d['unit']}" for d in lad["dosage_forms"]))
    return "; ".join(parts)


def render_rule(r: dict) -> str:
    if r["kind"] == "binary":
        b = r["rule"]
        quotes = r.get("stage_quotes") or []
        parts = []
        tox = b.get("outcome") == "toxicity"
        stops = "stopping is considered (non-binding)" if b.get("early_stop_binding") == "non_binding" else "the arm stops"
        for k, s in enumerate(b["stages"]):
            words = quotes[k] if k < len(quotes) and quotes[k] else None
            size = f"{s['n']} patients" if k == 0 else f"up to {s['n']} patients in total (cumulative, including stage 1)"
            text = f"stage {k + 1}: {size}" + (f" (as written: {words!r})" if words else "")
            if k < len(b["stages"]) - 1:
                if tox and s.get("stop_if_events_at_least") is not None:
                    text += f"; if at least {s['stop_if_events_at_least']} of them have the event (e.g. a DLT), {stops}, otherwise it continues to stage {k + 2}"
                elif s["stop_if_at_most"] is not None:
                    text += f"; if at most {s['stop_if_at_most']} of them respond, {stops}, otherwise it continues to stage {k + 2}"
            parts.append(text)
        stages = "; ".join(parts)
        if tox:
            last = b["stages"][-1] if b["stages"] else {}
            k = last.get("stop_if_events_at_least")
            threshold = (f"the study stops if at least {k} of the {last.get('n')} patients have the event (e.g. a DLT) and proceeds if at most "
                         f"{k - 1} do" if k is not None else "no final event threshold is stated")
        else:
            threshold = f"of interest if at least {b['success_if_at_least']} responses" + (f" (derived: {b['success_derivation']})" if b.get("success_derivation") else "")
        if r.get("decision_quote"):
            threshold += f" (as written: {r['decision_quote']!r})"
        cohort = r.get("cohort")
        cohort = cohort.get("text") if isinstance(cohort, dict) else cohort
        scope = ("the study's single arm" if r.get("single_arm") else
                 f"the arm {r.get('arm_labels') or 'of the study'} (the protocol applies the design to each arm separately)")
        return (f"{r['role']} binary decision rule for {scope} "
                f"(cohort: {cohort or 'all patients'}), {r['design_family']}: {stages}; {threshold}; p0 {b['p0']}, p1 {b['p1']}, "
                f"alpha {b['alpha']}, " + (f"power {1 - b['beta']:g} (beta {b['beta']:g}, {b['beta_derivation']})" if b.get("beta_derivation")
                                            else f"beta {b['beta']}")
                + (f", stated early termination {b['stated_early_termination']}" if b["stated_early_termination"] else ""))
    e = r["rule"]
    points = sorted({x["patients"] for x in e["rules"]}) or [e["cohort_size"]]

    def meaning(x: dict) -> str:
        nxt = next((p for p in points if p > x["patients"]), None)
        return {"escalate": "escalate to the next dose",
                "expand_cohort": (f"add {nxt - x['patients']} patients at the current dose (to {nxt})" if nxt else "add patients at the current dose"),
                "stop_dose_exceeds_mtd": "the current dose exceeds the MTD",
                "expand_previous_level": (f"the current dose exceeds the MTD; add {points[-1] - points[0]} patients at the previous dose level "
                                          f"if only {points[0]} patients had been treated there"),
                "declare_mtd": "declare the current dose the MTD"}.get(x["action"], x["action"])

    def when(x: dict) -> str:
        if x["comparator"] == "at_least" and x["patients"] == points[-1]:     # the level's cap: counted up to that number
            return f"if at least {x['dlt']} patients among up to {x['patients']} treated at the dose have a DLT"
        return f"if {x['comparator'].replace('_', ' ')} {x['dlt']} of {x['patients']} patients have a DLT"

    row_quotes = r.get("rule_quotes") or []

    def as_written(k: int) -> str:
        q = row_quotes[k] if k < len(row_quotes) else {}
        said = [_said(q.get(f)) for f in ("increment_quote", "evidence_quote") if _said(q.get(f))]
        return (" (as written: " + " | ".join(f"'{x}'" for x in dict.fromkeys(said)) + ")") if said else ""

    rows = "; ".join(f"{when(x)}: {meaning(x)}" + as_written(x.get("quote_index", k))
                     + (f" (dose {increment_text(x['increment'])})" if x.get("increment") else "") for k, x in enumerate(e["rules"]))
    cohort = f"cohorts of {e['cohort_size']}" + (f" (as written: up to {e['cohort_size_stated']} per dose level)" if e.get("cohort_size_stated") else "")
    text = f"dose escalation ({e['design_family']}): {cohort}; {rows}"
    window = ((r.get("quotes") or {}).get("dlt_window_quote") or {})
    window = window.get("text") if isinstance(window, dict) else window
    timing = f"; DLT evaluation window (as written: '{' '.join(window.split())}')" if window else ""
    mtd = _said((r.get("quotes") or {}).get("mtd_definition_quote"))
    mtd = f"; MTD definition (as written: '{mtd}')" if mtd else ""
    return text + (f"; dose levels {e['dose_levels']}" if e["dose_levels"] else f"; {_ladder_text(e, r)}") + timing + mtd


def build(results: list[dict], source_of, q, arms: list[dict]) -> list[dict]:
    """StudySpec 'decision_rules' from the extraction results. `q(src, quote, field)` records a verified quote."""
    labels = {a["arm_id"]: (a["label"].get("text") if isinstance(a["label"], dict) else a["label"]) or "" for a in arms}
    rules = []
    for r in results:
        src, o = source_of(r), r["output"]
        for raw in o.get("binary_rules", []):
            parsed = binary_rule({**raw, "family": raw["design_family"]})
            matched = [aid for aid, lab in labels.items()
                       if any(_key(lab) and (_key(lab) in _key(x) or _key(x) in _key(lab)) for x in raw["arm_label_quotes"])]
            rules.append({"decision_rule_id": f"DR{len(rules) + 1}", "kind": "binary", "role": raw["role"],
                          "design_family": raw["design_family"], "arms": matched, "arm_quotes": [q(src, x, "arm") for x in raw["arm_label_quotes"]],
                          "cohort": q(src, raw["cohort_quote"], "cohort"), "endpoint": q(src, raw["endpoint_quote"], "endpoint"),
                          "rule": parsed, "evidence": q(src, raw["evidence_quote"], "evidence"),
                          "stage_quotes": [" ".join((st.get("stage_quote") or "").split()) for st in raw["stages"]],
                          "decision_quote": " ".join((raw.get("decision_quote") or "").split()),
                          "quote_records": [q(src, st.get("stage_quote") or "", "stage") for st in raw["stages"]] + [q(src, raw.get("decision_quote") or "", "decision")],
                          "quotes": {k: q(src, raw[k], k) for k in ("p0_quote", "p1_quote", "alpha_quote", "beta_quote", "success_if_at_least_quote",
                                                                    "early_termination_probability_quote")},
                          "compile_issues": parsed["issues"], "sections": r["sections"], "document": r["document"]})
        for raw in o.get("dose_escalation", []):
            parsed = escalation_rule(raw)
            rules.append({"decision_rule_id": f"DR{len(rules) + 1}", "kind": "dose_escalation", "role": "primary",
                          "design_family": raw["design_family"], "arms": [], "applies_to": q(src, raw["applies_to_quote"], "applies_to"),
                          "rule": parsed, "evidence": q(src, raw["evidence_quote"], "evidence"),
                          "rule_quotes": [{k: q(src, x.get(k) or "", k) for k in ("dlt_count_quote", "patients_quote", "increment_quote", "evidence_quote")}
                                          for x in raw.get("rules") or []],
                          "stage_quotes": [{k: q(src, st.get(k) or "", k) for k in ("cohort_size_quote", "increment_quote", "switch_condition_quote",
                                                                                     "evidence_quote")} for st in raw.get("stages") or []],
                          "quotes": {k: q(src, raw.get(k) or "", k) for k in ("cohort_size_quote", "starting_dose_quote", "max_dose_quote",
                                                                              "increment_sequence_quote", "mtd_definition_quote", "dlt_window_quote")},
                          "compile_issues": parsed["issues"], "sections": r["sections"], "document": r["document"]})
    split = []
    for rule in rules:
        if rule["kind"] == "binary" and not rule["arms"]:
            rule["arms"] = list(labels)          # stated without an arm: the design applies to each arm
        for aid in rule["arms"] or [None]:
            one = {**rule, "arms": [aid] if aid else [], "arm_labels": labels.get(aid) if aid else None, "single_arm": len(labels) == 1}
            if one["kind"] == "dose_escalation":        # one rule per escalation table: keep the most complete compile of it
                sig = (one["kind"], aid, repr([(x["action"], x["dlt"], x["comparator"], x["patients"]) for x in one["rule"]["rules"]]))
                same = next((k for k, (s2, _) in enumerate(split) if s2 == sig), None)
                if same is not None:
                    if _completeness(one) > _completeness(split[same][1]):
                        split[same] = (sig, one)
                    continue
            else:
                sig = (one["kind"], aid, _key((one.get("cohort") or {}).get("text") if isinstance(one.get("cohort"), dict) else one.get("cohort")),
                       repr(one["rule"].get("stages")), one["rule"].get("success_if_at_least"), repr(one["rule"].get("rules")))
            if all(sig != s for s, _ in split):
                split.append((sig, one))
    out = []
    for k, (_, one) in enumerate(split):
        one["decision_rule_id"] = f"DR{k + 1}"
        one["rendering_basis"] = render_rule(one)
        out.append(one)
    return out


def _completeness(rule: dict) -> tuple:
    e = rule["rule"]
    lad = e.get("ladder") or {}
    return (-len(e.get("issues") or []), bool(lad.get("start")), len(lad.get("stages") or []), len(lad.get("dosage_forms") or []),
            sum(1 for x in e["rules"] if x.get("increment")))


def _key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").casefold())

