"""Contextual control-arm model with similarity-weighted robust borrowing (L057).

A calibration layer over the immutable evidence assets. For an outcome (any serious adverse event, death) of a target
control arm it separates two questions:
  baseline risk in a trial like this:   logit p0_j = alpha + gamma' Z_j + u_j      (Z: the trial context)
  patient effects on top of it:         logit p_ij = logit p0_j + X_ij' beta       (evidence synthesis, applied in the
                                                                                    patient simulation, not here)
The baseline risk is predicted by a robust mixture prior:
  pi * N(eta + similarity-weighted mean of historical residuals, tau^2(context) + residual variance / ESS)
  + (1 - pi) * N(eta, global residual variance)        (a vague, context-only component)
  eta: the context regression's prediction; residuals u_j: historical arms' observed logits minus their prediction;
  similarity w_j = exp(-sum_f s_f d_f(target, j)) over context features; pi = sigmoid(a + b * best similarity);
  context-specific heterogeneity: log tau^2 = c0 + c1 * best similarity + c2 * (closest arms share the drug classes).
All of s_f, a, b, c0, c1, c2 are learned (not set) on trials outside the target's fold (5-fold over trials), by
maximising the log predictive density of held-out historical control arms (smooth objective, L-BFGS). Similarity bands
are used only to report results. No asset row is changed.
"""

from __future__ import annotations

import math
import sys
import time

import numpy as np
from scipy import optimize, special

FEATURES = ("family", "phase", "classes", "year", "region", "age", "female", "ecog")
FOLDS = 5
BANDS = 3                                  # similarity bands for reporting (tertiles of the best similarity)
QUAD = np.linspace(-4, 4, 33)              # normal quadrature on the logit scale
QW = np.exp(-QUAD ** 2 / 2)
QW /= QW.sum()


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def emp_logit(k, n):
    """Empirical logit and its sampling variance (0.5 added to both cells)."""
    return math.log((k + 0.5) / (n - k + 0.5)), 1 / (k + 0.5) + 1 / (n - k + 0.5)


class Pool:
    """The historical arms' context features as arrays, for vectorised distances to any target."""

    def __init__(self, arms: list[dict], classes: list[str]):
        self.cidx = {c: i for i, c in enumerate(classes)}
        self.fam = np.array([a.get("family") or "" for a in arms], dtype=object)
        self.phase = np.array([a.get("phase") or "" for a in arms], dtype=object)
        self.region = np.array([a.get("region") or "" for a in arms], dtype=object)
        self.C = np.zeros((len(arms), len(classes)), dtype=np.float32)
        for i, a in enumerate(arms):
            for c in a.get("classes") or ():
                if c in self.cidx:
                    self.C[i, self.cidx[c]] = 1.0
        num = lambda k: np.array([a.get(k) if a.get(k) is not None else np.nan for a in arms], dtype=float)  # noqa: E731
        self.year, self.age, self.female, self.ecog = num("year"), num("age"), num("female"), num("ecog1")
        self.ncls = self.C.sum(axis=1)

    def distances(self, t: dict, rows: np.ndarray | None = None) -> np.ndarray:
        """Per-feature distances (rows: arms, columns: FEATURES); a missing value is half-way (0.5)."""
        sel = slice(None) if rows is None else rows
        tv = np.zeros(self.C.shape[1], dtype=np.float32)
        for c in t.get("classes") or ():
            if c in self.cidx:
                tv[self.cidx[c]] = 1.0
        inter = self.C[sel] @ tv
        union = self.ncls[sel] + tv.sum() - inter
        jac = np.where(union > 0, 1 - inter / np.where(union > 0, union, 1), 0.0)

        def diff(arr, v, scale):
            d = np.abs(arr[sel] - v) / scale if v is not None else np.full(len(arr[sel]), np.nan)
            return np.where(np.isnan(d), 0.5, d)

        return np.column_stack([
            np.where((self.fam[sel] == (t.get("family") or "")) & (self.fam[sel] != ""), 0.0, 1.0),
            np.where(self.phase[sel] == (t.get("phase") or ""), 0.0, 1.0), jac,
            diff(self.year, t.get("year"), 10), np.where(self.region[sel] == (t.get("region") or ""), 0.0, 1.0),
            diff(self.age, t.get("age"), 10), diff(self.female, t.get("female"), 1), diff(self.ecog, t.get("ecog1"), 1)])


def borrow(D: np.ndarray, resid: np.ndarray, scales: np.ndarray) -> tuple[float, float, float, float]:
    """Similarity-weighted mean residual, effective sample size, best similarity, and whether the arm with the largest
    weight shares the target's drug classes (1.0) or not (0.0)."""
    w = np.exp(-(D @ scales))
    sw = w.sum()
    if sw <= 0:
        return 0.0, 0.0, 0.0, 0.0
    best = int(np.argmax(w))
    return float(np.sum(w * resid) / sw), float(sw ** 2 / np.sum(w ** 2)), float(w[best]), float(D[best, 2] == 0.0)


def components(eta, var_eta, m, ess, smax, same, theta, sigma2, tau_global2):
    """The mixture's (pi, mean1, var1, mean2, var2), vectorised over targets."""
    nf = len(FEATURES)
    a, b, c0, c1, c2 = theta[nf:nf + 5]
    pi = special.expit(a + b * smax)
    tau2 = np.exp(c0 + c1 * smax + c2 * same)
    return pi, eta + m, var_eta + tau2 + sigma2 / np.maximum(ess, 1.0), eta, var_eta + tau_global2


def log_scores(k, n, comp) -> np.ndarray:
    """Log predictive density of k of n per target under the mixture (normal-logit components by quadrature)."""
    pi, m1, v1, m2, v2 = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in comp), np.asarray(k, dtype=float))[:5]
    lik = 0.0
    for wgt, m, v in ((pi, m1, v1), (1 - pi, m2, v2)):
        x = m[:, None] + np.sqrt(np.maximum(v, 1e-9))[:, None] * QUAD[None, :]
        lp = k[:, None] * -np.logaddexp(0, -x) + (n - k)[:, None] * -np.logaddexp(0, x)   # log p^k (1-p)^(n-k)
        dens = np.exp(lp + special.gammaln(n + 1)[:, None] - special.gammaln(k + 1)[:, None]
                      - special.gammaln(n - k + 1)[:, None]) @ QW
        lik = lik + wgt * dens
    return np.log(np.maximum(lik, 1e-300))


def draws(comp, size: int, rng) -> np.ndarray:
    pi, m1, v1, m2, v2 = (float(np.asarray(x).ravel()[0]) for x in comp)
    pick = rng.random(size) < pi
    x = np.where(pick, rng.normal(m1, math.sqrt(max(v1, 1e-12)), size), rng.normal(m2, math.sqrt(max(v2, 1e-12)), size))
    return special.expit(x)


def learn(targets: list[dict], pool: Pool, pool_resid: np.ndarray, pool_rvar: np.ndarray, pool_trial: np.ndarray,
          tau_global2: float, label: str = "") -> tuple[dict, dict]:
    """s_f, a, b, c0, c1, c2 learned on training targets (historical control arms, each predicted without its own
    trial) by maximising the summed log predictive density."""
    t0 = time.time()
    prep = []
    for t in targets:
        rows = np.flatnonzero(pool_trial != t["nct_id"])
        prep.append((pool.distances(t, rows), pool_resid[rows]))
    k = np.array([t["k"] for t in targets], float)
    n = np.array([t["n"] for t in targets], float)
    eta = np.array([t["eta"] for t in targets])
    sigma2 = float(np.median(pool_rvar))
    nf = len(FEATURES)

    def stats(scales):
        return np.array([borrow(D, r, scales) for D, r in prep]).T          # m, ess, smax, same

    def objective(theta):
        m, ess, smax, same = stats(np.exp(theta[:nf]))
        return -float(log_scores(k, n, components(eta, 0.0, m, ess, smax, same, theta, sigma2, tau_global2)).sum())

    x0 = np.concatenate([np.zeros(nf), [0.0, 1.0, math.log(max(tau_global2, 1e-3)), 0.0, 0.0]])
    bounds = [(-4, 4)] * nf + [(-10, 10), (-50, 50), (-8, 3), (-20, 20), (-5, 5)]
    res = optimize.minimize(objective, x0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 200})
    theta = res.x
    m, ess, smax, same = stats(np.exp(theta[:nf]))
    edges = np.quantile(smax, [i / BANDS for i in range(1, BANDS)])
    params = {"theta": theta, "sigma2": sigma2, "tau_global2": tau_global2, "edges": edges}
    info = {"converged": bool(res.success), "message": str(res.message)[:80], "iterations": int(res.nit),
            "neg_log_score": round(float(res.fun), 2), "start_neg_log_score": round(float(objective(x0)), 2),
            "kernel_scales": dict(zip(FEATURES, np.round(np.exp(theta[:nf]), 3).tolist(), strict=True)),
            "pi": {"a": round(float(theta[nf]), 3), "b": round(float(theta[nf + 1]), 3)},
            "log_tau2": {"c0": round(float(theta[nf + 2]), 3), "c1_similarity": round(float(theta[nf + 3]), 3),
                         "c2_same_classes": round(float(theta[nf + 4]), 3)},
            "band_edges": np.round(edges, 4).tolist(), "seconds": round(time.time() - t0)}
    log(f"learned {label}: {info['neg_log_score']} (start {info['start_neg_log_score']}), converged {info['converged']}, "
        f"{info['seconds']} s")
    return params, info


def predict(params: dict, eta: float, var_eta: float, D: np.ndarray, resid: np.ndarray) -> tuple[tuple, int, float]:
    """The target's mixture components, its similarity band and best similarity."""
    m, ess, smax, same = borrow(D, resid, np.exp(params["theta"][:len(FEATURES)]))
    comp = components(np.array([eta]), var_eta, np.array([m]), np.array([ess]), np.array([smax]), np.array([same]),
                      params["theta"], params["sigma2"], params["tau_global2"])
    return comp, int(np.searchsorted(params["edges"], smax)), smax
