"""The presentation storyline, generated from the run's canonical case-study summary (no number typed by hand).

usage: python scripts/presentation_story.py NCT VERSION OUT_FILE
"""

import json
import re
import sys
from pathlib import Path

NCT, VER, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
RUN = Path("data/trial/runs") / NCT / f"v{VER}" / "feasibility"
F = json.loads((RUN / "feasibility.json").read_text(encoding="utf-8"))
C = json.loads((RUN / "case_study_summary.json").read_text(encoding="utf-8"))
O, H = C["original_protocol"], C["historical_evidence"]
L = F.get("longitudinal") or {}
SG = F["subgroups"]


def pct(x, d=0):
    return "—" if x is None else f"{100 * x:.{d}f}%"


def short(ep):
    return "AUC" if "AUC" in ep else "Ctrough" if "trough" in ep.lower() else ep


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def response_text():
    """Simulated best overall response per arm next to its evidence input (canonical summary)."""
    parts = []
    for a in (O.get("by_arm") or {}).values():
        r = a.get("response") or {}
        i = r.get("input") or {}
        if r.get("rate") is not None:
            parts.append(f"{re.split(r',| [Ww]ith | [Cc]oformulated| [Aa]dministered', a['label'])[0].strip()} simulated {pct(r['rate'], 1)} ({r['responders']} of {r['n']}), input {pct(i.get('value'), 1)}")
        lvl = i.get("level")
    return ("; ".join(parts) + (f" (input level: {lvl}; the trial has not posted response)." if parts else "")) if parts else "not simulated."


def control_text():
    """Control-arm intervals of the two methods drawn in Figure 9 (registry population)."""
    d = Path("data/trial/runs") / NCT / f"v{VER}" / "comparison" / "control"
    out = []
    for name, lab in (("control_external.json", "serious AE"), ("control_external_response.json", "response")):
        f = d / name
        if not f.exists():
            continue
        rows = [r for r in json.loads(f.read_text(encoding="utf-8"))["rows"] if r["population"] == "registry_experimental"
                and (lab == "response" or r["outcome"] == "serious_ae")]
        txt = ", ".join(f"{m} {pct(r['predicted'])} ({pct(r['lower'])}-{pct(r['upper'])})"
                        for m, k in (("meta-analytic", "map_prior"), ("contextual", "contextual_robust"))
                        for r in rows if r["method"] == k)
        obs = next((r["observed"] for r in rows if r.get("observed") is not None), None)
        out.append(f"{lab}: {txt}; observed {pct(obs, 1) if obs is not None else 'not posted'}")
    return "; ".join(out) + "." if out else "not available."


req = {w["endpoint"]: w.get("required") for w in F["evaluability"]}
ev = O["evaluable"]
ct = next(ep for ep in ev if "trough" in ep.lower())
auc = next(ep for ep in ev if "AUC" in ep)
yields = {k: SG[d][lv]["p_eligible"] for d, lv, k in (("Sex", "female", "women"), ("Sex", "male", "men"), ("Age", "<65 years", "under 65"),
                                                       ("Age", "65 years or older", "65 or older")) if lv in SG.get(d, {})}
fem = SG["Sex"]["female"]["eligible_share"]
asian = SG["Race"].get("Asian", {}).get("eligible_share")
cr = F["criteria"]
top = cr[0]
nond = next(c for c in cr if c["category"] != "Disease and stage")
R = O["recruitment"]
wm = L.get("withdrawal_model") or {}
coef = wm.get("coefficients") or {}
comp = {c["category"]: c for c in L.get("completeness") or []}
pk = {p["endpoint"]: p for p in L.get("pk_capture") or []}
td = L.get("treatment_delivery") or {}
bs = {b["scenario"]: b["reported"] for b in C.get("burden_scenarios") or []}
sc = {s["scenario"]: s for s in C["scenarios"]}
orig = sc["Original protocol"]
relax = next((s for n, s in sc.items() if n.startswith("Relax")), None)
lines = [
    "# Protocol feasibility: presentation storyline", "",
    f"Generated from the case-study summary of the final run; every number below comes from it.", "",
    "Nine main figures (`figures/Figure1`–`Figure9`) and six supplementary figures (`S1`–`S6`).", "",
    "## 1. The question",
    f"**Figure 1, protocol to patient journey.** {O['enrolled']} patients randomised 2:1; at least {req[auc]} evaluable for AUC and "
    f"{req[ct]} for Ctrough. The strip underneath follows one simulated participant.", "",
    "## 2. Who can take part",
    f"- **Figure 2, attrition.** {O['candidates']:,} candidates → {O['eligible']:,} eligible ({pct(O['eligible_rate'])}): "
    f"{O['screened_per_eligible']:.1f} candidates screened per eligible patient; {O['screened_to_find_target']:.0f} screened to find "
    f"{O['enrolled']} eligible. Eligible patients who decline are not modelled.",
    f"- **Figure 3, subgroups.** Screening yield: " + ", ".join(f"{k} {pct(v)}" for k, v in yields.items()) +
    f". Eligibility did not materially change representation across the groups examined. The simulated eligible pool is "
    f"{pct(fem)} women and {pct(asian)} Asian.",
    f"- **Figure 4, bottlenecks.** The disease definition removes {pct(top['pct_excluded'])} of candidates; relaxing "
    f"{nond['label']} would add {100 * nond['gain_if_relaxed'] / F['candidates']:.1f} points of eligibility.", "",
    "## 3. Can they be recruited in time",
    f"**Figure 5, recruitment.** The plan needs {R['required_per_year']:.0f} patients a year, the "
    f"{ordinal(round(R['required_percentile'] * 100))} percentile of comparable trials (median {H['recruitment_median_per_year']:.0f}); "
    f"there is a {pct(R['p_complete_in_planned_window'])} chance of finishing within the planned {R['planned_months']:.0f} months.", "",
    "## 4. Do they stay, and is the data captured",
    f"- **Figure 6, evaluable numbers.** At {O['enrolled']} enrolled, {ev[auc]} patients are evaluable for AUC and {ev[ct]} for Ctrough; "
    f"P(≥{req[ct]} Ctrough-evaluable) is {pct(O['p_requirement'][ct], 1)}.",
    f"- **Figure 7, longitudinal feasibility.**",
    f"  - **A:** across {wm.get('trials', 0):,} registry trials, longer participation (OR {coef.get('log2_duration_months', {}).get('or', 0):.2f} "
    f"per doubling), more frequent visits ({coef.get('log2_visits_per_month', {}).get('or', 0):.2f}) and more assessments "
    f"({coef.get('log2_outcome_measures', {}).get('or', 0):.2f}) are associated with more withdrawal (adjusted, observational).",
    f"  - **B:** withdrawal risk accumulates over each patient's attended visits; the burden model predicts "
    f"{pct(O['withdrawal_rate_predicted'], 1)} for this protocol, and {pct(O['withdrawal_rate_simulated'], 1)} of the simulated cohort withdrew.",
    f"  - **C:** treatment delivery {pct(td.get('delivery'))} of administrations scheduled while on treatment (dose delays and missed doses "
    f"are not modelled: an upper bound); required visits completed: labs {pct(comp.get('Laboratory (safety) assessments', {}).get('attended'))}, "
    f"tumour assessments {pct(comp.get('Tumour assessments', {}).get('attended'))}, follow-up {pct(comp.get('Survival follow-up visits', {}).get('attended'))}; "
    f"PK samples captured {pct(pk[auc]['captured'] / pk[auc]['protocol_course_reaches'])} (AUC) and "
    f"{pct(pk[ct]['captured'] / pk[ct]['protocol_course_reaches'])} (Ctrough, of patients whose course reaches the sample).",
    f"  - **D:** changing follow-up frequency moves withdrawal from {pct(bs.get('Less frequent follow-up', {}).get('withdrawal_rate'), 1)} to "
    f"{pct(bs.get('Higher-burden follow-up', {}).get('withdrawal_rate'), 1)}; Ctrough-evaluable patients stay near {ev[ct]}.", "",
    "## 5. What planners can change",
    f"**Figure 8, trade-offs** (original protocol: eligible {pct(orig['eligible_pct'])}, {orig['median_recruitment_months']:.0f} months to "
    f"recruit, {orig['sae_patients']:.0f} patients with a serious AE, {orig['evaluable_median'][ct]:.0f} Ctrough-evaluable):",
    *(f"- {n}: eligible {pct(s['eligible_pct'])}, {s['screened_per_enrollee']:.2f} screened per eligible patient, "
      f"{s['median_recruitment_months']:.0f} months, {s['sae_patients']:.0f} with a serious AE, {s['evaluable_median'][ct]:.0f} Ctrough-evaluable"
      for n, s in sc.items() if n != "Original protocol"), "",
    "## 6. Comparison with the trial",
    f"**Figure 9.** Variability: comparable trials CV {pct(H['pk_cv_auc_registry'])} / {pct(H['pk_cv_ctrough_registry'])} "
    f"(protocol assumed {pct(H['pk_cv_auc_protocol'])} / {pct(H['pk_cv_ctrough_protocol'])}). Safety: historical arm-level estimate "
    f"{pct(H['sae_rate_arm_level'], 1)}; simulated cohort incidence {pct(O['sae_rate_simulated'], 1)} ({O['sae_count_simulated']} of "
    f"{O['enrolled']}). Objective response: " + response_text() + " Synthetic-control panel: " + control_text(), "",
    "## Supplementary figures",
    "S1 one participant's full record · S2 patient-level withdrawal modifiers (arm-level, not applied) · S3 control-arm benchmark · "
    "S4 every eligibility criterion · S5 effect of the journey calibration · S6 safety burden.", "",
    "## Known gaps",
    "1. Generated lab values are not yet used by the lab criteria at screening.",
    "2. The tumour scan schedule is simplified to one 12-week interval.",
    "3. The PK sampling table is redacted in the public protocol.",
    "4. Medications and hypertension are not simulated (no registry evidence).", ""]
OUT.write_text("\n".join(lines), encoding="utf-8")
print("written", OUT)
