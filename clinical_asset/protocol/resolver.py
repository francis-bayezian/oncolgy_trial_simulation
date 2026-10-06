"""Targeted, agentic resolution of the items a compiled StudySpec still gets wrong (lesson L033). Any protocol.

Recompiling the whole protocol to fix a few items wastes calls and can re-break items that were right. The resolver
works only on the failing items of the saved StudySpec, as an agentic RAG loop over the protocol PDF:

  1. select: items the verifiers judged INCOMPLETE or INCORRECT, or left UNVERIFIED;
  2. retrieve: the item's own sections, plus the paragraphs of the whole document that best match the verifiers'
     objection and the protocol wording they cite (lexical overlap; tables included);
  3. investigate: the model reads the objection and the retrieved passages and returns what the protocol actually
     states, the sections that settle it, and search terms when the evidence is still missing; new terms retrieve
     again (at most MAX_HOPS hops);
  4. resolve: the item is re-extracted from its own sections plus the sections the investigation found, with the
     objection and the finding attached (the compiler's repair builders: every quote is verified again);
  5. re-verify: only that item, by the compiler's three-vote verifier, with the investigated sections as context;
  6. repeat for items still failing, until all are faithful or a round brings no change (at most MAX_ROUNDS).

The resolved spec is written back in place, with `resolution_log.json` recording every hop, the passages used,
the findings and the verdicts. Items still failing are classified and added to the agent backlog.
"""

import json
import re
from collections import Counter
from pathlib import Path

MAX_ROUNDS = 3
MAX_HOPS = 2
TOP_PASSAGES = 8
FAILING = {"INCOMPLETE", "INCORRECT", "UNVERIFIED"}
STOP = set("the a an of to in on for and or with by be is are was were will shall this that these those as at from it its "
           "not no rendering protocol states state rather than whereas does omits instead only".split())

PATCH_FIELDS = ("kind", "relation", "offset_value", "offset_unit", "anchor", "op", "value", "unit", "expected", "modality", "quantity",
                "population", "per_group", "assessment", "summary_measures", "definition", "type")
FREE_TEXT_FIELDS = {"population", "per_group", "assessment", "summary_measures", "definition", "anchor"}
MAX_COPY_WORDS = 6                              # a free-text value longer than this may not copy its evidence (L036)
INVESTIGATE = {
    "type": "object", "additionalProperties": False,
    "required": ["finding", "settled", "relevant_sections", "search_terms", "corrections"],
    "properties": {
        "finding": {"type": "string"},
        "settled": {"type": "boolean"},
        "relevant_sections": {"type": "array", "items": {"type": "string"}},
        "search_terms": {"type": "array", "items": {"type": "string"}},
        "corrections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["target", "field", "value", "evidence_quote"],
            "properties": {"target": {"type": "string"}, "field": {"type": "string", "enum": list(PATCH_FIELDS)},
                           "value": {"type": "string"}, "evidence_quote": {"type": "string"}}}},
    }}
INVESTIGATE_INSTRUCTIONS = (
    "You investigate ONE compiled protocol rule that independent reviewers rejected. You get the compiled rule as "
    "rendered, its parts (leaves L0, L1, ... and the item itself), the reviewers' objection, the protocol wording they "
    "cite, and retrieved protocol passages (section number, title, text). Decide from the passages only what the "
    "protocol actually states for this rule (timing direction, values, units, anchor, scope, modality). Return: finding "
    "(one or two sentences quoting the decisive wording); settled (true when the passages settle it); relevant_sections "
    "(section numbers that settle it, as given); search_terms (when not settled: up to 5 short phrases to search for the "
    "missing evidence); corrections: the smallest field changes that make the compiled rule say exactly what the "
    "protocol says. Each correction names its target (a leaf id such as 'L1', or 'item'), the field (kind: window, "
    "compare, flag or category; relation: WITHIN_BEFORE, WITHIN_AFTER, WITHIN_EITHER, BEFORE, AFTER, AT_LEAST_BEFORE, "
    "AT_LEAST_AFTER, SAME_DAY; offset_value; offset_unit: hour, day, week, month or a stated unit; anchor: the protocol's "
    "own words for the reference event; op; value; unit; expected; modality: REQUIRED, RECOMMENDED, OPTIONAL, PROHIBITED; "
    "quantity; and for an endpoint or analysis: population, per_group (what it is estimated separately for), assessment "
    "(how it is assessed), summary_measures (how it is summarised), definition, type), the new value as text, and "
    "evidence_quote: an exact verbatim quote from the passages that supports it. Write every value as your own concise, "
    "structured statement of the meaning (for example 'central read' or 'number and percentage of patients per event; by "
    "severity'); never copy the protocol sentence into the value. Return no correction you cannot support with a verbatim "
    "quote. Never use knowledge outside the passages.")
UNIT_DAYS = {"hour": 1 / 24, "hours": 1 / 24, "day": 1.0, "days": 1.0, "week": 7.0, "weeks": 7.0, "month": 30.4375, "months": 30.4375}
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
LEAF_ID = re.compile(r"L(\d+)")


def _norm(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def quote_in_document(docs, quote: str) -> bool:
    """A correction counts only when its supporting quote is verbatim in the protocol (text or tables)."""
    q = _norm(quote)
    if len(q) < 4:
        return False
    for d in docs:
        body = _norm(" ".join(s.text() for s in d.sections))
        cells = _norm(" ".join(json.dumps(t.rows, ensure_ascii=False) for s in d.sections for t in s.tables))
        if q in body or q in cells:
            return True
    return False


def copies(value: str, quote: str) -> bool:
    """True when a free-text value is (nearly) the evidence sentence itself rather than the agent's structured statement."""
    vw, qw = _tokens(value), _tokens(quote)
    if len(vw) <= MAX_COPY_WORDS or not qw:
        return False
    shared = sum(1 for i in range(len(vw) - 2) if " ".join(vw[i:i + 3]) in " ".join(qw))
    return shared / max(1, len(vw) - 2) > 0.6


def _leaves_of(item: dict) -> list[dict]:
    from .qualifiers import _leaves

    trees = [item.get(k) for k in ("logic", "trigger", "condition")]
    trees += [(item.get(k) or {}).get("logic") for k in ("start_condition", "stop_condition")]
    return [leaf for t in trees for leaf in _leaves(t)]


def apply_corrections(item: dict, corrections: list[dict], docs) -> list[dict]:
    """Apply the investigator's quote-backed field corrections deterministically; returns those applied."""
    from .normalise import WINDOW

    leaves = _leaves_of(item)
    applied = []
    for c in corrections or []:
        if not quote_in_document(docs, c.get("evidence_quote") or ""):
            continue                                   # an unsupported correction is never applied
        m = LEAF_ID.fullmatch(c.get("target") or "")
        target = item if c.get("target") == "item" else (leaves[int(m.group(1))] if m and int(m.group(1)) < len(leaves) else None)
        if target is None:
            continue
        f, v = c["field"], c["value"]
        if f in FREE_TEXT_FIELDS and copies(v, c.get("evidence_quote") or ""):
            continue                                   # a value that copies the protocol sentence is not the agent's work (L036)
        if f in ("offset_value", "offset_unit"):
            off = dict(target.get("offset") or {})
            if f == "offset_value":
                off["value"] = float(v) if NUMBER.fullmatch(v.strip()) else v
            else:
                off["unit"] = v
            target["offset"] = off
        elif f == "value" and NUMBER.fullmatch(v.strip()):
            target[f] = float(v)
        elif f == "expected":
            target[f] = v.strip().casefold() in ("true", "yes", "present")
        else:
            target[f] = v
        target.setdefault("patched_by_investigation", []).append({"field": f, "value": v, "evidence": c["evidence_quote"]})
        applied.append(c)
    for leaf in leaves:                                 # a patched timing window: its days from relation and offset
        if leaf.get("patched_by_investigation") and leaf.get("kind") == "window":
            off = leaf.get("offset") or {}
            days = UNIT_DAYS.get((off.get("unit") or "").casefold())
            rel = leaf.get("relation")
            if days and off.get("value") is not None and isinstance(off["value"], float):
                v = off["value"] * days
                if rel == "WITHIN_EITHER":
                    leaf["min_days"], leaf["max_days"], leaf["strict"] = -v, v, False
                elif rel in WINDOW:
                    leaf["min_days"], leaf["max_days"], leaf["strict"] = WINDOW[rel](v)
            if rel and off.get("value") is not None:
                leaf["status"], leaf["issues"] = "EXECUTABLE", []
                if not leaf.get("variable"):                # a timing variable named as the compiler names them
                    from .qualifiers import _slug

                    leaf["variable"] = f"timing:{_slug(leaf.get('subject') or leaf.get('text'), 5)}_from_{_slug(leaf.get('anchor'), 4)}"
                    leaf.setdefault("rule_type", "timing")
    return applied


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").casefold()) if t not in STOP and len(t) > 1]


def passages(docs, query: str, k: int = TOP_PASSAGES, exclude: set[str] | None = None) -> list[dict]:
    """Paragraph-level retrieval over every section (text and tables), scored by query-term overlap."""
    q = Counter(_tokens(query))
    if not q:
        return []
    scored = []
    for d in docs:
        for s in d.sections:
            if exclude and s.number in exclude:
                continue
            chunks = [p for p in re.split(r"\n\s*\n", s.text()) if p.strip()] + ["TABLE: " + json.dumps(t.rows, ensure_ascii=False) for t in s.tables]
            for c in chunks:
                toks = Counter(_tokens(c))
                score = sum(min(n, toks[t]) for t, n in q.items())
                if score:
                    scored.append((score, s.number, s.title, " ".join(c.split())[:1500]))
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for score, num, title, text in scored:
        if (num, text[:80]) in seen:
            continue
        seen.add((num, text[:80]))
        out.append({"section": num, "title": title, "text": text, "score": score})
        if len(out) >= k:
            break
    return out


def investigate(model, item: dict, rendering: str, docs) -> dict:
    """The agentic hops for one item: retrieve, read, search again when the evidence is missing."""
    v = item.get("verification") or {}
    objection = " ".join(x for x in [v.get("reviewer_note"), *(v.get("vote_notes") or [])] if x)
    query = " ".join([objection, v.get("problem_quote") or "", rendering])
    own = set(item.get("sections") or [])
    hops, found = [], list(own)
    retrieved = passages(docs, query)
    parts = {f"L{i}": {k: leaf.get(k) for k in ("kind", "text", "relation", "offset", "anchor", "op", "value", "unit", "categories",
                                                    "expected", "status") if leaf.get(k) is not None}
             for i, leaf in enumerate(_leaves_of(item))}
    parts["item"] = {k: (item.get(k).get("text") if isinstance(item.get(k), dict) else item.get(k))
                     for k in ("kind", "modality", "quantity", "value", "unit", "type", "population", "per_group", "assessment",
                               "summary_measures", "definition") if item.get(k) is not None}
    for hop in range(MAX_HOPS + 1):
        payload = {"instructions": INVESTIGATE_INSTRUCTIONS, "compiled_rule": rendering, "parts": parts, "objection": objection,
                   "protocol_wording_cited": v.get("problem_quote"), "passages": retrieved}
        out = model.extract("protocol_investigate", INVESTIGATE, payload)
        hops.append({"hop": hop, "passages": [(p["section"], p["score"]) for p in retrieved], **out})
        found += [s for s in out.get("relevant_sections") or [] if s not in found]
        if out.get("settled") or not out.get("search_terms"):
            break
        retrieved = passages(docs, " ".join(out["search_terms"]), exclude={p["section"] for p in retrieved})
    return {"sections": found, "finding": hops[-1].get("finding"), "settled": bool(hops[-1].get("settled")), "hops": hops,
            "corrections": hops[-1].get("corrections") or []}


def resolve(spec_dir: Path, protocol_pdf: Path, model, terminology=None, votes: int = 3, reverify_all: bool = False) -> dict:
    from . import qualifiers, typecheck
    from .compiler import COMPILER_VERSION, ProtocolCompiler, _classify_residual, _item_id, _to_agent_backlog
    from .ingest import extract
    from .normalise import Provenance, Variables

    spec_dir = Path(spec_dir)
    spec = json.loads((spec_dir / "studyspec.json").read_text(encoding="utf-8"))
    audit = json.loads((spec_dir / "audit.json").read_text(encoding="utf-8")) if (spec_dir / "audit.json").exists() else {}
    review = json.loads((spec_dir / "review_required.json").read_text(encoding="utf-8")) if (spec_dir / "review_required.json").exists() else []
    doc = extract(Path(protocol_pdf))
    docs = [doc]
    compiler = ProtocolCompiler(model, terminology, critical_votes=votes)
    compiler._types = {doc.doc_id: compiler.classify(doc)}          # cached from the compile
    prov = Provenance(doc, COMPILER_VERSION)
    prov.records = list(audit.get("provenance") or [])
    variables = Variables(terminology)
    for var in spec.get("variables") or []:
        variables.registry[var["key"]] = var
    log = {"spec": str(spec_dir), "rounds": []}

    def flag(component, item_id, reason, provenance=None, text=None):
        review.append({"component": component, "item": item_id, "reason": reason, "provenance": provenance, "text": text})

    if reverify_all:                            # every item judged again under the current rendering (L036)
        qualifiers.enrich(spec, docs)
        compiler.verify(spec, docs, flag)
        log["reverified_all"] = True
    before = None
    for rnd in range(MAX_ROUNDS):
        failing = [(c, it) for c, it, _ in compiler._items(spec) if it.get("semantic_status") in FAILING]
        ids = sorted(_item_id(it) for _, it in failing)
        if not failing or ids == before:
            break
        before = ids
        entry = {"round": rnd + 1, "items": {}}
        patched, to_repair = set(), set()
        for _component, it in failing:
            inv = investigate(model, it, it.get("rendering") or "", docs)
            it["sections"] = list(dict.fromkeys((it.get("sections") or []) + [s for s in inv["sections"] if doc.section(s)]))
            it["investigation"] = {"finding": inv["finding"], "settled": inv["settled"], "sections": inv["sections"]}
            applied = apply_corrections(it, inv["corrections"], docs)
            (patched if applied else to_repair).add(_item_id(it))
            entry["items"][_item_id(it)] = {"before": it.get("semantic_status"), "investigation": inv, "patch_applied": applied,
                                            "path": "patch" if applied else "re-extraction"}
        # quote-backed patches first; only items without one are re-extracted, and only those items (L033)
        fixed = (compiler.repair(spec, docs, prov, variables, review, flag, only=to_repair) if to_repair else []) + sorted(patched)
        qualifiers.enrich(spec, docs)
        spec["variables"] = sorted(variables.registry.values(), key=lambda x: x["key"])
        compiler._runtime_and_criticality(spec)
        static, _ = typecheck.check(spec)
        compiler._apply_static(spec, {k: s for k, s in static.items() if k in set(fixed)}, lambda *a, **k: None)
        unverified = {_item_id(i) for _, i, _ in compiler._items(spec) if i.get("semantic_status") == "UNVERIFIED"}
        compiler.verify(spec, docs, flag, only=set(fixed) | (unverified & set(ids)) | set(ids))
        for c, it, _ in compiler._items(spec):
            if _item_id(it) in entry["items"]:
                entry["items"][_item_id(it)]["after"] = it.get("semantic_status")
                entry["items"][_item_id(it)]["rendering"] = it.get("rendering")
        log["rounds"].append(entry)
    compiler._finalise_status(spec)
    spec["unresolved_extraction"] = _classify_residual(spec, compiler._items(spec))
    spec.setdefault("resolution_history", []).append({"resolver": "protocol.resolver", "rounds": len(log["rounds"]),
                                                       "remaining": [r["item"] for r in spec["unresolved_extraction"]]})
    (spec_dir / "studyspec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    (spec_dir / "review_required.json").write_text(json.dumps(review, indent=1, ensure_ascii=False), encoding="utf-8")
    (spec_dir / "unresolved_extraction.json").write_text(json.dumps(spec["unresolved_extraction"], indent=1, ensure_ascii=False), encoding="utf-8")
    (spec_dir / "resolution_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    pid = ((spec.get("metadata") or {}).get("protocol_id") or {}).get("text") or spec_dir.name
    _to_agent_backlog(pid, spec["unresolved_extraction"])
    return {"rounds": len(log["rounds"]), "remaining": spec["unresolved_extraction"],
            "model_calls": getattr(model, "calls", None)}
