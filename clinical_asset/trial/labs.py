"""Laboratory values during the journey, derived from laboratory-type adverse events.

Baseline laboratory values are not generated: registry baseline tables almost never report them (see
data/evidence_baseline_v1/manifest.json), so they stay unsupported, and patients are within normal limits under
assumption A10. During a laboratory-type adverse event of grade g, the value is drawn uniformly within grade g's range
of the NCI CTCAE v5.0 definition (assumption A5), using the reference limits below (assumption A12).
"""

import re

from ..reference import vocabulary
from .patient_state import sourced

# CTCAE v5.0 grade ranges and reference limits: reference data (clinical_asset/reference/clinical_vocabulary.json)
_V = vocabulary()
REFERENCE = _V["lab_reference_lln"]                                        # LLN, assumption A12
TESTS = {k: {**v, "grades": {int(g): tuple(r) for g, r in v["grades"].items()}} for k, v in _V["ctcae_v5_lab_grades"].items()}


def test_of(term: str) -> str | None:
    for code, t in TESTS.items():
        if re.search(t["terms"], (term or "").lower().replace("_", " ")):
            return code
    return None


def value(code: str, grade: int, rng) -> dict:
    lo, hi = TESTS[code]["grades"][min(max(grade, 1), 4)]
    v = round(float(rng.uniform(lo, hi)), 2)
    return sourced({"test": TESTS[code]["label"], "value": v, "unit": TESTS[code]["unit"], "grade": grade}, "assumption",
                   f"CTCAE v5.0 grade {grade} range for {TESTS[code]['label']} ({lo:g}-{hi:g} {TESTS[code]['unit']})",
                   assumption="A5_lab_value_in_grade")


def normal(code: str) -> dict:
    return sourced({"test": TESTS[code]["label"], "value": None, "unit": TESTS[code]["unit"], "grade": 0}, "assumption",
                   "within normal limits (no laboratory adverse event active); value not simulated", assumption="A10_normal_baseline_labs")
