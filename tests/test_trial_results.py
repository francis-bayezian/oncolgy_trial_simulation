"""Milestones 15-16: success curve and registry-style results (synthetic fixtures; no protocol-specific content)."""

import numpy as np

from clinical_asset.trial import results as rs
from clinical_asset.trial import simulate as sim


def _model(grid=(0.5, 1.0)):
    return {"control_arm_id": "A", "control_efs": {"status": "RESOLVED", "cure_fraction": 0.5, "failure_rate_per_year": 1.0},
            "loss_to_follow_up": {"status": "RESOLVED", "rate_per_year": 0.01}, "off_study_limit": {"days": 3652.5},
            "analysis_rule": {"evaluable_target": 120, "min_followup_years": 1, "excluded_share": 0.1},
            "effect": {"grid_hr": list(grid), "design_alternatives": [{"hr": 0.5, "control_long_term": 0.5, "experimental_long_term": 0.707,
                                                                        "wording": "from 50% to 71%"},
                                                                       {"hr": 0.6, "control_long_term": 0.6, "experimental_long_term": 0.736,
                                                                        "wording": "from 60% to 74%"}]},
            "adverse_events_asset": {"A": {"class_signature": "x", "missing_classes": [], "note": "adult evidence",
                                           "events": [{"event": "nausea", "seriousness": "non_serious", "rate": 0.3}]},
                                     "B": {"class_signature": "x", "missing_classes": [], "note": "adult evidence",
                                           "events": [{"event": "nausea", "seriousness": "non_serious", "rate": 0.3}]}},
            "assessment_timing": "events observed at their true time", "efs_origin": "enrollment"}


def _spec():
    return {"analyses": [{"primary": True, "test_family": "stratified_logrank", "sidedness": "one_sided", "alpha": {"value": 0.05},
                          "scenarios": [{"power": 0.8, "effect": {"text": "from 50% to 71%"}}]}],
            "treatment_phases": [{"phase_id": "PH1", "sequence_number": 1, "status": "EXECUTABLE", "duration": {"days": 42.0}}],
            "endpoints": [{"name": {"text": "EFS"}, "role": "primary"}, {"name": {"text": "OS"}, "role": "secondary"}]}


def _plan_rand():
    plan = {"target": {"patients": 200}, "scenarios": [{"scenario": "accrual_50_per_year", "rate_per_year": 50.0}]}
    rand = {"arms": [{"arm_id": "A", "label": "Arm A"}, {"arm_id": "B", "label": "Arm B"}], "ratio": [1.0, 1.0], "strata": []}
    return plan, rand


def test_success_is_more_likely_under_a_stronger_true_effect():
    plan, rand = _plan_rand()
    curve = rs.success_curve(_spec(), _model(), np.array(["UNRESOLVED"] * 500), plan, rand, replicates=60, seed=1)
    rows = {r["hr"]: r for r in curve["accrual_50_per_year"]}
    assert rows[0.5]["p_success"] > 0.5 > rows[1.0]["p_success"]
    assert rows[1.0]["enrolled"]["median"] >= 120 and rows[0.5]["events"]["median"] > 0


def test_design_checks_only_compare_claims_made_for_the_simulated_control():
    curve = {"s": [{"hr": 0.5, "p_success": 0.85, "mc_se": 0.01}, {"hr": 0.6, "p_success": 0.7, "mc_se": 0.01},
                   {"hr": 1.0, "p_success": 0.05, "mc_se": 0.007}]}
    checks = rs.design_checks(curve, _model(), _spec())
    power = [c for c in checks if c["check"].startswith("power")]
    assert power[0]["comparable"] and power[0]["protocol_claims_at_least"] == 0.8 and power[0]["consistent"]
    assert not power[1]["comparable"] and "not comparable" in power[1]["note"]
    assert checks[0]["check"] == "type I error at HR 1" and checks[0]["consistent"]


def test_registry_record_reports_flow_baseline_efs_and_unresolved_endpoints():
    rng = np.random.default_rng(3)
    cohort = [{"subject_id": f"S{i}", "enrollment_day": 5.0 * i, "arm_id": "A" if i % 2 else "B", "stratum": "UNRESOLVED",
               "baseline": {"demographic:age": {"value": 10.0 + i % 5}, "demographic:sex": "female" if i % 3 else "male",
                            "demographic:race": "white", "demographic:ethnicity": "not_hispanic_or_latino"}} for i in range(300)]
    phases = sim.treatment_phases(_spec()) + [{"phase_id": "PH2", "status": "REVIEW_REQUIRED", "days": None, "reason": "not executable"}]
    trial = sim.simulate_trial(cohort, _model(), 0.7, rng, phases)
    _, rand = _plan_rand()
    rec = rs.registry_record(trial, sim.primary_analysis(trial, _spec()["analyses"][0]), _model(), _spec(), rand, rng)
    a = rec["arms"]["A"]
    assert a["participant_flow"]["started"] + rec["arms"]["B"]["participant_flow"]["started"] == trial["n_enrolled"]
    assert isinstance(a["participant_flow"]["completed_PH1"], int) and a["participant_flow"]["completed_PH2"]["status"] == "IN_JOURNEY_STAGE"
    assert set(a["efs_percent"]) == {"2y", "3y", "5y"} and a["baseline"]["participants"] == a["participant_flow"]["started"]
    assert rec["outcome_measures"][0]["status"] == "SIMULATED" and rec["outcome_measures"][1]["status"] == "IN_ENDPOINT_STAGE"
    assert a["adverse_events"]["other"][0]["term"] == "nausea"
