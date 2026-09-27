"""Deterministic in-place repair passes over stored clinical profiles (no re-extraction).

Every change is recorded as a repair entry so the QA table shows what was altered and why.
"""

import copy
import json
import re
from typing import Any

from .qa import NON_OUTCOME_TYPES, SCHEMA_VERSION, TOP_LEVEL
from .terminology import (
    DRUG_TYPES,
    FINDING_TYPES,
    GENE_TYPES,
    NEOPLASM_TYPES,
    VARIANT_TYPES,
    Terminology,
    concept_mentions,
)

AGE = re.compile(r"(?:age[ds]?\s*)?(?P<op>≥|>=|<=|≤|<|>|older than|younger than|over|under)\s*(?P<n>\d{2})\s*(?:years?|y)?", re.IGNORECASE)
AGE_OPS = {"≥": ">=", ">=": ">=", "over": ">", "older than": ">", ">": ">", "≤": "<=", "<=": "<=", "<": "<", "under": "<", "younger than": "<"}
SEX = re.compile(r"\b(female|male|women|men)\b", re.IGNORECASE)
SUBGROUP_TYPES = FINDING_TYPES | NEOPLASM_TYPES | GENE_TYPES | VARIANT_TYPES | DRUG_TYPES
CLINICAL_SECTIONS = ("efficacy", "toxicity", "treatment_course", "comparisons", "mortality_observations", "patient_profile")


def structure_subgroup(definition: str, terminology: Terminology) -> dict[str, Any]:
    """'patients with liver metastases aged ≥65 years' -> criteria concepts, age and sex."""
    result: dict[str, Any] = {"definition": definition}
    spans = concept_mentions(definition, terminology, SUBGROUP_TYPES)
    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    chosen: list[tuple[int, int, Any]] = []
    for span in spans:
        if all(span[1] <= c[0] or span[0] >= c[1] for c in chosen):
            chosen.append(span)
    criteria = [
        {"concept": c.name, "umls_cui": c.cui, "text": definition[s:e]}
        for s, e, c in sorted(chosen, key=lambda x: x[0])
    ]
    if criteria:
        result["criteria"] = criteria
    if age := AGE.search(definition):
        result["age"] = {"operator": AGE_OPS[age.group("op").casefold()], "years": int(age.group("n"))}
    if sex := SEX.search(definition):
        result["sex"] = "female" if sex.group(1).casefold() in {"female", "women"} else "male"
    return result


def repair_profile(profile: dict, types_of, terminology: Terminology | None) -> tuple[dict, list[dict]]:
    fixed = copy.deepcopy(profile)
    log: list[dict] = []

    def note(code: str, path: str, detail: Any = None) -> None:
        log.append({"repair": code, "path": path, **({"detail": detail} if detail is not None else {})})

    for section in set(fixed) - TOP_LEVEL:
        fixed.pop(section)
        note("DROP_UNKNOWN_SECTION", section)
    # --- UMLS mappings with the wrong semantic type are removed, never guessed
    for key, observations in fixed.get("efficacy", {}).items():
        for obs in observations:
            cui = obs.get("umls_cui")
            if cui and set(types_of(cui)) & NON_OUTCOME_TYPES:
                obs.pop("umls_cui")
                note("DROP_WRONG_TYPE_OUTCOME_CUI", f"efficacy.{key}", cui)
            if obs.get("rate") is not None and not 0 <= obs["rate"] <= 1:
                note("DROP_OUT_OF_RANGE_RATE", f"efficacy.{key}", obs.pop("rate"))
        unique, seen = [], set()
        for obs in observations:
            fingerprint = json.dumps(obs, sort_keys=True)
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique.append(obs)
        if len(unique) != len(observations):
            note("DEDUPE_OBSERVATIONS", f"efficacy.{key}", len(observations) - len(unique))
            fixed["efficacy"][key] = unique
    cancer = fixed.get("cancer", {})
    if cancer.get("disease") and not set(types_of(cancer["disease"]["umls_cui"])) & NEOPLASM_TYPES:
        note("DROP_NON_NEOPLASM_DISEASE", "cancer.disease", cancer.pop("disease"))
    if cancer.get("biomarkers"):
        keep = [m for m in cancer["biomarkers"] if set(types_of(m["umls_cui"])) & (VARIANT_TYPES | GENE_TYPES)]
        if len(keep) != len(cancer["biomarkers"]):
            note("DROP_WRONG_TYPE_BIOMARKER", "cancer.biomarkers")
            cancer["biomarkers"] = keep
    ontology = fixed.get("treatment_ontology", {})
    if ontology.get("umls_cui") and not set(types_of(ontology["umls_cui"])) & DRUG_TYPES:
        note("DROP_WRONG_TYPE_DRUG_CUI", "treatment_ontology", ontology.pop("umls_cui"))
    for section in ("key_events", "key_serious_events"):
        for key, event in list(fixed.get("toxicity", {}).get(section, {}).items()):
            if event.get("umls_cui") and set(types_of(event["umls_cui"])) & (DRUG_TYPES | GENE_TYPES):
                note("DROP_WRONG_TYPE_EVENT_CUI", f"toxicity.{section}.{key}", event.pop("umls_cui"))
    # --- comparisons: no self comparisons, no duplicates
    comparisons, seen = [], set()
    own = fixed.get("source", {}).get("registry_group")
    for comparison in fixed.get("comparisons", []):
        if comparison.get("comparator_group") and comparison["comparator_group"] == own:
            note("DROP_SELF_COMPARISON", "comparisons", comparison.get("outcome"))
            continue
        fingerprint = json.dumps({k: comparison.get(k) for k in ("comparator_group", "comparator", "outcome", "measure", "value")}, sort_keys=True)
        if fingerprint in seen:
            note("DEDUPE_COMPARISON", "comparisons", comparison.get("outcome"))
            continue
        seen.add(fingerprint)
        comparisons.append(comparison)
    if "comparisons" in fixed:
        fixed["comparisons"] = comparisons
        if not comparisons:
            fixed.pop("comparisons")
    # --- regimen name
    treatment = fixed.get("treatment", {})
    if treatment.get("interventions"):
        names = list(dict.fromkeys(str(x).strip().casefold() for x in treatment["interventions"] if str(x).strip()))
        treatment["interventions"] = names
        treatment["regimen"] = " + ".join(names)
    elif treatment.get("drug"):
        treatment["drug"] = str(treatment["drug"]).strip().casefold()
        treatment["regimen"] = treatment["drug"]
    elif treatment.get("arm_type") == "no_intervention":
        treatment["regimen"] = "no intervention"
    # --- structured subgroup definition
    if fixed.get("definition") and terminology is not None and "subgroup" not in fixed.get("patient_profile", {}):
        fixed.setdefault("patient_profile", {})["subgroup"] = structure_subgroup(fixed["definition"], terminology)
        note("STRUCTURE_SUBGROUP", "patient_profile.subgroup")
    return fixed, log


def repair_asset(asset: dict, nct: str, types_of, terminology: Terminology | None) -> tuple[dict, list[dict]]:
    repaired: list[dict] = []
    log: list[dict] = []
    for i, profile in enumerate(asset.get("clinical_profiles", [])):
        fixed, entries = repair_profile(profile, types_of, terminology)
        fixed = {"profile_id": f"{nct}-{i:02d}", **fixed}
        if not any(fixed.get(section) for section in CLINICAL_SECTIONS):
            # No observed clinical content: noise for the asset, kept only in the repair log.
            log.append({"profile_id": fixed["profile_id"], "repair": "DROP_PROFILE_WITHOUT_CLINICAL_CONTENT",
                        "path": "", "detail": fixed.get("source", {}).get("registry_group")})
            continue
        repaired.append(fixed)
        log.extend({"profile_id": fixed["profile_id"], **e} for e in entries)
    return {"schema_version": SCHEMA_VERSION, "clinical_profiles": repaired}, log
