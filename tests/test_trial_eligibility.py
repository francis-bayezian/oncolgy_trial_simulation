"""Milestone 6: eligibility and feasibility (synthetic fixtures; no protocol-specific content)."""

from clinical_asset.trial import eligibility as el


def _leaf(var, kind, **kw):
    return {"node": "LEAF", "kind": kind, "status": "EXECUTABLE", "variable": var, **kw}


def _crit(cid, kind, logic, status="EXECUTABLE", modality="REQUIRED"):
    return {"criterion_id": cid, "kind": kind, "logic": logic, "status": status, "modality": modality, "rendering": cid}


def _spec():
    return {"eligibility": [
        _crit("EL1", "inclusion", _leaf("demographic:age", "range", lower=3, upper=22, unit="year", upper_inclusive=False)),
        _crit("EL2", "exclusion", _leaf("var:stage", "category", op="in", categories=["M4"]), modality="PROHIBITED"),
        _crit("EL3", "inclusion", _leaf("var:lab", "compare", op=">=", value=750)),
        _crit("EL4", "inclusion", _leaf("timing:mri_from_surgery", "window", min_days=0, max_days=28)),
        _crit("EL5", "inclusion", _leaf("var:x", "flag", expected=True), modality="OPTIONAL"),
        _crit("EL6", "inclusion", _leaf("var:y", "flag", expected=True), status="REVIEW_REQUIRED"),
        _crit("EL7", "note", None)]}


def test_criteria_are_classified_by_how_they_can_be_checked():
    groups = {k: [c["criterion_id"] for c in v] for k, v in el.classify_criteria(_spec()).items()}
    assert groups == {"evaluated": ["EL1", "EL2", "EL3", "EL6"], "procedural": ["EL4"], "permissive": ["EL5"],
                      "run_with_review_flag": ["EL6"], "informational": ["EL7"]}


def test_patients_are_evaluated_three_valued_before_resolution():
    criteria = [c for c in el.classify_criteria(_spec())["evaluated"] if c["criterion_id"] != "EL6"]
    eligible = {"demographic:age": {"value": 10, "unit": "year"}, "var:stage": "M0", "var:lab": 900}
    too_old = {**eligible, "demographic:age": {"value": 22, "unit": "year"}}
    excluded = {**eligible, "var:stage": "M4"}
    lab_unknown = {k: v for k, v in eligible.items() if k != "var:lab"}
    assert el.evaluate_patient(criteria, eligible) == {"status": "ELIGIBLE", "failed": [], "unknown": []}
    assert el.evaluate_patient(criteria, too_old)["failed"] == ["EL1"]
    assert el.evaluate_patient(criteria, excluded) == {"status": "INELIGIBLE", "failed": ["EL2"], "unknown": []}
    assert el.evaluate_patient(criteria, lab_unknown) == {"status": "UNDETERMINED", "failed": [], "unknown": ["EL3"]}


def test_every_patient_is_decided_and_unknowns_follow_the_screen_pass_rate():
    """No patient stays UNDETERMINED: unanswerable criteria are calibrated so the eligible share matches the evidence
    screen pass rate (A16)."""
    spec = {"eligibility": [_crit("EL1", "inclusion", _leaf("demographic:age", "range", lower=18, upper=None, unit="year")),
                            _crit("EL2", "inclusion", _leaf("var:lab", "compare", op=">=", value=750)),
                            _crit("EL3", "exclusion", _leaf("var:history", "flag", expected=True))]}
    patients = [{"patient_id": f"P{i}", "demographic:age": {"value": 10 if i < 1000 else 50, "unit": "year"}} for i in range(5000)]
    results, summary = el.assess(spec, patients, {"value": 0.6, "source": "test"}, seed=1)
    assert {r["status"] for r in results} == {"ELIGIBLE", "INELIGIBLE"} and summary["status_counts"]["UNDETERMINED"] == 0
    assert abs(summary["eligible_share"] - 0.6) < 0.03                      # 20% fail on age; the unknowns supply the rest
    assert sorted(summary["unknown_resolution"]["criteria"]) == ["EL2", "EL3"]
    assert summary["decisive_exclusions"]["EL1"] == 1000


def test_a_criterion_excluding_a_whole_demographic_group_is_flagged():
    sex = {"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": "demographic:sex", "op": "in", "categories": ["female"]}
    spec = {"eligibility": [_crit("EL1", "inclusion", sex)]}
    patients = [{"patient_id": f"P{i}", "demographic:sex": "female" if i % 2 else "male"} for i in range(60)]
    _, summary = el.assess(spec, patients)
    assert summary["plausibility_warnings"] and "['male']" in summary["plausibility_warnings"][0]
