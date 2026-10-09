"""Evidence synthesis (L056): estimands are never pooled, tier-3 shrinkage is learned only from paired evidence."""

import numpy as np

from clinical_asset.trial import control_benchmark as cb
from clinical_asset.trial import evidence_synthesis as es


def _t3(c, est, value, se=0.02):
    return {"characteristic": c, "estimand": est, "tier": 3, "estimate": value, "se": se, "citation": "corpus"}


def _t1(c, est, value, se=0.03):
    return {"characteristic": c, "estimand": est, "tier": 1, "estimate": value, "se": se, "citation": "paper"}


def test_different_estimands_are_not_pooled_and_lambda_needs_pairs():
    ev = [_t3("female", "prognostic_log_or:serious_ae", -0.4), _t1("female", "prognostic_log_or:severe_ae_grade3plus", 0.29)]
    s = es.synthesise(ev, draws=1000)
    assert s["learning"]["paired_effects"] == []                          # severe AE is not the serious-AE estimand
    assert "NOT LEARNED" in s["learning"]["lambda_and_tau_ecological"]
    serious = s["effects"]["female|prognostic_log_or:serious_ae"]
    assert serious["tiers"] == [3] and serious["posterior_mean"] < 0      # only its own (tier-3) evidence moves it
    lo, hi = serious["interval_95"]
    assert hi - lo > 1.0                                                  # aggregate-only evidence stays uncertain


def test_paired_evidence_teaches_lambda():
    # trial-level estimates twice the patient-level truth: lambda is learned near 0.5
    ev = []
    for i, truth in enumerate((0.3, -0.2, 0.5, 0.4, -0.35, 0.25)):
        ev += [_t3(f"x{i}", "prognostic_log_or:death", 2 * truth, 0.02), _t1(f"x{i}", "prognostic_log_or:death", truth, 0.02)]
    s = es.synthesise(ev, draws=4000)
    lo, mid, hi = s["learning"]["lambda_posterior"]
    assert len(s["learning"]["paired_effects"]) == 6 and 0.3 < mid < 0.7 and hi - lo < 0.6


def test_a_replicate_draw_is_one_coherent_set():
    ev = [_t3("age10", "prognostic_log_or:death", 0.3), _t3("female", "prognostic_log_or:death", -0.4)]
    s = es.synthesise(ev, draws=500)
    d1, d2 = es.draw(s, 7), es.draw(s, 507)
    assert d1 == d2 and set(d1) == {("age10", "prognostic_log_or:death"), ("female", "prognostic_log_or:death")}
    assert es.draw(s, None)[("age10", "prognostic_log_or:death")] == s["effects"]["age10|prognostic_log_or:death"]["posterior_mean"]


def test_dersimonian_laird_finds_heterogeneity():
    k = np.array([10, 30, 50, 70]), np.array([100, 100, 100, 100])
    mu, vmu, tau2 = cb._dersimonian_laird(*map(lambda a: a.astype(float), k))
    assert tau2 > 0.5 and -1 < mu < 0.5
