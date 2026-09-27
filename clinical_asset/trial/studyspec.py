"""The locked StudySpec: the only form in which the simulation stages read a protocol."""

import json
from pathlib import Path

from . import lock

SPEC_FILES = ["studyspec.json", "audit.json", "review_required.json", "validation_report.json", "studyspec_review.md"]
DOWNSTREAM_POLICY = (
    "Items whose status is not EXECUTABLE are listed under 'not_executable'. Simulation stages never evaluate them as "
    "written. A stage that needs one reports it as unresolved in its own output (it is never replaced by an assumption); "
    "source gaps (UNRESOLVED_IN_SOURCE) are facts the protocol does not state and are handled the same way."
)


def _items(spec: dict):
    yield from (("eligibility", x, x["criterion_id"]) for x in spec["eligibility"])
    yield from (("stratification", x, x["stratum_id"]) for x in spec["stratification"]["strata"])
    yield from (("treatment_phases", x, x["phase_id"]) for x in spec["treatment_phases"])
    yield from (("interventions", x, x["intervention_id"]) for x in spec["interventions"])
    yield from (("radiotherapy", t, t["target_id"]) for c in spec["radiotherapy"] for t in c["targets"])
    yield from (("dose_modifications", x, x["rule_id"]) for x in spec["dose_modifications"])
    yield from (("endpoints", x, x["endpoint_id"]) for x in spec["endpoints"])
    yield from (("analyses", x, x["analysis_id"]) for x in spec["analyses"])


def lock_studyspec(spec_dir: Path, lock_dir: Path, protocol_pdf: Path, version: str = "1.0.0") -> dict:
    spec = json.loads((Path(spec_dir) / "studyspec.json").read_text(encoding="utf-8"))
    not_executable = [{"component": comp, "item": iid, "criticality": x.get("criticality"), "status": x.get("status"),
                       "semantic_status": x.get("semantic_status"), "runtime_status": x.get("runtime_status"),
                       "reviewer_note": (x.get("verification") or {}).get("reviewer_note")}
                      for comp, x, iid in _items(spec) if x.get("status") != "EXECUTABLE"]
    status = {"gate": spec["gate"]["result"], "failed_conditions": spec["gate"]["failed_conditions"],
              "source_gaps": spec["gate"]["source_gaps"],
              "critical_items": spec["gate"]["critical_items"],
              "critical_executable_and_faithful": spec["gate"]["critical_executable_and_faithful"],
              "compiler_version": spec["compiler_version"], "spec_version": spec["spec_version"],
              "not_executable": not_executable, "downstream_policy": DOWNSTREAM_POLICY}
    return lock.lock(spec_dir, lock_dir, "studyspec", version, {"protocol_pdf": protocol_pdf},
                     [Path("clinical_asset/protocol")], status, SPEC_FILES)


def load_studyspec(lock_dir: Path) -> tuple[dict, dict]:
    """(StudySpec, lock record) after verifying every checksum."""
    record = lock.verify(lock_dir)
    return lock.load_locked(lock_dir, "studyspec.json"), record


FACT_FILES = ["population_facts.json", "audit.json", "facts_review.md"]


def lock_facts(facts_dir: Path, lock_dir: Path, protocol_pdf: Path, version: str = "1.0.0") -> dict:
    """Lock the quantitative protocol facts. Only facts with status USABLE may be used downstream."""
    facts = json.loads((Path(facts_dir) / "population_facts.json").read_text(encoding="utf-8"))
    status = {"facts_version": facts["facts_version"], **facts["summary"],
              "downstream_policy": "Only facts with status USABLE are used; REVIEW_REQUIRED facts are never used."}
    return lock.lock(facts_dir, lock_dir, "protocol_facts", version, {"protocol_pdf": protocol_pdf},
                     [Path("clinical_asset/protocol")], status, FACT_FILES)


def load_facts(lock_dir: Path) -> tuple[list[dict], dict]:
    """(USABLE facts, lock record) after verifying every checksum."""
    record = lock.verify(lock_dir)
    facts = lock.load_locked(lock_dir, "population_facts.json")["facts"]
    return [f for f in facts if f["status"] == "USABLE"], record
