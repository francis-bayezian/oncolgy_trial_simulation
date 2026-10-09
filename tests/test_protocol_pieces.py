"""Long list sections are cut by code at numbered-item boundaries, and long tables by rows, before extraction (L047)."""

from clinical_asset.protocol import compiler as comp
from clinical_asset.protocol.ingest import Line, Section, Table


def test_long_section_is_cut_at_item_starts_and_tables_by_rows():
    lines = []
    for k in range(1, 21):
        lines += [Line(1, k, f"{k}. Criterion {k} " + "x" * 300), Line(1, k + 0.5, "continued wording of the same criterion")]
    rows = [["Toxicity", "Action"]] + [[f"Tox {i}", "y" * 200] for i in range(40)]
    s = Section("5.1", "Inclusion", 2, 1, 2, 0.0, lines, [Table(2, 1.0, rows)])
    parts = comp._pieces(s, 2000)
    text_parts = [p for p in parts if p.lines]
    assert len(text_parts) > 1 and all(p.number == "5.1" for p in parts)
    assert all(comp.ITEM_START.match(p.lines[0].text) for p in text_parts)          # every part starts at an item
    assert sum(len(p.lines) for p in text_parts) == len(lines)                        # nothing lost
    tables = [p.tables[0] for p in parts if p.tables]
    assert len(tables) > 1 and all(t.rows[0] == ["Toxicity", "Action"] for t in tables)
    assert sum(len(t.rows) - 1 for t in tables) == 40


def test_numbered_items_the_model_skipped_are_found_by_code():
    s = Section("5.2", "Exclusion", 2, 1, 1, 0.0, [Line(1, 1.0, "1. Has active brain metastases requiring therapy."),
                                                   Line(1, 2.0, "2. Has uncontrolled infection requiring antibiotics."),
                                                   Line(1, 3.0, "continued text"),
                                                   Line(1, 4.0, "3. Is pregnant or breastfeeding at screening.")], [])
    out = {"criteria": [{"evidence_quote": "Has active brain metastases requiring therapy.", "label_quote": ""}]}
    missing = comp._unmatched([s], out)
    assert len(comp._listed_items([s])) == 3 and len(missing) == 2
    assert missing[0].startswith("2. Has uncontrolled infection") and missing[1].startswith("3. Is pregnant")


def test_administrations_missing_from_an_arm_or_entirely_are_found_by_code():
    table = Table(5, 1.0, [["Arm Name", "Intervention Name", "Dosage Level(s)"],
                           ["Arm 1 (all)", "Drugone", "100 mg"], ["Arm 2 (all)", "Drugone", "100 mg"],
                           ["Arm 2 (all)", "Agentwo", "AUC 5"]])
    s = Section("6.1", "Interventions", 2, 5, 5, 0.0, [Line(5, 2.0, "• Supportive acid 350 to 1000 μg po daily"),
                                                       Line(5, 3.0, "Solution 25 mg/mL in a vial")], [table])
    req = comp._dosing_requirements([s])
    assert {r["agent"] for r in req} == {"Drugone", "Agentwo", "Supportive acid"}     # 'Solution' is not an agent
    given = [("drugone", {"arm 1"}), ("agentwo", set())]                                # no arms = all arms
    gaps = comp._administration_gaps(req, given)
    assert len(gaps) == 2 and "arm 2" in gaps[0] and "Supportive acid" in gaps[1]


def test_short_section_is_one_piece():
    s = Section("5.2", "Exclusion", 2, 1, 1, 0.0, [Line(1, 1.0, "1. Short.")], [])
    assert comp._pieces(s, 8000) == [s]
