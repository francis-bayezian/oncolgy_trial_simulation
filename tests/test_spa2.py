"""Milestone 2: hierarchical borrowing, censored toxicity, survival synthesis."""

import math

import numpy as np

from clinical_asset.spa.models import NormalRandomEffects
from clinical_asset.spa2 import borrow, survival, toxicity
from clinical_asset.spa2.hierarchy import fit_hierarchy, predictive


def test_single_level_tree_matches_milestone_1_random_effects() -> None:
    rng = np.random.default_rng(4)
    se = rng.uniform(0.1, 0.3, 8)
    y = rng.normal(0.5, np.sqrt(se**2 + 0.2**2))
    tree = fit_hierarchy([{"study": f"s{i}", "y": y[i], "s2": se[i] ** 2, "obs_id": i} for i in range(8)],
                         ["study"], [0.5], root_sd=1.0, samples=4000, draws=2000)
    m1 = NormalRandomEffects(0.0, 1.0, 0.5).fit(y, se)
    assert abs(tree.root_draws.mean() - m1.posterior["mean"]) < 0.05
    assert abs(float(np.median(tree.tau_draws)) - m1.heterogeneity["tau"]["median"]) < 0.06


def test_strong_leaf_evidence_dominates_and_sparse_leaf_borrows() -> None:
    rng = np.random.default_rng(1)
    records = []
    for d in range(5):  # five drugs in one class around logit 0
        for s in range(6):
            records.append({"cls": "A", "drug": f"d{d}", "study": f"d{d}s{s}", "y": rng.normal(0, 0.1), "s2": 0.01, "obs_id": len(records)})
    records.append({"cls": "A", "drug": "strong", "study": "x1", "y": 2.0, "s2": 0.0004, "obs_id": 900})
    records.append({"cls": "A", "drug": "sparse", "study": "x2", "y": 2.0, "s2": 1.0, "obs_id": 901})
    fit = fit_hierarchy(records, ["cls", "drug", "study"], [1.0, 0.5, 0.3], root_sd=2.0, samples=3000)
    strong, sparse = fit.node_draws[("A", "strong")].mean(), fit.node_draws[("A", "sparse")].mean()
    assert strong > 1.7  # precise leaf evidence is not overridden by the parent
    assert sparse < 1.5  # imprecise leaf is shrunk toward its class
    assert (2.0 - sparse) > 5 * (2.0 - strong)  # shrinkage follows the precision of the leaf
    new_drug = predictive(fit, ("A", "new", "new_study"), rng)
    assert abs(np.median(new_drug)) < 0.6


def test_single_study_parameter_borrows_heterogeneity_instead_of_estimating_it() -> None:
    records = []
    for s, (y, n) in enumerate([(20, 100), (35, 100), (50, 100), (28, 90)]):
        ly, s2 = borrow._logit_obs(y, n)
        records.append({"disease_family": "f", "disease": "d", "setting": "unspecified", "modality": "m",
                        "class_signature": "c", "regimen": "r1", "study": f"s{s}", "arm": f"s{s}|a", "y": ly, "s2": s2,
                        "n": n, "count": y, "obs_id": s, "profile_id": None})
    ly, s2 = borrow._logit_obs(12, 40)
    records.append({**records[0], "regimen": "single", "study": "one", "arm": "one|a", "y": ly, "s2": s2, "n": 40, "count": 12, "obs_id": 99})
    target = {"domain": "response", "variable": "objective_response_rate"}
    fitted = borrow.fit_target("efficacy_proportion", target, records, seed=3)
    params = {p["context"]["regimen"]: p for p in borrow.publish_target("efficacy_proportion", target, fitted, seed=3)}
    single = params["single"]
    assert single["support"]["level"] == "C"
    assert single["within_study_posterior"]["distribution"] == "Beta(12.5, 28.5)"
    assert single["heterogeneity"]["source"] == "estimated across the target hierarchy"
    # The future-study interval is wider than the within-study posterior (heterogeneity added).
    width = lambda d: d["q975"] - d["q025"]
    assert width(single["future_study_predictive"]) > width(single["within_study_posterior"])


def test_censored_reporting_threshold_pulls_selected_rates_down() -> None:
    exact = [(30, 100), (28, 100)]
    censored = [(5, 100)] * 6  # six studies did not list the event: at most 5/100
    corrected = toxicity.fit_censored(exact, censored, seed=1)
    naive = toxicity.fit_censored(exact, [], seed=1)
    assert np.median(corrected["m"]) < np.median(naive["m"]) - 0.05


def test_unlisted_serious_event_is_an_exact_zero_but_non_serious_is_censored() -> None:
    arm_a, arm_b = ("N1", "A"), ("N2", "B")
    observations = [
        {"nct_id": "N1", "arm": arm_a, "event": "x", "seriousness": "serious", "y": 3, "n": 50, "threshold": 5.0, "has_table": True},
        {"nct_id": "N2", "arm": arm_b, "event": "other", "seriousness": "serious", "y": 1, "n": 60, "threshold": 5.0, "has_table": True},
        {"nct_id": "N1", "arm": arm_a, "event": "y", "seriousness": "non_serious", "y": 10, "n": 50, "threshold": 5.0, "has_table": True},
        {"nct_id": "N2", "arm": arm_b, "event": "z", "seriousness": "non_serious", "y": 9, "n": 60, "threshold": 5.0, "has_table": True},
    ]
    context = {arm_a: {"class_signature": "c"}, arm_b: {"class_signature": "c"}}
    contexts = toxicity.build_contexts(observations, context, min_studies=1)
    serious = contexts[("x", "serious", "c")]
    assert (arm_b, 0, 60) in serious["exact"] and not serious["censored"]
    non_serious = contexts[("y", "non_serious", "c")]
    assert non_serious["censored"] == [(arm_b, 3, 60)]  # floor(5% of 60)


def test_survival_curve_recovered_from_median_and_landmarks() -> None:
    lam, k = 16.0, 1.3
    med = lam * math.log(2) ** (1 / k)
    s24 = math.exp(-((24 / lam) ** k))
    s12 = math.exp(-((12 / lam) ** k))
    cons = [{"kind": "median", "t": med, "y": math.log(med), "se": 0.08, "study": "a", "N": 200},
            {"kind": "landmark", "t": 12, "p": s12, "y": math.log(-math.log(s12)), "se": 0.08, "study": "a", "N": 200},
            {"kind": "landmark", "t": 24, "p": s24, "y": math.log(-math.log(s24)), "se": 0.1, "study": "a", "N": 200}]
    rng = np.random.default_rng(2)
    fit = survival.fit_family("weibull", cons, (0.0, 0.7), rng)
    d = survival.derived([fit], np.array([1.0]), rng)
    assert d["median_months"]["q025"] < med < d["median_months"]["q975"]
    assert d["survival_24_months"]["q025"] < s24 < d["survival_24_months"]["q975"]
    assert survival.identifiability(cons) == "HIGH"
    assert survival.identifiability(cons[:1]) == "LOW"
