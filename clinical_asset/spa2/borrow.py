"""Milestone 2A: hierarchical borrowing for proportions, age and log ratios.

For every target (for example objective response rate, or serious adverse events) one tree is
fitted over all evidence of that target, following the ordered levels in hierarchy_rules.json.
Each published parameter is the tree node at its parameter level (for example a regimen within
disease and setting) and reports, separately:

* within_study_posterior - exact posterior from this context's own data only (Jeffreys prior);
* hierarchical_posterior - the partially pooled node posterior;
* future_study_predictive - a new study under this node, using heterogeneity learned across the
  whole target hierarchy, never estimated from the single context itself;
* shrinkage - raw estimate, leaf-only estimate, hierarchical estimate and standardised shift.
"""

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import special, stats

from .hierarchy import fit_hierarchy, predictive
from .taxonomy import regimen_signature

RULES = json.loads(Path(__file__).with_name("hierarchy_rules.json").read_text(encoding="utf-8"))
PARAMETER_LEVEL = {"efficacy_proportion": "regimen", "safety_proportion": "disease_family", "baseline_sex": "setting",
                   "baseline_age": "setting", "relative_effect": "regimen_pair"}
RATIO = {"hazard_ratio", "odds_ratio", "risk_ratio"}


def _q(x: np.ndarray) -> dict:
    q = np.quantile(x, [0.025, 0.25, 0.5, 0.75, 0.975])
    return {"mean": float(np.mean(x)), "q025": float(q[0]), "q25": float(q[1]), "median": float(q[2]),
            "q75": float(q[3]), "q975": float(q[4])}


def context_fields(row: dict, families: dict, classes: dict) -> dict:
    components = [c.strip() for c in str(row.get("regimen") or "").split(" + ") if c.strip()]
    class_sig, modality_sig = regimen_signature(components, classes) if components else ("unclassified", "unclassified")
    family = families.get(row.get("disease") or "", {})
    return {
        "disease_family": family.get("label", "other") if family.get("confidence", 0) >= 0.7 else "other",
        "disease": row.get("disease") or "unspecified",
        "setting": row.get("setting") or "unspecified",
        "modality": modality_sig,
        "class_signature": class_sig,
        "regimen": row.get("regimen") or "unspecified",
        "study": row["nct_id"],
        "arm": f"{row['nct_id']}|{row.get('registry_group')}",
    }


def _logit_obs(y: int, n: int) -> tuple[float, float]:
    return math.log((y + 0.5) / (n - y + 0.5)), 1 / (y + 0.5) + 1 / (n - y + 0.5)


def build_records(rows: list[dict], families: dict, classes: dict, age_factor: dict | None = None) -> dict[tuple, dict]:
    """(group, target) -> {'records': [...], 'target': {...}}; one observation per arm."""
    targets: dict[tuple, dict] = {}
    seen: set = set()

    def add(group: str, target: dict, record: dict) -> None:
        key = (group, json.dumps(target, sort_keys=True, default=str))
        unit = (key, record["arm"])
        if unit in seen:
            return
        seen.add(unit)
        targets.setdefault(key, {"group": group, "target": target, "records": []})["records"].append(record)

    sex: dict[str, dict] = defaultdict(lambda: {"female": 0, "N": None})
    for row in rows:
        ctx = context_fields(row, families, classes)
        family, domain = row["statistic_family"], row["domain"]
        if domain == "baseline" and row["variable"] == "sex":
            entry = sex[ctx["arm"]]
            entry.update(ctx=ctx, N=row.get("denominator"))
            if str(row.get("category") or "").casefold() in {"female", "women"}:
                entry["female"] = int(row.get("numerator") or 0)
            continue
        if domain == "baseline" and row["variable"] == "age" and family == "continuous_mean":
            # Registry age units vary (years, months, days); convert, or skip when unknown.
            factor = (age_factor or {}).get(row["nct_id"], 1.0)
            if factor and row.get("sd") and row.get("denominator") and row.get("value") is not None:
                value, sd = float(row["value"]) * factor, float(row["sd"]) * factor
                add("baseline_age", {"domain": "baseline", "variable": "age", "statistic_family": "mean"},
                    {**ctx, "y": value, "s2": sd**2 / row["denominator"], "n": row["denominator"],
                     "obs_id": row["scientific_observation_id"], "profile_id": row["profile_id"], "sd": sd})
            continue
        if domain == "comparative" and family in RATIO:
            v, lo, hi = row.get("value"), row.get("ci_lower"), row.get("ci_upper")
            if not (v and lo and hi and v > 0 and lo > 0 and hi > lo):
                continue
            z = stats.norm.ppf(0.5 + (row.get("ci_level") or 95) / 200)
            comp = [c.strip() for c in str(row.get("comparator") or "").split(" + ") if c.strip()]
            comp_sig = regimen_signature(comp, classes)[0] if comp else "unclassified"
            record = {**ctx, "class_pair": f"{ctx['class_signature']} vs {comp_sig}",
                      "regimen_pair": f"{ctx['regimen']} vs {row.get('comparator')}",
                      "y": math.log(v), "s2": ((math.log(hi) - math.log(lo)) / (2 * z)) ** 2, "n": None,
                      "obs_id": row["scientific_observation_id"], "profile_id": row["profile_id"]}
            add("relative_effect", {"domain": "comparative", "variable": row["variable"], "statistic_family": family}, record)
            continue
        if family != "proportion" or row.get("response_category") or not row.get("canonical"):
            continue
        if row.get("reporting_filtered"):
            continue  # threshold-selected event terms are modelled with censoring (toxicity.py)
        n = row.get("denominator")
        y = row.get("numerator")
        if y is None and row.get("rate") is not None and n:
            y = round(row["rate"] * n)
        if not n or y is None or not 0 <= y <= n:
            continue
        group = "safety_proportion" if domain == "safety" else "efficacy_proportion" if domain in RULES["groups"]["efficacy_proportion"]["applies_to_domains"] else None
        if group is None:
            continue
        target = {"domain": domain, "variable": row["variable"], "statistic_family": "proportion",
                  "event_class": row.get("event_class"), "time": row.get("time"), "time_unit": row.get("time_unit")}
        ly, s2 = _logit_obs(int(y), int(n))
        add(group, target, {**ctx, "y": ly, "s2": s2, "n": int(n), "count": int(y), "obs_id": row["scientific_observation_id"],
                            "profile_id": row["profile_id"]})
    for arm, entry in sex.items():
        if entry.get("N") and 0 <= entry["female"] <= entry["N"]:
            ly, s2 = _logit_obs(entry["female"], entry["N"])
            add("baseline_sex", {"domain": "baseline", "variable": "sex_female", "statistic_family": "proportion"},
                {**entry["ctx"], "y": ly, "s2": s2, "n": entry["N"], "count": entry["female"], "obs_id": f"sex|{arm}",
                 "profile_id": None})
    return targets


def fit_target(group: str, target: dict, records: list[dict], seed: int, samples: int | None = None) -> dict:
    rule = RULES["groups"][group]
    levels = rule["levels"]
    centre = 0.0
    if group == "baseline_age":
        centre = float(np.average([r["y"] for r in records], weights=[1 / r["s2"] for r in records]))
        records = [{**r, "y": r["y"] - centre} for r in records]
    samples = samples or (1500 if len(levels) > 3 else 1000)
    fit = fit_hierarchy(records, levels, rule["tau_prior_scale"], rule["root_sd"], samples=samples, draws=400, seed=seed)
    return {"fit": fit, "centre": centre, "records": records}


def _transform(group: str, x: np.ndarray, centre: float) -> np.ndarray:
    if group in {"efficacy_proportion", "safety_proportion", "baseline_sex"}:
        return special.expit(x)
    if group == "relative_effect":
        return np.exp(x)
    return x + centre


def publish_target(group: str, target: dict, fitted: dict, seed: int) -> list[dict]:
    fit, centre, records = fitted["fit"], fitted["centre"], fitted["records"]
    levels = fit.levels
    depth = levels.index(PARAMETER_LEVEL[group]) + 1
    rng = np.random.default_rng(seed)
    by_node: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        by_node[tuple(r[level] for level in levels[:depth])].append(r)
    taus = {level: _q(fit.tau_draws[:, i]) for i, level in enumerate(levels)}
    out = []
    for node, recs in by_node.items():
        draws = fit.node_draws[node]
        new_path = node + tuple(f"__new_{level}__" for level in levels[depth:])
        future = predictive(fit, new_path, rng)
        studies = sorted({r["study"] for r in recs})
        level = "A" if len(studies) >= 3 else "B" if len(studies) == 2 else "C"
        hier = _transform(group, draws, centre)
        record = {
            "group": group, "target": target,
            "context": dict(zip(levels[:depth], node, strict=True)),
            "support": {"studies": len(studies), "arms": len(recs), "total_N": int(sum(r.get("n") or 0 for r in recs)),
                        "level": level},
            "hierarchical_posterior": _q(hier),
            "future_study_predictive": _q(_transform(group, future, centre)),
            "heterogeneity": {"tau_by_level": taus, "source": "estimated across the target hierarchy",
                              "tau_scale": RULES["groups"][group]["analysis_scale"]},
            "tau_importance_ess": fit.ess,
        }
        # Leaf-only (this context's data alone) and raw estimates for the shrinkage record.
        if group in {"efficacy_proportion", "safety_proportion", "baseline_sex"}:
            y = sum(r["count"] for r in recs)
            n = sum(r["n"] for r in recs)
            leaf = stats.beta(0.5 + y, 0.5 + n - y)
            record["within_study_posterior"] = {
                "distribution": f"Beta({0.5 + y}, {0.5 + n - y})",
                "median": float(leaf.median()), "q025": float(leaf.ppf(0.025)), "q975": float(leaf.ppf(0.975)),
                "note": "exact posterior from this context's data alone" + (" (single study)" if level == "C" else
                                                                           " (arms pooled as one population, ignores heterogeneity)"),
            }
            raw = y / n if n else None
            leaf_median = float(leaf.median())
            leaf_sd_logit = math.sqrt(1 / (y + 0.5) + 1 / (n - y + 0.5))
            hier_median = float(np.median(hier))
            record["shrinkage"] = {
                "raw_estimate": raw, "leaf_only_median": leaf_median, "hierarchical_median": hier_median,
                "standardised_shift": (special.logit(hier_median) - special.logit(leaf_median)) / leaf_sd_logit,
            }
        else:
            w = np.array([1 / r["s2"] for r in recs])
            yv = np.array([r["y"] for r in recs])
            pooled, se = float((w * yv).sum() / w.sum()), float(1 / math.sqrt(w.sum()))
            leaf = _transform(group, np.array([pooled, pooled - 1.96 * se, pooled + 1.96 * se]), centre)
            record["within_study_posterior"] = {"median": float(leaf[0]), "q025": float(leaf[1]), "q975": float(leaf[2]),
                                                "note": "inverse-variance estimate from this context's data alone"}
            if group == "baseline_age":
                record["within_study_sd"] = float(np.median([r["sd"] for r in recs]))
            record["shrinkage"] = {"leaf_only_median": float(leaf[0]), "hierarchical_median": float(np.median(hier)),
                                   "standardised_shift": (float(np.median(draws)) - pooled) / se}
        record["parameter_id"] = hashlib.sha1(json.dumps([group, target, record["context"]], sort_keys=True, default=str).encode()).hexdigest()[:16]
        record["draws"] = {"hierarchical": hier.astype("float32"), "future_study": _transform(group, future, centre).astype("float32")}
        record["source_observations"] = [r["obs_id"] for r in recs]
        out.append(record)
    return out


def hyperparameter_rows(group: str, target: dict, fitted: dict) -> list[dict]:
    """Posterior summaries of every internal node (disease, class, regimen levels)."""
    fit, centre = fitted["fit"], fitted["centre"]
    rows = []
    for key, draws in fit.node_draws.items():
        level = fit.levels[len(key) - 1]
        if level in {"study", "arm"}:
            continue
        summary = _q(_transform(group, draws, centre))
        rows.append({"group": group, "target": json.dumps(target, default=str), "level": level,
                     "path": " / ".join(map(str, key)), "node": str(key[-1]), **{f"posterior_{k}": v for k, v in summary.items()}})
    return rows
