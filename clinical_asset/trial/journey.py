"""The longitudinal patient journey: screening -> treatment cycles (dosing, laboratory tests, adverse events, dose
holds and reductions, tumour assessments) -> end of treatment -> safety and survival follow-up.

Inputs are locked stages only: the StudySpec (rules, doses, schedule), the protocol's schedule facts, the enrolled
cohort, the eligibility result, the patient-level adverse events of the outputs stage (which events each patient has,
already calibrated to the safety asset and the any-serious-event estimate), the safety stage's arm features and the
outcome model. The journey adds WHEN and HOW: onset, grade, resolution, the protocol's dose modifications, exposure,
laboratory values during events, progression detected at scheduled tumour assessments, and withdrawal.

Every trace event names its source and evidence level; every assumption is one of patient_state.ASSUMPTIONS.
"""

import csv
import json
import math
from pathlib import Path

import numpy as np

from . import dose_modification as dm
from . import labs
from .journey_evidence import (ae_discontinuation_probability, death_probability, progression_model, registry_phase,
                               withdrawal_probability)
from .patient_state import ASSUMPTIONS, PatientState, sourced
from .visits import calendar, planned_doses, schedule

JOURNEY_VERSION = "journey-1.1.0"
DAY = 365.25


def _t(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


REPORTING_WINDOW_DAYS = 30
REFERENCE_PARTICIPATION_DAYS = 365


def arm_agents(spec: dict, sched: dict, arm_id: str) -> list[str]:
    """The agents given in one arm: arm references are resolved once by visits.schedule (clinical_asset.trial.arms, L019)."""
    return [agent for agent, a in sched["agents"].items() if arm_id in a.get("arm_ids", [])]


def _dose_text(d: dict | None) -> str:
    if not d:
        return "dose not compiled"
    if d.get("value") is None:
        return d.get("label") or "reduced (level not stated)"
    return f"{d['value']:g} {d.get('unit') or ''}".strip()


def _reduce(st, agent: str, levels: dict, rules: list[dict], day: int, why: str) -> list[str]:
    """One dose reduction: the protocol's dose level for the new reduction count (else unstated), the dose history, and
    the protocol's limit on the number of reductions."""
    st.reductions[agent] += 1
    lvl = (levels.get(agent) or {}).get(st.reductions[agent])
    st.dose[agent] = {"value": lvl["value"], "unit": lvl["unit"]} if lvl else {"value": None, "label": f"reduced x{st.reductions[agent]} (level not stated)"}
    st.dose_history.append((day, agent, dict(st.dose[agent])))
    out = [f"{agent} reduced to {_dose_text(st.dose[agent])} from day {day} ({why})"]
    chk = dm.decide(rules, agent, {"term": "", "grade": 0}, {"reductions": st.reductions[agent], "held_days": 0})
    if chk["action"] in ("discontinue_agent", "discontinue_all"):
        st.discontinued[agent] = (day, f"{chk['rule_id']}: more reductions than the protocol allows")
        out.append(f"{agent} discontinued ({chk['rule_id']}: {st.reductions[agent]} reductions)")
    return out


def dose_on(st, agent: str, day: int, initial: dict | None) -> dict | None:
    d = initial
    for dd, a, dose in st.dose_history:
        if a == agent and dd <= day:
            d = dose
    return d


def simulate_patient(subject: dict, ae_rows: list[dict], eligibility: dict | None, spec: dict, sched: dict, rules: list[dict],
                     levels: dict, prog: dict, withdraw: dict, rng: np.random.Generator, horizon_days: int,
                     ae_stop: dict | None = None, death: dict | None = None) -> PatientState:
    st = PatientState(subject_id=subject["subject_id"], arm_id=subject["arm_id"], enrollment_day=subject["enrollment_day"],
                      baseline=subject["baseline"])
    agents = arm_agents(spec, sched, subject["arm_id"])
    arm_label = next((_t(a["label"]) for a in spec["arms"] if a["arm_id"] == subject["arm_id"]), "") or ""
    first = {}
    for a in agents:
        plan = planned_doses(sched["agents"][a], arm_label, 1)
        first[a] = plan[0] if plan else None
        st.dose[a] = dict(plan[-1][1]) if plan else (dict(sched["agents"][a]["dose"]["value"]) if sched["agents"][a]["dose"]["value"] else None)
        st.reductions[a] = 0

    # ---------------------------------------------------------------- screening and baseline
    win = sched["screening_window_days"]
    sday = -int(win["value"]) if win["value"] else -1
    b = subject["baseline"]
    age = (b.get("demographic:age") or {}).get("value")
    st.log(sday, "SCREENING", "screening", "eligibility",
           (eligibility or {}).get("status", "not evaluated"),
           f"{len((eligibility or {}).get('unknown', []))} criteria not checkable with generated variables",
           evidence_level="protocol", source="eligibility stage (three-valued: eligible / ineligible / undetermined)")
    if win["value"]:
        st.events[-1]["assumption"] = "A13_screening_day"
    st.log(sday, "SCREENING", "baseline", "demographics", f"age {age}, {b.get('demographic:sex')}, {b.get('demographic:race')}",
           evidence_level="evidence", source="population stage (V3 baseline parameters within the protocol's age limits)")
    for code in ("anc", "platelets", "hemoglobin", "alt", "creatinine"):
        n = labs.normal(code)
        st.log(sday, "SCREENING", "laboratory", n["value"]["test"], "within normal limits (value not simulated: no evidence)",
               evidence_level=n["evidence_level"], source=n["source"], assumption=n["assumption"])
    for a in agents:
        f = first[a]
        entry = next((e for e in sched["agents"][a]["entries"] if f and e["intervention_id"] == f[2]), sched["agents"][a])
        st.log(f[0] if f else 1, f"C1D{f[0] if f else 1}", "treatment", f"start {a}", _dose_text(f[1] if f else st.dose[a]),
               "first dose" + (f"; then {_dose_text(st.dose[a])} (the protocol's target dose)" if f and f[1] != st.dose[a] else ""),
               evidence_level="protocol", source=f"intervention {entry['intervention_id']}", quote=entry["dose"].get("quote"))

    # ---------------------------------------------------------------- latent times
    prog_day = None
    if prog["value"]:
        from .outcomes import sample_efs_years
        y = float(sample_efs_years(1, {"cure_fraction": prog["value"]["cure_fraction"], "failure_rate_per_year": prog["value"]["rate_per_year"]},
                                   1.0, rng)[0])
        prog_day = int(math.ceil(y * DAY)) + 1 if math.isfinite(y) else None
    st.progression_day = prog_day
    cycle = sched["cycle_length_days"]["value"] or 28
    max_c = sched["max_cycles"]["value"]
    plan_end = int(min(horizon_days, max_c * cycle if max_c else horizon_days))
    scale, end_label = 1.0, "completed planned treatment" if max_c else "end of simulated follow-up"
    if sched["cycle_length_days"]["value"] is None and not max_c:
        # no treatment cycles (e.g. single administrations at scan visits): participation ends after the last planned
        # administration plus the reporting window, and the registry's whole-trial exit shares are scaled to it (A22, L035)
        days = [d for a in agents for d in (sched["agents"][a]["dosing_days"]["value"] or [])]
        plan_end = int(max(days)) if days else 1
        horizon_days = plan_end + REPORTING_WINDOW_DAYS
        scale, end_label = min(1.0, horizon_days / REFERENCE_PARTICIPATION_DAYS), "completed planned procedures"
    withdraw_day = int(rng.integers(1, plan_end + 1)) if withdraw["value"] and rng.random() < withdraw["value"] * scale else None
    # registry competing exits (L021): treatment stopped for an adverse event (A14), death in the study period (A15)
    ae_stop_day = int(rng.integers(1, plan_end + 1)) if ae_stop and ae_stop["value"] and rng.random() < ae_stop["value"] * scale else None
    death_day = int(rng.integers(1, horizon_days + 1)) if death and death["value"] and rng.random() < death["value"] * scale else None
    st.death_day = death_day
    if death_day is not None and prog_day is not None and prog_day >= death_day:
        prog_day = st.progression_day = None                 # no progression after death

    visits = calendar(sched, horizon_days)
    ta_days = [v["day"] for v in visits if "tumour assessment" in v["planned"]]
    visit_days = sorted({v["day"] for v in visits})

    def next_visit(day, k=1):
        later = [d for d in visit_days if d > day]
        return later[k - 1] if len(later) >= k else day + 7 * k

    detect = None
    if prog_day is not None:
        if ta_days and sched["tumour_assessment_interval_days"]["value"]:
            detect = next((d for d in ta_days if d >= prog_day), None)
        else:
            detect = prog_day
    end_candidates = [(plan_end, end_label)]
    if detect is not None and end_label == "completed planned procedures" and detect > plan_end:
        detect = None                                   # progression after the last procedure is outside participation
    if detect is not None:
        end_candidates.append((detect, "disease progression"))
    if withdraw_day is not None:
        end_candidates.append((withdraw_day, "withdrawal (subject, loss to follow-up or physician decision)"))
    if ae_stop_day is not None:
        end_candidates.append((ae_stop_day, "adverse event (registry discontinuation rate)"))
    if death_day is not None:
        end_candidates.append((death_day, "death"))
    off_day, off_reason = min(end_candidates)

    # ---------------------------------------------------------------- adverse events: onset, grade, resolution
    reporting_end = off_day + 30
    aes = []
    for r in ae_rows:
        onset = int(rng.integers(1, max(2, reporting_end + 1)))
        serious = r["AESER"] == "Y"
        grade = 3 if serious else int(rng.integers(1, 3))
        aes.append({"term": r["AETERM"], "serious": serious, "grade": grade, "onset": onset, "source": r.get("SOURCE")})
    aes.sort(key=lambda e: e["onset"])

    # ---------------------------------------------------------------- walk the timeline
    dropped = 0
    ae_out = []
    for e in aes:
        if e["onset"] > (st.off_treatment[0] if st.off_treatment else off_day) + 30 or (death_day is not None and e["onset"] > death_day):
            dropped += 1
            continue
        e["end"] = next_visit(e["onset"], 1 if e["grade"] <= 2 else 2)
        visit_name = next((v["name"] for v in visits if v["day"] >= e["onset"]), "unscheduled")
        consequence = []
        on_tx = st.off_treatment is None and e["onset"] <= off_day
        if on_tx:
            for a in list(st.active_agents()):
                d = dm.decide(rules, a, {"term": e["term"], "grade": e["grade"]}, {"reductions": st.reductions.get(a, 0), "held_days": 0})
                e.setdefault("decisions", {})[a] = d
                act = d["action"]
                if act in ("hold", "delay_cycle"):
                    start = e["onset"]
                    resume_day = next_visit(e["end"] - 1)             # treatment resumes at the first visit after resolution
                    st.holds.append((a, start, resume_day))
                    st.held_since[a] = start
                    consequence.append(f"{a} held until day {resume_day} ({d['rule_id']})")
                    if d.get("resume") in ("reduce_to_dose", "reduce_percent"):
                        consequence += _reduce(st, a, levels, rules, resume_day, f"resumed reduced ({d['rule_id']})")
                    chk = dm.decide(rules, a, {"term": "", "grade": 0}, {"reductions": st.reductions[a], "held_days": resume_day - start})
                    if chk["action"] in ("discontinue_agent", "discontinue_all"):
                        st.discontinued[a] = (resume_day, f"{chk['rule_id']}: interruption beyond the protocol limit")
                        consequence.append(f"{a} discontinued ({chk['rule_id']}: interruption {resume_day - start} days)")
                elif act in ("reduce_to_dose", "reduce_percent"):
                    consequence += _reduce(st, a, levels, rules, e["onset"], d["rule_id"])
                elif act in ("discontinue_agent", "discontinue_all"):
                    st.discontinued[a] = (e["onset"], f"{d['rule_id']}: {e['term']} grade {e['grade']}")
                    consequence.append(f"{a} discontinued ({d['rule_id']})")
                elif act == "no_modification":
                    consequence.append(f"{a} continued ({d['rule_id']})")
                if d["undecidable"]:
                    consequence.append(f"undecidable: {','.join(d['undecidable'][:3])}")
            if agents and not st.active_agents() and st.off_treatment is None:
                st.off_treatment = (max(e["onset"], min(x[0] for x in st.discontinued.values())), "adverse event (all agents discontinued)")
        src = e["source"] or "safety asset"
        st.log(e["onset"], visit_name, "adverse event", e["term"], f"grade {e['grade']}{' serious' if e['serious'] else ''}; resolves by day {e['end']}",
               "; ".join(consequence) if consequence else ("after treatment" if not on_tx else "no protocol rule applies"),
               evidence_level="parameter", source=f"occurrence: {src}; onset A1, grade A2, resolution A3",
               assumption="A1_ae_onset")
        code = labs.test_of(e["term"])
        if code:
            lv = labs.value(code, e["grade"], rng)
            st.log(e["onset"], visit_name, "laboratory", lv["value"]["test"], f"{lv['value']['value']:g} {lv['value']['unit']} (grade {e['grade']})",
                   f"during {e['term']}", evidence_level=lv["evidence_level"], source=lv["source"], assumption=lv["assumption"])
        ae_out.append(e)

    if st.off_treatment is None:
        st.off_treatment = (off_day, off_reason)
    off_day, off_reason = st.off_treatment

    # ---------------------------------------------------------------- exposure by cycle
    exposure = []
    if cycle:
        c = 0
        while c * cycle + 1 <= off_day and (max_c is None or c < max_c):
            start, end = int(c * cycle) + 1, int(min((c + 1) * cycle, off_day))
            for a in agents:
                plan = [(start + d - 1, dose) for d, dose, _ in planned_doses(sched["agents"][a], arm_label, c + 1) if start + d - 1 <= end]
                planned_days = [d for d, _ in plan]
                if not planned_days:
                    continue
                disc = st.discontinued.get(a)
                given = [d for d in planned_days if not (disc and d >= disc[0])
                         and not any(h[0] == a and h[1] <= d < h[2] for h in st.holds)]
                doses = sorted({_dose_text(dose_on(st, a, d, dose) if any(dd <= d for dd, aa, _ in st.dose_history if aa == a) else dose)
                                for d, dose in plan if d in given}) or [_dose_text(plan[0][1])]
                exposure.append({"cycle": c + 1, "agent": a, "planned_administrations": len(planned_days), "administrations": len(given),
                                 "dose": " then ".join(doses) if len(doses) <= 2 else ", ".join(doses)})
                if len(given) < len(planned_days):
                    st.log(start, f"C{c + 1}D1", "treatment", a, f"{len(given)}/{len(planned_days)} planned administrations",
                           "interrupted or discontinued", evidence_level="protocol", source="protocol dosing schedule and dose-modification rules")
            c += 1

    # ---------------------------------------------------------------- tumour assessments, end of treatment, follow-up
    for k, d in enumerate([d for d in ta_days if d <= off_day + 1], 1):
        pd = prog_day is not None and d >= prog_day
        st.log(d, f"TA{k}", "tumour assessment", "RECIST / protocol response criteria",
               "progressive disease" if pd else "no progression (response category not simulated)",
               "progression detected: treatment ends" if pd else "continue",
               evidence_level=prog["evidence_level"], source=f"latent progression time: {prog['source']}; detected at scheduled assessment",
               **({"assumption": prog["assumption"]} if prog.get("assumption") else {}))
        if pd:
            st.progression_detected_day = d
            break
    if st.progression_detected_day is None and prog_day is not None and not ta_days and prog_day <= off_day + 1:
        st.progression_detected_day = prog_day
        st.log(prog_day, "unscheduled", "tumour assessment", "progression", "progressive disease",
               "no tumour assessment schedule resolved: recorded at its true time", evidence_level=prog["evidence_level"], source=prog["source"])
    registry_exit = {"withdrawal": (withdraw, None), "registry discontinuation": (ae_stop, "A14_ae_discontinuation"),
                     "death": (death, "A15_death_timing")}
    hit = next((v for k, v in registry_exit.items() if k in off_reason and v[0]), None)
    st.log(off_day, "EOT", "disposition", "end of treatment", off_reason, evidence_level="evidence" if hit else "protocol",
           source=hit[0]["source"] if hit else "protocol discontinuation rules", **({"assumption": hit[1]} if hit and hit[1] else {}))
    fu = sched["follow_up_interval_days"]
    if fu["value"] and (death_day is None or off_day + int(fu["value"]) < death_day):
        st.log(off_day + int(fu["value"]), "FU1", "follow-up", "follow-up visit", "attended", evidence_level="protocol", source=fu["source"])
    if death_day is not None and death_day > off_day:
        st.log(death_day, "follow-up", "disposition", "death", "died during follow-up", evidence_level="evidence",
               source=death["source"], assumption="A15_death_timing")
    st.events.sort(key=lambda e: (e["day"], e["category"] != "screening"))
    st.ae = ae_out
    st.exposure = exposure
    st.dropped_after_off_treatment = dropped
    st.agents = agents
    return st


def run(spec_lock: Path, cohorts_lock: Path, eligibility_lock: Path, outputs_lock: Path, safety_lock: Path, outcomes_lock: Path,
        schedule_facts: Path | None, out_dir: Path, scenario: str | None = None, horizon_days: int = 730, seed: int = 20260929,
        traces: int = 3, facts_lock: Path | None = None) -> dict:
    from .lock import verify
    from .studyspec import load_facts, load_studyspec

    spec, spec_rec = load_studyspec(spec_lock)
    protocol_facts = load_facts(facts_lock)[0] if facts_lock else None
    for lk in (cohorts_lock, eligibility_lock, outputs_lock, safety_lock, outcomes_lock):
        verify(lk)
    facts = json.loads(Path(schedule_facts).read_text(encoding="utf-8")) if schedule_facts and Path(schedule_facts).exists() else None
    sched = schedule(spec, facts)
    rules = dm.compile_rules(spec)
    levels = dm.dose_levels(rules)
    if scenario is None:                        # the recruitment stage's headline scenario (the historical model, L024)
        rs = Path(cohorts_lock) / "recruitment_summary.json"
        scenario = json.loads(rs.read_text(encoding="utf-8"))["summary"].get("headline_scenario") if rs.exists() else None
    cohort_file = sorted(Path(cohorts_lock).glob(f"cohort_{scenario or '*'}.jsonl"))[0]
    cohort = [json.loads(line) for line in open(cohort_file, encoding="utf-8")]
    elig = {}
    with open(Path(eligibility_lock) / "eligibility.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            elig[r["patient_id"]] = r
    ae_by: dict = {}
    with open(Path(outputs_lock) / "adae.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ae_by.setdefault(r["USUBJID"], []).append(r)
    safety = json.loads((Path(safety_lock) / "safety_results.json").read_text(encoding="utf-8"))
    feats = {a["arm_id"]: ((a.get("safety_v3") or {}).get("features") or {}) for a in safety["arms"]}
    model = json.loads((Path(outcomes_lock) / "outcome_model.json").read_text(encoding="utf-8"))
    phase = registry_phase(spec)
    rng = np.random.default_rng(seed)
    states, prog_by_arm, wd_by_arm, ae_by_arm, death_by_arm = [], {}, {}, {}, {}
    from . import subgroup_evidence as sge

    sg_evidence = sge.load(cohorts_lock)              # the protocol's subgroup factors and their prognostic effects (A28)
    for s in cohort:
        arm = s["arm_id"]
        if arm not in prog_by_arm:
            f = feats.get(arm) or next(iter(feats.values()), {})
            prog_by_arm[arm] = progression_model(model, f, spec, protocol_facts, arm)
            wd_by_arm[arm] = withdrawal_probability(f.get("disease_family"), phase)
            ae_by_arm[arm] = ae_discontinuation_probability(f.get("disease_family"), phase)
            death_by_arm[arm] = death_probability(f.get("disease_family"), phase)
        prog = prog_by_arm[arm]
        log_hr = sge.patient_log_effects(s["baseline"], sg_evidence)[0]
        if log_hr and (prog.get("value") or {}).get("rate_per_year"):
            prog = {**prog, "value": {**prog["value"], "rate_per_year": prog["value"]["rate_per_year"] * math.exp(log_hr)}}
        states.append(simulate_patient(s, ae_by.get(s["subject_id"], []), elig.get(s["patient_id"]), spec, sched, rules, levels,
                                       prog, wd_by_arm[arm], rng, horizon_days, ae_by_arm[arm], death_by_arm[arm]))
    from .export_clinical import write
    from .journey_evidence import screen_pass_rate
    summary = write(states, spec, sched, out_dir, traces)
    # screening funnel: what the generated population can decide, and the registry's screened -> enrolled pass rate
    el = json.loads((Path(eligibility_lock) / "eligibility_summary.json").read_text(encoding="utf-8"))["summary"]
    fam = next((f.get("disease_family") for f in feats.values() if f.get("disease_family")), None)
    pr = screen_pass_rate(fam, phase)
    target = max((x["value"] for x in spec.get("sample_size") or [] if x["quantity"] in ("maximum_accrual", "target_accrual") and x.get("value")), default=None)
    funnel = {"generated_patients": el["patients"], "status_counts": el["status_counts"],
              "not_ruled_out_share": round(1 - el["status_counts"].get("INELIGIBLE", 0) / el["patients"], 4),
              "undecidable_criteria": sorted({c for c, v in el["per_criterion"].items() if v.get("unknown")}),
              "screen_pass_rate": pr, "target": target}
    if pr["value"] and target:
        lo, hi = pr["detail"]["single_trial_80"]
        funnel["patients_to_screen"] = {"estimate": math.ceil(target / pr["value"]), "range_80": [math.ceil(target / hi), math.ceil(target / lo)],
                                        "basis": "target / registry pass rate (the range is for a single new trial)"}
    summary["screening_funnel"] = funnel
    doc = {"journey_version": JOURNEY_VERSION, "seed": seed, "horizon_days": horizon_days, "cohort_file": cohort_file.name,
           "inputs": {"studyspec": spec_rec["files"]["studyspec.json"], "schedule_facts": facts.get("version") if facts else None},
           "schedule": sched, "dose_levels": levels, "progression": prog_by_arm, "withdrawal": wd_by_arm,
           "ae_discontinuation": ae_by_arm, "death": death_by_arm,
           "assumptions": ASSUMPTIONS, "summary": summary}
    (Path(out_dir) / "journey_summary.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return doc
