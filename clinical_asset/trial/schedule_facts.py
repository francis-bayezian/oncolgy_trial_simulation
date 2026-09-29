"""Verified schedule facts read from the protocol text: when tumours are assessed, when laboratory tests are taken,
how long the screening window is, and how often patients are seen in follow-up.

The compiled StudySpec often misses these (assessment tables compile poorly). Here, candidate sentences are
pre-selected by a frequency pattern (every / q N weeks, cycles, months; day X of cycle Y); the model returns each
schedule element with a verbatim quote; a fact is kept only when its quote is in the protocol text, its numbers are
plausible for its kind, and a strict three-vote review judges it faithful (resolve or leave: an element that fails
stays unresolved).
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..protocol import schemas as psc
from ..protocol.compiler import _majority

VERSION = "schedule-facts-1.3.0"
TEXT = {"type": "string"}
NUM = {"type": ["number", "null"]}
KINDS = ("tumour_assessment", "laboratory_assessment", "screening_window", "follow_up_visit", "other")
SCHEMA = psc.obj({"facts": {"type": "array", "items": psc.obj({
    "kind": psc.enum(*KINDS), "recurring": {"type": "boolean"}, "first_day": NUM, "interval_days": NUM,
    "later_interval_days": NUM, "later_after_day": NUM, "window_days": NUM, "more_often_if_indicated": {"type": "boolean"},
    "approximate": {"type": "boolean"}, "applies_to_all_patients": {"type": "boolean"}, "assessment": TEXT,
    "time_origin": psc.enum("first_dose", "randomization", "enrollment", "end_of_treatment", "cycle_day", "unclear"),
    "quote": TEXT, "reason": TEXT})}})
INSTRUCTIONS = (
    "Each candidate is a sentence from a clinical trial protocol with its section. Return the schedule facts the "
    "protocol states for the study itself (not for other studies, not for drug dosing): "
    "tumour_assessment (imaging / disease or response evaluation during treatment): first_day and interval_days, and "
    "later_interval_days with later_after_day when the interval changes later; "
    "laboratory_assessment (blood tests during treatment): interval_days; screening_window: interval_days = the maximum "
    "number of days before treatment start within which screening must happen; follow_up_visit (after treatment ends): "
    "interval_days; recurring = false for a one-time visit or window (screening window, a single safety visit). "
    "window_days: the allowed +/- tolerance in days when stated; more_often_if_indicated: true when the protocol allows "
    "extra assessments when clinically indicated; approximate: true when the protocol says approximately / about; "
    "applies_to_all_patients: false when the schedule is for a subgroup only (a cohort, patients with a positive "
    "baseline scan); assessment: what is assessed, in a few words (e.g. 'CT/MRI restaging', 'screening laboratory tests'). "
    "screening_window is the window for the whole screening or for its laboratory tests or imaging (say which in "
    "assessment). Always give the numbers in days: weeks x7, months x30.4, cycles x the "
    "cycle length the sentence or the provided cycle_length_days gives (for 'every 3 cycles' with 28-day cycles, 84). quote: the shortest verbatim span that states the fact, copied "
    "exactly. Omit anything you are not sure about. reason: one short sentence.")
VERIFY_ADD = (" SPECIAL CASE, overriding the rule-faithfulness standard above: each item is a SCHEDULE fact (when an "
              "assessment is done), used to lay out simulated visits. Judge FAITHFUL when the evidence states this main "
              "schedule for the patients and assessment named: the same timing, interval and origin, where an interval "
              "the protocol calls approximate and rendered as approximate is faithful, and visit tolerance windows, extra "
              "assessments when clinically indicated or at progression, baseline and end-of-treatment visits are NOT "
              "required in the rendering (the simulation adds none of them). INCORRECT when the timing, interval, origin, "
              "assessment or the patients it applies to differ, or when it describes dosing or another study.")
FREQ = re.compile(r"(\bevery|\beach|\bq)\s*\d+\s*(-|to)?\s*\d*\s*(weeks?|wks?|w\b|cycles?|months?|days?)|day\s*\d+\s*of\s*(each\s*)?cycle|within\s*\d+\s*days", re.I)
CONTEXT = re.compile(r"ct\b|mri|scan|imag|tumou?r|recist|response|restag|disease (assessment|evaluation)|laborator|hematolog|haematolog|blood|chemistr|screen|baseline|follow", re.I)
PLAUSIBLE = {"tumour_assessment": (14, 185), "laboratory_assessment": (1, 92), "screening_window": (3, 60), "follow_up_visit": (14, 400)}


UNIT_DAYS = {"d": 1.0, "w": 7.0, "m": 30.4375}
QUOTE_INTERVAL = [
    re.compile(r"(?:every|each)\s*(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(days?|weeks?|wks?|months?|cycles?)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(day|week|wk|month|cycle)s?\s*intervals?", re.I),
    re.compile(r"\bq\s*(\d+)\s*(w|wk|weeks?|m|months?|d|days?)\b", re.I),
    re.compile(r"within\s*(\d+)\s*(days?|weeks?)", re.I),
]


def quote_interval(quote: str, cycle_days: float | None) -> float | None:
    """The interval a quote states, in days, parsed deterministically (the first pattern that matches)."""
    for rx in QUOTE_INTERVAL:
        m = rx.search(quote or "")
        if m:
            n, u = float(m.group(1)), m.group(2).lower()
            if u.startswith("c"):
                return n * cycle_days if cycle_days else None
            return n * UNIT_DAYS.get(u[0], 0) or None
    return None


def _norm(s: str) -> str:
    return " ".join((s or "").replace("±", "+/-").split()).casefold()


def candidates(pdf: Path, max_candidates: int = 80) -> list[dict]:
    from ..protocol.ingest import extract

    doc = extract(Path(pdf))
    out = []
    for s in doc.sections:
        text = " ".join(getattr(line, "text", str(line)) for line in s.lines)
        for m in FREQ.finditer(text):
            window = text[max(0, m.start() - 220): m.end() + 160]
            if CONTEXT.search(window) and not re.search(r"\bmg\b|mg/m|\bauc\b|infusion|orally|dose of", text[max(0, m.start() - 40): m.end() + 20], re.I):
                out.append({"section": f"{s.number} {s.title[:60]}", "text": " ".join(window.split())})
    seen, uniq = set(), []
    for c in out:
        k = c["text"][:120]
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq[:max_candidates]


def extract_facts(model: Any, pdf: Path, cycle_length_days: float | None, votes: int = 3, workers: int = 6) -> dict:
    cands = candidates(pdf)
    if not cands:
        return {"version": VERSION, "facts": [], "candidates": 0}
    payload = {"instructions": INSTRUCTIONS, "cycle_length_days": cycle_length_days, "candidates": cands}
    try:
        found = model.extract("protocol_schedule_facts", SCHEMA, payload).get("facts", [])
    except Exception as e:  # noqa: BLE001 - no facts: every element stays unresolved
        return {"version": VERSION, "facts": [], "candidates": len(cands), "error": str(e)}
    corpus = _norm(" ".join(c["text"] for c in cands))
    facts = []
    for i, f in enumerate(found):
        issues = []
        parsed = quote_interval(f.get("quote", ""), cycle_length_days)
        if f["kind"] != "other" and parsed is not None:
            if f.get("interval_days") is None:
                f["interval_days"], f["interval_source"] = parsed, "parsed from the quote"
            elif abs(f["interval_days"] - parsed) > 0.5 and f.get("later_interval_days") not in (parsed,):
                issues.append(f"model interval {f['interval_days']:g} differs from the quote's {parsed:g} days")
        if not f.get("quote") or _norm(f["quote"]) not in corpus:
            issues.append("quote not found verbatim in the protocol text")
        lo, hi = PLAUSIBLE.get(f["kind"], (0, 1e9))
        if f.get("interval_days") is not None and not lo <= f["interval_days"] <= hi:
            issues.append(f"interval {f['interval_days']} outside the plausible range {lo}-{hi} days for {f['kind']}")
        if f["kind"] != "other" and f.get("interval_days") is None and f.get("first_day") is None:
            issues.append("no number")
        evidence = next((c["text"] for c in cands if _norm(f.get("quote", "")) in _norm(c["text"])), "")
        facts.append({**f, "fact_id": f"SF{i + 1:02d}", "issues": issues, "evidence": evidence})
    keep = [f for f in facts if not f["issues"] and f["kind"] != "other"]
    _verify(model, keep, votes, workers)
    return {"version": VERSION, "candidates": len(cands), "facts": facts}


def _render(f: dict) -> str:
    k, iv, org = f["kind"], f.get("interval_days"), (f.get("time_origin") or "unclear").replace("_", " ")
    who = "all patients" if f.get("applies_to_all_patients", True) else "a subgroup of patients"
    what = f.get("assessment") or k.replace("_", " ")
    if k == "screening_window":
        return f"{what} must be done within {iv:g} days before {org} (a one-time window), for {who}"
    parts = [f"{what} for {who}"]
    if f.get("first_day") is not None:
        parts.append(f"first at day {f['first_day']:g} from {org}")
    if iv is not None:
        approx = "approximately " if f.get("approximate") else ""
        parts.append(f"{approx}every {iv:g} days" if f.get("recurring", True) else f"once, {approx}{iv:g} days after {org}")
    if f.get("later_interval_days") is not None:
        parts.append(f"every {f['later_interval_days']:g} days after day {f.get('later_after_day') or '?'}")
    if f.get("window_days"):
        parts.append(f"with a +/-{f['window_days']:g}-day window")
    if f.get("more_often_if_indicated"):
        parts.append("or more often when clinically indicated")
    return ", ".join(parts)


def _verify(model, facts: list[dict], votes: int, workers: int) -> None:
    jobs = list(range(votes))

    def run(vote):
        payload = {"instructions": psc.VERIFY_INSTRUCTIONS + VERIFY_ADD, "text": "(each item's evidence is its protocol sentence)",
                   "items": [{"item_id": f["fact_id"], "rendering": _render(f), "evidence": f["evidence"], "related": []} for f in facts]}
        if vote:
            payload["independent_review"] = f"review {vote + 1} of {votes}: judge from scratch"
        try:
            return model.extract("protocol_verify", psc.VERIFY, payload).get("verdicts", [])
        except Exception:  # noqa: BLE001 - a failed vote counts as no vote
            return []
    with ThreadPoolExecutor(workers) as pool:
        results = [v for vs in pool.map(run, jobs) for v in vs]
    for f in facts:
        cast = [v for v in results if v.get("item_id") == f["fact_id"]]
        m = _majority(cast, votes)
        f["verification"] = {"votes": [v["verdict"] for v in cast], "reviewer_note": m["reviewer_note"] if m else None}
        f["status"] = "VERIFIED" if m and m["verdict"] == "FAITHFUL" else "REVIEW_REQUIRED"


def best(facts_doc: dict | None, kind: str, accept_review: bool = True) -> dict | None:
    """The fact used for a schedule element: VERIFIED first; with accept_review (the standing decision to run
    REVIEW_REQUIRED items forward, flagged) a reviewed-but-not-passed fact with no deterministic issue next."""
    ok = {"VERIFIED", "REVIEW_REQUIRED"} if accept_review else {"VERIFIED"}
    fs = [f for f in (facts_doc or {}).get("facts", []) if f["kind"] == kind and f.get("status") in ok and not f["issues"]
          and f.get("applies_to_all_patients", True) and f.get("interval_days") is not None]
    if not fs:
        return None
    return max(fs, key=lambda f: (f.get("status") == "VERIFIED", f.get("recurring", True), f.get("later_interval_days") is not None))


def run(model: Any, pdf: Path, spec: dict, out_dir: Path) -> dict:
    from .visits import cycle_length

    doc = extract_facts(model, pdf, cycle_length(spec)["value"])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "schedule_facts.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return doc
