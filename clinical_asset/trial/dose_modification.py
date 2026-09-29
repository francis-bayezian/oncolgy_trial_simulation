"""The protocol's dose-modification rules, executed on a patient's adverse events.

Each compiled rule (StudySpec dose_modifications) has an agent, a trigger (a logic tree over adverse-event terms,
grades, laboratory values and treatment state) and ordered steps (ACTION, RESUME, SUPPORTIVE_CARE, MONITOR, ASSESS)
with typed actions. A rule fires for an event when its trigger evaluates TRUE with three-valued logic:

* an adverse-event or grade leaf is decided by the event's term (general clinical synonyms, never trial-specific) and
  its grade;
* a relatedness leaf is TRUE under assumption A4; an 'occurs despite optimal prophylaxis / supportive care' leaf is
  TRUE under assumption A9; a 'normal at baseline' laboratory leaf is TRUE under assumption A10;
* a treatment-state leaf on the number of dose reductions or the length of an interruption is decided from the
  patient's state;
* any other leaf (tolerability, investigator judgement, a measurement the journey does not generate) is UNKNOWN, and
  a trigger that stays UNKNOWN does not fire (its rule is reported as undecidable, never guessed).

When several rules fire, the most severe action is applied: discontinue all > discontinue the agent > reduce > hold
> delay the cycle > no modification. Dose levels come from the protocol's own 'set_dose' rules keyed on the number
of reductions, else a stated percentage, else the reduction is recorded without a level (unsupported).
"""

import re

from ..reference import vocabulary

SEVERITY = ["discontinue_all", "discontinue_agent", "reduce_to_dose", "reduce_percent", "set_dose", "hold", "delay_cycle",
            "omit_subsequent_doses", "no_modification"]
_V = vocabulary()
HEMATOLOGIC = set(_V["hematologic_terms"])
HEMATOLOGIC_HEADS = set(_V["hematologic_synonym_heads"])
SYNONYMS = [set(g) for g in _V["ae_synonym_groups"]]      # general clinical vocabulary (reference data)


def _words(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("_", " ")).strip()


def _synonym_set(term: str) -> set:
    t = _words(term)
    for group in SYNONYMS:
        if any(_words(g) == t or _words(g) in t or t in _words(g) for g in group if len(_words(g)) >= 4):
            return {_words(g) for g in group}
    return {t}


QUALIFIERS = tuple(_V["distinguishing_qualifiers"])


def term_matches(rule_term: str, ae_term: str) -> bool:
    rt, at = _words(rule_term), _words(ae_term)
    if not rt or not at:
        return False
    if any((q in rt) != (q in at) for q in QUALIFIERS[:1]):       # 'febrile neutropenia' is not 'neutropenia'
        return False
    rt = re.sub(r"\b(grade|grades|event|events|adverse|toxicity)\b", " ", rt).strip()
    if not rt:
        return False
    if rt in {"non hematologic", "non hematologic ae", "non hematologic adverse", "nonhematologic"}:
        return not any(h.replace("_", " ") in at for h in HEMATOLOGIC)
    a, b = _synonym_set(rt), _synonym_set(at)
    return bool(a & b) or any(x in at for x in a if len(x) >= 5) or any(x in rt for x in b if len(x) >= 5)


def grades_of(leaf: dict) -> set | None:
    """The grades a leaf accepts: from categories ('Grade 3/4', 'Grade 1', 'Grade 3 (without infection)') or from an
    operator and value on a grade variable; None when the leaf does not constrain the grade."""
    out = set()
    for c in leaf.get("categories") or []:
        for m in re.finditer(r"grade\s*([1-5](?:\s*[/\-–,]\s*[1-5])*)", c, re.I):
            for n in re.findall(r"[1-5]", m.group(1)):
                out.add(int(n))
        if re.fullmatch(r"\s*[1-5]\s*", c or ""):
            out.add(int(c))
    op, v = leaf.get("op"), leaf.get("value")
    if not out and v is not None and "grade" in (leaf.get("canonical") or "") and op in {">=", ">", "<=", "<", "=="}:
        v = int(v)
        out = {g for g in range(1, 6) if {">=": g >= v, ">": g > v, "<=": g <= v, "<": g < v, "==": g == v}[op]}
    return out or None


def _leaf(leaf: dict, ae: dict, state: dict) -> bool | None:
    rt, canon, subj = leaf.get("rule_type"), leaf.get("canonical") or "", leaf.get("subject") or ""
    if re.fullmatch(r"(\w+_)?(related|relatedness|attribution)(_to_\w+)?", canon, re.I):
        return True                                                        # assumption A4
    if re.search(r"prophylaxis_fail|despite|supportive_care_fail|optimal_(prophylaxis|management|treatment)", canon, re.I):
        return True                                                        # assumption A9
    if re.fullmatch(r"clinically[_ ]significant", canon.strip(), re.I) and rt in {"adverse_event", "toxicity_grade"}:
        return ae["grade"] >= 3                                            # assumption A11
    if rt == "laboratory" and re.search(r"baseline", canon + " " + subj, re.I) and             re.search(r"(<=|less than or equal|within|normal|uln)", " ".join(leaf.get("categories") or []) + str(leaf.get("op")), re.I):
        return True                                                        # assumption A10
    if rt == "treatment_state" and "reduction" in canon:
        n, op, v = state["reductions"], leaf.get("op"), leaf.get("value")
        if v is None:
            return n > 0 if leaf.get("expected") is not False else n == 0
        return {">": n > v, ">=": n >= v, "==": n == v, "<": n < v, "<=": n <= v}.get(op)
    if rt == "timing" and "interruption" in canon and leaf.get("value") is not None:
        return state["held_days"] > leaf["value"]
    if rt in {"toxicity_grade", "adverse_event", "laboratory"}:
        grades = grades_of(leaf)
        named = re.sub(r"_?(grade|occurrences)$", "", canon) or subj
        term_ok = term_matches(named, ae["term"]) or term_matches(subj, ae["term"]) or \
            any(term_matches(c, ae["term"]) for c in leaf.get("categories") or [] if not re.search(r"grade", c, re.I))
        if grades is not None:
            generic = re.fullmatch(r"(adverse_event|ae|toxicity|any_toxicity|non_hematologic.*|other_toxicit.*)", named)
            if not term_ok and not generic:
                return False
            term_ok = term_ok or bool(generic)                            # a generic grade rule applies to any event
            return term_ok and ae["grade"] in grades
        if re.fullmatch(r"(other_toxicit.*|any_toxicit.*)", named) or any(re.match(r"\s*other toxicit", c, re.I) for c in leaf.get("categories") or []):
            return True                                                    # an explicit catch-all 'other toxicities' leaf
        if term_ok:
            return leaf.get("expected") is not False
        return False if rt == "adverse_event" and leaf.get("kind") == "flag" and leaf.get("categories") else None
    return None


def evaluate(node: dict | None, ae: dict, state: dict) -> bool | None:
    if not node:
        return None
    kind = node.get("node")
    if kind == "LEAF":
        return _leaf(node, ae, state)
    vals = [evaluate(c, ae, state) for c in node.get("children") or []]
    if kind == "AND":
        return False if False in vals else (True if vals and all(v is True for v in vals) else None)
    if kind == "OR":
        return True if True in vals else (False if vals and all(v is False for v in vals) else None)
    if kind == "NOT":
        v = vals[0] if vals else None
        return None if v is None else not v
    return None


def compile_rules(spec: dict) -> list[dict]:
    rules = []
    for d in spec.get("dose_modifications") or []:
        steps = sorted(d.get("steps") or [], key=lambda s: s.get("order") or 0)
        # the first UNCONDITIONAL typed action is what the rule does; conditional steps ('reduce if intolerable') need a
        # condition the journey cannot observe and are not executed
        actions = [s for s in steps if s.get("step_type") == "ACTION" and (s.get("action") or {}).get("type") in SEVERITY
                   and not s.get("condition")]
        resume = next((s for s in steps if s.get("step_type") == "RESUME" and not s.get("condition")), None)
        leaves = _leaves(d.get("trigger"))
        rules.append({"rule_id": d["rule_id"], "agent": d.get("canonical_agent"), "trigger": d.get("trigger"), "modality": d.get("modality"),
                      "category": ((d.get("category") or {}).get("text") or "").strip(),
                      "action": actions[0]["action"] if actions else None,
                      "resume": (resume or {}).get("action"),
                      "state_only": bool(leaves) and all(lf.get("rule_type") in {"treatment_state", "timing"} for lf in leaves),
                      "quote": ((actions[0].get("instruction") or {}).get("text") if actions else None)})
    return rules


def _leaves(node) -> list[dict]:
    if not isinstance(node, dict):
        return []
    if node.get("node") == "LEAF":
        return [node]
    return [x for c in node.get("children") or [] for x in _leaves(c)]


def dose_levels(rules: list[dict]) -> dict:
    """agent -> {reductions: dose value} from the protocol's set_dose rules keyed on the number of reductions."""
    levels: dict = {}
    for r in rules:
        a = r["action"] or {}
        if a.get("type") != "set_dose" or a.get("value") is None:
            continue
        leaves = [r["trigger"]] if (r["trigger"] or {}).get("node") == "LEAF" else (r["trigger"] or {}).get("children") or []
        for lf in leaves:
            if "reduction" in (lf.get("canonical") or "") and lf.get("op") == "==" and lf.get("value") is not None:
                levels.setdefault(r["agent"], {})[int(lf["value"])] = {"value": a["value"], "unit": a.get("unit"), "rule_id": r["rule_id"]}
    return levels


def applicable(rules: list[dict], agent: str) -> list[dict]:
    return [r for r in rules if r["agent"] in (agent, "study_treatment", None, "all")]


def decide(rules: list[dict], agent: str, ae: dict, state: dict) -> dict:
    """The action the protocol takes on `agent` for adverse event `ae` (term, grade), given the patient's state
    (reductions so far, days held). Returns the firing rule, the action and the undecidable rules."""
    fired, undecidable = [], []
    hema = any(h.replace("_", " ") in _words(ae["term"]) for h in HEMATOLOGIC) or bool(_synonym_set(ae["term"]) & HEMATOLOGIC_HEADS)
    state_check = not ae.get("term")
    for r in applicable(rules, agent):
        if r["action"] is None or r.get("modality") == "OPTIONAL":
            continue                                    # optional rules ('may ...') are not executed
        if r["state_only"] != state_check or (state_check and r["action"]["type"] == "set_dose"):
            continue                                    # state rules (reduction counts, interruption length) are checked on
            #                                             the patient's state, never as a reaction to an event; dose-level
            #                                             definitions are read by dose_levels()
        cat = _words(r["category"])
        if re.search(r"non ?h(a)?ematolog", cat) and hema or re.search(r"(?<!non )h(a)?ematolog", cat) and not re.search(r"non ?h(a)?ematolog", cat) and not hema:
            continue                                    # the rule's section limits it to (non-)haematological events
        v = evaluate(r["trigger"], ae, state)
        if v is True:
            fired.append(r)
        elif v is None and any(term_matches(x, ae["term"]) for x in _trigger_terms(r["trigger"])):
            undecidable.append(r["rule_id"])
    if not fired:
        return {"action": "no_rule", "rule_id": None, "undecidable": undecidable}
    r = min(fired, key=lambda r: SEVERITY.index(r["action"]["type"]))
    return {"action": r["action"]["type"], "value": r["action"].get("value"), "unit": r["action"].get("unit"),
            "percent": r["action"].get("reduction_percent"), "resume": (r["resume"] or {}).get("type"),
            "rule_id": r["rule_id"], "category": r["category"], "quote": r["quote"], "undecidable": undecidable}


def _trigger_terms(node) -> list[str]:
    if not isinstance(node, dict):
        return []
    if node.get("node") == "LEAF":
        return [node.get("canonical") or "", node.get("subject") or ""]
    return [t for c in node.get("children") or [] for t in _trigger_terms(c)]
