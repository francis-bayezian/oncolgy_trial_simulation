"""Permanent start-date hold-out (user decision 2026-10-06): every trial that STARTED on or after 2023-01-01, in every
registry corpus the assets read, is never evidence. Writes data/manifest/excluded_start2023.json in the holdout-file
format ({"nct_ids": [...]}); clinical_asset.cutoff.evaluated_trials() reads it, so every evidence reader drops them.

Corpora scanned: the in-scope candidates (scripts/build_corpus_v2_manifest.py), the operational corpus (accrual and
failure models) and the oncology results corpus (baseline and journey evidence). A trial with no start date is kept
out as well (its timing cannot be shown to precede the cut-off).

Usage: .venv/Scripts/python.exe scripts/build_start_cutoff.py
"""

import gzip
import json
from collections import Counter
from datetime import date
from pathlib import Path

CUTOFF = "2023-01-01"


def _start(study: dict) -> str | None:
    d = ((study.get("protocolSection") or {}).get("statusModule") or {}).get("startDateStruct") or {}
    return d.get("date")


def _late(start: str | None) -> bool:
    if not start:
        return True
    return (start if len(start) == 10 else start + "-01") >= CUTOFF


def main() -> None:
    late: dict[str, set] = {"candidates": set(), "operational_corpus": set(), "oncology_results_corpus": set()}
    cand = Path("data/raw/corpus_v2_candidates.json")
    if cand.exists():
        for s in json.loads(cand.read_text(encoding="utf-8"))["studies"]:
            if _late(s.get("start")):
                late["candidates"].add(s["nct_id"])
    op = Path("data/raw/ctgov_operational/corpus.jsonl")
    if op.exists():
        with open(op, encoding="utf-8") as fh:
            for line in fh:
                s = json.loads(line)
                if _late(_start(s)):
                    late["operational_corpus"].add(s["protocolSection"]["identificationModule"]["nctId"])
    onc = Path("data/raw/ctgov_oncology_results/corpus.jsonl.gz")
    if onc.exists():
        with gzip.open(onc, "rt", encoding="utf-8") as fh:
            for line in fh:
                s = json.loads(line)
                if _late(_start(s)):
                    late["oncology_results_corpus"].add(s["protocolSection"]["identificationModule"]["nctId"])
    ids = sorted(set().union(*late.values()))
    doc = {"rule": f"started on or after {CUTOFF} (or no start date): never evidence", "created": date.today().isoformat(),
           "cutoff": CUTOFF, "nct_ids": ids, "counts": {k: len(v) for k, v in late.items()} | {"total": len(ids)}}
    Path("data/manifest/excluded_start2023.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps(doc["counts"], indent=1))


if __name__ == "__main__":
    main()
