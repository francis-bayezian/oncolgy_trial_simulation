"""Milestones 7 and 8: recruitment, randomization and the synthetic enrolled cohort.

Inputs: the locked StudySpec, the locked eligibility stage and the locked source population.

* Enrollment target: the StudySpec's maximum accrual, else the sum of its target accruals.
* Accrual rate: every accrual rate the protocol states as an estimate is a SCENARIO. Rates stated as a
  monitoring threshold ('50/year or less will be of concern') are not estimates and are excluded. No
  distribution between scenarios is assumed; later stages report every scenario.
* Arrivals follow a Poisson process at the scenario's rate. Arriving patients are drawn at random from the
  patients the eligibility stage did not prove ineligible; criteria that could not be checked stay listed
  with the patient.
* Randomization: the protocol's open randomized arms at its stated allocation ratio. When the protocol
  does not state a balancing method (permuted blocks and their size, minimization), each patient is
  allocated independently at that ratio, and this is reported.
* Stratum: the stratum whose rule the patient meets; UNRESOLVED when the patient data cannot decide it.
"""

import json
import re
from pathlib import Path

import numpy as np

from ..protocol import expressions as ex

RECRUITMENT_VERSION = "recruitment-1.0.0"
THRESHOLD_WORDING = re.compile(r"\b(concern|slower than|faster than|or less|or more|below|above|if the|unless)\b", re.IGNORECASE)
BALANCING_WORDING = re.compile(r"\b(block|permuted|minimi[sz]ation|biased coin|urn)\b", re.IGNORECASE)


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def accrual_plan(spec: dict) -> dict:
    sizes = spec.get("sample_size") or []
    stated = [s for s in sizes if s["quantity"] in {"maximum_accrual", "target_accrual"} and s.get("value")]
    if stated:  # the trial's enrollment target is its largest stated maximum or target accrual (cohort ceilings are smaller)
        top = max(stated, key=lambda s: (s["value"], s["quantity"] == "maximum_accrual"))
        target = {"patients": int(top["value"]), "source": top["quantity"], "evidence": _q(top["evidence"])}
    else:
        target = None
    scenarios, excluded = [], []
    for s in sizes:
        if s["quantity"] != "accrual_rate" or not s.get("value"):
            continue
        evidence = _q(s["evidence"]) or ""
        entry = {"rate_per_year": float(s["value"]), "evidence": evidence}
        if THRESHOLD_WORDING.search(evidence):
            excluded.append({**entry, "reason": "stated as a monitoring threshold, not an estimate"})
        elif all(abs(x["rate_per_year"] - entry["rate_per_year"]) > 1e-9 for x in scenarios):
            scenarios.append(entry)
    scenarios.sort(key=lambda x: x["rate_per_year"])
    for sc in scenarios:
        sc["scenario"] = f"accrual_{sc['rate_per_year']:g}_per_year"
    return {"target": target, "scenarios": scenarios, "excluded_rates": excluded}


def randomization_plan(spec: dict) -> dict:
    r = spec.get("randomization") or {}
    open_arms = [a for a in spec["arms"] if a.get("status") == "open"]
    randomized = []
    for q in r.get("arms") or []:
        text = (_q(q) or "").casefold()
        arm = next((a for a in open_arms if text.startswith((_q(a["label"]) or "").casefold())), None)
        if arm and arm not in randomized:
            randomized.append(arm)
    if not randomized:
        randomized = open_arms
    ratio = (r.get("allocation") or {}).get("ratio")
    ratio_ok = ratio and len(ratio) == len(randomized)
    method_text = " ".join(filter(None, [_q(r.get("method")), _q(r.get("timing"))]))
    return {"arms": [{"arm_id": a["arm_id"], "label": _q(a["label"]), "description": " ".join((_q(a.get("description")) or "").split())}
                     for a in randomized],
            "ratio": ratio if ratio_ok else None,
            "ratio_derivation": (r.get("allocation") or {}).get("derivation") if ratio_ok else "NOT_STATED",
            "method_text": method_text,
            "balancing": "stated" if BALANCING_WORDING.search(method_text) else "not stated: independent allocation at the ratio",
            "strata": [{"stratum_id": s["stratum_id"], "status": s.get("status"), "logic": s.get("logic"), "rendering": s.get("rendering")}
                       for s in spec["stratification"]["strata"]]}


def stratum_of(strata: list[dict], patient: dict) -> str:
    met = [s["stratum_id"] for s in strata if s.get("status") == "EXECUTABLE" and ex.evaluate(s.get("logic"), patient) is True]
    return met[0] if len(met) == 1 else "UNRESOLVED"


def enrollment_draws(pool_size: int, n: int, rate: float, ratio: list[float], rng: np.random.Generator) -> tuple:
    """Which pool patients arrive (in order), their arrival days (Poisson process) and their allocated arm index."""
    order = rng.permutation(pool_size)[:n]
    days = np.cumsum(rng.exponential(365.25 / rate, size=len(order))) if rate else np.arange(1, len(order) + 1, dtype=float)
    p = np.asarray(ratio, dtype=float)
    allocation = rng.choice(len(p), size=len(order), p=p / p.sum())
    return order, days, allocation


def enroll(pool: list[dict], eligibility: dict[str, dict], plan: dict, randomization: dict, rate: float, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    arms = randomization["arms"]
    order, days, allocation = enrollment_draws(len(pool), plan["target"]["patients"], rate,
                                               randomization["ratio"] or [1.0] * len(arms), rng)
    cohort = []
    for k, (i, day, a) in enumerate(zip(order, days, allocation, strict=True)):
        p = pool[int(i)]
        cohort.append({"subject_id": f"S{k + 1:04d}", "patient_id": p["patient_id"], "enrollment_day": float(day),
                       "arm_id": arms[int(a)]["arm_id"], "stratum": stratum_of(randomization["strata"], p),
                       "unchecked_criteria": eligibility[p["patient_id"]]["unknown"], "baseline": p})
    return cohort


def build_cohorts(spec_lock: Path, population_lock: Path, eligibility_lock: Path, out_dir: Path, seed: int = 20260927) -> dict:
    from .lock import verify
    from .studyspec import load_studyspec

    spec, spec_record = load_studyspec(spec_lock)
    pop_record, el_record = verify(population_lock), verify(eligibility_lock)
    with open(Path(population_lock) / "population.jsonl", encoding="utf-8") as fh:
        patients = [json.loads(line) for line in fh]
    with open(Path(eligibility_lock) / "eligibility.jsonl", encoding="utf-8") as fh:
        eligibility = {r["patient_id"]: r for r in map(json.loads, fh)}
    pool = [p for p in patients if eligibility[p["patient_id"]]["status"] != "INELIGIBLE"]
    plan, randomization = accrual_plan(spec), randomization_plan(spec)
    if plan["target"] is None:
        raise ValueError("the protocol states no enrollment target: recruitment is unresolved")
    if not plan["scenarios"]:  # who enrolls can still be simulated; when they enroll cannot
        plan["scenarios"] = [{"scenario": "accrual_rate_unresolved", "rate_per_year": None,
                              "evidence": "no accrual rate estimate is stated: enrollment days are placeholders in arrival order"}]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    per = {}
    for k, sc in enumerate(plan["scenarios"]):
        cohort = enroll(pool, eligibility, plan, randomization, sc["rate_per_year"], seed + k)
        with open(out_dir / f"cohort_{sc['scenario']}.jsonl", "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in cohort)
        per[sc["scenario"]] = _cohort_summary(cohort, randomization)
    summary = {"pool": len(pool), "target": plan["target"], "scenarios": per}
    doc = {"recruitment_version": RECRUITMENT_VERSION, "seed": seed,
           "inputs": {"studyspec": spec_record["files"]["studyspec.json"], "population": pop_record["files"]["population.jsonl"],
                      "eligibility": el_record["files"]["eligibility.jsonl"]},
           "accrual_plan": plan, "randomization": {k: v for k, v in randomization.items() if k != "strata"}
           | {"strata": [{k: v for k, v in s.items() if k != "logic"} for s in randomization["strata"]]}, "summary": summary}
    (out_dir / "recruitment_summary.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "recruitment_report.md").write_text(_report(doc), encoding="utf-8")
    return summary


def _cohort_summary(cohort: list[dict], randomization: dict) -> dict:
    n = len(cohort)
    arms = {a["arm_id"]: sum(c["arm_id"] == a["arm_id"] for c in cohort) for a in randomization["arms"]}
    strata: dict[str, int] = {}
    for c in cohort:
        strata[c["stratum"]] = strata.get(c["stratum"], 0) + 1
    sexes: dict[str, int] = {}
    for c in cohort:
        s = c["baseline"].get("demographic:sex")
        sexes[s] = sexes.get(s, 0) + 1
    return {"enrolled": n, "accrual_years": cohort[-1]["enrollment_day"] / 365.25 if n else 0.0, "arms": arms, "strata": strata,
            "sex": sexes, "age_mean": float(np.mean([c["baseline"]["demographic:age"]["value"] for c in cohort])) if n else None}


def _report(doc: dict) -> str:
    plan, r, s = doc["accrual_plan"], doc["randomization"], doc["summary"]
    lines = [f"# Recruitment and enrolled cohort ({doc['recruitment_version']})", "",
             f"Enrollment target: {plan['target']['patients']} patients ({plan['target']['source']}).",
             f"Enrollable pool: {s['pool']} source-population patients not proven ineligible.", "",
             "## Accrual scenarios (rates the protocol states as estimates)", ""]
    lines += [f"- {sc['scenario']}: " + (f"{sc['rate_per_year']:g} per year" if sc["rate_per_year"] else "no rate") + f" - '{sc['evidence'][:160]}'"
              for sc in plan["scenarios"]]
    lines += [f"- excluded {x['rate_per_year']:g} per year ({x['reason']}): '{x['evidence'][:160]}'" for x in plan["excluded_rates"]]
    lines += ["", "## Randomization", "",
              (f"Arms: {[a['label'] for a in r['arms']]}; ratio {r['ratio']} ({r['ratio_derivation']}); method '{r['method_text']}'; "
               f"balancing {r['balancing']}."), ""]
    for name, c in s["scenarios"].items():
        years = f"{c['accrual_years']:.1f} years" if not name.endswith("unresolved") else "an unresolved time (no accrual rate stated)"
        lines += [f"### {name}", "", (f"{c['enrolled']} enrolled over {years}; arms {c['arms']}; "
                                      f"strata {c['strata']}; sex {c['sex']}; mean age {c['age_mean']:.1f}."), ""]
    return "\n".join(lines) + "\n"
