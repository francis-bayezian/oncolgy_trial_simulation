"""Compare the same protocols run on two asset profiles (e.g. v1 assets at version 4.0.0 vs v2 assets at 5.0.0).

Per protocol: audit completeness; the evidence rung every endpoint input came from (strong: protocol-cited, same
regimen, overlapping drug classes / subgroup; weak: disease-family mixture, all oncology, design hypothesis,
assumption); headline numbers (eligible share, historical accrual p10/p50/p90, ORR, PFS and OS medians, any serious
AE share); and the width of the endpoint predictive intervals (p10-p90).

Usage: .venv/Scripts/python.exe scripts/compare_profiles.py OLD_VERSION NEW_VERSION  -> data/trial/runs/COMPARE_<old>_vs_<new>.md
"""

import json
import sys
from collections import Counter
from pathlib import Path

LOCK = Path("data/locked")
WEAK = ("disease family mixture", "all oncology", "design hypothesis", "assumption", "no source", "simulated")


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def strength(level: str | None) -> str:
    lv = (level or "").casefold()
    return "weak" if any(w in lv for w in WEAK) else "strong" if lv else "none"


def summary(nct: str, v: str) -> dict | None:
    L = LOCK / nct
    if not (L / f"studyspec_v{v}").exists():
        return None
    audit = _load(Path(f"data/trial/runs/{nct}/v{v}/audit/completeness.json"))
    ep = _load(L / f"endpoints_v{v}" / "endpoint_results.json") or {}
    pl = _load(L / f"planning_v{v}" / "planning_report.json") or {}
    an = _load(L / f"analysis_v{v}" / "analysis_results.json") or {}
    el = _load(L / f"eligibility_v{v}" / "eligibility_summary.json") or {}
    levels, widths = Counter(), []
    for e in ep.get("endpoints") or []:
        for arm in (e.get("by_arm") or {}).values():
            levels[strength((arm.get("input") or {}).get("level"))] += 1
            pr = arm.get("predictive_rate") or arm.get("predictive_median_months") or {}
            if pr.get("p10") is not None and pr.get("p90") is not None:
                widths.append(pr["p90"] - pr["p10"])
    py = (((pl.get("accrual") or {}).get("historical_model") or {}).get("patients_per_year") or {}).get("percentiles") or {}
    eff = an.get("efficacy") or {}
    arms = {} if eff.get("status") else eff
    sae = []
    for t in (an.get("safety_tables") or []):
        pass
    t6 = Path(f"data/trial/runs/{nct}/v{v}/analysis/tables/table_6.csv")
    if t6.exists():
        import csv
        rows = list(csv.reader(open(t6, encoding="utf-8")))
        sae = next((r[1:-1] for r in rows if r and r[0] == "SAE"), [])
    sg = _load(Path(f"data/trial/runs/{nct}/v{v}/analysis/subgroups/subgroups.json")) or {}
    ev = _load(L / f"population_v{v}" / "subgroup_evidence.json") or {}
    return {"subgroups": sg, "subgroup_evidence": ev,
            "complete": (audit or {}).get("summary", {}).get("complete"),
            "inputs": dict(levels), "median_interval_width": round(sorted(widths)[len(widths) // 2], 3) if widths else None,
            "eligible_share": (el.get("summary") or {}).get("eligible_share"),
            "accrual_per_year": [round(py[k], 1) for k in ("p10", "p50", "p90")] if py else None,
            "orr": {a: (x.get("objective_response") or {}).get("rate") for a, x in arms.items()},
            "pfs_median": {a: (x.get("PFS") or {}).get("median_months") for a, x in arms.items()},
            "os_median": {a: (x.get("OS") or {}).get("median_months") for a, x in arms.items()},
            "sae": sae}


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def baseline(nct: str, old: str, new: str) -> str | None:
    """The old-profile run: OLD itself, else the latest locked studyspec version below NEW (a protocol added after OLD)."""
    if (LOCK / nct / f"studyspec_v{old}").exists():
        return old
    vs = [p.name.split("_v", 1)[1] for p in (LOCK / nct).glob("studyspec_v*")]
    vs = [v for v in vs if _vkey(v) < _vkey(new)]
    return max(vs, key=_vkey) if vs else None


def _rate(r):
    return "-" if not r or r.get("rate") is None else f"{100 * r['rate']:.0f}%"


def subgroup_section(a: dict | None, b: dict | None, va: str, vb: str) -> list[str]:
    """Per subgroup factor: where its prevalence and effect come from, then ORR and PFS median by level and arm, old
    next to new (efficacy-evaluable n in brackets)."""
    if not ((a or {}).get("subgroups") or (b or {}).get("subgroups")):
        return []
    L = [f"Subgroups (v{va} | v{vb}):", ""]

    def evidence(s):
        return {f["key"]: f for f in ((s or {}).get("subgroup_evidence") or {}).get("factors") or []}

    ea, eb = evidence(a), evidence(b)
    L += ["| Factor | Driver v" + va + " | Driver v" + vb + " | Prevalence v" + vb + " |", "| --- | --- | --- | --- |"]
    fa = {f["factor"]: f for f in ((a or {}).get("subgroups") or {}).get("factors") or []}
    fb = {f["factor"]: f for f in ((b or {}).get("subgroups") or {}).get("factors") or []}
    for name in dict.fromkeys(list(fa) + list(fb)):
        x, y = fa.get(name) or {}, fb.get(name) or {}
        prev = ((eb.get(y.get("variable")) or {}).get("prevalence") or {}).get("source") or "-"
        drv = lambda f: ("not reported" if not f.get("levels") else (f.get("outcome_driver") or "-").split(":")[0])  # noqa: E731
        L.append(f"| {name[:50]} | {drv(x) if x else 'absent'} | {drv(y) if y else 'absent'} | {prev[:90]} |")
    L += ["", "| Factor | Level | Arm | ORR v" + va + " | ORR v" + vb + " | PFS median v" + va + " | PFS median v" + vb + " |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    ra = {(r["factor"], r["level"], r["arm"]): r for r in ((a or {}).get("subgroups") or {}).get("rows") or []}
    rb = {(r["factor"], r["level"], r["arm"]): r for r in ((b or {}).get("subgroups") or {}).get("rows") or []}
    for k in dict.fromkeys(list(ra) + list(rb)):
        x, y = ra.get(k) or {}, rb.get(k) or {}
        med = lambda r: (f"{(r.get('PFS') or {}).get('median_months') or 'NR'}" if r.get("PFS") else "-")  # noqa: E731
        ev = lambda r: f" ({r.get('efficacy_evaluable', 0)})" if r else ""  # noqa: E731
        L.append(f"| {k[0][:40]} | {k[1]} | {k[2]} | {_rate(x.get('objective_response'))}{ev(x)} | {_rate(y.get('objective_response'))}{ev(y)} | "
                 f"{med(x)} | {med(y)} |")
    return L + [""]


def fmt(x):
    if isinstance(x, dict):
        return "; ".join(f"{k}: {('%.0f%%' % (100 * v)) if isinstance(v, float) and v <= 1 else v}" for k, v in x.items()) or "-"
    if isinstance(x, list):
        return " / ".join(str(i) for i in x) or "-"
    if isinstance(x, float):
        return f"{x:.0%}" if x <= 1 else f"{x:g}"
    return "-" if x is None else str(x)


def main(old: str, new: str) -> Path:
    protocols = json.loads(Path("data/manifest/protocols.json").read_text(encoding="utf-8"))["protocols"]
    L = [f"# Same protocols, two asset profiles: v{old} (old) vs v{new} (new)", "",
         "Evidence inputs: strong = protocol-cited, same regimen, overlapping drug classes or a matched subgroup; weak = "
         "disease-family mixture, all oncology, design hypothesis or assumption. Interval width = median p10-p90 width of "
         "the endpoint predictive intervals (smaller is more precise).", ""]
    rows = [("Audit complete", "complete"), ("Endpoint inputs (strong / weak)", "inputs"), ("Median interval width", "median_interval_width"),
            ("Eligible share", "eligible_share"), ("Accrual/year p10 / p50 / p90", "accrual_per_year"), ("ORR (derived)", "orr"),
            ("PFS median, months", "pfs_median"), ("OS median, months", "os_median"), ("Any SAE, n (%) by arm", "sae")]
    totals = {old: Counter(), new: Counter()}
    for p in protocols:
        base = baseline(p["nct_id"], old, new)
        a, b = (summary(p["nct_id"], base) if base else None), summary(p["nct_id"], new)
        L += [f"## {p['nct_id']}", "", f"| | v{base or old} (v1 assets) | v{new} (v2 assets) |", "| --- | --- | --- |"]
        for label, key in rows:
            L.append(f"| {label} | {fmt((a or {}).get(key)) if a else 'not run'} | {fmt((b or {}).get(key)) if b else 'not run'} |")
        L.append("")
        L += subgroup_section(a, b, base or old, new)
        for v, s in ((old, a), (new, b)):
            if s:
                totals[v].update(s["inputs"])
    L += ["## All protocols: where the endpoint inputs came from", "", f"| | v{old} | v{new} |", "| --- | --- | --- |"]
    for k in ("strong", "weak", "none"):
        L.append(f"| {k} | {totals[old][k]} | {totals[new][k]} |")
    out = Path(f"data/trial/runs/COMPARE_v{old}_vs_v{new}.md")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2]).read_text(encoding="utf-8")[-1500:])
