"""Predictive summaries in one form for every stage: the 10th, 30th, 50th, 70th and 90th percentiles (user direction
2026-10-05: five points instead of one wide 80% interval)."""

import numpy as np
from scipy import stats

PERCENTILES = (10, 30, 50, 70, 90)


def from_draws(x) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return {}
    return {f"p{p}": float(np.percentile(x, p)) for p in PERCENTILES}


def from_normal(mu: float, sd: float, transform=None) -> dict:
    """Percentiles of mu + sd * Z, mapped through `transform` (e.g. the inverse logit) when given."""
    f = transform or (lambda v: v)
    return {f"p{p}": float(f(mu + sd * stats.norm.ppf(p / 100))) for p in PERCENTILES}


def text(pct: dict, fmt: str = "{:.1f}") -> str:
    """'p10 a | p30 b | p50 c | p70 d | p90 e' for reports."""
    return " | ".join(f"p{p} {fmt.format(pct[f'p{p}'])}" for p in PERCENTILES if f"p{p}" in pct) if pct else "n/a"


def percentile_from_quantiles(quantiles: dict, x: float) -> float:
    """The percentile (0-100) of x in a positive distribution known only by its quantiles {'p10': .., 'p50': .., ...}:
    log-linear interpolation between the stated quantiles, lognormal tails fitted to the outermost pair."""
    import math

    from scipy import stats

    pts = sorted((float(k[1:]), float(v)) for k, v in quantiles.items() if k.startswith("p") and v and v > 0)
    lx = math.log(x)
    zs = [(stats.norm.ppf(p / 100), math.log(v)) for p, v in pts]
    if lx <= zs[0][1] or lx >= zs[-1][1]:
        (z0, l0), (z1, l1) = zs[0], zs[-1]
        sigma = (l1 - l0) / (z1 - z0)
        mid = l0 - z0 * sigma
        return float(100 * stats.norm.cdf((lx - mid) / sigma))
    for (za, la), (zb, lb) in zip(zs, zs[1:]):
        if la <= lx <= lb:
            return float(100 * stats.norm.cdf(za + (zb - za) * (lx - la) / (lb - la)))
    return float("nan")
