"""Engineering checks for source population and treatment attribution."""

from clinical_asset.ctgov import eligibility, linked_result_references
from clinical_asset.registry import numeric, parse_study


def study_fixture() -> dict:
    return {
        "hasResults": True,
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT12345678",
                "briefTitle": "Example oncology study",
            },
            "designModule": {"studyType": "INTERVENTIONAL", "designInfo": {"allocation": "RANDOMIZED"}},
            "statusModule": {"overallStatus": "COMPLETED"},
            "conditionsModule": {"conditions": ["Metastatic NSCLC"]},
            "armsInterventionsModule": {
                "armGroups": [{"label": "Drug A"}, {"label": "Drug B"}],
                "interventions": [
                    {"name": "Drug A", "armGroupLabels": ["Drug A"]},
                    {"name": "Drug B", "armGroupLabels": ["Drug B"]},
                ],
            },
            "referencesModule": {
                "references": [
                    {"pmid": "111", "type": "RESULT", "citation": "Study. doi: 10.1000/a."},
                    {"pmid": "222", "type": "BACKGROUND", "citation": "Unrelated context."},
                ]
            },
        },
        "resultsSection": {
            "baselineCharacteristicsModule": {
                "populationDescription": "All randomised participants",
                "groups": [
                    {"id": "BG0", "title": "Drug A"},
                    {"id": "BG1", "title": "Drug B"},
                ],
                "denoms": [
                    {
                        "units": "Participants",
                        "counts": [
                            {"groupId": "BG0", "value": "50"},
                            {"groupId": "BG1", "value": "50"},
                        ],
                    }
                ],
                "measures": [
                    {
                        "title": "Age, Continuous",
                        "paramType": "MEAN",
                        "dispersionType": "STANDARD_DEVIATION",
                        "unitOfMeasure": "years",
                        "classes": [
                            {
                                "categories": [
                                    {
                                        "measurements": [
                                            {"groupId": "BG0", "value": "63.4", "spread": "9.9"},
                                            {"groupId": "BG1", "value": "64.2", "spread": "8.5"},
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ],
            },
            "outcomeMeasuresModule": {
                "outcomeMeasures": [
                    {
                        "title": "Objective Response Rate",
                        "populationDescription": "Biomarker-positive subset",
                        "paramType": "NUMBER",
                        "unitOfMeasure": "Participants",
                        "groups": [
                            {"id": "OG0", "title": "Drug A"},
                            {"id": "OG1", "title": "Drug B"},
                        ],
                        "denoms": [
                            {
                                "units": "Participants",
                                "counts": [
                                    {"groupId": "OG0", "value": "25"},
                                    {"groupId": "OG1", "value": "20"},
                                ],
                            }
                        ],
                        "classes": [
                            {
                                "categories": [
                                    {
                                        "measurements": [
                                            {"groupId": "OG0", "value": "13"},
                                            {"groupId": "OG1", "value": "4"},
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
            "adverseEventsModule": {},
            "participantFlowModule": {},
        },
    }


def test_separate_populations_and_correct_arms() -> None:
    parsed = parse_study(study_fixture())
    assert parsed.eligible
    assert len(parsed.profiles) == 4
    baseline_a = next(
        p
        for p in parsed.profiles
        if p.source_arm == "Drug A" and p.source_population == "treatment_arm_aggregate"
    )
    response_a = next(
        p
        for p in parsed.profiles
        if p.source_arm == "Drug A" and p.source_population == "Biomarker-positive subset"
    )
    response_b = next(
        p
        for p in parsed.profiles
        if p.source_arm == "Drug B" and p.source_population == "Biomarker-positive subset"
    )
    assert baseline_a.patient_group["n"] == 50
    assert baseline_a.patient_group["n_basis"] == "reported_baseline"
    assert baseline_a.baseline["measures"][0]["value"] == 63.4
    assert baseline_a.patient_group["age"]["standard_deviation"] == 9.9
    assert not baseline_a.response
    assert response_a.patient_group["n"] == 25
    assert response_a.response["outcomes"][0]["value"] == 13
    assert response_b.response["outcomes"][0]["value"] == 4
    assert not response_a.baseline


def test_only_registry_result_references_are_selected() -> None:
    references = linked_result_references(study_fixture())
    assert len(references) == 1
    assert references[0]["pmid"] == "111"
    assert references[0]["doi"] == "10.1000/a"


def test_endpoint_denominator_does_not_replace_baseline_population_count() -> None:
    study = study_fixture()
    outcome = study["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    outcome["populationDescription"] = "All randomised participants"

    parsed = parse_study(study)
    drug_a = next(profile for profile in parsed.profiles if profile.source_arm == "Drug A")

    assert drug_a.patient_group["n"] == 50
    assert drug_a.baseline["measures"][0]["denominator"] == 50
    assert drug_a.response["outcomes"][0]["denominator"] == 25
    assert len(parsed.profiles) == 2
    assert drug_a.response["outcomes"][0]["analysis_population"] == "All randomised participants"


def test_all_cause_deaths_are_separate_from_adverse_events() -> None:
    study = study_fixture()
    study["resultsSection"]["adverseEventsModule"] = {
        "description": "Serious events in treated patients. All-cause mortality in randomized patients.",
        "eventGroups": [
            {
                "title": "Drug A",
                "description": "Drug A treatment group",
                "seriousNumAffected": 8,
                "seriousNumAtRisk": 48,
                "deathsNumAffected": 7,
                "deathsNumAtRisk": 50,
            }
        ],
    }

    parsed = parse_study(study)
    drug_a = next(
        profile
        for profile in parsed.profiles
        if profile.source_arm == "Drug A" and profile.source_population == "treatment_arm_aggregate"
    )

    assert len(parsed.profiles) == 4
    assert drug_a.toxicity["serious_adverse_events_any_cause"]["N"] == 48
    assert drug_a.survival["all_cause_deaths_reported"] == {"n": 7, "at_risk": 50}
    assert "rate" not in drug_a.survival["all_cause_deaths_reported"]
    assert "deaths" not in drug_a.toxicity


def test_demographic_outcome_creates_only_reported_subgroup() -> None:
    study = study_fixture()
    outcome = study["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    outcome["populationDescription"] = "Full analysis set"
    outcome["groups"][0]["title"] = "Drug A: Female"
    outcome["groups"][1]["title"] = "Drug B: Female"

    parsed = parse_study(study)
    female_a = next(
        profile for profile in parsed.profiles if profile.source_population == "Drug A: Female"
    )

    assert len(parsed.profiles) == 4
    assert female_a.source_arm == "Drug A"
    assert female_a.patient_group["sex"] == "Female"
    assert female_a.patient_group["n"] == 25
    assert female_a.response["outcomes"][0]["reported_result_group"] == "Drug A: Female"
    assert all(profile.patient_group.get("sex") != "Male" for profile in parsed.profiles)


def test_impossible_serious_event_count_is_held_for_review() -> None:
    study = study_fixture()
    study["resultsSection"]["adverseEventsModule"] = {
        "eventGroups": [
            {
                "title": "Drug A",
                "seriousNumAffected": 51,
                "seriousNumAtRisk": 48,
            }
        ]
    }

    parsed = parse_study(study)
    drug_a = next(
        profile
        for profile in parsed.profiles
        if profile.source_arm == "Drug A" and profile.source_population == "treatment_arm_aggregate"
    )

    assert "serious_adverse_events_any_cause" not in drug_a.toxicity
    assert any(
        item.detail.get("reason") == "invalid_event_numerator_or_denominator"
        for item in parsed.audit
    )


def test_excludes_study_without_posted_results() -> None:
    study = study_fixture()
    study["hasResults"] = False
    assert eligibility(study) == (False, "results_not_posted")
    assert parse_study(study).profiles == []


def test_analysis_subset_population_stays_labelled_and_never_sets_arm_n() -> None:
    study = study_fixture()
    outcome = study["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    outcome["populationDescription"] = "Patients meeting an additional eligibility criterion"

    parsed = parse_study(study)
    drug_a = next(p for p in parsed.profiles if p.source_arm == "Drug A")

    assert len(parsed.profiles) == 2
    assert drug_a.patient_group["n"] == 50  # from baseline, not the subset's 25
    value = drug_a.response["outcomes"][0]
    assert value["population_scope"] == "analysis_subset"
    assert value["denominator"] == 25
    assert any(item.kind == "analysis_subset_population" for item in parsed.audit)


def test_result_groups_match_arms_by_prefix_or_intervention() -> None:
    study = study_fixture()
    arms = study["protocolSection"]["armsInterventionsModule"]
    arms["armGroups"] = [{"label": "A"}, {"label": "B: Drug B"}]
    arms["interventions"] = [
        {"name": "Drug A", "armGroupLabels": ["A"]},
        {"name": "Drug B", "armGroupLabels": ["B: Drug B"]},
    ]
    parsed = parse_study(study)
    assert {p.source_arm for p in parsed.profiles} == {"A", "B: Drug B"}


def test_numeric_parser_refuses_inequalities_and_text() -> None:
    assert numeric("5.62") == 5.62
    assert numeric("1,234") == 1234
    assert numeric("<0.001") is None
    assert numeric("not estimable") is None


def test_numbered_arms_match_by_drug_and_placebo_type_and_unmatched_group_keeps_its_drugs() -> None:
    study = study_fixture()
    arms = study["protocolSection"]["armsInterventionsModule"]
    arms["armGroups"] = [{"label": "1", "type": "PLACEBO_COMPARATOR"}, {"label": "2", "type": "EXPERIMENTAL"}]
    arms["interventions"] = [{"name": "ZD9999 (Examplinib)", "armGroupLabels": ["2"]}]
    base = study["resultsSection"]["baselineCharacteristicsModule"]
    base["groups"] = [
        {"id": "BG0", "title": "Examplinib 300 mg"},
        {"id": "BG1", "title": "Placebo"},
    ]
    parsed = parse_study(study)
    arms_found = {p.source_arm for p in parsed.profiles if p.baseline}
    assert arms_found == {"1", "2"}
    matched = {item.detail["via"] for item in parsed.audit if item.kind == "group_matched_to_arm"}
    assert {"unique_intervention_name", "placebo_comparator_arm"} <= matched


def test_placebo_group_never_inherits_a_drug_and_second_group_never_overwrites_an_arm() -> None:
    study = study_fixture()
    arms = study["protocolSection"]["armsInterventionsModule"]
    arms["armGroups"] = [{"label": "1", "type": "NO_INTERVENTION"}, {"label": "2", "type": "EXPERIMENTAL"}]
    arms["interventions"] = [{"name": "Examplinib", "type": "DRUG", "armGroupLabels": ["2"]}]
    study["resultsSection"]["adverseEventsModule"] = {
        "eventGroups": [
            {"id": "E0", "title": "Randomized Period: Examplinib", "seriousNumAffected": 10, "seriousNumAtRisk": 40},
            {"id": "E1", "title": "Randomized Period: Placebo", "description": "placebo matched to examplinib",
             "seriousNumAffected": 4, "seriousNumAtRisk": 38},
            {"id": "E2", "title": "Open-Label Period: Examplinib", "seriousNumAffected": 7, "seriousNumAtRisk": 30},
        ]
    }
    parsed = parse_study(study)
    by_arm = {p.source_arm: p for p in parsed.profiles if p.toxicity}
    assert by_arm["2"].toxicity["serious_adverse_events_any_cause"]["N"] == 40  # not overwritten by 30
    assert by_arm["1"].treatment.get("drug") == "placebo"
    assert by_arm["result group: Open-Label Period: Examplinib"].toxicity["serious_adverse_events_any_cause"]["N"] == 30
