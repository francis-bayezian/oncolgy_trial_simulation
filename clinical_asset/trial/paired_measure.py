"""Per-participant paired measurements of a within-patient continuous endpoint (one value per exposure), from a named,
labelled source, and the protocol's paired analysis of them.

Sources (each records where its numbers come from; nothing is taken from the trial's own observed results):
* "design": the protocol's design assumption only: the paired difference ~ Normal(effect, sd_diff) with the SD the
  power statement implies. It gives differences, not per-exposure levels (those are not stated).
* "per_exposure": each exposure's level from an evidence table (lognormal fitted to a stated median and IQR, or
  mean and SD), with a within-patient correlation on the log scale (a stated value, else an assumption to be varied).

The analysis is the protocol's own: the paired test (Wilcoxon signed rank or paired t), its sidedness and alpha.
"""

import math

import numpy as np
from scipy import stats

Z75 = stats.norm.ppf(0.75)


def lognormal_from(stat: dict) -> tuple[float, float]:
    """(mu, sigma) of a lognormal from a median and IQR, or a mean and SD."""
    if stat.get("median") is not None and stat.get("q1") is not None and stat.get("q3") is not None:
        mu = math.log(stat["median"])
        sigma = (math.log(stat["q3"]) - math.log(stat["q1"])) / (2 * Z75)
        return mu, sigma
    m, s = stat["mean"], stat["sd"]
    sigma2 = math.log(1 + (s / m) ** 2)
    return math.log(m) - sigma2 / 2, math.sqrt(sigma2)


def generate(n: int, source: dict, rng: np.random.Generator) -> dict:
    """n participants' paired values: {'reference', 'index', 'difference'} (reference - index), arrays (levels may be None)."""
    if source["kind"] == "design":
        d = rng.normal(source["effect"], source["sd_diff"], n)
        return {"reference": None, "index": None, "difference": d}
    (m1, s1), (m2, s2) = lognormal_from(source["reference"]), lognormal_from(source["index"])
    rho = source.get("correlation", 0.5)
    z = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], n)
    ref, idx = np.exp(m1 + s1 * z[:, 0]), np.exp(m2 + s2 * z[:, 1])
    return {"reference": ref, "index": idx, "difference": ref - idx}


def analyse(diff: np.ndarray, test: str = "wilcoxon", alpha: float = 0.05, two_sided: bool = True) -> dict:
    """The protocol's paired analysis of the differences."""
    alt = "two-sided" if two_sided else "greater"
    if len(diff) < 2:
        return {"n": len(diff), "p_value": None, "success": None}
    p = stats.wilcoxon(diff, alternative=alt).pvalue if test == "wilcoxon" else stats.ttest_1samp(diff, 0.0, alternative=alt).pvalue
    w = diff[:, None] + diff[None, :]
    hl = float(np.median(w[np.triu_indices(len(diff))]) / 2)          # Hodges-Lehmann estimate of the paired shift
    return {"n": int(len(diff)), "mean_difference": float(np.mean(diff)), "median_difference": float(np.median(diff)),
            "hodges_lehmann": hl, "p_value": float(p), "success": bool(p < alpha and np.median(diff) > 0),
            "lower_in_index": int((diff > 0).sum()), "equal": int((diff == 0).sum())}


def design_power(effect: float, sd_diff: float, n: int, alpha: float = 0.05, two_sided: bool = True, rank: bool = True) -> float:
    """The protocol's analytic power: normal approximation with the rank test's asymptotic relative efficiency (3/pi)."""
    are = 3 / math.pi if rank else 1.0
    z = stats.norm.ppf(1 - alpha / (2 if two_sided else 1))
    return float(stats.norm.cdf(effect / sd_diff * math.sqrt(n * are) - z))


def simulated_power(effect: float, sd_diff: float, n: int, replicates: int, seed: int, alpha: float = 0.05) -> dict:
    """Power by simulation of the protocol's test, with its Monte Carlo standard error."""
    rng = np.random.default_rng(seed)
    ok = sum(analyse(rng.normal(effect, sd_diff, n), alpha=alpha)["success"] for _ in range(replicates))
    p = ok / replicates
    return {"power": p, "mc_se": math.sqrt(p * (1 - p) / replicates), "replicates": replicates, "seed": seed}
