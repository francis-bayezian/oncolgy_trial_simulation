"""Select the paper's showcase trial for a TEMPORAL evaluation, from protocol-level information only.

Cut-off T0: the evidence will be rebuilt from information available before T0, and the showcase trial must have been
planned (first posted) before T0 with results first posted after T0.

Eligible candidates (oncology treatment trials in data/raw/ctgov_oncology_results):
  * first posted before T0, results first posted after T0; overall status COMPLETED; phase 2 or 3;
  * a protocol document hosted by ClinicalTrials.gov;
  * a dated recruitment description exists (only its presence is checked, not its content: it makes accrual scorable);
  * not a development protocol;
  * (v2, added 2026-09-29 before any result was read) no linked publication of the trial (registry references of type
    RESULT or DERIVED) dated before T0: a trial whose results were published before T0 was knowable at T0. The v1
    selection (data/manifest/temporal_showcase.json) chose NCT03924986, whose primary results were published in 2022;
    it is superseded for that reason only.
No results value (enrolment achieved, outcomes, adverse events, participant flow counts) is read.

Ranking (declared before running; higher is better), from protocolSection only:
  1. randomized with a comparator arm (ACTIVE_COMPARATOR / PLACEBO_COMPARATOR / NO_INTERVENTION): the control-arm case;
  2. every drug intervention covered by the safety asset's drug-class map;
  3. disease family mapped to one specific family;
  4. the share of eligibility criteria that the pipeline can decide with generated variables (age, sex, ECOG /
     performance status, histology, stage, prior therapy, measurable disease) rather than laboratory values;
  5. ties: a seeded random order.
Output: data/manifest/temporal_showcase.json (T0, rules, the ranked candidates, the chosen trial).
"""

import argparse
import gzip
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECIDABLE = re.compile(r"\bage\b|years? (old|of age)|\bsex\b|gender|ecog|performance status|karnofsky|histolog|cytolog|stage\b|"
                       r"metasta|prior (therapy|treatment|chemo|systemic|line)|previously (treated|untreated)|lines? of|"
                       r"measurable disease|recist", re.I)
LAB = re.compile(r"hemoglobin|haemoglobin|neutrophil|\banc\b|platelet|creatinine|bilirubin|\bast\b|\balt\b|aminotransferase|"
                 r"clearance|albumin|inr\b|\bptt?\b|potassium|magnesium|calcium|lvef|ejection fraction|qtc", re.I)
COMPARATOR = {"ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "NO_INTERVENTION", "SHAM_COMPARATOR"}


def criteria_lines(text: str) -> list[str]:
    return [x.strip(" -*•\t") for x in re.split(r"\n+", text or "") if len(x.strip()) > 8 and not re.match(r"^\s*(in|ex)clusion criteria", x, re.I)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--t0", default="2024-01-01")
    ap.add_argument("--seed", type=int, default=20260929)
    ap.add_argument("--out", default="data/manifest/temporal_showcase.json")
    a = ap.parse_args()
    out = ROOT / a.out
    if out.exists():
        print(f"{out} exists: the selection is made once and never redone")
        return
    from clinical_asset.planning.operational import family_of_terms
    from clinical_asset.trial.journey_evidence import _mesh_map
    from clinical_asset.trial.safety import class_map

    cmap = {k.casefold(): v for k, v in class_map().items()}
    mesh = _mesh_map()
    dev = {p["nct_id"] for p in json.loads((ROOT / "data/manifest/development_protocols.json").read_text(encoding="utf-8"))["protocols"]}
    cands = []
    with gzip.open(ROOT / "data/raw/ctgov_oncology_results/corpus.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            p = s["protocolSection"]
            st = p["statusModule"]
            nct = p["identificationModule"]["nctId"]
            first = (st.get("studyFirstPostDateStruct") or {}).get("date", "")
            res = (st.get("resultsFirstPostDateStruct") or {}).get("date", "")
            docs = (s.get("documentSection") or {}).get("largeDocumentModule", {}).get("largeDocs", [])
            prot = [d for d in docs if d.get("hasProtocol")]
            phases = (p.get("designModule") or {}).get("phases") or []
            recruit = ((s.get("resultsSection") or {}).get("participantFlowModule") or {}).get("recruitmentDetails") or ""
            if not (first < a.t0 < res and st.get("overallStatus") == "COMPLETED" and prot and nct not in dev
                    and any(x in ("PHASE2", "PHASE3") for x in phases) and re.search(r"(19|20)\d\d", recruit)):
                continue
            pubs = [r for r in (p.get("referencesModule") or {}).get("references") or [] if r.get("type") in ("RESULT", "DERIVED")]
            years = [int(y) for r in pubs for y in re.findall(r"\b((?:19|20)\d\d)\b", r.get("citation", ""))]
            if any(y < int(a.t0[:4]) for y in years):
                continue                                        # published before T0: knowable at T0
            design = p.get("designModule") or {}
            arms = (p.get("armsInterventionsModule") or {}).get("armGroups") or []
            drugs = [i["name"] for i in (p.get("armsInterventionsModule") or {}).get("interventions") or [] if i.get("type") == "DRUG"]
            covered = [d for d in drugs if any(k in d.casefold() for k in cmap)]
            fam = family_of_terms([m["term"] for m in (s.get("derivedSection") or {}).get("conditionBrowseModule", {}).get("meshes", [])], mesh)[0]
            lines = criteria_lines((p.get("eligibilityModule") or {}).get("eligibilityCriteria"))
            dec = sum(bool(DECIDABLE.search(x)) and not LAB.search(x) for x in lines)
            randomized = (design.get("designInfo") or {}).get("allocation") == "RANDOMIZED" and any(g.get("type") in COMPARATOR for g in arms)
            cands.append({"nct_id": nct, "title": p["identificationModule"].get("briefTitle"), "phases": phases, "family": fam,
                          "first_posted": first, "results_first_posted": res, "randomized_with_comparator": randomized,
                          "drugs": drugs, "drugs_covered": len(covered), "all_drugs_covered": bool(drugs) and len(covered) == len(drugs),
                          "criteria": len(lines), "decidable_share": round(dec / len(lines), 3) if lines else 0.0,
                          "protocol_files": [d.get("filename") for d in prot]})
    rng = random.Random(a.seed)
    for c in cands:
        c["tiebreak"] = rng.random()
    cands.sort(key=lambda c: (c["randomized_with_comparator"], c["all_drugs_covered"], c["family"] not in ("other",) and not c["family"].startswith("mixed"),
                              c["decidable_share"], c["tiebreak"]), reverse=True)
    doc = {"created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "t0": a.t0, "seed": a.seed,
           "rules": __doc__, "candidates": len(cands), "chosen": cands[0] if cands else None, "ranked": cands[:25]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(cands)} candidates; chosen:", json.dumps(doc["chosen"], indent=1, ensure_ascii=False))
    for c in cands[1:6]:
        print("  next:", c["nct_id"], c["family"], c["randomized_with_comparator"], c["all_drugs_covered"], c["decidable_share"], c["title"][:80])


if __name__ == "__main__":
    main()
