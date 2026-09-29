"""Write the prediction record of a blind or temporal trial from its locked artefacts only, BEFORE its registry results
are read: the key predictions, each lock's hash, and the time of recording. The scoring step later reads this record,
never the working directories.

usage: python scripts/record_locked_predictions.py STUDY VERSION
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("studyspec", "population", "eligibility", "cohorts", "outcomes", "results", "planning", "safety", "outputs", "journey")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main(study: str, version: str) -> None:
    L = Path("data/locked") / study
    locks = {s: _sha(L / f"{s}_v{version}" / "lock.json") for s in STAGES if (L / f"{s}_v{version}" / "lock.json").exists()}
    rec = {"study": study, "version": version, "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "registry_results_read_before_recording": False, "lock_sha256": locks}

    ni = _load(L / f"results_v{version}" / "ni_results.json")
    if ni:
        rec["efficacy"] = {k: ni.get(k) for k in ("evidence_prior", "predicted_response", "power_at_protocol_assumption", "p_success_curve",
                                                  "p_success_basis")}
        rec["efficacy"]["design"] = {k: ni["design"].get(k) for k in ("fraction", "alpha", "n_per_arm", "control_phrase", "comparator")}
    plan = _load(L / f"planning_v{version}" / "planning_report.json")
    if plan:
        a = plan["accrual"]
        h, f = a.get("historical_model") or {}, a.get("failure_model") or {}
        rec["planning"] = {"target_patients": a.get("target_patients"), "stated_operational": a.get("stated_operational"),
                           "patients_per_month": h.get("patients_per_month"), "enrollment_duration_years": h.get("enrollment_duration_years"),
                           "site_count_basis": h.get("site_count"), "failure_probabilities": f.get("probabilities"),
                           "sponsor_basis": f.get("sponsor_class")}
    saf = _load(L / f"safety_v{version}" / "safety_results.json")
    if saf:
        rec["safety"] = {a["arm_id"]: {"label": a.get("label"), "enrolled": a.get("enrolled"),
                                       "events": [{k: e.get(k) for k in ("term", "seriousness", "rate_median", "simulated_affected")}
                                                  for e in a.get("events") or []]} for a in saf["arms"]}
    jour = _load(L / f"journey_v{version}" / "journey_summary.json")
    if jour:
        rec["journey"] = {k: jour.get(k) for k in ("summary", "progression", "withdrawal") if k in jour}
    out = Path("data/validation") / f"{study}_predictions_v{version}.json"
    if out.exists():
        sys.exit(f"{out} exists: a prediction record is written once")
    out.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(out, _sha(out))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
