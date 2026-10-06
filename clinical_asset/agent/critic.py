"""The critic: automated checks on a protocol run's locked artefacts that need NO registry result, so it is safe to run
on a blind or temporal trial before its results are read.

Each check returns findings {check, severity (error | warning | info), message, artefact}. Severity 'error' means the
run must not be scored as is (e.g. an analysis with alpha 1.0); 'warning' marks a weakness to report (e.g. most
eligibility criteria undecidable); 'info' records a limitation.
"""

import csv
import json
import re
from pathlib import Path

LOCK = Path("data/locked")


def latest(study: str, kind: str) -> Path | None:
    c = [p for p in (LOCK / study).glob(f"{kind}_v*") if re.fullmatch(rf"{kind}_v[\d.]+", p.name)]
    return max(c, key=lambda p: tuple(int(x) for x in p.name.rsplit("_v", 1)[1].split("."))) if c else None


def _f(check, severity, message, artefact):
    return {"check": check, "severity": severity, "message": message, "artefact": str(artefact).replace("\\", "/")}


def check_spec(study: str) -> list[dict]:
    lk = latest(study, "studyspec")
    if not lk:
        return [_f("spec_missing", "error", "no locked StudySpec", LOCK / study)]
    s = json.loads((lk / "studyspec.json").read_text(encoding="utf-8"))
    out = []
    for a in s.get("analyses") or []:
        alpha = (a.get("alpha") or {}).get("value") if isinstance(a.get("alpha"), dict) else a.get("alpha")
        if isinstance(alpha, (int, float)) and not 0 < alpha <= 0.5:
            from ..trial.run_forward import analysis_alpha

            fixed = analysis_alpha(a)                   # engines use the re-parsed quote, so this is a warning, not a stop
            sev = "warning" if fixed["source"].startswith("re-parsed") else "error"
            out.append(_f("alpha_plausible", sev, f"analysis {a.get('analysis_id')} has alpha {alpha}; engines use {fixed['value']} ({fixed['source']})", lk))
        power = (a.get("power") or {}).get("value") if isinstance(a.get("power"), dict) else a.get("power")
        if isinstance(power, (int, float)) and not 0.5 <= power < 1:
            out.append(_f("power_plausible", "warning", f"analysis {a.get('analysis_id')} has power {power}", lk))
    arms = s.get("arms") or []
    if arms and not any(a.get("status") == "open" for a in arms):
        out.append(_f("arms_open", "warning", "no arm is stated open in the compiled version: all arms not stated closed are assumed to enrol", lk))
    el = s.get("eligibility") or []
    ex = sum(c.get("status") == "EXECUTABLE" for c in el)
    if el and ex / len(el) < 0.5:
        out.append(_f("eligibility_executable", "warning", f"only {ex} of {len(el)} eligibility criteria are executable", lk))
    rr = [x for x in ("review_required.json",) if (lk / x).exists()]
    if rr:
        n = len(json.loads((lk / rr[0]).read_text(encoding="utf-8")) or [])
        if n:
            out.append(_f("review_required", "info", f"{n} items REVIEW_REQUIRED (run forward, flagged)", lk))
    return out


def check_eligibility(study: str) -> list[dict]:
    lk = latest(study, "eligibility")
    if not lk:
        return []
    s = json.loads((lk / "eligibility_summary.json").read_text(encoding="utf-8"))["summary"]
    n, c = s["patients"], s["status_counts"]
    out = []
    if c.get("ELIGIBLE", 0) == 0:
        out.append(_f("screening_decidable", "warning", f"0 of {n} patients proven eligible ({c.get('UNDETERMINED', 0)} undetermined): "
                      "the screening funnel has no lower bound", lk))
    if c.get("INELIGIBLE", 0) == n:
        out.append(_f("screening_all_ineligible", "error", "every patient is ineligible: a criterion is probably misread", lk))
    return out


def check_journey(study: str, journey_dir: Path | None = None) -> list[dict]:
    d = journey_dir or Path("data/journey") / study / "run"
    f = d / "journey_summary.json"
    if not f.exists():
        return []
    s = json.loads(f.read_text(encoding="utf-8"))
    out = []
    sched = s["schedule"]
    for k in ("cycle_length_days", "tumour_assessment_interval_days", "screening_window_days"):
        if sched[k]["value"] is None:
            out.append(_f(f"schedule_{k}", "warning", f"{k} unresolved: {sched[k]['source']}", f))
    sm = s["summary"]
    if sm.get("rules_undecidable"):
        out.append(_f("dose_rules_undecidable", "info", f"dose-modification rules undecidable with generated data: {sm['rules_undecidable']}", f))
    # consistency with evidence: stopping treatment for adverse events vs the registry participant-flow share
    n = sm["subjects"] or 1
    ae_stop = sm["discontinued_for_ae"] / n
    if ae_stop > 0.5:
        out.append(_f("journey_ae_discontinuation", "warning", f"{ae_stop:.0%} of patients stop treatment for adverse events", f))
    with open(d / "adsl.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rdi = [float(r["RDI"]) for r in rows if r.get("RDI")]
    if rdi and min(rdi) < 0 or any(x > 1.0001 for x in rdi):
        out.append(_f("journey_rdi_range", "error", "relative dose intensity outside [0, 1]", d / "adsl.csv"))
    return out


MAX_PLAUSIBLE_ACCRUAL_YEARS = 15


def check_arms(study: str) -> list[dict]:
    """Every arm reference resolves, and every arm receives an anticancer agent (L019: bare designators 'A', 'B', 'C'
    matched by substring had given pemigatinib to the standard-care arms and no carfilzomib to the showcase journey)."""
    from ..trial.arms import ArmResolver

    lk = latest(study, "studyspec")
    if not lk:
        return []
    s = json.loads((lk / "studyspec.json").read_text(encoding="utf-8"))
    r = ArmResolver(s)
    out = [_f("arm_reference_unresolved", "warning", f"arm reference {ref!r} names no arm: its items apply to no arm", lk) for ref in r.unresolved()]
    for a in s.get("arms") or []:
        if a.get("status") != "closed" and not any(r.item_applies_to(it, a["arm_id"]) for it in r.anticancer):
            out.append(_f("arm_without_agent", "warning", f"arm {a['arm_id']} ({(a.get('label') or {}).get('text') if isinstance(a.get('label'), dict) else a.get('label')}) "
                          "receives no anticancer agent: its safety and journey are unresolved", lk))
    return out


def check_planning(study: str) -> list[dict]:
    """Planning units and protocol assumptions (L017, L024): an accrual duration or a deadline beyond
    MAX_PLAUSIBLE_ACCRUAL_YEARS is a unit error (a 36-month period read as 36 years); a protocol accrual rate outside
    the historical 80% range is reported."""
    lk = latest(study, "planning")
    if not lk:
        return []
    r = json.loads((lk / "planning_report.json").read_text(encoding="utf-8"))
    acc = r.get("accrual") or {}
    out = []
    for y in acc.get("stated_accrual_durations_years") or []:
        if y and y > MAX_PLAUSIBLE_ACCRUAL_YEARS:
            out.append(_f("planning_duration_units", "error", f"stated accrual duration {y:g} years: probably months or days read as years", lk))
    for s in acc.get("protocol_scenarios") or []:
        for deadline in s.get("p_enrollment_complete_by") or {}:
            m = re.fullmatch(r"([\d.]+)y", deadline)
            if m and float(m.group(1)) > MAX_PLAUSIBLE_ACCRUAL_YEARS:
                out.append(_f("planning_deadline_units", "error", f"deadline {deadline} in scenario {s['scenario']}: a unit error", lk))
    h = acc.get("historical_model") or {}
    py = h.get("patients_per_year") or {}
    for s in acc.get("protocol_scenarios") or []:
        if s.get("patients_per_year") and py.get("median") and not py["q10"] <= s["patients_per_year"] <= py["q90"]:
            out.append(_f("protocol_accrual_outside_history", "warning",
                          f"protocol accrual {s['patients_per_year']:g}/year is {s['patients_per_year'] / py['median']:.1f}x the historical median "
                          f"{py['median']:.1f}/year (p10 {py['q10']:.1f}, p90 {py['q90']:.1f}): report the historical model as the headline", lk))
    return out


def review(study: str) -> list[dict]:
    return check_spec(study) + check_arms(study) + check_eligibility(study) + check_planning(study) + check_journey(study)
