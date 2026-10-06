"""Top up evidence corpus v2 to its target: every trial the build excluded (no neoplasm concept in its conditions) is
replaced by an unused eligible trial of the same stratum (purpose x phase x disease family; else purpose x phase; else
purpose; else any), drawn with a seed. The manifest drops the excluded trials and records each replacement.

Eligible: in scope, COMPLETED, started before 2023, not an evaluated or hold-out trial, never selected before.

Usage: .venv/Scripts/python.exe scripts/topup_corpus_v2.py [--seed 20261007]   then rerun scripts/run_corpus_v2_build.py
"""

import argparse
import json
import random
from datetime import date
from pathlib import Path

MANIFEST = Path("data/manifest/corpus_v2_5000.json")
PROGRESS = Path("data/corpus_v2/build/progress.jsonl")


def main() -> None:
    from clinical_asset.cutoff import evaluated_trials

    import importlib.util
    spec = importlib.util.spec_from_file_location("cv2", "scripts/build_corpus_v2_manifest.py")
    cv2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cv2)

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261007)
    a = ap.parse_args()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    progress = [json.loads(line) for line in open(PROGRESS, encoding="utf-8")]
    excluded = {r["nct_id"]: r.get("excluded") for r in progress if r.get("status") == "excluded"}
    history = m.setdefault("topups", [])
    ever = {t["nct_id"] for t in m["trials"]} | {x["excluded"] for h in history for x in h["replacements"]}
    to_replace = [t for t in m["trials"] if t["nct_id"] in excluded]
    if not to_replace:
        print("nothing to replace")
        return
    studies = json.loads(Path("data/raw/corpus_v2_candidates.json").read_text(encoding="utf-8"))["studies"]
    evaluated = set(evaluated_trials())
    pool = [s for s in studies if cv2.started_before(s["start"]) is True and s.get("status") == "COMPLETED"
            and s["nct_id"] not in evaluated and s["nct_id"] not in ever]
    fam_cache: dict = {}

    def fam(s):
        k = tuple(s["mesh"][:6])
        if k not in fam_cache:
            fam_cache[k] = cv2.family(s["mesh"])
        return fam_cache[k]

    by_id = {s["nct_id"]: s for s in studies}
    rng = random.Random(a.seed)
    used, replacements = set(), []
    for t in to_replace:
        src = by_id.get(t["nct_id"]) or {"purpose": t["purpose"], "phases": t["phases"], "mesh": []}
        ph = "+".join(sorted(src["phases"]))
        levels = [lambda s: s["purpose"] == src["purpose"] and "+".join(sorted(s["phases"])) == ph and fam(s) == fam(src),
                  lambda s: s["purpose"] == src["purpose"] and "+".join(sorted(s["phases"])) == ph,
                  lambda s: s["purpose"] == src["purpose"],
                  lambda s: True]
        pick, level = None, None
        for i, cond in enumerate(levels):
            cands = sorted(s["nct_id"] for s in pool if s["nct_id"] not in used and cond(s))
            if cands:
                pick, level = rng.choice(cands), ["same purpose, phase and family", "same purpose and phase", "same purpose", "any"][i]
                break
        if pick is None:
            continue
        used.add(pick)
        s = by_id[pick]
        replacements.append({"excluded": t["nct_id"], "reason": excluded[t["nct_id"]], "replacement": pick, "match": level})
        m["trials"].append({"nct_id": pick, "reason": f"top-up for {t['nct_id']} ({level})", "phases": s["phases"], "purpose": s["purpose"],
                            "start": s["start"], "results_first_posted": s["results_first_posted"]})
    m["trials"] = sorted((x for x in m["trials"] if x["nct_id"] not in excluded), key=lambda x: x["nct_id"])
    history.append({"date": date.today().isoformat(), "seed": a.seed, "replacements": replacements})
    m["counts"]["selected"] = len(m["trials"])
    m["counts"]["topped_up"] = sum(len(h["replacements"]) for h in history)
    MANIFEST.write_text(json.dumps(m, indent=1), encoding="utf-8")
    from collections import Counter
    print(json.dumps({"replaced": len(replacements), "selected": len(m["trials"]), "match": dict(Counter(r["match"] for r in replacements))}, indent=1))


if __name__ == "__main__":
    main()
