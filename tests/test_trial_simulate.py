"""Milestones 9-14: trial engine and analysis (synthetic fixtures; no protocol-specific content)."""

import math

import numpy as np

from clinical_asset.trial import simulate as sim


def test_cox_recovers_the_true_hazard_ratio_and_logrank_detects_it():
    rng = np.random.default_rng(1)
    n = 4000
    g = rng.integers(0, 2, n)
    t = rng.exponential(1.0, n) / np.where(g == 1, 0.6, 1.0)
    c = rng.exponential(3.0, n)
    time, event = np.minimum(t, c), t <= c
    cox = sim.cox_hr(time, event, g)
    assert abs(cox["hr"] - 0.6) < 0.05 and cox["ci95"][0] < 0.6 < cox["ci95"][1]
    lr = sim.logrank(time, event, g)
    assert lr["z"] < -10 and lr["p_one_sided_group1_better"] < 1e-10


def test_logrank_keeps_its_type_one_error_under_no_effect():
    rng = np.random.default_rng(2)
    rejections = 0
    for _ in range(400):
        g = rng.integers(0, 2, 200)
        t = rng.exponential(1.0, 200)
        c = rng.exponential(2.0, 200)
        rejections += sim.logrank(np.minimum(t, c), t <= c, g)["p_one_sided_group1_better"] < 0.05
    assert abs(rejections / 400 - 0.05) < 0.03


def test_stratified_logrank_equals_unstratified_with_one_stratum():
    rng = np.random.default_rng(3)
    t, e, g = rng.exponential(1, 300), rng.random(300) < 0.7, rng.integers(0, 2, 300)
    a, b = sim.logrank(t, e, g), sim.logrank(t, e, g, np.zeros(300, dtype=int))
    assert math.isclose(a["z"], b["z"])


def test_kaplan_meier_matches_the_true_curve_without_censoring():
    rng = np.random.default_rng(4)
    t = rng.exponential(1.0, 20000)
    km = sim.kaplan_meier(t, np.ones_like(t, dtype=bool), [0.5, 1.0, 2.0])
    for v, x in zip(km, (0.5, 1.0, 2.0), strict=True):
        assert abs(v - math.exp(-x)) < 0.01
    assert sim.kaplan_meier(np.array([1.0, 2.0]), np.array([True, False]), [5.0]) == [None]


def _model():
    return {"control_arm_id": "A", "control_efs": {"cure_fraction": 0.5, "failure_rate_per_year": 1.0},
            "loss_to_follow_up": {"status": "RESOLVED", "rate_per_year": 0.01}, "off_study_limit": {"days": 3652.5},
            "analysis_rule": {"evaluable_target": 100, "min_followup_years": 1, "excluded_share": 0.1}}


def _cohort(n=300):
    return [{"subject_id": f"S{i}", "enrollment_day": 10.0 * i, "arm_id": "A" if i % 2 else "B", "stratum": "UNRESOLVED",
             "baseline": {}} for i in range(n)]


def test_accrual_stops_at_the_evaluable_target_and_the_analysis_follows_the_rule():
    rng = np.random.default_rng(5)
    phases = [{"phase_id": "PH1", "status": "EXECUTABLE", "days": 42.0}, {"phase_id": "PH2", "status": "REVIEW_REQUIRED", "days": None}]
    trial = sim.simulate_trial(_cohort(), _model(), 0.7, rng, phases)
    assert trial["evaluable"].sum() == 100 and trial["evaluable"][-1]                     # the last subject completes the target
    assert math.isclose(trial["analysis_day"], trial["enroll_day"][-1] + 365.25)
    assert np.all(trial["time_days"] <= trial["analysis_day"] - trial["enroll_day"] + 1e-9)
    assert trial["treatment"]["PH2"]["status"] == "UNRESOLVED" and trial["treatment"]["PH1"]["status"] == "RESOLVED"
    result = sim.primary_analysis(trial, {"test_family": "stratified_logrank", "sidedness": "one_sided", "alpha": {"value": 0.05}})
    assert result["evaluable"] == 100 and result["stratified"] is False and result["stratification_note"]


def test_treatment_phase_end_days_are_cumulative_and_stop_at_an_unresolved_phase():
    spec = {"treatment_phases": [
        {"phase_id": "PH1", "sequence_number": 1, "status": "EXECUTABLE", "duration": {"days": 42.0}},
        {"phase_id": "PH2", "sequence_number": 2, "status": "EXECUTABLE", "cycle_length": {"days": 28.0}, "cycle_count": {"value": 6.0}},
        {"phase_id": "PH3", "sequence_number": 3, "status": "REVIEW_REQUIRED", "duration": {"days": 10.0}},
        {"phase_id": "PH4", "sequence_number": 4, "status": "EXECUTABLE", "duration": {"days": 5.0}}]}
    phases = {p["phase_id"]: p for p in sim.treatment_phases(spec)}
    assert phases["PH1"]["days"] == 42.0 and phases["PH2"]["days"] == 42.0 + 168.0
    assert phases["PH4"]["days"] is None                                    # after an unresolved phase the timing is unknown
