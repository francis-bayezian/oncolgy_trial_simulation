"""Post-freeze amendments (review of 2026-10-07): computed from frozen inputs only, written to a separate folder so
the frozen step outputs stay as they were.

* Effect-size curve with two separate quantities: two-sided rejection rate (type I error at effect 0) and
  positive-direction trial success (p < alpha with the comparator higher). The frozen step-5 curve reported only the
  latter, so its value at effect 0 (about 0.02) is not the two-sided type I error.
* Per endpoint source, from the frozen master tables: trials rejecting two-sided vs trials succeeding in the expected
  direction.

Usage: .venv/Scripts/python.exe scripts/sca_amendments.py [FREEZE_DIR]
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from clinical_asset.trial import paired_measure as pm  # noqa: E402

F = Path(sys.argv[1] if len(sys.argv) > 1 else "analysis_freeze/NCT06604442")
EFFECTS = (0, 2.5, 5, 7.5, 10, 12.5, 15)

if __name__ == "__main__":
    design = json.loads((F / "inputs" / "endpoint_source_design.json").read_text(encoding="utf-8"))
    out = F / "amendments"
    out.mkdir(parents=True, exist_ok=True)
    L = ["# Amendment A1: two-sided rejection vs positive-direction success", "",
         "Computed after the reveal from frozen inputs only (the design SD; the frozen master tables). The protocol's test is a "
         "two-sided paired Wilcoxon signed-rank test at alpha 0.05. 'Rejection' = p < 0.05 (either direction); 'success' = "
         "p < 0.05 with the comparator (piflufolastat) higher. At effect 0 the rejection rate is the type I error; the success "
         "rate is about half of it and must not be reported as a type I error.", "",
         "## Effect-size curve (n = 52, design SD, 10,000 simulated trials per point)", "",
         "| True effect | Two-sided rejection (MC SE) | Positive-direction success (MC SE) |", "| ---: | --- | --- |"]
    rows = [["effect", "rejection", "rejection_se", "success", "success_se"]]
    for k, eff in enumerate(EFFECTS):
        r = pm.simulated_rates(eff, design["sd_diff"], 52, 10000, 20261300 + k)
        L.append(f"| {eff:g} | {r['rejected']['rate']:.3f} ({r['rejected']['mc_se']:.3f}) | {r['success']['rate']:.3f} ({r['success']['mc_se']:.3f}) |")
        rows.append([eff, r["rejected"]["rate"], r["rejected"]["mc_se"], r["success"]["rate"], r["success"]["mc_se"]])
    L += ["", "## The 100 frozen virtual trials, per endpoint source", "",
          "| Endpoint source | Two-sided rejection | Positive-direction success |", "| --- | ---: | ---: |"]
    for src in ("design", "literature", "prestart"):
        mt = list(csv.DictReader(open(F / "step2_master" / f"master_simulation_{src}.csv", encoding="utf-8")))
        rej = sum(float(x["p_value"]) < 0.05 for x in mt)
        suc = sum(x["success"] == "True" for x in mt)
        L.append(f"| {src} | {rej}/{len(mt)} | {suc}/{len(mt)} |")
    with open(out / "A1_effect_curve.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    (out / "A1_rejection_vs_success.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print((out / "A1_rejection_vs_success.md").read_text(encoding="utf-8"))
