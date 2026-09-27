"""Design rules: binary decision rules and dose escalation (synthetic fixtures; no protocol-specific content)."""

from clinical_asset.protocol import design_rules as dr


def _raw(n1="10", stop="0 or 1", cont="", n="22", success="6 or more", p0="p0=0.15", p1="p1=0.40", alpha="alpha=0.10",
         beta="beta = 0.10", pet="54%"):
    return {"stages": [{"cumulative_n_quote": n1, "stop_if_at_most_quote": stop, "continue_if_at_least_quote": cont},
                       {"cumulative_n_quote": n, "stop_if_at_most_quote": "", "continue_if_at_least_quote": ""}],
            "success_if_at_least_quote": success, "p0_quote": p0, "p1_quote": p1, "alpha_quote": alpha, "beta_quote": beta,
            "early_termination_probability_quote": pet, "family": "simon_optimal"}


def test_exact_operating_characteristics_of_a_published_optimal_two_stage_design():
    # Simon (1989) optimal design for p0 = 0.15, p1 = 0.40, alpha = beta = 0.10: r1/n1 = 1/10, r/n = 5/22
    rule = dr.binary_rule(_raw())
    oc = rule["operating_characteristics"]
    assert rule["issues"] == [] and rule["stages"][0]["stop_if_at_most"] == 1 and rule["success_if_at_least"] == 6
    assert abs(oc["at_p0"]["prob_success"] - 0.0907) < 1e-3 and abs(oc["at_p1"]["prob_success"] - 0.9031) < 1e-3
    assert abs(oc["at_p0"]["prob_early_stop"] - 0.544) < 1e-3 and abs(oc["at_p0"]["expected_n"] - 15.47) < 0.01


def test_a_continue_threshold_is_converted_and_a_misread_threshold_is_caught():
    same = dr.binary_rule(_raw(stop="", cont="2 or more"))
    assert same["stages"][0]["stop_if_at_most"] == 1 and same["issues"] == []
    misread = dr.binary_rule(_raw(success="3 or more"))                   # far too lenient for the stated alpha
    assert any("type I error" in i for i in misread["issues"])
    wrong_pet = dr.binary_rule(_raw(pet="80%"))
    assert any("early-termination" in i for i in wrong_pet["issues"])
    other_design = dr.binary_rule({**_raw(pet="99%"), "family": "single_stage"})     # a probability in another sense: not checked
    assert not any("early-termination" in i for i in other_design["issues"])


def test_single_stage_rule_and_incomplete_rules():
    single = dr.binary_rule({"stages": [{"cumulative_n_quote": "26", "stop_if_at_most_quote": "", "continue_if_at_least_quote": ""}],
                             "success_if_at_least_quote": "8 or more", "p0_quote": "20%", "p1_quote": "40%", "alpha_quote": "",
                             "beta_quote": "", "early_termination_probability_quote": ""})
    assert single["issues"] == [] and single["operating_characteristics"]["at_p0"]["prob_early_stop"] == 0.0
    assert dr.prob_success(single, 0.2) == dr.prob_success(single, 0.2)
    incomplete = dr.binary_rule({**_raw(), "success_if_at_least_quote": "", "alpha_quote": ""})     # nothing to derive it from
    assert "no success threshold" in incomplete["issues"]


def test_escalation_count_rules_are_parsed():
    rules = dr.count_rules("If 0 of 3 patients has a DLT escalate; if 1 of 3 expand to 6; if 2 or more of 6 stop")
    assert rules == [{"events": 0, "of": 3, "or_more": False}, {"events": 1, "of": 3, "or_more": False},
                     {"events": 2, "of": 6, "or_more": True}]
    e = dr.escalation_rule({"design_family": "three_plus_three", "cohort_size_quote": "3", "dose_level_quotes": ["25 mg", "50 mg", "dose level"],
                            "starting_dose_quote": "25 mg", "mtd_definition_quote": "", "dlt_window_quote": "", "applies_to_quote": "",
                            "evidence_quote": "",
                            "rules": [{"action": "escalate", "dlt_count_quote": "0", "dlt_count_comparator": "exactly", "patients_quote": "3",
                                       "evidence_quote": ""},
                                      {"action": "expand_cohort", "dlt_count_quote": "1", "dlt_count_comparator": "exactly", "patients_quote": "3",
                                       "evidence_quote": ""},
                                      {"action": "stop_dose_exceeds_mtd", "dlt_count_quote": "2 or more", "dlt_count_comparator": "at_least",
                                       "patients_quote": "up to 6", "evidence_quote": ""}]})
    assert e["issues"] == [] and e["cohort_size"] == 3 and e["dose_levels"] == ["25 mg", "50 mg"]
    assert e["rules"][2] == {"action": "stop_dose_exceeds_mtd", "dlt": 2, "comparator": "at_least", "patients": 6}


def test_no_means_zero_and_a_percentage_is_never_a_count():
    rule = dr.binary_rule(_raw(n1="9", stop="no patients", n="26", success="60% or higher", p0="p0=0.35", p1="p1=0.60",
                               alpha="0.05 (onesided)", beta="", pet=""))
    assert rule["stages"][0]["stop_if_at_most"] == 0 and rule["success_derivation"] and rule["issues"] == []
    from scipy import stats
    r = rule["success_if_at_least"]
    assert stats.binom.sf(r - 1, 26, 0.35) <= 0.05 < stats.binom.sf(r - 2, 26, 0.35)


def test_a_rule_stated_for_several_arms_becomes_one_rule_per_arm():
    raw = {**_raw(), "rule_id": "r", "role": "primary", "arm_label_quotes": ["drug a", "drug b"], "cohort_quote": "", "design_family": "simon_optimal",
           "endpoint_quote": "", "evidence_quote": ""}
    arms = [{"arm_id": "ARM1", "label": {"text": "Drug A (10 mg)"}}, {"arm_id": "ARM2", "label": {"text": "Drug B (5 mg)"}}]
    rules = dr.build([{"output": {"binary_rules": [raw, raw], "dose_escalation": []}, "sections": ["1"], "document": "d"}],
                     lambda r: None, lambda src, quote, field: {"text": quote} if quote else None, arms)
    assert [(r["decision_rule_id"], r["arms"]) for r in rules] == [("DR1", ["ARM1"]), ("DR2", ["ARM2"])]
    assert "for the arm Drug A (10 mg)" in rules[0]["rendering_basis"]


def test_a_dose_escalation_rule_is_built_into_the_spec():
    raw = {"rule_id": "e", "design_family": "three_plus_three", "applies_to_quote": "", "cohort_size_quote": "3", "dose_level_quotes": ["25 mg"],
           "starting_dose_quote": "", "mtd_definition_quote": "", "dlt_window_quote": "", "evidence_quote": "",
           "rules": [{"action": "escalate", "dlt_count_quote": "0", "dlt_count_comparator": "exactly", "patients_quote": "3", "evidence_quote": ""},
                     {"action": "stop_dose_exceeds_mtd", "dlt_count_quote": "2", "dlt_count_comparator": "at_least", "patients_quote": "6",
                      "evidence_quote": ""}]}
    rules = dr.build([{"output": {"binary_rules": [], "dose_escalation": [raw]}, "sections": ["1"], "document": "d"}],
                     lambda r: None, lambda src, quote, field: {"text": quote} if quote else None, [])
    assert rules[0]["kind"] == "dose_escalation" and rules[0]["compile_issues"] == [] and len(rules[0]["rule_quotes"]) == 2
    assert "escalate if exactly 0 of 3 patients have a DLT" in rules[0]["rendering_basis"]
