"""Safety asset V3 (synthetic fixtures; no trial-specific content)."""

import numpy as np
from scipy import special, stats

from clinical_asset import safety3 as s3


def test_doses_follow_the_agent_and_units_normalise():
    text = r"Drug A 175 mg/m\^2 IV on day 1; Drug B 0.5 mg daily. Drug C given IV"
    assert s3.doses_in(text, "Drug A") == [(175.0, "mg/m2")] and s3.doses_in(text, "drug b") == [(0.5, "mg")]
    assert s3.doses_in(text, "Drug C") == []


def _arm(i, rng):
    return {"classes": ["k1"] if i % 2 else ["k2"], "unclassified_agent": False, "pediatric": bool(i % 3 == 0), "log_relative_dose": float(rng.normal(0, 0.5)),
            "dose_unknown": False, "phase": "PHASE2", "disease_family": "f"}


def test_event_model_recovers_class_dose_and_age_effects_with_censoring():
    rng = np.random.default_rng(0)
    arms = [_arm(i, rng) for i in range(1500)]
    levels = s3.covariate_levels(arms)
    X, cols, sd = s3.design(arms, levels, True)
    truth = {"intercept": -2.0, "class=k1": 1.0, "pediatric": -0.5, "log_relative_dose": 0.8}
    beta = np.array([truth.get(c, 0.0) for c in cols])
    n = np.full(len(arms), 80)
    y = rng.binomial(n, special.expit(X @ beta))
    cens = np.arange(len(arms)) % 4 == 0                        # a quarter only known to be at or below a threshold of 10%
    y_obs = np.where(cens, np.maximum(y, 8), y)
    keep = ~cens | (y <= 8)                                      # censored arms are those not listed: below the threshold
    fit = s3.fit_event(X[keep], sd, y_obs[keep], n[keep], cens[keep])
    b = dict(zip(cols, fit["beta"], strict=True))
    assert abs(b["class=k1"] - b["class=k2"] - 1.0) < 0.15 and abs(b["pediatric"] + 0.5) < 0.15 and abs(b["log_relative_dose"] - 0.8) < 0.15


def test_no_informative_class_is_unresolved_not_a_catch_all():
    asset = {"manifest": {"design": {"levels": {"classes": ["k1"], "phase": ["PHASE2"], "family": ["f"]}, "cols": []}, "tau_default": 0.5}, "fits": {}}
    arm = {"classes": [], "unclassified_agent": True, "pediatric": False, "log_relative_dose": 0.0, "dose_unknown": True, "phase": "PHASE2", "disease_family": "f"}
    assert s3.predict_arm(asset, arm)["status"] == "UNRESOLVED"


def test_predictive_probability_integrates_the_rate_spread():
    d = {"logit_mu": float(special.logit(0.2)), "logit_sigma": 0.0}
    assert abs(s3._log_pred_prob(d, 3, 10) - np.log(stats.binom.pmf(3, 10, 0.2))) < 1e-9


def test_marginal_tau_recovers_the_between_trial_spread_of_a_rare_event():
    rng = np.random.default_rng(4)
    eta = np.full(600, special.logit(0.03))
    n = rng.integers(20, 200, size=600)
    y = rng.binomial(n, special.expit(eta + 0.8 * rng.normal(size=600)))
    assert abs(s3.marginal_tau(eta, y, n) - 0.8) < 0.15
    y0 = rng.binomial(n, special.expit(eta))
    assert s3.marginal_tau(eta, y0, n) < 0.2
