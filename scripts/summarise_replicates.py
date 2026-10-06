"""Summarise N replicate simulations of one protocol (scripts/run_replicates.sh): every trial-level number as
p10 / p30 / p50 / p70 / p90 across the replicates, and every replicate's simulated patients stacked with a REPLICATE
column.

Numbers summarised (any protocol, by path): eligibility (eligible share, status counts), recruitment, the endpoint
stage's participant flow and per-arm results, the analysis stage's efficacy, comparisons and censoring, the FDA overview
of adverse events (Table 6, percent of patients by arm), and the subgroup rows (n, response, PFS / OS medians, safety
counts).

Usage: .venv/Scripts/python.exe scripts/summarise_replicates.py ID BASE_VERSION
  -> data/trial/runs/<ID>/v<BASE>/replicates/summary/{replicate_summary.md, replicate_summary.csv, all_*.csv}
"""

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

Q = (10, 30, 50, 70, 90)


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def flatten(x, prefix: str, out: dict) -> None:
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out[prefix] = float(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(x, list) and len(x) <= 12 and all(isinstance(v, (int, float)) for v in x):
        for i, v in enumerate(x):
            flatten(v, f"{prefix}[{i}]", out)


def table_percent(path: Path, label: str, out: dict) -> None:
    """'n (pct)' cells of an FDA table as percent by row and arm."""
    if not path.exists():
        return
    rows = list(csv.reader(open(path, encoding="utf-8")))
    head = rows[0]
    for r in rows[1:]:
        for col, cell in zip(head[1:], r[1:]):
            m = re.match(r"\s*\d+\s*\(([\d.]+)\)", cell or "")
            if m:
                out[f"{label}.{r[0].strip()}.{col.split(' ')[0]} %"] = float(m.group(1))


def replicate_numbers(rd: Path) -> dict:
    out = {}
    el = _load(rd / "eligibility" / "eligibility_summary.json") or {}
    flatten({k: v for k, v in (el.get("summary") or {}).items() if k in ("eligible_share", "status_counts", "patients")}, "eligibility", out)
    rs = _load(rd / "cohorts" / "recruitment_summary.json") or {}
    flatten(rs.get("summary") or {}, "recruitment", out)
    ep = _load(rd / "endpoints" / "endpoint_results.json") or {}
    flatten(ep.get("participant_flow") or {}, "participant_flow", out)
    for e in ep.get("endpoints") or []:
        name = (e.get("endpoint") or e.get("variable") or "endpoint")[:60]
        flatten(e.get("by_arm") or {}, f"endpoint[{name}]", out)
        flatten(e.get("observed") or {}, f"endpoint[{name}].observed", out)
    an = _load(rd / "analysis" / "analysis_results.json") or {}
    if not (an.get("efficacy") or {}).get("status"):
        flatten(an.get("efficacy") or {}, "efficacy", out)
    flatten(an.get("comparisons") or {}, "comparison", out)
    table_percent(rd / "analysis" / "tables" / "table_6.csv", "AE overview", out)
    sg = _load(rd / "analysis" / "subgroups" / "subgroups.json") or {}
    for r in sg.get("rows") or []:
        key = f"subgroup[{r['factor'][:40]} = {r['level']}][{r['arm']}]"
        out[f"{key}.n"] = r["n"]
        for code in ("objective_response", "disease_control"):
            if (r.get(code) or {}).get("rate") is not None:
                out[f"{key}.{code} rate"] = r[code]["rate"]
        for code in ("PFS", "OS"):
            if (r.get(code) or {}).get("median_months") is not None:
                out[f"{key}.{code} median months"] = r[code]["median_months"]
        for k, v in (r.get("safety") or {}).items():
            out[f"{key}.{k} %"] = 100 * v / r["n"] if r["n"] else 0.0
    return out


def stack(reps: list[Path], rel: str, out: Path) -> int:
    rows, fields = 0, None
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = None
        for rd in reps:
            f = rd / rel
            if not f.exists() or not f.stat().st_size:
                continue
            with open(f, encoding="utf-8") as src:
                for r in csv.DictReader(src):
                    if w is None:
                        fields = ["REPLICATE", *r.keys()]
                        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                        w.writeheader()
                    w.writerow({"REPLICATE": rd.name, **r})
                    rows += 1
    return rows


def main(study: str, version: str) -> Path:
    root = Path(f"data/trial/runs/{study}/v{version}/replicates")
    reps = sorted(d for d in root.glob("r[0-9][0-9][0-9]") if (d / "analysis" / "analysis_results.json").exists())
    values = defaultdict(list)
    for rd in reps:
        for k, v in replicate_numbers(rd).items():
            values[k].append(v)
    out = root / "summary"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for k in sorted(values):
        v = np.array(values[k])
        rows.append([k, len(v), *[round(float(np.percentile(v, q)), 4) for q in Q]])
    with open(out / "replicate_summary.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([["quantity", "replicates", *[f"p{q}" for q in Q]], *rows])
    stacked = {name: stack(reps, rel, out / f"all_{name}.csv") for name, rel in
               (("adsl", "journey/adsl.csv"), ("adae", "journey/adae.csv"), ("adtte", "analysis/adam/adtte.csv"),
                ("adrs", "analysis/adam/adrs.csv"))}
    L = [f"# {study}: {len(reps)} replicate simulations (base v{version})", "",
         "Each replicate draws new patients and a new trial from the same locked extraction (StudySpec, facts, outcome "
         "model). Every number below is its spread ACROSS the simulated trials: p10 / p30 / p50 / p70 / p90.", "",
         "Simulated patients of every replicate (REPLICATE column): " + ", ".join(f"`all_{k}.csv` ({v} rows)" for k, v in stacked.items()) + ".", ""]
    sections = [("Eligibility and screening", "eligibility"), ("Recruitment", "recruitment"), ("Participant flow", "participant_flow"),
                ("Endpoints by arm", "endpoint["), ("Efficacy by arm", "efficacy"), ("Arm vs control", "comparison"),
                ("Adverse events overview (FDA Table 6, % of patients)", "AE overview"), ("Subgroups", "subgroup[")]
    for title, prefix in sections:
        sel = [r for r in rows if r[0].startswith(prefix)]
        if not sel:
            continue
        L += [f"## {title}", "", "| Quantity | n | p10 | p30 | p50 | p70 | p90 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        L += [f"| {r[0][len(prefix):] if prefix.endswith('[') else r[0]} | {r[1]} | " + " | ".join(f"{x:g}" for x in r[2:]) + " |"
              for r in sel[:400]]
        L.append("")
    (out / "replicate_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out / "replicate_summary.md"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2]))
