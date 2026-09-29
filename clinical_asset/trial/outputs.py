"""Trial outputs from the simulated patients: datasets, registry-style tables and feasibility analyses.

From the locked stages of one protocol (cohort, eligibility, outcome model, safety, planning, science results):

Datasets (CSV, one simulated trial, seeded), shaped after the analysis datasets trials report from:
* adsl.csv  - one row per enrolled subject: arm, stratum, baseline demographics, enrollment day, unchecked criteria;
* adae.csv  - one row per subject and adverse event: each event's trial-level rate is drawn from its predictive
              distribution (safety stage), then each subject has the event with that probability;
* adtte.csv - time-to-event trials only: event-free survival per subject from the locked outcome model, under no
              effect and under the design alternative (each row states the effect it assumes).

Registry-style tables: participant flow, baseline characteristics by arm, adverse events by arm.

Feasibility analyses:
* screening funnel: eligible share of the source population (bounds), patients to screen for the target, and the
  criteria that decide it (the ones the simulated population cannot check);
* accrual: the historical model's time to target, and the sites needed to reach the target within the protocol's
  stated accrual period (or 2, 3 and 5 years), each at an 80% probability;
* trial failure risk (failure model), decision probabilities (science engine), subgroup outcomes.

Every number states its source; what the sources cannot give is UNRESOLVED.
"""

import csv
import json
import math
from pathlib import Path

import numpy as np

OUTPUTS_VERSION = "outputs-1.0.0"
DAY = 365.25


def _q(x):
    return x.get("text") if isinstance(x, dict) else x


def _write_csv(path: Path, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for r in rows for k in r)) or ["empty"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _share(values: list, total: int) -> dict:
    out: dict[str, float] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return {k: round(100 * c / total, 1) for k, c in sorted(out.items(), key=lambda kv: -kv[1])} if total else {}


def baseline_table(adsl: list[dict]) -> dict:
    arms = sorted({r["ARM"] for r in adsl})
    out = {}
    for arm in arms + ["TOTAL"]:
        rows = [r for r in adsl if arm == "TOTAL" or r["ARM"] == arm]
        ages = np.array([r["AGE"] for r in rows if r["AGE"] is not None], dtype=float)
        out[arm] = {"participants": len(rows),
                    "age_years": {"mean": round(float(ages.mean()), 1), "sd": round(float(ages.std(ddof=1)), 1) if len(ages) > 1 else None,
                                  "median": round(float(np.median(ages)), 1), "min": round(float(ages.min()), 1),
                                  "max": round(float(ages.max()), 1)} if len(ages) else None,
                    "sex_percent": _share([r["SEX"] for r in rows], len(rows)), "race_percent": _share([r["RACE"] for r in rows], len(rows)),
                    "ethnicity_percent": _share([r["ETHNIC"] for r in rows], len(rows))}
    return out


_GH = np.polynomial.hermite_e.hermegauss(40)


def p_any(p: np.ndarray, rho: float) -> float:
    """P(a patient has at least one of the events) under a one-factor Gaussian copula with correlation rho; each
    event keeps its own marginal probability."""
    from scipy import stats

    if len(p) == 0:
        return 0.0
    z, w = _GH
    thr = stats.norm.ppf(np.clip(p, 1e-9, 1 - 1e-9))
    if rho <= 0:
        return float(1 - np.prod(1 - p))
    cond = stats.norm.cdf((thr[None, :] - math.sqrt(rho) * z[:, None]) / math.sqrt(1 - rho))
    return float(1 - np.sum(w / w.sum() * np.prod(1 - cond, axis=1)))


def copula_rho(p: np.ndarray, target: float) -> tuple[float, str]:
    """The correlation that makes P(any event) equal the target (bisection; the any-event share falls as rho grows)."""
    lo, hi = 0.0, 0.98
    if p_any(p, lo) <= target:
        return 0.0, "independent events already at or below the target"
    if p_any(p, hi) > target:
        return hi, "the single most frequent event alone exceeds the target: the per-event rates are too high for it"
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if p_any(p, mid) > target else (lo, mid)
    return (lo + hi) / 2, "matched"


def adverse_event_rows(safety: dict, adsl: list[dict], rng: np.random.Generator, context: dict | None = None) -> tuple[list[dict], dict]:
    """Patient-level adverse events. Each event's trial-level rate is drawn from its predictive distribution; events
    cluster in patients through a one-factor Gaussian copula (marginals unchanged) whose correlation is set so that
    the share of patients with any serious event equals a draw from the evidence build's prior for 'any serious
    adverse event' in the arm's context (Simulation Parameter Asset V3); without such a prior, events are independent."""
    from scipy import stats

    from . import efficacy_prior as ep
    from .safety import draw_rates

    rows, notes = [], {}
    by_arm: dict[str, list[dict]] = {}
    for r in adsl:
        by_arm.setdefault(r["ARM"], []).append(r)
    trial_targets: dict[tuple, float] = {}      # one draw per trial for arms of the same context (same regimen classes)
    for arm in safety["arms"]:
        subjects = by_arm.get(arm["arm_id"], [])
        events = [dict(e) for e in arm["events"]]
        if not subjects or not events:
            continue
        p = np.array([float(draw_rates(e, rng, 1)[0]) for e in events])     # this simulated trial's rate per event
        serious = np.array([e["seriousness"] == "serious" for e in events])
        feats = (arm.get("safety_v3") or {}).get("features") or {}
        # the share with any serious event: the subgroup estimate (most similar studies by age group, phase and drug
        # classes); the family-level asset prior only when no subgroup estimate exists
        sub = _subgroup_any_serious(feats, context) if feats and context else None
        prior = ({"status": "RESOLVED", "level": f"subgroup: {sub['headline_subgroup']}", "point": sub["headline"]["estimate"]} if sub
                 else ep.arm_prior("serious_adverse_event", feats.get("disease_family", ""), [x["agent"] for x in feats.get("agents", [])],
                                   feats.get("classes", [])) if feats else {"status": "UNRESOLVED"})
        if prior.get("status") == "RESOLVED" and serious.any():
            key = (prior["level"], feats.get("disease_family"), tuple(sorted(feats.get("classes", []))), tuple(sorted(x["agent"] for x in feats.get("agents", []))))
            target = trial_targets.setdefault(key, prior["point"] if "point" in prior else float(rng.choice(prior["draws"])))
            rho, how = copula_rho(p[serious], target)
            scale = 1.0
            if how.startswith("independent events already"):
                # the listed serious events add up to less than the calibrated share with any serious event: the rest is
                # carried by one residual term for serious events the model does not predict individually (registries list
                # many rare serious terms); the listed events keep their own rates
                residual = 1 - (1 - target) / max(1e-12, 1 - p_any(p[serious], 0.0))
                events.append({"term": "other serious adverse events (not individually predicted)", "seriousness": "serious",
                               "source": f"residual to the any-serious prior ({prior['level']})"})
                p, serious = np.append(p, residual), np.append(serious, True)
                how = f"residual serious term {residual:.3f} added so that any serious event matches the prior"
            if how.startswith("the single most frequent"):
                # the per-event serious rates cannot all hold with the calibrated any-serious prior: the aggregate is trusted
                # and the serious rates are scaled down together until, independent, they give that share
                lo, hi = 0.0, 1.0
                for _ in range(50):
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if p_any(p[serious] * mid, 0.0) < target else (lo, mid)
                scale = (lo + hi) / 2
                p = np.where(serious, p * scale, p)
                rho, how = 0.0, f"serious rates scaled by {scale:.3f} to agree with the any-serious prior"
            notes[arm["arm_id"]] = {"any_serious_target": round(target, 3), "prior_level": prior["level"], "copula_rho": round(rho, 3),
                                    "serious_rate_scale": round(scale, 4), "fit": how}
        else:
            rho = 0.0
            notes[arm["arm_id"]] = {"copula_rho": 0.0, "fit": "no any-serious prior: independent events"}
        z = rng.standard_normal(len(subjects))
        latent = math.sqrt(rho) * z[:, None] + math.sqrt(1 - rho) * rng.standard_normal((len(subjects), len(events)))
        hit = latent < stats.norm.ppf(np.clip(p, 1e-9, 1 - 1e-9))[None, :]
        for i, s in enumerate(subjects):
            for j in np.flatnonzero(hit[i]):
                e = events[j]
                rows.append({"USUBJID": s["USUBJID"], "ARM": arm["arm_id"], "AETERM": e["term"], "AESER": "Y" if e["seriousness"] == "serious" else "N",
                             "SOURCE": e["source"]})
    return rows, notes


def ae_table(adae: list[dict], adsl: list[dict], top: int = 15) -> dict:
    n = {}
    for r in adsl:
        n[r["ARM"]] = n.get(r["ARM"], 0) + 1
    out = {}
    for arm, total in n.items():
        per: dict[tuple, set] = {}
        for r in adae:
            if r["ARM"] == arm:
                per.setdefault((r["AETERM"], r["AESER"]), set()).add(r["USUBJID"])
        any_ser = len({r["USUBJID"] for r in adae if r["ARM"] == arm and r["AESER"] == "Y"})
        any_oth = len({r["USUBJID"] for r in adae if r["ARM"] == arm and r["AESER"] == "N"})
        ranked = sorted(per.items(), key=lambda kv: -len(kv[1]))[:top]
        out[arm] = {"participants": total, "any_serious_percent": round(100 * any_ser / total, 1) if total else None,
                    "any_other_percent": round(100 * any_oth / total, 1) if total else None,
                    "top_events": [{"term": t, "serious": s == "Y", "participants": len(ids), "percent": round(100 * len(ids) / total, 1)}
                                   for (t, s), ids in ranked]}
    return out


def tte_rows(adsl: list[dict], model: dict, rng: np.random.Generator, horizon_years: float = 5.0) -> list[dict]:
    from .outcomes import sample_efs_years

    efs = model.get("control_efs") or {}
    if efs.get("status") != "RESOLVED":
        return []
    params = efs.get("model") or efs
    alts = model.get("effect", {}).get("design_alternatives") or []
    effects = [("no effect", 1.0)] + ([("design alternative", round(alts[0]["hr"], 4))] if alts else [])
    control = model.get("control_arm_id")
    rows = []
    for label, hr in effects:
        for arm in sorted({r["ARM"] for r in adsl}):
            subjects = [r for r in adsl if r["ARM"] == arm]
            t = sample_efs_years(len(subjects), params, 1.0 if arm == control else hr, rng)
            for s, x in zip(subjects, t, strict=True):
                rows.append({"USUBJID": s["USUBJID"], "ARM": arm, "PARAMCD": "EFS", "EFFECT_ASSUMED": label, "HR_ASSUMED": 1.0 if arm == control else hr,
                             "AVAL_YEARS": round(float(min(x, horizon_years)), 4), "CNSR": int(not x <= horizon_years)})
    return rows


def subgroup_efs(adsl: list[dict], adtte: list[dict], at_years: float = 3.0) -> dict:
    from .simulate import kaplan_meier

    by_id = {r["USUBJID"]: r for r in adsl}
    out = {}
    for effect in sorted({r["EFFECT_ASSUMED"] for r in adtte}):
        rows = [r for r in adtte if r["EFFECT_ASSUMED"] == effect]
        groups = {"all": rows}
        for key, f in (("sex", lambda s: s["SEX"]), ("age", lambda s: "below 18" if (s["AGE"] or 0) < 18 else "18 to 64" if s["AGE"] < 65 else "65 or older"),
                       ("stratum", lambda s: s["STRATUM"])):
            for r in rows:
                groups.setdefault(f"{key}={f(by_id[r['USUBJID']])}", []).append(r)
        out[effect] = {}
        for g, v in groups.items():
            if len(v) < 10:
                continue
            km = kaplan_meier(np.array([r["AVAL_YEARS"] for r in v]), np.array([r["CNSR"] == 0 for r in v]), [at_years])[0]
            out[effect][g] = {"subjects": len(v), f"efs_{at_years:g}y_percent": None if km is None else round(100 * km, 1)}
    return out


def screening(spec: dict, eligibility: dict, target: int | None) -> dict:
    lo, hi = eligibility["proven_eligible_share"], eligibility["not_proven_ineligible_share"]
    rendering = {c["criterion_id"]: (c.get("rendering") or _q(c.get("text")) or "")[:160] for c in spec["eligibility"]}
    blocking = list(eligibility.get("blocking_unknowns") or [])
    return {"eligible_share_bounds": [lo, hi],
            "patients_to_screen_for_target": ({"at_least": math.ceil(target / hi) if hi else None, "at_most": math.ceil(target / lo) if lo else None}
                                              if target else None),
            "note": ("the upper bound needs every unchecked criterion to be met; the lower bound counts only patients proven eligible. "
                     "Narrowing them needs the variables the unchecked criteria use"),
            "unchecked_criteria": [{"criterion_id": c, "rendering": rendering.get(c, "")} for c in blocking[:15]],
            "decisive_exclusions": eligibility.get("decisive_exclusions")}


def sites_needed(spec: dict, target: int | None, asset: Path, durations: list[float], draws: int = 3000) -> dict:
    """Sites needed so that the historical accrual model gives an 80% probability of reaching the target within each
    period. Uses the model's site-count effect; everything else as in the planning report."""
    from ..planning.accrual import predict
    from ..planning.report import protocol_features

    if not target or not (Path(asset) / "accrual_model.json").exists():
        return {"status": "UNRESOLVED", "reason": "no enrollment target or no accrual model"}
    model = json.loads((Path(asset) / "accrual_model.json").read_text(encoding="utf-8"))
    feats = protocol_features(spec, target, Path("data/simulation_parameters_v2/hierarchy/disease_family_map.parquet"))
    rng = np.random.default_rng(0)
    out = {}
    for years in durations:
        found = None
        for sites in (1, 2, 3, 5, 8, 10, 15, 20, 30, 40, 60, 80, 100, 150, 200):
            per_month = np.exp(predict(model, {**feats, "listed_sites": sites}, draws=draws, seed=sites)["log_rate"])
            months = rng.gamma(shape=target, scale=1.0 / per_month)
            p = float(np.mean(months / 12 <= years))
            if p >= 0.8:
                found = {"sites": sites, "p_complete": round(p, 3)}
                break
        out[f"{years:g}y"] = found or {"sites": ">200", "p_complete_at_200": round(p, 3)}
    return {"status": "RESOLVED", "target": target, "by_accrual_period": out,
            "note": "sites as listed in registry records; the model's site effect is observational (trials that list more sites recruit faster)"}


def build(spec_lock: Path, eligibility_lock: Path, cohorts_lock: Path, outcomes_lock: Path, safety_lock: Path, planning_lock: Path,
          results_lock: Path | None, out_dir: Path, seed: int = 20260927,
          accrual_asset: Path = Path("data/planning_asset_v2_2/operational")) -> dict:
    from .lock import load_locked, verify
    from .studyspec import load_studyspec

    spec, _ = load_studyspec(spec_lock)
    eligibility = load_locked(eligibility_lock, "eligibility_summary.json")["summary"]
    recruitment = load_locked(cohorts_lock, "recruitment_summary.json")
    model = load_locked(outcomes_lock, "outcome_model.json")
    safety = load_locked(safety_lock, "safety_results.json")
    planning = load_locked(planning_lock, "planning_report.json")
    verify(cohorts_lock)
    first = min(Path(cohorts_lock).glob("cohort_*.jsonl"))
    with open(first, encoding="utf-8") as fh:
        cohort = [json.loads(line) for line in fh]
    rng = np.random.default_rng(seed)
    labels = {a["arm_id"]: _q(a["label"]) for a in spec["arms"]}
    adsl = [{"USUBJID": c["subject_id"], "PATIENT_ID": c["patient_id"], "ARM": c["arm_id"], "ARM_LABEL": (labels.get(c["arm_id"]) or "")[:80],
             "STRATUM": c.get("stratum"), "AGE": (c["baseline"].get("demographic:age") or {}).get("value"),
             "SEX": c["baseline"].get("demographic:sex"), "RACE": c["baseline"].get("demographic:race"),
             "ETHNIC": c["baseline"].get("demographic:ethnicity"), "ENROLLMENT_DAY": c.get("enrollment_day"),
             "UNCHECKED_CRITERIA": len(c.get("unchecked_criteria") or [])} for c in cohort]
    from .subgroups import arm_age_group

    phase = planning["accrual"]["historical_model"].get("features", {}).get("phase") if planning["accrual"].get("historical_model") else None
    context = {"age_group": arm_age_group(spec), "phase": phase}
    adae, ae_notes = adverse_event_rows(safety, adsl, rng, context)
    adtte = tte_rows(adsl, model, rng)
    target = (recruitment["accrual_plan"].get("target") or {}).get("patients")
    stated = planning["accrual"].get("stated_accrual_durations_years") or []
    doc = {"outputs_version": OUTPUTS_VERSION, "seed": seed, "protocol_id": planning.get("protocol_id"), "cohort_file": first.name,
           "datasets": {"adsl.csv": len(adsl), "adae.csv": len(adae), "adtte.csv": len(adtte)},
           "tables": {"participant_flow": {arm: {"enrolled": sum(r["ARM"] == arm for r in adsl)} for arm in sorted({r["ARM"] for r in adsl})},
                      "baseline_characteristics": baseline_table(adsl), "adverse_events": ae_table(adae, adsl),
                      "adverse_event_dependence": ae_notes},
           "feasibility": {
               "screening": screening(spec, eligibility, target),
               "accrual": {"historical_model": {k: planning["accrual"]["historical_model"].get(k) for k in
                                                ("status", "patients_per_year", "enrollment_duration_years", "p_enrollment_complete_by")},
                           "protocol_scenarios": planning["accrual"].get("protocol_scenarios")},
               "sites_needed": sites_needed(spec, target, Path(accrual_asset), sorted(set(stated)) or [2.0, 3.0, 5.0]),
               "trial_failure_risk": planning["accrual"].get("failure_model"),
               "retention": {"loss_to_follow_up": model.get("loss_to_follow_up"), "off_study_limit": model.get("off_study_limit")},
               "decision_probabilities": _decisions(results_lock),
               "subgroups": subgroup_efs(adsl, adtte) if adtte else {"status": "UNRESOLVED", "reason": "no time-to-event outcome model"},
               "subgroup_estimates": subgroup_estimates(safety, context, _primary_target(spec, results_lock))}}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "adsl.csv", adsl)
    _write_csv(out_dir / "adae.csv", adae)
    _write_csv(out_dir / "adtte.csv", adtte)
    (out_dir / "trial_outputs.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "trial_outputs.md").write_text(render(doc), encoding="utf-8")
    return doc


def _decisions(results_lock: Path | None) -> dict:
    from .lock import load_locked

    if results_lock is None:
        return {"status": "UNRESOLVED", "reason": "no science results"}
    for name in ("binary_results.json", "trial_results.json", "escalation_results.json", "ni_results.json"):
        if (Path(results_lock) / name).exists():
            r = load_locked(results_lock, name)
            if name == "ni_results.json":
                return {"kind": "non-inferiority (binary, synthesis)", "power_at_protocol_assumption": r.get("power_at_protocol_assumption"),
                        "p_success_curve": r.get("p_success_curve"), "predicted_response": r.get("predicted_response")}
            if name == "binary_results.json":
                return {"kind": "binary rules", "rules": [
                    {"rule": x["decision_rule_id"], "arm": (x["arm"] or "")[:60],
                     "prob_of_interest_at_p0_p1": {str(c["p"]): c["prob_of_interest"] for c in x["exact_curve"] if c["p"] in (x["rule"]["p0"], x["rule"]["p1"])},
                     "evidence_prior": {k: (x.get("evidence_prior") or {}).get(k) for k in ("status", "level", "rate", "predictive_prob_of_interest", "reason")}}
                    for x in r["rules"]]}
            if name == "trial_results.json":
                return {"kind": "time-to-event", "success_by_effect": {k: [{"hr": row["hr"], "p_success": row["p_success"]} for row in v]
                                                                        for k, v in (r.get("success_curve") or {}).items()}}
            return {"kind": "dose escalation", "rules": [{"rule": x["decision_rule_id"], "result": x.get("result", "simulated")} for x in r["rules"]]}
    return {"status": "UNRESOLVED", "reason": "no science results file"}


def render(doc: dict) -> str:
    t, f = doc["tables"], doc["feasibility"]
    L = [f"# Trial outputs: {doc['protocol_id']} ({doc['outputs_version']})", "",
         f"Datasets (one simulated trial, seed {doc['seed']}): " + ", ".join(f"{k} ({v} rows)" for k, v in doc["datasets"].items()) + ".", "",
         "## Participant flow", ""]
    L += [f"- {arm}: {v['enrolled']} enrolled" for arm, v in t["participant_flow"].items()]
    L += ["", "## Baseline characteristics", "", "| group | n | age mean (sd) | age median (range) | sex % | race % (top 3) | ethnicity % |",
          "| --- | ---: | --- | --- | --- | --- | --- |"]
    for g, b in t["baseline_characteristics"].items():
        a = b["age_years"] or {}
        L.append(f"| {g} | {b['participants']} | {a.get('mean')} ({a.get('sd')}) | {a.get('median')} ({a.get('min')}-{a.get('max')}) | "
                 f"{b['sex_percent']} | {dict(list(b['race_percent'].items())[:3])} | {b['ethnicity_percent']} |")
    L += ["", "## Adverse events (simulated patients)", ""]
    for arm, a in t["adverse_events"].items():
        L.append(f"- {arm} (n = {a['participants']}): any serious {a['any_serious_percent']}%, any other {a['any_other_percent']}%; top: "
                 + "; ".join(f"{e['term']} {e['percent']}%" for e in a["top_events"][:8]))
    s = f["screening"]
    L += ["", "## Feasibility", "", (f"- Eligible share of the source population: {s['eligible_share_bounds'][0]:.0%} to {s['eligible_share_bounds'][1]:.0%}; "
                                     f"patients to screen for the target: {s['patients_to_screen_for_target']}. {s['note']}.")]
    if s["unchecked_criteria"]:
        L.append("- Criteria the simulated population cannot check: " + "; ".join(c["criterion_id"] for c in s["unchecked_criteria"]))
    h = f["accrual"]["historical_model"]
    if h.get("status") == "RESOLVED":
        L.append(f"- Accrual (historical model): {h['patients_per_year']['median']:.1f} patients/year (80% {h['patients_per_year']['q10']:.1f}-"
                 f"{h['patients_per_year']['q90']:.1f}); target reached in {h['enrollment_duration_years']['median']:.1f} years (80% "
                 f"{h['enrollment_duration_years']['q10']:.1f}-{h['enrollment_duration_years']['q90']:.1f}).")
    sn = f["sites_needed"]
    if sn.get("status") == "RESOLVED":
        L.append("- Sites needed for an 80% chance of reaching the target of " + str(sn["target"]) + ": "
                 + "; ".join(f"within {k}: {v.get('sites')}" for k, v in sn["by_accrual_period"].items()) + f" ({sn['note']}).")
    fr = f["trial_failure_risk"] or {}
    if fr.get("status") == "RESOLVED":
        p = fr["probabilities"]
        L.append(f"- Trial outcome risk: withdrawn {p['withdrawn']:.0%}, terminated for poor accrual {p['terminated_accrual']:.0%}, "
                 f"terminated otherwise {p['terminated_other']:.0%}, completed {p['completed']:.0%}.")
    se = f.get("subgroup_estimates") or {}
    if se.get("arms"):
        L += ["", "## Subgroup estimates (most similar studies)", "", se["note"] + ".", ""]
        for arm, targets in se["arms"].items():
            for target, e in targets.items():
                if e.get("status") != "RESOLVED" or not e.get("headline"):
                    L.append(f"- {arm} {target}: {e.get('status')} ({e.get('reason')})")
                    continue
                h = e["headline"]
                flag = " **ATTENTION: " + e["protocol_subgroup"]["note"] + "**" if e["protocol_subgroup"]["attention"] else ""
                L.append(f"- {arm} {target}: {h['estimate']:.1%} (95% CI {h['ci95'][0]:.1%}-{h['ci95'][1]:.1%}; single trial {h['single_trial_80'][0]:.0%}-"
                         f"{h['single_trial_80'][1]:.0%}) from {h['studies']} studies, subgroup '{e['headline_subgroup']}'.{flag}")
                for key, groups in e["breakdown"].items():
                    L.append(f"    - by {key}: " + "; ".join(f"{g} {p['estimate']:.0%} ({p['studies']} studies)" for g, p in groups.items() if p))
    d = f["decision_probabilities"]
    if d.get("kind") == "binary rules":
        for r in d["rules"]:
            ep = r["evidence_prior"]
            L.append(f"- {r['rule']}: P(of interest) at p0/p1 {r['prob_of_interest_at_p0_p1']}; evidence prior: "
                     + (f"{ep['level']} level, rate {ep['rate']['median']:.2f} (90% {ep['rate']['q05']:.2f}-{ep['rate']['q95']:.2f}), predictive "
                        f"P(of interest) {ep.get('predictive_prob_of_interest')}" if ep.get("status") == "RESOLVED" else f"{ep.get('status')} ({ep.get('reason')})"))
    if isinstance(f["subgroups"], dict) and "status" not in f["subgroups"]:
        L += ["", "## Subgroups (simulated EFS)", ""]
        for effect, groups in f["subgroups"].items():
            L.append(f"- {effect}: " + "; ".join(f"{g} {v[next(k for k in v if k.startswith('efs_'))]}% (n={v['subjects']})" for g, v in groups.items()))
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------- baseline characteristics against the registry


def registry_baseline(registry: dict) -> dict | None:
    """The registry's baseline table, total row: participants, mean or median age, and the percentage of each sex,
    race and ethnicity category."""
    base = (registry.get("resultsSection") or {}).get("baselineCharacteristicsModule")
    if not base:
        return None
    total = next((g["id"] for g in base.get("groups", []) if g["title"].casefold() == "total"), None)
    if total is None and len(base.get("groups", [])) == 1:
        total = base["groups"][0]["id"]
    if total is None:
        return None
    n = next((int(c["value"]) for d in base.get("denoms", []) for c in d.get("counts", []) if c["groupId"] == total), None)
    out = {"participants": n, "age": {}, "sex": {}, "race": {}, "ethnicity": {}}
    for m in base.get("measures", []):
        title = m["title"].casefold()
        vals = [(cat.get("title") or c.get("title") or "", float(x["value"])) for c in m.get("classes", []) for cat in c.get("categories", [])
                for x in cat.get("measurements", []) if x["groupId"] == total and _num(x.get("value")) is not None]
        if title.startswith("age") and "continuous" in title and vals:
            out["age"][(m.get("paramType") or "").casefold()] = vals[0][1]
        for key, word in (("sex", "sex"), ("race", "race"), ("ethnicity", "ethnicity")):
            if title.startswith(word) and n:
                count = "count" in (m.get("paramType") or "").casefold()
                for cat, v in vals:
                    out[key][_norm_cat(cat)] = round(100 * v / n, 2) if count else v
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _norm_cat(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def compare_baseline(spec_lock: Path, registry_file: Path, registry_fetched_at: str, locked_at: str, out_dir: Path,
                     replicates: int = 300, seed: int = 20260927) -> dict:
    """The registry's baseline table against 90% predictive intervals from replicate trials of the registry's size,
    each drawn in the V3 generator's uncertainty-propagating mode (one posterior draw and a new-study deviation per
    trial) for the protocol's query. Protocol-stated shares are not applied: this scores the evidence model."""
    from ..spa3.protocol import BaselineGenerator
    from .population import protocol_query
    from .studyspec import load_studyspec

    spec, _ = load_studyspec(spec_lock)
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    observed = registry_baseline(registry)
    doc = {"outputs_version": OUTPUTS_VERSION, "registry_fetched_at": registry_fetched_at, "predictions_locked_at": locked_at,
           "nct_id": registry["protocolSection"]["identificationModule"]["nctId"], "observed": observed, "items": []}
    if not observed or not observed["participants"]:
        doc["status"] = "UNRESOLVED: the registry reports no baseline table"
    else:
        gen = BaselineGenerator.load()
        query = protocol_query(spec)
        n = observed["participants"]
        sims = {"age_mean": [], "age_median": [], "sex": {}, "race": {}, "ethnicity": {}}
        for r in range(replicates):
            params = gen.parameters(query, "random", True, seed + r)
            pats = gen.sample(params, n, seed + r)
            ages = np.asarray(pats["age"], dtype=float)
            sims["age_mean"].append(float(ages.mean()))
            sims["age_median"].append(float(np.median(ages)))
            for key, probs in (("sex", {"female": params["p_female"], "male": 1 - params["p_female"]}),
                               ("race", params.get("race_probabilities") or {}), ("ethnicity", params.get("ethnicity_probabilities") or {})):
                rng = np.random.default_rng(seed + 7 * r)
                cats = list(probs)
                draw = rng.multinomial(n, np.array([probs[c] for c in cats]) / max(1e-12, sum(probs.values())))
                for c, k in zip(cats, draw, strict=True):
                    sims[key].setdefault(_norm_cat(c), []).append(100 * k / n)
        def add(quantity, values, obs):
            lo, hi = float(np.quantile(values, 0.05)), float(np.quantile(values, 0.95))
            doc["items"].append({"quantity": quantity, "predicted_median": round(float(np.median(values)), 2), "predicted_90": [round(lo, 2), round(hi, 2)],
                                 "observed": obs, "inside_90": lo <= obs <= hi})
        for kind in ("mean", "median"):
            if kind in observed["age"]:
                add(f"age {kind}, years", sims[f"age_{kind}"], observed["age"][kind])
        for key in ("sex", "race", "ethnicity"):
            for cat, obs in observed[key].items():
                match = next((k for k in sims[key] if k == cat or k.replace("_", "") == cat.replace("_", "")), None)
                if match:
                    add(f"{key}: {cat} %", sims[key][match], obs)
                else:
                    doc["items"].append({"quantity": f"{key}: {cat} %", "observed": obs, "predicted_median": None,
                                         "note": "category not in the evidence model"})
        scored = [i for i in doc["items"] if "inside_90" in i]
        doc["summary"] = {"scored": len(scored), "inside_90": sum(i["inside_90"] for i in scored),
                          "query": {k: v for k, v in query.canonical().items() if k != "allowed_categories"}}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "baseline_comparison.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    lines = [f"# Baseline characteristics against the registry ({OUTPUTS_VERSION})", "",
             f"Registry {doc['nct_id']}; predictions locked at {locked_at}; registry fetched at {registry_fetched_at}.", ""]
    if "summary" in doc:
        lines += [f"Inside the 90% predictive interval: {doc['summary']['inside_90']} of {doc['summary']['scored']}. Query: {doc['summary']['query']}.", "",
                  "| quantity | predicted median | 90% interval | registry | inside |", "| --- | ---: | --- | ---: | --- |"]
        lines += [f"| {i['quantity']} | {i.get('predicted_median')} | {i.get('predicted_90')} | {i['observed']} | {i.get('inside_90', '-')} |" for i in doc["items"]]
    else:
        lines.append(doc["status"])
    (out_dir / "baseline_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


def _subgroup_any_serious(feats: dict, context: dict) -> dict | None:
    from . import subgroups as sg

    e = sg.estimate("serious_adverse_event", feats.get("disease_family", ""), feats.get("classes", []),
                    [x["agent"] for x in feats.get("agents", [])], context["age_group"], context.get("phase"))
    return e if e.get("status") == "RESOLVED" and e.get("headline") else None


def _primary_target(spec: dict, results_lock: Path | None) -> str | None:
    from . import efficacy_prior as ep

    name = next((_q(e.get("name")) for e in spec["endpoints"] if e["role"] == "primary"), None)
    return ep.endpoint_target(name or "") if name else None


def subgroup_estimates(safety: dict, context: dict, primary_target: str | None) -> dict:
    """Per arm: the subgroup estimate (point, 50% and 95% confidence interval of the subgroup average, single-trial
    range) of the share with any serious adverse event and of the primary response-type endpoint, with the breakdown by
    age group, phase and drug-class overlap and the flag for a protocol subgroup the evidence barely holds."""
    from . import subgroups as sg

    out = {}
    for arm in safety["arms"]:
        feats = (arm.get("safety_v3") or {}).get("features")
        if not feats:
            continue
        entry = {}
        for target in ["serious_adverse_event"] + ([primary_target] if primary_target else []):
            e = sg.estimate(target, feats["disease_family"], feats["classes"], [x["agent"] for x in feats["agents"]], context["age_group"], context.get("phase"))
            entry[target] = e
        out[arm["arm_id"]] = entry
    return {"context": context, "arms": out, "evidence": sg.evidence_provenance(),
            "note": ("estimates are the random-effects average of the most similar subgroup of studies; the 95% confidence interval is for that "
                     "average, the single-trial range for one new trial (held-out studies: median absolute error 0.16 for any serious event)")}
