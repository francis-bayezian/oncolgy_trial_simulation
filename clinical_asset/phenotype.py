"""Treatment identity, disease, biomarkers and selection context from the trial's own text.

Nothing here names a drug, disease, gene or event. Identities come from:

* the registry's MeSH intervention mapping and its alias wording (other names, "proposed INN");
* UMLS concepts selected by semantic-type codes;
* generic variant grammar (GENE p.X12Y) confirmed by UMLS gene and variant types;
* quote-validated GPT-5.6 Luna answers, normalised through UMLS.
"""

import re
from typing import Any

from .llm import StructuredModel, drug_ontology, quoted, selection_criteria
from .nlp import Mention
from .terminology import (
    DRUG_TYPES,
    FINDING_TYPES,
    GENE_TYPES,
    NEOPLASM_TYPES,
    PROCEDURE_TYPES,
    VARIANT_TYPES,
    Concept,
    Terminology,
)

VARIANT = re.compile(
    r"\b(?P<gene>[A-Z][A-Z0-9]{1,9})\b[\s,:/-]*(?:p\s*[.,]?\s*)?"
    r"(?P<variant>(?i:[A-Z]\d{1,4}(?:[A-Z]|\*|fs)))(?![\w])"
)
ALIAS = re.compile(
    r"(?P<name>[A-Za-z][\w -]{1,40}?)\s*[\"“(]*\s*(?:proposed INN|INN|also known as|a\.k\.a\.)\s*:?\s*"
    r"(?P<alias>[A-Za-z][\w-]{2,40})",
    re.IGNORECASE,
)
STRUCTURED_ELIGIBILITY = re.compile(
    r"\b(?:ECOG|Karnofsky|performance status|years? (?:old|of age)|aged?\b|informed consent|"
    r"contracepti|pregnan|breast[- ]?feeding|life expectancy)",
    re.IGNORECASE,
)


def _key(value: str) -> str:
    return " ".join(value.split()).casefold()


# ---------------------------------------------------------------------------- treatment


def drug_identities(study: dict[str, Any], terminology: Terminology) -> tuple[dict[str, dict], list[dict]]:
    """Map each registry intervention name to a canonical drug concept, with provenance."""
    protocol = study.get("protocolSection", {})
    interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
    meshes = study.get("derivedSection", {}).get("interventionBrowseModule", {}).get("meshes", [])
    identity = protocol.get("identificationModule", {})
    texts = [
        str(identity.get("officialTitle") or ""),
        str(identity.get("briefTitle") or ""),
        str(protocol.get("descriptionModule", {}).get("briefSummary") or ""),
        *(str(item.get("description") or "") for item in interventions),
    ]
    audit: list[dict] = []
    mesh_concepts = {
        m["term"]: terminology.link(m["term"], DRUG_TYPES) for m in meshes if m.get("term")
    }
    mesh_ids = {m["term"]: m.get("id") for m in meshes if m.get("term")}
    result: dict[str, dict] = {}
    for item in interventions:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        aliases = {name, *(str(n) for n in item.get("otherNames", []) if n)}
        for text in texts:
            for match in ALIAS.finditer(text):
                if _key(match.group("name")).endswith(_key(name)):
                    aliases.add(match.group("alias"))
                    audit.append({"intervention": name, "alias": match.group("alias"), "via": "registry_alias_wording"})
        concepts = {a: terminology.link(a, DRUG_TYPES) for a in aliases}
        result[name] = {"reported_name": name, "aliases": sorted(aliases), "concepts": concepts}

    unmatched_mesh = set(mesh_concepts)
    for name, entry in result.items():
        cuis = {c.cui for c in entry["concepts"].values() if c}
        alias_keys = {_key(a) for a in entry["aliases"]}
        for term, concept in mesh_concepts.items():
            if (concept and concept.cui in cuis) or _key(term) in alias_keys:
                entry["mesh"] = term
                unmatched_mesh.discard(term)
                audit.append({"intervention": name, "mesh": term, "via": "mesh_concept_or_alias_match"})
                break
    unmatched = [name for name, entry in result.items() if "mesh" not in entry]
    if len(unmatched) == 1 and len(unmatched_mesh) == 1:
        term = unmatched_mesh.pop()
        result[unmatched[0]]["mesh"] = term
        result[unmatched[0]]["aliases"].append(term)
        audit.append({"intervention": unmatched[0], "mesh": term, "via": "mesh_one_to_one_remainder"})

    for name, entry in result.items():
        concept = mesh_concepts.get(entry.get("mesh", "")) or next(
            (c for c in entry["concepts"].values() if c), None
        )
        # The MeSH heading is the registry's preferred name; UMLS display names can be brands.
        entry["drug"] = (entry["mesh"].casefold() if entry.get("mesh") else concept.name if concept else name)
        entry["concept"] = concept
        entry["mesh_id"] = mesh_ids.get(entry.get("mesh", ""))
        entry["cuis"] = sorted({c.cui for c in entry["concepts"].values() if c} | ({concept.cui} if concept else set()))
    return result, audit


def treatment_ontology(
    identity: dict, terminology: Terminology, model: StructuredModel | None
) -> tuple[dict[str, Any], list[dict]]:
    """Class and target quoted from the UMLS definition, never from background knowledge."""
    concept: Concept | None = identity.get("concept")
    result: dict[str, Any] = {}
    audit: list[dict] = []
    if concept is None:
        return result, audit
    result["umls_cui"] = concept.cui
    if identity.get("mesh_id"):
        result["mesh_id"] = identity["mesh_id"]
    definition = terminology.definition(concept.cui)
    if not definition or model is None:
        return result, audit
    answer = drug_ontology(model, concept.name, definition)
    for field in ("drug_class_quote", "target_quote"):
        quote = answer.get(field, "")
        if quote and not quoted(quote, definition):
            audit.append({"drug": concept.name, "rejected": field, "reason": "quote_not_in_definition"})
            answer[field] = ""
    if answer.get("drug_class_quote"):
        result["drug_class"] = answer["drug_class_quote"]
    if answer.get("target_quote"):
        variant = biomarkers([answer["target_quote"]], terminology) if variant_covers(answer["target_quote"]) else []
        target = terminology.link(answer["target_quote"], GENE_TYPES | VARIANT_TYPES)
        if variant:
            result["target"] = {"name": variant[0]["name"], "umls_cui": variant[0]["umls_cui"]}
        elif target:
            result["target"] = {"name": target.name, "umls_cui": target.cui}
        else:
            result["target"] = {"reported": answer["target_quote"]}
    if result.get("drug_class") or result.get("target"):
        result["ontology_source"] = "UMLS 2022AB definition"
    return result, audit


# ---------------------------------------------------------------------------- disease and biomarkers


def disease_concepts(texts: list[str], mentions: list[list[Mention]], terminology: Terminology) -> list[dict]:
    """Neoplasm concepts. A whole condition string that is itself a UMLS neoplasm wins;
    otherwise the most specific (longest) neoplasm span, so 'Prostate Cancer' is not reduced
    to the generic 'Cancer'."""
    counts: dict[str, dict] = {}
    for text, found in zip(texts, mentions, strict=True):
        whole = terminology.link(text, NEOPLASM_TYPES)
        if whole is not None:
            entry = counts.setdefault(whole.cui, {"name": whole.name, "umls_cui": whole.cui, "reported": text, "n": 0})
            entry["n"] += 2  # a condition that is exactly a concept outranks spans inside titles
            continue
        spans = [m for m in found if not m.negated]
        linked = [(m, terminology.link(m.text, NEOPLASM_TYPES)) for m in spans]
        linked = [(m, c) for m, c in linked if c]
        for mention, concept in linked:
            outer = any(
                o is not mention and o.start <= mention.start and mention.end <= o.end
                and (o.start, o.end) != (mention.start, mention.end)
                for o, _ in linked
            )
            if outer:
                continue
            entry = counts.setdefault(concept.cui, {"name": concept.name, "umls_cui": concept.cui, "reported": mention.text, "n": 0})
            entry["n"] += 1
    return sorted(counts.values(), key=lambda e: -e["n"])


def biomarkers(texts: list[str], terminology: Terminology) -> list[dict]:
    """Gene variants stated in the text, confirmed as UMLS gene and variant concepts."""
    found: dict[str, dict] = {}
    for text in texts:
        for match in VARIANT.finditer(text):
            gene = match.group("gene")
            variant = match.group("variant").upper()
            gene_concept = terminology.link(gene, GENE_TYPES)
            if gene_concept is None or not gene_concept.exact:
                continue
            concept = terminology.link(f"{gene} p.{variant}", VARIANT_TYPES)
            if concept is None:
                continue
            found.setdefault(
                concept.cui,
                {"gene": gene, "variant": f"p.{variant}", "name": concept.name, "umls_cui": concept.cui},
            )
    return list(found.values())


# ---------------------------------------------------------------------------- selection context


def variant_covers(text: str, share: float = 0.5) -> bool:
    """True when a gene-variant expression is most of the phrase ('KRAS G12C mutation'),
    not a modifier inside it ('direct KRAS G12C inhibitor')."""
    match = VARIANT.search(text)
    return bool(match) and (match.end() - match.start()) / max(len(text.strip()), 1) >= share


def _criterion_concept(quote: str, terminology: Terminology) -> tuple[str | None, str | None, tuple[str, ...]]:
    if variant_covers(quote):
        found = biomarkers([quote], terminology)
        if found:
            return found[0]["umls_cui"], found[0]["name"], tuple(VARIANT_TYPES)
    concept = terminology.link(
        quote, FINDING_TYPES | NEOPLASM_TYPES | DRUG_TYPES | PROCEDURE_TYPES | GENE_TYPES | VARIANT_TYPES
    )
    if concept is None:
        return None, None, ()
    return concept.cui, concept.name, concept.types


EXCEPTION = re.compile(r"^\s*(?:other than|except(?: for)?|excluding|apart from|besides)\b", re.IGNORECASE)
COORDINATED = re.compile(
    r"^(?:an?\s+)?(?P<a>[\w-]+)\s+(?:or|and|and/or)\s+(?P<b>[\w-]+)\s+(?P<head>[\w][\w -]*)$", re.IGNORECASE
)


def resolve_ellipsis(quote: str, text: str) -> str:
    """'PD-1' in '... a PD-1 or PD-L1 inhibitor' -> 'PD-1 inhibitor' (shared head noun)."""
    match = re.search(
        re.escape(quote) + r"\s+(?:or|and|and/or)\s+[\w-]+\s+(?P<head>[A-Za-z][\w-]*)", text, re.IGNORECASE
    )
    if match and len(quote.split()) == 1:
        return f"{quote} {match.group('head')}"
    return quote


def expand_coordination(phrase: str) -> list[str]:
    """'PD-1 or PD-L1 inhibitor' -> ['PD-1 inhibitor', 'PD-L1 inhibitor'] (grammar only)."""
    match = COORDINATED.match(phrase.strip())
    if not match:
        return [phrase]
    head = match.group("head")
    return [f"{match.group('a')} {head}", f"{match.group('b')} {head}"]


def selection_concepts(
    text: str, model: StructuredModel | None, terminology: Terminology, known_cuis: set[str]
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Clinical inclusion, exclusion and prior-therapy criteria, as UMLS concepts."""
    result: dict[str, list[dict]] = {}
    audit: list[dict] = []
    if not text.strip() or model is None:
        return result, audit
    answer = selection_criteria(model, text)
    target = {"inclusion": "required", "exclusion": "excluded", "required_prior_therapy": "required_prior_therapy"}
    expanded: list[tuple[dict, str, str]] = []
    for item in answer.get("criteria", []):
        concept_quote, qualifier = item.get("concept_quote", ""), item.get("qualifier_quote", "")
        if not concept_quote or not quoted(concept_quote, text) or not quoted(qualifier, text):
            audit.append({"criterion": item, "reason": "quote_not_in_source"})
            continue
        if STRUCTURED_ELIGIBILITY.search(concept_quote):
            continue
        if EXCEPTION.match(qualifier):
            # "X other than Y": Y is an exception to an exclusion, never itself excluded.
            audit.append({"criterion": item, "reason": "exception_clause_not_a_criterion"})
            continue
        # "a PD-1 or PD-L1 inhibitor" in the qualifier means two concepts, not one.
        source_phrase = qualifier if _key(concept_quote) in _key(qualifier) and COORDINATED.match(
            re.sub(r"^(?:an?\s+)", "", qualifier.strip())
        ) else concept_quote
        if source_phrase == concept_quote:
            source_phrase = resolve_ellipsis(concept_quote, text)
        for phrase in expand_coordination(source_phrase):
            expanded.append((item, phrase, "" if source_phrase == qualifier else qualifier))
    for item, concept_quote, qualifier in expanded:
        concept_cui, concept_name, types = _criterion_concept(concept_quote, terminology)
        if item["kind"] == "required_prior_therapy":
            if not types:
                unrestricted = terminology.link(concept_quote)
                types = unrestricted.types if unrestricted else ()
            if types and not set(types) & (DRUG_TYPES | PROCEDURE_TYPES):
                audit.append({"criterion": item, "reason": "prior_therapy_resolves_to_non_therapy_concept"})
                continue
        if concept_cui in known_cuis and item["kind"] == "inclusion":
            continue
        # A criterion UMLS cannot resolve is kept with its exact source wording, not dropped.
        entry = {"concept": concept_name or concept_quote, "umls_cui": concept_cui}
        if concept_cui is None:
            audit.append({"criterion": item, "reason": "kept_without_umls_concept"})
        if qualifier and _key(qualifier) not in _key(concept_quote):
            entry["qualifier"] = qualifier
        bucket = result.setdefault(target[item["kind"]], [])
        if all((e["concept"].casefold(), e.get("qualifier")) != (entry["concept"].casefold(), entry.get("qualifier")) for e in bucket):
            bucket.append(entry)
    return result, audit
