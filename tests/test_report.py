"""Clinical JSON contains supported facts without invented associations."""

from clinical_asset.report import build_audit, build_clinical_asset
from clinical_asset.types import ClinicalProfile, ParsedStudy


def test_local_report_separates_evidence_from_unestablished_relationships() -> None:
    profile = ClinicalProfile(
        source_nct="NCT12345678",
        source_arm="Drug A",
        source_population="treatment_arm_aggregate",
        disease="KRAS p.G12C NSCLC",
        histology="NSCLC",
        primary_drug="Drug A",
        patient_group={
            "n": 50,
            "n_basis": "reported_baseline",
            "age": {"mean": 63.4, "standard_deviation": 9.9, "denominator": 50},
            "sex": {"Female": {"n": 20, "denominator": 50}},
        },
        survival={
            "outcomes": [
                {
                    "measure": "Progression-free Survival (PFS)",
                    "key": "progression_free_survival",
                    "statistic": "MEDIAN",
                    "value": 5.62,
                    "unit": "months",
                    "denominator": 50,
                }
            ],
            "all_cause_deaths_reported": {"n": 10, "at_risk": 50},
        },
        toxicity={"serious_adverse_events_any_cause": {"n": 8, "N": 48, "rate": 8 / 48}},
    )
    parsed = ParsedStudy(
        nct_id="NCT12345678",
        study_title="Example",
        study_url="https://clinicaltrials.gov/study/NCT12345678",
        eligible=True,
        exclusion_reason=None,
        profiles=[profile],
    )

    asset = build_clinical_asset(parsed, [])
    profile = asset["clinical_profiles"][0]

    assert profile["patient_profile"]["n"] == 50
    assert profile["patient_profile"]["age"]["mean"] == 63.4
    [pfs] = profile["efficacy"]["progression_free_survival"]
    assert (pfs["statistic"], pfs["value"], pfs["unit"]) == ("median", 5.62, "month")
    # Death counts are never presented as a survival endpoint.
    assert profile["mortality_observations"] == {"all_cause_deaths": 10, "at_risk": 50}
    assert "survival" not in profile
    assert profile["toxicity"]["any_serious_AE"] == {"n": 8, "rate": 0.1667}
    assert "response" not in str(profile.get("efficacy", {}))
    assert profile["source"] == {"nct": "NCT12345678", "registry_group": "Drug A", "publications": []}
    audit = build_audit(parsed, [])
    assert audit["question_coverage"]["3_correlations_between_characteristics"].startswith(
        "not_available"
    )
    assert "review_status" not in str(asset) + str(audit)
