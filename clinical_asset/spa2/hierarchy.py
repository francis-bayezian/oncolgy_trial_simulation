"""Nested Gaussian hierarchy with one heterogeneity parameter per level.

Model (analysis scale: logit for proportions, identity for means, log for ratios):

    theta_root ~ N(0, root_sd^2)
    theta_child ~ N(theta_parent, tau_level(child)^2)      for every level of the tree
    y_obs ~ N(theta_leaf, s_obs^2)                           observation likelihood

Given the tau vector the posterior of every node is Gaussian and is computed exactly by an
upward pass (messages) and a downward pass (sampling). The tau vector gets a posterior by
importance sampling from its half-normal priors, weighted by the exact marginal likelihood.
Borrowing is therefore learned: a level whose tau is large shares little, a level with tau near
zero shares a lot, and strong leaf evidence dominates its parents through the likelihood.
"""

from dataclasses import dataclass, field

import numpy as np

LOG2PI = np.log(2 * np.pi)


@dataclass
class Node:
    key: tuple
    level: int
    children: dict = field(default_factory=dict)
    obs: list = field(default_factory=list)  # (y, s2, obs_id)
    # filled by passes (arrays over tau samples)
    m: np.ndarray | None = None
    v: np.ndarray | None = None


def build_tree(records: list[dict], levels: list[str]) -> Node:
    """records: dicts with the level fields, 'y', 's2', 'obs_id'. The last level is the leaf unit."""
    root = Node((), -1)
    for r in records:
        node = root
        for depth, name in enumerate(levels):
            key = node.key + (r[name],)
            node = node.children.setdefault(key, Node(key, depth))
        node.obs.append((r["y"], r["s2"], r["obs_id"]))
    return root


def _upward(node: Node, taus: np.ndarray, root_sd: float) -> np.ndarray:
    """Sets node.m, node.v (likelihood message for theta_node); returns log normaliser (K,)."""
    k = taus.shape[0]
    precision = np.zeros(k)
    weighted = np.zeros(k)
    logz = np.zeros(k)
    items = []
    for y, s2, _ in node.obs:
        items.append((np.full(k, y), np.full(k, s2)))
    for child in node.children.values():
        logz += _upward(child, taus, root_sd)
        # message about the parent: child's message widened by the child's level tau
        items.append((child.m, child.v + taus[:, child.level] ** 2))
    # Product of Gaussian factors in theta: accumulate normaliser of the product.
    for mean, var in items:
        if precision.any():
            # combining N(theta; a, A) and N(theta; b, B) gives N(a; b, A+B) * N(theta; c, C)
            a = weighted / precision
            big_a = 1 / precision
            logz += -0.5 * (LOG2PI + np.log(big_a + var) + (a - mean) ** 2 / (big_a + var))
        precision = precision + 1 / var
        weighted = weighted + mean / var
    node.v = 1 / precision
    node.m = weighted / precision
    return logz


def log_marginal(root: Node, taus: np.ndarray, root_sd: float) -> np.ndarray:
    logz = np.zeros(taus.shape[0])
    for child in root.children.values():
        logz += _upward(child, taus, root_sd)
    # root prior N(0, root_sd^2) combined with the children's messages about theta_root
    precision = np.full(taus.shape[0], 1 / root_sd**2)
    weighted = np.zeros(taus.shape[0])
    for child in root.children.values():
        var = child.v + taus[:, child.level] ** 2
        a, big_a = weighted / precision, 1 / precision
        logz += -0.5 * (LOG2PI + np.log(big_a + var) + (a - child.m) ** 2 / (big_a + var))
        precision += 1 / var
        weighted += child.m / var
    root.v, root.m = 1 / precision, weighted / precision
    return logz


def _downward(node: Node, parent_draw: np.ndarray, taus: np.ndarray, rng: np.random.Generator, out: dict) -> None:
    tau2 = taus[:, node.level] ** 2
    # posterior of theta_node | theta_parent, data below = N(parent, tau2) x message N(m, v)
    precision = 1 / tau2 + 1 / node.v
    mean = (parent_draw / tau2 + node.m / node.v) / precision
    draw = rng.normal(mean, 1 / np.sqrt(precision))
    out[node.key] = draw
    for child in node.children.values():
        _downward(child, draw, taus, rng, out)


@dataclass
class HierarchyFit:
    levels: list[str]
    tau_draws: np.ndarray            # (D, L)
    node_draws: dict                 # key tuple -> (D,)
    root_draws: np.ndarray
    ess: float


def fit_hierarchy(
    records: list[dict], levels: list[str], tau_scales: list[float], root_sd: float,
    samples: int = 600, draws: int = 400, seed: int = 20260926,
) -> HierarchyFit:
    rng = np.random.default_rng(seed)
    root = build_tree(records, levels)
    scales = np.array(tau_scales, dtype=float)

    def log_prior(t: np.ndarray) -> np.ndarray:  # independent half-normal priors
        return (np.log(2) - 0.5 * np.log(2 * np.pi) - np.log(scales) - 0.5 * (t / scales) ** 2).sum(1)

    # Adaptive importance sampling for the tau vector. Round 0 samples the priors; later rounds
    # use a log-normal proposal fitted to the weighted samples (inflated), with exact weights
    # likelihood x prior / proposal. With a lot of data the posterior is far narrower than the
    # prior, so sampling the prior alone would leave very few effective draws.
    taus = np.maximum(np.abs(rng.normal(0, 1, (samples, len(levels)))) * scales[None, :], 1e-4)
    logw = log_marginal(root, taus, root_sd)
    for _ in range(4):
        w = np.exp(logw - logw.max())
        w /= w.sum()
        if 1 / np.sum(w**2) >= 0.25 * samples:
            break
        log_t = np.log(taus)
        mean = (w[:, None] * log_t).sum(0)
        sd = np.sqrt((w[:, None] * (log_t - mean) ** 2).sum(0))
        sd = np.maximum(1.5 * sd, 0.05)
        log_new = rng.normal(mean, sd, (samples, len(levels)))
        taus = np.maximum(np.exp(log_new), 1e-4)
        log_q = (-0.5 * np.log(2 * np.pi) - np.log(sd) - 0.5 * ((np.log(taus) - mean) / sd) ** 2 - np.log(taus)).sum(1)
        logw = log_marginal(root, taus, root_sd) + log_prior(taus) - log_q
    w = np.exp(logw - logw.max())
    w /= w.sum()
    ess = float(1 / np.sum(w**2))
    index = rng.choice(samples, size=draws, p=w)
    chosen = taus[index]
    log_marginal(root, chosen, root_sd)  # recompute messages for the chosen tau draws
    root_draws = rng.normal(root.m, np.sqrt(root.v))
    out: dict = {}
    for child in root.children.values():
        _downward(child, root_draws, chosen, rng, out)
    return HierarchyFit(levels, chosen, out, root_draws, ess)


def predictive(fit: HierarchyFit, path: tuple, rng: np.random.Generator) -> np.ndarray:
    """Draws for a NEW unit below the deepest existing ancestor on `path`: walk down from the
    deepest known node adding the level taus for every missing level."""
    depth = len(path)
    known = None
    for d in range(depth, 0, -1):
        if path[:d] in fit.node_draws:
            known = d
            break
    base = fit.root_draws if known is None else fit.node_draws[path[:known]]
    start = 0 if known is None else known
    draw = base.copy()
    for level in range(start, depth):
        draw = rng.normal(draw, fit.tau_draws[:, level])
    return draw
