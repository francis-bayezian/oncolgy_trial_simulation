"""Milestone 11: outcome model (synthetic fixtures; no protocol-specific content)."""

import json
import math

import numpy as np

from clinical_asset.trial import outcomes as oc


def _fact(fid, kind, value, scale="proportion", text=None, qualifier=None):
    return {"fact_id": fid, "kind": kind, "value": {"value": value, "scale": scale}, "rendering": f"fact {fid}",
            "evidence": {"text": text or f"text {fid}"}, "qualifier": qualifier, "value_text": {"text": f"{value}"}}


def test_cure_model_is_fixed_by_the_cure_rate_and_one_time_point_and_sampled_exactly():
    items = [{"role": "efs_model_family", "family": "cure_model", "quote": "a cure model", "status": "USABLE"},
             {"role": "control_cure_rate", "fact_id": "F1", "status": "USABLE"},
             {"role": "control_efs_timepoint", "fact_id": "F2", "years": 2.0, "status": "USABLE"}]
    facts = [_fact("F1", "event_free_survival", 0.5), _fact("F2", "event_free_survival", 0.6)]
    m = oc.control_efs({"items": items}, facts)
    assert m["status"] == "RESOLVED" and abs(oc.efs_survival(np.array([2.0]), m)[0] - 0.6) < 1e-12
    rng = np.random.default_rng(0)
    for hr in (1.0, 0.6):
        t = oc.sample_efs_years(200_000, m, hr, rng)
        for year in (1.0, 3.0, 50.0):
            assert abs(np.mean(t > year) - oc.efs_survival(np.array([year]), m, hr)[0]) < 0.004
    assert abs(np.mean(np.isinf(oc.sample_efs_years(200_000, m, 0.6, rng))) - 0.5 ** 0.6) < 0.004


def test_cure_model_without_a_stated_family_or_cure_rate_is_unresolved():
    facts = [_fact("F1", "event_free_survival", 0.5)]
    items = [{"role": "control_cure_rate", "fact_id": "F1", "status": "USABLE"}]
    assert oc.control_efs({"items": items}, facts)["status"] == "UNRESOLVED"


def test_design_alternative_is_the_ratio_of_log_cure_rates():
    spec = {"analyses": [{"effects": [{"text": "15% increase in long-term EFS (56% to 71%, RFR=0.591)"}, {"text": "no numbers"}]}]}
    alt = oc.design_alternatives(spec)
    assert len(alt) == 1 and abs(alt[0]["hr"] - 0.591) < 0.0005 and alt[0]["control_long_term"] == 0.56


def test_random_effects_prior_and_add_on_orientation(tmp_path):
    rows = [{"fusion_id": "a", "endpoint": "progression_free_survival", "disease": "d1", "treatment": "drug x + radiation therapy",
             "comparator": "radiation therapy", "hr_population_posterior": {"median": 0.8, "q025": 0.64, "q975": 1.0}},
            {"fusion_id": "b", "endpoint": "progression_free_survival", "disease": "d2", "treatment": "radiotherapy + placebo",
             "comparator": "drug y + radiotherapy", "hr_population_posterior": {"median": 1.25, "q025": 1.0, "q975": 1.5625}},
            {"fusion_id": "c", "endpoint": "overall_survival", "disease": "d3", "treatment": "drug z + radiation therapy",
             "comparator": "radiation therapy", "hr_population_posterior": {"median": 0.5, "q025": 0.4, "q975": 0.6}},
            {"fusion_id": "d", "endpoint": "progression_free_survival", "disease": "d4", "treatment": "drug a + radiation therapy",
             "comparator": "drug b + radiation therapy", "hr_population_posterior": {"median": 0.5, "q025": 0.4, "q975": 0.6}}]
    path = tmp_path / "index.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    cs = oc.add_on_radiotherapy_comparisons(path)
    assert [c["fusion_id"] for c in cs] == ["a", "b"]                   # OS and non-add-on comparisons are excluded
    assert abs(cs[1]["hr_add_on"] - 0.8) < 1e-9                         # the add-on is the comparator: HR inverted
    prior = oc.random_effects_prior(cs)
    assert abs(prior["hr_median"] - 0.8) < 1e-6 and prior["tau2"] == 0.0
    assert oc.random_effects_prior([])["status"] == "UNRESOLVED"


def test_loss_to_follow_up_and_off_study_limit_come_from_the_spec():
    spec = {"sample_size": [{"quantity": "censoring_rate", "value": 1.0, "evidence": {"text": "with an annual 1% censoring rate"}}],
            "discontinuation_rules": [{"rule_id": "DC1", "scope": "off_study", "criterion": {"text": "tenth anniversary"},
                                       "time_limit": {"days": 3652.5, "canonical_anchor": "study_enrollment"}}]}
    ltf = oc.loss_to_follow_up(spec)
    assert ltf["status"] == "RESOLVED" and abs(ltf["rate_per_year"] + math.log(0.99)) < 1e-12
    assert oc.off_study_limit(spec)["days"] == 3652.5
    unstated = oc.loss_to_follow_up({"sample_size": [], "metadata": {}})        # registry evidence, never left unresolved
    assert unstated["status"] in ("RESOLVED", "ASSUMED_NONE") and unstated["rate_per_year"] >= 0


def test_nearest_class_signature_prefers_fewest_differences_then_subsets():
    sigs = {"a+b+c": 10, "a+b": 50, "a+b+c+d+e": 99, "a+b+x": 70}
    near = oc.nearest_class_signature({"a", "b", "c", "d"}, sigs)
    assert near["class_signature"] == "a+b+c" and near["missing_classes"] == ["d"] and near["extra_classes"] == []


class OutcomeModel:
    def __init__(self, out):
        self.out = out

    def extract(self, task, schema, payload):
        if task == "outcome_bindings":
            return self.out
        return {"verdicts": [{"item_id": i["item_id"], "verdict": "FAITHFUL", "problem": "none", "problem_quote": "",
                              "reviewer_note": ""} for i in payload["items"]]}


def test_outcome_bindings_are_checked_and_thresholds_are_not_rates():
    facts = [_fact("F1", "event_free_survival", 0.5), _fact("F2", "event_free_survival", 0.6),
             _fact("F3", "toxicity_rate", 0.2), _fact("F4", "toxicity_rate", 0.3, qualifier="at least"),
             _fact("F5", "dropout_or_evaluability", 0.1)]
    out = {"control_arm_id": "ARM1", "control_arm_reason": "", "efs_model_family": "cure_model", "efs_model_quote": "a cure model",
           "cure_fact_id": "F1", "timepoint_facts": [{"fact_id": "F2", "years": 2}],
           "toxicities": [{"fact_id": "F3", "event": "hearing loss", "grade": "3", "applies_to": "all_arms", "arm_id": ""},
                          {"fact_id": "F4", "event": "hearing loss", "grade": "4", "applies_to": "all_arms", "arm_id": ""}],
           "analysis_evaluable_target_ref": "SS1", "analysis_population_quote": "patients", "analysis_followup_years": 1.0,
           "analysis_rule_quote": "The final analysis is done once 280 patients are followed for 1 year.", "analysis_exclusion_ref": "F5"}
    size = [{"quantity": "evaluable_target", "value": 280.0, "evidence": {"text": "280 evaluable"}},
            {"quantity": "followup_duration", "value": 1.0, "evidence": {"text": "followed for at least 1 year"}}]
    for f in facts:
        f["sections"] = ["5.0"]
    b = oc.bind_outcomes(OutcomeModel(out), [{"arm_id": "ARM1", "label": "A"}, {"arm_id": "ARM2", "label": "B"}], facts,
                         section_text=lambda f: ("5.0 STATISTICS The control group is represented by a cure model. The final analysis is done once 280 "
                                                 "patients are followed for 1 year."), votes=3, workers=2,
                         sample_size=size)
    status = {(it["role"], it.get("fact_id") or it.get("ref")): it["status"] for it in b["items"]}
    assert status[("toxicity_incidence", "F3")] == "USABLE" and status[("toxicity_incidence", "F4")] == "REVIEW_REQUIRED"
    assert status[("analysis_rule", "SS1")] == "USABLE" and status[("analysis_exclusion", "F5")] == "USABLE"
    assert oc.control_efs(b, facts)["status"] == "RESOLVED"


def test_a_model_family_quote_not_in_the_protocol_is_rejected():
    facts = [_fact("F1", "event_free_survival", 0.5)]
    facts[0]["sections"] = ["5.0"]
    out = {"control_arm_id": "ARM1", "control_arm_reason": "", "efs_model_family": "cure_model", "efs_model_quote": "an invented sentence",
           "cure_fact_id": "F1", "timepoint_facts": [], "toxicities": [], "analysis_evaluable_target_ref": "", "analysis_population_quote": "",
           "analysis_followup_years": 0, "analysis_rule_quote": "", "analysis_exclusion_ref": ""}
    b = oc.bind_outcomes(OutcomeModel(out), [{"arm_id": "ARM1", "label": "A"}], facts, section_text=lambda f: "5.0 text", votes=1, workers=1)
    family = next(it for it in b["items"] if it["role"] == "efs_model_family")
    assert family["status"] == "REVIEW_REQUIRED" and "not in the protocol text" in family["issues"][0]
