"""Validation scorecard: every predictive component against its held-out (registry-scale) evidence.

Target (user, 2026-09-28): reported results fall inside the system's prediction intervals at the nominal rate
(a 90% interval holds the reported value about 90% of the time), with intervals as narrow as the evidence allows.
A component passes when its held-out coverage is within 5 points below to 7 points above nominal; sharpness
(interval width) is reported next to it, because wide intervals pass coverage trivially.

Sources are the assets' own held-out validations (never the development protocols) plus, separately, the
unblinded development protocols (too few to estimate coverage: shown, not scored).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict:
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def verdict(coverage: float | None, nominal: float) -> str:
    if coverage is None:
        return "NOT_MEASURED"
    if coverage < nominal - 0.05:
        return "BELOW (intervals too narrow)"
    if coverage > nominal + 0.07:
        return "ABOVE (intervals wider than needed)"
    return "PASS"


def main(safety_dir: str = "data/safety_asset_v3_1", operational_dir: str = "data/planning_asset_v2_2/operational") -> dict:
    rows = []
    op = _load(f"{operational_dir}/manifest.json")
    if op:
        cv = max(op["rate_model"]["cross_validation"], key=lambda c: c["mean_log_predictive_density"])
        for level in ("0.5", "0.8", "0.95"):
            rows.append({"component": "accrual rate (patients/month)", "held_out": cv["direct_trials"], "nominal": float(level),
                         "coverage": cv["coverage"][level], "sharpness": f"median relative error {cv['median_relative_error_rate']:.0%}",
                         "source": f"{operational_dir} 10-fold CV"})
        f = op["failure_model"]["cross_validation"]
        worst = max(abs(d["predicted"] - d["observed"]) for d in f["accrual_failure_reliability"])
        rows.append({"component": "trial accrual failure (withdrawn or terminated for accrual)", "held_out": f["trials"], "nominal": None,
                     "coverage": None, "sharpness": f"AUC {f['accrual_failure_auc']:.2f}; worst decile |predicted - observed| {worst:.3f}",
                     "source": "5-fold CV", "verdict": "PASS (calibrated)" if worst < 0.05 else "BELOW (miscalibrated)"})
    sa = _load(f"{safety_dir}/manifest.json")
    if sa:
        v = sa["validation"]
        for part, label in (("listed", "adverse events: reported counts"), ("zeros", "adverse events: serious events reported absent")):
            rows.append({"component": label, "held_out": v[part]["count"], "nominal": 0.90, "coverage": v[part]["coverage_90"]["v3"],
                         "sharpness": f"log score {v[part]['mean_log_predictive_probability']['v3']:.2f} (V2 in-sample "
                                      f"{v[part]['mean_log_predictive_probability']['v2_published_in_sample']:.2f})",
                         "source": f"{safety_dir}: 60/20/20 fit/calibrate/report split; spread factor {sa.get('sigma_scale')}"})
    b = _load("data/simulation_parameters_v3/validation/baseline_backtests.json")
    if b:
        rows.append({"component": "baseline: mean age", "held_out": b["held_out_studies"], "nominal": 0.95, "coverage": b["age_mean"]["coverage_95"],
                     "sharpness": f"median 95% width {b['age_mean']['median_width_95']:.1f} years; MAE {b['age_mean']['mean_abs_error']:.1f}",
                     "source": "V3 baseline backtest (refit without each study)"})
        rows.append({"component": "baseline: share female", "held_out": b["held_out_studies"], "nominal": 0.95, "coverage": b["female_share"]["coverage_95"],
                     "sharpness": f"MAE {b['female_share']['mean_abs_error']:.3f}", "source": "V3 baseline backtest"})
    p = _load("data/simulation_parameters_v3/validation/proportion_calibration.json")
    if p:
        m = p["overall"]["m3_normal"]
        for level, key in ((0.5, "coverage_50"), (0.8, "coverage_80"), (0.95, "coverage_95")):
            rows.append({"component": "outcome proportions (response, safety)", "held_out": m["held_out"], "nominal": level, "coverage": m[key],
                         "sharpness": f"median 95% width {m['median_width_95']:.2f}; MAE {m['mean_abs_error']:.3f}",
                         "source": "V3 leave-one-study-out"})
    s = _load("data/simulation_parameters_v3/validation/survival_backtests.json")
    if s:
        m = s["by_model"]["fused_S0_pow_HR"]
        for level, key in ((0.5, "coverage_50"), (0.95, "coverage_95")):
            rows.append({"component": "survival (arm medians, landmarks)", "held_out": m["held_out"], "nominal": level, "coverage": m[key],
                         "sharpness": f"median 95% width {m['median_width_95']:.2f} (log scale)",
                         "source": "V3 backtest (checks fusion consistency; the HR posterior includes the trial)"})
    for r in rows:
        r.setdefault("verdict", verdict(r["coverage"], r["nominal"]) if r["nominal"] is not None else "NOT_MEASURED")
    doc = {"target": "held-out coverage at the nominal level (-5 to +7 points), with sharpness reported", "components": rows}
    out = ROOT / "data/validation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "scorecard.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    lines = ["# Validation scorecard", "", doc["target"] + ".", "",
             "| component | held out | nominal | coverage | verdict | sharpness | source |", "| --- | ---: | ---: | ---: | --- | --- | --- |"]
    for r in rows:
        cov = f"{r['coverage']:.0%}" if r["coverage"] is not None else "-"
        nom = f"{r['nominal']:.0%}" if r["nominal"] is not None else "-"
        lines.append(f"| {r['component']} | {r['held_out']} | {nom} | {cov} | {r['verdict']} | {r['sharpness']} | {r['source']} |")
    (out / "scorecard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return doc


if __name__ == "__main__":
    main(*sys.argv[1:])
