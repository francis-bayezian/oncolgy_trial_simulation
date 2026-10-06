"""Clinical datasets from simulated journeys: SDTM-style domains (DM, EX, AE, LB, RS, DS, SV) and ADaM-style analysis
datasets (ADSL, ADAE, ADTTE), plus patient traces (JSON and a readable table) for a few subjects.

Variable names follow CDISC conventions where the meaning is the same; these are simulated data, not submission
datasets, and every record keeps the evidence level of what generated it.
"""

import csv
import json
from pathlib import Path


def _csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _trace_md(st) -> str:
    lines = [f"# Patient trace {st.subject_id} (arm {st.arm_id})", "",
             "Simulated patient. Each row names how it was generated: protocol (StudySpec rule or schedule), evidence (registry), "
             "parameter (fitted asset), assumption (listed in journey_summary.json).", "",
             "| Day | Visit | Category | Item | Result | Clinical consequence | Basis |", "| ---: | --- | --- | --- | --- | --- | --- |"]
    for e in st.events:
        basis = e.get("evidence_level", "") + (f" ({e['assumption'].split('_')[0]})" if e.get("assumption") else "")
        lines.append(f"| {e['day']} | {e['visit']} | {e['category']} | {e['item']} | {e['result']} | {e['consequence']} | {basis} |")
    return "\n".join(lines) + "\n"


def write(states: list, spec: dict, sched: dict, out_dir: Path, traces: int = 3) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pid = (spec.get("metadata") or {}).get("protocol_id")
    study = (pid.get("text") if isinstance(pid, dict) else pid) or "STUDY"
    dm_, ex, ae, lb, rs, ds, sv, adsl, adae, adtte = ([] for _ in range(10))
    for st in states:
        b = st.baseline
        usub = st.subject_id
        dm_.append({"STUDYID": study, "USUBJID": usub, "ARMCD": st.arm_id, "AGE": (b.get("demographic:age") or {}).get("value"),
                    "SEX": b.get("demographic:sex"), "RACE": b.get("demographic:race"), "ETHNIC": b.get("demographic:ethnicity"),
                    "RFSTDTC_DAY": 1, "ENROLLMENT_DAY": round(st.enrollment_day, 1)})
        for x in st.exposure:
            ex.append({"USUBJID": usub, "EXTRT": x["agent"], "CYCLE": x["cycle"], "EXDOSE": x["dose"],
                       "PLANNED_ADMIN": x["planned_administrations"], "ACTUAL_ADMIN": x["administrations"]})
        for i, e in enumerate(st.ae, 1):
            acts = sorted({d["action"] for d in (e.get("decisions") or {}).values() if d["action"] != "no_rule"})
            ae.append({"USUBJID": usub, "AESEQ": i, "AETERM": e["term"], "AESER": "Y" if e["serious"] else "N", "AETOXGR": e["grade"],
                       "AESTDY": e["onset"], "AEENDY": e["end"], "AEACN": ";".join(acts) or "NOT APPLICABLE",
                       "AERULE": ";".join(sorted({d["rule_id"] for d in (e.get("decisions") or {}).values() if d.get("rule_id")}))})
        for e in st.events:
            if e["category"] == "laboratory":
                lb.append({"USUBJID": usub, "LBTEST": e["item"], "LBORRES": e["result"], "LBDY": e["day"], "VISIT": e["visit"],
                           "BASIS": e.get("evidence_level")})
            elif e["category"] == "tumour assessment":
                rs.append({"USUBJID": usub, "RSTEST": "overall response", "RSORRES": e["result"], "RSDY": e["day"], "VISIT": e["visit"]})
            sv.append({"USUBJID": usub, "VISIT": e["visit"], "SVSTDY": e["day"]})
        ds.append({"USUBJID": usub, "DSDECOD": st.off_treatment[1], "DSSTDY": st.off_treatment[0], "DSCAT": "END OF TREATMENT"})
        planned = sum(x["planned_administrations"] for x in st.exposure)
        given = sum(x["administrations"] for x in st.exposure)
        adsl.append({**dm_[-1], "TRTSDY": 1, "TRTEDY": st.off_treatment[0], "EOTREAS": st.off_treatment[1],
                     "N_CYCLES": max((x["cycle"] for x in st.exposure), default=0), "N_REDUCTIONS": sum(st.reductions.values()),
                     "N_HOLDS": len(st.holds), "RDI": round(given / planned, 3) if planned else None,
                     "ANY_SAE": "Y" if any(e["serious"] for e in st.ae) else "N", "ANY_GR3": "Y" if any(e["grade"] >= 3 for e in st.ae) else "N",
                     "DTHFL": "Y" if st.death_day is not None else "N", "DTHDY": st.death_day})
        for e in ae:
            if e["USUBJID"] == usub:
                adae.append({**e, "ARMCD": st.arm_id, "TRTEMFL": "Y" if e["AESTDY"] <= st.off_treatment[0] + 30 else "N"})
        pfs_day = st.progression_detected_day
        last = max([ev["day"] for ev in st.events if ev["category"] == "tumour assessment"] or [st.off_treatment[0]])
        adtte.append({"USUBJID": usub, "ARMCD": st.arm_id, "PARAMCD": "PFS", "PARAM": "Progression-free survival (detected at assessment)",
                      "AVAL_DAYS": pfs_day if pfs_day else last, "CNSR": 0 if pfs_day else 1,
                      "EVNTDESC": "progression detected at scheduled tumour assessment" if pfs_day else "censored at last tumour assessment"})
        last_seen = max([ev["day"] for ev in st.events] + [st.off_treatment[0]])
        adtte.append({"USUBJID": usub, "ARMCD": st.arm_id, "PARAMCD": "OS", "PARAM": "Overall survival (death in the simulated horizon)",
                      "AVAL_DAYS": st.death_day if st.death_day is not None else last_seen, "CNSR": 0 if st.death_day is not None else 1,
                      "EVNTDESC": "death" if st.death_day is not None else "censored at last simulated contact"})
    for name, rows in (("dm", dm_), ("ex", ex), ("ae", ae), ("lb", lb), ("rs", rs), ("ds", ds), ("sv", sv),
                       ("adsl", adsl), ("adae", adae), ("adtte", adtte)):
        _csv(out / f"{name}.csv", rows)
    # traces: the subjects with the most eventful journeys (a dose modification first), then the first subjects
    ranked = sorted(states, key=lambda s: (-len(s.holds) - sum(s.reductions.values()), -len(s.ae), s.subject_id))
    chosen = ranked[:traces]
    tdir = out / "traces"
    tdir.mkdir(exist_ok=True)
    for st in chosen:
        (tdir / f"patient_trace_{st.subject_id}.json").write_text(json.dumps({
            "subject_id": st.subject_id, "arm": st.arm_id, "agents": st.agents, "baseline": st.baseline,
            "progression_day_latent": st.progression_day, "progression_detected_day": st.progression_detected_day,
            "off_treatment": st.off_treatment, "dose": st.dose, "reductions": st.reductions, "exposure": st.exposure,
            "adverse_events": st.ae, "events": st.events}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        (tdir / f"patient_trace_{st.subject_id}.md").write_text(_trace_md(st), encoding="utf-8")
    n = len(states)
    reasons: dict = {}
    for st in states:
        reasons[st.off_treatment[1]] = reasons.get(st.off_treatment[1], 0) + 1
    return {"subjects": n, "traces": [s.subject_id for s in chosen],
            "any_dose_hold": sum(bool(s.holds) for s in states), "any_dose_reduction": sum(bool(sum(s.reductions.values())) for s in states),
            "discontinued_for_ae": sum(s.off_treatment[1].startswith("adverse") for s in states),
            "deaths": sum(s.death_day is not None for s in states),
            "deaths_on_treatment": sum(s.off_treatment[1] == "death" for s in states),
            "end_of_treatment_reasons": reasons, "median_rdi": (lambda v: v[len(v) // 2] if v else None)(sorted(r["RDI"] for r in adsl if r["RDI"] is not None)),
            "progression_detected": sum(s.progression_detected_day is not None for s in states),
            "adverse_events_after_reporting_window_dropped": sum(s.dropped_after_off_treatment for s in states),
            "rules_undecidable": sorted({u for s in states for e in s.ae for d in (e.get("decisions") or {}).values() for u in d["undecidable"]})}
