"""Discrimination and calibration of the trial-failure model on held-out trials.

Reads the locked operational asset's trial table (the covariates the model uses) and re-runs its fitting procedure:

* random 5-fold cross-validation with the asset's own seed and fold order (reproduces the stored AUC), and
* a temporal split: fit on trials that started before a cut-off year, score trials that started in or after it.

"Accrual failure" is terminated for poor accrual or withdrawn (the outcome the planning report flags). Reported:
AUC, Brier score (with the base-rate Brier), calibration intercept and slope (logistic recalibration of the outcome on
logit(predicted)), reliability by decile, and the multinomial log loss against the base rates.

Output: data/validation/failure_model_scores.json and .csv (per-decile reliability).
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from scipy import optimize
from scipy.stats import rankdata

from clinical_asset.planning.operational import OUTCOMES, fit_failure, predict_failure

FAIL = [OUTCOMES.index("terminated_accrual"), OUTCOMES.index("withdrawn")]


def auc(p, y):
    r = rankdata(p)
    pos, neg = y.sum(), (~y).sum()
    return float((r[y].sum() - pos * (pos + 1) / 2) / (pos * neg))


def recalibration(p, y):
    """Logistic regression of y on logit(p): intercept 0 and slope 1 mean perfectly calibrated."""
    z = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1))

    def nll(t):
        eta = t[0] + t[1] * z
        return float(np.sum(np.logaddexp(0, eta) - y * eta))
    slope = optimize.minimize(nll, [0.0, 1.0], method="BFGS").x
    # calibration-in-the-large: intercept with the slope fixed at 1 (offset logit(p))
    inter = optimize.minimize_scalar(lambda a: nll([a, 1.0]), bounds=(-5, 5), method="bounded").x
    return float(inter), float(slope[1]), float(slope[0])


def score(P, rows):
    y_cls = np.array([OUTCOMES.index(r["outcome"]) for r in rows])
    y = np.isin(y_cls, FAIL)
    p = P[:, FAIL].sum(axis=1)
    base = y.mean()
    inter, slope, slope_inter = recalibration(p, y.astype(float))
    bins = np.quantile(p, np.linspace(0, 1, 11))
    idx = np.clip(np.searchsorted(bins, p, side="right") - 1, 0, 9)
    rel = [{"decile": d + 1, "n": int((idx == d).sum()), "predicted": float(p[idx == d].mean()), "observed": float(y[idx == d].mean())}
           for d in range(10) if (idx == d).any()]
    base_cls = np.bincount(y_cls, minlength=len(OUTCOMES)) / len(y_cls)
    return {"trials": len(rows), "events": int(y.sum()), "event_rate": float(base),
            "auc": auc(p, y), "brier": float(np.mean((p - y) ** 2)), "brier_base_rate": float(base * (1 - base)),
            "brier_skill": float(1 - np.mean((p - y) ** 2) / (base * (1 - base))),
            "calibration_in_the_large": inter, "calibration_slope": slope, "calibration_slope_intercept": slope_inter,
            "multinomial_log_loss": float(-np.mean(np.log(P[np.arange(len(y_cls)), y_cls]))),
            "multinomial_log_loss_base_rate": float(-np.mean(np.log(base_cls[y_cls]))),
            "max_abs_decile_error": float(max(abs(r["predicted"] - r["observed"]) for r in rel)), "reliability": rel}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default="data/locked/planning_asset/operational_v2.2.0")
    ap.add_argument("--cutoff-year", type=int, default=2016)
    ap.add_argument("--out", default="data/validation")
    a = ap.parse_args()
    rows = pq.read_table(Path(a.asset) / "trial_outcomes.parquet").to_pylist()

    # (1) random 5-fold CV exactly as the asset build (seed 0, permutation order, fold f = order[f::5])
    order = np.random.default_rng(0).permutation(len(rows))
    P = np.zeros((len(rows), len(OUTCOMES)))
    for f in range(5):
        test = order[f::5]
        model = fit_failure([rows[i] for i in np.setdiff1d(order, test)])
        P[test] = predict_failure(model, [rows[i] for i in test])
    cv = score(P, rows)
    stored = json.loads((Path(a.asset) / "manifest.json").read_text(encoding="utf-8"))["failure_model"]["cross_validation"]["accrual_failure_auc"]
    assert abs(cv["auc"] - stored) < 1e-6, (cv["auc"], stored)

    # (2) temporal: fit on trials started before the cut-off, score those started from it on
    train = [r for r in rows if r["start_year"] < a.cutoff_year]
    test = [r for r in rows if r["start_year"] >= a.cutoff_year]
    temporal = score(predict_failure(fit_failure(train), test), test)
    temporal["fit_trials"], temporal["cutoff_start_year"] = len(train), a.cutoff_year
    temporal["note"] = ("later-starting trials have had less time to be terminated or withdrawn; outcome rates differ by era, "
                        "so calibration-in-the-large here also measures drift")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"asset": a.asset, "outcome": "terminated for poor accrual or withdrawn", "random_5fold_cv": cv, "temporal": temporal}
    (out / "failure_model_scores.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    with open(out / "failure_model_scores.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["split", "decile", "n", "predicted", "observed"])
        for name, s in (("random_5fold_cv", cv), ("temporal", temporal)):
            for r in s["reliability"]:
                w.writerow([name, r["decile"], r["n"], round(r["predicted"], 4), round(r["observed"], 4)])
    for name, s in (("CV", cv), ("temporal", temporal)):
        print(f"{name}: n={s['trials']} AUC {s['auc']:.3f} Brier {s['brier']:.4f} (base {s['brier_base_rate']:.4f}) "
              f"CITL {s['calibration_in_the_large']:+.3f} slope {s['calibration_slope']:.3f}")


if __name__ == "__main__":
    main()
