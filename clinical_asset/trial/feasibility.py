"""Protocol feasibility from a locked simulation run (no new evidence, no rerun).

Everything is computed from the run's own locked stages: the screened population and its eligibility outcomes, the
enrolled cohort, the patient journey (treatment, adverse events, progression, death, withdrawal), the planning report
(historical accrual distribution) and the primary-engine results. Each derived quantity states how it is derived.

Chain: candidates -> screening (criteria by category) -> eligible -> enrolled -> treated -> on study -> endpoint
evaluable; subgroup availability, screening yield and representation; criterion bottlenecks and the gain from relaxing
each; recruitment demand against the historical distribution; evaluable-N probability by enrolment size; assessment
completeness and protocol burden; safety burden; scenario stress test.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from ..protocol import expressions as ex

VERSION = "feasibility-1.0.0"
DRAWS = 4000
CATEGORY_ORDER = ("Disease and stage", "Prior treatment", "Performance status", "Laboratory and organ function",
                  "Reproductive and contraception", "Comorbidity and other exclusions")
DISEASE_TYPES = {"diagnosis", "disease_stage", "histology", "biomarker", "imaging", "pathology_review", "molecular_subtype"}
REPRO_TYPES = {"sex", "reproductive_status", "contraception", "pregnancy"}
ACRONYMS = {"ecog", "hiv", "cns", "alt", "ast", "anc", "ctcae", "pk", "auc", "hbv", "hcv"}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def category(kind: str, types: set[str]) -> str:
    """A criterion's feasibility category from its rule types (general for any protocol)."""
    if types & {"performance_status", "life_expectancy"}:
        return "Performance status"
    if types & {"organ_function", "laboratory"} and kind == "inclusion":
        return "Laboratory and organ function"
    if kind == "inclusion" and types & DISEASE_TYPES:
        return "Disease and stage"
    if "prior_therapy" in types or (types & {"adverse_event", "concomitant_medication"} and kind == "inclusion"):
        return "Prior treatment"
    if types & REPRO_TYPES:
        return "Reproductive and contraception"
    if kind == "exclusion" and types & {"histology", "disease_stage"}:
        return "Disease and stage"
    return "Comorbidity and other exclusions"


def _label(c: dict, labels: dict) -> str:
    leaves = ex.leaves(c["logic"])
    names = []
    for leaf in leaves:
        n = labels.get(leaf.get("variable")) or leaf.get("label") or leaf.get("variable") or ""
        n = re.sub(r"^(var|umls|demographic):", "", str(n)).replace("_", " ").strip()
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    text = "; ".join(names[:2]) or c["criterion_id"]
    text = " ".join(w.upper() if w.lower().strip(";,") in ACRONYMS else w for w in text.split())
    text = text[0].upper() + text[1:]
    return text if len(text) <= 48 else text[:46].rstrip() + "…"


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def _age_group(a: float | None) -> str | None:
    return None if a is None else ("<65 years" if a < 65 else "65 years or older")


def _groups(p: dict) -> dict:
    """The subgroup memberships of a population record."""
    age = (p.get("demographic:age") or {}).get("value")
    ecog = (p.get("var:ecog_performance_status") or {}).get("value")
    race = p.get("demographic:race") or "unknown_or_not_reported"
    race = race if race in ("white", "asian", "black_or_african_american") else "other or not reported"
    return {"Age": _age_group(age), "Sex": p.get("demographic:sex"),
            "Race": race.replace("_", " ").replace("black or african american", "Black or African American").capitalize()
            if race != "black_or_african_american" else "Black or African American",
            "Ethnicity": {"hispanic_or_latino": "Hispanic or Latino", "not_hispanic_or_latino": "Not Hispanic or Latino"}.get(
                p.get("demographic:ethnicity"), "Not reported"),
            "ECOG": None if ecog is None else ("ECOG 0" if ecog == 0 else "ECOG 1" if ecog == 1 else "ECOG 2 or more"),
            "Region": p.get("var:region")}


def _lognormal_from_quantiles(q: dict) -> tuple[float, float]:
    """Log-normal fitted (least squares on the log scale) to a distribution's reported percentiles."""
    ps = [(int(k[1:]) / 100, v) for k, v in q.items() if k.startswith("p") and v and v > 0]
    z = np.array([stats.norm.ppf(p) for p, _ in ps])
    y = np.log([v for _, v in ps])
    sd, mu = np.polyfit(z, y, 1)
    return float(mu), float(sd)


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _text(x) -> str:
    return (x.get("text") if isinstance(x, dict) else x) or ""


def _pk_windows(spec: dict, cycle_days: float) -> list[dict]:
    """Primary endpoints measured in a stated treatment cycle, and the day a patient must still be on study to give
    them: a pre-dose measurement needs the start of cycle k; any other (over the dosing interval, or at its end) needs
    the end of cycle k's dosing interval."""
    out, seen = [], set()
    for e in spec.get("endpoints") or []:
        if e.get("role") != "primary":
            continue
        name = _text(e.get("name")) or e.get("endpoint_id")
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in seen:                       # the same endpoint extracted twice (spacing or punctuation differs)
            continue
        seen.add(key)
        m = re.search(r"cycle\s*(\d+)", name, re.I)
        if not m:
            continue
        k = int(m.group(1))
        text = " ".join(_text(e.get(f)) for f in ("definition", "assessment", "schedule")) + " " + name
        predose = bool(re.search(r"pre-?dose", text, re.I))
        day = (k - 1) * cycle_days if predose else k * cycle_days
        out.append({"endpoint": name, "cycle": k, "on_study_day": day,
                    "rule": f"on study through day {day:g} ({'start' if predose else 'end'} of cycle {k}'s dosing interval)"})
    return out


def build(nct: str, version: str, out_dir: Path) -> dict:
    L = Path("data/locked") / nct
    st = lambda s: L / f"{s}_v{version}"  # noqa: E731
    spec = json.loads((st("studyspec") / "studyspec.json").read_text(encoding="utf-8"))
    labels = {v["key"]: v.get("label") or v["key"] for v in spec.get("variables") or []}
    pop = {}
    with open(st("population") / "population.jsonl", encoding="utf-8") as fh:
        for line in fh:
            p = json.loads(line)
            pop[p["patient_id"]] = p
    elig = {}
    with open(st("eligibility") / "eligibility.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            elig[r["patient_id"]] = r
    journey = json.loads((st("journey") / "journey_summary.json").read_text(encoding="utf-8"))
    cohort = [json.loads(x) for x in open(st("cohorts") / journey["cohort_file"], encoding="utf-8")]
    subj_patient = {c["subject_id"]: c["patient_id"] for c in cohort}
    adsl = _read_csv(st("journey") / "adsl.csv")
    ds = {r["USUBJID"]: r for r in _read_csv(st("journey") / "ds.csv")}
    sv = _read_csv(st("journey") / "sv.csv")
    exr = _read_csv(st("journey") / "ex.csv")
    lb = _read_csv(st("journey") / "lb.csv")
    planning = json.loads((st("planning") / "planning_report.json").read_text(encoding="utf-8"))
    rni_file = st("results") / "ratio_ni_results.json"
    rni = json.loads(rni_file.read_text(encoding="utf-8")) if rni_file.exists() else None
    target = int(planning["accrual"]["target_patients"])

    # ---- criteria: categories, sequential funnel, marginal exclusion, gain from relaxing ----
    crit = {}
    for c in spec.get("eligibility") or []:
        if c.get("logic"):
            types = {x.get("rule_type") for x in ex.leaves(c["logic"]) if x.get("rule_type")}
            crit[c["criterion_id"]] = {"category": category(c.get("kind") or "", types), "label": _label(c, labels), "kind": c.get("kind")}
    n_cand = len(elig)
    failed = {pid: set(r.get("failed") or []) for pid, r in elig.items()}
    eligible = {pid for pid, r in elig.items() if r["status"] == "ELIGIBLE"}
    funnel, remaining = [], set(elig)
    funnel.append({"step": "Potential candidates", "remaining": n_cand})
    for cat in CATEGORY_ORDER:
        lost = {pid for pid in remaining if any(crit.get(c, {}).get("category") == cat for c in failed[pid])}
        remaining -= lost
        funnel.append({"step": cat, "lost": len(lost), "remaining": len(remaining)})
    rest = {pid for pid in remaining if failed[pid]}                 # criteria without a category (no logic)
    remaining -= rest
    if rest:
        funnel.append({"step": "Other criteria", "lost": len(rest), "remaining": len(remaining)})
    assert remaining == eligible or len(remaining) == len(eligible)
    for i in range(1, len(funnel)):
        prev = funnel[i - 1]["remaining"]
        funnel[i]["pct_remaining"] = funnel[i]["remaining"] / n_cand
        funnel[i]["pct_lost_at_step"] = funnel[i].get("lost", 0) / prev if prev else 0.0
    by_crit = []
    counts = Counter(c for f in failed.values() for c in f)
    only = Counter(next(iter(f)) for f in failed.values() if len(f) == 1)
    for cid, n in counts.most_common():
        by_crit.append({"criterion": cid, "label": crit.get(cid, {}).get("label", cid), "category": crit.get(cid, {}).get("category", "Other criteria"),
                        "excluded": n, "pct_excluded": n / n_cand, "gain_if_relaxed": only.get(cid, 0),
                        "eligible_if_relaxed_pct": (len(eligible) + only.get(cid, 0)) / n_cand})
    yield_ = len(eligible) / n_cand

    # ---- enrolled / treated / evaluable ----
    cycle_days = float(((journey.get("schedule") or {}).get("cycle_length_days") or {}).get("value") or 21)
    windows = _pk_windows(spec, cycle_days)
    req = {}
    for a in (rni or {}).get("analyses") or []:
        req[a["endpoint"]] = int(a["n"])
    treated = {r["USUBJID"] for r in exr if int(r["ACTUAL_ADMIN"] or 0) > 0}
    pats = []
    for r in adsl:
        sid = r["USUBJID"]
        end = float(ds[sid]["DSSTDY"]) if sid in ds and ds[sid]["DSSTDY"] else float(r["TRTEDY"] or 0)
        base = pop.get(subj_patient.get(sid)) or {}
        g = _groups(base) if base else {}
        dth = float(r["DTHDY"]) if r.get("DTHDY") else None
        pats.append({"sid": sid, "arm": r["ARMCD"], "treated": sid in treated, "end": end, "death_day": dth,
                     "sae": r["ANY_SAE"] == "Y", "holds": int(r["N_HOLDS"] or 0) > 0, "reductions": int(r["N_REDUCTIONS"] or 0) > 0,
                     "ae_disc": "adverse event" in (r["EOTREAS"] or ""), "eot": r["EOTREAS"], "groups": g,
                     "evaluable": {w["endpoint"]: sid in treated and end >= w["on_study_day"] for w in windows}})
    n_enr = len(pats)
    ev_counts = {w["endpoint"]: sum(p["evaluable"][w["endpoint"]] for p in pats) for w in windows}

    def _req_for(endpoint: str) -> int | None:
        for k, v in req.items():
            if k.lower() == endpoint.lower() or set(re.findall(r"\w+", k.lower())) & set(re.findall(r"\w+", endpoint.lower())) >= {"cycle"} \
                    and re.search(r"cycle\s*(\d+)", k, re.I) and re.search(r"cycle\s*(\d+)", k, re.I).group(1) == re.search(r"cycle\s*(\d+)", endpoint, re.I).group(1):
                return v
        return None
    for w in windows:
        w["required"] = _req_for(w["endpoint"])
        w["evaluable"] = ev_counts[w["endpoint"]]
        w["share"] = ev_counts[w["endpoint"]] / n_enr

    # evaluable-N probability by enrolment (Bayesian bootstrap of the simulated patients: their evaluability and its
    # uncertainty from the finite simulated cohort; joint across endpoints)
    rng = np.random.default_rng(20261009)
    E = np.array([[p["evaluable"][w["endpoint"]] for w in windows] for p in pats], dtype=float)

    def evaluable_draws(n: int, weights: np.ndarray | None = None) -> np.ndarray:
        # one fixed stream per enrolment size: the same question asked twice gets the same answer (canonical values)
        rng = np.random.default_rng(20261009 + n)
        out = np.empty((DRAWS, len(windows)))
        base_w = weights if weights is not None else np.ones(n_enr)
        for d in range(DRAWS):
            w = rng.dirichlet(base_w * (n_enr / base_w.sum()))
            idx = rng.choice(n_enr, size=n, p=w)
            out[d] = E[idx].sum(axis=0)
        return out
    curve = []
    sizes = sorted({int(round(target * f)) for f in (0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2)} | {350, 378, 400, 420})
    for n in sizes:
        d = evaluable_draws(n)
        row = {"enrolled": n}
        ok_all = np.ones(DRAWS, bool)
        for j, w in enumerate(windows):
            if w["required"]:
                ok = d[:, j] >= w["required"]
                row[w["endpoint"]] = {"p_meets": float(ok.mean()), "median": float(np.median(d[:, j]))}
                ok_all &= ok
        row["p_all"] = float(ok_all.mean())
        curve.append(row)

    # ---- subgroups: availability, screening yield, representation, safety and evaluability ----
    subgroups = defaultdict(dict)
    cand_g = {pid: _groups(p) for pid, p in pop.items()}
    enrolled_pids = {subj_patient[p["sid"]] for p in pats if p["sid"] in subj_patient}
    for dim in ("Age", "Sex", "Race", "Ethnicity", "ECOG", "Region"):
        levels = Counter(g[dim] for g in cand_g.values() if g.get(dim))
        for lv, n in levels.most_common():
            in_lv = [pid for pid, g in cand_g.items() if g.get(dim) == lv]
            ne = sum(pid in eligible for pid in in_lv)
            nr = sum(pid in enrolled_pids for pid in in_lv)
            pj = [p for p in pats if p["groups"].get(dim) == lv]
            k_sae = sum(p["sae"] for p in pj)
            subgroups[dim][lv] = {"candidates": n, "candidate_share": n / n_cand, "eligible": ne,
                                  "p_eligible": ne / n if n else None, "eligible_share": ne / len(eligible),
                                  "enrolled": nr, "enrolled_share": nr / n_enr, "p_enrolled_given_eligible": nr / ne if ne else None,
                                  "sae": k_sae, "sae_rate": k_sae / len(pj) if pj else None, "sae_ci": _wilson(k_sae, len(pj)) if pj else None,
                                  "evaluable_share": {w["endpoint"]: (sum(p["evaluable"][w["endpoint"]] for p in pj) / len(pj)) if pj else None
                                                      for w in windows}}
        # exclusion by category within the subgroup (who the criteria remove)
        for lv in subgroups[dim]:
            in_lv = [pid for pid, g in cand_g.items() if g.get(dim) == lv]
            subgroups[dim][lv]["lost_by_category"] = {cat: sum(any(crit.get(c, {}).get("category") == cat for c in failed[pid]) for pid in in_lv) / len(in_lv)
                                                      for cat in CATEGORY_ORDER}

    # ---- recruitment demand ----
    hist = planning["accrual"]["historical_model"]
    mu, sd = _lognormal_from_quantiles(hist["patients_per_year"]["percentiles"])
    windows_y = planning["accrual"].get("stated_accrual_durations_years") or []
    planned_years = float(windows_y[0]) if windows_y else None
    required_rate = target / planned_years if planned_years else None
    req_pct = float(stats.norm.cdf((math.log(required_rate) - mu) / sd)) if required_rate else None

    def p_complete_by(years: float, n: int = target, rate_mult: float = 1.0) -> float:
        # duration = n / rate (Poisson arrivals at n of this size add little): P(rate * mult >= n / years)
        return float(1 - stats.norm.cdf((math.log(n / years / rate_mult) - mu) / sd))

    def median_years(n: int = target, rate_mult: float = 1.0) -> float:
        return n / (math.exp(mu) * rate_mult)
    months = list(range(1, 121))
    completion_curve = [{"months": m, "p_complete": p_complete_by(m / 12)} for m in months]
    protocol_rate = next((s for s in planning["accrual"]["protocol_scenarios"] if "derived" in s["scenario"] or s.get("source") == "protocol (quoted)"
                          and "historical" not in s["scenario"]), None)

    # ---- completeness and burden ----
    sched = journey.get("schedule") or {}
    ta = float((sched.get("tumour_assessment_interval_days") or {}).get("value") or 0)
    fu = float((sched.get("follow_up_interval_days") or {}).get("value") or 0)
    horizon = float(journey.get("horizon_days") or 730)
    completeness = []
    if ta:
        for k in range(1, int(horizon // ta) + 1):
            day = k * ta
            due = [p for p in pats if (p["death_day"] is None or p["death_day"] >= day)]
            on = [p for p in pats if p["end"] >= day]
            completeness.append({"assessment": f"Tumour assessment {k} (day {day:g})", "day": day, "on_study": len(on) / n_enr,
                                 "alive": len(due) / n_enr})
    for w in windows:
        completeness.append({"assessment": f"{w['endpoint']} sampling", "day": w["on_study_day"], "on_study": w["share"],
                             "alive": sum(1 for p in pats if p["death_day"] is None or p["death_day"] >= w["on_study_day"]) / n_enr})
    visits = defaultdict(set)
    fu_visits = defaultdict(int)
    for r in sv:
        visits[r["USUBJID"]].add(int(r["SVSTDY"]))
        if r["VISIT"].startswith("FU"):
            fu_visits[r["USUBJID"]] += 1
    admins = defaultdict(int)
    for r in exr:
        admins[r["USUBJID"]] += int(r["ACTUAL_ADMIN"] or 0)
    labs = Counter(r["USUBJID"] for r in lb)
    scans = Counter(r["USUBJID"] for r in sv if r["VISIT"].startswith("TA"))
    burden = {k: {"median": float(np.median(v)), "q25": float(np.quantile(v, 0.25)), "q75": float(np.quantile(v, 0.75)), "total": float(np.sum(v))}
              for k, v in (("Clinic visit days", [len(visits[p["sid"]]) for p in pats]),
                           ("Drug administrations", [admins[p["sid"]] for p in pats]),
                           ("Laboratory draws", [labs[p["sid"]] for p in pats]),
                           ("Tumour scans", [scans[p["sid"]] for p in pats]),
                           ("Follow-up visits", [fu_visits[p["sid"]] for p in pats]))}
    days_on = np.array([max(p["end"], 1.0) for p in pats])
    burden["Clinic visit days per month on study"] = {"median": float(np.median([len(visits[p["sid"]]) / (d / 30.44) for p, d in zip(pats, days_on, strict=True)]))}
    withdrawal = journey.get("withdrawal") or {}

    # ---- safety burden ----
    def share(f):
        k = sum(1 for p in pats if f(p))
        return {"n": k, "share": k / n_enr, "ci": _wilson(k, n_enr), "per_target": k / n_enr * target}
    first_window = min((w["on_study_day"] for w in windows if w["on_study_day"] > 0), default=None)
    last_window = max((w["on_study_day"] for w in windows), default=None)
    safety = {"Serious adverse event": share(lambda p: p["sae"]),
              "Treatment interruption (dose hold)": share(lambda p: p["holds"]),
              "Dose reduction": share(lambda p: p["reductions"]),
              "Discontinuation for an adverse event": share(lambda p: p["ae_disc"]),
              "Death during follow-up": share(lambda p: p["death_day"] is not None)}
    if last_window:
        safety[f"Death within the primary sampling period (to day {last_window:g})"] = share(lambda p: p["death_day"] is not None and p["death_day"] < last_window)

    # ---- scenarios ----
    def cell(p):
        return (p["groups"].get("Age"), p["groups"].get("Sex"))
    cell_rates = defaultdict(lambda: [0, 0, np.zeros(len(windows))])
    for p in pats:
        c = cell_rates[cell(p)]
        c[0] += 1
        c[1] += p["sae"]
        c[2] += np.array([p["evaluable"][w["endpoint"]] for w in windows], float)
    overall_sae = sum(p["sae"] for p in pats) / n_enr

    def composition_weights(pool: list[str]) -> np.ndarray:
        """Weights on the simulated enrolled patients that give a pool's age-sex composition."""
        comp = Counter((cand_g[pid].get("Age"), cand_g[pid].get("Sex")) for pid in pool)
        tot = sum(comp.values())
        w = np.array([comp.get(cell(p), 0) / tot / (cell_rates[cell(p)][0] / n_enr) for p in pats])
        return np.where(w > 0, w, 1e-6)

    rate_designed = {w["endpoint"]: w["required"] for w in windows}
    p_ni = None
    if rni:
        for s in rni.get("scenarios") or []:
            g = next((x for x in s.get("grid") or [] if x.get("position") == 1), None)
            if g and s["variability"].startswith("protocol"):
                p_ni = g.get("all_endpoints_succeed")
    site_coef = None
    try:
        from .. import assets
        model = json.loads((Path(assets.path("operational")) / "accrual_model.json").read_text(encoding="utf-8"))
        site_coef = dict(zip(model["cols"], model["beta"], strict=True)).get("log_sites")
    except Exception:  # noqa: BLE001
        pass

    def scenario(name, how, pool=None, n=target, rate_mult=1.0, window=planned_years, female_target=None, fu_less=0):
        pool = pool if pool is not None else sorted(eligible)
        y = len(pool) / n_cand
        # weights relative to the original eligible pool: a scenario that does not change who is eligible has weight 1
        # for every patient and returns the original protocol's values exactly
        w = composition_weights(pool) / composition_weights(sorted(eligible))
        w = None if np.allclose(w, 1.0) else w
        ws = np.ones(n_enr) if w is None else w
        sae = float(np.sum(ws * np.array([p["sae"] for p in pats])) / np.sum(ws))
        fem_pool = sum(cand_g[pid].get("Sex") == "female" for pid in pool) / len(pool)
        old = sum(cand_g[pid].get("Age") == "65 years or older" for pid in pool) / len(pool)
        screen_mult = 1.0
        fem = fem_pool
        if female_target is not None:
            # composition-constrained enrolment: the scarcer sex limits accrual; screening needed scales by the
            # largest ratio of target share to the eligible pool's share
            screen_mult = max(female_target / fem_pool, (1 - female_target) / (1 - fem_pool))
            fem = female_target
        nns = 1 / y * screen_mult
        mult = rate_mult * (y / yield_) / screen_mult            # enrolment rate scales with the eligible yield at fixed screening
        d = evaluable_draws(n, w)
        ok = np.ones(DRAWS, bool)
        evals = {}
        for j, ww in enumerate(windows):
            # expected evaluable count (deterministic): the original protocol gives the simulated count itself
            evals[ww["endpoint"]] = float(n * np.sum(ws * E[:, j]) / np.sum(ws))
            if ww["required"]:
                ok &= d[:, j] >= ww["required"]
        return {"scenario": name, "how": how, "eligible_pct": y, "screened_per_enrollee": nns, "screened_for_target": n * nns,
                "median_recruitment_months": median_years(n, mult) * 12, "p_recruit_in_window": p_complete_by(window, n, mult) if window else None,
                "window_months": window * 12 if window else None, "female_pct": fem, "age65_pct": old,
                "sae_rate": sae, "sae_patients": sae * n, "enrolled": n, "evaluable_median": evals,
                "p_requirement": {ww["endpoint"]: float((d[:, j] >= ww["required"]).mean()) for j, ww in enumerate(windows) if ww["required"]},
                "p_evaluable_all": float(ok.mean()), "p_objectives": float(ok.mean()) * (p_ni if p_ni is not None else 1.0),
                "fu_visits_per_patient": burden["Follow-up visits"]["median"] - fu_less,
                "visit_days_per_patient": burden["Clinic visit days"]["median"] - fu_less}
    relax = next((c for c in by_crit if c["category"] != "Disease and stage" and c["gain_if_relaxed"] > 0), None)
    scen = [scenario("Original protocol", "the locked simulation")]
    if relax:
        pool = sorted(eligible | {pid for pid, f in failed.items() if f == {relax["criterion"]}})
        scen.append(scenario(f"Relax: {relax['label']}", f"patients failing only {relax['criterion']} become eligible; enrolment rate scales with "
                             "the eligible yield at a fixed screening throughput; their adverse-event and evaluability risk follows their age and sex "
                             "as in the simulated patients", pool=pool))
    if site_coef is not None:
        scen.append(scenario("20% more sites", f"enrolment rate x 1.2^{site_coef:.3f} (the historical accrual model's site coefficient)",
                             rate_mult=1.2 ** site_coef))
    if planned_years:
        scen.append(scenario("Recruitment window +6 months", "the planned window extended by 6 months", window=planned_years + 0.5))
    regions = Counter(cand_g[pid].get("Region") for pid in eligible if cand_g[pid].get("Region"))
    if regions:
        top = min(regions, key=lambda r: regions[r])
        share_now = regions[top] / sum(regions.values())
        new = min(0.95, share_now + 0.2)
        wts = {r: (new / share_now if r == top else (1 - new) / (1 - share_now)) for r in regions}
        pool_w = [pid for pid in eligible]
        sc = scenario(f"Regional mix: +20 points {top}", f"eligible candidates re-weighted to {new:.0%} from {top} (from {share_now:.0%})", pool=pool_w)
        # composition under the re-weighting
        tw = sum(wts.get(cand_g[pid].get("Region"), 1) for pid in pool_w)
        for key, f in (("female_pct", lambda g: g.get("Sex") == "female"), ("age65_pct", lambda g: g.get("Age") == "65 years or older")):
            sc[key] = sum(wts.get(cand_g[pid].get("Region"), 1) * f(cand_g[pid]) for pid in pool_w) / tw
        sc["asian_pct"] = sum(wts.get(cand_g[pid].get("Region"), 1) * (cand_g[pid].get("Race") == "Asian") for pid in pool_w) / tw
        sc["hispanic_pct"] = sum(wts.get(cand_g[pid].get("Region"), 1) * (cand_g[pid].get("Ethnicity") == "Hispanic or Latino") for pid in pool_w) / tw
        scen.append(sc)
    scen.append(scenario("50% female target", "enrolment held to 50% women; the scarcer sex limits accrual", female_target=0.5))
    scen.append(scenario("Enrolment +10%", f"{int(round(target * 1.1))} enrolled", n=int(round(target * 1.1))))
    scen.append(scenario("One fewer follow-up visit", "one follow-up visit removed per patient; the simulated withdrawal rate does not depend on "
                         "visit burden, so retention is unchanged", fu_less=1))
    for s in scen:
        if "asian_pct" not in s:
            s["asian_pct"] = sum(cand_g[pid].get("Race") == "Asian" for pid in eligible) / len(eligible)
            s["hispanic_pct"] = sum(cand_g[pid].get("Ethnicity") == "Hispanic or Latino" for pid in eligible) / len(eligible)
    longitudinal = _longitudinal(nct, version, st, journey, windows, target, rng) if (st("journey") / "visit_schedule.csv").exists() else None
    # ---- the canonical case-study values (L068): every report and figure reads these; scenario values are kept apart,
    # and a scenario's change is added to the original protocol's value, never substituted for it
    at = next(r for r in curve if r["enrolled"] == target)
    ev_canon = {w["endpoint"]: w["evaluable"] for w in windows}
    p_req = {w["endpoint"]: at[w["endpoint"]]["p_meets"] for w in windows if w["required"]}
    vs_rows = _read_csv(st("journey") / "visit_schedule.csv") if (st("journey") / "visit_schedule.csv").exists() else []
    withdrawn = {r["USUBJID"] for r in adsl if (r["EOTREAS"] or "").startswith("withdrawal")} | \
        {r["USUBJID"] for r in vs_rows if r["STATUS"] == "not attended: withdrew"}
    wd_sim = len(withdrawn) / n_enr
    death_sim = sum(r["DTHFL"] == "Y" for r in adsl) / n_enr
    # per arm and the enrolled demographics, from the same patients; response from the analysis stage (the realised best
    # overall response, next to the evidence input it was calibrated to; L069)
    arm_label = {a.get("arm_id"): _text(a.get("label")) for a in spec.get("arms") or []}
    an_file = st("analysis") / "analysis_results.json"
    an = json.loads(an_file.read_text(encoding="utf-8")) if an_file.exists() else {}
    eff = an.get("efficacy") or {}
    eff = {} if eff.get("status") == "NOT_APPLICABLE" else eff
    by_arm = {}
    for aid in sorted({r["ARMCD"] for r in adsl}):
        rows = [r for r in adsl if r["ARMCD"] == aid]
        n_a = len(rows)
        sae_a = sum(p["sae"] for p in pats if p["arm"] == aid)
        orr = (eff.get(aid) or {}).get("objective_response") or {}
        inp = ((an.get("latent_inputs") or {}).get(aid) or {}).get("response") or {}
        by_arm[aid] = {"label": arm_label.get(aid, aid), "n": n_a, "sae_rate": sae_a / n_a, "sae_count": sae_a,
                       "death_rate": sum(r["DTHFL"] == "Y" for r in rows) / n_a,
                       "withdrawal_rate_simulated": len({r["USUBJID"] for r in rows} & withdrawn) / n_a,
                       "response": {"rate": orr.get("rate"), "responders": orr.get("responders"), "n": (eff.get(aid) or {}).get("n"),
                                    "ci95": orr.get("ci95_exact"),
                                    "input": {k: inp.get(k) for k in ("value", "ci95", "level", "source")} if inp else None,
                                    "calibration": (an.get("response_calibration") or {}).get(aid)}}
    ages = [float(r["AGE"]) for r in adsl if r.get("AGE")]
    race_lab = {"white": "White", "asian": "Asian", "black_or_african_american": "Black or African American"}
    demographics = {"age_mean": float(np.mean(ages)) if ages else None, "age_sd": float(np.std(ages, ddof=1)) if len(ages) > 1 else None,
                    "female_share": sum(r["SEX"] == "female" for r in adsl) / n_enr,
                    "race_shares": {lab: sum(r["RACE"] == k for r in adsl) / n_enr for k, lab in race_lab.items()},
                    "hispanic_share": sum(r["ETHNIC"] == "hispanic_or_latino" for r in adsl) / n_enr}
    out_adsl = _read_csv(st("outputs") / "adsl.csv") if (st("outputs") / "adsl.csv").exists() else []
    split_outputs = dict(Counter(r["ARM"] for r in out_adsl)) or None
    o = scen[0]
    o.update({"evaluable_median": dict(ev_canon), "p_requirement": dict(p_req), "p_evaluable_all": at["p_all"],
              "p_objectives": at["p_all"] * (p_ni if p_ni is not None else 1.0), "sae_rate": overall_sae, "sae_patients": overall_sae * target})
    for s in scen:
        s["withdrawal_pct"] = wd_sim
    if longitudinal:
        bs = {b["scenario"]: b for b in longitudinal["burden_scenarios"]}
        b0 = bs.get("Original protocol")
        for b in longitudinal["burden_scenarios"]:
            d_ev = {ep: b["evaluable"][ep] - b0["evaluable"][ep] for ep in b["evaluable"]}
            d_p = {ep: b["p_required"][ep] - b0["p_required"][ep] for ep in b["p_required"]}
            b["reported"] = {"withdrawal_rate": wd_sim + (b["withdrawn_share"] - b0["withdrawn_share"]),
                             "evaluable": {ep: ev_canon[ep] + d_ev[ep] for ep in d_ev},
                             "p_requirement": {ep: min(1.0, max(0.0, p_req.get(ep, 0.0) + d_p[ep])) for ep in d_p if ep in p_req},
                             "p_joint": min(1.0, max(0.0, at["p_all"] + b["p_all_required"] - b0["p_all_required"])),
                             "basis": "original protocol's simulated value plus this schedule's expected change"}
        fewer = bs.get("One fewer follow-up visit")
        row = next((s for s in scen if s["scenario"] == "One fewer follow-up visit"), None)
        if fewer and row:
            rp = fewer["reported"]
            row.update({"how": fewer["how"] + "; withdrawal from the registry burden association for the change in visits per "
                               "patient-month, distributed over each patient's attended visits; reported as the original protocol's "
                               "value plus the schedule's expected change",
                        "withdrawal_pct": rp["withdrawal_rate"], "evaluable_median": rp["evaluable"], "p_requirement": rp["p_requirement"],
                        "p_evaluable_all": rp["p_joint"], "p_objectives": rp["p_joint"] * (p_ni if p_ni is not None else 1.0)})
    hist_sae = None
    tof = st("outputs") / "trial_outputs.json"
    if tof.exists():
        arms_e = ((json.loads(tof.read_text(encoding="utf-8")).get("feasibility") or {}).get("subgroup_estimates") or {}).get("arms") or {}
        vals = [a["serious_adverse_event"]["headline"]["estimate"] for a in arms_e.values() if a.get("serious_adverse_event")]
        hist_sae = sum(vals) / len(vals) if vals else None
    var = (rni or {}).get("variability") or {}
    case_study = {
        "original_protocol": {
            "enrolled": n_enr, "candidates": n_cand, "eligible": len(eligible), "eligible_rate": yield_,
            "screened_per_eligible": 1 / yield_, "screened_to_find_target": target / yield_,
            "evaluable": ev_canon, "p_requirement": p_req, "p_joint_requirement": at["p_all"],
            "p_primary_success_at_design": p_ni, "p_objectives": at["p_all"] * (p_ni if p_ni is not None else 1.0),
            "sae_rate_simulated": overall_sae, "sae_count_simulated": round(overall_sae * n_enr),
            "withdrawal_rate_simulated": wd_sim, "withdrawal_rate_predicted": ((longitudinal or {}).get("withdrawal_model") or {}).get("protocol", {}).get("share"),
            "death_rate_simulated": death_sim, "demographics": demographics, "by_arm": by_arm,
            "arm_split_outputs_stage": split_outputs,
            "recruitment": {"required_per_year": required_rate, "required_percentile": req_pct,
                            "p_complete_in_planned_window": p_complete_by(planned_years) if planned_years else None,
                            "median_months": median_years() * 12, "planned_months": planned_years * 12 if planned_years else None}},
        "scenarios": scen,
        "burden_scenarios": (longitudinal or {}).get("burden_scenarios"),
        "historical_evidence": {
            "sae_rate_arm_level": hist_sae, "recruitment_median_per_year": math.exp(mu),
            "pk_cv_auc_registry": (var.get("AN1") or {}).get("registry", {}).get("median_cv"),
            "pk_cv_ctrough_registry": (var.get("AN2") or {}).get("registry", {}).get("median_cv"),
            "pk_cv_auc_protocol": (var.get("AN1") or {}).get("protocol_derived_cv"),
            "pk_cv_ctrough_protocol": (var.get("AN2") or {}).get("protocol_derived_cv")},
        "definitions": {
            "evaluable": "simulated patients treated and on study through the endpoint's sampling day (this run's count)",
            "p_requirement": "Bayesian bootstrap of this run's patients at the target enrolment (4,000 draws, fixed stream)",
            "sae_rate_simulated": "simulated cohort incidence of any serious adverse event (this run)",
            "sae_rate_arm_level": "historical arm-level estimate from comparable registry trials (evidence, not a simulated value)",
            "withdrawal_rate_simulated": "share of this run's patients who withdrew (on treatment or from follow-up)",
            "withdrawal_rate_predicted": "registry protocol-burden model's prediction for this protocol",
            "by_arm.response.rate": "simulated best overall response (CR or PR) per arm at the analysis data cut-off (this run)",
            "by_arm.response.input": "the arm's response-rate input: same disease first, then similar drug classes, phase and era "
                                     "(evidence, not a simulated value)",
            "demographics": "simulated enrolled patients (this run)",
            "scenarios": "each scenario reports its own values; scenarios that do not change a quantity carry the original value exactly"}}

    doc = {"version": VERSION, "nct_id": nct, "run_version": version, "target": target,
           "protocol": _protocol_summary(spec, journey, windows, target),
           "candidates": n_cand, "eligible": len(eligible), "eligibility_yield": yield_, "screened_per_enrollee": 1 / yield_,
           "screened_for_target": target / yield_, "enrolled": n_enr, "treated": len(treated),
           "funnel": funnel, "criteria": by_crit, "categories": {c: crit[c]["category"] for c in crit},
           "evaluability": windows, "evaluable_curve": curve, "subgroups": subgroups,
           "recruitment": {"historical_lognormal": {"mu": mu, "sd": sd}, "historical_median_per_year": math.exp(mu),
                           "historical_percentiles": hist["patients_per_year"]["percentiles"], "planned_years": planned_years,
                           "required_rate_per_year": required_rate, "required_rate_percentile": req_pct,
                           "p_complete_in_planned_window": p_complete_by(planned_years) if planned_years else None,
                           "p_complete_in_planned_window_report": (hist.get("p_enrollment_complete_by") or {}),
                           "completion_curve": completion_curve,
                           "protocol_rate": protocol_rate and {"per_year": protocol_rate["patients_per_year"],
                                                               "p_complete_by": protocol_rate.get("p_enrollment_complete_by")},
                           "site_count": hist.get("site_count")},
           "completeness": completeness, "burden": burden, "withdrawal_rate": {a: v.get("value") for a, v in withdrawal.items()},
           "safety": safety, "overall_sae": overall_sae, "p_primary_success_at_design": p_ni, "scenarios": scen,
           "longitudinal": longitudinal, "case_study": case_study,
           "derivations": {
               "eligibility": "each simulated candidate's eligibility outcome; sequential funnel removes a candidate at the first category it fails",
               "gain_if_relaxed": "candidates who fail only that criterion",
               "evaluable": "treated and on study through the endpoint's sampling day (end of treatment or death ends it); sample collection "
                            "itself is not simulated",
               "evaluable_probability": "Bayesian bootstrap of the simulated patients (4,000 draws), joint across endpoints",
               "recruitment": "log-normal fitted to the planning report's historical accrual percentiles; duration = enrolment / rate",
               "objectives": "P(every evaluable count meets its requirement) x P(all primary hypotheses succeed at the design ratios)"}}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "feasibility.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    (out / "case_study_summary.json").write_text(json.dumps(case_study, indent=1, default=str), encoding="utf-8")
    (out / "FEASIBILITY.md").write_text(render(doc), encoding="utf-8")
    return doc


ITEM_CATEGORY = (("dose ", "Drug administration visits"), ("laboratory", "Laboratory (safety) assessments"),
                 ("tumour assessment", "Tumour assessments"), ("clinical assessment", "Cycle day-1 clinic visits"),
                 ("follow-up visit", "Survival follow-up visits"))


def _withdrawn(st) -> int | None:
    """The day a participant withdrew (on treatment or from follow-up), or None."""
    if st.off_study and "withdrawal" in st.off_study[1]:
        return st.off_study[0]
    if st.off_treatment and st.off_treatment[1].startswith("withdrawal"):
        return st.off_treatment[0]
    return None


def _bootstrap_meets(E: np.ndarray, required: list, n: int, rng, draws: int = DRAWS) -> tuple[list, float]:
    """P(each evaluable count >= its requirement) and P(all) for n enrolled (Bayesian bootstrap of the patients)."""
    m = len(E)
    ok = np.zeros((draws, E.shape[1]), bool)
    for d in range(draws):
        idx = rng.choice(m, size=n, p=rng.dirichlet(np.ones(m)))
        ok[d] = E[idx].sum(axis=0) >= np.array([r or 0 for r in required])
    return ok.mean(axis=0).tolist(), float(ok.all(axis=1).mean())


def _longitudinal(nct: str, version: str, st, journey: dict, windows: list[dict], target: int, rng) -> dict:
    """Protocol burden, retention, treatment delivery, monitoring intensity and data completeness (L064-L066)."""
    from . import journey as jr
    from . import withdrawal_burden as wb

    out: dict = {}
    model = wb.load()
    wd = next(iter((journey.get("withdrawal") or {}).values()), {}) or {}
    if model:
        keep = ["log2_duration_months", "log2_visits_per_month", "log2_outcome_measures", "log2_enrolled", "start_year_decade", "industry",
                "randomized"]
        out["withdrawal_model"] = {"trials": model["trials"], "participants": model["participants"], "overall_share": model["overall_share"],
                                   "coverage": model["coverage"], "coefficients": {k: model["coefficients"][k] for k in keep},
                                   "curves": model["curves"], "modifiers": model["modifiers"], "definitions": model["definitions"],
                                   "protocol": {"share": wd.get("value"), **(wd.get("detail") or {})}}
    # burden scenarios on the same locked patients: the registry association for the change in visits per patient-month,
    # distributed over each patient's attended visits
    ctx, sched, horizon, seed = jr.context_from_locks(nct, version)
    fu = (sched.get("follow_up_interval_days") or {}).get("value")
    cyc = (sched.get("cycle_length_days") or {}).get("value")
    variants = [("Original protocol", sched, "the protocol's schedule")]
    if fu:
        variants += [("One fewer follow-up visit", {**sched, "follow_up_skip": 1}, "the first survival follow-up visit after treatment dropped"),
                     ("Less frequent follow-up", {**sched, "follow_up_interval_days": {**sched["follow_up_interval_days"], "value": 2 * fu}},
                      f"survival follow-up every {2 * fu / 7:g} weeks instead of every {fu / 7:g}")]
        if cyc and cyc < fu:
            variants.append(("Higher-burden follow-up", {**sched, "follow_up_interval_days": {**sched["follow_up_interval_days"], "value": cyc}},
                             f"survival follow-up every {cyc / 7:g} weeks (the treatment cycle length) instead of every {fu / 7:g}"))
    scenarios, ref_rate = [], None
    for name, sch, how in variants:
        states, _, wds, _, _, pilot = jr.simulate_cohort(ctx, sch, horizon, seed, reference_visit_rate=ref_rate, return_pilot=True)
        w0 = next(iter(wds.values()))
        rate = w0["detail"].get("visits_per_patient_month") if w0.get("detail") else None
        if ref_rate is None:
            ref_rate = rate
        # expected values over each patient's own course (the no-withdrawal pass has the same disease courses): the chance
        # of still being on study at a day is (1 - per-visit hazard) ^ (visits attended before it); one random draw of
        # withdrawal would move these by more than the schedule does
        hz = {a: (w.get("detail") or {}).get("per_visit_hazard") or 0.0 for a, w in wds.items()}
        keep = []
        for s in pilot:
            days = sorted(d for d, _, _ in s.attended)
            keep.append((hz.get(s.arm_id, 0.0), days, bool(s.exposure), s.off_treatment[0]))

        def p_on(h, days, t):
            return (1 - h) ** sum(1 for d in days if d <= t)
        P = np.array([[float(tr and off >= w["on_study_day"]) * p_on(h, days, w["on_study_day"]) for w in windows] for h, days, tr, off in keep])
        draws = np.empty((2000, len(windows)))
        brng = np.random.default_rng(20261010)          # the same stream for every schedule: differences are the schedule's
        for k in range(2000):
            idx = brng.choice(len(P), size=target, p=brng.dirichlet(np.ones(len(P))))
            draws[k] = (brng.random((target, len(windows))) < P[idx]).sum(axis=0)
        req_n = np.array([w.get("required") or 0 for w in windows])
        ok = draws >= req_n
        exp_withdraw = float(np.mean([1 - (1 - h) ** len(days) for h, days, _, _ in keep]))
        visits_exp = sum(sum((1 - h) ** j for j in range(len(days))) for h, days, _, _ in keep)
        visits_all = sum(len(days) for _, days, _, _ in keep)
        scenarios.append({"scenario": name, "how": how, "predicted_withdrawal_share": w0.get("value"),
                          "per_visit_hazard": (w0.get("detail") or {}).get("per_visit_hazard"), "visits_per_patient_month": rate,
                          "withdrawn_share": exp_withdraw,
                          "withdrawn_share_one_draw": sum(_withdrawn(s) is not None for s in states) / len(states),
                          "retention": [{"day": t, "not_withdrawn": float(np.mean([p_on(h, days, t) for h, days, _, _ in keep]))}
                                        for t in range(0, horizon + 1, 14)],
                          "evaluable": {w["endpoint"]: round(float(P[:, j].sum()), 1) for j, w in enumerate(windows)},
                          "p_required": {w["endpoint"]: float(ok[:, j].mean()) for j, w in enumerate(windows)},
                          "p_all_required": float(ok.all(axis=1).mean()),
                          "visits_completed_expected": visits_exp / visits_all if visits_all else None,
                          "visits_per_patient": visits_all / len(keep),
                          "basis": "expected values over the patients' own disease courses (no-withdrawal pass) and the per-visit hazard"})
    out["burden_scenarios"] = scenarios
    # completeness of every protocol-required visit (locked journey): attended, or not attended because of withdrawal or death
    vs = _read_csv(st("journey") / "visit_schedule.csv") if (st("journey") / "visit_schedule.csv").exists() else []
    comp = {}
    for r in vs:
        for item in (r["PLANNED"] or "").split(";"):
            cat = next((c for key, c in ITEM_CATEGORY if item.startswith(key)), None)
            if not cat:
                continue
            c = comp.setdefault(cat, Counter())
            c["required"] += 1
            c[r["STATUS"]] += 1
    out["completeness"] = [{"category": cat, "required": c["required"], "attended": c["attended"] / c["required"],
                            "lost_withdrawal": c["not attended: withdrew"] / c["required"], "lost_death": c["not attended: died"] / c["required"],
                            "lost_operational": c["not attended"] / c["required"]} for cat, c in comp.items()]
    by_pt: dict = defaultdict(list)
    for r in vs:
        by_pt[r["USUBJID"]].append(r)
    pk = []
    for w in windows:
        need = got = lost_w = lost_d = 0
        for rows in by_pt.values():
            tx = [r for r in rows if not r["VISIT"].startswith("FU") and int(r["DAY"]) >= w["on_study_day"]]
            if tx:
                need += 1
                if any(r["STATUS"] == "attended" for r in tx):
                    got += 1
                elif any(r["STATUS"] == "not attended: withdrew" for r in tx):
                    lost_w += 1
                else:
                    lost_d += 1
        pk.append({"endpoint": w["endpoint"], "enrolled": len(by_pt), "protocol_course_reaches": need, "captured": got,
                   "lost_withdrawal": lost_w, "lost_death": lost_d, "required": w.get("required")})
    out["pk_capture"] = pk
    out["operational_missingness"] = "not modelled: no evidence for missed visits among participants on study (zero by construction)"
    # treatment delivery (administered treatment: received / scheduled while on treatment)
    ex = _read_csv(st("journey") / "ex.csv")
    adsl = {r["USUBJID"]: r for r in _read_csv(st("journey") / "adsl.csv")}
    per = defaultdict(lambda: [0, 0])
    for r in ex:
        per[r["USUBJID"]][0] += int(r["PLANNED_ADMIN"] or 0)
        per[r["USUBJID"]][1] += int(r["ACTUAL_ADMIN"] or 0)
    planned, given = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
    rdi = [float(a["RDI"]) for a in adsl.values() if a.get("RDI") not in (None, "")]

    def delivery(ids):
        p, g = sum(per[i][0] for i in ids), sum(per[i][1] for i in ids)
        return {"patients": len(ids), "delivery": g / p if p else None, "all_doses": sum(per[i][0] == per[i][1] for i in ids) / len(ids) if ids else None}
    groups = {"All": list(adsl)}
    for i, a in adsl.items():
        groups.setdefault(f"Arm {a['ARMCD']}", []).append(i)
        groups.setdefault("Age 65 or older" if float(a["AGE"]) >= 65 else "Age under 65", []).append(i)
        groups.setdefault("With a serious AE" if a["ANY_SAE"] == "Y" else "Without a serious AE", []).append(i)
    out["treatment_delivery"] = {"administrations_scheduled": planned, "administrations_received": given,
                                 "delivery": given / planned if planned else None, "missed": planned - given,
                                 "patients_all_doses": sum(v[0] == v[1] for v in per.values()) / len(per) if per else None,
                                 "patients_with_hold": sum(int(a["N_HOLDS"] or 0) > 0 for a in adsl.values()) / len(adsl),
                                 "patients_with_reduction": sum(int(a["N_REDUCTIONS"] or 0) > 0 for a in adsl.values()) / len(adsl),
                                 "rdi_median": float(np.median(rdi)) if rdi else None,
                                 "rdi_iqr": [float(np.quantile(rdi, 0.25)), float(np.quantile(rdi, 0.75))] if rdi else None,
                                 "by_group": {k: delivery(v) for k, v in groups.items()},
                                 "definition": "administrations received / administrations scheduled while on treatment; delays are not simulated"}
    # monitoring intensity: what the protocol asks of a participant per month on study
    att = [r for r in vs if r["STATUS"] == "attended"]
    months = sum(max(int(r["DAY"]) for r in rows) for rows in by_pt.values() if rows) / 30.44
    cnt = Counter()
    for r in att:
        for item in (r["PLANNED"] or "").split(";"):
            cat = next((c for key, c in ITEM_CATEGORY if item.startswith(key)), None)
            if cat:
                cnt[cat] += 1
    out["monitoring"] = {"per_patient_month": {k: v / months for k, v in cnt.items()} if months else {},
                         "clinic_visit_days_per_patient_month": len({(r["USUBJID"], r["DAY"]) for r in att}) / months if months else None,
                         "patient_months": months}
    # one simulated baseline patient and one longitudinal trace (synthetic EHR)
    pop_summary = json.loads((st("population") / "baseline_extra_summary.json").read_text(encoding="utf-8"))["summary"]
    out["baseline_sources"] = {k: v.get("source") for k, v in pop_summary["added_variables"].items()}
    out["not_simulated"] = pop_summary.get("not_simulated") or []
    tdir = st("journey") / "traces"
    if not tdir.exists():                          # a stage lock keeps the top-level files; the traces stay in the run folder
        tdir = Path("data/trial/runs") / nct / f"v{version}" / "journey" / "traces"
    traces = sorted(tdir.glob("patient_trace_*.json"))
    chosen = None
    for t in traces:
        d = json.loads(t.read_text(encoding="utf-8"))
        cats = {e["category"] for e in d["events"]}
        score = ("adverse event" in cats) + bool(d.get("progression_detected_day")) + ("follow-up" in cats) + 2 * any(
            "held" in (e.get("consequence") or "") for e in d["events"])
        if chosen is None or score > chosen[0]:
            chosen = (score, d)
    if chosen:
        d = chosen[1]
        out["trace"] = {"subject_id": d["subject_id"], "arm": d["arm"], "baseline": d["baseline"],
                        "events": [{k: e.get(k) for k in ("day", "visit", "category", "item", "result", "consequence")} for e in d["events"]]}
    return out


def _protocol_summary(spec: dict, journey: dict, windows: list[dict], target: int) -> dict:
    sched = journey.get("schedule") or {}
    arms = [_text(a.get("label")) for a in spec.get("arms") or []]
    alloc = ((spec.get("design") or {}).get("allocation") or {}).get("ratio")
    return {"target_enrolment": target, "allocation": alloc, "arms": arms,
            "primary_endpoints": [w["endpoint"] for w in windows], "required_evaluable": {w["endpoint"]: w.get("required") for w in windows},
            "criteria": len([c for c in spec.get("eligibility") or [] if c.get("logic")]),
            "cycle_days": (sched.get("cycle_length_days") or {}).get("value"), "max_cycles": (sched.get("max_cycles") or {}).get("value"),
            "tumour_assessment_days": (sched.get("tumour_assessment_interval_days") or {}).get("value"),
            "follow_up_days": (sched.get("follow_up_interval_days") or {}).get("value")}


def _p(x, d=0) -> str:
    return "—" if x is None else f"{100 * x:.{d}f}%"


def render(doc: dict) -> str:
    """The feasibility report: one section per planning question, every number from the locked simulation."""
    P, R = doc["protocol"], doc["recruitment"]
    L = [f"# {doc['nct_id']}: protocol feasibility (run v{doc['run_version']}, {doc['version']})", "",
         "Every number below comes from the locked simulation run (screened population, eligibility, enrolled cohort, patient "
         "journey, planning report, primary-engine results). How each is derived is stated with it and in section 9.", ""]
    cs = doc.get("case_study")
    if cs:
        o, h = cs["original_protocol"], cs["historical_evidence"]
        L += ["## 0. Case-study values (canonical: every figure and table uses these)", "", "| Quantity | Value |", "| --- | ---: |",
              f"| Enrolled | {o['enrolled']} |", f"| Eligible rate | {_p(o['eligible_rate'], 1)} |",
              f"| Candidates screened per eligible patient | {o['screened_per_eligible']:.2f} |"]
        L += [f"| Evaluable: {ep} | {n} |" for ep, n in o["evaluable"].items()]
        L += [f"| P(evaluable {ep} meets its requirement) | {_p(p, 1)} |" for ep, p in o["p_requirement"].items()]
        L += [f"| P(all requirements met) | {_p(o['p_joint_requirement'], 1)} |",
              f"| Serious AE, simulated cohort incidence | {_p(o['sae_rate_simulated'], 1)} ({o['sae_count_simulated']} of {o['enrolled']}) |",
              f"| Withdrawal, simulated cohort | {_p(o['withdrawal_rate_simulated'], 1)} |",
              f"| Withdrawal, registry burden model prediction | {_p(o['withdrawal_rate_predicted'], 1)} |",
              f"| Death, simulated cohort | {_p(o['death_rate_simulated'], 1)} |"]
        for a in (o.get("by_arm") or {}).values():
            r = a.get("response") or {}
            if r.get("rate") is not None:
                L.append(f"| Objective response, simulated, {a['label']} | {_p(r['rate'], 1)} ({r['responders']} of {r['n']}; 95% CI "
                         f"{_p(r['ci95'][0], 1)}-{_p(r['ci95'][1], 1)}) |")
        L += ["",
              "Historical evidence (not simulated values): "
              f"serious AE arm-level estimate {_p(h['sae_rate_arm_level'], 1)}; recruitment median {h['recruitment_median_per_year']:.0f}/year; "
              f"PK CV {_p(h['pk_cv_auc_registry'])} (AUC) and {_p(h['pk_cv_ctrough_registry'])} (Ctrough) in comparable trials, "
              f"{_p(h['pk_cv_auc_protocol'])} and {_p(h['pk_cv_ctrough_protocol'])} assumed by the protocol."
              + "".join(f" Response-rate input, {a['label']}: {_p(i['value'], 1)} (95% CI {_p(i['ci95'][0], 1)}-{_p(i['ci95'][1], 1)}; "
                        f"{i['level']}; {i['source']})." for a in (o.get("by_arm") or {}).values()
                        for i in [((a.get("response") or {}).get("input") or {})] if i.get("value") is not None and i.get("ci95")), ""]
    L += ["## 1. What the protocol demands", "",
         f"- Target enrolment {P['target_enrolment']}, allocation {':'.join(f'{x:g}' for x in P['allocation'] or [])}, arms: {'; '.join(P['arms'])}",
         f"- Primary endpoints and required evaluable participants: "
         + "; ".join(f"{k} ({v})" for k, v in P["required_evaluable"].items()),
         f"- {P['criteria']} executable eligibility criteria; cycle {P['cycle_days']} days, up to {P['max_cycles']} cycles; tumour assessment "
         f"every {P['tumour_assessment_days']} days; follow-up every {P['follow_up_days']} days", "",
         "## 2. Screening funnel", "",
         "| Step | Lost | Remaining | % of candidates | Lost at this step |", "| --- | ---: | ---: | ---: | ---: |"]
    for f in doc["funnel"]:
        L.append(f"| {f['step']} | {f.get('lost', '')} | {f['remaining']:,} | {_p(f.get('pct_remaining', 1.0), 1)} | {_p(f.get('pct_lost_at_step'), 1) if 'lost' in f else ''} |")
    L += ["", f"Eligibility yield **{_p(doc['eligibility_yield'], 1)}**; candidates screened per eligible patient **{doc['screened_per_enrollee']:.2f}**; "
          f"candidates screened to find {doc['target']} eligible patients: **{doc['screened_for_target']:.0f}** (eligible patients who decline or are "
          "not enrolled are not modelled).", "",
          "## 3. Criterion bottlenecks", "", "| Criterion | Category | Excluded | Gain if relaxed (points) |", "| --- | --- | ---: | ---: |"]
    for c in doc["criteria"][:15]:
        L.append(f"| {c['criterion']} {c['label']} | {c['category']} | {_p(c['pct_excluded'], 1)} | +{100 * c['gain_if_relaxed'] / doc['candidates']:.1f} |")
    L += ["", "## 4. Subgroups: availability, screening yield, representation, safety", "",
          "| Subgroup | Candidates | P(eligible) | Eligible share | Enrolled share | Serious AE (95% CI) |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for dim, levels in doc["subgroups"].items():
        for lv, r in levels.items():
            ci = r.get("sae_ci")
            sae = f"{_p(r['sae_rate'])} ({_p(ci[0])}-{_p(ci[1])})" if r.get("sae_rate") is not None else "—"
            L.append(f"| {dim}: {lv} | {_p(r['candidate_share'])} | {_p(r['p_eligible'])} | {_p(r['eligible_share'])} | {_p(r['enrolled_share'])} | {sae} |")
    L += ["", "## 5. Recruitment demand", "",
          f"- Required rate {R['required_rate_per_year']:.0f}/year ({doc['target']} in {R['planned_years'] * 12:.0f} months) = "
          f"{_ordinal(round(R['required_rate_percentile'] * 100))} percentile of comparable trials (historical median {R['historical_median_per_year']:.0f}/year).",
          f"- P(all {doc['target']} enrolled within the planned window): {_p(R['p_complete_in_planned_window'])} (planning report: "
          f"{_p(next(iter(R['p_complete_in_planned_window_report'].values()), None))}).",
          f"- Site count: {R['site_count']}.", "",
          "## 6. Endpoint evaluability", ""]
    for w in doc["evaluability"]:
        L.append(f"- {w['endpoint']}: {w['evaluable']} of {doc['enrolled']} evaluable ({_p(w['share'])}); rule: {w['rule']}; required {w['required']}")
    L += ["", "| Enrolled | " + " | ".join(f"P({w['endpoint']} ≥ {w['required']})" for w in doc["evaluability"] if w["required"]) + " | P(all) |",
          "| ---: | " + " | ".join("---:" for w in doc["evaluability"] if w["required"]) + " | ---: |"]
    for r in doc["evaluable_curve"]:
        L.append(f"| {r['enrolled']} | " + " | ".join(_p(r[w["endpoint"]]["p_meets"]) for w in doc["evaluability"] if w["required"]) + f" | {_p(r['p_all'])} |")
    L += ["", "## 7. Completeness, burden and safety", "", "| Assessment | On study | Alive |", "| --- | ---: | ---: |"]
    for c in doc["completeness"]:
        L.append(f"| {c['assessment']} | {_p(c['on_study'])} | {_p(c['alive'])} |")
    L += ["", "| Burden per patient | Median | IQR |", "| --- | ---: | --- |"]
    for k, v in doc["burden"].items():
        L.append(f"| {k} | {v['median']:.1f} | {v.get('q25', float('nan')):.0f}-{v.get('q75', float('nan')):.0f} |" if "q25" in v else f"| {k} | {v['median']:.2f} | |")
    lg = doc.get("longitudinal") or {}
    wp = ((lg.get("withdrawal_model") or {}).get("protocol") or {})
    if wp.get("share") is not None:
        ci = wp.get("ci95") or [None, None]
        L += ["", f"Withdrawal depends on protocol burden: the registry protocol-burden model predicts {_p(wp['share'], 1)} "
                  f"(95% CI {_p(ci[0], 1)}-{_p(ci[1], 1)}) for this protocol's participation duration, visit frequency and assessment count "
                  "(adjusted for phase, disease family, enrolment, start year, sponsor and randomisation); the share is distributed over the "
                  "visits each patient attends, so longer exposure to scheduled visits carries more risk."]
    else:
        L += ["", f"Withdrawal share used by the journey: {doc['withdrawal_rate']}"]
    td = lg.get("treatment_delivery") or {}
    if td:
        L += ["", "Treatment delivery and exposure (not adherence in the full sense: dose delays and missed doses are not modelled, so delivery "
                  f"is an upper bound): {_p(td['delivery'], 1)} of administrations scheduled while on treatment were given; "
                  f"{_p(td['patients_with_hold'], 1)} of patients had a dose hold; {_p(td['patients_with_reduction'], 1)} a dose reduction."]
    if lg.get("completeness"):
        L += ["", "| Protocol-required visits | Required | Attended | Lost: withdrawal | Lost: death |", "| --- | ---: | ---: | ---: | ---: |"]
        L += [f"| {c['category']} | {c['required']:,} | {_p(c['attended'], 1)} | {_p(c['lost_withdrawal'], 1)} | {_p(c['lost_death'], 1)} |"
              for c in lg["completeness"]]
        L += ["", "Missed visits among participants on study are not modelled (no evidence): losses are from withdrawal and death only."]
    L += ["", "| Safety | Share (95% CI) | Patients of the target |", "| --- | --- | ---: |"]
    for k, s in doc["safety"].items():
        L.append(f"| {k} | {_p(s['share'], 1)} ({_p(s['ci'][0], 1)}-{_p(s['ci'][1], 1)}) | {s['per_target']:.0f} |")
    L += ["", "## 8. Scenario stress test", "",
          "| Scenario | Eligible | Screened per eligible | Months to recruit | P(in window) | Women | Age ≥65 | Serious AE patients | Visit days | "
          + " | ".join(f"Evaluable {w['endpoint']}" for w in doc["evaluability"]) + " | P(objectives) |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | " + " | ".join("---:" for _ in doc["evaluability"]) + " | ---: |"]
    for s in doc["scenarios"]:
        L.append(f"| {s['scenario']} | {_p(s['eligible_pct'])} | {s['screened_per_enrollee']:.2f} | {s['median_recruitment_months']:.0f} | "
                 f"{_p(s['p_recruit_in_window'])} | {_p(s['female_pct'])} | {_p(s['age65_pct'])} | {s['sae_patients']:.0f} | {s['visit_days_per_patient']:.0f} | "
                 + " | ".join(f"{s['evaluable_median'][w['endpoint']]:.0f}" for w in doc["evaluability"]) + f" | {_p(s['p_objectives'])} |")
    L += ["", "How each scenario is derived:", ""] + [f"- **{s['scenario']}**: {s['how']}" for s in doc["scenarios"]]
    L += ["", "## 9. Derivations", ""] + [f"- {k}: {v}" for k, v in doc["derivations"].items()]
    L += ["", "Figures: `figures/Figure1-9` (PNG, SVG, PDF).", ""]
    return "\n".join(L)
