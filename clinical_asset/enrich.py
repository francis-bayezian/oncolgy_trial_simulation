"""Attach normalised concepts to the parsed registry profiles.

Runs after the deterministic registry parser and before the asset is built. Uses the
trial's own text, the registry MeSH mapping, UMLS (via scispaCy) and, for wording the rules
cannot interpret, quote-validated GPT-5.6 Luna answers.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .llm import StructuredModel
from .nlp import Mention
from .phenotype import (
    biomarkers,
    disease_concepts,
    drug_identities,
    selection_concepts,
    treatment_ontology,
)
from .terminology import FINDING_TYPES, NEOPLASM_TYPES, Terminology
from .types import ParsedStudy


def snake(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def strip_abbreviation(title: str) -> str:
    """'Progression-free Survival (PFS)' -> 'Progression-free Survival'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip() or title


REPORTING_PREFIX = re.compile(
    r"^(?:the\s+)?(?:number|percentage|percent|proportion|rate|count|incidence)\s+of\s+"
    r"(?:participants|patients|subjects|people|pts)\s+(?:with|who|achieving|experiencing|having|that)\s+"
    r"(?:an?\s+|the\s+)?(?:had\s+|achieved\s+|experienced\s+|have\s+)?(?:an?\s+|the\s+)?",
    re.IGNORECASE,
)
REPORTING_SUFFIX = re.compile(
    r"\s+(?:by|per|according to|as (?:assessed|determined|measured) by|assessed by|using)\s+.*$", re.IGNORECASE
)
STOP = frozenset({"of", "in", "the", "a", "an", "to", "with", "and", "or", "for", "on", "at", "by"})


def outcome_core(title: str) -> str:
    """Remove reporting wording, keep the clinical phrase: 'Number of Participants With
    Objective Response by BICR (ORR)' -> 'Objective Response'."""
    core = re.sub(r"\s*\([^)]*\)", "", title)
    core = REPORTING_PREFIX.sub("", core.strip())
    core = REPORTING_SUFFIX.sub("", core)
    return " ".join(core.split()) or title


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.casefold()) if w not in STOP}


def outcome_key(title: str, terminology: Terminology) -> tuple[str, str | None]:
    """A UMLS concept only when its name shares at least half its content words with the
    outcome's clinical phrase; otherwise the cleaned phrase itself. The full title is kept on
    every observation."""
    core = outcome_core(title)
    concept = terminology.link(core)
    if concept:
        a, b = _content(core), _content(concept.name)
        if a and b and len(a & b) / len(a | b) >= 0.5:
            return concept.key, concept.cui
    return snake(core), None


def enrich_study(
    parsed: ParsedStudy,
    study: dict[str, Any],
    terminology: Terminology,
    mentions_for: Any,
    model: StructuredModel | None,
) -> dict[str, Any]:
    """Mutates the parsed profiles; returns audit records."""
    audit: dict[str, Any] = {}
    protocol = study.get("protocolSection", {})

    # --- treatment identity
    identities, audit["drug_identity"] = drug_identities(study, terminology)
    ontology_audit: list[dict] = []
    ontologies: dict[str, dict] = {}
    eligibility_text = str(protocol.get("eligibilityModule", {}).get("eligibilityCriteria") or "")
    with ThreadPoolExecutor(max_workers=8) as pool:
        # Independent model calls run concurrently; answers are cached on disk.
        ontology_jobs = {
            name: pool.submit(treatment_ontology, identity, terminology, model)
            for name, identity in identities.items()
        }
        warm_selection = pool.submit(selection_concepts, eligibility_text, model, terminology, set())
        for name, job in ontology_jobs.items():
            ontologies[name], rejected = job.result()
            ontology_audit.extend(rejected)
        warm_selection.result()
    audit["drug_ontology_rejections"] = ontology_audit
    arm_drug: dict[str, str] = {}
    for profile in parsed.profiles:
        reported = profile.treatment.get("reported_name")
        identity = identities.get(reported or "")
        if identity:
            profile.treatment["drug"] = identity["drug"]
            profile.treatment["aliases"] = identity["aliases"]
            profile.treatment["umls_cuis"] = identity["cuis"]
            profile.treatment["ontology"] = ontologies.get(reported, {})
            profile.primary_drug = identity["drug"]
        if profile.treatment.get("interventions"):
            profile.treatment["interventions"] = [
                identities[name]["drug"] if name in identities else name for name in profile.treatment["interventions"]
            ]
            profile.treatment["umls_cuis"] = sorted(
                {cui for name in profile.treatment["interventions"] for cui in identities.get(name, {}).get("cuis", [])}
            )
        if not profile.patient_group.get("treatment_history_in_trial"):
            arm_drug[profile.source_arm] = profile.primary_drug or " + ".join(profile.treatment.get("interventions", [])) or profile.source_arm
        history = profile.patient_group.get("treatment_history_in_trial")
        if history:
            for key in ("randomized_to", "switched_to"):
                identity = identities.get(history.get(key, ""))
                if identity:
                    history[key] = identity["drug"]

    # --- disease and biomarkers from the trial's condition and title wording
    identity_module = protocol.get("identificationModule", {})
    conditions = [str(c) for c in protocol.get("conditionsModule", {}).get("conditions", [])]
    texts = [*conditions, str(identity_module.get("officialTitle") or ""), str(identity_module.get("briefTitle") or "")]
    texts = [t for t in texts if t]
    mentions: list[list[Mention]] = [mentions_for(t) for t in texts]
    diseases = disease_concepts(texts, mentions, terminology)
    inclusion_text = re.split(r"exclusion criteria", eligibility_text, maxsplit=1, flags=re.IGNORECASE)[0]
    markers = biomarkers([*texts, inclusion_text], terminology)
    audit["disease_candidates"] = diseases
    if not diseases:
        parsed.eligible = False
        parsed.exclusion_reason = "no_neoplasm_concept_in_conditions"
        return audit

    known = {d["umls_cui"] for d in diseases} | {m["umls_cui"] for m in markers}
    selection, audit["selection_rejections"] = selection_concepts(eligibility_text, model, terminology, known)
    for profile in parsed.profiles:
        primary = diseases[0]
        profile.cancer["disease"] = {"name": primary["name"], "umls_cui": primary["umls_cui"], "reported": primary["reported"]}
        profile.disease = primary["name"]
        if markers:
            profile.patient_group["biomarkers"] = markers
            profile.primary_biomarker = markers[0]["name"]
        if selection:
            profile.patient_group.setdefault("eligibility", {}).update(selection)

    # --- outcome and comparison keys
    for profile in parsed.profiles:
        for section in (profile.response, profile.survival):
            for item in section.get("outcomes", []):
                item["key"], item["umls_cui"] = outcome_key(str(item["measure"]), terminology)
        for effect in profile.comparative_effects:
            effect["outcome_key"], _ = outcome_key(str(effect["outcome"]), terminology)
            effect["comparator_drug"] = arm_drug.get(effect["comparator"], effect["comparator"])
            effect["treatment_drug"] = arm_drug.get(effect["treatment"], effect["treatment"])

    # --- adverse-event term concepts (one batch through the linker)
    terms = sorted(
        {
            str(item["term"])
            for profile in parsed.profiles
            for source in ("serious_terms", "non_serious_terms")
            for item in profile.toxicity.get(source, [])
        }
    )
    if hasattr(terminology, "prefetch"):
        terminology.prefetch(terms)
    keys: dict[str, tuple[str, str | None, bool]] = {}
    for term in terms:
        concept = terminology.link(term, FINDING_TYPES)
        neoplasm = bool(concept and set(concept.types) & NEOPLASM_TYPES)
        keys[term] = (concept.key, concept.cui, neoplasm) if concept else (snake(term), None, False)
    # An organ-system class that UMLS resolves to a neoplasm concept marks disease events too.
    systems = {
        str(item.get("organ_system") or "")
        for profile in parsed.profiles
        for source in ("serious_terms", "non_serious_terms")
        for item in profile.toxicity.get(source, [])
    }
    neoplasm_systems = {
        system
        for system in systems
        if system and terminology.link(re.split(r"[,(]", system)[0].strip(), NEOPLASM_TYPES)
    }
    for profile in parsed.profiles:
        for source in ("serious_terms", "non_serious_terms"):
            for item in profile.toxicity.get(source, []):
                item["key"], item["umls_cui"], neoplasm = keys[str(item["term"])]
                item["neoplasm"] = neoplasm or str(item.get("organ_system") or "") in neoplasm_systems
    audit["neoplasm_organ_systems"] = sorted(neoplasm_systems)
    audit["unlinked_event_terms"] = [t for t, (_, cui, _) in keys.items() if cui is None]
    audit["arm_drugs"] = arm_drug
    return audit
