"""Milestones 9-16 for rule-based dose escalation (3+3 and similar).

The compiled escalation rules (cohort size and one row per 'number of patients with a DLT out of n -> action')
are interpreted as written. The truth such a trial learns about, the probability of a dose-limiting toxicity
(DLT) at each dose level, is unknown and no source quantifies it for a new agent, so it is never invented: the
design is run under a grid of hypothetical truths in which the highest tolerable level is each level in turn
(DLT probability `low` at and below it, `high` above), and the report gives, for each truth, the probability that
each level is selected as the MTD and the number of patients the escalation uses.
"""

import json
from pathlib import Path

import numpy as np

ESCALATION_VERSION = "escalation-1.0.0"
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


def run(spec_lock: Path, out_dir: Path, replicates: int = 5000, seed: int = 20260927) -> dict:
    from .studyspec import load_studyspec

    spec, record = load_studyspec(spec_lock)
    rules = [r for r in spec.get("decision_rules") or [] if r["kind"] == "dose_escalation"]
    results = []
    for r in rules:
        entry = {"decision_rule_id": r["decision_rule_id"], "status": r.get("status"), "design_family": r["design_family"], "rule": r["rule"]}
        levels = len(r["rule"]["dose_levels"])
        if r.get("status") != "EXECUTABLE" or not r["rule"]["rules"]:
            entry["result"] = "UNRESOLVED: the escalation rule is not executable in the StudySpec"
        elif levels == 0:
            entry["result"] = "UNRESOLVED: the protocol states no dose levels"
        else:
            entry["operating_characteristics"] = operating_characteristics(r["rule"], levels, replicates, seed)
        results.append(entry)
    doc = {"escalation_version": ESCALATION_VERSION, "seed": seed, "replicates": replicates,
           "inputs": {"studyspec": record["files"]["studyspec.json"]},
           "truth": (f"hypothetical DLT probabilities {LOW} at and below the true highest tolerable level and {HIGH} above it, for "
                     "each level in turn: a grid of truths, not evidence"), "rules": results}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "escalation_results.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Dose escalation ({ESCALATION_VERSION})", "", doc["truth"] + ".", ""]
    for e in results:
        lines.append(f"## {e['decision_rule_id']} ({e['design_family']})")
        if "result" in e:
            lines += ["", e["result"], ""]
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
