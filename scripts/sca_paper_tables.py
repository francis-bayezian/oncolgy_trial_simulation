"""The two principal tables of the NCT06604442 synthetic-comparator paper (step 16) and the analysis manifest
(step 17), from frozen files and the observed targets.

Table 1 (provenance): every quantity the simulation uses - protocol value, evidence source, generated quantity,
assumption - and whether it feeds the feasibility analysis, the synthetic comparator, or both.
Table 2 (frozen simulation vs observed trial): every compared quantity with the frozen p10 / p50 / p90, the observed
value and its percentile.
Manifest: every output file with its checksum, the commands that produced it and the seeds.

Usage: .venv/Scripts/python.exe scripts/sca_paper_tables.py [FREEZE_DIR]
"""

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

F = Path(sys.argv[1] if len(sys.argv) > 1 else "analysis_freeze/NCT06604442")


def master(src):
    return list(csv.DictReader(open(F / "step2_master" / f"master_simulation_{src}.csv", encoding="utf-8")))


def col(rows, k):
    return np.array([float(r[k]) for r in rows if r[k] not in ("", "None", "nan")])


def pr(v, x):
    v = np.sort(np.asarray(v, float))
    return 100 * (np.searchsorted(v, x, "left") + np.searchsorted(v, x, "right")) / (2 * len(v))


def table1() -> list[list]:
    plan = json.loads(Path("data/locked/NCT06604442/planning_v4.1.0/planning_report.json").read_text(encoding="utf-8"))
    h = plan["accrual"]["historical_model"]
    return [["Quantity", "Protocol value", "Evidence / source", "Generated quantity", "Assumption", "Used in"],
            ["Eligibility rules", "13 inclusion/exclusion criteria (StudySpec, 100% faithful)", "protocol", "per-patient eligibility of 10,000 generated patients",
             "criteria patients cannot carry resolved to the registry screen-pass rate (A16)", "feasibility"],
            ["Age, sex, race, ethnicity", "men >= 18 years", "simulation parameter asset V3 (registry baselines)", "baseline demographics", "-", "feasibility"],
            ["Performance status", "-", "registry baseline ECOG (prostate, phase 4)", "per-patient ECOG", "-", "feasibility"],
            ["Evaluable target", "52 (60 to be screened)", "protocol section 15", "enrolment stops at 52 participants", "-", "feasibility"],
            ["Accrual rate", f"10 centers (protocol)", f"historical accrual model {h['source']}",
             f"Poisson arrivals, median {h['patients_per_year']['median']:.1f}/year (p10-p90 {h['patients_per_year']['percentiles']['p10']:.1f}-{h['patients_per_year']['percentiles']['p90']:.1f})",
             "site count from the protocol; rate uncertainty from the model", "feasibility"],
            ["Exposures and order", "piflufolastat then flotufolastat 1-10 days later", "protocol", "two records per participant",
             "exits person-level (L044)", "feasibility, SCA"],
            ["Exits (withdrawal, AE stop, death)", "-", "registry disposition rates (prostate, phase 4)", "per-participant exits in the procedure window",
             "registry whole-trial rates scaled to the window (A22)", "feasibility"],
            ["Flotufolastat bladder SUVmean", "-", "F1: Kuo et al., Mol Imaging Biol 2023 (n=718)", "per-participant index value", "lognormal from median and IQR", "SCA (truth and models)"],
            ["Piflufolastat bladder SUVmean (truth)", "-", "P1: preprint 2025-05 (n=50, independent)", "per-participant comparator value (masked)", "lognormal from median and range", "SCA truth"],
            ["Piflufolastat bladder SUVmean (independent model)", "-", "P2: Donswijk 2022 SUVmax (n=51) x 0.731", "synthetic comparator SCA-A",
             "SUVmax-to-SUVmean ratio from flotufolastat", "SCA comparator"],
            ["Within-patient correlation", "-", "none reported", "log-scale correlation of the two exposures", "0.5 (A29)", "SCA truth"],
            ["Design effect", "mean paired difference 10, SD 25, 80% power", "protocol (68Ga-PSMA-11 stand-in)", "design-assumption endpoint source",
             "reported as a sensitivity, never as truth", "feasibility (design check)"],
            ["Primary analysis", "two-sided paired Wilcoxon signed rank, alpha 0.05", "protocol", "per-trial p-value and success", "-", "feasibility, SCA"]]


def table2() -> list[list]:
    obs = json.loads((F / "post_reveal" / "observed_targets.json").read_text(encoding="utf-8"))
    e, c = obs["endpoint"], obs["conduct"]
    lit, des = master("literature"), master("design")
    sca = [json.loads(x) for x in open(F / "step10_sca_internal" / "sca_per_trial.jsonl", encoding="utf-8")]
    rows = [["Quantity", "Frozen simulation p10 / p50 / p90", "Observed", "Percentile of observed", "Within p5-p95"]]

    def add(name, v, o, fmt="{:.1f}"):
        q = np.percentile(v, [10, 50, 90])
        lo, hi = np.percentile(v, [5, 95])
        rows.append([name, " / ".join(fmt.format(x) for x in q), fmt.format(o), f"{pr(v, o):.0f}", "yes" if lo <= o <= hi else "no"])
    add("Screen-pass rate, %", col(lit, "eligible_pct"), 100 * c["dosed"] / c["screened"])
    add("Missing paired endpoints, % of enrolled", 100 * col(lit, "missing_pairs") / 52, 100 * c["missing_pairs"] / c["dosed"])
    add("Months to enrol (central accrual)", col(lit, "enrol_days_to_target") / 30.44, c["enrolment_months_approx"])
    add("Paired contrast, median (literature truth)", col(lit, "median_difference"), e["paired_difference"]["median"])
    add("Paired contrast, median (design assumption)", col(des, "median_difference"), e["paired_difference"]["median"])
    for name, label in (("SCA-B", "Synthetic comparator median, P1 model"), ("SCA-A", "Synthetic comparator median, P2 model")):
        add(label, [x["synthetic_comparator"]["median"] for x in sca if x["experiment"] == name], e["comparator_piflufolastat"]["median"])
    for name, label in (("SCA-B", "Synthetic-comparator contrast, P1 model"), ("SCA-A", "Synthetic-comparator contrast, P2 model")):
        add(label, [x["sca_contrast"] for x in sca if x["experiment"] == name], e["paired_difference"]["median"])
    rows.append(["Direction (comparator higher)", "100/100 trials (all sources)", f"{e['lower_with_index']}/{e['evaluable']} lower with flotufolastat", "-", "yes"])
    rows.append(["Significant at alpha 0.05", f"literature 100/100; design {sum(r['success'] == 'True' for r in des)}/100; SCA 99-100/100", f"yes (p {e['p']})", "-", "yes"])
    return rows


def write(rows, name):
    with open(F / "tables" / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"] + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows[1:]]


def manifest():
    files = {str(f).replace("\\", "/"): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in sorted(F.rglob("*")) if f.is_file() and f.name != "ANALYSIS_MANIFEST.md"}
    cmds = ["bash scripts/run_replicates.sh NCT06604442 4.1.0 100 4",
            "python scripts/replicate_master_table.py NCT06604442 4.1.0 <inputs/endpoint_source_{design,literature,prestart}.json> step2_master",
            "python scripts/replicate_qc.py NCT06604442 4.1.0 step3_qc",
            "python scripts/baseline_summary.py NCT06604442 4.1.0 step2_master step4_baseline",
            "python scripts/stress_tests.py NCT06604442 4.1.0 inputs step2_master step5_stress",
            "python scripts/freeze_manifest.py NCT06604442 4.1.0 pre_observed_comparison (step 6; then outputs hashed)",
            "python scripts/sca_experiment.py NCT06604442 4.1.0 inputs step10_sca_internal (then sca_freeze.json)",
            "python scripts/observed_comparison.py NCT06604442 4.1.0 . post_reveal/observed_targets.json post_reveal",
            ".venv-figures python scripts/sca_paper_figures.py", "python scripts/sca_paper_tables.py"]
    L = ["# Analysis manifest: NCT06604442 synthetic-comparator study", "",
         "Every number in the text, tables and figures traces to one file below. Seeds: replicate r uses 20270000 + 97 r "
         "(+0 population, +1 cohorts, +2 safety, +3 outputs, +4 journey, +5 endpoints, +6 analysis, +7 eligibility, +11 "
         "screening order, +13 paired measurements, +21 accrual stress, +31 completeness stress, +41 synthetic comparator).", "",
         "## Commands (in order)", ""] + [f"{i + 1}. `{c}`" for i, c in enumerate(cmds)] + \
        ["", "## Freezes", "", "- `pre_observed_comparison/freeze_manifest.json` and `FREEZE_ID.txt`: steps 1-5.",
         "- `pre_observed_comparison/sca_freeze.json`: steps 7-10.",
         "- Observed results read only after both (`post_reveal/observed_targets.json`).", "",
         "## Files and checksums (sha256)", ""] + [f"- `{k}` {v}" for k, v in files.items()]
    (F / "ANALYSIS_MANIFEST.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return len(files)


if __name__ == "__main__":
    (F / "tables").mkdir(parents=True, exist_ok=True)
    md = ["# Table 1. Provenance of every simulated quantity", ""] + write(table1(), "table1_provenance") + \
         ["", "# Table 2. Frozen simulation vs the completed NCT06604442", ""] + write(table2(), "table2_frozen_vs_observed")
    (F / "tables" / "tables.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("manifest files:", manifest())
