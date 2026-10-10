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

from .predictive import from_normal
from .. import assets as _assets

V1_TABLE = _assets.path("params_v1") / "evidence_table.parquet"
RAW = _assets.path("raw_ctgov")
MIN_STUDIES = 3


def evidence_provenance() -> dict:
    """The frozen evidence the estimates read, verified: the V1 evidence table must match the checksum recorded in the
    Simulation Parameter Asset V3 manifest (the table V3 was fitted on); anything else stops the estimate."""
    import hashlib

    from ..cutoff import asset

    recorded = json.loads((asset("v3") / "manifest.json").read_text(encoding="utf-8"))["inputs"]["parameter_asset_v1"]["evidence_table_sha256"]
    actual = hashlib.sha256(V1_TABLE.read_bytes()).hexdigest()
    if actual != recorded:
        raise RuntimeError(f"{V1_TABLE} does not match the checksum frozen in the V3 manifest: the evidence has changed")
    maps = {name: hashlib.sha256(Path(f"data/spa_work/{name}").read_bytes()).hexdigest() for name in ("disease_families.json", "drug_classes.json")}
    return {"evidence_table": {"path": str(V1_TABLE), "sha256": actual, "verified_against": "simulation_parameters_v3 manifest"}, "maps": maps}


@lru_cache(maxsize=1)
def _targets() -> dict:
    import pyarrow.parquet as pq

    from ..spa2 import borrow as b2

    from ..cutoff import excluded

    evidence_provenance()                       # refuses changed evidence
    drop = excluded()                           # an evidence cut-off in force drops later trials
    rows = [r for r in pq.read_table(V1_TABLE).to_pylist() if r["nct_id"] not in drop]
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
            "single_trial_percentiles": from_normal(mu, math.hypot(se, tau), ex),
            "studies": len({r["study"] for r in recs}), "arms": len(recs), "patients": int(n.sum())}


def _classes(sig: str) -> set[str]:
    return {c for c in (sig or "").split("+") if c and c not in {"other", "unclassified", "supportive_care", "placebo_or_no_active_treatment"}}


def estimate(target_variable: str, family: str, classes: list[str], agents: list[str], age_group: str, phase: str | None = None,
             exclude_studies: set[str] | None = None, min_studies: int = MIN_STUDIES, order: list[str] | None = None) -> dict:
    recs = [r for r in records(target_variable) if (family is None or r["disease_family"] == family) and r["study"] not in (exclude_studies or set())]
    if not recs and family is not None:          # no study in the family: the same ladder over all oncology (L027)
        return {**estimate(target_variable, None, classes, agents, age_group, phase, exclude_studies, min_studies, order), "family_fallback": family}
    if not recs:
        return {"status": "UNRESOLVED", "reason": f"no study of {target_variable} in the evidence"}
    mine = set(classes) - {"other", "unclassified"}
    agent_set = {a.casefold() for a in agents if a}

    def regimen_of(r):
        return {x.strip().casefold() for x in (r.get("regimen") or "").split("+") if x.strip()}
    rungs = _rungs(recs, mine, agent_set, age_group, phase, regimen_of)
    order = ladder_order(target_variable) if order is None else order
    ladder = [(rungs[k][0], rungs[k][1]) for k in order if k in rungs] + [("whole disease family" if family is not None else "all oncology", recs)]
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


RUNG_KEYS = ("regimen", "similar_classes_75", "similar_classes_50", "age_phase_classes", "age_classes", "age_phase", "age", "classes", "phase")
SIMILARITY_RUNGS = {"similar_classes_75": 0.75, "similar_classes_50": 0.5}      # Jaccard similarity of drug-class sets
LADDER_FILE = Path("data/validation/subgroup_ladder.json")


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _rungs(recs, mine, agent_set, age_group, phase, regimen_of) -> dict:
    overlap = [r for r in recs if mine and _classes(r["class_signature"]) & mine]
    same_age = [r for r in recs if r["age_group"] == age_group]
    similar = {k: (f"trials with a similar drug-class set (Jaccard at least {t:g})",
                   [r for r in recs if mine and _jaccard(_classes(r["class_signature"]) - {"other", "unclassified"}, mine) >= t])
               for k, t in SIMILARITY_RUNGS.items()}
    return {"regimen": ("same regimen", [r for r in recs if agent_set and regimen_of(r) == agent_set]), **similar,
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


def _has_ladder(key: str) -> bool:
    return LADDER_FILE.exists() and key in json.loads(LADDER_FILE.read_text(encoding="utf-8"))


def choose_median_ladder(variable: str, min_studies: int = MIN_STUDIES, save: bool = True) -> dict:
    """The rung order for a survival median, chosen like choose_ladder: leave-one-study-out, each rung alone (the disease
    family when the rung holds fewer than `min_studies` other studies) predicts every held-out study's largest arm;
    error = |log(predicted / observed median)|; rungs ordered by median error where they apply to at least 20 studies."""
    recs = list(median_records(variable))
    by_study: dict[str, list] = {}
    for r in recs:
        by_study.setdefault(r["study"], []).append(r)
    errors: dict[str, list] = {k: [] for k in RUNG_KEYS}
    family_errors = []
    for study, arms in by_study.items():
        a = max(arms, key=lambda r: r["n"])
        others = [r for r in recs if r["disease_family"] == a["disease_family"] and r["study"] != study]
        fam = pooled_median(others)
        if fam is None:
            continue
        family_errors.append(abs(math.log(fam["median_months"] / a["months"])))
        agents = {x.strip().casefold() for x in (a.get("regimen") or "").split("+") if x.strip()}
        rungs = _rungs(others, _classes(a["class_signature"]) - {"other", "unclassified"}, agents, a["age_group"], a["phase"],
                       lambda r: {x.strip().casefold() for x in (r.get("regimen") or "").split("+") if x.strip()})
        for k, (_, rs) in rungs.items():
            if len({r["study"] for r in rs}) >= min_studies:
                errors[k].append(abs(math.log(pooled_median(rs)["median_months"] / a["months"])))
    summary = {k: {"applies_to": len(v), "median_abs_log_error": float(np.median(v)) if v else None} for k, v in errors.items()}
    usable = [k for k, v in summary.items() if v["median_abs_log_error"] is not None and v["applies_to"] >= 20]
    order = sorted(usable, key=lambda k: summary[k]["median_abs_log_error"])
    doc = {"order": order, "rungs": summary, "whole_family_median_abs_log_error": float(np.median(family_errors)) if family_errors else None,
           "held_out_studies": len(family_errors), "rule": f"each rung alone, leave-one-study-out; at least {min_studies} other studies; "
                                                          "at least 20 applicable studies; error |log(predicted/observed)|"}
    if save:
        LADDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        cur = json.loads(LADDER_FILE.read_text(encoding="utf-8")) if LADDER_FILE.exists() else {}
        cur[f"median:{variable}"] = doc
        LADDER_FILE.write_text(json.dumps(cur, indent=1), encoding="utf-8")
    return doc


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


# ----------------------------------------------------------------------------- survival medians (months) by subgroup

_TO_MONTHS = {"month": 1.0, "months": 1.0, "week": 12 / 52.18, "weeks": 12 / 52.18, "day": 12 / 365.25, "days": 12 / 365.25,
              "year": 12.0, "years": 12.0}


@lru_cache(maxsize=4)
def median_records(variable: str) -> tuple:
    """Study arms reporting the median of a time-to-event endpoint (months), with disease family, drug classes,
    regimen, arm type, phase and age group (V1 evidence table, verified)."""
    import pyarrow.parquet as pq

    from ..spa2.taxonomy import regimen_signature

    evidence_provenance()
    families = json.loads(Path("data/spa_work/disease_families.json").read_text(encoding="utf-8"))
    classes = json.loads(Path("data/spa_work/drug_classes.json").read_text(encoding="utf-8"))
    cols = ["nct_id", "variable", "statistic_family", "value", "unit", "denominator", "disease", "regimen", "arm_type", "registry_group"]
    from ..cutoff import excluded

    drop = excluded()
    out = []
    for r in pq.read_table(V1_TABLE, columns=cols).to_pylist():
        if r["nct_id"] in drop or r["variable"] != variable or r["statistic_family"] != "median_time" or not r["value"] or not r["denominator"]:
            continue
        factor = _TO_MONTHS.get(str(r["unit"] or "").casefold())
        if not factor:
            continue
        fam = (families.get(r["disease"]) or {})
        comps = [c.strip() for c in str(r["regimen"] or "").split(" + ") if c.strip()]
        out.append({"study": r["nct_id"], "arm": f"{r['nct_id']}|{r['registry_group']}", "months": float(r["value"]) * factor, "n": int(r["denominator"]),
                    "disease_family": fam.get("label", "other") if (fam.get("confidence") or 0) >= 0.7 else "other",
                    "class_signature": regimen_signature(comps, classes)[0] if comps else "unclassified", "regimen": r["regimen"] or "",
                    "arm_type": r["arm_type"], **study_attributes(r["nct_id"])})
    return tuple(out)


def pooled_median(recs: list[dict]) -> dict | None:
    """Random-effects average of log medians (approximate variance 2/n per arm: about half of the patients have had
    the event by the median), as a median in months with confidence intervals."""
    if not recs:
        return None
    y = np.log([r["months"] for r in recs])
    v = np.array([2.0 / max(r["n"], 2) for r in recs])
    w = 1 / v
    mu_f = float(np.sum(w * y) / np.sum(w))
    q, df = float(np.sum(w * (y - mu_f) ** 2)), len(recs) - 1
    c = float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
    tau2 = max(0.0, (q - df) / c) if df > 0 and c > 0 else 0.0
    ws = 1 / (v + tau2)
    mu, se = float(np.sum(ws * y) / np.sum(ws)), math.sqrt(1 / float(np.sum(ws)))
    return {"median_months": math.exp(mu), "ci95": [math.exp(mu - 1.96 * se), math.exp(mu + 1.96 * se)],
            "single_trial_80": [math.exp(mu - 1.2816 * math.hypot(se, math.sqrt(tau2))), math.exp(mu + 1.2816 * math.hypot(se, math.sqrt(tau2)))],
            "studies": len({r["study"] for r in recs}), "arms": len(recs), "patients": int(sum(r["n"] for r in recs))}


def estimate_median(variable: str, family: str, classes: list[str], agents: list[str], age_group: str, phase: str | None,
                    min_studies: int = MIN_STUDIES) -> dict:
    """The most specific subgroup (the data-chosen rung order) holding at least `min_studies` studies, for a control
    arm's median; the whole disease family last."""
    recs = [r for r in median_records(variable) if family is None or r["disease_family"] == family]
    if not recs and family is not None:          # no reported median in the family: the same ladder over all oncology (L027)
        return {**estimate_median(variable, None, classes, agents, age_group, phase, min_studies), "family_fallback": family}
    if not recs:
        return {"status": "UNRESOLVED", "reason": f"no reported {variable} median in the evidence"}
    mine = set(classes) - {"other", "unclassified"}
    agent_set = {a.casefold() for a in agents if a}
    rungs = _rungs(recs, mine, agent_set, age_group, phase,
                   lambda r: {x.strip().casefold() for x in (r.get("regimen") or "").split("+") if x.strip()})
    # the rung order validated on held-out medians of this variable (choose_median_ladder); before one is chosen, the
    # serious-adverse-event order, as before
    order = ladder_order(f"median:{variable}") if _has_ladder(f"median:{variable}") else ladder_order("serious_adverse_event")
    ladder = [(rungs[k][0], rungs[k][1]) for k in order if k in rungs] + [("whole disease family" if family is not None else "all oncology", recs)]
    level, chosen = next(((lv, rs) for lv, rs in ladder if len({r["study"] for r in rs}) >= min_studies), ladder[-1])
    return {"status": "RESOLVED", "variable": variable, "family": family, "subgroup": level, **pooled_median(chosen)}


# ----------------------------------------------------------------------------- response rates: disease first (L069)

RESPONSE_VARIABLES = {"objective_response_rate", "complete_response"}
MIN_RESPONSE_STUDIES = 5
ERA_YEARS = 10
@lru_cache(maxsize=1)
def _disease_words() -> tuple[frozenset, dict]:
    """Stage and setting words, and disease-name synonyms (reference vocabulary: no medical terms in code)."""
    from ..reference import vocabulary

    w = vocabulary()["disease_name_words"]
    return frozenset(w["stage_and_setting"]), dict(w["synonyms"])


def disease_core(name: str | None) -> frozenset:
    """A disease name as a word set, without stage or setting words and with the synonyms above read as one word: two
    names that differ only in stage, setting or synonym are the same disease; a name with an extra or different
    qualifying word (a histology, a cell type) is a different disease."""
    stage, synonyms = _disease_words()
    words = [synonyms.get(w, w) for w in re.findall(r"[a-z0-9]+", (name or "").lower())]
    return frozenset(w for w in words if w not in stage)


@lru_cache(maxsize=None)
def start_year(nct: str) -> int | None:
    path = RAW / f"{nct}.json"
    if not path.exists():
        return None
    d = ((json.loads(path.read_text(encoding="utf-8")).get("protocolSection") or {}).get("statusModule") or {}).get("startDateStruct") or {}
    y = (d.get("date") or "")[:4]
    return int(y) if y.isdigit() else None


def response_hierarchy(recs: list[dict], family: str | None, disease: str | None, classes: list[str], phase: str | None,
                       year: int | None) -> list[tuple[str, list[dict]]]:
    """The evidence hierarchy for a response rate, most specific first: same disease, then drug-class similarity,
    phase and era within it; the disease family next; all oncology last (flagged). Line of therapy is not recorded in
    the evidence and cannot be matched."""
    mine = set(classes) - {"other", "unclassified"}
    core = disease_core(disease) if disease else frozenset()
    same = [r for r in recs if core and disease_core(r["disease"]) == core]
    fam = [r for r in recs if family and r["disease_family"] == family]

    def sim(rs, t):
        return [r for r in rs if mine and _jaccard(_classes(r["class_signature"]) - {"other", "unclassified"}, mine) >= t]

    def era(rs):
        return [r for r in rs if year and start_year(r["study"]) and start_year(r["study"]) >= year - ERA_YEARS]
    return [("same disease, similar drug-class set, same phase, same era", era([r for r in sim(same, 0.75) if phase and r["phase"] == phase])),
            ("same disease, similar drug-class set, same era", era(sim(same, 0.75))),
            ("same disease, similar drug-class set", sim(same, 0.75)),
            ("same disease, related drug-class set", sim(same, 0.5)),
            ("same disease family, similar drug-class set", sim(fam, 0.75)),
            ("same disease family, related drug-class set", sim(fam, 0.5)),
            ("same disease, any regimen", same),
            ("same disease family, any regimen", fam),
            ("all oncology, similar drug-class set (last resort)", sim(recs, 0.75)),
            ("all oncology (last resort)", recs)]


def estimate_response(variable: str, family: str | None, disease: str | None, classes: list[str], phase: str | None,
                      year: int | None, exclude_studies: set | None = None, min_studies: int = MIN_RESPONSE_STUDIES) -> dict:
    """A response rate from the first level of the hierarchy holding at least `min_studies` studies."""
    recs = [r for r in records(variable) if r["study"] not in (exclude_studies or set())]
    if not recs:
        return {"status": "UNRESOLVED", "reason": f"no study of {variable} in the evidence"}
    ladder = response_hierarchy(recs, family, disease, classes, phase, year)
    support = [{"level": lab, "studies": len({r["study"] for r in rs})} for lab, rs in ladder]
    level, chosen = next(((lab, rs) for lab, rs in ladder if len({r["study"] for r in rs}) >= min_studies), ladder[-1])
    return {"status": "RESOLVED", "target": variable, "headline_subgroup": level, "headline": pooled(chosen), "hierarchy": support,
            "last_resort": "last resort" in level, "disease": disease, "era_from": (year - ERA_YEARS) if year else None,
            "not_matched": "line of therapy (not recorded in the evidence)"}


def validate_response_hierarchy(variable: str = "objective_response_rate") -> dict:
    """Leave-one-study-out over the evidence: the hierarchy predicts each held-out study's largest arm (from that arm's
    own disease, drug classes, phase and start year); compared with the generic ladder on the same studies."""
    recs = records(variable)
    by_study: dict[str, list] = {}
    for r in recs:
        by_study.setdefault(r["study"], []).append(r)
    err_h, err_g, levels = [], [], {}
    for study, arms in by_study.items():
        a = max(arms, key=lambda r: r["n"])
        obs = a["count"] / a["n"]
        h = estimate_response(variable, a["disease_family"], a["disease"], list(_classes(a["class_signature"])), a["phase"],
                              start_year(study), exclude_studies={study})
        g = estimate(variable, a["disease_family"], list(_classes(a["class_signature"])), [], a["age_group"], a["phase"], exclude_studies={study})
        if h.get("headline") and g.get("headline"):
            err_h.append(abs(h["headline"]["estimate"] - obs))
            err_g.append(abs(g["headline"]["estimate"] - obs))
            levels[h["headline_subgroup"]] = levels.get(h["headline_subgroup"], 0) + 1
    return {"held_out_studies": len(err_h), "hierarchy_median_abs_error": float(np.median(err_h)) if err_h else None,
            "generic_ladder_median_abs_error": float(np.median(err_g)) if err_g else None, "levels_used": levels}
