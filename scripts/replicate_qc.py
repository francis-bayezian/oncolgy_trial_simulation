"""Quality control of a replicate experiment (paper step 3): programming failures, not legitimate extremes.

Checks per replicate: completed and every stage locked; ages within the protocol's limits; unique subject ids;
participants = the target number of people, each with the same number of exposure records; exposure days in order and
within the protocol's window between exposures; adverse events not starting after a participant's death or, beyond the
reporting window, after the end of participation; exits other than completion listed by reason. Firewall checks: the
trial is excluded from evidence, absent from the evidence asset's profiles, and no replicate input names its registry
results.

Usage: .venv/Scripts/python.exe scripts/replicate_qc.py ID BASE_VERSION OUT_DIR [MAX_GAP_DAYS]
"""

import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")

STAGES = ("population", "eligibility", "cohorts", "safety", "outputs", "journey", "endpoints", "analysis")
REPORTING_WINDOW = 30


def main(study: str, version: str, out: Path, max_gap: float = 10.0) -> Path:
    from clinical_asset import assets, cutoff
    from clinical_asset.trial.population import age_limits

    spec = json.loads((Path("data/locked") / study / f"studyspec_v{version}" / "studyspec.json").read_text(encoding="utf-8"))
    lo, hi = age_limits(spec)
    target = int(next(x["value"] for x in spec["sample_size"] if x["quantity"] in ("evaluable_target", "target_accrual")))
    root = Path(f"data/trial/runs/{study}/v{version}/replicates")
    issues, per = [], []
    exits = Counter()
    for rd in sorted(root.glob("r[0-9][0-9][0-9]")):
        r = int(rd.name[1:])
        tag = f"{version}-r{r:03d}"
        prob = []
        if not all((root / "locked" / f"{s}_v{tag}" / "lock.json").exists() for s in STAGES):
            prob.append("not every stage locked")
        adsl = list(csv.DictReader(open(rd / "journey" / "adsl.csv", encoding="utf-8")))
        ids = [a["USUBJID"] for a in adsl]
        if len(ids) != len(set(ids)):
            prob.append("duplicate subject ids")
        people = Counter(i.split("-P")[0] for i in ids)
        if len(people) != target:
            prob.append(f"{len(people)} participants, target {target}")
        if len(set(people.values())) != 1:
            prob.append(f"exposure records per participant vary: {sorted(set(people.values()))}")
        ages = [float(a["AGE"]) for a in adsl]
        if (lo is not None and min(ages) < lo) or (hi is not None and max(ages) > hi):
            prob.append(f"age outside protocol limits [{lo}, {hi}]: {min(ages):.1f}-{max(ages):.1f}")
        by = {}
        for a in adsl:
            by.setdefault(a["USUBJID"].split("-P")[0], []).append(a)
            exits[a["EOTREAS"]] += 1
            if a["TRTSDY"] and a["TRTEDY"] and float(a["TRTEDY"]) < float(a["TRTSDY"]):
                prob.append(f"{a['USUBJID']} ends before it starts")
        for p, v in by.items():
            days = sorted(float(x["TRTEDY"]) for x in v if x["EOTREAS"].startswith("completed") and x["TRTEDY"])
            if len(days) == len(v) and len(days) > 1 and (days[-1] - days[0] > max_gap):
                prob.append(f"{p}: exposures {days[-1] - days[0]:.0f} days apart (> {max_gap:g})")
        ae = list(csv.DictReader(open(rd / "journey" / "adae.csv", encoding="utf-8"))) if (rd / "journey" / "adae.csv").exists() else []
        end = {a["USUBJID"]: (float(a["TRTEDY"] or 0), float(a["DTHDY"]) if a.get("DTHDY") else None) for a in adsl}
        for x in ae:
            e_end, death = end.get(x["USUBJID"], (None, None))
            start = float(x.get("AESTDY") or 0)
            if death is not None and start > death:
                prob.append(f"{x['USUBJID']}: AE after death")
            elif e_end is not None and start > e_end + REPORTING_WINDOW:
                prob.append(f"{x['USUBJID']}: AE beyond the reporting window")
        per.append({"replicate": r, "problems": len(prob)})
        issues += [{"replicate": r, "problem": p} for p in prob]
    # firewall: the trial is never evidence
    excluded = study in cutoff.excluded()
    db = assets.path("asset") / "asset.sqlite"
    in_asset = None
    if db.exists():
        con = sqlite3.connect(db)
        tables = [t for (t,) in con.execute("select name from sqlite_master where type='table'")]
        in_asset = any(con.execute(f"select 1 from {t} where nct_id = ? limit 1", (study,)).fetchone()
                       for t in tables if "nct_id" in [c[1] for c in con.execute(f"pragma table_info({t})")])
    firewall = {"excluded_from_evidence": excluded, "present_in_evidence_asset": in_asset,
                "replicate_inputs_name_registry_results": any("holdout_comparison" in (p.read_text(encoding="utf-8", errors="ignore"))
                                                              for p in root.glob("locked/*/lock.json"))}
    out.mkdir(parents=True, exist_ok=True)
    doc = {"study": study, "replicates": len(per), "replicates_with_problems": sum(1 for p in per if p["problems"]),
           "problems_by_kind": Counter(i["problem"].split(":")[0] if ":" in i["problem"] and i["problem"].startswith("S") else i["problem"] for i in issues),
           "exit_reasons_all_records": dict(exits), "firewall": firewall, "issues": issues[:500]}
    (out / "qc_report.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    L = [f"# QC of {len(per)} replicates: {study} (base v{version})", "",
         f"Replicates with problems: **{doc['replicates_with_problems']}**.", "", "## Problems by kind", ""]
    L += [f"- {k}: {v}" for k, v in sorted(doc["problems_by_kind"].items(), key=lambda kv: -kv[1])] or ["- none"]
    L += ["", "## Exit reasons (all exposure records)", ""] + [f"- {k}: {v}" for k, v in exits.most_common()]
    L += ["", "## Firewall", ""] + [f"- {k}: {v}" for k, v in firewall.items()]
    (out / "qc_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out / "qc_report.md"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 10.0))
