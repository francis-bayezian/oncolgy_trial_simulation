"""The six paper figures of the NCT06604442 synthetic-comparator study (paper step 15), from frozen files only (and,
for figures 3 and 6, the observed targets read after the freeze). Run with .venv-figures/Scripts/python.exe.

Usage: .venv-figures/Scripts/python.exe scripts/sca_paper_figures.py [FREEZE_DIR]
"""

import csv
import json
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

F = Path(sys.argv[1] if len(sys.argv) > 1 else "analysis_freeze/NCT06604442")
OUT = F / "figures"
REP = Path("data/trial/runs/NCT06604442/v4.1.0/replicates")
BLUE, ORANGE, GREY, RED, GREEN = "#1f4e79", "#d9822b", "#8c8c8c", "#b22222", "#2e7d32"
mpl.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "font.family": "DejaVu Sans"})


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300 if ext == "png" else None, bbox_inches="tight")
    plt.close(fig)


def master(src):
    return list(csv.DictReader(open(F / "step2_master" / f"master_simulation_{src}.csv", encoding="utf-8")))


def col(rows, k):
    return np.array([float(r[k]) for r in rows if r[k] not in ("", "None", "nan")])


OBS = json.loads((F / "post_reveal" / "observed_targets.json").read_text(encoding="utf-8"))
SCA = [json.loads(x) for x in open(F / "step10_sca_internal" / "sca_per_trial.jsonl", encoding="utf-8")]
LIT, DES, PRE = master("literature"), master("design"), master("prestart")


def box(ax, x, y, w, h, text, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.03", fc=color, ec="none", alpha=0.95))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color="white", fontsize=8)


def arrow(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=GREY, lw=1.2))


# ---------------------------------------------------------------- Figure 1: the chain
def fig1():
    fig, ax = plt.subplots(figsize=(13, 3.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    steps = [("Protocol PDF\n(NCT06604442)", BLUE), ("Executable\nStudySpec\n(100% faithful)", BLUE), ("100 virtual trials\n(new patients,\nnew trial each)", BLUE),
             ("Feasibility +\nstress tests", BLUE), ("Synthetic\ncomparator\n(piflufolastat\nmasked)", ORANGE), ("FREEZE\n(checksums)", GREY),
             ("Reveal the\ncompleted trial\n(aggregates)", GREEN)]
    w, gap = 1.6, 0.25
    for i, (t, c) in enumerate(steps):
        x = 0.1 + i * (w + gap)
        box(ax, x, 1.2, w, 1.2, t, c)
        if i:
            arrow(ax, (x - gap, 1.8), (x, 1.8))
    save(fig, "fig1_chain")


# ---------------------------------------------------------------- Figure 2: screening funnel and eligibility pressure
def fig2():
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    gen, elig = col(LIT, "generated"), col(LIT, "eligible")
    scr, enr, use = col(LIT, "screened_to_target"), col(LIT, "participants_enrolled"), col(LIT, "usable_pairs")
    stages = [("generated", gen), ("eligible", elig)]
    ax = axes[0]
    ax.bar([s for s, _ in stages], [np.median(v) for _, v in stages], color=BLUE)
    for i, (_, v) in enumerate(stages):
        ax.text(i, np.median(v), f"{np.median(v):,.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_title("A. Source population (per trial)", loc="left")
    ax.set_ylabel("patients")
    ax = axes[1]
    labels = ["screened\nto target", "enrolled", "usable\npairs"]
    vals = [scr, enr, use]
    ax.bar(labels, [np.median(v) for v in vals], color=BLUE,
           yerr=[[np.median(v) - np.percentile(v, 10) for v in vals], [np.percentile(v, 90) - np.median(v) for v in vals]], capsize=4, ecolor=GREY)
    ax.set_title("B. Screening funnel (median, p10-p90)", loc="left")
    stress = [r for r in csv.DictReader(open(F / "step5_stress" / "stress_tests.csv", encoding="utf-8")) if r["family"] == "eligibility"]
    ax = axes[2]
    y = np.arange(len(stress))
    med = [float(r["v2"]) for r in stress]
    ax.errorbar(med, y, xerr=[[m - float(r["v1"]) for m, r in zip(med, stress)], [float(r["v3"]) - m for m, r in zip(med, stress)]], fmt="o",
                color=BLUE, ecolor=GREY, capsize=3)
    ax.set_yticks(y, [r["scenario"] for r in stress])
    ax.set_xlabel("eligible % of generated")
    ax.set_title("C. Criterion stress test (calibrated, A16)", loc="left")
    fig.tight_layout()
    save(fig, "fig2_screening")


# ---------------------------------------------------------------- Figure 3: recruitment distribution (+ observed afterwards)
def fig3():
    months = col(LIT, "enrol_days_to_target") / 30.44
    stress = {r["scenario"]: r for r in csv.DictReader(open(F / "step5_stress" / "stress_tests.csv", encoding="utf-8")) if r["family"] == "recruitment"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axes[0]
    ax.hist(months, bins=20, color=BLUE, alpha=0.85)
    ax.axvline(OBS["conduct"]["enrolment_months_approx"], color=RED, ls="--")
    ax.text(OBS["conduct"]["enrolment_months_approx"] + 0.5, ax.get_ylim()[1] * 0.9, "observed ~8 months\n(added after the freeze)", color=RED, fontsize=8)
    ax.set_xlabel("months to enrol 52 participants (central accrual, 16.4/year)")
    ax.set_ylabel("simulated trials")
    ax.set_title("A. Frozen baseline (100 trials)", loc="left")
    ax = axes[1]
    names = ["slow", "central", "fast"]
    for i, n in enumerate(names):
        r = stress[n]
        ax.plot([float(r["v1"]), float(r["v3"])], [i, i], color=BLUE, lw=6, alpha=0.5)
        ax.plot(float(r["v2"]), i, "o", color=BLUE)
    ax.axvline(OBS["conduct"]["enrolment_months_approx"], color=RED, ls="--")
    ax.set_yticks(range(3), [f"{n}\n({float(stress[n]['v5']):.1f}/year)" for n in names])
    ax.set_xscale("log")
    ax.set_xlabel("months to enrol (log scale; p10-p90, median)")
    ax.set_title("B. Accrual stress test", loc="left")
    fig.tight_layout()
    save(fig, "fig3_recruitment")


# ---------------------------------------------------------------- Figure 4: one synthetic participant, paired exposures
def fig4():
    rd = REP / "r001"
    adsl = list(csv.DictReader(open(rd / "journey" / "adsl.csv", encoding="utf-8")))
    pairs = {r["participant"]: r for r in csv.DictReader(open(rd / "paired_measurements_literature.csv", encoding="utf-8"))}
    pid = next(p for p in pairs)
    recs = sorted([r for r in adsl if r["USUBJID"].split("-P")[0] == pid], key=lambda r: r["USUBJID"])
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.set_xlim(-16, 45)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.plot([-15, 42], [2, 2], color=GREY, lw=1)
    coh = [json.loads(c) for c in open(next((rd / "cohorts").glob("cohort_*.jsonl")), encoding="utf-8")]
    patient = next(c["patient_id"] for c in coh if (c.get("patient_subject") or c["subject_id"].split("-P")[0]) == pid)
    el = next((json.loads(x) for x in open(rd / "eligibility" / "eligibility.jsonl", encoding="utf-8") if json.loads(x)["patient_id"] == patient), {})
    events = [(-14, f"Screening\n({el.get('status', '?').lower()}: {len(el.get('resolved') or {})} rules\nevaluated)", BLUE), (1, f"Scan 1: piflufolastat\nbladder SUVmean {float(pairs[pid]['reference']):.1f}", ORANGE),
              (float(recs[-1]["TRTEDY"] or 10), f"Scan 2: flotufolastat\nbladder SUVmean {float(pairs[pid]['index']):.1f}", BLUE),
              (float(recs[-1]["TRTEDY"] or 10) + 30, "End of reporting\nwindow (30 days)", GREY)]
    for k, (d, t, c) in enumerate(events):
        ax.plot(d, 2, "o", color=c, ms=9)
        up = k != 2                                  # the second scan's label below the line (the scans are days apart)
        ax.text(d, 2.35 if up else 1.25, t, ha="center", va="bottom" if up else "top", fontsize=8)
        ax.text(d, 1.75 if k != 2 else 2.2, f"day {d:g}", ha="center", va="top" if k != 2 else "bottom", fontsize=7.5, color=GREY)
    save(fig, "fig4_participant")


# ---------------------------------------------------------------- Figure 5: synthetic comparator experiment
def fig5():
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8), gridspec_kw={"width_ratios": [1, 1.3]})
    ax = axes[0]
    ax.axis("off")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 4)
    box(ax, 0.1, 2.6, 1.7, 0.9, "flotufolastat\nVISIBLE", BLUE)
    box(ax, 2.2, 2.6, 1.7, 0.9, "piflufolastat\nMASKED", GREY)
    box(ax, 2.2, 1.3, 1.7, 0.9, "synthetic comparator\n(frozen model,\nallowed inputs)", ORANGE)
    box(ax, 1.15, 0.05, 1.7, 0.9, "contrast → reveal\n→ error", GREEN)
    arrow(ax, (3.05, 2.6), (3.05, 2.2))
    arrow(ax, (3.05, 1.3), (2.4, 0.95))
    arrow(ax, (0.95, 2.6), (1.6, 0.95))
    ax.set_title("A. Design (internal validation)", loc="left")
    ax = axes[1]
    for name, c in (("SCA-A", ORANGE), ("SCA-B", BLUE), ("SCA-R", GREEN)):
        b = [x["signed_bias"] for x in SCA if x["experiment"] == name]
        ax.hist(b, bins=20, alpha=0.6, color=c, label=f"{name}: bias {np.mean(b):+.1f}, conclusion agrees "
                f"{sum(x['same_conclusion'] for x in SCA if x['experiment'] == name)}/100")
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("synthetic-comparator contrast minus true contrast (SUVmean)")
    ax.set_ylabel("simulated trials")
    ax.legend(fontsize=7.5, frameon=False)
    ax.set_title("B. Error across 100 virtual trials", loc="left")
    fig.tight_layout()
    save(fig, "fig5_sca")


# ---------------------------------------------------------------- Figure 6: reality check
def fig6():
    e, c = OBS["endpoint"], OBS["conduct"]
    sca_b = [x for x in SCA if x["experiment"] == "SCA-B"]
    sca_a = [x for x in SCA if x["experiment"] == "SCA-A"]
    rows = [("paired contrast (literature truth)", col(LIT, "median_difference"), e["paired_difference"]["median"]),
            ("paired contrast (design assumption)", col(DES, "median_difference"), e["paired_difference"]["median"]),
            ("synthetic comparator median (P1 model)", np.array([x["synthetic_comparator"]["median"] for x in sca_b]), e["comparator_piflufolastat"]["median"]),
            ("synthetic comparator median (P2 model)", np.array([x["synthetic_comparator"]["median"] for x in sca_a]), e["comparator_piflufolastat"]["median"]),
            ("screen-pass rate, %", col(LIT, "eligible_pct"), 100 * c["dosed"] / c["screened"]),
            ("missing pairs, % of enrolled", 100 * col(LIT, "missing_pairs") / 52, 100 * c["missing_pairs"] / c["dosed"]),
            ("months to enrol (central)", col(LIT, "enrol_days_to_target") / 30.44, c["enrolment_months_approx"])]
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for i, (lab, v, o) in enumerate(rows):
        lo, md, hi = np.percentile(v, [10, 50, 90])
        lo5, hi95 = np.percentile(v, [5, 95])
        inside = lo5 <= o <= hi95
        ax.plot([lo / md, hi / md], [i, i], color=BLUE, lw=6, alpha=0.45)
        ax.plot(1, i, "o", color=BLUE)
        ax.plot(o / md, i, "*", color=GREEN if inside else RED, ms=12)
        ax.text(max(hi / md, o / md) * 1.06, i, f"sim {md:.1f} [{lo:.1f}-{hi:.1f}]  obs {o:.1f}", va="center", fontsize=7.5)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xscale("log")
    ax.axvline(1, color=GREY, lw=0.6)
    ax.set_xlabel("value relative to the frozen simulated median (log scale); bar = p10-p90; star = observed (green inside p5-p95)")
    ax.invert_yaxis()
    save(fig, "fig6_reality_check")


if __name__ == "__main__":
    for f in (fig1, fig2, fig3, fig4, fig5, fig6):
        f()
    print(sorted(p.name for p in OUT.glob("*.png")))
