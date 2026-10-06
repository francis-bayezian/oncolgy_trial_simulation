"""Two-arm non-inferiority on a binary endpoint (response), synthesis method, from the StudySpec and protocol facts.

The protocol states that the experimental arm must preserve at least a fraction f of the active control's effect over a
historical comparator. With RR = p_E / p_C in the new trial and RR_h = p_control / p_comparator in the historical trial:

    Z = [log RR + (1 - f) log RR_h] / sqrt( Var(log RR) + (1 - f)^2 Var(log RR_h) ),  non-inferior if Z > z_(1 - alpha)

(the synthesis test; the protocol's Mantel-Haenszel stratified risk ratio is approximated by the unstratified one).

Read from the specification: the preserved fraction (a quote 'preserves at least X% of <control> effect vs <comparator>'),
one-sided alpha, the per-arm sample size (target accrual and allocation), the design assumption for the response rate.
Read from the protocol facts: the historical response rates of the control regimen and the comparator (category text
matched to the names in the quote) with their 95% CIs, else the historical sample size.
Evidence (as of the cut-off in force): the control regimen's future-study response rate (efficacy_prior, V3 proportions).

Output: the predicted response rate of each arm and of the observed rates at the trial's size, the power at the
protocol's own assumption, and P(non-inferiority) as a curve over the true RR, integrated over the evidence prior.
Anything not found is UNRESOLVED with its reason.
"""

import json
import math
import re
from pathlib import Path

import numpy as np
from scipy import stats

from .predictive import from_draws
from .. import assets as _assets

NI_VERSION = "ni-binary-1.1.0"
PRESERVE = re.compile(r"preserv\w*\s+at\s+least\s+(\d+(?:\.\d+)?)\s*%\s+of\s+(.+?)\s+effect\s*(?:in terms of \w+\s*)?(?:vs\.?|versus|over|relative to)\s+([A-Za-z0-9\-+/ ]+?)(?:[.\n]|$)", re.I | re.S)


def _t(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def design(spec: dict) -> dict:
    found = None
    for a in spec.get("analyses") or []:
        for text in [_t(e) for e in a.get("effects") or []] + [_t(a.get("method")), _t(a.get("evidence"))]:
            m = PRESERVE.search(" ".join((text or "").split()))
            if m:
                found = {"fraction": float(m.group(1)) / 100, "control_phrase": m.group(2).strip(), "comparator": m.group(3).strip(),
                         "quote": m.group(0).strip(), "alpha": (a.get("alpha") or {}).get("value"), "analysis_id": a["analysis_id"]}
                break
        if found:
            break
    if not found:
        return {"status": "UNRESOLVED", "reason": "no 'preserves at least X% of the control effect' statement in the analyses"}
    assumed = None
    for a in spec.get("analyses") or []:
        for e in a.get("effects") or []:
            m = re.search(r"(?:ORR|response rate)\s*=\s*(\d+(?:\.\d+)?)\s*%", _t(e) or "", re.I)
            if m:
                assumed = {"rate": float(m.group(1)) / 100, "quote": " ".join((_t(e) or "").split())}
    sizes = [s for s in spec.get("sample_size") or [] if s["quantity"] in ("target_accrual", "maximum_accrual") and s.get("value")]
    total = max((s["value"] for s in sizes), default=None)
    ratio = ((spec.get("randomization") or {}).get("allocation") or {}).get("ratio") or [1, 1]
    n_arm = [int(round(total * r / sum(ratio[:2]))) for r in ratio[:2]] if total else None
    return {"status": "RESOLVED", **found, "alpha": found["alpha"] or 0.025, "design_assumption": assumed,
            "total_n": total, "n_per_arm": n_arm}


def historical(facts: list[dict], control_phrase: str, comparator: str) -> dict:
    comp = _tokens(comparator)
    ctrl = _tokens(control_phrase) - comp
    rates, cis, n_total = {}, {}, None
    for f in facts:
        cat = _tokens(_t(f.get("category")) or f.get("canonical_category", ""))
        var = f.get("canonical_variable") or ""
        val = (f.get("value") or {})
        if f.get("source") != "historical_study":
            continue
        role = "comparator" if cat and (cat <= comp | {"arm", "alone"} or cat == comp) else "control" if cat & ctrl else None
        if var == "overall_response_rate" and val.get("scale") == "proportion" and role:
            rates.setdefault(role, (val["value"], f["fact_id"], _t(f.get("value_text"))))
        elif var.endswith("confidence_interval") and "response" in var and role and val.get("upper") is not None:
            lo, hi = val["value"], val["upper"]
            lo, hi = (lo / 100, hi / 100) if hi > 1 else (lo, hi)
            cis.setdefault(role, (lo, hi, f["fact_id"]))
        elif var in ("study_enrollment",) and val.get("value"):
            n_total = n_total or val["value"]
    if "control" not in rates or "comparator" not in rates:
        return {"status": "UNRESOLVED", "reason": f"historical response rates not found in the facts (found {sorted(rates)})"}

    def var_log(role):
        p = rates[role][0]
        if role in cis:
            lo, hi, _ = cis[role]
            return ((math.log(hi) - math.log(lo)) / 3.92) ** 2, f"from the stated 95% CI ({cis[role][2]})"
        if n_total:
            n = n_total / 2
            return (1 - p) / (p * n), f"binomial with n = {n:g} (half of the historical N)"
        return None, "no CI or sample size"
    vc, sc = var_log("control")
    vk, sk = var_log("comparator")
    if vc is None or vk is None:
        return {"status": "UNRESOLVED", "reason": "no variance for the historical effect"}
    rr = rates["control"][0] / rates["comparator"][0]
    return {"status": "RESOLVED", "control_rate": rates["control"], "comparator_rate": rates["comparator"],
            "log_rr": math.log(rr), "rr": rr, "var_log_rr": vc + vk, "variance_basis": [sc, sk], "var_log_control": vc}


def _regimen_tau_draws(rng, size: int) -> tuple[np.ndarray, str] | None:
    """Between-study SD (logit) of the response rate among studies of the SAME regimen, from the V3 proportions asset
    in force (its tau posterior quantiles, interpolated as an inverse CDF)."""
    import pyarrow.parquet as pq

    from ..cutoff import asset

    f = asset("v3") / "proportions" / "tau_posteriors.parquet"
    if not f.exists():
        return None
    for r in pq.read_table(f).to_pylist():
        k = r["target_key"]
        if r["level"] == "regimen" and r["status"] == "PUBLISHED" and '"variable": "objective_response_rate"' in k and '"time": null' in k:
            p = [0.025, 0.10, 0.25, 0.50, 0.75, 0.90, 0.975]
            q = [r[f"tau_{s}"] for s in ("q025", "q10", "q25", "median", "q75", "q90", "q975")]
            return np.interp(rng.uniform(0.025, 0.975, size), p, q), f"{f.as_posix()} (regimen level, median {r['tau_median']:.2f})"
    return None


def cited_control_prior(hist: dict, rng, size: int = 20000) -> dict:
    """A new trial's control response rate from the protocol-cited historical rate of the SAME control regimen: its
    sampling error (from the stated CI) plus between-trial heterogeneity of one regimen (the asset's regimen-level tau)."""
    p = hist["control_rate"][0]
    tau = _regimen_tau_draws(rng, size)
    if tau is None:
        return {"status": "UNRESOLVED", "reason": "no regimen-level heterogeneity in the proportions asset"}
    se_logit = math.sqrt(hist["var_log_control"]) / (1 - p)            # delta method: log p -> logit p
    z = math.log(p / (1 - p)) + rng.normal(0, se_logit, size) + rng.normal(0, 1, size) * tau[0]
    draws = 1 / (1 + np.exp(-z))
    q = np.quantile(draws, [0.05, 0.1, 0.5, 0.9, 0.95])
    return {"status": "RESOLVED", "level": "protocol-cited historical, same regimen", "source": f"protocol fact {hist['control_rate'][1]} "
            f"({hist['control_rate'][2]}); heterogeneity {tau[1]}", "studies": 1,
            "rate": {"median": float(q[2]), "q05": float(q[0]), "q10": float(q[1]), "q90": float(q[3]), "q95": float(q[4]),
                     "percentiles": from_draws(draws)}, "draws": draws}


def ni_test(x_e, n_e, x_c, n_c, fraction, hist, alpha):
    pe, pc = (x_e + 0.5) / (n_e + 1), (x_c + 0.5) / (n_c + 1)
    lrr = np.log(pe / pc)
    v = (1 - pe) / (pe * (n_e + 1)) + (1 - pc) / (pc * (n_c + 1))
    z = (lrr + (1 - fraction) * hist["log_rr"]) / np.sqrt(v + (1 - fraction) ** 2 * hist["var_log_rr"])
    return z > stats.norm.ppf(1 - alpha)


def power(p_c: np.ndarray, rr: float, n_e: int, n_c: int, fraction, hist, alpha, rng, reps: int = 20000) -> float:
    pc = rng.choice(p_c, size=reps) if np.ndim(p_c) else np.full(reps, float(p_c))
    pe = np.clip(pc * rr, 1e-6, 1 - 1e-6)
    return float(np.mean(ni_test(rng.binomial(n_e, pe), n_e, rng.binomial(n_c, pc), n_c, fraction, hist, alpha)))


def arm_features(spec: dict) -> dict:
    """Disease family, agents and drug classes of each arm, as the safety stage derives them (from the safety asset in
    force: the as-of-T0 build under an evidence cut-off)."""
    from ..cutoff import asset
    from .safety import class_map, dose_reference, v3_features

    cmap, refs = class_map(), dose_reference(asset("safety"))
    fam = _assets.family_map()
    return {a["arm_id"]: v3_features(spec, _t(a["label"]), cmap, refs, fam) for a in spec["arms"]}


def run(spec_lock: Path, facts_lock: Path, safety_lock: Path | None, out_dir: Path, seed: int = 20260929) -> dict:
    from .efficacy_prior import arm_prior, observed_interval
    from .studyspec import load_facts, load_studyspec

    spec, _ = load_studyspec(spec_lock)
    facts, _ = load_facts(facts_lock)                    # USABLE facts only
    d = design(spec)
    out = {"ni_version": NI_VERSION, "design": d}
    if d["status"] == "RESOLVED":
        h = historical(facts, d["control_phrase"], d["comparator"])
        out["historical"] = h
    rng = np.random.default_rng(seed)
    if safety_lock:
        s = json.loads((Path(safety_lock) / "safety_results.json").read_text(encoding="utf-8"))
        feats = {a["arm_id"]: ((a.get("safety_v3") or {}).get("features") or {}) for a in s["arms"]}
    else:
        feats = arm_features(spec)
    f0 = next(iter(feats.values()), {})
    prior = arm_prior("objective_response_rate", f0.get("disease_family", ""), [a["agent"] for a in f0.get("agents", [])], f0.get("classes", [])) \
        if f0 else {"status": "UNRESOLVED", "reason": "no arm features"}
    out["evidence_prior"] = {k: v for k, v in prior.items() if k != "draws"}
    if prior.get("level") == "family" and d["status"] == "RESOLVED" and out["historical"]["status"] == "RESOLVED":
        # a mixture over unrelated regimens of the family is context, not a prediction for this arm: the protocol's cited
        # rate of the same control regimen (with the asset's same-regimen heterogeneity) is the deeper match
        cited = cited_control_prior(out["historical"], rng)
        if cited["status"] == "RESOLVED":
            out["evidence_prior_context"] = out["evidence_prior"]
            out["evidence_prior"] = {k: v for k, v in cited.items() if k != "draws"}
            prior = cited
    if d["status"] == "RESOLVED" and out["historical"]["status"] == "RESOLVED" and d["n_per_arm"]:
        n_e, n_c = d["n_per_arm"]
        h, fr, al = out["historical"], d["fraction"], d["alpha"]
        if d["design_assumption"]:
            out["power_at_protocol_assumption"] = {"rate": d["design_assumption"]["rate"], "rr": 1.0,
                                                   "power": power(d["design_assumption"]["rate"], 1.0, n_e, n_c, fr, h, al, rng)}
        grid = [0.80, 0.85, 0.90, 0.95, 1.0, 1.05]
        base = prior["draws"] if prior.get("status") == "RESOLVED" else (d["design_assumption"] or {}).get("rate")
        if base is not None:
            out["p_success_curve"] = [{"rr": g, "p_noninferior": power(base, g, n_e, n_c, fr, h, al, rng)} for g in grid]
            out["p_success_basis"] = (f"prior on the control response rate ({prior['level']})" if prior.get("status") == "RESOLVED"
                                      else "protocol assumption")
        if prior.get("status") == "RESOLVED":
            lo, hi = observed_interval(prior["draws"], n_c, rng)
            out["predicted_response"] = {"control_true_rate": prior["rate"], "observed_rate_90_at_n": [lo, hi], "n_per_arm": n_c,
                                         "level": prior["level"], "studies": prior.get("studies"),
                                         "note": "the evidence has no information on dosing schedule: both arms share this prediction under RR = 1"}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ni_results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out
