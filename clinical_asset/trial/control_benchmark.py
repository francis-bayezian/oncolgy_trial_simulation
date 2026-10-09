"""Hidden-control-arm benchmark (L056): can a method recover a real randomised control arm it has not seen?

For every completed randomised trial of the evidence corpus with one control arm (active, placebo, sham or no
intervention) and at least one experimental arm, the control arm is hidden. Each method gets only what a single-arm
study would have: the control regimen's context (drug classes, disease family, phase) and the experimental arm's
baseline characteristics (age, share female, share ECOG >= 1, race shares). Every fit leaves the trial out.

Outcomes: the control arm's share with any serious adverse event and its share who died (registry adverse-event table).
Methods (aggregate data only; IPD methods need patient data the registry does not hold):
  evidence_calibrated  the corpus regression for the regimen context; population characteristics through the evidence
                       synthesis's effect draws (refit without the trial); between-trial heterogeneity
  outcome_regression   the same regression with its own characteristic coefficients and coefficient uncertainty only
                       (aggregate simulated treatment comparison)
  map_prior            meta-analytic predictive prior: random-effects (DerSimonian-Laird) meta-analysis of other trials'
                       control arms in the same disease family
  naive_pooled         the pooled rate of those control arms (binomial uncertainty only)
  contextual_robust    the contextual baseline-risk model with similarity-weighted robust borrowing and
                       context-specific heterogeneity (control_model, L057); its settings learned on other folds
Metrics: bias, RMSE, 95% predictive-interval coverage, interval width, type I error (the real control tested against the
prediction, two-sided 5%), power at the stated odds ratios (POWER_ODDS_RATIOS), the interval score (alpha 0.05: width
plus 2/alpha times any miss), and all of them by similarity band (how close the target's best historical match is).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np

from .. import assets
from . import evidence_ledger as led
from . import evidence_synthesis as es
from . import control_model as cm
from . import patient_risk as pr

CONTROL_TYPES = {"ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "SHAM_COMPARATOR", "NO_INTERVENTION"}
OUTCOMES = ("serious_ae", "death")
POWER_ODDS_RATIOS = (0.67, 1.5)      # the effects at which power is reported (a setting, stated in the report)
PREDICTIVE_DRAWS = 2000
SYNTHESIS_DRAWS = 1000
MAP_MIN_ARMS = 3


def _norm(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").casefold()).strip()


def rct(trial: dict) -> dict | None:
    """The trial's experimental and control adverse-event groups, when it is randomised with one control arm."""
    ps = trial.get("protocolSection") or {}
    if ((ps.get("designModule") or {}).get("designInfo") or {}).get("allocation") != "RANDOMIZED":
        return None
    arms = [(_norm(a.get("label")), a.get("type")) for a in (ps.get("armsInterventionsModule") or {}).get("armGroups") or []]
    roles = {}
    for g in ((trial.get("resultsSection") or {}).get("adverseEventsModule") or {}).get("eventGroups") or []:
        t = _norm(g.get("title"))
        match = [typ for lab, typ in arms if lab and (lab == t or lab in t or t in lab)]
        if len(set(match)) == 1:
            roles[g.get("title")] = match[0]
    control = [g for g, typ in roles.items() if typ in CONTROL_TYPES]
    experimental = [g for g, typ in roles.items() if typ == "EXPERIMENTAL"]
    if len(control) != 1 or not experimental:
        return None
    return {"nct_id": ps["identificationModule"]["nctId"], "control": control[0], "experimental": experimental}


def _records() -> tuple[list[dict], list[dict], dict]:
    """Every arm record of the corpus (as the patient-risk regression uses them) and the randomised trials."""
    import pyarrow.parquet as pq

    model = json.loads((pr.model_dir() / "model.json").read_text(encoding="utf-8"))
    families, classes = {}, {}
    for a in pq.read_table(assets.path("safety") / "arms.parquet", columns=["nct_id", "group", "classes", "disease_family"]).to_pylist():
        families[a["nct_id"]] = a["disease_family"]
        classes[(a["nct_id"], pr._key(a["group"]))] = tuple(json.loads(a["classes"] or "[]"))
    recs, trials = [], []
    for f in sorted(Path(assets.path("raw_ctgov")).glob("NCT*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        ps = t.get("protocolSection") or {}
        start = ((ps.get("statusModule") or {}).get("startDateStruct") or {}).get("date") or ""
        countries = {loc.get("country") for loc in (ps.get("contactsLocationsModule") or {}).get("locations") or [] if loc.get("country")}
        region = "us_only" if countries == {"United States"} else "non_us_only" if countries and "United States" not in countries \
            else "mixed" if countries else None
        for r in pr.arm_records(t):
            r["family"] = families.get(r["nct_id"])
            r["classes"] = classes.get((r["nct_id"], pr._key(r["group"])), ())
            r["year"] = int(start[:4]) if start[:4].isdigit() else None
            r["region"] = region
            recs.append(r)
        x = rct(t)
        if x:
            trials.append(x)
    return recs, trials, model


def _ctx_design(recs: list[dict], ref: dict, controls: dict) -> np.ndarray:
    """The context design: the patient-risk regression's columns plus start year and region."""
    X, _ = pr._design(recs, ref, controls)
    extra = np.array([[((r["year"] or 2010) - 2010) / 10, 1.0 if r.get("year") is None else 0.0,
                       1.0 if r.get("region") == "us_only" else 0.0, 1.0 if r.get("region") == "mixed" else 0.0,
                       1.0 if r.get("region") is None else 0.0] for r in recs])
    return np.hstack([X, extra])


def _fold(nct: str) -> int:
    return int(nct[3:]) % cm.FOLDS


def _interval_score(lo: float, hi: float, y: float, alpha: float = 0.05) -> float:
    return (hi - lo) + (2 / alpha) * max(0.0, lo - y) + (2 / alpha) * max(0.0, y - hi)


def _expit(x):
    return 1 / (1 + np.exp(-x))


def _interval_counts(p_draws: np.ndarray, n: int, rng) -> tuple[float, float]:
    y = rng.binomial(n, np.clip(p_draws, 1e-6, 1 - 1e-6))
    return float(np.quantile(y, 0.025)), float(np.quantile(y, 0.975))


def _dersimonian_laird(k: np.ndarray, n: np.ndarray) -> tuple[float, float, float]:
    """Random-effects meta-analysis of logit proportions: mean, its variance, between-arm variance tau^2."""
    p = (k + 0.5) / (n + 1)
    y = np.log(p / (1 - p))
    v = 1 / (k + 0.5) + 1 / (n - k + 0.5)
    w = 1 / v
    mu_f = np.sum(w * y) / np.sum(w)
    q = np.sum(w * (y - mu_f) ** 2)
    c = np.sum(w) - np.sum(w ** 2) / np.sum(w)
    tau2 = max(0.0, (q - (len(y) - 1)) / c) if c > 0 else 0.0
    ws = 1 / (v + tau2)
    mu = np.sum(ws * y) / np.sum(ws)
    return float(mu), float(1 / np.sum(ws)), float(tau2)


def _predict(S: dict, target: dict, outcome: str, keep: np.ndarray, params: dict) -> tuple[dict, int, float, tuple, list[int]]:
    """Every method's predictive draws of the target control arm's rate, from the arms kept (`keep`, the target's own
    trial removed), with the contextual model's learned `params`."""
    recs, ref, controls, X_all, Xc_all, rng = S["recs"], S["ref"], S["controls"], S["X_all"], S["Xc_all"], S["rng"]
    char_cols, role = S["char_cols"], S["role"]
    xt = pr._design([target], ref, controls)[0][0]
    m = keep & np.array([bool(r.get(outcome)) for r in recs])
    X = X_all[m]
    k = np.array([recs[i][outcome][0] for i in np.flatnonzero(m)], float)
    n = np.array([recs[i][outcome][1] for i in np.flatnonzero(m)], float)
    beta, se = pr.fit_logistic(X, k, n)
    eta = X @ beta
    # between-arm heterogeneity on the logit scale beyond binomial noise (method of moments)
    p = np.clip(k / n, 0.5 / n, 1 - 0.5 / n)
    resid2 = (np.log(p / (1 - p)) - eta) ** 2 - 1 / (n * p * (1 - p))
    tau2 = max(0.0, float(np.average(resid2, weights=n)))
    H = X.T @ (X * (n * _expit(eta) * (1 - _expit(eta)))[:, None]) + np.diag([0.0] + [1.0] * (X.shape[1] - 1))
    cov = np.linalg.inv(H)
    preds = {}
    # outcome regression: own coefficients, coefficient uncertainty only
    mu_or, var_or = float(xt @ beta), float(xt @ cov @ xt)
    preds["outcome_regression"] = _expit(rng.normal(mu_or, math.sqrt(var_or), PREDICTIVE_DRAWS))
    # evidence-calibrated: context part from the regression, population part from the synthesis (refit without
    # the trial), plus between-trial heterogeneity
    evid = [e for e in led.entries() if e["tier"] != 3]
    for c, col in zip(("age10", "female", "ecog1", "asian", "black"), char_cols, strict=True):
        evid.append({"characteristic": c, "estimand": led.SIMULATED[outcome], "tier": 3, "estimate": float(beta[col]),
                     "se": float(se[col]), "citation": "leave-one-trial-out corpus regression"})
    syn = es.synthesise(evid, draws=SYNTHESIS_DRAWS, seed=S["seed"])
    ctx = float(xt @ beta) - float(sum(xt[col] * beta[col] for col in char_cols))
    draws_eta = np.full(SYNTHESIS_DRAWS, ctx)
    for c, col in zip(("age10", "female", "ecog1", "asian", "black"), char_cols, strict=True):
        eff = syn["effects"].get(f"{c}|{led.SIMULATED[outcome]}")
        if eff:
            draws_eta = draws_eta + np.array(eff["draws"]) * xt[col]
    draws_eta = draws_eta + rng.normal(0, math.sqrt(tau2 + var_or), SYNTHESIS_DRAWS)
    preds["evidence_calibrated"] = _expit(draws_eta)
    # historical controls: other trials' control arms in the same disease family
    hist = [i for i, r in role.items() if r == "control" and recs[i]["nct_id"] != target["nct_id"] and recs[i].get(outcome)
            and recs[i].get("family") == target.get("family")]
    if len(hist) < MAP_MIN_ARMS:
        hist = [i for i, r in role.items() if r == "control" and recs[i]["nct_id"] != target["nct_id"] and recs[i].get(outcome)]
    hk = np.array([recs[i][outcome][0] for i in hist], float)
    hn = np.array([recs[i][outcome][1] for i in hist], float)
    mu, vmu, t2 = _dersimonian_laird(hk, hn)
    preds["map_prior"] = _expit(rng.normal(mu, math.sqrt(vmu + t2), PREDICTIVE_DRAWS))
    preds["naive_pooled"] = np.full(PREDICTIVE_DRAWS, hk.sum() / hn.sum())
    # contextual robust: context regression without the trial, similarity-weighted residuals of all other arms
    bc, _ = pr.fit_logistic(Xc_all[m], k, n)
    eta_c = Xc_all[m] @ bc
    el = np.array([cm.emp_logit(a, b2) for a, b2 in zip(k, n, strict=True)])
    xtc = _ctx_design([target], ref, controls)[0]
    Hc = Xc_all[m].T @ (Xc_all[m] * (n * _expit(eta_c) * (1 - _expit(eta_c)))[:, None]) + np.diag([0.0] + [1.0] * (Xc_all.shape[1] - 1))
    var_c = float(xtc @ np.linalg.inv(Hc) @ xtc)
    rows_m = np.array([S["pool_pos"][outcome][i] for i in np.flatnonzero(m)])
    D = S["pools"][outcome].distances(target, rows_m)
    comp, band, smax = cm.predict(params, float(xtc @ bc), var_c, D, el[:, 0] - eta_c)
    preds["contextual_robust"] = cm.draws(comp, PREDICTIVE_DRAWS, rng)
    return preds, band, smax, comp, hist


def _setup(seed: int) -> tuple[dict, list[dict], dict]:
    """The corpus arms, design matrices, arm roles and similarity pools every prediction uses."""
    rng = np.random.default_rng(seed)
    recs, trials, model = _records()
    ref, controls = model["reference"], model["controls"]
    by_trial: dict[str, list[int]] = {}
    for i, r in enumerate(recs):
        by_trial.setdefault(r["nct_id"], []).append(i)
    X_all, names = pr._design(recs, ref, controls)
    char_cols = [names.index(c) for c in ("age10", "female", "ecog1", "asian", "black")]
    # control arms of every randomised trial: the historical controls of MAP and naive pooling
    role = {}
    for t in trials:
        for i in by_trial.get(t["nct_id"], []):
            if recs[i]["group"] == t["control"]:
                role[i] = "control"
            elif recs[i]["group"] in t["experimental"]:
                role[i] = "experimental"
    Xc_all = _ctx_design(recs, ref, controls)
    all_classes = sorted({c for r in recs for c in r.get("classes") or ()})
    pools = {o: cm.Pool([r for r in recs if r.get(o)], all_classes) for o in OUTCOMES}
    pool_pos = {o: {i: j for j, i in enumerate(i for i, r in enumerate(recs) if r.get(o))} for o in OUTCOMES}
    S = {"recs": recs, "ref": ref, "controls": controls, "X_all": X_all, "Xc_all": Xc_all, "char_cols": char_cols, "role": role,
         "pools": pools, "pool_pos": pool_pos, "rng": rng, "seed": seed, "all_classes": all_classes}
    return S, trials, by_trial


def _learn(S: dict, outcome: str, train: np.ndarray, label: str) -> tuple[dict, dict]:
    """The contextual robust model's settings learned on the arms in `train` (their control arms are the targets)."""
    recs, Xc_all = S["recs"], S["Xc_all"]
    idx = np.flatnonzero(train)
    k = np.array([recs[i][outcome][0] for i in idx], float)
    n = np.array([recs[i][outcome][1] for i in idx], float)
    b, _ = pr.fit_logistic(Xc_all[idx], k, n)
    eta = Xc_all[idx] @ b
    el = np.array([cm.emp_logit(a, m) for a, m in zip(k, n, strict=True)])
    resid, rvar = el[:, 0] - eta, el[:, 1]
    tau_g2 = max(0.0, float(np.average(resid ** 2 - rvar, weights=n)))
    pos = {i: j for j, i in enumerate(idx)}
    targets = []
    for i, rl in S["role"].items():
        if rl == "control" and i in pos:
            j = pos[i]
            targets.append({**recs[i], "eta": float(eta[j]), "eta_var": 0.0, "u": float(resid[j]), "u_var": float(rvar[j]),
                            "k": int(k[j]), "n": int(n[j])})
    pool = cm.Pool([recs[i] for i in idx], S["all_classes"])
    params, info = cm.learn(targets, pool, resid, rvar, np.array([recs[i]["nct_id"] for i in idx]), tau_g2, label=label)
    return params, {**info, "training_targets": len(targets), "tau_global2": round(tau_g2, 4)}


def run(max_trials: int | None = None, seed: int = 20261008, out: Path | None = None) -> dict:
    S, trials, by_trial = _setup(seed)
    recs, role, rng = S["recs"], S["role"], S["rng"]
    # contextual robust model: settings learned per fold and outcome on trials outside the fold
    fold_params, fold_info = {}, {}
    for outcome in OUTCOMES:
        has = np.array([bool(r.get(outcome)) for r in recs])
        for f in range(cm.FOLDS):
            cm.log(f"learning {outcome} fold {f}")
            train = has & np.array([_fold(r["nct_id"]) != f for r in recs])
            fold_params[(outcome, f)], fold_info[f"{outcome}|fold{f}"] = _learn(S, outcome, train, f"{outcome} fold {f}")
    rows = []
    usable = [t for t in trials if any(role.get(i) == "control" for i in by_trial.get(t["nct_id"], []))
              and any(role.get(i) == "experimental" for i in by_trial.get(t["nct_id"], []))]
    if max_trials:
        usable = usable[:max_trials]
    for ti, t in enumerate(usable):
        if ti % 50 == 0:
            cm.log(f"benchmark trial {ti + 1} of {len(usable)}")
        ids = by_trial[t["nct_id"]]
        ci = next(i for i in ids if role.get(i) == "control")
        ei = [i for i in ids if role.get(i) == "experimental"]
        ctrl = recs[ci]
        # the single-arm study's knowledge: the experimental arm's baseline, the control regimen's context
        exp_n = sum((recs[i].get("serious_ae") or (0, 1))[1] for i in ei)
        pop = {}
        for c in ("age", "female", "ecog1", "asian", "black"):
            v = [(recs[i][c], (recs[i].get("serious_ae") or (0, 1))[1]) for i in ei if recs[i].get(c) is not None]
            pop[c] = sum(a * w for a, w in v) / sum(w for _, w in v) if v and sum(w for _, w in v) else None
        target = {**ctrl, **{c: pop[c] for c in pop}}           # the control's context with the experimental population
        keep = np.array([recs[i]["nct_id"] != t["nct_id"] for i in range(len(recs))])
        for outcome in OUTCOMES:
            if not ctrl.get(outcome):
                continue
            k_obs, n_obs = ctrl[outcome]
            preds, band, smax, comp, hist = _predict(S, target, outcome, keep, fold_params[(outcome, _fold(t["nct_id"]))])
            for method, pd in preds.items():
                lo, hi = _interval_counts(pd, int(n_obs), rng)
                power = {}
                for orr in POWER_ODDS_RATIOS:
                    p_true = np.clip(k_obs / n_obs, 0.5 / n_obs, 1 - 0.5 / n_obs)
                    p_alt = 1 / (1 + math.exp(-(math.log(p_true / (1 - p_true)) + math.log(orr))))
                    y = rng.binomial(int(n_obs), p_alt, 200)
                    power[str(orr)] = float(np.mean((y < lo) | (y > hi)))
                rows.append({"nct_id": t["nct_id"], "outcome": outcome, "method": method, "observed": k_obs / n_obs, "n": int(n_obs),
                             "predicted": float(pd.mean()), "lower": lo / n_obs, "upper": hi / n_obs,
                             "covered": bool(lo <= k_obs <= hi), "power": power, "family": ctrl.get("family"),
                             "historical_arms": len(hist), "interval_score": _interval_score(lo / n_obs, hi / n_obs, k_obs / n_obs),
                             "similarity_band": band, "best_similarity": smax, "mixture_pi": float(np.asarray(comp[0]).ravel()[0])})
    def metrics(rs):
        err = np.array([r["predicted"] - r["observed"] for r in rs])
        cov = float(np.mean([r["covered"] for r in rs]))
        return {"trials": len(rs), "bias": round(float(err.mean()), 4), "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
                "coverage_95": round(cov, 3), "type_i_error": round(1 - cov, 3),
                "median_interval_width": round(float(np.median([r["upper"] - r["lower"] for r in rs])), 4),
                "mean_interval_score": round(float(np.mean([r["interval_score"] for r in rs])), 4),
                **{f"power_or_{o}": round(float(np.mean([r["power"][str(o)] for r in rs])), 3) for o in POWER_ODDS_RATIOS}}

    methods = ("contextual_robust", "evidence_calibrated", "outcome_regression", "map_prior", "naive_pooled")
    by_band = {}
    for outcome in OUTCOMES:
        for method in methods:
            for band in range(cm.BANDS):
                rs = [r for r in rows if r["outcome"] == outcome and r["method"] == method and r["similarity_band"] == band]
                if rs:
                    by_band[f"{outcome}|{method}|band{band}"] = metrics(rs)
    summary = {}
    for outcome in OUTCOMES:
        for method in methods:
            rs = [r for r in rows if r["outcome"] == outcome and r["method"] == method]
            if not rs:
                continue
            err = np.array([r["predicted"] - r["observed"] for r in rs])
            cov = float(np.mean([r["covered"] for r in rs]))
            summary[f"{outcome}|{method}"] = {
                "trials": len(rs), "bias": round(float(err.mean()), 4), "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
                "coverage_95": round(cov, 3), "type_i_error": round(1 - cov, 3),
                "median_interval_width": round(float(np.median([r["upper"] - r["lower"] for r in rs])), 4),
                "mean_interval_score": round(float(np.mean([r["interval_score"] for r in rs])), 4),
                **{f"power_or_{o}": round(float(np.mean([r["power"][str(o)] for r in rs])), 3) for o in POWER_ODDS_RATIOS}}
    out = Path(out or pr.model_dir() / "benchmark")
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark_rows.json").write_text(json.dumps(rows), encoding="utf-8")
    doc = {"randomised_trials_found": len(trials), "trials_benchmarked": len(usable), "power_odds_ratios": list(POWER_ODDS_RATIOS),
           "summary": summary, "by_similarity_band": by_band, "contextual_robust_learning": fold_info}
    (out / "benchmark_summary.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def _population_from_adsl(adsl: Path, arm: str) -> dict:
    """An arm's aggregate characteristics from simulated subject-level data (ADSL): what the protocol alone gives."""
    import csv

    with open(adsl, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["ARM"] == arm]
    if not rows:
        raise ValueError(f"no ADSL rows for {arm}")
    share = lambda f: sum(map(f, rows)) / len(rows)  # noqa: E731
    ecog = [r for r in rows if (r.get("ECOG") or "").strip() not in ("", "nan", "None")]
    return {"age": sum(float(r["AGE"]) for r in rows) / len(rows), "female": share(lambda r: r["SEX"] == "female"),
            "ecog1": sum(float(r["ECOG"]) >= 1 for r in ecog) / len(ecog) if ecog else None,
            "asian": share(lambda r: r["RACE"] == "asian"), "black": share(lambda r: r["RACE"] == "black_or_african_american"),
            "n": len(rows)}


def external(registry_file: Path, safety_dir: Path, adsl: Path, control_arm: str, experimental_arm: str, out: Path,
             seed: int = 20261008) -> dict:
    """Predict the control arm of a trial OUTSIDE the corpus with every benchmark method, and score it against the
    trial's posted control arm.

    Context of the control arm: its drug classes and disease family from the locked safety stage; phase, start year and
    region from the registered design (known before results). Population, two variants:
      registry_experimental  the experimental arm's posted baseline (the benchmark's single-arm-study definition)
      simulated_protocol     the simulated experimental arm (locked ADSL): protocol and evidence only, no trial data
    The contextual model's settings are learned on every corpus trial (the target is not one of them)."""
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    ps = registry["protocolSection"]
    nct = ps["identificationModule"]["nctId"]
    roles = rct(registry)
    if not roles:
        raise ValueError(f"{nct}: no single control arm with posted adverse events")
    arm_recs = {r["group"]: r for r in pr.arm_records(registry)}
    ctrl_obs = arm_recs[roles["control"]]
    safety = json.loads((Path(safety_dir) / "safety_results.json").read_text(encoding="utf-8"))
    feat = next(a for a in safety["arms"] if a["arm_id"] == control_arm)["safety_v3"]["features"]
    start = ((ps.get("statusModule") or {}).get("startDateStruct") or {}).get("date") or ""
    countries = {loc.get("country") for loc in (ps.get("contactsLocationsModule") or {}).get("locations") or [] if loc.get("country")}
    region = "us_only" if countries == {"United States"} else "non_us_only" if countries and "United States" not in countries \
        else "mixed" if countries else None
    context = {"nct_id": nct, "group": roles["control"],
               "phase": "/".join(sorted((ps.get("designModule") or {}).get("phases") or [])) or "NA",
               "family": feat.get("disease_family"), "classes": tuple(feat.get("classes") or ()),
               "year": int(start[:4]) if start[:4].isdigit() else None, "region": region}
    exp = [arm_recs[g] for g in roles["experimental"]]
    w = [(r.get("serious_ae") or (0, 1))[1] for r in exp]

    def weighted(c):
        v = [(r[c], wi) for r, wi in zip(exp, w, strict=True) if r.get(c) is not None]
        return sum(a * wi for a, wi in v) / sum(wi for _, wi in v) if v else None

    reg_pop = {c: weighted(c) for c in ("age", "female", "ecog1", "asian", "black")}
    sim_pop = _population_from_adsl(Path(adsl), experimental_arm)
    variants = {"registry_experimental": reg_pop, "simulated_protocol": {c: sim_pop[c] for c in reg_pop}}

    S, _, _ = _setup(seed)
    recs, rng = S["recs"], S["rng"]
    if any(r["nct_id"] == nct for r in recs):
        raise ValueError(f"{nct} is in the corpus: use the cross-validated benchmark")
    keep = np.ones(len(recs), dtype=bool)
    rows, learning = [], {}
    for outcome in OUTCOMES:
        if not ctrl_obs.get(outcome):
            continue
        k_obs, n_obs = ctrl_obs[outcome]
        cm.log(f"learning {outcome} on all corpus trials")
        params, learning[outcome] = _learn(S, outcome, np.array([bool(r.get(outcome)) for r in recs]), f"{outcome} all")
        for variant, pop in variants.items():
            target = {**context, **pop}
            preds, band, smax, _, hist = _predict(S, target, outcome, keep, params)
            for method, pd in preds.items():
                lo, hi = _interval_counts(pd, int(n_obs), rng)
                rows.append({"outcome": outcome, "population": variant, "method": method, "observed": k_obs / n_obs, "k": int(k_obs),
                             "n": int(n_obs), "predicted": float(pd.mean()), "median": float(np.median(pd)),
                             "lower": lo / n_obs, "upper": hi / n_obs, "covered": bool(lo <= k_obs <= hi),
                             "interval_score": _interval_score(lo / n_obs, hi / n_obs, k_obs / n_obs),
                             "similarity_band": band, "best_similarity": smax, "historical_arms": len(hist)})
    doc = {"nct_id": nct, "control_group": roles["control"], "control_arm": control_arm, "experimental_arm": experimental_arm,
           "context": {k: (list(v) if isinstance(v, tuple) else v) for k, v in context.items()}, "populations": variants,
           "simulated_n": sim_pop["n"], "rows": rows, "learning": learning,
           "benchmark_reference": "data/corpus_v2/patient_risk/benchmark/benchmark_summary.json (cross-validated, corpus trials)"}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "control_external.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    (out / "control_external.md").write_text(render_external(doc), encoding="utf-8")
    return doc


def render_external(doc: dict) -> str:
    c = doc["context"]
    L = [f"# Hidden-control prediction for {doc['nct_id']} (outside the corpus)", "",
         f"Control arm: {doc['control_group']} (locked arm {doc['control_arm']}). Context: {c['family']}, {c['phase']}, classes "
         f"{', '.join(c['classes'])}, start {c['year']}, region {c['region']}. Contextual model settings learned on every corpus trial.", "",
         "Populations: `registry_experimental` = the experimental arm's posted baseline (the benchmark's single-arm definition); "
         "`simulated_protocol` = the simulated experimental arm (protocol and evidence only).", ""]
    for k, v in doc["populations"].items():
        L.append(f"- {k}: " + ", ".join(f"{a} {x:.3g}" if x is not None else f"{a} n/a" for a, x in v.items()))
    for outcome in OUTCOMES:
        rs = [r for r in doc["rows"] if r["outcome"] == outcome]
        if not rs:
            continue
        L += ["", f"## {outcome}: observed {rs[0]['k']}/{rs[0]['n']} = {rs[0]['observed']:.1%}", "",
              "| population | method | predicted mean | 95% predictive interval | covered | interval score | similarity band |",
              "| --- | --- | ---: | --- | --- | ---: | ---: |"]
        for r in rs:
            L.append(f"| {r['population']} | {r['method']} | {r['predicted']:.1%} | {r['lower']:.1%}-{r['upper']:.1%} | {r['covered']} "
                     f"| {r['interval_score']:.3f} | {r['similarity_band']} |")
    L += ["", "One trial is one draw: the methods' calibration is the cross-validated benchmark over the corpus.", ""]
    return "\n".join(L)
