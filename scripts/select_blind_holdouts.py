"""Select the sealed blind-test trials: one terminated for poor accrual, one terminated for safety, one completed.

Blinding: the script prints nothing about any candidate. It writes
* data/manifest/blind_holdout.json: the three NCT IDs in shuffled order, the selection rule, and a salted SHA-256
  commitment of the category of each ID (the categories themselves are not stored anywhere);
* protocols/blind/BLIND_1.pdf .. BLIND_3.pdf: the registry-hosted protocol documents, named in the shuffled order.
At unsealing, the categories are re-derived from the registry and checked against the commitment.

Candidates: the operational-asset base criteria (neoplasms, interventional, treatment, Phase 2 or 3), results posted,
a protocol document hosted by ClinicalTrials.gov, not in the evidence corpus (data/raw/ctgov) and not already held out.
"""

import hashlib
import json
import random
import secrets
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clinical_asset.planning.operational import (
    BASE_QUERY,
    accrual_reason,
    holdout_ids,
)

API = "https://clinicaltrials.gov/api/v2/studies"
SAFETY = __import__("re").compile(r"(?:^|[.!?;,])(?:(?!\b(?:no|not|without|never|neither)\b)[^.!?;,])*(?:safety|toxicit|adverse|side[- ]effect|tolerab|death)", __import__("re").IGNORECASE)
QUERIES = {
    "terminated_accrual": " AND AREA[OverallStatus]TERMINATED",
    "terminated_safety": " AND AREA[OverallStatus]TERMINATED",
    "completed": " AND AREA[OverallStatus]COMPLETED",
}


def candidates(extra: str, session: requests.Session) -> list[dict]:
    out, token = [], None
    while True:
        params = {"query.term": BASE_QUERY + extra + " AND AREA[HasResults]true AND AREA[LargeDocHasProtocol]true",
                  "fields": "NCTId,WhyStopped,LargeDocFilename,LargeDocHasProtocol", "pageSize": 1000}
        if token:
            params["pageToken"] = token
        page = session.get(API, params=params, timeout=120).json()
        out += page.get("studies", [])
        token = page.get("nextPageToken")
        if not token:
            return out


def main(seed: int = 20260928) -> None:
    root = Path(__file__).resolve().parents[1]
    held = holdout_ids(root / "data/manifest/holdout_test_trials.json", root / "data/holdout_comparison")
    corpus = {p.stem for p in (root / "data/raw/ctgov").glob("NCT*.json")}
    session = requests.Session()
    session.headers.update({"User-Agent": "ClinicalEvidenceAsset/0.1 (research)"})
    rng = random.Random(seed)
    picks = []
    for category, extra in QUERIES.items():
        pool = []
        for s in candidates(extra, session):
            nct = s["protocolSection"]["identificationModule"]["nctId"]
            why = s["protocolSection"].get("statusModule", {}).get("whyStopped") or ""
            docs = [d for d in (s.get("documentSection", {}).get("largeDocumentModule", {}).get("largeDocs") or []) if d.get("hasProtocol")]
            if nct in held or nct in corpus or not docs:
                continue
            if category == "terminated_accrual" and not (accrual_reason(why) and not SAFETY.search(why)):
                continue
            if category == "terminated_safety" and not (SAFETY.search(why) and not accrual_reason(why)):
                continue
            pool.append((nct, docs[0]["filename"]))
        pool.sort()
        picks.append((category, *rng.choice(pool)))
    rng.shuffle(picks)
    salt = secrets.token_hex(16)
    out_dir = root / "protocols/blind"
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for k, (category, nct, filename) in enumerate(picks, 1):
        url = f"https://cdn.clinicaltrials.gov/large-docs/{nct[-2:]}/{nct}/{filename}"
        pdf = session.get(url, timeout=300)
        pdf.raise_for_status()
        path = out_dir / f"BLIND_{k}.pdf"
        path.write_bytes(pdf.content)
        entries.append({"label": f"BLIND_{k}", "nct_id": nct, "protocol_file": str(path.relative_to(root)).replace("\\", "/"),
                        "protocol_sha256": hashlib.sha256(pdf.content).hexdigest(),
                        "category_commitment": hashlib.sha256(f"{salt}|{nct}|{category}".encode()).hexdigest()})
    manifest = {"purpose": "sealed blind test: one trial terminated for poor accrual, one terminated for safety, one completed (order shuffled)",
                "selection": {"base_query": BASE_QUERY, "also": "results posted; protocol document hosted by ClinicalTrials.gov; not in data/raw/ctgov; "
                              "not already held out", "seed": seed},
                "salt": salt, "nct_ids": [e["nct_id"] for e in entries], "trials": entries,
                "unseal": "category_commitment = sha256(salt|nct_id|category) with category in {terminated_accrual, terminated_safety, completed}"}
    (root / "data/manifest/blind_holdout.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({"written": ["data/manifest/blind_holdout.json"] + [e["protocol_file"] for e in entries]}, indent=1))


if __name__ == "__main__":
    main()
