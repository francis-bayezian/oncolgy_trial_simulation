"""Milestone 5: source population (synthetic fixtures; no protocol-specific content)."""

import numpy as np

from clinical_asset.protocol import expressions as ex
from clinical_asset.trial import population as pop


def _leaf(var, kind, **kw):
    return {"node": "LEAF", "kind": kind, "status": "EXECUTABLE", "variable": var, "text": var, **kw}


def _spec():
    age = _leaf("demographic:age", "range", lower=3.0, upper=22.0, unit="year")
    stage = _leaf("var:stage", "category", op="in", categories=["Stage A", "Stage B"])
    size = _leaf("var:size", "compare", op=">", value=1.5, unit="cm2")
    lab = _leaf("var:lab", "compare", op=">=", value=750, unit="/ul")
    return {"variables": [{"key": "var:stage", "label": "stage"}, {"key": "var:size", "label": "size"}, {"key": "var:lab", "label": "lab"},
                          {"key": "demographic:age", "label": "age"}],
            "eligibility": [{"criterion_id": "EL1", "kind": "inclusion", "status": "EXECUTABLE", "logic": age},
                            {"criterion_id": "EL2", "kind": "inclusion", "status": "EXECUTABLE",
                             "logic": {"node": "AND", "children": [stage, size]}},
                            {"criterion_id": "EL3", "kind": "inclusion", "status": "EXECUTABLE", "logic": lab}],
            "stratification": {"strata": []}}


def _fact(fid, value, scale="proportion", numerator=None, category=None, evidence="text"):
    v = {"value": value, "scale": scale}
    if numerator is not None:
        v.update(numerator=numerator, denominator=numerator / value)
    return {"fact_id": fid, "kind": "characteristic_distribution", "value": v, "rendering": f"fact {fid}",
            "evidence": {"text": evidence}, "category": {"text": category} if category else None, "population": None}


def test_catalog_and_age_limits_come_from_the_rules():
    cat = pop.variable_catalog(_spec())
    assert cat["var:stage"]["categories"] == ["Stage A", "Stage B"] and cat["var:size"]["conditions"][0]["item"] == "EL2"
    assert cat["demographic:sex"]["categories"] == ["female", "male"] and "demographic:age" not in cat
    assert pop.age_limits(_spec()) == (3.0, 22.0)


def test_category_matching_and_thresholds():
    assert pop._match_category("stage a", ["Stage A", "Stage B"]) == "Stage A"
    assert pop._match_category("American Indian or Alaskan Native", list(pop.V3_RACE)) == "american_indian_or_alaska_native"
    assert pop._match_category("Unknown", list(pop.V3_ETHNICITY)) == "unknown_or_not_reported"
    assert pop._match_category("Females", ["female", "male"]) == "female"
    assert pop._match_category("Stage C", ["Stage A", "Stage B"]) is None
    assert pop._threshold("residual measuring at least 1.5 cm2") == {"op": ">=", "value": 1.5, "unit": "cm2"}


def test_threshold_shares_give_intervals_that_evaluate_three_valued():
    leaf = _leaf("v", "compare", op=">", value=1.5, unit="cm2")
    t = {"op": ">=", "value": 1.5, "unit": "cm2"}
    meets, fails = pop._interval_for(t, True), pop._interval_for(t, False)
    assert ex.evaluate(leaf, {"v": fails}) is False and ex.evaluate(leaf, {"v": meets}) is None   # >= 1.5 need not be > 1.5
    t2 = {"op": ">", "value": 1.5, "unit": "cm2"}
    assert ex.evaluate(leaf, {"v": pop._interval_for(t2, True)}) is True
    for op in (">", ">=", "<", "<="):
        for yes in (True, False):
            probe = _leaf("v", "compare", op=op, value=1.5, unit="cm2")
            assert ex.evaluate(probe, {"v": pop._interval_for({"op": op, "value": 1.5, "unit": "cm2"}, yes)}) is yes


class BindingModel:
    def __init__(self, bindings, verdict="FAITHFUL"):
        self.bindings, self.verdict, self.calls = bindings, verdict, []

    def extract(self, task, schema, payload):
        self.calls.append(task)
        if task == "population_bindings":
            return {"bindings": self.bindings}
        return {"verdicts": [{"item_id": i["item_id"], "verdict": self.verdict, "problem": "none", "problem_quote": "",
                              "reviewer_note": ""} for i in payload["items"]]}


def _b(fid, kind, var="", cat="", var2="", cat2="", item=""):
    return {"fact_id": fid, "kind": kind, "variable": var, "category": cat, "variable_2": var2, "category_2": cat2,
            "condition_item": item, "reason": ""}


def test_bindings_are_checked_then_verified_by_majority():
    facts = [_fact("F1", 0.6, numerator=60, category="Stage A"), _fact("F2", 0.34, numerator=34, category="size at least 1.5 cm2"),
             _fact("F3", 0.2, category="Stage Z"), _fact("F4", 12.0, scale="number")]
    model = BindingModel([_b("F1", "share_of_category", "var:stage", "stage a"), _b("F2", "share_meeting_condition", "var:size", "size", item="EL2"),
                          _b("F3", "share_of_category", "var:stage", "Stage Z"), _b("F4", "share_of_category", "var:stage", "Stage B")])
    bindings = {b["fact_id"]: b for b in pop.bind_facts(model, _spec(), facts, votes=3, workers=2)}
    assert bindings["F1"]["status"] == "USABLE" and bindings["F1"]["category"] == "Stage A"
    assert bindings["F2"]["status"] == "USABLE" and bindings["F2"]["threshold"] == {"op": ">=", "value": 1.5, "unit": "cm2"}
    assert bindings["F3"]["status"] == "REVIEW_REQUIRED" and "not a category" in bindings["F3"]["issues"][0]
    assert bindings["F4"]["status"] == "REVIEW_REQUIRED" and "not a share" in bindings["F4"]["issues"][0]
    assert model.calls.count("protocol_verify") == 12
    rejected = pop.bind_facts(BindingModel([_b("F1", "share_of_category", "var:stage", "Stage A")], "INCORRECT"), _spec(), facts, votes=3, workers=2)
    assert rejected[0]["status"] == "REVIEW_REQUIRED"


def test_population_model_uses_joint_counts_shares_and_leaves_the_rest_unknown():
    facts = [_fact("F1", 0.6, numerator=60, category="Stage A"), _fact("F2", 0.34, numerator=34, category="size at least 1.5 cm2")]
    counts = {"J1": ("female", "white", 30), "J2": ("male", "white", 50), "J3": ("female", "asian", 10), "J4": ("male", "asian", 10),
              "J5": ("female", "hispanic_or_latino", 5), "J6": ("male", "hispanic_or_latino", 5),
              "J7": ("female", "not_hispanic_or_latino", 35), "J8": ("male", "not_hispanic_or_latino", 55)}
    bindings = [{**_b("F1", "share_of_category", "var:stage", "Stage A"), "status": "USABLE"},
                {**_b("F2", "share_meeting_condition", "var:size", "size", item="EL2"), "status": "USABLE",
                 "threshold": {"op": ">=", "value": 1.5, "unit": "cm2"}}]
    for fid, (sex, other, n) in counts.items():
        facts.append(_fact(fid, float(n), scale="number"))
        var = "demographic:ethnicity" if "hispanic" in other else "demographic:race"
        bindings.append({**_b(fid, "joint_count", "demographic:sex", sex, var, other), "status": "USABLE"})
    v3 = {"p_female": 0.4, "race_probabilities": {"white": 1.0}, "ethnicity_probabilities": {"not_hispanic_or_latino": 1.0}}
    model = pop.population_model(_spec(), facts, bindings, v3)
    assert model["demographic:sex"]["source"] == "protocol_projection" and abs(model["demographic:sex"]["probabilities"]["female"] - 0.4) < 1e-9
    assert model["demographic:race"]["given_sex"]["female"] == {"white": 0.75, "asian": 0.25}
    assert model["var:stage"]["probabilities"] == {"Stage A": 0.6, None: 0.4}           # the unstated rest stays unknown
    assert model["var:size"]["type"] == "threshold_share" and model["_unresolved"] == ["var:lab"]
    patients = pop.sample_population(model, {"age": np.full(4000, 10.0)}, 4000, seed=1)
    stage_a = np.mean([p.get("var:stage") == "Stage A" for p in patients])
    unknown = np.mean(["var:stage" not in p for p in patients])
    assert abs(stage_a - 0.6) < 0.03 and abs(unknown - 0.4) < 0.03 and all("var:lab" not in p for p in patients)
    females = [p for p in patients if p["demographic:sex"] == "female"]
    assert abs(np.mean([p["demographic:race"] == "asian" for p in females]) - 0.25) < 0.04


def test_inconsistent_shares_are_unresolved_not_renormalised():
    facts = [_fact("F1", 0.7, numerator=70, category="Stage A"), _fact("F2", 0.5, numerator=50, category="Stage B")]
    bindings = [{**_b("F1", "share_of_category", "var:stage", "Stage A"), "status": "USABLE"},
                {**_b("F2", "share_of_category", "var:stage", "Stage B"), "status": "USABLE"}]
    v3 = {"p_female": 0.4, "race_probabilities": {"white": 1.0}, "ethnicity_probabilities": {"not_hispanic_or_latino": 1.0}}
    assert pop.population_model(_spec(), facts, bindings, v3)["var:stage"]["type"] == "unresolved"


def test_an_exclusive_whole_year_upper_age_is_the_same_class_as_inclusive_one_year_less():
    spec = _spec()
    spec["eligibility"][0]["logic"]["upper_inclusive"] = False
    assert pop.age_limits(spec) == (3.0, 22.0) and pop.age_class_bounds(spec) == (3.0, 21.0)
    spec["eligibility"][0]["logic"]["upper_inclusive"] = True
    assert pop.age_class_bounds(spec) == (3.0, 22.0)


def test_a_bound_is_not_a_share_to_sample_from():
    fact = {**_fact("F1", 0.3, category="Stage A"), "qualifier": "less than"}
    b = pop.bind_facts(BindingModel([_b("F1", "share_of_category", "var:stage", "Stage A")]), _spec(), [fact], votes=1, workers=1)[0]
    assert b["status"] == "REVIEW_REQUIRED" and "states a bound" in b["issues"][0]
