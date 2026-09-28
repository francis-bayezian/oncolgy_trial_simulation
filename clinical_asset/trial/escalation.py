"""Milestones 9-16 for rule-based dose escalation (3+3 and similar).

The compiled escalation rules (cohort size and one row per 'number of patients with a DLT out of n -> action')
are interpreted as written. The truth such a trial learns about, the probability of a dose-limiting toxicity
(DLT) at each dose level, is unknown and no source quantifies it for a new agent, so it is never invented: the
design is run under a grid of hypothetical truths in which the highest tolerable level is each level in turn
(DLT probability `low` at and below it, `high` above), and the report gives, for each truth, the probability that
each level is selected as the MTD and the number of patients the escalation uses.
"""

import json
import math
from pathlib import Path

import numpy as np

ESCALATION_VERSION = "escalation-1.1.0"
LOW, HIGH = 0.10, 0.45            # hypothetical DLT probabilities below / above the true tolerable level (grid, not evidence)


def _matches(row: dict, dlt: int, n: int) -> bool:
    if n > row["patients"]:
        return False
    if row["comparator"] == "exactly":
        return dlt == row["dlt"] and n == row["patients"]
    if row["comparator"] == "at_most":
        return dlt <= row["dlt"] and n == row["patients"]
    return dlt >= row["dlt"]


def run_escalation(rule: dict, dlt_prob: list[float], rng: np.random.Generator, max_patients: int = 1000) -> dict:
    """One escalation: returns the selected MTD level index (-1: even the first level is too toxic; None: every level
    was cleared, the MTD is at or above the highest level) and the patients treated at each level."""
    size, rows = rule["cohort_size"], rule["rules"]
    level, treated, dlts = 0, [0] * len(dlt_prob), [0] * len(dlt_prob)
    while sum(treated) < max_patients:
        k = int(rng.binomial(size, dlt_prob[level]))
        treated[level] += size
        dlts[level] += k
        row = next((r for r in rows if _matches(r, dlts[level], treated[level])), None)
        action = row["action"] if row else "stop_dose_exceeds_mtd"
        if action == "expand_cohort":
            continue
        if action in {"stop_dose_exceeds_mtd"}:
            return {"mtd_level": level - 1, "treated": treated, "dlts": dlts}
        if action == "declare_mtd":
            return {"mtd_level": level, "treated": treated, "dlts": dlts}
        if level + 1 == len(dlt_prob):
            return {"mtd_level": None, "treated": treated, "dlts": dlts}
        level += 1
    return {"mtd_level": None, "treated": treated, "dlts": dlts, "note": "patient cap reached"}


def truth_grid(levels: int) -> list[dict]:
    out = []
    for j in range(-1, levels):
        out.append({"true_highest_tolerable_level": j, "dlt_prob": [LOW if d <= j else HIGH for d in range(levels)]})
    return out


def operating_characteristics(rule: dict, levels: int, replicates: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for truth in truth_grid(levels):
        picks, patients = {}, []
        for _ in range(replicates):
            r = run_escalation(rule, truth["dlt_prob"], rng)
            key = "none_tolerable" if r["mtd_level"] == -1 else "all_cleared" if r["mtd_level"] is None else f"level_{r['mtd_level'] + 1}"
            picks[key] = picks.get(key, 0) + 1
            patients.append(sum(r["treated"]))
        correct = ("none_tolerable" if truth["true_highest_tolerable_level"] == -1 else f"level_{truth['true_highest_tolerable_level'] + 1}")
        rows.append({**truth, "selection": {k: v / replicates for k, v in sorted(picks.items())},
                     "prob_correct": picks.get(correct, 0) / replicates if truth["true_highest_tolerable_level"] < levels - 1
                     else picks.get("all_cleared", 0) / replicates,
                     "patients": {"median": float(np.median(patients)), "q05": float(np.quantile(patients, 0.05)), "q95": float(np.quantile(patients, 0.95))}})
    return rows


# ----------------------------------------------------------------------------- dose ladders built from increments

TARGET_DLT = 0.30                  # D* in the hypothetical truths: the dose with this DLT probability (a definition, not evidence)
SLOPES = (1.0, 3.0)                # hypothetical dose-toxicity steepness on the log-dose scale (grid)
GRADE2_ODDS = (1.0, 4.0)           # hypothetical odds ratio of a grade >= 2 toxicity over a DLT at the same dose (grid)
DSTAR_MULTIPLES = tuple(2 ** (k / 2) for k in range(13))      # D* from the starting dose to 64 times it


def next_dose(dose: float, inc: dict | None, step: int, forms: list[dict], unit: str) -> float | None:
    """The next dose: an increment stated as a maximum is applied at that maximum, then rounded down to a multiple of
    the smallest stated dosage-form strength in the same unit (never below one strength above the current dose)."""
    if not inc:
        return None
    if "sequence" in inc:
        new = dose * inc["sequence"][min(step, len(inc["sequence"]) - 1)]
    elif "add" in inc:
        new = dose + inc["add"]
    else:
        new = dose * inc["factor"]
    strengths = [f["value"] for f in forms if f["unit"] == unit and f["value"] > 0]
    if strengths:
        s = min(strengths)
        new = max(math.floor(new / s + 1e-9) * s, dose + s)
    return float(new)


def _p_dlt(d: float, curve: dict) -> float:
    z = math.log(TARGET_DLT / (1 - TARGET_DLT)) + curve["slope"] * math.log(d / curve["d_star"])
    return 1 / (1 + math.exp(-z))


def _p_g2(d: float, curve: dict) -> float:
    p = _p_dlt(d, curve)
    odds = p / (1 - p) * curve["grade2_odds"]
    return odds / (1 + odds)


def run_ladder(rule: dict, curve: dict, rng: np.random.Generator, max_patients: int = 300) -> dict:
    """One dose escalation on a dose ladder computed from the starting dose and the stated increments. Returns the
    declared MTD dose (None: no dose tolerable at the start; 'not_reached': the patient cap or maximum dose was reached
    with every dose cleared), the doses visited and the patients treated."""
    lad = rule["ladder"]
    unit, forms, cap = lad["start"]["unit"], lad["dosage_forms"], (lad["max"] or {}).get("value")
    stages = lad["stages"] or [{"kind": "rule_based", "cohort_size": rule["cohort_size"], "increment": None, "switch": None}]
    rb = next((s for s in stages if s["kind"] == "rule_based"), {"cohort_size": rule["cohort_size"], "increment": None})
    size = rule["cohort_size"] or rb.get("cohort_size") or 3
    seq = {"sequence": lad["sequence"], "bound": "exact"} if lad.get("sequence") else None
    rows = rule["rules"]
    doses, treated, dlts = [lad["start"]["value"]], [0], [0]
    level, stage, step = 0, 0 if stages[0]["kind"] == "accelerated_titration" else None, 0

    def treat(k: int) -> int:
        tox = int(rng.binomial(k, _p_dlt(doses[level], curve)))
        treated[level] += k
        dlts[level] += tox
        return tox

    def climb(inc) -> bool:
        nonlocal level, step
        new = next_dose(doses[level], inc, step, forms, unit)
        if new is None or (cap is not None and doses[level] >= cap):
            return False
        new = min(new, cap) if cap is not None else new
        step += 1
        doses.append(new), treated.append(0), dlts.append(0)
        level += 1
        return True

    def exceeded(lvl: int) -> bool:
        """A confirmed lower dose exceeds the MTD only when a stop row of the table matches its counts ('0 of 6' has no row
        of its own in a 3+3 table and is tolerable)."""
        return any(r["action"] in {"stop_dose_exceeds_mtd", "expand_previous_level"} and _matches(r, dlts[lvl], treated[lvl]) for r in rows)

    while sum(treated) < max_patients:
        if stage is not None:                                          # accelerated titration
            st = stages[stage]
            k = st["cohort_size"] or 1
            p_dlt = _p_dlt(doses[level], curve)
            dl = rng.random(k) < p_dlt
            g2 = dl | (rng.random(k) < (_p_g2(doses[level], curve) - p_dlt) / max(1e-12, 1 - p_dlt))
            treated[level] += k
            dlts[level] += int(dl.sum())
            sw = st["switch"]
            hits = (g2 if sw["grade_at_least"] is not None else np.zeros(k, bool)) | (dl if sw["or_dlt"] else np.zeros(k, bool))
            if hits.sum() >= sw["patients"]:
                stage = None                                           # switch to the rule table at the current dose
                continue
            if not climb(st["increment"] or seq):
                return {"mtd": "not_reached", "doses": doses, "treated": treated}
            continue
        fill = size - treated[level] % size if treated[level] % size else size
        treat(fill)
        row = next((r for r in rows if _matches(r, dlts[level], treated[level])), None)
        action = row["action"] if row else "stop_dose_exceeds_mtd"
        if action == "expand_cohort":
            continue
        if action == "declare_mtd":
            return {"mtd": doses[level], "doses": doses, "treated": treated}
        if action == "escalate":
            if not climb(row.get("increment") or rb.get("increment") or seq):
                return {"mtd": "not_reached", "doses": doses, "treated": treated}
            continue
        # the current dose exceeds the MTD: confirm the lower doses (adding patients where a row says so)
        adds = any(r["action"] == "expand_previous_level" for r in rows)
        lvl = level - 1
        while lvl >= 0:
            if adds and treated[lvl] < 2 * size:
                level = lvl
                treat(2 * size - treated[lvl])
            if not exceeded(lvl):
                return {"mtd": doses[lvl], "doses": doses, "treated": treated}
            lvl -= 1
        return {"mtd": None, "doses": doses, "treated": treated}
    return {"mtd": "not_reached", "doses": doses, "treated": treated, "note": "patient cap reached"}


def ladder_characteristics(rule: dict, replicates: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    start = rule["ladder"]["start"]["value"]
    rows = []
    for slope in SLOPES:
        for odds in GRADE2_ODDS:
            for mult in DSTAR_MULTIPLES:
                curve = {"d_star": start * mult, "slope": slope, "grade2_odds": odds}
                mtds, patients, none, not_reached = [], [], 0, 0
                for _ in range(replicates):
                    r = run_ladder(rule, curve, rng)
                    patients.append(sum(r["treated"]))
                    if r["mtd"] is None:
                        none += 1
                    elif r["mtd"] == "not_reached":
                        not_reached += 1
                    else:
                        mtds.append(r["mtd"])
                m = np.array(mtds) if mtds else np.array([np.nan])
                ratio = m / curve["d_star"]
                rows.append({"truth": curve, "p_dlt_at_start": _p_dlt(start, curve),
                             "declared_mtd": {"median": float(np.nanmedian(m)), "q10": float(np.nanquantile(m, 0.1)), "q90": float(np.nanquantile(m, 0.9))} if mtds else None,
                             "p_mtd_within_two_thirds_to_one_of_d_star": float(np.mean((ratio >= 2 / 3) & (ratio <= 1))) * len(mtds) / replicates if mtds else 0.0,
                             "p_mtd_above_d_star": float(np.mean(ratio > 1)) * len(mtds) / replicates if mtds else 0.0,
                             "p_no_tolerable_dose": none / replicates, "p_not_reached": not_reached / replicates,
                             "mtd_distribution": {f"{d:g}": c / replicates for d, c in sorted(zip(*np.unique(mtds, return_counts=True), strict=True))} if mtds else {},
                             "patients": {"median": float(np.median(patients)), "q05": float(np.quantile(patients, 0.05)), "q95": float(np.quantile(patients, 0.95))}})
    return rows


def run(spec_lock: Path, out_dir: Path, replicates: int = 5000, seed: int = 20260927) -> dict:
    from .studyspec import load_studyspec

    spec, record = load_studyspec(spec_lock)
    rules = [r for r in spec.get("decision_rules") or [] if r["kind"] == "dose_escalation"]
    results = []
    for r in rules:
        entry = {"decision_rule_id": r["decision_rule_id"], "status": r.get("status"), "design_family": r["design_family"], "rule": r["rule"]}
        levels = len(r["rule"]["dose_levels"])
        ladder = (r["rule"].get("ladder") or {}).get("start")
        from .binary import accept_review

        runnable = r.get("status") == "EXECUTABLE" or (accept_review() and r.get("status") == "REVIEW_REQUIRED" and not r["rule"].get("issues"))
        entry["run_despite_review"] = r.get("status") != "EXECUTABLE"
        if not runnable or not r["rule"]["rules"]:
            entry["result"] = "UNRESOLVED: the escalation rule is not executable in the StudySpec"
        elif levels == 0 and not ladder:
            entry["result"] = "UNRESOLVED: the protocol states neither dose levels nor a starting dose with increments"
        elif levels == 0:
            entry["mode"] = "dose ladder from the starting dose and increments"
            entry["ladder_characteristics"] = ladder_characteristics(r["rule"], max(200, replicates // 10), seed)
        else:
            entry["operating_characteristics"] = operating_characteristics(r["rule"], levels, replicates, seed)
        results.append(entry)
    doc = {"escalation_version": ESCALATION_VERSION, "seed": seed, "replicates": replicates,
           "inputs": {"studyspec": record["files"]["studyspec.json"]},
           "truth": (f"hypothetical DLT probabilities {LOW} at and below the true highest tolerable level and {HIGH} above it, for "
                     "each level in turn: a grid of truths, not evidence"),
           "ladder_truth": (f"for a dose ladder built from increments: logistic dose-toxicity curves in log dose with DLT probability "
                            f"{TARGET_DLT} at the dose D*, D* from the starting dose to 64 times it, slopes {list(SLOPES)}, and odds ratios "
                            f"{list(GRADE2_ODDS)} of a grade >= 2 toxicity over a DLT (for an accelerated titration that stops at the first "
                            "grade >= 2 toxicity): a grid of truths, not evidence"), "rules": results}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "escalation_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Dose escalation ({ESCALATION_VERSION})", "", doc["truth"] + ".", ""]
    for e in results:
        lines.append(f"## {e['decision_rule_id']} ({e['design_family']})")
        if "result" in e:
            lines += ["", e["result"], ""]
            continue
        if "ladder_characteristics" in e:
            unit = e["rule"]["ladder"]["start"]["unit"]
            lines += ["", doc["ladder_truth"] + ".", "",
                      "| slope | grade>=2 odds | D* | P(DLT) at start | declared MTD median (80%) | P(MTD in [2/3 D*, D*]) | P(MTD > D*) | P(none tolerable) | P(not reached) | patients (median, 90%) |",
                      "| ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |"]
            for row in e["ladder_characteristics"]:
                t, m, pt = row["truth"], row["declared_mtd"], row["patients"]
                mtd = f"{m['median']:g} ({m['q10']:g}-{m['q90']:g}) {unit}" if m else "-"
                lines.append(f"| {t['slope']:g} | {t['grade2_odds']:g} | {t['d_star']:.0f} {unit} | {row['p_dlt_at_start']:.2f} | {mtd} | "
                             f"{row['p_mtd_within_two_thirds_to_one_of_d_star']:.2f} | {row['p_mtd_above_d_star']:.2f} | {row['p_no_tolerable_dose']:.2f} | "
                             f"{row['p_not_reached']:.2f} | {pt['median']:.0f} ({pt['q05']:.0f}-{pt['q95']:.0f}) |")
            lines.append("")
            continue
        lines += ["", "| true highest tolerable level | P(correct selection) | patients (median, 90%) | selection distribution |", "| --- | ---: | --- | --- |"]
        for row in e["operating_characteristics"]:
            j = row["true_highest_tolerable_level"]
            label = "none" if j == -1 else f"level {j + 1}"
            p = row["patients"]
            lines.append(f"| {label} | {row['prob_correct']:.2f} | {p['median']:.0f} ({p['q05']:.0f}-{p['q95']:.0f}) | "
                         + ", ".join(f"{k} {v:.2f}" for k, v in row["selection"].items()) + " |")
        lines.append("")
    (out_dir / "escalation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rules": [{"rule": e["decision_rule_id"], "result": e.get("result", "simulated")} for e in results]}


# ----------------------------------------------------------------------------- registry comparison

DOSE_UNITS = {"mg", "mg/m2", "mg/kg", "ug", "ug/kg", "mcg", "mcg/kg", "g", "gy", "iu", "units"}


def registry_dose_result(registry: dict) -> dict | None:
    """The registry's primary result reported in a dose unit (a maximum tolerated or recommended dose)."""
    rs = registry.get("resultsSection", {})
    for m in rs.get("outcomeMeasuresModule", {}).get("outcomeMeasures", []):
        unit = (m.get("unitOfMeasure") or "").casefold().replace(" ", "").replace("²", "2").replace("µ", "u")
        if m.get("type") != "PRIMARY" or unit not in DOSE_UNITS:
            continue
        for c in m.get("classes", []):
            for cat in c.get("categories", []):
                for x in cat.get("measurements", []):
                    try:
                        return {"title": m["title"], "value": float(x["value"]), "unit": unit}
                    except (KeyError, TypeError, ValueError):
                        continue
    return None


def compare_ladder(entry: dict, observed: dict) -> dict:
    """For each hypothetical truth: P(declared MTD within one maximal escalation step of the registry dose)."""
    unit = entry["rule"]["ladder"]["start"]["unit"]
    if observed["unit"] != unit:
        return {"status": "UNRESOLVED", "reason": f"registry dose unit {observed['unit']} differs from the protocol unit {unit}"}
    steps = [s["increment"]["factor"] for s in entry["rule"]["ladder"]["stages"] if s.get("increment") and "factor" in s["increment"]]
    steps += [r["increment"]["factor"] for r in entry["rule"]["rules"] if r.get("increment") and "factor" in r["increment"]]
    step = min(steps) if steps else 1.5
    lo, hi = observed["value"] / step, observed["value"] * step
    rows = []
    for row in entry["ladder_characteristics"]:
        p = sum(v for d, v in row["mtd_distribution"].items() if lo <= float(d) <= hi)
        rows.append({"truth": row["truth"], "p_declared_mtd_near_registry": p, "declared_mtd": row["declared_mtd"]})
    consistent = [r for r in rows if r["p_declared_mtd_near_registry"] >= 0.10]
    return {"status": "SCORED", "registry": observed, "window": [lo, hi], "step": step, "rows": rows,
            "consistent_truths": [r["truth"] for r in consistent],
            "best": max(rows, key=lambda r: r["p_declared_mtd_near_registry"]) if rows else None,
            "note": ("the true dose-toxicity curve is unknown, so the prediction is a curve over hypothetical truths: the comparison "
                     "reports under which truths the registry dose was a likely outcome of the design as compiled")}


def run_compare(results_lock: Path, registry_file: Path, registry_fetched_at: str, out_dir: Path) -> dict:
    from .lock import load_locked, verify

    rec = verify(results_lock)
    results = load_locked(results_lock, "escalation_results.json")
    registry = json.loads(Path(registry_file).read_text(encoding="utf-8"))
    observed = registry_dose_result(registry)
    items = []
    for e in results["rules"]:
        if "ladder_characteristics" not in e:
            items.append({"rule": e["decision_rule_id"], "status": "UNRESOLVED", "reason": e.get("result", "no dose-ladder simulation")})
        elif observed is None:
            items.append({"rule": e["decision_rule_id"], "status": "UNRESOLVED", "reason": "the registry reports no primary result in a dose unit"})
        else:
            items.append({"rule": e["decision_rule_id"], **compare_ladder(e, observed)})
    doc = {"escalation_version": ESCALATION_VERSION, "predictions_locked_at": rec["locked_at"], "registry_fetched_at": registry_fetched_at,
           "order_verified": rec["locked_at"] < registry_fetched_at, "nct_id": registry["protocolSection"]["identificationModule"]["nctId"],
           "registry_dose_result": observed, "items": items}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "escalation_comparison.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    lines = [f"# Dose-escalation comparison with the registry ({ESCALATION_VERSION})", "",
             (f"Registry {doc['nct_id']}. Predictions locked at {doc['predictions_locked_at']}; registry fetched at {registry_fetched_at}; "
              f"order verified: {doc['order_verified']}."), "",
             f"Registry primary dose result: {observed['title']} = {observed['value']:g} {observed['unit']}." if observed else "Registry: no dose result.", ""]
    for it in items:
        lines.append(f"## {it['rule']}")
        if it["status"] != "SCORED":
            lines += ["", f"{it['status']}: {it['reason']}", ""]
            continue
        lines += ["", it["note"] + ".", "",
                  (f"Window: declared MTD within one maximal step (x{it['step']:g}) of the registry dose: "
                   f"{it['window'][0]:.0f}-{it['window'][1]:.0f} {observed['unit']}."), "",
                  "| slope | grade>=2 odds | D* | P(declared MTD in window) | declared MTD median (80%) |", "| ---: | ---: | ---: | ---: | --- |"]
        for r in it["rows"]:
            t, m = r["truth"], r["declared_mtd"]
            lines.append(f"| {t['slope']:g} | {t['grade2_odds']:g} | {t['d_star']:.0f} | {r['p_declared_mtd_near_registry']:.2f} | "
                         + (f"{m['median']:g} ({m['q10']:g}-{m['q90']:g})" if m else "-") + " |")
        b = it["best"]
        lines += ["", (f"Most consistent truth: D* {b['truth']['d_star']:.0f} {observed['unit']} (slope {b['truth']['slope']:g}, grade>=2 odds "
                       f"{b['truth']['grade2_odds']:g}), P = {b['p_declared_mtd_near_registry']:.2f}. Truths with P >= 0.10: {len(it['consistent_truths'])}."), ""]
    (out_dir / "escalation_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc
