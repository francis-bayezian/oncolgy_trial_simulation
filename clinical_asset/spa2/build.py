"""Build Simulation Parameter Asset V2 (Milestone 2): borrowing, survival, censored toxicity,
validation. Inputs are the frozen Clinical Evidence Asset V1 and the frozen Parameter Asset V1
evidence table; neither is modified.
"""

import datetime
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import special, stats

from ..spa.evidence import ASSET, load_frozen_profiles
from ..spa.models import BetaBinomial
from ..terminology import UmlsTerminology
from . import borrow, survival, toxicity
from .hierarchy import fit_hierarchy, predictive
from .taxonomy import regimen_signature
from .. import assets as _assets

V1 = _assets.path("params_v1")
OUT = _assets.path("params_v2")
WORK = Path("data/spa_work")
SEED = 20260926
MODEL_VERSION = "spa-milestone-2.0.0"


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        pq.write_table(pa.table({}), path)
        return
    columns = sorted({k for r in rows for k in r})
    def cell(v):
        if isinstance(v, (dict, list, tuple)):
            return json.dumps(v, default=str)
        if isinstance(v, np.floating):
            return float(v)
        return v
    pq.write_table(pa.table({c: [cell(r.get(c)) for r in rows] for c in columns}), path)


def _q(x: np.ndarray) -> dict:
    q = np.quantile(x, [0.025, 0.5, 0.975])
    return {"median": float(q[1]), "q025": float(q[0]), "q975": float(q[2])}


def _scores(pred: np.ndarray, observed: float) -> dict:
    """Coverage, sharpness and proper scores for one held-out value from predictive draws."""
    q = np.quantile(pred, [0.025, 0.25, 0.5, 0.75, 0.975])
    a = np.abs(pred - observed).mean()
    b = np.abs(pred[:, None] - pred[None, : min(300, pred.size)]).mean()
    return {"covered_95": bool(q[0] <= observed <= q[4]), "covered_50": bool(q[1] <= observed <= q[3]),
            "width_95": float(q[4] - q[0]), "width_50": float(q[3] - q[1]),
            "abs_error": float(abs(q[2] - observed)), "crps": float(a - 0.5 * b)}


# ----------------------------------------------------------------------------- 2A: borrowing


def _fit_and_publish(args: tuple) -> dict:
    key, spec, seed = args
    fitted = borrow.fit_target(spec["group"], spec["target"], spec["records"], seed)
    if fitted["fit"].ess < 100:  # retry with a larger importance sample before judging the fit
        fitted = borrow.fit_target(spec["group"], spec["target"], spec["records"], seed, samples=8000)
    params = borrow.publish_target(spec["group"], spec["target"], fitted, seed)
    status = "PUBLISHED" if fitted["fit"].ess >= 100 else "NOT_PUBLISHED_DIAGNOSTIC_FAILURE"
    for param in params:
        param["status"] = status
    hyper = borrow.hyperparameter_rows(spec["group"], spec["target"], fitted)
    return {"key": key, "params": params, "hyper": hyper, "ess": fitted["fit"].ess}


def _loo_one(args: tuple) -> dict | None:
    """Hold out one study from a target tree; predict one of its arms from the rest."""
    spec, held_study, seed = args
    group, records = spec["group"], spec["records"]
    rest = [r for r in records if r["study"] != held_study]
    held = [r for r in records if r["study"] == held_study]
    if not rest or not held:
        return None
    rule = borrow.RULES["groups"][group]
    levels = rule["levels"]
    centre = 0.0
    if group == "baseline_age":
        centre = float(np.average([r["y"] for r in rest], weights=[1 / r["s2"] for r in rest]))
        rest = [{**r, "y": r["y"] - centre} for r in rest]
    fit = fit_hierarchy(rest, levels, rule["tau_prior_scale"], rule["root_sd"], samples=400, draws=300, seed=seed)
    rng = np.random.default_rng(seed)
    target_arm = held[0]
    path = tuple(target_arm[level] for level in levels)
    depth = levels.index(borrow.PARAMETER_LEVEL[group]) + 1
    leaf_studies = {r["study"] for r in rest if tuple(r[level] for level in levels[:depth]) == path[:depth]}
    theta = predictive(fit, path, rng)
    out = {"group": group, "target": json.dumps(spec["target"], default=str),
           "level": "A" if len(leaf_studies) >= 2 else "B" if len(leaf_studies) == 1 else "C",
           "leaf_other_studies": len(leaf_studies)}
    if group in {"efficacy_proportion", "safety_proportion", "baseline_sex"}:
        n, y = target_arm["n"], target_arm["count"]
        p = special.expit(theta)
        rate_rep = rng.binomial(n, p) / n
        observed = y / n
        out.update(_scores(rate_rep, observed), family="borrowed_logit_normal",
                   log_predictive_density=float(special.logsumexp(stats.binom.logpmf(y, n, p)) - math.log(p.size)),
                   brier=float(observed * (1 - p.mean()) ** 2 + (1 - observed) * p.mean() ** 2))
        # Baselines on the same observation: global pooled rate, and leaf-only beta-binomial (no borrowing).
        pooled = sum(r["count"] for r in rest) / sum(r["n"] for r in rest)
        out["baseline_global"] = _scores(rng.binomial(n, np.full(1000, pooled)) / n, observed)
        leaf_rest = [r for r in rest if r["study"] in leaf_studies and tuple(r[lv] for lv in levels[:depth]) == path[:depth]]
        if leaf_rest:
            bb = BetaBinomial().fit(np.array([r["count"] for r in leaf_rest]), np.array([r["n"] for r in leaf_rest]))
            out["baseline_leaf_only"] = _scores(rng.binomial(n, bb.draws["p_new_study"]) / n, observed)
    else:
        observed = target_arm["y"] - centre if group == "baseline_age" else target_arm["y"]
        rep = rng.normal(theta, math.sqrt(target_arm["s2"]))
        out.update(_scores(rep, observed), family="borrowed_normal" if group == "baseline_age" else "borrowed_log_ratio",
                   log_predictive_density=float(np.log(np.mean(stats.norm.pdf(observed, theta, math.sqrt(target_arm["s2"]))) + 1e-300)))
    return out


# ----------------------------------------------------------------------------- 2B: survival


def _survival_context(args: tuple) -> dict:
    key, cons, priors, context, seed, pass_no, tau = args
    rng = np.random.default_rng(seed)
    fits = []
    for family, spec in survival.FAMILIES.items():
        prior = (priors.get((context["endpoint"], family, context["disease_family"]))
                 or priors.get((context["endpoint"], family, "*")) or (*spec["default_prior"], 0))
        fit = survival.fit_family(family, cons, prior[:2], rng, tau=tau)
        fit["prior_source"] = ("disease_family" if (context["endpoint"], family, context["disease_family"]) in priors
                               else "endpoint" if (context["endpoint"], family, "*") in priors else "default")
        fits.append(fit)
    return {"key": key, "context": context, "cons": cons, "fits": fits, "pass": pass_no}


def _survival_loo(args: tuple) -> dict:
    cons, held_index, priors, context, identifiability, seed, tau = args
    rest = [c for i, c in enumerate(cons) if i != held_index]
    held = cons[held_index]
    rng = np.random.default_rng(seed)
    fits = []
    for family, spec in survival.FAMILIES.items():
        prior = (priors.get((context["endpoint"], family, context["disease_family"]))
                 or priors.get((context["endpoint"], family, "*")) or spec["default_prior"])
        fits.append(survival.fit_family(family, rest, prior[:2], rng, draws=600, tau=tau))
    ev = np.array([f["log_evidence"] for f in fits])
    w = np.exp(ev - ev.max())
    w /= w.sum()
    choice = rng.choice(len(fits), size=600, p=w)
    preds = []
    for idx, f in enumerate(fits):
        take = int((choice == idx).sum())
        if not take:
            continue
        loc, shape = f["loc"][:take], f["shape"][:take]
        if held["kind"] == "median":
            with np.errstate(divide="ignore"):
                preds.append(np.log(survival.median(f["family"], loc, shape)))
        else:
            preds.append(np.log(-np.log(np.clip(survival.survival(f["family"], held["t"], loc, shape), 1e-12, 1 - 1e-12))))
    pred = np.concatenate(preds)
    pred = pred[np.isfinite(pred)]
    pred = rng.normal(pred, math.sqrt(held["se"] ** 2 + tau**2))
    return {"family": "parametric_survival_bma", "kind": held["kind"], "identifiability": identifiability,
            **_scores(pred, held["y"])}


# ----------------------------------------------------------------------------- 2C: toxicity


def _toxicity_context(args: tuple) -> dict:
    key, spec, seed = args
    exact = [(y, n) for _, y, n in spec["exact"]]
    censored = [(c, n) for _, c, n in spec["censored"]]
    fit = toxicity.fit_censored(exact, censored, seed)
    naive = toxicity.fit_censored(exact, [], seed) if censored else fit  # identical when nothing is censored
    regimens: dict[str, dict] = defaultdict(lambda: {"exact": [], "censored": []})
    for arm, y, n in spec["exact"]:
        regimens[spec["arm_regimen"][arm]]["exact"].append((y, n))
    for arm, c, n in spec["censored"]:
        regimens[spec["arm_regimen"][arm]]["censored"].append((c, n))
    regimen_rows = []
    for regimen, obs in regimens.items():
        draws = toxicity.regimen_posterior(fit, obs["exact"], obs["censored"], seed)
        regimen_rows.append({"regimen": regimen, "posterior": _q(draws), "exact_arms": len(obs["exact"]),
                             "censored_arms": len(obs["censored"]),
                             "observed_rate": (sum(y for y, _ in obs["exact"]) / sum(n for _, n in obs["exact"])) if obs["exact"] else None})
    loo = []
    if spec.get("validate") and len(spec["exact"]) >= 3:
        rng = np.random.default_rng(seed)
        for held in rng.choice(len(spec["exact"]), size=min(2, len(spec["exact"])), replace=False):
            _, y, n = spec["exact"][held]
            rest = [(yy, nn) for i, (_, yy, nn) in enumerate(spec["exact"]) if i != held]
            for label, cens in (("censored_model", censored), ("naive_observed_only", [])):
                f = toxicity.fit_censored(rest, cens, seed, draws=600)
                rep = rng.binomial(n, f["new_study"]) / n
                loo.append({"model": label, **_scores(rep, y / n)})
    return {"key": key, "class_fit": fit, "naive": naive, "regimens": regimen_rows, "loo": loo,
            "n_exact": len(exact), "n_censored": len(censored)}


def _toxicity_validate(args: tuple) -> list[dict]:
    """Hold out arms of every kind. An exact arm is scored on its rate; a censored arm (event not
    listed, so below the study's threshold) is scored by the predictive probability of Y <= c.
    A model fitted only to listed arms inherits their selection and puts too little mass below
    the threshold."""
    _key, spec, seed = args
    rng = np.random.default_rng(seed)
    arms = [("exact", a, y, n) for a, y, n in spec["exact"]] + [("censored", a, c, n) for a, c, n in spec["censored"]]
    out = []
    for held in rng.choice(len(arms), size=min(4, len(arms)), replace=False):
        kind, arm, value, n = arms[held]
        exact = [(y, nn) for a, y, nn in spec["exact"] if a != arm]
        censored = [(c, nn) for a, c, nn in spec["censored"] if a != arm]
        if not exact:
            continue
        for label, cens in (("censored_model", censored), ("naive_observed_only", [])):
            fit = toxicity.fit_censored(exact, cens, seed, draws=600)
            if kind == "exact":
                out.append({"model": label, "held_out_kind": "exact", **_scores(rng.binomial(n, fit["new_study"]) / n, value / n)})
            else:
                prob = float(stats.binom.cdf(value, n, fit["new_study"]).mean())
                out.append({"model": label, "held_out_kind": "censored", "prob_below_threshold": prob})
    return out


# ----------------------------------------------------------------------------- orchestration


AGE_UNITS = {"year": 1.0, "years": 1.0, "month": 1 / 12, "months": 1 / 12, "week": 1 / 52.1775, "weeks": 1 / 52.1775,
             "day": 1 / 365.25, "days": 1 / 365.25}


def age_factors(raw_dir: Path) -> dict[str, float | None]:
    factors: dict[str, float | None] = {}
    for path in raw_dir.glob("NCT*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for m in raw.get("resultsSection", {}).get("baselineCharacteristicsModule", {}).get("measures", []):
            if m.get("title") == "Age, Continuous":
                factors[path.stem] = AGE_UNITS.get(str(m.get("unitOfMeasure") or "").strip().casefold())
    return factors


def build(workers: int = 6, loo_per_level: int = 40, stages: tuple[str, ...] = ("borrowing", "toxicity", "survival")) -> dict:
    profiles = load_frozen_profiles()
    previous = json.loads((OUT / "manifest.json").read_text(encoding="utf-8")) if (OUT / "manifest.json").exists() else {}
    v1_manifest = json.loads((V1 / "manifest.json").read_text(encoding="utf-8"))
    rows = pq.read_table(V1 / "evidence_table.parquet").to_pylist()
    families = json.loads((WORK / "disease_families.json").read_text(encoding="utf-8"))
    classes = json.loads((WORK / "drug_classes.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}

    # ---------------------------------------------------------------- 2A borrowing
    factors = age_factors(_assets.path("raw_ctgov"))
    report["age_unit_conversions"] = {str(k): v for k, v in factors.items() if v != 1.0}
    targets = borrow.build_records(rows, families, classes, factors)
    if "borrowing" not in stages:
        targets = {}
    jobs = [(k, spec, SEED + i) for i, (k, spec) in enumerate(sorted(targets.items(), key=lambda kv: str(kv[0])))]
    params, hyper = [], []
    ess_low = 0
    with ProcessPoolExecutor(workers) as pool:
        for result in pool.map(_fit_and_publish, jobs, chunksize=4):
            params.extend(result["params"])
            hyper.extend(result["hyper"])
            ess_low += result["ess"] < 100
            if result["ess"] < 100:
                print(json.dumps({"stage": "borrowing", "low_ess_target": str(result["key"])[:120]}), flush=True)
    draw_rows = []
    index_rows = []
    for p in params:
        d = p.pop("draws")
        for i in range(len(d["hierarchical"])):
            draw_rows.append({"parameter_id": p["parameter_id"], "draw": i, "hierarchical": float(d["hierarchical"][i]),
                              "future_study": float(d["future_study"][i])})
        index_rows.append({
            "parameter_id": p["parameter_id"], "status": p.get("status", "PUBLISHED"), "group": p["group"], **{f"context_{k}": v for k, v in p["context"].items()},
            **{f"target_{k}": v for k, v in p["target"].items()}, "level": p["support"]["level"],
            "studies": p["support"]["studies"], "arms": p["support"]["arms"], "total_N": p["support"]["total_N"],
            "within_study_median": p["within_study_posterior"]["median"],
            "within_study_q025": p["within_study_posterior"]["q025"], "within_study_q975": p["within_study_posterior"]["q975"],
            "hierarchical_median": p["hierarchical_posterior"]["median"], "hierarchical_q025": p["hierarchical_posterior"]["q025"],
            "hierarchical_q975": p["hierarchical_posterior"]["q975"], "future_study_q025": p["future_study_predictive"]["q025"],
            "future_study_median": p["future_study_predictive"]["median"], "future_study_q975": p["future_study_predictive"]["q975"],
            "shrinkage_standardised_shift": p["shrinkage"]["standardised_shift"],
            "heterogeneity_source": p["heterogeneity"]["source"],
        })
    if "borrowing" in stages:
        with open(OUT / "parameter_index.jsonl", "w", encoding="utf-8") as handle:
            for p in params:
                handle.write(json.dumps(p, default=str) + "\n")
        _write(OUT / "parameter_index.parquet", index_rows)
    if "borrowing" in stages:
        _write(OUT / "posterior_draws" / "borrowed_parameters.parquet", draw_rows)
    for level_name, file_name in (("disease", "disease_hyperparameters"), ("disease_family", "disease_family_hyperparameters"),
                                  ("class_signature", "treatment_class_hyperparameters"), ("modality", "modality_hyperparameters"),
                                  ("regimen", "regimen_hyperparameters"), ("setting", "setting_hyperparameters")):
        if "borrowing" in stages:
            _write(OUT / "hierarchy" / f"{file_name}.parquet", [h for h in hyper if h["level"] == level_name])
    _write(OUT / "hierarchy" / "disease_family_map.parquet",
           [{"disease": k, "disease_family": v["label"], "confidence": v["confidence"]} for k, v in families.items()])
    _write(OUT / "hierarchy" / "drug_class_map.parquet",
           [{"intervention": k, "drug_class": v["label"], "confidence": v["confidence"]} for k, v in classes.items()])
    print(json.dumps({"stage": "borrowing", "parameters": len(params)}), flush=True)
    report["borrowing"] = previous.get("borrowing", {}) if "borrowing" not in stages else {"targets": len(targets), "parameters": len(params),
                           "withheld_low_hyperparameter_ess": sum(p.get("status") != "PUBLISHED" for p in params),
                           "by_level": dict(Counter(p["support"]["level"] for p in params)),
                           "by_group": dict(Counter(p["group"] for p in params)),
                           "targets_with_tau_ess_below_100": ess_low}

    # LOO under borrowing: stratified sample of held-out studies.
    rng = random.Random(SEED)
    loo_jobs = []
    for level_bucket in ("A", "B", "C"):
        for group in ("efficacy_proportion", "safety_proportion", "baseline_sex", "baseline_age", "relative_effect"):
            candidates = []
            for spec in targets.values():
                if spec["group"] != group or len({r["study"] for r in spec["records"]}) < 2:
                    continue
                depth = borrow.RULES["groups"][group]["levels"].index(borrow.PARAMETER_LEVEL[group]) + 1
                by_node = defaultdict(set)
                for r in spec["records"]:
                    by_node[tuple(r[lv] for lv in borrow.RULES["groups"][group]["levels"][:depth])].add(r["study"])
                for studies in by_node.values():
                    others = len(studies) - 1
                    bucket = "A" if others >= 2 else "B" if others == 1 else "C"
                    if bucket == level_bucket:
                        candidates.extend((spec, s) for s in studies)
            for spec, study in rng.sample(candidates, min(loo_per_level, len(candidates))):
                loo_jobs.append((spec, study, SEED + len(loo_jobs)))
    print(json.dumps({"stage": "borrowing_loo", "jobs": len(loo_jobs)}), flush=True)
    if "borrowing" not in stages:
        loo_jobs = []
    loo = []
    with ProcessPoolExecutor(workers) as pool:
        for result in pool.map(_loo_one, loo_jobs, chunksize=2):
            if result:
                loo.append(result)
    print(json.dumps({"stage": "borrowing_loo", "done": len(loo)}), flush=True)

    # ---------------------------------------------------------------- 2C toxicity
    arm_context = {}
    for profile in profiles:
        if profile["profile_type"] in {"randomized_arm", "study_arm", "treatment_sequence", "result_group"}:
            t = profile.get("treatment", {})
            comps = t.get("interventions") or ([t["drug"]] if t.get("drug") else [])
            cls, mod = regimen_signature(comps, classes) if comps else ("unclassified", "unclassified")
            arm_context[(profile["source"]["nct"], profile["source"]["registry_group"])] = {
                "class_signature": cls, "modality": mod, "regimen": t.get("regimen") or "unspecified"}
    terminology = UmlsTerminology(cache_path=Path("data/cache/umls_links.json"))
    observations, thresholds = toxicity.study_event_tables(_assets.path("raw_ctgov"), arm_context, terminology)
    terminology.save()
    contexts = toxicity.build_contexts(observations, arm_context)
    validation_keys = random.Random(SEED + 1).sample(
        [k for k, v in contexts.items() if v["exact"] and len(v["exact"]) + len(v["censored"]) >= 4 and v["censored"]],
        k=300)
    with ProcessPoolExecutor(workers) as pool:
        tox_validation = [x for chunk in pool.map(_toxicity_validate, [(k, contexts[k], SEED + i) for i, k in enumerate(validation_keys)], chunksize=4) for x in chunk]
    print(json.dumps({"stage": "toxicity_validation", "held_out": len(tox_validation)}), flush=True)
    if "toxicity" not in stages:
        contexts = {}
    tox_jobs = []
    eligible = [k for k, v in contexts.items() if len(v["exact"]) >= 3 and v["censored"]]
    validate = set(random.Random(SEED).sample(eligible, min(300, len(eligible))))
    for i, (key, spec) in enumerate(sorted(contexts.items())):
        spec = {**spec, "validate": key in validate,
                "arm_regimen": {a: arm_context[a]["regimen"] for a, _, _ in spec["exact"] + spec["censored"]}}
        tox_jobs.append((key, spec, SEED + i))
    print(json.dumps({"stage": "toxicity", "contexts": len(tox_jobs), "validated": len(validate)}), flush=True)
    tox_rows, tox_regimen_rows, tox_loo = [], [], []
    with ProcessPoolExecutor(workers) as pool:
        for done, r in enumerate(pool.map(_toxicity_context, tox_jobs, chunksize=64), 1):
            if done % 5000 == 0:
                print(json.dumps({"stage": "toxicity", "done": done}), flush=True)
            event, seriousness, cls = r["key"]
            pid = hashlib.sha1(json.dumps(["toxicity", event, seriousness, cls]).encode()).hexdigest()[:16]
            tox_rows.append({
                "parameter_id": pid, "event": event, "seriousness": seriousness, "class_signature": cls,
                "exact_arms": r["n_exact"], "censored_arms": r["n_censored"],
                "population_rate": _q(r["class_fit"]["m"]), "future_study": _q(r["class_fit"]["new_study"]),
                "naive_observed_only_rate": _q(r["naive"]["m"]),
                "censoring_shift": float(np.median(r["class_fit"]["m"]) - np.median(r["naive"]["m"])),
                "grid_edge_mass": r["class_fit"]["edge"],
                "likelihood": "exact + left-censored below reporting threshold" if seriousness == "non_serious"
                              else "exact (unlisted serious events are zero)",
            })
            for reg in r["regimens"]:
                tox_regimen_rows.append({"parameter_id": pid, "event": event, "seriousness": seriousness,
                                         "class_signature": cls, **reg})
            tox_loo.extend({**x, "seriousness": seriousness} for x in r["loo"])
    if "toxicity" in stages:
        for row in tox_rows:
            row["status"] = "PUBLISHED" if row["grid_edge_mass"] <= 0.01 else "NOT_PUBLISHED_DIAGNOSTIC_FAILURE"
        _write(OUT / "toxicity" / "reporting_thresholds.parquet", thresholds)
        _write(OUT / "toxicity" / "censored_toxicity_parameters.parquet", tox_rows)
        _write(OUT / "toxicity" / "censored_toxicity_regimen_parameters.parquet", tox_regimen_rows)
    else:
        # Earlier full toxicity run: apply the publication rule to its stored parameters.
        stored = pq.read_table(OUT / "toxicity" / "censored_toxicity_parameters.parquet").to_pylist()
        for row in stored:
            row["status"] = "PUBLISHED" if row["grid_edge_mass"] <= 0.01 else "NOT_PUBLISHED_DIAGNOSTIC_FAILURE"
        _write(OUT / "toxicity" / "censored_toxicity_parameters.parquet", stored)
    report["toxicity"] = previous.get("toxicity", {}) if "toxicity" not in stages else {
        "event_observations": len(observations), "contexts": len(tox_rows),
        "non_serious_contexts_with_censoring": sum(1 for t in tox_rows if t["seriousness"] == "non_serious" and t["censored_arms"]),
        "median_censoring_shift_non_serious": float(np.median([t["censoring_shift"] for t in tox_rows if t["seriousness"] == "non_serious" and t["censored_arms"]] or [0])),
        "studies_with_known_threshold": sum(1 for t in thresholds if t["report_threshold"] is not None),
        "studies_without_threshold": sum(1 for t in thresholds if t["report_threshold"] is None),
        "contexts_with_grid_edge_over_1pct": sum(1 for t in tox_rows if t["grid_edge_mass"] > 0.01),
    }

    # ---------------------------------------------------------------- 2B survival
    classification = []
    groups: dict[tuple, list[dict]] = defaultdict(list)
    median_groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        fam = r["statistic_family"]
        if fam not in {"median_time", "mean_time", "survival_probability"}:
            continue
        variable = r["variable"]
        if fam in {"median_time", "mean_time"}:
            status = ("used" if fam == "median_time" and variable in survival.ENDPOINTS and r.get("value")
                      else "follow_up_time_not_an_endpoint" if variable == "follow_up"
                      else "mean_time_not_used" if fam == "mean_time"
                      else "endpoint_not_canonical" if variable not in survival.ENDPOINTS
                      else "median_not_reported")
            classification.append({"scientific_observation_id": r["scientific_observation_id"], "variable": variable,
                                   "statistic_family": fam, "status": status})
        if variable not in survival.ENDPOINTS:
            continue
        ctx = borrow.context_fields(r, families, classes)
        key = (variable, ctx["disease_family"], ctx["disease"], ctx["setting"], ctx["regimen"])
        groups[key].append(r)
        median_groups[key].append(r)
    tau, tau_pairs = survival.estimate_tau(median_groups)
    print(json.dumps({"stage": "survival", "tau_study": tau, "pairs": tau_pairs}), flush=True)
    print(json.dumps({"stage": "survival"}), flush=True)
    survival_inputs = {}
    for key, grp in groups.items():
        cons = survival.constraints_for(grp)
        if cons:
            survival_inputs[key] = cons
    priors: dict = {}
    pass1 = [(k, c, {}, {"endpoint": k[0], "disease_family": k[1]}, SEED + i, 1, tau)
             for i, (k, c) in enumerate(survival_inputs.items()) if len({round(x["t"], 1) for x in c}) >= 2]
    with ProcessPoolExecutor(workers) as pool:
        identifiable = [{"endpoint": r["context"]["endpoint"], "disease_family": r["context"]["disease_family"],
                         "families": {f["family"]: f for f in r["fits"]}} for r in pool.map(_survival_context, pass1, chunksize=4)]
    priors = survival.shape_priors(identifiable)
    pass2 = [(k, c, priors, {"endpoint": k[0], "disease_family": k[1]}, SEED + i, 2, tau) for i, (k, c) in enumerate(survival_inputs.items())]
    surv_rows, surv_draws = [], []
    rng = np.random.default_rng(SEED)
    with ProcessPoolExecutor(workers) as pool:
        for r in pool.map(_survival_context, pass2, chunksize=4):
            endpoint, family_name, disease, setting, regimen = r["key"]
            cons, fits = r["cons"], r["fits"]
            ev = np.array([f["log_evidence"] for f in fits])
            distinct = len({round(c["t"], 1) for c in cons})
            if distinct >= 3:
                w = np.exp(ev - ev.max())
                w /= w.sum()
                selection = "bayesian_model_averaging"
            else:
                w = np.full(len(fits), 1 / len(fits))
                selection = "equal_weights (evidence cannot discriminate families)"
            pid = hashlib.sha1(json.dumps(["survival", *r["key"]]).encode()).hexdigest()[:16]
            ident = survival.identifiability(cons)
            surv_rows.append({
                "parameter_id": pid, "endpoint": endpoint, "disease_family": family_name, "disease": disease,
                "setting": setting, "treatment": regimen, "identifiability": ident,
                "constraints": {"medians": sum(c["kind"] == "median" for c in cons),
                                "landmarks": sum(c["kind"] == "landmark" for c in cons), "distinct_times": distinct},
                "studies": len({c["study"] for c in cons}), "total_N": int(sum(c["N"] or 0 for c in cons)),
                "family_weights": {f["family"]: float(wi) for f, wi in zip(fits, w, strict=True)}, "family_selection": selection,
                "shape_prior_source": {f["family"]: f["prior_source"] for f in fits},
                "posterior": {f["family"]: {"log_scale": _q(f["loc"]), "shape": _q(f["shape"])} for f in fits},
                "derived": survival.derived(fits, w, rng),
                "grid_edge_mass_max": max(f["edge"] for f in fits),
                "status": "PUBLISHED" if max(f["edge"] for f in fits) <= 0.01 else "NOT_PUBLISHED_DIAGNOSTIC_FAILURE",
                "tau_study_log_scale": tau,
            })
            for f in fits:
                for i in range(0, len(f["loc"]), 2):
                    surv_draws.append({"parameter_id": pid, "family": f["family"], "draw": i // 2,
                                       "log_scale": float(f["loc"][i]), "shape": float(f["shape"][i])})
    surv_loo_jobs = []
    rng2 = random.Random(SEED)
    multi = [(k, c) for k, c in survival_inputs.items() if len(c) >= 2]
    for k, c in rng2.sample(multi, min(300, len(multi))):
        held = rng2.randrange(len(c))
        ident = survival.identifiability([x for i, x in enumerate(c) if i != held])
        surv_loo_jobs.append((c, held, priors, {"endpoint": k[0], "disease_family": k[1]}, ident, SEED + len(surv_loo_jobs), tau))
    with ProcessPoolExecutor(workers) as pool:
        surv_loo = list(pool.map(_survival_loo, surv_loo_jobs, chunksize=4))
    _write(OUT / "survival" / "survival_evidence_classification.parquet", classification)
    _write(OUT / "survival" / "survival_parameter_index.parquet", surv_rows)
    _write(OUT / "survival" / "survival_draws" / "survival_draws.parquet", surv_draws)
    _write(OUT / "survival" / "shape_priors.parquet",
           [{"endpoint": k[0], "family": k[1], "disease_family": k[2], "mean": v[0], "sd": v[1], "contexts": v[2]} for k, v in priors.items()])
    report["survival"] = {
        "deferred_observations_classified": len(classification),
        "classification": dict(Counter(c["status"] for c in classification)),
        "contexts": len(surv_rows), "identifiability": dict(Counter(r["identifiability"] for r in surv_rows)),
        "shape_priors": len(priors), "contexts_with_grid_edge_over_1pct": sum(r["grid_edge_mass_max"] > 0.01 for r in surv_rows),
        "tau_study_log_scale": tau, "tau_study_pairs": tau_pairs,
    }

    # ---------------------------------------------------------------- validation
    def summarise(items: list[dict], by: str) -> dict:
        out = {}
        for value in sorted({str(i.get(by)) for i in items}):
            sel = [i for i in items if str(i.get(by)) == value]
            out[value] = {
                "held_out": len(sel),
                "coverage_95": float(np.mean([i["covered_95"] for i in sel])),
                "coverage_50": float(np.mean([i["covered_50"] for i in sel])),
                "median_width_95": float(np.median([i["width_95"] for i in sel])),
                "median_width_50": float(np.median([i["width_50"] for i in sel])),
                "mean_abs_error": float(np.mean([i["abs_error"] for i in sel])),
                "mean_crps": float(np.mean([i["crps"] for i in sel])),
                **({"mean_log_predictive_density": float(np.mean([i["log_predictive_density"] for i in sel]))}
                   if all("log_predictive_density" in i for i in sel) else {}),
                **({"mean_brier": float(np.mean([i["brier"] for i in sel]))} if all("brier" in i for i in sel) else {}),
            }
        return out

    proportion_loo = [i for i in loo if "baseline_global" in i]
    comparison = {
        "held_out": len(proportion_loo),
        "hierarchical": {"coverage_95": float(np.mean([i["covered_95"] for i in proportion_loo])),
                         "mean_crps": float(np.mean([i["crps"] for i in proportion_loo])),
                         "median_width_95": float(np.median([i["width_95"] for i in proportion_loo]))},
        "global_pooled_rate_baseline": {"coverage_95": float(np.mean([i["baseline_global"]["covered_95"] for i in proportion_loo])),
                                        "mean_crps": float(np.mean([i["baseline_global"]["crps"] for i in proportion_loo])),
                                        "median_width_95": float(np.median([i["baseline_global"]["width_95"] for i in proportion_loo]))},
    }
    leaf = [i for i in proportion_loo if "baseline_leaf_only" in i]
    if leaf:
        comparison["same_observations_with_leaf_evidence"] = {
            "held_out": len(leaf),
            "hierarchical_mean_crps": float(np.mean([i["crps"] for i in leaf])),
            "leaf_only_beta_binomial_mean_crps": float(np.mean([i["baseline_leaf_only"]["crps"] for i in leaf])),
            "hierarchical_coverage_95": float(np.mean([i["covered_95"] for i in leaf])),
            "leaf_only_coverage_95": float(np.mean([i["baseline_leaf_only"]["covered_95"] for i in leaf])),
        }
    validation_dir = OUT / "validation"
    if not loo and (validation_dir / "loo_metrics.parquet").exists():
        loo = [r for r in pq.read_table(validation_dir / "loo_metrics.parquet").to_pylist() if r.get("group")]
    censored_summary = {}
    for model in ("censored_model", "naive_observed_only"):
        probs = [x["prob_below_threshold"] for x in tox_validation if x["model"] == model and x["held_out_kind"] == "censored"]
        exact = [x for x in tox_validation if x["model"] == model and x["held_out_kind"] == "exact"]
        censored_summary[model] = {
            "censored_held_out": len(probs),
            "mean_prob_below_threshold": float(np.mean(probs)) if probs else None,
            "mean_log_prob_below_threshold": float(np.mean(np.log(np.clip(probs, 1e-12, 1)))) if probs else None,
            "exact_held_out": len(exact),
            "exact_coverage_95": float(np.mean([x["covered_95"] for x in exact])) if exact else None,
            "exact_mean_crps": float(np.mean([x["crps"] for x in exact])) if exact else None,
        }
    tox_loo = [x for x in tox_validation if x["held_out_kind"] == "exact"]
    _write(validation_dir / "loo_metrics.parquet",
           [{k: v for k, v in i.items() if not k.startswith("baseline")} for i in loo] + tox_validation + surv_loo)
    (validation_dir / "calibration_by_level.json").write_text(json.dumps({
        "borrowing_leave_one_study_out": summarise(loo, "level"),
        "survival_leave_one_constraint_out_by_identifiability": summarise(surv_loo, "identifiability"),
    }, indent=1), encoding="utf-8")
    (validation_dir / "calibration_by_family.json").write_text(json.dumps({
        "borrowing": summarise(loo, "family"),
        "borrowing_by_group": summarise(loo, "group"),
        "toxicity_by_model": summarise(tox_loo, "model"),
        "toxicity_censored_and_exact_held_out": censored_summary,
        "survival": summarise(surv_loo, "family"),
        "hierarchical_vs_baselines_proportions": comparison,
    }, indent=1), encoding="utf-8")
    report["validation"] = {"borrowing_held_out": len(loo), "toxicity_held_out": len(tox_validation), "survival_held_out": len(surv_loo),
                            "toxicity_censored_and_exact_held_out": censored_summary,
                            "hierarchical_vs_baselines": comparison}

    manifest = {
        "asset": "Simulation Parameter Asset", "version": "2.0.0", "model_version": MODEL_VERSION,
        "created": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "inputs": {"clinical_evidence_asset": {"path": str(ASSET / "profiles.jsonl"),
                                               "sha256": hashlib.sha256((ASSET / "profiles.jsonl").read_bytes()).hexdigest()},
                   "parameter_asset_v1": {"path": str(V1), "version": v1_manifest["version"]}},
        "configuration": {"hierarchy_rules": borrow.RULES, "survival_tau_study": survival.TAU_STUDY, "seed": SEED},
        **report,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return report
