"""Adverse-event term -> system organ class, from the registry's own adverse-event tables (each reported term with the
organ system the trial reported it under), for the FDA standard safety tables (SOC / preferred-term layout).

Source: the oncology results corpus (data/raw/ctgov_oncology_results/corpus.jsonl.gz). Trials started in 2023 or later
and evaluated trials are skipped (clinical_asset.cutoff.excluded). A term's class is the organ system it is reported under
most often; the share of that choice is kept so ambiguous terms are visible. Terms are keyed casefolded with
underscores and runs of spaces collapsed. No model is used.

Usage: .venv/Scripts/python.exe scripts/build_ae_soc_map.py
"""

import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

OUT = Path("data/reference_derived/ae_term_soc.json")


def key(term: str) -> str:
    return " ".join(re.sub(r"[_]+", " ", (term or "")).casefold().split())


def main() -> None:
    from clinical_asset.cutoff import excluded

    drop = excluded()
    votes: dict[str, Counter] = defaultdict(Counter)
    trials = 0
    with gzip.open("data/raw/ctgov_oncology_results/corpus.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            nct = s["protocolSection"]["identificationModule"]["nctId"]
            if nct in drop:
                continue
            ae = (s.get("resultsSection") or {}).get("adverseEventsModule") or {}
            seen = False
            for group in ("seriousEvents", "otherEvents"):
                for e in ae.get(group) or []:
                    if e.get("term") and e.get("organSystem"):
                        votes[key(e["term"])][e["organSystem"]] += 1
                        seen = True
            trials += seen
    out = {}
    for term, c in votes.items():
        soc, n = c.most_common(1)[0]
        out[term] = {"soc": soc, "share": round(n / sum(c.values()), 3), "reports": sum(c.values())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"created": date.today().isoformat(), "source": "ClinicalTrials.gov adverse-event tables, oncology results corpus",
                               "trials": trials, "terms": len(out), "map": out}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"trials": trials, "terms": len(out)}))


if __name__ == "__main__":
    main()
