"""Publication figures for the PHUSE EU 2026 paper, generated only from locked or released artifacts.

Run with the isolated plotting environment (keeps the pipeline's pinned numpy untouched):
    .venv-figures/Scripts/python.exe scripts/paper_figures.py

Every plotted number is read from a file under data/; key values of the running examples are asserted so a
changed artifact fails loudly instead of silently producing a different figure. Outputs: docs/figures/*.{pdf,svg,png}.
"""

import json
import math
import re
from datetime import datetime
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
LOCK = ROOT / "data" / "locked"
V3P = ROOT / "data" / "simulation_parameters_v3" / "proportions"

# Colour language shared by paper and slides (labels always accompany colour).
EVIDENCE = "#1f5fa8"   # reported evidence
FITTED = "#6a3d9a"     # fitted distributions / predictions
SYNTH = "#0f8b8d"      # synthetic output
UNKNOWN = "#9a9a9a"    # unsupported / unresolved
PROTOCOL = "#d95f02"   # the protocol's own assumption
OBSERVED = "#111111"   # registry-observed result
SLATE = "#34495e"      # protocol / rules
PALE = {EVIDENCE: "#e3edf8", FITTED: "#eee6f5", SYNTH: "#e0f2f2", SLATE: "#e6eaee", UNKNOWN: "#f0f0f0", PROTOCOL: "#fdebdc"}

TEXT_W = 6.5  # inches: single-column A4 text width

mpl.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 6.8, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5, "axes.spines.top": False, "axes.spines.right": False,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "savefig.dpi": 600,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
})


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest(study, kind):
    """Highest locked version of a stage (e.g. 'safety_comparison') for a study."""
    cands = [p for p in (LOCK / study).glob(f"{kind}_v*") if re.fullmatch(rf"{kind}_v[\d.]+", p.name)]
    return max(cands, key=lambda p: tuple(int(x) for x in p.name.rsplit("_v", 1)[1].split(".")))


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    print("wrote", name)


def panel_label(ax, s, x=-0.02, y=1.02):
    ax.text(x, y, s, transform=ax.transAxes, fontsize=9, fontweight="bold", va="bottom", ha="right")


def box(ax, x, y, w, h, text, color, fs=6.4, bold_first=True, lw=0.9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.9", fc=PALE.get(color, "white"),
                                ec=color, lw=lw, zorder=2))
    lines = text.split("\n")
    if bold_first:
        ax.text(x + w / 2, y + h / 2 + (0.95 * (len(lines) - 1)), lines[0], ha="center", va="center", fontsize=fs,
                fontweight="bold", color=color, zorder=3)
        if len(lines) > 1:
            ax.text(x + w / 2, y + h / 2 - 0.95 * 1.1, "\n".join(lines[1:]), ha="center", va="center", fontsize=fs - 0.6,
                    color="#333333", zorder=3, linespacing=1.15)
    else:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color="#333333", zorder=3)


def arrow(ax, p, q, color="#555555", lw=0.8, style="-|>", ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=7, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", zorder=1, shrinkA=1, shrinkB=1))


# --------------------------------------------------------------------------------------------------------------------
# Figure 1: the pipeline strip (the recurring map)
# --------------------------------------------------------------------------------------------------------------------
def card(ax, x, y, w, h, title, body, color, tfs=6.0, bfs=5.1, lw=0.9, fc=None):
    """A rounded box with a bold (possibly multi-line) title above a smaller body, centred as one block."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.8",
                                fc=fc or PALE.get(color, "white"), ec=color, lw=lw, zorder=2))
    t_lines, b_lines = title.count("\n") + 1, (body.count("\n") + 1) if body else 0
    # line heights in data units, from the axes' points-per-unit so text never collides at any figure size
    pts_per_unit = ax.get_window_extent().height / (ax.get_ylim()[1] - ax.get_ylim()[0]) * 72 / ax.figure.dpi
    th, bh_ = t_lines * tfs * 1.2 / pts_per_unit, b_lines * bfs * 1.25 / pts_per_unit
    gap = 0.35 * tfs / pts_per_unit if body else 0
    top = y + h / 2 + (th + gap + bh_) / 2
    ax.text(x + w / 2, top, title, ha="center", va="top", fontsize=tfs, fontweight="bold", color=color, zorder=3,
            linespacing=1.1)
    if body:
        ax.text(x + w / 2, top - th - gap, body, ha="center", va="top", fontsize=bfs, color="#333333",
                zorder=3, linespacing=1.2)


def fig1_pipeline():
    n_params = pq.ParquetFile(V3P / "parameter_index.parquet").metadata.num_rows
    n_rows = pq.ParquetFile(ROOT / "data" / "simulation_parameters_v1" / "evidence_table.parquet").metadata.num_rows
    assert n_rows == 106185, n_rows

    fig, ax = plt.subplots(figsize=(TEXT_W, 3.55))
    ax.set_xlim(0, 104)
    ax.set_ylim(-4, 56)
    ax.axis("off")

    # protocol row: eight stages, each box centred over its column
    stages = [
        ("Protocol\nPDF", "text layer,\nOCR fallback", SLATE),
        ("StudySpec", "compile · verify\nresolve or leave", SLATE),
        ("Population", "10,000 synthetic\npatients", SYNTH),
        ("Screening", "eligible · ineligible\nundetermined", SYNTH),
        ("Enrolment", "accrual scenarios\nrandomisation", SYNTH),
        ("Simulation", "endpoints · AEs\noperating chars.", SYNTH),
        ("Datasets", "ADSL · ADAE\nADTTE", SYNTH),
        ("Feasibility\nreport", "funnel · sites\ntime · failure risk", SYNTH),
    ]
    bw, gap, x0, y0, bh = 11.7, 1.3, 0.6, 21, 11.5
    xs = [x0 + i * (bw + gap) for i in range(8)]
    cx = [x + bw / 2 for x in xs]
    for x, (t, b, c) in zip(xs, stages):
        card(ax, x, y0, bw, bh, t, b, c)
    for i in range(7):
        arrow(ax, (xs[i] + bw + 0.05, y0 + bh / 2), (xs[i + 1] - 0.05, y0 + bh / 2), SLATE, lw=0.9)

    # evidence row: assets placed above the stages they feed
    ey, eh = 41, 9.5
    card(ax, 0.6, ey, 15.8, eh, "Registry results\n& abstracts", "1,000 trials\n2,771 profiles", EVIDENCE)
    card(ax, 19.4, ey, 15.8, eh, "Evidence table", f"{n_rows:,} observation\nrows, context kept", EVIDENCE)
    pbx = cx[2] + 6.2
    card(ax, pbx, ey, 17.5, eh, "Parameter tables", f"{n_params:,} fitted\nparameters (V3)", FITTED)
    obx = cx[4] + 5.4
    card(ax, obx, ey, 14.6, eh, "Operational asset", "accrual → enrolment\nfailure risk → report", FITTED)
    sbx = cx[5] + 8.2
    card(ax, sbx, ey, 14.2, eh, "Safety asset", "per-event model\n(V3.1, calibrated)", FITTED)
    arrow(ax, (16.6, ey + eh / 2), (19.2, ey + eh / 2), EVIDENCE, lw=0.9)
    arrow(ax, (35.4, ey + eh / 2), (pbx - 0.2, ey + eh / 2), EVIDENCE, lw=0.9)
    top = y0 + bh + 0.5
    arrow(ax, (pbx + 4, ey - 0.4), (cx[2] + 1.5, top), FITTED, rad=0.18)           # parameters -> population
    arrow(ax, (pbx + 13.5, ey - 0.4), (cx[5] - 2.5, top), FITTED, rad=-0.12)      # parameters -> simulation
    arrow(ax, (obx + 4, ey - 0.4), (cx[4] + 1.5, top), FITTED, rad=0.15)          # operational -> enrolment
    arrow(ax, (sbx + 4, ey - 0.4), (cx[5] + 2.5, top), FITTED, rad=0.15)          # safety -> simulation

    # evaluation row
    ebw, eby, ebh = 27, 1.5, 8.2
    ex = [13, 44, 75]
    card(ax, ex[0], eby, ebw, ebh, "Lock every stage", "SHA-256 of outputs, inputs and code", OBSERVED, fc="white")
    card(ax, ex[1], eby, ebw, ebh, "Fetch registry results", "only after the last prediction lock", OBSERVED, fc="white")
    card(ax, ex[2], eby, ebw, ebh, "Unseal and score", "category commitment · order check", OBSERVED, fc="white")
    arrow(ax, (ex[0] + ebw + 0.2, eby + ebh / 2), (ex[1] - 0.2, eby + ebh / 2), OBSERVED, lw=0.9)
    arrow(ax, (ex[1] + ebw + 0.2, eby + ebh / 2), (ex[2] - 0.2, eby + ebh / 2), OBSERVED, lw=0.9)
    ax.plot([cx[1], cx[7]], [y0 - 2.2, y0 - 2.2], color="#888888", lw=0.7, ls=(0, (2, 1.5)))
    for c_ in (cx[1], cx[7]):
        ax.plot([c_, c_], [y0 - 0.4, y0 - 2.2], color="#888888", lw=0.7, ls=(0, (2, 1.5)))
    arrow(ax, (ex[0] + ebw / 2, y0 - 2.2), (ex[0] + ebw / 2, eby + ebh + 0.3), "#888888", ls=(0, (2, 1.5)))
    ax.text(ex[0] + ebw / 2 + 1, y0 - 3.9, "every stage from StudySpec to report", fontsize=5.2, color="#666666",
            style="italic", va="center")

    # row labels, in the left margin above each row
    for y, t, c in [(ey + eh + 1.2, "HISTORICAL EVIDENCE", EVIDENCE), (y0 + bh + 1.2, "PROTOCOL-CONDITIONED SIMULATION", SLATE),
                    (eby + ebh + 1.2, "BLIND EVALUATION", OBSERVED)]:
        ax.text(0.6, y, t, fontsize=5.8, fontweight="bold", color=c, ha="left", va="bottom")

    handles = [Patch(fc=PALE[EVIDENCE], ec=EVIDENCE, label="reported evidence"),
               Patch(fc=PALE[FITTED], ec=FITTED, label="fitted distributions"),
               Patch(fc=PALE[SLATE], ec=SLATE, label="protocol rules"),
               Patch(fc=PALE[SYNTH], ec=SYNTH, label="synthetic output"),
               Patch(fc="white", ec=OBSERVED, label="evaluation")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=5, handlelength=1.4,
              columnspacing=1.2, fontsize=6.2)
    save(fig, "fig1_pipeline")


# --------------------------------------------------------------------------------------------------------------------
# Figure 2: one observation, three probability summaries
# --------------------------------------------------------------------------------------------------------------------
def fig2_evidence_lane():
    pid, oid = "3b1473de78a0a559", "d9b934b17937e424"
    raw = load(ROOT / "data" / "raw" / "ctgov" / "NCT00091572.json")
    g = next(e for e in raw["resultsSection"]["adverseEventsModule"]["eventGroups"] if e["id"] == "EG000")
    assert (g["seriousNumAffected"], g["seriousNumAtRisk"]) == (124, 419)
    ev = pq.read_table(ROOT / "data" / "simulation_parameters_v1" / "evidence_table.parquet",
                       columns=["scientific_observation_id", "numerator", "denominator", "event_class", "regimen", "disease"])
    row = ev.filter(pc.equal(ev["scientific_observation_id"], oid)).to_pylist()[0]
    assert (row["numerator"], row["denominator"]) == (124, 419)
    rec = next(json.loads(line) for line in open(V3P / "parameter_index.jsonl", encoding="utf-8") if pid in line)
    dr = pq.read_table(V3P / "posterior_draws.parquet", filters=[("parameter_id", "=", pid)])
    pop = np.asarray(dr["population"].to_pylist())
    fut = np.asarray(dr["future_study"].to_pylist())
    assert abs(np.median(fut) - rec["future_study_predictive"]["median"]) < 0.02

    fig = plt.figure(figsize=(TEXT_W, 5.0))
    gs = fig.add_gridspec(3, 1, height_ratios=[0.62, 1.55, 0.95], hspace=0.62)

    # (a) provenance chain
    ax = fig.add_subplot(gs[0])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 12)
    ax.axis("off")
    panel_label(ax, "a", x=0.0, y=1.0)
    s = rec["support"]
    card(ax, 0.5, 1.2, 29, 9.6, "Registry record", "NCT00091572 · group EG000\nserious AE: 124 affected / 419 at risk",
         EVIDENCE, tfs=6.6, bfs=6.0)
    card(ax, 35.5, 1.2, 29, 9.6, f"Evidence row {oid}",
         f"{row['regimen']} · {row['disease']}\n{row['event_class'].replace('_', ' ')}\n"
         f"{row['numerator']}/{row['denominator']} (safety denominator kept)", EVIDENCE, tfs=6.6, bfs=6.0)
    card(ax, 70.5, 1.2, 29, 9.6, f"Parameter {pid}",
         f"support level {s['level']} · {s['studies']} direct study\n+ {s['borrowed_parent_studies']} parent studies borrowed",
         FITTED, tfs=6.6, bfs=6.0)
    arrow(ax, (29.9, 6), (35.1, 6), EVIDENCE, lw=1)
    arrow(ax, (64.9, 6), (70.1, 6), FITTED, lw=1)

    # (b) three distributions as a ridge plot; labels in the left margin
    ax = fig.add_subplot(gs[1])
    panel_label(ax, "b", x=-0.36, y=1.0)
    xg = np.linspace(0.001, 0.999, 1500)

    def kde_prob(d):
        lz = np.log(d / (1 - d))
        k = stats.gaussian_kde(lz)
        k.set_bandwidth(k.factor * 1.25)
        return k(np.log(xg / (1 - xg))) / (xg * (1 - xg))

    a_, b_ = 124.5, 295.5
    rows = [
        ("Within-study posterior", "this study's data only", stats.beta.pdf(xg, a_, b_),
         (stats.beta.ppf(.025, a_, b_), stats.beta.median(a_, b_), stats.beta.ppf(.975, a_, b_)), EVIDENCE),
        ("Population posterior", "hierarchy, with borrowing", kde_prob(pop),
         tuple(np.quantile(pop, [.025, .5, .975])), FITTED),
        ("Future-study probability", "a new study's true rate", kde_prob(fut),
         tuple(np.quantile(fut, [.025, .5, .975])), FITTED),
    ]
    step = 1.3
    for i, (name, sub, dens, (lo, med, hi), c) in enumerate(rows):
        base = (2 - i) * step
        yy = 1.0 * dens / dens.max()
        ax.fill_between(xg, base, base + yy, color=c, alpha=0.28 if i == 0 else 0.16, lw=0)
        ax.plot(xg, base + yy, color=c, lw=0.9)
        ax.plot([lo, hi], [base - 0.13] * 2, color=c, lw=1.8, solid_capstyle="butt")
        ax.plot([med], [base - 0.13], "o", ms=3.2, color=c, mec="white", mew=0.4)
        ax.text(-0.025, base + 0.42, name, transform=mpl.transforms.blended_transform_factory(ax.transAxes, ax.transData),
                ha="right", va="bottom", fontsize=6.8, fontweight="bold", color=c)
        ax.text(-0.025, base + 0.40, f"{sub}\nmedian {med:.1%} (95%: {lo:.1%}–{hi:.1%})",
                transform=mpl.transforms.blended_transform_factory(ax.transAxes, ax.transData),
                ha="right", va="top", fontsize=6.0, color="#333333", linespacing=1.2)
    ax.axvline(124 / 419, color=OBSERVED, lw=0.7, ls=(0, (3, 2)), zorder=0)
    ax.text(124 / 419 + 0.012, 3 * step + 0.05, "observed 124/419", fontsize=6, va="top", ha="left")
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.4, 3 * step + 0.1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Probability of any serious adverse event (temozolomide, melanoma)")
    pos = ax.get_position()
    ax.set_position([pos.x0 + 0.2, pos.y0, pos.width - 0.2, pos.height])

    # (c) borrowing chain
    ax = fig.add_subplot(gs[2])
    panel_label(ax, "c", x=-0.36, y=1.0)
    chain = rec["parent_contribution"]["chain"]
    names = {"modality": "Modality", "class_signature": "Drug class", "regimen": "Regimen", "disease_family": "Disease family"}
    ys = np.arange(len(chain))[::-1]
    for y, c in zip(ys, chain):
        v = c["share_of_precision_from_parent"]
        ax.barh(y, v, color=FITTED, alpha=0.85, height=0.6)
        ax.barh(y, 1 - v, left=v, color=PALE[EVIDENCE], ec=EVIDENCE, lw=0.4, height=0.6)
        ax.text(v - 0.012 if v > 0.15 else v + 0.012, y, f"{v:.0%}", va="center", ha="right" if v > 0.15 else "left",
                fontsize=6.2, color="white" if v > 0.15 else "#222222")
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{names.get(c['level'], c['level'])}: {c['node'].replace('_', ' ')} "
                        f"({c['studies_under_node']} {'study' if c['studies_under_node'] == 1 else 'studies'})"
                        for c in chain], fontsize=6.2)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Share of the node's posterior precision supplied by its parent level (borrowing)")
    ax.legend(handles=[Patch(fc=FITTED, alpha=0.85, label="borrowed from the parent level"),
                       Patch(fc=PALE[EVIDENCE], ec=EVIDENCE, lw=0.4, label="the node's own data")],
              loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=6.2)
    pos = ax.get_position()
    ax.set_position([pos.x0 + 0.2, pos.y0, pos.width - 0.2, pos.height])
    save(fig, "fig2_evidence_lane")


# --------------------------------------------------------------------------------------------------------------------
# Figure 3: from protocol to patients (development protocol ACNS0332)
# --------------------------------------------------------------------------------------------------------------------
def fig3_walkthrough():
    study = "ACNS0332"
    el = load(latest(study, "eligibility") / "eligibility_summary.json")["summary"]
    rec = load(latest(study, "cohorts") / "recruitment_summary.json")
    om = load(latest(study, "outcomes") / "outcome_model.json")["control_efs"]
    cmp_ = load(latest(study, "registry_comparison") / "comparison.json")
    ctl = next(i for i in cmp_["items"] if i["quantity"].startswith("5-year EFS %") and "control" in i["quantity"])

    fig = plt.figure(figsize=(TEXT_W, 2.75))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.35, 1, 1], wspace=0.42)

    # (a) screening: criteria by how they can be evaluated, and patient-level status
    ax = fig.add_subplot(gs[0])
    panel_label(ax, "a", x=-1.05, y=1.02)
    crit = el["criteria"]
    per = el["per_criterion"]
    ev_ids = crit["evaluated"]
    met = sum(1 for c in ev_ids if per[c]["met"] == el["patients"])
    unk = sum(1 for c in ev_ids if per[c]["unknown"] == el["patients"])
    cats = [("Executed: decided for every patient", met, SYNTH),
            ("Executed: variable not generated → unknown", unk, UNKNOWN),
            ("Not executable (rule unresolved)", len(crit["not_executable"]), PROTOCOL),
            ("Procedural (consent, timing)", len(crit["procedural"]), SLATE),
            ("Permissive / informational", len(crit["permissive"]) + len(crit["informational"]), "#c9c9c9")]
    total = sum(c[1] for c in cats)
    ys = np.arange(len(cats))[::-1]
    for y, (name, n, c) in zip(ys, cats):
        ax.barh(y, n, color=c, height=0.62)
        ax.text(n + 0.4, y, f"{n}", va="center", fontsize=6.5)
        ax.text(-0.6, y, name, va="center", ha="right", fontsize=6.1)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, max(c[1] for c in cats) * 1.25)
    ax.set_xlabel(f"Eligibility criteria (n = {total})")
    sc = el["status_counts"]
    ax.set_title(f"Screening {el['patients']:,} patients: {sc['ELIGIBLE']} proven eligible,\n"
                 f"{sc['UNDETERMINED']:,} undetermined, {sc['INELIGIBLE']} ineligible", fontsize=6.6,
                 fontweight="normal", loc="center", color="#333333", pad=4)

    # (b) enrolment under the protocol's accrual scenarios
    ax = fig.add_subplot(gs[1])
    panel_label(ax, "b")
    target = rec["summary"]["target"]["patients"]
    for sc_name, c, ls in [("accrual_35_per_year", SYNTH, "-"), ("accrual_60_per_year", SYNTH, (0, (3, 1.5)))]:
        days = [json.loads(line)["enrollment_day"] for line in
                open(latest(study, "cohorts") / f"cohort_{sc_name}.jsonl", encoding="utf-8")]
        yrs = np.sort(days) / 365.25
        ax.step(np.r_[0, yrs], np.arange(len(yrs) + 1), where="post", color=c, lw=1, ls=ls,
                label=f"{sc_name.split('_')[1]}/year: {yrs[-1]:.1f} y")
    ax.axhline(target, color=OBSERVED, lw=0.6, ls=":")
    ax.text(0.2, target + 8, f"target {target}", fontsize=6)
    ax.set_xlabel("Years from first enrolment")
    ax.set_ylabel("Patients enrolled")
    ax.set_ylim(0, target * 1.15)
    ax.set_xlim(0, None)
    ax.legend(loc="lower right", title="protocol-stated rate", title_fontsize=6, fontsize=6)

    # (c) control-arm EFS: the locked curve against the registry
    ax = fig.add_subplot(gs[2])
    panel_label(ax, "c")
    pi, lam = om["cure_fraction"], om["failure_rate_per_year"]
    t = np.linspace(0, 8, 400)
    ax.plot(t, 100 * (pi + (1 - pi) * np.exp(-lam * t)), color=FITTED, lw=1.1, label="locked control curve")
    lo, hi = ctl["predicted_90"]
    ax.errorbar([5 - 0.12], [ctl["predicted"]], yerr=[[ctl["predicted"] - lo], [hi - ctl["predicted"]]], fmt="o", ms=3,
                color=FITTED, capsize=2, lw=0.9, label="prediction, 90% interval")
    olo, ohi = ctl["observed_95ci"]
    ax.errorbar([5 + 0.12], [ctl["observed"]], yerr=[[ctl["observed"] - olo], [ohi - ctl["observed"]]], fmt="s", ms=3,
                color=OBSERVED, capsize=2, lw=0.9, label="registry, 95% CI")
    ax.set_ylim(0, 100)
    ax.set_xlim(0, 8)
    ax.set_xlabel("Years")
    ax.set_ylabel("Event-free survival, control arm (%)")
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 0.08), fontsize=5.9)
    ax.text(0.02, 0.03, "development protocol (unblinded)", transform=ax.transAxes, fontsize=5.8, color="#666666",
            style="italic")
    save(fig, "fig3_walkthrough_ACNS0332")


# --------------------------------------------------------------------------------------------------------------------
# Figure 4: the blind protocol, shown as the actual lock and fetch times
# --------------------------------------------------------------------------------------------------------------------
BLIND = {"BLIND_1": "NCT04003610", "BLIND_2": "NCT04205799", "BLIND_3": "NCT04083170"}
PRED_STAGES = ["studyspec", "protocol_facts", "population", "eligibility", "cohorts", "outcomes", "results", "planning",
               "safety", "outputs"]


def blind_versions(b):
    """The version scored at unsealing: the one the planning comparison was built from."""
    pc_ = latest(b, "planning_comparison")
    return pc_.name.rsplit("_v", 1)[1]


def stage_lock_times(b):
    v = blind_versions(b)
    out = {}
    for s in PRED_STAGES:
        p = LOCK / b / f"{s}_v{v}"
        if not p.exists():                      # stages not rebuilt for this version: take what the chain used
            p = latest(b, s) if list((LOCK / b).glob(f"{s}_v*")) else None
        if p is not None:
            out[s] = datetime.fromisoformat(load(p / "lock.json")["locked_at"])
    return out


def fig4_blind_timeline():
    names = {"studyspec": "StudySpec", "protocol_facts": "facts", "population": "population", "eligibility": "screening",
             "cohorts": "cohort", "outcomes": "outcome model", "results": "results", "planning": "planning",
             "safety": "safety", "outputs": "datasets"}
    fig, ax = plt.subplots(figsize=(TEXT_W, 2.6))
    rows = []
    for b in BLIND:
        pc_ = load(latest(b, "planning_comparison") / "planning_comparison.json")
        fetched = datetime.fromisoformat(pc_["registry_fetched_at"])
        locks = stage_lock_times(b)
        assert max(locks.values()) < fetched, (b, max(locks.values()), fetched)
        comps = {k: datetime.fromisoformat(load(latest(b, k) / "lock.json")["locked_at"])
                 for k in ["planning_comparison", "safety_comparison", "baseline_comparison", "median_comparison",
                           "registry_comparison"] if list((LOCK / b).glob(f"{k}_v*"))}
        rows.append((b, locks, fetched, comps))

    def m(t, f):
        return (t - f).total_seconds() / 60

    lo = min(m(min(r[1].values()), r[2]) for r in rows)
    ax.axvspan(lo - 20, 0, color=PALE[FITTED], lw=0, zorder=0)
    ax.axvspan(0, 22, color="#f2f2f2", lw=0, zorder=0)
    ax.axvline(0, color=OBSERVED, lw=1.1, zorder=1)
    ax.text(-4, len(rows) - 0.35, "predictions locked\n(registry results unseen)", ha="right", va="top", fontsize=6.2,
            color=FITTED, fontweight="bold")
    ax.text(3, len(rows) - 0.35, "registry\nfetched,\nscored", ha="left", va="top", fontsize=6.2, color=OBSERVED,
            fontweight="bold")
    for i, (b, locks, fetched, comps) in enumerate(rows):
        y = len(rows) - 1 - i
        xs = [m(t, fetched) for t in locks.values()]
        ax.plot([min(xs), max(xs)], [y, y], color=FITTED, lw=2.8, alpha=0.3, solid_capstyle="round", zorder=2)
        ax.plot(xs, [y] * len(xs), "|", color=FITTED, ms=9, mew=1.2, zorder=3)
        ax.plot([m(t, fetched) for t in comps.values()], [y] * len(comps), "|", color=OBSERVED, ms=9, mew=1.2, zorder=3)
        ax.plot([0], [y], "v", color=OBSERVED, ms=5.5, zorder=4)
        last = max(xs)
        ax.annotate(f"last lock {-last:.0f} min before fetch", (last, y), xytext=(0, -11), textcoords="offset points",
                    ha="right", fontsize=5.8, color="#444444")
        ax.text(lo - 24, y, f"{b}\n{BLIND[b]}", ha="right", va="center", fontsize=6.4, fontweight="bold",
                linespacing=1.15)
    ax.set_xlim(lo - 20, 22)
    ax.set_ylim(-0.75, len(rows) - 0.25)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Minutes relative to the registry fetch (each trial's own fetch time = 0)")
    handles = [Line2D([], [], color=FITTED, marker="|", ls="", ms=8, mew=1.2,
                      label="prediction stage locked (SHA-256 of files, inputs, code)"),
               Line2D([], [], color=OBSERVED, marker="v", ls="", ms=5, label="registry results fetched"),
               Line2D([], [], color=OBSERVED, marker="|", ls="", ms=8, mew=1.2, label="comparison locked")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.3), ncol=3, columnspacing=1.0)
    save(fig, "fig4_blind_timeline")


# --------------------------------------------------------------------------------------------------------------------
# Figure 5: recruitment — the protocol's assumption, the pipeline, and what happened
# --------------------------------------------------------------------------------------------------------------------
def fig5_accrual():
    fig = plt.figure(figsize=(TEXT_W, 2.55))
    gs = fig.add_gridspec(1, 2, width_ratios=[2.1, 1], wspace=0.55)
    ax = fig.add_subplot(gs[0])
    panel_label(ax, "a")
    xg = np.logspace(-0.5, 2.6, 600)
    labels = []
    fail = []
    for i, b in enumerate(BLIND):
        d = load(latest(b, "planning_comparison") / "planning_comparison.json")
        y = 2 - i
        hm = d["historical_model"]
        q = hm["predicted_patients_per_year"]
        mu, sg = hm["reconstruction"]["mu"], hm["reconstruction"]["sigma"]
        dens = stats.lognorm.pdf(xg, s=sg, scale=math.exp(mu)) * xg        # density on the log axis
        ax.fill_between(xg, y, y + 0.36 * dens / dens.max(), color=FITTED, alpha=0.16, lw=0)
        ax.plot([q["q10"], q["q90"]], [y, y], color=FITTED, lw=1.3, solid_capstyle="butt")
        ax.plot([q["q25"], q["q75"]], [y, y], color=FITTED, lw=3.6, solid_capstyle="butt")
        ax.plot([q["median"]], [y], "o", ms=4.2, mfc="white", mec=FITTED, mew=1.1)
        ax.text(q["median"], y + 0.1, f"{q['median']:.1f}", ha="center", va="bottom", fontsize=6, color=FITTED)
        ps = [s for s in d["protocol_scenarios"] if s.get("patients_per_year")]
        for s in ps:
            ax.plot([s["patients_per_year"]], [y], "D", ms=4.4, color=PROTOCOL)
            ax.text(s["patients_per_year"], y + 0.1, f"{s['patients_per_year']:g}", ha="center", fontsize=6,
                    color=PROTOCOL)
        act = d["actual"]
        obs = hm["observed_rate_per_year_lower_bound"]
        scoreable = act["enrolled"] >= 5
        ax.plot([obs], [y], marker=">", ms=5, color=OBSERVED if scoreable else UNKNOWN)
        ax.text(obs, y - 0.13, f"≥{obs:.1f}", fontsize=6, va="top", ha="center", color=OBSERVED if scoreable else UNKNOWN)
        status = act["overall_status"].lower().replace("_", " ")
        note = f"{act['enrolled']} enrolled · {status}" + ("" if scoreable else " · not scoreable")
        labels.append((y, f"{b}\n{note}", scoreable))
        if not ps:
            ax.text(0.37, y + 0.17, "no rate stated", fontsize=5.8, color=PROTOCOL, style="italic")
        fm = d["failure_model"]
        fail.append((b, fm["observed_outcome"], fm["predicted_probability"], fm["base_rate"]))
    for y, t, ok in labels:
        ax.text(0.26, y, t, ha="right", va="center", fontsize=6.2, color="#222222" if ok else UNKNOWN)
    ax.set_xscale("log")
    ax.set_xlim(0.3, 300)
    ax.set_ylim(-0.6, 2.65)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("Accrual rate (patients per year, log scale)")
    handles = [Line2D([], [], marker="D", color=PROTOCOL, ls="", ms=4, label="protocol's own assumption"),
               Line2D([], [], color=FITTED, lw=3.4, label="pipeline 50% interval"),
               Line2D([], [], color=FITTED, lw=1.2, label="pipeline 80% interval"),
               Line2D([], [], marker=">", color=OBSERVED, ls="", ms=5, label="observed (lower bound)")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.42, -0.22), ncol=2, handletextpad=0.4,
              columnspacing=1.2)

    # (b) failure model: probability given to the outcome that happened
    ax = fig.add_subplot(gs[1])
    panel_label(ax, "b")
    ys = np.arange(len(fail))[::-1]
    for y, (b, outcome, p, base) in zip(ys, fail):
        ax.barh(y + 0.17, base, height=0.3, color="#cfcfcf")
        ax.barh(y - 0.17, p, height=0.3, color=FITTED, alpha=0.85)
        ax.text(max(p, base) + 0.02, y, f"{p:.0%} vs {base:.0%}", va="center", fontsize=6)
    ax.set_xlim(0, 1)
    ax.set_yticks(ys)
    ax.set_yticklabels([b + "\n" + o.replace("_", " ") for b, o, _, _ in fail], fontsize=6.1)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Probability given to the observed outcome")
    ax.legend(handles=[Patch(fc=FITTED, alpha=0.85, label="failure model"), Patch(fc="#cfcfcf", label="base rate")],
              loc="upper center", bbox_to_anchor=(0.4, -0.22), ncol=1)
    save(fig, "fig5_accrual_blind")


# --------------------------------------------------------------------------------------------------------------------
# Figure 6: registry-scale calibration
# --------------------------------------------------------------------------------------------------------------------
def parse_scorecard():
    rows = []
    for line in (ROOT / "data" / "validation" / "scorecard.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 7 and cells[2].endswith("%") and cells[3].endswith("%"):
            rows.append({"component": cells[0], "n": int(cells[1].replace(",", "")), "nominal": float(cells[2][:-1]) / 100,
                         "coverage": float(cells[3][:-1]) / 100, "verdict": cells[4], "sharpness": cells[5]})
    return rows


def fig6_calibration():
    rows = parse_scorecard()
    short = {"accrual rate (patients/month)": ("Accrual rate", "o"),
             "adverse events: reported counts": ("Adverse-event counts", "s"),
             "adverse events: serious events reported absent": ("Serious AEs reported absent", "X"),
             "baseline: mean age": ("Baseline mean age", "^"),
             "baseline: share female": ("Baseline share female", "v"),
             "outcome proportions (response, safety)": ("Outcome proportions", "D"),
             "survival (arm medians, landmarks)": ("Survival (consistency check)", "P")}
    fig = plt.figure(figsize=(TEXT_W, 3.6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.2, 1], wspace=0.45)
    ax = fig.add_subplot(gs[0])
    panel_label(ax, "a")
    x = np.linspace(0.4, 1, 10)
    ax.fill_between(x, x - 0.05, np.minimum(x + 0.07, 1.0), color="#e8e8e8", lw=0, label="pass band (−5 to +7 points)")
    ax.plot(x, x, color="#777777", lw=0.7, ls=(0, (3, 2)))
    cols = {}
    palette = [FITTED, EVIDENCE, "#b15928", SYNTH, "#1b9e77", "#e7298a", "#555555"]
    seen = set()
    for r in rows:
        name, mk = short.get(r["component"], (r["component"], "o"))
        c = cols.setdefault(name, palette[len(cols) % len(palette)])
        ax.scatter(r["nominal"], r["coverage"], s=10 + 9 * math.log10(r["n"]), marker=mk, color=c, ec="white", lw=0.4,
                   zorder=3, label=None if name in seen else f"{name} (n = {r['n']:,})")
        seen.add(name)
    ax.set_xlim(0.44, 1.0)
    ax.set_ylim(0.44, 1.02)
    ax.set_xlabel("Nominal interval level")
    ax.set_ylabel("Held-out coverage")
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_aspect("equal")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=5.9, handletextpad=0.2, columnspacing=0.8)

    # (b) what calibration bought for adverse events: log score per held-out observation
    ax = fig.add_subplot(gs[1])
    panel_label(ax, "b", x=-0.02, y=1.14)
    ae = next(r for r in rows if r["component"] == "adverse events: reported counts")
    m = re.search(r"log score (-?[\d.]+) \(V2 in-sample (-?[\d.]+)\)", ae["sharpness"])
    v31, v2 = float(m.group(1)), float(m.group(2))
    rec = (ROOT / "data" / "trial" / "unblinded" / "results_record.md").read_text(encoding="utf-8")
    unc = float(re.search(r"against (-?[\d.]+) uncalibrated", rec).group(1))
    bars = [("V2\n(in-sample)", v2, "#cfcfcf"), ("V3.1\nuncalibrated", unc, PALE[FITTED]), ("V3.1\ncalibrated", v31, FITTED)]
    for i, (lbl, v, c) in enumerate(bars):
        ax.bar(i, v, color=c, ec=FITTED if i else "#999999", lw=0.5, width=0.62)
        ax.text(i, v - 0.06, f"{v:.2f}", ha="center", va="top", fontsize=6.6, color="white" if i == 2 else "#222222")
    ax.set_xticks(range(3))
    ax.set_xticklabels([b[0] for b in bars], fontsize=6.5)
    ax.set_ylim(-3.1, 0)
    ax.set_ylabel("Mean log score (higher is better)")
    ax.axhline(0, color="#333333", lw=0.6)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", length=0, pad=2)
    ax.xaxis.set_ticks_position("top")
    ax.set_xlabel("Adverse-event counts on held-out trials", fontsize=6.8)
    ax.xaxis.set_label_position("bottom")
    save(fig, "fig6_calibration")


# --------------------------------------------------------------------------------------------------------------------
# Figure 7: individual adverse events in the blind trials
# --------------------------------------------------------------------------------------------------------------------
def fig7_blind_events():
    data = []
    for b in ["BLIND_1", "BLIND_2"]:
        s = load(latest(b, "safety_comparison") / "safety_comparison.json")
        rows = [r for r in s["rows"] if r["observed_listed"]]
        assert len(rows) == s["matched_terms"]
        data.append((b, s, sorted(rows, key=lambda r: r["predicted_rate"])))
    fig = plt.figure(figsize=(TEXT_W, 4.9))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1], wspace=0.95)
    for k, (b, s, rows) in enumerate(data):
        ax = fig.add_subplot(gs[k])
        panel_label(ax, "ab"[k])
        n = rows[0]["at_risk"]
        for i, r in enumerate(rows):
            lo, hi = r["predicted_90"]
            ax.plot([lo / n, hi / n], [i, i], color=FITTED, lw=2.2, alpha=0.35, solid_capstyle="butt")
            ax.plot([r["predicted_median"] / n], [i], "|", color=FITTED, ms=5, mew=1)
            c = OBSERVED if r["inside_90"] else PROTOCOL
            ax.plot([r["observed"] / n], [i], "o", ms=3.2, color=c, mec="white", mew=0.3, zorder=3)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([("(S) " if r["seriousness"] == "serious" else "") + r["term"].replace("_", " ")[:34]
                            for r in rows], fontsize=5.8)
        ax.set_ylim(-0.8, len(rows) - 0.2)
        ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_xlim(-0.02, 1.02)
        ax.set_xlabel("Patients with the event")
        ax.set_title(f"{b} ({BLIND[b]}), n = {n} at risk\n{s['matched_inside_90']} of {s['matched_terms']} inside the 90% "
                     f"interval", fontsize=6.8, fontweight="normal", color="#333333")
        ax.grid(axis="x", color="#eeeeee", lw=0.5)
        ax.set_axisbelow(True)
    handles = [Line2D([], [], color=FITTED, lw=2.2, alpha=0.35, label="predicted 90% interval (at the registry's n)"),
               Line2D([], [], color=FITTED, marker="|", ls="", ms=5, label="predicted median"),
               Line2D([], [], color=OBSERVED, marker="o", ls="", ms=3.2, label="observed, inside"),
               Line2D([], [], color=PROTOCOL, marker="o", ls="", ms=3.2, label="observed, outside"),
               Line2D([], [], color="#333333", marker="", ls="", label="(S) serious event")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.03), ncol=5, fontsize=6.2,
               columnspacing=1.0, handletextpad=0.4)
    save(fig, "fig7_blind_adverse_events")


# --------------------------------------------------------------------------------------------------------------------
# Figure 8: the informative estimates — any serious adverse event by subgroup, and the control-arm median
# --------------------------------------------------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - hw, c + hw


def fig8_informative():
    fig = plt.figure(figsize=(TEXT_W, 5.2))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.7, 1], hspace=0.55, wspace=0.35)
    for k, b in enumerate(["BLIND_1", "BLIND_2"]):
        est = load(latest(b, "outputs") / "trial_outputs.json")["feasibility"]["subgroup_estimates"]
        s = load(latest(b, "safety_comparison") / "safety_comparison.json")["aggregate"]["serious"]
        arm = next(iter(est["arms"].values()))["serious_adverse_event"]
        entries = [("Headline: " + arm["headline_subgroup"].replace("trials with overlapping drug classes", "overlapping drug classes"), arm["headline"], True)]
        for dim, groups in arm["breakdown"].items():
            for gname, g in groups.items():
                if g is arm["headline"] or g == arm["headline"]:
                    continue
                entries.append((f"{dim}: {gname}", g, False))
        ax = fig.add_subplot(gs[k, 0])
        panel_label(ax, "ab"[k])
        ys = np.arange(len(entries))[::-1]
        kk, nn = s["registry_affected"], s["at_risk"]
        wl, wh = wilson(kk, nn)
        ax.axvspan(wl, wh, color="#dddddd", lw=0, zorder=0)
        ax.axvline(kk / nn, color=OBSERVED, lw=0.9, zorder=1)
        for y, (lbl, g, head) in zip(ys, entries):
            c = FITTED if head else "#8f7aa8"
            ax.plot(g["single_trial_80"], [y, y], color=c, lw=0.6, alpha=0.6)
            ax.plot(g["ci95"], [y, y], color=c, lw=2.4 if head else 1.6, solid_capstyle="butt")
            ax.plot([g["estimate"]], [y], "o" if head else "o", ms=4 if head else 3, color=c, mec="white", mew=0.4)
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{e[0]} ({e[1]['studies']} studies)" for e in entries], fontsize=5.8)
        for t, e in zip(ax.get_yticklabels(), entries):
            if e[2]:
                t.set_fontweight("bold")
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_xlabel("Any serious adverse event")
        ax.set_title(f"{b}: predicted {arm['headline']['estimate']:.1%}\nobserved {kk}/{nn} ({kk / nn:.0%})", fontsize=6.8,
                     fontweight="normal", color="#333333")
        ax.set_ylim(-0.7, len(entries) - 0.3)
    handles = [Line2D([], [], color=FITTED, lw=2.4, label="95% CI of the subgroup mean"),
               Line2D([], [], color=FITTED, lw=0.6, alpha=0.6, label="80% range for a single new trial"),
               Line2D([], [], color=OBSERVED, lw=0.9, label="observed"),
               Patch(fc="#dddddd", label="observed 95% CI (Wilson)")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.04), ncol=4, fontsize=6.1)

    # (c) control-arm median PFS, BLIND_1
    mc = load(latest("BLIND_1", "median_comparison") / "median_comparison.json")
    it = mc["items"][0]
    p = it["predicted_control"]
    ax = fig.add_subplot(gs[:, 1])
    panel_label(ax, "c")
    ctl = next(g for g in it["groups"] if g["group"] == it["control_group"])
    lo, hi = p["ci95_months"]
    ax.errorbar([p["median_months"]], [1], xerr=[[p["median_months"] - lo], [hi - p["median_months"]]], fmt="o",
                color=FITTED, capsize=2.5, ms=4, lw=1.2)
    clo = ctl["ci"][0]
    ax.plot([ctl["median_months"]], [0], "s", color=OBSERVED, ms=4)
    ax.annotate("", xy=(7.8, 0), xytext=(clo, 0), arrowprops=dict(arrowstyle="-|>", color=OBSERVED, lw=1.0,
                                                                  mutation_scale=6))
    ax.plot([clo, clo], [-0.08, 0.08], color=OBSERVED, lw=1)
    ax.text(ctl["median_months"], -0.22, f"{ctl['median_months']:.1f} mo (n = {int(ctl['participants'])})\nupper CI not reached",
            ha="left", va="top", fontsize=5.8)
    ax.text(p["median_months"], 1.18, f"{p['median_months']:.1f} mo\n({p['studies']} evidence studies)", ha="center",
            va="bottom", fontsize=5.8, color=FITTED)
    ax.set_yticks([1, 0])
    ax.set_yticklabels(["predicted\n(locked)", "registry\ncontrol arm"], fontsize=6.2)
    ax.set_ylim(-0.75, 1.75)
    ax.set_xlim(0, 8)
    ax.set_xlabel("Median PFS, control arm (months)")
    ax.set_title("BLIND_1: control-arm\nmedian PFS", fontsize=6.8, fontweight="normal", color="#333333")
    save(fig, "fig8_blind_informative_estimates")


if __name__ == "__main__":
    fig1_pipeline()
    fig2_evidence_lane()
    fig3_walkthrough()
    fig4_blind_timeline()
    fig5_accrual()
    fig6_calibration()
    fig7_blind_events()
    fig8_informative()
