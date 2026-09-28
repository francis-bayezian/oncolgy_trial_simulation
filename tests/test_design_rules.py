"""Design rules: binary decision rules and dose escalation (synthetic fixtures; no protocol-specific content)."""

from scipy import stats

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
    assert e["rules"][2] == {"action": "stop_dose_exceeds_mtd", "dlt": 2, "comparator": "at_least", "patients": 6, "increment": None, "quote_index": 2}


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
    raw = {"rule_id": "e", "design_family": "three_plus_three", "applies_to_quote": "", "cohort_size_quote": "3", "dose_level_quotes": ["25 mg", "50 mg"],
           "starting_dose_quote": "", "mtd_definition_quote": "", "dlt_window_quote": "", "evidence_quote": "",
           "rules": [{"action": "escalate", "dlt_count_quote": "0", "dlt_count_comparator": "exactly", "patients_quote": "3", "evidence_quote": ""},
                     {"action": "stop_dose_exceeds_mtd", "dlt_count_quote": "2", "dlt_count_comparator": "at_least", "patients_quote": "6",
                      "evidence_quote": ""}]}
    rules = dr.build([{"output": {"binary_rules": [], "dose_escalation": [raw]}, "sections": ["1"], "document": "d"}],
                     lambda r: None, lambda src, quote, field: {"text": quote} if quote else None, [])
    assert rules[0]["kind"] == "dose_escalation" and rules[0]["compile_issues"] == [] and len(rules[0]["rule_quotes"]) == 2
    assert "if exactly 0 of 3 patients have a DLT: escalate to the next dose" in rules[0]["rendering_basis"]


def test_a_dose_ladder_is_compiled_from_the_starting_dose_stages_and_row_increments():
    row = {"dlt_count_comparator": "exactly", "evidence_quote": ""}
    e = dr.escalation_rule({"design_family": "three_plus_three", "cohort_size_quote": "", "dose_level_quotes": [], "starting_dose_quote": "Starting dose of 25 mg",
                            "max_dose_quote": "", "dosage_form_quotes": ["25 mg capsules"], "increment_sequence_quote": "",
                            "stages": [{"stage_kind": "accelerated_titration", "cohort_size_quote": "1 patient", "increment_quote": "Twice the Previous Dose",
                                        "switch_condition_quote": "until 1 patient experiences a toxicity of >= Grade 2 or a DLT", "evidence_quote": ""},
                                       {"stage_kind": "rule_based", "cohort_size_quote": "3", "increment_quote": "", "switch_condition_quote": "", "evidence_quote": ""}],
                            "mtd_definition_quote": "", "dlt_window_quote": "", "applies_to_quote": "", "evidence_quote": "",
                            "rules": [{**row, "action": "escalate", "dlt_count_quote": "0", "patients_quote": "3", "increment_quote": "increase of <=50%"},
                                      {**row, "action": "expand_cohort", "dlt_count_quote": "1", "patients_quote": "3", "increment_quote": ""},
                                      {**row, "action": "expand_previous_level", "dlt_count_quote": "2 or more", "dlt_count_comparator": "at_least",
                                       "patients_quote": "3", "increment_quote": ""},
                                      {**row, "action": "escalate", "dlt_count_quote": "1", "patients_quote": "6", "increment_quote": "increase of <=33%"}]})
    assert e["issues"] == []
    assert e["ladder"]["start"] == {"value": 25.0, "unit": "mg"} and e["ladder"]["stages"][0]["increment"] == {"factor": 2.0, "bound": "exact"}
    assert e["ladder"]["stages"][0]["switch"] == {"patients": 1, "grade_at_least": 2, "or_dlt": True, "drug_related": False}
    assert e["rules"][3]["increment"] == {"factor": 1.33, "bound": "at_most"}
    incomplete = dr.escalation_rule({**{k: v for k, v in e.items()}, "design_family": "three_plus_three", "cohort_size_quote": "3", "dose_level_quotes": [],
                                     "starting_dose_quote": "", "stages": [], "rules": [{**row, "action": "escalate", "dlt_count_quote": "0", "patients_quote": "3",
                                                                                         "increment_quote": ""},
                                                                                        {**row, "action": "stop_dose_exceeds_mtd", "dlt_count_quote": "2",
                                                                                         "patients_quote": "3", "increment_quote": ""}]})
    assert any("dose ladder incomplete" in i for i in incomplete["issues"])


def _base(**kw):
    base = {"design_family": "two_stage_other", "family": "two_stage_other", "p0_quote": "", "p1_quote": "", "alpha_quote": "", "beta_quote": "",
            "success_if_at_least_quote": "", "early_termination_probability_quote": "", "stages": []}
    return {**base, **kw}


def test_a_stated_power_is_converted_to_beta():
    stage = {"stage_quote": "", "cumulative_n_quote": "17", "stop_if_at_most_quote": "", "continue_if_at_least_quote": "", "stop_if_events_at_least_quote": ""}
    r = dr.binary_rule(_base(stages=[stage], success_if_at_least_quote="3 or more", p0_quote="0.05", p1_quote="0.35", alpha_quote="0.05",
                             beta_quote="desired power of 0.9"))
    assert abs(r["beta"] - 0.1) < 1e-9 and "power" in r["beta_derivation"]


def test_a_toxicity_rule_stops_on_too_many_events_via_the_complement():
    stage = {"stage_quote": "", "cumulative_n_quote": "6", "stop_if_at_most_quote": "", "continue_if_at_least_quote": "",
             "stop_if_events_at_least_quote": "two or more (>= 2)"}
    r = dr.binary_rule(_base(design_family="single_stage", family="single_stage", outcome="toxicity", stages=[stage]))
    assert r["issues"] == [] and r["outcome"] == "toxicity" and r["success_if_at_least"] == 5      # at most 1 of 6 with a DLT
    q = 0.2                                                                                    # true DLT rate
    assert abs(dr.prob_success(r, 1 - q) - stats.binom.cdf(1, 6, q)) < 1e-12


def test_a_non_binding_futility_stop_is_ignored_for_the_error_rates():
    stages = [{"stage_quote": "", "cumulative_n_quote": "6", "stop_if_at_most_quote": "0", "continue_if_at_least_quote": "", "stop_if_events_at_least_quote": ""},
              {"stage_quote": "", "cumulative_n_quote": "17", "stop_if_at_most_quote": "", "continue_if_at_least_quote": "", "stop_if_events_at_least_quote": ""}]
    r = dr.binary_rule(_base(stages=stages, success_if_at_least_quote="3 or more", p0_quote="0.05", p1_quote="0.35", alpha_quote="0.05",
                             beta_quote="power 0.9", early_stop_binding="non_binding"))
    oc = r["operating_characteristics"]["at_p0"]
    assert abs(oc["prob_success_ignoring_interim"] - stats.binom.sf(2, 17, 0.05)) < 1e-12


def test_count_thresholds_read_fractions_and_strict_inequalities():
    assert dr.bound("p_Efficacy < 8/22", "at_most") == [7.0] and dr.bound("0 or 1", "at_most") == [1.0]
    assert dr.bound("> 4/22", "at_least") == [5.0] and dr.bound("2 or more", "at_least") == [2.0]
    assert dr.bound("p_Efficacy <21/51", "at_least") == [21.0]           # a failure condition leaves the success count at 21
