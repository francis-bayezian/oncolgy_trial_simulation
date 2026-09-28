"""Operational asset V2 (synthetic fixtures; no trial-specific content)."""

import numpy as np

from clinical_asset.planning import operational as op


def test_stop_reasons_are_classed_by_why_not_by_that():
    assert op.accrual_reason("Slow accrual") and op.accrual_reason("lack of eligible patients") and op.accrual_reason("closed to accrual due to poor accrual")
    assert not op.accrual_reason("Study closed to enrollment because the interim analysis showed futility")
    assert not op.accrual_reason("Enrollment completed early; sponsor decision") and not op.accrual_reason("Lack of funding")
    assert op.outcome({"status": "WITHDRAWN"}) == "withdrawn" and op.outcome({"status": "SUSPENDED"}) is None
    assert op.outcome({"status": "TERMINATED", "why_stopped": "poor recruitment"}) == "terminated_accrual"


def test_family_matcher_weights_family_specific_words(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    fam = tmp_path / "fam.parquet"
    pq.write_table(pa.Table.from_pylist([
        {"disease": "Diffuse large cell lymphoma", "disease_family": "lymphoma", "confidence": 1.0},
        {"disease": "Squamous cell carcinoma of the lung", "disease_family": "lung", "confidence": 1.0},
        {"disease": "Renal cell carcinoma", "disease_family": "renal", "confidence": 1.0},
        {"disease": "Ductal carcinoma of the breast", "disease_family": "breast", "confidence": 1.0}]), fam)
    match = op.family_matcher(fam)
    assert match("Recurrent Lymphoma")[0] == "lymphoma" and match("Lung Cancer")[0] == "lung"
    assert match("Carcinoma")[0] == "other"                      # shared by three families: a tie, not a guess
    assert match("Diabetes")[0] == "other"


def _row(i, rng, effect):
    r = {"randomized": bool(i % 2), "pediatric": False, "start_year": 2010, "arms": 2, "phase": "PHASE2", "sponsor_class": "OTHER",
         "disease_family": "a"}
    logits = np.array([0.0, -1.5 + effect * r["randomized"], -1.0, -2.0])
    p = np.exp(logits) / np.exp(logits).sum()
    return {**r, "outcome": op.OUTCOMES[rng.choice(4, p=p)]}


def test_failure_model_recovers_an_effect_and_is_calibrated():
    rng = np.random.default_rng(0)
    rows = [_row(i, rng, 1.0) for i in range(6000)]
    model = op.fit_failure(rows)
    b = dict(zip(model["cols"], np.array(model["coef"])[:, 0], strict=True))       # log-odds of terminated_accrual vs completed
    assert abs(b["randomized"] - 1.0) < 0.2
    cv = op.cross_validate_failure(rows, folds=3)
    assert cv["log_loss"] < cv["base_rate_log_loss"] and all(abs(d["predicted"] - d["observed"]) < 0.06 for d in cv["accrual_failure_reliability"])


def test_family_of_terms_takes_the_specific_majority_and_never_guesses_a_tie():
    m = {"Breast Neoplasms": {"label": "breast", "confidence": 0.95}, "Neoplasm Metastasis": {"label": "mixed_solid_tumors", "confidence": 0.9},
         "Lung Neoplasms": {"label": "lung", "confidence": 0.95}, "Neoplasms": {"label": "other", "confidence": 0.9},
         "Colitis": {"label": "colorectal", "confidence": 0.3}}
    assert op.family_of_terms(["Breast Neoplasms", "Neoplasm Metastasis", "Neoplasms"], m) == ("breast", "Breast Neoplasms")
    assert op.family_of_terms(["Neoplasm Metastasis", "Neoplasms"], m)[0] == "mixed_solid_tumors"
    assert op.family_of_terms(["Breast Neoplasms", "Lung Neoplasms"], m)[0] == "other"
    assert op.family_of_terms(["Colitis"], m)[0] == "other"                  # below the confidence threshold
