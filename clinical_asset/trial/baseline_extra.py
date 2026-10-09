"""Baseline variables beyond demographics, from registry baseline measures (data/evidence_baseline_v1):
ECOG performance status, weight and height, added to a locked population as a new population version.

ECOG: each trial's reported category counts (any common spelling: '0', 'Grade 1', 'ECOG = 2', '1 - Restricted but
ambulatory') give its distribution over levels 0-4; trials that report at least three separate levels are pooled
(equal weight per trial) within the protocol's disease family and phase, then family, then all oncology, requiring at
least MIN_TRIALS trials. Weight and height: trial-level means and SDs pooled the same way (normal, truncated to
plausible ranges).

These are ENROLLED participants' distributions (after each source trial's own eligibility): a protocol whose limit is
narrower than the source trials' (e.g. ECOG 0-1) screens some patients out; one that is broader cannot be assessed for
the patients the sources excluded. Every added value names its source.
"""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

MIN_TRIALS = 5
BASELINE = Path("data/evidence_baseline_v1/baseline_measures.parquet")


def ecog_level(label: str | None) -> int | None:
    t = (label or "").strip().lower()
    if not t or re.search(r"missing|unknown|not (reported|available|done)|n/?a\b", t):
        return None
    if re.search(r"\d\s*(-|–|to|/|,|or)\s*\d", t[:12]) or re.search(r"[<>≤≥]", t[:6]):
        return None                                    # combined categories ('0-1', '>= 2') are not one level
    m = re.match(r"^(?:ecog\s*(?:ps|performance status)?\s*[=:]?\s*|grade\s*|ps\s*|who\s*)?([0-5])\b", t)
    return int(m.group(1)) if m and int(m.group(1)) <= 4 else None


@lru_cache(maxsize=1)
def _rows() -> list[dict]:
    import pyarrow.parquet as pq

    from ..cutoff import excluded

    drop = excluded()                      # an evidence cut-off in force drops later trials
    return [r for r in pq.read_table(BASELINE, columns=["nct_id", "phase", "condition_mesh", "variable", "param_type", "dispersion_type",
                                                        "unit", "class_title", "category", "group_id", "is_total_group", "n", "value",
                                                        "spread"]).to_pylist() if r["nct_id"] not in drop]


@lru_cache(maxsize=None)
def _family(mesh: str) -> str:
    from ..planning.operational import family_of_terms
    from .journey_evidence import _mesh_map

    return family_of_terms([t for t in (mesh or "").split("; ") if t], _mesh_map())[0]


def _ecog_trials() -> list[dict]:
    per: dict = {}
    for r in _rows():
        if r["variable"] != "ecog_performance_status" or r["param_type"] not in ("COUNT_OF_PARTICIPANTS", "NUMBER") or r["value"] is None:
            continue
        lvl = ecog_level(r["category"]) if r["category"] else ecog_level(r["class_title"])
        if lvl is None:
            continue
        t = per.setdefault(r["nct_id"], {"nct_id": r["nct_id"], "phase": r["phase"], "mesh": r["condition_mesh"], "total": {}, "groups": {}})
        target = t["total"] if r["is_total_group"] else t["groups"].setdefault(r["group_id"], {})
        target[lvl] = target.get(lvl, 0) + r["value"]
    out = []
    for t in per.values():
        counts = t["total"] or {}
        if not counts:
            for g in t["groups"].values():
                for k, v in g.items():
                    counts[k] = counts.get(k, 0) + v
        n = sum(counts.values())
        if n >= 5 and len(counts) >= 3:
            out.append({"nct_id": t["nct_id"], "phase": t["phase"], "family": _family(t["mesh"]), "n": n,
                        "p": [counts.get(k, 0) / n for k in range(5)]})
    return out


def ecog_distribution(family: str | None, phase: str | None) -> dict:
    trials = _ecog_trials()
    for label, sel in ((f"{family}, {phase}", [t for t in trials if t["family"] == family and t["phase"] == phase]),
                       (f"{family}", [t for t in trials if t["family"] == family]),
                       (f"all oncology, {phase}", [t for t in trials if t["phase"] == phase]),
                       ("all oncology", trials)):
        if len(sel) >= MIN_TRIALS:
            P = np.array([t["p"] for t in sel])
            return {"status": "RESOLVED", "levels": [0, 1, 2, 3, 4], "p": P.mean(axis=0).tolist(),
                    "trial_range_10_90": np.quantile(P, [0.1, 0.9], axis=0).round(3).tolist(),
                    "trials": len(sel), "participants": int(sum(t["n"] for t in sel)),
                    "source": f"registry baseline ECOG of enrolled participants ({label}; {len(sel)} trials)"}
    return {"status": "UNSUPPORTED", "reason": "fewer than 5 trials report ECOG by level"}


def continuous_distribution(variable: str, family: str | None, unit_pattern: str, lo: float, hi: float) -> dict:
    trials = {}
    for r in _rows():
        if r["variable"] != variable or r["param_type"] != "MEAN" or r["value"] is None or not r["n"]:
            continue
        if not re.search(unit_pattern, r["unit"] or "", re.I) or not (lo <= r["value"] <= hi):
            continue
        if r["dispersion_type"] != "STANDARD_DEVIATION" or not r["spread"]:
            continue
        t = trials.setdefault(r["nct_id"], {"family": _family(r["condition_mesh"]), "rows": []})
        if r["is_total_group"] or not any(x["total"] for x in t["rows"]):
            t["rows"].append({"mean": r["value"], "sd": r["spread"], "n": r["n"], "total": r["is_total_group"]})
    for label, sel in ((family, [t for t in trials.values() if t["family"] == family]), ("all oncology", list(trials.values()))):
        rows = [x for t in sel for x in (t["rows"] if not any(y["total"] for y in t["rows"]) else [y for y in t["rows"] if y["total"]])]
        if len(sel) >= MIN_TRIALS:
            n = np.array([x["n"] for x in rows])
            m = np.array([x["mean"] for x in rows])
            s = np.array([x["sd"] for x in rows])
            mean = float(np.sum(n * m) / n.sum())
            var = float(np.sum(n * (s ** 2 + (m - mean) ** 2)) / n.sum())       # pooled mixture variance
            return {"status": "RESOLVED", "mean": mean, "sd": var ** 0.5, "trials": len(sel), "participants": int(n.sum()),
                    "source": f"registry baseline {variable} of enrolled participants ({label}; {len(sel)} trials)"}
    return {"status": "UNSUPPORTED", "reason": f"fewer than {MIN_TRIALS} trials report {variable} as mean and SD"}


# further baseline variables reported in registry baseline tables (L065): (key, registry variable, unit pattern, plausible
# range, unit) for continuous ones; (key, registry variable, label -> level map) for categorical ones. Each is generated
# only from at least MIN_TRIALS comparable trials (disease family, else all oncology), independently of the others (the
# registry tables give no joint distribution); anything else stays not simulated.
CONTINUOUS_EXTRA = (("var:body_mass_index", "body_mass_index", r"kg|kilogram", 12, 60, "kg/m2"),
                    ("var:body_surface_area", "body_surface_area", r"m\^?2|m²|square", 1.0, 3.0, "m2"),
                    ("var:hemoglobin", "hemoglobin", r"g/dl|gram per deciliter", 5, 20, "g/dL"),
                    ("var:heart_rate", "heart_rate", r"beat|bpm", 40, 160, "beats/min"),
                    ("var:systolic_blood_pressure", "systolic_blood_pressure", r"mm\s*hg", 80, 220, "mmHg"),
                    ("var:diastolic_blood_pressure", "diastolic_blood_pressure", r"mm\s*hg", 40, 130, "mmHg"),
                    ("var:creatinine_clearance", "creatinine_clearance", r"ml/min", 15, 250, "mL/min"),
                    ("var:left_ventricular_ejection_fraction", "left_ventricular_ejection_fraction", r"%|percent", 20, 85, "%"))
SMOKING = ((r"^\s*(never|non[- ]?smoker|never smok)", "never"), (r"^\s*(former|ex[- ]?smoker|past|previous|quit)", "former"),
           (r"^\s*current", "current"))
YES_NO = ((r"^\s*(yes|present)\b", "present"), (r"^\s*(no|absent)\b", "absent"))
CATEGORICAL_EXTRA = (("var:smoking_status", "smoking_status", SMOKING, ("never", "former", "current")),
                     ("var:diabetes", "diabetes", YES_NO, ("present", "absent")),
                     ("var:hypertension", "hypertension", YES_NO, ("present", "absent")))


def categorical_distribution(variable: str, family: str | None, mapping: tuple, levels: tuple) -> dict:
    """Pooled category shares (equal weight per trial) from trials reporting at least two mapped levels: the disease
    family, then all oncology, with at least MIN_TRIALS trials."""
    per: dict = {}
    for r in _rows():
        if r["variable"] != variable or r["param_type"] not in ("COUNT_OF_PARTICIPANTS", "NUMBER") or r["value"] is None:
            continue
        label = (r["category"] or r["class_title"] or "").strip()
        lv = next((name for pat, name in mapping if re.search(pat, label, re.I)), None)
        if lv is None:
            continue
        t = per.setdefault(r["nct_id"], {"family": _family(r["condition_mesh"]), "total": {}, "groups": {}})
        target = t["total"] if r["is_total_group"] else t["groups"].setdefault(r["group_id"], {})
        target[lv] = target.get(lv, 0) + r["value"]
    trials = []
    for t in per.values():
        counts = dict(t["total"])
        if not counts:
            for g in t["groups"].values():
                for k, v in g.items():
                    counts[k] = counts.get(k, 0) + v
        n = sum(counts.values())
        if n >= 5 and len(counts) >= 2:
            trials.append({"family": t["family"], "n": n, "p": [counts.get(k, 0) / n for k in levels]})
    for label, sel in ((family, [t for t in trials if t["family"] == family]), ("all oncology", trials)):
        if len(sel) >= MIN_TRIALS:
            P = np.array([t["p"] for t in sel])
            return {"status": "RESOLVED", "levels": list(levels), "p": P.mean(axis=0).tolist(), "trials": len(sel),
                    "participants": int(sum(t["n"] for t in sel)), "trial_range_10_90": np.quantile(P, [0.1, 0.9], axis=0).round(3).tolist(),
                    "source": f"registry baseline {variable} of enrolled participants ({label}; {len(sel)} trials)"}
    return {"status": "UNSUPPORTED", "reason": f"fewer than {MIN_TRIALS} trials report {variable} by category"}


def augment(population_lock: Path, family: str | None, phase: str | None, out_dir: Path, seed: int = 20260929,
            spec: dict | None = None, model=None, own_nct: str | None = None) -> dict:
    """`population_lock` may be a locked population or a population stage directory not yet locked. With the StudySpec
    and a model, the protocol's subgroup factors are generated and every factor's outcome effect is found (L039)."""
    from .lock import LOCK_FILE, verify

    if (Path(population_lock) / LOCK_FILE).exists():
        verify(population_lock)
    rng = np.random.default_rng(seed)
    pats = [json.loads(line) for line in open(Path(population_lock) / "population.jsonl", encoding="utf-8")]
    ecog = ecog_distribution(family, phase)
    weight = continuous_distribution("weight", family, r"kg|kilogram", 30, 150)
    height = continuous_distribution("height", family, r"cm|centimet", 120, 200)
    added = {}
    if ecog["status"] == "RESOLVED":
        # each patient's ECOG follows their age (corpus regression of the ECOG >= 1 share on age, L055), around the
        # population's mean age so the population's ECOG distribution stays the evidence's
        from . import patient_risk
        risk = patient_risk.load(seed)
        ages = [(p.get("demographic:age") or {}).get("value") for p in pats]
        known = [a for a in ages if a is not None]
        mean_age = sum(known) / len(known) if known else None
        for p, age in zip(pats, ages, strict=True):
            probs = patient_risk.ecog_given_age(ecog["p"], age, mean_age, risk)
            p["var:ecog_performance_status"] = {"value": int(rng.choice(5, p=np.array(probs) / sum(probs))), "unit": None}
        added["var:ecog_performance_status"] = {**ecog, "by_age": (risk or {}).get("ecog_by_age") or {"status": "NOT_ESTIMATED"}}
    for var, dist, lo, hi, unit in (("var:weight", weight, 30, 200, "kg"), ("var:height", height, 120, 210, "cm")):
        if dist["status"] == "RESOLVED":
            for p in pats:
                if (p.get("demographic:age") or {}).get("value", 99) >= 18:        # adult distributions only
                    p[var] = {"value": round(float(np.clip(rng.normal(dist["mean"], dist["sd"]), lo, hi)), 1), "unit": unit}
            added[var] = dist
    # further baseline characteristics: vitals, laboratory values, comorbidities and smoking history (L065)
    rng_x = np.random.default_rng(seed + 23)
    not_simulated = []
    for var, reg, unit_pat, lo, hi, unit in CONTINUOUS_EXTRA:
        if any(var in p for p in pats[:50]):
            continue
        if var in ("var:body_mass_index", "var:body_surface_area") and all(k in added for k in ("var:weight", "var:height")):
            # derived from the patient's own weight and height (BMI; Mosteller BSA), never drawn independently of them
            for p in pats:
                w, h = (p.get("var:weight") or {}).get("value"), (p.get("var:height") or {}).get("value")
                if w and h:
                    v = w / (h / 100) ** 2 if var == "var:body_mass_index" else math.sqrt(w * h / 3600)
                    p[var] = {"value": round(float(v), 2 if var == "var:body_surface_area" else 1), "unit": unit}
            added[var] = {"status": "RESOLVED", "source": "derived from the patient's weight and height"
                          + (" (Mosteller)" if var == "var:body_surface_area" else "")}
            continue
        dist = continuous_distribution(reg, family, unit_pat, lo, hi)
        if dist["status"] != "RESOLVED":
            not_simulated.append({"variable": var, "reason": dist["reason"]})
            continue
        for p in pats:
            if (p.get("demographic:age") or {}).get("value", 99) >= 18:
                p[var] = {"value": round(float(np.clip(rng_x.normal(dist["mean"], dist["sd"]), lo, hi)), 1), "unit": unit}
        added[var] = {**dist, "note": "generated independently of the other baseline variables (no joint registry distribution)"}
    for var, reg, mapping, levels_x in CATEGORICAL_EXTRA:
        if any(var in p for p in pats[:50]):
            continue
        dist = categorical_distribution(reg, family, mapping, levels_x)
        if dist["status"] != "RESOLVED":
            not_simulated.append({"variable": var, "reason": dist["reason"]})
            continue
        draws = rng_x.choice(len(levels_x), size=len(pats), p=np.array(dist["p"]) / sum(dist["p"]))
        for p, i in zip(pats, draws, strict=True):
            lv = levels_x[int(i)]
            p[var] = {"value": lv == "present", "unit": None} if set(levels_x) == {"present", "absent"} else lv
        added[var] = {**dist, "note": "generated independently of the other baseline variables (no joint registry distribution)"}
    not_simulated.append({"variable": "concomitant medications", "reason": "registry baseline tables do not report medications"})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    subgroups = None
    disease = None
    if spec is not None and model is not None:
        # the target disease's own characteristics (histology, stage, biomarkers) from registry baseline tables (L062)
        from ..cutoff import excluded
        from . import disease_variables as dv

        disease = dv.generate(model, spec, pats, family, phase, set(excluded()) | ({own_nct} if own_nct else set()),
                              np.random.default_rng(seed + 11))
        from . import subgroup_evidence as sge

        subgroups = sge.build(model, spec, pats, family, phase, own_nct, np.random.default_rng(seed + 7))
        (out / sge.EVIDENCE_FILE).write_text(json.dumps(subgroups, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    with open(out / "population.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in pats)
    for f in ("population_model.json", "population_report.md"):
        if (Path(population_lock) / f).exists():
            (out / f).write_text((Path(population_lock) / f).read_text(encoding="utf-8"), encoding="utf-8")
    summary = {"base_population": str(population_lock), "family": family, "phase": phase, "added_variables": added,
               "not_simulated": not_simulated,
               "caveat": "baseline distributions of enrolled participants in similar trials (truncated by their eligibility)"}
    if disease:
        summary["disease_variables"] = disease
        rep = out / "population_report.md"
        L = ["", "## Disease characteristics from registry evidence (L062)", "",
             "| Variable | Shares | Trials | Source |", "| --- | --- | ---: | --- |"]
        L += [f"| {g['key']} | {', '.join(f'{lv} {p:.0%}' for lv, p in zip(g['levels'], g['p'], strict=True))} | {g['trials']} | {g['source']} |"
              for g in disease["generated"]]
        L += ["", "Still unknown (no sufficient evidence): " + ", ".join(f"{u['key']} ({u['reason'][:60]})" for u in disease["unresolved"])]
        if added:
            L += ["", "## Baseline variables added from evidence", ""] + [f"- {k}" for k in added]
        rep.write_text((rep.read_text(encoding="utf-8") if rep.exists() else "") + "\n".join(L) + "\n", encoding="utf-8")
    if subgroups:
        summary["subgroup_factors"] = [{"factor": f["text"], "variable": f["key"], "kind": f["kind"],
                                        "prevalence": (f.get("prevalence") or {}).get("source"),
                                        "effect": (f.get("effects") or {}).get("source")} for f in subgroups["factors"]]
    (out / "baseline_extra_summary.json").write_text(json.dumps({"summary": summary}, indent=1), encoding="utf-8")
    return summary
