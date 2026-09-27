"""Milestones 9, 10, 12, 13 and 14: one simulated run of the trial and its protocol analysis.

For one enrolled cohort (milestone 8), one outcome model (milestone 11) and one true experimental effect:

* M9 time and state: every subject has an enrollment day; accrual stops when the protocol's evaluable target is
  reached (subjects are excluded from the analysis set at the protocol's stated share); the final analysis date
  is the last enrollment plus the protocol's minimum follow-up. Subjects go off study at the protocol's time
  limit or when lost to follow-up (the protocol's annual censoring rate).
* M10 treatment: the executable treatment phases are carried out from enrollment; a subject completes a phase
  when no event, loss or off-study occurs before its end. Phases the locked StudySpec could not compile are
  reported as unresolved, never guessed.
* M12 observation: EFS events are observed at their true time (detection at the next scheduled assessment is
  not applied; the outcome model states this).
* M13 endpoint: EFS from enrollment (the convention chosen for the protocol's unstated origin) to the first
  observed event, censored at loss, off study or the analysis date.
* M14 analysis: the protocol's primary test (log-rank, sidedness and alpha from the StudySpec). Strata that no
  subject can be assigned to (UNRESOLVED) cannot be used and the test is then unstratified; this is reported.
"""

import math

import numpy as np
from scipy import stats

DAY = 365.25


# ----------------------------------------------------------------------------- statistics


def logrank(time: np.ndarray, event: np.ndarray, group: np.ndarray, strata: np.ndarray | None = None) -> dict:
    """Log-rank test of group 1 against group 0 (stratified when strata are given). z < 0 means fewer events than
    expected in group 1, i.e. group 1 does better."""
    if strata is None:
        strata = np.zeros(len(time), dtype=int)
    o_minus_e, var = 0.0, 0.0
    for s in np.unique(strata):
        m = strata == s
        t, d, g = time[m], event[m].astype(bool), group[m].astype(bool)
        order = np.argsort(t, kind="stable")
        t, d, g = t[order], d[order], g[order]
        n = len(t)
        at_risk = n - np.arange(n)
        at_risk_1 = np.cumsum(g[::-1])[::-1]
        _, first = np.unique(t, return_index=True)
        for k, start in enumerate(first):
            end = first[k + 1] if k + 1 < len(first) else n
            deaths = d[start:end].sum()
            if deaths == 0:
                continue
            deaths_1 = (d[start:end] & g[start:end]).sum()
            r, r1 = at_risk[start], at_risk_1[start]
            o_minus_e += deaths_1 - deaths * r1 / r
            if r > 1:
                var += deaths * (r1 / r) * (1 - r1 / r) * (r - deaths) / (r - 1)
    z = o_minus_e / math.sqrt(var) if var > 0 else 0.0
    return {"o_minus_e": o_minus_e, "variance": var, "z": z,
            "p_one_sided_group1_better": float(stats.norm.cdf(z)), "p_two_sided": float(2 * stats.norm.sf(abs(z)))}


def cox_hr(time: np.ndarray, event: np.ndarray, group: np.ndarray, iterations: int = 30) -> dict:
    """Maximum partial likelihood hazard ratio of group 1 vs 0 (Breslow ties), with a Wald 95% interval."""
    order = np.argsort(-time, kind="stable")
    t, d, x = time[order], event[order].astype(bool), group[order].astype(float)
    beta = 0.0
    info = 0.0
    for _ in range(iterations):
        w = np.exp(beta * x)
        s0, s1 = np.cumsum(w), np.cumsum(w * x)
        # risk sets: all subjects with time >= t_i; with descending order and ties, use the last index of each tie
        last = np.searchsorted(-t, -t, side="right") - 1
        s0i, s1i = s0[last][d], s1[last][d]
        score = float(np.sum(x[d] - s1i / s0i))
        info = float(np.sum(s1i / s0i - (s1i / s0i) ** 2))
        if info <= 0:
            break
        step = score / info
        beta += step
        if abs(step) < 1e-9:
            break
    se = 1 / math.sqrt(info) if info > 0 else float("inf")
    return {"hr": math.exp(beta), "ci95": [math.exp(beta - 1.959964 * se), math.exp(beta + 1.959964 * se)], "log_hr": beta, "se": se}


def kaplan_meier(time: np.ndarray, event: np.ndarray, at: list[float]) -> list[float | None]:
    """Kaplan-Meier survival at the given times (None beyond the last observed time)."""
    t, d = np.asarray(time, dtype=float), np.asarray(event, dtype=bool)
    if len(t) == 0:
        return [None for _ in at]
    steps = []
    surv = 1.0
    for u in np.unique(t[d]):
        at_risk = int(np.sum(t >= u))
        deaths = int(np.sum((t == u) & d))
        surv *= 1 - deaths / at_risk
        steps.append((u, surv))
    out = []
    for p in at:
        if p > t.max():
            out.append(None)
            continue
        value = 1.0
        for u, v in steps:
            if u > p:
                break
            value = v
        out.append(value)
    return out


# ----------------------------------------------------------------------------- one trial


def simulate_trial(cohort: list[dict], model: dict, hr: float, rng: np.random.Generator, phases: list[dict]) -> dict:
    """One run from an enrolled cohort (subjects in enrollment order), keeping each subject's record."""
    trial = simulate_arrays(np.array([s["enrollment_day"] for s in cohort]), np.array([s["arm_id"] for s in cohort]),
                            np.array([s["stratum"] for s in cohort]), model, hr, rng, phases)
    n = trial["n_enrolled"]
    trial["subject_ids"] = [s["subject_id"] for s in cohort[:n]]
    trial["baseline"] = [s["baseline"] for s in cohort[:n]]
    return trial


def simulate_arrays(enroll_day: np.ndarray, arm: np.ndarray, strata: np.ndarray, model: dict, hr: float,
                    rng: np.random.Generator, phases: list[dict]) -> dict:
    from .outcomes import sample_efs_years

    rule = model["analysis_rule"]
    control = model["control_arm_id"]
    target = int(rule["evaluable_target"])
    excluded_share = rule.get("excluded_share") or 0.0
    evaluable = rng.random(len(enroll_day)) >= excluded_share
    reached = np.cumsum(evaluable)
    if reached[-1] < target:
        raise ValueError(f"the cohort holds {reached[-1]} evaluable subjects, fewer than the target {target}")
    n = int(np.searchsorted(reached, target) + 1)             # accrual stops when the target is reached
    enroll, arm, strata = enroll_day[:n], arm[:n], strata[:n]
    analysis_day = float(enroll[-1] + rule["min_followup_years"] * DAY)
    experimental = arm != control
    efs = np.where(experimental, sample_efs_years(n, model["control_efs"], hr, rng), sample_efs_years(n, model["control_efs"], 1.0, rng)) * DAY
    ltf = model["loss_to_follow_up"]
    loss = rng.exponential(DAY / ltf["rate_per_year"], size=n) if ltf["status"] == "RESOLVED" else np.full(n, np.inf)
    off_study = (model.get("off_study_limit") or {}).get("days") or np.inf
    admin = analysis_day - enroll
    end = np.minimum.reduce([efs, loss, np.full(n, off_study), admin])
    event = efs <= np.minimum.reduce([loss, np.full(n, off_study), admin])
    reason = np.where(event, "event", np.where(loss <= np.minimum(off_study, admin), "lost_to_follow_up",
                                              np.where(off_study <= admin, "off_study_time_limit", "administrative")))
    treatment = {}
    for ph in phases:
        if ph.get("days") is None:
            treatment[ph["phase_id"]] = {"status": "UNRESOLVED", "reason": ph.get("reason") or "phase not executable in the StudySpec"}
            continue
        treatment[ph["phase_id"]] = {"status": "RESOLVED", "days": ph["days"], "completed": end > ph["days"]}
    return {"n_enrolled": n, "analysis_day": analysis_day, "enroll_day": enroll, "arm": arm, "experimental": experimental,
            "evaluable": evaluable[:n], "time_days": end, "event": event, "reason": reason, "treatment": treatment, "strata": strata}


def primary_analysis(trial: dict, analysis: dict) -> dict:
    """The protocol's primary analysis on the evaluable subjects."""
    m = trial["evaluable"]
    t, e, g = trial["time_days"][m] / DAY, trial["event"][m], trial["experimental"][m].astype(int)
    strata = trial["strata"][m]
    usable_strata = not np.any(strata == "UNRESOLVED")
    lr = logrank(t, e, g, _codes(strata) if usable_strata else None)
    alpha = (analysis.get("alpha") or {}).get("value") or 0.05
    one_sided = analysis.get("sidedness") == "one_sided"
    p = lr["p_one_sided_group1_better"] if one_sided else lr["p_two_sided"]
    success = p < alpha and (lr["z"] < 0)
    cox = cox_hr(t, e, g) if e.sum() > 0 else {"hr": None, "ci95": [None, None]}
    return {"test": analysis.get("test_family"), "stratified": usable_strata, "sidedness": analysis.get("sidedness"), "alpha": alpha,
            "p_value": p, "z": lr["z"], "success": bool(success), "events": int(e.sum()), "evaluable": int(m.sum()),
            "events_by_group": {"control": int(e[g == 0].sum()), "experimental": int(e[g == 1].sum())}, "hr": cox["hr"], "hr_ci95": cox["ci95"],
            "stratification_note": None if usable_strata else "strata unresolved for enrolled subjects: the log-rank test is unstratified"}


def _codes(labels: np.ndarray) -> np.ndarray:
    _, codes = np.unique(labels, return_inverse=True)
    return codes


def treatment_phases(spec: dict) -> list[dict]:
    """Executable treatment phases with their length in days (duration, or cycles x cycle length)."""
    out = []
    for p in sorted(spec["treatment_phases"], key=lambda p: (p.get("sequence_number") or 0, p["phase_id"])):
        days = (p.get("duration") or {}).get("days")
        if days is None and (p.get("cycle_length") or {}).get("days") and (p.get("cycle_count") or {}).get("value"):
            days = p["cycle_length"]["days"] * p["cycle_count"]["value"]
        out.append({"phase_id": p["phase_id"], "name": (p.get("name") or {}).get("text"), "status": p.get("status"),
                    "days": days, "reason": None if p.get("status") == "EXECUTABLE" else f"phase {p['phase_id']} is {p.get('status')} in the StudySpec"})
    # a phase starts when the previous one ends: cumulative end day from enrollment
    total: float | None = 0.0
    for ph in out:
        if total is not None and ph["status"] == "EXECUTABLE" and ph["days"] is not None:
            total += ph["days"]
            ph["days"] = total
        else:
            if total is None and ph["status"] == "EXECUTABLE":
                ph["reason"] = "starts after a phase whose timing is unresolved"
            total = None
            ph["days"] = None
    return out
