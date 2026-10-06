"""Lesson L030: qualifiers held by verified quotes are restored deterministically (synthetic fixtures)."""

from clinical_asset.protocol import qualifiers as q


def test_dose_tolerance_and_ranges():
    t = q.dose_tolerance("296±20% MBq")
    assert t["tolerance"] == 20 and t["tolerance_unit"] == "percent" and abs(t["lower"] - 236.8) < 1e-9
    assert q.dose_tolerance("10-20 mg")["upper"] == 20 and q.dose_tolerance("75 mg") is None


def test_sequence_modality_design_and_judgement():
    assert q.sequence("Follow the injection with an IV flush")["relation"] == "after"
    assert q.sequence("given prior to the infusion")["relation"] == "before"
    assert q.modality("this visit should occur at least 24 hours later") == "RECOMMENDED" and q.modality("must occur") is None
    assert q.design_qualifiers("A two-sided paired Wilcoxon Signed Rank Test") == ["paired", "signed rank"]
    leaf = {"kind": "unresolved", "text": "other conditions affecting X, as judged by the investigator.", "status": "REVIEW_REQUIRED"}
    assert q.investigator_judgement(leaf) and leaf["kind"] == "flag" and leaf["status"] == "EXECUTABLE"


def test_day_window_is_not_a_duration():
    spec = {"treatment_phases": [{"phase_id": "P", "duration": {"value": 2.0, "unit": "to", "text": {"text": "Days 2 to 10"}}}]}
    q.enrich(spec)
    assert spec["treatment_phases"][0]["day_window"] == [2.0, 10.0] and spec["treatment_phases"][0]["duration"]["value"] is None


def test_windows_screening_counts_and_not_a_rule():
    leaf = {"kind": "window", "text": "received an IP within five biological half-lives prior to the scan", "relation": "WITHIN_BEFORE",
            "offset": {"value": 5.0, "unit": None}, "status": "REVIEW_REQUIRED"}
    assert q.fix_window(leaf) and leaf["offset"] == {"value": 5.0, "unit": "biological half-lives"} and leaf["status"] == "EXECUTABLE"
    two = {"kind": "window", "text": "within 14 days of Visit 2", "relation": "WITHIN_AFTER", "offset": {"value": 14.0, "unit": "day"}}
    assert q.fix_window(two) and two["relation"] == "WITHIN_EITHER" and (two["min_days"], two["max_days"]) == (-14.0, 14.0)
    after = {"kind": "window", "text": "within 14 days after Visit 2", "relation": "WITHIN_AFTER", "offset": {"value": 14.0, "unit": "day"}}
    assert not q.fix_window(after) and after["relation"] == "WITHIN_AFTER"
    ss = {"quantity": "target_accrual", "value": 60, "evidence": {"text": "Approximately 60 patients will be screened for inclusion"}}
    assert q.screening_count(ss) and ss["quantity"] == "planned_screened"
    enrolled = {"quantity": "target_accrual", "value": 60, "evidence": {"text": "60 patients will be screened and enrolled"}}
    assert not q.screening_count(enrolled)


def test_window_after_a_study_entry_event_stays_one_sided():
    leaf = {"kind": "window", "text": "Schedule patient for Visit 2 within 14 days of consent.", "relation": "WITHIN_AFTER",
            "anchor": "consent", "offset": {"value": 14.0, "unit": "day"}}
    q.fix_window(leaf)
    assert leaf["relation"] == "WITHIN_AFTER"
