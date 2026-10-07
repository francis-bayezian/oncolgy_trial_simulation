"""Stress tests of a replicate experiment (paper step 5): trial-design questions, not arbitrary scenarios.

(a) Eligibility (counterfactual feasibility, not a recommendation to drop a criterion): the three criteria excluding the
    most generated patients, removed one at a time; per replicate (first N_ELIG) the eligible share and the number
    screened to reach the evaluable target in the replicate's own screening order. Criteria generated patients cannot
    decide are resolved by the screen-pass calibration (A16): their exclusion rates are calibrated, not criterion
    evidence, and the report says so. The accrual model's rate does not depend on the eligible share, so enrolment
    time is unchanged by these scenarios (stated).
(b) Recruitment: slow / central / fast accrual = the historical accrual model's p10 / p50 / p90 patients per year for
    this protocol (planning report); per replicate, Poisson arrivals until the target is enrolled.
(c) Endpoint completeness: 0% / 10% / 20% loss of the paired primary endpoint (missing completely at random) on top of
    each replicate's usable pairs; the protocol's test on the remaining pairs, per endpoint source.
(d) Effect-size curve: the protocol's test at effects 0 to 15 (design SD), by simulation with Monte Carlo errors.

Usage: .venv/Scripts/python.exe scripts/stress_tests.py ID BASE_VERSION INPUTS_DIR MASTER_DIR OUT_DIR
"""

import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from clinical_asset.trial import paired_measure as pm  # noqa: E402

N_ELIG = 50
LOSSES = (0.0, 0.10, 0.20)
EFFECTS = (0, 2.5, 5, 7.5, 10, 12.5, 15)


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def q(v, ps=(10, 50, 90)):
    return [float(np.percentile(v, p)) for p in ps]


def main(study: str, version: str, inputs: Path, master: Path, out: Path) -> Path:
    spec = json.loads((Path("data/locked") / study / f"studyspec_v{version}" / "studyspec.json").read_text(encoding="utf-8"))
    target = int(next(x["value"] for x in spec["sample_size"] if x["quantity"] in ("evaluable_target", "target_accrual")))
    an = next(a for a in spec["analyses"] if a.get("primary"))
    alpha = float((an.get("alpha") or {}).get("value") or 0.05)
    root = Path(f"data/trial/runs/{study}/v{version}/replicates")
    reps = sorted(d for d in root.glob("r[0-9][0-9][0-9]") if (d / "eligibility" / "eligibility.jsonl").exists())
    crit_text = {c["criterion_id"]: " ".join(((c.get("label") or {}).get("text") or (c.get("evidence") or {}).get("text") or "")[:80].split())
                 for c in spec.get("eligibility") or []}
    L = [f"# Stress tests: {study} (base v{version})", ""]
    rows = []

    # (a) eligibility
    pressure = Counter()
    elig_cache = {}
    for rd in reps[:N_ELIG]:
        e = _jsonl(rd / "eligibility" / "eligibility.jsonl")
        elig_cache[rd.name] = e
        pressure.update(c for x in e for c in x.get("failed") or [])
    top = [c for c, _ in pressure.most_common(3)]
    L += ["## (a) Eligibility: one criterion removed at a time (counterfactual feasibility)", "",
          f"The three criteria excluding the most generated patients over {len(elig_cache)} replicates. Criteria the generated "
          "patients cannot decide are resolved by the screen-pass calibration (A16): their exclusion rates are calibrated, not "
          "evidence about that criterion. Enrolment time does not change in these scenarios (the accrual model's rate does not "
          "depend on the eligible share).", "",
          "| Scenario | Criterion text | Eligible % p10 / p50 / p90 | Screened to reach the target p10 / p50 / p90 |", "| --- | --- | --- | --- |"]
    for scen in [None, *top]:
        shares, nns = [], []
        for name, e in elig_cache.items():
            r = int(name[1:])
            ok = [x["status"] == "ELIGIBLE" or (scen is not None and x["status"] == "INELIGIBLE" and (x.get("failed") or []) == [scen])
                  for x in e]
            shares.append(100 * sum(ok) / len(ok))
            order = np.random.default_rng(20270000 + 97 * r + 11).permutation(len(ok))
            cum = np.cumsum([ok[i] for i in order])
            nns.append(int(np.searchsorted(cum, target) + 1))
        label = "baseline (all criteria)" if scen is None else f"without {scen}"
        L.append(f"| {label} | {crit_text.get(scen, '') if scen else ''} | " + " / ".join(f"{x:.1f}" for x in q(shares)) + " | "
                 + " / ".join(f"{x:.0f}" for x in q(nns)) + " |")
        rows.append(["eligibility", label, len(shares), *q(shares), *q(nns)])
    L.append("")

    # (b) recruitment
    plan = json.loads((Path("data/locked") / study / f"planning_v{version}" / "planning_report.json").read_text(encoding="utf-8"))
    pct = plan["accrual"]["historical_model"]["patients_per_year"]["percentiles"]
    stated = plan["accrual"].get("stated_accrual_durations_years") or []
    L += ["## (b) Recruitment: slow / central / fast accrual", "",
          f"Rates are the historical accrual model's p10 / p50 / p90 for this protocol ({pct['p10']:.1f} / {pct['p50']:.1f} / "
          f"{pct['p90']:.1f} patients per year). Time to enrol {target} participants, Poisson arrivals, {len(reps)} replicates."
          + (f" Stated accrual duration: {stated} years." if stated else ""), "",
          "| Scenario | Patients / year | Months to enrol the target p10 / p50 / p90 | Trials enrolled within 12 months |", "| --- | ---: | --- | ---: |"]
    for name, key in (("slow", "p10"), ("central", "p50"), ("fast", "p90")):
        rate = pct[key]
        months = []
        for rd in reps:
            rng = np.random.default_rng(20270000 + 97 * int(rd.name[1:]) + 21)
            months.append(float(np.sum(rng.exponential(365.25 / rate, target))) / 30.4375)
        within = sum(m <= 12 for m in months)
        L.append(f"| {name} | {rate:.1f} | " + " / ".join(f"{x:.1f}" for x in q(months)) + f" | {within}/{len(months)} |")
        rows.append(["recruitment", name, len(months), *q(months), within, rate, None])
    L.append("")

    # (c) endpoint completeness
    sources = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(inputs).glob("endpoint_source_*.json"))]
    mrows = {s["name"]: list(csv.DictReader(open(Path(master) / f"master_simulation_{s['name']}.csv", encoding="utf-8"))) for s in sources}
    L += ["## (c) Endpoint completeness: extra loss of the paired endpoint (missing completely at random)", "",
          "| Endpoint source | Extra loss | Usable pairs p10 / p50 / p90 | Trials reaching significance |", "| --- | ---: | --- | ---: |"]
    for s in sources:
        for loss in LOSSES:
            usable, ok = [], 0
            for row in mrows[s["name"]]:
                r = int(row["replicate"])
                pairs = list(csv.DictReader(open(root / f"r{r:03d}" / f"paired_measurements_{s['name']}.csv", encoding="utf-8")))
                d = np.array([float(x["difference"]) for x in pairs])
                rng = np.random.default_rng(20270000 + 97 * r + 31 + int(loss * 100))
                keep = rng.random(len(d)) >= loss
                usable.append(int(keep.sum()))
                ok += bool(pm.analyse(d[keep], alpha=alpha)["success"])
            n = len(usable)
            L.append(f"| {s['name']} | {100 * loss:.0f}% | " + " / ".join(f"{x:.0f}" for x in q(usable)) + f" | {ok}/{n} |")
            rows.append(["completeness", f"{s['name']} loss {loss:.0%}", n, *q(usable), ok, None, None])
    L.append("")

    # (d) effect-size curve
    design = next(s for s in sources if s["kind"] == "design")
    L += ["## (d) Effect-size curve (the protocol's test, design SD)", "",
          f"Paired Wilcoxon signed-rank, alpha {alpha:g}, SD of differences {design['sd_diff']:.2f}; 4,000 simulated trials per point.", "",
          f"| True effect | Power at n = {target} (MC SE) | Power at n = {target - 5} |", "| ---: | --- | --- |"]
    for k, eff in enumerate(EFFECTS):
        a = pm.simulated_power(eff, design["sd_diff"], target, 4000, 20261100 + k, alpha)
        b = pm.simulated_power(eff, design["sd_diff"], target - 5, 4000, 20261200 + k, alpha)
        L.append(f"| {eff:g} | {a['power']:.3f} ({a['mc_se']:.3f}) | {b['power']:.3f} |")
        rows.append(["effect_curve", f"effect {eff:g}", 4000, a["power"], a["mc_se"], b["power"], None, None, None])
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "stress_tests.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([["family", "scenario", "n", "v1", "v2", "v3", "v4", "v5", "v6"], *rows])
    (out / "stress_tests.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out / "stress_tests.md"


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])))
