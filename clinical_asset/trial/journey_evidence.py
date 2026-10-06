"""Evidence lookups for the patient journey, each returning a value with its provenance.

* withdrawal: the share of participants who left for a reason other than progression, death or toxicity (subject
  decision, loss to follow-up, physician decision), pooled over trials of the same disease family and phase from the
  registry participant flow (random effects on the logit scale); broader pools only when fewer than MIN_TRIALS trials;
* progression: the locked outcome model's control curve when resolved, else the arm's subgroup median progression-free
  survival from the evidence (clinical_asset.trial.subgroups), exponential (assumption A7).
"""

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from .patient_state import sourced
from .predictive import from_normal

EVIDENCE = Path("data/evidence_journey_v1")
MIN_TRIALS = 5
OTHER_WITHDRAWAL = ("withdrawal_by_subject", "lost_to_follow_up", "physician_decision")


@lru_cache(maxsize=1)
def _mesh_map() -> dict:
    f = Path("data/spa_work/mesh_disease_families.json")
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


@lru_cache(maxsize=1)
def _disposition() -> list[dict]:
    import pyarrow.parquet as pq

    from ..planning.operational import family_of_terms

    rows = pq.read_table(EVIDENCE / "disposition.parquet", columns=["nct_id", "phase", "condition_mesh", "period_index", "group_title",
                                                                    "started", "reason", "count"]).to_pylist()
    from ..cutoff import excluded

    drop = excluded()
    mapping = _mesh_map()
    per: dict = {}
    for r in rows:
        if r["period_index"] != 0 or not r["started"] or r["nct_id"] in drop:
            continue                                  # the first period: participants who started the trial
        g = per.setdefault((r["nct_id"], r["group_title"]), {"nct_id": r["nct_id"], "phase": r["phase"], "mesh": r["condition_mesh"],
                                                             "started": r["started"], "by_reason": {}})
        if r["reason"] and r["count"]:
            g["by_reason"][r["reason"]] = g["by_reason"].get(r["reason"], 0.0) + r["count"]
    fam: dict = {}
    out = []
    for g in per.values():
        if g["mesh"] not in fam:
            fam[g["mesh"]] = family_of_terms([t for t in (g["mesh"] or "").split("; ") if t], mapping)[0]
        out.append({**g, "family": fam[g["mesh"]]})
    return out


def pool_logit(groups: list[dict]) -> dict:
    """DerSimonian-Laird pooled proportion on the logit scale, with its 95% CI and the 80% range for a single new trial."""
    y, v = [], []
    for g in groups:
        k, n = min(g["other"], g["started"]), g["started"]
        y.append(math.log((k + 0.5) / (n - k + 0.5)))
        v.append(1 / (k + 0.5) + 1 / (n - k + 0.5))
    y, v = np.array(y), np.array(v)
    w = 1 / v
    mu = float(np.sum(w * y) / np.sum(w))
    q = float(np.sum(w * (y - mu) ** 2))
    tau2 = max(0.0, (q - (len(y) - 1)) / (np.sum(w) - np.sum(w ** 2) / np.sum(w))) if len(y) > 1 else 0.0
    ws = 1 / (v + tau2)
    mu = float(np.sum(ws * y) / np.sum(ws))
    se = math.sqrt(1 / np.sum(ws))
    inv = lambda x: 1 / (1 + math.exp(-x))  # noqa: E731
    half = 1.2816 * math.sqrt(se ** 2 + tau2)
    return {"estimate": inv(mu), "ci95": [inv(mu - 1.96 * se), inv(mu + 1.96 * se)], "single_trial_80": [inv(mu - half), inv(mu + half)],
            "single_trial_percentiles": from_normal(mu, math.sqrt(se ** 2 + tau2), inv),
            "tau_logit": math.sqrt(tau2), "groups": len(y), "trials": len({g["nct_id"] for g in groups}),
            "participants": int(sum(g["started"] for g in groups))}


def disposition_probability(reasons: tuple[str, ...], what: str, family: str | None, phase: str | None) -> dict:
    """The pooled share of starters who left the first period for one of `reasons` (family and phase, then family,
    then phase, then all oncology: the first pool with MIN_TRIALS trials)."""
    rows = [{**g, "other": sum(g["by_reason"].get(k, 0.0) for k in reasons)} for g in _disposition()]
    for label, sel in ((f"{family}, {phase}", [g for g in rows if g["family"] == family and g["phase"] == phase]),
                       (f"{family}", [g for g in rows if g["family"] == family]),
                       (f"all oncology, {phase}", [g for g in rows if g["phase"] == phase]),
                       ("all oncology", rows)):
        if len({g["nct_id"] for g in sel}) >= MIN_TRIALS:
            p = pool_logit(sel)
            out = sourced(p["estimate"], "evidence", f"registry participant flow ({label}): {what}; {p['trials']} trials, "
                          f"{p['participants']} participants")
            out["detail"] = p
            return out
    return sourced(None, "unsupported", "no registry disposition evidence")


def withdrawal_probability(family: str | None, phase: str | None) -> dict:
    return disposition_probability(OTHER_WITHDRAWAL, "left by subject decision, loss to follow-up or physician decision", family, phase)


def ae_discontinuation_probability(family: str | None, phase: str | None) -> dict:
    """Leaving treatment for an adverse event (lesson L021: the journey had no toxicity discontinuation beyond the
    protocol's own rules, which the generated grades rarely trigger)."""
    return disposition_probability(("adverse_event",), "left for an adverse event", family, phase)


def death_probability(family: str | None, phase: str | None) -> dict:
    """Death recorded as the reason for leaving the first period. Registry flow periods usually span treatment AND
    follow-up, so this is death at any time in the study period, drawn over the simulated horizon (L021)."""
    return disposition_probability(("death",), "died during the study period", family, phase)


def registry_phase(spec: dict) -> str | None:
    """The StudySpec's phase in registry form ('Phase 3' -> PHASE3, 'Phase 1/2' -> PHASE1+PHASE2)."""
    import re as _re

    ph = (spec.get("metadata") or {}).get("phase")
    text = ph.get("text") if isinstance(ph, dict) else ph
    nums = sorted(set(_re.findall(r"[1-4]", str(text or ""))))
    return "+".join(f"PHASE{n}" for n in nums) or None


@lru_cache(maxsize=1)
def _screening() -> list[dict]:
    import pyarrow.parquet as pq

    from ..cutoff import excluded
    from ..planning.operational import family_of_terms

    drop, mapping = excluded(), _mesh_map()
    out = []
    for r in pq.read_table(EVIDENCE / "screening.parquet", columns=["nct_id", "phase", "condition_mesh", "screened", "enrolled"]).to_pylist():
        s, e = r["screened"], r["enrolled"]
        if r["nct_id"] in drop or not s or not e or not 0 < e <= s <= 20 * e:
            continue                                   # implausible pairs (a screened count below enrolment) are not used
        out.append({"nct_id": r["nct_id"], "phase": r["phase"], "started": s, "other": e,
                    "family": family_of_terms([t for t in (r["condition_mesh"] or "").split("; ") if t], mapping)[0]})
    return out


def screen_pass_rate(family: str | None, phase: str | None) -> dict:
    """The share of screened patients who enrolled, from trials whose registry recruitment text states both counts
    (random effects on the logit scale; family and phase, then family, then phase, then all oncology)."""
    rows = _screening()
    for label, sel in ((f"{family}, {phase}", [g for g in rows if g["family"] == family and g["phase"] == phase]),
                       (f"{family}", [g for g in rows if g["family"] == family]),
                       (f"all oncology, {phase}", [g for g in rows if g["phase"] == phase]),
                       ("all oncology", rows)):
        if len({g["nct_id"] for g in sel}) >= MIN_TRIALS:
            p = pool_logit(sel)
            out = sourced(p["estimate"], "evidence", f"registry recruitment details stating screened and enrolled counts ({label}; "
                          f"{p['trials']} trials, {p['participants']} screened)")
            out["detail"] = p
            return out
    return sourced(None, "unsupported", "no registry screening counts")


def _tokens(text: str) -> set[str]:
    import re as _re

    return set(_re.findall(r"[a-z0-9]+", (text or "").casefold()))


def _arm_text(spec: dict, arm_id: str | None) -> str:
    """The arm's label and description plus every intervention arm reference naming it ('Arm 1 (once-weekly KRd 56 mg/m2)')."""
    def t(x):
        return x.get("text") if isinstance(x, dict) else x
    from .arms import ArmResolver

    arm = next((a for a in spec.get("arms") or [] if a["arm_id"] == arm_id), None)
    if not arm:
        return ""
    resolver = ArmResolver(spec)
    refs = {t(r) or "" for i in spec.get("interventions") or [] for r in i.get("arms") or []}
    return " ".join([t(arm.get("label")) or "", t(arm.get("description")) or ""] + sorted(r for r in refs if arm_id in (resolver.resolve(r) or [])))


def same_regimen(label: str | None, spec: dict, arm_id: str | None) -> bool:
    """A cited figure is for THIS arm's regimen (lessons L018, L029): when its wording names agents of the protocol,
    they must be exactly the arm's anticancer agents (a component's figure, e.g. one drug of a combination, is not the
    regimen's); wording that names no agent (an abbreviation such as 'XYz') must consist of words of the arm's own text."""
    from .arms import ArmResolver, _agent, words

    if not label or not _tokens(label):
        return False
    r = ArmResolver(spec)
    text = words(label)
    named = {a for a in r.agents if any(text[i:i + len(words(a))] == words(a) for i in range(len(text)))}
    if named:
        mine = {_agent(it) for it in r.anticancer if arm_id and r.applies_to(it.get("arms"), arm_id)}
        return named == mine
    return _tokens(label) <= _tokens(_arm_text(spec, arm_id))


def cited_progression(facts: list[dict] | None, spec: dict, arm_id: str | None) -> dict | None:
    """A median progression-free survival the protocol cites for THIS arm's regimen (a USABLE historical-study fact whose
    category names only words of the arm's own text, e.g. 'KRd' for 'Arm 2 (twice-weekly KRd 27 mg/m2)')."""
    best = None
    for f in facts or []:
        val = f.get("value") or {}
        cat = f.get("category")
        cat = cat.get("text") if isinstance(cat, dict) else cat
        unit = (val.get("unit") or "").casefold()
        if (f.get("source") == "historical_study" and f.get("canonical_variable") == "progression_free_survival" and unit.startswith("month")
                and val.get("value") and same_regimen(cat, spec, arm_id)):
            best = best or (float(val["value"]), f["fact_id"], cat)
    return best


def progression_model(outcome_model: dict, arm_features: dict | None, spec: dict, facts: list[dict] | None = None,
                      arm_id: str | None = None) -> dict:
    c = outcome_model.get("control_efs") or {}
    if c.get("status") == "RESOLVED":
        from_evidence = "evidence" in str(c.get("source") or c.get("family") or "")
        return sourced({"cure_fraction": c.get("cure_fraction") or 0.0, "rate_per_year": c["failure_rate_per_year"]},
                       "evidence" if from_evidence else "protocol",
                       f"locked outcome model control curve: {c.get('family')}" + (f" ({c['source']})" if c.get("source") else ""))
    cited = cited_progression(facts, spec, arm_id)
    if cited:                      # the protocol's cited figure for the same regimen beats a cross-regimen evidence mixture (L018)
        median, fid, cat = cited
        return sourced({"cure_fraction": 0.0, "rate_per_year": math.log(2) / (median / 12)}, "protocol",
                       f"protocol-cited median progression-free survival {median:g} months for {cat} (fact {fid}), exponential",
                       assumption="A7_progression_exponential")
    if arm_features:
        from .subgroups import arm_age_group, estimate_median

        phase = registry_phase(spec)
        est = estimate_median("progression_free_survival", arm_features.get("disease_family", ""), arm_features.get("classes", []),
                              [a["agent"] for a in arm_features.get("agents", [])], arm_age_group(spec), phase)
        if est.get("status") == "RESOLVED" and est.get("median_months"):
            out = sourced({"cure_fraction": 0.0, "rate_per_year": math.log(2) / (est["median_months"] / 12)}, "assumption",
                          f"evidence median progression-free survival {est['median_months']:.1f} months ({est.get('subgroup')}, "
                          f"{est.get('studies')} studies), exponential", assumption="A7_progression_exponential")
            out["detail"] = {k: v for k, v in est.items() if k != "status"}
            return out
        return sourced(None, "unsupported", est.get("reason", "no progression evidence for this arm"))
    return sourced(None, "unsupported", "no progression model and no arm features")
