"""One source ladder for every endpoint of any protocol (lesson L027: secondary endpoints, unmodelled binary endpoints
and families without evidence were left UNRESOLVED; lessons L016, L018, L022, L023 set the order).

classify(name) puts an endpoint in one class, from the wording table in the reference vocabulary:
  time_to_event (a median, in months), proportion (a share of patients), safety (the safety stage), or
  not_simulated:<kind> (patient-reported, pharmacokinetic, biomarker, economic, qualitative measures: the generated
  patients carry no such measurement, so these are reported as outside the simulation, never as failures).

quantify(...) gives the value for one arm, walking the ladder and labelling the rung it stops at:
  1. protocol-cited figure for the arm's own regimen (a verified historical-study fact; L018);
  2. evidence for the same regimen, then overlapping drug classes / age / phase (subgroups ladder);
  3. the disease family's evidence (a mixture over other regimens: weak, labelled; L022);
  4. the same ladder over all oncology when the family has no evidence;
  5. the protocol's own design hypothesis (p1, else p0) for a proportion with no evidence at all.
"""

from functools import lru_cache

from ..reference import vocabulary


@lru_cache(maxsize=1)
def _classes() -> dict:
    return vocabulary()["endpoint_classes"]


def classify(name: str | None, endpoint_type: str | None = None) -> tuple[str, str | None]:
    text = f" {' '.join((name or '').casefold().replace('(', ' ').replace(')', ' ').split())} "
    c = _classes()
    for kind, words in c["not_simulated"]:
        if any(w in text for w in words):
            return "not_simulated", kind
    if any(w in text for w in c["safety"]):
        return "safety", None
    if endpoint_type != "binary":
        for var, words in c["time_to_event"]:
            if any(w in text for w in words):
                return "time_to_event", var
    for var, words in c["proportion"]:
        if any(w in text for w in words):
            return "proportion", var
    if endpoint_type == "time_to_event":
        return "time_to_event", None
    return "not_simulated", "other_measure"


def _cited_median(facts: list[dict] | None, spec: dict, arm_id: str | None, variable: str) -> tuple | None:
    from .journey_evidence import same_regimen

    for f in facts or []:
        val = f.get("value") or {}
        cat = f.get("category")
        cat = cat.get("text") if isinstance(cat, dict) else cat
        if (f.get("source") == "historical_study" and f.get("canonical_variable") == variable and (val.get("unit") or "").casefold().startswith("month")
                and val.get("value") and same_regimen(cat, spec, arm_id)):
            return float(val["value"]), f["fact_id"], cat
    return None


def _cited_rate(facts: list[dict] | None, spec: dict, arm_id: str | None, variable: str) -> tuple | None:
    """A response proportion the protocol cites for the arm's own regimen (largest denominator first, L023)."""
    from .journey_evidence import _tokens, same_regimen

    best = None
    for f in facts or []:
        val = f.get("value") or {}
        cat = f.get("category")
        cat = cat.get("text") if isinstance(cat, dict) else cat
        arm = f.get("arm")
        arm = arm.get("text") if isinstance(arm, dict) else arm
        label = arm or cat
        if (f.get("source") == "historical_study" and f.get("kind") == "response_rate" and val.get("scale") == "proportion"
                and val.get("value") is not None and classify((f.get("canonical_variable") or "").replace("_", " "), "binary")[1] == variable
                and same_regimen(label, spec, arm_id)):
            key = (len(_tokens(label)), val.get("denominator") or 0)      # the most specific regimen wording, then the largest study
            if best is None or key > best[4]:
                best = (float(val["value"]), f["fact_id"], label, val.get("denominator") or 0, key)
    return best


def _level(est: dict) -> str:
    sub = est.get("subgroup") or ""
    if est.get("family_fallback"):
        return "all oncology (no evidence in the disease family)"
    return "disease family mixture (weak)" if sub == "whole disease family" else sub


def quantify(spec: dict, arm_id: str, kind: str, variable: str | None, features: dict, facts: list[dict] | None = None,
             design: dict | None = None) -> dict:
    """{'status': 'RESOLVED', 'value', 'unit', 'level', 'source'} for one arm (or NOT_SIMULATED with its kind)."""
    from .journey_evidence import registry_phase
    from .subgroups import arm_age_group, estimate, estimate_median

    if kind == "not_simulated":
        return {"status": "NOT_SIMULATED", "kind": variable, "reason": "the generated patients carry no such measurement"}
    if kind == "safety":
        return {"status": "RESOLVED", "level": "safety stage", "source": "simulated adverse events (safety stage)", "value": None}
    family = features.get("disease_family") or None
    classes = list(features.get("classes") or [])
    agents = [a["agent"] for a in features.get("agents") or []]
    age, phase = arm_age_group(spec), registry_phase(spec)
    if kind == "time_to_event":
        if variable:
            cited = _cited_median(facts, spec, arm_id, variable)
            if cited:
                return {"status": "RESOLVED", "value": cited[0], "unit": "months", "level": "protocol-cited, same regimen",
                        "source": f"protocol fact {cited[1]} ({cited[2]})"}
            est = estimate_median(variable, family, classes, agents, age, phase)
            if est.get("status") == "RESOLVED" and est.get("median_months"):
                return {"status": "RESOLVED", "value": est["median_months"], "unit": "months", "level": _level(est),
                        "source": f"evidence medians of {variable} ({est.get('studies')} studies)", "detail": {k: v for k, v in est.items() if k != "status"}}
        return {"status": "RESOLVED", "value": None, "unit": "months", "level": "simulated time-to-event",
                "source": "taken from the simulated patients' event times (no reported median for this endpoint)"}
    # proportion
    cited = _cited_rate(facts, spec, arm_id, variable) if variable else None
    if cited:
        return {"status": "RESOLVED", "value": cited[0], "unit": "proportion", "level": "protocol-cited, same regimen",
                "source": f"protocol fact {cited[1]} ({cited[2]}" + (f", n = {cited[3]:g})" if cited[3] else ")"),
                "small_sample": bool(cited[3]) and cited[3] < 20}
    est = estimate(variable, family, classes, agents, age, phase) if variable else {"status": "UNRESOLVED"}
    if est.get("status") == "RESOLVED" and est.get("headline"):
        h = est["headline"]
        return {"status": "RESOLVED", "value": h["estimate"], "unit": "proportion", "level": _level({**est, "subgroup": est.get("headline_subgroup")}),
                "source": f"evidence arms reporting {variable} ({h.get('studies')} studies)", "ci95": h.get("ci95")}
    d = design or {}
    rate = d.get("p1") if d.get("p1") is not None else d.get("p0")
    if rate is not None:
        return {"status": "RESOLVED", "value": float(rate), "unit": "proportion", "level": "protocol design hypothesis",
                "source": f"the protocol's {'alternative (p1)' if d.get('p1') is not None else 'null (p0)'} response rate"}
    return {"status": "RESOLVED", "value": None, "unit": "proportion", "level": "simulated",
            "source": "no evidence and no design rate: the share is read from the simulated patients"}
