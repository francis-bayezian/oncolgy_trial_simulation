"""Completeness audit of one protocol run (any protocol): the run is COMPLETE only when every stage is locked, every
patient is decided, and no stage output carries an UNRESOLVED, UNDETERMINED, PENDING or ERROR status.

StudySpec items still flagged by the verifiers (REVIEW_REQUIRED) are not failures by themselves: they are run as
compiled and counted, so the report shows how much of the run rests on flagged extraction. Endpoints the generated
patients cannot carry are NOT_SIMULATED by design and are counted separately.
"""

import json
from collections import Counter
from pathlib import Path

LOCK = Path("data/locked")
STAGES = ("studyspec", "protocol_facts", "population", "eligibility", "cohorts", "outcomes", "results", "planning", "safety",
          "outputs", "journey", "endpoints", "analysis")
FAILING = {"UNRESOLVED", "UNDETERMINED", "PENDING", "ERROR", "UNSUPPORTED"}


def _statuses(o, path: str, out: list) -> None:
    if isinstance(o, dict):
        st = o.get("status")
        if isinstance(st, str) and st.upper() in FAILING:
            out.append({"path": path, "status": st, "reason": str(o.get("reason") or o.get("source") or "")[:200]})
        for k, v in o.items():
            _statuses(v, f"{path}/{k}", out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _statuses(v, f"{path}[{i}]", out)


def audit(study: str, version: str, out_dir: Path) -> dict:
    from ..agent import critic

    base = LOCK / study
    stages, problems, flagged = {}, [], Counter()
    for stage in STAGES:
        d = base / f"{stage}_v{version}"
        if not d.exists() and stage == "protocol_facts":       # a run may reuse an earlier facts lock
            d = max(base.glob("protocol_facts_v*"), default=d, key=lambda x: tuple(int(v) for v in x.name.rsplit("_v", 1)[1].split(".")))
        if not d.exists():
            stages[stage] = "MISSING"
            problems.append({"path": stage, "status": "MISSING", "reason": f"{d} not locked"})
            continue
        stages[stage] = "LOCKED"
        if stage in ("studyspec", "protocol_facts"):
            if stage == "studyspec":
                spec = json.loads((d / "studyspec.json").read_text(encoding="utf-8"))
                for sec, items in spec.items():
                    if isinstance(items, list):
                        flagged.update(f"{sec}:{x.get('status')}" for x in items if isinstance(x, dict) and x.get("status") not in (None, "EXECUTABLE"))
            continue
        for f in sorted(d.glob("*.json")):
            if f.name != "lock.json":
                _statuses(json.loads(f.read_text(encoding="utf-8")), f"{stage}/{f.name}", problems)
    el = base / f"eligibility_v{version}" / "eligibility_summary.json"
    if el.exists():
        und = json.loads(el.read_text(encoding="utf-8"))["summary"]["status_counts"].get("UNDETERMINED", 0)
        if und:
            problems.append({"path": "eligibility", "status": "UNDETERMINED", "reason": f"{und} patients undetermined"})
    ep = base / f"endpoints_v{version}" / "endpoint_results.json"
    counts = json.loads(ep.read_text(encoding="utf-8"))["counts"] if ep.exists() else {}
    critic_errors = [f for f in critic.review(study) if f["severity"] == "error"]
    problems += [{"path": f"critic/{f['check']}", "status": "ERROR", "reason": f["message"]} for f in critic_errors]
    summary = {"study": study, "version": version, "complete": not problems, "problems": len(problems),
               "stages": stages, "endpoint_classes": counts,
               "studyspec_items_run_with_review_flag": sum(v for k, v in flagged.items() if k.endswith("REVIEW_REQUIRED"))}
    doc = {"summary": summary, "problems": problems, "studyspec_flags": dict(flagged)}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "completeness.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Completeness audit: {study} v{version}", "", f"**{'COMPLETE' if summary['complete'] else 'INCOMPLETE'}**: {len(problems)} problems.", "",
             "| Stage | State |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in stages.items()]
    lines += ["", f"Endpoint classes: {counts}", f"StudySpec items run with a review flag: {summary['studyspec_items_run_with_review_flag']}", "",
              "## Problems", ""] + [f"- {p['status']} {p['path']}: {p['reason']}" for p in problems[:200]]
    (out / "completeness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc
