"""Conditional operational scenarios with every non-evidence input explicitly named."""

import json
from pathlib import Path

import numpy as np

from ..trial.lock import verify
from ..trial.studyspec import load_studyspec
from .events import simulate_cure_calendar
from .report import _conditional_enrollment, _distribution


def simulate(spec_lock: Path, scenarios_path: Path, out_dir: Path, outcomes_dir: Path | None = None,
             draws: int = 5000, seed: int = 20260927) -> dict:
    spec, record = load_studyspec(spec_lock)
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))["scenarios"]
    outcome = None
    if outcomes_dir:
        verify(outcomes_dir)
        outcome = json.loads((outcomes_dir / "outcome_model.json").read_text(encoding="utf-8"))
        if outcome["inputs"]["studyspec"] != record["files"]["studyspec.json"]:
            raise ValueError("Outcome model StudySpec does not match scenario StudySpec")
    rows = []
    for i, sc in enumerate(scenarios):
        n = int(sc["target_enrollment"])
        if n < 1:
            raise ValueError("target_enrollment must be positive")
        sites, productivity = sc.get("sites"), sc.get("patients_per_site_month")
        total_rate = sc.get("patients_per_year")
        if total_rate is None and sites is not None and productivity is not None:
            share = float(sc.get("underperforming_share", 0))
            multiplier = float(sc.get("underperforming_multiplier", 1))
            if not (0 <= share <= 1 and 0 <= multiplier <= 1):
                raise ValueError("underperformance share and multiplier must be in [0,1]")
            total_rate = 12 * float(sites) * float(productivity) * (1 - share * (1 - multiplier))
        if total_rate is None or total_rate <= 0:
            raise ValueError(f"scenario {sc['name']} requires a positive total rate or sites and site productivity")
        deadline = float(sc.get("enrollment_deadline_months", 18))
        duration = _conditional_enrollment(n, float(total_rate), draws, seed + i)
        rng = np.random.default_rng(seed + i)
        arrivals = rng.gamma(shape=n, scale=12 / float(total_rate), size=draws)
        duration["deadline_months"] = deadline
        duration["probability_by_deadline"] = float(np.mean(arrivals <= deadline))
        conversion = sc.get("enrolled_per_screened")
        screening = None
        if conversion is not None:
            p = float(conversion)
            if not 0 < p <= 1:
                raise ValueError("enrolled_per_screened must be in (0,1]")
            needed = n + rng.negative_binomial(n, p, size=draws)
            screening = {"assumed_conversion": p, "screened_needed": _distribution(needed),
                         "probability_screen_failures_over_50_percent": float(np.mean((needed - n) / needed > .5))}
        event_calendar = None
        thresholds = sc.get("event_thresholds") or []
        if thresholds:
            if outcome is None:
                raise ValueError("event thresholds require a locked outcome model")
            event_calendar = simulate_cure_calendar(n, float(total_rate), outcome["control_efs"],
                outcome["loss_to_follow_up"], [int(x) for x in thresholds], draws, seed + i,
                hr=float(sc.get("hazard_ratio", 1)), by_month=int(sc.get("event_deadline_months", 36)))
        rows.append({"name": sc["name"], "assumptions": sc, "effective_patients_per_year": float(total_rate),
                     "enrollment_duration_months": duration, "screening": screening,
                     "event_calendar": event_calendar,
                     "status": "CONDITIONAL_SCENARIO_NOT_CALIBRATED"})
    doc = {"protocol_id": spec["metadata"]["protocol_id"]["text"], "studyspec_sha256": record["files"]["studyspec.json"],
           "seed": seed, "draws": draws, "scenarios": rows,
           "interpretation": "Inputs in the scenario file are assumptions. Intervals condition on fixed rates and conversion; no historical calibration is claimed."}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scenario_results.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    lines = [f"# Planning scenarios: {doc['protocol_id']}", "", doc["interpretation"], ""]
    for row in rows:
        d = row["enrollment_duration_months"]
        lines += [f"## {row['name']}", "", f"Effective accrual: {row['effective_patients_per_year']:.1f} patients/year.",
                  (f"Last patient in: median month {d['median']:.1f}, 80% interval {d['pi80'][0]:.1f}–{d['pi80'][1]:.1f}; "
                   f"P(by month {d['deadline_months']:g})={d['probability_by_deadline']:.1%}.")]
        if row["screening"]:
            s = row["screening"]["screened_needed"]
            lines.append(f"Screened needed under the assumed conversion: median {s['median']:.0f}, "
                         f"80% interval {s['pi80'][0]:.0f}–{s['pi80'][1]:.0f}.")
        if row["event_calendar"]:
            for threshold, e in row["event_calendar"]["thresholds"].items():
                when = e["month_from_first_patient"]
                lines.append(f"{threshold} events: median month {when['median']:.1f} "
                             f"(80% interval {when['pi80'][0]:.1f}–{when['pi80'][1]:.1f})." if when else
                             f"{threshold} events: not reached in simulated worlds.")
        lines.append("")
    (out_dir / "scenario_report.md").write_text("\n".join(lines), encoding="utf-8")
    return doc
