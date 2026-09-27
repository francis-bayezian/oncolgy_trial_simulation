"""Per-arm binary decision rules (synthetic fixtures; no protocol-specific content)."""

import numpy as np

from clinical_asset.protocol import design_rules as dr
from clinical_asset.trial import binary as bn
from clinical_asset.trial import recruitment as rc


def _rule():
    raw = {"stages": [{"cumulative_n_quote": "10", "stop_if_at_most_quote": "0 or 1", "continue_if_at_least_quote": ""},
                      {"cumulative_n_quote": "22", "stop_if_at_most_quote": "", "continue_if_at_least_quote": ""}],
           "success_if_at_least_quote": "6 or more", "p0_quote": "p0=0.15", "p1_quote": "p1=0.40", "alpha_quote": "alpha=0.10",
           "beta_quote": "beta = 0.10", "early_termination_probability_quote": "54%"}
    b = dr.binary_rule(raw)
    return {"decision_rule_id": "DR1", "kind": "binary", "role": "primary", "arms": ["ARM1"], "arm_quotes": [], "cohort": {"text": "all"},
            "design_family": "simon_optimal", "rule": b, "status": "EXECUTABLE", "compile_issues": b["issues"]}


def test_simulated_runs_agree_with_the_exact_curve_which_rises_with_the_true_rate():
    rule = _rule()
    curve = bn.exact_curve(rule, [0.1, 0.3, 0.5])
    assert curve[0]["prob_of_interest"] < curve[1]["prob_of_interest"] < curve[2]["prob_of_interest"]
    sim = bn.simulate_rule(rule, 0.3, np.random.default_rng(1), 20000)
    assert abs(sim["prob_of_interest_simulated"] - curve[1]["prob_of_interest"]) < 0.01
    assert abs(sim["prob_early_stop_simulated"] - curve[1]["prob_early_stop"]) < 0.01
    assert sim["enrolled"]["q05"] in (10.0, 22.0) and sim["enrolled"]["q95"] == 22.0


def test_an_exact_single_proportion_test_defines_its_success_threshold():
    raw = {"stages": [{"cumulative_n_quote": "26", "stop_if_at_most_quote": "", "continue_if_at_least_quote": ""}],
           "success_if_at_least_quote": "", "p0_quote": "p0=0.35", "p1_quote": "p1=0.60", "alpha_quote": "alpha = 0.05",
           "beta_quote": "", "early_termination_probability_quote": ""}
    b = dr.binary_rule(raw)
    r = b["success_if_at_least"]
    from scipy import stats
    assert stats.binom.sf(r - 1, 26, 0.35) <= 0.05 < stats.binom.sf(r - 2, 26, 0.35) and b["issues"] == [] and b["success_derivation"]


class RateModel:
    def __init__(self, verdict="FAITHFUL"):
        self.verdict = verdict

    def extract(self, task, schema, payload):
        if task == "binary_rate_bindings":
            return {"bindings": [{"decision_rule_id": "DR1", "fact_id": "F1", "reason": ""}]}
        return {"verdicts": [{"item_id": i["item_id"], "verdict": self.verdict, "problem": "none", "problem_quote": "", "reviewer_note": ""}
                             for i in payload["items"]]}


def test_a_cited_rate_is_used_only_when_the_verifier_majority_confirms_it():
    spec = {"arms": [{"arm_id": "ARM1", "label": {"text": "Drug X"}, "description": None}], "decision_rules": [_rule()]}
    facts = [{"fact_id": "F1", "kind": "response_rate", "value": {"value": 0.35, "scale": "proportion"}, "rendering": "35% responded",
              "evidence": {"text": "35% responded"}}]
    ok = bn.bind_cited_rates(RateModel(), spec, facts, section_text=None, votes=3, workers=2)
    assert ok[0]["status"] == "USABLE" and ok[0]["rate"] == 0.35
    assert bn.bind_cited_rates(RateModel("INCORRECT"), spec, facts, section_text=None, votes=3, workers=2)[0]["status"] == "REVIEW_REQUIRED"


def test_enrollment_without_an_accrual_rate_keeps_the_order_but_not_the_time():
    order, days, alloc = rc.enrollment_draws(100, 20, None, [1.0], np.random.default_rng(0))
    assert list(days) == list(range(1, 21)) and len(set(order)) == 20 and set(alloc) == {0}


def test_without_an_executable_rule_the_primary_rate_is_estimated_not_decided():
    spec = {"arms": [{"arm_id": "ARM1", "label": {"text": "Drug X"}, "status": "open"}], "decision_rules": [],
            "endpoints": [{"role": "primary", "type": "binary", "status": "EXECUTABLE", "name": {"text": "response"}}],
            "sample_size": [{"quantity": "evaluable_target", "value": 26.0, "evidence": {"text": "26 patients evaluable"}}]}
    rules = bn.descriptive_rules(spec)
    assert len(rules) == 1 and rules[0]["rule"]["stages"][0]["n"] == 26 and rules[0]["rule"]["success_if_at_least"] is None
    curve = bn.exact_curve(rules[0], [0.3])
    sim = bn.simulate_rule(rules[0], 0.3, np.random.default_rng(0), 4000)
    assert curve[0]["prob_of_interest"] is None and sim["prob_of_interest_simulated"] == 0.0 and abs(sim["observed_rate"]["median"] - 0.3) < 0.05
    spec["endpoints"][0]["role"] = "safety"
    assert bn.descriptive_rules(spec) == []                   # safety endpoints are not estimated as efficacy
