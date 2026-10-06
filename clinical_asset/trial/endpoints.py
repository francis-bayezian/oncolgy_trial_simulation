"""Endpoint results of the simulated trial, for every endpoint of any protocol (lesson L027).

Reads the simulated patients of the journey stage (ADSL, ADTTE, ADAE) and, per arm, gives each endpoint a result
computed FROM THE SIMULATED PATIENTS, with the source of the input that generated it (clinical_asset.trial.quantify):

* time to event: each patient's time is drawn from the arm's ladder median (exponential, assumption A7), censored at the
  protocol's follow-up (else FOLLOW_UP_YEARS) and by the journey's loss to follow-up; progression-type endpoints use
  the journey's own detected progression when its progression model is resolved. Reported: events, Kaplan-Meier median
  with a 95% CI, and the input median and its rung.
* proportion: each started patient responds with the arm's ladder rate; reported: count / n with the exact 95% CI.
* safety: patients with any serious, any grade >= 3 adverse event, and treatment stopped for an adverse event.
* participant flow: end-of-treatment reasons and deaths from the journey.
* endpoints the generated patients cannot carry (patient-reported, pharmacokinetic, biomarker ...) are listed as
  NOT_SIMULATED with their kind: by design, not a failure.
"""

import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

from .predictive import from_draws, text
from .quantify import classify, quantify

ENDPOINTS_VERSION = "endpoints-1.0.0"
FOLLOW_UP_YEARS = 5.0
DAY = 365.25
REPLICATES = 200
PROGRESSION_VARIABLES = {"progression_free_survival", "time_to_progression", "event_free_survival"}


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def _rows(path: Path) -> list[dict]:
    if not path.exists() or not path.stat().st_size:
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def km_median(t: np.ndarray, e: np.ndarray) -> float | None:
    order = np.argsort(t)
    t, e = t[order], e[order]
    s, n = 1.0, len(t)
    for i, (ti, ei) in enumerate(zip(t, e, strict=True)):
        if ei:
            s *= 1 - 1 / (n - i)
            if s <= 0.5:
                return float(ti)
    return None


LANDMARK_MONTHS = (12, 24, 36, 60)


def km_survival(t: np.ndarray, e: np.ndarray, at_years: float) -> float | None:
    """Kaplan-Meier survival (percent) at a landmark; None beyond the last follow-up."""
    if not len(t) or at_years > t.max():
        return None
    order = np.argsort(t)
    s, n = 1.0, len(t)
    for i, (ti, ei) in enumerate(zip(t[order], e[order], strict=True)):
        if ti > at_years:
            break
        if ei:
            s *= 1 - 1 / (n - i)
    return round(100 * s, 1)


def exact_ci(x: int, n: int) -> list[float]:
    lo = stats.beta.ppf(0.025, x, n - x + 1) if x > 0 else 0.0
    hi = stats.beta.ppf(0.975, x + 1, n - x) if x < n else 1.0
    return [float(lo), float(hi)]


def follow_up_years(spec: dict) -> float:
    from .outcomes import _months

    months = [_months(_q(x.get("evidence")) or "") for x in spec.get("sample_size") or [] if x.get("quantity") == "followup_duration"]
    months = [m for m in months if m]
    return max(months) / 12 if months else FOLLOW_UP_YEARS


def tte_result(times_years: np.ndarray, events: np.ndarray) -> dict:
    d = int(events.sum())
    total = float(times_years.sum())
    out = {"patients": int(len(times_years)), "events": d, "km_median_months": None, "median_ci95_months": None}
    med = km_median(times_years, events)
    out["km_median_months"] = None if med is None else round(12 * med, 2)
    out["survival_percent"] = {f"{m}m": km_survival(times_years, events, m / 12) for m in LANDMARK_MONTHS}
    if d and total:
        lam = d / total
        z = 1.96 / math.sqrt(d)
        if out["km_median_months"] is not None:     # a median not reached (e.g. a cure fraction) has no exponential stand-in
            out["median_ci95_months"] = [round(12 * math.log(2) / (lam * math.exp(z)), 2), round(12 * math.log(2) / (lam * math.exp(-z)), 2)]
    return out


def _rate_draws(src: dict, rate: float, rng: np.random.Generator) -> np.ndarray:
    """Replicate true rates: the input's 95% CI as a logit-normal spread when the source gives one, else the point."""
    ci = src.get("ci95")
    if ci and 0 < ci[0] < rate < ci[1] < 1:
        logit = lambda p: math.log(p / (1 - p))  # noqa: E731
        sd = (logit(ci[1]) - logit(ci[0])) / (2 * 1.96)
        return 1 / (1 + np.exp(-(logit(rate) + sd * rng.standard_normal(REPLICATES))))
    return np.full(REPLICATES, rate)


def _replicate_medians(t: np.ndarray, ev: np.ndarray, rng: np.random.Generator) -> list[float]:
    """Medians (months) of replicate trials of the same size, resampled from the simulated patients."""
    out = []
    for _ in range(REPLICATES):
        i = rng.integers(0, len(t), len(t))
        m = km_median(t[i], ev[i])
        if m is None and ev[i].sum():
            m = math.log(2) / (ev[i].sum() / t[i].sum())
        if m is not None:
            out.append(12 * m)
    return out


def run(spec_lock: Path, journey_lock: Path, safety_lock: Path, out_dir: Path, facts_lock: Path | None = None, seed: int = 20261005) -> dict:
    from .studyspec import load_facts, load_studyspec

    spec, spec_rec = load_studyspec(spec_lock)
    facts = load_facts(facts_lock)[0] if facts_lock else None
    j = Path(journey_lock)
    adsl, adtte = _rows(j / "adsl.csv"), _rows(j / "adtte.csv")
    summary = json.loads((j / "journey_summary.json").read_text(encoding="utf-8"))
    safety = json.loads((Path(safety_lock) / "safety_results.json").read_text(encoding="utf-8"))
    feats = {a["arm_id"]: ((a.get("safety_v3") or {}).get("features") or {}) for a in safety["arms"]}
    arms = [a for a in spec["arms"] if any(r["ARMCD"] == a["arm_id"] for r in adsl)]
    by_arm = {a["arm_id"]: [r for r in adsl if r["ARMCD"] == a["arm_id"]] for a in arms}
    pfs = {r["USUBJID"]: r for r in adtte if r["PARAMCD"] == "PFS"}
    wd = summary.get("withdrawal") or {}
    fu = follow_up_years(spec)
    design = {}
    for r in spec.get("decision_rules") or []:
        b = r.get("rule") or {}
        for aid in r.get("arms") or []:
            design.setdefault(aid, {"p0": b.get("p0"), "p1": b.get("p1")})
    rng = np.random.default_rng(seed)

    results = []
    for e in spec["endpoints"]:
        name = _q(e.get("name"))
        kind, variable = classify(name, e.get("type"))
        item = {"endpoint": name, "role": e["role"], "class": kind, "variable": variable, "by_arm": {}}
        if e["role"] == "primary" and kind == "not_simulated":
            from .continuous import design as continuous_design, simulate as continuous_sim

            cd = continuous_design(spec)
            if cd.get("status") == "RESOLVED":           # a continuous primary comparison with a stated design (L034)
                sim = continuous_sim(cd, cd["effect"], rng, REPLICATES)
                null = continuous_sim(cd, 0.0, rng, REPLICATES)
                item.update({"class": "continuous", "status": "SIMULATED", "design": {k: cd[k] for k in ("effect", "sd", "sd_source", "n", "paired")},
                             "at_design_effect": sim, "at_no_effect": null,
                             "input": {"level": "protocol design (power statement)", "source": "; ".join(cd["effect_wording"])}})
                results.append(item)
                continue
        if kind == "not_simulated":
            item.update({"status": "NOT_SIMULATED", "kind": variable, "reason": "the generated patients carry no such measurement"})
            results.append(item)
            continue
        for a in arms:
            aid, pts = a["arm_id"], by_arm[a["arm_id"]]
            n = len(pts)
            src = quantify(spec, aid, kind, variable, feats.get(aid) or next(iter(feats.values()), {}), facts, design.get(aid))
            if kind == "safety":
                item["by_arm"][aid] = {"patients": n, "input": src,
                                       "any_serious_ae": sum(p["ANY_SAE"] == "Y" for p in pts), "any_grade3_ae": sum(p["ANY_GR3"] == "Y" for p in pts),
                                       "stopped_for_ae": sum(p["EOTREAS"].startswith("adverse") for p in pts)}
            elif kind == "proportion":
                rate = src.get("value")
                if rate is None:                        # nothing above the patients themselves: the journey's response is not simulated
                    rate = 0.0
                    src = {**src, "level": "no source", "note": "no evidence, no design rate: zero responders reported"}
                x = int(rng.binomial(1, rate, size=n).sum())
                item["by_arm"][aid] = {"patients": n, "responders": x, "rate": round(x / n, 4) if n else None, "ci95": exact_ci(x, n) if n else None,
                                       "predictive_rate": from_draws(rng.binomial(n, _rate_draws(src, rate, rng), size=REPLICATES) / n) if n else {},
                                       "input": src}
            else:                                       # time to event
                prog = (summary.get("progression") or {}).get(aid) or {}
                pv = prog.get("value") or {}
                rate, cure = pv.get("rate_per_year"), pv.get("cure_fraction") or 0.0
                if variable in PROGRESSION_VARIABLES and rate:
                    # the journey's progression model, followed to the protocol's follow-up (the journey's own PFS ends
                    # with treatment, so it is censored early)
                    from .outcomes import sample_efs_years

                    t_event = sample_efs_years(n, {"cure_fraction": cure, "failure_rate_per_year": rate}, 1.0, rng)
                    src = {"status": "RESOLVED", "level": "journey progression model", "source": prog.get("source"),
                           "value": None if cure else 12 * math.log(2) / rate, "cure_fraction": cure}
                else:
                    med = src.get("value")
                    if med is None:                     # no reported median anywhere: the journey's progression rate, else 12 months
                        med = 12 * math.log(2) / rate if rate else 12.0
                        src = {**src, "level": "journey progression rate" if rate else "assumption (12-month median)", "value": med}
                    t_event = rng.exponential(1 / (math.log(2) / (med / 12)), size=n)
                p_loss = (wd.get(aid) or {}).get("value") or 0.0
                t_loss = np.where(rng.random(n) < p_loss, rng.uniform(0, fu, size=n), np.inf)
                t = np.minimum.reduce([t_event, t_loss, np.full(n, fu)])
                ev = t_event <= np.minimum(t_loss, fu)
                item["by_arm"][aid] = {**tte_result(t, ev), "follow_up_years": round(fu, 2), "input": src,
                                       "predictive_median_months": from_draws(_replicate_medians(t, ev, rng))}
        item["status"] = "SIMULATED"
        results.append(item)

    flow = {}
    for a in arms:
        pts = by_arm[a["arm_id"]]
        reasons: dict = {}
        for p in pts:
            reasons[p["EOTREAS"]] = reasons.get(p["EOTREAS"], 0) + 1
        flow[a["arm_id"]] = {"arm": _q(a.get("label")), "started": len(pts), "end_of_treatment": reasons,
                             "deaths": sum(p.get("DTHFL") == "Y" for p in pts)}
    doc = {"endpoints_version": ENDPOINTS_VERSION, "seed": seed, "inputs": {"studyspec": spec_rec["files"]["studyspec.json"]},
           "participant_flow": flow, "endpoints": results,
           "counts": {k: sum(r["class"] == k for r in results) for k in ("time_to_event", "proportion", "continuous", "safety", "not_simulated")}}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "endpoint_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "endpoint_results.md").write_text(render(doc), encoding="utf-8")
    return doc


def render(doc: dict) -> str:
    L = ["# Simulated trial results", "", "## Participant flow", "", "| Arm | Started | Deaths | End of treatment |", "| --- | ---: | ---: | --- |"]
    for aid, f in doc["participant_flow"].items():
        L.append(f"| {aid} {f['arm']} | {f['started']} | {f['deaths']} | " + "; ".join(f"{k}: {v}" for k, v in sorted(f["end_of_treatment"].items(), key=lambda x: -x[1])) + " |")
    L += ["", "## Endpoints", ""]
    for r in doc["endpoints"]:
        L.append(f"### {r['role']}: {r['endpoint']}")
        if r["status"] == "NOT_SIMULATED":
            L += [f"Not simulated ({r['kind']}): {r['reason']}.", ""]
            continue
        if r["class"] == "continuous":
            d, a, z = r["design"], r["at_design_effect"], r["at_no_effect"]
            L += [f"- {'paired' if d['paired'] else 'two-group'} mean difference, n = {d['n']}, SD {d['sd']:.2f} ({d['sd_source']}); input: {r['input']['source']}",
                  f"- at the design effect {d['effect']:g}: P(success) {a['p_success']:.2f}; observed difference {text(a['observed_mean_difference'], '{:.2f}')}",
                  f"- at no effect: P(success) {z['p_success']:.2f}; observed difference {text(z['observed_mean_difference'], '{:.2f}')}", ""]
            continue
        for aid, v in r["by_arm"].items():
            src = v["input"]
            basis = f"input: {src.get('level')} - {src.get('source')}"
            if r["class"] == "time_to_event":
                med = f"{v['km_median_months']} months (95% CI {v['median_ci95_months']}; predictive {text(v.get('predictive_median_months', {}))})"                     if v["km_median_months"] is not None else "not reached"
                land = ", ".join(f"{k} {x}%" for k, x in (v.get("survival_percent") or {}).items() if x is not None)
                L.append(f"- {aid}: median {med}; event-free at {land}; {v['events']} events / {v['patients']}; {basis}")
            elif r["class"] == "proportion":
                L.append(f"- {aid}: {v['responders']}/{v['patients']} ({v['rate']:.1%}, 95% CI {v['ci95'][0]:.1%}-{v['ci95'][1]:.1%}; "
                         f"predictive {text(v.get('predictive_rate', {}), '{:.0%}')}); {basis}")
            else:
                L.append(f"- {aid}: any serious AE {v['any_serious_ae']}/{v['patients']}, any grade >= 3 {v['any_grade3_ae']}, "
                         f"stopped for an AE {v['stopped_for_ae']}")
        L.append("")
    return "\n".join(L) + "\n"
