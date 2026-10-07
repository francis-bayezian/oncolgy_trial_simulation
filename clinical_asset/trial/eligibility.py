"""Milestone 6: eligibility of the screened population (eligibility-2.0.0, general for any protocol).

Every inclusion and exclusion requirement of the StudySpec is applied to every generated patient; none is skipped:

* criteria with compiled logic are evaluated three-valued (met, not met, unknown); logic still under review is run as
  compiled and listed under `run_with_review_flag`;
* criteria that only time trial procedures (timing:, event:, count:, calendar:) are met by the simulated schedule;
* optional policies are permissions and are not enforced; informational items are not requirements;
* a criterion a generated patient cannot answer (laboratory values, history, disease details no evidence source gives
  per patient) is resolved by calibration to the registry screen pass rate of the protocol's disease family and phase
  (resolve_unknowns, assumption A16), so every patient ends ELIGIBLE or INELIGIBLE (lesson L026: before, 0 of 10,000
  patients were ever proven eligible in any of nine protocols).
"""

import json
from pathlib import Path

from ..protocol import expressions as ex
from ..protocol.ir import DETERMINISTIC_MODALITIES, SIMULATOR_VARIABLE_PREFIXES
from .run_forward import use_compiled_logic

ELIGIBILITY_VERSION = "eligibility-2.0.0"


INFORMATIONAL_STATUSES = {"NON_EXECUTABLE_INFORMATIONAL"}


def classify_criteria(spec: dict) -> dict[str, list[dict]]:
    """Criteria by how they are treated (eligibility-2.0.0, run forward: a requirement is never skipped):
    evaluated (compiled logic, EXECUTABLE or run as compiled with its review flag), procedural (met by the simulated
    schedule), permissive (optional policies), informational (not a requirement). A requirement with no usable logic is
    evaluated as wholly unknown and resolved with the other unknowns (resolve_unknowns)."""
    out: dict[str, list[dict]] = {"evaluated": [], "procedural": [], "permissive": [], "informational": [], "run_with_review_flag": []}
    for c in spec["eligibility"]:
        if c["kind"] not in {"inclusion", "exclusion", "timing"} or c.get("status") in INFORMATIONAL_STATUSES:
            out["informational"].append(c)
        elif c.get("status") == "OPTIONAL_POLICY" or c.get("modality", "REQUIRED") not in DETERMINISTIC_MODALITIES:
            out["permissive"].append(c)
        elif c["kind"] == "timing" or _procedural(c.get("logic")):
            out["procedural"].append(c)
        else:
            out["evaluated"].append(c)
            if c.get("status") != "EXECUTABLE":
                out["run_with_review_flag"].append(c)
    return out


def _procedural(tree: dict | None) -> bool:
    variables = [leaf.get("variable") or "" for leaf in ex.leaves(tree)]
    return bool(variables) and all(v.startswith(SIMULATOR_VARIABLE_PREFIXES) for v in variables)


def evaluate_patient(criteria: list[dict], patient: dict) -> dict:
    """{'status', 'failed': [...], 'unknown': [...]} for one patient."""
    failed, unknown = [], []
    for c in criteria:
        try:                                           # an item the verifiers judged incorrect is unknown (run_forward)
            r = ex.evaluate(c.get("logic"), patient) if c.get("logic") and use_compiled_logic(c) else None
        except Exception:  # noqa: BLE001 - logic a review flagged may be malformed: it is then unknown, and resolved
            r = None
        ok = r if c["kind"] == "inclusion" else (None if r is None else not r)
        if ok is False:
            failed.append(c["criterion_id"])
        elif ok is None:
            unknown.append(c["criterion_id"])
    status = "INELIGIBLE" if failed else "UNDETERMINED" if unknown else "ELIGIBLE"
    return {"status": status, "failed": failed, "unknown": unknown}


MIN_RESIDUAL_PASS = 0.02


def resolve_unknowns(results: list[dict], screen_pass: dict, seed: int) -> dict:
    """Decide every criterion a generated patient cannot answer (assumption A16, general for any protocol).

    The registry screen pass rate P of trials of the protocol's disease family and phase (evidence) is the target share
    of screened patients who are eligible. The criteria decided from generated variables already exclude a share F;
    the unknown criteria must jointly pass r = P / (1 - F) (capped to [MIN_RESIDUAL_PASS, 1]); each of the k criteria
    that are unknown for some patient passes independently with q = r^(1/k). A patient's unknown criterion is then met
    with probability q (seeded per patient and criterion), so every patient ends ELIGIBLE or INELIGIBLE."""
    import numpy as np

    n = len(results) or 1
    unknown_ids = sorted({c for r in results for c in r["unknown"]})
    target = screen_pass.get("value")
    decided_fail = sum(bool(r["failed"]) for r in results) / n
    if not unknown_ids:
        return {"status": "NOT_NEEDED", "criteria": []}
    if target is None:
        target = 1.0 - decided_fail                       # no screening evidence at all: unknowns do not exclude further
    r_needed = min(1.0, max(MIN_RESIDUAL_PASS, target / max(1e-9, 1.0 - decided_fail)))
    q = r_needed ** (1.0 / len(unknown_ids))
    rng = np.random.default_rng(seed)
    for r in results:
        r["resolved"] = {}
        for cid in r["unknown"]:
            met = bool(rng.random() < q)
            r["resolved"][cid] = "met" if met else "not_met"
            if not met:
                r["failed"].append(cid)
        r["unknown"] = []
        r["status"] = "INELIGIBLE" if r["failed"] else "ELIGIBLE"
    return {"status": "RESOLVED", "assumption": "A16_unknown_criteria_calibrated", "screen_pass_rate": screen_pass,
            "target_eligible_share": target, "share_excluded_by_decided_criteria": decided_fail,
            "residual_pass_needed": r_needed, "per_criterion_pass_probability": q, "criteria": unknown_ids}


def screening_evidence(spec: dict) -> dict:
    """The registry screen pass rate for the protocol's disease family and phase (journey evidence)."""
    from .journey_evidence import registry_phase, screen_pass_rate
    from .population import protocol_query

    try:
        family = protocol_query(spec).disease_family
    except Exception:  # noqa: BLE001 - no condition mapping: the all-oncology pool is used
        family = None
    return screen_pass_rate(family, registry_phase(spec))


def assess(spec: dict, patients: list[dict], screen_pass: dict | None = None, seed: int = 20261005) -> tuple[list[dict], dict]:
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
    blocking = _decisive(results, "unknown")
    resolution = resolve_unknowns(results, screen_pass if screen_pass is not None else {"value": None}, seed)
    counts = {s: sum(r["status"] == s for r in results) for s in ("ELIGIBLE", "UNDETERMINED", "INELIGIBLE")}
    labels = {c["criterion_id"]: c.get("rendering") or "" for c in spec["eligibility"]}
    summary = {
        "patients": n, "status_counts": counts,
        "eligible_share": counts["ELIGIBLE"] / n if n else None,
        "proven_eligible_share": counts["ELIGIBLE"] / n if n else None,
        "not_proven_ineligible_share": (counts["ELIGIBLE"] + counts["UNDETERMINED"]) / n if n else None,
        "criteria": {name: [c["criterion_id"] for c in group] for name, group in groups.items()},
        "per_criterion": {cid: {**v, "share_not_met_decided": v["not_met"] / n if n else None, "rule": labels[cid][:300]} for cid, v in per.items()},
        "decisive_exclusions": _decisive(results, "failed"),
        "plausibility_warnings": _whole_group_exclusions(patients, results),
        "criteria_resolved_by_calibration": blocking,
        "unknown_resolution": resolution,
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


def build_eligibility(spec_lock: Path, population_lock: Path, out_dir: Path, seed: int = 20261005) -> dict:
    from .lock import verify
    from .studyspec import load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    pop_record = verify(population_lock)
    with open(Path(population_lock) / "population.jsonl", encoding="utf-8") as fh:
        patients = [json.loads(line) for line in fh]
    results, summary = assess(spec, patients, screening_evidence(spec), seed=seed)
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
             (f"{s['patients']} screened patients: {c['ELIGIBLE']} eligible, {c['INELIGIBLE']} ineligible."), "",
             f"Eligible share of the screened population: {s['eligible_share']:.1%}.", "",
             "## How each criterion is treated", ""]
    for name, ids in s["criteria"].items():
        lines.append(f"- {name} ({len(ids)}): {', '.join(ids)}")
    if s["plausibility_warnings"]:
        lines += ["", "## PLAUSIBILITY WARNINGS", ""] + [f"- {w}" for w in s["plausibility_warnings"]]
    lines += ["", "## Criteria that exclude patients", ""]
    for cid, k in s["decisive_exclusions"].items():
        lines.append(f"- {cid}: {k} patients ({k / s['patients']:.1%}) - {(rules[cid].get('rendering') or '')[:220]}")
    res = s["unknown_resolution"]
    lines += ["", "## Criteria resolved by calibration to the registry screen pass rate (A16)", ""]
    if res.get("status") == "RESOLVED":
        lines.append(f"Target eligible share {res['target_eligible_share']:.1%} ({res['screen_pass_rate'].get('source', 'no evidence')}); "
                     f"decided criteria exclude {res['share_excluded_by_decided_criteria']:.1%}; each of {len(res['criteria'])} "
                     f"unanswerable criteria passes with probability {res['per_criterion_pass_probability']:.3f}.")
    for cid, k in s["criteria_resolved_by_calibration"].items():
        lines.append(f"- {cid}: unanswerable for {k} patients - {(rules[cid].get('rendering') or '')[:220]}")
    return "\n".join(lines) + "\n"
