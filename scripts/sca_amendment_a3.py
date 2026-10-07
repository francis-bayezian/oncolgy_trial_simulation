"""Amendment A3 (post-reveal, design inputs only): the operating-characteristic surface of the protocol's primary
analysis - P(two-sided rejection) and P(positive-direction success) over effect size x analysable sample size, with the
design SD of paired differences (25.15) and the protocol's paired Wilcoxon signed-rank test at alpha 0.05.

Output: amendments/A3_operating_surface.csv (effect, n, rejection, success, replicates).
Usage: .venv/Scripts/python.exe scripts/sca_amendment_a3.py [FREEZE_DIR] [REPLICATES]
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

F = Path(sys.argv[1] if len(sys.argv) > 1 else "analysis_freeze/NCT06604442")
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
EFFECTS = np.round(np.arange(0, 20.01, 1.0), 2)
NS = list(range(30, 82, 2))                 # step 2: N = 52 (the protocol target) is a grid point

if __name__ == "__main__":
    sd = json.loads((F / "inputs" / "endpoint_source_design.json").read_text(encoding="utf-8"))["sd_diff"]
    rows = [["effect", "n", "rejection", "success", "replicates"]]
    for i, eff in enumerate(EFFECTS):
        for j, n in enumerate(NS):
            x = np.random.default_rng(20261400 + 1000 * i + j).normal(eff, sd, (REPS, n))
            p = stats.wilcoxon(x, axis=1, method="approx").pvalue
            rej = p < 0.05
            rows.append([float(eff), n, float(rej.mean()), float((rej & (np.median(x, axis=1) > 0)).mean()), REPS])
    (F / "amendments").mkdir(exist_ok=True)
    with open(F / "amendments" / "A3_operating_surface.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    at = {(r[0], r[1]): r for r in rows[1:]}
    print("design point (10, 52):", at.get((10.0, 52)), "| null (0, 52):", at.get((0.0, 52)))
