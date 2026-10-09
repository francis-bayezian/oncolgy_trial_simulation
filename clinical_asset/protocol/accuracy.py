"""Extraction accuracy of one compiled StudySpec (any protocol): every extracted item with the verifiers' verdict.

The target is 100%: every item that carries a protocol rule is judged FAITHFUL to the PDF by the verifier votes.
Counted separately:
  * INCOMPLETE / INCORRECT / NOT_A_RULE: the extraction is wrong or partial (a failure to fix);
  * UNVERIFIED: no verdict was recorded (the item was never checked: a failure of the check, not proof of accuracy);
  * UNRESOLVED_IN_SOURCE: the protocol itself does not state it (a gap in the source, not an extraction error);
  * informational items carry no rule and are not scored.
"""

import json
from collections import Counter
from pathlib import Path

NOT_SCORED = {"NON_EXECUTABLE_INFORMATIONAL"}
SECTIONS = ("eligibility", "interventions", "treatment_phases", "dose_modifications", "decision_rules", "analyses", "endpoints",
            "stratification", "sample_size", "discontinuation_rules", "assessments", "radiotherapy")


def _items(spec: dict):
    for sec in SECTIONS:
        val = spec.get(sec)
        if isinstance(val, dict):                     # stratification holds its strata in a list
            val = val.get("strata")
        for it in val or []:
            if not isinstance(it, dict):
                continue
            if sec == "assessments":                 # a schedule is scored by its rows, each one item
                for row in it.get("assessments") or []:
                    yield sec, row
            else:
                yield sec, it


def _id(it: dict) -> str:
    return next((str(it[k]) for k in it if k.endswith("_id") and isinstance(it[k], str)), "?")


def verdict(it: dict) -> str:
    if it.get("status") in NOT_SCORED:
        return "NOT_SCORED"
    if it.get("status") == "UNRESOLVED_IN_SOURCE":
        return "UNRESOLVED_IN_SOURCE"
    v = it.get("semantic_status") or (it.get("verification") or {}).get("verdict")
    if v:
        return v
    return "FAITHFUL" if it.get("status") == "EXECUTABLE" and it.get("verification") else "UNVERIFIED"


def report(spec_dir: Path) -> dict:
    spec = json.loads((Path(spec_dir) / "studyspec.json").read_text(encoding="utf-8"))
    rows = []
    for sec, it in _items(spec):
        v = verdict(it)
        ver = it.get("verification") or {}
        rows.append({"section": sec, "item": _id(it), "status": it.get("status"), "criticality": it.get("criticality"), "verdict": v,
                     "votes": ver.get("votes"), "problem": ver.get("problem"), "note": ver.get("reviewer_note"),
                     "protocol_wording": ver.get("problem_quote"), "rendering": (it.get("rendering") or "")[:300],
                     "repaired": bool(it.get("repair"))})
    scored = [r for r in rows if r["verdict"] not in ("NOT_SCORED", "UNRESOLVED_IN_SOURCE")]
    faithful = sum(r["verdict"] == "FAITHFUL" for r in scored)
    by_sec = {}
    for sec in SECTIONS:
        rs = [r for r in scored if r["section"] == sec]
        if rs:
            by_sec[sec] = {"items": len(rs), "faithful": sum(r["verdict"] == "FAITHFUL" for r in rs),
                           "verdicts": dict(Counter(r["verdict"] for r in rs))}
    return {"spec": str(spec_dir), "items_scored": len(scored), "faithful": faithful,
            "accuracy": round(faithful / len(scored), 4) if scored else None, "target_met": bool(scored) and faithful == len(scored),
            "verdicts": dict(Counter(r["verdict"] for r in rows)), "by_section": by_sec,
            "failures": [r for r in scored if r["verdict"] != "FAITHFUL"]}


def write(spec_dir: Path, out_dir: Path) -> dict:
    doc = report(spec_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "extraction_accuracy.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    L = [f"# Extraction accuracy: {doc['spec']}", "",
         f"**{doc['faithful']} of {doc['items_scored']} rule items judged FAITHFUL ({(doc['accuracy'] or 0):.1%})"
         f"; target 100%: {'MET' if doc['target_met'] else 'NOT MET'}.**", "",
         f"All verdicts: {doc['verdicts']}", "", "| Section | Items | Faithful | Verdicts |", "| --- | ---: | ---: | --- |"]
    L += [f"| {s} | {v['items']} | {v['faithful']} | {v['verdicts']} |" for s, v in doc["by_section"].items()]
    L += ["", "## Items not faithful", ""]
    for r in doc["failures"]:
        L.append(f"- **{r['item']}** ({r['section']}, {r['criticality']}, {r['verdict']}{', repaired' if r['repaired'] else ''}): "
                 f"{r['note'] or 'no verifier note'}" + (f" — protocol: \"{r['protocol_wording']}\"" if r["protocol_wording"] else ""))
    (out / "extraction_accuracy.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return doc
