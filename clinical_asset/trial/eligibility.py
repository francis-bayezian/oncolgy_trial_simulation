"""Milestone 6: eligibility and feasibility of the source population.

Every EXECUTABLE eligibility criterion of the locked StudySpec is evaluated three-valued (met, not met,
unknown) for every patient of the locked source population:

* An inclusion criterion must be met and an exclusion criterion must not be met. A patient is INELIGIBLE
  when any of them is decided against the patient, ELIGIBLE when all are decided in the patient's favour,
  and UNDETERMINED otherwise.
* Criteria whose status is not EXECUTABLE (incorrect, unresolved, informational) are never evaluated;
  OPTIONAL / RECOMMENDED criteria are permissions, not requirements, and are not enforced.
* Criteria that constrain only the timing of trial procedures (their variables belong to the simulator:
  timing:, event:, count:, calendar:) are PROCEDURAL: they are met by the simulated schedule, which
  carries out screening and procedures inside the protocol windows (milestone 9), and are not patient
  characteristics.

Feasibility is reported as bounds: the share proven eligible and the share not proven ineligible. The
enrollable pool for recruitment is every patient not proven ineligible, each with the list of criteria
that could not be checked; nothing unknown about a patient is filled in.
"""

import json
from pathlib import Path

from ..protocol import expressions as ex
from ..protocol.ir import DETERMINISTIC_MODALITIES, SIMULATOR_VARIABLE_PREFIXES

ELIGIBILITY_VERSION = "eligibility-1.0.0"


def classify_criteria(spec: dict) -> dict[str, list[dict]]:
    """Criteria by how they are treated: evaluated, procedural, permissive, not executable, informational."""
    out: dict[str, list[dict]] = {"evaluated": [], "procedural": [], "permissive": [], "not_executable": [], "informational": []}
    for c in spec["eligibility"]:
        if c["kind"] not in {"inclusion", "exclusion", "timing"}:
            out["informational"].append(c)
        elif c.get("status") != "EXECUTABLE":
            (out["permissive"] if c.get("status") == "OPTIONAL_POLICY" else out["not_executable"]).append(c)
        elif c.get("modality", "REQUIRED") not in DETERMINISTIC_MODALITIES:
            out["permissive"].append(c)
        elif c["kind"] == "timing" or _procedural(c.get("logic")):
            out["procedural"].append(c)
        else:
            out["evaluated"].append(c)
    return out


def _procedural(tree: dict | None) -> bool:
    variables = [leaf.get("variable") or "" for leaf in ex.leaves(tree)]
    return bool(variables) and all(v.startswith(SIMULATOR_VARIABLE_PREFIXES) for v in variables)


def evaluate_patient(criteria: list[dict], patient: dict) -> dict:
    """{'status', 'failed': [...], 'unknown': [...]} for one patient."""
    failed, unknown = [], []
    for c in criteria:
        r = ex.evaluate(c.get("logic"), patient)
        ok = r if c["kind"] == "inclusion" else (None if r is None else not r)
        if ok is False:
            failed.append(c["criterion_id"])
        elif ok is None:
            unknown.append(c["criterion_id"])
    status = "INELIGIBLE" if failed else "UNDETERMINED" if unknown else "ELIGIBLE"
    return {"status": status, "failed": failed, "unknown": unknown}


def assess(spec: dict, patients: list[dict]) -> tuple[list[dict], dict]:
    groups = classify_criteria(spec)
    criteria = groups["evaluated"]
    results = []
    per = {c["criterion_id"]: {"met": 0, "not_met": 0, "unknown": 0} for c in criteria}
    for p in patients:
        r = evaluate_patient(criteria, p)
        results.append({"patient_id": p["patient_id"], **r})
        for cid, tally in per.items():
            tally["not_met" if cid in r["failed"] else "unknown" if cid in r["unknown"] else "met"] += 1
    n = len(patients)
    counts = {s: sum(r["status"] == s for r in results) for s in ("ELIGIBLE", "UNDETERMINED", "INELIGIBLE")}
    labels = {c["criterion_id"]: c.get("rendering") or "" for c in spec["eligibility"]}
    summary = {
        "patients": n, "status_counts": counts,
        "proven_eligible_share": counts["ELIGIBLE"] / n if n else None,
        "not_proven_ineligible_share": (counts["ELIGIBLE"] + counts["UNDETERMINED"]) / n if n else None,
        "criteria": {name: [c["criterion_id"] for c in group] for name, group in groups.items()},
        "per_criterion": {cid: {**v, "share_not_met": v["not_met"] / n if n else None, "rule": labels[cid][:300]} for cid, v in per.items()},
        "decisive_exclusions": _decisive(results, "failed"),
        "plausibility_warnings": _whole_group_exclusions(patients, results),
        "blocking_unknowns": _decisive(results, "unknown"),
    }
    return results, summary


DEMOGRAPHIC_GROUPS = ("demographic:sex", "demographic:race", "demographic:ethnicity")


def _whole_group_exclusions(patients: list[dict], results: list[dict]) -> list[str]:
    """A criterion that rejects every patient of one demographic group while admitting others is almost always a
    compilation error (a subgroup requirement compiled as unconditional); it is reported, never silently used."""
    warnings = []
    for var in DEMOGRAPHIC_GROUPS:
        groups: dict[str, list[dict]] = {}
        for p, r in zip(patients, results, strict=True):
            if p.get(var) is not None:
                groups.setdefault(str(p[var]), []).append(r)
        for cid in sorted({c for r in results for c in r["failed"]}):
            fails = {g: all(cid in r["failed"] for r in rs) for g, rs in groups.items() if len(rs) >= 20}
            if any(fails.values()) and not all(fails.values()):
                excluded = sorted(g for g, f in fails.items() if f)
                warnings.append(f"{cid} excludes every patient with {var} in {excluded}: check that it is not a subgroup "
                                "requirement compiled as unconditional")
    return warnings


def _decisive(results: list[dict], field: str) -> dict:
    counts: dict[str, int] = {}
    for r in results:
        for cid in r[field]:
            counts[cid] = counts.get(cid, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def build_eligibility(spec_lock: Path, population_lock: Path, out_dir: Path) -> dict:
    from .lock import verify
    from .studyspec import load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    pop_record = verify(population_lock)
    with open(Path(population_lock) / "population.jsonl", encoding="utf-8") as fh:
        patients = [json.loads(line) for line in fh]
    results, summary = assess(spec, patients)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"eligibility_version": ELIGIBILITY_VERSION,
           "inputs": {"studyspec": spec_record["files"]["studyspec.json"], "population": pop_record["files"]["population.jsonl"]},
           "summary": summary}
    (out_dir / "eligibility_summary.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(out_dir / "eligibility.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in results)
    (out_dir / "feasibility_report.md").write_text(_report(doc, spec), encoding="utf-8")
    return summary


def _report(doc: dict, spec: dict) -> str:
    s = doc["summary"]
    rules = {c["criterion_id"]: c for c in spec["eligibility"]}
    c = s["status_counts"]
    lines = [f"# Eligibility and feasibility ({doc['eligibility_version']})", "",
             (f"{s['patients']} source-population patients: {c['ELIGIBLE']} proven eligible, {c['UNDETERMINED']} undetermined, "
              f"{c['INELIGIBLE']} proven ineligible."), "",
             (f"Feasibility bounds: between {s['proven_eligible_share']:.1%} (proven eligible) and "
              f"{s['not_proven_ineligible_share']:.1%} (not proven ineligible) of the source population can enroll. The gap is "
              "made of criteria whose patient variables no source states."), "",
             "## How each criterion is treated", ""]
    for name, ids in s["criteria"].items():
        lines.append(f"- {name} ({len(ids)}): {', '.join(ids)}")
    if s["plausibility_warnings"]:
        lines += ["", "## PLAUSIBILITY WARNINGS", ""] + [f"- {w}" for w in s["plausibility_warnings"]]
    lines += ["", "## Criteria that exclude patients", ""]
    for cid, k in s["decisive_exclusions"].items():
        lines.append(f"- {cid}: {k} patients ({k / s['patients']:.1%}) - {(rules[cid].get('rendering') or '')[:220]}")
    lines += ["", "## Criteria that cannot be checked (unknown patient data)", ""]
    for cid, k in s["blocking_unknowns"].items():
        lines.append(f"- {cid}: unknown for {k} patients - {(rules[cid].get('rendering') or '')[:220]}")
    return "\n".join(lines) + "\n"
