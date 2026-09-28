"""Milestone 4: protocol compiler machinery (synthetic fixtures; no protocol-specific content)."""

import json

import pytest

from clinical_asset.protocol import compiler as comp
from clinical_asset.protocol import expressions as ex
from clinical_asset.protocol.ingest import (
    Document,
    Line,
    Section,
    Table,
    _heading_like,
    _is_contents_page,
    _valid_successor,
)
from clinical_asset.protocol.normalise import (
    Provenance,
    Source,
    Variables,
    build_tree,
    compile_tree,
    parse_days,
)

# ----------------------------------------------------------------------------- parsing


@pytest.mark.parametrize(("text", "value"), [("1,000", 1000.0), ("100,000/µL", 100000.0), ("1.5", 1.5), ("6 ½", 6.5),
                                             ("the tenth anniversary", 10.0), ("none", None)])
def test_parse_number(text, value):
    assert ex.parse_number(text) == value


@pytest.mark.parametrize(("text", "op"), [("greater than or equal to", ">="), ("≥", ">="), ("<", "<"), ("at least", ">="),
                                          ("no more than", "<="), ("less than", "<"), ("above", ">"), ("≤", "<=")])
def test_parse_comparator(text, op):
    assert ex.parse_comparator(text) == op


def test_parse_range_inclusivity():
    assert ex.parse_range("2 to < 6 years") == {"lower": 2.0, "lower_inclusive": True, "upper": 6.0, "upper_inclusive": False}
    assert ex.parse_range("≥ 16 years") == {"lower": 16.0, "lower_inclusive": True, "upper": None, "upper_inclusive": False}
    assert ex.parse_range("1.5 - 1.9")["upper"] == 1.9


def test_parse_unit_and_days():
    assert ex.parse_unit("/µL") == "/ul"
    assert ex.parse_unit("mL/min/1.73m2") == "ml/min/1.73m2"
    assert ex.parse_unit("Years") == "year" and ex.parse_unit("mos") == "month"
    assert parse_days("Days 1 and 8") == [1, 8]
    assert parse_days("Weeks 1-6") == [1, 2, 3, 4, 5, 6]
    assert parse_days("Days 2 and 3") == [2, 3]


# ----------------------------------------------------------------------------- evaluation


def leaf(var, kind="compare", **kw):
    return {"node": "LEAF", "kind": kind, "status": "EXECUTABLE", "variable": var, **kw}


def test_three_valued_logic():
    a = leaf("x", op=">=", value=3)
    b = leaf("y", op="<", value=10)
    assert ex.evaluate({"node": "AND", "children": [a, b]}, {"x": 4, "y": 5}) is True
    assert ex.evaluate({"node": "AND", "children": [a, b]}, {"x": 4}) is None      # missing is unknown
    assert ex.evaluate({"node": "AND", "children": [a, b]}, {"x": 1}) is False     # one false decides AND
    assert ex.evaluate({"node": "OR", "children": [a, b]}, {"y": 5}) is True       # one true decides OR
    assert ex.evaluate({"node": "NOT", "child": a}, {}) is None
    review = {**a, "status": "REVIEW_REQUIRED"}
    assert ex.evaluate(review, {"x": 4}) is None                                   # never executes unresolved rules


def test_conditional_scale_by_age():
    rule = {"node": "AND", "children": [
        {"node": "IF", "condition": leaf("age", op=">", value=16), "then": leaf("scale_a", op=">=", value=30), "else": None},
        {"node": "IF", "condition": leaf("age", op="<=", value=16), "then": leaf("scale_b", op=">=", value=30), "else": None}]}
    assert ex.evaluate(rule, {"age": 20, "scale_a": 40}) is True
    assert ex.evaluate(rule, {"age": 10, "scale_b": 20}) is False
    assert ex.evaluate(rule, {"age": 10, "scale_a": 90}) is None  # the applicable scale is missing


def test_table_threshold_and_relative_reference():
    table = {"node": "LEAF", "kind": "table", "status": "EXECUTABLE", "variable": "marker", "op": "<=", "unit": None, "rows": [
        {"when": {"node": "AND", "children": [leaf("age", "range", lower=2, upper=6, lower_inclusive=True, upper_inclusive=False),
                                                leaf("group", "category", op="in", categories=["A"])]}, "value": 0.8},
        {"when": {"node": "AND", "children": [leaf("age", "range", lower=6, upper=None, lower_inclusive=True, upper_inclusive=False),
                                                leaf("group", "category", op="in", categories=["A"])]}, "value": 1.2}]}
    assert ex.evaluate(table, {"age": 4, "group": "A", "marker": 0.7}) is True
    assert ex.evaluate(table, {"age": 8, "group": "A", "marker": 1.3}) is False
    assert ex.evaluate(table, {"age": 1, "group": "A", "marker": 0.1}) is False    # outside the table
    rel = leaf("enzyme", op="<", value=2.5, reference={"variable": "enzyme_uln"})
    assert ex.evaluate(rel, {"enzyme": 50, "enzyme_uln": 40}) is True
    assert ex.evaluate(rel, {"enzyme": 50}) is None                                 # needs the reference value


# ----------------------------------------------------------------------------- ingestion


def test_outline_and_heading_rules():
    assert _valid_successor(None, (1,)) and not _valid_successor(None, (9,))
    assert _valid_successor((3, 2), (3, 2, 1)) and _valid_successor((3, 2, 8, 1), (3, 2, 9))
    assert _valid_successor((4, 1, 1), (5,)) and not _valid_successor((4, 1), (7,))
    assert _heading_like("Dose Modifications") and not _heading_like("29 ____mg# a ,f") and not _heading_like("a,f")
    toc = [Line(3, float(i), f"{i}.0 Heading number {i} {10 + i}") for i in range(1, 9)]
    assert _is_contents_page(toc, 90)
    body = [Line(20, float(i), "Ordinary sentence of protocol text without page numbers") for i in range(8)]
    assert not _is_contents_page(body, 90)


def test_quote_verification_tolerates_layout_but_not_invention():
    s = Section("3.1", "Criteria", 2, 5, 5, 0.0,
                [Line(5, 1.0, "Platelets > 100,000/µL (untrans-"), Line(5, 2.0, "fused) and other text")],
                [Table(5, 3.0, [["Band", "Limit"], ["low", "0.8"]])])
    src = Source.of([s])
    assert src.locate("Platelets > 100,000/µL")["verified"]
    assert src.locate("(untransfused)")["match"] == "hyphen_tolerant"
    assert src.locate("0.8")["verified"]
    assert not src.locate("Platelets > 150,000/µL")["verified"]


# ----------------------------------------------------------------------------- compile


def node(id_, parent, role, type_, **kw):
    base = {"id": id_, "parent": parent, "role": role, "type": type_, "leaf_kind": "none", "rule_type": "other",
            "subject_quote": "", "canonical_subject": "", "comparator_quote": "", "upper_comparator_quote": "",
            "value_quote": "", "upper_value_quote": "", "unit_quote": "", "reference_quote": "", "category_quotes": [],
            "expected": "none", "event_state": "NONE", "relation": "NONE", "anchor_quote": "", "canonical_anchor": "",
            "calendar_adjustment": "NONE", "time_quote": "", "qualifier_quote": "", "table_rows": [], "source_quote": ""}
    base.update(kw)
    return base


def test_leaf_with_invented_number_is_review_required():
    s = Section("2.1", "Labs", 2, 3, 3, 0.0, [Line(3, 1.0, "Count must be at least 750 per unit.")], [])
    src = Source.of([s])
    doc = Document("x", "x.pdf", 3, {}, [], [], [s])
    prov = Provenance(doc, "t")
    ok = node("n1", "", "root", "LEAF", leaf_kind="compare", subject_quote="Count", comparator_quote="at least",
              value_quote="750", source_quote="Count must be at least 750")
    bad = dict(ok, value_quote="1000")
    issues: list[str] = []
    good_leaf = compile_tree(build_tree([ok])[0], src, prov, Variables(None), "t", issues)
    bad_leaf = compile_tree(build_tree([bad])[0], src, prov, Variables(None), "t", issues)
    assert good_leaf["status"] == "EXECUTABLE" and good_leaf["op"] == ">=" and good_leaf["value"] == 750
    assert bad_leaf["status"] == "REVIEW_REQUIRED" and any("value_quote" in i for i in bad_leaf["issues"])


class ScriptedModel:
    """Returns canned outputs per task; records the payloads it was given."""

    def __init__(self, outputs, reject=()):
        self.outputs, self.calls, self.reject = outputs, [], set(reject)

    def extract(self, task, schema, payload):
        self.calls.append(task)
        if task == "protocol_verify":
            return {"verdicts": [{"item_id": i["item_id"], "verdict": "INCOMPLETE" if i["item_id"] in self.reject else "FAITHFUL",
                                  "problem": "missing_component" if i["item_id"] in self.reject else "none",
                                  "problem_quote": "", "reviewer_note": ""} for i in payload["items"]]}
        out = self.outputs.get(task)
        if task == "protocol_section_types":
            return {"assignments": [{"number": h["number"], "types": out.get(h["number"], ["other"])} for h in payload["headings"]]}
        return json.loads(json.dumps(out))


def _document():
    front = [Line(1, 1.0, "STUDY XYZ-1 A Phase II Study of Agent Q"), Line(1, 2.0, "Arm 1 (Agent Q) remains open.")]
    elig = Section("3.0", "ELIGIBILITY", 1, 2, 2, 0.0, [Line(2, 1.0, "Age at least 18 years."),
                                                        Line(2, 2.0, "Consent must be signed.")], [])
    tx = Section("4.0", "TREATMENT", 1, 3, 3, 0.0, [Line(3, 1.0, "Arm 1 Cycle phase: Agent Q 10 mg/kg IV on Days 1 and 8 of 21 day cycles for 4 cycles.")], [])
    st = Section("5.0", "STATISTICS", 1, 4, 4, 0.0, [
        Line(4, 1.0, "The primary endpoint is progression-free survival in all treated patients."),
        Line(4, 2.0, "Time is measured from the date of enrollment. Patients alive without progression are censored at last contact.")], [])
    return Document("sha", "synthetic.pdf", 4, {}, [], front, [elig, tx, st])


def _empty_stats():
    return {"design": {"phase_quote": "", "design_type": "single_arm", "design_quote": "", "allocation_ratio_quote": "", "blinding_quote": ""},
            "endpoints": [{"endpoint_id": "e1", "name_quote": "progression-free survival", "canonical_endpoint": "pfs",
                           "role": "primary", "type": "time_to_event", "event_quotes": ["progression"], "time_origin_quote": "",
                           "canonical_origin_event": "", "censoring_quotes": [], "population_quote": "all treated patients",
                           "evidence_quote": "The primary endpoint is progression-free survival"}],
            "analyses": [], "sample_size": [], "interim": [], "populations": [{"name_quote": "all treated patients", "definition_quote": ""}],
            "subgroups": [], "missing_data": []}


_OUTPUTS = {
    "protocol_section_types": {"3.0": ["eligibility"], "4.0": ["treatment_plan"], "5.0": ["statistics"]},
    "protocol_metadata": {"protocol_id_quote": "XYZ-1", "title_quote": "A Phase II Study of Agent Q", "phase_quote": "Phase II",
                          "sponsor_quote": "", "version_date_quote": "", "amendment_quote": "", "activation_date_quote": "",
                          "closure_date_quote": "", "condition_quote": "", "population_quote": "", "design_summary_quote": "",
                          "arms": [{"label_quote": "Arm 1", "canonical_arm": "arm_1", "description_quote": "Agent Q", "status": "open",
                                    "status_quote": "remains open"}],
                          "amendment_notes": []},
    "protocol_eligibility": {"criteria": [
        {"criterion_id": "c1", "kind": "inclusion", "modality": "REQUIRED", "label_quote": "Age", "evidence_quote": "Age at least 18 years.",
         "nodes": [node("n1", "", "root", "LEAF", leaf_kind="compare", rule_type="age", subject_quote="Age", canonical_subject="age",
                        comparator_quote="at least", value_quote="18", unit_quote="years", source_quote="Age at least 18 years")]},
        {"criterion_id": "c2", "kind": "administrative", "modality": "REQUIRED", "label_quote": "Consent",
         "evidence_quote": "Consent must be signed.", "nodes": []}]},
    "protocol_treatment": {
        "phases": [{"phase_id": "p1", "name_quote": "Cycle phase", "canonical_phase": "cycle_phase", "arm_label_quotes": ["Arm 1"],
                    "sequence_number": 1, "duration_quote": "", "cycle_length_quote": "21 day", "cycle_count_quote": "4 cycles",
                    "cycle_start_day_quote": "", "max_delay_quote": "", "start_quote": "", "start_nodes": [], "evidence_quote": "Cycle phase"}],
        "interventions": [{"intervention_id": "i1", "phase_id": "p1", "arm_label_quotes": ["Arm 1"], "agent_quote": "Agent Q",
                           "canonical_agent": "agent_q", "category": "anticancer_drug", "modality": "REQUIRED",
                           "dose_quote": "10", "dose_unit_quote": "mg/kg", "day_quote": "Days 1 and 8", "week_quote": "",
                           "frequency_quote": "", "dose_count_quote": "", "max_dose_quote": "", "rounding_quote": "",
                           "alternative_to_quote": "",
                           "administration_options": [{"route_quote": "IV", "canonical_route": "intravenous", "duration_quote": "",
                                                       "policy_quote": ""}],
                           "linked_events": [], "schedule_rules": [], "condition_quote": "", "condition_nodes": [],
                           "min_duration_quote": "", "stop_quote": "", "stop_nodes": [],
                           "evidence_quote": "Agent Q 10 mg/kg IV on Days 1 and 8"}],
        "radiotherapy": []},
    "protocol_statistics": _empty_stats(),
    "protocol_design_rules": {"binary_rules": [], "dose_escalation": []},
    "protocol_resolve": {"answers": [
        {"question_id": "EP1.origin", "status": "STATED", "answer_quote": "Time is measured from the date of enrollment",
         "evidence_quote": "", "canonical_value": "enrollment"},
        {"question_id": "EP1.censoring", "status": "STATED",
         "answer_quote": "Patients alive without progression are censored at last contact", "evidence_quote": "", "canonical_value": ""}]},
}


def test_end_to_end_compile_with_scripted_model(tmp_path, monkeypatch):
    doc = _document()
    monkeypatch.setattr(comp, "extract", lambda path: doc)
    outputs = json.loads(json.dumps(_OUTPUTS))
    model = ScriptedModel(outputs)
    result = comp.ProtocolCompiler(model, terminology=None, workers=2).compile(tmp_path / "p.pdf", out_dir=tmp_path / "out")
    spec = json.loads((tmp_path / "out" / "studyspec.json").read_text(encoding="utf-8"))
    audit = json.loads((tmp_path / "out" / "audit.json").read_text(encoding="utf-8"))
    age = spec["eligibility"][0]
    assert age["status"] == "EXECUTABLE" and age["logic"]["op"] == ">=" and age["logic"]["value"] == 18
    assert age["semantic_status"] == "FAITHFUL" and age["runtime_status"] == "EXECUTABLE_NOW" and age["criticality"] == "CRITICAL"
    assert age["logic"]["unit"] == "year" and age["logic"]["variable"] == "demographic:age"
    assert spec["eligibility"][1]["status"] == "NON_EXECUTABLE_INFORMATIONAL"
    tx = spec["interventions"][0]
    assert tx["dose"] == {**tx["dose"], "value": 10.0, "unit": "mg/kg", "basis": "per_body_weight"}
    assert tx["schedule"]["days"] == [1, 8] and tx["status"] == "EXECUTABLE"
    assert spec["treatment_phases"][0]["cycle_length"]["days"] == 21 and spec["treatment_phases"][0]["cycle_count"]["value"] == 4
    ep = spec["endpoints"][0]
    assert ep["role"] == "primary" and ep["time_origin_derivation"] == "STATED" and ep["censoring_derivation"] == "STATED"
    assert spec["gate"]["result"] == "PASS", spec["gate"]
    assert result["quotes_not_found"] == 0
    assert all(p["verified"] for p in audit["provenance"] if p["quote"])
    assert ex.evaluate(age["logic"], {age["logic"]["variable"]: {"value": 20, "unit": "year"}}) is True
    assert (tmp_path / "out" / "studyspec_review.md").exists()


def test_verifier_rejection_fails_the_gate(tmp_path, monkeypatch):
    doc = _document()
    monkeypatch.setattr(comp, "extract", lambda path: doc)
    outputs = json.loads(json.dumps(_OUTPUTS))
    model = ScriptedModel(outputs, reject={"EL001"})
    comp.ProtocolCompiler(model, terminology=None, workers=2).compile(tmp_path / "p.pdf", out_dir=tmp_path / "out")
    spec = json.loads((tmp_path / "out" / "studyspec.json").read_text(encoding="utf-8"))
    review = json.loads((tmp_path / "out" / "review_required.json").read_text(encoding="utf-8"))
    assert spec["eligibility"][0]["status"] == "REVIEW_REQUIRED"
    assert spec["eligibility"][0]["semantic_status"] == "INCOMPLETE"
    assert any(r["item"] == "EL001" and "independent verification" in r["reason"] for r in review)
    assert spec["gate"]["result"] == "FAIL" and "EL001" in spec["gate"]["failed_conditions"]["zero_critical_verifier_failures"]


def test_unstated_time_origin_is_a_source_gap_not_a_failure(tmp_path, monkeypatch):
    doc = _document()
    monkeypatch.setattr(comp, "extract", lambda path: doc)
    outputs = json.loads(json.dumps(_OUTPUTS))
    outputs["protocol_resolve"] = {"answers": [
        {"question_id": q, "status": "NOT_STATED", "answer_quote": "", "evidence_quote": "", "canonical_value": ""}
        for q in ("EP1.origin", "EP1.censoring")]}
    comp.ProtocolCompiler(ScriptedModel(outputs), terminology=None, workers=2).compile(tmp_path / "p.pdf", out_dir=tmp_path / "out")
    spec = json.loads((tmp_path / "out" / "studyspec.json").read_text(encoding="utf-8"))
    ep = spec["endpoints"][0]
    assert ep["runtime_status"] == "UNRESOLVED_IN_SOURCE" and ep["status"] == "UNRESOLVED_IN_SOURCE"
    assert spec["gate"]["result"] == "PASS_WITH_SOURCE_GAPS" and "EP1" in spec["gate"]["source_gaps"]


def test_timing_window_and_relative_threshold():
    from clinical_asset.protocol.normalise import linkable, table_streams

    w = ex.parse_window("within ... prior to", "7", "days", "enrollment")
    assert w == {"min_days": -7.0, "max_days": 0.0, "direction": "before_anchor"}
    assert ex.parse_window("within", "31", "days", "of diagnostic surgery")["max_days"] == 31.0
    assert ex.parse_window("no older than", "seven (7)", "days", "at the start of therapy")["min_days"] == -7.0
    node = {"node": "LEAF", "kind": "window", "status": "EXECUTABLE", "variable": "t", **w}
    assert ex.evaluate(node, {"t": -3}) is True and ex.evaluate(node, {"t": -9}) is False
    assert ex.is_relative_unit("x") and ex.is_relative_unit("× ULN") and not ex.is_relative_unit("mg/dL")
    assert ex.parse_unit("years of age") == "year"
    # semantic-type policy for UMLS links (types are UMLS semantic type codes)
    assert not linkable(("T101",), "age")               # a patient group is not a variable
    assert not linkable(("T028",), "laboratory")        # a gene only for biomarker rules
    assert linkable(("T028",), "biomarker")
    assert not linkable(("T080",), "diagnosis")         # an abstract qualitative concept
    streams = [t for _, t in table_streams(1, [["Score", "Text"], ["", "first part"], ["", "second part"]])]
    assert any("first part second part" in s for s in streams)


def test_window_forms_and_word_numbers():
    assert ex.parse_window("obtained", "", "", "pre-operatively") == {"min_days": None, "max_days": 0.0, "direction": "before_anchor"}
    late = ex.parse_window(">", "7", "days", "post-operatively")
    assert late["min_days"] == 7.0 and late["max_days"] is None and late["strict"]
    node = {"node": "LEAF", "kind": "window", "status": "EXECUTABLE", "variable": "t", **late}
    assert ex.evaluate(node, {"t": 7}) is False and ex.evaluate(node, {"t": 8}) is True
    assert ex.parse_number("Six weeks of radiation therapy (Weeks 1-6)") == 6.0
    assert ex.unit_after_number("28 day cycles") == "day"
    assert ex.parse_unit(ex.unit_after_number("6 week rest period")) == "week"


def test_range_strictness_and_table_key_checks():
    s = Section("5.1", "Counts", 2, 3, 3, 0.0, [Line(3, 1.0, "If the count is above 750 but below 1,000, reduce the dose.")],
                [Table(3, 2.0, [["Band", "Male", "Female"], ["2 to < 6 years", "0.8", "0.7"]])])
    src = Source.of([s])
    prov = Provenance(Document("x", "x.pdf", 3, {}, [], [], [s]), "t")
    rng = node("n1", "", "root", "LEAF", leaf_kind="range", subject_quote="count", comparator_quote="above",
               upper_comparator_quote="below", value_quote="750", upper_value_quote="1,000",
               source_quote="the count is above 750 but below 1,000")
    leaf_ = compile_tree(build_tree([rng])[0], src, prov, Variables(None), "t", [])
    assert leaf_["status"] == "EXECUTABLE" and not leaf_["lower_inclusive"] and not leaf_["upper_inclusive"]
    assert ex.evaluate(leaf_, {leaf_["variable"]: 750}) is False and ex.evaluate(leaf_, {leaf_["variable"]: 900}) is True
    bad_table = node("n1", "", "root", "LEAF", leaf_kind="table", subject_quote="count", comparator_quote="below",
                     table_rows=[{"conditions": [{"variable_quote": "Male", "value_quote": "Male"}], "value_quote": "0.8"}])
    t = compile_tree(build_tree([bad_table])[0], src, prov, Variables(None), "t", [])
    assert t["status"] == "REVIEW_REQUIRED" and any("key names a value" in i for i in t["issues"])


def test_gapped_documentary_quotes_and_implied_anchor():
    from clinical_asset.protocol.normalise import _implied_anchor

    s = Section("3.6", "Prior Therapy", 2, 4, 4, 0.0, [Line(4, 1.0, "No previous chemotherapy or radiation therapy.")], [])
    src = Source.of([s])
    assert not src.locate("No previous radiation therapy")["verified"]           # values never accept gaps
    assert src.locate_gapped("No previous radiation therapy")["match"] == "gapped"  # documentary quotes may
    assert not src.locate_gapped("No recent radiation therapy")["verified"]
    assert _implied_anchor({"comparator_quote": "pre-operative"}) == "pre-operative"
    w = ex.parse_window("", "", "", "pre-operative")
    assert w["max_days"] == 0.0 and w["min_days"] is None


def test_item_ids_prefer_the_most_specific_key():
    assert comp._item_id({"intervention_id": "TX001", "phase_id": "PH1"}) == "TX001"
    assert comp._item_id({"phase_id": "PH1"}) == "PH1"
    assert comp._item_id({"rule_id": "DM003"}) == "DM003"


def test_units_kept_readable_and_anniversary_is_a_year():
    assert comp._unit_or_text("medulloblastoma patients") == "medulloblastoma patients"
    assert comp._unit_or_text("years") == "year" and comp._unit_or_text("mg/m2") == "mg/m2"
    assert ex.parse_unit("anniversary") == "year"


# ----------------------------------------------------------------------------- StudySpec IR 1.1 primitives


def _leaf(n, text):
    s = Section("4.1", "Plan", 2, 3, 3, 0.0, [Line(3, 1.0, text)], [])
    prov = Provenance(Document("x", "x.pdf", 3, {}, [], [], [s]), "t")
    return compile_tree(build_tree([n])[0], Source.of([s]), prov, Variables(None), "t", [])


def test_temporal_relations_cycle_day_and_business_days():
    text = ("Therapy must begin within 31 days of diagnostic surgery. If Day 31 falls on a Saturday, Sunday or Holiday, "
            "therapy must begin the following business day. Begin each cycle on Day 29. The patient must have been off "
            "myeloid growth factor for at least 24 hours.")
    start = _leaf(node("n1", "", "root", "LEAF", leaf_kind="window", subject_quote="therapy", canonical_subject="therapy_start",
                       relation="WITHIN_AFTER", comparator_quote="within", value_quote="31", unit_quote="days",
                       anchor_quote="diagnostic surgery", canonical_anchor="diagnostic_surgery",
                       calendar_adjustment="NEXT_BUSINESS_DAY_IF_NON_BUSINESS_DAY",
                       source_quote="Therapy must begin within 31 days of diagnostic surgery"), text)
    assert start["status"] == "EXECUTABLE" and (start["min_days"], start["max_days"]) == (0.0, 31.0)
    assert start["calendar_adjustment"] == "NEXT_BUSINESS_DAY_IF_NON_BUSINESS_DAY"
    assert start["variable"].startswith("timing:")
    day = _leaf(node("n1", "", "root", "LEAF", leaf_kind="window", canonical_subject="cycle_start", relation="ON_CYCLE_DAY",
                     value_quote="29", anchor_quote="Begin each cycle", canonical_anchor="previous_cycle_start",
                     source_quote="Begin each cycle on Day 29"), text)
    assert day["cycle_day"] == 29.0 and day["min_days"] == day["max_days"] == 28.0
    off = _leaf(node("n1", "", "root", "LEAF", leaf_kind="window", canonical_subject="next_cycle_start", relation="AT_LEAST_AFTER",
                     comparator_quote="for at least", value_quote="24", unit_quote="hours", anchor_quote="myeloid growth factor",
                     canonical_anchor="last_growth_factor_dose", source_quote="off myeloid growth factor for at least 24 hours"), text)
    assert off["status"] == "EXECUTABLE" and off["min_days"] == 1.0 and off["max_days"] is None
    assert ex.evaluate(off, {off["variable"]: 0.5}) is False and ex.evaluate(off, {off["variable"]: 2}) is True
    wrong = _leaf(node("n1", "", "root", "LEAF", leaf_kind="window", subject_quote="therapy", relation="WITHIN_BEFORE",
                       comparator_quote="within", value_quote="31", unit_quote="days", anchor_quote="diagnostic surgery",
                       source_quote="Therapy must begin within 31 days following diagnostic surgery"),
                  "Therapy must begin within 31 days following diagnostic surgery.")
    assert wrong["status"] == "REVIEW_REQUIRED" and any("contradicts" in i for i in wrong["issues"])


def test_event_states_and_event_counts():
    text = "If chemotherapy is due, delay the cycle. After two cycles of therapy give full doses."
    due = _leaf(node("n1", "", "root", "LEAF", leaf_kind="event_state", subject_quote="chemotherapy",
                     canonical_subject="next_chemotherapy_cycle", event_state="DUE", source_quote="If chemotherapy is due"), text)
    assert due["status"] == "EXECUTABLE" and due["variable"].startswith("event:")
    assert ex.evaluate(due, {due["variable"]: "DUE"}) is True and ex.evaluate(due, {due["variable"]: "ADMINISTERED"}) is False
    two = _leaf(node("n1", "", "root", "LEAF", leaf_kind="event_count", canonical_subject="completed_cycles",
                     comparator_quote="After", value_quote="two", source_quote="After two cycles of therapy"), text)
    assert two["status"] == "EXECUTABLE" and two["op"] == ">=" and two["value"] == 2.0
    assert ex.evaluate(two, {two["variable"]: 2}) is True


def test_implied_characteristic_uses_canonical_label_not_a_fake_quote():
    from clinical_asset.protocol import ir

    text = "Female patients who are post-menarchal must have a negative pregnancy test."
    leaf_ = _leaf(node("n1", "", "root", "LEAF", leaf_kind="category", canonical_subject="menarchal_status",
                       category_quotes=["post-menarchal"], source_quote="post-menarchal"), text)
    assert leaf_["status"] == "EXECUTABLE" and leaf_["variable"] == "var:menarchal_status"
    assert ir.runtime_from_leaves([leaf_]) == "EXECUTABLE_AFTER_VARIABLE_AVAILABLE"
    assert ir.runtime_from_leaves([leaf_], "OPTIONAL") == "OPTIONAL_POLICY"


def test_unit_dimensions():
    from clinical_asset.protocol import units

    assert units.dimension("/ul") == "COUNT_PER_VOLUME"
    assert units.dimension("mg/dl") == "CONCENTRATION"
    assert units.dimension("ml/min/1.73m2") == "FLOW_OR_CLEARANCE"
    assert units.dimension("mg/m2") == "DOSE_PER_BSA" and units.dimension("micrograms/kg/day") == "DOSE_PER_WEIGHT"
    assert units.dimension("ml/min/1.73ml/min/1.73m2") == "INVALID"
    assert units.dimension("gy") == "RADIATION_DOSE"


def test_monitor_parameters_and_ratio():
    base = {"method_family": "", "spending_family": "NONE", "alpha_quote": "", "spending_parameter_quote": "", "information_quote": "",
            "prior_quote": "", "threshold_quote": "", "posterior_cutoff_quote": "", "futility_cutoff_quote": ""}
    bayes = comp._monitor({**base, "method_family": "BAYESIAN_POSTERIOR", "prior_quote": "Beta (2,12)",
                           "threshold_quote": "p0=15%", "posterior_cutoff_quote": "85%"})
    assert bayes["prior"] == {"family": "beta", "a": 2.0, "b": 12.0} and bayes["threshold"] == 0.15
    assert bayes["posterior_cutoff"] == 0.85 and bayes["runtime_status"] == "EXECUTABLE_NOW"
    spend = comp._monitor({**base, "method_family": "ALPHA_SPENDING", "spending_family": "POWER_FAMILY", "alpha_quote": "5%",
                           "spending_parameter_quote": "t2", "information_quote": "110 events"})
    assert (spend["alpha"], spend["rho"], spend["full_information"]) == (0.05, 2.0, 110.0)
    incomplete = comp._monitor({**base, "method_family": "CONDITIONAL_POWER"})
    assert incomplete["runtime_status"] == "UNSUPPORTED_RULE_TYPE" and incomplete["missing"] == ["futility_cutoff"]
    assert comp._ratio("randomized 2:1")["ratio"] == [2.0, 1.0] and comp._ratio("no ratio here") is None
    assert comp._weekdays("Fri., Sat., Sun.") == ["friday", "saturday", "sunday"]


def test_static_checks_radiotherapy_arithmetic_and_modality():
    from clinical_asset.protocol import typecheck

    target = {"target_id": "RT1.T1", "role": "primary_field", "total_dose": {"value": 36.0, "unit": "gy"}, "fraction_dose": None,
              "fraction_count": 31.0, "cumulative": False, "condition": None}
    spec = {"eligibility": [], "stratification": {"strata": []}, "treatment_phases": [], "grade_definitions": [],
            "interventions": [{"intervention_id": "TX1", "phase_id": "PH9", "dose": {"value": 5, "unit": "mg"}, "category": "supportive",
                               "linked_events": [], "schedule_rules": [], "modality": "REQUIRED", "agent": {"text": "agent"},
                               "canonical_agent": "agent", "evidence": {"text": "Diuretics may be used to increase output."}}],
            "radiotherapy": [{"course_id": "RT1", "fraction_dose": {"value": 1.8, "unit": "gy"}, "overall_fraction_count": 31.0,
                              "targets": [target]}],
            "dose_modifications": [], "endpoints": [], "arms": [], "randomization": {}, "interim_analyses": []}
    issues, _ = typecheck.check(spec)
    assert any("overall fraction count" in i or "!=" in i for i in issues["RT1.T1"])
    assert any("permissive" in i for i in issues["TX1"]) and any("no compiled phase" in i for i in issues["TX1"])


class OnceRejectingModel(ScriptedModel):
    """Rejects the given items, in every vote, until they have been repaired (a fixable extraction error)."""

    def __init__(self, outputs, reject_once):
        super().__init__(outputs)
        self.pending = set(reject_once)
        self.repair_payloads = []

    def extract(self, task, schema, payload):
        if task == "protocol_verify":
            verdicts = []
            for i in payload["items"]:
                bad = i["item_id"] in self.pending and not self.repair_payloads
                verdicts.append({"item_id": i["item_id"], "verdict": "INCOMPLETE" if bad else "FAITHFUL",
                                 "problem": "missing_component" if bad else "none", "problem_quote": "",
                                 "reviewer_note": "qualifier missing" if bad else ""})
            return {"verdicts": verdicts}
        if "repair" in payload:
            self.repair_payloads.append(payload["repair"])
        return super().extract(task, schema, payload)


def test_automatic_repair_recompiles_a_rejected_critical_item(tmp_path, monkeypatch):
    doc = _document()
    monkeypatch.setattr(comp, "extract", lambda path: doc)
    model = OnceRejectingModel(json.loads(json.dumps(_OUTPUTS)), reject_once={"EL001"})
    comp.ProtocolCompiler(model, terminology=None, workers=2).compile(tmp_path / "p.pdf", out_dir=tmp_path / "out")
    spec = json.loads((tmp_path / "out" / "studyspec.json").read_text(encoding="utf-8"))
    review = json.loads((tmp_path / "out" / "review_required.json").read_text(encoding="utf-8"))
    age = spec["eligibility"][0]
    assert spec["repaired_items"] == ["EL001"] and age["criterion_id"] == "EL001"
    assert age["status"] == "EXECUTABLE" and age["repair"]["previous_verdict"] == "INCOMPLETE"
    assert model.repair_payloads and model.repair_payloads[0]["verifier_note"] == "qualifier missing"
    assert not any(r["item"] == "EL001" for r in review)        # the pre-repair finding no longer applies
    assert spec["gate"]["result"] == "PASS"


def test_sex_values_are_canonical_so_rules_match_simulated_patients():
    text = "Males or females of reproductive potential may not participate unless they use contraception."
    leaf_ = _leaf(node("n1", "", "root", "LEAF", leaf_kind="category", rule_type="sex", subject_quote="Males",
                       canonical_subject="sex", category_quotes=["Males", "females"], source_quote="Males or females"), text)
    assert leaf_["variable"] == "demographic:sex" and leaf_["categories"] == ["male", "female"]
    assert ex.evaluate(leaf_, {"demographic:sex": "male"}) is True


class ReclassifyingModel(ScriptedModel):
    """Rejects EL001, repairs it as a note, then judges it with verdicts[n] in every vote after n repairs."""

    def __init__(self, outputs, verdicts):
        super().__init__(outputs)
        self.verdicts, self.repairs = list(verdicts), 0

    def extract(self, task, schema, payload):
        if task == "protocol_verify":
            out = []
            for i in payload["items"]:
                verdict = self.verdicts[min(self.repairs, len(self.verdicts) - 1)] if i["item_id"] == "EL001" else "FAITHFUL"
                out.append({"item_id": i["item_id"], "verdict": verdict, "problem": "none" if verdict == "FAITHFUL" else "wrong_action",
                            "problem_quote": "", "reviewer_note": ""})
            return {"verdicts": out}
        if "repair" in payload:
            self.repairs += 1
            return {"criteria": [{"criterion_id": "c1", "kind": "note", "modality": "REQUIRED", "label_quote": "Age",
                                  "evidence_quote": "Age at least 18 years.", "nodes": []}]}
        return super().extract(task, schema, payload)


def _compile_with(model, tmp_path, monkeypatch):
    doc = _document()
    monkeypatch.setattr(comp, "extract", lambda path: doc)
    comp.ProtocolCompiler(model, terminology=None, workers=2).compile(tmp_path / "p.pdf", out_dir=tmp_path / "out")
    return json.loads((tmp_path / "out" / "studyspec.json").read_text(encoding="utf-8"))


def test_repair_may_reclassify_a_rule_as_a_note_only_when_the_verifier_agrees(tmp_path, monkeypatch):
    spec = _compile_with(ReclassifyingModel(json.loads(json.dumps(_OUTPUTS)), ["INCORRECT", "FAITHFUL"]), tmp_path, monkeypatch)
    el = spec["eligibility"][0]
    assert el["kind"] == "note" and el["reclassified_from"] == "inclusion" and el["criticality"] == "INFORMATIONAL"
    assert el["status"] == "NON_EXECUTABLE_INFORMATIONAL" and spec["gate"]["result"] == "PASS"


def test_an_unconfirmed_reclassification_stays_critical_and_fails_the_gate(tmp_path, monkeypatch):
    spec = _compile_with(ReclassifyingModel(json.loads(json.dumps(_OUTPUTS)), ["INCORRECT"] * 5), tmp_path, monkeypatch)
    el = spec["eligibility"][0]
    assert el["kind"] == "note" and el["criticality"] == "CRITICAL" and el["semantic_status"] == "INCORRECT"
    assert spec["gate"]["result"] == "FAIL" and "EL001" in spec["gate"]["failed_conditions"]["zero_critical_verifier_failures"]


def test_a_repair_cannot_lower_criticality_by_changing_modality_without_verification(tmp_path, monkeypatch):
    outputs = json.loads(json.dumps(_OUTPUTS))

    class Softening(ReclassifyingModel):
        def extract(self, task, schema, payload):
            if "repair" in payload:
                self.repairs += 1
                c = json.loads(json.dumps(outputs["protocol_eligibility"]["criteria"][0]))
                return {"criteria": [{**c, "modality": "OPTIONAL"}]}
            return super().extract(task, schema, payload)

    spec = _compile_with(Softening(outputs, ["INCORRECT"] * 5), tmp_path, monkeypatch)
    el = spec["eligibility"][0]
    assert el["modality"] == "OPTIONAL" and el["criticality"] == "CRITICAL" and el["status"] == "REVIEW_REQUIRED" and spec["gate"]["result"] == "FAIL"


def test_majority_vote_decides_and_a_split_without_majority_is_unverified():
    f, inc, wrong = ({"verdict": v, "problem": "", "problem_quote": "", "reviewer_note": v} for v in ("FAITHFUL", "INCOMPLETE", "INCORRECT"))
    assert comp._majority([f, f, wrong], 3)["verdict"] == "FAITHFUL"
    assert comp._majority([f, wrong, wrong], 3)["verdict"] == "INCORRECT"
    assert comp._majority([f, inc, wrong], 3)["verdict"] == "INCORRECT"      # rejected by two of three, most severe reported
    assert comp._majority([f, wrong], 3) is None                              # one call failed: no majority either way
    assert comp._majority([f], 1)["verdict"] == "FAITHFUL"


class SplitVerifier(ScriptedModel):
    """One vote in three rejects each critical item: the majority still accepts it."""

    def extract(self, task, schema, payload):
        if task == "protocol_verify":
            self.calls.append(task)
            bad = payload.get("independent_review", "").startswith("review 2")
            return {"verdicts": [{"item_id": i["item_id"], "verdict": "INCORRECT" if bad else "FAITHFUL", "problem": "none",
                                  "problem_quote": "", "reviewer_note": ""} for i in payload["items"]]}
        return super().extract(task, schema, payload)


def test_critical_items_get_three_votes_and_one_dissent_does_not_fail_the_gate(tmp_path, monkeypatch):
    model = SplitVerifier(json.loads(json.dumps(_OUTPUTS)))
    spec = _compile_with(model, tmp_path, monkeypatch)
    age = spec["eligibility"][0]
    assert age["verification"]["votes"] == ["FAITHFUL", "INCORRECT", "FAITHFUL"] and age["semantic_status"] == "FAITHFUL"
    assert spec["gate"]["result"] == "PASS"


def test_a_linked_event_can_be_limited_to_some_administration_days():
    from clinical_asset.protocol import render, typecheck

    link = {"relation": "AFTER", "canonical_prerequisite": "agent_p", "min_offset": {"value": 24.0, "unit": "hour"}, "max_offset": None,
            "if_prerequisite_not_given": "NOT_STATED", "applies_to_days": [2], "applies_to_days_text": {"text": "On Day 2"}}
    it = {"intervention_id": "TX1", "phase_id": "PH1", "dose": {"value": 5, "unit": "mg", "basis": "flat"}, "category": "anticancer_drug",
          "linked_events": [link], "schedule_rules": [], "modality": "REQUIRED", "agent": {"text": "agent"}, "arms": [],
          "canonical_agent": "agent", "schedule": {"days": [2, 3]}, "evidence": {"text": "5 mg on Day 2 and Day 3."}}
    assert "on day(s) [2] only: given at least 24 hour after agent p" in render.intervention(it, {"PH1": "phase"}, {})
    spec = {"eligibility": [], "stratification": {"strata": []}, "treatment_phases": [{"phase_id": "PH1"}], "grade_definitions": [],
            "interventions": [it, {**it, "intervention_id": "TX2", "canonical_agent": "agent_p", "linked_events": []}],
            "radiotherapy": [], "dose_modifications": [], "endpoints": [], "arms": [], "randomization": {}, "interim_analyses": []}
    assert not typecheck.check(spec)[0].get("TX1")
    link["applies_to_days"] = [4]
    assert any("outside the schedule" in i for i in typecheck.check(spec)[0]["TX1"])


def test_treatment_gaps_name_empty_phases_and_agents_with_rules_but_no_administration():
    from clinical_asset.protocol import typecheck

    gaps = typecheck.treatment_gaps([("PH1", "Induction"), ("PH2", "Consolidation")], {"PH1"}, {"agent_a"},
                                    {"agent_a", "agent_b", "radiation_therapy"})
    assert gaps == ["treatment incomplete: phase PH2 'Consolidation' has no compiled administration",
                    "treatment incomplete: dose-modification rules name 'agent_b' but no administration of it was compiled"]


class OmittingModel(ScriptedModel):
    """The first treatment extraction omits every intervention; a completeness pass returns them if `recover`."""

    def __init__(self, outputs, recover):
        super().__init__(outputs)
        self.recover, self.completion_payloads = recover, []

    def extract(self, task, schema, payload):
        if task == "protocol_treatment":
            self.calls.append(task)
            out = json.loads(json.dumps(self.outputs[task]))
            if "completeness" in payload:
                self.completion_payloads.append(payload["completeness"])
                if self.recover:
                    return out
            return {**out, "interventions": []}
        return super().extract(task, schema, payload)


def test_a_missed_administration_is_recovered_by_the_completeness_pass(tmp_path, monkeypatch):
    model = OmittingModel(json.loads(json.dumps(_OUTPUTS)), recover=True)
    spec = _compile_with(model, tmp_path, monkeypatch)
    assert model.completion_payloads and "Cycle phase" in model.completion_payloads[0]["missing"][0]
    assert [p["phase_id"] for p in spec["treatment_phases"]] == ["PH1"]              # merged into the phase already compiled
    assert [(i["intervention_id"], i["phase_id"]) for i in spec["interventions"]] == [("TX001", "PH1")]
    assert spec["treatment_completion"]["passes"] == 1 and not spec["treatment_completion"]["gaps_after"]
    assert spec["gate"]["result"] == "PASS"


def test_an_unrecovered_omission_fails_the_gate(tmp_path, monkeypatch):
    spec = _compile_with(OmittingModel(json.loads(json.dumps(_OUTPUTS)), recover=False), tmp_path, monkeypatch)
    assert spec["treatment_completion"]["gaps_after"] and spec["gate"]["result"] == "FAIL"
    assert any("has no compiled administration" in g for g in spec["gate"]["failed_conditions"]["zero_spec_level_static_issues"])


def test_evidence_for_verification_falls_back_to_the_items_verified_quotes():
    item = {"evidence": None, "agent": {"text": "Agent Q", "provenance": "P1", "verified": True},
            "dose": {"quote": {"text": "10", "provenance": "P2", "verified": True}, "unit_quote": {"text": "mg", "provenance": "P3", "verified": False}},
            "verification": {"reviewer_note": {"text": "x", "provenance": "P9", "verified": True}}}
    assert comp._evidence(item, None) == "Agent Q | 10"


def test_a_completeness_pass_does_not_repeat_a_radiotherapy_course(tmp_path, monkeypatch):
    outputs = json.loads(json.dumps(_OUTPUTS))
    course = {"course_id": "c1", "phase_id": "", "arm_label_quotes": [], "overall_fraction_count_quote": "", "fraction_dose_quote": "",
              "fraction_unit_quote": "", "fractions_per_week_quote": "", "evidence_quote": "", "targets": []}
    outputs["protocol_treatment"]["radiotherapy"] = [course]

    class RepeatingCourse(OmittingModel):
        def extract(self, task, schema, payload):
            out = super().extract(task, schema, payload)
            if task == "protocol_treatment" and "completeness" in payload:
                out["radiotherapy"] = [{**course, "phase_id": "p1"}]
            return out

    spec = _compile_with(RepeatingCourse(outputs, recover=True), tmp_path, monkeypatch)
    assert [c["course_id"] for c in spec["radiotherapy"]] == ["RT1"] and spec["radiotherapy"][0]["phase_id"] is None
    assert [i["intervention_id"] for i in spec["interventions"]] == ["TX001"]


def test_a_boost_dose_recorded_as_a_fraction_dose_is_a_static_error():
    from clinical_asset.protocol import render, typecheck

    primary = {"target_id": "RT1.T1", "role": "primary_field", "total_dose": {"value": 36.0, "unit": "gy"}, "fraction_dose": None,
               "fraction_count": None, "cumulative": False, "condition": None}
    boost = {"target_id": "RT1.T2", "role": "boost", "total_dose": {"value": 39.6, "unit": "gy"}, "fraction_dose": {"value": 3.6, "unit": "gy"},
             "boost_dose": None, "fraction_count": None, "cumulative": True, "condition": {"node": "LEAF"}}
    course = {"course_id": "RT1", "fraction_dose": {"value": 1.8, "unit": "gy"}, "overall_fraction_count": None, "targets": [primary, boost]}
    spec = {"eligibility": [], "stratification": {"strata": []}, "treatment_phases": [], "grade_definitions": [], "interventions": [],
            "radiotherapy": [course], "dose_modifications": [], "endpoints": [], "arms": [], "randomization": {}, "interim_analyses": []}
    assert any("equals the target's whole additional dose" in i for i in typecheck.check(spec)[0]["RT1.T2"])
    boost.update(fraction_dose=None, boost_dose={"value": 3.6, "unit": "gy"})
    assert not any("additional dose" in i for i in typecheck.check(spec)[0].get("RT1.T2", []))
    assert "boost of 3.6 gy on top of earlier fields" in render.radiotherapy_target({**course, "arms": [], "fractions_per_week": None}, boost, {})


def test_course_fraction_count_may_include_conditional_boosts():
    from clinical_asset.protocol import typecheck

    primary = {"target_id": "RT1.T1", "role": "primary_field", "total_dose": {"value": 36.0, "unit": "gy"}, "fraction_dose": None,
               "fraction_count": None, "cumulative": False, "condition": None}
    boost = {"target_id": "RT1.T2", "role": "boost", "total_dose": {"value": 55.8, "unit": "gy"}, "fraction_dose": None,
             "fraction_count": None, "cumulative": True, "condition": {"node": "LEAF"}}
    course = {"course_id": "RT1", "fraction_dose": {"value": 1.8, "unit": "gy"}, "overall_fraction_count": 31.0, "targets": [primary, boost]}
    spec = {"eligibility": [], "stratification": {"strata": []}, "treatment_phases": [], "grade_definitions": [], "interventions": [],
            "radiotherapy": [course], "dose_modifications": [], "endpoints": [], "arms": [], "randomization": {}, "interim_analyses": []}
    assert not any("radiotherapy course" in g for g in typecheck.check(spec)[1])     # 20 + 11 = 31
    course["overall_fraction_count"] = 30.0
    assert any("no patient's targets give that" in g for g in typecheck.check(spec)[1])


def test_interval_valued_patient_data_is_evaluated_three_valued():
    leaf = {"node": "LEAF", "kind": "compare", "status": "EXECUTABLE", "variable": "v", "op": ">", "value": 1.5, "unit": "cm2"}
    above = {"v": {"interval": [1.5, None], "lower_inclusive": True, "unit": "cm2"}}
    strictly_above = {"v": {"interval": [1.5, None], "lower_inclusive": False, "unit": "cm2"}}
    below = {"v": {"interval": [0, 1.5], "upper_inclusive": False, "unit": "cm2"}}
    assert ex.evaluate(leaf, strictly_above) is True and ex.evaluate(leaf, below) is False
    assert ex.evaluate(leaf, above) is None                    # 1.5 itself is not > 1.5: undecided
    rng = {"node": "LEAF", "kind": "range", "status": "EXECUTABLE", "variable": "v", "lower": 1, "upper": 2, "unit": "cm2"}
    assert ex.evaluate(rng, {"v": {"interval": [1.2, 1.8], "unit": "cm2"}}) is True
    assert ex.evaluate(rng, {"v": {"interval": [2.5, None], "unit": "cm2"}}) is False
    assert ex.evaluate(rng, {"v": {"interval": [1.5, None], "unit": "cm2"}}) is None


def test_a_subgroup_requirement_compiled_as_a_conjunction_is_a_static_error():
    from clinical_asset.protocol import typecheck

    sex = {"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": "demographic:sex", "op": "in", "categories": ["female"]}
    test = {"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": "var:pregnancy_test", "op": "in", "categories": ["negative"]}
    spec = {"eligibility": [{"criterion_id": "EL1", "kind": "inclusion", "logic": {"node": "AND", "children": [sex, test]}},
                            {"criterion_id": "EL2", "kind": "inclusion", "logic": {"node": "IF", "condition": sex, "then": test}},
                            {"criterion_id": "EL3", "kind": "inclusion", "logic": sex}],
            "stratification": {"strata": []}, "treatment_phases": [], "grade_definitions": [], "interventions": [], "radiotherapy": [],
            "dose_modifications": [], "endpoints": [], "arms": [], "randomization": {}, "interim_analyses": []}
    issues = typecheck.check(spec)[0]
    assert any("IF subgroup THEN requirement" in i for i in issues["EL1"])
    assert not issues.get("EL2") and not issues.get("EL3")          # the conditional form and a plain sex restriction are fine


def test_a_sex_specific_requirement_in_any_shape_is_flagged():
    from clinical_asset.protocol import typecheck

    female = {"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": "demographic:sex", "op": "in", "categories": ["female"]}
    a = {"node": "LEAF", "kind": "flag", "status": "EXECUTABLE", "variable": "var:a", "expected": True}
    b = {"node": "LEAF", "kind": "flag", "status": "EXECUTABLE", "variable": "var:b", "expected": True}
    either = {"node": "OR", "children": [{"node": "AND", "children": [female, a]}, {"node": "AND", "children": [female, b]}]}
    conditional = {"node": "IF", "condition": female, "then": {"node": "OR", "children": [a, b]}}
    assert typecheck._subgroup_conjunction(either) and not typecheck._subgroup_conjunction(conditional)
    assert not typecheck._subgroup_conjunction(female) and not typecheck._subgroup_conjunction(a)


def test_a_category_test_on_age_is_undecidable_at_runtime_and_a_static_error():
    from clinical_asset.protocol import typecheck

    leaf = {"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": "demographic:age", "op": "in", "categories": ["adult"]}
    assert ex.evaluate(leaf, {"demographic:age": {"value": 38.0, "unit": "year"}}) is None
    spec = {"eligibility": [{"criterion_id": "EL1", "kind": "inclusion", "logic": leaf}], "stratification": {"strata": []},
            "treatment_phases": [], "grade_definitions": [], "interventions": [], "radiotherapy": [], "dose_modifications": [],
            "endpoints": [], "arms": [], "randomization": {}, "interim_analyses": []}
    assert any("age tested as a category" in i for i in typecheck.check(spec)[0]["EL1"])


def test_rejections_that_do_not_change_execution_are_accepted_only_by_majority():
    class Stub:
        def __init__(self, harmless):
            self.harmless = harmless

        def extract(self, task, schema, payload):
            assert task == "protocol_materiality"
            return {"verdicts": [{"item_id": i["item_id"], "changes_execution": not self.harmless.get(i["item_id"], False),
                                  "reason": "r"} for i in payload["items"]]}

    c = object.__new__(comp.ProtocolCompiler)
    c.critical_votes, c.workers = 3, 2
    flags = []

    def ballots():
        return {k: {"component": "design_rules", "rendering": "x", "votes": 3,
                    "cast": [{"verdict": "INCOMPLETE", "reviewer_note": "omits the sites where it runs"}] * 3,
                    "item": {"semantic_status": "INCOMPLETE", "verification": {"verdict": "INCOMPLETE"}}} for k in ("DR1", "DR2")}
    b = ballots()
    c.model = Stub({"DR1": True})
    c._materiality(b, {}, lambda *a: flags.append(a))
    assert b["DR1"]["item"]["semantic_status"] == "FAITHFUL" and "accepted_non_operational" in b["DR1"]["item"]["verification"]
    assert b["DR2"]["item"]["semantic_status"] == "INCOMPLETE"
