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


def augment(population_lock: Path, family: str | None, phase: str | None, out_dir: Path, seed: int = 20260929) -> dict:
    """`population_lock` may be a locked population or a population stage directory not yet locked."""
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
        levels = rng.choice(5, size=len(pats), p=np.array(ecog["p"]) / sum(ecog["p"]))
        for p, lvl in zip(pats, levels, strict=True):
            p["var:ecog_performance_status"] = {"value": int(lvl), "unit": None}
        added["var:ecog_performance_status"] = ecog
    for var, dist, lo, hi, unit in (("var:weight", weight, 30, 200, "kg"), ("var:height", height, 120, 210, "cm")):
        if dist["status"] == "RESOLVED":
            for p in pats:
                if (p.get("demographic:age") or {}).get("value", 99) >= 18:        # adult distributions only
                    p[var] = {"value": round(float(np.clip(rng.normal(dist["mean"], dist["sd"]), lo, hi)), 1), "unit": unit}
            added[var] = dist
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "population.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in pats)
    for f in ("population_model.json", "population_report.md"):
        if (Path(population_lock) / f).exists():
            (out / f).write_text((Path(population_lock) / f).read_text(encoding="utf-8"), encoding="utf-8")
    summary = {"base_population": str(population_lock), "family": family, "phase": phase, "added_variables": added,
               "caveat": "baseline distributions of enrolled participants in similar trials (truncated by their eligibility)"}
    (out / "baseline_extra_summary.json").write_text(json.dumps({"summary": summary}, indent=1), encoding="utf-8")
    return summary
