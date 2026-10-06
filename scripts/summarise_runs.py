"""One table over every audited protocol run: completeness, screening, accrual headline and primary endpoint by arm.
usage: python scripts/summarise_runs.py [VERSION=4.0.0]  ->  data/trial/runs/SUMMARY_v<VERSION>.md"""

import json
import sys
from pathlib import Path

RUNS = Path("data/trial/runs")
LOCK = Path("data/locked")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main(version: str = "4.0.0") -> Path:
    rows = ["| Protocol | Audit | Eligible share | Patients to screen | Accrual/year (historical p10 / p50 / p90) | Primary endpoint by arm |",
            "| --- | --- | ---: | ---: | --- | --- |"]
    for audit in sorted(RUNS.glob(f"*/v{version}/audit/completeness.json")):
        study = audit.parts[-4]
        a = _load(audit)["summary"]
        el = _load(LOCK / study / f"eligibility_v{version}" / "eligibility_summary.json")
        pl = _load(LOCK / study / f"planning_v{version}" / "planning_report.json")
        ep = _load(LOCK / study / f"endpoints_v{version}" / "endpoint_results.json")
        share = f"{el['summary']['eligible_share']:.0%}" if el and el["summary"].get("eligible_share") is not None else "-"
        screen = ((pl or {}).get("population_feasibility", {}).get("patients_to_screen") or {}).get("value") or "-"
        py = (((pl or {}).get("accrual") or {}).get("historical_model") or {}).get("patients_per_year") or {}
        pc = py.get("percentiles") or {}
        acc = f"{pc['p10']:.1f} / {pc['p50']:.1f} / {pc['p90']:.1f}" if pc else "-"
        primary = "-"
        if ep:
            e = next((x for x in ep["endpoints"] if x["role"] == "primary"), None)
            if e and e["status"] == "SIMULATED" and e["class"] == "continuous":
                a = e["at_design_effect"]
                primary = (f"{(e['endpoint'] or '')[:40]}: P(success) {a['p_success']:.2f} at the design effect {e['design']['effect']:g}; "
                           f"observed difference p50 {a['observed_mean_difference']['p50']:.1f}")
            elif e and e["status"] == "SIMULATED":
                parts = []
                for arm, v in e["by_arm"].items():
                    if e["class"] == "proportion":
                        parts.append(f"{arm} {v['rate']:.0%}")
                    elif e["class"] == "time_to_event":
                        land = (v.get("survival_percent") or {}).get("24m")
                        med = f"{v['km_median_months']} mo" if v["km_median_months"] is not None else "not reached"
                        parts.append(f"{arm} median {med}" + (f", 2-year {land}%" if land is not None else ""))
                    else:
                        parts.append(f"{arm} SAE {v['any_serious_ae']}/{v['patients']}")
                primary = f"{(e['endpoint'] or '')[:40]}: " + "; ".join(parts)
            elif e:
                primary = f"{(e['endpoint'] or '')[:40]}: {e['status']} ({e.get('kind')})"
        state = "COMPLETE" if a["complete"] else f"INCOMPLETE ({a['problems']})"
        rows.append(f"| {study} | {state} | {share} | {screen} | {acc} | {primary} |")
    out = RUNS / f"SUMMARY_v{version}.md"
    out.write_text(f"# Pipeline v4 runs (version {version})\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(main(*(sys.argv[1:2] or [])).read_text(encoding="utf-8"))
