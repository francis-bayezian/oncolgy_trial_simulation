"""Fit, validate and publish Simulation Parameter Asset V1 (milestone 1).

profiles.jsonl (frozen) -> evidence table -> contexts -> model per context -> posterior
summaries (all) + posterior draws (evidence levels A and B) -> parameter index.

Evidence sufficiency: A >= 3 studies, B = 2, C = 1 (study-informed posterior with a
conservative prior, never presented as a meta-analysis), D = no usable observation
(published as NO_RELIABLE_PARAMETER).
"""

import datetime
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from .contexts import build_contexts, parameter_id
from .evidence import ASSET, atomize, load_frozen_profiles
from .models import BetaBinomial, DirichletMultinomial, Fit, NormalRandomEffects

OUT = Path("data/simulation_parameters_v1")
MODEL_VERSION = "spa-milestone-1.0.0"
RATIO_MEASURES = (
    (re.compile(r"hazard.*\blog\b|\blog\b.*hazard", re.IGNORECASE), "hazard_ratio", True),
    (re.compile(r"hazard|\bcox\b", re.IGNORECASE), "hazard_ratio", False),
    (re.compile(r"odds", re.IGNORECASE), "odds_ratio", False),
    (re.compile(r"rate ratio|risk ratio|relative risk|response (?:rate )?ratio", re.IGNORECASE), "risk_ratio", False),
)


def normalise_comparison(row: dict) -> dict:
    """Map comparison-measure wording to a ratio family; a log hazard ratio is exponentiated."""
    if row.get("comparison_normalised"):
        return row
    raw = str(row.get("statistic") or "").replace("_", " ")
    for pattern, family, is_log in RATIO_MEASURES:
        if pattern.search(raw):
            row = dict(row, statistic_family=family, comparison_normalised=True)
            if is_log:
                row.update(value=math.exp(row["value"]) if row.get("value") is not None else None,
                           ci_lower=math.exp(row["ci_lower"]) if row.get("ci_lower") is not None else None,
                           ci_upper=math.exp(row["ci_upper"]) if row.get("ci_upper") is not None else None)
            return row
    return row


def _level(studies: int) -> str:
    return "A" if studies >= 3 else "B" if studies == 2 else "C" if studies == 1 else "D"


def _pick(rows: list[dict]) -> list[dict]:
    """One observation per arm/unit: prefer full analysis populations, then the largest N."""
    by_unit: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_unit[(r["nct_id"], r["registry_group"])].append(r)
    return [min(v, key=lambda r: (r.get("population_scope") is not None, -(r.get("denominator") or 0))) for v in by_unit.values()]


# ----------------------------------------------------------------------------- per-model data prep


def binomial_data(rows: list[dict]) -> tuple[list[dict], np.ndarray, np.ndarray]:
    used, ys, ns = [], [], []
    for r in _pick(rows):
        n = r.get("denominator")
        y = r.get("numerator")
        if y is None and r.get("rate") is not None and n:
            y = round(r["rate"] * n)
        if not n or y is None or not 0 <= y <= n:
            continue
        used.append(r)
        ys.append(int(y))
        ns.append(int(n))
    return used, np.array(ys), np.array(ns)


def continuous_data(rows: list[dict], baseline: bool) -> tuple[list[dict], np.ndarray, np.ndarray, float | None]:
    units: dict[str, list[dict]] = defaultdict(list)
    for r in _pick(rows):
        units[r["nct_id"] if baseline else f"{r['nct_id']}|{r['registry_group']}"].append(r)
    used, ys, ses, sds = [], [], [], []
    for group in units.values():
        valid = [r for r in group if r.get("value") is not None and r.get("denominator")]
        if not valid:
            continue
        n_total = sum(r["denominator"] for r in valid)
        mean = sum(r["value"] * r["denominator"] for r in valid) / n_total
        if all(r.get("sd") is not None for r in valid) and n_total > 1:
            pooled_var = (
                sum((r["denominator"] - 1) * r["sd"] ** 2 + r["denominator"] * (r["value"] - mean) ** 2 for r in valid)
            ) / (n_total - 1)
            sd = math.sqrt(pooled_var)
            se = sd / math.sqrt(n_total)
        elif len(valid) == 1 and valid[0].get("se"):
            sd, se = None, valid[0]["se"]
        elif len(valid) == 1 and valid[0].get("ci_lower") is not None and valid[0].get("ci_upper") is not None:
            z = stats.norm.ppf(0.5 + (valid[0].get("ci_level") or 95) / 200)
            sd, se = None, (valid[0]["ci_upper"] - valid[0]["ci_lower"]) / (2 * z)
        else:
            continue
        if not se or se <= 0:
            continue
        used.extend(valid)
        ys.append(mean)
        ses.append(se)
        if sd is not None:
            sds.append(sd)
    pooled_sd = float(np.median(sds)) if sds else None
    return used, np.array(ys), np.array(ses), pooled_sd


def ratio_data(rows: list[dict]) -> tuple[list[dict], np.ndarray, np.ndarray]:
    used, ys, ses, seen = [], [], [], set()
    for r in rows:
        r = normalise_comparison(r)
        v, lo, hi = r.get("value"), r.get("ci_lower"), r.get("ci_upper")
        if r["nct_id"] in seen or not v or not lo or not hi or v <= 0 or lo <= 0 or hi <= lo:
            continue
        z = stats.norm.ppf(0.5 + (r.get("ci_level") or 95) / 200)
        seen.add(r["nct_id"])  # one estimate per study: comparisons sharing a study are not independent
        used.append(r)
        ys.append(math.log(v))
        ses.append((math.log(hi) - math.log(lo)) / (2 * z))
    return used, np.array(ys), np.array(ses)


def categorical_data(rows: list[dict], baseline: bool) -> tuple[list[dict], list[str], np.ndarray]:
    units: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = r["nct_id"] if baseline else f"{r['nct_id']}|{r['registry_group']}|{r['raw_key'] if r.get('response_category') else ''}"
        units[key].append(r)
    categories: list[str] = []
    vectors, used = [], []
    for group in units.values():
        counts: dict[str, int] = defaultdict(int)
        total = None
        for r in group:
            label = str(r.get("response_category") or r.get("category") or "").strip().casefold()
            count = r.get("numerator")
            if count is None and r.get("rate") is not None and r.get("denominator"):
                count = round(r["rate"] * r["denominator"])
            if not label or count is None:
                continue
            counts[label] += int(count)
        if baseline:
            arm_n = {r["registry_group"]: r.get("denominator") for r in group}
            total = sum(v for v in arm_n.values() if v) or None
        else:
            total = max((r.get("denominator") or 0) for r in group) or None
        observed = sum(counts.values())
        if not counts or (total is not None and observed > total):
            continue
        if total is not None and total > observed and not baseline:
            counts["not_reported_or_other"] += total - observed
        if baseline and total is not None and observed != total:
            continue  # incomplete baseline distribution: missing categories are not zeros
        for label in counts:
            if label not in categories:
                categories.append(label)
        vectors.append(counts)
        used.extend(group)
    matrix = np.array([[v.get(c, 0) for c in categories] for v in vectors], dtype=float) if vectors else np.zeros((0, 0))
    return used, categories, matrix


# ----------------------------------------------------------------------------- fitting one context


def _fit_group(group: dict) -> dict[str, Any]:
    model, context, target, rows = group["model"], group["context"], group["target"], group["rows"]
    baseline = target["domain"] == "baseline"
    record: dict[str, Any] = {
        "parameter_id": parameter_id(context, target),
        "context": context,
        "target": target,
        "evidence_type": sorted({r["evidence_type"] for r in rows}),
        "reporting_filtered": any(r.get("reporting_filtered") for r in rows),
    }
    fit: Fit | None = None
    validation: dict[str, Any] = {}
    if model == "binomial":
        used, y, n = binomial_data(rows)
        if len(used):
            fitter = BetaBinomial()
            fit = fitter.fit(y, n)
            validation = _ppc_binomial(fitter, fit, y, n)
            if _level(len({r["nct_id"] for r in used})) == "A":
                validation["leave_one_study_out"] = _loso_binomial(used, y, n)
        support_n = int(n.sum()) if len(used) else 0
    elif model == "continuous":
        used, y, se, pooled_sd = continuous_data(rows, baseline)
        if len(used):
            scale = pooled_sd or max(float(np.max(np.abs(y))) * 0.25, 1e-3)
            fitter = NormalRandomEffects(0.0, 10 * (float(np.max(np.abs(y))) + scale), scale / 2)
            fit = fitter.fit(y, se)
            if pooled_sd is not None:
                fit.posterior["within_study_sd"] = pooled_sd
            validation = _ppc_normal(fitter, fit, y, se)
            if _level(len({r["nct_id"] for r in used})) == "A":
                validation["leave_one_study_out"] = _loso_normal(fitter, used, y, se, baseline)
        support_n = int(sum(r.get("denominator") or 0 for r in used))
    elif model == "relative_effect":
        used, y, se = ratio_data(rows)
        if len(used):
            fitter = NormalRandomEffects(0.0, 1.0, 0.5, log_scale=True)
            fit = fitter.fit(y, se)
            validation = _ppc_normal(fitter, fit, y, se)
            record["target"] = {**target, "statistic_family": normalise_comparison(used[0])["statistic_family"]}
            record["parameter_id"] = parameter_id(context, record["target"])
        support_n = 0
    else:
        used, categories, matrix = categorical_data(rows, baseline)
        if len(used) and matrix.shape[1] >= 2:
            fit = DirichletMultinomial().fit(matrix)
            fit.posterior["categories"] = categories
            fit.predictive["categories"] = categories
        support_n = int(matrix.sum()) if matrix.size else 0
    studies = len({r["nct_id"] for r in used}) if fit else 0
    record["support"] = {"studies": studies, "observations": len(used) if fit else 0, "total_N": support_n,
                         "level": _level(studies)}
    if fit is None:
        record.update(status="NO_RELIABLE_PARAMETER", model={"family": model})
        return {"record": record, "draws": None, "sources": []}
    failed = fit.diagnostics.get("grid_edge_mass", 0) > 0.01 or fit.diagnostics.get("importance_ess", 1e9) < 200
    record.update(
        status="NOT_PUBLISHED_DIAGNOSTIC_FAILURE" if failed else "PUBLISHED",
        model={"family": fit.family, "method": "exact grid posterior" if model != "categorical" else "importance sampling",
               "version": MODEL_VERSION},
        posterior_summary=fit.posterior,
        predictive_summary=fit.predictive,
        heterogeneity=fit.heterogeneity,
        diagnostics=fit.diagnostics,
        validation=validation,
    )
    if failed:
        return {"record": record, "draws": None, "sources": []}
    draws = {k: v.astype("float32") for k, v in fit.draws.items()} if record["support"]["level"] in {"A", "B"} else None
    record["posterior_draws"] = "stored" if draws else "regenerable_from_evidence (level C)"
    sources = [(record["parameter_id"], r["scientific_observation_id"], r["profile_id"]) for r in used]
    return {"record": record, "draws": draws, "sources": sources}


def _ppc_binomial(fitter: BetaBinomial, fit: Fit, y: np.ndarray, n: np.ndarray) -> dict:
    inside = 0
    for yi, ni in zip(y, n, strict=True):
        lo, hi = fitter.predictive_interval(fit, ni)
        inside += lo <= yi / ni <= hi
    return {"posterior_predictive_coverage_95": inside / len(y), "checked": len(y)}


def _ppc_normal(fitter: NormalRandomEffects, fit: Fit, y: np.ndarray, se: np.ndarray) -> dict:
    inside = sum(lo <= yi <= hi for yi, s in zip(y, se, strict=True) for lo, hi in [fitter.predictive_interval(fit, s)])
    return {"posterior_predictive_coverage_95": inside / len(y), "checked": len(y)}


def _loso_binomial(used: list[dict], y: np.ndarray, n: np.ndarray) -> dict:
    studies = sorted({r["nct_id"] for r in used})
    hits = tests = 0
    for held in studies:
        keep = np.array([r["nct_id"] != held for r in used])
        if keep.sum() == 0:
            continue
        fitter = BetaBinomial()
        fit = fitter.fit(y[keep], n[keep])
        for yi, ni in zip(y[~keep], n[~keep], strict=True):
            lo, hi = fitter.predictive_interval(fit, ni)
            hits += lo <= yi / ni <= hi
            tests += 1
    return {"coverage_95": hits / tests if tests else None, "held_out_observations": tests}


def _loso_normal(fitter: NormalRandomEffects, used: list[dict], y: np.ndarray, se: np.ndarray, baseline: bool) -> dict:
    hits = tests = 0
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        if keep.sum() == 0:
            continue
        fit = fitter.fit(y[keep], se[keep])
        lo, hi = fitter.predictive_interval(fit, se[i])
        hits += lo <= y[i] <= hi
        tests += 1
    return {"coverage_95": hits / tests if tests else None, "held_out_observations": tests}


# ----------------------------------------------------------------------------- publishing


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_parameter_asset(model_mappings: Path = Path("data/spa_work/model_outcome_mappings.json"), workers: int = 6) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    profiles = load_frozen_profiles()
    mappings = json.loads(model_mappings.read_text(encoding="utf-8")) if model_mappings.exists() else {}
    rows, dedup = atomize(profiles, mappings)
    rows = [normalise_comparison(r) if r["domain"] == "comparative" else r for r in rows]
    groups, skipped = build_contexts(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "posterior_draws").mkdir(exist_ok=True)

    # Layer B: the statistical evidence table
    columns = sorted({k for r in rows for k in r})
    pq.write_table(pa.table({c: [None if r.get(c) is None else str(r.get(c)) if isinstance(r.get(c), (dict, list)) else r.get(c)
                                 for r in rows] for c in columns}), OUT / "evidence_table.parquet")

    # Canonical outcome dictionary as observed in the corpus
    dictionary = Counter((r["raw_measure"], r["variable"], r["domain"], r["mapping_method"], r["statistic_family"])
                         for r in rows if r["domain"] not in {"baseline", "safety", "study_disposition"})
    pq.write_table(pa.table({
        "raw_measure": [k[0] for k in dictionary], "canonical_variable": [k[1] for k in dictionary],
        "domain": [k[2] for k in dictionary], "mapping_method": [k[3] for k in dictionary],
        "statistic_family": [k[4] for k in dictionary], "observations": list(dictionary.values()),
    }), OUT / "canonical_outcome_dictionary.parquet")

    records, sources = [], []
    draws_by_family: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(_fit_group, groups.values(), chunksize=64):
            record = result["record"]
            records.append(record)
            sources.extend(result["sources"])
            if result["draws"]:
                family = record["model"]["family"]
                store = draws_by_family[family]
                size = len(next(iter(result["draws"].values())))
                store["parameter_id"].extend([record["parameter_id"]] * size)
                store["draw"].extend(range(size))
                for name, values in result["draws"].items():
                    store[name].extend(values.tolist())
                for name in list(store):
                    if name not in {"parameter_id", "draw"} and name not in result["draws"]:
                        store[name].extend([None] * size)

    for family, store in draws_by_family.items():
        length = len(store["parameter_id"])
        table = {k: v + [None] * (length - len(v)) for k, v in store.items()}
        pq.write_table(pa.table(table), OUT / "posterior_draws" / f"{family}.parquet")

    with open(OUT / "parameter_index.jsonl", "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    flat = [{
        "parameter_id": r["parameter_id"], "status": r["status"], "model_family": r["model"]["family"],
        "level": r["support"]["level"], "studies": r["support"]["studies"], "observations": r["support"]["observations"],
        "total_N": r["support"]["total_N"], "disease": r["context"].get("disease"), "disease_cui": r["context"]["disease_cui"],
        "setting": r["context"]["setting"], "biomarker": r["context"]["biomarker"], "treatment": r["context"]["regimen"],
        "comparator": r["context"]["comparator"], "subgroup": r["context"]["subgroup_definition"],
        "domain": r["target"]["domain"], "variable": r["target"]["variable"], "statistic_family": r["target"]["statistic_family"],
        "event_class": r["target"].get("event_class"), "time": r["target"].get("time"), "time_unit": r["target"].get("time_unit"),
        "posterior_median": (r.get("posterior_summary") or {}).get("median"),
        "posterior_q025": (r.get("posterior_summary") or {}).get("q025"),
        "posterior_q975": (r.get("posterior_summary") or {}).get("q975"),
        "predictive_q025": (r.get("predictive_summary") or {}).get("q025"),
        "predictive_q975": (r.get("predictive_summary") or {}).get("q975"),
        "evidence_type": ",".join(r["evidence_type"]), "reporting_filtered": r["reporting_filtered"],
        "posterior_draws": r.get("posterior_draws"),
    } for r in records]
    pq.write_table(pa.table({k: [f[k] for f in flat] for k in flat[0]}), OUT / "parameter_index.parquet")
    pq.write_table(pa.table({"parameter_id": [s[0] for s in sources], "scientific_observation_id": [s[1] for s in sources],
                             "profile_id": [s[2] for s in sources]}), OUT / "parameter_sources.parquet")

    published = [r for r in records if r["status"] == "PUBLISHED"]
    loso = [r["validation"]["leave_one_study_out"] for r in published if "leave_one_study_out" in r.get("validation", {})]
    ppc = [r["validation"] for r in published if "posterior_predictive_coverage_95" in r.get("validation", {})]
    edge = [r["diagnostics"].get("grid_edge_mass", 0) for r in published]
    ess = [r["diagnostics"]["importance_ess"] for r in published if "importance_ess" in r["diagnostics"]]
    validation = {
        "posterior_predictive_coverage_95": {
            "observations": sum(v["checked"] for v in ppc),
            "coverage": sum(v["posterior_predictive_coverage_95"] * v["checked"] for v in ppc) / max(1, sum(v["checked"] for v in ppc)),
        },
        "leave_one_study_out_coverage_95": {
            "parameters": len(loso),
            "held_out_observations": sum(v["held_out_observations"] for v in loso),
            "coverage": sum((v["coverage_95"] or 0) * v["held_out_observations"] for v in loso) / max(1, sum(v["held_out_observations"] for v in loso)),
        },
        "grid_edge_mass_max": max(edge) if edge else None,
        "grids_with_edge_mass_over_1pct": sum(e > 0.01 for e in edge),
        "importance_ess_min": min(ess) if ess else None,
        "importance_fits_with_ess_below_200": sum(e < 200 for e in ess),
    }
    manifest = {
        "asset": "Simulation Parameter Asset",
        "version": "1.0.0-milestone-1",
        "created": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "model_version": MODEL_VERSION,
        "evidence_asset": {"path": str(ASSET / "profiles.jsonl"), "sha256": _sha256(ASSET / "profiles.jsonl")},
        "evidence_rows": dedup,
        "rows_not_modelled": skipped,
        "parameters": dict(Counter(f"{r['status']}:{r['support']['level']}" for r in records).most_common()),
        "parameters_by_family": dict(Counter(r["model"]["family"] for r in published)),
        "evidence_types": dict(Counter(r["evidence_type"] for r in rows)),
        "validation": validation,
        "scope_note": "Milestone 1: hierarchical binomial, continuous, log-ratio and Dirichlet-multinomial models. "
                      "Median survival times, survival curves, longitudinal models, modifiers and dependency layers are later stages.",
    }
    (OUT / "validation_report.json").write_text(json.dumps(validation, indent=1), encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")
    return manifest
