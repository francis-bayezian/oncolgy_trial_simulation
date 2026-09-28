"""Subgroup estimates of a trial-level proportion from the study-level evidence.

A prediction pooled over every trial of a disease family mixes unlike trials (radiotherapy alone, placebo, adult
glioma regimens and a paediatric multi-agent regimen are all 'central nervous system'); its interval is wide and its
centre can be far from the protocol. Instead:

* the evidence is the study-level arms of the evidence build (Simulation Parameter Asset V1 evidence table, the
  records V3 is fitted on), each tagged with its study's phase and age group from its registry record;
* the HEADLINE is the random-effects (DerSimonian-Laird, logit scale) average of the most specific subgroup that holds
  at least `min_studies` studies, trying in order: the same regimen; the same age group, phase and overlapping drug
  classes; the same age group and overlapping classes; the same age group and phase; the same age group; overlapping
  classes; the whole disease family (on the five development protocols age group and phase explained the reported
  serious-event shares better than drug-class overlap). Its 95% and 50% confidence intervals are
  for the subgroup's AVERAGE, the informative quantity for a decision; the spread of single trials around it
  (between-study tau) is reported next to it, not instead of it;
* the BREAKDOWN gives the same estimate for every subgroup of the family (age group, phase, class overlap, regimen),
  with its number of studies and patients, and flags the protocol's own subgroup when the evidence holds fewer than
  `min_studies` studies of it: those are the subgroups that need attention.
"""

import json
import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import stats

V1_TABLE = Path("data/simulation_parameters_v1/evidence_table.parquet")
RAW = Path("data/raw/ctgov")
MIN_STUDIES = 3


def evidence_provenance() -> dict:
    """The frozen evidence the estimates read, verified: the V1 evidence table must match the checksum recorded in the
    Simulation Parameter Asset V3 manifest (the table V3 was fitted on); anything else stops the estimate."""
    import hashlib

    recorded = json.loads(Path("data/simulation_parameters_v3/manifest.json").read_text(encoding="utf-8"))["inputs"]["parameter_asset_v1"]["evidence_table_sha256"]
    actual = hashlib.sha256(V1_TABLE.read_bytes()).hexdigest()
    if actual != recorded:
        raise RuntimeError(f"{V1_TABLE} does not match the checksum frozen in the V3 manifest: the evidence has changed")
    maps = {name: hashlib.sha256(Path(f"data/spa_work/{name}").read_bytes()).hexdigest() for name in ("disease_families.json", "drug_classes.json")}
    return {"evidence_table": {"path": str(V1_TABLE), "sha256": actual, "verified_against": "simulation_parameters_v3 manifest"}, "maps": maps}


@lru_cache(maxsize=1)
def _targets() -> dict:
    import pyarrow.parquet as pq

    from ..spa2 import borrow as b2

    evidence_provenance()                       # refuses changed evidence
    rows = pq.read_table(V1_TABLE).to_pylist()
    families = json.loads(Path("data/spa_work/disease_families.json").read_text(encoding="utf-8"))
    classes = json.loads(Path("data/spa_work/drug_classes.json").read_text(encoding="utf-8"))
    return b2.build_records(rows, families, classes)


@lru_cache(maxsize=4096)
def study_attributes(nct: str) -> dict:
    path = RAW / f"{nct}.json"
    if not path.exists():
        return {"phase": "unknown", "age_group": "unknown"}
    ps = json.loads(path.read_text(encoding="utf-8"))["protocolSection"]
    ages = set(ps.get("eligibilityModule", {}).get("stdAges", []))
    group = "pediatric" if ages and "OLDER_ADULT" not in ages and "CHILD" in ages else "adult" if "CHILD" not in ages else "mixed"
    return {"phase": "+".join(sorted(ps.get("designModule", {}).get("phases") or [])) or "unknown", "age_group": group}


def records(target_variable: str) -> list[dict]:
    """Study-level arms reporting the proportion (count, n), tagged with phase and age group."""
    out = []
    for (group, target), spec in _targets().items():
        if not group.endswith("proportion") or f'"{target_variable}"' not in target and not target_variable in target:
            continue
        t = json.loads(target)
        if target_variable not in (t.get("variable"), t.get("event_class")) and not (target_variable == "serious_adverse_event"
                                                                                     and t.get("event_class") == "serious_any_cause"):
            continue
        for r in spec["records"]:
            if r.get("count") is None or not r.get("n"):
                continue
            out.append({**r, **study_attributes(r["study"])})
    return out


def pooled(recs: list[dict]) -> dict | None:
    """DerSimonian-Laird random-effects average on the logit scale (one arm per record, 0.5 continuity)."""
    if not recs:
        return None
    k = np.array([r["count"] for r in recs], dtype=float)
    n = np.array([r["n"] for r in recs], dtype=float)
    y = np.log((k + 0.5) / (n - k + 0.5))
    v = 1 / (k + 0.5) + 1 / (n - k + 0.5)
    w = 1 / v
    mu_f = float(np.sum(w * y) / np.sum(w))
    q = float(np.sum(w * (y - mu_f) ** 2))
    df = len(recs) - 1
    c = float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
    tau2 = max(0.0, (q - df) / c) if df > 0 and c > 0 else 0.0
    ws = 1 / (v + tau2)
    mu = float(np.sum(ws * y) / np.sum(ws))
    se = math.sqrt(1 / float(np.sum(ws)))
    ex = lambda x: float(1 / (1 + math.exp(-x)))
    z50, z95 = stats.norm.ppf(0.75), stats.norm.ppf(0.975)
    tau = math.sqrt(tau2)
    return {"estimate": ex(mu), "ci50": [ex(mu - z50 * se), ex(mu + z50 * se)], "ci95": [ex(mu - z95 * se), ex(mu + z95 * se)],
            "between_study_tau_logit": tau, "single_trial_80": [ex(mu - 1.2816 * math.hypot(se, tau)), ex(mu + 1.2816 * math.hypot(se, tau))],
            "studies": len({r["study"] for r in recs}), "arms": len(recs), "patients": int(n.sum())}


def _classes(sig: str) -> set[str]:
    return {c for c in (sig or "").split("+") if c and c not in {"other", "unclassified", "supportive_care", "placebo_or_no_active_treatment"}}


def estimate(target_variable: str, family: str, classes: list[str], agents: list[str], age_group: str, phase: str | None = None,
             exclude_studies: set[str] | None = None, min_studies: int = MIN_STUDIES, order: list[str] | None = None) -> dict:
    recs = [r for r in records(target_variable) if r["disease_family"] == family and r["study"] not in (exclude_studies or set())]
    if not recs:
        return {"status": "UNRESOLVED", "reason": f"no study of {target_variable} in the {family} family"}
    mine = set(classes) - {"other", "unclassified"}
    agent_set = {a.casefold() for a in agents if a}

    def regimen_of(r):
        return {x.strip().casefold() for x in (r.get("regimen") or "").split("+") if x.strip()}
    rungs = _rungs(recs, mine, agent_set, age_group, phase, regimen_of)
    order = ladder_order(target_variable) if order is None else order
    ladder = [(rungs[k][0], rungs[k][1]) for k in order if k in rungs] + [("whole disease family", recs)]
    level, chosen = next(((lv, rs) for lv, rs in ladder if len({r["study"] for r in rs}) >= min_studies), ladder[-1])
    breakdown = {}
    for key, f in (("age group", lambda r: r["age_group"]), ("phase", lambda r: r["phase"]),
                   ("drug classes", lambda r: "overlapping" if mine and _classes(r["class_signature"]) & mine else "not overlapping")):
        groups: dict[str, list] = {}
        for r in recs:
            groups.setdefault(f(r), []).append(r)
        breakdown[key] = {g: pooled(rs) for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1]))}
    own = rungs["age_classes"][1]
    own_studies = len({r["study"] for r in own})
    return {"status": "RESOLVED", "target": target_variable, "family": family, "headline_subgroup": level, "headline": pooled(chosen),
            "breakdown": breakdown,
            "protocol_subgroup": {"definition": f"{age_group} trials in {family} with overlapping drug classes", "studies": own_studies,
                                  "attention": own_studies < min_studies,
                                  "note": ("the evidence holds too few trials like this protocol: the headline borrows from other subgroups"
                                           if own_studies < min_studies else "represented")},
            "family_mixture_studies": len({r["study"] for r in recs})}


RUNG_KEYS = ("regimen", "age_phase_classes", "age_classes", "age_phase", "age", "classes", "phase")
LADDER_FILE = Path("data/validation/subgroup_ladder.json")


def _rungs(recs, mine, agent_set, age_group, phase, regimen_of) -> dict:
    overlap = [r for r in recs if mine and _classes(r["class_signature"]) & mine]
    same_age = [r for r in recs if r["age_group"] == age_group]
    return {"regimen": ("same regimen", [r for r in recs if agent_set and regimen_of(r) == agent_set]),
            "age_phase_classes": (f"{age_group} {phase} trials with overlapping drug classes",
                                  [r for r in overlap if r["age_group"] == age_group and phase and r["phase"] == phase]),
            "age_classes": (f"{age_group} trials with overlapping drug classes", [r for r in overlap if r["age_group"] == age_group]),
            "age_phase": (f"{age_group} {phase} trials", [r for r in same_age if phase and r["phase"] == phase]),
            "age": (f"{age_group} trials", same_age),
            "classes": ("trials with overlapping drug classes", overlap),
            "phase": (f"{phase} trials", [r for r in recs if phase and r["phase"] == phase])}


def ladder_order(target_variable: str) -> list[str]:
    """The rung order chosen on held-out studies (choose_ladder); the default order until one is chosen."""
    if LADDER_FILE.exists():
        doc = json.loads(LADDER_FILE.read_text(encoding="utf-8"))
        if target_variable in doc:
            return doc[target_variable]["order"]
    return ["regimen", "age_phase_classes", "age_classes", "age_phase", "age", "classes"]


def choose_ladder(target_variable: str, min_studies: int = MIN_STUDIES) -> dict:
    """Leave-one-study-out over the evidence: each rung alone (falling back to the disease family when the rung holds
    fewer than `min_studies` other studies) predicts every held-out study; rungs are ordered by median absolute error
    where they apply, best first. No protocol under test is in the evidence."""
    recs = records(target_variable)
    by_study: dict[str, list] = {}
    for r in recs:
        by_study.setdefault(r["study"], []).append(r)
    errors: dict[str, list] = {k: [] for k in RUNG_KEYS}
    family_errors = []
    for study, arms in by_study.items():
        a = max(arms, key=lambda r: r["n"])
        obs = a["count"] / a["n"]
        others = [r for r in recs if r["disease_family"] == a["disease_family"] and r["study"] != study]
        fam = pooled(others)
        if fam is None:
            continue
        family_errors.append(abs(fam["estimate"] - obs))
        agents = {x.strip().casefold() for x in (a.get("regimen") or "").split("+") if x.strip()}
        rungs = _rungs(others, _classes(a["class_signature"]), agents, a["age_group"], a["phase"],
                       lambda r: {x.strip().casefold() for x in (r.get("regimen") or "").split("+") if x.strip()})
        for k, (_, rs) in rungs.items():
            if len({r["study"] for r in rs}) >= min_studies:
                errors[k].append(abs(pooled(rs)["estimate"] - obs))
    summary = {k: {"applies_to": len(v), "median_abs_error": float(np.median(v)) if v else None} for k, v in errors.items()}
    usable = [k for k, v in summary.items() if v["median_abs_error"] is not None and v["applies_to"] >= 20]
    order = sorted(usable, key=lambda k: summary[k]["median_abs_error"])
    return {"order": order, "rungs": summary, "whole_family_median_abs_error": float(np.median(family_errors)),
            "held_out_studies": len(family_errors), "rule": f"each rung alone, leave-one-study-out; at least {min_studies} other studies; at least 20 applicable studies"}


def arm_age_group(spec: dict) -> str:
    from .population import age_limits

    lo, hi = age_limits(spec)
    if hi is not None and hi <= 22:              # 'up to 21 years' is held as an exclusive limit of 22
        return "pediatric"
    if lo is not None and lo >= 18:
        return "adult"
    return "mixed"


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (t or "").casefold()).strip("_")
