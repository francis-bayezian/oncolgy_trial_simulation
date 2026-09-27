"""Blind comparison of the locked simulation with the trial's real registry results.

Run only after every simulation stage is locked. The registry record is read from a separate directory (never the
evidence build), and the comparison records the lock time of the predictions and the fetch time of the record, so
the order (predict, lock, then look) can be verified.

For every quantity the simulation predicted: the prediction and its source, the registry value, the error, and
whether the registry value lies in the prediction's 90% interval (when there is one). Quantities the simulation
declared UNRESOLVED are listed with the registry value, so the gaps are visible. Structural differences between
the simulated trial (this protocol version's open arms) and the registered trial (its whole history) are stated.
"""

import json
import math
import re
from pathlib import Path

import numpy as np

COMPARE_VERSION = "compare-1.0.0"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").casefold()).strip("_")


def _group_ids(groups: list[dict], arm_label: str, must_contain: str | None) -> list[str]:
    out = []
    for g in groups:
        title = g["title"].casefold()
        if arm_label.casefold() in title and (must_contain is None or must_contain.casefold() in title):
            out.append(g["id"])
    return out


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _measure(module: dict, title_words: list[str]) -> dict | None:
    for m in module.get("outcomeMeasures", []):
        t = m["title"].casefold()
        if all(w.casefold() in t for w in title_words):
            return m
    return None


def _value(measure: dict, group_id: str) -> tuple[float | None, float | None, float | None]:
    for c in measure.get("classes", []):
        for cat in c.get("categories", []):
            for x in cat["measurements"]:
                if x["groupId"] == group_id:
                    return _num(x.get("value")), _num(x.get("lowerLimit")), _num(x.get("upperLimit"))
    return None, None, None


def compare(results: dict, population_model: dict, cohort: list[dict], registry: dict, arms: list[dict], population_word: str,
            predictions_locked_at: str, registry_fetched_at: str) -> dict:
    rs = registry["resultsSection"]
    items, structural = [], []
    control = results["control_arm_id"]
    curve = results["success_curve"]
    first = next(iter(curve))
    null_row = next(r for r in curve[first] if abs(r["hr"] - 1.0) < 1e-9)

    # primary endpoint: control-arm EFS (independent of the unknown effect)
    efs = _measure(rs["outcomeMeasuresModule"], ["event-free", population_word])
    for a in arms:
        gid = _group_ids(efs["groups"], a["label"], population_word) if efs else []
        observed, lo, hi = _value(efs, gid[0]) if gid else (None, None, None)
        if a["arm_id"] == control:
            pred = null_row["efs_by_arm"][a["arm_id"]]["5y"]
            items.append({"quantity": f"5-year EFS %, {a['label']} (control)", "predicted": 100 * pred["median"],
                          "predicted_90": [100 * pred["q05"], 100 * pred["q95"]], "observed": observed, "observed_95ci": [lo, hi],
                          "abs_error": None if observed is None else abs(100 * pred["median"] - observed),
                          "observed_in_predicted_90": None if observed is None else 100 * pred["q05"] <= observed <= 100 * pred["q95"],
                          "prediction_in_observed_ci": None if lo is None else lo <= 100 * pred["median"] <= hi,
                          "source": "protocol's own control model (cure model 56%, 2-year 61%), no effect assumed for the control arm"})
        else:
            ctrl_gid = _group_ids(efs["groups"], next(x["label"] for x in arms if x["arm_id"] == control), population_word)
            c_obs = _value(efs, ctrl_gid[0])[0] if ctrl_gid else None
            implied = math.log(observed / 100) / math.log(c_obs / 100) if observed and c_obs and 0 < observed < 100 and 0 < c_obs < 100 else None
            nearest = min(curve[first], key=lambda r: abs(r["hr"] - implied)) if implied else None
            items.append({"quantity": f"5-year EFS %, {a['label']} (experimental)", "predicted": "conditional on the true effect (effect curve)",
                          "observed": observed, "observed_95ci": [lo, hi],
                          "implied_hr_vs_control": implied,
                          "predicted_efs_at_implied_hr": None if nearest is None else 100 * nearest["efs_by_arm"][a["arm_id"]]["5y"]["median"],
                          "p_success_at_implied_hr": None if nearest is None else {k: next(r for r in v if r["hr"] == nearest["hr"])["p_success"]
                                                                                 for k, v in curve.items()},
                          "source": "S_B = S_A ** HR; HR implied by the two observed 5-year EFS values"})

    # baseline characteristics (registry total row) against the source population model
    base = rs["baselineCharacteristicsModule"]
    total = next(g["id"] for g in base["groups"] if g["title"].casefold() == "total")
    counts = {}
    for m in base["measures"]:
        for c in m.get("classes", []):
            for cat in c.get("categories", []):
                for x in cat["measurements"]:
                    if x["groupId"] == total:
                        counts[(m["title"], cat.get("title"))] = float(x["value"])
    n_total = sum(v for (t, _), v in counts.items() if t.startswith("Sex"))
    sex_model = population_model["demographic:sex"]["probabilities"]
    items.append({"quantity": "share male (all registered participants)", "predicted": 100 * sex_model["male"],
                  "observed": 100 * counts.get(("Sex: Female, Male", "Male"), 0) / n_total, "source": population_model["demographic:sex"]["source"]})
    ages = np.array([c["baseline"]["demographic:age"]["value"] for c in cohort])
    age_median = next((float(x["value"]) for m in base["measures"] if m["title"] == "Age, Continuous" and m.get("paramType") == "MEDIAN"
                       for c in m.get("classes", []) for cat in c.get("categories", []) for x in cat["measurements"] if x["groupId"] == total), None)
    items.append({"quantity": "median age, years", "predicted": float(np.median(ages)), "observed": age_median,
                  "source": population_model["demographic:age"]["source"]})
    for var, title in (("demographic:race", "Race (NIH/OMB)"), ("demographic:ethnicity", "Ethnicity (NIH/OMB)")):
        m = population_model[var]
        probs = m["probabilities"] if "probabilities" in m else _marginal(m["given_sex"], sex_model)
        for (t, cat), v in counts.items():
            if t == title:
                key = next((k for k in probs if k and _norm(k) == _norm(cat)), None)
                items.append({"quantity": f"{title}: {cat} %", "predicted": None if key is None else 100 * probs[key],
                              "observed": 100 * v / n_total, "source": m["source"]})

    # participant flow and structure
    flow = rs["participantFlowModule"]
    started = {g["title"]: 0 for g in flow["groups"]}
    for per in flow["periods"]:
        for ms in per["milestones"]:
            if ms["type"] == "STARTED":
                for x in ms["achievements"]:
                    started[next(g["title"] for g in flow["groups"] if g["id"] == x["groupId"])] = int(x["numSubjects"])
    sim_enrolled = null_row["enrolled"]["median"]
    registered = sum(v for k, v in started.items() if population_word.casefold() in k.casefold())
    items.append({"quantity": f"{population_word} participants started", "predicted": sim_enrolled, "observed": registered,
                  "source": "accrual stops at the protocol's evaluable target"})
    structural.append(f"registered arms: {sorted(started)}; the simulation ran only the arms open in the protocol version compiled "
                      f"({[a['label'] for a in arms]}), so per-arm counts are not comparable")

    # unresolved endpoints: show what the registry reports
    for m in rs["outcomeMeasuresModule"].get("outcomeMeasures", []):
        if population_word.casefold() in m["title"].casefold() and "event-free" not in m["title"].casefold() and m.get("groups"):
            vals = {g["title"]: _value(m, g["id"])[0] for g in m["groups"]}
            items.append({"quantity": m["title"], "predicted": "UNRESOLVED (no source quantifies it)", "observed": vals})

    # adverse events: matched terms, pooled over the registered groups
    ae = rs["adverseEventsModule"]
    real = {}
    for kind in ("otherEvents", "seriousEvents"):
        for e in ae.get(kind, []):
            n = sum(s.get("numAffected", 0) for s in e["stats"])
            at = sum(s.get("numAtRisk", 0) for s in e["stats"])
            if at:
                real[(kind, _norm(e["term"]))] = (e["term"], n / at)
    asset = results["adverse_events_asset"][control]
    ae_rows = []
    for ev in asset["events"]:
        kind = "seriousEvents" if ev["seriousness"] == "serious" else "otherEvents"
        match = real.get((kind, _norm(ev["event"])))
        ae_rows.append({"term": ev["event"], "seriousness": ev["seriousness"], "predicted_pct": 100 * ev["rate"],
                        "observed_pct": None if match is None else 100 * match[1], "registry_term": None if match is None else match[0]})
    matched = [r for r in ae_rows if r["observed_pct"] is not None]
    mae = float(np.mean([abs(r["predicted_pct"] - r["observed_pct"]) for r in matched])) if matched else None
    top_real = sorted(((v[1], v[0], k[0]) for k, v in real.items()), reverse=True)[:15]
    return {"compare_version": COMPARE_VERSION, "predictions_locked_at": predictions_locked_at, "registry_fetched_at": registry_fetched_at,
            "order_verified": predictions_locked_at < registry_fetched_at, "items": items, "structural_differences": structural,
            "adverse_events": {"asset_signature": asset["class_signature"], "rows": ae_rows, "matched_terms": len(matched),
                               "mean_abs_error_pct_points_matched": mae,
                               "registry_top_terms": [{"term": t, "kind": k, "observed_pct": 100 * p} for p, t, k in top_real]}}


def _marginal(given_sex: dict, sex: dict) -> dict:
    out: dict[str, float] = {}
    for s, probs in given_sex.items():
        for k, p in probs.items():
            out[k] = out.get(k, 0.0) + sex.get(s, 0.0) * p
    return out


def run_compare(results_lock: Path, population_lock: Path, cohorts_lock: Path, outcomes_lock: Path, registry_file: Path,
                registry_fetched_at: str, out_dir: Path) -> dict:
    from .lock import load_locked, verify
    from .recruitment import randomization_plan
    from .studyspec import load_studyspec

    rec = verify(results_lock)
    results = load_locked(results_lock, "trial_results.json")
    model = load_locked(outcomes_lock, "outcome_model.json")
    pop = load_locked(population_lock, "population_model.json")["model"]
    spec_path = Path(json.loads((Path(results_lock) / "lock.json").read_text(encoding="utf-8"))["inputs"]["studyspec"]["path"]).parent
    spec, _ = load_studyspec(spec_path)
    first = next(p for p in sorted(Path(cohorts_lock).glob("cohort_*.jsonl")))
    with open(first, encoding="utf-8") as fh:
        cohort = [json.loads(line) for line in fh]
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    population = (model["analysis_rule"].get("population") or "").strip()
    population_word = re.sub(r"\s*\bpatients?\b", "", population, flags=re.IGNORECASE).strip() or population
    results = {**results, "control_arm_id": model["control_arm_id"], "adverse_events_asset": model["adverse_events_asset"]}
    doc = compare(results, pop, cohort, registry, randomization_plan(spec)["arms"], population_word, rec["locked_at"], registry_fetched_at)
    doc["registry"] = {"nct_id": registry["protocolSection"]["identificationModule"]["nctId"],
                       "org_study_id": registry["protocolSection"]["identificationModule"]["orgStudyIdInfo"]["id"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "comparison_report.md").write_text(_report(doc), encoding="utf-8")
    return doc


def _fmt(x) -> str:
    if isinstance(x, float):
        return f"{x:.1f}"
    if isinstance(x, dict):
        return "; ".join(f"{k}: {_fmt(v)}" for k, v in x.items())
    return str(x)


def _report(doc: dict) -> str:
    lines = [f"# Blind comparison with the registry results ({doc['compare_version']})", "",
             (f"Registry {doc['registry']['nct_id']} (study {doc['registry']['org_study_id']}). Predictions locked at "
              f"{doc['predictions_locked_at']}; registry record fetched at {doc['registry_fetched_at']}; "
              f"order verified: {doc['order_verified']}."), "",
             "| Quantity | Predicted | Observed | Agreement |", "| --- | --- | --- | --- |"]
    for it in doc["items"]:
        agree = ""
        if it.get("observed_in_predicted_90") is not None:
            agree = f"in 90% interval: {it['observed_in_predicted_90']}; prediction in registry 95% CI: {it.get('prediction_in_observed_ci')}"
        elif it.get("implied_hr_vs_control") is not None:
            agree = (f"implied HR {it['implied_hr_vs_control']:.2f}; predicted EFS there {it['predicted_efs_at_implied_hr']:.1f}; "
                     f"P(success) there {_fmt(it['p_success_at_implied_hr'])}")
        elif isinstance(it.get("predicted"), float) and isinstance(it.get("observed"), float):
            agree = f"difference {it['predicted'] - it['observed']:+.1f}"
        pred = _fmt(it["predicted"]) + (f" (90%: {it['predicted_90'][0]:.1f}-{it['predicted_90'][1]:.1f})" if it.get("predicted_90") else "")
        lines.append(f"| {it['quantity']} | {pred} | {_fmt(it['observed'])} | {agree} |")
    lines += ["", "## Structural differences", ""] + [f"- {s}" for s in doc["structural_differences"]]
    ae = doc["adverse_events"]
    lines += ["", f"## Adverse events (asset signature {ae['asset_signature']})", "",
              f"{ae['matched_terms']} predicted terms matched a registry term; mean absolute error {_fmt(ae['mean_abs_error_pct_points_matched'])} percentage points.", "",
              "| Predicted term | Predicted % | Observed % |", "| --- | ---: | ---: |"]
    lines += [f"| {r['term']} ({r['seriousness']}) | {r['predicted_pct']:.1f} | {_fmt(r['observed_pct'])} |" for r in ae["rows"]]
    lines += ["", "Most frequent registry terms: " + "; ".join(f"{t['term']} {t['observed_pct']:.1f}%" for t in ae["registry_top_terms"])]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- binary designs


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (text or "").casefold()) if len(w) > 3}


def _denominator(measure: dict, group_id: str) -> float | None:
    for d in measure.get("denoms", []):
        for c in d.get("counts", []):
            if c["groupId"] == group_id:
                return _num(c.get("value"))
    return None


def compare_binary(binary: dict, registry: dict, predictions_locked_at: str, registry_fetched_at: str) -> dict:
    """Per arm and cohort: the registry's observed primary response rate against the locked prediction."""
    rs = registry["resultsSection"]
    primaries = [m for m in rs["outcomeMeasuresModule"].get("outcomeMeasures", []) if m["type"] == "PRIMARY"]
    items = []
    for rule in binary["rules"]:
        arm_words = _words(rule["arm"])
        other_words = set().union(*[_words(r["arm"]) for r in binary["rules"] if r["arm"] != rule["arm"]]) - arm_words
        best = None
        for m in primaries:                      # the primary measure about this arm's treatment alone
            title = _words(m["title"])
            score = (len(arm_words & title) - len(other_words & title), -len(title - arm_words))
            if arm_words & title and (best is None or score > best[0]):
                best = (score, m)
        entry = {"decision_rule_id": rule["decision_rule_id"], "arm": rule["arm"], "cohort": rule.get("cohort")}
        single_arm = len({r["arm"] for r in binary["rules"]}) == 1
        if best is None and single_arm and primaries:     # one arm: its primary measure needs no treatment name
            best = ((0, 0), primaries[0])
        if best is None:
            entry["registry"] = "no registry primary measure matches this arm"
            items.append(entry)
            continue
        m = best[1]
        # responders over every response category and every group of the measure; participants over its denominators
        denoms = {x["groupId"]: _num(x.get("value")) or 0 for d in m.get("denoms", []) for x in d.get("counts", [])}
        n = sum(denoms.values())
        unit = (m.get("unitOfMeasure") or "").casefold()
        values = [(x["groupId"], _num(x.get("value")) or 0) for c in m.get("classes", []) for cat in c.get("categories", []) for x in cat["measurements"]]
        if "%" in unit or "percent" in unit:          # a percentage per group: responders = percentage x group size
            responders = sum(v / 100 * denoms.get(g, 0) for g, v in values)
        else:
            responders = sum(v for _, v in values)
        rate = responders / n if n and ("participant" in unit or "%" in unit or "percent" in unit) else None
        entry.update({"registry_measure": m["title"], "registry_groups": [g["title"] for g in m.get("groups", [])], "registry_responders": responders,
                      "registry_participants": n, "observed_rate": rate,
                      "note": "registry groups and response categories of the measure are pooled; the registry does not split the protocol's cohorts"})
        if rate is not None:
            curve = rule["exact_curve"]
            nearest = min(range(len(curve)), key=lambda k: abs(curve[k]["p"] - rate))
            sim = rule["simulated"][nearest]
            entry.update({"prediction_at_observed_rate": {"p": curve[nearest]["p"], "prob_of_interest": curve[nearest]["prob_of_interest"],
                                                          "expected_enrolled": curve[nearest]["expected_n"], "enrolled_90": [sim["enrolled"]["q05"], sim["enrolled"]["q95"]]},
                          "design_decision_at_observed": _decision(rule["rule"], round(responders), int(n))})
            for c in rule["cited_evidence"]:
                sim_c = next(s for s in rule["simulated"] if abs(s["p"] - c["rate"]) < 1e-9)
                o = sim_c["observed_rate"]
                entry.setdefault("cited_rate_predictions", []).append(
                    {"fact_id": c["fact_id"], "cited_rate": c["rate"], "predicted_observed_rate_90": [o["q05"], o["q95"]],
                     "registry_rate_in_interval": o["q05"] <= rate <= o["q95"], "prob_of_interest": c["prob_of_interest"]})
        items.append(entry)
    return {"compare_version": COMPARE_VERSION, "design": "binary decision rules", "predictions_locked_at": predictions_locked_at,
            "registry_fetched_at": registry_fetched_at, "order_verified": predictions_locked_at < registry_fetched_at, "items": items}


def _decision(rule: dict, responders: int, n: int) -> str:
    """What the protocol's rule concludes from the registry's own counts."""
    stages = rule.get("stages") or []
    if rule.get("success_if_at_least") is None:
        return f"no decision defined by the protocol (descriptive estimate): {responders} of {n} responded"
    if len(stages) > 1 and n <= stages[0]["n"] and responders <= (stages[0]["stop_if_at_most"] or -1):
        return f"stops after stage 1 ({responders} of {n} responded, stop if at most {stages[0]['stop_if_at_most']})"
    if n < (stages[-1]["n"] if stages else 0):
        return f"incomplete: {n} participants, fewer than the {stages[-1]['n']} of the final stage ({responders} responded)"
    return f"of interest ({responders} of {n})" if responders >= rule["success_if_at_least"] else f"not of interest ({responders} of {n})"


def run_compare_binary(results_lock: Path, registry_file: Path, registry_fetched_at: str, out_dir: Path) -> dict:
    from .lock import load_locked, verify

    rec = verify(results_lock)
    binary = load_locked(results_lock, "binary_results.json")
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    doc = compare_binary(binary, registry, rec["locked_at"], registry_fetched_at)
    doc["registry"] = {"nct_id": registry["protocolSection"]["identificationModule"]["nctId"],
                       "org_study_id": registry["protocolSection"]["identificationModule"]["orgStudyIdInfo"]["id"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [f"# Blind comparison with the registry results: binary decision rules ({doc['compare_version']})", "",
             (f"Registry {doc['registry']['nct_id']} (study {doc['registry']['org_study_id']}). Predictions locked at {doc['predictions_locked_at']}; "
              f"registry fetched at {doc['registry_fetched_at']}; order verified: {doc['order_verified']}."), ""]
    for it in doc["items"]:
        lines.append(f"## {it['decision_rule_id']}: {it['arm']} ({it.get('cohort')})")
        if "registry" in it:
            lines += ["", it["registry"], ""]
            continue
        rate = it["observed_rate"]
        lines += ["", (f"Registry: {it['registry_responders']:g} responders of {it['registry_participants']:g} "
                       f"({'n/a' if rate is None else f'{rate:.1%}'}) in '{it['registry_measure']}' (groups pooled: {it['registry_groups']})."),
                  f"Protocol rule applied to the registry counts: {it.get('design_decision_at_observed')}."]
        pa = it.get("prediction_at_observed_rate")
        if pa:
            interest = "not defined" if pa["prob_of_interest"] is None else f"{pa['prob_of_interest']:.3f}"
            lines.append(f"Locked prediction at the nearest grid rate {pa['p']:.2f}: P(of interest) {interest}, "
                         f"expected enrolled {pa['expected_enrolled']:.1f} (90%: {pa['enrolled_90'][0]:g}-{pa['enrolled_90'][1]:g}).")
        for c in it.get("cited_rate_predictions", []):
            lines.append(f"Prediction conditional on the rate the protocol cites ({c['fact_id']}: {c['cited_rate']:.1%}): observed rate 90% interval "
                         f"{c['predicted_observed_rate_90'][0]:.1%}-{c['predicted_observed_rate_90'][1]:.1%}; registry rate inside: "
                         f"{c['registry_rate_in_interval']}; P(of interest) {'not defined' if c['prob_of_interest'] is None else format(c['prob_of_interest'], '.3f')}.")
        lines.append("")
    (out_dir / "comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


def run_compare_unresolved(results_lock: Path, results_file: str, registry_file: Path, registry_fetched_at: str, out_dir: Path) -> dict:
    """For a trial whose primary prediction the sources could not determine: the registry's measures next to the locked
    statement of what was unresolved and why, so the gap is on record."""
    from .lock import load_locked, verify

    rec = verify(results_lock)
    results = load_locked(results_lock, results_file)
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    rs = registry.get("resultsSection", {})
    measures = []
    for m in rs.get("outcomeMeasuresModule", {}).get("outcomeMeasures", []):
        values = [(g["title"], _value(m, g["id"])[0]) for g in m.get("groups", [])]
        measures.append({"type": m["type"], "title": m["title"], "unit": m.get("unitOfMeasure"), "values": values})
    doc = {"compare_version": COMPARE_VERSION, "design": "primary prediction unresolved", "predictions_locked_at": rec["locked_at"],
           "registry_fetched_at": registry_fetched_at, "order_verified": rec["locked_at"] < registry_fetched_at,
           "locked_results": [{"rule": r.get("decision_rule_id"), "result": r.get("result", "simulated")} for r in results.get("rules", [])],
           "registry": {"nct_id": registry["protocolSection"]["identificationModule"]["nctId"],
                        "org_study_id": registry["protocolSection"]["identificationModule"]["orgStudyIdInfo"]["id"]},
           "registry_measures": measures}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [f"# Blind comparison with the registry results: primary prediction unresolved ({COMPARE_VERSION})", "",
             (f"Registry {doc['registry']['nct_id']} (study {doc['registry']['org_study_id']}). Predictions locked at {doc['predictions_locked_at']}; "
              f"registry fetched at {registry_fetched_at}; order verified: {doc['order_verified']}."), "", "## Locked simulation results", ""]
    lines += [f"- {r['rule']}: {r['result']}" for r in doc["locked_results"]] or ["- none"]
    lines += ["", "## Registry measures (not predicted)", ""]
    for m in measures:
        vals = "; ".join(f"{t}: {v}" for t, v in m["values"][:8])
        lines.append(f"- [{m['type']}] {m['title']} ({m['unit']}): {vals}")
    (out_dir / "comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc
