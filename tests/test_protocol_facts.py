"""Quantitative protocol facts (synthetic fixtures; no protocol-specific content)."""

import json

from clinical_asset.protocol import facts as fx
from clinical_asset.protocol.ingest import Document, Line, Section


def _doc():
    st = Section("5.0", "STATISTICS", 1, 4, 4, 0.0, [
        Line(4, 1.0, "In the earlier study XYZ-0, 50/146 patients (34%) had residual tumor after surgery."),
        Line(4, 2.0, "We expect an accrual rate of at least 60 patients per year.")], [])
    tx = Section("4.0", "TREATMENT", 1, 3, 3, 0.0, [Line(3, 1.0, "Agent Q 10 mg/kg IV on Day 1.")], [])
    return Document("sha", "synthetic.pdf", 4, {}, [], [], [tx, st])


def _fact(**kw):
    base = {"fact_id": "f", "kind": "characteristic_distribution", "subject_quote": "", "canonical_variable": "", "category_quote": "",
            "canonical_category": "", "value_quote": "", "upper_value_quote": "", "numerator_quote": "", "denominator_quote": "", "unit_quote": "",
            "time_point_quote": "", "population_quote": "", "arm_quote": "", "source": "not_stated", "source_study_quote": "",
            "evidence_quote": ""}
    return {**base, **kw}


class FactModel:
    def __init__(self, verdict="FAITHFUL"):
        self.verdict, self.calls = verdict, []

    def extract(self, task, schema, payload):
        self.calls.append(task)
        if task == "protocol_section_types":
            return {"assignments": [{"number": "4.0", "types": ["treatment_plan"]}, {"number": "5.0", "types": ["statistics"]}]}
        if task == "protocol_facts":
            return {"facts": [
                _fact(subject_quote="residual tumor", canonical_variable="residual_tumor", value_quote="34%", numerator_quote="50",
                      denominator_quote="146", source="historical_study", source_study_quote="XYZ-0",
                      evidence_quote="In the earlier study XYZ-0, 50/146 patients (34%) had residual tumor after surgery."),
                _fact(kind="accrual_rate", subject_quote="accrual rate", canonical_variable="accrual_rate", value_quote="60",
                      unit_quote="patients per year", source="this_protocol_projection",
                      evidence_quote="We expect an accrual rate of at least 60 patients per year."),
                _fact(subject_quote="residual tumor", canonical_variable="residual_tumor", value_quote="41%", source="historical_study",
                      evidence_quote="41% of patients had residual tumor")]}
        if task == "protocol_verify":
            return {"verdicts": [{"item_id": i["item_id"], "verdict": self.verdict, "problem": "none", "problem_quote": "",
                                  "reviewer_note": ""} for i in payload["items"]]}
        raise AssertionError(task)


def test_fact_values_are_parsed_from_the_quotes():
    assert fx.fact_value("34%", "50", "146", "") == {"value": 50 / 146, "scale": "proportion", "numerator": 50, "denominator": 146}
    assert fx.fact_value("56%", "", "", "") == {"value": 0.56, "scale": "proportion"}
    assert fx.fact_value("60", "", "", "patients per year") == {"value": 60, "scale": "number", "unit": "patients per year"}
    assert fx.fact_value("", "", "", "")["value"] is None
    assert fx.fact_value("25%", "", "", "", "30%") == {"value": 0.25, "scale": "proportion", "upper": 0.3}


def test_qualifiers_come_from_the_words_before_the_number():
    assert fx.qualifier("We expect approximately 10% of the patients", "10%") == "approximately"
    assert fx.qualifier("an accrual rate of at least 60 per year", "60") == "at least"
    assert fx.qualifier("34% had residual tumor", "34%") is None


def test_facts_are_quote_checked_verified_by_majority_and_only_usable_when_all_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "extract", lambda path: _doc())
    model = FactModel()
    summary = fx.FactExtractor(model, workers=2, votes=3).run(tmp_path / "p.pdf", tmp_path / "out")
    out = json.loads((tmp_path / "out" / "population_facts.json").read_text(encoding="utf-8"))
    by_id = {f["fact_id"]: f for f in out["facts"]}
    assert out["sections"] == ["5.0"]                                    # treatment sections are not read
    assert by_id["F001"]["status"] == "USABLE" and abs(by_id["F001"]["value"]["value"] - 50 / 146) < 1e-12
    assert by_id["F002"]["status"] == "USABLE" and by_id["F002"]["value"]["unit"] == "patients per year"
    assert by_id["F003"]["status"] == "REVIEW_REQUIRED" and any("not found" in i for i in by_id["F003"]["quote_issues"])
    assert model.calls.count("protocol_verify") == 9 and summary["usable"] == 2


def test_a_fact_the_verifier_majority_rejects_is_never_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "extract", lambda path: _doc())
    fx.FactExtractor(FactModel("INCORRECT"), workers=2, votes=3).run(tmp_path / "p.pdf", tmp_path / "out")
    out = json.loads((tmp_path / "out" / "population_facts.json").read_text(encoding="utf-8"))
    assert all(f["status"] == "REVIEW_REQUIRED" for f in out["facts"])


class RepairingModel(FactModel):
    """Rejects F001 until it has been repaired; the repair returns the corrected fact."""

    def __init__(self):
        super().__init__()
        self.repairs = []

    def extract(self, task, schema, payload):
        if task == "protocol_facts" and "repair" in payload:
            self.repairs.append(payload["repair"])
            return {"facts": [_fact(subject_quote="residual tumor", canonical_variable="residual_tumor", value_quote="34%",
                                    numerator_quote="50", denominator_quote="146", source="historical_study", source_study_quote="XYZ-0",
                                    evidence_quote="In the earlier study XYZ-0, 50/146 patients (34%) had residual tumor after surgery.")]}
        if task == "protocol_verify":
            bad = any(i["item_id"] == "F001" for i in payload["items"]) and not self.repairs
            return {"verdicts": [{"item_id": i["item_id"], "verdict": "INCORRECT" if bad else "FAITHFUL", "problem": "none",
                                  "problem_quote": "", "reviewer_note": "time point not stated" if bad else ""} for i in payload["items"]]}
        return super().extract(task, schema, payload)


def test_rejected_facts_are_repaired_with_the_reviewers_notes_and_verified_again(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "extract", lambda path: _doc())
    model = RepairingModel()
    summary = fx.FactExtractor(model, workers=2, votes=3).run(tmp_path / "p.pdf", tmp_path / "out")
    out = json.loads((tmp_path / "out" / "population_facts.json").read_text(encoding="utf-8"))
    f1 = out["facts"][0]
    assert model.repairs and model.repairs[0]["reviewer_notes"] == ["time point not stated"] * 3
    assert f1["fact_id"] == "F001" and f1["status"] == "USABLE" and f1["repair"]["previous_notes"]
    assert "50 of 146 (34%)" in f1["rendering"] and "[read as proportion" in f1["rendering"]
    assert out["repaired"] == ["F001"] and summary["repaired"] == 1


def test_a_percent_unit_is_not_repeated_after_a_percentage():
    f = {"kind": "event_free_survival", "subject": {"text": "EFS"}, "canonical_variable": "efs", "source": "historical_study",
         "value": fx.fact_value("45%", "", "", "%"), "value_text": {"text": "45%"}, "unit_text": {"text": "%"}}
    assert "value 45% [read as proportion 0.45]" in fx.render_fact(f)


def test_a_qualifier_inside_the_value_quote_is_found():
    assert fx.qualifier("which accounts for less than 30% of enrolled patients", "less than 30%") == "less than"
    assert fx.stated_qualifier({"qualifier": None, "value_text": {"text": "at least 60"}}) == "at least"
    assert fx.stated_qualifier({"qualifier": None, "value_text": {"text": "34%"}}) is None
