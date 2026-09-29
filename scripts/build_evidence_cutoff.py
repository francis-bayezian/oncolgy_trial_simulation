"""The evidence cut-off manifest for the temporal evaluation: every trial whose information became available on or after
T0 is excluded from every evidence source, together with the showcase trial itself.

* evidence corpus (data/raw/ctgov, V1 evidence table, V3 parameters, safety asset): results first posted >= T0;
* operational corpus (accrual and failure models): completion (else primary completion) >= T0, or no date;
* oncology results corpus (baseline and journey evidence): results first posted >= T0;
* the showcase trial (data/manifest/temporal_showcase_v2.json) and the standing holdout manifest.

Written in the holdout-file format ({"nct_ids": [...]}) that the asset builders accept, plus T0 and counts. It also
writes data/raw/ctgov_t0/: the evidence-corpus files before T0 (copies), for builders that read a directory.
"""

import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    show = json.loads((ROOT / "data/manifest/temporal_showcase_v2.json").read_text(encoding="utf-8"))
    t0 = show["t0"]
    out = ROOT / f"data/manifest/evidence_cutoff_{t0[:4]}.json"
    excl: dict[str, set] = {"evidence_corpus": set(), "operational_corpus": set(), "oncology_results_corpus": set()}
    raw_t0 = ROOT / "data/raw/ctgov_t0"
    raw_t0.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "data/raw/ctgov").glob("NCT*.json"):
        st = json.loads(f.read_text(encoding="utf-8"))["protocolSection"]["statusModule"]
        if ((st.get("resultsFirstPostDateStruct") or {}).get("date") or "9999") >= t0:
            excl["evidence_corpus"].add(f.stem)
        elif not (raw_t0 / f.name).exists():
            shutil.copy2(f, raw_t0 / f.name)
    with open(ROOT / "data/raw/ctgov_operational/corpus.jsonl", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            st = s["protocolSection"]["statusModule"]
            d = (st.get("completionDateStruct") or st.get("primaryCompletionDateStruct") or {}).get("date") or "9999"
            if d >= t0:
                excl["operational_corpus"].add(s["protocolSection"]["identificationModule"]["nctId"])
    with gzip.open(ROOT / "data/raw/ctgov_oncology_results/corpus.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            st = s["protocolSection"]["statusModule"]
            if ((st.get("resultsFirstPostDateStruct") or {}).get("date") or "9999") >= t0:
                excl["oncology_results_corpus"].add(s["protocolSection"]["identificationModule"]["nctId"])
    standing = set(json.loads((ROOT / "data/manifest/holdout_test_trials.json").read_text(encoding="utf-8"))["nct_ids"])
    ids = sorted(standing | {show["chosen"]["nct_id"]} | set().union(*excl.values()))
    doc = {"t0": t0, "showcase": show["chosen"]["nct_id"], "nct_ids": ids,
           "counts": {k: len(v) for k, v in excl.items()} | {"standing_holdout": len(standing), "total": len(ids)},
           "by_source": {k: sorted(v) for k, v in excl.items()},
           "note": "information on or after T0 is excluded from every evidence source; the showcase trial is excluded everywhere"}
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(out.relative_to(ROOT)), **doc["counts"], "raw_t0_files": len(list(raw_t0.glob('NCT*.json')))}, indent=1))


if __name__ == "__main__":
    main()
