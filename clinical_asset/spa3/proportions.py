"""Milestone 3A: publication and calibration of binomial parameters.

Each published parameter reports, separately:

* population_posterior - the partially pooled node (the context's population proportion);
* future_study_predictive - the proportion in a new study of this context, with the
  heterogeneity learned across the target and the tail family chosen by leave-one-study-out;
* within_study_posterior - this context's own data alone (Jeffreys prior);
* parent_contribution - how much of the node's posterior precision comes from its parents
  (borrowing) versus its own data, level by level, with the studies behind each level.
"""

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import special, stats

from ..spa.models import BetaBinomial
from ..spa2 import borrow as borrow2
from ..spa2.hierarchy import fit_hierarchy as fit_gaussian
from ..spa2.hierarchy import predictive as predictive_gaussian
from .binomial_tree import deepest_known, fit_binomial_hierarchy, node_draws, predictive

RULES = json.loads(Path(__file__).with_name("hierarchy_rules.json").read_text(encoding="utf-8"))
TAILS = {"normal": None, "student_t_7": 7.0, "student_t_4": 4.0}


def quantiles(x: np.ndarray) -> dict:
    q = np.quantile(x, [0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
    return {"mean": float(np.mean(x)), "q025": float(q[0]), "q10": float(q[1]), "q25": float(q[2]), "median": float(q[3]),
            "q75": float(q[4]), "q90": float(q[5]), "q975": float(q[6])}


def scores(pred: np.ndarray, observed: float) -> dict:
    """Coverage (50/80/95), sharpness and CRPS for one held-out value from predictive draws."""
    q = np.quantile(pred, [0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
    a = np.abs(pred - observed).mean()
    b = np.abs(pred[:, None] - pred[None, : min(300, pred.size)]).mean()
    return {"covered_95": bool(q[0] <= observed <= q[6]), "covered_80": bool(q[1] <= observed <= q[5]),
            "covered_50": bool(q[2] <= observed <= q[4]), "width_95": float(q[6] - q[0]), "width_50": float(q[4] - q[2]),
            "abs_error": float(abs(q[3] - observed)), "crps": float(a - 0.5 * b)}


def fit_group(group: str, records: list[dict], seed: int, samples: int = 400, draws: int = 400):
    rule = RULES["groups"][group]
    return fit_binomial_hierarchy(records, rule["levels"], rule["tau_prior_scale"], rule["root_sd"],
                                  samples=samples, draws=draws, seed=seed)


def studies_by_prefix(records: list[dict], levels: list[str], depth: int) -> dict[tuple, set]:
    out: dict[tuple, set] = defaultdict(set)
    for r in records:
        path = tuple(r[level] for level in levels)
        for d in range(1, depth + 1):
            out[path[:d]].add(r["study"])
    return out


def publish(group: str, target: dict, fit, records: list[dict], seed: int, tail: str) -> list[dict]:
    rule = RULES["groups"][group]
    levels = rule["levels"]
    depth = levels.index(rule["parameter_level"]) + 1
    rng = np.random.default_rng(seed)
    under = studies_by_prefix(records, levels, depth)
    by_node: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        by_node[tuple(r[level] for level in levels[:depth])].append(r)
    taus = {level: quantiles(fit.tau_draws[:, i]) for i, level in enumerate(levels)}
    out = []
    for node, recs in by_node.items():
        pop = special.expit(node_draws(fit, node))
        new_path = node + tuple(f"__new_{level}__" for level in levels[depth:])
        future = special.expit(predictive(fit, new_path, rng, TAILS[tail]))
        direct = sorted({r["study"] for r in recs})
        y = sum(r["count"] for r in recs)
        n = sum(r["n"] for r in recs)
        leaf = stats.beta(0.5 + y, 0.5 + n - y)
        chain = []
        for d in range(1, depth + 1):
            key = node[:d]
            chain.append({"level": levels[d - 1], "node": str(key[-1]), "studies_under_node": len(under[key]),
                          "share_of_precision_from_parent": float(fit.parent_weight[fit.tree.index[key]])})
        parent_studies = under[node[:-1]] - set(direct) if depth > 1 else set()
        level = "A" if len(direct) >= 3 else "B" if len(direct) == 2 else "C"
        record = {
            "group": group, "target": target, "context": dict(zip(levels[:depth], node, strict=True)),
            "support": {"studies": len(direct), "arms": len(recs), "total_N": int(n), "level": level,
                        "borrowed_parent_studies": len(parent_studies)},
            "population_posterior": quantiles(pop),
            "future_study_predictive": {**quantiles(future), "tail": tail},
            "within_study_posterior": {
                "distribution": f"Beta({0.5 + y}, {0.5 + n - y})", "median": float(leaf.median()),
                "q025": float(leaf.ppf(0.025)), "q975": float(leaf.ppf(0.975)),
                "note": "this context's data alone" + (" (single study)" if level == "C" else " (arms pooled, ignores heterogeneity)"),
            },
            "parent_contribution": {
                "share_of_precision_from_parent": float(fit.parent_weight[fit.tree.index[node]]),
                "direct_studies": len(direct), "borrowed_parent_studies": len(parent_studies), "chain": chain,
                "note": "share of the node's posterior precision (posterior-mean over tau draws) supplied by its parent "
                        "rather than its own data; 0 means own data dominate, 1 means fully borrowed",
            },
            "shrinkage": {"raw_estimate": y / n if n else None, "leaf_only_median": float(leaf.median()),
                          "population_median": float(np.median(pop)),
                          "standardised_shift": float((special.logit(np.median(pop)) - special.logit(leaf.median()))
                                                      / math.sqrt(1 / (y + 0.5) + 1 / (n - y + 0.5)))},
            "heterogeneity": {"tau_by_level": taus, "tau_scale": "logit", "source": "estimated across the target hierarchy"},
            "diagnostics": {"tau_importance_ess": fit.ess, "ep_iterations": fit.ep_iterations,
                            "ep_final_change": fit.ep_final_change},
            "likelihood": "exact binomial at the arm level (expectation propagation, quadrature tilted moments)",
        }
        record["parameter_id"] = hashlib.sha1(json.dumps([group, target, record["context"]], sort_keys=True, default=str).encode()).hexdigest()[:16]
        record["draws"] = {"population": pop.astype("float32"), "future_study": future.astype("float32")}
        record["source_observations"] = [r["obs_id"] for r in recs]
        out.append(record)
    return out


def internal_nodes(group: str, target: dict, fit, records: list[dict], max_level: str | None = None) -> list[dict]:
    """Posterior draws of every internal node up to the parameter level, for protocol retrieval."""
    rule = RULES["groups"][group]
    levels = rule["levels"]
    stop = levels.index(max_level or rule["parameter_level"]) + 1
    under = studies_by_prefix(records, levels, stop)
    rows = []
    for key, i in fit.tree.index.items():
        if len(key) > stop:
            continue
        rows.append({"path": list(key), "level": levels[len(key) - 1], "studies": len(under[key]),
                     "draws": fit.node_draws[i].astype("float32"),
                     "share_of_precision_from_parent": float(fit.parent_weight[i])})
    return rows


# ----------------------------------------------------------------------------- calibration


def probability_range(p: float) -> str:
    return "rare_<0.05" if p < 0.05 else "low_0.05-0.20" if p < 0.2 else "medium_0.20-0.80" if p <= 0.8 else "high_>0.80"


def _binomial_scores(theta: np.ndarray, y: int, n: int, rng: np.random.Generator) -> dict:
    p = special.expit(theta)
    rep = rng.binomial(n, p) / n
    return {**scores(rep, y / n),
            "log_predictive_density": float(special.logsumexp(stats.binom.logpmf(y, n, p)) - math.log(p.size)),
            "brier": float((y / n) * (1 - p.mean()) ** 2 + (1 - y / n) * p.mean() ** 2)}


def loo_one(args: tuple) -> dict | None:
    """Hold out one study; predict one of its arms from the rest with every model variant.

    Variants: Milestone 2 (Gaussian approximation to the logit), Milestone 3 exact binomial with
    normal, Student-t(7) and Student-t(4) new-study deviations, a global pooled rate and, where
    the context has other studies, a leaf-only beta-binomial."""
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
    leaf_studies = {r["study"] for r in rest if tuple(r[lv] for lv in levels[:depth]) == path[:depth]}
    out = {"group": group, "target": json.dumps(spec["target"], default=str), "held_out_study": held_study,
           "y": y, "n": n, "observed_rate": y / n,
           "borrowing_depth": levels[known - 1] if known else "root",
           "level": "A" if len(leaf_studies) >= 2 else "B" if len(leaf_studies) == 1 else "C",
           "tau_ess": fit.ess}
    models = {}
    pit_rng = np.random.default_rng(seed + 1)  # separate stream: interval scores stay reproducible
    pits = {}
    for tail, nu in TAILS.items():
        theta = predictive(fit, path, rng, nu)
        models[f"m3_{tail}"] = _binomial_scores(theta, y, n, rng)
        pits[f"m3_{tail}"] = randomized_pit(special.expit(theta), y, n, pit_rng)
    out["predicted_median"] = float(np.median(special.expit(predictive(fit, path, rng))))
    out["probability_range"] = probability_range(out["predicted_median"])
    # Milestone 2 model on the same held-out arm: Gaussian leaf approximation, its own levels.
    v2_rule = borrow2.RULES["groups"][group]
    v2_rest = []
    for r in rest:
        ly, s2 = borrow2._logit_obs(int(r["count"]), int(r["n"]))
        v2_rest.append({**r, "y": ly, "s2": s2})
    fit2 = fit_gaussian(v2_rest, v2_rule["levels"], v2_rule["tau_prior_scale"], v2_rule["root_sd"], samples=400, draws=400, seed=seed)
    theta2 = predictive_gaussian(fit2, tuple(target_arm[lv] for lv in v2_rule["levels"]), rng)
    models["m2_gaussian_logit"] = _binomial_scores(theta2, y, n, rng)
    pits["m2_gaussian_logit"] = randomized_pit(special.expit(theta2), y, n, pit_rng)
    pooled = sum(r["count"] for r in rest) / sum(r["n"] for r in rest)
    models["global_pooled_rate"] = scores(rng.binomial(n, np.full(1000, pooled)) / n, y / n)
    pits["global_pooled_rate"] = randomized_pit(np.array([pooled]), y, n, pit_rng)
    leaf_rest = [r for r in rest if r["study"] in leaf_studies and tuple(r[lv] for lv in levels[:depth]) == path[:depth]]
    if leaf_rest:
        bb = BetaBinomial().fit(np.array([r["count"] for r in leaf_rest]), np.array([r["n"] for r in leaf_rest]))
        models["leaf_only_beta_binomial"] = scores(rng.binomial(n, bb.draws["p_new_study"]) / n, y / n)
        pits["leaf_only_beta_binomial"] = randomized_pit(bb.draws["p_new_study"], y, n, pit_rng)
    out["models"] = models
    out["pit"] = pits
    return out


def randomized_pit(p: np.ndarray, y: int, n: int, rng: np.random.Generator) -> float:
    """Randomized PIT of a count under a mixture of binomials: uniform when calibrated."""
    upper = float(np.mean(stats.binom.cdf(y, n, p)))
    lower = float(np.mean(stats.binom.cdf(y - 1, n, p))) if y > 0 else 0.0
    return lower + rng.uniform() * (upper - lower)


def summarise_pit(items: list[dict], model: str, by: str | None = None) -> dict:
    """Central-interval coverage from randomized PIT (exact for discrete outcomes) and PIT shape."""
    def block(sel: list[dict]) -> dict:
        u = np.array([i["pit"][model] for i in sel if model in i.get("pit", {})])
        if not u.size:
            return {}
        return {"held_out": int(u.size), "coverage_95": float(np.mean((u >= 0.025) & (u <= 0.975))),
                "coverage_80": float(np.mean((u >= 0.1) & (u <= 0.9))), "coverage_50": float(np.mean((u >= 0.25) & (u <= 0.75))),
                "pit_mean": float(u.mean()), "pit_sd": float(u.std()),
                "pit_histogram_deciles": [round(float(h), 3) for h in np.histogram(u, bins=10, range=(0, 1))[0] / u.size]}
    if by is None:
        return block(items)
    return {value: block([i for i in items if str(i.get(by)) == value]) for value in sorted({str(i.get(by)) for i in items})}


def summarise(items: list[dict], model: str, by: str | None = None) -> dict:
    def block(sel: list[dict]) -> dict:
        m = [i["models"][model] for i in sel if model in i["models"]]
        if not m:
            return {}
        res = {"held_out": len(m)}
        for key in ("covered_95", "covered_80", "covered_50"):
            res[key.replace("covered", "coverage")] = float(np.mean([x[key] for x in m]))
        res["median_width_95"] = float(np.median([x["width_95"] for x in m]))
        res["median_width_50"] = float(np.median([x["width_50"] for x in m]))
        res["mean_crps"] = float(np.mean([x["crps"] for x in m]))
        res["mean_abs_error"] = float(np.mean([x["abs_error"] for x in m]))
        if all("log_predictive_density" in x for x in m):
            res["mean_log_predictive_density"] = float(np.mean([x["log_predictive_density"] for x in m]))
            res["mean_brier"] = float(np.mean([x["brier"] for x in m]))
        return res
    if by is None:
        return block(items)
    return {value: block([i for i in items if str(i.get(by)) == value]) for value in sorted({str(i.get(by)) for i in items})}
