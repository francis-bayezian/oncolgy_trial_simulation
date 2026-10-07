"""Reveal (paper steps 12-14): the frozen simulation outputs against the completed trial's published aggregates.

Step 13 (synthetic comparator vs the actual comparator, at the level public aggregates support): comparator location
and dispersion, index level, the treatment contrast, direction and qualitative conclusion, for every frozen comparator
and truth source. Step 14 (feasibility, separately): where the observed conduct falls in the frozen predictive
distributions (screened, evaluable, missing pairs, enrolment time). Reads frozen files only; verifies their checksums
against the freeze manifests first.

Usage: .venv/Scripts/python.exe scripts/observed_comparison.py ID BASE_VERSION FREEZE_DIR OBSERVED_JSON OUT_DIR
"""

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")


def pct_rank(values, x) -> float:
    v = np.sort(np.asarray(values, float))
    return float(100 * (np.searchsorted(v, x, side="left") + np.searchsorted(v, x, side="right")) / (2 * len(v)))


def verify(freeze: Path) -> list[str]:
    bad = []
    for name in ("freeze_manifest.json", "sca_freeze.json"):
        m = json.loads((freeze / "pre_observed_comparison" / name).read_text(encoding="utf-8"))
        for f, h in (m.get("frozen_outputs") or m.get("files") or {}).items():
            if not Path(f).exists() or hashlib.sha256(Path(f).read_bytes()).hexdigest() != h:
                bad.append(f)
    return bad


def main(study: str, version: str, freeze: Path, observed_file: Path, out: Path) -> Path:
    bad = verify(freeze)
    obs = json.loads(Path(observed_file).read_text(encoding="utf-8"))
    ep, cd = obs["endpoint"], obs["conduct"]
    root = Path(f"data/trial/runs/{study}/v{version}/replicates")
    L = [f"# Frozen simulation vs the completed trial: {study}", "",
         f"Observed: {obs['source']}. Frozen outputs verified against the freeze manifests: "
         + ("all checksums match." if not bad else f"MISMATCH in {bad}") , ""]
    # ---- step 13: comparator and contrast
    sca = [json.loads(x) for x in open(freeze / "step10_sca_internal" / "sca_per_trial.jsonl", encoding="utf-8")]
    L += ["## Step 13: synthetic comparator vs the actual comparator (aggregate level)", "",
          "Public data are aggregates (no individual patients), so this is location, dispersion, contrast and direction, "
          "not individual-level prediction.", "",
          "| Analysis | Comparator median (IQR) | Paired contrast (median) | Direction | Significant (alpha 0.05) |", "| --- | --- | --- | --- | --- |",
          f"| **Observed trial** | **{ep['comparator_piflufolastat']['median']} ({ep['comparator_piflufolastat']['q1']}-{ep['comparator_piflufolastat']['q3']})** | "
          f"**{ep['paired_difference']['median']}** | lower with index in {ep['lower_with_index']}/{ep['evaluable']} | yes (p {ep['p']}) |"]
    labels = {"SCA-A": "SCA-A, independent model (P2 evidence)", "SCA-B": "SCA-B, self-consistency check (same P1 evidence as the simulated truth; not independent)",
              "SCA-R": "SCA-R, reverse independent check (P1 model, P2 truth)"}
    for name in sorted({x["experiment"] for x in sca}):
        rows = [x for x in sca if x["experiment"] == name]
        med = np.median([x["synthetic_comparator"]["median"] for x in rows])
        q1 = np.median([x["synthetic_comparator"]["q1"] for x in rows])
        q3 = np.median([x["synthetic_comparator"]["q3"] for x in rows])
        c = [x["sca_contrast"] for x in rows]
        L.append(f"| {labels.get(name, name)}: synthetic comparator (median over 100 trials) | {med:.1f} ({q1:.1f}-{q3:.1f}) | "
                 f"{np.median(c):.1f} (p10-p90 {np.percentile(c, 10):.1f}-{np.percentile(c, 90):.1f}) | comparator higher in "
                 f"{sum(x > 0 for x in c)}/100 trials | {sum(x['sca_success'] for x in rows)}/100 trials |")
    for src in ("design", "literature", "prestart"):
        mt = list(csv.DictReader(open(freeze / "step2_master" / f"master_simulation_{src}.csv", encoding="utf-8")))
        d = [float(x["median_difference"]) for x in mt]
        pr = pct_rank(d, ep["paired_difference"]["median"])
        L.append(f"| simulated truth, `{src}` source (frozen) | - | {np.median(d):.1f} (p10-p90 {np.percentile(d, 10):.1f}-{np.percentile(d, 90):.1f}); "
                 f"observed at percentile {pr:.0f} | - | {sum(x['success'] == 'True' for x in mt)}/100 trials |")
    idx = []
    for rd in sorted(root.glob("r[0-9][0-9][0-9]")):
        v = [float(x["index"]) for x in csv.DictReader(open(rd / "paired_measurements_literature.csv", encoding="utf-8"))]
        idx.append((np.median(v), np.percentile(v, 25), np.percentile(v, 75)))
    idx = np.array(idx)
    L += ["", f"Index exposure (flotufolastat), frozen evidence F1 simulated: median {np.median(idx[:, 0]):.1f} "
              f"(IQR {np.median(idx[:, 1]):.1f}-{np.median(idx[:, 2]):.1f}); observed {ep['index_flotufolastat']['median']} "
              f"({ep['index_flotufolastat']['q1']}-{ep['index_flotufolastat']['q3']}).", ""]
    # ---- step 14: feasibility
    mt = list(csv.DictReader(open(freeze / "step2_master" / "master_simulation_literature.csv", encoding="utf-8")))
    stress = list(csv.DictReader(open(freeze / "step5_stress" / "stress_tests.csv", encoding="utf-8")))
    scr = [float(x["screened_to_target"]) for x in mt]
    elig = [float(x["eligible_pct"]) for x in mt]
    days = [float(x["enrol_days_to_target"]) for x in mt]
    usable = [float(x["usable_pairs"]) for x in mt]
    miss = [float(x["missing_pairs"]) / float(x["participants_enrolled"]) for x in mt]
    obs_miss = cd["missing_pairs"] / cd["dosed"]
    plan = json.loads((Path("data/locked") / study / f"planning_v{version}" / "planning_report.json").read_text(encoding="utf-8"))
    acc = plan["accrual"]["historical_model"]["enrollment_duration_years"]["percentiles"]
    from clinical_asset.trial.predictive import percentile_from_quantiles
    L += ["## Step 14: feasibility reality check (separate from the comparator check)", "",
          "Where the observed conduct falls in the frozen predictive distributions (percentile 0-100; outside 5-95 is outside the "
          "simulated plausible range).", "",
          "| Quantity | Frozen simulation p10 / p50 / p90 | Observed | Percentile of observed |", "| --- | --- | --- | ---: |",
          f"| screen-pass (CONTEXTUAL, denominators differ: simulated = eligible share of 10,000 generated candidates; observed = "
          f"dosed among formally screened, after any site prescreening) | {np.percentile(elig, 10):.1f}% / {np.median(elig):.1f}% / {np.percentile(elig, 90):.1f}% | "
          f"{100 * cd['dosed'] / cd['screened']:.1f}% ({cd['dosed']} dosed of {cd['screened']} screened) | not a calibration check |",
          f"| missing paired endpoints (share of enrolled) | {100 * np.percentile(miss, 10):.1f}% / {100 * np.median(miss):.1f}% / {100 * np.percentile(miss, 90):.1f}% | "
          f"{100 * obs_miss:.1f}% ({cd['missing_pairs']}/{cd['dosed']}: {cd['missing_reasons']}) | {pct_rank(miss, obs_miss):.0f} |",
          f"| usable pairs | {np.percentile(usable, 10):.0f} / {np.median(usable):.0f} / {np.percentile(usable, 90):.0f} (of 52 enrolled) | "
          f"{cd['evaluable']} (of {cd['dosed']} dosed; the trial over-enrolled) | - |",
          f"| **months to enrol, full prespecified accrual uncertainty** (frozen planning report: rate uncertainty x Poisson arrivals) | "
          f"{12 * acc['p10']:.1f} / {12 * acc['p50']:.1f} / {12 * acc['p90']:.1f} | ~{cd['enrolment_months_approx']} ({cd['enrolment_period']}, {cd['sites']} sites) | "
          f"{percentile_from_quantiles(acc, cd['enrolment_months_approx'] / 12):.0f} |",
          f"| months to enrol, central accrual rate only (replicates) | {np.percentile(days, 10) / 30.44:.1f} / {np.median(days) / 30.44:.1f} / {np.percentile(days, 90) / 30.44:.1f} | "
          f"~{cd['enrolment_months_approx']} | {pct_rank(np.asarray(days) / 30.44, cd['enrolment_months_approx']):.0f} |"]
    for r in stress:
        if r["family"] == "recruitment":
            L.append(f"| months to enrol, {r['scenario']} accrual ({float(r['v5']):.1f}/year) | {float(r['v1']):.1f} / {float(r['v2']):.1f} / {float(r['v3']):.1f} | "
                     f"~{cd['enrolment_months_approx']} | - |")
    out.mkdir(parents=True, exist_ok=True)
    (out / "observed_comparison.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out / "observed_comparison.md"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])))
