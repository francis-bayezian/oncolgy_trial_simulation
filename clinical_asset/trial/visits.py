"""The protocol's visit schedule, from the compiled StudySpec, with the quote for each element.

Resolved (each with provenance, or UNRESOLVED with the reason):

* cycle length of the first treatment phase with one;
* dosing days of each anticancer intervention within a cycle (listed days, or a frequency: daily, weekly, every N weeks);
* screening window (the largest 'within N days' offset before treatment in the assessment schedule);
* tumour assessment interval ('every N weeks / cycles / months' near imaging, tumour or response wording);
* in-cycle days on which laboratory tests are scheduled (day columns of laboratory rows);
* maximum number of cycles, when stated.

The calendar then lays out screening, each cycle's dosing and laboratory days, tumour assessments, end of treatment
and follow-up for one patient.
"""

import json
import re

from .patient_state import sourced

IMAGING = re.compile(r"\b(ct|mri|pet|imaging|scan|radiolog|tumou?r (assessment|evaluation|measurement)|recist|response (assessment|evaluation)|disease (assessment|evaluation))", re.I)
LAB = re.compile(r"laborator|haematolog|hematolog|\bcbc\b|biochem|chemistr|blood (count|assessment)", re.I)
EVERY = re.compile(r"(?:every|each|q)\s*(\d+)\s*(?:-|to)?\s*(weeks?|wks?|w\b|cycles?|months?|days?)", re.I)
DAY_COL = re.compile(r"^\s*(?:c\d+\s*)?d(?:ay)?\s*(\d+)\s*$", re.I)


def _t(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def _days(n: float, unit: str, cycle_days: float | None) -> float | None:
    u = unit.lower()
    if u.startswith("w"):
        return n * 7
    if u.startswith("d"):
        return n
    if u.startswith("m"):
        return n * 30.4375
    if u.startswith("c"):
        return n * cycle_days if cycle_days else None
    return None


def cycle_length(spec: dict) -> dict:
    for p in sorted(spec.get("treatment_phases") or [], key=lambda p: p.get("sequence_number") or 0):
        cl = p.get("cycle_length") or {}
        if cl.get("days"):
            return sourced(float(cl["days"]), "protocol", f"treatment phase {p['phase_id']}", _t(cl.get("text")))
    for iv in spec.get("interventions") or []:
        f = _t((iv.get("schedule") or {}).get("frequency")) or ""
        m = EVERY.search(f)
        if iv.get("category") == "anticancer_drug" and m:
            d = _days(float(m.group(1)), m.group(2), None)
            if d:
                return sourced(d, "protocol", f"dosing frequency of {iv.get('canonical_agent')}", f)
    return sourced(None, "unsupported", "no cycle length or dosing interval is stated in the compiled StudySpec")


def dosing_days(iv: dict, cycle_days: float | None) -> dict:
    s = iv.get("schedule") or {}
    if s.get("days"):
        return sourced(sorted({int(d) for d in s["days"]}), "protocol", "listed dosing days", _t(s.get("day_text")))
    f = (_t(s.get("frequency")) or "").lower()
    if cycle_days and re.search(r"\bdaily|once a day|every day|\bqd\b|\bbid\b|twice (a )?day", f):
        return sourced(list(range(1, int(cycle_days) + 1)), "protocol", "daily dosing", _t(s.get("frequency")))
    if cycle_days and re.search(r"\bweekly|once a week|every week", f):
        return sourced(list(range(1, int(cycle_days) + 1, 7)), "protocol", "weekly dosing", _t(s.get("frequency")))
    m = EVERY.search(f)
    if cycle_days and m:
        step = _days(float(m.group(1)), m.group(2), cycle_days)
        if step:
            return sourced(list(range(1, int(cycle_days) + 1, max(1, int(step)))), "protocol", "dosing interval", _t(s.get("frequency")))
    if s.get("weeks") and cycle_days is None:
        return sourced([7 * (int(w) - 1) + 1 for w in s["weeks"]], "protocol", "dosing weeks", _t(s.get("week_text")))
    if cycle_days:
        return sourced([1], "assumption", "no dosing days stated: day 1 of each cycle", assumption="A8_resume_same_dose") \
            if False else sourced(None, "unsupported", f"no dosing days for {iv.get('canonical_agent')}")
    return sourced(None, "unsupported", f"no dosing days for {iv.get('canonical_agent')}")


def _schedule_rows(spec: dict):
    for sch in spec.get("assessments") or []:
        for a in sch.get("assessments") or []:
            yield sch, a


def screening_window(spec: dict) -> dict:
    best = None
    for _, a in _schedule_rows(spec):
        for tp in a.get("timepoints") or []:
            t = tp.get("time") or {}
            head = (_t(tp.get("header")) or "").lower()
            if t.get("kind") == "offset" and t.get("days") and re.search(r"before|prior|screen|baseline|inclusion|pre", head):
                if best is None or t["days"] > best[0]:
                    best = (float(t["days"]), _t(tp.get("header")))
    if best:
        return sourced(best[0], "protocol", "assessment schedule: pre-treatment window", best[1])
    return sourced(None, "unsupported", "no screening window stated in the assessment schedule")


def tumour_assessment_interval(spec: dict, cycle_days: float | None) -> dict:
    cands = []
    for _, a in _schedule_rows(spec):
        name = _t(a.get("assessment")) or ""
        if not IMAGING.search(name):
            continue
        for tp in a.get("timepoints") or []:
            for txt in (_t(tp.get("frequency")), _t(tp.get("cell")), _t(tp.get("header"))):
                m = EVERY.search(txt or "")
                if m and (d := _days(float(m.group(1)), m.group(2), cycle_days)):
                    cands.append((d, f"{name.strip()[:60]}: {txt.strip()[:80]}"))
    if not cands:                                     # anywhere in the specification near imaging/response wording
        blob = json.dumps({k: spec.get(k) for k in ("assessments", "endpoints", "response_criteria", "definitions",
                                                    "discontinuation_rules", "treatment_phases")}, ensure_ascii=False)
        for m in EVERY.finditer(blob):
            window = blob[max(0, m.start() - 160): m.end() + 60]
            if IMAGING.search(window) and (d := _days(float(m.group(1)), m.group(2), cycle_days)) and 14 <= d <= 120:
                cands.append((d, window.replace("\\n", " ")[-200:]))
    if not cands:
        return sourced(None, "unsupported", "no tumour assessment interval stated: progression is recorded at its true time")
    counts: dict = {}
    for d, q in cands:
        counts.setdefault(round(d), []).append(q)
    d = max(counts, key=lambda k: (len(counts[k]), -k))
    return sourced(float(d), "protocol", "tumour assessment interval", counts[d][0])


def lab_days_in_cycle(spec: dict) -> dict:
    days, quote = set(), None
    for _, a in _schedule_rows(spec):
        if not LAB.search(_t(a.get("assessment")) or ""):
            continue
        for tp in a.get("timepoints") or []:
            m = DAY_COL.match((_t(tp.get("header")) or "").replace("\n", " "))
            if m:
                days.add(int(m.group(1)))
                quote = quote or (_t(a.get("assessment")) or "")[:80]
    if days:
        return sourced(sorted(days), "protocol", "laboratory rows of the assessment schedule", quote)
    return sourced(None, "unsupported", "no in-cycle laboratory days in the assessment schedule")


def max_cycles(spec: dict) -> dict:
    for p in spec.get("treatment_phases") or []:
        cc = p.get("cycle_count") or {}
        if cc.get("value"):
            return sourced(int(cc["value"]), "protocol", f"cycle count of {p['phase_id']}", _t(cc.get("text")))
    return sourced(None, "unsupported", "no maximum number of cycles: treatment continues until an off-treatment event")


def _from_fact(fact: dict | None, current: dict, label: str) -> dict:
    """A schedule element from a protocol schedule fact, when the StudySpec left it unresolved."""
    if current["value"] is not None or not fact:
        return current
    flag = "" if fact.get("status") == "VERIFIED" else " (REVIEW_REQUIRED: used under the accept-review decision, flagged)"
    out = sourced(float(fact["interval_days"]), "protocol", f"{label}: schedule fact {fact['fact_id']}{flag}", fact["quote"])
    for k in ("first_day", "later_interval_days", "later_after_day", "time_origin", "status"):
        if fact.get(k) is not None:
            out[k] = fact[k]
    return out


ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6}


def cycles_of(iv: dict) -> list[int] | None:
    """The cycles an intervention is restricted to by its compiled condition ('the first cycle', 'cycles 1-8',
    'cycle 2 onwards' is not a restriction to a finite set); None when it applies to every cycle."""
    cond = (iv.get("condition") or {}).get("logic")
    if not cond:
        return None
    texts = [cond.get("text") or ""] + list(cond.get("categories") or [])
    for t in texts:
        low = t.lower()
        m = re.search(r"cycles?\s*(\d+)\s*(?:-|–|to|through)\s*(\d+)", low)
        if m:
            return list(range(int(m.group(1)), int(m.group(2)) + 1))
        m = re.search(r"(?:the\s+)?(first|second|third|fourth|fifth|sixth)\s+cycle", low) or re.search(r"cycle\s*(\d+)\b(?!\s*(?:and|onward|onwards|thereafter|\+))", low)
        if m:
            g = m.group(1)
            return [ORDINAL.get(g) or int(g)]
    return None


def planned_doses(agent_rec: dict, arm_label: str, cycle: int) -> list[tuple[int, dict, str]]:
    """(day in cycle, dose, intervention) planned for one arm in one cycle: a cycle-restricted entry (a starting dose)
    replaces the general entry on its own days of its cycles."""
    def for_arm(e):
        return not e["arms"] or any(x.lower() in arm_label.lower() or arm_label.lower() in x.lower() for x in e["arms"] if x)
    entries = [e for e in agent_rec["entries"] if for_arm(e) and e["dosing_days"]["value"] and e["dose"]["value"]]
    special = [e for e in entries if e["cycles"] and cycle in e["cycles"]]
    general = [e for e in entries if e["cycles"] is None]
    days: dict[int, tuple] = {}
    for e in general[:1]:
        for d in e["dosing_days"]["value"]:
            days[d] = (e["dose"]["value"], e["intervention_id"])
    for e in special:
        for d in e["dosing_days"]["value"]:
            days[d] = (e["dose"]["value"], e["intervention_id"])
    return [(d, dose, iid) for d, (dose, iid) in sorted(days.items())]


def schedule(spec: dict, facts: dict | None = None) -> dict:
    """The schedule from the StudySpec; elements it leaves unresolved are taken from the protocol's schedule facts
    (clinical_asset.trial.schedule_facts) when given."""
    from .schedule_facts import best

    cyc = cycle_length(spec)
    cd = cyc["value"]
    agents: dict = {}
    for iv in spec.get("interventions") or []:
        if iv.get("category") != "anticancer_drug" or not iv.get("canonical_agent"):
            continue
        d = iv.get("dose") or {}
        entry = {"intervention_id": iv["intervention_id"], "arms": [_t(a) for a in iv.get("arms") or []],
                 "dose": sourced({"value": d.get("value"), "unit": d.get("unit"), "basis": d.get("basis")}, "protocol",
                                 f"intervention {iv['intervention_id']}", _t(iv.get("evidence")) or _t(d.get("quote"))) if d.get("value") else
                 sourced(None, "unsupported", "no dose compiled"),
                 "route": ((iv.get("administration_options") or [{}])[0].get("canonical_route")),
                 "dosing_days": dosing_days(iv, cd), "cycles": cycles_of(iv)}
        a = agents.setdefault(iv["canonical_agent"], {"entries": []})
        a["entries"].append(entry)
    for a in agents.values():                  # the general (every-cycle) entry stands for the agent in summaries
        general = next((e for e in a["entries"] if e["cycles"] is None and e["dosing_days"]["value"]), a["entries"][0])
        a.update({k: general[k] for k in ("intervention_id", "dose", "route", "dosing_days")})
        a["arms"] = [] if any(not e["arms"] for e in a["entries"]) else sorted({x for e in a["entries"] for x in e["arms"]})
    fu = sourced(None, "unsupported", "no follow-up visit interval stated")
    return {"cycle_length_days": cyc,
            "screening_window_days": _from_fact(best(facts, "screening_window"), screening_window(spec), "screening window"),
            "tumour_assessment_interval_days": _from_fact(best(facts, "tumour_assessment"), tumour_assessment_interval(spec, cd),
                                                          "tumour assessment interval"),
            "lab_days_in_cycle": lab_days_in_cycle(spec),
            "follow_up_interval_days": _from_fact(best(facts, "follow_up_visit"), fu, "follow-up visits"),
            "max_cycles": max_cycles(spec), "agents": agents}


def calendar(sched: dict, until_day: int) -> list[dict]:
    """Planned visits from day 1 (first dose) to `until_day`: cycle day-1 visits, in-cycle dosing and laboratory days,
    tumour assessments. Each visit lists what is planned at it."""
    cd = sched["cycle_length_days"]["value"]
    visits: dict[int, dict] = {}

    def add(day, name, item):
        v = visits.setdefault(day, {"day": day, "name": name, "planned": []})
        if item not in v["planned"]:
            v["planned"].append(item)
    if cd:
        max_c = sched["max_cycles"]["value"]
        c = 0
        while (c * cd) + 1 <= until_day and (max_c is None or c < max_c):
            start = int(c * cd) + 1
            add(start, f"C{c + 1}D1", "clinical assessment")
            for agent, a in sched["agents"].items():
                for d in sorted({d for e in a.get("entries", [a]) for d in (e["dosing_days"]["value"] or [])}):
                    if start + d - 1 <= until_day:
                        add(start + d - 1, f"C{c + 1}D{d}", f"dose {agent}")
            for d in sched["lab_days_in_cycle"]["value"] or []:
                if start + d - 1 <= until_day:
                    add(start + d - 1, f"C{c + 1}D{d}", "laboratory tests")
            c += 1
    ta = sched["tumour_assessment_interval_days"]
    ti = ta["value"]
    if ti:
        day, k = float(ta.get("first_day") or ti) + 1, 1
        while day <= until_day:
            v = visits.setdefault(int(round(day)), {"day": int(round(day)), "name": f"TA{k}", "planned": []})
            v["planned"].append("tumour assessment")
            step = ta.get("later_interval_days") if ta.get("later_interval_days") and ta.get("later_after_day") and day > ta["later_after_day"] else ti
            day, k = day + step, k + 1
    return [visits[d] for d in sorted(visits)]
