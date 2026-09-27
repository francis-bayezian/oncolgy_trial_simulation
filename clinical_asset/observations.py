"""Canonical observation records for registry outcome measures.

One outcome measure can report several categories (for example complete, partial and stable
response) and several classes (for example timepoints). Each becomes its own observation under
the same outcome key, so nothing is collapsed or renamed with _1, _2 suffixes.

Only reporting grammar lives here: statistics, units, interval types and measure classes.
"""

import re
from typing import Any

_TIME_UNITS = (
    (re.compile(r"\bmonths?\b", re.IGNORECASE), "month"),
    (re.compile(r"\bweeks?\b", re.IGNORECASE), "week"),
    (re.compile(r"\bdays?\b", re.IGNORECASE), "day"),
    (re.compile(r"\byears?\b", re.IGNORECASE), "year"),
    (re.compile(r"\bhours?\b", re.IGNORECASE), "hour"),
)
_PERCENT = re.compile(r"percent|%|\bpct\b", re.IGNORECASE)
_PROPORTION = re.compile(r"\bproportion|\bprobability|\bfraction\b|\bratio\b", re.IGNORECASE)
_PARTICIPANTS = re.compile(r"^\s*(?:number of\s+)?(?:participants?|patients?|subjects?|particpants?|partcipants?|participant s)\s*$", re.IGNORECASE)
_PK = re.compile(
    r"pharmacokinetic|plasma concentration|serum concentration|trough|\bauc\b|area under the (?:curve|concentration)|"
    r"\bc ?max\b|\bt ?max\b|\bc ?min\b|half[- ]life|\bclearance\b|volume of distribution|\bexposure\b",
    re.IGNORECASE,
)
_PK_UNIT = re.compile(r"(?:ng|µg|ug|mcg|pg|mg)\s*[*.·]?\s*(?:h|hr|day)?\s*/\s*m?l\b|(?:h|hr|day)\s*[*.·]\s*(?:ng|ug|µg|mcg|mg)|\bl/h\b", re.IGNORECASE)
_SAFETY = re.compile(
    r"adverse (?:events?|reactions?|experiences?)|\btoxicit|\bsafety\b|tolerab|dose[- ]limiting|\bteaes?\b|\bsaes?\b|"
    r"side effects?|laboratory abnormalit",
    re.IGNORECASE,
)
_STATISTICS = {
    "MEDIAN": "median",
    "MEAN": "mean",
    "GEOMETRIC_MEAN": "geometric_mean",
    "LEAST_SQUARES_MEAN": "least_squares_mean",
    "GEOMETRIC_LEAST_SQUARES_MEAN": "geometric_least_squares_mean",
    "LOG_MEAN": "log_mean",
    "COUNT_OF_PARTICIPANTS": "count",
    "COUNT_OF_UNITS": "count_of_units",
}


def canonical_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    text = " ".join(str(unit).split())
    for pattern, label in _TIME_UNITS:
        if pattern.search(text) and not _PERCENT.search(text) and not re.search(r"\bscore\b|\*", text, re.IGNORECASE):
            return label
    if _PERCENT.search(text):
        return "percent"
    if _PROPORTION.search(text):
        return "proportion"
    if _PARTICIPANTS.match(text):
        return "participants"
    return text.casefold()


def canonical_statistic(param_type: str | None, unit: str | None) -> str:
    param = str(param_type or "").upper()
    if param in _STATISTICS:
        return _STATISTICS[param]
    canonical = canonical_unit(unit)
    if param == "NUMBER":
        if canonical == "percent":
            return "percentage"
        if canonical == "proportion":
            return "proportion"
        if canonical == "participants":
            return "count"
        return "number"
    return re.sub(r"[^a-z0-9]+", "_", param.casefold()).strip("_") or "value"


def measure_class(title: str, unit: str | None) -> str:
    """'pharmacokinetic', 'safety' or 'efficacy' from the measure's own wording."""
    if _PK.search(title) or _PK_UNIT.search(str(unit or "")):
        return "pharmacokinetic"
    if _SAFETY.search(title):
        return "safety"
    return "efficacy"


def _interval(dispersion: str | None) -> str | None:
    text = str(dispersion or "").casefold()
    if "confidence interval" in text:
        return "ci"
    if "inter-quartile" in text or "interquartile" in text:
        return "iqr"
    if "full range" in text or text == "range":
        return "range"
    return None


def observation(item: dict[str, Any], population: dict[str, Any]) -> dict[str, Any]:
    """Registry measurement -> canonical observation. Never relabels an interval type."""
    unit = canonical_unit(item.get("unit"))
    statistic = canonical_statistic(item.get("statistic"), item.get("unit"))
    obs: dict[str, Any] = {"statistic": statistic, "value": item["value"]}
    if unit:
        obs["unit"] = unit
    for field in ("category", "class"):
        if item.get(field):
            obs[field] = str(item[field])[:120]
    if item.get("denominator") is not None:
        obs["N"] = item["denominator"]
    if statistic == "percentage" and isinstance(item["value"], (int, float)) and 0 <= item["value"] <= 100:
        obs["rate"] = round(item["value"] / 100, 4)
    elif statistic == "proportion" and isinstance(item["value"], (int, float)):
        value = item["value"]
        obs["rate"] = round(value / 100, 4) if 1 < value <= 100 else round(value, 4)
    elif statistic == "count" and obs.get("N") and isinstance(item["value"], int) and 0 <= item["value"] <= obs["N"]:
        obs["rate"] = round(item["value"] / obs["N"], 4)
    kind = _interval(item.get("dispersion"))
    if "lower_limit" in item and "upper_limit" in item:
        if kind == "ci":
            level = re.search(r"(\d+(?:\.\d+)?)\s*%", str(item.get("dispersion")))
            obs["ci"] = [item["lower_limit"], item["upper_limit"]]
            obs["ci_level"] = float(level.group(1)) if level else None
        elif kind in {"iqr", "range"}:
            obs[kind] = [item["lower_limit"], item["upper_limit"]]
        else:
            obs["interval"] = [item["lower_limit"], item["upper_limit"]]
            obs["interval_type"] = str(item.get("dispersion") or "unspecified")
    if "spread" in item:
        dispersion = str(item.get("dispersion") or "").casefold()
        field = "sd" if "standard deviation" in dispersion else "se" if "standard error" in dispersion else "spread"
        obs[field] = item["spread"]
    obs.update(population)
    if item.get("population_scope") == "analysis_subset":
        obs["population_scope"] = "analysis_subset"
        obs.setdefault("population_description", str(item.get("analysis_population") or "")[:200])
    if item.get("time_frame"):
        obs["time_frame"] = str(item["time_frame"])[:200]
    if item.get("assessment"):
        obs["assessment"] = item["assessment"]
    obs["measure"] = str(item.get("measure") or "")[:200]
    if obs.get("ci_level") is None:
        obs.pop("ci_level", None)
    return obs
