"""Deterministic parsing of quoted protocol wording and three-valued rule evaluation.

The language model never supplies a number, an operator or a unit of its own: it copies
exact wording ("greater than or equal to", "1,000", "/µL"). This module turns that wording
into typed values. Every lexicon here is ordinary English or unit notation; nothing is specific
to a disease, drug or sponsor.

Rule trees are JSON-serialisable dicts:

    {"node": "AND" | "OR", "children": [...]}
    {"node": "NOT", "child": {...}}
    {"node": "IF", "condition": {...}, "then": {...}, "else": {...} | None}
    {"node": "LEAF", "kind": "compare" | "range" | "category" | "flag" | "table", ...}

evaluate(tree, patient) returns True, False or None (UNKNOWN: a needed value is missing, a unit
does not match, or the rule is not executable). Missing data never becomes pass or fail.
"""

import math
import re
from typing import Any

WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "first": 1, "second": 2, "third": 3, "fourth": 4,
                "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "half": 0.5}
FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}

# Longest phrases first so "greater than or equal to" wins over "greater than".
COMPARATORS: list[tuple[str, str]] = sorted([
    (">=", ">="), ("≥", ">="), ("=>", ">="), ("greater than or equal to", ">="), ("at least", ">="),
    ("no less than", ">="), ("not less than", ">="), ("equal to or greater than", ">="), ("or more", ">="),
    ("or greater", ">="), ("minimum", ">="), ("minimum of", ">="),
    ("<=", "<="), ("≤", "<="), ("=<", "<="), ("less than or equal to", "<="), ("at most", "<="),
    ("no more than", "<="), ("not more than", "<="), ("not exceeding", "<="), ("equal to or less than", "<="),
    ("or less", "<="), ("maximum", "<="), ("maximum of", "<="), ("up to", "<="), ("within", "<="),
    (">", ">"), ("greater than", ">"), ("more than", ">"), ("above", ">"), ("exceeds", ">"), ("exceeding", ">"),
    ("over", ">"), ("higher than", ">"), ("increases to greater than", ">"), ("improves to", ">="),
    ("<", "<"), ("less than", "<"), ("below", "<"), ("under", "<"), ("lower than", "<"), ("falls below", "<"),
    ("no older than", "<="), ("not older than", "<="), ("no later than", "<="), ("not later than", "<="),
    ("no longer than", "<="), ("older than", ">"), ("later than", ">"), ("longer than", ">"),
    ("=", "=="), ("equal to", "=="), ("equals", "=="), ("is", "=="),
    ("between", "between"),
], key=lambda item: -len(item[0]))
NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s*[¼-¾⅓⅔])?")


def parse_number(text: str | None) -> float | None:
    """First number in the text: digits with thousands separators, decimals, a trailing
    vulgar fraction ("6 ½"), or an ordinal/cardinal word."""
    if not text:
        return None
    found = number_spans(text)
    return found[0][1] if found else None


def number_spans(text: str) -> list[tuple[int, float, int]]:
    """All numbers in reading order as (start, value, end): digits (with separators, decimals and
    a trailing vulgar fraction) and number words ('six weeks' comes before '(Weeks 1-6)')."""
    out: list[tuple[int, float, int]] = []
    for m in NUMBER.finditer(text):
        raw = m.group(0)
        frac = 0.0
        for symbol, value in FRACTIONS.items():
            if symbol in raw:
                frac = value
                raw = raw.replace(symbol, "")
        out.append((m.start(), float(raw.replace(",", "").strip()) + frac, m.end()))
    for m in re.finditer(r"[a-z]+", text.casefold()):
        if m.group(0) in WORD_NUMBERS and m.group(0) != "half":
            out.append((m.start(), float(WORD_NUMBERS[m.group(0)]), m.end()))
    for symbol, value in FRACTIONS.items():
        for m in re.finditer(re.escape(symbol), text):
            if not any(s <= m.start() < e for s, _, e in out):
                out.append((m.start(), value, m.end()))
    return sorted(out)


def unit_after_number(text: str | None) -> str | None:
    """The unit written right after the first number ('28 day cycles' -> 'day', '5 mg/kg' -> 'mg/kg')."""
    if not text:
        return None
    found = number_spans(text)
    if not found:
        return None
    m = re.match(r"\s*-?\s*([A-Za-zµμ%/][A-Za-zµμ/%0-9.²]*)", text[found[0][2]:])
    return m.group(1) if m else None


def numbers(text: str | None) -> list[float]:
    return [float(m.group(0).replace(",", "")) for m in NUMBER.finditer(text or "") if not any(f in m.group(0) for f in FRACTIONS)]


def parse_comparator(text: str | None) -> str | None:
    if not text:
        return None
    t = " " + re.sub(r"\s+", " ", text.casefold()).strip() + " "
    for phrase, op in COMPARATORS:
        if phrase.isalpha() or " " in phrase:
            if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", t):
                return op
        elif phrase in t:
            return op
    return None


def parse_range(text: str | None) -> dict | None:
    """'2 to < 6 years', '1.5 - 1.9', '≥ 16 years', 'between 3 and 21' -> bounds with inclusivity."""
    if not text:
        return None
    t = text.replace("≤", "<=").replace("≥", ">=").replace("–", "-").replace("—", "-")
    nums = [(m.start(), float(m.group(0).replace(",", ""))) for m in NUMBER.finditer(t)]
    if len(nums) >= 2:
        (p1, lo), (p2, hi) = nums[0], nums[1]
        between = t[p1:p2]
        hi_inclusive = not re.search(r"<(?!=)|less than(?! or equal)|below|under", between)
        lo_inclusive = not re.search(r">(?!=)|greater than(?! or equal)|above|over", t[:p1])
        return {"lower": lo, "lower_inclusive": lo_inclusive, "upper": hi, "upper_inclusive": hi_inclusive}
    if len(nums) == 1:
        op = parse_comparator(t[: nums[0][0]]) or parse_comparator(t)
        v = nums[0][1]
        if op in {">=", ">"}:
            return {"lower": v, "lower_inclusive": op == ">=", "upper": None, "upper_inclusive": False}
        if op in {"<=", "<"}:
            return {"lower": None, "lower_inclusive": False, "upper": v, "upper_inclusive": op == "<="}
    return None


UNIT_SYMBOLS = {"µ": "u", "μ": "u", "²": "2", "³": "3", " ": "", " ": ""}


def parse_unit(text: str | None) -> str | None:
    """Canonical unit notation: lower case, micro -> u, superscripts -> digits, no spaces;
    common spellings of time units reduced to a stem (year, month, week, day, hour, minute)."""
    if not text:
        return None
    t = text.strip()
    for a, b in UNIT_SYMBOLS.items():
        t = t.replace(a, b)
    t = t.casefold().strip(" .,:;()")
    t = re.sub(r"(of(age|life)|old)$", "", t)  # "years of age", "days old" -> the time unit
    if not t:
        return None
    for stem in ("year", "month", "week", "day", "hour", "minute", "second"):
        if re.fullmatch(stem + r"s?", t):
            return stem
    t = re.sub(r"^yrs?$", "year", t)
    t = re.sub(r"^anniversar(y|ies)$", "year", t)
    t = re.sub(r"^mos?$", "month", t)
    t = re.sub(r"^wks?$", "week", t)
    t = re.sub(r"^hrs?$", "hour", t)
    t = re.sub(r"^mins?$", "minute", t)
    return t


def is_relative_unit(text: str | None) -> bool:
    """'x ULN', '× upper limit', 'times the', '-fold': the threshold multiplies a reference value."""
    t = (text or "").casefold().strip()
    return bool(re.match(r"^(x|×|times)\b", t) or re.search(r"\b(times|fold)\b|×|\bx\s*(uln|lln|upper|lower|the|normal)", t))


def parse_window(comparator: str | None, value: str | None, unit: str | None, anchor: str | None,
                 context: str | None = None) -> dict | None:
    """Timing requirement -> window in days relative to the anchor event (negative = before it;
    None = unbounded on that side).
      'within 7 days prior to X' -> [-7, 0]        'within 31 days of/following X' -> [0, 31]
      'no older than 7 days at X' -> [-7, 0]        '> 7 days post-operatively' -> [7, None]
      'pre-operatively' (no number) -> [None, 0]    'at least 24 hours after X' -> [1, None]"""
    text = " ".join(x for x in (comparator, value, unit, anchor, context) if x).casefold()
    before = bool(re.search(r"\b(prior|before|preceding|older|old|earlier|pre)\b|\bpre-", text))
    after = bool(re.search(r"\b(after|following|post|since|later)\b|\bpost-", text))
    if before == after:  # neither or both: fall back to 'within ... of X' meaning after X
        if re.search(r"\bwithin\b.*\bof\b", text):
            before, after = False, True
        else:
            return None
    n = parse_number(value) if value and parse_number(value) is not None else parse_number(comparator)
    u = parse_unit(_first_time_word(" ".join(x for x in (unit, value, comparator) if x)))
    days = to_days(n, u)
    sign = -1.0 if before else 1.0
    if days is None:
        if n is None:  # direction only ('pre-operatively'): any time on that side of the anchor
            return {"min_days": None if before else 0.0, "max_days": 0.0 if before else None,
                    "direction": "before_anchor" if before else "after_anchor"}
        return None
    op = parse_comparator(comparator) or "<="
    outside = op in {">", ">="} and not re.search(r"\bwithin\b", text)
    if outside:  # at least / more than N days away from the anchor
        bound = sign * days
        return ({"min_days": None, "max_days": bound} if before else {"min_days": bound, "max_days": None}) | \
            {"direction": "before_anchor" if before else "after_anchor", "strict": op == ">"}
    return {"min_days": min(0.0, sign * days), "max_days": max(0.0, sign * days),
            "direction": "before_anchor" if before else "after_anchor"}


def _first_time_word(text: str) -> str | None:
    for word in re.findall(r"[a-z]+", (text or "").casefold()):
        u = parse_unit(word)
        if u in TIME_TO_DAYS:
            return word
    return None


TIME_TO_DAYS = {"day": 1.0, "week": 7.0, "month": 30.4375, "year": 365.25, "hour": 1 / 24, "minute": 1 / 1440}


def to_days(value: float | None, unit: str | None) -> float | None:
    if value is None or unit not in TIME_TO_DAYS:
        return None
    return value * TIME_TO_DAYS[unit]


# ----------------------------------------------------------------------------- evaluation


def _value(patient: dict, variable: str) -> Any:
    v = patient.get(variable)
    if isinstance(v, dict):  # {"value": x, "unit": u}
        return v
    return {"value": v, "unit": None} if v is not None else None


def _unit_ok(rule_unit: str | None, value_unit: str | None) -> bool:
    return rule_unit is None or value_unit is None or rule_unit == value_unit


def _compare(x: float, op: str, v: float) -> bool:
    return {">=": x >= v, ">": x > v, "<=": x <= v, "<": x < v, "==": math.isclose(x, v), "!=": not math.isclose(x, v)}[op]


def _interval_compare(lo: float | None, hi: float | None, lo_inc: bool, hi_inc: bool, op: str, t: float) -> bool | None:
    """Three-valued comparison of a value known only to lie in an interval (None = unbounded): True if every
    value in the interval satisfies `op t`, False if none does, None otherwise."""
    lo_ = -math.inf if lo is None else lo
    hi_ = math.inf if hi is None else hi
    if op == ">":
        return True if (lo_ > t or (lo_ == t and not lo_inc)) else False if hi_ <= t else None
    if op == ">=":
        return True if lo_ >= t else False if (hi_ < t or (hi_ == t and not hi_inc)) else None
    if op == "<":
        return True if (hi_ < t or (hi_ == t and not hi_inc)) else False if lo_ >= t else None
    if op == "<=":
        return True if hi_ <= t else False if (lo_ > t or (lo_ == t and not lo_inc)) else None
    if op == "==":
        return True if lo_ == hi_ == t else False if (t < lo_ or t > hi_) else None
    if op == "!=":
        r = _interval_compare(lo, hi, lo_inc, hi_inc, "==", t)
        return None if r is None else not r
    return None


def _and3(values) -> bool | None:
    values = list(values)
    return False if any(v is False for v in values) else None if any(v is None for v in values) else True


def evaluate(node: dict | None, patient: dict) -> bool | None:
    if node is None:
        return True
    kind = node.get("node")
    if kind == "AND":
        results = [evaluate(c, patient) for c in node["children"]]
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True
    if kind == "OR":
        results = [evaluate(c, patient) for c in node["children"]]
        if any(r is True for r in results):
            return True
        return None if any(r is None for r in results) else False
    if kind == "NOT":
        r = evaluate(node["child"], patient)
        return None if r is None else not r
    if kind == "IF":
        c = evaluate(node["condition"], patient)
        if c is True:
            return evaluate(node["then"], patient)
        if c is False:
            return evaluate(node.get("else"), patient) if node.get("else") is not None else True
        # Unknown condition: decidable only if both branches agree.
        a = evaluate(node["then"], patient)
        b = evaluate(node.get("else"), patient) if node.get("else") is not None else True
        return a if a == b and a is not None else None
    if kind != "LEAF" or node.get("status") != "EXECUTABLE":
        return None
    leaf = node["kind"]
    if leaf == "table":
        for row in node["rows"]:
            w = evaluate(row["when"], patient)
            if w is None:
                return None
            if w:
                return evaluate({"node": "LEAF", "kind": "compare", "status": "EXECUTABLE", "variable": node["variable"],
                                 "op": node["op"], "value": row["value"], "unit": node.get("unit")}, patient)
        return False  # the table does not cover this patient: the criterion cannot be met
    got = _value(patient, node["variable"])
    if got is not None and got.get("interval") is not None and leaf in {"compare", "range"}:
        return _evaluate_interval(node, got)
    if got is None or got.get("value") is None:
        return None
    x, unit = got["value"], got.get("unit")
    if leaf == "flag":
        return bool(x) == bool(node["expected"])
    if leaf == "category":
        values = set(x) if isinstance(x, (list, set, tuple)) else {x}
        allowed = {str(c).casefold() for c in node["categories"]}
        hit = any(str(v).casefold() in allowed for v in values)
        return hit if node.get("op", "in") == "in" else not hit
    if leaf == "window":  # x = days from the anchor event to the evaluated event (negative = before)
        if not isinstance(x, (int, float)):
            return None
        lo, hi = node.get("min_days"), node.get("max_days")
        strict = node.get("strict", False)  # 'more than N days': the bound away from the anchor is exclusive
        if lo is not None and not (x > lo if strict and lo != 0 else x >= lo):
            return False
        return not (hi is not None and not (x < hi if strict and hi != 0 else x <= hi))
    rule_unit = None if node.get("unit") == "x_reference" else node.get("unit")
    if not isinstance(x, (int, float)) or not _unit_ok(rule_unit, unit):
        return None
    if leaf == "compare":
        threshold = node["value"]
        if node.get("reference"):  # e.g. 1.5 x upper limit of normal: needs the patient's reference value
            ref = _value(patient, node["reference"]["variable"])
            if ref is None or ref.get("value") is None:
                return None
            threshold = threshold * ref["value"]
        return _compare(x, node["op"], threshold)
    if leaf == "range":
        lo, hi = node.get("lower"), node.get("upper")
        if lo is not None and not (x >= lo if node.get("lower_inclusive", True) else x > lo):
            return False
        return not (hi is not None and not (x <= hi if node.get("upper_inclusive", True) else x < hi))
    return None


def leaves(node: dict | None) -> list[dict]:
    if node is None:
        return []
    kind = node.get("node")
    if kind in {"AND", "OR"}:
        return [leaf for c in node["children"] for leaf in leaves(c)]
    if kind == "NOT":
        return leaves(node["child"])
    if kind == "IF":
        return leaves(node["condition"]) + leaves(node["then"]) + leaves(node.get("else"))
    if kind == "LEAF" and node.get("kind") == "table":
        return [node] + [leaf for row in node["rows"] for leaf in leaves(row["when"])]
    return [node] if kind == "LEAF" else []


def status_of(node: dict | None) -> str:
    """EXECUTABLE only when every leaf is executable."""
    ls = leaves(node)
    if not ls:
        return "REVIEW_REQUIRED"
    return "EXECUTABLE" if all(leaf.get("status") == "EXECUTABLE" for leaf in ls) else "REVIEW_REQUIRED"


def _evaluate_interval(node: dict, got: dict) -> bool | None:
    """A compare or range leaf on a patient value known only as an interval
    {"interval": [lo, hi], "lower_inclusive": bool, "upper_inclusive": bool, "unit": u}."""
    rule_unit = None if node.get("unit") == "x_reference" else node.get("unit")
    if node.get("reference") or not _unit_ok(rule_unit, got.get("unit")):
        return None
    lo, hi = got["interval"]
    li, hi_inc = got.get("lower_inclusive", True), got.get("upper_inclusive", True)
    if node["kind"] == "compare":
        return _interval_compare(lo, hi, li, hi_inc, node["op"], node["value"])
    parts = []
    if node.get("lower") is not None:
        parts.append(_interval_compare(lo, hi, li, hi_inc, ">=" if node.get("lower_inclusive", True) else ">", node["lower"]))
    if node.get("upper") is not None:
        parts.append(_interval_compare(lo, hi, li, hi_inc, "<=" if node.get("upper_inclusive", True) else "<", node["upper"]))
    return _and3(parts)
