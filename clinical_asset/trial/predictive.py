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
