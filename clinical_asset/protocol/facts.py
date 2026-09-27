"""Quantitative protocol facts: what a protocol states about its patients and their outcomes.

The StudySpec holds the rules of a trial. The simulation also needs the numbers a protocol states about
patients: the distribution of prognostic characteristics, accrual rates, enrollment projections by sex
and race, and the historical outcome and toxicity rates behind its design. This extractor reads the
statistics, design, background and objective sections, returns one fact per number with verbatim
quotes, parses every number deterministically, checks every quote against the PDF and has each fact
judged by independent verifier votes (majority wins). Rejected facts are re-extracted with the
reviewers' notes (automatic repair) and judged again. A fact that is not quote-verified, has no
parsable value or is not judged FAITHFUL is kept but marked REVIEW_REQUIRED, and is never used.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import expressions as ex
from . import schemas as sc
from .compiler import ProtocolCompiler, _chunks, _majority
from .ingest import Section, extract
from .normalise import Provenance, Source, canonical_label

FACTS_VERSION = "protocol-facts-1.1.0"
FACT_SECTION_TYPES = {"statistics", "sample_size", "background", "objectives", "schema_design", "interim_analysis",
                      "endpoints", "enrollment_procedures"}
REPAIR_ROUNDS = 2
PERCENT = re.compile(r"%|\bpercent\b", re.IGNORECASE)
QUALIFIERS = (("approximately", r"approximately|approx\.?|about|around|roughly|nearly|~"),
              ("at least", r"at least|a minimum of|minimum of"),
              ("at most", r"at most|a maximum of|maximum of|up to"),
              ("less than", r"less than|fewer than|under|below|<"),
              ("more than", r"more than|greater than|over|above|>"))


def fact_value(value_quote: str, numerator_quote: str, denominator_quote: str, unit_quote: str, upper_quote: str = "") -> dict:
    """The number a fact states. A count out of a total gives the proportion; a percentage is a proportion."""
    num, den = ex.parse_number(numerator_quote), ex.parse_number(denominator_quote)
    if num is not None and den:
        return {"value": num / den, "scale": "proportion", "numerator": num, "denominator": den}
    v = ex.parse_number(value_quote)
    if v is None:
        return {"value": None, "scale": None}
    percent = bool(PERCENT.search(value_quote or "") or PERCENT.search(unit_quote or "") or PERCENT.search(upper_quote or ""))
    hi = ex.parse_number(upper_quote)
    out = {"value": v / 100.0 if percent else v, "scale": "proportion" if percent else "number"}
    if hi is not None:
        out["upper"] = hi / 100.0 if percent else hi
    if not percent:
        out["unit"] = re.sub(r"\s+", " ", unit_quote or "").strip() or None
    return out


def qualifier(evidence: str, value_quote: str) -> str | None:
    """'approximately', 'at least', ... when the words just before the stated number say so."""
    if not evidence or not value_quote:
        return None
    inside = _leading_qualifier(value_quote)  # 'less than 30%' carries its qualifier in the value quote itself
    if inside:
        return inside
    at = evidence.find(value_quote)
    if at < 0:
        return None
    before = evidence[max(0, at - 30):at].casefold()
    for name, pattern in QUALIFIERS:
        if re.search(rf"(?:{pattern})\W*$", before):
            return name
    return None


def _leading_qualifier(text: str) -> str | None:
    head = (text or "").casefold().strip()
    for name, pattern in QUALIFIERS:
        if re.match(rf"(?:{pattern})\b\W*\d", head) or re.match(rf"(?:{pattern})\s*\d", head):
            return name
    return None


def stated_qualifier(fact: dict) -> str | None:
    """The qualifier of a fact's number: recorded at extraction, or leading its verified value quote."""
    return fact.get("qualifier") or _leading_qualifier(((fact.get("value_text") or {}).get("text")) or "")


def _q(x):
    return (x or {}).get("text") if isinstance(x, dict) else x


def render_fact(f: dict) -> str:
    v = f["value"]
    written = _q(f.get("value_text")) or "?"
    if _q(f.get("upper_text")):
        written += f" to {_q(f['upper_text'])}"
    if _q(f.get("numerator_text")) and _q(f.get("denominator_text")):
        written = f"{_q(f['numerator_text'])} of {_q(f['denominator_text'])}" + (f" ({_q(f.get('value_text'))})" if _q(f.get("value_text")) else "")
    number = (f"{f['qualifier']} " if f.get("qualifier") else "") + written
    unit = _q(f.get("unit_text"))
    if unit and not (PERCENT.fullmatch(unit.strip()) and PERCENT.search(written)):  # '45%' with unit '%' is not '45% %'
        number += f" {unit}"
    if v["value"] is not None and v["scale"] == "proportion":
        number += f" [read as proportion {v['value']:.4g}" + (f" to {v['upper']:.4g}" if v.get("upper") is not None else "") + "]"
    parts = [f"{f['kind']}: {_q(f['subject']) or f['canonical_variable']!r}"]
    if _q(f.get("category")):
        parts.append(f"level {_q(f['category'])!r}")
    parts.append(f"value {number}")
    if _q(f.get("time_point")):
        parts.append(f"at {_q(f['time_point'])!r}")
    if _q(f.get("population")):
        parts.append(f"population {_q(f['population'])!r}")
    if _q(f.get("arm")):
        parts.append(f"treatment {_q(f['arm'])!r}")
    parts.append(f"source {f['source']}" + (f" ({_q(f['source_study'])})" if _q(f.get("source_study")) else ""))
    return "; ".join(parts)


class FactExtractor:
    def __init__(self, model: Any, workers: int = 6, votes: int = 3) -> None:
        self.model, self.workers, self.votes = model, workers, max(1, votes)

    def run(self, protocol: Path, out_dir: Path) -> dict:
        doc = extract(protocol)
        compiler = ProtocolCompiler(self.model, workers=self.workers)
        types = compiler.classify(doc)
        chosen = [s for s in doc.sections if set(types.get(s.number, [])) & FACT_SECTION_TYPES and (s.lines or s.tables)]
        groups = _chunks(chosen)
        with ThreadPoolExecutor(self.workers) as pool:
            outputs = list(pool.map(lambda g: (g, compiler._call("facts", sc.FACTS, sc.FACTS_INSTRUCTIONS, g)), groups))
        prov = Provenance(doc, FACTS_VERSION)
        facts, seen = [], set()
        for group, out in outputs:
            for raw in out["facts"]:
                sig = _signature(raw)
                if sig in seen:
                    continue
                seen.add(sig)
                facts.append(self._build(raw, group, prov, f"F{len(facts) + 1:03d}"))
        self.text_of = {tuple(s.number for s in g): "\n".join(f"{s.number} {s.title}\n{s.text()}" for s in g)[:120000] for g, _ in outputs}
        self.groups = {tuple(s.number for s in g): g for g, _ in outputs}
        self._verify(facts)
        repaired: list[str] = []
        for _round in range(REPAIR_ROUNDS):
            fixed = self._repair(facts, compiler, prov)
            if not fixed:
                break
            self._verify([f for f in facts if f["fact_id"] in fixed])
            repaired += [i for i in fixed if i not in repaired]
        for f in facts:
            f["status"] = "USABLE" if (f.get("semantic_status") == "FAITHFUL" and not f["quote_issues"]) else "REVIEW_REQUIRED"
        result = {"facts_version": FACTS_VERSION, "protocol": {"path": doc.path, "sha256": doc.doc_id},
                  "sections": [s.number for s in chosen], "facts": facts, "repaired": repaired,
                  "summary": {"facts": len(facts), "usable": sum(f["status"] == "USABLE" for f in facts), "repaired": len(repaired),
                              "by_kind": _count(f["kind"] for f in facts), "by_source": _count(f["source"] for f in facts),
                              "quotes": len(prov.records), "quotes_not_found": sum(not r["verified"] for r in prov.records)}}
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "population_facts.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
        (out_dir / "audit.json").write_text(json.dumps(prov.records, indent=1, ensure_ascii=False), encoding="utf-8")
        (out_dir / "facts_review.md").write_text(_report(result), encoding="utf-8")
        return result["summary"]

    def _build(self, raw: dict, group: list[Section], prov: Provenance, fact_id: str) -> dict:
        src = Source.of(group)

        def q(text: str, field: str, fragments: bool = False) -> dict | None:
            if not text or not text.strip():
                return None
            rec = prov.add(src, text, "facts", field, allow_fragments=fragments)
            return {"text": text, "provenance": rec["id"], "verified": rec["verified"]}
        value = fact_value(raw["value_quote"], raw["numerator_quote"], raw["denominator_quote"], raw["unit_quote"], raw["upper_value_quote"])
        fact = {"fact_id": fact_id, "kind": raw["kind"], "source": raw["source"],
                "canonical_variable": canonical_label(raw["canonical_variable"]) or canonical_label(raw["subject_quote"]),
                "canonical_category": canonical_label(raw["canonical_category"]) or canonical_label(raw["category_quote"]),
                "subject": q(raw["subject_quote"], "subject"), "category": q(raw["category_quote"], "category"),
                "value": value, "value_text": q(raw["value_quote"], "value"), "upper_text": q(raw["upper_value_quote"], "upper_value"),
                "numerator_text": q(raw["numerator_quote"], "numerator"), "denominator_text": q(raw["denominator_quote"], "denominator"),
                "unit_text": q(raw["unit_quote"], "unit"), "time_point": q(raw["time_point_quote"], "time_point"),
                "population": q(raw["population_quote"], "population", True), "arm": q(raw["arm_quote"], "arm", True),
                "source_study": q(raw["source_study_quote"], "source_study"), "evidence": q(raw["evidence_quote"], "evidence", True),
                "qualifier": qualifier(raw["evidence_quote"], raw["value_quote"] or raw["numerator_quote"]),
                "sections": [s.number for s in group]}
        number_quotes = [fact[k] for k in ("value_text", "numerator_text", "denominator_text") if fact[k]]
        fact["quote_issues"] = [f"{k} quote not found in the PDF" for k in ("subject", "category", "value_text", "upper_text",
                                                                          "numerator_text", "denominator_text", "time_point", "evidence")
                                if fact[k] and not fact[k]["verified"]]
        if value["value"] is None or not number_quotes:
            fact["quote_issues"].append("no stated number could be parsed")
        fact["rendering"] = render_fact(fact)
        return fact

    def _verify(self, facts: list[dict]) -> None:
        jobs = [(f, vote) for f in facts for vote in range(self.votes)]

        def run(job):
            f, vote = job
            payload = {"instructions": sc.VERIFY_INSTRUCTIONS + sc.FACTS_VERIFY_NOTE, "text": self.text_of[tuple(f["sections"])],
                       "items": [{"item_id": f["fact_id"], "rendering": f["rendering"], "evidence": _q(f["evidence"]) or "", "related": []}]}
            if vote:
                payload["independent_review"] = f"review {vote + 1} of {self.votes}: judge from scratch"
            try:
                out = self.model.extract("protocol_verify", sc.VERIFY, payload)
                return f, next((v for v in out.get("verdicts", []) if v.get("item_id") == f["fact_id"]), None)
            except Exception:  # noqa: BLE001 - a failed vote counts as no vote
                return f, None
        with ThreadPoolExecutor(self.workers) as pool:
            results = list(pool.map(run, jobs))
        cast: dict[str, list[dict]] = {}
        for f, v in results:
            if v is not None and v.get("verdict") in {"FAITHFUL", "INCOMPLETE", "INCORRECT", "NOT_A_RULE"}:
                cast.setdefault(f["fact_id"], []).append(v)
        for f in facts:
            votes = cast.get(f["fact_id"], [])
            v = _majority(votes, self.votes)
            f["verification"] = {"votes": [x["verdict"] for x in votes],
                                 "notes": [x["reviewer_note"] for x in votes if x["verdict"] != "FAITHFUL" and x.get("reviewer_note")],
                                 **({k: v[k] for k in ("verdict", "problem", "problem_quote", "reviewer_note")} if v else {"verdict": "NO_MAJORITY"})}
            f["semantic_status"] = v["verdict"] if v and v["verdict"] in {"FAITHFUL", "INCOMPLETE", "INCORRECT"} else "UNVERIFIED"

    def _repair(self, facts: list[dict], compiler: ProtocolCompiler, prov: Provenance) -> list[str]:
        """Re-extract every fact the verifier majority rejected, with the reviewers' notes, under the same id."""
        todo = [f for f in facts if f.get("semantic_status") in {"INCOMPLETE", "INCORRECT"}]

        def run(f):
            problem = {"compiled_fact": f["rendering"], "evidence": _q(f["evidence"]) or "", "reviewer_notes": f["verification"]["notes"]}
            try:
                return f, compiler._call("facts", sc.FACTS, sc.FACTS_REPAIR_PREFIX + sc.FACTS_INSTRUCTIONS,
                                         self.groups[tuple(f["sections"])], {"repair": problem})
            except Exception:  # noqa: BLE001 - a fact that cannot be repaired keeps its first extraction
                return f, None
        with ThreadPoolExecutor(self.workers) as pool:
            outcomes = list(pool.map(run, todo))
        fixed = []
        for f, out in outcomes:
            if not out or not out.get("facts"):
                continue
            new = self._build(out["facts"][0], self.groups[tuple(f["sections"])], prov, f["fact_id"])
            new["repair"] = {"previous_rendering": f["rendering"], "previous_notes": f["verification"]["notes"]}
            f.clear()
            f.update(new)
            fixed.append(f["fact_id"])
        return fixed


def _signature(raw: dict) -> tuple:
    return (raw["kind"], canonical_label(raw["canonical_variable"]), canonical_label(raw["canonical_category"]),
            ex.parse_number(raw["value_quote"]), ex.parse_number(raw["numerator_quote"]),
            *(re.sub(r"\W+", "", (raw[k] or "").casefold()) for k in ("source_study_quote", "time_point_quote", "arm_quote", "population_quote")))


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _report(result: dict) -> str:
    lines = [f"# Quantitative protocol facts ({result['facts_version']})", "",
             f"Protocol: {result['protocol']['path']} (sha256 {result['protocol']['sha256'][:16]}...)", "",
             (f"{result['summary']['usable']} of {result['summary']['facts']} facts usable (quote-verified, parsed and judged FAITHFUL "
              f"by the verifier majority; {result['summary']['repaired']} repaired automatically). Facts marked REVIEW_REQUIRED are "
              "never used by the simulation."), ""]
    for f in result["facts"]:
        lines.append(f"- **{f['fact_id']}** [{f['status']}] votes {f['verification']['votes']}: {f['rendering']}")
        if f["status"] != "USABLE":
            reasons = f["quote_issues"] + ([f["verification"].get("reviewer_note")] if f["verification"].get("reviewer_note") else [])
            lines.append(f"  - {'; '.join(r for r in reasons if r)}")
    return "\n".join(lines) + "\n"
