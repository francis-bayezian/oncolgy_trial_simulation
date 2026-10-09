"""Presentation figures for the protocol-feasibility story (16:9, one clinical question per figure).

Reads the feasibility results computed from a locked run (clinical_asset.trial.feasibility) and, for the final
retrospective figure only, the run's comparison with the registry. Fixed colour system across all figures.
Run with .venv-figures/Scripts/python.exe scripts/feasibility_figures.py NCT VERSION
"""

import json
import math
import re
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from scipy import stats  # noqa: E402

NCT, VER = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("NCT05722015", "1.2.0")
RUN = Path("data/trial/runs") / NCT / f"v{VER}"
LOCK = Path("data/locked") / NCT
OUT = RUN / "feasibility" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
F = json.loads((RUN / "feasibility" / "feasibility.json").read_text(encoding="utf-8"))

CAND, ELIG, ENR, EVAL, SAFE, LOSS, OBS, ALT = "#BDBDBD", "#009E73", "#0072B2", "#005A8D", "#E69F00", "#D55E00", "#222222", "#CC79A7"
INK, MUTED, PALE = "#222222", "#6B6B6B", "#EFEFEF"
W, H = 13.33, 7.5
mpl.rcParams.update({"font.family": "Arial", "font.size": 13, "axes.titlesize": 14, "axes.labelsize": 13, "xtick.labelsize": 12,
                     "ytick.labelsize": 12, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.8,
                     "axes.edgecolor": "#444444", "xtick.color": "#444444", "ytick.color": "#444444", "pdf.fonttype": 42,
                     "svg.fonttype": "none", "axes.grid": False})


ACRONYMS = {"ecog", "hiv", "cns", "alt", "ast", "anc", "ctcae", "pd", "pk", "auc"}


def tidy(label: str) -> str:
    return " ".join(w.upper() if w.lower().strip(";,") in ACRONYMS else w for w in label.split())


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def frame(title: str, conclusion: str):
    fig = plt.figure(figsize=(W, H))
    fig.text(0.04, 0.945, title, fontsize=19, fontweight="bold", color=INK, va="center")
    fig.text(0.04, 0.035, conclusion, fontsize=14, color=INK, va="center", style="italic",
             bbox={"boxstyle": "round,pad=0.45", "fc": "#F4F4F4", "ec": "none"})
    return fig


def save(fig, name: str):
    for ext in ("png", "svg", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200 if ext == "png" else None)
    plt.close(fig)


def short(endpoint: str) -> str:
    e = endpoint.replace("Steady-state (Cycle 3) Ctrough", "Ctrough, cycle 3").replace("Cycle 1 AUC0-6wks", "AUC 0-6 weeks, cycle 1")
    return e.replace("Cycle 1 AUC0-6 wks", "AUC 0-6 weeks, cycle 1")


EVW = F["evaluability"]
TARGET = F["target"]


# ---------------------------------------------------------------- Figure 1
def figure1():
    fig = frame("From protocol requirements to a feasible patient journey",
                "Feasibility is decided at every step of the pathway, not only at enrolment.")
    ax = fig.add_axes([0.03, 0.1, 0.94, 0.78])
    ax.set_xlim(0, 7)
    ax.set_ylim(0, 3)
    ax.axis("off")
    steps = [("Potential\npatients", CAND), ("Screening", CAND), ("Eligible\npopulation", ELIG), ("Enrolment", ENR),
             ("Treatment", ENR), ("Follow-up", ENR), ("Endpoint-\nevaluable", EVAL)]
    questions = ["Who is\navailable?", "Who can\nenter?", "", "Who can be\nrecruited?", "", "Who remains\non study?", "Who provides\nthe endpoint?"]
    acts = ["", "Eligibility\ncriteria", "", "Treatment\nallocation", "Procedures and\nsafety monitoring", "Visit\nschedule", "Endpoint\nrequirements"]
    for i, (lab, col) in enumerate(steps):
        x = i + 0.08
        ax.add_patch(FancyBboxPatch((x, 1.15), 0.84, 0.7, boxstyle="round,pad=0.02,rounding_size=0.08", fc=col, ec="none"))
        ax.text(x + 0.42, 1.5, lab, ha="center", va="center", fontsize=14, fontweight="bold",
                color="white" if col != CAND else INK)
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch((x + 0.86, 1.5), (x + 1.06, 1.5), arrowstyle="-|>", mutation_scale=16, color=MUTED, lw=1.4))
        if questions[i]:
            ax.text(x + 0.42, 2.45, questions[i], ha="center", va="center", fontsize=13, color=INK)
            ax.plot([x + 0.42, x + 0.42], [2.18, 1.9], color=MUTED, lw=0.8)
        if acts[i]:
            ax.text(x + 0.42, 0.55, acts[i], ha="center", va="center", fontsize=12, color=MUTED)
            ax.plot([x + 0.42, x + 0.42], [0.85, 1.1], color=MUTED, lw=0.8)
    ax.text(0.0, 2.85, "Feasibility questions", fontsize=13, color=MUTED, fontweight="bold")
    ax.text(0.0, 0.18, "What the protocol acts on", fontsize=13, color=MUTED, fontweight="bold")
    save(fig, "Figure1_patient_journey")


# ---------------------------------------------------------------- Figure 2
def figure2():
    fu = F["funnel"]
    fig = frame("Patient attrition across the trial pathway",
                f"{pct(F['eligibility_yield'])} of candidates remained eligible after all protocol criteria; "
                f"{F['screened_per_enrollee']:.1f} patients must be screened per enrollee.")
    ax = fig.add_axes([0.22, 0.13, 0.33, 0.68])
    rows = [f for f in fu]
    labels = [r["step"] for r in rows] + ["Eligible"]
    n0 = rows[0]["remaining"]
    y = np.arange(len(labels))[::-1]
    for i, r in enumerate(rows):
        if i == 0:
            ax.barh(y[i], r["remaining"], color=CAND, height=0.62)
            ax.text(r["remaining"] * 1.01, y[i], f"{r['remaining']:,}", va="center", fontsize=12)
        else:
            ax.barh(y[i], r["remaining"], color=CAND, height=0.62)
            ax.barh(y[i], r["lost"], left=r["remaining"], color=LOSS, height=0.62)
            ax.text(n0 * 1.02, y[i], f"−{r['lost']:,} ({pct(r['pct_lost_at_step'], 1)})", va="center", fontsize=11, color=LOSS)
    ax.barh(y[-1], F["eligible"], color=ELIG, height=0.62)
    ax.text(F["eligible"] * 1.01, y[-1], f"{F['eligible']:,}  ({pct(F['eligibility_yield'])})", va="center", fontsize=12, color=ELIG,
            fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, n0 * 1.45)
    ax.set_xticks([0, n0 / 2, n0])
    ax.set_xticklabels([f"{int(v):,}" for v in (0, n0 / 2, n0)])
    ax.set_xlabel("Candidates screened")
    ax.set_title("A. Screening  (loss at each step, % of those reaching it)", loc="left", fontweight="bold", fontsize=13)
    # right: enrolled to evaluable
    bx = fig.add_axes([0.74, 0.13, 0.23, 0.68])
    steps = [("Enrolled", F["enrolled"], ENR), ("Treated", F["treated"], ENR)] + \
        [(f"Evaluable:\n{short(w['endpoint'])}", w["evaluable"], EVAL) for w in EVW]
    yy = np.arange(len(steps))[::-1]
    for (lab, n, col), yv in zip(steps, yy, strict=True):
        bx.barh(yv, n, color=col, height=0.62)
        bx.text(n + 5, yv, f"{n}  ({pct(n / F['enrolled'])})", va="center", fontsize=12)
    for w, yv in zip(EVW, yy[2:], strict=True):
        if w.get("required"):
            bx.plot([w["required"]] * 2, [yv - 0.38, yv + 0.38], color=OBS, lw=2)
            bx.text(w["required"], yv + 0.42, f"required {w['required']}", ha="center", fontsize=10.5, color=OBS)
    bx.set_yticks(yy)
    bx.set_yticklabels([s[0] for s in steps])
    bx.set_xlim(0, F["enrolled"] * 1.35)
    bx.set_xlabel("Participants")
    bx.set_title("B. After enrolment", loc="left", fontweight="bold")
    fig.text(0.04, 0.875, f"Eligibility yield {pct(F['eligibility_yield'])}   ·   Screened per enrollee {F['screened_per_enrollee']:.1f}   ·   "
             f"Screened for {TARGET}: {F['screened_for_target']:.0f}", fontsize=12.5, color=INK, ha="left")
    save(fig, "Figure2_attrition")


# ---------------------------------------------------------------- Figure 3
def figure3():
    sg = F["subgroups"]
    show = [("Sex", "female", "Women"), ("Sex", "male", "Men"), ("Age", "<65 years", "Age <65"), ("Age", "65 years or older", "Age ≥65"),
            ("ECOG", "ECOG 0", "ECOG 0"), ("ECOG", "ECOG 1", "ECOG 1"), ("ECOG", "ECOG 2 or more", "ECOG ≥2"),
            ("Race", "White", "White"), ("Race", "Asian", "Asian"), ("Race", "Black or African American", "Black"),
            ("Ethnicity", "Hispanic or Latino", "Hispanic")]
    show = [(d, lv, lab) for d, lv, lab in show if lv in sg.get(d, {})]
    yields = {lab: sg[d][lv]["p_eligible"] for d, lv, lab in show}
    lo = min(yields, key=yields.get)
    fig = frame("Feasibility differs across patient subgroups",
                f"Screening yield ranges from {pct(min(yields.values()))} ({lo}) to {pct(max(yields.values()))}; "
                "representation is set mostly by who is available.")
    y = np.arange(len(show))[::-1]
    a = fig.add_axes([0.1, 0.13, 0.2, 0.72])
    a.barh(y, [sg[d][lv]["candidate_share"] for d, lv, _ in show], color=CAND, height=0.6)
    for yv, (d, lv, _) in zip(y, show, strict=True):
        a.text(sg[d][lv]["candidate_share"] + 0.01, yv, pct(sg[d][lv]["candidate_share"]), va="center", fontsize=11)
    a.set_yticks(y)
    a.set_yticklabels([lab for _, _, lab in show])
    a.set_xlim(0, 1.05)
    a.set_xticks([0, 0.5, 1])
    a.set_xticklabels(["0%", "50%", "100%"])
    a.set_title("A. Availability\n(share of candidates)", loc="left", fontweight="bold")
    b = fig.add_axes([0.34, 0.13, 0.25, 0.72])
    b.axvline(F["eligibility_yield"], color=MUTED, lw=1, ls="--")
    b.text(F["eligibility_yield"], y[0] + 0.7, "all", ha="center", fontsize=10.5, color=MUTED)
    for yv, (d, lv, _) in zip(y, show, strict=True):
        v = sg[d][lv]["p_eligible"]
        b.plot([F["eligibility_yield"], v], [yv, yv], color=ELIG, lw=1.2, alpha=0.5)
        b.plot(v, yv, "o", color=ELIG, ms=9)
        b.text(v + (0.015 if v >= F["eligibility_yield"] else -0.015), yv + 0.28, pct(v), fontsize=10.5,
               ha="left" if v >= F["eligibility_yield"] else "right")
    b.set_yticks(y)
    b.set_yticklabels([])
    lo_x = min(yields.values()) - 0.12
    b.set_xlim(max(0, lo_x), min(1.0, max(yields.values()) + 0.12))
    b.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    b.set_title("B. Screening yield\nP(eligible | subgroup)", loc="left", fontweight="bold")
    c = fig.add_axes([0.66, 0.13, 0.13, 0.72])
    hl = ("Women", "Age ≥65", "ECOG 1", "Asian", "Hispanic")
    for d, lv, lab in show:
        if lab not in hl:
            continue
        r = sg[d][lv]
        vals = [r["candidate_share"], r["eligible_share"], r["enrolled_share"]]
        c.plot([0, 1, 2], vals, "-o", color=ENR, lw=1.8, ms=5)
        c.text(2.12, vals[2], f"{lab}  {pct(vals[0])} → {pct(vals[1])} → {pct(vals[2])}", va="center", fontsize=11, color=ENR)
    c.set_xticks([0, 1, 2])
    c.set_xticklabels(["Candidates", "Eligible", "Enrolled"], rotation=0, fontsize=11)
    c.set_xlim(-0.15, 2.1)
    c.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    c.set_title("C. Representation\nalong the pathway", loc="left", fontweight="bold")
    save(fig, "Figure3_subgroups")


# ---------------------------------------------------------------- Figure 4
def figure4():
    cr = [c for c in F["criteria"]][:12]
    shades = {"Disease and stage": "#7F7F7F", "Prior treatment": "#9E9E9E", "Performance status": "#5E5E5E",
              "Laboratory and organ function": "#B0B0B0", "Reproductive and contraception": "#C8C8C8",
              "Comorbidity and other exclusions": "#A3A3A3"}
    top = cr[0]
    nond = next((c for c in cr if c["category"] != "Disease and stage"), top)
    fig = frame("Contribution of individual eligibility criteria to screening failure",
                f"Disease definition removes {pct(top['pct_excluded'], 1)} of candidates; relaxing "
                f"{tidy(nond['label'])} would add {100 * nond['gain_if_relaxed'] / F['candidates']:.1f} points of eligibility.")
    y = np.arange(len(cr))[::-1]
    a = fig.add_axes([0.33, 0.13, 0.38, 0.72])
    a.barh(y, [c["pct_excluded"] for c in cr], color=[shades.get(c["category"], "#A0A0A0") for c in cr], height=0.62)
    for yv, c in zip(y, cr, strict=True):
        a.text(c["pct_excluded"] + 0.002, yv, pct(c["pct_excluded"], 1), va="center", fontsize=11)
    a.set_yticks(y)
    a.set_yticklabels([tidy(c["label"]) for c in cr], fontsize=11.5)
    a.xaxis.set_major_locator(mpl.ticker.MultipleLocator(0.05))
    a.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    a.set_xlabel("Candidates excluded by the criterion")
    a.set_title("A. Candidates excluded", loc="left", fontweight="bold")
    b = fig.add_axes([0.76, 0.13, 0.21, 0.72])
    b.barh(y, [100 * c["gain_if_relaxed"] / F["candidates"] for c in cr], color=ELIG, height=0.62)
    for yv, c in zip(y, cr, strict=True):
        b.text(100 * c["gain_if_relaxed"] / F["candidates"] + 0.1, yv, f"+{100 * c['gain_if_relaxed'] / F['candidates']:.1f}", va="center", fontsize=11)
    b.set_yticks(y)
    b.set_yticklabels([])
    b.set_xlabel("Gain if relaxed (points)")
    b.set_title("B. ΔEligibility", loc="left", fontweight="bold")
    cats = list(dict.fromkeys(c["category"] for c in cr))
    for i, cat in enumerate(cats):
        fig.text(0.52, 0.62 - i * 0.04, "■", color=shades.get(cat, "#A0A0A0"), fontsize=14, va="center")
        fig.text(0.535, 0.62 - i * 0.04, cat, fontsize=11, color=MUTED, va="center")
    save(fig, "Figure4_bottlenecks")


# ---------------------------------------------------------------- Figure 5
def figure5():
    R = F["recruitment"]
    mu, sd = R["historical_lognormal"]["mu"], R["historical_lognormal"]["sd"]
    obs = _observed_rate()
    fig = frame("How demanding is the planned recruitment target?",
                f"The planned rate ({R['required_rate_per_year']:.0f}/year) sits at the {ordinal(round(R['required_rate_percentile'] * 100))} percentile "
                "of comparable trials: it needs upper-tail recruitment performance.")
    a = fig.add_axes([0.06, 0.14, 0.5, 0.7])
    x = np.exp(np.linspace(np.log(2), np.log(3000), 400))
    dens = stats.norm.pdf((np.log(x) - mu) / sd) / sd
    a.fill_between(x, dens, color=CAND, alpha=0.7, lw=0)
    a.set_xscale("log")
    med = math.exp(mu)
    a.axvline(med, color=MUTED, lw=1.2, ls="--")
    a.text(med * 0.9, dens.max() * 0.6, f"historical\nmedian\n{med:.0f}/year", ha="right", fontsize=11, color=MUTED)
    a.axvline(R["required_rate_per_year"], color=ENR, lw=2.4)
    a.text(R["required_rate_per_year"] * 1.08, dens.max() * 0.75, f"planned requirement\n{R['required_rate_per_year']:.0f}/year",
           fontsize=12, color=ENR, fontweight="bold")
    if obs:
        a.plot([obs], [dens.max() * 0.12], "o", color=OBS, ms=9)
        a.annotate(f"what the trial later achieved\n(at least {obs:.0f}/year)", (obs, dens.max() * 0.12), (obs * 0.12, dens.max() * 0.38),
                   fontsize=11, color=OBS, arrowprops={"arrowstyle": "-", "color": OBS, "lw": 0.8})
    a.set_yticks([])
    a.spines["left"].set_visible(False)
    a.set_xlabel("Annual recruitment rate, comparable trials (patients per year, log scale)")
    a.set_xticks([5, 10, 30, 100, 300, 1000])
    a.set_xticklabels(["5", "10", "30", "100", "300", "1,000"])
    a.set_title("A. Where the requirement lies in historical experience", loc="left", fontweight="bold")
    b = fig.add_axes([0.64, 0.14, 0.33, 0.7])
    cc = R["completion_curve"]
    m = [c["months"] for c in cc if c["months"] <= 60]
    p = [c["p_complete"] for c in cc if c["months"] <= 60]
    b.plot(m, p, color=ELIG, lw=2.2)
    pm = R["planned_years"] * 12
    b.axvline(pm, color=ENR, lw=1.6)
    b.plot(pm, R["p_complete_in_planned_window"], "o", color=ENR, ms=8)
    b.text(pm + 3, R["p_complete_in_planned_window"] + 0.03, f"{pct(R['p_complete_in_planned_window'])} by the planned\n{pm:.0f} months",
           fontsize=12, color=ENR, fontweight="bold")
    b.set_ylim(0, 1)
    b.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    b.set_xlabel("Months from first enrolment")
    b.set_ylabel(f"P(all {TARGET} enrolled)")
    b.set_title("B. Probability of completing recruitment", loc="left", fontweight="bold")
    save(fig, "Figure5_recruitment")


def _observed_rate():
    f = RUN / "comparison" / "planning" / "planning_comparison.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["historical_model"].get("observed_rate_per_year_lower_bound")
    return None


def _actual() -> dict:
    """What the trial later reported (only when the run has been compared with the registry): evaluable PK numbers and
    the share with a serious adverse event, for the known-limitation notes."""
    out = {}
    f = RUN / "comparison" / "ratio_ni" / "ratio_ni_comparison.json"
    if f.exists():
        items = [i for i in json.loads(f.read_text(encoding="utf-8"))["items"] if i["status"] == "SCORED"]
        out["evaluable"] = {i["endpoint"]: sum(i["actual"]["n"].values()) for i in items}
    reg = Path(f"data/holdout_comparison/{NCT}.json")
    if reg.exists():
        rs = json.loads(reg.read_text(encoding="utf-8")).get("resultsSection") or {}
        groups = (rs.get("adverseEventsModule") or {}).get("eventGroups") or []
        if groups:
            out["at_risk"] = sum(g["seriousNumAtRisk"] for g in groups)
            out["sae"] = [g["seriousNumAffected"] / g["seriousNumAtRisk"] for g in groups]
    return out


def limitation(fig, text: str):
    fig.text(0.04, 0.895, "Known limitation: " + text, fontsize=12, color=LOSS, va="center")


# ---------------------------------------------------------------- Figure 6
def figure6():
    cur = F["evaluable_curve"]
    at = next(r for r in cur if r["enrolled"] == TARGET)
    weakest = min((w for w in EVW if w.get("required")), key=lambda w: at[w["endpoint"]]["p_meets"])
    fig = frame("Recruitment success does not guarantee endpoint feasibility",
                f"With {TARGET} enrolled, the chance of {weakest['required']} evaluable for {short(weakest['endpoint'])} is "
                f"{pct(at[weakest['endpoint']]['p_meets'])}; about {next(r['enrolled'] for r in cur if r['p_all'] >= 0.9)} enrolled gives ≥90%.")
    a = fig.add_axes([0.25, 0.14, 0.24, 0.7])
    steps = [("Enrolled", F["enrolled"], ENR), ("Received treatment", F["treated"], ENR)] + \
        [(f"On study at day {w['on_study_day']:.0f}\n({short(w['endpoint'])})", w["evaluable"], EVAL) for w in EVW]
    yy = np.arange(len(steps))[::-1]
    for (lab, n, col), yv in zip(steps, yy, strict=True):
        a.barh(yv, n, color=col, height=0.6)
        a.text(n + 4, yv, f"{n}", va="center", fontsize=12)
    for w, yv in zip(EVW, yy[2:], strict=True):
        if w.get("required"):
            a.plot([w["required"]] * 2, [yv - 0.36, yv + 0.36], color=OBS, lw=2)
            a.text(w["required"], yv + 0.42, f"required {w['required']}", ha="center", fontsize=10.5, color=OBS)
    a.set_yticks(yy)
    a.set_yticklabels([s[0] for s in steps], fontsize=11.5)
    a.set_xlim(0, F["enrolled"] * 1.2)
    a.set_xlabel("Participants")
    a.set_title("A. From enrolment to usable data", loc="left", fontweight="bold")
    b = fig.add_axes([0.58, 0.14, 0.39, 0.7])
    ns = [r["enrolled"] for r in cur]
    reqs = [w for w in EVW if w.get("required")]
    for w, col in zip(reqs, (ELIG, EVAL, ALT), strict=False):
        ys = [r[w["endpoint"]]["p_meets"] for r in cur]
        b.plot(ns, ys, "-o", color=col, lw=2.2, ms=5)
        i = next((k for k, v in enumerate(ys) if v >= 0.5), len(ys) - 1)
        b.text(ns[i] + 4, ys[i] - 0.06, f"{short(w['endpoint'])} ≥ {w['required']}", fontsize=11.5, color=col, fontweight="bold")
    if len(reqs) > 1:
        b.plot(ns, [r["p_all"] for r in cur], "--", color=OBS, lw=1.4)
    b.axvline(TARGET, color=MUTED, lw=1, ls=":")
    b.text(TARGET - 3, 0.04, f"planned {TARGET}", ha="right", fontsize=11, color=MUTED)
    b.set_ylim(0, 1.03)
    b.set_xlim(ns[0] - 5, ns[-1] + 5)
    b.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    b.set_xlabel("Number enrolled")
    b.set_ylabel("P(enough evaluable participants)")
    b.set_title("B. Enrolment needed for the required numbers", loc="left", fontweight="bold")
    act = _actual()
    if act.get("evaluable") and act.get("at_risk"):
        notes = []
        for w in EVW:
            k = re.search(r"cycle\s*(\d+)", w["endpoint"], re.IGNORECASE)
            n = next((v for e, v in act["evaluable"].items() if k and re.search(rf"cycle\s*{k.group(1)}\b", e, re.IGNORECASE)), None)
            if n is not None and w.get("required") and abs(w["share"] - n / act["at_risk"]) >= 0.05:
                notes.append(f"{short(w['endpoint']).split(',')[0]} {pct(w['share'])} simulated vs {pct(n / act['at_risk'])} in the trial")
        if notes:
            limitation(fig, "simulated patients leave treatment earlier than in the trial (evaluable " + "; ".join(notes) + ").")
    save(fig, "Figure6_evaluable")


# ---------------------------------------------------------------- Figure 7
def figure7():
    S = F["safety"]
    sae = S["Serious adverse event"]
    fig = frame("Expected safety burden across the patient journey",
                f"About {sae['share'] * TARGET:.0f} of {TARGET} enrolled patients may need serious-adverse-event management.")
    keys = list(S)
    y = np.arange(len(keys))[::-1]
    a = fig.add_axes([0.29, 0.14, 0.21, 0.7])
    for yv, k in zip(y, keys, strict=True):
        s = S[k]
        a.barh(yv, s["share"], color=SAFE, height=0.6)
        a.plot(s["ci"], [yv, yv], color=INK, lw=1)
        a.text(max(s["ci"][1], s["share"]) + 0.01, yv, pct(s["share"], 1), va="center", fontsize=11)
    a.set_yticks(y)
    a.set_yticklabels(keys, fontsize=11.5)
    a.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    a.set_xlim(0, max(s["ci"][1] for s in S.values()) * 1.3)
    a.set_title("A. Share of participants (95% CI)", loc="left", fontweight="bold")
    b = fig.add_axes([0.53, 0.14, 0.1, 0.7])
    b.barh(y, [S[k]["share"] * TARGET for k in keys], color=SAFE, height=0.6, alpha=0.75)
    for yv, k in zip(y, keys, strict=True):
        b.text(S[k]["share"] * TARGET + 2, yv, f"{S[k]['share'] * TARGET:.0f}", va="center", fontsize=11)
    b.set_yticks(y)
    b.set_yticklabels([])
    b.set_xlim(0, TARGET * 0.75)
    b.set_title(f"B. Of {TARGET}", loc="left", fontweight="bold")
    c = fig.add_axes([0.79, 0.14, 0.18, 0.7])
    sg = F["subgroups"]
    rows = [(d, lv) for d in ("Age", "Sex", "ECOG", "Region") for lv in sg.get(d, {}) if sg[d][lv].get("sae_rate") is not None
            and sg[d][lv]["enrolled"] >= 10]
    yc = np.arange(len(rows))[::-1]
    for yv, (d, lv) in zip(yc, rows, strict=True):
        r = sg[d][lv]
        c.plot(r["sae_ci"], [yv, yv], color=SAFE, lw=2.2)
        c.plot(r["sae_rate"], yv, "o", color=SAFE, ms=7)
    c.axvline(sae["share"], color=MUTED, lw=1, ls="--")
    c.set_yticks(yc)
    lab = {"North America/Western Europe/Australia/New Zealand": "N. America/W. Europe/Aus./NZ"}
    c.set_yticklabels([lab.get(lv, lv[0].upper() + lv[1:]) for _, lv in rows], fontsize=10.5)
    c.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    c.set_title("C. Serious AE by subgroup", loc="left", fontweight="bold")
    act = _actual()
    est = _sae_evidence()
    if act.get("sae") and est is not None:
        limitation(fig, f"patient-level events overshoot the evidence estimate ({pct(sae['share'])} simulated vs {pct(est, 1)} expected; "
                        f"the trial reported {' / '.join(pct(x, 1) for x in act['sae'])}).")
    save(fig, "Figure7_safety_burden")


def _sae_evidence():
    f = LOCK / f"outputs_v{VER}" / "trial_outputs.json"
    if not f.exists():
        return None
    arms = (json.loads(f.read_text(encoding="utf-8")).get("feasibility") or {}).get("subgroup_estimates", {}).get("arms", {})
    vals = [a["serious_adverse_event"]["headline"]["estimate"] for a in arms.values() if a.get("serious_adverse_event")]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------- Figure 8
def figure8():
    sc = F["scenarios"]
    req_eps = [w for w in EVW if w.get("required")]
    weak = min(req_eps, key=lambda w: w["share"])
    cols = [("Eligible\npopulation", "eligible_pct", +1, lambda v: pct(v)),
            ("Screened\nper enrollee", "screened_per_enrollee", -1, lambda v: f"{v:.2f}"),
            ("Months to\nrecruit", "median_recruitment_months", -1, lambda v: f"{v:.0f}"),
            ("P(recruit\nin window)", "p_recruit_in_window", +1, lambda v: pct(v)),
            ("Women", "female_pct", 0, lambda v: pct(v)),
            ("Age ≥65", "age65_pct", 0, lambda v: pct(v)),
            ("Patients with\nserious AE", "sae_patients", -1, lambda v: f"{v:.0f}"),
            ("Visit days\nper patient", "visit_days_per_patient", -1, lambda v: f"{v:.0f}"),
            (f"Evaluable\n{short(weak['endpoint']).split(',')[0]}", ("evaluable_median", weak["endpoint"]), +1, lambda v: f"{v:.0f}"),
            ("P(meeting trial\nobjectives)", "p_objectives", +1, lambda v: pct(v))]

    def val(s, key):
        return s[key[0]][key[1]] if isinstance(key, tuple) else s[key]
    best = max(sc[1:], key=lambda s: s["p_objectives"])
    fig = frame("Protocol changes create measurable feasibility trade-offs",
                f"'{best['scenario']}' raises the chance of meeting the trial objectives from {pct(sc[0]['p_objectives'])} to "
                f"{pct(best['p_objectives'])}, at the cost of {best['sae_patients'] - sc[0]['sae_patients']:.0f} more patients with a serious AE.")
    ax = fig.add_axes([0.2, 0.1, 0.79, 0.74])
    nr, nc = len(sc), len(cols)
    ax.set_xlim(0, nc)
    ax.set_ylim(0, nr)
    ax.invert_yaxis()
    ax.axis("off")
    good, bad = np.array(mpl.colors.to_rgb(ELIG)), np.array(mpl.colors.to_rgb(SAFE))
    neutral = np.array(mpl.colors.to_rgb(PALE))
    for j, (name, key, direction, fmt) in enumerate(cols):
        ax.text(j + 0.5, -0.12, name, ha="center", va="bottom", fontsize=11.5, fontweight="bold")
        base = val(sc[0], key)
        for i, s in enumerate(sc):
            v = val(s, key)
            rel = 0 if not base else (v - base) / abs(base)
            strength = min(1.0, abs(rel) / 0.25) if direction else 0
            col = neutral
            if direction and abs(rel) >= 0.03:          # smaller differences are within simulation noise
                tgt = good if rel * direction > 0 else bad
                col = neutral + (tgt - neutral) * (0.25 + 0.75 * strength)
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.06), 0.94, 0.88, color=col, lw=0))
            ax.text(j + 0.5, i + 0.5, fmt(v), ha="center", va="center", fontsize=12, color=INK,
                    fontweight="bold" if i == 0 else "normal")
    for i, s in enumerate(sc):
        fig.text(0.195, 0.84 - (i + 0.5) * 0.74 / nr, tidy(s["scenario"]), ha="right", va="center", fontsize=12,
                 fontweight="bold" if i == 0 else "normal", color=ALT if i else INK)
    fig.text(0.2, 0.065, "Teal: more favourable than the original protocol · Orange: greater feasibility burden · Grey: within 3% of the original, or descriptive",
             fontsize=10.5, color=MUTED)
    save(fig, "Figure8_tradeoffs")


# ---------------------------------------------------------------- Figure 9
def figure9():
    comp = RUN / "comparison"
    reg = json.loads(Path(f"data/holdout_comparison/{NCT}.json").read_text(encoding="utf-8"))
    rs = reg.get("resultsSection") or {}
    rni = json.loads((LOCK / f"results_v{VER}" / "ratio_ni_results.json").read_text(encoding="utf-8"))
    rcmp = json.loads((comp / "ratio_ni" / "ratio_ni_comparison.json").read_text(encoding="utf-8"))
    outs = json.loads((LOCK / f"outputs_v{VER}" / "trial_outputs.json").read_text(encoding="utf-8"))
    sae_est = outs["feasibility"]["subgroup_estimates"]["arms"]["ARM1"]["serious_adverse_event"]["headline"]["estimate"]
    R = F["recruitment"]
    var = rni["variability"]
    reg_cv = [var[a]["registry"]["median_cv"] for a in ("AN1", "AN2")]
    prot_cv = [var[a]["protocol_derived_cv"] for a in ("AN1", "AN2")]
    act_cv = [i["variability_actual"]["pooled_geo_cv"] for i in rcmp["items"] if i["status"] == "SCORED"]
    groups = (rs.get("adverseEventsModule") or {}).get("eventGroups") or []
    sae_act = " / ".join(pct(g["seriousNumAffected"] / g["seriousNumAtRisk"], 1) for g in groups)
    base = {}
    for m in (rs.get("baselineCharacteristicsModule") or {}).get("measures") or []:
        for c in m.get("classes") or []:
            for cat in c.get("categories") or []:
                tot = [x for x in cat["measurements"] if x["groupId"] == m["classes"][0]["categories"][0]["measurements"][-1]["groupId"]]
                if tot:
                    base[(m["title"].split(" (")[0].split(":")[0], cat.get("title"))] = float(tot[0]["value"])
    n_tot = sum(v for (t, k), v in base.items() if t == "Sex" and k in ("Female", "Male"))
    asian = base.get(("Race", "Asian"), 0) / n_tot if n_tot else None
    hisp = base.get(("Ethnicity", "Hispanic or Latino"), 0) / n_tot if n_tot else None
    female = base.get(("Sex", "Female"), 0) / n_tot if n_tot else None
    ev_act = {i["endpoint"]: sum(i["actual"]["n"].values()) for i in rcmp["items"] if i["status"] == "SCORED"}
    at = next(r for r in F["evaluable_curve"] if r["enrolled"] == TARGET)
    sg = F["subgroups"]
    fem_sim = sg["Sex"]["female"]["eligible_share"]
    asian_sim = sg["Race"].get("Asian", {}).get("eligible_share", 0)
    hisp_sim = sg["Ethnicity"].get("Hispanic or Latino", {}).get("eligible_share", 0)
    obs = _observed_rate()
    rows = [("Is recruitment demanding?",
             f"Planned {R['required_rate_per_year']:.0f}/year = {ordinal(round(R['required_rate_percentile'] * 100))} percentile of comparable trials;\n"
             f"{pct(R['p_complete_in_planned_window'])} chance of finishing in {R['planned_years'] * 12:.0f} months",
             f"377 enrolled at ≥{obs:.0f}/year:\nupper-tail performance was achieved" if obs else "—"),
            ("Are the variability assumptions realistic?",
             f"Comparable trials: CV {pct(reg_cv[0])} (AUC), {pct(reg_cv[1])} (Ctrough)\nProtocol assumed {pct(prot_cv[0])} and {pct(prot_cv[1])}",
             f"Observed CV {pct(act_cv[0])} and {pct(act_cv[1])}" if len(act_cv) == 2 else "—"),
            ("What safety burden should sites expect?",
             f"Comparable trials: {pct(sae_est, 1)} with a serious AE\n(≈{sae_est * TARGET:.0f} of {TARGET} patients)",
             f"{sae_act} (subcutaneous / intravenous)"),
            ("Is the population composition fixed?",
             f"Simulated eligible pool: {pct(fem_sim)} women, {pct(asian_sim)} Asian,\n{pct(hisp_sim)} Hispanic (one global mix)",
             f"{pct(female)} women, {pct(asian)} Asian, {pct(hisp)} Hispanic:\nrecruitment geography shaped the mix" if n_tot else "—"),
            ("Will the required PK numbers be retained?",
             "; ".join(f"P({short(w['endpoint']).split(',')[0]} ≥ {w['required']}) {pct(at[w['endpoint']]['p_meets'])}" for w in EVW if w.get("required"))
             + f"\nat {TARGET} enrolled",
             " / ".join(f"{v}" for v in ev_act.values()) + " evaluable (AUC / Ctrough)")]
    fig = frame(f"Retrospective evaluation of pre-trial feasibility signals in {NCT}",
                "The pre-trial assessment flagged the demanding accrual and gave realistic variability and safety inputs; "
                "composition depended on geography.")
    ax = fig.add_axes([0.03, 0.1, 0.94, 0.76])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows) + 0.8)
    ax.invert_yaxis()
    xs = [(0.0, 0.25, "Planning question", INK), (0.27, 0.42, "Feasibility assessment (before the trial)", ENR),
          (0.71, 0.29, "What subsequently occurred", OBS)]
    for x, w, t, col in xs:
        ax.text(x, 0.35, t, fontsize=13.5, fontweight="bold", color=col, va="center")
    for i, r in enumerate(rows):
        yv = i + 1.2
        ax.add_patch(plt.Rectangle((0, yv - 0.45), 1, 0.9, color=PALE if i % 2 == 0 else "white", lw=0))
        for (x, w, _, col), txt in zip(xs, r, strict=True):
            ax.text(x + 0.005, yv, txt, fontsize=12, va="center", color=col if col != INK else INK, fontweight="bold" if x == 0 else "normal")
    save(fig, "Figure9_retrospective")


for f in (figure1, figure2, figure3, figure4, figure5, figure6, figure7, figure8, figure9):
    f()
print("figures written to", OUT)
