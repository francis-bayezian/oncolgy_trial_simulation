"""Disease-defining variables of the screening pool from the evidence (L062).

The eligibility rules test the target disease's own characteristics: diagnosis and histology, stage and metastatic
sites, molecular subtype and biomarkers. When no protocol fact gives them a distribution, every generated patient used to
be unknown for them and screening could not test them. Here each such variable, unknown for every patient, gets values
from the registry baseline tables of trials of the same disease (the same retrieval and category mapping as the
subgroup prevalences, L039): its levels are the protocol's own categories plus 'other' (a flag: present / absent), and
the shares are those of enrolled participants of comparable trials (same family and phase, else family, else all
oncology). Without such evidence the variable stays unknown and the reason is recorded: no equal-share assumption.

Caveat recorded with every variable: registry baseline tables describe ENROLLED participants of other trials, an
approximation of who is referred to screening for the disease.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..protocol import expressions as ex

DISEASE_RULE_TYPES = {"diagnosis", "disease_stage", "histology", "molecular_subtype", "biomarker"}
FLAG_RULE_TYPES = {"disease_stage", "histology", "molecular_subtype", "biomarker"}     # a 'diagnosis' flag is a comorbidity
MIN_TRIALS = 5                 # a share needs at least this many comparable trials' baseline tables
CAVEAT = "registry baseline tables of enrolled participants of comparable trials (an approximation of the referred population)"


def candidates(spec: dict) -> list[dict]:
    """Executable eligibility leaves on disease-defining variables, one factor per variable."""
    labels = {v["key"]: v.get("label") or v["key"] for v in spec.get("variables") or []}
    by_var: dict[str, dict] = defaultdict(lambda: {"categories": [], "kinds": set(), "criteria": set(), "rule_types": set()})
    for c in spec.get("eligibility") or []:
        if not c.get("logic"):
            continue
        leaves = ex.leaves(c["logic"])
        if c.get("kind") == "exclusion" and any(x.get("rule_type") == "diagnosis" for x in leaves):
            continue                      # an excluded other condition (another cancer, an infection): not the target disease
        for leaf in leaves:
            rt, k, var = leaf.get("rule_type"), leaf.get("kind"), leaf.get("variable")
            if not var or leaf.get("status") != "EXECUTABLE" or rt not in DISEASE_RULE_TYPES:
                continue
            if k == "flag" and rt not in FLAG_RULE_TYPES:
                continue
            if k not in ("category", "flag"):
                continue
            d = by_var[var]
            d["kinds"].add(k)
            d["criteria"].add(c["criterion_id"])
            d["rule_types"].add(rt)
            d["categories"] += [x for x in leaf.get("categories") or [] if x not in d["categories"]]
    out = []
    for var, d in by_var.items():
        if d["kinds"] == {"flag"}:
            levels, kind = ["present", "absent"], "flag"
        elif "category" in d["kinds"] and d["categories"]:
            levels, kind = d["categories"] + ["other"], "category"
        else:
            continue
        out.append({"key": var, "kind": kind, "levels": levels, "criteria": sorted(d["criteria"]), "rule_types": sorted(d["rule_types"]),
                    "text": f"{labels.get(var, var)} ({', '.join(levels)})"})
    return out


def generate(model, spec: dict, patients: list[dict], family: str | None, phase: str | None, exclude: set[str], rng) -> dict:
    """Give every disease-defining variable that no patient has a value for values from the registry evidence."""
    from . import subgroup_evidence as sge

    known = {k for p in patients[:2000] for k in p}
    done, unresolved = [], []
    for f in candidates(spec):
        if f["key"] in known:
            continue
        factor = {"key": f["key"], "text": f["text"], "levels": list(f["levels"])}
        prev = sge.prevalence(model, factor, family, phase, exclude)
        if prev.get("status") != "RESOLVED" or (prev.get("trials") or 0) < MIN_TRIALS:
            unresolved.append({**f, "reason": prev.get("source") if prev.get("status") != "RESOLVED"
                               else f"only {prev.get('trials')} trials report it (at least {MIN_TRIALS} needed)"})
            continue
        levels = prev["levels"]
        draws = rng.choice(len(levels), size=len(patients), p=np.array(prev["p"]) / sum(prev["p"]))
        for p, i in zip(patients, draws, strict=True):
            lv = levels[int(i)]
            p[f["key"]] = {"value": lv == "present", "unit": None} if f["kind"] == "flag" else lv
        done.append({**f, "levels": levels, "p": prev["p"], "trials": prev.get("trials"), "participants": prev.get("participants"),
                     "trial_range_10_90": prev.get("trial_range_10_90"), "source": f"{prev['source']}; {CAVEAT}"})
    return {"generated": done, "unresolved": unresolved}
