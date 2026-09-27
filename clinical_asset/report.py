"""Build the compact clinical asset and, separately, its extraction audit.

The clinical asset holds only observed, attributable clinical facts:

* ``patient_profile``   - what was observed in the patients of this profile
* ``selection_context`` - protocol limits that say where the evidence applies
* ``treatment``         - the exposure actually given
* ``treatment_ontology``- concept identifiers and definition-quoted class and target

Pipeline QA (question coverage, source conflicts, retrieval state, withheld values) goes to
the audit record, never into the asset. No medical vocabulary is written in this module:
keys come from UMLS concepts attached during enrichment.
"""

import re
from typing import Any

from .abstract_evidence import PublicationEvidence, apply_publication_evidence
from .observations import measure_class, observation
from .publications import Publication
from .source_text import grouping_basis, population_label
from .types import ClinicalProfile, ParsedStudy

COMMON_EVENT_MIN_RATE = 0.10
SERIOUS_EVENT_MIN_RATE = 0.02
SERIOUS_EVENT_MIN_N = 2
DIFFERENTIAL_MIN_RATIO = 2.0
DIFFERENTIAL_MIN_DIFFERENCE = 0.05


def _population(description: str | None) -> dict[str, Any]:
    text = description or ""
    result: dict[str, Any] = {}
    if label := population_label(text):
        result["population"] = label
    if basis := grouping_basis(text):
        result["grouping"] = basis
    return result


def _snake(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def _measure(text: str) -> str:
    return _snake(re.sub(r"\s*\([^)]*\)\s*$", "", text))


ARM_TYPES = frozenset({"randomized_arm", "study_arm"})


def _profile_type(profile: ClinicalProfile, parsed: ParsedStudy | None = None) -> str:
    if profile.source_population != "treatment_arm_aggregate":
        return "reported_subgroup"
    if profile.patient_group.get("treatment_history_in_trial"):
        return "treatment_sequence"
    if profile.source_arm.startswith("result group: "):
        return "result_group"
    # Only the registry's allocation field makes an arm randomised.
    return "randomized_arm" if parsed is not None and parsed.allocation == "RANDOMIZED" else "study_arm"


def _conflicted_groups(parsed: ParsedStudy) -> set[str]:
    groups: set[str] = set()
    for conflict in parsed.source_conflicts:
        if conflict.get("topic") == "all_cause_deaths":
            groups.add(conflict["randomized_arm"].casefold())
            groups.update(name.casefold() for name in conflict.get("switched_group", []))
    return groups


# --------------------------------------------------------------------------- asset


def _cancer(profile: ClinicalProfile) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if disease := profile.cancer.get("disease"):
        result["disease"] = {"name": disease["name"], "umls_cui": disease["umls_cui"]}
    if profile.setting:
        result["setting"] = profile.setting
    if markers := profile.patient_group.get("biomarkers"):
        result["biomarkers"] = [
            {"gene": m["gene"], "variant": m["variant"], "umls_cui": m["umls_cui"]} for m in markers
        ]
    return result


def _treatment(profile: ClinicalProfile) -> tuple[dict[str, Any], dict[str, Any]]:
    given = profile.treatment
    treatment: dict[str, Any] = {}
    if given.get("drug"):
        treatment["drug"] = given["drug"]
        if given.get("reported_name") and given["reported_name"].casefold() != given["drug"].casefold():
            treatment["reported_name"] = given["reported_name"]
    elif given.get("interventions"):
        treatment["interventions"] = given["interventions"]
        treatment["combination"] = True
    if dose := given.get("dose"):
        treatment["dose"] = dose["value"]
        treatment["dose_unit"] = dose["unit"]
    for key in ("route", "frequency", "cycle_length_days", "arm_type"):
        if given.get(key) is not None:
            treatment[key] = given[key]
    return treatment, dict(given.get("ontology") or {})


def _patient_profile(profile: ClinicalProfile) -> dict[str, Any]:
    patient = profile.patient_group
    result: dict[str, Any] = {}
    measures = profile.baseline.get("measures", [])
    if patient.get("n_basis") in {"reported_baseline", "safety_at_risk"}:
        result["n"] = patient["n"]
    if measures:
        result.update(_population(measures[0].get("analysis_population")))
    if age := patient.get("age"):
        result["age"] = {
            "mean": age["mean"],
            **({"sd": age["standard_deviation"]} if "standard_deviation" in age else {}),
            "unit": "year",
        }
    for key in ("sex", "race", "ethnicity"):
        values = patient.get(key)
        if isinstance(values, dict):
            result[key] = {_snake(name): item["n"] for name, item in values.items()}
    if isinstance(patient.get("sex"), str):
        result["sex"] = {_snake(patient["sex"]): "all"}
    if history := patient.get("treatment_history_in_trial"):
        result["prior_treatment_in_trial"] = history
    return result


def _selection_context(profile: ClinicalProfile) -> dict[str, Any]:
    limits = profile.patient_group.get("eligibility") or {}
    result: dict[str, Any] = {}
    if "age_min_years" in limits or "age_max_years" in limits:
        result["age_allowed_years"] = [limits.get("age_min_years"), limits.get("age_max_years")]
    if status := limits.get("performance_status"):
        result[f"{status['scale']}_allowed"] = status["allowed"]
    for key in ("prior_systemic_therapy", "disease_extent", "biomarker_confirmation"):
        if limits.get(key):
            result[key] = limits[key]
    for key in ("required", "required_prior_therapy", "excluded"):
        if limits.get(key):
            result[key] = limits[key]
    return result


def _measures(profile: ClinicalProfile) -> tuple[dict[str, list], dict[str, list], list[dict]]:
    """Registry outcome measures as observation lists, routed by measure class:
    efficacy -> efficacy; safety -> toxicity.registry_safety_outcomes; pharmacokinetic -> audit only."""
    efficacy: dict[str, list] = {}
    safety: dict[str, list] = {}
    excluded: list[dict] = []
    for section in ("response", "survival"):
        for item in getattr(profile, section).get("outcomes", []):
            key = item.get("key") or _snake(item["measure"])
            kind = measure_class(str(item["measure"]), item.get("unit"))
            if kind == "pharmacokinetic":
                excluded.append({"registry_group": profile.source_arm, "measure": item["measure"], "reason": "pharmacokinetic"})
                continue
            obs = observation(item, _population(item.get("analysis_population")))
            if item.get("umls_cui"):
                obs["umls_cui"] = item["umls_cui"]
            target = safety if kind == "safety" else efficacy
            if obs not in target.setdefault(key, []):
                target[key].append(obs)
    return efficacy, safety, excluded


def _efficacy(profile: ClinicalProfile) -> dict[str, list]:
    return _measures(profile)[0]


def _comparator_rates(profile: ClinicalProfile, parsed: ParsedStudy, source: str) -> dict[str, float]:
    """Event rates in the other randomised arm(s), for the differential rule."""
    if _profile_type(profile, parsed) != "randomized_arm":
        return {}
    rates: dict[str, float] = {}
    for other in parsed.profiles:
        if other is profile or _profile_type(other, parsed) != "randomized_arm":
            continue
        for item in other.toxicity.get(source, []):
            rates[item["term"]] = max(rates.get(item["term"], 0.0), item["rate"])
    return rates


def select_key_events(profile: ClinicalProfile, parsed: ParsedStudy) -> dict[str, Any]:
    """Model-relevant events for one profile, chosen from the data alone.

    Kept: common events, serious events above a floor, and events that are markedly more
    frequent than in the comparator arm (treatment-differential). Left out: zero counts and
    events whose concept is a neoplasm (disease progression recorded as an adverse event).
    """
    selected: dict[str, dict[str, Any]] = {"key_events": {}, "key_serious_events": {}}
    for source, target, min_rate, min_n in (
        ("non_serious_terms", "key_events", COMMON_EVENT_MIN_RATE, 1),
        ("serious_terms", "key_serious_events", SERIOUS_EVENT_MIN_RATE, SERIOUS_EVENT_MIN_N),
    ):
        comparator = _comparator_rates(profile, parsed, source)
        for item in sorted(profile.toxicity.get(source, []), key=lambda i: -i["rate"]):
            if item["n"] == 0 or item.get("neoplasm"):
                continue
            other = comparator.get(item["term"])
            differential = (
                other is not None
                and item["rate"] - other >= DIFFERENTIAL_MIN_DIFFERENCE
                and item["rate"] >= DIFFERENTIAL_MIN_RATIO * other
            )
            if differential or (item["n"] >= min_n and item["rate"] >= min_rate):
                key = item.get("key") or _snake(item["term"])
                group_n = (profile.toxicity.get("serious_adverse_events_any_cause") or {}).get("N")
                selected[target][key] = {
                    "n": item["n"],
                    # An event's own at-risk count is kept whenever it differs from the group's.
                    **({"N": item["N"]} if item["N"] != group_n else {}),
                    "rate": round(item["rate"], 4),
                    **({"umls_cui": item["umls_cui"]} if item.get("umls_cui") else {}),
                    **({"higher_than_comparator": True} if differential else {}),
                }
    return {key: value for key, value in selected.items() if value}


def _toxicity(profile: ClinicalProfile, parsed: ParsedStudy) -> dict[str, Any]:
    serious = profile.toxicity.get("serious_adverse_events_any_cause")
    if not serious:
        return {}
    result: dict[str, Any] = {
        "N": serious["N"],
        **{
            key: value
            for key, value in (
                ("population", parsed.safety_reporting.get("adverse_event_population")),
                ("grouping", parsed.safety_reporting.get("grouping")),
            )
            if value
        },
        "any_serious_AE": {"n": serious["n"], "rate": round(serious["rate"], 4)},
    }
    result.update(select_key_events(profile, parsed))
    if safety := _measures(profile)[1]:
        result["registry_safety_outcomes"] = safety
    return result


def _treatment_course(profile: ClinicalProfile, conflicted: bool) -> dict[str, Any]:
    course = profile.treatment_course
    result: dict[str, Any] = {}
    for item in course.get("participant_flow", []):
        milestone = str(item.get("milestone", ""))
        if item["n"] > 0 and re.search(r"switch|crossover|cross over", milestone, re.IGNORECASE):
            result.setdefault("switched_to_other_arm", 0)
            result["switched_to_other_arm"] += item["n"]
    reasons = {
        _snake(str(item["reason"])): item["n"]
        for item in course.get("withdrawal_reasons", [])
        if not (conflicted and str(item["reason"]).casefold() == "death")
    }
    if reasons:
        # Reasons for leaving the study, not for stopping study treatment.
        result["study_status_at_data_cutoff"] = reasons
    return result


def _comparisons(profile: ClinicalProfile) -> list[dict[str, Any]]:
    comparisons = []
    for effect in profile.comparative_effects:
        entry: dict[str, Any] = {
            "comparator": effect.get("comparator_drug", effect["comparator"]),
            "comparator_group": effect["comparator"],
            "outcome": effect.get("outcome_key") or _snake(str(effect["outcome"])),
            "measure": _measure(str(effect["measure"])),
            "value": effect["value"],
        }
        interval = effect.get("confidence_interval")
        if interval:
            label = f"ci{interval['percent']}" if interval.get("percent") else "ci"
            entry[label] = [interval["lower"], interval["upper"]]
        p_value = effect.get("p_value_reported")
        if p_value:
            try:
                entry["p_value"] = float(p_value)
            except ValueError:
                entry["p_value_reported"] = p_value
        if effect.get("method"):
            entry["method"] = effect["method"]
        entry.update(_population(effect.get("analysis_population")))
        comparisons.append(entry)
    return comparisons


def _clinical_profile(
    profile: ClinicalProfile,
    parsed: ParsedStudy,
    publications: list[Publication],
    conflicted: set[str],
) -> dict[str, Any]:
    is_conflicted = profile.source_arm.casefold() in conflicted
    treatment, ontology = _treatment(profile)
    result: dict[str, Any] = {"profile_type": _profile_type(profile, parsed)}
    if profile.source_population != "treatment_arm_aggregate":
        result["definition"] = profile.patient_group.get("definition", profile.source_population)
    for key, value in (
        ("cancer", _cancer(profile)),
        ("treatment", treatment),
        ("treatment_ontology", ontology),
        ("patient_profile", _patient_profile(profile)),
        ("selection_context", _selection_context(profile)),
        ("efficacy", _efficacy(profile)),
        ("toxicity", _toxicity(profile, parsed)),
        ("treatment_course", _treatment_course(profile, is_conflicted)),
        ("comparisons", _comparisons(profile)),
    ):
        if value:
            result[key] = value
    deaths = profile.survival.get("all_cause_deaths_reported")
    if deaths and not is_conflicted:
        # Only reconciled counts enter the asset. A count is not a survival endpoint.
        result["mortality_observations"] = {
            "all_cause_deaths": deaths["n"],
            "at_risk": deaths["at_risk"],
            **(
                {"population": parsed.safety_reporting["mortality_population"]}
                if parsed.safety_reporting.get("mortality_population")
                else {}
            ),
        }
    result["source"] = {
        "nct": parsed.nct_id,
        "registry_group": profile.source_arm,
        "publications": [f"PMID:{p.pmid}" if p.pmid else f"DOI:{p.doi}" for p in publications],
    }
    return result


def build_asset_and_reconciliation(
    parsed: ParsedStudy,
    publications: list[Publication],
    evidence: list[PublicationEvidence] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conflicted = _conflicted_groups(parsed)
    asset = {
        "clinical_profiles": [
            _clinical_profile(profile, parsed, publications, conflicted)
            for profile in parsed.profiles
        ]
    }
    # Linked-publication facts; none when no publication or abstract exists.
    reconciliation = apply_publication_evidence(asset, evidence or [])
    return asset, reconciliation


def build_clinical_asset(
    parsed: ParsedStudy,
    publications: list[Publication],
    evidence: list[PublicationEvidence] | None = None,
) -> dict[str, Any]:
    """Observed clinical facts only. Never infers patient-level associations."""
    return build_asset_and_reconciliation(parsed, publications, evidence)[0]


# --------------------------------------------------------------------------- audit


def _question_coverage(parsed: ParsedStudy, asset: dict[str, Any]) -> dict[str, str]:
    profiles = asset["clinical_profiles"]
    efficacy = [o for p in profiles for obs in p.get("efficacy", {}).values() for o in obs]
    has_rate = any("rate" in e for e in efficacy)
    has_time = any(e.get("statistic") == "median" and e.get("unit") in {"month", "week", "day", "year"} for e in efficacy)
    has_grade = any(k.startswith("grade_") for p in profiles for k in p.get("toxicity", {}))
    return {
        "1_which_patients_exist": "partial: selection context, disease and biomarker concepts"
        if any(p.get("selection_context") for p in profiles)
        else "not_available",
        "2_baseline_characteristics": "partial: marginal demographics per arm only"
        if any(p.baseline for p in parsed.profiles)
        else "not_available",
        "3_correlations_between_characteristics": "not_available: only marginal summaries",
        "4_treatment_response": "available" if has_rate else "no response-rate endpoint found",
        "5_biomarker_lab_tumour_changes": "available"
        if any(p.longitudinal for p in parsed.profiles)
        else "not_available",
        "6_toxicity": "partial: event frequencies" + ("; grade 3 or higher from publication" if has_grade else "; no grade"),
        "7_interruption_reduction_discontinuation": "partial: crossover and study-level withdrawal only",
        "8_progression": "partial: arm-level time-to-event summaries" if has_time else "not_available",
        "9_pfs_os_trajectories": "partial: summary statistics only; no curve" if has_time else "not_available",
    }


def build_audit(
    parsed: ParsedStudy,
    publications: list[Publication],
    evidence: list[PublicationEvidence] | None = None,
    enrichment: dict[str, Any] | None = None,
    model_usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extraction QA and ingestion state. Not part of the clinical asset."""
    conflicted = _conflicted_groups(parsed)
    asset, reconciliation = build_asset_and_reconciliation(parsed, publications, evidence)
    withheld = []
    for profile in parsed.profiles:
        deaths = profile.survival.get("all_cause_deaths_reported")
        if deaths and profile.source_arm.casefold() in conflicted:
            withheld.append(
                {
                    "registry_group": profile.source_arm,
                    "field": "all_cause_deaths",
                    "value": deaths,
                    "reason": "unreconciled_source_conflict",
                }
            )
        for source in ("serious_terms", "non_serious_terms"):
            progression = [
                {"term": i["term"], "n": i["n"], "N": i["N"]}
                for i in profile.toxicity.get(source, [])
                if i.get("neoplasm") and i["n"] > 0
            ]
            if progression:
                withheld.append(
                    {
                        "registry_group": profile.source_arm,
                        "field": f"{source}_neoplasm_concepts",
                        "value": progression,
                        "reason": "disease_progression_reported_as_adverse_event",
                    }
                )
        if other := profile.toxicity.get("non_serious_adverse_events_above_threshold"):
            withheld.append(
                {
                    "registry_group": profile.source_arm,
                    "field": "any_non_serious_AE_above_reporting_threshold",
                    "value": {"n": other["n"], "N": other["N"]},
                    "reason": "definition_depends_on_registry_reporting_threshold",
                }
            )
    return {
        "nct_id": parsed.nct_id,
        "study_title": parsed.study_title,
        "registry_url": parsed.study_url,
        "question_coverage": _question_coverage(parsed, asset),
        "source_conflicts": parsed.source_conflicts,
        "withheld_from_asset": withheld,
        "normalisation": enrichment or {},
        "safety_reporting": parsed.safety_reporting,
        "key_event_rules": {
            "common_non_serious": f"rate >= {COMMON_EVENT_MIN_RATE} in the profile",
            "serious": f"rate >= {SERIOUS_EVENT_MIN_RATE} and n >= {SERIOUS_EVENT_MIN_N} in the profile",
            "higher_than_comparator": f"rate >= {DIFFERENTIAL_MIN_RATIO}x the comparator arm and "
            f">= {DIFFERENTIAL_MIN_DIFFERENCE} higher",
            "excluded": "zero counts and events whose UMLS concept or organ system is a neoplasm",
            "full_tables": "raw registry record",
        },
        "outcome_time_frames": sorted(
            {
                o["time_frame"]
                for p in parsed.profiles
                for s in (p.response, p.survival)
                for o in s.get("outcomes", [])
                if o.get("time_frame")
            }
        ),
        "publications": [p.audit_metadata() for p in publications],
        "excluded_measures": [x for p in parsed.profiles for x in _measures(p)[2]],
        "publication_extraction": [
            {
                "publication": item.publication_id,
                "text_used": item.text_source,
                "sentences": item.sentence_log,
                "model_relationships": item.model_log,
            }
            for item in evidence or []
        ],
        "publication_reconciliation": reconciliation,
        "model_usage": model_usage or {},
        "parser_items": [
            {"kind": item.kind, "path": item.source_path, **item.detail}
            for item in parsed.audit
            if item.kind not in {"extracted_baseline", "extracted_outcome", "extracted_flow"}
        ],
    }
