"""Design rules: the decision rules a protocol's design applies to accumulating data.

Two families are compiled:

* binary decision rules for an arm or cohort (single-stage or two-stage designs such as Simon's): stage sizes,
  the number of responses at or below which a stage stops the arm, the number at or above which the arm is
  declared of interest, and the design's stated null and alternative rates, type I and type II error and
  probability of early termination;
* rule-based dose escalation: cohort size, the escalate / expand / stop rules as 'x of n' patient counts, the
  maximum tolerated dose definition and the dose-limiting toxicity window.

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
        "endpoint_quote": TEXT, "p0_quote": TEXT, "p1_quote": TEXT, "alpha_quote": TEXT, "beta_quote": TEXT,
        "stages": {"type": "array", "items": obj({"stage_quote": TEXT, "cumulative_n_quote": TEXT, "stop_if_at_most_quote": TEXT,
                                                  "continue_if_at_least_quote": TEXT})},
        "success_if_at_least_quote": TEXT, "decision_quote": TEXT, "early_termination_probability_quote": TEXT, "evidence_quote": TEXT})},
    "dose_escalation": {"type": "array", "items": obj({
        "rule_id": TEXT, "design_family": enum("three_plus_three", "accelerated_titration", "rolling_six", "other"),
        "applies_to_quote": TEXT, "cohort_size_quote": TEXT, "dose_level_quotes": QUOTES, "starting_dose_quote": TEXT,
        "rules": {"type": "array", "items": obj({
            "action": enum("escalate", "expand_cohort", "stop_dose_exceeds_mtd", "declare_mtd"),
            "dlt_count_quote": TEXT, "dlt_count_comparator": enum("exactly", "at_most", "at_least"),
            "patients_quote": TEXT, "evidence_quote": TEXT})},
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
    "percentage or a test); p0/p1 the rates to rule out and to detect, alpha/beta as written; "
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
    "patients_quote the number of patients it refers to ('3', '6', 'up to 6'). Every *_quote is copied verbatim "
    "(contiguous words), or empty."
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
    "parameters are what the protocol text states, and whether any stated rule is missing."
)


def binary_rule(raw: dict) -> dict:
    """Stage sizes and thresholds from the quotes; issues when they are incomplete or inconsistent."""
    issues, stages = [], []
    for k, s in enumerate(raw["stages"]):
        n = _numbers(s["cumulative_n_quote"])
        stop = _numbers(s["stop_if_at_most_quote"])
        cont = _numbers(s["continue_if_at_least_quote"])
        at_most = max(stop) if stop else (min(cont) - 1 if cont else None)
        if not n:
            issues.append(f"stage {k + 1}: no cumulative sample size")
        stages.append({"n": int(n[-1]) if n else None, "stop_if_at_most": None if at_most is None else int(at_most)})
    success = _count(raw["success_if_at_least_quote"])
    rule = {"stages": stages, "success_if_at_least": int(min(success)) if success else None, "family": raw.get("family", ""),
            "p0": _rate(raw["p0_quote"]), "p1": _rate(raw["p1_quote"]), "alpha": _rate(raw["alpha_quote"]), "beta": _rate(raw["beta_quote"]),
            "stated_early_termination": _rate(raw["early_termination_probability_quote"])}
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


def operating_characteristics(rule: dict) -> dict:
    out = {}
    for name, p in (("at_p0", rule["p0"]), ("at_p1", rule["p1"])):
        if p is not None:
            out[name] = {"p": p, "prob_success": prob_success(rule, p), "prob_early_stop": prob_early_stop(rule, p), "expected_n": expected_n(rule, p)}
    return out


def design_consistency(rule: dict) -> list[str]:
    """The stated design's error rates and early-termination probability against the exact computation."""
    oc, issues = rule["operating_characteristics"], []
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
    for r in raw.get("rules") or []:
        k, n = _numbers(r["dlt_count_quote"]), _numbers(r["patients_quote"])
        if k and n:
            rows.append({"action": r["action"], "dlt": int(k[0]), "comparator": r["dlt_count_comparator"], "patients": int(max(n))})
    doses = [q for q in raw["dose_level_quotes"] if _numbers(q)]
    rule = {"design_family": raw["design_family"], "cohort_size": int(cohort[0]) if cohort else None, "rules": rows,
            "dose_levels": doses, "issues": []}
    actions = {r["action"] for r in rows}
    if raw["design_family"] in {"three_plus_three", "rolling_six"} and (rule["cohort_size"] is None or not {"escalate", "stop_dose_exceeds_mtd"} <= actions):
        rule["issues"].append("escalation rule incomplete: cohort size and both an escalate and a stop rule are required")
    return rule


def render_rule(r: dict) -> str:
    if r["kind"] == "binary":
        b = r["rule"]
        quotes = r.get("stage_quotes") or []
        parts = []
        for k, s in enumerate(b["stages"]):
            words = quotes[k] if k < len(quotes) and quotes[k] else None
            text = f"stage {k + 1}: {s['n']} patients" + (f" (as written: {words!r})" if words else "")
            if s["stop_if_at_most"] is not None and k < len(b["stages"]) - 1:
                text += f"; if at most {s['stop_if_at_most']} of them respond the arm stops, otherwise it continues to stage {k + 2}"
            parts.append(text)
        stages = "; ".join(parts)
        threshold = f"of interest if at least {b['success_if_at_least']} responses" + (f" (derived: {b['success_derivation']})" if b.get("success_derivation") else "")
        if r.get("decision_quote"):
            threshold += f" (as written: {r['decision_quote']!r})"
        cohort = r.get("cohort")
        cohort = cohort.get("text") if isinstance(cohort, dict) else cohort
        scope = ("the study's single arm" if r.get("single_arm") else
                 f"the arm {r.get('arm_labels') or 'of the study'} (the protocol applies the design to each arm separately)")
        return (f"{r['role']} binary decision rule for {scope} "
                f"(cohort: {cohort or 'all patients'}), {r['design_family']}: {stages}; {threshold}; p0 {b['p0']}, p1 {b['p1']}, "
                f"alpha {b['alpha']}, beta {b['beta']}" + (f", stated early termination {b['stated_early_termination']}" if b["stated_early_termination"] else ""))
    e = r["rule"]
    rows = "; ".join(f"{x['action']} if {x['comparator'].replace('_', ' ')} {x['dlt']} of {x['patients']} patients have a DLT" for x in e["rules"])
    return f"dose escalation ({e['design_family']}): cohorts of {e['cohort_size']}; {rows}; dose levels {e['dose_levels']}"


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
                          "rule_quotes": [{k: q(src, x[k], k) for k in ("dlt_count_quote", "patients_quote", "evidence_quote")} for x in raw.get("rules") or []],
                          "quotes": {k: q(src, raw[k], k) for k in ("cohort_size_quote",
                                                                    "mtd_definition_quote", "dlt_window_quote")},
                          "compile_issues": parsed["issues"], "sections": r["sections"], "document": r["document"]})
    split = []
    for rule in rules:
        if rule["kind"] == "binary" and not rule["arms"]:
            rule["arms"] = list(labels)          # stated without an arm: the design applies to each arm
        for aid in rule["arms"] or [None]:
            one = {**rule, "arms": [aid] if aid else [], "arm_labels": labels.get(aid) if aid else None, "single_arm": len(labels) == 1}
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


def _key(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").casefold())

