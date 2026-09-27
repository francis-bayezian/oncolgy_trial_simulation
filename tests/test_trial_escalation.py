"""Rule-based dose escalation (synthetic fixtures; no protocol-specific content)."""

import numpy as np

from clinical_asset.trial import escalation as es

RULE = {"cohort_size": 3, "rules": [
    {"action": "escalate", "dlt": 0, "comparator": "exactly", "patients": 3},
    {"action": "expand_cohort", "dlt": 1, "comparator": "exactly", "patients": 3},
    {"action": "escalate", "dlt": 1, "comparator": "at_most", "patients": 6},
    {"action": "stop_dose_exceeds_mtd", "dlt": 2, "comparator": "at_least", "patients": 6}]}


def test_no_toxicity_clears_every_level_and_certain_toxicity_stops_at_the_first():
    rng = np.random.default_rng(0)
    safe = es.run_escalation(RULE, [0.0, 0.0, 0.0], rng)
    assert safe["mtd_level"] is None and safe["treated"] == [3, 3, 3]
    toxic = es.run_escalation(RULE, [1.0, 1.0], rng)
    assert toxic["mtd_level"] == -1 and toxic["treated"] == [3, 0]


def test_a_toxic_level_stops_escalation_and_the_level_below_is_selected():
    rng = np.random.default_rng(1)
    r = es.run_escalation(RULE, [0.0, 0.0, 1.0], rng)
    assert r["mtd_level"] == 1 and r["treated"] == [3, 3, 3]


def test_operating_characteristics_cover_every_truth_of_the_grid():
    rows = es.operating_characteristics(RULE, 3, 2000, 2)
    assert [r["true_highest_tolerable_level"] for r in rows] == [-1, 0, 1, 2]
    assert all(abs(sum(r["selection"].values()) - 1) < 1e-9 for r in rows) and all(r["prob_correct"] > 0.4 for r in rows)
