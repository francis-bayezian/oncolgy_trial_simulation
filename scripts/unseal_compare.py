"""HISTORICAL (the retired blind-test unsealing; outputs now live in data/trial/runs/<NCT>/history/blind).

Unseal one blind trial: fetch its registry record AFTER its predictions are locked, verify the sealed category
commitment, and score the locked predictions (nothing is re-run).

usage: python scripts/unseal_compare.py LABEL NCT ENGINE(tte|binary|escalation) VERSION

The locks under data/locked/LABEL/*_vVERSION must exist; every comparison records the lock time and the fetch time,
and the order (locked before fetched) is checked and reported.
"""

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from select_blind_holdouts import SAFETY  # the exact rule the sealing used

from clinical_asset.planning.operational import accrual_reason


def category(registry: dict) -> str | None:
    st = registry["protocolSection"]["statusModule"]
    status, why = st.get("overallStatus"), st.get("whyStopped") or ""
    if status == "COMPLETED":
        return "completed"
    if status == "TERMINATED":
        safety = bool(SAFETY.search(why))
        if accrual_reason(why) and not safety:
            return "terminated_accrual"
        if safety and not accrual_reason(why):
            return "terminated_safety"
    return None


def run(*args: str) -> None:
    subprocess.run([str(ROOT / ".venv/Scripts/python.exe"), "-m", "clinical_asset.cli", *args], check=True, cwd=ROOT,
                   env={**__import__("os").environ, "PYTHONPATH": ".", "PYTHONIOENCODING": "utf-8"}, stdout=subprocess.DEVNULL)


def main(label: str, nct: str, engine: str, version: str) -> None:
    L = ROOT / "data/locked" / label
    needed = ["studyspec", "cohorts", "outcomes", "results", "planning", "safety", "outputs"]
    missing = [s for s in needed if not (L / f"{s}_v{version}" / "lock.json").exists()]
    if missing:
        raise SystemExit(f"predictions are not locked yet ({missing}): nothing is fetched")
    locked_at = max(json.loads((L / f"{s}_v{version}" / "lock.json").read_text(encoding="utf-8"))["locked_at"] for s in needed)
    fetched_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    reg_file = ROOT / "data/holdout_comparison" / f"{nct}.json"
    record = requests.get(f"https://clinicaltrials.gov/api/v2/studies/{nct}", timeout=120).json()
    reg_file.write_text(json.dumps(record, indent=1), encoding="utf-8")
    manifest = json.loads((ROOT / "data/manifest/blind_holdout.json").read_text(encoding="utf-8"))
    entry = next((t for t in manifest["trials"] if t["nct_id"] == nct), None)
    cat = category(record)
    verified = bool(entry and cat and hashlib.sha256(f"{manifest['salt']}|{nct}|{cat}".encode()).hexdigest() == entry["category_commitment"])
    T = f"data/trial/blind/{label}/v{version}"
    reg = f"data/holdout_comparison/{nct}.json"
    cmp = {"tte": ["compare-registry", "--population", f"data/locked/{label}/population_v{version}", "--cohorts", f"data/locked/{label}/cohorts_v{version}",
                   "--outcomes", f"data/locked/{label}/outcomes_v{version}"],
           "binary": ["compare-registry-binary"], "escalation": ["compare-registry-escalation"]}[engine]
    run(*cmp[:1], "--results", f"data/locked/{label}/results_v{version}", *cmp[1:], "--registry", reg, "--fetched-at", fetched_at, "--out", f"{T}/comparison")
    run("compare-registry-planning", "--planning", f"data/locked/{label}/planning_v{version}", "--registry", reg, "--fetched-at", fetched_at,
        "--out", f"{T}/planning_comparison")
    run("compare-registry-safety", "--results", f"data/locked/{label}/safety_v{version}", "--registry", reg, "--fetched-at", fetched_at,
        "--out", f"{T}/safety_comparison")
    run("compare-registry-baseline", "--studyspec", f"data/locked/{label}/studyspec_v{version}", "--registry", reg, "--fetched-at", fetched_at,
        "--locked-at", locked_at, "--out", f"{T}/baseline_comparison")
    for stage, kind, inp in (("comparison", "registry_comparison", "results"), ("planning_comparison", "planning_comparison", "planning"),
                             ("safety_comparison", "safety_comparison", "safety"), ("baseline_comparison", "baseline_comparison", "studyspec")):
        run("lock-stage", "--stage", f"{T}/{stage}", "--out", f"data/locked/{label}/{kind}_v{version}", "--kind", kind, "--version", version,
            "--input", f"{inp}=data/locked/{label}/{inp}_v{version}/lock.json", "--input", f"registry_{nct}={reg}", "--code", "clinical_asset")
    doc = {"label": label, "nct_id": nct, "predictions_locked_at": locked_at, "registry_fetched_at": fetched_at,
           "order_verified": locked_at < fetched_at, "category": cat, "category_commitment_verified": verified}
    (ROOT / T / "unsealing.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
