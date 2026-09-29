"""Registry evidence for the patient journey: why participants leave a trial, how often adverse events reach grade 3
or higher, and how many screened patients enrol.

* Disposition (participant flow): per reporting group and period, participants started and completed and the count for
  each reason for not completing, mapped to a small set of general reason classes.
* Grade >= 3 adverse events (outcome measures whose title states grade 3 or higher, 3-4, 3-5, >= 3): the proportion of
  participants, overall or per event term when the measure lists terms as categories or classes.
* Screening: the recruitment-details text, and the numbers screened / screen failures / enrolled when the text states
  them in a recognisable form.

All rows keep the trial context (conditions, phase, interventions, dates) for subgrouping and for a temporal cut-off.
"""

import gzip
import json
import re
from pathlib import Path

from .evidence_baseline import _num, trial_context

REASONS = [
    ("progression", r"progress|lack of efficacy|relapse|disease recurrence"),
    ("adverse_event", r"adverse|toxicit|side effect"),
    ("death", r"death|died|deceased"),
    ("withdrawal_by_subject", r"withdr[ae]w|withdrawal|consent|patient (decision|choice|request)|subject (decision|choice)|refus"),
    ("lost_to_follow_up", r"lost to follow"),
    ("physician_decision", r"physician|investigator"),
    ("protocol_violation", r"protocol (violation|deviation)|non-?complian|ineligib|eligibility"),
    ("sponsor_or_study_termination", r"sponsor|terminat|study (closed|closure|stopped)|administrative"),
]
REASON_RE = [(k, re.compile(p, re.IGNORECASE)) for k, p in REASONS]
GRADE3 = re.compile(r"grade\s*(3|iii)\s*(or|and|-|–|to|/)?\s*(higher|greater|above|more|4|iv|5)|grade\s*[≥>]\s*=?\s*(3|iii)|grade\s*3\s*\+", re.IGNORECASE)
SCREENED = re.compile(r"(\d[\d,]*)\s+(?:patients|participants|subjects|individuals|people)?\s*(?:were\s+|was\s+)?screened", re.IGNORECASE)
SCREEN_FAIL = re.compile(r"(\d[\d,]*)\s+(?:patients|participants|subjects)?\s*(?:were\s+)?screen(?:ing)?[\s-]*fail|screen(?:ing)?[\s-]*fail\w*\s*(?:\(|:|=|was|were)?\s*(?:n\s*=\s*)?(\d[\d,]*)", re.IGNORECASE)


def reason_class(text: str) -> str:
    for k, r in REASON_RE:
        if r.search(text or ""):
            return k
    return "other"


def disposition_rows(study: dict) -> list[dict]:
    flow = (study.get("resultsSection") or {}).get("participantFlowModule") or {}
    if not flow:
        return []
    ctx = trial_context(study)
    groups = {g["id"]: g.get("title", "") for g in flow.get("groups", [])}
    rows = []
    for pi, p in enumerate(flow.get("periods", [])):
        started, completed = {}, {}
        for m in p.get("milestones", []):
            t = (m.get("type") or "").upper()
            for a in m.get("achievements", []):
                if t == "STARTED":
                    started[a["groupId"]] = _num(a.get("numSubjects"))
                elif t == "COMPLETED":
                    completed[a["groupId"]] = _num(a.get("numSubjects"))
        reasons: dict = {}
        for d in p.get("dropWithdraws", []):
            cls = reason_class(d.get("type", ""))
            for r in d.get("reasons", []):
                key = (r["groupId"], cls)
                reasons[key] = reasons.get(key, 0) + (_num(r.get("numSubjects")) or 0)
        for gid in groups:
            base = {**ctx, "period_index": pi, "period_title": p.get("title"), "group_id": gid, "group_title": groups[gid],
                    "started": started.get(gid), "completed": completed.get(gid)}
            gr = {c: v for (g, c), v in reasons.items() if g == gid}
            if not gr:
                rows.append({**base, "reason": None, "count": None})
            for c, v in gr.items():
                rows.append({**base, "reason": c, "count": v})
    return rows


def grade3_rows(study: dict) -> list[dict]:
    oms = (study.get("resultsSection") or {}).get("outcomeMeasuresModule") or {}
    ctx = trial_context(study)
    rows = []
    for m in oms.get("outcomeMeasures", []):
        if not GRADE3.search(m.get("title", "")):
            continue
        unit = (m.get("unitOfMeasure") or "").lower()
        ptype = m.get("paramType")
        is_pct = "percent" in unit or "%" in unit
        is_count = ptype == "COUNT_OF_PARTICIPANTS" or (ptype == "NUMBER" and "participant" in unit)
        if not (is_pct or is_count):
            continue                        # event counts and medians are not a proportion of participants
        groups = {g["id"]: g.get("title", "") for g in m.get("groups", [])}
        denom = {}
        for dn in m.get("denoms", []):
            if (dn.get("units") or "").lower().startswith("participant"):
                denom = {c["groupId"]: _num(c.get("value")) for c in dn.get("counts", [])}
        for cls in m.get("classes", []):
            for cat in cls.get("categories", []):
                term = cat.get("title") or cls.get("title")
                for x in cat.get("measurements", []):
                    gid, v, n = x.get("groupId"), _num(x.get("value")), denom.get(x.get("groupId"))
                    if v is None or not n:
                        continue
                    p = v / 100.0 if is_pct else v / n
                    if not 0 <= p <= 1:
                        continue
                    rows.append({**ctx, "measure_title": m.get("title"), "term": term, "aggregate": term is None,
                                 "group_id": gid, "group_title": groups.get(gid), "n": n, "proportion": p,
                                 "count": round(p * n) if is_pct else v, "time_frame": m.get("timeFrame")})
    return rows


def screening_row(study: dict) -> dict | None:
    flow = (study.get("resultsSection") or {}).get("participantFlowModule") or {}
    text = " ".join(filter(None, [flow.get("recruitmentDetails"), flow.get("preAssignmentDetails")]))
    if not text:
        return None
    enrolled = _num(study["protocolSection"].get("designModule", {}).get("enrollmentInfo", {}).get("count"))
    sc = SCREENED.search(text)
    sf = SCREEN_FAIL.search(text)
    n_sc = _num(sc.group(1)) if sc else None
    n_sf = _num((sf.group(1) or sf.group(2))) if sf else None
    return {**trial_context(study), "text": text[:2000], "screened": n_sc, "screen_failures": n_sf, "enrolled": enrolled}


def build(corpus: Path, out_dir: Path) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    disp, g3, scr = [], [], []
    opener = gzip.open if str(corpus).endswith(".gz") else open
    with opener(corpus, "rt", encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            disp.extend(disposition_rows(s))
            g3.extend(grade3_rows(s))
            r = screening_row(s)
            if r:
                scr.append(r)
    pq.write_table(pa.Table.from_pylist(disp), out_dir / "disposition.parquet")
    pq.write_table(pa.Table.from_pylist(g3), out_dir / "grade3_adverse_events.parquet")
    pq.write_table(pa.Table.from_pylist(scr), out_dir / "screening.parquet")
    summary = {"corpus": str(corpus),
               "disposition": {"rows": len(disp), "trials": len({r["nct_id"] for r in disp}),
                               "reasons": {k: sum(1 for r in disp if r["reason"] == k) for k, _ in REASONS + [("other", "")]}},
               "grade3": {"rows": len(g3), "trials": len({r["nct_id"] for r in g3}),
                          "aggregate_rows": sum(r["aggregate"] for r in g3), "term_rows": sum(not r["aggregate"] for r in g3)},
               "screening": {"trials_with_text": len(scr), "with_screened_count": sum(r["screened"] is not None for r in scr),
                             "with_screen_failures": sum(r["screen_failures"] is not None for r in scr)}}
    (out_dir / "manifest.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
