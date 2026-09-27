"""Milestones 15 and 16: registry-style results and the probability of trial success.

Every replicate is a complete simulated trial: recruitment (arrivals, allocation and stratum drawn again from the
enrollable pool at the scenario's accrual rate), evaluability, outcomes, follow-up and the protocol's primary
analysis. For each accrual scenario and each true effect on the grid, `replicates` trials give:

* M16: the probability that the primary analysis succeeds (with its Monte Carlo standard error), the
  distribution of the analysis time, events and estimated hazard ratio; at HR = 1 this is the type I error and at
  the protocol's design alternatives it is the power, which is compared with the power the protocol claims.
* M15: distributions (median and 90% interval over replicates) of the quantities a registry results record
  reports: participants started and evaluable per arm, events, EFS by arm at 2, 3 and 5 years, the test result and
  the hazard ratio; plus, for the locked enrolled cohort, one complete registry-style results record per effect
  (participant flow, baseline characteristics, outcome measures, adverse events). Everything the sources cannot
  determine is reported as UNRESOLVED with its reason.
"""

import json
import math
from pathlib import Path

import numpy as np

from .recruitment import enrollment_draws, randomization_plan, stratum_of
from .simulate import (
    DAY,
    kaplan_meier,
    primary_analysis,
    simulate_arrays,
    simulate_trial,
    treatment_phases,
)

RESULTS_VERSION = "results-1.0.0"
TIMEPOINTS_YEARS = [2.0, 3.0, 5.0]


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def _dist(values) -> dict | None:
    v = np.array([x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))], dtype=float)
    if len(v) == 0:
        return None
    return {"median": float(np.median(v)), "q05": float(np.quantile(v, 0.05)), "q95": float(np.quantile(v, 0.95)), "n": len(v)}


def _km_by_arm(trial: dict, arms: list[str]) -> dict:
    m = trial["evaluable"]
    out = {}
    for a in arms:
        sel = m & (trial["arm"] == a)
        out[a] = kaplan_meier(trial["time_days"][sel] / DAY, trial["event"][sel], TIMEPOINTS_YEARS)
    return out


def success_curve(spec: dict, model: dict, pool_strata: np.ndarray, plan: dict, randomization: dict, replicates: int, seed: int) -> dict:
    phases = treatment_phases(spec)
    analysis = next(a for a in spec["analyses"] if a.get("primary"))
    arm_ids = np.array([a["arm_id"] for a in randomization["arms"]])
    ratio = randomization["ratio"] or [1.0] * len(arm_ids)
    grid = model["effect"]["grid_hr"]
    out = {}
    for si, sc in enumerate(plan["scenarios"]):
        rows = []
        for gi, hr in enumerate(grid):
            succ, pvals, events, hrs, years, enrolled, km = [], [], [], [], [], [], {a: [] for a in arm_ids}
            for r in range(replicates):
                rng = np.random.default_rng([seed, si, gi, r])
                order, days, alloc = enrollment_draws(len(pool_strata), plan["target"]["patients"], sc["rate_per_year"], ratio, rng)
                trial = simulate_arrays(days, arm_ids[alloc], pool_strata[order], model, hr, rng, phases)
                res = primary_analysis(trial, analysis)
                succ.append(res["success"])
                pvals.append(res["p_value"])
                events.append(res["events"])
                hrs.append(res["hr"])
                years.append(trial["analysis_day"] / DAY)
                enrolled.append(trial["n_enrolled"])
                for a, v in _km_by_arm(trial, list(arm_ids)).items():
                    km[a].append(v)
            p = float(np.mean(succ))
            rows.append({"hr": hr, "p_success": p, "mc_se": math.sqrt(p * (1 - p) / replicates), "replicates": replicates,
                         "analysis_years_from_first_enrollment": _dist(years), "enrolled": _dist(enrolled), "events": _dist(events),
                         "estimated_hr": _dist(hrs), "p_value": _dist(pvals),
                         "efs_by_arm": {a: {f"{t:g}y": _dist([v[k] for v in km[a]]) for k, t in enumerate(TIMEPOINTS_YEARS)} for a in arm_ids}})
        out[sc["scenario"]] = rows
    return out


def design_checks(curve: dict, model: dict, spec: dict) -> list[dict]:
    """Simulated power at the protocol's design alternatives against the power the protocol states, and type I error."""
    checks = []
    analysis = next(a for a in spec["analyses"] if a.get("primary"))
    stated = [(s.get("power"), _q(s.get("effect")) or "") for s in analysis.get("scenarios") or []]
    alpha = (analysis.get("alpha") or {}).get("value") or 0.05
    for name, rows in curve.items():
        null = next(r for r in rows if abs(r["hr"] - 1.0) < 1e-9)
        checks.append({"scenario": name, "check": "type I error at HR 1", "simulated": null["p_success"], "mc_se": null["mc_se"],
                       "expected": alpha, "consistent": abs(null["p_success"] - alpha) <= 3 * max(null["mc_se"], 1e-9)})
        cure = model["control_efs"].get("cure_fraction")
        for alt in model["effect"]["design_alternatives"]:
            row = min(rows, key=lambda r: abs(r["hr"] - alt["hr"]))
            claimed = next((p for p, text in stated if p is not None and f"{round(alt['experimental_long_term'] * 100)}%" in text), None)
            comparable = cure is not None and abs(alt["control_long_term"] - cure) < 0.005
            check = {"scenario": name, "check": f"power at design alternative HR {alt['hr']:.3f} ({' '.join(alt['wording'].split())[:80]})",
                     "simulated": row["p_success"], "mc_se": row["mc_se"], "protocol_claims_at_least": claimed, "comparable": comparable}
            if not comparable:
                check["note"] = (f"the protocol computed this power for a control long-term EFS of {alt['control_long_term']:.0%}; the simulated "
                                 f"control is {cure:.0%}, so the claim is not comparable")
            elif claimed is not None:
                check["consistent"] = row["p_success"] >= claimed - 3 * max(row["mc_se"], 1e-9)
            checks.append(check)
    return checks


def registry_record(trial: dict, analysis_result: dict, model: dict, spec: dict, randomization: dict, rng: np.random.Generator) -> dict:
    """A registry-style results record for one simulated trial."""
    arms = randomization["arms"]
    label = {a["arm_id"]: a["label"] for a in arms}
    rows = {}
    for a in arms:
        sel = trial["arm"] == a["arm_id"]
        ev = sel & trial["evaluable"]
        base = [b for b, s in zip(trial["baseline"], sel, strict=True) if s]
        ages = np.array([b["demographic:age"]["value"] for b in base])
        flow = {"started": int(sel.sum()), "evaluable_for_primary_objectives": int(ev.sum()),
                "reasons_follow_up_ended": {k: int(np.sum(sel & (trial["reason"] == k))) for k in ("event", "lost_to_follow_up", "off_study_time_limit", "administrative")}}
        for pid, t in trial["treatment"].items():
            flow[f"completed_{pid}"] = int(np.sum(sel & t["completed"])) if t["status"] == "RESOLVED" else {"status": "UNRESOLVED", "reason": t["reason"]}
        rows[a["arm_id"]] = {
            "arm": label[a["arm_id"]], "description": a.get("description"), "participant_flow": flow,
            "baseline": {"participants": len(base), "age_years": {"mean": float(ages.mean()), "sd": float(ages.std(ddof=1)) if len(ages) > 1 else None},
                         **{var.split(":")[1]: _counts(base, var) for var in ("demographic:sex", "demographic:race", "demographic:ethnicity")}},
            "efs_percent": {f"{t:g}y": (None if v is None else round(100 * v, 1))
                            for t, v in zip(TIMEPOINTS_YEARS, kaplan_meier(trial["time_days"][ev] / DAY, trial["event"][ev], TIMEPOINTS_YEARS), strict=True)},
            "events": int(np.sum(ev & trial["event"])),
            "adverse_events": _adverse_events(model, a["arm_id"], int(sel.sum()), rng)}
    endpoints = []
    for e in spec["endpoints"]:
        name = _q(e.get("name"))
        if e["role"] == "primary":
            endpoints.append({"endpoint": name, "type": "primary", "status": "SIMULATED", "measure": "EFS percent by arm at 2, 3 and 5 years",
                              "time_origin": model["efs_origin"],
                              "analysis": {k: analysis_result[k] for k in ("test", "stratified", "sidedness", "alpha", "p_value", "success", "events", "evaluable", "hr", "hr_ci95", "stratification_note")}})
        else:
            endpoints.append({"endpoint": name, "type": e["role"], "status": "UNRESOLVED",
                              "reason": "no source quantifies this endpoint for the simulation (see outcome model)"})
    return {"arms": rows, "outcome_measures": endpoints,
            "analysis_years_from_first_enrollment": trial["analysis_day"] / DAY, "enrolled": trial["n_enrolled"],
            "notes": [model["assessment_timing"], model["efs_origin"],
                      "adverse events: " + next(iter(model["adverse_events_asset"].values()))["note"]]}


def _counts(base: list[dict], var: str) -> dict:
    out: dict[str, int] = {}
    for b in base:
        k = str(b.get(var, "unknown"))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _adverse_events(model: dict, arm_id: str, n: int, rng: np.random.Generator) -> dict:
    src = model["adverse_events_asset"].get(arm_id) or {}
    events = {"serious": [], "other": []}
    for e in src.get("events", []):
        k = int(rng.binomial(n, e["rate"]))
        events["serious" if e["seriousness"] == "serious" else "other"].append({"term": e["event"], "participants_affected": k, "at_risk": n})
    return {"source": f"asset class signature {src.get('class_signature')} (missing classes {src.get('missing_classes')})", **events}


def run_results(spec_lock: Path, population_lock: Path, eligibility_lock: Path, cohorts_lock: Path, outcomes_lock: Path,
                out_dir: Path, replicates: int = 1000, seed: int = 20260927) -> dict:
    from .lock import load_locked, verify
    from .recruitment import accrual_plan
    from .studyspec import load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    model = load_locked(outcomes_lock, "outcome_model.json")
    records = {name: verify(p) for name, p in (("population", population_lock), ("eligibility", eligibility_lock), ("cohorts", cohorts_lock))}
    if model["control_efs"]["status"] != "RESOLVED" or not model["analysis_rule"].get("evaluable_target"):
        raise ValueError("the outcome model does not determine the control EFS or the analysis rule: the trial cannot be simulated")
    with open(Path(population_lock) / "population.jsonl", encoding="utf-8") as fh:
        patients = [json.loads(line) for line in fh]
    with open(Path(eligibility_lock) / "eligibility.jsonl", encoding="utf-8") as fh:
        eligibility = {r["patient_id"]: r for r in map(json.loads, fh)}
    pool = [p for p in patients if eligibility[p["patient_id"]]["status"] != "INELIGIBLE"]
    plan, randomization = accrual_plan(spec), randomization_plan(spec)
    pool_strata = np.array([stratum_of(randomization["strata"], p) for p in pool])
    curve = success_curve(spec, model, pool_strata, plan, randomization, replicates, seed)
    checks = design_checks(curve, model, spec)
    analysis = next(a for a in spec["analyses"] if a.get("primary"))
    phases = treatment_phases(spec)
    examples = {}
    for sc in plan["scenarios"]:
        with open(Path(cohorts_lock) / f"cohort_{sc['scenario']}.jsonl", encoding="utf-8") as fh:
            cohort = [json.loads(line) for line in fh]
        for hr in [1.0] + [round(a["hr"], 4) for a in model["effect"]["design_alternatives"][:1]]:
            rng = np.random.default_rng([seed, 99, int(hr * 10000)])
            trial = simulate_trial(cohort, model, hr, rng, phases)
            examples[f"{sc['scenario']}__hr_{hr:g}"] = registry_record(trial, primary_analysis(trial, analysis), model, spec, randomization, rng)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"results_version": RESULTS_VERSION, "seed": seed, "replicates": replicates,
           "inputs": {"studyspec": spec_record["files"]["studyspec.json"], **{k: v["files"] for k, v in records.items()},
                      "outcome_model": verify(outcomes_lock)["files"]["outcome_model.json"]},
           "effect_definition": model["effect"]["definition"], "asset_prior": {k: model["effect"]["asset_prior"].get(k) for k in
                                                                            ("status", "comparisons", "hr_median", "hr_predictive_95", "decision", "note")},
           "success_curve": curve, "design_checks": checks, "registry_examples": examples}
    (out_dir / "trial_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=_json), encoding="utf-8")
    (out_dir / "results_report.md").write_text(_report(doc, model), encoding="utf-8")
    return {"scenarios": {k: [(r["hr"], round(r["p_success"], 3)) for r in v] for k, v in curve.items()}, "design_checks": checks}


def _json(x):
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    return str(x)


def _report(doc: dict, model: dict) -> str:
    lines = [f"# Simulated trial results ({doc['results_version']})", "",
             f"{doc['replicates']} complete simulated trials per accrual scenario and true effect (seed {doc['seed']}).",
             f"True effect: {doc['effect_definition']}. The protocol's design hypothesis is never used as the truth.",
             f"Asset evidence on the effect: {doc['asset_prior']['decision']} ({doc['asset_prior']['comparisons']} comparisons).", "",
             "## Probability of success of the primary analysis by true hazard ratio", ""]
    names = list(doc["success_curve"])
    lines.append("| true HR | " + " | ".join(names) + " |")
    lines.append("| ---: | " + " | ".join("---:" for _ in names) + " |")
    for i, row in enumerate(doc["success_curve"][names[0]]):
        cells = [f"{doc['success_curve'][n][i]['p_success']:.3f} ± {doc['success_curve'][n][i]['mc_se']:.3f}" for n in names]
        lines.append(f"| {row['hr']:.3f} | " + " | ".join(cells) + " |")
    lines += ["", "## Checks against the protocol's own design", ""]
    for c in doc["design_checks"]:
        lines.append(f"- {c['scenario']}: {c['check']}: simulated {c['simulated']:.3f} ± {c['mc_se']:.3f}"
                     + (f" (protocol claims at least {c['protocol_claims_at_least']})" if c.get("protocol_claims_at_least") is not None else "")
                     + (f" (expected {c['expected']}, consistent: {c['consistent']})" if "expected" in c else "")
                     + (f" - consistent: {c['consistent']}" if "consistent" in c and "expected" not in c else "")
                     + (f" - {c['note']}" if c.get("note") else ""))
    lines += ["", "## Stated limitations", "",
              f"- {model['assessment_timing']}", f"- {model['efs_origin']}",
              "- Strata are unresolved for enrolled subjects, so the stratified log-rank test runs unstratified.",
              "- Only the randomized arms open in this protocol version are simulated.",
              "- Secondary endpoints are UNRESOLVED: no source quantifies them.",
              "- Adverse events come from adult class-level evidence and are identical in distribution for both arms."]
    return "\n".join(lines) + "\n"
