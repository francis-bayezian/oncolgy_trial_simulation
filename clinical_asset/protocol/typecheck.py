"""Static checking of a compiled StudySpec, without a language model.

Mechanical impossibilities are caught here, deterministically, before the independent verifier
judges meaning: malformed units and dimension conflicts, a variable used both as a number and as a
category, references to phases, agents or events that do not exist, dose rules without a trigger,
actions without values, 'may'-type wording compiled as a requirement, radiotherapy fraction
arithmetic that does not add up, time-to-event endpoints without origin/events/censoring, and
interim monitors missing a parameter.

check(spec) returns {item_id: [issue, ...]} plus a list of spec-level issues.
"""

import math
import re
from collections import defaultdict

from . import expressions as ex
from . import units

NUMERIC_KINDS = {"compare", "range", "window"}
CATEGORICAL_KINDS = {"category", "flag"}
MODAL_WORDING = re.compile(r"\b(may|can be|optional(ly)?|if desired|preferabl[ey]|strongly encouraged|encouraged|"
                           r"recommended|suggested|at the discretion)\b", re.IGNORECASE)


def _key(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").casefold()).strip()


def _q(x) -> str:
    return (x or {}).get("text") or "" if isinstance(x, dict) else ""


def _trees(spec: dict):
    """(item_id, component, tree) for every rule tree in the spec."""
    for c in spec["eligibility"]:
        yield c["criterion_id"], "eligibility", c.get("logic")
    for s in spec["stratification"]["strata"]:
        yield s["stratum_id"], "stratification", s.get("logic")
    for p in spec["treatment_phases"]:
        yield p["phase_id"], "treatment", (p.get("start_condition") or {}).get("logic")
    for it in spec["interventions"]:
        for part in ("condition", "stop_condition"):
            yield it["intervention_id"], "treatment", (it.get(part) or {}).get("logic")
        for rule in it.get("schedule_rules") or []:
            yield it["intervention_id"], "treatment", rule.get("condition")
    for course in spec.get("radiotherapy") or []:
        for t in course["targets"]:
            yield t["target_id"], "radiotherapy", t.get("condition")
    for m in spec["dose_modifications"]:
        yield m["rule_id"], "dose_modification", m.get("trigger")
        for step in m.get("steps") or []:
            yield m["rule_id"], "dose_modification", step.get("condition")
    for g in spec.get("grade_definitions") or []:
        for lv in g["levels"]:
            yield g["scale_id"], "grades", lv.get("criteria")


RADIATION_EVENTS = {"radiation", "radiation_fraction", "radiation_therapy", "radiotherapy"}


def treatment_gaps(phases: list[tuple[str, str]], administered: set[str], agents: set[str], dose_agents: set[str]) -> list[str]:
    """What the compiled treatment is missing: phases (id, name) with no administration (intervention
    or radiotherapy course) and agents that dose-modification rules name but that are never
    administered. Used on raw extractions (to trigger re-extraction) and on the built spec (gate)."""
    known = {a for a in agents if a} | RADIATION_EVENTS
    gaps = [f"treatment incomplete: phase {pid} {name!r} has no compiled administration" for pid, name in phases if pid not in administered]
    gaps += [f"treatment incomplete: dose-modification rules name {a!r} but no administration of it was compiled"
             for a in sorted(dose_agents) if a and not any(a in k or k in a for k in known)]
    return gaps


def check(spec: dict) -> tuple[dict[str, list[str]], list[str]]:
    issues: dict[str, list[str]] = defaultdict(list)
    global_issues: list[str] = []

    # ---- units and variable types
    dims: dict[str, set] = defaultdict(set)
    kinds: dict[str, set] = defaultdict(set)
    where: dict[str, set] = defaultdict(set)
    for item_id, _component, tree in _trees(spec):
        for leaf in ex.leaves(tree):
            var = leaf.get("variable")
            if not var:
                continue
            where[var].add(item_id)
            kind = leaf.get("kind")
            if kind in NUMERIC_KINDS or kind == "table":
                kinds[var].add("numeric")
            elif kind in CATEGORICAL_KINDS:
                kinds[var].add("categorical" if kind == "category" else "boolean")
            unit = leaf.get("unit")
            if unit and kind in {"compare", "range", "table"}:
                d = units.dimension(unit)
                if d == "INVALID":
                    issues[item_id].append(f"invalid unit {unit!r} on {var}")
                elif d not in {"UNKNOWN", "DIMENSIONLESS", "RELATIVE_TO_REFERENCE"}:
                    dims[var].add(d)
    for var, ds in dims.items():
        if len(ds) > 1:
            for item_id in where[var]:
                issues[item_id].append(f"variable {var} used with incompatible dimensions {sorted(ds)}")
    for var, ks in kinds.items():
        if "numeric" in ks and ks & {"categorical", "boolean"} and not var.startswith(("event:", "calendar:")):
            for item_id in where[var]:
                issues[item_id].append(f"variable {var} used both as a number and as a category")

    # ---- subgroup requirements compiled as unconditional
    for c in spec["eligibility"]:
        if c.get("kind") == "inclusion" and _subgroup_conjunction(c.get("logic")):
            issues[c["criterion_id"]].append(
                "requires one sex together with other conditions for every patient: a requirement that applies only to a "
                "subgroup ('female patients who ... must ...') is conditional (IF subgroup THEN requirement); as compiled it "
                "excludes every patient outside the subgroup")

    # ---- treatment references
    phase_ids = {p["phase_id"] for p in spec["treatment_phases"]}
    agents = {_key(_q(it.get("agent"))) for it in spec["interventions"]} | \
             {(it.get("canonical_agent") or "") for it in spec["interventions"]}
    agents |= {t.get("canonical_target") or "" for c in spec.get("radiotherapy") or [] for t in c["targets"]}
    agents.discard("")
    events = set(agents) | RADIATION_EVENTS
    for it in spec["interventions"]:
        iid = it["intervention_id"]
        if it.get("phase_id") not in phase_ids:
            issues[iid].append("intervention refers to no compiled phase")
        d = it.get("dose") or {}
        if d.get("unit") and units.dimension(d["unit"]) == "INVALID":
            issues[iid].append(f"invalid dose unit {d['unit']!r}")
        if it.get("category") in {"anticancer_drug", "growth_factor"} and d.get("value") is None:
            issues[iid].append("drug without a dose")
        for link in it.get("linked_events") or []:
            pre = link.get("canonical_prerequisite") or ""
            if pre and not any(pre in e or e in pre for e in events):
                issues[iid].append(f"linked event {pre!r} is not a compiled treatment event")
            scheduled = set((it.get("schedule") or {}).get("days") or [])
            if link.get("applies_to_days") and scheduled and not set(link["applies_to_days"]) <= scheduled:
                issues[iid].append(f"linked event applies to day(s) {link['applies_to_days']} outside the schedule {sorted(scheduled)}")
        evidence = _q(it.get("evidence"))
        if it.get("modality") in {"REQUIRED", "PROHIBITED"} and MODAL_WORDING.search(evidence) and \
                not (it.get("condition") or it.get("schedule_rules")):
            issues[iid].append("wording is permissive ('may', 'as needed', 'recommended') but compiled as REQUIRED")
    for m in spec["dose_modifications"]:
        rid = m["rule_id"]
        steps = m.get("steps") or []
        unconditional = all(s["action"]["type"] in {"no_modification", "none"} for s in steps if s["step_type"] == "ACTION")
        if m.get("trigger") is None and not unconditional:
            issues[rid].append("dose rule without a trigger")
        if not steps:
            issues[rid].append("dose rule without steps")
        for s in steps:
            a = s["action"]
            if a["type"] in {"reduce_percent", "reduce_to_dose", "set_dose"} and a.get("value") is None:
                issues[rid].append(f"step {s['order']}: {a['type']} without a value")
            if a.get("unit") and units.dimension(a["unit"]) == "INVALID":
                issues[rid].append(f"step {s['order']}: invalid unit {a['unit']!r}")
            if s["step_type"] == "MONITOR" and not s.get("frequency"):
                issues[rid].append(f"step {s['order']}: monitoring without a frequency")
            text = _q(s.get("evidence")) or _q(s.get("instruction"))
            if s.get("modality") in {"REQUIRED", "PROHIBITED"} and MODAL_WORDING.search(text):
                issues[rid].append(f"step {s['order']}: permissive wording compiled as {s['modality']}")

    # ---- radiotherapy arithmetic
    for course in spec.get("radiotherapy") or []:
        fd = (course.get("fraction_dose") or {}).get("value")
        total_fx = course.get("overall_fraction_count")
        primary_total = None
        assigned = 0.0
        conditional: list[float] = []
        for t in course["targets"]:
            tid = t["target_id"]
            dose = (t.get("total_dose") or {}).get("value")
            tfd = (t.get("fraction_dose") or {}).get("value") or fd
            n = t.get("fraction_count")
            if dose is None:
                issues[tid].append("radiotherapy target without a dose")
                continue
            if t.get("role") == "primary_field" and primary_total is None:
                primary_total = dose
            if n is not None and tfd and not math.isclose(n * tfd, dose, rel_tol=0.01) and not (t.get("cumulative") and primary_total):
                issues[tid].append(f"{n:g} fractions x {tfd:g} Gy != {dose:g} Gy")
            own = dose - primary_total if (t.get("cumulative") and primary_total is not None and t.get("role") != "primary_field") else dose
            boost = (t.get("boost_dose") or {}).get("value")
            own_tfd = (t.get("fraction_dose") or {}).get("value")
            if own_tfd and fd and not math.isclose(own_tfd, fd) and any(x and math.isclose(own_tfd, x, rel_tol=0.01) for x in (boost, own)):
                issues[tid].append(f"per-fraction dose {own_tfd:g} Gy equals the target's whole additional dose; "
                                   f"the course fraction is {fd:g} Gy (a boost or total dose recorded as a fraction?)")
            if tfd:
                implied = own / tfd
                if abs(implied - round(implied)) > 0.02:
                    issues[tid].append(f"{own:g} Gy is not a whole number of {tfd:g} Gy fractions")
                if n is not None and total_fx is not None and n == total_fx and not math.isclose(implied, n, rel_tol=0.01):
                    issues[tid].append("target given the course's overall fraction count although its dose implies otherwise")
            if t.get("condition") is None:  # every patient receives it: counts towards the course
                assigned += own / tfd if tfd else 0.0
            elif tfd:
                conditional.append(own / tfd)
        # The stated course count must be what some patient receives: every unconditional target plus
        # some subset of the conditional ones (conditional boosts differ between patients).
        reachable = {0.0}
        for extra in conditional[:16]:
            reachable |= {r + extra for r in reachable}
        if total_fx is not None and fd and assigned and not any(math.isclose(assigned + r, total_fx, abs_tol=0.5) for r in reachable):
            global_issues.append(f"radiotherapy course {course['course_id']}: the course states {total_fx:g} fractions, but no "
                                 f"patient's targets give that ({assigned:g} unconditional plus conditional boosts of "
                                 f"{sorted(round(c, 2) for c in conditional)})")

    # ---- endpoints, allocation, monitors
    for e in spec["endpoints"]:
        if e["type"] != "time_to_event":
            continue
        eid = e["endpoint_id"]
        if not e.get("time_origin") and not e.get("time_origin_unresolved_in_source"):
            issues[eid].append("time-to-event endpoint without a time origin")
        if not any(e.get("events") or []):
            issues[eid].append("time-to-event endpoint without event definitions")
        if not any(e.get("censoring") or []) and not e.get("censoring_unresolved_in_source"):
            issues[eid].append("time-to-event endpoint without censoring rules")
    open_arms = [a for a in spec["arms"] if a["status"] == "open"]
    if len(open_arms) >= 2 and not spec["randomization"].get("allocation") and not spec["randomization"].get("allocation_unresolved_in_source"):
        global_issues.append("randomized design without an allocation ratio")
    for m in spec.get("interim_analyses") or []:
        if m["status"] == "active" and m.get("monitor", {}).get("runtime_status") == "UNSUPPORTED_RULE_TYPE":
            issues[m["interim_id"]].append("active monitoring rule with missing parameters: " +
                                           ", ".join(m["monitor"].get("missing", [])))
    # ---- completeness of the treatment (an omission is not a fault of the items that were compiled)
    administered = {it.get("phase_id") for it in spec["interventions"]} | {c.get("phase_id") for c in spec.get("radiotherapy") or []}
    global_issues += treatment_gaps([(p["phase_id"], _q(p.get("name"))) for p in spec["treatment_phases"]], administered, agents,
                                    {m.get("canonical_agent") or _key(_q(m.get("agent"))) for m in spec["dose_modifications"]})
    return dict(issues), global_issues


def _subgroup_conjunction(tree: dict | None) -> bool:
    """True when the rule, knowing only a patient's sex, is certainly NOT met for one sex while it can be met for the
    other: a requirement that applies to one sex compiled as a condition every patient must meet. A rule that is
    nothing but a sex restriction is a genuine single-sex criterion and is not flagged."""
    if not tree or (tree.get("node") == "LEAF" and tree.get("variable") == "demographic:sex"):
        return False
    if not any(leaf.get("variable") == "demographic:sex" for leaf in ex.leaves(tree)):
        return False
    results = {sex: ex.evaluate(tree, {"demographic:sex": sex}) for sex in ("female", "male")}
    return any(r is False for r in results.values()) and not all(r is False for r in results.values())
