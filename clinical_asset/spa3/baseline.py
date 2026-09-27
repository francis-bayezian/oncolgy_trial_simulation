"""Milestone 3C: baseline marginal models, population classes and the dependency registry.

Age
    Registry arms report mean and SD of age among patients who satisfied the trial's age
    eligibility. Those are moments of a truncated distribution. Each arm is mapped to latent
    normal parameters (mu*, sigma*) whose truncation to the trial's own age range reproduces the
    reported mean and SD; the hierarchy is fitted to mu* (population mean) and log sigma*
    (within-study SD). A new protocol then draws ages from N(mu*, sigma*) truncated to *its*
    range. Trials are first split into population classes from their eligibility age range
    (PEDIATRIC, AYA, ADULT, MIXED), the top level of the age hierarchy.

Categorical variables (sex, race, ethnicity)
    Sex is one binomial tree. Race and ethnicity are sequential conditional binomials
    (stick-breaking): P(c1), P(c2 | not c1), ... Each step is an exact binomial tree, and every
    posterior draw composes into a valid probability vector. The category set is taken from the
    data (categories reported by most arms), never from a fixed list in code.

Dependencies
    Baseline-to-baseline dependencies (used by the copula) are kept apart from
    predictor-to-outcome dependencies (reserved for later milestones). A correlation is non-zero
    only when within-patient evidence supports it. Associations between arm-level summaries
    (for example, arms with older patients have fewer women) are ecological and are recorded but
    never used as patient-level correlations.
"""

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import optimize, stats

from ..spa2 import borrow as borrow2

UNIT_YEARS = {"year": 1.0, "month": 1 / 12, "week": 1 / 52.1775, "day": 1 / 365.25, "hour": 1 / 8766, "minute": 1 / 525960}
AGE_CLASSES = ("PEDIATRIC", "AYA", "ADULT", "MIXED")


def parse_age(text: str | None) -> float | None:
    if not text:
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)", str(text))
    if not m:
        return None
    unit = m.group(2).casefold().rstrip("s")
    return float(m.group(1)) * UNIT_YEARS[unit] if unit in UNIT_YEARS else None


def age_class(min_age: float | None, max_age: float | None) -> str:
    """Population class from an eligibility age range (in years; None = no limit)."""
    lo = 0.0 if min_age is None else min_age
    hi = math.inf if max_age is None else max_age
    if lo >= 15 and hi <= 39:
        return "AYA"
    if hi <= 21:
        return "PEDIATRIC"
    if lo >= 18:
        return "ADULT"
    return "MIXED"


def eligibility(raw_dir: Path) -> dict[str, dict]:
    """Age and sex eligibility per trial from the registry record. Protocol context only; these
    are never used as evidence about the enrolled population."""
    out = {}
    for path in raw_dir.glob("NCT*.json"):
        module = json.loads(path.read_text(encoding="utf-8")).get("protocolSection", {}).get("eligibilityModule", {})
        lo, hi = parse_age(module.get("minimumAge")), parse_age(module.get("maximumAge"))
        out[path.stem] = {"min_age": lo, "max_age": hi, "sex": module.get("sex") or "ALL", "age_class": age_class(lo, hi)}
    return out


def truncnorm_moments(mu: float, sigma: float, lo: float, hi: float) -> tuple[float, float]:
    a, b = (lo - mu) / sigma, (hi - mu) / sigma
    dist = stats.truncnorm(a, b, loc=mu, scale=sigma)
    return float(dist.mean()), float(dist.std())


def latent_age(mean: float, sd: float, lo: float | None, hi: float | None) -> tuple[float, float, str]:
    """Latent normal (mu, sigma) whose truncation to [lo, hi] has the reported mean and SD."""
    lo_v = -math.inf if lo is None else lo
    hi_v = math.inf if hi is None else hi
    z_lo, z_hi = (mean - lo_v) / sd, (hi_v - mean) / sd
    if min(z_lo, z_hi) > 4:
        return mean, sd, "bounds_not_binding"
    if not lo_v < mean < hi_v:
        return mean, sd, "reported_mean_outside_eligibility"

    def resid(x):
        m, s = truncnorm_moments(x[0], math.exp(x[1]), lo_v, hi_v)
        return [(m - mean) / sd, (s - sd) / sd]

    sol = optimize.least_squares(resid, [mean, math.log(sd)], bounds=([mean - 10 * sd, math.log(sd) - 1], [mean + 10 * sd, math.log(sd) + 3]))
    if sol.success and max(abs(v) for v in sol.fun) < 1e-3:
        return float(sol.x[0]), float(math.exp(sol.x[1])), "inverted"
    return mean, sd, "inversion_failed_reported_moments_used"


def age_records(rows: list[dict], families: dict, classes: dict, factors: dict, elig: dict) -> tuple[list[dict], list[dict], Counter]:
    """Latent age-mean records and log-SD records, one per arm."""
    means, sds, status = [], [], Counter()
    seen = set()
    for row in rows:
        if row["domain"] != "baseline" or row["variable"] != "age" or row["statistic_family"] != "continuous_mean":
            continue
        factor = factors.get(row["nct_id"], 1.0)
        n = row.get("denominator")
        if not factor or not row.get("sd") or not n or n < 2 or row.get("value") is None:
            status["skipped_missing_unit_sd_or_n"] += 1
            continue
        ctx = borrow2.context_fields(row, families, classes)
        if ctx["arm"] in seen:
            continue
        seen.add(ctx["arm"])
        e = elig.get(row["nct_id"], {"min_age": None, "max_age": None, "age_class": "MIXED"})
        mean, sd = float(row["value"]) * factor, float(row["sd"]) * factor
        mu, sigma, flag = latent_age(mean, sd, e["min_age"], e["max_age"])
        status[flag] += 1
        base = {**ctx, "age_class": e["age_class"], "n": n, "profile_id": row["profile_id"],
                "obs_id": row["scientific_observation_id"], "reported_mean": mean, "reported_sd": sd,
                "eligibility_min": e["min_age"], "eligibility_max": e["max_age"], "latent_status": flag}
        means.append({**base, "y": mu, "s2": sigma**2 / n, "sd_latent": sigma})
        sds.append({**base, "y": math.log(sigma), "s2": 1 / (2 * (n - 1))})
    return means, sds, status


def categorical_records(rows: list[dict], families: dict, classes: dict, variable: str, min_share: float = 0.8) -> tuple[list[dict], dict]:
    """Stick-breaking binomial records for one categorical baseline variable."""
    arms: dict[str, dict] = {}
    for row in rows:
        if row["domain"] != "baseline" or row["variable"] != variable or row.get("numerator") is None:
            continue
        ctx = borrow2.context_fields(row, families, classes)
        entry = arms.setdefault(ctx["arm"], {"ctx": ctx, "N": row.get("denominator"), "counts": {}})
        entry["counts"][str(row["category"])] = int(row["numerator"])
    reported = Counter(c for a in arms.values() for c in a["counts"])
    categories = [c for c, k in reported.items() if k >= min_share * len(arms)]
    pooled = Counter()
    for a in arms.values():
        for c in categories:
            pooled[c] += a["counts"].get(c, 0)
    order = sorted(categories, key=lambda c: -pooled[c])
    steps: dict[int, list[dict]] = defaultdict(list)
    used = 0
    for arm, a in arms.items():
        if not all(c in a["counts"] for c in order) or not a["N"]:
            continue
        total = sum(a["counts"][c] for c in order)
        if total == 0 or total > a["N"]:
            continue
        used += 1
        for j, cat in enumerate(order[:-1]):
            remaining = sum(a["counts"][c] for c in order[j:])
            if remaining == 0:
                break
            steps[j].append({**a["ctx"], "count": a["counts"][cat], "n": remaining, "obs_id": f"{variable}|{j}|{arm}",
                             "profile_id": None})
    meta = {"variable": variable, "categories": order, "arms_reporting": len(arms), "arms_used": used,
            "excluded_categories": sorted(set(reported) - set(order)),
            "note": f"categories reported by at least {min_share:.0%} of arms; arms reporting a different set are not used"}
    return [{"step": j, "category": order[j], "records": recs} for j, recs in sorted(steps.items())], meta


def stick_breaking(conditional: np.ndarray) -> np.ndarray:
    """(steps, D) conditional probabilities -> (steps + 1, D) category probabilities."""
    remaining = np.ones(conditional.shape[1])
    out = []
    for row in conditional:
        out.append(remaining * row)
        remaining = remaining * (1 - row)
    out.append(remaining)
    return np.array(out)


# ----------------------------------------------------------------------------- dependencies


def dependency_registry(age_means: list[dict], sex_records: list[dict], rows: list[dict], variables: list[str],
                        observed: list[dict] | None = None) -> dict:
    """Baseline-to-baseline registry (for the copula) and predictor-to-outcome registry (reserved).

    observed: optional within-patient correlations from sources that report them (for example
    individual-patient summaries), each {"a", "b", "rho", "se", "context", "source"}. The
    aggregate registry never reports within-patient correlations, so none are derived here."""
    observed = observed or []
    pairs = []
    for i, a in enumerate(variables):
        for b in variables[i + 1:]:
            hits = [o for o in observed if {o["a"], o["b"]} == {a, b}]
            pairs.append({"a": a, "b": b, "within_patient_evidence": len(hits),
                          "correlation_source": "OBSERVED" if hits else "PRIOR_DOMINATED",
                          "value_used": float(np.mean([h["rho"] for h in hits])) if hits else 0.0,
                          "note": None if hits else "no within-patient evidence; shrunk to zero (independence)"})
    # Ecological association between arm-level mean age and percent female: recorded, not used.
    by_arm = {r["arm"]: r for r in age_means}
    x, y = [], []
    for s in sex_records:
        if s["arm"] in by_arm:
            x.append(by_arm[s["arm"]]["reported_mean"])
            y.append(s["count"] / s["n"])
    ecological = []
    if len(x) >= 10:
        rho, p = stats.spearmanr(x, y)
        ecological.append({"a": "age", "b": "sex", "arm_level_spearman": float(rho), "p_value": float(p), "arms": len(x),
                           "status": "ECOLOGICAL_NOT_USED",
                           "note": "association between arm summaries reflects case mix across trials, not a within-patient correlation"})
    subgroup = Counter(str(r.get("domain")) for r in rows if r.get("profile_type") == "reported_subgroup")
    return {
        "baseline_baseline": pairs,
        "ecological_associations": ecological,
        "predictor_outcome": {"status": "RESERVED_FOR_LATER_MILESTONE",
                              "reported_subgroup_observations_by_domain": dict(subgroup),
                              "note": "subgroup-specific outcomes are predictor-to-outcome evidence and are not used by the baseline copula"},
    }


def nearest_correlation(a: np.ndarray, iterations: int = 200, tol: float = 1e-10) -> np.ndarray:
    """Higham (2002) alternating projections to the nearest correlation matrix (Frobenius)."""
    y = a.copy()
    ds = np.zeros_like(a)
    for _ in range(iterations):
        r = y - ds
        w, v = np.linalg.eigh((r + r.T) / 2)
        x = (v * np.maximum(w, 1e-10)) @ v.T
        ds = x - r
        y_new = x.copy()
        np.fill_diagonal(y_new, 1.0)
        if np.linalg.norm(y_new - y) < tol:
            y = y_new
            break
        y = y_new
    return y


def correlation_matrix(variables: list[str], registry: dict) -> dict:
    """Sparse copula correlation R with per-entry source labels and a PSD check/repair record."""
    k = len(variables)
    r = np.eye(k)
    labels = [["IDENTITY" if i == j else "PRIOR_DOMINATED" for j in range(k)] for i in range(k)]
    for pair in registry["baseline_baseline"]:
        i, j = variables.index(pair["a"]), variables.index(pair["b"])
        r[i, j] = r[j, i] = pair["value_used"]
        labels[i][j] = labels[j][i] = pair["correlation_source"]
    eig = np.linalg.eigvalsh(r)
    repaired = r
    if eig.min() < 1e-8:
        repaired = nearest_correlation(r)
    return {"variables": variables, "R": repaired.tolist(), "labels": labels,
            "min_eigenvalue_before": float(eig.min()), "min_eigenvalue_after": float(np.linalg.eigvalsh(repaired).min()),
            "psd_repair_frobenius": float(np.linalg.norm(repaired - r)), "nonzero_offdiagonal": int((np.abs(repaired - np.eye(k)) > 1e-12).sum() // 2)}
