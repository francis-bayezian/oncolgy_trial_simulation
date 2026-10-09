"""Blind comparison of locked ratio-noninferiority predictions (ratio_ni engine) with the registry's posted results.

Each engine analysis is matched to the registry outcome measure with a ratio analysis (geometric-mean ratio or any
'ratio' parameter) whose title shares the most tokens with the analysis' endpoint. Scored per endpoint:
- the noninferiority conclusion: predicted probability of success at the design ratio against the registry's
  conclusion (lower confidence limit above the margin);
- the observed ratio against the predicted distribution of the estimate at the design ratio (percentile, inside the
  80% interval) - the design ratio is the protocol's assumption, so this scores the protocol's assumption as simulated;
- variability: the log-scale SD assumed (from the power statement; from the registry) against the registry's
  per-arm geometric CVs (pooled on the log scale).
Order (predictions locked before the registry was fetched) is checked and recorded.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

VERSION = "ratio-ni-compare-1.0.0"


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+|\d+", (s or "").lower()) if t not in {"the", "of", "to", "from", "after", "at", "and", "time"}}


def _ratio_outcomes(registry: dict) -> list[dict]:
    out = []
    for m in ((registry.get("resultsSection") or {}).get("outcomeMeasuresModule") or {}).get("outcomeMeasures") or []:
        ans = [a for a in m.get("analyses") or [] if re.search(r"ratio|\bgmr\b", (a.get("paramType") or "").lower()) and a.get("paramValue")]
        if ans:
            out.append({"measure": m, "analysis": ans[0]})
    return out


def _pooled_log_sd(measure: dict) -> dict | None:
    """Per-arm geometric CVs (%) -> log-scale SDs, pooled by degrees of freedom."""
    if (measure.get("dispersionType") or "").lower().find("coefficient of variation") < 0:
        return None
    n = {c["groupId"]: int(c["value"]) for d in measure.get("denoms") or [] for c in d["counts"]}
    arms = []
    for c in measure.get("classes") or []:
        for cat in c.get("categories") or []:
            for x in cat["measurements"]:
                if x.get("spread") not in (None, "") and x["groupId"] in n:
                    cv = float(x["spread"]) / 100
                    arms.append({"group": x["groupId"], "n": n[x["groupId"]], "geo_cv": cv, "log_sd": math.sqrt(math.log(1 + cv * cv))})
    if not arms:
        return None
    df = sum(a["n"] - 1 for a in arms)
    pooled = math.sqrt(sum((a["n"] - 1) * a["log_sd"] ** 2 for a in arms) / df)
    return {"arms": arms, "pooled_log_sd": pooled, "pooled_geo_cv": math.sqrt(math.exp(pooled ** 2) - 1)}


def _percentile(value: float, q: dict) -> str:
    keys = sorted(q, key=lambda k: int(k[1:]))
    if value < q[keys[0]]:
        return f"below {keys[0]}"
    if value > q[keys[-1]]:
        return f"above {keys[-1]}"
    for a, b in zip(keys, keys[1:], strict=False):
        if q[a] <= value <= q[b]:
            return f"{a}-{b}"
    return "?"


def compare(results_dir: Path, registry_file: Path, fetched_at: str, out_dir: Path) -> dict:
    results_dir, out_dir = Path(results_dir), Path(out_dir)
    pred = json.loads((results_dir / "ratio_ni_results.json").read_text(encoding="utf-8"))
    lock = results_dir / "lock.json"
    locked_at = json.loads(lock.read_text(encoding="utf-8"))["locked_at"] if lock.exists() else None
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    candidates = _ratio_outcomes(registry)
    items, used = [], set()
    for an in pred.get("analyses") or []:
        aid, want = an["analysis_id"], _tokens(an["endpoint"])
        scored = sorted(((len(want & _tokens(c["measure"]["title"])), i) for i, c in enumerate(candidates) if i not in used), reverse=True)
        if not scored or scored[0][0] == 0:
            items.append({"analysis_id": aid, "endpoint": an["endpoint"], "status": "UNMATCHED", "reason": "no registry outcome with a ratio analysis"})
            continue
        i = scored[0][1]
        used.add(i)
        m, a = candidates[i]["measure"], candidates[i]["analysis"]
        gmr, lo, hi = float(a["paramValue"]), a.get("ciLowerLimit"), a.get("ciUpperLimit")
        lo = float(lo) if lo not in (None, "") else None
        actual_success = lo is not None and lo > an["margin"]
        var = _pooled_log_sd(m)
        scenarios = []
        for s in pred.get("scenarios") or []:
            design = next((g for g in s.get("grid") or [] if g.get("position") == 1), None)
            if not design:
                continue
            pe = design["per_endpoint"][aid]
            q = pe["observed_gmr"]
            scenarios.append({"variability": s["variability"], "assumed_log_sd": s["sd"][aid],
                              "predicted_p_success": pe["p_success"], "predicted_gmr": q,
                              "actual_gmr_percentile": _percentile(gmr, q), "actual_inside_80": q["p10"] <= gmr <= q["p90"],
                              "predicted_lower_bound": pe["lower_bound"],
                              "actual_lower_percentile": _percentile(lo, pe["lower_bound"]) if lo is not None else None})
        items.append({"analysis_id": aid, "endpoint": an["endpoint"], "status": "SCORED", "registry_title": m["title"],
                      "registry_type": m.get("type"), "margin": an["margin"], "design_ratio": an["design_ratio"],
                      "actual": {"gmr": gmr, "ci": [lo, float(hi) if hi not in (None, "") else None], "ci_pct": a.get("ciPctValue"),
                                 "p_value": a.get("pValue"), "method": a.get("statisticalMethod"), "noninferior": actual_success,
                                 "n": {c["groupId"]: int(c["value"]) for d in m.get("denoms") or [] for c in d["counts"]}},
                      "predicted_n": an.get("n"), "variability_actual": var, "scenarios": scenarios,
                      "conclusion_agrees": all((s["predicted_p_success"] >= 0.5) == actual_success for s in scenarios) if scenarios else None})
    both = [i for i in items if i["status"] == "SCORED"]
    doc = {"version": VERSION, "registry": registry["protocolSection"]["identificationModule"]["nctId"],
           "predictions_locked_at": locked_at, "registry_fetched_at": fetched_at,
           "order_verified": bool(locked_at and locked_at < fetched_at), "items": items,
           "all_succeed_actual": bool(both) and all(i["actual"]["noninferior"] for i in both),
           "all_succeed_predicted": {s["variability"]: next((g["all_endpoints_succeed"] for g in s.get("grid") or [] if g.get("position") == 1), None)
                                     for s in pred.get("scenarios") or []}}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ratio_ni_comparison.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    (out_dir / "ratio_ni_comparison.md").write_text(render(doc), encoding="utf-8")
    return doc


def render(doc: dict) -> str:
    L = [f"# Primary ratio noninferiority against the registry ({doc['version']})", "",
         f"Registry {doc['registry']}; predictions locked at {doc['predictions_locked_at']}; registry fetched at "
         f"{doc['registry_fetched_at']}; order verified: {doc['order_verified']}.", "",
         f"All hypotheses noninferior - registry: {doc['all_succeed_actual']}; predicted probability at the design ratios: "
         + "; ".join(f"{k} {v:.3f}" for k, v in doc["all_succeed_predicted"].items() if v is not None), ""]
    for i in doc["items"]:
        L += [f"## {i['analysis_id']}: {i['endpoint']}", ""]
        if i["status"] != "SCORED":
            L += [f"- {i['status']}: {i['reason']}", ""]
            continue
        a = i["actual"]
        L += [f"- Registry outcome: {i['registry_title']} ({i['registry_type']})",
              f"- Registry: GMR {a['gmr']} ({a['ci_pct']}% CI {a['ci'][0]}-{a['ci'][1]}), {a['method']}, p {a['p_value']}; margin "
              f"{i['margin']}; noninferior: {a['noninferior']}; evaluable {sum(a['n'].values())} (predicted {i['predicted_n']})",
              f"- Protocol design ratio (simulated truth): {i['design_ratio']}"]
        v = i["variability_actual"]
        if v:
            cvs = ", ".join(f"{x['geo_cv']:.0%}" for x in v["arms"])
            L.append(f"- Registry variability: geometric CV by arm {cvs}; pooled log-scale SD "
                     f"{v['pooled_log_sd']:.3f} (CV {v['pooled_geo_cv']:.0%})")
        L += ["", "| Variability assumed | log SD | P(noninferior) | predicted GMR p10-p50-p90 | registry GMR percentile | inside 80% |",
              "| --- | ---: | ---: | --- | --- | --- |"]
        for s in i["scenarios"]:
            q = s["predicted_gmr"]
            L.append(f"| {s['variability']} | {s['assumed_log_sd']:.3f} | {s['predicted_p_success']:.3f} | {q['p10']:.2f}-{q['p50']:.2f}-{q['p90']:.2f} "
                     f"| {s['actual_gmr_percentile']} | {s['actual_inside_80']} |")
        L += ["", f"Conclusion agrees: {i['conclusion_agrees']}", ""]
    L += ["The simulated estimate is centred on the protocol's design ratio (the engine's truth); a registry ratio outside the "
          "predicted interval means the protocol's assumed ratio, not the noninferiority conclusion, was off.", ""]
    return "\n".join(L)
