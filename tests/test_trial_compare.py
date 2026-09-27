"""Blind registry comparison (synthetic fixtures; no protocol-specific content)."""

import math

from clinical_asset.trial import compare as cp


def _registry():
    groups = [{"id": "OG0", "title": "Arm X (Disease Patients)"}, {"id": "OG1", "title": "Arm Y (Disease Patients)"}]

    def meas(values):
        return [{"categories": [{"measurements": [{"groupId": g, "value": str(v), "lowerLimit": str(v - 10), "upperLimit": str(v + 10)}
                                                  for g, v in values.items()]}]}]
    return {"resultsSection": {
        "outcomeMeasuresModule": {"outcomeMeasures": [
            {"title": "Percent Probability of Event-free Survival for Patients With Disease", "groups": groups, "classes": meas({"OG0": 50.0, "OG1": 60.0})}]},
        "baselineCharacteristicsModule": {"groups": [{"id": "BG9", "title": "Total"}], "measures": [
            {"title": "Sex: Female, Male", "classes": [{"categories": [{"title": "Female", "measurements": [{"groupId": "BG9", "value": "40"}]},
                                                                       {"title": "Male", "measurements": [{"groupId": "BG9", "value": "60"}]}]}]},
            {"title": "Age, Continuous", "paramType": "MEDIAN", "classes": [{"categories": [{"measurements": [{"groupId": "BG9", "value": "9"}]}]}]}]},
        "participantFlowModule": {"groups": [{"id": "FG0", "title": "Arm X (Disease Patients)"}, {"id": "FG1", "title": "Arm Y (Disease Patients)"}],
                                  "periods": [{"milestones": [{"type": "STARTED", "achievements": [{"groupId": "FG0", "numSubjects": "50"},
                                                                                                   {"groupId": "FG1", "numSubjects": "50"}]}]}]},
        "adverseEventsModule": {"otherEvents": [{"term": "Nausea", "stats": [{"numAffected": 20, "numAtRisk": 100}]}]}}}


def test_comparison_checks_the_control_arm_and_derives_the_implied_effect():
    efs = {"X": {"5y": {"median": 0.52, "q05": 0.45, "q95": 0.59}}, "Y": {"5y": {"median": 0.52, "q05": 0.45, "q95": 0.59}}}
    row = {"hr": 1.0, "enrolled": {"median": 100}, "efs_by_arm": efs, "p_success": 0.05}
    alt = {"hr": 0.75, "enrolled": {"median": 100}, "efs_by_arm": {"X": efs["X"], "Y": {"5y": {"median": 0.61}}}, "p_success": 0.4}
    results = {"control_arm_id": "X", "success_curve": {"s": [alt, row]},
               "adverse_events_asset": {"X": {"class_signature": "c", "events": [{"event": "nausea", "seriousness": "non_serious", "rate": 0.3}]}}}
    population = {"demographic:sex": {"source": "protocol_projection", "probabilities": {"female": 0.4, "male": 0.6}},
                  "demographic:age": {"source": "v3"}, "demographic:race": {"source": "v3", "probabilities": {}},
                  "demographic:ethnicity": {"source": "v3", "probabilities": {}}}
    cohort = [{"baseline": {"demographic:age": {"value": 10.0}}}]
    arms = [{"arm_id": "X", "label": "ARM X"}, {"arm_id": "Y", "label": "ARM Y"}]
    doc = cp.compare(results, population, cohort, _registry(), arms, "Disease", "2026-01-01T10:00:00", "2026-01-01T10:05:00")
    control = doc["items"][0]
    assert control["observed"] == 50.0 and control["observed_in_predicted_90"] and control["prediction_in_observed_ci"]
    experimental = doc["items"][1]
    assert math.isclose(experimental["implied_hr_vs_control"], math.log(0.6) / math.log(0.5))
    assert experimental["p_success_at_implied_hr"] == {"s": 0.4}
    male = next(i for i in doc["items"] if i["quantity"].startswith("share male"))
    assert male["predicted"] == 60.0 and male["observed"] == 60.0
    assert doc["order_verified"] and doc["adverse_events"]["rows"][0]["observed_pct"] == 20.0
    assert not cp.compare(results, population, cohort, _registry(), arms, "Disease", "2026-01-02", "2026-01-01")["order_verified"]


def test_binary_comparison_matches_arms_and_reads_counts_or_percentages():
    curve = [{"p": 0.2, "prob_of_interest": 0.3, "expected_n": 18.0}, {"p": 0.4, "prob_of_interest": 0.9, "expected_n": 21.0}]
    sim = [{"p": 0.2, "enrolled": {"q05": 10, "q95": 22}, "observed_rate": {"q05": 0.05, "q95": 0.35}},
           {"p": 0.4, "enrolled": {"q05": 22, "q95": 22}, "observed_rate": {"q05": 0.25, "q95": 0.55}}]
    binary = {"rules": [{"decision_rule_id": "DR1", "arm": "Drug Alpha (10 mg)", "cohort": "previously treated", "exact_curve": curve,
                         "simulated": sim, "rule": {"success_if_at_least": 6}, "cited_evidence": [{"fact_id": "F1", "rate": 0.4, "prob_of_interest": 0.9}]}]}
    registry = {"resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [
        {"type": "PRIMARY", "title": "Objective response of drug alpha", "unitOfMeasure": "Participants",
         "groups": [{"id": "OG0", "title": "Drug Alpha"}, {"id": "OG1", "title": "Drug Alpha then Beta"}],
         "denoms": [{"counts": [{"groupId": "OG0", "value": "8"}, {"groupId": "OG1", "value": "14"}]}],
         "classes": [{"categories": [{"title": "CR", "measurements": [{"groupId": "OG0", "value": "1"}, {"groupId": "OG1", "value": "0"}]},
                                     {"title": "PR", "measurements": [{"groupId": "OG0", "value": "3"}, {"groupId": "OG1", "value": "4"}]}]}]},
        {"type": "PRIMARY", "title": "Objective response of drug beta", "unitOfMeasure": "Participants", "groups": [], "denoms": [], "classes": []}]}}}
    doc = cp.compare_binary(binary, registry, "2026-01-01", "2026-01-02")
    item = doc["items"][0]
    assert item["observed_rate"] == 8 / 22 and item["registry_responders"] == 8 and item["registry_participants"] == 22
    assert item["design_decision_at_observed"].startswith("of interest") and doc["order_verified"]
    assert item["cited_rate_predictions"][0]["registry_rate_in_interval"]


def test_a_percentage_of_participants_is_read_as_a_rate():
    curve = [{"p": 0.55, "prob_of_interest": None, "expected_n": 26.0}]
    sim = [{"p": 0.55, "enrolled": {"q05": 26, "q95": 26}, "observed_rate": {"q05": 0.38, "q95": 0.69}}]
    binary = {"rules": [{"decision_rule_id": "EST", "arm": "Drug Gamma", "cohort": None, "exact_curve": curve, "simulated": sim,
                         "rule": {"success_if_at_least": None, "stages": [{"n": 26, "stop_if_at_most": None}]}, "cited_evidence": []}]}
    registry = {"resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [
        {"type": "PRIMARY", "title": "Response rate of drug gamma", "unitOfMeasure": "% of participants", "groups": [{"id": "OG0", "title": "Gamma"}],
         "denoms": [{"counts": [{"groupId": "OG0", "value": "26"}]}],
         "classes": [{"categories": [{"measurements": [{"groupId": "OG0", "value": "57.7"}]}]}]}]}}}
    item = cp.compare_binary(binary, registry, "a", "b")["items"][0]
    assert abs(item["observed_rate"] - 0.577) < 1e-9 and item["design_decision_at_observed"].startswith("no decision defined")
