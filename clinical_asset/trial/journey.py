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
    hazard = withdraw.get("per_visit_hazard") if withdraw else None       # burden-dependent withdrawal (L064)
    if hazard is None:
        withdraw_day = int(rng.integers(1, plan_end + 1)) if withdraw["value"] and rng.random() < withdraw["value"] * scale else None
    else:
        withdraw_day = None                   # drawn below, visit by visit, among the visits the patient attends
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
    if detect is not None and end_label == "completed planned procedures":
        # a procedure-only study (no treatment cycles, e.g. paired imaging): disease progression is not a reason to stop
        # the planned procedures, inside or after them (L044); withdrawal, adverse-event and death exits still apply
        detect = None
    if detect is not None:
        end_candidates.append((detect, "disease progression"))
    if hazard:
        # each attended on-treatment visit carries the per-visit withdrawal hazard; visits stop at any earlier exit
        off_other = min(end_candidates + [(ae_stop_day, "")] * (ae_stop_day is not None) + [(death_day, "")] * (death_day is not None))[0]
        wrng = withdraw.get("rng") or rng
        withdraw_day = next((d for d in visit_days if 1 <= d <= off_other and wrng.random() < hazard), None)
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
    st.attended = [(v["day"], v["name"], list(v["planned"])) for v in visits if 1 <= v["day"] <= off_day]
    withdrew = off_reason.startswith("withdrawal")
    if hazard is None:
        if fu["value"] and (death_day is None or off_day + int(fu["value"]) < death_day):
            st.log(off_day + int(fu["value"]), "FU1", "follow-up", "follow-up visit", "attended", evidence_level="protocol", source=fu["source"])
            st.attended.append((off_day + int(fu["value"]), "FU1", ["follow-up visit"]))
    elif fu["value"] and not withdrew:
        # follow-up visits at the protocol's interval until death, withdrawal or the end of the simulated horizon; each
        # attended visit carries the same per-visit withdrawal hazard (L064)
        k, d = 1, off_day + int(fu["value"]) * (1 + int(sched.get("follow_up_skip") or 0))   # a scenario may drop the first visit(s)
        wrng = withdraw.get("rng") or rng
        while d <= horizon_days and (death_day is None or d < death_day):
            if wrng.random() < hazard:
                st.off_study = (d, "withdrawal from follow-up (subject, loss to follow-up or physician decision)")
                st.log(d, f"FU{k}", "disposition", "withdrawal", "withdrew from follow-up", "no further visits or data",
                       evidence_level="evidence", source=withdraw.get("source"))
                break
            st.log(d, f"FU{k}", "follow-up", "follow-up visit", "attended", evidence_level="protocol", source=fu["source"])
            st.attended.append((d, f"FU{k}", ["follow-up visit"]))
            k, d = k + 1, d + int(fu["value"])
    if withdrew and hazard is not None:
        st.off_study = (off_day, off_reason)
    # the visits the protocol requires given the disease course (completion, progression, adverse-event stops), and
    # what happened at each: attended, or not attended because the participant had withdrawn or died (L066). No
    # evidence supports further operational missingness (missed visits among those on study): it is zero, not modelled.
    ends = [plan_end] + [x for x in (detect, ae_stop_day) if x is not None] + ([off_day] if off_reason.startswith("adverse event") else [])
    req_end = off_day if not (withdrew or off_reason == "death") else min(ends)
    required = [(v["day"], v["name"], list(v["planned"])) for v in visits if 1 <= v["day"] <= req_end]
    if fu["value"]:
        k, d = 1, req_end + int(fu["value"]) * (1 + int(sched.get("follow_up_skip") or 0))
        while d <= horizon_days:
            required.append((d, f"FU{k}", ["follow-up visit"]))
            k, d = k + 1, d + int(fu["value"])
    seen = {d for d, _, _ in st.attended}
    left_day = st.off_study[0] if st.off_study else None
    st.required = [(d, name, planned, "attended" if d in seen else
                    "not attended: died" if death_day is not None and d >= death_day else
                    "not attended: withdrew" if left_day is not None and d >= left_day else "not attended")
                   for d, name, planned in required]
    left = st.off_study[0] if st.off_study else None
    if death_day is not None and left is not None and death_day > left:
        st.death_day = death_day = None       # a death after the participant left the study is not observed (L064)
    if death_day is not None and death_day > off_day:
        st.log(death_day, "follow-up", "disposition", "death", "died during follow-up", evidence_level="evidence",
               source=death["source"], assumption="A15_death_timing")
    st.events.sort(key=lambda e: (e["day"], e["category"] != "screening"))
    st.ae = ae_out
    st.exposure = exposure
    st.dropped_after_off_treatment = dropped
    st.agents = agents
    return st


def person_level_exits(states: list, cohort: list[dict]) -> int:
    """Within-patient designs (one record per period of the same person): a participant who leaves the study in a
    period (adverse event, withdrawal, death; anything but completion) does not start the later periods. Those records
    keep the person's death day and carry no exposure or adverse events (L044). Returns the records changed."""
    period = {c["subject_id"]: (c.get("patient_subject"), c.get("period") or 0) for c in cohort}
    by_person: dict = {}
    for st in states:
        person, k = period.get(st.subject_id, (None, 0))
        if person:
            by_person.setdefault(person, []).append((k, st))
    changed = 0
    for recs in by_person.values():
        left = None
        for k, st in sorted(recs, key=lambda x: x[0]):
            if left is not None:
                st.off_treatment = (0, f"not started: left the study in period {left[0]} ({left[1]})")
                st.exposure, st.ae, st.holds, st.reductions = [], [], [], {}
                st.events = [e for e in st.events if e["day"] <= 0]
                st.death_day, st.progression_day, st.progression_detected_day = left[2], None, None
                changed += 1
                continue
            reason = (st.off_treatment or (0, "completed"))[1]
            if not reason.startswith("completed"):
                left = (k, reason, st.death_day)
    return changed


def burden_withdrawal(ctx: dict, sched: dict, family: str | None) -> dict | None:
    """The protocol's trial-level withdrawal share from the registry burden model (L064), or None without the model."""
    from ..planning.report import protocol_start_year, sponsor_class
    from . import withdrawal_burden as wb

    model = wb.load()
    if not model:
        return None
    spec = ctx["spec"]
    feats = wb.protocol_features(spec, sched, family, ctx["phase"], len(ctx["cohort"]), protocol_start_year(spec),
                                 sponsor_class(spec).get("value") == "INDUSTRY", len(spec.get("arms") or []) > 1, REPORTING_WINDOW_DAYS)
    pred = wb.predict(model, feats)
    out = sourced(pred["share"], "evidence", f"registry protocol-burden model {model['version']} ({model['trials']} trials): "
                  "withdrawal predicted from this protocol's participation duration, visit frequency, assessment count, phase, "
                  "disease family, enrolment, start year, sponsor class and randomisation")
    out["detail"] = {"ci95": pred["ci95"], "features": {k: v for k, v in feats.items() if k != "definitions"},
                     "definitions": feats["definitions"], "visit_frequency_log_or": model["coefficients"]["log2_visits_per_month"]["log_odds"]}
    return out


def _simulate_all(ctx: dict, sched: dict, horizon_days: int, rng, wd: dict, prog_by_arm: dict, ae_by_arm: dict, death_by_arm: dict,
                  hazard_by_arm: dict | None, seed_base: int = 0) -> list:
    from . import patient_risk
    from . import subgroup_evidence as sge

    states = []
    # one stream per patient, drawn from the cohort stream: a patient's disease course does not depend on how many random
    # numbers earlier patients used (common random numbers across schedule scenarios, L064)
    pseeds = rng.integers(0, 2 ** 32, size=len(ctx["cohort"])) if hazard_by_arm is not None else None
    for i, s in enumerate(ctx["cohort"]):
        arm = s["arm_id"]
        prog = prog_by_arm[arm]
        log_hr = sge.patient_log_effects(s["baseline"], ctx["sg"])[0]
        # exits by the patient's own risk (L055): the arm's evidence probability moved by age, sex and ECOG
        own = {}
        for kind, d in (("withdrawal", wd[arm]), ("ae_discontinuation", ae_by_arm[arm]), ("death", death_by_arm[arm])):
            v = (d or {}).get("value")
            own[kind] = {**d, "value": patient_risk.adjust(v, patient_risk.shift(ctx["risk"], kind, s["baseline"]))} if v else d
        if hazard_by_arm is not None:
            base = wd[arm].get("value") or 0.0
            mult = own["withdrawal"]["value"] / base if base and own["withdrawal"].get("value") else 1.0
            # withdrawal draws from the patient's own stream: every schedule scenario keeps the same disease courses
            # (common random numbers), so scenario differences are the schedule's, not simulation noise
            own["withdrawal"] = {**own["withdrawal"], "per_visit_hazard": min(0.5, hazard_by_arm[arm] * mult),
                                 "rng": np.random.default_rng([seed_base, int.from_bytes(s["subject_id"].encode()[-6:], "big")])}
        if log_hr and (prog.get("value") or {}).get("rate_per_year"):
            prog = {**prog, "value": {**prog["value"], "rate_per_year": prog["value"]["rate_per_year"] * math.exp(log_hr)}}
        states.append(simulate_patient(s, ctx["ae_by"].get(s["subject_id"], []), ctx["elig"].get(s["patient_id"]), ctx["spec"], sched,
                                       ctx["rules"], ctx["levels"], prog, own["withdrawal"],
                                       np.random.default_rng(int(pseeds[i])) if pseeds is not None else rng, horizon_days, own["ae_discontinuation"],
                                       own["death"]))
    return states


def visits_per_patient_month(states: list, horizon_days: int) -> float:
    """Attended visits per patient-month of participation, from the first dose to death or the end of the simulated
    follow-up (the pilot pass has no withdrawal): a schedule with fewer visits lowers it."""
    days = sum(min(s.death_day or horizon_days, horizon_days) for s in states)
    return sum(len(s.attended) for s in states) / (days / 30.44) if days else 0.0


def simulate_cohort(ctx: dict, sched: dict, horizon_days: int, seed: int, withdrawal_logit_shift: float = 0.0, return_pilot: bool = False,
                    reference_visit_rate: float | None = None) -> tuple:
    """The cohort's journeys. With the registry burden model, withdrawal is the protocol's predicted trial-level share
    distributed over the visits each patient attends: a pilot pass without withdrawal gives every patient's attended
    visits, and the per-visit hazard is solved so that the expected share withdrawing equals the predicted share (L064).
    A schedule scenario passes `reference_visit_rate` (the original schedule's visits per patient-month): its predicted
    share moves by the registry's visit-frequency association for the change in visits per patient-month."""
    prog_by_arm, wd_by_arm, ae_by_arm, death_by_arm = {}, {}, {}, {}
    for s in ctx["cohort"]:
        arm = s["arm_id"]
        if arm in prog_by_arm:
            continue
        f = ctx["feats"].get(arm) or next(iter(ctx["feats"].values()), {})
        prog_by_arm[arm] = progression_model(ctx["model"], f, ctx["spec"], ctx["facts"], arm)
        # the protocol's own burden features (a schedule scenario changes withdrawal only through visits per patient-month)
        wd_by_arm[arm] = burden_withdrawal(ctx, ctx["sched"], f.get("disease_family")) or withdrawal_probability(f.get("disease_family"), ctx["phase"])
        ae_by_arm[arm] = ae_discontinuation_probability(f.get("disease_family"), ctx["phase"])
        death_by_arm[arm] = death_probability(f.get("disease_family"), ctx["phase"])
    burden = all("burden model" in (w.get("source") or "") for w in wd_by_arm.values())
    if not burden:
        rng = np.random.default_rng(seed)
        return _simulate_all(ctx, sched, horizon_days, rng, wd_by_arm, prog_by_arm, ae_by_arm, death_by_arm, None, seed), prog_by_arm, wd_by_arm, ae_by_arm, death_by_arm
    pilot = _simulate_all(ctx, sched, horizon_days, np.random.default_rng(seed), wd_by_arm, prog_by_arm, ae_by_arm, death_by_arm,
                          {a: 0.0 for a in wd_by_arm}, seed)
    rate = visits_per_patient_month(pilot, horizon_days)
    beta_v = next(iter(wd_by_arm.values()))["detail"]["visit_frequency_log_or"]
    shift = withdrawal_logit_shift + (beta_v * math.log2(rate / reference_visit_rate) if reference_visit_rate else 0.0)
    hazard_by_arm = {}
    for arm, w in wd_by_arm.items():
        p = 1 / (1 + math.exp(-(math.log(w["value"] / (1 - w["value"])) + shift)))
        v = np.array([len(st.attended) for st, s in zip(pilot, ctx["cohort"], strict=True) if s["arm_id"] == arm], float)
        lo, hi = 0.0, 0.5
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if float(np.mean(1 - (1 - mid) ** v)) < p else (lo, mid)
        hazard_by_arm[arm] = (lo + hi) / 2
        wd_by_arm[arm] = {**w, "value": p, "detail": {**w["detail"], "per_visit_hazard": hazard_by_arm[arm], "visits_per_patient_month": rate,
                                                     "reference_visits_per_patient_month": reference_visit_rate, "logit_shift": shift,
                                                     "mean_attended_visits_without_withdrawal": float(v.mean())}}
    states = _simulate_all(ctx, sched, horizon_days, np.random.default_rng(seed), wd_by_arm, prog_by_arm, ae_by_arm, death_by_arm, hazard_by_arm, seed)
    if return_pilot:
        return states, prog_by_arm, wd_by_arm, ae_by_arm, death_by_arm, pilot
    return states, prog_by_arm, wd_by_arm, ae_by_arm, death_by_arm


def context_from_locks(nct: str, version: str) -> tuple[dict, dict, int, int]:
    """The locked journey's inputs (the same ones run() used), for schedule scenarios on the same patients."""
    from . import patient_risk
    from . import subgroup_evidence as sge
    from .studyspec import load_facts, load_studyspec

    L = Path("data/locked") / nct
    st = lambda s: L / f"{s}_v{version}"  # noqa: E731
    js = json.loads((st("journey") / "journey_summary.json").read_text(encoding="utf-8"))
    spec, _ = load_studyspec(st("studyspec"))
    ref = (json.loads((st("journey") / "lock.json").read_text(encoding="utf-8")).get("inputs") or {}).get("facts")
    facts_lock = Path(ref["path"]).parent if ref else None          # the facts lock the journey itself used
    sf = st("journey") / "schedule_facts.json"
    sched = schedule(spec, json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else None)
    rules = dm.compile_rules(spec)
    cohort = [json.loads(x) for x in open(st("cohorts") / js["cohort_file"], encoding="utf-8")]
    elig = {}
    with open(st("eligibility") / "eligibility.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            elig[r["patient_id"]] = r
    ae_by: dict = {}
    with open(st("outputs") / "adae.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ae_by.setdefault(r["USUBJID"], []).append(r)
    safety = json.loads((st("safety") / "safety_results.json").read_text(encoding="utf-8"))
    ctx = {"spec": spec, "sched": sched, "rules": rules, "levels": dm.dose_levels(rules), "cohort": cohort, "elig": elig, "ae_by": ae_by,
           "feats": {a["arm_id"]: ((a.get("safety_v3") or {}).get("features") or {}) for a in safety["arms"]},
           "model": json.loads((st("outcomes") / "outcome_model.json").read_text(encoding="utf-8")), "phase": registry_phase(spec),
           "facts": load_facts(facts_lock)[0] if facts_lock and Path(facts_lock).exists() else None, "sg": sge.load(st("cohorts")),
           "risk": patient_risk.load(js["seed"])}
    return ctx, sched, int(js["horizon_days"]), int(js["seed"])


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
    from . import subgroup_evidence as sge

    sg_evidence = sge.load(cohorts_lock)              # the protocol's subgroup factors and their prognostic effects (A28)
    from . import patient_risk
    risk_model = patient_risk.load(seed)              # this replicate's draw of the patient-level effects (L055, L056)
    ctx = {"spec": spec, "sched": sched, "rules": rules, "levels": levels, "cohort": cohort, "elig": elig, "ae_by": ae_by,
           "feats": feats, "model": model, "phase": phase, "facts": protocol_facts, "sg": sg_evidence, "risk": risk_model}
    states, prog_by_arm, wd_by_arm, ae_by_arm, death_by_arm = simulate_cohort(ctx, sched, horizon_days, seed)
    person_level_exits(states, cohort)
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
