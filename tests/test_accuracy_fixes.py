"""Regression tests for accuracy defects found when auditing NCT04303780."""

from fakes import FakeModel, mentions_for, standard_terminology
from test_registry import study_fixture

from clinical_asset.enrich import enrich_study
from clinical_asset.registry import parse_study
from clinical_asset.report import build_audit, build_clinical_asset
from clinical_asset.source_text import eligibility_phenotype, population_label, regimen


def crossover_study() -> dict:
    study = study_fixture()
    study["protocolSection"]["eligibilityModule"] = {
        "minimumAge": "18 Years",
        "eligibilityCriteria": (
            "Inclusion Criteria:\n\n* ECOG ≤ 1\n* Pathologically documented, previously treated, "
            "locally-advanced and unresectable or metastatic NSCLC\n\n"
            "Exclusion Criteria:\n\n* Active brain metastases\n"
        ),
    }
    study["resultsSection"]["adverseEventsModule"] = {
        "description": (
            "Serious and other adverse events are reported for all participants who received at "
            "least one dose of study drug. All-cause mortality is reported for all randomized "
            "participants. Data are reported per treatment received."
        ),
        "timeFrame": "Adverse events: first dose to 30 days after last dose. Mortality: from randomization.",
        "frequencyThreshold": "5",
        "eventGroups": [
            {"id": "EG0", "title": "Drug A", "seriousNumAffected": 10, "seriousNumAtRisk": 48,
             "deathsNumAffected": 20, "deathsNumAtRisk": 50},
            {"id": "EG1", "title": "Drug B", "seriousNumAffected": 12, "seriousNumAtRisk": 45,
             "deathsNumAffected": 15, "deathsNumAtRisk": 50},
            {"id": "EG2", "title": "Drug B, Then Switched to Drug A",
             "description": "Randomized to Drug B with radiological progression confirmed by "
             "independent central review, then switched to Drug A.",
             "seriousNumAffected": 3, "seriousNumAtRisk": 12,
             "deathsNumAffected": 4, "deathsNumAtRisk": 12},
        ],
        "seriousEvents": [
            {"term": "Pneumonia", "organSystem": "Infections and infestations",
             "stats": [{"groupId": "EG0", "numAffected": 1, "numAtRisk": 48},
                       {"groupId": "EG1", "numAffected": 5, "numAtRisk": 45},
                       {"groupId": "EG2", "numAffected": 0, "numAtRisk": 12}]},
            {"term": "Non-small cell lung cancer",
             "organSystem": "Neoplasms benign, malignant and unspecified (incl cysts and polyps)",
             "stats": [{"groupId": "EG0", "numAffected": 4, "numAtRisk": 48},
                       {"groupId": "EG1", "numAffected": 2, "numAtRisk": 45},
                       {"groupId": "EG2", "numAffected": 1, "numAtRisk": 12}]},
            {"term": "Rare event", "organSystem": "Cardiac disorders",
             "stats": [{"groupId": "EG0", "numAffected": 1, "numAtRisk": 48},
                       {"groupId": "EG1", "numAffected": 0, "numAtRisk": 45},
                       {"groupId": "EG2", "numAffected": 1, "numAtRisk": 12}]},
        ],
    }
    study["resultsSection"]["participantFlowModule"] = {
        "groups": [{"id": "FG0", "title": "Drug A"}, {"id": "FG1", "title": "Drug B"}],
        "periods": [
            {
                "title": "Overall Study",
                "milestones": [
                    {"type": "Switched From Drug B to Drug A",
                     "achievements": [{"groupId": "FG0", "numSubjects": "0"},
                                      {"groupId": "FG1", "numSubjects": "12"}]}
                ],
                "dropWithdraws": [
                    {"type": "Death", "reasons": [{"groupId": "FG0", "numSubjects": "20"},
                                                  {"groupId": "FG1", "numSubjects": "17"}]}
                ],
            }
        ],
    }
    return study


SELECTION = {
    "selection_criteria": {
        "criteria": [
            {"kind": "exclusion", "concept_quote": "brain metastases", "qualifier_quote": "Active"},
        ]
    }
}


def enriched(study: dict | None = None, model: FakeModel | None = None):
    study = study or crossover_study()
    parsed = parse_study(study)
    terminology = standard_terminology()
    audit = enrich_study(parsed, study, terminology, mentions_for(terminology), model or FakeModel(SELECTION))
    return parsed, audit


def arm_profiles(asset: dict) -> dict:
    return {
        p["source"]["registry_group"]: p
        for p in asset["clinical_profiles"]
        if p["profile_type"] != "reported_subgroup"
    }


def test_crossover_group_becomes_its_own_profile_not_dropped() -> None:
    parsed, _ = enriched()
    switched = next(p for p in parsed.profiles if p.source_arm.startswith("Drug B, Then"))
    history = switched.patient_group["treatment_history_in_trial"]
    assert history["randomized_to"] == "drug b"
    assert history["switched_to"] == "drug a"
    assert history["switch_trigger"] == "disease_progression"
    assert switched.patient_group["n"] == 12
    assert switched.toxicity["serious_adverse_events_any_cause"]["N"] == 12


def test_mortality_conflict_between_modules_is_reported_not_hidden() -> None:
    parsed = parse_study(crossover_study())
    conflicts = {c["randomized_arm"]: c for c in parsed.source_conflicts}
    assert "Drug A" not in conflicts
    assert conflicts["Drug B"]["participant_flow_deaths"] == 17
    assert conflicts["Drug B"]["adverse_events_module_deaths_in_switched_group"] == 4


def test_zero_counts_and_neoplasm_events_are_not_reported_as_toxicity() -> None:
    parsed, _ = enriched()
    profiles = arm_profiles(build_clinical_asset(parsed, []))
    assert "switched_to_other_arm" not in profiles["Drug A"].get("treatment_course", {})
    assert profiles["Drug B"]["treatment_course"]["switched_to_other_arm"] == 12
    serious_a = profiles["Drug A"]["toxicity"].get("key_serious_events", {})
    serious_b = profiles["Drug B"]["toxicity"]["key_serious_events"]
    # Progression recorded as a serious event is recognised by its UMLS neoplasm type.
    assert "non_small_cell_lung_carcinoma" not in serious_a
    assert serious_b["pneumonia"]["n"] == 5
    assert "pneumonia" not in serious_a
    assert "rare_event" not in serious_a
    switched = profiles["Drug B, Then Switched to Drug A"]["toxicity"]
    assert "pneumonia" not in switched.get("key_serious_events", {})


def test_safety_and_efficacy_populations_are_labelled() -> None:
    parsed, _ = enriched()
    toxicity = build_clinical_asset(parsed, [])["clinical_profiles"][0]["toxicity"]
    assert toxicity["population"] == "treated_safety_population"
    assert toxicity["grouping"] == "as_treated"
    assert build_audit(parsed, [])["safety_reporting"]["mortality_population"] == "all_randomized"
    assert population_label(
        "Measured in the Full Analysis Set (FAS), which included all randomized participants."
    ) == "full_analysis_set_all_randomized"


def test_selection_context_is_separate_from_observed_patient_profile() -> None:
    parsed, _ = enriched()
    profile = build_clinical_asset(parsed, [])["clinical_profiles"][0]
    assert profile["selection_context"]["ECOG_allowed"] == [0, 1]
    assert profile["selection_context"]["excluded"] == [
        {"concept": "Metastatic malignant neoplasm to brain", "umls_cui": "C_BRAIN", "qualifier": "Active"}
    ]
    assert "ECOG_allowed" not in profile["patient_profile"]
    assert profile["patient_profile"]["age"] == {"mean": 63.4, "sd": 9.9, "unit": "year"}


def test_unreconciled_deaths_and_qa_stay_out_of_the_asset() -> None:
    parsed, _ = enriched()
    asset = build_clinical_asset(parsed, [])
    profiles = arm_profiles(asset)
    assert profiles["Drug A"]["mortality_observations"]["all_cause_deaths"] == 20
    assert "mortality_observations" not in profiles["Drug B"]
    assert "mortality_observations" not in profiles["Drug B, Then Switched to Drug A"]
    assert "death" not in profiles["Drug B"]["treatment_course"].get("study_status_at_data_cutoff", {})
    for banned in ("question_coverage", "source_conflicts", "clinical_facts_extracted"):
        assert banned not in str(asset)
    audit = build_audit(parsed, [])
    withheld = {(w["registry_group"], w["field"]) for w in audit["withheld_from_asset"]}
    assert ("Drug B", "all_cause_deaths") in withheld


def test_eligibility_grammar_defines_setting() -> None:
    limits = eligibility_phenotype(crossover_study()["protocolSection"]["eligibilityModule"])
    assert limits["performance_status"] == {"scale": "ECOG", "allowed": [0, 1]}
    assert limits["prior_systemic_therapy"] == "required"
    assert limits["disease_extent"] == "locally_advanced_unresectable_or_metastatic"
    assert parse_study(crossover_study()).profiles[0].setting == "locally_advanced_unresectable_or_metastatic"


def test_regimen_grammar() -> None:
    assert regimen(
        r"received 75 mg/m\^2 of docetaxel via intravenous (IV) infusion once every 3 weeks "
        "(Q3W) in each 21 day cycle.",
        ["Docetaxel"],
    ) == {
        "dose": {"value": 75, "unit": "mg/m2"},
        "route": "intravenous",
        "frequency": "every 3 weeks",
        "cycle_length_days": 21,
    }
    # Two doses in one sentence: dose is withheld rather than guessed.
    assert "dose" not in regimen("received 100 mg or 200 mg of Drug A orally", ["Drug A"])
