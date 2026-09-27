"""Observation normalisation: categories, interval types, units, measure classes."""

from clinical_asset.observations import (
    canonical_statistic,
    canonical_unit,
    measure_class,
    observation,
)


def test_categories_become_separate_observations_not_suffix_keys() -> None:
    from test_registry import study_fixture

    from clinical_asset.registry import parse_study
    from clinical_asset.report import build_clinical_asset

    study = study_fixture()
    outcome = study["resultsSection"]["outcomeMeasuresModule"]["outcomeMeasures"][0]
    outcome["populationDescription"] = "All randomised participants"
    outcome["paramType"] = "COUNT_OF_PARTICIPANTS"
    outcome["classes"][0]["categories"] = [
        {"title": "Complete response", "measurements": [{"groupId": "OG0", "value": "3"}, {"groupId": "OG1", "value": "1"}]},
        {"title": "Partial response", "measurements": [{"groupId": "OG0", "value": "10"}, {"groupId": "OG1", "value": "3"}]},
    ]
    profile = build_clinical_asset(parse_study(study), [])["clinical_profiles"][0]
    [(key, observations)] = profile["efficacy"].items()
    assert not key[-1].isdigit()
    assert [(o["category"], o["value"], o["rate"]) for o in observations] == [
        ("Complete response", 3, 0.12), ("Partial response", 10, 0.4)
    ]


def test_intervals_keep_their_reported_type() -> None:
    base = {"measure": "Overall survival", "value": 11.2, "statistic": "MEDIAN", "unit": "Months",
            "lower_limit": 8.1, "upper_limit": 14.0}
    assert observation({**base, "dispersion": "95% Confidence Interval"}, {})["ci"] == [8.1, 14.0]
    assert observation({**base, "dispersion": "95% Confidence Interval"}, {})["ci_level"] == 95.0
    assert observation({**base, "dispersion": "Full Range"}, {})["range"] == [8.1, 14.0]
    assert observation({**base, "dispersion": "Inter-Quartile Range"}, {})["iqr"] == [8.1, 14.0]
    assert "ci" not in observation({**base, "dispersion": "Full Range"}, {})


def test_units_statistics_and_measure_classes() -> None:
    assert canonical_unit("Months") == "month"
    assert canonical_unit("percentage of particpants") == "percent"
    assert canonical_unit("Participants") == "participants"
    assert canonical_statistic("NUMBER", "Percentage of participants") == "percentage"
    assert measure_class("Maximum Plasma Concentration (Cmax) of Drug A", "ng/mL") == "pharmacokinetic"
    assert measure_class("Number of Participants With Adverse Events", "Participants") == "safety"
    assert measure_class("Progression-free Survival", "months") == "efficacy"
