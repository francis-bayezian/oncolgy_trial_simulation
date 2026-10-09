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
CMP_VER = sys.argv[3] if len(sys.argv) > 3 else "1.2.0"     # the blind run compared with the registry (Figure 9)
CMP = Path("data/trial/runs") / NCT / f"v{CMP_VER}"
FB = json.loads((CMP / "feasibility" / "feasibility.json").read_text(encoding="utf-8")) if (CMP / "feasibility" / "feasibility.json").exists() else F
LONG = F.get("longitudinal") or {}
DEATH = "#7A7A7A"

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


def arm_name(arm_id: str) -> str:
    """A plain name for a protocol arm (no internal identifiers)."""
    arms = (F.get("protocol") or {}).get("arms") or []
    m = re.search(r"(\d+)$", arm_id or "")
    label = arms[int(m.group(1)) - 1] if m and 0 < int(m.group(1)) <= len(arms) else arm_id
    return re.split(r",| [Ww]ith | [Cc]oformulated| [Aa]dministered", label)[0].strip().lower()


def pct(x, d=0):
    return f"{100 * x:.{d}f}%"


def frame(title: str, conclusion: str):
    fig = plt.figure(figsize=(W, H))
    fig.text(0.04, 0.945, title, fontsize=19, fontweight="bold", color=INK, va="center")
    return fig                      # the one-line conclusion is not drawn on the figure


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
    ax = fig.add_axes([0.03, 0.4, 0.94, 0.5])
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
    ax.text(0.0, 0.0, "What the protocol acts on", fontsize=13, color=MUTED, fontweight="bold")
    _trace_strip(fig)
    save(fig, "Figure1_patient_journey")


TRACE_COLOURS = {"screening": CAND, "treatment": ENR, "adverse event": SAFE, "hold": SAFE, "tumour assessment": EVAL,
                 "progression": LOSS, "disposition": OBS, "follow-up": "#8A8A8A", "withdrawal": LOSS, "death": OBS}


def _milestones(events: list[dict]) -> list[tuple]:
    """The milestones of one simulated patient's journey: screening, first dose, first adverse event and any dose hold,
    the cycle-3 visit, tumour assessments, progression, end of treatment, follow-up, withdrawal or death."""
    out, seen = [], set()

    def add(day, label, kind):
        out.append((int(day), label, kind))
    for e in events:
        cat, item, res, cons = e["category"], e.get("item") or "", e.get("result") or "", e.get("consequence") or ""
        if cat == "screening" and "screening" not in seen:
            seen.add("screening")
            add(e["day"], "Screened,\neligible", "screening")
        elif cat == "treatment" and str(item).startswith("start") and "start" not in seen:
            seen.add("start")
            add(e["day"], "Randomised,\ncycle 1", "treatment")
        elif cat == "adverse event" and "ae" not in seen:
            seen.add("ae")
            add(e["day"], f"{str(item).replace('_', ' ')}\n({res.split(';')[0]})", "adverse event")
            if "held" in cons and "hold" not in seen:
                seen.add("hold")
                add(e["day"] + 1, "Dose hold", "hold")
        elif cat == "adverse event" and "held" in cons and "hold" not in seen:
            seen.add("hold")
            add(e["day"], "Dose hold", "hold")
        elif e.get("visit") == "C3D1" and "c3" not in seen:
            seen.add("c3")
            add(e["day"], "Cycle 3", "treatment")
        elif cat == "tumour assessment" and "progressive" in res:
            add(e["day"], "Progression\nat scan", "progression")
        elif cat == "tumour assessment" and "ta" not in seen:
            seen.add("ta")
            add(e["day"], "Tumour\nassessment", "tumour assessment")
        elif cat == "disposition" and item == "end of treatment" and "eot" not in seen:
            seen.add("eot")
            add(e["day"], "End of\ntreatment", "disposition")
        elif cat == "follow-up" and "fu" not in seen:
            seen.add("fu")
            add(e["day"], "Follow-up\nvisit", "follow-up")
        elif cat == "disposition" and item == "withdrawal":
            add(e["day"], "Withdrew", "withdrawal")
        elif cat == "disposition" and item == "death":
            add(e["day"], "Died", "death")
    return sorted(out)


def _trace_strip(fig):
    tr = LONG.get("trace")
    if not tr:
        return
    ms = _milestones(tr["events"])
    ax = fig.add_axes([0.06, 0.12, 0.9, 0.2])
    lo, hi = min(d for d, _, _ in ms), max(d for d, _, _ in ms)
    span = hi - lo or 1
    ax.plot([lo, hi], [0, 0], color="#CCCCCC", lw=3, zorder=1)
    for i, (d, lab, kind) in enumerate(ms):
        ax.plot(d, 0, "o", color=TRACE_COLOURS.get(kind, MUTED), ms=11, zorder=2)
        up = i % 2 == 0
        ax.text(d, 0.55 if up else -0.55, lab, ha="center", va="bottom" if up else "top", fontsize=10.5,
                color=TRACE_COLOURS.get(kind, INK) if kind not in ("screening",) else INK)
        ax.text(d, -0.12 if up else 0.12, f"day {d}", ha="center", va="top" if up else "bottom", fontsize=9, color=MUTED)
    ax.set_xlim(lo - span * 0.03, hi + span * 0.03)
    ax.set_ylim(-1.6, 1.6)
    ax.axis("off")
    b = tr.get("baseline") or {}
    age = (b.get("demographic:age") or {}).get("value")
    ecog = (b.get("var:ecog_performance_status") or {}).get("value")
    fig.text(0.04, 0.345, f"One simulated participant ({arm_name(tr['arm'])} arm): {age:.0f}-year-old {b.get('demographic:sex')}, ECOG {ecog}"
             if age is not None else "One simulated participant", fontsize=12, color=INK, fontweight="bold")


# ---------------------------------------------------------------- Figure 2
def figure2():
    fu = F["funnel"]
    fig = frame("Patient attrition across the trial pathway",
                f"{pct(F['eligibility_yield'])} of candidates remained eligible after all protocol criteria; "
                f"{F['screened_per_enrollee']:.1f} candidates must be screened per eligible patient.")
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
    fig.text(0.04, 0.875, f"Eligibility yield {pct(F['eligibility_yield'])}   ·   Candidates screened per eligible patient {F['screened_per_enrollee']:.1f}   ·   "
             f"Screened to find {TARGET} eligible: {F['screened_for_target']:.0f}", fontsize=12.5, color=INK, ha="left")
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
    f = CMP / "comparison" / "planning" / "planning_comparison.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["historical_model"].get("observed_rate_per_year_lower_bound")
    return None


def _actual() -> dict:
    """What the trial later reported (only when the run has been compared with the registry): evaluable PK numbers and
    the share with a serious adverse event, for the known-limitation notes."""
    out = {}
    f = CMP / "comparison" / "ratio_ni" / "ratio_ni_comparison.json"
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
def supp_s6_safety():
    S = F["safety"]
    sae = S["Serious adverse event"]
    fig = frame("Supplementary Figure S6. Expected safety burden across the patient journey",
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
    if act.get("sae") and est is not None and abs(sae["share"] - est) >= 0.05:
        limitation(fig, f"patient-level events differ from the evidence estimate ({pct(sae['share'])} simulated vs {pct(est, 1)} expected; "
                        f"the trial reported {' / '.join(pct(x, 1) for x in act['sae'])}).")
    save(fig, "S6_safety_burden")


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
            ("Screened per\neligible patient", "screened_per_enrollee", -1, lambda v: f"{v:.2f}"),
            ("Months to\nrecruit", "median_recruitment_months", -1, lambda v: f"{v:.0f}"),
            ("P(recruit\nin window)", "p_recruit_in_window", +1, lambda v: pct(v)),
            ("Women", "female_pct", 0, lambda v: pct(v)),
            ("Age ≥65", "age65_pct", 0, lambda v: pct(v)),
            ("Withdrawal", "withdrawal_pct", -1, lambda v: pct(v, 1) if v is not None else "—"),
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
        ax.text(j + 0.5, -0.12, name, ha="center", va="bottom", fontsize=10.5, fontweight="bold")
        base = val(sc[0], key)
        for i, s in enumerate(sc):
            v = val(s, key)
            rel = 0 if not base or v is None else (v - base) / abs(base)
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
    comp = CMP / "comparison"
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
             "; ".join(f"P({short(w['endpoint']).split(',')[0]} ≥ {w['required']}) {pct(at[w['endpoint']]['p_meets'])}" for w in F["evaluability"] if w.get("required"))
             + f"\nat {TARGET} enrolled",
             " / ".join(f"{v}" for v in ev_act.values()) + " evaluable (AUC / Ctrough)")]
    fig = frame("Feasibility signals compared with what happened in the case-study trial",
                "The feasibility assessment flagged the demanding accrual and gave realistic variability and safety inputs; "
                "composition depended on geography.")
    ax = fig.add_axes([0.03, 0.37, 0.94, 0.52])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows) + 0.8)
    ax.invert_yaxis()
    xs = [(0.0, 0.25, "Planning question", INK), (0.27, 0.42, "Feasibility assessment", ENR),
          (0.71, 0.29, "What subsequently occurred", OBS)]
    for x, w, t, col in xs:
        ax.text(x, 0.35, t, fontsize=13.5, fontweight="bold", color=col, va="center")
    for i, r in enumerate(rows):
        yv = i + 1.2
        ax.add_patch(plt.Rectangle((0, yv - 0.45), 1, 0.9, color=PALE if i % 2 == 0 else "white", lw=0))
        for (x, w, _, col), txt in zip(xs, r, strict=True):
            ax.text(x + 0.005, yv, txt, fontsize=11, va="center", color=col if col != INK else INK, fontweight="bold" if x == 0 else "normal")
    _synthetic_control_panel(fig)
    save(fig, "Figure9_retrospective")


def _synthetic_control_panel(fig):
    """Synthetic-control exploration: the control arm's serious-AE share predicted without seeing it."""
    f = CMP / "comparison" / "control" / "control_external.json"
    if not f.exists():
        return
    rows = [r for r in json.loads(f.read_text(encoding="utf-8"))["rows"] if r["outcome"] == "serious_ae" and r["population"] == "registry_experimental"]
    pick = [("map_prior", "Historical controls (meta-analytic)", CAND), ("contextual_robust", "Synthetic control (contextual model)", ALT)]
    ax = fig.add_axes([0.3, 0.1, 0.4, 0.2])
    for i, (m, lab, col) in enumerate(pick):
        r = next((x for x in rows if x["method"] == m), None)
        if not r:
            continue
        ax.plot([r["lower"], r["upper"]], [i, i], color=col if col != CAND else "#8A8A8A", lw=3)
        ax.plot(r["predicted"], i, "o", color=col if col != CAND else "#8A8A8A", ms=9)
        ax.text(-0.02, i, lab, ha="right", va="center", fontsize=11, transform=ax.get_yaxis_transform())
        obs = r["observed"]
    ax.axvline(obs, color=OBS, lw=2)
    ax.text(obs, len(pick) - 0.35, f"observed control arm {pct(obs, 1)}", ha="center", fontsize=11, color=OBS)
    ax.set_yticks([])
    ax.set_ylim(-0.6, len(pick) - 0.2)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    ax.spines["left"].set_visible(False)
    ax.set_title("Synthetic-control exploration: control-arm serious AE (95% interval)", loc="left", fontsize=12.5, fontweight="bold")
    fig.text(0.72, 0.2, "Generating a synthetic control was feasible,\nbut its uncertainty was too wide to\nsupport replacing the control arm.",
             fontsize=11.5, color=INK, va="center")


# ---------------------------------------------------------------- Figure 7
SCEN_COLOURS = {"Original protocol": ENR, "Less frequent follow-up": ELIG, "One fewer follow-up visit": "#5FB89C",
                "Higher-burden follow-up": SAFE}
BURDEN_LABELS = {"log2_duration_months": "Participation duration (per doubling)", "log2_visits_per_month": "Visit frequency (per doubling)",
                 "log2_outcome_measures": "Number of assessments (per doubling)", "log2_enrolled": "Enrolment (per doubling)",
                 "start_year_decade": "Start year (per decade)", "industry": "Industry sponsor", "randomized": "Randomised design"}


def figure7():
    wm = LONG.get("withdrawal_model") or {}
    bs = {b["scenario"]: b for b in LONG.get("burden_scenarios") or []}
    orig, low, high = bs.get("Original protocol"), bs.get("Less frequent follow-up"), bs.get("Higher-burden follow-up")
    ct = min((w for w in EVW if w.get("required")), key=lambda w: w["share"])
    concl = "Protocol burden is associated with withdrawal; reducing follow-up burden changed endpoint feasibility only modestly."
    if orig and low and high:
        concl = (f"Changing follow-up frequency moved expected withdrawal by under "
                 f"{max(abs(high['withdrawn_share'] - orig['withdrawn_share']), abs(low['withdrawn_share'] - orig['withdrawn_share'])) * 100 + 0.05:.1f} "
                 f"points; endpoint feasibility is barely sensitive to follow-up burden.")
    fig = frame("Protocol burden shapes retention and endpoint feasibility", concl)
    # A: adjusted associations across registry trials
    a = fig.add_axes([0.27, 0.53, 0.22, 0.33])
    coefs = wm.get("coefficients") or {}
    keys = [k for k in BURDEN_LABELS if k in coefs]
    y = np.arange(len(keys))[::-1]
    for yv, k in zip(y, keys, strict=True):
        c = coefs[k]
        burden = k in ("log2_duration_months", "log2_visits_per_month", "log2_outcome_measures")
        col = ENR if burden else "#8FB8D8"
        a.plot(c["ci95"], [yv, yv], color=col, lw=2.4)
        a.plot(c["or"], yv, "o", color=col, ms=7 if burden else 5)
        a.text(max(c["ci95"][1], 1.0) * 1.02, yv, f"{c['or']:.2f}", va="center", fontsize=10, color=col)
    a.axvline(1, color=MUTED, lw=1)
    a.set_xscale("log")
    a.set_xticks([0.8, 1, 1.25, 1.6, 2])
    a.set_xticklabels(["0.8", "1", "1.25", "1.6", "2"])
    a.set_yticks(y)
    a.set_yticklabels([BURDEN_LABELS[k] for k in keys], fontsize=10.5)
    a.set_xlabel("Adjusted withdrawal odds ratio (95% CI)", fontsize=11)
    a.set_title(f"A. Protocol characteristics associated with withdrawal\n({wm.get('trials', 0):,} registry trials, "
                f"{wm.get('participants', 0) / 1e3:.0f}k participants)", loc="left", fontsize=12, fontweight="bold", x=-0.95)
    # B: retention under three follow-up schedules
    b = fig.add_axes([0.6, 0.53, 0.37, 0.33])
    for name in ("Less frequent follow-up", "Original protocol", "Higher-burden follow-up"):
        sc = bs.get(name)
        if not sc:
            continue
        days = [r["day"] / 30.44 for r in sc["retention"]]
        b.plot(days, [r["not_withdrawn"] for r in sc["retention"]], color=SCEN_COLOURS[name], lw=2.4)
        k = ("Less frequent follow-up", "Original protocol", "Higher-burden follow-up").index(name)
        how = sc["how"].split(" instead")[0].replace("survival follow-up ", "").split(" (")[0]
        b.text(0.98, 0.95 - 0.08 * k, f"{name}: follow-up {how}" if name != "Original protocol" else "Original protocol",
               transform=b.transAxes, ha="right", fontsize=10.5, color=SCEN_COLOURS[name])
    b.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    b.set_xlabel("Months since enrolment", fontsize=11)
    b.set_ylabel("Not withdrawn", fontsize=11)
    b.set_xlim(0, (orig["retention"][-1]["day"] / 30.44 if orig else 24) + 1)
    b.set_title("B. Withdrawal risk accumulates across the patient journey", loc="left", fontsize=12, fontweight="bold")
    fig.text(0.6, 0.455, "Trial-level association; patient-level risk accrues over each patient's attended visits.", fontsize=9.5, color=MUTED)
    # C: treatment delivery and data completeness
    c = fig.add_axes([0.27, 0.15, 0.2, 0.25])
    td = LONG.get("treatment_delivery") or {}
    rows = [("Treatment delivery\n(doses given / scheduled)", td.get("delivery"), 0.0, 0.0)] if td.get("delivery") is not None else []
    for comp in LONG.get("completeness") or []:
        if comp["category"] in ("Laboratory (safety) assessments", "Tumour assessments", "Survival follow-up visits"):
            rows.append((comp["category"].replace(" (safety)", ""), comp["attended"], comp["lost_withdrawal"], comp["lost_death"]))
    for pkc in LONG.get("pk_capture") or []:
        need = pkc["protocol_course_reaches"] or 1
        rows.append((f"PK samples: {short(pkc['endpoint']).split(',')[0]}", pkc["captured"] / need, pkc["lost_withdrawal"] / need, pkc["lost_death"] / need))
    yc = np.arange(len(rows))[::-1]
    for yv, (lab, att, lw_, ld) in zip(yc, rows, strict=True):
        c.barh(yv, att, color=ENR, height=0.6)
        c.barh(yv, lw_, left=att, color=LOSS, height=0.6)
        c.barh(yv, ld, left=att + lw_, color=DEATH, height=0.6)
        c.text(1.01, yv, pct(att, 0), va="center", fontsize=10)
    c.set_yticks(yc)
    c.set_yticklabels([r[0] for r in rows], fontsize=10)
    c.set_xlim(0, 1.12)
    c.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    c.set_title("C. Treatment delivery and data completeness", loc="left", fontsize=12, fontweight="bold", x=-0.95)
    fig.text(0.27, 0.075, "■ captured", color=ENR, fontsize=10)
    fig.text(0.325, 0.075, "■ lost: withdrawal", color=LOSS, fontsize=10)
    fig.text(0.415, 0.075, "■ lost: death", color=DEATH, fontsize=10)
    fig.text(0.27, 0.052, "Dose delays and missed doses are not modelled: delivery is an upper bound.", color=MUTED, fontsize=9)
    # D: endpoint consequence by schedule
    d = fig.add_axes([0.68, 0.15, 0.29, 0.25])
    names = [n for n in ("Less frequent follow-up", "One fewer follow-up visit", "Original protocol", "Higher-burden follow-up") if n in bs]
    yd = np.arange(len(names))[::-1]
    for yv, n in zip(yd, names, strict=True):
        sc = bs[n]
        v = sc["evaluable"][ct["endpoint"]]
        d.plot(v, yv, "o", color=SCEN_COLOURS[n], ms=10)
        d.text(v + 4, yv, f"{v:.0f} evaluable · withdrawal {pct(sc['withdrawn_share'], 1)} · P(≥{ct['required']}) {pct(sc['p_required'][ct['endpoint']])}",
               va="center", fontsize=10, color=SCEN_COLOURS[n])
    d.axvline(ct["required"], color=OBS, lw=1.6)
    d.text(ct["required"], len(names) - 0.4, f"required {ct['required']}", ha="center", fontsize=10, color=OBS)
    d.set_yticks(yd)
    d.set_yticklabels(names, fontsize=10.5)
    lo_v = min(bs[n]["evaluable"][ct["endpoint"]] for n in names)
    d.set_xlim(min(lo_v, ct["required"]) - 15, max(bs[n]["evaluable"][ct["endpoint"]] for n in names) + 175)
    d.set_ylim(-0.6, len(names) - 0.1)
    d.set_xlabel(f"{short(ct['endpoint']).split(',')[0]}-evaluable participants (of {TARGET})", fontsize=11)
    d.set_title("D. Visit burden and evaluable endpoint data", loc="left", x=-0.3, fontsize=12, fontweight="bold")
    save(fig, "Figure7_longitudinal")


# ---------------------------------------------------------------- Supplementary figures
def supp_s1_trace():
    tr = LONG.get("trace")
    if not tr:
        return
    lanes = [("Treatment", lambda e: e["category"] == "treatment"), ("Laboratory", lambda e: e["category"] == "laboratory"),
             ("Adverse events", lambda e: e["category"] == "adverse event"), ("Tumour assessments", lambda e: e["category"] == "tumour assessment"),
             ("Follow-up and disposition", lambda e: e["category"] in ("follow-up", "disposition", "screening", "baseline"))]
    cols = {"Treatment": ENR, "Laboratory": "#8FB8D8", "Adverse events": SAFE, "Tumour assessments": EVAL, "Follow-up and disposition": OBS}
    fig = frame(f"Supplementary Figure S1. One simulated participant's record ({arm_name(tr['arm'])} arm)",
                "Every visit, administration, adverse event, assessment and exit is generated from the protocol and registry evidence.")
    ax = fig.add_axes([0.42, 0.14, 0.55, 0.7])
    for i, (lane, test) in enumerate(lanes):
        ev = [e for e in tr["events"] if test(e)]
        yv = len(lanes) - 1 - i
        ax.scatter([e["day"] for e in ev], [yv] * len(ev), color=cols[lane], s=36, zorder=2)
        for e in ev:
            label = ((lane == "Adverse events" and "serious" in (e.get("result") or ""))
                     or (lane == "Follow-up and disposition" and e["category"] in ("disposition", "screening"))
                     or (lane == "Tumour assessments" and "progressive" in (e.get("result") or "")))
            if label:
                ax.text(e["day"], yv + 0.18, ("progressive disease" if lane == "Tumour assessments" else str(e.get("item") or "").replace("_", " ")[:22]), rotation=35, fontsize=9, color=cols[lane], ha="left")
    ax.set_yticks(range(len(lanes)))
    ax.set_yticklabels([lane for lane, _ in lanes][::-1])
    ax.set_ylim(-0.6, len(lanes) - 0.2)
    ax.set_xlabel("Study day")
    b = tr.get("baseline") or {}
    shown = []
    for k, v in b.items():
        if k == "patient_id":
            continue
        val = v.get("value") if isinstance(v, dict) else v
        if isinstance(val, dict) or val is None:
            continue
        name = k.split(":", 1)[-1].replace("_", " ")
        if k.startswith("umls:") or re.fullmatch(r"[Cc]\d{7}", name):
            continue                                     # concept-coded variables are not shown by code
        val = {True: "yes", False: "no"}.get(val, val) if isinstance(val, bool) else val
        shown.append(f"{name}: {val:.1f}" if isinstance(val, float) else f"{name}: {str(val).replace('_', ' ')}")
    fig.text(0.015, 0.84, "Baseline", fontsize=11, fontweight="bold")
    fig.text(0.015, 0.82, "\n".join(shown[:22]), fontsize=8.5, va="top", color=INK)
    save(fig, "S1_patient_record")


def supp_s2_modifiers():
    mod = ((LONG.get("withdrawal_model") or {}).get("modifiers") or {})
    eff = mod.get("effects") or {}
    if not eff:
        return
    fig = frame("Supplementary Figure S2. Evidence for patient-level modifiers of withdrawal",
                "Arm-level (ecological) associations, reported for transparency and not applied to simulated patients.")
    ax = fig.add_axes([0.3, 0.2, 0.6, 0.6])
    labels = {"age_per_10_years": "Arm mean age (per 10 years)", "female_share": "All-female vs all-male arm",
              "ecog1_share": "All ECOG ≥1 vs all ECOG 0 arm"}
    keys = [k for k in labels if k in eff]
    y = np.arange(len(keys))[::-1]
    for yv, k in zip(y, keys, strict=True):
        e = eff[k]
        ax.plot(e["ci95"], [yv, yv], color=ENR, lw=2.4)
        ax.plot(e["or"], yv, "o", color=ENR, ms=8)
        ax.text(e["ci95"][1] * 1.05, yv, f"{e['or']:.2f} ({e['ci95'][0]:.2f}-{e['ci95'][1]:.2f})", va="center", fontsize=11)
    ax.axvline(1, color=MUTED, lw=1)
    ax.set_xscale("log")
    ax.set_yticks(y)
    ax.set_yticklabels([labels[k] for k in keys])
    ax.set_xticks([0.5, 1, 2, 5, 10])
    ax.set_xticklabels(["0.5", "1", "2", "5", "10"])
    ax.set_xlabel("Adjusted withdrawal odds ratio (95% CI), arm level")
    ax.set_title(f"{mod.get('arms', 0):,} arms of {mod.get('trials', 0):,} trials; adjusted for the trial's burden and design", loc="left",
                 fontsize=12)
    save(fig, "S2_withdrawal_modifiers")


def supp_s3_control_benchmark():
    f = Path("data/corpus_v2/patient_risk/benchmark/benchmark_summary.json")
    if not f.exists():
        return
    summ = json.loads(f.read_text(encoding="utf-8"))["summary"]
    methods = [("contextual_robust", "Synthetic control (contextual model)"), ("evidence_calibrated", "Evidence-calibrated"),
               ("map_prior", "Meta-analytic prior"), ("outcome_regression", "Outcome regression"), ("naive_pooled", "Naive pooling")]
    fig = frame("Supplementary Figure S3. Hidden-control benchmark across registry trials",
                "Methods that cover the real control arm do so with wide intervals; narrow methods miss it often.")
    for j, (outcome, title) in enumerate((("serious_ae", "Serious adverse event"), ("death", "Death"))):
        ax = fig.add_axes([0.24 + j * 0.39, 0.15, 0.3, 0.68])
        y = np.arange(len(methods))[::-1]
        for yv, (m, lab) in zip(y, methods, strict=True):
            r = summ.get(f"{outcome}|{m}")
            if not r:
                continue
            ax.barh(yv, r["coverage_95"], color=ALT if m == "contextual_robust" else CAND, height=0.6)
            ax.text(r["coverage_95"] + 0.01, yv, f"coverage {pct(r['coverage_95'])} · width {pct(r['median_interval_width'])} · "
                    f"bias {r['bias'] * 100:+.1f} pts", va="center", fontsize=9.5)
        ax.axvline(0.95, color=OBS, lw=1, ls="--")
        ax.set_xlim(0, 1.9)
        ax.set_xticks([0, 0.5, 0.95])
        ax.set_xticklabels(["0%", "50%", "95%"])
        ax.set_yticks(y)
        ax.set_yticklabels([lab for _, lab in methods] if j == 0 else [], fontsize=10.5)
        ax.set_title(f"{title} ({summ.get(f'{outcome}|contextual_robust', {}).get('trials', 0)} trials)", loc="left", fontweight="bold", fontsize=12)
    save(fig, "S3_control_benchmark")


def supp_s4_all_criteria():
    cr = [c for c in F["criteria"] if c["excluded"] > 0]
    fig = plt.figure(figsize=(W, max(H, 0.28 * len(cr) + 2)))
    fig.text(0.04, 0.97, "Supplementary Figure S4. Candidates excluded by every eligibility criterion", fontsize=17, fontweight="bold", va="top")
    ax = fig.add_axes([0.42, 0.05, 0.5, 0.86])
    y = np.arange(len(cr))[::-1]
    ax.barh(y, [c["pct_excluded"] for c in cr], color="#9A9A9A", height=0.65)
    for yv, c in zip(y, cr, strict=True):
        ax.text(c["pct_excluded"] + 0.002, yv, f"{pct(c['pct_excluded'], 1)}  (+{100 * c['gain_if_relaxed'] / F['candidates']:.1f} if relaxed)",
                va="center", fontsize=9.5)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{tidy(c['label'])} · {c['category']}" for c in cr], fontsize=9)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    ax.set_xlabel("Candidates excluded")
    save(fig, "S4_all_criteria")


def supp_s5_sensitivity():
    if FB is F:
        return

    def ct_share(doc):
        w = min((w for w in doc["evaluability"] if w.get("required")), key=lambda w: w["share"])
        at = next(r for r in doc["evaluable_curve"] if r["enrolled"] == TARGET)
        return w["share"], at[w["endpoint"]]["p_meets"]
    rows = [("Serious AE, simulated patients", FB["overall_sae"], F["overall_sae"]),
            ("On study at day 126 (Ctrough evaluable)", ct_share(FB)[0], ct_share(F)[0]),
            ("P(≥240 Ctrough evaluable at 378)", ct_share(FB)[1], ct_share(F)[1]),
            ("Withdrawal (any time)", (FB.get("withdrawal_rate") and next(iter(FB["withdrawal_rate"].values()))),
             ((LONG.get("burden_scenarios") or [{}])[0].get("withdrawn_share")))]
    fig = frame("Supplementary Figure S5. Sensitivity of feasibility outputs to the patient-journey calibration",
                "The calibration anchors serious AEs to the evidence, takes progression from validated evidence and makes withdrawal burden-dependent.")
    ax = fig.add_axes([0.38, 0.18, 0.55, 0.62])
    y = np.arange(len(rows))[::-1]
    for yv, (lab, a_, b_) in zip(y, rows, strict=True):
        if a_ is None or b_ is None:
            continue
        ax.plot([a_, b_], [yv, yv], color="#BBBBBB", lw=2)
        ax.plot(a_, yv, "o", color=CAND, ms=11)
        ax.plot(b_, yv, "o", color=ENR, ms=11)
        ax.text(a_, yv + 0.22, pct(a_, 1), ha="center", fontsize=10, color=MUTED)
        ax.text(b_, yv - 0.32, pct(b_, 1), ha="center", fontsize=10, color=ENR)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=11.5)
    ax.set_xlim(0, 1.05)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))
    fig.text(0.38, 0.84, "● uncalibrated journey", color="#8A8A8A", fontsize=12)
    fig.text(0.56, 0.84, "● calibrated journey", color=ENR, fontsize=12)
    save(fig, "S5_sensitivity")


for f in (figure1, figure2, figure3, figure4, figure5, figure6, figure7, figure8, figure9,
          supp_s1_trace, supp_s2_modifiers, supp_s3_control_benchmark, supp_s4_all_criteria, supp_s5_sensitivity, supp_s6_safety):
    f()
print("figures written to", OUT)
