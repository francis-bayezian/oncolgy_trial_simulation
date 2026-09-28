"""Planning timelines (synthetic fixtures; no trial-specific content)."""

import numpy as np

from clinical_asset.planning import events as ev

CURE = {"cure_fraction": 0.5, "failure_rate_per_year": 1.0}


def test_enrollment_duration_is_n_over_rate_with_poisson_spread():
    rng = np.random.default_rng(0)
    t = ev.timelines(120, np.full(4000, 60.0), rng, deadlines_years=(2.0,))
    assert abs(t["last_patient_in_years"]["median"] - 119 / 60) < 0.05       # 119 gaps after the first patient
    assert 0.4 < t["p_enrollment_complete_by"]["2y"] < 0.6


def test_accrual_stops_at_the_evaluable_target_and_the_analysis_follows_the_rule():
    rng = np.random.default_rng(1)
    rule = {"evaluable_target": 90, "min_followup_years": 1.0, "excluded_share": 0.1}
    t = ev.timelines(200, np.full(3000, 50.0), rng, analysis_rule=rule)
    assert abs(t["enrolled"]["median"] - 100) <= 2                               # 90 evaluable of about 100 enrolled
    assert abs(t["primary_analysis_years"]["median"] - (t["last_patient_in_years"]["median"] + 1.0)) < 0.05


def test_events_come_only_from_enrolled_patients_and_fewer_under_a_better_effect():
    rng = np.random.default_rng(2)
    rule = {"evaluable_target": 50, "min_followup_years": 1.0, "excluded_share": 0.0}
    null = ev.timelines(400, np.full(800, 50.0), rng, outcome=CURE, hr=1.0, event_targets=(20, 30), analysis_rule=rule)
    better = ev.timelines(400, np.full(800, 50.0), rng, outcome=CURE, hr=0.5, event_targets=(20, 30), analysis_rule=rule)
    # 50 enrolled, each fails with probability 0.5 (cure fraction): reaching 30 events is the binomial tail P(X >= 30)
    from scipy import stats
    assert abs(null["event_maturity"]["30"]["p_reached_ever"] - stats.binom.sf(29, 50, 0.5)) < 0.03
    assert better["event_maturity"]["20"]["p_reached_ever"] < null["event_maturity"]["20"]["p_reached_ever"]


def test_protocol_features_parse_phase_year_and_disease(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from clinical_asset.planning.report import protocol_features

    fam = tmp_path / "fam.parquet"
    pq.write_table(pa.Table.from_pylist([{"disease": "Carcinoma of urinary bladder, invasive", "disease_family": "urothelial", "confidence": 1.0},
                                         {"disease": "Ductal carcinoma of the breast", "disease_family": "breast", "confidence": 1.0},
                                         {"disease": "Small cell lung cancer", "disease_family": "lung", "confidence": 0.5}]), fam)
    age = {"node": "LEAF", "kind": "range", "status": "EXECUTABLE", "variable": "demographic:age", "lower": 18, "upper": None, "unit": "year"}
    spec = {"metadata": {"phase": {"text": "Phase I/II"}, "version_date": {"text": "01/03/2017"},
                         "condition": {"text": "Transitional cell carcinoma of the urinary bladder"}},
            "design": {"type": "single_arm"}, "arms": [{"arm_id": "ARM1"}],
            "eligibility": [{"criterion_id": "EL1", "kind": "inclusion", "status": "EXECUTABLE", "logic": age}]}
    import json

    from clinical_asset.planning import operational as op

    cache = tmp_path / "cond.json"
    cache.write_text(json.dumps({"Transitional cell carcinoma of the urinary bladder": {"item": "x", "label": "urothelial", "confidence": 0.95},
                                 "small cell lung cancer": {"item": "x", "label": "lung", "confidence": 0.5}}), encoding="utf-8")
    monkeypatch.setattr(op, "CONDITION_FAMILIES", cache)
    monkeypatch.setattr(op.condition_family, "__defaults__", (None, cache))
    f = protocol_features(spec, 30, fam)
    assert f["phase"] == "PHASE1+PHASE2" and f["start_year"] == 2017 and not f["randomized"] and not f["pediatric"]
    assert f["disease_family"] == "urothelial" and f["matched_disease"] == "Transitional cell carcinoma of the urinary bladder"
    spec["metadata"]["condition"] = {"text": "small cell lung cancer"}                  # below the confidence threshold
    assert protocol_features(spec, 30, fam)["disease_family"] == "other"
