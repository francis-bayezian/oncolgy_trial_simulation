"""Protocol burden and participant withdrawal across registry trials (L064).

Outcome per trial: the share of participants who started the first participant-flow period and left it by their own
decision, loss to follow-up or physician decision (the journey's withdrawal reasons). Protocol burden as the registry
records it, read the same way for every trial:
  participation duration   the adverse-event reporting period (months; its longest stated duration)
  visit frequency          the most frequent stated assessment interval in the outcome measures ('every 6 weeks',
                           'Q3W'): visits per month; a 'not stated' flag where no interval is stated
  assessment count         the number of registered outcome measures
adjusted for phase, disease family, enrolment, start year, industry sponsorship and randomisation.

The association is estimated at trial level (observational: trials with more assessments differ in other ways too);
the journey propagates it to patients across the visits they attend (journey.py). Patient-level modifiers (age, sex,
ECOG) are estimated from arm-level baseline composition against arm-level withdrawal: ecological, reported for
transparency, not applied.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

from .. import assets

VERSION = "withdrawal-burden-1.0.0"
UNIT_MONTHS = {"day": 12 / 365.25, "week": 12 / 52.18, "month": 1.0, "year": 12.0}
UNIT_WEEKS = {"day": 1 / 7, "d": 1 / 7, "week": 1.0, "wk": 1.0, "w": 1.0, "month": 52.18 / 12, "mo": 52.18 / 12}
DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(day|week|month|year)s?\b", re.I)
EVERY = re.compile(r"\b(?:every|each)\s+(\d+(?:\.\d+)?)\s*(day|week|month)s?\b|\bq\s?(\d+)\s?(d|w|wk|mo)\b", re.I)
MIN_FAMILY_TRIALS = 30
BURDEN = ("log2_duration_months", "log2_visits_per_month", "log2_outcome_measures")


def duration_months(text: str | None) -> float | None:
    vals = [float(n) * UNIT_MONTHS[u.lower().rstrip("s")] for n, u in DURATION.findall(text or "")]
    vals = [v for v in vals if 0.2 <= v <= 240]
    return max(vals) if vals else None


def interval_weeks(text: str | None) -> float | None:
    vals = []
    for m in EVERY.finditer(text or ""):
        n, u = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        w = float(n) * UNIT_WEEKS[u.lower().rstrip("s")]
        if 0.5 <= w <= 52:
            vals.append(w)
    return min(vals) if vals else None


def trial_features(record: dict) -> dict:
    ps = record.get("protocolSection") or {}
    rs = record.get("resultsSection") or {}
    om = ps.get("outcomesModule") or {}
    outs = (om.get("primaryOutcomes") or []) + (om.get("secondaryOutcomes") or []) + (om.get("otherOutcomes") or [])
    text = " ".join(f"{o.get('timeFrame') or ''} {o.get('description') or ''}" for o in outs)
    start = ((ps.get("statusModule") or {}).get("startDateStruct") or {}).get("date") or ""
    design = ps.get("designModule") or {}
    sponsor = ((ps.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("class")
    return {"duration_months": duration_months((rs.get("adverseEventsModule") or {}).get("timeFrame")),
            "interval_weeks": interval_weeks(text), "outcome_measures": len(outs),
            "start_year": int(start[:4]) if start[:4].isdigit() else None, "industry": sponsor == "INDUSTRY",
            "randomized": (design.get("designInfo") or {}).get("allocation") == "RANDOMIZED"}


def _dataset() -> tuple[list[dict], list[dict]]:
    """Trial rows (withdrawals, starters, features) and arm rows (with baseline age, sex and ECOG)."""
    from . import journey_evidence as je
    from . import patient_risk as pr

    groups = je._disposition()
    raw = Path(assets.path("raw_ctgov"))
    by_trial: dict[str, list] = {}
    for g in groups:
        by_trial.setdefault(g["nct_id"], []).append(g)
    trials, arms = [], []
    for nct, gs in by_trial.items():
        f = raw / f"{nct}.json"
        if not f.exists():
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        feats = trial_features(rec)
        k = sum(min(g["started"], sum(g["by_reason"].get(r, 0.0) for r in je.OTHER_WITHDRAWAL)) for g in gs)
        n = sum(g["started"] for g in gs)
        if n < 5:
            continue
        trials.append({"nct_id": nct, "phase": gs[0]["phase"] or "NA", "family": gs[0]["family"] or "other", "k": k, "n": n, **feats})
        base = pr.baseline_by_group(rec.get("resultsSection") or {})
        for g in gs:
            b = base.get(pr._key(g["group_title"])) or {}
            if b.get("age") is None or g["started"] < 5:
                continue
            arms.append({"nct_id": nct, "k": min(g["started"], sum(g["by_reason"].get(r, 0.0) for r in je.OTHER_WITHDRAWAL)),
                         "n": g["started"], "age": b.get("age"), "female": b.get("female"), "ecog1": b.get("ecog1")})
    return trials, arms


def _design(rows: list[dict], levels: dict) -> tuple[np.ndarray, list[str]]:
    names = ["intercept", *BURDEN, "duration_not_stated", "interval_not_stated", "log2_enrolled", "start_year_decade",
             "industry", "randomized"] + [f"phase:{p}" for p in levels["phases"][1:]] + [f"family:{f}" for f in levels["families"][1:]]
    X = []
    for r in rows:
        dur, iv = r.get("duration_months"), r.get("interval_weeks")
        x = [1.0,
             math.log2(dur / levels["ref_duration"]) if dur else 0.0,
             math.log2((4.345 / iv) / levels["ref_visits"]) if iv else 0.0,
             math.log2(max(1, r["outcome_measures"]) / levels["ref_outcomes"]),
             0.0 if dur else 1.0, 0.0 if iv else 1.0,
             math.log2(max(r["n"], 1) / levels["ref_enrolled"]), ((r.get("start_year") or 2012) - 2012) / 10,
             float(bool(r.get("industry"))), float(bool(r.get("randomized")))]
        x += [float(r["phase"] == p) for p in levels["phases"][1:]]
        x += [float(r["family"] == f) for f in levels["families"][1:]]
        X.append(x)
    return np.array(X), names


def _fit(X: np.ndarray, k: np.ndarray, n: np.ndarray, ridge: float = 1e-3) -> dict:
    """Binomial GLM (logit) by Newton steps; covariance scaled by the Pearson overdispersion (quasi-binomial)."""
    b = np.zeros(X.shape[1])
    b[0] = math.log((k.sum() + 0.5) / (n.sum() - k.sum() + 0.5))
    P = np.diag([0.0] + [ridge] * (X.shape[1] - 1))
    for _ in range(100):
        p = 1 / (1 + np.exp(-(X @ b)))
        W = n * p * (1 - p)
        H = X.T @ (X * W[:, None]) + P
        step = np.linalg.solve(H, X.T @ (k - n * p) - P @ b)
        b += step
        if np.max(np.abs(step)) < 1e-9:
            break
    p = 1 / (1 + np.exp(-(X @ b)))
    pearson = float(np.sum((k - n * p) ** 2 / np.maximum(n * p * (1 - p), 1e-12)))
    phi = max(1.0, pearson / max(1, len(k) - X.shape[1]))
    cov = np.linalg.inv(X.T @ (X * (n * p * (1 - p))[:, None]) + P) * phi
    return {"beta": b, "cov": cov, "dispersion": phi}


def build(out_dir: Path | None = None) -> dict:
    trials, arms = _dataset()
    fam = Counter(t["family"] for t in trials)
    families = [f for f, c in fam.most_common() if c >= MIN_FAMILY_TRIALS and f != "other"]
    for t in trials:
        t["family"] = t["family"] if t["family"] in families else "other"
    phases = [p for p, _ in Counter(t["phase"] for t in trials).most_common()]
    med = lambda key: float(np.median([t[key] for t in trials if t.get(key)]))  # noqa: E731
    levels = {"phases": phases, "families": [families[0], *families[1:], "other"] if families else ["other"],
              "ref_duration": med("duration_months"), "ref_visits": 4.345 / med("interval_weeks"),
              "ref_outcomes": med("outcome_measures"), "ref_enrolled": med("n")}
    X, names = _design(trials, levels)
    k = np.array([t["k"] for t in trials], float)
    n = np.array([t["n"] for t in trials], float)
    fit = _fit(X, k, n)
    se = np.sqrt(np.diag(fit["cov"]))
    coef = {nm: {"log_odds": float(b), "se": float(s), "or": math.exp(b), "ci95": [math.exp(b - 1.96 * s), math.exp(b + 1.96 * s)],
                 "p": float(2 * stats.norm.sf(abs(b / s))) if s > 0 else None}
            for nm, b, s in zip(names, fit["beta"], se, strict=True)}
    curves = {f: _curve(trials, levels, fit, f) for f in BURDEN}
    modifiers = _modifiers(arms, trials, levels)
    doc = {"version": VERSION, "trials": len(trials), "participants": int(n.sum()), "withdrawals": int(k.sum()),
           "overall_share": float(k.sum() / n.sum()), "dispersion": fit["dispersion"], "levels": levels, "names": names,
           "beta": fit["beta"].tolist(), "cov": fit["cov"].tolist(), "coefficients": coef, "curves": curves,
           "coverage": {"duration_stated": sum(1 for t in trials if t.get("duration_months")),
                        "interval_stated": sum(1 for t in trials if t.get("interval_weeks"))},
           "modifiers": modifiers,
           "definitions": {"outcome": "left the first participant-flow period by subject decision, loss to follow-up or physician decision",
                           "duration": "longest duration stated in the adverse-event reporting period",
                           "visit_frequency": "most frequent 'every N days/weeks/months' or 'QnW' stated in the outcome measures",
                           "assessment_count": "number of registered outcome measures",
                           "coefficients": "odds ratio per doubling (approximately a rate ratio at these low withdrawal shares); "
                                           "quasi-binomial standard errors"}}
    out = Path(out_dir or Path(assets.path("patient_risk")).parent / "withdrawal_burden")
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    with open(out / "trials.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(t) + "\n" for t in trials)
    return doc


def _curve(trials: list[dict], levels: dict, fit: dict, feature: str) -> dict:
    """Adjusted response by fifths of a burden feature (trials stating it): the feature entered as categories with every
    other covariate as in the main model, as predicted withdrawal at the reference covariates."""
    key = {"log2_duration_months": "duration_months", "log2_visits_per_month": "interval_weeks", "log2_outcome_measures": "outcome_measures"}[feature]
    rows = [t for t in trials if t.get(key)]
    vals = np.array([t[key] if key != "interval_weeks" else 4.345 / t[key] for t in rows], float)
    edges = np.unique(np.quantile(vals, [0, 0.2, 0.4, 0.6, 0.8, 1.0]))
    if len(edges) < 3:
        return {"status": "TOO_FEW_LEVELS"}
    bins = np.clip(np.searchsorted(edges, vals, side="right") - 1, 0, len(edges) - 2)
    X, names = _design(rows, levels)
    j = names.index(feature)
    D = np.zeros((len(rows), len(edges) - 2))
    for i, b in enumerate(bins):
        if b > 0:
            D[i, b - 1] = 1.0
    Xc = np.hstack([np.delete(X, j, axis=1), D])
    f = _fit(Xc, np.array([t["k"] for t in rows], float), np.array([t["n"] for t in rows], float))
    base_ix = list(range(Xc.shape[1] - D.shape[1]))
    ref = np.zeros(Xc.shape[1])
    ref[0] = 1.0
    out = []
    for b in range(len(edges) - 1):
        x = ref.copy()
        if b > 0:
            x[len(base_ix) + b - 1] = 1.0
        eta, var = float(x @ f["beta"]), float(x @ f["cov"] @ x)
        inv = lambda z: 1 / (1 + math.exp(-z))  # noqa: E731
        out.append({"low": float(edges[b]), "high": float(edges[b + 1]), "median": float(np.median(vals[bins == b])), "trials": int(np.sum(bins == b)),
                    "share": inv(eta), "ci95": [inv(eta - 1.96 * math.sqrt(var)), inv(eta + 1.96 * math.sqrt(var))]})
    return {"status": "RESOLVED", "feature": key, "bins": out}


def _modifiers(arms: list[dict], trials: list[dict], levels: dict) -> dict:
    """Arm-level age, sex and ECOG against arm-level withdrawal, adjusted for the trial's burden and design (ecological)."""
    tf = {t["nct_id"]: t for t in trials}
    rows = [a for a in arms if a["nct_id"] in tf]
    if len(rows) < 50:
        return {"status": "TOO_FEW_ARMS"}
    X, names = _design([{**tf[a["nct_id"]], "n": a["n"]} for a in rows], levels)
    ref_age = float(np.median([a["age"] for a in rows]))
    extra, extra_names = [], ["age_per_10_years", "female_share", "ecog1_share", "ecog_not_reported"]
    for a in rows:
        e = a.get("ecog1")
        extra.append([(a["age"] - ref_age) / 10, (a["female"] if a.get("female") is not None else 0.5) - 0.5,
                      (e - 0.5) if e is not None else 0.0, 0.0 if e is not None else 1.0])
    Xm = np.hstack([X, np.array(extra)])
    f = _fit(Xm, np.array([a["k"] for a in rows], float), np.array([a["n"] for a in rows], float))
    se = np.sqrt(np.diag(f["cov"]))
    out = {}
    for i, nm in enumerate(extra_names[:3]):
        j = X.shape[1] + i
        b, s = float(f["beta"][j]), float(se[j])
        out[nm] = {"or": math.exp(b), "ci95": [math.exp(b - 1.96 * s), math.exp(b + 1.96 * s)], "log_odds": b, "se": s,
                   "unit": {"age_per_10_years": "per 10 years of arm mean age", "female_share": "all-female vs all-male arm",
                            "ecog1_share": "all ECOG >= 1 vs all ECOG 0 arm"}[nm]}
    return {"status": "RESOLVED", "arms": len(rows), "trials": len({a["nct_id"] for a in rows}), "effects": out,
            "basis": "arm-level baseline composition against arm-level withdrawal (ecological); not applied to patients"}


def load(path: Path | None = None) -> dict | None:
    p = Path(path or Path(assets.path("patient_risk")).parent / "withdrawal_burden") / "model.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def predict(model: dict, features: dict, draws: int = 0, rng=None) -> dict:
    """Predicted trial-level withdrawal share for a protocol's features (point, 95% CI, and parameter draws)."""
    X, _ = _design([features], model["levels"])
    x = X[0]
    b, cov = np.array(model["beta"]), np.array(model["cov"])
    eta, var = float(x @ b), float(x @ cov @ x)
    inv = lambda z: 1 / (1 + np.exp(-z))  # noqa: E731
    out = {"share": float(inv(eta)), "ci95": [float(inv(eta - 1.96 * math.sqrt(var))), float(inv(eta + 1.96 * math.sqrt(var)))]}
    if draws:
        out["draws"] = inv(rng.normal(eta, math.sqrt(var), draws)).tolist()
    return out


def protocol_features(spec: dict, sched: dict, family: str | None, phase: str | None, enrolled: int | None, start_year: int | None,
                      industry: bool | None, randomized: bool, reporting_window_days: int) -> dict:
    """The same burden features read from a protocol, mirroring what a registry record holds:
    participation   the planned treatment period (cycles x cycle length) plus the adverse-event reporting window
    visit frequency the most frequent stated ASSESSMENT interval (tumour assessment, follow-up): registry outcome
                    measures state assessment schedules ('assessed every 6 weeks'), not dosing
    assessments     the endpoints of the protocol's objectives-and-endpoints list (the endpoint group from the earliest
                    protocol section; the same endpoints restated in the statistical sections are not counted again):
                    the registry's outcome measures register that list"""
    cyc, max_c = (sched.get("cycle_length_days") or {}).get("value"), (sched.get("max_cycles") or {}).get("value")
    dur_days = (cyc * max_c + reporting_window_days) if cyc and max_c else None
    intervals = [v / 7 for v in ((sched.get(k) or {}).get("value") for k in ("tumour_assessment_interval_days", "follow_up_interval_days")) if v]

    def first_section(e):
        secs = e.get("sections") or ["999"]
        return min(tuple(int(x) for x in re.findall(r"\d+", s)) or (999,) for s in secs)
    eps = spec.get("endpoints") or []
    first = min((first_section(e) for e in eps), default=None)
    listed = [e for e in eps if first_section(e) == first] if first else eps
    name = lambda e: re.sub(r"[^a-z0-9]", "", ((e.get("name") or {}).get("text") if isinstance(e.get("name"), dict) else e.get("name") or "").lower())  # noqa: E731
    return {"duration_months": dur_days * 12 / 365.25 if dur_days else None, "interval_weeks": min(intervals) if intervals else None,
            "outcome_measures": len({name(e) for e in listed} - {""}), "phase": phase or "NA", "family": family or "other", "n": enrolled or 100,
            "start_year": start_year, "industry": bool(industry), "randomized": randomized,
            "definitions": {"duration": "planned treatment period plus the adverse-event reporting window",
                            "interval": "most frequent stated assessment interval (tumour assessment, follow-up)",
                            "outcome_measures": "endpoints of the objectives-and-endpoints list (earliest protocol section)"}}
