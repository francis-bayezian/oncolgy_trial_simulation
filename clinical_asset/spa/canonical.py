"""Canonical outcome normalisation (deterministic first, GPT-5.6 Luna only for leftovers).

The raw measure, value, statistic and time are never changed: canonicalisation only adds
canonical_variable, domain, statistic_family and parsed time fields next to them.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..enrich import outcome_core
from ..llm import StructuredModel

CONFIG = Path(__file__).with_name("canonical_outcomes.json")
TIME = re.compile(
    r"(?P<n>\d+(?:\.\d+)?)[- ]?(?P<u>years?|yrs?|months?|mos?|weeks?|wks?|days?)\b"
    r"|\b(?P<u2>year|month|week|day|cycle)\s+(?P<n2>\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
UNIT = {"y": "year", "m": "month", "w": "week", "d": "day", "c": "cycle"}
TIME_UNITS = {"month", "week", "day", "year", "hour"}


@lru_cache(maxsize=1)
def config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[re.Pattern, dict]]:
    return [(re.compile(p, re.IGNORECASE), entry) for entry in config()["outcomes"] for p in entry["patterns"]]


EXTRA_SUFFIX = re.compile(
    r"\s*(?:,\s*)?(?:based on|according to|using|assessed (?:by|using)|as (?:assessed|measured|determined) by|"
    r"per|by)\s+(?:the\s+)?(?:recist|irecist|mrecist|who|iwg|imwg|lugano|cheson|investigator|independent|blinded|central|"
    r"modified|international|response evaluation|irc|bicr|pcwg).*$",
    re.IGNORECASE,
)
SAFETY_LIKE = re.compile(
    r"\baes?\b|adverse|system organ class|vital sign|shift from baseline|laboratory|lab (?:value|abnormal)|"
    r"blood pressure|heart rate|\becg\b|\bqtc?\b|electrocardiogram|toxicit|\bgrade [345]\b|body temperature|"
    r"left ventricular ejection|\blvef\b",
    re.IGNORECASE,
)


def clinical_phrase(measure: str) -> str:
    return EXTRA_SUFFIX.sub("", outcome_core(measure)).strip() or measure


def safety_like(measure: str) -> bool:
    return bool(SAFETY_LIKE.search(measure))


def canonical_outcome(measure: str) -> dict | None:
    """Rule mapping on the clinical phrase, then on the full title."""
    if safety_like(measure):
        return None
    for text in (clinical_phrase(measure).casefold(), measure.casefold()):
        for pattern, entry in _compiled():
            if pattern.search(text):
                return entry
    return None


def parse_times(*texts: str | None) -> list[tuple[float, str]]:
    found = []
    for text in texts:
        for m in TIME.finditer(text or ""):
            number = float(m.group("n") or m.group("n2"))
            unit = UNIT[(m.group("u") or m.group("u2")).casefold()[0]]
            found.append((number, unit))
    return found


def statistic_family(entry: dict | None, obs: dict) -> str:
    stat, unit = obs.get("statistic"), obs.get("unit")
    value_type = (entry or {}).get("value_type")
    if stat in {"hazard_ratio", "odds_ratio", "risk_ratio"}:
        return stat
    if value_type == "time_to_event" and stat in {"percentage", "proportion"}:
        return "survival_probability"
    if stat in {"median", "mean"} and unit in TIME_UNITS and value_type in {"time_to_event", None}:
        return f"{stat}_time"
    if stat in {"count", "percentage", "proportion"} or obs.get("rate") is not None:
        return "proportion"
    if stat in {"mean", "least_squares_mean", "geometric_mean", "log_mean", "geometric_least_squares_mean"}:
        return "continuous_mean"
    if stat == "median":
        return "continuous_median"
    return "descriptive"


def _first(patterns: list[dict], text: str, key: str) -> str:
    for entry in patterns:
        if any(re.search(p, text, re.IGNORECASE) for p in entry["patterns"]):
            return entry[key]
    return "other"


def disposition_category(reason: str) -> str:
    return _first(config()["disposition"], reason.replace("_", " "), "category")


def response_category(label: str | None) -> str | None:
    if not label:
        return None
    category = _first(config()["response_categories"], label, "category")
    return None if category == "other" else category


# ----------------------------------------------------------------------------- model fallback

_SCHEMA = {
    "type": "object",
    "properties": {
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "measure": {"type": "string"},
                    "canonical_variable": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["measure", "canonical_variable", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mappings"],
    "additionalProperties": False,
}
_INSTRUCTIONS = (
    "Map each oncology trial outcome measure name to exactly one variable from allowed_variables, "
    "or to 'other' when none has the same clinical meaning, or 'not_an_outcome' for pharmacokinetic, "
    "procedural or administrative measures. Do not merge different endpoints: overall survival, "
    "progression-free survival, event-free and disease-free survival are distinct. A rate at a "
    "timepoint keeps its endpoint variable. Copy each measure exactly into 'measure'. Give "
    "confidence between 0 and 1."
)


def model_mappings(model: StructuredModel, measures: list[str], batch: int = 40) -> dict[str, dict[str, Any]]:
    allowed = [e["variable"] for e in config()["outcomes"]]
    result: dict[str, dict[str, Any]] = {}
    for start in range(0, len(measures), batch):
        chunk = measures[start : start + batch]
        answer = model.extract(
            "canonical_outcomes",
            _SCHEMA,
            {"instructions": _INSTRUCTIONS, "allowed_variables": [*allowed, "other", "not_an_outcome"], "measures": chunk},
        )
        for item in answer.get("mappings", []):
            if item["measure"] in chunk and item["canonical_variable"] in {*allowed, "other", "not_an_outcome"}:
                result[item["measure"]] = item
    return result


def entry_for(variable: str) -> dict | None:
    return next((e for e in config()["outcomes"] if e["variable"] == variable), None)
