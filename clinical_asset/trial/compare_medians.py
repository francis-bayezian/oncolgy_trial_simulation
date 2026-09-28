"""Registry median time-to-event results against the locked control-arm prediction (any design).

The locked outcome model holds the control arm's curve (the protocol's own, or evidence-derived when the protocol
states none); its median is compared with the registry's primary median for the group whose title best matches the
control arm, together with the registry's confidence interval and the number of participants.
"""

import json
import math
import re
from pathlib import Path

DAY = 365.25


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (t or "").casefold())}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def predicted_control_median_months(model: dict) -> dict | None:
    c = model.get("control_efs") or {}
    if c.get("status") != "RESOLVED":
        return None
    pi, lam = c.get("cure_fraction", 0.0), c.get("failure_rate_per_year")
    if pi >= 0.5 or not lam:
        return {"median_months": None, "note": "the control curve never falls to 50% (cure fraction >= 0.5)"}
    t = -math.log((0.5 - pi) / (1 - pi)) / lam                   # S(t) = pi + (1 - pi) exp(-lam t) = 0.5
    ev = c.get("evidence") or {}
    return {"median_months": 12 * t, "ci95_months": ev.get("ci95"), "source": c.get("source") or c.get("family"),
            "subgroup": ev.get("subgroup"), "studies": ev.get("studies")}


def control_words(model: dict, safety: dict | None) -> set[str]:
    """Words naming the control arm: its label, plus its agents that not every arm has (the agents that distinguish
    it), from the locked safety stage's arm features."""
    label = next((a["label"] for a in model["arms"] if a["arm_id"] == model.get("control_arm_id")), "")
    words = _words(label)
    if safety:
        agents = {a["arm_id"]: {x["agent"] for x in ((a.get("safety_v3") or {}).get("features") or {}).get("agents", [])} for a in safety["arms"]}
        if agents.get(model.get("control_arm_id")):
            shared = set.intersection(*agents.values())
            for agent in agents[model["control_arm_id"]] - shared:
                words |= _words(agent)
    return words


def run(outcomes_lock: Path, registry_file: Path, registry_fetched_at: str, out_dir: Path, safety_lock: Path | None = None) -> dict:
    from .lock import load_locked, verify

    rec = verify(outcomes_lock)
    model = load_locked(outcomes_lock, "outcome_model.json")
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    pred = predicted_control_median_months(model)
    cwords = control_words(model, load_locked(safety_lock, "safety_results.json") if safety_lock else None)
    control_label = next((a["label"] for a in model["arms"] if a["arm_id"] == model.get("control_arm_id")), "")
    items = []
    for m in (registry.get("resultsSection") or {}).get("outcomeMeasuresModule", {}).get("outcomeMeasures", []):
        if m.get("type") != "PRIMARY" or (m.get("paramType") or "").upper() != "MEDIAN":
            continue
        unit = (m.get("unitOfMeasure") or "").casefold()
        factor = 1.0 if "month" in unit else 12 / 52.18 if "week" in unit else 12 / DAY if "day" in unit else 12.0 if "year" in unit else None
        groups = {g["id"]: g["title"] for g in m.get("groups", [])}
        denoms = {c["groupId"]: _num(c.get("value")) for d in m.get("denoms", []) for c in d.get("counts", [])}
        rows = []
        for c in m.get("classes", []):
            for cat in c.get("categories", []):
                for x in cat.get("measurements", []):
                    v = _num(x.get("value"))
                    rows.append({"group": groups.get(x["groupId"], x["groupId"]), "participants": denoms.get(x["groupId"]),
                                 "median_months": v * factor if v is not None and factor else None,
                                 "ci": [(_num(x.get("lowerLimit")) or None) and _num(x.get("lowerLimit")) * factor,
                                        (_num(x.get("upperLimit")) or None) and _num(x.get("upperLimit")) * factor]})
        ctl = max(rows, key=lambda r: len(_words(r["group"]) & cwords), default=None)
        if ctl is not None and not (_words(ctl["group"]) & cwords):
            ctl = None
        entry = {"measure": m["title"], "unit": m.get("unitOfMeasure"), "groups": rows, "control_group": ctl["group"] if ctl else None,
                 "predicted_control": pred}
        if ctl and pred and pred.get("median_months") and ctl["median_months"] is not None:
            entry["abs_error_months"] = abs(pred["median_months"] - ctl["median_months"])
            ci = pred.get("ci95_months")
            entry["registry_median_in_predicted_ci95"] = bool(ci and ci[0] <= ctl["median_months"] <= ci[1])
            lo, hi = ctl["ci"]
            entry["prediction_in_registry_ci"] = (lo is None or lo <= pred["median_months"]) and (hi is None or pred["median_months"] <= hi)
        items.append(entry)
    doc = {"predictions_locked_at": rec["locked_at"], "registry_fetched_at": registry_fetched_at, "order_verified": rec["locked_at"] < registry_fetched_at,
           "nct_id": registry["protocolSection"]["identificationModule"]["nctId"], "control_arm": control_label, "items": items}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "median_comparison.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    lines = ["# Median time-to-event against the registry", "",
             (f"Registry {doc['nct_id']}; locked {doc['predictions_locked_at']}; fetched {registry_fetched_at}; order verified: "
              f"{doc['order_verified']}. Control arm: {control_label} (matched by {sorted(cwords)})."), ""]
    for it in items:
        p = it["predicted_control"] or {}
        lines.append(f"- {it['measure']}: predicted control median {p.get('median_months') and round(p['median_months'], 2)} months "
                     f"(95% CI {p.get('ci95_months')}; {p.get('source')}); registry: " + "; ".join(
                         f"{g['group']} {g['median_months']} (CI {g['ci']}, n={g['participants']})" for g in it["groups"]))
        if "abs_error_months" in it:
            lines.append(f"  - control error {it['abs_error_months']:.2f} months; registry median inside our 95% CI: {it['registry_median_in_predicted_ci95']}; "
                         f"our median inside the registry CI: {it['prediction_in_registry_ci']}")
    (out_dir / "median_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc
