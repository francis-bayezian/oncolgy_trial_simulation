"""Human-readable review report of a compiled StudySpec (Markdown).

Every compiled item is shown in plain language with its criticality, its semantic status (does it
say what the protocol says?), its runtime status (can a simulator run it?), the page of its source
wording and the independent verifier's note. The acceptance gate and any facts the protocol does
not state are listed first.
"""

from typing import Any

from . import render


def _q(x: dict | None) -> str:
    return render._q(x)


def _page(item: dict, prov: dict[str, dict]) -> str:
    for key in ("evidence", "label", "name", "agent", "criterion"):
        value = item.get(key)
        ref = value.get("provenance") if isinstance(value, dict) else None
        if ref and prov.get(ref, {}).get("page"):
            return f"p.{prov[ref]['page']}"
    return "p.?"


def _tags(item: dict) -> str:
    return (f"[{item.get('status', '-')}] {item.get('criticality', '-')}; semantic {item.get('semantic_status', '-')}; "
            f"runtime {item.get('runtime_status', '-')}")


def _notes(item: dict) -> list[str]:
    out = []
    v = item.get("verification") or {}
    if v and v.get("verdict") not in {None, "FAITHFUL"}:
        text = f"verifier: {v.get('verdict')} - {v.get('reviewer_note') or v.get('reason') or ''}"
        if v.get("problem_quote"):
            text += f" (protocol: \"{v['problem_quote'].strip()[:200]}\")"
        out.append(text)
    for issue in item.get("static_issues") or []:
        out.append(f"static check: {issue}")
    return out


def build(spec: dict, audit: dict, review: list[dict], validation: dict) -> str:
    prov = {p["id"]: p for p in audit["provenance"]}
    labels = {v["key"]: v["label"] for v in spec["variables"]}
    phases = {p["phase_id"]: _q(p.get("name")) for p in spec["treatment_phases"]}
    meta = spec["metadata"]
    gate = validation["gate"]
    out: list[str] = []
    add = out.append

    def item(line: str, it: dict) -> None:
        add(line)
        for note in _notes(it):
            add(f"  - {note}")

    add(f"# StudySpec review: {_q(meta.get('protocol_id')) or 'protocol'}")
    add("")
    add(_q(meta.get("title")))
    add("")
    add(f"Version date: {_q(meta.get('version_date')) or 'not stated'}. Amendment: {_q(meta.get('amendment')) or 'not stated'}. "
        f"Compiler {spec['compiler_version']}, StudySpec {spec['spec_version']}. Source: protocol PDF only.")
    add("")
    add(f"## Acceptance gate: **{gate['result']}**")
    add("")
    add(gate["rule"] + ".")
    add("")
    add(f"Critical items executable and faithful: {gate['critical_executable_and_faithful']} of {gate['critical_items']}.")
    add("")
    for name, ids in gate["failed_conditions"].items():
        add(f"- FAILED {name.replace('_', ' ')}: {', '.join(map(str, ids))[:400]}")
    if gate["source_gaps"]:
        add(f"- Not stated in the protocol: {', '.join(gate['source_gaps'])}")
    add("")
    add("Status meanings: semantic FAITHFUL / INCOMPLETE / INCORRECT / UNVERIFIED (independent verifier and quote checks); "
        "runtime EXECUTABLE_NOW, EXECUTABLE_AFTER_VARIABLE_AVAILABLE (valid rule on a patient variable the population "
        "model does not simulate yet), OPTIONAL_POLICY (may/should), UNSUPPORTED_RULE_TYPE, UNRESOLVED_IN_SOURCE, "
        "NON_EXECUTABLE_INFORMATIONAL.")
    add("")
    tc = spec.get("treatment_completion") or {}
    if tc.get("gaps_before"):
        add("## Treatment completeness")
        add(f"The first extraction missed administrations; {tc['passes']} completeness pass(es) re-read the treatment sections.")
        for g in tc["gaps_before"]:
            add(f"- found missing: {g.removeprefix('treatment incomplete: ')}")
        for g in tc.get("gaps_after") or []:
            add(f"- STILL MISSING after completion: {g.removeprefix('treatment incomplete: ')}")
        if not tc.get("gaps_after"):
            add("- all gaps recovered")
        add("")
    if spec.get("resolutions"):
        add("## Facts resolved from the protocol text")
        for r in spec["resolutions"]:
            add(f"- {r['question_id']}: {r['status']}" + (f" - {_q(r.get('answer') or r.get('evidence'))!r}" if r["status"] != "NOT_STATED" else "")
                + (f" -> {r['canonical_value']}" if r.get("canonical_value") else ""))
        add("")
    add("## Arms and randomization")
    for a in spec["arms"]:
        add(f"- {a['arm_id']} {_q(a['label'])}: {a['status']}")
    rz = spec["randomization"]
    alloc = rz.get("allocation")
    add(f"- allocation: {alloc['ratio'] if alloc else ('not stated in the protocol' if rz.get('allocation_unresolved_in_source') else 'missing')}"
        + (f" ({alloc.get('derivation', 'STATED')})" if alloc else ""))
    for st in spec["stratification"]["strata"]:
        item(f"- **{st['stratum_id']}** {_tags(st)}: {_q(st.get('label'))}: {render.rule(st.get('logic'), labels)}", st)
    add("")
    add("## Eligibility")
    for c in spec["eligibility"]:
        body = render.criterion(c, labels) if c.get("logic") is not None else f"{c['kind']}: {_q(c.get('evidence'))}"
        item(f"- **{c['criterion_id']}** {_tags(c)} {_page(c, prov)}: {body}", c)
    add("")
    add("## Treatment phases")
    for p in spec["treatment_phases"]:
        item(f"- **{p['phase_id']}** {_tags(p)} {_page(p, prov)}: {render.phase(p, labels)}", p)
    add("")
    add("## Interventions")
    for it in spec["interventions"]:
        item(f"- **{it['intervention_id']}** {_tags(it)} {_page(it, prov)}: {render.intervention(it, phases, labels)}", it)
    add("")
    add("## Radiotherapy")
    for course in spec["radiotherapy"]:
        add(f"- **{course['course_id']}** {render.radiotherapy_course(course)}")
        for t in course["targets"]:
            item(f"  - **{t['target_id']}** {_tags(t)}: {render.radiotherapy_target(course, t, labels).split('] ', 1)[-1]}", t)
    add("")
    add("## Dose-modification workflows")
    for m in spec["dose_modifications"]:
        item(f"- **{m['rule_id']}** {_tags(m)} {_page(m, prov)}: {render.dose_modification(m, labels)}", m)
    add("")
    add("## Protocol-defined grades")
    for g in spec["grade_definitions"]:
        add(f"- **{g['scale_id']}** {_q(g.get('system'))} ({g['canonical_concept']})")
        for lv in g["levels"]:
            add(f"  - {_q(lv.get('level'))}: {render.rule(lv.get('criteria'), labels) if lv.get('criteria') else _q(lv.get('definition'))}")
    add("")
    add("## Endpoints, analyses and monitoring")
    for e in spec["endpoints"]:
        item(f"- **{e['endpoint_id']}** {_tags(e)}: {render.endpoint(e)}", e)
    for a in spec["analyses"]:
        add(f"- **{a['analysis_id']}** {'PRIMARY ' if a.get('primary') else ''}{a['test_family']} ({a['sidedness']}) for "
            f"{_q(a.get('endpoint'))}: alpha {a['alpha']['value']}, power {a['power']['value']}")
    for i in spec["interim_analyses"]:
        mon = i.get("monitor") or {}
        params = {k: v for k, v in mon.items() if k not in {"missing", "runtime_status"}}
        item(f"- **{i['interim_id']}** {i['purpose']} [{i['status']}] runtime {i.get('runtime_status')}: {params}"
             + (f" missing {mon.get('missing')}" if mon.get("missing") else ""), i)
    add("")
    add("## Discontinuation")
    for d in spec["discontinuation_rules"]:
        add(f"- **{d['rule_id']}** {d['scope']} / {d['trigger']}: {_q(d.get('criterion'))}")
    add("")
    add("## Review list")
    add("")
    add("| Component | Item | Reason |")
    add("| --- | --- | --- |")
    for r in review:
        reason = str(r["reason"]).replace("|", "/").replace("\n", " ")[:300]
        add(f"| {r['component']} | {r['item']} | {reason} |")
    add("")
    add("## Validation checks")
    for c in validation["checks"]:
        add(f"- [{'pass' if c['pass'] else 'FAIL'}]{' (critical)' if c['critical'] else ''} {c['check']}: {_short(c['detail'])}")
    return "\n".join(out) + "\n"


def _short(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 200 else text[:200] + "..."
