"""Milestones 9-16 for designs whose primary decision is a binary rule per arm or cohort (single-stage or two-stage).

The quantity such a trial tests is each arm's true response rate p. As for the two-arm survival engine, the
protocol's design hypotheses (p0, p1) are never used as the truth:

* the probability that an arm is declared of interest is computed EXACTLY from the compiled decision rule for a
  grid of true rates (and at the protocol's p0 and p1, where it must reproduce the stated error rates);
* where the protocol itself cites an earlier response rate of the same treatment in the same disease, a binding
  step (model proposal, deterministic checks, verifier majority) links it to the arm, and the prediction at that
  rate is reported as conditional on that cited evidence;
* complete trials are simulated per rate to give registry-style distributions: participants enrolled per arm,
  responders, observed response rate with its exact 95% interval, and whether the arm stopped early.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from ..protocol import design_rules as dr
from ..protocol import schemas as psc
from ..protocol.compiler import _majority

BINARY_VERSION = "binary-1.0.0"
RATE_GRID = [round(0.05 * k, 2) for k in range(1, 15)]           # 5% ... 70%

TEXT = {"type": "string"}
RATE_BINDINGS = psc.obj({"bindings": {"type": "array", "items": psc.obj({
    "decision_rule_id": TEXT, "fact_id": TEXT, "reason": TEXT})}})
RATE_INSTRUCTIONS = (
    "'rules' are a trial's per-arm decision rules (the arm's treatment and cohort). 'facts' are quantitative statements "
    "from the same protocol. For each rule, give the fact (if any) that states an OBSERVED response rate of the SAME "
    "treatment in patients with the SAME disease as that rule's cohort, reported by an earlier study the protocol "
    "cites, counting the SAME outcome as the rule's endpoint ('endpoint'). Stable disease, clinical benefit, disease "
    "control or survival counts are different endpoints and never a response rate. Never use the design's null or "
    "target rates (p0, p1), rates of other drugs, other diseases or other endpoints. fact_id '' when there is none. "
    "reason: one short sentence."
)
RATE_VERIFY = (
    " Here each item states that a protocol fact is an earlier OBSERVED response rate of the same treatment in the "
    "same disease as the arm of a decision rule, counting the rule's endpoint. Judge only that link, using the protocol "
    "text: INCORRECT if the fact is a design hypothesis (p0 or p1), a different drug or combination, a different disease "
    "or a different endpoint (a stable-disease, clinical-benefit or disease-control count is not a response rate)."
)


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def binary_rules(spec: dict) -> list[dict]:
    return [r for r in spec.get("decision_rules") or [] if r["kind"] == "binary" and r.get("status") == "EXECUTABLE"]


def arm_text(spec: dict, rule: dict) -> str:
    labels = {a["arm_id"]: f"{_q(a['label'])} ({_q(a.get('description')) or ''})" for a in spec["arms"]}
    return "; ".join(labels.get(a, a) for a in rule["arms"]) or "; ".join(_q(x) or "" for x in rule.get("arm_quotes") or [])


def bind_cited_rates(model: Any, spec: dict, facts: list[dict], section_text: Any, votes: int = 3, workers: int = 6) -> list[dict]:
    rules = binary_rules(spec)
    candidates = [f for f in facts if f["kind"] == "response_rate" and f["value"].get("scale") == "proportion"]
    if not rules or not candidates:
        return []
    payload = {"instructions": RATE_INSTRUCTIONS,
               "rules": [{"decision_rule_id": r["decision_rule_id"], "arm": arm_text(spec, r), "cohort": _q(r.get("cohort")),
                          "endpoint": _q(r.get("endpoint"))} for r in rules],
               "facts": [{"fact_id": f["fact_id"], "fact": f["rendering"], "wording": _q(f.get("evidence")) or ""} for f in candidates]}
    out = model.extract("binary_rate_bindings", RATE_BINDINGS, payload)
    by_rule = {r["decision_rule_id"]: r for r in rules}
    by_fact = {f["fact_id"]: f for f in candidates}
    items = []
    for b in out.get("bindings", []):
        rule, fact = by_rule.get(b["decision_rule_id"]), by_fact.get(b["fact_id"])
        if not b["fact_id"] or rule is None:
            continue
        issues = [] if fact is not None else [f"{b['fact_id']!r} is not a usable response-rate fact"]
        items.append({"decision_rule_id": b["decision_rule_id"], "fact_id": b["fact_id"], "issues": issues,
                      "rate": None if fact is None else fact["value"]["value"],
                      "rendering": (f"fact {b['fact_id']} is an earlier observed rate of {_q(rule.get('endpoint')) or 'response'} for the treatment of arm "
                                    f"{arm_text(spec, rule)!r} in the disease of cohort {_q(rule.get('cohort'))!r}: "
                                    f"{fact['rendering'] if fact else '?'}")})

    def run(job):
        it, vote = job
        fact = by_fact.get(it["fact_id"])
        payload = {"instructions": psc.VERIFY_INSTRUCTIONS + RATE_VERIFY, "text": section_text(fact) if fact and section_text else "",
                   "items": [{"item_id": "B1", "rendering": it["rendering"], "evidence": _q((fact or {}).get("evidence")) or "", "related": []}]}
        if vote:
            payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
        try:
            got = model.extract("protocol_verify", psc.VERIFY, payload)
            return it, next((v for v in got.get("verdicts", []) if v.get("item_id") == "B1"), None)
        except Exception:  # noqa: BLE001 - a failed vote counts as no vote
            return it, None
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run, [(it, v) for it in items for v in range(votes)]))
    cast: dict[int, list] = {}
    for it, v in results:
        if v is not None and v.get("verdict") in {"FAITHFUL", "INCOMPLETE", "INCORRECT", "NOT_A_RULE"}:
            cast.setdefault(id(it), []).append(v)
    for it in items:
        v = _majority(cast.get(id(it), []), votes)
        it["verification"] = {"votes": [x["verdict"] for x in cast.get(id(it), [])], "reviewer_note": v["reviewer_note"] if v else None}
        it["status"] = "USABLE" if v and v["verdict"] == "FAITHFUL" and not it["issues"] else "REVIEW_REQUIRED"
    return items


def exact_curve(rule: dict, grid: list[float]) -> list[dict]:
    b = rule["rule"]
    if b.get("success_if_at_least") is None:        # descriptive: no decision is defined
        return [{"p": p, "prob_of_interest": None, "prob_early_stop": dr.prob_early_stop(b, p), "expected_n": dr.expected_n(b, p)} for p in grid]
    return [{"p": p, "prob_of_interest": dr.prob_success(b, p), "prob_early_stop": dr.prob_early_stop(b, p), "expected_n": dr.expected_n(b, p)}
            for p in grid]


def descriptive_rules(spec: dict) -> list[dict]:
    """When no decision rule is executable: the primary binary efficacy endpoint estimated on the protocol's evaluable
    sample size. Nothing is decided; only the distribution of the observed rate is predicted."""
    endpoints = [e for e in spec["endpoints"] if e["role"] == "primary" and e["type"] == "binary" and e.get("status") == "EXECUTABLE"]
    sizes = [s for s in spec.get("sample_size") or [] if s["quantity"] == "evaluable_target" and s.get("value")] or \
            [s for s in spec.get("sample_size") or [] if s["quantity"] == "target_accrual" and s.get("value")]
    if not endpoints or not sizes:
        return []
    n = int(sizes[0]["value"])
    rules = []
    for aid in [a["arm_id"] for a in spec["arms"] if a.get("status") == "open"] or [a["arm_id"] for a in spec["arms"]]:
        rules.append({"decision_rule_id": f"EST-{aid}", "kind": "binary", "role": "primary", "arms": [aid], "arm_quotes": [],
                      "cohort": None, "endpoint": endpoints[0].get("name"), "design_family": "descriptive_estimate", "status": "EXECUTABLE",
                      "compile_issues": [], "descriptive": True, "sample_size_evidence": _q(sizes[0].get("evidence")),
                      "rule": {"stages": [{"n": n, "stop_if_at_most": None}], "success_if_at_least": None, "p0": None, "p1": None,
                               "alpha": None, "beta": None, "stated_early_termination": None}})
    return rules


def simulate_rule(rule: dict, p: float, rng: np.random.Generator, replicates: int) -> dict:
    """Complete runs of one arm's rule: enrolled evaluable patients, responders, observed rate and its exact interval."""
    b = rule["rule"]
    enrolled, responders, stopped, of_interest = [], [], [], []
    for _ in range(replicates):
        x, prev = 0, 0
        stop = False
        for k, s in enumerate(b["stages"]):
            x += int(rng.binomial(s["n"] - prev, p))
            prev = s["n"]
            if k < len(b["stages"]) - 1 and x <= s["stop_if_at_most"]:
                stop = True
                break
        enrolled.append(prev)
        responders.append(x)
        stopped.append(stop)
        of_interest.append((not stop) and b["success_if_at_least"] is not None and x >= b["success_if_at_least"])
    enrolled, responders = np.array(enrolled), np.array(responders)
    rates = responders / enrolled
    return {"p": p, "prob_of_interest_simulated": float(np.mean(of_interest)), "prob_early_stop_simulated": float(np.mean(stopped)),
            "enrolled": _dist(enrolled), "responders": _dist(responders), "observed_rate": _dist(rates)}


def exact_interval(x: int, n: int) -> tuple[float, float]:
    lo = 0.0 if x == 0 else float(stats.beta.ppf(0.025, x, n - x + 1))
    hi = 1.0 if x == n else float(stats.beta.ppf(0.975, x + 1, n - x))
    return lo, hi


def _dist(v) -> dict:
    v = np.asarray(v, dtype=float)
    return {"median": float(np.median(v)), "q05": float(np.quantile(v, 0.05)), "q95": float(np.quantile(v, 0.95))}


def run_binary(model_client: Any, spec_lock: Path, facts_lock: Path, out_dir: Path, replicates: int = 2000, seed: int = 20260927,
               votes: int = 3) -> dict:
    from .population import _section_text_of
    from .studyspec import load_facts, load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    facts, facts_record = load_facts(facts_lock)
    rules = binary_rules(spec)
    unresolved = [r["decision_rule_id"] for r in spec.get("decision_rules") or [] if r["kind"] == "binary" and r.get("status") != "EXECUTABLE"]
    if not rules:
        rules = descriptive_rules(spec)
    if not rules:
        raise ValueError("the StudySpec has neither an executable binary decision rule nor a binary primary endpoint with a sample size")
    spec = {**spec, "decision_rules": rules if rules[0].get("descriptive") else spec.get("decision_rules")}
    cited = bind_cited_rates(model_client, spec, facts, _section_text_of(facts_record), votes=votes)
    rng = np.random.default_rng(seed)
    per_rule = []
    for rule in rules:
        b = rule["rule"]
        design = sorted({p for p in (b["p0"], b["p1"]) if p is not None})
        usable = [c for c in cited if c["decision_rule_id"] == rule["decision_rule_id"] and c["status"] == "USABLE"]
        grid = sorted(set(RATE_GRID + design + [c["rate"] for c in usable]))
        curve = exact_curve(rule, grid)
        sims = {p: simulate_rule(rule, p, rng, replicates) for p in grid}
        per_rule.append({
            "decision_rule_id": rule["decision_rule_id"], "role": rule["role"], "arm": arm_text(spec, rule), "arms": rule["arms"],
            "cohort": _q(rule.get("cohort")), "design_family": rule["design_family"], "rule": {k: b[k] for k in ("stages", "success_if_at_least", "p0", "p1", "alpha", "beta")},
            "design_checks": {"stated": {"alpha": b["alpha"], "beta": b["beta"], "early_termination": b["stated_early_termination"]},
                              "exact": b.get("operating_characteristics"), "consistent": not rule.get("compile_issues")},
            "exact_curve": curve, "simulated": [sims[p] for p in grid],
            "cited_evidence": [{"fact_id": c["fact_id"], "rate": c["rate"],
                                "prob_of_interest": None if b["success_if_at_least"] is None else dr.prob_success(b, c["rate"])} for c in usable],
            "descriptive": bool(rule.get("descriptive")),
            "arm_status": [next((a["status"] for a in spec["arms"] if a["arm_id"] == aid), None) for aid in rule["arms"]]})
    doc = {"binary_version": BINARY_VERSION, "seed": seed, "replicates": replicates,
           "inputs": {"studyspec": spec_record["files"]["studyspec.json"], "facts": facts_record["files"]["population_facts.json"]},
           "truth": "each arm's true response rate p is unknown: results are given for a grid of p (exact) and at rates the protocol cites",
           "cited_rate_bindings": cited, "rules": per_rule,
           "unresolved_decision_rules": unresolved,
           "mode": "descriptive estimation (no executable decision rule)" if rules[0].get("descriptive") else "decision rules"}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "binary_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "binary_report.md").write_text(_report(doc), encoding="utf-8")
    return {"mode": doc["mode"], "unresolved_decision_rules": unresolved,
            "rules": [{"rule": r["decision_rule_id"], "arm": r["arm"][:60], "cohort": (r["cohort"] or "")[:40],
                       "cited": r["cited_evidence"], "p_interest_at_p0": next((c["prob_of_interest"] for c in r["exact_curve"] if c["p"] == r["rule"]["p0"]), None),
                       "p_interest_at_p1": next((c["prob_of_interest"] for c in r["exact_curve"] if c["p"] == r["rule"]["p1"]), None)} for r in per_rule]}


def _report(doc: dict) -> str:
    lines = [f"# Per-arm binary decision rules ({doc['binary_version']})", "", doc["truth"] + ".", "", f"Mode: {doc['mode']}.",
             (f"Decision rules not executable in the StudySpec (unresolved, not simulated): {doc['unresolved_decision_rules']}."
              if doc["unresolved_decision_rules"] else ""), ""]
    for r in doc["rules"]:
        rule = r["rule"]
        stages = " -> ".join(f"{s['n']}" + (f" (stop if <= {s['stop_if_at_most']})" if s["stop_if_at_most"] is not None else "") for s in rule["stages"])
        lines += [f"## {r['decision_rule_id']} ({r['role']}): {r['arm']}", "",
                  f"Cohort: {r['cohort']}. Arm status in this protocol version: {r['arm_status']}.",
                  f"Design ({r['design_family']}): {stages}; of interest if >= {rule['success_if_at_least']} responses; p0 {rule['p0']}, p1 {rule['p1']}.", ""]
        ex = r["design_checks"]["exact"] or {}
        if ex:
            lines.append(f"Exact check against the protocol: type I error {ex.get('at_p0', {}).get('prob_success', float('nan')):.3f} "
                         f"(stated alpha {rule['alpha']}), power {ex.get('at_p1', {}).get('prob_success', float('nan')):.3f} "
                         f"(stated 1-beta {None if rule['beta'] is None else round(1 - rule['beta'], 2)}), early stop under p0 "
                         f"{ex.get('at_p0', {}).get('prob_early_stop', float('nan')):.3f} (stated {r['design_checks']['stated']['early_termination']}).")
            lines.append("")
        lines += ["| true rate | P(of interest) | P(early stop) | expected enrolled | observed rate (median, 90%) |", "| ---: | ---: | ---: | ---: | --- |"]
        for c, s in zip(r["exact_curve"], r["simulated"], strict=True):
            o = s["observed_rate"]
            interest = "not defined" if c["prob_of_interest"] is None else f"{c['prob_of_interest']:.3f}"
            lines.append(f"| {c['p']:.2f} | {interest} | {c['prob_early_stop']:.3f} | {c['expected_n']:.1f} | "
                         f"{o['median']:.2f} ({o['q05']:.2f}-{o['q95']:.2f}) |")
        for c in r["cited_evidence"]:
            interest = "not defined" if c["prob_of_interest"] is None else f"{c['prob_of_interest']:.3f}"
            lines.append(f"\nConditional on the rate the protocol cites ({c['fact_id']}: {c['rate']:.2f}): P(of interest) = {interest}.")
        lines.append("")
    return "\n".join(lines) + "\n"


def exact_interval_width(n: int, p: float) -> float:  # used by reports of descriptive expansion cohorts
    x = round(n * p)
    lo, hi = exact_interval(x, n)
    return hi - lo

