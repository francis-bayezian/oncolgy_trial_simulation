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


TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
TEENS = {"eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
         "eighteen": 18, "nineteen": 19}
# a power of ten whose superscript the PDF flattened: '1 x 107 DC' is 1 x 10^7 (L042)
SCIENTIFIC = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*10\s*(?:\^|\*\*)?\s*([1-9]\d?)" + WB)
UP_TO = re.compile(WB + r"(up to|a maximum of|maximum of|not (?:to )?exceed(?:ing)?|no more than|at most)" + WB, re.I)


def word_number(text: str) -> float | None:
    """'Thirty' -> 30, 'twenty-four' -> 24, '(30)' or '30' -> 30."""
    t = (text or "").strip().casefold()
    m = re.search(r"\d+(?:\.\d+)?", t)
    if m:
        return float(m.group(0))
    words = re.findall(r"[a-z]+", t)
    total = None
    for w in words:
        if w in TENS:
            total = (total or 0) + TENS[w]
        elif w in TEENS:
            total = (total or 0) + TEENS[w]
        elif w in NUMBER_WORDS:
            total = (total or 0) + NUMBER_WORDS[w]
    return float(total) if total is not None else None


def scientific(text: str) -> float | None:
    m = SCIENTIFIC.search(text or "")
    return float(m.group(1)) * 10 ** int(m.group(2)) if m else None


def fix_dose(it: dict) -> list[str]:
    """Dose basis and value restored from the dose's own verified quote and the item's evidence: a range quote
    ('12.5-50 mg') is a range, 'up to X' is a maximum, and a flattened power of ten ('1 x 107') is 1 x 10^7. The dose
    value is the lower bound of a range and the stated maximum of 'up to'."""
    fixed, dose = [], it.get("dose") or {}
    quote, evidence = _q(dose.get("quote")), _q(it.get("evidence"))
    sci = scientific(quote) or scientific(evidence if quote and quote in evidence else "")
    if sci is not None and (dose.get("value") is None or dose["value"] < sci / 10):
        unit_q = _q(dose.get("unit_quote"))
        dose.update({"value": sci, "unit": (unit_q.casefold() or dose.get("unit")), "scientific_from": quote})
        fixed.append("scientific")
    md = it.get("max_dose") or {}
    msci = scientific(_q(md.get("text")))
    if msci is not None and (md.get("value") is None or md["value"] < msci / 10):
        tail = re.split(r"10\s*\^?\s*[1-9]\d?", _q(md.get("text")), maxsplit=1)[-1].strip().split(" ")[0]
        md.update({"value": msci, "unit": tail.casefold() or md.get("unit")})
        fixed.append("max_scientific")
    if dose.get("basis") in ("fixed", "unspecified", None):
        if dose.get("tolerance") and dose["tolerance"].get("tolerance") is None and dose.get("value") is not None \
                and abs(dose["tolerance"]["lower"] - dose["value"]) < 1e-9:
            dose["basis"] = "range"
            fixed.append("range")
        elif quote and UP_TO.search(evidence.split(quote)[0][-40:] if quote in evidence else ""):
            dose["basis"] = "maximum"
            fixed.append("maximum")
    return fixed


def fix_offsets(it: dict) -> int:
    """A linked-event offset written in words ('Thirty minutes prior') gets its number and unit (the time unit
    following it in the evidence); equal minimum and maximum offsets are an exact offset."""
    n, evidence = 0, _q(it.get("evidence"))
    for link in it.get("linked_events") or []:
        ev = _q(link.get("evidence")) or evidence
        for key in ("min_offset", "max_offset"):
            off = link.get(key)
            if not off or off.get("value") is not None:
                continue
            text = _q(off.get("text")) if isinstance(off.get("text"), dict) else _q(off)
            v = word_number(text)
            if v is None:
                continue
            m = re.search(re.escape(text) + r"\s*\(?\d*\)?\s*(minutes?|hours?|days?|weeks?|months?)", ev, re.I)
            link[key] = {"value": v, "unit": (m.group(1).casefold().rstrip("s") + "s") if m else None, "text": text}
            n += 1
        lo, hi = link.get("min_offset") or {}, link.get("max_offset") or {}
        if lo.get("value") is not None and lo.get("value") == hi.get("value") and lo.get("unit") == hi.get("unit"):
            link["exact_offset"] = True
    return n


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
        n["dose_basis"] = n.get("dose_basis", 0) + len(fix_dose(it))
        n["offsets"] = n.get("offsets", 0) + fix_offsets(it)
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
