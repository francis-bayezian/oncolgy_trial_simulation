"""Randomized probability integral transform (PIT) calibration for binomial predictions.

Held-out outcomes are counts. Interval coverage computed from replicated counts counts ties with
the interval boundary as covered, which inflates coverage for small arms. The randomized PIT,
u = F(y - 1) + V * (F(y) - F(y - 1)) with V ~ Uniform(0, 1) and F the predictive CDF of the
count, is exactly uniform under a calibrated model; central-interval coverage is then
P(0.025 <= u <= 0.975), P(0.25 <= u <= 0.75), and so on.

The leave-one-study-out design, seeds and fits are those of proportions.loo_one, so the
predictive distributions scored here are the same ones.
"""

import json

import numpy as np
from scipy import special

from ..spa.models import BetaBinomial
from ..spa2 import borrow as borrow2
from ..spa2.hierarchy import fit_hierarchy as fit_gaussian
from ..spa2.hierarchy import predictive as predictive_gaussian
from .binomial_tree import deepest_known, predictive
from .proportions import (  # noqa: F401
    RULES,
    TAILS,
    fit_group,
    probability_range,
    randomized_pit,
    summarise_pit,
)


def loo_pit(args: tuple) -> dict | None:
    spec, held_study, seed = args
    group, records = spec["group"], spec["records"]
    rest = [r for r in records if r["study"] != held_study]
    held = [r for r in records if r["study"] == held_study]
    if not rest or not held:
        return None
    rule = RULES["groups"][group]
    levels = rule["levels"]
    depth = levels.index(rule["parameter_level"]) + 1
    rng = np.random.default_rng(seed)
    target_arm = held[0]
    path = tuple(target_arm[level] for level in levels)
    y, n = int(target_arm["count"]), int(target_arm["n"])
    fit = fit_group(group, rest, seed, samples=300, draws=400)
    known = deepest_known(fit, path[:depth])
    pit_rng = np.random.default_rng(seed + 1)
    out = {"group": group, "target": json.dumps(spec["target"], default=str), "held_out_study": held_study, "y": y, "n": n,
           "borrowing_depth": levels[known - 1] if known else "root", "pit": {}}
    for tail, nu in TAILS.items():
        out["pit"][f"m3_{tail}"] = randomized_pit(special.expit(predictive(fit, path, rng, nu)), y, n, pit_rng)
    out["probability_range"] = probability_range(float(np.median(special.expit(predictive(fit, path, rng)))))
    v2_rule = borrow2.RULES["groups"][group]
    v2_rest = []
    for r in rest:
        ly, s2 = borrow2._logit_obs(int(r["count"]), int(r["n"]))
        v2_rest.append({**r, "y": ly, "s2": s2})
    fit2 = fit_gaussian(v2_rest, v2_rule["levels"], v2_rule["tau_prior_scale"], v2_rule["root_sd"], samples=400, draws=400, seed=seed)
    out["pit"]["m2_gaussian_logit"] = randomized_pit(
        special.expit(predictive_gaussian(fit2, tuple(target_arm[lv] for lv in v2_rule["levels"]), rng)), y, n, pit_rng)
    pooled = sum(r["count"] for r in rest) / sum(r["n"] for r in rest)
    out["pit"]["global_pooled_rate"] = randomized_pit(np.array([pooled]), y, n, pit_rng)
    leaf_studies = {r["study"] for r in rest if tuple(r[lv] for lv in levels[:depth]) == path[:depth]}
    leaf_rest = [r for r in rest if r["study"] in leaf_studies and tuple(r[lv] for lv in levels[:depth]) == path[:depth]]
    if leaf_rest:
        bb = BetaBinomial().fit(np.array([r["count"] for r in leaf_rest]), np.array([r["n"] for r in leaf_rest]))
        out["pit"]["leaf_only_beta_binomial"] = randomized_pit(bb.draws["p_new_study"], y, n, pit_rng)
    return out
