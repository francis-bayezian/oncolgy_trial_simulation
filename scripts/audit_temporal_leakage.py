"""Leakage audit for every evaluated protocol: could the evidence behind a prediction contain the trial itself, or
information published after the trial was planned?

For each development protocol (data/manifest/development_protocols.json) it records, from the trial's registry record:
planning date (first posted), start, primary completion and results first posted; and, for each evidence source,
whether the trial itself is in it and how much of that source was published after the trial's planning date:

* evidence corpus (data/raw/ctgov, the source of the evidence table and V3 parameters) and evidence-table rows;
* operational corpus (accrual and failure models) and the fitted operational tables;
* safety asset arm table (per-event models).

"Published after planning" uses each source trial's results-first-posted date for the evidence corpus (registry results
are the evidence) and its completion date for the operational corpus (its final status is the evidence; that corpus
holds no results dates).
Output: data/validation/leakage_audit.csv and leakage_audit.md.
"""

import csv
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def dates(study: dict) -> dict:
    s = study["protocolSection"]["statusModule"]
    g = lambda k: (s.get(k) or {}).get("date")  # noqa: E731
    return {"first_posted": g("studyFirstPostDateStruct"), "start": g("startDateStruct"),
            "primary_completion": g("primaryCompletionDateStruct"), "results_first_posted": g("resultsFirstPostDateStruct")}


def norm(d):
    """Registry dates are 'YYYY-MM' or 'YYYY-MM-DD'; compare as 'YYYY-MM-DD' (month dates at the 1st)."""
    return None if not d else (d if len(d) == 10 else d + "-01")


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    protocols = json.loads((ROOT / "data/manifest/development_protocols.json").read_text(encoding="utf-8"))["protocols"]

    ev_results = {}
    for f in (ROOT / "data/raw/ctgov").glob("NCT*.json"):
        ev_results[f.stem] = norm(dates(json.loads(f.read_text(encoding="utf-8")))["results_first_posted"])
    ev = pq.read_table(ROOT / "data/simulation_parameters_v1/evidence_table.parquet", columns=["nct_id"])
    ev_counts = {}
    for n in ev["nct_id"].to_pylist():
        ev_counts[n] = ev_counts.get(n, 0) + 1

    op_results, op_ids = {}, set()
    with open(ROOT / "data/raw/ctgov_operational/corpus.jsonl", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            n = s["protocolSection"]["identificationModule"]["nctId"]
            op_ids.add(n)
            st = s["protocolSection"]["statusModule"]      # final status is known at completion (this corpus has no results dates)
            op_results[n] = norm((st.get("completionDateStruct") or st.get("primaryCompletionDateStruct") or {}).get("date"))
    op_asset = ROOT / "data/locked/planning_asset/operational_v2.2.0"
    op_fitted = set(pq.read_table(op_asset / "trial_outcomes.parquet", columns=["nct_id"])["nct_id"].to_pylist())
    op_rates = set(pq.read_table(op_asset / "study_level_rates.parquet", columns=["nct_id"])["nct_id"].to_pylist())
    safety_arms = json.loads((ROOT / "data/safety_asset_v3_1/arm_table.json").read_text(encoding="utf-8"))["arms"]
    safety_ids = {a["nct_id"] for a in safety_arms}

    rows = []
    for p in protocols:
        n = p["nct_id"]
        reg = json.loads((ROOT / "data/holdout_comparison" / f"{n}.json").read_text(encoding="utf-8"))
        d = dates(reg)
        plan = norm(d["first_posted"])

        def after(results):
            posted = [r for r in results.values() if r]
            return sum(r > plan for r in posted), len(posted)
        ev_after, ev_total = after(ev_results)
        op_after, op_total = after(op_results)
        rows.append({
            "protocol": p["id"], "nct_id": n, "planning_date_first_posted": d["first_posted"], "start": d["start"],
            "primary_completion": d["primary_completion"], "results_first_posted": d["results_first_posted"],
            "in_evidence_corpus": n in ev_results, "evidence_table_rows": ev_counts.get(n, 0),
            "in_operational_corpus": n in op_ids, "in_failure_model_fit": n in op_fitted, "in_accrual_model_fit": n in op_rates,
            "in_safety_asset": n in safety_ids,
            "evidence_trials_with_results_after_planning": ev_after, "evidence_trials_with_results": ev_total,
            "operational_trials_with_results_after_planning": op_after, "operational_trials_with_results": op_total,
        })

    out = ROOT / "data/validation"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "leakage_audit.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    self_leak = [r["protocol"] for r in rows if r["in_evidence_corpus"] or r["evidence_table_rows"] or r["in_failure_model_fit"]
                 or r["in_accrual_model_fit"] or r["in_safety_asset"]]
    lines = ["# Leakage audit", "",
             "Generated by `scripts/audit_temporal_leakage.py`. Two questions per evaluated trial: is the trial itself in any "
             "evidence source (self-leakage), and how much of each source was published after the trial was planned "
             "(temporal leakage: evidence a planner at the time could not have had).", "",
             f"**Self-leakage:** {'none: no evaluated trial is in any evidence source or fitted table' if not self_leak else 'PRESENT in ' + ', '.join(self_leak)}.", "",
             "| Protocol | NCT | Planned (first posted) | Results first posted | Evidence corpus: results after planning | Operational corpus: completed after planning |",
             "| --- | --- | --- | --- | ---: | ---: |"]
    for r in rows:
        lines.append(f"| {r['protocol']} | {r['nct_id']} | {r['planning_date_first_posted']} | {r['results_first_posted']} | "
                     f"{r['evidence_trials_with_results_after_planning']:,} of {r['evidence_trials_with_results']:,} "
                     f"({r['evidence_trials_with_results_after_planning'] / r['evidence_trials_with_results']:.0%}) | "
                     f"{r['operational_trials_with_results_after_planning']:,} of {r['operational_trials_with_results']:,} "
                     f"({r['operational_trials_with_results_after_planning'] / max(1, r['operational_trials_with_results']):.0%}) |")
    lines += ["", "**Reading.** The evidence sources were built without a planning-date cut-off, so every evaluated trial was "
              "predicted with evidence partly published after it was planned. These comparisons are retrospective and exploratory, "
              "not forecasts. A clean temporal evaluation must rebuild each source from trials whose results were posted before a "
              "cut-off date T0 and evaluate trials planned before T0 whose results were posted after it. Public information "
              "about a trial may also be present in the language model used by the compiler; a local lock does not exclude that."]
    (out / "leakage_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
