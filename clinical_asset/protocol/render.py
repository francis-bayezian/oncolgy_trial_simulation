"""Plain-language rendering of compiled StudySpec items, for independent verification and review."""

from typing import Any

OPS = {">=": "at least", ">": "greater than", "<=": "at most", "<": "less than", "==": "equal to", "!=": "not equal to"}
MODAL = {"REQUIRED": "", "PROHIBITED": "PROHIBITED: ", "OPTIONAL": "OPTIONAL (may): ", "RECOMMENDED": "RECOMMENDED (should): ",
         "STRONGLY_RECOMMENDED": "STRONGLY RECOMMENDED: "}
RELATIONS = {"WITHIN_BEFORE": "within {v} before", "WITHIN_AFTER": "within {v} after", "BEFORE": "before",
             "AFTER": "after", "AT_LEAST_BEFORE": "at least {v} before", "AT_LEAST_AFTER": "at least {v} after",
             "MORE_THAN_BEFORE": "more than {v} before", "MORE_THAN_AFTER": "more than {v} after",
             "ON_OR_BEFORE": "on or before day {v} of", "ON_CYCLE_DAY": "on day {v} of", "SAME_DAY": "on the same day as"}
CALENDAR = {"NEXT_BUSINESS_DAY_IF_NON_BUSINESS_DAY": " (moved to the next business day if that day is a weekend or holiday)",
            "PREVIOUS_BUSINESS_DAY_IF_NON_BUSINESS_DAY": " (moved to the previous business day if that day is a weekend or holiday)"}
ACTIONS = {"discontinue_agent": "permanently discontinue the agent (not restarted)", "discontinue_all": "stop all protocol therapy",
           "hold": "hold the dose", "delay_cycle": "delay the next cycle", "resume_full": "resume full dose",
           "no_modification": "make no dose modification", "omit_dose": "omit the dose",
           "omit_subsequent_doses": "omit subsequent doses", "give_supportive_care": "give supportive care",
           "obtain_assessment": "obtain", "reduce_percent": "reduce by", "reduce_to_dose": "reduce to", "set_dose": "give",
           "monitor": "monitor", "other": "other action", "none": ""}


def _num(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _unit(u: str | None) -> str:
    return f" {u}" if u and u != "x_reference" else ""


def _q(x: dict | None) -> str:
    return (x or {}).get("text") or ""


def _qty(x: dict | None) -> str:
    if not x or x.get("value") is None:
        return _q(x) if x else ""
    return f"{_num(x['value'])}{_unit(x.get('unit'))}"


def rule(node: dict | None, labels: dict[str, str], depth: int = 0) -> str:
    if node is None:
        return "(always)"
    kind = node.get("node")
    if kind in {"AND", "OR"}:
        joiner = " AND " if kind == "AND" else " OR "
        return "(" + joiner.join(rule(c, labels, depth + 1) for c in node["children"]) + ")"
    if kind == "NOT":
        return "NOT " + rule(node["child"], labels, depth + 1)
    if kind == "IF":
        text = f"IF {rule(node['condition'], labels, depth + 1)} THEN {rule(node['then'], labels, depth + 1)}"
        if node.get("else") is not None:
            text += f" ELSE {rule(node['else'], labels, depth + 1)}"
        return "[" + text + "]"
    name = node.get("subject") or (node.get("canonical") or "").replace("_", " ") or \
        labels.get(node.get("variable") or "", node.get("variable") or "?")
    leaf = node.get("kind")
    status = "" if node.get("status") == "EXECUTABLE" else " {NOT EXECUTABLE}"
    if node.get("event_state"):
        body = f"{name} is {node['event_state']}"
    elif leaf == "compare":
        if node.get("reference"):
            body = f"{name} {OPS.get(node.get('op'), node.get('op'))} {_num(node.get('value'))} times {node['reference']['text']}"
        else:
            body = f"{name} {OPS.get(node.get('op'), node.get('op'))} {_num(node.get('value'))}{_unit(node.get('unit'))}"
    elif leaf == "range":
        parts = []
        if node.get("lower") is not None:
            parts.append(f"{'at least' if node.get('lower_inclusive', True) else 'greater than'} {_num(node['lower'])}")
        if node.get("upper") is not None:
            parts.append(f"{'at most' if node.get('upper_inclusive', True) else 'less than'} {_num(node['upper'])}")
        body = f"{name} " + " and ".join(parts) + _unit(node.get("unit"))
    elif leaf == "category":
        values = ", ".join(repr(c) for c in node.get("categories") or [])
        body = f"{name} is {'one of' if node.get('op') == 'in' else 'none of'} [{values}]"
    elif leaf == "flag":
        body = f"{name} is {'present' if node.get('expected') else 'absent'}"
    elif leaf == "window":
        body = window(node, name)
    elif leaf == "table":
        rows = "; ".join(f"if {rule(r['when'], labels, depth + 1)} then {_num(r['value'])}" for r in node.get("rows") or [])
        body = f"{name} {OPS.get(node.get('op'), node.get('op'))} a threshold{_unit(node.get('unit'))} looked up from a table: {rows}"
    else:
        body = f"UNRESOLVED requirement: {node.get('text')!r}"
    if node.get("timing"):
        body += f" [assessed: {node['timing']['text']}]"
    if node.get("qualifier"):
        body += f" [qualifier: {node['qualifier']}]"
    if node.get("derived_from_definition"):
        body += f" [grade derived from protocol definition {node['derived_from_definition']}]"
    return body + status


def window(node: dict, name: str) -> str:
    off = node.get("offset") or {}
    amount = f"{_num(off['value'])} {off.get('unit') or ''}".strip() if off.get("value") is not None else ""
    phrase = RELATIONS.get(node.get("relation") or "", "relative to").format(v=amount)
    event = (node.get("anchor_event") or "").replace("_", " ")
    quote = node.get("anchor") or ""
    anchor = f"{event} (protocol wording: {quote!r})" if event and quote and event.casefold() != quote.casefold() else (event or quote or "?")
    return f"{name} occurs {phrase} {anchor}{CALENDAR.get(node.get('calendar_adjustment') or '', '')}"


KIND_PREFIX = {"inclusion": "ELIGIBLE ONLY IF", "exclusion": "EXCLUDED IF", "timing": "TIMING REQUIREMENT"}


def criterion(c: dict, labels: dict[str, str]) -> str:
    if c.get("logic") is None and c.get("reclassified_from"):
        return (f"NOT A PATIENT ELIGIBILITY RULE: recorded as an informational {c['kind']} (previously compiled as "
                f"{c['reclassified_from']}), i.e. this text does not by itself decide which patients may enrol: {_q(c.get('evidence'))!r}")
    return f"{MODAL.get(c.get('modality', 'REQUIRED'), '')}{KIND_PREFIX.get(c['kind'], c['kind'].upper())}: {rule(c.get('logic'), labels)}"


def intervention(it: dict, phases: dict[str, str], labels: dict[str, str]) -> str:
    d = it["dose"]
    parts = [f"{MODAL.get(it.get('modality', 'REQUIRED'), '')}phase {phases.get(it.get('phase_id') or '', '?')!r}",
             f"arms {[_q(a) for a in it['arms']] or 'all'}", f"agent {_q(it.get('agent'))!r} ({it.get('category')})",
             f"dose {_num(d['value']) if d['value'] is not None else '?'} {d['unit'] or ''} ({d['basis']})"]
    for opt in it.get("administration_options") or []:
        text = f"route option {_q(opt.get('route'))!r}"
        if (opt.get("duration") or {}).get("value") is not None:
            text += f" over {_qty(opt['duration'])}"
        if opt.get("institutional_policy"):
            text += f" per {_q(opt['institutional_policy'])!r}"
        parts.append(text)
    s = it["schedule"]
    if s.get("days"):
        parts.append(f"on days {s['days']}")
    if s.get("weeks"):
        parts.append(f"in weeks {s['weeks']}")
    if s.get("frequency"):
        parts.append(f"frequency {_q(s['frequency'])!r}")
    if s.get("dose_count") is not None:
        parts.append(f"{_num(s['dose_count'])} doses in total")
    if (it.get("max_dose") or {}).get("value") is not None:
        parts.append(f"maximum {_qty(it['max_dose'])} (protocol wording: {_q(it['max_dose'].get('text'))!r})")
    if (it.get("rounding") or {}).get("text"):
        parts.append(f"rounding {_q(it['rounding']['text'])!r}")
    for link in it.get("linked_events") or []:
        lo, hi = _qty(link.get("min_offset")), _qty(link.get("max_offset"))
        span = f"{lo}-{hi} " if lo and hi else f"at least {lo} " if lo else f"at most {hi} " if hi else ""
        text = f"given {span}{link['relation'].lower().replace('_', ' ')} {link.get('canonical_prerequisite', '').replace('_', ' ')}"
        if link.get("applies_to_days"):
            text = f"on day(s) {link['applies_to_days']} only: {text}"
        elif (link.get("applies_to_days_text") or {}).get("text"):
            text = f"only {_q(link['applies_to_days_text'])!r}: {text}"
        if link["if_prerequisite_not_given"] != "NOT_STATED":
            when = _q(link.get("not_given_circumstance"))
            text += (f"; if that is not given{f' ({when})' if when else ''}: "
                     f"{link['if_prerequisite_not_given'].lower().replace('_', ' ')}")
        parts.append(text)
    for r in it.get("schedule_rules") or []:
        parts.append(f"WHEN {rule(r.get('condition'), labels)} give on {r.get('weekdays') or _q(r.get('administer_days'))}"
                     + (f" ({_q(r.get('timing'))})" if r.get("timing") else ""))
    if (it.get("min_duration") or {}).get("value") is not None:
        parts.append(f"for at least {_qty(it['min_duration'])}")
    if it.get("stop_condition"):
        parts.append(f"until {rule(it['stop_condition']['logic'], labels)}")
    if it.get("condition"):
        parts.append(f"only when {rule(it['condition']['logic'], labels)}")
    if it.get("alternative_to"):
        parts.append(f"interchangeable alternative to {_q(it['alternative_to'])!r}")
    return "; ".join(parts)


def radiotherapy_course(c: dict) -> str:
    parts = [f"radiotherapy course for arms {[_q(a) for a in c['arms']] or 'all'}"]
    if c.get("overall_fraction_count") is not None:
        parts.append(f"{_num(c['overall_fraction_count'])} fractions in the whole course")
    if (c.get("fraction_dose") or {}).get("value") is not None:
        parts.append(f"{_qty(c['fraction_dose'])} per fraction")
    if c.get("fractions_per_week") is not None:
        parts.append(f"{_num(c['fractions_per_week'])} fractions per week")
    return "; ".join(parts)


def radiotherapy_target(c: dict, t: dict, labels: dict[str, str]) -> str:
    parts = [f"target {_q(t.get('name'))!r} ({t['role']})", f"dose {_qty(t.get('total_dose'))}"
             + (" cumulative (includes earlier fields)" if t.get("cumulative") else "")]
    if (t.get("boost_dose") or {}).get("value") is not None:
        parts.append(f"boost of {_qty(t['boost_dose'])} on top of earlier fields")
    if (t.get("fraction_dose") or {}).get("value") is not None:
        parts.append(f"{_qty(t['fraction_dose'])} per fraction")
    if t.get("fraction_count") is not None:
        parts.append(f"{_num(t['fraction_count'])} fractions for this target")
    if t.get("allowed_volumes"):
        parts.append(f"volumes {[_q(v) for v in t['allowed_volumes']]}")
    if t.get("condition"):
        parts.append(f"only for patients with {rule(t['condition'], labels)}")
    return f"[{radiotherapy_course(c)}] " + "; ".join(parts)


def dose_modification(m: dict, labels: dict[str, str]) -> str:
    text = f"{MODAL.get(m.get('modality', 'REQUIRED'), '')}agent {_q(m.get('agent'))!r}"
    if m.get("category"):
        text += f" [{_q(m['category'])}]"
    text += f": WHEN {rule(m.get('trigger'), labels)}"
    for s in m.get("steps") or []:
        a = s["action"]
        modal = MODAL.get(s.get("modality") or "REQUIRED", "").strip()
        step = f" -> step {s['order']} {s['step_type']}{' ' + modal if modal else ''}"
        if s.get("condition"):
            step += f" if {rule(s['condition'], labels)}"
        verb = ACTIONS.get(a["type"], a["type"])
        if a["type"] == "obtain_assessment":
            step += f": obtain {_q(s.get('assessment'))!r}"
        elif verb:
            step += f": {verb}"
        if a.get("value") is not None and a["type"] not in {"give_supportive_care", "obtain_assessment"}:
            step += f" {_num(a['value'])}{a['unit'] or ''}"
        if a.get("reduction_percent") is not None:
            step += f" (a {_num(a['reduction_percent'])}% reduction)"
        if (a.get("max_dose") or {}).get("value") is not None:
            step += f" (maximum {_qty(a['max_dose'])})"
        if s.get("instruction"):
            step += f" ({_q(s['instruction'])})"
        if s.get("frequency"):
            step += f" {_q(s['frequency'])}"
        if (s.get("duration") or {}).get("value") is not None:
            step += f" for {_qty(s['duration'])}"
        if s.get("scope"):
            step += f" [applies to: {_q(s['scope'])}]"
        text += step
    return text


def phase(p: dict, labels: dict[str, str]) -> str:
    parts = [f"phase {_q(p.get('name'))!r} (order {p['sequence_number']})", f"arms {[_q(a) for a in p['arms']] or 'all'}"]
    for f in ("duration", "cycle_length"):
        if (p.get(f) or {}).get("value") is not None:
            parts.append(f"{f.replace('_', ' ')} {_qty(p[f])}")
    if (p.get("cycle_count") or {}).get("value") is not None:
        parts.append(f"{_num(p['cycle_count']['value'])} cycles")
    if (p.get("cycle_start_day") or {}).get("value") is not None:
        parts.append(f"next cycle starts on day {_num(p['cycle_start_day']['value'])}")
    if (p.get("max_delay") or {}).get("value") is not None:
        parts.append(f"may be delayed up to {_qty(p['max_delay'])}")
    if p.get("start_condition") and p["start_condition"].get("logic"):
        parts.append(f"starts only when {rule(p['start_condition']['logic'], labels)}")
    return "; ".join(parts)


def endpoint(e: dict) -> str:
    parts = [f"{e['role']} endpoint {_q(e.get('name'))!r} ({e['type']})"]
    if e.get("events"):
        parts.append("events: " + "; ".join(_q(x) for x in e["events"] if x))
    origin = _q(e.get("time_origin"))
    if origin:
        parts.append(f"time origin: {origin!r}" + (f" ({e['time_origin_derivation']})" if e.get("time_origin_derivation") else ""))
    else:
        parts.append("time origin: not stated in the protocol" if e.get("time_origin_unresolved_in_source") else "time origin: missing")
    cens = "; ".join(_q(x) for x in e.get("censoring") or [] if x)
    if cens:
        parts.append(f"censoring: {cens}")
    else:
        parts.append("censoring: not stated in the protocol" if e.get("censoring_unresolved_in_source") else "censoring: missing")
    return "; ".join(parts)


def analysis(a: dict) -> str:
    parts = [f"{'primary ' if a.get('primary') else ''}analysis of {_q(a.get('endpoint'))!r}: {a['test_family']} ({a['sidedness']})"]
    if a["alpha"].get("value") is not None:
        parts.append(f"alpha {a['alpha']['value']}")
    if a["power"].get("value") is not None:
        wording = _q(a["power"].get("text"))
        parts.append(f"power {a['power']['value']}" + (f" (protocol wording: {wording!r})" if wording else ""))
    if a.get("stratification"):
        parts.append("stratified by " + "; ".join(_q(x) for x in a["stratification"] if x))
    if a.get("effects"):
        parts.append("assumed effects: " + "; ".join(_q(x) for x in a["effects"] if x))
    for sc_ in a.get("scenarios") or []:
        parts.append(f"scenario: power {sc_.get('power')} to detect {_q(sc_.get('effect'))!r}"
                     + (f" assuming {_q(sc_.get('assumption'))!r}" if sc_.get("assumption") else ""))
    if a.get("population"):
        parts.append(f"population {_q(a['population'])!r}")
    if a.get("multiplicity"):
        parts.append(f"multiplicity {_q(a['multiplicity'])!r}")
    return "; ".join(parts)
