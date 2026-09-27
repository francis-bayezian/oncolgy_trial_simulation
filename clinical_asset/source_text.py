"""Deterministic parsing of explicit registry wording.

Each parser returns a value only when the source states it unambiguously.
Nothing here uses background medical knowledge to fill gaps.
"""

import re
from typing import Any

_UNIT = r"mg/m\^?2|mg/m²|mg/kg|mg|µg|mcg|g"
_DOSE = re.compile(rf"(?<![\w.])(\d+(?:\.\d+)?)\s*({_UNIT})(?![\w/])", re.IGNORECASE)
_ROUTES = (
    (re.compile(r"\b(?:orally|oral|by mouth|tablets?|capsules?)\b", re.IGNORECASE), "oral"),
    (re.compile(r"\b(?:intravenous(?:ly)?|IV infusion|\(IV\))", re.IGNORECASE), "intravenous"),
    (re.compile(r"\bsubcutaneous(?:ly)?\b", re.IGNORECASE), "subcutaneous"),
)
_FREQUENCIES = (
    (re.compile(r"\b(?:once a day|once daily|QD)\b", re.IGNORECASE), "once daily"),
    (re.compile(r"\b(?:twice a day|twice daily|BID)\b", re.IGNORECASE), "twice daily"),
    (re.compile(r"\b(?:once every 3 weeks|every 3 weeks|Q3W)\b", re.IGNORECASE), "every 3 weeks"),
    (re.compile(r"\b(?:once every 2 weeks|every 2 weeks|Q2W)\b", re.IGNORECASE), "every 2 weeks"),
    (re.compile(r"\b(?:once weekly|every week|QW)\b", re.IGNORECASE), "weekly"),
)
_CYCLE = re.compile(r"\b(\d+)[- ]day cycles?\b", re.IGNORECASE)


def _unit(raw: str) -> str:
    lowered = raw.casefold().replace("\\", "").replace("^", "").replace("²", "2")
    return {"mcg": "µg"}.get(lowered, lowered)


def regimen(description: str, drug_names: list[str]) -> dict[str, Any]:
    """Dose, route and schedule of a single-drug arm, from its own description.

    The dose is accepted only if exactly one dose appears in the sentence that
    names the drug; otherwise the dose is left out.
    """
    if not description or len(drug_names) != 1:
        return {}
    text = description.replace(r"\^", "^")
    name = re.escape(drug_names[0])
    sentences = [s for s in re.split(r"(?<=\.)\s+", text) if re.search(name, s, re.IGNORECASE)]
    if not sentences:
        return {}
    sentence = sentences[0]
    result: dict[str, Any] = {}
    doses = _DOSE.findall(sentence)
    if len(doses) == 1:
        value, unit = doses[0]
        number = float(value)
        result["dose"] = {"value": int(number) if number.is_integer() else number, "unit": _unit(unit)}
    routes = {label for pattern, label in _ROUTES if pattern.search(sentence)}
    if len(routes) == 1:
        result["route"] = routes.pop()
    frequencies = {label for pattern, label in _FREQUENCIES if pattern.search(sentence)}
    if len(frequencies) == 1:
        result["frequency"] = frequencies.pop()
    cycles = set(_CYCLE.findall(sentence))
    if len(cycles) == 1:
        result["cycle_length_days"] = int(cycles.pop())
    return result


def _split_criteria(text: str) -> tuple[list[str], list[str]]:
    parts = re.split(r"exclusion criteria\s*:?", text, maxsplit=1, flags=re.IGNORECASE)
    inclusion_text = re.sub(r"^.*?inclusion criteria\s*:?", "", parts[0], flags=re.IGNORECASE | re.DOTALL)
    exclusion_text = parts[1] if len(parts) > 1 else ""

    def items(block: str) -> list[str]:
        lines = re.split(r"\n\s*(?:[*\-•]|\d+[.)])\s*", "\n" + block)
        return [re.sub(r"\s+", " ", line).strip() for line in lines if line.strip()]

    return items(inclusion_text), items(exclusion_text)


NEGATED_METASTATIC = re.compile(
    r"\b(?:non[- ]?metastatic|no (?:evidence of )?(?:distant )?metastat|without (?:distant )?metastas|"
    r"absence of (?:distant )?metastas|free of metastas|M0\b)",
    re.IGNORECASE,
)


def eligibility_phenotype(module: dict[str, Any]) -> dict[str, Any]:
    """Explicit eligibility limits that define which patients could exist."""
    result: dict[str, Any] = {}
    minimum = re.fullmatch(r"(\d+)\s+Years?", str(module.get("minimumAge") or ""), re.IGNORECASE)
    if minimum:
        result["age_min_years"] = int(minimum.group(1))
    maximum = re.fullmatch(r"(\d+)\s+Years?", str(module.get("maximumAge") or ""), re.IGNORECASE)
    if maximum:
        result["age_max_years"] = int(maximum.group(1))
    inclusion, exclusion = _split_criteria(str(module.get("eligibilityCriteria") or ""))
    joined = " ".join(inclusion)

    ecog = re.search(
        r"\bECOG\b[^.;]*?(?:≤|<=|less than or equal to)\s*(\d)|\bECOG\b[^.;]*?\b0\s*(?:-|–|to|or)\s*(\d)\b",
        joined,
        re.IGNORECASE,
    )
    if ecog:
        upper = int(ecog.group(1) or ecog.group(2))
        result["performance_status"] = {"scale": "ECOG", "allowed": list(range(upper + 1))}
    if re.search(r"\bpreviously treated\b", joined, re.IGNORECASE):
        result["prior_systemic_therapy"] = "required"
    if re.search(r"\btreatment[- ]na[iï]ve\b|\buntreated\b", joined, re.IGNORECASE):
        result["prior_systemic_therapy"] = "not_allowed"
    if re.search(r"locally[- ]advanced(?: and)? unresectable or metastatic", joined, re.IGNORECASE):
        result["disease_extent"] = "locally_advanced_unresectable_or_metastatic"
    elif (
        re.search(r"\bmetastatic\b", joined, re.IGNORECASE)
        and not re.search(r"locally[- ]advanced", joined, re.IGNORECASE)
        and not NEGATED_METASTATIC.search(joined)
    ):
        result["disease_extent"] = "metastatic"
    if re.search(r"\bcentral(?:ly)? (?:testing|confirmed)|confirmed through central testing", joined, re.IGNORECASE):
        result["biomarker_confirmation"] = "central_testing_or_documented"

    # Clinical exclusion concepts come from phenotype.selection_concepts (model + UMLS).
    del exclusion
    return result


_POPULATIONS = (
    (re.compile(r"at least one dose|received (?:any|at least one) (?:dose|study (?:drug|treatment))", re.IGNORECASE), "treated_safety_population"),
    (re.compile(r"full analysis set", re.IGNORECASE), "full_analysis_set"),
    (re.compile(r"intent(?:ion)?-to-treat|\bITT\b", re.IGNORECASE), "intention_to_treat"),
    (re.compile(r"all randomi[sz]ed", re.IGNORECASE), "all_randomized"),
)


def population_label(description: str) -> str | None:
    labels = [label for pattern, label in _POPULATIONS if pattern.search(description or "")]
    if not labels:
        return None
    if "full_analysis_set" in labels and "all_randomized" in labels:
        return "full_analysis_set_all_randomized"
    return labels[0]


def grouping_basis(description: str) -> str | None:
    text = description or ""
    if re.search(r"per treatment received|according to (?:the )?treatment (?:actually )?received", text, re.IGNORECASE):
        return "as_treated"
    if re.search(r"original treatment assignment|per original treatment randomi[sz]ed|as randomi[sz]ed", text, re.IGNORECASE):
        return "as_randomized"
    return None


def outcome_assessment(description: str) -> dict[str, Any]:
    text = description or ""
    result: dict[str, Any] = {}
    criteria = re.search(r"RECIST\s*(?:v(?:ersion)?\s*)?(1\.[01])", text, re.IGNORECASE)
    if criteria:
        result["criteria"] = f"RECIST v{criteria.group(1)}"
    if re.search(r"blinded,? independent,? central review|\bBICR\b", text, re.IGNORECASE):
        result["assessor"] = "blinded_independent_central_review"
    elif re.search(r"\binvestigator[- ]assessed\b|by (?:the )?investigator", text, re.IGNORECASE):
        result["assessor"] = "investigator"
    if re.search(r"post (?:first progression|crossover) was not used|censored at (?:crossover|switch)", text, re.IGNORECASE):
        result["post_crossover_data"] = "excluded"
    return result
