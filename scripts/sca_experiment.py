"""Synthetic comparator experiment inside the virtual trials (paper steps 7-10).

In every replicate the index exposure (flotufolastat) stays visible; the comparator exposure (piflufolastat) is MASKED
and replaced by a synthetic comparator generated from a frozen model that may use only allowed inputs
(SCA_ALLOWED_INPUTS.csv). The treatment contrast is computed with the synthetic comparator, then the held-out
comparator is revealed.

Truth (held out): per-participant comparator values from a named endpoint source (paired_measurements_<truth>.csv,
written by scripts/replicate_master_table.py). The comparator model must not be the truth's own model (step 9): the
primary comparator draws from an INDEPENDENT allowed source; a same-source comparator is reported only as a
self-consistency bound.

Per replicate: true and synthetic comparator median and IQR; true paired contrast (median of comparator - index);
synthetic contrast (the median over M synthetic draws) with a 95% interval (2.5 / 97.5 percentiles of the M draws);
absolute error, signed bias, squared error; interval covers the truth; same inferential conclusion (the protocol's
paired test, alpha, direction).
Across replicates: mean bias, median absolute error, RMSE, coverage, conclusions agreeing.

Usage: .venv/Scripts/python.exe scripts/sca_experiment.py ID BASE_VERSION INPUTS_DIR OUT_DIR
"""

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from clinical_asset.trial import paired_measure as pm  # noqa: E402

M = 200
EXPERIMENTS = [  # (name, truth source, comparator model, role)
    ("SCA-A", "literature", {"input": "P2 (pre-start, independent)", "stat": "prestart"}, "primary: comparator from an independent allowed source"),
    ("SCA-B", "literature", {"input": "P1 (same evidence as the truth)", "stat": "literature"}, "self-consistency bound (same evidence; within-patient link unknown)"),
    ("SCA-R", "prestart", {"input": "P1 (pre-results, independent of P2)", "stat": "literature"}, "reverse check: truth from P2, comparator from P1"),
]


def comparator_model(inputs: Path, stat: str) -> dict:
    src = json.loads((inputs / f"endpoint_source_{stat}.json").read_text(encoding="utf-8"))
    mu, sigma = pm.lognormal_from(src["reference"])
    return {"mu": mu, "sigma": sigma, "evidence": src["reference"]}


def summary(v: np.ndarray) -> dict:
    return {"median": float(np.median(v)), "q1": float(np.percentile(v, 25)), "q3": float(np.percentile(v, 75))}


def main(study: str, version: str, inputs: Path, out: Path) -> Path:
    spec = json.loads((Path("data/locked") / study / f"studyspec_v{version}" / "studyspec.json").read_text(encoding="utf-8"))
    an = next(a for a in spec["analyses"] if a.get("primary"))
    alpha = float((an.get("alpha") or {}).get("value") or 0.05)
    root = Path(f"data/trial/runs/{study}/v{version}/replicates")
    reps = sorted(d for d in root.glob("r[0-9][0-9][0-9]"))
    out.mkdir(parents=True, exist_ok=True)
    models = {}
    L = [f"# Synthetic comparator experiment: {study} (base v{version})", "",
         "Index exposure visible; comparator exposure masked and replaced by a synthetic comparator from a frozen model "
         "of allowed inputs only; then the held-out comparator is revealed. This is INTERNAL simulation validation: the "
         "truth is itself simulated from pre-result evidence, so agreement here is not proof that a synthetic comparator "
         "can replace a real one.", ""]
    per_rows = []
    for name, truth, cm, role in EXPERIMENTS:
        model = comparator_model(inputs, cm["stat"])
        models[name] = {"truth_source": truth, "comparator_input": cm["input"], "lognormal_mu": model["mu"], "lognormal_sigma": model["sigma"],
                        "evidence": model["evidence"], "role": role, "draws_per_trial": M, "uses_masked_values": False}
        errs, biases, covers, agree, rows = [], [], 0, 0, []
        for rd in reps:
            r = int(rd.name[1:])
            f = rd / f"paired_measurements_{truth}.csv"
            data = list(csv.DictReader(open(f, encoding="utf-8")))
            ref = np.array([float(x["reference"]) for x in data])          # held out (masked)
            idx = np.array([float(x["index"]) for x in data])              # visible
            true_c = float(np.median(ref - idx))
            true_test = pm.analyse(ref - idx, alpha=alpha)
            rng = np.random.default_rng(20270000 + 97 * r + 41 + EXPERIMENTS.index((name, truth, cm, role)))
            draws = np.array([float(np.median(np.exp(rng.normal(model["mu"], model["sigma"], len(idx))) - idx)) for _ in range(M)])
            synth = np.exp(rng.normal(model["mu"], model["sigma"], len(idx)))    # one synthetic comparator arm for the test
            sca_c = float(np.median(draws))
            lo, hi = np.percentile(draws, [2.5, 97.5])
            sca_test = pm.analyse(synth - idx, alpha=alpha)
            e = sca_c - true_c
            errs.append(e)
            covers += lo <= true_c <= hi
            agree += sca_test["success"] == true_test["success"]
            row = {"experiment": name, "replicate": r, "n": len(idx), "true_comparator": summary(ref), "synthetic_comparator": summary(synth),
                   "true_contrast": true_c, "sca_contrast": sca_c, "sca_interval": [float(lo), float(hi)], "signed_bias": e,
                   "absolute_error": abs(e), "squared_error": e * e, "covers": bool(lo <= true_c <= hi),
                   "true_success": true_test["success"], "sca_success": sca_test["success"], "same_conclusion": sca_test["success"] == true_test["success"]}
            rows.append(row)
        per_rows += rows
        e = np.array(errs)
        n = len(e)
        tc = np.array([x["true_contrast"] for x in rows])
        sc = np.array([x["sca_contrast"] for x in rows])
        tm = np.array([x["true_comparator"]["median"] for x in rows])
        sm = np.array([x["synthetic_comparator"]["median"] for x in rows])
        L += [f"## {name}: {role}", "",
              f"Truth: `{truth}` source. Comparator model: lognormal from {cm['input']} (median {math.exp(model['mu']):.1f}, "
              f"sigma {model['sigma']:.3f}); no access to the masked values.", "",
              "| Quantity | Value |", "| --- | --- |",
              f"| comparator median, true (p10 / p50 / p90 over trials) | {np.percentile(tm, 10):.1f} / {np.percentile(tm, 50):.1f} / {np.percentile(tm, 90):.1f} |",
              f"| comparator median, synthetic | {np.percentile(sm, 10):.1f} / {np.percentile(sm, 50):.1f} / {np.percentile(sm, 90):.1f} |",
              f"| paired contrast, true | {np.percentile(tc, 10):.1f} / {np.percentile(tc, 50):.1f} / {np.percentile(tc, 90):.1f} |",
              f"| paired contrast, synthetic comparator | {np.percentile(sc, 10):.1f} / {np.percentile(sc, 50):.1f} / {np.percentile(sc, 90):.1f} |",
              f"| mean signed bias | {e.mean():+.2f} |", f"| median absolute error | {np.median(np.abs(e)):.2f} |",
              f"| RMSE | {math.sqrt(np.mean(e * e)):.2f} |", f"| 95% interval covers the true contrast | {covers}/{n} |",
              f"| same inferential conclusion | {agree}/{n} |", ""]
    with open(out / "sca_per_trial.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(x) + "\n" for x in per_rows)
    (out / "sca_models.json").write_text(json.dumps(models, indent=1), encoding="utf-8")
    (out / "sca_experiment.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out / "sca_experiment.md"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])))
