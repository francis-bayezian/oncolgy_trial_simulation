"""Safety asset V3: adverse-event rates that depend on the regimen, dose, phase, age group and disease.

V2 pooled every arm of a treatment-class signature into one rate per event, and a regimen whose drugs had no class
fell back to the catch-all 'other' signature. V3:

Data. The arm-level adverse-event tables of the evidence build (registry, holdouts never read), with the registry
reporting mechanism of V2: an unlisted SERIOUS event in a study with a serious-event table is an exact zero; an
unlisted NON-SERIOUS event is left-censored below the study's frequency threshold (Y <= floor(q N / 100)).

Arm covariates, all from the arm's own registry record:
* drug classes of the regimen (the evidence build's drug-class map). 'other' and 'unclassified' are not
  pharmacological classes: they get no class effect; an arm containing such an agent gets the indicator
  'unclassified_agent';
* relative dose: each agent's dose per administration is read from the arm's registry text (an agent name followed
  by a number and a unit), divided by the corpus median for that agent and unit; the arm covariate is the mean log
  relative dose over agents with a dose (0 with the indicator 'dose_unknown' when none is read);
* phase, paediatric population (age groups without older adults), disease family (the evidence build's map).

Model, per (event, seriousness): logit p = alpha + sum of class effects + covariate effects, ridge (Gaussian) priors,
exact binomial and censored likelihood terms. The predictive rate of a new arm is logit-normal: the parameter
standard errors (Laplace, diagonal) plus a between-trial spread tau estimated from the exact arms (method of moments).

Validation: whole trials held out (20%, seeded). Log predictive probability of each held-out exact count, and
coverage of the 90% predictive count interval, for V3, for V3 without covariates (classes only), and for the V2
published class-signature rate.
"""

import hashlib
import json
import math
import random
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import optimize, special, stats

SAFETY3_VERSION = "safety-asset-3.1.0"
UNINFORMATIVE = {"other", "unclassified"}
DOSE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg/m\\?\^?2|mg/m²|mg/kg|mcg/kg|µg/kg|ug/kg|mg|mcg|µg|ug|g/m\\?\^?2|g|gy|iu/m\\?\^?2|iu|units?)\b", re.IGNORECASE)


def _unit(u: str) -> str:
    u = u.casefold().replace("\\", "").replace("^", "").replace("²", "2").replace("µ", "u").replace("mcg", "ug")
    return "unit" if u.startswith("unit") else u


def doses_in(text: str, agent: str, window: int = 80) -> list[tuple[float, str]]:
    """Doses written after a mention of the agent (within `window` characters, up to the end of that sentence or clause)."""
    out = []
    text = text or ""
    for m in re.finditer(re.escape(agent.casefold()), text.casefold()):
        seg = re.split(r"\.\s|;", text[m.end():m.end() + window])[0]
        d = DOSE.search(seg)
        if d:
            out.append((float(d.group(1).replace(",", ".")), _unit(d.group(2))))
    return out


# ----------------------------------------------------------------------------- arm table


def arm_table(raw_dir: Path, holdout: set[str], family_map_file: Path, class_map: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """(arms with covariates, arm-level adverse-event observations)."""
    import pyarrow.parquet as pq

    from .spa.evidence import load_frozen_profiles
    from .spa2.taxonomy import drug_class, modality
    from .spa2.toxicity import study_event_tables
    from .terminology import UmlsTerminology

    family = {r["disease"]: r["disease_family"] for r in pq.read_table(family_map_file).to_pylist() if (r.get("confidence") or 0) >= 0.7}
    arms: dict[tuple, dict] = {}
    for p in load_frozen_profiles():
        if p["profile_type"] not in {"randomized_arm", "study_arm", "treatment_sequence", "result_group"}:
            continue
        nct = p["source"]["nct"]
        if nct in holdout:
            continue
        t = p.get("treatment", {})
        comps = t.get("interventions") or ([t["drug"]] if t.get("drug") else [])
        classes = {drug_class(c, class_map) for c in comps if c}
        active = {c for c in classes if modality(c) not in {"supportive_care", "placebo_or_no_treatment"}} or classes
        arms[(nct, p["source"]["registry_group"])] = {
            "nct_id": nct, "group": p["source"]["registry_group"], "agents": comps,
            "reported_names": [x for x in [t.get("reported_name")] if x],
            "classes": sorted(active - UNINFORMATIVE), "unclassified_agent": bool(active & UNINFORMATIVE) or not active,
            "disease_family": family.get(((p.get("cancer") or {}).get("disease") or {}).get("name"), "other")}
    # registry covariates and doses
    by_nct: dict[str, list] = defaultdict(list)
    for key in arms:
        by_nct[key[0]].append(key)
    raw_doses: dict[tuple, list] = {}
    for nct, keys in by_nct.items():
        path = Path(raw_dir) / f"{nct}.json"
        if not path.exists():
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        ps = rec["protocolSection"]
        phases = "+".join(sorted(ps.get("designModule", {}).get("phases") or [])) or "unknown"
        ages = ps.get("eligibilityModule", {}).get("stdAges", [])
        ai = ps.get("armsInterventionsModule", {})
        groups = {g["title"].casefold(): g.get("description") or "" for g in (rec.get("resultsSection", {}).get("adverseEventsModule", {}) or {}).get("eventGroups", [])}
        labels = {g["label"].casefold(): g for g in ai.get("armGroups", [])}
        interventions = {i["name"].casefold(): i.get("description") or "" for i in ai.get("interventions", [])}
        for key in keys:
            a = arms[key]
            a.update({"phase": phases, "pediatric": "CHILD" in ages and "OLDER_ADULT" not in ages})
            g = labels.get(key[1].casefold()) or {}
            text = " ".join([groups.get(key[1].casefold(), ""), g.get("description") or ""])
            names = set(a["reported_names"]) | {n.split(": ", 1)[-1] for n in g.get("interventionNames", [])}
            found = []
            for name in names:
                own = interventions.get(name.casefold(), "")        # the intervention's own description: its first dose
                d = doses_in(text, name) or doses_in(own, name)
                if not d and DOSE.search(own):
                    first = DOSE.search(own)
                    d = [(float(first.group(1).replace(",", ".")), _unit(first.group(2)))]
                if d:
                    found.append((name.casefold(), d[0][0], d[0][1]))
            raw_doses[key] = found
    medians: dict[tuple, float] = {}
    pool: dict[tuple, list] = defaultdict(list)
    for found in raw_doses.values():
        for name, v, u in found:
            if v > 0:
                pool[(name, u)].append(v)
    medians = {k: float(np.median(v)) for k, v in pool.items() if len(v) >= 3}
    for key, a in arms.items():
        rel = [math.log(v / medians[(n, u)]) for n, v, u in raw_doses.get(key, []) if (n, u) in medians and v > 0]
        a.update({"log_relative_dose": float(np.mean(rel)) if rel else 0.0, "dose_unknown": not rel, "doses": raw_doses.get(key, [])})
    arms = {k: a for k, a in arms.items() if "phase" in a}
    terminology = UmlsTerminology(cache_path=Path("data/cache/umls_links.json"))
    observations, thresholds = study_event_tables(Path(raw_dir), arms, terminology)
    terminology.save()
    thr = {t["nct_id"]: t for t in thresholds}
    for a in arms.values():
        t = thr.get(a["nct_id"], {})
        a.update({"threshold": t.get("report_threshold"), "serious_table": t.get("serious_table", False), "other_table": t.get("non_serious_table", False)})
    return list(arms.values()), observations


# ----------------------------------------------------------------------------- model


def covariate_levels(arms: list[dict]) -> dict:
    return {"classes": sorted({c for a in arms for c in a["classes"]}), "phase": sorted({a["phase"] for a in arms}),
            "family": sorted({a["disease_family"] for a in arms})}


def design(arms: list[dict], levels: dict, covariates: bool = True) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Design matrix, column names and the prior standard deviation of each column."""
    cols = ["intercept"] + [f"class={c}" for c in levels["classes"]] + ["unclassified_agent"]
    sd = [10.0] + [1.5] * len(levels["classes"]) + [1.0]
    if covariates:
        cols += ["pediatric", "log_relative_dose", "dose_unknown"] + [f"phase={p}" for p in levels["phase"][1:]] + [f"family={f}" for f in levels["family"]]
        sd += [0.7, 0.7, 0.5] + [0.5] * (len(levels["phase"]) - 1) + [0.5] * len(levels["family"])
    X = np.zeros((len(arms), len(cols)))
    idx = {c: i for i, c in enumerate(cols)}
    for r, a in enumerate(arms):
        X[r, 0] = 1
        for c in a["classes"]:
            if f"class={c}" in idx:
                X[r, idx[f"class={c}"]] = 1
        X[r, idx["unclassified_agent"]] = float(a["unclassified_agent"])
        if covariates:
            X[r, idx["pediatric"]] = float(a["pediatric"])
            X[r, idx["log_relative_dose"]] = a["log_relative_dose"]
            X[r, idx["dose_unknown"]] = float(a["dose_unknown"])
            if f"phase={a['phase']}" in idx:
                X[r, idx[f"phase={a['phase']}"]] = 1
            if f"family={a['disease_family']}" in idx:
                X[r, idx[f"family={a['disease_family']}"]] = 1
    return X, cols, np.array(sd)


def event_data(arms: list[dict], obs: dict, seriousness: str) -> tuple[list[int], np.ndarray, np.ndarray, np.ndarray]:
    """Rows (arm index), y, n and the censoring flag for one event: listed counts are exact; an unlisted serious event
    with a serious table is an exact zero; an unlisted non-serious event is censored at the study threshold."""
    rows, y, n, cens = [], [], [], []
    for i, a in enumerate(arms):
        o = obs.get((a["nct_id"], a["group"]))
        if o is not None:
            rows.append(i), y.append(o[0]), n.append(o[1]), cens.append(False)
        elif seriousness == "serious" and a["serious_table"] and a.get("n"):
            rows.append(i), y.append(0), n.append(a["n"]), cens.append(False)
        elif seriousness == "non_serious" and a["other_table"] and a.get("n") and a["threshold"] is not None:
            rows.append(i), y.append(math.floor(a["threshold"] * a["n"] / 100)), n.append(a["n"]), cens.append(True)
    return rows, np.array(y), np.array(n), np.array(cens)


def fit_event(X: np.ndarray, sd: np.ndarray, y: np.ndarray, n: np.ndarray, cens: np.ndarray) -> dict:
    ex, ce = ~cens, cens

    def f(beta):
        eta = X @ beta
        p = special.expit(eta)
        ll = np.sum(y[ex] * eta[ex] - n[ex] * np.logaddexp(0, eta[ex]))
        g = X[ex].T @ (y[ex] - n[ex] * p[ex])
        if ce.any():               # log P(Y <= c) = log I_{1-p}(n - c, c + 1)
            a_, b_ = n[ce] - y[ce], y[ce] + 1
            q = 1 - p[ce]
            logF = np.log(np.clip(special.betainc(a_, b_, q), 1e-300, 1))
            ll += logF.sum()
            lognum = a_ * np.log(np.clip(q, 1e-300, 1)) + b_ * np.log(np.clip(p[ce], 1e-300, 1)) - special.betaln(a_, b_)
            g += X[ce].T @ (-np.exp(lognum - logF))
        prior = 0.5 * np.sum((beta / sd) ** 2)
        return -(ll - prior), -(g - beta / sd ** 2)
    res = optimize.minimize(f, np.zeros(X.shape[1]), jac=True, method="L-BFGS-B", options={"maxiter": 500})
    beta = res.x
    p = special.expit(X @ beta)
    W = np.where(ex, n * p * (1 - p), 0.25 * n * p * (1 - p))        # censored arms carry less information (approximation)
    H = X.T @ (X * W[:, None]) + np.diag(1 / sd ** 2)
    se = np.sqrt(np.clip(np.diag(np.linalg.pinv(H)), 0, None))
    # between-trial spread tau on the logit scale: maximum marginal likelihood of the exact arms under
    # y ~ Binomial(n, expit(x'beta + tau z)), z ~ N(0, 1), with the linear predictor fixed at its fit (Gauss-Hermite)
    informative = int((ex & (y > 0)).sum())
    tau = marginal_tau(X[ex] @ beta, y[ex], n[ex]) if informative >= 10 else None
    return {"beta": beta.tolist(), "se": se.tolist(), "tau": tau, "converged": bool(res.success), "arms": len(y), "exact_arms": int(ex.sum()),
            "informative_arms": informative}


_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(24)
_GH_W = _GH_W / _GH_W.sum()


def marginal_tau(eta: np.ndarray, y: np.ndarray, n: np.ndarray) -> float:
    logc = special.gammaln(n + 1) - special.gammaln(y + 1) - special.gammaln(n - y + 1)

    def nll(log_tau):
        e = eta[:, None] + math.exp(log_tau) * _GH_X[None, :]
        ll = logc[:, None] + y[:, None] * e - n[:, None] * np.logaddexp(0, e)
        return -float(np.sum(special.logsumexp(ll, axis=1, b=_GH_W[None, :])))
    res = optimize.minimize_scalar(nll, bounds=(math.log(0.01), math.log(5.0)), method="bounded")
    return float(math.exp(res.x))


def _fit_job(args):
    key, X, sd, y, n, cens = args
    return key, fit_event(X, sd, y, n, cens)


def predictive(fit: dict, x: np.ndarray, tau_default: float, scale: float = 1.0) -> dict:
    """Logit-normal predictive rate; `scale` widens the spread by the factor calibrated on held-out trials."""
    tau = fit["tau"] if fit["tau"] is not None else tau_default
    mu = float(x @ np.array(fit["beta"]))
    var = float(np.sum((x * np.array(fit["se"])) ** 2)) + tau ** 2
    return {"logit_mu": mu, "logit_sigma": scale * math.sqrt(var)}


SCALES = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0, 2.25, 2.5, 3.0)


def calibrate_scale(arms: list[dict], obs: list[dict], fits: dict, meta: dict, target: float = 0.90, sample: int = 4000, seed: int = 0) -> dict:
    """The smallest spread factor whose 90% predictive count intervals contain `target` of the listed counts of the
    calibration trials (trials used neither for fitting nor for the reported validation)."""
    X, _, _ = design(arms, meta["levels"], True)
    tau = float(np.median([f["tau"] for f in fits.values() if f["tau"] is not None] or [1.0]))
    index = {(a["nct_id"], a["group"]): i for i, a in enumerate(arms)}
    rows = [(index[tuple(o["arm"])], (o["event"], o["seriousness"]), o["y"], o["n"]) for o in obs
            if tuple(o["arm"]) in index and (o["event"], o["seriousness"]) in fits and arms[index[tuple(o["arm"])]]["classes"]]
    rows = random.Random(seed).sample(rows, min(sample, len(rows)))
    coverage = {}
    for sc in SCALES:
        hits = []
        for i, key, y, n in rows:
            lo, hi = _interval(predictive(fits[key], X[i], tau, sc), n)
            hits.append(lo <= y <= hi)
        coverage[sc] = float(np.mean(hits)) if hits else None
        if coverage[sc] is not None and coverage[sc] >= target:
            break
    chosen = next((sc for sc, c in coverage.items() if c is not None and c >= target), SCALES[-1])
    return {"scale": chosen, "target": target, "coverage_by_scale": {f"{k:g}": v for k, v in coverage.items()}, "listed_counts": len(rows)}


def _log_pred_prob(dist: dict, y: int, n: int, nodes: int = 64) -> float:
    z = stats.norm.ppf((np.arange(nodes) + 0.5) / nodes)
    p = special.expit(dist["logit_mu"] + dist["logit_sigma"] * z)
    return float(np.log(np.mean(stats.binom.pmf(y, n, p)) + 1e-300))


def _interval(dist: dict, n: int, nodes: int = 64) -> tuple[int, int]:
    z = stats.norm.ppf((np.arange(nodes) + 0.5) / nodes)
    p = special.expit(dist["logit_mu"] + dist["logit_sigma"] * z)
    cdf = np.cumsum(stats.binom.pmf(np.arange(n + 1)[None, :], n, p[:, None]).mean(axis=0))
    return int(np.searchsorted(cdf, 0.05)), int(np.searchsorted(cdf, 0.95))


def fit_all(arms: list[dict], observations: list[dict], events: list[tuple], covariates: bool, workers: int) -> tuple[dict, dict]:
    levels = covariate_levels(arms)
    X, cols, sd = design(arms, levels, covariates)
    by_event: dict[tuple, dict] = defaultdict(dict)
    for o in observations:
        by_event[(o["event"], o["seriousness"])][o["arm"]] = (o["y"], o["n"])
    jobs = []
    for key in events:
        rows, y, n, cens = event_data(arms, by_event.get(key, {}), key[1])
        if len(rows) >= 10 and (y[~cens] > 0).sum() >= 2:
            jobs.append((key, X[rows], sd, y, n, cens))
    with ProcessPoolExecutor(workers) as pool:
        fits = dict(pool.map(_fit_job, jobs, chunksize=8))
    return fits, {"levels": levels, "cols": cols, "covariates": covariates}


def _arm_sizes(arms: list[dict], observations: list[dict]) -> None:
    n = {}
    for o in observations:
        n[o["arm"]] = max(n.get(o["arm"], 0), o["n"])
    for a in arms:
        a["n"] = n.get((a["nct_id"], a["group"]))


def build(raw_dir: Path, holdout_file: Path, family_map_file: Path, class_map_file: Path, v2_toxicity: Path, out_dir: Path,
          created: str, workers: int = 6, min_studies: int = 3, validation_share: float = 0.2, seed: int = 20260927) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from .planning.operational import holdout_ids

    holdout = holdout_ids(holdout_file)
    class_map = json.loads(Path(class_map_file).read_text(encoding="utf-8"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = out_dir / "arm_table.json"               # the registry parse and term linking take long; reuse for the same inputs
    key = {"holdout": sorted(h for h in holdout if (Path(raw_dir) / f"{h}.json").exists()),       # holdouts that are in the corpus "class_map": hashlib.sha256(Path(class_map_file).read_bytes()).hexdigest(),
           "family_map": hashlib.sha256(Path(family_map_file).read_bytes()).hexdigest(), "raw_files": len(list(Path(raw_dir).glob("*.json")))}
    cached = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
    if cached and cached["key"] == key:
        arms, observations = cached["arms"], [{**o, "arm": tuple(o["arm"])} for o in cached["observations"]]
    else:
        arms, observations = arm_table(raw_dir, holdout, family_map_file, class_map)
        cache.write_text(json.dumps({"key": key, "arms": arms, "observations": observations}, default=list), encoding="utf-8")
    _arm_sizes(arms, observations)
    arms = [a for a in arms if a.get("n")]
    studies: dict[tuple, set] = defaultdict(set)
    for o in observations:
        studies[(o["event"], o["seriousness"])].add(o["nct_id"])
    events = sorted(k for k, v in studies.items() if len(v) >= min_studies)

    # whole trials held out: 60% fit, 20% calibrate the spread, 20% report (neither used for fitting nor for calibrating)
    ncts = sorted({a["nct_id"] for a in arms})
    held = random.Random(seed).sample(ncts, int(2 * validation_share * len(ncts)))
    calib, test = set(held[::2]), set(held[1::2])
    train_arms = [a for a in arms if a["nct_id"] not in test and a["nct_id"] not in calib]
    test_arms = [a for a in arms if a["nct_id"] in test]
    train_obs = [o for o in observations if o["nct_id"] not in test and o["nct_id"] not in calib]
    fits_cov, meta_cov = fit_all(train_arms, train_obs, events, True, workers)
    fits_cls, meta_cls = fit_all(train_arms, train_obs, events, False, workers)
    v2 = {}
    for r in pq.read_table(v2_toxicity, columns=["class_signature", "event", "seriousness", "status", "population_rate"]).to_pylist():
        if r["status"] == "PUBLISHED":
            q = json.loads(r["population_rate"])
            v2[(r["event"], r["seriousness"], r["class_signature"])] = q
    calibration = calibrate_scale([a for a in arms if a["nct_id"] in calib], [o for o in observations if o["nct_id"] in calib],
                                  fits_cov, meta_cov, seed=seed)
    validation = _validate(test_arms, [o for o in observations if o["nct_id"] in test], fits_cov, meta_cov, fits_cls, meta_cls, v2,
                           train_arms, train_obs, seed, scale=calibration["scale"])

    fits, meta = fit_all(arms, observations, events, True, workers)
    taus = [f["tau"] for f in fits.values() if f["tau"] is not None]
    tau_default = float(np.median(taus)) if taus else 1.0
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [{"event": k[0], "seriousness": k[1], "beta": json.dumps(f["beta"]), "se": json.dumps(f["se"]), "tau": f["tau"],
             "arms": f["arms"], "exact_arms": f["exact_arms"], "converged": f["converged"]} for k, f in sorted(fits.items())]
    pq.write_table(pa.Table.from_pylist(rows), out_dir / "event_models.parquet")
    arm_rows = [{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in a.items()} for a in arms]
    pq.write_table(pa.Table.from_pylist(arm_rows), out_dir / "arms.parquet")
    manifest = {"safety_asset_version": SAFETY3_VERSION, "created": created, "arms": len(arms), "studies": len(ncts),
                "holdout_excluded": len(holdout), "events_modelled": len(fits), "events_considered": len(events),
                "design": {"cols": meta["cols"], "levels": meta["levels"]}, "tau_default": tau_default,
                "dose": {"arms_with_dose": sum(not a["dose_unknown"] for a in arms), "agents_with_reference_dose": None},
                "sigma_scale": calibration["scale"], "calibration": calibration, "validation": validation,
                "split": {"fit": "60% of trials", "calibrate": "20%", "report": "20%"}}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _signature(a: dict) -> str:
    return "+".join(sorted(set(a["classes"]) | ({"other"} if a["unclassified_agent"] else set()))) or "unclassified"


def _validate(test_arms, test_obs, fits_cov, meta_cov, fits_cls, meta_cls, v2, train_arms, train_obs, seed, zero_sample: int = 20000,
              scale: float = 1.0) -> dict:
    """Held-out trials: listed counts, plus a sample of the exact zeros (unlisted serious events in a study with a serious
    table), scored under V3, V3 without covariates, a class-signature pooled rate fitted on the TRAINING trials only (the
    fair V2-style baseline), and the published V2 rate (fitted on all trials including the held-out ones: in-sample)."""
    Xc, _, _ = design(test_arms, meta_cov["levels"], True)
    Xk, _, _ = design(test_arms, meta_cls["levels"], False)
    tau_c = float(np.median([f["tau"] for f in fits_cov.values() if f["tau"] is not None] or [1.0]))
    tau_k = float(np.median([f["tau"] for f in fits_cls.values() if f["tau"] is not None] or [1.0]))
    # training class-signature pooled rates per event
    train_sig = {(a["nct_id"], a["group"]): _signature(a) for a in train_arms}
    pooled: dict[tuple, list] = defaultdict(lambda: [0, 0])
    for o in train_obs:
        s = train_sig.get(tuple(o["arm"]))
        if s:
            acc = pooled[(o["event"], o["seriousness"], s)]
            acc[0] += o["y"]
            acc[1] += o["n"]
    exposure: dict[tuple, int] = defaultdict(int)      # serious-table exposure of the signature (unlisted serious = 0)
    for a in train_arms:
        if a["serious_table"] and a.get("n"):
            exposure[_signature(a)] += a["n"]
    index = {(a["nct_id"], a["group"]): i for i, a in enumerate(test_arms)}
    rows = [(o["event"], o["seriousness"], index.get(tuple(o["arm"])), o["y"], o["n"], True) for o in test_obs]
    listed = {(o["event"], o["seriousness"], tuple(o["arm"])) for o in test_obs}
    zeros = [(e, "serious", i, 0, a["n"], False) for (e, s) in fits_cov if s == "serious" for i, a in enumerate(test_arms)
             if a["serious_table"] and a.get("n") and (e, "serious", (a["nct_id"], a["group"])) not in listed]
    rng = random.Random(seed)
    zeros = rng.sample(zeros, min(zero_sample, len(zeros)))
    names = ("v3", "v3_uncalibrated", "v3_classes_only", "signature_pooled_training", "v2_published_in_sample")
    res = {k: {"listed": [], "zeros": []} for k in names}
    cover = {k: {"listed": [], "zeros": []} for k in names}
    for event, ser, i, y, n, is_listed in rows + zeros:
        key = (event, ser)
        if i is None or key not in fits_cov or key not in fits_cls:
            continue
        a = test_arms[i]
        sig = _signature(a)
        q = v2.get((event, ser, sig))
        pool = pooled.get((event, ser, sig))
        if q is None or not a["classes"] or (ser == "non_serious" and pool is None):
            continue                                     # the same observations for every model
        ys, ns = (pool or [0, 0])
        if ser == "serious":
            ns = max(ns, exposure.get(sig, 0))
        tau_e = fits_cov[key]["tau"] if fits_cov[key]["tau"] is not None else tau_c
        dists = {"v3": predictive(fits_cov[key], Xc[i], tau_c, scale), "v3_uncalibrated": predictive(fits_cov[key], Xc[i], tau_c),
                 "v3_classes_only": predictive(fits_cls[key], Xk[i], tau_k),
                 "signature_pooled_training": {"logit_mu": float(special.logit((ys + 0.5) / (ns + 1))), "logit_sigma": tau_e},
                 "v2_published_in_sample": {"logit_mu": float(special.logit(np.clip(q["median"], 1e-4, 1 - 1e-4))),
                                            "logit_sigma": float((special.logit(np.clip(q["q975"], 1e-4, 1 - 1e-4))
                                                                  - special.logit(np.clip(q["q025"], 1e-4, 1 - 1e-4))) / (2 * 1.96))}}
        part = "listed" if is_listed else "zeros"
        for name, d in dists.items():
            res[name][part].append(_log_pred_prob(d, y, n))
            lo, hi = _interval(d, n)
            cover[name][part].append(lo <= y <= hi)
    summary = {}
    for part in ("listed", "zeros"):
        summary[part] = {"count": len(res["v3"][part]),
                         "mean_log_predictive_probability": {k: float(np.mean(v[part])) if v[part] else None for k, v in res.items()},
                         "coverage_90": {k: float(np.mean(v[part])) if v[part] else None for k, v in cover.items()}}
    return {**summary, "note": ("held-out trials (20%); listed counts and a sample of exact zeros (unlisted serious events with a serious table) "
                                "of arms whose regimen has an informative class and a V2 signature rate; the same observations for every model. "
                                "The published V2 rates were fitted on all trials, including these: their score is in-sample.")}


# ----------------------------------------------------------------------------- prediction for a protocol arm


def load(asset_dir: Path) -> dict:
    import pyarrow.parquet as pq

    manifest = json.loads((Path(asset_dir) / "manifest.json").read_text(encoding="utf-8"))
    support_file = Path(asset_dir) / "event_support.json"
    support = json.loads(support_file.read_text(encoding="utf-8")) if support_file.exists() else None
    fits = {(r["event"], r["seriousness"]): {"beta": json.loads(r["beta"]), "se": json.loads(r["se"]), "tau": r["tau"], "arms": r["arms"]}
            for r in pq.read_table(Path(asset_dir) / "event_models.parquet").to_pylist()}
    return {"manifest": manifest, "fits": fits, "support": support}


def supported(asset: dict, event: str, seriousness: str, arm: dict, min_studies: int = 2) -> bool:
    """An event is predicted for an arm only when trials of the same disease family, or with the same drug-class
    combination, reported it (at least `min_studies` studies): the additive class model is not extrapolated to
    events never seen in the arm's context."""
    s = (asset.get("support") or {}).get(f"{event}|{seriousness}")
    if asset.get("support") is None:
        return True
    if not s:
        return False
    return s["family"].get(arm["disease_family"], 0) >= min_studies or s["signature"].get("+".join(sorted(arm["classes"])), 0) >= min_studies


def predict_arm(asset: dict, arm: dict, min_rate: float = 0.05) -> dict:
    """Adverse-event rate distributions for one protocol arm: {classes, unclassified_agent, phase, pediatric,
    disease_family, log_relative_dose, dose_unknown}. No informative drug class: UNRESOLVED (no fallback). Events
    without support in the arm's disease family or drug-class combination are not predicted (counted)."""
    if not arm["classes"]:
        return {"status": "UNRESOLVED", "reason": "no agent of the regimen has a pharmacological class in the asset (no fallback to a catch-all group)",
                "events": []}
    levels, cols = asset["manifest"]["design"]["levels"], asset["manifest"]["design"]["cols"]
    unknown = [c for c in arm["classes"] if c not in levels["classes"]]
    X, _, _ = design([arm], levels, True)
    events = []
    unsupported = 0
    for (event, seriousness), fit in asset["fits"].items():
        if not supported(asset, event, seriousness, arm):
            unsupported += 1
            continue
        d = predictive(fit, X[0], asset["manifest"]["tau_default"], asset["manifest"].get("sigma_scale", 1.0))
        rate = float(special.expit(d["logit_mu"]))
        if rate >= min_rate or (seriousness == "serious" and rate >= min_rate / 5):
            events.append({"event": event, "seriousness": seriousness, "rate": rate, **d})
    status = "PARTIAL" if arm["unclassified_agent"] or unknown else "RESOLVED"
    return {"status": status, "classes_without_data": unknown, "covariates": dict(zip(cols, X[0].tolist(), strict=True)),
            "events_without_support_in_context": unsupported,
            "events": sorted(events, key=lambda e: (e["seriousness"], -e["rate"]))}


# ----------------------------------------------------------------------------- evidence support of each event model


def build_support(asset_dir: Path) -> dict:
    """For each (event, seriousness): the number of studies that reported it (at least one patient) per disease family
    and per drug-class combination, from the asset's own arm table. Written to event_support.json."""
    cached = json.loads((Path(asset_dir) / "arm_table.json").read_text(encoding="utf-8"))
    arms = {(a["nct_id"], a["group"]): a for a in cached["arms"]}
    support: dict[str, dict] = {}
    for o in cached["observations"]:
        a = arms.get(tuple(o["arm"]))
        if a is None or not o["y"]:
            continue
        key = f"{o['event']}|{o['seriousness']}"
        entry = support.setdefault(key, {"family": {}, "signature": {}})
        for bucket, value in (("family", a["disease_family"]), ("signature", "+".join(sorted(a["classes"])))):
            entry[bucket].setdefault(value, set()).add(o["nct_id"])
    doc = {k: {b: {v: len(ids) for v, ids in d.items()} for b, d in e.items()} for k, e in support.items()}
    (Path(asset_dir) / "event_support.json").write_text(json.dumps(doc), encoding="utf-8")
    return doc
