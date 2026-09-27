"""Integrity checks over every clinical profile.

Each issue has a code, a severity and an action:

* ``reprocess`` - the stored profile lost information that only the source can restore;
* ``repair``    - a deterministic in-place fix exists (see repair.py);
* ``flag``      - kept, but recorded in the QA table for review.
"""

import json
import re
from pathlib import Path
from typing import Any

from .source_text import NEGATED_METASTATIC
from .terminology import DRUG_TYPES, GENE_TYPES, NEOPLASM_TYPES, VARIANT_TYPES
from .umls_index import UmlsIndex

SCHEMA_VERSION = "1.0.0"
TOP_LEVEL = {
    "profile_id", "profile_type", "definition", "cancer", "treatment", "treatment_ontology", "patient_profile",
    "selection_context", "efficacy", "toxicity", "treatment_course", "comparisons",
    "mortality_observations", "source",
}
PROFILE_TYPES = {"randomized_arm", "study_arm", "result_group", "treatment_sequence", "reported_subgroup"}
NON_OUTCOME_TYPES = GENE_TYPES | DRUG_TYPES | VARIANT_TYPES


def _issue(code: str, severity: str, action: str, path: str, detail: Any = None) -> dict:
    return {"code": code, "severity": severity, "action": action, "path": path,
            **({"detail": detail} if detail is not None else {})}


def check_profile(profile: dict, index: int, raw: dict | None, types_of) -> list[dict]:
    issues: list[dict] = []
    here = f"clinical_profiles[{index}]"
    # --- frozen schema
    unknown = set(profile) - TOP_LEVEL
    if unknown:
        issues.append(_issue("SCHEMA_UNKNOWN_SECTION", "error", "repair", here, sorted(unknown)))
    if profile.get("profile_type") not in PROFILE_TYPES:
        issues.append(_issue("SCHEMA_PROFILE_TYPE", "error", "reprocess", here, profile.get("profile_type")))
    efficacy = profile.get("efficacy", {})
    if any(not isinstance(v, list) for v in efficacy.values()):
        issues.append(_issue("SCHEMA_PRE_V1_EFFICACY", "error", "reprocess", f"{here}.efficacy"))
        return issues  # the rest of the checks assume v1 observation lists
    for key in efficacy:
        # A collapsed duplicate ("x_3" next to "x"), not a title that ends in a number ("day_364").
        base = re.sub(r"_\d+$", "", key)
        if base != key and base in efficacy:
            issues.append(_issue("OUTCOME_KEY_SUFFIX", "error", "reprocess", f"{here}.efficacy.{key}"))
    # --- observations
    profile_n = profile.get("patient_profile", {}).get("n")
    for key, observations in efficacy.items():
        for j, obs in enumerate(observations):
            path = f"{here}.efficacy.{key}[{j}]"
            if not isinstance(obs.get("value"), (int, float)):
                issues.append(_issue("OBS_VALUE_NOT_NUMERIC", "error", "repair", path, obs.get("value")))
            if "statistic" not in obs:
                issues.append(_issue("OBS_NO_STATISTIC", "error", "repair", path))
            rate = obs.get("rate")
            if rate is not None and not 0 <= rate <= 1:
                issues.append(_issue("OBS_RATE_OUT_OF_RANGE", "error", "repair", path, rate))
            n_obs = obs.get("N")
            if (
                n_obs and profile_n and n_obs > profile_n
                and not obs.get("population") and not obs.get("population_scope")
            ):
                issues.append(_issue("OBS_N_EXCEEDS_PROFILE_N", "warning", "flag", path, [n_obs, profile_n]))
            cui = obs.get("umls_cui")
            if cui and set(types_of(cui)) & NON_OUTCOME_TYPES:
                issues.append(_issue("UMLS_OUTCOME_WRONG_TYPE", "error", "repair", path, cui))
            if "interval" in obs:
                issues.append(_issue("OBS_INTERVAL_TYPE_UNKNOWN", "info", "flag", path, obs.get("interval_type")))
        if len({json.dumps(o, sort_keys=True) for o in observations}) != len(observations):
            issues.append(_issue("OBS_DUPLICATE", "warning", "repair", f"{here}.efficacy.{key}"))
    # --- toxicity
    toxicity = profile.get("toxicity", {})
    for section in ("key_events", "key_serious_events"):
        for key, event in toxicity.get(section, {}).items():
            if not 0 <= event.get("rate", 0) <= 1:
                issues.append(_issue("TOX_RATE_OUT_OF_RANGE", "error", "repair", f"{here}.toxicity.{section}.{key}"))
            denominator = event.get("N") or toxicity.get("N")
            if denominator and event.get("n") is not None and abs(event["n"] / denominator - event.get("rate", 0)) > 0.0006:
                issues.append(_issue("TOX_DENOMINATOR_MISSING", "error", "reprocess", f"{here}.toxicity.{section}.{key}"))
            if event.get("N") is not None and event.get("N") == event.get("n") and event["n"] > 0:
                issues.append(_issue("TOX_AT_RISK_EQUALS_AFFECTED", "info", "flag", f"{here}.toxicity.{section}.{key}"))
            if event.get("umls_cui") and set(types_of(event["umls_cui"])) & (DRUG_TYPES | GENE_TYPES):
                issues.append(_issue("UMLS_EVENT_WRONG_TYPE", "error", "repair", f"{here}.toxicity.{section}.{key}", event["umls_cui"]))
    # --- comparisons
    seen = set()
    for j, comparison in enumerate(profile.get("comparisons", [])):
        path = f"{here}.comparisons[{j}]"
        if not comparison.get("comparator") or not comparison.get("outcome") or comparison.get("value") is None:
            issues.append(_issue("COMPARISON_INCOMPLETE", "error", "flag", path))
        own = profile.get("source", {}).get("registry_group")
        if comparison.get("comparator_group") and comparison.get("comparator_group") == own:
            issues.append(_issue("COMPARISON_SELF", "error", "repair", path))
        fingerprint = json.dumps({k: comparison.get(k) for k in ("comparator_group", "comparator", "outcome", "measure", "value")}, sort_keys=True)
        if fingerprint in seen:
            issues.append(_issue("COMPARISON_DUPLICATE", "warning", "repair", path))
        seen.add(fingerprint)
    # --- cancer, biomarkers, drugs
    cancer = profile.get("cancer", {})
    disease = cancer.get("disease")
    if not disease:
        issues.append(_issue("CANCER_NO_DISEASE", "warning", "flag", f"{here}.cancer"))
    elif not set(types_of(disease["umls_cui"])) & NEOPLASM_TYPES:
        issues.append(_issue("UMLS_DISEASE_NOT_NEOPLASM", "error", "repair", f"{here}.cancer.disease", disease["umls_cui"]))
    for j, marker in enumerate(cancer.get("biomarkers", [])):
        if not set(types_of(marker["umls_cui"])) & (VARIANT_TYPES | GENE_TYPES):
            issues.append(_issue("UMLS_BIOMARKER_WRONG_TYPE", "error", "repair", f"{here}.cancer.biomarkers[{j}]", marker["umls_cui"]))
    if raw is not None and cancer.get("setting") == "metastatic":
        protocol = raw.get("protocolSection", {})
        text = " ".join([
            *protocol.get("conditionsModule", {}).get("conditions", []),
            str(protocol.get("eligibilityModule", {}).get("eligibilityCriteria") or "").split("Exclusion")[0],
        ])
        if NEGATED_METASTATIC.search(text):
            issues.append(_issue("SETTING_CONTRADICTS_SOURCE", "error", "reprocess", f"{here}.cancer.setting",
                                  NEGATED_METASTATIC.search(text).group(0)))
    treatment = profile.get("treatment", {})
    if not treatment.get("drug") and not treatment.get("interventions") and treatment.get("arm_type") != "no_intervention":
        issues.append(_issue("TREATMENT_MISSING", "warning", "flag", f"{here}.treatment"))
    ontology = profile.get("treatment_ontology", {})
    if ontology.get("umls_cui") and not set(types_of(ontology["umls_cui"])) & DRUG_TYPES:
        issues.append(_issue("UMLS_DRUG_WRONG_TYPE", "error", "repair", f"{here}.treatment_ontology", ontology["umls_cui"]))
    # --- emptiness
    clinical = {"efficacy", "toxicity", "treatment_course", "comparisons", "mortality_observations", "patient_profile"}
    if not clinical & {k for k, v in profile.items() if v}:
        issues.append(_issue("PROFILE_NO_CLINICAL_CONTENT", "warning", "flag", here))
    return issues


def check_corpus(asset_dir: Path, raw_dir: Path, holdout: set[str], ids: list[str], index: UmlsIndex) -> dict[str, list[dict]]:
    cache: dict[str, list[str]] = {}

    def types_of(cui: str) -> list[str]:
        if cui not in cache:
            entity = index.entity(cui)
            cache[cui] = entity["types"] if entity else []
        return cache[cui]

    results: dict[str, list[dict]] = {}
    for nct in ids:
        path = asset_dir / f"{nct}.json"
        if not path.exists():
            results[nct] = [_issue("ASSET_MISSING", "error", "reprocess", nct)]
            continue
        issues: list[dict] = []
        if nct in holdout:
            issues.append(_issue("HOLDOUT_TRIAL_PRESENT", "error", "flag", nct))
        asset = json.loads(path.read_text(encoding="utf-8"))
        raw_path = raw_dir / f"{nct}.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else None
        for i, profile in enumerate(asset.get("clinical_profiles", [])):
            issues.extend(check_profile(profile, i, raw, types_of))
        results[nct] = issues
    return results


def summarise(results: dict[str, list[dict]]) -> dict:
    from collections import Counter

    codes = Counter(i["code"] for issues in results.values() for i in issues)
    actions = Counter(i["action"] for issues in results.values() for i in issues)
    reprocess = sorted(n for n, issues in results.items() if any(i["action"] == "reprocess" for i in issues))
    clean = sorted(n for n, issues in results.items() if not any(i["severity"] == "error" for i in issues))
    return {"trials": len(results), "trials_needing_reprocess": len(reprocess), "trials_without_errors": len(clean),
            "issues_by_code": dict(codes.most_common()), "issues_by_action": dict(actions), "reprocess_ids": reprocess}
