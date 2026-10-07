"""Freeze record of a replicate experiment (paper step 1 / step 6): checksums of everything the simulations rest on,
written before any observed result of the trial is used as a computational input (observed values may have been seen; see disclosures).

Records: the protocol PDF; the locked StudySpec, protocol facts, outcome model, engine results and planning of the base
run; the evidence assets of the profile (manifests / locks); the code (git commit, whether the tree differs from it,
and a checksum of every pipeline source file); the evidence cut-off (the trials excluded from evidence, and whether
the protocol itself is among them); the seed scheme; and every replicate's locked analysis.

Usage: .venv/Scripts/python.exe scripts/freeze_manifest.py ID BASE_VERSION OUT_DIR
"""

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")


def sha(p: Path) -> str | None:
    if not p.exists() or p.is_dir():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def main(study: str, version: str, out: Path) -> Path:
    from clinical_asset import assets, cutoff

    L = Path("data/locked") / study
    proto = next(p for p in json.loads(Path("data/manifest/protocols.json").read_text(encoding="utf-8"))["protocols"] if p["nct_id"] == study)
    facts = sorted(L.glob("protocol_facts_v*"))[-1]
    base = {s: sha(L / f"{s}_v{version}" / "lock.json") for s in ("studyspec", "outcomes", "results", "planning", "population",
                                                                   "eligibility", "cohorts", "safety", "outputs", "journey",
                                                                   "endpoints", "analysis")}
    base[facts.name] = sha(facts / "lock.json")
    asset_files = {"asset": assets.path("asset") / "manifest.json", "params_v1": assets.path("params_v1") / "manifest.json",
                   "params_v2": assets.path("params_v2") / "manifest.json", "params_v3": assets.path("params_v3") / "manifest.json",
                   "safety": assets.path("safety") / "lock.json", "operational": assets.path("operational") / "manifest.json"}
    excluded = cutoff.excluded()
    reps = Path(f"data/trial/runs/{study}/v{version}/replicates/locked")
    replicate_locks = {d.name: sha(d / "lock.json") for d in sorted(reps.glob("analysis_v*"))}
    code = {str(p).replace("\\", "/"): sha(p) for p in sorted(Path("clinical_asset").rglob("*.py"))}
    code.update({str(p).replace("\\", "/"): sha(p) for p in sorted(Path("scripts").glob("*")) if p.is_file()})
    doc = {"study": study, "base_version": version, "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "purpose": "computational inputs and simulation outputs fixed before any observed result of the trial is used as an input (retrospective held-out comparison)",
           "protocol": {"pdf": proto["pdf"], "sha256": sha(Path(proto["pdf"])), "protocols_manifest_sha256": proto.get("pdf_sha256")},
           "base_run_locks": base,
           "evidence_profile": assets.profile() if hasattr(assets, "profile") else "v1 (default)",
           "evidence_assets": {k: {"path": str(p).replace("\\", "/"), "sha256": sha(p)} for k, p in asset_files.items()},
           "evidence_cutoff": {"trials_excluded_from_evidence": len(excluded), "protocol_itself_excluded": study in excluded,
                               "env_cutoff_manifest": cutoff.manifest() is not None},
           "code": {"git_commit": git("rev-parse", "HEAD"), "git_branch": git("branch", "--show-current"),
                    "uncommitted_changes": [x for x in git("status", "--porcelain").splitlines() if x],
                    "files": code},
           "seed_scheme": {"replicate r base seed": "20270000 + 97 * r", "population": "+0", "cohorts": "+1", "safety": "+2",
                           "outputs": "+3", "journey": "+4", "endpoints": "+5", "analysis": "+6",
                           "eligibility": "+7 (build-eligibility --seed)", "screening order": "+11", "paired measurements": "+13"},
           "replicates": {"n": len(replicate_locks), "analysis_locks": replicate_locks},
           "observed_results_used": False}
    out.mkdir(parents=True, exist_ok=True)
    (out / "freeze_manifest.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return out / "freeze_manifest.json"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3])))
