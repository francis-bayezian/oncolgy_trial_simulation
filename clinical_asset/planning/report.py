"""The unified trial planning report: one document per protocol, built only from locked artefacts.

Sections: population feasibility, accrual, sample size, timelines, event maturity, retention, operational risk and
the protocol assumption stress test. Every number names its source: the protocol (quoted), a locked simulation, or a
historical planning asset. When a source does not exist yet the section says PENDING (the asset is not built) or
UNRESOLVED (no source can state it); nothing is filled in by assumption. A protocol's own planning assumption is never
replaced: when historical evidence exists it is shown next to it.
"""

import json
import math
import re
from pathlib import Path

import numpy as np

from ..protocol import design_rules as dr
from . import events
from .. import assets as _assets

REPORT_VERSION = "planning-report-1.1.0"
WORLDS = 5000


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


YEARS_PER_UNIT = {"day": 1 / 365.25, "week": 7 / 365.25, "month": 1 / 12, "year": 1.0}
ACCRUAL_WORDS = re.compile(r"\b(?:enrol|enroll|accru|recruit)\w*", re.I)
SITE_COUNT = re.compile(r"\b(?:approximately|about|around|up to|a total of)?\s*(\d{1,4})\s+(?:[A-Za-z]+\s+){0,2}?(?:sites|centres|centers|institutions)\b"
                        r"(?![^.]{0,40}\bof\b)", re.I)


def accrual_durations_years(spec: dict) -> list[dict]:
    """Stated accrual durations in years: only items with a time unit whose wording is about enrolment (a screening
    window or a count of subjects is not an accrual duration)."""
    out = []
    for s in _stated(spec, "accrual_duration"):
        unit = re.sub(r"s$", "", (s["unit"] or "").strip().casefold())
        if unit in YEARS_PER_UNIT and ACCRUAL_WORDS.search(s["wording"] or ""):
            out.append({**s, "years": s["value"] * YEARS_PER_UNIT[unit]})
    return out


def _protocol_text(spec_lock: Path) -> str | None:
    """The locked protocol's text, after checking the PDF still matches the hash in the StudySpec lock."""
    from ..protocol.ingest import extract, sha256

    lock = json.loads((Path(spec_lock) / "lock.json").read_text(encoding="utf-8"))
    from ..trial.lock import resolve

    pdf = (lock.get("inputs") or {}).get("protocol_pdf") or {}
    path = resolve(pdf["path"]) if pdf.get("path") else None   # a protocol renamed since the lock (alias manifest)
    if path is None or not path.exists() or sha256(path) != pdf.get("sha256"):
        return None
    return " ".join(extract(path).full_text().split())


def stated_site_count(text: str | None) -> dict:
    """The number of sites the protocol plans, as stated ('Approximately 100 investigative sites ... are planned'):
    the largest stated count, with its quote. Deterministic; UNRESOLVED when the protocol states none."""
    hits = [(int(m.group(1)), m.group(0).strip()) for m in SITE_COUNT.finditer(text or "") if int(m.group(1)) >= 2]
    if not hits:
        return {"status": "NOT_STATED_AVERAGED", "reason": "the protocol states no number of sites: the historical model averages over same-phase trials' site counts"}
    n, quote = max(hits)
    return {"status": "RESOLVED", "value": n, "quote": quote, "source": "protocol (quoted)"}


def sponsor_class(spec: dict) -> dict:
    """The registry sponsor class of the protocol's sponsor, when its name carries a company legal form (reference
    data: sponsor_industry_forms) or an academic / cooperative-group marker (OTHER); otherwise the models average over
    sponsor classes."""
    from ..reference import vocabulary

    name = " ".join((_q(spec["metadata"].get("sponsor")) or "").split())
    forms = vocabulary().get("sponsor_industry_forms", [])
    if name and any(re.search(rf"(?:^|[\s,]){re.escape(f)}(?:$|[\s,.])", name + " ", re.I) for f in forms):
        return {"status": "RESOLVED", "value": "INDUSTRY", "quote": name, "source": "protocol (quoted): company legal form"}
    words = vocabulary().get("sponsor_nonindustry_words", [])
    if name and any(w in name.casefold() for w in words):
        return {"status": "RESOLVED", "value": "OTHER", "quote": name, "source": "protocol (quoted): academic, cooperative-group or public sponsor"}
    return {"status": "NOT_STATED_AVERAGED", "reason": (f"sponsor '{name}' has no company legal form or academic marker" if name else "no sponsor stated")
            + ": the models average over sponsor classes"}


def _stated(spec: dict, quantity: str) -> list[dict]:
    return [{"value": s["value"], "unit": s.get("unit"), "wording": _q(s.get("evidence"))}
            for s in spec.get("sample_size") or [] if s["quantity"] == quantity and s.get("value") is not None]


def build(spec_lock: Path, cohorts_lock: Path, eligibility_lock: Path, results_lock: Path | None, outcomes_lock: Path | None,
          out_dir: Path, blind: bool, accrual_asset: Path | None = None, seed: int = 20260927) -> dict:
    from ..trial.lock import load_locked, verify
    from ..trial.studyspec import load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    recruitment = load_locked(cohorts_lock, "recruitment_summary.json")
    eligibility = load_locked(eligibility_lock, "eligibility_summary.json")["summary"]
    results = _load_results(results_lock) if results_lock else None
    outcome = load_locked(outcomes_lock, "outcome_model.json") if outcomes_lock else None
    rng = np.random.default_rng(seed)
    plan = recruitment["accrual_plan"]
    n_max = plan["target"]["patients"] if plan.get("target") else None
    durations = [round(s["years"], 3) for s in accrual_durations_years(spec) if s["years"] < 100]
    deadlines = tuple(sorted(set(durations))) or (1.0, 2.0, 3.0, 5.0)
    text = _protocol_text(spec_lock)
    stated = {"site_count": stated_site_count(text) if text else {"status": "UNRESOLVED", "reason": "locked protocol PDF not available"},
              "sponsor_class": sponsor_class(spec)}

    report = {"report_version": REPORT_VERSION, "protocol_id": _q(spec["metadata"].get("protocol_id")) or spec_lock.parent.name,
              "blind": blind, "note": ("planning predictions locked before any registry timeline was read" if blind else
                                       "RETROSPECTIVE: this trial's registry results were already seen; not a blind prediction"),
              "inputs": {"studyspec": spec_record["files"]["studyspec.json"], "cohorts": verify(cohorts_lock)["files"],
                         "eligibility": verify(eligibility_lock)["files"]}}

    # population feasibility
    report["population_feasibility"] = {
        "eligible_fraction_bounds": [eligibility["proven_eligible_share"], eligibility["not_proven_ineligible_share"]],
        "criteria_that_cannot_be_checked": list((eligibility.get("criteria_resolved_by_calibration") or eligibility.get("blocking_unknowns") or {}))[:20],
        **_screening_funnel(spec, eligibility)}

    # accrual (stopping at the protocol's evaluable target when the analysis rule states one)
    stop_rule = (outcome or {}).get("analysis_rule") if (outcome or {}).get("analysis_rule", {}).get("evaluable_target") else None
    scenarios = []
    for sc in plan["scenarios"]:
        if not sc.get("rate_per_year"):
            scenarios.append({"scenario": sc["scenario"], "status": "UNRESOLVED", "reason": "the protocol states no accrual rate"})
            continue
        t = events.timelines(n_max, np.full(WORLDS, sc["rate_per_year"]), rng, analysis_rule=stop_rule, deadlines_years=deadlines)
        scenarios.append({"scenario": sc["scenario"], "source": "protocol (quoted)", "wording": sc.get("evidence"),
                          "patients_per_year": sc["rate_per_year"], "patients_per_month": sc["rate_per_year"] / 12,
                          "enrolled": t["enrolled"], "enrollment_duration_years": t["last_patient_in_years"],
                          "p_enrollment_complete_by": t["p_enrollment_complete_by"],
                          "note": ("Poisson arrivals at the stated rate" + ("; accrual stops at the protocol's evaluable target" if stop_rule else "")
                                   + "; site activation and rate uncertainty are not included")})
    report["accrual"] = {"target_patients": n_max, "target_source": (plan.get("target") or {}).get("source"),
                         "stated_accrual_durations_years": durations, "protocol_scenarios": scenarios,
                         "excluded_rates": plan.get("excluded_rates", []),
                         "stated_operational": stated,
                         "historical_model": _historical(accrual_asset, spec, n_max, deadlines, rng, stated=stated),
                         "failure_model": _failure(accrual_asset, spec, n_max, stated=stated)}

    # sample size and decision timing
    report["sample_size"] = {"maximum": n_max, "evaluable_targets": [s["value"] for s in _stated(spec, "evaluable_target")],
                             "decision_rules": _rules_sample_size(results)}

    # timelines, events and retention for a time-to-event protocol with a locked outcome model
    if outcome and outcome.get("control_efs", {}).get("status") == "RESOLVED":
        report["timelines"] = _tte_timelines(spec, outcome, plan, n_max, deadlines, rng)
        ltf = outcome.get("loss_to_follow_up") or {}
        report["retention"] = {"loss_to_follow_up_per_year": ltf.get("annual_probability"), "source": "protocol (quoted)" if ltf.get("status") == "RESOLVED" else None,
                               "wording": ltf.get("wording"), "discontinuation_before_endpoint": _registry_retention(spec)}
    else:
        h = report["accrual"].get("historical_model") or {}
        hist = [{"scenario": "historical model (headline)", "enrollment_duration_years": h["enrollment_duration_years"]}]             if h.get("status") == "RESOLVED" and h.get("enrollment_duration_years") else []
        report["timelines"] = _simple_timelines(hist + scenarios, spec)
        report["retention"] = {"discontinuation_before_endpoint": _registry_retention(spec)}

    report["operational_risk"] = _risk(report)
    report["assumption_stress_test"] = _stress(spec, results, report)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "planning_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "planning_report.md").write_text(render(report), encoding="utf-8")
    return report


def _pct(q: dict) -> str:
    """The five predictive percentiles of a summary (older summaries: median and 80% limits)."""
    from ..trial.predictive import text

    return text(q["percentiles"]) if q.get("percentiles") else f"{q['median']:.1f} (80% {q['q10']:.1f}-{q['q90']:.1f})"


def _registry_retention(spec: dict) -> dict:
    """Shares of starters who leave early, from the registry participant flow of the protocol's disease family and
    phase (the evidence the patient journey uses): withdrawal, adverse-event discontinuation, death."""
    from ..trial import journey_evidence as je
    from ..trial.population import protocol_query

    try:
        family = protocol_query(spec).disease_family
    except Exception:  # noqa: BLE001
        family = None
    phase = je.registry_phase(spec)
    out = {"status": "RESOLVED"}
    for key, fn in (("withdrawal", je.withdrawal_probability), ("adverse_event", je.ae_discontinuation_probability), ("death", je.death_probability)):
        v = fn(family, phase)
        out[key] = {"value": v["value"], "source": v["source"]}
    return out


def _screening_funnel(spec: dict, eligibility: dict) -> dict:
    """Screen failure and patients to screen from the eligibility stage, whose unanswerable criteria are calibrated to
    the registry screen pass rate (eligibility-2.0.0); an older eligibility summary gives only bounds."""
    share = eligibility.get("eligible_share")
    if share is None or eligibility.get("status_counts", {}).get("UNDETERMINED"):
        return {"screen_failure": {"status": "UNRESOLVED", "reason": "eligibility has undetermined patients (eligibility-1.x)"},
                "patients_to_screen": {"status": "UNRESOLVED", "reason": "the eligible fraction is only bounded"}}
    target = max((x["value"] for x in spec.get("sample_size") or [] if x.get("quantity") in ("maximum_accrual", "target_accrual") and x.get("value")),
                 default=None) or max((x["value"] for x in spec.get("sample_size") or [] if x.get("quantity") == "evaluable_target" and x.get("value")),
                                      default=None)
    src = (eligibility.get("unknown_resolution") or {}).get("screen_pass_rate", {}).get("source") or "decided criteria only"
    return {"screen_failure": {"status": "RESOLVED", "value": round(1 - share, 4), "source": f"eligibility stage ({src})"},
            "patients_to_screen": ({"status": "RESOLVED", "value": math.ceil(target / share), "target": target} if target and share
                                   else {"status": "RESOLVED", "value": None, "reason": "no stated target accrual" if share else "no eligible patient"})}


def _load_results(lock_dir: Path) -> dict | None:
    from ..trial.lock import load_locked

    for name in ("binary_results.json", "trial_results.json", "escalation_results.json", "continuous_results.json"):
        if (Path(lock_dir) / name).exists():
            return {"file": name, **load_locked(lock_dir, name)}
    return None


ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}


def protocol_features(spec: dict, n_max: int | None, family_map_file: Path, family_model=None) -> dict:
    """The planning features of a protocol, from its locked StudySpec."""
    import re

    from ..trial.population import age_limits

    meta = spec["metadata"]
    phase_text = (_q(meta.get("phase")) or "").casefold()
    phases = sorted({f"PHASE{ROMAN.get(x, x)}" for x in re.findall(r"\b(iv|iii|ii|i|[1-4])\b", phase_text.replace("/", " "))})
    def year_of(text: str) -> int | None:
        m = re.search(r"(?:19|20)\d{2}", text) or re.search(r"/(\d{2})\s*$", text)     # a four-digit year first
        return (int(m.group(0)) if len(m.group(0)) == 4 else 2000 + int(m.group(1))) if m else None

    # start year: the activation date; else the earliest amendment date (a revised protocol's version date is its latest
    # amendment, years after the trial opened); else the version date
    year = year_of(_q(meta.get("activation_date")) or "")
    if year is None:
        amended = [y for y in (year_of(_q(a.get("date")) or "") for a in spec.get("amendment_history") or []) if y]
        version = year_of(_q(meta.get("version_date")) or "")
        year = min(amended + ([version] if version else [])) if amended or version else None
    hi = age_limits(spec)[1]
    from .operational import condition_family

    condition = " ".join((_q(meta.get("condition")) or "").split())
    family, disease = condition_family(condition, family_model)
    return {"phase": "+".join(phases) or "unknown", "randomized": spec["design"].get("type") in {"parallel", "factorial", "crossover"} and len(spec["arms"]) > 1,
            "pediatric": hi is not None and hi <= 22, "start_year": year, "enrolled": n_max, "disease_family": family,
            "matched_disease": disease, "condition": condition, "listed_sites": None, "site_count": None,
            "arms": len(spec["arms"]), "sponsor_class": None}


def _historical(asset: Path | None, spec: dict, n_max: int | None, deadlines: tuple = (), rng=None, draws: int = 8000,
                stated: dict | None = None) -> dict:
    """The historical accrual model's prediction for this protocol, next to (never instead of) the protocol's own rate."""
    if asset is None or not (Path(asset) / "accrual_model.json").exists():
        return {"status": "PENDING", "reason": "historical accrual asset not built yet"}
    import pyarrow.parquet as pq

    from .accrual import predict

    model = json.loads((Path(asset) / "accrual_model.json").read_text(encoding="utf-8"))
    feats = protocol_features(spec, n_max, _assets.family_map())
    hist = [r for r in pq.read_table(Path(asset) / "study_level_rates.parquet").to_pylist() if r["quality"] != "ACCRUAL_UNUSABLE"]
    same_phase = [r for r in hist if r["phase"] == feats["phase"]] or hist
    rng = rng or np.random.default_rng(0)
    site = (stated or {}).get("site_count") or {}
    if site.get("status") == "RESOLVED":
        picks = np.full(200, site["value"])
        site_note = f"protocol (quoted): '{site['quote']}'"
    else:
        sites = np.array([r.get("site_count") or r["listed_sites"] or 1 for r in same_phase])
        picks = rng.choice(sites, size=200)           # SITE_COUNT_UNKNOWN: average over same-phase trials' site counts
        site_note = "SITE_COUNT_UNKNOWN: averaged over the site counts of historical trials of the same phase"
    log_rate = np.concatenate([predict(model, {**feats, "listed_sites": int(k)}, draws=draws // 200, seed=int(i))["log_rate"]
                               for i, k in enumerate(picks)])
    per_month = np.exp(log_rate)
    months = rng.gamma(shape=n_max, scale=1.0 / per_month) if n_max else None
    def q(v):
        from ..trial.predictive import from_draws

        return {"median": float(np.median(v)), "q10": float(np.quantile(v, 0.1)), "q25": float(np.quantile(v, 0.25)),
                "q75": float(np.quantile(v, 0.75)), "q90": float(np.quantile(v, 0.9)), "percentiles": from_draws(v)}
    version = model["manifest"].get("operational_version") or model["manifest"].get("accrual_version")
    source = (f"historical accrual model {version} (completed and terminated non-holdout trials)" if model["manifest"].get("operational_version")
              else f"historical accrual model {version} (completed non-holdout trials)")
    return {"status": "RESOLVED", "source": source, "features": feats,
            "site_count": site_note,
            "patients_per_month": q(per_month), "patients_per_year": q(per_month * 12),
            "enrollment_duration_years": q(months / 12) if months is not None else None,
            "p_enrollment_complete_by": {f"{d:g}y": float(np.mean(months / 12 <= d)) for d in deadlines} if months is not None else {},
            "calibration": model["manifest"].get("cross_validation") or model["manifest"]["rate_model"]["cross_validation"], "family_known": feats["disease_family"] in model["families"]}


def _failure(asset: Path | None, spec: dict, n_max: int | None, stated: dict | None = None) -> dict:
    """P(the trial is withdrawn / terminated for poor accrual / terminated otherwise / completes), from the operational
    asset's failure model. The sponsor class is read from the sponsor's name when it carries a company legal form;
    otherwise the prediction is averaged over the sponsor classes of historical trials of the same phase (SPONSOR_CLASS_UNKNOWN)."""
    if asset is None or not (Path(asset) / "failure_model.json").exists():
        return {"status": "PENDING", "reason": "no failure model in the operational asset"}
    import pyarrow.parquet as pq

    from .operational import OUTCOMES, predict_failure

    model = json.loads((Path(asset) / "failure_model.json").read_text(encoding="utf-8"))
    manifest = json.loads((Path(asset) / "manifest.json").read_text(encoding="utf-8"))
    feats = protocol_features(spec, n_max, _assets.family_map())
    hist = pq.read_table(Path(asset) / "trial_outcomes.parquet", columns=["phase", "sponsor_class"]).to_pylist()
    sp = (stated or {}).get("sponsor_class") or {}
    if sp.get("status") == "RESOLVED":
        classes, weights = [sp["value"]], np.array([1.0])
        sponsor_note = f"{sp['value']} ({sp['source']}: '{sp['quote']}')"
    else:
        same = [r["sponsor_class"] for r in hist if r["phase"] == feats["phase"]] or [r["sponsor_class"] for r in hist]
        classes = sorted(set(same))
        weights = np.array([same.count(c) for c in classes], dtype=float) / len(same)
        sponsor_note = "SPONSOR_CLASS_UNKNOWN: averaged over the sponsor classes of historical trials of the same phase"
    probs = predict_failure(model, [{**feats, "sponsor_class": c} for c in classes])
    p = dict(zip(OUTCOMES, (weights @ probs).tolist(), strict=True))
    cv = manifest["failure_model"]["cross_validation"]
    return {"status": "RESOLVED", "source": f"operational asset {manifest.get('operational_version')} failure model",
            "features": {k: feats[k] for k in ("phase", "randomized", "pediatric", "start_year", "arms", "disease_family")},
            "sponsor_class": sponsor_note,
            "probabilities": p, "p_accrual_failure": p["withdrawn"] + p["terminated_accrual"],
            "base_rates": cv["base_rates"], "calibration": {k: cv[k] for k in ("log_loss", "base_rate_log_loss", "accrual_failure_auc", "accrual_failure_reliability")}}


def _rules_sample_size(results: dict | None) -> list[dict]:
    if not results or results["file"] != "binary_results.json":
        return []
    out = []
    for r in results["rules"]:
        rule = {"stages": r["rule"]["stages"], "success_if_at_least": r["rule"]["success_if_at_least"]}
        points = {"p0": r["rule"].get("p0"), "p1": r["rule"].get("p1")}
        points.update({f"cited {c['fact_id']}": c["rate"] for c in r.get("cited_evidence", [])})
        rows = {}
        for label, p in points.items():
            if p is None:
                continue
            rows[label] = {"true_rate": p, "expected_n": dr.expected_n(rule, p), "p_early_stop": dr.prob_early_stop(rule, p)}
        out.append({"rule": r["decision_rule_id"], "arm": r["arm"], "cohort": r.get("cohort"), "maximum_n": r["rule"]["stages"][-1]["n"],
                    "stage_1_n": r["rule"]["stages"][0]["n"] if len(r["rule"]["stages"]) > 1 else None, "at": rows})
    return out


def _tte_timelines(spec: dict, outcome: dict, plan: dict, n_max: int, deadlines: tuple, rng) -> dict:
    targets = tuple(int(s["value"]) for s in _stated(spec, "full_information_events"))
    rule = outcome.get("analysis_rule") or {}
    per = {}
    for sc in plan["scenarios"]:
        if not sc.get("rate_per_year"):
            continue
        rates = np.full(WORLDS // 5, sc["rate_per_year"])
        per[sc["scenario"]] = {}
        for label, hr in [("no effect (HR 1)", 1.0)] + [(f"design alternative HR {a['hr']:.3f}", a["hr"]) for a in outcome["effect"]["design_alternatives"][:1]]:
            per[sc["scenario"]][label] = events.timelines(
                n_max, rates, rng, outcome=outcome["control_efs"], hr=hr, event_targets=targets, analysis_rule=rule,
                loss_rate_per_year=(outcome.get("loss_to_follow_up") or {}).get("rate_per_year") or 0.0,
                off_study_days=(outcome.get("off_study_limit") or {}).get("days"), deadlines_years=deadlines + (10.0,))
    return {"event_targets": {"values": list(targets), "source": "protocol (quoted)"}, "analysis_rule": rule, "by_scenario": per,
            "note": ("event timing depends on the unknown true effect: shown under no effect and under the protocol's design alternative; "
                     "all times are years from first patient in")}


ASSESSMENT_LAG_MONTHS = 6.0


def _assessment_lag(spec: dict) -> dict:
    """Months from a patient's entry to the primary assessment: a time point stated in the primary endpoint ('at 3
    months'), else the planned treatment (cycle length x maximum cycles), else ASSESSMENT_LAG_MONTHS (assumption A20)."""
    from ..trial.outcomes import _months
    from ..trial.visits import cycle_length, max_cycles

    primary = next((e for e in spec.get("endpoints") or [] if e.get("role") == "primary"), None)
    m = _months(_q((primary or {}).get("name")) or "")
    if m:
        return {"months": m, "source": "primary endpoint time point (protocol)"}
    try:
        cyc, mx = cycle_length(spec).get("value"), max_cycles(spec).get("value")
    except Exception:  # noqa: BLE001
        cyc = mx = None
    if cyc and mx:
        return {"months": cyc * mx / 30.44, "source": "planned treatment: cycle length x maximum cycles (protocol)"}
    return {"months": ASSESSMENT_LAG_MONTHS, "source": "assumption A20: primary assessment 6 months after entry"}


def _simple_timelines(scenarios: list[dict], spec: dict) -> dict:
    """Last patient in per scenario; the primary analysis follows at the assessment lag; study completion at the
    off-study limit, else the follow-up the endpoint stage uses."""
    from ..trial.endpoints import follow_up_years
    from ..trial.outcomes import off_study_limit

    lag = _assessment_lag(spec)
    lpi = {s["scenario"]: s.get("enrollment_duration_years", {"status": s.get("status"), "reason": s.get("reason")}) for s in scenarios}
    shift = lambda q, years: {k: (v + years if isinstance(v, (int, float)) else v) for k, v in q.items() if k != "percentiles"}  # noqa: E731
    off = off_study_limit(spec)
    fu_years = (off["days"] / 365.25) if off and off.get("days") else follow_up_years(spec)
    return {"last_patient_in": lpi,
            "primary_analysis": {"years_after_start": {k: shift(v, lag["months"] / 12) for k, v in lpi.items() if "median" in v},
                                 "assessment_lag_months": round(lag["months"], 2), "source": lag["source"]},
            "study_completion": {"years_after_start": {k: shift(v, fu_years) for k, v in lpi.items() if "median" in v},
                                 "follow_up_years": round(fu_years, 2),
                                 "source": "off-study limit (protocol)" if off and off.get("days") else "endpoint follow-up (protocol, else 5 years)"}}


def _risk(report: dict) -> dict:
    """Operational risk. The headline is the historical (evidence) model; a protocol scenario is conditional on the
    protocol's own accrual assumption, which is flagged when it lies outside the historical 80% range (lesson L024:
    a stated 124/year, 12x the historical median, had made P(enrolment complete) 1.0 the only timed headline)."""
    risk = {}
    h = report["accrual"].get("historical_model") or {}
    if h.get("status") == "RESOLVED":
        if h.get("p_enrollment_complete_by"):
            risk["p_enrollment_complete_by (historical model, headline)"] = h["p_enrollment_complete_by"]
        if h.get("enrollment_duration_years"):
            risk["enrollment_duration_years (historical model, headline)"] = {k: (round(v, 2) if isinstance(v, (int, float)) else v) for k, v in h["enrollment_duration_years"].items()}
        py = h.get("patients_per_year") or {}
        outside = [{"scenario": s["scenario"], "patients_per_year": s["patients_per_year"],
                    "vs_historical_median": round(s["patients_per_year"] / py["median"], 2),
                    "direction": "optimistic" if s["patients_per_year"] > py["q90"] else "pessimistic"}
                   for s in report["accrual"]["protocol_scenarios"] if s.get("patients_per_year") and py.get("median")
                   and not py["q10"] <= s["patients_per_year"] <= py["q90"]]
        if outside:
            risk["protocol_accrual_assumption_outside_history"] = outside
    for s in report["accrual"]["protocol_scenarios"]:
        if s.get("p_enrollment_complete_by"):
            risk[f"p_enrollment_complete_by ({s['scenario']}, conditional on the protocol's assumption)"] = s["p_enrollment_complete_by"]
    for name, per in (report.get("timelines", {}).get("by_scenario") or {}).items():
        for label, t in per.items():
            if "p_primary_analysis_by" in t:
                risk[f"p_primary_analysis_by ({name}, {label})"] = t["p_primary_analysis_by"]
            for k, e in (t.get("event_maturity") or {}).items():
                risk[f"p_{k}_events_by ({name}, {label})"] = e["p_reached_by"]
    return risk or {"status": "UNRESOLVED", "reason": "no timed quantity could be simulated"}


def _stress(spec: dict, results: dict | None, report: dict) -> list[dict]:
    rows = []
    for s in report["accrual"]["protocol_scenarios"]:
        if s.get("patients_per_year"):
            h = report["accrual"]["historical_model"]
            if h.get("status") == "RESOLVED":
                py = h["patients_per_year"]
                where = "optimistic" if s["patients_per_year"] > py["q90"] else "pessimistic" if s["patients_per_year"] < py["q10"] else "plausible"
                rows.append({"assumption": f"accrual {s['patients_per_year']:g} patients/year", "protocol": s.get("wording"),
                             "evidence_estimate": {"status": "RESOLVED", "reason": f"historical /year: {_pct(py)}"},
                             "status": f"{where} (protocol/historical median {s['patients_per_year'] / py['median']:.2f}x)"})
            else:
                rows.append({"assumption": f"accrual {s['patients_per_year']:g} patients/year", "protocol": s.get("wording"),
                             "evidence_estimate": h, "status": "PENDING"})
    if results and results["file"] == "binary_results.json":
        for r in results["rules"]:
            for c in r.get("cited_evidence", []):
                ci = c.get("true_rate_90_from_cited_count")
                rows.append({"assumption": f"response rate {c['rate']:.0%} cited for {r['arm']}", "protocol": c["fact_id"],
                             "evidence_estimate": ({"status": "CITED_COUNT", "reason": f"{c['cited_count']:g}/{c['cited_n']:g}: true rate 90% {ci[0]:.0%}-{ci[1]:.0%}"}
                                                   if ci else {"status": "CITED_RATE_ONLY", "reason": "the cited rate states no count"}),
                             "status": "small sample: a conditional scenario, not a prediction" if c.get("small_sample") else "cited"})
    return rows


def render(r: dict) -> str:
    L = [f"# Trial planning report: {r['protocol_id']} ({r['report_version']})", "", f"**{r['note']}**", "", "## Population feasibility", ""]
    pf = r["population_feasibility"]
    sf, ps = pf["screen_failure"], pf["patients_to_screen"]
    L.append(f"- Eligible share of the screened population: {pf['eligible_fraction_bounds'][0]:.0%}.")
    L.append(f"- Screen failure: " + (f"{sf['value']:.0%} ({sf['source']})" if sf.get("value") is not None else f"{sf['status']} ({sf.get('reason')})")
             + "; patients to screen: " + (f"{ps['value']} for {ps.get('target')} enrolled" if ps.get("value") else f"{ps['status']} ({ps.get('reason')})") + ".")
    a = r["accrual"]
    stated = f"{a['stated_accrual_durations_years']} years" if a["stated_accrual_durations_years"] else "none stated"
    L += ["", "## Accrual", "", f"- Target: {a['target_patients']} patients ({a['target_source']}). Accrual durations in the protocol: {stated}."]
    for s in a["protocol_scenarios"]:
        if s.get("status") == "UNRESOLVED":
            L.append(f"- {s['scenario']}: UNRESOLVED ({s['reason']}).")
            continue
        d = s["enrollment_duration_years"]
        L.append(f"- {s['scenario']} ({s['patients_per_month']:.1f}/month, protocol): {s['enrolled']['median']:.0f} enrolled over {d['median']:.1f} years {_pct(d)}; "
                 f"P(complete by) {', '.join(f'{k}: {v:.0%}' for k, v in s['p_enrollment_complete_by'].items())}.")
    h = a["historical_model"]
    if h.get("status") == "RESOLVED":
        L.append(f"- Historical accrual model ({h['features']['disease_family']}, {h['features']['phase']}; matched '{h['features']['matched_disease']}'; "
                 f"{h['site_count']}): patients/year {_pct(h['patients_per_year'])}"
                 + (f"; enrollment of {a['target_patients']} in years {_pct(h['enrollment_duration_years'])}" if h.get("enrollment_duration_years") else "")
                 + (f"; P(complete by) {', '.join(f'{k}: {v:.0%}' for k, v in h['p_enrollment_complete_by'].items())}" if h.get("p_enrollment_complete_by") else "") + ".")
    else:
        L.append(f"- Historical accrual model: {h['status']} ({h['reason']}).")
    ss = r["sample_size"]
    L += ["", "## Sample size", "", f"- Maximum N {ss['maximum']}; evaluable targets {ss['evaluable_targets']}."]
    for rule in ss["decision_rules"]:
        cohort = f" ({rule['cohort'][:40]})" if rule["cohort"] else ""
        detail = "; ".join(f"{k} (p={v['true_rate']:.2f}): E[N] {v['expected_n']:.1f}, P(early stop) {v['p_early_stop']:.0%}" for k, v in rule["at"].items())
        L.append(f"- {rule['rule']} {rule['arm'][:50]}{cohort}: max {rule['maximum_n']}" + (f", stage 1 {rule['stage_1_n']}" if rule["stage_1_n"] else "")
                 + (f"; {detail}" if detail else "; single stage, no early stop (descriptive estimate)"))
    t = r["timelines"]
    L += ["", "## Timelines (years from first patient in)", ""]
    if "by_scenario" in t:
        L.append(f"- Event targets (protocol): {t['event_targets']['values']}. {t['note']}.")
        for name, per in t["by_scenario"].items():
            for label, x in per.items():
                parts = [f"last patient in {x['last_patient_in_years']['median']:.1f}"]
                if "primary_analysis_years" in x:
                    pa = x["primary_analysis_years"]
                    parts.append(f"primary analysis {pa['median']:.1f} {_pct(pa)}")
                for k, e in (x.get("event_maturity") or {}).items():
                    parts.append(f"{k} events {e.get('median', float('nan')):.1f}" + (f" {_pct(e)}" if "q10" in e else "")
                                 + f", ever reached {e['p_reached_ever']:.0%}")
                if "study_completion_years" in x:
                    parts.append(f"study completion (off-study limit) {x['study_completion_years']['median']:.1f}")
                L.append(f"- {name}, {label}: " + "; ".join(parts) + ".")
    else:
        for k, v in t.items():
            L.append(f"- {k}: {json.dumps(v)[:200]}")
    L += ["", "## Retention", "", f"- {json.dumps(r['retention'])[:300]}", "", "## Operational risk", ""]
    fm = r["accrual"].get("failure_model") or {}
    if fm.get("status") == "RESOLVED":
        pr = fm["probabilities"]
        L.append(f"- Trial outcome (historical failure model; {fm['sponsor_class']}): P(withdrawn) {pr['withdrawn']:.0%}, P(terminated for poor accrual) "
                 f"{pr['terminated_accrual']:.0%}, P(terminated, other reason) {pr['terminated_other']:.0%}, P(completed) {pr['completed']:.0%}. "
                 f"Base rates: accrual failure {fm['base_rates']['withdrawn'] + fm['base_rates']['terminated_accrual']:.0%}; model AUC for accrual failure "
                 f"{fm['calibration']['accrual_failure_auc']:.2f}.")
    elif fm:
        L.append(f"- Trial outcome: {fm['status']} ({fm['reason']}).")
    L += [f"- {k}: {json.dumps(v)}" for k, v in (r["operational_risk"].items() if isinstance(r["operational_risk"], dict) else [])]
    L += ["", "## Protocol assumption stress test", "", "| assumption | evidence estimate | status |", "| --- | --- | --- |"]
    L += [f"| {row['assumption']} | {row['evidence_estimate'].get('status')}: {row['evidence_estimate'].get('reason', '')} | {row['status']} |" for row in r["assumption_stress_test"]]
    return "\n".join(L) + "\n"
