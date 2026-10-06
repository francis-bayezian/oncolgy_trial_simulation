"""Analysis results layer (lesson L037): response derived from measurements under the protocol's own thresholds,
standard time-to-event summaries, and FDA-table helpers (synthetic fixtures only)."""

import numpy as np

from clinical_asset.trial import analysis_results as ar


def _crit(level, name, direction, value):
    return {"level": level, "category": {"text": name}, "threshold": {"value": value, "direction": direction}}


def test_criteria_come_from_the_protocol_else_recist():
    spec = {"response_criteria": {"categories": [_crit("target", "Partial response (PR)", "decrease", 50.0),
                                                 _crit("target", "Progressive Disease (PD)", "increase", 25.0),
                                                 _crit("overall", "VGPR", "decrease", 90.0)], "overall_rules": [{"text": "confirmed"}]}}
    c = ar.criteria(spec)
    assert (c["pr"], c["pd"], c["confirm"]) == (50.0, 25.0, True) and c["deeper"][0][0] == 90.0
    d = ar.criteria({"response_criteria": {"categories": []}})
    assert (d["pr"], d["pd"], d["pd_abs_mm"]) == (30.0, 20.0, 5.0) and "A25" in d["source"]


def test_overall_response_table_and_confirmation():
    assert ar._overall("PR", "NON-CR/NON-PD", False) == "PR" and ar._overall("CR", "CR", False) == "CR"
    assert ar._overall("SD", "NONE", True) == "PD" and ar._overall("CR", "NON-CR/NON-PD", False) == "PR"
    confirmed = [(56, "PR"), (84, "PR"), (112, "SD")]
    unconfirmed = [(56, "PR"), (70, "PD")]
    assert ar.best_overall_response(confirmed, True) == ("PR", 56)
    assert ar.best_overall_response(unconfirmed, True)[0] == "SD"
    assert ar.best_overall_response(unconfirmed, False)[0] == "PR"
    assert ar.best_overall_response([(28, "SD")], True)[0] == "NE"            # SD before the minimum duration


def test_tumour_measurements_derive_the_latent_response():
    rng = np.random.default_rng(0)
    c = ar.criteria({})
    out = ar.simulate_tumour("S1", "A", 400, 56, 1.0, 0.0, None, None, None, c, rng)
    sums = [r["TRORRES"] for r in out["tr"] if r["TRTESTCD"] == "SUMDIAM"]
    assert sums[-1] <= sums[0] * 0.7 and {v for _, v in out["visits"][1:]} <= {"PR", "CR"}
    prog = ar.simulate_tumour("S2", "A", 400, 56, 0.0, 0.0, 120.0, None, None, c, np.random.default_rng(1))
    assert prog["pd_day"] == 168 and prog["visits"][-1][1] == "PD"


def test_km_and_hazard_ratio():
    t = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], float) * 30.4375
    e = np.ones(10, bool)
    s = ar.km_summary(t, e)
    assert s["median_months"] == 5.0 and s["events"] == 10
    rng = np.random.default_rng(3)
    a, b = rng.exponential(10, 400), rng.exponential(10, 400)
    hr = ar.hazard_ratio(a, np.ones(400, bool), b, np.ones(400, bool))
    assert 0.8 < hr["hr"] < 1.25 and hr["logrank_p_two_sided"] > 0.01


def test_soc_map_falls_back_to_the_word_set(tmp_path):
    f = tmp_path / "m.json"
    f.write_text('{"map": {"acute kidney failure": {"soc": "Renal and urinary disorders"}}}', encoding="utf-8")
    m = ar.SocMap(f)
    assert m.soc("Acute_kidney_failure") == m.soc("kidney failure acute adverse events") == "Renal and urinary disorders"
    assert m.soc("unknown thing") == "SOC not determined"
