"""Unified planning report from locked protocol inputs and a classified accrual asset."""

import hashlib
import json
from pathlib import Path

import numpy as np

from ..trial.lock import verify
from ..trial.recruitment import accrual_plan
from ..trial.studyspec import load_studyspec

VERSION = "planning-report-1.0.0"


def _distribution(values):
    return {"median": float(np.median(values)), "pi50": [float(x) for x in np.quantile(values, [.25, .75])],
            "pi80": [float(x) for x in np.quantile(values, [.1, .9])],
            "pi95": [float(x) for x in np.quantile(values, [.025, .975])]}


def _conditional_enrollment(target, rate_year, n, seed):
    # Nth arrival in a homogeneous Poisson process. These intervals represent
    # arrival noise conditional on the stated rate, not uncertainty in that rate.
    rng = np.random.default_rng(seed)
    months = rng.gamma(shape=target, scale=12 / rate_year, size=n)
    result = _distribution(months)
    result["probability_by_month_18"] = float(np.mean(months <= 18))
    result["conditioning"] = "protocol stated accrual rate held fixed; site activation and rate uncertainty excluded"
    return result


def build(spec_lock: Path, asset_dir: Path, out_dir: Path, cohort_dir: Path | None = None,
          eligibility_dir: Path | None = None, draws: int = 5000, seed: int = 20260927,
          operations_dir: Path | None = None, results_dir: Path | None = None,
          outcomes_dir: Path | None = None, event_thresholds: list[int] | None = None,
          scenario_dir: Path | None = None) -> dict:
    if draws < 100:
        raise ValueError("draws must be at least 100")
    spec, spec_record = load_studyspec(spec_lock)
    asset = json.loads((asset_dir / "manifest.json").read_text(encoding="utf-8"))
    if asset["model"]["status"] not in {"UNRESOLVED", "BENCHMARK_ONLY"}:
        raise ValueError("Unsupported historical accrual model")
    model = json.loads((asset_dir / "accrual_model.json").read_text(encoding="utf-8"))
    if cohort_dir:
        verify(cohort_dir)
        cohort = json.loads((cohort_dir / "recruitment_summary.json").read_text(encoding="utf-8"))
        if cohort["inputs"]["studyspec"] != spec_record["files"]["studyspec.json"]:
            raise ValueError("Cohort StudySpec does not match planning StudySpec")
    else:
        cohort = None
    if eligibility_dir:
        verify(eligibility_dir)
        eligibility = json.loads((eligibility_dir / "eligibility_summary.json").read_text(encoding="utf-8"))
        if eligibility["inputs"]["studyspec"] != spec_record["files"]["studyspec.json"]:
            raise ValueError("Eligibility StudySpec does not match planning StudySpec")
    else:
        eligibility = None
    operations = json.loads((operations_dir / "manifest.json").read_text(encoding="utf-8")) if operations_dir else None
    scientific = None
    if results_dir:
        record = verify(results_dir)
        if "binary_results.json" in record["files"]:
            source = json.loads((results_dir / "binary_results.json").read_text(encoding="utf-8"))
            if source["inputs"]["studyspec"] != spec_record["files"]["studyspec.json"]:
                raise ValueError("Binary results StudySpec does not match planning StudySpec")
            scientific = {"kind": "binary_decision_rules", "truth": source["truth"],
                          "rules": [{"decision_rule_id": r["decision_rule_id"], "arm_status": r["arm_status"],
                                     "at_p0": r["design_checks"]["exact"]["at_p0"],
                                     "at_p1": r["design_checks"]["exact"]["at_p1"]}
                                    for r in source["rules"] if r.get("design_checks", {}).get("exact")],
                          "note": "Expected N and early stop are conditional on hypothetical true response p, not a single trial-wide estimate"}
        elif "trial_results.json" in record["files"]:
            source = json.loads((results_dir / "trial_results.json").read_text(encoding="utf-8"))
            if source["inputs"]["studyspec"] != spec_record["files"]["studyspec.json"]:
                raise ValueError("Trial results StudySpec does not match planning StudySpec")
            scientific = {"kind": "time_to_event_simulation", "scenario_effect_grid":
                          {name: [{"hr": x["hr"], "analysis_years": x["analysis_years_from_first_enrollment"],
                                   "events_at_analysis": x["events"]} for x in items]
                           for name, items in source["success_curve"].items()},
                          "note": "Analysis time is conditional on each hypothetical HR and protocol accrual scenario; it is not an event-threshold maturity prediction"}
    protocol_id = spec["metadata"]["protocol_id"]["text"]
    scenario_analysis = None
    if scenario_dir:
        scenario_analysis = json.loads((scenario_dir / "scenario_results.json").read_text(encoding="utf-8"))
        if scenario_analysis["studyspec_sha256"] != spec_record["files"]["studyspec.json"]:
            raise ValueError("Scenario StudySpec does not match planning StudySpec")
    plan = accrual_plan(spec)
    target = (plan["target"] or {}).get("patients")
    event_calendar = None
    if outcomes_dir and event_thresholds:
        from .events import simulate_cure_calendar
        verify(outcomes_dir)
        outcome = json.loads((outcomes_dir / "outcome_model.json").read_text(encoding="utf-8"))
        if outcome["inputs"]["studyspec"] != spec_record["files"]["studyspec.json"]:
            raise ValueError("Outcome model StudySpec does not match planning StudySpec")
        event_calendar = {str(x["rate_per_year"]): simulate_cure_calendar(
            target, x["rate_per_year"], outcome["control_efs"], outcome["loss_to_follow_up"],
            event_thresholds, draws, seed) for x in plan["scenarios"] if x["rate_per_year"]}
    scenarios = []
    for item in plan["scenarios"]:
        rate = item["rate_per_year"]
        scenarios.append({"source": "protocol_assumption", "rate_per_year": rate,
                          "evidence": item["evidence"], "enrollment_duration_months":
                          _conditional_enrollment(target, rate, draws, seed) if target and rate else None})
    report = {
        "version": VERSION, "protocol_id": protocol_id, "trial_id": spec_lock.parent.name,
        "inputs": {"studyspec_sha256": spec_record["files"]["studyspec.json"],
                   "accrual_asset_manifest_sha256": hashlib.sha256((asset_dir / "manifest.json").read_bytes()).hexdigest(),
                   "cohort_summary_sha256": hashlib.sha256((cohort_dir / "recruitment_summary.json").read_bytes()).hexdigest() if cohort_dir else None,
                   "eligibility_summary_sha256": hashlib.sha256((eligibility_dir / "eligibility_summary.json").read_bytes()).hexdigest() if eligibility_dir else None},
        "population_feasibility": {"eligible_fraction": None, "screen_failure": None, "screened_needed": None,
            "status": "UNRESOLVED", "reason": "Synthetic eligibility is not observed screen-to-enrollment conversion",
            "synthetic_eligibility_status_counts": (eligibility or {}).get("summary", {}).get("status_counts")},
        "accrual": {"target_enrollment": target, "protocol_scenarios": scenarios,
                    "historical_model": model, "patients_per_site_month": None,
                    "site_count": None, "status": "PROTOCOL_SCENARIO_ONLY" if scenarios else "UNRESOLVED",
                    "excluded_protocol_rates": plan["excluded_rates"]},
        "sample_size": {"maximum": target, "expected": None, "early_stop_probability": None,
                        "status": "UNRESOLVED" if target is not None else "TARGET_UNKNOWN"},
        "timelines": {"last_patient_in_months": {s["rate_per_year"]: s["enrollment_duration_months"] for s in scenarios},
                      "stage_1_decision": None, "primary_analysis": None,
                      "last_patient_last_visit": None, "study_completion": None},
        "retention": {"expected_dropout": None, "expected_evaluable": None, "status": "UNRESOLVED"},
        "events": {"interim_event_date": None, "final_event_date": None,
                   "scenario_calendar": event_calendar,
                   "status": "SCENARIO_ONLY" if event_calendar else "UNRESOLVED",
                   "threshold_provenance": "user-supplied scenario; not a protocol analysis rule" if event_calendar else None},
        "risk": {"probability_recruitment_by_18_months_conditional":
                 {s["rate_per_year"]: s["enrollment_duration_months"]["probability_by_month_18"] for s in scenarios},
                 "probability_analysis_on_time": None},
        "cohort_context": {"enrollable_synthetic_pool": (cohort or {}).get("summary", {}).get("pool"),
                           "warning": "Cohort days are placeholders when no protocol accrual rate is stated"},
        "validation": {"status": "NOT_BLINDLY_VALIDATED", "reason": "Planning predictions have not been locked before registry timeline access"},
        "historical_operations_evidence": operations,
        "scientific_simulation": scientific,
        "scenario_analysis": scenario_analysis,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "planning_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Trial planning summary: {protocol_id}", "",
             f"Enrollment target: {target if target is not None else 'unresolved'}.",
             f"Historical accrual model: {model['status']} — {model['reason']}.", "",
             "## Accrual and timing", ""]
    bench = model.get("unadjusted_benchmark")
    if bench:
        lines += [(f"Historical unadjusted benchmark: {bench['median']:.1f} patients per study month "
                   f"(10th–90th percentile {bench['pi80'][0]:.1f}–{bench['pi80'][1]:.1f}; {bench['n']} trials)."),
                  "This is context only; it is not a prediction for this protocol."]
    if scenarios:
        for s in scenarios:
            d = s["enrollment_duration_months"]
            lines.append(f"- Protocol assumption {s['rate_per_year']:g} patients/year: last patient in at month {d['median']:.1f} (80% conditional interval {d['pi80'][0]:.1f}–{d['pi80'][1]:.1f}); P(by month 18) = {d['probability_by_month_18']:.1%}.")
        lines.append("- Intervals include arrival variation only. Historical rate uncertainty and site activation are unresolved.")
    else:
        lines.append("- Accrual duration unresolved: no usable historical model or protocol rate.")
    lines += ["", "## Feasibility and milestones", "",
              "- Screened needed and screen failure: unresolved; no observed conversion evidence.",
              "- Sites and patients per site per month: unresolved; protocol site count is not established here.",
              "- Expected sample size and early stopping: unresolved pending decision-rule linkage.",
              "- Dropout, interim events, final analysis, and study completion: unresolved pending time-linked evidence.",
              ""]
    if operations:
        lines += [(f"Historical flow evidence: {operations['retention_trials']} trials have cumulative retention counts; "
                   f"{operations['screening_quality_counts'].get('DIRECT', 0)} report direct screened-to-enrolled conversion "
                   f"and {operations['screening_quality_counts'].get('DIRECT_RANDOMIZED', 0)} report screened-to-randomized conversion. "
                   "Neither is yet fitted to this protocol."), ""]
    if scientific and scientific["kind"] == "binary_decision_rules" and scientific["rules"]:
        lines += ["## Conditional decision-rule planning", ""]
        for rule in scientific["rules"]:
            p0, p1 = rule["at_p0"], rule["at_p1"]
            lines.append(f"- {rule['decision_rule_id']} ({', '.join(rule['arm_status'])}): at true response "
                         f"p={p0['p']:.2f}, expected N={p0['expected_n']:.1f} and early-stop probability={p0['prob_early_stop']:.1%}; "
                         f"at p={p1['p']:.2f}, expected N={p1['expected_n']:.1f} and early-stop probability={p1['prob_early_stop']:.1%}.")
        lines += ["These are per-rule values conditional on hypothetical response rates; no trial-wide expected N is identified.", ""]
    elif scientific and scientific["kind"] == "time_to_event_simulation":
        lines += ["## Conditional scientific analysis timing", ""]
        for name, grid in scientific["scenario_effect_grid"].items():
            near_null = min(grid, key=lambda item: abs(item["hr"] - 1))
            years = near_null["analysis_years"]
            lines.append(f"- {name}, HR={near_null['hr']:.2f}: analysis at {years['median']:.1f} years "
                         f"from first enrollment (5th–95th percentile {years['q05']:.1f}–{years['q95']:.1f}); "
                         f"median {near_null['events_at_analysis']['median']:.0f} events at analysis.")
        lines += ["These are existing simulator outputs under a hypothetical effect, not event-threshold maturity dates.", ""]
    if event_calendar:
        lines += ["## Event maturity scenario", "",
                  ("Thresholds are user-supplied sensitivities, not the protocol's primary analysis rule. "
                   "All target patients are assumed to enroll, with HR=1 and the locked control survival model.")]
        for rate, calendar in event_calendar.items():
            for threshold, estimate in calendar["thresholds"].items():
                when = estimate["month_from_first_patient"]
                lines.append(f"- {rate} patients/year, {threshold} events: median month {when['median']:.1f} "
                             f"(80% interval {when['pi80'][0]:.1f}–{when['pi80'][1]:.1f}); "
                             f"P(by month 36)={estimate['probability_by_month_36']:.1%}." if when else
                             f"- {rate} patients/year, {threshold} events: not reached in simulated worlds.")
        lines.append("")
    if scenario_analysis:
        lines += ["## Operational scenario comparison", "",
                  "These results condition on the assumptions in the scenario file."]
        for sc in scenario_analysis["scenarios"]:
            timing = sc["enrollment_duration_months"]
            lines.append(f"- {sc['name']}: {sc['effective_patients_per_year']:.1f} patients/year; "
                         f"median last-patient-in month {timing['median']:.1f}; "
                         f"P(by month {timing['deadline_months']:g})={timing['probability_by_deadline']:.1%}.")
        lines.append("")
    lines += ["Planning calibration: not blindly validated. Registry completion dates were not used as enrollment close dates.", ""]
    (out_dir / "planning_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report
