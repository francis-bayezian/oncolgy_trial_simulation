"""Analysis results layer: the simulated trial reported as a real oncology trial is (any protocol; no model calls).

Standards (documents at the repository root):
* PharmaSUG 2018 DS06 (Lee): response is DERIVED from tumour measurements under the protocol's response criteria
  (RECIST 1.1, Cheson, IMWG-type marker criteria): SDTM TU (lesions), TR (measurements), RS (response per visit), and
  ADaM ADRS and ADTTE (OS, PFS, TTP, DOR, TTR);
* FDA CDER Standard Safety Tables and Figures, Integrated Guide (August 2022): Tables 2, 3, 4, 5, 6, 7, 9, 12, 13, 36
  and 54, by arm, with the risk difference (95% CI) of each arm against the control arm.

Per patient, the latent truths come from the same sources the endpoint stage uses (clinical_asset.trial.quantify):
* responder: the arm's response-rate input; complete response: the arm's complete-response input as a share of it
  (else CR_SHARE, assumption A23);
* depth: a responder's burden falls to between the PR threshold and 99% below baseline (CR: 0); a non-responder's
  changes uniformly within the stable-disease band (assumption A24);
* progression: the journey's progression model (independent of response depth, assumption A24); at progression the
  target burden rises past the PD threshold from the nadir, or a new lesion appears (NEW_LESION_SHARE, A24);
* death: the journey's death day, else the overall-survival input (ladder) beyond the journey horizon;
* assessments: the protocol's tumour-assessment interval until progression, death, loss to follow-up or the end of
  follow-up.

Response thresholds are the protocol's own compiled criteria (target-level PR decrease, PD increase, CR disappearance,
deeper decrease categories such as VGPR); when the protocol compiles none, RECIST 1.1 (30% / 20% and 5 mm) is used
(assumption A25). Confirmation of CR/PR is applied when the protocol's response criteria mention confirmation.
"""

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from .predictive import from_draws

ANALYSIS_VERSION = "analysis-results-1.1.0"
DAY = 365.25
CR_SHARE = 0.15                 # A23
NEW_LESION_SHARE = 0.35         # A24
CONFIRM_DAYS = 28
PPS_MIN_MONTHS = 1.0           # A26
PPS_DEFAULT_MONTHS = 12.0      # A26
SD_MIN_DAYS = 42
RECIST = {"pr": 30.0, "pd": 20.0, "pd_abs_mm": 5.0, "deeper": [], "source": "RECIST 1.1 defaults (no criteria compiled; A25)"}
GENERIC_WORDS = {"adverse", "events", "event", "variable", "aes", "ae"}
BOR_ORDER = ["CR", "PR", "SD", "NON-CR/NON-PD", "PD", "NE"]


def _q(x):
    return ((x or {}).get("text") if isinstance(x, dict) else x) or ""


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _rows(path: Path) -> list[dict]:
    if not path.exists() or not path.stat().st_size:
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ----------------------------------------------------------------------------- response criteria from the protocol


def criteria(spec: dict) -> dict:
    """Target-level thresholds of the protocol's first criteria set: PR decrease (%), PD increase (%), deeper decrease
    categories (e.g. VGPR 90%), and whether confirmation is required."""
    rc = spec.get("response_criteria") or {}
    cats = rc.get("categories") or []
    text = json.dumps(rc, ensure_ascii=False).casefold()
    confirm = "confirm" in text
    pr = pd = None
    deeper = []
    for c in cats:
        name = _q(c.get("category")).casefold()
        t = c.get("threshold") or {}
        v = t.get("value")
        if v is None:
            continue
        if t.get("direction") == "decrease" and ("pr" in name.split() or "partial" in name) and pr is None:
            pr = float(v)
        elif t.get("direction") == "increase" and ("pd" in name or "progress" in name) and pd is None:
            pd = float(v)
        elif t.get("direction") == "decrease" and v and float(v) > (pr or 0):
            label = re.sub(r"[^A-Za-z/ -]", "", _q(c.get("category"))).strip().split(":")[0][:30] or "deeper response"
            deeper.append((float(v), label))
    if pr is None or pd is None:
        return {**RECIST, "confirm": confirm}
    deeper = sorted({(v, lab) for v, lab in deeper if v > pr and v < 100}, reverse=True)
    return {"pr": pr, "pd": pd, "pd_abs_mm": 5.0 if pd <= 20 else 0.0, "deeper": deeper[:1], "confirm": confirm,
            "source": "protocol response criteria (compiled thresholds)"}


# ----------------------------------------------------------------------------- tumour measurements and derived response


def _overall(target: str, nontarget: str, new: bool) -> str:
    """RECIST 1.1 overall response from target, non-target and new-lesion status (Table 1 of the guideline)."""
    if new or target == "PD" or nontarget == "PD":
        return "PD"
    if target == "CR" and nontarget in ("CR", "NONE"):
        return "CR"
    if target in ("CR", "PR"):
        return "PR"
    if target == "SD":
        return "SD"
    return "NE"


def simulate_tumour(subject: str, arm: str, horizon: int, interval: int, p_resp: float, p_cr: float, prog_day: float | None,
                    death_day: float | None, loss_day: float | None, crit: dict, rng: np.random.Generator) -> dict:
    """TU, TR and RS records of one patient, and the latent and derived summaries."""
    n_target = int(rng.integers(1, 6))
    lesions = [round(float(rng.uniform(10, 60)), 1) for _ in range(n_target)]
    base = sum(lesions)
    n_nontarget = int(rng.integers(0, 4))
    responder = rng.random() < p_resp
    complete = responder and rng.random() < p_cr
    if complete:
        nadir_frac = 0.0
    elif responder:
        nadir_frac = 1 - float(rng.uniform(crit["pr"] / 100, 0.99))
    else:
        nadir_frac = 1 + float(rng.uniform(-(crit["pr"] - 1) / 100, (crit["pd"] - 1) / 100))
    t_nadir = 2 * interval
    new_lesion_at_pd = rng.random() < NEW_LESION_SHARE
    end = min(x for x in (horizon, death_day or math.inf, loss_day or math.inf))
    days = list(range(interval, int(end) + 1, interval))
    tu = [{"USUBJID": subject, "TULNKID": f"T{i + 1:02d}", "TUTESTCD": "TUMIDENT", "TUORRES": "TARGET", "TUDY": 0} for i in range(n_target)]
    tu += [{"USUBJID": subject, "TULNKID": f"NT{i + 1:02d}", "TUTESTCD": "TUMIDENT", "TUORRES": "NON-TARGET", "TUDY": 0} for i in range(n_nontarget)]
    tr = [{"USUBJID": subject, "TRLNKID": f"T{i + 1:02d}", "TRTESTCD": "LDIAM", "TRORRES": d, "TRORRESU": "mm", "TRDY": 0, "VISIT": "BASELINE"}
          for i, d in enumerate(lesions)]
    tr.append({"USUBJID": subject, "TRLNKID": "", "TRTESTCD": "SUMDIAM", "TRORRES": round(base, 1), "TRORRESU": "mm", "TRDY": 0, "VISIT": "BASELINE"})
    rs, nadir, pd_day, visits = [], base, None, []
    for k, d in enumerate(days, 1):
        frac = 1 + (nadir_frac - 1) * min(1.0, d / t_nadir)
        progressed = prog_day is not None and d >= prog_day
        new = progressed and new_lesion_at_pd
        if progressed and not new_lesion_at_pd:
            frac = max(frac, (nadir / base) * (1 + crit["pd"] / 100) + 0.05, (nadir + crit["pd_abs_mm"] + 1) / base)
        s = round(base * frac, 1)
        for i, d0 in enumerate(lesions):
            tr.append({"USUBJID": subject, "TRLNKID": f"T{i + 1:02d}", "TRTESTCD": "LDIAM", "TRORRES": round(d0 * frac, 1), "TRORRESU": "mm",
                       "TRDY": d, "VISIT": f"TA{k}"})
        tr.append({"USUBJID": subject, "TRLNKID": "", "TRTESTCD": "SUMDIAM", "TRORRES": s, "TRORRESU": "mm", "TRDY": d, "VISIT": f"TA{k}"})
        if s == 0:
            target = "CR"
        elif s <= base * (1 - crit["pr"] / 100):
            target = "PR"
        elif s >= nadir * (1 + crit["pd"] / 100) and s - nadir >= crit["pd_abs_mm"]:
            target = "PD"
        else:
            target = "SD"
        nontarget = "NONE" if not n_nontarget else ("CR" if complete and d >= t_nadir else "NON-CR/NON-PD")
        overall = _overall(target, nontarget, new)
        nadir = min(nadir, s)
        for code, val in (("TRGRESP", target), ("NTRGRESP", nontarget), ("NEWLPROG", "Y" if new else "N"), ("OVRLRESP", overall)):
            rs.append({"USUBJID": subject, "RSTESTCD": code, "RSORRES": val, "RSDY": d, "VISIT": f"TA{k}", "RSCAT": crit["source"]})
        visits.append((d, overall))
        if overall == "PD":
            pd_day = d
            break
    return {"tu": tu, "tr": tr, "rs": rs, "visits": visits, "pd_day": pd_day, "last_assessment": visits[-1][0] if visits else None,
            "latent": {"responder": responder, "complete": complete, "nadir_frac": nadir_frac}}


def best_overall_response(visits: list[tuple], confirm: bool) -> tuple[str, int | None]:
    """Best overall response (and the day it was first met); CR/PR need a confirming assessment >= CONFIRM_DAYS later
    when the protocol requires confirmation; SD must be met at least SD_MIN_DAYS after the start."""
    best, first = "NE", None
    for i, (d, r) in enumerate(visits):
        if r in ("CR", "PR"):
            if confirm and not any(r2 in ("CR", "PR") and d2 - d >= CONFIRM_DAYS for d2, r2 in visits[i + 1:]):
                r = "SD" if d >= SD_MIN_DAYS else "NE"
        elif r in ("SD", "NON-CR/NON-PD") and d < SD_MIN_DAYS:
            r = "NE"
        if BOR_ORDER.index(r) < BOR_ORDER.index(best):
            best, first = r, d
    return best, first


# ----------------------------------------------------------------------------- survival summaries


def km(t: np.ndarray, e: np.ndarray) -> list[tuple]:
    """Kaplan-Meier steps (time, survival, variance term) at event times."""
    order = np.argsort(t)
    t, e = t[order], e[order]
    n, s, var, out = len(t), 1.0, 0.0, []
    for i in range(len(t)):
        if e[i]:
            at = n - i
            s *= 1 - 1 / at
            var += 1 / (at * (at - 1)) if at > 1 else 0.0
            out.append((float(t[i]), s, var))
    return out


def km_summary(t: np.ndarray, e: np.ndarray, landmarks_months=(6, 12, 24)) -> dict:
    steps = km(t, e)
    med = next((x[0] for x in steps if x[1] <= 0.5), None)
    lo = hi = None
    for x in steps:                                    # log(-log) CI of S(t); the median CI where it crosses 0.5
        if 0 < x[1] < 1:
            se = math.sqrt(x[2]) / abs(math.log(x[1]))
            up = x[1] ** math.exp(-1.96 * se)
            dn = x[1] ** math.exp(1.96 * se)
            if lo is None and dn <= 0.5:
                lo = x[0]
            if up <= 0.5:
                hi = x[0]
                break
    land = {}
    for m in landmarks_months:
        at = m * 30.4375
        s = [x[1] for x in steps if x[0] <= at]
        # known when follow-up reaches the landmark, or when the last patient's time is an event (the curve has ended)
        ended = bool(e[np.argmax(t)]) if len(t) else False
        land[f"{m}m"] = round(100 * (s[-1] if s else 1.0), 1) if t.max() >= at or ended else None
    return {"n": int(len(t)), "events": int(e.sum()), "median_months": None if med is None else round(med / 30.4375, 2),
            "median_ci95_months": [None if lo is None else round(lo / 30.4375, 2), None if hi is None else round(hi / 30.4375, 2)],
            "landmark_percent": land}


def hazard_ratio(t1, e1, t0, e0) -> dict:
    """Log-rank (Mantel) O/E hazard ratio of group 1 vs group 0 with its 95% CI and the log-rank p-value."""
    t = np.concatenate([t1, t0])
    e = np.concatenate([e1, e0]).astype(bool)
    g = np.concatenate([np.ones(len(t1)), np.zeros(len(t0))])
    o1 = e1n = v = 0.0
    for ti in np.unique(t[e]):
        at = t >= ti
        n, n1 = at.sum(), (at & (g == 1)).sum()
        d = ((t == ti) & e).sum()
        d1 = ((t == ti) & e & (g == 1)).sum()
        o1 += d1
        e1n += d * n1 / n
        v += d * (n1 / n) * (1 - n1 / n) * (n - d) / max(n - 1, 1)
    if v <= 0:
        return {"hr": None}
    z = (o1 - e1n) / math.sqrt(v)
    log_hr = (o1 - e1n) / v
    return {"hr": round(math.exp(log_hr), 3), "ci95": [round(math.exp(log_hr - 1.96 / math.sqrt(v)), 3), round(math.exp(log_hr + 1.96 / math.sqrt(v)), 3)],
            "logrank_p_two_sided": float(2 * stats.norm.sf(abs(z)))}


def exact_ci(x: int, n: int) -> list[float]:
    if not n:
        return [None, None]
    return [float(stats.beta.ppf(0.025, x, n - x + 1)) if x else 0.0, float(stats.beta.ppf(0.975, x + 1, n - x)) if x < n else 1.0]


def risk_difference(x1: int, n1: int, x0: int, n0: int) -> str:
    if not n1 or not n0:
        return ""
    p1, p0 = x1 / n1, x0 / n0
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    d = 100 * (p1 - p0)
    return f"{d:.1f} ({d - 196 * se:.1f}, {d + 196 * se:.1f})"


# ----------------------------------------------------------------------------- system organ class of a term


class SocMap:
    def __init__(self, path: Path = Path("data/reference_derived/ae_term_soc.json")):
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"map": {}}
        self.map = doc["map"]
        self.by_bag = {}
        for k, v in self.map.items():
            self.by_bag.setdefault(frozenset(k.split()) - GENERIC_WORDS, v)

    @staticmethod
    def key(term: str) -> str:
        return " ".join(re.sub(r"_+", " ", term or "").casefold().split())

    def soc(self, term: str) -> str:
        k = self.key(term)
        hit = self.map.get(k) or self.by_bag.get(frozenset(k.split()) - GENERIC_WORDS)
        return hit["soc"] if hit else "SOC not determined"


# ----------------------------------------------------------------------------- the stage


RESPONSE_VARS = {"objective_response_rate", "complete_response", "pathological_complete_response", "disease_control_rate", "clinical_benefit_rate"}
PROGRESSION_VARS = {"progression_free_survival", "time_to_progression", "event_free_survival", "disease_free_survival", "relapse_free_survival",
                    "duration_of_response", "time_to_response", "time_to_treatment_failure"}


def data_cutoff(patients: list[dict], rule: dict, spec: dict, interval: int) -> dict:
    """The analysis data cut-off day (from the first enrolment), as the protocol defines it:
    * event-driven: the day the protocol's event target is observed (calendar enrolment + progression, at the next
      scheduled assessment), capped at the stated maximum follow-up;
    * 'N evaluable patients followed for at least T': the last enrolment plus T;
    * otherwise: the last enrolment plus the stated follow-up (else FOLLOW_UP_YEARS)."""
    from .endpoints import follow_up_years

    if not patients:
        return {"day": 0.0, "rule": "no patients"}
    last_enrol = max(p["enrol"] for p in patients)
    cap = (rule.get("max_followup_years") or 0) * DAY or None
    if rule.get("event_target"):
        events = sorted(p["enrol"] + math.ceil(min(x for x in (p["prog"], p["death"]) if x is not None) / interval) * interval
                        for p in patients if p["prog"] is not None or p["death"] is not None)
        k = int(rule["event_target"])
        if len(events) >= k and not (cap and events[k - 1] > cap):
            return {"day": float(events[k - 1]), "rule": f"event-driven: the {k}th event (protocol event target)"}
        if cap:
            seen = sum(1 for x in events if x <= cap)
            return {"day": float(cap), "rule": f"stated maximum follow-up reached with {seen} of the {k} target events (the event target is not met)"}
        day = cap or last_enrol + follow_up_years(spec) * DAY
        return {"day": float(day), "rule": f"event target {k} not reached ({len(events)} events): stated maximum follow-up"}
    if rule.get("min_followup_years"):
        return {"day": last_enrol + float(rule["min_followup_years"]) * DAY, "rule": f"last enrolment + {rule['min_followup_years']} years of follow-up"}
    yrs = follow_up_years(spec)
    return {"day": last_enrol + yrs * DAY, "rule": f"last enrolment + {yrs:g} years (stated follow-up, else default)"}


def efficacy_scope(spec: dict) -> dict:
    """Which efficacy datasets the protocol calls for (its endpoints and compiled response criteria): a diagnostic or
    supportive-care study with neither gets none (L037)."""
    from .quantify import classify

    kinds = [classify(_q(e.get("name")), e.get("type")) for e in spec.get("endpoints") or []]
    response = any(k == "proportion" and v in RESPONSE_VARS for k, v in kinds) or bool((spec.get("response_criteria") or {}).get("categories"))
    pfs = any(k == "time_to_event" and v in PROGRESSION_VARS for k, v in kinds)
    os_ = any(k == "time_to_event" and v == "overall_survival" for k, v in kinds)
    return {"response": response, "PFS": pfs, "TTP": pfs, "OS": os_, "any": response or pfs or os_}


def run(spec_lock: Path, journey_lock: Path, safety_lock: Path, eligibility_lock: Path, outcomes_lock: Path, out_dir: Path,
        facts_lock: Path | None = None, seed: int = 20261006) -> dict:
    from .endpoints import follow_up_years
    from .quantify import quantify
    from .studyspec import load_facts, load_studyspec

    spec, rec = load_studyspec(spec_lock)
    facts = load_facts(facts_lock)[0] if facts_lock else None
    j = Path(journey_lock)
    adsl, adae = _rows(j / "adsl.csv"), _rows(j / "adae.csv")
    summary = json.loads((j / "journey_summary.json").read_text(encoding="utf-8"))
    safety = json.loads((Path(safety_lock) / "safety_results.json").read_text(encoding="utf-8"))
    feats = {a["arm_id"]: ((a.get("safety_v3") or {}).get("features") or {}) for a in safety["arms"]}
    elig = json.loads((Path(eligibility_lock) / "eligibility_summary.json").read_text(encoding="utf-8"))["summary"]
    rng = np.random.default_rng(seed)
    crit = criteria(spec)
    arms = [a for a in spec["arms"] if any(r["ARMCD"] == a["arm_id"] for r in adsl)]
    label = {a["arm_id"]: _q(a.get("label")) for a in arms}
    om = Path(outcomes_lock) / "outcome_model.json"
    om_doc = json.loads(om.read_text(encoding="utf-8")) if om.exists() else {}
    outcome_rule = om_doc.get("analysis_rule") or {}
    control = om_doc.get("control_arm_id")
    control = control if control in label else (arms[-1]["arm_id"] if arms else None)   # else the last arm is the reference
    interval = int((summary.get("schedule") or {}).get("tumour_assessment_interval_days", {}).get("value") or 56)
    fu_days = int(follow_up_years(spec) * DAY)

    # ---------------- efficacy: measurements -> response -> ADaM
    scope = efficacy_scope(spec)
    tu, tr, rs, adrs, adtte = [], [], [], [], []
    inputs = {}
    # pass 1: each patient's latent progression and death, on the calendar (enrolment day + time)
    from .outcomes import sample_efs_years

    from . import subgroup_evidence as sge

    sg_evidence = sge.load(Path(eligibility_lock))    # the protocol's subgroup factors and their prognostic effects (A28)
    coh_dir = j.parent / j.name.replace("journey_", "cohorts_")
    cohort = _jsonl(coh_dir / summary["cohort_file"]) if summary.get("cohort_file") and (coh_dir / summary["cohort_file"]).exists() else []
    baseline_of = {c["subject_id"]: c["baseline"] for c in cohort}
    patients = []
    for a in (arms if scope["any"] else []):
        aid = a["arm_id"]
        f = feats.get(aid) or next(iter(feats.values()), {})
        orr = quantify(spec, aid, "proportion", "objective_response_rate", f, facts)
        cr = quantify(spec, aid, "proportion", "complete_response", f, facts)
        osm = quantify(spec, aid, "time_to_event", "overall_survival", f, facts)
        p_resp = orr.get("value") if orr.get("value") is not None else 0.0
        p_cr = min(1.0, (cr["value"] / p_resp)) if cr.get("value") and p_resp else CR_SHARE
        pv = ((summary.get("progression") or {}).get(aid) or {}).get("value") or {}
        # post-progression survival: the arm's OS input minus its progression median (failing patients), at least
        # PPS_MIN_MONTHS; with no OS input, PPS_DEFAULT_MONTHS (A26)
        pfs_med = 12 * math.log(2) / pv["rate_per_year"] if pv.get("rate_per_year") else None
        pps_months = max(PPS_MIN_MONTHS, osm["value"] - pfs_med) if osm.get("value") and pfs_med else PPS_DEFAULT_MONTHS
        inputs[aid] = {"response": orr, "complete_response_share": {"value": p_cr, "source": cr.get("source") if cr.get("value") and p_resp else "assumption A23"},
                       "overall_survival": osm, "progression": (summary.get("progression") or {}).get(aid),
                       "post_progression_survival_months": pps_months}
        for r in [x for x in adsl if x["ARMCD"] == aid]:
            # the patient's subgroup levels shift the progression hazard and the response odds (A28; centred on the mix)
            log_hr, log_or = sge.patient_log_effects(baseline_of.get(r["USUBJID"]) or {}, sg_evidence)
            p_i = 1 / (1 + math.exp(-(math.log(p_resp / (1 - p_resp)) + log_or))) if log_or and 0 < p_resp < 1 else p_resp
            prog = None
            if pv.get("rate_per_year"):
                y = float(sample_efs_years(1, {"cure_fraction": pv.get("cure_fraction") or 0.0,
                                               "failure_rate_per_year": pv["rate_per_year"] * math.exp(log_hr)}, 1.0, rng)[0])
                prog = y * DAY if math.isfinite(y) else None
            death = float(r["DTHDY"]) if r.get("DTHDY") else None
            if death is None and prog is not None:      # death after progression (A26): OS is never independent of PFS
                death = prog + float(rng.exponential(pps_months / 12 / math.log(2))) * DAY
            patients.append({"r": r, "aid": aid, "p_resp": p_i, "p_cr": p_cr, "prog": prog, "death": death,
                             "enrol": float(r.get("ENROLLMENT_DAY") or 0.0),
                             "loss": float(r["TRTEDY"]) if r["EOTREAS"].startswith("withdrawal") else None})

    # the analysis data cut-off, as the protocol defines it (L037)
    cutoff = data_cutoff(patients, outcome_rule, spec, interval)

    # pass 2: measurements and response up to each patient's own follow-up at the cut-off
    # the analysis population at the cut-off: patients enrolled by then (as in a real interim or final analysis)
    cutoff["enrolled_by_cutoff"] = sum(pt["enrol"] <= cutoff["day"] for pt in patients)
    cutoff["planned"] = len(patients)
    for pt in [x for x in patients if x["enrol"] <= cutoff["day"]]:
        r, aid = pt["r"], pt["aid"]
        horizon = max(0.0, cutoff["day"] - pt["enrol"])
        death = pt["death"] if pt["death"] is not None and pt["death"] <= horizon else None
        tumour = simulate_tumour(r["USUBJID"], aid, int(horizon), interval, pt["p_resp"], pt["p_cr"], pt["prog"], death, pt["loss"], crit, rng)
        tu += tumour["tu"]
        tr += tumour["tr"]
        rs += tumour["rs"]
        bor, first = best_overall_response(tumour["visits"], crit["confirm"])
        adrs += [{"USUBJID": r["USUBJID"], "ARMCD": aid, "PARAMCD": "OVRLRESP", "AVALC": v, "ADY": d} for d, v in tumour["visits"]]
        adrs.append({"USUBJID": r["USUBJID"], "ARMCD": aid, "PARAMCD": "BOR" if not crit["confirm"] else "CBOR", "AVALC": bor, "ADY": first})
        last = tumour["last_assessment"] or 0
        pd = tumour["pd_day"]
        # PFS: progression or death is an event; death after two or more missed assessments is censored at the last one
        if pd is not None:
            pfs = (pd, 0, "progressive disease")
        elif death is not None and death <= last + 2 * interval:
            pfs = (death, 0, "death")
        else:
            pfs = (last, 1, "censored at last adequate tumour assessment")
        contact = min(horizon, pt["loss"] if pt["loss"] is not None else horizon)
        os_ = (death, 0, "death") if death is not None else (contact, 1, "censored at last contact")
        ttp = (pd, 0, "progressive disease") if pd is not None else (last, 1, "censored at last adequate tumour assessment")
        rows = [x for x in (("PFS", pfs), ("OS", os_), ("TTP", ttp)) if scope[x[0]]]
        if scope["response"] and bor in ("CR", "PR") and first is not None:
            rows.append(("DOR", ((pfs[0] - first), pfs[1], pfs[2])))
            rows.append(("TTR", (first, 0, "first response")))
        for code, (aval, cnsr, desc) in rows:
            adtte.append({"USUBJID": r["USUBJID"], "ARMCD": aid, "PARAMCD": code, "AVAL": round(float(aval), 1), "CNSR": cnsr, "EVNTDESC": desc})

    efficacy = {} if scope["any"] else {"status": "NOT_APPLICABLE", "reason": "the protocol has no tumour-response or time-to-event endpoint"}
    for a in (arms if scope["any"] else []):
        aid = a["arm_id"]
        bors = [x["AVALC"] for x in adrs if x["ARMCD"] == aid and x["PARAMCD"] in ("BOR", "CBOR")]
        n = len(bors)
        resp = sum(b in ("CR", "PR") for b in bors)
        efficacy[aid] = {"n": n, "best_overall_response": dict(Counter(bors)),
                         "objective_response": ({"responders": resp, "rate": round(resp / n, 4) if n else None, "ci95_exact": exact_ci(resp, n)}
                                if scope["response"] else {"status": "NOT_APPLICABLE", "rate": None, "ci95_exact": [None, None]}),
                         "disease_control": (lambda dc: {"n": dc, "rate": round(dc / n, 4) if n else None, "ci95_exact": exact_ci(dc, n)})(
                             sum(b in ("CR", "PR", "SD", "NON-CR/NON-PD") for b in bors))}
        for code in ("PFS", "OS", "TTP", "DOR", "TTR"):
            rows = [x for x in adtte if x["ARMCD"] == aid and x["PARAMCD"] == code]
            if rows:
                efficacy[aid][code] = km_summary(np.array([x["AVAL"] for x in rows], float), np.array([x["CNSR"] == 0 for x in rows]))
    comparisons = {}
    for a in (arms if scope["any"] else []):
        if a["arm_id"] == control:
            continue
        o1, o0 = (efficacy.get(a["arm_id"]) or {}).get("objective_response") or {}, (efficacy.get(control) or {}).get("objective_response") or {}
        if scope["response"] and o1.get("rate") is not None and o0.get("rate") is not None:
            n1, n0 = efficacy[a["arm_id"]]["n"], efficacy[control]["n"]
            d = o1["rate"] - o0["rate"]
            se = math.sqrt(o1["rate"] * (1 - o1["rate"]) / n1 + o0["rate"] * (1 - o0["rate"]) / n0) if n1 and n0 else 0.0
            comparisons[f"ORR {a['arm_id']} vs {control}"] = {"difference": round(d, 4), "ci95": [round(d - 1.96 * se, 4), round(d + 1.96 * se, 4)]}
        for code in [c for c in ("PFS", "OS") if scope[c]]:
            g1 = [x for x in adtte if x["ARMCD"] == a["arm_id"] and x["PARAMCD"] == code]
            g0 = [x for x in adtte if x["ARMCD"] == control and x["PARAMCD"] == code]
            if g1 and g0:
                comparisons[f"{code} {a['arm_id']} vs {control}"] = hazard_ratio(
                    np.array([x["AVAL"] for x in g1]), np.array([x["CNSR"] == 0 for x in g1]),
                    np.array([x["AVAL"] for x in g0]), np.array([x["CNSR"] == 0 for x in g0]))

    # ---------------- FDA standard safety tables
    socs = SocMap()
    n_arm = {a["arm_id"]: sum(r["ARMCD"] == a["arm_id"] for r in adsl) for a in arms}
    teae = [x for x in adae if x.get("TRTEMFL", "Y") == "Y"]
    # a patient who stopped treatment for an adverse event (journey exit, A14) without an AE record carrying that action:
    # the last treatment-emergent AE that started on or before the stop day is the one that led to discontinuation
    for r in adsl:
        if r["EOTREAS"].startswith("adverse"):
            own = [x for x in teae if x["USUBJID"] == r["USUBJID"]]
            if own and not any("discontinue" in (x.get("AEACN") or "").casefold() for x in own):
                before = [x for x in own if float(x.get("AESTDY") or 0) <= float(r["TRTEDY"] or 0)] or own
                cause = max(before, key=lambda x: (float(x.get("AESTDY") or 0), int(x.get("AETOXGR") or 0)))
                cause["AEACN"] = ((cause.get("AEACN") or "") + ";discontinue_all (stop day; derived)").strip(";")

    def pts(rows, aid):
        return len({x["USUBJID"] for x in rows if x["ARMCD"] == aid})

    def cell(x, aid):
        return f"{x} ({100 * x / n_arm[aid]:.1f})" if n_arm[aid] else "0"

    def row(name, counts):
        rd = [risk_difference(counts[a["arm_id"]], n_arm[a["arm_id"]], counts[control], n_arm[control]) if a["arm_id"] != control else ""
              for a in arms]
        return [name] + [cell(counts[a["arm_id"]], a["arm_id"]) for a in arms] + [" ; ".join(x for x in rd if x)]

    head = ["", *[f"{a['arm_id']} {label[a['arm_id']][:40]} (N={n_arm[a['arm_id']]})" for a in arms], f"Risk difference % (95% CI) vs {control}"]
    tables: dict[str, list] = {}

    def by_arm(f):
        return {a["arm_id"]: f(a["arm_id"]) for a in arms}

    def subj(aid, cond):
        return sum(1 for r in adsl if r["ARMCD"] == aid and cond(r))

    # Table 2: demographics
    t2 = [head]
    for name, cond in (("Female", lambda r: r["SEX"] == "female"), ("Male", lambda r: r["SEX"] == "male"),
                       ("Age < 65 years", lambda r: float(r["AGE"] or 0) < 65), ("Age 65-74 years", lambda r: 65 <= float(r["AGE"] or 0) < 75),
                       ("Age >= 75 years", lambda r: float(r["AGE"] or 0) >= 75)):
        t2.append(row(name, by_arm(lambda aid, c=cond: subj(aid, c))))
    for race in sorted({r["RACE"] for r in adsl}):
        t2.append(row(f"Race: {race}", by_arm(lambda aid, rc=race: subj(aid, lambda r: r["RACE"] == rc))))
    t2.append(["Age, mean (SD)"] + [f"{np.mean([float(r['AGE']) for r in adsl if r['ARMCD'] == a['arm_id']]):.1f} "
                                    f"({np.std([float(r['AGE']) for r in adsl if r['ARMCD'] == a['arm_id']], ddof=1):.1f})" for a in arms] + [""])
    tables["Table 2. Baseline demographic characteristics, safety population"] = t2
    # Table 3: screening and enrolment
    tables["Table 3. Patient screening and enrollment"] = [["", "n"], ["Screened (generated population)", str(elig["patients"])],
                                                           ["Eligible", str(elig["status_counts"]["ELIGIBLE"])],
                                                           ["Screen failures", str(elig["status_counts"]["INELIGIBLE"])],
                                                           ["Enrolled", str(len({r['USUBJID'].split('-P')[0] for r in adsl}))]]
    # Table 4: disposition
    t4 = [head, row("Safety population", n_arm)]
    reasons = sorted({r["EOTREAS"] for r in adsl})
    t4.append(row("Discontinued study drug", by_arm(lambda aid: subj(aid, lambda r: not r["EOTREAS"].startswith("completed")))))
    for rsn in reasons:
        if not rsn.startswith("completed"):
            t4.append(row(f"   {rsn}", by_arm(lambda aid, x=rsn: subj(aid, lambda r: r["EOTREAS"] == x))))
    t4.append(row("Completed planned treatment", by_arm(lambda aid: subj(aid, lambda r: r["EOTREAS"].startswith("completed")))))
    t4.append(row("Died", by_arm(lambda aid: subj(aid, lambda r: r.get("DTHFL") == "Y"))))
    tables["Table 4. Patient disposition"] = t4
    # Table 5: exposure
    t5 = [["Parameter", *head[1:-1]]]
    # exposure duration of records that started (a later period after the participant left has none, L044)
    dur = {a["arm_id"]: np.array([float(r["TRTEDY"]) - float(r["TRTSDY"]) + 1 for r in adsl if r["ARMCD"] == a["arm_id"] and r["TRTSDY"]] or [0.0])
           for a in arms}
    t5.append(["Duration of treatment, days: mean (SD)"] + [f"{dur[a['arm_id']].mean():.1f} ({dur[a['arm_id']].std(ddof=1):.1f})" for a in arms])
    t5.append(["Median (min, max)"] + [f"{np.median(dur[a['arm_id']]):.0f} ({dur[a['arm_id']].min():.0f}, {dur[a['arm_id']].max():.0f})" for a in arms])
    t5.append(["Total exposure, person-years"] + [f"{dur[a['arm_id']].sum() / DAY:.1f}" for a in arms])
    for lab, lo in (("Any duration (at least 1 dose)", 1), (">= 1 month", 30.4375), (">= 3 months", 91.3), (">= 6 months", 182.6), (">= 12 months", 365.25)):
        t5.append([lab] + [cell(int((dur[a["arm_id"]] >= lo).sum()), a["arm_id"]) for a in arms])
    tables["Table 5. Duration of treatment exposure, safety population"] = t5
    # Table 6: overview of adverse events
    act = lambda x, w: w in (x.get("AEACN") or "").casefold()  # noqa: E731
    t6 = [head]
    for name, rowsel in (("Any TEAE", teae), ("SAE", [x for x in teae if x["AESER"] == "Y"]),
                         ("AE leading to discontinuation of study drug", [x for x in teae if act(x, "discontinue")]),
                         ("AE leading to dose interruption", [x for x in teae if act(x, "hold") or act(x, "delay")]),
                         ("AE leading to dose reduction", [x for x in teae if act(x, "reduce")]),
                         ("Grade >= 3 AE", [x for x in teae if int(x.get("AETOXGR") or 0) >= 3])):
        t6.append(row(name, by_arm(lambda aid, rs_=rowsel: pts(rs_, aid))))
    t6.append(row("Deaths", by_arm(lambda aid: subj(aid, lambda r: r.get("DTHFL") == "Y"))))
    tables["Table 6. Overview of adverse events, safety population"] = t6
    # Table 7: deaths
    tables["Table 7. Deaths, safety population"] = [head, row("Total deaths", by_arm(lambda aid: subj(aid, lambda r: r.get("DTHFL") == "Y"))),
                                                    row("   On treatment", by_arm(lambda aid: subj(aid, lambda r: r["EOTREAS"] == "death"))),
                                                    ["   Cause of death", *["not simulated (registry disposition gives no cause)"] * len(arms), ""]]

    def soc_pt(rowsel, title):
        t = [head, row("Any", by_arm(lambda aid: pts(rowsel, aid)))]
        by_soc = defaultdict(list)
        for x in rowsel:
            by_soc[socs.soc(x["AETERM"])].append(x)
        for soc in sorted(by_soc, key=lambda s: -len({x["USUBJID"] for x in by_soc[s]})):
            t.append(row(soc, by_arm(lambda aid, s=soc: pts(by_soc[s], aid))))
            for term in sorted({x["AETERM"] for x in by_soc[soc]}, key=lambda tm: -len({x["USUBJID"] for x in by_soc[soc] if x["AETERM"] == tm})):
                t.append(row(f"   {term.replace('_', ' ')}", by_arm(lambda aid, tm=term, s=soc: pts([x for x in by_soc[s] if x["AETERM"] == tm], aid))))
        tables[title] = t
    soc_pt([x for x in teae if x["AESER"] == "Y"], "Table 9. Patients with serious adverse events by system organ class and preferred term")
    soc_pt([x for x in teae if act(x, "discontinue")], "Table 12. Patients with adverse events leading to treatment discontinuation by SOC and PT")
    soc_pt(teae, "Table 36. Patients with adverse events by system organ class and preferred term")
    common = [head]
    for term in sorted({x["AETERM"] for x in teae}):
        c = by_arm(lambda aid, tm=term: pts([x for x in teae if x["AETERM"] == tm], aid))
        if any(n_arm[k] and c[k] / n_arm[k] >= 0.05 for k in c):
            common.append(row(term.replace("_", " "), c))
    tables["Table 13. Patients with common adverse events occurring at >= 5% frequency"] = common
    t54 = [["Event", *[f"{a['arm_id']} events per 100 person-years" for a in arms]]]
    for name, rowsel in (("Any TEAE", teae), ("SAE", [x for x in teae if x["AESER"] == "Y"])):
        t54.append([name] + [f"{100 * sum(1 for x in rowsel if x['ARMCD'] == a['arm_id']) / max(dur[a['arm_id']].sum() / DAY, 1e-9):.1f}" for a in arms])
    tables["Table 54. Exposure-adjusted incidence rates"] = t54
    soc_pt([x for x in teae if act(x, "reduce") or act(x, "hold") or act(x, "delay") or act(x, "interrupt")],
           "Patients with adverse events leading to dose interruption or reduction by SOC and PT")
    # maximum toxicity grade per patient: overall, then grade >= 3 by organ system
    worst = defaultdict(int)
    for x in teae:
        worst[x["USUBJID"]] = max(worst[x["USUBJID"]], int(x.get("AETOXGR") or 0))
    tg = [head]
    for g in (1, 2, 3, 4, 5):
        tg.append(row(f"Maximum grade {g}", by_arm(lambda aid, gg=g: subj(aid, lambda r: worst.get(r["USUBJID"]) == gg))))
    by_soc3 = defaultdict(list)
    for x in teae:
        if int(x.get("AETOXGR") or 0) >= 3:
            by_soc3[socs.soc(x["AETERM"])].append(x)
    for soc in sorted(by_soc3, key=lambda s: -len({x["USUBJID"] for x in by_soc3[s]})):
        tg.append(row(f"Grade >= 3: {soc}", by_arm(lambda aid, s=soc: pts(by_soc3[s], aid))))
    tables["Patients with adverse events by maximum toxicity grade"] = tg

    # screen failures by criterion, and every result by subgroup
    from . import subgroup_report

    elig_rows = _jsonl(Path(eligibility_lock) / "eligibility.jsonl")
    tables["Screen failures by eligibility criterion"] = subgroup_report.screen_fail_reasons(spec, elig_rows)
    pop_dir = Path(eligibility_lock).parent / Path(eligibility_lock).name.replace("eligibility_", "population_")
    subgroups = subgroup_report.report(spec, adsl, teae, adrs, adtte, [a["arm_id"] for a in arms], control, cohort,
                                       _jsonl(pop_dir / "population.jsonl"), elig_rows, sge.effect_sources(sg_evidence),
                                       sge.prevalence_sources(sg_evidence))

    out = Path(out_dir)
    (out / "sdtm").mkdir(parents=True, exist_ok=True)
    (out / "adam").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)
    for name, rows_ in (("sdtm/tu", tu), ("sdtm/tr", tr), ("sdtm/rs", rs), ("adam/adrs", adrs), ("adam/adtte", adtte)):
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            if rows_:
                w = csv.DictWriter(fh, fieldnames=list(dict.fromkeys(k for r in rows_ for k in r)))
                w.writeheader()
                w.writerows(rows_)
    for title, t in tables.items():
        slug = re.sub(r"[^a-z0-9]+", "_", title.casefold().split(".")[0]).strip("_")
        with open(out / "tables" / f"{slug}.csv", "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(t)
    unmapped = sorted({x["AETERM"] for x in teae if socs.soc(x["AETERM"]) == "SOC not determined"})
    sg_files = subgroup_report.write(subgroups, out / "subgroups", [a["arm_id"] for a in arms])
    (out / "subgroups" / "subgroups.json").write_text(json.dumps(subgroups, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    doc = {"analysis_version": ANALYSIS_VERSION, "seed": seed, "inputs": {"studyspec": rec["files"]["studyspec.json"]},
           "efficacy_scope": scope, "data_cutoff": cutoff if scope["any"] else None, "response_criteria": crit, "assessment_interval_days": interval, "follow_up_days": fu_days, "control_arm": control,
           "latent_inputs": inputs, "efficacy": efficacy, "comparisons": comparisons, "censoring": subgroup_report.censoring(adtte),
           "safety_tables": list(tables), "terms_without_soc": unmapped,
           "subgroups": {"factors": subgroups["factors"], "files": sg_files},
           "standards": ["PharmaSUG 2018 DS06 (RECIST/Cheson/IMWG-type response derivation; SDTM TU/TR/RS; ADaM ADRS/ADTTE)",
                         "FDA CDER Standard Safety Tables and Figures Integrated Guide (Aug 2022): Tables 2-7, 9, 12, 13, 36, 54",
                         "results by subgroup: protocol stratification factors and analysis subgroups, FDA demographics, baseline disease factors"],
           "not_produced": ["FDA Medical Query tables (no machine-readable FMQ definitions)", "laboratory and vital-sign tables (not simulated)",
                            "MedDRA coding (registry terms with their reported organ system are used)",
                            "results by region (the recruitment model has no site country)"]}
    (out / "analysis_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "analysis_results.md").write_text(render(doc, tables, label) + "\n".join(subgroup_report.render(subgroups, sg_files)), encoding="utf-8")
    return doc


def render(doc: dict, tables: dict, label: dict) -> str:
    c = doc["response_criteria"]
    L = ["# Analysis results", "",
         f"Response criteria: PR >= {c['pr']:g}% decrease from baseline, PD >= {c['pd']:g}% increase from nadir"
         + (f" and >= {c['pd_abs_mm']:g} mm" if c.get("pd_abs_mm") else "") + f"; confirmation {'required' if c['confirm'] else 'not required'} "
         f"({c['source']}). Tumour assessments every {doc['assessment_interval_days']} days; data cut-off "
         + (f"day {doc['data_cutoff']['day']:.0f} after the first enrolment ({doc['data_cutoff']['rule']}); "
            f"{doc['data_cutoff'].get('enrolled_by_cutoff')} of {doc['data_cutoff'].get('planned')} patients enrolled by then." if doc.get("data_cutoff") else "not applicable."), "",
         "## Efficacy (derived from simulated tumour measurements)", "",
         "| Arm | N | ORR (95% CI) | DCR (95% CI) | Best response | TTR median, months | DOR median, months | PFS median, months (95% CI) | PFS 12 m | OS median, months (95% CI) | OS 12 m |",
         "| --- | ---: | --- | --- | --- | ---: | ---: | --- | ---: | --- | ---: |"]
    if doc["efficacy"].get("status") == "NOT_APPLICABLE":
        L += [f"Not applicable: {doc['efficacy']['reason']}."]
    for aid, e in ({} if doc["efficacy"].get("status") == "NOT_APPLICABLE" else doc["efficacy"]).items():
        o = e["objective_response"]
        ci = o["ci95_exact"]
        p, s = e.get("PFS") or {}, e.get("OS") or {}
        fmt = lambda k: (f"{k['median_months']} ({k['median_ci95_months'][0]}, {k['median_ci95_months'][1]})" if k.get("median_months") is not None else "not reached") if k else "-"  # noqa: E731
        orr = f"{100 * o['rate']:.1f}% ({100 * (ci[0] or 0):.1f}-{100 * (ci[1] or 0):.1f})" if o.get("rate") is not None else "not an endpoint"
        dc = e.get("disease_control") or {}
        dcr = (f"{100 * dc['rate']:.1f}% ({100 * (dc['ci95_exact'][0] or 0):.1f}-{100 * (dc['ci95_exact'][1] or 0):.1f})"
               if dc.get("rate") is not None and o.get("rate") is not None else "-")
        med = lambda k: (e.get(k) or {}).get("median_months") or "-"  # noqa: E731
        L.append(f"| {aid} {label.get(aid, '')[:30]} | {e['n']} | {orr} | {dcr} | "
                 f"{', '.join(f'{k} {v}' for k, v in sorted(e['best_overall_response'].items()))} | {med('TTR')} | {med('DOR')} | {fmt(p)} | "
                 f"{(p.get('landmark_percent') or {}).get('12m')} | {fmt(s)} | {(s.get('landmark_percent') or {}).get('12m')} |")
    for k, v in doc["comparisons"].items():
        if v.get("hr"):
            L.append(f"\n- {k}: HR {v['hr']} (95% CI {v['ci95'][0]}-{v['ci95'][1]}), log-rank p = {v['logrank_p_two_sided']:.3f}")
        elif v.get("difference") is not None:
            L.append(f"\n- {k}: difference {100 * v['difference']:.1f} percentage points (95% CI {100 * v['ci95'][0]:.1f} to {100 * v['ci95'][1]:.1f})")
    if doc.get("censoring"):
        L += ["", "Censoring: " + "; ".join(f"{code} {arm}: {c['events']} events, {c['censored']} censored"
                                            + (f" ({', '.join(f'{r} {n}' for r, n in c['by_reason'].items() if 'censor' in r)})" if c["censored"] else "")
                                            for code, by in doc["censoring"].items() if code in ("PFS", "OS") for arm, c in by.items())]
    L += ["", "## FDA standard safety tables", ""]
    for title, t in tables.items():
        L += [f"### {title}", "", "| " + " | ".join(t[0]) + " |", "| " + " | ".join("---" for _ in t[0]) + " |"]
        L += ["| " + " | ".join(str(x) for x in r) + " |" for r in t[1:60]]
        L.append("")
    if doc["terms_without_soc"]:
        L.append(f"Terms without a registry organ system: {', '.join(doc['terms_without_soc'])}.")
    L.append("Not produced: " + "; ".join(doc["not_produced"]) + ".")
    return "\n".join(L) + "\n"
