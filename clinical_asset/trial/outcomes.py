"""Milestone 11: patient outcomes (event-free survival, loss to follow-up, adverse events).

Sources, in the order they are used (nothing else, and nothing invented):

* Control-arm event-free survival: the protocol's own quantitative description, chosen by an outcome
  binding (model proposal, deterministic checks, verifier majority): the cure (long-term) EFS rate and
  EFS at stated time points, in the model family the protocol names. For a cure model
  S(t) = pi + (1 - pi) exp(-lambda t), lambda is solved from a stated time point.
* The experimental effect is never taken from the protocol's design hypothesis. It is a proportional
  effect on the whole EFS curve, S_B(t) = S_A(t)^HR (the protocol's relative failure rate), with HR from
  (a) an evidence prior built from Simulation Parameter Asset V3 comparisons in which one arm adds a
  drug to a radiotherapy-containing regimen (random-effects predictive distribution, indirect evidence),
  and reported conditionally at HR = 1 and at the protocol's design alternative.
* Loss to follow-up: the censoring rate the StudySpec states (exponential).
* Adverse events: incidence rates the protocol states for its own treatment (bound facts), and per-term
  rates from the retained Simulation Parameter Asset V2 toxicity models for the nearest treatment-class
  signature, flagged as adult evidence extrapolated to the protocol's population.
"""

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from ..protocol import schemas as psc
from ..protocol.compiler import _majority

OUTCOMES_VERSION = "outcomes-1.0.0"
EFS_LIKE = {"event_free_survival", "progression_free_survival", "disease_free_survival", "time_to_progression"}
RADIOTHERAPY = re.compile(r"\b(radiation|radiotherapy|irradiation|rt)\b", re.IGNORECASE)

TEXT = {"type": "string"}
OUTCOME_BINDINGS = psc.obj({
    "control_arm_id": TEXT, "control_arm_reason": TEXT,
    "efs_model_family": psc.enum("cure_model", "not_stated"), "efs_model_quote": TEXT,
    "cure_fact_id": TEXT,
    "timepoint_facts": {"type": "array", "items": psc.obj({"fact_id": TEXT, "years": {"type": "number"}})},
    "toxicities": {"type": "array", "items": psc.obj({"fact_id": TEXT, "event": TEXT, "grade": TEXT,
                                                       "applies_to": psc.enum("all_arms", "one_arm"), "arm_id": TEXT})},
    "analysis_evaluable_target_ref": TEXT, "analysis_population_quote": TEXT, "analysis_followup_years": {"type": "number"},
    "analysis_rule_quote": TEXT, "analysis_exclusion_ref": TEXT})
OUTCOME_INSTRUCTIONS = (
    "'arms' are the randomized arms of a protocol; 'facts' are quantitative statements the protocol makes. Identify: "
    "control_arm_id, the arm the protocol treats as its reference or control group (the arm without the experimental "
    "addition); efs_model_family 'cure_model' only if the protocol states that its reference group's event-free "
    "survival is represented by a cure model (quote that sentence in efs_model_quote), else 'not_stated'; cure_fact_id, "
    "the fact giving the reference group's long-term (cure) EFS rate as the protocol expects it for this trial's "
    "control treatment, or ''; timepoint_facts, facts giving the reference group's EFS at a stated time, with that time "
    "in years; toxicities, facts that state the INCIDENCE of an adverse event observed or expected under this "
    "protocol's treatment or under treatment the protocol cites as the basis for its own (historical studies of the "
    "same kind of treatment count; not a monitoring threshold, stopping rule, prior parameter or target), with the event "
    "name, grade as written and whether it applies to all arms or one arm. Use only fact ids from the list; never "
    "use the protocol's hypothesised experimental-arm rates or effect sizes. 'design' lists the protocol's sample-size "
    "statements (ids SS...). The FINAL primary analysis rule: analysis_evaluable_target_ref, the id (SS or fact) of the "
    "number of eligible and evaluable patients that must be enrolled; analysis_population_quote, who they are, copied "
    "from the text ('medulloblastoma patients'); analysis_followup_years, the minimum follow-up all of them must have; "
    "analysis_rule_quote, the sentence stating the rule, copied from the text; analysis_exclusion_ref: the id (SS or "
    "fact) of the share of enrolled patients expected to be excluded from the primary analysis set; '' when not stated."
)
OUTCOME_VERIFY = (
    " Here each item is an OUTCOME BINDING: a statement that a protocol statement plays a given role in the simulation "
    "(which arm is the control, the model family and rates of the control arm's EFS, the incidence of an adverse event "
    "under treatment the protocol describes, or a rule of the final analysis). The statement itself was already "
    "verified; judge ONLY whether it plays exactly that role according to 'text' (the protocol sections). For EFS and "
    "adverse-event roles, INCORRECT if the number is the protocol's hypothesis for the experimental arm, a monitoring "
    "threshold, a stopping rule, a prior parameter, a different group or a different time. For final-analysis roles "
    "(evaluable target, follow-up, exclusions) a planned target or expectation is exactly what is meant."
)


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


# ----------------------------------------------------------------------------- outcome bindings


def bind_outcomes(model: Any, arms: list[dict], facts: list[dict], section_text: Any, votes: int = 3, workers: int = 6,
                  sample_size: list[dict] | None = None) -> dict:
    design = {f"SS{i + 1}": s for i, s in enumerate(sample_size or [])}
    by_id = {f["fact_id"]: f for f in facts}
    candidates = [f for f in facts if f["kind"] in {"event_free_survival", "toxicity_rate", "other_outcome", "dropout_or_evaluability"}]
    protocol_text = _joined_sections(candidates, section_text)
    payload = {"instructions": OUTCOME_INSTRUCTIONS, "arms": arms, "protocol_text": protocol_text,
               "facts": [{"fact_id": f["fact_id"], "fact": f["rendering"], "wording": _q(f.get("evidence")) or ""} for f in candidates],
               "design": [{"id": k, "quantity": s["quantity"], "value": s["value"], "unit": s.get("unit"), "wording": _q(s.get("evidence"))}
                          for k, s in design.items()]}
    out = model.extract("outcome_bindings", OUTCOME_BINDINGS, payload)
    items = []
    for role, ref in (("analysis_rule", out["analysis_evaluable_target_ref"]), ("analysis_exclusion", out["analysis_exclusion_ref"])):
        if not ref:
            continue
        src = design.get(ref) or by_id.get(ref)
        value = (src or {}).get("value")
        value = value.get("value") if isinstance(value, dict) else value
        item = {"role": role, "ref": ref, "value": value, "issues": [] if src is not None and value is not None else [f"{ref!r} is not a stated value"],
                "evidence_text": _q((src or {}).get("evidence")) or "", "fact_id": ref if ref in by_id else None}
        if role == "analysis_rule":
            item["years"], item["population"], item["quote"] = out["analysis_followup_years"], out["analysis_population_quote"], out["analysis_rule_quote"]
            if not (item["years"] and item["years"] > 0):
                item["issues"].append("follow-up must be a positive number of years")
            if not item["quote"] or _normalised(item["quote"]) not in _normalised(protocol_text):
                item["issues"].append("the analysis-rule quote is not in the protocol text")
        if role == "analysis_exclusion" and ref in by_id and by_id[ref]["value"].get("scale") != "proportion":
            item["issues"].append("exclusion must be a share")
        if role == "analysis_rule":
            item["rendering"] = (f"the final analysis is conducted once {value or 0:g} eligible and evaluable {out['analysis_population_quote'] or 'patients'} "
                                 f"have been enrolled and all have been followed for at least {out['analysis_followup_years'] or 0:g} year(s)")
        else:
            item["rendering"] = (f"the protocol expects a share of about {value or 0:g} of enrolled patients to be excluded from the data set "
                                 "used for the primary objectives")
        items.append(item)
    arm_ids = {a["arm_id"] for a in arms}
    arm = next((a for a in arms if a["arm_id"] == out["control_arm_id"]), None)
    items.append({"role": "control_arm", "arm_id": out["control_arm_id"], "fact_id": None,
                  "issues": [] if arm else [f"{out['control_arm_id']!r} is not a randomized arm"],
                  "evidence_text": "; ".join(f"{a['label']}: {a.get('description') or ''}" for a in arms),
                  "rendering": (f"the protocol's control (reference) arm, the arm without the experimental addition, is "
                                f"{(arm or {}).get('label', '?')!r} ({(arm or {}).get('description') or ''})")})
    quote = out["efs_model_quote"] or ""
    found = bool(quote) and _normalised(quote) in _normalised(protocol_text)
    items.append({"role": "efs_model_family", "family": out["efs_model_family"], "quote": quote, "fact_id": None,
                  "issues": [] if found else ["the model-family quote is not in the protocol text"],
                  "rendering": f"the protocol states that the reference group's EFS is represented by a {out['efs_model_family']}: {quote!r}"})
    if out["cure_fact_id"]:
        f = by_id.get(out["cure_fact_id"])
        items.append({"role": "control_cure_rate", "fact_id": out["cure_fact_id"], "issues": _fact_issues(f, "event_free_survival"),
                      "rendering": f"fact {out['cure_fact_id']} is the control arm's long-term (cure) EFS rate ({f['rendering'] if f else '?'})"})
    for tp in out["timepoint_facts"]:
        f = by_id.get(tp["fact_id"])
        issues = _fact_issues(f, "event_free_survival") + ([] if tp["years"] and tp["years"] > 0 else ["time point must be positive"])
        items.append({"role": "control_efs_timepoint", "fact_id": tp["fact_id"], "years": tp["years"], "issues": issues,
                      "rendering": f"fact {tp['fact_id']} is the control arm's EFS at {tp['years']:g} years ({f['rendering'] if f else '?'})"})
    for t in out["toxicities"]:
        f = by_id.get(t["fact_id"])
        issues = _fact_issues(f, "toxicity_rate") + ([] if t["applies_to"] == "all_arms" or t["arm_id"] in arm_ids else ["unknown arm"])
        items.append({"role": "toxicity_incidence", "fact_id": t["fact_id"], "event": t["event"], "grade": t["grade"],
                      "applies_to": t["applies_to"], "arm_id": t["arm_id"], "issues": issues,
                      "rendering": (f"fact {t['fact_id']} is the incidence of {t['event']} (grade {t['grade']}) observed or expected under "
                                    f"this protocol's treatment or the treatment the protocol cites as the basis for its own, applied to "
                                    f"{'all arms' if t['applies_to'] == 'all_arms' else t['arm_id']} ({f['rendering'] if f else '?'})")})
    _verify(model, items, by_id, section_text, votes, workers, protocol_text)
    for it in items:
        it["status"] = "USABLE" if it.get("semantic_status") == "FAITHFUL" and not it["issues"] else "REVIEW_REQUIRED"
    return {"items": items}


def _normalised(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def _joined_sections(facts: list[dict], section_text: Any, limit: int = 80000) -> str:
    """The protocol sections the candidate facts come from, each once."""
    if section_text is None:
        return ""
    seen, parts = set(), []
    for f in facts:
        key = tuple(f.get("sections") or [])
        if key and key not in seen:
            seen.add(key)
            parts.append(section_text(f))
    return "\n\n".join(parts)[:limit]


def _fact_issues(fact: dict | None, kind: str) -> list[str]:
    from ..protocol.facts import stated_qualifier

    if fact is None:
        return ["fact id is not a USABLE fact"]
    issues = [] if fact["kind"] == kind else [f"fact is {fact['kind']}, not {kind}"]
    if fact["value"].get("scale") != "proportion":
        issues.append("fact is not a proportion")
    if stated_qualifier(fact) in {"at least", "at most", "less than", "more than"}:
        issues.append(f"fact states a bound ({stated_qualifier(fact)}), not a rate")
    return issues


def _verify(model, items, by_id, section_text, votes, workers, protocol_text: str = "") -> None:
    jobs = [(it, v) for it in items for v in range(votes)]

    def run(job):
        it, vote = job
        fact = by_id.get(it.get("fact_id") or "")
        text = section_text(fact) if fact is not None and section_text else protocol_text
        evidence = (_q(fact.get("evidence")) if fact else it.get("quote") or it.get("evidence_text")) or ""
        payload = {"instructions": psc.VERIFY_INSTRUCTIONS + OUTCOME_VERIFY, "text": text or evidence or "(see rendering)",
                   "items": [{"item_id": "B1", "rendering": it["rendering"], "evidence": evidence, "related": []}]}
        if vote:
            payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
        try:
            out = model.extract("protocol_verify", psc.VERIFY, payload)
            return it, next((v for v in out.get("verdicts", []) if v.get("item_id") == "B1"), None)
        except Exception:  # noqa: BLE001 - a failed vote counts as no vote
            return it, None
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run, jobs))
    cast: dict[int, list[dict]] = {}
    for it, v in results:
        if v is not None and v.get("verdict") in {"FAITHFUL", "INCOMPLETE", "INCORRECT", "NOT_A_RULE"}:
            cast.setdefault(id(it), []).append(v)
    for it in items:
        got = cast.get(id(it), [])
        v = _majority(got, votes)
        it["verification"] = {"votes": [x["verdict"] for x in got], "reviewer_note": v["reviewer_note"] if v else None}
        it["semantic_status"] = v["verdict"] if v else "UNVERIFIED"


# ----------------------------------------------------------------------------- control EFS


def control_efs(bindings: dict, facts: list[dict]) -> dict:
    """The control arm's EFS model from the USABLE outcome bindings; unresolved when they do not determine it."""
    by_id = {f["fact_id"]: f for f in facts}
    usable = [it for it in bindings["items"] if it["status"] == "USABLE"]
    family = next((it for it in usable if it["role"] == "efs_model_family"), None)
    cure = next((it for it in usable if it["role"] == "control_cure_rate"), None)
    points = sorted(({"years": it["years"], "efs": by_id[it["fact_id"]]["value"]["value"], "fact_id": it["fact_id"]}
                     for it in usable if it["role"] == "control_efs_timepoint"), key=lambda p: p["years"])
    if family is None or family["family"] != "cure_model" or cure is None:
        return {"status": "UNRESOLVED", "reason": "the protocol's control EFS model or cure rate is not established"}
    pi = by_id[cure["fact_id"]]["value"]["value"]
    usable_points = [p for p in points if pi < p["efs"] < 1.0]
    if not usable_points:
        return {"status": "UNRESOLVED", "reason": "no stated time point above the cure rate to fix the failure rate"}
    anchor = usable_points[0]
    lam = -math.log((anchor["efs"] - pi) / (1.0 - pi)) / anchor["years"]
    checks = [{"years": p["years"], "stated": p["efs"], "model": pi + (1 - pi) * math.exp(-lam * p["years"])} for p in points]
    return {"status": "RESOLVED", "family": "cure_model", "cure_fraction": pi, "failure_rate_per_year": lam,
            "anchor": anchor, "facts": [cure["fact_id"]] + [p["fact_id"] for p in points], "fit_checks": checks,
            "family_quote": family["quote"],
            "note": "cure model S(t) = pi + (1 - pi) exp(-lambda t) with exponential failure times among non-cured patients"}


def efs_survival(t_years: np.ndarray, model: dict, hr: float = 1.0) -> np.ndarray:
    base = model["cure_fraction"] + (1 - model["cure_fraction"]) * np.exp(-model["failure_rate_per_year"] * t_years)
    return base ** hr


def sample_efs_years(n: int, model: dict, hr: float, rng: np.random.Generator) -> np.ndarray:
    """Event times (years) from S_B(t) = S_A(t)^hr by inversion; inf for patients who never fail."""
    pi, lam = model["cure_fraction"], model["failure_rate_per_year"]
    s = rng.random(n) ** (1.0 / hr)                       # S_A(T) for the sampled patient
    out = np.full(n, np.inf)
    fails = s > pi
    out[fails] = -np.log((s[fails] - pi) / (1.0 - pi)) / lam
    return out


# ----------------------------------------------------------------------------- effect prior from the asset


def _components(text: str) -> frozenset[str]:
    """Regimen components, lower-cased; placebo is no component (it is the absence of the added drug)."""
    parts = (c.strip().casefold() for c in re.split(r"\s\+\s|,", text or ""))
    return frozenset(c for c in parts if c and c != "placebo")


def add_on_radiotherapy_comparisons(index_path: Path) -> list[dict]:
    """V3 comparisons in which one arm is the other arm plus one or more added components, both containing
    radiotherapy, on an EFS-like endpoint; HR oriented so that < 1 favours the arm with the addition."""
    with open(index_path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    out = []
    for r in rows:
        if r["endpoint"] not in EFS_LIKE:
            continue
        t, c = _components(r["treatment"]), _components(r["comparator"])
        if not (any(RADIOTHERAPY.search(x) for x in t) and any(RADIOTHERAPY.search(x) for x in c)):
            continue
        hr = r["hr_population_posterior"]
        if c < t:
            added, sign = sorted(t - c), 1.0
        elif t < c:
            added, sign = sorted(c - t), -1.0
        else:
            continue
        log_hr = sign * math.log(hr["median"])
        se = (math.log(hr["q975"]) - math.log(hr["q025"])) / (2 * 1.959964)
        out.append({"fusion_id": r["fusion_id"], "disease": r["disease"], "endpoint": r["endpoint"], "added": added,
                    "log_hr_add_on": log_hr, "se": se, "hr_add_on": math.exp(log_hr)})
    return out


def random_effects_prior(comparisons: list[dict]) -> dict:
    """DerSimonian-Laird random-effects summary and the predictive distribution of a new comparison's log HR."""
    y = np.array([c["log_hr_add_on"] for c in comparisons])
    v = np.array([c["se"] ** 2 for c in comparisons])
    k = len(y)
    if k == 0:
        return {"status": "UNRESOLVED", "reason": "no add-on-to-radiotherapy comparisons in the asset"}
    w = 1 / v
    mu_fixed = float(np.sum(w * y) / np.sum(w))
    q = float(np.sum(w * (y - mu_fixed) ** 2))
    tau2 = max(0.0, (q - (k - 1)) / (np.sum(w) - np.sum(w ** 2) / np.sum(w))) if k > 1 else 0.0
    w_star = 1 / (v + tau2)
    mu = float(np.sum(w_star * y) / np.sum(w_star))
    se_mu = float(math.sqrt(1 / np.sum(w_star)))
    pred_sd = math.sqrt(tau2 + se_mu ** 2)
    return {"status": "RESOLVED", "comparisons": k, "mu_log_hr": mu, "se_mu": se_mu, "tau2": tau2, "predictive_sd": pred_sd,
            "hr_median": math.exp(mu), "hr_predictive_95": [math.exp(mu - 1.959964 * pred_sd), math.exp(mu + 1.959964 * pred_sd)],
            "note": ("indirect evidence: adding a drug to a radiotherapy-containing regimen in other (adult) cancers; no "
                     "comparison of the protocol's own experimental addition exists in the asset")}


# ----------------------------------------------------------------------------- adverse events from the asset


def nearest_class_signature(target: set[str], signatures: dict[str, int]) -> dict:
    """The asset class signature closest to the regimen's classes: fewest differing classes, preferring a subset of
    the regimen's classes (nothing the regimen does not contain), then the most event terms."""
    ranked = sorted(signatures.items(), key=lambda kv: (len(set(kv[0].split("+")) ^ target), not set(kv[0].split("+")) <= target, -kv[1]))
    sig, count = ranked[0]
    parts = set(sig.split("+"))
    return {"class_signature": sig, "event_terms": count, "missing_classes": sorted(target - parts), "extra_classes": sorted(parts - target)}


def asset_adverse_events(path: Path, signature: str, min_rate: float = 0.05) -> list[dict]:
    import pyarrow.parquet as pq

    rows = pq.read_table(path, columns=["class_signature", "event", "seriousness", "status", "population_rate"],
                         filters=[("class_signature", "=", signature)]).to_pylist()
    out = []
    for r in rows:
        if r["status"] != "PUBLISHED":
            continue
        rate = json.loads(r["population_rate"])
        if rate["median"] >= min_rate or r["seriousness"] == "serious" and rate["median"] >= min_rate / 5:
            out.append({"event": r["event"], "seriousness": r["seriousness"], "rate": rate["median"], "q025": rate["q025"], "q975": rate["q975"]})
    return sorted(out, key=lambda x: (x["seriousness"], -x["rate"]))


# ----------------------------------------------------------------------------- stage runner

EFFECT_GRID = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.1, 1.2, 1.3]


def design_alternatives(spec: dict) -> list[dict]:
    """Effect sizes the protocol's design assumes, as a hazard ratio on the whole EFS curve: for a stated change of
    the long-term (cure) rate from p0 to p1 under a proportional-hazards cure model, HR = ln(p1) / ln(p0)."""
    out = []
    for a in spec.get("analyses") or []:
        for e in a.get("effects") or []:
            text = _q(e) or ""
            pcts = [float(m) / 100 for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
            if len(pcts) >= 3 and 0 < pcts[1] < pcts[2] < 1:
                p0, p1 = pcts[1], pcts[2]
            elif len(pcts) == 2 and 0 < pcts[0] < pcts[1] < 1:
                p0, p1 = pcts
            else:
                continue
            hr = math.log(p1) / math.log(p0)
            if all(abs(hr - x["hr"]) > 1e-9 for x in out):
                out.append({"hr": hr, "control_long_term": p0, "experimental_long_term": p1, "wording": text})
    return out


def loss_to_follow_up(spec: dict) -> dict:
    for s in spec.get("sample_size") or []:
        if s["quantity"] == "censoring_rate" and s.get("value") is not None:
            text = _q(s.get("evidence")) or ""
            if "%" in text and re.search(r"\b(annual|per year|yearly|each year)\b", text, re.IGNORECASE):
                p = s["value"] / 100.0
                return {"status": "RESOLVED", "annual_probability": p, "rate_per_year": -math.log(1 - p), "wording": text}
    return {"status": "UNRESOLVED", "reason": "no annual censoring rate stated"}


def off_study_limit(spec: dict) -> dict | None:
    for d in spec.get("discontinuation_rules") or []:
        t = d.get("time_limit") or {}
        if d.get("scope") == "off_study" and t.get("days") and t.get("canonical_anchor") == "study_enrollment":
            return {"days": t["days"], "rule_id": d["rule_id"], "wording": _q(d.get("criterion"))}
    return None


def regimen_classes(spec: dict, arm_label: str, drug_classes: dict[str, str]) -> dict:
    classes, unmapped = set(), []
    for it in spec["interventions"]:
        arms = [(_q(a) or "").casefold() for a in it.get("arms") or []]
        if arms and not any(arm_label.casefold() in a or a in arm_label.casefold() for a in arms):
            continue
        if it.get("category") != "anticancer_drug":
            continue
        name = (it.get("canonical_agent") or _q(it.get("agent")) or "").replace("_", " ").casefold()
        cls = drug_classes.get(name) or drug_classes.get((_q(it.get("agent")) or "").casefold())
        if cls and cls != "other":
            classes.add(cls)
        else:
            unmapped.append(name)
    if spec.get("radiotherapy"):
        classes.add("radiotherapy_or_radiopharmaceutical")
    return {"classes": sorted(classes), "unmapped": sorted(set(unmapped))}


def build_outcome_model(model_client: Any, spec_lock: Path, facts_lock: Path, out_dir: Path, votes: int = 3,
                        v3_survival: Path = Path("data/simulation_parameters_v3/survival/fused_survival_index.jsonl"),
                        v2_toxicity: Path = Path("data/simulation_parameters_v2/toxicity/censored_toxicity_parameters.parquet"),
                        v2_classes: Path = Path("data/simulation_parameters_v2/hierarchy/drug_class_map.parquet")) -> dict:
    import pyarrow.parquet as pq

    from .population import _section_text_of
    from .recruitment import randomization_plan
    from .studyspec import load_facts, load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    facts, facts_record = load_facts(facts_lock)
    arms = randomization_plan(spec)["arms"]
    bindings = bind_outcomes(model_client, arms, facts, _section_text_of(facts_record), votes=votes, sample_size=spec.get("sample_size"))
    usable = {it["role"]: it for it in bindings["items"] if it["status"] == "USABLE" and it["role"].startswith("analysis_")}
    rule = usable.get("analysis_rule") or {}
    control_arm = next((it["arm_id"] for it in bindings["items"] if it["role"] == "control_arm" and it["status"] == "USABLE"), None)
    by_id = {f["fact_id"]: f for f in facts}
    toxicities = [{"event": it["event"], "grade": it["grade"], "applies_to": it["applies_to"], "arm_id": it["arm_id"],
                   "rate": by_id[it["fact_id"]]["value"]["value"], "upper": by_id[it["fact_id"]]["value"].get("upper"), "fact_id": it["fact_id"]}
                  for it in bindings["items"] if it["role"] == "toxicity_incidence" and it["status"] == "USABLE"]
    classes_map = {r["intervention"].casefold(): r["drug_class"] for r in pq.read_table(v2_classes).to_pylist()}
    signatures: dict[str, int] = {}
    for r in pq.read_table(v2_toxicity, columns=["class_signature"]).to_pylist():
        signatures[r["class_signature"]] = signatures.get(r["class_signature"], 0) + 1
    asset_aes = {}
    for a in arms:
        reg = regimen_classes(spec, a["label"], classes_map)
        near = nearest_class_signature(set(reg["classes"]), signatures)
        asset_aes[a["arm_id"]] = {**reg, **near, "events": asset_adverse_events(v2_toxicity, near["class_signature"]),
                                  "note": "adult registry evidence at treatment-class level, extrapolated to this protocol's population"}
    comparisons = add_on_radiotherapy_comparisons(v3_survival)
    alternatives = design_alternatives(spec)
    model = {
        "outcomes_version": OUTCOMES_VERSION,
        "inputs": {"studyspec": spec_record["files"]["studyspec.json"], "facts": facts_record["files"]["population_facts.json"]},
        "arms": arms, "control_arm_id": control_arm,
        "control_efs": control_efs(bindings, facts),
        "effect": {"grid_hr": sorted(set(EFFECT_GRID + [round(d["hr"], 4) for d in alternatives])),
                   "design_alternatives": alternatives,
                   "asset_prior": {**random_effects_prior(comparisons), "comparisons_used": comparisons,
                                   "decision": "insufficient evidence: shown for reference, not used (user decision 2026-09-27)"},
                   "definition": "S_experimental(t) = S_control(t) ** HR (proportional hazards on the whole EFS curve)"},
        "loss_to_follow_up": loss_to_follow_up(spec),
        "off_study_limit": off_study_limit(spec),
        "analysis_rule": {"evaluable_target": rule.get("value"), "min_followup_years": rule.get("years"),
                          "population": rule.get("population"), "wording": rule.get("quote"),
                          "excluded_share": (usable.get("analysis_exclusion") or {}).get("value")},
        "toxicities_protocol": toxicities, "adverse_events_asset": asset_aes,
        "bindings": bindings["items"],
        "assessment_timing": "EFS events are observed at their true time: detection at the next scheduled assessment is not applied",
        "efs_origin": "enrollment (= randomization): the protocol does not state the EFS time origin (user decision 2026-09-27)",
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outcome_model.json").write_text(json.dumps(model, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    summary = {k: model[k] for k in ("control_arm_id", "control_efs", "loss_to_follow_up", "off_study_limit", "analysis_rule")}
    summary.update({"design_alternatives": [round(d["hr"], 3) for d in alternatives], "protocol_toxicities": len(toxicities),
                    "asset_ae_signature": {k: v["class_signature"] for k, v in asset_aes.items()},
                    "bindings_usable": sum(it["status"] == "USABLE" for it in bindings["items"]), "bindings": len(bindings["items"])})
    return summary
