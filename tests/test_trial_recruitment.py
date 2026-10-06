"""Milestones 7-8: recruitment and enrolled cohort (synthetic fixtures; no protocol-specific content)."""

import numpy as np

from clinical_asset.trial import recruitment as rc


def _size(quantity, value, evidence):
    return {"quantity": quantity, "value": value, "unit": "patients", "evidence": {"text": evidence}}


def _spec():
    stage = {"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": "var:stage", "op": "in", "categories": ["M0"]}
    return {"sample_size": [_size("target_accrual", 100, "accrue 100 patients"), _size("maximum_accrual", 120, "maximum accrual becomes 120"),
                            _size("accrual_rate", 40, "about 40 patients could be enrolled every year"),
                            _size("accrual_rate", 60, "we expect an accrual rate of at least 60 per year"),
                            _size("accrual_rate", 30, "Accrual rates of 30/year or less will be of concern")],
            "arms": [{"arm_id": "ARM1", "label": {"text": "ARM A"}, "status": "open"}, {"arm_id": "ARM2", "label": {"text": "ARM B"}, "status": "open"},
                     {"arm_id": "ARM3", "label": {"text": "ARM C"}, "status": "closed"}],
            "randomization": {"method": {"text": "via web system"}, "arms": [{"text": "Arm A (control)"}, {"text": "Arm B (experimental)"}],
                              "allocation": {"ratio": [2.0, 1.0], "derivation": "STATED"}},
            "stratification": {"strata": [{"stratum_id": "ST1", "status": "EXECUTABLE", "logic": stage, "rendering": "M0"}]}}


def test_accrual_plan_uses_stated_estimates_as_scenarios_and_excludes_thresholds():
    plan = rc.accrual_plan(_spec())
    assert plan["target"]["patients"] == 120 and plan["target"]["source"] == "maximum_accrual"
    assert [s["rate_per_year"] for s in plan["scenarios"]] == [40.0, 60.0]
    assert plan["scenarios"][0]["scenario"] == "accrual_40_per_year"
    assert [x["rate_per_year"] for x in plan["excluded_rates"]] == [30.0]


def test_randomization_uses_open_randomized_arms_and_reports_missing_balancing():
    r = rc.randomization_plan(_spec())
    assert [a["arm_id"] for a in r["arms"]] == ["ARM1", "ARM2"] and r["ratio"] == [2.0, 1.0]
    assert r["balancing"].startswith("not stated")


def test_enrollment_follows_rate_ratio_and_assigns_every_stratum():
    spec = _spec()
    plan, rand = rc.accrual_plan(spec), rc.randomization_plan(spec)
    plan["target"]["patients"] = 3000
    pool = [{"patient_id": f"P{i}", **({"var:stage": "M0"} if i % 2 else {})} for i in range(5000)]
    elig = {p["patient_id"]: {"status": "UNDETERMINED", "unknown": ["EL9"]} for p in pool}
    cohort = rc.enroll(pool, elig, plan, rand, rate=60.0, seed=3)
    years = cohort[-1]["enrollment_day"] / 365.25
    assert abs(years - 50.0) < 3.0                                       # 3000 patients at 60 per year
    assert abs(np.mean([c["arm_id"] == "ARM1" for c in cohort]) - 2 / 3) < 0.03
    strata = {c["stratum"] for c in cohort}
    assert "UNRESOLVED" not in strata and strata <= {s["stratum_id"] for s in rand["strata"]} and cohort[0]["unchecked_criteria"] == ["EL9"]
    assert any(c.get("stratum_assigned") for c in cohort)              # undecidable strata are drawn, and flagged
    assert len({c["patient_id"] for c in cohort}) == 3000                # each patient enrolled at most once


def test_a_report_is_written_when_no_accrual_rate_is_stated():
    doc = {"recruitment_version": "v", "accrual_plan": {"target": {"patients": 5, "source": "maximum_accrual"},
                                                      "scenarios": [{"scenario": "accrual_rate_unresolved", "rate_per_year": None, "evidence": "none"}],
                                                      "excluded_rates": []},
           "randomization": {"arms": [{"label": "A"}], "ratio": None, "ratio_derivation": "NOT_STATED", "method_text": "", "balancing": "not stated"},
           "summary": {"pool": 10, "scenarios": {"accrual_rate_unresolved": {"enrolled": 5, "accrual_years": 0.0, "arms": {}, "strata": {},
                                                                              "sex": {}, "age_mean": 50.0}}}}
    text = rc._report(doc)
    assert "no rate" in text and "an unresolved time" in text
