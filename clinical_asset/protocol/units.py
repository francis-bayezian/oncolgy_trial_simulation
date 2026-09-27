"""Unit dimensions for static type checking of compiled rules.

A unit written in a protocol is reduced to a canonical token string (expressions.parse_unit) and
then to a physical dimension. Two leaves on the same variable must agree on dimension, and a
unit whose segments repeat or cannot be read at all is invalid. The vocabulary is unit notation
only (SI and clinical-laboratory conventions), not medical content.
"""

import re

MASS = {"mg", "g", "ug", "mcg", "microgram", "micrograms", "ng", "kg", "gram", "grams", "milligram", "milligrams"}
VOLUME = {"l", "dl", "ml", "ul", "mm3", "cumm", "microliter", "microlitre", "liter", "litre"}
AMOUNT = {"mmol", "umol", "mol", "meq", "iu", "u", "units", "unit", "cells", "cell"}
TIME = {"second", "minute", "hour", "day", "week", "month", "year"}
LENGTH = {"mm", "cm", "m"}


def _segments(unit: str) -> list[str]:
    return [s for s in re.split(r"/", unit) if s]


def dimension(unit: str | None) -> str:
    """Dimension class of a canonical unit (see expressions.parse_unit), or INVALID / UNKNOWN."""
    if not unit:
        return "DIMENSIONLESS"
    u = unit.strip()
    if u == "x_reference":
        return "RELATIVE_TO_REFERENCE"
    if u in {"%", "percent"}:
        return "FRACTION"
    if u in TIME:
        return "TIME"
    if u in {"gy", "cgy"}:
        return "RADIATION_DOSE"
    if u in {"db"}:
        return "SOUND_LEVEL"
    if u in {"khz", "hz"}:
        return "FREQUENCY"
    segs = _segments(u)
    if len(segs) != len(set(segs)) or re.search(r"(ml/min)\S*\1", u):
        return "INVALID"
    head = segs[0] if segs else ""
    rest = segs[1:]
    # doses: mass per body size (optionally per time)
    if head in MASS and rest and rest[0] in {"m2", "m^2", "kg"}:
        return "DOSE_PER_BSA" if rest[0] != "kg" else "DOSE_PER_WEIGHT"
    if head in MASS and not rest:
        return "MASS"
    if head in {"auc"} or u.startswith("auc"):
        return "TARGET_AUC"
    # counts per volume: '/ul', 'cells/ul', 'x10^9/l'
    if (not head and rest) or (head in {"cells", "cell"} and rest) or re.match(r"x?10\^?\d+$", head):
        return "COUNT_PER_VOLUME"
    if u.startswith("/") and u[1:] in VOLUME:
        return "COUNT_PER_VOLUME"
    if head in MASS | AMOUNT and rest and rest[0] in VOLUME:
        return "CONCENTRATION"
    if head in VOLUME and rest and rest[0] in TIME | {"min", "hr", "h"}:
        return "FLOW_OR_CLEARANCE"
    if head in LENGTH:
        return "LENGTH"
    if head in {"cm2", "mm2", "m2"}:
        return "AREA"
    if head in {"cm3", "mm3", "cc"}:
        return "VOLUME"
    if re.fullmatch(r"[a-z]+", u) and u in VOLUME:
        return "VOLUME"
    if re.search(r"(rbc|wbc)/hpf", u):
        return "COUNT_PER_FIELD"
    return "UNKNOWN"


def invalid(unit: str | None) -> bool:
    return dimension(unit) == "INVALID"
