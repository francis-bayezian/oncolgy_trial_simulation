"""Export the trial-level splits every registry-scale evaluation used, so the claim "whole trials, never rows, are held
out" can be checked from a file rather than from the code.

* Safety asset V3.1: one 60/20/20 split of trials into fit / calibrate / report, reproduced from the cached arm table
  with the build's own seed. Every adverse-event observation inherits the split of its trial; the 90% coverage and log
  scores are computed on the report trials only, and the spread factor is chosen on the calibrate trials only.
* Trial-failure model: 5 folds of trials (one row per trial), seed 0.
* Accrual-rate model: 10 folds of trials with a directly observed recruitment window (one row per trial), seed 0.

Checks: the three safety sets are disjoint and cover every trial; no trial is in two folds.
Output: data/validation/trial_splits.json.
"""

import json
import random
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from clinical_asset.safety3 import _arm_sizes

    cache = json.loads((ROOT / "data/safety_asset_v3_1/arm_table.json").read_text(encoding="utf-8"))
    arms, observations = cache["arms"], [{**o, "arm": tuple(o["arm"])} for o in cache["observations"]]
    _arm_sizes(arms, observations)
    arms = [a for a in arms if a.get("n")]
    ncts = sorted({a["nct_id"] for a in arms})
    held = random.Random(20260927).sample(ncts, int(2 * 0.2 * len(ncts)))
    calib, report = sorted(set(held[::2])), sorted(set(held[1::2]))
    fit = sorted(set(ncts) - set(calib) - set(report))
    assert not (set(fit) & set(calib) or set(fit) & set(report) or set(calib) & set(report))
    assert len(fit) + len(calib) + len(report) == len(ncts)
    obs_by = {k: sum(o["nct_id"] in s for o in observations) for k, s in (("fit", set(fit)), ("calibrate", set(calib)), ("report", set(report)))}
    manifest = json.loads((ROOT / "data/locked/safety_asset/v3.1.0/manifest.json").read_text(encoding="utf-8"))

    rows = pq.read_table(ROOT / "data/locked/planning_asset/operational_v2.2.0/trial_outcomes.parquet", columns=["nct_id"])["nct_id"].to_pylist()
    order = np.random.default_rng(0).permutation(len(rows))
    fail_folds = {f: sorted(rows[i] for i in order[f::5]) for f in range(5)}
    assert sum(len(v) for v in fail_folds.values()) == len(set(rows)) == len(rows)

    rates = pq.read_table(ROOT / "data/locked/planning_asset/operational_v2.2.0/study_level_rates.parquet",
                          columns=["nct_id", "quality"]).to_pylist()
    idx = [i for i, r in enumerate(rates) if r["quality"] == "ACCRUAL_DIRECT"]
    order = np.random.default_rng(0).permutation(idx)
    acc_folds = {f: sorted(rates[i]["nct_id"] for i in order[f::10]) for f in range(10)}
    assert len({n for v in acc_folds.values() for n in v}) == len(idx)

    doc = {
        "principle": "whole trials are assigned to a split; every observation of a trial inherits its trial's split",
        "safety_asset_v3_1": {
            "seed": 20260927, "trials": len(ncts), "observations": len(observations),
            "fit_trials": fit, "calibrate_trials": calib, "report_trials": report,
            "observations_by_split": obs_by,
            "reported_listed_observations": manifest["validation"]["listed"]["count"],
            "note": ("fit: event models; calibrate: the spread factor (chosen to give 90% coverage there); report: all published "
                     "coverage and log scores. The V2 comparator was fitted on all trials, including the report trials, so its "
                     "score is in-sample and is not used as a comparator in the paper; the fair comparator is the "
                     "uncalibrated V3.1 model on the same report trials."),
        },
        "failure_model_5fold": {"seed": 0, "trials": len(rows), "folds": fail_folds},
        "accrual_rate_10fold": {"seed": 0, "direct_window_trials": len(idx), "folds": acc_folds},
    }
    out = ROOT / "data/validation/trial_splits.json"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"safety: {len(fit)} fit / {len(calib)} calibrate / {len(report)} report trials; observations {obs_by}")
    print(f"failure model: {len(rows)} trials in 5 folds; accrual: {len(idx)} direct-window trials in 10 folds")


if __name__ == "__main__":
    main()
