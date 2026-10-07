"""The master simulation dataset of a within-patient (paired) replicate experiment: one row per simulated trial.

Per replicate (scripts/run_replicates.sh): seed; patients generated; eligible (n, %); failures by eligibility criterion;
the number screened until the evaluable target is reached (the replicate's population in a seeded random screening
order); the time to enrol the target (calendar days of the target-th participant); participants enrolled (unique
people) and exposure records; participants completing every exposure; usable pairs; missing pairs; the primary
analysis on per-participant paired measurements from a named source (estimate, p-value, success at the protocol's
alpha); and whether every replicate stage is locked. Per-participant paired values are written for each replicate
(paired_measurements.csv), so a later step can mask one exposure.

Usage: .venv/Scripts/python.exe scripts/replicate_master_table.py ID BASE_VERSION SOURCE_JSON OUT_DIR
  SOURCE_JSON: {"name": ..., "kind": "design" | "per_exposure", ...} (clinical_asset.trial.paired_measure)
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from clinical_asset.trial import paired_measure as pm  # noqa: E402

STAGES = ("population", "eligibility", "cohorts", "safety", "outputs", "journey", "endpoints", "analysis")


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()] if p.exists() else []


def main(study: str, version: str, source_file: Path, out: Path) -> Path:
    spec = json.loads((Path("data/locked") / study / f"studyspec_v{version}" / "studyspec.json").read_text(encoding="utf-8"))
    an = next(a for a in spec["analyses"] if a.get("primary"))
    target = int(next(x["value"] for x in spec["sample_size"] if x["quantity"] in ("evaluable_target", "target_accrual")))
    alpha = float((an.get("alpha") or {}).get("value") or 0.05)
    test = "wilcoxon" if an.get("test_family") == "wilcoxon" else "t"
    source = json.loads(Path(source_file).read_text(encoding="utf-8"))
    root = Path(f"data/trial/runs/{study}/v{version}/replicates")
    out.mkdir(parents=True, exist_ok=True)
    rows, crit_names = [], Counter()
    for rd in sorted(root.glob("r[0-9][0-9][0-9]")):
        r = int(rd.name[1:])
        seed = 20270000 + 97 * r
        tag = f"{version}-r{r:03d}"
        elig = _jsonl(rd / "eligibility" / "eligibility.jsonl")
        n_gen = len(elig)
        status = [e["status"] for e in elig]
        fails = Counter(c for e in elig for c in e.get("failed") or [])
        crit_names.update(fails.keys())
        # screening order: the replicate's population in a seeded random order; screened until `target` are eligible
        order = np.random.default_rng(seed + 11).permutation(n_gen)
        cum = np.cumsum([status[i] == "ELIGIBLE" for i in order])
        nns = int(np.searchsorted(cum, target) + 1) if cum[-1] >= target else None
        cohort = _jsonl(next(iter(sorted((rd / "cohorts").glob("cohort_*.jsonl"))), rd / "missing"))
        people = {}
        for c in cohort:
            pid = c.get("patient_subject") or c["subject_id"].split("-P")[0]
            people.setdefault(pid, []).append(c)
        enrol_days = sorted(min(x["enrollment_day"] for x in v) for v in people.values())
        adsl = list(csv.DictReader(open(rd / "journey" / "adsl.csv", encoding="utf-8")))
        by_person = {}
        for a in adsl:
            by_person.setdefault(a["USUBJID"].split("-P")[0], []).append(a)
        n_exposures = max((len(v) for v in by_person.values()), default=0)
        complete = sorted(p for p, v in by_person.items() if len(v) == n_exposures and all(x["EOTREAS"].startswith("completed") for x in v))
        rng = np.random.default_rng(seed + 13)
        vals = pm.generate(len(complete), source, rng)
        res = pm.analyse(np.asarray(vals["difference"]), test=test, alpha=alpha, two_sided=an.get("sidedness") != "one_sided")
        with open(rd / f"paired_measurements_{source['name']}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["participant", "reference", "index", "difference"])
            for i, p in enumerate(complete):
                w.writerow([p, None if vals["reference"] is None else round(float(vals["reference"][i]), 4),
                            None if vals["index"] is None else round(float(vals["index"][i]), 4), round(float(vals["difference"][i]), 4)])
        locked = all((root / "locked" / f"{s}_v{tag}" / "lock.json").exists() for s in STAGES)
        exits = Counter(a["EOTREAS"] for a in adsl)
        rows.append({"replicate": r, "seed": seed, "generated": n_gen, "eligible": status.count("ELIGIBLE"),
                     "eligible_pct": round(100 * status.count("ELIGIBLE") / n_gen, 3) if n_gen else None,
                     "undetermined": status.count("UNDETERMINED"), "screened_to_target": nns,
                     "enrol_days_to_target": round(enrol_days[target - 1], 1) if len(enrol_days) >= target else None,
                     "participants_enrolled": len(people), "exposure_records": len(cohort), "exposures_per_participant": n_exposures,
                     "completed_all_exposures": len(complete), "usable_pairs": res["n"], "missing_pairs": len(people) - res["n"],
                     "exits_not_completed": "; ".join(f"{k}: {v}" for k, v in exits.items() if not k.startswith("completed")),
                     "endpoint_source": source["name"], "mean_difference": round(res.get("mean_difference", float("nan")), 4),
                     "median_difference": round(res.get("median_difference", float("nan")), 4),
                     "hodges_lehmann": round(res.get("hodges_lehmann", float("nan")), 4), "p_value": res["p_value"],
                     "success": res["success"], "all_stages_locked": locked,
                     **{f"fail_{c}": fails.get(c, 0) for c in sorted(fails)}})
    crit = sorted(crit_names)
    fields = [k for k in rows[0] if not k.startswith("fail_")] + [f"fail_{c}" for c in crit]
    path = out / f"master_simulation_{source['name']}.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval=0)
        w.writeheader()
        w.writerows(rows)
    return path


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])))
