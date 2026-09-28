"""Rule-based dose escalation (synthetic fixtures; no protocol-specific content)."""

import numpy as np

from clinical_asset.trial import escalation as es

RULE = {"cohort_size": 3, "rules": [
    {"action": "escalate", "dlt": 0, "comparator": "exactly", "patients": 3},
    {"action": "expand_cohort", "dlt": 1, "comparator": "exactly", "patients": 3},
    {"action": "escalate", "dlt": 1, "comparator": "at_most", "patients": 6},
    {"action": "stop_dose_exceeds_mtd", "dlt": 2, "comparator": "at_least", "patients": 6}]}


def test_no_toxicity_clears_every_level_and_certain_toxicity_stops_at_the_first():
    rng = np.random.default_rng(0)
    safe = es.run_escalation(RULE, [0.0, 0.0, 0.0], rng)
    assert safe["mtd_level"] is None and safe["treated"] == [3, 3, 3]
    toxic = es.run_escalation(RULE, [1.0, 1.0], rng)
    assert toxic["mtd_level"] == -1 and toxic["treated"] == [3, 0]


def test_a_toxic_level_stops_escalation_and_the_level_below_is_selected():
    rng = np.random.default_rng(1)
    r = es.run_escalation(RULE, [0.0, 0.0, 1.0], rng)
    assert r["mtd_level"] == 1 and r["treated"] == [3, 3, 3]


def test_operating_characteristics_cover_every_truth_of_the_grid():
    rows = es.operating_characteristics(RULE, 3, 2000, 2)
    assert [r["true_highest_tolerable_level"] for r in rows] == [-1, 0, 1, 2]
    assert all(abs(sum(r["selection"].values()) - 1) < 1e-9 for r in rows) and all(r["prob_correct"] > 0.4 for r in rows)


def _ladder_rule(stages=None, rows=None):
    return {"design_family": "three_plus_three", "cohort_size": 3, "dose_levels": [],
            "ladder": {"start": {"value": 25.0, "unit": "mg"}, "max": None, "dosage_forms": [{"value": 25.0, "unit": "mg"}], "sequence": None,
                       "stages": stages or []},
            "rules": rows or [{"action": "escalate", "dlt": 0, "comparator": "exactly", "patients": 3, "increment": {"factor": 1.5, "bound": "at_most"}},
                              {"action": "expand_cohort", "dlt": 1, "comparator": "exactly", "patients": 3, "increment": None},
                              {"action": "expand_previous_level", "dlt": 2, "comparator": "at_least", "patients": 3, "increment": None},
                              {"action": "escalate", "dlt": 1, "comparator": "exactly", "patients": 6, "increment": {"factor": 1.33, "bound": "at_most"}},
                              {"action": "expand_previous_level", "dlt": 2, "comparator": "at_least", "patients": 6, "increment": None}]}


def test_next_dose_applies_the_maximum_increment_rounded_down_to_dosage_forms():
    forms = [{"value": 25.0, "unit": "mg"}]
    assert es.next_dose(200, {"factor": 1.5, "bound": "at_most"}, 0, forms, "mg") == 300
    assert es.next_dose(300, {"factor": 1.33, "bound": "at_most"}, 0, forms, "mg") == 375        # 399 rounded down to 25 mg
    assert es.next_dose(25, {"factor": 1.33, "bound": "at_most"}, 0, forms, "mg") == 50          # never below one strength up
    assert es.next_dose(10, {"sequence": [2.0, 1.67], "bound": "exact"}, 1, [], "mg") == 16.7


def test_accelerated_titration_doubles_until_the_switch_then_follows_the_table():
    rule = _ladder_rule(stages=[{"kind": "accelerated_titration", "cohort_size": 1, "increment": {"factor": 2.0, "bound": "exact"},
                                 "switch": {"patients": 1, "grade_at_least": 2, "or_dlt": True}},
                                {"kind": "rule_based", "cohort_size": 3, "increment": None, "switch": None}])
    rng = np.random.default_rng(0)
    r = es.run_ladder(rule, {"d_star": 1e9, "slope": 3.0, "grade2_odds": 1.0}, rng, max_patients=12)
    assert r["doses"][:5] == [25.0, 50.0, 100.0, 200.0, 400.0] and r["treated"][:4] == [1, 1, 1, 1]
    # a steep curve with D* near 100 mg: the declared MTD sits at or just below D* most of the time
    oc = es.ladder_characteristics(rule, 300, 1)
    row = next(x for x in oc if x["truth"]["slope"] == 3.0 and x["truth"]["grade2_odds"] == 1.0 and abs(x["truth"]["d_star"] - 100) < 1e-9)
    assert row["declared_mtd"]["median"] <= 100 and row["p_mtd_above_d_star"] < 0.3


def test_a_toxic_starting_dose_declares_no_tolerable_dose():
    rng = np.random.default_rng(3)
    picks = [es.run_ladder(_ladder_rule(), {"d_star": 2.0, "slope": 3.0, "grade2_odds": 1.0}, rng)["mtd"] for _ in range(200)]
    assert sum(p is None for p in picks) > 180


def test_registry_dose_result_and_ladder_comparison():
    reg = {"resultsSection": {"outcomeMeasuresModule": {"outcomeMeasures": [
        {"type": "PRIMARY", "title": "Maximum Tolerated Dose", "unitOfMeasure": "mg", "classes": [{"categories": [{"measurements": [{"value": "100"}]}]}]}]}}}
    obs = es.registry_dose_result(reg)
    assert obs == {"title": "Maximum Tolerated Dose", "value": 100.0, "unit": "mg"}
    rule = _ladder_rule(stages=[{"kind": "accelerated_titration", "cohort_size": 1, "increment": {"factor": 2.0, "bound": "exact"},
                                 "switch": {"patients": 1, "grade_at_least": 2, "or_dlt": True}},
                                {"kind": "rule_based", "cohort_size": 3, "increment": None, "switch": None}])
    entry = {"rule": rule, "ladder_characteristics": es.ladder_characteristics(rule, 200, 2)}
    c = es.compare_ladder(entry, obs)
    assert c["status"] == "SCORED" and 60 < c["best"]["truth"]["d_star"] < 300


def test_a_nearly_harmless_start_is_almost_never_declared_intolerable():
    rule = _ladder_rule(stages=[{"kind": "accelerated_titration", "cohort_size": 1, "increment": {"factor": 2.0, "bound": "exact"},
                                 "switch": {"patients": 1, "grade_at_least": 2, "or_dlt": True}},
                                {"kind": "rule_based", "cohort_size": 3, "increment": None, "switch": None}])
    rng = np.random.default_rng(5)
    picks = [es.run_ladder(rule, {"d_star": 1600.0, "slope": 1.0, "grade2_odds": 1.0}, rng)["mtd"] for _ in range(400)]
    assert sum(p is None for p in picks) / 400 < 0.05          # P(DLT) is 1% at the starting dose
