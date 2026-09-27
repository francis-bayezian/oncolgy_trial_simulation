"""Build Simulation Parameter Asset V3 (Milestone 3).

Inputs (all read-only): Clinical Evidence Asset V1, Parameter Asset V1 evidence table, Parameter
Asset V2 (survival curves, hazard-ratio posteriors, censored toxicity). Output:
data/simulation_parameters_v3/.

Stages
  3A  exact hierarchical binomial for efficacy, safety and sex proportions; leave-one-study-out
      calibration against Milestone 2, global pooling and leaf-only models; random-effect tail
      (normal / Student-t) chosen per group by log predictive density.
  3C  baseline marginals: latent age mean and within-study SD by population class, sex, race and
      ethnicity (stick-breaking binomial trees); dependency registry; sparse Gaussian copula.
  3D  generator specification; baseline backtests on held-out studies.
  3B  hazard-ratio fusion with absolute survival curves; survival backtests.
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

from ..spa.evidence import ASSET
from ..spa2 import borrow as borrow2
from ..spa2.build import age_factors
from ..spa2.hierarchy import fit_hierarchy
from . import baseline, proportions, survival_fusion
from .protocol import (
    BaselineGenerator,
    eligibility_support,
    save_models,
    target_from_binomial,
    target_from_gaussian,
)

V1 = Path("data/simulation_parameters_v1")
V2 = Path("data/simulation_parameters_v2")
OUT = Path("data/simulation_parameters_v3")
WORK = Path("data/spa_work")
RAW = Path("data/raw/ctgov")
SEED = 20260927
MODEL_VERSION = "spa-milestone-3.0.0"
MIN_ESS_SHARE = 0.1  # first attempt; after the retry an absolute effective sample size is required
MIN_ESS_ABSOLUTE = 50
BINOMIAL_GROUPS = ("efficacy_proportion", "safety_proportion", "baseline_sex")


def log(**kw) -> None:
    print(json.dumps(kw, default=str), flush=True)


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
        if isinstance(v, np.integer):
            return int(v)
        return v
    pq.write_table(pa.table({c: [cell(r.get(c)) for r in rows] for c in columns}), path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------- workers


def _fit_publish(args: tuple) -> dict:
    key, spec, seed = args
    group, records = spec["group"], spec["records"]
    samples = 300
    fit = proportions.fit_group(group, records, seed, samples=samples)
    if fit.ess < MIN_ESS_SHARE * samples:  # retry once with a larger importance sample
        samples = 800
        fit = proportions.fit_group(group, records, seed + 1, samples=samples)
    status = "PUBLISHED" if fit.ess >= min(MIN_ESS_SHARE * samples, MIN_ESS_ABSOLUTE) else "NOT_PUBLISHED_DIAGNOSTIC_FAILURE"
    by_tail = {tail: proportions.publish(group, spec["target"], fit, records, seed, tail) for tail in proportions.TAILS}
    for params in by_tail.values():
        for p in params:
            p["status"] = status
    rule = proportions.RULES["groups"][group]
    out = {"key": key, "group": group, "by_tail": by_tail, "ess": fit.ess, "samples": samples, "status": status,
           "tau": {level: proportions.quantiles(fit.tau_draws[:, i]) for i, level in enumerate(fit.levels)},
           "ep_iterations": fit.ep_iterations}
    if spec.get("model_name"):
        context = rule["levels"][: rule["levels"].index(rule["parameter_level"]) + 1]
        out["model"] = target_from_binomial(spec["model_name"], fit, records, context, spec.get("meta"))
    return out


def pit_calibration(loo: list[dict], tail_choice: dict) -> dict:
    """Randomized-PIT calibration of every model and of the published (chosen-tail) model."""
    from .proportions import summarise_pit

    models = sorted({m for i in loo for m in i.get("pit", {})})
    chosen = [{**i, "pit": {**i["pit"], "m3_published": i["pit"][f"m3_{tail_choice[i['group']]['chosen']}"]}} for i in loo if i.get("pit")]
    return {"overall": {m: summarise_pit(loo, m) for m in models},
            "published_model": {"overall": summarise_pit(chosen, "m3_published"),
                                "by_group": summarise_pit(chosen, "m3_published", "group"),
                                "by_probability_range": summarise_pit(chosen, "m3_published", "probability_range"),
                                "by_borrowing_depth": summarise_pit(chosen, "m3_published", "borrowing_depth")},
            "m2_by_probability_range": summarise_pit(loo, "m2_gaussian_logit", "probability_range"),
            "note": "coverage from the randomized probability integral transform, which is exactly uniform for a calibrated "
                    "predictive of a count; interval coverage from replicated counts counts ties as covered and is inflated for small arms"}


def proportion_acceptance(calibration: dict) -> dict:
    pub = calibration["published_model"]["overall"]
    pit = calibration.get("randomized_pit", {}).get("published_model", {}).get("overall") or {}
    cov95 = pit.get("coverage_95", pub["coverage_95"])
    cov50 = pit.get("coverage_50", pub["coverage_50"])
    m2 = calibration["overall"]["m2_gaussian_logit"]["mean_crps"]
    glob = calibration["overall"]["global_pooled_rate"]["mean_crps"]
    return {
        "proportion_loo_coverage_95_in_93_97": {"value_randomized_pit": cov95, "value_interval": pub["coverage_95"], "pass": 0.93 <= cov95 <= 0.97},
        "proportion_loo_coverage_50_reasonable_40_60": {"value_randomized_pit": cov50, "value_interval": pub["coverage_50"], "pass": 0.40 <= cov50 <= 0.60},
        "proportion_crps_not_worse_than_milestone_2": {"m3": pub["mean_crps"], "m2": m2, "relative": pub["mean_crps"] / m2 - 1,
                                                       "pass": pub["mean_crps"] <= m2 * 1.02},
        "hierarchical_crps_below_global_pooling": {"hierarchical": pub["mean_crps"], "global": glob, "pass": pub["mean_crps"] < glob},
    }


# ----------------------------------------------------------------------------- baseline backtest

_BT: dict = {}


def _bt_init(bundle: dict) -> None:
    _BT.update(bundle)


def _fit_baseline_models(exclude: str, seed: int, samples: int = 150, draws: int = 200) -> dict:
    """All baseline target models refitted without one study (or with all when exclude='')."""
    models = {}
    for name in ("age_mean", "age_sd"):
        group = "baseline_age" if name == "age_mean" else "baseline_age_sd"
        rule = proportions.RULES["groups"][group]
        recs = [r for r in _BT[name] if r["study"] != exclude]
        centre = float(np.average([r["y"] for r in recs], weights=[1 / r["s2"] for r in recs]))
        fit = fit_hierarchy([{**r, "y": r["y"] - centre} for r in recs], rule["levels"], rule["tau_prior_scale"], rule["root_sd"],
                            samples=1500, draws=draws, seed=seed)
        context = rule["levels"][: rule["levels"].index(rule["parameter_level"]) + 1]
        meta = {"within_variance": float(np.median([r["sd_latent"] ** 2 for r in recs]))} if name == "age_mean" else {}
        models[name] = target_from_gaussian(name, fit, recs, context, centre, meta)
    for name, group, recs_all in _BT["binomial_targets"]:
        rule = proportions.RULES["groups"][group]
        recs = [r for r in recs_all if r["study"] != exclude]
        fit = proportions.fit_binomial_hierarchy(recs, rule["levels"], rule["tau_prior_scale"], rule["root_sd"],
                                                 samples=samples, draws=draws, seed=seed)
        context = rule["levels"][: rule["levels"].index(rule["parameter_level"]) + 1]
        models[name] = target_from_binomial(name, fit, recs, context)
    return models


def _crps(pred: np.ndarray, obs: float) -> float:
    return float(np.abs(pred - obs).mean() - 0.5 * np.abs(pred[:, None] - pred[None, : min(300, pred.size)]).mean())


def _interval(pred: np.ndarray, obs: float) -> dict:
    q = np.quantile(pred, [0.025, 0.25, 0.75, 0.975])
    return {"covered_95": bool(q[0] <= obs <= q[3]), "covered_50": bool(q[1] <= obs <= q[2]), "width_95": float(q[3] - q[0]),
            "abs_error": float(abs(np.median(pred) - obs)), "crps": _crps(pred, obs)}


def _baseline_backtest(args: tuple) -> dict | None:
    study, seed = args
    held = _BT["held_out"][study]
    models = _fit_baseline_models(study, seed)
    gen = BaselineGenerator(models, _BT["categorical"], _BT["copula"], {})
    e = held["eligibility"]
    q = {"disease_family": held["ctx"]["disease_family"], "disease": held["ctx"]["disease"], "setting": held["ctx"]["setting"],
         "min_age": e["min_age"], "max_age": e["max_age"], "age_class": e["age_class"], "sex": e["sex"],
         "allowed_categories": {}, "label": study}
    n = int(held["N"])
    rng = np.random.default_rng(seed)
    means, sds, females, cat_probs = [], [], [], defaultdict(list)
    for r in range(200):
        params = gen.parameters(q, posterior_draw=r, future_study=True, seed=seed + r)
        cohort = gen.sample(params, n, seed=seed + 10_000 + r)
        ages = np.array(cohort["age"])
        means.append(ages.mean())
        sds.append(ages.std(ddof=1) if n > 1 else 0.0)
        females.append(np.mean([s == "female" for s in cohort["sex"]]))
        for variable in _BT["categorical"]:
            cat_probs[variable].append(params[f"{variable}_probabilities"])
        extrapolation = params["extrapolation_level"]
    expected = gen.parameters(q, posterior_draw=None, seed=seed)
    ref = gen.sample(expected, 4000, seed=seed + 99)
    out: dict[str, Any] = {"study": study, "N": n, "age_class": e["age_class"], "extrapolation_level": extrapolation,
                           "support_age": expected["retrieval"]["age_mean"]["support"],
                           "eligibility_support": eligibility_support(expected)}
    pooled = _BT["global"]
    if held.get("age_mean") is not None:
        obs_m, obs_s = held["age_mean"], held["age_sd"]
        out["age_mean"] = _interval(np.array(means), obs_m)
        out["age_sd"] = _interval(np.array(sds), obs_s)
        approx_obs = rng.normal(obs_m, obs_s, 4000)
        if e["min_age"] is not None or e["max_age"] is not None:
            lo = e["min_age"] if e["min_age"] is not None else -np.inf
            hi = e["max_age"] if e["max_age"] is not None else np.inf
            approx_obs = stats.truncnorm.rvs((lo - obs_m) / obs_s, (hi - obs_m) / obs_s, loc=obs_m, scale=obs_s, size=4000, random_state=rng)
        out["age_wasserstein"] = float(stats.wasserstein_distance(ref["age"], approx_obs))
        g_means = rng.normal(pooled["age_mean"], pooled["age_sd"] / math.sqrt(n), 2000)
        out["age_mean_global"] = _interval(g_means, obs_m)
        out["age_wasserstein_global"] = float(stats.wasserstein_distance(rng.normal(pooled["age_mean"], pooled["age_sd"], 4000), approx_obs))
    if held.get("female") is not None:
        f = held["female"] / n
        out["female_share"] = _interval(np.array(females), f)
        p = expected["p_female"]
        out["female_brier"] = float(f * (1 - p) ** 2 + (1 - f) * p**2)
        out["female_share_global"] = _interval(rng.binomial(n, pooled["p_female"], 2000) / n, f)
        out["female_brier_global"] = float(f * (1 - pooled["p_female"]) ** 2 + (1 - f) * pooled["p_female"] ** 2)
    for variable, spec in _BT["categorical"].items():
        counts = held.get("categorical", {}).get(variable)
        if not counts:
            continue
        cats = spec["categories"]
        x = np.array([counts.get(c, 0) for c in cats])
        probs = np.array([[pr[c] for c in cats] for pr in cat_probs[variable]])
        probs = np.clip(probs, 1e-12, 1)
        probs /= probs.sum(1, keepdims=True)
        lp = stats.multinomial.logpmf(x, x.sum(), probs)
        glob = np.array([pooled[f"{variable}_probabilities"][c] for c in cats])
        out[f"{variable}_multinomial_log_score"] = float(special.logsumexp(lp) - math.log(lp.size)) / max(int(x.sum()), 1)
        out[f"{variable}_multinomial_log_score_global"] = float(stats.multinomial.logpmf(x, x.sum(), glob)) / max(int(x.sum()), 1)
        out[f"{variable}_brier"] = float(((probs.mean(0) - x / x.sum()) ** 2).sum())
        out[f"{variable}_brier_global"] = float(((glob - x / x.sum()) ** 2).sum())
    return out


# ----------------------------------------------------------------------------- 3B


def stage_survival(rows: list[dict], families: dict, classes: dict, v2_manifest: dict) -> tuple[dict, dict]:
    """3B: fuse V2 hazard ratios with V2 absolute survival curves; survival backtests."""
    hr_params = [json.loads(line) for line in (V2 / "parameter_index.jsonl").read_text(encoding="utf-8").splitlines()
                 if '"relative_effect"' in line]
    hr_params = [p for p in hr_params if p["group"] == "relative_effect"]
    hr_ids = {p["parameter_id"] for p in hr_params}
    hr_draws: dict[str, list] = defaultdict(list)
    for r in pq.read_table(V2 / "posterior_draws" / "borrowed_parameters.parquet", filters=[("parameter_id", "in", sorted(hr_ids))]).to_pylist():
        hr_draws[r["parameter_id"]].append(r["hierarchical"])
    hr_draws = {k: np.array(v) for k, v in hr_draws.items()}
    surv_index = pq.read_table(V2 / "survival" / "survival_parameter_index.parquet").to_pylist()
    surv_draws: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"loc": [], "shape": []}))
    for r in pq.read_table(V2 / "survival" / "survival_draws" / "survival_draws.parquet").to_pylist():
        d = surv_draws[r["parameter_id"]][r["family"]]
        d["loc"].append(r["log_scale"])
        d["shape"].append(r["shape"])
    surv_draws = {pid: {f: {"loc": np.array(v["loc"]), "shape": np.array(v["shape"])} for f, v in fams.items()} for pid, fams in surv_draws.items()}
    fusion, grid_rows = survival_fusion.fuse(hr_params, hr_draws, surv_index, surv_draws, SEED)
    tau = v2_manifest["survival"]["tau_study_log_scale"]
    observed = survival_fusion.observed_constraints(rows, families, classes, borrow2.context_fields)
    surv_bt = survival_fusion.backtest(fusion, observed, surv_index, surv_draws, hr_draws, tau, SEED)
    (OUT / "survival").mkdir(parents=True, exist_ok=True)
    (OUT / "validation").mkdir(parents=True, exist_ok=True)
    with open(OUT / "survival" / "fused_survival_index.jsonl", "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(rec, default=str) + "\n" for rec in fusion)
    _write(OUT / "survival" / "fused_survival_index.parquet", fusion)
    _write(OUT / "survival" / "fused_survival_curves.parquet", grid_rows)

    def sb(sel: list[dict]) -> dict:
        if not sel:
            return {"held_out": 0}
        return {"held_out": len(sel), "coverage_95": float(np.mean([x["covered_95"] for x in sel])),
                "coverage_50": float(np.mean([x["covered_50"] for x in sel])), "mean_crps": float(np.mean([x["crps"] for x in sel])),
                "mean_abs_error_log_scale": float(np.mean([x["abs_error"] for x in sel])),
                "median_width_95": float(np.median([x["width_95"] for x in sel]))}
    survival_bt = {"route_A_contexts_scored": len({x["fusion_id"] for x in surv_bt}),
                   "by_model": {m: sb([x for x in surv_bt if x["model"] == m]) for m in ("fused_S0_pow_HR", "naive_HR_1")},
                   "fused_by_PH_support": {s: sb([x for x in surv_bt if x["model"] == "fused_S0_pow_HR" and x["PH_support"] == s])
                                           for s in sorted({x["PH_support"] for x in surv_bt})},
                   "fused_by_kind": {k: sb([x for x in surv_bt if x["model"] == "fused_S0_pow_HR" and x["kind"] == k]) for k in ("median", "landmark")},
                   "note": "Route A contexts: the treatment arm's reported medians (log months) and landmarks (log cumulative hazard) are "
                           "predicted from the comparator curve and the HR posterior (S1 = S0^HR) as if the treatment curve were unknown; "
                           "the HR posterior includes the same trial, so this checks fusion consistency, not out-of-sample HR prediction"}
    (OUT / "validation" / "survival_backtests.json").write_text(json.dumps(survival_bt, indent=1), encoding="utf-8")
    _write(OUT / "validation" / "survival_backtest_records.parquet", surv_bt)
    report_part = {"hr_contexts": len(fusion), "routes": dict(Counter(f["route"] for f in fusion)),
                                 "status": dict(Counter(f["status"] for f in fusion)),
                                 "PH_support": dict(Counter(f["PH_support"] for f in fusion if f["route"] != "NONE"))}
    log(stage="3B_done", **report_part)
    return report_part, survival_bt


# ----------------------------------------------------------------------------- build


def build(workers: int = 6, loo_per_level: int = 40, baseline_backtests: int = 80, out_dir: Path | None = None,
          smoke: bool = False, resume: bool = False) -> dict:
    """smoke=True runs every stage on small subsets (for testing the pipeline), into out_dir.
    resume=True reuses stored 3A results (fits, calibration, binomial baseline models) and reruns
    the remaining stages."""
    global OUT
    if out_dir is not None:
        OUT = Path(out_dir)
    v2_manifest = json.loads((V2 / "manifest.json").read_text(encoding="utf-8"))
    rows = pq.read_table(V1 / "evidence_table.parquet").to_pylist()
    families = json.loads((WORK / "disease_families.json").read_text(encoding="utf-8"))
    classes = json.loads((WORK / "drug_classes.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    factors = age_factors(RAW)
    elig = baseline.eligibility(RAW)
    report["survival_fusion"], survival_bt = stage_survival(rows, families, classes, v2_manifest)

    # ------------------------------------------------------------------ 3A + categorical fits
    targets = {k: v for k, v in borrow2.build_records(rows, families, classes, factors).items() if v["group"] in BINOMIAL_GROUPS}
    if smoke:
        keep_studies = set(sorted({r["study"] for v in targets.values() for r in v["records"]})[::8])
        rows = [r for r in rows if r["nct_id"] in keep_studies]
        targets = {k: v for k, v in borrow2.build_records(rows, families, classes, factors).items()
                   if v["group"] in BINOMIAL_GROUPS and (len(v["records"]) <= 40 or v["group"] == "baseline_sex")}
    jobs = []
    for i, (key, spec) in enumerate(sorted(targets.items(), key=lambda kv: -len(kv[1]["records"]))):
        spec = dict(spec)
        if spec["group"] == "baseline_sex":
            spec["model_name"] = "sex_female"
        jobs.append((key, spec, SEED + i))
    categorical_spec, categorical_meta, binomial_bt = {}, {}, []
    sex_records = next(v["records"] for v in targets.values() if v["group"] == "baseline_sex")
    binomial_bt.append(("sex_female", "baseline_sex", sex_records))
    for variable in ("race", "ethnicity"):
        steps, meta = baseline.categorical_records(rows, families, classes, variable)
        categorical_meta[variable] = meta
        categorical_spec[variable] = {"categories": meta["categories"], "steps": [f"{variable}|{s['step']}" for s in steps]}
        for s in steps:
            name = f"{variable}|{s['step']}"
            target = {"domain": "baseline", "variable": variable, "statistic_family": "stick_breaking_conditional_proportion",
                      "step": s["step"], "category": s["category"], "conditional_on": "not in earlier categories " + json.dumps(meta["categories"][: s["step"]])}
            jobs.append(((f"baseline_categorical|{name}", json.dumps(target)), {"group": "baseline_categorical", "target": target,
                          "records": s["records"], "model_name": name}, SEED + 10_000 + s["step"] + (100 if variable == "ethnicity" else 0)))
            binomial_bt.append((name, "baseline_categorical", s["records"]))
    if not resume:
        log(stage="3A_fit", targets=len(jobs))
        results = []
        with ProcessPoolExecutor(workers) as pool:
            for done, r in enumerate(pool.map(_fit_publish, jobs, chunksize=1), 1):
                results.append(r)
                if done % 50 == 0 or r["status"] != "PUBLISHED":
                    log(stage="3A_fit", done=done, last=str(r["key"])[:100], ess=round(r["ess"]), status=r["status"])
        models = {r["model"].name: r["model"] for r in results if "model" in r}

        # ------------------------------------------------------------------ 3A calibration (LOO)
        rng = random.Random(SEED)
        loo_jobs = []
        for group in BINOMIAL_GROUPS:
            rule = proportions.RULES["groups"][group]
            depth = rule["levels"].index(rule["parameter_level"]) + 1
            for bucket in ("A", "B", "C"):
                candidates = []
                for spec in targets.values():
                    if spec["group"] != group or len({r["study"] for r in spec["records"]}) < 2:
                        continue
                    by_node = defaultdict(set)
                    for r in spec["records"]:
                        by_node[tuple(r[lv] for lv in rule["levels"][:depth])].add(r["study"])
                    for studies in by_node.values():
                        others = len(studies) - 1
                        if ("A" if others >= 2 else "B" if others == 1 else "C") == bucket:
                            candidates.extend((spec, s) for s in sorted(studies))
                for spec, study in rng.sample(candidates, min(loo_per_level, len(candidates))):
                    loo_jobs.append((spec, study, SEED + 50_000 + len(loo_jobs)))
        log(stage="3A_loo", jobs=len(loo_jobs))
        loo = []
        with ProcessPoolExecutor(workers) as pool:
            for done, r in enumerate(pool.map(proportions.loo_one, sorted(loo_jobs, key=lambda j: -len(j[0]["records"])), chunksize=1), 1):
                if r:
                    loo.append(r)
                if done % 40 == 0:
                    log(stage="3A_loo", done=done)
        tail_choice = {}
        for group in BINOMIAL_GROUPS:
            sel = [i for i in loo if i["group"] == group]
            if not sel:
                tail_choice[group] = {"chosen": "normal", "held_out": 0, "note": "no held-out studies; normal tail by default"}
                continue
            lpd = {tail: float(np.mean([i["models"][f"m3_{tail}"]["log_predictive_density"] for i in sel])) for tail in proportions.TAILS}
            tail_choice[group] = {"chosen": max(lpd, key=lpd.get), "mean_log_predictive_density": lpd, "held_out": len(sel)}
        tail_choice["baseline_categorical"] = {"chosen": tail_choice["baseline_sex"]["chosen"], "note": "follows baseline_sex (same hierarchy shape)"}
        model_names = [f"m3_{t}" for t in proportions.TAILS] + ["m2_gaussian_logit", "global_pooled_rate", "leaf_only_beta_binomial"]
        calibration = {
            "held_out": len(loo),
            "overall": {m: proportions.summarise(loo, m) for m in model_names},
            "by_group": {m: proportions.summarise(loo, m, "group") for m in model_names},
            "by_probability_range": {m: proportions.summarise(loo, m, "probability_range") for m in model_names},
            "by_borrowing_depth": {m: proportions.summarise(loo, m, "borrowing_depth") for m in model_names},
            "by_evidence_level": {m: proportions.summarise(loo, m, "level") for m in model_names},
            "tail_choice": tail_choice,
            "note": "one arm of a held-out study predicted from all other studies; y_rep ~ Binomial(n, p_new_study); probability range "
                    "from the predictive median; borrowing depth = deepest existing hierarchy node for the held-out context",
        }
        calibration["randomized_pit"] = pit_calibration(loo, tail_choice)
        same = [i for i in loo if "leaf_only_beta_binomial" in i["models"]]
        calibration["same_observations_with_leaf_evidence"] = {m: proportions.summarise(same, m) for m in model_names}
        # Chosen-tail summary by the requested breakdowns.
        chosen = []
        for i in loo:
            t = tail_choice[i["group"]]["chosen"]
            chosen.append({**i, "models": {**i["models"], "m3_published": i["models"][f"m3_{t}"]}})
        calibration["published_model"] = {"overall": proportions.summarise(chosen, "m3_published"),
                                          "by_probability_range": proportions.summarise(chosen, "m3_published", "probability_range"),
                                          "by_borrowing_depth": proportions.summarise(chosen, "m3_published", "borrowing_depth"),
                                          "by_group": proportions.summarise(chosen, "m3_published", "group")}

        # ------------------------------------------------------------------ 3A publication
        params, draw_rows, parent_rows, tau_rows = [], [], [], []
        for r in results:
            tail = tail_choice[r["group"]]["chosen"]
            params.extend(r["by_tail"][tail])
            tau_rows.extend({"target_key": str(r["key"]), "group": r["group"], "level": lv, **{f"tau_{k}": v for k, v in q.items()},
                             "importance_ess": r["ess"], "importance_samples": r["samples"], "status": r["status"]} for lv, q in r["tau"].items())
        index_rows = []
        for p in params:
            d = p.pop("draws")
            for i in range(d["population"].size):
                draw_rows.append({"parameter_id": p["parameter_id"], "draw": i, "population": float(d["population"][i]),
                                  "future_study": float(d["future_study"][i])})
            for c in p["parent_contribution"]["chain"]:
                parent_rows.append({"parameter_id": p["parameter_id"], **c})
            index_rows.append({
                "parameter_id": p["parameter_id"], "status": p["status"], "group": p["group"],
                **{f"context_{k}": v for k, v in p["context"].items()}, **{f"target_{k}": v for k, v in p["target"].items()},
                "level": p["support"]["level"], "studies": p["support"]["studies"], "arms": p["support"]["arms"],
                "total_N": p["support"]["total_N"], "borrowed_parent_studies": p["support"]["borrowed_parent_studies"],
                **{f"population_{k}": v for k, v in p["population_posterior"].items()},
                **{f"future_study_{k}": v for k, v in p["future_study_predictive"].items()},
                "within_study_median": p["within_study_posterior"]["median"], "within_study_q025": p["within_study_posterior"]["q025"],
                "within_study_q975": p["within_study_posterior"]["q975"],
                "share_of_precision_from_parent": p["parent_contribution"]["share_of_precision_from_parent"],
                "shrinkage_standardised_shift": p["shrinkage"]["standardised_shift"],
                "tau_importance_ess": p["diagnostics"]["tau_importance_ess"],
            })
        (OUT / "proportions").mkdir(parents=True, exist_ok=True)
        with open(OUT / "proportions" / "parameter_index.jsonl", "w", encoding="utf-8") as handle:
            for p in params:
                handle.write(json.dumps(p, default=str) + "\n")
        _write(OUT / "proportions" / "parameter_index.parquet", index_rows)
        _write(OUT / "proportions" / "posterior_draws.parquet", draw_rows)
        _write(OUT / "proportions" / "parent_contributions.parquet", parent_rows)
        _write(OUT / "proportions" / "tau_posteriors.parquet", tau_rows)
        _write(OUT / "validation" / "proportion_loo_records.parquet",
               [{k: v for k, v in i.items() if k != "models"} | {f"{m}__{s}": x for m, sc in i["models"].items() for s, x in sc.items()} for i in loo])
        (OUT / "validation").mkdir(parents=True, exist_ok=True)
        (OUT / "validation" / "proportion_calibration.json").write_text(json.dumps(calibration, indent=1), encoding="utf-8")
        report["proportions"] = {"targets": len(results), "parameters": len(params),
                                 "withheld_low_ess": sum(p["status"] != "PUBLISHED" for p in params),
                                 "by_group": dict(Counter(p["group"] for p in params)),
                                 "by_level": dict(Counter(p["support"]["level"] for p in params)),
                                 "tail_choice": {g: v["chosen"] for g, v in tail_choice.items()}}
        log(stage="3A_done", **report["proportions"])
    else:  # resume: reuse the stored 3A fits, calibration and binomial baseline models
        from .protocol import load_models

        calibration = json.loads((OUT / "validation" / "proportion_calibration.json").read_text(encoding="utf-8"))
        tail_choice = calibration["tail_choice"]
        models = {k: v for k, v in load_models(OUT / "baseline").items() if k not in {"age_mean", "age_sd"}}
        index = pq.read_table(OUT / "proportions" / "parameter_index.parquet").to_pylist()
        report["proportions"] = {"targets": len(jobs), "parameters": len(index),
                                 "withheld_low_ess": sum(p["status"] != "PUBLISHED" for p in index),
                                 "by_group": dict(Counter(p["group"] for p in index)), "by_level": dict(Counter(p["level"] for p in index)),
                                 "tail_choice": {g: v["chosen"] for g, v in tail_choice.items()}}
        log(stage="3A_resumed", **report["proportions"])

    # ------------------------------------------------------------------ 3C baseline marginals
    age_means, age_sds, latent_status = baseline.age_records(rows, families, classes, factors, elig)
    for name, recs, group in (("age_mean", age_means, "baseline_age"), ("age_sd", age_sds, "baseline_age_sd")):
        rule = proportions.RULES["groups"][group]
        centre = float(np.average([r["y"] for r in recs], weights=[1 / r["s2"] for r in recs]))
        fit = fit_hierarchy([{**r, "y": r["y"] - centre} for r in recs], rule["levels"], rule["tau_prior_scale"], rule["root_sd"],
                            samples=3000, draws=400, seed=SEED + 7)
        context = rule["levels"][: rule["levels"].index(rule["parameter_level"]) + 1]
        meta = {"within_variance": float(np.median([r["sd_latent"] ** 2 for r in recs])), "tau_importance_ess": fit.ess} \
            if name == "age_mean" else {"tau_importance_ess": fit.ess}
        models[name] = target_from_gaussian(name, fit, recs, context, centre, meta)
        log(stage="3C_age", target=name, ess=round(fit.ess), records=len(recs))
    variables = ["age", "sex", *categorical_spec]
    registry = baseline.dependency_registry(age_means, sex_records, rows, variables)
    copula = baseline.correlation_matrix(variables, registry)
    bdir = OUT / "baseline"
    save_models(models, bdir)
    (bdir / "dependency_registry.json").write_text(json.dumps(registry, indent=1), encoding="utf-8")
    (bdir / "copula.json").write_text(json.dumps(copula, indent=1), encoding="utf-8")
    (bdir / "generator_spec.json").write_text(json.dumps({
        "categorical": categorical_spec, "categorical_meta": categorical_meta,
        "disease_family_map": str(WORK / "disease_families.json"),
        "age_population_classes": {"rule": "from eligibility age range: AYA if min>=15 and max<=39; PEDIATRIC if max<=21; "
                                           "ADULT if min>=18; otherwise MIXED", "classes": list(baseline.AGE_CLASSES)},
        "age_model": "latent normal (mean, SD) inverted from reported moments under each trial's own eligibility truncation; "
                     "new protocols draw from the latent normal truncated to their own range",
    }, indent=1), encoding="utf-8")
    _write(bdir / "age_latent_records.parquet", [{k: r[k] for k in ("study", "arm", "age_class", "disease_family", "disease", "setting",
                                                                   "reported_mean", "reported_sd", "eligibility_min", "eligibility_max",
                                                                   "latent_status", "n")} | {"latent_mean": r["y"], "latent_sd": r["sd_latent"]}
                                                  for r in age_means])
    # Setting-level marginal summaries for inspection.
    marg_rows = []
    for name, m in models.items():
        for path, node in m.nodes.items():
            if len(path) != len(m.context_levels):
                continue
            draws = node["draws"].astype(float)
            nat = special.expit(draws) if m.kind == "binomial" else draws + m.centre
            if name == "age_sd":
                nat = np.exp(nat)
            marg_rows.append({"target": name, **dict(zip(m.context_levels, path, strict=True)), "studies": node["studies"], "N": node["N"],
                              **{f"population_{k}": v for k, v in proportions.quantiles(nat).items()}})
    _write(bdir / "marginal_summaries.parquet", marg_rows)
    report["baseline"] = {"age_latent_inversion": dict(latent_status), "age_classes": dict(Counter(r["age_class"] for r in age_means)),
                          "models": sorted(models), "categorical": categorical_meta,
                          "copula": {k: copula[k] for k in ("variables", "nonzero_offdiagonal", "min_eigenvalue_before", "psd_repair_frobenius")},
                          "correlation_sources": dict(Counter(p["correlation_source"] for p in registry["baseline_baseline"]))}
    log(stage="3C_done", models=len(models))

    # ------------------------------------------------------------------ 3D baseline backtests
    by_study: dict[str, dict] = {}
    for r in age_means:
        entry = by_study.setdefault(r["study"], {"arms": {}})
        entry["arms"].setdefault(r["arm"], {})["age"] = r
    for r in sex_records:
        by_study.setdefault(r["study"], {"arms": {}})["arms"].setdefault(r["arm"], {})["sex"] = r
    cat_counts: dict[str, dict] = defaultdict(dict)
    for row in rows:
        if row["domain"] == "baseline" and row["variable"] in categorical_spec and row.get("numerator") is not None:
            arm = f"{row['nct_id']}|{row.get('registry_group')}"
            cat_counts[arm].setdefault(row["variable"], {})[str(row["category"])] = int(row["numerator"])
    held_out = {}
    for study, entry in by_study.items():
        arms = [(a, v) for a, v in entry["arms"].items() if "age" in v and "sex" in v]
        if not arms:
            continue
        arm, v = max(arms, key=lambda av: av[1]["sex"]["n"])
        e = elig.get(study, {"min_age": None, "max_age": None, "age_class": "MIXED", "sex": "ALL"})
        held_out[study] = {"ctx": v["sex"], "N": v["sex"]["n"], "female": v["sex"]["count"], "eligibility": e,
                           "age_mean": v["age"]["reported_mean"], "age_sd": v["age"]["reported_sd"],
                           "categorical": cat_counts.get(arm, {})}
    all_age = [(r["reported_mean"], r["reported_sd"], r["n"]) for r in age_means]
    w = np.array([a[2] for a in all_age], float)
    gm = float(np.average([a[0] for a in all_age], weights=w))
    gsd = float(math.sqrt(np.average([a[1] ** 2 + (a[0] - gm) ** 2 for a in all_age], weights=w)))
    global_ref = {"age_mean": gm, "age_sd": gsd,
                  "p_female": sum(r["count"] for r in sex_records) / sum(r["n"] for r in sex_records)}
    for variable, spec in categorical_spec.items():
        tot = Counter()
        for counts in cat_counts.values():
            c = counts.get(variable)
            if c and all(k in c for k in spec["categories"]):
                for k in spec["categories"]:
                    tot[k] += c[k]
        s = sum(tot.values())
        global_ref[f"{variable}_probabilities"] = {k: tot[k] / s for k in spec["categories"]}
    bundle = {"age_mean": age_means, "age_sd": age_sds, "binomial_targets": binomial_bt, "categorical": categorical_spec,
              "copula": copula, "held_out": held_out, "global": global_ref}
    sample = random.Random(SEED + 3).sample(sorted(held_out), min(baseline_backtests, len(held_out)))
    log(stage="3D_backtest", studies=len(sample))
    backtests = []
    with ProcessPoolExecutor(workers, initializer=_bt_init, initargs=(bundle,)) as pool:
        for done, r in enumerate(pool.map(_baseline_backtest, [(s, SEED + 70_000 + i) for i, s in enumerate(sample)], chunksize=1), 1):
            if r:
                backtests.append(r)
            if done % 10 == 0:
                log(stage="3D_backtest", done=done)
    _write(OUT / "validation" / "baseline_backtest_records.parquet", backtests)

    def mean_of(key: str, sub: str) -> float | None:
        vals = [b[key][sub] for b in backtests if key in b]
        return float(np.mean(vals)) if vals else None

    def plain(key: str) -> float | None:
        vals = [b[key] for b in backtests if key in b]
        return float(np.mean(vals)) if vals else None

    def by(field: str) -> dict:
        out = {}
        for value in sorted({str(b[field]) for b in backtests}):
            sel = [b for b in backtests if str(b[field]) == value]
            out[value] = {"held_out": len(sel),
                          "age_mean_coverage_95": float(np.mean([b["age_mean"]["covered_95"] for b in sel if "age_mean" in b] or [np.nan])),
                          "age_mean_abs_error": float(np.mean([b["age_mean"]["abs_error"] for b in sel if "age_mean" in b] or [np.nan])),
                          "female_share_coverage_95": float(np.mean([b["female_share"]["covered_95"] for b in sel if "female_share" in b] or [np.nan]))}
        return out

    baseline_bt = {"held_out_studies": len(backtests),
                   "age_mean": {"coverage_95": mean_of("age_mean", "covered_95"), "coverage_50": mean_of("age_mean", "covered_50"),
                                "mean_abs_error": mean_of("age_mean", "abs_error"), "mean_crps": mean_of("age_mean", "crps"),
                                "median_width_95": float(np.median([b["age_mean"]["width_95"] for b in backtests if "age_mean" in b])),
                                "global_pooling_mean_crps": mean_of("age_mean_global", "crps"),
                                "global_pooling_coverage_95": mean_of("age_mean_global", "covered_95")},
                   "age_sd": {"coverage_95": mean_of("age_sd", "covered_95"), "coverage_50": mean_of("age_sd", "covered_50"),
                              "mean_abs_error": mean_of("age_sd", "abs_error"), "mean_crps": mean_of("age_sd", "crps")},
                   "age_wasserstein": {"hierarchical_mean": plain("age_wasserstein"), "global_pooling_mean": plain("age_wasserstein_global")},
                   "female_share": {"coverage_95": mean_of("female_share", "covered_95"), "coverage_50": mean_of("female_share", "covered_50"),
                                    "mean_abs_error": mean_of("female_share", "abs_error"), "mean_crps": mean_of("female_share", "crps"),
                                    "brier": plain("female_brier"), "global_pooling_mean_crps": mean_of("female_share_global", "crps"),
                                    "global_pooling_coverage_95": mean_of("female_share_global", "covered_95"), "global_pooling_brier": plain("female_brier_global")},
                   **{variable: {"mean_multinomial_log_score_per_patient": plain(f"{variable}_multinomial_log_score"),
                                 "global_pooling_mean_multinomial_log_score_per_patient": plain(f"{variable}_multinomial_log_score_global"),
                                 "brier": plain(f"{variable}_brier"), "global_pooling_brier": plain(f"{variable}_brier_global"),
                                 "held_out": sum(f"{variable}_brier" in b for b in backtests)} for variable in categorical_spec},
                   "by_age_class": by("age_class"), "by_extrapolation_level": by("extrapolation_level"),
                   "note": "each held-out study is removed from every baseline model, the models are refitted, and 200 trials of the "
                           "held-out arm's size are generated from its protocol (disease, setting, eligibility) in uncertainty mode "
                           "with a new-study effect; Wasserstein compares an expected-world cohort with a normal approximation "
                           "(truncated to eligibility) of the reported age distribution"}
    (OUT / "validation" / "baseline_backtests.json").write_text(json.dumps(baseline_bt, indent=1), encoding="utf-8")
    log(stage="3D_backtest_done", held_out=len(backtests))

    # ------------------------------------------------------------------ acceptance
    acceptance = {
        **proportion_acceptance(calibration),
        "baseline_age_crps_below_global_pooling": {"hierarchical": baseline_bt["age_mean"]["mean_crps"], "global": baseline_bt["age_mean"]["global_pooling_mean_crps"],
                                                   "pass": baseline_bt["age_mean"]["mean_crps"] < baseline_bt["age_mean"]["global_pooling_mean_crps"]},
        "baseline_sex_crps_below_global_pooling": {"hierarchical": baseline_bt["female_share"]["mean_crps"], "global": baseline_bt["female_share"]["global_pooling_mean_crps"],
                                                   "pass": baseline_bt["female_share"]["mean_crps"] < baseline_bt["female_share"]["global_pooling_mean_crps"]},
        "no_fabricated_correlations": {"nonzero_offdiagonal": copula["nonzero_offdiagonal"],
                                       "observed_sources": sum(p["correlation_source"] == "OBSERVED" for p in registry["baseline_baseline"]),
                                       "pass": copula["nonzero_offdiagonal"] <= sum(p["correlation_source"] == "OBSERVED" for p in registry["baseline_baseline"])},
        "correlation_matrices_psd": {"min_eigenvalue": copula["min_eigenvalue_after"], "pass": copula["min_eigenvalue_after"] > 0},
        "v2_toxicity_retained": {"path": str(V2 / "toxicity"), "pass": (V2 / "toxicity" / "censored_toxicity_parameters.parquet").exists()},
    }
    (OUT / "validation" / "acceptance.json").write_text(json.dumps(acceptance, indent=1), encoding="utf-8")
    report["acceptance"] = {k: v["pass"] for k, v in acceptance.items()}
    report["validation"] = {"proportion_calibration": calibration["published_model"]["overall"],
                            "baseline_backtests": {k: baseline_bt[k] for k in ("age_mean", "female_share", "age_wasserstein")},
                            "survival_backtests": survival_bt["by_model"]}

    tox = V2 / "toxicity"
    manifest = {
        "asset": "Simulation Parameter Asset", "version": "3.0.0", "model_version": MODEL_VERSION,
        "created": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "inputs": {"clinical_evidence_asset": {"path": str(ASSET / "profiles.jsonl"), "sha256": _sha(ASSET / "profiles.jsonl")},
                   "parameter_asset_v1": {"path": str(V1), "evidence_table_sha256": _sha(V1 / "evidence_table.parquet")},
                   "parameter_asset_v2": {"path": str(V2), "manifest_sha256": _sha(V2 / "manifest.json"), "status": "frozen (read-only)"}},
        "retained_from_v2": {"toxicity": {p.name: _sha(p) for p in sorted(tox.glob("*.parquet"))},
                             "relative_effects": "V2 relative_effect parameters (Gaussian on log ratio, which is exact for CI-derived log HR/OR)",
                             "survival_curves": "V2 absolute survival contexts (inputs to fusion)"},
        "configuration": {"hierarchy_rules": proportions.RULES, "seed": SEED, "min_importance_ess_share": MIN_ESS_SHARE,
                          "min_importance_ess_after_retry": MIN_ESS_ABSOLUTE},
        **report,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return report
