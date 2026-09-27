"""Milestone 2B: parametric survival synthesis from medians and landmark survival probabilities.

Per context (disease, setting, regimen) and endpoint (OS, PFS, DFS, EFS, RFS, FFS, MFS, TTP, DoR, TTF)
the evidence constraints are:

* median time m (with CI when reported):   log m_model ~ N(log m_obs, se^2 + tau_study^2)
* landmark S(t) = p (with CI or N):          cloglog S_model(t) ~ N(cloglog p, se^2 + tau_study^2)

Families: Weibull, log-normal, log-logistic, Gompertz, each with a location/scale parameter and a
shape parameter, integrated exactly on a grid. A median alone identifies location but not shape,
so the shape prior is borrowed: pass 1 fits contexts with at least two constraints at distinct
times; their shape posteriors define an empirical prior per endpoint (and disease family where it
has enough contexts), which pass 2 uses for every context. Hazard ratios stay separate relative
evidence (borrow.py) and are never converted into absolute survival here.
"""

import math
from collections import defaultdict

import numpy as np
from scipy import stats

TO_MONTHS = {"month": 1.0, "week": 12 / 52.1775, "day": 12 / 365.25, "year": 12.0}
ENDPOINTS = {"overall_survival", "progression_free_survival", "event_free_survival", "disease_free_survival",
             "relapse_free_survival", "failure_free_survival", "metastasis_free_survival", "time_to_progression",
             "duration_of_response", "time_to_treatment_failure"}
TAU_STUDY = 0.15
LOC = np.linspace(np.log(0.1), np.log(600), 161)  # log months
FAMILIES = {
    "weibull": {"shape_grid": np.linspace(np.log(0.25), np.log(6), 81), "default_prior": (0.0, 0.7)},
    "lognormal": {"shape_grid": np.linspace(np.log(0.15), np.log(5), 81), "default_prior": (0.0, 0.7)},
    "loglogistic": {"shape_grid": np.linspace(np.log(0.3), np.log(8), 81), "default_prior": (np.log(1.5), 0.7)},
    "gompertz": {"shape_grid": np.linspace(-0.3, 0.3, 81), "default_prior": (0.0, 0.08)},
}


def survival(family: str, t: float | np.ndarray, loc: np.ndarray, shape: np.ndarray) -> np.ndarray:
    """S(t) for grid arrays loc (log scale in months, or log baseline hazard for Gompertz) and shape."""
    t = np.asarray(t, float)
    if family == "weibull":
        return np.exp(-np.power(t / np.exp(loc), np.exp(shape)))
    if family == "lognormal":
        return stats.norm.sf((np.log(t) - loc) / np.exp(shape))
    if family == "loglogistic":
        return 1 / (1 + np.power(t / np.exp(loc), np.exp(shape)))
    # Gompertz: h(t) = b exp(a t); loc = log of the time at which the cumulative hazard reaches log 2
    # under a = 0, i.e. b = log 2 / exp(loc); shape = a (per month).
    b = math.log(2) / np.exp(loc)
    a = shape
    small = np.abs(a) < 1e-6
    cumulative = np.where(small, b * t, b / np.where(small, 1, a) * np.expm1(a * t))
    return np.exp(-cumulative)


def median(family: str, loc: np.ndarray, shape: np.ndarray) -> np.ndarray:
    if family == "weibull":
        return np.exp(loc) * math.log(2) ** (1 / np.exp(shape))
    if family in {"lognormal", "loglogistic"}:
        return np.exp(loc)
    b = math.log(2) / np.exp(loc)
    a = shape
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(np.abs(a) < 1e-6, math.log(2) / b, np.log1p(a * math.log(2) / b) / np.where(np.abs(a) < 1e-6, 1, a))
    return np.where(np.isfinite(m) & (m > 0), m, np.inf)  # plateau above 50%: median not reached


def constraints_for(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        unit = r.get("unit")
        n = r.get("denominator")
        if r["statistic_family"] == "median_time" and unit in TO_MONTHS and r.get("value"):
            m = r["value"] * TO_MONTHS[unit]
            lo, hi = r.get("ci_lower"), r.get("ci_upper")
            if lo and hi and 0 < lo < r["value"] < hi:
                se = (math.log(hi) - math.log(lo)) / (2 * 1.96)
            else:
                se = math.sqrt(2 / n) if n else 0.35  # >= N/2 events for a reached median
            out.append({"kind": "median", "t": m, "y": math.log(m), "se": se, "study": r["nct_id"], "N": n})
        elif r["statistic_family"] == "survival_probability" and r.get("time") and r.get("time_unit") in TO_MONTHS:
            p = r.get("rate")
            if p is None and r.get("value") is not None:
                p = r["value"] / 100 if r["value"] > 1 else r["value"]
            if p is None or not 0 < p < 1:
                continue
            p = min(max(p, 0.01), 0.99)
            t = r["time"] * TO_MONTHS[r["time_unit"]]
            lo, hi = r.get("ci_lower"), r.get("ci_upper")
            if lo is not None and hi is not None and hi > lo:
                scale = 100 if hi > 1 else 1
                se_p = (hi - lo) / scale / (2 * 1.96)
            else:
                se_p = math.sqrt(p * (1 - p) / n) if n else 0.1
            se = max(se_p / (p * abs(math.log(p))), 0.02)
            out.append({"kind": "landmark", "t": t, "p": p, "y": math.log(-math.log(p)), "se": se, "study": r["nct_id"], "N": n})
    return out


def _log_post(family: str, cons: list[dict], prior: tuple[float, float], tau: float = TAU_STUDY) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    shape_grid = FAMILIES[family]["shape_grid"]
    L, S = np.meshgrid(LOC, shape_grid, indexing="ij")
    lp = stats.norm.logpdf(L, np.log(12), 2.0) + stats.norm.logpdf(S, prior[0], prior[1])
    for c in cons:
        var = c["se"] ** 2 + tau**2
        if c["kind"] == "median":
            with np.errstate(divide="ignore"):
                model = np.log(median(family, L, S))
            lp += np.where(np.isfinite(model), stats.norm.logpdf(c["y"], model, math.sqrt(var)), -1e6)
        else:
            s = np.clip(survival(family, c["t"], L, S), 1e-12, 1 - 1e-12)
            lp += stats.norm.logpdf(c["y"], np.log(-np.log(s)), math.sqrt(var))
    return lp, L, S


def fit_family(family: str, cons: list[dict], prior: tuple[float, float], rng: np.random.Generator, draws: int = 1000,
               tau: float = TAU_STUDY) -> dict:
    lp, _L, _S = _log_post(family, cons, prior, tau)
    w = np.exp(lp - lp.max())
    log_evidence = float(lp.max() + np.log(w.sum()))
    w /= w.sum()
    edge = float(w[0, :].sum() + w[-1, :].sum() + w[:, 0].sum() + w[:, -1].sum())
    idx = rng.choice(w.size, size=draws, p=w.ravel())
    i, j = np.unravel_index(idx, w.shape)
    dl, ds = LOC[1] - LOC[0], FAMILIES[family]["shape_grid"][1] - FAMILIES[family]["shape_grid"][0]
    loc = LOC[i] + rng.uniform(-dl / 2, dl / 2, draws)
    shape = FAMILIES[family]["shape_grid"][j] + rng.uniform(-ds / 2, ds / 2, draws)
    return {"family": family, "loc": loc, "shape": shape, "log_evidence": log_evidence, "edge": edge}


def estimate_tau(groups: dict[tuple, list[dict]]) -> tuple[float, int]:
    """Between-study SD on the log-median scale, by method of moments over pairs of studies that
    report a median for the same endpoint, disease, setting and regimen (top decile trimmed)."""
    diffs = []
    for rows in groups.values():
        by_study: dict[str, dict] = {}
        for c in constraints_for(rows):
            if c["kind"] == "median":
                by_study.setdefault(c["study"], c)
        s = list(by_study.values())
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                diffs.append(((s[i]["y"] - s[j]["y"]) ** 2 - s[i]["se"] ** 2 - s[j]["se"] ** 2) / 2)
    if len(diffs) < 10:
        return TAU_STUDY, len(diffs)
    d = np.array(diffs)
    d = np.clip(d, None, np.quantile(d, 0.9))
    return float(np.clip(math.sqrt(max(d.mean(), 0.0)), 0.1, 1.0)), len(diffs)


def identifiability(cons: list[dict]) -> str:
    times = {round(c["t"], 1) for c in cons}
    landmarks = {round(c["t"], 1) for c in cons if c["kind"] == "landmark"}
    studies = {c["study"] for c in cons}
    if len(landmarks) >= 2 and len(times) >= 3:
        return "HIGH"
    if len(times) >= 2 or len(studies) >= 2:
        return "MEDIUM"
    return "LOW"


def shape_priors(pass1: list[dict], min_contexts: int = 8) -> dict:
    """Empirical shape priors per (endpoint, family, disease_family), falling back to (endpoint, family)."""
    buckets: dict[tuple, list[float]] = defaultdict(list)
    for fit in pass1:
        for family, f in fit["families"].items():
            value = float(np.median(f["shape"]))
            buckets[(fit["endpoint"], family, fit["disease_family"])].append(value)
            buckets[(fit["endpoint"], family, "*")].append(value)
    priors = {}
    for key, values in buckets.items():
        if len(values) >= min_contexts:
            priors[key] = (float(np.mean(values)), max(float(np.std(values, ddof=1)), 0.15 if key[1] != "gompertz" else 0.02),
                           len(values))
    return priors


def derived(family_fits: list[dict], weights: np.ndarray, rng: np.random.Generator, draws: int = 1000) -> dict:
    """Model-averaged derived quantities: median and S(t) at 6, 12, 24 and 60 months."""
    choice = rng.choice(len(family_fits), size=draws, p=weights)
    med, s = [], {t: [] for t in (6, 12, 24, 60)}
    for idx, fit in enumerate(family_fits):
        take = choice == idx
        if not take.any():
            continue
        loc, shape = fit["loc"][: take.sum()], fit["shape"][: take.sum()]
        med.append(median(fit["family"], loc, shape))
        for t, values in s.items():
            values.append(survival(fit["family"], t, loc, shape))
    def q(x):
        x = np.concatenate(x)
        finite = x[np.isfinite(x)]
        out = {"median": float(np.median(x)), "q025": float(np.quantile(x, 0.025)), "q975": float(np.quantile(x, 0.975))}
        out["share_not_reached"] = float(1 - finite.size / x.size) if x.size else None
        return out
    return {"median_months": q(med), **{f"survival_{t}_months": q(v) for t, v in s.items()}}
