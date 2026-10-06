"""Milestone 5: the source population for a protocol.

Inputs are the locked StudySpec, the locked USABLE protocol facts and Simulation Parameter Asset V3.
Nothing else is used, and nothing is invented:

* Age comes from the V3 baseline generator, conditioned on the protocol's unconditional age eligibility.
* Sex, race and ethnicity come from the protocol's own projected enrollment table when it states one
  (joint counts by sex), otherwise from V3.
* A disease characteristic gets a distribution only when a USABLE fact states it and an independent
  binding step links that fact to a StudySpec variable: a model proposes each link, deterministic
  checks confirm the variable and category exist, and verifier votes (majority) judge it. A share above
  a threshold ('34% had residual tumor of at least 1.5 cm2') gives interval values, never invented
  point values.
* Every other variable is unknown (None) for every patient and is listed as unresolved.

Variables are sampled independently except race and ethnicity, which are sampled given sex when the
protocol states joint counts: no correlation is assumed that no source states.
"""

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from ..protocol import expressions as ex
from ..protocol import render
from ..protocol import schemas as psc
from ..protocol.compiler import _majority
from ..protocol.facts import stated_qualifier
from ..protocol.normalise import CANONICAL_VALUES, canonical_label

POPULATION_VERSION = "population-1.0.0"
DEMOGRAPHICS = ("demographic:sex", "demographic:race", "demographic:ethnicity")
V3_RACE = ("white", "black_or_african_american", "asian", "american_indian_or_alaska_native",
           "native_hawaiian_or_other_pacific_islander", "more_than_one_race", "unknown_or_not_reported")
V3_ETHNICITY = ("hispanic_or_latino", "not_hispanic_or_latino", "unknown_or_not_reported")

TEXT = {"type": "string"}
BINDINGS = psc.obj({"bindings": {"type": "array", "items": psc.obj({
    "fact_id": TEXT, "kind": psc.enum("share_of_category", "share_meeting_condition", "joint_count", "none"),
    "variable": TEXT, "category": TEXT, "variable_2": TEXT, "category_2": TEXT, "condition_item": TEXT, "reason": TEXT})}})
BINDINGS_INSTRUCTIONS = (
    "'facts' are quantitative statements a protocol makes about patients; 'variables' are the patient variables "
    "the protocol's compiled rules use, with the categories and conditions they appear in. For every fact decide "
    "whether it states the distribution of one of these variables in patients like those the trial enrolls, and "
    "return one binding per fact: kind 'share_of_category' when the fact is the share of patients whose variable "
    "has one of the listed categories (variable and category copied exactly from the list); 'share_meeting_condition' "
    "when the fact is the share of patients meeting a numeric condition on the variable (condition_item names a "
    "rule id where that condition appears, category repeats the condition wording of the fact); 'joint_count' when "
    "the fact is a count of patients having two demographic values at once, as in an enrollment table by sex and "
    "race or ethnicity (variable/category and variable_2/category_2, categories from the list; a row or column "
    "total is 'none'); otherwise 'none'. Accrual rates, outcome rates, toxicity rates, evaluability and totals are "
    "'none'. Never bind a fact to a variable it does not describe. reason: one short sentence."
)
BINDING_VERIFY = (
    " Here each item is a BINDING: a statement that a protocol fact gives the distribution of a patient variable used "
    "by the protocol's rules. The fact itself (its number, population and time) has already been verified against the "
    "protocol; judge ONLY the link. 'text' holds the variable (its categories and the rule conditions it appears in) "
    "and the protocol section the fact comes from, including its tables: for a table cell, use the table's row and "
    "column headers. Judge FAITHFUL if the fact describes that patient variable and that category, or that variable "
    "measured the same way for a condition binding; a condition binding may use a threshold that differs from the "
    "rule's threshold (for example 'at least 1.5' against a rule 'greater than 1.5'): the compiler evaluates that "
    "difference itself and it is not a reason to reject. INCORRECT if the fact describes another variable, another "
    "category or a different characteristic."
)


# ----------------------------------------------------------------------------- variable catalog


def variable_catalog(spec: dict) -> dict[str, dict]:
    """Every patient variable the StudySpec's eligibility and strata use, with its categories and conditions."""
    labels = {v["key"]: v["label"] for v in spec["variables"]}
    catalog: dict[str, dict] = {}
    items = [(c["criterion_id"], c.get("logic")) for c in spec["eligibility"]] + \
            [(s["stratum_id"], s.get("logic")) for s in spec["stratification"]["strata"]]
    for item_id, tree in items:
        for leaf in ex.leaves(tree):
            key = leaf.get("variable")
            if not key or key == "demographic:age" or key.startswith(("timing:", "event:", "count:", "calendar:", "grade:")):
                continue  # age comes from V3 conditioned on the age limits; simulator-owned variables are not patient traits
            entry = catalog.setdefault(key, {"label": labels.get(key, key), "kinds": set(), "categories": [], "conditions": []})
            entry["kinds"].add(leaf["kind"])
            for c in leaf.get("categories") or []:
                if c not in entry["categories"]:
                    entry["categories"].append(c)
            if leaf["kind"] in {"compare", "range"}:
                entry["conditions"].append({"item": item_id, "leaf": leaf, "text": render.rule(leaf, labels)})
    catalog.setdefault("demographic:sex", {"label": "sex", "kinds": {"category"}, "categories": [], "conditions": []})
    catalog.setdefault("demographic:race", {"label": "race", "kinds": {"category"}, "categories": [], "conditions": []})
    catalog.setdefault("demographic:ethnicity", {"label": "ethnicity", "kinds": {"category"}, "categories": [], "conditions": []})
    catalog["demographic:sex"]["categories"] = ["female", "male"]
    catalog["demographic:race"]["categories"] = list(V3_RACE) + ["other"]
    catalog["demographic:ethnicity"]["categories"] = list(V3_ETHNICITY)
    for entry in catalog.values():
        entry["kinds"] = sorted(entry["kinds"])
    return catalog


def age_class_bounds(spec: dict) -> tuple[float | None, float | None]:
    """Age limits in completed years, for the V3 population class: an exclusive whole-year upper limit ('less than
    22 years') admits ages up to 21 in completed years, the same population as 'up to 21 years'."""
    lo, hi = age_limits(spec)
    if hi is not None and not _upper_inclusive(spec) and float(hi).is_integer():
        hi -= 1
    return lo, hi


def _upper_inclusive(spec: dict) -> bool:
    for c in spec["eligibility"]:
        tree = c.get("logic") or {}
        nodes = [tree] if tree.get("node") == "LEAF" else tree.get("children", []) if tree.get("node") == "AND" else []
        for leaf in nodes:
            if c["kind"] == "inclusion" and leaf.get("variable") == "demographic:age" and leaf.get("upper") is not None:
                return leaf.get("upper_inclusive", True)
            if c["kind"] == "inclusion" and leaf.get("variable") == "demographic:age" and leaf.get("op") in {"<", "<="}:
                return leaf["op"] == "<="
    return True


def age_limits(spec: dict) -> tuple[float | None, float | None]:
    """The unconditional age eligibility: range or comparison leaves on age in inclusion criteria whose logic is
    a single leaf or an AND of leaves (age inside IF branches or tables is conditional and not used)."""
    lo, hi = None, None
    for c in spec["eligibility"]:
        tree = c.get("logic")
        if c["kind"] != "inclusion" or c.get("status") != "EXECUTABLE" or tree is None:
            continue
        nodes = [tree] if tree.get("node") == "LEAF" else tree.get("children", []) if tree.get("node") == "AND" else []
        for leaf in nodes:
            if leaf.get("node") != "LEAF" or leaf.get("variable") != "demographic:age":
                continue
            factor = {"year": 1.0, "month": 1 / 12, "day": 1 / 365.25, "week": 7 / 365.25}.get(leaf.get("unit") or "year")
            if factor is None:
                continue
            if leaf["kind"] == "range":
                if leaf.get("lower") is not None:
                    lo = max(lo or -math.inf, leaf["lower"] * factor)
                if leaf.get("upper") is not None:
                    hi = min(hi or math.inf, leaf["upper"] * factor)
            elif leaf["kind"] == "compare" and leaf["op"] in {">", ">="}:
                lo = max(lo or -math.inf, leaf["value"] * factor)
            elif leaf["kind"] == "compare" and leaf["op"] in {"<", "<="}:
                hi = min(hi or math.inf, leaf["value"] * factor)
    return lo, hi


# ----------------------------------------------------------------------------- binding facts to variables


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def bind_facts(model: Any, spec: dict, facts: list[dict], votes: int = 3, workers: int = 6,
               section_text: Any = None) -> list[dict]:
    """Link USABLE facts to StudySpec variables: proposal by the model, deterministic checks, verifier majority.
    `section_text(fact)` returns the protocol text (with tables) the fact was extracted from, for the reviewers."""
    catalog = variable_catalog(spec)
    candidates = [f for f in facts if f["kind"] in {"characteristic_distribution", "enrollment_projection"}]
    if not candidates:
        return []
    payload = {"instructions": BINDINGS_INSTRUCTIONS,
               "variables": [{"variable": k, "label": v["label"], "kinds": v["kinds"], "categories": v["categories"],
                              "conditions": [{"item": c["item"], "condition": c["text"]} for c in v["conditions"]]}
                             for k, v in sorted(catalog.items())],
               "facts": [{"fact_id": f["fact_id"], "fact": f["rendering"], "wording": _q(f.get("evidence")) or ""} for f in candidates]}
    out = model.extract("population_bindings", BINDINGS, payload)
    by_id = {f["fact_id"]: f for f in candidates}
    bindings = []
    for b in out.get("bindings", []):
        fact = by_id.get(b["fact_id"])
        if fact is None or b["kind"] == "none":
            continue
        binding = {**b, "issues": []}
        _check_binding(binding, fact, catalog)
        binding["rendering"] = _render_binding(binding, fact, catalog)
        bindings.append(binding)
    _verify_bindings(model, bindings, by_id, catalog, votes, workers, section_text)
    for b in bindings:
        b["status"] = "USABLE" if b.get("semantic_status") == "FAITHFUL" and not b["issues"] else "REVIEW_REQUIRED"
    return bindings


def _match_category(value: str, categories: list[str]) -> str | None:
    """The listed category a written value names (exact, canonical, or every word of the value in the category)."""
    if not value:
        return None
    key = canonical_label(value)
    for c in categories:
        if c.casefold() == value.casefold() or canonical_label(c) == key:
            return c
    words = set(re.findall(r"[a-z]+", value.casefold()))
    for c in categories:
        cwords = re.findall(r"[a-z]+", c.casefold())
        if words and all(any(cw.startswith(w) or w.startswith(cw) for cw in cwords) for w in words):
            return c
    sex = CANONICAL_VALUES.get("demographic:sex", {})
    return sex.get(value.strip().casefold()) if set(categories) == {"female", "male"} else None


def _check_binding(b: dict, fact: dict, catalog: dict) -> None:
    for var_field, cat_field in (("variable", "category"), ("variable_2", "category_2")):
        if var_field == "variable_2" and b["kind"] != "joint_count":
            continue
        var = b.get(var_field)
        if var not in catalog:
            b["issues"].append(f"{var_field} {var!r} is not a variable of the StudySpec")
            continue
        if b["kind"] == "share_meeting_condition":
            cond = next((c for c in catalog[var]["conditions"] if c["item"] == b.get("condition_item")), None)
            if cond is None:
                b["issues"].append(f"no condition on {var} in rule {b.get('condition_item')!r}")
            continue
        matched = _match_category(b.get(cat_field) or "", catalog[var]["categories"])
        if matched is None:
            b["issues"].append(f"{b.get(cat_field)!r} is not a category of {var}")
        else:
            b[cat_field] = matched
    if b["kind"] in {"share_of_category", "share_meeting_condition"} and fact["value"].get("scale") != "proportion":
        b["issues"].append("fact is not a share (no proportion or count out of a total)")
    bound = stated_qualifier(fact)
    if bound in {"at least", "at most", "less than", "more than"}:
        b["issues"].append(f"the fact states a bound ({bound}), not a value to sample from")
    if b["kind"] == "joint_count" and fact["value"].get("value") is None:
        b["issues"].append("fact has no count")
    if b["kind"] == "share_meeting_condition" and not b["issues"]:
        threshold = _threshold(_q(fact.get("category")) or b.get("category") or "")
        if threshold is None:
            b["issues"].append("the fact's condition has no parsable comparison")
        else:
            b["threshold"] = threshold


def _threshold(text: str) -> dict | None:
    """'residual tumor measuring at least 1.5 cm2' -> {'op': '>=', 'value': 1.5, 'unit': 'cm2'}."""
    spans = ex.number_spans(text)
    if not spans:
        return None
    start, value, end = spans[0]
    op = ex.parse_comparator(text[:start])
    if op is None:
        return None
    unit = ex.parse_unit(text[end:].strip().split(" ")[0]) if text[end:].strip() else None
    return {"op": op, "value": value, "unit": unit}


def _render_binding(b: dict, fact: dict, catalog: dict) -> str:
    label = catalog.get(b.get("variable"), {}).get("label", b.get("variable"))
    if b["kind"] == "joint_count":
        label2 = catalog.get(b.get("variable_2"), {}).get("label", b.get("variable_2"))
        return (f"fact {fact['fact_id']} is the number of patients with {label} = {b.get('category')!r} AND {label2} = "
                f"{b.get('category_2')!r} ({fact['rendering']})")
    if b["kind"] == "share_meeting_condition":
        cond = next((c["text"] for c in catalog.get(b.get("variable"), {}).get("conditions", []) if c["item"] == b.get("condition_item")), "?")
        return (f"fact {fact['fact_id']} is the share of patients whose {label} meets {b.get('category')!r}, the variable used in "
                f"the rule condition {cond!r} of {b.get('condition_item')} ({fact['rendering']})")
    return f"fact {fact['fact_id']} is the share of patients whose {label} ({b.get('variable')}) is {b.get('category')!r} ({fact['rendering']})"


def _verify_bindings(model, bindings, facts_by_id, catalog, votes, workers, section_text=None) -> None:
    jobs = [(b, v) for b in bindings for v in range(votes)]

    def run(job):
        b, vote = job
        fact = facts_by_id[b["fact_id"]]
        variables = [b.get("variable")] + ([b.get("variable_2")] if b["kind"] == "joint_count" else [])
        described = [{"variable": v, "label": catalog.get(v, {}).get("label"), "categories": catalog.get(v, {}).get("categories"),
                      "conditions": [c["text"] for c in catalog.get(v, {}).get("conditions", [])]} for v in variables]
        text = "VARIABLES: " + json.dumps(described, ensure_ascii=False)
        if section_text is not None:
            text += "\n\nPROTOCOL SECTION THE FACT COMES FROM:\n" + section_text(fact)
        payload = {"instructions": psc.VERIFY_INSTRUCTIONS + BINDING_VERIFY, "text": text,
                   "items": [{"item_id": b["fact_id"], "rendering": b["rendering"], "evidence": _q(fact.get("evidence")) or "", "related": []}]}
        if vote:
            payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
        try:
            out = model.extract("protocol_verify", psc.VERIFY, payload)
            return b, next((v for v in out.get("verdicts", []) if v.get("item_id") == b["fact_id"]), None)
        except Exception:  # noqa: BLE001 - a failed vote counts as no vote
            return b, None
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(run, jobs))
    cast: dict[int, list[dict]] = {}
    for b, v in results:
        if v is not None and v.get("verdict") in {"FAITHFUL", "INCOMPLETE", "INCORRECT", "NOT_A_RULE"}:
            cast.setdefault(id(b), []).append(v)
    for b in bindings:
        got = cast.get(id(b), [])
        v = _majority(got, votes)
        b["verification"] = {"votes": [x["verdict"] for x in got], "reviewer_note": v["reviewer_note"] if v else None}
        b["semantic_status"] = v["verdict"] if v else "UNVERIFIED"


# ----------------------------------------------------------------------------- population model and sampling


def population_model(spec: dict, facts: list[dict], bindings: list[dict], v3_parameters: dict) -> dict:
    """The distribution of every variable, with its source, from the USABLE bindings and V3."""
    facts_by_id = {f["fact_id"]: f for f in facts}
    usable = [b for b in bindings if b["status"] == "USABLE"]
    model: dict[str, dict] = {}
    lo, hi = age_limits(spec)
    model["demographic:age"] = {"source": "simulation_parameters_v3", "type": "age", "eligibility_years": [lo, hi],
                                "retrieval": v3_parameters.get("retrieval", {}).get("age_mean")}

    joint = [b for b in usable if b["kind"] == "joint_count" and "demographic:sex" in (b["variable"], b["variable_2"])]
    table: dict[str, dict[str, dict[str, float]]] = {}
    for b in joint:
        sex, (other_var, other_cat) = ((b["category"], (b["variable_2"], b["category_2"])) if b["variable"] == "demographic:sex"
                                       else (b["category_2"], (b["variable"], b["category"])))
        table.setdefault(other_var, {}).setdefault(sex, {})
        table[other_var][sex][other_cat] = table[other_var][sex].get(other_cat, 0.0) + facts_by_id[b["fact_id"]]["value"]["value"]
    sex_counts = None
    for var in ("demographic:ethnicity", "demographic:race"):
        if var in table and set(table[var]) == {"female", "male"}:
            counts = {s: sum(table[var][s].values()) for s in ("female", "male")}
            sex_counts = sex_counts or counts
            model[var] = {"source": "protocol_projection", "type": "categorical_given_sex",
                          "given_sex": {s: _normalise(table[var][s]) for s in ("female", "male")},
                          "facts": sorted(b["fact_id"] for b in joint if var in (b["variable"], b["variable_2"]))}
    if sex_counts:
        model["demographic:sex"] = {"source": "protocol_projection", "type": "categorical", "probabilities": _normalise(sex_counts),
                                    "counts": sex_counts}
    else:
        model["demographic:sex"] = {"source": "simulation_parameters_v3", "type": "categorical",
                                    "probabilities": {"female": v3_parameters["p_female"], "male": 1 - v3_parameters["p_female"]}}
    model.setdefault("demographic:race", {"source": "simulation_parameters_v3", "type": "categorical",
                                          "probabilities": v3_parameters["race_probabilities"]})
    model.setdefault("demographic:ethnicity", {"source": "simulation_parameters_v3", "type": "categorical",
                                               "probabilities": v3_parameters["ethnicity_probabilities"]})

    shares: dict[str, list[tuple[str, float, str]]] = {}
    for b in usable:
        if b["kind"] == "share_of_category" and not b["variable"].startswith("demographic:"):
            shares.setdefault(b["variable"], []).append((b["category"], facts_by_id[b["fact_id"]]["value"]["value"], b["fact_id"]))
    for var, entries in shares.items():
        best: dict[str, tuple[float, str]] = {}
        for cat, p, fid in entries:  # a category stated twice: the fact with an explicit count wins
            f = facts_by_id[fid]
            if cat not in best or (f["value"].get("numerator") is not None and facts_by_id[best[cat][1]]["value"].get("numerator") is None):
                best[cat] = (p, fid)
        total = sum(p for p, _ in best.values())
        if total > 1.0 + 1e-6:
            model[var] = {"source": "protocol_facts", "type": "unresolved", "reason": f"stated shares sum to {total:.3f} > 1",
                          "facts": sorted(fid for _, fid in best.values())}
            continue
        probs = {cat: p for cat, (p, _) in best.items()}
        if total < 1.0 - 1e-6:
            probs[None] = 1.0 - total  # patients whose category the facts do not state
        model[var] = {"source": "protocol_facts", "type": "categorical", "probabilities": probs,
                      "facts": sorted(fid for _, fid in best.values())}
    for b in usable:
        if b["kind"] == "share_meeting_condition" and b["variable"] not in model:
            f = facts_by_id[b["fact_id"]]
            model[b["variable"]] = {"source": "protocol_facts", "type": "threshold_share", "threshold": b["threshold"],
                                    "p_meets": f["value"]["value"], "facts": [b["fact_id"]],
                                    "population": _q(f.get("population")), "source_study": _q(f.get("source_study"))}
    catalog = variable_catalog(spec)
    model["_unresolved"] = sorted(k for k in catalog if k not in model and k != "demographic:age")
    return model


def _normalise(counts: dict) -> dict:
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()} if total else {}


def sample_population(model: dict, v3_patients: dict, n: int, seed: int) -> list[dict]:
    """Patients as {variable: value}; unresolved variables are absent (unknown)."""
    rng = np.random.default_rng(seed)
    patients = [{"patient_id": f"P{i + 1:06d}", "demographic:age": {"value": float(v3_patients["age"][i]), "unit": "year"}} for i in range(n)]
    sex = _draw(rng, model["demographic:sex"]["probabilities"], n)
    for p, s in zip(patients, sex, strict=True):
        p["demographic:sex"] = s
    for var in ("demographic:race", "demographic:ethnicity"):
        m = model[var]
        if m["type"] == "categorical_given_sex":
            for p in patients:
                p[var] = _draw(rng, m["given_sex"][p["demographic:sex"]], 1)[0]
        else:
            for p, v in zip(patients, _draw(rng, m["probabilities"], n), strict=True):
                p[var] = v
    for var, m in model.items():
        if var.startswith(("_", "demographic:")):
            continue
        if m["type"] == "categorical":
            for p, v in zip(patients, _draw(rng, m["probabilities"], n), strict=True):
                if v is not None:
                    p[var] = v
        elif m["type"] == "threshold_share":
            t = m["threshold"]
            meets = rng.random(n) < m["p_meets"]
            for p, yes in zip(patients, meets, strict=True):
                p[var] = _interval_for(t, bool(yes))
    return patients


def _interval_for(t: dict, meets: bool) -> dict:
    op, v = t["op"], t["value"]
    upper_side = op in {">", ">="}
    inside_lower_inclusive = op == ">="
    if meets == upper_side:
        return {"interval": [v, None], "lower_inclusive": inside_lower_inclusive if meets else op == "<", "unit": t["unit"]}
    return {"interval": [None, v], "upper_inclusive": (op == "<=") if meets else op == ">", "unit": t["unit"]}


def _draw(rng, probs: dict, n: int) -> list:
    keys = list(probs)
    p = np.array([probs[k] for k in keys], dtype=float)
    p = p / p.sum()
    idx = rng.choice(len(keys), size=n, p=p)
    return [keys[i] for i in idx]


# ----------------------------------------------------------------------------- stage runner


def protocol_query(spec: dict):
    """The Simulation Parameter Asset V3 baseline query of a protocol: age limits and age class, and the disease family
    of its condition (the evidence build's disease mapper, cached; 'other' leaves the family unknown)."""
    from ..planning.operational import condition_family
    from ..spa3.baseline import age_class
    from ..spa3.protocol import ProtocolQuery

    lo, hi = age_limits(spec)
    cond = spec["metadata"].get("condition")
    family = condition_family(" ".join(((cond.get("text") if isinstance(cond, dict) else cond) or "").split()))[0]
    return ProtocolQuery(min_age=lo, max_age=hi, sex="ALL", age_class=age_class(*age_class_bounds(spec)),
                         disease_family=None if family == "other" else family)


def age_class_mixture(generator: Any, query: Any) -> list[tuple[str, float]]:
    """The age classes to draw ages from (lesson L020). With a stated age limit the class follows from it. With none,
    the class is UNKNOWN, not 'mixed children and adults': ages are a mixture over the classes in proportion to the
    V3 studies of the protocol's disease family in each class (all studies when the family has none). Querying the
    MIXED class instead had dropped the disease family and drawn generic ages (mean 38 for a urothelial trial)."""
    model = (getattr(generator, "models", None) or {}).get("age_mean")
    if query.min_age is not None or query.max_age is not None or model is None:
        return [(query.age_class, 1.0)]
    nodes = model.nodes
    counts = {p[0]: n["studies"] for p, n in nodes.items() if query.disease_family and len(p) == 2 and p[1] == query.disease_family}
    if not counts:
        counts = {p[0]: n["studies"] for p, n in nodes.items() if len(p) == 1}
    total = sum(counts.values())
    return sorted(((c, k / total) for c, k in counts.items() if k), key=lambda x: -x[1])


def mixed_ages(generator: Any, query: Any, mixture: list[tuple[str, float]], n: int, seed: int) -> list[float]:
    """n ages drawn from the age-class mixture (largest-remainder allocation), in a seeded random order."""
    from dataclasses import replace

    raw = [w * n for _, w in mixture]
    alloc = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: alloc[i] - raw[i])[: n - sum(alloc)]:
        alloc[i] += 1
    ages: list[float] = []
    for (cls, _), k in zip(mixture, alloc, strict=True):
        if k:
            q = replace(query, age_class=cls)
            ages += generator.sample(generator.parameters(q, None, True, seed), k, seed)["age"]
    order = np.random.default_rng(seed + 31).permutation(len(ages))
    return [float(ages[i]) for i in order]


def build_population(model_client: Any, spec_lock: Path, facts_lock: Path, out_dir: Path, n: int = 10000, seed: int = 20260927,
                     votes: int = 3, generator: Any = None) -> dict:
    from ..spa3.protocol import BaselineGenerator
    from .studyspec import load_facts, load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    facts, facts_record = load_facts(facts_lock)
    generator = generator or BaselineGenerator.load()
    query = protocol_query(spec)
    params = generator.parameters(query, None, True, seed)
    v3 = generator.sample(params, n, seed)
    mixture = age_class_mixture(generator, query)
    if mixture != [(query.age_class, 1.0)]:
        v3["age"] = mixed_ages(generator, query, mixture, n, seed)
    bindings = bind_facts(model_client, spec, facts, votes=votes, section_text=_section_text_of(facts_record))
    model = population_model(spec, facts, bindings, params)
    model["demographic:age"]["age_class_mixture"] = [{"age_class": c, "weight": round(w, 4)} for c, w in mixture]
    patients = sample_population(model, v3, n, seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = _summary(model, patients, bindings)
    doc = {"population_version": POPULATION_VERSION, "seed": seed, "n": n,
           "inputs": {"studyspec": spec_record["files"]["studyspec.json"], "facts": facts_record["files"]["population_facts.json"],
                      "simulation_parameters": "simulation_parameters_v3"},
           "model": _jsonable(model), "bindings": bindings, "summary": summary}
    (out_dir / "population_model.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    with open(out_dir / "population.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in patients)
    (out_dir / "population_report.md").write_text(_report(doc), encoding="utf-8")
    return summary


def _jsonable(model: dict) -> dict:
    out = {}
    for k, v in model.items():
        if isinstance(v, dict) and "probabilities" in v:
            v = {**v, "probabilities": {("__not_stated__" if c is None else c): p for c, p in v["probabilities"].items()}}
        out[k] = v
    return out


def _summary(model: dict, patients: list[dict], bindings: list[dict]) -> dict:
    n = len(patients)
    known = {k: sum(1 for p in patients if p.get(k) is not None) / n for k in model if not k.startswith("_")}
    ages = np.array([p["demographic:age"]["value"] for p in patients])
    return {"patients": n, "age_mean": float(ages.mean()), "age_range": [float(ages.min()), float(ages.max())],
            "share_known": known, "unresolved_variables": len(model["_unresolved"]),
            "bindings": len(bindings), "usable_bindings": sum(b["status"] == "USABLE" for b in bindings),
            "sources": {k: v["source"] for k, v in model.items() if not k.startswith("_")}}


def _report(doc: dict) -> str:
    s, m = doc["summary"], doc["model"]
    lines = [f"# Source population ({doc['population_version']})", "",
             (f"{s['patients']} simulated patients (seed {doc['seed']}); mean age {s['age_mean']:.1f} years, range "
              f"{s['age_range'][0]:.1f}-{s['age_range'][1]:.1f}."), "",
             "## Variables with a distribution", ""]
    for k, v in m.items():
        if k.startswith("_"):
            continue
        detail = v.get("probabilities") or v.get("given_sex") or v.get("threshold") or v.get("eligibility_years")
        facts = f" facts {v['facts']}" if v.get("facts") else ""
        lines.append(f"- **{k}** from {v['source']} ({v['type']}){facts}: {json.dumps(detail, default=str)[:300]}"
                     + (f"; p_meets {v['p_meets']:.3f} ({v.get('source_study') or v.get('population')})" if v.get("p_meets") is not None else ""))
    lines += ["", f"## Unresolved variables ({len(m['_unresolved'])}): unknown for every patient", ""]
    lines += [f"- {k}" for k in m["_unresolved"]]
    lines += ["", "## Fact bindings", ""]
    for b in doc["bindings"]:
        lines.append(f"- [{b['status']}] votes {b['verification']['votes']}: {b['rendering'][:260]}"
                     + (f" - issues: {b['issues']}" if b["issues"] else ""))
    return "\n".join(lines) + "\n"


def _section_text_of(facts_record: dict):
    """The protocol text (with tables) a fact was extracted from, read from the PDF the facts lock names; the PDF's
    checksum must match the lock."""
    from ..protocol.ingest import extract
    from .lock import LockError, resolve, sha256_file

    pdf = facts_record["inputs"]["protocol_pdf"]
    path = resolve(pdf["path"])                        # a protocol renamed since the facts were locked (alias manifest)
    if sha256_file(path) != pdf["sha256"]:
        raise LockError(f"{path} differs from the PDF the facts were locked from")
    doc = extract(path)

    def text(fact: dict) -> str:
        parts = []
        for number in fact.get("sections") or []:
            s = doc.section(number)
            if s is not None:
                parts.append(f"{s.number} {s.title}\n{s.text()}")
                parts.extend("TABLE: " + json.dumps(t.rows, ensure_ascii=False) for t in s.tables)
        return "\n".join(parts)[:60000]
    return text
