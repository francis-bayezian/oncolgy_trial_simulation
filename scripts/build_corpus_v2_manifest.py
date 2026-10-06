"""Evidence corpus v2: 5,000 oncology trials started before 2023, and the 2023+ hold-out (user decision 2026-10-06).

Scope: interventional, neoplasm conditions, phases early 1 to 4, primary purpose treatment, diagnostic or supportive
care, results posted on ClinicalTrials.gov.

* Hold-out: every in-scope trial that STARTED on or after 2023-01-01. It is never evidence; it is the test set the
  rebuilt pipeline is scored on (data/manifest/holdout_start2023.json).
* Evidence selection (data/manifest/corpus_v2_5000.json), all started before 2023 and never an evaluated trial:
  1. the 1,000 trials of evidence asset v1 that are in scope (already built and validated);
  2. every diagnostic, supportive-care, early phase 1 and phase 4 trial (rare in the corpus, needed for their designs);
  3. the rest by a seeded random sample of treatment trials stratified by phase x disease family, proportional to the
     pool, up to TARGET.

Usage: .venv/Scripts/python.exe scripts/build_corpus_v2_manifest.py [--target 5000] [--seed 20261006]
"""

import argparse
import json
import random
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

API = "https://clinicaltrials.gov/api/v2/studies"
QUERY = ("AREA[StudyType]INTERVENTIONAL AND (AREA[ConditionMeshTerm]Neoplasms OR AREA[ConditionAncestorTerm]Neoplasms) AND "
         "(AREA[DesignPrimaryPurpose]TREATMENT OR AREA[DesignPrimaryPurpose]DIAGNOSTIC OR AREA[DesignPrimaryPurpose]SUPPORTIVE_CARE) AND "
         "(AREA[Phase]EARLY_PHASE1 OR AREA[Phase]PHASE1 OR AREA[Phase]PHASE2 OR AREA[Phase]PHASE3 OR AREA[Phase]PHASE4)")
FILTER = "AREA[HasResults]true"
FIELDS = "NCTId,OverallStatus,Phase,DesignPrimaryPurpose,StartDate,ResultsFirstPostDate,ConditionMeshTerm,ConditionAncestorTerm,EnrollmentCount"
CUTOFF = "2023-01-01"
RARE_PURPOSES = {"DIAGNOSTIC", "SUPPORTIVE_CARE"}
RARE_PHASES = {"EARLY_PHASE1", "PHASE4"}


def fetch_candidates(cache: Path) -> list[dict]:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["studies"]
    s = requests.Session()
    s.headers.update({"User-Agent": "ClinicalEvidenceAsset/0.2 (research)"})
    out, token = [], None
    while True:
        params = {"query.term": QUERY, "filter.advanced": FILTER, "fields": FIELDS, "pageSize": 1000}
        if token:
            params["pageToken"] = token
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
        for st in page.get("studies", []):
            ps = st.get("protocolSection", {})
            design = ps.get("designModule", {})
            status = ps.get("statusModule", {})
            cond = st.get("derivedSection", {}).get("conditionBrowseModule", {})
            out.append({"nct_id": ps.get("identificationModule", {}).get("nctId"), "phases": design.get("phases") or [],
                        "status": status.get("overallStatus"),
                        "purpose": (design.get("designInfo") or {}).get("primaryPurpose"),
                        "start": (status.get("startDateStruct") or {}).get("date"),
                        "results_first_posted": (status.get("resultsFirstPostDateStruct") or {}).get("date"),
                        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
                        "mesh": [m.get("term") for m in cond.get("meshes") or []] + [m.get("term") for m in cond.get("ancestors") or []]})
        token = page.get("nextPageToken")
        if not token:
            break
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"query": QUERY, "filter": FILTER, "retrieved": date.today().isoformat(), "studies": out}), encoding="utf-8")
    return out


def started_before(start: str | None, cutoff: str = CUTOFF) -> bool | None:
    if not start:
        return None
    s = start if len(start) == 10 else start + "-01"
    return s < cutoff


def family(mesh: list[str]) -> str:
    from clinical_asset.planning.operational import family_of_terms

    mapping_file = Path("data/spa_work/mesh_disease_families.json")
    mapping = json.loads(mapping_file.read_text(encoding="utf-8")) if mapping_file.exists() else {}
    return family_of_terms([m for m in mesh if m], mapping)[0]


def main() -> None:
    from clinical_asset.cutoff import evaluated_trials

    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20261006)
    a = ap.parse_args()
    studies = fetch_candidates(Path("data/raw/corpus_v2_candidates.json"))
    evaluated = set(evaluated_trials())

    holdout = [s for s in studies if started_before(s["start"]) is False]
    # evidence quality: completed trials only, as evidence asset v1 (terminated trials are covered by the operational asset)
    pool = [s for s in studies if started_before(s["start"]) is True and s["nct_id"] not in evaluated and s.get("status") == "COMPLETED"]
    undated = [s["nct_id"] for s in studies if started_before(s["start"]) is None]
    Path("data/manifest/holdout_start2023.json").write_text(json.dumps({
        "rule": f"in-scope oncology trials with posted results that STARTED on or after {CUTOFF}: never evidence; the test set",
        "created": date.today().isoformat(), "query": QUERY, "nct_ids": sorted(s["nct_id"] for s in holdout),
        "trials": sorted(holdout, key=lambda x: x["nct_id"])}, indent=1), encoding="utf-8")

    v1 = {p.stem for p in Path("data/raw/ctgov").glob("NCT*.json")}
    by_id = {s["nct_id"]: s for s in pool}
    chosen: dict[str, str] = {}
    for nid in sorted(v1 & set(by_id)):
        chosen[nid] = "evidence asset v1"
    for s in pool:
        if s["nct_id"] not in chosen and (s["purpose"] in RARE_PURPOSES or set(s["phases"]) & RARE_PHASES):
            chosen[s["nct_id"]] = "rare purpose or phase (all included)"
    fam_cache = {}
    strata: dict[tuple, list] = defaultdict(list)
    for s in pool:
        if s["nct_id"] in chosen:
            continue
        key = tuple(s["mesh"][:6])
        if key not in fam_cache:
            fam_cache[key] = family(s["mesh"])
        strata[("+".join(sorted(s["phases"])), fam_cache[key])].append(s["nct_id"])
    remaining = max(0, a.target - len(chosen))
    total = sum(len(v) for v in strata.values())
    rng = random.Random(a.seed)
    quotas = {k: remaining * len(v) / total for k, v in strata.items()}
    alloc = {k: int(q) for k, q in quotas.items()}
    for k in sorted(quotas, key=lambda k: alloc[k] - quotas[k])[: remaining - sum(alloc.values())]:
        alloc[k] += 1
    for k, ids in sorted(strata.items()):
        for nid in rng.sample(sorted(ids), min(alloc[k], len(ids))):
            chosen[nid] = "stratified sample (phase x disease family)"

    trials = [{"nct_id": nid, "reason": why, "phases": by_id[nid]["phases"], "purpose": by_id[nid]["purpose"], "start": by_id[nid]["start"],
               "results_first_posted": by_id[nid]["results_first_posted"]} for nid, why in sorted(chosen.items())]
    manifest = {"version": "corpus-v2", "created": date.today().isoformat(), "target": a.target, "seed": a.seed,
                "scope": QUERY, "filter": FILTER, "evidence_rule": f"started before {CUTOFF}; overall status COMPLETED; never an evaluated or hold-out trial",
                "counts": {"in_scope": len(studies), "holdout_started_2023_or_later": len(holdout), "undated_excluded": len(undated),
                           "pool_before_2023": len(pool), "selected": len(trials),
                           "by_reason": dict(Counter(t["reason"] for t in trials)),
                           "by_purpose": dict(Counter(t["purpose"] for t in trials)),
                           "by_phase": dict(Counter("+".join(sorted(t["phases"])) for t in trials))},
                "trials": trials}
    Path("data/manifest/corpus_v2_5000.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=1))


if __name__ == "__main__":
    main()
