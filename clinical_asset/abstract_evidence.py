"""Clinical facts from linked result-publication abstracts.

Only publications linked from the registry record are used. A trial without a linked
publication, or whose abstract cannot be retrieved, contributes no publication facts.

Routing (handbook section 35):

1. Rules parse the statistical grammar: "n=12 [25%] vs n=18 [40%]", "5.6 months [95% CI ..]
   vs ..", "hazard ratio 0.66 [0.51-0.86]; p=..", "For X, the most common ... were ...".
2. Names are normalised through UMLS; arm names come from the registry and UMLS aliases.
3. Any results sentence the rules cannot fully resolve goes to GPT-5.6 Luna with scispaCy
   and medspaCy candidates. The model may only quote the sentence.
4. Every fact is validated: quotes must be in the sentence, the treatment must be exactly one
   registry arm, and n / N must reproduce any reported percentage for that arm.
5. A fact that repeats a registry value is merged as one observation with two sources; a
   disagreement is recorded in the audit and kept out of the asset.

No drug, disease, endpoint or event vocabulary is written in this module.
"""

import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .llm import StructuredModel, quoted, relationships
from .observations import canonical_unit
from .phenotype import selection_concepts
from .publications import Publication
from .source_text import outcome_assessment, population_label
from .terminology import DRUG_TYPES, FINDING_TYPES, GENE_TYPES, Terminology, concept_mentions
from .types import ParsedStudy

NUM = r"\d+(?:\.\d+)?"
HEADING = re.compile(
    r"(?:^|(?<=[.)\]]) )(Background|Purpose|Objectives?|Methods|Patients and Methods|"
    r"Findings|Results|Interpretation|Conclusions?|Funding)\s(?=[A-Z0-9])"
)
RESULT_SECTIONS = {"findings", "results", "unstructured"}
METHOD_SECTIONS = {"methods", "patients and methods"}
COUNT_PAIR = re.compile(
    rf"n=(?P<n1>\d+)\s*\[(?P<p1>{NUM})%\]\s*vs\.?\s*n=(?P<n2>\d+)\s*\[(?P<p2>{NUM})%\]",
    re.IGNORECASE,
)
PERCENT_PAIR = re.compile(
    rf"(?<![\w.])(?P<p1>{NUM})%\s*(?:\[(?:95% CI )?{NUM}-{NUM}\]\s*)?vs\.?\s*(?P<p2>{NUM})%",
    re.IGNORECASE,
)
_BOUND = rf"{NUM}|NE|NR|not (?:estimable|reached)"
MEDIAN_PAIR = re.compile(
    rf"(?:median (?P<label>[a-z -]+?) )?(?P<m1>{NUM}) months?\s*\[(?:95% CI )?(?P<l1>{NUM})-(?P<u1>{_BOUND})\]"
    rf"\s*vs\.?\s*(?P<m2>{NUM}) months?\s*\[(?:95% CI )?(?P<l2>{NUM})-(?P<u2>{_BOUND})\]",
    re.IGNORECASE,
)
EFFECT = re.compile(
    rf"(?P<measure>hazard ratio|odds ratio|risk ratio)\s*(?:\[[A-Z]+\]\s*)?(?P<value>{NUM})\s*"
    rf"[\[(]\s*(?:95% CI\s*)?(?P<lower>{NUM})\s*-\s*(?P<upper>{NUM})\s*[\])]"
    rf"(?:\s*[;,]\s*p\s*(?P<op>[=<>])\s*(?P<p>{NUM}))?",
    re.IGNORECASE,
)
ARM_LIST = re.compile(r"^For (?P<arm>[^,]+), the most common (?P<category>.+?) were (?P<items>.+)$", re.IGNORECASE)
LIST_ITEM = re.compile(rf"(?P<term>[A-Za-z][A-Za-z -]*?)\s*\(n=(?P<n>\d+)\s*\[(?P<p>{NUM})%\]\)")
FOLLOW_UP = re.compile(
    rf"median follow-up (?:of|was) (?P<median>{NUM}) months(?: \(IQR (?P<q1>{NUM})-(?P<q3>{NUM})\))?",
    re.IGNORECASE,
)
PERCENT_TOLERANCE = 1.0


@dataclass
class Arm:
    registry_group: str
    drug: str
    names: list[str]


@dataclass
class PublicationEvidence:
    publication_id: str
    text_source: str | None
    facts: list[dict[str, Any]] = field(default_factory=list)
    sentence_log: list[dict[str, Any]] = field(default_factory=list)
    model_log: list[dict[str, Any]] = field(default_factory=list)
    selection_context: dict[str, Any] = field(default_factory=dict)
    endpoint_methods: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Resources:
    terminology: Terminology
    model: StructuredModel | None = None
    mentions: Callable[[str], list] | None = None


def normalise(text: str) -> str:
    t = text.replace("·", ".").replace("–", "-").replace("—", "-").replace("−", "-")
    t = re.sub(r"\bn\s*=\s*", "n=", t)
    t = re.sub(r"mg/m\s*2\b", "mg/m2", t)
    return re.sub(r"\s+", " ", t).strip()


def split_sections(text: str) -> list[tuple[str, str]]:
    marks = list(HEADING.finditer(text))
    if not marks:
        return [("unstructured", text)]
    result = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        result.append((mark.group(1).casefold(), text[mark.end() : end].strip()))
    return result


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.])\s+(?=[A-Z0-9(])", text) if s.strip()]


def _usable_alias(alias: str) -> bool:
    return 3 <= len(alias) <= 40 and not re.search(r"[()\[\],]|containing|product|substance", alias, re.IGNORECASE)


def study_arms(parsed: ParsedStudy, terminology: Terminology) -> list[Arm]:
    """Randomised registry arms with every name the abstract might use: registry wording,
    registry alias evidence and the UMLS aliases of the arm's drug concepts."""
    arms = []
    for profile in parsed.profiles:
        if profile.source_population != "treatment_arm_aggregate":
            continue
        if profile.patient_group.get("treatment_history_in_trial"):
            continue
        drug = profile.treatment.get("drug")
        if not drug:
            continue
        names = {profile.source_arm, drug, str(profile.treatment.get("reported_name") or "")}
        names |= set(profile.treatment.get("aliases", []))
        for cui in profile.treatment.get("umls_cuis", []):
            names |= {a for a in terminology.aliases(cui) if _usable_alias(a)}
        arms.append(Arm(profile.source_arm, drug, sorted((n for n in names if n), key=len, reverse=True)))
    return arms


def _positions(text: str, arm: Arm) -> list[int]:
    return [
        m.start()
        for name in arm.names
        for m in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE)
    ]


def arms_in_order(text: str, arms: list[Arm]) -> list[Arm]:
    found = [(min(p), arm) for arm in arms if (p := _positions(text, arm))]
    return [arm for _, arm in sorted(found, key=lambda item: item[0])]


def _last_arm_before(text: str, arms: list[Arm]) -> Arm | None:
    found = [(max(p), arm) for arm in arms if (p := _positions(text, arm))]
    return max(found, key=lambda item: item[0])[1] if found else None


# Adverse-event reporting grammar (CTCAE wording), not a vocabulary of events.
def _ae_flags(text: str) -> tuple[bool, bool, bool, bool]:
    t = text.casefold()
    grade = bool(re.search(r"grade\s*(?:3 or (?:worse|higher|more|greater)|≥\s*3|>=\s*3|3\s*(?:-|to)\s*[45])", t))
    serious = bool(re.search(r"\bserious\b", t))
    related = bool(re.search(r"treatment[- ]related|drug[- ]related|related to (?:study )?treatment", t))
    adverse = bool(re.search(r"adverse (?:events?|reactions?)|\btraes?\b|\baes?\b", t))
    return grade, serious, related, adverse


def _ae_key(grade: bool, serious: bool, related: bool) -> str:
    return (
        ("grade_3_plus_" if grade else "")
        + ("serious_" if serious else "")
        + ("treatment_related_" if related else "")
        + "AE"
    )


def classify(context: str, following: str, label: str, terminology: Terminology) -> tuple[str, str, str | None] | None:
    """('toxicity', key, None) from reporting grammar, or ('efficacy', key, cui) from a UMLS-linked label."""
    grade, serious, related, adverse = _ae_flags(context)
    if grade or serious or adverse:
        if not adverse:
            # "fewer grade 3 or worse (..) and serious treatment-related adverse events (..)":
            # the first qualifier shares the coordinated head noun.
            head = re.match(
                r"^\W*and\s+(?:[\w-]+\s+){0,3}?(?P<related>treatment[- ]related\s+)?adverse events",
                following,
                re.IGNORECASE,
            )
            if not head:
                return None
            related = related or bool(head.group("related"))
        return "toxicity", _ae_key(grade, serious, related), None
    for text in (label, context):
        concept = _endpoint_concept(text, terminology)
        if concept:
            return "efficacy", concept.key, concept.cui
    return None


def _endpoint_concept(text: str, terminology: Terminology):
    """The longest (then last) UMLS concept in the text that is not a drug, disease, gene or
    event: e.g. the endpoint inside 'Median progression-free survival was'."""
    if not text:
        return None
    candidates = [
        (end - start, end, concept)
        for start, end, concept in concept_mentions(text, terminology)
        if not set(concept.types) & (DRUG_TYPES | FINDING_TYPES | GENE_TYPES)
    ]
    return max(candidates, key=lambda item: item[:2])[2] if candidates else None


def _percent_fits(n: int, total: int | None, percent: float) -> bool:
    return bool(total) and abs(100 * n / total - percent) <= PERCENT_TOLERANCE


def _number(text: str) -> int | float:
    value = float(text)
    return int(value) if value.is_integer() and "." not in text else value


def _denominators(evidence: PublicationEvidence, parsed: ParsedStudy) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for profile in parsed.profiles:
        entry = result.setdefault(profile.source_arm, {})
        if serious := profile.toxicity.get("serious_adverse_events_any_cause"):
            entry["treated"] = serious["N"]
        if profile.patient_group.get("n_basis") == "reported_baseline":
            entry["randomized"] = profile.patient_group["n"]
    for fact in evidence.facts:
        if fact["kind"] == "arm_count":
            result.setdefault(fact["arm"], {})[fact["population"]] = fact["n"]
    return result


def _log(evidence: PublicationEvidence, section: str, sentence: str, status: str, **extra: Any) -> None:
    evidence.sentence_log.append({"section": section, "status": status, "sentence": sentence, **extra})


# --------------------------------------------------------------------------- methods


def _methods(evidence: PublicationEvidence, sentence: str, arms: list[Arm], resources: Resources) -> bool:
    used = False
    for arm in arms:
        for name in arm.names:
            dose = re.search(
                rf"(?<![\w-]){re.escape(name)}\s*\((?P<v>{NUM})\s*(?P<u>mg/m2|mg/kg|mg)\b", sentence, re.IGNORECASE
            )
            if dose:
                evidence.facts.append(
                    {"kind": "arm_dose", "arm": arm.registry_group, "dose": _number(dose.group("v")),
                     "dose_unit": dose.group("u").casefold(), "publication": evidence.publication_id}
                )
                used = True
                break
    assessment = outcome_assessment(sentence)
    label = population_label(sentence)
    if assessment or label:
        for mention in resources.mentions(sentence) if resources.mentions else []:
            concept = resources.terminology.link(mention.text)
            if concept and not set(concept.types) & (DRUG_TYPES | FINDING_TYPES):
                evidence.endpoint_methods[concept.key] = {**assessment, **({"population": label} if label else {})}
                used = True
    return used


# --------------------------------------------------------------------------- results: rules


def _rule_facts(
    evidence: PublicationEvidence, parsed: ParsedStudy, sentence: str, arms: list[Arm], resources: Resources
) -> list[str]:
    """Adds facts found by rules; returns the problems that need the model."""
    problems: list[str] = []
    terminology = resources.terminology

    if re.search(r"at least one dose", sentence, re.IGNORECASE):
        for m in re.finditer(r"(\d+)\s*\(\d+%\)\s*(?:patients\s+)?in the ([\w -]+?) group", sentence):
            arm = _last_arm_before(m.group(2), arms)
            if arm:
                evidence.facts.append({"kind": "arm_count", "arm": arm.registry_group, "population": "treated", "n": int(m.group(1))})
    if re.search(r"randomly assigned|randomi[sz]ed", sentence, re.IGNORECASE):
        for m in re.finditer(r"\(n=(\d+)", sentence):
            arm = _last_arm_before(sentence[max(0, m.start() - 40) : m.start()], arms)
            if arm:
                evidence.facts.append({"kind": "arm_count", "arm": arm.registry_group, "population": "randomized", "n": int(m.group(1))})

    if follow := FOLLOW_UP.search(sentence):
        evidence.facts.append(
            {"kind": "follow_up", "median": _number(follow.group("median")), "unit": "months",
             **({"iqr": [_number(follow.group("q1")), _number(follow.group("q3"))]} if follow.group("q1") else {})}
        )

    denominators = _denominators(evidence, parsed)

    if listing := ARM_LIST.match(sentence):
        named = arms_in_order(listing.group("arm"), arms)
        grade, serious, related, adverse = _ae_flags(listing.group("category"))
        if len(named) != 1 or not adverse:
            return ["arm_or_category_not_identified"]
        arm = named[0]
        total = denominators.get(arm.registry_group, {}).get("treated")
        terms = {}
        for item in LIST_ITEM.finditer(listing.group("items")):
            term = re.sub(r"^(?:and|or)\s+", "", item.group("term").strip(), flags=re.IGNORECASE)
            n, percent = int(item.group("n")), float(item.group("p"))
            if not _percent_fits(n, total, percent):
                problems.append(f"denominator_check_failed:{term}")
                continue
            concept = terminology.link(term, FINDING_TYPES)
            key = concept.key if concept else re.sub(r"[^a-z0-9]+", "_", term.casefold()).strip("_")
            terms[key] = {"n": n, "rate": round(n / total, 4), **({"umls_cui": concept.cui} if concept else {})}
        if terms:
            evidence.facts.append(
                {"kind": "arm_event_terms", "arm": arm.registry_group,
                 "category": _ae_key(grade, serious, related), "N": total, "terms": terms}
            )
        return problems

    matches: list[tuple[int, int, str, re.Match[str]]] = []
    for kind, pattern in (("count", COUNT_PAIR), ("median", MEDIAN_PAIR), ("effect", EFFECT), ("percent", PERCENT_PAIR)):
        for m in pattern.finditer(sentence):
            if not any(m.start() < end and start < m.end() for start, end, _, _ in matches):
                matches.append((m.start(), m.end(), kind, m))
    matches.sort(key=lambda item: item[0])
    if not matches:
        return problems
    order = arms_in_order(sentence, arms)
    if len(order) != 2:
        return ["two_registry_arms_not_named"]
    first, second = order
    last_efficacy: tuple[str, str | None] | None = None
    for index, (start, end, kind, m) in enumerate(matches):
        previous_end = matches[index - 1][1] if index else 0
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(sentence)
        context, following = sentence[previous_end:start], sentence[end:next_start]
        if kind == "effect":
            if last_efficacy is None:
                problems.append("effect_outcome_not_identified")
                continue
            fact: dict[str, Any] = {
                "kind": "comparison", "arm": first.registry_group, "comparator": second.drug,
                "outcome": last_efficacy[0], "measure": re.sub(r"\s+", "_", m.group("measure").casefold()),
                "value": m.group("value"), "ci95": [m.group("lower"), m.group("upper")],
            }
            if m.group("p"):
                if m.group("op") == "=":
                    fact["p_value"] = m.group("p")
                else:
                    fact["p_value_reported"] = f"{m.group('op')}{m.group('p')}"
            evidence.facts.append(fact)
            continue
        label = classify(context, following, (m.groupdict().get("label") or "").strip(), terminology)
        if label is None:
            problems.append(f"outcome_not_identified:{m.group(0)}")
            continue
        section_name, key, cui = label
        if section_name == "efficacy":
            last_efficacy = (key, cui)
        if kind == "median":
            for arm, suffix in ((first, "1"), (second, "2")):
                upper = m.group(f"u{suffix}")
                evidence.facts.append(
                    {"kind": "arm_outcome", "arm": arm.registry_group, "section": section_name, "key": key,
                     "umls_cui": cui, "statistic": "median", "value": m.group(f"m{suffix}"), "unit": "months",
                     "ci95": [m.group(f"l{suffix}"), upper if re.fullmatch(NUM, upper) else None]}
                )
        elif kind == "count":
            population = "treated" if section_name == "toxicity" else "randomized"
            values = [(first, int(m.group("n1")), float(m.group("p1"))), (second, int(m.group("n2")), float(m.group("p2")))]
            totals = [denominators.get(arm.registry_group, {}).get(population) for arm, _, _ in values]
            fits = all(_percent_fits(n, total, p) for (_, n, p), total in zip(values, totals, strict=True))
            swapped = _percent_fits(values[0][1], totals[1], values[0][2]) and _percent_fits(values[1][1], totals[0], values[1][2])
            if not fits:
                problems.append("attribution_conflict_swapped_arms" if swapped else "denominator_check_failed")
                continue
            for (arm, n, _), total in zip(values, totals, strict=True):
                evidence.facts.append(
                    {"kind": "arm_rate", "arm": arm.registry_group, "section": section_name, "key": key,
                     "umls_cui": cui, "n": n, "N": total, "rate": round(n / total, 4)}
                )
        elif kind == "percent":
            for arm, group in ((first, "p1"), (second, "p2")):
                evidence.facts.append(
                    {"kind": "arm_percent", "arm": arm.registry_group, "section": section_name, "key": key,
                     "umls_cui": cui, "rate": round(float(m.group(group)) / 100, 4)}
                )
    return problems


# --------------------------------------------------------------------------- results: model


def _arms_matching(quote: str, arms: list[Arm]) -> list[Arm]:
    return [arm for arm in arms if _positions(quote, arm)]


def _model_facts(
    evidence: PublicationEvidence, parsed: ParsedStudy, sentence: str, arms: list[Arm], resources: Resources
) -> int:
    """GPT-5.6 Luna relationships for a sentence the rules could not resolve. Returns facts added."""
    mentions = resources.mentions(sentence) if resources.mentions else []
    answer = relationships(
        resources.model,
        sentence,
        sorted({name for arm in arms for name in arm.names}),
        [{"text": m.text, "labels": list(m.labels), "negated": m.negated} for m in mentions],
    )
    denominators = _denominators(evidence, parsed)
    existing = {(f.get("arm"), f.get("section"), f.get("key"), f.get("population_quote")) for f in evidence.facts}
    added = 0
    for item in answer.get("relationships", []):
        reason = _validate_model_item(item, sentence)
        treatment = _arms_matching(item.get("treatment_quote", ""), arms)
        if not reason and len(treatment) != 1:
            reason = "treatment_not_exactly_one_registry_arm"
        fact: dict[str, Any] | None = None
        if not reason:
            fact, reason = _model_fact(item, treatment[0], arms, denominators, resources.terminology)
        if fact and (fact.get("arm"), fact.get("section"), fact.get("key"), fact.get("population_quote")) in existing:
            reason = "duplicate_of_rule_fact"
        evidence.model_log.append({"sentence": sentence, "answer": item, "accepted": reason is None, **({"reason": reason} if reason else {})})
        if reason is None and fact is not None:
            evidence.facts.append(fact)
            existing.add((fact.get("arm"), fact.get("section"), fact.get("key"), fact.get("population_quote")))
            added += 1
    return added


def _validate_model_item(item: dict[str, Any], sentence: str) -> str | None:
    for field_name in ("treatment_quote", "outcome_quote", "value_quote", "evidence_quote", "population_quote",
                       "comparator_quote", "ci_quote", "p_value_quote"):
        if not quoted(item.get(field_name, ""), sentence):
            return f"{field_name}_not_in_source"
    if not item.get("value_quote") or not quoted(item["value_quote"], item.get("evidence_quote", "")):
        return "value_not_in_evidence_quote"
    if item.get("population_scope") == "subgroup" and not item.get("population_quote"):
        return "subgroup_without_population_quote"
    return None


def _model_fact(
    item: dict[str, Any], arm: Arm, arms: list[Arm], denominators: dict, terminology: Terminology
) -> tuple[dict[str, Any] | None, str | None]:
    category, statistic, value_quote = item["category"], item["statistic"], item["value_quote"]
    if category not in {"efficacy", "toxicity"}:
        return None, "category_not_supported_yet"
    grade, serious, related, adverse = _ae_flags(item["outcome_quote"])
    if category == "toxicity" and (grade or serious) and adverse:
        key, cui = _ae_key(grade, serious, related), None
    else:
        concept = terminology.link(item["outcome_quote"], FINDING_TYPES if category == "toxicity" else None)
        if concept is None:
            return None, "outcome_not_linked_to_umls"
        key, cui = concept.key, concept.cui
    fact: dict[str, Any] = {"arm": arm.registry_group, "section": category, "key": key, "umls_cui": cui, "via": "model"}
    if item.get("population_scope") == "subgroup":
        fact["population_quote"] = item["population_quote"]
    if statistic in {"hazard_ratio", "odds_ratio", "risk_ratio"}:
        comparators = [a for a in _arms_matching(item.get("comparator_quote", ""), arms) if a is not arm]
        if len(comparators) != 1:
            return None, "comparator_not_exactly_one_other_arm"
        value = re.fullmatch(rf"\s*({NUM})\s*", value_quote)
        if not value:
            return None, "ratio_value_not_numeric"
        fact.update({"kind": "comparison", "comparator": comparators[0].drug, "outcome": key,
                     "measure": statistic, "value": value.group(1)})
        bounds = re.findall(NUM, item.get("ci_quote", ""))
        if len(bounds) >= 2:
            fact["ci95"] = bounds[-2:]
        p = re.search(rf"p\s*([=<>])\s*({NUM})", item.get("p_value_quote", ""), re.IGNORECASE)
        if p and p.group(1) == "=":
            fact["p_value"] = p.group(2)
        elif p:
            fact["p_value_reported"] = p.group(1) + p.group(2)
        return fact, None
    if statistic in {"median", "mean"}:
        m = re.fullmatch(rf"\s*({NUM})\s*(months?|weeks?|days?|years?)\s*", value_quote, re.IGNORECASE)
        if not m:
            return None, "time_value_without_unit"
        bounds = re.findall(NUM, item.get("ci_quote", ""))
        fact.update({"kind": "arm_outcome", "statistic": statistic, "value": m.group(1), "unit": m.group(2).casefold(),
                     "ci95": bounds[-2:] if len(bounds) >= 2 else [None, None]})
        return fact, None
    count = re.search(r"n=(\d+)|^(\d+)\s*(?:\(|\[)", value_quote)
    percent = re.search(rf"({NUM})\s*%", value_quote)
    if count:
        n = int(count.group(1) or count.group(2))
        if "population_quote" in fact:
            if not percent:
                return None, "subgroup_count_without_percentage"
            fact.update({"kind": "arm_percent", "n": n, "rate": round(float(percent.group(1)) / 100, 4)})
            return fact, None
        total = denominators.get(arm.registry_group, {}).get("treated" if category == "toxicity" else "randomized")
        if not total:
            return None, "denominator_unknown"
        if percent and not _percent_fits(n, total, float(percent.group(1))):
            return None, "denominator_check_failed"
        fact.update({"kind": "arm_rate", "n": n, "N": total, "rate": round(n / total, 4)})
        return fact, None
    if percent:
        fact.update({"kind": "arm_percent", "rate": round(float(percent.group(1)) / 100, 4)})
        return fact, None
    return None, "value_not_parsed"


def _finish(
    evidence: PublicationEvidence, section: str, sentence: str, before: int, problems: list[str], model_facts: int
) -> None:
    new = evidence.facts[before:]
    for fact in new:
        fact["publication"] = evidence.publication_id
    extra: dict[str, Any] = {"facts": len(new)} if new else {}
    if model_facts:
        extra["model_facts"] = model_facts
    if new and problems and not model_facts:
        _log(evidence, section, sentence, "PARTIAL_REVIEW_REQUIRED", **extra, problems=problems)
    elif new:
        _log(evidence, section, sentence, "EXTRACTED", **extra)
    elif problems:
        status = "AMBIGUOUS" if any("attribution" in p or "not_named" in p for p in problems) else "REVIEW_REQUIRED"
        _log(evidence, section, sentence, status, problems=problems)
    elif re.search(r"\d", sentence):
        _log(evidence, section, sentence, "NOT_RELEVANT_TO_ASSET")
    else:
        _log(evidence, section, sentence, "NOT_QUANTIFIABLE")


def _needs_model(sentence: str, problems: list[str], rule_facts: int) -> bool:
    if problems:
        return True
    if rule_facts:
        return False
    # Unresolved numbers that look like results: a percentage, an n=, or a time with a unit.
    return bool(re.search(rf"{NUM}\s*%|n=\d+|{NUM}\s*(?:months?|weeks?)", sentence, re.IGNORECASE))


def _prefetch_model_answers(
    parsed: ParsedStudy, publications: list[Publication], resources: Resources, arms: list[Arm], known_cuis: set[str]
) -> None:
    """Find every model call a publication needs with a cheap rules-only pass, then run the
    calls concurrently. The real pass afterwards reads the answers from the disk cache."""
    if resources.model is None:
        return
    jobs: list[tuple] = []
    for publication in publications:
        abstract = " ".join(p["text"] for p in publication.paragraphs if p.get("section") == "abstract")
        if not abstract:
            continue
        scratch = PublicationEvidence("prefetch", publication.text_source)
        for section, body in split_sections(normalise(abstract)):
            if section in METHOD_SECTIONS:
                jobs.append((selection_concepts, body, resources.model, resources.terminology, known_cuis))
            elif section in RESULT_SECTIONS:
                for sentence in split_sentences(body):
                    before = len(scratch.facts)
                    problems = _rule_facts(scratch, parsed, sentence, arms, resources)
                    if _needs_model(sentence, problems, len(scratch.facts) - before):
                        jobs.append(("relationships", sentence))
    names = sorted({name for arm in arms for name in arm.names})
    lock = threading.Lock()

    def run(job: tuple) -> None:
        if job[0] == "relationships":
            with lock:
                mentions = resources.mentions(job[1]) if resources.mentions else []
            relationships(
                resources.model, job[1], names,
                [{"text": m.text, "labels": list(m.labels), "negated": m.negated} for m in mentions],
            )
        else:
            job[0](*job[1:])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run, jobs))


def extract_publication_evidence(
    parsed: ParsedStudy, publications: list[Publication], resources: Resources
) -> list[PublicationEvidence]:
    arms = study_arms(parsed, resources.terminology)
    known_cuis = {
        str(p.cancer["disease"]["umls_cui"]) for p in parsed.profiles if p.cancer.get("disease")
    } | {m["umls_cui"] for p in parsed.profiles for m in p.patient_group.get("biomarkers", [])}
    _prefetch_model_answers(parsed, publications, resources, arms, known_cuis)
    results = []
    for publication in publications:
        identifier = f"PMID:{publication.pmid}" if publication.pmid else f"DOI:{publication.doi}"
        evidence = PublicationEvidence(identifier, publication.text_source)
        abstract = " ".join(p["text"] for p in publication.paragraphs if p.get("section") == "abstract")
        if not abstract:
            evidence.sentence_log.append({"status": "NO_ABSTRACT", "retrieval": publication.retrieval_status})
            results.append(evidence)
            continue
        for section, body in split_sections(normalise(abstract)):
            if section in METHOD_SECTIONS:
                selection, rejected = selection_concepts(body, resources.model, resources.terminology, known_cuis)
                evidence.selection_context = selection
                evidence.model_log.extend({"selection_rejected": r} for r in rejected)
                for sentence in split_sentences(body):
                    before = len(evidence.facts)
                    if _methods(evidence, sentence, arms, resources):
                        _finish(evidence, section, sentence, before, [], 0)
                    else:
                        _log(evidence, section, sentence, "NOT_RELEVANT_TO_ASSET")
            elif section in RESULT_SECTIONS:
                for sentence in split_sentences(body):
                    before = len(evidence.facts)
                    problems = _rule_facts(evidence, parsed, sentence, arms, resources)
                    model_facts = 0
                    if resources.model is not None and _needs_model(sentence, problems, len(evidence.facts) - before):
                        model_facts = _model_facts(evidence, parsed, sentence, arms, resources)
                    _finish(evidence, section, sentence, before, problems, model_facts)
            else:
                for sentence in split_sentences(body):
                    _log(evidence, section, sentence, "NOT_RELEVANT_TO_ASSET")
        results.append(evidence)
    return results


# --------------------------------------------------------------------------- merging


def _decimals(value: Any) -> int:
    text = str(value)
    return len(text.split(".")[1]) if "." in text else 0


def agrees(a: Any, b: Any) -> bool:
    """True when the less precise value is the more precise one rounded (half up)."""
    coarse, fine = (a, b) if _decimals(a) <= _decimals(b) else (b, a)
    quantum = Decimal(1).scaleb(-_decimals(coarse))
    return Decimal(str(fine)).quantize(quantum, rounding=ROUND_HALF_UP) == Decimal(str(coarse))


def _precise(a: Any, b: Any) -> float:
    return float(a if _decimals(a) >= _decimals(b) else b)


def _add_source(entry: dict[str, Any], publication: str) -> None:
    sources = entry.setdefault("sources", ["registry"])
    if publication not in sources:
        sources.append(publication)


def _subgroup_profile(asset: dict[str, Any], arm_profile: dict[str, Any], quote: str) -> dict[str, Any]:
    for profile in asset["clinical_profiles"]:
        if (
            profile["profile_type"] == "reported_subgroup"
            and profile["source"]["registry_group"] == arm_profile["source"]["registry_group"]
            and profile.get("definition", "").casefold() == quote.casefold()
        ):
            return profile
    profile = {
        "profile_type": "reported_subgroup",
        "definition": quote,
        **{k: arm_profile[k] for k in ("cancer", "treatment", "treatment_ontology", "selection_context") if k in arm_profile},
        "source": dict(arm_profile["source"]),
    }
    asset["clinical_profiles"].append(profile)
    return profile


def apply_publication_evidence(asset: dict[str, Any], evidence: list[PublicationEvidence]) -> list[dict[str, Any]]:
    """Add publication facts to the asset. Returns reconciliation records for the audit."""
    profiles = {
        p["source"]["registry_group"]: p
        for p in asset["clinical_profiles"]
        if p["profile_type"] in {"randomized_arm", "study_arm"}
    }
    log: list[dict[str, Any]] = []

    def record(fact: dict[str, Any], outcome: str, **extra: Any) -> None:
        log.append({"reconciliation": outcome, **{k: v for k, v in fact.items() if k != "terms"}, **extra})

    for item in evidence:
        if item.selection_context:
            for profile in asset["clinical_profiles"]:
                context = profile.setdefault("selection_context", {})
                for bucket, entries in item.selection_context.items():
                    target = context.setdefault(bucket, [])
                    for entry in entries:
                        if all(
                            (e["umls_cui"] or e["concept"].casefold()) != (entry["umls_cui"] or entry["concept"].casefold())
                            for e in target
                        ):
                            target.append({**entry, "source": item.publication_id})
        for fact in list(item.facts):
            arm_profile = profiles.get(fact.get("arm", ""))
            pid = fact["publication"]
            kind = fact["kind"]
            if kind == "follow_up":
                for profile in profiles.values():
                    profile.setdefault("efficacy", {})["follow_up"] = [{
                        "statistic": "median", "value": fact["median"], "unit": "month",
                        **({"iqr": fact["iqr"]} if "iqr" in fact else {}),
                        "population": "all_randomized", "source": pid,
                    }]
                record(fact, "EXTRACTED")
                continue
            if arm_profile is None:
                record(fact, "REVIEW_REQUIRED", reason="arm_not_in_asset")
                continue
            profile = arm_profile
            if fact.get("population_quote"):
                profile = _subgroup_profile(asset, arm_profile, fact["population_quote"])
            if kind == "arm_count":
                registry = profile.get("toxicity", {}).get("N") if fact["population"] == "treated" else profile.get(
                    "patient_profile", {}).get("n")
                record(fact, "DUPLICATE" if registry == fact["n"] else "CONFLICT", registry_value=registry)
            elif kind == "arm_dose":
                given = profile.get("treatment", {})
                same = given.get("dose") == fact["dose"] and given.get("dose_unit") == fact["dose_unit"]
                record(fact, "DUPLICATE" if same else "CONFLICT", registry_value=[given.get("dose"), given.get("dose_unit")])
            elif kind == "arm_outcome":
                observations = profile.setdefault("efficacy", {}).setdefault(fact["key"], [])
                unit = canonical_unit(fact["unit"])
                existing = next(
                    (o for o in observations if o.get("statistic") == fact["statistic"] and not o.get("category")
                     and o.get("unit") == unit and "population_scope" not in o),
                    None,
                )
                if existing is not None:
                    ci_ok = all(
                        pub is None or agrees(reg, pub)
                        for reg, pub in zip(existing.get("ci", [None, None]), fact["ci95"], strict=True)
                        if reg is not None
                    )
                    if agrees(existing["value"], fact["value"]) and ci_ok:
                        _add_source(existing, pid)
                        record(fact, "DUPLICATE", registry_value=existing["value"])
                    else:
                        record(fact, "CONFLICT", registry_value=existing["value"])
                else:
                    methods = item.endpoint_methods.get(fact["key"], {})
                    bounds = [float(v) if v is not None else None for v in fact["ci95"]]
                    observations.append({
                        "statistic": fact["statistic"], "value": float(fact["value"]), "unit": unit,
                        **({"ci": bounds, "ci_level": 95.0} if any(b is not None for b in bounds) else {}),
                        **({"population": methods["population"]} if "population" in methods else {}),
                        **({"assessment": {k: v for k, v in methods.items() if k != "population"}}
                           if len(methods) > ("population" in methods) else {}),
                        **({"umls_cui": fact["umls_cui"]} if fact.get("umls_cui") else {}),
                        "source": pid,
                    })
                    record(fact, "EXTRACTED")
            elif kind in {"arm_rate", "arm_percent"} and fact["section"] == "efficacy":
                observations = profile.setdefault("efficacy", {}).setdefault(fact["key"], [])
                observations.append({
                    "statistic": "proportion", "value": fact["rate"], "rate": fact["rate"],
                    **({"n": fact["n"]} if "n" in fact else {}),
                    **({"N": fact["N"]} if "N" in fact else {}),
                    **({"umls_cui": fact["umls_cui"]} if fact.get("umls_cui") else {}),
                    "source": pid,
                })
                record(fact, "EXTRACTED")
            elif kind in {"arm_rate", "arm_percent"}:
                section = profile.setdefault(fact["section"], {})
                if fact["key"] in section:
                    record(fact, "REVIEW_REQUIRED", reason="key_already_present")
                    continue
                section[fact["key"]] = {
                    **({"n": fact["n"]} if "n" in fact else {}),
                    **({"N": fact["N"]} if "N" in fact else {}),
                    "rate": fact["rate"],
                    **({"umls_cui": fact["umls_cui"]} if fact.get("umls_cui") else {}),
                    "source": pid,
                }
                record(fact, "EXTRACTED")
            elif kind == "arm_event_terms":
                key = f"key_{fact['category'].removesuffix('_AE')}_events"
                profile.setdefault("toxicity", {})[key] = {
                    "N": fact["N"], "completeness": "most_common_only", "source": pid, "events": fact["terms"],
                }
                record(fact, "EXTRACTED", terms=list(fact["terms"]))
            elif kind == "comparison":
                comparisons = profile.setdefault("comparisons", [])
                existing = next(
                    (c for c in comparisons if c["outcome"] == fact["outcome"] and c["measure"] == fact["measure"]
                     and c["comparator"] == fact["comparator"]),
                    None,
                )
                if existing:
                    same = agrees(existing["value"], fact["value"]) and all(
                        agrees(a, b) for a, b in zip(existing.get("ci95", []), fact.get("ci95", []), strict=False)
                    ) and (fact.get("p_value") is None or existing.get("p_value") is None
                           or agrees(existing["p_value"], fact["p_value"]))
                    if not same:
                        record(fact, "CONFLICT", registry_value=existing["value"])
                        continue
                    existing["value"] = _precise(existing["value"], fact["value"])
                    if fact.get("ci95") and existing.get("ci95"):
                        existing["ci95"] = [_precise(a, b) for a, b in zip(existing["ci95"], fact["ci95"], strict=True)]
                    if fact.get("p_value") and existing.get("p_value") is not None:
                        existing["p_value"] = _precise(existing["p_value"], fact["p_value"])
                    _add_source(existing, pid)
                    record(fact, "DUPLICATE", registry_value=existing["value"])
                else:
                    comparisons.append({
                        "comparator": fact["comparator"], "outcome": fact["outcome"], "measure": fact["measure"],
                        "value": float(fact["value"]),
                        **({"ci95": [float(v) for v in fact["ci95"]]} if fact.get("ci95") else {}),
                        **({"p_value": float(fact["p_value"])} if fact.get("p_value") else {}),
                        **({"p_value_reported": fact["p_value_reported"]} if fact.get("p_value_reported") else {}),
                        "source": pid,
                    })
                    record(fact, "EXTRACTED")
    return log
