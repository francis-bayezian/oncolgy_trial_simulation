"""Repair passes and integrity checks for Asset v1."""

from fakes import standard_terminology

from clinical_asset.qa import check_profile
from clinical_asset.repair import repair_profile, structure_subgroup

TYPES = {"C_OK": ["T081"], "C_GENE": ["T028"], "C_NEO": ["T191"], "C_DRUG": ["T121"]}


def types_of(cui: str) -> list[str]:
    return TYPES.get(cui, [])


def base_profile(**extra) -> dict:
    return {
        "profile_type": "randomized_arm",
        "cancer": {"disease": {"name": "x", "umls_cui": "C_NEO"}, "setting": "metastatic"},
        "treatment": {"drug": "Drug A", "arm_type": "experimental"},
        "patient_profile": {"n": 50},
        "efficacy": {"orr": [{"statistic": "count", "value": 10, "N": 50, "rate": 0.2, "umls_cui": "C_OK"}]},
        "source": {"nct": "NCT1", "registry_group": "A"},
        **extra,
    }


def codes(profile: dict, raw: dict | None = None) -> set[str]:
    return {i["code"] for i in check_profile(profile, 0, raw, types_of)}


def test_clean_profile_has_no_errors() -> None:
    assert codes(base_profile()) == set()


def test_integrity_checks_flag_known_defects() -> None:
    profile = base_profile(comparisons=[{"comparator": "drug a", "comparator_group": "A", "outcome": "orr", "measure": "hazard_ratio", "value": 0.7}])
    profile["efficacy"]["orr_1"] = [{"statistic": "count", "value": 60, "N": 60, "rate": 1.2, "umls_cui": "C_GENE"}]
    raw = {"protocolSection": {"conditionsModule": {"conditions": ["Non-metastatic prostate cancer"]}}}
    found = codes(profile, raw)
    assert {"OUTCOME_KEY_SUFFIX", "OBS_RATE_OUT_OF_RANGE", "OBS_N_EXCEEDS_PROFILE_N", "UMLS_OUTCOME_WRONG_TYPE",
            "COMPARISON_SELF", "SETTING_CONTRADICTS_SOURCE"} <= found


def test_repairs_remove_bad_mappings_and_duplicates_without_inventing_values() -> None:
    profile = base_profile(comparisons=[{"comparator": "drug a", "comparator_group": "A", "outcome": "orr", "measure": "or", "value": 1.0}])
    obs = {"statistic": "count", "value": 10, "N": 50, "rate": 1.4, "umls_cui": "C_GENE"}
    profile["efficacy"]["orr"] = [obs, dict(obs)]
    fixed, log = repair_profile(profile, types_of, None)
    [kept] = fixed["efficacy"]["orr"]
    assert "umls_cui" not in kept and "rate" not in kept and kept["value"] == 10
    assert "comparisons" not in fixed
    assert fixed["treatment"]["regimen"] == "drug a"
    assert {e["repair"] for e in log} >= {"DROP_WRONG_TYPE_OUTCOME_CUI", "DROP_OUT_OF_RANGE_RATE", "DEDUPE_OBSERVATIONS", "DROP_SELF_COMPARISON"}


def test_subgroup_definition_is_structured() -> None:
    subgroup = structure_subgroup("female patients with liver metastases aged ≥65 years", standard_terminology())
    assert subgroup["sex"] == "female"
    assert subgroup["age"] == {"operator": ">=", "years": 65}
    assert subgroup["criteria"][0]["umls_cui"] == "C_LIVER"
