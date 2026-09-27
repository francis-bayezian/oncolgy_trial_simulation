"""Quote verification, provenance, variable linking and quote -> typed-rule normalisation."""

import itertools
import re
from dataclasses import dataclass, field
from typing import Any

from . import expressions as ex
from .ingest import Document, Section, normalise

# ----------------------------------------------------------------------------- sources


@dataclass
class Source:
    """The text a model call was given: sections (with page-resolved lines) and table cells."""
    sections: list[Section]
    pages: dict[int, str] = field(default_factory=dict)       # normalised text per page
    joined: str = ""                                            # normalised text of all sections
    joined_loose: str = ""
    cells: list[tuple[int, str]] = field(default_factory=list)  # (page, normalised cell text)

    @classmethod
    def of(cls, sections: list[Section], extra: list[tuple[int, str]] | None = None) -> "Source":
        by_page: dict[int, list[str]] = {}
        parts = []
        cells = []
        for s in sections:
            by_page.setdefault(s.page_start, []).append(f"{s.number} {s.title}")
            parts.append(f"{s.number} {s.title}")
            for line in s.lines:
                by_page.setdefault(line.page, []).append(line.text)
                parts.append(line.text)
            for t in s.tables:
                cells.extend(table_streams(t.page, t.rows))
        for page, text in extra or []:
            by_page.setdefault(page, []).append(text)
            parts.append(text)
        raw = "\n".join(parts)
        return cls(sections, {p: normalise("\n".join(v)) for p, v in by_page.items()}, normalise(raw),
                   normalise(raw, drop_hyphens=True), cells)

    def locate(self, quote: str) -> dict:
        """Verification of one quote: found?, where (page), how (exact / hyphen-tolerant / cell)."""
        q = normalise(quote)
        if not q:
            return {"verified": True, "empty": True}
        for page, text in sorted(self.pages.items()):
            if q in text:
                return {"verified": True, "page": page, "match": "exact"}
        if q in self.joined:
            pages = sorted(self.pages)
            for a, b in itertools.pairwise(pages):
                if q in self.pages[a] + " " + self.pages[b]:
                    return {"verified": True, "page": a, "page_end": b, "match": "exact_across_pages"}
            return {"verified": True, "page": min(self.pages) if self.pages else None, "match": "exact"}
        loose = normalise(quote, drop_hyphens=True)
        if loose and loose in self.joined_loose:
            return {"verified": True, "page": None, "match": "hyphen_tolerant"}
        for page, cell in self.cells:
            if q == cell or q in cell:
                return {"verified": True, "page": page, "match": "table_cell"}
        return {"verified": False}

    def locate_gapped(self, quote: str, max_gap: int = 6) -> dict:
        """Documentary quotes that distribute shared wording ('No previous chemotherapy or radiation
        therapy' -> 'No previous radiation therapy'): every word, in order, with at most max_gap
        words skipped between consecutive words. Never used where a value is parsed."""
        found = self.locate_fragments(quote)
        if found["verified"]:
            return found
        want = [w.strip(".,;:()[]\"'") for w in normalise(quote).split()]
        text = [w.strip(".,;:()[]\"'") for w in self.joined.split()]
        if len(want) < 2:
            return found
        for start in range(len(text)):
            if text[start] != want[0]:
                continue
            pos, ok = start, True
            for word in want[1:]:
                nxt = next((j for j in range(pos + 1, min(len(text), pos + 2 + max_gap)) if text[j] == word), None)
                if nxt is None:
                    ok = False
                    break
                pos = nxt
            if ok:
                return {"verified": True, "page": None, "match": "gapped"}
        return found

    def locate_fragments(self, quote: str) -> dict:
        """A quote stitched from pieces with '...' or ';' is not a verbatim quote. Each piece is
        checked separately; the result is labelled 'fragments' and is only acceptable where the
        quote documents evidence, never where a value is parsed from it."""
        found = self.locate(quote)
        if found["verified"]:
            return found
        pieces = [p.strip(" .;,") for p in re.split(r"\.\.\.|…|;", quote) if p.strip(" .;,")]
        if len(pieces) < 2:
            return found
        located = [self.locate(p) for p in pieces]
        if all(x["verified"] for x in located):
            return {"verified": True, "page": located[0].get("page"), "match": "fragments", "fragments": len(pieces)}
        return found


def table_streams(page: int, rows: list[list[str]]) -> list[tuple[int, str]]:
    """Every cell, plus each column and each row read as one text stream. Tables without ruling
    lines split a multi-line cell over several extracted rows; the column stream rejoins it."""
    out = [(page, normalise(c)) for row in rows for c in row if c]
    width = max((len(r) for r in rows), default=0)
    for j in range(width):
        column = " ".join(r[j] for r in rows if j < len(r) and r[j])
        if column:
            out.append((page, normalise(column)))
    for row in rows:
        joined = " ".join(c for c in row if c)
        if joined:
            out.append((page, normalise(joined)))
    return out


class Provenance:
    """Audit layer: every quote the compiler relies on gets one provenance record."""

    def __init__(self, doc: Document, compiler_version: str) -> None:
        self.doc = doc
        self.compiler_version = compiler_version
        self.records: list[dict] = []

    def document_source(self) -> Source:
        """The whole current document, for wording (variable names) defined outside a section."""
        cached = getattr(self, "_doc_source", None)
        if cached is None or cached[0] is not self.doc:
            front = Section("front", "Front matter", 0, 1, 1, 0.0, self.doc.front_matter, [])
            cached = (self.doc, Source.of([front, *self.doc.sections]))
            self._doc_source = cached
        return cached[1]

    def add(self, source: Source, quote: str, component: str, field_name: str, allow_fragments: bool = False) -> dict:
        found = source.locate_gapped(quote) if allow_fragments else source.locate(quote)
        section = None
        if found.get("page") is not None:
            for s in source.sections:
                if s.page_start <= found["page"] <= max(s.page_end, s.page_start):
                    section = s.number
                    break
        record = {"id": f"P{len(self.records) + 1:05d}", "document": self.doc.path, "document_sha256": self.doc.doc_id,
                  "component": component, "field": field_name, "quote": quote, "verified": found["verified"],
                  "match": found.get("match"), "page": found.get("page"), "page_end": found.get("page_end"),
                  "section": section or (source.sections[0].number if source.sections else None),
                  "compiler_version": self.compiler_version}
        self.records.append(record)
        return record


# ----------------------------------------------------------------------------- variables


def canonical_label(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").casefold()).strip("_")


class Variables:
    """Registry of the variables that rules test. Identity, in order of preference:

    * demographic:<age|sex|race|ethnicity> - chosen by the rule type or the plain name;
    * umls:<CUI> - the protocol wording (or canonical label) is an exact UMLS name or alias whose
      semantic group can be a clinical variable for this rule type;
    * var:<canonical_label> - the model's canonical label, which names the same variable
      consistently even when the protocol only implies it ('post-menarchal' -> menarchal_status).

    Protocol wording is kept as mentions; canonical labels never masquerade as quotes."""

    def __init__(self, terminology: Any | None) -> None:
        self.terminology = terminology
        self.registry: dict[str, dict] = {}
        self._by_text: dict[str, str] = {}

    def key(self, text: str | None, rule_type: str | None = None, link: bool = True, canonical: str | None = None,
            prefix: str | None = None) -> str:
        """text: protocol wording (may be empty); canonical: normalised label; prefix: a namespace for
        simulator-owned variables ('timing', 'event', 'count', 'calendar', 'grade') that are never
        UMLS-linked."""
        wording = re.sub(r"\s+", " ", (text or "").strip())
        label = canonical_label(canonical) or canonical_label(wording)
        if not label:
            label = "unnamed"
        if prefix:
            key = f"{prefix}:{label}"
            self._entry(key, label.replace("_", " "), None, [], False, wording, canonical, rule_type)
            return key
        memo = f"{wording.casefold()}|{label}|{rule_type if rule_type in DEMOGRAPHIC else ''}"
        if memo in self._by_text:
            key = self._by_text[memo]
            self._entry(key, None, None, [], False, wording, canonical, rule_type)
            return key
        demographic = DEMOGRAPHIC.get(rule_type or "") or DEMOGRAPHIC_NAMES.get(label) or DEMOGRAPHIC_NAMES.get(wording.casefold())
        concept = None
        if link and self.terminology is not None and not demographic:
            concept = self._link(wording, rule_type) if wording else None
            if concept is None and canonical:
                concept = self._link(canonical.replace("_", " "), rule_type)
            if concept is not None and DEMOGRAPHIC_NAMES.get(concept.name.casefold()):
                demographic = DEMOGRAPHIC_NAMES[concept.name.casefold()]
        if demographic:
            key = f"demographic:{demographic}"
            self._entry(key, demographic, concept.cui if concept else None, list(concept.types) if concept else [], True,
                        wording, canonical, rule_type)
        elif concept is not None:
            key = f"umls:{concept.cui}"
            self._entry(key, concept.name, concept.cui, list(concept.types), True, wording, canonical, rule_type)
        else:
            key = f"var:{label}"
            self._entry(key, label.replace("_", " "), None, [], False, wording, canonical, rule_type)
        self._by_text[memo] = key
        return key

    def _entry(self, key: str, label: str | None, cui: str | None, types: list[str], linked: bool, wording: str,
               canonical: str | None, rule_type: str | None) -> None:
        entry = self.registry.setdefault(key, {"key": key, "label": label or key, "cui": cui, "semantic_types": types,
                                               "linked": linked, "mentions": [], "canonical_labels": [], "rule_types": []})
        if wording and wording not in entry["mentions"]:
            entry["mentions"].append(wording)
        if canonical and canonical_label(canonical) not in entry["canonical_labels"]:
            entry["canonical_labels"].append(canonical_label(canonical))
        if rule_type and rule_type not in entry["rule_types"]:
            entry["rule_types"].append(rule_type)

    def _link(self, text: str, rule_type: str | None):
        """Exact UMLS link of the whole wording (or the wording without a parenthetical, or a
        parenthetical abbreviation of it), accepted only when the concept's semantic group can be
        a patient or clinical variable for this rule type."""
        base = re.sub(r"\s*\([^)]*\)", "", text).strip(" ,.;:")
        candidates = [text.strip(" ,.;:"), base]
        candidates += [p for p in re.findall(r"\(([^)]+)\)", text) if re.fullmatch(r"[A-Z0-9-]{2,8}", p.strip())]
        for candidate in dict.fromkeys(c for c in candidates if c):
            concept = self.terminology.probe(candidate)
            if concept and linkable(concept.types, rule_type):
                return concept
        return None

    def population_subject(self, text: str) -> bool:
        """True when the wording names a group of people ('patients', 'females') rather than a
        characteristic: its exact UMLS concept is a population or patient group."""
        if self.terminology is None or not text:
            return False
        concept = self.terminology.probe(re.sub(r"\s*\([^)]*\)", "", text).strip(" ,.;:"))
        return bool(concept and set(concept.types) & POPULATION_TYPES)


# Demographic characteristics every simulator needs under one canonical key, whatever the wording.
DEMOGRAPHIC = {"age": "age", "sex": "sex"}
DEMOGRAPHIC_NAMES = {"age": "age", "sex": "sex", "gender": "sex", "race": "race", "ethnicity": "ethnicity"}


# Canonical values of the canonical demographic variables, so that a rule written 'Males' matches a
# simulated patient whose sex is 'male'. Plain English words only.
CANONICAL_VALUES = {
    "demographic:sex": {"female": "female", "females": "female", "woman": "female", "women": "female", "girl": "female",
                        "girls": "female", "male": "male", "males": "male", "man": "male", "men": "male", "boy": "male",
                        "boys": "male"},
}


def canonical_categories(variable: str | None, values: list[str]) -> tuple[list[str], list[str]]:
    """Map written category values to the canonical values of a canonical variable; values of other
    variables are kept as written. Returns (values, unrecognised)."""
    table = CANONICAL_VALUES.get(variable or "")
    if not table:
        return values, []
    out, unknown = [], []
    for v in values:
        words = [w for w in re.findall(r"[a-z]+", v.casefold()) if w in table]
        if words:
            if table[words[0]] not in out:
                out.append(table[words[0]])
        else:
            unknown.append(v)
    return out, unknown


# UMLS semantic types (not medical content): groups that name people, abstract ideas or genes.
POPULATION_TYPES = frozenset({"T098", "T099", "T100", "T101", "T096", "T097"})
ABSTRACT_TYPES = frozenset({"T077", "T078", "T079", "T080", "T081", "T082", "T089", "T102", "T169", "T170", "T171", "T185"})
GENE_TYPES = frozenset({"T028", "T086", "T087", "T088"})


def linkable(types: tuple[str, ...], rule_type: str | None) -> bool:
    t = set(types)
    if not t or t & POPULATION_TYPES:
        return False
    if t & GENE_TYPES and rule_type not in {"biomarker", "molecular_subtype"}:
        return False
    return not (t <= ABSTRACT_TYPES and not (rule_type == "life_expectancy" and t & {"T102"}))


# ----------------------------------------------------------------------------- trees


def build_tree(nodes: list[dict]) -> tuple[dict | None, list[str]]:
    """Flat node list -> nested raw tree; returns (tree, structural issues)."""
    issues = []
    by_id = {n["id"]: n for n in nodes}
    roots = [n for n in nodes if n["role"] == "root" or not n["parent"]]
    if len(roots) != 1:
        issues.append(f"expected one root node, found {len(roots)}")
        if not roots:
            return None, issues
    children: dict[str, list[dict]] = {}
    for n in nodes:
        if n["parent"] and n is not roots[0]:
            if n["parent"] not in by_id:
                issues.append(f"node {n['id']} has unknown parent {n['parent']}")
            children.setdefault(n["parent"], []).append(n)

    def nest(n: dict, depth: int = 0) -> dict:
        if depth > 40:
            issues.append("logic nested too deeply (cycle?)")
            return {"raw": n, "children": []}
        return {"raw": n, "children": [nest(c, depth + 1) for c in children.get(n["id"], [])]}
    return nest(roots[0]), issues


def compile_tree(raw: dict | None, source: Source, prov: Provenance, variables: Variables, component: str,
                 issues: list[str]) -> dict | None:
    """Nested raw tree -> executable rule tree (expressions.py format) with per-leaf status."""
    if raw is None:
        return None
    n, kids = raw["raw"], raw["children"]
    t = n["type"]
    if t in {"AND", "OR"}:
        compiled = [compile_tree(k, source, prov, variables, component, issues) for k in kids]
        compiled = [c for c in compiled if c is not None]
        if not compiled:
            issues.append(f"{t} node {n['id']} has no operands")
            return _unresolved(n, "logical node without operands", source, prov, component)
        return compiled[0] if len(compiled) == 1 else {"node": t, "children": compiled}
    if t == "NOT":
        if len(kids) != 1:
            issues.append(f"NOT node {n['id']} needs exactly one operand")
            return _unresolved(n, "NOT without a single operand", source, prov, component)
        return {"node": "NOT", "child": compile_tree(kids[0], source, prov, variables, component, issues)}
    if t == "IF":
        parts = {k["raw"]["role"]: k for k in kids}
        if "condition" not in parts or "then" not in parts:
            issues.append(f"IF node {n['id']} lacks condition or then")
            return _unresolved(n, "IF without condition/then", source, prov, component)
        return {"node": "IF", "condition": compile_tree(parts["condition"], source, prov, variables, component, issues),
                "then": compile_tree(parts["then"], source, prov, variables, component, issues),
                "else": compile_tree(parts["else"], source, prov, variables, component, issues) if "else" in parts else None}
    return compile_leaf(n, source, prov, variables, component)


def _unresolved(n: dict, reason: str, source: Source, prov: Provenance, component: str) -> dict:
    record = prov.add(source, n.get("source_quote") or "", component, "source_quote", allow_fragments=True)
    return {"node": "LEAF", "kind": "unresolved", "status": "REVIEW_REQUIRED", "issues": [reason],
            "rule_type": n.get("rule_type"), "text": n.get("source_quote"), "provenance": record["id"]}


# Relations that need an amount, and the window each gives (value v in days; None = unbounded).
WINDOW = {
    "WITHIN_BEFORE": lambda v: (-v, 0.0, False), "WITHIN_AFTER": lambda v: (0.0, v, False),
    "AT_LEAST_BEFORE": lambda v: (None, -v, False), "AT_LEAST_AFTER": lambda v: (v, None, False),
    "MORE_THAN_BEFORE": lambda v: (None, -v, True), "MORE_THAN_AFTER": lambda v: (v, None, True),
    "ON_OR_BEFORE": lambda v: (None, v, False),
}
UNBOUNDED = {"BEFORE": (None, 0.0), "AFTER": (0.0, None), "SAME_DAY": (0.0, 0.0)}


def compile_leaf(n: dict, source: Source, prov: Provenance, variables: Variables, component: str) -> dict:
    """One model LEAF -> typed executable leaf. Every value comes from a verified quote; semantic
    checks catch leaves that parse but would execute the wrong test."""
    issues: list[str] = []
    warnings: list[str] = []
    record = prov.add(source, n.get("source_quote") or n.get("subject_quote") or "", component, "source_quote",
                      allow_fragments=True)
    for f in ("comparator_quote", "upper_comparator_quote", "value_quote", "upper_value_quote", "unit_quote",
              "reference_quote", "time_quote"):
        if n.get(f) and not prov.add(source, n[f], component, f)["verified"]:
            issues.append(f"{f} not found in source: {n[f]!r}")
    subject = (n.get("subject_quote") or "").strip()
    canonical = (n.get("canonical_subject") or "").strip()
    if subject:
        found = prov.add(source, subject, component, "subject_quote")["verified"] or \
            prov.add(prov.document_source(), subject, component, "subject_quote_document")["verified"]
        if not found:
            if canonical:  # the canonical label names the variable; the non-literal wording is dropped
                warnings.append(f"subject wording not literal in the document, canonical label used: {subject!r}")
                subject = ""
            elif n.get("rule_type") not in DEMOGRAPHIC:
                issues.append(f"subject_quote not found in the document: {subject!r}")
    for c in n.get("category_quotes") or []:
        if not prov.add(source, c, component, "category_quote")["verified"]:
            issues.append(f"category not found in source: {c!r}")
    if n.get("source_quote") and not record["verified"]:
        issues.append("source_quote not found in source")
    kind = n.get("leaf_kind")
    rule_type = n.get("rule_type")
    leaf: dict[str, Any] = {"node": "LEAF", "kind": kind, "rule_type": rule_type, "text": n.get("source_quote"),
                            "subject": subject or None, "canonical": canonical_label(canonical) or None,
                            "provenance": record["id"]}
    named = bool(subject or canonical)
    if kind in {"compare", "range", "category", "flag", "table"}:
        if not named:
            issues.append("no variable named")
        else:
            if rule_type not in DEMOGRAPHIC and subject and not canonical and variables.population_subject(subject):
                issues.append(f"subject names a group of people, not a characteristic: {subject!r}")
            prefix = "calendar" if canonical_label(canonical) in {"day_of_week", "weekday"} else None
            leaf["variable"] = variables.key(subject, rule_type, canonical=canonical, prefix=prefix)
    if n.get("time_quote"):
        leaf["timing"] = {"text": n["time_quote"]}
    if n.get("qualifier_quote"):
        if not prov.add(source, n["qualifier_quote"], component, "qualifier_quote", allow_fragments=True)["verified"]:
            issues.append(f"qualifier_quote not found in source: {n['qualifier_quote']!r}")
        leaf["qualifier"] = n["qualifier_quote"]
    unit_text = n.get("unit_quote") or ""
    if kind in {"compare", "range"}:
        unit = ex.parse_unit(unit_text)
        if unit and not unit.startswith("/") and _written_per(source, n.get("value_quote") or n.get("upper_value_quote"), unit_text):
            unit = "/" + unit  # '1,000/uL' quoted as value '1,000' and unit 'uL': the slash belongs to the unit
        relative = ex.is_relative_unit(unit_text) or bool(n.get("reference_quote"))
        if relative and not n.get("reference_quote"):
            issues.append(f"threshold is a multiple of a reference value but no reference is quoted ({unit_text!r})")
        leaf["unit"] = "x_reference" if relative else unit
    if kind == "compare":
        op = ex.parse_comparator(n.get("comparator_quote"))
        value = ex.parse_number(n.get("value_quote"))
        if op is None:
            issues.append(f"comparator not recognised: {n.get('comparator_quote')!r}")
        elif op == "between":
            issues.append("range wording given as a single comparison")
        if value is None:
            issues.append(f"no number in value: {n.get('value_quote')!r}")
        leaf.update(op=op, value=value)
        if n.get("reference_quote"):
            ref_key = variables.key(f"{n['reference_quote']} of {subject or canonical}", "reference_value", link=False,
                                    canonical=f"{canonical_label(n['reference_quote'])}__{canonical_label(canonical or subject)}")
            leaf["reference"] = {"variable": ref_key, "text": n["reference_quote"]}
    elif kind == "range":
        lo, hi = ex.parse_number(n.get("value_quote")), ex.parse_number(n.get("upper_value_quote"))
        lower_op, upper_op = ex.parse_comparator(n.get("comparator_quote")), ex.parse_comparator(n.get("upper_comparator_quote"))
        if lower_op in {">", ">="} and (upper_op in {"<", "<="} or not n.get("upper_comparator_quote")):
            lower_inclusive = lower_op == ">="
            upper_inclusive = upper_op != "<" if n.get("upper_comparator_quote") else True
        else:
            combined = " ".join(x for x in (n.get("comparator_quote"), n.get("value_quote"), n.get("upper_comparator_quote"),
                                            n.get("upper_value_quote")) if x)
            bounds = ex.parse_range(combined) or {}
            lower_inclusive, upper_inclusive = bounds.get("lower_inclusive", True), bounds.get("upper_inclusive", True)
        leaf.update(lower=lo, upper=hi, lower_inclusive=lower_inclusive, upper_inclusive=upper_inclusive)
        if lo is None and hi is None:
            issues.append("range without parsable bounds")
        elif lo is not None and hi is not None and lo > hi:
            issues.append("range lower bound exceeds upper bound")
    elif kind == "category":
        cats = [c for c in n.get("category_quotes") or [] if c.strip()]
        if not cats:
            issues.append("category test without categories")
        negated = bool(re.search(r"\b(not|no|non|except|other than|excluding)\b", (n.get("comparator_quote") or "").casefold()))
        canonical_cats, unknown = canonical_categories(leaf.get("variable"), cats)
        if unknown:
            issues.append(f"value(s) {unknown} are not values of the canonical variable {leaf.get('variable')}")
        leaf.update(op="not_in" if negated else "in", categories=canonical_cats)
        if canonical_cats != cats:
            leaf["categories_as_written"] = cats
    elif kind == "flag":
        if n.get("expected") not in {"present", "absent"}:
            issues.append("flag without expected presence/absence")
        leaf["expected"] = n.get("expected") == "present"
    elif kind == "event_state":
        state = n.get("event_state")
        if state in (None, "NONE"):
            issues.append("event state not given")
        if not named:
            issues.append("event not named")
        leaf.update(kind="category", event_state=state, op="in", categories=[state],
                    variable=variables.key(subject, "treatment_state", canonical=canonical, prefix="event"))
    elif kind == "event_count":
        value = ex.parse_number(n.get("value_quote"))
        op = ex.parse_comparator(n.get("comparator_quote"))
        if op is None and re.search(r"\b(after|following|completion|completed)\b", (n.get("comparator_quote") or "").casefold()):
            op = ">="  # 'after two cycles' = at least two completed
        if value is None or op in (None, "between"):
            issues.append("event count needs a number and a comparison")
        leaf.update(kind="compare", op=op, value=value, unit=None,
                    variable=variables.key(subject, "treatment_state", canonical=canonical, prefix="count"))
    elif kind == "window":
        _compile_window(n, leaf, issues, source, variables, subject, canonical, unit_text)
    elif kind == "table":
        op = ex.parse_comparator(n.get("comparator_quote"))
        if op is None or op == "between":
            issues.append(f"table threshold comparator not recognised: {n.get('comparator_quote')!r}")
        rows = []
        for i, row in enumerate(n.get("table_rows") or []):
            value = ex.parse_number(row["value_quote"])
            if value is None or not prov.add(source, row["value_quote"], component, "table_value")["verified"]:
                issues.append(f"table row {i + 1}: threshold not parsable or not in source ({row['value_quote']!r})")
                continue
            conds = []
            for cond in row["conditions"]:
                ok = prov.add(source, cond["value_quote"], component, "table_key")["verified"]
                if cond["variable_quote"] and not (prov.add(source, cond["variable_quote"], component, "table_key_variable")["verified"]
                                                   or prov.add(prov.document_source(), cond["variable_quote"], component,
                                                               "table_key_variable_document")["verified"]):
                    ok = ok and bool(cond.get("canonical_variable"))
                if not ok:
                    issues.append(f"table row {i + 1}: key not in source ({cond['variable_quote']!r}={cond['value_quote']!r})")
                if cond["variable_quote"].strip().casefold() == cond["value_quote"].strip().casefold() and not cond.get("canonical_variable"):
                    issues.append(f"table row {i + 1}: key names a value, not a variable ({cond['variable_quote']!r})")
                var = variables.key(cond["variable_quote"], "table_key", canonical=cond.get("canonical_variable"))
                bounds = ex.parse_range(cond["value_quote"])
                if bounds:
                    conds.append({"node": "LEAF", "kind": "range", "status": "EXECUTABLE", "variable": var,
                                  "unit": ex.parse_unit(_unit_word(cond["value_quote"])), **bounds})
                else:
                    values, unknown = canonical_categories(var, [cond["value_quote"].strip()])
                    if unknown:
                        issues.append(f"table row {i + 1}: {unknown} is not a value of {var}")
                    conds.append({"node": "LEAF", "kind": "category", "status": "EXECUTABLE", "variable": var,
                                  "op": "in", "categories": values})
            if not conds:
                issues.append(f"table row {i + 1}: no key conditions")
                continue
            when = conds[0] if len(conds) == 1 else {"node": "AND", "children": conds}
            rows.append({"when": when, "value": value})
        if not rows:
            issues.append("table without usable rows")
        leaf.update(op=op, unit=ex.parse_unit(unit_text), rows=rows)
    elif kind == "unresolved":
        issues.append("requirement could not be expressed as an executable test")
    else:
        issues.append(f"unsupported leaf kind {kind!r}")
    leaf["status"] = "EXECUTABLE" if not issues else "REVIEW_REQUIRED"
    if issues:
        leaf["issues"] = issues
    if warnings:
        leaf["warnings"] = warnings
    return leaf


def _compile_window(n: dict, leaf: dict, issues: list[str], source: Source, variables: Variables, subject: str,
                    canonical: str, unit_text: str) -> None:
    """Typed temporal constraint: event (subject) relative to an anchor event, relation, offsets,
    calendar adjustment. The relation the model classified is cross-checked against the wording."""
    relation = n.get("relation") or "NONE"
    anchor_quote = (n.get("anchor_quote") or "").strip() or _implied_anchor(n) or (n.get("time_quote") or "").strip()
    anchor_label = canonical_label(n.get("canonical_anchor")) or canonical_label(anchor_quote)
    if not anchor_label:
        issues.append("timing window without an anchor event")
    if not (subject or canonical):
        issues.append("timing window without the event it constrains")
    value = ex.parse_number(n.get("value_quote"))
    unit = ex.parse_unit(ex._first_time_word(" ".join(x for x in (unit_text, n.get("value_quote"), n.get("comparator_quote")) if x)))
    days = ex.to_days(value, unit)
    leaf.update(kind="window", relation=relation, anchor=anchor_quote or None, anchor_event=anchor_label or None,
                calendar_adjustment=n.get("calendar_adjustment") or "NONE", offset={"value": value, "unit": unit})
    if relation == "ON_CYCLE_DAY":
        if value is None:
            issues.append("cycle day without a number")
        leaf.update(cycle_day=value, min_days=(value - 1) if value is not None else None,
                    max_days=(value - 1) if value is not None else None, strict=False)
    elif relation in WINDOW:
        if days is None:
            issues.append(f"relation {relation} needs an amount with a time unit")
        else:
            lo, hi, strict = WINDOW[relation](days)
            leaf.update(min_days=lo, max_days=hi, strict=strict)
    elif relation in UNBOUNDED:
        lo, hi = UNBOUNDED[relation]
        leaf.update(min_days=lo, max_days=hi, strict=False)
    else:
        issues.append("timing window without a temporal relation")
    # Cross-check the classified direction against the wording where the wording is explicit.
    context = " ".join(x for x in (n.get("comparator_quote"), n.get("value_quote"), anchor_quote, n.get("source_quote")) if x)
    heuristic = ex.parse_window(n.get("comparator_quote"), n.get("value_quote"), unit_text, anchor_quote, context) \
        or ex.parse_window(n.get("comparator_quote"), n.get("value_quote"), unit_text, anchor_quote,
                           _surrounding(source, n.get("value_quote"), unit_text, n.get("anchor_quote")))
    if heuristic and relation in WINDOW | UNBOUNDED and relation != "SAME_DAY":
        wording_before = heuristic["direction"] == "before_anchor"
        relation_before = "BEFORE" in relation
        if wording_before != relation_before:
            issues.append(f"temporal relation {relation} contradicts the wording ('{context[:80]}')")
    if (subject or canonical) and anchor_label:
        leaf["variable"] = variables.key(f"{subject or canonical} relative to {anchor_quote or anchor_label}", "timing",
                                         canonical=f"{canonical_label(canonical or subject)}__from__{anchor_label}", prefix="timing")


def _implied_anchor(n: dict) -> str | None:
    """'pre-operative', 'post-operatively': the anchor event is named inside the direction word."""
    for f in ("comparator_quote", "qualifier_quote", "source_quote"):
        m = re.search(r"\b((?:pre|post)-?[a-z]+)", (n.get(f) or "").casefold())
        if m:
            return m.group(1)
    return None


def _surrounding(source: Source, value: str | None, unit: str | None, anchor: str | None) -> str | None:
    """The wording between '<value> <unit>' and the anchor in the source ('48 hours prior to
    initiating therapy' -> 'prior to'), used only to find the direction of a window."""
    if not value or not anchor:
        return None
    pattern = re.escape(normalise(value)) + r"\s*" + (re.escape(normalise(unit)) if unit else r"\S*") + r"\W+(.{0,40}?)" + re.escape(normalise(anchor))
    m = re.search(pattern, source.joined)
    return m.group(1) if m else None


def _written_per(source: Source, value: str | None, unit: str | None) -> bool:
    """True when the source writes '<value>/<unit>' (a count per volume), so a unit quoted without
    its slash is restored exactly as written."""
    if not value or not unit:
        return False
    return bool(re.search(re.escape(normalise(value)) + r"\s*/\s*" + re.escape(normalise(unit)), source.joined))


def _unit_word(text: str) -> str | None:
    m = re.search(r"(?:\d|\b)\s*([A-Za-zµμ/%][A-Za-zµμ/%0-9.²]*)\s*$", text or "")
    return m.group(1) if m else None


# ----------------------------------------------------------------------------- schedules and quantities


def parse_days(text: str | None) -> list[int] | None:
    """'Days 1 and 8' -> [1, 8]; 'Day 1' -> [1]; 'Days 1-5' -> [1..5]; 'Days 2 and 3' -> [2, 3]."""
    if not text:
        return None
    t = text.replace("–", "-")
    days: list[int] = []
    for a, b in re.findall(r"(\d+)\s*(?:-|to|through)\s*(\d+)", t):
        days.extend(range(int(a), int(b) + 1))
    t2 = re.sub(r"(\d+)\s*(?:-|to|through)\s*(\d+)", " ", t)
    days.extend(int(x) for x in re.findall(r"\d+", t2))
    return sorted(set(days)) or None


def parse_quantity(value_quote: str | None, unit_quote: str | None = None) -> dict | None:
    value = ex.parse_number(value_quote)
    if value is None:
        return None
    unit = ex.parse_unit(unit_quote) if unit_quote else ex.parse_unit(ex.unit_after_number(value_quote or ""))
    return {"value": value, "unit": unit, "days": ex.to_days(value, unit)}


def dose_basis(unit: str | None) -> str:
    if not unit:
        return "unspecified"
    u = unit.replace(" ", "")
    if "/m2" in u or "/m^2" in u:
        return "per_body_surface_area"
    if "/kg" in u:
        return "per_body_weight"
    if u.startswith("auc"):
        return "target_auc"
    if u in {"gy", "cgy"}:
        return "radiation_dose"
    return "fixed"
