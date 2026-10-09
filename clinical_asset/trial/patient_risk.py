"""Patient-level risk from the evidence: who gets an event depends on the patient's characteristics (L055).

Across the 5,000 registry trials of the evidence corpus, each arm reports its participants' median age, the share
female and the share with ECOG performance status 1 or more, and how many of them had a serious adverse event, any
other adverse event, or died; the participant flow reports who stopped for an adverse event or withdrew. A binomial
regression over the arms (with phase, disease family and drug classes as controls) gives how each outcome's odds move
with those characteristics. A second regression gives how the share with ECOG >= 1 moves with age, so generated
patients' performance status follows their age.

These slopes are trial-level (tier-3) evidence. The effects applied to patients come from the evidence synthesis
(evidence_synthesis, L056), which weighs them against patient-level evidence for the same estimand, so each effect
is a distribution whose width reflects its evidence; a replicate uses one draw.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from .. import assets

OUTCOMES = ("serious_ae", "other_ae", "death", "ae_discontinuation", "withdrawal")
CHARACTERISTICS = ("age10", "female", "ecog1", "asian", "black")   # per 10 years of age; female, ECOG >= 1, race (0/1)
MIXED_SEX = (0.05, 0.95)        # the sex effect is estimated from arms with both sexes (single-sex trials are other cancers)
MAX_SHIFT = 2.0                                     # a patient's log-odds shift is bounded (extrapolation guard)
WITHDRAWAL_TYPES = re.compile(r"withdraw|lost to follow|physician decision|consent", re.I)
AE_TYPES = re.compile(r"adverse|toxicit", re.I)


def model_dir() -> Path:
    return assets.path("patient_risk")


# ----------------------------------------------------------------------------- registry reading


def _key(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def baseline_by_group(results: dict) -> dict[str, dict]:
    """Median (or mean) age, share female and share with ECOG >= 1 for each baseline group, by normalised title;
    the 'total' entry holds the whole trial."""
    bl = results.get("baselineCharacteristicsModule") or {}
    titles = {g["id"]: g.get("title") or "" for g in bl.get("groups") or []}
    out: dict[str, dict] = {}

    def put(gid, k, v):
        if v is None:
            return
        name = "total" if re.fullmatch(r"\s*total\s*", titles.get(gid, ""), re.I) else _key(titles.get(gid))
        out.setdefault(name, {})[k] = v

    for m in bl.get("measures") or []:
        title = m.get("title") or ""
        cats = [(c.get("title") or "", meas) for cl in m.get("classes") or [] for c in cl.get("categories") or []
                for meas in [c.get("measurements") or []]]
        if re.match(r"^\s*age\b", title, re.I) and (m.get("paramType") in ("MEAN", "MEDIAN")) and re.search(r"year", m.get("unitOfMeasure") or "", re.I):
            for _, meas in cats:
                for x in meas:
                    put(x.get("groupId"), "age", _num(x.get("value")))
        elif re.search(r"\bsex\b|gender", title, re.I) and m.get("paramType") in ("COUNT_OF_PARTICIPANTS", "NUMBER"):
            per: dict[str, dict] = {}
            for name, meas in cats:
                for x in meas:
                    per.setdefault(x.get("groupId"), {})[name.casefold()] = _num(x.get("value")) or 0.0
            for gid, d in per.items():
                f = sum(v for k, v in d.items() if k.startswith("female") or k == "women")
                tot = sum(d.values())
                if tot > 0:
                    put(gid, "female", f / tot)
        elif re.search(r"\brace\b", title, re.I) and not re.search(r"ethnic", title, re.I) and m.get("paramType") in ("COUNT_OF_PARTICIPANTS", "NUMBER"):
            per = {}
            for name, meas in cats:
                for x in meas:
                    per.setdefault(x.get("groupId"), {})[name.casefold()] = _num(x.get("value")) or 0.0
            for gid, d in per.items():
                known = sum(v for k, v in d.items() if k and not re.search(r"unknown|not reported|missing", k))
                if known > 0:
                    put(gid, "asian", sum(v for k, v in d.items() if k.startswith("asian")) / known)
                    put(gid, "black", sum(v for k, v in d.items() if k.startswith("black")) / known)
        elif re.search(r"ecog|eastern cooperative", title, re.I) and m.get("paramType") in ("COUNT_OF_PARTICIPANTS", "NUMBER"):
            per = {}
            ok = True
            for name, meas in cats:
                levels = [int(d) for d in re.findall(r"(?<![\d.])([0-4])(?![\d.])", name)]
                if not levels or re.search(r"missing|unknown|not", name, re.I):
                    continue
                if min(levels) == 0 and max(levels) >= 1:        # '0-1': cannot split 0 from >= 1
                    ok = False
                for x in meas:
                    d = per.setdefault(x.get("groupId"), [0.0, 0.0])
                    d[0 if max(levels) == 0 else 1] += _num(x.get("value")) or 0.0
            if ok:
                for gid, (zero, more) in per.items():
                    if zero + more > 0:
                        put(gid, "ecog1", more / (zero + more))
    return out


def arm_records(trial: dict) -> list[dict]:
    """One record per adverse-event group: its characteristics (own group, else the trial total) and its counts."""
    ps, rs = trial.get("protocolSection") or {}, trial.get("resultsSection") or {}
    base = baseline_by_group(rs)
    total = base.get("total", {})
    phase = "/".join(sorted((ps.get("designModule") or {}).get("phases") or [])) or "NA"
    out = []
    for g in (rs.get("adverseEventsModule") or {}).get("eventGroups") or []:
        own = base.get(_key(g.get("title")), {})
        chars = {k: own.get(k, total.get(k)) for k in ("age", "female", "ecog1", "asian", "black")}
        if chars["age"] is None:
            continue
        rec = {"nct_id": ps.get("identificationModule", {}).get("nctId"), "group": g.get("title"), "phase": phase, **chars}
        for outcome, a, n in (("serious_ae", "seriousNumAffected", "seriousNumAtRisk"), ("other_ae", "otherNumAffected", "otherNumAtRisk"),
                              ("death", "deathsNumAffected", "deathsNumAtRisk")):
            if g.get(n):
                rec[outcome] = (int(g.get(a) or 0), int(g[n]))
        out.append(rec)
    return out


def trial_exit_record(trial: dict) -> dict | None:
    """Trial-level exits from the participant flow: stopped for an adverse event, withdrew (subject, lost, physician)."""
    ps, rs = trial.get("protocolSection") or {}, trial.get("resultsSection") or {}
    pf = rs.get("participantFlowModule") or {}
    periods = pf.get("periods") or []
    if not periods:
        return None
    started = sum(_num(a.get("numSubjects")) or 0 for m in periods[0].get("milestones") or [] if (m.get("type") or "").upper() == "STARTED"
                  for a in m.get("achievements") or [])
    if started <= 0:
        return None
    ae = wd = 0.0
    for p in periods:
        for d in p.get("dropWithdraws") or []:
            n = sum(_num(r.get("numSubjects")) or 0 for r in d.get("reasons") or [])
            if AE_TYPES.search(d.get("type") or ""):
                ae += n
            elif WITHDRAWAL_TYPES.search(d.get("type") or ""):
                wd += n
    total = baseline_by_group(rs).get("total", {})
    if total.get("age") is None:
        return None
    phase = "/".join(sorted((ps.get("designModule") or {}).get("phases") or [])) or "NA"
    return {"nct_id": ps.get("identificationModule", {}).get("nctId"), "phase": phase,
            **{k: total.get(k) for k in ("age", "female", "ecog1", "asian", "black")},
            "ae_discontinuation": (int(min(ae, started)), int(started)), "withdrawal": (int(min(wd, started)), int(started))}


# ----------------------------------------------------------------------------- regression


def fit_logistic(X: np.ndarray, k: np.ndarray, n: np.ndarray, ridge: float = 1.0, iters: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Binomial logistic regression (events k of n per row) by iteratively reweighted least squares, with a small ridge
    on every coefficient but the intercept; returns coefficients and their standard errors."""
    beta = np.zeros(X.shape[1])
    p0 = np.clip(k.sum() / n.sum(), 1e-4, 1 - 1e-4)
    beta[0] = math.log(p0 / (1 - p0))
    pen = np.full(X.shape[1], ridge)
    pen[0] = 0.0
    for _ in range(iters):
        eta = X @ beta
        mu = 1 / (1 + np.exp(-eta))
        w = n * mu * (1 - mu)
        grad = X.T @ (k - n * mu) - pen * beta
        H = X.T @ (X * w[:, None]) + np.diag(pen)
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    eta = X @ beta
    mu = 1 / (1 + np.exp(-eta))
    H = X.T @ (X * (n * mu * (1 - mu))[:, None]) + np.diag(pen)
    se = np.sqrt(np.clip(np.diag(np.linalg.inv(H)), 0, None))
    return beta, se


def _design(recs: list[dict], ref: dict, controls: dict) -> tuple[np.ndarray, list[str]]:
    names = ["intercept", "age10", "female", "ecog1", "ecog1_missing", "asian", "black", "race_missing"] + [f"phase:{p}" for p in controls["phases"]] + \
        [f"family:{f}" for f in controls["families"]] + [f"class:{c}" for c in controls["classes"]]
    rows = []
    for r in recs:
        e = r.get("ecog1")
        x = [1.0, (r["age"] - ref["age"]) / 10, (r["female"] if r.get("female") is not None else ref["female"]) - ref["female"],
             (e - ref["ecog1"]) if e is not None else 0.0, 0.0 if e is not None else 1.0]
        race = r.get("asian") is not None and r.get("black") is not None
        x += [(r["asian"] - ref["asian"]) if race else 0.0, (r["black"] - ref["black"]) if race else 0.0, 0.0 if race else 1.0]
        x += [1.0 if r.get("phase") == p else 0.0 for p in controls["phases"]]
        x += [1.0 if r.get("family") == f else 0.0 for f in controls["families"]]
        x += [1.0 if c in (r.get("classes") or ()) else 0.0 for c in controls["classes"]]
        rows.append(x)
    return np.array(rows, dtype=float), names


def build(out_dir: Path | None = None, top_classes: int = 25) -> dict:
    """Read the corpus's registry records, fit every outcome and the ECOG-by-age model, write model.json."""
    import pyarrow.parquet as pq

    raw = assets.path("raw_ctgov")
    out_dir = Path(out_dir or model_dir())
    families, classes = {}, {}
    try:
        arms = pq.read_table(assets.path("safety") / "arms.parquet", columns=["nct_id", "group", "classes", "disease_family"]).to_pylist()
        for a in arms:
            families[a["nct_id"]] = a["disease_family"]
            classes[(a["nct_id"], _key(a["group"]))] = tuple(json.loads(a["classes"] or "[]"))
    except Exception:  # noqa: BLE001 - without the safety arm table the controls are phase only
        pass
    arm_recs, exit_recs = [], []
    files = sorted(Path(raw).glob("NCT*.json"))
    for f in files:
        t = json.loads(f.read_text(encoding="utf-8"))
        for r in arm_records(t):
            r["family"] = families.get(r["nct_id"])
            r["classes"] = classes.get((r["nct_id"], _key(r["group"])), ())
            arm_recs.append(r)
        e = trial_exit_record(t)
        if e:
            e["family"] = families.get(e["nct_id"])
            exit_recs.append(e)

    def mean(recs, k):
        v = [(r[k], (r.get("serious_ae") or r.get("withdrawal") or (0, 1))[1]) for r in recs if r.get(k) is not None]
        w = sum(n for _, n in v)
        return sum(x * n for x, n in v) / w if w else None

    ref = {k: mean(arm_recs, k) for k in ("age", "female", "ecog1", "asian", "black")}
    controls = {"phases": [p for p, _ in Counter(r["phase"] for r in arm_recs).most_common() if p != "PHASE2"][:6],
                "families": [f for f, n in Counter(r["family"] for r in arm_recs if r.get("family")).most_common() if n >= 30][:20],
                "classes": [c for c, _ in Counter(c for r in arm_recs for c in r.get("classes") or ()).most_common(top_classes)]}
    model: dict = {"model": "patient-risk-1.0.0", "source": f"{len(files)} registry trials ({raw})", "reference": ref, "controls": controls,
                   "kind": "trial-level (ecological) association applied to individual patients", "outcomes": {}}
    for outcome in OUTCOMES:
        recs = [r for r in (exit_recs if outcome in ("ae_discontinuation", "withdrawal") else arm_recs) if r.get(outcome)]
        if len(recs) < 50:
            model["outcomes"][outcome] = {"status": "NOT_ESTIMATED", "reason": f"only {len(recs)} records"}
            continue
        X, names = _design(recs, ref, controls)
        k = np.array([r[outcome][0] for r in recs], dtype=float)
        n = np.array([r[outcome][1] for r in recs], dtype=float)
        beta, se = fit_logistic(X, k, n)
        coef = {nm: {"estimate": round(float(b), 5), "se": round(float(s), 5)} for nm, b, s in zip(names, beta, se, strict=True)}
        # the sex effect from arms with both sexes only: in single-sex trials the share female stands for the cancer
        mixed = [r for r in recs if r.get("female") is not None and MIXED_SEX[0] < r["female"] < MIXED_SEX[1]]
        if len(mixed) >= 50:
            Xm, _ = _design(mixed, ref, controls)
            bm, sm = fit_logistic(Xm, np.array([r[outcome][0] for r in mixed], float), np.array([r[outcome][1] for r in mixed], float))
            i = names.index("female")
            coef["female"] = {"estimate": round(float(bm[i]), 5), "se": round(float(sm[i]), 5),
                              "from": f"{len(mixed)} mixed-sex records (share female {MIXED_SEX[0]}-{MIXED_SEX[1]})",
                              "all_records_estimate": coef["female"]["estimate"]}
        model["outcomes"][outcome] = {
            "status": "ESTIMATED", "records": len(recs), "trials": len({r["nct_id"] for r in recs}), "participants": int(n.sum()),
            "event_rate": round(float(k.sum() / n.sum()), 4),
            "patient_effects": {c: coef[c] for c in CHARACTERISTICS},
            "odds_ratio_per_unit": {c: round(math.exp(coef[c]["estimate"]), 3) for c in CHARACTERISTICS},
            "ecog_reported_in": sum(r.get("ecog1") is not None for r in recs), "coefficients": coef}
    # ECOG's effect is not applied (user decision 2026-10-08): the trial-level slope compares arms where everyone has
    # ECOG >= 1 with arms where no one does and absorbs disease stage and pretreatment (an odds ratio of 13 for death),
    # and the registry holds no within-trial results by ECOG to replace it (1 survival result by ECOG in 1,621).
    # The estimate is kept for the record; the effect used is zero.
    # the model keeps the regression's own (tier-3) estimates; the effects applied to patients come from the evidence
    # synthesis (evidence_synthesis, L056), which weighs them against patient-level evidence
    # ECOG >= 1 share by age (arms reporting both): generated patients' performance status follows their age
    eco = [r for r in arm_recs if r.get("ecog1") is not None and r.get("serious_ae")]
    if len(eco) >= 50:
        X = np.column_stack([np.ones(len(eco)), [(r["age"] - ref["age"]) / 10 for r in eco]])
        n = np.array([r["serious_ae"][1] for r in eco], dtype=float)
        k = np.round(np.array([r["ecog1"] for r in eco]) * n)
        beta, se = fit_logistic(X, k, n, ridge=0.0)
        model["ecog_by_age"] = {"status": "ESTIMATED", "arms": len(eco), "log_odds_per_10_years": round(float(beta[1]), 5),
                                "se": round(float(se[1]), 5), "odds_ratio_per_10_years": round(math.exp(beta[1]), 3)}
    else:
        model["ecog_by_age"] = {"status": "NOT_ESTIMATED", "reason": f"only {len(eco)} arms report ECOG with age"}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model.json").write_text(json.dumps(model, indent=1), encoding="utf-8")
    return {k: v for k, v in model.items() if k != "outcomes"} | {
        "outcomes": {o: {k: v for k, v in m.items() if k != "coefficients"} for o, m in model["outcomes"].items()}}


# ----------------------------------------------------------------------------- applying to patients


def load(seed: int | None = None) -> dict | None:
    """The patient-risk model with the effects a patient gets: one posterior draw of the evidence synthesis for a
    replicate's seed (a posterior of cohorts), the posterior means without a seed. Without a synthesis no effect is
    applied (every patient has the arm's evidence rate) and the model says so."""
    f = model_dir() / "model.json"
    if not f.exists():
        return None
    model = json.loads(f.read_text(encoding="utf-8"))
    from . import evidence_ledger as led
    from . import evidence_synthesis as syn_mod

    syn = syn_mod.load()
    values = syn_mod.draw(syn, seed) if syn else {}
    for outcome, m in (model.get("outcomes") or {}).items():
        if m.get("status") != "ESTIMATED":
            continue
        est = led.SIMULATED[outcome]
        for c in list(m["patient_effects"]):
            v = values.get((c, est))
            m["patient_effects"][c] = {"estimate": float(v) if v is not None else 0.0,
                                       "source": ("evidence synthesis " + ("draw for seed " + str(seed) if seed is not None else "posterior mean"))
                                       if v is not None else "no synthesis: not applied",
                                       "trial_level_estimate": m["patient_effects"][c]}
    model["effects_from"] = "evidence synthesis" if syn else "none (no synthesis built)"
    return model


def characteristics(baseline: dict) -> dict:
    """The patient's age (years), female (0/1) and ECOG >= 1 (0/1) from a generated baseline; None when not generated."""
    age = (baseline.get("demographic:age") or {}).get("value") if isinstance(baseline.get("demographic:age"), dict) else baseline.get("demographic:age")
    sex = baseline.get("demographic:sex")
    sex = sex.get("value") if isinstance(sex, dict) else sex
    ecog = baseline.get("var:ecog_performance_status")
    ecog = ecog.get("value") if isinstance(ecog, dict) else ecog
    race = baseline.get("demographic:race")
    race = race.get("value") if isinstance(race, dict) else race
    known_race = bool(race) and not re.search(r"unknown|not_reported|not reported", str(race), re.I)
    return {"age": float(age) if age is not None else None,
            "asian": (1.0 if str(race).casefold().startswith("asian") else 0.0) if known_race else None,
            "black": (1.0 if str(race).casefold().startswith("black") else 0.0) if known_race else None,
            "female": (1.0 if str(sex).casefold().startswith("f") else 0.0) if sex else None,
            "ecog1": (1.0 if float(ecog) >= 1 else 0.0) if ecog is not None else None}


def shift(model: dict | None, outcome: str, baseline: dict) -> float:
    """The patient's log-odds shift for an outcome from the corpus-average patient (0 without a model or an estimate)."""
    if not model or (model.get("outcomes", {}).get(outcome) or {}).get("status") != "ESTIMATED":
        return 0.0
    eff = model["outcomes"][outcome]["patient_effects"]
    ref = model["reference"]
    c = characteristics(baseline)
    s = 0.0
    if c["age"] is not None:
        s += eff["age10"]["estimate"] * (c["age"] - ref["age"]) / 10
    if c["female"] is not None and ref.get("female") is not None:
        s += eff["female"]["estimate"] * (c["female"] - ref["female"])
    if c["ecog1"] is not None and ref.get("ecog1") is not None:
        s += eff["ecog1"]["estimate"] * (c["ecog1"] - ref["ecog1"])
    for k in ("asian", "black"):
        if c.get(k) is not None and ref.get(k) is not None and k in eff:
            s += eff[k]["estimate"] * (c[k] - ref[k])
    return float(np.clip(s, -MAX_SHIFT, MAX_SHIFT))


def adjust(p: float, delta: float) -> float:
    """A probability moved by a log-odds shift."""
    if p is None or delta == 0.0 or p <= 0 or p >= 1:
        return p
    return 1 / (1 + math.exp(-(math.log(p / (1 - p)) + delta)))


def ecog_given_age(p_levels: list[float], age: float | None, mean_age: float | None, model: dict | None) -> list[float]:
    """ECOG level probabilities for one patient: the share with ECOG >= 1 moves with the patient's age relative to the
    population's mean age (so the population's overall ECOG distribution is kept), levels 1-4 keep their proportions."""
    p = np.array(p_levels, dtype=float)
    p = p / p.sum()
    eb = (model or {}).get("ecog_by_age") or {}
    if eb.get("status") != "ESTIMATED" or age is None or mean_age is None or not 0 < p[0] < 1:
        return list(p)
    above = adjust(1 - p[0], eb["log_odds_per_10_years"] * (age - mean_age) / 10)
    rest = p[1:] / p[1:].sum() if p[1:].sum() > 0 else np.full(len(p) - 1, 1 / (len(p) - 1))
    return [1 - above] + list(above * rest)
