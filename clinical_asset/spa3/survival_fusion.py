"""Milestone 3B: fuse relative effects (hazard ratios) with absolute survival curves.

For every hazard-ratio context (endpoint, disease, setting, "treatment vs comparator"):

Route A  both arms have an absolute curve from their own medians/landmarks (Milestone 2).
         The arm curves come from the absolute data; the reported HR is used as validation
         (implied cumulative-hazard ratios at 6, 12 and 24 months versus the HR posterior) and to
         judge proportional-hazards support.
Route B  only the comparator has an absolute curve. The treatment curve is S1(t) = S0(t)^HR,
         computed draw by draw (curve draw x HR draw), which assumes proportional hazards; the
         result is flagged assumption_based.
Otherwise the context is relative-only and is marked ABSOLUTE_BASELINE_REQUIRED: no absolute
         treatment curve is produced.

Every emitted curve carries S(t), H(t) = -log S(t) and h(t) = dH/dt on a monthly grid, the
median, S at 6, 12 and 24 months and the restricted mean survival time (RMST) at 24 and 60 months.
"""

import hashlib
import json
import math
from collections import defaultdict

import numpy as np
from scipy.integrate import trapezoid

from ..spa2 import survival as surv2

GRID = np.linspace(0.0, 60.0, 121)  # months
FINE = np.linspace(1e-3, 60.0, 1201)
LANDMARKS = (6, 12, 24)


def curve_draws(index_row: dict, draws_by_family: dict[str, dict], rng: np.random.Generator, n: int = 1000) -> np.ndarray:
    """(n, len(FINE)) survival curve draws, model-averaged over families by their weights."""
    weights = json.loads(index_row["family_weights"]) if isinstance(index_row["family_weights"], str) else index_row["family_weights"]
    families = [f for f in weights if f in draws_by_family and weights[f] > 0]
    w = np.array([weights[f] for f in families], float)
    w /= w.sum()
    pick = rng.choice(len(families), size=n, p=w)
    out = np.empty((n, FINE.size))
    for i, fam in enumerate(families):
        rows = np.flatnonzero(pick == i)
        if not rows.size:
            continue
        d = draws_by_family[fam]
        j = rng.integers(0, d["loc"].size, rows.size)
        out[rows] = surv2.survival(fam, FINE[None, :], d["loc"][j, None], d["shape"][j, None])
    return np.clip(out, 1e-12, 1 - 1e-12)


def summarise_curve(s: np.ndarray) -> dict:
    """Median, landmarks, RMST and S/H/h on GRID from (n, len(FINE)) curve draws."""
    h_cum = -np.log(s)
    hazard = np.gradient(h_cum, FINE, axis=1)
    below = s <= 0.5
    reached = below.any(1)
    med = np.where(reached, FINE[np.argmax(below, axis=1)], np.inf)
    dt = FINE[1] - FINE[0]
    rmst = {m: trapezoid(np.where(FINE <= m, s, 0.0), dx=dt, axis=1) + FINE[0] for m in (24, 60)}

    def q(x):
        # No interpolation: medians may be infinite (not reached within the horizon), reported as None.
        x = np.asarray(x)
        vals = np.quantile(x, [0.5, 0.025, 0.975], method="inverted_cdf")
        return {k: (float(v) if np.isfinite(v) else None) for k, v in zip(("median", "q025", "q975"), vals, strict=True)}

    at = np.searchsorted(FINE, GRID).clip(0, FINE.size - 1)
    grid = []
    for g, k in zip(GRID, at, strict=True):
        grid.append({"t": float(g), "S": q(s[:, k]), "H": q(h_cum[:, k]), "h": q(hazard[:, k])})
    lm = {f"survival_{t}_months": q(s[:, np.searchsorted(FINE, t)]) for t in LANDMARKS}
    return {"median_months": {**q(med), "share_not_reached": float(1 - reached.mean())},
            **lm, **{f"rmst_{m}_months": q(v) for m, v in rmst.items()}, "grid": grid}


def ph_assessment(s0: np.ndarray, s1: np.ndarray, log_hr: np.ndarray) -> dict:
    """Implied log cumulative-hazard ratios at the landmarks (Route A), their agreement with the
    reported HR, and proportional-hazards support (constancy of the implied ratio over time)."""
    implied = {}
    for t in LANDMARKS:
        k = np.searchsorted(FINE, t)
        implied[t] = np.log(-np.log(s1[:, k])) - np.log(-np.log(s0[:, k]))
    diff = implied[24] - implied[6]
    lo, hi = np.quantile(diff, [0.025, 0.975])
    # NOT_SUPPORTED: the implied log hazard ratio clearly changes between 6 and 24 months;
    # SUPPORTED: any change is bounded within +-0.35 (hazard ratio drifts by < ~40%);
    # otherwise the curves are too uncertain to judge.
    if (lo > 0.05 or hi < -0.05) and abs(np.median(diff)) >= 0.1:
        support = "NOT_SUPPORTED"
    elif lo >= -0.35 and hi <= 0.35:
        support = "SUPPORTED"
    else:
        support = "INCONCLUSIVE"
    agree = {}
    for t, v in implied.items():
        d = v - log_hr[: v.size]
        a, b = np.quantile(d, [0.025, 0.975])
        agree[f"{t}_months"] = {"implied_log_ratio_median": float(np.median(v)), "difference_from_reported_log_hr_median": float(np.median(d)),
                                "difference_interval_covers_zero": bool(a <= 0 <= b)}
    return {"PH_support": support, "log_ratio_change_6_to_24_months": {"median": float(np.median(diff)), "q025": float(lo), "q975": float(hi)},
            "hr_validation": agree}


def split_pair(pair: str) -> tuple[str, str]:
    left, _, right = pair.partition(" vs ")
    return left.strip(), right.strip()


def fuse(hr_params: list[dict], hr_draws: dict[str, np.ndarray], surv_index: list[dict], surv_draws: dict[str, dict],
         seed: int) -> tuple[list[dict], list[dict]]:
    """Return (fusion records, grid rows)."""
    rng = np.random.default_rng(seed)
    by_context: dict[tuple, dict] = {}
    for row in surv_index:
        if row.get("status") == "PUBLISHED":
            by_context[(row["endpoint"], row["disease"], row["setting"], row["treatment"])] = row
    records, grid_rows = [], []
    for p in hr_params:
        if p["target"].get("statistic_family") != "hazard_ratio" or p.get("status") != "PUBLISHED":
            continue
        endpoint = p["target"]["variable"]
        if endpoint not in surv2.ENDPOINTS:
            continue
        ctx = p["context"]
        treatment, comparator = split_pair(ctx["regimen_pair"])
        base = by_context.get((endpoint, ctx["disease"], ctx["setting"], comparator))
        arm = by_context.get((endpoint, ctx["disease"], ctx["setting"], treatment))
        log_hr = np.log(hr_draws[p["parameter_id"]].astype(float))
        fid = hashlib.sha1(json.dumps(["fusion", p["parameter_id"]]).encode()).hexdigest()[:16]
        rec = {"fusion_id": fid, "hr_parameter_id": p["parameter_id"], "endpoint": endpoint, "disease_family": ctx["disease_family"],
               "disease": ctx["disease"], "setting": ctx["setting"], "treatment": treatment, "comparator": comparator,
               "hr_population_posterior": {"median": float(np.exp(np.median(log_hr))), "q025": float(np.exp(np.quantile(log_hr, 0.025))),
                                           "q975": float(np.exp(np.quantile(log_hr, 0.975)))},
               "hr_studies": p["support"]["studies"],
               "comparator_curve_id": base["parameter_id"] if base else None, "treatment_curve_id": arm["parameter_id"] if arm else None}
        if base is None:
            rec.update(route="NONE", status="ABSOLUTE_BASELINE_REQUIRED", assumption_based=None, PH_support="UNTESTED",
                       note="relative evidence only: an absolute comparator curve is needed before a treatment curve can be produced")
            records.append(rec)
            continue
        s0 = curve_draws(base, surv_draws[base["parameter_id"]], rng)
        hr = np.exp(rng.choice(log_hr, size=s0.shape[0]))
        if arm is not None:
            s1 = curve_draws(arm, surv_draws[arm["parameter_id"]], rng)
            ph = ph_assessment(s0, s1, np.log(hr))
            rec.update(route="A", status="PUBLISHED", assumption_based=False, PH_support=ph["PH_support"], ph_assessment=ph,
                       treatment_curve_source="absolute arm data; HR used as validation",
                       comparator_identifiability=base["identifiability"], treatment_identifiability=arm["identifiability"])
        else:
            s1 = np.power(s0, hr[:, None])
            rec.update(route="B", status="PUBLISHED", assumption_based=True, PH_support="UNTESTED",
                       treatment_curve_source="S1 = S0^HR draw-wise (proportional hazards assumed)",
                       comparator_identifiability=base["identifiability"])
        c0, c1 = summarise_curve(s0), summarise_curve(s1)
        for label, c in (("comparator", c0), ("treatment", c1)):
            rec[f"{label}_curve"] = {k: v for k, v in c.items() if k != "grid"}
            for g in c["grid"]:
                grid_rows.append({"fusion_id": fid, "arm": label, "t_months": g["t"],
                                  **{f"{fn}_{k}": v for fn in ("S", "H", "h") for k, v in g[fn].items()}})
        records.append(rec)
    return records, grid_rows


def backtest(records: list[dict], observed: dict[tuple, list[dict]], surv_index: list[dict], surv_draws: dict, hr_draws: dict,
             tau: float, seed: int) -> list[dict]:
    """For Route A contexts, predict the treatment arm's reported medians and landmarks from
    S0^HR (as if its own curve were unknown) and score against the reported values. A naive
    HR = 1 prediction is scored on the same values."""
    rng = np.random.default_rng(seed)
    by_id = {r["parameter_id"]: r for r in surv_index}
    out = []
    for rec in records:
        if rec.get("route") != "A":
            continue
        cons = observed.get((rec["endpoint"], rec["disease"], rec["setting"], rec["treatment"]), [])
        if not cons:
            continue
        s0 = curve_draws(by_id[rec["comparator_curve_id"]], surv_draws[rec["comparator_curve_id"]], rng, n=600)
        hr = np.exp(rng.choice(np.log(hr_draws[rec["hr_parameter_id"]].astype(float)), size=600))
        for label, s1 in (("fused_S0_pow_HR", np.power(s0, hr[:, None])), ("naive_HR_1", s0)):
            for c in cons:
                if c["kind"] == "median":
                    below = s1 <= 0.5
                    med = np.where(below.any(1), FINE[np.argmax(below, axis=1)], 600.0)
                    pred = np.log(med)
                else:
                    k = np.searchsorted(FINE, min(c["t"], FINE[-1]))
                    pred = np.log(-np.log(np.clip(s1[:, k], 1e-9, 1 - 1e-9)))
                pred = rng.normal(pred, math.sqrt(c["se"] ** 2 + tau**2))
                q = np.quantile(pred, [0.025, 0.25, 0.75, 0.975])
                a = np.abs(pred - c["y"]).mean()
                b = np.abs(pred[:, None] - pred[None, :300]).mean()
                out.append({"fusion_id": rec["fusion_id"], "model": label, "kind": c["kind"], "PH_support": rec["PH_support"],
                            "covered_95": bool(q[0] <= c["y"] <= q[3]), "covered_50": bool(q[1] <= c["y"] <= q[2]),
                            "width_95": float(q[3] - q[0]), "crps": float(a - 0.5 * b),
                            "abs_error": float(abs(np.median(pred) - c["y"]))})
    return out


def observed_constraints(rows: list[dict], families: dict, classes: dict, context_fields) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["statistic_family"] in {"median_time", "survival_probability"} and r["variable"] in surv2.ENDPOINTS:
            ctx = context_fields(r, families, classes)
            groups[(r["variable"], ctx["disease"], ctx["setting"], ctx["regimen"])].append(r)
    return {k: surv2.constraints_for(v) for k, v in groups.items()}
