"""Bayesian hierarchical models for aggregate evidence, computed exactly on grids.

Each model has at most two hyperparameters, so the posterior is integrated numerically on a
grid instead of sampled by MCMC: there is no convergence to diagnose, only grid coverage,
which every fit reports (posterior mass on the grid boundary).

* BetaBinomial          y_i ~ BetaBinomial(n_i, m*kappa, (1-m)*kappa)   (proportions)
* NormalRandomEffects   y_i ~ N(theta_i, se_i^2), theta_i ~ N(mu, tau^2)  (means, log HR/OR/RR)
* DirichletMultinomial  counts_i ~ DirMult(n_i, kappa*m)                 (exclusive categories)

Priors are weakly informative and set per model family (never one universal prior).
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import special, stats

RNG_SEED = 20260926
DRAWS = 1000


def _quantiles(x: np.ndarray) -> dict[str, float]:
    q = np.quantile(x, [0.025, 0.5, 0.975])
    return {"mean": float(np.mean(x)), "median": float(q[1]), "q025": float(q[0]), "q975": float(q[2])}


def _sample_grid(log_post: np.ndarray, rng: np.random.Generator, n: int) -> tuple[np.ndarray, float]:
    weights = np.exp(log_post - log_post.max())
    weights /= weights.sum()
    flat = weights.ravel()
    index = rng.choice(flat.size, size=n, p=flat)
    edge = np.zeros_like(weights, dtype=bool)
    edge[0, ...] = edge[-1, ...] = True
    if weights.ndim == 2:
        edge[:, 0] = edge[:, -1] = True
    return index, float(weights[edge].sum())


@dataclass
class Fit:
    family: str
    posterior: dict
    predictive: dict
    heterogeneity: dict
    draws: dict[str, np.ndarray]
    diagnostics: dict = field(default_factory=dict)


class BetaBinomial:
    """Proportions with between-study heterogeneity. Prior: logit(m) ~ N(0, 1.5^2),
    log(kappa) ~ N(log 10, 1.5^2) (kappa = prior sample size of the population distribution)."""

    family = "hierarchical_beta_binomial"

    def fit(self, y: np.ndarray, n: np.ndarray, seed: int = RNG_SEED) -> Fit:
        y, n = np.asarray(y, float), np.asarray(n, float)
        logit_m = np.linspace(-12, 12, 161)
        log_k = np.linspace(np.log(0.01), np.log(1e6), 141)
        LM, LK = np.meshgrid(logit_m, log_k, indexing="ij")
        m, k = special.expit(LM), np.exp(LK)
        a, b = (m * k)[..., None], ((1 - m) * k)[..., None]
        loglik = (special.betaln(y + a, n - y + b) - special.betaln(a, b)).sum(-1)
        log_post = loglik + stats.norm.logpdf(LM, 0, 1.5) + stats.norm.logpdf(LK, np.log(10), 1.5)
        rng = np.random.default_rng(seed)
        index, edge = _sample_grid(log_post, rng, DRAWS)
        i, j = np.unravel_index(index, LM.shape)
        dl, dk = logit_m[1] - logit_m[0], log_k[1] - log_k[0]
        lm = logit_m[i] + rng.uniform(-dl / 2, dl / 2, DRAWS)
        lk = log_k[j] + rng.uniform(-dk / 2, dk / 2, DRAWS)
        mean, kappa = special.expit(lm), np.exp(lk)
        new_study = rng.beta(mean * kappa, (1 - mean) * kappa)
        between_sd = np.sqrt(mean * (1 - mean) / (kappa + 1))
        return Fit(
            self.family,
            posterior=_quantiles(mean),
            predictive=_quantiles(new_study),
            heterogeneity={"kappa": _quantiles(kappa), "between_study_sd": _quantiles(between_sd)},
            draws={"p": mean, "p_new_study": new_study, "kappa": kappa},
            diagnostics={"grid_edge_mass": edge},
        )

    @staticmethod
    def predictive_interval(fit: Fit, n: float, seed: int = RNG_SEED) -> tuple[float, float]:
        """95% interval for an observed proportion y/n in a new study of size n."""
        rng = np.random.default_rng(seed)
        y = rng.binomial(int(n), fit.draws["p_new_study"])
        q = np.quantile(y / n, [0.025, 0.975])
        return float(q[0]), float(q[1])


class NormalRandomEffects:
    """Random-effects meta-analysis on the analysis scale (identity or log).
    Prior: mu ~ N(prior_mean, prior_sd^2), tau ~ HalfNormal(tau_scale)."""

    family = "normal_random_effects"

    def __init__(self, prior_mean: float, prior_sd: float, tau_scale: float, log_scale: bool = False) -> None:
        self.prior_mean, self.prior_sd, self.tau_scale, self.log_scale = prior_mean, prior_sd, tau_scale, log_scale

    def fit(self, y: np.ndarray, se: np.ndarray, seed: int = RNG_SEED) -> Fit:
        y, se = np.asarray(y, float), np.asarray(se, float)
        tau = np.linspace(0, 6 * self.tau_scale, 601)
        v = se[None, :] ** 2 + tau[:, None] ** 2
        # mu | tau is conjugate normal; integrate mu out analytically.
        precision = 1 / self.prior_sd**2 + (1 / v).sum(1)
        post_mean = (self.prior_mean / self.prior_sd**2 + (y[None, :] / v).sum(1)) / precision
        log_marg = (
            -0.5 * np.log(v).sum(1) - 0.5 * np.log(precision) - np.log(self.prior_sd)
            - 0.5 * ((y[None, :] ** 2 / v).sum(1) + self.prior_mean**2 / self.prior_sd**2 - post_mean**2 * precision)
        )
        log_post = log_marg + stats.halfnorm.logpdf(tau, scale=self.tau_scale)
        rng = np.random.default_rng(seed)
        weights = np.exp(log_post - log_post.max())
        weights /= weights.sum()
        index = rng.choice(tau.size, size=DRAWS, p=weights)
        t = np.abs(tau[index] + rng.uniform(-0.5, 0.5, DRAWS) * (tau[1] - tau[0]))
        mu = rng.normal(post_mean[index], 1 / np.sqrt(precision[index]))
        theta_new = rng.normal(mu, t)
        edge = float(weights[-1])
        transform = np.exp if self.log_scale else (lambda x: x)
        return Fit(
            self.family + ("_log" if self.log_scale else ""),
            posterior=_quantiles(transform(mu)),
            predictive=_quantiles(transform(theta_new)),
            heterogeneity={"tau": _quantiles(t)},
            draws={"mu": mu, "theta_new_study": theta_new, "tau": t},
            diagnostics={"grid_edge_mass": edge, "scale": "log" if self.log_scale else "identity"},
        )

    def predictive_interval(self, fit: Fit, se: float, seed: int = RNG_SEED) -> tuple[float, float]:
        rng = np.random.default_rng(seed)
        y = rng.normal(fit.draws["theta_new_study"], se)
        q = np.quantile(y, [0.025, 0.975])
        return float(q[0]), float(q[1])


class DirichletMultinomial:
    """Mutually exclusive categories. Prior: mean composition m ~ Dirichlet(1),
    log(kappa) ~ N(log 20, 1.5^2). Posterior by adaptive self-normalised importance sampling:
    the proposal for m is a Dirichlet matched to the data's effective concentration (moment
    estimate of kappa), the proposal for kappa mixes a data-centred log-normal with the prior.
    Several proposal widths are tried; the fit with the largest effective sample size is kept."""

    family = "hierarchical_dirichlet_multinomial"
    MIN_ESS = 200

    @staticmethod
    def _kappa_moment(counts: np.ndarray) -> float:
        n = counts.sum(1)
        if len(n) < 2:
            return 20.0
        p = counts / n[:, None]
        pooled = counts.sum(0) / n.sum()
        estimates = []
        for c in range(counts.shape[1]):
            base = pooled[c] * (1 - pooled[c])
            v = np.var(p[:, c], ddof=1)
            nbar = float(np.mean(n))
            if base <= 0 or v <= base / nbar:
                estimates.append(1e5)
                continue
            estimates.append((base - v) / max(v - base / nbar, 1e-12))
        return float(np.clip(np.median(estimates), 0.5, 1e5))

    def _attempt(self, counts, rng, samples, concentration, k_hat):
        k_cat = counts.shape[1]
        pooled = (counts.sum(0) + 1) / (counts.sum() + k_cat)
        alpha_q = 1 + concentration * pooled
        m = rng.dirichlet(alpha_q, samples)
        from_data = rng.random(samples) < 0.5
        log_kappa = np.where(from_data, rng.normal(np.log(k_hat), 1.2, samples), rng.normal(np.log(20), 1.5, samples))
        kappa = np.exp(log_kappa)
        log_q_kappa = np.logaddexp(np.log(0.5) + stats.norm.logpdf(log_kappa, np.log(k_hat), 1.2),
                                   np.log(0.5) + stats.norm.logpdf(log_kappa, np.log(20), 1.5))
        log_prior_kappa = stats.norm.logpdf(log_kappa, np.log(20), 1.5)
        alpha = m * kappa[:, None]
        n = counts.sum(1)
        loglik = (
            special.gammaln(kappa)[:, None] - special.gammaln(n[None, :] + kappa[:, None])
            + (special.gammaln(counts[None, :, :] + alpha[:, None, :]) - special.gammaln(alpha[:, None, :])).sum(-1)
        ).sum(1)
        log_m = np.log(np.clip(m, 1e-300, None))
        log_q_m = special.gammaln(alpha_q.sum()) - special.gammaln(alpha_q).sum() + ((alpha_q - 1) * log_m).sum(1)
        log_w = loglik + special.gammaln(k_cat) + log_prior_kappa - log_q_m - log_q_kappa
        log_w = np.where(np.isfinite(log_w), log_w, -np.inf)
        if not np.isfinite(log_w).any():
            return m, kappa, np.full(samples, 1 / samples), 0.0
        w = np.exp(log_w - log_w.max())
        w /= w.sum()
        return m, kappa, w, float(1 / np.sum(w**2))

    def fit(self, counts: np.ndarray, seed: int = RNG_SEED, samples: int = 30000) -> Fit:
        counts = np.asarray(counts, float)
        rng = np.random.default_rng(seed)
        k_cat = counts.shape[1]
        k_hat = self._kappa_moment(counts)
        base = min(float(counts.sum()), len(counts) * k_hat + k_cat)
        best = None
        for scale in (1.0, 0.3, 3.0, 0.1, 10.0):
            attempt = self._attempt(counts, rng, samples, max(base * scale, 1.0), k_hat)
            if best is None or attempt[3] > best[3]:
                best = attempt
            if best[3] >= self.MIN_ESS * 5:
                break
        m, kappa, w, ess = best
        index = rng.choice(samples, size=DRAWS, p=w)
        mean, kap = m[index], kappa[index]
        new_study = np.vstack([rng.dirichlet(np.clip(a, 1e-6, None)) for a in mean * kap[:, None]])
        return Fit(
            self.family,
            posterior={"composition": [_quantiles(mean[:, c]) for c in range(k_cat)]},
            predictive={"composition": [_quantiles(new_study[:, c]) for c in range(k_cat)]},
            heterogeneity={"kappa": _quantiles(kap)},
            draws={**{f"p_{c}": mean[:, c] for c in range(k_cat)}, "kappa": kap},
            diagnostics={"importance_ess": ess, "importance_samples": samples},
        )
