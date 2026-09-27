import json

from clinical_asset.planning.asset import build, classify
from clinical_asset.planning.events import simulate_cure_calendar
from clinical_asset.planning.operations import extract as extract_operations
from clinical_asset.planning.report import _conditional_enrollment


def test_completion_is_only_a_bound_not_an_accrual_rate():
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT00000001"},
        "statusModule": {"startDateStruct": {"date": "2020-01-01"},
                         "primaryCompletionDateStruct": {"date": "2022-01-01"}},
        "designModule": {"enrollmentInfo": {"count": 100, "type": "ACTUAL"}},
    }}
    row = classify(study)
    assert row["quality"] == "ACCRUAL_INTERVAL_CENSORED"
    assert row["duration_upper_bound_months"] > 23
    assert row["accrual_duration_months"] is None
    assert row["patients_per_site_month"] is None


def test_explicit_recruitment_window_is_used_but_followup_is_not():
    study = {"protocolSection": {
        "identificationModule": {"nctId": "NCT00000001"},
        "statusModule": {"startDateStruct": {"date": "2020-01-01"},
                         "primaryCompletionDateStruct": {"date": "2025-01-01"}},
        "designModule": {"enrollmentInfo": {"count": 60, "type": "ACTUAL"}},
        "contactsLocationsModule": {"locations": [{"facility": "A", "country": "US"}]},
    }, "resultsSection": {"participantFlowModule": {
        "recruitmentDetails": "Recruitment began in January 2020 and ended in January 2022; follow-up ended January 2025."}}}
    row = classify(study)
    assert row["quality"] == "ACCRUAL_DERIVED"
    assert 23 < row["accrual_duration_months"] < 25
    assert 2 < row["patients_per_site_month"] < 3


def test_screening_and_retention_preserve_distinct_denominators():
    study = {"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}},
             "resultsSection": {"participantFlowModule": {
                 "recruitmentDetails": "100 patients were screened; 60 patients were enrolled.",
                 "periods": [{"title": "Overall Study", "milestones": [
                     {"type": "STARTED", "achievements": [{"groupId": "A", "numSubjects": "60"}]},
                     {"type": "COMPLETED", "achievements": [{"groupId": "A", "numSubjects": "45"}]}],
                     "dropWithdraws": [{"type": "Lost to Follow-up", "reasons": [{"groupId": "A", "numSubjects": "3"}]}]}]}}}
    screening, retention = extract_operations(study)
    assert screening["quality"] == "DIRECT" and screening["conversion"] == .6
    assert retention[0]["completion_fraction"] == .75
    assert json.loads(retention[0]["reasons"])["loss_to_followup"] == 3
    assert retention[0]["time_to_dropout"] is None


def test_planning_asset_excludes_holdout_before_loading_registry(tmp_path):
    manifest = tmp_path / "manifest.json"
    holdout = tmp_path / "holdout.json"
    raw = tmp_path / "raw"
    raw.mkdir()
    manifest.write_text(json.dumps({"trials": [{"nct_id": "NCT00000001"}, {"nct_id": "NCT00000002"}]}))
    holdout.write_text(json.dumps({"nct_ids": ["NCT00000002"]}))
    (raw / "NCT00000001.json").write_text(json.dumps({"protocolSection": {
        "identificationModule": {"nctId": "NCT00000001"}}}))
    # The holdout file deliberately does not exist; the builder must never ask for it.
    result = build(manifest, holdout, raw, tmp_path / "asset")
    assert result["records"] == 1
    assert result["missing_raw"] == []
    assert result["model"]["status"] == "UNRESOLVED"


def test_protocol_timing_is_conditional_on_rate():
    fast = _conditional_enrollment(100, 60, 5000, 1)
    slow = _conditional_enrollment(100, 30, 5000, 1)
    assert 19 < fast["median"] < 21
    assert 39 < slow["median"] < 41
    assert fast["probability_by_month_18"] > slow["probability_by_month_18"]


def test_event_maturity_moves_with_accrual_and_does_not_force_unreachable_thresholds():
    survival = {"family": "cure_model", "status": "RESOLVED", "cure_fraction": .5,
                "failure_rate_per_year": 1.0}
    fast = simulate_cure_calendar(100, 100, survival, {}, [20, 101], draws=500, seed=1)
    slow = simulate_cure_calendar(100, 25, survival, {}, [20], draws=500, seed=1)
    assert fast["thresholds"]["20"]["month_from_first_patient"]["median"] < slow["thresholds"]["20"]["month_from_first_patient"]["median"]
    assert fast["thresholds"]["101"]["reach_probability"] == 0
    assert fast["thresholds"]["101"]["month_from_first_patient"] is None
