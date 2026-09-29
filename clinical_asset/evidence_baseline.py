"""Baseline-measure evidence from registry results: the distributions of patient characteristics at study entry.

Each registry baseline measure of each reporting group becomes one row with its statistical meaning intact:
the canonical variable it measures (by title and unit), the statistic (mean, median, count), its dispersion (SD,
IQR, range), the number of participants it describes, the unit as reported, and, for categorical measures, the
category label and count. Trial context is kept on every row (conditions, phase, interventions, dates, including the
results-first-posted date used for a temporal cut-off).

Canonical variables are recognised by general clinical vocabulary, never by trial. A measure whose title matches no
canonical variable keeps variable = None and stays in the table for audit.

Values describe ENROLLED participants: they are distributions after eligibility screening, not of the screened
population. Consumers must treat them as truncated by the enrolling trial's own criteria.
"""

import gzip
import json
import re
from pathlib import Path

from .reference import vocabulary

# canonical variable -> (title pattern, allowed unit pattern or None, kind): reference data, not code
CANONICAL = [tuple(x) for x in vocabulary()["baseline_measures"]]
PATTERNS = [(v, re.compile(t, re.IGNORECASE), re.compile(u, re.IGNORECASE) if u else None, k) for v, t, u, k in CANONICAL]


def canonical(title: str, unit: str | None) -> str | None:
    t = (title or "").strip()
    for var, tp, up, _ in PATTERNS:
        if tp.search(t):
            if up is None or not unit or up.search(unit):
                return var
    return None


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def trial_context(study: dict) -> dict:
    p = study["protocolSection"]
    s, d = p.get("statusModule", {}), p.get("designModule", {})
    arms = p.get("armsInterventionsModule", {})
    cond = study.get("derivedSection", {}).get("conditionBrowseModule", {})
    return {
        "nct_id": p["identificationModule"]["nctId"],
        "phase": "+".join(d.get("phases") or []) or None,
        "conditions": "; ".join(p.get("conditionsModule", {}).get("conditions") or []),
        "condition_mesh": "; ".join(m.get("term", "") for m in cond.get("meshes") or []),
        "interventions": "; ".join(i.get("name", "") for i in arms.get("interventions") or []),
        "start_date": (s.get("startDateStruct") or {}).get("date"),
        "primary_completion_date": (s.get("primaryCompletionDateStruct") or {}).get("date"),
        "results_first_posted": (s.get("resultsFirstPostDateStruct") or {}).get("date"),
        "minimum_age": p.get("eligibilityModule", {}).get("minimumAge"),
        "maximum_age": p.get("eligibilityModule", {}).get("maximumAge"),
    }


def measure_rows(study: dict) -> list[dict]:
    base = (study.get("resultsSection") or {}).get("baselineCharacteristicsModule") or {}
    if not base:
        return []
    ctx = trial_context(study)
    groups = {g["id"]: g.get("title", "") for g in base.get("groups", [])}
    total_ids = {gid for gid, t in groups.items() if re.fullmatch(r"\s*total\s*", t or "", re.IGNORECASE)}
    rows = []
    for m in base.get("measures", []):
        unit = m.get("unitOfMeasure")
        var = canonical(m.get("title", ""), unit)
        denom = {}
        for dn in m.get("denoms") or base.get("denoms") or []:
            if (dn.get("units") or "").lower().startswith("participant"):
                denom = {c["groupId"]: _num(c.get("value")) for c in dn.get("counts", [])}
        for cls in m.get("classes", []):
            cls_title = cls.get("title")
            cls_denom = {}
            for dn in cls.get("denoms") or []:
                if (dn.get("units") or "").lower().startswith("participant"):
                    cls_denom = {c["groupId"]: _num(c.get("value")) for c in dn.get("counts", [])}
            for cat in cls.get("categories", []):
                for x in cat.get("measurements", []):
                    gid = x.get("groupId")
                    rows.append({**ctx, "variable": var, "measure_title": m.get("title"), "param_type": m.get("paramType"),
                                 "dispersion_type": m.get("dispersionType"), "unit": unit,
                                 "class_title": cls_title, "category": cat.get("title"),
                                 "group_id": gid, "group_title": groups.get(gid), "is_total_group": gid in total_ids,
                                 "n": cls_denom.get(gid, denom.get(gid)), "value": _num(x.get("value")), "spread": _num(x.get("spread")),
                                 "lower": _num(x.get("lowerLimit")), "upper": _num(x.get("upperLimit")),
                                 "value_text": x.get("value")})
    return rows


def build(corpus: Path, out_dir: Path) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, trials = [], 0
    opener = gzip.open if str(corpus).endswith(".gz") else open
    with opener(corpus, "rt", encoding="utf-8") as fh:
        for line in fh:
            study = json.loads(line)
            r = measure_rows(study)
            trials += bool(r)
            rows.extend(r)
    pq.write_table(pa.Table.from_pylist(rows), out_dir / "baseline_measures.parquet")
    by_var: dict = {}
    for r in rows:
        if r["variable"]:
            by_var.setdefault(r["variable"], set()).add(r["nct_id"])
    summary = {"corpus": str(corpus), "trials_with_baseline": trials, "rows": len(rows),
               "rows_with_canonical_variable": sum(1 for r in rows if r["variable"]),
               "trials_per_variable": {k: len(v) for k, v in sorted(by_var.items(), key=lambda kv: -len(kv[1]))},
               "caveat": "baseline of ENROLLED participants (after eligibility), not of the screened population"}
    (out_dir / "manifest.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
