"""Amendment A2 (post-reveal sensitivity, frozen inputs only): the synthetic-comparator experiment under different
within-patient correlations of the simulated truth (assumption A29: 0.3 / 0.5 / 0.7). The comparator models do not
use the correlation (they cannot see the masked values), so the correlation changes only the held-out truth.

For each correlation and each of the 100 frozen trials (their usable pair counts), the truth is generated from the
`literature` source; SCA-A (P2) and SCA-B (P1) are built as in scripts/sca_experiment.py (200 synthetic draws per trial).
Output: amendments/A2_correlation_sensitivity.csv and .md.

Usage: .venv/Scripts/python.exe scripts/sca_amendment_a2.py [FREEZE_DIR]
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from clinical_asset.trial import paired_measure as pm  # noqa: E402

F = Path(sys.argv[1] if len(sys.argv) > 1 else "analysis_freeze/NCT06604442")
M = 200

if __name__ == "__main__":
    lit = json.loads((F / "inputs" / "endpoint_source_literature.json").read_text(encoding="utf-8"))
    models = {"SCA-A": pm.lognormal_from(json.loads((F / "inputs" / "endpoint_source_prestart.json").read_text(encoding="utf-8"))["reference"]),
              "SCA-B": pm.lognormal_from(lit["reference"])}
    master = list(csv.DictReader(open(F / "step2_master" / "master_simulation_literature.csv", encoding="utf-8")))
    rows = [["correlation", "model", "bias", "mae", "rmse", "coverage", "n_trials"]]
    L = ["# Amendment A2: synthetic comparator vs the within-patient correlation of the simulated truth", "",
         "| Correlation | Model | Bias | MAE | RMSE | 95% coverage |", "| ---: | --- | ---: | ---: | ---: | ---: |"]
    for rho in (0.3, 0.5, 0.7):
        src = {**lit, "correlation": rho}
        for name, (mu, sigma) in models.items():
            err, cover = [], 0
            for row in master:
                r, n = int(row["replicate"]), int(row["usable_pairs"])
                seed = 20270000 + 97 * r
                vals = pm.generate(n, src, np.random.default_rng(seed + 13))
                ref, idx = vals["reference"], vals["index"]
                true_c = float(np.median(ref - idx))
                rng = np.random.default_rng(seed + 61 + int(rho * 10))
                draws = np.array([float(np.median(np.exp(rng.normal(mu, sigma, n)) - idx)) for _ in range(M)])
                lo, hi = np.percentile(draws, [2.5, 97.5])
                err.append(float(np.median(draws)) - true_c)
                cover += lo <= true_c <= hi
            e = np.array(err)
            vals_ = [rho, name, e.mean(), np.median(np.abs(e)), math.sqrt(np.mean(e * e)), cover / len(e), len(e)]
            rows.append(vals_)
            L.append(f"| {rho:g} | {name} | {e.mean():+.2f} | {np.median(np.abs(e)):.2f} | {math.sqrt(np.mean(e * e)):.2f} | {cover}/{len(e)} |")
    (F / "amendments").mkdir(exist_ok=True)
    with open(F / "amendments" / "A2_correlation_sensitivity.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    (F / "amendments" / "A2_correlation_sensitivity.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
