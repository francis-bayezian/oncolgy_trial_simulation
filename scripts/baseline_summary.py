"""Baseline Monte Carlo results of a replicate experiment (paper step 4), from its master tables
(scripts/replicate_master_table.py): per quantity n, median, mean, SD, p10/p25/p50/p75/p90; success as a count with a
Wilson 95% interval; eligibility pressure by criterion (share of the generated patients each criterion excludes, with
the criterion's text); and QC histograms (SVG) of the eligible share and the time to enrol the target.

Usage: .venv/Scripts/python.exe scripts/baseline_summary.py ID BASE_VERSION MASTER_DIR OUT_DIR
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

QUANTITIES = [("generated", "patients generated"), ("eligible_pct", "eligible, % of generated"),
              ("screened_to_target", "screened to reach the evaluable target"), ("enrol_days_to_target", "days to enrol the target"),
              ("participants_enrolled", "participants enrolled"), ("completed_all_exposures", "participants completing both exposures"),
              ("usable_pairs", "usable paired endpoints"), ("missing_pairs", "missing paired endpoints"),
              ("median_difference", "median paired difference"), ("hodges_lehmann", "Hodges-Lehmann paired shift"),
              ("mean_difference", "mean paired difference"), ("p_value", "p-value")]


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (float("nan"), float("nan"))
    z, p = 1.96, k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (c - h, c + h)


def hist_svg(values, title: str, unit: str) -> str:
    v = np.asarray(values, float)
    counts, edges = np.histogram(v, bins=min(20, max(5, len(set(np.round(v, 3))))))
    W, H, L, B = 640, 300, 50, 40
    mx = counts.max() or 1
    bw = (W - L - 20) / len(counts)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif" font-size="11">',
         f'<rect width="{W}" height="{H}" fill="white"/><text x="{L}" y="18" font-size="13" font-weight="bold">{title}</text>']
    for i, c in enumerate(counts):
        h = (H - B - 40) * c / mx
        s.append(f'<rect x="{L + i * bw:.1f}" y="{H - B - h:.1f}" width="{bw - 1:.1f}" height="{h:.1f}" fill="#1f4e79"/>')
    for i in (0, len(edges) // 2, len(edges) - 1):
        s.append(f'<text x="{L + i * bw:.1f}" y="{H - B + 15}" text-anchor="middle">{edges[i]:.4g}</text>')
    s.append(f'<text x="{W / 2}" y="{H - 8}" text-anchor="middle">{unit} (n = {len(v)} simulated trials; counts up to {mx})</text></svg>')
    return "\n".join(s)


def main(study: str, version: str, master_dir: Path, out: Path) -> Path:
    spec = json.loads((Path("data/locked") / study / f"studyspec_v{version}" / "studyspec.json").read_text(encoding="utf-8"))
    crit_text = {c["criterion_id"]: " ".join(((c.get("label") or {}).get("text") or (c.get("evidence") or {}).get("text") or "")[:90].split())
                 for c in spec.get("eligibility") or []}
    out.mkdir(parents=True, exist_ok=True)
    L = [f"# Baseline Monte Carlo results: {study} (base v{version})", "",
         "Each quantity across the simulated trials. Probabilities are counts of trials with a Wilson 95% interval; with "
         "100 trials, differences of a few percentage points are not meaningful.", ""]
    rows_out = []
    for f in sorted(Path(master_dir).glob("master_simulation_*.csv")):
        src = f.stem.replace("master_simulation_", "")
        rows = list(csv.DictReader(open(f, encoding="utf-8")))
        n = len(rows)
        succ = sum(r["success"] == "True" for r in rows)
        lo, hi = wilson(succ, n)
        L += [f"## Endpoint source: {src}", "", f"Trials reaching significance at the protocol's alpha: **{succ}/{n}** "
              f"(95% CI {100 * lo:.0f}-{100 * hi:.0f}%).", "",
              "| Quantity | n | median | mean | SD | p10 | p25 | p50 | p75 | p90 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for key, label in QUANTITIES:
            v = np.array([float(r[key]) for r in rows if r.get(key) not in (None, "", "None", "nan")])
            if not len(v):
                continue
            q = np.percentile(v, [10, 25, 50, 75, 90])
            L.append(f"| {label} | {len(v)} | {np.median(v):.4g} | {v.mean():.4g} | {v.std(ddof=1) if len(v) > 1 else 0:.4g} | "
                     + " | ".join(f"{x:.4g}" for x in q) + " |")
            rows_out.append([src, key, len(v), np.median(v), v.mean(), v.std(ddof=1) if len(v) > 1 else 0, *q])
        L.append("")
    # eligibility pressure and QC plots (identical across endpoint sources: take the first table)
    rows = list(csv.DictReader(open(sorted(Path(master_dir).glob("master_simulation_*.csv"))[0], encoding="utf-8")))
    gen = np.array([float(r["generated"]) for r in rows])
    fails = sorted(k for k in rows[0] if k.startswith("fail_"))
    L += ["## Eligibility pressure (criteria that exclude generated patients)", "",
          "| Criterion | Text | % of generated excluded: mean | p10 | p90 |", "| --- | --- | ---: | ---: | ---: |"]
    pressure = []
    for k in fails:
        pct = 100 * np.array([float(r[k]) for r in rows]) / gen
        pressure.append((pct.mean(), k[5:], np.percentile(pct, 10), np.percentile(pct, 90)))
    for m, c, p10, p90 in sorted(pressure, reverse=True):
        if m > 0:
            L.append(f"| {c} | {crit_text.get(c, '')} | {m:.2f} | {p10:.2f} | {p90:.2f} |")
    L.append("")
    (out / "qc_eligible_share.svg").write_text(hist_svg([float(r["eligible_pct"]) for r in rows], "Eligible share across simulated trials",
                                                       "% of generated patients eligible"), encoding="utf-8")
    (out / "qc_enrolment_days.svg").write_text(hist_svg([float(r["enrol_days_to_target"]) for r in rows if r["enrol_days_to_target"]],
                                                        "Time to enrol the evaluable target", "days from the first enrolment"), encoding="utf-8")
    L += ["QC plots: `qc_eligible_share.svg`, `qc_enrolment_days.svg`.", ""]
    with open(out / "baseline_summary.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([["source", "quantity", "n", "median", "mean", "sd", "p10", "p25", "p50", "p75", "p90"], *rows_out])
    (out / "baseline_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out / "baseline_summary.md"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])))
