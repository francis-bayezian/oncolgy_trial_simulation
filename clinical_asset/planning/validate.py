"""Planning: blind comparison of a locked planning report with the trial's registry timeline.

The registry gives the actual start, primary completion, enrollment count (ACTUAL) and overall status. The accrual
window from start to primary completion bounds the time the trial spent recruiting, so:

* observed rate = enrolled / window is a lower bound on the recruiting rate (recruitment may have ended earlier);
* the prediction is scored by its own predictive probability of an outcome at least as poor as the registry's:
  P(at most the actual enrollment within the window), mixing Poisson arrivals over the predicted rate distribution.

The predicted rate distribution is represented by a log-normal matched to the report's 10th and 90th percentiles
(the accrual model predicts log rates; this reconstructs it from the locked quantiles, not from the model).
"""

import datetime as dt
import json
from pathlib import Path

import numpy as np
from scipy import stats

VALIDATE_VERSION = "planning-compare-1.0.0"
Z90 = stats.norm.ppf(0.9)


def _date(struct: dict | None) -> dt.date | None:
    if not struct or not struct.get("date"):
        return None
    parts = [int(x) for x in struct["date"].split("-")]
    return dt.date(parts[0], parts[1], parts[2] if len(parts) > 2 else 15)


def registry_timeline(registry: dict) -> dict:
    p = registry["protocolSection"]
    s, e = p["statusModule"], p["designModule"].get("enrollmentInfo", {})
    start, pc = _date(s.get("startDateStruct")), _date(s.get("primaryCompletionDateStruct"))
    return {"overall_status": s.get("overallStatus"), "why_stopped": s.get("whyStopped"),
            "start": start, "start_type": (s.get("startDateStruct") or {}).get("type"),
            "primary_completion": pc, "primary_completion_type": (s.get("primaryCompletionDateStruct") or {}).get("type"),
            "enrolled": e.get("count"), "enrollment_type": e.get("type"),
            "window_years": (pc - start).days / 365.25 if start and pc and pc > start else None}


def score(predicted_rate_q: dict, target: int, enrolled: int, window_years: float, draws: int = 200_000, seed: int = 0,
          exact: bool = False) -> dict:
    """Score a predicted accrual-rate distribution (patients/year quantiles) against an actual enrollment in a window."""
    mu = float(np.log(predicted_rate_q["median"]))
    sigma = float(np.log(predicted_rate_q["q90"] / predicted_rate_q["q10"]) / (2 * Z90))
    lam = np.exp(np.random.default_rng(seed).normal(mu, sigma, draws)) * window_years
    observed = enrolled / window_years
    if sigma > 0:
        pct = float(stats.norm.cdf((np.log(observed) - mu) / sigma)) if observed > 0 else 0.0
    else:                                     # a point rate (a protocol-stated rate): the percentile is 0 or 1
        pct = float(observed >= predicted_rate_q["median"])
    p_short = float(stats.poisson.cdf(enrolled, lam).mean())
    p_target = float(stats.poisson.sf(target - 1, lam).mean())
    reached = enrolled >= target
    if exact:          # the window is the verified recruitment period: enrolled / window IS the rate
        # two-sided tail of the enrolled count over that window (Poisson arrivals mixed over the predicted rate); unlike a
        # percentile of the rate, it stays meaningful for a single stated rate
        p_high = float(stats.poisson.sf(enrolled - 1, lam).mean())
        headline = {"event": f"{enrolled} enrolled over the verified {window_years:.2f}-year recruitment window ({observed:.2f}/year)",
                    "predicted_probability": min(1.0, 2 * min(p_short, p_high)), "kind": "two-sided predictive tail probability of the enrolled count"}
    elif reached:
        headline = {"event": f"target of {target} reached within the {window_years:.2f}-year window", "predicted_probability": p_target}
    else:
        headline = {"event": f"at most {enrolled} enrolled within the {window_years:.2f}-year window", "predicted_probability": p_short}
    return {"observed_rate_per_year_lower_bound": observed, "observed_is_lower_bound": not exact,
            "observed_rate_percentile_in_prediction": pct,
            "inside_80_interval": predicted_rate_q["q10"] <= observed <= predicted_rate_q["q90"],
            "p_at_most_actual_enrollment_in_window": p_short,
            "p_target_reached_in_window": p_target,
            "target_reached": reached,
            "headline": headline,
            "reconstruction": {"distribution": "log-normal from locked q10/median/q90" if sigma > 0 else "point rate", "mu": mu, "sigma": sigma}}


def recruitment_window(model_client, registry: dict) -> dict | None:
    """The verified recruitment window stated in the registry's recruitment details (the accrual asset's extraction and
    verifier votes), or None."""
    from . import accrual as ac

    t = ac.trial_features(registry, {})
    if model_client is None or not t["recruitment_details"]:
        return None
    w = ac.extract_windows(model_client, [t]).get(t["nct_id"])
    return w if w and w.get("status") == "USABLE" else None


def score_failure(failure: dict, registry: dict) -> dict:
    from .operational import outcome

    st = registry["protocolSection"]["statusModule"]
    observed = outcome({"status": st.get("overallStatus"), "why_stopped": st.get("whyStopped")})
    if failure.get("status") != "RESOLVED" or observed is None:
        return {"status": "UNRESOLVED", "reason": "no failure prediction or no final registry status", "observed_outcome": observed}
    p, base = failure["probabilities"][observed], failure["base_rates"][observed]
    return {"status": "SCORED", "observed_outcome": observed, "predicted_probability": p, "base_rate": base,
            "log_score_gain_over_base_rate": float(np.log(p) - np.log(base)), "predicted": failure["probabilities"]}


def run(planning_lock: Path, registry_file: Path, registry_fetched_at: str, out_dir: Path, model_client=None) -> dict:
    from ..trial.lock import load_locked, verify

    rec = verify(planning_lock)
    report = load_locked(planning_lock, "planning_report.json")
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    actual = registry_timeline(registry)
    window = recruitment_window(model_client, registry)
    exact = window is not None
    if exact:
        actual["window_years"] = (dt.date.fromisoformat(window["end"]) - dt.date.fromisoformat(window["start"])).days / 365.25
        actual["window_kind"] = f"RECRUITMENT (verified: {window['start_quote']!r} to {window['end_quote']!r}; votes {window['verification']['votes']})"
    else:
        actual["window_kind"] = "REGISTRY_INTERVAL (start to primary completion; includes any follow-up, so the rate is a lower bound)"
    acc = report["accrual"]
    hist = acc.get("historical_model") or {}
    doc = {"validate_version": VALIDATE_VERSION, "planning_locked_at": rec["locked_at"], "registry_fetched_at": registry_fetched_at,
           "order_verified": rec["locked_at"] < registry_fetched_at, "report_marked_blind": bool(report.get("blind")),
           "nct_id": registry["protocolSection"]["identificationModule"]["nctId"], "protocol_id": report.get("protocol_id"),
           "target_patients": acc.get("target_patients"), "actual": actual,
           "protocol_scenarios": []}
    usable_actual = actual["enrolled"] is not None and actual["window_years"] and actual["enrollment_type"] == "ACTUAL"
    for sc in acc.get("protocol_scenarios", []):
        row = {"scenario": sc.get("scenario"), "status": sc.get("status") or "RESOLVED", "patients_per_year": sc.get("patients_per_year")}
        if sc.get("patients_per_year") and usable_actual:
            r = sc["patients_per_year"]
            row.update(status="SCORED", **score({"median": r, "q10": r, "q90": r}, acc["target_patients"], actual["enrolled"], actual["window_years"], exact=exact))
        doc["protocol_scenarios"].append(row)
    if hist.get("status") != "RESOLVED":
        doc["historical_model"] = {"status": "UNRESOLVED", "reason": "the locked report has no historical accrual prediction"}
    elif actual["enrolled"] is None or not actual["window_years"] or actual["enrollment_type"] != "ACTUAL":
        doc["historical_model"] = {"status": "UNRESOLVED", "reason": "the registry gives no actual enrollment or no start-to-primary-completion window"}
    else:
        doc["historical_model"] = {"status": "SCORED", "predicted_patients_per_year": hist["patients_per_year"],
                                   "predicted_enrollment_duration_years": hist["enrollment_duration_years"],
                                   **score(hist["patients_per_year"], acc["target_patients"], actual["enrolled"], actual["window_years"], exact=exact)}
    doc["failure_model"] = score_failure(acc.get("failure_model") or {}, registry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "planning_comparison.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    (out_dir / "planning_comparison.md").write_text(render(doc), encoding="utf-8")
    return doc


def render(doc: dict) -> str:
    a, h = doc["actual"], doc["historical_model"]
    lines = [f"# Blind planning comparison with the registry timeline ({VALIDATE_VERSION})", "",
             (f"Registry {doc['nct_id']} (study {doc['protocol_id']}). Planning report locked at {doc['planning_locked_at']}; "
              f"registry fetched at {doc['registry_fetched_at']}; order verified: {doc['order_verified']}; report marked blind: {doc['report_marked_blind']}."),
             "", "## Registry timeline", "",
             f"- Status: {a['overall_status']}" + (f" ({a['why_stopped']})" if a["why_stopped"] else ""),
             (f"- Start {a['start']} ({a['start_type']}); primary completion {a['primary_completion']} ({a['primary_completion_type']}); "
              f"window {a['window_years']:.2f} years: {a.get('window_kind')}") if a["window_years"] else "- Start or primary completion not given",
             f"- Enrolled: {a['enrolled']} ({a['enrollment_type']}) against a protocol target of {doc['target_patients']}", "",
             "## Protocol-stated accrual scenarios", ""]
    for sc in doc["protocol_scenarios"]:
        if sc["status"] == "SCORED":
            lines.append(f"- {sc['scenario']}: {sc['patients_per_year']:.1f} patients/year (stated); observed {'at least ' if sc['observed_is_lower_bound'] else ''}"
                         f"{sc['observed_rate_per_year_lower_bound']:.2f}; predicted probability of the outcome ({sc['headline']['event']}): "
                         f"{100 * sc['headline']['predicted_probability']:.1f}%")
        else:
            lines.append(f"- {sc['scenario']}: {sc['status']}")
    if not doc["protocol_scenarios"]:
        lines.append("- none")
    lines += ["", "## Historical accrual model", ""]
    if h["status"] != "SCORED":
        lines.append(f"- {h['status']}: {h['reason']}")
    else:
        q, d = h["predicted_patients_per_year"], h["predicted_enrollment_duration_years"]
        lines += [f"- Predicted: {q['median']:.1f} patients/year (80% {q['q10']:.1f}-{q['q90']:.1f}); target in {d['median']:.1f} years (80% {d['q10']:.1f}-{d['q90']:.1f})",
                  (f"- Observed: {'at least ' if h['observed_is_lower_bound'] else ''}{h['observed_rate_per_year_lower_bound']:.2f} patients/year (enrolled / window); "
                   f"percentile in the prediction {100 * h['observed_rate_percentile_in_prediction']:.0f}; inside the 80% interval: {h['inside_80_interval']}"),
                  f"- Predictive probability of enrolling at most {a['enrolled']} in the window: {100 * h['p_at_most_actual_enrollment_in_window']:.1f}%",
                  f"- Predicted probability of reaching the target of {doc['target_patients']} in the window: {100 * h['p_target_reached_in_window']:.1f}%",
                  f"- **Headline: predicted probability of the outcome ({h['headline']['event']}): {100 * h['headline']['predicted_probability']:.1f}%**",
                  ]
    f = doc.get("failure_model") or {}
    lines += ["", "## Trial outcome (failure model)", ""]
    if f.get("status") == "SCORED":
        lines.append(f"- Observed outcome: {f['observed_outcome']}; predicted probability {100 * f['predicted_probability']:.1f}% (base rate "
                     f"{100 * f['base_rate']:.1f}%); log-score gain over the base rate {f['log_score_gain_over_base_rate']:+.2f}")
    else:
        lines.append(f"- {f.get('status', 'UNRESOLVED')}: {f.get('reason', 'not in the locked report')}")
    lines += ["", "One trial is not a calibration result; calibration needs the blind validation over many held-out trials."]
    return "\n".join(lines) + "\n"
