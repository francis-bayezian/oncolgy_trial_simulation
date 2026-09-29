"""Download every interventional oncology treatment trial with posted results from ClinicalTrials.gov (full records:
protocol and all result sections), as gzip JSON lines. Resumable: the page token of the last completed page is saved,
and a rerun continues from it.

This corpus is the source for (1) baseline-measure evidence (labs, performance status, body size, disease
characteristics) and (2) rebuilding evidence as of a cut-off date T0 for the temporal evaluation: every record keeps
its results-first-posted date.

Usage: .venv/Scripts/python.exe scripts/fetch_oncology_results_corpus.py [--out data/raw/ctgov_oncology_results]
"""

import argparse
import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://clinicaltrials.gov/api/v2/studies"
QUERY = ("AREA[StudyType]INTERVENTIONAL AND (AREA[ConditionMeshTerm]Neoplasms OR AREA[ConditionAncestorTerm]Neoplasms) "
         "AND AREA[DesignPrimaryPurpose]TREATMENT")
FILTER = "AREA[HasResults]true"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw/ctgov_oncology_results")
    ap.add_argument("--page-size", type=int, default=100)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    state_file, data_file = out / "fetch_state.json", out / "corpus.jsonl.gz"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {
        "query": QUERY, "filter": FILTER, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "token": None, "pages": 0, "studies": 0, "done": False}
    if state["done"]:
        print("already complete:", state["studies"], "studies")
        return
    s = requests.Session()
    s.headers.update({"User-Agent": "ClinicalEvidenceAsset/0.1 (research)"})
    total = s.get(API, params={"query.term": QUERY, "filter.advanced": FILTER, "countTotal": "true", "pageSize": 1,
                               "fields": "NCTId"}, timeout=120).json().get("totalCount")
    state["total_at_start"] = total
    while True:
        params = {"query.term": QUERY, "filter.advanced": FILTER, "pageSize": a.page_size}
        if state["token"]:
            params["pageToken"] = state["token"]
        for attempt in range(6):
            try:
                r = s.get(API, params=params, timeout=300)
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(2 ** attempt)
        r.raise_for_status()
        page = r.json()
        with gzip.open(data_file, "at", encoding="utf-8") as fh:        # append the whole page, then advance the token
            for st in page.get("studies", []):
                fh.write(json.dumps(st, ensure_ascii=False) + "\n")
        state["studies"] += len(page.get("studies", []))
        state["pages"] += 1
        state["token"] = page.get("nextPageToken")
        state["done"] = not state["token"]
        if state["done"]:
            state["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        state_file.write_text(json.dumps(state, indent=1), encoding="utf-8")
        print(f"page {state['pages']}: {state['studies']} / {total}", flush=True)
        if state["done"]:
            break


if __name__ == "__main__":
    main()
