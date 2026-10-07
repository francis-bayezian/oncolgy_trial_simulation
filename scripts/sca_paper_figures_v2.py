"""Journal figures (redesign) for the NCT06604442 virtual-trial and synthetic-comparator study.

Main: 1 protocol to virtual trial (conceptual); 2 eligibility pressure and screening burden; 3 recruitment predictive
distribution; 4 operating-characteristic surface; 5 synthetic-comparator transportability; 6 benchmark against the
completed trial (native units). Supplementary: S1 longitudinal participant trace; S2 effect-size curve; S3 eligibility
criterion distributions; S4 synthetic comparator vs within-patient correlation.

No titles in the figures (captions belong to the manuscript); panel letters only. Okabe-Ito palette; 180 mm width.
Run with .venv-figures/Scripts/python.exe scripts/sca_paper_figures_v2.py [FREEZE_DIR]
"""

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from scipy import stats  # noqa: E402

sys.path.insert(0, ".")
from clinical_asset.trial.predictive import percentile_from_quantiles  # noqa: E402

F = Path(sys.argv[1] if len(sys.argv) > 1 else "analysis_freeze/NCT06604442")
OUT = F / "figures"
REP = Path("data/trial/runs/NCT06604442/v4.1.0/replicates")
W2 = 7.09                                   # 180 mm
BLUE, ORANGE, VERM, GREEN, SKY, PURPLE, GREY, INK = "#0072B2", "#E69F00", "#D55E00", "#009E73", "#56B4E9", "#CC79A7", "#8C8C8C", "#222222"
OBS_C = VERM
mpl.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7,
                     "legend.fontsize": 6.8, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
                     "xtick.major.width": 0.6, "ytick.major.width": 0.6, "font.family": "DejaVu Sans", "pdf.fonttype": 42,
                     "svg.fonttype": "none", "lines.linewidth": 1.0})


# ---------------------------------------------------------------- data
def master(src):
    return list(csv.DictReader(open(F / "step2_master" / f"master_simulation_{src}.csv", encoding="utf-8")))


def col(rows, k):
    return np.array([float(r[k]) for r in rows if r[k] not in ("", "None", "nan")])


LIT, DES = master("literature"), master("design")
SCA = [json.loads(x) for x in open(F / "step10_sca_internal" / "sca_per_trial.jsonl", encoding="utf-8")]
OBS = json.loads((F / "post_reveal" / "observed_targets.json").read_text(encoding="utf-8"))
PLAN = json.loads(Path("data/locked/NCT06604442/planning_v4.1.0/planning_report.json").read_text(encoding="utf-8"))
ACC = PLAN["accrual"]["historical_model"]["enrollment_duration_years"]["percentiles"]
ACC_BY = PLAN["accrual"]["historical_model"]["p_enrollment_complete_by"]
STRESS = list(csv.DictReader(open(F / "step5_stress" / "stress_tests.csv", encoding="utf-8")))
SPEC = json.loads(Path("data/locked/NCT06604442/studyspec_v4.1.0/studyspec.json").read_text(encoding="utf-8"))


def save(fig, name, sub=""):
    d = OUT / sub if sub else OUT
    d.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(d / f"{name}.{ext}", dpi=600 if ext == "png" else None, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


def letter(ax, s, x=-0.02, y=1.02):
    ax.text(x, y, s, transform=ax.transAxes, fontsize=9, fontweight="bold", va="bottom", ha="right")


def obs_star(ax, x, y, label=True):
    ax.plot(x, y, marker="*", ms=10, color=OBS_C, mec="white", mew=0.5, zorder=6, label="Observed (NCT06604442)" if label else None)


def q(v, p):
    return float(np.percentile(v, p))


# ---------------------------------------------------------------- Figure 1
def fig1():
    fig = plt.figure(figsize=(W2, 5.0))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 70)
    ax.axis("off")

    def card(x, y, w, h, text, fc="white", ec=GREY, tc=INK, fs=7, lw=0.7):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=1.2", fc=fc, ec=ec, lw=lw))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, linespacing=1.25)

    def down(y0, y1):
        ax.add_patch(FancyArrowPatch((50, y0), (50, y1), arrowstyle="-|>", mutation_scale=10, color=GREY, lw=0.9))

    # A. protocol intent
    ax.text(1.5, 67.5, "A", fontsize=10, fontweight="bold", va="top")
    ax.text(5, 67.5, "Protocol intent", fontsize=8, fontweight="bold", va="top", color=INK)
    frags = ["Eligibility\n13 criteria", "52 evaluable\nparticipants", "Two paired\nPSMA PET scans", "Scan interval\n1-10 days", "Endpoint\npaired bladder\nSUVmean"]
    for i, t in enumerate(frags):
        card(4 + i * 19, 55.5, 16.5, 8, t, fc="#F4F7FB", ec=BLUE)
    down(54, 50.5)

    # B. patient-level trial representation
    ax.text(1.5, 49.5, "B", fontsize=10, fontweight="bold", va="top")
    ax.text(5, 49.5, "Patient-level virtual trial", fontsize=8, fontweight="bold", va="top")
    rng = np.random.default_rng(3)
    stages = [("Candidate\npopulation", 140, 1.0), ("Screening", 90, 0.79), ("Enrolment", 40, 1.0), ("Paired\nexposures", 40, 1.0)]
    xs = [6, 27, 48, 69]
    for (lab, n, keep), x0 in zip(stages, xs):
        px, py = x0 + rng.uniform(0, 15, n), 31 + rng.uniform(0, 12, n)
        ok = rng.random(n) < keep
        ax.scatter(px[ok], py[ok], s=3, color=BLUE, lw=0)
        ax.scatter(px[~ok], py[~ok], s=3, color="#C9C9C9", lw=0)
        if lab.startswith("Paired"):
            ax.scatter(px + 0.45, py, s=3, color=ORANGE, lw=0)
        ax.text(x0 + 7.5, 28.5, lab, ha="center", va="top", fontsize=7)
    for a, b in zip(xs, xs[1:]):
        ax.add_patch(FancyArrowPatch((a + 16.2, 37), (b - 1.2, 37), arrowstyle="-|>", mutation_scale=8, color=GREY, lw=0.8))
    # tiny participant trace (longitudinal record)
    tx, ty = 87, 37
    ax.add_patch(FancyArrowPatch((69 + 16.2, 37), (tx - 1.5, 37), arrowstyle="-|>", mutation_scale=8, color=GREY, lw=0.8))
    ax.plot([tx, tx + 11], [ty, ty], color=INK, lw=0.7)
    for k, (dx, c, t) in enumerate(((0, GREY, "screening"), (3.5, ORANGE, "scan 1"), (7.5, BLUE, "scan 2"), (11, GREY, "day +30"))):
        ax.plot(tx + dx, ty, "o", ms=3.2, color=c)
        ax.text(tx + dx, ty + (1.4 if k % 2 == 0 else -1.4), t, ha="center", va="bottom" if k % 2 == 0 else "top", fontsize=5.6)
    ax.text(tx + 5.5, 28.5, "Longitudinal\nrecord", ha="center", va="top", fontsize=7)
    ax.text(tx + 5.5, 41.5, "one participant", ha="center", fontsize=5.6, color=GREY, style="italic")
    down(22, 18.5)

    # C. scientific questions
    ax.text(1.5, 17.5, "C", fontsize=10, fontweight="bold", va="top")
    ax.text(5, 17.5, "Scientific questions", fontsize=8, fontweight="bold", va="top")
    qs = ["Who enters?\n(Fig. 2)", "How long will\nrecruitment take?\n(Fig. 3)", "How robust is\nthe endpoint?\n(Fig. 4)",
          "Can external evidence\nreconstruct the missing\ncomparator? (Fig. 5)"]
    for i, t in enumerate(qs):
        card(4 + i * 24, 2.5, 21, 10, t, fc="#FFF6E5", ec=ORANGE)
    save(fig, "Figure1")


# ---------------------------------------------------------------- Figure 2
def eligibility_deltas(n_rep=50):
    reps = sorted(REP.glob("r[0-9][0-9][0-9]"))[:n_rep]
    target = 52
    out = {}
    from collections import Counter
    pressure = Counter()
    data = []
    for rd in reps:
        e = [json.loads(x) for x in open(rd / "eligibility" / "eligibility.jsonl", encoding="utf-8")]
        data.append((int(rd.name[1:]), e))
        pressure.update(c for x in e for c in x.get("failed") or [])
    top = [c for c, _ in pressure.most_common(3)]

    def metrics(e, r, drop):
        ok = [bool(x["status"] == "ELIGIBLE" or (drop is not None and x["status"] == "INELIGIBLE" and (x.get("failed") or []) == [drop])) for x in e]
        order = np.random.default_rng(20270000 + 97 * r + 11).permutation(len(ok))
        cum = np.cumsum([ok[i] for i in order])
        return 100 * sum(ok) / len(ok), int(np.searchsorted(cum, target) + 1)
    for c in top:
        d_el, d_scr = [], []
        for r, e in data:
            b, bs = metrics(e, r, None)
            a, as_ = metrics(e, r, c)
            d_el.append(a - b)
            d_scr.append(as_ - bs)
        out[c] = (np.array(d_el), np.array(d_scr))
    return out


def fig2():
    crit = {c["criterion_id"]: " ".join(((c.get("label") or {}).get("text") or (c.get("evidence") or {}).get("text") or "").split())
            for c in SPEC["eligibility"]}
    short = {"EL011": "Cystectomy, renal failure or\nconditions affecting bladder", "EL009": "Interventional trial\nwithin 30 days",
             "EL003": "Low-PSA BCR\n(PSA <= 0.5 ng/mL)"}
    fig = plt.figure(figsize=(W2, 3.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[0.62, 1.35], hspace=0.45, wspace=0.35)
    ax = fig.add_subplot(gs[0, :])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    el, scr, use = col(LIT, "eligible_pct"), col(LIT, "screened_to_target"), col(LIT, "usable_pairs")
    nodes = [("10,000", "candidates", "generated per trial"),
             (f"{np.median(el):.1f}%", "eligible", f"p10-p90 {q(el, 10):.1f}-{q(el, 90):.1f}"),
             (f"{np.median(scr):.0f}", "screened", f"p10-p90 {q(scr, 10):.0f}-{q(scr, 90):.0f}"),
             ("52", "enrolled", "protocol target"),
             (f"{np.median(use):.0f}", "analysable pairs", f"p10-p90 {q(use, 10):.0f}-{q(use, 90):.0f}")]
    for i, (big, lab, sub) in enumerate(nodes):
        x = 8 + i * 21
        ax.text(x, 6.6, big, ha="center", fontsize=11, fontweight="bold", color=BLUE)
        ax.text(x, 4.4, lab, ha="center", fontsize=7.5)
        ax.text(x, 2.5, sub, ha="center", fontsize=6.3, color=GREY)
        if i:
            ax.add_patch(FancyArrowPatch((x - 15, 7.1), (x - 6, 7.1), arrowstyle="-|>", mutation_scale=8, color=GREY, lw=0.8))
    letter(ax, "A", x=0.0, y=0.95)
    deltas = eligibility_deltas()
    keys = list(deltas)
    for k, (idx, xlabel, fmt) in enumerate(((0, "Change in eligible share (percentage points)", "{:+.1f}"),
                                           (1, "Change in patients screened to reach 52", "{:+.0f}"))):
        ax = fig.add_subplot(gs[1, k])
        for j, c in enumerate(keys):
            v = deltas[c][idx]
            m, lo, hi = np.median(v), q(v, 10), q(v, 90)
            ax.plot([lo, hi], [j, j], color=BLUE, lw=1.2)
            ax.plot(m, j, "o", color=BLUE, ms=4.5)
            ax.text(m, j - 0.18, fmt.format(m), fontsize=6.3, color=INK, ha="center", va="bottom")
        ax.axvline(0, color=GREY, lw=0.6, ls=":")
        ax.set_yticks(range(len(keys)), [short.get(c, crit.get(c, c)[:30]) if k == 0 else "" for c in keys])
        ax.set_ylim(-0.6, len(keys) - 0.4)
        ax.invert_yaxis()
        ax.set_xlabel(xlabel)
        letter(ax, "B" if k == 0 else "C")
    save(fig, "Figure2")


# ---------------------------------------------------------------- Figure 3
def fig3():
    fig = plt.figure(figsize=(W2, 2.9))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.45, 1], wspace=0.32)
    ax = fig.add_subplot(gs[0])
    t = np.logspace(np.log10(2), np.log10(400), 400)
    cdf = np.array([percentile_from_quantiles(ACC, m / 12) for m in t]) / 100
    ax.fill_between(t, 0, cdf, color=SKY, alpha=0.18, lw=0)
    ax.plot(t, cdf, color=BLUE, lw=1.4, label="Predictive distribution")
    for k, v in ACC_BY.items():
        ax.plot(12 * float(k.rstrip("y")), v, "s", ms=3.2, color=BLUE, mec="white", mew=0.4)
    o = OBS["conduct"]["enrolment_months_approx"]
    po = percentile_from_quantiles(ACC, o / 12) / 100
    ax.axvline(o, color=OBS_C, lw=0.8, ls="--")
    obs_star(ax, o, po)
    ax.annotate(f"Observed ~{o:g} months\n(predictive percentile {100 * po:.0f})", (o, po), xytext=(40, 0.08), fontsize=6.5, color=OBS_C,
                arrowprops=dict(arrowstyle="-", color=OBS_C, lw=0.6))
    ax.set_xscale("log")
    ax.set_xticks([3, 6, 12, 24, 48, 96, 192], ["3", "6", "12", "24", "48", "96", "192"])
    ax.set_xlabel("Months to enrol 52 participants")
    ax.set_ylabel("Probability target reached")
    ax.set_ylim(0, 1)
    letter(ax, "A")
    ax = fig.add_subplot(gs[1])
    rows = [("Prespecified\npredictive", 12 * ACC["p10"], 12 * ACC["p50"], 12 * ACC["p90"], BLUE)]
    st = {r["scenario"]: r for r in STRESS if r["family"] == "recruitment"}
    for name, lab in (("fast", "Fast rate\n(p90, 65.9/yr)"), ("central", "Central rate\n(16.4/yr)"), ("slow", "Slow rate\n(p10, 4.2/yr)")):
        r = st[name]
        rows.append((lab, float(r["v1"]), float(r["v2"]), float(r["v3"]), GREY))
    for i, (lab, lo, md, hi, c) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color=c, lw=3, alpha=0.55, solid_capstyle="butt")
        ax.plot(md, i, "o", color=c, ms=4)
    ax.axvline(o, color=OBS_C, lw=0.8, ls="--")
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xticks([6, 12, 24, 48, 96, 192], ["6", "12", "24", "48", "96", "192"])
    ax.set_xlabel("Months (median; 10th-90th percentile)")
    letter(ax, "B")
    save(fig, "Figure3")


# ---------------------------------------------------------------- Figure 4
def fig4():
    rows = list(csv.DictReader(open(F / "amendments" / "A3_operating_surface.csv", encoding="utf-8")))
    effs = sorted({float(r["effect"]) for r in rows})
    ns = sorted({int(r["n"]) for r in rows})
    Z = np.zeros((len(ns), len(effs)))
    for r in rows:
        Z[ns.index(int(r["n"])), effs.index(float(r["effect"]))] = float(r["success"])
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    cf = ax.contourf(effs, ns, Z, levels=np.linspace(0, 1, 21), cmap="cividis")
    cs = ax.contour(effs, ns, Z, levels=[0.5, 0.8, 0.9, 0.95], colors="white", linewidths=0.8)
    ax.clabel(cs, fmt=lambda v: f"{100 * v:.0f}%", fontsize=6.5, inline_spacing=2)
    ax.plot(10, 52, "D", ms=6, color="white", mec=INK, mew=0.8, label="Protocol design (N = 52, effect 10)")
    ax.plot(OBS["endpoint"]["paired_difference"]["median"], OBS["endpoint"]["evaluable"], "*", ms=12, color=OBS_C, mec="white", mew=0.5,
            label=f"Observed (N = {OBS['endpoint']['evaluable']}, median difference {OBS['endpoint']['paired_difference']['median']:g})")
    ax.set_xlabel("True mean paired difference in bladder SUVmean")
    ax.set_ylabel("Analysable participants (N)")
    cb = fig.colorbar(cf, ax=ax, fraction=0.05, pad=0.02, ticks=[0, 0.25, 0.5, 0.75, 1])
    cb.set_label("P(significant, comparator higher)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    ax.legend(loc="lower right", frameon=True, framealpha=0.9, edgecolor="none")
    save(fig, "Figure4")


# ---------------------------------------------------------------- Figure 5
COLS = {"SCA-A": ORANGE, "SCA-B": BLUE, "SCA-R": GREEN}
NAMES = {"SCA-A": "Independent evidence (P2)", "SCA-B": "Same evidence as truth (P1)\nself-consistency", "SCA-R": "Reverse independent\n(P1 model, P2 truth)"}


def fig5():
    fig = plt.figure(figsize=(W2, 4.3))
    gs = fig.add_gridspec(2, 2, height_ratios=[0.26, 1], width_ratios=[1, 1.15], hspace=0.22, wspace=0.75)
    ax = fig.add_subplot(gs[0, :])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 10)
    ax.axis("off")
    steps = [("Index scan observed\n(flotufolastat)", BLUE), ("Comparator masked\n(piflufolastat)", GREY), ("External evidence\n(published cohorts)", PURPLE),
             ("Synthetic\ncomparator", ORANGE), ("Compare with the\nheld-out comparator", GREEN)]
    for i, (t, c) in enumerate(steps):
        x = 1 + i * 20
        ax.add_patch(FancyBboxPatch((x, 1.5), 17.5, 7, boxstyle="round,pad=0.2,rounding_size=1", fc="white", ec=c, lw=0.9))
        ax.text(x + 8.75, 5, t, ha="center", va="center", fontsize=6.0)
        if i:
            ax.add_patch(FancyArrowPatch((x - 2.3, 5), (x - 0.2, 5), arrowstyle="-|>", mutation_scale=7, color=GREY, lw=0.7))
    letter(ax, "A", x=0.0, y=0.92)
    short = {"SCA-A": "Independent (P2)", "SCA-B": "Self-consistency (P1)", "SCA-R": "Reverse independent"}
    ax = fig.add_subplot(gs[1, 0])
    lim = [0, 50]
    ax.plot(lim, lim, color=GREY, lw=0.7, ls="--", label="Identity")
    for name, c in COLS.items():
        rows = [x for x in SCA if x["experiment"] == name]
        ax.scatter([x["true_contrast"] for x in rows], [x["sca_contrast"] for x in rows], s=7, color=c, alpha=0.75, lw=0, label=short[name])
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Held-out true paired difference")
    ax.set_ylabel("Synthetic-comparator paired difference")
    ax.legend(loc="upper right", frameon=False, handletextpad=0.2, fontsize=6.2, borderaxespad=0.1)
    letter(ax, "B")
    ax = fig.add_subplot(gs[1, 1])
    for i, name in enumerate(COLS):
        e = np.array([x["signed_bias"] for x in SCA if x["experiment"] == name])
        cov = sum(x["covers"] for x in SCA if x["experiment"] == name)
        ax.plot([q(e, 10), q(e, 90)], [i, i], color=COLS[name], lw=1.4)
        ax.plot(e.mean(), i, "o", color=COLS[name], ms=5)
        ax.text(1.03, i, f"{e.mean():+5.1f} {np.median(np.abs(e)):5.1f} {math.sqrt(np.mean(e * e)):5.1f} {cov:4d}%", va="center", fontsize=6.3,
                family="DejaVu Sans Mono", transform=ax.get_yaxis_transform())
    ax.text(1.03, -0.75, " Bias   MAE  RMSE  Cov.", fontsize=6.1, color=GREY, family="DejaVu Sans Mono", transform=ax.get_yaxis_transform())
    ax.axvline(0, color=GREY, lw=0.6, ls=":")
    ax.set_yticks(range(3), [short[n] for n in COLS], fontsize=6.6)
    ax.set_ylim(-1.0, 2.5)
    ax.invert_yaxis()
    ax.set_xlim(-35, 25)
    ax.set_xlabel("Error in paired difference\n(mean; 10th-90th percentile)")
    letter(ax, "C")
    save(fig, "Figure5")


# ---------------------------------------------------------------- Figure 6
def half_violin(ax, v, y, c, h=0.35):
    v = np.asarray(v, float)
    if np.ptp(v) == 0:
        ax.plot(v[0], y, "|", color=c, ms=10)
        return
    k = stats.gaussian_kde(v)
    xs = np.linspace(v.min() - 0.1 * np.ptp(v), v.max() + 0.1 * np.ptp(v), 200)
    d = k(xs)
    ax.fill_between(xs, y, y + h * d / d.max(), color=c, alpha=0.35, lw=0)
    ax.plot([q(v, 10), q(v, 90)], [y - 0.06, y - 0.06], color=c, lw=2.2, solid_capstyle="butt")
    ax.plot(np.median(v), y - 0.06, "o", color="white", mec=c, ms=4, mew=1)


def fig6():
    e, c = OBS["endpoint"], OBS["conduct"]
    fig, axes = plt.subplots(2, 2, figsize=(W2, 4.4))
    plt.subplots_adjust(hspace=0.62, wspace=0.42)
    # A recruitment
    ax = axes[0, 0]
    t = np.logspace(np.log10(3), np.log10(400), 400)
    cdf = np.array([percentile_from_quantiles(ACC, m / 12) for m in t]) / 100
    dens = np.convolve(np.gradient(cdf, np.log(t)), np.ones(25) / 25, mode="same")      # display smoothing of the interpolated density
    ax.fill_between(t, 0, dens / dens.max(), color=SKY, alpha=0.35, lw=0)
    ax.plot(t, dens / dens.max(), color=BLUE, lw=1.1)
    ax.plot([12 * ACC["p10"], 12 * ACC["p90"]], [-0.08, -0.08], color=BLUE, lw=2.2, solid_capstyle="butt")
    obs_star(ax, c["enrolment_months_approx"], -0.08)
    ax.set_xscale("log")
    ax.set_xticks([6, 12, 24, 48, 96, 192], ["6", "12", "24", "48", "96", "192"])
    ax.set_yticks([])
    ax.set_ylabel("Predictive density")
    ax.set_xlabel("Months to enrol 52 participants")
    ax.text(0.98, 0.95, f"observed: percentile {percentile_from_quantiles(ACC, c['enrolment_months_approx'] / 12):.0f}",
            transform=ax.transAxes, ha="right", fontsize=6.3, color=OBS_C)
    letter(ax, "A")
    # B paired contrast
    ax = axes[0, 1]
    half_violin(ax, col(LIT, "median_difference"), 1, BLUE)
    half_violin(ax, col(DES, "median_difference"), 0, GREY)
    obs_star(ax, e["paired_difference"]["median"], 1 - 0.06)
    obs_star(ax, e["paired_difference"]["median"], -0.06, label=False)
    ax.set_yticks([0, 1], ["Design\nassumption", "Pre-result\nliterature"])
    ax.set_ylim(-0.4, 1.55)
    ax.set_xlabel("Median paired difference in bladder SUVmean")
    letter(ax, "B")
    # C comparator level
    ax = axes[1, 0]
    for y, name, colr, lab in ((1, "SCA-B", BLUE, "P1 evidence\n(25.7 median)"), (0, "SCA-A", ORANGE, "P2 evidence\n(SUVmax-converted)")):
        half_violin(ax, [x["synthetic_comparator"]["median"] for x in SCA if x["experiment"] == name], y, colr)
    for y in (1, 0):
        obs_star(ax, e["comparator_piflufolastat"]["median"], y - 0.06, label=(y == 1))
    ax.set_yticks([0, 1], ["P2 evidence\n(SUVmax-converted)", "P1 evidence"])
    ax.set_ylim(-0.4, 1.55)
    ax.set_xlabel("Synthetic piflufolastat bladder SUVmean (median)")
    letter(ax, "C")
    # D missingness
    ax = axes[1, 1]
    miss = 100 * col(LIT, "missing_pairs") / 52
    vals, counts = np.unique(np.round(miss, 2), return_counts=True)
    ax.bar(vals, counts / counts.sum(), width=1.2, color=BLUE, alpha=0.6, lw=0)
    obs_star(ax, 100 * c["missing_pairs"] / c["dosed"], 0.02)
    ax.set_xlabel("Participants without an analysable pair (%)")
    ax.set_ylabel("Share of virtual trials")
    ax.set_xlim(-1.5, 14)
    letter(ax, "D")
    h, lab = axes[0, 0].get_legend_handles_labels()
    fig.legend(h[:1], lab[:1], loc="lower center", ncol=1, frameon=False, bbox_to_anchor=(0.5, -0.04))
    save(fig, "Figure6")


# ---------------------------------------------------------------- supplementary
def figS1():
    rd = REP / "r001"
    adsl = list(csv.DictReader(open(rd / "journey" / "adsl.csv", encoding="utf-8")))
    pairs = {r["participant"]: r for r in csv.DictReader(open(rd / "paired_measurements_literature.csv", encoding="utf-8"))}
    pid = next(iter(pairs))
    recs = sorted([r for r in adsl if r["USUBJID"].split("-P")[0] == pid], key=lambda r: r["USUBJID"])
    coh = [json.loads(x) for x in open(next((rd / "cohorts").glob("cohort_*.jsonl")), encoding="utf-8")]
    patient = next(x["patient_id"] for x in coh if (x.get("patient_subject") or x["subject_id"].split("-P")[0]) == pid)
    el = next((json.loads(x) for x in open(rd / "eligibility" / "eligibility.jsonl", encoding="utf-8") if json.loads(x)["patient_id"] == patient), {})
    d2 = float(recs[-1]["TRTEDY"] or 10)
    fig, ax = plt.subplots(figsize=(W2, 1.9))
    ax.set_xlim(-17, 45)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.plot([-15, 42], [2, 2], color=GREY, lw=0.8)
    ev = [(-14, f"Screening\n{len(el.get('resolved') or {})} criteria evaluated: {el.get('status', '?').lower()}", INK, 1),
          (1, f"Scan 1: piflufolastat\nbladder SUVmean {float(pairs[pid]['reference']):.1f}", ORANGE, 1),
          (d2, f"Scan 2: flotufolastat\nbladder SUVmean {float(pairs[pid]['index']):.1f}", BLUE, -1),
          (d2 + 30, "End of reporting window", GREY, 1)]
    for d, t, c, side in ev:
        ax.plot(d, 2, "o", color=c, ms=5)
        ax.text(d, 2 + 0.4 * side, t, ha="center", va="bottom" if side > 0 else "top", fontsize=6.6)
        ax.text(d, 2 - 0.35 * side, f"day {d:g}", ha="center", va="top" if side > 0 else "bottom", fontsize=6, color=GREY)
    save(fig, "FigureS1", "supplementary")


def figS2():
    rows = list(csv.DictReader(open(F / "amendments" / "A1_effect_curve.csv", encoding="utf-8")))
    x = [float(r["effect"]) for r in rows]
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    for key, c, lab in (("rejection", GREY, "Two-sided rejection"), ("success", BLUE, "Significant with comparator higher")):
        y = np.array([float(r[key]) for r in rows])
        se = np.array([float(r[key + "_se"]) for r in rows])
        ax.errorbar(x, y, yerr=1.96 * se, color=c, marker="o", ms=3, lw=1, capsize=2, label=lab)
    ax.axhline(0.05, color=GREY, lw=0.5, ls=":")
    ax.axhline(0.8, color=GREY, lw=0.5, ls=":")
    ax.set_xlabel("True mean paired difference (N = 52)")
    ax.set_ylabel("Probability")
    ax.legend(frameon=False, loc="lower right")
    save(fig, "FigureS2", "supplementary")


def figS3():
    reps = sorted(REP.glob("r[0-9][0-9][0-9]"))
    from collections import Counter
    per = {}
    for rd in reps:
        e = [json.loads(x) for x in open(rd / "eligibility" / "eligibility.jsonl", encoding="utf-8")]
        cnt = Counter(c for x in e for c in x.get("failed") or [])
        for c, k in cnt.items():
            per.setdefault(c, []).append(100 * k / len(e))
    crit = sorted(per, key=lambda c: -np.median(per[c]))
    fig, ax = plt.subplots(figsize=(3.6, 2.8))
    ax.boxplot([per[c] for c in crit], orientation="horizontal", widths=0.5, showfliers=False, medianprops=dict(color=BLUE),
               boxprops=dict(lw=0.6), whiskerprops=dict(lw=0.6), capprops=dict(lw=0.6))
    ax.set_yticks(range(1, len(crit) + 1), crit)
    ax.invert_yaxis()
    ax.set_xlabel("Generated candidates excluded (%), 100 virtual trials")
    save(fig, "FigureS3", "supplementary")


def figS4():
    rows = list(csv.DictReader(open(F / "amendments" / "A2_correlation_sensitivity.csv", encoding="utf-8")))
    fig, axes = plt.subplots(1, 2, figsize=(5.4, 2.3))
    plt.subplots_adjust(wspace=0.4)
    for name, c in (("SCA-A", ORANGE), ("SCA-B", BLUE)):
        r = [x for x in rows if x["model"] == name]
        rho = [float(x["correlation"]) for x in r]
        axes[0].plot(rho, [float(x["bias"]) for x in r], "o-", color=c, ms=3.5, label=NAMES[name].split("\n")[0])
        axes[1].plot(rho, [100 * float(x["coverage"]) for x in r], "o-", color=c, ms=3.5)
    axes[0].axhline(0, color=GREY, lw=0.5, ls=":")
    axes[0].set_xlabel("Within-patient correlation")
    axes[0].set_ylabel("Bias in paired difference")
    axes[1].set_xlabel("Within-patient correlation")
    axes[1].set_ylabel("95% interval coverage (%)")
    axes[1].axhline(95, color=GREY, lw=0.5, ls=":")
    axes[0].legend(frameon=False, fontsize=6)
    letter(axes[0], "A")
    letter(axes[1], "B")
    save(fig, "FigureS4", "supplementary")


if __name__ == "__main__":
    for f in (fig1, fig2, fig3, fig4, fig5, fig6, figS1, figS2, figS3, figS4):
        f()
        print("ok", f.__name__)
