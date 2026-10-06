"""Subgroup evidence: levels from protocol wording, the complement from a whole-population row, and patient effects
centred on the mix (synthetic fixtures only; no model calls)."""

import math

from clinical_asset.trial import subgroup_evidence as sge


def test_levels_from_protocol_wording():
    assert sge.parse_levels("prior therapy X (yes vs no)") == ["yes", "no"]
    assert sge.parse_levels("number of prior therapies (1 vs > 1; 1 vs 2 vs > 2)") == ["1", "> 1"]
    assert sge.parse_levels("Marker high versus marker low") == ["Marker high", "marker low"]
    assert sge.parse_levels("tumour location") == []


def test_protocol_factors_merge_duplicates_and_skip_demographics():
    spec = {"stratification": {"factors": [{"text": "disease stage at entry (I vs II)", "canonical_factor": "disease_stage_at_entry"}],
                               "strata": []},
            "subgroups": [{"subgroup": {"text": "disease stage at entry"}}, {"subgroup": {"text": "age (< 65, >= 65)"}},
                          {"subgroup": {"text": "marker status (positive vs negative)"}}]}
    fs = sge.protocol_factors(spec)
    assert [f["key"] for f in fs] == ["var:disease_stage_at_entry", "var:marker_status"]
    assert fs[0]["levels"] == ["I", "II"]


def test_complement_from_whole_population():
    # 40 of 100 patients in level A with response 50%; whole population 35% -> level B response 25%
    v = sge.complement({"A": (0.5, 40), sge.ALL: (0.35, 100)}, ["A", "B"], orr=True)
    assert v[0] == "B" and abs(v[1] - 0.25) < 1e-9
    # medians: exponential mixture through the event rates
    m = sge.complement({"A": (12.0, 50), sge.ALL: (8.0, 100)}, ["A", "B"], orr=False)
    lam_b = (math.log(2) / 8 - 0.5 * math.log(2) / 12) / 0.5
    assert m[0] == "B" and abs(m[1] - math.log(2) / lam_b) < 1e-9


def test_patient_effects_are_centred_on_the_mix():
    ev = {"factors": [{"key": "var:m", "kind": "existing", "levels": ["pos", "neg"], "mix": {"pos": 0.25, "neg": 0.75},
                       "effects": {"status": "RESOLVED", "reference_level": "pos",
                                   "log_hazard_ratio": {"neg": {"log_effect": 0.4}}}}]}
    hr_pos = sge.patient_log_effects({"var:m": "pos"}, ev)[0]
    hr_neg = sge.patient_log_effects({"var:m": "neg"}, ev)[0]
    assert abs(0.25 * hr_pos + 0.75 * hr_neg) < 1e-12            # the mix average is unchanged
    assert abs((hr_neg - hr_pos) - 0.4) < 1e-12                  # the stated effect between levels
    assert sge.patient_log_effects({}, ev) == (0.0, 0.0)          # unknown level: no shift
    assert sge.patient_log_effects({"var:m": "pos"}, None) == (0.0, 0.0)
