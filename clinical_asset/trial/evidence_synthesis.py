"""Evidence synthesis for patient-level effects: every effect a probability distribution (L056).

For each (characteristic, estimand), with the evidence of evidence_ledger:
  tier 3 (trial-level) evidence is noisy evidence:      beta ~ N(lambda * beta_A, sigma_A^2 + tau_eco^2)
  tier 1-2 (patient-level) evidence k:                 est_k ~ N(beta, se_k^2 + tau_between^2)
  hierarchy within a clinically defensible group g:    beta_j ~ N(mu_g, tau_g^2)   (groups of two or more members)
  a characteristic alone in its group:                 beta ~ the effect prior
lambda (shrinkage of trial-level evidence) and tau_eco (ecological uncertainty) are learned from every
(characteristic, estimand) that has both tier-3 and tier-1/2 evidence; with none, they stay at their priors and the
ledger says so. All hyperparameters are integrated by importance resampling of prior draws, so every draw of the
posterior is one coherent set of effects; a simulation replicate uses one draw (a posterior of cohorts).
The variance of every effect is split into the part from the evidence itself and the parts from each hyperparameter.
Every prior is a named setting below and is written into the synthesis output.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import evidence_ledger as led
from . import patient_risk

DRAWS = 4000
SHRINKAGE_MIN_DIRECT = 0.05    # shrinkage (1 - posterior mean / direct estimate) is reported only for a clear direct estimate
GROUP_CANDIDATES = 400          # prior draws of a group's mean and spread considered per posterior draw
SEED = 20261008
PRIORS = {   # every prior the engine uses; none is hidden in the code
    "effect": {"distribution": "normal", "mean": 0.0, "sd": 1.0,
               "meaning": "a characteristic alone in its group: log odds ratio before any evidence"},
    "lambda": {"distribution": "uniform", "low": 0.0, "high": 1.0, "meaning": "how much of a trial-level estimate carries to patients"},
    "tau_ecological": {"distribution": "half_normal", "scale": 1.0, "meaning": "extra uncertainty of trial-level (aggregate) evidence, log OR"},
    "tau_between": {"distribution": "half_normal", "scale": 0.5, "meaning": "between-study heterogeneity of patient-level evidence, log OR"},
    "group_mean": {"distribution": "normal", "mean": 0.0, "sd": 1.0, "meaning": "mean log OR of a group of characteristics"},
    "group_tau": {"distribution": "half_normal", "scale": 0.5, "meaning": "spread of log ORs within a group"},
}


def out_dir() -> Path:
    return patient_risk.model_dir()


def _lognorm(x, m, v):
    return -0.5 * (np.log(2 * np.pi * v) + (x - m) ** 2 / v)


def _combine(parts: list[tuple]) -> tuple:
    """Precision-weighted combination of normal pieces (mean, variance), vectorised over draws."""
    prec = sum(1 / v for _, v in parts)
    return sum(m / v for m, v in parts) / prec, 1 / prec


def synthesise(evidence: list[dict], draws: int = DRAWS, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    keys = sorted({(e["characteristic"], e["estimand"]) for e in evidence})
    t3 = {(e["characteristic"], e["estimand"]): e for e in evidence if e["tier"] == 3}
    t12: dict[tuple, list[dict]] = {}
    for e in evidence:
        if e["tier"] in (1, 2):
            t12.setdefault((e["characteristic"], e["estimand"]), []).append(e)
    # hyperparameter draws from their priors
    lam = rng.uniform(PRIORS["lambda"]["low"], PRIORS["lambda"]["high"], draws)
    teco = np.abs(rng.normal(0, PRIORS["tau_ecological"]["scale"], draws))
    tbet = np.abs(rng.normal(0, PRIORS["tau_between"]["scale"], draws))
    groups: dict[str, list[tuple]] = {}
    for k in keys:
        groups.setdefault(led.CHARACTERISTICS.get(k[0], {}).get("group", k[0]) + "|" + k[1], []).append(k)
    multi = {g: ks for g, ks in groups.items() if len(ks) >= 2}

    def evidence_summary(k):
        """The key's evidence as one normal piece per draw (given the hyperparameters), or None."""
        parts = []
        if k in t3:
            a, sa = t3[k]["estimate"], t3[k]["se"]
            parts.append((lam * a, np.full(draws, sa ** 2) + teco ** 2))
        for e in t12.get(k, []):
            parts.append((np.full(draws, e["estimate"]), e["se"] ** 2 + tbet ** 2))
        return _combine(parts) if parts else None

    # stage 1: lambda, tau_eco and tau_between are learned from paired evidence only (the same estimand with both
    # trial-level and patient-level evidence); without pairs they keep their priors
    logw = np.zeros(draws)
    pairs = [k for k in keys if k in t3 and k in t12]
    for k in pairs:
        m12, v12 = _combine([(np.full(draws, e["estimate"]), e["se"] ** 2 + tbet ** 2) for e in t12[k]])
        logw += _lognorm(m12, lam * t3[k]["estimate"], t3[k]["se"] ** 2 + teco ** 2 + v12)
    w = np.exp(logw - logw.max())
    w /= w.sum()
    ess = float(1 / np.sum(w ** 2))
    idx = rng.choice(draws, size=draws, p=w)
    lam, teco, tbet = lam[idx], teco[idx], tbet[idx]
    summaries = {k: evidence_summary(k) for k in keys}
    # stage 2: for every stage-1 draw, each group's mean and spread drawn from their posterior given the members'
    # evidence (importance resampling of GROUP_CANDIDATES prior draws per stage-1 draw)
    gmu, gtau, group_ess = {}, {}, {}
    for g, ks in multi.items():
        mu_c = rng.normal(PRIORS["group_mean"]["mean"], PRIORS["group_mean"]["sd"], (draws, GROUP_CANDIDATES))
        tau_c = np.abs(rng.normal(0, PRIORS["group_tau"]["scale"], (draws, GROUP_CANDIDATES)))
        lw = np.zeros((draws, GROUP_CANDIDATES))
        for k in ks:
            if summaries[k] is not None:
                m, v = summaries[k]
                lw += _lognorm(m[:, None], mu_c, tau_c ** 2 + v[:, None])
        wg = np.exp(lw - lw.max(axis=1, keepdims=True))
        wg /= wg.sum(axis=1, keepdims=True)
        group_ess[g] = round(float(np.median(1 / np.sum(wg ** 2, axis=1))), 1)
        pick = np.array([rng.choice(GROUP_CANDIDATES, p=row) for row in wg])
        gmu[g], gtau[g] = mu_c[np.arange(draws), pick], tau_c[np.arange(draws), pick]
    idx = np.arange(draws)
    hyper = {"lambda": lam, "tau_ecological": teco, "tau_between": tbet,
             **{f"group_mean:{g}": gmu[g] for g in multi}, **{f"group_tau:{g}": gtau[g] for g in multi}}

    effects = {}
    for k in keys:
        g = led.CHARACTERISTICS.get(k[0], {}).get("group", k[0]) + "|" + k[1]
        prior = (gmu[g][idx], gtau[g][idx] ** 2) if g in multi else (np.full(draws, PRIORS["effect"]["mean"]), np.full(draws, PRIORS["effect"]["sd"] ** 2))
        s = summaries[k]
        pm, pv = _combine([prior, (s[0][idx], s[1][idx])]) if s is not None else prior
        beta = rng.normal(pm, np.sqrt(pv))
        # variance split: the evidence itself (posterior variance given the hyperparameters) and each hyperparameter's
        # share of the variance of the conditional mean (first-order, from a linear fit of the conditional mean)
        total = float(beta.var())
        within = float(pv.mean())
        comps = {"evidence_and_prior": within / total if total else 0.0}
        names = [n for n in hyper if n in ("lambda", "tau_ecological", "tau_between")
                 or n.startswith(("group_mean:", "group_tau:")) and n.split(":", 1)[1] == g]
        if names and float(pm.var()) > 0:
            X = np.column_stack([hyper[n] for n in names] + [np.ones(draws)])
            coef = np.linalg.lstsq(X, pm, rcond=None)[0]
            for n, b in zip(names, coef[:-1], strict=True):
                comps[n.split(":")[0]] = comps.get(n.split(":")[0], 0.0) + float(b ** 2 * hyper[n].var()) / total
            comps["hyperparameter_interactions"] = max(0.0, 1 - sum(comps.values()))
        direct = (_combine([(e["estimate"], e["se"] ** 2) for e in t12[k]])[0] if k in t12 else t3[k]["estimate"] if k in t3 else None)
        mean = float(beta.mean())
        effects[f"{k[0]}|{k[1]}"] = {
            "characteristic": k[0], "estimand": k[1], "tiers": sorted({e["tier"] for e in evidence if (e["characteristic"], e["estimand"]) == k}),
            "posterior_mean": round(mean, 5), "posterior_sd": round(float(beta.std()), 5),
            "interval_95": [round(float(np.quantile(beta, 0.025)), 5), round(float(np.quantile(beta, 0.975)), 5)],
            "most_direct_evidence": None if direct is None else round(float(direct), 5),
            "shrinkage": None if direct is None or abs(direct) < SHRINKAGE_MIN_DIRECT else round(1 - mean / direct, 3),
            "variance_components": {n: round(v, 3) for n, v in comps.items()},
            "group": g if g in multi else None, "draws": [round(float(x), 5) for x in beta]}
    return {"engine": "evidence-synthesis-1.0.0", "draws": draws, "seed": seed, "priors": PRIORS,
            "learning": {"paired_effects": [f"{k[0]}|{k[1]}" for k in pairs],
                         "lambda_and_tau_ecological": "learned from paired effects" if pairs else
                         "NOT LEARNED: no characteristic has both trial-level and patient-level evidence for the same estimand; "
                         "lambda and tau_ecological are at their priors",
                         "groups": sorted(multi), "effective_sample_size_stage1": round(ess, 1),
                         "effective_sample_size_groups_median": group_ess,
                         "lambda_posterior": [round(float(np.quantile(hyper["lambda"], q)), 3) for q in (0.025, 0.5, 0.975)],
                         "tau_ecological_posterior": [round(float(np.quantile(hyper["tau_ecological"], q)), 3) for q in (0.025, 0.5, 0.975)]},
            "effects": effects}


def build() -> dict:
    """Synthesise the ledger's evidence, write synthesis.json and the evidence ledger."""
    evidence = led.entries()
    syn = synthesise(evidence)
    d = out_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "synthesis.json").write_text(json.dumps(syn), encoding="utf-8")
    led.write_ledger(led.ledger_rows(evidence, syn), d)
    return {k: v for k, v in syn.items() if k != "effects"} | {
        "effects": {k: {x: v[x] for x in ("posterior_mean", "interval_95", "shrinkage", "variance_components")} for k, v in syn["effects"].items()}}


def load() -> dict | None:
    f = out_dir() / "synthesis.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def draw(syn: dict, seed: int | None) -> dict[tuple, float]:
    """One coherent set of effects: the draw for a replicate's seed, or the posterior means without a seed."""
    out = {}
    for v in syn["effects"].values():
        out[(v["characteristic"], v["estimand"])] = v["posterior_mean"] if seed is None else v["draws"][seed % syn["draws"]]
    return out


def attribute(results: list[float], seeds: list[int], syn: dict | None = None) -> dict:
    """Why a simulated result is uncertain: the share of its variance across replicates explained by each effect's draw
    (first-order, linear), the rest being patient-level and simulation variation."""
    syn = syn or load()
    y = np.asarray(results, dtype=float)
    keys = [k for k, v in syn["effects"].items() if v["estimand"] in led.SIMULATED.values()]
    X = np.array([[syn["effects"][k]["draws"][s % syn["draws"]] for k in keys] for s in seeds])
    total = float(y.var())
    if total == 0 or len(y) < len(keys) + 3:
        return {"status": "TOO_FEW_REPLICATES", "replicates": len(y)}
    coef = np.linalg.lstsq(np.column_stack([X, np.ones(len(y))]), y, rcond=None)[0]
    shares = {k: float(b ** 2 * X[:, i].var()) / total for i, (k, b) in enumerate(zip(keys, coef[:-1], strict=True))}
    shares = {k: round(v, 3) for k, v in sorted(shares.items(), key=lambda kv: -kv[1]) if v >= 0.001}
    return {"status": "OK", "replicates": len(y), "variance": round(total, 6), "shares": shares,
            "patient_level_and_simulation": round(max(0.0, 1 - sum(shares.values())), 3)}
