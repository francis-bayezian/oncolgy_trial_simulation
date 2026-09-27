"""Milestone 3A: nested hierarchy with the exact binomial likelihood at the arm level.

Model (logit scale):

    theta_root ~ N(0, root_sd^2)
    theta_child ~ N(theta_parent, tau_level(child)^2)       every level of the tree
    y_arm ~ Binomial(n_arm, expit(theta_arm))                exact leaf likelihood

Milestone 2 replaced the binomial by a Gaussian on the continuity-corrected empirical logit,
which is poor for rare or near-certain events and small arms. Here each binomial leaf is
handled by expectation propagation (EP): the tilted moments of Binomial x cavity are computed
by adaptive Gauss-Hermite quadrature around the tilted mode, so every leaf update uses the
exact binomial likelihood; the Gaussian tree is then solved exactly given the site
approximations. The heterogeneity vector tau gets its posterior by adaptive importance
sampling weighted with the EP marginal likelihood. For log-concave leaves (the binomial) EP is
known to be very accurate; tests compare it against brute-force numerical integration.

Everything is vectorised over nodes (per depth) and over tau samples.
"""

from dataclasses import dataclass

import numpy as np
from scipy import special

LOG2PI = float(np.log(2 * np.pi))
GH_X, GH_W = np.polynomial.hermite.hermgauss(12)
LOG_GH_W = np.log(GH_W)


@dataclass
class FlatTree:
    levels: list[str]
    keys: list[tuple]            # node key per index
    parent: np.ndarray           # parent index, -1 for children of the root
    level: np.ndarray            # level index per node
    by_depth: list[np.ndarray]   # node indices per level, shallow to deep
    leaf: np.ndarray             # node index of each observation's leaf
    y: np.ndarray                # successes per observation
    n: np.ndarray                # trials per observation
    obs_ids: list
    index: dict                  # key -> node index


def build_flat_tree(records: list[dict], levels: list[str]) -> FlatTree:
    """records need the level fields plus 'count', 'n', 'obs_id'; one record per leaf (arm)."""
    index: dict[tuple, int] = {}
    keys, parent, level = [], [], []
    leaf = []
    for r in records:
        key: tuple = ()
        p = -1
        for depth, name in enumerate(levels):
            key = key + (r[name],)
            if key not in index:
                index[key] = len(keys)
                keys.append(key)
                parent.append(p)
                level.append(depth)
            p = index[key]
        leaf.append(p)
    if len(set(leaf)) != len(leaf):
        raise ValueError("each leaf node must carry exactly one binomial observation")
    level_arr = np.array(level)
    return FlatTree(levels, keys, np.array(parent), level_arr,
                    [np.flatnonzero(level_arr == d) for d in range(len(levels))], np.array(leaf),
                    np.array([r["count"] for r in records], float), np.array([r["n"] for r in records], float),
                    [r["obs_id"] for r in records], index)


def _combine_logz(prec, weighted, sq, logdet, count):
    """log normaliser of a product of `count` Gaussian factors N(theta; a_j, A_j), given
    prec = sum 1/A_j, weighted = sum a_j/A_j, sq = sum a_j^2/A_j, logdet = sum log A_j."""
    c_var = 1 / prec
    return 0.5 * (LOG2PI + np.log(c_var)) - 0.5 * (count * LOG2PI + logdet) - 0.5 * (sq - weighted**2 * c_var)


def gaussian_pass(tree: FlatTree, taus: np.ndarray, site_mean: np.ndarray, site_var: np.ndarray, root_sd: float,
                  marginals: bool = True) -> dict:
    """Exact Gaussian tree with pseudo-observations (site_mean, site_var) at the leaves.

    taus: (K, L). site arrays: (n_obs, K). Returns upward messages m, v (M, K), the log marginal
    likelihood (K,), and when requested posterior marginals and the message from above
    (the cavity) for every node."""
    m_nodes, k = len(tree.keys), taus.shape[0]
    tau2 = taus[:, tree.level].T ** 2  # (M, K)
    prec = np.zeros((m_nodes, k))
    weighted = np.zeros((m_nodes, k))
    sq = np.zeros((m_nodes, k))
    logdet = np.zeros((m_nodes, k))
    count = np.zeros((m_nodes, 1))
    np.add.at(prec, tree.leaf, 1 / site_var)
    np.add.at(weighted, tree.leaf, site_mean / site_var)
    np.add.at(sq, tree.leaf, site_mean**2 / site_var)
    np.add.at(logdet, tree.leaf, np.log(site_var))
    np.add.at(count, tree.leaf, 1)
    m = np.zeros((m_nodes, k))
    v = np.zeros((m_nodes, k))
    logz = np.zeros(k)
    r_prec, r_w, r_sq, r_ld, r_cnt = np.full(k, 1 / root_sd**2), np.zeros(k), np.zeros(k), np.full(k, np.log(root_sd**2)), 1.0
    for depth in range(len(tree.levels) - 1, -1, -1):
        idx = tree.by_depth[depth]
        logz += _combine_logz(prec[idx], weighted[idx], sq[idx], logdet[idx], count[idx]).sum(0)
        v[idx] = 1 / prec[idx]
        m[idx] = weighted[idx] * v[idx]
        a_var = v[idx] + tau2[idx]
        par = tree.parent[idx]
        top = par < 0
        if top.any():
            sel, av = idx[top], a_var[top]
            r_prec = r_prec + (1 / av).sum(0)
            r_w = r_w + (m[sel] / av).sum(0)
            r_sq = r_sq + (m[sel] ** 2 / av).sum(0)
            r_ld = r_ld + np.log(av).sum(0)
            r_cnt = r_cnt + int(top.sum())
        if (~top).any():
            sel, av, pp = idx[~top], a_var[~top], par[~top]
            np.add.at(prec, pp, 1 / av)
            np.add.at(weighted, pp, m[sel] / av)
            np.add.at(sq, pp, m[sel] ** 2 / av)
            np.add.at(logdet, pp, np.log(av))
            np.add.at(count, pp, 1)
    # Root: product of the prior and the children messages; integrating theta_root.
    logz += _combine_logz(r_prec, r_w, r_sq, r_ld, r_cnt)
    out = {"m": m, "v": v, "logz": logz, "root_mean": r_w / r_prec, "root_var": 1 / r_prec}
    if not marginals:
        return out
    post_mean = np.zeros((m_nodes, k))
    post_var = np.zeros((m_nodes, k))
    above_mean = np.zeros((m_nodes, k))
    above_var = np.zeros((m_nodes, k))
    for depth in range(len(tree.levels)):
        idx = tree.by_depth[depth]
        par = tree.parent[idx]
        a_var = v[idx] + tau2[idx]
        top = (par < 0)[:, None]
        p_mean = np.where(top, out["root_mean"][None, :], post_mean[np.maximum(par, 0)])
        p_var = np.where(top, out["root_var"][None, :], post_var[np.maximum(par, 0)])
        # remove this child's own contribution from the parent posterior, then widen by its tau
        c_prec = np.maximum(1 / p_var - 1 / a_var, 1e-12)
        c_mean = (p_mean / p_var - m[idx] / a_var) / c_prec
        above_mean[idx] = c_mean
        above_var[idx] = 1 / c_prec + tau2[idx]
        pr = 1 / above_var[idx] + 1 / v[idx]
        post_var[idx] = 1 / pr
        post_mean[idx] = (above_mean[idx] / above_var[idx] + m[idx] / v[idx]) / pr
    out.update(post_mean=post_mean, post_var=post_var, above_mean=above_mean, above_var=above_var)
    return out


def tilted_moments(y, n, mu: np.ndarray, var: np.ndarray, x0: np.ndarray | None = None):
    """Moments of Binomial(y | n, expit(theta)) x N(theta; mu, var): log Z, mean, variance.

    Adaptive Gauss-Hermite quadrature centred at the tilted mode (Newton) with the Laplace scale,
    accurate for sharp likelihoods (large n) and flat ones alike."""
    y = np.broadcast_to(y, mu.shape)
    n = np.broadcast_to(n, mu.shape)
    x = mu.copy() if x0 is None else x0.copy()
    for _ in range(40):
        p = special.expit(x)
        grad = y - n * p - (x - mu) / var
        hess = -n * p * (1 - p) - 1 / var
        step = np.clip(grad / hess, -2, 2)
        x = x - step
        if np.max(np.abs(step)) < 1e-8:
            break
    p = special.expit(x)
    s = 1 / np.sqrt(n * p * (1 - p) + 1 / var)
    nodes = x[..., None] + np.sqrt(2) * s[..., None] * GH_X
    le = special.log_expit(nodes)
    log_f = (y[..., None] * le + (n - y)[..., None] * (le - nodes)
             - 0.5 * (nodes - mu[..., None]) ** 2 / var[..., None] - 0.5 * np.log(2 * np.pi * var[..., None]))
    log_terms = log_f + LOG_GH_W + GH_X**2 + np.log(np.sqrt(2) * s[..., None])
    log_z = special.logsumexp(log_terms, axis=-1)
    w = np.exp(log_terms - log_z[..., None])
    mean = (w * nodes).sum(-1)
    variance = np.maximum((w * (nodes - mean[..., None]) ** 2).sum(-1), 1e-12)
    log_binom = special.gammaln(n + 1) - special.gammaln(y + 1) - special.gammaln(n - y + 1)
    return log_z + log_binom, mean, variance


def laplace_sites(tree: FlatTree, taus: np.ndarray, root_sd: float, iterations: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Gaussian sites of the Laplace approximation (Newton / IRLS on the whole tree): the
    binomial log-likelihood is expanded at the current posterior mode of every leaf and the
    Gaussian tree is re-solved exactly. Converges quadratically and gives EP a starting point
    near its fixed point."""
    k = taus.shape[0]
    y, n = tree.y[:, None], tree.n[:, None]
    x = np.repeat(np.log((y + 0.5) / (n - y + 0.5)), k, axis=1)
    site_mean = site_var = x
    for _ in range(iterations):
        p = special.expit(x)
        w = np.maximum(n * p * (1 - p), 1e-10)
        site_mean, site_var = x + (y - n * p) / w, 1 / w
        g = gaussian_pass(tree, taus, site_mean, site_var, root_sd)
        new = g["post_mean"][tree.leaf]
        step = np.clip(new - x, -3, 3)
        x = x + step
        if float(np.max(np.abs(step))) < 1e-5:
            break
    return site_mean, site_var


def ep_fit(tree: FlatTree, taus: np.ndarray, root_sd: float, iterations: int = 40, damping: float = 0.7,
           tol: float = 5e-3, logz_tol: float = 1e-3) -> dict:
    """Parallel EP over all leaves, per tau sample (column), started from the Laplace sites.

    A column has converged when its tilted moments move by less than `tol` posterior SDs and its
    EP log marginal likelihood by less than `logz_tol` between sweeps; converged columns are
    frozen so slow columns do not hold up the rest. Returns the site parameters, the EP log
    marginal likelihood per column and the Gaussian pass at the final sites."""
    k = taus.shape[0]
    y, n = tree.y[:, None], tree.n[:, None]
    site_mean, site_var = laplace_sites(tree, taus, root_sd)
    keys = ("m", "v", "above_mean", "above_var", "post_mean", "post_var")
    out = {key: np.zeros((len(tree.keys), k)) for key in keys}
    out.update(logz=np.zeros(k), root_mean=np.zeros(k), root_var=np.zeros(k))
    log_marginal = np.zeros(k)
    iters = np.zeros(k, int)
    change_final = np.zeros(k)
    active = np.arange(k)
    mode = None
    last = np.full(k, np.inf)
    for it in range(iterations + 1):
        sm, sv, t = site_mean[:, active], site_var[:, active], taus[active]
        g = gaussian_pass(tree, t, sm, sv, root_sd)
        cav_m, cav_v = g["above_mean"][tree.leaf], g["above_var"][tree.leaf]
        log_zhat, t_mean, t_var = tilted_moments(y, n, cav_m, cav_v, None if mode is None else mode[:, active])
        tot = sv + cav_v
        # log Z_EP = log Z_gauss(sites) + sum_i [log Zhat_i - log N(site_mean_i; cav_m_i, site_var_i + cav_v_i)]
        lz = g["logz"] + (log_zhat + 0.5 * (LOG2PI + np.log(tot)) + 0.5 * (sm - cav_m) ** 2 / tot).sum(0)
        change = np.full(active.size, np.inf) if mode is None else np.max(np.abs(t_mean - mode[:, active]) / np.sqrt(t_var), axis=0)
        done = (change < tol) & (np.abs(lz - last[active]) < logz_tol)
        if it == iterations:
            done[:] = True
        if done.any():
            cols = active[done]
            for key in keys:
                out[key][:, cols] = g[key][:, done]
            out["logz"][cols], out["root_mean"][cols], out["root_var"][cols] = g["logz"][done], g["root_mean"][done], g["root_var"][done]
            log_marginal[cols] = lz[done]
            iters[cols] = it
            change_final[cols] = change[done]
        if mode is None:
            mode = np.zeros_like(site_mean)
        mode[:, active] = t_mean
        last[active] = lz
        keep = ~done
        if not keep.any():
            break
        new_prec = np.maximum(1 / t_var[:, keep] - 1 / cav_v[:, keep], 1e-10)  # non-negative for log-concave sites
        new_wm = t_mean[:, keep] / t_var[:, keep] - cav_m[:, keep] / cav_v[:, keep]
        prec = (1 - damping) / sv[:, keep] + damping * new_prec
        wm = (1 - damping) * sm[:, keep] / sv[:, keep] + damping * new_wm
        cols = active[keep]
        site_mean[:, cols], site_var[:, cols] = wm / prec, 1 / prec
        active = cols
    return {"site_mean": site_mean, "site_var": site_var, "log_marginal": log_marginal, "gauss": out,
            "iterations": int(iters.max()), "final_change": float(change_final.max()), "column_iterations": iters}


@dataclass
class BinomialFit:
    levels: list[str]
    tree: FlatTree
    tau_draws: np.ndarray       # (D, L)
    node_draws: np.ndarray      # (M, D) posterior draws of every node
    root_draws: np.ndarray      # (D,)
    ess: float
    ep_iterations: int
    ep_final_change: float
    parent_weight: np.ndarray   # (M,) share of the node's posterior precision that comes from above


def _log_half_normal(t: np.ndarray, scales: np.ndarray) -> np.ndarray:
    return (np.log(2) - 0.5 * LOG2PI - np.log(scales) - 0.5 * (t / scales) ** 2).sum(1)


def fit_binomial_hierarchy(records: list[dict], levels: list[str], tau_scales: list[float], root_sd: float,
                           samples: int = 300, draws: int = 400, seed: int = 20260926, chunk: int = 100) -> BinomialFit:
    """Posterior of the heterogeneity vector by importance sampling on u = log tau.

    1. Mode of log p(u | y) = log Z_EP(exp u) + log prior(exp u) + sum(u), where Z_EP is the
       exact-binomial EP marginal likelihood (started from the cheap Gaussian-leaf solution;
       central-difference gradients evaluated in one vectorised EP call).
    2. Proposal: the posterior in u is skewed (steep towards large tau, a long tail towards
       small tau), so each coordinate gets a split-normal whose left and right scales come from
       exact slices of log p(u | y); coordinates are coupled by the Laplace correlation through a
       Gaussian copula, mixed with a wider defensive component.
    3. Importance weights use the exact EP marginal likelihood, so the proposal only affects
       efficiency. Node draws reuse the EP state of the resampled tau values."""
    from scipy import optimize

    rng = np.random.default_rng(seed)
    tree = build_flat_tree(records, levels)
    scales = np.array(tau_scales, float)
    n_lev = len(levels)
    y, n = tree.y[:, None], tree.n[:, None]
    approx_var = 1 / (y + 0.5) + 1 / (n - y + 0.5)
    approx_mean = np.log((y + 0.5) / (n - y + 0.5))
    medium = {"tol": 1e-3, "logz_tol": 1e-4, "iterations": 60}

    def log_post(u: np.ndarray, mode: str = "ep", keep: bool = False):
        t = np.exp(u)
        if mode == "gaussian":
            k = t.shape[0]
            lm = gaussian_pass(tree, t, np.repeat(approx_mean, k, 1), np.repeat(approx_var, k, 1), root_sd, marginals=False)["logz"]
            return lm + _log_half_normal(t, scales) + u.sum(1)
        out, states, iters = np.empty(t.shape[0]), [], []
        for start in range(0, t.shape[0], chunk):
            ep = ep_fit(tree, t[start:start + chunk], root_sd, **(medium if mode == "medium" else {"tol": 5e-3, "logz_tol": 1e-3}))
            out[start:start + chunk] = ep["log_marginal"]
            iters.append(ep["iterations"])
            if keep:
                states.append({k: ep["gauss"][k] for k in ("m", "v", "root_mean", "root_var", "above_var")})
        lp = out + _log_half_normal(t, scales) + u.sum(1)
        return (lp, states, iters) if keep else lp

    h = 0.1
    eye = np.eye(n_lev)

    def value_and_grad(u: np.ndarray, mode: str):
        pts = np.vstack([u, u + h * eye, u - h * eye])
        f = log_post(pts, mode)
        return -f[0], -(f[1:1 + n_lev] - f[1 + n_lev:]) / (2 * h)

    bounds = [(-7, 3)] * n_lev
    res = optimize.minimize(value_and_grad, np.log(0.5 * scales), args=("gaussian",), jac=True, method="L-BFGS-B",
                            bounds=bounds, options={"maxiter": 200})
    res = optimize.minimize(value_and_grad, res.x, args=("medium",), jac=True, method="L-BFGS-B", bounds=bounds,
                            options={"maxiter": 40, "ftol": 1e-7})
    mode = res.x
    # Laplace curvature (second differences) and exact slices, one vectorised call.
    pairs = [(i, j) for i in range(n_lev) for j in range(i + 1, n_lev)]
    pts = [mode] + [mode + h * eye[i] for i in range(n_lev)] + [mode - h * eye[i] for i in range(n_lev)] + \
          [mode + h * eye[i] + h * eye[j] for i, j in pairs]
    f = log_post(np.array(pts), "medium")
    f0, fp, fm = f[0], f[1:1 + n_lev], f[1 + n_lev:1 + 2 * n_lev]
    hess = np.diag((fp - 2 * f0 + fm) / h**2)
    for k, (i, j) in enumerate(pairs):
        hess[i, j] = hess[j, i] = (f[1 + 2 * n_lev + k] - fp[i] - fp[j] + f0) / h**2
    w_eig, v_eig = np.linalg.eigh(-(hess + hess.T) / 2)
    cov = (v_eig * (1 / np.clip(w_eig, 1 / 4.0, 1e6))) @ v_eig.T
    sd = np.sqrt(np.diag(cov))
    corr = cov / np.outer(sd, sd)
    step = np.clip(sd, 0.05, 1.0)
    sl = log_post(np.vstack([mode - step * eye, mode + step * eye]), "medium")
    drop_left, drop_right = np.maximum(f0 - sl[:n_lev], 1e-3), np.maximum(f0 - sl[n_lev:], 1e-3)
    s_left = np.clip(step / np.sqrt(2 * drop_left), 0.02, 3.0) * 1.2
    s_right = np.clip(step / np.sqrt(2 * drop_right), 0.02, 3.0) * 1.2
    chol = np.linalg.cholesky(corr + 1e-9 * eye)
    corr_inv = np.linalg.inv(corr + 1e-9 * eye)
    _, logdet = np.linalg.slogdet(corr + 1e-9 * eye)

    nu_t = 4.0  # heavy tails: weakly identified levels have exponential tails towards small tau
    log_c = special.gammaln((nu_t + n_lev) / 2) - special.gammaln(nu_t / 2) - 0.5 * n_lev * np.log(nu_t * np.pi) - 0.5 * logdet

    def log_q_one(u: np.ndarray, widen: float) -> np.ndarray:
        d = u - mode
        s = np.where(d < 0, s_left, s_right) * widen
        z = d / s
        return log_c - 0.5 * (nu_t + n_lev) * np.log1p(np.einsum("ij,jk,ik->i", z, corr_inv, z) / nu_t) - np.log(s).sum(1)

    # Defensive mixture with the prior: for weakly informative data the posterior of tau is
    # close to its prior, which the likelihood-centred component alone covers poorly.
    prior_share = 0.5 if len(records) <= 30 else 0.15

    def draw(count: int) -> np.ndarray:
        z = (rng.standard_normal((count, n_lev)) @ chol.T) / np.sqrt(rng.chisquare(nu_t, count) / nu_t)[:, None]
        widen = np.where(rng.random(count) < 0.15, 2.0, 1.0)[:, None]
        laplace = mode + z * np.where(z < 0, s_left, s_right) * widen
        prior = np.log(np.maximum(np.abs(rng.standard_normal((count, n_lev))) * scales, 1e-300))
        return np.where((rng.random(count) < prior_share)[:, None], prior, laplace)

    def log_q(u: np.ndarray) -> np.ndarray:
        laplace = np.logaddexp(np.log(0.85) + log_q_one(u, 1.0), np.log(0.15) + log_q_one(u, 2.0))
        prior = _log_half_normal(np.exp(u), scales) + u.sum(1)
        return np.logaddexp(np.log(prior_share) + prior, np.log1p(-prior_share) + laplace)

    # Adaptive multiple importance sampling: if the first batch is inefficient, further batches
    # come from multivariate-t proposals moment-matched to the weighted draws, and all batches
    # are weighted against the deterministic mixture of every proposal used (balance heuristic).
    def mvt_logpdf(center: np.ndarray, cov: np.ndarray, nu_m: float = 5.0):
        inv = np.linalg.inv(cov)
        _, ld = np.linalg.slogdet(cov)
        c = special.gammaln((nu_m + n_lev) / 2) - special.gammaln(nu_m / 2) - 0.5 * n_lev * np.log(nu_m * np.pi) - 0.5 * ld
        return lambda x: c - 0.5 * (nu_m + n_lev) * np.log1p(np.einsum("ij,jk,ik->i", x - center, inv, x - center) / nu_m)

    components = [(samples, log_q)]
    u = np.clip(draw(samples), -12, 4)
    all_u, all_lp, states, iters = [], [], [], []
    for _round in range(4):
        lp_b, st_b, it_b = log_post(u, keep=True)
        all_u.append(u)
        all_lp.append(lp_b)
        states.extend(st_b)
        iters.extend(it_b)
        big_u, lp = np.vstack(all_u), np.concatenate(all_lp)
        total = sum(c[0] for c in components)
        log_mix = special.logsumexp([np.log(c[0] / total) + c[1](big_u) for c in components], axis=0)
        logw = lp - log_mix
        w = np.exp(logw - logw.max())
        w /= w.sum()
        ess = float(1 / np.sum(w**2))
        if ess >= max(100.0, 0.2 * samples):
            break
        center = (w[:, None] * big_u).sum(0)
        dev = big_u - center
        cov = (w[:, None, None] * dev[:, :, None] * dev[:, None, :]).sum(0) * 1.5**2 + 1e-3 * eye
        chol_r = np.linalg.cholesky(cov)
        g = np.sqrt(rng.chisquare(5.0, samples) / 5.0)[:, None]
        u = np.clip(center + (rng.standard_normal((samples, n_lev)) @ chol_r.T) / g, -12, 4)
        components.append((samples, mvt_logpdf(center, cov)))
    u = big_u
    pick = rng.choice(u.shape[0], size=draws, p=w)
    chosen = np.exp(u[pick])
    m_all = np.concatenate([s["m"] for s in states], axis=1)[:, pick]
    v_all = np.concatenate([s["v"] for s in states], axis=1)[:, pick]
    above = np.concatenate([s["above_var"] for s in states], axis=1)[:, pick]
    root_mean = np.concatenate([s["root_mean"] for s in states])[pick]
    root_var = np.concatenate([s["root_var"] for s in states])[pick]
    tau2 = chosen[:, tree.level].T ** 2
    root = rng.normal(root_mean, np.sqrt(root_var))
    nd = np.zeros((len(tree.keys), draws))
    for depth in range(n_lev):
        idx = tree.by_depth[depth]
        par = tree.parent[idx]
        parent_draw = np.where((par < 0)[:, None], root[None, :], nd[np.maximum(par, 0)])
        pr = 1 / tau2[idx] + 1 / v_all[idx]
        mu = (parent_draw / tau2[idx] + m_all[idx] / v_all[idx]) / pr
        nd[idx] = rng.normal(mu, 1 / np.sqrt(pr))
    parent_weight = ((1 / above) / (1 / above + 1 / v_all)).mean(1)
    return BinomialFit(levels, tree, chosen, nd, root, ess, int(max(iters)), 5e-3, parent_weight)


def node_draws(fit: BinomialFit, key: tuple) -> np.ndarray:
    return fit.node_draws[fit.tree.index[key]]


def deepest_known(fit, path: tuple) -> int:
    index = fit.tree.index if hasattr(fit, "tree") else fit.node_draws
    for d in range(len(path), 0, -1):
        if path[:d] in index:
            return d
    return 0


def predictive(fit: BinomialFit, path: tuple, rng: np.random.Generator, nu: float | None = None) -> np.ndarray:
    """Draws for a new unit on `path`: start at the deepest existing ancestor and add a deviation
    for every missing level. nu=None uses normal deviations; a finite nu uses Student-t deviations
    with the same scale (heavier tails for surprising new studies)."""
    known = deepest_known(fit, path)
    draw = (fit.root_draws if known == 0 else node_draws(fit, path[:known])).copy()
    for level in range(known, len(path)):
        z = rng.standard_normal(draw.size) if nu is None else rng.standard_t(nu, draw.size)
        draw = draw + fit.tau_draws[:, level] * z
    return draw
