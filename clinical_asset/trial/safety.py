"""Safety results: simulated adverse-event counts per arm, for any design, from the locked outcome model.

Sources, in the locked outcome model:

* protocol: adverse-event incidences the protocol states (verified facts), a point rate;
* asset: the Simulation Parameter Asset V2 toxicity rates for the treatment-class signature nearest to the arm's
  regimen, a population rate with its 95% interval.

Each simulated trial draws each event's true rate (asset: logit-normal matched to the asset's 95% interval; protocol:
the stated rate) and then the number of the arm's enrolled patients affected (binomial). The rate uncertainty is
stored with the prediction so the count distribution can be evaluated at any number at risk (a registry may report
fewer patients at risk than the protocol planned to enroll).
"""

import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

SAFETY_VERSION = "safety-1.0.0"
COMPARE_SAFETY_VERSION = "safety-compare-1.1.0"
Z975 = stats.norm.ppf(0.975)


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


def rate_distribution(event: dict) -> dict:
    """Logit-normal rate distribution of one event (point mass when no interval is given)."""
    if event.get("q025") is None or event.get("q975") is None:
        return {"logit_mu": _logit(event["rate"]), "logit_sigma": 0.0}
    return {"logit_mu": _logit(event["rate"]), "logit_sigma": (_logit(event["q975"]) - _logit(event["q025"])) / (2 * Z975)}


def draw_rates(dist: dict, rng: np.random.Generator, size: int) -> np.ndarray:
    return 1 / (1 + np.exp(-rng.normal(dist["logit_mu"], dist["logit_sigma"], size)))


def count_distribution(dist: dict, n: int, nodes: int = 400) -> dict:
    """Predictive distribution of the number of n patients affected: mixture of binomials over the rate, integrated at
    equally weighted quantile midpoints of the rate distribution (deterministic)."""
    z = stats.norm.ppf((np.arange(nodes) + 0.5) / nodes) if dist["logit_sigma"] > 0 else np.zeros(1)
    p = 1 / (1 + np.exp(-(dist["logit_mu"] + dist["logit_sigma"] * z)))
    pmf = stats.binom.pmf(np.arange(n + 1)[None, :], n, p[:, None]).mean(axis=0)
    cdf = np.cumsum(pmf)
    return {"pmf": pmf, "cdf": cdf, "q05": int(np.searchsorted(cdf, 0.05)), "median": int(np.searchsorted(cdf, 0.5)),
            "q95": int(np.searchsorted(cdf, 0.95))}


def _protocol_rate(value: float) -> float | None:
    if value is None:
        return None
    return value / 100 if value > 1 else value


def arm_events(model: dict, arm_id: str) -> list[dict]:
    asset = model["adverse_events_asset"].get(arm_id) or {}
    out = [{"term": e["event"], "seriousness": e["seriousness"], "source": f"asset:{asset.get('class_signature')}",
            **rate_distribution(e), "rate_median": e["rate"]} for e in asset.get("events", [])]
    for t in model.get("toxicities_protocol", []):
        if t["applies_to"] != "all_arms" and t["arm_id"] != arm_id:
            continue
        r = _protocol_rate(t["rate"])
        if r is not None:
            out.append({"term": t["event"], "seriousness": "grade " + str(t.get("grade") or "not stated"), "source": f"protocol:{t['fact_id']}",
                        "logit_mu": _logit(r), "logit_sigma": 0.0, "rate_median": r})
    return out


def run_safety(outcomes_lock: Path, cohorts_lock: Path, out_dir: Path, replicates: int = 2000, seed: int = 20260927,
               safety_asset: Path | None = None, class_map_file: Path = Path("data/spa_work/drug_classes.json"),
               family_map_file: Path | None = None) -> dict:
    from .. import assets
    from .lock import load_locked, verify

    family_map_file = family_map_file or assets.family_map()                                              # asset profile

    model = load_locked(outcomes_lock, "outcome_model.json")
    verify(cohorts_lock)
    v3 = None
    if safety_asset is not None:
        from ..safety3 import load as load_v3
        from .studyspec import load_studyspec

        from .lock import resolve

        spec_path = resolve(json.loads((Path(outcomes_lock) / "lock.json").read_text(encoding="utf-8"))["inputs"]["studyspec"]["path"]).parent
        spec, _ = load_studyspec(spec_path)
        v3 = {"asset": load_v3(safety_asset), "spec": spec, "class_map": class_map(class_map_file),
              "refs": dose_reference(safety_asset)}
    cohorts = {}
    for path in sorted(Path(cohorts_lock).glob("cohort_*.jsonl")):
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        cohorts[path.stem.removeprefix("cohort_")] = {a["arm_id"]: sum(r["arm_id"] == a["arm_id"] for r in rows) for a in model["arms"]}
    scenario, per_arm = next(iter(cohorts.items()))           # arm sizes do not depend on the accrual scenario
    rng = np.random.default_rng(seed)
    arms = []
    for a in model["arms"]:
        n = per_arm.get(a["arm_id"], 0)
        events, v3_info = [], None
        if v3 is not None:
            source_events, v3_info = v3_arm_events(v3["spec"], a, model, v3["asset"], v3["class_map"], v3["refs"], family_map_file)
        else:
            source_events = arm_events(model, a["arm_id"])
        for e in source_events:
            counts = rng.binomial(n, draw_rates(e, rng, replicates)) if n else np.zeros(replicates, int)
            events.append({**e, "enrolled": n, "simulated_affected": {"median": float(np.median(counts)), "q05": float(np.quantile(counts, 0.05)),
                                                                       "q95": float(np.quantile(counts, 0.95))}})
        arms.append({"arm_id": a["arm_id"], "label": a["label"], "enrolled": n,
                     "asset_signature": (model["adverse_events_asset"].get(a["arm_id"]) or {}).get("class_signature"),
                     "missing_classes": (model["adverse_events_asset"].get(a["arm_id"]) or {}).get("missing_classes"),
                     "unmapped_agents": (model["adverse_events_asset"].get(a["arm_id"]) or {}).get("unmapped"),
                     "safety_v3": v3_info, "events": events})
    doc = {"safety_version": SAFETY_VERSION, "scenario": scenario, "replicates": replicates, "seed": seed, "arms": arms,
           "source": (f"safety asset V3 ({v3['asset']['manifest']['safety_asset_version']}) and protocol-stated incidences" if v3
                      else "outcome model: Simulation Parameter Asset V2 class-signature rates and protocol-stated incidences"),
           "status": "RESOLVED" if any(a["events"] for a in arms) else "UNRESOLVED",
           "note": ("V3 rates: regimen classes, relative dose, phase, age group and disease family from the protocol; an arm with no "
                    "classified agent is UNRESOLVED (no catch-all group)" if v3 else
                    "asset rates are adult registry evidence at treatment-class level, extrapolated to this protocol's population")}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "safety_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "safety_summary.json").write_text(json.dumps({"summary": {"status": doc["status"], "arms": {a["arm_id"]: {"enrolled": a["enrolled"], "events": len(a["events"])} for a in arms}}}, indent=1), encoding="utf-8")
    lines = [f"# Simulated adverse events ({SAFETY_VERSION})", "", doc["note"], ""]
    for a in arms:
        info = a.get("safety_v3")
        basis = (f"Safety asset V3: {info['status']}" + (f" ({info['reason']})" if info.get("reason") else "")
                 + f"; classes {info['features']['classes']}; agents {[x['agent'] + ':' + x['class'] for x in info['features']['agents']]}; "
                 f"phase {info['features']['phase']}; paediatric {info['features']['pediatric']}; family {info['features']['disease_family']}; "
                 f"relative dose {'unknown' if info['features']['dose_unknown'] else round(math.exp(info['features']['log_relative_dose']), 2)}."
                 if info else f"Asset class signature {a['asset_signature']}; missing classes {a['missing_classes']}; unmapped agents {a['unmapped_agents']}.")
        lines += [f"## {a['arm_id']}: {a['label']} (n = {a['enrolled']})", "", basis, "",
                  "| event | seriousness | source | rate | patients affected (median, 90%) |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {e['term']} | {e['seriousness']} | {e['source']} | {100 * e['rate_median']:.1f}% | "
                  f"{e['simulated_affected']['median']:g} ({e['simulated_affected']['q05']:g}-{e['simulated_affected']['q95']:g}) |" for e in a["events"]]
        lines.append("")
    (out_dir / "safety_report.md").write_text("\n".join(lines), encoding="utf-8")
    return doc


def pooled_arms(arms: list[dict]) -> list[dict]:
    """The registry tables pool the registered groups, so the arms' predictions are pooled too: per event, the
    enrolment-weighted mean rate (logit-normal with the weighted mean spread). One arm is returned unchanged."""
    if len(arms) <= 1:
        return arms
    total = sum(a["enrolled"] for a in arms) or len(arms)
    acc: dict[tuple, dict] = {}
    for a in arms:
        w = (a["enrolled"] or 1) / total
        for e in a["events"]:
            k = (e["term"], e["seriousness"])
            x = acc.setdefault(k, {"term": e["term"], "seriousness": e["seriousness"], "sources": set(), "rate": 0.0, "sigma": 0.0, "w": 0.0})
            x["sources"].add(e["source"])
            x["rate"] += w * e["rate_median"]
            x["sigma"] += w * e["logit_sigma"]
            x["w"] += w
    events = []
    for x in acc.values():
        rate = x["rate"] / x["w"]                 # events predicted for only some arms are pooled over those arms
        events.append({"term": x["term"], "seriousness": x["seriousness"], "source": "+".join(sorted(x["sources"])),
                       "rate_median": rate, "logit_mu": _logit(rate), "logit_sigma": x["sigma"] / x["w"]})
    return [{"arm_id": "+".join(a["arm_id"] for a in arms), "enrolled": sum(a["enrolled"] for a in arms), "events": events}]


def compare_safety(results: dict, registry: dict) -> dict:
    """Registry adverse events (pooled over the registered groups) against the predicted count distribution at the
    registry's own number at risk. Registry terms are keyed exactly as the safety asset keyed its training terms (the
    UMLS concept linked by the same cached terminology, else the normalised text), within seriousness. A predicted term
    the registry does not list is below the registry's frequency threshold (censored), zero only when the threshold is 0."""
    from .compare import _norm

    key_of = _event_key()
    ae = registry.get("resultsSection", {}).get("adverseEventsModule", {})
    real = {}
    for kind in ("seriousEvents", "otherEvents"):
        for e in ae.get(kind, []):
            k = sum(s.get("numAffected", 0) or 0 for s in e.get("stats", []))
            n = sum(s.get("numAtRisk", 0) or 0 for s in e.get("stats", []))
            if n:
                real[(kind, _norm(key_of(e["term"])))] = {"term": e["term"], "key": _norm(key_of(e["term"])), "kind": kind, "affected": k, "at_risk": n}
    at_risk = [g.get("seriousNumAtRisk") or g.get("otherNumAtRisk") or 0 for g in ae.get("eventGroups", [])]
    n_registry = int(sum(at_risk)) or None
    try:
        threshold = float(ae.get("frequencyThreshold")) if ae.get("frequencyThreshold") not in (None, "") else None
    except ValueError:
        threshold = None
    complete = threshold == 0.0      # every event term was reported, so an unlisted term had no affected patient
    rows, used = [], set()
    for a in pooled_arms(results["arms"]):
        for e in a["events"]:
            kind = "seriousEvents" if e["seriousness"] == "serious" else "otherEvents"
            # asset terms are already concept keys; protocol-quoted terms are free text and are linked the same way
            names = [_norm(e["term"])] if e["source"].startswith("safety_v3") else [_norm(key_of(e["term"])), _norm(e["term"])]
            match = next((real[(kind, t)] for t in names if (kind, t) in real), None) \
                or next((v for (k2, t), v in real.items() if t in names), None)
            row = {"arm_id": a["arm_id"], "term": e["term"], "seriousness": e["seriousness"], "source": e["source"], "predicted_rate": e["rate_median"]}
            n = match["at_risk"] if match else n_registry
            if n:
                d = count_distribution(e, n)
                row.update({"at_risk": n, "predicted_median": d["median"], "predicted_90": [d["q05"], d["q95"]]})
                observed = match["affected"] if match else 0          # a term not listed is not reported, not necessarily absent
                row.update({"observed": observed, "observed_listed": bool(match),
                            "inside_90": d["q05"] <= observed <= d["q95"],
                            "predictive_p_two_sided": float(min(1.0, 2 * min(d["cdf"][observed], 1 - (d["cdf"][observed - 1] if observed else 0.0))))})
                if not match and not complete and threshold:
                    below = max(0, math.ceil(threshold / 100 * n) - 1)   # unlisted: at most this many affected
                    row.update({"observed": None, "observed_at_most": below, "inside_90": d["q05"] <= below,
                                "p_at_most_observed": float(d["cdf"][min(below, n)])})
                    row.pop("predictive_p_two_sided")
                if match:
                    used.add((match["kind"], match["key"]))
            rows.append(row)
    listed = [r for r in rows if r.get("observed_listed")]
    unpredicted = sorted((v for k, v in real.items() if k not in used), key=lambda v: -v["affected"] / v["at_risk"])
    for r in rows:
        if "observed" in r and not r["observed_listed"]:
            r["unlisted_meaning"] = "reported absent (threshold 0)" if complete else "not reported (may be below the reporting threshold)"
    # patients with any event of a kind: at least as many as with any single event, whatever the dependence between events, so
    # P(any-event count <= observed) <= min over events of P(event count <= observed)
    aggregate = {}
    for kind, serious in (("serious", True), ("other", False)):
        k = sum(g.get(f"{kind}NumAffected") or 0 for g in ae.get("eventGroups", []))
        n = sum(g.get(f"{kind}NumAtRisk") or 0 for g in ae.get("eventGroups", []))
        cand = [(e, count_distribution(e, n)) for a in pooled_arms(results["arms"]) for e in a["events"] if (e["seriousness"] == "serious") == serious] if n else []
        if cand:
            e, d = min(cand, key=lambda c: c[1]["cdf"][min(k, n)])
            aggregate[kind] = {"registry_affected": k, "at_risk": n, "bounding_event": e["term"],
                               "p_at_most_observed_upper_bound": float(d["cdf"][min(k, n)])}
        else:
            aggregate[kind] = {"registry_affected": k, "at_risk": n, "status": "UNRESOLVED", "reason": "no predicted event of this kind or no patient at risk"}
    return {"registry_at_risk": n_registry, "registry_reports_adverse_events": bool(ae), "frequency_threshold_pct": threshold,
            "unlisted_terms_are_zero": complete, "aggregate": aggregate, "rows": rows,
            "matched_terms": len(listed), "matched_inside_90": sum(r["inside_90"] for r in listed),
            "unlisted_predicted_terms": sum(1 for r in rows if "observed" in r and not r["observed_listed"]),
            "unlisted_inside_90": sum(r["inside_90"] for r in rows if "observed" in r and not r["observed_listed"]),
            "unpredicted_registry_terms": unpredicted,
            "term_matching": "UMLS concept key, as the safety asset",
            "note": ("a predicted term the registry does not list is censored: fewer patients than the registry's frequency threshold "
                     "(zero only when the threshold is 0); it is inside the 90% interval when the interval reaches below that bound")}


def _event_key():
    """The safety asset's event key for a registry term (spa2.toxicity.study_event_tables): the linked UMLS concept."""
    from ..terminology import FINDING_TYPES, UmlsTerminology

    t = UmlsTerminology(cache_path=Path("data/cache/umls_links.json"))
    cache: dict = {}

    def key(term: str) -> str:
        if term not in cache:
            c = t.link(term, FINDING_TYPES)
            cache[term] = c.key if c else term.casefold().replace(" ", "_")
        return cache[term]
    return key


def run_compare_safety(results_lock: Path, registry_file: Path, registry_fetched_at: str, out_dir: Path) -> dict:
    from .lock import load_locked, verify

    rec = verify(results_lock)
    results = load_locked(results_lock, "safety_results.json")
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    doc = {"compare_version": COMPARE_SAFETY_VERSION, "predictions_locked_at": rec["locked_at"], "registry_fetched_at": registry_fetched_at,
           "order_verified": rec["locked_at"] < registry_fetched_at,
           "registry": {"nct_id": registry["protocolSection"]["identificationModule"]["nctId"]}, **compare_safety(results, registry)}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "safety_comparison.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [f"# Safety comparison with the registry ({COMPARE_SAFETY_VERSION})", "",
             (f"Registry {doc['registry']['nct_id']}. Predictions locked at {doc['predictions_locked_at']}; registry fetched at "
              f"{registry_fetched_at}; order verified: {doc['order_verified']}."), "",
             (f"Registry participants at risk: {doc['registry_at_risk']}; reporting frequency threshold {doc['frequency_threshold_pct']}% "
              f"(unlisted terms are zero: {doc['unlisted_terms_are_zero']}). Matched terms: {doc['matched_terms']}, inside the 90% predictive "
              f"interval: {doc['matched_inside_90']}. Predicted terms not listed (below the threshold): {doc['unlisted_predicted_terms']}, "
              f"consistent with the 90% interval: {doc['unlisted_inside_90']}. Term matching: {doc['term_matching']}."), "", "## Patients with any event", ""]
    for kind, g in doc["aggregate"].items():
        if "bounding_event" in g:
            lines.append(f"- {kind}: registry {g['registry_affected']}/{g['at_risk']}; predicted P(at most {g['registry_affected']}) <= "
                         f"{100 * g['p_at_most_observed_upper_bound']:.1f}% (bound from the most frequent predicted event, '{g['bounding_event']}')")
        else:
            lines.append(f"- {kind}: registry {g['registry_affected']}/{g['at_risk']}; {g['status']}: {g['reason']}")
    lines += ["", "## Per event", "",
             "| arm | event | source | predicted rate | at risk | predicted count (median, 90%) | registry count | listed | inside 90% |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in doc["rows"]:
        if "at_risk" in r:
            lines.append(f"| {r['arm_id']} | {r['term']} | {r['source']} | {100 * r['predicted_rate']:.1f}% | {r['at_risk']} | "
                         f"{r['predicted_median']} ({r['predicted_90'][0]}-{r['predicted_90'][1]}) | "
                         f"{r['observed'] if r['observed'] is not None else '<= ' + str(r['observed_at_most'])} | {r['observed_listed']} | {r['inside_90']} |")
        else:
            lines.append(f"| {r['arm_id']} | {r['term']} | {r['source']} | {100 * r['predicted_rate']:.1f}% | no number at risk | | | | |")
    lines += ["", doc["note"], "", "## Registry terms not predicted", ""]
    lines += [f"- {v['term']} ({v['kind']}): {v['affected']}/{v['at_risk']}" for v in doc["unpredicted_registry_terms"][:30]] or ["- none"]
    (out_dir / "safety_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


# ----------------------------------------------------------------------------- safety asset V3 features of a protocol arm


def _text(x) -> str:
    return (x.get("text") if isinstance(x, dict) else x) or ""


def v3_features(spec: dict, arm_label: str, class_map: dict, dose_reference: dict, family_map_file: Path) -> dict:
    """The safety asset V3 covariates of one protocol arm, from the StudySpec: drug classes of the arm's anticancer
    agents (the evidence build's class map; 'other' and 'unclassified' are not classes), radiotherapy only when a
    radiotherapy item names this arm, dose relative to the corpus median for the agent and unit, phase, paediatric
    population and disease family."""
    from ..planning.report import protocol_features
    from ..safety3 import UNINFORMATIVE, _unit
    from ..spa2.taxonomy import drug_class, modality

    from .arms import ArmResolver

    resolver = ArmResolver(spec)
    arm_id = resolver.arm_id_of_label(arm_label)

    def on_arm(item) -> bool:                          # whole-word arm resolution (clinical_asset.trial.arms, L019)
        return resolver.item_applies_to(item, arm_id) if arm_id else not item.get("arms")

    classes, agents, rel = set(), [], []
    for it in spec["interventions"]:
        if it.get("category") != "anticancer_drug" or not on_arm(it):
            continue
        name = (it.get("canonical_agent") or _text(it.get("agent"))).replace("_", " ").casefold()
        c = drug_class(name, class_map)
        if c == "unclassified":
            c = drug_class(_text(it.get("agent")).casefold(), class_map)
        source = "class map"
        if c in ("unclassified", "other"):                 # a registry synonym found by the self-review (L059)
            from .review import synonym
            alt = synonym(name)
            if alt:
                c, source = drug_class(alt, class_map), f"class of registry synonym '{alt}' (self-review correction)"
        agents.append({"agent": name, "class": c, "class_source": source})
        if modality(c) not in {"supportive_care", "placebo_or_no_treatment"}:
            classes.add(c)
        dose = it.get("dose") or {}
        if dose.get("value") and dose.get("unit"):
            ref = dose_reference.get((name, _unit(dose["unit"])))
            if ref:
                rel.append(math.log(dose["value"] / ref))
    for rt in spec.get("radiotherapy") or []:
        if rt.get("arms") and on_arm(rt):
            classes.add("radiotherapy_or_radiopharmaceutical")
    f = protocol_features(spec, None, family_map_file)
    return {"classes": sorted(classes - UNINFORMATIVE), "unclassified_agent": bool(classes & UNINFORMATIVE) or not classes,
            "agents": agents, "phase": f["phase"], "pediatric": f["pediatric"], "disease_family": f["disease_family"],
            "log_relative_dose": float(np.mean(rel)) if rel else 0.0, "dose_unknown": not rel}


def dose_reference(asset_dir: Path) -> dict:
    """Corpus median dose per (agent, unit) from the safety asset's arms (at least 3 arms)."""
    import pyarrow.parquet as pq

    pool: dict[tuple, list] = {}
    for r in pq.read_table(Path(asset_dir) / "arms.parquet", columns=["doses"]).to_pylist():
        for name, value, unit in json.loads(r["doses"] or "[]"):
            if value and value > 0:
                pool.setdefault((name, unit), []).append(value)
    return {k: float(np.median(v)) for k, v in pool.items() if len(v) >= 3}


def v3_arm_events(spec: dict, arm: dict, model: dict, asset: dict, class_map: dict, refs: dict, family_map_file: Path) -> tuple[list[dict], dict]:
    from ..safety3 import predict_arm

    feats = v3_features(spec, arm["label"], class_map, refs, family_map_file)
    pred = predict_arm(asset, feats)
    from .safety_calibration import calibrate                # implausible rates against comparable registry arms (L061)
    pred["events"], calibration = calibrate(pred.get("events") or [], feats)
    out = [{"term": e["event"], "seriousness": e["seriousness"], "source": f"safety_v3:{pred['status']}", "logit_mu": e["logit_mu"],
            "logit_sigma": e["logit_sigma"], "rate_median": e["rate"],
            **({"plausible_upper": e["plausible_upper"]["rate"]} if e.get("plausible_upper") else {}),
            **({"calibrated_from": e["calibrated_from"]["rate"]} if e.get("calibrated_from") else {})} for e in pred["events"]]
    cited = [e for e in arm_events({**model, "adverse_events_asset": {}}, arm["arm_id"])]          # protocol-stated incidences
    out += cited
    from .review import excluded_terms
    dropped = excluded_terms()                          # terms the self-review found are not events (L059)
    out = [e for e in out if e["term"] not in dropped]
    status, reason = pred["status"], pred.get("reason")
    if status == "UNRESOLVED":                  # no drug class in the asset (L034): the protocol's own figures, else none
        status = "PROTOCOL_CITED" if cited else "NO_EVIDENCE"
        reason = (f"{reason}; the protocol's cited incidences are used ({len(cited)} events)" if cited else
                  f"{reason}; the protocol cites no incidence for this arm: no source quantifies its adverse events, so none are simulated")
    return out, {"status": status, "reason": reason, "features": feats, "classes_without_data": pred.get("classes_without_data"),
                 "calibration": calibration}


# ----------------------------------------------------------------------------- drug classes of agents new to the class map

EXTENSION = Path("data/spa_work/drug_classes_ext.json")


def class_map(base_file: Path = Path("data/spa_work/drug_classes.json"), extension_file: Path = EXTENSION) -> dict:
    """The evidence build's drug-class map, plus agents classified later by the same mapper (never overriding the base)."""
    base = json.loads(Path(base_file).read_text(encoding="utf-8"))
    ext = json.loads(Path(extension_file).read_text(encoding="utf-8"))["mappings"] if Path(extension_file).exists() else {}
    confident = {k: v for k, v in base.items() if (v.get("confidence") or 0) >= 0.7}
    return {**base, **{k: v for k, v in ext.items() if k not in confident}}      # never overrides a confident base entry


def extend_class_map(model, spec_locks: list[Path], created: str, extension_file: Path = EXTENSION) -> dict:
    """Classify the anticancer agents of the given StudySpecs that the class map does not know, with the same mapper
    (taxonomy, instructions and confidence threshold) that built the map. Existing entries are kept."""
    from ..spa2.taxonomy import map_drugs
    from .studyspec import load_studyspec

    known = class_map(extension_file=extension_file)
    todo: dict[str, str] = {}
    for lock in spec_locks:
        spec, _ = load_studyspec(lock)
        for it in spec["interventions"]:
            if it.get("category") != "anticancer_drug":
                continue
            name = (it.get("canonical_agent") or _text(it.get("agent"))).replace("_", " ").casefold()
            if name and (name not in known or (known[name].get("confidence") or 0) < 0.7):   # absent, or below the map's threshold
                todo[name] = _text(it.get("agent"))
    found = map_drugs(model, [{"item": k, "definition": f"as written in the protocol: {v}"} for k, v in sorted(todo.items())]) if todo else {}
    doc = json.loads(Path(extension_file).read_text(encoding="utf-8")) if Path(extension_file).exists() else {"mappings": {}, "history": []}
    doc["mappings"].update(found)
    doc["history"].append({"created": created, "specs": [str(p) for p in spec_locks], "classified": sorted(found), "unmatched": sorted(set(todo) - set(found))})
    Path(extension_file).write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"classified": {k: found[k] for k in sorted(found)}, "unmatched": sorted(set(todo) - set(found))}
