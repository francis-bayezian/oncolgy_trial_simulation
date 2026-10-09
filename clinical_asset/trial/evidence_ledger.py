"""Estimand registry, evidence tiers and the evidence ledger for patient-level effects (L056).

Every effect answers one question (its estimand); evidence answering a different question is never pooled with it.
Every piece of evidence has a tier:
  1  individual-patient evidence (IPD or pooled patient-level analyses)
  2  adjusted published multivariable estimates
  3  aggregate / trial-level relationships (the regression over the evidence corpus)
  4  mechanistic or hierarchical prior only
The ledger lists, for every (characteristic, estimand), the evidence behind it, its tier and source; the synthesis
engine (evidence_synthesis) adds the learned shrinkage and the posterior uncertainty.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from . import patient_risk

# ----------------------------------------------------------------------------- estimands
# key -> definition. Prognostic effects: the log odds ratio of the outcome per unit of the characteristic, within one
# treatment, in a cancer trial population. Treatment-effect modifiers are separate estimands (none registered yet).
ESTIMANDS = {
    "prognostic_log_or:serious_ae": "log odds ratio of having any serious adverse event (regulatory seriousness) during the study",
    "prognostic_log_or:other_ae": "log odds ratio of having any non-serious adverse event above the reporting threshold",
    "prognostic_log_or:death": "log odds ratio of dying during the study period",
    "prognostic_log_or:ae_discontinuation": "log odds ratio of stopping study treatment for an adverse event",
    "prognostic_log_or:withdrawal": "log odds ratio of withdrawing (subject decision, lost to follow-up, physician decision)",
    "prognostic_log_or:severe_ae_grade3plus": "log odds ratio of having any severe (CTCAE grade >= 3) adverse event",
}
SIMULATED = {"serious_ae": "prognostic_log_or:serious_ae", "other_ae": "prognostic_log_or:other_ae", "death": "prognostic_log_or:death",
             "ae_discontinuation": "prognostic_log_or:ae_discontinuation", "withdrawal": "prognostic_log_or:withdrawal"}

# ----------------------------------------------------------------------------- characteristics and groups
# unit of each characteristic and its group for hierarchical borrowing (only clinically defensible groups; a group of
# one is no borrowing)
CHARACTERISTICS = {
    "age10": {"unit": "per 10 years of age", "group": "age"},
    "female": {"unit": "female vs male", "group": "sex"},
    "ecog1": {"unit": "ECOG performance status >= 1 vs 0", "group": "performance_status"},
    "asian": {"unit": "Asian vs not", "group": "race"},
    "black": {"unit": "Black vs not", "group": "race"},
}

# ----------------------------------------------------------------------------- published evidence (tiers 1-2)
LITERATURE = [
    {"characteristic": "female", "estimand": "prognostic_log_or:severe_ae_grade3plus", "tier": 1,
     "estimate": math.log(1.34), "se": (math.log(1.42) - math.log(1.27)) / (2 * 1.96), "odds_ratio": 1.34, "ci_95": [1.27, 1.42],
     "population": "202 SWOG trials, 23,296 patients; all treatment modalities",
     "citation": "Unger JM, Vaidya R, Albain KS, et al. Sex Differences in Risk of Severe Adverse Events in Patients Receiving "
                 "Immunotherapy, Targeted Therapy, or Chemotherapy in Cancer Clinical Trials. J Clin Oncol. 2022. "
                 "doi:10.1200/JCO.21.02377"},
]


def tier3_entries(model: dict | None = None) -> list[dict]:
    """The corpus regression's trial-level estimates (tier 3), one per (characteristic, simulated outcome)."""
    f = patient_risk.model_dir() / "model.json"           # the regression as fitted, not the effects applied
    model = model or (json.loads(f.read_text(encoding="utf-8")) if f.exists() else None)
    out = []
    for outcome, m in ((model or {}).get("outcomes") or {}).items():
        if m.get("status") != "ESTIMATED":
            continue
        for c in CHARACTERISTICS:
            e = m["patient_effects"].get(c) or {}
            raw = e.get("trial_level_estimate") or e          # the regression's own estimate, whatever was applied before
            est, se = raw.get("estimate"), raw.get("se")
            if est is None or se is None:
                continue
            out.append({"characteristic": c, "estimand": SIMULATED[outcome], "tier": 3, "estimate": float(est), "se": float(se),
                        "population": f"{m['records']} arm/trial records, {m['trials']} trials, {m['participants']} participants",
                        "citation": f"{model['source']}; binomial regression with phase, disease family and drug-class controls"
                                    + (f"; {raw.get('from')}" if isinstance(raw, dict) and raw.get("from") else "")})
    return out


def entries(model: dict | None = None) -> list[dict]:
    return tier3_entries(model) + [dict(x) for x in LITERATURE]


def ledger_rows(evidence: list[dict], synthesis: dict | None = None) -> list[dict]:
    """One row per (characteristic, estimand): its evidence by tier and, from the synthesis, shrinkage and uncertainty."""
    rows = {}
    for e in evidence:
        k = (e["characteristic"], e["estimand"])
        rows.setdefault(k, {"characteristic": e["characteristic"], "unit": CHARACTERISTICS.get(e["characteristic"], {}).get("unit"),
                            "estimand": e["estimand"], "evidence": []})["evidence"].append(
            {"tier": e["tier"], "estimate": round(e["estimate"], 4), "se": round(e["se"], 4), "source": e["citation"], "population": e.get("population")})
    for k, r in rows.items():
        r["tiers"] = sorted({x["tier"] for x in r["evidence"]})
        s = ((synthesis or {}).get("effects") or {}).get(f"{k[0]}|{k[1]}")
        if s:
            r.update({key: s[key] for key in ("posterior_mean", "posterior_sd", "interval_95", "shrinkage", "variance_components") if key in s})
    return sorted(rows.values(), key=lambda r: (r["estimand"], r["characteristic"]))


def write_ledger(rows: list[dict], out: Path) -> Path:
    """The ledger as JSON and as a readable markdown table."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence_ledger.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    L = ["# Evidence ledger: patient-level effects", "",
         "Every effect is a probability distribution; its width reflects the evidence behind it (tiers: 1 IPD, 2 adjusted "
         "published, 3 trial-level corpus regression, 4 prior only).", "",
         "| Characteristic | Estimand | Tiers | Evidence (log OR, se) | Shrinkage | Posterior mean (95% interval) | OR (95% interval) |",
         "| --- | --- | --- | --- | ---: | --- | --- |"]
    for r in rows:
        ev = "; ".join(f"T{x['tier']}: {x['estimate']} ({x['se']})" for x in r["evidence"])
        if "posterior_mean" in r:
            lo, hi = r["interval_95"]
            post = f"{r['posterior_mean']:.3f} ({lo:.3f} to {hi:.3f})"
            orr = f"{math.exp(r['posterior_mean']):.2f} ({math.exp(lo):.2f}-{math.exp(hi):.2f})"
            shr = f"{r['shrinkage']:.2f}" if r.get("shrinkage") is not None else "-"
        else:
            post = orr = shr = "not synthesised (estimand not simulated)"
        L.append(f"| {r['characteristic']} | {r['estimand'].split(':')[1]} | {','.join(map(str, r['tiers']))} | {ev} | {shr} | {post} | {orr} |")
    L += ["", "## Sources", ""] + sorted({f"- {x['source']}" for r in rows for x in r["evidence"]})
    (out / "EVIDENCE_LEDGER.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out
