"""Milestone 3: exact binomial hierarchy, baseline models, copula, protocol generator, survival fusion."""

import math

import numpy as np
import pytest
from scipy import special, stats

from clinical_asset.spa2 import survival as surv2
from clinical_asset.spa3 import baseline, survival_fusion
from clinical_asset.spa3.binomial_tree import (
    build_flat_tree,
    ep_fit,
    fit_binomial_hierarchy,
    predictive,
    tilted_moments,
)
from clinical_asset.spa3.protocol import BaselineGenerator, ProtocolQuery, TargetModel, retrieve

DATA = [(0, 12), (1, 30), (3, 25), (0, 8), (40, 45), (2, 200)]


def _records():
    return [{"g": "a" if i < 3 else "b", "arm": f"x{i}", "count": y, "n": n, "obs_id": i, "study": f"s{i}"}
            for i, (y, n) in enumerate(DATA)]


def _brute(tau_g: float, tau_a: float, root_sd: float = 2.0) -> tuple[float, float]:
    """log marginal likelihood and root posterior mean by nested numerical integration."""
    th = np.linspace(-15, 15, 1201)
    r = np.linspace(-10, 10, 321)
    g = np.linspace(-12, 12, 321)
    groups = {}
    for grp in "ab":
        prod = np.ones_like(g)
        for rec, (y, n) in zip(_records(), DATA, strict=True):
            if rec["g"] == grp:
                like = stats.binom.pmf(y, n, special.expit(th))
                prod *= (stats.norm.pdf(th[None, :], g[:, None], tau_a) * like).sum(1) * (th[1] - th[0])
        groups[grp] = prod
    post = stats.norm.pdf(r, 0, root_sd)
    for grp in "ab":
        post = post * (stats.norm.pdf(g[None, :], r[:, None], tau_g) * groups[grp][None, :]).sum(1) * (g[1] - g[0])
    z = post.sum() * (r[1] - r[0])
    return math.log(z), float((r * post).sum() / post.sum())


def test_tilted_moments_match_numerical_integration() -> None:
    for y, n, mu, var in ((0, 50, -1.0, 2.0), (7, 9, 0.0, 0.5), (300, 1000, -2.0, 4.0)):
        log_z, mean, variance = tilted_moments(np.array([y]), np.array([n]), np.array([mu]), np.array([var]))
        th = np.linspace(-20, 20, 40001)
        f = stats.binom.pmf(y, n, special.expit(th)) * stats.norm.pdf(th, mu, math.sqrt(var))
        z = f.sum() * (th[1] - th[0])
        m = (th * f).sum() / f.sum()
        v = ((th - m) ** 2 * f).sum() / f.sum()
        assert abs(log_z[0] - math.log(z)) < 1e-4
        assert abs(mean[0] - m) < 1e-4
        assert abs(variance[0] - v) < 1e-4 * max(v, 1)


def test_exact_binomial_ep_matches_brute_force_integration() -> None:
    tree = build_flat_tree(_records(), ["g", "arm"])
    taus = np.array([[0.8, 0.6], [0.3, 1.2]])
    ep = ep_fit(tree, taus, 2.0, tol=1e-6, logz_tol=1e-8, iterations=200)
    for k, (tg, ta) in enumerate(taus):
        log_z, root_mean = _brute(tg, ta)
        assert abs(ep["log_marginal"][k] - log_z) < 5e-3
        assert abs(ep["gauss"]["root_mean"][k] - root_mean) < 5e-3


def test_rare_events_are_not_inflated_by_continuity_correction() -> None:
    # 20 studies of a rare event (true rate 0.5%): the exact likelihood keeps the population
    # rate near the truth where the continuity-corrected Gaussian logit is biased upwards.
    rng = np.random.default_rng(3)
    records = [{"ctx": "c", "study": f"s{i}", "arm": f"s{i}|a", "n": 80, "count": int(rng.binomial(80, 0.005)), "obs_id": i}
               for i in range(20)]
    fit = fit_binomial_hierarchy(records, ["ctx", "study", "arm"], [1.0, 0.5, 0.1], 3.0, samples=200, draws=300, seed=1)
    p = special.expit(fit.node_draws[fit.tree.index[("c",)]])
    assert np.median(p) < 0.015
    assert fit.ess > 20
    assert predictive(fit, ("c", "new", "new"), rng).shape == (300,)


def test_parent_weight_reflects_evidence() -> None:
    records = [{"cls": "A", "drug": f"d{d}", "study": f"d{d}s{s}", "arm": f"d{d}s{s}|a", "n": 100, "count": 30, "obs_id": len(str(d)) + s}
               for d in range(4) for s in range(3)]
    records.append({"cls": "A", "drug": "big", "study": "b1", "arm": "b1|a", "n": 5000, "count": 3000, "obs_id": "big"})
    records.append({"cls": "A", "drug": "tiny", "study": "t1", "arm": "t1|a", "n": 4, "count": 3, "obs_id": "tiny"})
    for i, r in enumerate(records):
        r["obs_id"] = i
    fit = fit_binomial_hierarchy(records, ["cls", "drug", "study", "arm"], [1.0, 0.5, 0.3, 0.1], 2.0, samples=200, draws=200, seed=2)
    big = fit.parent_weight[fit.tree.index[("A", "big")]]
    tiny = fit.parent_weight[fit.tree.index[("A", "tiny")]]
    assert big < 0.2
    assert tiny > 0.5


def test_age_classes_and_latent_inversion() -> None:
    assert baseline.age_class(18, None) == "ADULT"
    assert baseline.age_class(1, 18) == "PEDIATRIC"
    assert baseline.age_class(15, 39) == "AYA"
    assert baseline.age_class(12, None) == "MIXED"
    assert baseline.age_class(None, None) == "MIXED"
    assert baseline.parse_age("6 Months") == pytest.approx(0.5)
    # Reported moments of a truncated normal are mapped back to the latent normal.
    true_mu, true_sd, lo, hi = 20.0, 10.0, 18.0, 30.0
    m, s = baseline.truncnorm_moments(true_mu, true_sd, lo, hi)
    mu, sd, flag = baseline.latent_age(m, s, lo, hi)
    assert flag == "inverted"
    assert abs(mu - true_mu) < 0.05 and abs(sd - true_sd) < 0.05
    assert baseline.latent_age(62.0, 9.0, 18.0, None)[2] == "bounds_not_binding"


def test_stick_breaking_gives_valid_probabilities() -> None:
    cond = np.array([[0.6, 0.5], [0.5, 0.2], [0.3, 0.9]])
    probs = baseline.stick_breaking(cond)
    assert probs.shape == (4, 2)
    assert np.allclose(probs.sum(0), 1.0)
    assert np.all(probs >= 0)


def test_copula_is_identity_without_within_patient_evidence_and_repairs_non_psd() -> None:
    variables = ["age", "sex", "race"]
    registry = baseline.dependency_registry([], [], [], variables)
    c = baseline.correlation_matrix(variables, registry)
    assert np.allclose(c["R"], np.eye(3))
    assert c["nonzero_offdiagonal"] == 0
    assert all(p["correlation_source"] == "PRIOR_DOMINATED" for p in registry["baseline_baseline"])
    observed = [{"a": "age", "b": "sex", "rho": 0.9}, {"a": "sex", "b": "race", "rho": 0.9}, {"a": "age", "b": "race", "rho": -0.9}]
    reg2 = baseline.dependency_registry([], [], [], variables, observed)
    c2 = baseline.correlation_matrix(variables, reg2)
    assert c2["min_eigenvalue_before"] < 0 < c2["min_eigenvalue_after"]
    assert c2["psd_repair_frobenius"] > 0
    assert np.allclose(np.diag(c2["R"]), 1.0)


def _model(name: str, kind: str, centre: float, level_values: list[float], tau: float = 0.2, draws: int = 300) -> TargetModel:
    rng = np.random.default_rng(len(name))
    context = ["age_class", "disease_family", "disease", "setting"] if name.startswith("age") else ["disease_family", "disease", "setting"]
    path = ("ADULT", "fam", "dis", "set") if name.startswith("age") else ("fam", "dis", "set")
    nodes = {}
    for d in range(1, len(path) + 1):
        nodes[path[:d]] = {"draws": rng.normal(level_values[min(d, len(level_values)) - 1], 0.05, draws).astype("float32"),
                           "studies": 5 - d // 2, "N": 1000, "study_ids": [f"s{i}" for i in range(5 - d // 2)]}
    return TargetModel(name, kind, [*context, "study"], context, nodes, np.full((draws, len(context) + 1), tau),
                       rng.normal(level_values[0], 0.05, draws), centre, {"within_variance": 100.0})


def _generator() -> BaselineGenerator:
    models = {"age_mean": _model("age_mean", "gaussian", 60.0, [0.0]), "age_sd": _model("age_sd", "gaussian", math.log(10), [0.0], tau=0.05),
              "sex_female": _model("sex_female", "binomial", 0.0, [0.0]),
              "race|0": _model("race|0", "binomial", 0.0, [special.logit(0.7)]), "race|1": _model("race|1", "binomial", 0.0, [0.0])}
    copula = {"variables": ["age", "sex", "race"], "R": np.eye(3).tolist(), "nonzero_offdiagonal": 0}
    return BaselineGenerator(models, {"race": {"categories": ["w", "b", "a"], "steps": ["race|0", "race|1"]}}, copula, {})


def test_retrieval_reports_extrapolation_and_support() -> None:
    gen = _generator()
    known = ProtocolQuery(disease="dis", disease_family="fam", setting="set", min_age=18).canonical()
    r = retrieve(gen.models["sex_female"], known)
    assert r["extrapolation_level"] == 0 and r["support"]["direct_studies"] > 0
    assert r["support"]["borrowed_parent_studies"] == 0  # the synthetic parent holds no other studies
    new_setting = retrieve(gen.models["sex_female"], {**known, "setting": "other"})
    assert new_setting["extrapolation_level"] == 1 and new_setting["support"]["direct_studies"] == 0
    new_disease = retrieve(gen.models["sex_female"], {**known, "disease": "other", "setting": "other"})
    assert new_disease["extrapolation_level"] == 2
    nothing = retrieve(gen.models["age_mean"], {**known, "age_class": "PEDIATRIC"})
    assert nothing["extrapolation_level"] == 4
    assert new_disease["theta"].std() > r["theta"].std()  # new levels add between-context uncertainty


def test_generator_respects_eligibility_and_modes() -> None:
    gen = _generator()
    protocol = ProtocolQuery(disease="dis", disease_family="fam", setting="set", min_age=50, max_age=70, sex="FEMALE",
                             allowed_categories={"race": ["b", "a"]})
    out = gen.parameters(protocol, posterior_draw=None)
    assert out["mode"] == "expected_world"
    cohort = gen.sample(out, 3000, seed=1)
    ages = np.array(cohort["age"])
    assert ages.min() >= 50 and ages.max() <= 70
    assert set(cohort["sex"]) == {"female"}
    assert set(cohort["race"]) <= {"b", "a"}
    # expected world is deterministic in its parameters; uncertainty mode varies between trials
    assert gen.parameters(protocol)["age_latent_mean"] == gen.parameters(protocol)["age_latent_mean"]
    trials = [gen.parameters(protocol, posterior_draw=d, future_study=True, seed=d)["age_latent_mean"] for d in range(30)]
    assert np.std(trials) > 0.05
    pr = gen.parameters(ProtocolQuery(disease="dis", disease_family="fam", setting="set", min_age=18))["race_probabilities"]
    assert abs(sum(pr.values()) - 1) < 1e-9 and pr["w"] > 0.6


def _curve(family: str, loc: float, shape: float, pid: str):
    row = {"parameter_id": pid, "family_weights": {family: 1.0}, "status": "PUBLISHED", "identifiability": "HIGH"}
    draws = {family: {"loc": np.full(200, loc), "shape": np.full(200, shape)}}
    return row, draws


def test_route_b_power_transform_and_relative_only_contexts() -> None:
    base_row, base_draws = _curve("weibull", math.log(12), 0.0, "c0")  # exponential, scale 12 months
    base_row.update(endpoint="overall_survival", disease="d", setting="s", treatment="control")
    hr = {"id": "h1", "hr": 0.5}
    param = {"parameter_id": "h1", "status": "PUBLISHED", "target": {"statistic_family": "hazard_ratio", "variable": "overall_survival"},
             "context": {"disease_family": "f", "disease": "d", "setting": "s", "regimen_pair": "new vs control"}, "support": {"studies": 2}}
    orphan = {**param, "parameter_id": "h2", "context": {**param["context"], "regimen_pair": "new vs unseen"}}
    records, grid = survival_fusion.fuse([param, orphan], {"h1": np.full(400, hr["hr"]), "h2": np.full(400, 0.7)}, [base_row],
                                         {"c0": base_draws}, seed=1)
    route_b = next(r for r in records if r["hr_parameter_id"] == "h1")
    assert route_b["route"] == "B" and route_b["assumption_based"] is True
    # exponential: median = 12 ln2; S0^0.5 halves the hazard, doubling the median
    assert abs(route_b["comparator_curve"]["median_months"]["median"] - 12 * math.log(2)) < 0.1
    assert abs(route_b["treatment_curve"]["median_months"]["median"] - 24 * math.log(2)) < 0.15
    s12 = route_b["treatment_curve"]["survival_12_months"]["median"]
    assert abs(s12 - math.exp(-0.5)) < 1e-3
    assert route_b["treatment_curve"]["rmst_24_months"]["median"] > route_b["comparator_curve"]["rmst_24_months"]["median"]
    orphan_rec = next(r for r in records if r["hr_parameter_id"] == "h2")
    assert orphan_rec["status"] == "ABSOLUTE_BASELINE_REQUIRED" and "treatment_curve" not in orphan_rec
    assert {g["arm"] for g in grid} == {"comparator", "treatment"}


def test_route_a_flags_proportional_hazards_support() -> None:
    base_row, base_draws = _curve("weibull", math.log(12), math.log(1.3), "c0")
    arm_row, arm_draws = _curve("weibull", math.log(12) + math.log(2) / 1.3, math.log(1.3), "c1")  # same shape: PH holds, HR 0.5
    for row, treat in ((base_row, "control"), (arm_row, "new")):
        row.update(endpoint="overall_survival", disease="d", setting="s", treatment=treat)
    param = {"parameter_id": "h1", "status": "PUBLISHED", "target": {"statistic_family": "hazard_ratio", "variable": "overall_survival"},
             "context": {"disease_family": "f", "disease": "d", "setting": "s", "regimen_pair": "new vs control"}, "support": {"studies": 1}}
    records, _ = survival_fusion.fuse([param], {"h1": np.exp(np.random.default_rng(0).normal(math.log(0.5), 0.05, 400))},
                                      [base_row, arm_row], {"c0": base_draws, "c1": arm_draws}, seed=2)
    rec = records[0]
    assert rec["route"] == "A" and rec["assumption_based"] is False
    assert rec["PH_support"] == "SUPPORTED"
    assert all(v["difference_interval_covers_zero"] for v in rec["ph_assessment"]["hr_validation"].values())
    # a curve with a different shape does not satisfy proportional hazards
    arm_row2, arm_draws2 = _curve("weibull", math.log(20), math.log(0.6), "c2")
    arm_row2.update(endpoint="overall_survival", disease="d", setting="s", treatment="new")
    records2, _ = survival_fusion.fuse([param], {"h1": np.full(400, 0.5)}, [base_row, arm_row2], {"c0": base_draws, "c2": arm_draws2}, seed=3)
    assert records2[0]["PH_support"] == "NOT_SUPPORTED"
    assert surv2.ENDPOINTS  # fusion only uses the canonical survival endpoints


def test_randomized_pit_is_uniform_for_calibrated_count_predictions() -> None:
    from clinical_asset.spa3.proportions import randomized_pit

    rng = np.random.default_rng(11)
    pits = []
    for _ in range(3000):
        p_draws = special.expit(rng.normal(-1.0, 0.7, 200))  # predictive distribution of the rate
        n = int(rng.integers(3, 40))
        y = int(rng.binomial(n, rng.choice(p_draws)))  # outcome drawn from that same predictive
        pits.append(randomized_pit(p_draws, y, n, rng))
    u = np.array(pits)
    assert abs(u.mean() - 0.5) < 0.02
    assert abs(np.mean((u >= 0.25) & (u <= 0.75)) - 0.5) < 0.03
    assert abs(np.mean((u >= 0.025) & (u <= 0.975)) - 0.95) < 0.015


def test_protocol_outside_evidence_is_sampled_and_flagged_not_crashed() -> None:
    from clinical_asset.spa3.protocol import eligibility_support

    gen = _generator()  # adult context: latent age about N(60, 10)
    child = ProtocolQuery(disease="dis", disease_family="fam", setting="set", min_age=1, max_age=12)
    params = gen.parameters(child)
    params["age_latent_sd"] = 3.0  # make the protocol range essentially unsupported
    ages = np.array(gen.sample(params, 500, seed=2)["age"])
    assert np.all((ages >= 1) & (ages <= 12)) and np.isfinite(ages).all()
    support = eligibility_support(params)
    assert support["age"] < 1e-3 and support["flag"] == "PROTOCOL_OUTSIDE_EVIDENCE"
