"""Qualifiers the structured items lost although their verified quotes carry them (lessons L030, L031), restored
deterministically from those quotes (never from the model), for any protocol. Run after every build and every repair,
before verification, so the rendering the verifiers judge says what the protocol says:

* dose tolerance and ranges: '296±20% MBq' is 296 MBq +/- 20% (237-355), not a fixed 296;
* order relative to another administration: 'Follow the injection with an IV flush' (after), 'prior to', 'before';
* modality of a timing window: 'this visit should occur at least 24 hours later than ...' is recommended, not a
  condition the phase 'starts only when';
* design qualifiers of a test: 'paired', 'signed rank', 'stratified', 'adjusted', 'exact', 'one-sample';
* an endpoint list's lead-in: 'The secondary endpoints will be an estimate of the following for each
  radiopharmaceutical following a central read:' applies to every endpoint listed under it;
* investigator judgement: 'other conditions that may significantly affect X, as judged by the investigator' is a
  patient attribute the investigator decides (a flag), not an inexpressible requirement;
* timing windows: drug-relative units ('five biological half-lives'), two-sided 'within N days of X', and an anchor
  that is only the window's own wording;
* a count of patients to be screened is not the enrolment target.

Every word boundary is built from WB: a regular expression edited through a string once lost its backslash and
gained a backspace character (lesson L012).
"""

import re

WB = "\\b"
TOLERANCE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:±|\+/-|\+-)\s*(\d+(?:\.\d+)?)\s*(%)?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)")
SEQUENCE = [(re.compile(WB + r"follow(?:ed)?\s+(?:the|each|every)?\s*(\w[\w\s()-]{0,40}?)\s+(?:with|by)" + WB, re.I), "after"),
            (re.compile(WB + r"(?:immediately\s+)?(?:after|following)\s+(?:the|each|every)?\s*(\w[\w\s()-]{0,40}?)(?:[,.;]|$)", re.I), "after"),
            (re.compile(WB + r"(?:before|prior to)\s+(?:the|each|every)?\s*(\w[\w\s()-]{0,40}?)(?:[,.;]|$)", re.I), "before")]
RECOMMENDED = re.compile(WB + r"(should|recommended|preferably|ideally|where possible|if possible)" + WB, re.I)
OPTIONAL = re.compile(WB + r"(may|can|at the discretion|optional(?:ly)?)" + WB, re.I)
DESIGN = ["paired", "signed rank", "rank sum", "stratified", "adjusted", "exact", "one-sample", "two-sample", "matched",
          "intra-patient", "within-patient", "mixed model", "repeated measures"]
TIME_UNITS = {"minute", "minutes", "hour", "hours", "day", "days", "week", "weeks", "month", "months", "year", "years", "cycle", "cycles"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
RELATIVE_UNIT = re.compile(WB + r"(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
                           r"((?:biological\s+|elimination\s+)?half[- ]li(?:fe|ves)|cycles?|doses?)" + WB, re.I)
EITHER_SIDE = re.compile(WB + r"within\s+\S+\s+\w+\s+of" + WB, re.I)
DIRECTION = re.compile(WB + r"(before|after|prior|following|preceding|since|from)" + WB, re.I)
JUDGEMENT = re.compile(WB + r"(judg(?:e)?ment|judged|opinion|discretion|deemed|considered by the investigator)" + WB, re.I)
SCREENED = re.compile(WB + r"screen", re.I)
ENROLLED = re.compile(WB + r"(enrol|enroll|randomi[sz]|treated|registered|accrue)", re.I)
SELF_ANCHOR = re.compile(r"^within\s+\S+\s+\w+$", re.I)
# study-entry events: anything timed 'within N days of' them can only come after them (L032), so such a window is
# never made two-sided
STUDY_ENTRY = re.compile(WB + r"(consent|enrol|enroll|registration|registered|randomi[sz]|screening|study entry)", re.I)


def _q(x) -> str:
    return ((x.get("text") if isinstance(x, dict) else x) or "").strip()


def dose_tolerance(quote: str) -> dict | None:
    m = TOLERANCE.search(quote or "")
    if m:
        v, t, pct = float(m.group(1)), float(m.group(2)), bool(m.group(3))
        lo, hi = (v * (1 - t / 100), v * (1 + t / 100)) if pct else (v - t, v + t)
        return {"nominal": v, "tolerance": t, "tolerance_unit": "percent" if pct else "absolute", "lower": round(lo, 4), "upper": round(hi, 4),
                "quote": m.group(0)}
    m = RANGE.search(quote or "")
    if m and float(m.group(1)) < float(m.group(2)):
        return {"lower": float(m.group(1)), "upper": float(m.group(2)), "quote": m.group(0)}
    return None


def sequence(evidence: str) -> dict | None:
    for rx, relation in SEQUENCE:
        m = rx.search(evidence or "")
        if m:
            return {"relation": relation, "anchor_text": " ".join(m.group(1).split()), "quote": m.group(0).strip()}
    return None


def modality(text: str) -> str | None:
    if RECOMMENDED.search(text or ""):
        return "RECOMMENDED"
    if OPTIONAL.search(text or ""):
        return "OPTIONAL"
    return None


def design_qualifiers(text: str) -> list[str]:
    low = " ".join((text or "").casefold().split())
    return [d for d in DESIGN if d in low]


def _leaves(node):
    if isinstance(node, dict):
        if node.get("node") == "LEAF":
            yield node
        for c in node.get("children") or []:
            yield from _leaves(c)


def _slug(text: str, n: int = 6) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", (text or "").casefold())[:n])


def investigator_judgement(leaf: dict) -> bool:
    """An unresolved requirement the protocol leaves to the investigator's judgement becomes a flag the investigator
    sets (rule_type investigator_judgement), so the criterion can execute; its value per patient is resolved like any
    other unknown patient attribute downstream."""
    if leaf.get("kind") != "unresolved" or not JUDGEMENT.search(f"{leaf.get('text') or ''} {leaf.get('qualifier') or ''}"):
        return False
    text = re.sub(r",?\s*as judged by the investigator\.?|,?\s*in the (?:investigator'?s )?opinion of the investigator\.?", "", leaf.get("text") or "", flags=re.I)
    leaf.update({"kind": "flag", "rule_type": "investigator_judgement", "expected": True, "status": "EXECUTABLE",
                 "subject": text.strip(" .") or leaf.get("text"), "variable": f"var:investigator_judged_{_slug(text)}",
                 "issues": [], "judgement": "investigator"})
    return True


def fix_window(leaf: dict, settled: bool = False) -> bool:
    """Timing windows the calendar fields lost (L031):
    * a drug-relative unit ('within five biological half-lives prior to ...') is kept as stated, value parsed;
    * 'within N days of X' with no direction word is two-sided (WITHIN_EITHER), not 'after';
    * an anchor that is only the window's own wording ('within 30 days') is no anchor."""
    if leaf.get("kind") != "window":
        return False
    text, changed = leaf.get("text") or "", False
    off = leaf.get("offset") or {}
    m = RELATIVE_UNIT.search(text)
    if m and not off.get("unit"):
        v = m.group(1).casefold()
        leaf["offset"] = {**off, "value": float(NUMBER_WORDS.get(v, v)), "unit": " ".join(m.group(2).casefold().split())}
        leaf["status"], leaf["issues"] = "EXECUTABLE", []
        changed = True
    entry = STUDY_ENTRY.search(f"{leaf.get('anchor') or ''} {leaf.get('anchor_event') or ''}")
    # a default never overrides a direction the targeted resolver settled from the protocol's own passages (L033)
    if (not settled and leaf.get("relation") in ("WITHIN_AFTER", "WITHIN_BEFORE") and EITHER_SIDE.search(text)
            and not DIRECTION.search(text) and not entry):
        v = (leaf.get("offset") or {}).get("value")
        leaf["relation"] = "WITHIN_EITHER"
        if v is not None and (leaf.get("offset") or {}).get("unit") in ("day", "days"):
            leaf["min_days"], leaf["max_days"] = -float(v), float(v)
        changed = True
    anchor = (leaf.get("anchor") or "").strip()
    event = (leaf.get("anchor_event") or "").replace("_", " ").strip()
    if (anchor and SELF_ANCHOR.match(anchor)) or (event and SELF_ANCHOR.match(event)):
        leaf["anchor"], leaf["anchor_event"], leaf["anchor_note"] = None, None, "no anchor stated in the protocol"
        changed = True
    return changed


def screening_count(q: dict) -> bool:
    """A count of patients to be SCREENED is not the enrolment target (L031: 'Approximately 60 patients will be
    screened' had been compiled as target accrual 60)."""
    ev = _q(q.get("evidence")) + " " + _q(q.get("text"))
    if q.get("quantity") in ("target_accrual", "maximum_accrual") and SCREENED.search(ev) and not ENROLLED.search(ev):
        q["quantity_as_extracted"], q["quantity"] = q["quantity"], "planned_screened"
        return True
    return False


def _lead_in(docs, phrase: str, name: str) -> str | None:
    """The last sentence ending with ':' that contains `phrase` and comes before the endpoint's own name in the same
    section (the lead-in of the list the endpoint belongs to)."""
    if not phrase or not name or not docs:
        return None
    key, nm = " ".join(phrase.split()).casefold(), " ".join(name.split()).casefold()
    for d in docs:
        for s in d.sections:
            text = " ".join(s.text().split())
            at = text.casefold().find(nm)
            if at < 0:
                continue
            leads = [m for m in re.finditer(r"[^.:]*:", text[:at]) if key in m.group(0).casefold()]
            if leads:
                return leads[-1].group(0).strip().rstrip(":")
    return None


def enrich(spec: dict, docs=None) -> dict:
    """Restore the lost qualifiers on every item, in place. Returns counts per kind."""
    n = {"dose_tolerance": 0, "sequence": 0, "window_modality": 0, "design_qualifiers": 0, "endpoint_lead_in": 0,
         "investigator_judgement": 0, "window_fixed": 0, "day_window": 0, "screening_count": 0}
    for it in spec.get("interventions") or []:
        dose = it.get("dose") or {}
        tol = dose_tolerance(_q(dose.get("quote")) or _q(it.get("evidence")))
        if tol and dose.get("value") is not None:
            dose["tolerance"] = tol
            n["dose_tolerance"] += 1
        seq = sequence(_q(it.get("evidence")))
        if seq and seq["anchor_text"].casefold() != _q(it.get("agent")).casefold():   # not the item's own administration
            it["sequence"] = seq
            n["sequence"] += 1
    for p in spec.get("treatment_phases") or []:
        dur = p.get("duration") or {}
        if dur.get("value") is not None and (dur.get("unit") or "").casefold() not in TIME_UNITS:
            m = RANGE.search(_q(dur.get("text")))      # 'Days 2 to 10' is a day window, not a duration of 2 'to'
            p["day_window"] = [float(m.group(1)), float(m.group(2))] if m else None
            p["duration"] = {**dur, "value": None, "unit": None, "invalid_unit": dur.get("unit")}
            n["day_window"] += 1
        sc = p.get("start_condition") or {}
        if sc.get("logic"):
            m = modality(_q(sc.get("text")) or " ".join(leaf.get("text") or "" for leaf in _leaves(sc["logic"])))
            if m:
                sc["modality"] = m
                n["window_modality"] += 1
    for a in spec.get("analyses") or []:
        q = design_qualifiers(_q(a.get("evidence")) + " " + _q(a.get("test")))
        if q:
            a["design_qualifiers"] = q
            n["design_qualifiers"] += 1
    for e in spec.get("endpoints") or []:
        e.pop("lead_in", None)                  # no copied sentences (L036): the resolver agent fills structured fields
    for c in spec.get("eligibility") or []:
        for leaf in _leaves(c.get("logic")):
            if investigator_judgement(leaf):
                n["investigator_judgement"] += 1
            if fix_window(leaf, settled=bool((c.get("investigation") or {}).get("settled"))):
                n["window_fixed"] += 1
    for q in spec.get("sample_size") or []:
        if screening_count(q):
            n["screening_count"] += 1
    spec["qualifier_restoration"] = n
    return n
