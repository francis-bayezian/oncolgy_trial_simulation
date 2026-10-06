"""Subgroup reporting: every analysis result by arm AND by subgroup (any protocol; no model calls).

Subgroup factors, in this order:
* protocol: the stratification factors and the subgroups the statistical analysis section names, resolved to a
  simulated patient variable by meaning (canonical factor, variable name, or the words of the subgroup); age subgroups
  use the protocol's own cut points; a factor with no patient variable is reported by the randomisation stratum when
  the stratum carries it (levels then assigned at random), else listed as not simulated;
* FDA demographics (Standard Safety Tables guide): age band (the paediatric bands of ICH E11 when the protocol enrols
  children), sex, race, ethnicity;
* baseline disease factors: every categorical baseline variable the population stage generated (performance status,
  stage, disease categories); anthropometrics and other continuous variables only when the protocol names them.

Per factor level and arm: n; best overall response, ORR and disease control rate with exact 95% CIs; time to response
and duration of response; PFS, OS and TTP Kaplan-Meier medians, 12-month landmarks, events and censored; any TEAE,
grade >= 3, SAE, AE leading to discontinuation / dose modification, deaths; disposition. Per level, each arm against
the control arm: the ORR difference (95% CI) and the PFS / OS hazard ratio (95% CI), drawn as forest plots.
Feasibility per level: screened, eligible share, the criteria that fail most, enrolled.

Every factor states what drives its differences:
* feasibility: "protocol criteria" when an eligibility criterion reads the factor's variable, else "patient mix";
* outcomes: "evidence-driven" when the outcome model applies an effect of the factor (outcome_model.json
  covariate_effects), else "mix only": the factor has no effect in the model, so its levels differ only by chance.
"""

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

SMALL_N = 10                       # below this a level's estimates are flagged as too small to read
MAX_LEVELS = 8
FDA_AGE = [(None, 65, "< 65 years"), (65, 75, "65-74 years"), (75, None, ">= 75 years")]
PAED_AGE = [(None, 2, "< 2 years"), (2, 12, "2-11 years"), (12, 18, "12-17 years"), (18, None, ">= 18 years")]  # ICH E11
STOP = {"the", "of", "and", "or", "vs", "versus", "at", "to", "in", "on", "for", "a", "an", "by", "with", "yes", "no", "each",
        "baseline", "study", "entry", "patients", "patient", "prior", "status", "categories", "category", "type", "group"}
DEMOGRAPHIC = {"demographic:age", "demographic:sex", "demographic:race", "demographic:ethnicity"}


def _q(x):
    return ((x or {}).get("text") if isinstance(x, dict) else x) or ""


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").casefold().replace("_", " ")) if w not in STOP and len(w) > 1}


def _value(v):
    """A baseline value as a category label (interval records as their bounds)."""
    if isinstance(v, dict):
        if "interval" in v:
            lo, hi = v["interval"]
            u = v.get("unit") or ""
            if lo is not None and hi is None:
                return f"{'>=' if v.get('lower_inclusive') else '>'} {lo:g} {u}".strip()
            if hi is not None and lo is None:
                return f"{'<=' if v.get('upper_inclusive') else '<'} {hi:g} {u}".strip()
            return f"{lo:g}-{hi:g} {u}".strip()
        v = v.get("value")
    return v


# ----------------------------------------------------------------------------- factors


def _age_bands(text: str, ages: list[float]) -> tuple[list, str]:
    """The protocol's own age cut points when its subgroup text states them, else the FDA (or ICH E11) bands."""
    cuts = sorted({float(x) for x in re.findall(r"(?<![\d.])(\d{1,3})(?![\d.])", text or "") if 1 <= float(x) <= 100})
    if text and cuts:
        edges = [None, *cuts, None]
        bands = []
        for lo, hi in zip(edges, edges[1:]):
            lab = f"< {hi:g} years" if lo is None else (f">= {lo:g} years" if hi is None else f"{lo:g}-<{hi:g} years")
            bands.append((lo, hi, lab))
        return bands, "protocol cut points"
    if ages and min(ages) < 18:
        return PAED_AGE, "ICH E11 paediatric bands"
    return FDA_AGE, "FDA standard age bands"


def _band(age, bands):
    for lo, hi, lab in bands:
        if (lo is None or age >= lo) and (hi is None or age < hi):
            return lab
    return None


def _ecog(v):
    try:
        x = int(float(v))
    except (TypeError, ValueError):
        return v
    return str(x) if x < 2 else "2 or more"


def factors(spec: dict, baselines: list[dict], strata_of: dict, cohort_records: list[dict] = ()) -> list[dict]:
    """The subgroup factors of this protocol, each with a function from a baseline record (and subject) to a level."""
    keys = Counter(k for b in baselines for k in b if k != "patient_id")
    ages = [float(_value(b.get("demographic:age")) or 0) for b in baselines if b.get("demographic:age")]
    elig_vars = {m for c in spec.get("eligibility") or [] for m in re.findall(r'"variable": "([^"]+)"', json.dumps(c))}
    names = variable_names(spec)
    values = {k: {w for b in baselines for w in _words(str(_value(b.get(k)) or ""))} for k in keys if k not in DEMOGRAPHIC}
    out, used = [], set()

    def add(name, source, variable, fn, note=""):
        out.append({"factor": name, "source": source, "variable": variable, "level": fn, "note": note,
                    "feasibility_driver": "protocol criteria" if variable in elig_vars or (variable == "demographic:age" and
                                                                                           "demographic:age" in elig_vars) else "patient mix"})
        used.add(variable)

    def resolve(text: str, canonical: str | None = None) -> str | None:
        if canonical and f"var:{canonical}" in keys:
            return f"var:{canonical}"
        w = _words(text) | _words(canonical or "")
        if w & {"age", "aged", "older", "elderly"}:
            return "demographic:age"
        if w & {"sex", "gender", "male", "female", "men", "women"}:
            return "demographic:sex"
        if w & {"race", "racial"}:
            return "demographic:race"
        if w & {"ethnicity", "ethnic", "hispanic"}:
            return "demographic:ethnicity"
        best, score = None, 0
        for k in keys:
            if k in DEMOGRAPHIC:
                continue
            s = len(w & (_words(k.split(":", 1)[-1]) | _words(names.get(k, "")))) or len(w & values.get(k, set()))
            if s > score:
                best, score = k, s
        return best

    # protocol: stratification factors and the analysis section's subgroups
    strat = spec.get("stratification") or {}
    named = [(_q(f), f.get("canonical_factor"), "protocol stratification factor") for f in strat.get("factors") or []]
    named += [(_q(s.get("subgroup")), None, "protocol subgroup (analysis section)") for s in spec.get("subgroups") or []]
    arm_words = {w for a in spec.get("arms") or [] for w in _words(_q(a.get("label")))}
    not_simulated = []
    for text, canon, source in named:
        if not text or any(o["note"] == text for o in out):
            continue
        var = resolve(text, canon)
        if var == "demographic:age":
            bands, how = _age_bands(text, ages)
            if var in used and how != "protocol cut points":
                continue
            add(f"Age ({how})", source, var, lambda b, s, bd=bands: _band(float(_value(b.get("demographic:age")) or 0), bd), text)
        elif var and var not in used:
            add(text, source, var, (lambda b, s, v=var: _ecog(_value(b.get(v))) if "ecog" in v else _value(b.get(v))), text)
        elif var in used:
            continue
        elif _words(text) and len(_words(text) & arm_words) >= max(1, len(_words(text)) // 2):
            continue                                  # the subgroup is the arm (cohort) itself: the arm columns report it
        elif any(len(_words(text) & _words(x["subgroup"])) / max(1, len(_words(text) | _words(x["subgroup"]))) >= 0.6 for x in not_simulated):
            continue                                  # the same factor named twice (stratification and analysis section)
        else:
            not_simulated.append({"subgroup": text, "source": source,
                                  "reason": "no simulated patient variable carries this factor (the population stage does not generate it)"})
    # the randomisation stratum, once (its levels are random when patient data could not decide them)
    if strata_of and any(s.get("stratum") for s in cohort_records):
        rnd = any("random" in (s.get("stratum_assigned") or "") for s in cohort_records)
        add("Randomisation stratum", "protocol stratification (stratum)", "stratum",
            lambda b, s: (strata_of.get(s.get("stratum")) or {}).get("label") or s.get("stratum"),
            "assigned at random: the stratification variables are not generated for patients" if rnd else "")
    # FDA demographics
    if "demographic:age" not in used:
        bands, how = _age_bands("", ages)
        add(f"Age ({how})", "FDA demographic", "demographic:age", lambda b, s, bd=bands: _band(float(_value(b.get("demographic:age")) or 0), bd))
    for var, name in (("demographic:sex", "Sex"), ("demographic:race", "Race"), ("demographic:ethnicity", "Ethnicity")):
        if var not in used:
            add(name, "FDA demographic", var, lambda b, s, v=var: _value(b.get(v)))
    out.append({"factor": "Region", "source": "FDA demographic", "variable": None, "level": None,
                "note": "not simulated: the recruitment model has no site country", "feasibility_driver": None})
    # baseline disease factors: categorical baseline variables
    for k in sorted(keys):
        if k in used or k in DEMOGRAPHIC:
            continue
        vals = [_value(b.get(k)) for b in baselines if b.get(k) is not None]
        if not vals or any(isinstance(v, float) and not v.is_integer() for v in vals):
            continue                                   # continuous (e.g. weight, height): not a subgroup unless named
        levels = {_ecog(v) if "ecog" in k else v for v in vals}
        if len(levels) < 2 and len(vals) == len(baselines):
            continue                                   # one level for everybody: no subgroup
        name = names.get(k) or k.split(":", 1)[-1].replace("_", " ")
        add(name[0].upper() + name[1:], "baseline disease factor", k,
            lambda b, s, v=k: (_ecog(_value(b.get(v))) if "ecog" in v else _value(b.get(v))) if b.get(v) is not None else "not recorded")
    return out + [{"factor": x["subgroup"], "source": x["source"], "variable": None, "level": None, "note": x["reason"],
                   "feasibility_driver": None} for x in not_simulated]


def variable_names(spec: dict) -> dict:
    """A readable name for each patient variable the protocol's rules read (the rule's subject or canonical name), so a
    coded variable (e.g. a UMLS concept) is reported by what the protocol calls it."""
    out = {}

    def walk(x):
        if isinstance(x, dict):
            v = x.get("variable")
            if isinstance(v, str) and v not in out:
                nm = x.get("subject") or (x.get("canonical") or "").replace("_", " ")
                if nm:
                    out[v] = " ".join(str(nm).split())[:60]
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(spec.get("eligibility"))
    walk(spec.get("stratification"))
    return out


def strata_labels(spec: dict) -> dict:
    out = {}
    for st in (spec.get("stratification") or {}).get("strata") or []:
        leaves = re.findall(r'"text": "([^"]+)"', json.dumps((st.get("logic") or {}), ensure_ascii=False))
        lab = _q(st.get("label")) or "; ".join(dict.fromkeys(leaves))
        out[st.get("stratum_id")] = {"label": " ".join(lab.split())[:80] or st.get("stratum_id"),
                                     "factor_words": _words(" ".join(leaves) + " " + lab)}
    return out


# ----------------------------------------------------------------------------- estimates


def _rate(x, n):
    from .analysis_results import exact_ci

    lo, hi = exact_ci(x, n)
    return {"n": x, "rate": round(x / n, 4) if n else None, "ci95_exact": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)]}


def _diff(x1, n1, x0, n0):
    if not n1 or not n0:
        return None
    p1, p0 = x1 / n1, x0 / n0
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    return {"difference": round(p1 - p0, 4), "ci95": [round(p1 - p0 - 1.96 * se, 4), round(p1 - p0 + 1.96 * se, 4)]}


def _km(rows):
    from .analysis_results import km_summary

    if not rows:
        return None
    s = km_summary(np.array([x["AVAL"] for x in rows], float), np.array([int(x["CNSR"]) == 0 for x in rows]))
    return {"n": s["n"], "events": s["events"], "censored": s["n"] - s["events"], "median_months": s["median_months"],
            "median_ci95_months": s["median_ci95_months"], "landmark_12m_percent": s["landmark_percent"].get("12m")}


def censoring(adtte: list[dict]) -> dict:
    """Censoring summary per endpoint and arm: events, censored, and the reasons (PharmaSUG ADTTE EVNTDESC)."""
    out = defaultdict(dict)
    for (code, arm), rows in _group(adtte, lambda x: (x["PARAMCD"], x["ARMCD"])).items():
        out[code][arm] = {"n": len(rows), "events": sum(int(x["CNSR"]) == 0 for x in rows),
                          "censored": sum(int(x["CNSR"]) == 1 for x in rows),
                          "by_reason": dict(Counter(x["EVNTDESC"] for x in rows))}
    return dict(out)


def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


def report(spec: dict, adsl: list[dict], adae: list[dict], adrs: list[dict], adtte: list[dict], arms: list[str], control: str | None,
           cohort: list[dict], population: list[dict], eligibility: list[dict], covariate_effects: dict | None = None,
           prevalence: dict | None = None) -> dict:
    """Subgroup results of one simulated trial (the analysis stage's datasets). `prevalence`: {variable: source} of the
    factors the population stage generated."""
    from .analysis_results import hazard_ratio

    covariate_effects, prevalence = covariate_effects or {}, prevalence or {}
    base_of = {c["subject_id"]: c for c in cohort}
    strata = strata_labels(spec)
    fs = factors(spec, [c["baseline"] for c in cohort] or population, strata, cohort)
    sid = lambda u: u.split("-P")[0]  # noqa: E731  (escalation periods share the subject's baseline)
    level_of = {}
    for f in fs:
        if f["level"] is None:
            continue
        for r in adsl:
            c = base_of.get(r["USUBJID"]) or base_of.get(sid(r["USUBJID"]))
            if c:
                lv = f["level"](c["baseline"], c)
                level_of[(f["factor"], r["USUBJID"])] = "not recorded" if lv is None else str(lv)
    bor = {x["USUBJID"]: x["AVALC"] for x in adrs if x["PARAMCD"] in ("BOR", "CBOR")}
    tte = _group(adtte, lambda x: (x["PARAMCD"], x["USUBJID"]))
    teae = [x for x in adae if x.get("TRTEMFL", "Y") == "Y"]
    ae_by = _group(teae, lambda x: x["USUBJID"])
    act = lambda x, *w: any(k in (x.get("AEACN") or "").casefold() for k in w)  # noqa: E731
    rows, comps, factors_out = [], [], []
    for f in fs:
        entry = {k: f[k] for k in ("factor", "source", "variable", "note", "feasibility_driver")}
        entry["prevalence_source"] = prevalence.get(f["variable"])
        if f["level"] is None:
            entry["outcome_driver"] = None
            factors_out.append(entry)
            continue
        eff = covariate_effects.get(f["variable"])
        entry["outcome_driver"] = (f"evidence-driven ({eff.get('source')})" if eff else
                                   "mix only: the outcome model applies no effect of this factor, so its levels differ only by chance")
        levels = Counter(level_of[(f["factor"], r["USUBJID"])] for r in adsl if (f["factor"], r["USUBJID"]) in level_of)
        if len(levels) > MAX_LEVELS:                      # keep the largest levels; the rest pooled
            keep = {lv for lv, _ in levels.most_common(MAX_LEVELS - 1)}
            for key in [k for k in level_of if k[0] == f["factor"] and level_of[k] not in keep]:
                level_of[key] = "other"
            levels = Counter(level_of[(f["factor"], r["USUBJID"])] for r in adsl if (f["factor"], r["USUBJID"]) in level_of)
        entry["levels"] = dict(levels)
        factors_out.append(entry)
        for lv in sorted(levels, key=lambda v: (v == "not recorded", str(v))):
            subj = {a: [r for r in adsl if r["ARMCD"] == a and level_of.get((f["factor"], r["USUBJID"])) == lv] for a in arms}
            per_arm = {}
            for a in arms:
                ids = [r["USUBJID"] for r in subj[a]]
                evaluable = [bor[i] for i in ids if i in bor]
                n_e = len(evaluable)
                resp = sum(b in ("CR", "PR") for b in evaluable)
                dc = sum(b in ("CR", "PR", "SD", "NON-CR/NON-PD") for b in evaluable)
                aes = [x for i in ids for x in ae_by.get(i, [])]
                pts = lambda sel: len({x["USUBJID"] for x in aes if sel(x)})  # noqa: E731
                d = {"n": len(ids), "small_n": len(ids) < SMALL_N, "efficacy_evaluable": n_e,
                     "best_overall_response": dict(Counter(evaluable)), "objective_response": _rate(resp, n_e) if n_e else None,
                     "disease_control": _rate(dc, n_e) if n_e else None}
                for code in ("PFS", "OS", "TTP", "DOR", "TTR"):
                    d[code] = _km([x for i in ids for x in tte.get((code, i), [])])
                d["safety"] = {"any_teae": pts(lambda x: True), "grade_3_plus": pts(lambda x: int(x.get("AETOXGR") or 0) >= 3),
                               "sae": pts(lambda x: x.get("AESER") == "Y"), "ae_leading_to_discontinuation": pts(lambda x: act(x, "discontinue")),
                               "ae_leading_to_dose_modification": pts(lambda x: act(x, "reduce", "hold", "delay", "interrupt")),
                               "deaths": sum(r.get("DTHFL") == "Y" for r in subj[a])}
                d["disposition"] = dict(Counter(r["EOTREAS"] for r in subj[a]))
                per_arm[a] = d
                rows.append({"factor": f["factor"], "level": lv, "arm": a, **d})
            if control in per_arm:
                c0 = per_arm[control]
                for a in arms:
                    if a == control:
                        continue
                    c1 = per_arm[a]
                    comp = {"factor": f["factor"], "level": lv, "arm": a, "control": control, "n": c1["n"], "n_control": c0["n"]}
                    if c1["objective_response"] and c0["objective_response"]:
                        comp["orr_difference"] = _diff(c1["objective_response"]["n"], c1["efficacy_evaluable"],
                                                       c0["objective_response"]["n"], c0["efficacy_evaluable"])
                    for code in ("PFS", "OS"):
                        g1 = [x for r in subj[a] for x in tte.get((code, r["USUBJID"]), [])]
                        g0 = [x for r in subj[control] for x in tte.get((code, r["USUBJID"]), [])]
                        if g1 and g0 and any(int(x["CNSR"]) == 0 for x in g1 + g0):
                            hr = hazard_ratio(np.array([x["AVAL"] for x in g1], float), np.array([int(x["CNSR"]) == 0 for x in g1]),
                                              np.array([x["AVAL"] for x in g0], float), np.array([int(x["CNSR"]) == 0 for x in g0]))
                            if hr.get("hr"):
                                comp[f"{code}_hazard_ratio"] = {"hr": hr["hr"], "ci95": hr["ci95"]}
                    comps.append(comp)
    return {"factors": factors_out, "rows": rows, "comparisons": comps,
            "feasibility": feasibility(spec, fs, population, eligibility, cohort)}


def feasibility(spec: dict, fs: list[dict], population: list[dict], eligibility: list[dict], cohort: list[dict]) -> list[dict]:
    """Per factor level of the screened population: screened, eligible share, the most frequent failing criteria,
    enrolled: which patients the criteria exclude."""
    base = {p["patient_id"]: p for p in population}
    label = {c.get("criterion_id"): " ".join((_q(c.get("label")) or _q(c.get("evidence")))[:70].split()) for c in spec.get("eligibility") or []}
    enrolled = Counter()
    out = []
    for f in fs:
        if f["level"] is None or f["variable"] == "stratum":
            continue
        enrolled = Counter(str(f["level"](c["baseline"], c)) for c in cohort)
        by = defaultdict(list)
        for e in eligibility:
            b = base.get(e["patient_id"])
            if b is not None:
                lv = f["level"](b, {})
                by["not recorded" if lv is None else str(lv)].append(e)
        for lv in sorted(by, key=lambda v: (v == "not recorded", str(v)))[:MAX_LEVELS + 1]:
            es = by[lv]
            elig = sum(e["status"] == "ELIGIBLE" for e in es)
            fails = Counter(c for e in es for c in e.get("failed") or [])
            out.append({"factor": f["factor"], "level": lv, "screened": len(es), "eligible": elig,
                        "eligible_share": round(elig / len(es), 4) if es else None, "enrolled": enrolled.get(lv, 0),
                        "driver": f["feasibility_driver"],
                        "top_failing_criteria": [{"criterion": c, "text": label.get(c, ""), "share_of_screened": round(k / len(es), 4)}
                                                 for c, k in fails.most_common(3)]})
    return out


def screen_fail_reasons(spec: dict, eligibility: list[dict]) -> list[list]:
    """Screen failures by criterion (a patient can fail several), with the criterion text."""
    label = {c.get("criterion_id"): " ".join((_q(c.get("label")) or _q(c.get("evidence")))[:90].split()) for c in spec.get("eligibility") or []}
    n = len(eligibility)
    fails = Counter(c for e in eligibility for c in e.get("failed") or [])
    only = Counter(e["failed"][0] for e in eligibility if len(e.get("failed") or []) == 1)
    t = [["Criterion", "Text", "Patients failing, n (% of screened)", "Failing this criterion only, n"]]
    for c, k in fails.most_common():
        t.append([c, label.get(c, ""), f"{k} ({100 * k / n:.1f})", str(only.get(c, 0))])
    return t


# ----------------------------------------------------------------------------- tables, forest plots, markdown


def _fmt_rate(r):
    if not r or r.get("rate") is None:
        return "-"
    lo, hi = r["ci95_exact"]
    return f"{100 * r['rate']:.0f}% ({100 * lo:.0f}-{100 * hi:.0f})"


def _fmt_km(k):
    if not k:
        return "-"
    m = k["median_months"]
    return f"{'NR' if m is None else m} ({k['events']}/{k['n']} ev)"


def write(doc: dict, out: Path, arms: list[str]) -> dict:
    """CSV tables and SVG forest plots; returns {name: relative path}."""
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    eff = [["Factor", "Level", "Arm", "N enrolled", "N efficacy-evaluable at cut-off", "Small n", "ORR % (95% CI)", "DCR % (95% CI)", "CR/PR/SD/PD/NE", "TTR median mo", "DOR median mo",
            "PFS median mo (events/n)", "PFS 12 m %", "OS median mo (events/n)", "OS 12 m %"]]
    saf = [["Factor", "Level", "Arm", "N", "Any TEAE", "Grade >= 3", "SAE", "AE -> discontinuation", "AE -> dose modification", "Deaths",
            "Disposition"]]
    for r in doc["rows"]:
        b = r["best_overall_response"]
        eff.append([r["factor"], r["level"], r["arm"], r["n"], r["efficacy_evaluable"], "yes" if r["efficacy_evaluable"] < SMALL_N else "",
                    _fmt_rate(r["objective_response"]),
                    _fmt_rate(r["disease_control"]), "/".join(str(b.get(k, 0)) for k in ("CR", "PR", "SD", "PD", "NE")) if b else "-",
                    (r["TTR"] or {}).get("median_months") or "-", (r["DOR"] or {}).get("median_months") or "-", _fmt_km(r["PFS"]),
                    (r["PFS"] or {}).get("landmark_12m_percent") or "-", _fmt_km(r["OS"]), (r["OS"] or {}).get("landmark_12m_percent") or "-"])
        s = r["safety"]
        pct = lambda x, n=r["n"]: f"{x} ({100 * x / n:.0f}%)" if n else "0"  # noqa: E731
        saf.append([r["factor"], r["level"], r["arm"], r["n"], pct(s["any_teae"]), pct(s["grade_3_plus"]), pct(s["sae"]),
                    pct(s["ae_leading_to_discontinuation"]), pct(s["ae_leading_to_dose_modification"]), pct(s["deaths"]),
                    "; ".join(f"{k}: {v}" for k, v in sorted(r["disposition"].items(), key=lambda kv: -kv[1])[:3])])
    cmp_ = [["Factor", "Level", "Arm vs control", "N / N control", "ORR difference % (95% CI)", "PFS HR (95% CI)", "OS HR (95% CI)"]]
    for c in doc["comparisons"]:
        d = c.get("orr_difference")
        h = lambda k: (f"{c[k]['hr']} ({c[k]['ci95'][0]}-{c[k]['ci95'][1]})" if c.get(k) else "-")  # noqa: E731
        cmp_.append([c["factor"], c["level"], f"{c['arm']} vs {c['control']}", f"{c['n']} / {c['n_control']}",
                     f"{100 * d['difference']:.1f} ({100 * d['ci95'][0]:.1f}, {100 * d['ci95'][1]:.1f})" if d else "-",
                     h("PFS_hazard_ratio"), h("OS_hazard_ratio")])
    fea = [["Factor", "Level", "Screened", "Eligible (%)", "Enrolled", "Most frequent failing criteria (% of screened)", "Driver"]]
    for r in doc["feasibility"]:
        fea.append([r["factor"], r["level"], r["screened"], f"{r['eligible']} ({100 * (r['eligible_share'] or 0):.0f}%)", r["enrolled"],
                    "; ".join(f"{c['criterion']} {c['text'][:40]} ({100 * c['share_of_screened']:.0f}%)" for c in r["top_failing_criteria"]),
                    r["driver"]])
    for name, t in (("subgroup_efficacy", eff), ("subgroup_safety", saf), ("subgroup_comparisons", cmp_), ("subgroup_feasibility", fea)):
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(t)
        files[name] = f"subgroups/{name}.csv"
    for key, title, log in (("PFS_hazard_ratio", "PFS hazard ratio", True), ("OS_hazard_ratio", "OS hazard ratio", True),
                            ("orr_difference", "ORR difference", False)):
        for a in sorted({c["arm"] for c in doc["comparisons"]}):
            pts = [c for c in doc["comparisons"] if c["arm"] == a and c.get(key)]
            if pts:
                name = f"forest_{key.split('_')[0].lower()}_{a}"
                (out / f"{name}.svg").write_text(forest(pts, key, f"{title}: {a} vs {pts[0]['control']}", log), encoding="utf-8")
                files[name] = f"subgroups/{name}.svg"
    return files


def forest(pts: list[dict], key: str, title: str, log: bool) -> str:
    """A forest plot (SVG): one row per factor level, point estimate and 95% CI, line of no effect."""
    vals = []
    for c in pts:
        v = c[key]
        est, lo, hi = (v["hr"], *v["ci95"]) if log else (v["difference"], *v["ci95"])
        vals.append((c["factor"], c["level"], c["n"] + c["n_control"], est, lo, hi))
    tf = (lambda x: math.log(max(x, 1e-3))) if log else (lambda x: x)
    xs = [tf(x) for v in vals for x in v[3:] if x is not None]
    lo_x, hi_x = min(xs + [tf(1.0 if log else 0.0)]), max(xs + [tf(1.0 if log else 0.0)])
    pad = (hi_x - lo_x) * 0.05 or 0.1
    lo_x, hi_x = lo_x - pad, hi_x + pad
    W, left, plot, rowh = 900, 380, 420, 20
    H = 60 + rowh * len(vals) + 40
    sx = lambda x: left + (tf(x) - lo_x) / (hi_x - lo_x) * plot  # noqa: E731
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="white"/>', f'<text x="10" y="20" font-size="14" font-weight="bold">{esc(title)}</text>',
         f'<text x="10" y="44" fill="#555">Subgroup (n)</text>', f'<text x="{left + plot + 10}" y="44" fill="#555">Estimate (95% CI)</text>']
    null = sx(1.0 if log else 0.0)
    s.append(f'<line x1="{null:.1f}" y1="50" x2="{null:.1f}" y2="{H - 30}" stroke="#999" stroke-dasharray="4,3"/>')
    last = None
    for i, (fac, lv, n, est, lo, hi) in enumerate(vals):
        y = 62 + i * rowh
        lab = (f"{fac[:34]}: " if fac != last else "    ") + f"{lv} ({n})"
        last = fac
        s.append(f'<text x="10" y="{y + 4}">{esc(lab[:58])}</text>')
        s.append(f'<line x1="{sx(lo):.1f}" y1="{y}" x2="{sx(hi):.1f}" y2="{y}" stroke="#1f4e79" stroke-width="1.5"/>')
        s.append(f'<rect x="{sx(est) - 4:.1f}" y="{y - 4}" width="8" height="8" fill="#1f4e79"/>')
        fmt = (lambda x: f"{x:.2f}") if log else (lambda x: f"{100 * x:.0f}%")
        s.append(f'<text x="{left + plot + 10}" y="{y + 4}">{fmt(est)} ({fmt(lo)}, {fmt(hi)})</text>')
    s.append(f'<text x="{null:.1f}" y="{H - 12}" text-anchor="middle" fill="#555">'
             f'{"favours arm <- 1 -> favours control" if log else "favours control <- 0 -> favours arm"}</text></svg>')
    return "\n".join(s)


def render(doc: dict, files: dict) -> list[str]:
    L = ["## Results by subgroup", "",
         "Every result by arm and by subgroup. 'Outcome driver' says whether the simulation gives the factor an effect on "
         "outcomes; 'mix only' means its levels differ only by chance and the size of the subgroup, so read those rows as the "
         f"precision a real trial of this size would have, not as a subgroup effect. Levels with fewer than {SMALL_N} patients "
         "are flagged.", "", "| Factor | Source | Levels (n) | Generated from | Feasibility driver | Outcome driver |",
         "| --- | --- | --- | --- | --- | --- |"]
    for f in doc["factors"]:
        lv = "; ".join(f"{k} ({v})" for k, v in (f.get("levels") or {}).items()) or f"not reported: {f['note']}"
        L.append(f"| {f['factor']} | {f['source']} | {lv} | {f.get('prevalence_source') or '-'} | {f['feasibility_driver'] or '-'} | "
                 f"{f['outcome_driver'] or '-'} |")
    L += ["", "### Efficacy by subgroup and arm", "",
          "N = enrolled (safety population); E = efficacy-evaluable, enrolled by the data cut-off; * fewer than "
          f"{SMALL_N} evaluable.", "",
          "| Factor | Level | Arm | N / E | ORR % (95% CI) | DCR % (95% CI) | PFS median mo (ev/n) | OS median mo (ev/n) | DOR mo |",
          "| --- | --- | --- | ---: | --- | --- | --- | --- | --- |"]
    for r in doc["rows"]:
        L.append(f"| {r['factor']} | {r['level']} | {r['arm']} | {r['n']} / {r['efficacy_evaluable']}{' *' if r['efficacy_evaluable'] < SMALL_N else ''} | "
                 f"{_fmt_rate(r['objective_response'])} | "
                 f"{_fmt_rate(r['disease_control'])} | {_fmt_km(r['PFS'])} | {_fmt_km(r['OS'])} | {(r['DOR'] or {}).get('median_months') or '-'} |")
    if doc["comparisons"]:
        L += ["", "### Arm vs control within each subgroup", "", "| Factor | Level | Comparison | N / N control | ORR difference % (95% CI) | PFS HR (95% CI) | OS HR (95% CI) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for c in doc["comparisons"]:
            d = c.get("orr_difference")
            h = lambda k: (f"{c[k]['hr']} ({c[k]['ci95'][0]}-{c[k]['ci95'][1]})" if c.get(k) else "-")  # noqa: E731
            diff = f"{100 * d['difference']:.1f} ({100 * d['ci95'][0]:.1f}, {100 * d['ci95'][1]:.1f})" if d else "-"
            L.append(f"| {c['factor']} | {c['level']} | {c['arm']} vs {c['control']} | {c['n']} / {c['n_control']} | {diff} | "
                     f"{h('PFS_hazard_ratio')} | {h('OS_hazard_ratio')} |")
        forests = [v for k, v in files.items() if k.startswith("forest_")]
        if forests:
            L += ["", "Forest plots: " + ", ".join(f"[{Path(v).stem}]({v})" for v in forests) + "."]
    L += ["", "### Safety by subgroup and arm", "", "| Factor | Level | Arm | N | Any TEAE | Grade >= 3 | SAE | AE -> discontinuation | AE -> dose modification | Deaths |",
          "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in doc["rows"]:
        s = r["safety"]
        L.append(f"| {r['factor']} | {r['level']} | {r['arm']} | {r['n']} | {s['any_teae']} | {s['grade_3_plus']} | {s['sae']} | "
                 f"{s['ae_leading_to_discontinuation']} | {s['ae_leading_to_dose_modification']} | {s['deaths']} |")
    L += ["", "### Screening by subgroup (which patients the criteria exclude)", "", "| Factor | Level | Screened | Eligible % | Enrolled | Most frequent failing criteria | Driver |",
          "| --- | --- | ---: | ---: | ---: | --- | --- |"]
    for r in doc["feasibility"]:
        L.append(f"| {r['factor']} | {r['level']} | {r['screened']} | {100 * (r['eligible_share'] or 0):.0f}% | {r['enrolled']} | "
                 + "; ".join(f"{c['criterion']} ({100 * c['share_of_screened']:.0f}%)" for c in r["top_failing_criteria"]) + f" | {r['driver']} |")
    return L + [""]
