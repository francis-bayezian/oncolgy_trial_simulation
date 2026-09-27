"""Normalisation without a medical dictionary: registry MeSH, UMLS concepts, validated quotes."""

import re
from pathlib import Path

from fakes import FakeModel, FakeTerminology, standard_terminology
from test_accuracy_fixes import enriched
from test_registry import study_fixture

from clinical_asset.phenotype import (
    biomarkers,
    drug_identities,
    expand_coordination,
    resolve_ellipsis,
    selection_concepts,
    treatment_ontology,
)
from clinical_asset.terminology import Concept, inflection_variants


def test_no_trial_specific_medical_vocabulary_in_pipeline_code() -> None:
    banned = re.compile(
        r"sotorasib|docetaxel|amg ?510|\bkras\b|nsclc|lung|neutropen|diarrh|alanine|alopecia|"
        r"brain|platinum|pd-?l?1|egfr|taxane|carcinoma|melanoma|leuk|lymphoma|myeloma",
        re.IGNORECASE,
    )
    root = Path(__file__).resolve().parents[1] / "clinical_asset"
    offenders = [
        f"{path.name}:{number}"
        for path in root.rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if banned.search(line) and not line.strip().startswith("#")
        and "e.g." not in line and "'" not in line  # docstring examples only
    ]
    assert offenders == []


def test_intervention_mapped_to_mesh_drug_by_registry_evidence() -> None:
    study = study_fixture()
    study["protocolSection"]["armsInterventionsModule"]["interventions"][0]["name"] = "XY-123"
    study["protocolSection"]["identificationModule"]["officialTitle"] = 'Study of XY-123 "Proposed INN Examplinib" vs Drug B'
    study["derivedSection"] = {"interventionBrowseModule": {"meshes": [
        {"id": "C1", "term": "examplinib"}, {"id": "D2", "term": "Drug B"}]}}
    terminology = FakeTerminology({
        "XY-123": ("C_XY", "XY-123", ("T121",)),
        "examplinib": ("C_EX", "examplinib", ("T121",)),
        "Examplinib": ("C_EX", "examplinib", ("T121",)),
        "Drug B": ("C_B", "drug b", ("T121",)),
    })
    identities, audit = drug_identities(study, terminology)
    assert identities["XY-123"]["drug"] == "examplinib"
    assert identities["Drug B"]["drug"] == "drug b"
    assert {"intervention": "XY-123", "alias": "Examplinib", "via": "registry_alias_wording"} in audit


def test_mesh_one_to_one_remainder_used_only_when_unambiguous() -> None:
    study = study_fixture()
    study["protocolSection"]["armsInterventionsModule"]["interventions"][0]["name"] = "XY-123"
    study["derivedSection"] = {"interventionBrowseModule": {"meshes": [
        {"id": "C1", "term": "examplinib"}, {"id": "D2", "term": "Drug B"}]}}
    terminology = FakeTerminology({"Drug B": ("C_B", "drug b", ("T121",)), "examplinib": ("C_EX", "examplinib", ("T121",))})
    identities, audit = drug_identities(study, terminology)
    assert identities["XY-123"]["drug"] == "examplinib"
    assert any(a.get("via") == "mesh_one_to_one_remainder" for a in audit)


def test_drug_class_must_be_quoted_from_the_umls_definition() -> None:
    terminology = FakeTerminology(
        {"KRAS p.G12C": ("C_G12C", "KRAS p.G12C", ("T049",)), "KRAS": ("C_KRAS", "KRAS gene", ("T028",))},
        definitions={"C_EX": "An orally available inhibitor of KRAS p.G12C with antineoplastic activity."},
    )
    identity = {"concept": Concept("C_EX", "examplinib", ("T121",), 1.0, True), "mesh_id": "C1"}
    good = FakeModel({"drug_ontology": {"drug_class_quote": "orally available inhibitor of KRAS p.G12C",
                                        "target_quote": "KRAS p.G12C", "mechanism_quote": ""}})
    ontology, rejected = treatment_ontology(identity, terminology, good)
    assert ontology["drug_class"] == "orally available inhibitor of KRAS p.G12C"
    assert ontology["target"] == {"name": "KRAS p.G12C", "umls_cui": "C_G12C"}
    invented = FakeModel({"drug_ontology": {"drug_class_quote": "tyrosine kinase inhibitor",
                                            "target_quote": "", "mechanism_quote": ""}})
    ontology, rejected = treatment_ontology(identity, terminology, invented)
    assert "drug_class" not in ontology
    assert rejected[0]["reason"] == "quote_not_in_definition"


def test_disease_and_biomarker_come_from_umls_concepts() -> None:
    parsed, _ = enriched()
    profile = parsed.profiles[0]
    assert profile.cancer["disease"]["umls_cui"] == "C_MNSCLC"  # most specific neoplasm span
    assert profile.patient_group.get("biomarkers", []) == []  # fixture condition names no variant
    assert biomarkers(["KRAS p, G12c Mutated NSCLC"], standard_terminology())[0]["variant"] == "p.G12C"


def test_study_without_neoplasm_concept_is_excluded() -> None:
    study = study_fixture()
    study["protocolSection"]["conditionsModule"]["conditions"] = ["Healthy volunteers"]
    study["protocolSection"]["identificationModule"]["officialTitle"] = "Pharmacokinetics of Drug A"
    parsed, _ = enriched(study)
    assert not parsed.eligible
    assert parsed.exclusion_reason == "no_neoplasm_concept_in_conditions"


def test_exception_clause_and_coordination_in_selection_criteria() -> None:
    text = ("Exclusion: previously identified oncogenic driver mutation other than KRAS G12C. "
            "Patients progressed after a PD-1 or PD-L1 inhibitor.")
    model = FakeModel({"selection_criteria": {"criteria": [
        {"kind": "exclusion", "concept_quote": "oncogenic driver mutation", "qualifier_quote": "previously identified"},
        {"kind": "exclusion", "concept_quote": "KRAS G12C", "qualifier_quote": "other than"},
        {"kind": "required_prior_therapy", "concept_quote": "PD-L1 inhibitor", "qualifier_quote": "a PD-1 or PD-L1 inhibitor"},
        {"kind": "required_prior_therapy", "concept_quote": "Patients", "qualifier_quote": ""},
    ]}})
    terminology = standard_terminology()
    terminology.concepts["patients"] = ("C_PAT", "Patients", ("T101",))
    result, audit = selection_concepts(text, model, terminology, set())
    excluded = [e["concept"] for e in result["excluded"]]
    assert excluded == ["oncogenic driver mutation"]  # kept with source wording; KRAS not excluded
    assert {e["umls_cui"] for e in result["required_prior_therapy"]} == {"C_PD1", "C_PDL1"}
    reasons = {a["reason"] for a in audit}
    assert {"exception_clause_not_a_criterion", "prior_therapy_resolves_to_non_therapy_concept"} <= reasons
    assert expand_coordination("PD-1 or PD-L1 inhibitor") == ["PD-1 inhibitor", "PD-L1 inhibitor"]
    assert resolve_ellipsis("PD-1", text) == "PD-1 inhibitor"
    assert inflection_variants("aspartate aminotransferase increase")[1] == "aspartate aminotransferase increased"
